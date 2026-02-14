"""RAG Chunks API Endpoints.

Document Chunking Management:
- Dokumente chunken
- Chunks abrufen
- Chunks loeschen
- Bulk-Chunking
"""

import structlog
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_current_user, get_db, require_admin
from app.api.schemas.rag import (
    RAGChunkResponse,
    RAGChunkDocumentRequest,
    RAGChunkDocumentResponse,
    RAGBulkChunkRequest,
)
from app.services.rag.chunking_service import get_chunking_service, DocumentChunkingService
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chunks", tags=["rag-chunks"])


def get_chunking_service_dep() -> DocumentChunkingService:
    """Dependency fuer DocumentChunkingService."""
    return get_chunking_service()


@router.post(
    "/document/{document_id}",
    response_model=RAGChunkDocumentResponse,
    summary="Dokument chunken",
    description="Erstellt Chunks fuer ein Dokument und generiert Embeddings."
)
async def chunk_document(
    document_id: UUID,
    request: Optional[RAGChunkDocumentRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    chunking_service: DocumentChunkingService = Depends(get_chunking_service_dep)
) -> RAGChunkDocumentResponse:
    """
    Chunked ein einzelnes Dokument.

    - Laedt den OCR-Text des Dokuments
    - Teilt in semantische Chunks
    - Generiert Embeddings fuer jeden Chunk
    - Speichert in rag_document_chunks

    **Strategien:**
    - `semantic`: Respektiert Absatz- und Satzgrenzen (Standard)
    - `fixed`: Feste Chunk-Groesse
    - `document_type`: Dokumenttyp-spezifische Strategie
    """
    strategy = request.strategy if request else "semantic"
    generate_embeddings = request.generate_embeddings if request else True

    logger.info(
        "chunk_document_request",
        user_id=str(current_user.id),
        document_id=str(document_id),
        strategy=strategy
    )

    try:
        from datetime import datetime, timezone
        start_time = datetime.now(timezone.utc)

        chunks = await chunking_service.chunk_document(
            db=db,
            document_id=document_id,
            strategy=strategy,
            generate_embeddings=generate_embeddings
        )

        processing_time = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        total_tokens = sum(c.chunk_tokens for c in chunks)

        return RAGChunkDocumentResponse(
            document_id=document_id,
            chunks_created=len(chunks),
            total_tokens=total_tokens,
            strategy_used=strategy,
            processing_time_ms=processing_time
        )

    except ValueError as e:
        # SECURITY FIX 28-25: Generische Fehlermeldung
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden."
        )
    except Exception as e:
        # SECURITY FIX 28-25: Generische Fehlermeldung
        logger.exception(
            "chunk_document_failed",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chunking fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


@router.get(
    "/document/{document_id}",
    response_model=List[RAGChunkResponse],
    summary="Chunks eines Dokuments abrufen",
    description="Gibt alle Chunks eines Dokuments zurueck."
)
async def get_document_chunks(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    chunking_service: DocumentChunkingService = Depends(get_chunking_service_dep)
) -> List[RAGChunkResponse]:
    """
    Ruft alle Chunks eines Dokuments ab.

    Sortiert nach chunk_index.
    """
    try:
        chunks = await chunking_service.get_document_chunks(db, document_id)

        return [
            RAGChunkResponse(
                id=c.id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                chunk_text=c.chunk_text,
                chunk_tokens=c.chunk_tokens,
                page_number=c.page_number,
                section_type=c.section_type,
                embedding_model=c.embedding_model or "",
                embedding_created_at=c.embedding_created_at or c.created_at,
                created_at=c.created_at
            )
            for c in chunks
        ]

    except Exception as e:
        # SECURITY FIX 28-25: Generische Fehlermeldung
        logger.exception(
            "get_document_chunks_failed",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Abrufen fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


@router.delete(
    "/document/{document_id}",
    summary="Chunks eines Dokuments loeschen",
    description="Loescht alle Chunks eines Dokuments."
)
async def delete_document_chunks(
    document_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    chunking_service: DocumentChunkingService = Depends(get_chunking_service_dep)
) -> dict:
    """
    Loescht alle Chunks eines Dokuments.

    Nuetzlich vor dem erneuten Chunken oder beim Loeschen eines Dokuments.
    """
    logger.info(
        "delete_document_chunks_request",
        user_id=str(current_user.id),
        document_id=str(document_id)
    )

    try:
        deleted_count = await chunking_service.delete_document_chunks(db, document_id)

        return {
            "success": True,
            "document_id": str(document_id),
            "deleted_chunks": deleted_count
        }

    except Exception as e:
        # SECURITY FIX 28-25: Generische Fehlermeldung
        logger.exception(
            "delete_document_chunks_failed",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Loeschen fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


@router.post(
    "/document/{document_id}/rechunk",
    response_model=RAGChunkDocumentResponse,
    summary="Dokument neu chunken",
    description="Loescht existierende Chunks und erstellt neue."
)
async def rechunk_document(
    document_id: UUID,
    strategy: str = Query("semantic", description="Chunking-Strategie"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    chunking_service: DocumentChunkingService = Depends(get_chunking_service_dep)
) -> RAGChunkDocumentResponse:
    """
    Chunked ein Dokument neu.

    - Loescht alle existierenden Chunks
    - Erstellt neue Chunks mit der angegebenen Strategie
    - Generiert neue Embeddings
    """
    logger.info(
        "rechunk_document_request",
        user_id=str(current_user.id),
        document_id=str(document_id),
        strategy=strategy
    )

    try:
        from datetime import datetime, timezone
        start_time = datetime.now(timezone.utc)

        chunks = await chunking_service.rechunk_document(
            db=db,
            document_id=document_id,
            strategy=strategy
        )

        processing_time = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        total_tokens = sum(c.chunk_tokens for c in chunks)

        return RAGChunkDocumentResponse(
            document_id=document_id,
            chunks_created=len(chunks),
            total_tokens=total_tokens,
            strategy_used=strategy,
            processing_time_ms=processing_time
        )

    except ValueError as e:
        # SECURITY FIX 28-25: Generische Fehlermeldung
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden."
        )
    except Exception as e:
        # SECURITY FIX 28-25: Generische Fehlermeldung
        logger.exception(
            "rechunk_document_failed",
            document_id=str(document_id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Rechunking fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


@router.post(
    "/bulk",
    summary="Bulk-Chunking starten",
    description="Startet einen Batch-Job fuer Bulk-Chunking.",
    dependencies=[Depends(require_admin)]
)
async def bulk_chunk_documents(
    request: RAGBulkChunkRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Startet Bulk-Chunking als Hintergrund-Task.

    - **document_ids**: Spezifische Dokumente (oder alle ohne Chunks)
    - **force**: Existierende Chunks ueberschreiben
    - **strategy**: Chunking-Strategie

    Gibt eine Task-ID zurueck fuer Status-Abfragen.
    """
    from app.workers.tasks.rag_tasks import batch_chunk_documents

    logger.info(
        "bulk_chunk_request",
        user_id=str(current_user.id),
        document_count=len(request.document_ids) if request.document_ids else "all",
        force=request.force,
        strategy=request.strategy
    )

    # Celery Task starten
    document_ids = [str(d) for d in request.document_ids] if request.document_ids else None

    task = batch_chunk_documents.delay(
        document_ids=document_ids,
        strategy=request.strategy,
        force=request.force
    )

    return {
        "success": True,
        "task_id": task.id,
        "message": "Bulk-Chunking gestartet",
        "strategy": request.strategy,
        "force": request.force
    }


@router.get(
    "/stats",
    summary="Chunk-Statistiken abrufen",
    description="Gibt Statistiken ueber alle Chunks zurueck."
)
async def get_chunk_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Statistiken ueber Document Chunks.

    - Gesamtanzahl Chunks
    - Chunks mit/ohne Embeddings
    - Durchschnittliche Tokens pro Chunk
    - Anzahl gechunkte Dokumente
    """
    from sqlalchemy import select, func
    from app.db.models import RAGDocumentChunk, Document


    try:
        # Gesamtanzahl Chunks
        total_chunks = await db.scalar(
            select(func.count(RAGDocumentChunk.id))
        ) or 0

        # Chunks mit Embeddings
        chunks_with_embedding = await db.scalar(
            select(func.count(RAGDocumentChunk.id)).where(
                RAGDocumentChunk.embedding.isnot(None)
            )
        ) or 0

        # Gesamt-Tokens
        total_tokens = await db.scalar(
            select(func.sum(RAGDocumentChunk.chunk_tokens))
        ) or 0

        # Gechunkte Dokumente
        chunked_docs = await db.scalar(
            select(func.count(func.distinct(RAGDocumentChunk.document_id)))
        ) or 0

        # Dokumente mit OCR-Text
        docs_with_text = await db.scalar(
            select(func.count(Document.id)).where(
                Document.extracted_text.isnot(None)
            )
        ) or 0

        return {
            "total_chunks": total_chunks,
            "chunks_with_embedding": chunks_with_embedding,
            "chunks_without_embedding": total_chunks - chunks_with_embedding,
            "embedding_coverage_percent": round(
                (chunks_with_embedding / total_chunks * 100) if total_chunks > 0 else 0, 2
            ),
            "total_tokens": total_tokens,
            "avg_tokens_per_chunk": round(
                total_tokens / total_chunks if total_chunks > 0 else 0, 1
            ),
            "documents_chunked": chunked_docs,
            "documents_with_text": docs_with_text,
            "documents_not_chunked": docs_with_text - chunked_docs,
            "chunk_coverage_percent": round(
                (chunked_docs / docs_with_text * 100) if docs_with_text > 0 else 0, 2
            )
        }

    except Exception as e:
        # SECURITY FIX 28-25: Generische Fehlermeldung
        logger.exception("get_chunk_stats_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Statistiken fehlgeschlagen. Bitte versuchen Sie es erneut."
        )
