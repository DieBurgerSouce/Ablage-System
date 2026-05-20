# -*- coding: utf-8 -*-
"""
Zero-Touch OCR API Endpoints.

Automatisierte OCR-Verarbeitung mit intelligentem Auto-Processing:
- Dokument durch vollautomatische Pipeline verarbeiten
- Confidence-basierte Entscheidungen (Auto-Process vs. Review)
- Batch-Verarbeitung mehrerer Dokumente
- Review-Queue für niedrige Confidence
- Schwellwert-Verwaltung (Admin)

Feinpoliert und durchdacht - Deutsche Geschäftsdokumente.
"""

from typing import Optional, List, Dict
from uuid import UUID

from app.core.types import JSONDict
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/zero-touch", tags=["Zero-Touch OCR"])


# =============================================================================
# HELPER DEPENDENCIES
# =============================================================================


async def get_company_id(
    current_user: User = Depends(get_current_active_user)
) -> UUID:
    """
    Dependency: Extrahiere Company-ID vom aktuellen User.

    Raises:
        HTTPException: Falls User keine Company zugewiesen hat
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Firma zugewiesen"
        )
    return current_user.company_id


async def require_admin(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """
    Dependency: Prüfe ob User Admin ist.

    Raises:
        HTTPException: Falls User kein Admin
    """
    if not current_user.is_superuser and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren duerfen diese Aktion ausführen"
        )
    return current_user


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class ZeroTouchProcessRequest(BaseModel):
    """Request für einzelnes Dokument."""

    document_id: UUID = Field(..., description="UUID des zu verarbeitenden Dokuments")

    model_config = ConfigDict(from_attributes=True)


class ZeroTouchBatchRequest(BaseModel):
    """Request für Batch-Verarbeitung."""

    document_ids: List[UUID] = Field(
        ...,
        max_length=100,
        description="Liste von Dokument-UUIDs (max 100)"
    )

    @field_validator("document_ids")
    @classmethod
    def validate_unique_ids(cls, v: List[UUID]) -> List[UUID]:
        """Prüfe auf Duplikate."""
        if len(v) != len(set(v)):
            raise ValueError("Duplikate in document_ids nicht erlaubt")
        return v

    model_config = ConfigDict(from_attributes=True)


class ZeroTouchBatchResponse(BaseModel):
    """Response für Batch-Verarbeitung."""

    queued: int = Field(..., description="Anzahl erfolgreich eingereihter Dokumente")
    errors: List[JSONDict] = Field(
        default_factory=list,
        description="Fehler bei einzelnen Dokumenten"
    )
    task_ids: List[str] = Field(
        default_factory=list,
        description="Celery Task-IDs für Batch-Jobs"
    )

    model_config = ConfigDict(from_attributes=True)


class ZeroTouchResultResponse(BaseModel):
    """Response für Zero-Touch Ergebnis."""

    id: UUID = Field(..., description="UUID des Zero-Touch Results")
    document_id: UUID = Field(..., description="Verknüpftes Dokument")

    # Confidence-Scores
    ocr_confidence: float = Field(..., ge=0.0, le=1.0, description="OCR Confidence")
    classification_type: Optional[str] = Field(None, description="Erkannter Dokumenttyp")
    classification_confidence: float = Field(..., ge=0.0, le=1.0, description="Klassifikations-Confidence")
    extraction_confidence: float = Field(..., ge=0.0, le=1.0, description="Extraktions-Confidence")
    overall_confidence: float = Field(..., ge=0.0, le=1.0, description="Gesamte Confidence")

    # Entity-Zuordnung
    entity_id: Optional[UUID] = Field(None, description="Verknüpfte Business-Entity")
    entity_match_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Status
    auto_processed: bool = Field(..., description="Wurde automatisch verarbeitet")
    requires_review: bool = Field(..., description="Benötigt manuelle Review")
    review_completed: bool = Field(default=False, description="Review abgeschlossen")

    # Business Objects
    business_object_type: Optional[str] = Field(None, description="Erzeugter Business-Objekt-Typ")
    business_object_id: Optional[UUID] = Field(None, description="Business-Objekt-ID")

    # Performance
    total_processing_ms: int = Field(..., description="Gesamte Verarbeitungszeit in ms")

    # Extrahierte Felder
    extracted_fields: JSONDict = Field(
        default_factory=dict,
        description="Extrahierte Felder (JSON)"
    )

    # Timestamps
    created_at: datetime
    updated_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)


class ZeroTouchStatsResponse(BaseModel):
    """Statistiken für Company."""

    total_processed: int = Field(..., description="Gesamt verarbeitete Dokumente")
    auto_processed: int = Field(..., description="Automatisch verarbeitet (kein Review)")
    manual_review: int = Field(..., description="Manuelle Review erforderlich")
    auto_rate: float = Field(..., ge=0.0, le=1.0, description="Auto-Processing Rate")

    avg_confidence: float = Field(..., ge=0.0, le=1.0, description="Durchschnittliche Confidence")
    avg_processing_ms: int = Field(..., description="Durchschnittliche Verarbeitungszeit")

    by_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Verteilung nach Dokumenttyp"
    )
    by_status: Dict[str, int] = Field(
        default_factory=dict,
        description="Verteilung nach Status"
    )

    last_24h: Dict[str, int] = Field(
        default_factory=dict,
        description="Statistiken der letzten 24 Stunden"
    )

    model_config = ConfigDict(from_attributes=True)


class ZeroTouchReviewRequest(BaseModel):
    """Request für Review-Submission."""

    approved: bool = Field(..., description="Ergebnis genehmigt oder abgelehnt")
    corrections: Optional[JSONDict] = Field(
        None,
        description="Korrekturen an extrahierten Feldern"
    )
    comment: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optionaler Kommentar"
    )

    model_config = ConfigDict(from_attributes=True)


class ZeroTouchThresholdRequest(BaseModel):
    """Request für Schwellwert-Anpassung (Admin)."""

    auto_process_threshold: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="Minimum Confidence für Auto-Processing"
    )
    review_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum Confidence für Review (darunter: Ablehnung)"
    )

    @field_validator("review_threshold")
    @classmethod
    def validate_threshold_order(cls, v: float, info) -> float:
        """Prüfe dass review_threshold < auto_process_threshold."""
        auto_threshold = info.data.get("auto_process_threshold", 0.90)
        if v >= auto_threshold:
            raise ValueError(
                "review_threshold muss kleiner als auto_process_threshold sein"
            )
        return v

    model_config = ConfigDict(from_attributes=True)


class ZeroTouchThresholdResponse(BaseModel):
    """Response für Schwellwert-Update."""

    success: bool
    thresholds: Dict[str, float] = Field(
        ...,
        description="Aktualisierte Schwellwerte"
    )
    message: str

    model_config = ConfigDict(from_attributes=True)


class PendingReviewResponse(BaseModel):
    """Response für Pending-Review Liste."""

    total: int = Field(..., description="Gesamtanzahl pending reviews")
    items: List[ZeroTouchResultResponse]
    page: int
    per_page: int
    has_more: bool

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# API ENDPOINTS
# =============================================================================


@router.post(
    "/process",
    response_model=ZeroTouchResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Dokument durch Zero-Touch Pipeline verarbeiten",
    description="""
    Verarbeitet ein einzelnes Dokument durch die vollautomatische Zero-Touch Pipeline:

    1. OCR-Verarbeitung mit bestem verfügbaren Backend
    2. Dokumentklassifikation
    3. Metadaten-Extraktion
    4. Entity-Matching
    5. Confidence-basierte Entscheidung:
       - >= auto_process_threshold: Automatisch in Workflow einfuegen
       - >= review_threshold: Manuelle Review erforderlich
       - < review_threshold: Ablehnung

    Erfordert Authentifizierung und Company-Zuordnung.
    """
)
async def process_document(
    request: ZeroTouchProcessRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
) -> ZeroTouchResultResponse:
    """Verarbeite einzelnes Dokument."""
    try:
        # Import hier um zirkuläre Abhängigkeiten zu vermeiden
        from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator

        orchestrator = ZeroTouchOrchestrator()

        result = await orchestrator.process_document(
            document_id=request.document_id,
            company_id=company_id,
            db=db,
        )

        logger.info(
            "zero_touch_processing_completed",
            document_id=str(request.document_id),
            user_id=str(current_user.id),
            auto_processed=result.auto_processed,
            confidence=result.overall_confidence,
        )

        return ZeroTouchResultResponse.model_validate(result)

    except ValueError as e:
        logger.warning(
            "zero_touch_validation_error",
            document_id=str(request.document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Vorgang")
        )
    except PermissionError as e:
        logger.warning(
            "zero_touch_permission_denied",
            document_id=str(request.document_id),
            user_id=str(current_user.id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für dieses Dokument"
        )
    except Exception as e:
        logger.error(
            "zero_touch_processing_failed",
            document_id=str(request.document_id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei Zero-Touch Verarbeitung"
        )


@router.post(
    "/batch",
    response_model=ZeroTouchBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Batch-Verarbeitung mehrerer Dokumente",
    description="""
    Verarbeitet mehrere Dokumente asynchron durch die Zero-Touch Pipeline.

    Die Verarbeitung erfolgt im Hintergrund via Celery.
    Maximale Batch-Größe: 100 Dokumente.

    Returns Celery Task-IDs für Status-Tracking.
    """
)
async def process_batch(
    request: ZeroTouchBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
) -> ZeroTouchBatchResponse:
    """Batch-Verarbeitung."""
    try:
        # Import hier um zirkuläre Abhängigkeiten zu vermeiden
        from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator

        orchestrator = ZeroTouchOrchestrator()

        result = await orchestrator.process_batch(
            document_ids=request.document_ids,
            user_id=current_user.id,
            company_id=company_id,
        )

        logger.info(
            "zero_touch_batch_queued",
            batch_size=len(request.document_ids),
            queued=result["queued"],
            errors=len(result["errors"]),
            user_id=str(current_user.id),
        )

        return ZeroTouchBatchResponse(
            queued=result["queued"],
            errors=result["errors"],
            task_ids=result.get("task_ids", []),
        )

    except Exception as e:
        logger.error(
            "zero_touch_batch_failed",
            batch_size=len(request.document_ids),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler bei Batch-Verarbeitung"
        )


@router.get(
    "/result/{document_id}",
    response_model=ZeroTouchResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Zero-Touch Ergebnis abrufen",
    description="Ruft das Zero-Touch Verarbeitungsergebnis für ein Dokument ab."
)
async def get_result(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
) -> ZeroTouchResultResponse:
    """Ergebnis abrufen."""
    try:
        from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator

        orchestrator = ZeroTouchOrchestrator()

        result = await orchestrator.get_result(
            document_id=document_id,
            company_id=company_id,
            db=db,
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Kein Zero-Touch Ergebnis für dieses Dokument gefunden"
            )

        return ZeroTouchResultResponse.model_validate(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "zero_touch_result_fetch_failed",
            document_id=str(document_id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen des Ergebnisses"
        )


@router.get(
    "/stats",
    response_model=ZeroTouchStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Statistiken abrufen",
    description="Ruft Zero-Touch Statistiken für die Company ab."
)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
) -> ZeroTouchStatsResponse:
    """Statistiken abrufen."""
    try:
        from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator

        orchestrator = ZeroTouchOrchestrator()

        stats = await orchestrator.get_stats(company_id=company_id, db=db)

        return ZeroTouchStatsResponse(**stats)

    except Exception as e:
        logger.error(
            "zero_touch_stats_failed",
            company_id=str(company_id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Statistiken"
        )


@router.patch(
    "/thresholds",
    response_model=ZeroTouchThresholdResponse,
    status_code=status.HTTP_200_OK,
    summary="Schwellwerte anpassen (Admin)",
    description="""
    Passt die Auto-Processing und Review Schwellwerte an.

    Nur für Administratoren.

    - auto_process_threshold: Minimum Confidence für automatische Verarbeitung
    - review_threshold: Minimum Confidence für manuelle Review
    """
)
async def update_thresholds(
    request: ZeroTouchThresholdRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    company_id: UUID = Depends(get_company_id),
) -> ZeroTouchThresholdResponse:
    """Schwellwerte anpassen."""
    try:
        from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator

        orchestrator = ZeroTouchOrchestrator()

        await orchestrator.update_thresholds(
            company_id=company_id,
            thresholds={
                "auto_process_threshold": request.auto_process_threshold,
                "review_threshold": request.review_threshold,
            },
            db=db,
        )

        logger.info(
            "zero_touch_thresholds_updated",
            company_id=str(company_id),
            auto_process=request.auto_process_threshold,
            review=request.review_threshold,
            admin_id=str(current_user.id),
        )

        return ZeroTouchThresholdResponse(
            success=True,
            thresholds={
                "auto_process_threshold": request.auto_process_threshold,
                "review_threshold": request.review_threshold,
            },
            message="Schwellwerte erfolgreich aktualisiert",
        )

    except Exception as e:
        logger.error(
            "zero_touch_threshold_update_failed",
            company_id=str(company_id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der Schwellwerte"
        )


@router.get(
    "/pending-review",
    response_model=PendingReviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Dokumente mit ausstehender Review",
    description="Ruft alle Dokumente ab, die eine manuelle Review benötigen."
)
async def get_pending_review(
    page: int = Query(default=1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(default=20, ge=1, le=100, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
) -> PendingReviewResponse:
    """Pending Reviews abrufen."""
    try:
        from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator

        orchestrator = ZeroTouchOrchestrator()

        result = await orchestrator.get_pending_reviews(
            company_id=company_id,
            limit=per_page,
            offset=(page - 1) * per_page,
        )

        return PendingReviewResponse(
            total=result["total"],
            items=[ZeroTouchResultResponse.model_validate(r) for r in result["items"]],
            page=page,
            per_page=per_page,
            has_more=result["has_more"],
        )

    except Exception as e:
        logger.error(
            "zero_touch_pending_review_failed",
            company_id=str(company_id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der ausstehenden Reviews"
        )


@router.post(
    "/{document_id}/review",
    response_model=ZeroTouchResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Review absenden",
    description="""
    Sendet eine Review für ein Zero-Touch Ergebnis ab.

    Der Reviewer kann:
    - Das Ergebnis genehmigen (approved=true)
    - Das Ergebnis ablehnen (approved=false)
    - Korrekturen an extrahierten Feldern vornehmen
    - Einen Kommentar hinterlassen

    Nach der Review wird das Dokument entsprechend verarbeitet oder verworfen.
    """
)
async def submit_review(
    document_id: UUID,
    request: ZeroTouchReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_company_id),
) -> ZeroTouchResultResponse:
    """Review absenden."""
    try:
        from app.services.zero_touch.zero_touch_orchestrator import ZeroTouchOrchestrator


        orchestrator = ZeroTouchOrchestrator()

        result = await orchestrator.submit_review(
            document_id=document_id,
            company_id=company_id,
            reviewer_id=current_user.id,
            approved=request.approved,
            corrections=request.corrections,
            comment=request.comment,
        )

        logger.info(
            "zero_touch_review_submitted",
            document_id=str(document_id),
            reviewer_id=str(current_user.id),
            approved=request.approved,
            has_corrections=bool(request.corrections),
        )

        return ZeroTouchResultResponse.model_validate(result)

    except ValueError as e:
        logger.warning(
            "zero_touch_review_validation_error",
            document_id=str(document_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Vorgang")
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für dieses Dokument"
        )
    except Exception as e:
        logger.error(
            "zero_touch_review_failed",
            document_id=str(document_id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Absenden der Review"
        )
