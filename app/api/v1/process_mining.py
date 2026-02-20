# -*- coding: utf-8 -*-
"""
Process Mining API Endpoints.

Endpoints für Process Mining und Automatisierungsvorschläge:
- Event-Tracking und -Analyse
- Bottleneck-Erkennung
- Automatisierungsvorschläge
- Prozess-Metriken und -Visualisierung

Vision 2.0 Feature: Process Mining & Autonome Automatisierung
Feinpoliert und durchdacht.
"""

from datetime import datetime, date
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.db.models import User, Company
from app.db.models_process_mining import (
    ProcessEvent,
    AutomationSuggestion,
    ProcessMetric,
    EventType,
    ActorType,
    SuggestionStatus,
    SuggestionType,
)
from app.services.process_mining.event_tracker import ProcessEventTracker as EventTracker
from app.services.process_mining.bottleneck_detector import BottleneckDetector
from app.services.process_mining.automation_suggester import AutomationSuggester
from app.services.process_mining.process_discovery_service import ProcessDiscoveryService

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/process-mining", tags=["Process Mining"])


# =============================================================================
# Request/Response Schemas
# =============================================================================

class EventCreateRequest(BaseModel):
    """Schema für Event-Erstellung."""
    document_id: Optional[UUID] = None
    entity_id: Optional[UUID] = None
    event_type: str = Field(..., description="Event-Typ (z.B. document_uploaded)")
    event_subtype: Optional[str] = None
    actor_type: str = Field(default="system", description="Akteur-Typ (system, user, automation)")
    duration_ms: Optional[int] = Field(None, ge=0, description="Dauer in Millisekunden")
    process_instance_id: Optional[str] = Field(None, max_length=100)
    activity_name: Optional[str] = Field(None, max_length=100)
    resource: Optional[str] = Field(None, max_length=100)
    success: bool = True
    error_message: Optional[str] = None
    metadata: Optional[dict] = None


class EventResponse(BaseModel):
    """Schema für Event-Antwort."""
    id: UUID
    document_id: Optional[UUID]
    entity_id: Optional[UUID]
    event_type: str
    event_subtype: Optional[str]
    actor_type: str
    actor_id: Optional[UUID]
    timestamp: datetime
    duration_ms: Optional[int]
    time_since_previous_ms: Optional[int]
    process_instance_id: Optional[str]
    activity_name: Optional[str]
    resource: Optional[str]
    success: bool
    error_message: Optional[str]
    metadata: dict


class EventListResponse(BaseModel):
    """Paginierte Event-Liste."""
    items: List[EventResponse]
    total: int
    page: int
    per_page: int


class BottleneckResponse(BaseModel):
    """Schema für Bottleneck-Details."""
    type: str
    location: str
    score: float
    severity: str
    details: dict
    recommendation: str


class BottleneckAnalysisResponse(BaseModel):
    """Vollständige Bottleneck-Analyse."""
    bottlenecks: List[BottleneckResponse]
    overall_score: float
    overall_severity: str
    bottleneck_count: int
    period_days: int


class ProcessHealthResponse(BaseModel):
    """Prozessgesundheits-Score."""
    health_score: float
    health_grade: str
    components: dict
    bottleneck_count: int
    top_bottleneck: Optional[BottleneckResponse]
    period_days: int


class SuggestionResponse(BaseModel):
    """Schema für Automatisierungsvorschlag."""
    id: UUID
    suggestion_type: str
    title: str
    description: Optional[str]
    pattern_description: Optional[str]
    confidence: float
    potential_savings_hours: Optional[float]
    potential_savings_cost: Optional[float]
    affected_steps: List[str]
    trigger_conditions: dict
    suggested_actions: List[dict]
    frequency_per_week: Optional[int]
    status: str
    activated_at: Optional[datetime]
    rejected_at: Optional[datetime]
    rejection_reason: Optional[str]
    created_at: Optional[datetime]


class SuggestionListResponse(BaseModel):
    """Liste von Vorschlägen."""
    items: List[SuggestionResponse]
    total: int


class SuggestionActivateRequest(BaseModel):
    """Request für Vorschlags-Aktivierung."""
    # Optional: Parameter für die erstellte Automatisierungsregel
    rule_name: Optional[str] = None
    rule_priority: int = Field(default=50, ge=1, le=100)


class SuggestionRejectRequest(BaseModel):
    """Request für Vorschlags-Ablehnung."""
    reason: Optional[str] = Field(None, max_length=500)


class MetricResponse(BaseModel):
    """Schema für Prozess-Metrik."""
    id: UUID
    metric_date: date
    metric_type: str
    process_name: Optional[str]
    activity_name: Optional[str]
    event_count: int
    success_count: int
    failure_count: int
    avg_duration_ms: Optional[int]
    min_duration_ms: Optional[int]
    max_duration_ms: Optional[int]
    p50_duration_ms: Optional[int]
    p95_duration_ms: Optional[int]
    manual_action_count: int
    automated_action_count: int
    bottleneck_score: Optional[float]
    automation_rate: float


class FlowDiagramResponse(BaseModel):
    """Prozessfluss-Daten für Visualisierung."""
    nodes: List[dict]
    edges: List[dict]
    variants: List[dict]
    statistics: dict


class HeatmapResponse(BaseModel):
    """Heatmap-Daten."""
    data: List[dict]
    period_days: int


class SuggestionStatsResponse(BaseModel):
    """Vorschlags-Statistiken."""
    by_status: dict
    total_pending: int
    total_activated: int
    realized_savings_hours: float
    realized_savings_cost: float


# =============================================================================
# Helper Functions
# =============================================================================

def _event_to_response(event: ProcessEvent) -> EventResponse:
    """Konvertiere Event-Model zu Response."""
    return EventResponse(
        id=event.id,
        document_id=event.document_id,
        entity_id=event.entity_id,
        event_type=event.event_type,
        event_subtype=event.event_subtype,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        timestamp=event.timestamp,
        duration_ms=event.duration_ms,
        time_since_previous_ms=event.time_since_previous_ms,
        process_instance_id=event.process_instance_id,
        activity_name=event.activity_name,
        resource=event.resource,
        success=event.success,
        error_message=event.error_message,
        metadata=event.metadata or {},
    )


def _suggestion_to_response(suggestion: AutomationSuggestion) -> SuggestionResponse:
    """Konvertiere Vorschlag-Model zu Response."""
    return SuggestionResponse(
        id=suggestion.id,
        suggestion_type=suggestion.suggestion_type,
        title=suggestion.title,
        description=suggestion.description,
        pattern_description=suggestion.pattern_description,
        confidence=float(suggestion.confidence) if suggestion.confidence else 0,
        potential_savings_hours=float(suggestion.potential_savings_hours) if suggestion.potential_savings_hours else None,
        potential_savings_cost=float(suggestion.potential_savings_cost) if suggestion.potential_savings_cost else None,
        affected_steps=suggestion.affected_steps or [],
        trigger_conditions=suggestion.trigger_conditions or {},
        suggested_actions=suggestion.suggested_actions or [],
        frequency_per_week=suggestion.frequency_per_week,
        status=suggestion.status,
        activated_at=suggestion.activated_at,
        rejected_at=suggestion.rejected_at,
        rejection_reason=suggestion.rejection_reason,
        created_at=suggestion.created_at,
    )


def _metric_to_response(metric: ProcessMetric) -> MetricResponse:
    """Konvertiere Metrik-Model zu Response."""
    data = metric.to_dict()
    return MetricResponse(**data)


# =============================================================================
# Event Endpoints
# =============================================================================

@router.post("/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    data: EventCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> EventResponse:
    """
    Erstelle ein neues Prozess-Event.

    Wird automatisch für Tracking verwendet, kann aber auch manuell aufgerufen werden.
    Events werden für Process Mining und Analyse verwendet.
    """
    # Validiere Event-Typ
    valid_event_types = [e.value for e in EventType]
    if data.event_type not in valid_event_types:
        logger.warning(f"Unbekannter Event-Typ: {data.event_type}")
        # Erlauben wir auch unbekannte Typen für Erweiterbarkeit

    tracker = EventTracker(db)

    event = await tracker.track_event(
        company_id=company.company_id,
        event_type=data.event_type,
        document_id=data.document_id,
        entity_id=data.entity_id,
        actor_type=data.actor_type,
        actor_id=current_user.id if data.actor_type == ActorType.USER.value else None,
        duration_ms=data.duration_ms,
        process_instance_id=data.process_instance_id,
        activity_name=data.activity_name,
        resource=data.resource,
        success=data.success,
        error_message=data.error_message,
        metadata=data.metadata,
    )

    logger.info(
        "Process event created",
        event_id=str(event.id),
        event_type=data.event_type,
        company_id=str(company.company_id),
    )

    return _event_to_response(event)


@router.get("/events", response_model=EventListResponse)
async def list_events(
    document_id: Optional[UUID] = Query(None, description="Filter nach Dokument"),
    entity_id: Optional[UUID] = Query(None, description="Filter nach Entity"),
    event_type: Optional[str] = Query(None, description="Filter nach Event-Typ"),
    actor_type: Optional[str] = Query(None, description="Filter nach Akteur-Typ"),
    success: Optional[bool] = Query(None, description="Filter nach Erfolg"),
    date_from: Optional[datetime] = Query(None, description="Startdatum"),
    date_to: Optional[datetime] = Query(None, description="Enddatum"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(50, ge=1, le=500, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> EventListResponse:
    """
    Liste alle Prozess-Events mit Filteroptionen.

    Unterstützte Filter:
    - document_id: Nur Events für ein bestimmtes Dokument
    - entity_id: Nur Events für eine bestimmte Entity
    - event_type: Nur bestimmter Event-Typ
    - actor_type: Nur bestimmter Akteur-Typ (system, user, automation)
    - success: Nur erfolgreiche/fehlgeschlagene Events
    - date_from/date_to: Zeitraum-Filter
    """
    from sqlalchemy import select, and_, func, desc

    # Basisquery
    query = select(ProcessEvent).where(ProcessEvent.company_id == company.company_id)
    count_query = select(func.count(ProcessEvent.id)).where(ProcessEvent.company_id == company.company_id)

    # Filter anwenden
    filters = []

    if document_id:
        filters.append(ProcessEvent.document_id == document_id)
    if entity_id:
        filters.append(ProcessEvent.entity_id == entity_id)
    if event_type:
        filters.append(ProcessEvent.event_type == event_type)
    if actor_type:
        filters.append(ProcessEvent.actor_type == actor_type)
    if success is not None:
        filters.append(ProcessEvent.success == success)
    if date_from:
        filters.append(ProcessEvent.timestamp >= date_from)
    if date_to:
        filters.append(ProcessEvent.timestamp <= date_to)

    if filters:
        query = query.where(and_(*filters))
        count_query = count_query.where(and_(*filters))

    # Zaehlen
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginieren und sortieren
    query = query.order_by(desc(ProcessEvent.timestamp)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    events = list(result.scalars().all())

    return EventListResponse(
        items=[_event_to_response(e) for e in events],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/events/{event_id}", response_model=EventResponse)
async def get_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> EventResponse:
    """
    Einzelnes Event abrufen.
    """
    from sqlalchemy import select, and_

    result = await db.execute(
        select(ProcessEvent).where(
            and_(
                ProcessEvent.id == event_id,
                ProcessEvent.company_id == company.company_id,
            )
        )
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event nicht gefunden",
        )

    return _event_to_response(event)


@router.get("/events/document/{document_id}/timeline", response_model=List[EventResponse])
async def get_document_timeline(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[EventResponse]:
    """
    Vollständige Event-Timeline für ein Dokument.

    Chronologisch sortiert, zeigt den kompletten Lebenszyklus.
    """
    from sqlalchemy import select, and_, asc

    result = await db.execute(
        select(ProcessEvent)
        .where(
            and_(
                ProcessEvent.document_id == document_id,
                ProcessEvent.company_id == company.company_id,
            )
        )
        .order_by(asc(ProcessEvent.timestamp))
    )
    events = list(result.scalars().all())

    return [_event_to_response(e) for e in events]


# =============================================================================
# Bottleneck Endpoints
# =============================================================================

@router.get("/bottlenecks", response_model=BottleneckAnalysisResponse)
async def get_bottlenecks(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> BottleneckAnalysisResponse:
    """
    Erkenne Prozess-Engpaesse.

    Analysiert:
    - Durchlaufzeiten pro Schritt
    - Warteschlangen und Staus
    - Fehlerraten
    - Ressourcen-Engpaesse (manuelle Aktionen)

    Liefert Empfehlungen zur Optimierung.
    """
    detector = BottleneckDetector(db)
    result = await detector.detect_bottlenecks(
        company_id=company.company_id,
        days=days,
    )

    return BottleneckAnalysisResponse(
        bottlenecks=[
            BottleneckResponse(**b) for b in result["bottlenecks"]
        ],
        overall_score=result["overall_score"],
        overall_severity=result["overall_severity"],
        bottleneck_count=result["bottleneck_count"],
        period_days=result["period_days"],
    )


@router.get("/bottlenecks/heatmap", response_model=HeatmapResponse)
async def get_bottleneck_heatmap(
    days: int = Query(7, ge=1, le=30, description="Analysezeitraum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> HeatmapResponse:
    """
    Heatmap-Daten für Bottleneck-Visualisierung.

    Zeigt Lastverteilung nach Wochentag und Stunde.
    """
    detector = BottleneckDetector(db)
    result = await detector.get_bottleneck_heatmap(
        company_id=company.company_id,
        days=days,
    )

    return HeatmapResponse(
        data=result["data"],
        period_days=result["period_days"],
    )


@router.get("/health", response_model=ProcessHealthResponse)
async def get_process_health(
    days: int = Query(30, ge=1, le=365, description="Analysezeitraum"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ProcessHealthResponse:
    """
    Berechne Gesamt-Prozessgesundheit.

    Kombiniert:
    - Bottleneck-Score (40%)
    - Erfolgsrate (40%)
    - Automatisierungsgrad (20%)

    Liefert Note A-F und Details.
    """
    detector = BottleneckDetector(db)
    result = await detector.calculate_process_health(
        company_id=company.company_id,
        days=days,
    )

    top_bottleneck = None
    if result.get("top_bottleneck"):
        top_bottleneck = BottleneckResponse(**result["top_bottleneck"])

    return ProcessHealthResponse(
        health_score=result["health_score"],
        health_grade=result["health_grade"],
        components=result["components"],
        bottleneck_count=result["bottleneck_count"],
        top_bottleneck=top_bottleneck,
        period_days=result["period_days"],
    )


# =============================================================================
# Automation Suggestion Endpoints
# =============================================================================

@router.get("/suggestions", response_model=SuggestionListResponse)
async def list_suggestions(
    status_filter: Optional[str] = Query(
        None,
        alias="status",
        description="Filter nach Status (pending, activated, rejected)",
    ),
    suggestion_type: Optional[str] = Query(None, description="Filter nach Vorschlags-Typ"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Mindest-Confidence"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SuggestionListResponse:
    """
    Liste Automatisierungsvorschläge.

    Vorschläge werden basierend auf Process Mining generiert und
    zeigen potenzielle Automatisierungsmöglichkeiten.
    """
    from sqlalchemy import select, and_, desc

    query = select(AutomationSuggestion).where(
        AutomationSuggestion.company_id == company.company_id
    )

    filters = []
    if status_filter:
        filters.append(AutomationSuggestion.status == status_filter)
    if suggestion_type:
        filters.append(AutomationSuggestion.suggestion_type == suggestion_type)
    if min_confidence > 0:
        filters.append(AutomationSuggestion.confidence >= min_confidence)

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(desc(AutomationSuggestion.potential_savings_hours)).limit(limit)

    result = await db.execute(query)
    suggestions = list(result.scalars().all())

    return SuggestionListResponse(
        items=[_suggestion_to_response(s) for s in suggestions],
        total=len(suggestions),
    )


@router.post("/suggestions/generate", response_model=SuggestionListResponse)
async def generate_suggestions(
    days: int = Query(30, ge=7, le=90, description="Analysezeitraum"),
    save: bool = Query(True, description="Vorschläge speichern"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SuggestionListResponse:
    """
    Generiere neue Automatisierungsvorschläge.

    Analysiert manuelle Aktionen und identifiziert:
    - Wiederkehrende Klassifikations-Korrekturen
    - Routing-Muster
    - Freigabe-Muster
    - Entity-Linking Verbesserungen
    - Workflow-Optimierungen

    Berechnet ROI (Stunden/Kosten) für jeden Vorschlag.
    """
    suggester = AutomationSuggester(db)

    # Generiere Vorschläge
    suggestions_data = await suggester.generate_suggestions(
        company_id=company.company_id,
        days=days,
    )

    if save and suggestions_data:
        saved = await suggester.save_suggestions(
            company_id=company.company_id,
            suggestions=suggestions_data,
        )
        await db.commit()

        logger.info(
            "Generated automation suggestions",
            count=len(saved),
            company_id=str(company.company_id),
        )

        return SuggestionListResponse(
            items=[_suggestion_to_response(s) for s in saved],
            total=len(saved),
        )

    # Ohne Speichern: direkte Rückgabe
    return SuggestionListResponse(
        items=[
            SuggestionResponse(
                id=UUID("00000000-0000-0000-0000-000000000000"),
                **s,
                status=SuggestionStatus.PENDING.value,
                activated_at=None,
                rejected_at=None,
                rejection_reason=None,
                created_at=None,
            )
            for s in suggestions_data
        ],
        total=len(suggestions_data),
    )


@router.get("/suggestions/{suggestion_id}", response_model=SuggestionResponse)
async def get_suggestion(
    suggestion_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SuggestionResponse:
    """
    Einzelnen Vorschlag abrufen.
    """
    from sqlalchemy import select, and_

    result = await db.execute(
        select(AutomationSuggestion).where(
            and_(
                AutomationSuggestion.id == suggestion_id,
                AutomationSuggestion.company_id == company.company_id,
            )
        )
    )
    suggestion = result.scalar_one_or_none()

    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorschlag nicht gefunden",
        )

    return _suggestion_to_response(suggestion)


@router.post("/suggestions/{suggestion_id}/activate", response_model=SuggestionResponse)
async def activate_suggestion(
    suggestion_id: UUID,
    data: SuggestionActivateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SuggestionResponse:
    """
    Automatisierungsvorschlag aktivieren.

    Erstellt eine Automatisierungsregel basierend auf dem Vorschlag.
    """
    suggester = AutomationSuggester(db)

    suggestion = await suggester.activate_suggestion(
        suggestion_id=suggestion_id,
        user_id=current_user.id,
    )

    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorschlag nicht gefunden",
        )

    # Verifiziere Company-Zugehoerigkeit
    if suggestion.company_id != company.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert",
        )

    await db.commit()

    logger.info(
        "Automation suggestion activated",
        suggestion_id=str(suggestion_id),
        user_id=str(current_user.id),
    )

    return _suggestion_to_response(suggestion)


@router.post("/suggestions/{suggestion_id}/reject", response_model=SuggestionResponse)
async def reject_suggestion(
    suggestion_id: UUID,
    data: SuggestionRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SuggestionResponse:
    """
    Automatisierungsvorschlag ablehnen.
    """
    suggester = AutomationSuggester(db)

    suggestion = await suggester.reject_suggestion(
        suggestion_id=suggestion_id,
        user_id=current_user.id,
        reason=data.reason,
    )

    if not suggestion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vorschlag nicht gefunden",
        )

    # Verifiziere Company-Zugehoerigkeit
    if suggestion.company_id != company.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff verweigert",
        )

    await db.commit()

    logger.info(
        "Automation suggestion rejected",
        suggestion_id=str(suggestion_id),
        reason=data.reason,
    )

    return _suggestion_to_response(suggestion)


@router.get("/suggestions/statistics", response_model=SuggestionStatsResponse)
async def get_suggestion_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> SuggestionStatsResponse:
    """
    Statistiken über Automatisierungsvorschläge.

    Zeigt:
    - Anzahl nach Status
    - Realisierte Einsparungen
    """
    suggester = AutomationSuggester(db)
    stats = await suggester.get_suggestion_statistics(company_id=company.company_id)

    return SuggestionStatsResponse(**stats)


# =============================================================================
# Metrics Endpoints
# =============================================================================

@router.get("/metrics", response_model=List[MetricResponse])
async def list_metrics(
    metric_type: Optional[str] = Query(None, description="Filter nach Metrik-Typ"),
    date_from: Optional[date] = Query(None, description="Startdatum"),
    date_to: Optional[date] = Query(None, description="Enddatum"),
    process_name: Optional[str] = Query(None, description="Filter nach Prozessname"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[MetricResponse]:
    """
    Liste Prozess-Metriken.

    Täglich aggregierte Statistiken für Dashboard und Reporting.
    """
    from sqlalchemy import select, and_, desc

    query = select(ProcessMetric).where(ProcessMetric.company_id == company.company_id)

    filters = []
    if metric_type:
        filters.append(ProcessMetric.metric_type == metric_type)
    if date_from:
        filters.append(ProcessMetric.metric_date >= date_from)
    if date_to:
        filters.append(ProcessMetric.metric_date <= date_to)
    if process_name:
        filters.append(ProcessMetric.process_name == process_name)

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(desc(ProcessMetric.metric_date)).limit(limit)

    result = await db.execute(query)
    metrics = list(result.scalars().all())

    return [_metric_to_response(m) for m in metrics]


@router.get("/metrics/summary", response_model=dict)
async def get_metrics_summary(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Zusammenfassung der Prozess-Metriken.

    Aggregiert Kennzahlen für das Dashboard:
    - Gesamtdokumente
    - Durchschnittliche Durchlaufzeit
    - Erfolgsrate
    - Automatisierungsgrad
    """
    from sqlalchemy import select, and_, func
    from datetime import timedelta

    since = datetime.utcnow() - timedelta(days=days)

    # Event-Statistiken
    event_stats = await db.execute(
        select(
            func.count(ProcessEvent.id).label("total_events"),
            func.count(ProcessEvent.id).filter(ProcessEvent.success == True).label("success_events"),
            func.count(ProcessEvent.id).filter(ProcessEvent.actor_type == ActorType.USER.value).label("manual_events"),
            func.avg(ProcessEvent.duration_ms).label("avg_duration"),
        )
        .where(
            and_(
                ProcessEvent.company_id == company.company_id,
                ProcessEvent.timestamp >= since,
            )
        )
    )
    stats = event_stats.one()

    total_events = stats.total_events or 0
    success_events = stats.success_events or 0
    manual_events = stats.manual_events or 0

    success_rate = success_events / total_events if total_events > 0 else 0
    automation_rate = 1 - (manual_events / total_events) if total_events > 0 else 0

    # Dokument-Statistiken
    doc_stats = await db.execute(
        select(func.count(func.distinct(ProcessEvent.document_id)))
        .where(
            and_(
                ProcessEvent.company_id == company.company_id,
                ProcessEvent.timestamp >= since,
                ProcessEvent.document_id.isnot(None),
            )
        )
    )
    unique_documents = doc_stats.scalar() or 0

    return {
        "period_days": days,
        "total_events": total_events,
        "unique_documents": unique_documents,
        "success_rate": round(success_rate, 4),
        "automation_rate": round(automation_rate, 4),
        "avg_duration_ms": int(stats.avg_duration) if stats.avg_duration else 0,
        "manual_events": manual_events,
        "automated_events": total_events - manual_events,
    }


# =============================================================================
# Process Flow Visualization Endpoints
# =============================================================================

@router.get("/flow-diagram", response_model=FlowDiagramResponse)
async def get_flow_diagram(
    days: int = Query(30, ge=1, le=365),
    min_frequency: int = Query(5, ge=1, description="Mindestanzahl für Kanten"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> FlowDiagramResponse:
    """
    Prozessfluss-Diagramm Daten.

    Liefert:
    - Knoten (Event-Typen)
    - Kanten (Übergaenge zwischen Events)
    - Varianten (verschiedene Prozesspfade)
    - Statistiken
    """
    discovery_service = ProcessDiscoveryService(db)

    result = await discovery_service.discover_process(
        company_id=company.company_id,
        days=days,
        min_frequency=min_frequency,
    )

    return FlowDiagramResponse(
        nodes=result.get("nodes", []),
        edges=result.get("edges", []),
        variants=result.get("variants", []),
        statistics=result.get("statistics", {}),
    )


@router.get("/variants", response_model=List[dict])
async def get_process_variants(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[dict]:
    """
    Prozessvarianten analysieren.

    Zeigt die verschiedenen Wege, die Dokumente durch den Prozess nehmen.
    Sortiert nach Häufigkeit.
    """
    discovery_service = ProcessDiscoveryService(db)

    variants = await discovery_service.get_variants(
        company_id=company.company_id,
        days=days,
        limit=limit,
    )

    return variants


# =============================================================================
# Admin Endpoints
# =============================================================================

@router.post("/admin/calculate-metrics", status_code=status.HTTP_202_ACCEPTED)
async def trigger_metric_calculation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Lösche tägliche Metrik-Berechnung aus (Admin).

    Normalerweise automatisch per Celery-Task.
    """
    detector = BottleneckDetector(db)
    await detector.save_daily_metrics(company_id=company.company_id)
    await db.commit()

    return {
        "status": "accepted",
        "message": "Metrik-Berechnung gestartet",
    }


@router.get("/admin/event-types", response_model=List[dict])
async def list_event_types(
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Liste alle verfügbaren Event-Typen (Admin).
    """
    return [
        {"value": e.value, "name": e.name}
        for e in EventType
    ]


@router.get("/admin/suggestion-types", response_model=List[dict])
async def list_suggestion_types(
    current_user: User = Depends(get_current_active_user),
) -> List[dict]:
    """
    Liste alle verfügbaren Vorschlags-Typen (Admin).
    """
    return [
        {"value": t.value, "name": t.name}
        for t in SuggestionType
    ]
