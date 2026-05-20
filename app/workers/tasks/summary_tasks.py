"""Celery Tasks fuer Dokumenten-Zusammenfassungen.

Automatische Generierung von Zusammenfassungen, Schluesselwoertern
und Einzeilern nach OCR-Verarbeitung.

Phase 2.2: Auto-Zusammenfassungen.
Feinpoliert und durchdacht.
"""

from __future__ import annotations

import asyncio
from typing import Dict, Union
from uuid import UUID

import structlog

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app, CPUTask

logger = structlog.get_logger(__name__)

# Type aliases fuer mypy strict mode
SummaryResultDict = Dict[str, Union[str, int, float, bool, None]]


# =============================================================================
# Einzel-Dokument Summary Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="summary.generate",
    queue="metadata",
    priority=5,
    acks_late=True,
    ignore_result=False,
    soft_time_limit=180,
    time_limit=200,
)
def generate_document_summary_task(
    document_id: str,
) -> SummaryResultDict:
    """Generiert Zusammenfassung fuer ein einzelnes Dokument.

    Wird nach OCR-Abschluss automatisch getriggert oder manuell
    ueber die API ausgeloest.

    Args:
        document_id: UUID des Dokuments als String

    Returns:
        Dict mit summary, keywords, one_liner, model, generated_at
    """
    from app.db.session import get_async_session_context
    from app.services.summarization.summary_service import SummaryService

    async def _generate() -> SummaryResultDict:
        async with get_async_session_context() as session:
            service = SummaryService(session)
            result = await service.generate_summary(
                document_id=UUID(document_id),
            )
            return result

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_generate())
        finally:
            loop.close()

        logger.info(
            "summary_task_completed",
            document_id=document_id,
            model=result.get("model"),
        )
        return result

    except ValueError as exc:
        # Dokument nicht gefunden oder kein Text
        logger.warning(
            "summary_task_skipped",
            document_id=document_id,
            reason=str(exc),
        )
        return {
            "status": "skipped",
            "document_id": document_id,
            "reason": str(exc),
        }
    except Exception as exc:
        logger.error(
            "summary_task_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise


# =============================================================================
# Batch Summary Task
# =============================================================================


@celery_app.task(
    base=CPUTask,
    name="summary.batch_generate",
    queue="metadata",
    priority=3,
    ignore_result=False,
    soft_time_limit=1800,
    time_limit=1900,
)
def batch_generate_summaries_task(
    company_id: str,
    limit: int = 50,
) -> SummaryResultDict:
    """Batch-Generierung fuer Dokumente ohne Summary.

    Verarbeitet bis zu `limit` Dokumente einer Company,
    die noch keine Zusammenfassung haben.

    Args:
        company_id: Mandanten-UUID als String
        limit: Maximale Anzahl zu verarbeitender Dokumente

    Returns:
        Dict mit Verarbeitungsstatistiken
    """
    from app.db.session import get_async_session_context
    from app.services.summarization.summary_service import SummaryService

    async def _batch_generate() -> int:
        async with get_async_session_context() as session:
            service = SummaryService(session)
            return await service.batch_generate(
                company_id=UUID(company_id),
                limit=limit,
            )

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            processed = loop.run_until_complete(_batch_generate())
        finally:
            loop.close()

        logger.info(
            "batch_summary_task_completed",
            company_id=company_id,
            processed=processed,
            limit=limit,
        )
        return {
            "status": "completed",
            "company_id": company_id,
            "processed": processed,
            "limit": limit,
        }

    except Exception as exc:
        logger.error(
            "batch_summary_task_failed",
            company_id=company_id,
            **safe_error_log(exc),
        )
        raise
