"""
CEO Dashboard - Digital Twin Service

Zentrale Übersicht über Unternehmensgesundheit.
Kombiniert Daten aus allen Modulen für Executive Dashboard.

Feinpoliert und durchdacht - Enterprise CEO Dashboard.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, List, Dict, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Document,
    InvoiceTracking,
    InvoiceStatus,
    ProcessingStatus,
    BusinessEntity,
)
from app.db.models_alert import Alert, AlertStatus, AlertSeverity

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class HealthScore:
    """Gesundheits-Score des Unternehmens (0-100)."""

    overall: float  # Gesamt-Score (0-100)
    financial: float  # Finanzielle Gesundheit
    operations: float  # Operative Effizienz
    risk: float  # Risikomanagement
    compliance: float  # Compliance-Status
    trend: str  # improving, stable, declining

    def to_dict(self) -> Dict[str, float | str]:
        """Konvertiert zu Dictionary."""
        return {
            "overall": round(self.overall, 1),
            "financial": round(self.financial, 1),
            "operations": round(self.operations, 1),
            "risk": round(self.risk, 1),
            "compliance": round(self.compliance, 1),
            "trend": self.trend,
        }


@dataclass
class CompanyOverview:
    """Unternehmens-Übersicht für CEO Dashboard."""

    health_score: HealthScore
    documents_today: int
    documents_this_month: int
    pending_invoices: int
    pending_amount: Decimal
    overdue_invoices: int
    overdue_amount: Decimal
    active_alerts: int
    critical_alerts: int
    auto_process_rate: float  # 0-1

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "health_score": self.health_score.to_dict(),
            "documents_today": self.documents_today,
            "documents_this_month": self.documents_this_month,
            "pending_invoices": self.pending_invoices,
            "pending_amount": float(self.pending_amount),
            "overdue_invoices": self.overdue_invoices,
            "overdue_amount": float(self.overdue_amount),
            "active_alerts": self.active_alerts,
            "critical_alerts": self.critical_alerts,
            "auto_process_rate": round(self.auto_process_rate, 3),
        }


@dataclass
class TrendDataPoint:
    """Einzelner Datenpunkt für Trend-Analyse."""

    timestamp: datetime
    value: float
    label: str


@dataclass
class TrendData:
    """Trend-Daten für Sparklines."""

    documents_processed: List[TrendDataPoint]
    invoice_volume: List[TrendDataPoint]
    auto_process_rate: List[TrendDataPoint]
    alert_count: List[TrendDataPoint]

    def to_dict(self) -> Dict[str, List[Dict]]:
        """Konvertiert zu Dictionary."""
        return {
            "documents_processed": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "value": p.value,
                    "label": p.label,
                }
                for p in self.documents_processed
            ],
            "invoice_volume": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "value": p.value,
                    "label": p.label,
                }
                for p in self.invoice_volume
            ],
            "auto_process_rate": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "value": p.value,
                    "label": p.label,
                }
                for p in self.auto_process_rate
            ],
            "alert_count": [
                {
                    "timestamp": p.timestamp.isoformat(),
                    "value": p.value,
                    "label": p.label,
                }
                for p in self.alert_count
            ],
        }


@dataclass
class Anomaly:
    """Erkannte Anomalie im System."""

    title: str  # German
    description: str  # German
    severity: str  # info, warning, critical
    category: str
    detected_at: datetime
    metric_name: str
    expected_value: float
    actual_value: float
    deviation_percent: float

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "category": self.category,
            "detected_at": self.detected_at.isoformat(),
            "metric_name": self.metric_name,
            "expected_value": round(self.expected_value, 2),
            "actual_value": round(self.actual_value, 2),
            "deviation_percent": round(self.deviation_percent, 1),
        }


# =============================================================================
# Digital Twin Service
# =============================================================================


class DigitalTwinService:
    """
    Digital Twin Service für CEO Dashboard.

    Aggregiert Daten aus allen Modulen für Executive-Level Übersicht.
    """

    def __init__(self) -> None:
        """Initialisiert Service."""
        pass

    async def get_overview(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> CompanyOverview:
        """
        Holt Unternehmens-Übersicht.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            CompanyOverview mit allen Metriken
        """
        logger.info("ceo_dashboard.get_overview", company_id=str(company_id))

        # Parallele Datenabfragen
        health_score = await self.get_health_score(company_id, db)

        # Dokument-Statistiken
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Dokumente heute
        docs_today_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= today_start,
                Document.deleted_at.is_(None),
            )
        )
        docs_today_result = await db.execute(docs_today_query)
        documents_today = docs_today_result.scalar() or 0

        # Dokumente diesen Monat
        docs_month_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= month_start,
                Document.deleted_at.is_(None),
            )
        )
        docs_month_result = await db.execute(docs_month_query)
        documents_this_month = docs_month_result.scalar() or 0

        # Rechnungs-Statistiken
        pending_invoices_query = select(
            func.count(InvoiceTracking.id),
            func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status.in_([InvoiceStatus.OPEN, InvoiceStatus.SENT]),
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        pending_result = await db.execute(pending_invoices_query)
        pending_row = pending_result.first()
        pending_invoices = pending_row[0] if pending_row else 0
        pending_amount = Decimal(str(pending_row[1])) if pending_row else Decimal("0")

        # Überfällige Rechnungen
        overdue_query = select(
            func.count(InvoiceTracking.id),
            func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.status == InvoiceStatus.OVERDUE,
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        overdue_result = await db.execute(overdue_query)
        overdue_row = overdue_result.first()
        overdue_invoices = overdue_row[0] if overdue_row else 0
        overdue_amount = Decimal(str(overdue_row[1])) if overdue_row else Decimal("0")

        # Alert-Statistiken
        active_alerts_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED, AlertStatus.IN_PROGRESS]),
            )
        )
        active_alerts_result = await db.execute(active_alerts_query)
        active_alerts = active_alerts_result.scalar() or 0

        critical_alerts_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.severity == AlertSeverity.CRITICAL,
                Alert.status.in_([AlertStatus.NEW, AlertStatus.ACKNOWLEDGED]),
            )
        )
        critical_alerts_result = await db.execute(critical_alerts_query)
        critical_alerts = critical_alerts_result.scalar() or 0

        # Auto-Process Rate (letzte 7 Tage)
        week_ago = now - timedelta(days=7)
        auto_rate_query = select(
            func.count(Document.id).filter(
                Document.status == ProcessingStatus.COMPLETED
            ).label("completed"),
            func.count(Document.id).label("total"),
        ).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= week_ago,
                Document.deleted_at.is_(None),
            )
        )
        auto_rate_result = await db.execute(auto_rate_query)
        auto_rate_row = auto_rate_result.first()
        completed = auto_rate_row[0] if auto_rate_row else 0
        total = auto_rate_row[1] if auto_rate_row else 0
        auto_process_rate = completed / total if total > 0 else 0.0

        return CompanyOverview(
            health_score=health_score,
            documents_today=documents_today,
            documents_this_month=documents_this_month,
            pending_invoices=pending_invoices,
            pending_amount=pending_amount,
            overdue_invoices=overdue_invoices,
            overdue_amount=overdue_amount,
            active_alerts=active_alerts,
            critical_alerts=critical_alerts,
            auto_process_rate=auto_process_rate,
        )

    async def get_health_score(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> HealthScore:
        """
        Berechnet Unternehmens-Gesundheits-Score.

        Delegiert an HealthScoreCalculator für detaillierte Berechnung.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            HealthScore (0-100)
        """
        from app.services.ceo_dashboard.health_score_calculator import HealthScoreCalculator

        calculator = HealthScoreCalculator()
        return await calculator.calculate(company_id, db)

    async def get_trends(
        self,
        company_id: UUID,
        days: int,
        db: AsyncSession,
    ) -> TrendData:
        """
        Holt Trend-Daten für Sparklines.

        Args:
            company_id: Company UUID
            days: Anzahl Tage
            db: Database session

        Returns:
            TrendData mit Zeitreihen
        """
        from app.services.ceo_dashboard.trend_analyzer import TrendAnalyzer

        analyzer = TrendAnalyzer()
        return await analyzer.analyze(company_id, days, db)

    async def get_anomalies(
        self,
        company_id: UUID,
        db: AsyncSession,
    ) -> List[Anomaly]:
        """
        Erkennt Anomalien in Unternehmens-Metriken.

        Args:
            company_id: Company UUID
            db: Database session

        Returns:
            Liste erkannter Anomalien
        """
        logger.info("ceo_dashboard.detect_anomalies", company_id=str(company_id))

        anomalies: List[Anomaly] = []
        now = datetime.now(timezone.utc)

        # 1. Ungewoehnlich viele neue Alerts
        last_24h = now - timedelta(hours=24)
        alerts_24h_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.created_at >= last_24h,
            )
        )
        alerts_24h_result = await db.execute(alerts_24h_query)
        alerts_count = alerts_24h_result.scalar() or 0

        # Erwartungswert: Durchschnitt der letzten 7 Tage
        week_ago = now - timedelta(days=7)
        alerts_avg_query = select(func.count(Alert.id)).where(
            and_(
                Alert.company_id == company_id,
                Alert.created_at >= week_ago,
                Alert.created_at < last_24h,
            )
        )
        alerts_avg_result = await db.execute(alerts_avg_query)
        alerts_avg = (alerts_avg_result.scalar() or 0) / 6  # 6 Tage Durchschnitt

        if alerts_avg > 0 and alerts_count > alerts_avg * 2:  # 2x mehr als normal
            deviation = ((alerts_count - alerts_avg) / alerts_avg) * 100
            anomalies.append(
                Anomaly(
                    title="Ungewöhnlich viele Alerts",
                    description=f"{alerts_count} Alerts in 24h (normal: {int(alerts_avg)})",
                    severity="warning",
                    category="system",
                    detected_at=now,
                    metric_name="alerts_24h",
                    expected_value=alerts_avg,
                    actual_value=float(alerts_count),
                    deviation_percent=deviation,
                )
            )

        # 2. Dokument-Verarbeitung stark abgefallen
        docs_today_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                Document.deleted_at.is_(None),
            )
        )
        docs_today_result = await db.execute(docs_today_query)
        docs_today = docs_today_result.scalar() or 0

        # Durchschnitt letzte 7 Tage
        docs_avg_query = select(func.count(Document.id)).where(
            and_(
                Document.company_id == company_id,
                Document.created_at >= week_ago,
                Document.created_at < now.replace(hour=0, minute=0, second=0, microsecond=0),
                Document.deleted_at.is_(None),
            )
        )
        docs_avg_result = await db.execute(docs_avg_query)
        docs_avg = (docs_avg_result.scalar() or 0) / 7

        if docs_avg > 5 and docs_today <= docs_avg * 0.5:  # 50% oder mehr weniger als normal
            deviation = ((docs_today - docs_avg) / docs_avg) * 100 if docs_avg > 0 else 0
            anomalies.append(
                Anomaly(
                    title="Dokument-Verarbeitung stark gesunken",
                    description=f"Nur {docs_today} Dokumente heute (normal: {int(docs_avg)})",
                    severity="warning",
                    category="operations",
                    detected_at=now,
                    metric_name="documents_processed",
                    expected_value=docs_avg,
                    actual_value=float(docs_today),
                    deviation_percent=deviation,
                )
            )

        # 3. Ungewoehnlich hohe Ausfallrate
        overdue_query = select(
            func.count(InvoiceTracking.id).filter(
                InvoiceTracking.status == InvoiceStatus.OVERDUE
            ).label("overdue"),
            func.count(InvoiceTracking.id).label("total"),
        ).where(
            and_(
                InvoiceTracking.company_id == company_id,
                InvoiceTracking.deleted_at.is_(None),
            )
        )
        overdue_result = await db.execute(overdue_query)
        overdue_row = overdue_result.first()
        overdue_count = overdue_row[0] if overdue_row else 0
        total_invoices = overdue_row[1] if overdue_row else 0

        if total_invoices > 10:
            overdue_rate = overdue_count / total_invoices
            if overdue_rate > 0.15:  # Mehr als 15% überfällig
                anomalies.append(
                    Anomaly(
                        title="Hohe Ausfallrate bei Rechnungen",
                        description=f"{overdue_count} von {total_invoices} Rechnungen überfällig ({overdue_rate*100:.1f}%)",
                        severity="critical" if overdue_rate > 0.25 else "warning",
                        category="financial",
                        detected_at=now,
                        metric_name="invoice_default_rate",
                        expected_value=0.10,  # 10% als akzeptabel
                        actual_value=overdue_rate,
                        deviation_percent=(overdue_rate - 0.10) / 0.10 * 100,
                    )
                )

        logger.info(
            "ceo_dashboard.anomalies_detected",
            company_id=str(company_id),
            count=len(anomalies),
        )

        return anomalies
