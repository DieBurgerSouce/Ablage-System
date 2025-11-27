"""
System Monitoring and Metrics for Ablage-System OCR
Tracks GPU, memory, processing time, and errors
Created: 2024-11-22
"""

import time
import psutil
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from collections import defaultdict, deque
import structlog

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

logger = structlog.get_logger(__name__)


class MetricsCollector:
    """Collect and aggregate system metrics"""

    def __init__(self, max_history: int = 1000):
        """
        Args:
            max_history: Maximum number of historical data points to keep
        """
        self.max_history = max_history

        # Metrics storage
        self.request_times: deque = deque(maxlen=max_history)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.backend_usage: Dict[str, int] = defaultdict(int)
        self.gpu_memory_history: deque = deque(maxlen=max_history)
        self.document_count = 0
        self.successful_ocr = 0
        self.failed_ocr = 0

        # Start time
        self.start_time = datetime.now()

    def record_request(self, duration_ms: float, backend: str, success: bool) -> None:
        """Record OCR request metrics"""
        self.request_times.append({
            "timestamp": datetime.now(),
            "duration_ms": duration_ms,
            "backend": backend,
            "success": success
        })

        self.backend_usage[backend] += 1
        self.document_count += 1

        if success:
            self.successful_ocr += 1
        else:
            self.failed_ocr += 1

    def record_error(self, error_code: str) -> None:
        """Record error occurrence"""
        self.error_counts[error_code] += 1

    def record_gpu_memory(self, used_gb: float, total_gb: float) -> None:
        """Record GPU memory snapshot"""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            self.gpu_memory_history.append({
                "timestamp": datetime.now(),
                "used_gb": used_gb,
                "total_gb": total_gb,
                "utilization_percent": (used_gb / total_gb) * 100
            })

    def get_summary(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        uptime = datetime.now() - self.start_time

        # Calculate statistics
        avg_processing_time = 0
        if self.request_times:
            avg_processing_time = sum(r["duration_ms"] for r in self.request_times) / len(self.request_times)

        success_rate = 0
        if self.document_count > 0:
            success_rate = (self.successful_ocr / self.document_count) * 100

        return {
            "uptime_seconds": uptime.total_seconds(),
            "uptime_formatted": str(uptime),
            "total_documents": self.document_count,
            "successful_ocr": self.successful_ocr,
            "failed_ocr": self.failed_ocr,
            "success_rate_percent": round(success_rate, 2),
            "avg_processing_time_ms": round(avg_processing_time, 2),
            "backend_usage": dict(self.backend_usage),
            "error_counts": dict(self.error_counts),
            "requests_per_minute": self._calculate_rpm()
        }

    def _calculate_rpm(self) -> float:
        """Calculate requests per minute (last 5 minutes)"""
        if not self.request_times:
            return 0.0

        five_min_ago = datetime.now() - timedelta(minutes=5)
        recent_requests = [r for r in self.request_times if r["timestamp"] > five_min_ago]

        if not recent_requests:
            return 0.0

        time_span = (datetime.now() - recent_requests[0]["timestamp"]).total_seconds() / 60
        return len(recent_requests) / max(time_span, 0.1)  # Avoid division by zero


class SystemMonitor:
    """Monitor system resources (CPU, RAM, GPU)"""

    def __init__(self):
        self.metrics = MetricsCollector()

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        status = {
            "cpu": {
                "percent": cpu_percent,
                "cores": psutil.cpu_count(),
                "freq_mhz": psutil.cpu_freq().current if psutil.cpu_freq() else None
            },
            "memory": {
                "total_gb": memory.total / (1024**3),
                "available_gb": memory.available / (1024**3),
                "used_gb": memory.used / (1024**3),
                "percent": memory.percent
            },
            "disk": {
                "total_gb": disk.total / (1024**3),
                "used_gb": disk.used / (1024**3),
                "free_gb": disk.free / (1024**3),
                "percent": disk.percent
            },
            "timestamp": datetime.now().isoformat()
        }

        # Add GPU info if available
        if TORCH_AVAILABLE and torch.cuda.is_available():
            gpu_status = self._get_gpu_status()
            status["gpu"] = gpu_status
            self.metrics.record_gpu_memory(
                gpu_status["memory_used_gb"],
                gpu_status["memory_total_gb"]
            )

        return status

    def _get_gpu_status(self) -> Dict[str, Any]:
        """Get detailed GPU status"""
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return {"available": False}

        memory_allocated = torch.cuda.memory_allocated(0)
        memory_reserved = torch.cuda.memory_reserved(0)
        memory_total = torch.cuda.get_device_properties(0).total_memory

        return {
            "available": True,
            "device_name": torch.cuda.get_device_name(0),
            "memory_allocated_gb": memory_allocated / (1024**3),
            "memory_reserved_gb": memory_reserved / (1024**3),
            "memory_total_gb": memory_total / (1024**3),
            "memory_used_gb": memory_allocated / (1024**3),
            "memory_free_gb": (memory_total - memory_allocated) / (1024**3),
            "utilization_percent": (memory_allocated / memory_total) * 100
        }

    def check_health(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        health_checks = {
            "system_resources": self._check_system_resources(),
            "gpu": self._check_gpu(),
            "timestamp": datetime.now().isoformat()
        }

        all_healthy = all(
            check.get("healthy", False)
            for check in health_checks.values()
            if isinstance(check, dict)
        )

        health_checks["overall_status"] = "healthy" if all_healthy else "unhealthy"
        return health_checks

    def _check_system_resources(self) -> Dict[str, Any]:
        """Check if system resources are adequate"""
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        warnings = []

        if memory.percent > 90:
            warnings.append("RAM usage >90%")

        if disk.percent > 90:
            warnings.append("Disk usage >90%")

        if psutil.cpu_percent(interval=1) > 95:
            warnings.append("CPU usage >95%")

        return {
            "healthy": len(warnings) == 0,
            "warnings": warnings,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent
        }

    def _check_gpu(self) -> Dict[str, Any]:
        """Check GPU health"""
        if not TORCH_AVAILABLE:
            return {
                "healthy": False,
                "reason": "PyTorch not installed",
                "warnings": ["GPU acceleration not available"]
            }

        if not torch.cuda.is_available():
            return {
                "healthy": False,
                "reason": "CUDA not available",
                "warnings": ["GPU not detected"]
            }

        gpu_status = self._get_gpu_status()
        warnings = []

        # Check VRAM usage
        if gpu_status["utilization_percent"] > 85:
            warnings.append(f"GPU VRAM usage high: {gpu_status['utilization_percent']:.1f}%")

        if gpu_status["memory_free_gb"] < 4:
            warnings.append(f"Low free VRAM: {gpu_status['memory_free_gb']:.1f}GB")

        return {
            "healthy": len(warnings) == 0,
            "warnings": warnings,
            "vram_utilization": gpu_status["utilization_percent"],
            "vram_free_gb": gpu_status["memory_free_gb"]
        }


class PerformanceTimer:
    """Context manager for timing operations"""

    def __init__(self, name: str, metrics: Optional[MetricsCollector] = None):
        self.name = name
        self.metrics = metrics
        self.start_time = None
        self.duration_ms = None

    def __enter__(self):
        self.start_time = time.time()
        logger.debug("timer_started", timer_name=self.name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        self.duration_ms = (end_time - self.start_time) * 1000

        if exc_type is None:
            logger.info("timer_completed", timer_name=self.name, duration_ms=round(self.duration_ms, 2))
        else:
            logger.error("timer_failed", timer_name=self.name, duration_ms=round(self.duration_ms, 2), error=str(exc_val))

        return False  # Don't suppress exceptions


# Global singleton instances
_system_monitor = None


def get_system_monitor() -> SystemMonitor:
    """Get global SystemMonitor instance"""
    global _system_monitor
    if _system_monitor is None:
        _system_monitor = SystemMonitor()
    return _system_monitor
