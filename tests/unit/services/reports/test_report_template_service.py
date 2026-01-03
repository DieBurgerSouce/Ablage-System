# -*- coding: utf-8 -*-
"""
Unit Tests for ReportTemplateService.

Testet CRUD-Operationen fuer Report-Templates, Spalten, Filter und Charts.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.reports.report_template_service import ReportTemplateService


@pytest.fixture
def service():
    """Erstellt eine Service-Instanz."""
    return ReportTemplateService()


@pytest.fixture
def mock_db():
    """Erstellt eine Mock-Datenbankverbindung."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def sample_user_id():
    """Sample User UUID."""
    return uuid.uuid4()


@pytest.fixture
def sample_template_id():
    """Sample Template UUID."""
    return uuid.uuid4()


class TestReportTemplateService:
    """Test-Klasse fuer ReportTemplateService."""

    @pytest.mark.asyncio
    async def test_create_template_success(self, service, mock_db, sample_user_id):
        """Test: Template erfolgreich erstellen."""
        # Arrange
        mock_db.refresh = AsyncMock()

        # Act
        result = await service.create_template(
            db=mock_db,
            user_id=sample_user_id,
            name="Test Report",
            description="Beschreibung",
            report_type="document",
            data_source="documents",
            default_format="excel",
        )

        # Assert
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_template_with_company(self, service, mock_db, sample_user_id):
        """Test: Template mit Company-ID erstellen."""
        company_id = uuid.uuid4()

        result = await service.create_template(
            db=mock_db,
            user_id=sample_user_id,
            name="Firmen-Report",
            report_type="finance",
            data_source="invoices",
            company_id=company_id,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, service, mock_db, sample_user_id, sample_template_id):
        """Test: Template nicht gefunden."""
        # Mock: Kein Template gefunden
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.get_template(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_template_access_denied(self, service, mock_db, sample_user_id, sample_template_id):
        """Test: Zugriff auf fremdes Template verweigert."""
        other_user_id = uuid.uuid4()

        # Mock: Template gehoert anderem User
        mock_template = MagicMock()
        mock_template.user_id = other_user_id
        mock_template.is_public = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        # Mock: Keine Freigabe
        mock_share_result = MagicMock()
        mock_share_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [mock_result, mock_share_result]

        result = await service.get_template(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_list_templates_user_only(self, service, mock_db, sample_user_id):
        """Test: Nur eigene Templates listen."""
        mock_template = MagicMock()
        mock_template.id = uuid.uuid4()
        mock_template.name = "Mein Report"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_template]
        mock_db.execute.return_value = mock_result

        result = await service.list_templates(
            db=mock_db,
            user_id=sample_user_id,
            include_public=False,
            include_shared=False,
        )

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_update_template_success(self, service, mock_db, sample_user_id, sample_template_id):
        """Test: Template erfolgreich aktualisieren."""
        # Mock: Template existiert und gehoert User
        mock_template = MagicMock()
        mock_template.id = sample_template_id
        mock_template.user_id = sample_user_id
        mock_template.name = "Alter Name"
        mock_template.is_public = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        result = await service.update_template(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
            name="Neuer Name",
            description="Neue Beschreibung",
        )

        assert result is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_template_success(self, service, mock_db, sample_user_id, sample_template_id):
        """Test: Template erfolgreich loeschen."""
        # Mock: Template existiert und gehoert User
        mock_template = MagicMock()
        mock_template.id = sample_template_id
        mock_template.user_id = sample_user_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        result = await service.delete_template(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
        )

        assert result is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_template_not_found(self, service, mock_db, sample_user_id, sample_template_id):
        """Test: Loeschen fehlgeschlagen - Template nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await service.delete_template(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
        )

        assert result is False


class TestColumnManagement:
    """Tests fuer Spalten-Management."""

    @pytest.fixture
    def service(self):
        return ReportTemplateService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_add_column_success(self, service, mock_db):
        """Test: Spalte hinzufuegen."""
        template_id = uuid.uuid4()

        result = await service.add_column(
            db=mock_db,
            template_id=template_id,
            field_path="document.filename",
            display_name="Dateiname",
            data_type="string",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_add_column_with_aggregation(self, service, mock_db):
        """Test: Spalte mit Aggregation hinzufuegen."""
        template_id = uuid.uuid4()

        result = await service.add_column(
            db=mock_db,
            template_id=template_id,
            field_path="invoice.total_gross",
            display_name="Bruttobetrag",
            data_type="currency",
            aggregation="sum",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestFilterManagement:
    """Tests fuer Filter-Management."""

    @pytest.fixture
    def service(self):
        return ReportTemplateService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_add_filter_success(self, service, mock_db):
        """Test: Filter hinzufuegen."""
        template_id = uuid.uuid4()

        result = await service.add_filter(
            db=mock_db,
            template_id=template_id,
            field_path="document.status",
            operator="equals",
            value="processed",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_add_filter_with_logic_operator(self, service, mock_db):
        """Test: Filter mit OR-Verknuepfung hinzufuegen."""
        template_id = uuid.uuid4()

        result = await service.add_filter(
            db=mock_db,
            template_id=template_id,
            field_path="document.type",
            operator="in",
            value=["invoice", "receipt"],
            logic_operator="OR",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestSharingManagement:
    """Tests fuer Report-Sharing."""

    @pytest.fixture
    def service(self):
        return ReportTemplateService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_share_template_success(self, service, mock_db):
        """Test: Template teilen."""
        template_id = uuid.uuid4()
        shared_by_id = uuid.uuid4()
        shared_with_user_id = uuid.uuid4()

        # Mock: Template existiert und gehoert User
        mock_template = MagicMock()
        mock_template.id = template_id
        mock_template.user_id = shared_by_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template

        # Mock: Keine existierende Freigabe
        mock_share_result = MagicMock()
        mock_share_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_result, mock_share_result]

        result = await service.share_template(
            db=mock_db,
            template_id=template_id,
            shared_by_id=shared_by_id,
            shared_with_user_id=shared_with_user_id,
            can_view=True,
            can_execute=True,
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_share_template_not_owner(self, service, mock_db):
        """Test: Template teilen fehlschlaegt wenn nicht Owner."""
        template_id = uuid.uuid4()
        owner_id = uuid.uuid4()
        other_user_id = uuid.uuid4()
        shared_with_user_id = uuid.uuid4()

        # Mock: Template gehoert anderem User
        mock_template = MagicMock()
        mock_template.id = template_id
        mock_template.user_id = owner_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        result = await service.share_template(
            db=mock_db,
            template_id=template_id,
            shared_by_id=other_user_id,  # Nicht der Owner
            shared_with_user_id=shared_with_user_id,
        )

        assert result is None
        mock_db.add.assert_not_called()
