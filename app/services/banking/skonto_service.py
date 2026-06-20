# -*- coding: utf-8 -*-
"""Skonto Service.

Verwaltet Skonto (Frühzahlerrabatt) für Rechnungen:
- Skonto-Berechnung basierend auf Konditionen
- Fristenüberwachung mit Alerts
- Skonto-Anwendung bei Zahlung
- Reporting zu gesparten/verpassten Skonti

Standard-Konditionen (typisch Deutschland):
- 2% Skonto bei Zahlung innerhalb 10 Tagen
- Netto 30 Tage Zahlungsziel
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now

logger = structlog.get_logger(__name__)


@dataclass
class SkontoCondition:
    """Skonto-Konditionen."""
    percentage: float  # z.B. 2.0 für 2%
    days: int  # Tage nach Rechnungsdatum
    net_days: int  # Zahlungsziel netto


@dataclass
class SkontoCalculation:
    """Ergebnis einer Skonto-Berechnung."""
    invoice_amount: Decimal
    skonto_percentage: float
    skonto_amount: Decimal
    skonto_deadline: datetime
    net_deadline: datetime
    days_remaining: Optional[int]  # None wenn abgelaufen
    is_expired: bool
    amount_with_skonto: Decimal
    savings_potential: Decimal
    skonto_days: int = 0  # Anzahl Tage für Skonto-Berechtigung

    @property
    def is_skonto_valid(self) -> bool:
        """Ist Skonto noch gültig (nicht abgelaufen)?"""
        return not self.is_expired


@dataclass
class SkontoAlert:
    """Skonto-Frist Alert."""
    invoice_id: UUID
    invoice_number: str
    entity_name: str
    skonto_deadline: datetime
    skonto_amount: Decimal
    days_remaining: int
    urgency: str  # "critical" (<1 Tag), "warning" (<3 Tage), "info" (>3 Tage)


@dataclass
class SkontoStatistics:
    """Skonto-Statistiken."""
    period_start: datetime
    period_end: datetime
    total_invoices: int
    invoices_with_skonto: int
    skonto_used_count: int
    skonto_missed_count: int
    skonto_pending_count: int
    total_savings: Decimal
    missed_savings: Decimal
    potential_savings: Decimal
    usage_rate: float  # Prozent


# Standard Skonto-Konditionen für Deutschland
DEFAULT_SKONTO_CONDITIONS = SkontoCondition(
    percentage=2.0,
    days=10,
    net_days=30
)


class SkontoService:
    """Service für Skonto-Management.

    Features:
    - Automatische Skonto-Berechnung bei Rechnungserfassung
    - Fristenmonitoring mit konfigurierbaren Alerts
    - Skonto-Anwendung bei Zahlungserfassung
    - Reporting und Statistiken
    """

    def __init__(
        self,
        default_conditions: Optional[SkontoCondition] = None
    ) -> None:
        """Initialisiere SkontoService.

        Args:
            default_conditions: Standard-Skonto-Konditionen falls nicht in Rechnung
        """
        self.default_conditions = default_conditions or DEFAULT_SKONTO_CONDITIONS

    async def calculate_skonto(
        self,
        db: AsyncSession,
        invoice_amount: Decimal,
        invoice_date: datetime,
        skonto_percentage: Optional[float] = None,
        skonto_days: Optional[int] = None,
        net_days: Optional[int] = None,
    ) -> SkontoCalculation:
        """Berechne Skonto für eine Rechnung.

        Args:
            db: Datenbank-Session
            invoice_amount: Rechnungsbetrag
            invoice_date: Rechnungsdatum
            skonto_percentage: Skonto-Prozentsatz (oder Default)
            skonto_days: Tage für Skonto-Berechtigung (oder Default)
            net_days: Zahlungsziel netto (oder Default)

        Returns:
            SkontoCalculation mit allen relevanten Werten
        """
        # Defaults anwenden
        percentage = skonto_percentage if skonto_percentage is not None else self.default_conditions.percentage
        days = skonto_days if skonto_days is not None else self.default_conditions.days
        net = net_days if net_days is not None else self.default_conditions.net_days

        now = utc_now()
        skonto_deadline = invoice_date + timedelta(days=days)
        net_deadline = invoice_date + timedelta(days=net)

        # Berechnung
        skonto_amount = Decimal(str(invoice_amount)) * Decimal(str(percentage)) / Decimal("100")
        skonto_amount = skonto_amount.quantize(Decimal("0.01"))  # Auf Cent runden

        amount_with_skonto = Decimal(str(invoice_amount)) - skonto_amount

        # Status
        is_expired = now > skonto_deadline
        # days_remaining ist None wenn abgelaufen, sonst die verbleibenden Tage
        days_remaining = None if is_expired else max(0, (skonto_deadline - now).days)

        return SkontoCalculation(
            invoice_amount=Decimal(str(invoice_amount)),
            skonto_percentage=percentage,
            skonto_amount=skonto_amount,
            skonto_deadline=skonto_deadline,
            net_deadline=net_deadline,
            days_remaining=days_remaining,
            is_expired=is_expired,
            amount_with_skonto=amount_with_skonto,
            savings_potential=skonto_amount if not is_expired else Decimal("0.00"),
            skonto_days=days,  # Anzahl Tage für Skonto-Berechtigung
        )

    async def apply_skonto(
        self,
        db: AsyncSession,
        invoice_tracking_id: UUID,
        payment_amount: Decimal,
        payment_date: datetime,
        user_id: UUID,
        company_id: UUID,
        force_apply: bool = False,
    ) -> Tuple[bool, Decimal, str]:
        """Wende Skonto auf Zahlung an.

        SECURITY: company_id ist REQUIRED für Multi-Tenant Isolation.

        Args:
            db: Datenbank-Session
            invoice_tracking_id: ID des Invoice-Trackings
            payment_amount: Gezahlter Betrag
            payment_date: Zahlungsdatum
            user_id: Benutzer-ID
            company_id: Firmen-ID (REQUIRED für Multi-Tenant)
            force_apply: Skonto auch nach Fristablauf anwenden (mit Warnung)

        Returns:
            Tuple: (skonto_applied, actual_amount, message)
        """
        from app.db.models import InvoiceTracking  # Lazy import

        # Invoice laden - SECURITY: company_id Filter für Multi-Tenant Isolation
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.id == invoice_tracking_id,
                InvoiceTracking.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            logger.warning(
                "apply_skonto_failed",
                invoice_id=str(invoice_tracking_id),
                company_id=str(company_id),
                reason="not_found_or_wrong_company",
            )
            return False, payment_amount, "Rechnung nicht gefunden"

        # Prüfen ob Skonto-Konditionen vorhanden
        if not invoice.skonto_percentage or invoice.skonto_percentage <= 0:
            return False, payment_amount, "Keine Skonto-Konditionen hinterlegt"

        # Prüfen ob Skonto bereits genutzt
        if invoice.skonto_used:
            return False, payment_amount, "Skonto wurde bereits angewendet"

        # Skonto-Frist prüfen
        skonto_deadline = invoice.skonto_deadline
        is_expired = payment_date > skonto_deadline if skonto_deadline else True

        if is_expired and not force_apply:
            return False, payment_amount, f"Skonto-Frist abgelaufen am {skonto_deadline.strftime('%d.%m.%Y')}"

        # Skonto berechnen
        skonto_amount = Decimal(str(invoice.amount)) * Decimal(str(invoice.skonto_percentage)) / Decimal("100")
        skonto_amount = skonto_amount.quantize(Decimal("0.01"))
        expected_amount = Decimal(str(invoice.amount)) - skonto_amount

        # Toleranz für Rundungsdifferenzen (5 Cent)
        tolerance = Decimal("0.05")
        if abs(Decimal(str(payment_amount)) - expected_amount) > tolerance:
            # Betrag stimmt nicht mit Skonto-Erwartung überein
            logger.warning(
                "Skonto-Zahlung weicht ab",
                invoice_id=str(invoice_tracking_id),
                expected=str(expected_amount),
                received=str(payment_amount),
            )

        # Skonto anwenden
        invoice.skonto_used = True
        invoice.paid_amount = float(payment_amount)
        invoice.paid_at = payment_date
        invoice.status = "paid"
        invoice.outstanding_amount = 0.0
        invoice.updated_at = utc_now()

        await db.flush()

        message = f"Skonto von {skonto_amount}EUR ({invoice.skonto_percentage}%) angewendet"
        if is_expired and force_apply:
            message += " (nach Fristablauf - manuell freigegeben)"

        logger.info(
            "Skonto angewendet",
            invoice_id=str(invoice_tracking_id),
            skonto_amount=str(skonto_amount),
            payment_amount=str(payment_amount),
        )

        return True, skonto_amount, message

    async def get_upcoming_skonto_deadlines(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 7,
        limit: int = 50,
    ) -> List[SkontoAlert]:
        """Hole anstehende Skonto-Fristen.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            days_ahead: Tage im Voraus
            limit: Maximale Anzahl

        Returns:
            Liste von SkontoAlerts sortiert nach Dringlichkeit
        """
        from app.db.models import InvoiceTracking, Document, BusinessEntity

        now = utc_now()
        deadline_cutoff = now + timedelta(days=days_ahead)

        # Query für Rechnungen mit anstehendem Skonto
        # Entity-Info kommt über Document.business_entity_id
        stmt = (
            select(InvoiceTracking, Document, BusinessEntity)
            .join(Document, InvoiceTracking.document_id == Document.id)
            .outerjoin(BusinessEntity, Document.business_entity_id == BusinessEntity.id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.skonto_deadline.isnot(None),
                    InvoiceTracking.skonto_deadline > now,
                    InvoiceTracking.skonto_deadline <= deadline_cutoff,
                    InvoiceTracking.skonto_used == False,
                    InvoiceTracking.status.in_(["open", "sent"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
            .order_by(InvoiceTracking.skonto_deadline.asc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        rows = result.all()

        alerts: List[SkontoAlert] = []
        for invoice, document, entity in rows:
            days_remaining = (invoice.skonto_deadline - now).days

            # Dringlichkeit bestimmen
            if days_remaining <= 1:
                urgency = "critical"
            elif days_remaining <= 3:
                urgency = "warning"
            else:
                urgency = "info"

            skonto_amount = Decimal(str(invoice.amount)) * Decimal(str(invoice.skonto_percentage)) / Decimal("100")

            alerts.append(SkontoAlert(
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number or document.original_filename,
                entity_name=entity.name if entity else "Unbekannt",
                skonto_deadline=invoice.skonto_deadline,
                skonto_amount=skonto_amount.quantize(Decimal("0.01")),
                days_remaining=days_remaining,
                urgency=urgency,
            ))

        return alerts

    async def get_skonto_statistics(
        self,
        db: AsyncSession,
        company_id: UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> SkontoStatistics:
        """Berechne Skonto-Statistiken für einen Zeitraum.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            start_date: Startdatum
            end_date: Enddatum

        Returns:
            SkontoStatistics
        """
        from app.db.models import InvoiceTracking

        # Alle Rechnungen im Zeitraum
        base_query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_date >= start_date,
                InvoiceTracking.invoice_date <= end_date,
                InvoiceTracking.deleted_at.is_(None),
            )
        )

        result = await db.execute(base_query)
        invoices = result.scalars().all()

        total_invoices = len(invoices)
        invoices_with_skonto = 0
        skonto_used_count = 0
        skonto_missed_count = 0
        skonto_pending_count = 0
        total_savings = Decimal("0.00")
        missed_savings = Decimal("0.00")
        potential_savings = Decimal("0.00")

        now = utc_now()

        for inv in invoices:
            if inv.skonto_percentage and inv.skonto_percentage > 0:
                invoices_with_skonto += 1
                skonto_amount = Decimal(str(inv.amount)) * Decimal(str(inv.skonto_percentage)) / Decimal("100")
                skonto_amount = skonto_amount.quantize(Decimal("0.01"))

                if inv.skonto_used:
                    skonto_used_count += 1
                    total_savings += skonto_amount
                elif inv.skonto_deadline and inv.skonto_deadline < now:
                    # Frist abgelaufen, nicht genutzt
                    skonto_missed_count += 1
                    missed_savings += skonto_amount
                else:
                    # Noch offen
                    skonto_pending_count += 1
                    potential_savings += skonto_amount

        usage_rate = (skonto_used_count / invoices_with_skonto * 100) if invoices_with_skonto > 0 else 0.0

        return SkontoStatistics(
            period_start=start_date,
            period_end=end_date,
            total_invoices=total_invoices,
            invoices_with_skonto=invoices_with_skonto,
            skonto_used_count=skonto_used_count,
            skonto_missed_count=skonto_missed_count,
            skonto_pending_count=skonto_pending_count,
            total_savings=total_savings,
            missed_savings=missed_savings,
            potential_savings=potential_savings,
            usage_rate=usage_rate,
        )

    async def update_invoice_skonto_fields(
        self,
        db: AsyncSession,
        invoice_tracking_id: UUID,
        company_id: UUID,
        skonto_percentage: Optional[float] = None,
        skonto_days: Optional[int] = None,
        net_days: Optional[int] = None,
    ) -> bool:
        """Aktualisiere Skonto-Felder einer Rechnung.

        SECURITY: company_id ist REQUIRED für Multi-Tenant Isolation.

        Berechnet automatisch skonto_deadline, skonto_amount, etc.

        Args:
            db: Datenbank-Session
            invoice_tracking_id: ID des Invoice-Trackings
            company_id: Firmen-ID (REQUIRED für Multi-Tenant)
            skonto_percentage: Skonto-Prozentsatz
            skonto_days: Tage für Skonto
            net_days: Zahlungsziel netto

        Returns:
            True bei Erfolg
        """
        from app.db.models import InvoiceTracking

        # SECURITY: company_id Filter für Multi-Tenant Isolation
        stmt = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.id == invoice_tracking_id,
                InvoiceTracking.company_id == company_id,
            )
        )
        result = await db.execute(stmt)
        invoice = result.scalar_one_or_none()

        if not invoice:
            logger.warning(
                "update_invoice_skonto_fields_failed",
                invoice_id=str(invoice_tracking_id),
                company_id=str(company_id),
                reason="not_found_or_wrong_company",
            )
            return False

        # Werte setzen
        if skonto_percentage is not None:
            invoice.skonto_percentage = skonto_percentage
        if skonto_days is not None:
            invoice.skonto_days = skonto_days
        if net_days is not None:
            invoice.net_days = net_days

        # Berechnete Felder aktualisieren
        if invoice.invoice_date and invoice.skonto_percentage and invoice.skonto_days:
            invoice.skonto_deadline = invoice.invoice_date + timedelta(days=invoice.skonto_days)
            invoice.skonto_amount = float(
                Decimal(str(invoice.amount)) * Decimal(str(invoice.skonto_percentage)) / Decimal("100")
            )

        if invoice.invoice_date and invoice.net_days:
            invoice.due_date = invoice.invoice_date + timedelta(days=invoice.net_days)

        invoice.updated_at = utc_now()
        await db.flush()

        logger.info(
            "Skonto-Felder aktualisiert",
            invoice_id=str(invoice_tracking_id),
            skonto_percentage=skonto_percentage,
            skonto_deadline=str(invoice.skonto_deadline) if invoice.skonto_deadline else None,
        )

        return True

    async def auto_detect_skonto_from_text(
        self,
        text: str,
    ) -> Optional[SkontoCondition]:
        """Erkenne Skonto-Konditionen aus OCR-Text.

        Typische Formulierungen:
        - "2% Skonto bei Zahlung innerhalb 10 Tagen"
        - "Zahlbar innerhalb 30 Tagen netto, 10 Tage 2% Skonto"
        - "Bei Zahlung bis zum ... gewähren wir 2% Skonto"

        Args:
            text: OCR-Text der Rechnung

        Returns:
            SkontoCondition wenn erkannt, sonst None
        """
        import re

        text_lower = text.lower()

        # Pattern für Prozent und Tage
        # "2% skonto" oder "2 % skonto" oder "2 prozent skonto"
        skonto_pattern = r"(\d+(?:[.,]\d+)?)\s*(?:%|prozent)?\s*skonto"
        days_pattern = r"(?:innerhalb|binnen|in)\s+(\d+)\s*(?:tage|tag)"
        netto_pattern = r"(?:netto|zahlungsziel|fällig)\s*(?:innerhalb)?\s*(\d+)\s*(?:tage|tag)"

        percentage = None
        skonto_days = None
        net_days = None

        # Skonto-Prozent suchen
        match = re.search(skonto_pattern, text_lower)
        if match:
            try:
                percentage = float(match.group(1).replace(",", "."))
            except ValueError as e:
                logger.debug("skonto_auto_detect_percentage_parse_failed", error_type=type(e).__name__, percentage_value=match.group(1))

        # Skonto-Tage suchen (im Kontext von Skonto)
        # Suche nach "skonto" und dann nach Tagen davor oder danach
        if "skonto" in text_lower:
            # Suche Tage im Umfeld von "skonto"
            skonto_context = text_lower[max(0, text_lower.find("skonto") - 100):text_lower.find("skonto") + 100]
            days_match = re.search(days_pattern, skonto_context)
            if days_match:
                try:
                    skonto_days = int(days_match.group(1))
                except ValueError as e:
                    logger.debug("skonto_auto_detect_days_parse_failed", error_type=type(e).__name__, days_value=days_match.group(1))

        # Netto-Zahlungsziel suchen
        netto_match = re.search(netto_pattern, text_lower)
        if netto_match:
            try:
                net_days = int(netto_match.group(1))
            except ValueError as e:
                logger.debug("skonto_auto_detect_net_days_parse_failed", error_type=type(e).__name__, net_days_value=netto_match.group(1))

        # Nur zurückgeben wenn mindestens Prozent gefunden
        if percentage and percentage > 0 and percentage < 10:  # Plausibilitaet
            return SkontoCondition(
                percentage=percentage,
                days=skonto_days or 10,  # Default 10 Tage
                net_days=net_days or 30,  # Default 30 Tage
            )

        return None
