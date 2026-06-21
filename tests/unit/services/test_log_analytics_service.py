# -*- coding: utf-8 -*-
"""
Tests fuer den Log Analytics Service.

Testet:
- Log Recording
- Metriken Berechnung
- Trend-Analyse
- Health Reports
- Dashboard-Daten
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.log_analytics_service import (
    LogAnalyticsService,
    LogEntry,
    LogLevel,
    LogMetrics,
    TrendAnalysis,
    TrendDirection,
    get_log_analytics_service,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def service():
    """Erstellt eine frische Service-Instanz."""
    return LogAnalyticsService(window_size_minutes=60)


@pytest.fixture
def service_with_logs(service):
    """Service mit vorhandenen Log-Eintraegen."""
    # Info Logs
    for i in range(50):
        service.record_log(
            level=LogLevel.INFO,
            source="app.main",
            message=f"Info message {i}",
        )

    # Warning Logs
    for i in range(20):
        service.record_log(
            level=LogLevel.WARNING,
            source="app.api",
            message=f"Warning message {i}",
        )

    # Error Logs
    for i in range(10):
        service.record_log(
            level=LogLevel.ERROR,
            source="app.services",
            message=f"Error message {i}",
        )

    # Critical Logs
    for i in range(5):
        service.record_log(
            level=LogLevel.CRITICAL,
            source="app.core",
            message=f"Critical message {i}",
        )

    return service


# =============================================================================
# LOG ENTRY TESTS
# =============================================================================


class TestLogEntry:
    """Tests fuer LogEntry Dataclass."""

    def test_log_entry_creation(self):
        """LogEntry sollte korrekt erstellt werden."""
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            level=LogLevel.INFO,
            source="test",
            message="Test message",
            metadata={"key": "value"},
        )

        assert entry.level == LogLevel.INFO
        assert entry.source == "test"
        assert entry.message == "Test message"
        assert entry.metadata == {"key": "value"}


# =============================================================================
# LOG RECORDING TESTS
# =============================================================================


class TestLogRecording:
    """Tests fuer Log Recording."""

    def test_record_log_single(self, service):
        """Einzelner Log-Eintrag sollte aufgezeichnet werden."""
        service.record_log(
            level=LogLevel.INFO,
            source="test",
            message="Test message",
        )

        metrics = service.get_metrics()
        assert metrics.total_entries == 1

    def test_record_log_multiple(self, service):
        """Mehrere Log-Eintraege sollten aufgezeichnet werden."""
        for i in range(100):
            service.record_log(
                level=LogLevel.INFO,
                source="test",
                message=f"Message {i}",
            )

        metrics = service.get_metrics()
        assert metrics.total_entries == 100

    def test_record_log_with_metadata(self, service):
        """Log mit Metadata sollte aufgezeichnet werden."""
        service.record_log(
            level=LogLevel.ERROR,
            source="test",
            message="Error",
            metadata={"error_code": 500, "user_id": "123"},
        )

        metrics = service.get_metrics()
        assert metrics.total_entries == 1
        assert metrics.by_level.get("error", 0) == 1


# =============================================================================
# METRICS CALCULATION TESTS
# =============================================================================


class TestMetricsCalculation:
    """Tests fuer Metriken-Berechnung."""

    def test_metrics_empty(self, service):
        """Leerer Service sollte leere Metriken zurueckgeben."""
        metrics = service.get_metrics()

        assert metrics.total_entries == 0
        assert metrics.error_rate_percent == 0
        assert metrics.warning_rate_percent == 0

    def test_metrics_by_level(self, service_with_logs):
        """Metriken sollten nach Level aggregiert werden."""
        metrics = service_with_logs.get_metrics()

        assert metrics.total_entries == 85  # 50 + 20 + 10 + 5
        assert metrics.by_level["info"] == 50
        assert metrics.by_level["warning"] == 20
        assert metrics.by_level["error"] == 10
        assert metrics.by_level["critical"] == 5

    def test_metrics_by_source(self, service_with_logs):
        """Metriken sollten nach Source aggregiert werden."""
        metrics = service_with_logs.get_metrics()

        assert metrics.by_source["app.main"] == 50
        assert metrics.by_source["app.api"] == 20
        assert metrics.by_source["app.services"] == 10
        assert metrics.by_source["app.core"] == 5

    def test_error_rate_calculation(self, service_with_logs):
        """Error Rate sollte korrekt berechnet werden."""
        metrics = service_with_logs.get_metrics()

        # Error Rate = (Error + Critical) / Total * 100
        expected_rate = (10 + 5) / 85 * 100
        assert abs(metrics.error_rate_percent - expected_rate) < 0.1

    def test_warning_rate_calculation(self, service_with_logs):
        """Warning Rate sollte korrekt berechnet werden."""
        metrics = service_with_logs.get_metrics()

        # Warning Rate = Warning / Total * 100
        expected_rate = 20 / 85 * 100
        assert abs(metrics.warning_rate_percent - expected_rate) < 0.1

    def test_metrics_with_time_window(self, service):
        """Metriken sollten auf Zeitfenster begrenzt werden."""
        # Alte Eintraege (werden ignoriert)
        for i in range(10):
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
                level=LogLevel.INFO,
                source="old",
                message=f"Old {i}",
            )
            service._entries.append(entry)

        # Neue Eintraege
        for i in range(5):
            service.record_log(LogLevel.INFO, "new", f"New {i}")

        # Alle Eintraege
        metrics_all = service.get_metrics(None)
        assert metrics_all.total_entries == 15

        # Nur letzte Stunde
        metrics_hour = service.get_metrics(60)
        assert metrics_hour.total_entries == 5


# =============================================================================
# TREND ANALYSIS TESTS
# =============================================================================


class TestTrendAnalysis:
    """Tests fuer Trend-Analyse."""

    def test_analyze_trends_stable(self, service_with_logs):
        """Stabile Metriken sollten als STABLE markiert werden."""
        # Speichere ersten Snapshot
        service_with_logs.store_metrics_snapshot()

        # Fuege aehnliche Anzahl Logs hinzu
        for i in range(85):
            service_with_logs.record_log(LogLevel.INFO, "test", f"More {i}")

        # Speichere zweiten Snapshot
        service_with_logs.store_metrics_snapshot()

        trends = service_with_logs.analyze_trends()

        # Mindestens ein Trend sollte existieren
        assert len(trends) > 0

    def test_analyze_trends_increasing(self, service):
        """Steigende Error Rate sollte erkannt werden."""
        # Erste Periode - wenige Errors
        service.record_log(LogLevel.INFO, "test", "Info 1")
        service.record_log(LogLevel.INFO, "test", "Info 2")
        service.store_metrics_snapshot()

        # Zweite Periode - viele Errors
        for i in range(10):
            service.record_log(LogLevel.ERROR, "test", f"Error {i}")
        service.store_metrics_snapshot()

        trends = service.analyze_trends()

        error_trend = next((t for t in trends if t.metric_name == "Error Rate"), None)
        assert error_trend is not None
        assert error_trend.direction in (TrendDirection.INCREASING, TrendDirection.VOLATILE)

    def test_anomaly_detection_high_error_rate(self, service):
        """Hohe Error Rate sollte als Anomalie erkannt werden."""
        # Nur Errors loggen
        for i in range(20):
            service.record_log(LogLevel.ERROR, "test", f"Error {i}")

        trends = service.analyze_trends()

        error_trend = next((t for t in trends if t.metric_name == "Error Rate"), None)
        assert error_trend is not None
        assert error_trend.is_anomaly is True
        assert error_trend.anomaly_reason is not None


# =============================================================================
# HEALTH REPORT TESTS
# =============================================================================


class TestHealthReport:
    """Tests fuer Health Reports."""

    def test_health_report_structure(self, service_with_logs):
        """Health Report sollte vollstaendige Struktur haben."""
        report = service_with_logs.get_health_report()

        assert report.timestamp is not None
        assert report.period_minutes == 60
        assert report.metrics is not None
        assert isinstance(report.trends, list)
        assert isinstance(report.alerts, list)
        assert isinstance(report.recommendations, list)

    def test_health_report_alerts_high_error_rate(self, service):
        """Alert sollte bei hoher Error Rate generiert werden."""
        # Erzeuge hohe Error Rate (>10%)
        for i in range(100):
            if i < 15:
                service.record_log(LogLevel.ERROR, "test", f"Error {i}")
            else:
                service.record_log(LogLevel.INFO, "test", f"Info {i}")

        report = service.get_health_report()

        # Sollte Alert haben
        assert len(report.alerts) > 0
        error_alert = next(
            (a for a in report.alerts if "error_rate" in a.get("type", "")),
            None
        )
        assert error_alert is not None

    def test_health_report_recommendations(self, service_with_logs):
        """Health Report sollte Empfehlungen enthalten."""
        report = service_with_logs.get_health_report()

        assert len(report.recommendations) > 0


# =============================================================================
# TOP ERRORS TESTS
# =============================================================================


class TestTopErrors:
    """Tests fuer Top Errors."""

    def test_get_top_errors_empty(self, service):
        """Leerer Service sollte keine Errors zurueckgeben."""
        errors = service.get_top_errors()
        assert len(errors) == 0

    def test_get_top_errors_sorted(self, service):
        """Top Errors sollten nach Haeufigkeit sortiert sein."""
        # Verschiedene Errors mit unterschiedlicher Haeufigkeit
        for i in range(10):
            service.record_log(LogLevel.ERROR, "api", "Error A")
        for i in range(5):
            service.record_log(LogLevel.ERROR, "api", "Error B")
        for i in range(2):
            service.record_log(LogLevel.ERROR, "api", "Error C")

        errors = service.get_top_errors()

        assert len(errors) == 3
        assert errors[0]["count"] >= errors[1]["count"]
        assert errors[1]["count"] >= errors[2]["count"]

    def test_get_top_errors_includes_critical(self, service):
        """Top Errors sollte auch Critical Level einschliessen."""
        service.record_log(LogLevel.CRITICAL, "core", "Critical error")
        service.record_log(LogLevel.ERROR, "api", "Normal error")

        errors = service.get_top_errors()

        assert len(errors) == 2
        critical_error = next((e for e in errors if e["level"] == "critical"), None)
        assert critical_error is not None


# =============================================================================
# VOLUME TIMELINE TESTS
# =============================================================================


class TestVolumeTimeline:
    """Tests fuer Volume Timeline."""

    def test_get_volume_timeline_structure(self, service_with_logs):
        """Timeline sollte korrekte Struktur haben."""
        timeline = service_with_logs.get_log_volume_by_time(
            interval_minutes=5,
            periods=6,
        )

        assert len(timeline) == 6
        for entry in timeline:
            assert "timestamp" in entry
            assert "total" in entry
            assert "by_level" in entry

    def test_get_volume_timeline_periods(self, service_with_logs):
        """Timeline sollte korrekte Anzahl Perioden haben."""
        timeline = service_with_logs.get_log_volume_by_time(
            interval_minutes=5,
            periods=12,
        )

        assert len(timeline) == 12


# =============================================================================
# SOURCE STATISTICS TESTS
# =============================================================================


class TestSourceStatistics:
    """Tests fuer Source Statistics."""

    def test_get_source_statistics(self, service_with_logs):
        """Source Statistics sollten alle Sources enthalten."""
        stats = service_with_logs.get_source_statistics()

        assert len(stats) == 4  # app.main, app.api, app.services, app.core
        sources = [s["source"] for s in stats]
        assert "app.main" in sources

    def test_source_statistics_sorted_by_total(self, service_with_logs):
        """Source Statistics sollten nach Total sortiert sein."""
        stats = service_with_logs.get_source_statistics()

        # Erster Eintrag sollte hoechste Total haben
        assert stats[0]["total"] >= stats[-1]["total"]

    def test_source_statistics_error_rate(self, service_with_logs):
        """Source Statistics sollten Error Rate enthalten."""
        stats = service_with_logs.get_source_statistics()

        # app.services hat nur Errors, also 100% Error Rate
        services_stat = next((s for s in stats if s["source"] == "app.services"), None)
        assert services_stat is not None
        assert services_stat["error_rate_percent"] == 100.0


# =============================================================================
# DASHBOARD DATA TESTS
# =============================================================================


class TestDashboardData:
    """Tests fuer Dashboard Data."""

    def test_get_dashboard_data_structure(self, service_with_logs):
        """Dashboard Data sollte vollstaendige Struktur haben."""
        data = service_with_logs.get_dashboard_data()

        assert "timestamp" in data
        assert "period_minutes" in data
        assert "summary" in data
        assert "by_level" in data
        assert "trends" in data
        assert "alerts" in data
        assert "recommendations" in data
        assert "top_errors" in data
        assert "volume_timeline" in data
        assert "source_stats" in data

    def test_get_dashboard_data_summary(self, service_with_logs):
        """Dashboard Summary sollte korrekte Werte haben."""
        data = service_with_logs.get_dashboard_data()
        summary = data["summary"]

        # F-31: Summary-Keys an DashboardSummary-Schema angeglichen
        # (total_entries, error_count, warning_count, error_rate_percent,
        # entries_per_minute) - kein warning_rate_percent mehr.
        assert summary["total_entries"] == 85
        assert "error_rate_percent" in summary
        assert "error_count" in summary
        assert "warning_count" in summary
        assert "entries_per_minute" in summary


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton-Verhalten."""

    def test_get_log_analytics_service_returns_instance(self):
        """get_log_analytics_service sollte Instanz zurueckgeben."""
        service1 = get_log_analytics_service()
        service2 = get_log_analytics_service()

        assert service1 is service2
        assert isinstance(service1, LogAnalyticsService)
