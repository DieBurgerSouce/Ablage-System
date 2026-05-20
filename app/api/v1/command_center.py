# -*- coding: utf-8 -*-
"""
Command Center API - Konsolidierte Startseite.

Enterprise Feature: Ein einziger Endpunkt der alle Daten fuer die
Startseite/Command-Center-View aggregiert. Vereinigt:
- CEO Dashboard (Gesundheits-Score, Metriken)
- Daily Insights (proaktive Warnungen)
- Financial Insights (Cashflow, Skonto)
- Predictive Health (System-Gesundheit)
- Action Queue (priorisierte Aufgaben)

Endpoints:
- GET /command-center - Vollstaendige Startseiten-Daten
- GET /command-center/kpis - Nur KPI-Widgets
- GET /command-center/tasks - Nur priorisierte Aufgaben
- GET /command-center/insights - Nur proaktive Insights
- GET /command-center/alerts - Nur aktive Warnungen
- GET /command-center/cashflow - Nur Cashflow-Sparkline

Feinpoliert und durchdacht - Die All-in-One Finanzplattform Startseite.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Annotated, Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import Document, User
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/command-center", tags=["Command Center"])


# =============================================================================
# PROMETHEUS METRIKEN
# =============================================================================

_CC_REQUEST = Counter(
    "command_center_request_total",
    "Command Center API-Anfragen",
    ["endpoint", "status"],
)

_CC_DURATION = Histogram(
    "command_center_request_duration_seconds",
    "Command Center Antwortzeit",
    ["endpoint"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================


class KPIWidget(BaseModel):
    """Ein einzelnes KPI-Widget."""

    id: str = Field(..., description="Widget-ID")
    label: str = Field(..., description="Anzeigename (Deutsch)")
    value: str = Field(..., description="Formatierter Wert")
    raw_value: float = Field(0.0, description="Numerischer Rohwert")
    unit: str = Field("", description="Einheit (EUR, %, Stueck)")
    trend: Optional[str] = Field(None, description="up, down, stable")
    trend_value: Optional[str] = Field(
        None, description="Trend-Wert, z.B. '+12%'"
    )
    variant: str = Field(
        "default",
        description="Widget-Variante: default, success, warning, danger",
    )
    icon: Optional[str] = Field(None, description="Icon-Name fuer die UI")


class ProactiveInsight(BaseModel):
    """Ein proaktiver Insight/Warnung."""

    id: str
    severity: str = Field(..., description="info, warning, critical")
    title: str = Field(..., description="Kurztitel (Deutsch)")
    description: str = Field(..., description="Beschreibung (Deutsch)")
    category: str = Field(
        ..., description="cashflow, skonto, contract, payment, compliance"
    )
    action_label: Optional[str] = Field(
        None, description="Button-Text fuer Aktion"
    )
    action_route: Optional[str] = Field(
        None, description="Navigation-Route"
    )
    created_at: str


class TaskItem(BaseModel):
    """Eine priorisierte Aufgabe."""

    id: str
    title: str = Field(..., description="Aufgabentitel (Deutsch)")
    description: Optional[str] = None
    priority: int = Field(..., ge=1, le=5, description="1=hoechste Prioritaet")
    action_type: str = Field(
        ...,
        description=(
            "Typ: approve, pay, categorize, review, resolve, link"
        ),
    )
    category: str
    due_date: Optional[str] = None
    financial_impact: Optional[float] = Field(
        None, description="Finanzieller Impact in EUR"
    )
    action_route: Optional[str] = None


class AlertItem(BaseModel):
    """Ein aktiver Alert."""

    id: str
    severity: str
    title: str
    source: str = Field(
        ..., description="Quelle: anomaly, compliance, fraud, system"
    )
    created_at: str


class CashflowPoint(BaseModel):
    """Ein Cashflow-Datenpunkt fuer die Sparkline."""

    date: str
    inflow: float
    outflow: float
    balance: float


class CommandCenterProgress(BaseModel):
    """Tagesfortschritt."""

    completed: int
    total: int
    percentage: float


class CommandCenterResponse(BaseModel):
    """Vollstaendige Command Center Response."""

    # KPI-Widgets (Top-Row)
    kpis: List[KPIWidget] = Field(
        default_factory=list,
        description="KPI-Widgets fuer die obere Reihe",
    )

    # Priorisierte Aufgaben (Hauptbereich)
    tasks: List[TaskItem] = Field(
        default_factory=list,
        description="Priorisierte Tages-Aufgaben",
    )
    task_progress: CommandCenterProgress = Field(
        default_factory=lambda: CommandCenterProgress(
            completed=0, total=0, percentage=0.0
        ),
    )

    # Proaktive Insights (Sidebar)
    insights: List[ProactiveInsight] = Field(
        default_factory=list,
        description="Proaktive Warnungen und Empfehlungen",
    )

    # Alerts (Badge-Zaehler)
    alerts: List[AlertItem] = Field(
        default_factory=list,
        description="Aktive Warnungen",
    )
    alert_count: int = Field(0, description="Gesamtzahl aktiver Alerts")

    # Cashflow-Sparkline
    cashflow: List[CashflowPoint] = Field(
        default_factory=list,
        description="Cashflow-Daten fuer Sparkline",
    )

    # Meta
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    ai_status: str = Field(
        "operational", description="KI-Status: operational, degraded, offline"
    )


# =============================================================================
# DATA AGGREGATION
# =============================================================================


async def _build_kpis(
    db: AsyncSession,
    company_id: UUID,
) -> List[KPIWidget]:
    """Baut KPI-Widgets aus verschiedenen Quellen."""
    kpis: List[KPIWidget] = []

    try:
        # Offene Rechnungen
        result = await db.execute(
            select(
                func.count(Document.id),
            ).where(
                and_(
                    Document.company_id == company_id,
                    Document.document_type == "invoice",
                    Document.status.in_(["pending", "processing"]),
                    Document.deleted_at.is_(None),
                )
            )
        )
        open_invoices = result.scalar() or 0
        kpis.append(KPIWidget(
            id="open_invoices",
            label="Offene Rechnungen",
            value=str(open_invoices),
            raw_value=float(open_invoices),
            unit="Stueck",
            variant="warning" if open_invoices > 10 else "default",
            icon="FileText",
        ))

        # Dokumente heute
        from datetime import date

        today_start = datetime.combine(date.today(), datetime.min.time())
        result = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.created_at >= today_start,
                    Document.deleted_at.is_(None),
                )
            )
        )
        docs_today = result.scalar() or 0
        kpis.append(KPIWidget(
            id="docs_today",
            label="Dokumente heute",
            value=str(docs_today),
            raw_value=float(docs_today),
            unit="Stueck",
            icon="Upload",
        ))

        # Gesamtdokumente
        result = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.deleted_at.is_(None),
                )
            )
        )
        total_docs = result.scalar() or 0
        kpis.append(KPIWidget(
            id="total_docs",
            label="Dokumente gesamt",
            value=f"{total_docs:,}".replace(",", "."),
            raw_value=float(total_docs),
            unit="Stueck",
            icon="Database",
        ))

        # Auto-Verarbeitungsrate
        auto_count_result = await db.execute(
            select(func.count(Document.id)).where(
                and_(
                    Document.company_id == company_id,
                    Document.status == "completed",
                    Document.deleted_at.is_(None),
                )
            )
        )
        auto_count = auto_count_result.scalar() or 0
        rate = (auto_count / total_docs * 100) if total_docs > 0 else 0
        kpis.append(KPIWidget(
            id="auto_rate",
            label="Auto-Verarbeitung",
            value=f"{rate:.0f}%",
            raw_value=rate,
            unit="%",
            variant="success" if rate > 80 else "warning" if rate > 50 else "danger",
            icon="Zap",
        ))

    except Exception as e:
        logger.warning("kpi_build_partial_failure", error=str(e))

    return kpis


async def _build_tasks(
    db: AsyncSession,
    company_id: UUID,
    user_id: UUID,
) -> tuple[List[TaskItem], CommandCenterProgress]:
    """Baut die priorisierte Aufgabenliste."""
    tasks: List[TaskItem] = []

    try:
        from app.services.action_queue_service import (
            get_proactive_action_queue_service,
        )

        service = get_proactive_action_queue_service()
        queue_result = await service.get_today_actions(
            db=db, company_id=company_id, user_id=user_id,
        )

        # Prioritaets-Score (0-1) auf 1-5 Skala mappen
        def _score_to_priority(score: float) -> int:
            if score >= 0.8:
                return 1
            if score >= 0.6:
                return 2
            if score >= 0.4:
                return 3
            if score >= 0.2:
                return 4
            return 5

        for item in queue_result.items:
            if item.is_completed:
                continue
            tasks.append(TaskItem(
                id=str(item.id),
                title=item.title,
                description=item.description,
                priority=_score_to_priority(item.priority_score),
                action_type=item.action_type,
                category=item.action_type,
                due_date=item.deadline,
                financial_impact=item.financial_amount,
                action_route=item.source_url,
            ))

        progress = CommandCenterProgress(
            completed=queue_result.progress.completed,
            total=queue_result.progress.total,
            percentage=queue_result.progress.completion_rate * 100,
        )
        return tasks[:20], progress

    except Exception as e:
        logger.warning("tasks_build_failure", error=str(e))
        return tasks, CommandCenterProgress(
            completed=0, total=0, percentage=0.0,
        )


async def _build_insights(
    db: AsyncSession,
    company_id: UUID,
) -> List[ProactiveInsight]:
    """Sammelt proaktive Insights."""
    insights: List[ProactiveInsight] = []

    try:
        from app.services.insights.daily_insights_engine import (
            generate_all_insights_from_db,
            get_daily_insights_engine,
        )

        engine = get_daily_insights_engine()
        raw_insights = await generate_all_insights_from_db(
            engine=engine, db=db, company_id=company_id,
        )

        for ins in raw_insights[:10]:
            insights.append(ProactiveInsight(
                id=str(ins.id),
                severity=ins.severity.value if hasattr(ins.severity, "value") else str(ins.severity),
                title=ins.title,
                description=ins.summary or ins.detail or "",
                category=ins.insight_type.value if hasattr(ins.insight_type, "value") else str(ins.insight_type),
                action_label=ins.primary_action_label,
                action_route=ins.primary_action_url,
                created_at=ins.created_at.isoformat() if ins.created_at else datetime.now(timezone.utc).isoformat(),
            ))

    except Exception as e:
        logger.warning("insights_build_failure", error=str(e))

    return insights


async def _build_alerts(
    db: AsyncSession,
    company_id: UUID,
) -> List[AlertItem]:
    """Sammelt aktive Alerts aus der Anomalie-Tabelle."""
    alerts: List[AlertItem] = []

    try:
        from app.db.models_anomaly import Anomaly

        result = await db.execute(
            select(Anomaly).where(
                and_(
                    Anomaly.company_id == company_id,
                    Anomaly.status.in_(["open", "investigating"]),
                )
            ).order_by(Anomaly.created_at.desc()).limit(10)
        )
        anomalies = result.scalars().all()

        for a in anomalies:
            alerts.append(AlertItem(
                id=str(a.id),
                severity=a.severity,
                title=a.title,
                source="anomaly",
                created_at=a.created_at.isoformat() if a.created_at else "",
            ))

    except Exception as e:
        logger.warning("alerts_build_failure", error=str(e))

    return alerts


# =============================================================================
# ENDPOINTS
# =============================================================================


@router.get(
    "",
    response_model=CommandCenterResponse,
    summary="Command Center Startseite",
    description=(
        "Aggregiert alle Daten fuer die Command-Center Startansicht. "
        "Laeuft parallel fuer minimale Latenz."
    ),
)
async def get_command_center(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CommandCenterResponse:
    """
    Vollstaendige Command Center Daten.

    Aggregiert parallel:
    - KPI-Widgets (Offene Rechnungen, Dokumente, Auto-Rate)
    - Priorisierte Aufgaben (Action Queue)
    - Proaktive Insights (Daily Insights)
    - Aktive Alerts (Anomalien)

    Returns:
        CommandCenterResponse mit allen Startseiten-Daten
    """
    start = time.perf_counter()
    company_id = current_user.company_id

    # Parallele Datenabfrage fuer minimale Latenz
    kpis_task = _build_kpis(db, company_id)
    tasks_task = _build_tasks(db, company_id, current_user.id)
    insights_task = _build_insights(db, company_id)
    alerts_task = _build_alerts(db, company_id)

    kpis, (tasks, progress), insights, alerts = await asyncio.gather(
        kpis_task,
        tasks_task,
        insights_task,
        alerts_task,
    )

    # AI-Status pruefen
    ai_status = "operational"
    try:
        from app.core.llm_provider import get_llm_registry

        registry = get_llm_registry()
        default = registry.default
        if not await default.is_available():
            ai_status = "degraded"
    except Exception:
        ai_status = "offline"

    duration = time.perf_counter() - start
    _CC_REQUEST.labels(endpoint="full", status="success").inc()
    _CC_DURATION.labels(endpoint="full").observe(duration)

    logger.info(
        "command_center_served",
        company_id=str(company_id),
        kpi_count=len(kpis),
        task_count=len(tasks),
        insight_count=len(insights),
        alert_count=len(alerts),
        duration_ms=round(duration * 1000, 1),
    )

    return CommandCenterResponse(
        kpis=kpis,
        tasks=tasks,
        task_progress=progress,
        insights=insights,
        alerts=alerts,
        alert_count=len(alerts),
        ai_status=ai_status,
    )


@router.get(
    "/kpis",
    response_model=List[KPIWidget],
    summary="Nur KPI-Widgets",
)
async def get_kpis(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[KPIWidget]:
    """Liefert nur die KPI-Widgets fuer schnelles Polling."""
    return await _build_kpis(db, current_user.company_id)


@router.get(
    "/tasks",
    response_model=List[TaskItem],
    summary="Nur priorisierte Aufgaben",
)
async def get_tasks(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
) -> List[TaskItem]:
    """Liefert nur die priorisierte Aufgabenliste."""
    tasks, _ = await _build_tasks(db, current_user.company_id, current_user.id)
    return tasks[:limit]


@router.get(
    "/insights",
    response_model=List[ProactiveInsight],
    summary="Nur proaktive Insights",
)
async def get_insights(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[ProactiveInsight]:
    """Liefert nur proaktive Insights/Warnungen."""
    return await _build_insights(db, current_user.company_id)


@router.get(
    "/alerts",
    response_model=List[AlertItem],
    summary="Nur aktive Alerts",
)
async def get_alerts(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> List[AlertItem]:
    """Liefert nur aktive Alerts/Anomalien."""
    return await _build_alerts(db, current_user.company_id)
