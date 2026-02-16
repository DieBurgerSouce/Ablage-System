# -*- coding: utf-8 -*-
"""Cash-Flow Service.

Berechnet Cash-Flow-Prognosen basierend auf:
- Offene Forderungen (Eingangsrechnungen)
- Offene Verbindlichkeiten (Ausgangsrechnungen)
- Historisches Zahlungsverhalten
- Geplante Zahlungen

Features:
- Tages/Wochen/Monats-Projektion
- Wahrscheinlichkeitsgewichtung
- Szenario-Analyse (optimistisch/realistisch/pessimistisch)
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from app.core.datetime_utils import utc_now
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
from uuid import UUID
import structlog

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.banking.models import (
    CashFlowDirection,
    CashFlowStatus,
    CashFlowEntryResponse,
    CashFlowForecast,
    PaymentStatus,
    ReconciliationStatus,
)
from app.db.models import Document, BankTransaction, PaymentOrder

if TYPE_CHECKING:
    pass  # Imports moved above for runtime availability

logger = structlog.get_logger(__name__)


class ForecastPeriod(str, Enum):
    """Prognose-Zeitraum."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ForecastScenario(str, Enum):
    """Prognose-Szenario."""
    OPTIMISTIC = "optimistic"
    REALISTIC = "realistic"
    PESSIMISTIC = "pessimistic"


@dataclass
class CashFlowEntry:
    """Einzelner Cash-Flow-Eintrag."""
    date: date
    amount: Decimal
    direction: CashFlowDirection
    source: str  # "receivable", "payable", "scheduled_payment", "recurring"
    reference: Optional[str] = None
    document_id: Optional[UUID] = None
    payment_id: Optional[UUID] = None
    probability: float = 1.0  # 0.0 - 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CashFlowProjection:
    """Cash-Flow-Projektion für einen Zeitraum."""
    start_date: date
    end_date: date
    period: ForecastPeriod
    scenario: ForecastScenario

    # Summen
    total_inflow: Decimal = Decimal("0.00")
    total_outflow: Decimal = Decimal("0.00")
    net_flow: Decimal = Decimal("0.00")

    # Details
    entries: List[CashFlowEntry] = field(default_factory=list)
    daily_balances: Dict[date, Decimal] = field(default_factory=dict)

    # Risiko-Indikatoren
    min_balance: Decimal = Decimal("0.00")
    min_balance_date: Optional[date] = None
    days_negative: int = 0


class CashFlowService:
    """Service für Cash-Flow-Prognosen."""

    # Konfiguration
    DEFAULT_FORECAST_DAYS = 90
    PAYMENT_BEHAVIOR_WEIGHTS = {
        "on_time": 1.0,      # Zahlt puenktlich
        "late_7": 0.9,       # Bis 7 Tage spät
        "late_14": 0.7,      # Bis 14 Tage spät
        "late_30": 0.5,      # Bis 30 Tage spät
        "late_60": 0.3,      # Bis 60 Tage spät
        "default": 0.8,      # Ohne Historie
    }

    async def get_cash_flow_forecast(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        days_ahead: int = DEFAULT_FORECAST_DAYS,
        scenario: ForecastScenario = ForecastScenario.REALISTIC,
        period: ForecastPeriod = ForecastPeriod.DAILY,
        starting_balance: Optional[Decimal] = None,
    ) -> CashFlowProjection:
        """Erstelle Cash-Flow-Prognose.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optional - nur für bestimmtes Konto
            days_ahead: Tage in die Zukunft
            scenario: Prognose-Szenario
            period: Aggregations-Zeitraum
            starting_balance: Anfangssaldo (optional)

        Returns:
            CashFlowProjection mit Details
        """
        today = date.today()
        end_date = today + timedelta(days=days_ahead)

        projection = CashFlowProjection(
            start_date=today,
            end_date=end_date,
            period=period,
            scenario=scenario,
        )

        # 1. Offene Forderungen (erwartete Einnahmen)
        receivables = await self._get_open_receivables(
            db, user_id, bank_account_id, end_date
        )

        # 2. Offene Verbindlichkeiten (erwartete Ausgaben)
        payables = await self._get_open_payables(
            db, user_id, bank_account_id, end_date
        )

        # 3. Geplante Zahlungen
        scheduled = await self._get_scheduled_payments(
            db, user_id, bank_account_id, end_date
        )

        # 4. Wahrscheinlichkeiten basierend auf Szenario anpassen
        all_entries = self._apply_scenario(
            receivables + payables + scheduled,
            scenario
        )

        # 5. Projektion berechnen
        projection.entries = all_entries
        projection = self._calculate_projection(
            projection, starting_balance or Decimal("0.00")
        )

        logger.info(
            "cash_flow_forecast_created",
            user_id=str(user_id),
            days_ahead=days_ahead,
            scenario=scenario.value,
            total_inflow=float(projection.total_inflow),
            total_outflow=float(projection.total_outflow),
            net_flow=float(projection.net_flow),
        )

        return projection

    async def get_cash_flow_summary(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Hole Cash-Flow-Zusammenfassung.

        Returns:
            Dictionary mit Kennzahlen
        """
        today = date.today()

        # Kurzfristig (7 Tage)
        short_term = await self.get_cash_flow_forecast(
            db, user_id, bank_account_id, days_ahead=7
        )

        # Mittelfristig (30 Tage)
        mid_term = await self.get_cash_flow_forecast(
            db, user_id, bank_account_id, days_ahead=30
        )

        # Langfristig (90 Tage)
        long_term = await self.get_cash_flow_forecast(
            db, user_id, bank_account_id, days_ahead=90
        )

        return {
            "generated_at": utc_now().isoformat(),
            "short_term": {
                "period": "7 Tage",
                "inflow": float(short_term.total_inflow),
                "outflow": float(short_term.total_outflow),
                "net": float(short_term.net_flow),
            },
            "mid_term": {
                "period": "30 Tage",
                "inflow": float(mid_term.total_inflow),
                "outflow": float(mid_term.total_outflow),
                "net": float(mid_term.net_flow),
            },
            "long_term": {
                "period": "90 Tage",
                "inflow": float(long_term.total_inflow),
                "outflow": float(long_term.total_outflow),
                "net": float(long_term.net_flow),
            },
            "alerts": self._generate_alerts(short_term, mid_term, long_term),
        }

    async def get_daily_forecast(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        """Hole tägliche Cash-Flow-Prognose.

        Returns:
            Liste mit täglichen Werten
        """
        projection = await self.get_cash_flow_forecast(
            db, user_id, bank_account_id, days_ahead=days
        )

        daily = []
        current_date = projection.start_date

        while current_date <= projection.end_date:
            day_entries = [e for e in projection.entries if e.date == current_date]

            inflow = sum(
                e.amount * Decimal(str(e.probability))
                for e in day_entries
                if e.direction == CashFlowDirection.INFLOW
            )
            outflow = sum(
                e.amount * Decimal(str(e.probability))
                for e in day_entries
                if e.direction == CashFlowDirection.OUTFLOW
            )

            daily.append({
                "date": current_date.isoformat(),
                "inflow": float(inflow),
                "outflow": float(outflow),
                "net": float(inflow - outflow),
                "balance": float(projection.daily_balances.get(current_date, Decimal("0.00"))),
                "entries_count": len(day_entries),
            })

            current_date += timedelta(days=1)

        return daily

    async def compare_scenarios(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        days_ahead: int = 90,
    ) -> Dict[str, Any]:
        """Vergleiche verschiedene Szenarien.

        Returns:
            Dictionary mit Szenario-Vergleich
        """
        scenarios = {}

        for scenario in ForecastScenario:
            projection = await self.get_cash_flow_forecast(
                db, user_id, bank_account_id,
                days_ahead=days_ahead,
                scenario=scenario
            )

            scenarios[scenario.value] = {
                "total_inflow": float(projection.total_inflow),
                "total_outflow": float(projection.total_outflow),
                "net_flow": float(projection.net_flow),
                "min_balance": float(projection.min_balance),
                "min_balance_date": (
                    projection.min_balance_date.isoformat()
                    if projection.min_balance_date else None
                ),
                "days_negative": projection.days_negative,
            }

        return {
            "period_days": days_ahead,
            "scenarios": scenarios,
            "recommendation": self._get_scenario_recommendation(scenarios),
        }

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _get_open_receivables(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID],
        end_date: date,
    ) -> List[CashFlowEntry]:
        """Hole offene Forderungen."""
        entries = []

        # Dokumente mit offenen Betraegen (Eingangsrechnungen)
        query = select(Document).where(
            and_(
                Document.owner_id == user_id,
                Document.document_type == "invoice",
                Document.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        for doc in documents:
            # Extrahierte Daten prüfen
            extracted = doc.extracted_data or {}

            # Prüfen ob bereits bezahlt
            if extracted.get("payment_status") == "paid":
                continue

            amount = extracted.get("total_amount") or extracted.get("amount")
            if not amount:
                continue

            try:
                amount = Decimal(str(amount))
            except (ValueError, TypeError, InvalidOperation):
                continue

            # Fälligkeitsdatum
            due_date_str = extracted.get("due_date")
            if due_date_str:
                try:
                    if isinstance(due_date_str, str):
                        due_date = datetime.fromisoformat(due_date_str).date()
                    else:
                        due_date = due_date_str
                except (ValueError, TypeError):
                    due_date = date.today() + timedelta(days=14)
            else:
                due_date = date.today() + timedelta(days=14)

            # Nur zukünftige oder überfällige
            if due_date > end_date:
                continue

            # Wahrscheinlichkeit basierend auf Zahlungsverhalten
            probability = await self._get_payment_probability(
                db, user_id, extracted.get("creditor_name")
            )

            entries.append(CashFlowEntry(
                date=due_date,
                amount=amount,
                direction=CashFlowDirection.INFLOW,
                source="receivable",
                reference=extracted.get("invoice_number"),
                document_id=doc.id,
                probability=probability,
                metadata={
                    "creditor": extracted.get("creditor_name"),
                    "document_type": doc.document_type,
                },
            ))

        return entries

    async def _get_open_payables(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID],
        end_date: date,
    ) -> List[CashFlowEntry]:
        """Hole offene Verbindlichkeiten."""
        entries = []

        # Dokumente mit offenen Betraegen (Ausgangsrechnungen/Lieferantenrechnungen)
        query = select(Document).where(
            and_(
                Document.owner_id == user_id,
                Document.document_type.in_(["supplier_invoice", "purchase_order"]),
                Document.deleted_at.is_(None),
            )
        )

        result = await db.execute(query)
        documents = result.scalars().all()

        for doc in documents:
            extracted = doc.extracted_data or {}

            if extracted.get("payment_status") == "paid":
                continue

            amount = extracted.get("total_amount") or extracted.get("amount")
            if not amount:
                continue

            try:
                amount = Decimal(str(amount))
            except (ValueError, TypeError, InvalidOperation):
                continue

            # Fälligkeitsdatum
            due_date_str = extracted.get("due_date")
            if due_date_str:
                try:
                    if isinstance(due_date_str, str):
                        due_date = datetime.fromisoformat(due_date_str).date()
                    else:
                        due_date = due_date_str
                except (ValueError, TypeError):
                    due_date = date.today() + timedelta(days=14)
            else:
                due_date = date.today() + timedelta(days=14)

            if due_date > end_date:
                continue

            entries.append(CashFlowEntry(
                date=due_date,
                amount=amount,
                direction=CashFlowDirection.OUTFLOW,
                source="payable",
                reference=extracted.get("invoice_number"),
                document_id=doc.id,
                probability=1.0,  # Verbindlichkeiten werden immer bezahlt
                metadata={
                    "supplier": extracted.get("creditor_name"),
                    "document_type": doc.document_type,
                },
            ))

        return entries

    async def _get_scheduled_payments(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID],
        end_date: date,
    ) -> List[CashFlowEntry]:
        """Hole geplante Zahlungen."""
        entries = []

        # Genehmigte aber noch nicht ausgeführte Zahlungen
        query = select(PaymentOrder).where(
            and_(
                PaymentOrder.user_id == user_id,
                PaymentOrder.status.in_([
                    PaymentStatus.DRAFT.value,
                    PaymentStatus.APPROVED.value,
                    PaymentStatus.PENDING_TAN.value,
                ]),
            )
        )

        if bank_account_id:
            query = query.where(PaymentOrder.bank_account_id == bank_account_id)

        result = await db.execute(query)
        payments = result.scalars().all()

        for payment in payments:
            exec_date = payment.execution_date or date.today()

            if exec_date > end_date:
                continue

            # Wahrscheinlichkeit basierend auf Status
            probability = {
                PaymentStatus.DRAFT.value: 0.5,
                PaymentStatus.APPROVED.value: 0.9,
                PaymentStatus.PENDING_TAN.value: 0.95,
            }.get(payment.status, 0.8)

            entries.append(CashFlowEntry(
                date=exec_date,
                amount=payment.amount,
                direction=CashFlowDirection.OUTFLOW,
                source="scheduled_payment",
                reference=payment.reference,
                payment_id=payment.id,
                probability=probability,
                metadata={
                    "beneficiary": payment.beneficiary_name,
                    "status": payment.status,
                },
            ))

        return entries

    async def _get_payment_probability(
        self,
        db: AsyncSession,
        user_id: UUID,
        creditor_name: Optional[str],
    ) -> float:
        """Berechne Zahlungswahrscheinlichkeit basierend auf Historie."""
        if not creditor_name:
            return self.PAYMENT_BEHAVIOR_WEIGHTS["default"]

        # Historische Transaktionen dieses Kreditors analysieren
        # Vereinfachte Implementierung - in Produktion komplexere Analyse
        return self.PAYMENT_BEHAVIOR_WEIGHTS["default"]

    def _apply_scenario(
        self,
        entries: List[CashFlowEntry],
        scenario: ForecastScenario,
    ) -> List[CashFlowEntry]:
        """Wende Szenario auf Einträge an."""
        multipliers = {
            ForecastScenario.OPTIMISTIC: {
                CashFlowDirection.INFLOW: 1.1,   # +10% Einnahmen
                CashFlowDirection.OUTFLOW: 0.9,  # -10% Ausgaben
            },
            ForecastScenario.REALISTIC: {
                CashFlowDirection.INFLOW: 1.0,
                CashFlowDirection.OUTFLOW: 1.0,
            },
            ForecastScenario.PESSIMISTIC: {
                CashFlowDirection.INFLOW: 0.8,   # -20% Einnahmen
                CashFlowDirection.OUTFLOW: 1.15, # +15% Ausgaben
            },
        }

        multiplier = multipliers[scenario]

        for entry in entries:
            if entry.direction == CashFlowDirection.INFLOW:
                entry.probability *= multiplier[CashFlowDirection.INFLOW]
            else:
                entry.probability *= multiplier[CashFlowDirection.OUTFLOW]

            # Wahrscheinlichkeit auf 0-1 begrenzen
            entry.probability = min(1.0, max(0.0, entry.probability))

        return entries

    def _calculate_projection(
        self,
        projection: CashFlowProjection,
        starting_balance: Decimal,
    ) -> CashFlowProjection:
        """Berechne Projektion aus Einträgen."""
        balance = starting_balance
        min_balance = balance
        min_balance_date = projection.start_date
        days_negative = 0

        current_date = projection.start_date

        while current_date <= projection.end_date:
            day_entries = [e for e in projection.entries if e.date == current_date]

            for entry in day_entries:
                weighted_amount = entry.amount * Decimal(str(entry.probability))

                if entry.direction == CashFlowDirection.INFLOW:
                    projection.total_inflow += weighted_amount
                    balance += weighted_amount
                else:
                    projection.total_outflow += weighted_amount
                    balance -= weighted_amount

            projection.daily_balances[current_date] = balance

            if balance < min_balance:
                min_balance = balance
                min_balance_date = current_date

            if balance < 0:
                days_negative += 1

            current_date += timedelta(days=1)

        projection.net_flow = projection.total_inflow - projection.total_outflow
        projection.min_balance = min_balance
        projection.min_balance_date = min_balance_date
        projection.days_negative = days_negative

        return projection

    def _generate_alerts(
        self,
        short_term: CashFlowProjection,
        mid_term: CashFlowProjection,
        long_term: CashFlowProjection,
    ) -> List[Dict[str, Any]]:
        """Generiere Cash-Flow-Warnungen."""
        alerts = []

        # Kurzfristige Liquiditaetsprobleme
        if short_term.min_balance < 0:
            alerts.append({
                "level": "critical",
                "type": "liquidity",
                "message": f"Liquiditaetsengpass in {short_term.days_negative} von 7 Tagen erwartet",
                "date": short_term.min_balance_date.isoformat() if short_term.min_balance_date else None,
                "amount": float(short_term.min_balance),
            })

        # Mittelfristige Warnung
        if mid_term.days_negative > 5:
            alerts.append({
                "level": "warning",
                "type": "liquidity",
                "message": f"Liquiditaetsprobleme an {mid_term.days_negative} Tagen im nächsten Monat",
            })

        # Hohe Ausgaben
        if mid_term.total_outflow > mid_term.total_inflow * Decimal("1.2"):
            alerts.append({
                "level": "warning",
                "type": "cash_burn",
                "message": "Ausgaben übersteigen Einnahmen um mehr als 20%",
                "outflow": float(mid_term.total_outflow),
                "inflow": float(mid_term.total_inflow),
            })

        # Positiver Trend
        if long_term.net_flow > 0 and long_term.days_negative == 0:
            alerts.append({
                "level": "info",
                "type": "positive",
                "message": "Positiver Cash-Flow erwartet",
                "net_flow": float(long_term.net_flow),
            })

        return alerts

    def _get_scenario_recommendation(
        self,
        scenarios: Dict[str, Any],
    ) -> str:
        """Generiere Empfehlung basierend auf Szenarien."""
        pessimistic = scenarios.get("pessimistic", {})

        if pessimistic.get("days_negative", 0) > 10:
            return "Vorsicht: Auch im pessimistischen Szenario drohen Liquiditaetsprobleme. Massnahmen zur Liquiditaetssicherung empfohlen."
        elif pessimistic.get("min_balance", 0) < 0:
            return "Risiko: Im pessimistischen Szenario könnte kurzfristig Liquiditaet knapp werden. Rücklagen empfohlen."
        else:
            return "Stabil: Cash-Flow sieht in allen Szenarien solide aus."


# Singleton
cash_flow_service = CashFlowService()
