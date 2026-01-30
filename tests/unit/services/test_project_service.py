# -*- coding: utf-8 -*-
"""Unit Tests fuer ProjectService.

Vision 2026+ Feature #3: Projekt-Kontext (Multi-Chain Bundling)
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Result

from app.services.project_service import (
    ProjectService,
    ProjectSummary,
    ProjectDocumentStats,
    AutoAssignmentResult,
)
from app.db.models_project import (
    Project,
    ProjectMember,
    DocumentProjectAssignment,
    ProjectStatus,
    ProjectPriority,
    ProjectMemberRole,
    DocumentAssignmentType,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    db = AsyncMock(spec=AsyncSession)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def service() -> ProjectService:
    """Erstellt Service-Instanz."""
    return ProjectService()


@pytest.fixture
def company_id() -> uuid.UUID:
    """Test Company ID."""
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    """Test User ID."""
    return uuid.uuid4()


@pytest.fixture
def project_id() -> uuid.UUID:
    """Test Project ID."""
    return uuid.uuid4()


@pytest.fixture
def client_id() -> uuid.UUID:
    """Test Client (Entity) ID."""
    return uuid.uuid4()


@pytest.fixture
def mock_project(company_id: uuid.UUID, project_id: uuid.UUID) -> MagicMock:
    """Mock Project Objekt."""
    project = MagicMock(spec=Project)
    project.id = project_id
    project.company_id = company_id
    project.code = "PRJ-001"
    project.name = "Test Projekt"
    project.description = "Testbeschreibung"
    project.status = ProjectStatus.PLANNING.value
    project.priority = ProjectPriority.MEDIUM.value
    project.budget = Decimal("10000.00")
    project.budget_spent = Decimal("0.00")
    project.currency = "EUR"
    project.start_date = date.today()
    project.end_date = date.today() + timedelta(days=90)
    project.tags = ["test", "wichtig"]
    project.members = []
    project.document_assignments = []
    return project


# =============================================================================
# Test: CRUD Operations - Create
# =============================================================================


class TestCreateProject:
    """Tests fuer create_project Methode."""

    @pytest.mark.asyncio
    async def test_creates_project_successfully(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Erstellt Projekt erfolgreich."""
        project = await service.create_project(
            db=mock_db,
            company_id=company_id,
            code="PRJ-001",
            name="Neues Projekt",
            description="Beschreibung",
            budget=Decimal("5000.00"),
            created_by_id=user_id,
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_project_with_all_fields(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        client_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> None:
        """Erstellt Projekt mit allen Feldern."""
        start_date = date.today()
        end_date = date.today() + timedelta(days=180)

        project = await service.create_project(
            db=mock_db,
            company_id=company_id,
            code="PRJ-FULL",
            name="Vollstaendiges Projekt",
            description="Detaillierte Beschreibung",
            client_id=client_id,
            start_date=start_date,
            end_date=end_date,
            budget=Decimal("50000.00"),
            currency="EUR",
            manager_id=user_id,
            priority=ProjectPriority.HIGH.value,
            category="Entwicklung",
            tags=["wichtig", "2026"],
            created_by_id=user_id,
        )

        # Verifiziere dass Project-Objekt erstellt wurde
        add_call_args = mock_db.add.call_args
        assert add_call_args is not None

    @pytest.mark.asyncio
    async def test_creates_project_with_minimum_fields(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Erstellt Projekt mit minimalen Pflichtfeldern."""
        project = await service.create_project(
            db=mock_db,
            company_id=company_id,
            code="MIN-001",
            name="Minimales Projekt",
        )

        mock_db.add.assert_called_once()


# =============================================================================
# Test: CRUD Operations - Read
# =============================================================================


class TestGetProject:
    """Tests fuer get_project Methode."""

    @pytest.mark.asyncio
    async def test_returns_project_by_id(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Gibt Projekt nach ID zurueck."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.get_project(mock_db, project_id)

        assert result == mock_project
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_project(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
    ) -> None:
        """Gibt None fuer nicht existierendes Projekt zurueck."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_project(mock_db, uuid.uuid4())

        assert result is None

    @pytest.mark.asyncio
    async def test_includes_members_when_requested(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Laedt Members wenn angefordert."""
        mock_project.members = [MagicMock(spec=ProjectMember)]
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.get_project(
            mock_db,
            project_id,
            include_members=True,
        )

        assert result is not None


class TestGetProjectByCode:
    """Tests fuer get_project_by_code Methode."""

    @pytest.mark.asyncio
    async def test_returns_project_by_code(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Gibt Projekt nach Code zurueck."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.get_project_by_code(
            mock_db,
            company_id,
            "PRJ-001",
        )

        assert result == mock_project


class TestListProjects:
    """Tests fuer list_projects Methode."""

    @pytest.mark.asyncio
    async def test_lists_projects_with_pagination(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Listet Projekte mit Paginierung."""
        # Mock fuer Count-Query
        count_result = MagicMock()
        count_result.scalar.return_value = 5

        # Mock fuer Projects-Query
        projects_result = MagicMock()
        projects_result.scalars.return_value.all.return_value = [mock_project]

        mock_db.execute.side_effect = [count_result, projects_result]

        projects, total = await service.list_projects(
            mock_db,
            company_id,
            limit=10,
            offset=0,
        )

        assert total == 5
        assert len(projects) == 1

    @pytest.mark.asyncio
    async def test_filters_by_status(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Filtert nach Status."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        projects_result = MagicMock()
        projects_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, projects_result]

        projects, total = await service.list_projects(
            mock_db,
            company_id,
            status=ProjectStatus.ACTIVE.value,
        )

        assert total == 0
        assert projects == []

    @pytest.mark.asyncio
    async def test_search_by_name(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Sucht nach Projektnamen."""
        count_result = MagicMock()
        count_result.scalar.return_value = 1

        projects_result = MagicMock()
        projects_result.scalars.return_value.all.return_value = [mock_project]

        mock_db.execute.side_effect = [count_result, projects_result]

        projects, total = await service.list_projects(
            mock_db,
            company_id,
            search="Test",
        )

        assert total == 1


# =============================================================================
# Test: CRUD Operations - Update
# =============================================================================


class TestUpdateProject:
    """Tests fuer update_project Methode."""

    @pytest.mark.asyncio
    async def test_updates_project_name(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Aktualisiert Projektname."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.update_project(
            mock_db,
            project_id,
            name="Neuer Name",
        )

        assert result is not None
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_project(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
    ) -> None:
        """Gibt None fuer nicht existierendes Projekt zurueck."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.update_project(
            mock_db,
            uuid.uuid4(),
            name="Test",
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_ignores_non_allowed_fields(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Ignoriert nicht erlaubte Felder."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        # id sollte nicht aktualisierbar sein
        result = await service.update_project(
            mock_db,
            project_id,
            id=uuid.uuid4(),  # Nicht erlaubt
            name="Erlaubter Name",
        )

        assert result is not None


# =============================================================================
# Test: CRUD Operations - Delete
# =============================================================================


class TestDeleteProject:
    """Tests fuer delete_project Methode."""

    @pytest.mark.asyncio
    async def test_soft_delete_archives_project(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Soft-Delete archiviert Projekt."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.delete_project(
            mock_db,
            project_id,
            soft_delete=True,
        )

        assert result is True
        assert mock_project.status == ProjectStatus.ARCHIVED.value

    @pytest.mark.asyncio
    async def test_hard_delete_removes_project(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Hard-Delete loescht Projekt."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.delete_project(
            mock_db,
            project_id,
            soft_delete=False,
        )

        assert result is True
        mock_db.delete.assert_called_once_with(mock_project)

    @pytest.mark.asyncio
    async def test_returns_false_for_nonexistent_project(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
    ) -> None:
        """Gibt False fuer nicht existierendes Projekt zurueck."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.delete_project(mock_db, uuid.uuid4())

        assert result is False


# =============================================================================
# Test: Status Management
# =============================================================================


class TestStatusManagement:
    """Tests fuer Status-Verwaltung."""

    @pytest.mark.asyncio
    async def test_activate_project(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Aktiviert Projekt."""
        mock_project.actual_start_date = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.activate_project(mock_db, project_id)

        assert result is not None
        assert mock_project.status == ProjectStatus.ACTIVE.value
        assert mock_project.actual_start_date == date.today()

    @pytest.mark.asyncio
    async def test_complete_project(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        project_id: uuid.UUID,
        mock_project: MagicMock,
    ) -> None:
        """Schliesst Projekt ab."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_project
        mock_db.execute.return_value = mock_result

        result = await service.complete_project(mock_db, project_id)

        assert result is not None
        assert mock_project.status == ProjectStatus.COMPLETED.value
        assert mock_project.actual_end_date == date.today()


# =============================================================================
# Test: Enums
# =============================================================================


class TestEnums:
    """Tests fuer Enum-Typen."""

    def test_project_status_values(self) -> None:
        """ProjectStatus hat erwartete Werte."""
        assert ProjectStatus.PLANNING.value == "planning"
        assert ProjectStatus.ACTIVE.value == "active"
        assert ProjectStatus.ON_HOLD.value == "on_hold"
        assert ProjectStatus.COMPLETED.value == "completed"
        assert ProjectStatus.ARCHIVED.value == "archived"

    def test_project_priority_values(self) -> None:
        """ProjectPriority hat erwartete Werte."""
        assert ProjectPriority.LOW.value == "low"
        assert ProjectPriority.MEDIUM.value == "medium"
        assert ProjectPriority.HIGH.value == "high"
        assert ProjectPriority.CRITICAL.value == "critical"

    def test_member_role_values(self) -> None:
        """ProjectMemberRole hat erwartete Werte."""
        assert ProjectMemberRole.MEMBER.value == "member"
        assert ProjectMemberRole.LEAD.value == "lead"
        assert ProjectMemberRole.MANAGER.value == "manager"
        assert ProjectMemberRole.VIEWER.value == "viewer"


# =============================================================================
# Test: Data Classes
# =============================================================================


class TestDataClasses:
    """Tests fuer Data Classes."""

    def test_project_summary_creation(self) -> None:
        """ProjectSummary kann erstellt werden."""
        summary = ProjectSummary(
            total_projects=10,
            active_projects=5,
            completed_projects=3,
            on_hold_projects=2,
            total_budget=Decimal("100000.00"),
            total_spent=Decimal("45000.00"),
            overdue_count=1,
        )

        assert summary.total_projects == 10
        assert summary.active_projects == 5
        assert summary.total_budget == Decimal("100000.00")

    def test_project_document_stats_creation(self) -> None:
        """ProjectDocumentStats kann erstellt werden."""
        stats = ProjectDocumentStats(
            total_documents=50,
            invoices=20,
            contracts=10,
            correspondence=15,
            other=5,
            auto_assigned=30,
            manual_assigned=20,
        )

        assert stats.total_documents == 50
        assert stats.invoices == 20
        assert stats.auto_assigned == 30

    def test_auto_assignment_result_creation(self) -> None:
        """AutoAssignmentResult kann erstellt werden."""
        result = AutoAssignmentResult(
            document_id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            confidence=0.85,
            assignment_reason="Entity-Match: Kunde XYZ",
            assignment_type=DocumentAssignmentType.AUTO.value,
            auto_assigned=True,
        )

        assert result.confidence == 0.85
        assert result.auto_assigned is True


# =============================================================================
# Test: Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_handles_empty_project_list(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Verarbeitet leere Projektliste."""
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        projects_result = MagicMock()
        projects_result.scalars.return_value.all.return_value = []

        mock_db.execute.side_effect = [count_result, projects_result]

        projects, total = await service.list_projects(mock_db, company_id)

        assert total == 0
        assert projects == []

    @pytest.mark.asyncio
    async def test_handles_unicode_in_names(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Verarbeitet Unicode in Projektnamen."""
        await service.create_project(
            db=mock_db,
            company_id=company_id,
            code="UNI-001",
            name="Projekt mit Umlauten: äöüß",
            description="Beschreibung mit Sonderzeichen: €£¥",
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_large_budget_values(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Verarbeitet grosse Budget-Werte."""
        large_budget = Decimal("999999999.99")

        await service.create_project(
            db=mock_db,
            company_id=company_id,
            code="BIG-001",
            name="Grossprojekt",
            budget=large_budget,
        )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_empty_tags(
        self,
        service: ProjectService,
        mock_db: AsyncMock,
        company_id: uuid.UUID,
    ) -> None:
        """Verarbeitet leere Tags-Liste."""
        await service.create_project(
            db=mock_db,
            company_id=company_id,
            code="NOTAG-001",
            name="Projekt ohne Tags",
            tags=[],
        )

        mock_db.add.assert_called_once()
