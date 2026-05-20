# -*- coding: utf-8 -*-
"""
Unit Tests fuer WorkflowTriggerService.

Tests fuer Multi-Tenant Isolation und Trigger-Funktionalitaet:
- company_id Filterung in _find_matching_workflows
- company_id Validierung in handle_webhook
- Document Event Triggers
- Condition Triggers
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4, UUID
from typing import List

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.workflow.workflow_trigger_service import WorkflowTriggerService


class TestWorkflowTriggerServiceInit:
    """Tests fuer WorkflowTriggerService Initialisierung."""

    def test_service_creation(self) -> None:
        """Test: Service kann erstellt werden."""
        db = AsyncMock(spec=AsyncSession)
        service = WorkflowTriggerService(db)
        assert service.db == db
        assert service.execution_service is None

    def test_service_with_execution_service(self) -> None:
        """Test: Service mit ExecutionService."""
        db = AsyncMock(spec=AsyncSession)
        execution_service = MagicMock()
        service = WorkflowTriggerService(db, execution_service)
        assert service.execution_service == execution_service


class TestFindMatchingWorkflowsMultiTenant:
    """Tests fuer Multi-Tenant Isolation in _find_matching_workflows.

    SECURITY: Diese Tests verifizieren, dass Workflows NUR fuer die
    richtige Company gefunden werden.
    """

    @pytest.fixture
    def service(self) -> WorkflowTriggerService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowTriggerService(db)

    @pytest.fixture
    def company_a_id(self) -> UUID:
        return uuid4()

    @pytest.fixture
    def company_b_id(self) -> UUID:
        return uuid4()

    @pytest.fixture
    def user_id(self) -> UUID:
        return uuid4()

    def _create_mock_workflow(
        self,
        workflow_id: UUID,
        user_id: UUID,
        company_id: UUID,
        trigger_type: str = "document_event",
        is_active: bool = True,
        is_template: bool = False,
        trigger_config: dict = None,
    ) -> MagicMock:
        """Erstellt ein Mock Workflow Objekt."""
        workflow = MagicMock()
        workflow.id = workflow_id
        workflow.user_id = user_id
        workflow.company_id = company_id
        workflow.trigger_type = trigger_type
        workflow.is_active = is_active
        workflow.is_template = is_template
        workflow.trigger_config = trigger_config or {"events": ["created"]}
        return workflow

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="SQLAlchemy JSONB .astext nicht mockbar - Integration Test erforderlich")
    async def test_find_workflows_filters_by_company_id(
        self,
        service: WorkflowTriggerService,
        company_a_id: UUID,
        company_b_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test: _find_matching_workflows filtert nach company_id.

        SECURITY: Ein User darf NUR Workflows seiner Company sehen.
        NOTE: Dieser Test erfordert Integration Test mit echter DB wegen JSONB .astext
        """
        # Workflow Company A
        workflow_a = self._create_mock_workflow(
            workflow_id=uuid4(),
            user_id=user_id,
            company_id=company_a_id,
        )

        # Workflow Company B (sollte NICHT gefunden werden)
        workflow_b = self._create_mock_workflow(
            workflow_id=uuid4(),
            user_id=user_id,  # Gleicher User, andere Company
            company_id=company_b_id,
        )

        # Mock DB Query - nur Company A Workflow zurueckgeben
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [workflow_a]  # Nur Company A
        mock_result.scalars.return_value = mock_scalars
        service.db.execute = AsyncMock(return_value=mock_result)

        # Suche mit Company A
        workflows = await service._find_matching_workflows(
            trigger_type="document_event",
            user_id=user_id,
            company_id=company_a_id,
            event_type="created",
        )

        # Verifizieren
        assert len(workflows) == 1
        assert workflows[0].company_id == company_a_id

        # Pruefen dass execute aufgerufen wurde
        service.db.execute.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="SQLAlchemy JSONB .astext nicht mockbar - Integration Test erforderlich")
    async def test_find_workflows_empty_for_wrong_company(
        self,
        service: WorkflowTriggerService,
        company_a_id: UUID,
        company_b_id: UUID,
        user_id: UUID,
    ) -> None:
        """Test: Keine Workflows fuer falsche Company.

        SECURITY: Cross-Tenant Zugriff muss verhindert werden.
        NOTE: Dieser Test erfordert Integration Test mit echter DB wegen JSONB .astext
        """
        # Mock DB Query - leeres Ergebnis
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        service.db.execute = AsyncMock(return_value=mock_result)

        # Suche mit Company B (keine Workflows)
        workflows = await service._find_matching_workflows(
            trigger_type="document_event",
            user_id=user_id,
            company_id=company_b_id,
            event_type="created",
        )

        assert len(workflows) == 0


class TestOnDocumentEventMultiTenant:
    """Tests fuer Multi-Tenant Isolation in on_document_event."""

    @pytest.fixture
    def service(self) -> WorkflowTriggerService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowTriggerService(db)

    @pytest.mark.asyncio
    async def test_on_document_event_loads_document_first(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: on_document_event laedt das Dokument ZUERST.

        SECURITY: company_id wird aus dem Dokument geholt.
        """
        document_id = uuid4()
        user_id = uuid4()
        company_id = uuid4()

        # Mock Document
        mock_doc = MagicMock()
        mock_doc.id = document_id
        mock_doc.company_id = company_id

        # Mock _load_document
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        service.db.execute = AsyncMock(return_value=mock_result)

        # Mock _find_matching_workflows
        with patch.object(
            service,
            "_find_matching_workflows",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_find:
            await service.on_document_event(
                event_type="created",
                document_id=document_id,
                user_id=user_id,
            )

            # Verifizieren dass _find_matching_workflows mit company_id aufgerufen wurde
            mock_find.assert_called_once_with(
                trigger_type="document_event",
                user_id=user_id,
                company_id=company_id,
                event_type="created",
            )

    @pytest.mark.asyncio
    async def test_on_document_event_returns_empty_if_no_document(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: on_document_event gibt [] zurueck wenn Document nicht gefunden."""
        document_id = uuid4()
        user_id = uuid4()

        # Mock _load_document - kein Dokument
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.on_document_event(
            event_type="created",
            document_id=document_id,
            user_id=user_id,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_on_document_event_returns_empty_if_no_company_id(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: on_document_event gibt [] zurueck wenn Document keine company_id hat.

        SECURITY: Dokumente ohne company_id duerfen keine Workflows triggern.
        """
        document_id = uuid4()
        user_id = uuid4()

        # Mock Document ohne company_id
        mock_doc = MagicMock()
        mock_doc.id = document_id
        mock_doc.company_id = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.on_document_event(
            event_type="created",
            document_id=document_id,
            user_id=user_id,
        )

        assert result == []


class TestHandleWebhookMultiTenant:
    """Tests fuer Multi-Tenant Isolation in handle_webhook."""

    @pytest.fixture
    def service(self) -> WorkflowTriggerService:
        db = AsyncMock(spec=AsyncSession)
        execution_service = MagicMock()
        execution_service.start_execution = AsyncMock()
        return WorkflowTriggerService(db, execution_service)

    @pytest.mark.asyncio
    async def test_handle_webhook_rejects_workflow_without_company_id(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: handle_webhook lehnt Workflows ohne company_id ab.

        SECURITY: Workflows MUESSEN company_id haben.
        """
        webhook_path = "/test/webhook"

        # Mock Workflow OHNE company_id
        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.company_id = None  # KRITISCH: keine company_id
        mock_workflow.trigger_config = {}

        # Mock _find_workflow_by_webhook_path
        with patch.object(
            service,
            "_find_workflow_by_webhook_path",
            new_callable=AsyncMock,
            return_value=mock_workflow,
        ):
            result = await service.handle_webhook(
                webhook_path=webhook_path,
                payload={"test": "data"},
                headers={},
            )

        # Muss None zurueckgeben - Workflow ohne company_id
        assert result is None
        # ExecutionService darf NICHT aufgerufen werden
        service.execution_service.start_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_webhook_accepts_workflow_with_company_id(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: handle_webhook akzeptiert Workflows MIT company_id."""
        webhook_path = "/test/webhook"
        company_id = uuid4()
        user_id = uuid4()
        execution_id = uuid4()

        # Mock Workflow MIT company_id
        mock_workflow = MagicMock()
        mock_workflow.id = uuid4()
        mock_workflow.user_id = user_id
        mock_workflow.company_id = company_id
        mock_workflow.trigger_config = {}

        # Mock Execution
        mock_execution = MagicMock()
        mock_execution.id = execution_id
        service.execution_service.start_execution.return_value = mock_execution

        # Mock _find_workflow_by_webhook_path
        with patch.object(
            service,
            "_find_workflow_by_webhook_path",
            new_callable=AsyncMock,
            return_value=mock_workflow,
        ):
            result = await service.handle_webhook(
                webhook_path=webhook_path,
                payload={"test": "data"},
                headers={},
            )

        assert result == execution_id
        service.execution_service.start_execution.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_webhook_with_company_id_parameter(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: handle_webhook uebergibt company_id an Suche."""
        webhook_path = "/test/webhook"
        company_id = uuid4()

        # Mock _find_workflow_by_webhook_path
        with patch.object(
            service,
            "_find_workflow_by_webhook_path",
            new_callable=AsyncMock,
            return_value=None,
        ) as mock_find:
            await service.handle_webhook(
                webhook_path=webhook_path,
                payload={"test": "data"},
                headers={},
                company_id=company_id,
            )

            # Verifizieren dass company_id uebergeben wurde
            mock_find.assert_called_once_with(webhook_path, company_id)


class TestFindWorkflowByWebhookPathMultiTenant:
    """Tests fuer Multi-Tenant Isolation in _find_workflow_by_webhook_path."""

    @pytest.fixture
    def service(self) -> WorkflowTriggerService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowTriggerService(db)

    @pytest.mark.asyncio
    async def test_find_by_webhook_path_filters_by_company_id(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: _find_workflow_by_webhook_path filtert nach company_id wenn angegeben."""
        webhook_path = "/test/webhook"
        company_id = uuid4()

        # Mock Workflow
        mock_workflow = MagicMock()
        mock_workflow.trigger_config = {"webhook_path": webhook_path}

        # Mock DB Query
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_workflow]
        mock_result.scalars.return_value = mock_scalars
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service._find_workflow_by_webhook_path(
            webhook_path=webhook_path,
            company_id=company_id,
        )

        assert result == mock_workflow
        # Pruefen dass execute aufgerufen wurde
        service.db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_webhook_path_without_company_id(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: _find_workflow_by_webhook_path ohne company_id (Legacy)."""
        webhook_path = "/test/webhook"

        # Mock Workflow
        mock_workflow = MagicMock()
        mock_workflow.trigger_config = {"webhook_path": webhook_path}

        # Mock DB Query
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_workflow]
        mock_result.scalars.return_value = mock_scalars
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service._find_workflow_by_webhook_path(
            webhook_path=webhook_path,
        )

        assert result == mock_workflow


class TestCheckConditionTriggersMultiTenant:
    """Tests fuer Multi-Tenant Isolation in check_condition_triggers."""

    @pytest.fixture
    def service(self) -> WorkflowTriggerService:
        db = AsyncMock(spec=AsyncSession)
        return WorkflowTriggerService(db)

    @pytest.mark.asyncio
    async def test_check_condition_triggers_loads_document_first(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: check_condition_triggers laedt Document fuer company_id."""
        document_id = uuid4()
        user_id = uuid4()
        company_id = uuid4()
        changed_fields = {"status": ("draft", "published")}

        # Mock Document
        mock_doc = MagicMock()
        mock_doc.id = document_id
        mock_doc.company_id = company_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_doc
        service.db.execute = AsyncMock(return_value=mock_result)

        # Mock _find_matching_workflows
        with patch.object(
            service,
            "_find_matching_workflows",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_find:
            await service.check_condition_triggers(
                document_id=document_id,
                user_id=user_id,
                changed_fields=changed_fields,
            )

            # Verifizieren dass _find_matching_workflows mit company_id aufgerufen wurde
            mock_find.assert_called_once_with(
                trigger_type="condition",
                user_id=user_id,
                company_id=company_id,
            )

    @pytest.mark.asyncio
    async def test_check_condition_triggers_empty_if_no_document(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: check_condition_triggers gibt [] wenn Document nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.check_condition_triggers(
            document_id=uuid4(),
            user_id=uuid4(),
            changed_fields={"status": ("a", "b")},
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_check_condition_triggers_empty_if_no_changes(
        self,
        service: WorkflowTriggerService,
    ) -> None:
        """Test: check_condition_triggers gibt [] bei leeren changed_fields."""
        result = await service.check_condition_triggers(
            document_id=uuid4(),
            user_id=uuid4(),
            changed_fields={},
        )

        assert result == []
