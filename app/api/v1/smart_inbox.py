"""
Smart Inbox API Router.

KI-gestützte Posteingang-Priorisierung mit automatischer Aggregation
und Handlungsempfehlungen.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_detail
from app.db.models import User
from app.services.ai.smart_inbox.smart_inbox_service import SmartInboxService

router = APIRouter(prefix="/smart-inbox", tags=["smart-inbox"])


# ============================================================================
# Schemas
# ============================================================================


class SmartInboxItemResponse(BaseModel):
    """Einzelnes Smart Inbox Item."""

    id: UUID
    source_type: str
    source_id: Optional[UUID]
    title: str
    description: Optional[str]
    category: Optional[str]
    raw_priority: float
    ml_priority: float
    status: str
    deadline: Optional[datetime]
    recommended_actions: List[JSONDict]
    context_data: JSONDict
    document_id: Optional[UUID]
    entity_id: Optional[UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SmartInboxListResponse(BaseModel):
    """Paginierte Liste von Smart Inbox Items."""

    items: List[SmartInboxItemResponse]
    total: int
    has_more: bool

    model_config = ConfigDict(from_attributes=True)


class SmartInboxActionRequest(BaseModel):
    """Aktion auf einem Inbox Item."""

    action: str = Field(
        ..., pattern="^(complete|approve|reject|escalate|review|pay)$"
    )
    data: Optional[JSONDict] = None

    model_config = ConfigDict(from_attributes=True)


class SmartInboxSnoozeRequest(BaseModel):
    """Snooze-Request für ein Inbox Item."""

    snooze_until: datetime

    model_config = ConfigDict(from_attributes=True)


class SmartInboxInsight(BaseModel):
    """KI-Insight über Benutzerverhalten."""

    title: str
    description: str
    metric: str
    value: float
    trend: str  # up, down, stable

    model_config = ConfigDict(from_attributes=True)


class SmartInboxInsightsResponse(BaseModel):
    """Liste von KI-Insights."""

    insights: List[SmartInboxInsight]

    model_config = ConfigDict(from_attributes=True)


class SmartInboxStatsResponse(BaseModel):
    """Statistiken über den Smart Inbox."""

    total: int
    pending: int
    in_progress: int
    completed_today: int
    dismissed_today: int
    avg_response_time_ms: int
    by_category: Dict[str, int]
    by_source: Dict[str, int]

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=SmartInboxListResponse)
async def get_smart_inbox(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SmartInboxListResponse:
    """
    Gibt priorisierte Inbox Items zurück.

    Sortiert Items nach ML-basierter Priorität und berücksichtigt
    Deadlines, Kategorie und Benutzerverhalten.

    Args:
        limit: Max. Anzahl Items (1-100)
        offset: Offset für Pagination
        status_filter: Filter nach Status (pending, in_progress, completed, dismissed)
        category: Filter nach Kategorie
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Paginierte Liste von Inbox Items

    Raises:
        HTTPException: Bei Fehler beim Abrufen der Items
    """
    try:
        service = SmartInboxService(db=db, user_id=current_user.id)

        result = await service.get_prioritized_items(
            company_id=current_user.company_id,
            limit=limit,
            offset=offset,
            status=status_filter,
            category=category,
        )

        return SmartInboxListResponse(
            items=[
                SmartInboxItemResponse.model_validate(item) for item in result.items
            ],
            total=result.total,
            has_more=result.has_more,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.post("/{item_id}/act", status_code=status.HTTP_204_NO_CONTENT)
async def perform_inbox_action(
    item_id: UUID,
    request: SmartInboxActionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Führt eine Aktion auf einem Inbox Item aus.

    Unterstützte Aktionen: complete, approve, reject, escalate, review, pay

    Args:
        item_id: ID des Inbox Items
        request: Aktion mit optionalen zusätzlichen Daten
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Raises:
        HTTPException: Bei ungültiger Item-ID oder Fehler
    """
    try:
        service = SmartInboxService(db=db, user_id=current_user.id)

        await service.perform_action(
            item_id=item_id,
            action=request.action,
            action_data=request.data,
            company_id=current_user.company_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.post("/{item_id}/snooze", status_code=status.HTTP_204_NO_CONTENT)
async def snooze_inbox_item(
    item_id: UUID,
    request: SmartInboxSnoozeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Snoozed ein Inbox Item bis zu einem bestimmten Zeitpunkt.

    Das Item wird aus der Inbox ausgeblendet und zur angegebenen Zeit
    wieder angezeigt.

    Args:
        item_id: ID des Inbox Items
        request: Zeitpunkt, bis zu dem gesnoozed werden soll
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Raises:
        HTTPException: Bei ungültiger Item-ID oder Zeitpunkt in der Vergangenheit
    """
    try:
        if request.snooze_until <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Snooze-Zeitpunkt muss in der Zukunft liegen",
            )

        service = SmartInboxService(db=db, user_id=current_user.id)

        await service.snooze_item(
            item_id=item_id,
            snooze_until=request.snooze_until,
            company_id=current_user.company_id,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.post("/{item_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_inbox_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Verwirft ein Inbox Item.

    Das Item wird als erledigt markiert und aus der Inbox entfernt.

    Args:
        item_id: ID des Inbox Items
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Raises:
        HTTPException: Bei ungültiger Item-ID
    """
    try:
        service = SmartInboxService(db=db, user_id=current_user.id)

        await service.dismiss_item(
            item_id=item_id, company_id=current_user.company_id
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.get("/insights", response_model=SmartInboxInsightsResponse)
async def get_inbox_insights(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SmartInboxInsightsResponse:
    """
    Gibt KI-Insights über Benutzerverhalten zurück.

    Analysiert Muster im Umgang mit Inbox Items und generiert
    Handlungsempfehlungen.

    Args:
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Liste von KI-generierten Insights

    Raises:
        HTTPException: Bei Fehler beim Generieren der Insights
    """
    try:
        service = SmartInboxService(db=db, user_id=current_user.id)

        insights = await service.get_user_insights(
            company_id=current_user.company_id
        )

        return SmartInboxInsightsResponse(
            insights=[
                SmartInboxInsight(
                    title=insight["title"],
                    description=insight["description"],
                    metric=insight["metric"],
                    value=insight["value"],
                    trend=insight["trend"],
                )
                for insight in insights
            ]
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.post("/aggregate", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual_aggregation(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, str]:
    """
    Triggert eine manuelle Aggregation von Inbox Items.

    Sammelt neue Items aus verschiedenen Quellen (Alerts, Dokumente,
    Rechnungen, etc.) und berechnet Prioritäten neu.

    Args:
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Status-Nachricht mit Task-ID

    Raises:
        HTTPException: Bei Fehler beim Triggern der Aggregation
    """
    try:
        service = SmartInboxService(db=db, user_id=current_user.id)

        task_id = await service.trigger_aggregation(
            company_id=current_user.company_id
        )

        return {
            "message": "Aggregation wurde gestartet",
            "task_id": str(task_id),
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.get("/stats", response_model=SmartInboxStatsResponse)
async def get_inbox_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SmartInboxStatsResponse:
    """
    Gibt Statistiken über den Smart Inbox zurück.

    Umfasst Gesamtzahlen, Status-Verteilung, Kategorie-Verteilung
    und Performance-Metriken.

    Args:
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Detaillierte Inbox-Statistiken

    Raises:
        HTTPException: Bei Fehler beim Abrufen der Statistiken
    """
    try:
        service = SmartInboxService(db=db, user_id=current_user.id)

        stats = await service.get_statistics(company_id=current_user.company_id)

        return SmartInboxStatsResponse(
            total=stats["total"],
            pending=stats["pending"],
            in_progress=stats["in_progress"],
            completed_today=stats["completed_today"],
            dismissed_today=stats["dismissed_today"],
            avg_response_time_ms=stats["avg_response_time_ms"],
            by_category=stats["by_category"],
            by_source=stats["by_source"],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )
