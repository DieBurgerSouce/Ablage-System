# -*- coding: utf-8 -*-
"""
Cashflow Prediction Service - Monte Carlo basierte Liquiditaetsprognose.

Enterprise Feature: Februar 2026

Funktionen:
- 30/60/90-Tage Liquiditaetsprognose mit Unsicherheitsbereichen
- Monte Carlo Simulation für probabilistische Vorhersagen
- Payment Delay Analyse basierend auf historischem Kundenverhalten
- Frühwarnsystem für Liquiditaetsengpaesse
- What-If Szenario-Simulation
- Integration mit InvoiceTracking, RiskScoring, Banking

SECURITY:
- NIEMALS Entity-Namen, Kundennummern oder IBANs loggen (PII)
- Alle Betraege werden nur aggregiert ausgegeben
- Company-Isolation via company_id Filter

Feinpoliert und durchdacht.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union
from uuid import UUID

# Type aliases for JSON data
JSONValue = Union[str, int, float, bool, None, Dict[str, "JSONValue"], List["JSONValue"]]
JSONDict = Dict[str, JSONValue]
import math
import random
import statistics

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    BankAccount,
    BankTransaction,
    BusinessEntity,
    Document,
    InvoiceTracking,
)
from app.services.ai.predictive_payment_service import SEASONAL_DELAY_FACTORS

logger = structlog.get_logger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================


class WarningSeverity(str, Enum):
    """Schweregrade für Cashflow-Warnungen."""

    INFO = "info"  # Informativ, keine Aktion erforderlich
    WARNING = "warning"  # Aufmerksamkeit erforderlich
    CRITICAL = "critical"  # Sofortige Aktion erforderlich


class WarningType(str, Enum):
    """Typen von Cashflow-Warnungen."""

    SHORTFALL = "shortfall"  # Liquiditaetsengpass
    LOW_BALANCE = "low_balance"  # Niedriger Kontostand
    LARGE_OUTGOING = "large_outgoing"  # Grosse anstehende Zahlung
    TREND_NEGATIVE = "trend_negative"  # Negativer Trend
    HIGH_UNCERTAINTY = "high_uncertainty"  # Hohe Prognose-Unsicherheit


class ScenarioType(str, Enum):
    """Typen von What-If Szenarien."""

    CUSTOMER_LATE_PAYMENT = "customer_late_payment"  # Kunde zahlt spät
    DELAY_OUTGOING = "delay_outgoing"  # Eigene Zahlung verschieben
    NEW_ORDER = "new_order"  # Neuer Auftrag
    CUSTOMER_DEFAULT = "customer_default"  # Kundenausfall
    ACCELERATE_COLLECTION = "accelerate_collection"  # Forderungseinzug beschleunigen


# Konfigurationskonstanten
MONTE_CARLO_ITERATIONS = 1000  # Anzahl Simulationen
DEFAULT_CONFIDENCE_LEVEL = 0.9  # 90% Konfidenzintervall
LOW_BALANCE_THRESHOLD_DAYS = 30  # Liquiditaet für X Tage
CRITICAL_BALANCE_EUR = Decimal("0")  # Kritische Schwelle
WARNING_BALANCE_EUR = Decimal("5000")  # Warnschwelle

# Payment Delay Faktoren (historisch kalibriert)
PAYMENT_DELAY_WEIGHTS = {
    "excellent": {"mean_days": 5, "stddev": 2},  # Zahlungsverhalten 90-100
    "good": {"mean_days": 10, "stddev": 5},  # 70-89
    "average": {"mean_days": 20, "stddev": 10},  # 50-69
    "poor": {"mean_days": 35, "stddev": 15},  # 30-49
    "high_risk": {"mean_days": 60, "stddev": 25},  # 0-29
    "unknown": {"mean_days": 25, "stddev": 15},  # Keine Historie
}


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class PaymentDelayStats:
    """Statistiken zum Zahlungsverhalten eines Kunden."""

    entity_id: UUID
    average_delay_days: float
    std_deviation: float
    sample_count: int
    payment_behavior_score: float  # 0-100 (höher = besser)
    risk_score: float  # 0-100 (höher = riskanter)
    last_payment_date: Optional[datetime] = None


@dataclass
class CashflowForecast:
    """Tagesweise Cashflow-Prognose mit Unsicherheitsbereichen."""

    date: date
    predicted_balance: Decimal
    lower_bound: Decimal  # Unteres Konfidenzintervall (z.B. 10. Perzentil)
    upper_bound: Decimal  # Oberes Konfidenzintervall (z.B. 90. Perzentil)
    incoming: Decimal  # Erwartete Eingaenge
    outgoing: Decimal  # Erwartete Ausgaenge
    confidence: float  # Gesamt-Konfidenz 0-1
    incoming_count: int = 0  # Anzahl erwarteter Eingaenge
    outgoing_count: int = 0  # Anzahl erwarteter Ausgaenge


@dataclass
class CashflowWarning:
    """Cashflow-Warnung mit Handlungsempfehlung."""

    type: WarningType
    severity: WarningSeverity
    date: date
    predicted_balance: Decimal
    message: str  # German
    suggested_actions: List[str]  # German
    days_until_trigger: int = 0
    affected_amount: Optional[Decimal] = None


@dataclass
class ScenarioResult:
    """Ergebnis einer Szenario-Simulation."""

    scenario_type: ScenarioType
    description: str  # German
    impact_on_min_balance: Decimal
    impact_on_avg_balance: Decimal
    new_forecasts: List[CashflowForecast]
    risk_assessment: str  # German
    recommendations: List[str]  # German


@dataclass
class PredictionMetrics:
    """Metriken zur Vorhersagegenauigkeit."""

    total_predictions: int
    correct_predictions: int
    mean_absolute_error_days: float
    accuracy_rate: float
    last_evaluated: datetime
    # True, wenn die Genauigkeit auf einer Schaetzung (Proxy aus Entity-Historie)
    # statt auf gespeicherten historischen Vorhersagen basiert (M13-Transparenz).
    is_estimated: bool = False


@dataclass
class RecurringPattern:
    """Erkanntes wiederkehrendes Zahlungsmuster."""

    pattern_type: str  # "income" oder "expense"
    amount: Decimal
    frequency_days: int
    next_expected_date: date
    confidence: float
    description: str


# =============================================================================
# SERVICE CLASS
# =============================================================================


class CashflowPredictionService:
    """
    Service für ML-basierte Cashflow-Vorhersagen.

    Kombiniert:
    - Historische Zahlungsmuster-Analyse
    - Monte Carlo Simulation für Unsicherheitsquantifizierung
    - Integration mit RiskScoring für Kundenrisiko-Bewertung
    - What-If Szenario-Analyse

    SECURITY:
    - Alle Abfragen mit company_id Filter (Multi-Tenant)
    - Keine PII in Logs (Entity-Namen, Kundennummern)
    - Betraege nur aggregiert ausgeben
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiere Service mit Datenbankverbindung.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db
        self._delay_stats_cache: Dict[UUID, PaymentDelayStats] = {}
        self._recurring_patterns_cache: Optional[List[RecurringPattern]] = None

    # =========================================================================
    # PUBLIC METHODS - Hauptfunktionen
    # =========================================================================

    async def get_cashflow_forecast(
        self,
        company_id: UUID,
        days: int = 90,
        confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
        include_recurring: bool = True,
    ) -> List[CashflowForecast]:
        """
        Erstellt eine Cashflow-Prognose für die nächsten X Tage.

        Verwendet Monte Carlo Simulation für Unsicherheitsbereiche.

        Args:
            company_id: Mandanten-ID (Multi-Tenant Filter)
            days: Prognosezeitraum in Tagen (7-90)
            confidence_level: Konfidenzintervall (0.8-0.99)
            include_recurring: Wiederkehrende Muster einbeziehen

        Returns:
            Liste von tagesweisen Prognosen mit Unsicherheitsbereichen

        Raises:
            ValueError: Bei ungültigen Parametern
        """
        # Validierung
        days = max(7, min(90, days))
        confidence_level = max(0.8, min(0.99, confidence_level))

        logger.info(
            "cashflow_forecast_started",
            company_id=str(company_id),
            days=days,
            confidence_level=confidence_level,
        )

        # 1. Aktuellen Kontostand ermitteln
        current_balance = await self._get_current_balance(company_id)

        # 2. Offene Forderungen (erwartete Eingaenge)
        receivables = await self._get_open_receivables(company_id, days)

        # 3. Offene Verbindlichkeiten (erwartete Ausgaenge)
        payables = await self._get_open_payables(company_id, days)

        # 4. Wiederkehrende Muster erkennen
        recurring = []
        if include_recurring:
            recurring = await self._detect_recurring_patterns(company_id, days)

        # 5. Monte Carlo Simulation durchführen
        forecasts = await self._run_monte_carlo_simulation(
            current_balance=current_balance,
            receivables=receivables,
            payables=payables,
            recurring=recurring,
            days=days,
            confidence_level=confidence_level,
            company_id=company_id,
        )

        logger.info(
            "cashflow_forecast_completed",
            company_id=str(company_id),
            forecast_days=len(forecasts),
            min_balance=float(min(f.predicted_balance for f in forecasts)) if forecasts else 0,
        )

        return forecasts

    async def get_cashflow_warnings(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> List[CashflowWarning]:
        """
        Generiert Warnungen für bevorstehende Cashflow-Probleme.

        Args:
            company_id: Mandanten-ID
            days: Vorausschau in Tagen

        Returns:
            Liste von Warnungen sortiert nach Dringlichkeit
        """
        logger.info(
            "cashflow_warnings_requested",
            company_id=str(company_id),
            days=days,
        )

        # Prognose erstellen
        forecasts = await self.get_cashflow_forecast(company_id, days)

        warnings: List[CashflowWarning] = []
        today = date.today()

        # Durchschnittlichen täglichen Abfluss berechnen
        avg_daily_outflow = Decimal("0")
        if forecasts:
            total_outflow = sum(f.outgoing for f in forecasts)
            avg_daily_outflow = total_outflow / len(forecasts) if len(forecasts) > 0 else Decimal("0")

        for forecast in forecasts:
            days_until = (forecast.date - today).days

            # 1. Liquiditaetsengpass (negativ)
            if forecast.predicted_balance < CRITICAL_BALANCE_EUR:
                warnings.append(CashflowWarning(
                    type=WarningType.SHORTFALL,
                    severity=WarningSeverity.CRITICAL,
                    date=forecast.date,
                    predicted_balance=forecast.predicted_balance,
                    message=f"Kritischer Liquiditaetsengpass am {forecast.date.strftime('%d.%m.%Y')}: "
                            f"Prognostizierter Saldo {float(forecast.predicted_balance):,.2f} EUR",
                    suggested_actions=[
                        "Zahlungseingaenge beschleunigen (Skonto anbieten)",
                        "Nicht-kritische Zahlungen verschieben",
                        "Kontokorrent-Kredit in Betracht ziehen",
                        "Grosskunden zu schnellerer Zahlung auffordern",
                    ],
                    days_until_trigger=days_until,
                    affected_amount=abs(forecast.predicted_balance) if forecast.predicted_balance < 0 else None,
                ))

            # 2. Niedriger Kontostand (unter Schwelle)
            elif forecast.predicted_balance < WARNING_BALANCE_EUR:
                warnings.append(CashflowWarning(
                    type=WarningType.LOW_BALANCE,
                    severity=WarningSeverity.WARNING,
                    date=forecast.date,
                    predicted_balance=forecast.predicted_balance,
                    message=f"Niedriger Kontostand am {forecast.date.strftime('%d.%m.%Y')}: "
                            f"Nur {float(forecast.predicted_balance):,.2f} EUR verfügbar",
                    suggested_actions=[
                        "Forderungsmanagement intensivieren",
                        "Zahlungsziele bei Lieferanten verlängern",
                        "Liquiditaetsreserve prüfen",
                    ],
                    days_until_trigger=days_until,
                ))

            # 3. Grosse anstehende Zahlung (>20% des aktuellen Saldos)
            current_balance = forecasts[0].predicted_balance if forecasts else Decimal("0")
            if current_balance > 0 and forecast.outgoing > current_balance * Decimal("0.2"):
                # Nur einmal pro grosse Zahlung warnen
                warnings.append(CashflowWarning(
                    type=WarningType.LARGE_OUTGOING,
                    severity=WarningSeverity.INFO,
                    date=forecast.date,
                    predicted_balance=forecast.predicted_balance,
                    message=f"Grosse Zahlung am {forecast.date.strftime('%d.%m.%Y')}: "
                            f"{float(forecast.outgoing):,.2f} EUR",
                    suggested_actions=[
                        "Liquiditaet für diesen Tag sicherstellen",
                        "Ggf. Zahlung in Teilen leisten",
                    ],
                    days_until_trigger=days_until,
                    affected_amount=forecast.outgoing,
                ))

            # 4. Hohe Unsicherheit in der Prognose
            if forecast.confidence < 0.5:
                warnings.append(CashflowWarning(
                    type=WarningType.HIGH_UNCERTAINTY,
                    severity=WarningSeverity.INFO,
                    date=forecast.date,
                    predicted_balance=forecast.predicted_balance,
                    message=f"Hohe Unsicherheit für {forecast.date.strftime('%d.%m.%Y')}: "
                            f"Spanne {float(forecast.lower_bound):,.2f} bis {float(forecast.upper_bound):,.2f} EUR",
                    suggested_actions=[
                        "Zahlungsstatus bei offenen Forderungen prüfen",
                        "Rücksprache mit Kunden halten",
                    ],
                    days_until_trigger=days_until,
                ))

        # Trend-basierte Warnung (fallender Trend über 7 Tage)
        if len(forecasts) >= 7:
            first_week_avg = sum(f.predicted_balance for f in forecasts[:7]) / 7
            last_week_start = len(forecasts) - 7
            last_week_avg = sum(f.predicted_balance for f in forecasts[last_week_start:]) / 7

            trend_decline = first_week_avg - last_week_avg
            if trend_decline > first_week_avg * Decimal("0.3"):  # >30% Rückgang
                warnings.append(CashflowWarning(
                    type=WarningType.TREND_NEGATIVE,
                    severity=WarningSeverity.WARNING,
                    date=today,
                    predicted_balance=first_week_avg,
                    message=f"Negativer Liquiditaetstrend: Rückgang um {float(trend_decline):,.2f} EUR "
                            f"im Prognosezeitraum",
                    suggested_actions=[
                        "Ursachen für Rückgang analysieren",
                        "Einnahmequellen diversifizieren",
                        "Kostensenkungsmassnahmen prüfen",
                    ],
                    days_until_trigger=0,
                    affected_amount=trend_decline,
                ))

        # Sortieren nach Dringlichkeit (kritisch zuerst, dann nach Datum)
        severity_order = {
            WarningSeverity.CRITICAL: 0,
            WarningSeverity.WARNING: 1,
            WarningSeverity.INFO: 2,
        }
        warnings.sort(key=lambda w: (severity_order[w.severity], w.days_until_trigger))

        # Deduplizierung: Maximal eine Warnung pro Typ und Datum
        seen: set = set()
        unique_warnings: List[CashflowWarning] = []
        for w in warnings:
            key = (w.type, w.date)
            if key not in seen:
                seen.add(key)
                unique_warnings.append(w)

        logger.info(
            "cashflow_warnings_generated",
            company_id=str(company_id),
            warning_count=len(unique_warnings),
            critical_count=sum(1 for w in unique_warnings if w.severity == WarningSeverity.CRITICAL),
        )

        return unique_warnings[:20]  # Maximal 20 Warnungen

    async def simulate_scenario(
        self,
        company_id: UUID,
        scenario_type: ScenarioType,
        parameters: JSONDict,
    ) -> ScenarioResult:
        """
        Führt eine What-If Szenario-Simulation durch.

        Args:
            company_id: Mandanten-ID
            scenario_type: Art des Szenarios
            parameters: Szenario-spezifische Parameter

        Returns:
            Ergebnis der Simulation mit Empfehlungen

        Supported scenarios:
        - CUSTOMER_LATE_PAYMENT: {"entity_id": UUID, "delay_days": int}
        - DELAY_OUTGOING: {"invoice_id": UUID, "delay_days": int}
        - NEW_ORDER: {"amount": float, "payment_due_days": int}
        - CUSTOMER_DEFAULT: {"entity_id": UUID}
        - ACCELERATE_COLLECTION: {"days_improvement": int}
        """
        logger.info(
            "scenario_simulation_started",
            company_id=str(company_id),
            scenario_type=scenario_type.value,
        )

        # Basis-Prognose (ohne Szenario)
        base_forecasts = await self.get_cashflow_forecast(company_id, days=30)

        if not base_forecasts:
            return ScenarioResult(
                scenario_type=scenario_type,
                description="Keine Basisdaten verfügbar",
                impact_on_min_balance=Decimal("0"),
                impact_on_avg_balance=Decimal("0"),
                new_forecasts=[],
                risk_assessment="Nicht bewertbar - keine Daten",
                recommendations=["Kontodaten und offene Rechnungen prüfen"],
            )

        base_min = min(f.predicted_balance for f in base_forecasts)
        base_avg = sum(f.predicted_balance for f in base_forecasts) / len(base_forecasts)

        # Szenario-spezifische Berechnung
        if scenario_type == ScenarioType.CUSTOMER_LATE_PAYMENT:
            result = await self._simulate_customer_late_payment(
                company_id, base_forecasts, parameters
            )

        elif scenario_type == ScenarioType.DELAY_OUTGOING:
            result = await self._simulate_delay_outgoing(
                company_id, base_forecasts, parameters
            )

        elif scenario_type == ScenarioType.NEW_ORDER:
            result = await self._simulate_new_order(
                company_id, base_forecasts, parameters
            )

        elif scenario_type == ScenarioType.CUSTOMER_DEFAULT:
            result = await self._simulate_customer_default(
                company_id, base_forecasts, parameters
            )

        elif scenario_type == ScenarioType.ACCELERATE_COLLECTION:
            result = await self._simulate_accelerate_collection(
                company_id, base_forecasts, parameters
            )

        else:
            result = ScenarioResult(
                scenario_type=scenario_type,
                description=f"Unbekannter Szenario-Typ: {scenario_type.value}",
                impact_on_min_balance=Decimal("0"),
                impact_on_avg_balance=Decimal("0"),
                new_forecasts=base_forecasts,
                risk_assessment="Nicht unterstützt",
                recommendations=[],
            )

        # Impact berechnen
        if result.new_forecasts:
            new_min = min(f.predicted_balance for f in result.new_forecasts)
            new_avg = sum(f.predicted_balance for f in result.new_forecasts) / len(result.new_forecasts)
            result.impact_on_min_balance = new_min - base_min
            result.impact_on_avg_balance = new_avg - base_avg

        logger.info(
            "scenario_simulation_completed",
            company_id=str(company_id),
            scenario_type=scenario_type.value,
            impact_min=float(result.impact_on_min_balance),
        )

        return result

    async def get_prediction_metrics(
        self,
        company_id: UUID,
    ) -> PredictionMetrics:
        """
        Ruft Metriken zur Vorhersagegenauigkeit ab.

        Args:
            company_id: Mandanten-ID

        Returns:
            Metriken basierend auf historischen Vorhersagen vs. Ist-Werten
        """
        # M13-TRANSPARENZ: Diese Metrik basiert NICHT auf gespeicherten
        # historischen Vorhersagen, sondern auf einer Schaetzung — als Proxy
        # fuer "die damalige Vorhersage" dient die Entity-Zahlungshistorie.
        # Das Ergebnis wird daher unten transparent als geschaetzt
        # gekennzeichnet (is_estimated=True), statt eine echte Backtest-
        # Genauigkeit vorzutaeuschen.

        now = utc_now()
        cutoff = now - timedelta(days=90)

        # Hole bezahlte Rechnungen der letzten 90 Tage
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at >= cutoff,
                    InvoiceTracking.due_date.isnot(None),
                )
            )
            .limit(500)
        )
        paid_invoices = result.scalars().all()

        total_predictions = len(paid_invoices)
        correct_predictions = 0
        errors: List[float] = []

        for inv in paid_invoices:
            if inv.paid_at and inv.due_date:
                # Tatsaechliche Verzögerung
                actual_delay = (inv.paid_at - inv.due_date).days

                # In Produktion: Gespeicherte Vorhersage laden
                # Hier: Vereinfachte Schätzung basierend auf Entity-Historie
                entity_stats = await self._get_payment_delay_stats(
                    inv.entity_id, company_id
                ) if inv.entity_id else None

                predicted_delay = entity_stats.average_delay_days if entity_stats else 0

                error = abs(actual_delay - predicted_delay)
                errors.append(error)

                # Vorhersage korrekt wenn innerhalb 5 Tage Toleranz
                if error <= 5:
                    correct_predictions += 1

        mae = sum(errors) / len(errors) if errors else 0.0
        accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0.0

        logger.warning(
            "cashflow_prediction_metrics_estimated",
            company_id=str(company_id),
            total_predictions=total_predictions,
            reason="proxy_entity_historie_keine_gespeicherten_predictions",
        )

        return PredictionMetrics(
            total_predictions=total_predictions,
            correct_predictions=correct_predictions,
            mean_absolute_error_days=round(mae, 2),
            accuracy_rate=round(accuracy * 100, 1),
            last_evaluated=now,
            is_estimated=True,
        )

    async def get_payment_delay_analysis(
        self,
        company_id: UUID,
        entity_id: Optional[UUID] = None,
    ) -> List[PaymentDelayStats]:
        """
        Analysiert das Zahlungsverhalten von Kunden.

        Args:
            company_id: Mandanten-ID
            entity_id: Optional - nur für bestimmten Kunden

        Returns:
            Liste von Zahlungsverhaltens-Statistiken
        """
        if entity_id:
            stats = await self._get_payment_delay_stats(entity_id, company_id)
            return [stats] if stats else []

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
            .limit(100)
        )
        entity_ids = [row[0] for row in result.fetchall()]

        stats_list: List[PaymentDelayStats] = []
        for eid in entity_ids:
            stats = await self._get_payment_delay_stats(eid, company_id)
            if stats and stats.sample_count > 0:
                stats_list.append(stats)

        # Sortieren nach Risiko (hoechstes Risiko zuerst)
        stats_list.sort(key=lambda s: s.risk_score, reverse=True)

        return stats_list

    # =========================================================================
    # PRIVATE METHODS - Hilfsfunktionen
    # =========================================================================

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

    async def _get_open_receivables(
        self,
        company_id: UUID,
        days: int,
    ) -> List[JSONDict]:
        """
        Holt offene Forderungen (Ausgangsrechnungen - wir erwarten Geld).

        Returns:
            Liste mit {amount, due_date, entity_id, invoice_id, delay_stats}
        """
        now = utc_now()
        end_date = now + timedelta(days=days)

        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_type == "outgoing",
                    InvoiceTracking.status.in_(["open", "sent", "overdue"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        invoices = result.scalars().all()

        receivables = []
        for inv in invoices:
            # Fälligkeitsdatum oder Schätzung
            due = inv.due_date or (inv.invoice_date + timedelta(days=30) if inv.invoice_date else now + timedelta(days=30))

            # Nur innerhalb des Prognosezeitraums
            if due.date() <= end_date.date():
                # Payment Delay Stats für Entity
                delay_stats = None
                if inv.entity_id:
                    delay_stats = await self._get_payment_delay_stats(inv.entity_id, company_id)

                receivables.append({
                    "amount": Decimal(str(inv.amount or 0)),
                    "due_date": due.date() if isinstance(due, datetime) else due,
                    "entity_id": inv.entity_id,
                    "invoice_id": inv.id,
                    "delay_stats": delay_stats,
                    "dunning_level": inv.dunning_level or 0,
                })

        return receivables

    async def _get_open_payables(
        self,
        company_id: UUID,
        days: int,
    ) -> List[JSONDict]:
        """
        Holt offene Verbindlichkeiten (Eingangsrechnungen - wir müssen zahlen).

        Returns:
            Liste mit {amount, due_date, skonto_deadline, skonto_amount}
        """
        now = utc_now()
        end_date = now + timedelta(days=days)

        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_type == "incoming",
                    InvoiceTracking.status.in_(["open", "sent"]),
                    InvoiceTracking.deleted_at.is_(None),
                )
            )
        )
        invoices = result.scalars().all()

        payables = []
        for inv in invoices:
            due = inv.due_date or (inv.invoice_date + timedelta(days=30) if inv.invoice_date else now + timedelta(days=30))

            if due.date() <= end_date.date():
                # Berechne effektiven Zahlungsbetrag (mit Skonto falls genutzt)
                amount = Decimal(str(inv.amount or 0))
                effective_amount = amount

                # Skonto-Deadline prüfen
                skonto_deadline = None
                skonto_amount = Decimal("0")
                if inv.skonto_deadline and inv.skonto_percentage:
                    skonto_deadline = inv.skonto_deadline.date() if isinstance(inv.skonto_deadline, datetime) else inv.skonto_deadline
                    if skonto_deadline >= date.today():
                        skonto_amount = amount * Decimal(str(inv.skonto_percentage)) / 100
                        effective_amount = amount - skonto_amount

                # Zahlungsdatum: Skonto-Deadline wenn möglich, sonst Due Date
                payment_date = due.date() if isinstance(due, datetime) else due
                if skonto_deadline and skonto_deadline >= date.today():
                    payment_date = skonto_deadline

                payables.append({
                    "amount": effective_amount,
                    "original_amount": amount,
                    "payment_date": payment_date,
                    "due_date": due.date() if isinstance(due, datetime) else due,
                    "skonto_deadline": skonto_deadline,
                    "skonto_amount": skonto_amount,
                    "invoice_id": inv.id,
                })

        return payables

    async def _detect_recurring_patterns(
        self,
        company_id: UUID,
        days: int,
    ) -> List[RecurringPattern]:
        """
        Erkennt wiederkehrende Zahlungsmuster aus historischen Transaktionen.

        Returns:
            Liste von erkannten Mustern (Miete, Gehälter, etc.)
        """
        if self._recurring_patterns_cache is not None:
            return self._recurring_patterns_cache

        # Hole Transaktionen der letzten 6 Monate
        cutoff = utc_now() - timedelta(days=180)

        result = await self.db.execute(
            select(BankTransaction)
            .join(BankAccount)
            .where(
                and_(
                    BankAccount.company_id == company_id,
                    BankTransaction.booking_date >= cutoff,
                )
            )
            .order_by(BankTransaction.booking_date)
            .limit(1000)
        )
        transactions = result.scalars().all()

        # Gruppiere nach Empfänger/Auftraggeber und Betrag
        patterns: List[RecurringPattern] = []

        # Vereinfachte Pattern-Erkennung
        # Gruppiere ähnliche Betraege (+-5%)
        amount_groups: Dict[str, List[Dict]] = {}

        for tx in transactions:
            amount_key = str(round(float(tx.amount) / 100) * 100)  # 100er-Rundung
            if amount_key not in amount_groups:
                amount_groups[amount_key] = []
            amount_groups[amount_key].append({
                "date": tx.booking_date.date() if tx.booking_date else date.today(),
                "amount": Decimal(str(tx.amount)),
                "reference": tx.reference or "",
            })

        for amount_key, txs in amount_groups.items():
            if len(txs) >= 3:  # Mindestens 3 Vorkommen
                # Berechne durchschnittlichen Abstand
                dates = sorted([t["date"] for t in txs])
                intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]

                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    stddev = statistics.stdev(intervals) if len(intervals) > 1 else avg_interval

                    # Nur regelmäßige Muster (CV < 0.3)
                    cv = stddev / avg_interval if avg_interval > 0 else 1.0

                    if cv < 0.3 and 7 <= avg_interval <= 35:  # Woche bis Monat
                        avg_amount = sum(t["amount"] for t in txs) / len(txs)
                        last_date = max(dates)
                        next_date = last_date + timedelta(days=int(avg_interval))

                        # Nur zukünftige Muster
                        if next_date > date.today() and next_date <= date.today() + timedelta(days=days):
                            pattern_type = "expense" if avg_amount < 0 else "income"

                            patterns.append(RecurringPattern(
                                pattern_type=pattern_type,
                                amount=abs(avg_amount),
                                frequency_days=int(avg_interval),
                                next_expected_date=next_date,
                                confidence=1.0 - cv,
                                description=f"Wiederkehrend alle ~{int(avg_interval)} Tage",
                            ))

        self._recurring_patterns_cache = patterns
        return patterns

    async def _get_payment_delay_stats(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Optional[PaymentDelayStats]:
        """
        Berechnet Zahlungsverzögerungs-Statistiken für einen Kunden.

        Uses caching für Performance.
        """
        # Cache prüfen
        if entity_id in self._delay_stats_cache:
            return self._delay_stats_cache[entity_id]

        # Historische bezahlte Rechnungen
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.entity_id == entity_id,
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status == "paid",
                    InvoiceTracking.paid_at.isnot(None),
                    InvoiceTracking.due_date.isnot(None),
                )
            )
            .limit(100)
        )
        invoices = result.scalars().all()

        if not invoices:
            return None

        # Berechne Verzögerungen
        delays: List[float] = []
        last_payment: Optional[datetime] = None

        for inv in invoices:
            if inv.paid_at and inv.due_date:
                delay = (inv.paid_at - inv.due_date).days
                delays.append(float(delay))
                if last_payment is None or inv.paid_at > last_payment:
                    last_payment = inv.paid_at

        if not delays:
            return None

        avg_delay = sum(delays) / len(delays)
        stddev = statistics.stdev(delays) if len(delays) > 1 else 10.0

        # Payment Behavior Score: 100 = immer puenktlich, 0 = immer >60 Tage spät
        # Formel: 100 - min(100, avg_delay * 1.5)
        payment_behavior_score = max(0, 100 - min(100, avg_delay * 1.5))

        # Risk Score aus RiskScoringService (vereinfacht)
        # Höhere Verzögerung = höheres Risiko
        risk_score = min(100, max(0, avg_delay * 2))

        stats = PaymentDelayStats(
            entity_id=entity_id,
            average_delay_days=round(avg_delay, 1),
            std_deviation=round(stddev, 1),
            sample_count=len(delays),
            payment_behavior_score=round(payment_behavior_score, 1),
            risk_score=round(risk_score, 1),
            last_payment_date=last_payment,
        )

        # Cachen
        self._delay_stats_cache[entity_id] = stats
        return stats

    async def _run_monte_carlo_simulation(
        self,
        current_balance: Decimal,
        receivables: List[JSONDict],
        payables: List[JSONDict],
        recurring: List[RecurringPattern],
        days: int,
        confidence_level: float,
        company_id: UUID,
    ) -> List[CashflowForecast]:
        """
        Führt Monte Carlo Simulation für Cashflow-Prognose durch.

        Simuliert N Szenarien mit stochastischen Zahlungseingaengen.
        """
        today = date.today()
        num_days = days + 1  # Inklusive heute

        # Initialisiere Ergebnis-Arrays für alle Simulationen
        balance_simulations: List[List[Decimal]] = []

        for _ in range(MONTE_CARLO_ITERATIONS):
            # Eine Simulation durchführen
            daily_balances: List[Decimal] = []
            running_balance = current_balance

            for day_offset in range(num_days):
                current_date = today + timedelta(days=day_offset)
                day_inflow = Decimal("0")
                day_outflow = Decimal("0")

                # 1. Erwartete Eingaenge (stochastisch)
                for recv in receivables:
                    due_date = recv["due_date"]
                    delay_stats = recv.get("delay_stats")

                    # Simuliere Zahlungsdatum basierend auf historischem Verhalten
                    if delay_stats:
                        mean_delay = delay_stats.average_delay_days
                        std_delay = delay_stats.std_deviation
                    else:
                        # Default für unbekannte Kunden
                        mean_delay = PAYMENT_DELAY_WEIGHTS["unknown"]["mean_days"]
                        std_delay = PAYMENT_DELAY_WEIGHTS["unknown"]["stddev"]

                    # Simuliertes Zahlungsdatum mit Normalverteilung
                    simulated_delay = max(0, random.gauss(mean_delay, std_delay))
                    # Saisonale Verzoegerung einbeziehen
                    projected_month = (due_date + timedelta(days=int(simulated_delay))).month
                    seasonal_factor = SEASONAL_DELAY_FACTORS.get(projected_month, 1.0)
                    simulated_delay *= seasonal_factor
                    simulated_payment_date = due_date + timedelta(days=int(simulated_delay))

                    if simulated_payment_date == current_date:
                        # Zusätzliche Unsicherheit für den Betrag (95-105%)
                        amount_factor = random.uniform(0.95, 1.05)
                        day_inflow += recv["amount"] * Decimal(str(amount_factor))

                # 2. Ausgaenge (weniger stochastisch - wir kontrollieren)
                for pay in payables:
                    payment_date = pay["payment_date"]

                    if payment_date == current_date:
                        # Leichte Variation (99-101%)
                        amount_factor = random.uniform(0.99, 1.01)
                        day_outflow += pay["amount"] * Decimal(str(amount_factor))

                # 3. Wiederkehrende Muster
                for pattern in recurring:
                    if pattern.next_expected_date == current_date:
                        if pattern.pattern_type == "income":
                            day_inflow += pattern.amount * Decimal(str(random.uniform(0.9, 1.1)))
                        else:
                            day_outflow += pattern.amount * Decimal(str(random.uniform(0.95, 1.05)))

                running_balance = running_balance + day_inflow - day_outflow
                daily_balances.append(running_balance)

            balance_simulations.append(daily_balances)

        # Berechne Statistiken aus allen Simulationen
        forecasts: List[CashflowForecast] = []

        lower_percentile = (1 - confidence_level) / 2 * 100  # z.B. 5
        upper_percentile = 100 - lower_percentile  # z.B. 95

        for day_offset in range(num_days):
            current_date = today + timedelta(days=day_offset)

            # Sammle alle simulierten Werte für diesen Tag
            day_balances = [sim[day_offset] for sim in balance_simulations]

            predicted = Decimal(str(statistics.median([float(b) for b in day_balances])))
            lower = Decimal(str(self._percentile([float(b) for b in day_balances], lower_percentile)))
            upper = Decimal(str(self._percentile([float(b) for b in day_balances], upper_percentile)))

            # Berechne tatsaechliche Ein-/Ausgaenge für diesen Tag (Erwartungswert)
            day_incoming = sum(
                recv["amount"] for recv in receivables
                if recv["due_date"] == current_date
            )
            day_outgoing = sum(
                pay["amount"] for pay in payables
                if pay["payment_date"] == current_date
            )

            # Zaehle Transaktionen
            incoming_count = sum(1 for recv in receivables if recv["due_date"] == current_date)
            outgoing_count = sum(1 for pay in payables if pay["payment_date"] == current_date)

            # Konfidenz basierend auf Streuung
            spread = float(upper - lower)
            mid = float(predicted) if predicted != 0 else 1.0
            confidence = max(0.3, 1.0 - (spread / (2 * abs(mid) + 0.01)))

            forecasts.append(CashflowForecast(
                date=current_date,
                predicted_balance=round(predicted, 2),
                lower_bound=round(lower, 2),
                upper_bound=round(upper, 2),
                incoming=round(day_incoming, 2),
                outgoing=round(day_outgoing, 2),
                confidence=round(confidence, 2),
                incoming_count=incoming_count,
                outgoing_count=outgoing_count,
            ))

        return forecasts

    @staticmethod
    def _percentile(data: List[float], percentile: float) -> float:
        """Berechnet Perzentil aus einer Liste."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        k = (len(sorted_data) - 1) * percentile / 100
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_data[int(k)]
        return sorted_data[int(f)] * (c - k) + sorted_data[int(c)] * (k - f)

    # =========================================================================
    # SCENARIO SIMULATION METHODS
    # =========================================================================

    async def _simulate_customer_late_payment(
        self,
        company_id: UUID,
        base_forecasts: List[CashflowForecast],
        parameters: JSONDict,
    ) -> ScenarioResult:
        """Simuliert: Was wenn Kunde X später zahlt?"""
        entity_id = parameters.get("entity_id")
        delay_days = parameters.get("delay_days", 14)

        if not entity_id:
            return ScenarioResult(
                scenario_type=ScenarioType.CUSTOMER_LATE_PAYMENT,
                description="Fehlender Parameter: entity_id",
                impact_on_min_balance=Decimal("0"),
                impact_on_avg_balance=Decimal("0"),
                new_forecasts=base_forecasts,
                risk_assessment="Parameter unvollständig",
                recommendations=[],
            )

        # Finde offene Forderungen des Kunden
        receivables = await self._get_open_receivables(company_id, 30)
        customer_receivables = [r for r in receivables if r.get("entity_id") == entity_id]

        if not customer_receivables:
            return ScenarioResult(
                scenario_type=ScenarioType.CUSTOMER_LATE_PAYMENT,
                description="Keine offenen Forderungen für diesen Kunden gefunden",
                impact_on_min_balance=Decimal("0"),
                impact_on_avg_balance=Decimal("0"),
                new_forecasts=base_forecasts,
                risk_assessment="Kein Einfluss",
                recommendations=[],
            )

        affected_amount = sum(r["amount"] for r in customer_receivables)

        # Neue Prognose mit verschobenen Eingaengen
        new_forecasts = []
        for f in base_forecasts:
            # Prüfen ob an diesem Tag eine Zahlung erwartet wurde
            original_incoming = f.incoming
            delayed_incoming = Decimal("0")

            for recv in customer_receivables:
                if recv["due_date"] == f.date:
                    delayed_incoming += recv["amount"]

            new_incoming = original_incoming - delayed_incoming
            new_balance = f.predicted_balance - delayed_incoming

            # Verzögerte Zahlungen kommen später
            incoming_from_delay = Decimal("0")
            for recv in customer_receivables:
                delayed_date = recv["due_date"] + timedelta(days=delay_days)
                if delayed_date == f.date:
                    incoming_from_delay += recv["amount"]

            new_balance += incoming_from_delay
            new_incoming += incoming_from_delay

            new_forecasts.append(CashflowForecast(
                date=f.date,
                predicted_balance=round(new_balance, 2),
                lower_bound=f.lower_bound - delayed_incoming + incoming_from_delay,
                upper_bound=f.upper_bound - delayed_incoming + incoming_from_delay,
                incoming=round(new_incoming, 2),
                outgoing=f.outgoing,
                confidence=f.confidence * Decimal("0.9"),  # Etwas niedrigere Konfidenz
            ))

        # Risikobewertung
        new_min = min(f.predicted_balance for f in new_forecasts)
        risk = "Kritisch" if new_min < 0 else "Moderat" if new_min < WARNING_BALANCE_EUR else "Gering"

        return ScenarioResult(
            scenario_type=ScenarioType.CUSTOMER_LATE_PAYMENT,
            description=f"Szenario: Kunde zahlt {delay_days} Tage später "
                        f"(betroffen: {float(affected_amount):,.2f} EUR)",
            impact_on_min_balance=Decimal("0"),  # Wird später berechnet
            impact_on_avg_balance=Decimal("0"),
            new_forecasts=new_forecasts,
            risk_assessment=risk,
            recommendations=[
                "Zahlungserinnerung rechtzeitig versenden",
                f"Skonto anbieten für frühzeitige Zahlung",
                "Alternative Zahlungsquellen prüfen",
            ],
        )

    async def _simulate_delay_outgoing(
        self,
        company_id: UUID,
        base_forecasts: List[CashflowForecast],
        parameters: JSONDict,
    ) -> ScenarioResult:
        """Simuliert: Was wenn wir Zahlung Y verschieben?"""
        invoice_id = parameters.get("invoice_id")
        delay_days = parameters.get("delay_days", 7)

        # Finde die Rechnung
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                and_(
                    InvoiceTracking.id == invoice_id,
                    InvoiceTracking.company_id == company_id,
                )
            )
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            return ScenarioResult(
                scenario_type=ScenarioType.DELAY_OUTGOING,
                description="Rechnung nicht gefunden",
                impact_on_min_balance=Decimal("0"),
                impact_on_avg_balance=Decimal("0"),
                new_forecasts=base_forecasts,
                risk_assessment="Parameter ungültig",
                recommendations=[],
            )

        payment_amount = Decimal(str(invoice.amount or 0))
        original_due = invoice.due_date.date() if invoice.due_date else date.today() + timedelta(days=14)
        new_due = original_due + timedelta(days=delay_days)

        # Neue Prognose mit verschobener Zahlung
        new_forecasts = []
        for f in base_forecasts:
            new_outgoing = f.outgoing
            adjustment = Decimal("0")

            # Am urspruenglichen Datum: Ausgabe entfernen
            if f.date == original_due:
                new_outgoing -= payment_amount
                adjustment = payment_amount

            # Am neuen Datum: Ausgabe hinzufuegen
            if f.date == new_due:
                new_outgoing += payment_amount
                adjustment = -payment_amount

            new_forecasts.append(CashflowForecast(
                date=f.date,
                predicted_balance=f.predicted_balance + adjustment,
                lower_bound=f.lower_bound + adjustment,
                upper_bound=f.upper_bound + adjustment,
                incoming=f.incoming,
                outgoing=round(new_outgoing, 2),
                confidence=f.confidence,
            ))

        # Warnung wenn Skonto verloren geht
        warnings = []
        if invoice.skonto_deadline:
            skonto_date = invoice.skonto_deadline.date() if isinstance(invoice.skonto_deadline, datetime) else invoice.skonto_deadline
            if new_due > skonto_date and invoice.skonto_percentage:
                lost_skonto = payment_amount * Decimal(str(invoice.skonto_percentage)) / 100
                warnings.append(f"Achtung: Skonto-Verlust von {float(lost_skonto):,.2f} EUR möglich")

        return ScenarioResult(
            scenario_type=ScenarioType.DELAY_OUTGOING,
            description=f"Szenario: Zahlung von {float(payment_amount):,.2f} EUR "
                        f"um {delay_days} Tage verschieben",
            impact_on_min_balance=Decimal("0"),
            impact_on_avg_balance=Decimal("0"),
            new_forecasts=new_forecasts,
            risk_assessment="Positiv für Liquiditaet" if not warnings else "Mit Skonto-Verlust",
            recommendations=[
                "Lieferanten über Verzögerung informieren",
                *warnings,
                "Sicherstellen, dass Zahlung nicht überfällig wird",
            ],
        )

    async def _simulate_new_order(
        self,
        company_id: UUID,
        base_forecasts: List[CashflowForecast],
        parameters: JSONDict,
    ) -> ScenarioResult:
        """Simuliert: Was wenn wir neuen Auftrag Z bekommen?"""
        order_amount = Decimal(str(parameters.get("amount", 10000)))
        payment_due_days = parameters.get("payment_due_days", 30)

        expected_payment_date = date.today() + timedelta(days=payment_due_days)

        # Neue Prognose mit zusätzlichem Eingang
        new_forecasts = []
        for f in base_forecasts:
            adjustment = Decimal("0")
            new_incoming = f.incoming

            # Ab dem Zahlungsdatum: Balance erhöhen
            if f.date >= expected_payment_date:
                adjustment = order_amount
            if f.date == expected_payment_date:
                new_incoming += order_amount

            new_forecasts.append(CashflowForecast(
                date=f.date,
                predicted_balance=f.predicted_balance + adjustment,
                lower_bound=f.lower_bound + adjustment * Decimal("0.8"),  # Konservativ
                upper_bound=f.upper_bound + adjustment * Decimal("1.2"),
                incoming=new_incoming,
                outgoing=f.outgoing,
                confidence=f.confidence * Decimal("0.85"),  # Etwas unsicherer
            ))

        return ScenarioResult(
            scenario_type=ScenarioType.NEW_ORDER,
            description=f"Szenario: Neuer Auftrag über {float(order_amount):,.2f} EUR "
                        f"mit Zahlung in {payment_due_days} Tagen",
            impact_on_min_balance=Decimal("0"),
            impact_on_avg_balance=Decimal("0"),
            new_forecasts=new_forecasts,
            risk_assessment="Positiv",
            recommendations=[
                "Ressourcen für Auftragsabwicklung planen",
                "Rechnung zeitnah stellen",
                "Zahlungsverhalten des Kunden prüfen",
            ],
        )

    async def _simulate_customer_default(
        self,
        company_id: UUID,
        base_forecasts: List[CashflowForecast],
        parameters: JSONDict,
    ) -> ScenarioResult:
        """Simuliert: Was wenn Kunde X komplett ausfaellt?"""
        entity_id = parameters.get("entity_id")

        if not entity_id:
            return ScenarioResult(
                scenario_type=ScenarioType.CUSTOMER_DEFAULT,
                description="Fehlender Parameter: entity_id",
                impact_on_min_balance=Decimal("0"),
                impact_on_avg_balance=Decimal("0"),
                new_forecasts=base_forecasts,
                risk_assessment="Parameter unvollständig",
                recommendations=[],
            )

        # Finde alle offenen Forderungen des Kunden
        receivables = await self._get_open_receivables(company_id, 90)
        customer_receivables = [r for r in receivables if r.get("entity_id") == entity_id]

        total_exposure = sum(r["amount"] for r in customer_receivables)

        # Neue Prognose ohne diese Eingaenge
        new_forecasts = []
        cumulative_loss = Decimal("0")

        for f in base_forecasts:
            # Verlust an diesem Tag
            day_loss = sum(
                r["amount"] for r in customer_receivables
                if r["due_date"] == f.date
            )
            cumulative_loss += day_loss

            new_forecasts.append(CashflowForecast(
                date=f.date,
                predicted_balance=f.predicted_balance - cumulative_loss,
                lower_bound=f.lower_bound - cumulative_loss,
                upper_bound=f.upper_bound - cumulative_loss,
                incoming=f.incoming - day_loss,
                outgoing=f.outgoing,
                confidence=f.confidence,
            ))

        # Risikobewertung
        new_min = min(f.predicted_balance for f in new_forecasts)
        risk = "Kritisch" if new_min < 0 else "Hoch" if new_min < WARNING_BALANCE_EUR else "Moderat"

        return ScenarioResult(
            scenario_type=ScenarioType.CUSTOMER_DEFAULT,
            description=f"Szenario: Komplettausfall eines Kunden "
                        f"(Exposure: {float(total_exposure):,.2f} EUR)",
            impact_on_min_balance=Decimal("0"),
            impact_on_avg_balance=Decimal("0"),
            new_forecasts=new_forecasts,
            risk_assessment=risk,
            recommendations=[
                "Forderungsausfallversicherung prüfen",
                "Mahnwesen intensivieren",
                "Rechtliche Schritte erwaegen",
                "Kundenportfolio diversifizieren",
            ],
        )

    async def _simulate_accelerate_collection(
        self,
        company_id: UUID,
        base_forecasts: List[CashflowForecast],
        parameters: JSONDict,
    ) -> ScenarioResult:
        """Simuliert: Was wenn wir Forderungseinzug beschleunigen?"""
        days_improvement = parameters.get("days_improvement", 7)

        receivables = await self._get_open_receivables(company_id, 90)

        # Berechne Auswirkung der früheren Zahlungen
        new_forecasts = []

        for f in base_forecasts:
            additional_income = Decimal("0")
            reduced_income = Decimal("0")

            for recv in receivables:
                original_date = recv["due_date"]
                new_date = original_date - timedelta(days=days_improvement)

                # Eingang kommt früher
                if new_date == f.date:
                    additional_income += recv["amount"]

                # Eingang waere urspruenglich an diesem Tag
                if original_date == f.date:
                    reduced_income += recv["amount"]

            net_change = additional_income - reduced_income

            new_forecasts.append(CashflowForecast(
                date=f.date,
                predicted_balance=f.predicted_balance + net_change,
                lower_bound=f.lower_bound + net_change * Decimal("0.7"),
                upper_bound=f.upper_bound + net_change * Decimal("1.3"),
                incoming=f.incoming + additional_income - reduced_income,
                outgoing=f.outgoing,
                confidence=f.confidence * Decimal("0.9"),
            ))

        total_accelerated = sum(r["amount"] for r in receivables)

        return ScenarioResult(
            scenario_type=ScenarioType.ACCELERATE_COLLECTION,
            description=f"Szenario: Forderungseinzug um {days_improvement} Tage beschleunigen "
                        f"(betrifft {float(total_accelerated):,.2f} EUR)",
            impact_on_min_balance=Decimal("0"),
            impact_on_avg_balance=Decimal("0"),
            new_forecasts=new_forecasts,
            risk_assessment="Positiv",
            recommendations=[
                "Skonto-Anreize für frühzeitige Zahlung anbieten",
                "Automatische Zahlungserinnerungen einrichten",
                "Telefonisches Nachfassen bei überfälligen Rechnungen",
            ],
        )


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def get_cashflow_prediction_service(db: AsyncSession) -> CashflowPredictionService:
    """Factory-Funktion für CashflowPredictionService."""
    return CashflowPredictionService(db)
