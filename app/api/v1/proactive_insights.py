# -*- coding: utf-8 -*-
"""
Proactive Insights API Endpoints.

Enterprise Feature: Proaktive Intelligenz (Phase 6).

Endpoints:
- GET  /insights/all                  - Alle proaktiven Insights abrufen
- GET  /insights/deadlines            - Deadline-Warnungen
- GET  /insights/anomalies            - Anomalie-Alerts
- GET  /insights/workflow             - Workflow-Optimierungen
- GET  /insights/data-quality         - Datenqualitaets-Insights
- GET  /insights/summary              - Zusammenfassung aller Insights
- POST /insights/{id}/feedback        - Feedback zu Insight geben
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User
from app.core.safe_errors import safe_error_log
from app.services.orchestration.proactive_insights_service import (
    get_proactive_insights_service,
    InsightPriority,
    InsightType,
    ProactiveInsight,
)
from app.services.orchestration.deadline_insights_service import (
    get_deadline_insights_service,
)
from app.services.orchestration.anomaly_insights_service import (
    get_anomaly_insights_service,
)
from app.services.orchestration.workflow_insights_service import (
    get_workflow_insights_service,
)
from app.services.orchestration.data_enrichment_insights_service import (

    get_data_enrichment_insights_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/insights", tags=["Proactive Insights"])


# =============================================================================
# Pydantic Schemas
# =============================================================================

class RelatedEntityResponse(BaseModel):
    """Eine mit dem Insight verbundene Entitaet."""
    entity_type: str = Field(..., description="Typ der Entitaet")
    entity_id: Optional[str] = Field(None, description="ID der Entitaet")
    entity_name: str = Field(..., description="Name der Entitaet")
    confidence: float = Field(..., description="Konfidenz (0-1)")


class InsightResponse(BaseModel):
    """Ein proaktiver Insight."""
    id: str = Field(..., description="Insight-ID")
    insight_type: str = Field(..., description="Typ des Insights")
    priority: str = Field(..., description="Prioritaet (critical, high, medium, low)")
    title: str = Field(..., description="Titel des Insights")
    message: str = Field(..., description="Hauptnachricht")
    detail: str = Field(default="", description="Zusaetzliche Details")
    related_entities: List[RelatedEntityResponse] = Field(
        default=[], description="Verbundene Entitaeten"
    )
    potential_value: Optional[float] = Field(None, description="Potenzieller Wert in EUR")
    action_url: Optional[str] = Field(None, description="URL fuer Aktion")
    action_label: Optional[str] = Field(None, description="Label fuer Aktion")
    expires_at: Optional[str] = Field(None, description="Ablaufzeitpunkt")
    source_rule: Optional[str] = Field(None, description="Quellregel")
    confidence: float = Field(default=1.0, description="Konfidenz des Insights")
    created_at: str = Field(..., description="Erstellungszeitpunkt")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "insight_type": "reminder",
            "priority": "high",
            "title": "Skonto-Frist in 2 Tagen",
            "message": "Bei Zahlung bis 25.01.2026 sparen Sie 2% (50 EUR).",
            "detail": "Rechnung: R-2026-001, Lieferant: Mueller GmbH",
            "potential_value": 50.0,
            "action_url": "/invoices/123",
            "action_label": "Jetzt bezahlen",
            "source_rule": "skonto_expiring",
            "confidence": 0.95,
            "created_at": "2026-01-21T10:00:00Z",
        }
    })


class InsightListResponse(BaseModel):
    """Liste von Insights mit Metadaten."""
    insights: List[InsightResponse] = Field(..., description="Liste der Insights")
    total_count: int = Field(..., description="Gesamtanzahl")
    by_priority: Dict[str, int] = Field(
        default_factory=dict, description="Anzahl nach Prioritaet"
    )
    by_type: Dict[str, int] = Field(
        default_factory=dict, description="Anzahl nach Typ"
    )


class InsightSummaryResponse(BaseModel):
    """Zusammenfassung aller Insights."""
    total_insights: int = Field(..., description="Gesamtanzahl Insights")
    critical_count: int = Field(default=0, description="Kritische Insights")
    high_count: int = Field(default=0, description="Hohe Prioritaet")
    medium_count: int = Field(default=0, description="Mittlere Prioritaet")
    low_count: int = Field(default=0, description="Niedrige Prioritaet")
    by_category: Dict[str, int] = Field(
        default_factory=dict, description="Anzahl nach Kategorie"
    )
    total_potential_value: float = Field(
        default=0.0, description="Gesamtes Einsparpotenzial in EUR"
    )
    data_quality_score: Optional[float] = Field(
        None, description="Datenqualitaets-Score (0-100)"
    )


class FeedbackRequest(BaseModel):
    """Feedback zu einem Insight."""
    was_helpful: bool = Field(..., description="War der Insight hilfreich?")
    comment: Optional[str] = Field(
        None, max_length=500, description="Optionaler Kommentar"
    )


class FeedbackResponse(BaseModel):
    """Antwort auf Feedback."""
    success: bool = Field(..., description="Feedback erfolgreich gespeichert")
    message: str = Field(..., description="Bestaetigung")


class DataQualitySummaryResponse(BaseModel):
    """Zusammenfassung der Datenqualitaet."""
    quality_score: float = Field(..., description="Qualitaets-Score (0-100)")
    grade: str = Field(..., description="Note (A-F)")
    total_issues: int = Field(..., description="Gesamtanzahl Probleme")
    by_type: Dict[str, int] = Field(
        default_factory=dict, description="Probleme nach Typ"
    )
    by_severity: Dict[str, int] = Field(
        default_factory=dict, description="Probleme nach Schweregrad"
    )


# =============================================================================
# Helper Functions
# =============================================================================

def _insight_to_response(insight: ProactiveInsight) -> InsightResponse:
    """Konvertiert ProactiveInsight zu Response-Schema."""
    return InsightResponse(
        id=str(insight.id),
        insight_type=insight.insight_type.value,
        priority=insight.priority.value,
        title=insight.title,
        message=insight.message,
        detail=insight.detail,
        related_entities=[
            RelatedEntityResponse(
                entity_type=e.entity_type.value,
                entity_id=str(e.entity_id) if e.entity_id else None,
                entity_name=e.entity_name,
                confidence=e.confidence,
            )
            for e in insight.related_entities
        ],
        potential_value=float(insight.potential_value) if insight.potential_value else None,
        action_url=insight.action_url,
        action_label=insight.action_label,
        expires_at=insight.expires_at.isoformat() if insight.expires_at else None,
        source_rule=insight.source_rule,
        confidence=insight.confidence,
        created_at=insight.created_at.isoformat(),
    )


def _count_by_priority(insights: List[ProactiveInsight]) -> Dict[str, int]:
    """Zaehlt Insights nach Prioritaet."""
    counts: Dict[str, int] = {}
    for insight in insights:
        key = insight.priority.value
        counts[key] = counts.get(key, 0) + 1
    return counts


def _count_by_type(insights: List[ProactiveInsight]) -> Dict[str, int]:
    """Zaehlt Insights nach Typ."""
    counts: Dict[str, int] = {}
    for insight in insights:
        key = insight.source_rule or insight.insight_type.value
        counts[key] = counts.get(key, 0) + 1
    return counts


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "/all",
    response_model=InsightListResponse,
    summary="Alle proaktiven Insights",
    description="Ruft alle proaktiven Insights fuer den aktuellen Benutzer ab.",
)
@limiter.limit("30/minute")
async def get_all_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days_ahead: int = Query(14, ge=1, le=90, description="Tage in die Zukunft"),
    max_insights: int = Query(50, ge=1, le=100, description="Maximale Anzahl"),
    priority: Optional[str] = Query(None, description="Filter nach Prioritaet"),
) -> InsightListResponse:
    """
    Ruft alle proaktiven Insights ab.

    Kombiniert Insights aus allen Kategorien:
    - Deadlines (Skonto, Vertraege, Zahlungen)
    - Anomalien (Preise, Volumen, Muster)
    - Workflow (Genehmigungen, Bottlenecks)
    - Datenqualitaet (Fehlende Daten, Duplikate)
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    logger.info(
        "fetching_all_insights",
        user_id=str(current_user.id),
        company_id=str(company_id),
        days_ahead=days_ahead,
    )

    all_insights: List[ProactiveInsight] = []

    # Parallel alle Insight-Services abrufen
    try:
        deadline_service = get_deadline_insights_service()
        anomaly_service = get_anomaly_insights_service()
        workflow_service = get_workflow_insights_service()
        data_service = get_data_enrichment_insights_service()

        deadline_insights = await deadline_service.check_all_deadlines(
            db, company_id, days_ahead
        )
        anomaly_insights = await anomaly_service.check_all_anomalies(db, company_id)
        workflow_insights = await workflow_service.check_all_workflow_insights(
            db, company_id, current_user.id
        )
        data_insights = await data_service.check_all_data_issues(db, company_id)

        all_insights.extend(deadline_insights)
        all_insights.extend(anomaly_insights)
        all_insights.extend(workflow_insights)
        all_insights.extend(data_insights)

    except Exception as e:
        logger.warning(
            "insight_fetch_partial_failure",
            **safe_error_log(e),
        )

    # Filter nach Prioritaet
    if priority:
        all_insights = [
            i for i in all_insights
            if i.priority.value == priority
        ]

    # Sortieren nach Prioritaet
    priority_order = {
        InsightPriority.CRITICAL: 0,
        InsightPriority.HIGH: 1,
        InsightPriority.MEDIUM: 2,
        InsightPriority.LOW: 3,
    }
    all_insights.sort(key=lambda i: priority_order.get(i.priority, 4))

    # Limitieren
    limited_insights = all_insights[:max_insights]

    return InsightListResponse(
        insights=[_insight_to_response(i) for i in limited_insights],
        total_count=len(all_insights),
        by_priority=_count_by_priority(all_insights),
        by_type=_count_by_type(all_insights),
    )


@router.get(
    "/deadlines",
    response_model=InsightListResponse,
    summary="Deadline-Warnungen",
    description="Ruft Insights zu ablaufenden Fristen ab.",
)
@limiter.limit("30/minute")
async def get_deadline_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    days_ahead: int = Query(14, ge=1, le=90, description="Tage in die Zukunft"),
) -> InsightListResponse:
    """
    Ruft Deadline-Warnungen ab.

    Kategorien:
    - Skonto-Fristen
    - Vertrags-Kuendigungsfristen
    - Zahlungsfristen
    - Aufbewahrungsfristen
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_deadline_insights_service()
    insights = await service.check_all_deadlines(db, company_id, days_ahead)

    return InsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_priority=_count_by_priority(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/anomalies",
    response_model=InsightListResponse,
    summary="Anomalie-Alerts",
    description="Ruft erkannte Anomalien ab.",
)
@limiter.limit("30/minute")
async def get_anomaly_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InsightListResponse:
    """
    Ruft Anomalie-Alerts ab.

    Kategorien:
    - Preisanomalien
    - Volumenanomalien
    - Rechnungsmuster-Anomalien
    - Duplikat-Muster
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_anomaly_insights_service()
    insights = await service.check_all_anomalies(db, company_id)

    return InsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_priority=_count_by_priority(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/workflow",
    response_model=InsightListResponse,
    summary="Workflow-Optimierungen",
    description="Ruft Workflow-Optimierungsvorschlaege ab.",
)
@limiter.limit("30/minute")
async def get_workflow_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InsightListResponse:
    """
    Ruft Workflow-Optimierungen ab.

    Kategorien:
    - Batch-Genehmigungsvorschlaege
    - Bottleneck-Erkennung
    - Automatisierungsvorschlaege
    - Veraltete Elemente
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_workflow_insights_service()
    insights = await service.check_all_workflow_insights(
        db, company_id, current_user.id
    )

    return InsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_priority=_count_by_priority(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/data-quality",
    response_model=InsightListResponse,
    summary="Datenqualitaets-Insights",
    description="Ruft Insights zur Datenqualitaet ab.",
)
@limiter.limit("30/minute")
async def get_data_quality_insights(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InsightListResponse:
    """
    Ruft Datenqualitaets-Insights ab.

    Kategorien:
    - Fehlende Stammdaten
    - Potenzielle Duplikate
    - Inkonsistenzen
    - Veraltete Daten
    - Nicht verknuepfte Dokumente
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_data_enrichment_insights_service()
    insights = await service.check_all_data_issues(db, company_id)

    return InsightListResponse(
        insights=[_insight_to_response(i) for i in insights],
        total_count=len(insights),
        by_priority=_count_by_priority(insights),
        by_type=_count_by_type(insights),
    )


@router.get(
    "/data-quality/summary",
    response_model=DataQualitySummaryResponse,
    summary="Datenqualitaets-Zusammenfassung",
    description="Ruft eine Zusammenfassung der Datenqualitaet ab.",
)
@limiter.limit("30/minute")
async def get_data_quality_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DataQualitySummaryResponse:
    """
    Ruft die Zusammenfassung der Datenqualitaet ab.

    Enthaelt:
    - Qualitaets-Score (0-100)
    - Note (A-F)
    - Anzahl Issues nach Typ und Schweregrad
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    service = get_data_enrichment_insights_service()
    summary = await service.get_data_quality_summary(db, company_id)

    return DataQualitySummaryResponse(
        quality_score=summary.get("quality_score", 0),
        grade=summary.get("grade", "F"),
        total_issues=summary.get("total_issues", 0),
        by_type=summary.get("by_type", {}),
        by_severity=summary.get("by_severity", {}),
    )


@router.get(
    "/summary",
    response_model=InsightSummaryResponse,
    summary="Zusammenfassung aller Insights",
    description="Ruft eine Zusammenfassung aller proaktiven Insights ab.",
)
@limiter.limit("30/minute")
async def get_insights_summary(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> InsightSummaryResponse:
    """
    Ruft eine Zusammenfassung aller Insights ab.

    Enthaelt:
    - Gesamtanzahl
    - Anzahl nach Prioritaet
    - Gesamtes Einsparpotenzial
    - Datenqualitaets-Score
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer ist keiner Firma zugeordnet.",
        )

    # Insights sammeln
    all_insights: List[ProactiveInsight] = []

    try:
        deadline_service = get_deadline_insights_service()
        anomaly_service = get_anomaly_insights_service()
        workflow_service = get_workflow_insights_service()
        data_service = get_data_enrichment_insights_service()

        deadline_insights = await deadline_service.check_all_deadlines(db, company_id, 14)
        anomaly_insights = await anomaly_service.check_all_anomalies(db, company_id)
        workflow_insights = await workflow_service.check_all_workflow_insights(
            db, company_id, current_user.id
        )
        data_insights = await data_service.check_all_data_issues(db, company_id)
        data_quality = await data_service.get_data_quality_summary(db, company_id)

        all_insights.extend(deadline_insights)
        all_insights.extend(anomaly_insights)
        all_insights.extend(workflow_insights)
        all_insights.extend(data_insights)

    except Exception as e:
        logger.warning("insight_summary_partial_failure", **safe_error_log(e))
        data_quality = {"quality_score": None}

    # Zaehlen
    by_priority = _count_by_priority(all_insights)

    # Einsparpotenzial berechnen
    total_value = sum(
        float(i.potential_value)
        for i in all_insights
        if i.potential_value
    )

    # Nach Kategorie zaehlen
    by_category = {
        "deadlines": len(deadline_insights) if "deadline_insights" in dir() else 0,
        "anomalies": len(anomaly_insights) if "anomaly_insights" in dir() else 0,
        "workflow": len(workflow_insights) if "workflow_insights" in dir() else 0,
        "data_quality": len(data_insights) if "data_insights" in dir() else 0,
    }

    return InsightSummaryResponse(
        total_insights=len(all_insights),
        critical_count=by_priority.get("critical", 0),
        high_count=by_priority.get("high", 0),
        medium_count=by_priority.get("medium", 0),
        low_count=by_priority.get("low", 0),
        by_category=by_category,
        total_potential_value=total_value,
        data_quality_score=data_quality.get("quality_score"),
    )


@router.post(
    "/{insight_id}/feedback",
    response_model=FeedbackResponse,
    summary="Feedback zu Insight",
    description="Gibt Feedback zu einem Insight ab.",
)
@limiter.limit("60/minute")
async def post_insight_feedback(
    request: Request,
    insight_id: UUID = Path(..., description="ID des Insights"),
    feedback: FeedbackRequest = ...,
    current_user: User = Depends(get_current_active_user),
) -> FeedbackResponse:
    """
    Gibt Feedback zu einem Insight ab.

    Das Feedback wird genutzt um:
    - Die Relevanz von Insights zu verbessern
    - Weniger hilfreiche Insights seltener zu zeigen
    - Die Personalisierung zu optimieren
    """
    service = get_proactive_insights_service()

    await service.learn_from_feedback(
        insight_id=insight_id,
        was_helpful=feedback.was_helpful,
        user_id=current_user.id,
    )

    logger.info(
        "insight_feedback_received",
        insight_id=str(insight_id),
        user_id=str(current_user.id),
        was_helpful=feedback.was_helpful,
    )

    return FeedbackResponse(
        success=True,
        message="Vielen Dank fuer Ihr Feedback! Es hilft uns die Insights zu verbessern.",
    )
