# -*- coding: utf-8 -*-
"""
DATEV Booking Celery Tasks.

Hintergrund-Jobs fuer automatische Buchungsverarbeitung:
- Einzeldokument-Buchung (nach OCR-Pipeline)
- Batch-Verarbeitung unbuchter Rechnungen (periodisch)

Feinpoliert und durchdacht - Zuverlaessige Auto-Buchung.
"""

import asyncio
from typing import Dict, List, Optional

import structlog
from celery import shared_task

from app.core.safe_errors import safe_error_log, safe_error_detail
from app.db.session import get_async_session_context
from app.workers.celery_app import celery_app as celery

logger = structlog.get_logger(__name__)


# =============================================================================
# SINGLE DOCUMENT BOOKING
# =============================================================================


@celery.task(
    name="app.workers.tasks.booking_tasks.process_auto_booking",
    queue="datev",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=180,
)
def process_auto_booking(
    self,  # type: ignore[no-untyped-def]
    document_id: str,
    company_id: str,
) -> Dict[str, object]:
    """
    Verarbeitet ein Dokument fuer automatische Buchung nach OCR.

    Wird nach Abschluss der OCR-Pipeline aufgerufen,
    wenn das Dokument als Rechnung klassifiziert wurde.

    Args:
        document_id: Dokument-UUID als String
        company_id: Mandanten-UUID als String

    Returns:
        Dict mit Ergebnis (routing, success, reason)
    """
    from uuid import UUID

    async def _process() -> Dict[str, object]:
        from app.services.datev.scan_to_booking_orchestrator import (
            get_scan_to_booking_orchestrator,
        )

        orchestrator = get_scan_to_booking_orchestrator()

        async with get_async_session_context() as db:
            result = await orchestrator.process_document_for_booking(
                document_id=UUID(document_id),
                company_id=UUID(company_id),
                db=db,
            )
            await db.commit()

            return {
                "document_id": document_id,
                "routing": result.routing,
                "success": result.success,
                "datev_booking_id": result.datev_booking_id,
                "plausibility_score": result.plausibility_score,
                "reason": result.reason,
                "processing_time_ms": result.processing_time_ms,
            }

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_process())
        finally:
            loop.close()

    except Exception as e:
        logger.error(
            "process_auto_booking_error",
            document_id=document_id,
            **safe_error_log(e),
        )
        # Retry bei transienten Fehlern
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            return {
                "document_id": document_id,
                "routing": "manual",
                "success": False,
                "reason": safe_error_detail(e, "Auto-Buchung"),
            }
        # Unreachable, but type-checker needs it
        return {
            "document_id": document_id,
            "routing": "manual",
            "success": False,
            "reason": safe_error_detail(e, "Auto-Buchung"),
        }


# =============================================================================
# BATCH PROCESSING
# =============================================================================


@celery.task(
    name="app.workers.tasks.booking_tasks.batch_process_bookings",
    queue="datev",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    soft_time_limit=600,
    time_limit=900,
)
def batch_process_bookings(
    self,  # type: ignore[no-untyped-def]
    company_id: str,
    batch_size: int = 50,
) -> Dict[str, object]:
    """
    Batch-Verarbeitung unbuchter Rechnungen.

    Findet OCR-fertige Rechnungen ohne Buchungsverarbeitung und
    fuehrt sie durch die Scan-to-Booking Pipeline.

    Laeuft periodisch alle 15 Minuten via Beat Schedule.

    Args:
        company_id: Mandanten-UUID als String
        batch_size: Maximale Dokumente pro Durchlauf

    Returns:
        Dict mit Statistik (auto_booked, review, manual, errors)
    """
    from uuid import UUID

    async def _batch() -> Dict[str, object]:
        from app.services.datev.scan_to_booking_orchestrator import (
            get_scan_to_booking_orchestrator,
        )

        orchestrator = get_scan_to_booking_orchestrator()

        async with get_async_session_context() as db:
            stats = await orchestrator.batch_process_unbooked(
                company_id=UUID(company_id),
                batch_size=batch_size,
                db=db,
            )
            return {
                "company_id": company_id,
                "batch_size": batch_size,
                **stats,
            }

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_batch())
        finally:
            loop.close()

    except Exception as e:
        logger.error(
            "batch_process_bookings_error",
            company_id=company_id,
            **safe_error_log(e),
        )
        return {
            "company_id": company_id,
            "error": safe_error_detail(e, "Batch-Buchung"),
        }


# =============================================================================
# BATCH ALL COMPANIES
# =============================================================================


@celery.task(
    name="app.workers.tasks.booking_tasks.batch_process_all_companies",
    queue="datev",
    bind=True,
    soft_time_limit=1800,
    time_limit=2400,
)
def batch_process_all_companies(
    self,  # type: ignore[no-untyped-def]
    batch_size: int = 50,
) -> Dict[str, object]:
    """
    Batch-Verarbeitung fuer alle Mandanten mit aktiver DATEV-Connection.

    Wird via Beat Schedule aufgerufen und iteriert ueber alle
    Mandanten mit aktiven DATEV-Verbindungen.

    Args:
        batch_size: Maximale Dokumente pro Mandant

    Returns:
        Dict mit Gesamtstatistik
    """
    async def _batch_all() -> Dict[str, object]:
        from sqlalchemy import select
        from app.db.models_datev import DATEVConnection

        total_stats = {
            "companies_processed": 0,
            "total_auto_booked": 0,
            "total_review": 0,
            "total_manual": 0,
            "total_errors": 0,
        }

        async with get_async_session_context() as db:
            # Alle aktiven DATEV-Verbindungen finden
            result = await db.execute(
                select(DATEVConnection.company_id).where(
                    DATEVConnection.is_active.is_(True),
                    DATEVConnection.connection_status == "connected",
                ).distinct()
            )
            company_ids = [row[0] for row in result.all()]

        for cid in company_ids:
            try:
                result = batch_process_bookings.apply(
                    args=[str(cid), batch_size],
                )
                if result and isinstance(result, dict):
                    total_stats["total_auto_booked"] += result.get("auto_booked", 0)
                    total_stats["total_review"] += result.get("review", 0)
                    total_stats["total_manual"] += result.get("manual", 0)
                    total_stats["total_errors"] += result.get("errors", 0)
                total_stats["companies_processed"] += 1
            except Exception as e:
                logger.warning(
                    "batch_all_company_error",
                    company_id=str(cid),
                    **safe_error_log(e),
                )
                total_stats["total_errors"] += 1

        logger.info("batch_process_all_complete", **total_stats)
        return total_stats

    try:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_batch_all())
        finally:
            loop.close()

    except Exception as e:
        logger.error(
            "batch_process_all_error",
            **safe_error_log(e),
        )
        return {"error": safe_error_detail(e, "Batch-Buchung alle Mandanten")}
