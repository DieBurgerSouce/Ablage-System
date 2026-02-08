# -*- coding: utf-8 -*-
"""
Celery Tasks for GL-Posting.

Background tasks:
- Auto-post documents after OCR pipeline
- Generate trial balance reports
- Generate EÜR reports
"""

from typing import Any, Dict, Optional
from uuid import UUID

import structlog
from celery import Task

from app.core.safe_errors import safe_error_log
from app.workers.celery_app import celery_app
from app.db.session import get_async_session
from app.services.accounting.gl_posting_service import GLPostingService
from app.services.accounting.euer_report_service import EUeRReportService

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="app.workers.tasks.gl_posting_tasks.auto_post_document",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
)
def auto_post_document_task(
    self: Task,
    company_id: str,
    document_id: str,
    confidence: float,
) -> Optional[str]:
    """
    Auto-posts a document if confidence >= 0.85.

    Args:
        company_id: Company UUID (str)
        document_id: Document UUID (str)
        confidence: Confidence score (0.0-1.0)

    Returns:
        Journal Entry ID (str) if posted, else None
    """
    from asyncio import run

    async def _run() -> Optional[str]:
        async with get_async_session() as db:
            service = GLPostingService(db)
            entry = await service.auto_post_from_pipeline(
                company_id=UUID(company_id),
                document_id=UUID(document_id),
                confidence=confidence,
            )
            await db.commit()
            return str(entry.id) if entry else None

    try:
        result = run(_run())
        logger.info(
            "auto_post_document_task_completed",
            document_id=document_id,
            entry_id=result,
        )
        return result
    except Exception as exc:
        logger.error(
            "auto_post_document_task_failed",
            document_id=document_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.gl_posting_tasks.generate_trial_balance",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_trial_balance_task(
    self: Task,
    company_id: str,
    fiscal_year: int,
    period: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generates trial balance report.

    Args:
        company_id: Company UUID (str)
        fiscal_year: Fiscal year
        period: Period 1-12 (optional)

    Returns:
        Trial balance data as dict
    """
    from asyncio import run

    async def _run() -> Dict[str, Any]:
        async with get_async_session() as db:
            service = GLPostingService(db)
            rows = await service.get_trial_balance(
                company_id=UUID(company_id),
                fiscal_year=fiscal_year,
                period=period,
            )
            return {
                "company_id": company_id,
                "fiscal_year": fiscal_year,
                "period": period,
                "rows": [
                    {
                        "account_number": r.account_number,
                        "account_name": r.account_name,
                        "total_debit": str(r.total_debit),
                        "total_credit": str(r.total_credit),
                        "balance": str(r.balance),
                    }
                    for r in rows
                ],
            }

    try:
        result = run(_run())
        logger.info(
            "generate_trial_balance_task_completed",
            company_id=company_id,
            fiscal_year=fiscal_year,
            row_count=len(result["rows"]),
        )
        return result
    except Exception as exc:
        logger.error(
            "generate_trial_balance_task_failed",
            company_id=company_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.workers.tasks.gl_posting_tasks.generate_euer",
    bind=True,
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_euer_task(
    self: Task,
    company_id: str,
    fiscal_year: int,
) -> Dict[str, Any]:
    """
    Generates EÜR report.

    Args:
        company_id: Company UUID (str)
        fiscal_year: Fiscal year

    Returns:
        EÜR data as dict
    """
    from asyncio import run

    async def _run() -> Dict[str, Any]:
        async with get_async_session() as db:
            service = EUeRReportService(db)
            report = await service.generate_euer(
                company_id=UUID(company_id),
                fiscal_year=fiscal_year,
            )
            return {
                "company_id": company_id,
                "fiscal_year": fiscal_year,
                "total_revenue": str(report.total_revenue),
                "total_expenses": str(report.total_expenses),
                "profit_loss": str(report.profit_loss),
            }

    try:
        result = run(_run())
        logger.info(
            "generate_euer_task_completed",
            company_id=company_id,
            fiscal_year=fiscal_year,
            profit_loss=result["profit_loss"],
        )
        return result
    except Exception as exc:
        logger.error(
            "generate_euer_task_failed",
            company_id=company_id,
            **safe_error_log(exc),
        )
        raise self.retry(exc=exc)
