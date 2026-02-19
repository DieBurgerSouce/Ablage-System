# -*- coding: utf-8 -*-
"""
3-Way Matching Service - Bestellung <-> Lieferschein <-> Rechnung.

Intelligentes Matching für den Purchase-to-Pay Prozess:
- Bestellnummern-basiertes Matching (95% Confidence)
- Lieferanten + Betrags-Matching (85% Confidence)
- Lieferanten + Datums-Matching (70% Confidence)
- Automatische Abweichungserkennung mit konfigurierbaren Toleranzen
- Auto-Freigabe bei Score >= 95

Feature-Phase: 2.2 (Februar 2026)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Document, BusinessEntity, InvoiceTracking
from app.db.models_po_matching import (
    PurchaseOrderMatch,
    MatchDiscrepancy,
    MatchStatus,
    DiscrepancyCategory,
    DiscrepancySeverity,
)
from app.core.security.sensitive_data_filter import get_pii_safe_logger
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = get_pii_safe_logger(__name__)


# =============================================================================
# Prometheus Metriken
# =============================================================================

MATCHING_ATTEMPTS = Counter(
    "three_way_matching_attempts_total",
    "Match-Versuche",
    ["result", "strategy"],
)

MATCHING_SCORE = Histogram(
    "three_way_matching_score",
    "Match-Score Verteilung",
    buckets=[0, 20, 40, 60, 80, 90, 95, 100],
)

MATCHING_DISCREPANCIES = Counter(
    "three_way_matching_discrepancies_total",
    "Abweichungen",
    ["category", "severity"],
)


# =============================================================================
# DTOs
# =============================================================================


@dataclass
class DiscrepancyInfo:
    """Informationen zu einer erkannten Abweichung."""

    category: str
    description: str
    field_name: str
    expected_value: str
    actual_value: str
    deviation_percent: Optional[float]
    severity: str


@dataclass
class MatchCandidate:
    """Ein potentieller Match-Partner."""

    document_id: UUID
    document_type: str           # "purchase_order", "delivery_note", "invoice"
    reference_number: Optional[str]
    amount: Optional[Decimal]
    vendor_name: Optional[str]
    vendor_entity_id: Optional[UUID]
    match_confidence: float      # 0.0 - 1.0
    match_reason: str            # Deutscher Erklärungstext
    existing_match_id: Optional[UUID] = None


@dataclass
class ThreeWayMatchResult:
    """Ergebnis eines 3-Way Match-Versuchs."""

    success: bool
    match_id: Optional[UUID]
    match_status: MatchStatus
    match_score: float           # 0-100
    documents_matched: int       # 1, 2 oder 3
    discrepancies: List[DiscrepancyInfo] = field(default_factory=list)
    auto_approved: bool = False
    explanation: str = ""
    error: Optional[str] = None


# =============================================================================
# Hilfs-Konstanten
# =============================================================================

# Erlaubte document_type-Werte
VALID_DOCUMENT_TYPES: Tuple[str, ...] = (
    "purchase_order",
    "delivery_note",
    "invoice",
)

# Mapping document_type -> PurchaseOrderMatch Spaltenname
_COLUMN_FOR_TYPE: Dict[str, str] = {
    "purchase_order": "purchase_order_id",
    "delivery_note": "delivery_note_id",
    "invoice": "invoice_id",
}

# Mapping document_type -> Betragsspalte
_AMOUNT_COL_FOR_TYPE: Dict[str, str] = {
    "purchase_order": "po_amount",
    "delivery_note": "dn_amount",
    "invoice": "invoice_amount",
}


# =============================================================================
# ThreeWayMatchingService
# =============================================================================


class ThreeWayMatchingService:
    """Intelligentes 3-Way Matching: Bestellung <-> Lieferschein <-> Rechnung.

    Baut Match-Datensätze schrittweise auf, wenn Dokumente eintreffen.
    Erkennt automatisch Abweichungen und prüft konfigurierbare Toleranzen.

    Matching-Strategie (Priorität):
        1. Bestellnummer-Match        (Confidence 0.95)
        2. Lieferant + Betrag         (Confidence 0.85)
        3. Lieferant + Datumsfenster  (Confidence 0.70)
    """

    DEFAULT_AMOUNT_TOLERANCE: float = 2.0      # 2% Betragstoleranz
    DEFAULT_QUANTITY_TOLERANCE: float = 1.0    # 1% Mengentoleranz
    AUTO_APPROVE_SCORE: float = 95.0           # Auto-Freigabe ab diesem Score
    VENDOR_AMOUNT_WINDOW_DAYS: int = 90        # Suchfenster Lieferant+Betrag
    VENDOR_DATE_WINDOW_DAYS: int = 30          # Datumsfenster Lieferant+Datum
    VENDOR_DATE_AMOUNT_TOLERANCE_PCT: float = 10.0  # Toleranz für Strategie 3

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -------------------------------------------------------------------------
    # Öffentliche API
    # -------------------------------------------------------------------------

    async def match_document(
        self,
        document_id: UUID,
        company_id: UUID,
        document_type: str,
        reference_number: Optional[str] = None,
        amount: Optional[Decimal] = None,
        vendor_entity_id: Optional[UUID] = None,
        vendor_name: Optional[str] = None,
        extracted_fields: Optional[Dict[str, Dict[str, object]]] = None,
    ) -> ThreeWayMatchResult:
        """Haupteinsteigspunkt: Versucht, ein eingehendes Dokument zu matchen.

        Args:
            document_id: ID des zu matchenden Dokuments.
            company_id: Mandanten-ID (Multi-Tenant-Pflicht).
            document_type: Art des Dokuments (purchase_order, delivery_note, invoice).
            reference_number: Bestellnummer oder Referenznummer.
            amount: Brutto-Betrag aus OCR.
            vendor_entity_id: Verknüpfte BusinessEntity-ID.
            vendor_name: Lieferantenname aus OCR (Fallback wenn keine Entity).
            extracted_fields: Rohe OCR-Felder aus document_metadata.

        Returns:
            ThreeWayMatchResult mit Status, Score und Abweichungen.
        """
        if document_type not in VALID_DOCUMENT_TYPES:
            return ThreeWayMatchResult(
                success=False,
                match_id=None,
                match_status=MatchStatus.PENDING,
                match_score=0.0,
                documents_matched=0,
                error=f"Unbekannter Dokumenttyp: {document_type}. "
                      f"Erlaubt: {', '.join(VALID_DOCUMENT_TYPES)}",
            )

        try:
            # Extrahiere Bestellnummer aus extracted_fields falls nicht direkt übergeben
            if reference_number is None and extracted_fields:
                reference_number = self._extract_reference_from_fields(extracted_fields)

            # Suche passende Kandidaten
            candidates = await self.find_match_candidates(
                company_id=company_id,
                document_type=document_type,
                reference_number=reference_number,
                amount=amount,
                vendor_entity_id=vendor_entity_id,
            )

            if not candidates:
                # Kein Match-Partner gefunden -> neuen Match anlegen
                result = await self._create_new_match(
                    document_id=document_id,
                    company_id=company_id,
                    document_type=document_type,
                    reference_number=reference_number,
                    amount=amount,
                    vendor_entity_id=vendor_entity_id,
                    vendor_name=vendor_name,
                )
                MATCHING_ATTEMPTS.labels(result="new_match", strategy="none").inc()
                return result

            # Besten Kandidaten wählen (höchste Confidence)
            best = max(candidates, key=lambda c: c.match_confidence)
            strategy = self._detect_strategy_from_confidence(best.match_confidence)

            result = await self._add_document_to_match(
                candidate=best,
                document_id=document_id,
                company_id=company_id,
                document_type=document_type,
                reference_number=reference_number,
                amount=amount,
                vendor_entity_id=vendor_entity_id,
                vendor_name=vendor_name,
            )

            MATCHING_ATTEMPTS.labels(
                result="matched" if result.success else "error",
                strategy=strategy,
            ).inc()
            if result.success:
                MATCHING_SCORE.observe(result.match_score)

            return result

        except Exception as exc:
            logger.error(
                "match_document_fehlgeschlagen",
                document_type=document_type,
                **safe_error_log(exc, context="3-Way Matching"),
            )
            return ThreeWayMatchResult(
                success=False,
                match_id=None,
                match_status=MatchStatus.PENDING,
                match_score=0.0,
                documents_matched=0,
                error=safe_error_detail(exc, "Matching"),
            )

    async def find_match_candidates(
        self,
        company_id: UUID,
        document_type: str,
        reference_number: Optional[str],
        amount: Optional[Decimal],
        vendor_entity_id: Optional[UUID],
    ) -> List[MatchCandidate]:
        """Findet potentielle Match-Partner für ein Dokument.

        Suche erfolgt in drei Strategien (absteigend nach Confidence):
        1. Bestellnummer-Match      -> confidence 0.95
        2. Lieferant + Betrag       -> confidence 0.85
        3. Lieferant + Datumsfenster -> confidence 0.70

        Args:
            company_id: Mandanten-ID.
            document_type: Art des Dokuments.
            reference_number: Bestellnummer/Referenznummer.
            amount: Betrag für Betrags-Matching.
            vendor_entity_id: Lieferanten-Entity-ID.

        Returns:
            Sortierte Liste von MatchCandidate (bester zuerst).
        """
        # Spaltenname des bereits im Match gespeicherten Dokuments ermitteln:
        # Wir suchen Matches, in denen DIESER Dokumenttyp noch NICHT belegt ist.
        slot_column = _COLUMN_FOR_TYPE[document_type]
        candidates: List[MatchCandidate] = []

        # ----- Strategie 1: Bestellnummer -----
        if reference_number:
            order_candidates = await self._find_by_order_number(
                company_id=company_id,
                reference_number=reference_number,
                slot_column=slot_column,
            )
            candidates.extend(order_candidates)

        # ----- Strategie 2: Lieferant + Betrag -----
        if vendor_entity_id and amount:
            vendor_amount_candidates = await self._find_by_vendor_and_amount(
                company_id=company_id,
                vendor_entity_id=vendor_entity_id,
                amount=amount,
                slot_column=slot_column,
                exclude_ids=[c.existing_match_id for c in candidates if c.existing_match_id],
            )
            candidates.extend(vendor_amount_candidates)

        # ----- Strategie 3: Lieferant + Datumsfenster -----
        if vendor_entity_id and amount:
            vendor_date_candidates = await self._find_by_vendor_and_date(
                company_id=company_id,
                vendor_entity_id=vendor_entity_id,
                amount=amount,
                slot_column=slot_column,
                exclude_ids=[c.existing_match_id for c in candidates if c.existing_match_id],
            )
            candidates.extend(vendor_date_candidates)

        # Deduplizieren (falls Kandidat in mehreren Strategien auftaucht, höchste Confidence behalten)
        seen_ids: Dict[UUID, MatchCandidate] = {}
        for cand in candidates:
            if cand.existing_match_id is None:
                continue
            if cand.existing_match_id not in seen_ids:
                seen_ids[cand.existing_match_id] = cand
            elif cand.match_confidence > seen_ids[cand.existing_match_id].match_confidence:
                seen_ids[cand.existing_match_id] = cand

        return sorted(seen_ids.values(), key=lambda c: c.match_confidence, reverse=True)

    async def get_match_status(
        self,
        match_id: UUID,
        company_id: UUID,
    ) -> Optional[ThreeWayMatchResult]:
        """Gibt den aktuellen Status eines Matches zurück.

        Args:
            match_id: PurchaseOrderMatch-ID.
            company_id: Mandanten-ID.

        Returns:
            ThreeWayMatchResult oder None falls nicht gefunden.
        """
        stmt = (
            select(PurchaseOrderMatch)
            .where(
                and_(
                    PurchaseOrderMatch.id == match_id,
                    PurchaseOrderMatch.company_id == company_id,
                )
            )
            .options(selectinload(PurchaseOrderMatch.discrepancies))
        )
        result = await self.db.execute(stmt)
        match = result.scalar_one_or_none()

        if match is None:
            return None

        discrepancy_infos = [
            self._discrepancy_to_info(d)
            for d in match.discrepancies
        ]

        return ThreeWayMatchResult(
            success=True,
            match_id=match.id,
            match_status=match.match_status,
            match_score=match.match_score or 0.0,
            documents_matched=match.document_count,
            discrepancies=discrepancy_infos,
            auto_approved=match.auto_matched,
            explanation=self._build_status_explanation(match),
        )

    async def approve_match(
        self,
        match_id: UUID,
        company_id: UUID,
        user_id: UUID,
        notes: Optional[str] = None,
    ) -> ThreeWayMatchResult:
        """Gibt einen Match manuell frei (auch bei Abweichungen).

        Args:
            match_id: PurchaseOrderMatch-ID.
            company_id: Mandanten-ID.
            user_id: Freigebender Benutzer.
            notes: Optionale Freigabe-Notiz.

        Returns:
            Aktualisierter ThreeWayMatchResult.
        """
        try:
            stmt = (
                select(PurchaseOrderMatch)
                .where(
                    and_(
                        PurchaseOrderMatch.id == match_id,
                        PurchaseOrderMatch.company_id == company_id,
                    )
                )
                .options(selectinload(PurchaseOrderMatch.discrepancies))
            )
            result = await self.db.execute(stmt)
            match = result.scalar_one_or_none()

            if match is None:
                return ThreeWayMatchResult(
                    success=False,
                    match_id=None,
                    match_status=MatchStatus.PENDING,
                    match_score=0.0,
                    documents_matched=0,
                    error="Match nicht gefunden",
                )

            if match.match_status in (MatchStatus.REJECTED,):
                return ThreeWayMatchResult(
                    success=False,
                    match_id=match.id,
                    match_status=match.match_status,
                    match_score=match.match_score or 0.0,
                    documents_matched=match.document_count,
                    error="Abgelehnter Match kann nicht freigegeben werden",
                )

            match.match_status = MatchStatus.APPROVED
            match.approved_by_id = user_id
            match.approved_at = datetime.now(timezone.utc)
            match.approval_notes = notes
            await self.db.commit()
            await self.db.refresh(match)

            logger.info(
                "match_freigegeben",
                match_id=str(match_id),
                company_id=str(company_id),
            )

            return ThreeWayMatchResult(
                success=True,
                match_id=match.id,
                match_status=MatchStatus.APPROVED,
                match_score=match.match_score or 0.0,
                documents_matched=match.document_count,
                discrepancies=[self._discrepancy_to_info(d) for d in match.discrepancies],
                explanation="Match wurde manuell freigegeben.",
            )

        except Exception as exc:
            await self.db.rollback()
            logger.error(
                "approve_match_fehlgeschlagen",
                match_id=str(match_id),
                **safe_error_log(exc, context="Match-Freigabe"),
            )
            return ThreeWayMatchResult(
                success=False,
                match_id=match_id,
                match_status=MatchStatus.PENDING,
                match_score=0.0,
                documents_matched=0,
                error=safe_error_detail(exc, "Freigabe"),
            )

    async def reject_match(
        self,
        match_id: UUID,
        company_id: UUID,
        user_id: UUID,
        reason: str,
    ) -> ThreeWayMatchResult:
        """Lehnt einen Match manuell ab.

        Args:
            match_id: PurchaseOrderMatch-ID.
            company_id: Mandanten-ID.
            user_id: Ablehnender Benutzer.
            reason: Pflichtfeld: Ablehnungsgrund (Deutsch).

        Returns:
            Aktualisierter ThreeWayMatchResult.
        """
        try:
            stmt = (
                select(PurchaseOrderMatch)
                .where(
                    and_(
                        PurchaseOrderMatch.id == match_id,
                        PurchaseOrderMatch.company_id == company_id,
                    )
                )
            )
            result = await self.db.execute(stmt)
            match = result.scalar_one_or_none()

            if match is None:
                return ThreeWayMatchResult(
                    success=False,
                    match_id=None,
                    match_status=MatchStatus.PENDING,
                    match_score=0.0,
                    documents_matched=0,
                    error="Match nicht gefunden",
                )

            match.match_status = MatchStatus.REJECTED
            match.approved_by_id = user_id
            match.approved_at = datetime.now(timezone.utc)
            match.approval_notes = reason
            await self.db.commit()
            await self.db.refresh(match)

            logger.info(
                "match_abgelehnt",
                match_id=str(match_id),
                company_id=str(company_id),
            )

            return ThreeWayMatchResult(
                success=True,
                match_id=match.id,
                match_status=MatchStatus.REJECTED,
                match_score=match.match_score or 0.0,
                documents_matched=match.document_count,
                explanation=f"Match wurde abgelehnt: {reason}",
            )

        except Exception as exc:
            await self.db.rollback()
            logger.error(
                "reject_match_fehlgeschlagen",
                match_id=str(match_id),
                **safe_error_log(exc, context="Match-Ablehnung"),
            )
            return ThreeWayMatchResult(
                success=False,
                match_id=match_id,
                match_status=MatchStatus.PENDING,
                match_score=0.0,
                documents_matched=0,
                error=safe_error_detail(exc, "Ablehnung"),
            )

    async def get_unmatched_documents(
        self,
        company_id: UUID,
        document_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, object]]:
        """Gibt Dokumente zurück, die noch nicht gematcht wurden.

        Sucht nach PurchaseOrderMatch-Einträgen im Status PENDING oder
        Documents ohne zugehörigen Match-Eintrag für den jeweiligen Typ.

        Args:
            company_id: Mandanten-ID.
            document_type: Optional: Filtern nach Dokumenttyp.
            limit: Maximale Trefferanzahl.

        Returns:
            Liste von Dictionaries mit Dokumentinformationen.
        """
        try:
            conditions = [
                PurchaseOrderMatch.company_id == company_id,
                PurchaseOrderMatch.match_status == MatchStatus.PENDING,
            ]

            if document_type == "purchase_order":
                conditions.append(PurchaseOrderMatch.purchase_order_id.isnot(None))
                conditions.append(PurchaseOrderMatch.delivery_note_id.is_(None))
                conditions.append(PurchaseOrderMatch.invoice_id.is_(None))
            elif document_type == "delivery_note":
                conditions.append(PurchaseOrderMatch.delivery_note_id.isnot(None))
                conditions.append(PurchaseOrderMatch.purchase_order_id.is_(None))
                conditions.append(PurchaseOrderMatch.invoice_id.is_(None))
            elif document_type == "invoice":
                conditions.append(PurchaseOrderMatch.invoice_id.isnot(None))
                conditions.append(PurchaseOrderMatch.purchase_order_id.is_(None))
                conditions.append(PurchaseOrderMatch.delivery_note_id.is_(None))

            stmt = (
                select(PurchaseOrderMatch)
                .where(and_(*conditions))
                .order_by(PurchaseOrderMatch.created_at.asc())
                .limit(limit)
            )
            result = await self.db.execute(stmt)
            matches = result.scalars().all()

            output: List[Dict[str, object]] = []
            for m in matches:
                doc_type_found: Optional[str] = None
                doc_id: Optional[UUID] = None
                if m.purchase_order_id:
                    doc_type_found = "purchase_order"
                    doc_id = m.purchase_order_id
                elif m.delivery_note_id:
                    doc_type_found = "delivery_note"
                    doc_id = m.delivery_note_id
                elif m.invoice_id:
                    doc_type_found = "invoice"
                    doc_id = m.invoice_id

                output.append({
                    "match_id": str(m.id),
                    "document_id": str(doc_id) if doc_id else None,
                    "document_type": doc_type_found,
                    "order_number": m.order_number,
                    "vendor_name": m.vendor_name,
                    "amount": float(m.po_amount or m.dn_amount or m.invoice_amount or 0),
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "match_status": m.match_status.value,
                })

            return output

        except Exception as exc:
            logger.error(
                "get_unmatched_fehlgeschlagen",
                company_id=str(company_id),
                **safe_error_log(exc, context="Ungematcht-Abfrage"),
            )
            return []

    # -------------------------------------------------------------------------
    # Interne Hilfsmethoden: Matching-Strategien
    # -------------------------------------------------------------------------

    async def _find_by_order_number(
        self,
        company_id: UUID,
        reference_number: str,
        slot_column: str,
    ) -> List[MatchCandidate]:
        """Strategie 1: Suche nach übereinstimmender Bestellnummer."""
        slot_filter = getattr(PurchaseOrderMatch, slot_column).is_(None)
        stmt = (
            select(PurchaseOrderMatch)
            .where(
                and_(
                    PurchaseOrderMatch.company_id == company_id,
                    PurchaseOrderMatch.order_number == reference_number,
                    PurchaseOrderMatch.match_status.notin_([
                        MatchStatus.REJECTED,
                        MatchStatus.APPROVED,
                    ]),
                    slot_filter,
                )
            )
            .limit(5)
        )
        result = await self.db.execute(stmt)
        matches = result.scalars().all()

        candidates: List[MatchCandidate] = []
        for m in matches:
            existing_doc_id, existing_doc_type = self._get_first_existing_doc(m)
            candidates.append(
                MatchCandidate(
                    document_id=existing_doc_id or m.id,
                    document_type=existing_doc_type or "purchase_order",
                    reference_number=m.order_number,
                    amount=self._get_primary_amount(m),
                    vendor_name=m.vendor_name,
                    vendor_entity_id=m.vendor_entity_id,
                    match_confidence=0.95,
                    match_reason=(
                        f"Bestellnummer '{reference_number}' stimmt überein"
                    ),
                    existing_match_id=m.id,
                )
            )
        return candidates

    async def _find_by_vendor_and_amount(
        self,
        company_id: UUID,
        vendor_entity_id: UUID,
        amount: Decimal,
        slot_column: str,
        exclude_ids: List[Optional[UUID]],
    ) -> List[MatchCandidate]:
        """Strategie 2: Suche nach Lieferant + Betrag (±2%)."""
        tolerance = self.DEFAULT_AMOUNT_TOLERANCE / 100.0
        amount_min = amount * Decimal(str(1.0 - tolerance))
        amount_max = amount * Decimal(str(1.0 + tolerance))
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.VENDOR_AMOUNT_WINDOW_DAYS)
        slot_filter = getattr(PurchaseOrderMatch, slot_column).is_(None)

        # Alle Betragsspalten prüfen (Bestellung, Lieferschein oder Rechnung)
        amount_filter = or_(
            and_(
                PurchaseOrderMatch.po_amount >= amount_min,
                PurchaseOrderMatch.po_amount <= amount_max,
            ),
            and_(
                PurchaseOrderMatch.dn_amount >= amount_min,
                PurchaseOrderMatch.dn_amount <= amount_max,
            ),
            and_(
                PurchaseOrderMatch.invoice_amount >= amount_min,
                PurchaseOrderMatch.invoice_amount <= amount_max,
            ),
        )

        filters = [
            PurchaseOrderMatch.company_id == company_id,
            PurchaseOrderMatch.vendor_entity_id == vendor_entity_id,
            amount_filter,
            PurchaseOrderMatch.created_at >= cutoff,
            PurchaseOrderMatch.match_status.notin_([
                MatchStatus.REJECTED,
                MatchStatus.APPROVED,
            ]),
            slot_filter,
        ]
        non_none_excludes = [eid for eid in exclude_ids if eid is not None]
        if non_none_excludes:
            filters.append(PurchaseOrderMatch.id.notin_(non_none_excludes))

        stmt = (
            select(PurchaseOrderMatch)
            .where(and_(*filters))
            .order_by(PurchaseOrderMatch.created_at.desc())
            .limit(5)
        )
        result = await self.db.execute(stmt)
        matches = result.scalars().all()

        candidates: List[MatchCandidate] = []
        for m in matches:
            existing_doc_id, existing_doc_type = self._get_first_existing_doc(m)
            candidates.append(
                MatchCandidate(
                    document_id=existing_doc_id or m.id,
                    document_type=existing_doc_type or "purchase_order",
                    reference_number=m.order_number,
                    amount=self._get_primary_amount(m),
                    vendor_name=m.vendor_name,
                    vendor_entity_id=m.vendor_entity_id,
                    match_confidence=0.85,
                    match_reason="Lieferant und Betrag stimmen überein (±2%)",
                    existing_match_id=m.id,
                )
            )
        return candidates

    async def _find_by_vendor_and_date(
        self,
        company_id: UUID,
        vendor_entity_id: UUID,
        amount: Decimal,
        slot_column: str,
        exclude_ids: List[Optional[UUID]],
    ) -> List[MatchCandidate]:
        """Strategie 3: Suche nach Lieferant + Datumsfenster (±30 Tage, ±10% Betrag)."""
        tolerance = self.VENDOR_DATE_AMOUNT_TOLERANCE_PCT / 100.0
        amount_min = amount * Decimal(str(1.0 - tolerance))
        amount_max = amount * Decimal(str(1.0 + tolerance))
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.VENDOR_DATE_WINDOW_DAYS)
        slot_filter = getattr(PurchaseOrderMatch, slot_column).is_(None)

        amount_filter = or_(
            and_(
                PurchaseOrderMatch.po_amount >= amount_min,
                PurchaseOrderMatch.po_amount <= amount_max,
            ),
            and_(
                PurchaseOrderMatch.dn_amount >= amount_min,
                PurchaseOrderMatch.dn_amount <= amount_max,
            ),
            and_(
                PurchaseOrderMatch.invoice_amount >= amount_min,
                PurchaseOrderMatch.invoice_amount <= amount_max,
            ),
        )

        filters = [
            PurchaseOrderMatch.company_id == company_id,
            PurchaseOrderMatch.vendor_entity_id == vendor_entity_id,
            amount_filter,
            PurchaseOrderMatch.created_at >= cutoff,
            PurchaseOrderMatch.match_status.notin_([
                MatchStatus.REJECTED,
                MatchStatus.APPROVED,
            ]),
            slot_filter,
        ]
        non_none_excludes = [eid for eid in exclude_ids if eid is not None]
        if non_none_excludes:
            filters.append(PurchaseOrderMatch.id.notin_(non_none_excludes))

        stmt = (
            select(PurchaseOrderMatch)
            .where(and_(*filters))
            .order_by(PurchaseOrderMatch.created_at.desc())
            .limit(5)
        )
        result = await self.db.execute(stmt)
        matches = result.scalars().all()

        candidates: List[MatchCandidate] = []
        for m in matches:
            existing_doc_id, existing_doc_type = self._get_first_existing_doc(m)
            candidates.append(
                MatchCandidate(
                    document_id=existing_doc_id or m.id,
                    document_type=existing_doc_type or "purchase_order",
                    reference_number=m.order_number,
                    amount=self._get_primary_amount(m),
                    vendor_name=m.vendor_name,
                    vendor_entity_id=m.vendor_entity_id,
                    match_confidence=0.70,
                    match_reason=(
                        f"Lieferant stimmt überein, Betrag innerhalb "
                        f"{self.VENDOR_DATE_AMOUNT_TOLERANCE_PCT}% Toleranz "
                        f"(letzte {self.VENDOR_DATE_WINDOW_DAYS} Tage)"
                    ),
                    existing_match_id=m.id,
                )
            )
        return candidates

    # -------------------------------------------------------------------------
    # Interne Hilfsmethoden: Match-Erstellung und -Aktualisierung
    # -------------------------------------------------------------------------

    async def _create_new_match(
        self,
        document_id: UUID,
        company_id: UUID,
        document_type: str,
        reference_number: Optional[str],
        amount: Optional[Decimal],
        vendor_entity_id: Optional[UUID],
        vendor_name: Optional[str],
    ) -> ThreeWayMatchResult:
        """Legt einen neuen PurchaseOrderMatch an (1. Dokument einer Kette)."""
        slot_column = _COLUMN_FOR_TYPE[document_type]
        amount_column = _AMOUNT_COL_FOR_TYPE[document_type]

        match_kwargs: Dict[str, object] = {
            "id": uuid4(),
            "company_id": company_id,
            "match_status": MatchStatus.PENDING,
            "match_score": 0.0,
            "auto_matched": False,
            "amount_tolerance_percent": self.DEFAULT_AMOUNT_TOLERANCE,
            "quantity_tolerance_percent": self.DEFAULT_QUANTITY_TOLERANCE,
            slot_column: document_id,
            amount_column: amount,
        }
        if reference_number:
            match_kwargs["order_number"] = reference_number
        if vendor_entity_id:
            match_kwargs["vendor_entity_id"] = vendor_entity_id
        if vendor_name:
            match_kwargs["vendor_name"] = vendor_name

        new_match = PurchaseOrderMatch(**match_kwargs)
        self.db.add(new_match)
        await self.db.commit()
        await self.db.refresh(new_match)

        logger.info(
            "neuer_match_erstellt",
            match_id=str(new_match.id),
            document_type=document_type,
            company_id=str(company_id),
        )

        return ThreeWayMatchResult(
            success=True,
            match_id=new_match.id,
            match_status=MatchStatus.PENDING,
            match_score=0.0,
            documents_matched=1,
            explanation=(
                f"Neuer Match-Eintrag erstellt. "
                f"Warte auf weitere Dokumente "
                f"({'Bestellung, Lieferschein' if document_type == 'invoice' else 'Lieferschein, Rechnung'})."
            ),
        )

    async def _add_document_to_match(
        self,
        candidate: MatchCandidate,
        document_id: UUID,
        company_id: UUID,
        document_type: str,
        reference_number: Optional[str],
        amount: Optional[Decimal],
        vendor_entity_id: Optional[UUID],
        vendor_name: Optional[str],
    ) -> ThreeWayMatchResult:
        """Fügt ein Dokument zu einem bestehenden Match hinzu und berechnet Score."""
        assert candidate.existing_match_id is not None

        stmt = (
            select(PurchaseOrderMatch)
            .where(
                and_(
                    PurchaseOrderMatch.id == candidate.existing_match_id,
                    PurchaseOrderMatch.company_id == company_id,
                )
            )
            .options(selectinload(PurchaseOrderMatch.discrepancies))
        )
        result = await self.db.execute(stmt)
        match = result.scalar_one_or_none()

        if match is None:
            return ThreeWayMatchResult(
                success=False,
                match_id=None,
                match_status=MatchStatus.PENDING,
                match_score=0.0,
                documents_matched=0,
                error="Match-Eintrag nicht mehr vorhanden (ggf. gelöscht)",
            )

        # Slot befüllen
        slot_column = _COLUMN_FOR_TYPE[document_type]
        amount_column = _AMOUNT_COL_FOR_TYPE[document_type]
        setattr(match, slot_column, document_id)
        if amount is not None:
            setattr(match, amount_column, amount)
        if vendor_entity_id and not match.vendor_entity_id:
            match.vendor_entity_id = vendor_entity_id
        if vendor_name and not match.vendor_name:
            match.vendor_name = vendor_name
        if reference_number and not match.order_number:
            match.order_number = reference_number

        # Abweichungen prüfen
        new_discrepancies = self._detect_discrepancies(match, document_type, amount)

        # Bestehende ungelöste Abweichungen löschen und neu berechnen
        for d in list(match.discrepancies):
            if not d.resolved:
                await self.db.delete(d)

        for disc_info in new_discrepancies:
            disc = MatchDiscrepancy(
                id=uuid4(),
                match_id=match.id,
                category=DiscrepancyCategory(disc_info.category),
                description=disc_info.description,
                field_name=disc_info.field_name,
                expected_value=disc_info.expected_value,
                actual_value=disc_info.actual_value,
                deviation_percent=disc_info.deviation_percent,
                severity=DiscrepancySeverity(disc_info.severity),
            )
            self.db.add(disc)

        # Score berechnen
        match_score = self._calculate_score(
            confidence=candidate.match_confidence,
            discrepancies=new_discrepancies,
            document_count=match.document_count + 1,  # +1 für das neue Dokument
        )
        match.match_score = match_score

        # Status aktualisieren
        new_status = self._determine_status(
            match=match,
            discrepancies=new_discrepancies,
            score=match_score,
        )
        match.match_status = new_status

        # Auto-Matched Marker
        auto_approved = False
        if match_score >= self.AUTO_APPROVE_SCORE and not new_discrepancies:
            match.auto_matched = True
            match.matched_at = datetime.now(timezone.utc)
            auto_approved = True

        await self.db.commit()
        await self.db.refresh(match)

        # Prometheus
        for disc_info in new_discrepancies:
            MATCHING_DISCREPANCIES.labels(
                category=disc_info.category,
                severity=disc_info.severity,
            ).inc()

        doc_count = match.document_count
        explanation = self._build_match_explanation(
            candidate=candidate,
            doc_count=doc_count,
            score=match_score,
            discrepancies=new_discrepancies,
            auto_approved=auto_approved,
        )

        logger.info(
            "match_aktualisiert",
            match_id=str(match.id),
            document_type=document_type,
            doc_count=doc_count,
            status=new_status.value,
            score=match_score,
            company_id=str(company_id),
        )

        return ThreeWayMatchResult(
            success=True,
            match_id=match.id,
            match_status=new_status,
            match_score=match_score,
            documents_matched=doc_count,
            discrepancies=new_discrepancies,
            auto_approved=auto_approved,
            explanation=explanation,
        )

    # -------------------------------------------------------------------------
    # Abweichungserkennung
    # -------------------------------------------------------------------------

    def _detect_discrepancies(
        self,
        match: PurchaseOrderMatch,
        incoming_type: str,
        incoming_amount: Optional[Decimal],
    ) -> List[DiscrepancyInfo]:
        """Erkennt Abweichungen zwischen den Match-Dokumenten.

        Vergleicht Beträge und Datumsreihenfolge sobald mindestens 2 Dokumente
        im Match vorhanden sind (inkl. das neu hinzukommende).

        Args:
            match: Bestehender PurchaseOrderMatch (noch ohne das neue Dokument).
            incoming_type: Typ des neu hinzukommenden Dokuments.
            incoming_amount: Betrag des neuen Dokuments.

        Returns:
            Liste erkannter Abweichungen als DiscrepancyInfo.
        """
        discrepancies: List[DiscrepancyInfo] = []
        tolerance = (match.amount_tolerance_percent or self.DEFAULT_AMOUNT_TOLERANCE) / 100.0

        # Alle Beträge sammeln (inklusive das neue Dokument)
        amounts: Dict[str, Optional[Decimal]] = {
            "purchase_order": match.po_amount,
            "delivery_note": match.dn_amount,
            "invoice": match.invoice_amount,
        }
        if incoming_type in amounts and incoming_amount is not None:
            amounts[incoming_type] = incoming_amount

        # Betragsvergleiche nur bei vorhandenen Werten
        available_amounts = {k: v for k, v in amounts.items() if v is not None}
        if len(available_amounts) >= 2:
            amount_pairs = [
                ("purchase_order", "delivery_note", "Bestellung", "Lieferschein"),
                ("purchase_order", "invoice", "Bestellung", "Rechnung"),
                ("delivery_note", "invoice", "Lieferschein", "Rechnung"),
            ]
            for type_a, type_b, label_a, label_b in amount_pairs:
                val_a = available_amounts.get(type_a)
                val_b = available_amounts.get(type_b)
                if val_a is None or val_b is None:
                    continue
                deviation = self._calc_deviation_percent(val_a, val_b)
                if deviation is None:
                    continue
                if abs(deviation) > tolerance * 100:
                    severity = self._amount_deviation_severity(abs(deviation))
                    discrepancies.append(
                        DiscrepancyInfo(
                            category=DiscrepancyCategory.AMOUNT.value,
                            description=(
                                f"Betragsabweichung zwischen {label_a} ({val_a:.2f} EUR) "
                                f"und {label_b} ({val_b:.2f} EUR): {deviation:+.2f}%"
                            ),
                            field_name=f"{type_a}_vs_{type_b}_amount",
                            expected_value=f"{val_a:.2f} EUR",
                            actual_value=f"{val_b:.2f} EUR",
                            deviation_percent=deviation,
                            severity=severity,
                        )
                    )

        # Datumsreihenfolge prüfen (nur wenn Bestelldatum vorhanden)
        if match.order_date and incoming_type == "invoice" and incoming_amount is not None:
            # Rechnungsdatum sollte >= Bestelldatum sein
            now = datetime.now(timezone.utc)
            order_date = match.order_date
            if hasattr(order_date, "tzinfo") and order_date.tzinfo is None:
                order_date = order_date.replace(tzinfo=timezone.utc)
            if now < order_date:
                discrepancies.append(
                    DiscrepancyInfo(
                        category=DiscrepancyCategory.DATE.value,
                        description=(
                            "Systemdatum liegt vor dem Bestelldatum - "
                            "Datumsreihenfolge prüfen"
                        ),
                        field_name="invoice_date_vs_order_date",
                        expected_value=f">= {order_date.date().isoformat()}",
                        actual_value=now.date().isoformat(),
                        deviation_percent=None,
                        severity=DiscrepancySeverity.WARNING.value,
                    )
                )

        return discrepancies

    # -------------------------------------------------------------------------
    # Score-Berechnung und Status-Logik
    # -------------------------------------------------------------------------

    def _calculate_score(
        self,
        confidence: float,
        discrepancies: List[DiscrepancyInfo],
        document_count: int,
    ) -> float:
        """Berechnet den Match-Score (0-100).

        Basis: confidence * 100
        Abzüge je nach Schweregrad der Abweichungen
        Bonus für vollständigen 3-Way-Match
        """
        base = confidence * 100.0

        # Abzüge für Abweichungen
        severity_deductions: Dict[str, float] = {
            DiscrepancySeverity.INFO.value: 2.0,
            DiscrepancySeverity.WARNING.value: 5.0,
            DiscrepancySeverity.ERROR.value: 15.0,
            DiscrepancySeverity.CRITICAL.value: 30.0,
        }
        for disc in discrepancies:
            base -= severity_deductions.get(disc.severity, 5.0)

        # Bonus für 3 Dokumente
        if document_count >= 3:
            base = min(base + 5.0, 100.0)

        return max(0.0, min(base, 100.0))

    def _determine_status(
        self,
        match: PurchaseOrderMatch,
        discrepancies: List[DiscrepancyInfo],
        score: float,
    ) -> MatchStatus:
        """Bestimmt den neuen Match-Status basierend auf Dokumentenanzahl und Abweichungen."""
        # Dokumentenanzahl nach Update ermitteln (das neue Dokument ist noch nicht committed)
        # Wir zählen nicht-null Werte (der neue Slot wurde via setattr bereits gesetzt)
        doc_count = match.document_count

        critical_or_error = any(
            d.severity in (DiscrepancySeverity.CRITICAL.value, DiscrepancySeverity.ERROR.value)
            for d in discrepancies
        )

        if doc_count >= 3:
            if discrepancies and critical_or_error:
                return MatchStatus.DISCREPANCY
            return MatchStatus.FULL

        if doc_count == 2:
            if discrepancies and critical_or_error:
                return MatchStatus.DISCREPANCY
            return MatchStatus.PARTIAL

        return MatchStatus.PENDING

    # -------------------------------------------------------------------------
    # Statische Hilfsmethoden
    # -------------------------------------------------------------------------

    @staticmethod
    def _amount_deviation_severity(deviation_pct: float) -> str:
        """Berechnet den Schweregrad einer Betragsabweichung."""
        if deviation_pct > 10.0:
            return DiscrepancySeverity.CRITICAL.value
        if deviation_pct > 5.0:
            return DiscrepancySeverity.ERROR.value
        if deviation_pct > 2.0:
            return DiscrepancySeverity.WARNING.value
        return DiscrepancySeverity.INFO.value

    @staticmethod
    def _calc_deviation_percent(
        expected: Decimal,
        actual: Decimal,
    ) -> Optional[float]:
        """Berechnet die prozentuale Abweichung von expected zu actual."""
        if expected == Decimal("0"):
            return None
        deviation = ((actual - expected) / expected) * Decimal("100")
        return float(deviation)

    @staticmethod
    def _get_first_existing_doc(
        match: PurchaseOrderMatch,
    ) -> Tuple[Optional[UUID], Optional[str]]:
        """Gibt das erste bereits vorhandene Dokument eines Matches zurück."""
        if match.purchase_order_id:
            return match.purchase_order_id, "purchase_order"
        if match.delivery_note_id:
            return match.delivery_note_id, "delivery_note"
        if match.invoice_id:
            return match.invoice_id, "invoice"
        return None, None

    @staticmethod
    def _get_primary_amount(match: PurchaseOrderMatch) -> Optional[Decimal]:
        """Gibt den primären Betrag eines Matches zurück (PO > DN > Invoice)."""
        return match.po_amount or match.dn_amount or match.invoice_amount

    @staticmethod
    def _discrepancy_to_info(disc: MatchDiscrepancy) -> DiscrepancyInfo:
        """Konvertiert ein MatchDiscrepancy-Objekt in ein DiscrepancyInfo-DTO."""
        return DiscrepancyInfo(
            category=disc.category.value,
            description=disc.description,
            field_name=disc.field_name,
            expected_value=disc.expected_value or "",
            actual_value=disc.actual_value or "",
            deviation_percent=disc.deviation_percent,
            severity=disc.severity.value,
        )

    @staticmethod
    def _extract_reference_from_fields(
        extracted_fields: Dict[str, Dict[str, object]],
    ) -> Optional[str]:
        """Extrahiert Bestellnummer aus OCR-extracted_fields."""
        for key in ("order_number", "bestellnummer", "reference", "referenz", "po_number"):
            field_data = extracted_fields.get(key, {})
            if isinstance(field_data, dict):
                value = field_data.get("value") or field_data.get("text")
                if value and isinstance(value, str):
                    return value.strip()
        return None

    @staticmethod
    def _detect_strategy_from_confidence(confidence: float) -> str:
        """Gibt den Strategienamen basierend auf der Confidence zurück."""
        if confidence >= 0.90:
            return "order_number"
        if confidence >= 0.80:
            return "vendor_amount"
        return "vendor_date"

    @staticmethod
    def _build_match_explanation(
        candidate: MatchCandidate,
        doc_count: int,
        score: float,
        discrepancies: List[DiscrepancyInfo],
        auto_approved: bool,
    ) -> str:
        """Erstellt eine deutsche Erklärung des Match-Ergebnisses."""
        parts: List[str] = [
            f"Match gefunden via: {candidate.match_reason}.",
            f"Dokumente im Match: {doc_count}/3.",
            f"Match-Score: {score:.1f}/100.",
        ]
        if discrepancies:
            parts.append(
                f"{len(discrepancies)} Abweichung(en) erkannt: "
                + ", ".join(d.field_name for d in discrepancies)
                + "."
            )
        if auto_approved:
            parts.append("Match wurde automatisch freigegeben (Score >= 95, keine Abweichungen).")
        elif doc_count >= 3:
            parts.append("3-Way Match vollständig - manuelle Prüfung empfohlen.")
        return " ".join(parts)

    @staticmethod
    def _build_status_explanation(match: PurchaseOrderMatch) -> str:
        """Erstellt eine deutsche Statusbeschreibung für einen Match."""
        status_texts: Dict[str, str] = {
            MatchStatus.PENDING.value: "Warte auf weitere Dokumente.",
            MatchStatus.PARTIAL.value: "Teilweise gematcht - ein weiteres Dokument fehlt.",
            MatchStatus.FULL.value: "3-Way Match vollständig.",
            MatchStatus.DISCREPANCY.value: "Match vollständig, aber Abweichungen vorhanden.",
            MatchStatus.REJECTED.value: "Match wurde manuell abgelehnt.",
            MatchStatus.APPROVED.value: "Match wurde freigegeben.",
        }
        base = status_texts.get(
            match.match_status.value,
            "Status unbekannt.",
        )
        doc_count = match.document_count
        return f"{base} Dokumente: {doc_count}/3. Score: {match.match_score or 0:.1f}/100."
