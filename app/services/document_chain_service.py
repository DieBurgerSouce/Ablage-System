# -*- coding: utf-8 -*-
"""Document Chain Service.

Verwaltet Auftragsketten (Document Chains):
Angebot → Auftragsbestätigung → Lieferschein → Rechnung → Gutschrift

Features:
- Automatische Erkennung zusammengehoeriger Dokumente
- Manuelle Verknüpfung von Dokumenten
- Differenz-Erkennung zwischen Dokumenten
- Chain-Visualisierung
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Tuple, Set, TypedDict
from uuid import UUID, uuid4
import structlog
import re

from sqlalchemy import select, func, and_, or_, update, delete, cast
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


class RelationshipType(str, Enum):
    """Arten von Dokumentbeziehungen."""
    QUOTE_TO_ORDER = "quote_to_order"  # Angebot -> Auftrag
    ORDER_TO_DELIVERY = "order_to_delivery"  # Auftrag -> Lieferschein
    DELIVERY_TO_INVOICE = "delivery_to_invoice"  # Lieferschein -> Rechnung
    INVOICE_TO_CREDIT = "invoice_to_credit_note"  # Rechnung -> Gutschrift
    ORDER_TO_INVOICE = "order_to_invoice"  # Auftrag -> Rechnung (ohne Lieferschein)
    QUOTE_TO_INVOICE = "quote_to_invoice"  # Angebot -> Rechnung (Direktkauf)
    RELATED = "related"  # Allgemeine Verwandtschaft


class DiscrepancyType(str, Enum):
    """Arten von Abweichungen zwischen Dokumenten."""
    AMOUNT_MISMATCH = "amount_mismatch"
    QUANTITY_MISMATCH = "quantity_mismatch"
    MISSING_POSITION = "missing_position"
    EXTRA_POSITION = "extra_position"
    DATE_INCONSISTENCY = "date_inconsistency"
    CUSTOMER_MISMATCH = "customer_mismatch"
    REFERENCE_MISMATCH = "reference_mismatch"


class DiscrepancySeverity(str, Enum):
    """Schweregrad von Abweichungen."""
    INFO = "info"  # Harmlos
    WARNING = "warning"  # Prüfung empfohlen
    ERROR = "error"  # Muss geprüft werden
    CRITICAL = "critical"  # Blockiert Workflow


# Mapping: Document Type -> Chain Position
CHAIN_POSITIONS = {
    "quote": 1,
    "order": 2,
    "delivery_note": 3,
    "invoice": 4,
    "credit_note": 5,
}


@dataclass
class ChainDocument:
    """Ein Dokument in einer Kette."""
    id: UUID
    document_type: str
    chain_position: int
    filename: str
    document_date: Optional[datetime]
    amount: Optional[Decimal]
    reference_numbers: Dict[str, str]  # order_number, delivery_note_number, etc.
    created_at: datetime


@dataclass
class DocumentChain:
    """Eine vollständige Auftragskette."""
    chain_id: str
    company_id: UUID
    documents: List[ChainDocument]
    document_count: int
    chain_started_at: datetime
    chain_updated_at: datetime
    has_quote: bool
    has_order: bool
    has_delivery_note: bool
    has_invoice: bool
    has_credit_note: bool
    open_discrepancies: int
    is_complete: bool  # Hat alle erwarteten Dokumente


@dataclass
class ChainDiscrepancy:
    """Eine Abweichung zwischen Dokumenten."""
    id: UUID
    chain_id: str
    source_document_id: UUID
    target_document_id: UUID
    discrepancy_type: DiscrepancyType
    field_name: Optional[str]
    expected_value: str
    actual_value: str
    difference_percentage: Optional[float]
    severity: DiscrepancySeverity
    is_resolved: bool
    created_at: datetime


@dataclass
class ChainMatchResult:
    """Ergebnis eines Auto-Match-Versuchs."""
    matched: bool
    chain_id: Optional[str]
    relationship_type: Optional[RelationshipType]
    confidence: float
    matched_documents: List[UUID]
    match_reason: str


class DiscrepancyData(TypedDict):
    """Typisierte Datenstruktur für Discrepancy-Erkennung.

    Ersetzt Dict[str, Any] für Type-Safety (Critical Rule #4).
    """
    type: str
    field: str
    expected_value: str
    actual_value: str
    diff_pct: Optional[float]
    severity: str


class DocumentChainService:
    """Service für Auftragsketten-Management.

    Automatische Erkennung:
    - Über Referenznummern (Bestellnummer, Angebotsnummer, etc.)
    - Über Kundennummer + ähnliche Betraege
    - Über OCR-Text-Analyse
    """

    # Schwellenwerte für Auto-Matching
    AMOUNT_TOLERANCE_PERCENT = 1.0  # 1% Toleranz bei Betraegen
    MIN_CONFIDENCE_AUTO = 0.85  # Min 85% Konfidenz für Auto-Link

    async def create_chain(
        self,
        db: AsyncSession,
        documents: List[UUID],
        company_id: UUID,
        user_id: UUID,
        chain_id: Optional[str] = None,
    ) -> str:
        """Erstelle eine neue Auftragskette.

        Args:
            db: Datenbank-Session
            documents: Liste von Dokument-IDs
            company_id: Firmen-ID
            user_id: Benutzer-ID
            chain_id: Optionale Chain-ID (sonst auto-generiert)

        Returns:
            Chain-ID
        """
        from app.db.models import Document

        if not documents:
            raise ValueError("Mindestens ein Dokument erforderlich")

        # Chain-ID generieren oder verwenden
        if not chain_id:
            # Format: FIRMA-JAHR-LAUFNUMMER
            year = utc_now().year
            stmt = select(func.count()).select_from(Document).where(
                and_(
                    Document.company_id == company_id,
                    Document.chain_id.isnot(None),
                    Document.chain_id.like(f"%-{year}-%"),
                )
            )
            result = await db.execute(stmt)
            count = result.scalar() or 0
            chain_id = f"CHAIN-{year}-{count + 1:05d}"

        # Dokumente laden und Chain zuweisen
        for idx, doc_id in enumerate(documents):
            doc_stmt = select(Document).where(Document.id == doc_id)
            result = await db.execute(doc_stmt)
            doc = result.scalar_one_or_none()

            if not doc:
                logger.warning(f"Dokument nicht gefunden: {doc_id}")
                continue

            # Chain-Position basierend auf Dokumenttyp
            position = CHAIN_POSITIONS.get(doc.document_type, idx + 1)

            doc.chain_id = chain_id
            doc.chain_position = position
            if idx == 0:
                doc.chain_root_document_id = None  # Erstes Dokument
            else:
                doc.chain_root_document_id = documents[0]

        await db.flush()

        logger.info(
            "Auftragskette erstellt",
            chain_id=chain_id,
            document_count=len(documents),
        )

        return chain_id

    async def link_documents(
        self,
        db: AsyncSession,
        source_document_id: UUID,
        target_document_id: UUID,
        relationship_type: RelationshipType,
        company_id: UUID,
        user_id: UUID,
        auto_detected: bool = False,
        confidence_score: Optional[float] = None,
    ) -> UUID:
        """Verknüpfe zwei Dokumente.

        Args:
            db: Datenbank-Session
            source_document_id: Quell-Dokument (z.B. Angebot)
            target_document_id: Ziel-Dokument (z.B. Auftrag)
            relationship_type: Art der Beziehung
            company_id: Firmen-ID
            user_id: Benutzer-ID
            auto_detected: True wenn automatisch erkannt
            confidence_score: Konfidenz bei Auto-Detection

        Returns:
            ID der neuen Beziehung
        """
        from app.db.models import DocumentRelationship, Document

        # Dokumente prüfen
        source = await db.get(Document, source_document_id)
        target = await db.get(Document, target_document_id)

        if not source or not target:
            raise ValueError("Quell- oder Zieldokument nicht gefunden")

        if source.company_id != company_id or target.company_id != company_id:
            raise ValueError("Dokumente gehoeren nicht zur selben Firma")

        # Chain-ID bestimmen oder erstellen
        chain_id = source.chain_id or target.chain_id
        if not chain_id:
            # Neue Chain erstellen
            chain_id = await self.create_chain(
                db, [source_document_id, target_document_id], company_id, user_id
            )
        else:
            # Beide Dokumente der Chain zuweisen
            source.chain_id = chain_id
            target.chain_id = chain_id

        # Beziehung erstellen
        relationship = DocumentRelationship(
            id=uuid4(),
            source_document_id=source_document_id,
            target_document_id=target_document_id,
            relationship_type=relationship_type.value,
            chain_id=chain_id,
            auto_detected=auto_detected,
            confidence_score=confidence_score,
            validated=not auto_detected,  # Manuell = sofort validiert
            validated_at=utc_now() if not auto_detected else None,
            validated_by_id=user_id if not auto_detected else None,
            created_at=utc_now(),
            created_by_id=user_id,
            company_id=company_id,
        )

        db.add(relationship)
        await db.flush()

        # Differenzen prüfen
        await self._check_discrepancies(db, source, target, chain_id, company_id)

        logger.info(
            "Dokumente verknüpft",
            source_id=str(source_document_id),
            target_id=str(target_document_id),
            relationship=relationship_type.value,
            chain_id=chain_id,
        )

        return relationship.id

    async def get_chain(
        self,
        db: AsyncSession,
        chain_id: str,
        company_id: UUID,
    ) -> Optional[DocumentChain]:
        """Hole eine vollständige Auftragskette.

        Args:
            db: Datenbank-Session
            chain_id: Chain-ID
            company_id: Firmen-ID

        Returns:
            DocumentChain oder None
        """
        from app.db.models import Document, DocumentChainDiscrepancy

        # Dokumente laden
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.chain_id == chain_id,
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
            .order_by(Document.chain_position.asc(), Document.created_at.asc())
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        if not documents:
            return None

        # Discrepancies zaehlen
        discrepancy_stmt = select(func.count()).select_from(DocumentChainDiscrepancy).where(
            and_(
                DocumentChainDiscrepancy.chain_id == chain_id,
                DocumentChainDiscrepancy.is_resolved == False,
            )
        )
        discrepancy_result = await db.execute(discrepancy_stmt)
        open_discrepancies = discrepancy_result.scalar() or 0

        # Chain-Dokumente erstellen
        chain_documents = []
        doc_types: Set[str] = set()

        for doc in documents:
            doc_types.add(doc.document_type)

            # Referenznummern aus extracted_data
            refs = {}
            if doc.document_metadata:
                extracted = doc.document_metadata.get("extracted_data", {})
                refs = {
                    "order_number": extracted.get("order_number"),
                    "invoice_number": extracted.get("invoice_number"),
                    "delivery_note_number": extracted.get("delivery_note_number"),
                    "quotation_number": extracted.get("quotation_number"),
                }
                refs = {k: v for k, v in refs.items() if v}

            # Betrag aus extracted_data
            amount = None
            if doc.document_metadata:
                extracted = doc.document_metadata.get("extracted_data", {})
                try:
                    amount_str = extracted.get("total_amount", extracted.get("amount"))
                    if amount_str:
                        amount = Decimal(str(amount_str))
                except (ValueError, TypeError) as e:
                    logger.debug("chain_document_amount_parse_failed", document_id=str(doc.id), error_type=type(e).__name__)

            chain_documents.append(ChainDocument(
                id=doc.id,
                document_type=doc.document_type,
                chain_position=doc.chain_position or 0,
                filename=doc.original_filename,
                document_date=doc.processed_date or doc.created_at,
                amount=amount,
                reference_numbers=refs,
                created_at=doc.created_at,
            ))

        return DocumentChain(
            chain_id=chain_id,
            company_id=company_id,
            documents=chain_documents,
            document_count=len(chain_documents),
            chain_started_at=min(d.created_at for d in chain_documents),
            chain_updated_at=max(d.created_at for d in chain_documents),
            has_quote="quote" in doc_types,
            has_order="order" in doc_types,
            has_delivery_note="delivery_note" in doc_types,
            has_invoice="invoice" in doc_types,
            has_credit_note="credit_note" in doc_types,
            open_discrepancies=open_discrepancies,
            is_complete="invoice" in doc_types,  # Minimal: Rechnung vorhanden
        )

    async def get_document_chain(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
    ) -> Optional[DocumentChain]:
        """Hole Auftragskette für ein bestimmtes Dokument.

        Args:
            db: Datenbank-Session
            document_id: Dokument-ID
            company_id: Firmen-ID

        Returns:
            DocumentChain oder None
        """
        from app.db.models import Document

        doc = await db.get(Document, document_id)
        if not doc or not doc.chain_id:
            return None

        return await self.get_chain(db, doc.chain_id, company_id)

    async def auto_match_documents(
        self,
        db: AsyncSession,
        document_id: UUID,
        company_id: UUID,
    ) -> List[ChainMatchResult]:
        """Suche automatisch nach verwandten Dokumenten.

        Matching-Strategien:
        1. Referenznummern (Bestellnummer, Angebotsnummer)
        2. Kundennummer + ähnlicher Betrag + Zeitraum
        3. Textanalyse

        Args:
            db: Datenbank-Session
            document_id: Zu matchendes Dokument
            company_id: Firmen-ID

        Returns:
            Liste möglicher Matches mit Konfidenz
        """
        from app.db.models import Document

        doc = await db.get(Document, document_id)
        if not doc:
            return []

        results: List[ChainMatchResult] = []

        # Referenznummern extrahieren
        refs = {}
        if doc.document_metadata:
            extracted = doc.document_metadata.get("extracted_data", {})
            refs = {
                "order_number": extracted.get("order_number"),
                "invoice_number": extracted.get("invoice_number"),
                "delivery_note_number": extracted.get("delivery_note_number"),
                "quotation_number": extracted.get("quotation_number"),
            }
            refs = {k: v for k, v in refs.items() if v}

        # 1. Matching über Referenznummern
        if refs:
            for ref_type, ref_value in refs.items():
                matches = await self._match_by_reference(db, ref_type, ref_value, document_id, company_id)
                results.extend(matches)

        # 2. Matching über Kundennummer + Betrag
        customer_number = None
        amount = None
        if doc.document_metadata:
            extracted = doc.document_metadata.get("extracted_data", {})
            customer_number = extracted.get("customer_number")
            try:
                amount = Decimal(str(extracted.get("total_amount", 0)))
            except (ValueError, TypeError) as e:
                logger.debug("auto_match_amount_parse_failed", document_id=str(document_id), error_type=type(e).__name__)

        if customer_number and amount:
            amount_matches = await self._match_by_customer_amount(
                db, customer_number, amount, document_id, company_id
            )
            results.extend(amount_matches)

        # Duplikate entfernen und nach Konfidenz sortieren
        seen_docs: Set[UUID] = set()
        unique_results = []
        for r in sorted(results, key=lambda x: x.confidence, reverse=True):
            if r.matched_documents[0] not in seen_docs:
                seen_docs.update(r.matched_documents)
                unique_results.append(r)

        return unique_results[:10]  # Top 10 Matches

    async def get_chain_discrepancies(
        self,
        db: AsyncSession,
        chain_id: str,
        company_id: UUID,
        include_resolved: bool = False,
    ) -> List[ChainDiscrepancy]:
        """Hole alle Abweichungen einer Kette.

        Args:
            db: Datenbank-Session
            chain_id: Chain-ID
            company_id: Firmen-ID (Multi-Tenant Isolation)
            include_resolved: Auch geloeste Abweichungen

        Returns:
            Liste von Abweichungen
        """
        from app.db.models import DocumentChainDiscrepancy

        # SECURITY: Multi-Tenant Isolation - IMMER nach company_id filtern!
        conditions = [
            DocumentChainDiscrepancy.chain_id == chain_id,
            DocumentChainDiscrepancy.company_id == company_id,
        ]
        if not include_resolved:
            conditions.append(DocumentChainDiscrepancy.is_resolved == False)

        stmt = (
            select(DocumentChainDiscrepancy)
            .where(and_(*conditions))
            .order_by(DocumentChainDiscrepancy.created_at.desc())
        )

        result = await db.execute(stmt)
        discrepancies = result.scalars().all()

        return [
            ChainDiscrepancy(
                id=d.id,
                chain_id=d.chain_id,
                source_document_id=d.source_document_id,
                target_document_id=d.target_document_id,
                discrepancy_type=DiscrepancyType(d.discrepancy_type),
                field_name=d.field_name,
                expected_value=d.expected_value or "",
                actual_value=d.actual_value or "",
                difference_percentage=d.difference_percentage,
                severity=DiscrepancySeverity(d.severity),
                is_resolved=d.is_resolved,
                created_at=d.created_at,
            )
            for d in discrepancies
        ]

    async def resolve_discrepancy(
        self,
        db: AsyncSession,
        discrepancy_id: UUID,
        company_id: UUID,
        user_id: UUID,
        resolution_notes: Optional[str] = None,
    ) -> bool:
        """Markiere Abweichung als geloest.

        Args:
            db: Datenbank-Session
            discrepancy_id: ID der Abweichung
            company_id: Firmen-ID (Multi-Tenant Security Check)
            user_id: Benutzer-ID
            resolution_notes: Begruendung

        Returns:
            True bei Erfolg, False wenn nicht gefunden oder nicht berechtigt
        """
        from app.db.models import DocumentChainDiscrepancy

        # SECURITY: Multi-Tenant Check - nur Discrepancies der eigenen Firma erlauben!
        stmt = select(DocumentChainDiscrepancy).where(
            and_(
                DocumentChainDiscrepancy.id == discrepancy_id,
                DocumentChainDiscrepancy.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        discrepancy = result.scalar_one_or_none()

        if not discrepancy:
            logger.warning(
                "Abweichung nicht gefunden oder nicht berechtigt",
                discrepancy_id=str(discrepancy_id),
            )
            return False

        discrepancy.is_resolved = True
        discrepancy.resolved_at = utc_now()
        discrepancy.resolved_by_id = user_id
        discrepancy.resolution_notes = resolution_notes

        await db.flush()

        logger.info(
            "Abweichung geloest",
            discrepancy_id=str(discrepancy_id),
            chain_id=discrepancy.chain_id,
        )

        return True

    async def _check_discrepancies(
        self,
        db: AsyncSession,
        source: "Document",
        target: "Document",
        chain_id: str,
        company_id: UUID,
    ) -> None:
        """Prüfe Abweichungen zwischen zwei Dokumenten.

        Args:
            db: Datenbank-Session
            source: Quelldokument
            target: Zieldokument
            chain_id: Chain-ID
            company_id: Firmen-ID
        """
        from app.db.models import DocumentChainDiscrepancy, Document

        discrepancies: List[DiscrepancyData] = []

        # Extracted Data holen
        source_data = source.document_metadata.get("extracted_data", {}) if source.document_metadata else {}
        target_data = target.document_metadata.get("extracted_data", {}) if target.document_metadata else {}

        # Betrags-Check
        source_amount = source_data.get("total_amount")
        target_amount = target_data.get("total_amount")

        if source_amount and target_amount:
            try:
                s_amt = Decimal(str(source_amount))
                t_amt = Decimal(str(target_amount))
                diff_pct = abs((t_amt - s_amt) / s_amt * 100) if s_amt else 0

                if diff_pct > self.AMOUNT_TOLERANCE_PERCENT:
                    severity = "error" if diff_pct > 5 else "warning"
                    discrepancies.append({
                        "type": DiscrepancyType.AMOUNT_MISMATCH.value,
                        "field": "total_amount",
                        "expected_value": str(source_amount),
                        "actual_value": str(target_amount),
                        "diff_pct": float(diff_pct),
                        "severity": severity,
                    })
            except (ValueError, TypeError) as e:
                logger.debug("amount_discrepancy_check_failed", source_id=str(source.id), target_id=str(target.id), error_type=type(e).__name__)

        # Kundennummer-Check
        source_customer = source_data.get("customer_number")
        target_customer = target_data.get("customer_number")

        if source_customer and target_customer and source_customer != target_customer:
            discrepancies.append({
                "type": DiscrepancyType.CUSTOMER_MISMATCH.value,
                "field": "customer_number",
                "expected_value": str(source_customer),
                "actual_value": str(target_customer),
                "diff_pct": None,
                "severity": "critical",
            })

        # Abweichungen speichern
        for disc in discrepancies:
            db.add(DocumentChainDiscrepancy(
                id=uuid4(),
                chain_id=chain_id,
                source_document_id=source.id,
                target_document_id=target.id,
                discrepancy_type=disc["type"],
                field_name=disc["field"],
                expected_value=disc["expected_value"],
                actual_value=disc["actual_value"],
                difference_percentage=disc["diff_pct"],
                severity=disc["severity"],
                is_resolved=False,
                company_id=company_id,
            ))

    async def _match_by_reference(
        self,
        db: AsyncSession,
        ref_type: str,
        ref_value: str,
        exclude_document_id: UUID,
        company_id: UUID,
    ) -> List[ChainMatchResult]:
        """Suche Dokumente mit gleicher Referenznummer.

        Args:
            db: Datenbank-Session
            ref_type: Typ der Referenz (order_number, etc.)
            ref_value: Wert der Referenz
            exclude_document_id: Auszuschließendes Dokument
            company_id: Firmen-ID

        Returns:
            Liste von Matches
        """
        from app.db.models import Document

        # JSONB-Suche nach Referenznummer
        # PostgreSQL: document_metadata->'extracted_data'->>'order_number' = 'value'
        stmt = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.id != exclude_document_id,
                Document.deleted_at.is_(None),
                cast(Document.document_metadata, JSONB)["extracted_data"][ref_type].astext == ref_value,
            )
        )

        result = await db.execute(stmt)
        matches = result.scalars().all()

        return [
            ChainMatchResult(
                matched=True,
                chain_id=m.chain_id,
                relationship_type=self._infer_relationship(ref_type),
                confidence=0.95,  # Hohe Konfidenz bei Referenzmatch
                matched_documents=[m.id],
                match_reason=f"Gleiche {ref_type}: {ref_value}",
            )
            for m in matches
        ]

    async def _match_by_customer_amount(
        self,
        db: AsyncSession,
        customer_number: str,
        amount: Decimal,
        exclude_document_id: UUID,
        company_id: UUID,
    ) -> List[ChainMatchResult]:
        """Suche Dokumente mit gleicher Kundennummer und ähnlichem Betrag.

        Args:
            db: Datenbank-Session
            customer_number: Kundennummer
            amount: Rechnungsbetrag
            exclude_document_id: Auszuschließendes Dokument
            company_id: Firmen-ID

        Returns:
            Liste von Matches
        """
        from app.db.models import Document

        # Toleranzbereich für Betrag
        tolerance = amount * Decimal(str(self.AMOUNT_TOLERANCE_PERCENT / 100))
        min_amount = amount - tolerance
        max_amount = amount + tolerance

        # Suche nach Kundennummer
        stmt = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.id != exclude_document_id,
                Document.deleted_at.is_(None),
                cast(Document.document_metadata, JSONB)["extracted_data"]["customer_number"].astext == customer_number,
            )
        )

        result = await db.execute(stmt)
        potential_matches = result.scalars().all()

        matches = []
        for doc in potential_matches:
            if doc.document_metadata:
                extracted = doc.document_metadata.get("extracted_data", {})
                try:
                    doc_amount = Decimal(str(extracted.get("total_amount", 0)))
                    if min_amount <= doc_amount <= max_amount:
                        # Konfidenz basierend auf Betragsnaehe
                        diff_pct = abs((doc_amount - amount) / amount * 100) if amount else 0
                        confidence = max(0.7, 0.9 - diff_pct / 10)

                        matches.append(ChainMatchResult(
                            matched=True,
                            chain_id=doc.chain_id,
                            relationship_type=RelationshipType.RELATED,
                            confidence=confidence,
                            matched_documents=[doc.id],
                            match_reason=f"Gleicher Kunde {customer_number}, ähnlicher Betrag",
                        ))
                except (ValueError, TypeError) as e:
                    logger.debug("customer_amount_match_parse_failed", document_id=str(doc.id), error_type=type(e).__name__)
                    continue

        return matches

    def _infer_relationship(self, ref_type: str) -> RelationshipType:
        """Leite Beziehungstyp aus Referenztyp ab."""
        mapping = {
            "order_number": RelationshipType.ORDER_TO_INVOICE,
            "quotation_number": RelationshipType.QUOTE_TO_ORDER,
            "delivery_note_number": RelationshipType.DELIVERY_TO_INVOICE,
        }
        return mapping.get(ref_type, RelationshipType.RELATED)
