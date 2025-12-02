"""OCR processing tasks for Celery.

This module contains all async OCR processing tasks including:
- Single document OCR processing
- Batch document processing
- German text validation
- Metadata extraction
- System maintenance tasks
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from uuid import UUID
import asyncio
import psutil
import torch

import structlog
from celery import states
from celery.exceptions import SoftTimeLimitExceeded, Ignore
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete

from app.workers.celery_app import celery_app, GPUTask, CPUTask, gpu_memory_guard
from app.core.config import settings
from app.db.models import Document, ProcessingJob, OCRResult, ProcessingStatus, SystemMetrics, BatchJob
from app.services.ocr_service import OCRService
from app.german_validator import GermanValidator

# GPU Recovery und strukturierte Exceptions
from app.core.gpu_recovery import (
    GPURecoveryManager,
    get_gpu_recovery_manager,
    BACKEND_CONFIGS,
)
from app.core.exceptions import (
    GPUOutOfMemoryError,
    GPUNotAvailableError,
    OCRProcessingError,
    OCRBackendTimeoutError,
)

# Import embedding task for auto-generation after OCR
from app.workers.tasks.embedding_tasks import generate_document_embedding

# Import ML tracking for A/B testing and metrics
from app.workers.tasks.ml_tasks import ml_tracker

# Import Cache Invalidation für Document/Search Caches
from app.core.cache import invalidate_on_document_change

logger = structlog.get_logger(__name__)

# Database session factory mit Worker-optimiertem Connection Pool
# Worker brauchen weniger Connections, aber längere Timeouts für lange Tasks
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_WORKER_POOL_SIZE,
    max_overflow=settings.DB_WORKER_MAX_OVERFLOW,
    pool_recycle=settings.DB_WORKER_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=False,  # Kein SQL-Logging in Production
)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# GPU Recovery Manager (global für Worker)
_gpu_recovery_manager: Optional[GPURecoveryManager] = None


def get_worker_gpu_recovery_manager() -> GPURecoveryManager:
    """Get worker-local GPU recovery manager."""
    global _gpu_recovery_manager
    if _gpu_recovery_manager is None:
        _gpu_recovery_manager = GPURecoveryManager()
    return _gpu_recovery_manager


def _is_oom_error(exception: Exception) -> bool:
    """Prüfe ob Exception ein GPU OOM Error ist."""
    if torch.cuda.is_available() and isinstance(exception, torch.cuda.OutOfMemoryError):
        return True

    error_msg = str(exception).lower()
    oom_indicators = [
        "out of memory",
        "cuda out of memory",
        "oom",
        "memory allocation",
        "cannot allocate",
    ]
    return any(indicator in error_msg for indicator in oom_indicators)


# ==================== Helper Functions ====================

async def get_db_session() -> AsyncSession:
    """Get async database session."""
    return async_session_maker()


async def update_document_status(
    session: AsyncSession,
    document_id: UUID,
    status: ProcessingStatus,
    **kwargs: Any
) -> None:
    """Update document processing status.

    Args:
        session: Database session
        document_id: Document UUID
        status: New processing status
        **kwargs: Additional fields to update
    """
    result = await session.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if document:
        document.status = status
        for key, value in kwargs.items():
            if hasattr(document, key):
                setattr(document, key, value)
        await session.commit()
        logger.info(
            "document_status_updated",
            document_id=str(document_id),
            status=status,
            **kwargs
        )


async def update_job_status(
    session: AsyncSession,
    job_id: UUID,
    status: ProcessingStatus,
    **kwargs: Any
) -> None:
    """Update processing job status.

    Args:
        session: Database session
        job_id: Job UUID
        status: New processing status
        **kwargs: Additional fields to update
    """
    result = await session.execute(
        select(ProcessingJob).where(ProcessingJob.id == job_id)
    )
    job = result.scalar_one_or_none()

    if job:
        job.status = status
        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)
        await session.commit()
        logger.info(
            "job_status_updated",
            job_id=str(job_id),
            status=status,
            **kwargs
        )


def update_task_progress(task_id: str, current: int, total: int, message: str) -> None:
    """Update task progress for real-time monitoring.

    Args:
        task_id: Celery task ID
        current: Current progress value
        total: Total progress value
        message: Progress message (German)
    """
    progress = int((current / total) * 100) if total > 0 else 0
    celery_app.backend.store_result(
        task_id,
        {
            "current": current,
            "total": total,
            "progress": progress,
            "message": message,
        },
        states.STARTED,
    )


# ==================== OCR Processing Tasks ====================

@celery_app.task(bind=True, base=GPUTask, name="app.workers.tasks.ocr_tasks.process_document_task")
def process_document_task(
    self,
    document_id: str,
    backend: str = "auto",
    language: str = "de",
    detect_layout: bool = True,
    detect_fraktur: bool = False,
    priority: str = "normal"
) -> Dict[str, Any]:
    """Process a single document with OCR.

    This is the main OCR processing task that handles document recognition.
    Supports GPU acceleration with automatic fallback to CPU if needed.

    Args:
        document_id: Document UUID as string
        backend: OCR backend to use (auto, deepseek, got_ocr, surya, surya_gpu)
        language: Target language (de, en)
        detect_layout: Whether to detect document layout
        detect_fraktur: Enable Fraktur font detection for German documents
        priority: Task priority (high, normal, low)

    Returns:
        Dictionary with OCR results, metadata, and processing information
    """
    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)
    task_id = self.request.id

    logger.info(
        "ocr_task_starting",
        task_id=task_id,
        document_id=document_id,
        backend=backend,
        language=language,
        priority=priority
    )

    # Initialize services
    ocr_service = OCRService()
    german_validator = GermanValidator()

    async def process_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            try:
                # Update initial status
                update_task_progress(task_id, 0, 100, "Dokument wird geladen...")
                await update_document_status(
                    session, doc_uuid, ProcessingStatus.PROCESSING
                )

                # Get document from database
                result = await session.execute(
                    select(Document).where(Document.id == doc_uuid)
                )
                document = result.scalar_one_or_none()

                if not document:
                    raise ValueError(f"Dokument {document_id} nicht gefunden")

                if not document.file_path or not Path(document.file_path).exists():
                    raise FileNotFoundError(
                        f"Dokumentdatei nicht gefunden: {document.file_path}"
                    )

                # Start OCR processing
                update_task_progress(task_id, 20, 100, "OCR-Verarbeitung läuft...")

                ocr_result = await ocr_service.process_document(
                    image_path=document.file_path,
                    backend=backend,
                    language=language,
                    detect_layout=detect_layout,
                    detect_fraktur=detect_fraktur,
                    document_id=document_id  # For A/B experiment allocation
                )

                if not ocr_result.get("success"):
                    raise RuntimeError(
                        f"OCR fehlgeschlagen: {ocr_result.get('error', 'Unbekannter Fehler')}"
                    )

                # German text validation for German documents
                validation_result = None
                if language == "de" and ocr_result.get("text"):
                    update_task_progress(
                        task_id, 70, 100, "Deutsche Textvalidierung..."
                    )
                    validation_result = await ocr_service.validate_german_text(
                        ocr_result["text"]
                    )

                # Calculate processing duration
                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                processing_ms = int(processing_time * 1000)

                # Update document with OCR results
                update_task_progress(task_id, 90, 100, "Speichere Ergebnisse...")

                document.extracted_text = ocr_result.get("text", "")
                document.ocr_backend_used = ocr_result.get("metadata", {}).get(
                    "backend_used", backend
                )
                document.ocr_confidence = ocr_result.get("confidence", 0.0)
                document.processing_duration_ms = processing_ms
                document.processed_date = datetime.now(timezone.utc)
                document.status = ProcessingStatus.COMPLETED

                # German validation scores
                if validation_result:
                    document.has_umlauts = validation_result.get("has_umlauts", False)
                    document.german_validation_score = validation_result.get(
                        "quality_score", 0.0
                    )
                    document.detected_language = language

                # Create detailed OCR result record
                ocr_result_record = OCRResult(
                    document_id=doc_uuid,
                    backend=ocr_result.get("metadata", {}).get("backend_used", backend),
                    extracted_text=ocr_result.get("text", ""),
                    confidence_score=ocr_result.get("confidence", 0.0),
                    word_count=len(ocr_result.get("text", "").split()),
                    char_count=len(ocr_result.get("text", "")),
                    detected_layout=ocr_result.get("layout", {}),
                    bounding_boxes=ocr_result.get("bounding_boxes", []),
                    page_number=1,
                    processing_time_ms=processing_ms,
                )

                # Add German-specific data if validated
                if validation_result:
                    ocr_result_record.detected_dates = validation_result.get(
                        "dates_found", []
                    )
                    ocr_result_record.detected_amounts = validation_result.get(
                        "amounts_found", []
                    )
                    ocr_result_record.business_terms = validation_result.get(
                        "business_terms", []
                    )

                session.add(ocr_result_record)
                await session.commit()

                # Cache Invalidation: Dokument wurde verarbeitet, Caches müssen aktualisiert werden
                try:
                    cache_result = await invalidate_on_document_change(
                        document_id=document_id,
                        change_type="ocr"
                    )
                    logger.debug(
                        "ocr_cache_invalidated",
                        document_id=document_id,
                        invalidated_keys=cache_result.get("total", 0)
                    )
                except Exception as cache_error:
                    # Cache-Invalidation sollte OCR-Erfolg nicht blockieren
                    logger.warning(
                        "ocr_cache_invalidation_failed",
                        document_id=document_id,
                        error=str(cache_error)
                    )

                update_task_progress(task_id, 100, 100, "Verarbeitung abgeschlossen!")

                logger.info(
                    "ocr_task_completed",
                    task_id=task_id,
                    document_id=document_id,
                    backend=document.ocr_backend_used,
                    duration_ms=processing_ms,
                    text_length=len(document.extracted_text),
                    confidence=document.ocr_confidence
                )

                # Track OCR result for A/B testing and metrics
                ml_tracker.track_ocr_result(
                    document_id=document_id,
                    backend=document.ocr_backend_used,
                    success=True,
                    processing_time_ms=float(processing_ms),
                    accuracy=document.ocr_confidence,
                    language=language,
                    document_type=document.document_type or "unknown",
                )

                # Record OCR quality metrics for monitoring
                try:
                    from app.services.ocr_quality_metrics_service import record_ocr_quality

                    await record_ocr_quality(
                        backend=document.ocr_backend_used,
                        confidence=document.ocr_confidence,
                        processing_time_ms=float(processing_ms),
                        has_umlauts=document.has_umlauts if hasattr(document, 'has_umlauts') else False,
                        german_quality_score=document.german_validation_score if hasattr(document, 'german_validation_score') else 1.0,
                        document_type=document.document_type or "unknown",
                    )
                except Exception as quality_error:
                    # Don't fail OCR if quality metrics recording fails
                    logger.warning(
                        "ocr_quality_metrics_failed",
                        document_id=document_id,
                        error=str(quality_error)
                    )

                # Queue embedding generation as low-priority background task
                embedding_task_id = None
                if settings.EMBEDDING_AUTO_GENERATE and document.extracted_text:
                    try:
                        result = generate_document_embedding.apply_async(
                            args=[document_id],
                            countdown=settings.EMBEDDING_TASK_DELAY_SECONDS,
                            priority=settings.EMBEDDING_TASK_PRIORITY,
                        )
                        embedding_task_id = result.id
                        logger.info(
                            "embedding_task_queued",
                            task_id=task_id,
                            document_id=document_id,
                            embedding_task_id=embedding_task_id,
                            delay_seconds=settings.EMBEDDING_TASK_DELAY_SECONDS
                        )
                    except Exception as e:
                        # Don't fail OCR if embedding queuing fails
                        logger.warning(
                            "embedding_task_queue_failed",
                            task_id=task_id,
                            document_id=document_id,
                            error=str(e)
                        )

                return {
                    "success": True,
                    "document_id": document_id,
                    "text": document.extracted_text,
                    "confidence": document.ocr_confidence,
                    "backend_used": document.ocr_backend_used,
                    "processing_time_ms": processing_ms,
                    "word_count": len(document.extracted_text.split()),
                    "german_validation": validation_result,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "embedding_task_id": embedding_task_id,
                }

            except SoftTimeLimitExceeded:
                # Timeout: CPU-Fallback versuchen wenn GPU-Backend verwendet wurde
                gpu_backends = ["deepseek", "got_ocr", "surya_gpu"]
                actual_backend = backend if backend != "auto" else "unknown"

                logger.warning(
                    "ocr_task_timeout_attempting_cpu_fallback",
                    task_id=task_id,
                    document_id=document_id,
                    backend=actual_backend
                )

                # CPU-Fallback nur wenn GPU-Backend verwendet wurde
                if actual_backend in gpu_backends:
                    try:
                        update_task_progress(
                            task_id, 30, 100,
                            "GPU-Timeout - wechsle zu CPU-Backend..."
                        )

                        # Surya-CPU als Fallback
                        ocr_result = await ocr_service.process_document(
                            image_path=document.file_path,
                            backend="surya",  # CPU-Backend
                            language=language,
                            detect_layout=detect_layout,
                            detect_fraktur=detect_fraktur,
                            document_id=document_id
                        )

                        if ocr_result.get("success"):
                            logger.info(
                                "ocr_cpu_fallback_success",
                                task_id=task_id,
                                document_id=document_id
                            )
                            # Weiterverarbeitung mit CPU-Ergebnis...
                            document.extracted_text = ocr_result.get("text", "")
                            document.ocr_backend_used = "surya_cpu_fallback"
                            document.ocr_confidence = ocr_result.get("confidence", 0.0)
                            document.status = ProcessingStatus.COMPLETED
                            document.processed_date = datetime.now(timezone.utc)
                            await session.commit()

                            # Record quality metrics for fallback
                            try:
                                from app.services.ocr_quality_metrics_service import record_ocr_quality
                                fallback_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                                await record_ocr_quality(
                                    backend="surya_cpu_fallback",
                                    confidence=document.ocr_confidence,
                                    processing_time_ms=float(fallback_time),
                                    document_type="unknown",
                                )
                            except Exception:
                                pass  # Non-critical

                            return {
                                "success": True,
                                "document_id": document_id,
                                "text": document.extracted_text,
                                "confidence": document.ocr_confidence,
                                "backend_used": "surya_cpu_fallback",
                                "fallback_reason": "gpu_timeout",
                            }
                    except Exception as fallback_error:
                        logger.error(
                            "ocr_cpu_fallback_failed",
                            task_id=task_id,
                            document_id=document_id,
                            error=str(fallback_error)
                        )

                # Wenn kein Fallback möglich oder Fallback fehlgeschlagen
                await update_document_status(
                    session,
                    doc_uuid,
                    ProcessingStatus.FAILED,
                    error_message="Zeitüberschreitung bei der Verarbeitung"
                )
                raise OCRBackendTimeoutError(
                    backend=actual_backend,
                    timeout_seconds=int(getattr(settings, 'OCR_TIMEOUT_SECONDS', 300))
                )

            except Exception as e:
                # GPU OOM spezifisch behandeln
                if _is_oom_error(e):
                    gpu_manager = get_worker_gpu_recovery_manager()
                    memory_stats = gpu_manager.get_memory_stats()

                    logger.warning(
                        "ocr_task_gpu_oom",
                        task_id=task_id,
                        document_id=document_id,
                        gpu_allocated_gb=memory_stats.allocated_gb,
                        gpu_total_gb=memory_stats.total_gb,
                        backend=backend
                    )

                    # GPU-Speicher aufräumen
                    await gpu_manager.clear_gpu_memory()

                    # Retry-Zähler prüfen (Celery's retry-Mechanismus)
                    retry_count = self.request.retries
                    max_retries = getattr(self, 'max_retries', 3)

                    if retry_count < max_retries:
                        # Kleinere Batch-Size für nächsten Versuch im Backend-Config
                        reduced_config = BACKEND_CONFIGS.get(backend)
                        if reduced_config:
                            current_batch = reduced_config.default_batch_size
                            new_batch = max(1, int(current_batch * 0.5))
                            logger.info(
                                "ocr_task_reducing_batch_size",
                                task_id=task_id,
                                old_batch=current_batch,
                                new_batch=new_batch
                            )

                        # Retry mit Exponential Backoff
                        countdown = 60 * (2 ** retry_count)  # 60s, 120s, 240s
                        logger.info(
                            "ocr_task_scheduling_retry",
                            task_id=task_id,
                            retry_count=retry_count + 1,
                            countdown_seconds=countdown
                        )
                        raise self.retry(exc=e, countdown=countdown)
                    else:
                        # Max retries erreicht - als GPU OOM Error melden
                        raise GPUOutOfMemoryError(
                            message=f"GPU OOM nach {max_retries} Versuchen für Dokument {document_id}",
                            required_gb=memory_stats.allocated_gb + 2.0,  # Geschätzt
                            available_gb=memory_stats.total_gb - memory_stats.allocated_gb
                        )

                # Andere Exceptions normal behandeln
                logger.exception(
                    "ocr_task_failed",
                    task_id=task_id,
                    document_id=document_id,
                    error=str(e)
                )

                # Track failed OCR for A/B testing and metrics
                processing_time_failed = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                ml_tracker.track_ocr_result(
                    document_id=document_id,
                    backend=backend,
                    success=False,
                    processing_time_ms=float(processing_time_failed),
                    accuracy=None,
                    language=language,
                    document_type="unknown",
                )

                await update_document_status(
                    session,
                    doc_uuid,
                    ProcessingStatus.FAILED,
                    error_message=str(e)
                )
                raise OCRProcessingError(
                    document_id=document_id,
                    backend=backend,
                    reason=str(e)
                )

            finally:
                # GPU-Speicher immer aufräumen nach Verarbeitung
                if torch.cuda.is_available():
                    try:
                        torch.cuda.empty_cache()
                    except Exception as cleanup_error:
                        logger.warning(
                            "gpu_cleanup_failed",
                            task_id=task_id,
                            error=str(cleanup_error)
                        )

    # Run async processing - use asyncio.run() for automatic cleanup
    return asyncio.run(process_async())


@celery_app.task(bind=True, base=GPUTask, name="app.workers.tasks.ocr_tasks.batch_process_task")
def batch_process_task(
    self,
    document_ids: List[str],
    backend: str = "auto",
    language: str = "de",
    max_concurrent: int = 1,  # GPU tasks must be sequential
    batch_job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    resume_from_index: int = 0
) -> Dict[str, Any]:
    """Process multiple documents in batch.

    Args:
        document_ids: List of document UUIDs as strings
        backend: OCR backend to use
        language: Target language
        max_concurrent: Maximum concurrent processing (GPU: 1, CPU: 3)
        batch_job_id: Optional BatchJob ID for tracking
        user_id: User ID for BatchJob updates
        resume_from_index: Index to resume from (for paused jobs)

    Returns:
        Dictionary with batch processing results
    """
    # Validate batch size to prevent resource abuse
    MAX_BATCH_SIZE = 500
    if len(document_ids) > MAX_BATCH_SIZE:
        raise ValueError(
            f"Batch zu gross: maximal {MAX_BATCH_SIZE} Dokumente pro Batch, "
            f"erhalten: {len(document_ids)}"
        )

    task_id = self.request.id
    start_time = datetime.now(timezone.utc)
    total_docs = len(document_ids)

    logger.info(
        "batch_task_starting",
        task_id=task_id,
        document_count=total_docs,
        backend=backend,
        batch_job_id=batch_job_id,
        resume_from=resume_from_index
    )

    results = []
    successful = 0
    failed = 0

    # Helper function to update BatchJob status
    async def update_batch_job_progress(processed: int, failed_count: int, current_doc: str):
        if batch_job_id:
            try:
                from app.services.batch_job_service import get_batch_job_service
                async with async_session_maker() as session:
                    service = get_batch_job_service()
                    await service.update_progress(
                        db=session,
                        batch_id=UUID(batch_job_id),
                        processed=processed,
                        failed=failed_count,
                        current_document=current_doc
                    )
            except Exception as e:
                logger.warning("batch_job_progress_update_failed", error=str(e))

    # Helper function to check if batch is paused
    async def check_batch_paused() -> bool:
        if not batch_job_id:
            return False
        try:
            async with async_session_maker() as session:
                from app.db.models import BatchJob
                result = await session.execute(
                    select(BatchJob).where(BatchJob.id == UUID(batch_job_id))
                )
                batch_job = result.scalar_one_or_none()
                return batch_job.is_paused if batch_job else False
        except Exception:
            return False

    # Start from resume index
    start_index = resume_from_index

    for idx, doc_id in enumerate(document_ids[start_index:], start=start_index):
        # Check if batch was paused
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            is_paused = loop.run_until_complete(check_batch_paused())
        finally:
            loop.close()

        if is_paused:
            logger.info(
                "batch_task_paused",
                task_id=task_id,
                batch_job_id=batch_job_id,
                paused_at_document=idx
            )
            break

        try:
            update_task_progress(
                task_id,
                idx,
                total_docs,
                f"Verarbeite Dokument {idx + 1}/{total_docs}..."
            )

            # Process individual document
            result = process_document_task(
                document_id=doc_id,
                backend=backend,
                language=language
            )

            if result.get("success"):
                successful += 1
            else:
                failed += 1

            results.append(result)

            # Update BatchJob progress
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(update_batch_job_progress(
                    idx + 1 - start_index + successful + failed - 1,
                    failed,
                    doc_id[:8]
                ))
            finally:
                loop.close()

        except Exception as e:
            # GPU OOM bei Batch-Verarbeitung: Speicher aufräumen, aber weitermachen
            if _is_oom_error(e):
                logger.warning(
                    "batch_document_gpu_oom",
                    task_id=task_id,
                    document_id=doc_id,
                    error=str(e)
                )

                # GPU-Speicher aufräumen vor nächstem Dokument
                if torch.cuda.is_available():
                    try:
                        gpu_manager = get_worker_gpu_recovery_manager()
                        asyncio.run(gpu_manager.clear_gpu_memory())
                    except Exception as cleanup_error:
                        logger.warning(
                            "batch_gpu_cleanup_failed",
                            error=str(cleanup_error)
                        )

                failed += 1
                results.append({
                    "success": False,
                    "document_id": doc_id,
                    "error": f"GPU Out of Memory: {str(e)}",
                    "error_type": "gpu_oom"
                })
            else:
                logger.error(
                    "batch_document_failed",
                    task_id=task_id,
                    document_id=doc_id,
                    error=str(e)
                )
                failed += 1
                results.append({
                    "success": False,
                    "document_id": doc_id,
                    "error": str(e),
                    "error_type": "processing_error"
                })

    # GPU-Speicher nach Batch-Verarbeitung aufräumen
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            logger.debug("batch_gpu_cleanup_complete", task_id=task_id)
        except Exception as cleanup_error:
            logger.warning("batch_gpu_final_cleanup_failed", error=str(cleanup_error))

    processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

    update_task_progress(
        task_id,
        total_docs,
        total_docs,
        f"Batch abgeschlossen: {successful}/{total_docs} erfolgreich"
    )

    logger.info(
        "batch_task_completed",
        task_id=task_id,
        total=total_docs,
        successful=successful,
        failed=failed,
        duration_seconds=processing_time
    )

    # Complete BatchJob
    if batch_job_id:
        async def complete_batch():
            try:
                from app.services.batch_job_service import get_batch_job_service
                async with async_session_maker() as session:
                    service = get_batch_job_service()
                    await service.complete_batch_job(
                        db=session,
                        batch_id=UUID(batch_job_id),
                        result_summary={
                            "total": total_docs,
                            "successful": successful,
                            "failed": failed,
                            "processing_time_seconds": processing_time
                        }
                    )
            except Exception as e:
                logger.warning("batch_job_completion_failed", error=str(e))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(complete_batch())
        finally:
            loop.close()

    # GPU OOM Statistiken sammeln
    gpu_oom_count = sum(1 for r in results if r.get("error_type") == "gpu_oom")
    gpu_recovery_stats = None
    if torch.cuda.is_available():
        try:
            gpu_manager = get_worker_gpu_recovery_manager()
            gpu_recovery_stats = gpu_manager.get_stats()
        except Exception as e:
            # GPU-Stats nicht kritisch für Batch-Ergebnis
            logger.debug("gpu_recovery_stats_failed", error=str(e))

    return {
        "success": True,
        "total_documents": total_docs,
        "successful": successful,
        "failed": failed,
        "gpu_oom_failures": gpu_oom_count,
        "results": results,
        "processing_time_seconds": processing_time,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "batch_job_id": batch_job_id,
        "gpu_recovery_stats": gpu_recovery_stats,
    }


@celery_app.task(bind=True, base=CPUTask, name="app.workers.tasks.ocr_tasks.validate_german_text_task")
def validate_german_text_task(
    self,
    text: str,
    document_id: Optional[str] = None
) -> Dict[str, Any]:
    """Validate German text quality.

    Args:
        text: Text to validate
        document_id: Optional document UUID for database updates

    Returns:
        Validation results with quality metrics
    """
    task_id = self.request.id
    validator = GermanValidator()

    logger.info(
        "validation_task_starting",
        task_id=task_id,
        document_id=document_id,
        text_length=len(text)
    )

    try:
        # Perform validation
        has_umlauts = validator.validate_umlauts(text)
        dates = validator.validate_date_format(text)
        amounts = validator.validate_currency_format(text)
        business_terms = validator.extract_business_terms(text)

        # Check for potential OCR errors
        ocr_errors = []
        for pattern, replacements in validator.OCR_ERROR_PATTERNS.items():
            for replacement in replacements:
                if replacement in text and pattern not in text:
                    ocr_errors.append({
                        "found": replacement,
                        "suggested": pattern,
                        "count": text.count(replacement)
                    })

        quality_score = 1.0 - (len(ocr_errors) * 0.1)
        quality_score = max(0.0, min(1.0, quality_score))

        result = {
            "valid": has_umlauts or len(dates) > 0 or len(amounts) > 0,
            "has_umlauts": has_umlauts,
            "dates_found": dates,
            "amounts_found": amounts,
            "business_terms": business_terms,
            "potential_ocr_errors": ocr_errors,
            "quality_score": quality_score,
            "text_length": len(text),
            "word_count": len(text.split())
        }

        # Update document if ID provided
        if document_id:
            async def update_doc():
                async with async_session_maker() as session:
                    await update_document_status(
                        session,
                        UUID(document_id),
                        ProcessingStatus.COMPLETED,
                        has_umlauts=has_umlauts,
                        german_validation_score=quality_score
                    )

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(update_doc())
            finally:
                loop.close()

        logger.info(
            "validation_task_completed",
            task_id=task_id,
            document_id=document_id,
            quality_score=quality_score
        )

        return result

    except Exception as e:
        logger.exception(
            "validation_task_failed",
            task_id=task_id,
            document_id=document_id,
            error=str(e)
        )
        raise


@celery_app.task(bind=True, base=CPUTask, name="app.workers.tasks.ocr_tasks.extract_metadata_task")
def extract_metadata_task(
    self,
    document_id: str
) -> Dict[str, Any]:
    """Extract metadata from processed document.

    Args:
        document_id: Document UUID as string

    Returns:
        Extracted metadata including dates, amounts, IBANs, etc.
    """
    task_id = self.request.id
    doc_uuid = UUID(document_id)
    validator = GermanValidator()

    logger.info(
        "metadata_extraction_starting",
        task_id=task_id,
        document_id=document_id
    )

    async def extract_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            # Get document
            result = await session.execute(
                select(Document).where(Document.id == doc_uuid)
            )
            document = result.scalar_one_or_none()

            if not document or not document.extracted_text:
                raise ValueError(
                    f"Dokument {document_id} nicht gefunden oder kein Text extrahiert"
                )

            text = document.extracted_text

            # Extract metadata
            metadata = {
                "dates": validator.validate_date_format(text),
                "amounts": validator.validate_currency_format(text),
                "business_terms": validator.extract_business_terms(text),
                "ibans": [],
                "vat_ids": [],
            }

            # Extract IBANs and VAT IDs
            words = text.split()
            for word in words:
                if word.startswith("DE") and len(word) == 22:
                    if validator.validate_iban(word):
                        metadata["ibans"].append(word)
                elif word.startswith("DE") and len(word) == 11:
                    if validator.validate_vat_id(word):
                        metadata["vat_ids"].append(word)

            # Update document metadata
            document.document_metadata = metadata
            await session.commit()

            logger.info(
                "metadata_extraction_completed",
                task_id=task_id,
                document_id=document_id,
                dates_count=len(metadata["dates"]),
                amounts_count=len(metadata["amounts"]),
                ibans_count=len(metadata["ibans"])
            )

            return metadata

    # Run async processing - use asyncio.run() for automatic cleanup
    return asyncio.run(extract_async())


# ==================== Maintenance Tasks ====================

@celery_app.task(bind=True, base=CPUTask, name="app.workers.tasks.ocr_tasks.cleanup_task")
def cleanup_task(self, hours_old: int = 24) -> Dict[str, Any]:
    """Clean up old task results and temporary files.

    Args:
        hours_old: Delete results older than this many hours

    Returns:
        Cleanup statistics
    """
    task_id = self.request.id
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_old)

    logger.info(
        "cleanup_task_starting",
        task_id=task_id,
        hours_old=hours_old,
        cutoff_time=cutoff_time.isoformat()
    )

    async def cleanup_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            # Delete old processing jobs
            result = await session.execute(
                delete(ProcessingJob).where(
                    ProcessingJob.completed_at < cutoff_time,
                    ProcessingJob.status.in_([
                        ProcessingStatus.COMPLETED,
                        ProcessingStatus.FAILED,
                        ProcessingStatus.CANCELLED
                    ])
                )
            )
            jobs_deleted = result.rowcount

            # Delete old system metrics
            result = await session.execute(
                delete(SystemMetrics).where(SystemMetrics.timestamp < cutoff_time)
            )
            metrics_deleted = result.rowcount

            await session.commit()

            # Clean up temporary files
            upload_dir = Path(settings.UPLOAD_DIR)
            temp_files_deleted = 0
            if upload_dir.exists():
                for file_path in upload_dir.glob("*"):
                    if file_path.is_file():
                        file_age = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if file_age < cutoff_time:
                            file_path.unlink()
                            temp_files_deleted += 1

            logger.info(
                "cleanup_task_completed",
                task_id=task_id,
                jobs_deleted=jobs_deleted,
                metrics_deleted=metrics_deleted,
                temp_files_deleted=temp_files_deleted
            )

            return {
                "success": True,
                "jobs_deleted": jobs_deleted,
                "metrics_deleted": metrics_deleted,
                "temp_files_deleted": temp_files_deleted,
                "cutoff_time": cutoff_time.isoformat(),
            }

    # Run async processing - use asyncio.run() for automatic cleanup
    return asyncio.run(cleanup_async())


# =============================================================================
# WORKFLOW TASK - Full document processing pipeline
# =============================================================================


@celery_app.task(bind=True, base=GPUTask, name="app.workers.tasks.ocr_tasks.process_document_workflow")
def process_document_workflow(
    self,
    document_id: str,
    file_path: str,
    priority: int = 0,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Execute complete document processing workflow.

    Orchestrates the full pipeline:
    1. Classification - Document type detection
    2. Pre-Processing - Image enhancement
    3. OCR - Text extraction
    4. Post-Processing - German text validation
    5. QA - Quality assurance
    6. Storage - Result persistence

    Args:
        document_id: Document UUID as string
        file_path: Path to document file
        priority: Processing priority (0=normal, higher=more urgent)
        options: Optional processing options

    Returns:
        Dictionary with complete workflow results
    """
    task_id = self.request.id
    options = options or {}

    logger.info(
        "workflow_task_starting",
        task_id=task_id,
        document_id=document_id,
        file_path=file_path,
        priority=priority
    )

    # Use process_document_task for the main processing
    # It already handles OCR + German validation + embedding generation
    result = process_document_task(
        document_id=document_id,
        backend=options.get("backend", "auto"),
        language=options.get("language", "de"),
        detect_layout=options.get("detect_layout", True),
        detect_fraktur=options.get("detect_fraktur", False),
        priority="high" if priority > 0 else "normal"
    )

    # Extract metadata after OCR if successful
    if result.get("success"):
        try:
            metadata_result = extract_metadata_task(document_id=document_id)
            result["metadata"] = metadata_result
        except Exception as e:
            logger.warning(
                "workflow_metadata_extraction_failed",
                task_id=task_id,
                document_id=document_id,
                error=str(e)
            )
            result["metadata"] = None

    logger.info(
        "workflow_task_completed",
        task_id=task_id,
        document_id=document_id,
        success=result.get("success", False)
    )

    return {
        "workflow": "full_processing",
        "task_id": task_id,
        **result
    }


# =============================================================================
# ALIASES FOR BACKWARDS COMPATIBILITY
# =============================================================================

# These aliases are used by app/api/v1/agents.py
process_document_gpu = process_document_task
batch_process_documents = batch_process_task


# ==================== System Metrics Task ====================


@celery_app.task(bind=True, base=CPUTask, name="app.workers.tasks.ocr_tasks.update_system_metrics")
def update_system_metrics(self) -> Dict[str, Any]:
    """Collect and store system performance metrics.

    Returns:
        Current system metrics
    """
    task_id = self.request.id

    # Collect metrics
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')

    metrics_data = {
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "memory_available_gb": memory.available / 1024**3,
        "disk_percent": disk.percent,
        "disk_free_gb": disk.free / 1024**3,
    }

    # GPU metrics if available
    if torch.cuda.is_available():
        gpu_memory_allocated = torch.cuda.memory_allocated() / 1024**3
        gpu_memory_reserved = torch.cuda.memory_reserved() / 1024**3
        gpu_memory_total = torch.cuda.get_device_properties(0).total_memory / 1024**3

        metrics_data.update({
            "gpu_memory_allocated_gb": gpu_memory_allocated,
            "gpu_memory_reserved_gb": gpu_memory_reserved,
            "gpu_memory_total_gb": gpu_memory_total,
            "gpu_memory_percent": (gpu_memory_allocated / gpu_memory_total) * 100,
        })

    async def store_metrics() -> Dict[str, Any]:
        async with async_session_maker() as session:
            # Store CPU metrics
            session.add(SystemMetrics(
                metric_type="cpu_usage",
                metric_value=cpu_percent,
                metric_unit="percent"
            ))

            # Store memory metrics
            session.add(SystemMetrics(
                metric_type="memory_usage",
                metric_value=memory.percent,
                metric_unit="percent",
                metric_metadata={"available_gb": memory.available / 1024**3}
            ))

            # Store GPU metrics if available
            if torch.cuda.is_available():
                session.add(SystemMetrics(
                    metric_type="gpu_memory_usage",
                    metric_value=metrics_data["gpu_memory_percent"],
                    metric_unit="percent",
                    metric_metadata={
                        "allocated_gb": metrics_data["gpu_memory_allocated_gb"],
                        "total_gb": metrics_data["gpu_memory_total_gb"]
                    }
                ))

            await session.commit()

            logger.info(
                "system_metrics_updated",
                task_id=task_id,
                **metrics_data
            )

            return metrics_data

    # Run async processing - use asyncio.run() for automatic cleanup
    return asyncio.run(store_metrics())
