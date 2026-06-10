# -*- coding: utf-8 -*-
"""
Celery Tasks fuer die Document Processing Pipeline.

Async-Ausfuehrung der Pipeline-Chain via Celery Worker.

Tasks:
- process_document_pipeline: Einzeldokument durch komplette Pipeline-Chain
- retry_pipeline_step: Einzelnen Schritt der Pipeline wiederholen

Muster (wie im restlichen Projekt):
- celery_app.task Dekorator
- asyncio.run() fuer Async-Code aus synchronem Celery-Task
- Inline Engine-Erstellung mit create_async_engine + async_sessionmaker
- Fehlerbehandlung via self.retry() + safe_error_log
"""

import asyncio
from typing import Any, Dict, List, Optional, TypedDict

import structlog

from app.workers.celery_app import celery_app
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class PipelineProcessResult(TypedDict, total=False):
    """Ergebnis der Pipeline-Verarbeitung eines Einzeldokuments."""

    auto_processed: bool
    overall_confidence: float
    requires_review: bool
    total_duration_ms: int
    steps_completed: List[str]
    steps_failed: List[str]
    error: str


class PipelineRetryResult(TypedDict, total=False):
    """Ergebnis eines Pipeline-Schritt-Retries."""

    success: bool
    step_name: str
    error: str


# W1 Idempotenz: hoechstens ein aktiver Pipeline-Lauf pro Dokument.
PIPELINE_JOB_TYPE = "pipeline_chain"
# Claim gilt als verwaist, wenn aelter als ~3x time_limit (Worker-Crash o.ae.)
STALE_CLAIM_SECONDS = 600


async def _claim_pipeline_job(session, document_id: str, task_id: str):
    """Idempotenz-Claim via INSERT .. ON CONFLICT DO NOTHING.

    Nutzt den Partial-Unique-Index ``uq_processing_jobs_active_per_doc_type``
    (Migration 268): hoechstens ein ProcessingJob mit status queued/processing
    pro (document_id, job_type). Celery-Retries desselben Tasks (gleiche
    task_id) duerfen fortsetzen; verwaiste Claims werden uebernommen.

    Returns:
        (proceed, job_id): proceed=False -> Duplikat-Lauf, Task soll skippen.
    """
    from datetime import datetime, timedelta, timezone
    from uuid import UUID, uuid4

    from sqlalchemy import select, text, update
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from app.db.models import ProcessingJob

    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(ProcessingJob)
        .values(
            id=uuid4(),
            document_id=UUID(document_id),
            job_type=PIPELINE_JOB_TYPE,
            status="processing",
            worker_id=task_id,
            started_at=now,
        )
        .on_conflict_do_nothing(
            index_elements=["document_id", "job_type"],
            index_where=text("status IN ('queued', 'processing')"),
        )
        .returning(ProcessingJob.id)
    )
    claimed_id = (await session.execute(stmt)).scalar_one_or_none()
    if claimed_id is not None:
        await session.commit()
        return True, claimed_id

    existing = (
        (
            await session.execute(
                select(ProcessingJob)
                .where(
                    ProcessingJob.document_id == UUID(document_id),
                    ProcessingJob.job_type == PIPELINE_JOB_TYPE,
                    ProcessingJob.status.in_(("queued", "processing")),
                )
                .limit(1)
            )
        )
        .scalars()
        .first()
    )

    if existing is None:
        # Race: aktiver Job wurde zwischen INSERT und SELECT abgeschlossen.
        return True, None

    if existing.worker_id == task_id:
        # Celery-Retry desselben Tasks -> eigener Claim, fortsetzen.
        return True, existing.id

    started = existing.started_at
    if started is not None and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if started is None or (now - started) > timedelta(seconds=STALE_CLAIM_SECONDS):
        takeover = await session.execute(
            update(ProcessingJob)
            .where(
                ProcessingJob.id == existing.id,
                ProcessingJob.status.in_(("queued", "processing")),
            )
            .values(worker_id=task_id, started_at=now)
        )
        await session.commit()
        if takeover.rowcount:
            logger.warning(
                "pipeline_stale_claim_taken_over",
                document_id=document_id,
                previous_worker=existing.worker_id,
            )
            return True, existing.id

    return False, None


async def _finish_pipeline_job(session, job_id, *, success: bool, error: Optional[str] = None) -> None:
    """Markiert den Idempotenz-Claim als abgeschlossen/fehlgeschlagen."""
    if job_id is None:
        return

    from datetime import datetime, timezone

    from sqlalchemy import update

    from app.db.models import ProcessingJob

    await session.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job_id)
        .values(
            status="completed" if success else "failed",
            completed_at=datetime.now(timezone.utc),
            error_message=None if success else (error or "Pipeline fehlgeschlagen")[:2000],
        )
    )
    await session.commit()


@celery_app.task(
    name="pipeline.process_document",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
    queue="metadata",
)
def process_document_pipeline(
    self,
    document_id: str,
    company_id: str,
    user_id: Optional[str] = None,
    skip_kontierung: bool = False,
    skip_matching: bool = False,
) -> PipelineProcessResult:
    """
    Celery Task: Verarbeitet Dokument durch die komplette Pipeline-Chain.

    Fuehrt die End-to-End-Verarbeitungskette aus:
    Zero-Touch -> Klassifizierung -> Entity-Linking -> Kontierung -> 3-Way-Matching

    Args:
        document_id: Dokument-UUID als String
        company_id: Mandant-UUID als String (Multi-Tenant-Sicherheit)
        user_id: Optional - Ausfuehrender Benutzer als String-UUID
        skip_kontierung: Kontierungsschritt ueberspringen (z. B. bei Nicht-Buchhaltungs-Dokumenten)
        skip_matching: 3-Way-Matching ueberspringen

    Returns:
        Dict mit Ergebnis-Zusammenfassung (serialisiertes PipelineChainResult)

    Usage:
        process_document_pipeline.delay(str(doc_id), str(company_id))
        process_document_pipeline.apply_async(
            args=[str(doc_id), str(company_id)],
            countdown=5,
        )
    """
    logger.info(
        "pipeline_task_started",
        document_id=document_id,
        company_id=company_id,
        user_id=user_id,
        skip_kontierung=skip_kontierung,
        skip_matching=skip_matching,
    )

    # Celery-Retries behalten dieselbe task_id -> Claim bleibt unser eigener.
    # Bei Direktaufruf (Tests/eager) gibt es keine request.id.
    from uuid import uuid4 as _uuid4

    task_id = self.request.id or f"local-{_uuid4()}"
    claim_state: Dict[str, Any] = {"job_id": None}

    async def _run_pipeline() -> PipelineProcessResult:
        from uuid import UUID

        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        from app.core.config import settings
        from app.services.pipeline.pipeline_chain_service import PipelineChainService

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        try:
            # W1 Idempotenz: doppelte Zustellung/parallele Laeufe skippen
            # (Celery acks_late kann denselben Task mehrfach zustellen).
            async with session_factory() as session:
                proceed, job_id = await _claim_pipeline_job(session, document_id, task_id)
            claim_state["job_id"] = job_id
            if not proceed:
                logger.info(
                    "pipeline_task_skipped_duplicate",
                    document_id=document_id,
                    company_id=company_id,
                )
                return PipelineProcessResult(
                    auto_processed=False,
                    error="Pipeline-Lauf uebersprungen: bereits in Verarbeitung",
                )

            async with session_factory() as session:
                service = PipelineChainService(session)
                chain_result = await service.process_document(
                    document_id=UUID(document_id),
                    company_id=UUID(company_id),
                    user_id=UUID(user_id) if user_id else None,
                    skip_kontierung=skip_kontierung,
                    skip_matching=skip_matching,
                )
                result = chain_result.to_dict()

            async with session_factory() as session:
                await _finish_pipeline_job(session, job_id, success=True)
            return result
        finally:
            await engine.dispose()

    async def _persist_final_failure(error_text: str) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        from app.core.config import settings

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        try:
            async with session_factory() as session:
                await _finish_pipeline_job(
                    session, claim_state["job_id"], success=False, error=error_text
                )
        finally:
            await engine.dispose()

    try:
        result = asyncio.run(_run_pipeline())
        logger.info(
            "pipeline_task_completed",
            document_id=document_id,
            company_id=company_id,
            auto_processed=result.get("auto_processed", False),
            overall_confidence=result.get("overall_confidence", 0.0),
            requires_review=result.get("requires_review", False),
            total_duration_ms=result.get("total_duration_ms", 0),
        )
        return result
    except Exception as exc:
        max_retries = self.max_retries if self.max_retries is not None else 0
        final_attempt = self.request.retries >= max_retries
        # W1: exc_info=True - asyncio.run() schluckte vorher den Stacktrace
        # des eigentlichen Pipeline-Fehlers aus dem Log.
        logger.error(
            "pipeline_task_failed",
            document_id=document_id,
            company_id=company_id,
            retries=self.request.retries,
            final_attempt=final_attempt,
            **safe_error_log(exc),
            exc_info=True,
        )
        if final_attempt:
            # Claim freigeben (failed), damit ein spaeterer manueller Lauf
            # nicht am Partial-Unique-Index haengen bleibt.
            try:
                asyncio.run(_persist_final_failure(str(exc)))
            except Exception:
                logger.warning(
                    "pipeline_job_failure_persist_failed",
                    document_id=document_id,
                )
        raise self.retry(exc=exc)


@celery_app.task(
    name="pipeline.retry_step",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=90,
    time_limit=120,
    acks_late=True,
    queue="metadata",
)
def retry_pipeline_step(
    self,
    document_id: str,
    company_id: str,
    step_name: str,
) -> PipelineRetryResult:
    """
    Celery Task: Wiederholt einen einzelnen fehlgeschlagenen Pipeline-Schritt.

    Unterstuetzte Schritte: zero_touch, pipeline, kontierung, matching.

    Args:
        document_id: Dokument-UUID als String
        company_id: Mandant-UUID als String
        step_name: Name des zu wiederholenden Schritts

    Returns:
        Dict mit Ergebnis-Zusammenfassung nach dem Wiederholungsversuch

    Usage:
        retry_pipeline_step.delay(str(doc_id), str(company_id), "kontierung")
    """
    logger.info(
        "pipeline_retry_task_started",
        document_id=document_id,
        company_id=company_id,
        step_name=step_name,
    )

    async def _run_retry() -> PipelineRetryResult:
        from uuid import UUID

        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        from app.core.config import settings
        from app.services.pipeline.pipeline_chain_service import PipelineChainService

        engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        try:
            async with session_factory() as session:
                service = PipelineChainService(session)
                chain_result = await service.retry_failed_step(
                    document_id=UUID(document_id),
                    company_id=UUID(company_id),
                    step_name=step_name,
                )
                return chain_result.to_dict()
        finally:
            await engine.dispose()

    try:
        result = asyncio.run(_run_retry())
        logger.info(
            "pipeline_retry_task_completed",
            document_id=document_id,
            company_id=company_id,
            step_name=step_name,
            success=result.get("success", False),
        )
        return result
    except Exception as exc:
        logger.error(
            "pipeline_retry_task_failed",
            document_id=document_id,
            company_id=company_id,
            step_name=step_name,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)
