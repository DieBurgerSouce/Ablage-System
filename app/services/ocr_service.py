"""
OCR Service - Central OCR Processing Layer
Integrates backend manager with FastAPI
Priority: P0 - CRITICAL
Created: 2024-11-22
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

# Import backends (will be mocked if dependencies not installed)
try:
    import sys
    sys.path.append(str(Path(__file__).parent.parent.parent))

    from Static_Knowledge.Skills.ocr_backends.backend_manager import BackendManager
    BACKENDS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Backend manager not available: {e}")
    BACKENDS_AVAILABLE = False


class OCRService:
    """
    Central OCR Service
    Provides high-level OCR processing interface for FastAPI
    """

    def __init__(self):
        """Initialize OCR service with backend manager"""
        self.backend_manager = BackendManager() if BACKENDS_AVAILABLE else None
        self.processing_stats = {
            "total_processed": 0,
            "total_errors": 0,
            "by_backend": {}
        }
        logger.info("OCR Service initialized")

    async def process_document(
        self,
        image_path: str,
        backend: Optional[str] = None,
        language: str = "de",
        detect_layout: bool = True,
        detect_fraktur: bool = False
    ) -> Dict[str, Any]:
        """
        Process document with OCR

        Args:
            image_path: Path to image file
            backend: Backend to use ("auto", "deepseek", "got_ocr", "surya")
            language: Target language ("de", "en")
            detect_layout: Whether to perform layout detection
            detect_fraktur: Special handling for Fraktur fonts

        Returns:
            OCR result with extracted text and metadata
        """
        start_time = datetime.utcnow()

        try:
            # Validate file exists
            if not Path(image_path).exists():
                raise FileNotFoundError(f"Image not found: {image_path}")

            # Mock processing if backends not available
            if not BACKENDS_AVAILABLE or not self.backend_manager:
                logger.warning("Using mock OCR processing")
                return await self._mock_process(image_path, language)

            # Select backend (auto-selection if not specified)
            if backend == "auto" or backend is None:
                selected_backend = await self.backend_manager.select_backend(
                    image_path=image_path,
                    language=language,
                    detect_layout=detect_layout
                )
            else:
                selected_backend = backend

            logger.info(
                f"Processing document with {selected_backend}",
                extra={
                    "image": image_path,
                    "backend": selected_backend,
                    "language": language
                }
            )

            # Process with selected backend
            result = await self.backend_manager.process_with_backend(
                backend_name=selected_backend,
                image_path=image_path,
                language=language,
                detect_fraktur=detect_fraktur
            )

            # Add processing metadata
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            result["metadata"] = {
                "backend_used": selected_backend,
                "processing_time_seconds": processing_time,
                "language": language,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Update stats
            self.processing_stats["total_processed"] += 1
            backend_stats = self.processing_stats["by_backend"].get(selected_backend, 0)
            self.processing_stats["by_backend"][selected_backend] = backend_stats + 1

            return result

        except Exception as e:
            self.processing_stats["total_errors"] += 1
            logger.exception(f"OCR processing failed: {e}")

            # Try fallback to CPU if GPU failed
            if BACKENDS_AVAILABLE and "cuda" in str(e).lower():
                logger.warning("GPU error detected, falling back to Surya (CPU)")
                try:
                    return await self.backend_manager.process_with_backend(
                        backend_name="surya",
                        image_path=image_path,
                        language=language
                    )
                except Exception as fallback_error:
                    logger.exception(f"Fallback also failed: {fallback_error}")

            raise

    async def _mock_process(self, image_path: str, language: str) -> Dict[str, Any]:
        """Mock OCR processing for testing without real backends"""
        await asyncio.sleep(0.5)  # Simulate processing time

        return {
            "success": True,
            "text": f"[MOCK] Extrahierter Text aus {Path(image_path).name}\n\n"
                    f"Rechnung Nr. 2024-001\n"
                    f"Müller GmbH & Co. KG\n"
                    f"Datum: 22.11.2024\n"
                    f"Betrag: 1.234,56 €",
            "confidence": 0.95,
            "metadata": {
                "backend_used": "mock",
                "processing_time_seconds": 0.5,
                "language": language,
                "timestamp": datetime.utcnow().isoformat(),
                "note": "Mock processing - install OCR backends for real processing"
            }
        }

    async def batch_process(
        self,
        image_paths: List[str],
        backend: Optional[str] = None,
        language: str = "de",
        max_concurrent: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Process multiple documents in parallel

        Args:
            image_paths: List of image file paths
            backend: Backend to use for all documents
            language: Target language
            max_concurrent: Maximum concurrent processing tasks

        Returns:
            List of OCR results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(path: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.process_document(
                    image_path=path,
                    backend=backend,
                    language=language
                )

        # Process all documents concurrently (respecting semaphore)
        results = await asyncio.gather(
            *[process_with_semaphore(path) for path in image_paths],
            return_exceptions=True
        )

        # Convert exceptions to error dicts
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "success": False,
                    "error": str(result),
                    "image_path": image_paths[i]
                })
            else:
                processed_results.append(result)

        return processed_results

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            **self.processing_stats,
            "backends_available": BACKENDS_AVAILABLE,
            "available_backends": ["deepseek", "got_ocr", "surya"] if BACKENDS_AVAILABLE else []
        }

    def health_check(self) -> Dict[str, Any]:
        """Check service health"""
        return {
            "status": "healthy" if BACKENDS_AVAILABLE else "degraded",
            "backends_available": BACKENDS_AVAILABLE,
            "message": "OCR service operational" if BACKENDS_AVAILABLE else "Running with mock processing"
        }


# Singleton instance
_ocr_service_instance: Optional[OCRService] = None

def get_ocr_service() -> OCRService:
    """Get or create OCR service singleton"""
    global _ocr_service_instance
    if _ocr_service_instance is None:
        _ocr_service_instance = OCRService()
    return _ocr_service_instance
