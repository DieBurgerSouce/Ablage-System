# -*- coding: utf-8 -*-
"""
Unit Tests fuer Health Check API Endpoints.

Testet alle Gesundheitspruefungen und Komponenten-Checks.
"""

import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.health import (
    BasicHealthResponse,
    DetailedHealthResponse,
    DependencyHealthResponse,
    KomponentenStatus,
    _check_database,
    _check_disk_space,
    _check_gpu,
    _check_minio,
    _check_redis,
    basic_health,
    detailed_health,
    liveness_probe,
    readiness_probe,
)


# =============================================================================
# Test Basic Health
# =============================================================================


class TestBasicHealth:
    """Tests fuer einfache Gesundheitspruefung."""

    @pytest.mark.asyncio
    async def test_basic_health_returns_healthy(self):
        """Basic health check sollte 'gesund' zurueckgeben."""
        result = await basic_health()

        assert isinstance(result, BasicHealthResponse)
        assert result.status == "gesund"
        assert result.version == "0.2.0-poc"
        assert result.zeitstempel is not None

    @pytest.mark.asyncio
    async def test_basic_health_timestamp_format(self):
        """Zeitstempel sollte ISO-Format haben."""
        result = await basic_health()

        # Sollte parsebar sein
        datetime.fromisoformat(result.zeitstempel.replace("Z", "+00:00"))


# =============================================================================
# Test Database Check
# =============================================================================


class TestDatabaseCheck:
    """Tests fuer Datenbank-Pruefung."""

    @pytest.mark.asyncio
    async def test_check_database_success(self):
        """Erfolgreiche Datenbank-Verbindung."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        result = await _check_database(mock_db)

        assert result.gesund is True
        assert "PostgreSQL erreichbar" in result.nachricht
        assert result.latenz_ms is not None
        assert result.latenz_ms > 0

    @pytest.mark.asyncio
    async def test_check_database_failure(self):
        """Fehlgeschlagene Datenbank-Verbindung."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("Connection refused")

        result = await _check_database(mock_db)

        assert result.gesund is False
        assert "nicht erreichbar" in result.nachricht


# =============================================================================
# Test Redis Check
# =============================================================================


class TestRedisCheck:
    """Tests fuer Redis-Pruefung."""

    @pytest.mark.asyncio
    async def test_check_redis_success(self):
        """Erfolgreiche Redis-Verbindung."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_from_url.return_value = mock_client
            mock_client.ping.return_value = True

            result = await _check_redis()

            assert result.gesund is True
            assert "Redis erreichbar" in result.nachricht
            mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_redis_failure(self):
        """Fehlgeschlagene Redis-Verbindung."""
        with patch("redis.asyncio.from_url") as mock_from_url:
            mock_client = AsyncMock()
            mock_from_url.return_value = mock_client
            mock_client.ping.side_effect = Exception("Connection refused")

            result = await _check_redis()

            assert result.gesund is False
            assert "nicht erreichbar" in result.nachricht


# =============================================================================
# Test GPU Check
# =============================================================================


class TestGPUCheck:
    """Tests fuer GPU-Pruefung."""

    def test_check_gpu_with_cuda(self):
        """GPU verfuegbar mit CUDA."""
        with patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.get_device_name", return_value="NVIDIA RTX 4080"), \
             patch("torch.cuda.get_device_properties") as mock_props, \
             patch("torch.cuda.memory_allocated", return_value=4 * 1024**3):

            mock_props.return_value.total_memory = 16 * 1024**3  # 16GB

            result = _check_gpu()

            assert result.gesund is True
            assert "RTX 4080" in result.nachricht
            assert result.details["speicher_prozent"] < 85

    def test_check_gpu_high_memory(self):
        """GPU mit hoher Speicherauslastung."""
        with patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.get_device_name", return_value="NVIDIA RTX 4080"), \
             patch("torch.cuda.get_device_properties") as mock_props, \
             patch("torch.cuda.memory_allocated", return_value=14 * 1024**3):

            mock_props.return_value.total_memory = 16 * 1024**3  # 16GB

            result = _check_gpu()

            assert result.gesund is False  # >85% = nicht gesund
            assert result.details["speicher_prozent"] > 85

    def test_check_gpu_no_cuda(self):
        """Keine GPU verfuegbar."""
        with patch("torch.cuda.is_available", return_value=False):
            result = _check_gpu()

            assert result.gesund is True  # CPU-Modus ist akzeptabel
            assert "CPU-Modus" in result.nachricht


# =============================================================================
# Test Disk Space Check
# =============================================================================


class TestDiskSpaceCheck:
    """Tests fuer Speicherplatz-Pruefung."""

    def test_check_disk_space_sufficient(self):
        """Genuegend Speicherplatz vorhanden."""
        with patch("shutil.disk_usage") as mock_disk:
            # 100GB total, 50GB used, 50GB free
            mock_disk.return_value = (100 * 1024**3, 50 * 1024**3, 50 * 1024**3)

            result = _check_disk_space()

            assert result.gesund is True
            assert "50.0 GB frei" in result.nachricht
            assert result.details["frei_gb"] == 50.0

    def test_check_disk_space_low(self):
        """Wenig Speicherplatz."""
        with patch("shutil.disk_usage") as mock_disk:
            # 100GB total, 95GB used, 5GB free
            mock_disk.return_value = (100 * 1024**3, 95 * 1024**3, 5 * 1024**3)

            result = _check_disk_space()

            assert result.gesund is False  # <10GB = nicht gesund
            assert "5.0 GB frei" in result.nachricht


# =============================================================================
# Test MinIO Check
# =============================================================================


class TestMinIOCheck:
    """Tests fuer MinIO-Pruefung."""

    @pytest.mark.asyncio
    async def test_check_minio_success(self):
        """Erfolgreiche MinIO-Verbindung."""
        # Mock the entire minio module
        mock_minio_module = MagicMock()
        mock_client = MagicMock()
        mock_minio_module.Minio.return_value = mock_client
        mock_client.list_buckets.return_value = [
            MagicMock(name="documents"),
            MagicMock(name="backups"),
        ]

        mock_settings = MagicMock()
        mock_settings.MINIO_HOST = "localhost"
        mock_settings.MINIO_PORT = "9000"
        mock_settings.MINIO_ACCESS_KEY = "test"
        mock_settings.MINIO_SECRET_KEY = "test"

        with patch.dict("sys.modules", {"minio": mock_minio_module}), \
             patch("app.api.v1.health.settings", mock_settings):
            result = await _check_minio()

            assert result.gesund is True
            assert "MinIO erreichbar" in result.nachricht
            assert "2 Buckets" in result.nachricht

    @pytest.mark.asyncio
    async def test_check_minio_failure(self):
        """Fehlgeschlagene MinIO-Verbindung."""
        mock_minio_module = MagicMock()
        mock_minio_module.Minio.side_effect = Exception("Connection refused")

        mock_settings = MagicMock()
        mock_settings.MINIO_HOST = "localhost"
        mock_settings.MINIO_PORT = "9000"
        mock_settings.MINIO_ACCESS_KEY = "test"
        mock_settings.MINIO_SECRET_KEY = "test"

        with patch.dict("sys.modules", {"minio": mock_minio_module}), \
             patch("app.api.v1.health.settings", mock_settings):
            result = await _check_minio()

            assert result.gesund is False
            assert "nicht erreichbar" in result.nachricht

    @pytest.mark.asyncio
    async def test_check_minio_not_installed(self):
        """MinIO-Client nicht installiert."""
        # Bei ImportError sollte es nicht gesund sein
        result = await _check_minio()

        # Da minio nicht installiert ist, sollte der Test direkt "nicht installiert" zurueckgeben
        assert result.gesund is False


# =============================================================================
# Test Detailed Health
# =============================================================================


class TestDetailedHealth:
    """Tests fuer detaillierte Gesundheitspruefung."""

    @pytest.mark.asyncio
    async def test_detailed_health_all_healthy(self):
        """Alle Komponenten gesund."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        with patch("app.api.v1.health._check_redis") as mock_redis, patch(
            "app.api.v1.health._check_gpu"
        ) as mock_gpu, patch(
            "app.api.v1.health._check_disk_space"
        ) as mock_disk:
            mock_redis.return_value = KomponentenStatus(
                gesund=True, nachricht="Redis OK"
            )
            mock_gpu.return_value = KomponentenStatus(gesund=True, nachricht="GPU OK")
            mock_disk.return_value = KomponentenStatus(
                gesund=True, nachricht="Disk OK"
            )

            result = await detailed_health(mock_db)

            assert result.status == "gesund"
            assert "ordnungsgemaess" in result.zusammenfassung

    @pytest.mark.asyncio
    async def test_detailed_health_database_critical(self):
        """Datenbank kritisch - sollte kritischen Status ergeben."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB down")

        with patch("app.api.v1.health._check_redis") as mock_redis, patch(
            "app.api.v1.health._check_gpu"
        ) as mock_gpu, patch(
            "app.api.v1.health._check_disk_space"
        ) as mock_disk:
            mock_redis.return_value = KomponentenStatus(
                gesund=True, nachricht="Redis OK"
            )
            mock_gpu.return_value = KomponentenStatus(gesund=True, nachricht="GPU OK")
            mock_disk.return_value = KomponentenStatus(
                gesund=True, nachricht="Disk OK"
            )

            result = await detailed_health(mock_db)

            assert result.status == "kritisch"
            assert "datenbank" in result.zusammenfassung.lower()

    @pytest.mark.asyncio
    async def test_detailed_health_redis_degraded(self):
        """Redis nicht verfuegbar - sollte beeintraechtigt sein."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        with patch("app.api.v1.health._check_redis") as mock_redis, patch(
            "app.api.v1.health._check_gpu"
        ) as mock_gpu, patch(
            "app.api.v1.health._check_disk_space"
        ) as mock_disk:
            mock_redis.return_value = KomponentenStatus(
                gesund=False, nachricht="Redis nicht erreichbar"
            )
            mock_gpu.return_value = KomponentenStatus(gesund=True, nachricht="GPU OK")
            mock_disk.return_value = KomponentenStatus(
                gesund=True, nachricht="Disk OK"
            )

            result = await detailed_health(mock_db)

            assert result.status == "beeintraechtigt"
            assert "cache" in result.zusammenfassung.lower()


# =============================================================================
# Test Kubernetes Probes
# =============================================================================


class TestKubernetesProbes:
    """Tests fuer Kubernetes Liveness und Readiness Probes."""

    @pytest.mark.asyncio
    async def test_liveness_probe(self):
        """Liveness Probe sollte immer alive zurueckgeben."""
        result = await liveness_probe()

        assert result["status"] == "alive"

    @pytest.mark.asyncio
    async def test_readiness_probe_ready(self):
        """Readiness Probe mit gesunder Datenbank."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        result = await readiness_probe(mock_db)

        assert result["status"] == "ready"
        assert result["datenbank"] is True

    @pytest.mark.asyncio
    async def test_readiness_probe_not_ready(self):
        """Readiness Probe mit nicht verfuegbarer Datenbank."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB down")

        with pytest.raises(HTTPException) as exc_info:
            await readiness_probe(mock_db)

        assert exc_info.value.status_code == 503
        assert "Datenbank" in exc_info.value.detail


# =============================================================================
# Test Response Models
# =============================================================================


class TestResponseModels:
    """Tests fuer Response Models."""

    def test_komponenten_status_healthy(self):
        """KomponentenStatus mit gesunder Komponente."""
        status = KomponentenStatus(
            gesund=True, nachricht="Alles OK", latenz_ms=5.2, details={"key": "value"}
        )

        assert status.gesund is True
        assert status.nachricht == "Alles OK"
        assert status.latenz_ms == 5.2
        assert status.details == {"key": "value"}

    def test_komponenten_status_unhealthy(self):
        """KomponentenStatus mit ungesunder Komponente."""
        status = KomponentenStatus(gesund=False, nachricht="Fehler aufgetreten")

        assert status.gesund is False
        assert "Fehler" in status.nachricht
        assert status.latenz_ms is None
        assert status.details is None

    def test_basic_health_response(self):
        """BasicHealthResponse Model."""
        response = BasicHealthResponse(
            status="gesund",
            zeitstempel="2025-11-29T12:00:00+00:00",
            version="0.2.0-poc",
        )

        assert response.status == "gesund"
        assert "2025-11-29" in response.zeitstempel

    def test_detailed_health_response(self):
        """DetailedHealthResponse Model."""
        response = DetailedHealthResponse(
            status="gesund",
            zeitstempel="2025-11-29T12:00:00+00:00",
            version="0.2.0-poc",
            komponenten={
                "datenbank": KomponentenStatus(gesund=True, nachricht="OK"),
                "cache": KomponentenStatus(gesund=True, nachricht="OK"),
            },
            zusammenfassung="Alles funktioniert",
        )

        assert response.status == "gesund"
        assert len(response.komponenten) == 2
        assert response.zusammenfassung == "Alles funktioniert"
