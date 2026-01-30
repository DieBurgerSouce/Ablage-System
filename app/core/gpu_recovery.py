"""
GPU OOM Recovery Manager.

Handles automatic recovery from GPU Out-of-Memory errors by:
- Reducing batch sizes dynamically
- Clearing GPU memory
- Tracking optimal batch sizes per backend
- Providing fallback to CPU processing
"""

import gc
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# Try to import torch, gracefully handle if not available
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("torch_not_available", message="GPU recovery features limited")


@dataclass
class GPUBackendConfig:
    """Configuration for GPU backend memory management."""

    default_batch_size: int
    min_batch_size: int = 1
    max_batch_size: int = 32
    vram_gb: float = 0.0  # Estimated VRAM usage
    reduction_factor: float = 0.5  # Reduce by 50% on OOM


# Backend-specific configurations for RTX 4080 (16GB VRAM)
BACKEND_CONFIGS: Dict[str, GPUBackendConfig] = {
    "deepseek": GPUBackendConfig(
        default_batch_size=4,
        min_batch_size=1,
        max_batch_size=8,
        vram_gb=12.0,  # With 4-bit quantization
        reduction_factor=0.5,
    ),
    "got_ocr": GPUBackendConfig(
        default_batch_size=8,
        min_batch_size=1,
        max_batch_size=16,
        vram_gb=10.0,
        reduction_factor=0.5,
    ),
    "surya_gpu": GPUBackendConfig(
        default_batch_size=16,
        min_batch_size=2,
        max_batch_size=32,
        vram_gb=8.0,  # Corrected from 4.0 to 8.0
        reduction_factor=0.5,
    ),
    "donut": GPUBackendConfig(
        default_batch_size=8,
        min_batch_size=1,
        max_batch_size=16,
        vram_gb=8.0,  # Donut vision encoder-decoder
        reduction_factor=0.5,
    ),
    "hybrid": GPUBackendConfig(
        default_batch_size=2,
        min_batch_size=1,
        max_batch_size=4,
        vram_gb=12.0,  # Uses multiple backends
        reduction_factor=0.5,
    ),
}

# Maximum VRAM usage threshold (85% of 16GB)
MAX_VRAM_USAGE_GB = 13.6


@dataclass
class GPUMemoryStats:
    """GPU memory statistics."""

    total_gb: float = 0.0
    allocated_gb: float = 0.0
    cached_gb: float = 0.0
    free_gb: float = 0.0
    utilization_percent: float = 0.0


class GPURecoveryError(Exception):
    """Raised when GPU recovery fails completely."""

    def __init__(self, backend: str, reason: str):
        self.backend = backend
        self.reason = reason
        super().__init__(
            f"GPU-Wiederherstellung fehlgeschlagen für {backend}: {reason}"
        )


class GPURecoveryManager:
    """
    Manager for GPU OOM recovery and batch size optimization.

    Usage:
        manager = GPURecoveryManager()
        results = await manager.execute_with_oom_recovery(
            process_batch, backend="deepseek", batch=documents
        )
    """

    def __init__(self):
        """Initialize GPU recovery manager."""
        self._batch_size_history: Dict[str, List[int]] = {}
        self._optimal_batch_sizes: Dict[str, int] = {
            backend: config.default_batch_size
            for backend, config in BACKEND_CONFIGS.items()
        }
        self._oom_count: Dict[str, int] = {}
        self._last_memory_stats: Optional[GPUMemoryStats] = None

    def get_memory_stats(self) -> GPUMemoryStats:
        """Get current GPU memory statistics."""
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return GPUMemoryStats()

        try:
            total = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            allocated = torch.cuda.memory_allocated(0) / (1024**3)
            cached = torch.cuda.memory_reserved(0) / (1024**3)
            free = total - allocated

            stats = GPUMemoryStats(
                total_gb=round(total, 2),
                allocated_gb=round(allocated, 2),
                cached_gb=round(cached, 2),
                free_gb=round(free, 2),
                utilization_percent=round((allocated / total) * 100, 1),
            )
            self._last_memory_stats = stats
            return stats

        except Exception as e:
            logger.warning("gpu_memory_stats_failed", **safe_error_log(e))
            return GPUMemoryStats()

    async def clear_gpu_memory(self) -> GPUMemoryStats:
        """
        Clear GPU memory cache.

        Returns:
            Memory stats after clearing
        """
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return GPUMemoryStats()

        before = self.get_memory_stats()

        try:
            # Clear PyTorch cache
            torch.cuda.empty_cache()

            # Force garbage collection
            gc.collect()

            # Synchronize CUDA operations
            torch.cuda.synchronize()

            after = self.get_memory_stats()

            freed = before.allocated_gb - after.allocated_gb

            logger.info(
                "gpu_memory_cleared",
                before_allocated_gb=before.allocated_gb,
                after_allocated_gb=after.allocated_gb,
                freed_gb=round(freed, 2),
            )

            return after

        except Exception as e:
            logger.error("gpu_memory_clear_failed", **safe_error_log(e))
            return self.get_memory_stats()

    def get_optimal_batch_size(self, backend: str) -> int:
        """
        Get optimal batch size for backend.

        Args:
            backend: OCR backend name

        Returns:
            Optimal batch size
        """
        if backend in self._optimal_batch_sizes:
            return self._optimal_batch_sizes[backend]

        config = BACKEND_CONFIGS.get(backend)
        if config:
            return config.default_batch_size

        return 4  # Default fallback

    def _reduce_batch_size(
        self,
        backend: str,
        current_size: int,
    ) -> int:
        """
        Reduce batch size after OOM.

        Args:
            backend: OCR backend name
            current_size: Current batch size that caused OOM

        Returns:
            Reduced batch size
        """
        config = BACKEND_CONFIGS.get(backend, GPUBackendConfig(default_batch_size=4))

        # Calculate new size
        new_size = max(
            config.min_batch_size,
            int(current_size * config.reduction_factor),
        )

        # Track history
        if backend not in self._batch_size_history:
            self._batch_size_history[backend] = []
        self._batch_size_history[backend].append(current_size)

        # Update optimal size
        self._optimal_batch_sizes[backend] = new_size

        logger.info(
            "batch_size_reduced",
            backend=backend,
            old_size=current_size,
            new_size=new_size,
            min_size=config.min_batch_size,
        )

        return new_size

    def _is_oom_error(self, exception: Exception) -> bool:
        """Check if exception is a GPU OOM error."""
        if not TORCH_AVAILABLE:
            return False

        # Check for CUDA OOM
        if isinstance(exception, torch.cuda.OutOfMemoryError):
            return True

        # Check error message for OOM indicators
        error_msg = str(exception).lower()
        oom_indicators = [
            "out of memory",
            "cuda out of memory",
            "oom",
            "memory allocation",
            "cannot allocate",
        ]

        return any(indicator in error_msg for indicator in oom_indicators)

    async def execute_with_oom_recovery(
        self,
        func: Callable[..., T],
        backend: str,
        batch: List[Any],
        max_retries: int = 3,
        **kwargs: Any,
    ) -> List[T]:
        """
        Execute batch processing with OOM recovery.

        Args:
            func: Async function to process batch
            backend: OCR backend name
            batch: Items to process
            max_retries: Maximum OOM recovery attempts
            **kwargs: Additional function arguments

        Returns:
            List of results

        Raises:
            GPURecoveryError: If recovery fails after max retries
        """
        if not batch:
            return []

        current_batch_size = self.get_optimal_batch_size(backend)
        remaining = list(batch)
        results: List[T] = []
        oom_count = 0

        while remaining and oom_count < max_retries:
            # Take a batch of items
            current_batch = remaining[:current_batch_size]

            try:
                # Check memory before processing
                stats = self.get_memory_stats()
                if stats.utilization_percent > 85:
                    logger.warning(
                        "high_gpu_memory_before_processing",
                        utilization=stats.utilization_percent,
                    )
                    await self.clear_gpu_memory()

                # Execute processing
                batch_results = await func(current_batch, **kwargs)

                # Success - add results and remove processed items
                if isinstance(batch_results, list):
                    results.extend(batch_results)
                else:
                    results.append(batch_results)

                remaining = remaining[current_batch_size:]

                # Potentially increase batch size if stable
                if oom_count == 0 and len(remaining) > current_batch_size:
                    config = BACKEND_CONFIGS.get(
                        backend, GPUBackendConfig(default_batch_size=4)
                    )
                    if current_batch_size < config.max_batch_size:
                        current_batch_size = min(
                            current_batch_size + 1,
                            config.max_batch_size,
                        )

            except Exception as e:
                if self._is_oom_error(e):
                    oom_count += 1
                    self._oom_count[backend] = self._oom_count.get(backend, 0) + 1

                    logger.warning(
                        "gpu_oom_detected",
                        backend=backend,
                        batch_size=current_batch_size,
                        oom_count=oom_count,
                        max_retries=max_retries,
                    )

                    # SECURITY FIX: Bei wiederholten OOM-Fehlern Incident melden
                    # Könnte auf Resource-Exhaustion-Angriff hindeuten
                    if oom_count >= 2 or self._oom_count[backend] >= 5:
                        await self._report_oom_incident(
                            backend=backend,
                            oom_count=self._oom_count[backend],
                            batch_size=current_batch_size,
                        )

                    # Clear memory
                    await self.clear_gpu_memory()

                    # Reduce batch size
                    current_batch_size = self._reduce_batch_size(
                        backend, current_batch_size
                    )

                    if current_batch_size < 1:
                        raise GPURecoveryError(
                            backend=backend,
                            reason="Batch-Größe kann nicht weiter reduziert werden",
                        )

                else:
                    # Non-OOM error, re-raise
                    raise

        if remaining:
            logger.error(
                "gpu_recovery_failed",
                backend=backend,
                items_remaining=len(remaining),
                oom_count=oom_count,
            )
            raise GPURecoveryError(
                backend=backend,
                reason=f"Nach {max_retries} OOM-Wiederherstellungsversuchen noch {len(remaining)} Elemente übrig",
            )

        logger.info(
            "batch_processing_complete",
            backend=backend,
            total_items=len(batch),
            results_count=len(results),
            final_batch_size=current_batch_size,
            oom_recoveries=oom_count,
        )

        return results

    async def _report_oom_incident(
        self,
        backend: str,
        oom_count: int,
        batch_size: int,
    ) -> None:
        """
        Report repeated OOM errors as security incident.

        Repeated GPU OOM could indicate:
        - Resource exhaustion attack
        - Malicious oversized documents
        - System configuration issues

        Args:
            backend: OCR backend with OOM
            oom_count: Total OOM count for this backend
            batch_size: Batch size at time of OOM
        """
        try:
            from app.services.incident_response_service import (

                get_incident_response_service,
                Incident,
                IncidentType,
                IncidentSeverity,
            )

            # Determine severity based on OOM frequency
            if oom_count >= 10:
                severity = IncidentSeverity.HIGH
            elif oom_count >= 5:
                severity = IncidentSeverity.MEDIUM
            else:
                severity = IncidentSeverity.LOW

            # Create incident
            incident = Incident(
                incident_type=IncidentType.RATE_LIMIT_ABUSE,  # Closest type for resource abuse
                severity=severity,
                description=f"GPU Resource Exhaustion: {oom_count} OOM-Fehler bei {backend}-Backend",
                details={
                    "backend": backend,
                    "oom_count": oom_count,
                    "batch_size": batch_size,
                    "memory_stats": (
                        {
                            "allocated_gb": self._last_memory_stats.allocated_gb,
                            "utilization": self._last_memory_stats.utilization_percent,
                        }
                        if self._last_memory_stats
                        else None
                    ),
                    "incident_category": "gpu_resource_exhaustion",
                },
            )

            service = get_incident_response_service()
            service.active_incidents[incident.id] = incident

            logger.warning(
                "gpu_oom_incident_reported",
                incident_id=incident.id,
                backend=backend,
                oom_count=oom_count,
                severity=severity.value,
                security_event=True,
            )

        except ImportError:
            # IncidentResponseService not available
            logger.debug("incident_response_service_not_available")
        except Exception as e:
            # Don't let incident reporting break recovery
            logger.warning("oom_incident_report_failed", **safe_error_log(e))

    def get_stats(self) -> Dict[str, Any]:
        """Get recovery statistics."""
        return {
            "optimal_batch_sizes": self._optimal_batch_sizes.copy(),
            "oom_counts": self._oom_count.copy(),
            "batch_size_history": {
                k: v[-10:]  # Last 10 changes
                for k, v in self._batch_size_history.items()
            },
            "last_memory_stats": (
                {
                    "total_gb": self._last_memory_stats.total_gb,
                    "allocated_gb": self._last_memory_stats.allocated_gb,
                    "utilization_percent": self._last_memory_stats.utilization_percent,
                }
                if self._last_memory_stats
                else None
            ),
        }


@asynccontextmanager
async def gpu_memory_guard(threshold_gb: float = MAX_VRAM_USAGE_GB):
    """
    Context manager for GPU memory monitoring.

    Clears memory if threshold exceeded after processing.

    Usage:
        async with gpu_memory_guard():
            result = await process_with_gpu(data)
    """
    manager = GPURecoveryManager()
    before = manager.get_memory_stats()

    try:
        yield manager
    finally:
        after = manager.get_memory_stats()

        if after.allocated_gb > threshold_gb:
            logger.warning(
                "gpu_memory_threshold_exceeded",
                threshold_gb=threshold_gb,
                allocated_gb=after.allocated_gb,
            )
            await manager.clear_gpu_memory()


# Global instance
_global_manager: Optional[GPURecoveryManager] = None


def get_gpu_recovery_manager() -> GPURecoveryManager:
    """Get global GPU recovery manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = GPURecoveryManager()
    return _global_manager
