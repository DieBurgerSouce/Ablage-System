"""Backend Manager - OCR Backend Selection and Management."""

import logging
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path
import os

from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
# GPU-based backends - only import if torch is available
try:
    import torch
    TORCH_AVAILABLE = torch.cuda.is_available()
    if TORCH_AVAILABLE:
        from app.agents.ocr.deepseek_agent import DeepSeekAgent
        from app.agents.ocr.got_ocr_agent import GOTOCRAgent
except ImportError:
    TORCH_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.info("PyTorch not available - only CPU backends will be used")

logger = logging.getLogger(__name__)


class BackendManager:
    """Manages OCR backend selection and processing."""

    def __init__(self):
        """Initialize backend manager with available OCR agents."""
        self.backends = {}
        self._initialize_backends()
        logger.info(f"Backend Manager initialized with {len(self.backends)} backends")

    def _initialize_backends(self):
        """Initialize available OCR backends."""
        # Try to initialize GPU-accelerated Surya first if available
        gpu_surya_initialized = False
        if TORCH_AVAILABLE:
            try:
                from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
                self.backends["surya_gpu"] = SuryaGPUAgent()
                gpu_surya_initialized = True
                logger.info(f"Surya GPU backend initialized on {torch.cuda.get_device_name(0)}")
            except Exception as e:
                logger.info(f"Surya GPU backend not available: {e}")

        # Always initialize CPU Surya as fallback
        try:
            self.backends["surya"] = SuryaDoclingAgent()
            logger.info("Surya CPU backend initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Surya CPU backend: {e}")

        # Try to initialize GPU-based backends if PyTorch and GPU are available
        if TORCH_AVAILABLE:
            # Initialize DeepSeek (requires GPU)
            try:
                self.backends["deepseek"] = DeepSeekAgent()
                logger.info("DeepSeek backend initialized")
            except Exception as e:
                logger.warning(f"DeepSeek backend not available: {e}")

            # Initialize GOT-OCR (requires GPU)
            try:
                self.backends["got_ocr"] = GOTOCRAgent()
                logger.info("GOT-OCR backend initialized")
            except Exception as e:
                logger.warning(f"GOT-OCR backend not available: {e}")
        else:
            logger.info("GPU/PyTorch not available - only CPU backends (Surya) will be used")

    async def select_backend(
        self,
        image_path: str,
        language: str = "de",
        detect_layout: bool = True,
        prefer_gpu: bool = True
    ) -> str:
        """
        Select the best backend for processing.

        Args:
            image_path: Path to the document
            language: Target language
            detect_layout: Whether layout detection is needed
            prefer_gpu: Whether to prefer GPU backends

        Returns:
            Name of the selected backend
        """
        # Check file size and type
        file_path = Path(image_path)
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        is_pdf = file_path.suffix.lower() == '.pdf'

        # Selection logic
        available_backends = list(self.backends.keys())

        if not available_backends:
            raise RuntimeError("No OCR backends available")

        # Prefer GPU-accelerated Surya if available
        if prefer_gpu and "surya_gpu" in available_backends:
            logger.info("Selecting GPU-accelerated Surya for maximum performance")
            return "surya_gpu"

        # If only CPU Surya is available, use it
        if len(available_backends) == 1 and "surya" in available_backends:
            logger.info("Only Surya CPU backend available, selecting it")
            return "surya"

        # Complex documents with tables/layout → prefer DeepSeek or GOT-OCR
        if detect_layout and prefer_gpu and TORCH_AVAILABLE:
            if "deepseek" in available_backends and file_size_mb > 5:
                logger.info(f"Selecting DeepSeek for large complex document ({file_size_mb:.1f}MB)")
                return "deepseek"
            elif "got_ocr" in available_backends:
                logger.info("Selecting GOT-OCR for layout detection")
                return "got_ocr"

        # PDF files → prefer GOT-OCR or Surya
        if is_pdf:
            if "got_ocr" in available_backends:
                logger.info("Selecting GOT-OCR for PDF processing")
                return "got_ocr"
            else:
                logger.info("Selecting Surya for PDF processing")
                return "surya"

        # German text with potential Fraktur → prefer DeepSeek
        if language == "de" and "deepseek" in available_backends:
            logger.info("Selecting DeepSeek for German text")
            return "deepseek"

        # Default to fastest available
        if "surya" in available_backends:
            logger.info("Selecting Surya as default backend")
            return "surya"
        elif "got_ocr" in available_backends:
            logger.info("Selecting GOT-OCR as default backend")
            return "got_ocr"
        else:
            logger.info(f"Selecting first available backend: {available_backends[0]}")
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
        logger.info(f"Processing with {backend_name} backend")

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
            logger.error(f"Backend {backend_name} processing failed: {e}")
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
                logger.info(f"Cleaned up {name} backend")
            except Exception as e:
                logger.error(f"Error cleaning up {name} backend: {e}")