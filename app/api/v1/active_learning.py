# -*- coding: utf-8 -*-
"""
API-Endpunkte fuer Active Learning Pipeline.

Phase 2.4: Uncertainty Sampling - Review-Queue und Impact-Metriken.
Ermoeglicht die manuelle Pruefung und Korrektur von OCR-Ergebnissen
mit niedrigem Confidence-Score.

Feinpoliert und durchdacht - Enterprise Active Learning API.
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db, get_current_company_id
from app.db.models import User
from app.services.active_learning.active_learning_service import ActiveLearningService
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/active-learning", tags=["Active Learning"])


# =============================================================================
# Request/Response Models
# =============================================================================


class ReviewSubmission(BaseModel):
    """Korrektur-Eingabe fuer ein Queue-Item."""

    corrections: Dict[str, str] = Field(
        ...,
        description="Korrekturen: {feldname: korrigierter_wert}",
        examples=[{"amount": "1.234,56", "date": "15.02.2026"}],
    )

    model_config = ConfigDict(from_attributes=True)


class QueueItemResponse(BaseModel):
    """Response fuer ein Active-Learning-Queue-Item."""

    id: str = Field(..., description="Queue-Item-ID")
    document_id: str = Field(..., description="Dokument-ID")
    priority_score: float = Field(..., description="Prioritaet (0-1)")
    uncertainty_score: float = Field(..., description="Unsicherheits-Score (0-1)")
    estimated_impact: float = Field(..., description="Geschaetzter Impact")
    queue_reason: str = Field(..., description="Grund fuer Queue-Aufnahme")
    ocr_backend: Optional[str] = Field(None, description="OCR-Backend")
    ocr_confidence: Optional[float] = Field(None, description="OCR-Confidence")
    field_focus: List[str] = Field(default_factory=list, description="Fokus-Felder")
    status: str = Field(..., description="Status: queued/in_review/reviewed/skipped")
    reviewed_at: Optional[datetime] = Field(None, description="Pruefungszeitpunkt")
    correction_data: Optional[Dict[str, str]] = Field(
        None, description="Korrekturdaten"
    )
    created_at: datetime = Field(..., description="Erstellungszeitpunkt")

    model_config = ConfigDict(from_attributes=True)


class QueueStatsResponse(BaseModel):
    """Statistiken der Review-Queue."""

    queued: int = Field(0, description="Wartend auf Pruefung")
    in_review: int = Field(0, description="Aktuell in Pruefung")
    reviewed: int = Field(0, description="Geprueft mit Korrekturen")
    skipped: int = Field(0, description="Uebersprungen")
    total: int = Field(0, description="Gesamt")
    avg_priority: int = Field(0, description="Durchschnittliche Prioritaet (%)")

    model_config = ConfigDict(from_attributes=True)


class ImpactMetricsResponse(BaseModel):
    """Impact-Metriken fuer Active Learning."""

    total_reviewed_30d: float = Field(0, description="Geprueft (30 Tage)")
    total_corrections_30d: float = Field(0, description="Korrekturen (30 Tage)")
    estimated_errors_prevented: float = Field(
        0, description="Geschaetzte verhinderte Fehler"
    )
    avg_confidence_before: float = Field(0, description="Durchschn. Confidence vorher")
    avg_confidence_after: float = Field(0, description="Durchschn. Confidence nachher")
    confidence_improvement: float = Field(0, description="Confidence-Verbesserung")
    correction_rate: float = Field(0, description="Korrektur-Rate")

    model_config = ConfigDict(from_attributes=True)


class PopulateResponse(BaseModel):
    """Response fuer Queue-Befuellung."""

    added: int = Field(..., description="Neu hinzugefuegte Items")
    message: str = Field(..., description="Status-Nachricht")

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/queue",
    response_model=List[QueueItemResponse],
    summary="Review-Queue abrufen",
    description="Aktuelle Review-Queue mit priorisierten OCR-Korrekturen (paginiert).",
)
async def get_queue(
    limit: int = Query(20, ge=1, le=100, description="Anzahl Eintraege"),
    offset: int = Query(0, ge=0, description="Offset fuer Pagination"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> List[QueueItemResponse]:
    """Holt die aktuelle Review-Queue fuer die Company des Benutzers."""
    try:
        from sqlalchemy import select
        from app.db.models_active_learning import ActiveLearningQueue

        query = (
            select(ActiveLearningQueue)
            .where(
                ActiveLearningQueue.company_id == company_id,
                ActiveLearningQueue.status.in_(["queued", "in_review"]),
            )
            .order_by(ActiveLearningQueue.priority_score.desc())
            .offset(offset)
            .limit(limit)
        )

        result = await db.execute(query)
        items = result.scalars().all()

        return [
            QueueItemResponse(
                id=str(item.id),
                document_id=str(item.document_id),
                priority_score=item.priority_score,
                uncertainty_score=item.uncertainty_score,
                estimated_impact=item.estimated_impact,
                queue_reason=item.queue_reason,
                ocr_backend=item.ocr_backend,
                ocr_confidence=item.ocr_confidence,
                field_focus=item.field_focus or [],
                status=item.status,
                reviewed_at=item.reviewed_at,
                correction_data=item.correction_data,
                created_at=item.created_at,
            )
            for item in items
        ]

    except Exception as e:
        logger.error(
            "get_queue_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning Queue"),
        )


@router.get(
    "/next",
    response_model=Optional[QueueItemResponse],
    summary="Naechstes Review-Item",
    description="Holt das naechste priorisierte Item zur Pruefung.",
)
async def get_next_item(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Optional[QueueItemResponse]:
    """Holt das naechste Item mit der hoechsten Prioritaet."""
    try:
        service = ActiveLearningService(db)
        item = await service.get_next_review_item(company_id=company_id)

        if item is None:
            return None

        return QueueItemResponse(
            id=str(item.id),
            document_id=str(item.document_id),
            priority_score=item.priority_score,
            uncertainty_score=item.uncertainty_score,
            estimated_impact=item.estimated_impact,
            queue_reason=item.queue_reason,
            ocr_backend=item.ocr_backend,
            ocr_confidence=item.ocr_confidence,
            field_focus=item.field_focus or [],
            status=item.status,
            reviewed_at=item.reviewed_at,
            correction_data=item.correction_data,
            created_at=item.created_at,
        )

    except Exception as e:
        logger.error(
            "get_next_item_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning"),
        )


@router.post(
    "/{item_id}/review",
    response_model=QueueItemResponse,
    summary="Korrektur einreichen",
    description="Reicht die Korrektur fuer ein Queue-Item ein.",
)
async def submit_review(
    item_id: UUID,
    body: ReviewSubmission,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> QueueItemResponse:
    """Speichert die Korrektur eines Benutzers fuer ein Queue-Item."""
    try:
        service = ActiveLearningService(db)
        item = await service.submit_review(
            item_id=item_id,
            user_id=current_user.id,
            corrections=body.corrections,
            skip=False,
        )
        await db.commit()

        logger.info(
            "review_submitted_via_api",
            item_id=str(item_id),
            user_id=str(current_user.id),
            corrections_count=len(body.corrections),
        )

        return QueueItemResponse(
            id=str(item.id),
            document_id=str(item.document_id),
            priority_score=item.priority_score,
            uncertainty_score=item.uncertainty_score,
            estimated_impact=item.estimated_impact,
            queue_reason=item.queue_reason,
            ocr_backend=item.ocr_backend,
            ocr_confidence=item.ocr_confidence,
            field_focus=item.field_focus or [],
            status=item.status,
            reviewed_at=item.reviewed_at,
            correction_data=item.correction_data,
            created_at=item.created_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "submit_review_failed",
            item_id=str(item_id),
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning Review"),
        )


@router.post(
    "/{item_id}/skip",
    response_model=QueueItemResponse,
    summary="Item ueberspringen",
    description="Markiert ein Queue-Item als uebersprungen.",
)
async def skip_item(
    item_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> QueueItemResponse:
    """Ueberspringt ein Queue-Item ohne Korrektur."""
    try:
        service = ActiveLearningService(db)
        item = await service.submit_review(
            item_id=item_id,
            user_id=current_user.id,
            corrections={},
            skip=True,
        )
        await db.commit()

        logger.info(
            "item_skipped_via_api",
            item_id=str(item_id),
            user_id=str(current_user.id),
        )

        return QueueItemResponse(
            id=str(item.id),
            document_id=str(item.document_id),
            priority_score=item.priority_score,
            uncertainty_score=item.uncertainty_score,
            estimated_impact=item.estimated_impact,
            queue_reason=item.queue_reason,
            ocr_backend=item.ocr_backend,
            ocr_confidence=item.ocr_confidence,
            field_focus=item.field_focus or [],
            status=item.status,
            reviewed_at=item.reviewed_at,
            correction_data=item.correction_data,
            created_at=item.created_at,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "skip_item_failed",
            item_id=str(item_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning Skip"),
        )


@router.get(
    "/stats",
    response_model=QueueStatsResponse,
    summary="Queue-Statistiken",
    description="Statistiken der Active-Learning-Queue.",
)
async def get_stats(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> QueueStatsResponse:
    """Holt Statistiken der Review-Queue."""
    try:
        service = ActiveLearningService(db)
        stats = await service.get_queue_stats(company_id=company_id)

        return QueueStatsResponse(**stats)

    except Exception as e:
        logger.error(
            "get_stats_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning Statistiken"),
        )


@router.get(
    "/metrics",
    response_model=ImpactMetricsResponse,
    summary="Impact-Metriken",
    description=(
        "Berechnet Impact-Metriken: Wie viele Fehler wurden durch "
        "Active Learning verhindert?"
    ),
)
async def get_metrics(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> ImpactMetricsResponse:
    """Berechnet und liefert Impact-Metriken."""
    try:
        service = ActiveLearningService(db)
        metrics = await service.calculate_impact_metrics(company_id=company_id)

        return ImpactMetricsResponse(**metrics)

    except Exception as e:
        logger.error(
            "get_metrics_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning Metriken"),
        )


@router.post(
    "/populate",
    response_model=PopulateResponse,
    summary="Queue befuellen",
    description="Triggert die Befuellung der Queue mit neuen Kandidaten.",
)
async def populate_queue(
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl neuer Items"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> PopulateResponse:
    """Befuellt die Queue manuell mit neuen Kandidaten."""
    try:
        service = ActiveLearningService(db)
        added = await service.populate_queue(
            company_id=company_id,
            limit=limit,
        )
        await db.commit()

        message = (
            f"{added} neue Items zur Queue hinzugefuegt"
            if added > 0
            else "Keine neuen Kandidaten gefunden"
        )

        logger.info(
            "queue_populated_via_api",
            user_id=str(current_user.id),
            added=added,
        )

        return PopulateResponse(
            added=added,
            message=message,
        )

    except Exception as e:
        logger.error(
            "populate_queue_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning Queue-Befuellung"),
        )


@router.get(
    "/history",
    response_model=List[QueueItemResponse],
    summary="Review-Verlauf",
    description="Letzte bearbeitete Items mit Korrekturdaten.",
)
async def get_history(
    limit: int = Query(20, ge=1, le=100, description="Anzahl Eintraege"),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> List[QueueItemResponse]:
    """Holt den Review-Verlauf."""
    try:
        service = ActiveLearningService(db)
        items = await service.get_review_history(
            company_id=company_id,
            limit=limit,
        )

        return [
            QueueItemResponse(
                id=str(item.id),
                document_id=str(item.document_id),
                priority_score=item.priority_score,
                uncertainty_score=item.uncertainty_score,
                estimated_impact=item.estimated_impact,
                queue_reason=item.queue_reason,
                ocr_backend=item.ocr_backend,
                ocr_confidence=item.ocr_confidence,
                field_focus=item.field_focus or [],
                status=item.status,
                reviewed_at=item.reviewed_at,
                correction_data=item.correction_data,
                created_at=item.created_at,
            )
            for item in items
        ]

    except Exception as e:
        logger.error(
            "get_history_failed",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Active Learning Verlauf"),
        )
