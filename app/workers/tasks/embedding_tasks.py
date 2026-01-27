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
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

import torch

from app.workers.celery_app import celery_app, GPUTask, CPUTask
from app.core.config import settings
from app.db.models import Document, ProcessingStatus
from app.db.session import get_async_session_context
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

# NOTE: Wir nutzen get_async_session_context() aus app.db.session
# Das vermeidet Event-Loop-Bugs da Engine INSIDE async context erstellt wird


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
        async with get_async_session_context() as session:
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
        async with get_async_session_context() as session:
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
        async with get_async_session_context() as session:
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
        async with get_async_session_context() as session:
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


# ==================== Qdrant Sync Tasks (A/B Testing) ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.embedding_tasks.sync_document_to_qdrant"
)
def sync_document_to_qdrant(
    self,
    document_id: str,
    embedding_model: Optional[str] = None,
    force_reindex: bool = False
) -> Dict[str, Any]:
    """Sync single document to Qdrant (Dual-Write fuer A/B Testing).

    Wird nach pgvector-Indexierung getriggert wenn Dual-Write aktiviert.
    Generiert Embedding mit konfiguriertem Modell und indexiert in Qdrant.

    Args:
        document_id: Document UUID als String
        embedding_model: Optional Embedding-Modell (default: Jina-DE)
        force_reindex: Reindexieren auch wenn schon in Qdrant

    Returns:
        Dictionary mit Sync-Ergebnis
    """
    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)
    task_id = self.request.id

    # Import hier um zirkulaere Importe zu vermeiden
    from app.services.vector.qdrant_service import get_qdrant_service
    from app.services.vector.embedding_factory import get_embedding_factory, EmbeddingModel

    logger.info(
        "qdrant_sync_starting",
        task_id=task_id,
        document_id=document_id,
        model=embedding_model
    )

    # Default zu Jina-DE fuer A/B Testing (Treatment-Variante)
    model = embedding_model or settings.VECTOR_AB_TREATMENT_EMBEDDING

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            try:
                # Dokument laden
                result = await session.execute(
                    select(Document).where(Document.id == doc_uuid)
                )
                document = result.scalar_one_or_none()

                if not document:
                    raise ValueError(f"Dokument {document_id} nicht gefunden")

                if not document.extracted_text:
                    raise ValueError(f"Dokument {document_id} hat keinen Text")

                # Pruefe ob bereits in Qdrant (wenn nicht force)
                if document.qdrant_indexed_at and not force_reindex:
                    logger.info(
                        "qdrant_sync_skipped_already_indexed",
                        document_id=document_id
                    )
                    return {
                        "success": True,
                        "document_id": document_id,
                        "skipped": True,
                        "message": "Bereits in Qdrant indexiert"
                    }

                # Qdrant Service initialisieren
                qdrant = await get_qdrant_service()
                if not await qdrant.initialize():
                    raise ValueError("Qdrant nicht verfuegbar")

                # Embedding Factory initialisieren
                embedding_factory = get_embedding_factory()

                # Embedding mit gewaehltem Modell generieren
                embedding = await embedding_factory.generate_document_embedding(
                    document.extracted_text,
                    model_name=model
                )

                if not embedding:
                    raise ValueError(f"Embedding-Generierung fehlgeschlagen fuer {document_id}")

                # Payload fuer Qdrant
                payload = {
                    "document_id": str(document.id),
                    "owner_id": str(document.owner_id) if document.owner_id else None,
                    "filename": document.filename,
                    "document_type": document.document_type,
                    "mime_type": document.mime_type,
                    "extracted_text": document.extracted_text[:2000] if document.extracted_text else None,
                    "embedding_model": model,
                    "created_at": document.created_at.isoformat() if document.created_at else None,
                }

                # In Qdrant upserten
                success = await qdrant.upsert_document(
                    document_id=doc_uuid,
                    embedding=embedding,
                    payload=payload
                )

                if not success:
                    raise ValueError(f"Qdrant upsert fehlgeschlagen fuer {document_id}")

                # Dokument-Timestamp aktualisieren
                document.qdrant_indexed_at = datetime.now(timezone.utc)
                await session.commit()

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                processing_ms = int(processing_time * 1000)

                logger.info(
                    "qdrant_sync_completed",
                    task_id=task_id,
                    document_id=document_id,
                    embedding_dimension=len(embedding),
                    model=model,
                    duration_ms=processing_ms
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "embedding_dimension": len(embedding),
                    "embedding_model": model,
                    "processing_time_ms": processing_ms,
                    "indexed_at": datetime.now(timezone.utc).isoformat()
                }

            except Exception as e:
                if _is_oom_error(e):
                    logger.warning("qdrant_sync_oom", document_id=document_id, error=str(e))
                    await _cleanup_gpu_memory()
                logger.exception("qdrant_sync_failed", document_id=document_id, error=str(e))
                raise

            finally:
                await _cleanup_gpu_memory()

    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.embedding_tasks.migrate_embeddings_to_qdrant",
    soft_time_limit=3600,  # 1 Stunde
    time_limit=3700
)
def migrate_embeddings_to_qdrant(
    self,
    batch_size: Optional[int] = None,
    max_documents: Optional[int] = None,
    embedding_model: Optional[str] = None
) -> Dict[str, Any]:
    """Batch-Migration bestehender Dokumente zu Qdrant.

    Migriert alle Dokumente mit Text zu Qdrant Vector DB.
    Fuer initiale Sync nach Qdrant-Aktivierung.

    Args:
        batch_size: Dokumente pro Batch (default: settings.VECTOR_MIGRATION_BATCH_SIZE)
        max_documents: Maximale Anzahl zu migrierender Dokumente
        embedding_model: Zu verwendendes Embedding-Modell

    Returns:
        Dictionary mit Migrations-Statistiken
    """
    start_time = datetime.now(timezone.utc)
    task_id = self.request.id
    batch_size = batch_size or settings.VECTOR_MIGRATION_BATCH_SIZE

    from app.services.vector.qdrant_service import get_qdrant_service, QdrantPoint
    from app.services.vector.embedding_factory import get_embedding_factory

    model = embedding_model or settings.VECTOR_AB_TREATMENT_EMBEDDING

    logger.info(
        "qdrant_migration_starting",
        task_id=task_id,
        batch_size=batch_size,
        max_documents=max_documents,
        model=model
    )

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            # Qdrant initialisieren
            qdrant = await get_qdrant_service()
            if not await qdrant.initialize():
                raise ValueError("Qdrant nicht verfuegbar - Migration abgebrochen")

            embedding_factory = get_embedding_factory()

            # Dokumente ohne Qdrant-Index finden
            query = select(Document).where(
                Document.extracted_text.isnot(None),
                Document.extracted_text != "",
                Document.qdrant_indexed_at.is_(None)
            ).order_by(Document.created_at.desc())

            if max_documents:
                query = query.limit(max_documents)

            result = await session.execute(query)
            documents = result.scalars().all()

            total_docs = len(documents)
            successful = 0
            failed = 0
            skipped = 0

            logger.info(
                "qdrant_migration_found_documents",
                task_id=task_id,
                count=total_docs
            )

            if not documents:
                return {
                    "success": True,
                    "total_documents": 0,
                    "message": "Keine Dokumente zum Migrieren gefunden"
                }

            # In Batches verarbeiten
            for batch_start in range(0, total_docs, batch_size):
                batch_end = min(batch_start + batch_size, total_docs)
                batch = documents[batch_start:batch_end]

                update_task_progress(
                    task_id,
                    batch_start,
                    total_docs,
                    f"Migriere Batch {batch_start // batch_size + 1}: {batch_start + 1}-{batch_end}/{total_docs}"
                )

                try:
                    # Texts sammeln
                    texts = [doc.extracted_text for doc in batch]

                    # Batch Embeddings generieren
                    embeddings = await embedding_factory.generate_batch_embeddings(
                        texts=texts,
                        model_name=model,
                        is_query=False,
                        batch_size=min(8, len(texts))
                    )

                    # Qdrant Points erstellen
                    points = []
                    for doc, emb in zip(batch, embeddings):
                        if emb is None:
                            failed += 1
                            continue

                        points.append(QdrantPoint(
                            id=str(doc.id),
                            vector=emb,
                            payload={
                                "document_id": str(doc.id),
                                "owner_id": str(doc.owner_id) if doc.owner_id else None,
                                "filename": doc.filename,
                                "document_type": doc.document_type,
                                "mime_type": doc.mime_type,
                                "extracted_text": doc.extracted_text[:2000] if doc.extracted_text else None,
                                "embedding_model": model,
                            }
                        ))

                    # Batch in Qdrant upserten
                    if points:
                        batch_success, batch_failed = await qdrant.batch_upsert_documents(
                            points=points,
                            batch_size=100
                        )
                        successful += batch_success
                        failed += batch_failed

                        # Timestamps aktualisieren
                        now = datetime.now(timezone.utc)
                        for doc in batch:
                            if any(p.id == str(doc.id) for p in points):
                                doc.qdrant_indexed_at = now

                        await session.commit()

                except Exception as e:
                    if _is_oom_error(e):
                        logger.warning(
                            "qdrant_migration_oom",
                            task_id=task_id,
                            batch_start=batch_start,
                            error=str(e)
                        )
                        await _cleanup_gpu_memory()
                        # Bei OOM: Einzeln verarbeiten
                        for doc in batch:
                            try:
                                emb = await embedding_factory.generate_document_embedding(
                                    doc.extracted_text,
                                    model_name=model
                                )
                                if emb:
                                    success = await qdrant.upsert_document(
                                        document_id=doc.id,
                                        embedding=emb,
                                        payload={
                                            "document_id": str(doc.id),
                                            "owner_id": str(doc.owner_id) if doc.owner_id else None,
                                            "filename": doc.filename,
                                            "document_type": doc.document_type,
                                            "embedding_model": model,
                                        }
                                    )
                                    if success:
                                        doc.qdrant_indexed_at = datetime.now(timezone.utc)
                                        successful += 1
                                    else:
                                        failed += 1
                                else:
                                    failed += 1
                            except Exception as e:
                                logger.debug(
                                    "embedding_document_process_failed",
                                    error_type=type(e).__name__,
                                )
                                await _cleanup_gpu_memory()
                                failed += 1
                        await session.commit()
                    else:
                        logger.error(
                            "qdrant_migration_batch_error",
                            task_id=task_id,
                            batch_start=batch_start,
                            error=str(e)
                        )
                        failed += len(batch)

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            update_task_progress(
                task_id,
                total_docs,
                total_docs,
                f"Migration abgeschlossen: {successful}/{total_docs} erfolgreich"
            )

            logger.info(
                "qdrant_migration_completed",
                task_id=task_id,
                total=total_docs,
                successful=successful,
                failed=failed,
                skipped=skipped,
                duration_seconds=processing_time
            )

            return {
                "success": True,
                "total_documents": total_docs,
                "successful": successful,
                "failed": failed,
                "skipped": skipped,
                "embedding_model": model,
                "processing_time_seconds": processing_time,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.embedding_tasks.generate_jina_embedding"
)
def generate_jina_embedding(
    self,
    document_id: str,
    sync_to_qdrant: bool = True
) -> Dict[str, Any]:
    """Generiere Jina-DE Embedding fuer ein Dokument.

    Spezifische Task fuer jina-embeddings-v2-base-de Modell.
    Optimiert fuer deutsche Dokumente mit 8k Token-Kontext.

    Args:
        document_id: Document UUID als String
        sync_to_qdrant: Embedding auch zu Qdrant syncen

    Returns:
        Dictionary mit Embedding-Ergebnis
    """
    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)
    task_id = self.request.id

    from app.services.vector.embedding_factory import get_embedding_factory, EmbeddingModel

    logger.info(
        "jina_embedding_starting",
        task_id=task_id,
        document_id=document_id,
        sync_to_qdrant=sync_to_qdrant
    )

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            try:
                # Dokument laden
                result = await session.execute(
                    select(Document).where(Document.id == doc_uuid)
                )
                document = result.scalar_one_or_none()

                if not document:
                    raise ValueError(f"Dokument {document_id} nicht gefunden")

                if not document.extracted_text:
                    raise ValueError(f"Dokument {document_id} hat keinen Text")

                # Jina-DE Embedding generieren
                embedding_factory = get_embedding_factory()
                embedding = await embedding_factory.generate_document_embedding(
                    document.extracted_text,
                    model_name=EmbeddingModel.JINA_DE
                )

                if not embedding:
                    raise ValueError(f"Jina Embedding-Generierung fehlgeschlagen")

                result_data = {
                    "success": True,
                    "document_id": document_id,
                    "embedding_dimension": len(embedding),
                    "embedding_model": EmbeddingModel.JINA_DE,
                    "text_length": len(document.extracted_text),
                }

                # Optional zu Qdrant syncen
                if sync_to_qdrant and settings.QDRANT_ENABLED:
                    from app.services.vector.qdrant_service import get_qdrant_service

                    qdrant = await get_qdrant_service()
                    if await qdrant.initialize():
                        success = await qdrant.upsert_document(
                            document_id=doc_uuid,
                            embedding=embedding,
                            payload={
                                "document_id": str(document.id),
                                "owner_id": str(document.owner_id) if document.owner_id else None,
                                "filename": document.filename,
                                "document_type": document.document_type,
                                "embedding_model": EmbeddingModel.JINA_DE,
                            }
                        )
                        if success:
                            document.qdrant_indexed_at = datetime.now(timezone.utc)
                            await session.commit()
                            result_data["qdrant_synced"] = True
                        else:
                            result_data["qdrant_synced"] = False
                            result_data["qdrant_error"] = "Upsert fehlgeschlagen"

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                result_data["processing_time_ms"] = int(processing_time * 1000)

                logger.info(
                    "jina_embedding_completed",
                    task_id=task_id,
                    document_id=document_id,
                    duration_ms=result_data["processing_time_ms"]
                )

                return result_data

            except Exception as e:
                if _is_oom_error(e):
                    logger.warning("jina_embedding_oom", document_id=document_id, error=str(e))
                    await _cleanup_gpu_memory()
                logger.exception("jina_embedding_failed", document_id=document_id, error=str(e))
                raise

            finally:
                await _cleanup_gpu_memory()

    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.embedding_tasks.analyze_ab_test_metrics"
)
def analyze_ab_test_metrics(
    self,
    experiment_id: Optional[str] = None,
    days: int = 7
) -> Dict[str, Any]:
    """Analysiere A/B Test Metriken fuer Vector Search.

    Berechnet statistische Signifikanz und Latenz-Vergleiche
    zwischen pgvector (Control) und Qdrant (Treatment).

    Args:
        experiment_id: Optional spezifisches Experiment
        days: Anzahl Tage zurueck fuer Analyse

    Returns:
        Dictionary mit A/B Test Analyse-Ergebnissen
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)

    from app.services.vector.vector_orchestrator import get_vector_orchestrator

    logger.info(
        "ab_test_analysis_starting",
        task_id=task_id,
        experiment_id=experiment_id,
        days=days
    )

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            try:
                # Orchestrator-Metriken holen
                orchestrator = await get_vector_orchestrator()
                metrics_summary = orchestrator.get_metrics_summary()

                # Vergleich berechnen
                pgvector_metrics = metrics_summary.get("pgvector", {})
                qdrant_metrics = metrics_summary.get("qdrant", {})

                comparison = {
                    "pgvector": pgvector_metrics,
                    "qdrant": qdrant_metrics,
                }

                # Latenz-Differenz berechnen falls beide Daten haben
                if pgvector_metrics.get("sample_count", 0) > 0 and qdrant_metrics.get("sample_count", 0) > 0:
                    pg_avg = pgvector_metrics.get("avg_latency_ms", 0)
                    qd_avg = qdrant_metrics.get("avg_latency_ms", 0)

                    if pg_avg > 0:
                        latency_improvement = ((pg_avg - qd_avg) / pg_avg) * 100
                        comparison["latency_improvement_percent"] = round(latency_improvement, 2)
                        comparison["recommendation"] = (
                            "qdrant" if latency_improvement > 10
                            else "pgvector" if latency_improvement < -10
                            else "inconclusive"
                        )

                # Health Check
                health = await orchestrator.health_check()
                comparison["health"] = health

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                logger.info(
                    "ab_test_analysis_completed",
                    task_id=task_id,
                    pgvector_samples=pgvector_metrics.get("sample_count", 0),
                    qdrant_samples=qdrant_metrics.get("sample_count", 0),
                    duration_seconds=processing_time
                )

                return {
                    "success": True,
                    "comparison": comparison,
                    "analysis_period_days": days,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "processing_time_seconds": processing_time
                }

            except Exception as e:
                logger.exception("ab_test_analysis_failed", task_id=task_id, error=str(e))
                raise

    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.embedding_tasks.sync_pending_to_qdrant"
)
def sync_pending_to_qdrant(
    self,
    limit: int = 100
) -> Dict[str, Any]:
    """Sync ausstehende Dokumente zu Qdrant (Periodic Task).

    Findet Dokumente die in PostgreSQL aber nicht in Qdrant indexiert sind
    und synchronisiert diese. Fuer Celery Beat Scheduling.

    Args:
        limit: Maximale Anzahl pro Durchlauf

    Returns:
        Dictionary mit Sync-Statistiken
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)

    logger.info(
        "sync_pending_to_qdrant_starting",
        task_id=task_id,
        limit=limit
    )

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            # Dokumente finden die Embedding haben aber nicht in Qdrant
            query = select(Document.id).where(
                Document.embedding.isnot(None),
                Document.qdrant_indexed_at.is_(None)
            ).limit(limit)

            result = await session.execute(query)
            pending_ids = [str(row[0]) for row in result.fetchall()]

            if not pending_ids:
                return {
                    "success": True,
                    "synced": 0,
                    "message": "Keine ausstehenden Dokumente"
                }

            # Jobs fuer Sync erstellen
            from celery import group

            sync_tasks = group([
                sync_document_to_qdrant.s(doc_id)
                for doc_id in pending_ids
            ])

            # Async ausfuehren
            result = sync_tasks.apply_async()

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            logger.info(
                "sync_pending_to_qdrant_scheduled",
                task_id=task_id,
                pending_count=len(pending_ids),
                duration_seconds=processing_time
            )

            return {
                "success": True,
                "scheduled": len(pending_ids),
                "group_id": str(result.id) if result else None,
                "processing_time_seconds": processing_time
            }

    return run_async_task(process_async())


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
        async with get_async_session_context() as session:
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
