# -*- coding: utf-8 -*-
"""Duplikat-Erkennungs-Tasks fuer asynchrone Verarbeitung.

Asynchrone Celery-Tasks:
- Batch-Scan fuer alle Dokumente einer Firma
- Einzelne Dokument-Duplikat-Pruefung
- Bereinigung veralteter Duplikat-Flags

Feinpoliert und durchdacht - Async Duplikat-Erkennung.
"""

import asyncio
import uuid
from typing import Dict, Optional

import structlog

from app.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Helper um async Code in Celery auszufuehren."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.duplicate_detection_tasks.batch_scan_duplicates_task",
    acks_late=True,
    max_retries=3,
    default_retry_delay=300,
    queue="default",
)
def batch_scan_duplicates_task(
    self,  # type: ignore[no-untyped-def]
    company_id: str,
) -> Dict[str, object]:
    """
    Batch-Scan aller Dokumente einer Firma auf Duplikate.

    Args:
        company_id: Company-ID fuer den Batch-Scan

    Returns:
        Dict mit Scan-Ergebnis-Statistiken
    """
    return _run_async(_batch_scan_async(company_id=company_id))


@celery_app.task(
    bind=True,
    name="app.workers.tasks.duplicate_detection_tasks.check_document_duplicates_task",
    acks_late=True,
    max_retries=3,
    default_retry_delay=60,
    queue="default",
)
def check_document_duplicates_task(
    self,  # type: ignore[no-untyped-def]
    document_id: str,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """
    Einzelne Duplikat-Pruefung fuer ein Dokument.

    Args:
        document_id: Dokument-ID
        company_id: Optional Company-ID fuer Mandanten-Filter

    Returns:
        Dict mit Pruefungs-Ergebnis
    """
    return _run_async(
        _check_document_async(
            document_id=document_id,
            company_id=company_id,
        )
    )


@celery_app.task(
    bind=True,
    name="app.workers.tasks.duplicate_detection_tasks.cleanup_stale_duplicate_flags_task",
    acks_late=True,
    max_retries=2,
    default_retry_delay=120,
    queue="default",
)
def cleanup_stale_duplicate_flags_task(
    self,  # type: ignore[no-untyped-def]
) -> Dict[str, object]:
    """
    Bereinigt veraltete Duplikat-Flags in Dokument-Metadaten.

    Entfernt potential_duplicate Flags aus Metadaten, wenn das referenzierte
    Duplikat-Dokument geloescht wurde.

    Returns:
        Dict mit Bereinigungsstatistiken
    """
    return _run_async(_cleanup_stale_flags_async())


# =============================================================================
# Interne async Implementierungen
# =============================================================================


async def _batch_scan_async(company_id: str) -> Dict[str, object]:
    """Interne async Implementierung des Batch-Scans."""
    from sqlalchemy import select

    from app.db.models import Document
    from app.db.session import async_session_factory
    from app.services.ai.duplicate_detection_service import get_duplicate_detection_service

    async with async_session_factory() as db:
        try:
            company_uuid = uuid.UUID(company_id)
            service = get_duplicate_detection_service()

            # Alle Dokumente der Firma laden
            stmt = select(Document).where(
                Document.company_id == company_uuid,
                Document.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            documents = result.scalars().all()

            scanned = 0
            duplicates_found = 0
            errors = 0

            for doc in documents:
                try:
                    check_result = await service.check_document(
                        db=db,
                        document_id=doc.id,
                        company_id=company_uuid,
                        include_near=True,
                    )

                    if check_result.has_duplicates:
                        await service.create_duplicate_decision(
                            db=db,
                            document_id=doc.id,
                            check_result=check_result,
                            company_id=company_uuid,
                        )
                        duplicates_found += 1

                    scanned += 1

                except Exception as doc_error:
                    logger.warning(
                        "batch_scan_document_error",
                        document_id=str(doc.id),
                        error=str(type(doc_error).__name__),
                    )
                    errors += 1

            await db.commit()

            logger.info(
                "batch_scan_complete",
                company_id=company_id,
                scanned=scanned,
                duplicates_found=duplicates_found,
                errors=errors,
            )

            return {
                "erfolg": True,
                "company_id": company_id,
                "gescannt": scanned,
                "duplikate_gefunden": duplicates_found,
                "fehler": errors,
            }

        except Exception as e:
            await db.rollback()
            logger.error(
                "batch_scan_error",
                company_id=company_id,
                error=str(type(e).__name__),
            )
            return {
                "erfolg": False,
                "company_id": company_id,
                "fehler_meldung": str(type(e).__name__),
            }


async def _check_document_async(
    document_id: str,
    company_id: Optional[str] = None,
) -> Dict[str, object]:
    """Interne async Implementierung der Einzelpruefung."""
    from app.db.session import async_session_factory
    from app.services.ai.duplicate_detection_service import get_duplicate_detection_service

    async with async_session_factory() as db:
        try:
            doc_uuid = uuid.UUID(document_id)
            company_uuid = uuid.UUID(company_id) if company_id else None
            service = get_duplicate_detection_service()

            result = await service.check_document(
                db=db,
                document_id=doc_uuid,
                company_id=company_uuid,
            )

            if result.has_duplicates:
                await service.create_duplicate_decision(
                    db=db,
                    document_id=doc_uuid,
                    check_result=result,
                    company_id=company_uuid,
                )
                await db.commit()

            logger.info(
                "document_duplicate_check_complete",
                document_id=document_id,
                has_duplicates=result.has_duplicates,
                candidates_count=len(result.candidates),
                processing_time_ms=result.processing_time_ms,
            )

            return {
                "has_duplicates": result.has_duplicates,
                "candidates_count": len(result.candidates),
                "processing_time_ms": result.processing_time_ms,
                "document_id": document_id,
            }

        except Exception as e:
            await db.rollback()
            logger.error(
                "check_document_duplicates_error",
                document_id=document_id,
                error=str(type(e).__name__),
            )
            return {
                "has_duplicates": False,
                "document_id": document_id,
                "fehler": str(type(e).__name__),
            }


async def _cleanup_stale_flags_async() -> Dict[str, object]:
    """Interne async Implementierung der Flag-Bereinigung."""
    from sqlalchemy import select

    from app.db.models import Document
    from app.db.session import async_session_factory

    async with async_session_factory() as db:
        try:
            # Dokumente mit potential_duplicate Flag laden
            stmt = select(Document).where(
                Document.deleted_at.is_(None),
                Document.metadata.isnot(None),
            )
            result = await db.execute(stmt)
            all_docs = result.scalars().all()

            flagged_docs = [
                doc for doc in all_docs
                if (doc.metadata or {}).get("potential_duplicate") is True
            ]

            cleaned = 0

            for doc in flagged_docs:
                meta = doc.metadata or {}
                duplicate_of_str = meta.get("duplicate_of")

                if not duplicate_of_str:
                    continue

                # Pruefen ob referenziertes Dokument noch existiert
                try:
                    ref_uuid = uuid.UUID(str(duplicate_of_str))
                except ValueError:
                    # Ungueltige UUID -> Flag entfernen
                    meta.pop("potential_duplicate", None)
                    meta.pop("duplicate_of", None)
                    meta.pop("duplicate_similarity", None)
                    doc.metadata = meta
                    cleaned += 1
                    continue

                ref_stmt = select(Document).where(
                    Document.id == ref_uuid,
                    Document.deleted_at.is_(None),
                )
                ref_result = await db.execute(ref_stmt)
                ref_doc = ref_result.scalar_one_or_none()

                if ref_doc is None:
                    # Referenziertes Dokument geloescht -> Flag entfernen
                    meta.pop("potential_duplicate", None)
                    meta.pop("duplicate_of", None)
                    meta.pop("duplicate_similarity", None)
                    doc.metadata = meta
                    cleaned += 1

            await db.commit()

            logger.info(
                "cleanup_stale_flags_complete",
                flagged_count=len(flagged_docs),
                cleaned=cleaned,
            )

            return {
                "erfolg": True,
                "geprueft": len(flagged_docs),
                "bereinigt": cleaned,
            }

        except Exception as e:
            await db.rollback()
            logger.error(
                "cleanup_stale_flags_error",
                error=str(type(e).__name__),
            )
            return {
                "erfolg": False,
                "fehler": str(type(e).__name__),
            }
