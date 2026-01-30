# -*- coding: utf-8 -*-
"""
Action Approval Queue API Endpoints.

Enterprise Feature: API für Aktions-Genehmigungsqueue.

Endpoints:
- GET /action-queue/levels - Alle Autonomie-Levels
- GET /action-queue/pending - Ausstehende Aktionen
- POST /action-queue/{id}/approve - Aktion genehmigen
- POST /action-queue/{id}/reject - Aktion ablehnen
- POST /action-queue/bulk-approve - Massengenehmigung
- GET /action-queue/stats - Queue-Statistiken
- GET /action-queue/categories - Aktions-Kategorien

ENTERPRISE-GRADE: Verwendet AutonomySettings DB-Modell für Persistenz.
"""

import structlog
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_user,
    get_db,
    require_permission,
)
from app.db.models import User
from app.db.models_autonomy import (
    AutonomySettings,
    AutonomyLevelEnum,
)
from app.services.autonomy import (
    ActionCategory,
    ActionPriority,
    AutonomyLevel,
    QueuedActionData,
    QueueStats,
    get_action_queue,
    get_confidence_router,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/action-queue", tags=["Action Queue"])


# === Pydantic Models ===


class AutonomyLevelResponse(BaseModel):
    """Antwort mit aktuellem Autonomie-Level."""

    level: int = Field(..., description="Autonomie-Level (1-4)")
    level_name: str = Field(..., description="Name des Levels")
    description: str = Field(..., description="Beschreibung")
    confidence_threshold: float = Field(
        ..., description="Confidence-Schwellenwert für Auto-Ausführung"
    )
    auto_approve_routine: bool = Field(
        ..., description="Routine-Aufgaben automatisch genehmigen"
    )


class AutonomyLevelUpdate(BaseModel):
    """Request zum Ändern des Autonomie-Levels."""

    level: int = Field(
        ..., ge=1, le=4, description="Neues Autonomie-Level (1-4)"
    )
    reason: str | None = Field(
        None, max_length=500, description="Begründung für die Änderung"
    )


class QueuedActionResponse(BaseModel):
    """Antwort mit einer Queue-Aktion."""

    id: str
    action_type: str
    category: str
    description: str
    confidence: float
    priority: int
    status: str
    created_at: str
    timeout_at: str | None
    auto_approve_on_timeout: bool
    autonomy_decision: dict
    metadata: dict


class ApproveActionRequest(BaseModel):
    """Request zum Genehmigen einer Aktion."""

    comment: str | None = Field(
        None, max_length=500, description="Optionaler Kommentar"
    )


class RejectActionRequest(BaseModel):
    """Request zum Ablehnen einer Aktion."""

    reason: str = Field(
        ..., min_length=1, max_length=500, description="Ablehnungsgrund"
    )


class BulkApproveRequest(BaseModel):
    """Request für Massengenehmigung."""

    action_ids: list[str] = Field(
        ..., min_length=1, max_length=100, description="IDs der Aktionen"
    )


class BulkApproveResponse(BaseModel):
    """Antwort auf Massengenehmigung."""

    results: dict[str, bool] = Field(
        ..., description="action_id -> success"
    )
    approved_count: int
    failed_count: int


class QueueStatsResponse(BaseModel):
    """Statistiken der Action Queue."""

    total_pending: int
    by_priority: dict[str, int]
    by_category: dict[str, int]
    avg_wait_time_seconds: float
    oldest_pending_age_seconds: float
    auto_approved_today: int
    manual_approved_today: int
    rejected_today: int


class RoutingStatsResponse(BaseModel):
    """Routing-Statistiken."""

    queue_stats: QueueStatsResponse
    routing_distribution: dict
    confidence_stats: dict
    execution_stats: dict


# === Helper Functions ===


def _db_level_to_autonomy_level(db_level: str) -> AutonomyLevel:
    """Konvertiert DB-Level zu AutonomyLevel Enum."""
    mapping = {
        "conservative": AutonomyLevel.CONSERVATIVE,
        "smart_hybrid": AutonomyLevel.SMART_HYBRID,
        "progressive": AutonomyLevel.PROGRESSIVE,
        "zero_touch": AutonomyLevel.ZERO_TOUCH,
    }
    return mapping.get(db_level, AutonomyLevel.CONSERVATIVE)


def _autonomy_level_to_db(level: AutonomyLevel) -> str:
    """Konvertiert AutonomyLevel zu DB-String."""
    mapping = {
        AutonomyLevel.CONSERVATIVE: "conservative",
        AutonomyLevel.SMART_HYBRID: "smart_hybrid",
        AutonomyLevel.PROGRESSIVE: "progressive",
        AutonomyLevel.ZERO_TOUCH: "zero_touch",
    }
    return mapping.get(level, "conservative")


async def _get_or_create_autonomy_settings(
    db: AsyncSession, company_id: UUID
) -> AutonomySettings:
    """Holt oder erstellt AutonomySettings für eine Company."""
    query = select(AutonomySettings).where(
        AutonomySettings.company_id == company_id
    )
    result = await db.execute(query)
    settings = result.scalar_one_or_none()

    if not settings:
        # Erstelle Default-Einstellungen
        settings = AutonomySettings(
            company_id=company_id,
            autonomy_level=AutonomyLevelEnum.CONSERVATIVE.value,
        )
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
        logger.info(
            "autonomy_settings_created",
            company_id=str(company_id),
        )

    return settings


# === Endpoints ===


@router.get(
    "/level",
    response_model=AutonomyLevelResponse,
    summary="Aktuelles Autonomie-Level abrufen",
)
async def get_autonomy_level(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutonomyLevelResponse:
    """
    Ruft das aktuelle Autonomie-Level der Company ab.

    Liest aus der Datenbank (AutonomySettings).

    Returns:
        AutonomyLevelResponse mit Level-Details
    """
    settings = await _get_or_create_autonomy_settings(db, current_user.company_id)
    level = _db_level_to_autonomy_level(settings.autonomy_level)

    return AutonomyLevelResponse(
        level=level.value,
        level_name=level.name,
        description=level.description,
        confidence_threshold=level.confidence_threshold,
        auto_approve_routine=level.auto_approve_routine,
    )


@router.put(
    "/level",
    response_model=AutonomyLevelResponse,
    summary="Autonomie-Level ändern",
    dependencies=[Depends(require_permission("admin:settings:write"))],
)
async def update_autonomy_level(
    request: AutonomyLevelUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AutonomyLevelResponse:
    """
    Ändert das Autonomie-Level der Company.

    Erfordert Admin-Berechtigung.
    Persistiert in der Datenbank (AutonomySettings).

    Args:
        request: Neues Level und Begründung

    Returns:
        AutonomyLevelResponse mit aktualisiertem Level
    """
    try:
        level = AutonomyLevel(request.level)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültiges Autonomie-Level. Erlaubt: 1-4",
        )

    # Hole oder erstelle Settings
    settings = await _get_or_create_autonomy_settings(db, current_user.company_id)

    # Speichere alten Wert für Audit
    old_level = settings.autonomy_level

    # Update
    settings.autonomy_level = _autonomy_level_to_db(level)
    settings.updated_by_id = current_user.id

    await db.commit()
    await db.refresh(settings)

    # Audit-Log
    logger.info(
        "autonomy_level_changed",
        company_id=str(current_user.company_id),
        user_id=str(current_user.id),
        old_level=old_level,
        new_level=settings.autonomy_level,
        reason=request.reason,
    )

    return AutonomyLevelResponse(
        level=level.value,
        level_name=level.name,
        description=level.description,
        confidence_threshold=level.confidence_threshold,
        auto_approve_routine=level.auto_approve_routine,
    )


@router.get(
    "/levels",
    response_model=list[AutonomyLevelResponse],
    summary="Alle verfügbaren Autonomie-Levels",
)
async def list_autonomy_levels() -> list[AutonomyLevelResponse]:
    """
    Listet alle verfügbaren Autonomie-Levels auf.

    Returns:
        Liste aller Levels mit Beschreibungen
    """
    return [
        AutonomyLevelResponse(
            level=level.value,
            level_name=level.name,
            description=level.description,
            confidence_threshold=level.confidence_threshold,
            auto_approve_routine=level.auto_approve_routine,
        )
        for level in AutonomyLevel
    ]


@router.get(
    "/queue",
    response_model=list[QueuedActionResponse],
    summary="Ausstehende Aktionen abrufen",
)
async def get_pending_actions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(50, ge=1, le=200),
    priority: int | None = Query(None, ge=1, le=5),
    category: str | None = Query(None),
) -> list[QueuedActionResponse]:
    """
    Ruft ausstehende Aktionen aus der Genehmigungsqueue ab.

    Args:
        limit: Maximale Anzahl
        priority: Filter nach Priorität (1-5)
        category: Filter nach Kategorie

    Returns:
        Liste der ausstehenden Aktionen
    """
    queue = get_action_queue()

    # Parse Filter
    priority_filter = ActionPriority(priority) if priority else None
    category_filter = None
    if category:
        try:
            category_filter = ActionCategory[category.upper()]
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültige Kategorie: {category}",
            )

    actions = await queue.get_pending(
        db=db,
        company_id=current_user.company_id,
        limit=limit,
        priority_filter=priority_filter,
        category_filter=category_filter,
    )

    return [
        QueuedActionResponse(
            id=a["id"],
            action_type=a["action_type"],
            category=a["category"],
            description=a["description"],
            confidence=a["confidence"],
            priority=a["priority"],
            status=a["status"],
            created_at=a["created_at"],
            timeout_at=a["timeout_at"],
            auto_approve_on_timeout=a["auto_approve_on_timeout"],
            autonomy_decision=a["autonomy_decision"],
            metadata=a["metadata"],
        )
        for a in actions
    ]


@router.post(
    "/queue/{action_id}/approve",
    response_model=QueuedActionResponse,
    summary="Aktion genehmigen",
)
async def approve_action(
    action_id: str,
    request: ApproveActionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QueuedActionResponse:
    """
    Genehmigt eine ausstehende Aktion.

    Args:
        action_id: ID der Aktion
        request: Optionaler Kommentar

    Returns:
        Aktualisierte Aktion
    """
    queue = get_action_queue()

    action = await queue.approve(
        db=db,
        company_id=current_user.company_id,
        action_id=action_id,
        approved_by=current_user.id,
        comment=request.comment,
    )

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aktion nicht gefunden oder bereits bearbeitet",
        )

    return QueuedActionResponse(
        id=action["id"],
        action_type=action["action_type"],
        category=action["category"],
        description=action["description"],
        confidence=action["confidence"],
        priority=action["priority"],
        status=action["status"],
        created_at=action["created_at"],
        timeout_at=action["timeout_at"],
        auto_approve_on_timeout=action["auto_approve_on_timeout"],
        autonomy_decision=action["autonomy_decision"],
        metadata=action["metadata"],
    )


@router.post(
    "/queue/{action_id}/reject",
    response_model=QueuedActionResponse,
    summary="Aktion ablehnen",
)
async def reject_action(
    action_id: str,
    request: RejectActionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QueuedActionResponse:
    """
    Lehnt eine ausstehende Aktion ab.

    Args:
        action_id: ID der Aktion
        request: Ablehnungsgrund (erforderlich)

    Returns:
        Aktualisierte Aktion
    """
    queue = get_action_queue()

    action = await queue.reject(
        db=db,
        company_id=current_user.company_id,
        action_id=action_id,
        rejected_by=current_user.id,
        reason=request.reason,
    )

    if not action:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Aktion nicht gefunden oder bereits bearbeitet",
        )

    return QueuedActionResponse(
        id=action["id"],
        action_type=action["action_type"],
        category=action["category"],
        description=action["description"],
        confidence=action["confidence"],
        priority=action["priority"],
        status=action["status"],
        created_at=action["created_at"],
        timeout_at=action["timeout_at"],
        auto_approve_on_timeout=action["auto_approve_on_timeout"],
        autonomy_decision=action["autonomy_decision"],
        metadata=action["metadata"],
    )


@router.post(
    "/queue/bulk-approve",
    response_model=BulkApproveResponse,
    summary="Mehrere Aktionen genehmigen",
)
async def bulk_approve_actions(
    request: BulkApproveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkApproveResponse:
    """
    Genehmigt mehrere Aktionen auf einmal.

    Args:
        request: Liste der Aktions-IDs

    Returns:
        Ergebnis pro Aktion
    """
    queue = get_action_queue()

    results = await queue.bulk_approve(
        db=db,
        company_id=current_user.company_id,
        action_ids=request.action_ids,
        approved_by=current_user.id,
    )

    approved_count = sum(1 for success in results.values() if success)
    failed_count = len(results) - approved_count

    return BulkApproveResponse(
        results=results,
        approved_count=approved_count,
        failed_count=failed_count,
    )


@router.get(
    "/queue/stats",
    response_model=QueueStatsResponse,
    summary="Queue-Statistiken abrufen",
)
async def get_queue_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> QueueStatsResponse:
    """
    Ruft Statistiken der Genehmigungsqueue ab.

    Returns:
        Zusammenfassung der Queue-Statistiken
    """
    queue = get_action_queue()
    stats = await queue.get_stats(db, current_user.company_id)

    return QueueStatsResponse(**stats)


@router.get(
    "/stats",
    response_model=RoutingStatsResponse,
    summary="Routing-Statistiken abrufen",
)
async def get_routing_stats(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
) -> RoutingStatsResponse:
    """
    Ruft umfassende Routing-Statistiken ab.

    Args:
        days: Anzahl Tage für historische Daten

    Returns:
        Routing- und Queue-Statistiken
    """
    router_instance = get_confidence_router()
    stats = await router_instance.get_routing_stats(
        db=db,
        company_id=current_user.company_id,
        days=days,
    )

    return RoutingStatsResponse(
        queue_stats=QueueStatsResponse(**stats["queue_stats"]),
        routing_distribution=stats["routing_distribution"],
        confidence_stats=stats["confidence_stats"],
        execution_stats=stats["execution_stats"],
    )


@router.get(
    "/categories",
    summary="Verfügbare Aktions-Kategorien",
)
async def list_action_categories() -> list[dict]:
    """
    Listet alle verfügbaren Aktions-Kategorien auf.

    Returns:
        Liste der Kategorien mit Risiko-Level
    """
    return [
        {
            "name": cat.name,
            "value": cat.value,
            "risk_level": cat.risk_level,
            "requires_explicit_approval": cat.requires_explicit_approval,
            "min_confidence_boost": cat.min_confidence_boost,
        }
        for cat in ActionCategory
    ]
