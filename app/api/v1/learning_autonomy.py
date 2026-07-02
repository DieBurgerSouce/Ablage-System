# -*- coding: utf-8 -*-
"""
Learning Autonomy API endpoints for Ablage-System.

Zentrale API für lernende Autonomie:
- Autonomie-Level pro User x Aktionstyp abrufen
- Bestätigungen, Ablehnungen, Korrekturen aufzeichnen
- Autonomie-Level manuell setzen
- Vertrauenskurve abrufen

Feinpoliert und durchdacht - Enterprise-grade Learning System.
"""

from typing import Dict, List, Optional
from uuid import UUID

from app.core.types import JSONDict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_active_user,
    get_db,
    get_user_company_id_dep,
)
from app.db.models import User
from app.db.models_learning_autonomy import (
    ActionType,
    LearningAutonomyLevel,
)
from app.services.ai.learning_autonomy_service import (
    LearningAutonomyService,
    get_learning_autonomy_service,
)

router = APIRouter(prefix="/learning-autonomy", tags=["Lernende Autonomie"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class AutonomyLevelResponse(BaseModel):
    """Response schema for a single autonomy level."""
    action_type: str
    current_level: str
    is_manually_set: bool
    total_suggestions: int
    total_confirmations: int
    total_rejections: int
    current_streak: int
    best_streak: int
    avg_confidence: float
    confirmation_rate: float

    model_config = ConfigDict(from_attributes=True)


class AllLevelsResponse(BaseModel):
    """Response schema for all autonomy levels."""
    levels: List[Dict]


class ConfirmationRequest(BaseModel):
    """Request schema for recording a confirmation."""
    action_type: str = Field(..., min_length=1, max_length=50)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    document_id: Optional[UUID] = None
    suggested_value: Optional[str] = None


class RejectionRequest(BaseModel):
    """Request schema for recording a rejection."""
    action_type: str = Field(..., min_length=1, max_length=50)
    document_id: Optional[UUID] = None
    suggested_value: Optional[str] = None


class CorrectionRequest(BaseModel):
    """Request schema for recording a correction."""
    action_type: str = Field(..., min_length=1, max_length=50)
    suggested_value: str = Field(..., min_length=1)
    corrected_value: str = Field(..., min_length=1)
    document_id: Optional[UUID] = None


class UndoRequest(BaseModel):
    """Request schema for recording an undo."""
    action_type: str = Field(..., min_length=1, max_length=50)
    document_id: Optional[UUID] = None


class SetLevelRequest(BaseModel):
    """Request schema for manually setting a level."""
    new_level: LearningAutonomyLevel


class ActionResultResponse(BaseModel):
    """Response schema for confirmation/rejection/correction actions."""
    level_changed: bool
    current_level: str
    current_streak: Optional[int] = None
    total_confirmations: Optional[int] = None
    total_rejections: Optional[int] = None
    total_corrections: Optional[int] = None
    total_undone: Optional[int] = None


class SetLevelResponse(BaseModel):
    """Response schema for manual level setting."""
    old_level: str
    new_level: str
    is_manually_set: bool


class TrustCurveDataPoint(BaseModel):
    """Single data point in trust curve."""
    timestamp: Optional[str]
    action: str
    level: str
    confidence: Optional[float]


class TrustCurveResponse(BaseModel):
    """Response schema for trust curve."""
    action_type: str
    data: List[TrustCurveDataPoint]


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/levels", response_model=AllLevelsResponse)
async def get_all_autonomy_levels(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> AllLevelsResponse:
    """
    Alle Autonomie-Level des aktuellen Users abrufen.

    Returns:
        Liste aller Autonomie-Level pro Aktionstyp
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    levels = await service.get_all_levels(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
    )

    return AllLevelsResponse(levels=levels)


@router.get("/levels/{action_type}", response_model=Dict)
async def get_autonomy_level(
    action_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> Dict:
    """
    Autonomie-Level für eine bestimmte Aktion abrufen.

    Args:
        action_type: Aktionstyp (z.B. "kategorisierung", "ordner_zuweisung")

    Returns:
        Aktuelles Autonomie-Level
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    level = await service.get_autonomy_level(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        action_type=action_type,
    )

    return {
        "action_type": action_type,
        "current_level": level.value,
    }


@router.post("/confirm", response_model=ActionResultResponse)
async def record_confirmation(
    request: ConfirmationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ActionResultResponse:
    """
    Bestätigung eines Vorschlags aufzeichnen.

    Erhöht den Streak und prüft ob ein Level-Upgrade fällig ist.

    Args:
        request: Bestätigungs-Details

    Returns:
        Ergebnis der Bestätigung mit Level-Änderungs-Status
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    result = await service.record_confirmation(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        action_type=request.action_type,
        confidence=request.confidence,
        document_id=request.document_id,
        suggested_value=request.suggested_value,
    )

    await db.commit()

    return ActionResultResponse(**result)


@router.post("/reject", response_model=ActionResultResponse)
async def record_rejection(
    request: RejectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ActionResultResponse:
    """
    Ablehnung eines Vorschlags aufzeichnen.

    Setzt den Streak zurück und prüft ob ein Level-Downgrade nötig ist.

    Args:
        request: Ablehnungs-Details

    Returns:
        Ergebnis der Ablehnung mit Level-Änderungs-Status
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    result = await service.record_rejection(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        action_type=request.action_type,
        document_id=request.document_id,
        suggested_value=request.suggested_value,
    )

    await db.commit()

    return ActionResultResponse(**result)


@router.post("/correct", response_model=ActionResultResponse)
async def record_correction(
    request: CorrectionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ActionResultResponse:
    """
    Korrektur eines Vorschlags aufzeichnen.

    Zaehlt als Teilbestätigung (Richtung stimmte, Details nicht).

    Args:
        request: Korrektur-Details

    Returns:
        Ergebnis der Korrektur
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    result = await service.record_correction(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        action_type=request.action_type,
        suggested_value=request.suggested_value,
        corrected_value=request.corrected_value,
        document_id=request.document_id,
    )

    await db.commit()

    return ActionResultResponse(**result)


@router.post("/undo", response_model=ActionResultResponse)
async def record_undo(
    request: UndoRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ActionResultResponse:
    """
    Undo einer automatischen Ausführung aufzeichnen.

    Zu viele Undos führen zu Level-Downgrade.

    Args:
        request: Undo-Details

    Returns:
        Ergebnis des Undos mit Level-Änderungs-Status
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    result = await service.record_undo(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        action_type=request.action_type,
        document_id=request.document_id,
    )

    await db.commit()

    return ActionResultResponse(**result)


@router.put("/levels/{action_type}", response_model=SetLevelResponse)
async def set_level_manually(
    action_type: str,
    request: SetLevelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> SetLevelResponse:
    """
    Autonomie-Level für eine Aktion manuell setzen.

    Erlaubt dem User das Level für eine spezifische Aktion
    manuell zu überschreiben (z.B. sofort auf full_auto setzen).

    Args:
        action_type: Aktionstyp
        request: Neues Level

    Returns:
        Altes und neues Level
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    result = await service.set_level_manually(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        action_type=action_type,
        new_level=request.new_level.value,
    )

    await db.commit()

    return SetLevelResponse(**result)


@router.get("/trust-curve/{action_type}", response_model=TrustCurveResponse)
async def get_trust_curve(
    action_type: str,
    limit: int = Query(100, ge=1, le=1000, description="Anzahl der letzten Entscheidungen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> TrustCurveResponse:
    """
    Vertrauenskurve für eine Aktion abrufen.

    Liefert eine Zeitreihe aller Entscheidungen für die Visualisierung
    des Lernfortschritts und der Vertrauensentwicklung.

    Args:
        action_type: Aktionstyp
        limit: Anzahl der letzten Entscheidungen (default: 100)

    Returns:
        Liste von Datenpunkten mit Zeitstempel, Aktion, Level, Confidence
    """
    service: LearningAutonomyService = get_learning_autonomy_service()

    data_points = await service.get_trust_curve(
        db=db,
        user_id=current_user.id,
        company_id=company_id,
        action_type=action_type,
        limit=limit,
    )

    return TrustCurveResponse(
        action_type=action_type,
        data=[TrustCurveDataPoint(**point) for point in data_points],
    )
