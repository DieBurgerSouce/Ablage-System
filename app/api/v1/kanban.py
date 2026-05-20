# -*- coding: utf-8 -*-
"""Kanban Board API - Dokument-Workflow-Management."""

from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, validate_company_access
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.services.workflow.kanban_service import (
    KanbanService, get_kanban_service, KanbanBoardData, KanbanItemData, KanbanStageData, StageStatistics
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/kanban", tags=["Kanban Board"])


# =============================================================================
# Schemas
# =============================================================================

class KanbanItemSchema(BaseModel):
    """Schema für Kanban-Item."""
    id: UUID
    document_id: UUID
    document_name: Optional[str] = None
    entity_name: Optional[str] = None
    amount: Optional[Decimal] = None
    priority: str = "normal"
    assigned_to: Optional[UUID] = None
    assigned_to_name: Optional[str] = None
    entered_stage_at: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class KanbanStageSchema(BaseModel):
    """Schema für Kanban-Stage."""
    id: UUID
    stage_key: str
    stage_name: str
    stage_order: int
    color: str = "#6B7280"
    icon: Optional[str] = None
    is_final: bool = False
    item_count: int = 0
    items: List[KanbanItemSchema] = []

    model_config = ConfigDict(from_attributes=True)


class KanbanBoardSchema(BaseModel):
    """Schema für vollständiges Kanban-Board."""
    workflow_type: str
    stages: List[KanbanStageSchema]
    total_items: int


class MoveItemRequest(BaseModel):
    """Request für Item-Verschiebung."""
    target_stage_id: UUID = Field(..., description="Ziel-Stage ID")


class AddItemRequest(BaseModel):
    """Request für neues Item."""
    document_id: UUID = Field(..., description="Dokument ID")
    priority: str = Field(default="normal", description="Prioritaet (low, normal, high, urgent)")
    assigned_to: Optional[UUID] = Field(None, description="Zugewiesener User ID")


class StageConfigRequest(BaseModel):
    """Request für Stage-Konfiguration."""
    stage_key: str = Field(..., description="Eindeutiger Stage-Key")
    stage_name: str = Field(..., description="Anzeigename")
    stage_order: int = Field(..., description="Reihenfolge")
    color: str = Field(default="#6B7280", description="Hex-Farbe")
    icon: Optional[str] = Field(None, description="Lucide Icon-Name")
    is_final: bool = Field(default=False, description="Finale Stage?")
    auto_transition_after_hours: Optional[int] = Field(None, description="Auto-Transition nach N Stunden")
    required_approval: bool = Field(default=False, description="Freigabe erforderlich?")


class StageStatisticsSchema(BaseModel):
    """Schema für Stage-Statistiken."""
    stage_key: str
    stage_name: str
    item_count: int
    avg_time_in_stage_hours: Optional[float] = None


# =============================================================================
# Helper Functions
# =============================================================================

def _board_data_to_schema(data: KanbanBoardData) -> KanbanBoardSchema:
    """Konvertiert KanbanBoardData zu Schema."""
    stages = [
        KanbanStageSchema(
            id=stage.id,
            stage_key=stage.stage_key,
            stage_name=stage.stage_name,
            stage_order=stage.stage_order,
            color=stage.color,
            icon=stage.icon,
            is_final=stage.is_final,
            item_count=stage.item_count,
            items=[
                KanbanItemSchema(
                    id=item.id,
                    document_id=item.document_id,
                    document_name=item.document_name,
                    entity_name=item.entity_name,
                    amount=item.amount,
                    priority=item.priority,
                    assigned_to=item.assigned_to,
                    assigned_to_name=item.assigned_to_name,
                    entered_stage_at=item.entered_stage_at,
                    notes=item.notes,
                )
                for item in stage.items
            ]
        )
        for stage in data.stages
    ]

    return KanbanBoardSchema(
        workflow_type=data.workflow_type,
        stages=stages,
        total_items=data.total_items,
    )


def _item_data_to_schema(item: KanbanItemData) -> KanbanItemSchema:
    """Konvertiert KanbanItemData zu Schema."""
    return KanbanItemSchema(
        id=item.id,
        document_id=item.document_id,
        document_name=item.document_name,
        entity_name=item.entity_name,
        amount=item.amount,
        priority=item.priority,
        assigned_to=item.assigned_to,
        assigned_to_name=item.assigned_to_name,
        entered_stage_at=item.entered_stage_at,
        notes=item.notes,
    )


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/{workflow_type}/board", response_model=KanbanBoardSchema)
async def get_board(
    workflow_type: str,
    company_id: UUID = Query(..., description="Company ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> KanbanBoardSchema:
    """
    Gibt vollständiges Kanban-Board mit allen Stages und Items zurück.

    **Workflow-Typen:**
    - `document`: Standard-Dokumentenworkflow
    - `invoice`: Rechnungsworkflow
    - `contract`: Vertragsworkflow
    - `custom`: Benutzerdefiniert

    **German Error Messages:**
    - 403: "Kein Zugriff auf diese Firma"
    - 500: "Fehler beim Laden des Kanban-Boards"
    """
    validate_company_access(company_id, user)

    try:
        service = get_kanban_service(db)
        board_data = await service.get_board(company_id, workflow_type)
        return _board_data_to_schema(board_data)
    except Exception as e:
        logger.error("kanban_get_board_failed", workflow_type=workflow_type, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des Kanban-Boards"
        )


@router.patch("/items/{item_id}/move", response_model=KanbanItemSchema)
async def move_item(
    item_id: UUID,
    request: MoveItemRequest,
    company_id: UUID = Query(..., description="Company ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> KanbanItemSchema:
    """
    Verschiebt ein Item zu einer anderen Stage.

    **WebSocket Event:**
    Emittiert `kanban.item_moved` Event an alle Company-Mitglieder.

    **German Error Messages:**
    - 403: "Kein Zugriff auf diese Firma"
    - 404: "Workflow-Item nicht gefunden"
    - 400: "Invalide Stage oder Workflow-Typ"
    - 500: "Fehler beim Verschieben des Items"
    """
    validate_company_access(company_id, user)

    try:
        service = get_kanban_service(db)
        item_data = await service.move_item(item_id, request.target_stage_id, user.id)
        return _item_data_to_schema(item_data)
    except ValueError as e:
        logger.warning("kanban_move_item_invalid", item_id=str(item_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Kanban")
        )
    except Exception as e:
        logger.error("kanban_move_item_failed", item_id=str(item_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Verschieben des Items"
        )


@router.post("/{workflow_type}/items", response_model=KanbanItemSchema, status_code=status.HTTP_201_CREATED)
async def add_item(
    workflow_type: str,
    request: AddItemRequest,
    company_id: UUID = Query(..., description="Company ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> KanbanItemSchema:
    """
    Fuegt ein Dokument zum Kanban-Board hinzu (erste Stage).

    **German Error Messages:**
    - 403: "Kein Zugriff auf diese Firma"
    - 400: "Dokument ist bereits im Workflow" oder "Keine Stages konfiguriert"
    - 500: "Fehler beim Hinzufuegen des Items"
    """
    validate_company_access(company_id, user)

    try:
        service = get_kanban_service(db)
        item_data = await service.add_item(
            company_id=company_id,
            document_id=request.document_id,
            workflow_type=workflow_type,
            priority=request.priority,
            assigned_to=request.assigned_to,
        )
        return _item_data_to_schema(item_data)
    except ValueError as e:
        logger.warning("kanban_add_item_invalid", document_id=str(request.document_id), error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Kanban")
        )
    except Exception as e:
        logger.error("kanban_add_item_failed", document_id=str(request.document_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Hinzufuegen des Items"
        )


@router.get("/{workflow_type}/stages", response_model=List[KanbanStageSchema])
async def get_stages(
    workflow_type: str,
    company_id: UUID = Query(..., description="Company ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> List[KanbanStageSchema]:
    """
    Gibt alle Stages für einen Workflow-Typ zurück.

    Erstellt Default-Stages falls keine existieren.

    **German Error Messages:**
    - 403: "Kein Zugriff auf diese Firma"
    - 500: "Fehler beim Laden der Stages"
    """
    validate_company_access(company_id, user)

    try:
        service = get_kanban_service(db)
        stages = await service.ensure_default_stages(company_id, workflow_type)

        # Convert to schemas (ohne Items)
        stage_schemas = [
            KanbanStageSchema(
                id=stage.id,
                stage_key=stage.stage_key,
                stage_name=stage.stage_name,
                stage_order=stage.stage_order,
                color=stage.color,
                icon=stage.icon,
                is_final=stage.is_final,
                item_count=0,
                items=[],
            )
            for stage in stages
        ]

        return stage_schemas
    except Exception as e:
        logger.error("kanban_get_stages_failed", workflow_type=workflow_type, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Stages"
        )


@router.put("/{workflow_type}/stages", response_model=List[KanbanStageSchema])
async def update_stages(
    workflow_type: str,
    request: List[StageConfigRequest],
    company_id: UUID = Query(..., description="Company ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> List[KanbanStageSchema]:
    """
    Admin: Aktualisiert Stage-Konfiguration für einen Workflow-Typ.

    **WARNUNG:** Löscht alle existierenden Stages und Items!

    **German Error Messages:**
    - 403: "Kein Zugriff auf diese Firma" oder "Nur Administratoren"
    - 400: "Stage-Orders müssen eindeutig sein"
    - 500: "Fehler beim Aktualisieren der Stages"
    """
    validate_company_access(company_id, user)

    # Only admins can reconfigure stages
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Stages konfigurieren"
        )

    try:
        service = get_kanban_service(db)

        # Convert request to dict format
        stages_dicts = [req.model_dump() for req in request]

        stages = await service.configure_stages(company_id, workflow_type, stages_dicts)

        # Convert to schemas
        stage_schemas = [
            KanbanStageSchema(
                id=stage.id,
                stage_key=stage.stage_key,
                stage_name=stage.stage_name,
                stage_order=stage.stage_order,
                color=stage.color,
                icon=stage.icon,
                is_final=stage.is_final,
                item_count=0,
                items=[],
            )
            for stage in stages
        ]

        return stage_schemas
    except ValueError as e:
        logger.warning("kanban_configure_stages_invalid", workflow_type=workflow_type, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Kanban")
        )
    except Exception as e:
        logger.error("kanban_configure_stages_failed", workflow_type=workflow_type, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der Stages"
        )


@router.get("/{workflow_type}/statistics", response_model=List[StageStatisticsSchema])
async def get_statistics(
    workflow_type: str,
    company_id: UUID = Query(..., description="Company ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> List[StageStatisticsSchema]:
    """
    Gibt Statistiken für alle Stages eines Workflows zurück.

    Beinhaltet:
    - Anzahl Items pro Stage
    - Durchschnittliche Verweildauer in Stunden

    **German Error Messages:**
    - 403: "Kein Zugriff auf diese Firma"
    - 500: "Fehler beim Laden der Statistiken"
    """
    validate_company_access(company_id, user)

    try:
        service = get_kanban_service(db)
        stats = await service.get_statistics(company_id, workflow_type)

        return [
            StageStatisticsSchema(
                stage_key=stat.stage_key,
                stage_name=stat.stage_name,
                item_count=stat.item_count,
                avg_time_in_stage_hours=stat.avg_time_in_stage_hours,
            )
            for stat in stats
        ]
    except Exception as e:
        logger.error("kanban_get_statistics_failed", workflow_type=workflow_type, **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Statistiken"
        )


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    item_id: UUID,
    company_id: UUID = Query(..., description="Company ID"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> None:
    """
    Entfernt ein Item vom Kanban-Board.

    Das Dokument selbst wird nicht gelöscht, nur die Workflow-Zuordnung.

    **German Error Messages:**
    - 403: "Kein Zugriff auf diese Firma"
    - 500: "Fehler beim Entfernen des Items"
    """
    validate_company_access(company_id, user)

    try:
        service = get_kanban_service(db)
        await service.remove_item(item_id)
    except Exception as e:
        logger.error("kanban_remove_item_failed", item_id=str(item_id), **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Entfernen des Items"
        )
