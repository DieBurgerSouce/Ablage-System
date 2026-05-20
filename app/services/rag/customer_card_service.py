"""Customer Card Service.

Generiert und verwaltet pre-computed Customer Cards mit:
- LLM-basierte Zusammenfassungen
- Schneller Abruf (< 100ms)
- Automatische Synchronisation
- Fuzzy Search
"""

import structlog
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, or_
from sqlalchemy.orm import selectinload

from app.db.models import (
    RAGCustomerCard,
    RAGDocumentChunk,
    Document,
    RAGCardSyncStatus,
)
from app.services.rag.search_service import get_rag_search_service, RAGSearchService
from app.services.rag.llm_service import get_llm_service, LLMService, LLMMessage, LLMContextType
from app.services.rag.prompt_templates import build_customer_card_prompt
from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class CustomerCardResult:
    """Ergebnis einer Customer Card Abfrage."""
    card: Optional[RAGCustomerCard]
    from_cache: bool
    generation_time_ms: Optional[int] = None


@dataclass
class CustomerSearchResult:
    """Ergebnis einer Kundensuche."""
    customer_id: str
    customer_name: str
    similarity: float
    document_count: int
    last_document_date: Optional[datetime] = None


class CustomerCardService:
    """Service für Customer Card Management."""

    def __init__(
        self,
        search_service: Optional[RAGSearchService] = None,
        llm_service: Optional[LLMService] = None
    ):
        self.search_service = search_service or get_rag_search_service()
        self.llm_service = llm_service or get_llm_service()
        self._cache: Dict[str, RAGCustomerCard] = {}

    async def get_card(
        self,
        db: AsyncSession,
        customer_id: str,
        force_refresh: bool = False
    ) -> CustomerCardResult:
        """
        Ruft Customer Card ab (< 100ms Ziel).

        Args:
            db: Database Session
            customer_id: Kunden-ID oder -Name
            force_refresh: Card neu generieren

        Returns:
            CustomerCardResult mit Card oder None
        """
        start_time = datetime.now(timezone.utc)

        # 1. Cache prüfen (In-Memory)
        if not force_refresh and customer_id in self._cache:
            card = self._cache[customer_id]
            # Prüfen ob Card noch aktuell (max 1h alt)
            if card.last_sync_at:
                age_hours = (datetime.now(timezone.utc) - card.last_sync_at).total_seconds() / 3600
                if age_hours < 1:
                    return CustomerCardResult(card=card, from_cache=True)

        # 2. Aus Datenbank laden
        result = await db.execute(
            select(RAGCustomerCard).where(
                or_(
                    RAGCustomerCard.customer_id == customer_id,
                    RAGCustomerCard.customer_name.ilike(f"%{customer_id}%")
                )
            )
        )
        card = result.scalar_one_or_none()

        if card and not force_refresh:
            # In Cache speichern
            self._cache[card.customer_id] = card

            generation_time = int(
                (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            )
            return CustomerCardResult(
                card=card,
                from_cache=False,
                generation_time_ms=generation_time
            )

        # 3. Card generieren wenn nicht vorhanden oder force_refresh
        if force_refresh or not card:
            try:
                card = await self.generate_card(
                    db=db,
                    customer_id=customer_id,
                    customer_name=customer_id  # Wird später aus Dokumenten ermittelt
                )

                generation_time = int(
                    (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                )

                return CustomerCardResult(
                    card=card,
                    from_cache=False,
                    generation_time_ms=generation_time
                )
            except Exception as e:
                logger.exception(
                    "customer_card_generation_failed",
                    customer_id=customer_id,
                    **safe_error_log(e)
                )
                return CustomerCardResult(card=None, from_cache=False)

        return CustomerCardResult(card=None, from_cache=False)

    async def generate_card(
        self,
        db: AsyncSession,
        customer_id: str,
        customer_name: str
    ) -> RAGCustomerCard:
        """
        Generiert eine neue Customer Card mit LLM.

        Args:
            db: Database Session
            customer_id: Eindeutige Kunden-ID
            customer_name: Kundenname für Suche

        Returns:
            Generierte RAGCustomerCard
        """
        logger.info(
            "generating_customer_card",
            customer_id=customer_id,
            customer_name=customer_name
        )

        # 1. Relevante Dokumente suchen
        search_results = await self.search_service.search_for_context(
            db=db,
            query=f"Kunde {customer_name}",
            context_chunks=settings.RAG_CUSTOMER_CARD_CONTEXT_CHUNKS
        )

        # 2. Kontext aufbauen
        context_texts = []
        source_document_ids = []

        for chunk in search_results:
            context_texts.append(chunk.get("text", ""))
            doc_id = chunk.get("document_id")
            if doc_id and doc_id not in source_document_ids:
                source_document_ids.append(doc_id)

        context = "\n\n---\n\n".join(context_texts) if context_texts else ""

        # 3. Quick Facts aus Dokumenten extrahieren
        quick_facts = await self._extract_quick_facts(db, source_document_ids)

        # 4. LLM für Zusammenfassung aufrufen
        messages = build_customer_card_prompt(
            customer_name=customer_name,
            context=context
        )

        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in messages
        ]

        llm_response = await self.llm_service.generate(
            messages=llm_messages,
            context_type=LLMContextType.CUSTOMER,
            enable_thinking=True
        )

        # 5. Card erstellen oder aktualisieren
        existing_card = await db.execute(
            select(RAGCustomerCard).where(
                RAGCustomerCard.customer_id == customer_id
            )
        )
        card = existing_card.scalar_one_or_none()

        if card:
            # Update
            card.summary_text = llm_response.content
            card.quick_facts = quick_facts
            card.last_full_sync_at = datetime.now(timezone.utc)
            card.sync_status = RAGCardSyncStatus.COMPLETED.value
            card.source_document_ids = [str(d) for d in source_document_ids if d]
            card.source_document_count = len(source_document_ids)
        else:
            # Neu erstellen
            card = RAGCustomerCard(
                customer_id=customer_id,
                customer_name=customer_name,
                summary_text=llm_response.content,
                quick_facts=quick_facts,
                open_invoices=[],
                active_contracts=[],
                flags=[],
                priority_level=5,  # Normal priority (0-10 scale)
                last_full_sync_at=datetime.now(timezone.utc),
                sync_status=RAGCardSyncStatus.COMPLETED.value,
                source_document_ids=[str(d) for d in source_document_ids if d],
                source_document_count=len(source_document_ids)
            )
            db.add(card)

        await db.commit()
        await db.refresh(card)

        # Cache aktualisieren
        self._cache[customer_id] = card

        logger.info(
            "customer_card_generated",
            customer_id=customer_id,
            source_documents=len(source_document_ids),
            summary_length=len(llm_response.content)
        )

        return card

    async def search_customers(
        self,
        db: AsyncSession,
        query: str,
        limit: int = 10
    ) -> List[CustomerSearchResult]:
        """
        Fuzzy-Suche nach Kunden.

        Verwendet pg_trgm für ähnlichkeitsbasierte Suche.

        Args:
            db: Database Session
            query: Suchanfrage
            limit: Max Ergebnisse

        Returns:
            Liste von CustomerSearchResult
        """
        # Fuzzy Search mit pg_trgm similarity
        # Fallback auf ILIKE wenn pg_trgm nicht verfügbar
        try:
            result = await db.execute(
                text("""
                    SELECT
                        customer_id,
                        customer_name,
                        similarity(customer_name, :query) as sim,
                        COALESCE(array_length(source_document_ids, 1), 0) as doc_count,
                        last_sync_at
                    FROM rag_customer_cards
                    WHERE customer_name % :query
                       OR customer_name ILIKE :like_query
                    ORDER BY sim DESC
                    LIMIT :limit
                """),
                {
                    "query": query,
                    "like_query": f"%{query}%",
                    "limit": limit
                }
            )
            rows = result.fetchall()

            return [
                CustomerSearchResult(
                    customer_id=row.customer_id,
                    customer_name=row.customer_name,
                    similarity=row.sim or 0.0,
                    document_count=row.doc_count,
                    last_document_date=row.last_sync_at
                )
                for row in rows
            ]

        except Exception as e:
            # Fallback ohne pg_trgm
            logger.warning("pg_trgm_not_available", **safe_error_log(e))

            result = await db.execute(
                select(RAGCustomerCard)
                .where(RAGCustomerCard.customer_name.ilike(f"%{query}%"))
                .limit(limit)
            )
            cards = result.scalars().all()

            return [
                CustomerSearchResult(
                    customer_id=c.customer_id,
                    customer_name=c.customer_name,
                    similarity=0.5,  # Default similarity
                    document_count=len(c.source_document_ids) if c.source_document_ids else 0,
                    last_document_date=c.last_sync_at
                )
                for c in cards
            ]

    async def get_all_customers(
        self,
        db: AsyncSession,
        limit: int = 100,
        offset: int = 0
    ) -> List[RAGCustomerCard]:
        """
        Ruft alle Customer Cards ab.

        Args:
            db: Database Session
            limit: Max Ergebnisse
            offset: Offset für Pagination

        Returns:
            Liste von RAGCustomerCard
        """
        result = await db.execute(
            select(RAGCustomerCard)
            .order_by(RAGCustomerCard.customer_name)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def sync_all_cards(
        self,
        db: AsyncSession,
        batch_size: int = 50
    ) -> Dict[str, int]:
        """
        Synchronisiert alle Customer Cards.

        Wird typischerweise als Nightly Job ausgeführt.

        Args:
            db: Database Session
            batch_size: Verarbeitungsgröße

        Returns:
            Statistiken über Sync
        """
        logger.info("customer_card_sync_started")

        stats = {
            "total": 0,
            "updated": 0,
            "created": 0,
            "failed": 0
        }

        # 1. Alle eindeutigen Kunden aus Dokumenten ermitteln
        # Dies ist ein vereinfachter Ansatz - in Production wuerde man
        # Kundeninformationen aus strukturierten Daten extrahieren
        customers = await self._discover_customers(db)
        stats["total"] = len(customers)

        # 2. In Batches verarbeiten
        for i in range(0, len(customers), batch_size):
            batch = customers[i:i + batch_size]

            for customer_id, customer_name in batch:
                try:
                    # Prüfen ob Card existiert
                    existing = await db.execute(
                        select(RAGCustomerCard).where(
                            RAGCustomerCard.customer_id == customer_id
                        )
                    )
                    card = existing.scalar_one_or_none()

                    if card:
                        # Card aktualisieren
                        await self.generate_card(db, customer_id, customer_name)
                        stats["updated"] += 1
                    else:
                        # Neue Card erstellen
                        await self.generate_card(db, customer_id, customer_name)
                        stats["created"] += 1

                except Exception as e:
                    logger.exception(
                        "customer_card_sync_item_failed",
                        customer_id=customer_id,
                        **safe_error_log(e)
                    )
                    stats["failed"] += 1

            # Commit nach jedem Batch
            await db.commit()

        logger.info(
            "customer_card_sync_completed",
            **stats
        )

        return stats

    async def _extract_quick_facts(
        self,
        db: AsyncSession,
        document_ids: List[str]
    ) -> Dict[str, Any]:
        """Extrahiert Quick Facts aus Dokumenten."""
        if not document_ids:
            return {}

        # Dokument-Metadaten laden
        uuid_ids = [UUID(d) for d in document_ids if d]
        if not uuid_ids:
            return {}

        result = await db.execute(
            select(Document).where(Document.id.in_(uuid_ids))
        )
        documents = result.scalars().all()

        # Quick Facts zusammenstellen
        doc_types = {}
        date_range = {"earliest": None, "latest": None}

        for doc in documents:
            # Dokumenttypen zaehlen
            doc_type = doc.doc_type or "unbekannt"
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1

            # Datumsbereich
            if doc.created_at:
                if not date_range["earliest"] or doc.created_at < date_range["earliest"]:
                    date_range["earliest"] = doc.created_at
                if not date_range["latest"] or doc.created_at > date_range["latest"]:
                    date_range["latest"] = doc.created_at

        return {
            "document_count": len(documents),
            "document_types": doc_types,
            "date_range": {
                "earliest": date_range["earliest"].isoformat() if date_range["earliest"] else None,
                "latest": date_range["latest"].isoformat() if date_range["latest"] else None
            }
        }

    async def _discover_customers(
        self,
        db: AsyncSession
    ) -> List[tuple]:
        """
        Ermittelt Kunden aus Dokumenten.

        In einer vollständigen Implementierung wuerde dies:
        - Extracted Data nach Kundennamen durchsuchen
        - NER für Kundenextraktion verwenden
        - Existierende Customer Cards berücksichtigen
        """
        # Vereinfachte Implementierung: Existierende Cards + neue aus Extracted Data
        customers = []

        # Existierende Cards
        existing_names: set[str] = set()
        result = await db.execute(
            select(
                RAGCustomerCard.customer_id,
                RAGCustomerCard.customer_name
            )
        )
        for row in result.fetchall():
            customers.append((row.customer_id, row.customer_name))
            existing_names.add(row.customer_name.lower() if row.customer_name else "")

        # Neue Kunden aus extracted_data ermitteln
        # Suche nach sender_name/company_name in Dokumenten ohne zugeordnete Customer Card
        docs_result = await db.execute(
            select(Document.extracted_data)
            .where(
                Document.extracted_data.isnot(None),
                Document.deleted_at.is_(None),
            )
            .limit(500)  # Performance-Limit
        )

        # Extrahiere eindeutige Kundennamen
        for row in docs_result.fetchall():
            if row.extracted_data:
                for key in ["sender_name", "company_name", "customer_name", "lieferant"]:
                    name = row.extracted_data.get(key)
                    if name and isinstance(name, str) and len(name) > 2:
                        name_lower = name.strip().lower()
                        if name_lower not in existing_names:
                            # Generiere eine temporaere ID basierend auf dem Namen
                            temp_id = f"new_{name_lower.replace(' ', '_')[:50]}"
                            customers.append((temp_id, name.strip()))
                            existing_names.add(name_lower)

        return customers

    def clear_cache(self, customer_id: Optional[str] = None):
        """
        Leert den In-Memory Cache.

        Args:
            customer_id: Spezifischer Kunde oder alle (None)
        """
        if customer_id:
            self._cache.pop(customer_id, None)
        else:
            self._cache.clear()


# Singleton Instance
_customer_card_service: Optional[CustomerCardService] = None


def get_customer_card_service() -> CustomerCardService:
    """Gibt CustomerCardService Singleton zurück."""
    global _customer_card_service
    if _customer_card_service is None:
        _customer_card_service = CustomerCardService()
    return _customer_card_service
