"""Backend Manager - OCR Backend Selection and Management."""

import structlog
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
import os

from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent

# Import A/B testing for backend selection experiments
from app.ml.ab_testing import get_ab_test_manager
# GPU-based backends - only import if torch is available
try:
    import torch
    TORCH_AVAILABLE = torch.cuda.is_available()
    if TORCH_AVAILABLE:
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent
except ImportError:
    TORCH_AVAILABLE = False

logger = structlog.get_logger(__name__)


class BackendManager:
    """Manages OCR backend selection and processing."""

    def __init__(self):
        """Initialize backend manager with available OCR agents."""
        self.backends = {}
        self._initialize_backends()
        logger.info("backend_manager_initialized", backend_count=len(self.backends))

    def _initialize_backends(self):
        """Initialize available OCR backends."""
        # Try to initialize GPU-accelerated Surya first if available
        gpu_surya_initialized = False
        if TORCH_AVAILABLE:
            try:
                from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
                self.backends["surya_gpu"] = SuryaGPUAgent()
                gpu_surya_initialized = True
                logger.info("surya_gpu_backend_initialized", device=torch.cuda.get_device_name(0))
            except Exception as e:
                logger.info("surya_gpu_backend_unavailable", error=str(e))

        # Always initialize CPU Surya as fallback
        try:
            self.backends["surya"] = SuryaDoclingAgent()
            logger.info("surya_cpu_backend_initialized")
        except Exception as e:
            logger.error("surya_cpu_backend_init_failed", error=str(e))

        # Try to initialize GPU-based backends if PyTorch and GPU are available
        if TORCH_AVAILABLE:
            # Initialize DeepSeek (requires GPU)
            try:
                self.backends["deepseek"] = DeepSeekAgent()
                logger.info("deepseek_backend_initialized")
            except Exception as e:
                logger.warning("deepseek_backend_unavailable", error=str(e))

            # Initialize GOT-OCR (requires GPU)
            try:
                self.backends["got_ocr"] = GOTOCRAgent()
                logger.info("got_ocr_backend_initialized")
            except Exception as e:
                logger.warning("got_ocr_backend_unavailable", error=str(e))
        else:
            logger.info("gpu_unavailable_cpu_only")

    async def select_backend(
        self,
        image_path: str,
        language: str = "de",
        detect_layout: bool = True,
        prefer_gpu: bool = True,
        document_id: Optional[str] = None
    ) -> str:
        """
        Select the best backend for processing.

        Checks for active A/B experiments first, then falls back to rule-based selection.

        Args:
            image_path: Path to the document
            language: Target language
            detect_layout: Whether layout detection is needed
            prefer_gpu: Whether to prefer GPU backends
            document_id: Optional document ID for A/B experiment allocation

        Returns:
            Name of the selected backend
        """
        available_backends = list(self.backends.keys())

        if not available_backends:
            raise RuntimeError("No OCR backends available")

        # Check for active A/B experiment first (if document_id provided)
        if document_id:
            try:
                ab_manager = get_ab_test_manager()
                for experiment in ab_manager.get_active_experiments():
                    # Check if experiment is for OCR backend testing
                    variant = ab_manager.get_variant(experiment.experiment_id, document_id)
                    if variant and "backend" in variant.config:
                        ab_backend = variant.config["backend"]
                        # Validate the backend is available
                        if ab_backend in available_backends:
                            logger.info(
                                "backend_selected_ab_test",
                                backend=ab_backend,
                                experiment_id=experiment.experiment_id,
                                variant=variant.name,
                                document_id=document_id
                            )
                            return ab_backend
                        else:
                            logger.warning(
                                "ab_backend_unavailable",
                                requested=ab_backend,
                                available=available_backends,
                                experiment_id=experiment.experiment_id
                            )
            except Exception as e:
                # Don't fail if A/B testing has issues - fall back to normal selection
                logger.warning("ab_test_check_failed", error=str(e))

        # Check file size and type for rule-based selection
        file_path = Path(image_path)
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        is_pdf = file_path.suffix.lower() == '.pdf'

        # Prefer GPU-accelerated Surya if available
        if prefer_gpu and "surya_gpu" in available_backends:
            logger.info("backend_selected", backend="surya_gpu", reason="gpu_accelerated")
            return "surya_gpu"

        # If only CPU Surya is available, use it
        if len(available_backends) == 1 and "surya" in available_backends:
            logger.info("backend_selected", backend="surya", reason="only_available")
            return "surya"

        # Complex documents with tables/layout → prefer DeepSeek or GOT-OCR
        if detect_layout and prefer_gpu and TORCH_AVAILABLE:
            if "deepseek" in available_backends and file_size_mb > 5:
                logger.info("backend_selected", backend="deepseek", reason="large_complex_document", file_size_mb=round(file_size_mb, 1))
                return "deepseek"
            elif "got_ocr" in available_backends:
                logger.info("backend_selected", backend="got_ocr", reason="layout_detection")
                return "got_ocr"

        # PDF files → prefer GOT-OCR or Surya
        if is_pdf:
            if "got_ocr" in available_backends:
                logger.info("backend_selected", backend="got_ocr", reason="pdf_processing")
                return "got_ocr"
            else:
                logger.info("backend_selected", backend="surya", reason="pdf_processing")
                return "surya"

        # German text with potential Fraktur → prefer DeepSeek
        if language == "de" and "deepseek" in available_backends:
            logger.info("backend_selected", backend="deepseek", reason="german_text")
            return "deepseek"

        # Default to fastest available
        if "surya" in available_backends:
            logger.info("backend_selected", backend="surya", reason="default")
            return "surya"
        elif "got_ocr" in available_backends:
            logger.info("backend_selected", backend="got_ocr", reason="default")
            return "got_ocr"
        else:
            logger.info("backend_selected", backend=available_backends[0], reason="first_available")
            return available_backends[0]

    async def process_with_backend(
        self,
        backend_name: str,
        image_path: str,
        language: str = "de",
        detect_fraktur: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Process document with specified backend.

        Args:
            backend_name: Name of the backend to use
            image_path: Path to the document
            language: Target language
            detect_fraktur: Whether to detect Fraktur script
            **kwargs: Additional backend-specific parameters

        Returns:
            OCR processing result
        """
        if backend_name not in self.backends:
            available = list(self.backends.keys())
            raise ValueError(f"Backend '{backend_name}' not available. Available: {available}")

        backend = self.backends[backend_name]
        logger.info("processing_with_backend", backend=backend_name)

        # Prepare input data
        input_data = {
            "image_path": image_path,
            "language": language,
            "detect_fraktur": detect_fraktur,
            **kwargs
        }

        # Process with backend
        try:
            result = await backend.process(input_data)
            result["backend"] = backend_name
            return result
        except Exception as e:
            logger.error("backend_processing_failed", backend=backend_name, error=str(e))
            raise

    async def get_backend_status(self, backend_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get status of backend(s).

        Args:
            backend_name: Specific backend to check, or None for all

        Returns:
            Status information
        """
        if backend_name:
            if backend_name not in self.backends:
                return {"error": f"Backend '{backend_name}' not found"}
            # Await if it's a coroutine, otherwise call directly
            status = self.backends[backend_name].get_status()
            if asyncio.iscoroutine(status):
                return await status
            return status

        # Return status for all backends
        status_dict = {}
        for name, backend in self.backends.items():
            status = backend.get_status()
            if asyncio.iscoroutine(status):
                status_dict[name] = await status
            else:
                status_dict[name] = status
        return status_dict

    def get_available_backends(self) -> List[str]:
        """Get list of available backend names."""
        return list(self.backends.keys())

    async def cleanup(self):
        """Clean up all backends."""
        for name, backend in self.backends.items():
            try:
                await backend.cleanup()
                logger.info("backend_cleaned_up", backend=name)
            except Exception as e:
                logger.error("backend_cleanup_failed", backend=name, error=str(e))