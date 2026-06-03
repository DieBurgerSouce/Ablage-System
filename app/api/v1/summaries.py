"""API-Endpunkte fuer Dokumenten-Zusammenfassungen.

Generierung, Abruf und Batch-Verarbeitung von KI-generierten
Zusammenfassungen, Schluesselwoertern und Einzeilern.

Phase 2.2: Auto-Zusammenfassungen.
Feinpoliert und durchdacht.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_user_company_id_dep
from app.core.rate_limiting import limiter, get_user_identifier
from app.core.safe_errors import safe_error_log
from app.db.models import Document, User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/summaries", tags=["summaries"])


# =============================================================================
# Response Models
# =============================================================================


class SummaryResponse(BaseModel):
    """Zusammenfassungs-Antwort fuer ein Dokument."""

    document_id: str = Field(..., description="Dokument-ID")
    summary: Optional[str] = Field(None, description="Zusammenfassung (3-5 Saetze)")
    keywords: List[str] = Field(default_factory=list, description="Schluesselwoerter")
    one_liner: Optional[str] = Field(None, description="Einzeilige Beschreibung")
    model: Optional[str] = Field(None, description="Verwendetes LLM-Modell")
    generated_at: Optional[str] = Field(None, description="Zeitpunkt der Generierung")


class SummaryGenerateResponse(BaseModel):
    """Antwort nach Summary-Generierung."""

    document_id: str = Field(..., description="Dokument-ID")
    summary: str = Field(..., description="Generierte Zusammenfassung")
    keywords: List[str] = Field(default_factory=list, description="Schluesselwoerter")
    one_liner: str = Field(..., description="Einzeilige Beschreibung")
    model: str = Field(..., description="Verwendetes LLM-Modell")
    generated_at: str = Field(..., description="Zeitpunkt der Generierung")


class BatchGenerateRequest(BaseModel):
    """Request fuer Batch-Generierung."""

    limit: int = Field(default=50, ge=1, le=500, description="Maximale Anzahl Dokumente")


class BatchGenerateResponse(BaseModel):
    """Antwort nach Batch-Generierung."""

    message: str = Field(..., description="Statusmeldung")
    task_id: str = Field(..., description="Celery Task-ID")
    company_id: str = Field(..., description="Mandanten-ID")
    limit: int = Field(..., description="Angefordertes Limit")


class SummaryStatsResponse(BaseModel):
    """Statistiken ueber Summary-Generierung."""

    total_documents: int = Field(..., description="Gesamtanzahl Dokumente")
    with_summary: int = Field(..., description="Dokumente mit Zusammenfassung")
    without_summary: int = Field(..., description="Dokumente ohne Zusammenfassung")
    percentage: float = Field(..., description="Prozent mit Zusammenfassung")


# =============================================================================
# API Endpoints
# =============================================================================


@router.post(
    "/documents/{document_id}/summary",
    response_model=SummaryGenerateResponse,
    summary="Zusammenfassung generieren",
    description="Generiert oder regeneriert die KI-Zusammenfassung fuer ein Dokument.",
    status_code=status.HTTP_200_OK,
)
@limiter.limit("10/minute", key_func=get_user_identifier)
async def generate_summary(
    request,  # noqa: ANN001 - Required by slowapi limiter
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SummaryGenerateResponse:
    """Generiert oder regeneriert die Zusammenfassung fuer ein Dokument."""
    from app.services.summarization.summary_service import SummaryService

    # Dokument-Zugriff pruefen
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.company_id == company_id,
            Document.deleted_at.is_(None),
        )
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    try:
        service = SummaryService(db)

        # Regenerieren wenn bereits vorhanden, sonst neu generieren
        if document.summary is not None:
            summary_result = await service.regenerate_summary(document_id)
        else:
            summary_result = await service.generate_summary(document_id)

        return SummaryGenerateResponse(
            document_id=str(document_id),
            summary=str(summary_result["summary"]),
            keywords=list(summary_result.get("keywords", [])),
            one_liner=str(summary_result.get("one_liner", "")),
            model=str(summary_result["model"]),
            generated_at=str(summary_result["generated_at"]),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except RuntimeError as exc:
        logger.error(
            "summary_generation_api_error",
            document_id=str(document_id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM-Service nicht verfuegbar. Bitte spaeter erneut versuchen.",
        )


@router.get(
    "/documents/{document_id}/summary",
    response_model=SummaryResponse,
    summary="Zusammenfassung abrufen",
    description="Gibt die gespeicherte Zusammenfassung fuer ein Dokument zurueck.",
)
@limiter.limit("60/minute", key_func=get_user_identifier)
async def get_summary(
    request,  # noqa: ANN001 - Required by slowapi limiter
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SummaryResponse:
    """Gibt die gespeicherte Zusammenfassung eines Dokuments zurueck."""
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.company_id == company_id,
            Document.deleted_at.is_(None),
        )
    )
    document = result.scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    generated_at = None
    if document.summary_generated_at is not None:
        generated_at = document.summary_generated_at.isoformat()

    return SummaryResponse(
        document_id=str(document_id),
        summary=document.summary,
        keywords=document.keywords if document.keywords else [],
        one_liner=document.one_liner,
        model=document.summary_model,
        generated_at=generated_at,
    )


@router.post(
    "/batch",
    response_model=BatchGenerateResponse,
    summary="Batch-Generierung starten",
    description="Startet die Batch-Generierung von Zusammenfassungen fuer alle Dokumente ohne Summary.",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("5/minute", key_func=get_user_identifier)
async def batch_generate(
    request,  # noqa: ANN001 - Required by slowapi limiter
    body: BatchGenerateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> BatchGenerateResponse:
    """Startet asynchrone Batch-Generierung von Zusammenfassungen."""
    from app.workers.tasks.summary_tasks import batch_generate_summaries_task

    task = batch_generate_summaries_task.apply_async(
        args=[str(company_id)],
        kwargs={"limit": body.limit},
    )

    logger.info(
        "batch_summary_triggered",
        company_id=str(company_id),
        task_id=task.id,
        limit=body.limit,
    )

    return BatchGenerateResponse(
        message=f"Batch-Generierung gestartet fuer bis zu {body.limit} Dokumente",
        task_id=task.id,
        company_id=str(company_id),
        limit=body.limit,
    )


@router.get(
    "/stats",
    response_model=SummaryStatsResponse,
    summary="Summary-Statistiken",
    description="Zeigt Statistiken ueber die Summary-Generierung fuer den aktuellen Mandanten.",
)
@limiter.limit("30/minute", key_func=get_user_identifier)
async def get_stats(
    request,  # noqa: ANN001 - Required by slowapi limiter
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SummaryStatsResponse:
    """Gibt Summary-Statistiken fuer den aktuellen Mandanten zurueck."""
    from app.services.summarization.summary_service import SummaryService

    service = SummaryService(db)
    stats = await service.get_summary_stats(company_id=company_id)

    return SummaryStatsResponse(
        total_documents=stats["total_documents"],
        with_summary=stats["with_summary"],
        without_summary=stats["without_summary"],
        percentage=stats["percentage"],
    )
