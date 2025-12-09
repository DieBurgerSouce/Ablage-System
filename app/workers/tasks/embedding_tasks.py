"""Embedding generation tasks for Celery.

This module contains tasks for generating document embeddings:
- Single document embedding generation (triggered after OCR)
- Batch embedding generation for multiple documents
- Embedding updates when document text changes
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TypeVar, Coroutine
from uuid import UUID
import asyncio

import structlog
from celery import states
from celery.exceptions import SoftTimeLimitExceeded, Ignore
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update

import torch

from app.workers.celery_app import celery_app, GPUTask, CPUTask
from app.core.config import settings
from app.db.models import Document, ProcessingStatus
from app.services.embedding_service import get_embedding_service
from app.services.search_analytics_service import get_search_analytics_service
from app.core.cache import invalidate_on_document_change

logger = structlog.get_logger(__name__)


def _is_oom_error(exception: Exception) -> bool:
    """Prüfe ob Exception ein GPU OOM Error ist.

    Args:
        exception: Die zu prüfende Exception

    Returns:
        True wenn OOM-Fehler, sonst False
    """
    if torch.cuda.is_available() and isinstance(exception, torch.cuda.OutOfMemoryError):
        return True

    error_msg = str(exception).lower()
    oom_indicators = [
        "out of memory",
        "cuda out of memory",
        "oom",
        "memory allocation",
        "cannot allocate",
        "memory exhausted",
    ]
    return any(indicator in error_msg for indicator in oom_indicators)


async def _cleanup_gpu_memory() -> None:
    """GPU-Speicher aufräumen nach OOM oder bei Bedarf."""
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.debug("gpu_memory_cleaned_embedding_tasks")
        except Exception as e:
            logger.warning("gpu_cleanup_failed_embedding_tasks", error=str(e))

# Type variable for async return type
T = TypeVar('T')


def run_async_task(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine in a Celery task context.

    Uses asyncio.run() for proper event loop management in Python 3.7+.
    This is preferred over manual loop creation/management.

    Args:
        coro: Coroutine to execute

    Returns:
        Result of the coroutine
    """
    return asyncio.run(coro)

# Database session factory mit Worker-optimiertem Connection Pool
# Embedding-Tasks sind länger laufend, brauchen angepasste Timeouts
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_WORKER_POOL_SIZE,
    max_overflow=settings.DB_WORKER_MAX_OVERFLOW,
    pool_recycle=settings.DB_WORKER_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=False,
)
async_session_maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def update_task_progress(task_id: str, current: int, total: int, message: str) -> None:
    """Update task progress for real-time monitoring.

    Args:
        task_id: Celery task ID
        current: Current progress value
        total: Total progress value
        message: Progress message (German)
    """
    progress = int((current / total) * 100) if total > 0 else 0
    celery_app.backend.store_result(
        task_id,
        {
            "current": current,
            "total": total,
            "progress": progress,
            "message": message,
        },
        states.STARTED,
    )


# ==================== Embedding Generation Tasks ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.embedding_tasks.generate_document_embedding"
)
def generate_document_embedding(
    self,
    document_id: str,
    force_regenerate: bool = False
) -> Dict[str, Any]:
    """Generate embedding for a single document.

    This task is typically triggered after OCR processing completes.
    Uses GPU acceleration with multilingual-e5-large model.

    Args:
        document_id: Document UUID as string
        force_regenerate: Regenerate even if embedding exists

    Returns:
        Dictionary with embedding generation result
    """
    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)
    task_id = self.request.id

    logger.info(
        "embedding_task_starting",
        task_id=task_id,
        document_id=document_id,
        force_regenerate=force_regenerate
    )

    embedding_service = get_embedding_service()

    async def process_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            try:
                update_task_progress(task_id, 0, 100, "Lade Dokument...")

                # Get document from database
                result = await session.execute(
                    select(Document).where(Document.id == doc_uuid)
                )
                document = result.scalar_one_or_none()

                if not document:
                    raise ValueError(f"Dokument {document_id} nicht gefunden")

                if not document.extracted_text:
                    raise ValueError(
                        f"Dokument {document_id} hat keinen extrahierten Text"
                    )

                # Check if embedding already exists
                if document.embedding is not None and not force_regenerate:
                    logger.info(
                        "embedding_already_exists",
                        task_id=task_id,
                        document_id=document_id
                    )
                    return {
                        "success": True,
                        "document_id": document_id,
                        "skipped": True,
                        "message": "Embedding existiert bereits"
                    }

                update_task_progress(task_id, 30, 100, "Generiere Embedding...")

                # Generate embedding (async)
                embedding = await embedding_service.generate_embedding_async(
                    document.extracted_text,
                    is_query=False  # Document embedding, not query
                )

                update_task_progress(task_id, 80, 100, "Speichere Embedding...")

                # Update document with embedding
                document.embedding = embedding
                document.embedding_updated_at = datetime.now(timezone.utc)
                document.embedding_model = settings.EMBEDDING_MODEL

                await session.commit()

                # Cache Invalidation: Embedding wurde generiert, Search-Cache invalidieren
                try:
                    cache_result = await invalidate_on_document_change(
                        document_id=document_id,
                        change_type="embedding"
                    )
                    logger.debug(
                        "embedding_cache_invalidated",
                        document_id=document_id,
                        invalidated_keys=cache_result.get("total", 0)
                    )
                except Exception as cache_error:
                    # Cache-Invalidation sollte Embedding-Erfolg nicht blockieren
                    logger.warning(
                        "embedding_cache_invalidation_failed",
                        document_id=document_id,
                        error=str(cache_error)
                    )

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                processing_ms = int(processing_time * 1000)

                update_task_progress(task_id, 100, 100, "Embedding generiert!")

                logger.info(
                    "embedding_task_completed",
                    task_id=task_id,
                    document_id=document_id,
                    embedding_dimension=len(embedding),
                    duration_ms=processing_ms
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "embedding_dimension": len(embedding),
                    "model": settings.EMBEDDING_MODEL,
                    "processing_time_ms": processing_ms,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }

            except SoftTimeLimitExceeded:
                logger.error(
                    "embedding_task_timeout",
                    task_id=task_id,
                    document_id=document_id
                )
                raise Ignore()

            except Exception as e:
                # OOM-Handling: Bei GPU-Speichermangel aufräumen und mit Fallback retry
                if _is_oom_error(e):
                    logger.warning(
                        "embedding_task_oom",
                        task_id=task_id,
                        document_id=document_id,
                        error=str(e)
                    )
                    await _cleanup_gpu_memory()

                    # Versuche mit kleinerem Batch (falls Text zu lang)
                    # Der GPUTask retry-Mechanismus wird dies automatisch handhaben
                    raise

                logger.exception(
                    "embedding_task_failed",
                    task_id=task_id,
                    document_id=document_id,
                    error=str(e)
                )
                raise

            finally:
                # GPU-Speicher immer aufräumen nach Verarbeitung
                await _cleanup_gpu_memory()

    # Run async processing with proper event loop management
    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.embedding_tasks.batch_generate_embeddings"
)
def batch_generate_embeddings(
    self,
    document_ids: List[str],
    force_regenerate: bool = False,
    batch_size: Optional[int] = None
) -> Dict[str, Any]:
    """Generate embeddings for multiple documents in batch.

    Uses GPU batch processing for efficiency. Handles memory management
    with dynamic batch sizing based on available VRAM.

    Args:
        document_ids: List of document UUIDs as strings
        force_regenerate: Regenerate even if embeddings exist
        batch_size: Optional batch size (default from config)

    Returns:
        Dictionary with batch processing results
    """
    start_time = datetime.now(timezone.utc)
    task_id = self.request.id
    total_docs = len(document_ids)
    batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE

    logger.info(
        "batch_embedding_task_starting",
        task_id=task_id,
        document_count=total_docs,
        batch_size=batch_size
    )

    embedding_service = get_embedding_service()

    async def process_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            successful = 0
            failed = 0
            skipped = 0
            results = []

            # Process in batches for GPU efficiency
            for batch_start in range(0, total_docs, batch_size):
                batch_end = min(batch_start + batch_size, total_docs)
                batch_doc_ids = document_ids[batch_start:batch_end]

                update_task_progress(
                    task_id,
                    batch_start,
                    total_docs,
                    f"Verarbeite Dokumente {batch_start + 1}-{batch_end}/{total_docs}..."
                )

                # Load documents for this batch
                batch_uuids = [UUID(doc_id) for doc_id in batch_doc_ids]
                result = await session.execute(
                    select(Document).where(Document.id.in_(batch_uuids))
                )
                documents = {str(doc.id): doc for doc in result.scalars().all()}

                # Collect texts for batch embedding
                texts_to_embed = []
                doc_ids_to_embed = []

                for doc_id in batch_doc_ids:
                    doc = documents.get(doc_id)
                    if not doc:
                        logger.warning(
                            "document_not_found_in_batch",
                            document_id=doc_id
                        )
                        failed += 1
                        results.append({
                            "document_id": doc_id,
                            "success": False,
                            "error": "Dokument nicht gefunden"
                        })
                        continue

                    if not doc.extracted_text:
                        logger.warning(
                            "document_no_text",
                            document_id=doc_id
                        )
                        failed += 1
                        results.append({
                            "document_id": doc_id,
                            "success": False,
                            "error": "Kein extrahierter Text"
                        })
                        continue

                    if doc.embedding is not None and not force_regenerate:
                        skipped += 1
                        results.append({
                            "document_id": doc_id,
                            "success": True,
                            "skipped": True
                        })
                        continue

                    texts_to_embed.append(doc.extracted_text)
                    doc_ids_to_embed.append(doc_id)

                # Generate batch embeddings if any texts to process
                if texts_to_embed:
                    try:
                        embeddings = await embedding_service.generate_batch_embeddings_async(
                            texts_to_embed,
                            is_query=False
                        )

                        # Update documents with embeddings
                        now = datetime.now(timezone.utc)
                        for doc_id, embedding in zip(doc_ids_to_embed, embeddings):
                            doc = documents[doc_id]
                            doc.embedding = embedding
                            doc.embedding_updated_at = now
                            doc.embedding_model = settings.EMBEDDING_MODEL
                            successful += 1
                            results.append({
                                "document_id": doc_id,
                                "success": True,
                                "embedding_dimension": len(embedding)
                            })

                        await session.commit()

                    except Exception as e:
                        # OOM-Handling: Bei GPU-Speichermangel aufräumen
                        if _is_oom_error(e):
                            logger.warning(
                                "batch_embedding_oom",
                                task_id=task_id,
                                batch_start=batch_start,
                                batch_size=len(texts_to_embed),
                                error=str(e)
                            )
                            await _cleanup_gpu_memory()

                            # Bei OOM: Batch-Größe halbieren und einzeln verarbeiten
                            logger.info(
                                "batch_embedding_retry_individual",
                                task_id=task_id,
                                document_count=len(doc_ids_to_embed)
                            )
                            for doc_id, text in zip(doc_ids_to_embed, texts_to_embed):
                                try:
                                    embedding = await embedding_service.generate_embedding_async(
                                        text,
                                        is_query=False
                                    )
                                    doc = documents[doc_id]
                                    doc.embedding = embedding
                                    doc.embedding_updated_at = datetime.now(timezone.utc)
                                    doc.embedding_model = settings.EMBEDDING_MODEL
                                    successful += 1
                                    results.append({
                                        "document_id": doc_id,
                                        "success": True,
                                        "embedding_dimension": len(embedding),
                                        "fallback": "individual_after_oom"
                                    })
                                except Exception as ind_e:
                                    await _cleanup_gpu_memory()
                                    failed += 1
                                    results.append({
                                        "document_id": doc_id,
                                        "success": False,
                                        "error": f"OOM-Fallback fehlgeschlagen: {str(ind_e)}"
                                    })
                            await session.commit()
                        else:
                            logger.error(
                                "batch_embedding_error",
                                task_id=task_id,
                                batch_start=batch_start,
                                error=str(e)
                            )
                            # Mark all as failed
                            for doc_id in doc_ids_to_embed:
                                failed += 1
                                results.append({
                                    "document_id": doc_id,
                                    "success": False,
                                    "error": str(e)
                                })

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            update_task_progress(
                task_id,
                total_docs,
                total_docs,
                f"Abgeschlossen: {successful} erfolgreich, {skipped} uebersprungen, {failed} fehlgeschlagen"
            )

            logger.info(
                "batch_embedding_task_completed",
                task_id=task_id,
                total=total_docs,
                successful=successful,
                skipped=skipped,
                failed=failed,
                duration_seconds=processing_time
            )

            return {
                "success": True,
                "total_documents": total_docs,
                "successful": successful,
                "skipped": skipped,
                "failed": failed,
                "results": results,
                "model": settings.EMBEDDING_MODEL,
                "processing_time_seconds": processing_time,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

    # Run async processing with proper event loop management
    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.embedding_tasks.regenerate_all_embeddings"
)
def regenerate_all_embeddings(
    self,
    user_id: Optional[str] = None,
    batch_size: Optional[int] = None
) -> Dict[str, Any]:
    """Regenerate embeddings for all documents.

    Useful when switching to a new embedding model or after model updates.
    Can be filtered to a specific user's documents.

    Args:
        user_id: Optional user UUID to filter documents
        batch_size: Optional batch size

    Returns:
        Dictionary with regeneration results
    """
    start_time = datetime.now(timezone.utc)
    task_id = self.request.id
    batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE

    logger.info(
        "regenerate_all_embeddings_starting",
        task_id=task_id,
        user_id=user_id
    )

    async def process_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            # Build query to find all documents with extracted text
            query = select(Document.id).where(
                Document.extracted_text.isnot(None),
                Document.extracted_text != ""
            )

            if user_id:
                query = query.where(Document.owner_id == UUID(user_id))

            result = await session.execute(query)
            document_ids = [str(row[0]) for row in result.fetchall()]

            total_docs = len(document_ids)
            logger.info(
                "regenerate_found_documents",
                task_id=task_id,
                count=total_docs
            )

            if not document_ids:
                return {
                    "success": True,
                    "total_documents": 0,
                    "message": "Keine Dokumente zum Regenerieren gefunden"
                }

            # Use batch task for actual processing
            result = batch_generate_embeddings(
                document_ids=document_ids,
                force_regenerate=True,
                batch_size=batch_size
            )

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            logger.info(
                "regenerate_all_embeddings_completed",
                task_id=task_id,
                total=total_docs,
                duration_seconds=processing_time
            )

            return {
                "success": True,
                "total_documents": total_docs,
                "batch_result": result,
                "processing_time_seconds": processing_time,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

    # Run async processing with proper event loop management
    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.embedding_tasks.check_embedding_coverage"
)
def check_embedding_coverage(
    self,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Check how many documents have embeddings.

    Useful for monitoring embedding coverage and identifying
    documents that need embedding generation.

    Args:
        user_id: Optional user UUID to filter documents

    Returns:
        Dictionary with coverage statistics
    """
    task_id = self.request.id

    logger.info(
        "check_embedding_coverage_starting",
        task_id=task_id,
        user_id=user_id
    )

    async def check_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            from sqlalchemy import func

            # Base filter
            base_filter = Document.extracted_text.isnot(None)
            if user_id:
                base_filter = base_filter & (Document.owner_id == UUID(user_id))

            # Total documents with text
            total_query = select(func.count(Document.id)).where(base_filter)
            total_result = await session.execute(total_query)
            total = total_result.scalar() or 0

            # Documents with embeddings
            with_embedding_query = select(func.count(Document.id)).where(
                base_filter,
                Document.embedding.isnot(None)
            )
            with_embedding_result = await session.execute(with_embedding_query)
            with_embedding = with_embedding_result.scalar() or 0

            # Documents without embeddings
            without_embedding = total - with_embedding
            coverage_percent = (with_embedding / total * 100) if total > 0 else 0

            # Get documents without embeddings (for potential processing)
            missing_query = select(Document.id).where(
                base_filter,
                Document.embedding.is_(None)
            ).limit(100)
            missing_result = await session.execute(missing_query)
            missing_ids = [str(row[0]) for row in missing_result.fetchall()]

            result = {
                "total_documents": total,
                "with_embedding": with_embedding,
                "without_embedding": without_embedding,
                "coverage_percent": round(coverage_percent, 2),
                "missing_document_ids": missing_ids,
                "model": settings.EMBEDDING_MODEL,
                "dimension": settings.EMBEDDING_DIMENSION,
                "checked_at": datetime.now(timezone.utc).isoformat()
            }

            logger.info(
                "embedding_coverage_check_completed",
                task_id=task_id,
                **{k: v for k, v in result.items() if k != "missing_document_ids"}
            )

            return result

    # Run async processing with proper event loop management
    return run_async_task(check_async())


# ==================== Search Analytics Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.embedding_tasks.refresh_search_analytics"
)
def refresh_search_analytics(self) -> Dict[str, Any]:
    """Aktualisiert die materialisierte View fuer Such-Analytics.

    Diese Task sollte taeglich ausgefuehrt werden (via Celery Beat),
    idealerweise waehrend Zeiten geringer Auslastung (z.B. 2 Uhr nachts).

    Die materialisierte View aggregiert Suchstatistiken nach Tag und
    Suchtyp fuer schnellere Analytics-Abfragen.

    Returns:
        Dictionary mit Refresh-Status und Zeitstempel
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)

    logger.info(
        "refresh_search_analytics_starting",
        task_id=task_id
    )

    analytics_service = get_search_analytics_service()

    async def refresh_async() -> Dict[str, Any]:
        async with async_session_maker() as session:
            try:
                success = await analytics_service.refresh_daily_statistics(session)

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                result = {
                    "success": success,
                    "task_id": task_id,
                    "processing_time_seconds": round(processing_time, 2),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }

                if success:
                    logger.info(
                        "refresh_search_analytics_completed",
                        task_id=task_id,
                        duration_seconds=processing_time
                    )
                else:
                    logger.warning(
                        "refresh_search_analytics_failed",
                        task_id=task_id
                    )

                return result

            except Exception as e:
                logger.exception(
                    "refresh_search_analytics_error",
                    task_id=task_id,
                    error=str(e)
                )
                raise

    # Run async processing with proper event loop management
    return run_async_task(refresh_async())
