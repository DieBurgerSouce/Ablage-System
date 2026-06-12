"""RAG Legacy-Endpoints (aus dem frueheren app/api/v1/rag.py uebernommen).

BUGFIX (2026-06-12, B6 Modul-Shadowing): Das Package ``app/api/v1/rag/``
shadowte das Modul ``app/api/v1/rag.py`` - dessen Routen waren dadurch NIE
registriert (Frontend bekam Dauer-404 auf /rag/ai/*, /rag/bi/* etc.).

Hier leben NUR die Endpoint-Gruppen, die im Package KEIN Pendant haben:
- /customer-cards  (Package hat /customers mit anderem Pfad-Schema)
- /models          (LLM-Modelle)
- /health          (RAG Service Health, Admin-only)
- /bi/*            (Business Intelligence)
- /ai/*            (AI Assistant Actions + Kontext)

Die in rag.py zusaetzlich enthaltenen search/chat/chunks/jobs-Endpoints waren
Duplikate der (neueren, gepflegten) Package-Implementierungen und wurden
bewusst NICHT uebernommen.
"""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_current_superuser, get_current_user
from app.api.schemas.rag import (
    # Customer Cards
    RAGCustomerCardResponse,
    RAGCustomerCardSummary,
    # LLM Models
    RAGLLMModelResponse,
    # Search Result (fuer BI-Chat Quellen)
    RAGChunkSearchResult,
    # Business Intelligence
    BIChatRequest,
    BIChatResponse,
    BIQueryRequest,
    BIQueryResponse,
    BIQueryType,
    BITimeRange,
    # AI Assistant Actions
    AIActionConfirmRequest,
    AIActionListResponse,
    AIActionRequest,
    AIActionResult,
    AIContextInfo,
)
from app.core.config import settings
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import (
    Company,
    RAGChatMessage,
    RAGChatSession,
    RAGCustomerCard,
    RAGLLMModel,
    User,
)
from app.db.session import get_async_session
# S.3-S.5 SECURITY FIX: Company Context fuer Multi-Tenancy IDOR Protection
from app.middleware.company_context import require_company
from app.services.rag import (
    LLMContextType,
    LLMMessage,
    get_customer_card_service,
    get_llm_service,
    get_rag_search_service,
)

logger = structlog.get_logger(__name__)

# Kein eigener Prefix - der Parent-Router (router.py) ergaenzt "/rag".
router = APIRouter(tags=["rag"])


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
    # S.4 SECURITY FIX: Company Context fuer Multi-Tenancy IDOR Protection
    company_ctx: Company = Depends(require_company),
) -> List[RAGCustomerCardSummary]:
    """Listet Customer Cards auf, optional mit Suche.

    SECURITY: Nur Customer Cards der eigenen Company werden zurueckgegeben.
    """
    # BUGFIX (2026-06-12): require_company liefert das Company-Objekt selbst,
    # also company_ctx.id (das fruehere company_ctx.company_id existierte nicht).
    query = select(RAGCustomerCard).where(
        RAGCustomerCard.company_id == company_ctx.id
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
    # S.3 SECURITY FIX: Company Context fuer Multi-Tenancy IDOR Protection
    company_ctx: Company = Depends(require_company),
) -> RAGCustomerCardResponse:
    """Laedt eine einzelne Customer Card.

    SECURITY: Nur Customer Cards der eigenen Company koennen geladen werden.
    """
    query = select(RAGCustomerCard).where(
        RAGCustomerCard.customer_id == customer_id,
        RAGCustomerCard.company_id == company_ctx.id,
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
    # S.5 SECURITY FIX: Company Context fuer Multi-Tenancy IDOR Protection
    company_ctx: Company = Depends(require_company),
) -> dict:
    """Aktualisiert eine Customer Card asynchron.

    SECURITY: Nur Customer Cards der eigenen Company koennen aktualisiert werden.
    """
    card_service = get_customer_card_service()

    query = select(RAGCustomerCard).where(
        RAGCustomerCard.customer_id == customer_id,
        RAGCustomerCard.company_id == company_ctx.id,
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
# LLM MODELS ENDPOINTS
# ============================================================================

@router.get("/models", response_model=List[RAGLLMModelResponse])
async def list_llm_models(
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> List[RAGLLMModelResponse]:
    """Listet verfuegbare LLM-Modelle auf."""
    query = select(RAGLLMModel)
    if active_only:
        query = query.where(RAGLLMModel.is_active == True)  # noqa: E712
    query = query.order_by(RAGLLMModel.priority.desc())

    result = await db.execute(query)
    models = result.scalars().all()

    return [RAGLLMModelResponse.model_validate(m) for m in models]


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def rag_health_check(
    current_user: User = Depends(get_current_superuser),  # AA.1 SECURITY FIX: Admin required
    db: AsyncSession = Depends(get_async_session),
) -> dict:
    """Health Check fuer RAG Services.

    **REQUIRES ADMIN AUTHENTICATION**
    """
    health = {
        "status": "healthy",
        "components": {},
    }

    # Database Check
    try:
        await db.execute(text("SELECT 1"))
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
    request: BIQueryRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """Fuehrt eine Business Intelligence Abfrage durch.

    Unterstuetzt natuerlichsprachige Anfragen wie:
    - "Finde alle Rechnungen von Mueller GmbH aus Q3"
    - "Wie haben sich die Marketing-Ausgaben entwickelt?"
    - "Wann zahlt Kunde X?"
    - "Zeige offene Posten"
    """
    from app.services.business_intelligence_service import get_bi_service

    bi_service = get_bi_service()

    try:
        result = await bi_service.process_query(
            db=db,
            user_id=current_user.id,
            company_id=company.id,
            query=request.query,
        )

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
    time_range: Optional[str] = Query("this_year", description="Zeitraum fuer Analyse"),
    entity_id: Optional[UUID] = Query(None, description="Filter auf Entitaet"),
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """Analysiert Rechnungen mit Aggregationen."""
    from app.services.business_intelligence_service import TimeRange, get_bi_service

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
    """Holt Statistiken fuer eine spezifische Geschaeftsentitaet."""
    from app.services.business_intelligence_service import get_bi_service

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
    """Sucht Entitaet nach Name und liefert Statistiken.

    Unterstuetzt Teilsuche (z.B. "Mueller" findet "Mueller GmbH").
    """
    from app.services.business_intelligence_service import get_bi_service

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
    """Prognostiziert Zahlungsverhalten einer Entitaet."""
    from app.services.business_intelligence_service import get_bi_service

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
    """Analysiert Trends fuer eine gegebene Metrik."""
    from app.services.business_intelligence_service import TimeRange, get_bi_service

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
    request: BIChatRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
    company: Company = Depends(require_company),
):
    """Chat mit kombiniertem RAG- und Business Intelligence-Kontext.

    1. Erkennt ob die Anfrage eine BI-Frage ist
    2. Fuehrt ggf. BI-Analyse durch
    3. Kombiniert BI-Ergebnisse mit RAG-Dokumentkontext
    4. Generiert eine umfassende Antwort
    """
    import secrets
    from app.services.business_intelligence_service import QueryType, get_bi_service

    search_service = get_rag_search_service()
    llm_service = get_llm_service()
    bi_service = get_bi_service()

    bi_insights = None
    bi_context = ""

    try:
        # 1. BI-Analyse wenn aktiviert
        if request.enable_bi:
            query_type = bi_service.detect_query_type(request.message)

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

                bi_context = f"""
BUSINESS INTELLIGENCE ERGEBNISSE:
{bi_result.summary}

STRUKTURIERTE DATEN:
{bi_result.data}
"""

        # 2. RAG-Suche durchfuehren
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
        system_content = f"""Du bist ein intelligenter Geschaeftsassistent fuer ein Dokumentenmanagementsystem.
Du hast Zugriff auf:
1. Strukturierte Geschaeftsdaten (Rechnungen, Kunden, Statistiken)
2. Dokumenteninhalte (Vertraege, Korrespondenz, etc.)

Beantworte Fragen praezise und hilfreich.
Nutze die verfuegbaren Daten um fundierte Antworten zu geben.
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
) -> AIActionListResponse:
    """Listet verfuegbare AI-Aktionen basierend auf Benutzerrolle auf.

    Autonomie-Level:
    - Viewer: Nur Lese-Aktionen (Suche, Analyse, Berichte)
    - Editor: Supervised Actions (Vorschlag + Bestaetigung erforderlich)
    - Admin: Autonome Aktionen (selbststaendig ausfuehrbar)
    """
    from app.services.rag.ai_action_service import get_ai_action_service

    action_service = get_ai_action_service()
    return action_service.get_available_actions(user=current_user, context_type=context_type)


@router.post("/ai/actions/execute")
async def execute_ai_action(
    request: AIActionRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> AIActionResult:
    """Fuehrt eine AI-Aktion aus.

    Bei Aktionen die Bestaetigung erfordern (Editor-Level):
    - Status wird auf 'suggested' gesetzt
    - User muss ueber /ai/actions/confirm bestaetigen

    Bei Admin-Level oder auto_execute=True:
    - Aktion wird direkt ausgefuehrt
    """
    from app.services.rag.ai_action_service import get_ai_action_service

    action_service = get_ai_action_service()
    return await action_service.execute_action(db=db, user=current_user, request=request)


@router.post("/ai/actions/confirm")
async def confirm_ai_action(
    request: AIActionConfirmRequest,
    db: AsyncSession = Depends(get_async_session),
    current_user: User = Depends(get_current_user),
) -> AIActionResult:
    """Bestaetigt oder lehnt eine vorgeschlagene AI-Aktion ab.

    Args:
        request.action_id: ID der vorgeschlagenen Aktion
        request.confirmed: True = ausfuehren, False = ablehnen
        request.modified_parameters: Optional geaenderte Parameter
    """
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
) -> AIContextInfo:
    """Gibt kontextspezifische Informationen fuer den AI-Assistenten zurueck.

    Liefert:
    - Verfuegbare Aktionen fuer den aktuellen Kontext
    - Vorgeschlagene Fragen/Befehle
    - Autonomie-Level des Benutzers
    """
    from app.services.rag.ai_action_service import get_ai_action_service

    action_service = get_ai_action_service()
    return action_service.get_context_info(
        user=current_user,
        page_type=page_type,
        document_id=document_id,
        entity_id=entity_id,
    )
