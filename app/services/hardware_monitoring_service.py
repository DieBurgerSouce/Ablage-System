"""
Hardware Monitoring Service für Ablage-System.

Überwacht Hardware-Metriken:
- Disk I/O
- Netzwerk
- CPU/Memory
- GPU (NVIDIA)
- Temperatur

Integriert mit Prometheus für Metriken-Export.
"""

import asyncio
import structlog
import os
import platform
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import psutil
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)


# =============================================================================
# Prometheus Metrics
# =============================================================================

# CPU Metrics
CPU_USAGE_PERCENT = Gauge(
    "hardware_cpu_usage_percent",
    "CPU usage percentage",
    ["core"],
)
CPU_FREQUENCY_MHZ = Gauge(
    "hardware_cpu_frequency_mhz",
    "CPU frequency in MHz",
    ["core"],
)
CPU_TEMPERATURE_CELSIUS = Gauge(
    "hardware_cpu_temperature_celsius",
    "CPU temperature in Celsius",
    ["sensor"],
)

# Memory Metrics
MEMORY_TOTAL_BYTES = Gauge(
    "hardware_memory_total_bytes",
    "Total memory in bytes",
)
MEMORY_AVAILABLE_BYTES = Gauge(
    "hardware_memory_available_bytes",
    "Available memory in bytes",
)
MEMORY_USED_PERCENT = Gauge(
    "hardware_memory_used_percent",
    "Memory usage percentage",
)

# Disk Metrics
DISK_TOTAL_BYTES = Gauge(
    "hardware_disk_total_bytes",
    "Total disk space in bytes",
    ["mountpoint"],
)
DISK_USED_BYTES = Gauge(
    "hardware_disk_used_bytes",
    "Used disk space in bytes",
    ["mountpoint"],
)
DISK_USED_PERCENT = Gauge(
    "hardware_disk_used_percent",
    "Disk usage percentage",
    ["mountpoint"],
)
DISK_READ_BYTES = Counter(
    "hardware_disk_read_bytes_total",
    "Total bytes read from disk",
    ["device"],
)
DISK_WRITE_BYTES = Counter(
    "hardware_disk_write_bytes_total",
    "Total bytes written to disk",
    ["device"],
)
DISK_READ_IOPS = Gauge(
    "hardware_disk_read_iops",
    "Disk read IOPS",
    ["device"],
)
DISK_WRITE_IOPS = Gauge(
    "hardware_disk_write_iops",
    "Disk write IOPS",
    ["device"],
)
DISK_IO_TIME_MS = Gauge(
    "hardware_disk_io_time_ms",
    "Time spent on I/O in milliseconds",
    ["device"],
)

# Network Metrics
NETWORK_BYTES_SENT = Counter(
    "hardware_network_bytes_sent_total",
    "Total bytes sent",
    ["interface"],
)
NETWORK_BYTES_RECV = Counter(
    "hardware_network_bytes_recv_total",
    "Total bytes received",
    ["interface"],
)
NETWORK_PACKETS_SENT = Counter(
    "hardware_network_packets_sent_total",
    "Total packets sent",
    ["interface"],
)
NETWORK_PACKETS_RECV = Counter(
    "hardware_network_packets_recv_total",
    "Total packets received",
    ["interface"],
)
NETWORK_ERRORS_IN = Counter(
    "hardware_network_errors_in_total",
    "Total inbound errors",
    ["interface"],
)
NETWORK_ERRORS_OUT = Counter(
    "hardware_network_errors_out_total",
    "Total outbound errors",
    ["interface"],
)

# GPU Metrics (NVIDIA)
GPU_UTILIZATION_PERCENT = Gauge(
    "hardware_gpu_utilization_percent",
    "GPU utilization percentage",
    ["gpu_id", "gpu_name"],
)
GPU_MEMORY_TOTAL_BYTES = Gauge(
    "hardware_gpu_memory_total_bytes",
    "Total GPU memory in bytes",
    ["gpu_id", "gpu_name"],
)
GPU_MEMORY_USED_BYTES = Gauge(
    "hardware_gpu_memory_used_bytes",
    "Used GPU memory in bytes",
    ["gpu_id", "gpu_name"],
)
GPU_MEMORY_USED_PERCENT = Gauge(
    "hardware_gpu_memory_used_percent",
    "GPU memory usage percentage",
    ["gpu_id", "gpu_name"],
)
GPU_TEMPERATURE_CELSIUS = Gauge(
    "hardware_gpu_temperature_celsius",
    "GPU temperature in Celsius",
    ["gpu_id", "gpu_name"],
)
GPU_POWER_WATTS = Gauge(
    "hardware_gpu_power_watts",
    "GPU power consumption in Watts",
    ["gpu_id", "gpu_name"],
)
GPU_FAN_SPEED_PERCENT = Gauge(
    "hardware_gpu_fan_speed_percent",
    "GPU fan speed percentage",
    ["gpu_id", "gpu_name"],
)

# System Metrics
SYSTEM_UPTIME_SECONDS = Gauge(
    "hardware_system_uptime_seconds",
    "System uptime in seconds",
)
SYSTEM_LOAD_AVERAGE = Gauge(
    "hardware_system_load_average",
    "System load average",
    ["interval"],
)


# =============================================================================
# Enums and Data Classes
# =============================================================================

class AlertSeverity(str, Enum):
    """Schweregrad von Hardware-Alerts."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Typ von Hardware-Alerts."""

    DISK_SPACE = "disk_space"
    DISK_IO = "disk_io"
    MEMORY = "memory"
    CPU = "cpu"
    GPU_MEMORY = "gpu_memory"
    GPU_TEMPERATURE = "gpu_temperature"
    NETWORK = "network"
    TEMPERATURE = "temperature"


@dataclass
class CPUMetrics:
    """CPU-Metriken."""

    usage_percent: float
    usage_per_core: list[float]
    frequency_mhz: float
    frequency_per_core: list[float]
    core_count: int
    thread_count: int
    load_average: tuple[float, float, float]  # 1min, 5min, 15min


@dataclass
class MemoryMetrics:
    """Speicher-Metriken."""

    total_bytes: int
    available_bytes: int
    used_bytes: int
    used_percent: float
    swap_total_bytes: int
    swap_used_bytes: int
    swap_percent: float


@dataclass
class DiskMetrics:
    """Festplatten-Metriken."""

    mountpoint: str
    device: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float
    read_bytes: int
    write_bytes: int
    read_iops: float
    write_iops: float
    io_time_ms: int


@dataclass
class NetworkMetrics:
    """Netzwerk-Metriken."""

    interface: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errors_in: int
    errors_out: int
    is_up: bool


@dataclass
class GPUMetrics:
    """GPU-Metriken (NVIDIA)."""

    gpu_id: int
    name: str
    utilization_percent: float
    memory_total_bytes: int
    memory_used_bytes: int
    memory_used_percent: float
    temperature_celsius: float
    power_watts: float
    fan_speed_percent: float


@dataclass
class TemperatureMetrics:
    """Temperatur-Metriken."""

    sensor_name: str
    current_celsius: float
    high_celsius: Optional[float] = None
    critical_celsius: Optional[float] = None


@dataclass
class HardwareAlert:
    """Hardware-Warnung."""

    alert_type: AlertType
    severity: AlertSeverity
    message: str
    value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False


@dataclass
class HardwareReport:
    """Vollständiger Hardware-Bericht."""

    timestamp: datetime
    hostname: str
    os_info: str
    uptime_seconds: float
    cpu: CPUMetrics
    memory: MemoryMetrics
    disks: list[DiskMetrics]
    networks: list[NetworkMetrics]
    gpus: list[GPUMetrics]
    temperatures: list[TemperatureMetrics]
    alerts: list[HardwareAlert]


# =============================================================================
# Hardware Monitoring Service
# =============================================================================

class HardwareMonitoringService:
    """Service für Hardware-Überwachung."""

    def __init__(
        self,
        disk_threshold_percent: float = 85.0,
        memory_threshold_percent: float = 85.0,
        cpu_threshold_percent: float = 90.0,
        gpu_memory_threshold_percent: float = 85.0,
        gpu_temp_threshold_celsius: float = 80.0,
        cpu_temp_threshold_celsius: float = 85.0,
    ) -> None:
        """
        Initialisiert den Hardware-Monitoring-Service.

        Args:
            disk_threshold_percent: Schwellwert für Disk-Warnung
            memory_threshold_percent: Schwellwert für Memory-Warnung
            cpu_threshold_percent: Schwellwert für CPU-Warnung
            gpu_memory_threshold_percent: Schwellwert für GPU-Memory-Warnung
            gpu_temp_threshold_celsius: Schwellwert für GPU-Temperatur-Warnung
            cpu_temp_threshold_celsius: Schwellwert für CPU-Temperatur-Warnung
        """
        self.disk_threshold = disk_threshold_percent
        self.memory_threshold = memory_threshold_percent
        self.cpu_threshold = cpu_threshold_percent
        self.gpu_memory_threshold = gpu_memory_threshold_percent
        self.gpu_temp_threshold = gpu_temp_threshold_celsius
        self.cpu_temp_threshold = cpu_temp_threshold_celsius

        # Cache für I/O-Berechnungen
        self._last_disk_io: dict[str, tuple[int, int, float]] = {}
        self._last_network_io: dict[str, tuple[int, int, float]] = {}

        # GPU-Verfügbarkeit prüfen
        self._nvml_available = self._init_nvml()

    def _init_nvml(self) -> bool:
        """Initialisiert NVIDIA Management Library."""
        try:
            import pynvml

            pynvml.nvmlInit()
            logger.info("NVML initialisiert - GPU-Monitoring verfügbar")
            return True
        except ImportError:
            logger.warning("pynvml nicht installiert - GPU-Monitoring deaktiviert")
            return False
        except Exception as e:
            logger.warning(f"NVML-Initialisierung fehlgeschlagen: {e}")
            return False

    # =========================================================================
    # CPU Metrics
    # =========================================================================

    async def get_cpu_metrics(self) -> CPUMetrics:
        """Erfasst CPU-Metriken."""
        # CPU-Auslastung (blockiert für Intervall)
        usage_per_core = await asyncio.to_thread(
            psutil.cpu_percent, interval=0.1, percpu=True
        )
        usage_total = sum(usage_per_core) / len(usage_per_core)

        # CPU-Frequenz
        freq = psutil.cpu_freq(percpu=True)
        freq_per_core = [f.current for f in freq] if freq else []
        freq_total = sum(freq_per_core) / len(freq_per_core) if freq_per_core else 0

        # Load Average (Unix-only)
        try:
            load_avg = os.getloadavg()
        except (AttributeError, OSError):
            load_avg = (0.0, 0.0, 0.0)

        # Prometheus-Metriken aktualisieren
        for i, usage in enumerate(usage_per_core):
            CPU_USAGE_PERCENT.labels(core=str(i)).set(usage)
        for i, freq_val in enumerate(freq_per_core):
            CPU_FREQUENCY_MHZ.labels(core=str(i)).set(freq_val)

        SYSTEM_LOAD_AVERAGE.labels(interval="1m").set(load_avg[0])
        SYSTEM_LOAD_AVERAGE.labels(interval="5m").set(load_avg[1])
        SYSTEM_LOAD_AVERAGE.labels(interval="15m").set(load_avg[2])

        return CPUMetrics(
            usage_percent=usage_total,
            usage_per_core=usage_per_core,
            frequency_mhz=freq_total,
            frequency_per_core=freq_per_core,
            core_count=psutil.cpu_count(logical=False) or 1,
            thread_count=psutil.cpu_count(logical=True) or 1,
            load_average=load_avg,
        )

    # =========================================================================
    # Memory Metrics
    # =========================================================================

    async def get_memory_metrics(self) -> MemoryMetrics:
        """Erfasst Speicher-Metriken."""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Prometheus-Metriken aktualisieren
        MEMORY_TOTAL_BYTES.set(mem.total)
        MEMORY_AVAILABLE_BYTES.set(mem.available)
        MEMORY_USED_PERCENT.set(mem.percent)

        return MemoryMetrics(
            total_bytes=mem.total,
            available_bytes=mem.available,
            used_bytes=mem.used,
            used_percent=mem.percent,
            swap_total_bytes=swap.total,
            swap_used_bytes=swap.used,
            swap_percent=swap.percent,
        )

    # =========================================================================
    # Disk Metrics
    # =========================================================================

    async def get_disk_metrics(self) -> list[DiskMetrics]:
        """Erfasst Festplatten-Metriken."""
        disks: list[DiskMetrics] = []
        current_time = time.time()

        # Disk I/O Counters
        io_counters = psutil.disk_io_counters(perdisk=True)

        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)

                # Device-Name normalisieren
                device = partition.device.split("/")[-1] if "/" in partition.device else partition.device

                # I/O-Metriken berechnen
                read_bytes = 0
                write_bytes = 0
                read_iops = 0.0
                write_iops = 0.0
                io_time_ms = 0

                if io_counters and device in io_counters:
                    io = io_counters[device]
                    read_bytes = io.read_bytes
                    write_bytes = io.write_bytes
                    io_time_ms = getattr(io, "busy_time", 0)

                    # IOPS berechnen (Delta seit letzter Messung)
                    if device in self._last_disk_io:
                        last_read, last_write, last_time = self._last_disk_io[device]
                        time_delta = current_time - last_time
                        if time_delta > 0:
                            read_iops = (io.read_count - last_read) / time_delta
                            write_iops = (io.write_count - last_write) / time_delta

                    self._last_disk_io[device] = (io.read_count, io.write_count, current_time)

                # Prometheus-Metriken aktualisieren
                DISK_TOTAL_BYTES.labels(mountpoint=partition.mountpoint).set(usage.total)
                DISK_USED_BYTES.labels(mountpoint=partition.mountpoint).set(usage.used)
                DISK_USED_PERCENT.labels(mountpoint=partition.mountpoint).set(usage.percent)
                DISK_READ_IOPS.labels(device=device).set(read_iops)
                DISK_WRITE_IOPS.labels(device=device).set(write_iops)
                DISK_IO_TIME_MS.labels(device=device).set(io_time_ms)

                disks.append(
                    DiskMetrics(
                        mountpoint=partition.mountpoint,
                        device=device,
                        total_bytes=usage.total,
                        used_bytes=usage.used,
                        free_bytes=usage.free,
                        used_percent=usage.percent,
                        read_bytes=read_bytes,
                        write_bytes=write_bytes,
                        read_iops=read_iops,
                        write_iops=write_iops,
                        io_time_ms=io_time_ms,
                    )
                )
            except (PermissionError, OSError) as e:
                logger.debug(f"Disk-Zugriff fehlgeschlagen für {partition.mountpoint}: {e}")
                continue

        return disks

    # =========================================================================
    # Network Metrics
    # =========================================================================

    async def get_network_metrics(self) -> list[NetworkMetrics]:
        """Erfasst Netzwerk-Metriken."""
        networks: list[NetworkMetrics] = []
        io_counters = psutil.net_io_counters(pernic=True)
        net_if_stats = psutil.net_if_stats()

        for interface, io in io_counters.items():
            # Loopback und virtuelle Interfaces überspringen
            if interface.startswith(("lo", "veth", "docker", "br-")):
                continue

            is_up = net_if_stats.get(interface, None)
            is_up = is_up.isup if is_up else False

            # Prometheus-Metriken aktualisieren
            NETWORK_BYTES_SENT.labels(interface=interface)._value.set(io.bytes_sent)
            NETWORK_BYTES_RECV.labels(interface=interface)._value.set(io.bytes_recv)
            NETWORK_PACKETS_SENT.labels(interface=interface)._value.set(io.packets_sent)
            NETWORK_PACKETS_RECV.labels(interface=interface)._value.set(io.packets_recv)
            NETWORK_ERRORS_IN.labels(interface=interface)._value.set(io.errin)
            NETWORK_ERRORS_OUT.labels(interface=interface)._value.set(io.errout)

            networks.append(
                NetworkMetrics(
                    interface=interface,
                    bytes_sent=io.bytes_sent,
                    bytes_recv=io.bytes_recv,
                    packets_sent=io.packets_sent,
                    packets_recv=io.packets_recv,
                    errors_in=io.errin,
                    errors_out=io.errout,
                    is_up=is_up,
                )
            )

        return networks

    # =========================================================================
    # GPU Metrics
    # =========================================================================

    async def get_gpu_metrics(self) -> list[GPUMetrics]:
        """Erfasst GPU-Metriken (NVIDIA)."""
        if not self._nvml_available:
            return []

        gpus: list[GPUMetrics] = []

        try:
            import pynvml

            device_count = pynvml.nvmlDeviceGetCount()

            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)

                # GPU-Name
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8")

                # Utilization
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)

                # Memory
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)

                # Temperature
                temp = pynvml.nvmlDeviceGetTemperature(
                    handle, pynvml.NVML_TEMPERATURE_GPU
                )

                # Power
                try:
                    power = pynvml.nvmlDeviceGetPowerUsage(handle) / 1000.0  # mW to W
                except pynvml.NVMLError:
                    power = 0.0

                # Fan Speed
                try:
                    fan = pynvml.nvmlDeviceGetFanSpeed(handle)
                except pynvml.NVMLError:
                    fan = 0

                # Memory-Prozent berechnen
                mem_percent = (mem.used / mem.total * 100) if mem.total > 0 else 0

                # Prometheus-Metriken aktualisieren
                labels = {"gpu_id": str(i), "gpu_name": name}
                GPU_UTILIZATION_PERCENT.labels(**labels).set(util.gpu)
                GPU_MEMORY_TOTAL_BYTES.labels(**labels).set(mem.total)
                GPU_MEMORY_USED_BYTES.labels(**labels).set(mem.used)
                GPU_MEMORY_USED_PERCENT.labels(**labels).set(mem_percent)
                GPU_TEMPERATURE_CELSIUS.labels(**labels).set(temp)
                GPU_POWER_WATTS.labels(**labels).set(power)
                GPU_FAN_SPEED_PERCENT.labels(**labels).set(fan)

                gpus.append(
                    GPUMetrics(
                        gpu_id=i,
                        name=name,
                        utilization_percent=util.gpu,
                        memory_total_bytes=mem.total,
                        memory_used_bytes=mem.used,
                        memory_used_percent=mem_percent,
                        temperature_celsius=temp,
                        power_watts=power,
                        fan_speed_percent=fan,
                    )
                )

        except Exception as e:
            logger.error(f"GPU-Metriken-Erfassung fehlgeschlagen: {e}")

        return gpus

    # =========================================================================
    # Temperature Metrics
    # =========================================================================

    async def get_temperature_metrics(self) -> list[TemperatureMetrics]:
        """Erfasst Temperatur-Metriken."""
        temps: list[TemperatureMetrics] = []

        try:
            sensors = psutil.sensors_temperatures()

            for sensor_type, entries in sensors.items():
                for entry in entries:
                    label = f"{sensor_type}_{entry.label}" if entry.label else sensor_type

                    # Prometheus-Metrik aktualisieren
                    CPU_TEMPERATURE_CELSIUS.labels(sensor=label).set(entry.current)

                    temps.append(
                        TemperatureMetrics(
                            sensor_name=label,
                            current_celsius=entry.current,
                            high_celsius=entry.high,
                            critical_celsius=entry.critical,
                        )
                    )

        except (AttributeError, OSError):
            # sensors_temperatures() nicht auf allen Plattformen verfügbar
            pass

        return temps

    # =========================================================================
    # Health Alerts
    # =========================================================================

    async def check_health_alerts(
        self,
        cpu: CPUMetrics,
        memory: MemoryMetrics,
        disks: list[DiskMetrics],
        gpus: list[GPUMetrics],
        temperatures: list[TemperatureMetrics],
    ) -> list[HardwareAlert]:
        """Prüft auf Hardware-Probleme und generiert Alerts."""
        alerts: list[HardwareAlert] = []

        # CPU-Auslastung
        if cpu.usage_percent > self.cpu_threshold:
            alerts.append(
                HardwareAlert(
                    alert_type=AlertType.CPU,
                    severity=AlertSeverity.WARNING
                    if cpu.usage_percent < 95
                    else AlertSeverity.CRITICAL,
                    message=f"CPU-Auslastung kritisch: {cpu.usage_percent:.1f}%",
                    value=cpu.usage_percent,
                    threshold=self.cpu_threshold,
                )
            )

        # Speicher
        if memory.used_percent > self.memory_threshold:
            alerts.append(
                HardwareAlert(
                    alert_type=AlertType.MEMORY,
                    severity=AlertSeverity.WARNING
                    if memory.used_percent < 95
                    else AlertSeverity.CRITICAL,
                    message=f"Speicherauslastung kritisch: {memory.used_percent:.1f}%",
                    value=memory.used_percent,
                    threshold=self.memory_threshold,
                )
            )

        # Festplatten
        for disk in disks:
            if disk.used_percent > self.disk_threshold:
                alerts.append(
                    HardwareAlert(
                        alert_type=AlertType.DISK_SPACE,
                        severity=AlertSeverity.WARNING
                        if disk.used_percent < 95
                        else AlertSeverity.CRITICAL,
                        message=f"Speicherplatz auf {disk.mountpoint} kritisch: {disk.used_percent:.1f}%",
                        value=disk.used_percent,
                        threshold=self.disk_threshold,
                    )
                )

        # GPU
        for gpu in gpus:
            # GPU-Speicher
            if gpu.memory_used_percent > self.gpu_memory_threshold:
                alerts.append(
                    HardwareAlert(
                        alert_type=AlertType.GPU_MEMORY,
                        severity=AlertSeverity.WARNING
                        if gpu.memory_used_percent < 95
                        else AlertSeverity.CRITICAL,
                        message=f"GPU {gpu.gpu_id} ({gpu.name}) Speicher kritisch: {gpu.memory_used_percent:.1f}%",
                        value=gpu.memory_used_percent,
                        threshold=self.gpu_memory_threshold,
                    )
                )

            # GPU-Temperatur
            if gpu.temperature_celsius > self.gpu_temp_threshold:
                alerts.append(
                    HardwareAlert(
                        alert_type=AlertType.GPU_TEMPERATURE,
                        severity=AlertSeverity.WARNING
                        if gpu.temperature_celsius < 90
                        else AlertSeverity.CRITICAL,
                        message=f"GPU {gpu.gpu_id} ({gpu.name}) Temperatur kritisch: {gpu.temperature_celsius}°C",
                        value=gpu.temperature_celsius,
                        threshold=self.gpu_temp_threshold,
                    )
                )

        # CPU-Temperatur
        for temp in temperatures:
            if temp.current_celsius > self.cpu_temp_threshold:
                alerts.append(
                    HardwareAlert(
                        alert_type=AlertType.TEMPERATURE,
                        severity=AlertSeverity.WARNING
                        if temp.current_celsius < 95
                        else AlertSeverity.CRITICAL,
                        message=f"Temperatur {temp.sensor_name} kritisch: {temp.current_celsius}°C",
                        value=temp.current_celsius,
                        threshold=self.cpu_temp_threshold,
                    )
                )

        return alerts

    # =========================================================================
    # Full Hardware Report
    # =========================================================================

    async def get_full_hardware_status(self) -> HardwareReport:
        """Erfasst vollständigen Hardware-Status."""
        # Alle Metriken parallel erfassen
        cpu, memory, disks, networks, gpus, temps = await asyncio.gather(
            self.get_cpu_metrics(),
            self.get_memory_metrics(),
            self.get_disk_metrics(),
            self.get_network_metrics(),
            self.get_gpu_metrics(),
            self.get_temperature_metrics(),
        )

        # Uptime
        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time
        SYSTEM_UPTIME_SECONDS.set(uptime)

        # System-Info
        uname = platform.uname()
        os_info = f"{uname.system} {uname.release} ({uname.machine})"

        # Alerts prüfen
        alerts = await self.check_health_alerts(cpu, memory, disks, gpus, temps)

        return HardwareReport(
            timestamp=datetime.utcnow(),
            hostname=uname.node,
            os_info=os_info,
            uptime_seconds=uptime,
            cpu=cpu,
            memory=memory,
            disks=disks,
            networks=networks,
            gpus=gpus,
            temperatures=temps,
            alerts=alerts,
        )

    # =========================================================================
    # Quick Health Check
    # =========================================================================

    async def quick_health_check(self) -> dict[str, Any]:
        """Schnelle Health-Prüfung für API-Endpoints."""
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        health = {
            "status": "healthy",
            "cpu_percent": cpu,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent,
            "issues": [],
        }

        # Quick Checks
        if cpu > self.cpu_threshold:
            health["issues"].append(f"CPU hoch: {cpu:.1f}%")
        if memory.percent > self.memory_threshold:
            health["issues"].append(f"Speicher hoch: {memory.percent:.1f}%")
        if disk.percent > self.disk_threshold:
            health["issues"].append(f"Festplatte voll: {disk.percent:.1f}%")

        # GPU-Check
        if self._nvml_available:
            try:
                import pynvml

                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
                gpu_percent = mem.used / mem.total * 100

                health["gpu_memory_percent"] = gpu_percent
                health["gpu_temperature"] = temp

                if gpu_percent > self.gpu_memory_threshold:
                    health["issues"].append(f"GPU-Speicher hoch: {gpu_percent:.1f}%")
                if temp > self.gpu_temp_threshold:
                    health["issues"].append(f"GPU-Temperatur hoch: {temp}°C")

            except Exception as e:
                logger.debug(f"GPU-Quick-Check fehlgeschlagen: {e}")

        if health["issues"]:
            health["status"] = "degraded" if len(health["issues"]) < 3 else "critical"

        return health


# =============================================================================
# Singleton Instance
# =============================================================================

_hardware_monitoring_service: Optional[HardwareMonitoringService] = None


def get_hardware_monitoring_service() -> HardwareMonitoringService:
    """Gibt die Singleton-Instanz des Hardware-Monitoring-Service zurück."""
    global _hardware_monitoring_service
    if _hardware_monitoring_service is None:
        _hardware_monitoring_service = HardwareMonitoringService()
    return _hardware_monitoring_service
