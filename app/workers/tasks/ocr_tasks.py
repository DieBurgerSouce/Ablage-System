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
from typing import Dict, Any, List, Optional, Union
from uuid import UUID

from app.core.types import OCRTaskResult, OCRBatchResult
import asyncio
import io
import os
import psutil
import torch

import structlog
from celery import states
from celery.exceptions import SoftTimeLimitExceeded, Ignore
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.workers.celery_app import celery_app, GPUTask, CPUTask, gpu_memory_guard
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.session import get_worker_session_context
from app.db.models import Document, ProcessingJob, OCRResult, ProcessingStatus, SystemMetrics, BatchJob
from app.services.ocr_service import OCRService
from app.german_validator import GermanValidator
from app.services.storage_service import StorageService
import tempfile
import secrets

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
from app.workers.error_handling import celery_error_handler

logger = structlog.get_logger(__name__)

# GPU Recovery Manager (global für Worker)
_gpu_recovery_manager: Optional[GPURecoveryManager] = None


def get_worker_gpu_recovery_manager() -> GPURecoveryManager:
    """Get worker-local GPU recovery manager."""
    global _gpu_recovery_manager
    if _gpu_recovery_manager is None:
        _gpu_recovery_manager = GPURecoveryManager()
    return _gpu_recovery_manager


def _is_oom_error(exception: Exception) -> bool:
    """Prüfe ob Exception ein GPU OOM Error ist.

    W1: Logik nach app.core.gpu_errors extrahiert (backend_manager nutzt
    dieselbe Erkennung); Alias bleibt fuer bestehende Aufrufer erhalten.
    """
    from app.core.gpu_errors import is_oom_error

    return is_oom_error(exception)


def secure_delete_file(file_path: Union[str, Path], passes: int = 1) -> bool:
    """
    Sicheres Löschen einer Datei durch Überschreiben mit Zufallsdaten.

    SECURITY FIX: Verhindert Wiederherstellung sensibler Dokumentdaten
    von Temp-Dateien durch forensische Tools.

    Args:
        file_path: Pfad zur zu löschenden Datei
        passes: Anzahl der Überschreibdurchgaenge (Default: 1)

    Returns:
        True wenn erfolgreich gelöscht, False bei Fehler

    Security:
        - Überschreibt Dateiinhalt mit kryptografisch sicheren Zufallsdaten
        - Fsync nach jedem Schreibvorgang für sofortiges Schreiben auf Disk
        - Geeignet für sensitive Dokumente (GDPR Art. 17)
    """
    path = Path(file_path)
    if not path.exists():
        return True  # Bereits gelöscht

    try:
        file_size = path.stat().st_size

        # Überschreibe mit Zufallsdaten
        for pass_num in range(passes):
            with open(path, 'rb+') as f:
                # Schreibe in Bloecken für grosse Dateien
                block_size = 64 * 1024  # 64KB Bloecke
                remaining = file_size

                while remaining > 0:
                    write_size = min(block_size, remaining)
                    random_data = secrets.token_bytes(write_size)
                    f.write(random_data)
                    remaining -= write_size

                # Forciere Schreiben auf Disk
                f.flush()
                os.fsync(f.fileno())

        # Lösche Datei
        path.unlink()

        logger.debug(
            "secure_file_deleted",
            file_path=str(path),
            file_size=file_size,
            passes=passes
        )
        return True

    except Exception as e:
        logger.warning(
            "secure_delete_failed",
            file_path=str(path),
            **safe_error_log(e)
        )
        # Fallback: Normales Löschen
        try:
            path.unlink()
            return True
        except Exception as e:
            logger.debug(
                "secure_delete_fallback_failed",
                path=str(path),
                error_type=type(e).__name__,
            )
            return False


# GPU Lock Refresh Konfiguration
GPU_LOCK_REFRESH_INTERVAL = 25  # Sekunden (Lock läuft nach 60s ab, refreshe alle 25s)


async def _periodic_lock_refresh(
    task: 'GPUTask',
    interval: int = GPU_LOCK_REFRESH_INTERVAL,
    logger_context: Optional[Dict[str, Any]] = None
) -> None:
    """Background-Task für periodisches GPU-Lock-Refresh.

    Verhindert Lock-Ablauf bei langen OCR-Tasks (> 60s).
    Wird als asyncio.Task gestartet und nach OCR gecancelt.

    Args:
        task: GPUTask-Instanz mit refresh_lock() Methode
        interval: Refresh-Intervall in Sekunden
        logger_context: Optionale Log-Kontextdaten
    """
    log_ctx = logger_context or {}
    try:
        while True:
            await asyncio.sleep(interval)
            loop = asyncio.get_running_loop()
            refreshed = await loop.run_in_executor(None, task.refresh_lock)
            if refreshed:
                logger.debug("gpu_lock_background_refresh_success", **log_ctx)
            else:
                logger.warning("gpu_lock_background_refresh_failed", **log_ctx)
    except asyncio.CancelledError:
        # Normales Beenden wenn Task gecancelt wird
        logger.debug("gpu_lock_background_refresh_stopped", **log_ctx)
        raise
    except Exception as e:
        logger.error("gpu_lock_background_refresh_error", **safe_error_log(e), **log_ctx)


# ==================== Helper Functions ====================

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
@celery_error_handler()
def process_document_task(
    self,
    document_id: str,
    backend: str = "auto",
    language: str = "de",
    detect_layout: bool = True,
    detect_fraktur: bool = False,
    priority: str = "normal"
) -> OCRTaskResult:
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
        OCRTaskResult with success, text, confidence, backend_used, and processing information
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
        local_file_path = None  # Track temp file for cleanup
        async with get_worker_session_context() as session:
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

                if not document.file_path:
                    raise FileNotFoundError(
                        f"Dokumentdatei-Pfad nicht gesetzt für: {document_id}"
                    )

                # Pre-OCR Duplicate Check (spart GPU-Ressourcen)
                try:
                    from app.services.ai.duplicate_detection_service import get_duplicate_detection_service
                    dup_service = get_duplicate_detection_service()
                    dup_result = await dup_service.check_document(
                        db=session,
                        document_id=doc_uuid,
                        company_id=getattr(document, 'company_id', None),
                        include_near=False,  # Nur exakter Hash-Check (schnell)
                    )
                    if dup_result.has_duplicates and dup_result.best_match:
                        best = dup_result.best_match
                        if best.duplicate_type == "exact" and best.similarity >= 0.99:
                            # OCR-Ergebnisse vom Duplikat kopieren
                            from sqlalchemy import select as _select
                            dup_stmt = _select(Document).where(Document.id == best.document_id)
                            dup_result_row = await session.execute(dup_stmt)
                            dup_doc = dup_result_row.scalar_one_or_none()
                            copied_text = dup_doc.extracted_text if dup_doc else None
                            copied_confidence = dup_doc.ocr_confidence if dup_doc else None
                            copied_backend = dup_doc.ocr_backend_used if dup_doc else None

                            if copied_text:
                                document.extracted_text = copied_text
                                document.ocr_confidence = copied_confidence
                                document.ocr_backend_used = f"{copied_backend or 'unknown'}_copied"

                            logger.warning(
                                "ocr_skipped_duplicate",
                                document_id=document_id,
                                duplicate_of=str(best.document_id),
                                ocr_text_copied=copied_text is not None,
                            )
                            metadata = document.document_metadata or {}
                            metadata["potential_duplicate"] = True
                            metadata["duplicate_of"] = str(best.document_id)
                            metadata["ocr_skipped_reason"] = "exact_duplicate"
                            metadata["ocr_copied_from"] = str(best.document_id)
                            document.document_metadata = metadata
                            document.status = ProcessingStatus.COMPLETED
                            await session.commit()
                            return {
                                "success": True,
                                "document_id": document_id,
                                "text": copied_text,
                                "confidence": copied_confidence or 0.0,
                                "backend_used": "skipped_duplicate_copy",
                                "processing_time_ms": 0,
                                "skipped_reason": "exact_duplicate",
                            }
                except Exception as dup_err:
                    logger.debug(
                        "pre_ocr_duplicate_check_failed",
                        error=str(dup_err),
                    )
                    # Duplikat-Check-Fehler darf OCR niemals blockieren

                # Download file from MinIO to temp location (sync to avoid event loop issues)
                update_task_progress(task_id, 10, 100, "Datei wird heruntergeladen...")
                storage = StorageService()

                # Use sync MinIO client directly to avoid asyncio event loop conflicts
                response = storage.client.get_object(
                    bucket_name=storage.config.DOCUMENTS_BUCKET,
                    object_name=document.file_path
                )
                try:
                    file_content = response.read()
                finally:
                    response.close()
                    response.release_conn()

                # Save to temp file for OCR processing
                file_ext = Path(document.file_path).suffix or '.tif'
                with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                    tmp_file.write(file_content)
                    local_file_path = tmp_file.name

                # Start OCR processing
                update_task_progress(task_id, 20, 100, "OCR-Verarbeitung läuft...")

                # Starte Background-Task für periodisches GPU-Lock-Refresh
                # Verhindert Lock-Ablauf bei langen OCR-Tasks (> 60s)
                log_context = {"document_id": str(document_id), "backend": backend}
                lock_refresh_task = asyncio.create_task(
                    _periodic_lock_refresh(self, logger_context=log_context)
                )

                try:
                    ocr_result = await ocr_service.process_document(
                        image_path=local_file_path,
                        backend=backend,
                        language=language,
                        detect_layout=detect_layout,
                        detect_fraktur=detect_fraktur,
                        document_id=document_id  # For A/B experiment allocation
                    )
                finally:
                    # Background-Refresh-Task stoppen
                    lock_refresh_task.cancel()
                    try:
                        await lock_refresh_task
                    except asyncio.CancelledError:
                        pass  # Erwartet

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

                # Perceptual Hash berechnen für Bild-Dokumente
                if document.mime_type and document.mime_type.startswith("image/"):
                    try:
                        import imagehash as _imagehash
                        from PIL import Image as _Image
                        img = _Image.open(io.BytesIO(file_content))
                        phash = str(_imagehash.phash(img, hash_size=16))
                        doc_metadata = document.document_metadata or {}
                        doc_metadata["perceptual_hash"] = phash
                        document.document_metadata = doc_metadata
                        await session.commit()
                    except Exception as e:
                        # pHash-Berechnung ist optional (Duplikat-Erkennung); Fehler nicht fatal
                        logger.debug(
                            "perceptual_hash_failed",
                            document_id=str(document.id),
                            **safe_error_log(e),
                        )
                elif document.mime_type == "application/pdf":
                    try:
                        import imagehash as _imagehash
                        from PIL import Image as _Image
                        import fitz as _fitz
                        pdf_doc = _fitz.open(stream=file_content, filetype="pdf")
                        if len(pdf_doc) > 0:
                            pix = pdf_doc[0].get_pixmap(dpi=72)
                            img = _Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            phash = str(_imagehash.phash(img, hash_size=16))
                            doc_metadata = document.document_metadata or {}
                            doc_metadata["perceptual_hash"] = phash
                            document.document_metadata = doc_metadata
                            await session.commit()
                        pdf_doc.close()
                    except Exception as e:
                        # pHash-Berechnung ist optional (Duplikat-Erkennung); Fehler nicht fatal
                        logger.debug(
                            "perceptual_hash_failed",
                            document_id=str(document.id),
                            **safe_error_log(e),
                        )

                # Post-OCR: Vollständiger Duplikat-Check (Text steht jetzt zur Verfügung)
                try:
                    from app.services.ai.duplicate_detection_service import get_duplicate_detection_service
                    dup_service = get_duplicate_detection_service()
                    dup_result = await dup_service.check_document(
                        db=session,
                        document_id=doc_uuid,
                        company_id=getattr(document, 'company_id', None),
                        include_near=True,
                    )
                    if dup_result.has_duplicates:
                        await dup_service.create_duplicate_decision(
                            db=session,
                            document_id=doc_uuid,
                            check_result=dup_result,
                            company_id=getattr(document, 'company_id', None),
                        )
                except Exception as dup_err:
                    logger.debug(
                        "post_ocr_duplicate_check_failed",
                        error=str(dup_err),
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

                # Auto Ground-Truth Pipeline: High-Confidence OCR als Training-Sample
                if settings.AUTO_GROUND_TRUTH_ENABLED and document.extracted_text:
                    try:
                        from app.services.auto_ground_truth_service import get_auto_ground_truth_service

                        auto_gt_service = get_auto_ground_truth_service()
                        gt_result = await auto_gt_service.process_document_for_training(
                            db=session,
                            document_id=doc_uuid,
                            ocr_text=document.extracted_text,
                            ocr_confidence=document.ocr_confidence or 0.0,
                            document_type=document.document_type,
                            file_path=document.file_path,
                            file_hash=document.file_hash if hasattr(document, 'file_hash') else None,
                        )

                        if gt_result.auto_accepted:
                            logger.info(
                                "auto_ground_truth_created",
                                document_id=document_id,
                                sample_id=str(gt_result.sample_id),
                                needs_spot_check=gt_result.needs_manual_review,
                            )
                        else:
                            logger.debug(
                                "auto_ground_truth_skipped",
                                document_id=document_id,
                                reasons=gt_result.reasons,
                            )
                    except Exception as gt_error:
                        # Don't fail OCR if auto ground-truth fails
                        logger.warning(
                            "auto_ground_truth_failed",
                            document_id=document_id,
                            error=str(gt_error)
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
                            **safe_error_log(e)
                        )

                # Auto-Filing Pipeline nach OCR auslösen
                filing_pipeline_task_id = None
                if document.extracted_text and getattr(document, "company_id", None):
                    try:
                        from app.workers.tasks.auto_filing_tasks import trigger_auto_filing_pipeline_task
                        filing_result = trigger_auto_filing_pipeline_task.delay(
                            document_id=str(document_id),
                            company_id=str(document.company_id),
                            ocr_text=document.extracted_text,
                            user_id=str(document.owner_id) if document.owner_id else None,
                        )
                        filing_pipeline_task_id = filing_result.id
                        logger.info(
                            "auto_filing_pipeline_task_queued",
                            task_id=task_id,
                            document_id=document_id,
                            filing_pipeline_task_id=filing_pipeline_task_id,
                        )
                    except Exception as e:
                        # Filing-Pipeline darf OCR-Erfolg nicht blockieren
                        logger.warning(
                            "auto_filing_pipeline_task_queue_failed",
                            task_id=task_id,
                            document_id=document_id,
                            **safe_error_log(e)
                        )

                # Queue RAG chunking as background task (für Chat/Suche)
                rag_chunking_task_id = None
                if settings.AUTO_RAG_CHUNKING_ENABLED and document.extracted_text:
                    try:
                        from app.workers.tasks.rag_tasks import chunk_document
                        rag_result = chunk_document.apply_async(
                            args=[document_id],
                            countdown=settings.RAG_CHUNKING_DELAY_SECONDS,
                            priority=settings.RAG_TASK_PRIORITY,
                        )
                        rag_chunking_task_id = rag_result.id
                        logger.info(
                            "rag_chunking_task_queued",
                            task_id=task_id,
                            document_id=document_id,
                            rag_chunking_task_id=rag_chunking_task_id,
                            delay_seconds=settings.RAG_CHUNKING_DELAY_SECONDS
                        )
                    except Exception as e:
                        # Don't fail OCR if RAG chunking queuing fails
                        logger.warning(
                            "rag_chunking_task_queue_failed",
                            task_id=task_id,
                            document_id=document_id,
                            **safe_error_log(e)
                        )

                # Queue structured data extraction (Invoice/Order parsing)
                extraction_task_id = None
                quick_classification_task_id = None
                if document.extracted_text:
                    try:
                        from app.workers.tasks.extraction_tasks import reprocess_single_document
                        result = reprocess_single_document.apply_async(
                            args=[document_id],
                            countdown=2,  # Start 2 seconds after OCR completes
                            priority=5,
                        )
                        extraction_task_id = result.id
                        logger.info(
                            "extraction_task_queued",
                            task_id=task_id,
                            document_id=document_id,
                            extraction_task_id=extraction_task_id
                        )
                    except Exception as e:
                        # Don't fail OCR if extraction queuing fails
                        logger.warning(
                            "extraction_task_queue_failed",
                            task_id=task_id,
                            document_id=document_id,
                            **safe_error_log(e)
                        )

                    # Quick Classification nach OCR starten (nutzt vorhandenen OCR-Text)
                    try:
                        from app.workers.tasks.extraction_tasks import quick_classify_document
                        qc_result = quick_classify_document.apply_async(
                            kwargs={"document_id": document_id},
                            countdown=1,  # Start 1 second after OCR completes
                            priority=1,   # Hohe Priorität für schnelle Badge-Anzeige
                        )
                        quick_classification_task_id = qc_result.id
                        logger.info(
                            "quick_classification_task_queued_after_ocr",
                            task_id=task_id,
                            document_id=document_id,
                            quick_classification_task_id=quick_classification_task_id
                        )
                    except Exception as e:
                        # Don't fail OCR if quick classification queuing fails
                        logger.warning(
                            "quick_classification_task_queue_failed",
                            task_id=task_id,
                            document_id=document_id,
                            **safe_error_log(e)
                        )

                # Workflow-Trigger: Document Processed Event
                try:
                    from app.workers.tasks.workflow_tasks import on_document_processed
                    on_document_processed.delay(
                        document_id=document_id,
                        user_id=str(document.owner_id),
                        ocr_result={
                            "confidence": document.ocr_confidence,
                            "backend_used": document.ocr_backend_used,
                            "word_count": len(document.extracted_text.split()),
                            "processing_time_ms": processing_ms,
                        }
                    )
                except Exception as workflow_error:
                    # Workflow-Trigger sollte OCR-Erfolg nicht blockieren
                    logger.warning(
                        "workflow_trigger_failed",
                        document_id=document_id,
                        error=str(workflow_error)
                    )

                # Odoo-Vendor-Bill-Push (Neuausrichtung Phase 4):
                # Eingangsrechnungen aus E-Mail-/Ordner-Import als ENTWURFS-
                # Lieferantenrechnung nach Odoo pushen.
                # Reihenfolge (verifiziert): Der Import persistiert das Original
                # bereits VOR dem OCR in MinIO + Document-Zeile (inkl. SHA256) —
                # der Push haengt hier als LETZTER Schritt des Abschlussblocks
                # ("Archiv immer zuerst, Push danach"). Die formale GoBD-
                # Archivierung (is_archived via ArchiveService) ist ein separater
                # Schritt und wird bewusst NICHT von hier ausgeloest.
                # Klassifikation/Extraktion laufen asynchron (s. o., countdown
                # 1-2 s) und liegen hier noch NICHT vor -> der Task startet
                # verzoegert und prueft die invoice-Klassifikation selbst
                # (Retry bis extracted_data vorliegt).
                odoo_push_task_id = None
                try:
                    from app.services.erp.odoo_vendor_bill_push_service import (
                        should_enqueue_vendor_bill_push,
                    )

                    if await should_enqueue_vendor_bill_push(session, document):
                        from app.workers.tasks.erp_sync_tasks import (
                            push_vendor_bill_draft,
                        )

                        odoo_push_result = push_vendor_bill_draft.apply_async(
                            args=[document_id],
                            countdown=settings.ODOO_VENDOR_BILL_PUSH_DELAY_SECONDS,
                        )
                        odoo_push_task_id = odoo_push_result.id
                        logger.info(
                            "odoo_vendor_bill_push_queued",
                            task_id=task_id,
                            document_id=document_id,
                            odoo_push_task_id=odoo_push_task_id,
                            delay_seconds=settings.ODOO_VENDOR_BILL_PUSH_DELAY_SECONDS,
                        )
                except Exception as e:
                    # Push-Queueing darf OCR-Erfolg nicht blockieren
                    logger.warning(
                        "odoo_vendor_bill_push_queue_failed",
                        task_id=task_id,
                        document_id=document_id,
                        **safe_error_log(e)
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
                    "extraction_task_id": extraction_task_id,
                    "rag_chunking_task_id": rag_chunking_task_id,
                    "filing_pipeline_task_id": filing_pipeline_task_id,
                    "odoo_push_task_id": odoo_push_task_id,
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
                            image_path=local_file_path,
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
                            except Exception as e:
                                logger.debug(
                                    "ocr_metrics_recording_failed",
                                    backend="surya_cpu_fallback",
                                    error_type=type(e).__name__,
                                )

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
                        # Max retries erreicht - W1: Status FAILED persistieren,
                        # sonst bleibt das Dokument fuer immer auf "processing"
                        # haengen (der Timeout-Pfad oben macht das bereits).
                        await update_document_status(
                            session,
                            doc_uuid,
                            ProcessingStatus.FAILED,
                            error_message="GPU-Speicher erschöpft - Verarbeitung fehlgeschlagen",
                        )
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
                    **safe_error_log(e)
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
                    error_message=safe_error_detail(e, "OCR")
                )

                # Workflow-Trigger: Document Failed Event
                try:
                    # Get owner_id from document if available
                    doc_result = await session.execute(
                        select(Document.owner_id).where(Document.id == doc_uuid)
                    )
                    owner_id = doc_result.scalar_one_or_none()
                    if owner_id:
                        from app.workers.tasks.workflow_tasks import on_document_failed
                        on_document_failed.delay(
                            document_id=document_id,
                            user_id=str(owner_id),
                            **safe_error_log(e)
                        )
                except Exception as workflow_error:
                    logger.warning(
                        "workflow_trigger_failed_on_error",
                        document_id=document_id,
                        error=str(workflow_error)
                    )

                raise OCRProcessingError(
                    document_id=document_id,
                    backend=backend,
                    reason=safe_error_detail(e, "OCR")
                )

            finally:
                # SECURITY FIX: Secure cleanup temp file - überschreibe vor Löschung
                # Verhindert Wiederherstellung sensibler Dokumentdaten
                if local_file_path and Path(local_file_path).exists():
                    if not secure_delete_file(local_file_path):
                        logger.warning(
                            "temp_file_secure_cleanup_failed",
                            task_id=task_id,
                            file_path=local_file_path,
                            message="Konnte Temp-Datei nicht sicher löschen"
                        )

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
@celery_error_handler()
def batch_process_task(
    self,
    document_ids: List[str],
    backend: str = "auto",
    language: str = "de",
    max_concurrent: int = 1,  # GPU tasks must be sequential
    batch_job_id: Optional[str] = None,
    user_id: Optional[str] = None,
    resume_from_index: int = 0
) -> OCRBatchResult:
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
        OCRBatchResult with processing results and statistics
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

    # MEMORY FIX: Wrap entire batch processing in single async function
    # This prevents memory leaks from multiple asyncio.run() calls in the loop
    async def run_batch_processing() -> tuple[list, int, int, bool]:
        """Run the entire batch processing loop asynchronously.

        Returns:
            Tuple of (results, successful_count, failed_count, was_paused)
        """
        nonlocal results, successful, failed
        was_paused = False
        start_index = resume_from_index

        # Helper to update BatchJob progress
        async def update_progress(processed: int, failed_count: int, current_doc: str):
            if batch_job_id:
                try:
                    from app.services.batch_job_service import get_batch_job_service
                    async with get_worker_session_context() as session:
                        service = get_batch_job_service()
                        await service.update_progress(
                            db=session,
                            batch_id=UUID(batch_job_id),
                            processed=processed,
                            failed=failed_count,
                            current_document=current_doc
                        )
                except Exception as e:
                    logger.warning("batch_job_progress_update_failed", **safe_error_log(e))

        # Helper to check if batch is paused
        async def is_batch_paused() -> bool:
            if not batch_job_id:
                return False
            try:
                async with get_worker_session_context() as session:
                    result = await session.execute(
                        select(BatchJob).where(BatchJob.id == UUID(batch_job_id))
                    )
                    batch_job = result.scalar_one_or_none()
                    return batch_job.is_paused if batch_job else False
            except Exception as e:
                logger.debug(
                    "batch_pause_check_failed",
                    batch_job_id=batch_job_id,
                    error_type=type(e).__name__,
                )
                return False

        # Helper to clear GPU memory
        async def clear_gpu_memory_async():
            if torch.cuda.is_available():
                try:
                    gpu_manager = get_worker_gpu_recovery_manager()
                    await gpu_manager.clear_gpu_memory()
                except Exception as cleanup_error:
                    logger.warning("batch_gpu_cleanup_failed", **safe_error_log(cleanup_error))

        for idx, doc_id in enumerate(document_ids[start_index:], start=start_index):
            # Check if batch was paused
            if await is_batch_paused():
                logger.info(
                    "batch_task_paused",
                    task_id=task_id,
                    batch_job_id=batch_job_id,
                    paused_at_document=idx
                )
                was_paused = True
                break

            try:
                update_task_progress(
                    task_id,
                    idx,
                    total_docs,
                    f"Verarbeite Dokument {idx + 1}/{total_docs}..."
                )

                # Process individual document (sync call)
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

                # GPU Lock Refresh nach jedem verarbeiteten Dokument
                self.refresh_lock()

                # Update BatchJob progress
                await update_progress(
                    idx + 1 - start_index + successful + failed - 1,
                    failed,
                    doc_id[:8]
                )

            except Exception as e:
                # GPU OOM bei Batch-Verarbeitung: Speicher aufräumen, aber weitermachen
                if _is_oom_error(e):
                    logger.warning(
                        "batch_document_gpu_oom",
                        task_id=task_id,
                        document_id=doc_id,
                        **safe_error_log(e)
                    )

                    # GPU-Speicher aufräumen vor nächstem Dokument
                    await clear_gpu_memory_async()

                    failed += 1
                    results.append({
                        "success": False,
                        "document_id": doc_id,
                        "error": safe_error_detail(e, "GPU OOM"),
                        "error_type": "gpu_oom"
                    })
                else:
                    logger.error(
                        "batch_document_failed",
                        task_id=task_id,
                        document_id=doc_id,
                        **safe_error_log(e)
                    )
                    failed += 1
                    results.append({
                        "success": False,
                        "document_id": doc_id,
                        "error": safe_error_detail(e, "Vorgang"),
                        "error_type": "processing_error"
                    })

        return results, successful, failed, was_paused

    # Run entire batch processing in single event loop (prevents memory leak)
    results, successful, failed, was_paused = asyncio.run(run_batch_processing())

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

    # Complete BatchJob in separate async call (only once at end)
    if batch_job_id:
        async def complete_batch():
            try:
                from app.services.batch_job_service import get_batch_job_service
                async with get_worker_session_context() as session:
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
                logger.warning("batch_job_completion_failed", **safe_error_log(e))

        asyncio.run(complete_batch())

    # GPU OOM Statistiken sammeln
    gpu_oom_count = sum(1 for r in results if r.get("error_type") == "gpu_oom")
    gpu_recovery_stats = None
    if torch.cuda.is_available():
        try:
            gpu_manager = get_worker_gpu_recovery_manager()
            gpu_recovery_stats = gpu_manager.get_stats()
        except Exception as e:
            # GPU-Stats nicht kritisch für Batch-Ergebnis
            logger.debug("gpu_recovery_stats_failed", **safe_error_log(e))

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
@celery_error_handler()
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
                async with get_worker_session_context() as session:
                    await update_document_status(
                        session,
                        UUID(document_id),
                        ProcessingStatus.COMPLETED,
                        has_umlauts=has_umlauts,
                        german_validation_score=quality_score
                    )

            # MEMORY FIX: asyncio.run() statt new_event_loop() - verhindert Memory Leaks
            asyncio.run(update_doc())

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
            **safe_error_log(e)
        )
        raise


@celery_app.task(bind=True, base=CPUTask, name="app.workers.tasks.ocr_tasks.extract_metadata_task")
@celery_error_handler()
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
        async with get_worker_session_context() as session:
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
@celery_error_handler()
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
        async with get_worker_session_context() as session:
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
@celery_error_handler()
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
                **safe_error_log(e)
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
@celery_error_handler()
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
        async with get_worker_session_context() as session:
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


# ==================== OCR Self-Learning Tasks ====================


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ocr_tasks.calculate_ocr_backend_performance"
)
@celery_error_handler()
def calculate_ocr_backend_performance(
    self,
    backend: Optional[str] = None,
    period_days: int = 30,
) -> Dict[str, Any]:
    """
    Berechne und persistiere OCR Backend Performance-Metriken.

    Aggregiert OCR-Korrekturen aus der ocr_correction_feedbacks Tabelle
    und erstellt/aktualisiert ocr_backend_performance Records.

    Args:
        backend: Optional - Filter auf spezifisches Backend
        period_days: Zeitraum in Tagen (default: 30)

    Returns:
        Dictionary mit Berechnungs-Ergebnissen
    """
    task_id = self.request.id

    logger.info(
        "ocr_backend_performance_calculation_starting",
        task_id=task_id,
        backend=backend,
        period_days=period_days,
    )

    async def calculate_async() -> Dict[str, Any]:
        from app.services.ocr.self_learning_service import get_self_learning_service

        async with get_worker_session_context() as session:
            service = get_self_learning_service(session)

            # Berechne Performance-Metriken
            performance_records = await service.calculate_backend_performance(
                backend=backend,
                period_days=period_days,
            )

            logger.info(
                "ocr_backend_performance_calculation_completed",
                task_id=task_id,
                records_created=len(performance_records),
            )

            return {
                "success": True,
                "task_id": task_id,
                "records_created": len(performance_records),
                "performance_data": performance_records,
            }

    return asyncio.run(calculate_async())


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.ocr_tasks.process_pending_ocr_feedbacks"
)
@celery_error_handler()
def process_pending_ocr_feedbacks(
    self,
    batch_size: int = 100,
    backend: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verarbeite ausstehende OCR-Feedbacks und markiere als processed.

    Dieser Task wird regelmäßig ausgeführt um:
    1. Pending Feedbacks zu holen
    2. Confidence-Adjustments zu aktualisieren
    3. Feedbacks als processed zu markieren

    Args:
        batch_size: Maximale Anzahl pro Batch
        backend: Optional - Filter auf Backend

    Returns:
        Dictionary mit Verarbeitungs-Ergebnissen
    """
    task_id = self.request.id

    logger.info(
        "ocr_feedback_processing_starting",
        task_id=task_id,
        batch_size=batch_size,
        backend=backend,
    )

    async def process_async() -> Dict[str, Any]:
        from app.services.ocr.self_learning_service import get_self_learning_service

        async with get_worker_session_context() as session:
            service = get_self_learning_service(session)

            # Hole ausstehende Feedbacks
            pending_feedbacks = await service.get_pending_feedbacks(
                limit=batch_size,
                backend=backend,
            )

            if not pending_feedbacks:
                logger.info(
                    "ocr_feedback_processing_no_pending",
                    task_id=task_id,
                )
                return {
                    "success": True,
                    "task_id": task_id,
                    "processed_count": 0,
                    "message": "Keine ausstehenden Feedbacks",
                }

            # Markiere als verarbeitet
            feedback_ids = [f.id for f in pending_feedbacks]
            processed_count = await service.mark_feedbacks_processed(feedback_ids)

            logger.info(
                "ocr_feedback_processing_completed",
                task_id=task_id,
                processed_count=processed_count,
            )

            # Trigger Korrektur-Queue-Consumer fuer Template-Updates
            try:
                from app.workers.tasks.ocr_learning_tasks import consume_correction_queue
                consume_correction_queue.apply_async()
                logger.info(
                    "ocr_correction_queue_consumer_triggered",
                    task_id=task_id,
                    processed_count=processed_count,
                )
            except Exception as trigger_err:
                # Consumer-Trigger sollte Feedback-Verarbeitung nicht blockieren
                logger.warning(
                    "ocr_correction_queue_consumer_trigger_failed",
                    task_id=task_id,
                    error=str(trigger_err),
                )

            return {
                "success": True,
                "task_id": task_id,
                "processed_count": processed_count,
                "feedback_ids": [str(fid) for fid in feedback_ids],
            }

    return asyncio.run(process_async())
