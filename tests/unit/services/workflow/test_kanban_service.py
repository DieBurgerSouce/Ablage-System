# -*- coding: utf-8 -*-
"""Unit tests for KanbanService."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workflow.kanban_service import (
    KanbanService, DEFAULT_DOCUMENT_STAGES, WorkflowType,
    KanbanBoardData, KanbanItemData
)
from app.db.models_workflow_stage import WorkflowStage, DocumentWorkflowItem
from app.db.models import Document, User


@pytest.fixture
def mock_db():
    """Mock async database session."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def company_id():
    """Test company ID."""
    return uuid.uuid4()


@pytest.fixture
def user_id():
    """Test user ID."""
    return uuid.uuid4()


@pytest.fixture
def document_id():
    """Test document ID."""
    return uuid.uuid4()


@pytest.fixture
def kanban_service(mock_db):
    """KanbanService instance with mocked database."""
    return KanbanService(mock_db)


@pytest.mark.asyncio
async def test_ensure_default_stages_creates_6_stages(kanban_service, mock_db, company_id):
    """Test: ensure_default_stages erstellt 6 Standard-Stages wenn keine existieren."""
    # Mock: Keine existierenden Stages
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    # Execute
    stages = await kanban_service.ensure_default_stages(company_id, WorkflowType.DOCUMENT.value)

    # Assert
    assert len(stages) == 6
    assert stages[0].stage_key == "eingang"
    assert stages[1].stage_key == "ocr"
    assert stages[2].stage_key == "prüfung"
    assert stages[3].stage_key == "freigabe"
    assert stages[4].stage_key == "gebucht"
    assert stages[5].stage_key == "archiv"
    assert stages[5].is_final is True

    # Verify stages were added to DB
    assert mock_db.add.call_count == 6
    assert mock_db.commit.call_count == 1


@pytest.mark.asyncio
async def test_ensure_default_stages_returns_existing(kanban_service, mock_db, company_id):
    """Test: ensure_default_stages gibt existierende Stages zurueck ohne neue zu erstellen."""
    # Mock: Existierende Stages
    existing_stages = [
        WorkflowStage(
            id=uuid.uuid4(),
            company_id=company_id,
            workflow_type=WorkflowType.DOCUMENT.value,
            stage_key="eingang",
            stage_name="Eingang",
            stage_order=1,
        ),
        WorkflowStage(
            id=uuid.uuid4(),
            company_id=company_id,
            workflow_type=WorkflowType.DOCUMENT.value,
            stage_key="archiv",
            stage_name="Archiv",
            stage_order=2,
            is_final=True,
        ),
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = existing_stages
    mock_db.execute.return_value = mock_result

    # Execute
    stages = await kanban_service.ensure_default_stages(company_id, WorkflowType.DOCUMENT.value)

    # Assert
    assert len(stages) == 2
    assert stages == existing_stages
    assert mock_db.add.call_count == 0  # Keine neuen Stages


@pytest.mark.asyncio
async def test_get_board_returns_all_stages(kanban_service, mock_db, company_id):
    """Test: get_board gibt alle Stages mit Items zurueck."""
    # Mock stages
    stage1 = WorkflowStage(
        id=uuid.uuid4(),
        company_id=company_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        stage_key="eingang",
        stage_name="Eingang",
        stage_order=1,
        color="#6B7280",
        icon="inbox",
        is_final=False,
    )
    stage2 = WorkflowStage(
        id=uuid.uuid4(),
        company_id=company_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        stage_key="archiv",
        stage_name="Archiv",
        stage_order=2,
        color="#6B7280",
        icon="archive",
        is_final=True,
    )

    # Mock document
    doc = Document(
        id=uuid.uuid4(),
        filename="test.pdf",
        extracted_data={"supplier_name": "ACME Corp", "total_amount": "100.50"},
    )

    # Mock items
    item1 = DocumentWorkflowItem(
        id=uuid.uuid4(),
        company_id=company_id,
        document_id=doc.id,
        workflow_type=WorkflowType.DOCUMENT.value,
        current_stage_id=stage1.id,
        priority="normal",
        entered_stage_at=datetime.utcnow(),
    )
    item1.document = doc
    item1.assignee = None

    # Mock database responses
    # First call: get existing stages
    mock_result_stages = MagicMock()
    mock_result_stages.scalars.return_value.all.return_value = [stage1, stage2]

    # Second call: get items for stage1
    mock_result_items1 = MagicMock()
    mock_result_items1.scalars.return_value.all.return_value = [item1]

    # Third call: get items for stage2 (empty)
    mock_result_items2 = MagicMock()
    mock_result_items2.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [mock_result_stages, mock_result_items1, mock_result_items2]

    # Execute
    board = await kanban_service.get_board(company_id, WorkflowType.DOCUMENT.value)

    # Assert
    assert isinstance(board, KanbanBoardData)
    assert board.workflow_type == WorkflowType.DOCUMENT.value
    assert len(board.stages) == 2
    assert board.total_items == 1

    # Check first stage
    assert board.stages[0].stage_key == "eingang"
    assert board.stages[0].item_count == 1
    assert len(board.stages[0].items) == 1
    assert board.stages[0].items[0].document_name == "test.pdf"
    assert board.stages[0].items[0].entity_name == "ACME Corp"
    assert board.stages[0].items[0].amount == Decimal("100.50")

    # Check second stage
    assert board.stages[1].stage_key == "archiv"
    assert board.stages[1].item_count == 0
    assert len(board.stages[1].items) == 0


@pytest.mark.asyncio
async def test_add_item_to_first_stage(kanban_service, mock_db, company_id, document_id):
    """Test: add_item fuegt Dokument zur ersten Stage hinzu."""
    # Mock: No existing item
    mock_result_existing = MagicMock()
    mock_result_existing.scalar_one_or_none.return_value = None

    # Mock: Existing stages
    stage1 = WorkflowStage(
        id=uuid.uuid4(),
        company_id=company_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        stage_key="eingang",
        stage_name="Eingang",
        stage_order=1,
    )
    mock_result_stages = MagicMock()
    mock_result_stages.scalars.return_value.all.return_value = [stage1]

    # Mock: Created item with relationships
    item = DocumentWorkflowItem(
        id=uuid.uuid4(),
        company_id=company_id,
        document_id=document_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        current_stage_id=stage1.id,
        priority="normal",
        entered_stage_at=datetime.utcnow(),
    )
    item.document = Document(id=document_id, filename="test.pdf", extracted_data={})
    item.assignee = None

    mock_result_item = MagicMock()
    mock_result_item.scalar_one.return_value = item

    mock_db.execute.side_effect = [mock_result_existing, mock_result_stages, mock_result_item]

    # Execute
    item_data = await kanban_service.add_item(
        company_id=company_id,
        document_id=document_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        priority="high",
        assigned_to=None,
    )

    # Assert
    assert isinstance(item_data, KanbanItemData)
    assert item_data.document_id == document_id
    assert item_data.priority == "normal"  # From mock
    assert mock_db.add.call_count == 1
    assert mock_db.commit.call_count == 1


@pytest.mark.asyncio
async def test_move_item_updates_stage_and_previous(kanban_service, mock_db, company_id, user_id):
    """Test: move_item aktualisiert current_stage_id und previous_stage_id."""
    # Mock: Existing item
    old_stage_id = uuid.uuid4()
    new_stage_id = uuid.uuid4()

    item = DocumentWorkflowItem(
        id=uuid.uuid4(),
        company_id=company_id,
        document_id=uuid.uuid4(),
        workflow_type=WorkflowType.DOCUMENT.value,
        current_stage_id=old_stage_id,
        priority="normal",
        entered_stage_at=datetime.utcnow() - timedelta(hours=2),
    )
    item.document = Document(id=item.document_id, filename="test.pdf", extracted_data={})
    item.assignee = None
    item.stage = WorkflowStage(
        id=old_stage_id,
        company_id=company_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        stage_key="eingang",
        stage_name="Eingang",
        stage_order=1,
    )

    mock_result_item = MagicMock()
    mock_result_item.scalar_one_or_none.return_value = item

    # Mock: Target stage
    target_stage = WorkflowStage(
        id=new_stage_id,
        company_id=company_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        stage_key="pruefung",
        stage_name="Pruefung",
        stage_order=2,
    )
    mock_result_target = MagicMock()
    mock_result_target.scalar_one_or_none.return_value = target_stage

    mock_db.execute.side_effect = [mock_result_item, mock_result_target]

    # Mock WebSocket manager
    with patch("app.services.realtime.realtime_websocket_manager.get_realtime_ws_manager") as mock_ws:
        mock_manager = AsyncMock()
        mock_ws.return_value = mock_manager

        # Execute
        item_data = await kanban_service.move_item(item.id, new_stage_id, user_id)

        # Assert
        assert item.current_stage_id == new_stage_id
        assert item.previous_stage_id == old_stage_id
        assert item.entered_stage_at > datetime.utcnow() - timedelta(seconds=5)
        assert mock_db.commit.call_count == 1

        # Verify WebSocket broadcast
        assert mock_manager.broadcast_to_company.call_count == 1


@pytest.mark.asyncio
async def test_move_item_emits_websocket_event(kanban_service, mock_db, company_id, user_id):
    """Test: move_item emittiert WebSocket-Event."""
    # Mock: Item and stage
    old_stage_id = uuid.uuid4()
    new_stage_id = uuid.uuid4()

    item = DocumentWorkflowItem(
        id=uuid.uuid4(),
        company_id=company_id,
        document_id=uuid.uuid4(),
        workflow_type=WorkflowType.DOCUMENT.value,
        current_stage_id=old_stage_id,
        priority="normal",
        entered_stage_at=datetime.utcnow(),
    )
    item.document = Document(id=item.document_id, filename="test.pdf", extracted_data={})
    item.assignee = None
    item.stage = WorkflowStage(id=old_stage_id, company_id=company_id, workflow_type=WorkflowType.DOCUMENT.value, stage_key="eingang", stage_name="Eingang", stage_order=1)

    target_stage = WorkflowStage(id=new_stage_id, company_id=company_id, workflow_type=WorkflowType.DOCUMENT.value, stage_key="pruefung", stage_name="Pruefung", stage_order=2)

    mock_result_item = MagicMock()
    mock_result_item.scalar_one_or_none.return_value = item
    mock_result_target = MagicMock()
    mock_result_target.scalar_one_or_none.return_value = target_stage

    mock_db.execute.side_effect = [mock_result_item, mock_result_target]

    # Mock WebSocket
    with patch("app.services.realtime.realtime_websocket_manager.get_realtime_ws_manager") as mock_ws:
        mock_manager = AsyncMock()
        mock_ws.return_value = mock_manager

        # Execute
        await kanban_service.move_item(item.id, new_stage_id, user_id)

        # Assert WebSocket event
        mock_manager.broadcast_to_company.assert_called_once()
        call_args = mock_manager.broadcast_to_company.call_args
        assert call_args[1]["company_id"] == str(company_id)
        assert call_args[1]["message"].type == "kanban.item_moved"
        assert call_args[1]["message"].payload["workflow_type"] == WorkflowType.DOCUMENT.value


@pytest.mark.asyncio
async def test_configure_stages_validates_ordering(kanban_service, mock_db, company_id):
    """Test: configure_stages validiert eindeutige stage_orders."""
    # Duplicate stage_order
    stages = [
        {"stage_key": "eingang", "stage_name": "Eingang", "stage_order": 1},
        {"stage_key": "archiv", "stage_name": "Archiv", "stage_order": 1},  # Duplicate!
    ]

    # Execute & Assert
    with pytest.raises(ValueError, match="eindeutig"):
        await kanban_service.configure_stages(company_id, WorkflowType.DOCUMENT.value, stages)


@pytest.mark.asyncio
async def test_statistics_counts_items_per_stage(kanban_service, mock_db, company_id):
    """Test: get_statistics zaehlt Items pro Stage und berechnet avg time."""
    # Mock stages
    stage1 = WorkflowStage(
        id=uuid.uuid4(),
        company_id=company_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        stage_key="eingang",
        stage_name="Eingang",
        stage_order=1,
    )
    stage2 = WorkflowStage(
        id=uuid.uuid4(),
        company_id=company_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        stage_key="archiv",
        stage_name="Archiv",
        stage_order=2,
        is_final=True,
    )

    mock_result_stages = MagicMock()
    mock_result_stages.scalars.return_value.all.return_value = [stage1, stage2]

    # Mock counts and averages
    mock_result_count1 = MagicMock()
    mock_result_count1.scalar.return_value = 5
    mock_result_avg1 = MagicMock()
    mock_result_avg1.scalar.return_value = 2.5  # 2.5 hours avg

    mock_result_count2 = MagicMock()
    mock_result_count2.scalar.return_value = 10
    mock_result_avg2 = MagicMock()
    mock_result_avg2.scalar.return_value = None  # No items with time

    mock_db.execute.side_effect = [
        mock_result_stages,
        mock_result_count1,
        mock_result_avg1,
        mock_result_count2,
        mock_result_avg2,
    ]

    # Execute
    stats = await kanban_service.get_statistics(company_id, WorkflowType.DOCUMENT.value)

    # Assert
    assert len(stats) == 2
    assert stats[0].stage_key == "eingang"
    assert stats[0].item_count == 5
    assert stats[0].avg_time_in_stage_hours == 2.5

    assert stats[1].stage_key == "archiv"
    assert stats[1].item_count == 10
    assert stats[1].avg_time_in_stage_hours is None


@pytest.mark.asyncio
async def test_duplicate_document_workflow_rejected(kanban_service, mock_db, company_id, document_id):
    """Test: add_item lehnt Dokument ab das bereits im Workflow ist."""
    # Mock: Existing item
    existing_item = DocumentWorkflowItem(
        id=uuid.uuid4(),
        company_id=company_id,
        document_id=document_id,
        workflow_type=WorkflowType.DOCUMENT.value,
        current_stage_id=uuid.uuid4(),
        priority="normal",
        entered_stage_at=datetime.utcnow(),
    )
    mock_result_existing = MagicMock()
    mock_result_existing.scalar_one_or_none.return_value = existing_item

    mock_db.execute.return_value = mock_result_existing

    # Execute & Assert
    with pytest.raises(ValueError, match="bereits im Workflow"):
        await kanban_service.add_item(
            company_id=company_id,
            document_id=document_id,
            workflow_type=WorkflowType.DOCUMENT.value,
        )
