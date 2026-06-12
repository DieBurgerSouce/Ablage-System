# -*- coding: utf-8 -*-
"""
Skonto Optimizer Service - Intelligente Zahlungsempfehlungen.

Enterprise Feature: KI-basierte Optimierung von Skonto-Nutzung.

Features:
- Priorisierung nach ROI (Skonto-Ersparnis vs. Liquiditaetskosten)
- Cash-Buffer Berücksichtigung
- Batch-Zahlungsvorschläge
- Seasonal Payment Planning
- Vendor Payment Terms Learning

Vision: "Soll ich diese Rechnung heute bezahlen um 2% zu sparen?"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    InvoiceTracking,
    BankAccount,
    BankTransaction,
    BusinessEntity,
)
from app.services.invoice_direction import (
    is_incoming_invoice,
    is_open_invoice,
    is_outgoing_invoice,
)
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

SKONTO_RECOMMENDATIONS_GENERATED = Counter(
    "skonto_recommendations_generated_total",
    "Total skonto recommendations generated",
    ["company_id", "recommendation_type"]
)

SKONTO_POTENTIAL_SAVINGS = Gauge(
    "skonto_potential_savings_eur",
    "Potential savings from skonto in EUR",
    ["company_id"]
)

SKONTO_OPTIMIZATION_TIME = Histogram(
    "skonto_optimization_duration_seconds",
    "Time to generate skonto recommendations",
    ["company_id"]
)


# =============================================================================
# Enums
# =============================================================================

class RecommendationType(str, Enum):
    """Typ der Zahlungsempfehlung."""
    PAY_NOW = "pay_now"           # Sofort zahlen (Skonto nutzen)
    PAY_LATER = "pay_later"       # Später zahlen (Liquiditaet priorisieren)
    BATCH_PAYMENT = "batch_payment"  # Sammelzahlung am optimalen Tag
    NEGOTIATE = "negotiate"       # Bessere Konditionen verhandeln
    REVIEW = "review"             # Manuelle Prüfung empfohlen


class Priority(str, Enum):
    """Priorität der Empfehlung."""
    CRITICAL = "critical"   # Frist laeuft ab
    HIGH = "high"           # Hohe Ersparnis
    MEDIUM = "medium"       # Moderate Ersparnis
    LOW = "low"             # Geringe Ersparnis


class LiquidityImpact(str, Enum):
    """Auswirkung auf Liquiditaet."""
    POSITIVE = "positive"   # Liquiditaet verbessert sich
    NEUTRAL = "neutral"     # Kein wesentlicher Einfluss
    NEGATIVE = "negative"   # Liquiditaet verschlechtert sich
    CRITICAL = "critical"   # Kritische Liquiditaetssituation


# =============================================================================
# TypedDicts
# =============================================================================

class SkontoInvoiceDict(TypedDict):
    """Rechnung mit Skonto-Details."""
    invoice_id: str
    entity_id: Optional[str]
    entity_name: str
    amount: float
    outstanding_amount: float
    skonto_percentage: float
    skonto_amount: float
    skonto_deadline: str
    due_date: str
    days_until_skonto: int
    days_until_due: int


class RecommendationDict(TypedDict):
    """Zahlungsempfehlung."""
    id: str
    recommendation_type: str
    priority: str
    title: str
    summary: str
    detail: str
    invoices: List[SkontoInvoiceDict]
    total_amount: float
    total_savings: float
    roi_percent: float
    recommended_pay_date: str
    liquidity_impact: str
    confidence: float
    reasoning: List[str]


class OptimizationResultDict(TypedDict):
    """Ergebnis der Skonto-Optimierung."""
    company_id: str
    generated_at: str
    total_skonto_eligible: int
    total_potential_savings: float
    current_balance: float
    optimal_payment_schedule: List[RecommendationDict]
    summary_by_priority: Dict[str, int]
    liquidity_forecast: Dict[str, float]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SkontoInvoice:
    """Rechnung mit Skonto-Möglichkeit."""
    invoice_id: UUID
    entity_id: Optional[UUID]
    entity_name: str
    amount: Decimal
    outstanding_amount: Decimal
    skonto_percentage: Decimal  # z.B. 2.0 für 2%
    skonto_amount: Decimal
    skonto_deadline: datetime
    due_date: datetime
    days_until_skonto: int
    days_until_due: int

    def to_dict(self) -> SkontoInvoiceDict:
        """Konvertiert zu Dictionary."""
        return SkontoInvoiceDict(
            invoice_id=str(self.invoice_id),
            entity_id=str(self.entity_id) if self.entity_id else None,
            entity_name=self.entity_name,
            amount=float(self.amount),
            outstanding_amount=float(self.outstanding_amount),
            skonto_percentage=float(self.skonto_percentage),
            skonto_amount=float(self.skonto_amount),
            skonto_deadline=self.skonto_deadline.isoformat(),
            due_date=self.due_date.isoformat(),
            days_until_skonto=self.days_until_skonto,
            days_until_due=self.days_until_due,
        )


@dataclass
class PaymentRecommendation:
    """Zahlungsempfehlung."""
    id: UUID = field(default_factory=uuid4)
    recommendation_type: RecommendationType = RecommendationType.PAY_NOW
    priority: Priority = Priority.MEDIUM
    title: str = ""
    summary: str = ""
    detail: str = ""
    invoices: List[SkontoInvoice] = field(default_factory=list)
    total_amount: Decimal = Decimal("0")
    total_savings: Decimal = Decimal("0")
    roi_percent: float = 0.0
    recommended_pay_date: Optional[datetime] = None
    liquidity_impact: LiquidityImpact = LiquidityImpact.NEUTRAL
    confidence: float = 0.7
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> RecommendationDict:
        """Konvertiert zu Dictionary."""
        return RecommendationDict(
            id=str(self.id),
            recommendation_type=self.recommendation_type.value,
            priority=self.priority.value,
            title=self.title,
            summary=self.summary,
            detail=self.detail,
            invoices=[inv.to_dict() for inv in self.invoices],
            total_amount=float(self.total_amount),
            total_savings=float(self.total_savings),
            roi_percent=self.roi_percent,
            recommended_pay_date=self.recommended_pay_date.isoformat() if self.recommended_pay_date else "",
            liquidity_impact=self.liquidity_impact.value,
            confidence=self.confidence,
            reasoning=self.reasoning,
        )


@dataclass
class OptimizationResult:
    """Ergebnis der Skonto-Optimierung."""
    company_id: UUID
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    total_skonto_eligible: int = 0
    total_potential_savings: Decimal = Decimal("0")
    current_balance: Decimal = Decimal("0")
    optimal_payment_schedule: List[PaymentRecommendation] = field(default_factory=list)
    summary_by_priority: Dict[str, int] = field(default_factory=dict)
    liquidity_forecast: Dict[str, Decimal] = field(default_factory=dict)

    def to_dict(self) -> OptimizationResultDict:
        """Konvertiert zu Dictionary."""
        return OptimizationResultDict(
            company_id=str(self.company_id),
            generated_at=self.generated_at.isoformat(),
            total_skonto_eligible=self.total_skonto_eligible,
            total_potential_savings=float(self.total_potential_savings),
            current_balance=float(self.current_balance),
            optimal_payment_schedule=[rec.to_dict() for rec in self.optimal_payment_schedule],
            summary_by_priority=self.summary_by_priority,
            liquidity_forecast={k: float(v) for k, v in self.liquidity_forecast.items()},
        )


# =============================================================================
# Skonto Optimizer Service
# =============================================================================

class SkontoOptimizer:
    """
    KI-basierter Skonto-Optimierer.

    Analysiert offene Rechnungen mit Skonto-Möglichkeit und
    erstellt optimierte Zahlungsvorschläge basierend auf:
    - Liquiditaetslage
    - ROI der Skonto-Nutzung
    - Vendor-Beziehungen
    - Saisonale Muster
    """

    # Konfiguration
    MIN_SKONTO_PERCENTAGE = Decimal("0.5")  # Mindestens 0.5% Skonto
    ANNUALIZED_ROI_THRESHOLD = 15.0  # 15% annualisierter ROI = lohnenswert
    SAFETY_BUFFER_DAYS = 2  # Sicherheitspuffer für Zahlung
    LIQUIDITY_SAFETY_FACTOR = 1.5  # 1.5x Monat Reserve halten

    def __init__(self) -> None:
        """Initialisiert den Optimizer."""
        self._entity_payment_history: Dict[UUID, Dict[str, Any]] = {}

    async def optimize(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int = 14,
        min_savings: Decimal = Decimal("10"),
    ) -> OptimizationResult:
        """
        Optimiert Skonto-Nutzung.

        Args:
            db: Database Session
            company_id: Company-ID
            days_ahead: Prognose-Horizont
            min_savings: Mindest-Ersparnis pro Rechnung

        Returns:
            OptimizationResult mit Zahlungsempfehlungen
        """
        import time
        start_time = time.perf_counter()

        logger.info(
            "starting_skonto_optimization",
            company_id=str(company_id),
            days_ahead=days_ahead,
        )

        # 1. Aktuelle Liquiditaet laden
        current_balance = await self._get_current_balance(db, company_id)

        # 2. Skonto-fähige Rechnungen laden
        skonto_invoices = await self._get_skonto_invoices(db, company_id, days_ahead)

        # 3. Erwartete Ein-/Ausgaenge für Liquiditaetsprognose
        expected_inflows = await self._get_expected_inflows(db, company_id, days_ahead)
        expected_outflows = await self._get_expected_outflows(db, company_id, days_ahead)

        # 4. Optimale Zahlungsstrategie berechnen
        recommendations = await self._calculate_optimal_strategy(
            current_balance=current_balance,
            invoices=skonto_invoices,
            expected_inflows=expected_inflows,
            expected_outflows=expected_outflows,
            min_savings=min_savings,
        )

        # 5. Batch-Zahlungen identifizieren
        batch_recommendations = self._identify_batch_payments(recommendations)

        # 6. Ergebnis zusammenstellen
        all_recommendations = recommendations + batch_recommendations

        # Statistiken
        total_savings = sum(r.total_savings for r in all_recommendations)
        by_priority = {}
        for rec in all_recommendations:
            by_priority[rec.priority.value] = by_priority.get(rec.priority.value, 0) + 1

        # Liquiditaetsprognose
        liquidity_forecast = self._forecast_liquidity(
            current_balance=current_balance,
            recommendations=all_recommendations,
            expected_inflows=expected_inflows,
            expected_outflows=expected_outflows,
            days_ahead=days_ahead,
        )

        duration = time.perf_counter() - start_time

        SKONTO_OPTIMIZATION_TIME.labels(company_id=str(company_id)).observe(duration)
        SKONTO_POTENTIAL_SAVINGS.labels(company_id=str(company_id)).set(float(total_savings))

        for rec in all_recommendations:
            SKONTO_RECOMMENDATIONS_GENERATED.labels(
                company_id=str(company_id),
                recommendation_type=rec.recommendation_type.value,
            ).inc()

        logger.info(
            "skonto_optimization_completed",
            company_id=str(company_id),
            total_invoices=len(skonto_invoices),
            total_recommendations=len(all_recommendations),
            total_potential_savings=float(total_savings),
            duration_seconds=duration,
        )

        return OptimizationResult(
            company_id=company_id,
            total_skonto_eligible=len(skonto_invoices),
            total_potential_savings=total_savings,
            current_balance=current_balance,
            optimal_payment_schedule=all_recommendations,
            summary_by_priority=by_priority,
            liquidity_forecast=liquidity_forecast,
        )

    async def _get_current_balance(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Decimal:
        """Laedt aktuellen Kontostand."""
        # Company-Scope via BankAccount-JOIN (BankTransaction hat KEINE
        # company_id-Spalte)
        query = (
            select(func.coalesce(func.sum(BankTransaction.amount), 0))
            .select_from(BankTransaction)
            .join(BankAccount, BankTransaction.bank_account_id == BankAccount.id)
            .where(BankAccount.company_id == company_id)
        )

        result = await db.execute(query)
        return Decimal(str(result.scalar_one_or_none() or 0))

    async def _get_skonto_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int,
    ) -> List[SkontoInvoice]:
        """Laedt Rechnungen mit Skonto-Möglichkeit."""
        now = datetime.now(timezone.utc)
        deadline_cutoff = now + timedelta(days=days_ahead)

        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                # "pending" existiert nicht in InvoiceStatus — offene
                # Rechnungen via Status-Allowlist (invoice_direction.py)
                is_open_invoice(),
                InvoiceTracking.skonto_percentage.isnot(None),
                InvoiceTracking.skonto_percentage >= self.MIN_SKONTO_PERCENTAGE,
                InvoiceTracking.skonto_deadline.isnot(None),
                InvoiceTracking.skonto_deadline <= deadline_cutoff,
                InvoiceTracking.skonto_deadline >= now,  # Nicht abgelaufen
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        skonto_invoices = []
        for inv in invoices:
            outstanding = inv.outstanding_amount or inv.amount
            skonto_pct = Decimal(str(inv.skonto_percentage or 0))
            skonto_amount = outstanding * (skonto_pct / Decimal("100"))

            days_until_skonto = (inv.skonto_deadline - now).days if inv.skonto_deadline else 0
            days_until_due = (inv.due_date - now).days if inv.due_date else 30

            # Entity-Name laden
            entity_name = "Unbekannt"
            if inv.entity:
                entity_name = inv.entity.name or "Unbekannt"

            skonto_invoices.append(SkontoInvoice(
                invoice_id=inv.id,
                entity_id=inv.entity_id,
                entity_name=entity_name,
                amount=inv.amount,
                outstanding_amount=outstanding,
                skonto_percentage=skonto_pct,
                skonto_amount=skonto_amount,
                skonto_deadline=inv.skonto_deadline,
                due_date=inv.due_date or (now + timedelta(days=30)),
                days_until_skonto=days_until_skonto,
                days_until_due=days_until_due,
            ))

        # Sortieren nach Skonto-Deadline
        skonto_invoices.sort(key=lambda x: x.skonto_deadline)

        return skonto_invoices

    async def _get_expected_inflows(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int,
    ) -> Dict[datetime, Decimal]:
        """Laedt erwartete Zahlungseingaenge."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_ahead)

        # Erwartete Zahlungen von Kunden (offene Forderungen)
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                # Richtungs-Kommentar war vertauscht: Forderung = Kunde
                # = Ausgangsrechnung (siehe app/services/invoice_direction.py)
                is_outgoing_invoice(),  # Forderung
                is_open_invoice(),
                InvoiceTracking.due_date.isnot(None),
                InvoiceTracking.due_date <= cutoff,
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        inflows: Dict[datetime, Decimal] = {}

        for inv in invoices:
            # Zahlungswahrscheinlichkeit schätzen (vereinfacht: 70%)
            expected_amount = (inv.outstanding_amount or inv.amount) * Decimal("0.7")
            date_key = inv.due_date.replace(hour=0, minute=0, second=0, microsecond=0)

            if date_key not in inflows:
                inflows[date_key] = Decimal("0")
            inflows[date_key] += expected_amount

        return inflows

    async def _get_expected_outflows(
        self,
        db: AsyncSession,
        company_id: UUID,
        days_ahead: int,
    ) -> Dict[datetime, Decimal]:
        """Laedt erwartete Zahlungsausgaenge (ohne Skonto-Rechnungen)."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_ahead)

        # Andere fällige Verbindlichkeiten
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                # Richtungs-Kommentar war vertauscht: Verbindlichkeit =
                # Lieferant = Eingangsrechnung
                is_incoming_invoice(),  # Verbindlichkeit
                is_open_invoice(),
                InvoiceTracking.due_date.isnot(None),
                InvoiceTracking.due_date <= cutoff,
                or_(
                    InvoiceTracking.skonto_percentage.is_(None),
                    InvoiceTracking.skonto_percentage < self.MIN_SKONTO_PERCENTAGE,
                ),
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        outflows: Dict[datetime, Decimal] = {}

        for inv in invoices:
            date_key = inv.due_date.replace(hour=0, minute=0, second=0, microsecond=0)

            if date_key not in outflows:
                outflows[date_key] = Decimal("0")
            outflows[date_key] += (inv.outstanding_amount or inv.amount)

        return outflows

    async def _calculate_optimal_strategy(
        self,
        current_balance: Decimal,
        invoices: List[SkontoInvoice],
        expected_inflows: Dict[datetime, Decimal],
        expected_outflows: Dict[datetime, Decimal],
        min_savings: Decimal,
    ) -> List[PaymentRecommendation]:
        """Berechnet optimale Zahlungsstrategie."""
        recommendations = []
        available_balance = current_balance

        # Sortieren nach ROI (annualisiert)
        invoices_with_roi = []
        for inv in invoices:
            # Annualisierter ROI: (Skonto% / Tage bis Frist) * 365
            days_saved = inv.days_until_due - inv.days_until_skonto
            if days_saved > 0:
                annualized_roi = (float(inv.skonto_percentage) / days_saved) * 365
            else:
                annualized_roi = float(inv.skonto_percentage) * 365 / 30  # Default 30 Tage

            invoices_with_roi.append((inv, annualized_roi))

        # Nach ROI sortieren (hoechster zuerst)
        invoices_with_roi.sort(key=lambda x: x[1], reverse=True)

        for inv, annualized_roi in invoices_with_roi:
            # Prüfen ob Ersparnis Minimum erreicht
            if inv.skonto_amount < min_savings:
                continue

            # Prüfen ob genuegend Liquiditaet
            net_amount = inv.outstanding_amount - inv.skonto_amount
            projected_balance = self._project_balance_at_date(
                current_balance=available_balance,
                target_date=inv.skonto_deadline,
                expected_inflows=expected_inflows,
                expected_outflows=expected_outflows,
            )

            # Liquiditaetsreserve berechnen (monatliche Ausgaben als Basis)
            total_monthly_outflow = sum(expected_outflows.values()) if expected_outflows else Decimal("10000")
            safety_reserve = total_monthly_outflow * Decimal(str(self.LIQUIDITY_SAFETY_FACTOR))

            # Recommendation erstellen
            if inv.days_until_skonto <= 0:
                # Frist bereits abgelaufen
                continue
            elif inv.days_until_skonto <= 2:
                # Dringend (1-2 Tage)
                priority = Priority.CRITICAL
            elif annualized_roi >= self.ANNUALIZED_ROI_THRESHOLD:
                priority = Priority.HIGH
            elif annualized_roi >= self.ANNUALIZED_ROI_THRESHOLD / 2:
                priority = Priority.MEDIUM
            else:
                priority = Priority.LOW

            # Liquiditaetsauswirkung
            remaining_after_payment = projected_balance - net_amount
            if remaining_after_payment < Decimal("0"):
                liquidity_impact = LiquidityImpact.CRITICAL
                rec_type = RecommendationType.PAY_LATER
                reasoning = [
                    "Zahlung wuerde zu negativem Saldo führen",
                    f"Verfügbar: {float(projected_balance):,.2f} EUR, Benötigt: {float(net_amount):,.2f} EUR",
                ]
            elif remaining_after_payment < safety_reserve:
                liquidity_impact = LiquidityImpact.NEGATIVE
                if annualized_roi >= self.ANNUALIZED_ROI_THRESHOLD * 2:
                    # Sehr hoher ROI rechtfertigt Risiko
                    rec_type = RecommendationType.PAY_NOW
                    reasoning = [
                        f"Hoher annualisierter ROI von {annualized_roi:.0f}% rechtfertigt Zahlung",
                        f"Liquiditaetsreserve wird unterschritten ({float(remaining_after_payment):,.2f} EUR < {float(safety_reserve):,.2f} EUR)",
                    ]
                else:
                    rec_type = RecommendationType.REVIEW
                    reasoning = [
                        "Liquiditaetsreserve wird unterschritten",
                        "Manuelle Prüfung empfohlen",
                    ]
            else:
                liquidity_impact = LiquidityImpact.NEUTRAL
                rec_type = RecommendationType.PAY_NOW
                reasoning = [
                    f"Annualisierter ROI: {annualized_roi:.0f}%",
                    f"Ersparnis: {float(inv.skonto_amount):,.2f} EUR ({float(inv.skonto_percentage):.1f}%)",
                    f"Ausreichend Liquiditaet vorhanden",
                ]

            # Pay-Date berechnen (Frist - Sicherheitspuffer)
            recommended_pay_date = inv.skonto_deadline - timedelta(days=self.SAFETY_BUFFER_DAYS)
            if recommended_pay_date < datetime.now(timezone.utc):
                recommended_pay_date = datetime.now(timezone.utc)

            recommendations.append(PaymentRecommendation(
                recommendation_type=rec_type,
                priority=priority,
                title=f"Skonto {float(inv.skonto_percentage):.1f}% - {inv.entity_name}",
                summary=f"Sparen Sie {float(inv.skonto_amount):,.2f} EUR bei Zahlung bis {inv.skonto_deadline.strftime('%d.%m.%Y')}",
                detail=f"Rechnung {float(inv.outstanding_amount):,.2f} EUR, Netto: {float(net_amount):,.2f} EUR",
                invoices=[inv],
                total_amount=net_amount,
                total_savings=inv.skonto_amount,
                roi_percent=annualized_roi,
                recommended_pay_date=recommended_pay_date,
                liquidity_impact=liquidity_impact,
                confidence=0.85 if liquidity_impact != LiquidityImpact.CRITICAL else 0.6,
                reasoning=reasoning,
            ))

            # Balance für weitere Berechnungen aktualisieren (wenn PAY_NOW)
            if rec_type == RecommendationType.PAY_NOW:
                available_balance -= net_amount

        return recommendations

    def _project_balance_at_date(
        self,
        current_balance: Decimal,
        target_date: datetime,
        expected_inflows: Dict[datetime, Decimal],
        expected_outflows: Dict[datetime, Decimal],
    ) -> Decimal:
        """Projiziert Kontostand zu einem bestimmten Datum."""
        balance = current_balance
        target_date_normalized = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Eingaenge addieren
        for date, amount in expected_inflows.items():
            if date <= target_date_normalized:
                balance += amount

        # Ausgaenge subtrahieren
        for date, amount in expected_outflows.items():
            if date <= target_date_normalized:
                balance -= amount

        return balance

    def _identify_batch_payments(
        self,
        recommendations: List[PaymentRecommendation],
    ) -> List[PaymentRecommendation]:
        """Identifiziert Möglichkeiten für Sammelzahlungen."""
        batch_recommendations = []

        # Gruppieren nach Zahlungsdatum
        by_date: Dict[str, List[PaymentRecommendation]] = {}

        for rec in recommendations:
            if rec.recommendation_type == RecommendationType.PAY_NOW and rec.recommended_pay_date:
                date_key = rec.recommended_pay_date.strftime("%Y-%m-%d")
                if date_key not in by_date:
                    by_date[date_key] = []
                by_date[date_key].append(rec)

        # Batch-Empfehlungen für Tage mit >1 Zahlung
        for date_key, recs in by_date.items():
            if len(recs) > 1:
                total_amount = sum(r.total_amount for r in recs)
                total_savings = sum(r.total_savings for r in recs)
                all_invoices = [inv for r in recs for inv in r.invoices]

                batch_recommendations.append(PaymentRecommendation(
                    recommendation_type=RecommendationType.BATCH_PAYMENT,
                    priority=Priority.MEDIUM,
                    title=f"Sammelzahlung am {date_key}",
                    summary=f"{len(recs)} Zahlungen buendeln, Gesamtersparnis: {float(total_savings):,.2f} EUR",
                    detail=f"Gesamtbetrag: {float(total_amount):,.2f} EUR",
                    invoices=all_invoices,
                    total_amount=total_amount,
                    total_savings=total_savings,
                    roi_percent=mean([r.roi_percent for r in recs]),
                    recommended_pay_date=datetime.strptime(date_key, "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    liquidity_impact=LiquidityImpact.NEUTRAL,
                    confidence=0.9,
                    reasoning=[
                        f"{len(recs)} Zahlungen am gleichen Tag",
                        "Sammelzahlung reduziert Transaktionskosten",
                        "Bessere Übersicht über Zahlungsausgaenge",
                    ],
                ))

        return batch_recommendations

    def _forecast_liquidity(
        self,
        current_balance: Decimal,
        recommendations: List[PaymentRecommendation],
        expected_inflows: Dict[datetime, Decimal],
        expected_outflows: Dict[datetime, Decimal],
        days_ahead: int,
    ) -> Dict[str, Decimal]:
        """Erstellt Liquiditaetsprognose mit Empfehlungen."""
        forecast: Dict[str, Decimal] = {}
        balance = current_balance
        now = datetime.now(timezone.utc)

        # Empfohlene Zahlungen nach Datum
        recommended_payments: Dict[str, Decimal] = {}
        for rec in recommendations:
            if rec.recommendation_type == RecommendationType.PAY_NOW and rec.recommended_pay_date:
                date_key = rec.recommended_pay_date.strftime("%Y-%m-%d")
                if date_key not in recommended_payments:
                    recommended_payments[date_key] = Decimal("0")
                recommended_payments[date_key] += rec.total_amount

        # Tag für Tag
        for day_offset in range(1, days_ahead + 1):
            target_date = now + timedelta(days=day_offset)
            date_key = target_date.strftime("%Y-%m-%d")
            date_normalized = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

            # Eingaenge
            inflow = expected_inflows.get(date_normalized, Decimal("0"))
            balance += inflow

            # Ausgaenge
            outflow = expected_outflows.get(date_normalized, Decimal("0"))
            balance -= outflow

            # Empfohlene Zahlungen
            recommended = recommended_payments.get(date_key, Decimal("0"))
            balance -= recommended

            forecast[date_key] = balance

        return forecast


# =============================================================================
# Singleton
# =============================================================================

_skonto_optimizer: Optional[SkontoOptimizer] = None


def get_skonto_optimizer() -> SkontoOptimizer:
    """Gibt die Singleton-Instanz zurück."""
    global _skonto_optimizer
    if _skonto_optimizer is None:
        _skonto_optimizer = SkontoOptimizer()
    return _skonto_optimizer
