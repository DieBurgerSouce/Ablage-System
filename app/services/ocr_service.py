"""
OCR Service - Central OCR Processing Layer
Integrates backend manager with FastAPI
Priority: P0 - CRITICAL
Created: 2024-11-22
"""

import structlog
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime, timezone
import asyncio
import os

logger = structlog.get_logger(__name__)

# Import our backend manager (Singleton für Performance)
from app.services.backend_manager import get_backend_manager
# Import German correction components
from app.agents.postprocessing.german_correction_agent import GermanCorrectionAgent
from app.utils.german_text import normalize_german_text


class OCRService:
    """
    Central OCR Service
    Provides high-level OCR processing interface for FastAPI
    """

    # Timeout for batch operations to prevent hanging (5 minutes per batch)
    BATCH_TIMEOUT_SECONDS = 300.0

    def __init__(self, enable_german_correction: bool = True):
        """Initialize OCR service with backend manager

        Args:
            enable_german_correction: Enable automatic German text correction (default: True)
        """
        # Verwende Singleton BackendManager für Performance
        # Das vermeidet ~60s Model-Loading bei jedem Task
        self.backend_manager = get_backend_manager()
        self.processing_stats = {
            "total_processed": 0,
            "total_errors": 0,
            "total_fallbacks": 0,
            "total_corrections": 0,
            "total_correction_errors": 0,  # P2: Track German correction failures
            "by_backend": {},
            "health_checks": {
                "total": 0,
                "healthy": 0,
                "unhealthy": 0
            }
        }

        # Initialize German correction agent
        self._enable_german_correction = enable_german_correction
        self._german_corrector: Optional[GermanCorrectionAgent] = None
        if enable_german_correction:
            try:
                self._german_corrector = GermanCorrectionAgent(enable_languagetool=True)
                logger.info("german_correction_agent_initialized")
            except Exception as e:
                logger.warning(
                    "german_correction_agent_init_failed",
                    error=str(e),
                    message="Korrektur deaktiviert"
                )

        # Create upload directory if it doesn't exist
        self.upload_dir = Path("uploads")
        self.upload_dir.mkdir(exist_ok=True)

        logger.info(
            "ocr_service_initialized",
            available_backends=self.backend_manager.get_available_backends(),
            german_correction_enabled=self._german_corrector is not None
        )

    async def process_document(
        self,
        image_path: str,
        backend: Optional[str] = None,
        language: str = "de",
        detect_layout: bool = True,
        detect_fraktur: bool = False,
        document_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process document with OCR

        Args:
            image_path: Path to image file
            backend: Backend to use ("auto", "deepseek", "got_ocr", "surya")
            language: Target language ("de", "en")
            detect_layout: Whether to perform layout detection
            detect_fraktur: Special handling for Fraktur fonts
            document_id: Optional document ID for A/B experiment allocation

        Returns:
            OCR result with extracted text and metadata
        """
        start_time = datetime.now(timezone.utc)

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
                    detect_layout=detect_layout,
                    document_id=document_id
                )
            else:
                # Validate requested backend is available
                if backend not in available_backends:
                    logger.warning("requested_backend_unavailable", requested=backend, available=available_backends)
                    # Fallback to auto-selection
                    selected_backend = await self.backend_manager.select_backend(
                        image_path=image_path,
                        language=language,
                        detect_layout=detect_layout,
                        document_id=document_id
                    )
                else:
                    selected_backend = backend

            logger.info(
                "processing_document",
                backend=selected_backend,
                image_path=image_path,
                language=language
            )

            # Process with selected backend (with automatic fallback enabled)
            result = await self.backend_manager.process_with_backend(
                backend_name=selected_backend,
                image_path=image_path,
                language=language,
                detect_fraktur=detect_fraktur,
                enable_fallback=True,  # Enable automatic fallback chain
                enable_layout=detect_layout
            )

            # Apply German correction for German documents
            correction_applied = False
            correction_result = None
            # Guard clause: Explizite None-Pruefung fuer Type Safety
            if language == "de" and self._german_corrector is not None and result.get("text"):
                try:
                    logger.info(
                        "applying_german_correction",
                        text_length=len(result["text"]),
                        image_path=image_path
                    )

                    # Run German correction agent
                    correction_result = await self._german_corrector.process({
                        "text": result["text"],
                        "options": {
                            "skip_languagetool": False,
                            "skip_fuzzy_matching": False,
                            "skip_compound_validation": False,
                        }
                    })

                    # Apply corrected text
                    if correction_result.get("text"):
                        original_text = result["text"]
                        result["text"] = correction_result["text"]

                        # Normalize German text (Unicode NFC, whitespace)
                        result["text"] = normalize_german_text(result["text"])

                        correction_applied = True
                        self.processing_stats["total_corrections"] += 1

                        logger.info(
                            "german_correction_applied",
                            corrections_count=correction_result.get("corrections_applied", 0),
                            umlauts_restored=correction_result.get("umlauts_restored", 0),
                            quality_score=correction_result.get("validation_score", 0),
                            text_changed=original_text != result["text"]
                        )

                except Exception as e:
                    # P2: Track correction errors for monitoring
                    self.processing_stats["total_correction_errors"] += 1

                    logger.warning(
                        "german_correction_failed",
                        error_type=type(e).__name__,
                        error=str(e),
                        text_length=len(result.get("text", "")),
                        total_correction_errors=self.processing_stats["total_correction_errors"],
                        message="Korrektur übersprungen, Originaltext beibehalten"
                    )

            # Add processing metadata
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Ensure we have a proper result structure
            if "metadata" not in result:
                result["metadata"] = {}

            # Track fallback usage
            actual_backend = result.get("backend", selected_backend)
            if result.get("fallback_used"):
                self.processing_stats["total_fallbacks"] += 1
                logger.info(
                    "fallback_used",
                    original=result.get("original_backend"),
                    actual=actual_backend
                )

            result["metadata"].update({
                "backend_used": actual_backend,
                "backend_requested": selected_backend,
                "fallback_used": result.get("fallback_used", False),
                "processing_time_seconds": round(processing_time, 3),
                "language": language,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "german_correction_applied": correction_applied,
            })

            # Add German correction details if applied
            if correction_applied and correction_result:
                result["metadata"]["german_correction"] = {
                    "corrections_count": correction_result.get("corrections_applied", 0),
                    "umlauts_restored": correction_result.get("umlauts_restored", 0),
                    "quality_score": correction_result.get("validation_score", 0),
                    "domain_detected": correction_result.get("domain_detected"),
                }

            # Update stats
            self.processing_stats["total_processed"] += 1
            backend_stats = self.processing_stats["by_backend"].get(actual_backend, 0)
            self.processing_stats["by_backend"][actual_backend] = backend_stats + 1

            # Add success flag if not present
            if "success" not in result:
                result["success"] = True

            return result

        except Exception as e:
            self.processing_stats["total_errors"] += 1
            logger.error("ocr_processing_failed", error=str(e), exc_info=True)

            # Return error response (fallback already attempted by backend_manager)
            return {
                "success": False,
                "error": str(e),
                "metadata": {
                    "processing_time_seconds": (datetime.now(timezone.utc) - start_time).total_seconds(),
                    "timestamp": datetime.now(timezone.utc).isoformat()
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
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.BATCH_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.error(
                "batch_processing_timeout",
                document_count=len(image_paths),
                timeout_seconds=self.BATCH_TIMEOUT_SECONDS
            )
            # Return timeout errors for all documents
            results = [
                TimeoutError(f"Batch-Timeout nach {self.BATCH_TIMEOUT_SECONDS}s")
                for _ in image_paths
            ]

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
        total_processed = self.processing_stats["total_processed"]
        total_errors = self.processing_stats["total_errors"]
        total_corrections = self.processing_stats["total_corrections"]

        return {
            "total_processed": total_processed,
            "total_errors": total_errors,
            "total_fallbacks": self.processing_stats["total_fallbacks"],
            "total_corrections": total_corrections,
            "success_rate": (
                total_processed /
                max(1, total_processed + total_errors)
            ),
            "fallback_rate": (
                self.processing_stats["total_fallbacks"] /
                max(1, total_processed)
            ),
            "correction_rate": (
                total_corrections /
                max(1, total_processed)
            ),
            "by_backend": self.processing_stats["by_backend"],
            "health_checks": self.processing_stats["health_checks"],
            "available_backends": self.backend_manager.get_available_backends(),
            "backend_status": await self.backend_manager.get_backend_status(),
            "german_correction_enabled": self._german_corrector is not None,
        }

    async def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status of all OCR backends.

        Returns:
            Health status including:
            - overall_healthy: True if at least one backend is healthy
            - backends: Dict of backend name -> health status
            - healthy_count: Number of healthy backends
            - unhealthy_count: Number of unhealthy backends
            - fallback_available: True if CPU fallback is available
        """
        self.processing_stats["health_checks"]["total"] += 1

        backends = self.backend_manager.get_available_backends()
        health_results = {}
        healthy_count = 0
        unhealthy_count = 0

        for backend_name in backends:
            health = await self.backend_manager.check_backend_health(backend_name)
            health_results[backend_name] = health

            if health.get("healthy"):
                healthy_count += 1
                self.processing_stats["health_checks"]["healthy"] += 1
            else:
                unhealthy_count += 1
                self.processing_stats["health_checks"]["unhealthy"] += 1
                logger.warning(
                    "backend_unhealthy",
                    backend=backend_name,
                    reason=health.get("reason")
                )

        # Check if CPU fallback is available
        fallback_available = "surya" in backends
        if fallback_available:
            surya_health = health_results.get("surya", {})
            fallback_available = surya_health.get("healthy", False)

        overall_healthy = healthy_count > 0

        if not overall_healthy:
            logger.error("all_backends_unhealthy", backends=list(health_results.keys()))

        return {
            "overall_healthy": overall_healthy,
            "backends": health_results,
            "healthy_count": healthy_count,
            "unhealthy_count": unhealthy_count,
            "total_backends": len(backends),
            "fallback_available": fallback_available,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def check_backend_health(self, backend_name: str) -> Dict[str, Any]:
        """
        Check health of a specific backend.

        Args:
            backend_name: Name of the backend to check

        Returns:
            Health status for the specified backend
        """
        self.processing_stats["health_checks"]["total"] += 1

        health = await self.backend_manager.check_backend_health(backend_name)

        if health.get("healthy"):
            self.processing_stats["health_checks"]["healthy"] += 1
        else:
            self.processing_stats["health_checks"]["unhealthy"] += 1

        return health

    async def get_recommended_backend(
        self,
        image_path: Optional[str] = None,
        language: str = "de",
        prefer_gpu: bool = True
    ) -> Dict[str, Any]:
        """
        Get recommended backend based on current health and workload.

        Args:
            image_path: Optional path to document (for size-based selection)
            language: Target language
            prefer_gpu: Whether to prefer GPU backends

        Returns:
            Recommendation with backend name and reasoning
        """
        # Get health status first
        health_status = await self.get_health_status()

        if not health_status["overall_healthy"]:
            return {
                "recommended": None,
                "reason": "Keine gesunden Backends verfügbar",
                "health_status": health_status
            }

        # Find healthy backends
        healthy_backends = [
            name for name, health in health_status["backends"].items()
            if health.get("healthy")
        ]

        # Priority order based on preferences
        if prefer_gpu:
            priority = ["deepseek", "got_ocr", "surya_gpu", "surya"]
        else:
            priority = ["surya", "surya_gpu", "got_ocr", "deepseek"]

        # Select first healthy backend in priority order
        for backend in priority:
            if backend in healthy_backends:
                return {
                    "recommended": backend,
                    "reason": f"Gesundes Backend mit {'GPU' if prefer_gpu else 'CPU'}-Präferenz",
                    "healthy_backends": healthy_backends,
                    "health_status": health_status
                }

        # Fallback to first available healthy backend
        return {
            "recommended": healthy_backends[0] if healthy_backends else None,
            "reason": "Erstes verfügbares gesundes Backend",
            "healthy_backends": healthy_backends,
            "health_status": health_status
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
        umlaut_result = validator.validate_umlauts(text)
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

        # Determine if text contains German indicators
        has_german_indicators = (
            len(umlaut_result.get("umlauts_found", [])) > 0
            or len(dates) > 0
            or len(amounts) > 0
        )

        return {
            "valid": has_german_indicators,
            "umlaut_validation": umlaut_result,
            "dates_found": dates,
            "amounts_found": amounts,
            "business_terms": terms,
            "potential_ocr_errors": ocr_errors,
            "quality_score": max(0.0, 1.0 - (len(ocr_errors) * 0.1))
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
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_filename = f"{timestamp}_{filename}"
        file_path = self.upload_dir / safe_filename

        # Save file
        with open(file_path, "wb") as f:
            f.write(file_content)

        logger.info("upload_saved", file_path=str(file_path))
        return str(file_path)

    async def save_ocr_version(
        self,
        db: "AsyncSession",
        document_id: str,
        ocr_result: Dict[str, Any],
        user_id: Optional[str] = None,
        version_note: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Save OCR result as a new version.

        Creates a version entry for the given document with the OCR results.
        This enables version history tracking, comparison, and rollback.

        Args:
            db: Database session
            document_id: Document UUID
            ocr_result: OCR result dictionary from process_document
            user_id: User ID who triggered the OCR
            version_note: Optional note for this version

        Returns:
            Version info dictionary or None if failed
        """
        try:
            from uuid import UUID
            from app.services.version_service import get_version_service

            version_service = get_version_service()

            doc_uuid = UUID(document_id) if isinstance(document_id, str) else document_id
            user_uuid = UUID(user_id) if user_id else None

            version = await version_service.create_version_from_dict(
                db=db,
                document_id=doc_uuid,
                ocr_data=ocr_result,
                user_id=user_uuid,
                version_note=version_note
            )

            logger.info(
                "ocr_version_saved",
                document_id=document_id,
                version_number=version.version_number,
                backend=version.backend
            )

            return {
                "version_id": str(version.id),
                "version_number": version.version_number,
                "backend": version.backend,
                "is_current": version.is_current,
                "created_at": version.created_at.isoformat() if version.created_at else None
            }

        except Exception as e:
            logger.error(
                "ocr_version_save_failed",
                document_id=document_id,
                error=str(e)
            )
            return None

    async def cleanup(self):
        """Clean up resources"""
        await self.backend_manager.cleanup()
        logger.info("ocr_service_cleanup_complete")