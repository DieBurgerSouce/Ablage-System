# -*- coding: utf-8 -*-
"""Celery Export Tasks fuer asynchrone Batch-Exports.

Enthaelt:
- batch_export_task: Async Export mit Progress-Tracking
- Export-Cancellation Support
- Progress-Updates via Redis/Celery State
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from celery import Task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.models import BatchJob, ProcessingStatus
from app.db.schemas import ExportFormat
from app.workers.celery_app import celery_app
from app.workers.task_callbacks import ProgressCallback

logger = structlog.get_logger(__name__)

# Database session factory fuer Worker
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class ExportCancelledError(Exception):
    """Raised when an export job is cancelled."""
    pass


def _run_async(coro):
    """Run async coroutine in sync context."""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        raise


async def _check_cancellation(job_id: UUID) -> bool:
    """Check if job was cancelled.

    Args:
        job_id: BatchJob UUID

    Returns:
        True if cancelled, False otherwise
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(BatchJob.is_cancelled).where(BatchJob.id == job_id)
        )
        is_cancelled = result.scalar()
        return bool(is_cancelled)


async def _update_job_progress(
    job_id: UUID,
    progress: int,
    processed: int,
    message: str,
    current_document: Optional[str] = None
) -> None:
    """Update job progress in database.

    Args:
        job_id: BatchJob UUID
        progress: Progress percentage (0-100)
        processed: Number of processed documents
        message: Progress message
        current_document: Current document being processed
    """
    async with async_session_maker() as session:
        await session.execute(
            update(BatchJob)
            .where(BatchJob.id == job_id)
            .values(
                progress=progress,
                processed_documents=processed,
                message=message,
                current_document=current_document,
            )
        )
        await session.commit()


async def _complete_job(
    job_id: UUID,
    success: bool,
    result_summary: Dict,
    error_message: Optional[str] = None
) -> None:
    """Mark job as completed.

    Args:
        job_id: BatchJob UUID
        success: Whether export succeeded
        result_summary: Export result summary
        error_message: Error message if failed
    """
    async with async_session_maker() as session:
        status = ProcessingStatus.COMPLETED if success else ProcessingStatus.FAILED
        values = {
            "status": status,
            "completed_at": datetime.now(timezone.utc),
            "progress": 100 if success else 0,
            "result_summary": result_summary,
        }
        if error_message:
            values["error_message"] = error_message

        await session.execute(
            update(BatchJob)
            .where(BatchJob.id == job_id)
            .values(**values)
        )
        await session.commit()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.export_tasks.batch_export_task",
    queue="default",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
)
def batch_export_task(
    self: Task,
    job_id: str,
    document_ids: List[str],
    user_id: str,
    format_str: str = "json",
    include_text: bool = True,
    include_metadata: bool = True,
) -> Dict:
    """Celery task fuer asynchronen Batch-Export.

    Args:
        self: Celery Task instance
        job_id: BatchJob UUID as string
        document_ids: Liste der Document UUIDs as strings
        user_id: User UUID as string
        format_str: Export-Format (json, csv, zip, pdf)
        include_text: Include extracted text
        include_metadata: Include metadata

    Returns:
        Dict with export result
    """
    job_uuid = UUID(job_id)
    user_uuid = UUID(user_id)
    doc_uuids = [UUID(doc_id) for doc_id in document_ids]
    total = len(doc_uuids)

    # Parse format
    try:
        export_format = ExportFormat(format_str.lower())
    except ValueError:
        export_format = ExportFormat.JSON

    logger.info(
        "batch_export_task_started",
        job_id=job_id,
        total_documents=total,
        format=format_str,
    )

    # Progress callback
    progress = ProgressCallback(self, total_steps=total)

    async def run_export():
        from app.services.document_services.export_service import DocumentExportService

        service = DocumentExportService()
        processed = 0
        errors = []
        last_checkpoint_idx = 0

        async with async_session_maker() as session:
            # Update job to started
            await session.execute(
                update(BatchJob)
                .where(BatchJob.id == job_uuid)
                .values(
                    status=ProcessingStatus.PROCESSING,
                    started_at=datetime.now(timezone.utc),
                    celery_task_id=self.request.id,
                )
            )
            await session.commit()

            # Check for cancellation before starting
            if await _check_cancellation(job_uuid):
                raise ExportCancelledError("Export wurde vor Start abgebrochen")

            # Process in smaller batches for more responsive cancellation
            # Reduced from 50 to 10 for better cancellation granularity
            batch_size = 10
            all_export_data = []

            for batch_start in range(0, total, batch_size):
                batch_end = min(batch_start + batch_size, total)
                batch_ids = doc_uuids[batch_start:batch_end]

                # Graceful cancellation check at batch start
                if await _check_cancellation(job_uuid):
                    # Save checkpoint for potential resume
                    await _update_job_progress(
                        job_uuid,
                        progress=int((batch_start / total) * 100),
                        processed=processed,
                        message=f"Abgebrochen bei Dokument {batch_start}/{total}",
                        current_document=None,
                    )
                    raise ExportCancelledError(
                        f"Export abgebrochen nach {processed} von {total} Dokumenten"
                    )

                # Update progress
                progress_pct = int((batch_start / total) * 100)
                progress.update(
                    batch_start,
                    f"Exportiere Dokumente {batch_start + 1}-{batch_end} von {total}..."
                )

                await _update_job_progress(
                    job_uuid,
                    progress_pct,
                    batch_start,
                    f"Batch {batch_start // batch_size + 1} von {(total + batch_size - 1) // batch_size}"
                )

                # Do the actual export for this batch
                try:
                    export_data, content_type, result = await service.batch_export(
                        db=session,
                        document_ids=batch_ids,
                        user_id=user_uuid,
                        format=export_format,
                        include_text=include_text,
                        include_metadata=include_metadata,
                    )

                    processed += result.processed
                    if result.errors:
                        errors.extend([e.dict() for e in result.errors])

                    # Collect export data
                    all_export_data.append({
                        "data": export_data,
                        "content_type": content_type,
                        "count": result.processed,
                    })

                    # Checkpoint: Update progress after each successful batch
                    last_checkpoint_idx = batch_end
                    await _update_job_progress(
                        job_uuid,
                        progress=int((batch_end / total) * 100),
                        processed=processed,
                        message=f"Verarbeitet: {processed}/{total} Dokumente",
                        current_document=None,
                    )

                    # Mid-batch cancellation check after processing
                    if await _check_cancellation(job_uuid):
                        await _update_job_progress(
                            job_uuid,
                            progress=int((batch_end / total) * 100),
                            processed=processed,
                            message=f"Abgebrochen nach {processed} Dokumenten",
                            current_document=None,
                        )
                        raise ExportCancelledError(
                            f"Export abgebrochen nach {processed} von {total} Dokumenten"
                        )

                except ExportCancelledError:
                    # Re-raise cancellation without wrapping
                    raise
                except Exception as e:
                    logger.error(
                        "batch_export_error",
                        batch_start=batch_start,
                        **safe_error_log(e),
                    )
                    errors.append({
                        "batch_start": batch_start,
                        "error": safe_error_detail(e, "Vorgang"),
                    })
                    # Continue with next batch on partial failure

            # Finalize
            progress.complete("Export abgeschlossen!")

            # Combine results
            total_bytes = sum(len(b["data"]) for b in all_export_data)

            result_summary = {
                "total_requested": total,
                "processed": processed,
                "failed": len(errors),
                "format": format_str,
                "total_bytes": total_bytes,
                "errors": errors[:10],  # Limit error list
            }

            await _complete_job(
                job_uuid,
                success=processed > 0,
                result_summary=result_summary,
            )

            return result_summary

    try:
        return _run_async(run_export())

    except ExportCancelledError as e:
        logger.warning(
            "batch_export_cancelled",
            job_id=job_id,
        )
        _run_async(_complete_job(
            job_uuid,
            success=False,
            result_summary={"cancelled": True},
            error_message=safe_error_detail(e, "Export"),
        ))
        return {"cancelled": True, "message": safe_error_detail(e, "Export")}

    except Exception as e:
        logger.error(
            "batch_export_failed",
            job_id=job_id,
            **safe_error_log(e),
            exc_info=True,
        )
        _run_async(_complete_job(
            job_uuid,
            success=False,
            result_summary={"error": safe_error_detail(e, "Vorgang")},
            error_message=safe_error_detail(e, "Export"),
        ))
        raise


@celery_app.task(
    name="app.workers.tasks.export_tasks.check_scheduled_exports",
    queue="default",
)
def check_scheduled_exports() -> Dict:
    """Prueft und startet faellige Scheduled Exports.

    Wird via Celery Beat alle 5 Minuten aufgerufen.

    Returns:
        Dict with check result
    """
    logger.info("check_scheduled_exports_started")

    async def check():
        from app.db.models import ScheduledExport
        from croniter import croniter
        from uuid import uuid4

        started_count = 0

        async with async_session_maker() as session:
            # Get scheduled exports that are due
            now = datetime.now(timezone.utc)

            result = await session.execute(
                select(ScheduledExport).where(
                    ScheduledExport.is_active == True,
                    ScheduledExport.next_run_at <= now,
                )
            )
            due_exports = result.scalars().all()

            for scheduled_export in due_exports:
                try:
                    job_id = uuid4()

                    # Create BatchJob
                    batch_job = BatchJob(
                        id=job_id,
                        user_id=scheduled_export.user_id,
                        job_type="export",
                        status=ProcessingStatus.QUEUED,
                        priority=5,
                        message=f"Geplanter Export: {scheduled_export.name}",
                        options={
                            "scheduled_export_id": str(scheduled_export.id),
                            "format": scheduled_export.export_format,
                            "export_type": scheduled_export.export_type,
                            "include_text": scheduled_export.include_text,
                            "include_metadata": scheduled_export.include_metadata,
                            "filter_config": scheduled_export.filter_config,
                        },
                    )
                    session.add(batch_job)

                    # Calculate next run
                    try:
                        import pytz
                        tz = pytz.timezone(scheduled_export.timezone)
                        tz_now = datetime.now(tz)
                    except Exception as e:
                        logger.debug(
                            "timezone_parse_failed",
                            timezone=scheduled_export.timezone,
                            error_type=type(e).__name__,
                        )
                        tz_now = now

                    cron = croniter(scheduled_export.cron_expression, tz_now)
                    next_run = cron.get_next(datetime)
                    if hasattr(next_run, 'astimezone'):
                        next_run = next_run.astimezone(timezone.utc)

                    # Update scheduled export
                    scheduled_export.next_run_at = next_run
                    scheduled_export.total_runs = (scheduled_export.total_runs or 0) + 1
                    scheduled_export.last_run_job_id = job_id

                    await session.commit()

                    # Trigger the actual export task
                    run_scheduled_export_task.delay(
                        scheduled_export_id=str(scheduled_export.id),
                        job_id=str(job_id),
                        user_id=str(scheduled_export.user_id),
                        manual=False,
                    )

                    started_count += 1

                    logger.info(
                        "scheduled_export_triggered",
                        export_id=str(scheduled_export.id),
                        job_id=str(job_id),
                        next_run=str(next_run),
                    )

                except Exception as e:
                    logger.error(
                        "scheduled_export_trigger_failed",
                        export_id=str(scheduled_export.id),
                        **safe_error_log(e),
                    )

        return {"checked": True, "started": started_count, "checked_at": now.isoformat()}

    return _run_async(check())


@celery_app.task(
    bind=True,
    name="app.workers.tasks.export_tasks.run_scheduled_export_task",
    queue="default",
    max_retries=2,
)
def run_scheduled_export_task(
    self: Task,
    scheduled_export_id: str,
    job_id: str,
    user_id: str,
    manual: bool = False,
) -> Dict:
    """Fuehrt einen Scheduled Export aus.

    Args:
        self: Celery Task instance
        scheduled_export_id: ScheduledExport UUID as string
        job_id: BatchJob UUID as string
        user_id: User UUID as string
        manual: True wenn manuell ausgeloest

    Returns:
        Dict with export result
    """
    from app.db.models import ScheduledExport, Document

    logger.info(
        "run_scheduled_export_started",
        scheduled_export_id=scheduled_export_id,
        job_id=job_id,
        manual=manual,
    )

    async def run():
        async with async_session_maker() as session:
            # Get scheduled export config
            result = await session.execute(
                select(ScheduledExport).where(
                    ScheduledExport.id == UUID(scheduled_export_id)
                )
            )
            scheduled_export = result.scalar_one_or_none()

            if not scheduled_export:
                raise ValueError(f"ScheduledExport {scheduled_export_id} nicht gefunden")

            # Get documents based on filter_config
            filter_config = scheduled_export.filter_config or {}

            # Build query based on export_type and filters
            query = select(Document.id).where(
                Document.owner_id == UUID(user_id),
                Document.deleted_at.is_(None),
            )

            # Apply date filters
            if filter_config.get("date_from"):
                from datetime import datetime as dt
                date_from = dt.fromisoformat(filter_config["date_from"].replace("Z", "+00:00"))
                query = query.where(Document.created_at >= date_from)

            if filter_config.get("date_to"):
                from datetime import datetime as dt
                date_to = dt.fromisoformat(filter_config["date_to"].replace("Z", "+00:00"))
                query = query.where(Document.created_at <= date_to)

            # Apply document type filter
            if filter_config.get("document_types"):
                query = query.where(Document.document_type.in_(filter_config["document_types"]))

            # Apply status filter
            if filter_config.get("statuses"):
                query = query.where(Document.status.in_(filter_config["statuses"]))

            # Limit
            max_docs = filter_config.get("max_documents", 1000)
            query = query.limit(max_docs)

            doc_result = await session.execute(query)
            document_ids = [str(row[0]) for row in doc_result.all()]

            if not document_ids:
                # No documents to export
                await session.execute(
                    update(BatchJob)
                    .where(BatchJob.id == UUID(job_id))
                    .values(
                        status=ProcessingStatus.COMPLETED,
                        completed_at=datetime.now(timezone.utc),
                        message="Keine Dokumente zum Exportieren gefunden",
                        result_summary={"total": 0, "message": "Keine Dokumente"},
                    )
                )
                scheduled_export.last_run_at = datetime.now(timezone.utc)
                scheduled_export.last_run_status = "success"
                scheduled_export.successful_runs = (scheduled_export.successful_runs or 0) + 1
                await session.commit()

                return {"status": "completed", "documents": 0}

            # Update job with document count
            await session.execute(
                update(BatchJob)
                .where(BatchJob.id == UUID(job_id))
                .values(
                    total_documents=len(document_ids),
                    document_ids=document_ids,
                )
            )
            await session.commit()

        # Delegate to batch_export_task
        result = batch_export_task.apply(
            args=[
                job_id,
                document_ids,
                user_id,
                scheduled_export.export_format,
                scheduled_export.include_text,
                scheduled_export.include_metadata,
            ]
        ).get()

        # Update scheduled export status
        async with async_session_maker() as session:
            result_db = await session.execute(
                select(ScheduledExport).where(
                    ScheduledExport.id == UUID(scheduled_export_id)
                )
            )
            scheduled_export = result_db.scalar_one_or_none()

            if scheduled_export:
                scheduled_export.last_run_at = datetime.now(timezone.utc)

                if result.get("error") or result.get("cancelled"):
                    scheduled_export.last_run_status = "failed"
                    scheduled_export.failed_runs = (scheduled_export.failed_runs or 0) + 1
                else:
                    scheduled_export.last_run_status = "success"
                    scheduled_export.successful_runs = (scheduled_export.successful_runs or 0) + 1

                await session.commit()

                # Notification senden falls konfiguriert
                if scheduled_export.notify_email:
                    should_notify = (
                        not scheduled_export.notify_on_failure_only
                        or result.get("error")
                        or result.get("cancelled")
                    )

                    if should_notify:
                        try:
                            from app.services.notification_service import (
                                get_notification_service,
                                NotificationType,
                            )

                            notification_service = get_notification_service()

                            # Hole User-E-Mail
                            from app.db.models import User as UserModel
                            user_result = await session.execute(
                                select(UserModel).where(UserModel.id == UUID(user_id))
                            )
                            user = user_result.scalar_one_or_none()
                            recipient_email = (
                                scheduled_export.notification_email
                                or (user.email if user else None)
                            )

                            if recipient_email:
                                # Berechne next_run
                                next_run_str = "N/A"
                                if scheduled_export.next_run_at:
                                    next_run_str = scheduled_export.next_run_at.strftime(
                                        "%d.%m.%Y %H:%M"
                                    )

                                if result.get("error") or result.get("cancelled"):
                                    # Fehler-Benachrichtigung
                                    await notification_service.notify(
                                        notification_type=NotificationType.SCHEDULED_EXPORT_FAILED,
                                        context={
                                            "export_name": scheduled_export.name,
                                            "executed_at": datetime.now(timezone.utc).strftime(
                                                "%d.%m.%Y %H:%M"
                                            ),
                                            "error_message": result.get("error", "Unbekannter Fehler"),
                                            "processed_count": result.get("processed", 0),
                                            "total_count": result.get("total", 0),
                                            "next_run": next_run_str,
                                        },
                                        user_id=user_id,
                                        email=recipient_email,
                                    )
                                else:
                                    # Erfolgs-Benachrichtigung
                                    await notification_service.notify(
                                        notification_type=NotificationType.SCHEDULED_EXPORT_COMPLETED,
                                        context={
                                            "export_name": scheduled_export.name,
                                            "executed_at": datetime.now(timezone.utc).strftime(
                                                "%d.%m.%Y %H:%M"
                                            ),
                                            "documents_exported": result.get("processed", 0),
                                            "export_format": scheduled_export.export_format,
                                            "next_run": next_run_str,
                                        },
                                        user_id=user_id,
                                        email=recipient_email,
                                    )

                                logger.info(
                                    "scheduled_export_notification_sent",
                                    export_id=scheduled_export_id,
                                    recipient=recipient_email,
                                    success=not (result.get("error") or result.get("cancelled")),
                                )

                        except Exception as notify_error:
                            logger.warning(
                                "scheduled_export_notification_failed",
                                export_id=scheduled_export_id,
                                error=str(notify_error),
                            )

        return result

    try:
        return _run_async(run())
    except Exception as e:
        logger.error(
            "run_scheduled_export_failed",
            scheduled_export_id=scheduled_export_id,
            **safe_error_log(e),
            exc_info=True,
        )
        # Update failure status
        async def update_failure():
            async with async_session_maker() as session:
                await session.execute(
                    update(BatchJob)
                    .where(BatchJob.id == UUID(job_id))
                    .values(
                        status=ProcessingStatus.FAILED,
                        completed_at=datetime.now(timezone.utc),
                        error_message=safe_error_detail(e, "Export"),
                    )
                )
                from app.db.models import ScheduledExport
                result = await session.execute(
                    select(ScheduledExport).where(
                        ScheduledExport.id == UUID(scheduled_export_id)
                    )
                )
                scheduled_export = result.scalar_one_or_none()
                if scheduled_export:
                    scheduled_export.last_run_at = datetime.now(timezone.utc)
                    scheduled_export.last_run_status = "failed"
                    scheduled_export.failed_runs = (scheduled_export.failed_runs or 0) + 1
                await session.commit()

        _run_async(update_failure())
        raise
