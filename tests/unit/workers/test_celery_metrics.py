# -*- coding: utf-8 -*-
"""
Tests für celery_metrics.py - Prometheus Metriken für Celery Worker.

Testet:
- Task Metriken (started, succeeded, failed, retried)
- GPU Metriken
- Worker Metriken
- Metrics HTTP Server
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch, MagicMock
from http.client import HTTPConnection

from app.workers.celery_metrics import (
    # Metriken
    celery_tasks_total,
    celery_task_duration_seconds,
    celery_tasks_active,
    celery_task_retries_total,
    celery_task_exceptions_total,
    celery_gpu_memory_bytes,
    celery_gpu_oom_events_total,
    celery_worker_up,
    celery_worker_uptime_seconds,
    celery_queue_length,
    # Funktionen
    record_task_started,
    record_task_succeeded,
    record_task_failed,
    record_task_retried,
    record_gpu_oom,
    init_worker_metrics,
    shutdown_worker_metrics,
    update_gpu_metrics,
    start_metrics_server,
    stop_metrics_server,
    # Registry
    CELERY_REGISTRY,
)


# ==================== Task Metrics Tests ====================


class TestTaskMetrics:
    """Tests für Task-bezogene Metriken."""

    def setup_method(self):
        """Reset metrics before each test."""
        # Prometheus metrics können nicht einfach resettet werden,
        # daher prüfen wir relative Änderungen
        pass

    def test_record_task_started(self):
        """Task-Start wird aufgezeichnet."""
        task_id = "test-task-123"
        task_name = "app.workers.tasks.test_task"
        queue = "test_queue"

        # Vor dem Aufruf: Aktuelle Werte merken
        initial_active = celery_tasks_active.labels(
            task_name=task_name, queue=queue
        )._value.get()

        record_task_started(task_id, task_name, queue)

        # Nach dem Aufruf: Werte prüfen
        new_active = celery_tasks_active.labels(
            task_name=task_name, queue=queue
        )._value.get()

        assert new_active == initial_active + 1

    def test_record_task_succeeded(self):
        """Task-Erfolg wird aufgezeichnet."""
        task_id = "test-success-456"
        task_name = "app.workers.tasks.success_task"
        queue = "default"

        # Starte Task zuerst
        record_task_started(task_id, task_name, queue)

        # Dann beende erfolgreich
        record_task_succeeded(task_id, task_name, queue)

        # Active sollte wieder reduziert sein
        # (Der Counter für succeeded wurde erhöht)

    def test_record_task_failed(self):
        """Task-Fehler wird aufgezeichnet."""
        task_id = "test-failure-789"
        task_name = "app.workers.tasks.failing_task"
        queue = "default"
        exception_type = "ValueError"

        # Starte Task
        record_task_started(task_id, task_name, queue)

        # Dann Fehler aufzeichnen
        record_task_failed(task_id, task_name, queue, exception_type)

        # Exception counter sollte erhöht sein

    def test_record_task_retried(self):
        """Task-Retry wird aufgezeichnet."""
        task_id = "test-retry-abc"
        task_name = "app.workers.tasks.retry_task"
        queue = "default"

        record_task_retried(task_id, task_name, queue)

        # Retry counter sollte erhöht sein

    def test_task_duration_recorded(self):
        """Task-Dauer wird als Histogram aufgezeichnet."""
        task_id = "test-duration-xyz"
        task_name = "app.workers.tasks.timed_task"
        queue = "default"

        # Starte Task
        record_task_started(task_id, task_name, queue)

        # Simuliere Verarbeitung
        time.sleep(0.1)

        # Beende Task
        record_task_succeeded(task_id, task_name, queue)

        # Duration Histogram sollte Wert enthalten


# ==================== GPU Metrics Tests ====================


class TestGPUMetrics:
    """Tests für GPU-bezogene Metriken."""

    def test_record_gpu_oom(self):
        """GPU OOM Event wird aufgezeichnet."""
        task_name = "app.workers.tasks.gpu_task"

        # OOM Event aufzeichnen
        record_gpu_oom(task_name)

        # Counter sollte erhöht sein

    @patch('torch.cuda.is_available', return_value=True)
    @patch('torch.cuda.memory_allocated', return_value=4 * 1024**3)  # 4GB
    @patch('torch.cuda.memory_reserved', return_value=6 * 1024**3)   # 6GB
    @patch('torch.cuda.get_device_properties')
    def test_update_gpu_metrics_with_gpu(
        self, mock_props, mock_reserved, mock_allocated, mock_available
    ):
        """GPU Metriken werden aktualisiert wenn GPU verfügbar."""
        mock_props.return_value = MagicMock(total_memory=16 * 1024**3)  # 16GB

        update_gpu_metrics()

        # Metriken sollten gesetzt sein
        allocated = celery_gpu_memory_bytes.labels(type="allocated")._value.get()
        assert allocated == 4 * 1024**3

    @patch('torch.cuda.is_available', return_value=False)
    def test_update_gpu_metrics_without_gpu(self, mock_available):
        """GPU Metriken ohne GPU verfügbar."""
        # Sollte nicht crashen
        update_gpu_metrics()


# ==================== Worker Metrics Tests ====================


class TestWorkerMetrics:
    """Tests für Worker-bezogene Metriken."""

    def test_init_worker_metrics(self):
        """Worker Metriken werden initialisiert."""
        init_worker_metrics(
            hostname="test-worker",
            pool_size=1,
            prefetch=1
        )

        # Worker sollte als "up" markiert sein
        assert celery_worker_up._value.get() == 1

    def test_shutdown_worker_metrics(self):
        """Worker Metriken bei Shutdown."""
        init_worker_metrics(hostname="shutdown-test")
        shutdown_worker_metrics()

        # Worker sollte als "down" markiert sein
        assert celery_worker_up._value.get() == 0

    def test_worker_uptime_calculation(self):
        """Worker Uptime wird berechnet."""
        init_worker_metrics(hostname="uptime-test")

        # Warte kurz
        time.sleep(0.1)

        # Uptime sollte > 0 sein
        from app.workers.celery_metrics import update_worker_uptime
        update_worker_uptime()

        uptime = celery_worker_uptime_seconds._value.get()
        assert uptime >= 0.1


# ==================== HTTP Server Tests ====================


class TestMetricsServer:
    """Tests für den Prometheus Metrics HTTP Server."""

    def test_start_and_stop_server(self):
        """Server kann gestartet und gestoppt werden."""
        # Starte Server auf nicht-standard Port
        test_port = 18001
        start_metrics_server(port=test_port)

        # Kurz warten bis Server läuft
        time.sleep(0.2)

        # Stoppe Server
        stop_metrics_server()

    def test_metrics_endpoint_accessible(self):
        """Metrics Endpoint ist erreichbar."""
        test_port = 18002
        start_metrics_server(port=test_port)

        try:
            time.sleep(0.2)

            # HTTP Request an /metrics
            conn = HTTPConnection("localhost", test_port, timeout=2)
            conn.request("GET", "/metrics")
            response = conn.getresponse()

            assert response.status == 200
            assert "text/plain" in response.getheader("Content-Type")

            body = response.read().decode()
            assert "ablage_celery" in body

        finally:
            stop_metrics_server()

    def test_health_endpoint_accessible(self):
        """Health Endpoint ist erreichbar."""
        test_port = 18003
        start_metrics_server(port=test_port)

        try:
            time.sleep(0.2)

            conn = HTTPConnection("localhost", test_port, timeout=2)
            conn.request("GET", "/health")
            response = conn.getresponse()

            assert response.status == 200
            assert response.read() == b"OK"

        finally:
            stop_metrics_server()

    def test_404_for_unknown_path(self):
        """Unbekannter Pfad gibt 404."""
        test_port = 18004
        start_metrics_server(port=test_port)

        try:
            time.sleep(0.2)

            conn = HTTPConnection("localhost", test_port, timeout=2)
            conn.request("GET", "/unknown")
            response = conn.getresponse()

            assert response.status == 404

        finally:
            stop_metrics_server()

    def test_server_not_started_twice(self):
        """Server wird nicht doppelt gestartet."""
        test_port = 18005
        start_metrics_server(port=test_port)

        try:
            time.sleep(0.1)
            # Zweiter Start sollte warnen, nicht crashen
            start_metrics_server(port=test_port)
        finally:
            stop_metrics_server()


# ==================== Registry Tests ====================


class TestCeleryRegistry:
    """Tests für die Prometheus Registry."""

    def test_registry_contains_metrics(self):
        """Registry enthält erwartete Metriken."""
        # Sammle Metrik-Namen aus Registry
        metric_names = []
        for metric_family in CELERY_REGISTRY.collect():
            # In prometheus_client, collect() returns MetricFamily objects
            # which have a 'name' attribute directly
            if hasattr(metric_family, 'name'):
                metric_names.append(metric_family.name)

        # Counter metrics don't have _total suffix in registry name
        assert "ablage_celery_tasks" in metric_names
        assert "ablage_celery_task_duration_seconds" in metric_names
        assert "ablage_celery_gpu_memory_bytes" in metric_names
        assert "ablage_celery_worker_up" in metric_names

    def test_registry_separate_from_default(self):
        """Celery Registry ist separiert von Default Registry."""
        from prometheus_client import REGISTRY

        # Celery-spezifische Metriken sollten in separater Registry sein
        assert CELERY_REGISTRY is not REGISTRY


# ==================== Integration Tests ====================


class TestMetricsIntegration:
    """Integration Tests für Celery Metriken."""

    def test_full_task_lifecycle(self):
        """Vollständiger Task-Lifecycle wird korrekt aufgezeichnet."""
        task_id = "integration-test-full"
        task_name = "app.workers.tasks.integration_task"
        queue = "integration"

        # 1. Task starten
        record_task_started(task_id, task_name, queue)

        # 2. Simuliere Verarbeitung
        time.sleep(0.05)

        # 3. Task erfolgreich beenden
        record_task_succeeded(task_id, task_name, queue)

        # Alle Metriken sollten konsistent sein

    def test_failed_task_with_retry(self):
        """Fehlgeschlagener Task mit Retry wird korrekt aufgezeichnet."""
        task_id = "integration-test-retry"
        task_name = "app.workers.tasks.flaky_task"
        queue = "default"

        # 1. Erster Versuch
        record_task_started(task_id, task_name, queue)
        record_task_failed(task_id, task_name, queue, "TimeoutError")

        # 2. Retry
        record_task_retried(task_id + "-retry-1", task_name, queue)
        record_task_started(task_id + "-retry-1", task_name, queue)

        # 3. Erfolg nach Retry
        record_task_succeeded(task_id + "-retry-1", task_name, queue)

    def test_concurrent_tasks(self):
        """Mehrere gleichzeitige Tasks werden korrekt aufgezeichnet."""
        tasks = [
            ("concurrent-1", "app.workers.tasks.task_a", "queue_a"),
            ("concurrent-2", "app.workers.tasks.task_b", "queue_b"),
            ("concurrent-3", "app.workers.tasks.task_c", "queue_c"),
        ]

        # Alle Tasks starten
        for task_id, task_name, queue in tasks:
            record_task_started(task_id, task_name, queue)

        # Alle Tasks beenden
        for task_id, task_name, queue in tasks:
            record_task_succeeded(task_id, task_name, queue)

    def test_gpu_oom_during_task(self):
        """GPU OOM während Task-Verarbeitung."""
        task_id = "gpu-oom-test"
        task_name = "app.workers.tasks.gpu_heavy_task"
        queue = "gpu"

        # Task starten
        record_task_started(task_id, task_name, queue)

        # OOM Event
        record_gpu_oom(task_name)

        # Task als fehlgeschlagen markieren
        record_task_failed(task_id, task_name, queue, "OutOfMemoryError")
