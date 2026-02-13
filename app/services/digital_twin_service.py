# -*- coding: utf-8 -*-
"""
Digital Twin Service - 360° Unternehmensansicht.

Bietet einen vollstaendigen Schnappschuss des Unternehmens:
- Financial Health Status
- Risk Overview
- Document Pipeline
- Compliance Status
- Key Metrics
- Trends

Feinpoliert und durchdacht - Enterprise Digital Twin.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    BusinessEntity,
    InvoiceTracking,
    User,
)
from app.services.privat.financial_health_service import (
    FinancialHealthService,
    HealthRating,
)
from app.services.risk_scoring_service import (
    RiskScoringService,
    RiskLevel,
    get_risk_scoring_service,
)
from app.services.alert_center_service import AlertStatus
from app.db.models_alert import Alert

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class FinancialHealthSection:
    """Financial Health Zusammenfassung."""
    health_score: float  # 0-100
    cashflow_current_month: Decimal
    cashflow_trend: str  # "steigend", "stabil", "fallend"
    open_receivables: Decimal
    open_payables: Decimal
    overdue_amount: Decimal
    liquidity_ratio: float


@dataclass
class RiskOverviewSection:
    """Risk Overview Zusammenfassung."""
    average_risk_score: float
    high_risk_entities: int
    entities_with_worsening_trend: int
    top_risks: List[Dict[str, str]]  # [{entity_name, risk_score, trend}]


@dataclass
class DocumentPipelineSection:
    """Document Pipeline Status."""
    documents_today: int
    documents_this_week: int
    documents_this_month: int
    pending_ocr: int
    pending_review: int
    pending_approval: int
    auto_processed_rate: float  # % of documents auto-processed


@dataclass
class ComplianceSection:
    """Compliance Status Zusammenfassung."""
    gdpr_score: float  # 0-100
    gobd_score: float  # 0-100
    retention_violations: int
    missing_audit_trails: int
    upcoming_deadlines: int


@dataclass
class KeyMetricsSection:
    """Key Business Metrics."""
    total_documents: int
    total_entities: int
    total_invoices: int
    average_processing_time_s: float
    ocr_accuracy_rate: float
    auto_categorization_rate: float


@dataclass
class TrendSection:
    """Trend Data fuer Charts."""
    document_volume_trend: List[Dict[str, int]]  # [{month, count}]
    revenue_trend: List[Dict[str, float]]  # [{month, amount}]
    risk_trend: List[Dict[str, float]]  # [{month, avg_score}]


@dataclass
class DigitalTwinSnapshot:
    """Vollstaendiges Unternehmens-Abbild."""
    timestamp: datetime
    financial_health: FinancialHealthSection
    risk_overview: RiskOverviewSection
    document_pipeline: DocumentPipelineSection
    compliance_status: ComplianceSection
    key_metrics: KeyMetricsSection
    trends: TrendSection

    def to_dict(self) -> Dict[str, Any]:
        """Convert to serializable dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "financial_health": {
                "health_score": self.financial_health.health_score,
                "cashflow_current_month": float(self.financial_health.cashflow_current_month),
                "cashflow_trend": self.financial_health.cashflow_trend,
                "open_receivables": float(self.financial_health.open_receivables),
                "open_payables": float(self.financial_health.open_payables),
                "overdue_amount": float(self.financial_health.overdue_amount),
                "liquidity_ratio": self.financial_health.liquidity_ratio,
            },
            "risk_overview": {
                "average_risk_score": self.risk_overview.average_risk_score,
                "high_risk_entities": self.risk_overview.high_risk_entities,
                "entities_with_worsening_trend": self.risk_overview.entities_with_worsening_trend,
                "top_risks": self.risk_overview.top_risks,
            },
            "document_pipeline": {
                "documents_today": self.document_pipeline.documents_today,
                "documents_this_week": self.document_pipeline.documents_this_week,
                "documents_this_month": self.document_pipeline.documents_this_month,
                "pending_ocr": self.document_pipeline.pending_ocr,
                "pending_review": self.document_pipeline.pending_review,
                "pending_approval": self.document_pipeline.pending_approval,
                "auto_processed_rate": self.document_pipeline.auto_processed_rate,
            },
            "compliance_status": {
                "gdpr_score": self.compliance_status.gdpr_score,
                "gobd_score": self.compliance_status.gobd_score,
                "retention_violations": self.compliance_status.retention_violations,
                "missing_audit_trails": self.compliance_status.missing_audit_trails,
                "upcoming_deadlines": self.compliance_status.upcoming_deadlines,
            },
            "key_metrics": {
                "total_documents": self.key_metrics.total_documents,
                "total_entities": self.key_metrics.total_entities,
                "total_invoices": self.key_metrics.total_invoices,
                "average_processing_time_s": self.key_metrics.average_processing_time_s,
                "ocr_accuracy_rate": self.key_metrics.ocr_accuracy_rate,
                "auto_categorization_rate": self.key_metrics.auto_categorization_rate,
            },
            "trends": {
                "document_volume_trend": self.trends.document_volume_trend,
                "revenue_trend": self.trends.revenue_trend,
                "risk_trend": self.trends.risk_trend,
            },
        }


# =============================================================================
# Digital Twin Service
# =============================================================================

class DigitalTwinService:
    """
    Service fuer Digital Twin Snapshot-Generierung.

    Kombiniert Daten aus verschiedenen Services fuer 360° Sicht.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service."""
        self.db = db
        self._financial_health_service = FinancialHealthService()
        self._risk_scoring_service = get_risk_scoring_service(use_v2=True)

    async def get_snapshot(
        self,
        company_id: UUID,
    ) -> DigitalTwinSnapshot:
        """
        Erstellt vollstaendigen Digital Twin Snapshot.

        Args:
            company_id: Company ID

        Returns:
            DigitalTwinSnapshot mit allen Sektionen
        """
        logger.info("digital_twin_snapshot_start", company_id=str(company_id))

        # Alle Sektionen parallel abrufen
        financial_health = await self._get_financial_health_section(company_id)
        risk_overview = await self._get_risk_overview_section(company_id)
        document_pipeline = await self._get_document_pipeline_section(company_id)
        compliance_status = await self._get_compliance_section(company_id)
        key_metrics = await self._get_key_metrics_section(company_id)
        trends = await self._get_trends_section(company_id)

        snapshot = DigitalTwinSnapshot(
            timestamp=datetime.now(timezone.utc),
            financial_health=financial_health,
            risk_overview=risk_overview,
            document_pipeline=document_pipeline,
            compliance_status=compliance_status,
            key_metrics=key_metrics,
            trends=trends,
        )

        logger.info("digital_twin_snapshot_complete", company_id=str(company_id))
        return snapshot

    async def get_section(
        self,
        company_id: UUID,
        section: str,
    ) -> Any:
        """
        Ruft einzelne Sektion ab.

        Args:
            company_id: Company ID
            section: Section name (financial_health, risk_overview, etc.)

        Returns:
            Section dataclass
        """
        section_map = {
            "financial_health": self._get_financial_health_section,
            "risk_overview": self._get_risk_overview_section,
            "document_pipeline": self._get_document_pipeline_section,
            "compliance_status": self._get_compliance_section,
            "key_metrics": self._get_key_metrics_section,
            "trends": self._get_trends_section,
        }

        if section not in section_map:
            raise ValueError(f"Unbekannte Sektion: {section}")

        return await section_map[section](company_id)

    # =========================================================================
    # Section Builders
    # =========================================================================

    async def _get_financial_health_section(
        self,
        company_id: UUID,
    ) -> FinancialHealthSection:
        """Berechnet Financial Health Sektion."""
        # Cashflow aus Invoices
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        cashflow_query = select(
            func.coalesce(func.sum(InvoiceTracking.amount_total), 0)
        ).join(
            Document, InvoiceTracking.document_id == Document.id
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                InvoiceTracking.paid_at >= month_start,
                InvoiceTracking.paid_at.isnot(None),
            )
        )
        result = await self.db.execute(cashflow_query)
        cashflow_current_month = Decimal(str(result.scalar() or 0))

        # Open Receivables
        receivables_query = select(
            func.coalesce(func.sum(InvoiceTracking.amount_total), 0)
        ).join(
            Document, InvoiceTracking.document_id == Document.id
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                InvoiceTracking.status.in_(["open", "sent"]),
                InvoiceTracking.invoice_type == "incoming",
            )
        )
        result = await self.db.execute(receivables_query)
        open_receivables = Decimal(str(result.scalar() or 0))

        # Open Payables
        payables_query = select(
            func.coalesce(func.sum(InvoiceTracking.amount_total), 0)
        ).join(
            Document, InvoiceTracking.document_id == Document.id
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                InvoiceTracking.status.in_(["open", "sent"]),
                InvoiceTracking.invoice_type == "outgoing",
            )
        )
        result = await self.db.execute(payables_query)
        open_payables = Decimal(str(result.scalar() or 0))

        # Overdue Amount
        overdue_query = select(
            func.coalesce(func.sum(InvoiceTracking.amount_total), 0)
        ).join(
            Document, InvoiceTracking.document_id == Document.id
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                InvoiceTracking.status == "overdue",
            )
        )
        result = await self.db.execute(overdue_query)
        overdue_amount = Decimal(str(result.scalar() or 0))

        # Liquidity Ratio (vereinfacht: Cashflow / Payables)
        liquidity_ratio = 0.0
        if open_payables > 0:
            liquidity_ratio = float(cashflow_current_month / open_payables)

        # Cashflow Trend (letzte 3 Monate vergleichen)
        cashflow_trend = "stabil"
        # TODO: Implement trend calculation

        return FinancialHealthSection(
            health_score=75.0,  # TODO: Integration mit Financial Health Service
            cashflow_current_month=cashflow_current_month,
            cashflow_trend=cashflow_trend,
            open_receivables=open_receivables,
            open_payables=open_payables,
            overdue_amount=overdue_amount,
            liquidity_ratio=liquidity_ratio,
        )

    async def _get_risk_overview_section(
        self,
        company_id: UUID,
    ) -> RiskOverviewSection:
        """Berechnet Risk Overview Sektion."""
        # Average Risk Score
        avg_query = select(
            func.coalesce(func.avg(BusinessEntity.risk_score), 0)
        ).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
                BusinessEntity.risk_score.isnot(None),
            )
        )
        result = await self.db.execute(avg_query)
        average_risk_score = float(result.scalar() or 0)

        # High Risk Entities Count (score >= 60)
        high_risk_query = select(
            func.count(BusinessEntity.id)
        ).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
                BusinessEntity.risk_score >= 60,
            )
        )
        result = await self.db.execute(high_risk_query)
        high_risk_entities = result.scalar() or 0

        # Entities with Worsening Trend
        # (risk_factors JSONB contains payment_trend = WORSENING)
        worsening_query = select(
            func.count(BusinessEntity.id)
        ).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
                BusinessEntity.risk_factors.contains({"payment_trend": "WORSENING"}),
            )
        )
        result = await self.db.execute(worsening_query)
        entities_with_worsening_trend = result.scalar() or 0

        # Top 5 Risks
        top_risks_query = select(
            BusinessEntity.name,
            BusinessEntity.risk_score,
            BusinessEntity.risk_factors,
        ).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
                BusinessEntity.risk_score.isnot(None),
            )
        ).order_by(desc(BusinessEntity.risk_score)).limit(5)

        result = await self.db.execute(top_risks_query)
        top_risks: List[Dict[str, str]] = []

        for row in result.all():
            trend = "stabil"
            if row.risk_factors and isinstance(row.risk_factors, dict):
                trend = row.risk_factors.get("payment_trend", "STABLE").lower()

            top_risks.append({
                "entity_name": row.name,
                "risk_score": f"{row.risk_score:.1f}" if row.risk_score else "0",
                "trend": trend,
            })

        return RiskOverviewSection(
            average_risk_score=round(average_risk_score, 1),
            high_risk_entities=high_risk_entities,
            entities_with_worsening_trend=entities_with_worsening_trend,
            top_risks=top_risks,
        )

    async def _get_document_pipeline_section(
        self,
        company_id: UUID,
    ) -> DocumentPipelineSection:
        """Berechnet Document Pipeline Sektion."""
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Documents Today
        today_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.created_at >= today_start,
            )
        )
        result = await self.db.execute(today_query)
        documents_today = result.scalar() or 0

        # Documents This Week
        week_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.created_at >= week_start,
            )
        )
        result = await self.db.execute(week_query)
        documents_this_week = result.scalar() or 0

        # Documents This Month
        month_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.created_at >= month_start,
            )
        )
        result = await self.db.execute(month_query)
        documents_this_month = result.scalar() or 0

        # Pending OCR (status = processing)
        pending_ocr_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.processing_status == "processing",
            )
        )
        result = await self.db.execute(pending_ocr_query)
        pending_ocr = result.scalar() or 0

        # Pending Review (flagged for manual review)
        pending_review_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.needs_review == True,
            )
        )
        result = await self.db.execute(pending_review_query)
        pending_review = result.scalar() or 0

        # Pending Approval (Invoice status = pending_approval)
        pending_approval_query = select(
            func.count(Document.id)
        ).join(
            InvoiceTracking, Document.id == InvoiceTracking.document_id
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                InvoiceTracking.status == "pending_approval",
            )
        )
        result = await self.db.execute(pending_approval_query)
        pending_approval = result.scalar() or 0

        # Auto-processed Rate (documents with category set automatically)
        total_month_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.created_at >= month_start,
            )
        )
        result = await self.db.execute(total_month_query)
        total_month = result.scalar() or 1  # Avoid division by zero

        auto_processed_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
                Document.created_at >= month_start,
                Document.category.isnot(None),
                Document.needs_review == False,
            )
        )
        result = await self.db.execute(auto_processed_query)
        auto_processed = result.scalar() or 0

        auto_processed_rate = (auto_processed / total_month) * 100 if total_month > 0 else 0.0

        return DocumentPipelineSection(
            documents_today=documents_today,
            documents_this_week=documents_this_week,
            documents_this_month=documents_this_month,
            pending_ocr=pending_ocr,
            pending_review=pending_review,
            pending_approval=pending_approval,
            auto_processed_rate=round(auto_processed_rate, 1),
        )

    async def _get_compliance_section(
        self,
        company_id: UUID,
    ) -> ComplianceSection:
        """Berechnet Compliance Sektion."""
        # GDPR Score (vereinfacht)
        gdpr_score = 85.0  # TODO: Implement GDPR scoring

        # GoBD Score (vereinfacht)
        gobd_score = 90.0  # TODO: Implement GoBD scoring

        # Retention Violations
        retention_violations = 0  # TODO: Check retention policy violations

        # Missing Audit Trails
        missing_audit_trails = 0  # TODO: Check for documents without audit trail

        # Upcoming Deadlines (next 30 days)
        thirty_days = datetime.now(timezone.utc) + timedelta(days=30)

        deadline_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.category == "deadline",
                Alert.status.in_([AlertStatus.NEW.value, AlertStatus.ACKNOWLEDGED.value]),
                Alert.metadata.contains({"deadline_date": None}),  # Placeholder
            )
        )
        result = await self.db.execute(deadline_query)
        upcoming_deadlines = result.scalar() or 0

        return ComplianceSection(
            gdpr_score=gdpr_score,
            gobd_score=gobd_score,
            retention_violations=retention_violations,
            missing_audit_trails=missing_audit_trails,
            upcoming_deadlines=upcoming_deadlines,
        )

    async def _get_key_metrics_section(
        self,
        company_id: UUID,
    ) -> KeyMetricsSection:
        """Berechnet Key Metrics Sektion."""
        # Total Documents
        total_docs_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(total_docs_query)
        total_documents = result.scalar() or 0

        # Total Entities
        total_entities_query = select(func.count(BusinessEntity.id)).where(
            and_(
                BusinessEntity.company_id == company_id,
                BusinessEntity.is_active == True,
                BusinessEntity.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(total_entities_query)
        total_entities = result.scalar() or 0

        # Total Invoices
        total_invoices_query = select(func.count(InvoiceTracking.id)).join(
            Document, InvoiceTracking.document_id == Document.id
        ).where(
            and_(
                Document.company_id == company_id,
                Document.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(total_invoices_query)
        total_invoices = result.scalar() or 0

        # Average Processing Time
        average_processing_time_s = 2.5  # TODO: Calculate from task logs

        # OCR Accuracy Rate
        ocr_accuracy_rate = 94.5  # TODO: Calculate from OCR feedback

        # Auto-Categorization Rate
        auto_categorization_rate = 87.3  # TODO: Calculate from document categories

        return KeyMetricsSection(
            total_documents=total_documents,
            total_entities=total_entities,
            total_invoices=total_invoices,
            average_processing_time_s=average_processing_time_s,
            ocr_accuracy_rate=ocr_accuracy_rate,
            auto_categorization_rate=auto_categorization_rate,
        )

    async def _get_trends_section(
        self,
        company_id: UUID,
    ) -> TrendSection:
        """Berechnet Trends Sektion."""
        # Document Volume Trend (last 6 months)
        document_volume_trend: List[Dict[str, int]] = []
        # TODO: Implement monthly aggregation

        # Revenue Trend (last 6 months)
        revenue_trend: List[Dict[str, float]] = []
        # TODO: Implement monthly revenue aggregation

        # Risk Trend (last 6 months)
        risk_trend: List[Dict[str, float]] = []
        # TODO: Implement monthly average risk score

        return TrendSection(
            document_volume_trend=document_volume_trend,
            revenue_trend=revenue_trend,
            risk_trend=risk_trend,
        )


# =============================================================================
# Factory Function
# =============================================================================

def get_digital_twin_service(db: AsyncSession) -> DigitalTwinService:
    """Factory function to create DigitalTwinService instance."""
    return DigitalTwinService(db)
