# -*- coding: utf-8 -*-
"""
Unit tests for Backup Report Service.

Tests the backup report generation functionality.
"""

import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.backup_report_service import (
    BackupReportService,
    BackupReportData,
    get_backup_report_service,
)


class TestBackupReportData:
    """Tests for BackupReportData model."""

    def test_create_basic_report_data(self):
        """Test creating basic report data."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)

        data = BackupReportData(
            report_type="daily",
            generated_at=now,
            period_start=yesterday,
            period_end=now,
        )

        assert data.report_type == "daily"
        assert data.total_backups == 0
        assert data.successful_backups == 0
        assert data.success_rate == 0.0

    def test_report_data_with_statistics(self):
        """Test report data with backup statistics."""
        now = datetime.utcnow()

        data = BackupReportData(
            report_type="weekly",
            generated_at=now,
            period_start=now - timedelta(days=7),
            period_end=now,
            total_backups=7,
            successful_backups=6,
            failed_backups=1,
            success_rate=85.7,
            encryption_enabled=True,
        )

        assert data.total_backups == 7
        assert data.successful_backups == 6
        assert data.failed_backups == 1
        assert data.success_rate == 85.7
        assert data.encryption_enabled is True

    def test_report_data_with_issues(self):
        """Test report data with issues and warnings."""
        now = datetime.utcnow()

        data = BackupReportData(
            report_type="daily",
            generated_at=now,
            period_start=now - timedelta(days=1),
            period_end=now,
            issues=["Backup fehlgeschlagen", "Validierung fehlgeschlagen"],
            warnings=["Speicherplatz wird knapp"],
            recommendations=["Speicherplatz erweitern"],
        )

        assert len(data.issues) == 2
        assert len(data.warnings) == 1
        assert len(data.recommendations) == 1


class TestBackupReportService:
    """Tests for BackupReportService class."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as backup_dir:
            with tempfile.TemporaryDirectory() as report_dir:
                yield Path(backup_dir), Path(report_dir)

    def test_init_creates_report_directory(self, temp_dirs):
        """Test that initialization creates report directory."""
        backup_dir, report_dir = temp_dirs
        report_subdir = backup_dir / "reports"

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_subdir,
        )

        assert report_subdir.exists()

    def test_generate_daily_report(self, temp_dirs):
        """Test generating daily report."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        report = service.generate_daily_report()

        assert report is not None
        assert report.report_type == "daily"
        assert isinstance(report.generated_at, datetime)

    def test_generate_weekly_report(self, temp_dirs):
        """Test generating weekly report."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        report = service.generate_weekly_report()

        assert report is not None
        assert report.report_type == "weekly"
        # Weekly report covers 7 days
        period_length = (report.period_end - report.period_start).days
        assert period_length == 7

    def test_generate_monthly_report(self, temp_dirs):
        """Test generating monthly report."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        report = service.generate_monthly_report()

        assert report is not None
        assert report.report_type == "monthly"
        # Monthly report covers 30 days
        period_length = (report.period_end - report.period_start).days
        assert period_length == 30

    def test_report_saved_to_file(self, temp_dirs):
        """Test that report is saved to file."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        report = service.generate_daily_report()

        # Check that a report file was created
        report_files = list(report_dir.glob("daily_report_*.md"))
        assert len(report_files) == 1

    def test_report_format_markdown(self, temp_dirs):
        """Test that report is in markdown format."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        report = service.generate_daily_report()

        # Read the saved report
        report_files = list(report_dir.glob("daily_report_*.md"))
        content = report_files[0].read_text(encoding="utf-8")

        # Check markdown elements
        assert "# " in content  # Headers
        assert "**" in content  # Bold text
        assert "|" in content  # Tables

    def test_analyze_issues_low_success_rate(self, temp_dirs):
        """Test that low success rate generates issues."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        # Create report with low success rate
        now = datetime.utcnow()
        report = BackupReportData(
            report_type="daily",
            generated_at=now,
            period_start=now - timedelta(days=1),
            period_end=now,
            total_backups=10,
            successful_backups=8,
            failed_backups=2,
            success_rate=80.0,
        )

        service._analyze_issues(report)

        # Should have issues about success rate
        assert len(report.issues) > 0
        assert any("100%" in issue for issue in report.issues)

    def test_analyze_issues_high_disk_usage(self, temp_dirs):
        """Test that high disk usage generates warnings."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        now = datetime.utcnow()
        report = BackupReportData(
            report_type="daily",
            generated_at=now,
            period_start=now - timedelta(days=1),
            period_end=now,
            disk_usage_percent=85.0,
            success_rate=100.0,
            total_backups=1,
            successful_backups=1,
        )

        service._analyze_issues(report)

        # Should have warnings about disk space
        assert len(report.warnings) > 0
        assert any("Speicherplatz" in warning for warning in report.warnings)

    def test_analyze_issues_no_encryption(self, temp_dirs):
        """Test that disabled encryption generates warning."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        now = datetime.utcnow()
        report = BackupReportData(
            report_type="daily",
            generated_at=now,
            period_start=now - timedelta(days=1),
            period_end=now,
            encryption_enabled=False,
            success_rate=100.0,
            total_backups=1,
            successful_backups=1,
        )

        service._analyze_issues(report)

        # Should have warning about encryption
        assert any("Verschlüsselung" in warning for warning in report.warnings)

    def test_analyze_issues_stale_backup(self, temp_dirs):
        """Test that stale backup generates issue."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        now = datetime.utcnow()
        report = BackupReportData(
            report_type="daily",
            generated_at=now,
            period_start=now - timedelta(days=1),
            period_end=now,
            newest_backup_hours=30.0,  # Over 26 hours
            success_rate=100.0,
            total_backups=1,
            successful_backups=1,
        )

        service._analyze_issues(report)

        # Should have issue about stale backup
        assert len(report.issues) > 0

    def test_german_labels_in_report(self, temp_dirs):
        """Test that report uses German labels."""
        backup_dir, report_dir = temp_dirs

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        report = service.generate_daily_report()

        # Read the saved report
        report_files = list(report_dir.glob("daily_report_*.md"))
        content = report_files[0].read_text(encoding="utf-8")

        # Check for German words
        assert "Sicherungsbericht" in content or "Backup" in content
        assert "Erstellt" in content
        assert "Status" in content


class TestBackupReportServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_backup_report_service_singleton(self):
        """Test that get_backup_report_service returns singleton."""
        # Reset singleton for test
        import app.services.backup_report_service as module
        module._report_service = None

        service1 = get_backup_report_service()
        service2 = get_backup_report_service()

        assert service1 is service2


class TestBackupReportServiceWithMetrics:
    """Tests for BackupReportService with metrics integration."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as backup_dir:
            with tempfile.TemporaryDirectory() as report_dir:
                yield Path(backup_dir), Path(report_dir)

    @patch("app.services.backup_report_service.METRICS_AVAILABLE", True)
    @patch("app.services.backup_report_service.get_backup_metrics")
    def test_collect_from_metrics(self, mock_get_metrics, temp_dirs):
        """Test collecting data from metrics service."""
        backup_dir, report_dir = temp_dirs

        # Mock metrics
        mock_metrics = Mock()
        mock_metrics.get_summary.return_value = {
            "success_count": 7,
            "failure_count": 1,
            "validation_success_count": 6,
            "validation_failure_count": 0,
            "encryption_enabled": True,
        }
        mock_get_metrics.return_value = mock_metrics

        service = BackupReportService(
            backup_dir=backup_dir,
            report_dir=report_dir,
        )

        report = service.generate_daily_report()

        # Verify metrics were collected
        assert report.total_backups == 8
        assert report.successful_backups == 7
        assert report.failed_backups == 1
        assert report.encryption_enabled is True
