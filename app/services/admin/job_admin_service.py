"""Job Administration Service.

Provides job management operations for the admin console:
- List jobs with filtering and pagination
- Cancel running/pending jobs
- Retry failed jobs
- Clear job queue
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID
import math

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, delete
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import ProcessingJob, Document, User, ProcessingStatus, AdminAction
from app.db.schemas import (
    JobAdminView,
    JobListFilters,
    JobListResponse,
    JobActionResponse,
    QueueClearResponse,
    SortOrder,
)

logger = structlog.get_logger(__name__)


class JobAdminService:
    """Service for job administration operations."""

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        page: int = 1,
        per_page: int = 20,
        filters: Optional[JobListFilters] = None,
        sort_by: str = "created_at",
        sort_order: SortOrder = SortOrder.DESC,
    ) -> JobListResponse:
        """List jobs with filtering and pagination.

        Args:
            db: Database session
            page: Page number (1-based)
            per_page: Items per page
            filters: Optional filters
            sort_by: Field to sort by
            sort_order: Sort direction

        Returns:
            Paginated job list
        """
        query = select(ProcessingJob).options(
            selectinload(ProcessingJob.document)
        )

        # Apply filters
        if filters:
            conditions = []

            if filters.status:
                conditions.append(ProcessingJob.status == filters.status)
            if filters.backend:
                conditions.append(ProcessingJob.backend == filters.backend)
            if filters.user_id:
                # Join with document to filter by owner
                query = query.join(Document).where(Document.owner_id == filters.user_id)
            if filters.priority:
                conditions.append(ProcessingJob.priority == filters.priority)
            if filters.created_from:
                conditions.append(ProcessingJob.created_at >= filters.created_from)
            if filters.created_to:
                conditions.append(ProcessingJob.created_at <= filters.created_to)
            if filters.has_error is not None:
                if filters.has_error:
                    conditions.append(ProcessingJob.error_message.isnot(None))
                else:
                    conditions.append(ProcessingJob.error_message.is_(None))

            if conditions:
                query = query.where(and_(*conditions))

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(ProcessingJob, sort_by, ProcessingJob.created_at)
        if sort_order == SortOrder.DESC:
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Execute query with eager loading to avoid N+1
        query = query.options(selectinload(ProcessingJob.document))
        result = await db.execute(query)
        jobs = result.scalars().all()

        # Batch fetch all owners to avoid N+1 queries
        owner_ids = {job.document.owner_id for job in jobs if job.document and job.document.owner_id}
        owners_map: Dict[UUID, User] = {}
        if owner_ids:
            owners_result = await db.execute(
                select(User).where(User.id.in_(owner_ids))
            )
            for user in owners_result.scalars().all():
                owners_map[user.id] = user

        # Convert to response format
        job_views = []
        for job in jobs:
            doc = job.document
            owner = owners_map.get(doc.owner_id) if doc and doc.owner_id else None

            # Calculate durations
            duration_ms = None
            if job.started_at and job.completed_at:
                duration_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)

            wait_time_ms = None
            if job.started_at:
                wait_time_ms = int((job.started_at - job.created_at).total_seconds() * 1000)

            job_views.append(JobAdminView(
                id=job.id,
                document_id=job.document_id,
                document_filename=doc.filename if doc else None,
                user_id=doc.owner_id if doc else None,
                user_email=owner.email if owner else None,
                job_type=job.job_type,
                backend=job.backend,
                status=job.status,
                priority=job.priority,
                retry_count=job.retry_count,
                max_retries=job.max_retries,
                created_at=job.created_at,
                started_at=job.started_at,
                completed_at=job.completed_at,
                error_message=job.error_message,
                worker_id=job.worker_id,
                result=job.result or {},
                duration_ms=duration_ms,
                wait_time_ms=wait_time_ms,
            ))

        # Status summary
        status_result = await db.execute(
            select(ProcessingJob.status, func.count())
            .group_by(ProcessingJob.status)
        )
        status_summary = {row[0].value if hasattr(row[0], 'value') else row[0]: row[1] for row in status_result.all()}

        return JobListResponse(
            jobs=job_views,
            total=total,
            page=page,
            per_page=per_page,
            total_pages=math.ceil(total / per_page) if total > 0 else 1,
            status_summary=status_summary,
        )

    @staticmethod
    async def get_job(db: AsyncSession, job_id: UUID) -> Optional[JobAdminView]:
        """Get a single job by ID.

        Args:
            db: Database session
            job_id: Job UUID

        Returns:
            Job view or None if not found
        """
        result = await db.execute(
            select(ProcessingJob)
            .options(selectinload(ProcessingJob.document))
            .where(ProcessingJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return None

        doc = job.document
        owner = None
        if doc:
            owner_result = await db.execute(
                select(User).where(User.id == doc.owner_id)
            )
            owner = owner_result.scalar_one_or_none()

        duration_ms = None
        if job.started_at and job.completed_at:
            duration_ms = int((job.completed_at - job.started_at).total_seconds() * 1000)

        wait_time_ms = None
        if job.started_at:
            wait_time_ms = int((job.started_at - job.created_at).total_seconds() * 1000)

        return JobAdminView(
            id=job.id,
            document_id=job.document_id,
            document_filename=doc.filename if doc else None,
            user_id=doc.owner_id if doc else None,
            user_email=owner.email if owner else None,
            job_type=job.job_type,
            backend=job.backend,
            status=job.status,
            priority=job.priority,
            retry_count=job.retry_count,
            max_retries=job.max_retries,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
            worker_id=job.worker_id,
            result=job.result or {},
            duration_ms=duration_ms,
            wait_time_ms=wait_time_ms,
        )

    @staticmethod
    async def cancel_job(
        db: AsyncSession,
        job_id: UUID,
        admin: User,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> JobActionResponse:
        """Cancel a pending or processing job.

        Args:
            db: Database session
            job_id: Job to cancel
            admin: Admin performing the action
            reason: Optional cancellation reason
            ip_address: Request IP address

        Returns:
            Action response
        """
        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="cancel",
                message="Auftrag nicht gefunden",
            )

        if job.status in [ProcessingStatus.COMPLETED, ProcessingStatus.CANCELLED]:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="cancel",
                message="Auftrag kann nicht abgebrochen werden (bereits abgeschlossen)",
            )

        # Store previous status before modifying
        previous_status = job.status.value if hasattr(job.status, 'value') else str(job.status)

        # Use savepoint for atomic operation (job update + admin action)
        try:
            async with db.begin_nested():
                # Cancel the job
                job.status = ProcessingStatus.CANCELLED
                job.completed_at = datetime.utcnow()
                job.error_message = f"Abgebrochen durch Admin: {reason}" if reason else "Abgebrochen durch Admin"

                # Log admin action
                admin_action = AdminAction(
                    admin_id=admin.id,
                    target_user_id=None,
                    action="cancel_job",
                    action_details={
                        "job_id": str(job_id),
                        "previous_status": previous_status,
                        "reason": reason,
                    },
                    ip_address=ip_address,
                )
                db.add(admin_action)

            # Savepoint succeeded - commit the transaction
            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(
                "cancel_job_failed",
                job_id=str(job_id),
                admin_id=str(admin.id),
                error=str(e),
            )
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="cancel",
                message="Betriebsfehler aufgetreten. Bitte versuchen Sie es spaeter erneut.",
            )

        logger.info(
            "job_cancelled_by_admin",
            job_id=str(job_id),
            admin_id=str(admin.id),
            reason=reason,
        )

        return JobActionResponse(
            success=True,
            job_id=job_id,
            action="cancel",
            message="Auftrag wurde abgebrochen",
        )

    @staticmethod
    async def retry_job(
        db: AsyncSession,
        job_id: UUID,
        admin: User,
        priority: Optional[int] = None,
        backend: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> JobActionResponse:
        """Retry a failed job.

        Args:
            db: Database session
            job_id: Job to retry
            admin: Admin performing the action
            priority: Optional new priority
            backend: Optional new backend
            ip_address: Request IP address

        Returns:
            Action response with new job ID
        """
        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="retry",
                message="Auftrag nicht gefunden",
            )

        if job.status != ProcessingStatus.FAILED:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="retry",
                message="Nur fehlgeschlagene Auftraege koennen wiederholt werden",
            )

        # Use savepoint for atomic operation (new job + admin action)
        try:
            async with db.begin_nested():
                # Create new job
                new_job = ProcessingJob(
                    document_id=job.document_id,
                    job_type=job.job_type,
                    backend=backend or job.backend,
                    status=ProcessingStatus.PENDING,
                    priority=priority or job.priority,
                    retry_count=0,
                    max_retries=job.max_retries,
                )
                db.add(new_job)
                await db.flush()

                # Log admin action
                admin_action = AdminAction(
                    admin_id=admin.id,
                    target_user_id=None,
                    action="retry_job",
                    action_details={
                        "original_job_id": str(job_id),
                        "new_job_id": str(new_job.id),
                        "priority": priority or job.priority,
                        "backend": backend or job.backend,
                    },
                    ip_address=ip_address,
                )
                db.add(admin_action)

            # Savepoint succeeded - commit the transaction
            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(
                "retry_job_failed",
                job_id=str(job_id),
                admin_id=str(admin.id),
                error=str(e),
            )
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="retry",
                message="Betriebsfehler aufgetreten. Bitte versuchen Sie es spaeter erneut.",
            )

        logger.info(
            "job_retried_by_admin",
            original_job_id=str(job_id),
            new_job_id=str(new_job.id),
            admin_id=str(admin.id),
        )

        return JobActionResponse(
            success=True,
            job_id=new_job.id,
            action="retry",
            message=f"Auftrag wird erneut verarbeitet (neue ID: {new_job.id})",
        )

    @staticmethod
    async def clear_queue(
        db: AsyncSession,
        admin: User,
        status: ProcessingStatus = ProcessingStatus.PENDING,
        ip_address: Optional[str] = None,
    ) -> QueueClearResponse:
        """Clear jobs with a specific status from the queue.

        Args:
            db: Database session
            admin: Admin performing the action
            status: Status of jobs to clear (default: PENDING)
            ip_address: Request IP address

        Returns:
            Clear operation response
        """
        if status not in [ProcessingStatus.PENDING, ProcessingStatus.QUEUED]:
            return QueueClearResponse(
                success=False,
                cleared_count=0,
                message="Nur wartende Auftraege koennen geloescht werden",
            )

        # Count jobs to clear
        count_result = await db.execute(
            select(func.count()).where(ProcessingJob.status == status)
        )
        count = count_result.scalar() or 0

        if count == 0:
            return QueueClearResponse(
                success=True,
                cleared_count=0,
                message="Keine wartenden Auftraege vorhanden",
            )

        status_value = status.value if hasattr(status, 'value') else str(status)

        # Use savepoint for atomic operation (delete + admin action)
        try:
            async with db.begin_nested():
                # Delete jobs
                await db.execute(
                    delete(ProcessingJob).where(ProcessingJob.status == status)
                )

                # Log admin action
                admin_action = AdminAction(
                    admin_id=admin.id,
                    target_user_id=None,
                    action="clear_queue",
                    action_details={
                        "status": status_value,
                        "cleared_count": count,
                    },
                    ip_address=ip_address,
                )
                db.add(admin_action)

            # Savepoint succeeded - commit the transaction
            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(
                "clear_queue_failed",
                admin_id=str(admin.id),
                status=status_value,
                target_count=count,
                error=str(e),
            )
            return QueueClearResponse(
                success=False,
                cleared_count=0,
                message="Fehler beim Leeren der Warteschlange. Bitte versuchen Sie es spaeter erneut.",
            )

        logger.warning(
            "queue_cleared_by_admin",
            admin_id=str(admin.id),
            status=status_value,
            count=count,
        )

        return QueueClearResponse(
            success=True,
            cleared_count=count,
            message=f"{count} wartende Auftraege wurden geloescht",
        )

    @staticmethod
    async def get_job_stats(db: AsyncSession) -> Dict[str, Any]:
        """Get comprehensive job statistics.

        Args:
            db: Database session

        Returns:
            Dictionary with job statistics
        """
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)
        last_hour = now - timedelta(hours=1)

        # Status summary
        status_result = await db.execute(
            select(ProcessingJob.status, func.count())
            .group_by(ProcessingJob.status)
        )
        status_summary = {
            row[0].value if hasattr(row[0], 'value') else row[0]: row[1]
            for row in status_result.all()
        }

        # Active jobs (processing + queued)
        active_count = status_summary.get('processing', 0) + status_summary.get('queued', 0)

        # Jobs in last 24h
        result_24h = await db.execute(
            select(func.count()).where(ProcessingJob.created_at >= last_24h)
        )
        jobs_24h = result_24h.scalar() or 0

        # Completed in last 24h
        completed_24h_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= last_24h
                )
            )
        )
        completed_24h = completed_24h_result.scalar() or 0

        # Failed in last 24h
        failed_24h_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.FAILED,
                    ProcessingJob.completed_at >= last_24h
                )
            )
        )
        failed_24h = failed_24h_result.scalar() or 0

        # Success rate
        total_finished_24h = completed_24h + failed_24h
        success_rate = (completed_24h / total_finished_24h * 100) if total_finished_24h > 0 else 100.0

        # Jobs completed in last hour (throughput)
        throughput_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= last_hour
                )
            )
        )
        throughput_per_hour = throughput_result.scalar() or 0

        # Average processing time (last 24h, completed jobs)
        # Explicit NULL checks for both timestamps to prevent SQL arithmetic errors
        avg_time_result = await db.execute(
            select(func.avg(
                func.extract('epoch', ProcessingJob.completed_at) -
                func.extract('epoch', ProcessingJob.started_at)
            )).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= last_24h,
                    ProcessingJob.completed_at.isnot(None),  # Explicit NULL check
                    ProcessingJob.started_at.isnot(None)
                )
            )
        )
        avg_processing_time_seconds = avg_time_result.scalar() or 0

        # Average wait time (last 24h)
        # Explicit NULL checks for both timestamps to prevent SQL arithmetic errors
        avg_wait_result = await db.execute(
            select(func.avg(
                func.extract('epoch', ProcessingJob.started_at) -
                func.extract('epoch', ProcessingJob.created_at)
            )).where(
                and_(
                    ProcessingJob.started_at.isnot(None),
                    ProcessingJob.created_at.isnot(None),  # Explicit NULL check
                    ProcessingJob.created_at >= last_24h
                )
            )
        )
        avg_wait_time_seconds = avg_wait_result.scalar() or 0

        # Jobs by backend
        backend_result = await db.execute(
            select(ProcessingJob.backend, func.count())
            .where(ProcessingJob.created_at >= last_24h)
            .group_by(ProcessingJob.backend)
        )
        jobs_by_backend = {row[0] or 'unknown': row[1] for row in backend_result.all()}

        # Jobs by type
        type_result = await db.execute(
            select(ProcessingJob.job_type, func.count())
            .where(ProcessingJob.created_at >= last_24h)
            .group_by(ProcessingJob.job_type)
        )
        jobs_by_type = {row[0] or 'unknown': row[1] for row in type_result.all()}

        return {
            "status_summary": status_summary,
            "total_jobs": sum(status_summary.values()),
            "active_jobs": active_count,
            "queued_jobs": status_summary.get('queued', 0) + status_summary.get('pending', 0),
            "jobs_24h": jobs_24h,
            "completed_24h": completed_24h,
            "failed_24h": failed_24h,
            "success_rate_24h": round(success_rate, 2),
            "throughput_per_hour": throughput_per_hour,
            "avg_processing_time_ms": int(avg_processing_time_seconds * 1000) if avg_processing_time_seconds else 0,
            "avg_wait_time_ms": int(avg_wait_time_seconds * 1000) if avg_wait_time_seconds else 0,
            "jobs_by_backend": jobs_by_backend,
            "jobs_by_type": jobs_by_type,
        }

    @staticmethod
    async def change_priority(
        db: AsyncSession,
        job_id: UUID,
        priority: int,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> JobActionResponse:
        """Change job priority.

        Args:
            db: Database session
            job_id: Job to update
            priority: New priority (1-10)
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Action response
        """
        from app.db.schemas import JobActionResponse

        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="change_priority",
                message="Auftrag nicht gefunden",
            )

        if job.status not in [ProcessingStatus.PENDING, ProcessingStatus.QUEUED]:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="change_priority",
                message="Prioritaet kann nur fuer wartende Auftraege geaendert werden",
            )

        old_priority = job.priority
        job.priority = priority

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=None,
            action="change_job_priority",
            action_details={
                "job_id": str(job_id),
                "old_priority": old_priority,
                "new_priority": priority,
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()

        logger.info(
            "job_priority_changed",
            job_id=str(job_id),
            admin_id=str(admin.id),
            old_priority=old_priority,
            new_priority=priority,
        )

        return JobActionResponse(
            success=True,
            job_id=job_id,
            action="change_priority",
            message=f"Prioritaet von {old_priority} auf {priority} geaendert",
        )

    @staticmethod
    async def force_kill_job(
        db: AsyncSession,
        job_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> JobActionResponse:
        """Force kill a stuck job.

        Args:
            db: Database session
            job_id: Job to force kill
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Action response
        """
        from app.db.schemas import JobActionResponse

        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="force_kill",
                message="Auftrag nicht gefunden",
            )

        if job.status not in [ProcessingStatus.PROCESSING, ProcessingStatus.QUEUED]:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="force_kill",
                message="Nur laufende Auftraege koennen erzwungen beendet werden",
            )

        # Try to revoke the Celery task if we have a worker_id
        revoked = False
        if job.worker_id:
            try:
                from app.workers.celery_app import celery_app
                celery_app.control.revoke(job.worker_id, terminate=True, signal="SIGKILL")
                revoked = True
                logger.warning(
                    "celery_task_revoked",
                    task_id=job.worker_id,
                    job_id=str(job_id),
                )
            except Exception as e:
                logger.error(
                    "celery_revoke_failed",
                    task_id=job.worker_id,
                    error=str(e),
                )

        # Update job status
        job.status = ProcessingStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        job.error_message = "Erzwungen beendet durch Admin (SIGKILL)"

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=None,
            action="force_kill_job",
            action_details={
                "job_id": str(job_id),
                "worker_id": job.worker_id,
                "revoked": revoked,
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()

        logger.warning(
            "job_force_killed",
            job_id=str(job_id),
            admin_id=str(admin.id),
            worker_id=job.worker_id,
            revoked=revoked,
        )

        return JobActionResponse(
            success=True,
            job_id=job_id,
            action="force_kill",
            message="Auftrag wurde erzwungen beendet" + (" (Celery Task widerrufen)" if revoked else ""),
        )

    @staticmethod
    async def pause_job(
        db: AsyncSession,
        job_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> JobActionResponse:
        """Pause a job.

        Args:
            db: Database session
            job_id: Job to pause
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Action response
        """
        from app.db.schemas import JobActionResponse

        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="pause",
                message="Auftrag nicht gefunden",
            )

        if job.status not in [ProcessingStatus.PENDING, ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING]:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="pause",
                message="Nur aktive Auftraege koennen pausiert werden",
            )

        # We use a special status marker in the result field since ProcessingStatus doesn't have PAUSED
        if job.result is None:
            job.result = {}
        job.result["paused"] = True
        job.result["paused_at"] = datetime.now(timezone.utc).isoformat()
        job.result["paused_by"] = str(admin.id)

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=None,
            action="pause_job",
            action_details={
                "job_id": str(job_id),
                "previous_status": job.status.value if hasattr(job.status, 'value') else str(job.status),
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()

        logger.info(
            "job_paused",
            job_id=str(job_id),
            admin_id=str(admin.id),
        )

        return JobActionResponse(
            success=True,
            job_id=job_id,
            action="pause",
            message="Auftrag wurde pausiert",
        )

    @staticmethod
    async def resume_job(
        db: AsyncSession,
        job_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> JobActionResponse:
        """Resume a paused job.

        Args:
            db: Database session
            job_id: Job to resume
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Action response
        """
        from app.db.schemas import JobActionResponse

        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="resume",
                message="Auftrag nicht gefunden",
            )

        if not job.result or not job.result.get("paused"):
            return JobActionResponse(
                success=False,
                job_id=job_id,
                action="resume",
                message="Auftrag ist nicht pausiert",
            )

        # Remove pause marker
        job.result.pop("paused", None)
        job.result.pop("paused_at", None)
        job.result.pop("paused_by", None)
        job.result["resumed_at"] = datetime.now(timezone.utc).isoformat()
        job.result["resumed_by"] = str(admin.id)

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=None,
            action="resume_job",
            action_details={
                "job_id": str(job_id),
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()

        logger.info(
            "job_resumed",
            job_id=str(job_id),
            admin_id=str(admin.id),
        )

        return JobActionResponse(
            success=True,
            job_id=job_id,
            action="resume",
            message="Auftrag wurde fortgesetzt",
        )
