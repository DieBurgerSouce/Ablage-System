# -*- coding: utf-8 -*-
"""Celery Tasks fuer Barcode/QR-Code-Erkennung.

Asynchrone Barcode-Erkennung:
- Erkennung bei Dokument-Upload
- Erneute Erkennung bei Bedarf
- Batch-Erkennung

Feinpoliert und durchdacht - Async Barcode Detection.
"""

import asyncio
from typing import Optional
from uuid import UUID

import structlog
from celery import shared_task

from app.core.safe_errors import safe_error_log
from app.db.session import async_session_factory

logger = structlog.get_logger(__name__)


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Helper um async Code in Celery auszufuehren."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(
    name="app.workers.tasks.barcode_tasks.detect_barcodes_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def detect_barcodes_task(
    self,  # type: ignore[no-untyped-def]
    document_id: str,
    company_id: str,
    redetect: bool = False,
) -> dict:
    """
    Asynchrone Barcode/QR-Code-Erkennung fuer ein Dokument.

    Args:
        document_id: Dokument-ID
        company_id: Company-ID (Multi-Tenant)
        redetect: Ob alte Erkennungen geloescht werden sollen

    Returns:
        Dict mit Ergebnis-Statistiken
    """
    return _run_async(
        _detect_barcodes(
            document_id=document_id,
            company_id=company_id,
            redetect=redetect,
        )
    )


async def _detect_barcodes(
    document_id: str,
    company_id: str,
    redetect: bool = False,
) -> dict:
    """Interne async Implementierung der Barcode-Erkennung."""
    from app.services.barcode_pipeline_service import BarcodePipelineService
    from app.services.storage_service import StorageService
    from app.db.models import Document

    from sqlalchemy import select

    async with async_session_factory() as session:
        try:
            # Dokument laden
            stmt = select(Document).where(Document.id == UUID(document_id))
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()

            if document is None:
                logger.warning(
                    "barcode_task_document_not_found",
                    document_id=document_id,
                )
                return {
                    "erfolg": False,
                    "fehler": "Dokument nicht gefunden",
                    "document_id": document_id,
                }

            # Bild-Seiten aus Storage laden
            storage = StorageService()
            image_pages = await storage.get_document_pages(document_id)

            if not image_pages:
                logger.warning(
                    "barcode_task_no_pages",
                    document_id=document_id,
                )
                return {
                    "erfolg": False,
                    "fehler": "Keine Seiten gefunden",
                    "document_id": document_id,
                }

            service = BarcodePipelineService(session)

            if redetect:
                detections = await service.redetect_document(
                    document_id=document_id,
                    company_id=company_id,
                    image_pages=image_pages,
                )
            else:
                detections = await service.detect_and_store(
                    document_id=document_id,
                    company_id=company_id,
                    image_pages=image_pages,
                )

            await session.commit()

            zahlungscodes = sum(
                1 for d in detections if d.category == "payment"
            )
            produktcodes = sum(
                1 for d in detections if d.category == "product"
            )

            logger.info(
                "barcode_task_complete",
                document_id=document_id,
                total_detections=len(detections),
                zahlungscodes=zahlungscodes,
                produktcodes=produktcodes,
                redetect=redetect,
            )

            return {
                "erfolg": True,
                "document_id": document_id,
                "erkennungen_gesamt": len(detections),
                "zahlungscodes": zahlungscodes,
                "produktcodes": produktcodes,
                "erneut_erkannt": redetect,
            }

        except Exception as e:
            await session.rollback()
            logger.error(
                "barcode_task_error",
                document_id=document_id,
                **safe_error_log(e),
            )
            return {
                "erfolg": False,
                "fehler": str(type(e).__name__),
                "document_id": document_id,
            }
