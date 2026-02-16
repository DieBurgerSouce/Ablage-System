# -*- coding: utf-8 -*-
"""
Payment Behavior Report Service.

Analysiert das Zahlungsverhalten von Kunden:
- Durchschnittliche Zahldauer
- Puenktlichkeitsrate
- Zahlungsverzögerungs-Trends
- Problematische Kunden identifizieren
- Vergleich mit Branchendurchschnitt
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_, desc, asc, case, extract
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    BusinessEntity,
    Document,
    InvoiceTracking,
    EntityType,
    BankTransaction,
)
from app.core.datetime_utils import utc_now


logger = structlog.get_logger(__name__)


class PaymentBehaviorCategory(str, Enum):
    """Kategorisierung des Zahlungsverhaltens."""
    EXCELLENT = "excellent"      # Zahlt vor Fälligkeit
    PUNCTUAL = "punctual"        # Zahlt puenktlich
    DELAYED = "delayed"          # Zahlt verzögert (1-14 Tage)
    PROBLEMATIC = "problematic"  # Häufig stark verzögert
    DEFAULTER = "defaulter"      # Regelmäßige Ausfaelle


class PaymentTrend(str, Enum):
    """Trend des Zahlungsverhaltens."""
    IMPROVING = "improving"      # Wird besser
    STABLE = "stable"            # Gleichbleibend
    DECLINING = "declining"      # Wird schlechter


@dataclass
class PaymentMetrics:
    """Zahlungsmetriken für einen Kunden."""
    entity_id: UUID
    entity_name: str

    # Basis-Statistiken
    total_invoices: int
    paid_invoices: int
    unpaid_invoices: int
    overdue_invoices: int

    # Volumen
    total_volume: Decimal
    paid_volume: Decimal
    outstanding_volume: Decimal
    overdue_volume: Decimal

    # Zeitbasierte Metriken
    avg_payment_days: float  # Durchschnittliche Tage bis Zahlung
    min_payment_days: int
    max_payment_days: int
    median_payment_days: float

    # Verhalten
    punctuality_rate: float  # Anteil puenktlicher Zahlungen (0-1)
    early_payment_rate: float  # Anteil vorzeitiger Zahlungen
    late_payment_rate: float  # Anteil verspäteter Zahlungen
    default_rate: float  # Ausfallrate

    # Skonto
    skonto_utilization_rate: float  # Wie oft wird Skonto genutzt?
    skonto_saved: Decimal  # Eingesparter Betrag durch Skonto

    # Kategorisierung
    behavior_category: PaymentBehaviorCategory
    payment_trend: PaymentTrend

    # Score
    payment_score: float  # 0-100 (100 = bester Zahler)

    # Zeitraum
    first_invoice_date: Optional[date]
    last_invoice_date: Optional[date]
    analysis_period_days: int


@dataclass
class PaymentBehaviorSummary:
    """Zusammenfassung des Zahlungsverhaltens."""
    # Kategorien-Verteilung
    excellent_count: int = 0
    punctual_count: int = 0
    delayed_count: int = 0
    problematic_count: int = 0
    defaulter_count: int = 0

    # Durchschnittswerte
    avg_payment_days_overall: float = 0.0
    avg_punctuality_rate: float = 0.0
    avg_payment_score: float = 0.0

    # Volumen-Gewichtet
    volume_at_risk: Decimal = Decimal("0.00")  # Volumen bei problematischen Kunden
    overdue_total: Decimal = Decimal("0.00")

    # Trends
    improving_count: int = 0
    stable_count: int = 0
    declining_count: int = 0


@dataclass
class PaymentBehaviorReport:
    """Kompletter Report über Kunden-Zahlungsverhalten."""
    company_id: UUID

    # Übersicht
    total_customers: int
    analyzed_customers: int

    # Zusammenfassung
    summary: PaymentBehaviorSummary

    # Detaillierte Metriken
    customer_metrics: List[PaymentMetrics]

    # Spezielle Listen
    top_payers: List[PaymentMetrics]  # Beste Zahler
    worst_payers: List[PaymentMetrics]  # Schlechteste Zahler
    improving_customers: List[PaymentMetrics]
    declining_customers: List[PaymentMetrics]
    high_risk_customers: List[PaymentMetrics]  # Hohe Ausfallgefahr

    # Zeitraum
    analysis_period_start: date
    analysis_period_end: date

    # Vergleichswerte (Branche/Firma)
    benchmark_avg_payment_days: float = 30.0  # Branchendurchschnitt
    benchmark_punctuality_rate: float = 0.75  # 75% puenktlich ist Standard

    generated_at: datetime = field(default_factory=utc_now)


class PaymentBehaviorReportService:
    """
    Service zur Analyse des Kunden-Zahlungsverhaltens.

    Analysiert:
    - Historisches Zahlungsverhalten
    - Puenktlichkeitsraten
    - Zahlungstrends
    - Risikokunden identifizieren
    """

    # Schwellenwerte für Kategorisierung
    PUNCTUALITY_THRESHOLD = 3  # Tage Toleranz für "puenktlich"
    DELAYED_THRESHOLD = 14  # Bis 14 Tage = "verzögert"
    PROBLEMATIC_THRESHOLD = 0.3  # 30% verspätet = problematisch
    DEFAULT_THRESHOLD = 0.1  # 10% Ausfaelle = Defaulter

    # Scoring-Gewichte
    SCORE_WEIGHTS = {
        "punctuality": 0.35,
        "avg_delay": 0.25,
        "default_rate": 0.25,
        "skonto_usage": 0.15,
    }

    async def analyze_customer_payment_behavior(
        self,
        db: AsyncSession,
        entity_id: UUID,
        company_id: UUID,
        period_days: int = 365,
    ) -> Optional[PaymentMetrics]:
        """Analysiert Zahlungsverhalten eines einzelnen Kunden.

        Args:
            db: Datenbank-Session
            entity_id: Kunden-ID
            company_id: Firmen-ID
            period_days: Auswertungszeitraum

        Returns:
            PaymentMetrics oder None
        """
        # Kunde laden
        entity_result = await db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.entity_type == EntityType.CUSTOMER.value,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        customer = entity_result.scalar_one_or_none()

        if not customer:
            return None

        # Zeitraum
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        # Rechnungen laden
        invoices_result = await db.execute(
            select(InvoiceTracking).where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= start_date,
                )
            )
        )
        invoices = list(invoices_result.scalars().all())

        if not invoices:
            return None

        # Metriken berechnen
        return await self._calculate_metrics(
            customer, invoices, period_days
        )

    async def _calculate_metrics(
        self,
        customer: BusinessEntity,
        invoices: List[InvoiceTracking],
        period_days: int,
    ) -> PaymentMetrics:
        """Berechnet alle Zahlungsmetriken."""

        # Basis-Statistiken
        total_invoices = len(invoices)
        paid_invoices = sum(1 for inv in invoices if inv.status == "paid")
        unpaid_invoices = sum(1 for inv in invoices if inv.status not in ["paid", "cancelled"])
        overdue_invoices = sum(1 for inv in invoices if inv.is_overdue)

        # Volumen
        total_volume = sum(inv.total_amount or Decimal("0") for inv in invoices)
        paid_volume = sum(
            inv.total_amount or Decimal("0") for inv in invoices
            if inv.status == "paid"
        )
        outstanding_volume = sum(
            inv.outstanding_amount or Decimal("0") for inv in invoices
            if inv.status not in ["paid", "cancelled"]
        )
        overdue_volume = sum(
            inv.outstanding_amount or Decimal("0") for inv in invoices
            if inv.is_overdue
        )

        # Zahlungsdauer berechnen
        payment_days_list = []
        early_payments = 0
        late_payments = 0
        skonto_used = 0
        skonto_saved = Decimal("0")

        for inv in invoices:
            if inv.status == "paid" and inv.paid_date and inv.due_date:
                days = (inv.paid_date - inv.invoice_date).days
                payment_days_list.append(days)

                # Puenktlichkeit
                days_to_due = (inv.paid_date - inv.due_date).days
                if days_to_due <= -self.PUNCTUALITY_THRESHOLD:
                    early_payments += 1
                elif days_to_due > self.PUNCTUALITY_THRESHOLD:
                    late_payments += 1

                # Skonto
                if inv.discount_percent and inv.discount_date:
                    if inv.paid_date <= inv.discount_date:
                        skonto_used += 1
                        discount_amount = (
                            (inv.total_amount or Decimal("0")) *
                            Decimal(str(inv.discount_percent)) / 100
                        )
                        skonto_saved += discount_amount

        # Zeitbasierte Metriken
        if payment_days_list:
            avg_payment_days = sum(payment_days_list) / len(payment_days_list)
            min_payment_days = min(payment_days_list)
            max_payment_days = max(payment_days_list)
            sorted_days = sorted(payment_days_list)
            median_payment_days = sorted_days[len(sorted_days) // 2]
        else:
            avg_payment_days = 0.0
            min_payment_days = 0
            max_payment_days = 0
            median_payment_days = 0.0

        # Raten berechnen
        punctual_payments = paid_invoices - late_payments
        punctuality_rate = punctual_payments / paid_invoices if paid_invoices > 0 else 0.0
        early_payment_rate = early_payments / paid_invoices if paid_invoices > 0 else 0.0
        late_payment_rate = late_payments / paid_invoices if paid_invoices > 0 else 0.0

        # Default-Rate (überfällig > 90 Tage)
        severe_overdue = sum(
            1 for inv in invoices
            if inv.is_overdue and inv.days_overdue and inv.days_overdue > 90
        )
        default_rate = severe_overdue / total_invoices if total_invoices > 0 else 0.0

        # Skonto-Nutzung
        skonto_invoices = sum(1 for inv in invoices if inv.discount_percent and inv.discount_percent > 0)
        skonto_utilization_rate = skonto_used / skonto_invoices if skonto_invoices > 0 else 0.0

        # Kategorisierung
        behavior_category = self._categorize_behavior(
            punctuality_rate, late_payment_rate, default_rate
        )

        # Trend berechnen (vereinfacht - Vergleich letzte 3 Monate vs vorherige)
        payment_trend = await self._calculate_trend(invoices)

        # Score berechnen
        payment_score = self._calculate_payment_score(
            punctuality_rate, avg_payment_days, default_rate, skonto_utilization_rate
        )

        # Datumsgrenzen
        invoice_dates = [inv.invoice_date for inv in invoices if inv.invoice_date]
        first_invoice = min(invoice_dates) if invoice_dates else None
        last_invoice = max(invoice_dates) if invoice_dates else None

        return PaymentMetrics(
            entity_id=customer.id,
            entity_name=customer.name,
            total_invoices=total_invoices,
            paid_invoices=paid_invoices,
            unpaid_invoices=unpaid_invoices,
            overdue_invoices=overdue_invoices,
            total_volume=total_volume,
            paid_volume=paid_volume,
            outstanding_volume=outstanding_volume,
            overdue_volume=overdue_volume,
            avg_payment_days=round(avg_payment_days, 1),
            min_payment_days=min_payment_days,
            max_payment_days=max_payment_days,
            median_payment_days=median_payment_days,
            punctuality_rate=round(punctuality_rate, 3),
            early_payment_rate=round(early_payment_rate, 3),
            late_payment_rate=round(late_payment_rate, 3),
            default_rate=round(default_rate, 3),
            skonto_utilization_rate=round(skonto_utilization_rate, 3),
            skonto_saved=skonto_saved,
            behavior_category=behavior_category,
            payment_trend=payment_trend,
            payment_score=round(payment_score, 1),
            first_invoice_date=first_invoice,
            last_invoice_date=last_invoice,
            analysis_period_days=period_days,
        )

    def _categorize_behavior(
        self,
        punctuality_rate: float,
        late_rate: float,
        default_rate: float,
    ) -> PaymentBehaviorCategory:
        """Kategorisiert Zahlungsverhalten."""
        if default_rate >= self.DEFAULT_THRESHOLD:
            return PaymentBehaviorCategory.DEFAULTER
        elif late_rate >= self.PROBLEMATIC_THRESHOLD:
            return PaymentBehaviorCategory.PROBLEMATIC
        elif late_rate > 0.1:  # Mehr als 10% verspätet
            return PaymentBehaviorCategory.DELAYED
        elif punctuality_rate >= 0.95:
            return PaymentBehaviorCategory.EXCELLENT
        else:
            return PaymentBehaviorCategory.PUNCTUAL

    async def _calculate_trend(
        self,
        invoices: List[InvoiceTracking],
    ) -> PaymentTrend:
        """Berechnet Zahlungstrend."""
        if len(invoices) < 4:
            return PaymentTrend.STABLE

        # Sortieren nach Datum
        sorted_invoices = sorted(
            [inv for inv in invoices if inv.invoice_date],
            key=lambda x: x.invoice_date
        )

        # Teilen in erste und zweite Haelfte
        mid = len(sorted_invoices) // 2
        older = sorted_invoices[:mid]
        newer = sorted_invoices[mid:]

        # Verspätungsraten vergleichen
        def calc_late_rate(invs):
            paid = [i for i in invs if i.status == "paid" and i.paid_date and i.due_date]
            if not paid:
                return 0.5
            late = sum(1 for i in paid if i.paid_date > i.due_date)
            return late / len(paid)

        older_late = calc_late_rate(older)
        newer_late = calc_late_rate(newer)

        if newer_late < older_late - 0.1:
            return PaymentTrend.IMPROVING
        elif newer_late > older_late + 0.1:
            return PaymentTrend.DECLINING
        else:
            return PaymentTrend.STABLE

    def _calculate_payment_score(
        self,
        punctuality_rate: float,
        avg_payment_days: float,
        default_rate: float,
        skonto_rate: float,
    ) -> float:
        """Berechnet Zahlungs-Score (0-100)."""
        # Puenktlichkeit (0-100)
        punctuality_score = punctuality_rate * 100

        # Zahlungsdauer-Score (30 Tage = 100, 60+ Tage = 0)
        delay_score = max(0, 100 - ((avg_payment_days - 30) * 2.5))
        delay_score = min(100, delay_score)

        # Default-Score (0% = 100, 10%+ = 0)
        default_score = max(0, 100 - (default_rate * 1000))

        # Skonto-Bonus
        skonto_score = skonto_rate * 100

        # Gewichteter Score
        score = (
            punctuality_score * self.SCORE_WEIGHTS["punctuality"] +
            delay_score * self.SCORE_WEIGHTS["avg_delay"] +
            default_score * self.SCORE_WEIGHTS["default_rate"] +
            skonto_score * self.SCORE_WEIGHTS["skonto_usage"]
        )

        return max(0, min(100, score))

    # -------------------------------------------------------------------------
    # Report-Generierung
    # -------------------------------------------------------------------------

    async def generate_payment_behavior_report(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_days: int = 365,
        top_n: int = 10,
    ) -> PaymentBehaviorReport:
        """Generiert kompletten Zahlungsverhaltens-Report.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            period_days: Auswertungszeitraum
            top_n: Anzahl Top/Bottom Kunden

        Returns:
            PaymentBehaviorReport
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        # Alle Kunden laden
        customers_result = await db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.entity_type == EntityType.CUSTOMER.value,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        customers = customers_result.scalars().all()

        total_customers = len(customers)

        # Metriken für alle Kunden berechnen
        all_metrics: List[PaymentMetrics] = []
        for customer in customers:
            metrics = await self.analyze_customer_payment_behavior(
                db, customer.id, company_id, period_days
            )
            if metrics and metrics.total_invoices > 0:
                all_metrics.append(metrics)

        # Zusammenfassung erstellen
        summary = PaymentBehaviorSummary()

        for m in all_metrics:
            # Kategorien zaehlen
            if m.behavior_category == PaymentBehaviorCategory.EXCELLENT:
                summary.excellent_count += 1
            elif m.behavior_category == PaymentBehaviorCategory.PUNCTUAL:
                summary.punctual_count += 1
            elif m.behavior_category == PaymentBehaviorCategory.DELAYED:
                summary.delayed_count += 1
            elif m.behavior_category == PaymentBehaviorCategory.PROBLEMATIC:
                summary.problematic_count += 1
                summary.volume_at_risk += m.total_volume
            elif m.behavior_category == PaymentBehaviorCategory.DEFAULTER:
                summary.defaulter_count += 1
                summary.volume_at_risk += m.total_volume

            # Trends zaehlen
            if m.payment_trend == PaymentTrend.IMPROVING:
                summary.improving_count += 1
            elif m.payment_trend == PaymentTrend.STABLE:
                summary.stable_count += 1
            elif m.payment_trend == PaymentTrend.DECLINING:
                summary.declining_count += 1

            # Überfällig
            summary.overdue_total += m.overdue_volume

        # Durchschnitte
        if all_metrics:
            summary.avg_payment_days_overall = (
                sum(m.avg_payment_days for m in all_metrics) / len(all_metrics)
            )
            summary.avg_punctuality_rate = (
                sum(m.punctuality_rate for m in all_metrics) / len(all_metrics)
            )
            summary.avg_payment_score = (
                sum(m.payment_score for m in all_metrics) / len(all_metrics)
            )

        # Sortierte Listen
        sorted_by_score = sorted(all_metrics, key=lambda m: m.payment_score, reverse=True)
        top_payers = sorted_by_score[:top_n]
        worst_payers = sorted_by_score[-top_n:] if len(sorted_by_score) >= top_n else sorted_by_score[::-1]

        improving = [m for m in all_metrics if m.payment_trend == PaymentTrend.IMPROVING][:top_n]
        declining = [m for m in all_metrics if m.payment_trend == PaymentTrend.DECLINING][:top_n]

        high_risk = [
            m for m in all_metrics
            if m.behavior_category in [
                PaymentBehaviorCategory.PROBLEMATIC,
                PaymentBehaviorCategory.DEFAULTER
            ]
        ]
        high_risk.sort(key=lambda m: m.overdue_volume, reverse=True)

        report = PaymentBehaviorReport(
            company_id=company_id,
            total_customers=total_customers,
            analyzed_customers=len(all_metrics),
            summary=summary,
            customer_metrics=all_metrics,
            top_payers=top_payers,
            worst_payers=worst_payers,
            improving_customers=improving,
            declining_customers=declining,
            high_risk_customers=high_risk[:top_n],
            analysis_period_start=start_date,
            analysis_period_end=end_date,
        )

        logger.info(
            "payment_behavior_report_generated",
            company_id=str(company_id),
            total_customers=total_customers,
            analyzed_customers=len(all_metrics),
        )

        return report

    async def get_customer_ranking_by_payment(
        self,
        db: AsyncSession,
        company_id: UUID,
        period_days: int = 365,
        limit: int = 50,
        sort_by: str = "payment_score",
        sort_desc: bool = True,
    ) -> List[PaymentMetrics]:
        """Ruft Kunden-Ranking nach Zahlungsverhalten ab.

        Args:
            db: Datenbank-Session
            company_id: Firmen-ID
            period_days: Auswertungszeitraum
            limit: Max. Anzahl Ergebnisse
            sort_by: Sortierfeld (payment_score, avg_payment_days, punctuality_rate, total_volume)
            sort_desc: Absteigend sortieren

        Returns:
            Liste von PaymentMetrics
        """
        # Alle Kunden analysieren
        customers_result = await db.execute(
            select(BusinessEntity).where(
                and_(
                    BusinessEntity.entity_type == EntityType.CUSTOMER.value,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        customers = customers_result.scalars().all()

        all_metrics: List[PaymentMetrics] = []
        for customer in customers:
            metrics = await self.analyze_customer_payment_behavior(
                db, customer.id, company_id, period_days
            )
            if metrics and metrics.total_invoices > 0:
                all_metrics.append(metrics)

        # Sortieren
        if sort_by == "avg_payment_days":
            all_metrics.sort(key=lambda m: m.avg_payment_days, reverse=sort_desc)
        elif sort_by == "punctuality_rate":
            all_metrics.sort(key=lambda m: m.punctuality_rate, reverse=sort_desc)
        elif sort_by == "total_volume":
            all_metrics.sort(key=lambda m: m.total_volume, reverse=sort_desc)
        elif sort_by == "overdue_volume":
            all_metrics.sort(key=lambda m: m.overdue_volume, reverse=sort_desc)
        else:
            all_metrics.sort(key=lambda m: m.payment_score, reverse=sort_desc)

        return all_metrics[:limit]


# =============================================================================
# Singleton
# =============================================================================

_payment_behavior_service: Optional[PaymentBehaviorReportService] = None


def get_payment_behavior_report_service() -> PaymentBehaviorReportService:
    """Gibt Payment-Behavior-Report-Service-Instanz zurück."""
    global _payment_behavior_service
    if _payment_behavior_service is None:
        _payment_behavior_service = PaymentBehaviorReportService()
    return _payment_behavior_service
