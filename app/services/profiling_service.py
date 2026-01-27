# -*- coding: utf-8 -*-
"""
Performance Profiling Service.

Erfasst detaillierte Performance-Metriken fuer Endpoints:
- Latenz-Verteilung (min, max, avg, p50, p95, p99)
- Langsame Requests
- Hot Paths (haeufig aufgerufene Endpoints)
- Ressourcenverbrauch pro Endpoint
- Memory Snapshots

Feinpoliert und durchdacht - Enterprise-grade Profiling.
"""

import statistics
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import structlog
from prometheus_client import Counter, Gauge, Histogram

logger = structlog.get_logger(__name__)


# =============================================================================
# PROMETHEUS METRIKEN
# =============================================================================

PROFILING_REQUESTS = Counter(
    "ablage_profiling_requests_total",
    "Anzahl profilierter Requests",
    ["endpoint", "method"],
)

PROFILING_LATENCY = Histogram(
    "ablage_profiling_latency_seconds",
    "Request-Latenz in Sekunden",
    ["endpoint", "method"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

PROFILING_SLOW_REQUESTS = Counter(
    "ablage_profiling_slow_requests_total",
    "Anzahl langsamer Requests",
    ["endpoint", "method"],
)

PROFILING_MEMORY_USAGE = Gauge(
    "ablage_profiling_memory_usage_bytes",
    "Memory-Nutzung waehrend Profiling",
    ["phase"],
)


# =============================================================================
# DATA CLASSES
# =============================================================================


class ProfilingLevel(str, Enum):
    """Profiling-Detailgrad."""

    OFF = "off"
    BASIC = "basic"  # Nur Timings
    DETAILED = "detailed"  # Timings + Memory
    FULL = "full"  # Alles inklusive Stack Traces


@dataclass
class EndpointStats:
    """Statistiken fuer einen einzelnen Endpoint."""

    endpoint: str
    method: str
    request_count: int = 0
    total_time_ms: float = 0.0
    min_time_ms: float = float("inf")
    max_time_ms: float = 0.0
    times: List[float] = field(default_factory=list)
    error_count: int = 0
    slow_request_count: int = 0
    last_request_time: Optional[datetime] = None

    def add_timing(self, duration_ms: float, is_error: bool = False) -> None:
        """Fuegt neues Timing hinzu."""
        self.request_count += 1
        self.total_time_ms += duration_ms
        self.min_time_ms = min(self.min_time_ms, duration_ms)
        self.max_time_ms = max(self.max_time_ms, duration_ms)
        self.last_request_time = datetime.now(timezone.utc)

        # Nur letzte 1000 Timings behalten fuer Perzentil-Berechnung
        if len(self.times) >= 1000:
            self.times.pop(0)
        self.times.append(duration_ms)

        if is_error:
            self.error_count += 1

    def get_percentile(self, percentile: float) -> float:
        """Berechnet Perzentil."""
        if not self.times:
            return 0.0
        sorted_times = sorted(self.times)
        idx = int(len(sorted_times) * percentile / 100)
        return sorted_times[min(idx, len(sorted_times) - 1)]

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        avg_time = self.total_time_ms / self.request_count if self.request_count > 0 else 0
        return {
            "endpoint": self.endpoint,
            "method": self.method,
            "request_count": self.request_count,
            "total_time_ms": round(self.total_time_ms, 2),
            "avg_time_ms": round(avg_time, 2),
            "min_time_ms": round(self.min_time_ms, 2) if self.min_time_ms != float("inf") else 0,
            "max_time_ms": round(self.max_time_ms, 2),
            "p50_time_ms": round(self.get_percentile(50), 2),
            "p95_time_ms": round(self.get_percentile(95), 2),
            "p99_time_ms": round(self.get_percentile(99), 2),
            "error_count": self.error_count,
            "error_rate_percent": round(self.error_count / self.request_count * 100, 2) if self.request_count > 0 else 0,
            "slow_request_count": self.slow_request_count,
            "last_request_time": self.last_request_time.isoformat() if self.last_request_time else None,
        }


@dataclass
class SlowRequest:
    """Aufzeichnung eines langsamen Requests."""

    timestamp: datetime
    endpoint: str
    method: str
    duration_ms: float
    status_code: int
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    query_params: Optional[str] = None
    memory_before_mb: Optional[float] = None
    memory_after_mb: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "endpoint": self.endpoint,
            "method": self.method,
            "duration_ms": round(self.duration_ms, 2),
            "status_code": self.status_code,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "query_params": self.query_params,
            "memory_before_mb": round(self.memory_before_mb, 2) if self.memory_before_mb else None,
            "memory_after_mb": round(self.memory_after_mb, 2) if self.memory_after_mb else None,
            "memory_delta_mb": round(self.memory_after_mb - self.memory_before_mb, 2) if self.memory_before_mb and self.memory_after_mb else None,
        }


@dataclass
class MemorySnapshot:
    """Memory-Snapshot zu einem Zeitpunkt."""

    timestamp: datetime
    rss_mb: float
    vms_mb: float
    shared_mb: float
    heap_mb: Optional[float] = None
    gpu_used_mb: Optional[float] = None
    context: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "rss_mb": round(self.rss_mb, 2),
            "vms_mb": round(self.vms_mb, 2),
            "shared_mb": round(self.shared_mb, 2),
            "heap_mb": round(self.heap_mb, 2) if self.heap_mb else None,
            "gpu_used_mb": round(self.gpu_used_mb, 2) if self.gpu_used_mb else None,
            "context": self.context,
        }


# =============================================================================
# PROFILING SERVICE
# =============================================================================


class ProfilingService:
    """
    Singleton Service fuer Performance Profiling.

    Features:
    - Endpoint-Timing-Statistiken
    - Langsame Request-Aufzeichnung
    - Memory-Snapshots
    - Konfigurierbare Schwellwerte
    """

    _instance: Optional["ProfilingService"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ProfilingService":
        """Singleton Pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialisiere Service."""
        if self._initialized:
            return

        self._initialized = True
        self._stats_lock = threading.Lock()

        # Konfiguration
        self._profiling_level = ProfilingLevel.BASIC
        self._slow_request_threshold_ms = 1000.0  # 1 Sekunde
        self._max_slow_requests = 100  # Maximale Anzahl gespeicherter langsamer Requests
        self._max_memory_snapshots = 100

        # Daten
        self._endpoint_stats: Dict[str, EndpointStats] = {}
        self._slow_requests: List[SlowRequest] = []
        self._memory_snapshots: List[MemorySnapshot] = []
        self._start_time = datetime.now(timezone.utc)

        # Excluded Paths
        self._excluded_paths = {
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        }

        logger.info(
            "profiling_service_initialized",
            level=self._profiling_level.value,
            slow_threshold_ms=self._slow_request_threshold_ms,
        )

    def record_request(
        self,
        endpoint: str,
        method: str,
        duration_ms: float,
        status_code: int,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        query_params: Optional[str] = None,
        memory_before_mb: Optional[float] = None,
        memory_after_mb: Optional[float] = None,
    ) -> None:
        """
        Zeichnet Request-Metriken auf.

        Args:
            endpoint: API-Endpoint-Pfad
            method: HTTP-Methode
            duration_ms: Dauer in Millisekunden
            status_code: HTTP-Status-Code
            request_id: Optional Request-ID
            user_id: Optional User-ID
            query_params: Optional Query-Parameter
            memory_before_mb: Memory vor Request
            memory_after_mb: Memory nach Request
        """
        if self._profiling_level == ProfilingLevel.OFF:
            return

        # Excluded Paths ueberspringen
        if any(endpoint.startswith(p) for p in self._excluded_paths):
            return

        # Prometheus Metriken
        PROFILING_REQUESTS.labels(endpoint=endpoint, method=method).inc()
        PROFILING_LATENCY.labels(endpoint=endpoint, method=method).observe(duration_ms / 1000)

        with self._stats_lock:
            # Endpoint-Stats aktualisieren
            key = f"{method}:{endpoint}"
            if key not in self._endpoint_stats:
                self._endpoint_stats[key] = EndpointStats(endpoint=endpoint, method=method)

            is_error = status_code >= 400
            self._endpoint_stats[key].add_timing(duration_ms, is_error)

            # Langsame Requests aufzeichnen
            is_slow = duration_ms > self._slow_request_threshold_ms
            if is_slow:
                self._endpoint_stats[key].slow_request_count += 1
                PROFILING_SLOW_REQUESTS.labels(endpoint=endpoint, method=method).inc()

                slow_req = SlowRequest(
                    timestamp=datetime.now(timezone.utc),
                    endpoint=endpoint,
                    method=method,
                    duration_ms=duration_ms,
                    status_code=status_code,
                    request_id=request_id,
                    user_id=user_id,
                    query_params=query_params,
                    memory_before_mb=memory_before_mb,
                    memory_after_mb=memory_after_mb,
                )
                self._slow_requests.append(slow_req)

                # Buffer begrenzen
                if len(self._slow_requests) > self._max_slow_requests:
                    self._slow_requests.pop(0)

                logger.warning(
                    "slow_request_detected",
                    endpoint=endpoint,
                    method=method,
                    duration_ms=round(duration_ms, 2),
                    threshold_ms=self._slow_request_threshold_ms,
                    request_id=request_id,
                )

    def take_memory_snapshot(self, context: Optional[str] = None) -> MemorySnapshot:
        """
        Erstellt einen Memory-Snapshot.

        Args:
            context: Optionaler Kontext-String

        Returns:
            MemorySnapshot mit aktuellen Werten
        """
        import psutil

        process = psutil.Process()
        mem_info = process.memory_info()

        gpu_used_mb = None
        try:
            import torch

            if torch.cuda.is_available():
                gpu_used_mb = torch.cuda.memory_allocated() / (1024 * 1024)
        except ImportError as e:
            logger.debug("torch_import_failed_for_memory_snapshot", error_type=type(e).__name__)

        snapshot = MemorySnapshot(
            timestamp=datetime.now(timezone.utc),
            rss_mb=mem_info.rss / (1024 * 1024),
            vms_mb=mem_info.vms / (1024 * 1024),
            shared_mb=getattr(mem_info, "shared", 0) / (1024 * 1024),
            gpu_used_mb=gpu_used_mb,
            context=context,
        )

        with self._stats_lock:
            self._memory_snapshots.append(snapshot)
            if len(self._memory_snapshots) > self._max_memory_snapshots:
                self._memory_snapshots.pop(0)

        # Prometheus
        PROFILING_MEMORY_USAGE.labels(phase="rss").set(mem_info.rss)
        if gpu_used_mb:
            PROFILING_MEMORY_USAGE.labels(phase="gpu").set(gpu_used_mb * 1024 * 1024)

        return snapshot

    def get_endpoint_stats(
        self,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        limit: int = 50,
        sort_by: str = "request_count",
    ) -> List[Dict[str, Any]]:
        """
        Gibt Endpoint-Statistiken zurueck.

        Args:
            endpoint: Optional Filter nach Endpoint
            method: Optional Filter nach Methode
            limit: Maximale Anzahl Ergebnisse
            sort_by: Sortierfeld (request_count, avg_time_ms, max_time_ms, error_count)

        Returns:
            Liste von Endpoint-Statistiken
        """
        with self._stats_lock:
            stats = list(self._endpoint_stats.values())

        # Filter
        if endpoint:
            stats = [s for s in stats if endpoint in s.endpoint]
        if method:
            stats = [s for s in stats if s.method.upper() == method.upper()]

        # Sortieren
        sort_fields = {
            "request_count": lambda s: s.request_count,
            "avg_time_ms": lambda s: s.total_time_ms / max(s.request_count, 1),
            "max_time_ms": lambda s: s.max_time_ms,
            "error_count": lambda s: s.error_count,
            "slow_request_count": lambda s: s.slow_request_count,
        }
        sort_func = sort_fields.get(sort_by, sort_fields["request_count"])
        stats = sorted(stats, key=sort_func, reverse=True)

        return [s.to_dict() for s in stats[:limit]]

    def get_slow_requests(
        self,
        endpoint: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Gibt langsame Requests zurueck.

        Args:
            endpoint: Optional Filter nach Endpoint
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von langsamen Requests
        """
        with self._stats_lock:
            requests = list(self._slow_requests)

        # Filter
        if endpoint:
            requests = [r for r in requests if endpoint in r.endpoint]

        # Nach Dauer sortieren (langsamste zuerst)
        requests = sorted(requests, key=lambda r: r.duration_ms, reverse=True)

        return [r.to_dict() for r in requests[:limit]]

    def get_hot_paths(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Gibt die meistgenutzten Endpoints zurueck.

        Args:
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste der Hot Paths
        """
        stats = self.get_endpoint_stats(limit=limit, sort_by="request_count")
        return [
            {
                "rank": idx + 1,
                "endpoint": s["endpoint"],
                "method": s["method"],
                "request_count": s["request_count"],
                "avg_time_ms": s["avg_time_ms"],
                "requests_per_second": round(s["request_count"] / max((datetime.now(timezone.utc) - self._start_time).total_seconds(), 1), 2),
            }
            for idx, s in enumerate(stats)
        ]

    def get_memory_snapshots(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Gibt Memory-Snapshots zurueck.

        Args:
            limit: Maximale Anzahl Ergebnisse

        Returns:
            Liste von Memory-Snapshots
        """
        with self._stats_lock:
            snapshots = list(self._memory_snapshots)

        # Neueste zuerst
        snapshots = sorted(snapshots, key=lambda s: s.timestamp, reverse=True)

        return [s.to_dict() for s in snapshots[:limit]]

    def get_summary(self) -> Dict[str, Any]:
        """
        Gibt Profiling-Zusammenfassung zurueck.

        Returns:
            Dictionary mit Zusammenfassung
        """
        with self._stats_lock:
            all_stats = list(self._endpoint_stats.values())
            slow_requests = list(self._slow_requests)

        total_requests = sum(s.request_count for s in all_stats)
        total_errors = sum(s.error_count for s in all_stats)
        total_slow = sum(s.slow_request_count for s in all_stats)

        all_times = []
        for s in all_stats:
            all_times.extend(s.times)

        avg_time = statistics.mean(all_times) if all_times else 0
        p95_time = sorted(all_times)[int(len(all_times) * 0.95)] if all_times else 0
        p99_time = sorted(all_times)[int(len(all_times) * 0.99)] if all_times else 0

        uptime = datetime.now(timezone.utc) - self._start_time

        return {
            "status": "aktiv" if self._profiling_level != ProfilingLevel.OFF else "deaktiviert",
            "profiling_level": self._profiling_level.value,
            "uptime_seconds": round(uptime.total_seconds(), 2),
            "uptime_formatted": str(uptime).split(".")[0],
            "total_endpoints_tracked": len(all_stats),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate_percent": round(total_errors / max(total_requests, 1) * 100, 2),
            "total_slow_requests": total_slow,
            "slow_request_threshold_ms": self._slow_request_threshold_ms,
            "avg_latency_ms": round(avg_time, 2),
            "p95_latency_ms": round(p95_time, 2),
            "p99_latency_ms": round(p99_time, 2),
            "memory_snapshots_count": len(self._memory_snapshots),
            "slow_requests_buffer_count": len(slow_requests),
        }

    def configure(
        self,
        level: Optional[ProfilingLevel] = None,
        slow_threshold_ms: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Konfiguriert Profiling-Einstellungen.

        Args:
            level: Neuer Profiling-Level
            slow_threshold_ms: Neuer Schwellwert fuer langsame Requests

        Returns:
            Aktuelle Konfiguration
        """
        if level is not None:
            old_level = self._profiling_level
            self._profiling_level = level
            logger.info(
                "profiling_level_changed",
                old_level=old_level.value,
                new_level=level.value,
            )

        if slow_threshold_ms is not None:
            old_threshold = self._slow_request_threshold_ms
            self._slow_request_threshold_ms = slow_threshold_ms
            logger.info(
                "slow_threshold_changed",
                old_threshold_ms=old_threshold,
                new_threshold_ms=slow_threshold_ms,
            )

        return {
            "profiling_level": self._profiling_level.value,
            "slow_request_threshold_ms": self._slow_request_threshold_ms,
            "max_slow_requests": self._max_slow_requests,
            "max_memory_snapshots": self._max_memory_snapshots,
            "excluded_paths": list(self._excluded_paths),
        }

    def reset_stats(self) -> Dict[str, Any]:
        """
        Setzt alle Statistiken zurueck.

        Returns:
            Bestaetigung mit geloeschten Counts
        """
        with self._stats_lock:
            endpoint_count = len(self._endpoint_stats)
            slow_count = len(self._slow_requests)
            snapshot_count = len(self._memory_snapshots)

            self._endpoint_stats.clear()
            self._slow_requests.clear()
            self._memory_snapshots.clear()
            self._start_time = datetime.now(timezone.utc)

        logger.warning(
            "profiling_stats_reset",
            endpoints_cleared=endpoint_count,
            slow_requests_cleared=slow_count,
            snapshots_cleared=snapshot_count,
        )

        return {
            "status": "erfolg",
            "geloeschte_endpoints": endpoint_count,
            "geloeschte_langsame_requests": slow_count,
            "geloeschte_snapshots": snapshot_count,
        }

    @property
    def profiling_level(self) -> ProfilingLevel:
        """Aktueller Profiling-Level."""
        return self._profiling_level


# =============================================================================
# SINGLETON ACCESS
# =============================================================================


def get_profiling_service() -> ProfilingService:
    """Gibt Singleton-Instanz des ProfilingService zurueck."""
    return ProfilingService()


# =============================================================================
# CONTEXT MANAGER FUER PROFILING
# =============================================================================


class ProfileBlock:
    """Context Manager fuer das Profiling von Code-Bloecken."""

    def __init__(
        self,
        name: str,
        endpoint: str = "/internal",
        method: str = "INTERNAL",
        track_memory: bool = False,
    ):
        """
        Initialisiert Profile-Block.

        Args:
            name: Name des Blocks (fuer Logging)
            endpoint: Virtueller Endpoint
            method: Virtuelle HTTP-Methode
            track_memory: Memory-Nutzung tracken
        """
        self.name = name
        self.endpoint = endpoint
        self.method = method
        self.track_memory = track_memory
        self.start_time: Optional[float] = None
        self.memory_before: Optional[float] = None
        self.duration_ms: Optional[float] = None

    def __enter__(self) -> "ProfileBlock":
        """Start des Profiling-Blocks."""
        self.start_time = time.perf_counter()

        if self.track_memory:
            try:
                import psutil

                self.memory_before = psutil.Process().memory_info().rss / (1024 * 1024)
            except Exception as e:
                logger.debug("memory_before_capture_failed", error_type=type(e).__name__)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Ende des Profiling-Blocks."""
        self.duration_ms = (time.perf_counter() - self.start_time) * 1000

        memory_after = None
        if self.track_memory:
            try:
                import psutil

                memory_after = psutil.Process().memory_info().rss / (1024 * 1024)
            except Exception as e:
                logger.debug("memory_after_capture_failed", error_type=type(e).__name__)

        service = get_profiling_service()
        service.record_request(
            endpoint=self.endpoint,
            method=self.method,
            duration_ms=self.duration_ms,
            status_code=500 if exc_type else 200,
            memory_before_mb=self.memory_before,
            memory_after_mb=memory_after,
        )

        if exc_type:
            logger.error(
                "profile_block_failed",
                block_name=self.name,
                duration_ms=round(self.duration_ms, 2),
                error_type=exc_type.__name__,
            )
        else:
            logger.debug(
                "profile_block_completed",
                block_name=self.name,
                duration_ms=round(self.duration_ms, 2),
            )
