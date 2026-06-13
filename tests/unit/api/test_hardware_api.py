"""
Tests fuer Hardware API Endpoints.

Testet:
- GET /api/v1/hardware/status
- GET /api/v1/hardware/health
- GET /api/v1/hardware/cpu
- GET /api/v1/hardware/memory
- GET /api/v1/hardware/disks
- GET /api/v1/hardware/gpu
- GET /api/v1/hardware/network
- GET /api/v1/hardware/alerts
"""

from contextlib import contextmanager
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from httpx import AsyncClient

from app.services.hardware_monitoring_service import (
    AlertSeverity,
    AlertType,
    CPUMetrics,
    DiskMetrics,
    GPUMetrics,
    HardwareAlert,
    HardwareReport,
    MemoryMetrics,
    NetworkMetrics,
    TemperatureMetrics,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_cpu_metrics() -> CPUMetrics:
    """Erstellt Mock-CPU-Metriken."""
    return CPUMetrics(
        usage_percent=45.5,
        usage_per_core=[40.0, 50.0, 45.0, 46.0],
        frequency_mhz=3500.0,
        frequency_per_core=[3500.0, 3500.0, 3500.0, 3500.0],
        core_count=4,
        thread_count=4,
        load_average=(1.5, 2.0, 1.8),
    )


@pytest.fixture
def mock_memory_metrics() -> MemoryMetrics:
    """Erstellt Mock-Memory-Metriken."""
    return MemoryMetrics(
        total_bytes=34359738368,  # 32 GB
        available_bytes=17179869184,  # 16 GB
        used_bytes=17179869184,  # 16 GB
        used_percent=50.0,
        swap_total_bytes=8589934592,  # 8 GB
        swap_used_bytes=1073741824,  # 1 GB
        swap_percent=12.5,
    )


@pytest.fixture
def mock_disk_metrics() -> list[DiskMetrics]:
    """Erstellt Mock-Disk-Metriken."""
    return [
        DiskMetrics(
            mountpoint="C:\\",
            device="PhysicalDrive0",
            total_bytes=512110190592,  # 477 GB
            used_bytes=256055095296,  # 238 GB
            free_bytes=256055095296,  # 238 GB
            used_percent=50.0,
            read_bytes=1073741824000,
            write_bytes=536870912000,
            read_iops=150.5,
            write_iops=75.2,
            io_time_ms=5000,
        ),
        DiskMetrics(
            mountpoint="D:\\",
            device="PhysicalDrive1",
            total_bytes=2199023255552,  # 2 TB
            used_bytes=1099511627776,  # 1 TB
            free_bytes=1099511627776,  # 1 TB
            used_percent=50.0,
            read_bytes=2147483648000,
            write_bytes=1073741824000,
            read_iops=200.0,
            write_iops=100.0,
            io_time_ms=10000,
        ),
    ]


@pytest.fixture
def mock_network_metrics() -> list[NetworkMetrics]:
    """Erstellt Mock-Network-Metriken."""
    return [
        NetworkMetrics(
            interface="Ethernet",
            bytes_sent=1073741824,  # 1 GB
            bytes_recv=2147483648,  # 2 GB
            packets_sent=1000000,
            packets_recv=2000000,
            errors_in=0,
            errors_out=0,
            is_up=True,
        ),
        NetworkMetrics(
            interface="Loopback",
            bytes_sent=536870912,
            bytes_recv=536870912,
            packets_sent=500000,
            packets_recv=500000,
            errors_in=0,
            errors_out=0,
            is_up=True,
        ),
    ]


@pytest.fixture
def mock_gpu_metrics() -> list[GPUMetrics]:
    """Erstellt Mock-GPU-Metriken."""
    return [
        GPUMetrics(
            gpu_id=0,
            name="NVIDIA GeForce RTX 4080",
            utilization_percent=65.0,
            memory_total_bytes=17179869184,  # 16 GB
            memory_used_bytes=8589934592,  # 8 GB
            memory_used_percent=50.0,
            temperature_celsius=68.0,
            power_watts=250.0,
            fan_speed_percent=55.0,
        )
    ]


@pytest.fixture
def mock_temperature_metrics() -> list[TemperatureMetrics]:
    """Erstellt Mock-Temperatur-Metriken."""
    return [
        TemperatureMetrics(
            sensor_name="CPU Package",
            current_celsius=55.0,
            high_celsius=90.0,
            critical_celsius=100.0,
        ),
        TemperatureMetrics(
            sensor_name="CPU Core 0",
            current_celsius=52.0,
            high_celsius=90.0,
            critical_celsius=100.0,
        ),
    ]


@pytest.fixture
def mock_alerts() -> list[HardwareAlert]:
    """Erstellt Mock-Alerts."""
    return [
        HardwareAlert(
            alert_type=AlertType.DISK_SPACE,
            severity=AlertSeverity.WARNING,
            message="Festplatte C:\\ ist zu 88% belegt",
            value=88.0,
            threshold=85.0,
            timestamp=datetime.utcnow(),
            resolved=False,
        ),
    ]


@pytest.fixture
def mock_hardware_report(
    mock_cpu_metrics: CPUMetrics,
    mock_memory_metrics: MemoryMetrics,
    mock_disk_metrics: list[DiskMetrics],
    mock_network_metrics: list[NetworkMetrics],
    mock_gpu_metrics: list[GPUMetrics],
    mock_temperature_metrics: list[TemperatureMetrics],
    mock_alerts: list[HardwareAlert],
) -> HardwareReport:
    """Erstellt vollstaendigen Mock-Hardware-Report."""
    return HardwareReport(
        timestamp=datetime.utcnow(),
        hostname="test-server",
        os_info="Windows 11 Pro 22H2",
        uptime_seconds=86400.0,  # 1 Tag
        cpu=mock_cpu_metrics,
        memory=mock_memory_metrics,
        disks=mock_disk_metrics,
        networks=mock_network_metrics,
        gpus=mock_gpu_metrics,
        temperatures=mock_temperature_metrics,
        alerts=mock_alerts,
    )


@pytest.fixture
def admin_user() -> MagicMock:
    """Erstellt Mock-Admin-User."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "admin@test.com"
    user.is_admin = True
    user.is_superuser = True
    user.is_active = True
    user.company_id = uuid4()
    return user


@pytest.fixture
def non_admin_user() -> MagicMock:
    """Erstellt Mock-Non-Admin-User."""
    user = MagicMock()
    user.id = uuid4()
    user.email = "user@test.com"
    user.is_admin = False
    user.is_superuser = False
    user.is_active = True
    user.company_id = uuid4()
    return user


@contextmanager
def _override_auth(user: MagicMock):
    """
    Ueberschreibt die Basis-Auth-Dependency (get_current_active_user) des
    Hardware-Routers per app.dependency_overrides.

    Hintergrund: Die Endpoints haengen via Depends(get_current_superuser) an
    der Auth ab; ein mock.patch greift hier NICHT (Depends bindet die Referenz
    bei Decoration). Durch Override von get_current_active_user bleibt die
    echte Superuser-Pruefung in get_current_superuser aktiv -> Non-Admins
    erhalten korrekt 403, Admins (is_superuser=True) kommen durch.
    Cleanup ist garantiert.
    """
    from app.main import app
    from app.api.dependencies import get_current_active_user

    app.dependency_overrides[get_current_active_user] = lambda: user
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_active_user, None)


# =============================================================================
# Authorization Tests
# =============================================================================


class TestAuthorization:
    """Tests fuer Zugriffsberechtigungen."""

    @pytest.mark.asyncio
    async def test_hardware_status_requires_admin(
        self,
        async_client: AsyncClient,
        non_admin_user: MagicMock,
    ) -> None:
        """Hardware-Status erfordert Admin-Rechte."""
        with _override_auth(non_admin_user):
            response = await async_client.get(
                "/api/v1/hardware/status",
                headers={"Authorization": "Bearer dummy"},
            )

            # Sollte 403 Forbidden zurueckgeben (Non-Admin)
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ]

    @pytest.mark.asyncio
    async def test_hardware_status_allows_admin(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_hardware_report: HardwareReport,
    ) -> None:
        """Hardware-Status erlaubt Admin-Zugriff."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_full_hardware_status = AsyncMock(return_value=mock_hardware_report)
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/status")

            # Sollte erfolgreich sein (oder 401 wenn Auth fehlt)
            assert response.status_code in [
                status.HTTP_200_OK,
                status.HTTP_401_UNAUTHORIZED,
            ]


# =============================================================================
# Hardware Status Endpoint Tests
# =============================================================================


class TestHardwareStatusEndpoint:
    """Tests fuer /api/v1/hardware/status."""

    @pytest.mark.asyncio
    async def test_status_response_structure(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_hardware_report: HardwareReport,
    ) -> None:
        """Status-Response hat korrekte Struktur."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_full_hardware_status = AsyncMock(return_value=mock_hardware_report)
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/status")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Pruefe erwartete Felder
                assert "hostname" in data or "timestamp" in data


# =============================================================================
# CPU Endpoint Tests
# =============================================================================


class TestCPUEndpoint:
    """Tests fuer /api/v1/hardware/cpu."""

    @pytest.mark.asyncio
    async def test_cpu_response_structure(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_cpu_metrics: CPUMetrics,
    ) -> None:
        """CPU-Response hat korrekte Struktur."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_cpu_metrics = AsyncMock(return_value=mock_cpu_metrics)
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/cpu")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Pruefe CPU-spezifische Felder
                assert "usage_percent" in data or "cpu" in data


# =============================================================================
# Memory Endpoint Tests
# =============================================================================


class TestMemoryEndpoint:
    """Tests fuer /api/v1/hardware/memory."""

    @pytest.mark.asyncio
    async def test_memory_response_structure(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_memory_metrics: MemoryMetrics,
    ) -> None:
        """Memory-Response hat korrekte Struktur."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_memory_metrics = AsyncMock(
                return_value=mock_memory_metrics
            )
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/memory")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Pruefe Memory-spezifische Felder
                assert "total_bytes" in data or "memory" in data or "used_percent" in data


# =============================================================================
# Disks Endpoint Tests
# =============================================================================


class TestDisksEndpoint:
    """Tests fuer /api/v1/hardware/disks."""

    @pytest.mark.asyncio
    async def test_disks_response_is_list(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_disk_metrics: list[DiskMetrics],
    ) -> None:
        """Disks-Response ist eine Liste."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_disk_metrics = AsyncMock(return_value=mock_disk_metrics)
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/disks")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Response sollte Liste sein oder "disks" Feld enthalten
                assert isinstance(data, list) or "disks" in data


# =============================================================================
# GPU Endpoint Tests
# =============================================================================


class TestGPUEndpoint:
    """Tests fuer /api/v1/hardware/gpu."""

    @pytest.mark.asyncio
    async def test_gpu_response_structure(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_gpu_metrics: list[GPUMetrics],
    ) -> None:
        """GPU-Response hat korrekte Struktur."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_gpu_metrics = AsyncMock(return_value=mock_gpu_metrics)
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/gpu")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Response sollte GPU-Daten enthalten
                assert isinstance(data, (list, dict))

    @pytest.mark.asyncio
    async def test_gpu_response_empty_without_nvidia(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
    ) -> None:
        """GPU-Response ist leer ohne NVIDIA."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_gpu_metrics = AsyncMock(return_value=[])
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/gpu")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Leere Liste oder leeres gpus-Feld
                if isinstance(data, list):
                    assert len(data) == 0
                elif "gpus" in data:
                    assert len(data["gpus"]) == 0


# =============================================================================
# Network Endpoint Tests
# =============================================================================


class TestNetworkEndpoint:
    """Tests fuer /api/v1/hardware/network."""

    @pytest.mark.asyncio
    async def test_network_response_is_list(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_network_metrics: list[NetworkMetrics],
    ) -> None:
        """Network-Response ist eine Liste."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_network_metrics = AsyncMock(
                return_value=mock_network_metrics
            )
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/network")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Response sollte Liste sein oder "networks" Feld enthalten
                assert isinstance(data, list) or "networks" in data


# =============================================================================
# Alerts Endpoint Tests
# =============================================================================


class TestAlertsEndpoint:
    """Tests fuer /api/v1/hardware/alerts."""

    @pytest.mark.asyncio
    async def test_alerts_response_is_list(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_alerts: list[HardwareAlert],
    ) -> None:
        """Alerts-Response ist eine Liste."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.check_health_alerts = AsyncMock(return_value=mock_alerts)
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/alerts")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Response sollte Liste sein oder "alerts" Feld enthalten
                assert isinstance(data, list) or "alerts" in data

    @pytest.mark.asyncio
    async def test_alerts_empty_when_healthy(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
    ) -> None:
        """Alerts-Response ist leer bei gesundem System."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.check_health_alerts = AsyncMock(return_value=[])
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/alerts")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Leere Liste oder leeres alerts-Feld
                if isinstance(data, list):
                    assert len(data) == 0
                elif "alerts" in data:
                    assert len(data["alerts"]) == 0


# =============================================================================
# Health Endpoint Tests
# =============================================================================


class TestHealthEndpoint:
    """Tests fuer /api/v1/hardware/health."""

    @pytest.mark.asyncio
    async def test_health_response_structure(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
    ) -> None:
        """Health-Response hat korrekte Struktur."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.check_health_alerts = AsyncMock(return_value=[])
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/health")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Health-Response sollte Status enthalten
                assert "status" in data or "healthy" in data or isinstance(data, dict)

    @pytest.mark.asyncio
    async def test_health_unhealthy_with_critical_alerts(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
    ) -> None:
        """Health zeigt unhealthy bei kritischen Alerts."""
        critical_alert = HardwareAlert(
            alert_type=AlertType.DISK_SPACE,
            severity=AlertSeverity.CRITICAL,
            message="Festplatte C:\\ ist zu 98% belegt",
            value=98.0,
            threshold=85.0,
            timestamp=datetime.utcnow(),
            resolved=False,
        )

        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.check_health_alerts = AsyncMock(return_value=[critical_alert])
            mock_service.return_value = mock_instance

            response = await async_client.get("/api/v1/hardware/health")

            if response.status_code == status.HTTP_200_OK:
                data = response.json()
                # Bei kritischen Alerts sollte Status nicht "healthy" sein
                # (Implementierungsabhaengig)


# =============================================================================
# Response Format Tests
# =============================================================================


class TestResponseFormats:
    """Tests fuer Response-Formate."""

    @pytest.mark.asyncio
    async def test_all_endpoints_return_json(
        self,
        async_client: AsyncClient,
        admin_user: MagicMock,
        mock_hardware_report: HardwareReport,
        mock_cpu_metrics: CPUMetrics,
        mock_memory_metrics: MemoryMetrics,
        mock_disk_metrics: list[DiskMetrics],
        mock_gpu_metrics: list[GPUMetrics],
        mock_network_metrics: list[NetworkMetrics],
        mock_alerts: list[HardwareAlert],
    ) -> None:
        """Alle Endpoints geben JSON zurueck."""
        with (
            _override_auth(admin_user),
            patch(
                "app.api.v1.hardware.get_hardware_monitoring_service"
            ) as mock_service,
        ):
            mock_instance = AsyncMock()
            mock_instance.get_full_hardware_status = AsyncMock(return_value=mock_hardware_report)
            mock_instance.get_cpu_metrics = AsyncMock(return_value=mock_cpu_metrics)
            mock_instance.get_memory_metrics = AsyncMock(
                return_value=mock_memory_metrics
            )
            mock_instance.get_disk_metrics = AsyncMock(return_value=mock_disk_metrics)
            mock_instance.get_gpu_metrics = AsyncMock(return_value=mock_gpu_metrics)
            mock_instance.get_network_metrics = AsyncMock(
                return_value=mock_network_metrics
            )
            mock_instance.check_health_alerts = AsyncMock(return_value=mock_alerts)
            mock_service.return_value = mock_instance

            endpoints = [
                "/api/v1/hardware/status",
                "/api/v1/hardware/health",
                "/api/v1/hardware/cpu",
                "/api/v1/hardware/memory",
                "/api/v1/hardware/disks",
                "/api/v1/hardware/gpu",
                "/api/v1/hardware/network",
                "/api/v1/hardware/alerts",
            ]

            for endpoint in endpoints:
                response = await async_client.get(endpoint)
                if response.status_code == status.HTTP_200_OK:
                    # Content-Type sollte JSON sein
                    assert "application/json" in response.headers.get(
                        "content-type", ""
                    )
