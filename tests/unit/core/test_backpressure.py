# -*- coding: utf-8 -*-
"""
Unit Tests fuer Backpressure Handling Module.

Testet:
- Queue-Status-Ermittlung
- Backpressure-Schwellenwerte
- Anfrage-Akzeptanz/Ablehnung
- Graceful Degradation
- FastAPI Dependency
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

from app.core.backpressure import (
    BackpressureConfig,
    BackpressureStatus,
    get_queue_lengths,
    get_backpressure_status,
    check_backpressure,
    backpressure_dependency,
    add_backpressure_headers,
    get_backpressure_info,
    _get_recommendation,
)


class TestBackpressureConfig:
    """Tests fuer BackpressureConfig."""

    def test_default_thresholds(self):
        """Standard-Schwellenwerte sind konfiguriert."""
        assert BackpressureConfig.QUEUE_THRESHOLD_WARNING > 0
        assert BackpressureConfig.QUEUE_THRESHOLD_CRITICAL > BackpressureConfig.QUEUE_THRESHOLD_WARNING
        assert BackpressureConfig.QUEUE_THRESHOLD_REJECT > BackpressureConfig.QUEUE_THRESHOLD_CRITICAL

    def test_monitored_queues_defined(self):
        """Ueberwachte Queues sind definiert."""
        assert len(BackpressureConfig.MONITORED_QUEUES) > 0
        assert "ocr_high" in BackpressureConfig.MONITORED_QUEUES
        assert "ocr_normal" in BackpressureConfig.MONITORED_QUEUES

    def test_cache_ttl_positive(self):
        """Cache-TTL ist positiv."""
        assert BackpressureConfig.STATUS_CACHE_TTL_SECONDS > 0

    def test_retry_after_positive(self):
        """Retry-After-Wert ist positiv."""
        assert BackpressureConfig.RETRY_AFTER_SECONDS > 0


class TestBackpressureStatus:
    """Tests fuer BackpressureStatus Enum."""

    def test_status_values(self):
        """Alle Status-Werte sind definiert."""
        assert BackpressureStatus.NORMAL == "normal"
        assert BackpressureStatus.WARNING == "warning"
        assert BackpressureStatus.CRITICAL == "critical"
        assert BackpressureStatus.OVERLOADED == "overloaded"


class TestGetQueueLengths:
    """Tests fuer get_queue_lengths()."""

    @patch('celery.current_app')
    @patch('redis.Redis')
    def test_returns_queue_lengths(self, mock_redis_class, mock_celery):
        """Gibt Queue-Laengen zurueck."""
        mock_redis = MagicMock()
        mock_redis.llen.return_value = 10
        mock_redis_class.from_url.return_value = mock_redis
        mock_celery.conf.broker_url = "redis://localhost:6379"

        result = get_queue_lengths()

        assert isinstance(result, dict)
        # Sollte fuer jede Queue einen Wert haben
        for queue in BackpressureConfig.MONITORED_QUEUES:
            assert queue in result

    def test_handles_import_error(self):
        """Behandelt Import-Fehler graceful."""
        # Wenn Redis nicht verfuegbar, gibt leeres Dict zurueck
        result = get_queue_lengths()
        # Gibt entweder leeres Dict oder Dict mit 0-Werten zurueck
        assert isinstance(result, dict)


class TestGetBackpressureStatus:
    """Tests fuer get_backpressure_status()."""

    @patch('app.core.backpressure.get_queue_lengths')
    def test_normal_status(self, mock_get_lengths):
        """Normaler Status bei niedriger Queue-Laenge."""
        mock_get_lengths.return_value = {"ocr_high": 5, "ocr_normal": 10}

        result = get_backpressure_status(force_refresh=True)

        assert result["status"] == BackpressureStatus.NORMAL
        assert result["total_queue_length"] == 15

    @patch('app.core.backpressure.get_queue_lengths')
    def test_warning_status(self, mock_get_lengths):
        """Warning-Status bei erhoehter Queue-Laenge."""
        mock_get_lengths.return_value = {
            "ocr_high": 30,
            "ocr_normal": 30
        }  # 60 > 50 (WARNING)

        result = get_backpressure_status(force_refresh=True)

        assert result["status"] == BackpressureStatus.WARNING

    @patch('app.core.backpressure.get_queue_lengths')
    def test_critical_status(self, mock_get_lengths):
        """Critical-Status bei hoher Queue-Laenge."""
        mock_get_lengths.return_value = {
            "ocr_high": 60,
            "ocr_normal": 60
        }  # 120 > 100 (CRITICAL)

        result = get_backpressure_status(force_refresh=True)

        assert result["status"] == BackpressureStatus.CRITICAL

    @patch('app.core.backpressure.get_queue_lengths')
    def test_overloaded_status(self, mock_get_lengths):
        """Overloaded-Status bei sehr hoher Queue-Laenge."""
        mock_get_lengths.return_value = {
            "ocr_high": 120,
            "ocr_normal": 100
        }  # 220 > 200 (REJECT)

        result = get_backpressure_status(force_refresh=True)

        assert result["status"] == BackpressureStatus.OVERLOADED

    @patch('app.core.backpressure.get_queue_lengths')
    def test_includes_thresholds(self, mock_get_lengths):
        """Status enthaelt Schwellenwerte."""
        mock_get_lengths.return_value = {"ocr_high": 5, "ocr_normal": 5}

        result = get_backpressure_status(force_refresh=True)

        assert "thresholds" in result
        assert "warning" in result["thresholds"]
        assert "critical" in result["thresholds"]
        assert "reject" in result["thresholds"]

    @patch('app.core.backpressure.get_queue_lengths')
    def test_includes_timestamp(self, mock_get_lengths):
        """Status enthaelt Timestamp."""
        mock_get_lengths.return_value = {"ocr_high": 5, "ocr_normal": 5}

        result = get_backpressure_status(force_refresh=True)

        assert "timestamp" in result


class TestCheckBackpressure:
    """Tests fuer check_backpressure()."""

    @patch('app.core.backpressure.get_backpressure_status')
    def test_accepts_on_normal(self, mock_status):
        """Akzeptiert Anfragen bei normalem Status."""
        mock_status.return_value = {
            "status": BackpressureStatus.NORMAL,
            "total_queue_length": 10
        }

        accepted, backend, status = check_backpressure()

        assert accepted is True
        assert backend is None

    @patch('app.core.backpressure.get_backpressure_status')
    def test_accepts_on_warning(self, mock_status):
        """Akzeptiert Anfragen bei Warning-Status."""
        mock_status.return_value = {
            "status": BackpressureStatus.WARNING,
            "total_queue_length": 60
        }

        accepted, backend, status = check_backpressure()

        assert accepted is True

    @patch('app.core.backpressure.get_backpressure_status')
    def test_high_priority_accepted_on_critical(self, mock_status):
        """High-Priority Anfragen werden bei Critical akzeptiert."""
        mock_status.return_value = {
            "status": BackpressureStatus.CRITICAL,
            "total_queue_length": 120
        }

        accepted, backend, status = check_backpressure(priority="high")

        assert accepted is True

    @patch('app.core.backpressure.get_backpressure_status')
    def test_suggests_cpu_backend_on_critical(self, mock_status):
        """Empfiehlt CPU-Backend bei Critical-Status."""
        mock_status.return_value = {
            "status": BackpressureStatus.CRITICAL,
            "total_queue_length": 120
        }

        accepted, backend, status = check_backpressure(
            priority="normal",
            allow_degraded=True
        )

        assert accepted is True
        assert backend == "surya"  # CPU-Backend

    @patch('app.core.backpressure.get_backpressure_status')
    def test_rejects_on_critical_without_degradation(self, mock_status):
        """Lehnt ab bei Critical ohne Degradation-Option."""
        mock_status.return_value = {
            "status": BackpressureStatus.CRITICAL,
            "total_queue_length": 120
        }

        accepted, backend, status = check_backpressure(
            priority="normal",
            allow_degraded=False
        )

        assert accepted is False

    @patch('app.core.backpressure.get_backpressure_status')
    def test_rejects_on_overloaded(self, mock_status):
        """Lehnt normale Anfragen bei Overloaded ab."""
        mock_status.return_value = {
            "status": BackpressureStatus.OVERLOADED,
            "total_queue_length": 250
        }

        accepted, backend, status = check_backpressure(priority="normal")

        assert accepted is False

    @patch('app.core.backpressure.get_backpressure_status')
    def test_high_priority_degraded_on_overloaded(self, mock_status):
        """High-Priority wird auf CPU degradiert bei Overloaded."""
        mock_status.return_value = {
            "status": BackpressureStatus.OVERLOADED,
            "total_queue_length": 250
        }

        accepted, backend, status = check_backpressure(priority="high")

        assert accepted is True
        assert backend == "surya"

    def test_disabled_backpressure_accepts_all(self):
        """Deaktiviertes Backpressure akzeptiert alle Anfragen."""
        with patch.object(BackpressureConfig, 'ENABLED', False):
            accepted, backend, status = check_backpressure()

            assert accepted is True
            assert status["status"] == BackpressureStatus.NORMAL


class TestBackpressureDependency:
    """Tests fuer backpressure_dependency()."""

    @pytest.mark.asyncio
    @patch('app.core.backpressure.check_backpressure')
    async def test_returns_status_on_accept(self, mock_check):
        """Gibt Status zurueck wenn akzeptiert."""
        mock_check.return_value = (
            True,
            None,
            {"status": BackpressureStatus.NORMAL, "total_queue_length": 10}
        )
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "normal"

        result = await backpressure_dependency(mock_request)

        assert result["accepted"] is True
        assert result["status"] == BackpressureStatus.NORMAL

    @pytest.mark.asyncio
    @patch('app.core.backpressure.check_backpressure')
    async def test_raises_503_on_reject(self, mock_check):
        """Wirft HTTPException 503 wenn abgelehnt."""
        from fastapi import HTTPException

        mock_check.return_value = (
            False,
            None,
            {"status": BackpressureStatus.OVERLOADED, "total_queue_length": 250}
        )
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "normal"

        with pytest.raises(HTTPException) as exc_info:
            await backpressure_dependency(mock_request)

        assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    @patch('app.core.backpressure.check_backpressure')
    async def test_includes_suggested_backend(self, mock_check):
        """Inkludiert vorgeschlagenes Backend."""
        mock_check.return_value = (
            True,
            "surya",
            {"status": BackpressureStatus.CRITICAL, "total_queue_length": 120}
        )
        mock_request = MagicMock()
        mock_request.headers.get.return_value = "normal"

        result = await backpressure_dependency(mock_request)

        assert result["suggested_backend"] == "surya"

    @pytest.mark.asyncio
    async def test_disabled_returns_normal(self):
        """Deaktiviertes Backpressure gibt Normal-Status."""
        with patch.object(BackpressureConfig, 'ENABLED', False):
            mock_request = MagicMock()

            result = await backpressure_dependency(mock_request)

            assert result["status"] == BackpressureStatus.NORMAL
            assert result["accepted"] is True


class TestAddBackpressureHeaders:
    """Tests fuer add_backpressure_headers()."""

    def test_adds_queue_length_header(self):
        """Fuegt X-Queue-Length Header hinzu."""
        from starlette.responses import JSONResponse

        response = JSONResponse(content={})
        status = {"total_queue_length": 50, "status": BackpressureStatus.WARNING}

        add_backpressure_headers(response, status)

        assert response.headers["X-Queue-Length"] == "50"

    def test_adds_status_header(self):
        """Fuegt X-Backpressure-Status Header hinzu."""
        from starlette.responses import JSONResponse

        response = JSONResponse(content={})
        status = {"total_queue_length": 50, "status": BackpressureStatus.WARNING}

        add_backpressure_headers(response, status)

        assert response.headers["X-Backpressure-Status"] == BackpressureStatus.WARNING

    def test_adds_warning_header_on_warning(self):
        """Fuegt Warning-Header bei Warning-Status hinzu."""
        from starlette.responses import JSONResponse

        response = JSONResponse(content={})
        status = {"total_queue_length": 60, "status": BackpressureStatus.WARNING}

        add_backpressure_headers(response, status)

        assert response.headers.get("X-Backpressure-Warning") == "true"


class TestGetBackpressureInfo:
    """Tests fuer get_backpressure_info()."""

    @patch('app.core.backpressure.get_backpressure_status')
    def test_returns_complete_info(self, mock_status):
        """Gibt vollstaendige Info zurueck."""
        mock_status.return_value = {
            "status": BackpressureStatus.NORMAL,
            "total_queue_length": 10,
            "queues": {"ocr_high": 5, "ocr_normal": 5},
            "thresholds": {"warning": 50, "critical": 100, "reject": 200},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        result = get_backpressure_info()

        assert "enabled" in result
        assert "current_status" in result
        assert "queue_lengths" in result
        assert "total_queue_length" in result
        assert "thresholds" in result
        assert "config" in result
        assert "recommendation" in result
        assert "timestamp" in result


class TestGetRecommendation:
    """Tests fuer _get_recommendation()."""

    def test_normal_recommendation(self):
        """Empfehlung fuer normalen Status."""
        result = _get_recommendation(BackpressureStatus.NORMAL)
        assert "normal" in result.lower() or "keine" in result.lower()

    def test_warning_recommendation(self):
        """Empfehlung fuer Warning-Status."""
        result = _get_recommendation(BackpressureStatus.WARNING)
        assert "worker" in result.lower() or "erhoeh" in result.lower()

    def test_critical_recommendation(self):
        """Empfehlung fuer Critical-Status."""
        result = _get_recommendation(BackpressureStatus.CRITICAL)
        assert "kritisch" in result.lower() or "cpu" in result.lower()

    def test_overloaded_recommendation(self):
        """Empfehlung fuer Overloaded-Status."""
        result = _get_recommendation(BackpressureStatus.OVERLOADED)
        assert "ueberlast" in result.lower() or "sofort" in result.lower()
