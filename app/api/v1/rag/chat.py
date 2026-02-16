"""RAG Chat API Endpoints.

Chat-System mit RAG-Kontext:
- Session Management
- Kontext-aware Antworten
- Streaming Support
- Chat Historie
"""

import json
import secrets
import structlog
from typing import List, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

# SECURITY FIX 28-12: Rate Limiting für Chat Endpoints
from app.core.rate_limiting import limiter, get_user_identifier
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models import (
    User,
    RAGChatSession,
    RAGChatMessage,
    RAGChatRole,
    ChatSessionAccess,
    ChatSessionAccessLevel as DBChatSessionAccessLevel,
)
from app.db.models_chat_actions import ChatToolAction
from app.api.dependencies import get_current_user, get_db
from app.api.schemas.rag import (
    RAGChatRequest,
    RAGChatResponse,
    RAGChatSessionCreate,
    RAGChatSessionResponse,
    RAGChatSessionWithMessages,
    RAGChatMessageResponse,
    RAGContextType,
    RAGChunkSearchResult,
    AttachedDocumentInfo,
    ChatSessionShareRequest,
    ChatSessionCollaboratorResponse,
    ChatSessionSharedResponse,
    ChatSessionAccessLevel,
)
from app.services.chat_sharing_service import ChatSharingService, get_chat_sharing_service
from app.services.rag.llm_service import (
    get_llm_service,
    LLMService,
    LLMMessage,
    LLMContextType,
)
from app.services.rag.search_service import get_rag_search_service, RAGSearchService
from app.services.rag.prompt_templates import (
    build_rag_context,
    build_chat_prompt,
)
from app.services.rag.tool_registry import get_tool_registry
from app.services.rag.action_dispatcher import get_action_dispatcher
from app.core.config import settings
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["rag-chat"])


def get_llm_service_dep() -> LLMService:
    """Dependency für LLMService."""
    return get_llm_service()


def get_search_service_dep() -> RAGSearchService:
    """Dependency für RAGSearchService."""
    return get_rag_search_service()


# SECURITY FIX 28-12: Rate-Limit für Chat-Nachrichten (LLM-intensiv)
@limiter.limit("30/minute", key_func=get_user_identifier)
@router.post(
    "",
    response_model=RAGChatResponse,
    summary="Chat-Nachricht senden",
    description="Sendet eine Nachricht und erhaelt eine RAG-gestuetzte Antwort."
)
async def send_chat_message(
    request: Request,  # SECURITY FIX: Required for rate limiter
    body: RAGChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm_service: LLMService = Depends(get_llm_service_dep),
    search_service: RAGSearchService = Depends(get_search_service_dep)
) -> RAGChatResponse:
    """
    Sendet eine Chat-Nachricht und erhaelt eine Antwort.

    **Ablauf:**
    1. Relevante Chunks suchen (RAG)
    2. Kontext aus Chunks aufbauen
    3. LLM-Antwort generieren
    4. Nachricht und Antwort speichern

    **Kontext-Typen:**
    - `general`: Allgemeine Dokumenten-Fragen
    - `customer`: Kunden-bezogene Anfragen
    - `document`: Fragen zu spezifischem Dokument
    - `report`: Report-Generierung
    """
    start_time = datetime.now(timezone.utc)

    logger.info(
        "chat_message_request",
        user_id=str(current_user.id),
        session_id=str(body.session_id) if body.session_id else "new",
        context_type=body.context_type.value,
        realtime=body.realtime,
        message_length=len(body.message)
    )

    try:
        # 1. Session holen oder erstellen
        session = await _get_or_create_session(
            db=db,
            user_id=current_user.id,
            session_id=body.session_id,
            context_type=body.context_type,
            context_id=body.context_id
        )

        # 2. Chat-Historie laden
        history = await _get_chat_history(db, session.id)

        # 3. Relevante Chunks suchen
        document_ids = None
        if body.context_type == RAGContextType.DOCUMENT and body.context_id:
            try:
                document_ids = [UUID(body.context_id)]
            except ValueError as e:
                logger.debug("invalid_context_id_uuid_skipped", context_id=body.context_id, error_type=type(e).__name__)

        chunks = await search_service.search_for_context(
            db=db,
            query=body.message,
            context_chunks=settings.RAG_CHAT_CONTEXT_CHUNKS,
            document_ids=document_ids
        )

        # 4. RAG-Kontext aufbauen
        context = build_rag_context(chunks)

        # 5. Prompt erstellen
        messages = build_chat_prompt(
            question=body.message,
            context=context,
            history=history,
            realtime=body.realtime
        )

        # LLM Messages konvertieren
        llm_messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in messages
        ]

        # 6. LLM-Antwort generieren
        llm_context = LLMContextType.REALTIME if body.realtime else LLMContextType.GENERAL
        if body.context_type == RAGContextType.CUSTOMER:
            llm_context = LLMContextType.CUSTOMER

        response = await llm_service.generate(
            messages=llm_messages,
            context_type=llm_context,
            enable_thinking=not body.realtime  # Kein Thinking im Realtime-Modus
        )

        # 7. Nachrichten speichern
        # User-Nachricht (mit optionalem attached_document)
        user_message = RAGChatMessage(
            session_id=session.id,
            role=RAGChatRole.USER,
            content=body.message,
            attached_document_id=document_ids[0] if document_ids else None
        )
        db.add(user_message)

        # Assistant-Nachricht
        assistant_message = RAGChatMessage(
            session_id=session.id,
            role=RAGChatRole.ASSISTANT,
            content=response.content,
            thinking_content=response.thinking_content,
            model_used=response.model,
            tokens_input=response.tokens_input,
            tokens_output=response.tokens_output,
            generation_time_ms=response.generation_time_ms,
        )
        db.add(assistant_message)

        # Session aktualisieren
        session.message_count += 2
        session.last_message_at = datetime.now(timezone.utc)

        await db.commit()

        # 8. Response erstellen
        total_time = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

        sources = [
            RAGChunkSearchResult(
                chunk_id=UUID(c["chunk_id"]),
                document_id=UUID(c["document_id"]),
                chunk_text=c["text"][:500],  # Gekürzt
                chunk_index=0,
                page_number=c.get("page_number"),
                section_type=c.get("section_type"),
                similarity=c.get("similarity", 0),
                rerank_score=c.get("rerank_score")
            )
            for c in chunks
        ]

        return RAGChatResponse(
            session_id=session.id,
            message=response.content,
            thinking_content=response.thinking_content,
            sources=sources,
            model_used=response.model,
            generation_time_ms=total_time
        )

    except Exception as e:
        # SECURITY FIX 28-24: Generische Fehlermeldung
        logger.exception(
            "chat_message_failed",
            user_id=str(current_user.id),
            **safe_error_log(e)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Chat fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


# SECURITY FIX 28-12: Rate-Limit für Streaming-Chat (LLM-intensiv)
@limiter.limit("20/minute", key_func=get_user_identifier)
@router.post(
    "/stream",
    summary="Chat mit Streaming",
    description="Sendet eine Nachricht und streamt die Antwort via SSE."
)
async def send_chat_message_stream(
    request: Request,  # SECURITY FIX: Required for rate limiter
    body: RAGChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm_service: LLMService = Depends(get_llm_service_dep),
    search_service: RAGSearchService = Depends(get_search_service_dep)
) -> StreamingResponse:
    """
    Chat mit Dokumenten-Kontext (Streaming).

    Verwendet SSE (Server-Sent Events) für Echtzeit-Streaming der Antwort.

    Event-Typen:
    - chunk: Text-Chunk der Antwort
    - source: Quellen-Referenz
    - thinking: Denk-Prozess (optional)
    - done: Abschluss mit Session-ID
    - error: Fehler-Meldung
    """

    async def generate_stream():
        """Generator für SSE-Events."""
        try:
            # 1. Relevante Chunks finden
            document_ids = None
            logger.debug(
                "rag_chat_context_check",
                context_type=body.context_type.value if body.context_type else None,
                context_id=body.context_id,
            )
            if body.context_type == RAGContextType.DOCUMENT and body.context_id:
                try:
                    document_ids = [UUID(body.context_id)]
                    logger.info(
                        "document_context_set",
                        context_id=body.context_id,
                        document_ids=str(document_ids)
                    )
                except ValueError:
                    logger.warning("invalid_context_id", context_id=body.context_id)

            chunks = await search_service.search_for_context(
                db=db,
                query=body.message,
                context_chunks=settings.RAG_CHAT_CONTEXT_CHUNKS,
                document_ids=document_ids
            )

            # Debug-Logging: Wurden Chunks gefunden?
            logger.info(
                "rag_chat_search_result",
                query=body.message[:50],
                chunks_found=len(chunks),
                has_context=bool(chunks),
                document_filter=str(document_ids) if document_ids else "none"
            )

            # 2. Kontext aufbauen
            context_parts = []
            for c in chunks:
                page_info = f", Seite {c.get('page_number')}" if c.get('page_number') else ""
                context_parts.append(f"[Quelle: Dokument {c['document_id']}{page_info}]\n{c['text']}")
            context = "\n\n---\n\n".join(context_parts)

            # Fallback wenn keine Chunks gefunden
            fallback_used = False
            fallback_doc_name = None
            if not context and document_ids:
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
                    # Fallback: Dokument aus MinIO laden und schnell Text extrahieren
                    if doc and doc.file_path:
                        try:
                            from app.services.storage_service import get_storage_service
                            from app.services.ocr import quick_ocr_preview

                            import tempfile
                            from pathlib import Path as FilePath

                            storage = get_storage_service()
                            file_bytes = await storage.download_document(doc.file_path)

                            # Temporaere Datei für Text-Extraktion
                            suffix = FilePath(doc.original_filename).suffix or ".pdf"
                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                                tmp.write(file_bytes)
                                tmp_path = FilePath(tmp.name)

                            try:
                                # Schnelle Text-Extraktion (PyMuPDF für embedded text)
                                preview_text = await quick_ocr_preview(
                                    tmp_path,
                                    max_pages=10,
                                    max_chars=15000
                                )

                                if preview_text and len(preview_text.strip()) > 50:
                                    context = preview_text
                                    fallback_used = True
                                    fallback_doc_name = doc.original_filename
                                    logger.info(
                                        "chat_fallback_quick_ocr",
                                        document_id=str(doc.id),
                                        document_name=doc.original_filename,
                                        text_length=len(preview_text),
                                    )
                                else:
                                    context = "HINWEIS: Das Dokument wurde noch nicht verarbeitet und enthält keinen extrahierbaren Text. Bitte warten Sie einen Moment."
                                    logger.warning("chat_fallback_quick_ocr_empty", document_id=str(doc.id))
                            finally:
                                # Cleanup temp file
                                tmp_path.unlink(missing_ok=True)

                        except Exception as e:
                            logger.warning("chat_fallback_quick_ocr_failed", document_id=str(doc.id), **safe_error_log(e))
                            context = "HINWEIS: Das Dokument konnte nicht gelesen werden. Bitte warten Sie bis die Verarbeitung abgeschlossen ist."
                    else:
                        context = "HINWEIS: Das Dokument wurde noch nicht verarbeitet. Bitte warten Sie einen Moment und versuchen Sie es erneut."
                        logger.warning(
                            "chat_fallback_no_text",
                            document_id=str(document_ids[0]) if document_ids else "none",
                            has_doc=doc is not None,
                            has_text=doc.extracted_text is not None if doc else False,
                        )
            elif not context:
                context = "HINWEIS: Es wurden keine relevanten Dokumente zu dieser Anfrage gefunden. Der Benutzer fragt möglicherweise nach Dokumenten, die noch nicht indexiert wurden, oder die Suchanfrage ist zu allgemein."
                logger.warning(
                    "rag_chat_no_context",
                    query=body.message[:50],
                    document_filter=str(document_ids) if document_ids else "none"
                )

            # 3. Chat Session verwalten
            if body.session_id:
                result = await db.execute(
                    select(RAGChatSession).where(
                        RAGChatSession.id == body.session_id,
                        RAGChatSession.user_id == current_user.id
                    )
                )
                session = result.scalar_one_or_none()
                if not session:
                    yield f"data: {json.dumps({'type': 'error', 'error': 'Session nicht gefunden'})}\n\n"
                    return
                session_is_new = False
            else:
                session = RAGChatSession(
                    user_id=current_user.id,
                    session_token=secrets.token_urlsafe(32),
                    context_type=body.context_type.value if body.context_type else None,
                    context_id=body.context_id,
                    status="active",
                )
                db.add(session)
                await db.flush()
                session_is_new = True

            # 4. User Message speichern (mit optionalem attached_document)
            user_message = RAGChatMessage(
                session_id=session.id,
                role=RAGChatRole.USER,
                content=body.message,
                attached_document_id=document_ids[0] if document_ids else None,
            )
            db.add(user_message)

            # 5. Quellen senden
            logger.info(
                "rag_chat_sending_sources",
                source_count=len(chunks)
            )
            for c in chunks:
                source_event = {
                    "type": "source",
                    "source": {
                        "chunk_id": str(c["chunk_id"]),
                        "document_id": str(c["document_id"]),
                        "chunk_text": c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
                        "chunk_index": c.get("chunk_index", 0),
                        "page_number": c.get("page_number"),
                        "section_type": c.get("section_type"),
                        "similarity": c.get("similarity", 0.0),
                        "rerank_score": c.get("rerank_score"),
                    }
                }
                yield f"data: {json.dumps(source_event)}\n\n"

            # 6. LLM Context
            llm_context = LLMContextType.REALTIME if body.realtime else LLMContextType.GENERAL
            if body.context_type == RAGContextType.CUSTOMER:
                llm_context = LLMContextType.CUSTOMER

            # 7. LLM Streaming - System-Prompt je nach Modus
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

            messages = [
                LLMMessage(role="system", content=system_content),
                LLMMessage(role="user", content=body.message),
            ]

            full_response = ""
            async for chunk in llm_service.generate_stream(
                messages=messages,
                context_type=llm_context,
            ):
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"

            # 8. Check for tool calls in response
            tool_registry = get_tool_registry()
            tool_call = tool_registry.parse_tool_call(full_response)

            if tool_call:
                logger.info(
                    "tool_call_detected_in_chat",
                    tool_name=tool_call.tool_name,
                    session_id=str(session.id)
                )

                # Get tool definition
                tool_def = tool_registry.get_tool(tool_call.tool_name)

                if tool_def:
                    # Dispatch tool call
                    dispatcher = get_action_dispatcher()

                    # Extract context_id if document_id in params
                    context_id = None
                    if "document_id" in tool_call.parameters:
                        try:
                            context_id = UUID(tool_call.parameters["document_id"])
                        except (ValueError, TypeError):
                            pass

                    action_result = await dispatcher.dispatch(
                        tool_call=tool_call,
                        user=current_user,
                        db=db,
                        context_id=context_id
                    )

                    # Store action in DB
                    chat_action = ChatToolAction(
                        session_id=session.id,
                        message_id=None,  # Will be set after assistant_message is created
                        tool_name=tool_call.tool_name,
                        parameters=tool_call.parameters,
                        status="pending_confirmation" if tool_def.requires_confirmation else "executed",
                        result=action_result.details if action_result.status.value == "completed" else None,
                        error_message=action_result.message if action_result.status.value == "failed" else None,
                        requires_confirmation=tool_def.requires_confirmation,
                        executed_at=datetime.now(timezone.utc) if not tool_def.requires_confirmation else None
                    )
                    db.add(chat_action)
                    await db.flush()  # Get ID

                    # Send action SSE event
                    action_event = {
                        "type": "action",
                        "action": {
                            "id": str(chat_action.id),
                            "tool_name": tool_call.tool_name,
                            "status": chat_action.status,
                            "requires_confirmation": tool_def.requires_confirmation,
                            "result": action_result.message
                        }
                    }
                    yield f"data: {json.dumps(action_event)}\n\n"

            # 9. Assistant Message speichern
            assistant_message = RAGChatMessage(
                session_id=session.id,
                role=RAGChatRole.ASSISTANT,
                content=full_response,
            )
            db.add(assistant_message)
            await db.flush()  # Get message ID

            # Link action to message if exists
            if tool_call:
                chat_action.message_id = assistant_message.id

            # 10. Session aktualisieren
            session.message_count = (session.message_count or 0) + 2
            session.last_message_at = datetime.now(timezone.utc)

            # 11. Titel generieren wenn neue Session
            if session_is_new and not session.title:
                try:
                    generated_title = await _generate_chat_title(
                        llm_service=llm_service,
                        user_message=body.message
                    )
                    session.title = generated_title
                    logger.info(
                        "chat_title_auto_generated",
                        session_id=str(session.id),
                        title=generated_title
                    )
                except Exception as e:
                    logger.warning("chat_title_generation_skipped", **safe_error_log(e))

            await db.commit()

            # 12. Done Event
            yield f"data: {json.dumps({'type': 'done', 'session_id': str(session.id), 'message_id': str(assistant_message.id)})}\n\n"

            logger.info(
                "rag_chat_stream_completed",
                user_id=str(current_user.id),
                session_id=str(session.id),
                context_chunks=len(chunks),
                response_length=len(full_response),
            )

        except Exception as e:
            logger.error("rag_chat_stream_failed", **safe_error_log(e))
            yield f"data: {json.dumps({'type': 'error', 'error': safe_error_detail(e, 'Chat')})}\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


# SECURITY FIX 28-12: Rate-Limit für Session-Erstellung
@limiter.limit("30/minute", key_func=get_user_identifier)
@router.post(
    "/sessions",
    response_model=RAGChatSessionResponse,
    summary="Neue Chat-Session erstellen",
    description="Erstellt eine neue Chat-Session."
)
async def create_chat_session(
    request: Request,  # SECURITY FIX: Required for rate limiter
    body: RAGChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RAGChatSessionResponse:
    """
    Erstellt eine neue Chat-Session.

    Sessions organisieren zusammengehoerige Chat-Nachrichten.
    """
    session = RAGChatSession(
        user_id=current_user.id,
        session_token=str(uuid4()),
        title=body.title,
        context_type=body.context_type.value if body.context_type else None,
        context_id=body.context_id,
        status="active"
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info(
        "chat_session_created",
        user_id=str(current_user.id),
        session_id=str(session.id)
    )

    return RAGChatSessionResponse(
        id=session.id,
        user_id=session.user_id,
        session_token=session.session_token,
        title=session.title,
        context_type=session.context_type,
        context_id=session.context_id,
        status=session.status,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at
    )


@router.get(
    "/sessions",
    response_model=List[RAGChatSessionResponse],
    summary="Chat-Sessions auflisten",
    description="Listet alle Chat-Sessions des Benutzers auf."
)
async def list_chat_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[RAGChatSessionResponse]:
    """
    Listet Chat-Sessions des aktuellen Benutzers.

    Sortiert nach letzter Aktivitaet.
    """
    result = await db.execute(
        select(RAGChatSession)
        .where(RAGChatSession.user_id == current_user.id)
        .order_by(RAGChatSession.last_message_at.desc().nullsfirst())
        .offset(offset)
        .limit(limit)
    )
    sessions = result.scalars().all()

    return [
        RAGChatSessionResponse(
            id=s.id,
            user_id=s.user_id,
            session_token=s.session_token,
            title=s.title,
            context_type=s.context_type,
            context_id=s.context_id,
            status=s.status,
            message_count=s.message_count,
            created_at=s.created_at,
            updated_at=s.updated_at,
            last_message_at=s.last_message_at
        )
        for s in sessions
    ]


# WICHTIG: Diese Route MUSS vor /sessions/{session_id} stehen,
# sonst wird "shared" als session_id interpretiert (422 Fehler)
@router.get(
    "/sessions/shared",
    response_model=List[ChatSessionSharedResponse],
    summary="Mit mir geteilte Sessions",
    description="Listet alle Chat-Sessions auf, die mit dem aktuellen Benutzer geteilt wurden."
)
async def get_shared_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[ChatSessionSharedResponse]:
    """
    Ruft alle Sessions ab, die mit dem aktuellen Benutzer geteilt wurden.
    """
    sharing_service = get_chat_sharing_service(db)
    sessions = await sharing_service.get_shared_sessions(current_user.id)

    result = []
    for session in sessions:
        # Access Level holen
        access_level = await sharing_service.get_access_level(session.id, current_user.id)

        # Collaborator Count
        collaborators = await sharing_service.get_collaborators(session.id, current_user.id)

        result.append(ChatSessionSharedResponse(
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
            access_level=access_level or "view",
            is_shared=True,
            collaborator_count=len(collaborators)
        ))

    return result


@router.get(
    "/sessions/{session_id}",
    response_model=RAGChatSessionWithMessages,
    summary="Chat-Session mit Verlauf abrufen",
    description="Gibt eine Session mit allen Nachrichten zurück."
)
async def get_chat_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RAGChatSessionWithMessages:
    """
    Ruft eine Chat-Session mit vollständigem Verlauf ab.

    Unterstützt sowohl eigene als auch geteilte Sessions.
    """
    # Session laden (ohne User-Filter, Zugriff wird separat geprüft)
    session = await db.get(RAGChatSession, session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden"
        )

    # Zugriffsprüfung: Owner oder Shared Access
    if session.user_id != current_user.id:
        sharing_service = get_chat_sharing_service(db)
        has_access = await sharing_service.check_access(
            session_id=session_id,
            user_id=current_user.id,
            required_level=DBChatSessionAccessLevel.VIEW
        )
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session nicht gefunden"
            )

    # Nachrichten laden (mit attached_document eager loading)
    messages_result = await db.execute(
        select(RAGChatMessage)
        .where(RAGChatMessage.session_id == session_id)
        .options(selectinload(RAGChatMessage.attached_document))
        .order_by(RAGChatMessage.created_at)
    )
    messages = messages_result.scalars().all()

    return RAGChatSessionWithMessages(
        id=session.id,
        user_id=session.user_id,
        session_token=session.session_token,
        title=session.title,
        context_type=session.context_type,
        context_id=session.context_id,
        status=session.status,
        message_count=session.message_count,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_message_at=session.last_message_at,
        messages=[
            RAGChatMessageResponse(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                thinking_content=m.thinking_content,
                confidence_score=m.confidence_score,
                model_used=m.model_used,
                tokens_input=m.tokens_input,
                tokens_output=m.tokens_output,
                generation_time_ms=m.generation_time_ms,
                created_at=m.created_at,
                attached_document=AttachedDocumentInfo(
                    id=m.attached_document.id,
                    name=m.attached_document.original_filename
                ) if m.attached_document else None
            )
            for m in messages
        ]
    )


# SECURITY FIX 28-12: Rate-Limit für Session-Updates
@limiter.limit("60/minute", key_func=get_user_identifier)
@router.put(
    "/sessions/{session_id}",
    response_model=RAGChatSessionResponse,
    summary="Chat-Session aktualisieren",
    description="Aktualisiert eine Chat-Session (z.B. Titel)."
)
async def update_chat_session(
    request: Request,  # SECURITY FIX 28-12: Required for rate limiter
    session_id: UUID,
    title: str = Query(..., max_length=255, description="Neuer Titel der Session"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> RAGChatSessionResponse:
    """
    Aktualisiert eine Chat-Session.

    Ermöglicht das Setzen eines benutzerdefinierten Titels.
    """
    result = await db.execute(
        select(RAGChatSession).where(
            RAGChatSession.id == session_id,
            RAGChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden"
        )

    session.title = title
    await db.commit()
    await db.refresh(session)

    logger.info(
        "chat_session_title_updated",
        user_id=str(current_user.id),
        session_id=str(session_id),
        new_title=title
    )

    return RAGChatSessionResponse(
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
    )


# SECURITY FIX 28-12: Rate-Limit für Session-Löschung
@limiter.limit("30/minute", key_func=get_user_identifier)
@router.delete(
    "/sessions/{session_id}",
    summary="Chat-Session löschen",
    description="Löscht eine Chat-Session und alle Nachrichten."
)
async def delete_chat_session(
    request: Request,  # SECURITY FIX 28-12: Required for rate limiter
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Löscht eine Chat-Session.

    Alle zugehoerigen Nachrichten werden ebenfalls gelöscht.
    """
    # Session prüfen
    result = await db.execute(
        select(RAGChatSession).where(
            RAGChatSession.id == session_id,
            RAGChatSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session nicht gefunden"
        )

    # Nachrichten löschen
    await db.execute(
        RAGChatMessage.__table__.delete().where(
            RAGChatMessage.session_id == session_id
        )
    )

    # Session löschen
    await db.delete(session)
    await db.commit()

    logger.info(
        "chat_session_deleted",
        user_id=str(current_user.id),
        session_id=str(session_id)
    )

    return {
        "success": True,
        "session_id": str(session_id),
        "message": "Session gelöscht"
    }


# =============================================================================
# Helper Functions
# =============================================================================

async def _generate_chat_title(
    llm_service: LLMService,
    user_message: str
) -> str:
    """
    Generiert einen kurzen Chat-Titel aus der ersten User-Nachricht.

    Nutzt das lokale LLM für intelligente Titel-Generierung.
    Fallback auf erste 50 Zeichen bei Fehlern.

    Args:
        llm_service: LLM Service Instanz
        user_message: Die erste Nachricht des Users

    Returns:
        Kurzer Titel (max 50 Zeichen)
    """
    try:
        # Thematischer Prompt für bessere Titel wie bei Claude Desktop
        prompt = f"""Du bist ein Titel-Generator für Chat-Konversationen.

Erstelle einen prägnanten, thematischen Titel der:
- Das Kernthema in 3-6 Wörtern zusammenfasst
- Auf Deutsch ist
- Wie eine professionelle Überschrift klingt
- Das Ziel/die Absicht des Users erfasst

Beispiele guter Titel:
- "Rechnungsdetails von Alpac prüfen"
- "OCR-Optimierung für Dokumente"
- "Vertragsanalyse Lieferanten"
- "Zahlungsstatus offene Rechnungen"

Nachricht: {user_message[:300]}

Titel (NUR der Titel, ohne Anführungszeichen):"""

        messages = [
            LLMMessage(role="user", content=prompt)
        ]

        # Generierung mit ausreichend Tokens für thematische Titel
        title = ""
        async for chunk in llm_service.generate_stream(
            messages=messages,
            context_type=LLMContextType.GENERAL,
            max_tokens=50,
        ):
            title += chunk

        # Bereinigen
        title = title.strip().strip('"').strip("'").strip()

        # Auf 50 Zeichen begrenzen
        if len(title) > 50:
            title = title[:47] + "..."

        # Fallback wenn leer
        if not title:
            title = user_message[:50].strip()
            if len(user_message) > 50:
                title = title.rsplit(' ', 1)[0] + "..."

        return title

    except Exception as e:
        logger.warning("chat_title_generation_failed", **safe_error_log(e))
        # Fallback: Erste 50 Zeichen der Nachricht
        title = user_message[:50].strip()
        if len(user_message) > 50:
            title = title.rsplit(' ', 1)[0] + "..."
        return title


async def _get_or_create_session(
    db: AsyncSession,
    user_id: UUID,
    session_id: Optional[UUID],
    context_type: RAGContextType,
    context_id: Optional[str]
) -> RAGChatSession:
    """Holt oder erstellt eine Chat-Session."""
    if session_id:
        result = await db.execute(
            select(RAGChatSession).where(
                RAGChatSession.id == session_id,
                RAGChatSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    # Neue Session erstellen
    session = RAGChatSession(
        user_id=user_id,
        session_token=str(uuid4()),
        context_type=context_type.value,
        context_id=context_id,
        status="active"
    )
    db.add(session)
    await db.flush()

    return session


async def _get_chat_history(
    db: AsyncSession,
    session_id: UUID,
    max_messages: int = None
) -> List[dict]:
    """Laedt Chat-Historie für Kontext."""
    max_messages = max_messages or settings.RAG_CHAT_MAX_HISTORY

    result = await db.execute(
        select(RAGChatMessage)
        .where(RAGChatMessage.session_id == session_id)
        .order_by(RAGChatMessage.created_at.desc())
        .limit(max_messages)
    )
    messages = result.scalars().all()

    # Umkehren für chronologische Reihenfolge
    return [
        {"role": m.role.value, "content": m.content}
        for m in reversed(messages)
    ]


# =============================================================================
# TOOL ACTION CONFIRMATION ENDPOINTS
# =============================================================================

# SECURITY FIX 28-12: Rate-Limit für Action-Bestätigung
@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/actions/{action_id}/confirm",
    summary="Tool-Aktion bestätigen",
    description="Bestätigt eine ausstehende Tool-Aktion aus dem Chat."
)
async def confirm_chat_action(
    request: Request,  # SECURITY FIX: Required for rate limiter
    action_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Bestätigt eine ausstehende Tool-Aktion.

    Für Aktionen die requires_confirmation=True haben.
    """
    try:
        # Action laden
        result = await db.execute(
            select(ChatToolAction)
            .join(RAGChatSession, ChatToolAction.session_id == RAGChatSession.id)
            .where(
                ChatToolAction.id == action_id,
                ChatToolAction.status == "pending_confirmation",
                RAGChatSession.user_id == current_user.id
            )
        )
        action = result.scalar_one_or_none()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aktion nicht gefunden oder bereits verarbeitet"
            )

        # Action Dispatcher verwenden
        dispatcher = get_action_dispatcher()
        action_result = await dispatcher.confirm_action(
            action_id=action_id,
            user=current_user,
            db=db
        )

        # Action-Status aktualisieren
        if action_result.status.value == "completed":
            action.status = "executed"
            action.result = action_result.details
            action.executed_at = datetime.now(timezone.utc)
            action.confirmed_by_id = current_user.id
        elif action_result.status.value == "failed":
            action.status = "failed"
            action.error_message = action_result.message

        await db.commit()

        logger.info(
            "chat_action_confirmed",
            action_id=str(action_id),
            user_id=str(current_user.id),
            status=action.status
        )

        return {
            "success": True,
            "action_id": str(action_id),
            "status": action.status,
            "result": action.result,
            "message": action_result.message
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_action_confirm_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bestätigung fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


# SECURITY FIX 28-12: Rate-Limit für Action-Ablehnung
@limiter.limit("60/minute", key_func=get_user_identifier)
@router.post(
    "/actions/{action_id}/reject",
    summary="Tool-Aktion ablehnen",
    description="Lehnt eine ausstehende Tool-Aktion aus dem Chat ab."
)
async def reject_chat_action(
    request: Request,  # SECURITY FIX: Required for rate limiter
    action_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Lehnt eine ausstehende Tool-Aktion ab.

    Für Aktionen die requires_confirmation=True haben.
    """
    try:
        # Action laden
        result = await db.execute(
            select(ChatToolAction)
            .join(RAGChatSession, ChatToolAction.session_id == RAGChatSession.id)
            .where(
                ChatToolAction.id == action_id,
                ChatToolAction.status == "pending_confirmation",
                RAGChatSession.user_id == current_user.id
            )
        )
        action = result.scalar_one_or_none()

        if not action:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Aktion nicht gefunden oder bereits verarbeitet"
            )

        # Action Dispatcher verwenden
        dispatcher = get_action_dispatcher()
        action_result = await dispatcher.reject_action(
            action_id=action_id,
            user=current_user,
            db=db
        )

        # Action-Status aktualisieren
        action.status = "rejected"
        action.confirmed_by_id = current_user.id

        await db.commit()

        logger.info(
            "chat_action_rejected",
            action_id=str(action_id),
            user_id=str(current_user.id)
        )

        return {
            "success": True,
            "action_id": str(action_id),
            "status": "rejected",
            "message": "Aktion wurde abgelehnt"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_action_reject_failed", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ablehnung fehlgeschlagen. Bitte versuchen Sie es erneut."
        )


# =============================================================================
# SHARING ENDPOINTS
# =============================================================================
# HINWEIS: /sessions/shared wurde nach oben verschoben (vor /sessions/{session_id})
# um korrekte Route-Priorisierung zu gewährleisten

# SECURITY FIX 28-12: Rate-Limit für Session-Sharing
@limiter.limit("20/minute", key_func=get_user_identifier)
@router.post(
    "/sessions/{session_id}/share",
    response_model=ChatSessionCollaboratorResponse,
    summary="Session teilen",
    description="Teilt eine Chat-Session mit einem anderen Benutzer."
)
async def share_chat_session(
    request: Request,  # SECURITY FIX: Required for rate limiter
    session_id: UUID,
    body: ChatSessionShareRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> ChatSessionCollaboratorResponse:
    """
    Teilt eine Chat-Session mit einem anderen Benutzer.

    Erfordert MANAGE-Berechtigung oder Ownership.
    """
    sharing_service = get_chat_sharing_service(db)

    try:
        # Access Level konvertieren
        db_level = DBChatSessionAccessLevel(body.access_level.value)

        access = await sharing_service.share_session(
            session_id=session_id,
            owner_id=current_user.id,
            target_user_id=body.user_id,
            access_level=db_level
        )
        await db.commit()

        # User-Info holen
        user = await db.get(User, body.user_id)

        return ChatSessionCollaboratorResponse(
            user_id=str(access.user_id),
            username=user.username if user else "Unbekannt",
            email=user.email if user else None,
            access_level=access.access_level,
            is_owner=False,
            granted_at=str(access.granted_at) if access.granted_at else None
        )

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("chat_session_validation_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen."
        )


# SECURITY FIX 28-12: Rate-Limit für Zugriffsentzug
@limiter.limit("20/minute", key_func=get_user_identifier)
@router.delete(
    "/sessions/{session_id}/share/{user_id}",
    summary="Zugriff entziehen",
    description="Entzieht einem Benutzer den Zugriff auf eine Chat-Session."
)
async def revoke_chat_session_access(
    request: Request,  # SECURITY FIX 28-12: Required for rate limiter
    session_id: UUID,
    user_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Entzieht einem Benutzer den Zugriff auf eine Chat-Session.

    Erfordert MANAGE-Berechtigung oder Ownership.
    """
    sharing_service = get_chat_sharing_service(db)

    try:
        revoked = await sharing_service.revoke_access(
            session_id=session_id,
            owner_id=current_user.id,
            target_user_id=user_id
        )
        await db.commit()

        if not revoked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Zugriff nicht gefunden"
            )

        return {
            "success": True,
            "session_id": str(session_id),
            "user_id": str(user_id),
            "message": "Zugriff entzogen"
        }

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("chat_session_validation_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen."
        )


@router.get(
    "/sessions/{session_id}/collaborators",
    response_model=List[ChatSessionCollaboratorResponse],
    summary="Collaborators auflisten",
    description="Listet alle Benutzer auf, die Zugriff auf eine Chat-Session haben."
)
async def get_chat_session_collaborators(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[ChatSessionCollaboratorResponse]:
    """
    Listet alle Collaborators einer Chat-Session auf.

    Erfordert mindestens VIEW-Berechtigung.
    """
    sharing_service = get_chat_sharing_service(db)

    try:
        collaborators = await sharing_service.get_collaborators(
            session_id=session_id,
            user_id=current_user.id
        )

        return [
            ChatSessionCollaboratorResponse(**c)
            for c in collaborators
        ]

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("chat_session_validation_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen."
        )
