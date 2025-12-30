"""Task Service for managing Celery task submission and monitoring.

Provides high-level interface for:
- Task submission with priority
- Task status checking
- Task cancellation
- Result retrieval
- Priority queue management
"""

import structlog
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from uuid import UUID

from celery.result import AsyncResult
from celery import states
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.workers.celery_app import celery_app
from app.workers.tasks.ocr_tasks import (
    process_document_task,
    batch_process_task,
    validate_german_text_task,
    extract_metadata_task,
)
from app.db.models import Document, ProcessingJob, ProcessingStatus
from app.core.config import settings
from app.core.german_messages import StatusMessages

logger = structlog.get_logger(__name__)


class TaskService:
    """Service for managing async OCR tasks."""

    def __init__(self):
        """Initialize task service."""
        self.celery = celery_app

    async def submit_document_task(
        self,
        session: AsyncSession,
        document_id: UUID,
        backend: str = "auto",
        language: str = "de",
        detect_layout: bool = True,
        detect_fraktur: bool = False,
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """Submit OCR task for a document.

        Args:
            session: Database session
            document_id: Document UUID
            backend: OCR backend to use
            language: Target language
            detect_layout: Enable layout detection
            detect_fraktur: Enable Fraktur detection
            priority: Task priority (high, normal, low)

        Returns:
            Task submission result with task ID
        """
        doc_uuid = document_id if isinstance(document_id, UUID) else UUID(document_id)

        # Get document
        result = await session.execute(
            select(Document).where(Document.id == doc_uuid)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Dokument {document_id} nicht gefunden")

        # Create processing job record
        job = ProcessingJob(
            document_id=doc_uuid,
            job_type="ocr",
            backend=backend,
            status=ProcessingStatus.QUEUED,
            priority=self._get_priority_value(priority),
        )
        session.add(job)
        await session.commit()

        # Submit Celery task
        task_priority = self._get_celery_priority(priority)
        task = process_document_task.apply_async(
            args=[str(document_id)],
            kwargs={
                "backend": backend,
                "language": language,
                "detect_layout": detect_layout,
                "detect_fraktur": detect_fraktur,
                "priority": priority,
            },
            priority=task_priority,
        )

        # Update job with task ID
        job.worker_id = task.id
        job.started_at = datetime.utcnow()
        await session.commit()

        logger.info("document_task_submitted", document_id=str(document_id), task_id=task.id, backend=backend, priority=priority)

        return {
            "task_id": task.id,
            "job_id": str(job.id),
            "document_id": str(document_id),
            "status": "queued",
            "priority": priority,
            "submitted_at": datetime.utcnow().isoformat(),
        }

    async def submit_batch_task(
        self,
        session: AsyncSession,
        document_ids: List[UUID],
        backend: str = "auto",
        language: str = "de",
        priority: str = "normal"
    ) -> Dict[str, Any]:
        """Submit batch OCR task for multiple documents.

        Args:
            session: Database session
            document_ids: List of document UUIDs
            backend: OCR backend to use
            language: Target language
            priority: Task priority

        Returns:
            Batch task submission result
        """
        # Convert UUIDs to strings
        doc_id_strings = [str(doc_id) for doc_id in document_ids]

        # Submit batch task
        task_priority = self._get_celery_priority(priority)
        task = batch_process_task.apply_async(
            args=[doc_id_strings],
            kwargs={
                "backend": backend,
                "language": language,
            },
            priority=task_priority,
        )

        logger.info("batch_task_submitted", task_id=task.id, document_count=len(document_ids), backend=backend, priority=priority)

        return {
            "task_id": task.id,
            "document_ids": doc_id_strings,
            "document_count": len(document_ids),
            "status": "queued",
            "priority": priority,
            "submitted_at": datetime.utcnow().isoformat(),
        }

    async def verify_task_ownership(
        self,
        session: AsyncSession,
        task_id: str,
        user_id: UUID
    ) -> bool:
        """Verify that a task belongs to a user.

        Y.1-Y.2 SECURITY FIX: Task-Ownership-Pruefung hinzugefuegt.

        Checks via ProcessingJob -> Document -> owner_id chain.

        Args:
            session: Database session
            task_id: Celery task ID (worker_id in ProcessingJob)
            user_id: User UUID to verify against

        Returns:
            True if task belongs to user or user is admin, False otherwise
        """
        result = await session.execute(
            select(ProcessingJob)
            .join(Document, ProcessingJob.document_id == Document.id)
            .where(ProcessingJob.worker_id == task_id)
            .where(Document.owner_id == user_id)
        )
        job = result.scalar_one_or_none()

        if job:
            return True

        logger.warning(
            "task_ownership_denied",
            task_id=task_id,
            user_id=str(user_id),
        )
        return False

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get current status of a task.

        Args:
            task_id: Celery task ID

        Returns:
            Task status information
        """
        task_result = AsyncResult(task_id, app=self.celery)

        status_info = {
            "task_id": task_id,
            "state": task_result.state,
            "ready": task_result.ready(),
            "successful": task_result.successful() if task_result.ready() else None,
            "failed": task_result.failed() if task_result.ready() else None,
        }

        # Add progress info if available
        if task_result.state == "PROGRESS":
            info = task_result.info or {}
            status_info.update({
                "progress": info.get("progress", 0),
                "current": info.get("current", 0),
                "total": info.get("total", 100),
                "message": info.get("message", "Verarbeitung läuft..."),
            })

        # Add result if complete
        if task_result.ready():
            if task_result.successful():
                status_info["result"] = task_result.result
            elif task_result.failed():
                status_info["error"] = str(task_result.info)

        logger.debug("task_status_checked", task_id=task_id, state=task_result.state)

        return status_info

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """Cancel a running task.

        Args:
            task_id: Celery task ID

        Returns:
            Cancellation result
        """
        task_result = AsyncResult(task_id, app=self.celery)

        if not task_result.ready():
            task_result.revoke(terminate=True)

            logger.warning("task_cancelled", task_id=task_id)

            return {
                "task_id": task_id,
                "cancelled": True,
                "message": StatusMessages.CANCELLED,
            }
        else:
            logger.info("task_cancellation_failed_already_completed", task_id=task_id, state=task_result.state)

            return {
                "task_id": task_id,
                "cancelled": False,
                "message": f"Aufgabe bereits abgeschlossen (Status: {task_result.state})",
                "state": task_result.state,
            }

    def get_task_result(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """Get task result (blocks until complete if timeout specified).

        Args:
            task_id: Celery task ID
            timeout: Optional timeout in seconds

        Returns:
            Task result

        Raises:
            TimeoutError: If timeout is reached
        """
        task_result = AsyncResult(task_id, app=self.celery)

        if timeout:
            result = task_result.get(timeout=timeout)
        else:
            if task_result.ready():
                result = task_result.result
            else:
                raise ValueError("Aufgabe noch nicht abgeschlossen")

        logger.info("task_result_retrieved", task_id=task_id)

        return result

    async def get_user_tasks(
        self,
        session: AsyncSession,
        user_id: UUID,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get recent tasks for a user.

        Args:
            session: Database session
            user_id: User UUID
            limit: Maximum number of tasks to return

        Returns:
            List of task information
        """
        # Get user's recent processing jobs
        result = await session.execute(
            select(ProcessingJob)
            .join(Document, ProcessingJob.document_id == Document.id)
            .where(Document.owner_id == user_id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(limit)
        )
        jobs = result.scalars().all()

        tasks = []
        for job in jobs:
            task_info = {
                "job_id": str(job.id),
                "document_id": str(job.document_id),
                "job_type": job.job_type,
                "backend": job.backend,
                "status": job.status,
                "priority": job.priority,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            }

            # Get Celery task status if task ID available
            if job.worker_id:
                task_info["task_id"] = job.worker_id
                celery_status = self.get_task_status(job.worker_id)
                task_info["celery_state"] = celery_status["state"]
                task_info["progress"] = celery_status.get("progress")

            tasks.append(task_info)

        logger.info("user_tasks_retrieved", user_id=str(user_id), task_count=len(tasks))

        return tasks

    def _get_priority_value(self, priority: str) -> int:
        """Convert priority string to numeric value.

        Args:
            priority: Priority string (high, normal, low)

        Returns:
            Numeric priority value (1-10)
        """
        priority_map = {
            "high": 9,
            "normal": 5,
            "low": 1,
        }
        return priority_map.get(priority.lower(), 5)

    def _get_celery_priority(self, priority: str) -> int:
        """Convert priority string to Celery priority value.

        Args:
            priority: Priority string (high, normal, low)

        Returns:
            Celery priority value (0-9, higher is more important)
        """
        return self._get_priority_value(priority)

    async def cleanup_old_tasks(
        self,
        session: AsyncSession,
        hours_old: int = 24
    ) -> Dict[str, Any]:
        """Clean up old completed tasks.

        Args:
            session: Database session
            hours_old: Delete tasks older than this many hours

        Returns:
            Cleanup statistics
        """
        from app.workers.tasks.ocr_tasks import cleanup_task

        # Submit cleanup task
        task = cleanup_task.apply_async(args=[hours_old])

        logger.info("cleanup_task_submitted", task_id=task.id, hours_old=hours_old)

        # Wait for result
        result = task.get(timeout=60)

        return result
