# -*- coding: utf-8 -*-
"""
Cashflow Predictor - ML-basierte Cashflow-Prognose.

Enterprise Feature: 7-90 Tage Liquiditaetsprognose mit Confidence-Scores.

Features:
- Historische Muster-Erkennung (Seasonal Patterns)
- Pending Invoices Tracking
- Recurring Payments Prediction
- Holiday/Seasonal Adjustments
- What-If Scenario Support

Unterschied zum CashflowWarningGenerator:
- CashflowWarningGenerator: Einfache Regel-basierte Warnungen
- CashflowPredictor: ML-basierte Vorhersage mit Confidence-Calibration
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from statistics import mean, stdev
from typing import Any, Dict, List, Optional, Tuple, TypedDict
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram, Gauge
from sqlalchemy import select, and_, func, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BankTransaction,
    InvoiceTracking,
    BusinessEntity,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

CASHFLOW_PREDICTIONS_GENERATED = Counter(
    "cashflow_predictions_generated_total",
    "Total cashflow predictions generated",
    ["company_id", "horizon_days"]
)

CASHFLOW_PREDICTION_ACCURACY = Histogram(
    "cashflow_prediction_accuracy",
    "Cashflow prediction accuracy (actual vs predicted)",
    ["company_id"],
    buckets=[0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.99, 1.0]
)

CASHFLOW_PREDICTION_TIME = Histogram(
    "cashflow_prediction_generation_seconds",
    "Time to generate cashflow predictions",
    ["company_id"]
)


# =============================================================================
# Enums
# =============================================================================

class CashflowTrend(str, Enum):
    """Trend der Cashflow-Entwicklung."""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"
    VOLATILE = "volatile"


class RiskLevel(str, Enum):
    """Risiko-Level für Liquiditaet."""
    CRITICAL = "critical"   # Negative Balance erwartet
    HIGH = "high"           # < 1 Monat Reserve
    MEDIUM = "medium"       # 1-3 Monate Reserve
    LOW = "low"             # > 3 Monate Reserve


class PredictionConfidence(str, Enum):
    """Confidence-Level der Prognose."""
    HIGH = "high"       # > 80% Confidence
    MEDIUM = "medium"   # 60-80% Confidence
    LOW = "low"         # < 60% Confidence


# =============================================================================
# TypedDicts
# =============================================================================

class DailyCashflowDict(TypedDict):
    """Tägliche Cashflow-Prognose."""
    date: str
    predicted_balance: float
    incoming: float
    outgoing: float
    confidence: float
    risk_level: str
    factors: List[Dict[str, Any]]


class CashflowScenarioDict(TypedDict):
    """What-If Szenario."""
    name: str
    description: str
    adjustments: Dict[str, float]
    impact_on_balance: float
    risk_change: str


class CashflowPredictionDict(TypedDict):
    """Vollständige Cashflow-Prognose."""
    id: str
    company_id: str
    generated_at: str
    horizon_days: int
    current_balance: float
    predicted_end_balance: float
    lowest_balance: float
    lowest_balance_date: str
    trend: str
    overall_risk: str
    confidence: float
    daily_predictions: List[DailyCashflowDict]
    scenarios: List[CashflowScenarioDict]
    recommendations: List[str]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RecurringPayment:
    """Wiederkehrende Zahlung (ein- oder ausgehend)."""
    id: UUID
    name: str
    amount: Decimal
    is_incoming: bool
    frequency_days: int  # 7=weekly, 30=monthly, 365=yearly
    next_date: datetime
    confidence: float = 0.9


@dataclass
class PendingInvoice:
    """Ausstehende Rechnung."""
    id: UUID
    amount: Decimal
    is_incoming: bool  # True = Forderung, False = Verbindlichkeit
    due_date: datetime
    entity_name: str
    payment_probability: float  # Basierend auf Entity-Historie
    expected_delay_days: int  # Historische Durchschnittsverzögerung


@dataclass
class SeasonalPattern:
    """Saisonales Muster."""
    month: int
    day_of_month: int
    adjustment_factor: float  # 1.0 = normal, 1.5 = 50% mehr
    description: str


@dataclass
class CashflowDataPoint:
    """Einzelner Datenpunkt für Prognose."""
    date: datetime
    predicted_balance: Decimal
    incoming: Decimal
    outgoing: Decimal
    confidence: float
    risk_level: RiskLevel
    factors: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class CashflowPrediction:
    """Vollständige Cashflow-Prognose."""
    id: UUID = field(default_factory=uuid4)
    company_id: Optional[UUID] = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    horizon_days: int = 30

    # Aktueller Zustand
    current_balance: Decimal = Decimal("0")

    # Prognose-Ergebnisse
    predicted_end_balance: Decimal = Decimal("0")
    lowest_balance: Decimal = Decimal("0")
    lowest_balance_date: Optional[datetime] = None
    trend: CashflowTrend = CashflowTrend.STABLE
    overall_risk: RiskLevel = RiskLevel.MEDIUM
    confidence: float = 0.7

    # Detaillierte Prognose
    daily_predictions: List[CashflowDataPoint] = field(default_factory=list)

    # Szenarien
    scenarios: List[Dict[str, Any]] = field(default_factory=list)

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> CashflowPredictionDict:
        """Konvertiert zu Dictionary."""
        return CashflowPredictionDict(
            id=str(self.id),
            company_id=str(self.company_id) if self.company_id else "",
            generated_at=self.generated_at.isoformat(),
            horizon_days=self.horizon_days,
            current_balance=float(self.current_balance),
            predicted_end_balance=float(self.predicted_end_balance),
            lowest_balance=float(self.lowest_balance),
            lowest_balance_date=self.lowest_balance_date.isoformat() if self.lowest_balance_date else "",
            trend=self.trend.value,
            overall_risk=self.overall_risk.value,
            confidence=self.confidence,
            daily_predictions=[
                DailyCashflowDict(
                    date=dp.date.isoformat(),
                    predicted_balance=float(dp.predicted_balance),
                    incoming=float(dp.incoming),
                    outgoing=float(dp.outgoing),
                    confidence=dp.confidence,
                    risk_level=dp.risk_level.value,
                    factors=dp.factors,
                )
                for dp in self.daily_predictions
            ],
            scenarios=[
                CashflowScenarioDict(
                    name=s.get("name", ""),
                    description=s.get("description", ""),
                    adjustments=s.get("adjustments", {}),
                    impact_on_balance=s.get("impact_on_balance", 0),
                    risk_change=s.get("risk_change", "neutral"),
                )
                for s in self.scenarios
            ],
            recommendations=self.recommendations,
        )


# =============================================================================
# Cashflow Predictor Service
# =============================================================================

class CashflowPredictor:
    """
    ML-basierter Cashflow-Prognose-Service.

    Kombiniert mehrere Datenquellen:
    - Historische Transaktionen (Pattern Learning)
    - Ausstehende Rechnungen (mit Zahlungswahrscheinlichkeit)
    - Wiederkehrende Zahlungen
    - Saisonale Muster
    - Entity-spezifische Zahlungsverhalten
    """

    # Defaults
    DEFAULT_HORIZON_DAYS = 30
    MAX_HORIZON_DAYS = 90
    MIN_HISTORICAL_DAYS = 90  # Mindestens 90 Tage Historie für Patterns

    def __init__(self) -> None:
        """Initialisiert den Service."""
        self._seasonal_patterns: Dict[UUID, List[SeasonalPattern]] = {}
        self._entity_payment_stats: Dict[UUID, Dict[str, float]] = {}

    async def predict(
        self,
        db: AsyncSession,
        company_id: UUID,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
        include_scenarios: bool = True,
        scenario_adjustments: Optional[Dict[str, float]] = None,
    ) -> CashflowPrediction:
        """
        Generiert Cashflow-Prognose.

        Args:
            db: Database Session
            company_id: Company-ID
            horizon_days: Prognose-Horizont in Tagen (max 90)
            include_scenarios: What-If Szenarien generieren
            scenario_adjustments: Manuelle Anpassungen für Szenarien

        Returns:
            CashflowPrediction mit detaillierten Prognosen
        """
        import time
        start_time = time.perf_counter()

        horizon_days = min(horizon_days, self.MAX_HORIZON_DAYS)

        logger.info(
            "generating_cashflow_prediction",
            company_id=str(company_id),
            horizon_days=horizon_days,
        )

        # 1. Aktuellen Kontostand laden
        current_balance = await self._get_current_balance(db, company_id)

        # 2. Historische Muster analysieren
        patterns = await self._analyze_historical_patterns(db, company_id)

        # 3. Ausstehende Rechnungen laden
        pending_invoices = await self._get_pending_invoices(db, company_id)

        # 4. Wiederkehrende Zahlungen identifizieren
        recurring = await self._identify_recurring_payments(db, company_id)

        # 5. Tägliche Prognose erstellen
        daily_predictions = await self._generate_daily_predictions(
            current_balance=current_balance,
            pending_invoices=pending_invoices,
            recurring_payments=recurring,
            patterns=patterns,
            horizon_days=horizon_days,
        )

        # 6. Gesamtanalyse
        prediction = self._create_prediction(
            company_id=company_id,
            current_balance=current_balance,
            daily_predictions=daily_predictions,
            horizon_days=horizon_days,
        )

        # 7. Szenarien generieren
        if include_scenarios:
            prediction.scenarios = self._generate_scenarios(
                prediction=prediction,
                pending_invoices=pending_invoices,
                scenario_adjustments=scenario_adjustments,
            )

        # 8. Empfehlungen generieren
        prediction.recommendations = self._generate_recommendations(prediction)

        # Metrics
        duration = time.perf_counter() - start_time
        CASHFLOW_PREDICTION_TIME.labels(company_id=str(company_id)).observe(duration)
        CASHFLOW_PREDICTIONS_GENERATED.labels(
            company_id=str(company_id),
            horizon_days=str(horizon_days),
        ).inc()

        logger.info(
            "cashflow_prediction_generated",
            company_id=str(company_id),
            horizon_days=horizon_days,
            current_balance=float(current_balance),
            predicted_end_balance=float(prediction.predicted_end_balance),
            lowest_balance=float(prediction.lowest_balance),
            risk_level=prediction.overall_risk.value,
            confidence=prediction.confidence,
            duration_seconds=duration,
        )

        return prediction

    async def _get_current_balance(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Decimal:
        """Laedt aktuellen Kontostand aus Bank-Transaktionen."""
        # Summe aller Transaktionen = aktueller Kontostand
        query = select(
            func.coalesce(func.sum(BankTransaction.amount), 0)
        ).where(
            BankTransaction.company_id == company_id
        )

        result = await db.execute(query)
        balance = result.scalar_one_or_none()

        return Decimal(str(balance or 0))

    async def _analyze_historical_patterns(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """
        Analysiert historische Transaktionsmuster.

        Erkennt:
        - Monatliche Durchschnitte (Ein-/Ausgaenge)
        - Wochentags-Muster
        - Monatsende-Effekte
        - Saisonale Schwankungen
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.MIN_HISTORICAL_DAYS)

        # Lade historische Transaktionen
        query = select(BankTransaction).where(
            and_(
                BankTransaction.company_id == company_id,
                BankTransaction.booking_date >= cutoff,
            )
        )

        result = await db.execute(query)
        transactions = result.scalars().all()

        if not transactions:
            return self._default_patterns()

        # Aggregiere nach Tag
        daily_totals: Dict[str, Dict[str, Decimal]] = {}

        for tx in transactions:
            date_key = tx.booking_date.strftime("%Y-%m-%d")
            if date_key not in daily_totals:
                daily_totals[date_key] = {"incoming": Decimal("0"), "outgoing": Decimal("0")}

            if tx.amount > 0:
                daily_totals[date_key]["incoming"] += tx.amount
            else:
                daily_totals[date_key]["outgoing"] += abs(tx.amount)

        # Berechne Durchschnitte
        incoming_values = [float(d["incoming"]) for d in daily_totals.values()]
        outgoing_values = [float(d["outgoing"]) for d in daily_totals.values()]

        avg_daily_incoming = mean(incoming_values) if incoming_values else 0
        avg_daily_outgoing = mean(outgoing_values) if outgoing_values else 0

        # Volatilität berechnen
        incoming_volatility = stdev(incoming_values) / avg_daily_incoming if avg_daily_incoming > 0 and len(incoming_values) > 1 else 0.5
        outgoing_volatility = stdev(outgoing_values) / avg_daily_outgoing if avg_daily_outgoing > 0 and len(outgoing_values) > 1 else 0.5

        # Wochentags-Faktoren berechnen
        weekday_factors = self._calculate_weekday_factors(transactions)

        # Monatsende-Effekt
        month_end_factor = self._calculate_month_end_factor(transactions)

        return {
            "avg_daily_incoming": avg_daily_incoming,
            "avg_daily_outgoing": avg_daily_outgoing,
            "incoming_volatility": incoming_volatility,
            "outgoing_volatility": outgoing_volatility,
            "weekday_factors": weekday_factors,
            "month_end_factor": month_end_factor,
            "data_points": len(transactions),
            "confidence_factor": min(1.0, len(transactions) / 500),  # Mehr Daten = mehr Confidence
        }

    def _calculate_weekday_factors(
        self,
        transactions: List[BankTransaction],
    ) -> Dict[int, float]:
        """Berechnet Faktoren pro Wochentag."""
        weekday_amounts: Dict[int, List[float]] = {i: [] for i in range(7)}

        for tx in transactions:
            weekday = tx.booking_date.weekday()
            weekday_amounts[weekday].append(float(abs(tx.amount)))

        overall_avg = mean([float(abs(tx.amount)) for tx in transactions]) if transactions else 1

        factors = {}
        for weekday, amounts in weekday_amounts.items():
            if amounts:
                weekday_avg = mean(amounts)
                factors[weekday] = weekday_avg / overall_avg if overall_avg > 0 else 1.0
            else:
                factors[weekday] = 1.0

        return factors

    def _calculate_month_end_factor(
        self,
        transactions: List[BankTransaction],
    ) -> float:
        """Berechnet Faktor für Monatsende (letzte 5 Tage)."""
        month_end_amounts = []
        other_amounts = []

        for tx in transactions:
            day = tx.booking_date.day
            # Letzte 5 Tage des Monats (vereinfacht: Tag > 25)
            if day > 25:
                month_end_amounts.append(float(abs(tx.amount)))
            else:
                other_amounts.append(float(abs(tx.amount)))

        if not month_end_amounts or not other_amounts:
            return 1.0

        return mean(month_end_amounts) / mean(other_amounts)

    def _default_patterns(self) -> Dict[str, Any]:
        """Standard-Muster wenn keine Historie vorhanden."""
        return {
            "avg_daily_incoming": 0,
            "avg_daily_outgoing": 0,
            "incoming_volatility": 0.5,
            "outgoing_volatility": 0.5,
            "weekday_factors": {i: 1.0 for i in range(7)},
            "month_end_factor": 1.2,
            "data_points": 0,
            "confidence_factor": 0.3,
        }

    async def _get_pending_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[PendingInvoice]:
        """Laedt ausstehende Rechnungen mit Zahlungswahrscheinlichkeit."""
        # Forderungen (eingehend) und Verbindlichkeiten (ausgehend)
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status.in_(["pending", "partial", "overdue"]),
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        pending = []
        for inv in invoices:
            # Zahlungswahrscheinlichkeit aus Entity-Historie
            payment_prob = await self._get_entity_payment_probability(
                db, inv.entity_id
            ) if inv.entity_id else 0.7

            # Erwartete Verzögerung
            expected_delay = await self._get_entity_payment_delay(
                db, inv.entity_id
            ) if inv.entity_id else 0

            pending.append(PendingInvoice(
                id=inv.id,
                amount=inv.outstanding_amount or inv.amount,
                is_incoming=inv.invoice_type == "incoming",  # Forderung
                due_date=inv.due_date or datetime.now(timezone.utc),
                entity_name=inv.entity.name if inv.entity else "Unbekannt",
                payment_probability=payment_prob,
                expected_delay_days=expected_delay,
            ))

        return pending

    async def _get_entity_payment_probability(
        self,
        db: AsyncSession,
        entity_id: Optional[UUID],
    ) -> float:
        """Berechnet Zahlungswahrscheinlichkeit basierend auf Historie."""
        if not entity_id:
            return 0.7  # Default

        # Cache prüfen
        cache_key = str(entity_id)
        if cache_key in self._entity_payment_stats:
            return self._entity_payment_stats[cache_key].get("payment_probability", 0.7)

        # Historische Zahlungen analysieren
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.entity_id == entity_id,
                InvoiceTracking.status.in_(["paid", "partial", "overdue"]),
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        if not invoices:
            return 0.7

        # Bezahlt vs. überfällig Ratio
        paid_count = sum(1 for i in invoices if i.status == "paid")
        total_count = len(invoices)

        probability = paid_count / total_count if total_count > 0 else 0.7

        # Cache speichern
        self._entity_payment_stats[cache_key] = {"payment_probability": probability}

        return probability

    async def _get_entity_payment_delay(
        self,
        db: AsyncSession,
        entity_id: Optional[UUID],
    ) -> int:
        """Berechnet durchschnittliche Zahlungsverzögerung in Tagen."""
        if not entity_id:
            return 0

        cache_key = str(entity_id)
        if cache_key in self._entity_payment_stats:
            return int(self._entity_payment_stats[cache_key].get("avg_delay", 0))

        # Historische Verzögerungen
        query = select(InvoiceTracking).where(
            and_(
                InvoiceTracking.entity_id == entity_id,
                InvoiceTracking.status == "paid",
                InvoiceTracking.paid_at.isnot(None),
            )
        )

        result = await db.execute(query)
        invoices = result.scalars().all()

        if not invoices:
            return 0

        delays = []
        for inv in invoices:
            if inv.paid_at and inv.due_date:
                delay = (inv.paid_at - inv.due_date).days
                if delay > 0:
                    delays.append(delay)

        avg_delay = int(mean(delays)) if delays else 0

        # Cache aktualisieren
        if cache_key not in self._entity_payment_stats:
            self._entity_payment_stats[cache_key] = {}
        self._entity_payment_stats[cache_key]["avg_delay"] = avg_delay

        return avg_delay

    async def _identify_recurring_payments(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[RecurringPayment]:
        """
        Identifiziert wiederkehrende Zahlungen aus Historie.

        Erkennt monatliche, woechentliche und jährliche Muster.
        """
        # Mindestens 3 Monate Historie für Muster-Erkennung
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        # Gruppiere nach Verwendungszweck/Partner
        query = select(
            BankTransaction.purpose,
            BankTransaction.partner_name,
            func.array_agg(BankTransaction.amount).label("amounts"),
            func.array_agg(BankTransaction.booking_date).label("dates"),
            func.count().label("count"),
        ).where(
            and_(
                BankTransaction.company_id == company_id,
                BankTransaction.booking_date >= cutoff,
            )
        ).group_by(
            BankTransaction.purpose,
            BankTransaction.partner_name,
        ).having(
            func.count() >= 2  # Mindestens 2 Transaktionen
        )

        result = await db.execute(query)
        groups = result.all()

        recurring = []

        for group in groups:
            amounts = group.amounts or []
            dates = group.dates or []

            if len(amounts) < 2:
                continue

            # Prüfen ob Betraege ähnlich sind (Varianz < 10%)
            amounts_float = [float(a) for a in amounts]
            if len(amounts_float) > 1:
                avg_amount = mean(amounts_float)
                max_variance = abs(max(amounts_float) - min(amounts_float)) / abs(avg_amount) if avg_amount != 0 else 1

                if max_variance > 0.1:
                    continue  # Zu unterschiedlich
            else:
                avg_amount = amounts_float[0]

            # Frequenz erkennen
            if len(dates) >= 2:
                dates_sorted = sorted(dates)
                intervals = [
                    (dates_sorted[i+1] - dates_sorted[i]).days
                    for i in range(len(dates_sorted) - 1)
                ]
                avg_interval = int(mean(intervals))

                # Frequenz normalisieren
                if 25 <= avg_interval <= 35:
                    frequency = 30  # Monatlich
                elif 5 <= avg_interval <= 9:
                    frequency = 7   # Woechentlich
                elif 350 <= avg_interval <= 380:
                    frequency = 365  # Jährlich
                else:
                    continue  # Kein klares Muster

                # Nächstes Datum berechnen
                last_date = max(dates)
                next_date = last_date + timedelta(days=frequency)

                recurring.append(RecurringPayment(
                    id=uuid4(),
                    name=group.partner_name or group.purpose or "Unbekannt",
                    amount=Decimal(str(abs(avg_amount))),
                    is_incoming=avg_amount > 0,
                    frequency_days=frequency,
                    next_date=next_date,
                    confidence=min(0.95, 0.7 + (len(amounts) * 0.05)),
                ))

        return recurring

    async def _generate_daily_predictions(
        self,
        current_balance: Decimal,
        pending_invoices: List[PendingInvoice],
        recurring_payments: List[RecurringPayment],
        patterns: Dict[str, Any],
        horizon_days: int,
    ) -> List[CashflowDataPoint]:
        """Generiert tägliche Prognosen."""
        predictions = []
        balance = current_balance
        now = datetime.now(timezone.utc)

        for day_offset in range(1, horizon_days + 1):
            target_date = now + timedelta(days=day_offset)

            # Erwartete Ein-/Ausgaenge
            incoming = Decimal("0")
            outgoing = Decimal("0")
            factors = []
            confidence = patterns.get("confidence_factor", 0.5)

            # 1. Ausstehende Rechnungen (Fälligkeit = target_date)
            for inv in pending_invoices:
                expected_date = inv.due_date + timedelta(days=inv.expected_delay_days)
                if expected_date.date() == target_date.date():
                    weighted_amount = inv.amount * Decimal(str(inv.payment_probability))
                    if inv.is_incoming:
                        incoming += weighted_amount
                        factors.append({
                            "type": "invoice_incoming",
                            "entity": inv.entity_name,
                            "amount": float(inv.amount),
                            "probability": inv.payment_probability,
                        })
                    else:
                        outgoing += weighted_amount
                        factors.append({
                            "type": "invoice_outgoing",
                            "entity": inv.entity_name,
                            "amount": float(inv.amount),
                            "probability": inv.payment_probability,
                        })

            # 2. Wiederkehrende Zahlungen
            for rec in recurring_payments:
                # Prüfen ob Zahlung in diesem Zeitfenster fällig
                days_since_last = (target_date - rec.next_date).days
                if 0 <= days_since_last < rec.frequency_days:
                    occurrences = days_since_last // rec.frequency_days
                    payment_date = rec.next_date + timedelta(days=occurrences * rec.frequency_days)

                    if payment_date.date() == target_date.date():
                        if rec.is_incoming:
                            incoming += rec.amount * Decimal(str(rec.confidence))
                        else:
                            outgoing += rec.amount * Decimal(str(rec.confidence))

                        factors.append({
                            "type": "recurring",
                            "name": rec.name,
                            "amount": float(rec.amount),
                            "is_incoming": rec.is_incoming,
                            "confidence": rec.confidence,
                        })

            # 3. Baseline aus historischen Mustern
            weekday = target_date.weekday()
            weekday_factor = patterns.get("weekday_factors", {}).get(weekday, 1.0)

            # Monatsende-Effekt
            if target_date.day > 25:
                weekday_factor *= patterns.get("month_end_factor", 1.0)

            # Basis-Einnahmen/-Ausgaben (wenn keine konkreten Zahlungen)
            if not factors:
                base_incoming = Decimal(str(patterns.get("avg_daily_incoming", 0)))
                base_outgoing = Decimal(str(patterns.get("avg_daily_outgoing", 0)))

                incoming += base_incoming * Decimal(str(weekday_factor))
                outgoing += base_outgoing * Decimal(str(weekday_factor))

                factors.append({
                    "type": "baseline",
                    "weekday_factor": weekday_factor,
                })

            # Neuen Saldo berechnen
            balance = balance + incoming - outgoing

            # Risiko-Level bestimmen
            monthly_outgoing = patterns.get("avg_daily_outgoing", 0) * 30

            if balance < Decimal("0"):
                risk = RiskLevel.CRITICAL
            elif float(balance) < monthly_outgoing:
                risk = RiskLevel.HIGH
            elif float(balance) < monthly_outgoing * 3:
                risk = RiskLevel.MEDIUM
            else:
                risk = RiskLevel.LOW

            # Confidence basierend auf Faktoren
            if factors:
                avg_factor_confidence = mean([
                    f.get("confidence", 0.7) if "confidence" in f else 0.7
                    for f in factors
                ])
                confidence = (confidence + avg_factor_confidence) / 2

            predictions.append(CashflowDataPoint(
                date=target_date,
                predicted_balance=balance,
                incoming=incoming,
                outgoing=outgoing,
                confidence=confidence,
                risk_level=risk,
                factors=factors,
            ))

        return predictions

    def _create_prediction(
        self,
        company_id: UUID,
        current_balance: Decimal,
        daily_predictions: List[CashflowDataPoint],
        horizon_days: int,
    ) -> CashflowPrediction:
        """Erstellt das Prediction-Objekt aus den täglichen Prognosen."""
        if not daily_predictions:
            return CashflowPrediction(
                company_id=company_id,
                horizon_days=horizon_days,
                current_balance=current_balance,
            )

        # Niedrigster Saldo
        lowest = min(daily_predictions, key=lambda d: d.predicted_balance)

        # Trend berechnen
        balances = [float(d.predicted_balance) for d in daily_predictions]
        trend = self._calculate_trend(balances)

        # Durchschnittliche Confidence
        avg_confidence = mean([d.confidence for d in daily_predictions])

        # Gesamtrisiko = hoechstes Risiko
        risk_order = [RiskLevel.CRITICAL, RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW]
        overall_risk = min(
            [d.risk_level for d in daily_predictions],
            key=lambda r: risk_order.index(r)
        )

        return CashflowPrediction(
            company_id=company_id,
            horizon_days=horizon_days,
            current_balance=current_balance,
            predicted_end_balance=daily_predictions[-1].predicted_balance,
            lowest_balance=lowest.predicted_balance,
            lowest_balance_date=lowest.date,
            trend=trend,
            overall_risk=overall_risk,
            confidence=avg_confidence,
            daily_predictions=daily_predictions,
        )

    def _calculate_trend(self, values: List[float]) -> CashflowTrend:
        """Berechnet den Trend aus einer Wertereihe."""
        if len(values) < 2:
            return CashflowTrend.STABLE

        # Lineare Regression vereinfacht
        n = len(values)
        x_mean = n / 2
        y_mean = mean(values)

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        if denominator == 0:
            return CashflowTrend.STABLE

        slope = numerator / denominator

        # Normalisierte Steigung
        normalized_slope = slope / (abs(y_mean) if y_mean != 0 else 1)

        # Volatilität
        if len(values) > 1:
            volatility = stdev(values) / abs(y_mean) if y_mean != 0 else 0
        else:
            volatility = 0

        if volatility > 0.3:
            return CashflowTrend.VOLATILE
        elif normalized_slope > 0.05:
            return CashflowTrend.IMPROVING
        elif normalized_slope < -0.05:
            return CashflowTrend.DECLINING
        else:
            return CashflowTrend.STABLE

    def _generate_scenarios(
        self,
        prediction: CashflowPrediction,
        pending_invoices: List[PendingInvoice],
        scenario_adjustments: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """Generiert What-If Szenarien."""
        scenarios = []

        # Szenario 1: Alle Forderungen bezahlt
        total_incoming = sum(
            float(inv.amount) for inv in pending_invoices if inv.is_incoming
        )
        if total_incoming > 0:
            new_balance = float(prediction.predicted_end_balance) + total_incoming
            new_risk = "low" if new_balance > float(prediction.current_balance) * 0.5 else prediction.overall_risk.value

            scenarios.append({
                "name": "Alle Forderungen bezahlt",
                "description": f"Wenn alle offenen Forderungen ({total_incoming:,.2f} EUR) eingehen.",
                "adjustments": {"incoming_invoices": total_incoming},
                "impact_on_balance": total_incoming,
                "risk_change": "improved" if new_risk != prediction.overall_risk.value else "neutral",
            })

        # Szenario 2: 50% Verzögerung bei Einzahlungen
        delayed_impact = total_incoming * 0.5
        if delayed_impact > 0:
            scenarios.append({
                "name": "Zahlungsverzögerungen",
                "description": f"Wenn 50% der Forderungen später eingehen.",
                "adjustments": {"incoming_delay": -delayed_impact},
                "impact_on_balance": -delayed_impact,
                "risk_change": "worsened",
            })

        # Szenario 3: Unerwartete Ausgabe
        unexpected_cost = float(prediction.current_balance) * 0.2
        scenarios.append({
            "name": "Unerwartete Ausgabe",
            "description": f"Eine unerwartete Ausgabe von {unexpected_cost:,.2f} EUR.",
            "adjustments": {"unexpected_cost": -unexpected_cost},
            "impact_on_balance": -unexpected_cost,
            "risk_change": "worsened",
        })

        # Szenario 4: Benutzerdefiniert
        if scenario_adjustments:
            custom_impact = sum(scenario_adjustments.values())
            scenarios.append({
                "name": "Benutzerdefiniert",
                "description": "Ihre manuellen Anpassungen.",
                "adjustments": scenario_adjustments,
                "impact_on_balance": custom_impact,
                "risk_change": "improved" if custom_impact > 0 else "worsened",
            })

        return scenarios

    def _generate_recommendations(
        self,
        prediction: CashflowPrediction,
    ) -> List[str]:
        """Generiert Empfehlungen basierend auf Prognose."""
        recommendations = []

        if prediction.overall_risk == RiskLevel.CRITICAL:
            recommendations.append(
                "DRINGEND: Negativer Saldo erwartet. Zahlungseingaenge beschleunigen oder Kreditlinie nutzen."
            )
            recommendations.append(
                "Nicht-kritische Zahlungen verschieben um Liquiditaet zu sichern."
            )

        if prediction.overall_risk == RiskLevel.HIGH:
            recommendations.append(
                "Liquiditaetsreserve unter einem Monat. Forderungen aktiv einfordern."
            )
            recommendations.append(
                "Skonto-Möglichkeiten bei Verbindlichkeiten prüfen."
            )

        if prediction.trend == CashflowTrend.DECLINING:
            recommendations.append(
                "Abwärtstrend erkannt. Ursachenanalyse empfohlen."
            )

        if prediction.trend == CashflowTrend.VOLATILE:
            recommendations.append(
                "Hohe Schwankungen im Cashflow. Automatische Zahlungen prüfen."
            )

        # Positive Empfehlungen
        if prediction.overall_risk == RiskLevel.LOW and prediction.trend == CashflowTrend.IMPROVING:
            recommendations.append(
                "Gute Liquiditaetslage. Optionale Investitionen oder Sondertilgungen möglich."
            )

        if not recommendations:
            recommendations.append(
                "Cashflow-Situation im gruenen Bereich. Weiter beobachten."
            )

        return recommendations


# =============================================================================
# Singleton
# =============================================================================

_cashflow_predictor: Optional[CashflowPredictor] = None


def get_cashflow_predictor() -> CashflowPredictor:
    """Gibt die Singleton-Instanz zurück."""
    global _cashflow_predictor
    if _cashflow_predictor is None:
        _cashflow_predictor = CashflowPredictor()
    return _cashflow_predictor
