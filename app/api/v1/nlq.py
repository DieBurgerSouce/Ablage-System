"""
Natural Language Query (NLQ) API Router.

Ermöglicht natürlichsprachige Datenbankabfragen mit KI-gestützter SQL-Generierung.
"""

from typing import AsyncGenerator, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, engine
from app.core.safe_errors import safe_error_detail
from app.core.redis_state import get_redis
from app.db.models import User
from app.services.ai.nlq.nlq_orchestrator import NLQOrchestrator
from app.core.rate_limiting import limiter, get_user_identifier

router = APIRouter(prefix="/nlq", tags=["nlq"])


# ============================================================================
# Schemas
# ============================================================================


class NLQQueryRequest(BaseModel):
    """Anfrage für eine natürlichsprachige Query."""

    query: str = Field(..., min_length=3, max_length=1000)

    model_config = ConfigDict(from_attributes=True)


class NLQQueryResponse(BaseModel):
    """Antwort auf eine natürlichsprachige Query."""

    query_log_id: UUID
    natural_query: str
    # SECURITY: generated_sql wird nur für Superuser zurueckgegeben (Injection-
    # Iteration durch Non-Admins verhindern). Non-Admin sieht ``None``.
    generated_sql: Optional[str] = None
    text_summary: str
    data: List[JSONDict]
    visualization_type: str
    visualization_config: JSONDict
    execution_time_ms: int
    result_count: int
    was_cached: bool
    confidence: float

    model_config = ConfigDict(from_attributes=True)


class NLQFeedbackRequest(BaseModel):
    """Feedback für eine Query."""

    query_log_id: UUID
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)

    model_config = ConfigDict(from_attributes=True)


class NLQSuggestionsResponse(BaseModel):
    """Vorgeschlagene natürlichsprachige Queries."""

    suggestions: List[str]

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/query", response_model=NLQQueryResponse)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def execute_nlq_query(
    request: Request,
    body: NLQQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NLQQueryResponse:
    """
    Führt eine natürlichsprachige Query aus.

    Wandelt natürliche Sprache in SQL um, führt die Query aus und
    generiert eine Zusammenfassung mit Visualisierungsvorschlägen.

    Args:
        body: Query-Request mit natürlichsprachiger Frage
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Query-Ergebnis mit SQL, Daten, Zusammenfassung und Visualisierung

    Raises:
        HTTPException: Bei ungültiger Query oder Ausführungsfehler
    """
    try:
        redis_manager = await get_redis()
        redis_client = await redis_manager.get_client()
        orchestrator = NLQOrchestrator(engine=engine, redis=redis_client)

        result = await orchestrator.query(
            natural_query=body.query,
            user_id=current_user.id,
            company_id=current_user.company_id,
            db=db,
        )

        return NLQQueryResponse(
            query_log_id=result.query_log_id,
            natural_query=result.natural_query,
            # SECURITY: SQL nur für Admins exposen - Non-Admin sieht None.
            # Verhindert dass Angreifer durch iterierte Queries den
            # SQL-Sanitizer/Generator profilen koennen.
            generated_sql=(
                result.generated_sql if current_user.is_superuser else None
            ),
            text_summary=result.result.text_summary,
            data=result.result.data,
            visualization_type=result.visualization_type,
            visualization_config=result.visualization_config,
            execution_time_ms=result.execution_time_ms,
            result_count=len(result.result.data),
            was_cached=result.was_cached,
            confidence=result.confidence,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.post("/query/stream")
@limiter.limit("10/minute", key_func=get_user_identifier)
async def execute_nlq_query_stream(
    request: Request,
    body: NLQQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> StreamingResponse:
    """
    Führt eine natürlichsprachige Query mit SSE-Streaming aus.

    Streamt den Fortschritt der Query-Ausführung in Echtzeit.

    Args:
        body: Query-Request mit natürlichsprachiger Frage
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Server-Sent Events Stream mit Fortschrittsinformationen

    Raises:
        HTTPException: Bei ungültiger Query oder Ausführungsfehler
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        """Generiert SSE-Events für Query-Ausführung."""
        try:
            redis_manager = await get_redis()
            redis_client = await redis_manager.get_client()
            orchestrator = NLQOrchestrator(engine=engine, redis=redis_client)

            # Streaming nicht nativ unterstützt - fallback auf regulaere Query
            result = await orchestrator.query(
                natural_query=body.query,
                user_id=current_user.id,
                company_id=current_user.company_id,
                db=db,
            )

            # Single event mit Ergebnis
            import json
            yield f"data: {json.dumps({'status': 'completed', 'query_log_id': str(result.query_log_id)})}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as e:
            error_msg = f'{{"error": "{safe_error_detail(e, "Query-Streaming")}"}}'
            yield f"data: {error_msg}\n\n"

    return StreamingResponse(
        event_generator(), media_type="text/event-stream"
    )


@router.get("/suggestions", response_model=NLQSuggestionsResponse)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def get_query_suggestions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> NLQSuggestionsResponse:
    """
    Gibt Query-Vorschläge basierend auf dem Datenbankschema.

    Generiert kontextbasierte Beispiel-Queries, die der Benutzer
    verwenden kann.

    Args:
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Returns:
        Liste mit vorgeschlagenen natürlichsprachigen Queries

    Raises:
        HTTPException: Bei Fehler beim Generieren der Vorschläge
    """
    try:
        redis_manager = await get_redis()
        redis_client = await redis_manager.get_client()
        orchestrator = NLQOrchestrator(engine=engine, redis=redis_client)

        suggestions = await orchestrator.get_suggestions(
            company_id=current_user.company_id,
            db=db,
        )

        return NLQSuggestionsResponse(suggestions=suggestions)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def submit_query_feedback(
    request: Request,
    body: NLQFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Übermittelt Feedback für eine Query.

    Speichert Benutzer-Feedback zur kontinuierlichen Verbesserung
    der NLQ-Engine.

    Args:
        body: Feedback-Request mit Bewertung und Kommentar
        db: Datenbank-Session
        current_user: Aktuell angemeldeter Benutzer

    Raises:
        HTTPException: Bei ungültiger Query-Log-ID oder Fehler
    """
    try:
        redis_manager = await get_redis()
        redis_client = await redis_manager.get_client()
        orchestrator = NLQOrchestrator(engine=engine, redis=redis_client)

        await orchestrator.submit_feedback(
            query_log_id=body.query_log_id,
            rating=body.rating,
            comment=body.comment,
            db=db,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Vorgang"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vorgang"),
        )
