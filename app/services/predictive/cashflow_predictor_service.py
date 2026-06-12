# -*- coding: utf-8 -*-
"""
Cashflow Predictor Service - Entity-basierte Zahlungsprognose.

Phase 2.2: Predictive Cash Flow AI Service

Features:
- Entity Payment Pattern Analysis (historische Zahlungsverzögerungen)
- Seasonal Pattern Detection (Weihnachtsgeschäft, Sommerloch)
- Payment Consistency Tracking (puenktlich, verspätet, variabel)
- 30/60/90-Tage Forecasts mit Confidence Intervals
- Individual Invoice Payment Probability
- Liquidity Alert Integration mit Alert Center

SECURITY:
- NIEMALS Entity-Namen, Kundennummern oder IBANs loggen (PII)
- Alle Betraege werden nur aggregiert ausgegeben
- Company-Isolation via company_id Filter

Created: 2026-02-02
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID
import math
import statistics

import structlog
from sqlalchemy import and_, func, or_, select, extract, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    BankAccount,
    BankTransaction,
    BusinessEntity,
    Document,
    InvoiceTracking,
)
from app.services.invoice_direction import is_incoming_invoice, is_outgoing_invoice

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class PaymentConsistency(str, Enum):
    """Zahlungskonsistenz-Klassifikation."""

    ALWAYS_EARLY = "always_early"      # Immer vor Fälligkeit
    ALWAYS_ON_TIME = "always_on_time"  # Immer puenktlich (+/- 3 Tage)
    MOSTLY_ON_TIME = "mostly_on_time"  # Meist puenktlich (>70%)
    VARIABLE = "variable"              # Unvorhersehbar
    ALWAYS_LATE = "always_late"        # Immer verspätet
    HIGH_RISK = "high_risk"            # Sehr unzuverlaessig/Ausfaelle


class SeasonalPatternType(str, Enum):
    """Saisonale Zahlungsmuster."""

    Q4_DELAY = "q4_delay"           # Verzögerungen im Q4 (Weihnachtsgeschäft)
    SUMMER_SLOW = "summer_slow"      # Sommerloch (Jul/Aug)
    SUMMER_EARLY = "summer_early"    # Frühzahler im Sommer
    MONTH_END_RUSH = "month_end_rush"  # Zahlung zum Monatsende
    QUARTER_END = "quarter_end"      # Quartalszahler
    NO_PATTERN = "no_pattern"        # Kein erkennbares Muster


class LiquidityAlertType(str, Enum):
    """Typ der Liquiditaetswarnung."""

    CASHFLOW_GAP = "cashflow_gap"         # Erwartete Eingaenge < Ausgaenge
    CRITICAL_SHORTFALL = "critical_shortfall"  # Kritischer Engpass erwartet
    HIGH_RISK_CONCENTRATION = "high_risk_concentration"  # Zu viele High-Risk Entities
    SEASONAL_WARNING = "seasonal_warning"  # Saisonale Warnung
    TREND_NEGATIVE = "trend_negative"      # Negativer Trend erkannt


class AlertSeverity(str, Enum):
    """Alarm-Schweregrade."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class SeasonalPattern:
    """Erkanntes saisonales Zahlungsmuster einer Entity."""

    pattern_type: SeasonalPatternType
    affected_months: List[int]
    avg_delay_adjustment: float  # Tage (+/-) zur normalen Verzögerung
    confidence: float  # 0-1
    description: str  # German


@dataclass
class EntityPaymentProfile:
    """Zahlungsprofil eines Geschäftspartners."""

    entity_id: UUID
    avg_payment_delay_days: int
    payment_consistency: PaymentConsistency
    consistency_score: float  # 0-1 (1 = sehr konsistent)
    seasonal_pattern: Optional[SeasonalPattern]
    risk_adjusted_probability: float  # Zahlungswahrscheinlichkeit 0-1

    # Zusätzliche Metriken
    sample_count: int = 0
    stddev_days: float = 0.0
    min_delay_days: int = 0
    max_delay_days: int = 0
    last_payment_date: Optional[datetime] = None

    # Risk Score Integration
    risk_score: float = 50.0  # 0-100
    payment_behavior_score: float = 50.0  # 0-100

    # Metadata (keine PII)
    profile_updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary ohne PII."""
        return {
            "entity_id": str(self.entity_id),
            "avg_payment_delay_days": self.avg_payment_delay_days,
            "payment_consistency": self.payment_consistency.value,
            "consistency_score": round(self.consistency_score, 2),
            "seasonal_pattern": {
                "type": self.seasonal_pattern.pattern_type.value,
                "affected_months": self.seasonal_pattern.affected_months,
                "avg_delay_adjustment": self.seasonal_pattern.avg_delay_adjustment,
                "confidence": self.seasonal_pattern.confidence,
                "description": self.seasonal_pattern.description,
            } if self.seasonal_pattern else None,
            "risk_adjusted_probability": round(self.risk_adjusted_probability, 3),
            "sample_count": self.sample_count,
            "stddev_days": round(self.stddev_days, 1),
            "risk_score": round(self.risk_score, 1),
            "payment_behavior_score": round(self.payment_behavior_score, 1),
            "profile_updated_at": self.profile_updated_at.isoformat(),
        }


@dataclass
class PaymentProbability:
    """Zahlungswahrscheinlichkeit für eine einzelne Rechnung."""

    invoice_id: UUID
    entity_id: Optional[UUID]
    amount: Decimal
    due_date: date

    # Vorhersage
    predicted_payment_date: date
    probability: float  # 0-1
    delay_days: int  # Erwartete Verzögerung

    # Confidence Interval
    optimistic_date: date  # 10. Perzentil
    pessimistic_date: date  # 90. Perzentil

    # Risikofaktoren
    risk_factors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "invoice_id": str(self.invoice_id),
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "amount": float(self.amount),
            "due_date": self.due_date.isoformat(),
            "predicted_payment_date": self.predicted_payment_date.isoformat(),
            "probability": round(self.probability, 3),
            "delay_days": self.delay_days,
            "confidence_interval": {
                "optimistic": self.optimistic_date.isoformat(),
                "pessimistic": self.pessimistic_date.isoformat(),
            },
            "risk_factors": self.risk_factors,
        }


@dataclass
class CashFlowPrediction:
    """Tagesweise Cashflow-Prognose."""

    prediction_date: date
    expected_inflows: Decimal
    expected_outflows: Decimal
    net_cash_flow: Decimal

    # Confidence Intervals
    confidence_low: Decimal    # Pessimistic (10. Perzentil)
    confidence_mid: Decimal    # Realistic (Median)
    confidence_high: Decimal   # Optimistic (90. Perzentil)

    # Detailinformationen
    contributing_invoices: List[UUID]
    inflow_count: int = 0
    outflow_count: int = 0

    # Risikofaktoren
    risk_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "prediction_date": self.prediction_date.isoformat(),
            "expected_inflows": float(self.expected_inflows),
            "expected_outflows": float(self.expected_outflows),
            "net_cash_flow": float(self.net_cash_flow),
            "confidence": {
                "low": float(self.confidence_low),
                "mid": float(self.confidence_mid),
                "high": float(self.confidence_high),
            },
            "contributing_invoices": [str(i) for i in self.contributing_invoices],
            "inflow_count": self.inflow_count,
            "outflow_count": self.outflow_count,
            "risk_factors": self.risk_factors,
        }


@dataclass
class LiquidityAlert:
    """Liquiditaetswarnung."""

    alert_type: LiquidityAlertType
    severity: AlertSeverity
    trigger_date: date
    predicted_balance: Decimal
    expected_inflows: Decimal
    expected_outflows: Decimal
    message: str  # German
    recommendations: List[str]  # German
    days_until_trigger: int

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "trigger_date": self.trigger_date.isoformat(),
            "predicted_balance": float(self.predicted_balance),
            "expected_inflows": float(self.expected_inflows),
            "expected_outflows": float(self.expected_outflows),
            "message": self.message,
            "recommendations": self.recommendations,
            "days_until_trigger": self.days_until_trigger,
        }


# =============================================================================
# SERVICE CLASS
# =============================================================================


class CashflowPredictorService:
    """
    Service für Entity-basierte Cashflow-Vorhersagen.

    Kombiniert:
    - Historische Zahlungsmuster-Analyse pro Entity
    - Saisonale Pattern-Erkennung
    - Risk-Score-gewichtete Wahrscheinlichkeiten
    - Monte Carlo Simulation für Confidence Intervals

    SECURITY:
    - Alle Abfragen mit company_id Filter (Multi-Tenant)
    - Keine PII in Logs (Entity-Namen, Kundennummern)
    """

    # Konfiguration
    MIN_SAMPLES_FOR_PATTERN = 5  # Mindestanzahl Zahlungen für Muster-Erkennung
    SEASONAL_SIGNIFICANCE_THRESHOLD = 0.15  # 15% Abweichung für saisonales Muster
    WARNING_BALANCE_THRESHOLD = Decimal("5000")
    CRITICAL_BALANCE_THRESHOLD = Decimal("0")
    HIGH_RISK_ENTITY_THRESHOLD = 75  # Risk Score > 75 = High Risk

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Service mit Datenbankverbindung.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db
        self._profile_cache: Dict[UUID, EntityPaymentProfile] = {}

    # =========================================================================
    # PUBLIC API - Hauptfunktionen
    # =========================================================================

    async def get_entity_payment_profile(
        self,
        entity_id: UUID,
        company_id: UUID,
        force_refresh: bool = False,
    ) -> Optional[EntityPaymentProfile]:
        """
        Berechnet das vollständige Zahlungsprofil einer Entity.

        Args:
            entity_id: Geschäftspartner-ID
            company_id: Mandanten-ID (Multi-Tenant)
            force_refresh: Cache ignorieren

        Returns:
            EntityPaymentProfile oder None wenn keine Daten
        """
        # Cache prüfen
        if not force_refresh and entity_id in self._profile_cache:
            cached = self._profile_cache[entity_id]
            # Cache ist 1 Stunde gültig
            if (utc_now() - cached.profile_updated_at).total_seconds() < 3600:
                return cached

        logger.debug(
            "entity_profile_calculation_started",
            entity_id=str(entity_id),
            company_id=str(company_id),
        )

        # 1. Historische Zahlungsdaten laden
        payment_history = await self._get_payment_history(entity_id, company_id)

        if not payment_history:
            logger.debug(
                "no_payment_history_found",
                entity_id=str(entity_id),
            )
            return None

        # 2. Basis-Statistiken berechnen
        delays = [p["delay_days"] for p in payment_history]
        avg_delay = statistics.mean(delays)
        stddev = statistics.stdev(delays) if len(delays) > 1 else 0.0

        # 3. Konsistenz bewerten
        consistency, consistency_score = self._calculate_consistency(delays)

        # 4. Saisonale Muster erkennen
        seasonal_pattern = await self._detect_seasonal_pattern(payment_history)

        # 5. Risk Score laden (falls vorhanden)
        risk_score, payment_behavior_score = await self._get_entity_risk_scores(
            entity_id, company_id
        )

        # 6. Zahlungswahrscheinlichkeit berechnen
        probability = self._calculate_payment_probability(
            avg_delay=avg_delay,
            stddev=stddev,
            consistency_score=consistency_score,
            risk_score=risk_score,
            sample_count=len(delays),
        )

        profile = EntityPaymentProfile(
            entity_id=entity_id,
            avg_payment_delay_days=int(round(avg_delay)),
            payment_consistency=consistency,
            consistency_score=consistency_score,
            seasonal_pattern=seasonal_pattern,
            risk_adjusted_probability=probability,
            sample_count=len(delays),
            stddev_days=stddev,
            min_delay_days=min(delays),
            max_delay_days=max(delays),
            last_payment_date=payment_history[-1]["paid_at"] if payment_history else None,
            risk_score=risk_score,
            payment_behavior_score=payment_behavior_score,
        )

        # Cache aktualisieren
        self._profile_cache[entity_id] = profile

        logger.info(
            "entity_profile_calculated",
            entity_id=str(entity_id),
            avg_delay=int(avg_delay),
            consistency=consistency.value,
            probability=round(probability, 2),
        )

        return profile

    async def get_invoice_payment_probability(
        self,
        invoice_id: UUID,
        company_id: UUID,
    ) -> Optional[PaymentProbability]:
        """
        Berechnet die Zahlungswahrscheinlichkeit für eine einzelne Rechnung.

        Args:
            invoice_id: Rechnungs-ID
            company_id: Mandanten-ID

        Returns:
            PaymentProbability oder None
        """
        # Rechnung laden
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.id == invoice_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            return None

        if invoice.status == "paid":
            # Bereits bezahlt
            return PaymentProbability(
                invoice_id=invoice_id,
                entity_id=invoice.entity_id,
                amount=Decimal(str(invoice.amount or 0)),
                due_date=invoice.due_date.date() if invoice.due_date else date.today(),
                predicted_payment_date=invoice.paid_at.date() if invoice.paid_at else date.today(),
                probability=1.0,
                delay_days=0,
                optimistic_date=date.today(),
                pessimistic_date=date.today(),
                risk_factors=["already_paid"],
            )

        # Entity-Profil laden (falls vorhanden)
        profile: Optional[EntityPaymentProfile] = None
        if invoice.entity_id:
            profile = await self.get_entity_payment_profile(
                invoice.entity_id, company_id
            )

        # Basiswerte
        due_date = invoice.due_date.date() if invoice.due_date else date.today() + timedelta(days=30)
        amount = Decimal(str(invoice.amount or 0))

        if profile:
            # Entity-basierte Vorhersage
            avg_delay = profile.avg_payment_delay_days
            stddev = profile.stddev_days
            probability = profile.risk_adjusted_probability

            # Saisonale Anpassung
            if profile.seasonal_pattern:
                current_month = date.today().month
                if current_month in profile.seasonal_pattern.affected_months:
                    avg_delay += int(profile.seasonal_pattern.avg_delay_adjustment)
        else:
            # Default-Werte für unbekannte Entities
            avg_delay = 25
            stddev = 15.0
            probability = 0.7

        # Betragsabhängige Anpassung (größere Betraege = längere Zahlung)
        amount_factor = self._get_amount_delay_factor(amount)
        avg_delay = int(avg_delay * amount_factor)

        # Predicted Date
        predicted_date = due_date + timedelta(days=avg_delay)

        # Confidence Interval (10. und 90. Perzentil)
        optimistic = due_date + timedelta(days=max(0, int(avg_delay - 1.645 * stddev)))
        pessimistic = due_date + timedelta(days=int(avg_delay + 1.645 * stddev))

        # Risikofaktoren sammeln
        risk_factors = []

        if invoice.dunning_level and invoice.dunning_level > 0:
            risk_factors.append(f"dunning_level_{invoice.dunning_level}")
            probability *= 0.8  # Mahnungen reduzieren Wahrscheinlichkeit

        if amount > Decimal("50000"):
            risk_factors.append("high_amount")
            probability *= 0.95

        if profile and profile.risk_score > self.HIGH_RISK_ENTITY_THRESHOLD:
            risk_factors.append("high_risk_entity")
            probability *= 0.85

        if profile and profile.payment_consistency == PaymentConsistency.ALWAYS_LATE:
            risk_factors.append("consistently_late_payer")

        if profile and profile.payment_consistency == PaymentConsistency.HIGH_RISK:
            risk_factors.append("unreliable_payer")
            probability *= 0.7

        # Überfällig?
        if due_date < date.today():
            days_overdue = (date.today() - due_date).days
            risk_factors.append(f"overdue_{days_overdue}_days")
            probability *= max(0.3, 1.0 - (days_overdue * 0.02))

        return PaymentProbability(
            invoice_id=invoice_id,
            entity_id=invoice.entity_id,
            amount=amount,
            due_date=due_date,
            predicted_payment_date=predicted_date,
            probability=min(1.0, max(0.0, probability)),
            delay_days=avg_delay,
            optimistic_date=optimistic,
            pessimistic_date=pessimistic,
            risk_factors=risk_factors,
        )

    async def get_cashflow_forecast(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> List[CashFlowPrediction]:
        """
        Erstellt eine Cashflow-Prognose für die nächsten X Tage.

        Verwendet Entity-Profile für praezise Vorhersagen.

        Args:
            company_id: Mandanten-ID
            days: Prognosezeitraum (30, 60, oder 90)

        Returns:
            Liste von tagesweisen Prognosen
        """
        days = max(7, min(90, days))
        today = date.today()
        end_date = today + timedelta(days=days)

        logger.info(
            "cashflow_forecast_started",
            company_id=str(company_id),
            days=days,
        )

        # 1. Aktuellen Kontostand ermitteln
        current_balance = await self._get_current_balance(company_id)

        # 2. Offene Forderungen mit Zahlungswahrscheinlichkeiten
        receivables = await self._get_receivables_with_probabilities(company_id, days)

        # 3. Offene Verbindlichkeiten
        payables = await self._get_payables(company_id, days)

        # 4. Tagesweise Aggregation
        predictions: List[CashFlowPrediction] = []
        running_balance = current_balance

        for day_offset in range(days + 1):
            current_date = today + timedelta(days=day_offset)

            # Eingaenge für diesen Tag
            day_inflows_data = [
                r for r in receivables
                if r["predicted_date"] == current_date
            ]

            # Ausgaenge für diesen Tag
            day_outflows_data = [
                p for p in payables
                if p["payment_date"] == current_date
            ]

            # Erwartete Betraege (gewichtet nach Wahrscheinlichkeit)
            expected_inflow = Decimal("0")
            optimistic_inflow = Decimal("0")
            pessimistic_inflow = Decimal("0")
            contributing_invoices: List[UUID] = []
            risk_factors: List[str] = []

            for recv in day_inflows_data:
                amount = recv["amount"]
                prob = recv["probability"]

                expected_inflow += amount * Decimal(str(prob))
                optimistic_inflow += amount  # 100% Zahlung
                pessimistic_inflow += amount * Decimal(str(max(0, prob - 0.2)))
                contributing_invoices.append(recv["invoice_id"])

                if recv.get("risk_factors"):
                    risk_factors.extend(recv["risk_factors"][:2])

            expected_outflow = sum(
                Decimal(str(p["amount"])) for p in day_outflows_data
            )

            net_flow = expected_inflow - expected_outflow
            running_balance += net_flow

            # Confidence Intervals für Balance
            optimistic_balance = running_balance + (optimistic_inflow - expected_inflow)
            pessimistic_balance = running_balance + (pessimistic_inflow - expected_inflow)

            # Risikofaktoren für den Tag
            if running_balance < self.CRITICAL_BALANCE_THRESHOLD:
                risk_factors.append("critical_balance")
            elif running_balance < self.WARNING_BALANCE_THRESHOLD:
                risk_factors.append("low_balance")

            predictions.append(CashFlowPrediction(
                prediction_date=current_date,
                expected_inflows=round(expected_inflow, 2),
                expected_outflows=round(expected_outflow, 2),
                net_cash_flow=round(net_flow, 2),
                confidence_low=round(pessimistic_balance, 2),
                confidence_mid=round(running_balance, 2),
                confidence_high=round(optimistic_balance, 2),
                contributing_invoices=contributing_invoices,
                inflow_count=len(day_inflows_data),
                outflow_count=len(day_outflows_data),
                risk_factors=list(set(risk_factors))[:5],
            ))

        logger.info(
            "cashflow_forecast_completed",
            company_id=str(company_id),
            days=len(predictions),
            min_balance=float(min(p.confidence_mid for p in predictions)),
        )

        return predictions

    async def get_liquidity_alerts(
        self,
        company_id: UUID,
        forecast_days: int = 30,
    ) -> List[LiquidityAlert]:
        """
        Generiert Liquiditaetswarnungen basierend auf Forecast.

        Args:
            company_id: Mandanten-ID
            forecast_days: Vorausschau in Tagen

        Returns:
            Liste von Warnungen sortiert nach Dringlichkeit
        """
        forecast = await self.get_cashflow_forecast(company_id, forecast_days)

        if not forecast:
            return []

        alerts: List[LiquidityAlert] = []
        today = date.today()
        current_balance = await self._get_current_balance(company_id)

        for prediction in forecast:
            days_until = (prediction.prediction_date - today).days

            # 1. Kritischer Engpass
            if prediction.confidence_mid < self.CRITICAL_BALANCE_THRESHOLD:
                alerts.append(LiquidityAlert(
                    alert_type=LiquidityAlertType.CRITICAL_SHORTFALL,
                    severity=AlertSeverity.CRITICAL,
                    trigger_date=prediction.prediction_date,
                    predicted_balance=prediction.confidence_mid,
                    expected_inflows=prediction.expected_inflows,
                    expected_outflows=prediction.expected_outflows,
                    message=(
                        f"Kritischer Liquiditaetsengpass am "
                        f"{prediction.prediction_date.strftime('%d.%m.%Y')}: "
                        f"Prognostizierter Saldo {float(prediction.confidence_mid):,.2f} EUR"
                    ),
                    recommendations=[
                        "Zahlungseingaenge beschleunigen (Skonto anbieten)",
                        "Nicht-kritische Zahlungen verschieben",
                        "Kontokorrent-Kredit prüfen",
                        "Grosskunden zu schnellerer Zahlung auffordern",
                    ],
                    days_until_trigger=days_until,
                ))

            # 2. Cashflow-Gap (Ausgaenge > Eingaenge an diesem Tag)
            elif prediction.expected_outflows > prediction.expected_inflows * Decimal("1.5"):
                if prediction.expected_outflows > Decimal("5000"):
                    alerts.append(LiquidityAlert(
                        alert_type=LiquidityAlertType.CASHFLOW_GAP,
                        severity=AlertSeverity.WARNING,
                        trigger_date=prediction.prediction_date,
                        predicted_balance=prediction.confidence_mid,
                        expected_inflows=prediction.expected_inflows,
                        expected_outflows=prediction.expected_outflows,
                        message=(
                            f"Cashflow-Lücke am {prediction.prediction_date.strftime('%d.%m.%Y')}: "
                            f"Ausgaenge ({float(prediction.expected_outflows):,.2f} EUR) "
                            f"übersteigen Eingaenge ({float(prediction.expected_inflows):,.2f} EUR)"
                        ),
                        recommendations=[
                            "Zahlungseingaenge für diesen Tag prüfen",
                            "Ausgaben-Verschiebung erwaegen",
                        ],
                        days_until_trigger=days_until,
                    ))

            # 3. Niedrige Balance-Warnung
            elif prediction.confidence_mid < self.WARNING_BALANCE_THRESHOLD:
                if prediction.confidence_mid < self.WARNING_BALANCE_THRESHOLD * Decimal("0.5"):
                    severity = AlertSeverity.WARNING
                else:
                    severity = AlertSeverity.INFO

                alerts.append(LiquidityAlert(
                    alert_type=LiquidityAlertType.CASHFLOW_GAP,
                    severity=severity,
                    trigger_date=prediction.prediction_date,
                    predicted_balance=prediction.confidence_mid,
                    expected_inflows=prediction.expected_inflows,
                    expected_outflows=prediction.expected_outflows,
                    message=(
                        f"Niedriger Kontostand am {prediction.prediction_date.strftime('%d.%m.%Y')}: "
                        f"Nur {float(prediction.confidence_mid):,.2f} EUR verfügbar"
                    ),
                    recommendations=[
                        "Forderungsmanagement intensivieren",
                        "Liquiditaetsreserve prüfen",
                    ],
                    days_until_trigger=days_until,
                ))

        # Trend-basierte Warnung
        if len(forecast) >= 7:
            first_week_avg = sum(p.confidence_mid for p in forecast[:7]) / 7
            last_week_avg = sum(p.confidence_mid for p in forecast[-7:]) / 7
            trend_decline = first_week_avg - last_week_avg

            if trend_decline > first_week_avg * Decimal("0.3"):
                alerts.append(LiquidityAlert(
                    alert_type=LiquidityAlertType.TREND_NEGATIVE,
                    severity=AlertSeverity.WARNING,
                    trigger_date=today,
                    predicted_balance=first_week_avg,
                    expected_inflows=Decimal("0"),
                    expected_outflows=Decimal("0"),
                    message=(
                        f"Negativer Liquiditaetstrend: Rückgang um "
                        f"{float(trend_decline):,.2f} EUR im Prognosezeitraum"
                    ),
                    recommendations=[
                        "Ursachen für Rückgang analysieren",
                        "Einnahmequellen diversifizieren",
                        "Kostensenkungsmassnahmen prüfen",
                    ],
                    days_until_trigger=0,
                ))

        # High-Risk Concentration Check
        high_risk_count = await self._count_high_risk_entities(company_id)
        total_entities = await self._count_active_entities(company_id)

        if total_entities > 0:
            high_risk_ratio = high_risk_count / total_entities
            if high_risk_ratio > 0.3:  # > 30% High-Risk
                alerts.append(LiquidityAlert(
                    alert_type=LiquidityAlertType.HIGH_RISK_CONCENTRATION,
                    severity=AlertSeverity.WARNING,
                    trigger_date=today,
                    predicted_balance=current_balance,
                    expected_inflows=Decimal("0"),
                    expected_outflows=Decimal("0"),
                    message=(
                        f"Hohe Konzentration von High-Risk Geschäftspartnern: "
                        f"{high_risk_count} von {total_entities} ({high_risk_ratio*100:.0f}%)"
                    ),
                    recommendations=[
                        "Portfolio-Diversifikation verbessern",
                        "Kreditlimits für High-Risk Entities prüfen",
                        "Vorkasse-Optionen für High-Risk Entities einfordern",
                    ],
                    days_until_trigger=0,
                ))

        # Sortieren nach Severity und Datum
        severity_order = {
            AlertSeverity.CRITICAL: 0,
            AlertSeverity.WARNING: 1,
            AlertSeverity.INFO: 2,
        }
        alerts.sort(key=lambda a: (severity_order[a.severity], a.days_until_trigger))

        # Deduplizierung: Max eine Warnung pro Typ und Tag
        seen: set = set()
        unique_alerts: List[LiquidityAlert] = []
        for alert in alerts:
            key = (alert.alert_type, alert.trigger_date)
            if key not in seen:
                seen.add(key)
                unique_alerts.append(alert)

        return unique_alerts[:15]  # Max 15 Warnungen

    async def update_all_entity_profiles(
        self,
        company_id: UUID,
        limit: int = 100,
    ) -> int:
        """
        Aktualisiert alle Entity-Profile für ein Unternehmen.

        Wird woechentlich via Celery Task ausgeführt.

        Args:
            company_id: Mandanten-ID
            limit: Maximale Anzahl zu aktualisierender Entities

        Returns:
            Anzahl aktualisierter Profile
        """
        # Alle aktiven Entities mit Rechnungshistorie
        result = await self.db.execute(
            select(BusinessEntity.id)
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
            .limit(limit)
        )
        entity_ids = [row[0] for row in result.fetchall()]

        updated_count = 0
        for entity_id in entity_ids:
            try:
                profile = await self.get_entity_payment_profile(
                    entity_id, company_id, force_refresh=True
                )
                if profile:
                    updated_count += 1
            except Exception as e:
                logger.warning(
                    "entity_profile_update_failed",
                    entity_id=str(entity_id),
                    error=str(e),
                )

        logger.info(
            "entity_profiles_updated",
            company_id=str(company_id),
            count=updated_count,
        )

        return updated_count

    # =========================================================================
    # PRIVATE METHODS - Hilfsfunktionen
    # =========================================================================

    async def _get_payment_history(
        self,
        entity_id: UUID,
        company_id: UUID,
        lookback_months: int = 24,
    ) -> List[Dict[str, Any]]:
        """Holt historische Zahlungsdaten einer Entity."""
        cutoff = utc_now() - timedelta(days=lookback_months * 30)

        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at.isnot(None),
                    InvoiceTracking.due_date.isnot(None),
                    InvoiceTracking.paid_at >= cutoff,
                )
            )
            .order_by(InvoiceTracking.paid_at.asc())
        )
        invoices = result.scalars().all()

        history = []
        for inv in invoices:
            if inv.paid_at and inv.due_date:
                # Timezone-aware Vergleich
                paid_date = inv.paid_at.replace(tzinfo=None) if inv.paid_at.tzinfo else inv.paid_at
                due_date_val = inv.due_date.replace(tzinfo=None) if inv.due_date.tzinfo else inv.due_date
                delay = (paid_date - due_date_val).days

                history.append({
                    "invoice_id": inv.id,
                    "amount": float(inv.amount or 0),
                    "due_date": inv.due_date,
                    "paid_at": inv.paid_at,
                    "delay_days": delay,
                    "month": inv.paid_at.month,
                    "quarter": (inv.paid_at.month - 1) // 3 + 1,
                })

        return history

    def _calculate_consistency(
        self,
        delays: List[int],
    ) -> Tuple[PaymentConsistency, float]:
        """Berechnet die Zahlungskonsistenz."""
        if not delays:
            return PaymentConsistency.VARIABLE, 0.0

        avg_delay = statistics.mean(delays)
        stddev = statistics.stdev(delays) if len(delays) > 1 else 0.0

        # Konsistenz-Score: CV (Variationskoeffizient)
        cv = stddev / (abs(avg_delay) + 0.1)
        consistency_score = max(0, 1.0 - cv)

        # Early payers (avg < -3 Tage)
        early_count = sum(1 for d in delays if d < -3)
        early_ratio = early_count / len(delays)

        # On-time payers (+/- 3 Tage)
        on_time_count = sum(1 for d in delays if -3 <= d <= 3)
        on_time_ratio = on_time_count / len(delays)

        # Late payers (> 3 Tage)
        late_count = sum(1 for d in delays if d > 3)
        late_ratio = late_count / len(delays)

        # Very late (> 30 Tage)
        very_late_count = sum(1 for d in delays if d > 30)
        very_late_ratio = very_late_count / len(delays)

        # Klassifizierung
        if early_ratio >= 0.7:
            return PaymentConsistency.ALWAYS_EARLY, consistency_score
        elif on_time_ratio >= 0.7:
            return PaymentConsistency.ALWAYS_ON_TIME, consistency_score
        elif on_time_ratio + early_ratio >= 0.7:
            return PaymentConsistency.MOSTLY_ON_TIME, consistency_score
        elif very_late_ratio >= 0.3:
            return PaymentConsistency.HIGH_RISK, consistency_score * 0.5
        elif late_ratio >= 0.7:
            return PaymentConsistency.ALWAYS_LATE, consistency_score
        else:
            return PaymentConsistency.VARIABLE, consistency_score * 0.7

    async def _detect_seasonal_pattern(
        self,
        payment_history: List[Dict[str, Any]],
    ) -> Optional[SeasonalPattern]:
        """Erkennt saisonale Zahlungsmuster."""
        if len(payment_history) < self.MIN_SAMPLES_FOR_PATTERN * 2:
            return None

        # Gruppiere nach Monat
        monthly_delays: Dict[int, List[int]] = {i: [] for i in range(1, 13)}
        for payment in payment_history:
            month = payment["month"]
            delay = payment["delay_days"]
            monthly_delays[month].append(delay)

        # Berechne Durchschnitt pro Monat (nur Monate mit Daten)
        monthly_avgs: Dict[int, float] = {}
        for month, delays in monthly_delays.items():
            if len(delays) >= 2:
                monthly_avgs[month] = statistics.mean(delays)

        if len(monthly_avgs) < 6:
            return None

        # Gesamtdurchschnitt
        all_delays = [d for delays in monthly_delays.values() for d in delays]
        overall_avg = statistics.mean(all_delays)

        # Signifikante Abweichungen finden
        high_delay_months: List[int] = []
        low_delay_months: List[int] = []

        for month, avg in monthly_avgs.items():
            deviation = (avg - overall_avg) / (overall_avg + 0.1)
            if deviation > self.SEASONAL_SIGNIFICANCE_THRESHOLD:
                high_delay_months.append(month)
            elif deviation < -self.SEASONAL_SIGNIFICANCE_THRESHOLD:
                low_delay_months.append(month)

        # Muster klassifizieren
        if 7 in high_delay_months or 8 in high_delay_months:
            affected = [m for m in [7, 8] if m in high_delay_months]
            avg_adjustment = statistics.mean(
                [monthly_avgs[m] - overall_avg for m in affected]
            )
            return SeasonalPattern(
                pattern_type=SeasonalPatternType.SUMMER_SLOW,
                affected_months=affected,
                avg_delay_adjustment=avg_adjustment,
                confidence=0.7,
                description="Längere Zahlungsdauer im Sommer (Urlaubszeit)",
            )

        if 11 in high_delay_months or 12 in high_delay_months:
            affected = [m for m in [11, 12] if m in high_delay_months]
            avg_adjustment = statistics.mean(
                [monthly_avgs[m] - overall_avg for m in affected]
            )
            return SeasonalPattern(
                pattern_type=SeasonalPatternType.Q4_DELAY,
                affected_months=affected,
                avg_delay_adjustment=avg_adjustment,
                confidence=0.7,
                description="Verzögerungen im Q4 (Jahresendgeschäft)",
            )

        if 7 in low_delay_months or 8 in low_delay_months:
            affected = [m for m in [7, 8] if m in low_delay_months]
            avg_adjustment = statistics.mean(
                [monthly_avgs[m] - overall_avg for m in affected]
            )
            return SeasonalPattern(
                pattern_type=SeasonalPatternType.SUMMER_EARLY,
                affected_months=affected,
                avg_delay_adjustment=avg_adjustment,
                confidence=0.6,
                description="Frühzahlung im Sommer",
            )

        # Quartals-Muster prüfen
        q_ends = [3, 6, 9, 12]
        q_end_in_high = [m for m in q_ends if m in high_delay_months]
        if len(q_end_in_high) >= 2:
            avg_adjustment = statistics.mean(
                [monthly_avgs[m] - overall_avg for m in q_end_in_high]
            )
            return SeasonalPattern(
                pattern_type=SeasonalPatternType.QUARTER_END,
                affected_months=q_end_in_high,
                avg_delay_adjustment=avg_adjustment,
                confidence=0.65,
                description="Verzögerte Zahlungen zum Quartalsende",
            )

        return None

    async def _get_entity_risk_scores(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Tuple[float, float]:
        """Holt Risk Score und Payment Behavior Score einer Entity."""
        result = await self.db.execute(
            select(
                BusinessEntity.risk_score,
                BusinessEntity.payment_behavior_score,
            )
            .where(
                and_(
                    BusinessEntity.id == entity_id,
                    BusinessEntity.company_id == company_id,
                )
            )
        )
        row = result.first()

        if row:
            return (
                float(row.risk_score or 50),
                float(row.payment_behavior_score or 50),
            )

        return 50.0, 50.0

    def _calculate_payment_probability(
        self,
        avg_delay: float,
        stddev: float,
        consistency_score: float,
        risk_score: float,
        sample_count: int,
    ) -> float:
        """Berechnet die Zahlungswahrscheinlichkeit."""
        # Basis-Wahrscheinlichkeit aus Delay
        # Je kürzer der Delay, desto höher die Wahrscheinlichkeit
        delay_factor = 1.0 - min(1.0, avg_delay / 60)  # 0-60 Tage -> 1-0

        # Konsistenz-Faktor
        consistency_factor = 0.5 + 0.5 * consistency_score

        # Risk-Faktor (100 = max Risiko)
        risk_factor = 1.0 - (risk_score / 200)  # 0-100 -> 1-0.5

        # Sample-Count Faktor (mehr Daten = höhere Konfidenz)
        sample_factor = min(1.0, 0.5 + sample_count * 0.05)

        # Kombinierte Wahrscheinlichkeit
        probability = (
            delay_factor * 0.35 +
            consistency_factor * 0.25 +
            risk_factor * 0.25 +
            sample_factor * 0.15
        )

        return max(0.1, min(0.95, probability))

    def _get_amount_delay_factor(self, amount: Decimal) -> float:
        """Betragsabhängiger Verzögerungsfaktor."""
        if amount < 500:
            return 0.9
        elif amount < 2000:
            return 1.0
        elif amount < 10000:
            return 1.1
        elif amount < 50000:
            return 1.2
        else:
            return 1.3

    async def _get_current_balance(self, company_id: UUID) -> Decimal:
        """Ermittelt den aktuellen Gesamtkontostand."""
        result = await self.db.execute(
            select(func.sum(BankAccount.current_balance))
            .where(
                and_(
                    BankAccount.company_id == company_id,
                    BankAccount.is_active == True,
                    BankAccount.deleted_at.is_(None),
                )
            )
        )
        balance = result.scalar()
        return Decimal(str(balance)) if balance else Decimal("0")

    async def _get_receivables_with_probabilities(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Holt offene Forderungen mit Zahlungswahrscheinlichkeiten."""
        now = utc_now()
        end_date = now + timedelta(days=days * 2)  # Extra Puffer für verzögerte Zahlungen

        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    is_outgoing_invoice(),
                    InvoiceTracking.status.in_(["open", "sent", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        invoices = result.scalars().all()

        receivables = []
        for inv in invoices:
            # Zahlungswahrscheinlichkeit berechnen
            prob = await self.get_invoice_payment_probability(inv.id, company_id)

            if prob and prob.predicted_payment_date <= date.today() + timedelta(days=days):
                receivables.append({
                    "invoice_id": inv.id,
                    "amount": prob.amount,
                    "predicted_date": prob.predicted_payment_date,
                    "probability": prob.probability,
                    "risk_factors": prob.risk_factors,
                })

        return receivables

    async def _get_payables(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Holt offene Verbindlichkeiten."""
        now = utc_now()
        end_date = now + timedelta(days=days)

        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    is_incoming_invoice(),
                    InvoiceTracking.status.in_(["open", "sent"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        invoices = result.scalars().all()

        payables = []
        for inv in invoices:
            due = inv.due_date or (inv.invoice_date + timedelta(days=30) if inv.invoice_date else now + timedelta(days=30))
            due_date = due.date() if isinstance(due, datetime) else due

            if due_date <= date.today() + timedelta(days=days):
                # Skonto-Deadline prüfen
                payment_date = due_date
                amount = float(inv.amount or 0)

                if inv.skonto_deadline and inv.skonto_percentage:
                    skonto_date = inv.skonto_deadline.date() if isinstance(inv.skonto_deadline, datetime) else inv.skonto_deadline
                    if skonto_date >= date.today():
                        payment_date = skonto_date
                        amount = amount * (1 - inv.skonto_percentage / 100)

                payables.append({
                    "invoice_id": inv.id,
                    "amount": amount,
                    "payment_date": payment_date,
                })

        return payables

    async def _count_high_risk_entities(self, company_id: UUID) -> int:
        """Zaehlt High-Risk Entities."""
        result = await self.db.execute(
            select(func.count(BusinessEntity.id))
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                    BusinessEntity.risk_score >= self.HIGH_RISK_ENTITY_THRESHOLD,
                )
            )
        )
        return result.scalar() or 0

    async def _count_active_entities(self, company_id: UUID) -> int:
        """Zaehlt aktive Entities."""
        result = await self.db.execute(
            select(func.count(BusinessEntity.id))
            .where(
                and_(
                    BusinessEntity.company_id == company_id,
                    BusinessEntity.is_active == True,
                    BusinessEntity.deleted_at.is_(None),
                )
            )
        )
        return result.scalar() or 0


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


_service_instance: Optional[CashflowPredictorService] = None


def get_cashflow_predictor_service(db: AsyncSession) -> CashflowPredictorService:
    """Factory-Funktion für CashflowPredictorService."""
    return CashflowPredictorService(db)
