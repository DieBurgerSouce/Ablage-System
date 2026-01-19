"""
Predictive Cash-Flow Service.

ML-basierte Vorhersage von Zahlungseingaengen und Liquiditaetsengpaessen.

Features:
- Zahlungseingangs-Vorhersage pro Rechnung
- Liquiditaetsprognose (7/14/30 Tage)
- Zahlungsverzugs-Wahrscheinlichkeit
- Optimale Zahlungszeitpunkt-Empfehlung
- What-If Szenarien

Created: 2026-01-19
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
import math

import structlog
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Company,
    InvoiceTracking,
    BankTransaction,
    BankAccount,
    BusinessEntity,
)

logger = structlog.get_logger(__name__)


class PredictiveCashFlowService:
    """Service fuer ML-basierte Cashflow-Vorhersagen."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def predict_payment_date(
        self,
        invoice_id: UUID,
    ) -> Dict[str, Any]:
        """Vorhersage des Zahlungseingangs fuer eine Rechnung.

        Berechnet basierend auf:
        - Historisches Zahlungsverhalten des Kunden
        - Rechnungsbetrag (groessere Betraege = laengere Zahlungsziele)
        - Wochentag der Rechnungsstellung
        - Saisonale Faktoren

        Returns:
            predicted_date: Vorhergesagtes Zahlungsdatum
            confidence: Konfidenz der Vorhersage (0-1)
            delay_probability: Wahrscheinlichkeit einer Verspaetung
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

        # Verspaetungs-Wahrscheinlichkeit
        if invoice.due_date:
            days_until_due = (invoice.due_date - datetime.now(timezone.utc)).days
            if days_until_due < 0:
                delay_probability = 0.95  # Bereits ueberfaellig
            elif predicted_date > invoice.due_date:
                delay_probability = 0.7
            else:
                delay_probability = max(0.1, 1 - (days_until_due / 60))
        else:
            delay_probability = 0.3  # Default ohne Faelligkeitsdatum

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
        """Liquiditaetsprognose fuer die naechsten X Tage.

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
        """Empfehlungen fuer optimale Zahlungszeitpunkte.

        Beruecksichtigt:
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
            # Pruefen ob Skonto moeglich
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
                reason = "Ueberfaellig - sofort zahlen"
            elif urgency == "critical":
                recommendation = "pay_soon"
                reason = "Faellig in weniger als 3 Tagen"

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
        - delayed_payments: Was wenn X% der Zahlungen sich verzoegern?
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
        """Betragsabhaengiger Faktor (groessere Betraege = laengere Zahlung)."""
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
        """Wochentags-Faktor (Rechnungen am Freitag = laengere Zahlung)."""
        if not date:
            return 1.0
        weekday = date.weekday()
        # Freitag und Wochenende
        if weekday >= 4:
            return 1.1
        return 1.0

    def _calculate_seasonal_factor(self, date: datetime) -> float:
        """Saisonaler Faktor (Jahresende/Urlaubszeit = laengere Zahlung)."""
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
            # Vorhersage basierend auf Faelligkeitsdatum oder Durchschnitt
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
            # Zahlungszeitpunkt: Skonto-Frist oder Faelligkeitsdatum
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
