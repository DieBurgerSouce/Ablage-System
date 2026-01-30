# -*- coding: utf-8 -*-
"""
Batch Job Service für Ablage-System OCR.

Verwaltet Batch-Verarbeitungsjobs mit:
- Erstellung und Tracking von Batch-Jobs
- Fortschrittsverfolgung und Zeitschätzung
- Pause/Resume-Funktionalität
- Webhook-Benachrichtigungen

Feinpoliert und durchdacht - Enterprise-grade Batch Management.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import BatchJob, Document, ProcessingStatus
from app.core.safe_errors import safe_error_log
from app.services.webhook_dispatcher import (

    get_webhook_dispatcher,
    WebhookEventType
)

logger = structlog.get_logger(__name__)


class BatchJobService:
    """Service für Batch-Job-Verwaltung."""

    async def create_batch_job(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_ids: List[UUID],
        job_type: str = "ocr",
        backend: str = "auto",
        language: str = "de",
        priority: int = 5,
        options: Optional[Dict[str, Any]] = None
    ) -> BatchJob:
        """
        Erstellt einen neuen Batch-Job.

        Args:
            db: Datenbank-Session
            user_id: Benutzer-ID
            document_ids: Liste der Dokument-IDs
            job_type: Job-Typ (ocr, embedding, validation)
            backend: OCR-Backend
            language: Zielsprache
            priority: Priorität (1-10, 1=höchste)
            options: Zusätzliche Optionen

        Returns:
            Erstellter BatchJob
        """
        # Schätze Verarbeitungszeit basierend auf historischen Daten
        estimated_time = await self._estimate_processing_time(
            db, user_id, len(document_ids), job_type, backend
        )

        batch_job = BatchJob(
            user_id=user_id,
            job_type=job_type,
            status=ProcessingStatus.QUEUED,
            priority=priority,
            total_documents=len(document_ids),
            document_ids=[str(doc_id) for doc_id in document_ids],
            backend=backend,
            language=language,
            options=options or {},
            estimated_completion=(
                datetime.now(timezone.utc) + timedelta(seconds=estimated_time)
                if estimated_time else None
            )
        )

        db.add(batch_job)
        await db.commit()
        await db.refresh(batch_job)

        logger.info(
            "batch_job_created",
            batch_id=str(batch_job.id)[:8],
            user_id=str(user_id)[:8],
            total_documents=len(document_ids),
            job_type=job_type
        )

        return batch_job

    async def start_batch_job(
        self,
        db: AsyncSession,
        batch_id: UUID,
        celery_task_id: Optional[str] = None
    ) -> Optional[BatchJob]:
        """Startet einen Batch-Job."""
        batch_job = await self._get_batch_job(db, batch_id)
        if not batch_job:
            return None

        batch_job.status = ProcessingStatus.PROCESSING
        batch_job.started_at = datetime.now(timezone.utc)
        batch_job.message = "Batch-Verarbeitung gestartet"
        if celery_task_id:
            batch_job.celery_task_id = celery_task_id

        await db.commit()

        logger.info(
            "batch_job_started",
            batch_id=str(batch_id)[:8],
            celery_task_id=celery_task_id
        )

        return batch_job

    async def update_progress(
        self,
        db: AsyncSession,
        batch_id: UUID,
        processed: int,
        failed: int = 0,
        current_document: Optional[str] = None,
        message: Optional[str] = None
    ) -> Optional[BatchJob]:
        """
        Aktualisiert den Fortschritt eines Batch-Jobs.

        Args:
            db: Datenbank-Session
            batch_id: Batch-Job-ID
            processed: Anzahl verarbeiteter Dokumente
            failed: Anzahl fehlgeschlagener Dokumente
            current_document: Aktuell verarbeitetes Dokument
            message: Status-Nachricht
        """
        batch_job = await self._get_batch_job(db, batch_id)
        if not batch_job:
            return None

        batch_job.processed_documents = processed
        batch_job.failed_documents = failed
        batch_job.progress = int((processed / batch_job.total_documents) * 100) if batch_job.total_documents > 0 else 0

        if current_document:
            batch_job.current_document = current_document

        if message:
            batch_job.message = message
        else:
            batch_job.message = f"Verarbeite {processed}/{batch_job.total_documents} Dokumente..."

        # Aktualisiere Zeitschätzung basierend auf bisheriger Geschwindigkeit
        if processed > 0 and batch_job.started_at:
            elapsed = (datetime.now(timezone.utc) - batch_job.started_at).total_seconds()
            avg_time = elapsed / processed
            remaining = batch_job.total_documents - processed
            estimated_remaining = remaining * avg_time

            batch_job.avg_time_per_document_ms = int(avg_time * 1000)
            batch_job.estimated_completion = (
                datetime.now(timezone.utc) + timedelta(seconds=estimated_remaining)
            )

        await db.commit()
        return batch_job

    async def complete_batch_job(
        self,
        db: AsyncSession,
        batch_id: UUID,
        result_summary: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Optional[BatchJob]:
        """
        Markiert einen Batch-Job als abgeschlossen.

        Sendet auch Webhook-Benachrichtigung bei Abschluss.
        """
        batch_job = await self._get_batch_job(db, batch_id)
        if not batch_job:
            return None

        now = datetime.now(timezone.utc)
        batch_job.completed_at = now
        batch_job.progress = 100

        if error_message:
            batch_job.status = ProcessingStatus.FAILED
            batch_job.error_message = error_message
            batch_job.message = "Batch fehlgeschlagen"
        elif batch_job.failed_documents == batch_job.total_documents:
            batch_job.status = ProcessingStatus.FAILED
            batch_job.message = "Alle Dokumente fehlgeschlagen"
        else:
            batch_job.status = ProcessingStatus.COMPLETED
            batch_job.message = f"Batch abgeschlossen: {batch_job.processed_documents - batch_job.failed_documents}/{batch_job.total_documents} erfolgreich"

        # Berechne Gesamtverarbeitungszeit
        if batch_job.started_at:
            batch_job.total_processing_time_ms = int(
                (now - batch_job.started_at).total_seconds() * 1000
            )

        # Ergebnis-Zusammenfassung
        batch_job.result_summary = result_summary or {
            "total": batch_job.total_documents,
            "successful": batch_job.processed_documents - batch_job.failed_documents,
            "failed": batch_job.failed_documents,
            "processing_time_ms": batch_job.total_processing_time_ms
        }

        await db.commit()

        # Webhook-Benachrichtigung senden
        try:
            dispatcher = get_webhook_dispatcher()
            await dispatcher.dispatch_event(
                db=db,
                user_id=batch_job.user_id,
                event_type=WebhookEventType.BATCH_COMPLETED.value,
                payload={
                    "batch_id": str(batch_job.id),
                    "job_type": batch_job.job_type,
                    "status": batch_job.status,
                    "total_documents": batch_job.total_documents,
                    "successful": batch_job.processed_documents - batch_job.failed_documents,
                    "failed": batch_job.failed_documents,
                    "processing_time_ms": batch_job.total_processing_time_ms,
                    "completed_at": now.isoformat()
                }
            )
        except Exception as e:
            logger.warning(
                "batch_webhook_dispatch_failed",
                batch_id=str(batch_id)[:8],
                **safe_error_log(e)
            )

        logger.info(
            "batch_job_completed",
            batch_id=str(batch_id)[:8],
            status=batch_job.status,
            successful=batch_job.processed_documents - batch_job.failed_documents,
            failed=batch_job.failed_documents,
            duration_ms=batch_job.total_processing_time_ms
        )

        return batch_job

    async def pause_batch_job(
        self,
        db: AsyncSession,
        batch_id: UUID,
        user_id: UUID
    ) -> Optional[BatchJob]:
        """
        Pausiert einen laufenden Batch-Job.

        Nur Jobs im Status PROCESSING können pausiert werden.
        """
        batch_job = await self._get_batch_job(db, batch_id)
        if not batch_job:
            return None

        # Prüfe Berechtigung
        if batch_job.user_id != user_id:
            raise PermissionError("Keine Berechtigung zum Pausieren dieses Batch-Jobs")

        if batch_job.status != ProcessingStatus.PROCESSING:
            raise ValueError(f"Batch-Job kann nicht pausiert werden (Status: {batch_job.status})")

        batch_job.is_paused = True
        batch_job.paused_at = datetime.now(timezone.utc)
        batch_job.resume_from_index = batch_job.processed_documents
        batch_job.message = "Batch pausiert"

        await db.commit()

        logger.info(
            "batch_job_paused",
            batch_id=str(batch_id)[:8],
            paused_at_document=batch_job.processed_documents
        )

        return batch_job

    async def resume_batch_job(
        self,
        db: AsyncSession,
        batch_id: UUID,
        user_id: UUID
    ) -> Optional[BatchJob]:
        """
        Setzt einen pausierten Batch-Job fort.
        """
        batch_job = await self._get_batch_job(db, batch_id)
        if not batch_job:
            return None

        # Prüfe Berechtigung
        if batch_job.user_id != user_id:
            raise PermissionError("Keine Berechtigung zum Fortsetzen dieses Batch-Jobs")

        if not batch_job.is_paused:
            raise ValueError("Batch-Job ist nicht pausiert")

        batch_job.is_paused = False
        batch_job.paused_at = None
        batch_job.message = f"Batch fortgesetzt ab Dokument {batch_job.resume_from_index + 1}"

        await db.commit()

        logger.info(
            "batch_job_resumed",
            batch_id=str(batch_id)[:8],
            resume_from=batch_job.resume_from_index
        )

        return batch_job

    async def cancel_batch_job(
        self,
        db: AsyncSession,
        batch_id: UUID,
        user_id: UUID
    ) -> Optional[BatchJob]:
        """Bricht einen Batch-Job ab."""
        batch_job = await self._get_batch_job(db, batch_id)
        if not batch_job:
            return None

        # Prüfe Berechtigung
        if batch_job.user_id != user_id:
            raise PermissionError("Keine Berechtigung zum Abbrechen dieses Batch-Jobs")

        if batch_job.status in [ProcessingStatus.COMPLETED, ProcessingStatus.CANCELLED]:
            raise ValueError(f"Batch-Job kann nicht abgebrochen werden (Status: {batch_job.status})")

        batch_job.status = ProcessingStatus.CANCELLED
        batch_job.completed_at = datetime.now(timezone.utc)
        batch_job.message = f"Batch abgebrochen nach {batch_job.processed_documents} Dokumenten"

        await db.commit()

        logger.info(
            "batch_job_cancelled",
            batch_id=str(batch_id)[:8],
            processed_before_cancel=batch_job.processed_documents
        )

        return batch_job

    def _batch_job_to_dict(self, batch_job: BatchJob) -> Dict[str, Any]:
        """Konvertiert ein BatchJob-Objekt zu einem Dictionary (vermeidet N+1 Queries)."""
        remaining_time = None
        if batch_job.estimated_completion and batch_job.status == ProcessingStatus.PROCESSING:
            remaining = (batch_job.estimated_completion - datetime.now(timezone.utc)).total_seconds()
            remaining_time = max(0, int(remaining))

        return {
            "id": str(batch_job.id),
            "job_type": batch_job.job_type,
            "status": batch_job.status,
            "priority": batch_job.priority,
            "total_documents": batch_job.total_documents,
            "processed_documents": batch_job.processed_documents,
            "failed_documents": batch_job.failed_documents,
            "successful_documents": batch_job.processed_documents - batch_job.failed_documents,
            "progress": batch_job.progress,
            "current_document": batch_job.current_document,
            "message": batch_job.message,
            "backend": batch_job.backend,
            "language": batch_job.language,
            "is_paused": batch_job.is_paused,
            "created_at": batch_job.created_at.isoformat() if batch_job.created_at else None,
            "started_at": batch_job.started_at.isoformat() if batch_job.started_at else None,
            "completed_at": batch_job.completed_at.isoformat() if batch_job.completed_at else None,
            "estimated_completion": batch_job.estimated_completion.isoformat() if batch_job.estimated_completion else None,
            "remaining_time_seconds": remaining_time,
            "avg_time_per_document_ms": batch_job.avg_time_per_document_ms,
            "total_processing_time_ms": batch_job.total_processing_time_ms,
            "result_summary": batch_job.result_summary
        }

    async def get_batch_job(
        self,
        db: AsyncSession,
        batch_id: UUID,
        user_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Gibt detaillierte Informationen zu einem Batch-Job zurück.
        """
        batch_job = await self._get_batch_job(db, batch_id)
        if not batch_job:
            return None

        # Prüfe Berechtigung
        if batch_job.user_id != user_id:
            return None

        return self._batch_job_to_dict(batch_job)

    async def list_batch_jobs(
        self,
        db: AsyncSession,
        user_id: UUID,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Listet Batch-Jobs eines Benutzers auf.
        """
        # Basis-Query
        query = select(BatchJob).where(BatchJob.user_id == user_id)

        if status:
            query = query.where(BatchJob.status == status)
        if job_type:
            query = query.where(BatchJob.job_type == job_type)

        # Gesamt-Anzahl
        count_query = select(func.count(BatchJob.id)).where(BatchJob.user_id == user_id)
        if status:
            count_query = count_query.where(BatchJob.status == status)
        if job_type:
            count_query = count_query.where(BatchJob.job_type == job_type)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginated results
        query = query.order_by(desc(BatchJob.created_at)).offset(offset).limit(limit)
        result = await db.execute(query)
        batch_jobs = list(result.scalars().all())

        # Direkte Konvertierung ohne erneute DB-Abfragen (N+1 Fix)
        return {
            "total": total,
            "batch_jobs": [
                self._batch_job_to_dict(job)
                for job in batch_jobs
            ]
        }

    async def get_active_batch_jobs(
        self,
        db: AsyncSession,
        user_id: UUID
    ) -> List[Dict[str, Any]]:
        """Gibt alle aktiven (laufenden/pausierten) Batch-Jobs zurück."""
        query = select(BatchJob).where(
            and_(
                BatchJob.user_id == user_id,
                BatchJob.status.in_([
                    ProcessingStatus.QUEUED,
                    ProcessingStatus.PROCESSING
                ])
            )
        ).order_by(BatchJob.priority, BatchJob.created_at)

        result = await db.execute(query)
        batch_jobs = list(result.scalars().all())

        # Direkte Konvertierung ohne erneute DB-Abfragen (N+1 Fix)
        return [
            self._batch_job_to_dict(job)
            for job in batch_jobs
        ]

    async def _get_batch_job(
        self,
        db: AsyncSession,
        batch_id: UUID
    ) -> Optional[BatchJob]:
        """Holt einen Batch-Job aus der Datenbank."""
        result = await db.execute(
            select(BatchJob).where(BatchJob.id == batch_id)
        )
        return result.scalar_one_or_none()

    async def _estimate_processing_time(
        self,
        db: AsyncSession,
        user_id: UUID,
        document_count: int,
        job_type: str,
        backend: str
    ) -> Optional[int]:
        """
        Schätzt Verarbeitungszeit basierend auf historischen Daten.

        Returns:
            Geschätzte Zeit in Sekunden oder None
        """
        # Suche abgeschlossene Jobs mit gleichem Typ/Backend
        query = select(
            func.avg(BatchJob.avg_time_per_document_ms)
        ).where(
            and_(
                BatchJob.user_id == user_id,
                BatchJob.job_type == job_type,
                BatchJob.status == ProcessingStatus.COMPLETED,
                BatchJob.avg_time_per_document_ms.isnot(None)
            )
        )

        if backend != "auto":
            query = query.where(BatchJob.backend == backend)

        result = await db.execute(query)
        avg_time_ms = result.scalar()

        if avg_time_ms:
            # Schätzung basierend auf historischen Daten
            estimated_ms = avg_time_ms * document_count
            return int(estimated_ms / 1000)  # In Sekunden

        # Fallback: Standardschätzung (3s pro Dokument für OCR)
        default_times = {
            "ocr": 3000,
            "embedding": 500,
            "validation": 200,
            "export": 100
        }
        default_ms = default_times.get(job_type, 1000)
        return int((default_ms * document_count) / 1000)


# Singleton
_batch_job_service: Optional[BatchJobService] = None


def get_batch_job_service() -> BatchJobService:
    """Gibt BatchJobService-Singleton zurück."""
    global _batch_job_service
    if _batch_job_service is None:
        _batch_job_service = BatchJobService()
    return _batch_job_service
