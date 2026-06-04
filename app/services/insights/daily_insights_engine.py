# -*- coding: utf-8 -*-
"""
Daily Insights Engine - Proaktive Warnungen VOR Problemen.

Vision 2026 Q4: System das proaktiv warnt BEVOR Probleme entstehen.

Unterschied zum ProactiveInsightsService:
- ProactiveInsightsService: Kontext-sensitive Insights während Chat/UI-Interaktion
- DailyInsightsEngine: Batch-generierte Insights die täglich erstellt werden

Insight-Typen:
- cashflow_warning: "In 2 Wochen könnte Liquiditaet eng werden"
- contract_expiring: "Vertrag X laeuft in 30 Tagen aus"
- payment_risk: "Kunde Y hat 3 überfällige Rechnungen"
- skonto_deadline: "Skonto für Rechnung Z verfaellt morgen"
- unusual_pattern: "Ausgaben diesen Monat 40% höher als ueblich"
- compliance_reminder: "Aufbewahrungsfrist für Dokumente 2015 endet bald"
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Callable, TypedDict, Union
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram, Gauge

from app.core.safe_errors import safe_error_log
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

INSIGHTS_GENERATED = Counter(
    "daily_insights_generated_total",
    "Total daily insights generated",
    ["insight_type", "severity", "company_id"]
)

INSIGHTS_GENERATION_TIME = Histogram(
    "daily_insights_generation_seconds",
    "Time to generate daily insights",
    ["company_id"]
)

INSIGHTS_ACTIVE = Gauge(
    "daily_insights_active_count",
    "Number of active (unresolved) insights",
    ["company_id", "insight_type"]
)


# =============================================================================
# Enums
# =============================================================================

class DailyInsightType(str, Enum):
    """Typ des täglichen Insights."""
    CASHFLOW_WARNING = "cashflow_warning"
    CONTRACT_EXPIRING = "contract_expiring"
    PAYMENT_RISK = "payment_risk"
    SKONTO_DEADLINE = "skonto_deadline"
    UNUSUAL_PATTERN = "unusual_pattern"
    COMPLIANCE_REMINDER = "compliance_reminder"
    HIGH_RISK_ENTITY = "high_risk_entity"
    OVERDUE_INVOICE = "overdue_invoice"
    DUNNING_REQUIRED = "dunning_required"
    DOCUMENT_RETENTION = "document_retention"
    BANK_RECONCILIATION = "bank_reconciliation"
    MISSING_DOCUMENT = "missing_document"


class InsightSeverity(str, Enum):
    """Schweregrad des Insights."""
    CRITICAL = "critical"   # Sofortige Aktion erforderlich
    HIGH = "high"           # Aktion innerhalb 24h
    MEDIUM = "medium"       # Aktion innerhalb 7 Tage
    LOW = "low"             # Informativ


class InsightStatus(str, Enum):
    """Status des Insights."""
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


# =============================================================================
# TypedDicts for Type Safety
# =============================================================================


class InsightFactorDict(TypedDict, total=False):
    """Ein Faktor der zum Insight beitraegt."""
    name: str
    value: str
    contribution: float
    explanation: str


class HistoricalComparisonDict(TypedDict, total=False):
    """Historischer Vergleich für Insights."""
    previous_value: str
    current_value: str
    change_percent: float
    period: str
    trend: str


class DailyInsightDict(TypedDict):
    """Typisiertes Dictionary für DailyInsight.to_dict()."""
    id: str
    insight_type: str
    severity: str
    status: str
    title: str
    summary: str
    detail: str
    recommendation: str
    company_id: Optional[str]
    related_entity_id: Optional[str]
    related_entity_name: Optional[str]
    related_document_id: Optional[str]
    related_invoice_id: Optional[str]
    predicted_date: Optional[str]
    predicted_amount: Optional[float]
    confidence: float
    available_actions: List[str]
    primary_action_url: Optional[str]
    primary_action_label: Optional[str]
    factors: List[InsightFactorDict]
    historical_comparison: Optional[HistoricalComparisonDict]
    expires_at: Optional[str]
    created_at: str


class CashflowDataDict(TypedDict, total=False):
    """Cashflow-Daten für Insight-Generierung."""
    current_balance: float
    projected_balance: float
    incoming_payments: List[Dict[str, Union[str, float]]]
    outgoing_payments: List[Dict[str, Union[str, float]]]


class ContractDataDict(TypedDict, total=False):
    """Vertragsdaten für Insight-Generierung."""
    contracts: List[Dict[str, Union[str, int, float]]]


class PaymentRiskDataDict(TypedDict, total=False):
    """Zahlungsrisiko-Daten für Insight-Generierung."""
    entities: List[Dict[str, Union[str, int, float]]]
    overdue_invoices: List[Dict[str, Union[str, float]]]


class SkontoDataDict(TypedDict, total=False):
    """Skonto-Daten für Insight-Generierung."""
    invoices: List[Dict[str, Union[str, float]]]


class PatternDataDict(TypedDict, total=False):
    """Muster-Daten für Insight-Generierung."""
    patterns: List[Dict[str, Union[str, float]]]
    baselines: Dict[str, float]


class ComplianceDataDict(TypedDict, total=False):
    """Compliance-Daten für Insight-Generierung."""
    deadlines: List[Dict[str, Union[str, int]]]
    documents: List[Dict[str, Union[str, int]]]


class RiskDataDict(TypedDict, total=False):
    """Risiko-Daten für Insight-Generierung."""
    entities: List[Dict[str, Union[str, int, float]]]


class DunningDataDict(TypedDict, total=False):
    """Mahnungs-Daten für Insight-Generierung."""
    invoices: List[Dict[str, Union[str, float, int]]]


# Union type für alle Insight-Daten (für Generator-Signaturen)
InsightDataDict = Union[
    CashflowDataDict,
    ContractDataDict,
    PaymentRiskDataDict,
    SkontoDataDict,
    PatternDataDict,
    ComplianceDataDict,
    RiskDataDict,
    DunningDataDict,
    Dict[str, List[Dict[str, Union[str, int, float]]]],
]


class DataProvidersResult(TypedDict, total=False):
    """
    Typisiertes Dictionary für alle Data Provider Ergebnisse.

    Alle Keys sind optional (total=False), da nicht alle Provider
    bei jedem Aufruf verwendet werden.
    """
    # Cashflow
    cashflow_predictions: List[Dict[str, Union[str, float, int]]]

    # Contracts
    contracts: List[Dict[str, Union[str, float, int]]]

    # Payment Risk
    entities: List[Dict[str, Union[str, float, int]]]

    # Skonto
    invoices: List[Dict[str, Union[str, float, int]]]

    # Patterns
    patterns: List[Dict[str, Union[str, float, int]]]
    monthly_expenses: List[Dict[str, Union[str, float, int]]]

    # Compliance
    retention_items: List[Dict[str, Union[str, float, int]]]
    gdpr_requests: List[Dict[str, Union[str, float, int]]]

    # Risk
    risk_entities: List[Dict[str, Union[str, float, int]]]

    # Dunning
    dunning_invoices: List[Dict[str, Union[str, int, float, bool]]]

    # Bank reconciliation
    unreconciled_transactions: List[Dict[str, Union[str, int, float]]]

    # Document gaps
    document_gaps: List[Dict[str, Union[str, int, float, List[str]]]]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DailyInsight:
    """Ein täglicher proaktiver Insight."""
    id: UUID = field(default_factory=uuid4)
    insight_type: DailyInsightType = DailyInsightType.CASHFLOW_WARNING
    severity: InsightSeverity = InsightSeverity.MEDIUM
    status: InsightStatus = InsightStatus.NEW

    # Content
    title: str = ""
    summary: str = ""
    detail: str = ""
    recommendation: str = ""

    # Context
    company_id: Optional[UUID] = None
    related_entity_id: Optional[UUID] = None
    related_entity_name: Optional[str] = None
    related_document_id: Optional[UUID] = None
    related_invoice_id: Optional[UUID] = None

    # Prediction
    predicted_date: Optional[datetime] = None
    predicted_amount: Optional[Decimal] = None
    confidence: float = 0.85

    # Actions
    available_actions: List[str] = field(default_factory=list)
    primary_action_url: Optional[str] = None
    primary_action_label: Optional[str] = None

    # Metadata
    factors: List[InsightFactorDict] = field(default_factory=list)
    historical_comparison: Optional[HistoricalComparisonDict] = None
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> DailyInsightDict:
        """Konvertiert zu Dictionary."""
        return DailyInsightDict(
            id=str(self.id),
            insight_type=self.insight_type.value,
            severity=self.severity.value,
            status=self.status.value,
            title=self.title,
            summary=self.summary,
            detail=self.detail,
            recommendation=self.recommendation,
            company_id=str(self.company_id) if self.company_id else None,
            related_entity_id=str(self.related_entity_id) if self.related_entity_id else None,
            related_entity_name=self.related_entity_name,
            related_document_id=str(self.related_document_id) if self.related_document_id else None,
            related_invoice_id=str(self.related_invoice_id) if self.related_invoice_id else None,
            predicted_date=self.predicted_date.isoformat() if self.predicted_date else None,
            predicted_amount=float(self.predicted_amount) if self.predicted_amount else None,
            confidence=self.confidence,
            available_actions=self.available_actions,
            primary_action_url=self.primary_action_url,
            primary_action_label=self.primary_action_label,
            factors=self.factors,
            historical_comparison=self.historical_comparison,
            expires_at=self.expires_at.isoformat() if self.expires_at else None,
            created_at=self.created_at.isoformat(),
        )


@dataclass
class InsightGenerationResult:
    """Ergebnis der Insight-Generierung."""
    company_id: UUID
    generated_at: datetime
    total_insights: int
    insights_by_type: Dict[str, int]
    insights_by_severity: Dict[str, int]
    insights: List[DailyInsight]
    generation_time_seconds: float


@dataclass
class InsightGeneratorConfig:
    """Konfiguration für Insight-Generatoren."""
    # Cashflow
    cashflow_warning_days: int = 14  # Warnung X Tage im Voraus
    cashflow_critical_threshold: Decimal = Decimal("0")  # Unter 0 = kritisch
    cashflow_warning_threshold: Decimal = Decimal("5000")  # Unter X = Warnung

    # Contracts
    contract_warning_days: int = 30  # Warnung X Tage vor Ablauf
    contract_critical_days: int = 7

    # Skonto
    skonto_warning_days: int = 3
    skonto_critical_days: int = 1

    # Risk
    risk_score_high_threshold: int = 75
    risk_score_critical_threshold: int = 90

    # Patterns
    unusual_pattern_threshold: float = 0.3  # 30% Abweichung

    # Compliance
    retention_warning_months: int = 3  # 3 Monate vor Ablauf warnen

    # Dunning thresholds
    dunning_critical_days_overdue: int = 60
    dunning_warning_days_overdue: int = 30
    dunning_reminder_days_overdue: int = 14

    # Bank reconciliation
    reconciliation_critical_days: int = 30
    reconciliation_warning_days: int = 7
    reconciliation_notice_days: int = 3

    # Document gaps
    document_gap_critical_count: int = 5
    document_gap_warning_count: int = 2


# =============================================================================
# Insight Generators
# =============================================================================

class BaseInsightGenerator:
    """Basis-Klasse für Insight-Generatoren."""

    insight_type: DailyInsightType

    def __init__(self, config: InsightGeneratorConfig):
        self.config = config

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        """Generiert Insights. Muss überschrieben werden."""
        raise NotImplementedError


class CashflowWarningGenerator(BaseInsightGenerator):
    """Generiert Cashflow-Warnungen."""

    insight_type = DailyInsightType.CASHFLOW_WARNING

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: cashflow_predictions: List[{date, predicted_balance, confidence}]
        predictions = data.get("cashflow_predictions", [])

        for prediction in predictions:
            pred_date = prediction.get("date")
            pred_balance = Decimal(str(prediction.get("predicted_balance", 0)))
            confidence = prediction.get("confidence", 0.85)

            if pred_balance <= self.config.cashflow_critical_threshold:
                severity = InsightSeverity.CRITICAL
                title = "Kritischer Liquiditaetsengpass erwartet"
                summary = f"Am {pred_date} wird ein negativer Kontostand von {pred_balance:,.2f} EUR erwartet."
            elif pred_balance <= self.config.cashflow_warning_threshold:
                severity = InsightSeverity.HIGH
                title = "Liquiditaetswarnung"
                summary = f"Am {pred_date} sinkt die Liquiditaet auf {pred_balance:,.2f} EUR."
            else:
                continue  # Kein Insight noetig

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=title,
                summary=summary,
                detail=f"Basierend auf erwarteten Ein- und Ausgaengen.",
                recommendation="Zahlungseingaenge beschleunigen oder Zahlungen verschieben.",
                predicted_date=datetime.fromisoformat(pred_date) if isinstance(pred_date, str) else pred_date,
                predicted_amount=pred_balance,
                confidence=confidence,
                available_actions=["show_details", "optimize_payments", "delay_outgoing"],
                primary_action_url="/cashflow/optimize",
                primary_action_label="Zahlungen optimieren",
                factors=prediction.get("factors", []),
            ))

        return insights


class ContractExpiringGenerator(BaseInsightGenerator):
    """Generiert Vertrags-Ablauf-Warnungen."""

    insight_type = DailyInsightType.CONTRACT_EXPIRING

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: expiring_contracts: List[{id, title, end_date, notice_date, monthly_cost}]
        contracts = data.get("expiring_contracts", [])
        now = datetime.now(timezone.utc)

        for contract in contracts:
            notice_date = contract.get("notice_date")
            if isinstance(notice_date, str):
                notice_date = datetime.fromisoformat(notice_date.replace("Z", "+00:00"))

            if not notice_date:
                continue

            days_remaining = (notice_date - now).days

            if days_remaining < 0:
                continue  # Bereits abgelaufen

            if days_remaining <= self.config.contract_critical_days:
                severity = InsightSeverity.CRITICAL
            elif days_remaining <= self.config.contract_warning_days:
                severity = InsightSeverity.HIGH
            else:
                continue

            monthly_cost = Decimal(str(contract.get("monthly_cost", 0)))

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=f"Kündigungsfrist: {contract.get('title', 'Vertrag')}",
                summary=f"Kündigungsfrist endet in {days_remaining} Tagen ({notice_date.strftime('%d.%m.%Y')}).",
                detail=f"Monatliche Kosten: {monthly_cost:,.2f} EUR. Vertrag verlängert sich automatisch.",
                recommendation="Vertrag prüfen und ggf. kündigen oder neu verhandeln.",
                related_document_id=UUID(contract["id"]) if contract.get("id") else None,
                predicted_date=notice_date,
                predicted_amount=monthly_cost * 12,  # Jährliche Kosten
                confidence=1.0,  # Sicher, da vertraglich festgelegt
                available_actions=["view_contract", "cancel", "renew", "negotiate"],
                primary_action_url=f"/contracts/{contract.get('id')}",
                primary_action_label="Vertrag prüfen",
            ))

        return insights


class SkontoDeadlineGenerator(BaseInsightGenerator):
    """Generiert Skonto-Frist-Warnungen."""

    insight_type = DailyInsightType.SKONTO_DEADLINE

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: upcoming_skonto: List[{invoice_id, skonto_deadline, skonto_amount, supplier_name}]
        skonto_items = data.get("upcoming_skonto", [])
        now = datetime.now(timezone.utc)

        for item in skonto_items:
            deadline = item.get("skonto_deadline")
            if isinstance(deadline, str):
                deadline = datetime.fromisoformat(deadline.replace("Z", "+00:00"))

            if not deadline:
                continue

            days_remaining = (deadline - now).days

            if days_remaining < 0:
                continue  # Bereits abgelaufen

            if days_remaining <= self.config.skonto_critical_days:
                severity = InsightSeverity.CRITICAL
            elif days_remaining <= self.config.skonto_warning_days:
                severity = InsightSeverity.HIGH
            else:
                continue

            skonto_amount = Decimal(str(item.get("skonto_amount", 0)))

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=f"Skonto-Frist: {item.get('supplier_name', 'Lieferant')}",
                summary=f"Skonto von {skonto_amount:,.2f} EUR verfaellt in {days_remaining} Tag(en).",
                detail=f"Rechnungsnummer: {item.get('invoice_number', 'N/A')}, Zahlung bis {deadline.strftime('%d.%m.%Y')}.",
                recommendation="Rechnung zeitnah bezahlen um Skonto zu sichern.",
                related_invoice_id=UUID(item["invoice_id"]) if item.get("invoice_id") else None,
                related_entity_name=item.get("supplier_name"),
                predicted_date=deadline,
                predicted_amount=skonto_amount,
                confidence=1.0,
                expires_at=deadline,
                available_actions=["pay_now", "schedule_payment", "view_invoice"],
                primary_action_url=f"/invoices/{item.get('invoice_id')}/pay",
                primary_action_label="Jetzt bezahlen",
            ))

        return insights


class PaymentRiskGenerator(BaseInsightGenerator):
    """Generiert Zahlungsrisiko-Warnungen."""

    insight_type = DailyInsightType.PAYMENT_RISK

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: high_risk_entities: List[{entity_id, name, risk_score, overdue_count, overdue_amount}]
        entities = data.get("high_risk_entities", [])

        for entity in entities:
            risk_score = entity.get("risk_score", 0)

            if risk_score >= self.config.risk_score_critical_threshold:
                severity = InsightSeverity.CRITICAL
            elif risk_score >= self.config.risk_score_high_threshold:
                severity = InsightSeverity.HIGH
            else:
                continue

            overdue_amount = Decimal(str(entity.get("overdue_amount", 0)))

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=f"Hohes Zahlungsrisiko: {entity.get('name', 'Kunde')}",
                summary=f"Risiko-Score: {risk_score}/100, {entity.get('overdue_count', 0)} überfällige Rechnungen.",
                detail=f"Ausstehender Betrag: {overdue_amount:,.2f} EUR.",
                recommendation="Zahlungsbedingungen überprüfen, ggf. Mahnung oder Inkasso einleiten.",
                related_entity_id=UUID(entity["entity_id"]) if entity.get("entity_id") else None,
                related_entity_name=entity.get("name"),
                predicted_amount=overdue_amount,
                confidence=risk_score / 100,
                available_actions=["view_entity", "send_reminder", "start_dunning", "block_entity"],
                primary_action_url=f"/entities/{entity.get('entity_id')}/risk",
                primary_action_label="Risiko analysieren",
                factors=[
                    {"name": "Risiko-Score", "value": f"{risk_score}/100"},
                    {"name": "Überfällige Rechnungen", "value": str(entity.get("overdue_count", 0))},
                    {"name": "Ausstehend", "value": f"{overdue_amount:,.2f} EUR"},
                ],
            ))

        return insights


class UnusualPatternGenerator(BaseInsightGenerator):
    """Generiert Warnungen bei ungewoehnlichen Mustern."""

    insight_type = DailyInsightType.UNUSUAL_PATTERN

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: spending_patterns: List[{category, current_amount, avg_amount, deviation_percent}]
        patterns = data.get("spending_patterns", [])

        for pattern in patterns:
            deviation = pattern.get("deviation_percent", 0)

            if abs(deviation) < self.config.unusual_pattern_threshold * 100:
                continue

            current = Decimal(str(pattern.get("current_amount", 0)))
            avg = Decimal(str(pattern.get("avg_amount", 0)))

            if deviation > 0:
                direction = "höher"
                severity = InsightSeverity.HIGH if deviation > 50 else InsightSeverity.MEDIUM
            else:
                direction = "niedriger"
                severity = InsightSeverity.LOW  # Niedriger ist meist gut

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=f"Ungewoehnliches Muster: {pattern.get('category', 'Ausgaben')}",
                summary=f"Ausgaben {abs(deviation):.0f}% {direction} als ueblich ({current:,.2f} EUR vs. {avg:,.2f} EUR Durchschnitt).",
                detail=f"Kategorie: {pattern.get('category')}, Zeitraum: {pattern.get('period', 'dieser Monat')}.",
                recommendation="Überprüfen ob die Abweichung beabsichtigt ist.",
                predicted_amount=current - avg,
                confidence=0.75,
                available_actions=["view_details", "set_alert", "mark_expected"],
                primary_action_url=f"/analytics/spending?category={pattern.get('category')}",
                primary_action_label="Details anzeigen",
                historical_comparison={
                    "current": float(current),
                    "average": float(avg),
                    "deviation_percent": deviation,
                    "period": pattern.get("period", "dieser Monat"),
                },
            ))

        return insights


class ComplianceReminderGenerator(BaseInsightGenerator):
    """Generiert Compliance-Erinnerungen."""

    insight_type = DailyInsightType.COMPLIANCE_REMINDER

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: retention_items: List[{year, document_count, retention_end_date}]
        retention_items = data.get("retention_items", [])
        now = datetime.now(timezone.utc)

        for item in retention_items:
            end_date = item.get("retention_end_date")
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

            if not end_date:
                continue

            months_remaining = (end_date.year - now.year) * 12 + (end_date.month - now.month)

            if months_remaining < 0:
                # Bereits abgelaufen - Dokumente können gelöscht werden
                severity = InsightSeverity.LOW
                title = f"Aufbewahrungsfrist abgelaufen: Dokumente {item.get('year')}"
                summary = f"{item.get('document_count', 0)} Dokumente können gelöscht werden."
                recommendation = "Dokumente archivieren oder sicher löschen."
            elif months_remaining <= self.config.retention_warning_months:
                severity = InsightSeverity.MEDIUM
                title = f"Aufbewahrungsfrist endet bald: Dokumente {item.get('year')}"
                summary = f"Aufbewahrungsfrist für {item.get('document_count', 0)} Dokumente endet in {months_remaining} Monaten."
                recommendation = "Archivierung vorbereiten."
            else:
                continue

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=title,
                summary=summary,
                detail=f"Jahr: {item.get('year')}, Dokumente: {item.get('document_count')}, Ende: {end_date.strftime('%d.%m.%Y')}.",
                recommendation=recommendation,
                predicted_date=end_date,
                confidence=1.0,
                available_actions=["view_documents", "archive", "extend_retention"],
                primary_action_url=f"/documents?year={item.get('year')}&retention=expiring",
                primary_action_label="Dokumente anzeigen",
            ))

        return insights


class OverdueInvoiceGenerator(BaseInsightGenerator):
    """Generiert Warnungen für überfällige Rechnungen."""

    insight_type = DailyInsightType.OVERDUE_INVOICE

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: overdue_invoices: List[{invoice_id, invoice_number, customer_name, amount, days_overdue, dunning_level}]
        invoices = data.get("overdue_invoices", [])

        for invoice in invoices:
            days_overdue = invoice.get("days_overdue", 0)

            if days_overdue > 30:
                severity = InsightSeverity.CRITICAL
            elif days_overdue > 14:
                severity = InsightSeverity.HIGH
            elif days_overdue > 0:
                severity = InsightSeverity.MEDIUM
            else:
                continue

            amount = Decimal(str(invoice.get("amount", 0)))

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=f"Überfällige Rechnung: {invoice.get('invoice_number')}",
                summary=f"{days_overdue} Tage überfällig, Kunde: {invoice.get('customer_name')}.",
                detail=f"Betrag: {amount:,.2f} EUR, Mahnstufe: {invoice.get('dunning_level', 0)}.",
                recommendation="Zahlungserinnerung senden oder Mahnstufe erhöhen.",
                related_invoice_id=UUID(invoice["invoice_id"]) if invoice.get("invoice_id") else None,
                related_entity_name=invoice.get("customer_name"),
                predicted_amount=amount,
                confidence=1.0,
                available_actions=["send_reminder", "increase_dunning", "mark_paid", "view_invoice"],
                primary_action_url=f"/invoices/{invoice.get('invoice_id')}",
                primary_action_label="Rechnung öffnen",
                factors=[
                    {"name": "Tage überfällig", "value": str(days_overdue)},
                    {"name": "Mahnstufe", "value": str(invoice.get("dunning_level", 0))},
                ],
            ))

        return insights


class DunningRequiredGenerator(BaseInsightGenerator):
    """Generiert Mahnungs-Empfehlungen für überfällige Rechnungen."""

    insight_type = DailyInsightType.DUNNING_REQUIRED

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: dunning_invoices: List[{dunning_record_id, invoice_number, days_overdue, outstanding_amount, dunning_level, customer_name, entity_id, is_b2b, mahnstopp}]
        dunning_invoices = data.get("dunning_invoices", [])

        for invoice in dunning_invoices:
            # Skip wenn Mahnstopp gesetzt ist
            if invoice.get("mahnstopp", False):
                continue

            days_overdue = invoice.get("days_overdue", 0)
            dunning_level = invoice.get("dunning_level", 0)
            outstanding_amount = Decimal(str(invoice.get("outstanding_amount", 0)))
            is_b2b = invoice.get("is_b2b", False)

            # Severity Logic
            if days_overdue > self.config.dunning_critical_days_overdue and dunning_level < 3:
                severity = InsightSeverity.CRITICAL
                title = "Sofortige Mahnung erforderlich"
            elif days_overdue > self.config.dunning_warning_days_overdue and dunning_level < 2:
                severity = InsightSeverity.HIGH
                title = "Mahnstufe erhöhen"
            elif days_overdue > self.config.dunning_reminder_days_overdue and dunning_level == 0:
                severity = InsightSeverity.MEDIUM
                title = "Erste Zahlungserinnerung senden"
            else:
                continue

            # Recommendation basierend auf Mahnstufe
            if dunning_level == 0:
                recommendation = "Zahlungserinnerung senden"
            elif dunning_level == 1:
                recommendation = "Zweite Mahnung mit Mahngebühr senden"
            elif dunning_level == 2:
                recommendation = "Letzte Mahnung mit Inkasso-Androhung senden"
            else:
                recommendation = "Inkasso-Verfahren einleiten"

            # Faktoren sammeln
            factors: List[InsightFactorDict] = [
                {"name": "Tage überfällig", "value": str(days_overdue)},
                {"name": "Aktuelle Mahnstufe", "value": str(dunning_level)},
                {"name": "Ausstehender Betrag", "value": f"{outstanding_amount:,.2f} EUR"},
            ]

            # B2B Pauschale nach BGB 288
            if is_b2b:
                factors.append({"name": "B2B Pauschale", "value": "40 EUR nach BGB 288"})

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=f"{title}: {invoice.get('customer_name', 'Kunde')}",
                summary=f"Rechnung {invoice.get('invoice_number')} seit {days_overdue} Tagen überfällig (Mahnstufe {dunning_level}).",
                detail=f"Ausstehend: {outstanding_amount:,.2f} EUR, Kunde: {invoice.get('customer_name')}.",
                recommendation=recommendation,
                related_invoice_id=UUID(invoice["dunning_record_id"]) if invoice.get("dunning_record_id") else None,
                related_entity_id=UUID(invoice["entity_id"]) if invoice.get("entity_id") else None,
                related_entity_name=invoice.get("customer_name"),
                predicted_amount=outstanding_amount,
                confidence=1.0,
                available_actions=["send_reminder", "increase_dunning", "view_invoice", "set_mahnstopp"],
                primary_action_url=f"/invoices/{invoice.get('dunning_record_id')}/dunning",
                primary_action_label="Mahnung verwalten",
                factors=factors,
            ))

        return insights


class BankReconciliationGenerator(BaseInsightGenerator):
    """Generiert Warnungen für nicht-zugeordnete Banktransaktionen."""

    insight_type = DailyInsightType.BANK_RECONCILIATION

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: unreconciled_transactions: List[{transaction_id, amount, booking_date, counterparty_name, reference_text, days_pending, match_confidence}]
        transactions = data.get("unreconciled_transactions", [])

        for transaction in transactions:
            days_pending = transaction.get("days_pending", 0)

            # Severity Logic
            if days_pending > self.config.reconciliation_critical_days:
                severity = InsightSeverity.CRITICAL
                title = "Kontobewegung seit über 30 Tagen offen"
            elif days_pending > self.config.reconciliation_warning_days:
                severity = InsightSeverity.HIGH
                title = "Nicht-zugeordnete Kontobewegung"
            elif days_pending > self.config.reconciliation_notice_days:
                severity = InsightSeverity.MEDIUM
                title = "Neue Kontobewegung zuordnen"
            else:
                continue

            amount = Decimal(str(transaction.get("amount", 0)))
            match_confidence = transaction.get("match_confidence", 0.0)

            # Recommendation basierend auf match_confidence
            if match_confidence > 0.8:
                recommendation = "Auto-Matching prüfen"
            else:
                recommendation = "Kontobewegung einem Beleg zuordnen"

            # Faktoren sammeln
            factors: List[InsightFactorDict] = [
                {"name": "Tage offen", "value": str(days_pending)},
                {"name": "Betrag", "value": f"{amount:,.2f} EUR"},
                {"name": "Gegenseite", "value": transaction.get("counterparty_name", "Unbekannt")},
            ]

            # Mögliche Zuordnung gefunden
            if match_confidence > 0.8:
                factors.append({
                    "name": "Mögliche Zuordnung",
                    "value": f"Konfidenz: {match_confidence * 100:.0f}%"
                })

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=title,
                summary=f"Kontobewegung von {transaction.get('counterparty_name', 'Unbekannt')} über {amount:,.2f} EUR seit {days_pending} Tagen offen.",
                detail=f"Buchungsdatum: {transaction.get('booking_date')}, Verwendungszweck: {transaction.get('reference_text', 'N/A')}.",
                recommendation=recommendation,
                predicted_amount=amount,
                confidence=1.0,
                available_actions=["auto_match", "manual_match", "mark_private", "view_transaction"],
                primary_action_url=f"/banking/reconciliation/{transaction.get('transaction_id')}",
                primary_action_label="Zuordnung bearbeiten",
                factors=factors,
            ))

        return insights


class MissingDocumentGenerator(BaseInsightGenerator):
    """Generiert Warnungen für fehlende Belege und Belegnummern-Lücken."""

    insight_type = DailyInsightType.MISSING_DOCUMENT

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        insights = []

        # Data: document_gaps: List[{document_type, missing_numbers, gaps_count, period, total_documents, unmatched_transaction_count}]
        document_gaps_list = data.get("document_gaps", [])

        for gap_data in document_gaps_list:
            gaps_count = gap_data.get("gaps_count", 0)
            unmatched_count = gap_data.get("unmatched_transaction_count", 0)
            document_type = gap_data.get("document_type", "Beleg")

            # Severity Logic
            if gaps_count >= self.config.document_gap_critical_count:
                severity = InsightSeverity.CRITICAL
                title = "Erhebliche Belegnummern-Lücken festgestellt"
            elif gaps_count >= self.config.document_gap_warning_count:
                severity = InsightSeverity.HIGH
                title = "Belegnummern-Lücken gefunden"
            elif unmatched_count > 10:
                severity = InsightSeverity.HIGH
                title = "Viele Transaktionen ohne Beleg"
            elif unmatched_count > 0:
                severity = InsightSeverity.MEDIUM
                title = "Transaktionen ohne zugehoerigen Beleg"
            else:
                continue

            # Faktoren sammeln
            factors: List[InsightFactorDict] = [
                {"name": "Belegtyp", "value": document_type},
            ]

            if gaps_count > 0:
                factors.append({"name": "Anzahl Lücken", "value": str(gaps_count)})

                # Fehlende Nummern (max 5)
                missing_numbers = gap_data.get("missing_numbers", [])
                if isinstance(missing_numbers, list) and missing_numbers:
                    display_numbers = missing_numbers[:5]
                    more_text = f" (+{len(missing_numbers) - 5} weitere)" if len(missing_numbers) > 5 else ""
                    factors.append({
                        "name": "Fehlende Nummern",
                        "value": f"{', '.join(display_numbers)}{more_text}"
                    })

            if unmatched_count > 0:
                factors.append({"name": "Nicht zugeordnete Transaktionen", "value": str(unmatched_count)})

            insights.append(DailyInsight(
                insight_type=self.insight_type,
                severity=severity,
                company_id=company_id,
                title=f"{title}: {document_type}",
                summary=f"{gaps_count} Belegnummern-Lücken, {unmatched_count} Transaktionen ohne Beleg (Zeitraum: {gap_data.get('period', 'N/A')}).",
                detail=f"Gesamt {gap_data.get('total_documents', 0)} Belege im Zeitraum {gap_data.get('period', 'N/A')}.",
                recommendation="Fehlende Belege nachscannen oder manuell erfassen",
                confidence=1.0,
                available_actions=["view_gaps", "upload_document", "scan_folder", "ignore_gap"],
                primary_action_url=f"/documents/gaps/{document_type}",
                primary_action_label="Lücken anzeigen",
                factors=factors,
            ))

        return insights


# =============================================================================
# Daily Insights Engine
# =============================================================================

class DailyInsightsEngine:
    """
    Engine für tägliche proaktive Insights.

    Generiert Batch-Insights für alle Companies basierend auf:
    - Cashflow-Prognosen
    - Vertragsfristen
    - Skonto-Deadlines
    - Zahlungsrisiken
    - Ungewoehnliche Muster
    - Compliance-Fristen
    """

    def __init__(
        self,
        config: Optional[InsightGeneratorConfig] = None,
    ):
        self.config = config or InsightGeneratorConfig()
        self._generators: List[BaseInsightGenerator] = []
        self._register_default_generators()

        logger.info("daily_insights_engine_initialized")

    def _register_default_generators(self) -> None:
        """Registriert die Standard-Generatoren."""
        self._generators = [
            CashflowWarningGenerator(self.config),
            ContractExpiringGenerator(self.config),
            SkontoDeadlineGenerator(self.config),
            PaymentRiskGenerator(self.config),
            UnusualPatternGenerator(self.config),
            ComplianceReminderGenerator(self.config),
            OverdueInvoiceGenerator(self.config),
            DunningRequiredGenerator(self.config),
            BankReconciliationGenerator(self.config),
            MissingDocumentGenerator(self.config),
        ]

    def register_generator(self, generator: BaseInsightGenerator) -> None:
        """Registriert einen zusätzlichen Generator."""
        self._generators.append(generator)
        logger.info(
            "insight_generator_registered",
            generator_type=generator.insight_type.value,
        )

    async def generate_daily_insights(
        self,
        company_id: UUID,
        data_providers: Dict[str, Callable[[], List[Dict[str, Union[str, int, float]]]]],
    ) -> InsightGenerationResult:
        """
        Generiert alle täglichen Insights für eine Company.

        Args:
            company_id: Company-ID
            data_providers: Dict mit Datenprovidern pro Generator-Typ
                z.B. {"cashflow_predictions": async_func_to_get_predictions}

        Returns:
            InsightGenerationResult mit allen generierten Insights
        """
        import time

        start_time = time.time()

        logger.info(
            "generating_daily_insights",
            company_id=str(company_id),
        )

        all_insights: List[DailyInsight] = []
        insights_by_type: Dict[str, int] = {}
        insights_by_severity: Dict[str, int] = {}

        # Daten von allen Providern abrufen
        data: DataProvidersResult = {}
        for key, provider in data_providers.items():
            try:
                if asyncio.iscoroutinefunction(provider):
                    data[key] = await provider()
                else:
                    data[key] = provider()
            except Exception as e:
                logger.warning(
                    "data_provider_failed",
                    provider=key,
                    **safe_error_log(e),
                )
                data[key] = []

        # Alle Generatoren ausführen
        for generator in self._generators:
            try:
                insights = await generator.generate(company_id, data)
                all_insights.extend(insights)

                # Statistiken
                insight_type = generator.insight_type.value
                insights_by_type[insight_type] = insights_by_type.get(insight_type, 0) + len(insights)

                for insight in insights:
                    severity = insight.severity.value
                    insights_by_severity[severity] = insights_by_severity.get(severity, 0) + 1

                    # Prometheus Metrics
                    INSIGHTS_GENERATED.labels(
                        insight_type=insight_type,
                        severity=severity,
                        company_id=str(company_id),
                    ).inc()

            except Exception as e:
                logger.error(
                    "insight_generator_failed",
                    generator=generator.insight_type.value,
                    **safe_error_log(e),
                )

        # Sortieren nach Severity
        severity_order = {
            InsightSeverity.CRITICAL: 0,
            InsightSeverity.HIGH: 1,
            InsightSeverity.MEDIUM: 2,
            InsightSeverity.LOW: 3,
        }
        all_insights.sort(key=lambda i: severity_order.get(i.severity, 4))

        generation_time = time.time() - start_time

        # Metrics
        INSIGHTS_GENERATION_TIME.labels(company_id=str(company_id)).observe(generation_time)

        logger.info(
            "daily_insights_generated",
            company_id=str(company_id),
            total_insights=len(all_insights),
            generation_time_seconds=generation_time,
        )

        return InsightGenerationResult(
            company_id=company_id,
            generated_at=datetime.now(timezone.utc),
            total_insights=len(all_insights),
            insights_by_type=insights_by_type,
            insights_by_severity=insights_by_severity,
            insights=all_insights,
            generation_time_seconds=generation_time,
        )

    async def get_critical_insights(
        self,
        company_id: UUID,
        data_providers: Dict[str, Callable[[], List[Dict[str, Union[str, int, float]]]]],
        max_insights: int = 10,
    ) -> List[DailyInsight]:
        """
        Holt nur die kritischsten Insights (für Dashboard).

        Args:
            company_id: Company-ID
            data_providers: Datenprovider
            max_insights: Maximale Anzahl

        Returns:
            Liste der kritischsten Insights
        """
        result = await self.generate_daily_insights(company_id, data_providers)
        return result.insights[:max_insights]

    async def get_actionable_insights(
        self,
        company_id: UUID,
        data_providers: Dict[str, Callable[[], List[Dict[str, Union[str, int, float]]]]],
        insight_types: Optional[List[DailyInsightType]] = None,
    ) -> List[DailyInsight]:
        """
        Holt Insights mit verfügbaren Aktionen.

        Args:
            company_id: Company-ID
            data_providers: Datenprovider
            insight_types: Optional Filter nach Typen

        Returns:
            Liste von Insights mit Aktionen
        """
        result = await self.generate_daily_insights(company_id, data_providers)

        insights = [i for i in result.insights if i.available_actions]

        if insight_types:
            insights = [i for i in insights if i.insight_type in insight_types]

        return insights


# =============================================================================
# Database-Backed Data Providers
# =============================================================================


async def _build_data_providers_from_db(
    db: "AsyncSession",
    company_id: UUID,
) -> Dict[str, Callable[[], List[Dict[str, Union[str, int, float]]]]]:
    """
    Erstellt Data Provider Funktionen die echte Daten aus der DB liefern.

    Wird vom Celery Beat Task und von den API-Endpoints genutzt.

    Args:
        db: Async Database Session
        company_id: Company/Mandant UUID

    Returns:
        Dict mit async Funktionen pro Daten-Kategorie
    """
    from sqlalchemy import select, func, and_
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from datetime import timedelta

    now = datetime.now(timezone.utc)

    async def _get_cashflow_predictions() -> List[Dict[str, Union[str, int, float]]]:
        """Projiziert Cashflow basierend auf offenen Rechnungen."""
        try:
            from app.db.models import InvoiceTracking

            # Offene Eingangsrechnungen (ausstehende Zahlungen)
            result = await db.execute(
                select(
                    InvoiceTracking.due_date,
                    func.sum(InvoiceTracking.outstanding_amount).label("total_due"),
                ).where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["open", "partial", "overdue"]),
                        InvoiceTracking.due_date.isnot(None),
                        InvoiceTracking.due_date <= now + timedelta(days=30),
                    )
                ).group_by(InvoiceTracking.due_date)
                .order_by(InvoiceTracking.due_date)
            )
            rows = result.all()

            predictions: List[Dict[str, Union[str, int, float]]] = []
            running_balance: float = 0.0

            for row in rows:
                due_amount = float(row.total_due or 0)
                running_balance -= due_amount
                predictions.append({
                    "date": row.due_date.isoformat() if row.due_date else "",
                    "predicted_balance": running_balance,
                    "confidence": 0.8,
                })

            return predictions
        except Exception as e:
            logger.warning("cashflow_provider_error", **safe_error_log(e))
            return []

    async def _get_skonto_invoices() -> List[Dict[str, Union[str, int, float]]]:
        """Rechnungen mit ablaufenden Skonto-Fristen (nächste 7 Tage)."""
        try:
            from app.db.models import InvoiceTracking

            result = await db.execute(
                select(InvoiceTracking).where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.skonto_deadline.isnot(None),
                        InvoiceTracking.skonto_deadline >= now,
                        InvoiceTracking.skonto_deadline <= now + timedelta(days=7),
                        InvoiceTracking.skonto_used == False,
                        InvoiceTracking.status.in_(["open", "partial"]),
                    )
                ).order_by(InvoiceTracking.skonto_deadline)
            )
            invoices = result.scalars().all()

            return [
                {
                    "invoice_id": str(inv.id),
                    "invoice_number": inv.invoice_number or "",
                    "skonto_deadline": inv.skonto_deadline.isoformat() if inv.skonto_deadline else "",
                    "skonto_amount": float(inv.skonto_amount or 0),
                    "supplier_name": "",
                }
                for inv in invoices
            ]
        except Exception as e:
            logger.warning("skonto_provider_error", **safe_error_log(e))
            return []

    async def _get_high_risk_entities() -> List[Dict[str, Union[str, int, float]]]:
        """Entities mit hohem Zahlungsrisiko."""
        try:
            from app.db.models import BusinessEntity, InvoiceTracking, Document

            # Entities mit überfälligen Rechnungen
            # Join: InvoiceTracking -> Document -> BusinessEntity
            result = await db.execute(
                select(
                    BusinessEntity.id,
                    BusinessEntity.name,
                    func.count(InvoiceTracking.id).label("overdue_count"),
                    func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0).label("overdue_amount"),
                ).select_from(InvoiceTracking)
                .join(
                    Document,
                    InvoiceTracking.document_id == Document.id,
                ).join(
                    BusinessEntity,
                    Document.business_entity_id == BusinessEntity.id,
                ).where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["overdue", "dunning"]),
                        BusinessEntity.is_active == True,
                    )
                ).group_by(BusinessEntity.id, BusinessEntity.name)
                .having(func.count(InvoiceTracking.id) >= 2)
            )
            rows = result.all()

            return [
                {
                    "entity_id": str(row.id),
                    "name": row.name,
                    "risk_score": min(95, 50 + int(row.overdue_count) * 10),
                    "overdue_count": int(row.overdue_count),
                    "overdue_amount": float(row.overdue_amount),
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("risk_entity_provider_error", **safe_error_log(e))
            return []

    async def _get_dunning_invoices() -> List[Dict[str, Union[str, int, float, bool]]]:
        """Rechnungen die eine Mahnung benötigen."""
        try:
            from app.db.models import InvoiceTracking, BusinessEntity, Document

            # Join: InvoiceTracking -> Document -> BusinessEntity
            result = await db.execute(
                select(
                    InvoiceTracking,
                    BusinessEntity.name.label("customer_name"),
                    BusinessEntity.id.label("entity_id_ref"),
                ).select_from(InvoiceTracking)
                .join(
                    Document,
                    InvoiceTracking.document_id == Document.id,
                    isouter=True,
                ).join(
                    BusinessEntity,
                    Document.business_entity_id == BusinessEntity.id,
                    isouter=True,
                ).where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["overdue", "dunning"]),
                        InvoiceTracking.due_date.isnot(None),
                        InvoiceTracking.due_date < now,
                    )
                ).order_by(InvoiceTracking.due_date)
            )
            rows = result.all()

            invoices: List[Dict[str, Union[str, int, float, bool]]] = []
            for row in rows:
                inv = row[0]
                customer_name = row.customer_name or ""
                entity_id_ref = row.entity_id_ref
                days_overdue = (now - inv.due_date).days if inv.due_date else 0

                invoices.append({
                    "dunning_record_id": str(inv.id),
                    "invoice_number": inv.invoice_number or "",
                    "days_overdue": days_overdue,
                    "outstanding_amount": float(inv.outstanding_amount or inv.amount or 0),
                    "dunning_level": int(inv.dunning_level or 0),
                    "customer_name": customer_name,
                    "entity_id": str(entity_id_ref) if entity_id_ref else "",
                    "is_b2b": True,
                    "mahnstopp": False,
                })

            return invoices
        except Exception as e:
            logger.warning("dunning_provider_error", **safe_error_log(e))
            return []

    async def _get_overdue_invoices() -> List[Dict[str, Union[str, int, float]]]:
        """Überfällige Rechnungen für OverdueInvoiceGenerator."""
        try:
            from app.db.models import InvoiceTracking, BusinessEntity, Document

            # Join: InvoiceTracking -> Document -> BusinessEntity
            result = await db.execute(
                select(
                    InvoiceTracking,
                    BusinessEntity.name.label("customer_name"),
                ).select_from(InvoiceTracking)
                .join(
                    Document,
                    InvoiceTracking.document_id == Document.id,
                    isouter=True,
                ).join(
                    BusinessEntity,
                    Document.business_entity_id == BusinessEntity.id,
                    isouter=True,
                ).where(
                    and_(
                        InvoiceTracking.company_id == company_id,
                        InvoiceTracking.status.in_(["overdue", "dunning"]),
                        InvoiceTracking.due_date.isnot(None),
                        InvoiceTracking.due_date < now,
                    )
                )
            )
            rows = result.all()

            return [
                {
                    "invoice_id": str(row[0].id),
                    "invoice_number": row[0].invoice_number or "",
                    "customer_name": row.customer_name or "",
                    "amount": float(row[0].outstanding_amount or row[0].amount or 0),
                    "days_overdue": (now - row[0].due_date).days if row[0].due_date else 0,
                    "dunning_level": int(row[0].dunning_level or 0),
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("overdue_provider_error", **safe_error_log(e))
            return []

    return {
        "cashflow_predictions": _get_cashflow_predictions,
        "upcoming_skonto": _get_skonto_invoices,
        "high_risk_entities": _get_high_risk_entities,
        "dunning_invoices": _get_dunning_invoices,
        "overdue_invoices": _get_overdue_invoices,
    }


# =============================================================================
# Convenience Methods (used by API endpoints)
# =============================================================================


async def generate_all_insights_from_db(
    engine: DailyInsightsEngine,
    db: "AsyncSession",
    company_id: UUID,
) -> List[DailyInsight]:
    """
    Generiert alle Insights für eine Company aus der DB.

    Convenience-Funktion die von den API-Endpoints genutzt wird.
    Erstellt Data Provider aus der DB und ruft die Engine auf.
    """
    providers = await _build_data_providers_from_db(db, company_id)
    result = await engine.generate_daily_insights(company_id, providers)
    return result.insights


async def generate_insights_by_type_from_db(
    engine: DailyInsightsEngine,
    db: "AsyncSession",
    company_id: UUID,
    insight_type: DailyInsightType,
) -> List[DailyInsight]:
    """
    Generiert Insights eines bestimmten Typs für eine Company.

    Filtert die generierten Insights nach dem angegebenen Typ.
    """
    all_insights = await generate_all_insights_from_db(engine, db, company_id)
    return [i for i in all_insights if i.insight_type == insight_type]


# =============================================================================
# Factory
# =============================================================================

_engine_instance: Optional[DailyInsightsEngine] = None


def get_daily_insights_engine(
    config: Optional[InsightGeneratorConfig] = None,
) -> DailyInsightsEngine:
    """
    Factory-Funktion für DailyInsightsEngine.

    Args:
        config: Optional Konfiguration

    Returns:
        DailyInsightsEngine Instanz
    """
    global _engine_instance

    if _engine_instance is None or config is not None:
        _engine_instance = DailyInsightsEngine(config=config)

    return _engine_instance
