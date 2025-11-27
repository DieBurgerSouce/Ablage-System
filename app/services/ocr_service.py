"""
OCR Service - Central OCR Processing Layer
Integrates backend manager with FastAPI
Priority: P0 - CRITICAL
Created: 2024-11-22
"""

import structlog
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
import asyncio
import os

logger = structlog.get_logger(__name__)

# Import our backend manager
from app.services.backend_manager import BackendManager


class OCRService:
    """
    Central OCR Service
    Provides high-level OCR processing interface for FastAPI
    """

    def __init__(self):
        """Initialize OCR service with backend manager"""
        self.backend_manager = BackendManager()
        self.processing_stats = {
            "total_processed": 0,
            "total_errors": 0,
            "by_backend": {}
        }

        # Create upload directory if it doesn't exist
        self.upload_dir = Path("uploads")
        self.upload_dir.mkdir(exist_ok=True)

        logger.info("ocr_service_initialized", available_backends=self.backend_manager.get_available_backends())

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

            # Check if backends are available
            available_backends = self.backend_manager.get_available_backends()
            if not available_backends:
                raise RuntimeError("No OCR backends available. Please check installation.")

            # Select backend (auto-selection if not specified)
            if backend == "auto" or backend is None:
                selected_backend = await self.backend_manager.select_backend(
                    image_path=image_path,
                    language=language,
                    detect_layout=detect_layout
                )
            else:
                # Validate requested backend is available
                if backend not in available_backends:
                    logger.warning("requested_backend_unavailable", requested=backend, available=available_backends)
                    # Fallback to auto-selection
                    selected_backend = await self.backend_manager.select_backend(
                        image_path=image_path,
                        language=language,
                        detect_layout=detect_layout
                    )
                else:
                    selected_backend = backend

            logger.info(
                "processing_document",
                backend=selected_backend,
                image_path=image_path,
                language=language
            )

            # Process with selected backend
            result = await self.backend_manager.process_with_backend(
                backend_name=selected_backend,
                image_path=image_path,
                language=language,
                detect_fraktur=detect_fraktur,
                enable_layout=detect_layout
            )

            # Add processing metadata
            processing_time = (datetime.utcnow() - start_time).total_seconds()

            # Ensure we have a proper result structure
            if "metadata" not in result:
                result["metadata"] = {}

            result["metadata"].update({
                "backend_used": selected_backend,
                "processing_time_seconds": round(processing_time, 3),
                "language": language,
                "timestamp": datetime.utcnow().isoformat()
            })

            # Update stats
            self.processing_stats["total_processed"] += 1
            backend_stats = self.processing_stats["by_backend"].get(selected_backend, 0)
            self.processing_stats["by_backend"][selected_backend] = backend_stats + 1

            # Add success flag if not present
            if "success" not in result:
                result["success"] = True

            return result

        except Exception as e:
            self.processing_stats["total_errors"] += 1
            logger.error("ocr_processing_failed", error=str(e), exc_info=True)

            # Try fallback to CPU if GPU failed
            if "cuda" in str(e).lower() or "gpu" in str(e).lower():
                logger.warning("gpu_error_fallback_to_cpu")
                try:
                    # Ensure Surya is available
                    if "surya" in self.backend_manager.get_available_backends():
                        result = await self.backend_manager.process_with_backend(
                            backend_name="surya",
                            image_path=image_path,
                            language=language,
                            enable_layout=detect_layout
                        )

                        # Add metadata about fallback
                        processing_time = (datetime.utcnow() - start_time).total_seconds()
                        if "metadata" not in result:
                            result["metadata"] = {}
                        result["metadata"].update({
                            "backend_used": "surya",
                            "processing_time_seconds": round(processing_time, 3),
                            "language": language,
                            "timestamp": datetime.utcnow().isoformat(),
                            "fallback_reason": "GPU error"
                        })

                        return result
                except Exception as fallback_error:
                    logger.error("fallback_also_failed", error=str(fallback_error), exc_info=True)

            # Return error response
            return {
                "success": False,
                "error": str(e),
                "metadata": {
                    "processing_time_seconds": (datetime.utcnow() - start_time).total_seconds(),
                    "timestamp": datetime.utcnow().isoformat()
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
        Process multiple documents in batch

        Args:
            image_paths: List of image file paths
            backend: Backend to use (or "auto")
            language: Target language
            max_concurrent: Maximum concurrent processing

        Returns:
            List of OCR results
        """
        logger.info("batch_processing_starting", document_count=len(image_paths))

        # Create semaphore to limit concurrent processing
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(path: str) -> Dict[str, Any]:
            async with semaphore:
                return await self.process_document(
                    image_path=path,
                    backend=backend,
                    language=language
                )

        # Process all documents concurrently (limited by semaphore)
        tasks = [process_with_semaphore(path) for path in image_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to error results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "success": False,
                    "error": str(result),
                    "image_path": image_paths[i]
                })
            else:
                result["image_path"] = image_paths[i]
                processed_results.append(result)

        successful = sum(1 for r in processed_results if r.get("success", False))
        logger.info("batch_processing_complete", successful=successful, total=len(image_paths))

        return processed_results

    async def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            "total_processed": self.processing_stats["total_processed"],
            "total_errors": self.processing_stats["total_errors"],
            "success_rate": (
                self.processing_stats["total_processed"] /
                max(1, self.processing_stats["total_processed"] + self.processing_stats["total_errors"])
            ),
            "by_backend": self.processing_stats["by_backend"],
            "available_backends": self.backend_manager.get_available_backends(),
            "backend_status": await self.backend_manager.get_backend_status()
        }

    async def validate_german_text(self, text: str) -> Dict[str, Any]:
        """
        Validate German text quality

        Args:
            text: Text to validate

        Returns:
            Validation results with issues and suggestions
        """
        from app.german_validator import GermanValidator

        validator = GermanValidator()

        # Check various aspects
        has_umlauts = validator.validate_umlauts(text)
        dates = validator.validate_date_format(text)
        amounts = validator.validate_currency_format(text)
        terms = validator.extract_business_terms(text)

        # Count potential OCR errors
        ocr_errors = []
        for pattern, replacements in validator.OCR_ERROR_PATTERNS.items():
            for replacement in replacements:
                if replacement in text and pattern not in text:
                    ocr_errors.append({
                        "found": replacement,
                        "suggested": pattern,
                        "count": text.count(replacement)
                    })

        return {
            "valid": has_umlauts or len(dates) > 0 or len(amounts) > 0,
            "has_umlauts": has_umlauts,
            "dates_found": dates,
            "amounts_found": amounts,
            "business_terms": terms,
            "potential_ocr_errors": ocr_errors,
            "quality_score": 1.0 - (len(ocr_errors) * 0.1)  # Simple quality metric
        }

    async def save_upload(self, file_content: bytes, filename: str) -> str:
        """
        Save uploaded file to local storage

        Args:
            file_content: File content as bytes
            filename: Original filename

        Returns:
            Path to saved file
        """
        # Generate unique filename with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{filename}"
        file_path = self.upload_dir / safe_filename

        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)

        logger.info("upload_saved", file_path=str(file_path))
        return str(file_path)

    async def cleanup(self):
        """Clean up resources"""
        await self.backend_manager.cleanup()
        logger.info("ocr_service_cleanup_complete")