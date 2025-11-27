"""
OCR Backend Manager - Unified Backend Interface
Central orchestration layer for all OCR backends
Priority: P0 - CRITICAL

Responsibilities:
- Backend selection based on document type and GPU availability
- Load balancing and fallback handling
- Performance monitoring and optimization
- Resource allocation (GPU VRAM)
"""

from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pathlib import Path
import yaml

import structlog

logger = structlog.get_logger(__name__)


class BackendType(Enum):
    """Available OCR backends"""
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    SURYA = "surya"


class DocumentType(Enum):
    """German document types"""
    RECHNUNG = "rechnung"  # Invoice
    VERTRAG = "vertrag"  # Contract
    LIEFERSCHEIN = "lieferschein"  # Delivery note
    BEHOERDENSCHREIBEN = "behoerdenschreiben"  # Official letter
    HANDSCHRIFT = "handschrift"  # Handwritten
    NIEDRIGE_QUALITAET = "niedrige_qualitaet"  # Low quality
    UNKNOWN = "unknown"


class OCRResult:
    """Standardized OCR result format"""

    def __init__(
        self,
        text: str,
        confidence: float,
        backend_used: BackendType,
        processing_time_ms: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.text = text
        self.confidence = confidence
        self.backend_used = backend_used
        self.processing_time_ms = processing_time_ms
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "backend": self.backend_used.value,
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata
        }


class BackendManager:
    """
    Central OCR Backend Manager
    Orchestrates DeepSeek, GOT-OCR, and Surya backends
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize backend manager

        Args:
            config_path: Path to skills_config.yaml
        """
        self.config = self._load_config(config_path)
        self.backends: Dict[BackendType, Any] = {}
        self.backend_stats: Dict[BackendType, Dict] = {
            backend: {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "total_time_ms": 0.0
            }
            for backend in BackendType
        }

        logger.info("Backend Manager initialized")

    def _load_config(self, config_path: Optional[Path]) -> Dict:
        """Load skills configuration"""
        if config_path is None:
            # Default path
            config_path = Path(__file__).parent.parent / "skills_config.yaml"

        if not config_path.exists():
            logger.warning("config_not_found", config_path=str(config_path))
            return self._get_default_config()

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info("config_loaded", config_path=str(config_path))
            return config
        except Exception as e:
            logger.error("failed_to_load_config", error=str(e))
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Default configuration if YAML not available"""
        return {
            "backends": {
                "deepseek": {"vram_required_gb": 12.0, "priority": 1},
                "got_ocr": {"vram_required_gb": 10.0, "priority": 2},
                "surya": {"vram_required_gb": 0.0, "priority": 3}
            },
            "document_routing": {
                "rechnung": {"primary": "deepseek", "fallback": ["got_ocr", "surya"]},
                "unknown": {"primary": "deepseek", "fallback": ["got_ocr", "surya"]}
            }
        }

    def register_backend(self, backend_type: BackendType, backend_instance: Any) -> None:
        """
        Register an OCR backend

        Args:
            backend_type: Type of backend
            backend_instance: Backend implementation instance
        """
        self.backends[backend_type] = backend_instance
        logger.info("backend_registered", backend=backend_type.value)

    def select_backend(
        self,
        document_type: DocumentType,
        available_vram_gb: float,
        force_backend: Optional[BackendType] = None
    ) -> Tuple[BackendType, str]:
        """
        Select optimal backend for document processing

        Args:
            document_type: Type of document
            available_vram_gb: Available GPU VRAM in GB
            force_backend: Force specific backend (for testing)

        Returns:
            Tuple of (selected_backend, selection_reason)
        """
        if force_backend:
            return force_backend, "forced_by_user"

        # Get routing rules for document type
        doc_type_key = document_type.value
        routing = self.config.get("document_routing", {}).get(
            doc_type_key,
            self.config["document_routing"]["unknown"]
        )

        primary = routing["primary"]
        fallbacks = routing.get("fallback", [])

        # Check if primary backend is available
        primary_backend = BackendType(primary)
        primary_vram = self.config["backends"][primary]["vram_required_gb"]

        if self._is_backend_available(primary_backend, available_vram_gb, primary_vram):
            return primary_backend, f"optimal_for_{doc_type_key}"

        # Try fallbacks
        for fallback in fallbacks:
            fallback_backend = BackendType(fallback)
            fallback_vram = self.config["backends"][fallback]["vram_required_gb"]

            if self._is_backend_available(fallback_backend, available_vram_gb, fallback_vram):
                return fallback_backend, f"fallback_vram_insufficient_for_{primary}"

        # Last resort: Surya (CPU only)
        return BackendType.SURYA, "emergency_fallback_no_gpu"

    def _is_backend_available(
        self,
        backend: BackendType,
        available_vram: float,
        required_vram: float
    ) -> bool:
        """Check if backend is available and has enough resources"""
        # Surya is always available (CPU only)
        if backend == BackendType.SURYA:
            return backend in self.backends

        # GPU backends require VRAM
        if available_vram < required_vram:
            return False

        return backend in self.backends

    async def process_document(
        self,
        document_path: Path,
        document_type: DocumentType,
        available_vram_gb: float,
        options: Optional[Dict[str, Any]] = None
    ) -> OCRResult:
        """
        Process document with optimal backend

        Args:
            document_path: Path to document file
            document_type: Type of document
            available_vram_gb: Available GPU VRAM
            options: Additional processing options

        Returns:
            OCRResult with extracted text and metadata

        Raises:
            ValueError: If no backend available
            RuntimeError: If processing fails
        """
        import time

        options = options or {}

        # Select backend
        backend_type, reason = self.select_backend(
            document_type,
            available_vram_gb,
            force_backend=options.get("force_backend")
        )

        if backend_type not in self.backends:
            raise ValueError(f"Backend {backend_type.value} not registered")

        logger.info("backend_selected", backend=backend_type.value, reason=reason)

        # Get backend instance
        backend = self.backends[backend_type]

        # Update stats
        self.backend_stats[backend_type]["requests"] += 1

        # Process document
        try:
            start_time = time.time()

            # Call backend's process method
            # This is a placeholder - actual implementation depends on backend
            result = await self._process_with_backend(
                backend,
                backend_type,
                document_path,
                options
            )

            processing_time_ms = (time.time() - start_time) * 1000

            # Update success stats
            self.backend_stats[backend_type]["successes"] += 1
            self.backend_stats[backend_type]["total_time_ms"] += processing_time_ms

            # Create result
            ocr_result = OCRResult(
                text=result["text"],
                confidence=result.get("confidence", 0.0),
                backend_used=backend_type,
                processing_time_ms=processing_time_ms,
                metadata={
                    "selection_reason": reason,
                    "document_type": document_type.value,
                    **result.get("metadata", {})
                }
            )

            logger.info(
                "ocr_completed",
                backend=backend_type.value,
                processing_time_ms=round(processing_time_ms),
                confidence=round(ocr_result.confidence, 2)
            )

            return ocr_result

        except Exception as e:
            self.backend_stats[backend_type]["failures"] += 1
            logger.error("backend_failed", backend=backend_type.value, error=str(e))
            raise RuntimeError(f"OCR processing failed with {backend_type.value}: {e}") from e

    async def _process_with_backend(
        self,
        backend: Any,
        backend_type: BackendType,
        document_path: Path,
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Call backend's processing method

        This is a unified interface - actual implementation varies by backend
        """
        # Check if backend has process method
        if hasattr(backend, 'process'):
            return await backend.process(document_path, **options)
        elif hasattr(backend, 'extract_text'):
            return await backend.extract_text(document_path, **options)
        else:
            raise NotImplementedError(
                f"Backend {backend_type.value} missing process/extract_text method"
            )

    def get_backend_stats(self) -> Dict[str, Dict]:
        """Get performance statistics for all backends"""
        stats = {}

        for backend_type, data in self.backend_stats.items():
            avg_time_ms = 0
            success_rate = 0

            if data["requests"] > 0:
                success_rate = (data["successes"] / data["requests"]) * 100

            if data["successes"] > 0:
                avg_time_ms = data["total_time_ms"] / data["successes"]

            stats[backend_type.value] = {
                "requests": data["requests"],
                "successes": data["successes"],
                "failures": data["failures"],
                "success_rate_percent": round(success_rate, 2),
                "avg_processing_time_ms": round(avg_time_ms, 2)
            }

        return stats

    def get_recommended_batch_size(
        self,
        backend_type: BackendType,
        available_vram_gb: float,
        quality_mode: str = "medium"
    ) -> int:
        """
        Get recommended batch size for backend

        Args:
            backend_type: Backend to use
            available_vram_gb: Available VRAM
            quality_mode: small, medium, or large

        Returns:
            Recommended batch size
        """
        batch_config = self.config.get("gpu_allocation", {}).get("batch_sizes", {})
        backend_batches = batch_config.get(backend_type.value, {"small": 1, "medium": 2, "large": 4})

        # Get base batch size
        base_batch = backend_batches.get(quality_mode, backend_batches["medium"])

        # Adjust based on available VRAM
        required_vram = self.config["backends"][backend_type.value]["vram_required_gb"]

        if available_vram < required_vram:
            return 1  # Minimum

        # Scale batch size based on available headroom
        vram_ratio = available_vram / required_vram
        adjusted_batch = int(base_batch * min(vram_ratio, 2.0))

        return max(1, adjusted_batch)


# Singleton instance
_backend_manager = None


def get_backend_manager(config_path: Optional[Path] = None) -> BackendManager:
    """Get global BackendManager instance"""
    global _backend_manager
    if _backend_manager is None:
        _backend_manager = BackendManager(config_path)
    return _backend_manager
