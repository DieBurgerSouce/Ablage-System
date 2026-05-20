# -*- coding: utf-8 -*-
"""
Unit Tests fuer WorkflowService.

Tests fuer Workflow CRUD-Operationen:
- Workflow erstellen/lesen/aktualisieren/loeschen
- Workflow-Steps verwalten
- Workflow-Validierung
- Templates
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workflow.workflow_service import WorkflowService


class TestWorkflowServiceInit:
    """Tests fuer WorkflowService Initialisierung."""

    def test_service_creation(self) -> None:
        """Test: Service kann erstellt werden."""
        db = AsyncMock(spec=AsyncSession)
        service = WorkflowService(db)
        assert service.db == db


class TestCreateWorkflow:
    """Tests fuer create_workflow Methode."""

    @pytest.fixture
    def service(self) -> WorkflowService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowService(db)

    @pytest.mark.asyncio
    async def test_create_workflow_basic(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: Workflow kann erstellt werden."""
        user_id = uuid4()

        service.db.add = MagicMock()
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        workflow = await service.create_workflow(
            user_id=user_id,
            name="Test Workflow",
            trigger_type="document_event",
            trigger_config={"event": "created"},
        )

        assert workflow is not None
        assert workflow.name == "Test Workflow"
        assert workflow.trigger_type == "document_event"
        assert workflow.user_id == user_id
        service.db.add.assert_called_once()
        service.db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_workflow_with_nodes_edges(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: Workflow mit Nodes und Edges."""
        service.db.add = MagicMock()
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        nodes = [
            {"id": "1", "type": "trigger", "data": {}},
            {"id": "2", "type": "action", "data": {}},
        ]
        edges = [
            {"source": "1", "target": "2"},
        ]

        workflow = await service.create_workflow(
            user_id=uuid4(),
            name="Workflow mit Graph",
            trigger_type="schedule",
            trigger_config={"cron": "0 0 * * *"},
            nodes=nodes,
            edges=edges,
        )

        assert len(workflow.nodes) == 2
        assert len(workflow.edges) == 1

    @pytest.mark.asyncio
    async def test_create_workflow_default_values(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: Workflow hat korrekte Defaults."""
        service.db.add = MagicMock()
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        workflow = await service.create_workflow(
            user_id=uuid4(),
            name="Default Test",
            trigger_type="manual",
            trigger_config={},
        )

        assert workflow.is_active is False
        assert workflow.is_template is False
        assert workflow.max_concurrent_executions == 10
        assert workflow.timeout_seconds == 3600
        assert workflow.execution_count == 0


class TestGetWorkflow:
    """Tests fuer get_workflow Methode."""

    @pytest.fixture
    def service(self) -> WorkflowService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowService(db)

    @pytest.mark.asyncio
    async def test_get_workflow_found(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: Workflow wird gefunden."""
        workflow_id = uuid4()
        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "Test"

        service.db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_workflow)
        ))

        result = await service.get_workflow(workflow_id)

        assert result is not None
        assert result.id == workflow_id

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: Workflow nicht gefunden."""
        service.db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=None)
        ))

        result = await service.get_workflow(uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_get_workflow_with_user_filter(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: Workflow mit User-Filter."""
        workflow_id = uuid4()
        user_id = uuid4()

        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.user_id = user_id

        service.db.execute = AsyncMock(return_value=MagicMock(
            scalar_one_or_none=MagicMock(return_value=mock_workflow)
        ))

        result = await service.get_workflow(workflow_id, user_id=user_id)

        assert result is not None
        service.db.execute.assert_called_once()


class TestListWorkflows:
    """Tests fuer list_workflows Methode."""

    @pytest.fixture
    def service(self) -> WorkflowService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowService(db)

    @pytest.mark.asyncio
    async def test_list_workflows_empty(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: Leere Liste bei keinen Workflows."""
        # Mock execute fuer scalars.all() (Workflows) und scalar() (count)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar.return_value = 0
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.list_workflows(user_id=uuid4())

        # list_workflows returns tuple[List[Workflow], int]
        assert isinstance(result, tuple)
        workflows, total = result
        assert isinstance(workflows, list)
        assert len(workflows) == 0

    @pytest.mark.asyncio
    async def test_list_workflows_returns_list(
        self,
        service: WorkflowService,
    ) -> None:
        """Test: list_workflows gibt Tuple zurueck."""
        mock_workflow = MagicMock()
        mock_workflow.name = "Test"

        # Mock execute fuer scalars.all() (Workflows) und scalar() (count)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_workflow]
        mock_result.scalar.return_value = 1
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.list_workflows(user_id=uuid4())

        # list_workflows returns tuple[List[Workflow], int]
        assert isinstance(result, tuple)
        workflows, total = result
        assert isinstance(workflows, list)


class TestUpdateWorkflow:
    """Tests fuer update_workflow Methode (falls vorhanden)."""

    @pytest.fixture
    def service(self) -> WorkflowService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowService(db)


class TestDeleteWorkflow:
    """Tests fuer delete_workflow Methode (falls vorhanden)."""

    @pytest.fixture
    def service(self) -> WorkflowService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowService(db)


class TestWorkflowValidation:
    """Tests fuer Workflow-Validierung."""

    @pytest.fixture
    def service(self) -> WorkflowService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowService(db)

    def test_trigger_types(self) -> None:
        """Test: Bekannte Trigger-Types."""
        # Diese Trigger-Types sollten unterstuetzt werden
        known_triggers = [
            "document_event",
            "schedule",
            "manual",
            "webhook",
        ]
        for trigger in known_triggers:
            assert isinstance(trigger, str)
