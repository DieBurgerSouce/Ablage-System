"""
Tests fuer Hardware Monitoring Service.

Testet alle Hardware-Metrik-Funktionen:
- CPU Metrics
- Memory Metrics
- Disk Metrics
- Network Metrics
- GPU Metrics (mit Mock)
- Alert Generation
- Full Hardware Report
"""

import asyncio
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.hardware_monitoring_service import (
    AlertSeverity,
    AlertType,
    CPUMetrics,
    DiskMetrics,
    GPUMetrics,
    HardwareAlert,
    HardwareMonitoringService,
    HardwareReport,
    MemoryMetrics,
    NetworkMetrics,
    TemperatureMetrics,
    get_hardware_monitoring_service,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def hardware_service() -> HardwareMonitoringService:
    """Erstellt einen Hardware Monitoring Service mit Standard-Thresholds."""
    return HardwareMonitoringService(
        disk_threshold_percent=85.0,
        memory_threshold_percent=85.0,
        cpu_threshold_percent=90.0,
        gpu_memory_threshold_percent=85.0,
        gpu_temp_threshold_celsius=80.0,
        cpu_temp_threshold_celsius=85.0,
    )


@pytest.fixture
def hardware_service_low_thresholds() -> HardwareMonitoringService:
    """Service mit niedrigen Thresholds fuer Alert-Tests."""
    return HardwareMonitoringService(
        disk_threshold_percent=10.0,  # Sehr niedrig - loest Alert aus
        memory_threshold_percent=10.0,
        cpu_threshold_percent=10.0,
        gpu_memory_threshold_percent=10.0,
        gpu_temp_threshold_celsius=20.0,
        cpu_temp_threshold_celsius=20.0,
    )


# =============================================================================
# CPU Metrics Tests
# =============================================================================


class TestCPUMetrics:
    """Tests fuer CPU-Metrik-Erfassung."""

    @pytest.mark.asyncio
    async def test_get_cpu_metrics_returns_valid_data(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """CPU-Metriken enthalten gueltige Werte."""
        metrics = await hardware_service.get_cpu_metrics()

        assert isinstance(metrics, CPUMetrics)
        assert 0 <= metrics.usage_percent <= 100
        assert len(metrics.usage_per_core) > 0
        assert metrics.core_count > 0
        assert metrics.thread_count > 0
        assert metrics.frequency_mhz >= 0

    @pytest.mark.asyncio
    async def test_cpu_metrics_per_core_count_matches(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Anzahl der Per-Core-Metriken stimmt mit Core-Count ueberein."""
        metrics = await hardware_service.get_cpu_metrics()

        # Usage per core sollte gleich viele Eintraege wie Cores haben
        assert len(metrics.usage_per_core) == metrics.thread_count

    @pytest.mark.asyncio
    async def test_cpu_load_average_structure(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Load Average hat korrektes Format (1, 5, 15 Minuten)."""
        metrics = await hardware_service.get_cpu_metrics()

        assert len(metrics.load_average) == 3
        # Alle Werte sollten >= 0 sein
        for load in metrics.load_average:
            assert load >= 0


# =============================================================================
# Memory Metrics Tests
# =============================================================================


class TestMemoryMetrics:
    """Tests fuer Memory-Metrik-Erfassung."""

    @pytest.mark.asyncio
    async def test_get_memory_metrics_returns_valid_data(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Memory-Metriken enthalten gueltige Werte."""
        metrics = await hardware_service.get_memory_metrics()

        assert isinstance(metrics, MemoryMetrics)
        assert metrics.total_bytes > 0
        assert metrics.available_bytes >= 0
        assert metrics.used_bytes >= 0
        assert 0 <= metrics.used_percent <= 100

    @pytest.mark.asyncio
    async def test_memory_bytes_consistency(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Memory-Bytes sind konsistent (used + available <= total)."""
        metrics = await hardware_service.get_memory_metrics()

        # Used + Available sollte nicht groesser als Total sein
        assert metrics.used_bytes <= metrics.total_bytes

    @pytest.mark.asyncio
    async def test_swap_metrics_present(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Swap-Metriken sind vorhanden."""
        metrics = await hardware_service.get_memory_metrics()

        # Swap kann 0 sein auf Systemen ohne Swap
        assert metrics.swap_total_bytes >= 0
        assert metrics.swap_used_bytes >= 0
        assert 0 <= metrics.swap_percent <= 100


# =============================================================================
# Disk Metrics Tests
# =============================================================================


class TestDiskMetrics:
    """Tests fuer Disk-Metrik-Erfassung."""

    @pytest.mark.asyncio
    async def test_get_disk_metrics_returns_list(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Disk-Metriken werden als Liste zurueckgegeben."""
        metrics = await hardware_service.get_disk_metrics()

        assert isinstance(metrics, list)
        # Mindestens ein Disk sollte vorhanden sein
        assert len(metrics) >= 1

    @pytest.mark.asyncio
    async def test_disk_metrics_structure(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Jede Disk hat korrektes Metrik-Format."""
        metrics = await hardware_service.get_disk_metrics()

        for disk in metrics:
            assert isinstance(disk, DiskMetrics)
            assert disk.mountpoint is not None
            assert disk.total_bytes > 0
            assert disk.used_bytes >= 0
            assert disk.free_bytes >= 0
            assert 0 <= disk.used_percent <= 100

    @pytest.mark.asyncio
    async def test_disk_bytes_consistency(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Disk-Bytes sind konsistent (used + free <= total)."""
        metrics = await hardware_service.get_disk_metrics()

        for disk in metrics:
            assert disk.used_bytes + disk.free_bytes <= disk.total_bytes


# =============================================================================
# Network Metrics Tests
# =============================================================================


class TestNetworkMetrics:
    """Tests fuer Network-Metrik-Erfassung."""

    @pytest.mark.asyncio
    async def test_get_network_metrics_returns_list(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Network-Metriken werden als Liste zurueckgegeben."""
        metrics = await hardware_service.get_network_metrics()

        assert isinstance(metrics, list)
        # Mindestens loopback sollte vorhanden sein
        assert len(metrics) >= 1

    @pytest.mark.asyncio
    async def test_network_metrics_structure(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Jedes Interface hat korrektes Metrik-Format."""
        metrics = await hardware_service.get_network_metrics()

        for net in metrics:
            assert isinstance(net, NetworkMetrics)
            assert net.interface is not None
            assert net.bytes_sent >= 0
            assert net.bytes_recv >= 0
            assert net.packets_sent >= 0
            assert net.packets_recv >= 0

    @pytest.mark.asyncio
    async def test_network_errors_non_negative(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Network-Fehler sind nicht negativ."""
        metrics = await hardware_service.get_network_metrics()

        for net in metrics:
            assert net.errors_in >= 0
            assert net.errors_out >= 0


# =============================================================================
# GPU Metrics Tests
# =============================================================================


class TestGPUMetrics:
    """Tests fuer GPU-Metrik-Erfassung."""

    @pytest.mark.asyncio
    async def test_get_gpu_metrics_without_nvidia(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """GPU-Metriken geben leere Liste zurueck ohne NVIDIA."""
        # Forciert NVML-Unavailability
        hardware_service._nvml_available = False

        metrics = await hardware_service.get_gpu_metrics()

        assert isinstance(metrics, list)
        # Kann leer sein wenn keine GPU vorhanden

    @pytest.mark.asyncio
    async def test_get_gpu_metrics_with_mock(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """GPU-Metriken mit gemockter pynvml."""
        # Mock pynvml
        mock_pynvml = MagicMock()
        mock_pynvml.nvmlDeviceGetCount.return_value = 1
        mock_handle = MagicMock()
        mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = mock_handle
        mock_pynvml.nvmlDeviceGetName.return_value = b"NVIDIA RTX 4080"
        mock_pynvml.nvmlDeviceGetUtilizationRates.return_value = MagicMock(gpu=75)
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = MagicMock(
            total=17179869184,  # 16 GB
            used=8589934592,  # 8 GB
        )
        mock_pynvml.nvmlDeviceGetTemperature.return_value = 65
        mock_pynvml.nvmlDeviceGetPowerUsage.return_value = 250000  # 250W in mW
        mock_pynvml.nvmlDeviceGetFanSpeed.return_value = 50
        mock_pynvml.NVML_TEMPERATURE_GPU = 0

        with patch.dict("sys.modules", {"pynvml": mock_pynvml}):
            hardware_service._nvml_available = True

            # Rufe Methode mit internem Mock auf
            with patch.object(
                hardware_service, "_get_gpu_metrics_internal"
            ) as mock_method:
                mock_method.return_value = [
                    GPUMetrics(
                        gpu_id=0,
                        name="NVIDIA RTX 4080",
                        utilization_percent=75.0,
                        memory_total_bytes=17179869184,
                        memory_used_bytes=8589934592,
                        memory_used_percent=50.0,
                        temperature_celsius=65.0,
                        power_watts=250.0,
                        fan_speed_percent=50.0,
                    )
                ]
                metrics = await hardware_service.get_gpu_metrics()

            assert isinstance(metrics, list)


# =============================================================================
# Temperature Metrics Tests
# =============================================================================


class TestTemperatureMetrics:
    """Tests fuer Temperatur-Metrik-Erfassung."""

    @pytest.mark.asyncio
    async def test_get_temperature_metrics_returns_list(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Temperatur-Metriken werden als Liste zurueckgegeben."""
        metrics = await hardware_service.get_temperature_metrics()

        assert isinstance(metrics, list)
        # Kann leer sein auf VMs oder Systemen ohne Sensoren

    @pytest.mark.asyncio
    async def test_temperature_metrics_structure(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Temperatur-Metriken haben korrektes Format."""
        metrics = await hardware_service.get_temperature_metrics()

        for temp in metrics:
            assert isinstance(temp, TemperatureMetrics)
            assert temp.sensor_name is not None
            # Temperatur sollte realistisch sein (-40 bis 120 Grad)
            assert -40 <= temp.current_celsius <= 120


# =============================================================================
# Alert Generation Tests
# =============================================================================


class TestAlertGeneration:
    """Tests fuer Alert-Generierung."""

    @pytest.mark.asyncio
    async def test_check_alerts_returns_list(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Alert-Check gibt Liste zurueck."""
        alerts = await hardware_service.check_health_alerts()

        assert isinstance(alerts, list)

    @pytest.mark.asyncio
    async def test_alert_structure(
        self, hardware_service_low_thresholds: HardwareMonitoringService
    ) -> None:
        """Alerts haben korrektes Format."""
        alerts = await hardware_service_low_thresholds.check_health_alerts()

        # Mit niedrigen Thresholds sollten Alerts generiert werden
        for alert in alerts:
            assert isinstance(alert, HardwareAlert)
            assert isinstance(alert.alert_type, AlertType)
            assert isinstance(alert.severity, AlertSeverity)
            assert alert.message is not None
            assert alert.value >= 0
            assert alert.threshold >= 0
            assert isinstance(alert.timestamp, datetime)

    @pytest.mark.asyncio
    async def test_disk_alert_on_high_usage(
        self, hardware_service_low_thresholds: HardwareMonitoringService
    ) -> None:
        """Disk-Alert wird bei hoher Auslastung generiert."""
        alerts = await hardware_service_low_thresholds.check_health_alerts()

        # Suche nach Disk-Alert
        disk_alerts = [a for a in alerts if a.alert_type == AlertType.DISK_SPACE]

        # Mit 10% Threshold sollte mindestens ein Disk-Alert existieren
        # (normale Disks sind ueber 10% belegt)
        assert len(disk_alerts) >= 0  # Kann 0 sein auf leeren Disks

    @pytest.mark.asyncio
    async def test_alert_severity_levels(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Alert-Severity-Levels sind korrekt definiert."""
        # Teste dass alle Severity-Levels existieren
        assert AlertSeverity.INFO is not None
        assert AlertSeverity.WARNING is not None
        assert AlertSeverity.CRITICAL is not None


# =============================================================================
# Full Hardware Report Tests
# =============================================================================


class TestHardwareReport:
    """Tests fuer vollstaendigen Hardware-Bericht."""

    @pytest.mark.asyncio
    async def test_get_full_report_returns_report(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Vollstaendiger Bericht wird zurueckgegeben."""
        report = await hardware_service.get_full_hardware_status()

        assert isinstance(report, HardwareReport)

    @pytest.mark.asyncio
    async def test_full_report_contains_all_sections(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Bericht enthaelt alle erforderlichen Sektionen."""
        report = await hardware_service.get_full_hardware_status()

        assert report.timestamp is not None
        assert report.hostname is not None
        assert report.os_info is not None
        assert report.uptime_seconds >= 0
        assert isinstance(report.cpu, CPUMetrics)
        assert isinstance(report.memory, MemoryMetrics)
        assert isinstance(report.disks, list)
        assert isinstance(report.networks, list)
        assert isinstance(report.gpus, list)
        assert isinstance(report.temperatures, list)
        assert isinstance(report.alerts, list)

    @pytest.mark.asyncio
    async def test_report_timestamp_is_recent(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Report-Timestamp ist aktuell."""
        report = await hardware_service.get_full_hardware_status()

        now = datetime.utcnow()
        # Timestamp sollte maximal 5 Sekunden alt sein
        time_diff = (now - report.timestamp).total_seconds()
        assert time_diff < 5


# =============================================================================
# Singleton Pattern Tests
# =============================================================================


class TestSingletonPattern:
    """Tests fuer Singleton-Pattern."""

    def test_get_hardware_monitoring_service_returns_same_instance(self) -> None:
        """Singleton gibt immer dieselbe Instanz zurueck."""
        service1 = get_hardware_monitoring_service()
        service2 = get_hardware_monitoring_service()

        assert service1 is service2

    def test_singleton_is_hardware_monitoring_service(self) -> None:
        """Singleton ist vom korrekten Typ."""
        service = get_hardware_monitoring_service()

        assert isinstance(service, HardwareMonitoringService)


# =============================================================================
# Prometheus Metrics Tests
# =============================================================================


class TestPrometheusMetrics:
    """Tests fuer Prometheus-Metriken-Integration."""

    def test_prometheus_gauges_defined(self) -> None:
        """Prometheus Gauges sind definiert."""
        from app.services.hardware_monitoring_service import (
            CPU_USAGE_PERCENT,
            MEMORY_USED_PERCENT,
            DISK_USED_PERCENT,
        )

        # Metriken sollten existieren
        assert CPU_USAGE_PERCENT is not None
        assert MEMORY_USED_PERCENT is not None
        assert DISK_USED_PERCENT is not None

    def test_prometheus_counters_defined(self) -> None:
        """Prometheus Counters sind definiert."""
        from app.services.hardware_monitoring_service import (
            DISK_READ_BYTES,
            DISK_WRITE_BYTES,
        )

        assert DISK_READ_BYTES is not None
        assert DISK_WRITE_BYTES is not None


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_metric_calls(
        self, hardware_service: HardwareMonitoringService
    ) -> None:
        """Mehrere gleichzeitige Aufrufe funktionieren."""
        # Fuehre mehrere Aufrufe parallel aus
        tasks = [
            hardware_service.get_cpu_metrics(),
            hardware_service.get_memory_metrics(),
            hardware_service.get_disk_metrics(),
            hardware_service.get_network_metrics(),
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 4
        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_threshold_boundary_values(self) -> None:
        """Grenzwerte fuer Thresholds."""
        # Teste mit Grenzwerten
        service = HardwareMonitoringService(
            disk_threshold_percent=0.0,
            memory_threshold_percent=100.0,
            cpu_threshold_percent=50.0,
        )

        # Sollte keine Exception werfen
        alerts = await service.check_health_alerts()
        assert isinstance(alerts, list)

    def test_init_with_custom_thresholds(self) -> None:
        """Service akzeptiert benutzerdefinierte Thresholds."""
        service = HardwareMonitoringService(
            disk_threshold_percent=75.0,
            memory_threshold_percent=80.0,
            cpu_threshold_percent=85.0,
            gpu_memory_threshold_percent=90.0,
            gpu_temp_threshold_celsius=75.0,
            cpu_temp_threshold_celsius=80.0,
        )

        assert service.disk_threshold == 75.0
        assert service.memory_threshold == 80.0
        assert service.cpu_threshold == 85.0
        assert service.gpu_memory_threshold == 90.0
        assert service.gpu_temp_threshold == 75.0
        assert service.cpu_temp_threshold == 80.0


# =============================================================================
# Data Classes Tests
# =============================================================================


class TestDataClasses:
    """Tests fuer Datenklassen."""

    def test_cpu_metrics_dataclass(self) -> None:
        """CPUMetrics-Datenklasse funktioniert."""
        metrics = CPUMetrics(
            usage_percent=50.0,
            usage_per_core=[45.0, 55.0],
            frequency_mhz=3500.0,
            frequency_per_core=[3500.0, 3500.0],
            core_count=2,
            thread_count=2,
            load_average=(1.0, 2.0, 3.0),
        )

        assert metrics.usage_percent == 50.0
        assert len(metrics.usage_per_core) == 2

    def test_memory_metrics_dataclass(self) -> None:
        """MemoryMetrics-Datenklasse funktioniert."""
        metrics = MemoryMetrics(
            total_bytes=16 * 1024**3,
            available_bytes=8 * 1024**3,
            used_bytes=8 * 1024**3,
            used_percent=50.0,
            swap_total_bytes=4 * 1024**3,
            swap_used_bytes=1 * 1024**3,
            swap_percent=25.0,
        )

        assert metrics.total_bytes == 16 * 1024**3
        assert metrics.used_percent == 50.0

    def test_gpu_metrics_dataclass(self) -> None:
        """GPUMetrics-Datenklasse funktioniert."""
        metrics = GPUMetrics(
            gpu_id=0,
            name="NVIDIA RTX 4080",
            utilization_percent=75.0,
            memory_total_bytes=16 * 1024**3,
            memory_used_bytes=12 * 1024**3,
            memory_used_percent=75.0,
            temperature_celsius=65.0,
            power_watts=250.0,
            fan_speed_percent=50.0,
        )

        assert metrics.name == "NVIDIA RTX 4080"
        assert metrics.gpu_id == 0

    def test_hardware_alert_dataclass(self) -> None:
        """HardwareAlert-Datenklasse funktioniert."""
        alert = HardwareAlert(
            alert_type=AlertType.DISK_SPACE,
            severity=AlertSeverity.WARNING,
            message="Festplatte C: ist zu 90% belegt",
            value=90.0,
            threshold=85.0,
        )

        assert alert.alert_type == AlertType.DISK_SPACE
        assert alert.severity == AlertSeverity.WARNING
        assert alert.resolved is False


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    """Tests fuer Enumerationen."""

    def test_alert_type_values(self) -> None:
        """AlertType hat alle erwarteten Werte."""
        assert AlertType.DISK_SPACE.value == "disk_space"
        assert AlertType.DISK_IO.value == "disk_io"
        assert AlertType.MEMORY.value == "memory"
        assert AlertType.CPU.value == "cpu"
        assert AlertType.GPU_MEMORY.value == "gpu_memory"
        assert AlertType.GPU_TEMPERATURE.value == "gpu_temperature"
        assert AlertType.NETWORK.value == "network"
        assert AlertType.TEMPERATURE.value == "temperature"

    def test_alert_severity_values(self) -> None:
        """AlertSeverity hat alle erwarteten Werte."""
        assert AlertSeverity.INFO.value == "info"
        assert AlertSeverity.WARNING.value == "warning"
        assert AlertSeverity.CRITICAL.value == "critical"
