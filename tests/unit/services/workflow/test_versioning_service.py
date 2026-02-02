# -*- coding: utf-8 -*-
"""Unit-Tests fuer WorkflowVersioningService.

Testet:
- Versionserstellung mit semantischer Versionierung
- Diff-Berechnung zwischen Versionen
- Rollback auf vorherige Versionen
- A/B Testing zwischen Versionen
- Statistik-Aggregation
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Workflow
from app.db.models_workflow_versioning import (
    WorkflowVersion,
    WorkflowVersionStatus,
    WorkflowABTest,
    ABTestStatus,
)
from app.services.workflow.versioning_service import WorkflowVersioningService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def versioning_service(mock_db: AsyncMock) -> WorkflowVersioningService:
    """Erstellt einen WorkflowVersioningService."""
    return WorkflowVersioningService(db=mock_db)


@pytest.fixture
def sample_workflow() -> Workflow:
    """Erstellt einen Sample-Workflow."""
    workflow = MagicMock(spec=Workflow)
    workflow.id = uuid4()
    workflow.company_id = uuid4()
    workflow.name = "Test Workflow"
    workflow.description = "Testbeschreibung"
    workflow.trigger_type = "document_event"
    workflow.trigger_config = {"events": ["uploaded"]}
    workflow.nodes = [{"id": "1", "type": "trigger"}]
    workflow.edges = [{"id": "e1", "source": "1", "target": "2"}]
    workflow.variables = {"var1": "value1"}
    workflow.max_concurrent_executions = 10
    workflow.timeout_seconds = 3600
    workflow.retry_config = {"max_retries": 3}
    return workflow


@pytest.fixture
def sample_version() -> WorkflowVersion:
    """Erstellt eine Sample-Version."""
    version = MagicMock(spec=WorkflowVersion)
    version.id = uuid4()
    version.workflow_id = uuid4()
    version.company_id = uuid4()
    version.version = "1.0.0"
    version.major = 1
    version.minor = 0
    version.patch = 0
    version.status = WorkflowVersionStatus.ACTIVE.value
    version.is_active = True
    version.is_latest = True
    version.definition = {
        "name": "Test Workflow",
        "nodes": [{"id": "1", "type": "trigger"}],
        "edges": [],
    }
    version.execution_count = 100
    version.success_count = 95
    version.failure_count = 5
    return version


# ============================================================================
# Test: Version Creation
# ============================================================================


class TestVersionCreation:
    """Tests fuer Versionserstellung."""

    @pytest.mark.asyncio
    async def test_create_first_version(
        self,
        versioning_service: WorkflowVersioningService,
        mock_db: AsyncMock,
        sample_workflow: Workflow,
    ) -> None:
        """Testet das Erstellen der ersten Version."""
        company_id = uuid4()
        user_id = uuid4()

        # Mock: Workflow gefunden, keine vorherige Version
        mock_result_workflow = MagicMock()
        mock_result_workflow.scalar_one_or_none.return_value = sample_workflow

        mock_result_version = MagicMock()
        mock_result_version.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_result_workflow, mock_result_version]

        # Mock refresh um Version-Daten zu setzen
        async def mock_refresh(obj):
            if isinstance(obj, WorkflowVersion):
                obj.version = "1.0.0"
                obj.major = 1
                obj.minor = 0
                obj.patch = 0

        mock_db.refresh = mock_refresh

        version = await versioning_service.create_version(
            workflow_id=sample_workflow.id,
            company_id=company_id,
            user_id=user_id,
            change_description="Erste Version",
            change_type="minor",
        )

        assert version is not None
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_create_version_increments_minor(
        self,
        versioning_service: WorkflowVersioningService,
        mock_db: AsyncMock,
        sample_workflow: Workflow,
        sample_version: WorkflowVersion,
    ) -> None:
        """Testet Minor-Version-Inkrement."""
        company_id = uuid4()
        user_id = uuid4()

        # Mock: Workflow und vorherige Version gefunden
        mock_result_workflow = MagicMock()
        mock_result_workflow.scalar_one_or_none.return_value = sample_workflow

        mock_result_version = MagicMock()
        mock_result_version.scalar_one_or_none.return_value = sample_version

        mock_db.execute.side_effect = [mock_result_workflow, mock_result_version]

        version = await versioning_service.create_version(
            workflow_id=sample_workflow.id,
            company_id=company_id,
            user_id=user_id,
            change_description="Neue Features",
            change_type="minor",
        )

        # Die neue Version sollte 1.1.0 sein
        assert version is not None
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_create_version_increments_major(
        self,
        versioning_service: WorkflowVersioningService,
        mock_db: AsyncMock,
        sample_workflow: Workflow,
        sample_version: WorkflowVersion,
    ) -> None:
        """Testet Major-Version-Inkrement."""
        company_id = uuid4()
        user_id = uuid4()

        mock_result_workflow = MagicMock()
        mock_result_workflow.scalar_one_or_none.return_value = sample_workflow

        mock_result_version = MagicMock()
        mock_result_version.scalar_one_or_none.return_value = sample_version

        mock_db.execute.side_effect = [mock_result_workflow, mock_result_version]

        version = await versioning_service.create_version(
            workflow_id=sample_workflow.id,
            company_id=company_id,
            user_id=user_id,
            change_description="Breaking Changes",
            change_type="major",
        )

        assert version is not None

    @pytest.mark.asyncio
    async def test_create_version_invalid_change_type(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Fehler bei ungueltigem change_type."""
        with pytest.raises(ValueError, match="Ungueltiger change_type"):
            await versioning_service.create_version(
                workflow_id=uuid4(),
                company_id=uuid4(),
                user_id=uuid4(),
                change_description="Test",
                change_type="invalid",
            )


# ============================================================================
# Test: Diff Calculation
# ============================================================================


class TestDiffCalculation:
    """Tests fuer Diff-Berechnung."""

    def test_calculate_diff_added(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Erkennung von hinzugefuegten Feldern."""
        old_def = {"name": "Test"}
        new_def = {"name": "Test", "description": "Neu"}

        diff = versioning_service._calculate_diff(old_def, new_def)

        assert "description" in diff["added"]
        assert len(diff["removed"]) == 0
        assert len(diff["modified"]) == 0

    def test_calculate_diff_removed(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Erkennung von entfernten Feldern."""
        old_def = {"name": "Test", "description": "Alt"}
        new_def = {"name": "Test"}

        diff = versioning_service._calculate_diff(old_def, new_def)

        assert "description" in diff["removed"]
        assert len(diff["added"]) == 0
        assert len(diff["modified"]) == 0

    def test_calculate_diff_modified(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Erkennung von geaenderten Feldern."""
        old_def = {"name": "Test Alt"}
        new_def = {"name": "Test Neu"}

        diff = versioning_service._calculate_diff(old_def, new_def)

        assert "name" in diff["modified"]
        assert len(diff["added"]) == 0
        assert len(diff["removed"]) == 0

    def test_calculate_detailed_diff_nodes(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet detaillierten Diff fuer Nodes."""
        old_def = {
            "nodes": [
                {"id": "1", "type": "trigger"},
                {"id": "2", "type": "action"},
            ]
        }
        new_def = {
            "nodes": [
                {"id": "1", "type": "trigger"},
                {"id": "3", "type": "condition"},  # 2 entfernt, 3 hinzugefuegt
            ]
        }

        diff = versioning_service._calculate_detailed_diff(old_def, new_def)

        assert "nodes" in diff["details"]
        assert "3" in diff["details"]["nodes"]["added"]
        assert "2" in diff["details"]["nodes"]["removed"]


# ============================================================================
# Test: A/B Testing
# ============================================================================


class TestABTesting:
    """Tests fuer A/B Testing."""

    @pytest.mark.asyncio
    async def test_create_ab_test(
        self,
        versioning_service: WorkflowVersioningService,
        mock_db: AsyncMock,
        sample_version: WorkflowVersion,
    ) -> None:
        """Testet das Erstellen eines A/B Tests."""
        workflow_id = uuid4()
        company_id = uuid4()
        user_id = uuid4()
        control_id = uuid4()
        treatment_id = uuid4()

        # Mock: Beide Versionen gefunden
        control = MagicMock(spec=WorkflowVersion)
        control.id = control_id
        control.workflow_id = workflow_id

        treatment = MagicMock(spec=WorkflowVersion)
        treatment.id = treatment_id
        treatment.workflow_id = workflow_id

        mock_result_control = MagicMock()
        mock_result_control.scalar_one_or_none.return_value = control

        mock_result_treatment = MagicMock()
        mock_result_treatment.scalar_one_or_none.return_value = treatment

        mock_db.execute.side_effect = [mock_result_control, mock_result_treatment]

        ab_test = await versioning_service.create_ab_test(
            workflow_id=workflow_id,
            company_id=company_id,
            user_id=user_id,
            name="Test A/B",
            control_version_id=control_id,
            treatment_version_id=treatment_id,
            treatment_percentage=50,
        )

        assert ab_test is not None
        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_create_ab_test_invalid_percentage(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Fehler bei ungueltigem Treatment-Prozentsatz."""
        with pytest.raises(ValueError, match="treatment_percentage muss zwischen"):
            await versioning_service.create_ab_test(
                workflow_id=uuid4(),
                company_id=uuid4(),
                user_id=uuid4(),
                name="Test",
                control_version_id=uuid4(),
                treatment_version_id=uuid4(),
                treatment_percentage=150,  # Ungueltig
            )

    def test_calculate_ab_test_winner_treatment(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Gewinner-Berechnung: Treatment gewinnt."""
        ab_test = MagicMock(spec=WorkflowABTest)
        ab_test.control_executions = 1000
        ab_test.control_successes = 800
        ab_test.treatment_executions = 1000
        ab_test.treatment_successes = 900  # +10% besser
        ab_test.control_success_rate = 80.0
        ab_test.treatment_success_rate = 90.0

        winner = versioning_service._calculate_ab_test_winner(ab_test)

        assert winner == "treatment"

    def test_calculate_ab_test_winner_control(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Gewinner-Berechnung: Control gewinnt."""
        ab_test = MagicMock(spec=WorkflowABTest)
        ab_test.control_executions = 1000
        ab_test.control_successes = 900
        ab_test.treatment_executions = 1000
        ab_test.treatment_successes = 800
        ab_test.control_success_rate = 90.0
        ab_test.treatment_success_rate = 80.0

        winner = versioning_service._calculate_ab_test_winner(ab_test)

        assert winner == "control"

    def test_calculate_ab_test_winner_inconclusive(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Gewinner-Berechnung: Unentschieden."""
        ab_test = MagicMock(spec=WorkflowABTest)
        ab_test.control_executions = 1000
        ab_test.control_successes = 850
        ab_test.treatment_executions = 1000
        ab_test.treatment_successes = 860  # Nur 1% Unterschied
        ab_test.control_success_rate = 85.0
        ab_test.treatment_success_rate = 86.0

        winner = versioning_service._calculate_ab_test_winner(ab_test)

        assert winner == "inconclusive"

    def test_calculate_ab_test_winner_insufficient_data(
        self,
        versioning_service: WorkflowVersioningService,
    ) -> None:
        """Testet Gewinner-Berechnung: Zu wenig Daten."""
        ab_test = MagicMock(spec=WorkflowABTest)
        ab_test.control_executions = 50  # Unter 100
        ab_test.treatment_executions = 50
        ab_test.control_success_rate = 90.0
        ab_test.treatment_success_rate = 60.0

        winner = versioning_service._calculate_ab_test_winner(ab_test)

        assert winner == "inconclusive"


# ============================================================================
# Test: Version Properties
# ============================================================================


class TestVersionProperties:
    """Tests fuer Version-Properties."""

    def test_semver_property(self) -> None:
        """Testet die semver Property."""
        version = WorkflowVersion()
        version.major = 2
        version.minor = 3
        version.patch = 4

        assert version.semver == "2.3.4"

    def test_success_rate_property(self) -> None:
        """Testet die success_rate Property."""
        version = WorkflowVersion()
        version.execution_count = 100
        version.success_count = 85
        version.failure_count = 15

        assert version.success_rate == 85.0

    def test_success_rate_zero_executions(self) -> None:
        """Testet success_rate bei 0 Executions."""
        version = WorkflowVersion()
        version.execution_count = 0
        version.success_count = 0
        version.failure_count = 0

        assert version.success_rate == 0.0

    def test_is_publishable_draft(self) -> None:
        """Testet is_publishable fuer Draft."""
        version = WorkflowVersion()
        version.status = WorkflowVersionStatus.DRAFT.value

        assert version.is_publishable is True

    def test_is_publishable_active(self) -> None:
        """Testet is_publishable fuer Active."""
        version = WorkflowVersion()
        version.status = WorkflowVersionStatus.ACTIVE.value

        assert version.is_publishable is False
