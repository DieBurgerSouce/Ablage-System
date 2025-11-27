"""OCR processing tasks for Celery.

This module contains all async OCR processing tasks including:
- Single document OCR processing
- Batch document processing
- German text validation
- Metadata extraction
- System maintenance tasks
"""

from datetime import datetime, timedelta
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
from app.db.models import Document, ProcessingJob, OCRResult, ProcessingStatus, SystemMetrics
from app.services.ocr_service import OCRService
from app.german_validator import GermanValidator

logger = structlog.get_logger(__name__)

# Database session factory
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
    start_time = datetime.utcnow()
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
                    detect_fraktur=detect_fraktur
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
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                processing_ms = int(processing_time * 1000)

                # Update document with OCR results
                update_task_progress(task_id, 90, 100, "Speichere Ergebnisse...")

                document.extracted_text = ocr_result.get("text", "")
                document.ocr_backend_used = ocr_result.get("metadata", {}).get(
                    "backend_used", backend
                )
                document.ocr_confidence = ocr_result.get("confidence", 0.0)
                document.processing_duration_ms = processing_ms
                document.processed_date = datetime.utcnow()
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

                return {
                    "success": True,
                    "document_id": document_id,
                    "text": document.extracted_text,
                    "confidence": document.ocr_confidence,
                    "backend_used": document.ocr_backend_used,
                    "processing_time_ms": processing_ms,
                    "word_count": len(document.extracted_text.split()),
                    "german_validation": validation_result,
                    "completed_at": datetime.utcnow().isoformat(),
                }

            except SoftTimeLimitExceeded:
                logger.error("ocr_task_timeout", task_id=task_id, document_id=document_id)
                await update_document_status(
                    session,
                    doc_uuid,
                    ProcessingStatus.FAILED,
                    error_message="Zeitüberschreitung bei der Verarbeitung"
                )
                raise Ignore()

            except Exception as e:
                logger.exception(
                    "ocr_task_failed",
                    task_id=task_id,
                    document_id=document_id,
                    error=str(e)
                )
                await update_document_status(
                    session,
                    doc_uuid,
                    ProcessingStatus.FAILED,
                    error_message=str(e)
                )
                raise

    # Run async processing
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(process_async())
    finally:
        loop.close()


@celery_app.task(bind=True, base=GPUTask, name="app.workers.tasks.ocr_tasks.batch_process_task")
def batch_process_task(
    self,
    document_ids: List[str],
    backend: str = "auto",
    language: str = "de",
    max_concurrent: int = 1  # GPU tasks must be sequential
) -> Dict[str, Any]:
    """Process multiple documents in batch.

    Args:
        document_ids: List of document UUIDs as strings
        backend: OCR backend to use
        language: Target language
        max_concurrent: Maximum concurrent processing (GPU: 1, CPU: 3)

    Returns:
        Dictionary with batch processing results
    """
    task_id = self.request.id
    start_time = datetime.utcnow()
    total_docs = len(document_ids)

    logger.info(
        "batch_task_starting",
        task_id=task_id,
        document_count=total_docs,
        backend=backend
    )

    results = []
    successful = 0
    failed = 0

    for idx, doc_id in enumerate(document_ids):
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

        except Exception as e:
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
                "error": str(e)
            })

    processing_time = (datetime.utcnow() - start_time).total_seconds()

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

    return {
        "success": True,
        "total_documents": total_docs,
        "successful": successful,
        "failed": failed,
        "results": results,
        "processing_time_seconds": processing_time,
        "completed_at": datetime.utcnow().isoformat(),
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

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(extract_async())
    finally:
        loop.close()


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
    cutoff_time = datetime.utcnow() - timedelta(hours=hours_old)

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

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(cleanup_async())
    finally:
        loop.close()


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

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(store_metrics())
    finally:
        loop.close()
