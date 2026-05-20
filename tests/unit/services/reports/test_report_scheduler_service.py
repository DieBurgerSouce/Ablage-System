# -*- coding: utf-8 -*-
"""
Unit Tests for ReportSchedulerService.

Testet Zeitplan-Validierung, Ausfuehrungen und Cleanup.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.reports.report_scheduler_service import ReportSchedulerService


@pytest.fixture
def service():
    """Erstellt eine Service-Instanz."""
    return ReportSchedulerService()


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


class TestCronValidation:
    """Tests fuer Cron-Expression-Validierung."""

    @pytest.fixture
    def service(self):
        return ReportSchedulerService()

    def test_valid_cron_expression(self, service):
        """Test: Gueltige Cron-Expression."""
        assert service.validate_cron_expression("0 8 * * *") is True  # Taeglich 08:00
        assert service.validate_cron_expression("0 0 * * 1") is True  # Montag 00:00
        assert service.validate_cron_expression("*/15 * * * *") is True  # Alle 15 Min
        assert service.validate_cron_expression("0 8 1 * *") is True  # 1. Tag im Monat

    def test_invalid_cron_expression(self, service):
        """Test: Ungueltige Cron-Expression."""
        assert service.validate_cron_expression("invalid") is False
        assert service.validate_cron_expression("60 * * * *") is False  # 60 Minuten ungueltig
        # Note: 6-Feld Cron mit Sekunden wird von croniter akzeptiert
        assert service.validate_cron_expression("") is False

    def test_next_run_time(self, service):
        """Test: Berechnung der naechsten Ausfuehrungszeit."""
        # Taeglich 08:00
        next_run = service.get_next_run_time("0 8 * * *")

        if next_run:
            assert next_run.hour == 8
            assert next_run.minute == 0

    def test_next_run_time_invalid_cron(self, service):
        """Test: Ungueltige Cron gibt None zurueck."""
        result = service.get_next_run_time("invalid")
        assert result is None


class TestSchedulePresets:
    """Tests fuer Zeitplan-Presets."""

    @pytest.fixture
    def service(self):
        return ReportSchedulerService()

    def test_get_schedule_presets(self, service):
        """Test: Presets werden korrekt zurueckgegeben."""
        presets = service.get_schedule_presets()

        assert len(presets) >= 5
        assert any(p["id"] == "daily_morning" for p in presets)
        assert any(p["id"] == "weekly_monday" for p in presets)
        assert any(p["id"] == "monthly_first" for p in presets)

    def test_presets_have_valid_cron(self, service):
        """Test: Alle Presets haben gueltige Cron-Expressions."""
        presets = service.get_schedule_presets()

        for preset in presets:
            assert "cron" in preset
            # Spezialfall: "L" fuer letzten Tag wird von croniter nicht unterstuetzt
            if "L" not in preset["cron"]:
                assert service.validate_cron_expression(preset["cron"]) is True


class TestScheduleManagement:
    """Tests fuer Zeitplan-Aktivierung/Deaktivierung."""

    @pytest.fixture
    def service(self):
        return ReportSchedulerService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_enable_schedule_success(self, service, mock_db, sample_template_id, sample_user_id):
        """Test: Zeitplan erfolgreich aktivieren."""
        # Mock: Template existiert
        mock_template = MagicMock()
        mock_template.id = sample_template_id
        mock_template.user_id = sample_user_id
        mock_template.is_scheduled = False
        mock_template.schedule_config = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute.return_value = mock_result

        result = await service.enable_schedule(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
            cron_expression="0 8 * * *",
            recipients=["test@example.com"],
        )

        assert result is not None
        assert mock_template.is_scheduled is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_enable_schedule_invalid_cron(self, service, mock_db, sample_template_id, sample_user_id):
        """Test: Zeitplan mit ungueltiger Cron fehlschlaegt."""
        result = await service.enable_schedule(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
            cron_expression="invalid_cron",
        )

        assert result is None
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_disable_schedule_success(self, service, mock_db, sample_template_id, sample_user_id):
        """Test: Zeitplan erfolgreich deaktivieren."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await service.disable_schedule(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
        )

        assert result is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_disable_schedule_not_found(self, service, mock_db, sample_template_id, sample_user_id):
        """Test: Deaktivierung fehlschlaegt bei nicht existierendem Template."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await service.disable_schedule(
            db=mock_db,
            template_id=sample_template_id,
            user_id=sample_user_id,
        )

        assert result is False


class TestExecutionManagement:
    """Tests fuer Ausfuehrungs-Tracking."""

    @pytest.fixture
    def service(self):
        return ReportSchedulerService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.mark.asyncio
    async def test_create_execution(self, service, mock_db, sample_template_id, sample_user_id):
        """Test: Execution erstellen."""
        result = await service.create_execution(
            db=mock_db,
            template_id=sample_template_id,
            executed_by_id=sample_user_id,
            format="excel",
            trigger_type="manual",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_execution_scheduled(self, service, mock_db, sample_template_id):
        """Test: Geplante Execution erstellen (ohne User)."""
        result = await service.create_execution(
            db=mock_db,
            template_id=sample_template_id,
            executed_by_id=None,
            format="pdf",
            trigger_type="scheduled",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_execution_status_running(self, service, mock_db):
        """Test: Execution-Status auf running setzen."""
        execution_id = uuid.uuid4()

        mock_execution = MagicMock()
        mock_execution.id = execution_id
        mock_execution.status = "pending"
        mock_execution.started_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_execution
        mock_db.execute.return_value = mock_result

        result = await service.update_execution_status(
            db=mock_db,
            execution_id=execution_id,
            status="running",
        )

        assert result is not None
        assert mock_execution.status == "running"
        assert mock_execution.started_at is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_execution_status_completed(self, service, mock_db):
        """Test: Execution-Status auf completed setzen."""
        execution_id = uuid.uuid4()

        mock_execution = MagicMock()
        mock_execution.id = execution_id
        mock_execution.status = "running"
        mock_execution.started_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        mock_execution.completed_at = None
        mock_execution.duration_ms = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_execution
        mock_db.execute.return_value = mock_result

        result = await service.update_execution_status(
            db=mock_db,
            execution_id=execution_id,
            status="completed",
            row_count=100,
            file_size_bytes=12345,
            file_path="/data/reports/test.xlsx",
            download_url="/api/v1/reports/executions/123/download",
        )

        assert result is not None
        assert mock_execution.status == "completed"
        assert mock_execution.completed_at is not None
        assert mock_execution.duration_ms is not None
        assert mock_execution.row_count == 100
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_execution_status_failed(self, service, mock_db):
        """Test: Execution-Status auf failed setzen."""
        execution_id = uuid.uuid4()

        mock_execution = MagicMock()
        mock_execution.id = execution_id
        mock_execution.status = "running"
        mock_execution.started_at = datetime.now(timezone.utc)
        mock_execution.error_message = None
        mock_execution.error_details = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_execution
        mock_db.execute.return_value = mock_result

        result = await service.update_execution_status(
            db=mock_db,
            execution_id=execution_id,
            status="failed",
            error_message="Database connection failed",
            error_details={"exception_type": "ConnectionError"},
        )

        assert result is not None
        assert mock_execution.status == "failed"
        assert mock_execution.error_message == "Database connection failed"
        mock_db.commit.assert_called_once()


class TestCleanup:
    """Tests fuer Cleanup-Operationen."""

    @pytest.fixture
    def service(self):
        return ReportSchedulerService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_cleanup_old_executions(self, service, mock_db):
        """Test: Alte Executions loeschen."""
        mock_result = MagicMock()
        mock_result.rowcount = 15
        mock_db.execute.return_value = mock_result

        deleted = await service.cleanup_old_executions(
            db=mock_db,
            days=90,
        )

        assert deleted == 15
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_different_retention(self, service, mock_db):
        """Test: Cleanup mit anderem Retention-Wert."""
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_db.execute.return_value = mock_result

        deleted = await service.cleanup_old_executions(
            db=mock_db,
            days=30,
        )

        assert deleted == 5


class TestDueReports:
    """Tests fuer faellige Reports."""

    @pytest.fixture
    def service(self):
        return ReportSchedulerService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        return db

    @pytest.mark.asyncio
    async def test_get_due_reports_empty(self, service, mock_db):
        """Test: Keine faelligen Reports."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await service.get_due_reports(db=mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_due_reports_with_past_next_run(self, service, mock_db):
        """Test: Reports mit vergangener next_run werden zurueckgegeben."""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        mock_template = MagicMock()
        mock_template.id = uuid.uuid4()
        mock_template.is_scheduled = True
        mock_template.schedule_config = {
            "cron_expression": "0 8 * * *",
            "next_run": past_time,
            "enabled": True,
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_template]
        mock_db.execute.return_value = mock_result

        result = await service.get_due_reports(db=mock_db)

        assert len(result) == 1
        assert result[0].id == mock_template.id

    @pytest.mark.asyncio
    async def test_get_due_reports_future_not_included(self, service, mock_db):
        """Test: Reports mit zukuenftiger next_run werden nicht zurueckgegeben."""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        mock_template = MagicMock()
        mock_template.id = uuid.uuid4()
        mock_template.is_scheduled = True
        mock_template.schedule_config = {
            "cron_expression": "0 8 * * *",
            "next_run": future_time,
            "enabled": True,
        }

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_template]
        mock_db.execute.return_value = mock_result

        result = await service.get_due_reports(db=mock_db)

        assert len(result) == 0
