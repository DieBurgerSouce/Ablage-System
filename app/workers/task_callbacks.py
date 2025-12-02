"""Celery task callbacks for state management and notifications.

Provides callback functions for task lifecycle events:
- on_success: Called when task completes successfully
- on_failure: Called when task fails
- on_retry: Called when task is retried
- update_progress: Progress update callbacks for real-time monitoring

Integrated with NotificationService for enterprise-grade notifications.
Feinpoliert und durchdacht - Zuverlässige Aufgabenverfolgung und Benachrichtigungen.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID
import asyncio

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.core.config import settings
from app.db.models import Document, ProcessingJob, ProcessingStatus, User

logger = structlog.get_logger(__name__)


def _run_async_callback(coro) -> Any:
    """
    Run async callback safely using asyncio.run().

    This is the recommended way to run async code in sync callbacks.
    asyncio.run() handles event loop creation and cleanup properly.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        # Handle case where there's already a running event loop
        # (e.g., in some test environments or nested async contexts)
        if "cannot be called from a running event loop" in str(e):
            logger.warning(
                "async_callback_nested_loop",
                message="Falling back to get_event_loop for nested context"
            )
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create task in existing loop - this shouldn't happen in production
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result(timeout=30)
            return loop.run_until_complete(coro)
        raise


# Database session factory mit Worker-optimiertem Connection Pool
# Callbacks sind kurzlebig, brauchen weniger Pool-Size
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_CALLBACK_POOL_SIZE,
    max_overflow=settings.DB_CALLBACK_MAX_OVERFLOW,
    pool_recycle=settings.DB_CALLBACK_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=False,
)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ==================== Webhook Dispatch Integration ====================

async def _dispatch_webhook_event(
    document_id: str,
    event_type: str,
    payload: Dict[str, Any]
) -> None:
    """Dispatcht Webhook-Event für Dokument-Owner."""
    try:
        from app.services.webhook_dispatcher import get_webhook_dispatcher

        async with async_session_maker() as session:
            # Get document with owner
            doc_result = await session.execute(
                select(Document).where(Document.id == UUID(document_id))
            )
            document = doc_result.scalar_one_or_none()

            if not document or not document.owner_id:
                return

            dispatcher = get_webhook_dispatcher()
            await dispatcher.dispatch_event(
                db=session,
                user_id=document.owner_id,
                event_type=event_type,
                payload={
                    "document_id": document_id,
                    "filename": document.original_filename or document.filename,
                    **payload
                }
            )

    except Exception as e:
        logger.warning(
            "webhook_dispatch_failed",
            document_id=document_id,
            event_type=event_type,
            error=str(e)
        )


# ==================== Success Callbacks ====================

def on_success(
    retval: Any,
    task_id: str,
    args: tuple,
    kwargs: dict
) -> None:
    """Handle successful task completion.

    Updates database records and logs success metrics.

    Args:
        retval: Task return value
        task_id: Celery task ID
        args: Task positional arguments
        kwargs: Task keyword arguments
    """
    logger.info(
        "task_success_callback",
        task_id=task_id,
        args=args,
        kwargs=kwargs
    )

    # Extract document_id from args or kwargs
    document_id = None
    if args and len(args) > 0:
        document_id = args[0]
    elif "document_id" in kwargs:
        document_id = kwargs["document_id"]

    if document_id and isinstance(retval, dict) and retval.get("success"):
        async def update_database() -> None:
            async with async_session_maker() as session:
                try:
                    doc_uuid = UUID(document_id)

                    # Update document status
                    result = await session.execute(
                        select(Document).where(Document.id == doc_uuid)
                    )
                    document = result.scalar_one_or_none()

                    if document:
                        document.status = ProcessingStatus.COMPLETED
                        document.processed_date = datetime.now(timezone.utc)

                        # Update processing job if exists
                        job_result = await session.execute(
                            select(ProcessingJob)
                            .where(ProcessingJob.document_id == doc_uuid)
                            .order_by(ProcessingJob.created_at.desc())
                            .limit(1)
                        )
                        job = job_result.scalar_one_or_none()

                        if job:
                            job.status = ProcessingStatus.COMPLETED
                            job.completed_at = datetime.now(timezone.utc)
                            job.result = retval

                        await session.commit()

                        logger.info(
                            "document_updated_on_success",
                            task_id=task_id,
                            document_id=document_id
                        )

                except Exception as e:
                    logger.error(
                        "success_callback_database_error",
                        task_id=task_id,
                        document_id=document_id,
                        error=str(e)
                    )

        # Run async update using safe helper
        _run_async_callback(update_database())


# ==================== Failure Callbacks ====================

def on_failure(
    exc: Exception,
    task_id: str,
    args: tuple,
    kwargs: dict,
    einfo: Any
) -> None:
    """Handle task failure.

    Updates database records, logs errors, and can send notifications.

    Args:
        exc: Exception that caused the failure
        task_id: Celery task ID
        args: Task positional arguments
        kwargs: Task keyword arguments
        einfo: Exception information
    """
    logger.error(
        "task_failure_callback",
        task_id=task_id,
        exception=str(exc),
        args=args,
        kwargs=kwargs,
        exc_info=True
    )

    # Extract document_id from args or kwargs
    document_id = None
    if args and len(args) > 0:
        document_id = args[0]
    elif "document_id" in kwargs:
        document_id = kwargs["document_id"]

    if document_id:
        async def update_database() -> None:
            async with async_session_maker() as session:
                try:
                    doc_uuid = UUID(document_id)

                    # Update document status
                    result = await session.execute(
                        select(Document).where(Document.id == doc_uuid)
                    )
                    document = result.scalar_one_or_none()

                    if document:
                        document.status = ProcessingStatus.FAILED

                        # Update processing job if exists
                        job_result = await session.execute(
                            select(ProcessingJob)
                            .where(ProcessingJob.document_id == doc_uuid)
                            .order_by(ProcessingJob.created_at.desc())
                            .limit(1)
                        )
                        job = job_result.scalar_one_or_none()

                        if job:
                            job.status = ProcessingStatus.FAILED
                            job.completed_at = datetime.now(timezone.utc)
                            job.error_message = str(exc)

                        await session.commit()

                        logger.info(
                            "document_updated_on_failure",
                            task_id=task_id,
                            document_id=document_id,
                            error=str(exc)
                        )

                except Exception as e:
                    logger.error(
                        "failure_callback_database_error",
                        task_id=task_id,
                        document_id=document_id,
                        error=str(e)
                    )

        # Run async update using safe helper
        _run_async_callback(update_database())

    # Send notification to user
    _send_failure_notification(document_id, str(exc))


# ==================== Retry Callbacks ====================

def on_retry(
    exc: Exception,
    task_id: str,
    args: tuple,
    kwargs: dict,
    einfo: Any
) -> None:
    """Handle task retry.

    Logs retry attempts and updates retry count in database.

    Args:
        exc: Exception that triggered the retry
        task_id: Celery task ID
        args: Task positional arguments
        kwargs: Task keyword arguments
        einfo: Exception information
    """
    logger.warning(
        "task_retry_callback",
        task_id=task_id,
        exception=str(exc),
        args=args,
        kwargs=kwargs
    )

    # Extract document_id from args or kwargs
    document_id = None
    if args and len(args) > 0:
        document_id = args[0]
    elif "document_id" in kwargs:
        document_id = kwargs["document_id"]

    if document_id:
        async def update_database() -> None:
            async with async_session_maker() as session:
                try:
                    doc_uuid = UUID(document_id)

                    # Update processing job retry count
                    job_result = await session.execute(
                        select(ProcessingJob)
                        .where(ProcessingJob.document_id == doc_uuid)
                        .order_by(ProcessingJob.created_at.desc())
                        .limit(1)
                    )
                    job = job_result.scalar_one_or_none()

                    if job:
                        job.retry_count = (job.retry_count or 0) + 1
                        job.error_message = f"Retry {job.retry_count}/{job.max_retries}: {str(exc)}"
                        await session.commit()

                        logger.info(
                            "job_retry_count_updated",
                            task_id=task_id,
                            document_id=document_id,
                            retry_count=job.retry_count,
                            max_retries=job.max_retries
                        )

                except Exception as e:
                    logger.error(
                        "retry_callback_database_error",
                        task_id=task_id,
                        document_id=document_id,
                        error=str(e)
                    )

        # Run async update using safe helper
        _run_async_callback(update_database())


# ==================== Progress Update Callbacks ====================

class ProgressCallback:
    """Progress callback for real-time task monitoring.

    Provides methods to update task progress with German messages.
    """

    def __init__(self, task: Task, total_steps: int = 100):
        """Initialize progress callback.

        Args:
            task: Celery task instance
            total_steps: Total number of progress steps
        """
        self.task = task
        self.total_steps = total_steps
        self.current_step = 0

    def update(
        self,
        current: Optional[int] = None,
        message: str = "Verarbeitung läuft..."
    ) -> None:
        """Update progress.

        Args:
            current: Current step (if None, increments by 1)
            message: Progress message in German
        """
        if current is not None:
            self.current_step = current
        else:
            self.current_step += 1

        progress = int((self.current_step / self.total_steps) * 100)
        progress = min(100, max(0, progress))

        self.task.update_state(
            state="PROGRESS",
            meta={
                "current": self.current_step,
                "total": self.total_steps,
                "progress": progress,
                "message": message,
            }
        )

        logger.info(
            "task_progress_updated",
            task_id=self.task.request.id,
            progress=progress,
            message=message
        )

    def complete(self, message: str = "Verarbeitung abgeschlossen!") -> None:
        """Mark progress as complete.

        Args:
            message: Completion message in German
        """
        self.update(self.total_steps, message)


# ==================== Helper Functions ====================

async def send_task_notification(
    document_id: str,
    status: str,
    message: str,
    email: Optional[str] = None,
    user_id: Optional[str] = None,
    webhook_url: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, bool]:
    """
    Send task completion notification via all configured channels.

    Sends notifications through:
    - Email (if SMTP configured and email provided)
    - Webhook (if webhook URL configured)
    - In-app notification (if user_id provided)

    Args:
        document_id: Document UUID
        status: Task status (success, failure, warning)
        message: Notification message
        email: Optional email address for notification
        user_id: Optional user ID for in-app notifications
        webhook_url: Optional webhook URL override
        metadata: Optional additional metadata for notification

    Returns:
        Dictionary with channel -> success status
    """
    from app.services.notification_service import (
        get_notification_service,
        NotificationType,
        NotificationPriority,
    )

    logger.info(
        "task_notification_sending",
        document_id=document_id,
        status=status,
        email=email,
        user_id=user_id
    )

    try:
        notification_service = get_notification_service()

        # Map status to notification type
        notification_type_map = {
            "success": NotificationType.PROCESSING_COMPLETED,
            "completed": NotificationType.PROCESSING_COMPLETED,
            "failure": NotificationType.PROCESSING_FAILED,
            "failed": NotificationType.PROCESSING_FAILED,
            "warning": NotificationType.OCR_QUALITY_WARNING,
            "started": NotificationType.PROCESSING_STARTED,
        }

        notification_type = notification_type_map.get(
            status.lower(),
            NotificationType.SYSTEM_ALERT
        )

        # Map status to priority
        priority_map = {
            "success": NotificationPriority.NORMAL,
            "completed": NotificationPriority.NORMAL,
            "failure": NotificationPriority.HIGH,
            "failed": NotificationPriority.HIGH,
            "warning": NotificationPriority.HIGH,
            "started": NotificationPriority.LOW,
        }

        priority = priority_map.get(status.lower(), NotificationPriority.NORMAL)

        # Build context
        context = {
            "document_id": document_id,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S"),
            **(metadata or {})
        }

        # Send notification
        results = await notification_service.notify(
            notification_type=notification_type,
            context=context,
            user_id=user_id,
            email=email,
            webhook_url=webhook_url,
            priority=priority,
        )

        logger.info(
            "task_notification_sent",
            document_id=document_id,
            status=status,
            results=results
        )

        return results

    except Exception as e:
        logger.error(
            "task_notification_failed",
            document_id=document_id,
            status=status,
            error=str(e),
            exc_info=True
        )
        return {"error": str(e)}


def get_german_error_message(exc: Exception) -> str:
    """Convert exception to German error message.

    Args:
        exc: Exception to convert

    Returns:
        German error message
    """
    error_map = {
        "FileNotFoundError": "Datei nicht gefunden",
        "ValueError": "Ungültiger Wert",
        "RuntimeError": "Laufzeitfehler",
        "TimeoutError": "Zeitüberschreitung",
        "MemoryError": "Speicherfehler",
        "OutOfMemoryError": "GPU-Speicher überschritten",
    }

    exc_type = type(exc).__name__
    base_message = error_map.get(exc_type, "Unbekannter Fehler")

    return f"{base_message}: {str(exc)}"


# ==================== Notification Integration ====================

def _send_success_notification(document_id: str, result: Dict[str, Any]) -> None:
    """Send success notification to document owner.

    Args:
        document_id: Document UUID
        result: Processing result data
    """
    async def _send_async() -> None:
        try:
            from app.services.notification_service import get_notification_service

            async with async_session_maker() as session:
                # Get document with owner
                doc_result = await session.execute(
                    select(Document).where(Document.id == UUID(document_id))
                )
                document = doc_result.scalar_one_or_none()

                if not document:
                    return

                # Get owner email if exists
                user_email = None
                user_id = None
                if document.owner_id:
                    user_result = await session.execute(
                        select(User).where(User.id == document.owner_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        user_email = user.email
                        user_id = str(user.id)

                # Send notification
                notification_service = get_notification_service()
                await notification_service.notify_processing_completed(
                    document_id=document_id,
                    filename=document.original_filename or document.filename,
                    backend=document.ocr_backend_used or "unknown",
                    processing_result={
                        "processing_time": f"{result.get('processing_time_ms', 0)}ms",
                        "confidence": result.get("confidence", 0),
                        "word_count": result.get("word_count", 0),
                        "entity_count": result.get("entity_count", 0),
                        "umlauts_valid": result.get("german_validation_score", 0) > 0.8,
                    },
                    user_id=user_id,
                    email=user_email,
                )

                logger.info(
                    "success_notification_sent",
                    document_id=document_id,
                    user_id=user_id,
                )

                # Dispatch webhook event
                await _dispatch_webhook_event(
                    document_id=document_id,
                    event_type="ocr.completed",
                    payload={
                        "backend": document.ocr_backend_used or "unknown",
                        "confidence": result.get("confidence", 0),
                        "word_count": result.get("word_count", 0),
                        "processing_time_ms": result.get("processing_time_ms", 0),
                    }
                )

        except Exception as e:
            logger.warning(
                "success_notification_failed",
                document_id=document_id,
                error=str(e),
            )

    # Run async notification using optimized helper
    # FIX P1.3: Use _run_async_callback instead of manual event loop creation
    # This reduces ~300ms overhead per task by avoiding loop creation/teardown
    try:
        _run_async_callback(_send_async())
    except Exception as e:
        logger.warning("notification_loop_error", error=str(e))


def _send_failure_notification(document_id: str, error_message: str) -> None:
    """Send failure notification to document owner.

    Args:
        document_id: Document UUID
        error_message: Error message string
    """
    async def _send_async() -> None:
        try:
            from app.services.notification_service import get_notification_service

            async with async_session_maker() as session:
                # Get document with owner
                doc_result = await session.execute(
                    select(Document).where(Document.id == UUID(document_id))
                )
                document = doc_result.scalar_one_or_none()

                if not document:
                    return

                # Get owner email if exists
                user_email = None
                user_id = None
                if document.owner_id:
                    user_result = await session.execute(
                        select(User).where(User.id == document.owner_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        user_email = user.email
                        user_id = str(user.id)

                # Convert error to German
                german_error = get_german_error_message(
                    ValueError(error_message)  # Wrap string in exception
                ) if not any(
                    german in error_message.lower()
                    for german in ["fehler", "nicht", "ungültig"]
                ) else error_message

                # Send notification
                notification_service = get_notification_service()
                await notification_service.notify_processing_failed(
                    document_id=document_id,
                    filename=document.original_filename or document.filename,
                    error_message=german_error,
                    user_id=user_id,
                    email=user_email,
                )

                logger.info(
                    "failure_notification_sent",
                    document_id=document_id,
                    user_id=user_id,
                )

                # Dispatch webhook event
                await _dispatch_webhook_event(
                    document_id=document_id,
                    event_type="ocr.failed",
                    payload={
                        "error_message": german_error,
                        "backend": document.ocr_backend_used,
                    }
                )

        except Exception as e:
            logger.warning(
                "failure_notification_failed",
                document_id=document_id,
                error=str(e),
            )

    # Run async notification using optimized helper
    # FIX P1.3: Use _run_async_callback instead of manual event loop creation
    try:
        _run_async_callback(_send_async())
    except Exception as e:
        logger.warning("notification_loop_error", error=str(e))


def _send_quality_warning(document_id: str, confidence: float) -> None:
    """Send quality warning notification.

    Args:
        document_id: Document UUID
        confidence: OCR confidence score
    """
    async def _send_async() -> None:
        try:
            from app.services.notification_service import get_notification_service

            async with async_session_maker() as session:
                # Get document with owner
                doc_result = await session.execute(
                    select(Document).where(Document.id == UUID(document_id))
                )
                document = doc_result.scalar_one_or_none()

                if not document or not document.owner_id:
                    return

                # Determine recommendation
                if confidence < 0.5:
                    recommendation = "Das Dokument sollte manuell überprüft werden. Die OCR-Qualität ist sehr niedrig."
                elif confidence < 0.7:
                    recommendation = "Eine manuelle Überprüfung des extrahierten Texts wird empfohlen."
                else:
                    recommendation = "Bitte überprüfen Sie kritische Felder wie Beträge und Daten."

                # Send notification
                notification_service = get_notification_service()
                await notification_service.notify_quality_warning(
                    document_id=document_id,
                    confidence=confidence,
                    recommendation=recommendation,
                    user_id=str(document.owner_id),
                )

        except Exception as e:
            logger.warning(
                "quality_warning_notification_failed",
                document_id=document_id,
                error=str(e),
            )

    # Run async notification using optimized helper
    # FIX P1.3: Use _run_async_callback instead of manual event loop creation
    try:
        _run_async_callback(_send_async())
    except Exception as e:
        # Quality Warning ist nicht kritisch, aber loggen für Debugging
        logger.debug(
            "quality_warning_loop_error",
            document_id=document_id,
            error=str(e)
        )
