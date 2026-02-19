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
            async with session_factory() as session:
                service = PipelineChainService(session)
                chain_result = await service.process_document(
                    document_id=UUID(document_id),
                    company_id=UUID(company_id),
                    user_id=UUID(user_id) if user_id else None,
                    skip_kontierung=skip_kontierung,
                    skip_matching=skip_matching,
                )
                return chain_result.to_dict()
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
        logger.error(
            "pipeline_task_failed",
            document_id=document_id,
            company_id=company_id,
            **safe_error_log(exc),
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
