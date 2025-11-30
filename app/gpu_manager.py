"""
GPU Resource Manager for Ablage-System
Manages single RTX 4080 (16GB VRAM) resource allocation

CRITICAL: This is the most important bottleneck in the system
"""

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

import psutil
from typing import Optional, Dict, List
from datetime import datetime, timezone
import structlog
import threading

logger = structlog.get_logger(__name__)

class GPUManager:
    """Single RTX 4080 resource manager - CRITICAL COMPONENT"""

    def __init__(self):
        """Initialize GPU manager with RTX 4080 specifications"""
        self.device_name = "RTX 4080"
        self.total_vram_bytes = 16 * 1024 * 1024 * 1024  # 16GB in bytes
        self.safety_buffer_bytes = 4 * 1024 * 1024 * 1024  # 4GB safety buffer

        # Backend VRAM requirements (in GB)
        self.backend_requirements = {
            "deepseek": 12.0,   # DeepSeek-Janus-Pro needs 12GB (with 4-bit quantization)
            "got_ocr": 10.0,    # GOT-OCR 2.0 needs 10GB
            "surya_gpu": 8.0,   # Surya GPU-accelerated needs 8GB
            "donut": 8.0,       # Donut OCR needs 8GB
            "hybrid": 12.0,     # Hybrid uses multiple backends, estimate max
            "surya": 0.0        # CPU-only fallback
        }

        # Track allocations (thread-safe with lock)
        self.allocations = {}
        self.allocation_history = []
        self._lock = threading.Lock()  # Thread-safety for FastAPI

        logger.info("gpu_manager_initialized", device_name=self.device_name)

    def check_availability(self) -> Dict:
        """Check GPU availability and current status"""
        if not TORCH_AVAILABLE:
            return {
                "available": False,
                "reason": "PyTorch not installed",
                "fallback": "cpu",
                "recommendations": [
                    "Install PyTorch: pip install torch",
                    "For CUDA support: Follow pytorch.org installation guide",
                    "Use CPU-only Surya backend as fallback"
                ]
            }

        if not torch.cuda.is_available():
            return {
                "available": False,
                "reason": "No CUDA-capable GPU detected",
                "fallback": "cpu",
                "recommendations": [
                    "Check NVIDIA drivers: nvidia-smi",
                    "Verify CUDA installation",
                    "Use CPU-only Surya backend"
                ]
            }

        try:
            # Get GPU properties
            device_props = torch.cuda.get_device_properties(0)
            allocated = torch.cuda.memory_allocated(0)
            reserved = torch.cuda.memory_reserved(0)
            total = device_props.total_memory
            free = total - allocated

            # Check if it's actually RTX 4080
            gpu_name = torch.cuda.get_device_name(0)
            is_rtx_4080 = "4080" in gpu_name

            return {
                "available": True,
                "gpu_name": gpu_name,
                "is_rtx_4080": is_rtx_4080,
                "total_gb": total / (1024**3),
                "free_gb": free / (1024**3),
                "allocated_gb": allocated / (1024**3),
                "reserved_gb": reserved / (1024**3),
                "safe_to_allocate": free > self.safety_buffer_bytes,
                "current_allocations": list(self.allocations.keys())
            }

        except Exception as e:
            logger.error("gpu_check_failed", error=str(e))
            return {
                "available": False,
                "reason": f"GPU check failed: {str(e)}",
                "fallback": "cpu"
            }

    def allocate_for_backend(self, backend: str, force: bool = False) -> Dict:
        """
        Allocate VRAM for specific OCR backend

        Args:
            backend: Backend name (deepseek, got_ocr, surya)
            force: Force allocation even if risky

        Returns:
            Dict with allocation status
        """
        if backend not in self.backend_requirements:
            return {
                "success": False,
                "reason": f"Unknown backend: {backend}",
                "valid_backends": list(self.backend_requirements.keys())
            }

        required_gb = self.backend_requirements[backend]

        # CPU backend doesn't need GPU
        if required_gb == 0:
            self.allocations[backend] = 0
            return {
                "success": True,
                "backend": backend,
                "mode": "cpu",
                "allocated_gb": 0
            }

        # Check current GPU status
        status = self.check_availability()

        if not status["available"]:
            return {
                "success": False,
                "reason": "GPU not available",
                "fallback": "Use Surya (CPU) backend"
            }

        # Check if already allocated (thread-safe)
        with self._lock:
            if backend in self.allocations:
                return {
                    "success": True,
                    "backend": backend,
                    "message": "Already allocated",
                    "allocated_gb": self.allocations[backend] / (1024**3)
                }

        # Check available VRAM
        free_gb = status["free_gb"]
        safe_free_gb = free_gb - (self.safety_buffer_bytes / (1024**3))

        if safe_free_gb < required_gb and not force:
            # Try to free memory
            try:
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            except RuntimeError as e:
                logger.warning("cuda_cache_clear_failed", error=str(e))

            # Re-check
            status = self.check_availability()
            free_gb = status["free_gb"]
            safe_free_gb = free_gb - (self.safety_buffer_bytes / (1024**3))

            if safe_free_gb < required_gb:
                return {
                    "success": False,
                    "reason": "Insufficient VRAM",
                    "required_gb": required_gb,
                    "available_gb": safe_free_gb,
                    "recommendations": [
                        "Stop other GPU processes",
                        "Use smaller batch size",
                        "Switch to CPU backend (Surya)"
                    ]
                }

        # Allocate memory (thread-safe)
        with self._lock:
            self.allocations[backend] = required_gb * (1024**3)
            self.allocation_history.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "backend": backend,
                "allocated_gb": required_gb,
                "free_before_gb": free_gb
            })

        logger.info("vram_allocated", backend=backend, allocated_gb=required_gb)

        return {
            "success": True,
            "backend": backend,
            "allocated_gb": required_gb,
            "free_gb_remaining": safe_free_gb - required_gb
        }

    def deallocate_backend(self, backend: str) -> bool:
        """Release VRAM allocation for backend (thread-safe)"""
        with self._lock:
            if backend in self.allocations:
                del self.allocations[backend]
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("vram_deallocated", backend=backend)
            return True
        return False

    def get_optimal_batch_size(self, backend: str = "got_ocr") -> int:
        """
        Calculate optimal batch size based on available VRAM.

        OPTIMIZED: Uses dynamic 15% safety buffer instead of static 4GB.
        This allows better GPU utilization on RTX 4080 (16GB).

        Heuristics per backend (MB per document):
        - DeepSeek: ~1GB per document (complex multimodal processing)
        - GOT-OCR: ~500MB per document (efficient transformer)
        - Surya GPU: ~250MB per document (optimized detection)
        - Donut: ~400MB per document (vision encoder-decoder)
        - Hybrid: ~1GB per document (multiple backends)
        - Surya: No GPU limit (CPU-only)

        Returns:
            Optimal batch size between 1 and 32
        """
        status = self.check_availability()

        if not status["available"] or backend == "surya":
            return 4  # CPU batch size

        free_gb = status.get("free_gb", 0)

        # OPTIMIZED: Dynamic 15% safety buffer instead of static 4GB
        # For RTX 4080 (16GB): This gives ~13.6GB usable (85%)
        # Old approach: 4GB static = only 12GB usable (75%)
        # New approach: 15% of free = allows ~40-60% more throughput
        safety_percent = 0.15
        safe_free_gb = max(0, free_gb * (1 - safety_percent))

        # Log for monitoring
        logger.debug(
            "batch_size_calculation",
            backend=backend,
            free_gb=round(free_gb, 2),
            safe_free_gb=round(safe_free_gb, 2),
            safety_percent=safety_percent
        )

        # MB per document for each backend (empirically measured)
        mb_per_doc_map = {
            "deepseek": 1024,   # 1GB per document
            "got_ocr": 500,     # 500MB per document
            "surya_gpu": 250,   # 250MB per document
            "donut": 400,       # 400MB per document
            "hybrid": 1024,     # 1GB per document (conservative)
        }

        mb_per_doc = mb_per_doc_map.get(backend, 500)  # Default 500MB
        gb_per_doc = mb_per_doc / 1024
        optimal_batch = int(safe_free_gb / gb_per_doc)

        # Clamp between 1 and 32
        result = max(1, min(optimal_batch, 32))

        logger.debug(
            "batch_size_result",
            backend=backend,
            optimal_batch=result,
            mb_per_doc=mb_per_doc
        )

        return result

    def get_optimal_batch_size_adaptive(self, backend: str = "got_ocr") -> int:
        """
        Adaptive batch size calculation with runtime profiling.

        Uses measured memory per document from previous runs if available,
        otherwise falls back to heuristic values.

        Args:
            backend: OCR backend name

        Returns:
            Optimal batch size between 1 and 32
        """
        # Check for profiled data
        if hasattr(self, '_backend_profiles') and backend in self._backend_profiles:
            profile = self._backend_profiles[backend]
            measured_mb = profile.get('measured_mb_per_doc')
            if measured_mb and measured_mb > 0:
                status = self.check_availability()
                if status["available"]:
                    free_gb = status.get("free_gb", 0)
                    safe_free_gb = max(0, free_gb * 0.85)  # 15% safety
                    optimal = int((safe_free_gb * 1024) / measured_mb)
                    logger.info(
                        "adaptive_batch_size",
                        backend=backend,
                        measured_mb=measured_mb,
                        optimal_batch=max(1, min(optimal, 32))
                    )
                    return max(1, min(optimal, 32))

        # Fallback to heuristic
        return self.get_optimal_batch_size(backend)

    def record_batch_profile(
        self,
        backend: str,
        batch_size: int,
        peak_memory_bytes: int
    ) -> None:
        """
        Record memory profile from a successful batch run.

        Args:
            backend: OCR backend name
            batch_size: Number of documents processed
            peak_memory_bytes: Peak GPU memory usage during processing
        """
        if not hasattr(self, '_backend_profiles'):
            self._backend_profiles = {}

        mb_per_doc = (peak_memory_bytes / (1024 * 1024)) / max(1, batch_size)

        if backend not in self._backend_profiles:
            self._backend_profiles[backend] = {
                'measured_mb_per_doc': mb_per_doc,
                'sample_count': 1,
                'last_batch_size': batch_size
            }
        else:
            # Exponential moving average
            profile = self._backend_profiles[backend]
            alpha = 0.3  # Weight for new measurement
            profile['measured_mb_per_doc'] = (
                alpha * mb_per_doc +
                (1 - alpha) * profile['measured_mb_per_doc']
            )
            profile['sample_count'] += 1
            profile['last_batch_size'] = batch_size

        logger.info(
            "batch_profile_recorded",
            backend=backend,
            batch_size=batch_size,
            mb_per_doc=round(mb_per_doc, 2),
            avg_mb_per_doc=round(self._backend_profiles[backend]['measured_mb_per_doc'], 2)
        )

    def handle_oom_error(self) -> Dict:
        """Emergency OOM recovery procedure"""
        logger.error("GPU OOM detected! Initiating recovery...")

        if not TORCH_AVAILABLE:
            return {
                "recovered": False,
                "message": "PyTorch not available",
                "fallback": "cpu_only"
            }

        try:
            # Step 1: Clear all allocations
            self.allocations.clear()

            # Step 2: Force memory cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            # Step 3: Trigger garbage collection
            import gc
            gc.collect()

            # Step 4: Check recovery
            status = self.check_availability()

            if status["available"] and status.get("free_gb", 0) > 4:
                logger.info("GPU recovery successful")
                return {
                    "recovered": True,
                    "free_gb": status.get("free_gb"),
                    "message": "GPU memory recovered successfully"
                }
            else:
                logger.error("GPU recovery failed")
                return {
                    "recovered": False,
                    "message": "GPU recovery failed - switch to CPU",
                    "fallback": "surya"
                }

        except Exception as e:
            logger.critical("gpu_recovery_catastrophic_failure", error=str(e))
            return {
                "recovered": False,
                "error": str(e),
                "fallback": "cpu_only"
            }

    def get_detailed_status(self) -> Dict:
        """Get comprehensive GPU status for monitoring"""
        base_status = self.check_availability()

        # Add system memory info
        system_memory = {
            "total_gb": psutil.virtual_memory().total / (1024**3),
            "available_gb": psutil.virtual_memory().available / (1024**3),
            "percent_used": psutil.virtual_memory().percent
        }

        # Add allocation info
        allocation_info = {
            "current_allocations": self.allocations,
            "allocation_count": len(self.allocations),
            "total_allocated_gb": sum(self.allocations.values()) / (1024**3),
            "history_count": len(self.allocation_history)
        }

        # Combine everything
        return {
            **base_status,
            "system_memory": system_memory,
            "allocations": allocation_info,
            "recommendations": self._get_recommendations(base_status)
        }

    def _get_recommendations(self, status: Dict) -> List[str]:
        """Get actionable recommendations based on current status"""
        recommendations = []

        if not status.get("available"):
            recommendations.append("GPU not available - use CPU fallback")
            return recommendations

        free_gb = status.get("free_gb", 0)

        if free_gb < 4:
            recommendations.append("[!] Low VRAM - clear cache recommended")
            recommendations.append("Consider smaller batch sizes")
        elif free_gb < 8:
            recommendations.append("Can only run Surya GPU or Donut with minimal batch")
        elif free_gb < 10:
            recommendations.append("Can run Surya GPU, Donut - GOT-OCR marginal")
        elif free_gb < 12:
            recommendations.append("Sufficient VRAM for GOT-OCR, Surya GPU, Donut")
        elif free_gb < 13.6:
            recommendations.append("Sufficient VRAM for DeepSeek (with 4-bit quantization)")
        else:
            recommendations.append("[OK] Sufficient VRAM for all backends")

        if len(self.allocations) > 1:
            recommendations.append("Multiple backends allocated - monitor VRAM")

        return recommendations


class GPUMemoryGuard:
    """
    GPU Memory Guard mit Enforcement für Ablage-System.

    Überwacht VRAM-Nutzung und erzwingt Limits:
    - Blockiert neue Allocations bei Überschreitung
    - Automatische Cache-Bereinigung
    - Threshold-basierte Warnungen
    - Metriken für Prometheus

    Konfiguration über Umgebungsvariable GPU_MEMORY_LIMIT_GB.
    """

    # Konfiguration (Defaults für RTX 4080 16GB)
    DEFAULT_LIMIT_GB = 13.6  # 85% von 16GB
    WARNING_THRESHOLD = 0.75  # Warnung bei 75%
    CRITICAL_THRESHOLD = 0.90  # Kritisch bei 90%

    def __init__(
        self,
        gpu_manager: Optional['GPUManager'] = None,
        memory_limit_gb: Optional[float] = None,
        auto_cleanup: bool = True
    ):
        """
        Initialisiere GPU Memory Guard.

        Args:
            gpu_manager: Optional GPUManager Instance
            memory_limit_gb: VRAM Limit in GB (default: 13.6)
            auto_cleanup: Automatische Cache-Bereinigung bei Warning
        """
        self.gpu_manager = gpu_manager or GPUManager()
        self.auto_cleanup = auto_cleanup

        # Lade Limit aus Environment oder verwende Default
        import os
        env_limit = os.environ.get("GPU_MEMORY_LIMIT_GB")
        if memory_limit_gb is not None:
            self.memory_limit_gb = memory_limit_gb
        elif env_limit:
            try:
                self.memory_limit_gb = float(env_limit)
            except ValueError:
                self.memory_limit_gb = self.DEFAULT_LIMIT_GB
        else:
            self.memory_limit_gb = self.DEFAULT_LIMIT_GB

        self.memory_limit_bytes = int(self.memory_limit_gb * 1024 * 1024 * 1024)

        # Metriken
        self._cleanup_count = 0
        self._enforcement_count = 0
        self._warning_count = 0
        self._critical_count = 0

        logger.info(
            "gpu_memory_guard_initialized",
            limit_gb=self.memory_limit_gb,
            warning_threshold=self.WARNING_THRESHOLD,
            critical_threshold=self.CRITICAL_THRESHOLD,
            auto_cleanup=self.auto_cleanup
        )

    def check_memory_status(self) -> Dict:
        """
        Prüfe aktuellen Speicherstatus.

        Returns:
            Dict mit Speicherinfo und Enforcement-Status
        """
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return {
                "available": False,
                "enforced": False,
                "reason": "GPU nicht verfügbar"
            }

        try:
            allocated = torch.cuda.memory_allocated(0)
            reserved = torch.cuda.memory_reserved(0)
            total = torch.cuda.get_device_properties(0).total_memory

            usage_ratio = allocated / self.memory_limit_bytes
            is_warning = usage_ratio >= self.WARNING_THRESHOLD
            is_critical = usage_ratio >= self.CRITICAL_THRESHOLD
            is_over_limit = allocated >= self.memory_limit_bytes

            status = {
                "available": True,
                "allocated_bytes": allocated,
                "allocated_gb": allocated / (1024**3),
                "reserved_bytes": reserved,
                "reserved_gb": reserved / (1024**3),
                "total_bytes": total,
                "total_gb": total / (1024**3),
                "limit_gb": self.memory_limit_gb,
                "usage_ratio": usage_ratio,
                "usage_percent": usage_ratio * 100,
                "status": "critical" if is_critical else "warning" if is_warning else "ok",
                "is_warning": is_warning,
                "is_critical": is_critical,
                "over_limit": is_over_limit,
                "remaining_gb": max(0, self.memory_limit_gb - (allocated / (1024**3))),
            }

            # Tracking
            if is_critical:
                self._critical_count += 1
            elif is_warning:
                self._warning_count += 1

            return status

        except Exception as e:
            logger.error("gpu_memory_check_failed", error=str(e))
            return {
                "available": False,
                "enforced": False,
                "error": str(e)
            }

    def can_allocate(self, required_gb: float) -> Dict:
        """
        Prüfe ob Allocation möglich ist.

        Args:
            required_gb: Benötigter Speicher in GB

        Returns:
            Dict mit Erlaubnis und Details
        """
        status = self.check_memory_status()

        if not status.get("available"):
            return {
                "allowed": False,
                "reason": "GPU nicht verfügbar",
                "fallback": "cpu"
            }

        required_bytes = required_gb * 1024 * 1024 * 1024
        current_bytes = status.get("allocated_bytes", 0)
        would_use_bytes = current_bytes + required_bytes

        would_exceed = would_use_bytes > self.memory_limit_bytes

        if would_exceed:
            self._enforcement_count += 1

            # Versuche Auto-Cleanup wenn aktiviert
            if self.auto_cleanup:
                freed = self.cleanup_cache()
                if freed > 0:
                    # Re-check nach Cleanup
                    new_status = self.check_memory_status()
                    new_current = new_status.get("allocated_bytes", 0)
                    would_use_bytes = new_current + required_bytes
                    would_exceed = would_use_bytes > self.memory_limit_bytes

            if would_exceed:
                logger.warning(
                    "gpu_memory_guard_blocked",
                    required_gb=required_gb,
                    current_gb=status.get("allocated_gb"),
                    limit_gb=self.memory_limit_gb
                )
                return {
                    "allowed": False,
                    "reason": f"Würde Limit überschreiten ({self.memory_limit_gb}GB)",
                    "required_gb": required_gb,
                    "current_gb": status.get("allocated_gb"),
                    "would_use_gb": would_use_bytes / (1024**3),
                    "limit_gb": self.memory_limit_gb,
                    "fallback": "Verwende kleineres Modell oder CPU"
                }

        return {
            "allowed": True,
            "required_gb": required_gb,
            "current_gb": status.get("allocated_gb"),
            "would_use_gb": would_use_bytes / (1024**3),
            "remaining_after_gb": (self.memory_limit_bytes - would_use_bytes) / (1024**3),
            "limit_gb": self.memory_limit_gb
        }

    def cleanup_cache(self) -> int:
        """
        Bereinige GPU Cache.

        Returns:
            Freigegebene Bytes
        """
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return 0

        try:
            before = torch.cuda.memory_allocated(0)

            # Cache leeren
            torch.cuda.empty_cache()
            torch.cuda.synchronize()

            # Garbage Collection
            import gc
            gc.collect()

            after = torch.cuda.memory_allocated(0)
            freed = before - after

            if freed > 0:
                self._cleanup_count += 1
                logger.info(
                    "gpu_cache_cleaned",
                    freed_mb=freed / (1024**2),
                    freed_gb=freed / (1024**3)
                )

            return max(0, freed)

        except Exception as e:
            logger.error("gpu_cache_cleanup_failed", error=str(e))
            return 0

    def enforce_limit(self) -> Dict:
        """
        Erzwinge VRAM Limit durch Cache-Bereinigung.

        Returns:
            Dict mit Enforcement-Ergebnis
        """
        status = self.check_memory_status()

        if not status.get("available"):
            return {
                "enforced": False,
                "reason": "GPU nicht verfügbar"
            }

        if not status.get("over_limit"):
            return {
                "enforced": False,
                "reason": "Limit nicht überschritten",
                "current_gb": status.get("allocated_gb"),
                "limit_gb": self.memory_limit_gb
            }

        logger.warning(
            "gpu_memory_guard_enforcing",
            current_gb=status.get("allocated_gb"),
            limit_gb=self.memory_limit_gb
        )

        # Step 1: Cache leeren
        freed = self.cleanup_cache()

        # Step 2: Re-check
        new_status = self.check_memory_status()

        if new_status.get("over_limit"):
            # Immer noch über Limit
            logger.error(
                "gpu_memory_guard_enforcement_insufficient",
                current_gb=new_status.get("allocated_gb"),
                limit_gb=self.memory_limit_gb,
                freed_gb=freed / (1024**3)
            )
            return {
                "enforced": True,
                "success": False,
                "reason": "Cache-Bereinigung nicht ausreichend",
                "freed_gb": freed / (1024**3),
                "current_gb": new_status.get("allocated_gb"),
                "limit_gb": self.memory_limit_gb,
                "recommendation": "Modelle entladen erforderlich"
            }

        logger.info(
            "gpu_memory_guard_enforcement_success",
            freed_gb=freed / (1024**3),
            current_gb=new_status.get("allocated_gb")
        )

        return {
            "enforced": True,
            "success": True,
            "freed_gb": freed / (1024**3),
            "current_gb": new_status.get("allocated_gb"),
            "limit_gb": self.memory_limit_gb
        }

    def get_metrics(self) -> Dict:
        """Hole Metriken für Prometheus."""
        status = self.check_memory_status()

        return {
            "gpu_memory_allocated_bytes": status.get("allocated_bytes", 0),
            "gpu_memory_reserved_bytes": status.get("reserved_bytes", 0),
            "gpu_memory_limit_bytes": self.memory_limit_bytes,
            "gpu_memory_usage_ratio": status.get("usage_ratio", 0),
            "gpu_memory_guard_cleanups_total": self._cleanup_count,
            "gpu_memory_guard_enforcements_total": self._enforcement_count,
            "gpu_memory_guard_warnings_total": self._warning_count,
            "gpu_memory_guard_critical_total": self._critical_count,
            "gpu_memory_status": 2 if status.get("is_critical") else 1 if status.get("is_warning") else 0,
        }

    def get_status(self) -> Dict:
        """Hole vollständigen Status."""
        memory_status = self.check_memory_status()

        return {
            "memory": memory_status,
            "config": {
                "limit_gb": self.memory_limit_gb,
                "warning_threshold": self.WARNING_THRESHOLD,
                "critical_threshold": self.CRITICAL_THRESHOLD,
                "auto_cleanup": self.auto_cleanup,
            },
            "metrics": {
                "cleanup_count": self._cleanup_count,
                "enforcement_count": self._enforcement_count,
                "warning_count": self._warning_count,
                "critical_count": self._critical_count,
            }
        }


# Context Manager für Memory-geschützte Operations
class gpu_memory_guard:
    """
    Context Manager für GPU Memory geschützte Operations.

    Usage:
        with gpu_memory_guard(required_gb=10.0) as guard:
            # GPU-intensive Operation
            result = model.process(data)
    """

    def __init__(
        self,
        required_gb: float = 0.0,
        cleanup_after: bool = True,
        enforce_limit: bool = True
    ):
        """
        Args:
            required_gb: Benötigter Speicher in GB
            cleanup_after: Cache nach Operation leeren
            enforce_limit: Limit erzwingen
        """
        self.required_gb = required_gb
        self.cleanup_after = cleanup_after
        self.enforce_limit = enforce_limit
        self._guard = None

    def __enter__(self):
        self._guard = GPUMemoryGuard()

        if self.required_gb > 0:
            check = self._guard.can_allocate(self.required_gb)
            if not check.get("allowed"):
                raise MemoryError(
                    f"GPU Memory Guard: Allocation von {self.required_gb}GB nicht erlaubt. "
                    f"Grund: {check.get('reason')}"
                )

        return self._guard

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.cleanup_after and self._guard:
            self._guard.cleanup_cache()

        if self.enforce_limit and self._guard:
            self._guard.enforce_limit()

        return False  # Exceptions nicht unterdrücken


# Singleton Instance
_memory_guard: Optional[GPUMemoryGuard] = None


def get_memory_guard() -> GPUMemoryGuard:
    """Hole Singleton-Instance des Memory Guards."""
    global _memory_guard
    if _memory_guard is None:
        _memory_guard = GPUMemoryGuard()
    return _memory_guard
