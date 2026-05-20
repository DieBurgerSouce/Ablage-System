"""RAG Intelligence Layer API Endpoints.

Endpoints für:
- Semantische Suche
- Chat mit Dokumenten
- Customer Cards
- Batch Jobs
- Analytics
"""

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

import structlog

from app.db.session import get_async_session
from app.api.dependencies import AsyncSessionLocal
from app.db.models import (
    User,
    Document,
    RAGDocumentChunk,
    RAGCustomerCard,
    RAGChatSession,
    RAGChatMessage,
    RAGBatchJob,
    RAGLLMModel,
    Company,
)
from app.api.dependencies import get_current_user, get_current_superuser
# S.3-S.5 SECURITY FIX: Company Context für Multi-Tenancy IDOR Protection
from app.middleware.company_context import require_company
from app.api.schemas.rag import (
    # Enums
    RAGSearchType,
    RAGContextType,
    RAGJobType,
    RAGJobStatus,
    RAGChatRole,
    # Search
    RAGSearchRequest,
    RAGSearchResponse,
    RAGChunkSearchResult,
    # Chat
    RAGChatRequest,
    RAGChatResponse,
    RAGChatSessionCreate,
    RAGChatSessionResponse,
    RAGChatSessionWithMessages,
    RAGChatMessageResponse,
    # Customer Cards
    RAGCustomerCardResponse,
    RAGCustomerCardSummary,
    # Batch Jobs
    RAGBatchJobCreate,
    RAGBatchJobResponse,
    RAGBatchJobSummary,
    # Chunking
    RAGChunkDocumentRequest,
    RAGChunkDocumentResponse,
    RAGBulkChunkRequest,
    # LLM Models
    RAGLLMModelResponse,
    # Business Intelligence
    BIQueryType,
    BITimeRange,
    BIQueryRequest,
    BIQueryResponse,
    BIChatRequest,
    BIChatResponse,
)
from app.services.rag import (
    RAGSearchService,
    get_rag_search_service,
    LLMService,
    LLMMessage,
    LLMContextType,
    get_llm_service,
    CustomerCardService,
    get_customer_card_service,
    DocumentChunkingService,
    get_chunking_service,
)
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/rag", tags=["RAG Intelligence"])


# ============================================================================
# SEARCH ENDPOINTS
# ============================================================================

@router.post("/search", response_model=RAGSearchResponse)
async def search_documents(
    request: RAGSearchRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RAGSearchResponse:
    """Führt semantische Suche auf Dokument-Chunks durch.

    Unterstützt:
    - Semantische Suche (Embedding-basiert)
    - Hybrid Search (Semantic + Keyword)
    - Optionales Reranking für bessere Präzision
    """
    search_service = get_rag_search_service()

    try:
        if request.search_type == RAGSearchType.SEMANTIC:
            response = await search_service.semantic_search(
                db=db,
                query=request.query,
                limit=request.limit,
                threshold=request.threshold,
                document_ids=request.document_ids,
                section_types=request.section_types,
                rerank=request.rerank,
                user_id=current_user.id,  # SECURITY: Nur eigene Dokumente durchsuchen
            )
        elif request.search_type == RAGSearchType.HYBRID:
            response = await search_service.hybrid_search(
                db=db,
                query=request.query,
                limit=request.limit,
                document_ids=request.document_ids,
                rerank=request.rerank,
                user_id=current_user.id,  # SECURITY: Nur eigene Dokumente durchsuchen
            )
        else:
            # Keyword-only Search
            response = await search_service.keyword_search(
                db=db,
                query=request.query,
                limit=request.limit,
                document_ids=request.document_ids,
                user_id=current_user.id,  # SECURITY: Nur eigene Dokumente durchsuchen
            )

        logger.info(
            "rag_search_completed",
            user_id=str(current_user.id),
            query_length=len(request.query),
            search_type=request.search_type.value,
            results_count=len(response.results),
            search_time_ms=response.search_time_ms,
        )

        return RAGSearchResponse(
            query=response.query,
            search_type=request.search_type,
            results=[
                RAGChunkSearchResult(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    chunk_text=r.chunk_text,
                    chunk_index=r.chunk_index,
                    page_number=r.page_number,
                    section_type=r.section_type,
                    similarity=r.similarity,
                    rerank_score=r.rerank_score,
                )
                for r in response.results
            ],
            total_results=response.total_results,
            search_time_ms=response.search_time_ms,
            embedding_time_ms=response.embedding_time_ms,
            rerank_time_ms=response.rerank_time_ms,
        )

    except Exception as e:
        # SECURITY FIX 28-18: Generische Fehlermeldung - keine internen Details exponieren
        logger.error("rag_search_failed", **safe_error_log(e), query=request.query[:100])
        raise HTTPException(status_code=500, detail="Suche fehlgeschlagen. Bitte versuchen Sie es erneut.")


# ============================================================================
# CHAT ENDPOINTS
# ============================================================================

@router.post("/chat", response_model=RAGChatResponse)
async def chat_with_documents(
    request: RAGChatRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RAGChatResponse:
    """Chat mit Dokumenten-Kontext.

    Verwendet RAG um relevante Dokument-Chunks zu finden und
    eine kontextbezogene Antwort zu generieren.

    Args:
        request: Chat-Anfrage mit Message und optional Session/Context

    Returns:
        RAGChatResponse mit Antwort, Quellen und Metriken
    """
    import secrets

    search_service = get_rag_search_service()
    llm_service = get_llm_service()

    try:
        # ===================================================================
        # PHASE 1: Alle DB-Operationen VOR dem LLM-Call (SQLAlchemy Concurrency Fix)
        # ===================================================================

        # Document-Context: Wenn context_type="document", dann nur in diesem Dokument suchen
        document_ids = None
        search_threshold = settings.RAG_SEMANTIC_THRESHOLD
        if request.context_type == "document" and request.context_id:
            from uuid import UUID
            try:
                document_ids = [UUID(request.context_id)]
                # Bei explizitem Dokument-Kontext: Threshold auf 0 setzen
                # damit alle Chunks des Dokuments gefunden werden
                search_threshold = 0.0
                logger.info(f"Chat mit Dokument-Kontext: {request.context_id} (threshold=0)")
            except ValueError:
                logger.warning(f"Ungültige Document-ID: {request.context_id}")

        # 1. Relevante Chunks finden
        search_response = await search_service.semantic_search(
            db=db,
            query=request.message,
            limit=settings.RAG_CHAT_CONTEXT_CHUNKS,
            threshold=search_threshold,
            document_ids=document_ids,
            rerank=settings.RAG_RERANK_ENABLED,
            user_id=current_user.id,  # SECURITY: Nur eigene Dokumente durchsuchen
        )

        # 2. Chat Session verwalten (Load or Create)
        if request.session_id:
            # Existierende Session laden
            session = await db.get(RAGChatSession, request.session_id)
            if not session or session.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="Chat-Session nicht gefunden")
        else:
            # Neue Session erstellen
            session = RAGChatSession(
                user_id=current_user.id,
                session_token=secrets.token_urlsafe(32),
                context_type=request.context_type.value if request.context_type else None,
                context_id=request.context_id,
                status="active",
            )
            db.add(session)
            await db.flush()

        # 3. User Message speichern
        user_message = RAGChatMessage(
            session_id=session.id,
            role="user",
            content=request.message,
        )
        db.add(user_message)

        # 4. Session-ID und Search-Results sichern, dann COMMIT
        # WICHTIG: Commit vor LLM-Call um DB-Session freizugeben
        session_id = session.id
        await db.commit()

        # ===================================================================
        # PHASE 2: LLM-Call (keine DB-Operationen aktiv)
        # ===================================================================

        # 5. Kontext aufbauen - mit Fallback auf direkten Dokument-Text
        context = ""
        fallback_used = False
        fallback_doc_name = None

        if search_response.results:
            # Normal: RAG-Chunks als Kontext
            context_chunks = [
                f"[Quelle: Dokument {r.document_id}, Seite {r.page_number or 'N/A'}]\n{r.chunk_text}"
                for r in search_response.results
            ]
            context = "\n\n---\n\n".join(context_chunks)
        elif document_ids:
            # Fallback: Dokument-Text direkt laden (keine Chunks vorhanden)
            from app.db.models import Document
            doc_result = await db.execute(
                select(Document).where(Document.id == document_ids[0])
            )
            doc = doc_result.scalar_one_or_none()

            if doc and doc.extracted_text:
                # Text ggf. kürzen (LLM-Context-Limit beachten)
                max_chars = 15000  # ~4000 Tokens
                text = doc.extracted_text[:max_chars]
                if len(doc.extracted_text) > max_chars:
                    text += "\n\n[... Text gekürzt, Dokument hat mehr Inhalt ...]"

                context = text
                fallback_used = True
                fallback_doc_name = doc.original_filename
                logger.info(
                    "chat_fallback_direct_text",
                    document_id=str(doc.id),
                    document_name=doc.original_filename,
                    text_length=len(doc.extracted_text),
                    truncated=len(doc.extracted_text) > max_chars,
                )
            else:
                # Dokument existiert aber hat keinen Text (noch nicht verarbeitet)
                logger.warning(
                    "chat_fallback_no_text",
                    document_id=str(document_ids[0]),
                    has_doc=doc is not None,
                    has_text=doc.extracted_text is not None if doc else False,
                )

        # 6. LLM Context Type bestimmen
        llm_context = LLMContextType.REALTIME if request.realtime else LLMContextType.GENERAL

        # 7. System-Prompt je nach Modus (Fallback vs RAG)
        if fallback_used:
            system_content = f"""Du bist ein hilfreicher Assistent.
Der Benutzer hat das Dokument '{fallback_doc_name}' hochgeladen.
Analysiere den Inhalt und beantworte Fragen dazu.
Antworte auf Deutsch.

DOKUMENTINHALT:
{context}"""
        else:
            system_content = f"""Du bist ein hilfreicher Assistent für ein Dokumentenmanagementsystem.
Beantworte Fragen basierend auf dem folgenden Kontext aus den Dokumenten.
Wenn du etwas nicht weisst, sage es ehrlich.
Antworte auf Deutsch.

KONTEXT:
{context}"""

        # 8. LLM Anfrage (lange Operation - DB ist frei)
        messages = [
            LLMMessage(role="system", content=system_content),
            LLMMessage(role="user", content=request.message),
        ]

        llm_response = await llm_service.generate(
            messages=messages,
            context_type=llm_context,
        )

        # ===================================================================
        # PHASE 3: Ergebnis speichern (neue Transaction)
        # ===================================================================

        # 8. Session neu laden (frische Transaction)
        session = await db.get(RAGChatSession, session_id)
        if not session:
            raise HTTPException(status_code=500, detail="Session verloren nach LLM-Call")

        # 9. Assistant Message speichern
        assistant_message = RAGChatMessage(
            session_id=session.id,
            role="assistant",
            content=llm_response.content,
            thinking_content=llm_response.thinking_content,
            model_used=llm_response.model,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            generation_time_ms=llm_response.generation_time_ms,
        )
        db.add(assistant_message)

        # 10. Session aktualisieren
        session.message_count = (session.message_count or 0) + 2
        session.last_message_at = datetime.now(timezone.utc)
        session.updated_at = datetime.now(timezone.utc)

        await db.commit()

        logger.info(
            "rag_chat_completed",
            user_id=str(current_user.id),
            session_id=str(session.id),
            context_chunks=len(search_response.results),
            model=llm_response.model,
            generation_time_ms=llm_response.generation_time_ms,
        )

        return RAGChatResponse(
            session_id=session.id,
            message=llm_response.content,
            thinking_content=llm_response.thinking_content,
            sources=[
                RAGChunkSearchResult(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    chunk_text=r.chunk_text[:200] + "..." if len(r.chunk_text) > 200 else r.chunk_text,
                    chunk_index=r.chunk_index,
                    page_number=r.page_number,
                    section_type=r.section_type,
                    similarity=r.similarity,
                    rerank_score=r.rerank_score,
                )
                for r in search_response.results
            ],
            model_used=llm_response.model,
            generation_time_ms=llm_response.generation_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        # SECURITY FIX 28-18: Generische Fehlermeldung - keine internen Details exponieren
        logger.error("rag_chat_failed", **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Chat fehlgeschlagen. Bitte versuchen Sie es erneut.")


@router.post("/chat/stream")
async def chat_with_documents_stream(
    request: RAGChatRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Chat mit Dokumenten-Kontext (Streaming).

    WICHTIG: Dieser Endpoint verwendet KEINE Depends(db) weil StreamingResponse
    einen anderen Lifecycle hat als normale Endpoints. FastAPI würde die DB-Session
    schließen bevor der Stream fertig ist.

    Stattdessen werden alle DB-Operationen mit manuell verwalteten Sessions gemacht.

    Event-Typen:
    - chunk: Text-Chunk der Antwort
    - source: Quellen-Referenz
    - thinking: Denk-Prozess (optional)
    - done: Abschluss mit Session-ID
    - error: Fehler-Meldung
    """
    import json
    import secrets

    search_service = get_rag_search_service()
    llm_service = get_llm_service()

    # ===================================================================
    # PHASE 1: Pre-Stream DB-Ops mit EIGENER Session
    # Diese Session wird komplett abgeschlossen bevor StreamingResponse
    # zurückgegeben wird.
    # ===================================================================

    try:
        async with AsyncSessionLocal() as db:
            # Document-Context: Wenn context_type="document", dann nur in diesem Dokument suchen
            document_ids = None
            search_threshold = settings.RAG_SEMANTIC_THRESHOLD
            if request.context_type == "document" and request.context_id:
                from uuid import UUID
                try:
                    document_ids = [UUID(request.context_id)]
                    # Bei explizitem Dokument-Kontext: Threshold auf 0 setzen
                    search_threshold = 0.0
                    logger.info(f"Streaming Chat mit Dokument-Kontext: {request.context_id} (threshold=0)")
                except ValueError:
                    logger.warning(f"Ungültige Document-ID: {request.context_id}")

            # 1. Relevante Chunks finden
            search_response = await search_service.semantic_search(
                db=db,
                query=request.message,
                limit=settings.RAG_CHAT_CONTEXT_CHUNKS,
                threshold=search_threshold,
                document_ids=document_ids,
                rerank=settings.RAG_RERANK_ENABLED,
                user_id=current_user.id,  # SECURITY: Nur eigene Dokumente durchsuchen
            )

            # 2. Chat Session verwalten
            if request.session_id:
                session = await db.get(RAGChatSession, request.session_id)
                if not session or session.user_id != current_user.id:
                    async def error_stream():
                        yield f"data: {json.dumps({'type': 'error', 'error': 'Session nicht gefunden'})}\n\n"
                    return StreamingResponse(
                        error_stream(),
                        media_type="text/event-stream",
                    )
            else:
                session = RAGChatSession(
                    user_id=current_user.id,
                    session_token=secrets.token_urlsafe(32),
                    context_type=request.context_type.value if request.context_type else None,
                    context_id=request.context_id,
                    status="active",
                )
                db.add(session)
                await db.flush()

            # 3. User Message speichern
            user_message = RAGChatMessage(
                session_id=session.id,
                role="user",
                content=request.message,
            )
            db.add(user_message)

            # 4. Session-ID sichern und COMMIT
            session_id = session.id
            user_id = current_user.id

            # 5. Fallback: Wenn keine Chunks, aber Dokument-Kontext, Text direkt laden
            fallback_context = None
            fallback_doc_name = None
            if not search_response.results and document_ids:
                from app.db.models import Document
                doc_result = await db.execute(
                    select(Document).where(Document.id == document_ids[0])
                )
                doc = doc_result.scalar_one_or_none()

                if doc and doc.extracted_text:
                    max_chars = 15000  # ~4000 Tokens
                    text = doc.extracted_text[:max_chars]
                    if len(doc.extracted_text) > max_chars:
                        text += "\n\n[... Text gekürzt, Dokument hat mehr Inhalt ...]"

                    fallback_context = text
                    fallback_doc_name = doc.original_filename
                    logger.info(
                        "stream_fallback_direct_text",
                        document_id=str(doc.id),
                        document_name=doc.original_filename,
                        text_length=len(doc.extracted_text),
                        truncated=len(doc.extracted_text) > max_chars,
                    )

            await db.commit()

            # 6. Search results für Generator sichern (außerhalb der Session)
            search_results = list(search_response.results)

    except Exception as e:
        logger.error("rag_chat_stream_setup_failed", **safe_error_log(e))
        async def error_stream():
            yield f"data: {json.dumps({'type': 'error', 'error': safe_error_detail(e, 'RAG')})}\n\n"
        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
        )

    # ===================================================================
    # PHASE 2: Streaming Generator
    # Keine äußere DB-Session mehr aktiv - der Context Manager ist beendet!
    # ===================================================================

    async def generate_stream():
        """Generator für SSE-Events."""
        try:
            # 7. Kontext aufbauen - Normal oder Fallback
            if fallback_context:
                # Fallback-Modus: Direkter Dokumenttext
                context = fallback_context

                # 8. System-Prompt für Fallback
                system_content = f"""Du bist ein hilfreicher Assistent.
Der Benutzer hat das Dokument '{fallback_doc_name}' hochgeladen.
Analysiere den Inhalt und beantworte Fragen dazu.
Antworte auf Deutsch.

DOKUMENTINHALT:
{context}"""
                # Keine Quellen senden bei Fallback (keine Chunks vorhanden)
            else:
                # Normal-Modus: RAG-Chunks
                context_chunks = [
                    f"[Quelle: Dokument {r.document_id}, Seite {r.page_number or 'N/A'}]\n{r.chunk_text}"
                    for r in search_results
                ]
                context = "\n\n---\n\n".join(context_chunks)

                # 8. System-Prompt für RAG
                system_content = f"""Du bist ein hilfreicher Assistent für ein Dokumentenmanagementsystem.
Beantworte Fragen basierend auf dem folgenden Kontext aus den Dokumenten.
Wenn du etwas nicht weisst, sage es ehrlich.
Antworte auf Deutsch.

KONTEXT:
{context}"""

                # 9. Quellen senden (nur bei RAG-Modus)
                for r in search_results:
                    source_event = {
                        "type": "source",
                        "source": {
                            "chunk_id": str(r.chunk_id),
                            "document_id": str(r.document_id),
                            "chunk_text": r.chunk_text[:200] + "..." if len(r.chunk_text) > 200 else r.chunk_text,
                            "chunk_index": r.chunk_index,
                            "page_number": r.page_number,
                            "section_type": r.section_type,
                            "similarity": r.similarity,
                            "rerank_score": r.rerank_score,
                        }
                    }
                    yield f"data: {json.dumps(source_event)}\n\n"

            # 10. LLM Context
            llm_context = LLMContextType.REALTIME if request.realtime else LLMContextType.GENERAL

            # 11. LLM Streaming
            messages = [
                LLMMessage(role="system", content=system_content),
                LLMMessage(role="user", content=request.message),
            ]

            full_response = ""
            async for chunk in llm_service.generate_stream(
                messages=messages,
                context_type=llm_context,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # ===================================================================
            # PHASE 3: Post-Stream DB-Ops mit EIGENER Session
            # ===================================================================

            async with AsyncSessionLocal() as post_db:
                session = await post_db.get(RAGChatSession, session_id)
                if not session:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Session verloren'})}\n\n"
                    return

                # 10. Assistant Message speichern
                assistant_message = RAGChatMessage(
                    session_id=session.id,
                    role="assistant",
                    content=full_response,
                )
                post_db.add(assistant_message)

                # 11. Session aktualisieren
                session.message_count = (session.message_count or 0) + 2
                session.last_message_at = datetime.now(timezone.utc)
                session.updated_at = datetime.now(timezone.utc)

                await post_db.commit()

                # 12. Done Event
                yield f"data: {json.dumps({'type': 'done', 'session_id': str(session.id), 'message_id': str(assistant_message.id)})}\n\n"

                logger.info(
                    "rag_chat_stream_completed",
                    user_id=str(user_id),
                    session_id=str(session.id),
                    context_chunks=len(search_results),
                    response_length=len(full_response),
                )

        except Exception as e:
            logger.error("rag_chat_stream_failed", **safe_error_log(e))
            yield f"data: {json.dumps({'type': 'error', 'error': safe_error_detail(e, 'RAG')})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


@router.delete("/chat/sessions/{session_id}")
async def delete_chat_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Löscht eine Chat-Session (soft delete)."""
    session = await db.get(RAGChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")

    session.status = "archived"
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "success", "message": "Session archiviert"}


@router.put("/chat/sessions/{session_id}")
async def update_chat_session(
    session_id: UUID,
    title: str = Query(..., min_length=1, max_length=255),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RAGChatSessionResponse:
    """Aktualisiert den Titel einer Chat-Session."""
    session = await db.get(RAGChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")

    session.title = title
    session.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return RAGChatSessionResponse.model_validate(session)


@router.get("/chat/sessions", response_model=List[RAGChatSessionResponse])
async def list_chat_sessions(
    page: int = Query(default=1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(default=20, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[RAGChatSessionResponse]:
    """Listet Chat-Sessions des aktuellen Users auf."""
    query = (
        select(RAGChatSession)
        .where(RAGChatSession.user_id == current_user.id)
        .where(RAGChatSession.status == "active")
        .order_by(RAGChatSession.updated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    sessions = result.scalars().all()

    return [RAGChatSessionResponse.model_validate(s) for s in sessions]


@router.post("/chat/sessions", response_model=RAGChatSessionResponse)
async def create_chat_session(
    request: RAGChatSessionCreate,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RAGChatSessionResponse:
    """Erstellt eine neue leere Chat-Session."""
    import secrets

    session = RAGChatSession(
        user_id=current_user.id,
        session_token=secrets.token_urlsafe(32),
        title=request.title,
        context_type=request.context_type.value if request.context_type else None,
        context_id=request.context_id,
        status="active",
        message_count=0,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "rag_chat_session_created",
        user_id=str(current_user.id),
        session_id=str(session.id),
    )

    return RAGChatSessionResponse.model_validate(session)


@router.get("/chat/sessions/{session_id}", response_model=RAGChatSessionWithMessages)
async def get_chat_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RAGChatSessionWithMessages:
    """Laedt eine Chat-Session mit allen Messages."""
    session = await db.get(RAGChatSession, session_id)
    if not session or session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")

    # Messages laden
    messages_query = (
        select(RAGChatMessage)
        .where(RAGChatMessage.session_id == session_id)
        .order_by(RAGChatMessage.created_at.asc())
    )
    result = await db.execute(messages_query)
    messages = result.scalars().all()

    return RAGChatSessionWithMessages(
        id=session.id,
        user_id=session.user_id,
        session_token=session.session_token,
        title=session.title,
        context_type=session.context_type,
        context_id=session.context_id,
        status=session.status,
        message_count=session.message_count or 0,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at,
        messages=[RAGChatMessageResponse.model_validate(m) for m in messages],
    )


# ============================================================================
# CUSTOMER CARDS ENDPOINTS
# ============================================================================

@router.get("/customer-cards", response_model=List[RAGCustomerCardSummary])
async def list_customer_cards(
    search: Optional[str] = Query(None, min_length=1, max_length=100),
    page: int = Query(default=1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(default=20, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    # S.4 SECURITY FIX: Company Context für Multi-Tenancy IDOR Protection
    company_ctx: Company = Depends(require_company),
) -> List[RAGCustomerCardSummary]:
    """Listet Customer Cards auf, optional mit Suche.

    SECURITY: Nur Customer Cards der eigenen Company werden zurückgegeben.
    """
    # S.4 SECURITY FIX: Nur Cards der eigenen Company zurückgeben
    query = select(RAGCustomerCard).where(
        RAGCustomerCard.company_id == company_ctx.company_id
    ).order_by(RAGCustomerCard.priority_level.desc())

    if search:
        query = query.where(RAGCustomerCard.customer_name.ilike(f"%{search}%"))

    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    cards = result.scalars().all()

    return [
        RAGCustomerCardSummary(
            customer_id=c.customer_id,
            customer_name=c.customer_name,
            customer_type=c.customer_type,
            priority_level=c.priority_level or 0,
            flags=c.flags or [],
            last_sync_at=c.last_full_sync_at,
        )
        for c in cards
    ]


@router.get("/customer-cards/{customer_id}", response_model=RAGCustomerCardResponse)
async def get_customer_card(
    customer_id: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    # S.3 SECURITY FIX: Company Context für Multi-Tenancy IDOR Protection
    company_ctx: Company = Depends(require_company),
) -> RAGCustomerCardResponse:
    """Laedt eine einzelne Customer Card.

    SECURITY: Nur Customer Cards der eigenen Company können geladen werden.
    """
    # S.3 SECURITY FIX: Nur Cards der eigenen Company laden
    query = select(RAGCustomerCard).where(
        RAGCustomerCard.customer_id == customer_id,
        RAGCustomerCard.company_id == company_ctx.company_id,
    )
    result = await db.execute(query)
    card = result.scalar_one_or_none()

    if not card:
        raise HTTPException(status_code=404, detail="Customer Card nicht gefunden")

    return RAGCustomerCardResponse.model_validate(card)


@router.post("/customer-cards/{customer_id}/refresh")
async def refresh_customer_card(
    customer_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    # S.5 SECURITY FIX: Company Context für Multi-Tenancy IDOR Protection
    company_ctx: Company = Depends(require_company),
) -> dict:
    """Aktualisiert eine Customer Card asynchron.

    SECURITY: Nur Customer Cards der eigenen Company können aktualisiert werden.
    """
    card_service = get_customer_card_service()

    # S.5 SECURITY FIX: Prüfe ob Customer Card existiert UND zur Company gehoert
    query = select(RAGCustomerCard).where(
        RAGCustomerCard.customer_id == customer_id,
        RAGCustomerCard.company_id == company_ctx.company_id,
    )
    result = await db.execute(query)
    card = result.scalar_one_or_none()

    if not card:
        raise HTTPException(status_code=404, detail="Customer Card nicht gefunden")

    # Background Task starten
    background_tasks.add_task(
        card_service.refresh_card,
        customer_id=customer_id,
    )

    return {
        "status": "accepted",
        "message": f"Customer Card {customer_id} wird aktualisiert",
    }


# ============================================================================
# CHUNKING ENDPOINTS
# ============================================================================

@router.post("/chunks", response_model=RAGChunkDocumentResponse)
async def chunk_document(
    request: RAGChunkDocumentRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RAGChunkDocumentResponse:
    """Chunked ein Dokument und generiert Embeddings.

    SECURITY: Nur eigene Dokumente können gechunkt werden.
    """
    # SECURITY: Prüfen ob User das Dokument besitzt
    doc = await db.get(Document, request.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    if doc.owner_id != current_user.id:
        logger.warning(
            "security_access_denied",
            action="chunk_document",
            user_id=str(current_user.id),
            document_id=str(request.document_id),
            owner_id=str(doc.owner_id) if doc.owner_id else None,
        )
        raise HTTPException(status_code=404, detail="Dokument nicht gefunden")

    chunking_service = get_chunking_service()

    try:
        result = await chunking_service.chunk_document(
            db=db,
            document_id=request.document_id,
            strategy=request.strategy,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
            generate_embeddings=request.generate_embeddings,
        )

        logger.info(
            "rag_document_chunked",
            document_id=str(request.document_id),
            chunks_created=result.chunks_created,
            total_tokens=result.total_tokens,
        )

        return RAGChunkDocumentResponse(
            document_id=request.document_id,
            chunks_created=result.chunks_created,
            total_tokens=result.total_tokens,
            strategy_used=result.strategy_used,
            processing_time_ms=result.processing_time_ms,
        )

    except Exception as e:
        # SECURITY FIX 28-18: Generische Fehlermeldung - keine internen Details exponieren
        logger.error("rag_chunking_failed", document_id=str(request.document_id), **safe_error_log(e))
        raise HTTPException(status_code=500, detail="Chunking fehlgeschlagen. Bitte versuchen Sie es erneut.")


@router.post("/chunks/bulk")
async def bulk_chunk_documents(
    request: RAGBulkChunkRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Startet Bulk-Chunking als Background Task.

    SECURITY: Nur eigene Dokumente können gechunkt werden.
    """
    # SECURITY: Wenn document_ids angegeben, prüfen ob alle dem User gehoeren
    if request.document_ids:
        query = select(func.count()).select_from(Document).where(
            Document.id.in_(request.document_ids),
            Document.owner_id == current_user.id
        )
        result = await db.execute(query)
        valid_count = result.scalar()

        if valid_count != len(request.document_ids):
            logger.warning(
                "security_access_denied",
                action="bulk_chunk_documents",
                user_id=str(current_user.id),
                requested_count=len(request.document_ids),
                valid_count=valid_count,
            )
            raise HTTPException(
                status_code=403,
                detail="Nicht alle angegebenen Dokumente gehoeren Ihnen"
            )

    # Batch Job erstellen - immer mit user_id für Filter im Background Task
    job = RAGBatchJob(
        job_type="chunk_documents",
        job_name=f"Bulk Chunking - {datetime.now(timezone.utc).isoformat()}",
        created_by_id=current_user.id,
        parameters={
            "document_ids": [str(d) for d in request.document_ids] if request.document_ids else None,
            "user_id": str(current_user.id),  # SECURITY: User-ID für Filter im Background Task
            "force": request.force,
            "strategy": request.strategy,
        },
        status="pending",
    )
    db.add(job)
    await db.commit()

    return {
        "status": "accepted",
        "job_id": str(job.id),
        "message": "Bulk-Chunking gestartet",
    }


# ============================================================================
# LLM MODELS ENDPOINTS
# ============================================================================

@router.get("/models", response_model=List[RAGLLMModelResponse])
async def list_llm_models(
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[RAGLLMModelResponse]:
    """Listet verfügbare LLM-Modelle auf."""
    query = select(RAGLLMModel)
    if active_only:
        query = query.where(RAGLLMModel.is_active == True)
    query = query.order_by(RAGLLMModel.priority.desc())

    result = await db.execute(query)
    models = result.scalars().all()

    return [RAGLLMModelResponse.model_validate(m) for m in models]


# ============================================================================
# BATCH JOBS ENDPOINTS
# ============================================================================

@router.get("/jobs", response_model=List[RAGBatchJobSummary])
async def list_batch_jobs(
    status: Optional[RAGJobStatus] = None,
    job_type: Optional[RAGJobType] = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[RAGBatchJobSummary]:
    """Listet Batch-Jobs auf.

    SECURITY: Zeigt nur Jobs an, die vom aktuellen User erstellt wurden.
    """
    query = (
        select(RAGBatchJob)
        .where(RAGBatchJob.created_by_id == current_user.id)  # SECURITY: Nur eigene Jobs
        .order_by(RAGBatchJob.created_at.desc())
    )

    if status:
        query = query.where(RAGBatchJob.status == status.value)
    if job_type:
        query = query.where(RAGBatchJob.job_type == job_type.value)

    query = query.limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()

    return [
        RAGBatchJobSummary(
            id=j.id,
            job_type=j.job_type,
            status=RAGJobStatus(j.status),
            progress_percent=j.progress_percent or 0,
            items_processed=j.items_processed or 0,
            items_total=j.items_total,
            started_at=j.started_at,
        )
        for j in jobs
    ]


@router.get("/jobs/{job_id}", response_model=RAGBatchJobResponse)
async def get_batch_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> RAGBatchJobResponse:
    """Laedt Details eines Batch-Jobs.

    SECURITY: Zeigt nur Jobs an, die vom aktuellen User erstellt wurden.
    """
    job = await db.get(RAGBatchJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    if job.created_by_id != current_user.id:
        logger.warning(
            "security_access_denied",
            action="get_batch_job",
            user_id=str(current_user.id),
            job_id=str(job_id),
            owner_id=str(job.created_by_id) if job.created_by_id else None,
        )
        raise HTTPException(status_code=404, detail="Job nicht gefunden")

    return RAGBatchJobResponse.model_validate(job)


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def rag_health_check(
    current_user: User = Depends(get_current_superuser),  # AA.1 SECURITY FIX: Admin required
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Health Check für RAG Services.

    **REQUIRES ADMIN AUTHENTICATION**

    Args:
        current_user: Authenticated admin user (required)
    """
    health = {
        "status": "healthy",
        "components": {},
    }

    # Database Check
    try:
        result = await db.execute(text("SELECT 1"))
        health["components"]["database"] = "healthy"
    except Exception as e:
        health["components"]["database"] = safe_error_detail(e, "Vorgang")
        health["status"] = "degraded"

    # Embedding Service Check
    try:
        from app.services.embedding_service import get_embedding_service
        embedding_service = get_embedding_service()
        info = embedding_service.get_model_info()
        health["components"]["embedding_service"] = {
            "status": "healthy" if info.get("loaded") else "not_loaded",
            "model": info.get("model_name"),
            "device": info.get("device"),
        }
    except Exception as e:
        health["components"]["embedding_service"] = safe_error_detail(e, "Vorgang")
        health["status"] = "degraded"

    # LLM Service Check
    try:
        llm_service = get_llm_service()
        llm_healthy = await llm_service.health_check()
        health["components"]["llm_service"] = "healthy" if llm_healthy else "unhealthy"
        if not llm_healthy:
            health["status"] = "degraded"
    except Exception as e:
        health["components"]["llm_service"] = safe_error_detail(e, "Vorgang")
        health["status"] = "degraded"

    return health


# ============================================================================
# BUSINESS INTELLIGENCE ENDPOINTS
# ============================================================================

@router.post("/bi/query", response_model=None)
async def business_intelligence_query(
    request: "BIQueryRequest",
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """
    Führt eine Business Intelligence Abfrage durch.

    Unterstützt natürlichsprachige Anfragen wie:
    - "Finde alle Rechnungen von Mueller GmbH aus Q3"
    - "Wie haben sich die Marketing-Ausgaben entwickelt?"
    - "Wann zahlt Kunde X?"
    - "Zeige offene Posten"

    Der Endpoint erkennt automatisch den Query-Typ und routet
    zur passenden Analyse-Funktion.
    """
    from app.api.schemas.rag import BIQueryRequest, BIQueryResponse, BITimeRange
    from app.services.business_intelligence_service import (
        get_bi_service,
        TimeRange,
    )

    bi_service = get_bi_service()

    # Map BITimeRange to internal TimeRange
    time_range_map = {
        BITimeRange.LAST_7_DAYS: TimeRange.LAST_7_DAYS,
        BITimeRange.LAST_30_DAYS: TimeRange.LAST_30_DAYS,
        BITimeRange.LAST_QUARTER: TimeRange.LAST_QUARTER,
        BITimeRange.LAST_YEAR: TimeRange.LAST_YEAR,
        BITimeRange.THIS_MONTH: TimeRange.THIS_MONTH,
        BITimeRange.THIS_QUARTER: TimeRange.THIS_QUARTER,
        BITimeRange.THIS_YEAR: TimeRange.THIS_YEAR,
        BITimeRange.ALL_TIME: TimeRange.ALL_TIME,
        BITimeRange.CUSTOM: TimeRange.CUSTOM,
    }

    try:
        result = await bi_service.process_query(
            db=db,
            user_id=current_user.id,
            company_id=company.id,
            query=request.query,
        )

        from app.api.schemas.rag import BIQueryType

        return BIQueryResponse(
            query_type=BIQueryType(result.query_type.value),
            summary=result.summary,
            data=result.data,
            suggestions=result.suggestions if request.include_suggestions else [],
            query_time_ms=result.query_time_ms,
        )

    except Exception as e:
        logger.error("bi_query_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Analyse fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


@router.post("/bi/invoices", response_model=None)
async def analyze_invoices(
    time_range: Optional[str] = Query("this_year", description="Zeitraum für Analyse"),
    entity_id: Optional[UUID] = Query(None, description="Filter auf Entitaet"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """
    Analysiert Rechnungen mit Aggregationen.

    Liefert:
    - Gesamtanzahl und -betrag
    - Bezahlte vs. offene Rechnungen
    - Überfällige Rechnungen
    - Aufschluesselung nach Monat
    - Top-Entitaeten nach Umsatz
    """
    from app.services.business_intelligence_service import get_bi_service, TimeRange
    from app.api.schemas.rag import BIQueryResponse, BIQueryType

    bi_service = get_bi_service()

    time_range_enum = TimeRange(time_range) if time_range else TimeRange.THIS_YEAR

    result = await bi_service.analyze_invoices(
        db=db,
        user_id=current_user.id,
        company_id=company.id,
        entity_id=entity_id,
        time_range=time_range_enum,
    )

    return BIQueryResponse(
        query_type=BIQueryType.INVOICE_ANALYSIS,
        summary=result.summary,
        data=result.data,
        suggestions=result.suggestions,
        query_time_ms=result.query_time_ms,
    )


@router.get("/bi/entity/{entity_id}", response_model=None)
async def get_entity_statistics(
    entity_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """
    Holt Statistiken für eine spezifische Geschäftsentitaet.

    Liefert:
    - Dokumenten-Anzahl
    - Rechnungs-Statistiken
    - Gesamtumsatz
    - Offene Posten
    - Risiko-Score
    - Letzte Aktivitaet
    """
    from app.services.business_intelligence_service import get_bi_service
    from app.api.schemas.rag import BIQueryResponse, BIQueryType

    bi_service = get_bi_service()

    result = await bi_service.get_entity_statistics(
        db=db,
        user_id=current_user.id,
        company_id=company.id,
        entity_id=entity_id,
    )

    return BIQueryResponse(
        query_type=BIQueryType.ENTITY_STATISTICS,
        summary=result.summary,
        data=result.data,
        suggestions=result.suggestions,
        query_time_ms=result.query_time_ms,
    )


@router.get("/bi/entity/search/{name}", response_model=None)
async def search_entity_statistics(
    name: str,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """
    Sucht Entitaet nach Name und liefert Statistiken.

    Unterstützt Teilsuche (z.B. "Mueller" findet "Mueller GmbH").
    """
    from app.services.business_intelligence_service import get_bi_service
    from app.api.schemas.rag import BIQueryResponse, BIQueryType

    bi_service = get_bi_service()

    result = await bi_service.get_entity_statistics(
        db=db,
        user_id=current_user.id,
        company_id=company.id,
        entity_name=name,
    )

    return BIQueryResponse(
        query_type=BIQueryType.ENTITY_STATISTICS,
        summary=result.summary,
        data=result.data,
        suggestions=result.suggestions,
        query_time_ms=result.query_time_ms,
    )


@router.get("/bi/payment-prediction/{entity_id}", response_model=None)
async def predict_payment(
    entity_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """
    Prognostiziert Zahlungsverhalten einer Entitaet.

    Analysiert historische Zahlungen und liefert:
    - Erwartete Zahlungsdauer in Tagen
    - Konfidenz der Prognose
    - Trend (verbessert sich, stabil, verschlechtert sich)
    - Erklärende Faktoren
    """
    from app.services.business_intelligence_service import get_bi_service
    from app.api.schemas.rag import BIQueryResponse, BIQueryType

    bi_service = get_bi_service()

    result = await bi_service.predict_payment(
        db=db,
        user_id=current_user.id,
        company_id=company.id,
        entity_id=entity_id,
    )

    return BIQueryResponse(
        query_type=BIQueryType.PAYMENT_PREDICTION,
        summary=result.summary,
        data=result.data,
        suggestions=result.suggestions,
        query_time_ms=result.query_time_ms,
    )


@router.post("/bi/trends", response_model=None)
async def analyze_trends(
    metric: str = Query("revenue", description="Metrik: revenue, invoice_count"),
    time_range: str = Query("last_year", description="Zeitraum"),
    group_by: str = Query("month", description="Gruppierung: month, quarter, year"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """
    Analysiert Trends für eine gegebene Metrik.

    Unterstützte Metriken:
    - revenue: Umsatzentwicklung
    - invoice_count: Anzahl Rechnungen

    Gruppierungen:
    - month: Monatlich
    - quarter: Quartalweise
    - year: Jährlich
    """
    from app.services.business_intelligence_service import get_bi_service, TimeRange
    from app.api.schemas.rag import BIQueryResponse, BIQueryType

    bi_service = get_bi_service()

    time_range_enum = TimeRange(time_range) if time_range else TimeRange.LAST_YEAR

    result = await bi_service.analyze_trends(
        db=db,
        user_id=current_user.id,
        company_id=company.id,
        metric=metric,
        time_range=time_range_enum,
        group_by=group_by,
    )

    return BIQueryResponse(
        query_type=BIQueryType.TREND_ANALYSIS,
        summary=result.summary,
        data=result.data,
        suggestions=result.suggestions,
        query_time_ms=result.query_time_ms,
    )


@router.post("/bi/chat", response_model=None)
async def bi_enhanced_chat(
    request: "BIChatRequest",
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """
    Chat mit kombiniertem RAG- und Business Intelligence-Kontext.

    Dieser Endpoint:
    1. Erkennt ob die Anfrage eine BI-Frage ist
    2. Führt ggf. BI-Analyse durch
    3. Kombiniert BI-Ergebnisse mit RAG-Dokumentkontext
    4. Generiert eine umfassende Antwort

    Beispiele:
    - "Finde alle Rechnungen von Mueller GmbH" -> BI + Dokument-Suche
    - "Wie entwickelt sich der Umsatz?" -> BI Trend-Analyse
    - "Was steht im Vertrag mit X?" -> RAG Dokument-Suche
    """
    import secrets
    from app.api.schemas.rag import BIChatRequest, BIChatResponse, BIQueryResponse, BIQueryType
    from app.services.business_intelligence_service import get_bi_service, QueryType

    search_service = get_rag_search_service()
    llm_service = get_llm_service()
    bi_service = get_bi_service()

    bi_insights = None
    bi_context = ""

    try:
        # 1. BI-Analyse wenn aktiviert
        if request.enable_bi:
            query_type = bi_service.detect_query_type(request.message)

            # Nur BI-relevante Anfragen verarbeiten
            if query_type != QueryType.SUMMARY:
                bi_result = await bi_service.process_query(
                    db=db,
                    user_id=current_user.id,
                    company_id=company.id,
                    query=request.message,
                )

                bi_insights = BIQueryResponse(
                    query_type=BIQueryType(bi_result.query_type.value),
                    summary=bi_result.summary,
                    data=bi_result.data,
                    suggestions=bi_result.suggestions,
                    query_time_ms=bi_result.query_time_ms,
                )

                # BI-Kontext für LLM aufbauen
                bi_context = f"""
BUSINESS INTELLIGENCE ERGEBNISSE:
{bi_result.summary}

STRUKTURIERTE DATEN:
{bi_result.data}
"""

        # 2. RAG-Suche durchführen
        document_ids = None
        search_threshold = settings.RAG_SEMANTIC_THRESHOLD

        if request.context_type == "document" and request.context_id:
            try:
                document_ids = [UUID(request.context_id)]
                search_threshold = 0.0
            except ValueError as e:
                logger.debug(
                    "context_id_uuid_parse_failed",
                    error_type=type(e).__name__,
                )

        search_response = await search_service.semantic_search(
            db=db,
            query=request.message,
            limit=settings.RAG_CHAT_CONTEXT_CHUNKS,
            threshold=search_threshold,
            document_ids=document_ids,
            rerank=settings.RAG_RERANK_ENABLED,
            user_id=current_user.id,
        )

        # 3. Chat Session verwalten
        if request.session_id:
            session = await db.get(RAGChatSession, request.session_id)
            if not session or session.user_id != current_user.id:
                raise HTTPException(status_code=404, detail="Chat-Session nicht gefunden")
        else:
            session = RAGChatSession(
                user_id=current_user.id,
                session_token=secrets.token_urlsafe(32),
                context_type=request.context_type.value if request.context_type else None,
                context_id=request.context_id,
                status="active",
            )
            db.add(session)
            await db.flush()

        # 4. User Message speichern
        user_message = RAGChatMessage(
            session_id=session.id,
            role="user",
            content=request.message,
        )
        db.add(user_message)

        session_id = session.id
        await db.commit()

        # 5. Kontext aufbauen (RAG + BI)
        context_chunks = []
        if search_response.results:
            context_chunks = [
                f"[Quelle: Dokument {r.document_id}]\n{r.chunk_text}"
                for r in search_response.results
            ]

        rag_context = "\n\n---\n\n".join(context_chunks) if context_chunks else ""

        # 6. System-Prompt mit beiden Kontexten
        system_content = f"""Du bist ein intelligenter Geschäftsassistent für ein Dokumentenmanagementsystem.
Du hast Zugriff auf:
1. Strukturierte Geschäftsdaten (Rechnungen, Kunden, Statistiken)
2. Dokumenteninhalte (Verträge, Korrespondenz, etc.)

Beantworte Fragen praezise und hilfreich.
Nutze die verfügbaren Daten um fundierte Antworten zu geben.
Antworte immer auf Deutsch.

{bi_context}

DOKUMENTKONTEXT:
{rag_context if rag_context else "(Keine relevanten Dokumente gefunden)"}
"""

        # 7. LLM Anfrage
        messages = [
            LLMMessage(role="system", content=system_content),
            LLMMessage(role="user", content=request.message),
        ]

        llm_context = LLMContextType.REALTIME if request.realtime else LLMContextType.GENERAL
        llm_response = await llm_service.generate(
            messages=messages,
            context_type=llm_context,
        )

        # 8. Session aktualisieren
        session = await db.get(RAGChatSession, session_id)
        if session:
            assistant_message = RAGChatMessage(
                session_id=session.id,
                role="assistant",
                content=llm_response.content,
                thinking_content=llm_response.thinking_content,
                model_used=llm_response.model,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                generation_time_ms=llm_response.generation_time_ms,
            )
            db.add(assistant_message)

            session.message_count = (session.message_count or 0) + 2
            session.last_message_at = datetime.now(timezone.utc)
            await db.commit()

        logger.info(
            "bi_chat_completed",
            user_id=str(current_user.id),
            session_id=str(session_id),
            has_bi_insights=bi_insights is not None,
            rag_chunks=len(search_response.results),
            model=llm_response.model,
        )

        return BIChatResponse(
            session_id=session_id,
            message=llm_response.content,
            thinking_content=llm_response.thinking_content,
            sources=[
                RAGChunkSearchResult(
                    chunk_id=r.chunk_id,
                    document_id=r.document_id,
                    chunk_text=r.chunk_text[:200] + "..." if len(r.chunk_text) > 200 else r.chunk_text,
                    chunk_index=r.chunk_index,
                    page_number=r.page_number,
                    section_type=r.section_type,
                    similarity=r.similarity,
                    rerank_score=r.rerank_score,
                )
                for r in search_response.results
            ],
            bi_insights=bi_insights,
            model_used=llm_response.model,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            generation_time_ms=llm_response.generation_time_ms,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("bi_chat_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail="Chat fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


# ============================================================================
# AI ASSISTANT ACTIONS ENDPOINTS
# ============================================================================

@router.get("/ai/actions")
async def list_ai_actions(
    context_type: Optional[str] = Query(None, description="Kontext-Typ (document, entity)"),
    current_user: User = Depends(get_current_user),
) -> "AIActionListResponse":
    """Listet verfügbare AI-Aktionen basierend auf Benutzerrolle auf.

    Autonomie-Level:
    - Viewer: Nur Lese-Aktionen (Suche, Analyse, Berichte)
    - Editor: Supervised Actions (Vorschlag + Bestätigung erforderlich)
    - Admin: Autonome Aktionen (selbststaendig ausführbar)
    """
    from app.api.schemas.rag import AIActionListResponse
    from app.services.rag.ai_action_service import get_ai_action_service

    action_service = get_ai_action_service()
    return action_service.get_available_actions(user=current_user, context_type=context_type)


@router.post("/ai/actions/execute")
async def execute_ai_action(
    request: "AIActionRequest",
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> "AIActionResult":
    """Führt eine AI-Aktion aus.

    Bei Aktionen die Bestätigung erfordern (Editor-Level):
    - Status wird auf 'suggested' gesetzt
    - User muss über /ai/actions/confirm bestätigen

    Bei Admin-Level oder auto_execute=True:
    - Aktion wird direkt ausgeführt
    """
    from app.api.schemas.rag import AIActionRequest, AIActionResult
    from app.services.rag.ai_action_service import get_ai_action_service

    action_service = get_ai_action_service()
    return await action_service.execute_action(db=db, user=current_user, request=request)


@router.post("/ai/actions/confirm")
async def confirm_ai_action(
    request: "AIActionConfirmRequest",
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> "AIActionResult":
    """Bestätigt oder lehnt eine vorgeschlagene AI-Aktion ab.

    Args:
        request.action_id: ID der vorgeschlagenen Aktion
        request.confirmed: True = ausführen, False = ablehnen
        request.modified_parameters: Optional geänderte Parameter
    """
    from app.api.schemas.rag import AIActionConfirmRequest, AIActionResult
    from app.services.rag.ai_action_service import get_ai_action_service

    action_service = get_ai_action_service()
    return await action_service.confirm_action(
        db=db,
        user=current_user,
        action_id=request.action_id,
        confirmed=request.confirmed,
        modified_parameters=request.modified_parameters,
    )


@router.get("/ai/context")
async def get_ai_context(
    page_type: str = Query(..., description="Aktueller Seitentyp (dashboard, documents, etc.)"),
    document_id: Optional[UUID] = Query(None, description="Aktuelle Dokument-ID"),
    entity_id: Optional[UUID] = Query(None, description="Aktuelle Entity-ID"),
    current_user: User = Depends(get_current_user),
) -> "AIContextInfo":
    """Gibt kontextspezifische Informationen für den AI-Assistenten zurück.

    Liefert:
    - Verfügbare Aktionen für den aktuellen Kontext
    - Vorgeschlagene Fragen/Befehle
    - Autonomie-Level des Benutzers
    """
    from app.api.schemas.rag import AIContextInfo
    from app.services.rag.ai_action_service import get_ai_action_service


    action_service = get_ai_action_service()
    return action_service.get_context_info(
        user=current_user,
        page_type=page_type,
        document_id=document_id,
        entity_id=entity_id,
    )
