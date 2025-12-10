"""RAG Intelligence Layer Tasks fuer Celery.

Dieses Modul enthaelt Tasks fuer:
- Document Chunking
- Customer Card Synchronisation
- RAG Batch Jobs
- Analytics Refresh
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TypeVar, Coroutine
from uuid import UUID

import structlog
from celery import states
from celery.exceptions import SoftTimeLimitExceeded, Ignore
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.workers.celery_app import celery_app, GPUTask, CPUTask
from app.core.config import settings
from app.db.session import get_async_session_context
from app.db.models import (
    Document,
    RAGDocumentChunk,
    RAGBatchJob,
    RAGJobType,
    RAGJobStatus,
    ProcessingStatus,
)

logger = structlog.get_logger(__name__)

# Type variable for async return type
T = TypeVar('T')


def run_async_task(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async coroutine in a Celery task context."""
    return asyncio.run(coro)


# NOTE: Wir nutzen get_async_session_context() aus app.db.session
# Das vermeidet Event-Loop-Bugs da Engine INSIDE async context erstellt wird


def update_task_progress(task_id: str, current: int, total: int, message: str) -> None:
    """Update task progress for real-time monitoring."""
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


# ==================== Document Chunking Tasks ====================

@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.rag_tasks.chunk_document"
)
def chunk_document(
    self,
    document_id: str,
    strategy: str = "semantic",
    generate_embeddings: bool = True
) -> Dict[str, Any]:
    """Chunked ein einzelnes Dokument.

    Args:
        document_id: Dokument-UUID als String
        strategy: Chunking-Strategie (semantic, fixed, document_type)
        generate_embeddings: Embeddings fuer Chunks generieren

    Returns:
        Dictionary mit Chunking-Ergebnis
    """
    start_time = datetime.now(timezone.utc)
    doc_uuid = UUID(document_id)
    task_id = self.request.id

    logger.info(
        "chunk_document_task_starting",
        task_id=task_id,
        document_id=document_id,
        strategy=strategy
    )

    async def process_async() -> Dict[str, Any]:
        from app.services.rag.chunking_service import get_chunking_service

        chunking_service = get_chunking_service()

        async with get_async_session_context() as session:
            try:
                update_task_progress(task_id, 0, 100, "Starte Chunking...")

                # Document laden
                result = await session.execute(
                    select(Document).where(Document.id == doc_uuid)
                )
                document = result.scalar_one_or_none()

                if not document:
                    raise ValueError(f"Dokument {document_id} nicht gefunden")

                if not document.extracted_text:
                    raise ValueError(f"Dokument {document_id} hat keinen OCR-Text")

                update_task_progress(task_id, 20, 100, "Chunke Dokument...")

                # Chunking durchfuehren
                chunks = await chunking_service.chunk_document(
                    db=session,
                    document_id=doc_uuid,
                    strategy=strategy,
                    generate_embeddings=generate_embeddings
                )

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                processing_ms = int(processing_time * 1000)

                update_task_progress(task_id, 100, 100, "Chunking abgeschlossen!")

                logger.info(
                    "chunk_document_task_completed",
                    task_id=task_id,
                    document_id=document_id,
                    chunks_created=len(chunks),
                    duration_ms=processing_ms
                )

                return {
                    "success": True,
                    "document_id": document_id,
                    "chunks_created": len(chunks),
                    "total_tokens": sum(c.chunk_tokens for c in chunks),
                    "strategy": strategy,
                    "embeddings_generated": generate_embeddings,
                    "processing_time_ms": processing_ms,
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }

            except SoftTimeLimitExceeded:
                logger.error(
                    "chunk_document_task_timeout",
                    task_id=task_id,
                    document_id=document_id
                )
                raise Ignore()

            except Exception as e:
                logger.exception(
                    "chunk_document_task_failed",
                    task_id=task_id,
                    document_id=document_id,
                    error=str(e)
                )
                raise

    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.rag_tasks.batch_chunk_documents"
)
def batch_chunk_documents(
    self,
    document_ids: Optional[List[str]] = None,
    strategy: str = "semantic",
    force: bool = False,
    batch_size: int = 10
) -> Dict[str, Any]:
    """Chunked mehrere Dokumente in Batch.

    Args:
        document_ids: Liste von Dokument-IDs (None = alle ohne Chunks)
        strategy: Chunking-Strategie
        force: Existierende Chunks ueberschreiben
        batch_size: Batch-Groesse

    Returns:
        Dictionary mit Batch-Ergebnis
    """
    start_time = datetime.now(timezone.utc)
    task_id = self.request.id

    logger.info(
        "batch_chunk_documents_starting",
        task_id=task_id,
        document_count=len(document_ids) if document_ids else "all",
        strategy=strategy,
        force=force
    )

    async def process_async() -> Dict[str, Any]:
        from app.services.rag.chunking_service import get_chunking_service

        chunking_service = get_chunking_service()

        async with get_async_session_context() as session:
            # Dokumente ermitteln
            if document_ids:
                doc_uuids = [UUID(d) for d in document_ids]
                query = select(Document).where(
                    Document.id.in_(doc_uuids),
                    Document.extracted_text.isnot(None)
                )
            else:
                # Alle Dokumente mit OCR-Text
                query = select(Document).where(Document.extracted_text.isnot(None))

                if not force:
                    # Nur Dokumente ohne Chunks
                    subquery = select(RAGDocumentChunk.document_id).distinct()
                    query = query.where(~Document.id.in_(subquery))

            result = await session.execute(query)
            documents = result.scalars().all()
            total_docs = len(documents)

            logger.info(
                "batch_chunk_found_documents",
                task_id=task_id,
                count=total_docs
            )

            if not documents:
                return {
                    "success": True,
                    "total_documents": 0,
                    "message": "Keine Dokumente zum Chunken gefunden"
                }

            successful = 0
            failed = 0
            total_chunks = 0
            results = []

            for i, doc in enumerate(documents):
                update_task_progress(
                    task_id,
                    i,
                    total_docs,
                    f"Chunke Dokument {i + 1}/{total_docs}..."
                )

                try:
                    if force:
                        # Existierende Chunks loeschen
                        await chunking_service.delete_document_chunks(session, doc.id)

                    chunks = await chunking_service.chunk_document(
                        db=session,
                        document_id=doc.id,
                        strategy=strategy,
                        generate_embeddings=True
                    )

                    successful += 1
                    total_chunks += len(chunks)
                    results.append({
                        "document_id": str(doc.id),
                        "success": True,
                        "chunks": len(chunks)
                    })

                except Exception as e:
                    failed += 1
                    results.append({
                        "document_id": str(doc.id),
                        "success": False,
                        "error": str(e)
                    })
                    logger.error(
                        "batch_chunk_document_failed",
                        document_id=str(doc.id),
                        error=str(e)
                    )

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            update_task_progress(
                task_id,
                total_docs,
                total_docs,
                f"Abgeschlossen: {successful} erfolgreich, {failed} fehlgeschlagen"
            )

            logger.info(
                "batch_chunk_documents_completed",
                task_id=task_id,
                total=total_docs,
                successful=successful,
                failed=failed,
                total_chunks=total_chunks,
                duration_seconds=processing_time
            )

            return {
                "success": True,
                "total_documents": total_docs,
                "successful": successful,
                "failed": failed,
                "total_chunks_created": total_chunks,
                "strategy": strategy,
                "results": results,
                "processing_time_seconds": processing_time,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.rag_tasks.regenerate_chunk_embeddings"
)
def regenerate_chunk_embeddings(
    self,
    document_id: Optional[str] = None
) -> Dict[str, Any]:
    """Regeneriert Embeddings fuer existierende Chunks.

    Args:
        document_id: Optional - nur fuer dieses Dokument

    Returns:
        Dictionary mit Ergebnis
    """
    start_time = datetime.now(timezone.utc)
    task_id = self.request.id

    logger.info(
        "regenerate_chunk_embeddings_starting",
        task_id=task_id,
        document_id=document_id
    )

    async def process_async() -> Dict[str, Any]:
        from app.services.embedding_service import get_embedding_service

        embedding_service = get_embedding_service()

        async with get_async_session_context() as session:
            # Chunks laden
            query = select(RAGDocumentChunk)
            if document_id:
                query = query.where(RAGDocumentChunk.document_id == UUID(document_id))

            result = await session.execute(query)
            chunks = result.scalars().all()
            total_chunks = len(chunks)

            if not chunks:
                return {
                    "success": True,
                    "total_chunks": 0,
                    "message": "Keine Chunks gefunden"
                }

            # Batch-Embeddings generieren
            texts = [c.chunk_text for c in chunks]
            batch_size = settings.EMBEDDING_BATCH_SIZE

            all_embeddings = []
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                update_task_progress(
                    task_id,
                    i,
                    total_chunks,
                    f"Generiere Embeddings {i + 1}-{min(i + batch_size, total_chunks)}/{total_chunks}..."
                )

                embeddings = await embedding_service.generate_batch_embeddings_async(
                    batch,
                    is_query=False
                )
                all_embeddings.extend(embeddings)

            # Chunks aktualisieren
            now = datetime.now(timezone.utc)
            model_name = embedding_service.model_name

            for chunk, embedding in zip(chunks, all_embeddings):
                chunk.embedding = embedding
                chunk.embedding_model = model_name
                chunk.embedding_created_at = now

            await session.commit()

            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            update_task_progress(
                task_id,
                total_chunks,
                total_chunks,
                "Embeddings regeneriert!"
            )

            logger.info(
                "regenerate_chunk_embeddings_completed",
                task_id=task_id,
                total_chunks=total_chunks,
                duration_seconds=processing_time
            )

            return {
                "success": True,
                "total_chunks": total_chunks,
                "embedding_model": model_name,
                "processing_time_seconds": processing_time,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }

    return run_async_task(process_async())


# ==================== RAG Batch Job Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.rag_tasks.run_rag_batch_job"
)
def run_rag_batch_job(
    self,
    job_id: str
) -> Dict[str, Any]:
    """Fuehrt einen RAG Batch Job aus.

    Args:
        job_id: Batch Job UUID

    Returns:
        Dictionary mit Job-Ergebnis
    """
    start_time = datetime.now(timezone.utc)
    task_id = self.request.id
    job_uuid = UUID(job_id)

    logger.info(
        "rag_batch_job_starting",
        task_id=task_id,
        job_id=job_id
    )

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            # Job laden
            result = await session.execute(
                select(RAGBatchJob).where(RAGBatchJob.id == job_uuid)
            )
            job = result.scalar_one_or_none()

            if not job:
                raise ValueError(f"Batch Job {job_id} nicht gefunden")

            # Job als laufend markieren
            job.status = RAGJobStatus.RUNNING
            job.started_at = start_time
            job.celery_task_id = task_id
            await session.commit()

            try:
                # Job-Typ spezifische Verarbeitung
                if job.job_type == RAGJobType.CHUNK_DOCUMENTS:
                    result_data = await _run_chunk_documents_job(session, job, task_id)
                elif job.job_type == RAGJobType.REEMBEDDING:
                    result_data = await _run_reembedding_job(session, job, task_id)
                elif job.job_type == RAGJobType.CUSTOMER_CARD_SYNC:
                    result_data = await _run_customer_card_sync_job(session, job, task_id)
                elif job.job_type == RAGJobType.REPORT_GENERATION:
                    result_data = await _run_report_generation_job(session, job, task_id)
                else:
                    raise ValueError(f"Unbekannter Job-Typ: {job.job_type}")

                # Job als erfolgreich markieren
                job.status = RAGJobStatus.COMPLETED
                job.progress_percent = 100
                job.result = result_data
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()

                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

                logger.info(
                    "rag_batch_job_completed",
                    task_id=task_id,
                    job_id=job_id,
                    job_type=job.job_type.value,
                    duration_seconds=processing_time
                )

                return {
                    "success": True,
                    "job_id": job_id,
                    "job_type": job.job_type.value,
                    "result": result_data,
                    "processing_time_seconds": processing_time,
                    "completed_at": job.completed_at.isoformat()
                }

            except Exception as e:
                # Job als fehlgeschlagen markieren
                job.status = RAGJobStatus.FAILED
                job.error_message = str(e)
                job.retry_count += 1
                job.completed_at = datetime.now(timezone.utc)
                await session.commit()

                logger.exception(
                    "rag_batch_job_failed",
                    task_id=task_id,
                    job_id=job_id,
                    error=str(e)
                )
                raise

    return run_async_task(process_async())


async def _run_chunk_documents_job(
    session: AsyncSession,
    job: RAGBatchJob,
    task_id: str
) -> Dict[str, Any]:
    """Verarbeitet einen Chunk Documents Job."""
    from app.services.rag.chunking_service import get_chunking_service

    chunking_service = get_chunking_service()
    params = job.parameters or {}
    document_ids = params.get("document_ids")
    strategy = params.get("strategy", "semantic")
    force = params.get("force", False)

    # Dokumente ermitteln
    if document_ids:
        doc_uuids = [UUID(d) for d in document_ids]
        query = select(Document).where(
            Document.id.in_(doc_uuids),
            Document.extracted_text.isnot(None)
        )
    else:
        query = select(Document).where(Document.extracted_text.isnot(None))

    result = await session.execute(query)
    documents = result.scalars().all()
    total = len(documents)

    job.items_total = total
    await session.commit()

    successful = 0
    failed = 0
    total_chunks = 0

    for i, doc in enumerate(documents):
        try:
            if force:
                await chunking_service.delete_document_chunks(session, doc.id)

            chunks = await chunking_service.chunk_document(
                db=session,
                document_id=doc.id,
                strategy=strategy,
                generate_embeddings=True
            )

            successful += 1
            total_chunks += len(chunks)
            job.items_processed = successful + failed
            job.progress_percent = int((job.items_processed / total) * 100)
            job.progress_message = f"Verarbeitet: {job.items_processed}/{total}"
            await session.commit()

        except Exception as e:
            failed += 1
            job.items_failed = failed
            logger.error("chunk_job_document_failed", document_id=str(doc.id), error=str(e))

    return {
        "total_documents": total,
        "successful": successful,
        "failed": failed,
        "total_chunks": total_chunks,
        "strategy": strategy
    }


async def _run_reembedding_job(
    session: AsyncSession,
    job: RAGBatchJob,
    task_id: str
) -> Dict[str, Any]:
    """Verarbeitet einen Reembedding Job."""
    from app.services.embedding_service import get_embedding_service

    embedding_service = get_embedding_service()
    params = job.parameters or {}
    document_ids = params.get("document_ids")

    # Chunks laden
    query = select(RAGDocumentChunk)
    if document_ids:
        doc_uuids = [UUID(d) for d in document_ids]
        query = query.where(RAGDocumentChunk.document_id.in_(doc_uuids))

    result = await session.execute(query)
    chunks = result.scalars().all()
    total = len(chunks)

    job.items_total = total
    await session.commit()

    if not chunks:
        return {"total_chunks": 0, "message": "Keine Chunks gefunden"}

    # Batch-Embeddings generieren
    texts = [c.chunk_text for c in chunks]
    embeddings = await embedding_service.generate_batch_embeddings_async(texts, is_query=False)

    # Chunks aktualisieren
    now = datetime.now(timezone.utc)
    model_name = embedding_service.model_name

    for chunk, embedding in zip(chunks, embeddings):
        chunk.embedding = embedding
        chunk.embedding_model = model_name
        chunk.embedding_created_at = now

    job.items_processed = total
    job.progress_percent = 100
    await session.commit()

    return {
        "total_chunks": total,
        "embedding_model": model_name
    }


async def _run_customer_card_sync_job(
    session: AsyncSession,
    job: RAGBatchJob,
    task_id: str
) -> Dict[str, Any]:
    """Verarbeitet einen Customer Card Sync Job.

    Hinweis: Diese Funktion wird in Phase 5 (Customer Cards) vollstaendig implementiert.
    """
    logger.info("customer_card_sync_job_placeholder", job_id=str(job.id))

    return {
        "message": "Customer Card Sync wird in Phase 5 implementiert",
        "status": "placeholder"
    }


async def _run_report_generation_job(
    session: AsyncSession,
    job: RAGBatchJob,
    task_id: str
) -> Dict[str, Any]:
    """Verarbeitet einen Report Generation Job.

    Hinweis: Diese Funktion wird in Phase 7 (Report Generation) vollstaendig implementiert.
    """
    logger.info("report_generation_job_placeholder", job_id=str(job.id))

    return {
        "message": "Report Generation wird in Phase 7 implementiert",
        "status": "placeholder"
    }


# ==================== Statistics & Analytics Tasks ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.rag_tasks.get_rag_statistics"
)
def get_rag_statistics(self) -> Dict[str, Any]:
    """Sammelt RAG-System-Statistiken.

    Returns:
        Dictionary mit Statistiken
    """
    task_id = self.request.id

    logger.info("get_rag_statistics_starting", task_id=task_id)

    async def collect_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            # Chunk-Statistiken
            chunk_count = await session.execute(
                select(func.count(RAGDocumentChunk.id))
            )
            total_chunks = chunk_count.scalar() or 0

            chunk_tokens = await session.execute(
                select(func.sum(RAGDocumentChunk.chunk_tokens))
            )
            total_tokens = chunk_tokens.scalar() or 0

            chunks_with_embedding = await session.execute(
                select(func.count(RAGDocumentChunk.id)).where(
                    RAGDocumentChunk.embedding.isnot(None)
                )
            )
            embedded_chunks = chunks_with_embedding.scalar() or 0

            # Dokumente mit Chunks
            docs_with_chunks = await session.execute(
                select(func.count(func.distinct(RAGDocumentChunk.document_id)))
            )
            chunked_documents = docs_with_chunks.scalar() or 0

            # Gesamte Dokumente
            total_docs = await session.execute(
                select(func.count(Document.id)).where(
                    Document.extracted_text.isnot(None)
                )
            )
            total_documents = total_docs.scalar() or 0

            # Batch Jobs
            pending_jobs = await session.execute(
                select(func.count(RAGBatchJob.id)).where(
                    RAGBatchJob.status == RAGJobStatus.PENDING
                )
            )
            pending_job_count = pending_jobs.scalar() or 0

            running_jobs = await session.execute(
                select(func.count(RAGBatchJob.id)).where(
                    RAGBatchJob.status == RAGJobStatus.RUNNING
                )
            )
            running_job_count = running_jobs.scalar() or 0

            return {
                "chunks": {
                    "total": total_chunks,
                    "with_embedding": embedded_chunks,
                    "without_embedding": total_chunks - embedded_chunks,
                    "embedding_coverage_percent": round(
                        (embedded_chunks / total_chunks * 100) if total_chunks > 0 else 0, 2
                    ),
                    "total_tokens": total_tokens,
                    "avg_tokens_per_chunk": round(
                        total_tokens / total_chunks if total_chunks > 0 else 0, 1
                    )
                },
                "documents": {
                    "total_with_text": total_documents,
                    "chunked": chunked_documents,
                    "not_chunked": total_documents - chunked_documents,
                    "chunk_coverage_percent": round(
                        (chunked_documents / total_documents * 100) if total_documents > 0 else 0, 2
                    )
                },
                "batch_jobs": {
                    "pending": pending_job_count,
                    "running": running_job_count
                },
                "collected_at": datetime.now(timezone.utc).isoformat()
            }

    return run_async_task(collect_async())


# ==================== Scheduled Tasks (Celery Beat) ====================

@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.rag_tasks.scheduled_chunk_new_documents"
)
def scheduled_chunk_new_documents(self) -> Dict[str, Any]:
    """Scheduled Task: Chunked neue Dokumente ohne Chunks.

    Wird regelmaessig via Celery Beat ausgefuehrt.
    """
    task_id = self.request.id

    logger.info("scheduled_chunk_new_documents_starting", task_id=task_id)

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            # Dokumente ohne Chunks finden
            subquery = select(RAGDocumentChunk.document_id).distinct()
            query = select(Document.id).where(
                Document.extracted_text.isnot(None),
                Document.processing_status == ProcessingStatus.COMPLETED,
                ~Document.id.in_(subquery)
            ).limit(50)  # Batch-Limit

            result = await session.execute(query)
            document_ids = [str(row[0]) for row in result.fetchall()]

            if not document_ids:
                logger.info("scheduled_chunk_no_documents", task_id=task_id)
                return {
                    "success": True,
                    "documents_found": 0,
                    "message": "Keine neuen Dokumente zum Chunken"
                }

            logger.info(
                "scheduled_chunk_found_documents",
                task_id=task_id,
                count=len(document_ids)
            )

        # Batch-Task starten
        batch_result = batch_chunk_documents.delay(
            document_ids=document_ids,
            strategy="semantic",
            force=False
        )

        return {
            "success": True,
            "documents_found": len(document_ids),
            "batch_task_id": batch_result.id,
            "scheduled_at": datetime.now(timezone.utc).isoformat()
        }

    return run_async_task(process_async())


@celery_app.task(
    bind=True,
    base=CPUTask,
    name="app.workers.tasks.rag_tasks.sync_customer_cards_scheduled"
)
def sync_customer_cards_scheduled(self) -> Dict[str, Any]:
    """Scheduled Task: Synchronisiert alle Customer Cards.

    Wird taeglich um 03:30 via Celery Beat ausgefuehrt.
    Erstellt einen RAG Batch Job fuer den Customer Card Sync.
    """
    task_id = self.request.id

    logger.info("sync_customer_cards_scheduled_starting", task_id=task_id)

    async def process_async() -> Dict[str, Any]:
        async with get_async_session_context() as session:
            # Batch Job erstellen
            job = RAGBatchJob(
                job_type=RAGJobType.CUSTOMER_CARD_SYNC,
                job_name="Scheduled Customer Card Sync",
                status=RAGJobStatus.PENDING,
                progress_percent=0,
                parameters={"source": "scheduled", "task_id": task_id}
            )
            session.add(job)
            await session.commit()
            await session.refresh(job)

            job_id = str(job.id)

            logger.info(
                "sync_customer_cards_job_created",
                task_id=task_id,
                job_id=job_id
            )

        # Batch Job Task starten
        run_rag_batch_job.delay(job_id)

        return {
            "success": True,
            "job_id": job_id,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "message": "Customer Card Sync Job gestartet"
        }

    return run_async_task(process_async())
