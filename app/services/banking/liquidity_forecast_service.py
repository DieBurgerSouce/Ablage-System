# -*- coding: utf-8 -*-
"""Liquidity Forecast Service.

Erweiterte Liquiditaetsprognose mit:
- Rolling-Window Forecasts (30/60/90 Tage)
- Confidence Intervals und Unsicherheitsquantifizierung
- ML-basierte Anomalie-Erkennung für Zahlungsmuster
- Engpass-Vorhersage (Liquidity Bottleneck Prediction)
- Integration mit InvoiceTracking für offene Rechnungen
- Waterfall-Chart Daten für Frontend-Visualisierung

Enterprise Feature: Januar 2026
"""

from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional, Dict, Any, List, Tuple
from uuid import UUID
import statistics
import structlog

from sqlalchemy import select, func, and_, or_, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utc_now
from app.db.models import (
    Document, BankTransaction, PaymentOrder, BankAccount,
    InvoiceTracking, BusinessEntity,
)
from app.services.banking.models import (
    CashFlowDirection,
    PaymentStatus,
)
from app.services.banking.cash_flow_service import (
    CashFlowService,
    CashFlowEntry,
    CashFlowProjection,
    ForecastPeriod,
    ForecastScenario,
)

logger = structlog.get_logger(__name__)


class LiquidityRiskLevel(str, Enum):
    """Liquiditaetsrisiko-Stufen."""
    HEALTHY = "healthy"            # > 2 Monate Liquiditaet
    ADEQUATE = "adequate"          # 1-2 Monate
    CAUTION = "caution"            # 2-4 Wochen
    WARNING = "warning"            # 1-2 Wochen
    CRITICAL = "critical"          # < 1 Woche


class AnomalyType(str, Enum):
    """Typen von Zahlungsanomalien."""
    UNUSUAL_AMOUNT = "unusual_amount"
    UNEXPECTED_TIMING = "unexpected_timing"
    MISSING_RECURRING = "missing_recurring"
    DUPLICATE_PAYMENT = "duplicate_payment"
    LARGE_OUTFLOW = "large_outflow"
    PATTERN_BREAK = "pattern_break"


class ForecastConfidence(str, Enum):
    """Vertrauensniveau der Prognose."""
    HIGH = "high"      # > 80% Confidence
    MEDIUM = "medium"  # 50-80% Confidence
    LOW = "low"        # < 50% Confidence


@dataclass
class ConfidenceInterval:
    """Konfidenzintervall für eine Prognose."""
    lower_bound: Decimal
    expected: Decimal
    upper_bound: Decimal
    confidence_level: float = 0.95  # 95% Konfidenz


@dataclass
class LiquidityBottleneck:
    """Erkannter Liquiditaetsengpass."""
    date: date
    expected_balance: Decimal
    shortfall: Decimal  # Negativer Betrag = Unterdeckung
    contributing_factors: List[str]
    severity: LiquidityRiskLevel
    recommendations: List[str]


@dataclass
class PaymentAnomaly:
    """Erkannte Zahlungsanomalie."""
    anomaly_type: AnomalyType
    date: date
    amount: Decimal
    expected_amount: Optional[Decimal] = None
    description: str = ""
    confidence: float = 0.0  # 0-1
    related_entity_id: Optional[UUID] = None
    related_document_id: Optional[UUID] = None


@dataclass
class WaterfallChartData:
    """Daten für Wasserfall-Chart."""
    label: str
    value: Decimal
    cumulative: Decimal
    is_total: bool = False
    category: str = "flow"  # "starting", "inflow", "outflow", "ending"


@dataclass
class RollingForecast:
    """Rolling-Window Prognose (30/60/90 Tage)."""
    period_days: int
    start_date: date
    end_date: date

    # Erwartete Werte
    expected_inflow: Decimal = Decimal("0.00")
    expected_outflow: Decimal = Decimal("0.00")
    expected_net_flow: Decimal = Decimal("0.00")
    expected_ending_balance: Decimal = Decimal("0.00")

    # Konfidenzintervalle
    inflow_confidence: Optional[ConfidenceInterval] = None
    outflow_confidence: Optional[ConfidenceInterval] = None
    balance_confidence: Optional[ConfidenceInterval] = None

    # Risiko-Indikatoren
    risk_level: LiquidityRiskLevel = LiquidityRiskLevel.HEALTHY
    days_until_critical: Optional[int] = None
    probability_of_shortfall: float = 0.0

    # Details
    bottlenecks: List[LiquidityBottleneck] = field(default_factory=list)
    major_inflows: List[Dict[str, Any]] = field(default_factory=list)
    major_outflows: List[Dict[str, Any]] = field(default_factory=list)

    # Vertrauensniveau
    forecast_confidence: ForecastConfidence = ForecastConfidence.MEDIUM
    data_quality_score: float = 0.0  # 0-1


@dataclass
class LiquidityForecastResult:
    """Gesamtergebnis der Liquiditaetsprognose."""
    generated_at: datetime
    starting_balance: Decimal

    # Rolling Forecasts
    forecast_30_days: RollingForecast
    forecast_60_days: RollingForecast
    forecast_90_days: RollingForecast

    # Anomalien
    detected_anomalies: List[PaymentAnomaly] = field(default_factory=list)

    # Waterfall-Daten
    waterfall_data: List[WaterfallChartData] = field(default_factory=list)

    # Empfehlungen
    recommendations: List[str] = field(default_factory=list)

    # Alerts
    alerts: List[Dict[str, Any]] = field(default_factory=list)


class LiquidityForecastService:
    """Service für erweiterte Liquiditaetsprognosen."""

    # Konfiguration
    CRITICAL_BALANCE_THRESHOLD = Decimal("-1000.00")
    WARNING_DAYS_THRESHOLD = 14  # Tage bis kritisch = Warning
    CAUTION_DAYS_THRESHOLD = 30  # Tage bis kritisch = Caution

    ANOMALY_AMOUNT_THRESHOLD = 2.0  # Standardabweichungen
    LARGE_OUTFLOW_THRESHOLD = Decimal("5000.00")  # Grosser Abfluss

    HISTORICAL_MONTHS_FOR_ANALYSIS = 6

    def __init__(self, cash_flow_service: Optional[CashFlowService] = None):
        """Initialisiere Service mit optionaler CashFlowService-Injektion."""
        self._cash_flow_service = cash_flow_service

    @property
    def cash_flow_service(self) -> CashFlowService:
        """Lazy-loaded CashFlowService."""
        if self._cash_flow_service is None:
            from app.services.banking.cash_flow_service import cash_flow_service
            self._cash_flow_service = cash_flow_service
        return self._cash_flow_service

    async def get_liquidity_forecast(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        starting_balance: Optional[Decimal] = None,
        company_id: Optional[UUID] = None,
    ) -> LiquidityForecastResult:
        """Erstelle umfassende Liquiditaetsprognose.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optional - nur für bestimmtes Konto
            starting_balance: Anfangssaldo (optional, wird ermittelt)
            company_id: Optional - Multi-Tenant Filter

        Returns:
            LiquidityForecastResult mit allen Prognosen
        """
        generated_at = utc_now()
        today = date.today()

        # 1. Anfangssaldo ermitteln
        if starting_balance is None:
            starting_balance = await self._get_current_balance(
                db, user_id, bank_account_id
            )

        # 2. Rolling Forecasts erstellen
        forecast_30 = await self._create_rolling_forecast(
            db, user_id, bank_account_id, 30, starting_balance, company_id
        )
        forecast_60 = await self._create_rolling_forecast(
            db, user_id, bank_account_id, 60, starting_balance, company_id
        )
        forecast_90 = await self._create_rolling_forecast(
            db, user_id, bank_account_id, 90, starting_balance, company_id
        )

        # 3. Anomalien erkennen
        anomalies = await self._detect_payment_anomalies(
            db, user_id, bank_account_id, company_id
        )

        # 4. Waterfall-Daten erstellen
        waterfall = self._create_waterfall_data(
            starting_balance, forecast_30
        )

        # 5. Empfehlungen generieren
        recommendations = self._generate_recommendations(
            forecast_30, forecast_60, forecast_90, anomalies
        )

        # 6. Alerts erstellen
        alerts = self._generate_alerts(
            forecast_30, forecast_60, forecast_90, anomalies
        )

        logger.info(
            "liquidity_forecast_created",
            user_id=str(user_id),
            starting_balance=float(starting_balance),
            risk_30d=forecast_30.risk_level.value,
            risk_60d=forecast_60.risk_level.value,
            risk_90d=forecast_90.risk_level.value,
            anomaly_count=len(anomalies),
        )

        return LiquidityForecastResult(
            generated_at=generated_at,
            starting_balance=starting_balance,
            forecast_30_days=forecast_30,
            forecast_60_days=forecast_60,
            forecast_90_days=forecast_90,
            detected_anomalies=anomalies,
            waterfall_data=waterfall,
            recommendations=recommendations,
            alerts=alerts,
        )

    async def get_bottleneck_prediction(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        days_ahead: int = 90,
        starting_balance: Optional[Decimal] = None,
    ) -> List[LiquidityBottleneck]:
        """Identifiziere potenzielle Liquiditaetsengpaesse.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optional - nur für bestimmtes Konto
            days_ahead: Prognosezeitraum
            starting_balance: Anfangssaldo

        Returns:
            Liste von erkannten Engpaessen
        """
        if starting_balance is None:
            starting_balance = await self._get_current_balance(
                db, user_id, bank_account_id
            )

        # Cash-Flow-Projektion erstellen
        projection = await self.cash_flow_service.get_cash_flow_forecast(
            db, user_id, bank_account_id,
            days_ahead=days_ahead,
            scenario=ForecastScenario.PESSIMISTIC,
            starting_balance=starting_balance,
        )

        bottlenecks: List[LiquidityBottleneck] = []

        # Durch tägliche Salden iterieren
        for day_date, balance in projection.daily_balances.items():
            if balance < Decimal("0"):
                # Engpass identifiziert
                factors = []

                # Ausgaben an diesem Tag
                day_outflows = [
                    e for e in projection.entries
                    if e.date == day_date and e.direction == CashFlowDirection.OUTFLOW
                ]

                for outflow in day_outflows[:3]:  # Top 3
                    metadata = outflow.metadata or {}
                    source = metadata.get("supplier") or metadata.get("beneficiary") or outflow.reference or "Unbekannt"
                    factors.append(f"Zahlung an {source}: {float(outflow.amount):.2f} EUR")

                # Severity bestimmen
                shortfall = balance  # Negativ
                if shortfall < Decimal("-10000"):
                    severity = LiquidityRiskLevel.CRITICAL
                elif shortfall < Decimal("-5000"):
                    severity = LiquidityRiskLevel.WARNING
                elif shortfall < Decimal("-1000"):
                    severity = LiquidityRiskLevel.CAUTION
                else:
                    severity = LiquidityRiskLevel.ADEQUATE

                # Empfehlungen
                recommendations = self._get_bottleneck_recommendations(
                    shortfall, day_date, day_outflows
                )

                bottlenecks.append(LiquidityBottleneck(
                    date=day_date,
                    expected_balance=balance,
                    shortfall=shortfall,
                    contributing_factors=factors,
                    severity=severity,
                    recommendations=recommendations,
                ))

        # Nur signifikante Engpaesse (nicht jeden Tag einzeln)
        return self._consolidate_bottlenecks(bottlenecks)

    async def get_waterfall_chart_data(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        period_days: int = 30,
        starting_balance: Optional[Decimal] = None,
    ) -> List[WaterfallChartData]:
        """Erstelle Daten für Wasserfall-Chart.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optional - nur für bestimmtes Konto
            period_days: Zeitraum
            starting_balance: Anfangssaldo

        Returns:
            Liste von Waterfall-Datenpunkten
        """
        if starting_balance is None:
            starting_balance = await self._get_current_balance(
                db, user_id, bank_account_id
            )

        projection = await self.cash_flow_service.get_cash_flow_forecast(
            db, user_id, bank_account_id,
            days_ahead=period_days,
            scenario=ForecastScenario.REALISTIC,
            starting_balance=starting_balance,
        )

        return self._create_waterfall_data(starting_balance, None, projection)

    async def detect_anomalies(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID] = None,
        company_id: Optional[UUID] = None,
        lookback_days: int = 90,
    ) -> List[PaymentAnomaly]:
        """Erkenne Zahlungsanomalien.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            bank_account_id: Optional - nur für bestimmtes Konto
            company_id: Optional - Multi-Tenant Filter
            lookback_days: Tage für historische Analyse

        Returns:
            Liste erkannter Anomalien
        """
        return await self._detect_payment_anomalies(
            db, user_id, bank_account_id, company_id, lookback_days
        )

    # =========================================================================
    # Private Methoden
    # =========================================================================

    async def _get_current_balance(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID],
    ) -> Decimal:
        """Ermittle aktuellen Kontostand."""
        query = select(BankAccount).where(
            and_(
                BankAccount.user_id == user_id,
                BankAccount.is_active == True,
            )
        )

        if bank_account_id:
            query = query.where(BankAccount.id == bank_account_id)

        result = await db.execute(query)
        accounts = result.scalars().all()

        total_balance = Decimal("0.00")

        for account in accounts:
            # Neueste Transaktion für Saldo
            tx_query = (
                select(BankTransaction.running_balance)
                .where(BankTransaction.bank_account_id == account.id)
                .order_by(BankTransaction.booking_date.desc())
                .limit(1)
            )
            tx_result = await db.execute(tx_query)
            balance = tx_result.scalar()

            if balance is not None:
                total_balance += Decimal(str(balance))

        return total_balance

    async def _create_rolling_forecast(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID],
        period_days: int,
        starting_balance: Decimal,
        company_id: Optional[UUID],
    ) -> RollingForecast:
        """Erstelle Rolling-Window Forecast."""
        today = date.today()
        end_date = today + timedelta(days=period_days)

        # CashFlow-Projektionen für verschiedene Szenarien
        optimistic = await self.cash_flow_service.get_cash_flow_forecast(
            db, user_id, bank_account_id,
            days_ahead=period_days,
            scenario=ForecastScenario.OPTIMISTIC,
            starting_balance=starting_balance,
        )

        realistic = await self.cash_flow_service.get_cash_flow_forecast(
            db, user_id, bank_account_id,
            days_ahead=period_days,
            scenario=ForecastScenario.REALISTIC,
            starting_balance=starting_balance,
        )

        pessimistic = await self.cash_flow_service.get_cash_flow_forecast(
            db, user_id, bank_account_id,
            days_ahead=period_days,
            scenario=ForecastScenario.PESSIMISTIC,
            starting_balance=starting_balance,
        )

        # Erwartete Werte (realistisches Szenario)
        expected_inflow = realistic.total_inflow
        expected_outflow = realistic.total_outflow
        expected_net_flow = realistic.net_flow
        expected_ending = starting_balance + expected_net_flow

        # Konfidenzintervalle berechnen
        inflow_ci = ConfidenceInterval(
            lower_bound=pessimistic.total_inflow,
            expected=realistic.total_inflow,
            upper_bound=optimistic.total_inflow,
        )

        outflow_ci = ConfidenceInterval(
            lower_bound=optimistic.total_outflow,  # Lower is better for outflow
            expected=realistic.total_outflow,
            upper_bound=pessimistic.total_outflow,
        )

        pessimistic_ending = starting_balance + pessimistic.net_flow
        optimistic_ending = starting_balance + optimistic.net_flow

        balance_ci = ConfidenceInterval(
            lower_bound=pessimistic_ending,
            expected=expected_ending,
            upper_bound=optimistic_ending,
        )

        # Risiko-Level bestimmen
        risk_level = self._assess_risk_level(
            pessimistic, expected_ending, period_days
        )

        # Tage bis kritisch
        days_until_critical = None
        for day_date, balance in pessimistic.daily_balances.items():
            if balance < self.CRITICAL_BALANCE_THRESHOLD:
                days_until_critical = (day_date - today).days
                break

        # Wahrscheinlichkeit eines Engpasses
        probability_shortfall = self._calculate_shortfall_probability(
            realistic, pessimistic
        )

        # Bottlenecks identifizieren
        bottlenecks = []
        for day_date, balance in pessimistic.daily_balances.items():
            if balance < Decimal("0"):
                # Vereinfachte Bottleneck-Erstellung
                bottlenecks.append(LiquidityBottleneck(
                    date=day_date,
                    expected_balance=balance,
                    shortfall=balance,
                    contributing_factors=[],
                    severity=LiquidityRiskLevel.WARNING if balance > Decimal("-5000") else LiquidityRiskLevel.CRITICAL,
                    recommendations=[],
                ))

        # Major In/Outflows extrahieren
        major_inflows = self._extract_major_flows(
            realistic.entries, CashFlowDirection.INFLOW, limit=5
        )
        major_outflows = self._extract_major_flows(
            realistic.entries, CashFlowDirection.OUTFLOW, limit=5
        )

        # Datenqualität bewerten
        data_quality = self._assess_data_quality(realistic.entries)

        # Forecast Confidence
        if data_quality > 0.7 and len(realistic.entries) > 10:
            forecast_confidence = ForecastConfidence.HIGH
        elif data_quality > 0.4 and len(realistic.entries) > 5:
            forecast_confidence = ForecastConfidence.MEDIUM
        else:
            forecast_confidence = ForecastConfidence.LOW

        return RollingForecast(
            period_days=period_days,
            start_date=today,
            end_date=end_date,
            expected_inflow=expected_inflow,
            expected_outflow=expected_outflow,
            expected_net_flow=expected_net_flow,
            expected_ending_balance=expected_ending,
            inflow_confidence=inflow_ci,
            outflow_confidence=outflow_ci,
            balance_confidence=balance_ci,
            risk_level=risk_level,
            days_until_critical=days_until_critical,
            probability_of_shortfall=probability_shortfall,
            bottlenecks=self._consolidate_bottlenecks(bottlenecks)[:3],
            major_inflows=major_inflows,
            major_outflows=major_outflows,
            forecast_confidence=forecast_confidence,
            data_quality_score=data_quality,
        )

    async def _detect_payment_anomalies(
        self,
        db: AsyncSession,
        user_id: UUID,
        bank_account_id: Optional[UUID],
        company_id: Optional[UUID],
        lookback_days: int = 90,
    ) -> List[PaymentAnomaly]:
        """Erkenne Anomalien in Zahlungsmustern."""
        anomalies: List[PaymentAnomaly] = []
        today = date.today()
        lookback_start = today - timedelta(days=lookback_days)

        # 1. Historische Transaktionen laden
        query = select(BankTransaction).where(
            and_(
                BankTransaction.user_id == user_id,
                BankTransaction.booking_date >= lookback_start,
            )
        )

        if bank_account_id:
            query = query.where(BankTransaction.bank_account_id == bank_account_id)

        result = await db.execute(query)
        transactions = result.scalars().all()

        if len(transactions) < 10:
            return anomalies  # Nicht genug Daten

        # 2. Statistiken berechnen
        amounts = [abs(float(tx.amount)) for tx in transactions]
        mean_amount = statistics.mean(amounts) if amounts else 0
        stdev_amount = statistics.stdev(amounts) if len(amounts) > 1 else 0

        # 3. Ungewoehnliche Betraege erkennen
        for tx in transactions:
            amount = abs(float(tx.amount))

            # Z-Score berechnen
            if stdev_amount > 0:
                z_score = (amount - mean_amount) / stdev_amount

                if abs(z_score) > self.ANOMALY_AMOUNT_THRESHOLD:
                    anomalies.append(PaymentAnomaly(
                        anomaly_type=AnomalyType.UNUSUAL_AMOUNT,
                        date=tx.booking_date.date() if tx.booking_date else today,
                        amount=Decimal(str(tx.amount)),
                        expected_amount=Decimal(str(mean_amount)),
                        description=f"Ungewoehnlicher Betrag (Z-Score: {z_score:.2f})",
                        confidence=min(0.95, abs(z_score) / 5),
                        related_document_id=tx.matched_document_id,
                    ))

        # 4. Grosse Abfluesse erkennen
        for tx in transactions:
            if tx.amount < -float(self.LARGE_OUTFLOW_THRESHOLD):
                # Prüfen ob nicht bereits als unusual_amount markiert
                already_flagged = any(
                    a.date == (tx.booking_date.date() if tx.booking_date else today)
                    and a.amount == Decimal(str(tx.amount))
                    for a in anomalies
                )

                if not already_flagged:
                    anomalies.append(PaymentAnomaly(
                        anomaly_type=AnomalyType.LARGE_OUTFLOW,
                        date=tx.booking_date.date() if tx.booking_date else today,
                        amount=Decimal(str(tx.amount)),
                        description=f"Grosser Geldabfluss: {abs(tx.amount):.2f} EUR",
                        confidence=0.8,
                        related_document_id=tx.matched_document_id,
                    ))

        # 5. Wochenend-Transaktionen (potentiell verdaechtig)
        for tx in transactions:
            if tx.booking_date and tx.booking_date.weekday() >= 5:  # Sa/So
                if abs(float(tx.amount)) > 1000:  # Nur signifikante
                    anomalies.append(PaymentAnomaly(
                        anomaly_type=AnomalyType.UNEXPECTED_TIMING,
                        date=tx.booking_date.date(),
                        amount=Decimal(str(tx.amount)),
                        description="Transaktion am Wochenende",
                        confidence=0.5,
                        related_document_id=tx.matched_document_id,
                    ))

        # Nach Confidence sortieren
        anomalies.sort(key=lambda a: a.confidence, reverse=True)

        return anomalies[:20]  # Maximal 20 Anomalien

    def _create_waterfall_data(
        self,
        starting_balance: Decimal,
        forecast: Optional[RollingForecast],
        projection: Optional[CashFlowProjection] = None,
    ) -> List[WaterfallChartData]:
        """Erstelle Waterfall-Chart Daten."""
        data: List[WaterfallChartData] = []
        cumulative = starting_balance

        # Starting Balance
        data.append(WaterfallChartData(
            label="Anfangssaldo",
            value=starting_balance,
            cumulative=cumulative,
            is_total=True,
            category="starting",
        ))

        if forecast:
            # Hauptkategorien aus Forecast
            # Erwartete Eingaenge
            inflow = forecast.expected_inflow
            cumulative += inflow
            data.append(WaterfallChartData(
                label="Erwartete Eingaenge",
                value=inflow,
                cumulative=cumulative,
                category="inflow",
            ))

            # Erwartete Ausgaben (negativ dargestellt)
            outflow = -forecast.expected_outflow
            cumulative += outflow
            data.append(WaterfallChartData(
                label="Geplante Ausgaben",
                value=outflow,
                cumulative=cumulative,
                category="outflow",
            ))

            # Endsaldo
            data.append(WaterfallChartData(
                label="Erwarteter Endsaldo",
                value=cumulative,
                cumulative=cumulative,
                is_total=True,
                category="ending",
            ))

        elif projection:
            # Detailliertere Aufschluesselung aus Projection
            # Gruppiere nach Quelle
            inflow_by_source: Dict[str, Decimal] = {}
            outflow_by_source: Dict[str, Decimal] = {}

            for entry in projection.entries:
                source = entry.source
                weighted = entry.amount * Decimal(str(entry.probability))

                if entry.direction == CashFlowDirection.INFLOW:
                    inflow_by_source[source] = inflow_by_source.get(source, Decimal("0")) + weighted
                else:
                    outflow_by_source[source] = outflow_by_source.get(source, Decimal("0")) + weighted

            # Eingaenge hinzufuegen
            for source, amount in sorted(inflow_by_source.items(), key=lambda x: x[1], reverse=True)[:5]:
                cumulative += amount
                label = {
                    "receivable": "Offene Forderungen",
                    "scheduled_payment": "Geplante Eingaenge",
                    "recurring": "Wiederkehrende Eingaenge",
                }.get(source, source.replace("_", " ").title())

                data.append(WaterfallChartData(
                    label=label,
                    value=amount,
                    cumulative=cumulative,
                    category="inflow",
                ))

            # Ausgaben hinzufuegen
            for source, amount in sorted(outflow_by_source.items(), key=lambda x: x[1], reverse=True)[:5]:
                cumulative -= amount
                label = {
                    "payable": "Offene Verbindlichkeiten",
                    "scheduled_payment": "Geplante Zahlungen",
                    "recurring": "Wiederkehrende Ausgaben",
                }.get(source, source.replace("_", " ").title())

                data.append(WaterfallChartData(
                    label=label,
                    value=-amount,
                    cumulative=cumulative,
                    category="outflow",
                ))

            # Endsaldo
            data.append(WaterfallChartData(
                label="Endsaldo",
                value=cumulative,
                cumulative=cumulative,
                is_total=True,
                category="ending",
            ))

        return data

    def _assess_risk_level(
        self,
        pessimistic: CashFlowProjection,
        expected_ending: Decimal,
        period_days: int,
    ) -> LiquidityRiskLevel:
        """Bewerte Risiko-Level."""
        # Tage mit negativem Saldo
        days_negative = pessimistic.days_negative
        min_balance = pessimistic.min_balance

        if min_balance < Decimal("-10000") or days_negative > period_days * 0.5:
            return LiquidityRiskLevel.CRITICAL
        elif min_balance < Decimal("-5000") or days_negative > period_days * 0.3:
            return LiquidityRiskLevel.WARNING
        elif min_balance < Decimal("0") or days_negative > period_days * 0.1:
            return LiquidityRiskLevel.CAUTION
        elif expected_ending < Decimal("5000"):
            return LiquidityRiskLevel.ADEQUATE
        else:
            return LiquidityRiskLevel.HEALTHY

    def _calculate_shortfall_probability(
        self,
        realistic: CashFlowProjection,
        pessimistic: CashFlowProjection,
    ) -> float:
        """Berechne Wahrscheinlichkeit eines Engpasses."""
        # Vereinfachte Berechnung basierend auf Szenarien
        realistic_negative_days = sum(
            1 for b in realistic.daily_balances.values() if b < 0
        )
        pessimistic_negative_days = pessimistic.days_negative
        total_days = len(realistic.daily_balances)

        if total_days == 0:
            return 0.0

        # Gewichteter Durchschnitt
        prob = (realistic_negative_days * 0.3 + pessimistic_negative_days * 0.7) / total_days
        return min(1.0, max(0.0, prob))

    def _extract_major_flows(
        self,
        entries: List[CashFlowEntry],
        direction: CashFlowDirection,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Extrahiere die größten Zahlungsstroeme."""
        filtered = [e for e in entries if e.direction == direction]
        sorted_entries = sorted(filtered, key=lambda e: e.amount, reverse=True)

        result = []
        for entry in sorted_entries[:limit]:
            metadata = entry.metadata or {}
            result.append({
                "date": entry.date.isoformat(),
                "amount": float(entry.amount),
                "source": entry.source,
                "reference": entry.reference,
                "probability": entry.probability,
                "entity": metadata.get("creditor") or metadata.get("supplier") or metadata.get("beneficiary"),
            })

        return result

    def _assess_data_quality(self, entries: List[CashFlowEntry]) -> float:
        """Bewerte Datenqualität der Prognose."""
        if not entries:
            return 0.0

        # Faktoren:
        # 1. Anzahl Einträge
        count_score = min(1.0, len(entries) / 50)

        # 2. Durchschnittliche Wahrscheinlichkeit
        avg_prob = statistics.mean(e.probability for e in entries) if entries else 0

        # 3. Anteil mit Referenzen
        ref_count = sum(1 for e in entries if e.reference)
        ref_score = ref_count / len(entries) if entries else 0

        # Gewichteter Score
        return count_score * 0.3 + avg_prob * 0.5 + ref_score * 0.2

    def _get_bottleneck_recommendations(
        self,
        shortfall: Decimal,
        bottleneck_date: date,
        outflows: List[CashFlowEntry],
    ) -> List[str]:
        """Generiere Empfehlungen für Engpass."""
        recommendations = []

        if shortfall < Decimal("-10000"):
            recommendations.append("Kritischer Engpass: Sofortige Massnahmen erforderlich")
            recommendations.append("Prüfen Sie Möglichkeiten zur Kontokorrent-Nutzung")

        if shortfall < Decimal("-5000"):
            recommendations.append("Kontaktieren Sie Ihre Bank für kurzfristige Finanzierung")

        # Spezifische Empfehlungen basierend auf Ausgaben
        total_outflow = sum(e.amount for e in outflows)
        if total_outflow > Decimal("5000"):
            recommendations.append("Prüfen Sie, ob Zahlungen verschoben werden können")

        days_until = (bottleneck_date - date.today()).days
        if days_until > 14:
            recommendations.append(
                f"Sie haben noch {days_until} Tage Zeit - prüfen Sie Skonto-Möglichkeiten bei offenen Forderungen"
            )

        return recommendations

    def _consolidate_bottlenecks(
        self,
        bottlenecks: List[LiquidityBottleneck],
    ) -> List[LiquidityBottleneck]:
        """Konsolidiere aufeinanderfolgende Engpaesse."""
        if not bottlenecks:
            return []

        consolidated: List[LiquidityBottleneck] = []
        current_period: List[LiquidityBottleneck] = [bottlenecks[0]]

        for i in range(1, len(bottlenecks)):
            prev = bottlenecks[i-1]
            curr = bottlenecks[i]

            # Wenn aufeinanderfolgend (max 3 Tage Lücke)
            if (curr.date - prev.date).days <= 3:
                current_period.append(curr)
            else:
                # Periode abschließen
                if current_period:
                    # Schlimmsten Engpass der Periode nehmen
                    worst = min(current_period, key=lambda b: b.shortfall)
                    worst.contributing_factors.insert(
                        0, f"Engpass-Periode: {current_period[0].date} - {current_period[-1].date}"
                    )
                    consolidated.append(worst)
                current_period = [curr]

        # Letzte Periode
        if current_period:
            worst = min(current_period, key=lambda b: b.shortfall)
            if len(current_period) > 1:
                worst.contributing_factors.insert(
                    0, f"Engpass-Periode: {current_period[0].date} - {current_period[-1].date}"
                )
            consolidated.append(worst)

        return consolidated

    def _generate_recommendations(
        self,
        forecast_30: RollingForecast,
        forecast_60: RollingForecast,
        forecast_90: RollingForecast,
        anomalies: List[PaymentAnomaly],
    ) -> List[str]:
        """Generiere Handlungsempfehlungen."""
        recommendations = []

        # Risiko-basierte Empfehlungen
        if forecast_30.risk_level == LiquidityRiskLevel.CRITICAL:
            recommendations.append(
                "DRINGEND: Kritische Liquiditaetssituation in den nächsten 30 Tagen erwartet. "
                "Sofortige Massnahmen zur Liquiditaetssicherung erforderlich."
            )
        elif forecast_30.risk_level == LiquidityRiskLevel.WARNING:
            recommendations.append(
                "WARNUNG: Erhöhtes Liquiditaetsrisiko. Zahlungen priorisieren und "
                "offene Forderungen zeitnah einziehen."
            )

        # Skonto-Empfehlung
        if forecast_30.expected_inflow > Decimal("10000"):
            recommendations.append(
                "Prüfen Sie Skonto-Möglichkeiten bei Ihren Lieferanten - "
                "Sie haben genuegend erwartete Eingaenge."
            )

        # Anomalie-Empfehlungen
        high_confidence_anomalies = [a for a in anomalies if a.confidence > 0.7]
        if high_confidence_anomalies:
            recommendations.append(
                f"{len(high_confidence_anomalies)} Zahlungsanomalien erkannt. "
                "Bitte prüfen Sie diese Transaktionen."
            )

        # Diversifikations-Empfehlung
        if forecast_90.major_inflows:
            top_inflow = forecast_90.major_inflows[0]
            if top_inflow.get("amount", 0) > float(forecast_90.expected_inflow) * 0.5:
                recommendations.append(
                    "Hohe Abhängigkeit von einzelnen Einnahmen erkannt. "
                    "Diversifikation der Einnahmequellen empfohlen."
                )

        return recommendations

    def _generate_alerts(
        self,
        forecast_30: RollingForecast,
        forecast_60: RollingForecast,
        forecast_90: RollingForecast,
        anomalies: List[PaymentAnomaly],
    ) -> List[Dict[str, Any]]:
        """Generiere Alerts."""
        alerts = []

        # Risiko-Alerts
        for forecast, label in [
            (forecast_30, "30 Tage"),
            (forecast_60, "60 Tage"),
            (forecast_90, "90 Tage"),
        ]:
            if forecast.risk_level in [LiquidityRiskLevel.CRITICAL, LiquidityRiskLevel.WARNING]:
                alerts.append({
                    "type": "liquidity_risk",
                    "level": "critical" if forecast.risk_level == LiquidityRiskLevel.CRITICAL else "warning",
                    "message": f"Liquiditaetsrisiko in den nächsten {label}: {forecast.risk_level.value}",
                    "period": label,
                    "expected_balance": float(forecast.expected_ending_balance),
                    "probability_shortfall": forecast.probability_of_shortfall,
                })

        # Bottleneck-Alerts
        all_bottlenecks = (
            forecast_30.bottlenecks + forecast_60.bottlenecks + forecast_90.bottlenecks
        )
        for bottleneck in all_bottlenecks[:3]:
            alerts.append({
                "type": "bottleneck",
                "level": "critical" if bottleneck.severity == LiquidityRiskLevel.CRITICAL else "warning",
                "message": f"Liquiditaetsengpass am {bottleneck.date.isoformat()}",
                "date": bottleneck.date.isoformat(),
                "shortfall": float(bottleneck.shortfall),
            })

        # Anomalie-Alerts
        critical_anomalies = [a for a in anomalies if a.confidence > 0.8]
        for anomaly in critical_anomalies[:3]:
            alerts.append({
                "type": "anomaly",
                "level": "warning",
                "message": anomaly.description,
                "anomaly_type": anomaly.anomaly_type.value,
                "date": anomaly.date.isoformat(),
                "amount": float(anomaly.amount),
            })

        return alerts


# Singleton
_liquidity_forecast_service: Optional[LiquidityForecastService] = None


def get_liquidity_forecast_service() -> LiquidityForecastService:
    """Hole LiquidityForecastService Singleton."""
    global _liquidity_forecast_service
    if _liquidity_forecast_service is None:
        _liquidity_forecast_service = LiquidityForecastService()
    return _liquidity_forecast_service
