# -*- coding: utf-8 -*-
"""
AutoMatchingService - Automatisches Dokumenten-Matching.

Feature #7: Automation 2.0
Findet zusammengehoerige Dokumente:
Bestellung <-> Lieferschein <-> Rechnung

Basierend auf:
- PO-Nummer (exakter Match)
- Betrag + Lieferant + Datum (Fuzzy Match)

Nutzt models_approval_extended für AutoMatchResult.
"""

from __future__ import annotations

import re
import structlog
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import Document
from app.db.models_approval_extended import AutoMatchResult

logger = structlog.get_logger(__name__)

# PO-Nummern-Muster (deutsch und englisch)
PO_NUMBER_PATTERNS = [
    r"(?:PO|Bestellnr|Bestellung|Bestell-Nr|Order)[.\s:#-]*(\w{2,}-?\d{3,})",
    r"(?:Auftrags?(?:nummer|nr))[.\s:#-]*(\w{2,}-?\d{3,})",
]


class AutoMatchingService:
    """Automatisches Matching: Bestellung <-> Lieferschein <-> Rechnung.

    Workflow:
    1. Neues Dokument wird verarbeitet
    2. find_matches() extrahiert Schluesselfelder
    3. Sucht nach passenden Dokumenten in der Datenbank
    4. Erstellt AutoMatchResult-Einträge mit Konfidenz
    5. User kann Matches bestätigen
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Auto-Matching Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def find_matches(
        self,
        db: AsyncSession,
        company_id: UUID,
        document_id: UUID,
    ) -> List[AutoMatchResult]:
        """Passende Dokumente für ein gegebenes Dokument finden.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            document_id: ID des Dokuments

        Returns:
            Liste der erstellten AutoMatchResult-Einträge
        """
        doc_stmt = select(Document).where(
            and_(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        doc_result = await db.execute(doc_stmt)
        source_doc = doc_result.scalar_one_or_none()

        if not source_doc:
            logger.warning(
                "document_not_found_for_matching",
                document_id=str(document_id),
            )
            return []

        doc_text = source_doc.extracted_text or ""
        doc_metadata = source_doc.metadata_extracted or {}

        po_number = self._extract_po_number(doc_text, doc_metadata)
        supplier_id = source_doc.business_entity_id

        matches: List[AutoMatchResult] = []

        # 1. Match per PO-Nummer (hoechste Konfidenz)
        if po_number:
            po_matches = await self._find_by_po_number(
                db, company_id, document_id, po_number
            )
            matches.extend(po_matches)

        # 2. Match per Lieferant (mittel Konfidenz)
        if supplier_id:
            supplier_matches = await self._find_by_supplier(
                db, company_id, document_id, supplier_id, doc_metadata
            )
            # Duplikate vermeiden
            existing_ids = {m.matched_document_id for m in matches}
            for sm in supplier_matches:
                if sm.matched_document_id not in existing_ids:
                    matches.append(sm)

        if matches:
            for match in matches:
                db.add(match)
            await db.flush()

            logger.info(
                "matches_found",
                document_id=str(document_id),
                match_count=len(matches),
            )

        return matches

    async def get_unmatched_documents(
        self,
        db: AsyncSession,
        company_id: UUID,
        limit: int = 100,
    ) -> List[Dict[str, object]]:
        """Dokumente ohne Match finden.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            limit: Maximale Anzahl

        Returns:
            Liste von Dicts mit Dokument-Informationen
        """
        # IDs die bereits in Matches vorkommen
        matched_source_ids = select(AutoMatchResult.document_id).where(
            AutoMatchResult.company_id == company_id,
        )
        matched_target_ids = select(AutoMatchResult.matched_document_id).where(
            AutoMatchResult.company_id == company_id,
        )

        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.id.notin_(matched_source_ids),
                    Document.id.notin_(matched_target_ids),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        documents = result.scalars().all()

        return [
            {
                "id": str(doc.id),
                "filename": doc.original_filename,
                "document_type": doc.document_type,
                "created_at": (
                    doc.created_at.isoformat() if doc.created_at else None
                ),
                "business_entity_id": (
                    str(doc.business_entity_id)
                    if doc.business_entity_id
                    else None
                ),
            }
            for doc in documents
        ]

    async def confirm_match(
        self,
        db: AsyncSession,
        match_id: UUID,
        user_id: UUID,
        company_id: UUID,
    ) -> Optional[AutoMatchResult]:
        """Match manuell bestätigen.

        Args:
            db: Async Database Session
            match_id: ID des AutoMatchResult
            user_id: ID des bestätigenden Users
            company_id: ID der Firma (Multi-Tenant Isolation)

        Returns:
            Aktualisiertes AutoMatchResult oder None
        """
        stmt = select(AutoMatchResult).where(
            and_(
                AutoMatchResult.id == match_id,
                AutoMatchResult.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        match = result.scalar_one_or_none()

        if not match:
            return None

        match.is_confirmed = True
        match.confirmed_by_user_id = user_id
        await db.flush()

        logger.info(
            "match_confirmed",
            match_id=str(match_id),
            user_id=str(user_id),
        )

        return match

    async def run_batch_matching(
        self,
        db: AsyncSession,
        company_id: UUID,
        limit: int = 500,
    ) -> Dict[str, object]:
        """Batch-Matching für alle ungematchten Dokumente.

        Args:
            db: Async Database Session
            company_id: ID der Firma
            limit: Maximale Anzahl

        Returns:
            Dict mit Verarbeitungsstatistiken
        """
        unmatched = await self.get_unmatched_documents(db, company_id, limit=limit)

        total_matched = 0
        total_processed = 0
        errors = 0

        for doc_info in unmatched:
            try:
                doc_id = UUID(str(doc_info["id"]))
                matches = await self.find_matches(db, company_id, doc_id)
                total_processed += 1
                if matches:
                    total_matched += len(matches)
            except Exception as exc:
                errors += 1
                logger.debug(
                    "batch_match_error",
                    document_id=str(doc_info.get("id")),
                    error_type=type(exc).__name__,
                )

        logger.info(
            "batch_matching_completed",
            company_id=str(company_id),
            processed=total_processed,
            matched=total_matched,
            errors=errors,
        )

        return {
            "processed": total_processed,
            "matched": total_matched,
            "errors": errors,
        }

    # =========================================================================
    # Hilfsmethoden
    # =========================================================================

    def _extract_po_number(
        self,
        text: str,
        metadata: Dict[str, object],
    ) -> Optional[str]:
        """PO-Nummer aus Text oder Metadaten extrahieren."""
        po = metadata.get("po_number") or metadata.get("order_number")
        if po:
            return str(po)

        for pattern in PO_NUMBER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_amount(
        self,
        metadata: Dict[str, object],
    ) -> Optional[Decimal]:
        """Betrag aus Metadaten extrahieren."""
        amount = (
            metadata.get("total_amount")
            or metadata.get("amount")
            or metadata.get("netto")
        )
        if amount is not None:
            try:
                return Decimal(str(amount))
            except Exception:
                pass
        return None

    def _determine_match_type(
        self,
        source_type: str,
        candidate_type: str,
    ) -> Optional[str]:
        """Bestimmt den Match-Typ aus den Dokumenttypen.

        Returns:
            Match-Typ-String oder None wenn keine sinnvolle Kombination
        """
        types = {source_type.lower(), candidate_type.lower()}

        order_keywords = {"order", "bestellung", "purchase"}
        delivery_keywords = {"delivery", "lieferschein", "shipping"}
        invoice_keywords = {"invoice", "rechnung", "bill"}

        has_order = bool(types.intersection(order_keywords))
        has_delivery = bool(types.intersection(delivery_keywords))
        has_invoice = bool(types.intersection(invoice_keywords))

        if has_order and has_delivery:
            return "bestellung_lieferschein"
        elif has_delivery and has_invoice:
            return "lieferschein_rechnung"
        elif has_order and has_invoice:
            return "bestellung_rechnung"

        return None

    async def _find_by_po_number(
        self,
        db: AsyncSession,
        company_id: UUID,
        source_doc_id: UUID,
        po_number: str,
    ) -> List[AutoMatchResult]:
        """Matches per PO-Nummer finden."""
        stmt = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.id != source_doc_id,
                Document.extracted_text.ilike(f"%{po_number}%"),
            )
        ).limit(20)

        result = await db.execute(stmt)
        candidates = result.scalars().all()

        # Quelldokument-Typ laden
        source_stmt = select(Document.document_type).where(
            Document.id == source_doc_id
        )
        source_result = await db.execute(source_stmt)
        source_type = source_result.scalar() or ""

        matches: List[AutoMatchResult] = []
        for candidate in candidates:
            match_type = self._determine_match_type(
                source_type, candidate.document_type or ""
            )

            match_details: Dict[str, object] = {"po_number": True}
            confidence = 0.95

            # Betrags-Vergleich wenn verfügbar
            source_doc_stmt = select(Document).where(Document.id == source_doc_id)
            source_doc_result = await db.execute(source_doc_stmt)
            source_doc = source_doc_result.scalar_one_or_none()

            if source_doc:
                source_amount = self._extract_amount(
                    source_doc.metadata_extracted or {}
                )
                candidate_amount = self._extract_amount(
                    candidate.metadata_extracted or {}
                )
                if source_amount and candidate_amount:
                    amount_ratio = min(source_amount, candidate_amount) / max(
                        source_amount, candidate_amount
                    )
                    match_details["amount"] = float(round(amount_ratio, 3))
                    if amount_ratio >= 0.95:
                        confidence = min(confidence + 0.03, 0.99)

            auto_match = AutoMatchResult(
                company_id=company_id,
                document_id=source_doc_id,
                matched_document_id=candidate.id,
                match_type=match_type or "bestellung_rechnung",
                confidence=confidence,
                match_details=match_details,
                is_confirmed=False,
            )
            matches.append(auto_match)

        return matches

    async def _find_by_supplier(
        self,
        db: AsyncSession,
        company_id: UUID,
        source_doc_id: UUID,
        supplier_id: UUID,
        source_metadata: Dict[str, object],
    ) -> List[AutoMatchResult]:
        """Matches per Lieferant + Betrag finden."""
        stmt = (
            select(Document)
            .where(
                and_(
                    Document.company_id == company_id,
                    Document.id != source_doc_id,
                    Document.business_entity_id == supplier_id,
                )
            )
            .order_by(Document.created_at.desc())
            .limit(20)
        )

        result = await db.execute(stmt)
        candidates = result.scalars().all()

        source_amount = self._extract_amount(source_metadata)

        # Quelldokument-Typ laden
        source_stmt = select(Document.document_type).where(
            Document.id == source_doc_id
        )
        source_result = await db.execute(source_stmt)
        source_type = source_result.scalar() or ""

        matches: List[AutoMatchResult] = []
        for candidate in candidates:
            match_details: Dict[str, object] = {"supplier": True}
            confidence = 0.5  # Basis: gleicher Lieferant

            candidate_metadata = candidate.metadata_extracted or {}
            candidate_amount = self._extract_amount(candidate_metadata)

            if source_amount and candidate_amount:
                amount_ratio = min(source_amount, candidate_amount) / max(
                    source_amount, candidate_amount
                )
                match_details["amount"] = float(round(amount_ratio, 3))
                if amount_ratio >= 0.95:
                    confidence += 0.3
                elif amount_ratio >= 0.85:
                    confidence += 0.15

            match_type = self._determine_match_type(
                source_type, candidate.document_type or ""
            )

            if confidence >= 0.7 and match_type:
                auto_match = AutoMatchResult(
                    company_id=company_id,
                    document_id=source_doc_id,
                    matched_document_id=candidate.id,
                    match_type=match_type,
                    confidence=min(confidence, 0.95),
                    match_details=match_details,
                    is_confirmed=False,
                )
                matches.append(auto_match)

        return matches
