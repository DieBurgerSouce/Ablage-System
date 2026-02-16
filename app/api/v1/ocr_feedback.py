# -*- coding: utf-8 -*-
"""
Enhanced OCR Feedback API Endpoints.

REST API für erweitertes OCR-Korrektur-System mit Gamification:
- Inline-Korrekturen auf Feld-Ebene
- Korrektur-Queue für niedrig-konfidente Extraktionen
- Punkte-System mit Leaderboard
- Batch-Korrektur-Verarbeitung
- Benutzer-Statistiken und Achievements

Phase 6.3: OCR Feedback UX Improvements für Enterprise-Dokumentenmanagement.
Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Präzision.
"""

from typing import Optional, List
from uuid import UUID
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import User, Document
from app.api.dependencies import get_db, get_current_active_user
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.services.ocr.feedback_service import (
    EnhancedOCRFeedbackService,
    CorrectionFeedback,
    LeaderboardPeriod,
    QueuePriority,
    get_feedback_service,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ocr-feedback", tags=["OCR Feedback"])


# =============================================================================
# SCHEMAS
# =============================================================================


class CorrectionRequest(BaseModel):
    """Anfrage für eine Korrektur."""
    document_id: UUID
    field_name: str = Field(..., max_length=100)
    original_value: str
    corrected_value: str
    confidence_before: float = Field(..., ge=0.0, le=1.0)
    correction_type: str = Field("text", regex="^(text|amount|date|entity|iban|vat_id|reference)$")
    ocr_backend: Optional[str] = Field(None, max_length=50)
    page_number: Optional[int] = Field(None, ge=1)
    bounding_box: Optional[dict] = None
    context_text: Optional[str] = Field(None, max_length=500)


class BatchCorrectionRequest(BaseModel):
    """Anfrage für Batch-Korrekturen."""
    corrections: List[CorrectionRequest] = Field(..., min_length=1, max_length=100)


class CorrectionResultResponse(BaseModel):
    """Antwort für eine einzelne Korrektur."""
    correction_id: str
    document_id: str
    field_name: str
    applied: bool
    points_awarded: int
    bonus_points: int
    total_points: int
    new_user_total: int
    new_streak: int
    achievements_unlocked: List[str]
    feedback_message: str


class BatchCorrectionResponse(BaseModel):
    """Antwort für Batch-Korrekturen."""
    batch_id: str
    total_corrections: int
    applied_count: int
    rejected_count: int
    total_points_awarded: int
    processing_time_ms: int
    errors: List[dict]


class QueueItemResponse(BaseModel):
    """Antwort für ein Queue-Item."""
    id: str
    document_id: str
    document_filename: str
    field_name: str
    ocr_value: str
    confidence: float
    priority: str
    ocr_backend: str
    document_type: Optional[str]
    entity_name: Optional[str]
    page_number: Optional[int]
    context_text: Optional[str]
    suggested_value: Optional[str]
    created_at: str


class LeaderboardEntryResponse(BaseModel):
    """Antwort für einen Leaderboard-Eintrag."""
    rank: int
    user_id: str
    username: str
    full_name: Optional[str]
    corrections_count: int
    total_points: int
    accuracy_rate: float
    current_streak: int
    longest_streak: int
    achievements: List[str]
    is_current_user: bool


class UserStatsResponse(BaseModel):
    """Antwort für Benutzer-Statistiken."""
    user_id: str
    total_corrections: int
    total_points: int
    current_streak: int
    longest_streak: int
    weekly_corrections: int
    weekly_points: int
    monthly_corrections: int
    monthly_points: int
    weekly_rank: Optional[int]
    monthly_rank: Optional[int]
    accuracy_rate: float
    achievements: List[str]
    recent_corrections: List[dict]
    points_breakdown: dict


# =============================================================================
# CORRECTION ENDPOINTS
# =============================================================================


@router.post(
    "/correction",
    status_code=status.HTTP_201_CREATED,
    response_model=CorrectionResultResponse,
    summary="Korrektur einreichen",
    description="Reicht eine OCR-Korrektur ein und berechnet Punkte"
)
async def submit_correction(
    request: CorrectionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> CorrectionResultResponse:
    """
    Reicht eine einzelne OCR-Korrektur ein.

    **Punkte-System:**
    - Basis-Punkte je nach Korrektur-Typ (10-25)
    - Bonus für grosse Korrekturen (+5)
    - Bonus für niedrige Konfidenz (+10)
    - Streak-Bonus (+3 pro Tag)
    - Erste Korrektur des Tages (+5)
    - Konsekutive Korrekturen (+2 pro Korrektur, max +20)

    **Korrektur-Typen:**
    - text: Allgemeiner Text (10 Punkte)
    - amount: Geldbetraege (15 Punkte)
    - date: Datumsangaben (12 Punkte)
    - entity: Firmen-/Personennamen (20 Punkte)
    - iban: Bankdaten (25 Punkte)
    - vat_id: Steuernummern (25 Punkte)
    - reference: Referenznummern (15 Punkte)
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Dokument prüfen
    result = await db.execute(
        select(Document).where(
            Document.id == request.document_id,
            Document.owner_id == current_user.id,
            Document.deleted_at.is_(None),
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden oder keine Berechtigung"
        )

    service = get_feedback_service(db)

    feedback = CorrectionFeedback(
        document_id=request.document_id,
        field_name=request.field_name,
        original_value=request.original_value,
        corrected_value=request.corrected_value,
        confidence_before=request.confidence_before,
        correction_type=request.correction_type,
        user_id=current_user.id,
        ocr_backend=request.ocr_backend,
        page_number=request.page_number,
        bounding_box=request.bounding_box,
        context_text=request.context_text,
    )

    try:
        result = await service.submit_correction(feedback, company_id)
    except Exception as e:
        logger.error(
            "correction_submission_failed",
            document_id=str(request.document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "OCR-Korrektur")
        )

    await db.commit()

    logger.info(
        "correction_submitted_via_api",
        correction_id=str(result.correction_id),
        points=result.total_points,
        streak=result.new_streak,
    )

    return CorrectionResultResponse(
        correction_id=str(result.correction_id),
        document_id=str(result.document_id),
        field_name=result.field_name,
        applied=result.applied,
        points_awarded=result.points_awarded,
        bonus_points=result.bonus_points,
        total_points=result.total_points,
        new_user_total=result.new_user_total,
        new_streak=result.new_streak,
        achievements_unlocked=result.achievements_unlocked,
        feedback_message=result.feedback_message,
    )


@router.post(
    "/batch",
    status_code=status.HTTP_201_CREATED,
    response_model=BatchCorrectionResponse,
    summary="Batch-Korrekturen einreichen",
    description="Reicht mehrere OCR-Korrekturen auf einmal ein"
)
async def submit_batch_corrections(
    request: BatchCorrectionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BatchCorrectionResponse:
    """
    Reicht mehrere Korrekturen als Batch ein.

    Effizientere Verarbeitung für größere Korrektur-Sessions.
    Punkte werden für jede Korrektur einzeln berechnet.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Alle Dokumente prüfen
    doc_ids = {c.document_id for c in request.corrections}
    for doc_id in doc_ids:
        result = await db.execute(
            select(Document).where(
                Document.id == doc_id,
                Document.owner_id == current_user.id,
                Document.deleted_at.is_(None),
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokument {doc_id} nicht gefunden"
            )

    service = get_feedback_service(db)

    corrections = [
        CorrectionFeedback(
            document_id=c.document_id,
            field_name=c.field_name,
            original_value=c.original_value,
            corrected_value=c.corrected_value,
            confidence_before=c.confidence_before,
            correction_type=c.correction_type,
            user_id=current_user.id,
            ocr_backend=c.ocr_backend,
            page_number=c.page_number,
            bounding_box=c.bounding_box,
            context_text=c.context_text,
        )
        for c in request.corrections
    ]

    result = await service.submit_batch_corrections(
        corrections=corrections,
        company_id=company_id,
        user_id=current_user.id,
    )

    logger.info(
        "batch_corrections_submitted_via_api",
        batch_id=str(result.batch_id),
        total=result.total_corrections,
        applied=result.applied_count,
        points=result.total_points_awarded,
    )

    return BatchCorrectionResponse(
        batch_id=str(result.batch_id),
        total_corrections=result.total_corrections,
        applied_count=result.applied_count,
        rejected_count=result.rejected_count,
        total_points_awarded=result.total_points_awarded,
        processing_time_ms=result.processing_time_ms,
        errors=result.errors,
    )


# =============================================================================
# QUEUE ENDPOINTS
# =============================================================================


@router.get(
    "/queue",
    summary="Korrektur-Queue abrufen",
    description="Liefert niedrig-konfidente OCR-Extraktionen zur Korrektur"
)
async def get_correction_queue(
    priority: Optional[str] = Query(None, regex="^(critical|high|medium|low)$"),
    document_type: Optional[str] = Query(None, max_length=50),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft die Korrektur-Queue ab.

    **Prioritaeten:**
    - critical: <40% Konfidenz
    - high: 40-55% Konfidenz
    - medium: 55-65% Konfidenz
    - low: 65-70% Konfidenz

    Items werden nach Konfidenz aufsteigend sortiert (niedrigste zuerst).
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    priority_enum = QueuePriority(priority) if priority else None

    service = get_feedback_service(db)
    items, total = await service.get_correction_queue(
        company_id=company_id,
        priority=priority_enum,
        document_type=document_type,
        limit=limit,
        offset=offset,
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            QueueItemResponse(
                id=str(item.id),
                document_id=str(item.document_id),
                document_filename=item.document_filename,
                field_name=item.field_name,
                ocr_value=item.ocr_value,
                confidence=item.confidence,
                priority=item.priority.value,
                ocr_backend=item.ocr_backend,
                document_type=item.document_type,
                entity_name=item.entity_name,
                page_number=item.page_number,
                context_text=item.context_text,
                suggested_value=item.suggested_value,
                created_at=item.created_at.isoformat() if item.created_at else None,
            ).model_dump()
            for item in items
        ],
    }


@router.post(
    "/queue/{item_id}/claim",
    summary="Queue-Item reservieren",
    description="Reserviert ein Queue-Item für den aktuellen Benutzer"
)
async def claim_queue_item(
    item_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Reserviert ein Queue-Item.

    Verhindert dass mehrere Benutzer gleichzeitig am selben Item arbeiten.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_feedback_service(db)
    success = await service.claim_queue_item(
        item_id=item_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Queue-Item nicht gefunden oder bereits reserviert"
        )

    await db.commit()

    return {
        "item_id": str(item_id),
        "claimed": True,
        "claimed_by": str(current_user.id),
        "message": "Queue-Item erfolgreich reserviert",
    }


# =============================================================================
# LEADERBOARD ENDPOINTS
# =============================================================================


@router.get(
    "/leaderboard",
    summary="Leaderboard abrufen",
    description="Liefert das Korrektur-Leaderboard"
)
async def get_leaderboard(
    period: str = Query("weekly", regex="^(weekly|monthly|all_time)$"),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft das Leaderboard ab.

    **Zeitraeume:**
    - weekly: Letzte 7 Tage
    - monthly: Letzte 30 Tage
    - all_time: Alle Zeit

    Mindestens 5 Korrekturen erforderlich für Ranking.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    period_enum = LeaderboardPeriod(period)

    service = get_feedback_service(db)
    entries = await service.get_leaderboard(
        company_id=company_id,
        period=period_enum,
        current_user_id=current_user.id,
        limit=limit,
    )

    return {
        "period": period,
        "entries": [
            LeaderboardEntryResponse(
                rank=e.rank,
                user_id=str(e.user_id),
                username=e.username,
                full_name=e.full_name,
                corrections_count=e.corrections_count,
                total_points=e.total_points,
                accuracy_rate=e.accuracy_rate,
                current_streak=e.current_streak,
                longest_streak=e.longest_streak,
                achievements=e.achievements,
                is_current_user=e.is_current_user,
            ).model_dump()
            for e in entries
        ],
    }


@router.get(
    "/stats",
    response_model=UserStatsResponse,
    summary="Benutzer-Statistiken abrufen",
    description="Liefert die OCR-Korrektur-Statistiken des aktuellen Benutzers"
)
async def get_user_stats(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    """
    Ruft die Statistiken des aktuellen Benutzers ab.

    Beinhaltet:
    - Gesamtstatistiken
    - Woechentliche/monatliche Statistiken
    - Ranks in Leaderboards
    - Achievements
    - Letzte Korrekturen
    - Punkte-Aufschluesselung
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_feedback_service(db)
    stats = await service.get_user_stats(
        user_id=current_user.id,
        company_id=company_id,
    )

    return UserStatsResponse(
        user_id=str(stats.user_id),
        total_corrections=stats.total_corrections,
        total_points=stats.total_points,
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        weekly_corrections=stats.weekly_corrections,
        weekly_points=stats.weekly_points,
        monthly_corrections=stats.monthly_corrections,
        monthly_points=stats.monthly_points,
        weekly_rank=stats.weekly_rank,
        monthly_rank=stats.monthly_rank,
        accuracy_rate=stats.accuracy_rate,
        achievements=stats.achievements,
        recent_corrections=stats.recent_corrections,
        points_breakdown=stats.points_breakdown,
    )


@router.get(
    "/stats/{user_id}",
    response_model=UserStatsResponse,
    summary="Statistiken eines Benutzers abrufen",
    description="Liefert die OCR-Korrektur-Statistiken eines bestimmten Benutzers (Admin)"
)
async def get_user_stats_by_id(
    user_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserStatsResponse:
    """
    Ruft die Statistiken eines bestimmten Benutzers ab.

    Nur für Admins oder den Benutzer selbst.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    # Nur eigene Stats oder Admin
    if user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für diese Statistiken"
        )

    service = get_feedback_service(db)
    stats = await service.get_user_stats(
        user_id=user_id,
        company_id=company_id,
    )

    return UserStatsResponse(
        user_id=str(stats.user_id),
        total_corrections=stats.total_corrections,
        total_points=stats.total_points,
        current_streak=stats.current_streak,
        longest_streak=stats.longest_streak,
        weekly_corrections=stats.weekly_corrections,
        weekly_points=stats.weekly_points,
        monthly_corrections=stats.monthly_corrections,
        monthly_points=stats.monthly_points,
        weekly_rank=stats.weekly_rank,
        monthly_rank=stats.monthly_rank,
        accuracy_rate=stats.accuracy_rate,
        achievements=stats.achievements,
        recent_corrections=stats.recent_corrections,
        points_breakdown=stats.points_breakdown,
    )


# =============================================================================
# ACHIEVEMENTS ENDPOINTS
# =============================================================================


@router.get(
    "/achievements",
    summary="Achievements abrufen",
    description="Liefert alle verfügbaren und erreichten Achievements"
)
async def get_achievements(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ruft alle Achievements ab.

    Zeigt sowohl erreichte als auch noch nicht erreichte Achievements.
    """
    company_id = current_user.company_id
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firmenzuordnung"
        )

    service = get_feedback_service(db)
    stats = await service.get_user_stats(
        user_id=current_user.id,
        company_id=company_id,
    )

    # Alle Achievements mit Labels
    ALL_ACHIEVEMENTS = {
        "first_correction": {
            "name": "Erste Korrektur",
            "description": "Erste OCR-Korrektur eingereicht",
            "icon": "star",
        },
        "correction_10": {
            "name": "Fleissiger Korrektor",
            "description": "10 Korrekturen eingereicht",
            "icon": "edit",
        },
        "correction_50": {
            "name": "Korrektur-Experte",
            "description": "50 Korrekturen eingereicht",
            "icon": "award",
        },
        "correction_100": {
            "name": "Korrektur-Meister",
            "description": "100 Korrekturen eingereicht",
            "icon": "trophy",
        },
        "points_100": {
            "name": "Punktesammler",
            "description": "100 Punkte erreicht",
            "icon": "target",
        },
        "points_500": {
            "name": "Punkte-Profi",
            "description": "500 Punkte erreicht",
            "icon": "zap",
        },
        "points_1000": {
            "name": "Punkte-Champion",
            "description": "1000 Punkte erreicht",
            "icon": "crown",
        },
        "streak_3": {
            "name": "Drei-Tage-Streak",
            "description": "3 Tage in Folge korrigiert",
            "icon": "flame",
        },
        "streak_7": {
            "name": "Wochen-Streak",
            "description": "7 Tage in Folge korrigiert",
            "icon": "fire",
        },
        "streak_30": {
            "name": "Monats-Champion",
            "description": "30 Tage in Folge korrigiert",
            "icon": "diamond",
        },
    }

    unlocked = set(stats.achievements)

    achievements = [
        {
            "id": ach_id,
            "name": ach_data["name"],
            "description": ach_data["description"],
            "icon": ach_data["icon"],
            "unlocked": ach_id in unlocked,
        }
        for ach_id, ach_data in ALL_ACHIEVEMENTS.items()
    ]

    return {
        "total_achievements": len(ALL_ACHIEVEMENTS),
        "unlocked_count": len(unlocked),
        "achievements": achievements,
    }
