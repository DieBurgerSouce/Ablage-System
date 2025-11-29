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
        Calculate optimal batch size based on available VRAM

        Heuristics per backend (MB per document):
        - DeepSeek: ~1GB per document (complex multimodal processing)
        - GOT-OCR: ~500MB per document (efficient transformer)
        - Surya GPU: ~250MB per document (optimized detection)
        - Donut: ~400MB per document (vision encoder-decoder)
        - Hybrid: ~1GB per document (multiple backends)
        - Surya: No GPU limit (CPU-only)
        """
        status = self.check_availability()

        if not status["available"] or backend == "surya":
            return 4  # CPU batch size

        free_gb = status.get("free_gb", 0)
        safe_free_gb = max(0, free_gb - 4)  # Keep 4GB buffer

        # MB per document for each backend
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
        return max(1, min(optimal_batch, 32))

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
