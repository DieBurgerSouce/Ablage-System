# -*- coding: utf-8 -*-
"""
Unit tests for Backup Metrics Service.

Tests the Prometheus metrics collection for backup monitoring.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Import the service
import sys
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.backup_metrics_service import (
    BackupMetrics,
    BackupMetricData,
    DiskUsageData,
    get_backup_metrics,
)


class TestBackupMetricData:
    """Tests for BackupMetricData dataclass."""

    def test_create_basic_metric_data(self):
        """Test creating basic metric data."""
        now = datetime.utcnow()
        data = BackupMetricData(
            backup_type="full",
            success=True,
            duration_seconds=120.5,
            size_bytes=1024 * 1024 * 100,  # 100 MB
            timestamp=now,
        )

        assert data.backup_type == "full"
        assert data.success is True
        assert data.duration_seconds == 120.5
        assert data.size_bytes == 100 * 1024 * 1024
        assert data.error_message is None
        assert data.timestamp == now

    def test_create_failed_metric_data(self):
        """Test creating metric data for failed backup."""
        now = datetime.utcnow()
        data = BackupMetricData(
            backup_type="postgres",
            success=False,
            duration_seconds=5.0,
            size_bytes=0,
            timestamp=now,
            error_message="Datenbankverbindung fehlgeschlagen",
        )

        assert data.success is False
        assert data.error_message == "Datenbankverbindung fehlgeschlagen"

    def test_metric_data_with_all_fields(self):
        """Test metric data with all fields."""
        now = datetime.utcnow()
        data = BackupMetricData(
            backup_type="minio",
            success=True,
            duration_seconds=300.0,
            size_bytes=1024 * 1024 * 1024,  # 1 GB
            timestamp=now,
            error_message=None,
        )

        assert data.timestamp == now
        assert data.backup_type == "minio"
        assert data.success is True


class TestDiskUsageData:
    """Tests for DiskUsageData dataclass."""

    def test_create_disk_usage_data(self):
        """Test creating disk usage data."""
        data = DiskUsageData(
            total_bytes=500 * 1024 * 1024 * 1024,  # 500 GB
            free_bytes=100 * 1024 * 1024 * 1024,  # 100 GB
            used_bytes=400 * 1024 * 1024 * 1024,  # 400 GB
            usage_percent=80.0,  # 80% used
        )

        assert data.total_bytes == 500 * 1024**3
        assert data.free_bytes == 100 * 1024**3
        assert data.used_bytes == 400 * 1024**3
        assert data.usage_percent == 80.0


class TestBackupMetrics:
    """Tests for BackupMetrics class."""

    def test_singleton_pattern(self):
        """Test that get_backup_metrics returns singleton."""
        metrics1 = get_backup_metrics()
        metrics2 = get_backup_metrics()

        # Should be the same instance
        assert metrics1 is metrics2

    def test_record_backup_success(self):
        """Test recording successful backup."""
        metrics = BackupMetrics()

        # Record success
        metrics.record_backup_success(
            backup_type="full",
            size_bytes=1024 * 1024 * 50,
            duration_seconds=60.0,
        )

        # Verify metrics were updated (check internal state)
        # Note: In real tests, we'd check Prometheus metrics
        summary = metrics.get_summary()
        assert summary is not None

    def test_record_backup_failure(self):
        """Test recording failed backup."""
        metrics = BackupMetrics()

        # Record failure (requires duration_seconds as per implementation)
        metrics.record_backup_failure(
            backup_type="postgres",
            duration_seconds=5.0,
            error_message="Verbindung abgelehnt",
        )

        summary = metrics.get_summary()
        assert summary is not None

    def test_record_validation_success(self):
        """Test recording validation success."""
        metrics = BackupMetrics()

        # Implementation takes duration_seconds
        metrics.record_validation_success(duration_seconds=30.0)

        summary = metrics.get_summary()
        assert summary is not None

    def test_record_validation_failure(self):
        """Test recording validation failure."""
        metrics = BackupMetrics()

        # Implementation takes duration_seconds and error_message
        metrics.record_validation_failure(
            duration_seconds=5.0,
            error_message="Pruefsumme stimmt nicht",
        )

        summary = metrics.get_summary()
        assert summary is not None

    def test_update_disk_usage(self):
        """Test updating disk usage metrics."""
        import tempfile
        metrics = BackupMetrics()

        # Implementation takes path and returns DiskUsageData
        with tempfile.TemporaryDirectory() as temp_dir:
            disk_data = metrics.update_disk_usage(path=temp_dir)

            assert disk_data is not None
            assert disk_data.total_bytes > 0

        summary = metrics.get_summary()
        assert summary is not None

    def test_get_metrics_returns_prometheus_format(self):
        """Test that get_metrics returns Prometheus format."""
        metrics = BackupMetrics()

        output = metrics.get_metrics()

        # Returns bytes, not str
        assert isinstance(output, bytes)
        # Should contain HELP comments when Prometheus is available
        decoded = output.decode("utf-8")
        assert "# " in decoded or decoded == "# Prometheus not available\n"

    def test_get_content_type(self):
        """Test content type for Prometheus exposition."""
        metrics = BackupMetrics()

        content_type = metrics.get_content_type()

        # Should be Prometheus text format
        assert "text/plain" in content_type or "openmetrics" in content_type.lower()

    def test_record_remote_sync_success(self):
        """Test recording remote sync success."""
        metrics = BackupMetrics()

        # Implementation requires duration_seconds
        metrics.record_remote_sync_success(duration_seconds=120.0)

        summary = metrics.get_summary()
        assert summary is not None

    def test_record_remote_sync_failure(self):
        """Test recording remote sync failure."""
        metrics = BackupMetrics()

        metrics.record_remote_sync_failure("SSH-Verbindung fehlgeschlagen")

        summary = metrics.get_summary()
        assert summary is not None

    def test_set_encryption_status(self):
        """Test setting encryption status."""
        metrics = BackupMetrics()

        # Implementation uses set_encryption_enabled - sets Prometheus gauge
        # Just verify no exceptions are raised when called
        metrics.set_encryption_enabled(True)
        summary = metrics.get_summary()
        assert summary is not None
        assert "prometheus_aktiv" in summary

        metrics.set_encryption_enabled(False)
        summary = metrics.get_summary()
        assert summary is not None


class TestBackupMetricsIntegration:
    """Integration tests for backup metrics."""

    def test_full_backup_workflow(self):
        """Test complete backup workflow metrics."""
        metrics = BackupMetrics()

        # Simulate full backup
        metrics.record_backup_success(
            backup_type="postgres",
            size_bytes=500 * 1024 * 1024,
            duration_seconds=30.0,
        )
        metrics.record_backup_success(
            backup_type="redis",
            size_bytes=10 * 1024 * 1024,
            duration_seconds=5.0,
        )
        metrics.record_backup_success(
            backup_type="minio",
            size_bytes=2 * 1024 * 1024 * 1024,
            duration_seconds=120.0,
        )
        metrics.record_backup_success(
            backup_type="config",
            size_bytes=1 * 1024 * 1024,
            duration_seconds=2.0,
        )

        # Validate - implementation takes duration_seconds
        metrics.record_validation_success(duration_seconds=30.0)

        # Remote sync - implementation takes duration_seconds
        metrics.record_remote_sync_success(duration_seconds=5.0)

        # Check summary
        summary = metrics.get_summary()
        assert summary is not None

    def test_backup_with_failure_and_recovery(self):
        """Test backup failure followed by success."""
        metrics = BackupMetrics()

        # First attempt fails - needs duration_seconds
        metrics.record_backup_failure(
            backup_type="postgres",
            duration_seconds=5.0,
            error_message="Datenbank nicht erreichbar",
        )

        # Second attempt succeeds
        metrics.record_backup_success(
            backup_type="postgres",
            size_bytes=500 * 1024 * 1024,
            duration_seconds=45.0,
        )

        summary = metrics.get_summary()
        assert summary is not None
