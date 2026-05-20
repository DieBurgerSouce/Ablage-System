# -*- coding: utf-8 -*-
"""
RecurringInvoiceService - Abo-Verwaltung für Ablage-System.

Implementiert:
- Automatische Erkennung wiederkehrender Rechnungsmuster
- Manuelle Abo-Verwaltung (CRUD)
- Soll/Ist-Vergleiche für erwartete vs. tatsaechliche Rechnungen
- Preisänderungs-Erkennung und Alerts
- Fehlende-Rechnungen-Erkennung
- Kündigungsfristen-Tracking

Phase 2.2 der Feature-Roadmap (Februar 2026).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import structlog
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.datetime_utils import utc_now
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import Document, InvoiceTracking
from app.db.models_recurring_invoice import (
    RecurringInvoice,
    RecurringInvoiceOccurrence,
    RecurringInvoiceStatus,
    RecurringIntervalType,
    DetectionMethod,
    OccurrenceStatus,
    OccurrenceMatchMethod,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Request/Response Dataclasses
# ============================================================================


@dataclass
class RecurringInvoiceCreateRequest:
    """Request für manuelle Abo-Erstellung."""
    company_id: uuid.UUID
    vendor_name: str
    interval_type: RecurringIntervalType
    expected_amount: Decimal
    interval_months: int = 1
    currency: str = "EUR"
    tolerance_percent: float = 5.0
    vendor_entity_id: Optional[uuid.UUID] = None
    first_seen_date: Optional[date] = None
    next_expected_date: Optional[date] = None
    cancellation_deadline: Optional[date] = None
    notice_period_days: Optional[int] = None
    auto_renewal: bool = True
    category: Optional[str] = None
    description: Optional[str] = None
    document_type: Optional[str] = None
    reference_pattern: Optional[str] = None


@dataclass
class RecurringInvoiceUpdateRequest:
    """Request für Abo-Aktualisierung."""
    status: Optional[RecurringInvoiceStatus] = None
    expected_amount: Optional[Decimal] = None
    interval_type: Optional[RecurringIntervalType] = None
    interval_months: Optional[int] = None
    tolerance_percent: Optional[float] = None
    cancellation_deadline: Optional[date] = None
    notice_period_days: Optional[int] = None
    auto_renewal: Optional[bool] = None
    next_expected_date: Optional[date] = None
    category: Optional[str] = None
    description: Optional[str] = None
    reference_pattern: Optional[str] = None


@dataclass
class MatchInvoiceRequest:
    """Request für manuelles Zuordnen einer Rechnung."""
    document_id: uuid.UUID
    vendor_name: str
    amount: Decimal
    invoice_date: date
    invoice_tracking_id: Optional[uuid.UUID] = None


@dataclass
class DetectedPattern:
    """Ein erkanntes wiederkehrendes Muster."""
    vendor_name: str
    vendor_entity_id: Optional[uuid.UUID]
    interval_type: RecurringIntervalType
    interval_months: int
    average_amount: Decimal
    occurrences_found: int
    confidence: float
    first_date: date
    last_date: date
    amounts: List[Decimal]


@dataclass
class MissingInvoiceInfo:
    """Information über eine fehlende Rechnung."""
    recurring_invoice_id: uuid.UUID
    vendor_name: str
    expected_date: date
    expected_amount: Decimal
    days_overdue: int
    occurrence_id: Optional[uuid.UUID] = None


@dataclass
class PriceChangeInfo:
    """Information über eine Preisänderung."""
    recurring_invoice_id: uuid.UUID
    vendor_name: str
    old_amount: Decimal
    new_amount: Decimal
    change_percent: float
    change_date: date


@dataclass
class SollIstRow:
    """Eine Zeile im Soll/Ist-Bericht."""
    recurring_invoice_id: uuid.UUID
    vendor_name: str
    category: Optional[str]
    expected_amount: Decimal
    actual_amount: Optional[Decimal]
    deviation: Optional[Decimal]
    deviation_percent: Optional[float]
    status: OccurrenceStatus
    expected_date: date
    actual_date: Optional[date]


@dataclass
class SollIstReport:
    """Soll/Ist-Vergleichsbericht."""
    company_id: uuid.UUID
    year: int
    month: int
    rows: List[SollIstRow]
    total_expected: Decimal
    total_actual: Decimal
    total_deviation: Decimal
    missing_count: int
    matched_count: int
    generated_at: date


# ============================================================================
# RecurringInvoiceService Implementation
# ============================================================================


class RecurringInvoiceService:
    """Service für Abo-Verwaltung und wiederkehrende Rechnungserkennung."""

    # ========================================================================
    # Detection
    # ========================================================================

    async def detect_recurring_invoices(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        min_occurrences: int = 3,
        lookback_months: int = 12,
    ) -> List[DetectedPattern]:
        """Analysiert Rechnungshistorie und erkennt wiederkehrende Muster.

        Gruppiert Rechnungen nach Lieferant (aus Dokument-Metadaten),
        prüft Intervalle und Betragsähnlichkeit, um Abo-Muster zu identifizieren.
        """
        cutoff_date = date.today() - timedelta(days=lookback_months * 30)

        # Hole Rechnungen der letzten N Monate mit zugehoerigem Dokument
        result = await db.execute(
            select(InvoiceTracking, Document)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= cutoff_date,
                )
            )
            .order_by(InvoiceTracking.invoice_date)
        )
        rows = list(result.all())

        if not rows:
            return []

        # Gruppiere nach Lieferant (aus Dokument-Metadaten)
        vendor_groups: Dict[str, List[Tuple[InvoiceTracking, Document]]] = defaultdict(list)
        for inv, doc in rows:
            vendor_name = self._extract_vendor_name(doc)
            if vendor_name:
                key = vendor_name.strip().lower()
                vendor_groups[key].append((inv, doc))

        detected: List[DetectedPattern] = []

        for vendor_key, vendor_entries in vendor_groups.items():
            if len(vendor_entries) < min_occurrences:
                continue

            pattern = self._analyze_vendor_pattern(vendor_entries, min_occurrences)
            if pattern:
                detected.append(pattern)

        logger.info(
            "recurring_detection_complete",
            company_id=str(company_id),
            patterns_found=len(detected),
            invoices_analyzed=len(rows),
        )

        return detected

    @staticmethod
    def _extract_vendor_name(doc: Document) -> Optional[str]:
        """Extrahiert den Lieferantennamen aus Dokument-Metadaten."""
        metadata = doc.document_metadata or {}
        # Prüfe verschiedene Felder in den Metadaten
        for field_name in ("vendor_name", "sender_name", "supplier_name", "absender"):
            value = metadata.get(field_name)
            if value and isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _analyze_vendor_pattern(
        self,
        entries: List[Tuple[InvoiceTracking, Document]],
        min_occurrences: int,
    ) -> Optional[DetectedPattern]:
        """Analysiert Rechnungen eines Lieferanten auf wiederkehrende Muster."""
        if len(entries) < min_occurrences:
            return None

        # Sortiere nach Datum
        sorted_entries = sorted(
            entries,
            key=lambda e: e[0].invoice_date or date.min,
        )
        dates: List[date] = []
        amounts: List[Decimal] = []
        for inv, _doc in sorted_entries:
            if inv.invoice_date:
                # invoice_date ist DateTime, konvertiere zu date
                inv_date = inv.invoice_date
                if hasattr(inv_date, "date"):
                    inv_date = inv_date.date()
                dates.append(inv_date)
            if inv.amount is not None:
                amounts.append(Decimal(str(inv.amount)))

        if len(dates) < min_occurrences or len(amounts) < min_occurrences:
            return None

        # Berechne Intervalle zwischen Rechnungen (in Tagen)
        intervals_days: List[int] = []
        for i in range(1, len(dates)):
            delta = (dates[i] - dates[i - 1]).days
            if delta > 0:
                intervals_days.append(delta)

        if not intervals_days:
            return None

        avg_interval = sum(intervals_days) / len(intervals_days)

        # Bestimme Intervall-Typ
        interval_type, interval_months = self._classify_interval(avg_interval)
        if interval_type is None:
            return None

        # Prüfe Konsistenz der Intervalle (Standardabweichung)
        if len(intervals_days) > 1:
            variance = sum((d - avg_interval) ** 2 for d in intervals_days) / len(intervals_days)
            std_dev = variance ** 0.5
            interval_consistency = max(0.0, 1.0 - (std_dev / avg_interval)) if avg_interval > 0 else 0.0
        else:
            interval_consistency = 0.5

        # Prüfe Betragsähnlichkeit
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount > 0:
            amount_deviations = [abs(a - avg_amount) / avg_amount for a in amounts]
            avg_deviation = sum(amount_deviations) / len(amount_deviations)
            amount_consistency = max(0.0, 1.0 - float(avg_deviation))
        else:
            amount_consistency = 0.0

        # Gesamtkonfidenz
        confidence = (interval_consistency * 0.6) + (amount_consistency * 0.4)

        if confidence < 0.5:
            return None

        first_inv, first_doc = sorted_entries[0]
        vendor_name = self._extract_vendor_name(first_doc) or ""

        return DetectedPattern(
            vendor_name=vendor_name,
            vendor_entity_id=None,
            interval_type=interval_type,
            interval_months=interval_months,
            average_amount=Decimal(str(round(float(avg_amount), 2))),
            occurrences_found=len(sorted_entries),
            confidence=round(confidence, 3),
            first_date=dates[0],
            last_date=dates[-1],
            amounts=amounts,
        )

    @staticmethod
    def _classify_interval(
        avg_days: float,
    ) -> Tuple[Optional[RecurringIntervalType], int]:
        """Klassifiziert ein Durchschnittsintervall in einen Typ."""
        if 25 <= avg_days <= 35:
            return RecurringIntervalType.MONTHLY, 1
        elif 55 <= avg_days <= 65:
            # Zweimonatlich (kein eigener Enum, nutze interval_months=2)
            return RecurringIntervalType.MONTHLY, 2
        elif 80 <= avg_days <= 100:
            return RecurringIntervalType.QUARTERLY, 3
        elif 170 <= avg_days <= 195:
            return RecurringIntervalType.HALF_YEARLY, 6
        elif 350 <= avg_days <= 380:
            return RecurringIntervalType.YEARLY, 12
        else:
            return None, 0

    # ========================================================================
    # CRUD
    # ========================================================================

    async def create_recurring_invoice(
        self,
        db: AsyncSession,
        request: RecurringInvoiceCreateRequest,
    ) -> RecurringInvoice:
        """Erstellt eine neue wiederkehrende Rechnung (manuell)."""
        recurring = RecurringInvoice(
            company_id=request.company_id,
            vendor_entity_id=request.vendor_entity_id,
            vendor_name=request.vendor_name,
            interval_type=request.interval_type,
            interval_months=request.interval_months,
            expected_amount=request.expected_amount,
            currency=request.currency,
            tolerance_percent=request.tolerance_percent,
            first_seen_date=request.first_seen_date,
            next_expected_date=request.next_expected_date,
            cancellation_deadline=request.cancellation_deadline,
            notice_period_days=request.notice_period_days,
            auto_renewal=request.auto_renewal,
            detection_method=DetectionMethod.MANUAL,
            detection_confidence=1.0,
            category=request.category,
            description=request.description,
            document_type=request.document_type,
            reference_pattern=request.reference_pattern,
            status=RecurringInvoiceStatus.ACTIVE,
        )

        db.add(recurring)
        await db.commit()
        await db.refresh(recurring)

        logger.info(
            "recurring_invoice_created",
            recurring_id=str(recurring.id),
            vendor_name=request.vendor_name,
            company_id=str(request.company_id),
        )

        return recurring

    async def list_recurring_invoices(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        status_filter: Optional[RecurringInvoiceStatus] = None,
        page: int = 0,
        page_size: int = 25,
    ) -> Tuple[List[RecurringInvoice], int]:
        """Listet wiederkehrende Rechnungen mit optionalem Status-Filter."""
        query = select(RecurringInvoice).where(
            RecurringInvoice.company_id == company_id
        )

        if status_filter:
            query = query.where(RecurringInvoice.status == status_filter)

        # Gesamtanzahl
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        # Paginierung
        query = (
            query
            .order_by(RecurringInvoice.next_expected_date.asc().nullslast(), RecurringInvoice.vendor_name)
            .offset(page * page_size)
            .limit(page_size)
        )

        result = await db.execute(query)
        return list(result.scalars().all()), total

    async def get_recurring_invoice(
        self,
        db: AsyncSession,
        recurring_id: uuid.UUID,
    ) -> Optional[RecurringInvoice]:
        """Ruft eine wiederkehrende Rechnung mit Vorkommen ab."""
        query = (
            select(RecurringInvoice)
            .where(RecurringInvoice.id == recurring_id)
            .options(selectinload(RecurringInvoice.occurrences))
        )
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def update_recurring_invoice(
        self,
        db: AsyncSession,
        recurring_id: uuid.UUID,
        request: RecurringInvoiceUpdateRequest,
    ) -> RecurringInvoice:
        """Aktualisiert eine wiederkehrende Rechnung."""
        recurring = await db.get(RecurringInvoice, recurring_id)
        if not recurring:
            raise ValueError(f"Wiederkehrende Rechnung {recurring_id} nicht gefunden")

        if request.status is not None:
            recurring.status = request.status
        if request.expected_amount is not None:
            recurring.expected_amount = request.expected_amount
        if request.interval_type is not None:
            recurring.interval_type = request.interval_type
        if request.interval_months is not None:
            recurring.interval_months = request.interval_months
        if request.tolerance_percent is not None:
            recurring.tolerance_percent = request.tolerance_percent
        if request.cancellation_deadline is not None:
            recurring.cancellation_deadline = request.cancellation_deadline
        if request.notice_period_days is not None:
            recurring.notice_period_days = request.notice_period_days
        if request.auto_renewal is not None:
            recurring.auto_renewal = request.auto_renewal
        if request.next_expected_date is not None:
            recurring.next_expected_date = request.next_expected_date
        if request.category is not None:
            recurring.category = request.category
        if request.description is not None:
            recurring.description = request.description
        if request.reference_pattern is not None:
            recurring.reference_pattern = request.reference_pattern

        await db.commit()
        await db.refresh(recurring)

        logger.info(
            "recurring_invoice_updated",
            recurring_id=str(recurring_id),
        )

        return recurring

    # ========================================================================
    # Matching
    # ========================================================================

    async def match_incoming_invoice(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        request: MatchInvoiceRequest,
    ) -> Optional[RecurringInvoiceOccurrence]:
        """Versucht eine eingehende Rechnung einem Abo-Muster zuzuordnen.

        Sucht aktive wiederkehrende Rechnungen des Lieferanten und prüft
        ob Betrag und Datum zur Erwartung passen.
        """
        vendor_lower = request.vendor_name.strip().lower()

        # Suche passende aktive Abos
        result = await db.execute(
            select(RecurringInvoice)
            .where(
                and_(
                    RecurringInvoice.company_id == company_id,
                    RecurringInvoice.status == RecurringInvoiceStatus.ACTIVE,
                    func.lower(RecurringInvoice.vendor_name) == vendor_lower,
                )
            )
        )
        candidates = list(result.scalars().all())

        if not candidates:
            return None

        best_match: Optional[RecurringInvoice] = None
        best_confidence = 0.0

        for candidate in candidates:
            confidence = self._calculate_match_confidence(
                candidate, request.amount, request.invoice_date,
            )
            if confidence > best_confidence and confidence >= 0.5:
                best_confidence = confidence
                best_match = candidate

        if not best_match:
            return None

        # Erstelle oder aktualisiere Occurrence
        occurrence = await self._create_or_update_occurrence(
            db, best_match, request, best_confidence,
        )

        # Aktualisiere Abo-Statistiken
        best_match.last_seen_date = request.invoice_date
        best_match.match_count = (best_match.match_count or 0) + 1
        best_match.next_expected_date = self._calculate_next_expected_date(
            request.invoice_date, best_match.interval_months,
        )

        # Prüfe auf Preisänderung
        await self._check_price_change(db, best_match, request.amount)

        await db.commit()
        await db.refresh(occurrence)

        logger.info(
            "incoming_invoice_matched",
            recurring_id=str(best_match.id),
            document_id=str(request.document_id),
            confidence=best_confidence,
        )

        return occurrence

    def _calculate_match_confidence(
        self,
        recurring: RecurringInvoice,
        amount: Decimal,
        invoice_date: date,
    ) -> float:
        """Berechnet die Zuordnungskonfidenz."""
        # Betrags-Übereinstimmung
        if recurring.expected_amount and recurring.expected_amount > 0:
            deviation = abs(float(amount - recurring.expected_amount) / float(recurring.expected_amount)) * 100
            tolerance = recurring.tolerance_percent or 5.0
            if deviation <= tolerance:
                amount_score = 1.0 - (deviation / tolerance) * 0.3
            elif deviation <= tolerance * 2:
                amount_score = 0.5
            else:
                amount_score = 0.1
        else:
            amount_score = 0.5

        # Datums-Übereinstimmung
        if recurring.next_expected_date:
            days_diff = abs((invoice_date - recurring.next_expected_date).days)
            if days_diff <= 5:
                date_score = 1.0
            elif days_diff <= 15:
                date_score = 0.7
            elif days_diff <= 30:
                date_score = 0.4
            else:
                date_score = 0.1
        else:
            date_score = 0.5

        return (amount_score * 0.5) + (date_score * 0.5)

    async def _create_or_update_occurrence(
        self,
        db: AsyncSession,
        recurring: RecurringInvoice,
        request: MatchInvoiceRequest,
        confidence: float,
    ) -> RecurringInvoiceOccurrence:
        """Erstellt oder aktualisiert eine Occurrence für das Match."""
        # Suche bestehende erwartete Occurrence im Zeitfenster +/- 30 Tage
        existing_result = await db.execute(
            select(RecurringInvoiceOccurrence)
            .where(
                and_(
                    RecurringInvoiceOccurrence.recurring_invoice_id == recurring.id,
                    RecurringInvoiceOccurrence.status == OccurrenceStatus.EXPECTED,
                    RecurringInvoiceOccurrence.expected_date >= request.invoice_date - timedelta(days=30),
                    RecurringInvoiceOccurrence.expected_date <= request.invoice_date + timedelta(days=30),
                )
            )
            .order_by(RecurringInvoiceOccurrence.expected_date)
            .limit(1)
        )
        existing = existing_result.scalar_one_or_none()

        now = utc_now()

        if existing:
            # Aktualisiere bestehende Occurrence
            existing.document_id = request.document_id
            existing.invoice_tracking_id = request.invoice_tracking_id
            existing.actual_date = request.invoice_date
            existing.actual_amount = request.amount
            existing.amount_deviation = request.amount - existing.expected_amount
            existing.match_confidence = confidence
            existing.matched_at = now
            existing.matched_by = OccurrenceMatchMethod.AUTO
            existing.status = self._determine_occurrence_status(
                existing.expected_amount, request.amount, existing.expected_date, request.invoice_date,
            )
            return existing

        # Erstelle neue Occurrence
        deviation = request.amount - recurring.expected_amount if recurring.expected_amount else None
        occurrence = RecurringInvoiceOccurrence(
            recurring_invoice_id=recurring.id,
            document_id=request.document_id,
            invoice_tracking_id=request.invoice_tracking_id,
            expected_date=recurring.next_expected_date or request.invoice_date,
            actual_date=request.invoice_date,
            expected_amount=recurring.expected_amount,
            actual_amount=request.amount,
            amount_deviation=deviation,
            match_confidence=confidence,
            matched_at=now,
            matched_by=OccurrenceMatchMethod.AUTO,
            status=self._determine_occurrence_status(
                recurring.expected_amount, request.amount,
                recurring.next_expected_date or request.invoice_date, request.invoice_date,
            ),
        )
        db.add(occurrence)
        return occurrence

    @staticmethod
    def _determine_occurrence_status(
        expected_amount: Decimal,
        actual_amount: Decimal,
        expected_date: date,
        actual_date: date,
    ) -> OccurrenceStatus:
        """Bestimmt den Status einer Occurrence basierend auf Betrag und Datum."""
        tolerance = Decimal("0.05")  # 5% Toleranz
        if expected_amount and expected_amount > 0:
            deviation_ratio = abs(actual_amount - expected_amount) / expected_amount
        else:
            deviation_ratio = Decimal("0")

        if deviation_ratio <= tolerance:
            if (actual_date - expected_date).days > 15:
                return OccurrenceStatus.LATE
            return OccurrenceStatus.MATCHED
        elif actual_amount > expected_amount:
            return OccurrenceStatus.OVERPAID
        else:
            return OccurrenceStatus.UNDERPAID

    async def _check_price_change(
        self,
        db: AsyncSession,
        recurring: RecurringInvoice,
        new_amount: Decimal,
    ) -> None:
        """Prüft auf Preisänderung und aktualisiert Preis-History."""
        if not recurring.expected_amount or recurring.expected_amount == 0:
            return

        tolerance = Decimal(str(recurring.tolerance_percent or 5.0)) / Decimal("100")
        deviation = abs(new_amount - recurring.expected_amount) / recurring.expected_amount

        if deviation > tolerance:
            change_percent = float((new_amount - recurring.expected_amount) / recurring.expected_amount * 100)

            # Aktualisiere Preis-History
            history = list(recurring.price_history or [])
            history.append({
                "date": date.today().isoformat(),
                "old_amount": float(recurring.expected_amount),
                "new_amount": float(new_amount),
                "change_percent": round(change_percent, 2),
            })
            recurring.price_history = history
            recurring.last_price_change_date = date.today()
            recurring.price_change_percent = round(change_percent, 2)
            recurring.expected_amount = new_amount
            recurring.price_increase_alerted = False  # Reset für neuen Alert

            logger.info(
                "recurring_price_change_detected",
                recurring_id=str(recurring.id),
                change_percent=round(change_percent, 2),
            )

    @staticmethod
    def _calculate_next_expected_date(
        from_date: date,
        interval_months: int,
    ) -> date:
        """Berechnet das nächste erwartete Datum basierend auf dem Intervall."""
        month = from_date.month + interval_months
        year = from_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        day = min(from_date.day, 28)  # Sicher für alle Monate
        return date(year, month, day)

    # ========================================================================
    # Missing & Price Change Detection
    # ========================================================================

    async def check_missing_invoices(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[MissingInvoiceInfo]:
        """Findet überfällige / fehlende erwartete Rechnungen."""
        today = date.today()

        # Finde aktive Abos mit überfälligem next_expected_date
        result = await db.execute(
            select(RecurringInvoice)
            .where(
                and_(
                    RecurringInvoice.company_id == company_id,
                    RecurringInvoice.status == RecurringInvoiceStatus.ACTIVE,
                    RecurringInvoice.next_expected_date < today,
                )
            )
            .order_by(RecurringInvoice.next_expected_date)
        )
        overdue_abos = list(result.scalars().all())

        missing: List[MissingInvoiceInfo] = []

        for abo in overdue_abos:
            if not abo.next_expected_date:
                continue

            days_overdue = (today - abo.next_expected_date).days

            # Nur melden wenn mehr als 5 Tage überfällig
            if days_overdue > 5:
                missing.append(MissingInvoiceInfo(
                    recurring_invoice_id=abo.id,
                    vendor_name=abo.vendor_name,
                    expected_date=abo.next_expected_date,
                    expected_amount=abo.expected_amount,
                    days_overdue=days_overdue,
                ))

        logger.info(
            "missing_invoices_checked",
            company_id=str(company_id),
            missing_count=len(missing),
        )

        return missing

    async def check_price_changes(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[PriceChangeInfo]:
        """Findet Abos mit nicht-alertierten Preisänderungen."""
        result = await db.execute(
            select(RecurringInvoice)
            .where(
                and_(
                    RecurringInvoice.company_id == company_id,
                    RecurringInvoice.status == RecurringInvoiceStatus.ACTIVE,
                    RecurringInvoice.price_increase_alerted == False,
                    RecurringInvoice.last_price_change_date.isnot(None),
                    RecurringInvoice.price_change_percent.isnot(None),
                )
            )
            .order_by(RecurringInvoice.last_price_change_date.desc())
        )
        abos = list(result.scalars().all())

        changes: List[PriceChangeInfo] = []

        for abo in abos:
            history = list(abo.price_history or [])
            if not history:
                continue

            last_change = history[-1]
            changes.append(PriceChangeInfo(
                recurring_invoice_id=abo.id,
                vendor_name=abo.vendor_name,
                old_amount=Decimal(str(last_change.get("old_amount", 0))),
                new_amount=Decimal(str(last_change.get("new_amount", 0))),
                change_percent=last_change.get("change_percent", 0.0),
                change_date=date.fromisoformat(last_change["date"]) if "date" in last_change else date.today(),
            ))

        return changes

    # ========================================================================
    # Soll/Ist Report
    # ========================================================================

    async def get_soll_ist_report(
        self,
        db: AsyncSession,
        company_id: uuid.UUID,
        year: int,
        month: int,
    ) -> SollIstReport:
        """Erstellt Soll/Ist-Vergleichsbericht für einen Monat.

        Vergleicht erwartete wiederkehrende Rechnungen mit
        tatsaechlich eingegangenen Rechnungen.
        """
        period_start = date(year, month, 1)
        if month == 12:
            period_end = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            period_end = date(year, month + 1, 1) - timedelta(days=1)

        # Hole alle aktiven Abos der Firma
        abos_result = await db.execute(
            select(RecurringInvoice)
            .where(
                and_(
                    RecurringInvoice.company_id == company_id,
                    RecurringInvoice.status.in_([
                        RecurringInvoiceStatus.ACTIVE,
                        RecurringInvoiceStatus.PAUSED,
                    ]),
                )
            )
            .options(selectinload(RecurringInvoice.occurrences))
        )
        abos = list(abos_result.scalars().all())

        rows: List[SollIstRow] = []
        total_expected = Decimal("0")
        total_actual = Decimal("0")
        missing_count = 0
        matched_count = 0

        for abo in abos:
            # Prüfe ob dieses Abo im Zeitraum eine Rechnung erwartet
            if not self._is_expected_in_period(abo, period_start, period_end):
                continue

            # Suche passende Occurrence im Zeitraum
            occurrence = self._find_occurrence_in_period(
                abo.occurrences, period_start, period_end,
            )

            expected_amount = abo.expected_amount or Decimal("0")
            total_expected += expected_amount

            if occurrence and occurrence.actual_amount is not None:
                actual_amount = occurrence.actual_amount
                total_actual += actual_amount
                deviation = actual_amount - expected_amount
                deviation_percent = (
                    float(deviation / expected_amount * 100)
                    if expected_amount > 0 else 0.0
                )
                row_status = occurrence.status
                actual_date = occurrence.actual_date
                matched_count += 1
            else:
                actual_amount = None
                deviation = None
                deviation_percent = None
                actual_date = None
                if date.today() > period_end:
                    row_status = OccurrenceStatus.MISSING
                    missing_count += 1
                else:
                    row_status = OccurrenceStatus.EXPECTED

            rows.append(SollIstRow(
                recurring_invoice_id=abo.id,
                vendor_name=abo.vendor_name,
                category=abo.category,
                expected_amount=expected_amount,
                actual_amount=actual_amount,
                deviation=deviation,
                deviation_percent=deviation_percent,
                status=row_status,
                expected_date=self._expected_date_in_period(abo, period_start),
                actual_date=actual_date,
            ))

        total_deviation = total_actual - total_expected

        return SollIstReport(
            company_id=company_id,
            year=year,
            month=month,
            rows=rows,
            total_expected=total_expected,
            total_actual=total_actual,
            total_deviation=total_deviation,
            missing_count=missing_count,
            matched_count=matched_count,
            generated_at=date.today(),
        )

    def _is_expected_in_period(
        self,
        recurring: RecurringInvoice,
        period_start: date,
        period_end: date,
    ) -> bool:
        """Prüft ob ein Abo im gegebenen Zeitraum eine Rechnung erwartet."""
        if not recurring.first_seen_date:
            return True

        if recurring.first_seen_date > period_end:
            return False

        interval = recurring.interval_months or 1
        # Einfache Prüfung: monatlich = immer, vierteljährlich = Monat % 3, etc.
        if interval == 1:
            return True

        # Prüfe ob der Monat ein Vielfaches des Intervalls vom Startmonat ist
        start_month = recurring.first_seen_date.month
        period_month = period_start.month
        months_diff = (period_start.year - recurring.first_seen_date.year) * 12 + (period_month - start_month)
        return months_diff % interval == 0

    def _expected_date_in_period(
        self,
        recurring: RecurringInvoice,
        period_start: date,
    ) -> date:
        """Berechnet das erwartete Datum in einem Zeitraum."""
        if recurring.next_expected_date:
            # Wenn next_expected_date im Monat liegt
            if recurring.next_expected_date.year == period_start.year and recurring.next_expected_date.month == period_start.month:
                return recurring.next_expected_date

        # Fallback: erster Freitag des Monats oder gespeicherter Tag
        if recurring.first_seen_date:
            day = min(recurring.first_seen_date.day, 28)
        else:
            day = 15
        return date(period_start.year, period_start.month, day)

    @staticmethod
    def _find_occurrence_in_period(
        occurrences: List[RecurringInvoiceOccurrence],
        period_start: date,
        period_end: date,
    ) -> Optional[RecurringInvoiceOccurrence]:
        """Findet eine Occurrence im gegebenen Zeitraum."""
        for occ in occurrences:
            occ_date = occ.actual_date or occ.expected_date
            if period_start <= occ_date <= period_end:
                return occ
        return None

    # ========================================================================
    # Cancellation Management
    # ========================================================================

    async def update_cancellation_deadline(
        self,
        db: AsyncSession,
        recurring_id: uuid.UUID,
        deadline: date,
        notice_days: Optional[int] = None,
    ) -> RecurringInvoice:
        """Aktualisiert die Kündigungsfrist eines Abos."""
        recurring = await db.get(RecurringInvoice, recurring_id)
        if not recurring:
            raise ValueError(f"Wiederkehrende Rechnung {recurring_id} nicht gefunden")

        recurring.cancellation_deadline = deadline
        if notice_days is not None:
            recurring.notice_period_days = notice_days

        await db.commit()
        await db.refresh(recurring)

        logger.info(
            "cancellation_deadline_updated",
            recurring_id=str(recurring_id),
            deadline=deadline.isoformat(),
        )

        return recurring

    # ========================================================================
    # Manual Match
    # ========================================================================

    async def manual_match_document(
        self,
        db: AsyncSession,
        recurring_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> RecurringInvoiceOccurrence:
        """Ordnet ein Dokument manuell einem Abo zu."""
        recurring = await db.get(RecurringInvoice, recurring_id)
        if not recurring:
            raise ValueError(f"Wiederkehrende Rechnung {recurring_id} nicht gefunden")

        now = utc_now()

        occurrence = RecurringInvoiceOccurrence(
            recurring_invoice_id=recurring_id,
            document_id=document_id,
            expected_date=recurring.next_expected_date or date.today(),
            expected_amount=recurring.expected_amount,
            actual_date=date.today(),
            match_confidence=1.0,
            matched_at=now,
            matched_by=OccurrenceMatchMethod.MANUAL,
            status=OccurrenceStatus.MATCHED,
        )

        db.add(occurrence)

        # Aktualisiere Abo
        recurring.last_seen_date = date.today()
        recurring.match_count = (recurring.match_count or 0) + 1
        recurring.next_expected_date = self._calculate_next_expected_date(
            date.today(), recurring.interval_months,
        )

        await db.commit()
        await db.refresh(occurrence)

        logger.info(
            "manual_match_created",
            recurring_id=str(recurring_id),
            document_id=str(document_id),
        )

        return occurrence


# ============================================================================
# Singleton
# ============================================================================


_recurring_invoice_service: Optional[RecurringInvoiceService] = None


def get_recurring_invoice_service() -> RecurringInvoiceService:
    """Returns singleton RecurringInvoiceService instance."""
    global _recurring_invoice_service
    if _recurring_invoice_service is None:
        _recurring_invoice_service = RecurringInvoiceService()
    return _recurring_invoice_service
