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
from typing import Optional, Dict, List, Any, Callable, TypeVar
from datetime import datetime, timezone
import structlog
import threading
import asyncio
from functools import wraps
from contextlib import contextmanager
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Type variable for generic decorator
T = TypeVar('T')

class GPUManager:
    """Single RTX 4080 resource manager - CRITICAL COMPONENT"""

    def __init__(self):
        """Initialize GPU manager with RTX 4080 specifications"""
        self.device_name = "RTX 4080"
        self.total_vram_bytes = 16 * 1024 * 1024 * 1024  # 16GB in bytes
        self.safety_buffer_bytes = 2 * 1024 * 1024 * 1024  # 2GB safety buffer (reduced from 4GB for RTX 4080)

        # Backend VRAM requirements (in GB)
        self.backend_requirements = {
            "deepseek": 12.0,   # DeepSeek-Janus-Pro needs 12GB (with 4-bit quantization)
            "got_ocr": 10.0,    # GOT-OCR 2.0 needs 10GB
            "surya_gpu": 8.0,   # Surya GPU-accelerated needs 8GB
            "donut": 8.0,       # Donut OCR needs 8GB
            "hybrid": 12.0,     # Hybrid uses multiple backends, estimate max
            "surya": 0.0,       # CPU-only fallback
            "qwen_ocr": 14.0,   # Qwen2.5-VL-7B needs 14GB
            "chandra": 15.0,    # Chandra 9B VLM - Standard FP16
            "chandra_8bit": 9.0,  # Chandra 9B - 8-bit Quantisierung
            "chandra_4bit": 5.0,  # Chandra 9B - 4-bit Quantisierung
            "olmocr": 14.0,     # OlmOCR-2 7B needs 14GB (based on Qwen2.5-VL)
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
            logger.error("gpu_check_failed", **safe_error_log(e))
            return {
                "available": False,
                "reason": safe_error_detail(e, "GPU-Check"),
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
                logger.debug("cuda_cache_clear_failed", error_type=type(e).__name__)

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
            logger.critical("gpu_recovery_catastrophic_failure", **safe_error_log(e))
            return {
                "recovered": False,
                "error": safe_error_detail(e, "Vorgang"),
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

    # ==========================================================================
    # GPU Memory Vorhersage (P1 - Proaktive OOM-Verhinderung)
    # ==========================================================================

    def predict_memory_usage(
        self,
        backend: str,
        batch_size: int = 1,
        image_size_mb: float = 0.0,
        page_count: int = 1
    ) -> Dict[str, Any]:
        """
        Vorhersage des VRAM-Verbrauchs für einen OCR-Task.

        Verwendet empirische Messungen und Heuristiken um den erwarteten
        Speicherverbrauch zu schätzen. Ermöglicht proaktive OOM-Verhinderung.

        Args:
            backend: OCR Backend Name
            batch_size: Anzahl der Dokumente im Batch
            image_size_mb: Größe des Eingabebilds in MB (optional)
            page_count: Anzahl der Seiten (für Multi-Page-PDFs)

        Returns:
            Dict mit Vorhersage:
            - predicted_gb: Geschätzter VRAM-Verbrauch in GB
            - confidence: Konfidenz der Vorhersage (0-1)
            - model_base_gb: Basis-VRAM für Model
            - processing_gb: VRAM für Verarbeitung
            - overhead_gb: Overhead/Buffer
        """
        # Basis-VRAM für geladenes Model (in GB)
        model_base_map = {
            "deepseek": 10.0,    # DeepSeek-Janus-Pro Model Weights
            "got_ocr": 6.0,     # GOT-OCR 2.0 Weights
            "surya_gpu": 4.0,   # Surya GPU Weights
            "surya_docling": 2.0,  # Surya CPU (minimal GPU)
            "donut": 5.0,       # Donut Weights
            "hybrid": 10.0,     # Conservative: Max of sub-models
            "surya": 0.0,       # CPU-only
        }

        # Verarbeitungs-VRAM pro Dokument (in MB)
        processing_mb_per_doc = {
            "deepseek": 1024,   # 1GB pro Dokument (complex multimodal)
            "got_ocr": 500,     # 500MB pro Dokument
            "surya_gpu": 250,   # 250MB pro Dokument
            "surya_docling": 100,  # 100MB (mostly CPU)
            "donut": 400,       # 400MB pro Dokument
            "hybrid": 1024,     # Conservative
            "surya": 0,         # CPU-only
        }

        # Hole profiled Werte falls verfügbar
        if hasattr(self, '_backend_profiles') and backend in self._backend_profiles:
            profile = self._backend_profiles[backend]
            measured_mb = profile.get('measured_mb_per_doc')
            if measured_mb and measured_mb > 0:
                processing_mb_per_doc[backend] = measured_mb
                confidence = 0.9  # Hohe Konfidenz bei gemessenen Werten
            else:
                confidence = 0.7  # Mittlere Konfidenz bei Heuristik
        else:
            confidence = 0.7

        # Berechne Vorhersage
        model_base_gb = model_base_map.get(backend, 5.0)
        processing_mb = processing_mb_per_doc.get(backend, 500) * batch_size

        # Skalierung nach Bildgröße (größere Bilder brauchen mehr VRAM)
        if image_size_mb > 0:
            # Faktor: 10MB Bild -> 1.0x, 50MB Bild -> 1.5x, 100MB Bild -> 2.0x
            size_factor = 1.0 + (image_size_mb / 100.0)
            processing_mb *= size_factor
            confidence *= 0.9  # Leicht reduzierte Konfidenz bei größeren Bildern

        # Skalierung nach Seitenanzahl
        if page_count > 1:
            # Multi-Page PDFs: Nicht linear (Batching)
            page_factor = 1.0 + (0.2 * (page_count - 1))  # 20% mehr pro Seite
            processing_mb *= page_factor

        processing_gb = processing_mb / 1024

        # Overhead (CUDA Kernel, Aktivierungen, temporaere Tensoren)
        # Ca. 15% des Verarbeitungs-VRAMs
        overhead_gb = processing_gb * 0.15

        total_predicted_gb = model_base_gb + processing_gb + overhead_gb

        prediction = {
            "predicted_gb": round(total_predicted_gb, 2),
            "confidence": round(confidence, 2),
            "breakdown": {
                "model_base_gb": round(model_base_gb, 2),
                "processing_gb": round(processing_gb, 2),
                "overhead_gb": round(overhead_gb, 2),
            },
            "parameters": {
                "backend": backend,
                "batch_size": batch_size,
                "image_size_mb": image_size_mb,
                "page_count": page_count,
            }
        }

        logger.debug("memory_prediction", **prediction)
        return prediction

    def can_process_task(
        self,
        backend: str,
        batch_size: int = 1,
        image_size_mb: float = 0.0,
        page_count: int = 1,
        safety_margin: float = 0.15
    ) -> Dict[str, Any]:
        """
        Prüfe ob ein Task mit den aktuellen VRAM-Ressourcen verarbeitet werden kann.

        Args:
            backend: OCR Backend Name
            batch_size: Batch-Größe
            image_size_mb: Bildgröße in MB
            page_count: Seitenanzahl
            safety_margin: Sicherheitspuffer (default: 15%)

        Returns:
            Dict mit:
            - can_process: Bool - Ob der Task verarbeitet werden kann
            - reason: Grund falls nicht möglich
            - predicted_gb: Vorhergesagter Verbrauch
            - available_gb: Verfügbarer VRAM
            - suggested_batch_size: Empfohlene Batch-Größe falls zu groß
            - suggested_backend: Alternative Backend-Empfehlung
        """
        # Vorhersage erstellen
        prediction = self.predict_memory_usage(
            backend=backend,
            batch_size=batch_size,
            image_size_mb=image_size_mb,
            page_count=page_count
        )

        # Aktuellen Status prüfen
        status = self.check_availability()

        if not status.get("available"):
            return {
                "can_process": backend == "surya",  # CPU-only funktioniert immer
                "reason": "GPU nicht verfügbar",
                "suggested_backend": "surya",
                "predicted_gb": prediction["predicted_gb"],
                "available_gb": 0.0,
            }

        available_gb = status.get("free_gb", 0)
        safe_available_gb = available_gb * (1 - safety_margin)
        predicted_gb = prediction["predicted_gb"]

        result = {
            "predicted_gb": predicted_gb,
            "available_gb": round(available_gb, 2),
            "safe_available_gb": round(safe_available_gb, 2),
            "prediction_confidence": prediction["confidence"],
        }

        if predicted_gb <= safe_available_gb:
            # Genügend VRAM verfügbar
            result["can_process"] = True
            result["reason"] = "Ausreichend VRAM verfügbar"
            result["headroom_gb"] = round(safe_available_gb - predicted_gb, 2)

        else:
            # Nicht genügend VRAM
            result["can_process"] = False
            result["reason"] = f"Unzureichend VRAM: {predicted_gb:.1f}GB benötigt, {safe_available_gb:.1f}GB verfügbar"
            result["deficit_gb"] = round(predicted_gb - safe_available_gb, 2)

            # Berechne optimale Batch-Größe
            suggested_batch = self._calculate_max_batch_size(
                backend=backend,
                available_gb=safe_available_gb,
                image_size_mb=image_size_mb,
                page_count=page_count
            )
            result["suggested_batch_size"] = suggested_batch

            # Schlage alternatives Backend vor
            suggested_backend = self._suggest_alternative_backend(
                available_gb=safe_available_gb,
                batch_size=batch_size
            )
            result["suggested_backend"] = suggested_backend

        logger.info("task_processability_check", **result)
        return result

    def _calculate_max_batch_size(
        self,
        backend: str,
        available_gb: float,
        image_size_mb: float = 0.0,
        page_count: int = 1
    ) -> int:
        """Berechne maximale Batch-Größe für gegebenen VRAM."""
        # Binäre Suche nach maximaler Batch-Größe
        for batch_size in range(32, 0, -1):
            prediction = self.predict_memory_usage(
                backend=backend,
                batch_size=batch_size,
                image_size_mb=image_size_mb,
                page_count=page_count
            )
            if prediction["predicted_gb"] <= available_gb:
                return batch_size
        return 1

    def _suggest_alternative_backend(
        self,
        available_gb: float,
        batch_size: int = 1
    ) -> Optional[str]:
        """Schlage alternatives Backend vor basierend auf verfügbarem VRAM."""
        # Sortiert nach Qualität (beste zuerst)
        backend_priority = [
            ("deepseek", 12.0),
            ("got_ocr", 8.0),
            ("surya_gpu", 5.0),
            ("surya_docling", 2.0),
            ("surya", 0.0),  # CPU-fallback
        ]

        for backend, min_vram in backend_priority:
            prediction = self.predict_memory_usage(
                backend=backend,
                batch_size=min(batch_size, 4)  # Konservative Batch-Größe
            )
            if prediction["predicted_gb"] <= available_gb:
                return backend

        return "surya"  # Immer CPU als letzter Fallback

    def suggest_optimal_settings(
        self,
        preferred_backend: str = "auto",
        document_count: int = 1,
        image_size_mb: float = 0.0,
        page_count: int = 1,
        target_throughput: str = "balanced"
    ) -> Dict[str, Any]:
        """
        Empfehle optimale Einstellungen für einen OCR-Job.

        Berücksichtigt:
        - Verfügbaren VRAM
        - Anzahl der Dokumente
        - Gewünschten Durchsatz
        - Backend-Fähigkeiten

        Args:
            preferred_backend: Bevorzugtes Backend oder "auto"
            document_count: Anzahl zu verarbeitender Dokumente
            image_size_mb: Bildgröße in MB
            page_count: Seiten pro Dokument
            target_throughput: "fast", "balanced", oder "quality"

        Returns:
            Dict mit empfohlenen Einstellungen
        """
        status = self.check_availability()
        available_gb = status.get("free_gb", 0) if status.get("available") else 0

        # Backend-Auswahl
        if preferred_backend == "auto":
            if target_throughput == "quality":
                backend_candidates = ["deepseek", "got_ocr", "surya_gpu", "surya"]
            elif target_throughput == "fast":
                backend_candidates = ["surya_gpu", "got_ocr", "surya"]
            else:  # balanced
                backend_candidates = ["got_ocr", "surya_gpu", "deepseek", "surya"]

            selected_backend = None
            for backend in backend_candidates:
                check = self.can_process_task(
                    backend=backend,
                    batch_size=1,
                    image_size_mb=image_size_mb,
                    page_count=page_count
                )
                if check["can_process"]:
                    selected_backend = backend
                    break

            if not selected_backend:
                selected_backend = "surya"  # CPU-fallback
        else:
            selected_backend = preferred_backend

        # Batch-Größe optimieren
        optimal_batch = self._calculate_max_batch_size(
            backend=selected_backend,
            available_gb=available_gb * 0.85,  # 15% Safety
            image_size_mb=image_size_mb,
            page_count=page_count
        )

        # Batch-Größe auf Dokumentanzahl begrenzen
        optimal_batch = min(optimal_batch, document_count)

        # Finales Check
        final_check = self.can_process_task(
            backend=selected_backend,
            batch_size=optimal_batch,
            image_size_mb=image_size_mb,
            page_count=page_count
        )

        suggestion = {
            "backend": selected_backend,
            "batch_size": optimal_batch,
            "can_process": final_check["can_process"],
            "predicted_vram_gb": final_check["predicted_gb"],
            "available_vram_gb": round(available_gb, 2),
            "batches_needed": (document_count + optimal_batch - 1) // optimal_batch,
            "target_throughput": target_throughput,
            "warnings": [],
        }

        # Warnungen hinzufügen
        if optimal_batch < document_count:
            suggestion["warnings"].append(
                f"Batch-Größe auf {optimal_batch} reduziert (VRAM-Limit)"
            )

        if selected_backend != preferred_backend and preferred_backend != "auto":
            suggestion["warnings"].append(
                f"Backend von {preferred_backend} auf {selected_backend} geändert (VRAM)"
            )

        if available_gb < 4:
            suggestion["warnings"].append("Niedriger VRAM - erwäge GPU-Cache-Cleanup")

        logger.info("optimal_settings_suggestion", **suggestion)
        return suggestion

    def has_gpu(self) -> bool:
        """Prüfe ob GPU verfügbar ist."""
        if not TORCH_AVAILABLE:
            return False
        return torch.cuda.is_available()


class GPUMemoryGuard:
    """
    GPU Memory Guard mit Enforcement für Ablage-System.

    Überwacht VRAM-Nutzung und erzwingt Limits:
    - Blockiert neue Allocations bei Überschreitung
    - Automatische Cache-Bereinigung
    - Threshold-basierte Warnungen
    - Metriken für Prometheus
    - **NEU: Proaktive Background-Überwachung (P0-Optimierung)**

    Konfiguration über Umgebungsvariable GPU_MEMORY_LIMIT_GB.
    """

    # Konfiguration (Defaults für RTX 4080 16GB)
    DEFAULT_LIMIT_GB = 13.6  # 85% von 16GB
    WARNING_THRESHOLD = 0.75  # Warnung bei 75%
    CRITICAL_THRESHOLD = 0.90  # Kritisch bei 90%

    # Background Monitor Konfiguration
    MONITOR_INTERVAL_SECONDS = 10  # Prüfintervall
    PROACTIVE_CLEANUP_THRESHOLD = 0.80  # Cleanup bei 80% (zwischen Warning und Critical)

    def __init__(
        self,
        gpu_manager: Optional['GPUManager'] = None,
        memory_limit_gb: Optional[float] = None,
        auto_cleanup: bool = True,
        enable_background_monitor: bool = True
    ):
        """
        Initialisiere GPU Memory Guard.

        Args:
            gpu_manager: Optional GPUManager Instance
            memory_limit_gb: VRAM Limit in GB (default: 13.6)
            auto_cleanup: Automatische Cache-Bereinigung bei Warning
            enable_background_monitor: Aktiviere proaktive Hintergrund-Überwachung
        """
        self.gpu_manager = gpu_manager or GPUManager()
        self.auto_cleanup = auto_cleanup
        self._enable_background_monitor = enable_background_monitor

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
        self._proactive_cleanup_count = 0  # Neue Metrik für proaktive Cleanups

        # Background Monitor State
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_running = False

        logger.info(
            "gpu_memory_guard_initialized",
            limit_gb=self.memory_limit_gb,
            warning_threshold=self.WARNING_THRESHOLD,
            critical_threshold=self.CRITICAL_THRESHOLD,
            proactive_threshold=self.PROACTIVE_CLEANUP_THRESHOLD,
            auto_cleanup=self.auto_cleanup,
            background_monitor=enable_background_monitor
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
            logger.error("gpu_memory_check_failed", **safe_error_log(e))
            return {
                "available": False,
                "enforced": False, **safe_error_log(e)}

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
            logger.error("gpu_cache_cleanup_failed", **safe_error_log(e))
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
                "proactive_threshold": self.PROACTIVE_CLEANUP_THRESHOLD,
                "auto_cleanup": self.auto_cleanup,
                "background_monitor_enabled": self._enable_background_monitor,
            },
            "metrics": {
                "cleanup_count": self._cleanup_count,
                "enforcement_count": self._enforcement_count,
                "warning_count": self._warning_count,
                "critical_count": self._critical_count,
                "proactive_cleanup_count": self._proactive_cleanup_count,
            },
            "monitor": {
                "running": self._monitor_running,
                "interval_seconds": self.MONITOR_INTERVAL_SECONDS,
            }
        }

    # =========================================================================
    # P0: Proactive GPU Memory Monitor - Background Task
    # =========================================================================

    async def start_memory_monitor(self) -> bool:
        """
        Starte proaktiven Hintergrund-Memory-Monitor.

        Der Monitor prüft alle MONITOR_INTERVAL_SECONDS den VRAM-Status und
        führt proaktive Cleanups durch, bevor kritische Zustände erreicht werden.

        Returns:
            True wenn Monitor gestartet wurde, False wenn bereits läuft oder deaktiviert
        """
        if not self._enable_background_monitor:
            logger.debug("background_monitor_disabled")
            return False

        if self._monitor_running:
            logger.debug("background_monitor_already_running")
            return False

        self._monitor_running = True
        self._monitor_task = asyncio.create_task(self._memory_monitor_loop())
        logger.info(
            "gpu_memory_monitor_started",
            interval_seconds=self.MONITOR_INTERVAL_SECONDS,
            proactive_threshold=self.PROACTIVE_CLEANUP_THRESHOLD
        )
        return True

    async def stop_memory_monitor(self) -> bool:
        """
        Stoppe den Hintergrund-Memory-Monitor.

        Returns:
            True wenn Monitor gestoppt wurde, False wenn nicht lief
        """
        if not self._monitor_running:
            return False

        self._monitor_running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        logger.info("gpu_memory_monitor_stopped")
        return True

    async def _memory_monitor_loop(self) -> None:
        """
        Hauptschleife des Memory-Monitors.

        Prüft periodisch den VRAM-Status und führt proaktive Cleanups durch
        bei Überschreitung des proaktiven Thresholds (80%).
        """
        logger.info("gpu_memory_monitor_loop_started")

        while self._monitor_running:
            try:
                await self._proactive_memory_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("memory_monitor_check_error", error_type=type(e).__name__)

            try:
                await asyncio.sleep(self.MONITOR_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                break

        logger.info("gpu_memory_monitor_loop_ended")

    async def _proactive_memory_check(self) -> None:
        """
        Führe proaktive Memory-Prüfung durch.

        Wenn VRAM-Nutzung über PROACTIVE_CLEANUP_THRESHOLD (80%) liegt,
        wird proaktiv der Cache bereinigt, BEVOR es kritisch wird.
        """
        if not TORCH_AVAILABLE or not torch.cuda.is_available():
            return

        try:
            allocated = torch.cuda.memory_allocated(0)
            usage_ratio = allocated / self.memory_limit_bytes

            # Proaktives Cleanup bei 80% (vor Warning bei 75% des Limits)
            if usage_ratio >= self.PROACTIVE_CLEANUP_THRESHOLD:
                before_gb = allocated / (1024**3)

                # Cleanup durchführen
                freed = self.cleanup_cache()
                freed_gb = freed / (1024**3)

                if freed > 0:
                    self._proactive_cleanup_count += 1
                    after_allocated = torch.cuda.memory_allocated(0)
                    after_gb = after_allocated / (1024**3)

                    logger.info(
                        "proactive_memory_cleanup",
                        before_gb=round(before_gb, 2),
                        freed_gb=round(freed_gb, 2),
                        after_gb=round(after_gb, 2),
                        usage_ratio_before=round(usage_ratio, 2),
                        proactive_cleanup_count=self._proactive_cleanup_count
                    )

            # Log bei Critical-Level (auch ohne Cleanup)
            elif usage_ratio >= self.CRITICAL_THRESHOLD:
                logger.warning(
                    "gpu_memory_critical_level",
                    usage_ratio=round(usage_ratio, 2),
                    allocated_gb=round(allocated / (1024**3), 2),
                    limit_gb=self.memory_limit_gb
                )

        except Exception as e:
            logger.debug("proactive_memory_check_error", error_type=type(e).__name__)


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


# =============================================================================
# AdaptiveBatchProcessor - OOM-sichere Batch-Verarbeitung
# =============================================================================

class AdaptiveBatchProcessor:
    """
    Adaptive Batch-Verarbeitung mit automatischem OOM-Fallback und Hysterese.

    Implementiert exponentielles Backoff bei GPU Out-of-Memory Fehlern:
    - Startet mit optimaler Batch-Size (z.B. 4)
    - Bei OOM: Halbiert Batch-Size (4→2→1)
    - Hysterese: Nach 100 erfolgreichen Batches wird Batch-Size um 10% erhöht
    - Tracked Erfolgs/Fehler-Statistiken
    - Integriert mit GPU Memory Profiling

    Usage:
        processor = AdaptiveBatchProcessor(gpu_manager)
        results = await processor.process_with_fallback(
            documents,
            process_func=ocr_backend.process_batch,
            backend="deepseek"
        )
    """

    # Default Konfiguration
    DEFAULT_INITIAL_BATCH = 4
    MIN_BATCH_SIZE = 1
    MAX_BATCH_SIZE = 8

    # Hysterese-Konfiguration
    HYSTERESIS_SUCCESS_THRESHOLD = 100  # Erfolgreiche Batches bis zur Erhöhung
    HYSTERESIS_INCREASE_FACTOR = 1.1  # +10% Batch-Size bei Erholung

    def __init__(
        self,
        gpu_manager: Optional['GPUManager'] = None,
        initial_batch_size: int = DEFAULT_INITIAL_BATCH,
        enable_profiling: bool = True
    ):
        """
        Initialisiere AdaptiveBatchProcessor.

        Args:
            gpu_manager: GPUManager Instance für Batch-Size-Berechnung
            initial_batch_size: Start-Batch-Size
            enable_profiling: GPU Memory Profiling aktivieren
        """
        self.gpu_manager = gpu_manager or GPUManager()
        self.initial_batch_size = initial_batch_size
        self.enable_profiling = enable_profiling

        # Statistiken
        self._stats = {
            "total_batches": 0,
            "successful_batches": 0,
            "oom_events": 0,
            "fallback_count": 0,
            "last_successful_batch_size": initial_batch_size,
            # Hysterese-Tracking
            "consecutive_successes_since_oom": 0,
            "hysteresis_increases": 0,
            "current_effective_max_batch": initial_batch_size,
        }
        self._lock = threading.Lock()

        logger.info(
            "adaptive_batch_processor_initialized",
            initial_batch_size=initial_batch_size,
            enable_profiling=enable_profiling
        )

    async def process_with_fallback(
        self,
        documents: List[Dict[str, Any]],
        process_func: Callable,
        backend: str = "auto",
        initial_batch: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Verarbeite Dokumente mit automatischem OOM-Fallback.

        Implementiert exponentielles Backoff:
        - Bei OOM: batch_size = batch_size // 2
        - Minimum: batch_size = 1
        - Bei Erfolg: Profiling der Memory-Nutzung

        Args:
            documents: Liste von Dokumenten zur Verarbeitung
            process_func: Async/Sync Funktion für Batch-Verarbeitung
            backend: OCR Backend Name für Profiling
            initial_batch: Optionale Start-Batch-Size (überschreibt Default)

        Returns:
            Liste von verarbeiteten Ergebnissen

        Raises:
            RuntimeError: Wenn Verarbeitung auch mit batch_size=1 fehlschlägt
        """
        if not documents:
            return []

        # Bestimme optimale Start-Batch-Size (berücksichtigt Hysterese)
        if initial_batch is not None:
            batch_size = initial_batch
        else:
            batch_size = self.gpu_manager.get_optimal_batch_size_adaptive(backend)
            # Hysterese: Verwende current_effective_max_batch als Obergrenze
            effective_max = self._stats.get("current_effective_max_batch", self.initial_batch_size)
            batch_size = min(batch_size, effective_max, len(documents))

        results: List[Dict[str, Any]] = []
        remaining = list(documents)

        while remaining:
            current_batch = remaining[:batch_size]

            try:
                with self._stats_lock():
                    self._stats["total_batches"] += 1

                # GPU Memory vor Verarbeitung
                start_memory = 0
                if TORCH_AVAILABLE and torch.cuda.is_available() and self.enable_profiling:
                    torch.cuda.reset_peak_memory_stats()
                    start_memory = torch.cuda.memory_allocated()

                # Verarbeite Batch (unterstützt sync und async)
                if asyncio.iscoroutinefunction(process_func):
                    batch_results = await process_func(current_batch)
                else:
                    batch_results = process_func(current_batch)

                # Profiling bei Erfolg
                if TORCH_AVAILABLE and torch.cuda.is_available() and self.enable_profiling:
                    peak_memory = torch.cuda.max_memory_allocated()
                    self.gpu_manager.record_batch_profile(
                        backend=backend,
                        batch_size=len(current_batch),
                        peak_memory_bytes=peak_memory
                    )

                # Erfolg!
                results.extend(batch_results if isinstance(batch_results, list) else [batch_results])
                remaining = remaining[batch_size:]

                with self._stats_lock():
                    self._stats["successful_batches"] += 1
                    self._stats["last_successful_batch_size"] = batch_size
                    self._stats["consecutive_successes_since_oom"] += 1

                    # Hysterese: Nach genügend erfolgreichen Batches Batch-Size erhöhen
                    if self._stats["consecutive_successes_since_oom"] >= self.HYSTERESIS_SUCCESS_THRESHOLD:
                        old_max = self._stats["current_effective_max_batch"]
                        new_max = min(
                            int(old_max * self.HYSTERESIS_INCREASE_FACTOR),
                            self.MAX_BATCH_SIZE
                        )

                        if new_max > old_max:
                            self._stats["current_effective_max_batch"] = new_max
                            self._stats["hysteresis_increases"] += 1
                            self._stats["consecutive_successes_since_oom"] = 0

                            logger.info(
                                "hysteresis_batch_size_increased",
                                old_max_batch=old_max,
                                new_max_batch=new_max,
                                successes_before_increase=self.HYSTERESIS_SUCCESS_THRESHOLD,
                                backend=backend
                            )
                        else:
                            # Max erreicht, Zähler zurücksetzen
                            self._stats["consecutive_successes_since_oom"] = 0

                logger.debug(
                    "batch_processed_successfully",
                    batch_size=batch_size,
                    remaining=len(remaining),
                    backend=backend,
                    consecutive_successes=self._stats.get("consecutive_successes_since_oom", 0)
                )

            except (torch.cuda.OutOfMemoryError if TORCH_AVAILABLE else Exception) as e:
                # OOM Error - Fallback zu kleinerer Batch-Size
                with self._stats_lock():
                    self._stats["oom_events"] += 1
                    self._stats["fallback_count"] += 1
                    # Hysterese zurücksetzen bei OOM
                    self._stats["consecutive_successes_since_oom"] = 0
                    # Effektive Max-Batch-Size ebenfalls reduzieren
                    self._stats["current_effective_max_batch"] = max(
                        self.MIN_BATCH_SIZE,
                        batch_size // 2
                    )

                logger.warning(
                    "oom_batch_fallback",
                    current_batch_size=batch_size,
                    new_batch_size=batch_size // 2,
                    new_effective_max=self._stats["current_effective_max_batch"],
                    hysteresis_reset=True,
                    **safe_error_log(e),
                    backend=backend
                )

                # GPU Memory bereinigen
                if TORCH_AVAILABLE and torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.synchronize()

                # Batch-Size halbieren
                batch_size = batch_size // 2

                if batch_size < self.MIN_BATCH_SIZE:
                    # Auch mit minimaler Batch-Size fehlgeschlagen
                    logger.error(
                        "batch_processing_failed_min_size",
                        backend=backend,
                        documents_remaining=len(remaining)
                    )
                    raise RuntimeError(
                        f"OCR-Verarbeitung fehlgeschlagen auch mit batch_size=1. "
                        f"Backend: {backend}, Error: {str(e)}"
                    ) from e

                # Retry mit kleinerer Batch-Size (nächste Iteration)
                continue

            except Exception as e:
                # Andere Fehler - nicht recoverable durch Batch-Size Reduktion
                logger.error(
                    "batch_processing_error",
                    **safe_error_log(e),
                    backend=backend,
                    batch_size=batch_size
                )
                raise

        return results

    def get_stats(self) -> Dict[str, Any]:
        """Hole Verarbeitungs-Statistiken."""
        with self._stats_lock():
            return {
                **self._stats,
                "oom_rate": (
                    self._stats["oom_events"] / max(1, self._stats["total_batches"])
                ),
                "success_rate": (
                    self._stats["successful_batches"] / max(1, self._stats["total_batches"])
                )
            }

    def reset_stats(self) -> None:
        """Setze Statistiken zurück (inkl. Hysterese)."""
        with self._stats_lock():
            self._stats = {
                "total_batches": 0,
                "successful_batches": 0,
                "oom_events": 0,
                "fallback_count": 0,
                "last_successful_batch_size": self.initial_batch_size,
                # Hysterese zurücksetzen
                "consecutive_successes_since_oom": 0,
                "hysteresis_increases": 0,
                "current_effective_max_batch": self.initial_batch_size,
            }

    @contextmanager
    def _stats_lock(self):
        """Thread-safe Stats-Zugriff."""
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()


# =============================================================================
# GPU Memory Profiling Decorator
# =============================================================================

def profile_gpu_memory(backend_name: str, gpu_manager: Optional['GPUManager'] = None):
    """
    Decorator für automatisches GPU Memory Profiling.

    Trackt Peak-Memory-Nutzung und speichert Profil für adaptive Batch-Sizing.

    Usage:
        @profile_gpu_memory("deepseek")
        async def process_batch(self, documents):
            ...

    Args:
        backend_name: Name des OCR Backends für Profiling
        gpu_manager: Optional GPUManager Instance (Default: Singleton)

    Returns:
        Decorated Function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            manager = gpu_manager or get_gpu_manager()

            # Memory vor Ausführung
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()

            try:
                result = await func(*args, **kwargs)

                # Memory nach Ausführung
                if TORCH_AVAILABLE and torch.cuda.is_available():
                    peak_memory = torch.cuda.max_memory_allocated()

                    # Bestimme Batch-Size aus Args
                    batch_size = 1
                    if args and len(args) > 1 and isinstance(args[1], (list, tuple)):
                        batch_size = len(args[1])
                    elif 'documents' in kwargs and isinstance(kwargs['documents'], (list, tuple)):
                        batch_size = len(kwargs['documents'])

                    manager.record_batch_profile(
                        backend=backend_name,
                        batch_size=batch_size,
                        peak_memory_bytes=peak_memory
                    )

                    logger.debug(
                        "gpu_memory_profiled",
                        backend=backend_name,
                        peak_memory_gb=round(peak_memory / (1024**3), 2),
                        batch_size=batch_size
                    )

                return result

            finally:
                # Cleanup
                if TORCH_AVAILABLE and torch.cuda.is_available():
                    torch.cuda.empty_cache()

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            manager = gpu_manager or get_gpu_manager()

            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()

            try:
                result = func(*args, **kwargs)

                if TORCH_AVAILABLE and torch.cuda.is_available():
                    peak_memory = torch.cuda.max_memory_allocated()

                    batch_size = 1
                    if args and len(args) > 1 and isinstance(args[1], (list, tuple)):
                        batch_size = len(args[1])
                    elif 'documents' in kwargs and isinstance(kwargs['documents'], (list, tuple)):
                        batch_size = len(kwargs['documents'])

                    manager.record_batch_profile(
                        backend=backend_name,
                        batch_size=batch_size,
                        peak_memory_bytes=peak_memory
                    )

                return result

            finally:
                if TORCH_AVAILABLE and torch.cuda.is_available():
                    torch.cuda.empty_cache()

        # Return async or sync wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# =============================================================================
# Adaptive Batch Size Calculator
# =============================================================================

def get_optimal_batch_size_for_document(
    backend: str,
    document_size_mb: float,
    gpu_manager: Optional['GPUManager'] = None
) -> int:
    """
    Berechne optimale Batch-Size basierend auf Dokumentgröße und verfügbarem VRAM.

    Berücksichtigt:
    - Backend-spezifische Memory-Anforderungen
    - Aktuelle GPU-Auslastung
    - Dokumentgröße (größere Dokumente = mehr Memory)
    - 15% Safety Buffer

    Args:
        backend: OCR Backend Name
        document_size_mb: Dokumentgröße in MB
        gpu_manager: Optional GPUManager Instance

    Returns:
        Optimale Batch-Size (1-8)
    """
    manager = gpu_manager or get_gpu_manager()
    status = manager.check_availability()

    if not status.get("available") or backend == "surya":
        return 4  # CPU Fallback

    available_vram_gb = status.get("free_gb", 0)

    # Heuristiken: Base Memory + Document Size Faktor (in GB)
    memory_per_doc = {
        "deepseek": lambda size: 2.0 + size * 0.15,   # 2GB base + 150MB pro MB
        "got_ocr": lambda size: 1.5 + size * 0.10,    # 1.5GB base + 100MB pro MB
        "surya_gpu": lambda size: 0.5 + size * 0.05,  # 0.5GB base + 50MB pro MB
        "donut": lambda size: 1.0 + size * 0.08,      # 1GB base + 80MB pro MB
        "hybrid": lambda size: 2.0 + size * 0.15,     # Wie DeepSeek (konservativ)
    }

    # Berechne Memory pro Dokument
    size_mb = document_size_mb / 1024  # Convert to GB für Formel
    estimated_gb = memory_per_doc.get(backend, lambda s: 1.5)(size_mb)

    # Safety Buffer: 15%
    safe_vram_gb = available_vram_gb * 0.85

    # Berechne optimale Batch-Size
    optimal = int(safe_vram_gb / estimated_gb)

    # Clamp zwischen 1 und 8
    result = max(1, min(optimal, 8))

    logger.debug(
        "optimal_batch_size_calculated",
        backend=backend,
        document_size_mb=document_size_mb,
        available_vram_gb=round(available_vram_gb, 2),
        estimated_gb_per_doc=round(estimated_gb, 2),
        optimal_batch_size=result
    )

    return result


# =============================================================================
# Singleton Instances
# =============================================================================

_memory_guard: Optional[GPUMemoryGuard] = None
_gpu_manager: Optional[GPUManager] = None
_batch_processor: Optional[AdaptiveBatchProcessor] = None


def get_memory_guard() -> GPUMemoryGuard:
    """Hole Singleton-Instance des Memory Guards."""
    global _memory_guard
    if _memory_guard is None:
        _memory_guard = GPUMemoryGuard()
    return _memory_guard


def get_gpu_manager() -> GPUManager:
    """Hole Singleton-Instance des GPU Managers."""
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager()
    return _gpu_manager


def get_batch_processor() -> AdaptiveBatchProcessor:
    """Hole Singleton-Instance des AdaptiveBatchProcessor."""
    global _batch_processor
    if _batch_processor is None:
        _batch_processor = AdaptiveBatchProcessor(gpu_manager=get_gpu_manager())
    return _batch_processor
