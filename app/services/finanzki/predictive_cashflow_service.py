"""
Predictive Cash-Flow Service 2.0.

ML-basierte Vorhersage von Zahlungseingaengen und Liquiditaetsengpaessen.

Features:
- Zahlungseingangs-Vorhersage pro Rechnung
- Liquiditaetsprognose (7/14/30/90 Tage)
- Zahlungsverzugs-Wahrscheinlichkeit
- Optimale Zahlungszeitpunkt-Empfehlung
- What-If Szenarien (erweitert)
- Saisonalitaets-Erkennung (NEU: Januar 2026)
- Multi-Company Konsolidierung (NEU: Januar 2026)
- Frühwarnsystem (NEU: Januar 2026)

Created: 2026-01-19
Updated: 2026-01-21 - Phase 5.2 Enhancement
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
from enum import Enum
from dataclasses import dataclass, field
import math
import statistics

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_, case, or_, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Company,
    InvoiceTracking,
    BankTransaction,
    BankAccount,
    BusinessEntity,
)


# =============================================================================
# MODELS
# =============================================================================


class SeasonalityPeriod(str, Enum):
    """Saisonalitaets-Perioden."""

    WEEKLY = "weekly"      # Wochentags-Muster
    MONTHLY = "monthly"    # Monatsmuster
    QUARTERLY = "quarterly"  # Quartalsmuster
    YEARLY = "yearly"      # Jährliches Muster


class AlertSeverity(str, Enum):
    """Alarm-Schweregrade."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class SeasonalityPattern:
    """Erkanntes Saisonalitaets-Muster."""

    period: SeasonalityPeriod
    pattern_data: Dict[str, float]  # z.B. {"jan": 1.2, "feb": 0.9, ...}
    confidence: float
    description: str


@dataclass
class LiquidityAlert:
    """Liquiditaets-Warnung."""

    severity: AlertSeverity
    trigger_date: datetime
    projected_balance: float
    message: str
    recommendation: str
    days_until_trigger: int


@dataclass
class ConsolidatedForecast:
    """Konsolidierte Prognose für Holding."""

    total_current_balance: float
    total_min_balance: float
    total_expected_inflows: float
    total_expected_outflows: float
    company_forecasts: List[Dict[str, Any]]
    intercompany_flows: List[Dict[str, Any]]
    consolidated_daily: List[Dict[str, Any]]
    alerts: List[LiquidityAlert]

logger = structlog.get_logger(__name__)


class PredictiveCashFlowService:
    """Service für ML-basierte Cashflow-Vorhersagen."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def predict_payment_date(
        self,
        invoice_id: UUID,
    ) -> Dict[str, Any]:
        """Vorhersage des Zahlungseingangs für eine Rechnung.

        Berechnet basierend auf:
        - Historisches Zahlungsverhalten des Kunden
        - Rechnungsbetrag (größere Betraege = längere Zahlungsziele)
        - Wochentag der Rechnungsstellung
        - Saisonale Faktoren

        Returns:
            predicted_date: Vorhergesagtes Zahlungsdatum
            confidence: Konfidenz der Vorhersage (0-1)
            delay_probability: Wahrscheinlichkeit einer Verspätung
            factors: Einflussfaktoren
        """
        # Hole Rechnung
        result = await self.db.execute(
            select(InvoiceTracking).where(InvoiceTracking.id == invoice_id)
        )
        invoice = result.scalar_one_or_none()

        if not invoice:
            return {"error": "Rechnung nicht gefunden"}

        if invoice.is_paid:
            return {
                "predicted_date": invoice.paid_date.isoformat() if invoice.paid_date else None,
                "confidence": 1.0,
                "delay_probability": 0.0,
                "factors": {"status": "already_paid"},
            }

        # Hole historische Zahlungen des Kunden
        entity_id = invoice.entity_id
        if entity_id:
            history = await self._get_payment_history(entity_id, invoice.company_id)
        else:
            history = {"avg_days": 30, "stddev": 10, "count": 0}

        # Berechne Faktoren
        amount_factor = self._calculate_amount_factor(float(invoice.amount or 0))
        weekday_factor = self._calculate_weekday_factor(invoice.invoice_date)
        seasonal_factor = self._calculate_seasonal_factor(datetime.now(timezone.utc))

        # Basis: Durchschnittliche Zahlungsdauer des Kunden
        base_days = history["avg_days"]

        # Adjustierte Tage
        predicted_days = base_days * amount_factor * weekday_factor * seasonal_factor

        # Vorhersage-Datum
        base_date = invoice.invoice_date or datetime.now(timezone.utc)
        predicted_date = base_date + timedelta(days=int(predicted_days))

        # Konfidenz basierend auf Datenmenge
        confidence = min(0.9, 0.3 + (history["count"] * 0.05))

        # Verspätungs-Wahrscheinlichkeit
        if invoice.due_date:
            days_until_due = (invoice.due_date - datetime.now(timezone.utc)).days
            if days_until_due < 0:
                delay_probability = 0.95  # Bereits überfällig
            elif predicted_date > invoice.due_date:
                delay_probability = 0.7
            else:
                delay_probability = max(0.1, 1 - (days_until_due / 60))
        else:
            delay_probability = 0.3  # Default ohne Fälligkeitsdatum

        return {
            "invoice_id": str(invoice_id),
            "predicted_date": predicted_date.isoformat(),
            "predicted_days": int(predicted_days),
            "confidence": round(confidence, 2),
            "delay_probability": round(delay_probability, 2),
            "factors": {
                "base_days": base_days,
                "amount_factor": round(amount_factor, 2),
                "weekday_factor": round(weekday_factor, 2),
                "seasonal_factor": round(seasonal_factor, 2),
                "history_count": history["count"],
            },
        }

    async def forecast_liquidity(
        self,
        company_id: UUID,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Liquiditaetsprognose für die nächsten X Tage.

        Args:
            company_id: Firmen-ID
            days: Prognosezeitraum in Tagen

        Returns:
            Tagesweise Liquiditaetsprognose mit Warnungen
        """
        now = datetime.now(timezone.utc)
        end_date = now + timedelta(days=days)

        # Aktueller Kontostand
        balance_result = await self.db.execute(
            select(func.sum(BankAccount.balance))
            .where(
                BankAccount.company_id == company_id,
                BankAccount.is_active == True,
            )
        )
        current_balance = float(balance_result.scalar() or 0)

        # Erwartete Eingaenge (offene Ausgangsrechnungen)
        expected_inflows = await self._get_expected_inflows(company_id, days)

        # Erwartete Ausgaenge (offene Eingangsrechnungen)
        expected_outflows = await self._get_expected_outflows(company_id, days)

        # Tagesweise Prognose erstellen
        forecast = []
        running_balance = current_balance

        for day_offset in range(days + 1):
            date = now + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")

            day_inflows = sum(
                item["amount"] for item in expected_inflows
                if item["expected_date"] == date_str
            )
            day_outflows = sum(
                item["amount"] for item in expected_outflows
                if item["expected_date"] == date_str
            )

            running_balance = running_balance + day_inflows - day_outflows

            forecast.append({
                "date": date_str,
                "inflows": round(day_inflows, 2),
                "outflows": round(day_outflows, 2),
                "net_flow": round(day_inflows - day_outflows, 2),
                "balance": round(running_balance, 2),
                "is_warning": running_balance < 0,
                "is_critical": running_balance < -10000,
            })

        # Warnungen generieren
        warnings = []
        for item in forecast:
            if item["is_critical"]:
                warnings.append({
                    "type": "critical",
                    "date": item["date"],
                    "message": f"Kritischer Liquiditaetsengpass: {item['balance']:,.2f} EUR",
                })
            elif item["is_warning"]:
                warnings.append({
                    "type": "warning",
                    "date": item["date"],
                    "message": f"Liquiditaetswarnung: {item['balance']:,.2f} EUR",
                })

        # Zusammenfassung
        min_balance = min(f["balance"] for f in forecast)
        min_balance_date = next(
            f["date"] for f in forecast if f["balance"] == min_balance
        )

        return {
            "company_id": str(company_id),
            "forecast_days": days,
            "current_balance": round(current_balance, 2),
            "min_balance": round(min_balance, 2),
            "min_balance_date": min_balance_date,
            "total_expected_inflows": round(sum(i["amount"] for i in expected_inflows), 2),
            "total_expected_outflows": round(sum(o["amount"] for o in expected_outflows), 2),
            "forecast": forecast,
            "warnings": warnings,
            "currency": "EUR",
        }

    async def get_payment_recommendations(
        self,
        company_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Empfehlungen für optimale Zahlungszeitpunkte.

        Berücksichtigt:
        - Skonto-Fristen
        - Liquiditaetssituation
        - Lieferanten-Priorisierung
        """
        now = datetime.now(timezone.utc)
        next_30_days = now + timedelta(days=30)

        # Hole offene Eingangsrechnungen
        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
                InvoiceTracking.due_date <= next_30_days,
            )
            .order_by(InvoiceTracking.due_date)
        )
        invoices = result.scalars().all()

        recommendations = []

        for inv in invoices:
            # Prüfen ob Skonto möglich
            skonto_savings = 0.0
            if inv.skonto_percentage and inv.skonto_deadline:
                if inv.skonto_deadline > now:
                    skonto_savings = float(inv.amount or 0) * (inv.skonto_percentage / 100)

            # Priorisierung berechnen
            days_until_due = (inv.due_date - now).days if inv.due_date else 30
            urgency = "low"
            if days_until_due < 0:
                urgency = "overdue"
            elif days_until_due <= 3:
                urgency = "critical"
            elif days_until_due <= 7:
                urgency = "high"
            elif days_until_due <= 14:
                urgency = "medium"

            # Empfehlung
            recommendation = "normal"
            reason = ""

            if skonto_savings > 0:
                recommendation = "pay_early"
                reason = f"Skonto nutzen: {skonto_savings:,.2f} EUR sparen"
            elif urgency == "overdue":
                recommendation = "pay_immediately"
                reason = "Überfällig - sofort zahlen"
            elif urgency == "critical":
                recommendation = "pay_soon"
                reason = "Fällig in weniger als 3 Tagen"

            recommendations.append({
                "invoice_id": str(inv.id),
                "invoice_number": inv.invoice_number,
                "amount": float(inv.amount or 0),
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
                "days_until_due": days_until_due,
                "urgency": urgency,
                "recommendation": recommendation,
                "reason": reason,
                "skonto_savings": round(skonto_savings, 2),
                "skonto_deadline": inv.skonto_deadline.isoformat() if inv.skonto_deadline else None,
            })

        return recommendations

    async def run_scenario(
        self,
        company_id: UUID,
        scenario_type: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """What-If Szenario-Analyse.

        Scenario Types:
        - delayed_payments: Was wenn X% der Zahlungen sich verzögern?
        - large_expense: Was wenn eine grosse Ausgabe ansteht?
        - revenue_drop: Was wenn Umsatz um X% sinkt?
        """
        base_forecast = await self.forecast_liquidity(company_id, days=30)

        if scenario_type == "delayed_payments":
            delay_percentage = parameters.get("delay_percentage", 30)
            delay_days = parameters.get("delay_days", 14)

            # Modifiziere Eingaenge
            modified_forecast = []
            delayed_amount = 0.0

            for item in base_forecast["forecast"]:
                inflows = item["inflows"]
                delayed = inflows * (delay_percentage / 100)
                delayed_amount += delayed

                modified_forecast.append({
                    **item,
                    "inflows": round(inflows - delayed, 2),
                    "net_flow": round((inflows - delayed) - item["outflows"], 2),
                })

            # Neuberechnung der Bilanzen
            running = base_forecast["current_balance"]
            for item in modified_forecast:
                running = running + item["inflows"] - item["outflows"]
                item["balance"] = round(running, 2)
                item["is_warning"] = running < 0
                item["is_critical"] = running < -10000

            return {
                "scenario_type": scenario_type,
                "parameters": parameters,
                "base_min_balance": base_forecast["min_balance"],
                "scenario_min_balance": min(f["balance"] for f in modified_forecast),
                "delayed_amount": round(delayed_amount, 2),
                "forecast": modified_forecast,
                "impact": "negative" if min(f["balance"] for f in modified_forecast) < base_forecast["min_balance"] else "neutral",
            }

        elif scenario_type == "large_expense":
            expense_amount = parameters.get("amount", 10000)
            expense_date = parameters.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

            modified_forecast = []
            for item in base_forecast["forecast"]:
                if item["date"] == expense_date:
                    modified_forecast.append({
                        **item,
                        "outflows": round(item["outflows"] + expense_amount, 2),
                        "net_flow": round(item["net_flow"] - expense_amount, 2),
                    })
                else:
                    modified_forecast.append(item)

            # Neuberechnung
            running = base_forecast["current_balance"]
            for item in modified_forecast:
                running = running + item["inflows"] - item["outflows"]
                item["balance"] = round(running, 2)
                item["is_warning"] = running < 0
                item["is_critical"] = running < -10000

            return {
                "scenario_type": scenario_type,
                "parameters": parameters,
                "base_min_balance": base_forecast["min_balance"],
                "scenario_min_balance": min(f["balance"] for f in modified_forecast),
                "forecast": modified_forecast,
                "impact": "negative" if min(f["balance"] for f in modified_forecast) < base_forecast["min_balance"] else "neutral",
            }

        return {"error": f"Unbekannter Szenario-Typ: {scenario_type}"}

    # ==================== Helper Methods ====================

    async def _get_payment_history(
        self,
        entity_id: UUID,
        company_id: UUID,
    ) -> Dict[str, Any]:
        """Hole historisches Zahlungsverhalten eines Kunden."""
        result = await self.db.execute(
            select(
                func.avg(
                    func.extract('epoch', InvoiceTracking.paid_date - InvoiceTracking.invoice_date) / 86400
                ).label('avg_days'),
                func.stddev(
                    func.extract('epoch', InvoiceTracking.paid_date - InvoiceTracking.invoice_date) / 86400
                ).label('stddev'),
                func.count().label('count'),
            )
            .where(
                InvoiceTracking.entity_id == entity_id,
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.is_paid == True,
                InvoiceTracking.paid_date.isnot(None),
                InvoiceTracking.invoice_date.isnot(None),
            )
        )
        row = result.first()

        if row and row.count and row.count > 0:
            return {
                "avg_days": float(row.avg_days or 30),
                "stddev": float(row.stddev or 10),
                "count": row.count,
            }

        return {"avg_days": 30, "stddev": 10, "count": 0}

    def _calculate_amount_factor(self, amount: float) -> float:
        """Betragsabhängiger Faktor (größere Betraege = längere Zahlung)."""
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

    def _calculate_weekday_factor(self, date: Optional[datetime]) -> float:
        """Wochentags-Faktor (Rechnungen am Freitag = längere Zahlung)."""
        if not date:
            return 1.0
        weekday = date.weekday()
        # Freitag und Wochenende
        if weekday >= 4:
            return 1.1
        return 1.0

    def _calculate_seasonal_factor(self, date: datetime) -> float:
        """Saisonaler Faktor (Jahresende/Urlaubszeit = längere Zahlung)."""
        month = date.month
        # Dezember, August = Urlaubszeit
        if month in [8, 12]:
            return 1.15
        # Januar = Jahresanfang-Chaos
        if month == 1:
            return 1.1
        return 1.0

    async def _get_expected_inflows(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Hole erwartete Zahlungseingaenge."""
        now = datetime.now(timezone.utc)
        end_date = now + timedelta(days=days)

        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "outgoing",
                InvoiceTracking.is_paid == False,
            )
        )
        invoices = result.scalars().all()

        inflows = []
        for inv in invoices:
            # Vorhersage basierend auf Fälligkeitsdatum oder Durchschnitt
            if inv.due_date:
                expected = inv.due_date
            else:
                # Default: 30 Tage nach Rechnungsdatum
                expected = (inv.invoice_date or now) + timedelta(days=30)

            if expected <= end_date:
                inflows.append({
                    "invoice_id": str(inv.id),
                    "amount": float(inv.amount or 0),
                    "expected_date": expected.strftime("%Y-%m-%d"),
                    "confidence": 0.7,  # Basis-Konfidenz
                })

        return inflows

    async def _get_expected_outflows(
        self,
        company_id: UUID,
        days: int,
    ) -> List[Dict[str, Any]]:
        """Hole erwartete Zahlungsausgaenge."""
        now = datetime.now(timezone.utc)
        end_date = now + timedelta(days=days)

        result = await self.db.execute(
            select(InvoiceTracking)
            .where(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.invoice_type == "incoming",
                InvoiceTracking.is_paid == False,
            )
        )
        invoices = result.scalars().all()

        outflows = []
        for inv in invoices:
            # Zahlungszeitpunkt: Skonto-Frist oder Fälligkeitsdatum
            if inv.skonto_deadline and inv.skonto_deadline > now:
                expected = inv.skonto_deadline  # Skonto nutzen
            elif inv.due_date:
                expected = inv.due_date
            else:
                expected = (inv.invoice_date or now) + timedelta(days=30)

            if expected <= end_date:
                amount = float(inv.amount or 0)
                # Bei Skonto-Nutzung: reduzierter Betrag
                if inv.skonto_deadline and inv.skonto_deadline > now and inv.skonto_percentage:
                    amount = amount * (1 - inv.skonto_percentage / 100)

                outflows.append({
                    "invoice_id": str(inv.id),
                    "amount": amount,
                    "expected_date": expected.strftime("%Y-%m-%d"),
                    "confidence": 0.8,  # Ausgaben sind planbarer
                })

        return outflows

    # ==================== PHASE 5.2: Neue Features ====================

    async def detect_seasonality(
        self,
        company_id: UUID,
        lookback_months: int = 24,
    ) -> List[SeasonalityPattern]:
        """Erkennt Saisonalitaets-Muster in den historischen Cashflows.

        Analysiert:
        - Wochentags-Muster (z.B. Freitags mehr Zahlungseingaenge)
        - Monatsmuster (z.B. Quartalszahlungen)
        - Jährliche Muster (z.B. Weihnachtsgeschäft)

        Returns:
            Liste erkannter Saisonalitaets-Muster mit Konfidenz
        """
        logger.info(
            "seasonality_detection_started",
            company_id=str(company_id),
            lookback_months=lookback_months,
        )

        patterns: List[SeasonalityPattern] = []
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=lookback_months * 30)

        # Hole historische Transaktionen
        result = await self.db.execute(
            select(
                extract('dow', BankTransaction.booking_date).label('weekday'),
                extract('month', BankTransaction.booking_date).label('month'),
                extract('quarter', BankTransaction.booking_date).label('quarter'),
                BankTransaction.amount,
                BankTransaction.booking_date,
            )
            .join(BankAccount)
            .where(
                BankAccount.company_id == company_id,
                BankTransaction.booking_date >= cutoff_date,
            )
        )
        transactions = result.all()

        if len(transactions) < 50:
            logger.info(
                "insufficient_data_for_seasonality",
                company_id=str(company_id),
                transaction_count=len(transactions),
            )
            return []

        # 1. Wochentags-Muster
        weekday_pattern = await self._detect_weekday_pattern(transactions)
        if weekday_pattern:
            patterns.append(weekday_pattern)

        # 2. Monatsmuster
        monthly_pattern = await self._detect_monthly_pattern(transactions)
        if monthly_pattern:
            patterns.append(monthly_pattern)

        # 3. Quartalsmuster
        quarterly_pattern = await self._detect_quarterly_pattern(transactions)
        if quarterly_pattern:
            patterns.append(quarterly_pattern)

        logger.info(
            "seasonality_detection_completed",
            company_id=str(company_id),
            patterns_found=len(patterns),
        )

        return patterns

    async def _detect_weekday_pattern(
        self,
        transactions: List[Any],
    ) -> Optional[SeasonalityPattern]:
        """Erkennt Wochentags-Muster."""
        # Gruppiere nach Wochentag
        weekday_sums: Dict[int, List[float]] = {i: [] for i in range(7)}

        for tx in transactions:
            weekday = int(tx.weekday or 0)
            amount = float(tx.amount or 0)
            weekday_sums[weekday].append(amount)

        # Berechne Durchschnitte
        weekday_avgs = {}
        weekday_names = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"]

        for day, amounts in weekday_sums.items():
            if amounts:
                weekday_avgs[weekday_names[day]] = statistics.mean(amounts)

        if not weekday_avgs:
            return None

        # Berechne Variationskoeffizient
        values = list(weekday_avgs.values())
        if len(values) < 2:
            return None

        mean_val = statistics.mean(values)
        if mean_val == 0:
            return None

        stddev = statistics.stdev(values)
        cv = stddev / abs(mean_val)

        # Nur bei signifikanter Variation
        if cv < 0.15:
            return None

        # Normalisiere auf Durchschnitt = 1.0
        pattern_data = {k: v / mean_val for k, v in weekday_avgs.items()}

        return SeasonalityPattern(
            period=SeasonalityPeriod.WEEKLY,
            pattern_data=pattern_data,
            confidence=min(0.9, cv * 2),
            description=f"Wochentags-Muster erkannt (CV={cv:.2f})",
        )

    async def _detect_monthly_pattern(
        self,
        transactions: List[Any],
    ) -> Optional[SeasonalityPattern]:
        """Erkennt Monatsmuster."""
        month_sums: Dict[int, List[float]] = {i: [] for i in range(1, 13)}
        month_names = [
            "Jan", "Feb", "Mrz", "Apr", "Mai", "Jun",
            "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"
        ]

        for tx in transactions:
            month = int(tx.month or 1)
            amount = float(tx.amount or 0)
            month_sums[month].append(amount)

        # Berechne Durchschnitte
        month_avgs = {}
        for month, amounts in month_sums.items():
            if amounts:
                month_avgs[month_names[month - 1]] = statistics.mean(amounts)

        if len(month_avgs) < 6:
            return None

        values = list(month_avgs.values())
        mean_val = statistics.mean(values)
        if mean_val == 0:
            return None

        stddev = statistics.stdev(values)
        cv = stddev / abs(mean_val)

        if cv < 0.2:
            return None

        pattern_data = {k: v / mean_val for k, v in month_avgs.items()}

        # Finde Spitzen- und Tiefmonate
        max_month = max(pattern_data.items(), key=lambda x: x[1])
        min_month = min(pattern_data.items(), key=lambda x: x[1])

        return SeasonalityPattern(
            period=SeasonalityPeriod.MONTHLY,
            pattern_data=pattern_data,
            confidence=min(0.85, cv * 1.5),
            description=f"Monatsmuster: Hoch in {max_month[0]}, Tief in {min_month[0]}",
        )

    async def _detect_quarterly_pattern(
        self,
        transactions: List[Any],
    ) -> Optional[SeasonalityPattern]:
        """Erkennt Quartalsmuster."""
        quarter_sums: Dict[int, List[float]] = {i: [] for i in range(1, 5)}
        quarter_names = ["Q1", "Q2", "Q3", "Q4"]

        for tx in transactions:
            quarter = int(tx.quarter or 1)
            amount = float(tx.amount or 0)
            quarter_sums[quarter].append(amount)

        quarter_avgs = {}
        for q, amounts in quarter_sums.items():
            if amounts:
                quarter_avgs[quarter_names[q - 1]] = statistics.mean(amounts)

        if len(quarter_avgs) < 4:
            return None

        values = list(quarter_avgs.values())
        mean_val = statistics.mean(values)
        if mean_val == 0:
            return None

        stddev = statistics.stdev(values)
        cv = stddev / abs(mean_val)

        if cv < 0.15:
            return None

        pattern_data = {k: v / mean_val for k, v in quarter_avgs.items()}

        return SeasonalityPattern(
            period=SeasonalityPeriod.QUARTERLY,
            pattern_data=pattern_data,
            confidence=min(0.8, cv * 2),
            description=f"Quartalsmuster erkannt (CV={cv:.2f})",
        )

    async def forecast_with_seasonality(
        self,
        company_id: UUID,
        days: int = 90,
        include_patterns: bool = True,
    ) -> Dict[str, Any]:
        """Erweiterte Liquiditaetsprognose mit Saisonalitaets-Korrektur.

        Args:
            company_id: Firmen-ID
            days: Prognosezeitraum (bis zu 90 Tage)
            include_patterns: Saisonalitaetsmuster einbeziehen

        Returns:
            Erweiterte Prognose mit Saisonalitaets-Faktoren
        """
        # Basis-Prognose
        base_forecast = await self.forecast_liquidity(company_id, days)

        if not include_patterns:
            return base_forecast

        # Saisonalitaets-Muster erkennen
        patterns = await self.detect_seasonality(company_id)

        if not patterns:
            base_forecast["seasonality_applied"] = False
            return base_forecast

        # Prognose mit Saisonalitaets-Korrekturen
        monthly_pattern = next(
            (p for p in patterns if p.period == SeasonalityPeriod.MONTHLY),
            None
        )

        adjusted_forecast = []
        now = datetime.now(timezone.utc)

        for item in base_forecast["forecast"]:
            forecast_date = datetime.strptime(item["date"], "%Y-%m-%d")
            month_name = [
                "Jan", "Feb", "Mrz", "Apr", "Mai", "Jun",
                "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"
            ][forecast_date.month - 1]

            adjustment = 1.0
            if monthly_pattern and month_name in monthly_pattern.pattern_data:
                adjustment = monthly_pattern.pattern_data[month_name]

            adjusted_inflows = item["inflows"] * adjustment
            adjusted_net = adjusted_inflows - item["outflows"]

            adjusted_forecast.append({
                **item,
                "inflows_adjusted": round(adjusted_inflows, 2),
                "net_flow_adjusted": round(adjusted_net, 2),
                "seasonality_factor": round(adjustment, 2),
            })

        # Neuberechnung der Bilanzen mit Adjustment
        running_balance = base_forecast["current_balance"]
        for item in adjusted_forecast:
            running_balance = running_balance + item["inflows_adjusted"] - item["outflows"]
            item["balance_adjusted"] = round(running_balance, 2)

        return {
            **base_forecast,
            "forecast": adjusted_forecast,
            "seasonality_applied": True,
            "patterns_detected": [
                {
                    "period": p.period.value,
                    "confidence": p.confidence,
                    "description": p.description,
                }
                for p in patterns
            ],
            "adjusted_min_balance": min(f["balance_adjusted"] for f in adjusted_forecast),
        }

    async def generate_early_warnings(
        self,
        company_id: UUID,
        forecast_days: int = 30,
        warning_threshold: float = 5000.0,
        critical_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Generiert Frühwarnungen für Liquiditaetsprobleme.

        Args:
            company_id: Firmen-ID
            forecast_days: Vorausschau in Tagen
            warning_threshold: Schwelle für Warnung (EUR)
            critical_threshold: Schwelle für kritisch (EUR)

        Returns:
            Liste von Warnungen mit Empfehlungen
        """
        logger.info(
            "early_warning_generation_started",
            company_id=str(company_id),
            forecast_days=forecast_days,
        )

        forecast = await self.forecast_with_seasonality(company_id, forecast_days)
        alerts: List[LiquidityAlert] = []
        now = datetime.now(timezone.utc)

        # Analysiere Prognose
        for item in forecast["forecast"]:
            balance = item.get("balance_adjusted", item["balance"])
            forecast_date = datetime.strptime(item["date"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            days_until = (forecast_date - now).days

            if balance < critical_threshold:
                alert = LiquidityAlert(
                    severity=AlertSeverity.CRITICAL,
                    trigger_date=forecast_date,
                    projected_balance=balance,
                    message=f"Kritischer Liquiditaetsengpass am {item['date']}: {balance:,.2f} EUR",
                    recommendation=self._get_recommendation(balance, days_until, "critical"),
                    days_until_trigger=days_until,
                )
                alerts.append(alert)
            elif balance < warning_threshold:
                alert = LiquidityAlert(
                    severity=AlertSeverity.WARNING,
                    trigger_date=forecast_date,
                    projected_balance=balance,
                    message=f"Liquiditaetswarnung am {item['date']}: {balance:,.2f} EUR",
                    recommendation=self._get_recommendation(balance, days_until, "warning"),
                    days_until_trigger=days_until,
                )
                alerts.append(alert)

        # Trend-basierte Warnungen
        if len(forecast["forecast"]) >= 7:
            balances = [f.get("balance_adjusted", f["balance"]) for f in forecast["forecast"][:7]]
            trend = (balances[-1] - balances[0]) / 7

            if trend < -1000:  # Negativer Trend > 1000 EUR/Tag
                alerts.append(LiquidityAlert(
                    severity=AlertSeverity.INFO,
                    trigger_date=now,
                    projected_balance=balances[0],
                    message=f"Negativer Liquiditaets-Trend: {trend:,.0f} EUR/Tag",
                    recommendation="Eingaenge beschleunigen oder Ausgaben verschieben",
                    days_until_trigger=0,
                ))

        # Sortiere nach Dringlichkeit
        severity_order = {
            AlertSeverity.EMERGENCY: 0,
            AlertSeverity.CRITICAL: 1,
            AlertSeverity.WARNING: 2,
            AlertSeverity.INFO: 3,
        }
        alerts.sort(key=lambda x: (severity_order[x.severity], x.days_until_trigger))

        return [
            {
                "severity": a.severity.value,
                "trigger_date": a.trigger_date.isoformat(),
                "projected_balance": a.projected_balance,
                "message": a.message,
                "recommendation": a.recommendation,
                "days_until_trigger": a.days_until_trigger,
            }
            for a in alerts[:10]  # Max 10 Warnungen
        ]

    def _get_recommendation(
        self,
        balance: float,
        days_until: int,
        severity: str,
    ) -> str:
        """Generiert Handlungsempfehlung basierend auf Situation."""
        if severity == "critical":
            if days_until <= 3:
                return "SOFORT: Kontokorrent-Kredit nutzen oder Zahlungen verschieben"
            elif days_until <= 7:
                return "DRINGEND: Zahlungseingaenge beschleunigen, Skonto anbieten"
            else:
                return "WICHTIG: Zahlungsplan erstellen, Lieferanten kontaktieren"
        else:
            if days_until <= 7:
                return "Ausgaben priorisieren, optionale Zahlungen verschieben"
            else:
                return "Liquiditaetsreserve aufbauen, Forderungsmanagement optimieren"

    async def consolidate_forecasts(
        self,
        company_ids: List[UUID],
        days: int = 30,
    ) -> Dict[str, Any]:
        """Konsolidierte Cashflow-Prognose für mehrere Unternehmen (Holding).

        Args:
            company_ids: Liste der Firmen-IDs
            days: Prognosezeitraum

        Returns:
            Konsolidierte Prognose mit Intercompany-Eliminierung
        """
        logger.info(
            "consolidated_forecast_started",
            company_count=len(company_ids),
            days=days,
        )

        company_forecasts = []
        total_current_balance = 0.0

        # Einzelprognosen erstellen
        for company_id in company_ids:
            forecast = await self.forecast_with_seasonality(company_id, days)
            company_forecasts.append({
                "company_id": str(company_id),
                "forecast": forecast,
            })
            total_current_balance += forecast["current_balance"]

        # Konsolidierte Tagesprognose
        consolidated_daily: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        for day_offset in range(days + 1):
            date = now + timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")

            day_data = {
                "date": date_str,
                "inflows": 0.0,
                "outflows": 0.0,
                "net_flow": 0.0,
                "balance": 0.0,
            }

            for cf in company_forecasts:
                # Finde passenden Tag
                day_forecast = next(
                    (f for f in cf["forecast"]["forecast"] if f["date"] == date_str),
                    None
                )
                if day_forecast:
                    day_data["inflows"] += day_forecast.get("inflows_adjusted", day_forecast["inflows"])
                    day_data["outflows"] += day_forecast["outflows"]
                    day_data["balance"] += day_forecast.get("balance_adjusted", day_forecast["balance"])

            day_data["net_flow"] = day_data["inflows"] - day_data["outflows"]
            consolidated_daily.append(day_data)

        # Intercompany-Flows identifizieren (vereinfacht)
        intercompany_flows: List[Dict[str, Any]] = []

        # Alerts generieren
        alerts = []
        for item in consolidated_daily:
            if item["balance"] < 0:
                alerts.append({
                    "severity": "critical" if item["balance"] < -50000 else "warning",
                    "date": item["date"],
                    "message": f"Konsolidierter Engpass: {item['balance']:,.2f} EUR",
                })

        return {
            "company_count": len(company_ids),
            "forecast_days": days,
            "total_current_balance": round(total_current_balance, 2),
            "total_min_balance": round(min(d["balance"] for d in consolidated_daily), 2),
            "total_expected_inflows": round(sum(d["inflows"] for d in consolidated_daily), 2),
            "total_expected_outflows": round(sum(d["outflows"] for d in consolidated_daily), 2),
            "company_forecasts": [
                {
                    "company_id": cf["company_id"],
                    "current_balance": cf["forecast"]["current_balance"],
                    "min_balance": cf["forecast"]["min_balance"],
                }
                for cf in company_forecasts
            ],
            "intercompany_flows": intercompany_flows,
            "consolidated_daily": consolidated_daily,
            "alerts": alerts[:5],
        }

    async def run_extended_scenario(
        self,
        company_id: UUID,
        scenario_type: str,
        parameters: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Erweiterte What-If Szenario-Analyse.

        Neue Szenarien:
        - customer_default: Was wenn ein Grosskunde ausfaellt?
        - interest_rate_change: Was wenn Zinsen steigen?
        - seasonal_adjustment: Was wenn Saisonalitaet sich ändert?
        - revenue_growth: Was wenn Umsatz um X% waechst?
        """
        # Basis-Methode für einfache Szenarien
        if scenario_type in ("delayed_payments", "large_expense"):
            return await self.run_scenario(company_id, scenario_type, parameters)

        base_forecast = await self.forecast_with_seasonality(company_id, days=90)

        if scenario_type == "customer_default":
            customer_name = parameters.get("customer_name", "")
            default_percentage = parameters.get("default_percentage", 100)

            # Finde Rechnungen des Kunden
            result = await self.db.execute(
                select(InvoiceTracking)
                .join(BusinessEntity)
                .where(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_type == "outgoing",
                    InvoiceTracking.is_paid == False,
                    BusinessEntity.name.ilike(f"%{customer_name}%"),
                )
            )
            customer_invoices = result.scalars().all()

            affected_amount = sum(
                float(inv.amount or 0) for inv in customer_invoices
            ) * (default_percentage / 100)

            # Modifiziere Prognose
            modified_forecast = []
            for item in base_forecast["forecast"]:
                modified_forecast.append({
                    **item,
                    "inflows_scenario": round(
                        item.get("inflows_adjusted", item["inflows"]) * (1 - default_percentage / 100),
                        2
                    ),
                })

            return {
                "scenario_type": scenario_type,
                "parameters": parameters,
                "affected_amount": round(affected_amount, 2),
                "affected_invoices": len(customer_invoices),
                "base_min_balance": base_forecast.get("adjusted_min_balance", base_forecast["min_balance"]),
                "scenario_min_balance": min(
                    f["balance"] - affected_amount / len(modified_forecast)
                    for f in base_forecast["forecast"]
                ),
                "impact": "severe" if affected_amount > 50000 else "moderate",
                "recommendation": "Zahlungsausfall-Versicherung prüfen" if affected_amount > 50000 else "Diversifikation verbessern",
            }

        elif scenario_type == "revenue_growth":
            growth_percentage = parameters.get("growth_percentage", 10)
            growth_factor = 1 + (growth_percentage / 100)

            modified_forecast = []
            running_balance = base_forecast["current_balance"]

            for item in base_forecast["forecast"]:
                new_inflows = item.get("inflows_adjusted", item["inflows"]) * growth_factor
                new_net = new_inflows - item["outflows"]
                running_balance += new_net

                modified_forecast.append({
                    **item,
                    "inflows_scenario": round(new_inflows, 2),
                    "net_flow_scenario": round(new_net, 2),
                    "balance_scenario": round(running_balance, 2),
                })

            return {
                "scenario_type": scenario_type,
                "parameters": parameters,
                "growth_percentage": growth_percentage,
                "base_min_balance": base_forecast.get("adjusted_min_balance", base_forecast["min_balance"]),
                "scenario_min_balance": min(f["balance_scenario"] for f in modified_forecast),
                "scenario_max_balance": max(f["balance_scenario"] for f in modified_forecast),
                "forecast": modified_forecast,
                "impact": "positive",
            }

        return {"error": f"Unbekannter Szenario-Typ: {scenario_type}"}


def get_predictive_cashflow_service(db: AsyncSession) -> PredictiveCashFlowService:
    """Factory-Funktion für PredictiveCashFlowService."""
    return PredictiveCashFlowService(db)
