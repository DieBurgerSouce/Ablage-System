"""System Status Service.

Provides system monitoring and status information for the admin dashboard:
- GPU status and memory usage
- Job queue statistics
- Backend health checks (PostgreSQL, Redis, MinIO, Celery)
- Processing statistics
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import structlog
import redis.asyncio as redis

from app.db.models import ProcessingJob, Document, ProcessingStatus
from app.db.schemas import (
    GPUStatusAdmin,
    QueueStatus,
    BackendHealthStatus,
    SystemHealthStatus,
    ProcessingStats,
    SystemDashboard,
)
from app.core.config import settings
from app.core.safe_errors import safe_error_detail,  safe_error_log

logger = structlog.get_logger(__name__)


class SystemStatusService:
    """Service for system status monitoring."""

    @staticmethod
    async def get_gpu_status() -> GPUStatusAdmin:
        """Get detailed GPU status.

        Returns:
            GPU status with memory, utilization, and recommendations
        """
        try:
            # Import GPU manager
            from app.gpu_manager import GPUManager

            gpu_manager = GPUManager()
            status = gpu_manager.get_detailed_status()

            # Calculate memory usage percentage
            total_gb = status.get("total_gb", 0)
            allocated_gb = status.get("allocated_gb", 0)
            memory_usage_percent = (allocated_gb / total_gb * 100) if total_gb > 0 else 0

            # Generate recommendations
            recommendations = []
            if memory_usage_percent > 85:
                recommendations.append("VRAM-Auslastung kritisch hoch. Batch-Groesse reduzieren.")
            elif memory_usage_percent > 70:
                recommendations.append("VRAM-Auslastung erhoet. Monitoring empfohlen.")

            if not status.get("available", False):
                recommendations.append("GPU nicht verfuegbar. Fallback auf CPU aktiv.")

            return GPUStatusAdmin(
                available=status.get("available", False),
                gpu_name=status.get("gpu_name"),
                total_gb=total_gb,
                free_gb=status.get("free_gb", 0),
                allocated_gb=allocated_gb,
                utilization_percent=status.get("utilization_percent", 0),
                temperature_celsius=status.get("temperature_celsius"),
                memory_usage_percent=memory_usage_percent,
                current_allocations=status.get("current_allocations", []),
                recommendations=recommendations,
            )
        except Exception as e:
            logger.warning("gpu_status_failed", **safe_error_log(e))
            return GPUStatusAdmin(
                available=False,
                gpu_name=None,
                total_gb=0,
                free_gb=0,
                allocated_gb=0,
                utilization_percent=0,
                memory_usage_percent=0,
                current_allocations=[],
                recommendations=["GPU-Status konnte nicht abgerufen werden."],
            )

    @staticmethod
    async def get_queue_status(db: AsyncSession) -> QueueStatus:
        """Get job queue statistics.

        Args:
            db: Database session

        Returns:
            Queue status with job counts and timing
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Count jobs by status
        status_counts = {}
        for status in [ProcessingStatus.PENDING, ProcessingStatus.QUEUED, ProcessingStatus.PROCESSING]:
            result = await db.execute(
                select(func.count()).where(ProcessingJob.status == status)
            )
            status_counts[status.value] = result.scalar() or 0

        # Count completed today
        completed_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= today_start,
                )
            )
        )
        completed_today = completed_result.scalar() or 0

        # Count failed today
        failed_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.FAILED,
                    ProcessingJob.completed_at >= today_start,
                )
            )
        )
        failed_today = failed_result.scalar() or 0

        # Count cancelled today
        cancelled_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.CANCELLED,
                    ProcessingJob.completed_at >= today_start,
                )
            )
        )
        cancelled_today = cancelled_result.scalar() or 0

        # Calculate average wait time (pending jobs)
        avg_wait_result = await db.execute(
            select(func.avg(func.extract('epoch', func.now() - ProcessingJob.created_at)))
            .where(ProcessingJob.status.in_([ProcessingStatus.PENDING, ProcessingStatus.QUEUED]))
        )
        avg_wait_seconds = avg_wait_result.scalar() or 0

        # Calculate average processing time (completed jobs today)
        avg_processing_result = await db.execute(
            select(
                func.avg(
                    func.extract('epoch', ProcessingJob.completed_at - ProcessingJob.started_at)
                )
            ).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= today_start,
                    ProcessingJob.started_at.isnot(None),
                )
            )
        )
        avg_processing_seconds = avg_processing_result.scalar() or 0

        # Queue by priority
        priority_result = await db.execute(
            select(ProcessingJob.priority, func.count())
            .where(ProcessingJob.status.in_([ProcessingStatus.PENDING, ProcessingStatus.QUEUED]))
            .group_by(ProcessingJob.priority)
        )
        queue_by_priority = {row[0]: row[1] for row in priority_result.all()}

        # Queue by backend
        backend_result = await db.execute(
            select(ProcessingJob.backend, func.count())
            .where(ProcessingJob.status.in_([ProcessingStatus.PENDING, ProcessingStatus.QUEUED]))
            .group_by(ProcessingJob.backend)
        )
        queue_by_backend = {row[0] or "unspecified": row[1] for row in backend_result.all()}

        return QueueStatus(
            pending_jobs=status_counts.get("pending", 0) + status_counts.get("queued", 0),
            processing_jobs=status_counts.get("processing", 0),
            completed_today=completed_today,
            failed_today=failed_today,
            cancelled_today=cancelled_today,
            avg_wait_time_seconds=float(avg_wait_seconds),
            avg_processing_time_seconds=float(avg_processing_seconds),
            queue_by_priority=queue_by_priority,
            queue_by_backend=queue_by_backend,
        )

    @staticmethod
    async def check_postgresql_health(db: AsyncSession) -> BackendHealthStatus:
        """Check PostgreSQL database health.

        Args:
            db: Database session

        Returns:
            Health status for PostgreSQL
        """
        start_time = datetime.now(timezone.utc)
        try:
            result = await db.execute(select(func.now()))
            _ = result.scalar()
            latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            return BackendHealthStatus(
                name="PostgreSQL",
                status="healthy",
                latency_ms=latency_ms,
                message="Verbindung erfolgreich",
                last_check=datetime.now(timezone.utc),
            )
        except Exception as e:
            return BackendHealthStatus(
                name="PostgreSQL",
                status="unhealthy",
                latency_ms=None,
                message=safe_error_detail(e, "Fehler: "),
                last_check=datetime.now(timezone.utc),
            )

    @staticmethod
    async def check_redis_health() -> BackendHealthStatus:
        """Check Redis cache/queue health.

        Returns:
            Health status for Redis
        """
        start_time = datetime.now(timezone.utc)
        try:
            # Verwende zentrale settings - REDIS_URL wird automatisch konstruiert
            client = redis.from_url(settings.REDIS_URL)
            await client.ping()
            latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            await client.close()

            return BackendHealthStatus(
                name="Redis",
                status="healthy",
                latency_ms=latency_ms,
                message="Verbindung erfolgreich",
                last_check=datetime.now(timezone.utc),
            )
        except Exception as e:
            return BackendHealthStatus(
                name="Redis",
                status="unhealthy",
                latency_ms=None,
                message=safe_error_detail(e, "Fehler: "),
                last_check=datetime.now(timezone.utc),
            )

    @staticmethod
    async def check_minio_health() -> BackendHealthStatus:
        """Check MinIO storage health.

        Returns:
            Health status for MinIO
        """
        start_time = datetime.now(timezone.utc)
        try:
            from minio import Minio

            # Verwende zentrale settings statt getattr Fallbacks
            minio_secret = settings.MINIO_SECRET_KEY.get_secret_value() if settings.MINIO_SECRET_KEY else ""

            client = Minio(
                settings.MINIO_ENDPOINT,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=minio_secret,
                secure=settings.MINIO_SECURE,
            )
            # Try to list buckets as health check
            _ = client.list_buckets()
            latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            return BackendHealthStatus(
                name="MinIO",
                status="healthy",
                latency_ms=latency_ms,
                message="Verbindung erfolgreich",
                last_check=datetime.now(timezone.utc),
            )
        except Exception as e:
            return BackendHealthStatus(
                name="MinIO",
                status="unhealthy",
                latency_ms=None,
                message=safe_error_detail(e, "Fehler: "),
                last_check=datetime.now(timezone.utc),
            )

    @staticmethod
    async def check_celery_health() -> BackendHealthStatus:
        """Check Celery worker health.

        Returns:
            Health status for Celery
        """
        start_time = datetime.now(timezone.utc)
        try:
            from app.workers.celery_app import celery_app


            # Try to ping workers
            inspect = celery_app.control.inspect()
            active = inspect.active()

            if active:
                worker_count = len(active)
                latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
                return BackendHealthStatus(
                    name="Celery",
                    status="healthy",
                    latency_ms=latency_ms,
                    message=f"{worker_count} Worker aktiv",
                    last_check=datetime.now(timezone.utc),
                )
            else:
                return BackendHealthStatus(
                    name="Celery",
                    status="unhealthy",
                    latency_ms=None,
                    message="Keine Worker gefunden",
                    last_check=datetime.now(timezone.utc),
                )
        except Exception as e:
            return BackendHealthStatus(
                name="Celery",
                status="unknown",
                latency_ms=None,
                message=safe_error_detail(e, "Status unbekannt: "),
                last_check=datetime.now(timezone.utc),
            )

    @staticmethod
    async def get_health_status(db: AsyncSession) -> SystemHealthStatus:
        """Get overall system health status.

        Args:
            db: Database session

        Returns:
            Complete health status for all backends
        """
        # Run all health checks in parallel
        postgres_task = SystemStatusService.check_postgresql_health(db)
        redis_task = SystemStatusService.check_redis_health()
        minio_task = SystemStatusService.check_minio_health()
        celery_task = SystemStatusService.check_celery_health()

        postgres, redis_status, minio, celery = await asyncio.gather(
            postgres_task, redis_task, minio_task, celery_task
        )

        # Determine overall status
        statuses = [postgres.status, redis_status.status, minio.status, celery.status]
        unhealthy_count = statuses.count("unhealthy")
        unknown_count = statuses.count("unknown")

        if unhealthy_count == 0 and unknown_count == 0:
            overall = "healthy"
        elif unhealthy_count > 2 or (postgres.status == "unhealthy"):
            overall = "unhealthy"
        else:
            overall = "degraded"

        return SystemHealthStatus(
            postgresql=postgres,
            redis=redis_status,
            minio=minio,
            celery=celery,
            overall=overall,
        )

    @staticmethod
    async def get_processing_stats(
        db: AsyncSession,
        hours: int = 24,
    ) -> ProcessingStats:
        """Get processing statistics.

        Args:
            db: Database session
            hours: Hours to look back for statistics

        Returns:
            Processing statistics
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        hour_ago = now - timedelta(hours=1)
        lookback = now - timedelta(hours=hours)

        # Documents processed today
        today_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= today_start,
                )
            )
        )
        docs_today = today_result.scalar() or 0

        # Documents processed last hour
        hour_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= hour_ago,
                )
            )
        )
        docs_hour = hour_result.scalar() or 0

        # Success rate (last 24 hours)
        total_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status.in_([ProcessingStatus.COMPLETED, ProcessingStatus.FAILED]),
                    ProcessingJob.completed_at >= lookback,
                )
            )
        )
        total_finished = total_result.scalar() or 0

        success_result = await db.execute(
            select(func.count()).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= lookback,
                )
            )
        )
        total_success = success_result.scalar() or 0

        success_rate = (total_success / total_finished * 100) if total_finished > 0 else 100.0

        # Average processing time
        avg_time_result = await db.execute(
            select(
                func.avg(
                    func.extract('epoch', ProcessingJob.completed_at - ProcessingJob.started_at) * 1000
                )
            ).where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= lookback,
                    ProcessingJob.started_at.isnot(None),
                )
            )
        )
        avg_processing_ms = avg_time_result.scalar() or 0

        # Total documents
        total_docs_result = await db.execute(select(func.count()).select_from(Document))
        total_docs = total_docs_result.scalar() or 0

        # Total pages (sum of page_count)
        total_pages_result = await db.execute(
            select(func.sum(Document.page_count)).where(Document.page_count.isnot(None))
        )
        total_pages = total_pages_result.scalar() or 0

        # By backend
        backend_result = await db.execute(
            select(ProcessingJob.backend, func.count())
            .where(
                and_(
                    ProcessingJob.status == ProcessingStatus.COMPLETED,
                    ProcessingJob.completed_at >= lookback,
                )
            )
            .group_by(ProcessingJob.backend)
        )
        by_backend = {
            row[0] or "unknown": {"count": row[1]}
            for row in backend_result.all()
        }

        # By document type
        doc_type_result = await db.execute(
            select(Document.document_type, func.count())
            .group_by(Document.document_type)
        )
        by_doc_type = {row[0]: row[1] for row in doc_type_result.all()}

        # Hourly trend (last 24 hours)
        hourly_trend = []
        for i in range(24):
            hour_start = now - timedelta(hours=i + 1)
            hour_end = now - timedelta(hours=i)

            count_result = await db.execute(
                select(func.count()).where(
                    and_(
                        ProcessingJob.status == ProcessingStatus.COMPLETED,
                        ProcessingJob.completed_at >= hour_start,
                        ProcessingJob.completed_at < hour_end,
                    )
                )
            )
            hourly_trend.append({
                "hour": hour_start.isoformat(),
                "count": count_result.scalar() or 0,
            })

        hourly_trend.reverse()  # Oldest first

        return ProcessingStats(
            documents_processed_today=docs_today,
            documents_processed_hour=docs_hour,
            success_rate=success_rate,
            avg_processing_time_ms=float(avg_processing_ms),
            total_documents=total_docs,
            total_pages_processed=total_pages,
            by_backend=by_backend,
            by_document_type=by_doc_type,
            hourly_trend=hourly_trend,
        )

    @staticmethod
    async def get_dashboard(db: AsyncSession) -> SystemDashboard:
        """Get complete system dashboard data.

        Args:
            db: Database session

        Returns:
            Complete dashboard data
        """
        # Run all queries in parallel
        gpu_task = SystemStatusService.get_gpu_status()
        queue_task = SystemStatusService.get_queue_status(db)
        health_task = SystemStatusService.get_health_status(db)
        stats_task = SystemStatusService.get_processing_stats(db)

        gpu, queue, health, stats = await asyncio.gather(
            gpu_task, queue_task, health_task, stats_task
        )

        return SystemDashboard(
            gpu=gpu,
            queue=queue,
            health=health,
            processing=stats,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    async def clear_gpu_cache() -> bool:
        """Clear GPU memory cache.

        Returns:
            True if successful
        """
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("gpu_cache_cleared")
                return True
            return False
        except Exception as e:
            logger.error("gpu_cache_clear_failed", **safe_error_log(e))
            return False
