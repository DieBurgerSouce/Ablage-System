# -*- coding: utf-8 -*-
"""Celery Tasks fuer Semantische Suche.

Tasks:
- embed_document_task: Embedding fuer einzelnes Dokument (nach OCR)
- batch_embed_documents_task: Batch-Verarbeitung ohne Embedding
- reindex_embeddings_task: Vollstaendige Neuindexierung
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from celery import states

from app.workers.celery_app import celery_app, GPUTask, CPUTask
from app.core.config import settings
from app.core.safe_errors import safe_error_log
from app.db.session import get_async_session_context

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Fuehre async Coroutine in Celery-Kontext aus."""
    return asyncio.run(coro)


# ============================================================================
# Einzel-Embedding Task
# ============================================================================


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.semantic_search_tasks.embed_document_task",
    queue="embedding_normal",
    soft_time_limit=120,
    time_limit=180,
)
def embed_document_task(
    self,
    document_id: str,
) -> Dict[str, object]:
    """Generiere Embedding fuer ein einzelnes Dokument.

    Wird typischerweise nach OCR-Abschluss getriggert.
    Nutzt den SemanticSearchService fuer die Embedding-Generierung.

    Args:
        document_id: Dokument-UUID als String

    Returns:
        Dict mit Ergebnis der Embedding-Generierung
    """
    task_id = self.request.id
    doc_uuid = UUID(document_id)

    logger.info(
        "semantic_embed_task_starting",
        task_id=task_id,
        document_id=document_id,
    )

    async def _process() -> Dict[str, object]:
        from app.services.semantic_search_service import get_semantic_search_service

        service = get_semantic_search_service()

        async with get_async_session_context() as session:
            success = await service.embed_document(doc_uuid, session)

            return {
                "success": success,
                "document_id": document_id,
                "task_id": task_id,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }

    try:
        result = _run_async(_process())
        logger.info(
            "semantic_embed_task_completed",
            task_id=task_id,
            document_id=document_id,
            success=result["success"],
        )
        return result

    except Exception as e:
        logger.error(
            "semantic_embed_task_failed",
            task_id=task_id,
            document_id=document_id,
            **safe_error_log(e),
        )
        raise


# ============================================================================
# Batch-Embedding Task
# ============================================================================


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.semantic_search_tasks.batch_embed_documents_task",
    queue="embedding_normal",
    soft_time_limit=3600,
    time_limit=4200,
)
def batch_embed_documents_task(
    self,
    batch_size: int = 100,
) -> Dict[str, object]:
    """Batch-Verarbeitung: Embeddings fuer Dokumente ohne Vektor.

    Laeuft taeglich um 04:00 als Beat-Task und verarbeitet
    alle Dokumente die noch kein Embedding haben.

    Args:
        batch_size: Anzahl Dokumente pro Batch

    Returns:
        Dict mit Batch-Ergebnis
    """
    task_id = self.request.id

    logger.info(
        "semantic_batch_embed_starting",
        task_id=task_id,
        batch_size=batch_size,
    )

    async def _process() -> Dict[str, object]:
        from app.services.semantic_search_service import get_semantic_search_service

        service = get_semantic_search_service()
        total_processed = 0

        # Wiederhole bis keine unverarbeiteten Dokumente mehr
        while True:
            async with get_async_session_context() as session:
                processed = await service.batch_embed_unprocessed(
                    session, batch_size=batch_size
                )

            total_processed += processed

            # Fortschritt melden
            celery_app.backend.store_result(
                task_id,
                {
                    "current": total_processed,
                    "message": f"{total_processed} Dokumente verarbeitet",
                },
                states.STARTED,
            )

            if processed < batch_size:
                # Weniger als batch_size verarbeitet = fertig
                break

        return {
            "success": True,
            "total_processed": total_processed,
            "batch_size": batch_size,
            "task_id": task_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        result = _run_async(_process())
        logger.info(
            "semantic_batch_embed_completed",
            task_id=task_id,
            total_processed=result["total_processed"],
        )
        return result

    except Exception as e:
        logger.error(
            "semantic_batch_embed_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise


# ============================================================================
# Reindex Task
# ============================================================================


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.semantic_search_tasks.reindex_embeddings_task",
    queue="embedding_normal",
    soft_time_limit=7200,
    time_limit=8400,
)
def reindex_embeddings_task(
    self,
    batch_size: int = 50,
    force: bool = False,
) -> Dict[str, object]:
    """Vollstaendige Neuindexierung aller Embeddings.

    Regeneriert Embeddings fuer alle Dokumente mit extrahiertem Text.
    Nutzt Batch-Verarbeitung mit GPU-Speicher-Management.

    Args:
        batch_size: Dokumente pro Batch
        force: Auch bestehende Embeddings neu generieren

    Returns:
        Dict mit Reindex-Ergebnis
    """
    task_id = self.request.id

    logger.info(
        "semantic_reindex_starting",
        task_id=task_id,
        batch_size=batch_size,
        force=force,
    )

    async def _process() -> Dict[str, object]:
        from app.services.embedding_service import get_embedding_service
        from app.db.models import Document
        from sqlalchemy import select, func, text as sa_text

        embedding_service = get_embedding_service()
        total_processed = 0
        total_failed = 0
        offset = 0

        while True:
            async with get_async_session_context() as session:
                # Dokumente laden
                query = (
                    select(Document.id, Document.extracted_text)
                    .where(
                        Document.extracted_text.isnot(None),
                        Document.deleted_at.is_(None),
                        Document.status == "completed",
                    )
                    .order_by(Document.created_at)
                    .offset(offset)
                    .limit(batch_size)
                )

                if not force:
                    query = query.where(Document.embedding.is_(None))

                result = await session.execute(query)
                docs = result.fetchall()

                if not docs:
                    break

                texts = [row.extracted_text for row in docs]
                doc_ids = [row.id for row in docs]

                try:
                    embeddings = await embedding_service.generate_batch_embeddings_async(
                        texts, is_query=False
                    )

                    now = datetime.now(timezone.utc)
                    for doc_id, embedding in zip(doc_ids, embeddings):
                        if all(v == 0.0 for v in embedding):
                            total_failed += 1
                            continue

                        await session.execute(
                            sa_text("""
                                UPDATE documents
                                SET embedding = :embedding::vector,
                                    embedding_updated_at = :updated_at,
                                    embedding_model = :model
                                WHERE id = :doc_id
                            """),
                            {
                                "embedding": "[" + ",".join(str(x) for x in embedding) + "]",
                                "updated_at": now,
                                "model": settings.EMBEDDING_MODEL,
                                "doc_id": str(doc_id),
                            },
                        )
                        total_processed += 1

                    await session.commit()

                except Exception as e:
                    logger.error(
                        "reindex_batch_failed",
                        offset=offset,
                        **safe_error_log(e),
                    )
                    total_failed += len(docs)

                offset += batch_size

                # Fortschritt melden
                celery_app.backend.store_result(
                    task_id,
                    {
                        "current": total_processed,
                        "failed": total_failed,
                        "message": f"{total_processed} verarbeitet, {total_failed} fehlgeschlagen",
                    },
                    states.STARTED,
                )

        return {
            "success": True,
            "total_processed": total_processed,
            "total_failed": total_failed,
            "force": force,
            "task_id": task_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    try:
        result = _run_async(_process())
        logger.info(
            "semantic_reindex_completed",
            task_id=task_id,
            total_processed=result["total_processed"],
            total_failed=result["total_failed"],
        )
        return result

    except Exception as e:
        logger.error(
            "semantic_reindex_failed",
            task_id=task_id,
            **safe_error_log(e),
        )
        raise
