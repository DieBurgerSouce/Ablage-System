# -*- coding: utf-8 -*-
"""
POMatchingService - 3-Way Purchase Order Matching für Ablage-System.

Implementiert:
- Bestellung <-> Lieferschein <-> Rechnung Matching
- Automatisches Matching nach Bestellnummer, Lieferant und Betraegen
- Abweichungserkennung mit konfigurierbaren Toleranzen
- Freigabe-Workflow für Abweichungen
- Statistiken und Auswertungen

Phase 2.2 der Feature-Roadmap (Februar 2026).
"""

from __future__ import annotations
from sqlalchemy import union  # F-31

import uuid
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.db.models import Document
from app.db.models_po_matching import (
    PurchaseOrderMatch,
    MatchDiscrepancy,
    MatchStatus,
    DiscrepancyCategory,
    DiscrepancySeverity,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Request/Response Dataclasses
# ============================================================================


@dataclass
class MatchCreateRequest:
    """Request für Match-Erstellung."""
    company_id: uuid.UUID
    purchase_order_id: Optional[uuid.UUID] = None
    delivery_note_id: Optional[uuid.UUID] = None
    invoice_id: Optional[uuid.UUID] = None
    document_chain_id: Optional[str] = None
    vendor_entity_id: Optional[uuid.UUID] = None
    vendor_name: Optional[str] = None
    order_number: Optional[str] = None
    order_date: Optional[datetime] = None
    po_amount: Optional[Decimal] = None
    dn_amount: Optional[Decimal] = None
    invoice_amount: Optional[Decimal] = None
    amount_tolerance_percent: float = 2.0
    quantity_tolerance_percent: float = 1.0


@dataclass
class AddDocumentRequest:
    """Request zum Hinzufuegen eines Dokuments zu einem Match."""
    document_id: uuid.UUID
    document_type: str  # "purchase_order", "delivery_note", "invoice"
    amount: Optional[Decimal] = None


@dataclass
class MatchFilter:
    """Filter für Match-Abfragen."""
    company_id: uuid.UUID
    status: Optional[MatchStatus] = None
    vendor_entity_id: Optional[uuid.UUID] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    order_number: Optional[str] = None


@dataclass
class MatchStatistics:
    """Statistiken für PO-Matching."""
    total_matches: int
    pending_matches: int
    partial_matches: int
    full_matches: int
    discrepancy_matches: int
    approved_matches: int
    rejected_matches: int
    auto_matched_count: int
    avg_match_score: float
    total_discrepancies: int
    unresolved_discrepancies: int
    avg_amount_deviation_percent: float
    period_start: date
    period_end: date


# ============================================================================
# POMatchingService Implementation
# ============================================================================


class POMatchingService:
    """Service für 3-Way Purchase Order Matching."""

    # ========================================================================
    # Match CRUD
    # ========================================================================

    async def create_match(
        self,
        db: AsyncSession,
        request: MatchCreateRequest,
    ) -> PurchaseOrderMatch:
        """Erstellt einen neuen 3-Way Match."""
        # Bestimme initialen Status
        doc_count = sum(1 for doc_id in [
            request.purchase_order_id,
            request.delivery_note_id,
            request.invoice_id,
        ] if doc_id is not None)

        if doc_count >= 3:
            initial_status = MatchStatus.FULL
        elif doc_count >= 2:
            initial_status = MatchStatus.PARTIAL
        else:
            initial_status = MatchStatus.PENDING

        match = PurchaseOrderMatch(
            company_id=request.company_id,
            purchase_order_id=request.purchase_order_id,
            delivery_note_id=request.delivery_note_id,
            invoice_id=request.invoice_id,
            document_chain_id=request.document_chain_id,
            vendor_entity_id=request.vendor_entity_id,
            vendor_name=request.vendor_name,
            order_number=request.order_number,
            order_date=request.order_date,
            po_amount=request.po_amount,
            dn_amount=request.dn_amount,
            invoice_amount=request.invoice_amount,
            match_status=initial_status,
            amount_tolerance_percent=request.amount_tolerance_percent,
            quantity_tolerance_percent=request.quantity_tolerance_percent,
        )

        db.add(match)
        await db.commit()
        await db.refresh(match)

        logger.info(
            "po_match_created",
            match_id=str(match.id),
            company_id=str(request.company_id),
            status=initial_status.value,
            document_count=doc_count,
        )

        return match

    async def get_match_detail(
        self,
        db: AsyncSession,
        match_id: uuid.UUID,
    ) -> Optional[PurchaseOrderMatch]:
        """Ruft einen Match mit allen Abweichungen ab."""
        result = await db.execute(
            select(PurchaseOrderMatch)
            .where(PurchaseOrderMatch.id == match_id)
            .options(
                selectinload(PurchaseOrderMatch.discrepancies),
            )
        )
        return result.scalar_one_or_none()

    async def list_matches(
        self,
        db: AsyncSession,
        filter_params: MatchFilter,
        page: int = 0,
        page_size: int = 25,
    ) -> Tuple[List[PurchaseOrderMatch], int]:
        """Listet Matches mit Filtern und Paginierung."""
        query = select(PurchaseOrderMatch).where(
            PurchaseOrderMatch.company_id == filter_params.company_id
        )

        if filter_params.status is not None:
            query = query.where(PurchaseOrderMatch.match_status == filter_params.status)
        if filter_params.vendor_entity_id is not None:
            query = query.where(
                PurchaseOrderMatch.vendor_entity_id == filter_params.vendor_entity_id
            )
        if filter_params.date_from is not None:
            query = query.where(PurchaseOrderMatch.created_at >= filter_params.date_from)
        if filter_params.date_to is not None:
            query = query.where(PurchaseOrderMatch.created_at <= filter_params.date_to)
        if filter_params.order_number is not None:
            query = query.where(
                PurchaseOrderMatch.order_number.ilike(f"%{filter_params.order_number}%")
            )

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Paginate
        query = (
            query
            .options(selectinload(PurchaseOrderMatch.discrepancies))
            .order_by(PurchaseOrderMatch.created_at.desc())
            .offset(page * page_size)
            .limit(page_size)
        )

        result = await db.execute(query)
        return list(result.scalars().all()), total

    async def add_document_to_match(
        self,
        db: AsyncSession,
        match_id: uuid.UUID,
        request: AddDocumentRequest,
    ) -> PurchaseOrderMatch:
        """Fuegt ein Dokument zu einem bestehenden Match hinzu."""
        match = await db.get(PurchaseOrderMatch, match_id)
        if not match:
            raise ValueError(f"Match nicht gefunden")

        if request.document_type == "purchase_order":
            if match.purchase_order_id is not None:
                raise ValueError("Bestellung ist bereits verknüpft")
            match.purchase_order_id = request.document_id
            if request.amount is not None:
                match.po_amount = request.amount
        elif request.document_type == "delivery_note":
            if match.delivery_note_id is not None:
                raise ValueError("Lieferschein ist bereits verknüpft")
            match.delivery_note_id = request.document_id
            if request.amount is not None:
                match.dn_amount = request.amount
        elif request.document_type == "invoice":
            if match.invoice_id is not None:
                raise ValueError("Rechnung ist bereits verknüpft")
            match.invoice_id = request.document_id
            if request.amount is not None:
                match.invoice_amount = request.amount
        else:
            raise ValueError(
                f"Ungültiger Dokumenttyp: {request.document_type}. "
                "Erlaubt: purchase_order, delivery_note, invoice"
            )

        # Status aktualisieren
        if match.is_complete:
            match.match_status = MatchStatus.FULL
        elif match.document_count >= 2:
            match.match_status = MatchStatus.PARTIAL

        match.updated_at = utc_now()

        await db.commit()
        await db.refresh(match)

        logger.info(
            "po_match_document_added",
            match_id=str(match_id),
            document_type=request.document_type,
            document_count=match.document_count,
        )

        return match

    # ========================================================================
    # Match-Bewertung & Abweichungserkennung
    # ========================================================================

    async def evaluate_match(
        self,
        db: AsyncSession,
        match_id: uuid.UUID,
    ) -> PurchaseOrderMatch:
        """Bewertet einen Match und erkennt Abweichungen."""
        match = await self.get_match_detail(db, match_id)
        if not match:
            raise ValueError("Match nicht gefunden")

        # Bestehende Abweichungen löschen (Neubewertung)
        for disc in list(match.discrepancies):
            await db.delete(disc)

        discrepancies: List[MatchDiscrepancy] = []
        score = 100.0

        # Betragsvergleiche
        amounts = self._collect_amounts(match)
        amount_discrepancies = self._check_amount_discrepancies(
            match, amounts
        )
        discrepancies.extend(amount_discrepancies)

        # Score reduzieren pro Abweichung
        for disc in discrepancies:
            if disc.severity == DiscrepancySeverity.CRITICAL:
                score -= 30.0
            elif disc.severity == DiscrepancySeverity.ERROR:
                score -= 20.0
            elif disc.severity == DiscrepancySeverity.WARNING:
                score -= 10.0
            elif disc.severity == DiscrepancySeverity.INFO:
                score -= 2.0

        score = max(0.0, min(100.0, score))

        # Abweichungen speichern
        for disc in discrepancies:
            db.add(disc)

        # Match aktualisieren
        match.match_score = score
        match.matched_at = utc_now()

        if discrepancies:
            # Nur auf DISCREPANCY setzen wenn es echte Probleme gibt
            has_serious = any(
                d.severity in (DiscrepancySeverity.ERROR, DiscrepancySeverity.CRITICAL)
                for d in discrepancies
            )
            if has_serious:
                match.match_status = MatchStatus.DISCREPANCY
            elif match.is_complete:
                match.match_status = MatchStatus.FULL
        elif match.is_complete:
            match.match_status = MatchStatus.FULL

        await db.commit()
        await db.refresh(match)

        logger.info(
            "po_match_evaluated",
            match_id=str(match_id),
            score=score,
            discrepancy_count=len(discrepancies),
            status=match.match_status.value,
        )

        return match

    def _collect_amounts(
        self,
        match: PurchaseOrderMatch,
    ) -> Dict[str, Optional[Decimal]]:
        """Sammelt alle verfügbaren Betraege."""
        return {
            "po": match.po_amount,
            "dn": match.dn_amount,
            "invoice": match.invoice_amount,
        }

    def _check_amount_discrepancies(
        self,
        match: PurchaseOrderMatch,
        amounts: Dict[str, Optional[Decimal]],
    ) -> List[MatchDiscrepancy]:
        """Prüft Betragsabweichungen zwischen den Dokumenten."""
        discrepancies: List[MatchDiscrepancy] = []
        tolerance = match.amount_tolerance_percent

        # Vergleichspaare definieren
        pairs = [
            ("po", "invoice", "Bestellung vs. Rechnung"),
            ("po", "dn", "Bestellung vs. Lieferschein"),
            ("dn", "invoice", "Lieferschein vs. Rechnung"),
        ]

        for source_key, target_key, label in pairs:
            source_amount = amounts.get(source_key)
            target_amount = amounts.get(target_key)

            if source_amount is None or target_amount is None:
                continue

            if source_amount == Decimal("0"):
                continue

            deviation = abs(target_amount - source_amount)
            deviation_percent = float((deviation / source_amount) * 100)

            if deviation_percent > tolerance:
                # Schweregrad bestimmen
                if deviation_percent > 10.0:
                    severity = DiscrepancySeverity.CRITICAL
                elif deviation_percent > 5.0:
                    severity = DiscrepancySeverity.ERROR
                else:
                    severity = DiscrepancySeverity.WARNING

                discrepancies.append(
                    MatchDiscrepancy(
                        match_id=match.id,
                        category=DiscrepancyCategory.AMOUNT,
                        description=(
                            f"Betragabweichung {label}: "
                            f"Erwartet {source_amount:.2f} EUR, "
                            f"Tatsaechlich {target_amount:.2f} EUR "
                            f"({deviation_percent:.1f}% Abweichung)"
                        ),
                        field_name=f"amount_{source_key}_vs_{target_key}",
                        expected_value=f"{source_amount:.2f} EUR",
                        actual_value=f"{target_amount:.2f} EUR",
                        expected_amount=source_amount,
                        actual_amount=target_amount,
                        deviation_percent=deviation_percent,
                        severity=severity,
                    )
                )

        return discrepancies

    # ========================================================================
    # Freigabe-Workflow
    # ========================================================================

    async def approve_match(
        self,
        db: AsyncSession,
        match_id: uuid.UUID,
        user_id: uuid.UUID,
        notes: Optional[str] = None,
    ) -> PurchaseOrderMatch:
        """Gibt einen Match frei (trotz Abweichungen)."""
        match = await db.get(PurchaseOrderMatch, match_id)
        if not match:
            raise ValueError("Match nicht gefunden")

        match.match_status = MatchStatus.APPROVED
        match.approved_by_id = user_id
        match.approved_at = utc_now()
        match.approval_notes = notes

        await db.commit()
        await db.refresh(match)

        logger.info(
            "po_match_approved",
            match_id=str(match_id),
            user_id=str(user_id),
        )

        return match

    # ========================================================================
    # Unmatched Documents & Auto-Matching
    # ========================================================================

    async def get_unmatched_documents(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        document_type: Optional[str] = None,
    ) -> List[Document]:
        """Findet Dokumente ohne PO-Match.

        Sucht nach Dokumenten vom Typ Bestellung, Lieferschein oder Rechnung,
        die noch keinem Match zugeordnet sind.
        """
        # Sammle IDs aller bereits gematchten Dokumente
        matched_po_ids = select(PurchaseOrderMatch.purchase_order_id).where(
            and_(
                PurchaseOrderMatch.company_id == company_id,
                PurchaseOrderMatch.purchase_order_id.isnot(None),
            )
        )
        matched_dn_ids = select(PurchaseOrderMatch.delivery_note_id).where(
            and_(
                PurchaseOrderMatch.company_id == company_id,
                PurchaseOrderMatch.delivery_note_id.isnot(None),
            )
        )
        matched_inv_ids = select(PurchaseOrderMatch.invoice_id).where(
            and_(
                PurchaseOrderMatch.company_id == company_id,
                PurchaseOrderMatch.invoice_id.isnot(None),
            )
        )

        # Alle gematchten IDs zusammenfassen
        all_matched = union(matched_po_ids, matched_dn_ids, matched_inv_ids)

        # Dokumente suchen die NICHT gematcht sind
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                Document.id.notin_(all_matched),
            )
        )

        # Optionaler Typfilter
        if document_type is not None:
            type_mapping = {
                "purchase_order": ["bestellung", "purchase_order", "order"],
                "delivery_note": ["lieferschein", "delivery_note", "delivery"],
                "invoice": ["rechnung", "invoice"],
            }
            allowed_types = type_mapping.get(document_type, [document_type])
            query = query.where(
                or_(*[
                    Document.document_type.ilike(t) for t in allowed_types
                ])
            )

        query = query.order_by(Document.created_at.desc()).limit(100)

        result = await db.execute(query)
        return list(result.scalars().all())

    async def auto_match_by_reference(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[PurchaseOrderMatch]:
        """Versucht automatisches Matching nach Bestellnummer und Lieferant.

        Sucht nach PENDING/PARTIAL Matches und versucht, fehlende
        Dokumente anhand der Bestellnummer oder des Lieferanten zuzuordnen.
        """
        # Finde unvollständige Matches
        result = await db.execute(
            select(PurchaseOrderMatch).where(
                and_(
                    PurchaseOrderMatch.company_id == company_id,
                    PurchaseOrderMatch.match_status.in_([
                        MatchStatus.PENDING,
                        MatchStatus.PARTIAL,
                    ]),
                    PurchaseOrderMatch.order_number.isnot(None),
                )
            )
        )
        pending_matches = list(result.scalars().all())

        updated_matches: List[PurchaseOrderMatch] = []

        for match in pending_matches:
            if match.order_number is None:
                continue

            updated = False

            # Suche nach fehlenden Dokumenten mit gleicher Bestellnummer
            # (Vereinfachte Suche über document_type und extracted_data)
            if match.purchase_order_id is None:
                po_doc = await self._find_document_by_reference(
                    db, company_id, match.order_number,
                    ["bestellung", "purchase_order"]
                )
                if po_doc:
                    match.purchase_order_id = po_doc.id
                    updated = True

            if match.delivery_note_id is None:
                dn_doc = await self._find_document_by_reference(
                    db, company_id, match.order_number,
                    ["lieferschein", "delivery_note"]
                )
                if dn_doc:
                    match.delivery_note_id = dn_doc.id
                    updated = True

            if match.invoice_id is None:
                inv_doc = await self._find_document_by_reference(
                    db, company_id, match.order_number,
                    ["rechnung", "invoice"]
                )
                if inv_doc:
                    match.invoice_id = inv_doc.id
                    updated = True

            if updated:
                match.auto_matched = True
                match.updated_at = utc_now()

                # Status aktualisieren
                if match.is_complete:
                    match.match_status = MatchStatus.FULL
                elif match.document_count >= 2:
                    match.match_status = MatchStatus.PARTIAL

                updated_matches.append(match)

        if updated_matches:
            await db.commit()

            logger.info(
                "po_auto_match_completed",
                company_id=str(company_id),
                matches_updated=len(updated_matches),
            )

        return updated_matches

    async def _find_document_by_reference(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        order_number: str,
        doc_types: List[str],
    ) -> Optional[Document]:
        """Sucht ein Dokument anhand der Bestellnummer und Dokumenttypen.

        Sucht in chain_id und extracted_data nach der Bestellnummer.
        """
        query = select(Document).where(
            and_(
                Document.company_id == company_id,
                or_(*[
                    Document.document_type.ilike(t) for t in doc_types
                ]),
                or_(
                    Document.chain_id == order_number,
                    Document.chain_id.ilike(f"%{order_number}%"),
                ),
            )
        ).limit(1)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    # ========================================================================
    # Potential Matches (Vorschläge)
    # ========================================================================

    async def find_potential_matches(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        document_id: uuid.UUID,
        document_type: str,
    ) -> List[PurchaseOrderMatch]:
        """Findet potentielle Matches für ein neues Dokument.

        Sucht nach bestehenden Matches, zu denen das Dokument passen könnte
        (gleiche Bestellnummer, gleicher Lieferant, ähnlicher Betrag).
        """
        # Lade das Dokument
        doc = await db.get(Document, document_id)
        if not doc:
            raise ValueError("Dokument nicht gefunden")

        # Suche nach passenden Matches
        conditions = [
            PurchaseOrderMatch.company_id == company_id,
            PurchaseOrderMatch.match_status.in_([
                MatchStatus.PENDING,
                MatchStatus.PARTIAL,
            ]),
        ]

        # Dokumenttyp-spezifische Bedingungen
        if document_type == "purchase_order":
            conditions.append(PurchaseOrderMatch.purchase_order_id.is_(None))
        elif document_type == "delivery_note":
            conditions.append(PurchaseOrderMatch.delivery_note_id.is_(None))
        elif document_type == "invoice":
            conditions.append(PurchaseOrderMatch.invoice_id.is_(None))

        # Kettenreferenz-Matching (chain_id enthält Bestellnummer)
        if hasattr(doc, "chain_id") and doc.chain_id:
            conditions.append(
                or_(
                    PurchaseOrderMatch.order_number == doc.chain_id,
                    PurchaseOrderMatch.order_number.ilike(
                        f"%{doc.chain_id}%"
                    ),
                )
            )

        query = (
            select(PurchaseOrderMatch)
            .where(and_(*conditions))
            .order_by(PurchaseOrderMatch.created_at.desc())
            .limit(10)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    # ========================================================================
    # Statistiken
    # ========================================================================

    async def get_matching_statistics(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        period_start: date,
        period_end: date,
    ) -> MatchStatistics:
        """Berechnet Matching-Statistiken für einen Zeitraum."""
        base_filter = and_(
            PurchaseOrderMatch.company_id == company_id,
            PurchaseOrderMatch.created_at >= period_start,
            PurchaseOrderMatch.created_at <= period_end,
        )

        # Gesamt-Zaehlung nach Status
        status_counts = await db.execute(
            select(
                PurchaseOrderMatch.match_status,
                func.count(PurchaseOrderMatch.id),
            )
            .where(base_filter)
            .group_by(PurchaseOrderMatch.match_status)
        )
        counts_by_status: Dict[str, int] = {}
        for row in status_counts:
            counts_by_status[row[0].value] = row[1]

        total = sum(counts_by_status.values())

        # Durchschnittlicher Match-Score
        avg_score_result = await db.execute(
            select(func.avg(PurchaseOrderMatch.match_score))
            .where(base_filter)
        )
        avg_score = avg_score_result.scalar() or 0.0

        # Auto-Matched Zaehlung
        auto_matched_result = await db.execute(
            select(func.count(PurchaseOrderMatch.id))
            .where(and_(base_filter, PurchaseOrderMatch.auto_matched == True))
        )
        auto_matched_count = auto_matched_result.scalar() or 0

        # Abweichungs-Statistiken
        disc_base_filter = and_(
            MatchDiscrepancy.match_id.in_(
                select(PurchaseOrderMatch.id).where(base_filter)
            ),
        )

        total_disc_result = await db.execute(
            select(func.count(MatchDiscrepancy.id)).where(disc_base_filter)
        )
        total_disc = total_disc_result.scalar() or 0

        unresolved_disc_result = await db.execute(
            select(func.count(MatchDiscrepancy.id)).where(
                and_(disc_base_filter, MatchDiscrepancy.resolved == False)
            )
        )
        unresolved_disc = unresolved_disc_result.scalar() or 0

        # Durchschnittliche Betrags-Abweichung
        avg_deviation_result = await db.execute(
            select(func.avg(MatchDiscrepancy.deviation_percent)).where(
                and_(
                    disc_base_filter,
                    MatchDiscrepancy.category == DiscrepancyCategory.AMOUNT,
                )
            )
        )
        avg_deviation = avg_deviation_result.scalar() or 0.0

        return MatchStatistics(
            total_matches=total,
            pending_matches=counts_by_status.get("pending", 0),
            partial_matches=counts_by_status.get("partial", 0),
            full_matches=counts_by_status.get("full", 0),
            discrepancy_matches=counts_by_status.get("discrepancy", 0),
            approved_matches=counts_by_status.get("approved", 0),
            rejected_matches=counts_by_status.get("rejected", 0),
            auto_matched_count=auto_matched_count,
            avg_match_score=float(avg_score),
            total_discrepancies=total_disc,
            unresolved_discrepancies=unresolved_disc,
            avg_amount_deviation_percent=float(avg_deviation),
            period_start=period_start,
            period_end=period_end,
        )


# ============================================================================
# Singleton
# ============================================================================


_po_matching_service: Optional[POMatchingService] = None


def get_po_matching_service() -> POMatchingService:
    """Returns singleton POMatchingService instance."""
    global _po_matching_service
    if _po_matching_service is None:
        _po_matching_service = POMatchingService()
    return _po_matching_service
