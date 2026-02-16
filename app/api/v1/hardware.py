"""
Hardware Monitoring API Endpoints.

Stellt Hardware-Metriken und Health-Status bereit:
- GET /api/v1/hardware/status - Vollständiger Hardware-Bericht
- GET /api/v1/hardware/health - Schneller Health-Check
- GET /api/v1/hardware/cpu - CPU-Metriken
- GET /api/v1/hardware/memory - Speicher-Metriken
- GET /api/v1/hardware/disks - Festplatten-Metriken
- GET /api/v1/hardware/gpu - GPU-Metriken
- GET /api/v1/hardware/network - Netzwerk-Metriken
- GET /api/v1/hardware/alerts - Aktive Hardware-Alerts
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_superuser
from app.db.models import User
from app.services.hardware_monitoring_service import (
    AlertSeverity,
    AlertType,
    get_hardware_monitoring_service,
)

router = APIRouter(prefix="/hardware", tags=["Hardware-Monitoring"])


# =============================================================================
# Response Models
# =============================================================================


class CPUMetricsResponse(BaseModel):
    """CPU-Metriken Antwort."""

    usage_percent: float = Field(..., description="Gesamte CPU-Auslastung in Prozent")
    usage_per_core: list[float] = Field(..., description="CPU-Auslastung pro Kern")
    frequency_mhz: float = Field(..., description="Durchschnittliche CPU-Frequenz")
    core_count: int = Field(..., description="Anzahl physischer Kerne")
    thread_count: int = Field(..., description="Anzahl logischer Threads")
    load_average: tuple[float, float, float] = Field(
        ..., description="Load Average (1min, 5min, 15min)"
    )


class MemoryMetricsResponse(BaseModel):
    """Speicher-Metriken Antwort."""

    total_gb: float = Field(..., description="Gesamtspeicher in GB")
    available_gb: float = Field(..., description="Verfügbarer Speicher in GB")
    used_gb: float = Field(..., description="Belegter Speicher in GB")
    used_percent: float = Field(..., description="Speicherbelegung in Prozent")
    swap_total_gb: float = Field(..., description="Swap-Speicher gesamt in GB")
    swap_used_gb: float = Field(..., description="Swap-Speicher belegt in GB")
    swap_percent: float = Field(..., description="Swap-Belegung in Prozent")


class DiskMetricsResponse(BaseModel):
    """Festplatten-Metriken Antwort."""

    mountpoint: str = Field(..., description="Mount-Punkt")
    device: str = Field(..., description="Geraetename")
    total_gb: float = Field(..., description="Gesamtkapazitaet in GB")
    used_gb: float = Field(..., description="Belegter Speicher in GB")
    free_gb: float = Field(..., description="Freier Speicher in GB")
    used_percent: float = Field(..., description="Belegung in Prozent")
    read_iops: float = Field(..., description="Lese-IOPS")
    write_iops: float = Field(..., description="Schreib-IOPS")


class NetworkMetricsResponse(BaseModel):
    """Netzwerk-Metriken Antwort."""

    interface: str = Field(..., description="Interface-Name")
    bytes_sent_mb: float = Field(..., description="Gesendete Daten in MB")
    bytes_recv_mb: float = Field(..., description="Empfangene Daten in MB")
    packets_sent: int = Field(..., description="Gesendete Pakete")
    packets_recv: int = Field(..., description="Empfangene Pakete")
    errors_in: int = Field(..., description="Eingehende Fehler")
    errors_out: int = Field(..., description="Ausgehende Fehler")
    is_up: bool = Field(..., description="Interface aktiv")


class GPUMetricsResponse(BaseModel):
    """GPU-Metriken Antwort."""

    gpu_id: int = Field(..., description="GPU-ID")
    name: str = Field(..., description="GPU-Name")
    utilization_percent: float = Field(..., description="GPU-Auslastung in Prozent")
    memory_total_gb: float = Field(..., description="VRAM gesamt in GB")
    memory_used_gb: float = Field(..., description="VRAM belegt in GB")
    memory_used_percent: float = Field(..., description="VRAM-Belegung in Prozent")
    temperature_celsius: float = Field(..., description="Temperatur in Celsius")
    power_watts: float = Field(..., description="Leistungsaufnahme in Watt")
    fan_speed_percent: float = Field(..., description="Lueftergeschwindigkeit in Prozent")


class TemperatureResponse(BaseModel):
    """Temperatur-Metriken Antwort."""

    sensor_name: str = Field(..., description="Sensor-Name")
    current_celsius: float = Field(..., description="Aktuelle Temperatur")
    high_celsius: float | None = Field(None, description="Warntemperatur")
    critical_celsius: float | None = Field(None, description="Kritische Temperatur")


class HardwareAlertResponse(BaseModel):
    """Hardware-Alert Antwort."""

    alert_type: str = Field(..., description="Alert-Typ")
    severity: str = Field(..., description="Schweregrad")
    message: str = Field(..., description="Alert-Nachricht")
    value: float = Field(..., description="Aktueller Wert")
    threshold: float = Field(..., description="Schwellwert")
    timestamp: datetime = Field(..., description="Zeitstempel")


class HardwareStatusResponse(BaseModel):
    """Vollständiger Hardware-Status Antwort."""

    timestamp: datetime = Field(..., description="Zeitstempel der Messung")
    hostname: str = Field(..., description="Hostname")
    os_info: str = Field(..., description="Betriebssystem-Info")
    uptime_hours: float = Field(..., description="Uptime in Stunden")
    cpu: CPUMetricsResponse = Field(..., description="CPU-Metriken")
    memory: MemoryMetricsResponse = Field(..., description="Speicher-Metriken")
    disks: list[DiskMetricsResponse] = Field(..., description="Festplatten-Metriken")
    networks: list[NetworkMetricsResponse] = Field(..., description="Netzwerk-Metriken")
    gpus: list[GPUMetricsResponse] = Field(..., description="GPU-Metriken")
    temperatures: list[TemperatureResponse] = Field(..., description="Temperatur-Metriken")
    alerts: list[HardwareAlertResponse] = Field(..., description="Aktive Alerts")


class HealthCheckResponse(BaseModel):
    """Quick Health Check Antwort."""

    status: str = Field(..., description="Status: healthy, degraded, critical")
    cpu_percent: float = Field(..., description="CPU-Auslastung")
    memory_percent: float = Field(..., description="Speicher-Auslastung")
    disk_percent: float = Field(..., description="Festplatten-Belegung")
    gpu_memory_percent: float | None = Field(None, description="GPU-VRAM-Belegung")
    gpu_temperature: float | None = Field(None, description="GPU-Temperatur")
    issues: list[str] = Field(..., description="Liste von Problemen")


# =============================================================================
# Helper Functions
# =============================================================================


def bytes_to_gb(bytes_val: int) -> float:
    """Konvertiert Bytes zu GB."""
    return round(bytes_val / (1024**3), 2)


def bytes_to_mb(bytes_val: int) -> float:
    """Konvertiert Bytes zu MB."""
    return round(bytes_val / (1024**2), 2)


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/status",
    response_model=HardwareStatusResponse,
    summary="Vollständiger Hardware-Status",
    description="Liefert detaillierte Hardware-Metriken inklusive CPU, Memory, Disk, GPU und Alerts.",
)
async def get_hardware_status(
    current_user: User = Depends(get_current_superuser),
) -> HardwareStatusResponse:
    """Erfasst vollständigen Hardware-Status."""
    service = get_hardware_monitoring_service()
    report = await service.get_full_hardware_status()

    return HardwareStatusResponse(
        timestamp=report.timestamp,
        hostname=report.hostname,
        os_info=report.os_info,
        uptime_hours=round(report.uptime_seconds / 3600, 2),
        cpu=CPUMetricsResponse(
            usage_percent=report.cpu.usage_percent,
            usage_per_core=report.cpu.usage_per_core,
            frequency_mhz=report.cpu.frequency_mhz,
            core_count=report.cpu.core_count,
            thread_count=report.cpu.thread_count,
            load_average=report.cpu.load_average,
        ),
        memory=MemoryMetricsResponse(
            total_gb=bytes_to_gb(report.memory.total_bytes),
            available_gb=bytes_to_gb(report.memory.available_bytes),
            used_gb=bytes_to_gb(report.memory.used_bytes),
            used_percent=report.memory.used_percent,
            swap_total_gb=bytes_to_gb(report.memory.swap_total_bytes),
            swap_used_gb=bytes_to_gb(report.memory.swap_used_bytes),
            swap_percent=report.memory.swap_percent,
        ),
        disks=[
            DiskMetricsResponse(
                mountpoint=d.mountpoint,
                device=d.device,
                total_gb=bytes_to_gb(d.total_bytes),
                used_gb=bytes_to_gb(d.used_bytes),
                free_gb=bytes_to_gb(d.free_bytes),
                used_percent=d.used_percent,
                read_iops=d.read_iops,
                write_iops=d.write_iops,
            )
            for d in report.disks
        ],
        networks=[
            NetworkMetricsResponse(
                interface=n.interface,
                bytes_sent_mb=bytes_to_mb(n.bytes_sent),
                bytes_recv_mb=bytes_to_mb(n.bytes_recv),
                packets_sent=n.packets_sent,
                packets_recv=n.packets_recv,
                errors_in=n.errors_in,
                errors_out=n.errors_out,
                is_up=n.is_up,
            )
            for n in report.networks
        ],
        gpus=[
            GPUMetricsResponse(
                gpu_id=g.gpu_id,
                name=g.name,
                utilization_percent=g.utilization_percent,
                memory_total_gb=bytes_to_gb(g.memory_total_bytes),
                memory_used_gb=bytes_to_gb(g.memory_used_bytes),
                memory_used_percent=g.memory_used_percent,
                temperature_celsius=g.temperature_celsius,
                power_watts=g.power_watts,
                fan_speed_percent=g.fan_speed_percent,
            )
            for g in report.gpus
        ],
        temperatures=[
            TemperatureResponse(
                sensor_name=t.sensor_name,
                current_celsius=t.current_celsius,
                high_celsius=t.high_celsius,
                critical_celsius=t.critical_celsius,
            )
            for t in report.temperatures
        ],
        alerts=[
            HardwareAlertResponse(
                alert_type=a.alert_type.value,
                severity=a.severity.value,
                message=a.message,
                value=a.value,
                threshold=a.threshold,
                timestamp=a.timestamp,
            )
            for a in report.alerts
        ],
    )


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Schneller Health-Check",
    description="Schnelle Überprüfung der wichtigsten Hardware-Metriken.",
)
async def get_hardware_health(
    current_user: User = Depends(get_current_superuser),
) -> HealthCheckResponse:
    """Schneller Hardware-Health-Check."""
    service = get_hardware_monitoring_service()
    health = await service.quick_health_check()

    return HealthCheckResponse(
        status=health["status"],
        cpu_percent=health["cpu_percent"],
        memory_percent=health["memory_percent"],
        disk_percent=health["disk_percent"],
        gpu_memory_percent=health.get("gpu_memory_percent"),
        gpu_temperature=health.get("gpu_temperature"),
        issues=health["issues"],
    )


@router.get(
    "/cpu",
    response_model=CPUMetricsResponse,
    summary="CPU-Metriken",
    description="Detaillierte CPU-Auslastung und Frequenz.",
)
async def get_cpu_metrics(
    current_user: User = Depends(get_current_superuser),
) -> CPUMetricsResponse:
    """Erfasst CPU-Metriken."""
    service = get_hardware_monitoring_service()
    cpu = await service.get_cpu_metrics()

    return CPUMetricsResponse(
        usage_percent=cpu.usage_percent,
        usage_per_core=cpu.usage_per_core,
        frequency_mhz=cpu.frequency_mhz,
        core_count=cpu.core_count,
        thread_count=cpu.thread_count,
        load_average=cpu.load_average,
    )


@router.get(
    "/memory",
    response_model=MemoryMetricsResponse,
    summary="Speicher-Metriken",
    description="RAM- und Swap-Auslastung.",
)
async def get_memory_metrics(
    current_user: User = Depends(get_current_superuser),
) -> MemoryMetricsResponse:
    """Erfasst Speicher-Metriken."""
    service = get_hardware_monitoring_service()
    memory = await service.get_memory_metrics()

    return MemoryMetricsResponse(
        total_gb=bytes_to_gb(memory.total_bytes),
        available_gb=bytes_to_gb(memory.available_bytes),
        used_gb=bytes_to_gb(memory.used_bytes),
        used_percent=memory.used_percent,
        swap_total_gb=bytes_to_gb(memory.swap_total_bytes),
        swap_used_gb=bytes_to_gb(memory.swap_used_bytes),
        swap_percent=memory.swap_percent,
    )


@router.get(
    "/disks",
    response_model=list[DiskMetricsResponse],
    summary="Festplatten-Metriken",
    description="Speicherplatz und I/O-Statistiken aller Festplatten.",
)
async def get_disk_metrics(
    current_user: User = Depends(get_current_superuser),
) -> list[DiskMetricsResponse]:
    """Erfasst Festplatten-Metriken."""
    service = get_hardware_monitoring_service()
    disks = await service.get_disk_metrics()

    return [
        DiskMetricsResponse(
            mountpoint=d.mountpoint,
            device=d.device,
            total_gb=bytes_to_gb(d.total_bytes),
            used_gb=bytes_to_gb(d.used_bytes),
            free_gb=bytes_to_gb(d.free_bytes),
            used_percent=d.used_percent,
            read_iops=d.read_iops,
            write_iops=d.write_iops,
        )
        for d in disks
    ]


@router.get(
    "/gpu",
    response_model=list[GPUMetricsResponse],
    summary="GPU-Metriken",
    description="NVIDIA GPU-Auslastung, VRAM und Temperatur.",
)
async def get_gpu_metrics(
    current_user: User = Depends(get_current_superuser),
) -> list[GPUMetricsResponse]:
    """Erfasst GPU-Metriken."""
    service = get_hardware_monitoring_service()
    gpus = await service.get_gpu_metrics()

    if not gpus:
        return []

    return [
        GPUMetricsResponse(
            gpu_id=g.gpu_id,
            name=g.name,
            utilization_percent=g.utilization_percent,
            memory_total_gb=bytes_to_gb(g.memory_total_bytes),
            memory_used_gb=bytes_to_gb(g.memory_used_bytes),
            memory_used_percent=g.memory_used_percent,
            temperature_celsius=g.temperature_celsius,
            power_watts=g.power_watts,
            fan_speed_percent=g.fan_speed_percent,
        )
        for g in gpus
    ]


@router.get(
    "/network",
    response_model=list[NetworkMetricsResponse],
    summary="Netzwerk-Metriken",
    description="Netzwerk-Traffic und Fehler pro Interface.",
)
async def get_network_metrics(
    current_user: User = Depends(get_current_superuser),
) -> list[NetworkMetricsResponse]:
    """Erfasst Netzwerk-Metriken."""
    service = get_hardware_monitoring_service()
    networks = await service.get_network_metrics()

    return [
        NetworkMetricsResponse(
            interface=n.interface,
            bytes_sent_mb=bytes_to_mb(n.bytes_sent),
            bytes_recv_mb=bytes_to_mb(n.bytes_recv),
            packets_sent=n.packets_sent,
            packets_recv=n.packets_recv,
            errors_in=n.errors_in,
            errors_out=n.errors_out,
            is_up=n.is_up,
        )
        for n in networks
    ]


@router.get(
    "/alerts",
    response_model=list[HardwareAlertResponse],
    summary="Aktive Hardware-Alerts",
    description="Liste aller aktuellen Hardware-Warnungen.",
)
async def get_hardware_alerts(
    current_user: User = Depends(get_current_superuser),
) -> list[HardwareAlertResponse]:
    """Liefert aktive Hardware-Alerts."""
    service = get_hardware_monitoring_service()
    report = await service.get_full_hardware_status()

    return [
        HardwareAlertResponse(
            alert_type=a.alert_type.value,
            severity=a.severity.value,
            message=a.message,
            value=a.value,
            threshold=a.threshold,
            timestamp=a.timestamp,
        )
        for a in report.alerts
    ]
