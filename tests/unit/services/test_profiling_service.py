# -*- coding: utf-8 -*-
"""
Tests fuer den Profiling Service.

Testet:
- Singleton-Verhalten
- Request-Tracking
- Statistik-Berechnung
- Slow-Request-Erkennung
- Memory-Snapshots
- Konfiguration
"""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.profiling_service import (
    EndpointStats,
    MemorySnapshot,
    ProfileBlock,
    ProfilingLevel,
    ProfilingService,
    SlowRequest,
    get_profiling_service,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def fresh_service():
    """Erstellt eine frische Service-Instanz fuer isolierte Tests."""
    # Reset Singleton
    ProfilingService._instance = None

    service = ProfilingService()
    service._profiling_level = ProfilingLevel.BASIC
    service._slow_request_threshold_ms = 1000.0
    service._endpoint_stats = {}
    service._slow_requests = []
    service._memory_snapshots = []
    service._excluded_paths = {"/health", "/metrics"}

    yield service

    # Cleanup
    ProfilingService._instance = None


# =============================================================================
# SINGLETON TESTS
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self):
        """Singleton sollte immer die gleiche Instanz zurueckgeben."""
        ProfilingService._instance = None

        service1 = ProfilingService()
        service2 = ProfilingService()

        assert service1 is service2

        ProfilingService._instance = None

    def test_get_profiling_service_returns_singleton(self):
        """get_profiling_service sollte Singleton zurueckgeben."""
        ProfilingService._instance = None

        service1 = get_profiling_service()
        service2 = get_profiling_service()

        assert service1 is service2

        ProfilingService._instance = None


# =============================================================================
# ENDPOINT STATS TESTS
# =============================================================================


class TestEndpointStats:
    """Tests fuer EndpointStats Klasse."""

    def test_add_timing_updates_stats(self):
        """add_timing sollte Statistiken korrekt aktualisieren."""
        stats = EndpointStats(endpoint="/test", method="GET")

        stats.add_timing(100.0)
        stats.add_timing(200.0)
        stats.add_timing(150.0)

        assert stats.request_count == 3
        assert stats.total_time_ms == 450.0
        assert stats.min_time_ms == 100.0
        assert stats.max_time_ms == 200.0

    def test_add_timing_with_error(self):
        """add_timing sollte Fehler zaehlen."""
        stats = EndpointStats(endpoint="/test", method="GET")

        stats.add_timing(100.0, is_error=True)
        stats.add_timing(200.0, is_error=False)
        stats.add_timing(150.0, is_error=True)

        assert stats.request_count == 3
        assert stats.error_count == 2

    def test_get_percentile(self):
        """get_percentile sollte korrekte Werte berechnen."""
        stats = EndpointStats(endpoint="/test", method="GET")

        # 100 Timings von 1-100
        for i in range(1, 101):
            stats.add_timing(float(i))

        # Perzentile sind approximiert, erlauben kleine Abweichungen
        assert 50 <= stats.get_percentile(50) <= 52
        assert 94 <= stats.get_percentile(95) <= 96
        assert 98 <= stats.get_percentile(99) <= 100

    def test_get_percentile_empty(self):
        """get_percentile sollte 0 bei leeren Stats zurueckgeben."""
        stats = EndpointStats(endpoint="/test", method="GET")

        assert stats.get_percentile(50) == 0.0

    def test_to_dict(self):
        """to_dict sollte vollstaendiges Dictionary zurueckgeben."""
        stats = EndpointStats(endpoint="/api/test", method="POST")
        stats.add_timing(100.0)
        stats.add_timing(200.0)

        result = stats.to_dict()

        assert result["endpoint"] == "/api/test"
        assert result["method"] == "POST"
        assert result["request_count"] == 2
        assert result["avg_time_ms"] == 150.0
        assert result["min_time_ms"] == 100.0
        assert result["max_time_ms"] == 200.0

    def test_buffer_limits(self):
        """Buffer sollte auf 1000 Eintraege begrenzt sein."""
        stats = EndpointStats(endpoint="/test", method="GET")

        for i in range(1500):
            stats.add_timing(float(i))

        assert len(stats.times) == 1000
        # Aelteste sollten entfernt worden sein
        assert stats.times[0] >= 500


# =============================================================================
# SLOW REQUEST TESTS
# =============================================================================


class TestSlowRequest:
    """Tests fuer SlowRequest Klasse."""

    def test_to_dict(self):
        """to_dict sollte vollstaendiges Dictionary zurueckgeben."""
        slow = SlowRequest(
            timestamp=datetime.now(timezone.utc),
            endpoint="/api/slow",
            method="GET",
            duration_ms=2500.0,
            status_code=200,
            request_id="req-123",
            user_id="user-456",
            memory_before_mb=100.0,
            memory_after_mb=150.0,
        )

        result = slow.to_dict()

        assert result["endpoint"] == "/api/slow"
        assert result["duration_ms"] == 2500.0
        assert result["request_id"] == "req-123"
        assert result["memory_delta_mb"] == 50.0


# =============================================================================
# MEMORY SNAPSHOT TESTS
# =============================================================================


class TestMemorySnapshot:
    """Tests fuer MemorySnapshot Klasse."""

    def test_to_dict(self):
        """to_dict sollte vollstaendiges Dictionary zurueckgeben."""
        snapshot = MemorySnapshot(
            timestamp=datetime.now(timezone.utc),
            rss_mb=500.5,
            vms_mb=1000.0,
            shared_mb=100.0,
            gpu_used_mb=2000.0,
            context="test_context",
        )

        result = snapshot.to_dict()

        assert result["rss_mb"] == 500.5
        assert result["vms_mb"] == 1000.0
        assert result["gpu_used_mb"] == 2000.0
        assert result["context"] == "test_context"


# =============================================================================
# PROFILING SERVICE TESTS
# =============================================================================


class TestProfilingServiceRecording:
    """Tests fuer Request-Recording."""

    def test_record_request_basic(self, fresh_service):
        """record_request sollte Request aufzeichnen."""
        fresh_service.record_request(
            endpoint="/api/test",
            method="GET",
            duration_ms=100.0,
            status_code=200,
        )

        stats = fresh_service.get_endpoint_stats()
        assert len(stats) == 1
        assert stats[0]["endpoint"] == "/api/test"
        assert stats[0]["request_count"] == 1

    def test_record_request_excluded_paths(self, fresh_service):
        """Excluded Paths sollten nicht aufgezeichnet werden."""
        fresh_service.record_request(
            endpoint="/health",
            method="GET",
            duration_ms=10.0,
            status_code=200,
        )

        stats = fresh_service.get_endpoint_stats()
        assert len(stats) == 0

    def test_record_request_profiling_off(self, fresh_service):
        """Bei Profiling OFF sollten keine Requests aufgezeichnet werden."""
        fresh_service._profiling_level = ProfilingLevel.OFF

        fresh_service.record_request(
            endpoint="/api/test",
            method="GET",
            duration_ms=100.0,
            status_code=200,
        )

        stats = fresh_service.get_endpoint_stats()
        assert len(stats) == 0

    def test_record_slow_request(self, fresh_service):
        """Langsame Requests sollten separat aufgezeichnet werden."""
        fresh_service._slow_request_threshold_ms = 500.0

        fresh_service.record_request(
            endpoint="/api/slow",
            method="GET",
            duration_ms=1000.0,
            status_code=200,
            request_id="req-slow",
        )

        slow_requests = fresh_service.get_slow_requests()
        assert len(slow_requests) == 1
        assert slow_requests[0]["duration_ms"] == 1000.0

    def test_slow_request_buffer_limit(self, fresh_service):
        """Slow-Request-Buffer sollte begrenzt sein."""
        fresh_service._slow_request_threshold_ms = 100.0
        fresh_service._max_slow_requests = 10

        for i in range(20):
            fresh_service.record_request(
                endpoint="/api/slow",
                method="GET",
                duration_ms=200.0 + i,
                status_code=200,
            )

        slow_requests = fresh_service.get_slow_requests(limit=100)
        assert len(slow_requests) == 10

    def test_record_request_with_memory(self, fresh_service):
        """Memory-Tracking sollte aufgezeichnet werden."""
        fresh_service._slow_request_threshold_ms = 100.0

        fresh_service.record_request(
            endpoint="/api/test",
            method="POST",
            duration_ms=500.0,
            status_code=201,
            memory_before_mb=100.0,
            memory_after_mb=150.0,
        )

        slow_requests = fresh_service.get_slow_requests()
        assert len(slow_requests) == 1
        assert slow_requests[0]["memory_delta_mb"] == 50.0


class TestProfilingServiceStats:
    """Tests fuer Statistik-Abfragen."""

    def test_get_endpoint_stats_with_filter(self, fresh_service):
        """get_endpoint_stats sollte Filter unterstuetzen."""
        fresh_service.record_request("/api/users", "GET", 100.0, 200)
        fresh_service.record_request("/api/users", "POST", 150.0, 201)
        fresh_service.record_request("/api/docs", "GET", 80.0, 200)

        # Filter nach Endpoint
        stats = fresh_service.get_endpoint_stats(endpoint="/api/users")
        assert len(stats) == 2

        # Filter nach Method
        stats = fresh_service.get_endpoint_stats(method="GET")
        assert len(stats) == 2

    def test_get_endpoint_stats_sorting(self, fresh_service):
        """get_endpoint_stats sollte korrekt sortieren."""
        for i in range(5):
            fresh_service.record_request("/api/hot", "GET", 50.0, 200)

        fresh_service.record_request("/api/slow", "GET", 500.0, 200)

        # Nach Request-Count sortieren
        stats = fresh_service.get_endpoint_stats(sort_by="request_count")
        assert stats[0]["endpoint"] == "/api/hot"

        # Nach avg_time sortieren
        stats = fresh_service.get_endpoint_stats(sort_by="avg_time_ms")
        assert stats[0]["endpoint"] == "/api/slow"

    def test_get_hot_paths(self, fresh_service):
        """get_hot_paths sollte Hot Paths korrekt identifizieren."""
        for i in range(100):
            fresh_service.record_request("/api/popular", "GET", 50.0, 200)
        for i in range(10):
            fresh_service.record_request("/api/less_popular", "GET", 50.0, 200)

        hot_paths = fresh_service.get_hot_paths(limit=5)

        assert len(hot_paths) == 2
        assert hot_paths[0]["endpoint"] == "/api/popular"
        assert hot_paths[0]["rank"] == 1

    def test_get_summary(self, fresh_service):
        """get_summary sollte korrekten Ueberblick liefern."""
        fresh_service._slow_request_threshold_ms = 100.0

        for i in range(10):
            fresh_service.record_request("/api/test", "GET", 50.0, 200)
        fresh_service.record_request("/api/test", "GET", 200.0, 200)  # Slow
        fresh_service.record_request("/api/test", "GET", 50.0, 500)  # Error

        summary = fresh_service.get_summary()

        assert summary["total_requests"] == 12
        assert summary["total_errors"] == 1
        assert summary["total_slow_requests"] == 1
        assert summary["profiling_level"] == "basic"


class TestProfilingServiceMemory:
    """Tests fuer Memory-Snapshots."""

    @patch("psutil.Process")
    def test_take_memory_snapshot(self, mock_process, fresh_service):
        """take_memory_snapshot sollte Snapshot erstellen."""
        mock_mem = MagicMock()
        mock_mem.rss = 500 * 1024 * 1024  # 500 MB
        mock_mem.vms = 1000 * 1024 * 1024  # 1000 MB
        mock_mem.shared = 100 * 1024 * 1024  # 100 MB
        mock_process.return_value.memory_info.return_value = mock_mem

        snapshot = fresh_service.take_memory_snapshot(context="test")

        assert snapshot.rss_mb == pytest.approx(500.0, rel=0.01)
        assert snapshot.vms_mb == pytest.approx(1000.0, rel=0.01)
        assert snapshot.context == "test"

    def test_get_memory_snapshots(self, fresh_service):
        """get_memory_snapshots sollte Snapshots zurueckgeben."""
        import time as time_module
        from datetime import timedelta

        # Manuell Snapshots hinzufuegen mit verschiedenen Timestamps
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            snapshot = MemorySnapshot(
                timestamp=base_time + timedelta(seconds=i),  # Steigende Timestamps
                rss_mb=100.0 + i,
                vms_mb=200.0,
                shared_mb=50.0,
            )
            fresh_service._memory_snapshots.append(snapshot)

        snapshots = fresh_service.get_memory_snapshots(limit=3)

        assert len(snapshots) == 3
        # Neueste zuerst (hoechster Timestamp = index 4 = rss_mb 104.0)
        assert snapshots[0]["rss_mb"] == 104.0


class TestProfilingServiceConfig:
    """Tests fuer Konfiguration."""

    def test_configure_level(self, fresh_service):
        """configure sollte Level aendern."""
        config = fresh_service.configure(level=ProfilingLevel.DETAILED)

        assert config["profiling_level"] == "detailed"
        assert fresh_service._profiling_level == ProfilingLevel.DETAILED

    def test_configure_threshold(self, fresh_service):
        """configure sollte Schwellwert aendern."""
        config = fresh_service.configure(slow_threshold_ms=2000.0)

        assert config["slow_request_threshold_ms"] == 2000.0
        assert fresh_service._slow_request_threshold_ms == 2000.0

    def test_reset_stats(self, fresh_service):
        """reset_stats sollte alle Daten loeschen."""
        # Daten hinzufuegen
        fresh_service.record_request("/api/test", "GET", 100.0, 200)
        fresh_service._slow_requests.append(
            SlowRequest(
                timestamp=datetime.now(timezone.utc),
                endpoint="/test",
                method="GET",
                duration_ms=2000.0,
                status_code=200,
            )
        )
        fresh_service._memory_snapshots.append(
            MemorySnapshot(
                timestamp=datetime.now(timezone.utc),
                rss_mb=100.0,
                vms_mb=200.0,
                shared_mb=50.0,
            )
        )

        result = fresh_service.reset_stats()

        # Service-interne Dict-Keys nutzen UTF-8-Umlaute (gelöschte_*);
        # die API-Schicht (profiling.py) mappt sie auf ASCII-Feldnamen
        # für die externe HTTP-Antwort. Hier wird der echte interne Vertrag geprüft.
        assert result["gelöschte_endpoints"] == 1
        assert result["gelöschte_langsame_requests"] == 1
        assert result["gelöschte_snapshots"] == 1
        assert len(fresh_service._endpoint_stats) == 0


# =============================================================================
# PROFILE BLOCK TESTS
# =============================================================================


class TestProfileBlock:
    """Tests fuer ProfileBlock Context Manager."""

    def test_profile_block_basic(self, fresh_service):
        """ProfileBlock sollte Timing aufzeichnen."""
        with ProfileBlock(name="test_block", endpoint="/internal/test"):
            time.sleep(0.01)  # 10ms

        stats = fresh_service.get_endpoint_stats(endpoint="/internal")
        assert len(stats) == 1
        assert stats[0]["request_count"] == 1
        assert stats[0]["avg_time_ms"] > 10  # Mindestens 10ms

    def test_profile_block_with_exception(self, fresh_service):
        """ProfileBlock sollte auch bei Exceptions aufzeichnen."""
        with pytest.raises(ValueError):
            with ProfileBlock(name="failing_block", endpoint="/internal/fail"):
                raise ValueError("Test error")

        stats = fresh_service.get_endpoint_stats(endpoint="/internal/fail")
        assert len(stats) == 1
        # 500 Status-Code bei Exception

    def test_profile_block_duration(self, fresh_service):
        """ProfileBlock sollte Dauer korrekt messen."""
        with ProfileBlock(name="timed_block", endpoint="/internal/timed") as block:
            time.sleep(0.05)  # 50ms

        assert block.duration_ms >= 50


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestProfilingIntegration:
    """Integration Tests."""

    def test_full_profiling_workflow(self):
        """Kompletter Profiling-Workflow."""
        ProfilingService._instance = None
        service = ProfilingService()
        service._profiling_level = ProfilingLevel.DETAILED
        service._slow_request_threshold_ms = 50.0
        service._endpoint_stats = {}
        service._slow_requests = []
        service._excluded_paths = {"/health"}

        # Normale Requests
        for i in range(10):
            service.record_request(
                endpoint="/api/users",
                method="GET",
                duration_ms=20.0 + i,
                status_code=200,
            )

        # Langsamer Request
        service.record_request(
            endpoint="/api/users",
            method="POST",
            duration_ms=100.0,
            status_code=201,
            request_id="slow-req",
        )

        # Error Request
        service.record_request(
            endpoint="/api/users",
            method="DELETE",
            duration_ms=30.0,
            status_code=500,
        )

        # Excluded Path (sollte ignoriert werden)
        service.record_request(
            endpoint="/health",
            method="GET",
            duration_ms=5.0,
            status_code=200,
        )

        # Validieren
        summary = service.get_summary()
        assert summary["total_requests"] == 12
        assert summary["total_errors"] == 1
        assert summary["total_slow_requests"] == 1

        stats = service.get_endpoint_stats()
        assert len(stats) == 3  # GET, POST, DELETE

        slow = service.get_slow_requests()
        assert len(slow) == 1
        assert slow[0]["request_id"] == "slow-req"

        hot_paths = service.get_hot_paths(limit=1)
        assert hot_paths[0]["endpoint"] == "/api/users"

        ProfilingService._instance = None
