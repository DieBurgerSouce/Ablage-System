# -*- coding: utf-8 -*-
"""Prediction Engine - Zeitreihen-Analyse fuer Finanzprognosen.

Bietet:
- Wochenweise Cashflow-Prognose mit Exponential Moving Average (EMA)
- Erkennung ungewoehnlicher Ausgaben-Muster (>2 Standardabweichungen)
- Multi-Tenant Support via company_id

Feinpoliert und durchdacht.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_entity_business import BusinessEntity, InvoiceTracking
from app.db.models_banking import BankTransaction

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------


@dataclass
class WeekForecast:
    """Prognose fuer eine einzelne Woche."""

    week_start: date
    week_end: date
    expected_inflow: Decimal
    expected_outflow: Decimal
    projected_balance: Decimal
    confidence: float  # 0.0 – 1.0


@dataclass
class CashflowForecast:
    """Aggregierte Cashflow-Prognose."""

    weeks: List[WeekForecast] = field(default_factory=list)
    total_inflow: Decimal = Decimal("0.00")
    total_outflow: Decimal = Decimal("0.00")
    projected_balance: Decimal = Decimal("0.00")
    confidence: float = 0.0


@dataclass
class SpendingAnomaly:
    """Erkannte Ausgaben-Anomalie."""

    vendor_name: str
    invoice_amount: Decimal
    vendor_avg: Decimal
    deviation_factor: float
    description: str  # Deutschsprachig


# ---------------------------------------------------------------------------
# EMA-Hilfsfunktion
# ---------------------------------------------------------------------------


def _compute_ema(values: List[Decimal], alpha: float = 0.3) -> Decimal:
    """Berechnet Exponential Moving Average (EMA).

    Args:
        values: Zeitreihe (chronologisch aufsteigend).
        alpha: Glaettungsfaktor 0 < alpha <= 1.

    Returns:
        EMA-Wert der Zeitreihe.
    """
    if not values:
        return Decimal("0.00")
    ema = values[0]
    for v in values[1:]:
        ema = Decimal(str(alpha)) * v + (Decimal("1") - Decimal(str(alpha))) * ema
    return ema


# ---------------------------------------------------------------------------
# PredictionEngine
# ---------------------------------------------------------------------------


class PredictionEngine:
    """Zeitreihen-Analyse fuer Finanzprognosen.

    Verwendet ausschliesslich einfache statistische Methoden (EMA,
    Standardabweichung) – keine externen ML-Bibliotheken erforderlich.
    """

    # Skonto-Zeitraum-Schwellwert: Rechnungen innerhalb der naechsten N Wochen
    _FORECAST_LOOKBACK_DAYS: int = 90

    # Mindestanzahl historischer Datenpunkte fuer belastbare Prognose
    _MIN_DATA_POINTS: int = 3

    # Anomalie-Schwellwert in Standardabweichungen
    _ANOMALY_STD_THRESHOLD: float = 2.0

    async def predict_cashflow(
        self,
        db: AsyncSession,
        company_id: UUID,
        weeks: int = 4,
    ) -> CashflowForecast:
        """Wochenweise Cashflow-Prognose basierend auf offenen Rechnungen
        und historischen Mustern.

        Args:
            db: Async-Datenbank-Session.
            company_id: Mandant-ID fuer Multi-Tenant-Isolation.
            weeks: Anzahl Prognose-Wochen (Standard: 4).

        Returns:
            CashflowForecast mit wochenweisen Teilprognosen.
        """
        log = logger.bind(company_id=str(company_id), weeks=weeks)
        log.info("Starte Cashflow-Prognose")

        today = date.today()
        lookback_start = today - timedelta(days=self._FORECAST_LOOKBACK_DAYS)

        # --- 1. Historische Transaktionsdaten laden ---
        inflow_series, outflow_series = await self._load_weekly_transaction_history(
            db, company_id, lookback_start, today
        )

        # --- 2. EMA-Basislinie berechnen ---
        base_inflow = _compute_ema(inflow_series)
        base_outflow = _compute_ema(outflow_series)

        # Konfidenz: hoeher wenn mehr Datenpunkte vorhanden
        data_points = min(len(inflow_series), len(outflow_series))
        confidence = min(1.0, data_points / max(self._MIN_DATA_POINTS, 1) * 0.7)

        # --- 3. Offene Rechnungen laden und wochenweise verteilen ---
        open_invoice_schedule = await self._load_open_invoice_schedule(
            db, company_id, today, weeks
        )

        # --- 4. Wochenweise Prognosen aufbauen ---
        week_forecasts: List[WeekForecast] = []
        running_balance = Decimal("0.00")

        for week_idx in range(weeks):
            w_start = today + timedelta(weeks=week_idx)
            w_end = w_start + timedelta(days=6)

            # Einnahmen = EMA-Basislinie + bekannte faellige Eingangszahlungen
            week_inflow = base_inflow + open_invoice_schedule.get(
                week_idx, Decimal("0.00")
            )
            week_outflow = base_outflow

            running_balance += week_inflow - week_outflow

            week_forecasts.append(
                WeekForecast(
                    week_start=w_start,
                    week_end=w_end,
                    expected_inflow=week_inflow.quantize(Decimal("0.01")),
                    expected_outflow=week_outflow.quantize(Decimal("0.01")),
                    projected_balance=running_balance.quantize(Decimal("0.01")),
                    confidence=round(confidence, 3),
                )
            )

        total_inflow = sum(
            (w.expected_inflow for w in week_forecasts), Decimal("0.00")
        )
        total_outflow = sum(
            (w.expected_outflow for w in week_forecasts), Decimal("0.00")
        )

        log.info(
            "Cashflow-Prognose abgeschlossen",
            total_inflow=str(total_inflow),
            total_outflow=str(total_outflow),
            confidence=confidence,
        )

        return CashflowForecast(
            weeks=week_forecasts,
            total_inflow=total_inflow.quantize(Decimal("0.01")),
            total_outflow=total_outflow.quantize(Decimal("0.01")),
            projected_balance=running_balance.quantize(Decimal("0.01")),
            confidence=round(confidence, 3),
        )

    async def predict_spending_anomalies(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[SpendingAnomaly]:
        """Erkennt ungewoehnliche Ausgaben-Muster pro Lieferant.

        Vergleicht aktuelle Rechnungsbetraege mit dem historischen
        Lieferanten-Durchschnitt. Flaggt Ausreisser >2 Standardabweichungen.

        Args:
            db: Async-Datenbank-Session.
            company_id: Mandant-ID.

        Returns:
            Liste erkannter Ausgaben-Anomalien (kann leer sein).
        """
        log = logger.bind(company_id=str(company_id))
        log.info("Starte Ausgaben-Anomalie-Erkennung")

        lookback_start = date.today() - timedelta(days=self._FORECAST_LOOKBACK_DAYS)

        # Historische Rechnungsbetraege pro Entity laden
        vendor_history = await self._load_vendor_invoice_history(
            db, company_id, lookback_start
        )

        # Aktuelle (offene) Rechnungen laden
        current_invoices = await self._load_current_open_invoices(db, company_id)

        anomalies: List[SpendingAnomaly] = []

        for entity_id, invoice_amount, vendor_name in current_invoices:
            history = vendor_history.get(entity_id, [])
            if len(history) < self._MIN_DATA_POINTS:
                continue  # Zu wenig Daten fuer Vergleich

            avg = Decimal(str(statistics.mean(float(h) for h in history)))
            try:
                std = Decimal(str(statistics.stdev(float(h) for h in history)))
            except statistics.StatisticsError:
                continue

            if std == Decimal("0.00"):
                continue

            deviation_factor = float(
                (invoice_amount - avg) / std
            )

            if abs(deviation_factor) >= self._ANOMALY_STD_THRESHOLD:
                direction = "hoeher" if deviation_factor > 0 else "niedriger"
                description = (
                    f"Rechnung von {vendor_name} ist {abs(deviation_factor):.1f}x "
                    f"Standardabweichungen {direction} als der historische Durchschnitt "
                    f"({avg:.2f} EUR)."
                )
                anomalies.append(
                    SpendingAnomaly(
                        vendor_name=vendor_name or "Unbekannter Lieferant",
                        invoice_amount=invoice_amount.quantize(Decimal("0.01")),
                        vendor_avg=avg.quantize(Decimal("0.01")),
                        deviation_factor=round(deviation_factor, 2),
                        description=description,
                    )
                )

        log.info("Anomalie-Erkennung abgeschlossen", anomalies_found=len(anomalies))
        return anomalies

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    async def _load_weekly_transaction_history(
        self,
        db: AsyncSession,
        company_id: UUID,
        start: date,
        end: date,
    ) -> Tuple[List[Decimal], List[Decimal]]:
        """Laedt wochenweise Transaktionssummen aus bank_transactions.

        Returns:
            (inflow_series, outflow_series) – je chronologisch aufsteigend.
        """
        from app.db.models_banking import BankAccount

        # Alle BankAccounts der Firma
        account_stmt = select(BankAccount.id).where(
            BankAccount.company_id == company_id
        )
        account_result = await db.execute(account_stmt)
        account_ids = [row[0] for row in account_result.fetchall()]

        if not account_ids:
            return [], []

        inflow_by_week: Dict[int, Decimal] = {}
        outflow_by_week: Dict[int, Decimal] = {}

        start_dt = datetime.combine(start, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.combine(end, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )

        stmt = select(
            BankTransaction.booking_date,
            BankTransaction.amount,
        ).where(
            and_(
                BankTransaction.bank_account_id.in_(account_ids),
                BankTransaction.booking_date >= start_dt,
                BankTransaction.booking_date < end_dt,
            )
        )
        result = await db.execute(stmt)
        rows = result.fetchall()

        for booking_date, amount in rows:
            if booking_date is None or amount is None:
                continue
            if hasattr(booking_date, "date"):
                tx_date = booking_date.date()
            else:
                tx_date = booking_date
            week_idx = (tx_date - start).days // 7
            amt = Decimal(str(amount))
            if amt >= Decimal("0"):
                inflow_by_week[week_idx] = (
                    inflow_by_week.get(week_idx, Decimal("0.00")) + amt
                )
            else:
                outflow_by_week[week_idx] = (
                    outflow_by_week.get(week_idx, Decimal("0.00")) + abs(amt)
                )

        total_weeks = ((end - start).days // 7) + 1
        inflow_series = [
            inflow_by_week.get(i, Decimal("0.00")) for i in range(total_weeks)
        ]
        outflow_series = [
            outflow_by_week.get(i, Decimal("0.00")) for i in range(total_weeks)
        ]
        return inflow_series, outflow_series

    async def _load_open_invoice_schedule(
        self,
        db: AsyncSession,
        company_id: UUID,
        today: date,
        weeks: int,
    ) -> Dict[int, Decimal]:
        """Verteilt offene Eingangsrechnungen auf Prognose-Wochen anhand due_date.

        Returns:
            Dict {week_index: expected_amount}.
        """
        end_date = today + timedelta(weeks=weeks)
        today_dt = datetime.combine(today, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )
        end_dt = datetime.combine(end_date, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )

        stmt = select(
            InvoiceTracking.due_date,
            InvoiceTracking.amount,
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status == "open",
                InvoiceTracking.due_date >= today_dt,
                InvoiceTracking.due_date < end_dt,
            )
        )
        result = await db.execute(stmt)

        schedule: Dict[int, Decimal] = {}
        for due_date, amount in result.fetchall():
            if due_date is None or amount is None:
                continue
            if hasattr(due_date, "date"):
                due = due_date.date()
            else:
                due = due_date
            week_idx = (due - today).days // 7
            amt = Decimal(str(amount))
            schedule[week_idx] = schedule.get(week_idx, Decimal("0.00")) + amt

        return schedule

    async def _load_vendor_invoice_history(
        self,
        db: AsyncSession,
        company_id: UUID,
        start: date,
    ) -> Dict[UUID, List[Decimal]]:
        """Laedt historische Rechnungsbetraege pro Entity.

        Returns:
            Dict {entity_id: [amount, ...]}.
        """
        from app.db.models import Document

        start_dt = datetime.combine(start, datetime.min.time()).replace(
            tzinfo=timezone.utc
        )

        stmt = (
            select(
                Document.business_entity_id,
                InvoiceTracking.amount,
            )
            .join(Document, Document.id == InvoiceTracking.document_id)
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.invoice_date >= start_dt,
                    Document.business_entity_id.isnot(None),
                    InvoiceTracking.amount.isnot(None),
                )
            )
        )
        result = await db.execute(stmt)

        history: Dict[UUID, List[Decimal]] = {}
        for entity_id, amount in result.fetchall():
            if entity_id is None:
                continue
            history.setdefault(entity_id, []).append(Decimal(str(amount)))

        return history

    async def _load_current_open_invoices(
        self,
        db: AsyncSession,
        company_id: UUID,
    ) -> List[Tuple[UUID, Decimal, str]]:
        """Laedt aktuell offene Rechnungen mit Entity-Namen.

        Returns:
            Liste von (entity_id, amount, vendor_name) Tupeln.
        """
        from app.db.models import Document

        stmt = (
            select(
                Document.business_entity_id,
                InvoiceTracking.amount,
                BusinessEntity.name,
            )
            .join(Document, Document.id == InvoiceTracking.document_id)
            .outerjoin(
                BusinessEntity,
                BusinessEntity.id == Document.business_entity_id,
            )
            .where(
                and_(
                    InvoiceTracking.company_id == company_id,
                    InvoiceTracking.status == "open",
                    Document.business_entity_id.isnot(None),
                    InvoiceTracking.amount.isnot(None),
                )
            )
        )
        result = await db.execute(stmt)
        return [
            (entity_id, Decimal(str(amount)), vendor_name or "")
            for entity_id, amount, vendor_name in result.fetchall()
            if entity_id is not None
        ]
