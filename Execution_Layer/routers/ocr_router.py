"""
OCR Backend Router - Intelligent backend selection based on initial-prompt.md specifications.

Implements the routing rules:
1. Formeln/Geometrie → GOT-OCR 2.0
2. Komplexe multimodale Analyse → DeepSeek-Janus-Pro (wenn GPU 24GB+ verfügbar)
3. Strukturierte PDFs (Rechnungen, Verträge) → Docling
4. Multi-Language/Layout-kritisch → Surya
5. Fallback-Kette: Janus → GOT → Surya → Docling → Tesseract
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Protocol
from pydantic import BaseModel
import asyncio

import structlog

logger = structlog.get_logger(__name__)


class BackendType(str, Enum):
    """Available OCR backend types."""
    JANUS_PRO = "deepseek-janus-pro"
    GOT_OCR = "got-ocr-2.0"
    SURYA_DOCLING = "surya-docling"
    TESSERACT = "tesseract"  # Fallback


class DocumentAnalysis(BaseModel):
    """Document characteristics for routing decision."""
    has_formulas: bool = False
    has_tables: bool = False
    has_complex_layout: bool = False
    has_images: bool = False
    requires_image_understanding: bool = False
    has_handwriting: bool = False
    has_fraktur: bool = False
    languages: List[str] = ["de"]
    is_scanned: bool = False
    is_structured_pdf: bool = False  # Invoices, contracts
    document_type: Optional[str] = None  # invoice, contract, form, etc.
    page_count: int = 1
    quality_score: float = 0.8  # 0-1, image quality


class BackendCapabilities(BaseModel):
    """Backend capabilities and requirements."""
    name: str
    vram_gb: float
    supports_gpu: bool
    supports_cpu: bool
    best_for: List[str]
    languages: List[str]
    avg_speed_pages_per_sec: float
    accuracy_score: float  # 0-1
    max_batch_size: int


class OCRBackend(Protocol):
    """Protocol for OCR backends."""
    async def ocr(self, image_bytes: bytes, **kwargs) -> Dict[str, Any]: ...
    async def health_check(self) -> bool: ...


class OCRRouter:
    """
    Intelligentes Routing zwischen OCR-Backends.

    Implements the routing strategy from initial-prompt.md.
    """

    # Backend capabilities as per initial-prompt.md
    BACKEND_SPECS = {
        BackendType.JANUS_PRO: BackendCapabilities(
            name="DeepSeek-Janus-Pro 7B",
            vram_gb=24.0,  # Can be reduced to 12GB with quantization
            supports_gpu=True,
            supports_cpu=False,  # GPU only
            best_for=["complex_layouts", "multimodal", "handwriting", "fraktur", "semantic_understanding"],
            languages=["de", "en", "multi"],
            avg_speed_pages_per_sec=2.5,  # 2-3 pages/second on RTX 4080
            accuracy_score=0.96,
            max_batch_size=4
        ),
        BackendType.GOT_OCR: BackendCapabilities(
            name="GOT-OCR 2.0",
            vram_gb=10.0,
            supports_gpu=True,
            supports_cpu=True,  # Can fallback to CPU
            best_for=["formulas", "geometry", "tables", "markdown", "latex"],
            languages=["de", "en", "multi"],
            avg_speed_pages_per_sec=6.0,  # 5-7 pages/second on RTX 4080
            accuracy_score=0.92,
            max_batch_size=8
        ),
        BackendType.SURYA_DOCLING: BackendCapabilities(
            name="Surya + Docling",
            vram_gb=0.0,  # CPU-based
            supports_gpu=False,
            supports_cpu=True,
            best_for=["layout_preservation", "multi_language", "structured_extraction"],
            languages=["de", "en", "multi"],
            avg_speed_pages_per_sec=1.5,  # 1-2 pages/second with layout analysis
            accuracy_score=0.88,
            max_batch_size=4
        ),
        BackendType.TESSERACT: BackendCapabilities(
            name="Tesseract",
            vram_gb=0.0,
            supports_gpu=False,
            supports_cpu=True,
            best_for=["fallback", "simple_text"],
            languages=["de", "en"],
            avg_speed_pages_per_sec=0.5,
            accuracy_score=0.75,
            max_batch_size=1
        )
    }

    def __init__(
        self,
        janus_client: Optional[OCRBackend] = None,
        got_client: Optional[OCRBackend] = None,
        surya_client: Optional[OCRBackend] = None,
        tesseract_client: Optional[OCRBackend] = None
    ):
        self.backends = {
            BackendType.JANUS_PRO: janus_client,
            BackendType.GOT_OCR: got_client,
            BackendType.SURYA_DOCLING: surya_client,
            BackendType.TESSERACT: tesseract_client,
        }

        self.gpu_available = self._check_gpu()
        self.vram_gb = self._get_vram() if self.gpu_available else 0

        logger.info(
            "ocr_router_initialized",
            gpu_available=self.gpu_available,
            vram_gb=round(self.vram_gb, 1),
            backends=[b.value for b in self.get_available_backends()]
        )

    def _check_gpu(self) -> bool:
        """Check if GPU is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _get_vram(self) -> float:
        """Get available VRAM in GB."""
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_properties(0).total_memory / (1024**3)
        return 0

    def get_available_backends(self) -> List[BackendType]:
        """Get list of available backends based on hardware and configuration."""
        available = []

        for backend_type, client in self.backends.items():
            if client is None:
                continue

            specs = self.BACKEND_SPECS[backend_type]

            # Check hardware requirements
            if specs.vram_gb > 0:
                # Needs GPU
                if not self.gpu_available:
                    if not specs.supports_cpu:
                        continue  # Skip GPU-only backends
                elif self.vram_gb < specs.vram_gb:
                    # Check for quantization support (DeepSeek can run with half VRAM)
                    if backend_type == BackendType.JANUS_PRO and self.vram_gb >= 12:
                        available.append(backend_type)  # Can run with quantization
                    continue

            available.append(backend_type)

        return available

    def select_backend(self, analysis: DocumentAnalysis) -> BackendType:
        """
        Wählt das optimale Backend basierend auf Dokumenteigenschaften.

        Implements routing rules from initial-prompt.md:
        1. Formeln/Geometrie → GOT-OCR
        2. Multimodale Analyse → Janus (wenn genug VRAM)
        3. Strukturierte Dokumente → Surya/Docling
        4. Multi-Language/Layout → Surya
        5. Fallback chain
        """
        available_backends = self.get_available_backends()

        if not available_backends:
            raise RuntimeError("No OCR backends available")

        logger.info(
            "selecting_backend",
            has_formulas=analysis.has_formulas,
            has_tables=analysis.has_tables,
            has_complex_layout=analysis.has_complex_layout,
            document_type=analysis.document_type,
            languages=analysis.languages,
            available_backends=[b.value for b in available_backends]
        )

        # Regel 1: Komplexe Formeln/Geometrie → GOT-OCR
        if analysis.has_formulas and BackendType.GOT_OCR in available_backends:
            logger.info("backend_selected", backend="got_ocr", reason="formula_extraction")
            return BackendType.GOT_OCR

        # Regel 2: Multimodale Analyse benötigt → Janus (wenn genug VRAM)
        if analysis.requires_image_understanding or analysis.has_handwriting or analysis.has_fraktur:
            if BackendType.JANUS_PRO in available_backends:
                logger.info("backend_selected", backend="janus_pro", reason="multimodal_analysis")
                return BackendType.JANUS_PRO
            # Fallback to GOT if Janus not available
            if BackendType.GOT_OCR in available_backends:
                logger.info("backend_selected", backend="got_ocr", reason="complex_document_fallback")
                return BackendType.GOT_OCR

        # Regel 3: Strukturierte Dokumente (Rechnungen, Verträge) → Surya/Docling
        if analysis.is_structured_pdf or analysis.document_type in ["invoice", "contract", "form"]:
            if BackendType.SURYA_DOCLING in available_backends:
                logger.info("backend_selected", backend="surya_docling", reason="structured_document")
                return BackendType.SURYA_DOCLING

        # Regel 4: Multi-Language oder komplexes Layout → Surya
        if len(analysis.languages) > 1 or analysis.has_complex_layout:
            if BackendType.SURYA_DOCLING in available_backends:
                logger.info("backend_selected", backend="surya_docling", reason="multi_language_layout")
                return BackendType.SURYA_DOCLING

        # Regel 5: Einfache gescannte Dokumente
        if analysis.is_scanned:
            # Prefer GPU backends for speed
            if BackendType.GOT_OCR in available_backends:
                logger.info("backend_selected", backend="got_ocr", reason="scanned_document")
                return BackendType.GOT_OCR
            if BackendType.JANUS_PRO in available_backends:
                logger.info("backend_selected", backend="janus_pro", reason="scanned_document")
                return BackendType.JANUS_PRO

        # Default fallback chain: Janus → GOT → Surya → Tesseract
        fallback_order = [
            BackendType.JANUS_PRO,
            BackendType.GOT_OCR,
            BackendType.SURYA_DOCLING,
            BackendType.TESSERACT
        ]

        for backend in fallback_order:
            if backend in available_backends:
                logger.info("backend_selected", backend=backend.value, reason="default_fallback")
                return backend

        # Should not reach here if backends are properly configured
        raise RuntimeError("No suitable backend found")

    async def process_with_fallback(
        self,
        image_bytes: bytes,
        analysis: DocumentAnalysis,
        options: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process document with automatic fallback on failure.

        Implements fallback chain from initial-prompt.md:
        Janus → GOT → Surya → Docling → Tesseract
        """
        options = options or {}
        primary_backend = self.select_backend(analysis)

        # Define fallback order starting from selected backend
        fallback_chain = self._get_fallback_chain(primary_backend)

        last_error = None
        for backend_type in fallback_chain:
            backend = self.backends.get(backend_type)
            if backend is None:
                continue

            try:
                logger.info("attempting_ocr", backend=backend_type.value)

                # Prepare backend-specific options
                backend_options = self._prepare_backend_options(
                    backend_type, analysis, options
                )

                # Run OCR
                result = await backend.ocr(image_bytes, **backend_options)

                # Add metadata
                result["backend_used"] = backend_type.value
                result["fallback_attempted"] = backend_type != primary_backend

                return result

            except Exception as e:
                logger.error(
                    "backend_failed",
                    backend=backend_type.value,
                    error=str(e),
                    exc_info=True
                )
                last_error = e
                continue

        # All backends failed
        raise RuntimeError(f"All OCR backends failed. Last error: {last_error}")

    def _get_fallback_chain(self, primary: BackendType) -> List[BackendType]:
        """Get fallback chain starting from primary backend."""
        # Standard fallback order
        standard_order = [
            BackendType.JANUS_PRO,
            BackendType.GOT_OCR,
            BackendType.SURYA_DOCLING,
            BackendType.TESSERACT
        ]

        # Start with primary, then add others in order
        chain = [primary]
        for backend in standard_order:
            if backend != primary and backend in self.get_available_backends():
                chain.append(backend)

        return chain

    def _prepare_backend_options(
        self,
        backend_type: BackendType,
        analysis: DocumentAnalysis,
        user_options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare backend-specific options."""
        options = user_options.copy()

        # Add language preference
        if analysis.languages:
            options["language"] = analysis.languages[0]  # Primary language

        # Backend-specific configurations
        if backend_type == BackendType.GOT_OCR:
            # GOT-OCR specific options
            if analysis.has_formulas:
                options["output_format"] = "latex"
                options["extract_formulas"] = True
            elif analysis.has_tables:
                options["output_format"] = "markdown"

        elif backend_type == BackendType.JANUS_PRO:
            # DeepSeek specific options
            options["extract_entities"] = analysis.document_type in ["invoice", "contract"]
            options["detect_layout"] = analysis.has_complex_layout
            options["extract_tables"] = analysis.has_tables
            options["extract_handwriting"] = analysis.has_handwriting

        elif backend_type == BackendType.SURYA_DOCLING:
            # Surya/Docling specific options
            options["extract_structure"] = True
            options["preserve_layout"] = analysis.has_complex_layout

        return options

    def get_backend_info(self, backend_type: BackendType) -> BackendCapabilities:
        """Get backend capabilities and characteristics."""
        return self.BACKEND_SPECS.get(backend_type)

    def estimate_processing_time(
        self,
        backend_type: BackendType,
        page_count: int
    ) -> float:
        """Estimate processing time in seconds."""
        specs = self.BACKEND_SPECS.get(backend_type)
        if specs:
            return page_count / specs.avg_speed_pages_per_sec
        return page_count * 2  # Default 2 seconds per page

    def get_optimal_batch_size(
        self,
        backend_type: BackendType,
        available_memory_gb: float = None
    ) -> int:
        """Get optimal batch size for backend."""
        specs = self.BACKEND_SPECS.get(backend_type)
        if not specs:
            return 1

        # If memory constrained, reduce batch size
        if available_memory_gb and specs.vram_gb > 0:
            memory_ratio = available_memory_gb / specs.vram_gb
            if memory_ratio < 1:
                return max(1, int(specs.max_batch_size * memory_ratio))

        return specs.max_batch_size

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all backends."""
        health_status = {
            "router": "healthy",
            "gpu_available": self.gpu_available,
            "vram_gb": self.vram_gb,
            "backends": {}
        }

        for backend_type, backend in self.backends.items():
            if backend is None:
                health_status["backends"][backend_type.value] = "not_configured"
            else:
                try:
                    is_healthy = await asyncio.wait_for(
                        backend.health_check(),
                        timeout=5.0
                    )
                    health_status["backends"][backend_type.value] = (
                        "healthy" if is_healthy else "unhealthy"
                    )
                except asyncio.TimeoutError:
                    health_status["backends"][backend_type.value] = "timeout"
                except Exception as e:
                    health_status["backends"][backend_type.value] = f"error: {str(e)}"

        # Overall health
        backend_statuses = health_status["backends"].values()
        if all(s == "healthy" or s == "not_configured" for s in backend_statuses):
            health_status["router"] = "healthy"
        elif any(s == "healthy" for s in backend_statuses):
            health_status["router"] = "degraded"
        else:
            health_status["router"] = "unhealthy"

        return health_status