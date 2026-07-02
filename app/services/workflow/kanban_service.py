# -*- coding: utf-8 -*-
"""
KanbanService - Generalisierter Dokument-Workflow.

Default-Stages:
1. Eingang - Neue Dokumente
2. OCR-Verarbeitung - Automatische Texterkennung
3. Prüfung - Manuelle Kontrolle
4. Freigabe - Zur Freigabe bereit
5. Gebucht - Buchung erfasst
6. Archiv - Abgeschlossen
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import select, and_, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.safe_errors import safe_error_log
from app.db.models_workflow_stage import (
    WorkflowStage, DocumentWorkflowItem, WorkflowType, ItemPriority
)
from app.db.models import Document, BusinessEntity, User

logger = structlog.get_logger(__name__)


# Default stage definitions for "document" workflow
DEFAULT_DOCUMENT_STAGES = [
    {"stage_key": "eingang", "stage_name": "Eingang", "stage_order": 1, "color": "#6B7280", "icon": "inbox"},
    {"stage_key": "ocr", "stage_name": "OCR-Verarbeitung", "stage_order": 2, "color": "#3B82F6", "icon": "scan"},
    {"stage_key": "prüfung", "stage_name": "Prüfung", "stage_order": 3, "color": "#F59E0B", "icon": "search"},
    {"stage_key": "freigabe", "stage_name": "Freigabe", "stage_order": 4, "color": "#8B5CF6", "icon": "check-circle"},
    {"stage_key": "gebucht", "stage_name": "Gebucht", "stage_order": 5, "color": "#10B981", "icon": "book-open"},
    {"stage_key": "archiv", "stage_name": "Archiv", "stage_order": 6, "color": "#6B7280", "icon": "archive", "is_final": True},
]


@dataclass
class KanbanBoardData:
    """Vollständige Kanban-Board-Daten."""
    workflow_type: str
    stages: List[KanbanStageData]
    total_items: int


@dataclass
class KanbanStageData:
    """Daten einer einzelnen Kanban-Stage."""
    id: UUID
    stage_key: str
    stage_name: str
    stage_order: int
    color: str
    icon: Optional[str]
    is_final: bool
    item_count: int
    items: List[KanbanItemData]


@dataclass
class KanbanItemData:
    """Daten eines einzelnen Kanban-Items."""
    id: UUID
    document_id: UUID
    document_name: Optional[str]
    entity_name: Optional[str]
    amount: Optional[Decimal]
    priority: str
    assigned_to: Optional[UUID]
    assigned_to_name: Optional[str]
    entered_stage_at: datetime
    notes: Optional[str]


@dataclass
class StageStatistics:
    """Statistiken für eine einzelne Stage."""
    stage_key: str
    stage_name: str
    item_count: int
    avg_time_in_stage_hours: Optional[float]


class KanbanService:
    """Service für Kanban-Workflow-Management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def ensure_default_stages(self, company_id: UUID, workflow_type: str) -> List[WorkflowStage]:
        """
        Erstellt Default-Stages für Company falls keine existieren.

        Args:
            company_id: Company ID
            workflow_type: Workflow-Typ (z.B. "document")

        Returns:
            Liste der Stages sortiert nach stage_order
        """
        # Check if stages exist
        result = await self.db.execute(
            select(WorkflowStage)
            .where(
                and_(
                    WorkflowStage.company_id == company_id,
                    WorkflowStage.workflow_type == workflow_type
                )
            )
            .order_by(WorkflowStage.stage_order)
        )
        existing_stages = result.scalars().all()

        if existing_stages:
            return list(existing_stages)

        # Create default stages for "document" workflow
        if workflow_type == WorkflowType.DOCUMENT.value:
            stages_to_create = DEFAULT_DOCUMENT_STAGES
        else:
            # For other workflow types, use minimal default
            stages_to_create = [
                {"stage_key": "todo", "stage_name": "Zu erledigen", "stage_order": 1, "color": "#6B7280", "icon": "inbox"},
                {"stage_key": "done", "stage_name": "Erledigt", "stage_order": 2, "color": "#10B981", "icon": "check", "is_final": True},
            ]

        new_stages: List[WorkflowStage] = []
        for stage_def in stages_to_create:
            stage = WorkflowStage(
                id=uuid.uuid4(),
                company_id=company_id,
                workflow_type=workflow_type,
                stage_key=stage_def["stage_key"],
                stage_name=stage_def["stage_name"],
                stage_order=stage_def["stage_order"],
                color=stage_def.get("color", "#6B7280"),
                icon=stage_def.get("icon"),
                is_final=stage_def.get("is_final", False),
            )
            self.db.add(stage)
            new_stages.append(stage)

        await self.db.commit()
        for stage in new_stages:
            await self.db.refresh(stage)

        logger.info(
            "default_workflow_stages_created",
            company_id=str(company_id),
            workflow_type=workflow_type,
            stage_count=len(new_stages)
        )

        return new_stages

    async def get_board(self, company_id: UUID, workflow_type: str) -> KanbanBoardData:
        """
        Gibt vollständiges Kanban-Board mit allen Stages und Items zurück.

        Args:
            company_id: Company ID
            workflow_type: Workflow-Typ

        Returns:
            KanbanBoardData mit allen Stages und Items
        """
        stages = await self.ensure_default_stages(company_id, workflow_type)

        stage_data_list: List[KanbanStageData] = []
        total_items = 0

        for stage in stages:
            # Load items for this stage with joined document, entity, assigned_to
            result = await self.db.execute(
                select(DocumentWorkflowItem)
                .options(
                    selectinload(DocumentWorkflowItem.document),
                    selectinload(DocumentWorkflowItem.assignee)
                )
                .where(DocumentWorkflowItem.current_stage_id == stage.id)
                .order_by(DocumentWorkflowItem.entered_stage_at.desc())
            )
            items = result.scalars().all()

            # Convert to KanbanItemData
            item_data_list: List[KanbanItemData] = []
            for item in items:
                # Get entity name and amount from document
                entity_name: Optional[str] = None
                amount: Optional[Decimal] = None

                if item.document:
                    # Try to get entity name from extracted data
                    if item.document.extracted_data:
                        entity_name = item.document.extracted_data.get("supplier_name") or item.document.extracted_data.get("customer_name")
                        amount_str = item.document.extracted_data.get("total_amount")
                        if amount_str:
                            try:
                                amount = Decimal(str(amount_str))
                            except (ArithmeticError, ValueError, TypeError) as e:
                                logger.debug(
                                    "kanban_amount_parse_skipped",
                                    error_type=type(e).__name__,
                                )

                assigned_to_name: Optional[str] = None
                if item.assignee:
                    assigned_to_name = f"{item.assignee.first_name} {item.assignee.last_name}" if item.assignee.first_name else item.assignee.email

                item_data = KanbanItemData(
                    id=item.id,
                    document_id=item.document_id,
                    document_name=item.document.filename if item.document else None,
                    entity_name=entity_name,
                    amount=amount,
                    priority=item.priority,
                    assigned_to=item.assigned_to,
                    assigned_to_name=assigned_to_name,
                    entered_stage_at=item.entered_stage_at,
                    notes=item.notes,
                )
                item_data_list.append(item_data)

            stage_data = KanbanStageData(
                id=stage.id,
                stage_key=stage.stage_key,
                stage_name=stage.stage_name,
                stage_order=stage.stage_order,
                color=stage.color,
                icon=stage.icon,
                is_final=stage.is_final,
                item_count=len(items),
                items=item_data_list,
            )
            stage_data_list.append(stage_data)
            total_items += len(items)

        return KanbanBoardData(
            workflow_type=workflow_type,
            stages=stage_data_list,
            total_items=total_items,
        )

    async def move_item(self, item_id: UUID, target_stage_id: UUID, user_id: UUID) -> KanbanItemData:
        """
        Verschiebt ein Item zwischen Stages.

        Args:
            item_id: Item ID
            target_stage_id: Ziel-Stage ID
            user_id: User ID (für Audit)

        Returns:
            Aktualisiertes Item

        Raises:
            ValueError: Wenn Item oder Stage nicht gefunden
        """
        # Load item
        result = await self.db.execute(
            select(DocumentWorkflowItem)
            .options(
                selectinload(DocumentWorkflowItem.document),
                selectinload(DocumentWorkflowItem.assignee),
                selectinload(DocumentWorkflowItem.stage)
            )
            .where(DocumentWorkflowItem.id == item_id)
        )
        item = result.scalar_one_or_none()

        if not item:
            raise ValueError(f"Workflow-Item nicht gefunden: {item_id}")

        # Validate target stage
        result = await self.db.execute(
            select(WorkflowStage).where(WorkflowStage.id == target_stage_id)
        )
        target_stage = result.scalar_one_or_none()

        if not target_stage:
            raise ValueError(f"Ziel-Stage nicht gefunden: {target_stage_id}")

        # Validate same company and workflow
        if target_stage.company_id != item.company_id:
            raise ValueError("Stage gehoert zu anderer Company")

        if target_stage.workflow_type != item.workflow_type:
            raise ValueError("Stage gehoert zu anderem Workflow-Typ")

        # Update item
        old_stage_id = item.current_stage_id
        item.previous_stage_id = old_stage_id
        item.current_stage_id = target_stage_id
        item.entered_stage_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(item)

        logger.info(
            "workflow_item_moved",
            item_id=str(item_id),
            document_id=str(item.document_id),
            from_stage_id=str(old_stage_id),
            to_stage_id=str(target_stage_id),
            user_id=str(user_id)
        )

        # Emit WebSocket event
        await self._emit_websocket_event(
            company_id=item.company_id,
            event_type="kanban.item_moved",
            data={
                "item_id": str(item_id),
                "document_id": str(item.document_id),
                "from_stage_id": str(old_stage_id),
                "to_stage_id": str(target_stage_id),
                "workflow_type": item.workflow_type,
            }
        )

        # Convert to KanbanItemData
        return await self._item_to_data(item)

    async def add_item(
        self,
        company_id: UUID,
        document_id: UUID,
        workflow_type: str,
        priority: str = "normal",
        assigned_to: Optional[UUID] = None
    ) -> KanbanItemData:
        """
        Fuegt ein Dokument zum Board hinzu (erste Stage).

        Args:
            company_id: Company ID
            document_id: Dokument ID
            workflow_type: Workflow-Typ
            priority: Priorität
            assigned_to: Optional zugewiesener User

        Returns:
            Erstelltes Item

        Raises:
            ValueError: Wenn Dokument bereits im Workflow oder nicht gefunden
        """
        # Check if document already in workflow
        result = await self.db.execute(
            select(DocumentWorkflowItem).where(
                and_(
                    DocumentWorkflowItem.company_id == company_id,
                    DocumentWorkflowItem.document_id == document_id,
                    DocumentWorkflowItem.workflow_type == workflow_type
                )
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"Dokument ist bereits im Workflow '{workflow_type}'")

        # Get first stage (lowest stage_order)
        stages = await self.ensure_default_stages(company_id, workflow_type)
        if not stages:
            raise ValueError(f"Keine Stages für Workflow '{workflow_type}' gefunden")

        first_stage = min(stages, key=lambda s: s.stage_order)

        # Create item
        item = DocumentWorkflowItem(
            id=uuid.uuid4(),
            company_id=company_id,
            document_id=document_id,
            workflow_type=workflow_type,
            current_stage_id=first_stage.id,
            priority=priority,
            assigned_to=assigned_to,
            entered_stage_at=datetime.utcnow(),
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)

        # Load relationships
        result = await self.db.execute(
            select(DocumentWorkflowItem)
            .options(
                selectinload(DocumentWorkflowItem.document),
                selectinload(DocumentWorkflowItem.assignee)
            )
            .where(DocumentWorkflowItem.id == item.id)
        )
        item = result.scalar_one()

        logger.info(
            "workflow_item_added",
            item_id=str(item.id),
            document_id=str(document_id),
            stage_id=str(first_stage.id),
            workflow_type=workflow_type
        )

        return await self._item_to_data(item)

    async def configure_stages(self, company_id: UUID, workflow_type: str, stages: List[Dict[str, object]]) -> List[WorkflowStage]:
        """
        Admin-Funktion: Stages für einen Workflow konfigurieren.

        Args:
            company_id: Company ID
            workflow_type: Workflow-Typ
            stages: Liste von Stage-Definitionen

        Returns:
            Aktualisierte Stages

        Raises:
            ValueError: Bei invalider Konfiguration
        """
        # Validate stage ordering
        stage_orders = [s["stage_order"] for s in stages]
        if len(stage_orders) != len(set(stage_orders)):
            raise ValueError("Stage-Orders müssen eindeutig sein")

        # Delete existing stages (CASCADE deletes items)
        await self.db.execute(
            delete(WorkflowStage).where(
                and_(
                    WorkflowStage.company_id == company_id,
                    WorkflowStage.workflow_type == workflow_type
                )
            )
        )

        # Create new stages
        new_stages: List[WorkflowStage] = []
        for stage_def in stages:
            stage = WorkflowStage(
                id=uuid.uuid4(),
                company_id=company_id,
                workflow_type=workflow_type,
                stage_key=str(stage_def["stage_key"]),
                stage_name=str(stage_def["stage_name"]),
                stage_order=int(stage_def["stage_order"]),
                color=str(stage_def.get("color", "#6B7280")),
                icon=str(stage_def.get("icon")) if stage_def.get("icon") else None,
                is_final=bool(stage_def.get("is_final", False)),
                auto_transition_after_hours=int(stage_def["auto_transition_after_hours"]) if stage_def.get("auto_transition_after_hours") else None,
                required_approval=bool(stage_def.get("required_approval", False)),
            )
            self.db.add(stage)
            new_stages.append(stage)

        await self.db.commit()
        for stage in new_stages:
            await self.db.refresh(stage)

        logger.info(
            "workflow_stages_configured",
            company_id=str(company_id),
            workflow_type=workflow_type,
            stage_count=len(new_stages)
        )

        return new_stages

    async def get_statistics(self, company_id: UUID, workflow_type: str) -> List[StageStatistics]:
        """
        Gibt Statistiken pro Stage zurück.

        Args:
            company_id: Company ID
            workflow_type: Workflow-Typ

        Returns:
            Liste von Stage-Statistiken
        """
        stages = await self.ensure_default_stages(company_id, workflow_type)

        stats_list: List[StageStatistics] = []
        for stage in stages:
            # Count items
            result = await self.db.execute(
                select(func.count(DocumentWorkflowItem.id)).where(
                    DocumentWorkflowItem.current_stage_id == stage.id
                )
            )
            item_count = result.scalar() or 0

            # Calculate avg time in stage
            result = await self.db.execute(
                select(func.avg(
                    func.extract('epoch', func.now() - DocumentWorkflowItem.entered_stage_at) / 3600
                )).where(
                    DocumentWorkflowItem.current_stage_id == stage.id
                )
            )
            avg_hours = result.scalar()

            stats = StageStatistics(
                stage_key=stage.stage_key,
                stage_name=stage.stage_name,
                item_count=int(item_count),
                avg_time_in_stage_hours=float(avg_hours) if avg_hours else None,
            )
            stats_list.append(stats)

        return stats_list

    async def remove_item(self, item_id: UUID) -> None:
        """
        Entfernt ein Item vom Board.

        Args:
            item_id: Item ID
        """
        await self.db.execute(
            delete(DocumentWorkflowItem).where(DocumentWorkflowItem.id == item_id)
        )
        await self.db.commit()

        logger.info("workflow_item_removed", item_id=str(item_id))

    async def _emit_websocket_event(self, company_id: UUID, event_type: str, data: Dict[str, object]) -> None:
        """
        Emittiert WebSocket-Event an alle Company-Mitglieder.

        Args:
            company_id: Company ID
            event_type: Event-Typ
            data: Event-Daten
        """
        try:
            from app.services.realtime.realtime_websocket_manager import get_realtime_ws_manager

            manager = get_realtime_ws_manager()
            from app.services.realtime.realtime_websocket_manager import WSMessage

            await manager.broadcast_to_company(
                company_id=str(company_id),
                message=WSMessage(
                    type=event_type,
                    payload=data,
                ),
            )
        except Exception as e:
            logger.warning("websocket_broadcast_failed", event_type=event_type, **safe_error_log(e))

    async def _item_to_data(self, item: DocumentWorkflowItem) -> KanbanItemData:
        """
        Konvertiert DocumentWorkflowItem zu KanbanItemData.

        Args:
            item: Workflow-Item

        Returns:
            KanbanItemData
        """
        entity_name: Optional[str] = None
        amount: Optional[Decimal] = None

        if item.document and item.document.extracted_data:
            entity_name = item.document.extracted_data.get("supplier_name") or item.document.extracted_data.get("customer_name")
            amount_str = item.document.extracted_data.get("total_amount")
            if amount_str:
                try:
                    amount = Decimal(str(amount_str))
                except (ArithmeticError, ValueError, TypeError) as e:
                    logger.debug(
                        "kanban_amount_parse_skipped",
                        error_type=type(e).__name__,
                    )

        assigned_to_name: Optional[str] = None
        if item.assignee:
            assigned_to_name = f"{item.assignee.first_name} {item.assignee.last_name}" if item.assignee.first_name else item.assignee.email

        return KanbanItemData(
            id=item.id,
            document_id=item.document_id,
            document_name=item.document.filename if item.document else None,
            entity_name=entity_name,
            amount=amount,
            priority=item.priority,
            assigned_to=item.assigned_to,
            assigned_to_name=assigned_to_name,
            entered_stage_at=item.entered_stage_at,
            notes=item.notes,
        )


def get_kanban_service(db: AsyncSession) -> KanbanService:
    """Factory-Funktion für KanbanService."""
    return KanbanService(db)
