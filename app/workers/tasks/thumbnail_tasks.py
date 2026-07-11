"""Thumbnail Generation Tasks for Celery.

Generiert Vorschaubilder für Dokumente nach dem Upload oder OCR.
"""

from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import UUID
import asyncio

import structlog
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from app.workers.celery_app import celery_app, CPUTask
from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.db.models import Document
from app.services.thumbnail_service import get_thumbnail_service
from app.services.storage_service import get_storage_service
from app.core.safe_errors import safe_error_detail

logger = structlog.get_logger(__name__)

# Database session factory
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
from contextlib import asynccontextmanager

from app.db.session import arm_rls_bypass

_pool_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def async_session_maker():
    """Pool-Session mit session-level RLS-Bypass (F-16-Muster, 2026-07-11).

    Behaelt den modul-eigenen Engine-Pool; der Bypass-GUC haftet an dessen
    Verbindungen (gewollt: alle Tasks hier sind systemische Prozessoren).
    Ohne Bypass sahen diese Tasks nach den RLS-Migrationen 272-274 still
    0 Zeilen bzw. scheiterten an documents-INSERTs.
    """
    async with _pool_session_maker() as session:
        await arm_rls_bypass(session)
        yield session


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.thumbnail_tasks.generate_thumbnail_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
)
def generate_thumbnail_task(
    self,
    document_id: str,
    generate_preview: bool = True,
) -> Dict[str, Any]:
    """Generate thumbnail and preview for a document.

    Args:
        document_id: Document UUID as string
        generate_preview: Also generate larger preview image

    Returns:
        Dictionary with generation results
    """
    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)
    task_id = self.request.id

    logger.info(
        "thumbnail_generation_starting",
        task_id=task_id,
        document_id=document_id,
    )

    async def generate_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            try:
                # Get document
                result = await session.execute(
                    select(Document).where(Document.id == doc_uuid)
                )
                document = result.scalar_one_or_none()

                if not document:
                    logger.warning(
                        "document_not_found_for_thumbnail",
                        document_id=document_id,
                    )
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "Dokument nicht gefunden",
                    }

                if not document.file_path:
                    return {
                        "success": False,
                        "document_id": document_id,
                        "error": "Kein Dateipfad vorhanden",
                    }

                thumbnail_service = get_thumbnail_service()
                storage_service = get_storage_service()

                # Generate thumbnail
                thumbnail_data = await thumbnail_service.generate_thumbnail(
                    file_path=document.file_path,
                    document_id=document_id,
                )

                thumbnail_key = None
                if thumbnail_data:
                    try:
                        thumbnail_key = await storage_service.upload_thumbnail(
                            thumbnail_data=thumbnail_data,
                            document_id=document_id,
                            format="webp",
                        )
                        document.thumbnail_key = thumbnail_key
                        logger.info(
                            "thumbnail_uploaded",
                            document_id=document_id,
                            key=thumbnail_key,
                        )
                    except Exception as e:
                        logger.warning(
                            "thumbnail_upload_failed",
                            document_id=document_id,
                            **safe_error_log(e),
                        )

                # Generate preview if requested
                preview_key = None
                if generate_preview:
                    preview_data = await thumbnail_service.generate_preview(
                        file_path=document.file_path,
                        document_id=document_id,
                    )

                    if preview_data:
                        try:
                            preview_key = f"{document_id}/preview.webp"
                            await storage_service.upload_thumbnail(
                                thumbnail_data=preview_data,
                                document_id=document_id,
                                format="webp",
                            )
                            # Store as preview key
                            document.preview_key = preview_key
                            logger.info(
                                "preview_uploaded",
                                document_id=document_id,
                                key=preview_key,
                            )
                        except Exception as e:
                            logger.warning(
                                "preview_upload_failed",
                                document_id=document_id,
                                **safe_error_log(e),
                            )

                # Update document
                document.thumbnail_generated_at = datetime.now(timezone.utc)
                await session.commit()

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                logger.info(
                    "thumbnail_generation_completed",
                    task_id=task_id,
                    document_id=document_id,
                    thumbnail_generated=thumbnail_key is not None,
                    preview_generated=preview_key is not None,
                    duration_seconds=processing_time,
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "thumbnail_key": thumbnail_key,
                    "preview_key": preview_key,
                    "processing_time_seconds": processing_time,
                }

            except Exception as e:
                logger.exception(
                    "thumbnail_generation_failed",
                    task_id=task_id,
                    document_id=document_id,
                    **safe_error_log(e),
                )
                raise

    # Run async generation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(generate_async())
    finally:
        loop.close()


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.thumbnail_tasks.batch_generate_thumbnails_task",
)
def batch_generate_thumbnails_task(
    self,
    document_ids: list,
    generate_preview: bool = True,
) -> Dict[str, Any]:
    """Batch generate thumbnails for multiple documents.

    Args:
        document_ids: List of document UUIDs
        generate_preview: Also generate larger preview images

    Returns:
        Dictionary with batch results
    """
    task_id = self.request.id

    logger.info(
        "batch_thumbnail_starting",
        task_id=task_id,
        document_count=len(document_ids),
    )

    results = []
    for doc_id in document_ids:
        try:
            result = generate_thumbnail_task.apply(
                args=[doc_id, generate_preview]
            ).get(timeout=120)
            results.append(result)
        except Exception as e:
            logger.warning(
                "batch_thumbnail_single_failure",
                document_id=doc_id,
                **safe_error_log(e),
            )
            results.append({
                "success": False,
                "document_id": doc_id,
                "error": safe_error_detail(e, "Vorgang"),
            })

    successful = sum(1 for r in results if r.get("success", False))

    logger.info(
        "batch_thumbnail_completed",
        task_id=task_id,
        documents_processed=len(results),
        successful=successful,
    )

    return {
        "success": True,
        "documents_processed": len(results),
        "successful": successful,
        "failed": len(results) - successful,
        "results": results,
    }


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.thumbnail_tasks.regenerate_missing_thumbnails_task",
)
def regenerate_missing_thumbnails_task(
    self,
    owner_id: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """Regenerate thumbnails for documents missing them.

    Args:
        owner_id: Optional owner filter
        limit: Maximum documents to process

    Returns:
        Dictionary with regeneration results
    """
    task_id = self.request.id

    logger.info(
        "regenerate_missing_thumbnails_starting",
        task_id=task_id,
        owner_id=owner_id,
        limit=limit,
    )

    async def find_missing_async() -> list:
        async with async_session_maker() as session:
            query = select(Document.id).where(
                Document.thumbnail_key.is_(None),
                Document.file_path.isnot(None),
                Document.deleted_at.is_(None),
            )

            if owner_id:
                query = query.where(Document.owner_id == UUID(owner_id))

            query = query.limit(limit)
            result = await session.execute(query)
            return [str(row[0]) for row in result.fetchall()]

    # Get documents missing thumbnails
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        doc_ids = loop.run_until_complete(find_missing_async())
    finally:
        loop.close()

    if not doc_ids:
        return {
            "success": True,
            "message": "Keine Dokumente ohne Thumbnail gefunden",
            "documents_processed": 0,
        }

    # Queue batch task
    batch_result = batch_generate_thumbnails_task.apply_async(
        args=[doc_ids, True],
        countdown=5,
    )

    return {
        "success": True,
        "batch_task_id": batch_result.id,
        "documents_queued": len(doc_ids),
        "message": f"{len(doc_ids)} Dokumente zur Thumbnail-Generierung eingereiht",
    }
