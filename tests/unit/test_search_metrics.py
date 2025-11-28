# -*- coding: utf-8 -*-
"""Unit-Tests fuer Such-Metriken.

Testet das SearchMetrics-Modul fuer Prometheus-Metriken.
"""

import pytest
import time
from unittest.mock import patch, MagicMock


class TestSearchMetrics:
    """Tests fuer SearchMetrics-Klasse."""

    def test_singleton_instance(self):
        """get_search_metrics sollte immer dieselbe Instanz zurueckgeben."""
        from app.services.search_metrics import get_search_metrics

        metrics1 = get_search_metrics()
        metrics2 = get_search_metrics()

        assert metrics1 is metrics2

    def test_metrics_enabled_with_prometheus(self):
        """Metriken sollten aktiviert sein wenn Prometheus verfuegbar."""
        from app.services.search_metrics import SearchMetrics, PROMETHEUS_AVAILABLE

        metrics = SearchMetrics()

        if PROMETHEUS_AVAILABLE:
            assert metrics.enabled is True
        else:
            assert metrics.enabled is False


class TestSearchMetricsRecording:
    """Tests fuer Metrik-Aufzeichnung."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_record_search_success(self, metrics):
        """Erfolgreiche Suche sollte aufgezeichnet werden."""
        # Should not raise
        metrics.record_search(
            search_type="fts",
            duration_seconds=0.5,
            results_count=10,
            cached=False,
            success=True
        )

    def test_record_search_cached(self, metrics):
        """Cache-Hit sollte aufgezeichnet werden."""
        metrics.record_search(
            search_type="semantic",
            duration_seconds=0.01,
            results_count=5,
            cached=True,
            success=True
        )

    def test_record_search_error(self, metrics):
        """Fehlerhafte Suche sollte aufgezeichnet werden."""
        metrics.record_search(
            search_type="hybrid",
            duration_seconds=1.0,
            results_count=0,
            cached=False,
            success=False
        )

    def test_record_zero_results_search(self, metrics):
        """Suche ohne Ergebnisse sollte aufgezeichnet werden."""
        metrics.record_search(
            search_type="fts",
            duration_seconds=0.2,
            results_count=0,
            cached=False,
            success=True
        )


class TestSearchMetricsCaching:
    """Tests fuer Cache-Metriken."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_record_cache_hit(self, metrics):
        """Cache-Hit sollte aufgezeichnet werden."""
        metrics.record_cache_hit()

    def test_record_cache_miss(self, metrics):
        """Cache-Miss sollte aufgezeichnet werden."""
        metrics.record_cache_miss()

    def test_record_cache_store_success(self, metrics):
        """Erfolgreiche Cache-Speicherung sollte aufgezeichnet werden."""
        metrics.record_cache_store(success=True)

    def test_record_cache_store_error(self, metrics):
        """Fehlgeschlagene Cache-Speicherung sollte aufgezeichnet werden."""
        metrics.record_cache_store(success=False)

    def test_record_cache_invalidation(self, metrics):
        """Cache-Invalidierung sollte aufgezeichnet werden."""
        metrics.record_cache_invalidation(reason="document_update", count=1)
        metrics.record_cache_invalidation(reason="document_delete", count=1)
        metrics.record_cache_invalidation(reason="batch_delete", count=5)
        metrics.record_cache_invalidation(reason="batch_tag", count=3)
        metrics.record_cache_invalidation(reason="admin", count=100)

    def test_set_cache_size(self, metrics):
        """Cache-Groesse sollte gesetzt werden koennen."""
        metrics.set_cache_size(1000)
        metrics.set_cache_size(0)


class TestSearchMetricsEmbeddings:
    """Tests fuer Embedding-Metriken."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_record_embedding_generation_query(self, metrics):
        """Query-Embedding-Generierung sollte aufgezeichnet werden."""
        metrics.record_embedding_generation(
            duration_seconds=0.1,
            source="query"
        )

    def test_record_embedding_generation_document(self, metrics):
        """Dokument-Embedding-Generierung sollte aufgezeichnet werden."""
        metrics.record_embedding_generation(
            duration_seconds=0.5,
            source="document"
        )

    def test_record_embedding_cache_hit(self, metrics):
        """Embedding-Cache-Hit sollte aufgezeichnet werden."""
        metrics.record_embedding_cache_hit()

    def test_measure_embedding_context_manager(self, metrics):
        """measure_embedding Context Manager sollte Zeit messen."""
        with metrics.measure_embedding(source="query"):
            time.sleep(0.01)  # Minimal wait


class TestSearchMetricsSimilarDocuments:
    """Tests fuer aehnliche-Dokumente-Metriken."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_record_similar_documents_success(self, metrics):
        """Erfolgreiche Aehnlichkeitssuche sollte aufgezeichnet werden."""
        metrics.record_similar_documents(
            count=5,
            duration_seconds=0.3,
            cached=False,
            success=True
        )

    def test_record_similar_documents_cached(self, metrics):
        """Gecachte Aehnlichkeitssuche sollte aufgezeichnet werden."""
        metrics.record_similar_documents(
            count=3,
            duration_seconds=0.01,
            cached=True,
            success=True
        )

    def test_record_similar_documents_error(self, metrics):
        """Fehlerhafte Aehnlichkeitssuche sollte aufgezeichnet werden."""
        metrics.record_similar_documents(
            count=0,
            duration_seconds=0.5,
            cached=False,
            success=False
        )


class TestSearchMetricsFilters:
    """Tests fuer Filter-Metriken."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_record_filter_usage(self, metrics):
        """Filter-Verwendung sollte aufgezeichnet werden."""
        metrics.record_filter_usage("document_type")
        metrics.record_filter_usage("date")
        metrics.record_filter_usage("status")
        metrics.record_filter_usage("tags")
        metrics.record_filter_usage("confidence")
        metrics.record_filter_usage("language")
        metrics.record_filter_usage("embedding")

    def test_record_filters_from_request(self, metrics):
        """Mehrere Filter sollten aus Anfrage aufgezeichnet werden."""
        metrics.record_filters_from_request(
            document_type=True,
            date=True,
            status=False,
            tags=True,
            confidence=False,
            language=True,
            embedding=False
        )

    def test_record_no_filters(self, metrics):
        """Keine Filter sollte keine Aufzeichnung verursachen."""
        metrics.record_filters_from_request(
            document_type=False,
            date=False,
            status=False,
            tags=False,
            confidence=False,
            language=False,
            embedding=False
        )


class TestSearchMetricsAnalytics:
    """Tests fuer Analytics-Metriken."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_record_analytics_logged(self, metrics):
        """Analytics-Logging sollte aufgezeichnet werden."""
        metrics.record_analytics_logged()

    def test_record_click_logged(self, metrics):
        """Klick-Logging sollte aufgezeichnet werden."""
        metrics.record_click_logged(is_download=False)
        metrics.record_click_logged(is_download=True)


class TestSearchMetricsExport:
    """Tests fuer Metrik-Export."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_get_metrics_returns_bytes(self, metrics):
        """get_metrics sollte Bytes zurueckgeben."""
        result = metrics.get_metrics()
        assert isinstance(result, bytes)

    def test_get_content_type_returns_string(self, metrics):
        """get_content_type sollte String zurueckgeben."""
        result = metrics.get_content_type()
        assert isinstance(result, str)


class TestSearchMetricsContextManagers:
    """Tests fuer Context Manager."""

    @pytest.fixture
    def metrics(self):
        """Frische SearchMetrics-Instanz."""
        from app.services.search_metrics import SearchMetrics
        return SearchMetrics()

    def test_measure_search_context_manager(self, metrics):
        """measure_search Context Manager sollte Zeit messen."""
        with metrics.measure_search(search_type="fts"):
            time.sleep(0.01)

    def test_measure_search_with_exception(self, metrics):
        """measure_search sollte auch bei Exception Zeit messen."""
        try:
            with metrics.measure_search(search_type="semantic"):
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected

    def test_measure_embedding_with_exception(self, metrics):
        """measure_embedding sollte auch bei Exception Zeit messen."""
        try:
            with metrics.measure_embedding(source="query"):
                raise RuntimeError("Test error")
        except RuntimeError:
            pass  # Expected


class TestTrackSearchDecorator:
    """Tests fuer @track_search Decorator."""

    @pytest.mark.asyncio
    async def test_track_search_decorator_success(self):
        """Decorator sollte erfolgreiche async Funktionen tracken."""
        from app.services.search_metrics import track_search

        @track_search(search_type="fts")
        async def sample_search():
            return [{"id": 1}, {"id": 2}]

        result = await sample_search()
        assert result == [{"id": 1}, {"id": 2}]

    @pytest.mark.asyncio
    async def test_track_search_decorator_with_total_attribute(self):
        """Decorator sollte total-Attribut aus Ergebnis extrahieren."""
        from app.services.search_metrics import track_search

        class MockResult:
            total = 42

        @track_search(search_type="semantic")
        async def sample_search():
            return MockResult()

        result = await sample_search()
        assert result.total == 42

    @pytest.mark.asyncio
    async def test_track_search_decorator_error(self):
        """Decorator sollte Fehler weitergeben und trotzdem tracken."""
        from app.services.search_metrics import track_search

        @track_search(search_type="hybrid")
        async def failing_search():
            raise ValueError("Search failed")

        with pytest.raises(ValueError, match="Search failed"):
            await failing_search()


class TestSearchMetricsPrometheusIntegration:
    """Tests fuer Prometheus-Integration."""

    def test_prometheus_available_check(self):
        """PROMETHEUS_AVAILABLE sollte korrekt gesetzt sein."""
        from app.services.search_metrics import PROMETHEUS_AVAILABLE
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_metrics_with_prometheus_disabled(self):
        """Metriken sollten ohne Fehler funktionieren wenn Prometheus deaktiviert."""
        from app.services.search_metrics import SearchMetrics

        metrics = SearchMetrics()
        # Override enabled to test fallback path
        original_enabled = metrics.enabled
        metrics.enabled = False

        # All methods should work without error
        metrics.record_search("fts", 0.1, 10, False, True)
        metrics.record_cache_hit()
        metrics.record_cache_miss()
        metrics.record_cache_store(True)
        metrics.record_cache_invalidation("test", 1)
        metrics.set_cache_size(100)
        metrics.record_embedding_generation(0.1, "query")
        metrics.record_embedding_cache_hit()
        metrics.record_similar_documents(5, 0.1, False, True)
        metrics.record_filter_usage("tags")
        metrics.record_analytics_logged()
        metrics.record_click_logged(False)

        result = metrics.get_metrics()
        assert b"Prometheus not available" in result

        # Restore
        metrics.enabled = original_enabled


class TestSearchMetricsThreadSafety:
    """Tests fuer Thread-Sicherheit."""

    def test_singleton_thread_safe(self):
        """Singleton sollte thread-safe sein."""
        import threading
        from app.services.search_metrics import get_search_metrics

        instances = []

        def get_instance():
            instances.append(get_search_metrics())

        threads = [threading.Thread(target=get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All instances should be the same
        assert all(inst is instances[0] for inst in instances)

    def test_record_operations_thread_safe(self):
        """Metrik-Operationen sollten thread-safe sein."""
        import threading
        from app.services.search_metrics import get_search_metrics

        metrics = get_search_metrics()
        errors = []

        def record_metrics():
            try:
                for _ in range(100):
                    metrics.record_cache_hit()
                    metrics.record_cache_miss()
                    metrics.record_search("fts", 0.1, 10, False, True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=record_metrics) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
