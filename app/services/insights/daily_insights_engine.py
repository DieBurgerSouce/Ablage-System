# -*- coding: utf-8 -*-
"""
Daily Insights Engine - Proaktive Warnungen VOR Problemen.

Vision 2026 Q4: System das proaktiv warnt BEVOR Probleme entstehen.

Unterschied zum ProactiveInsightsService:
- ProactiveInsightsService: Kontext-sensitive Insights waehrend Chat/UI-Interaktion
- DailyInsightsEngine: Batch-generierte Insights die taeglich erstellt werden

Insight-Typen:
- cashflow_warning: "In 2 Wochen koennte Liquiditaet eng werden"
- contract_expiring: "Vertrag X laeuft in 30 Tagen aus"
- payment_risk: "Kunde Y hat 3 ueberfaellige Rechnungen"
- skonto_deadline: "Skonto fuer Rechnung Z verfaellt morgen"
- unusual_pattern: "Ausgaben diesen Monat 40% hoeher als ueblich"
- compliance_reminder: "Aufbewahrungsfrist fuer Dokumente 2015 endet bald"
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Callable, TypedDict, Union
from uuid import UUID, uuid4

import structlog
from prometheus_client import Counter, Histogram, Gauge

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
    """Typ des taeglichen Insights."""
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
    """Historischer Vergleich fuer Insights."""
    previous_value: str
    current_value: str
    change_percent: float
    period: str
    trend: str


class DailyInsightDict(TypedDict):
    """Typisiertes Dictionary fuer DailyInsight.to_dict()."""
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
    """Cashflow-Daten fuer Insight-Generierung."""
    current_balance: float
    projected_balance: float
    incoming_payments: List[Dict[str, Union[str, float]]]
    outgoing_payments: List[Dict[str, Union[str, float]]]


class ContractDataDict(TypedDict, total=False):
    """Vertragsdaten fuer Insight-Generierung."""
    contracts: List[Dict[str, Union[str, int, float]]]


class PaymentRiskDataDict(TypedDict, total=False):
    """Zahlungsrisiko-Daten fuer Insight-Generierung."""
    entities: List[Dict[str, Union[str, int, float]]]
    overdue_invoices: List[Dict[str, Union[str, float]]]


class SkontoDataDict(TypedDict, total=False):
    """Skonto-Daten fuer Insight-Generierung."""
    invoices: List[Dict[str, Union[str, float]]]


class PatternDataDict(TypedDict, total=False):
    """Muster-Daten fuer Insight-Generierung."""
    patterns: List[Dict[str, Union[str, float]]]
    baselines: Dict[str, float]


class ComplianceDataDict(TypedDict, total=False):
    """Compliance-Daten fuer Insight-Generierung."""
    deadlines: List[Dict[str, Union[str, int]]]
    documents: List[Dict[str, Union[str, int]]]


class RiskDataDict(TypedDict, total=False):
    """Risiko-Daten fuer Insight-Generierung."""
    entities: List[Dict[str, Union[str, int, float]]]


class DunningDataDict(TypedDict, total=False):
    """Mahnungs-Daten fuer Insight-Generierung."""
    invoices: List[Dict[str, Union[str, float, int]]]


# Union type fuer alle Insight-Daten (fuer Generator-Signaturen)
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
    Typisiertes Dictionary fuer alle Data Provider Ergebnisse.

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
    dunning_invoices: List[Dict[str, Union[str, float, int]]]


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class DailyInsight:
    """Ein taeglicher proaktiver Insight."""
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
    """Konfiguration fuer Insight-Generatoren."""
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


# =============================================================================
# Insight Generators
# =============================================================================

class BaseInsightGenerator:
    """Basis-Klasse fuer Insight-Generatoren."""

    insight_type: DailyInsightType

    def __init__(self, config: InsightGeneratorConfig):
        self.config = config

    async def generate(
        self,
        company_id: UUID,
        data: DataProvidersResult,
    ) -> List[DailyInsight]:
        """Generiert Insights. Muss ueberschrieben werden."""
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
                title=f"Kuendigungsfrist: {contract.get('title', 'Vertrag')}",
                summary=f"Kuendigungsfrist endet in {days_remaining} Tagen ({notice_date.strftime('%d.%m.%Y')}).",
                detail=f"Monatliche Kosten: {monthly_cost:,.2f} EUR. Vertrag verlaengert sich automatisch.",
                recommendation="Vertrag pruefen und ggf. kuendigen oder neu verhandeln.",
                related_document_id=UUID(contract["id"]) if contract.get("id") else None,
                predicted_date=notice_date,
                predicted_amount=monthly_cost * 12,  # Jaehrliche Kosten
                confidence=1.0,  # Sicher, da vertraglich festgelegt
                available_actions=["view_contract", "cancel", "renew", "negotiate"],
                primary_action_url=f"/contracts/{contract.get('id')}",
                primary_action_label="Vertrag pruefen",
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
                summary=f"Risiko-Score: {risk_score}/100, {entity.get('overdue_count', 0)} ueberfaellige Rechnungen.",
                detail=f"Ausstehender Betrag: {overdue_amount:,.2f} EUR.",
                recommendation="Zahlungsbedingungen ueberpruefen, ggf. Mahnung oder Inkasso einleiten.",
                related_entity_id=UUID(entity["entity_id"]) if entity.get("entity_id") else None,
                related_entity_name=entity.get("name"),
                predicted_amount=overdue_amount,
                confidence=risk_score / 100,
                available_actions=["view_entity", "send_reminder", "start_dunning", "block_entity"],
                primary_action_url=f"/entities/{entity.get('entity_id')}/risk",
                primary_action_label="Risiko analysieren",
                factors=[
                    {"name": "Risiko-Score", "value": f"{risk_score}/100"},
                    {"name": "Ueberfaellige Rechnungen", "value": str(entity.get("overdue_count", 0))},
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
                direction = "hoeher"
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
                recommendation="Ueberpruefen ob die Abweichung beabsichtigt ist.",
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
                # Bereits abgelaufen - Dokumente koennen geloescht werden
                severity = InsightSeverity.LOW
                title = f"Aufbewahrungsfrist abgelaufen: Dokumente {item.get('year')}"
                summary = f"{item.get('document_count', 0)} Dokumente koennen geloescht werden."
                recommendation = "Dokumente archivieren oder sicher loeschen."
            elif months_remaining <= self.config.retention_warning_months:
                severity = InsightSeverity.MEDIUM
                title = f"Aufbewahrungsfrist endet bald: Dokumente {item.get('year')}"
                summary = f"Aufbewahrungsfrist fuer {item.get('document_count', 0)} Dokumente endet in {months_remaining} Monaten."
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
    """Generiert Warnungen fuer ueberfaellige Rechnungen."""

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
                title=f"Ueberfaellige Rechnung: {invoice.get('invoice_number')}",
                summary=f"{days_overdue} Tage ueberfaellig, Kunde: {invoice.get('customer_name')}.",
                detail=f"Betrag: {amount:,.2f} EUR, Mahnstufe: {invoice.get('dunning_level', 0)}.",
                recommendation="Zahlungserinnerung senden oder Mahnstufe erhoehen.",
                related_invoice_id=UUID(invoice["invoice_id"]) if invoice.get("invoice_id") else None,
                related_entity_name=invoice.get("customer_name"),
                predicted_amount=amount,
                confidence=1.0,
                available_actions=["send_reminder", "increase_dunning", "mark_paid", "view_invoice"],
                primary_action_url=f"/invoices/{invoice.get('invoice_id')}",
                primary_action_label="Rechnung oeffnen",
                factors=[
                    {"name": "Tage ueberfaellig", "value": str(days_overdue)},
                    {"name": "Mahnstufe", "value": str(invoice.get("dunning_level", 0))},
                ],
            ))

        return insights


# =============================================================================
# Daily Insights Engine
# =============================================================================

class DailyInsightsEngine:
    """
    Engine fuer taegliche proaktive Insights.

    Generiert Batch-Insights fuer alle Companies basierend auf:
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
        ]

    def register_generator(self, generator: BaseInsightGenerator) -> None:
        """Registriert einen zusaetzlichen Generator."""
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
        Generiert alle taeglichen Insights fuer eine Company.

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

        # Alle Generatoren ausfuehren
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
        Holt nur die kritischsten Insights (fuer Dashboard).

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
        Holt Insights mit verfuegbaren Aktionen.

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
# Factory
# =============================================================================

_engine_instance: Optional[DailyInsightsEngine] = None


def get_daily_insights_engine(
    config: Optional[InsightGeneratorConfig] = None,
) -> DailyInsightsEngine:
    """
    Factory-Funktion fuer DailyInsightsEngine.

    Args:
        config: Optional Konfiguration

    Returns:
        DailyInsightsEngine Instanz
    """
    global _engine_instance

    if _engine_instance is None or config is not None:
        _engine_instance = DailyInsightsEngine(config=config)

    return _engine_instance
