# -*- coding: utf-8 -*-
"""AI Mentor API - Proaktive Hilfe und personalisierte Tipps.

Stellt Endpoints bereit für:
- Kontextuelle Tipps basierend auf Seite
- Verhaltensmuster-Analyse
- Tipp-Praeferenzen
- Tipp verwerfen

Vision 2.0 - Feature #9 (Januar 2026)
"""

from typing import Optional, List, Dict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import User
from app.api.dependencies import get_current_active_user, get_current_company_id
from app.services.ai.mentor_service import (
    AIMentorService,
    get_mentor_service,
    Tip,
    BehaviorPattern,
    MentorPreferences,
    TipCategory,
    TipPriority,
    UserExperience,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ai/mentor", tags=["ai-mentor"])


# ==================== Schemas ====================


class TipResponse(BaseModel):
    """Tipp-Antwort Schema."""

    id: str = Field(..., description="Tipp-ID")
    title: str = Field(..., description="Tipp-Titel")
    content: str = Field(..., description="Tipp-Inhalt")
    category: str = Field(..., description="Kategorie: shortcut, automation, pattern, etc.")
    priority: str = Field(..., description="Prioritaet: low, medium, high")
    context_pages: List[str] = Field(default_factory=list, description="Relevante Seiten")
    action_url: Optional[str] = Field(None, description="URL für Aktion")
    action_label: Optional[str] = Field(None, description="Button-Text")
    shortcut: Optional[str] = Field(None, description="Keyboard-Shortcut")
    experience_level: str = Field(..., description="Erfahrungsstufe: beginner, intermediate, advanced")

    class Config:
        from_attributes = True


class TipsListResponse(BaseModel):
    """Liste von Tipps."""

    tips: List[TipResponse]
    total: int
    context_page: Optional[str] = None


class PatternResponse(BaseModel):
    """Verhaltensmuster-Antwort Schema."""

    id: str = Field(..., description="Muster-ID")
    pattern_type: str = Field(..., description="Muster-Typ")
    description: str = Field(..., description="Beschreibung auf Deutsch")
    frequency: int = Field(..., description="Häufigkeit des Musters")
    last_occurrence: str = Field(..., description="Letztes Auftreten (ISO)")
    recommendation: str = Field(..., description="Empfehlung")
    potential_savings_minutes: int = Field(0, description="Potenzielle Zeitersparnis in Minuten")


class PatternsListResponse(BaseModel):
    """Liste von Mustern."""

    patterns: List[PatternResponse]
    total: int
    analysis_days: int


class PreferencesResponse(BaseModel):
    """Praeferenzen-Antwort Schema."""

    enabled: bool = Field(True, description="Mentor aktiviert")
    show_shortcuts: bool = Field(True, description="Shortcut-Tipps anzeigen")
    show_automation_tips: bool = Field(True, description="Automatisierungs-Tipps anzeigen")
    show_pattern_insights: bool = Field(True, description="Muster-Insights anzeigen")
    experience_level: str = Field("beginner", description="Erfahrungsstufe")
    dismissed_tips_count: int = Field(0, description="Anzahl verworfener Tipps")
    max_tips_per_session: int = Field(5, description="Max Tipps pro Session")
    tip_frequency_hours: int = Field(24, description="Stunden zwischen Tipps")


class UpdatePreferencesRequest(BaseModel):
    """Request zum Aktualisieren der Praeferenzen."""

    enabled: Optional[bool] = None
    show_shortcuts: Optional[bool] = None
    show_automation_tips: Optional[bool] = None
    show_pattern_insights: Optional[bool] = None
    experience_level: Optional[str] = Field(
        None,
        description="beginner, intermediate, oder advanced"
    )
    max_tips_per_session: Optional[int] = Field(None, ge=1, le=10)
    tip_frequency_hours: Optional[int] = Field(None, ge=1, le=168)


class DismissTipRequest(BaseModel):
    """Request zum Verwerfen eines Tipps."""

    tip_id: str = Field(..., min_length=3, max_length=64, pattern=r'^[a-zA-Z][a-zA-Z0-9_-]+$')


class SuccessResponse(BaseModel):
    """Erfolgs-Antwort."""

    success: bool
    message: str


# ==================== Helper Functions ====================


def _tip_to_response(tip: Tip) -> TipResponse:
    """Konvertiert Tip zu TipResponse."""
    return TipResponse(
        id=tip.id,
        title=tip.title,
        content=tip.content,
        category=tip.category.value if isinstance(tip.category, TipCategory) else tip.category,
        priority=tip.priority.value if isinstance(tip.priority, TipPriority) else tip.priority,
        context_pages=tip.context_pages,
        action_url=tip.action_url,
        action_label=tip.action_label,
        shortcut=tip.shortcut,
        experience_level=tip.experience_level.value if isinstance(tip.experience_level, UserExperience) else tip.experience_level,
    )


def _pattern_to_response(pattern: BehaviorPattern) -> PatternResponse:
    """Konvertiert BehaviorPattern zu PatternResponse."""
    return PatternResponse(
        id=pattern.id,
        pattern_type=pattern.pattern_type,
        description=pattern.description,
        frequency=pattern.frequency,
        last_occurrence=pattern.last_occurrence.isoformat(),
        recommendation=pattern.recommendation,
        potential_savings_minutes=pattern.potential_savings_minutes,
    )


# ==================== Endpoints ====================


@router.get(
    "/tips",
    response_model=TipsListResponse,
    summary="Kontextuelle Tipps abrufen",
    description="Holt Tipps basierend auf der aktuellen Seite und Benutzer-Praeferenzen.",
)
async def get_tips(
    context_page: Optional[str] = Query(
        None,
        description="Aktuelle Seite (z.B. 'documents', 'validation')"
    ),
    max_tips: int = Query(3, ge=1, le=10, description="Maximale Anzahl Tipps"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TipsListResponse:
    """Holt kontextuelle Tipps für den aktuellen Benutzer."""
    service = await get_mentor_service(db)

    # Praeferenzen laden
    preferences = await service.get_mentor_preferences(current_user.id)

    # Tipps holen
    tips = await service.get_contextual_tips(
        user_id=current_user.id,
        context_page=context_page or "dashboard",
        preferences=preferences,
        max_tips=max_tips,
    )

    return TipsListResponse(
        tips=[_tip_to_response(t) for t in tips],
        total=len(tips),
        context_page=context_page,
    )


@router.get(
    "/tips/context/{context_page}",
    response_model=TipsListResponse,
    summary="Tipps für spezifischen Kontext",
    description="Holt Tipps für eine spezifische Seite.",
)
async def get_tips_by_context(
    context_page: str = Path(..., description="Seiten-Kontext"),
    max_tips: int = Query(3, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TipsListResponse:
    """Holt Tipps für eine spezifische Seite."""
    service = await get_mentor_service(db)
    preferences = await service.get_mentor_preferences(current_user.id)

    tips = await service.get_contextual_tips(
        user_id=current_user.id,
        context_page=context_page,
        preferences=preferences,
        max_tips=max_tips,
    )

    return TipsListResponse(
        tips=[_tip_to_response(t) for t in tips],
        total=len(tips),
        context_page=context_page,
    )


@router.get(
    "/tips/all",
    response_model=TipsListResponse,
    summary="Alle Tipps abrufen",
    description="Holt alle verfügbaren Tipps ohne Filterung.",
)
async def get_all_tips(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> TipsListResponse:
    """Holt alle verfügbaren Tipps."""
    service = await get_mentor_service(db)
    tips = await service.get_all_tips()

    return TipsListResponse(
        tips=[_tip_to_response(t) for t in tips],
        total=len(tips),
    )


@router.post(
    "/tips/{tip_id}/dismiss",
    response_model=SuccessResponse,
    summary="Tipp verwerfen",
    description="Markiert einen Tipp als verworfen. Wird nicht mehr angezeigt.",
)
async def dismiss_tip(
    tip_id: str = Path(..., min_length=3, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SuccessResponse:
    """Verwirft einen Tipp für den aktuellen Benutzer."""
    service = await get_mentor_service(db)

    success = await service.dismiss_tip(
        user_id=current_user.id,
        tip_id=tip_id,
    )

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Tipp konnte nicht verworfen werden. Ungültige Tipp-ID.",
        )

    return SuccessResponse(
        success=True,
        message=f"Tipp '{tip_id}' wurde verworfen.",
    )


@router.get(
    "/patterns",
    response_model=PatternsListResponse,
    summary="Verhaltensmuster analysieren",
    description="Analysiert das Benutzerverhalten und erkennt Muster.",
)
async def get_behavior_patterns(
    days: int = Query(7, ge=1, le=30, description="Analyse-Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company_id: Optional[UUID] = Depends(get_current_company_id),
) -> PatternsListResponse:
    """Analysiert Verhaltensmuster des Benutzers."""
    # SECURITY FIX: Multi-Tenant Check via get_current_company_id
    if not company_id:
        raise HTTPException(
            status_code=400,
            detail="Keine Firma zugeordnet.",
        )

    service = await get_mentor_service(db)

    patterns = await service.analyze_behavior_patterns(
        user_id=current_user.id,
        company_id=company_id,  # SECURITY FIX
        days=days,
    )

    return PatternsListResponse(
        patterns=[_pattern_to_response(p) for p in patterns],
        total=len(patterns),
        analysis_days=days,
    )


@router.get(
    "/preferences",
    response_model=PreferencesResponse,
    summary="Praeferenzen abrufen",
    description="Holt die Mentor-Praeferenzen des Benutzers.",
)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PreferencesResponse:
    """Holt die Mentor-Praeferenzen."""
    service = await get_mentor_service(db)
    prefs = await service.get_mentor_preferences(current_user.id)

    return PreferencesResponse(
        enabled=prefs.enabled,
        show_shortcuts=prefs.show_shortcuts,
        show_automation_tips=prefs.show_automation_tips,
        show_pattern_insights=prefs.show_pattern_insights,
        experience_level=prefs.experience_level.value,
        dismissed_tips_count=len(prefs.dismissed_tips),
        max_tips_per_session=prefs.max_tips_per_session,
        tip_frequency_hours=prefs.tip_frequency_hours,
    )


@router.patch(
    "/preferences",
    response_model=PreferencesResponse,
    summary="Praeferenzen aktualisieren",
    description="Aktualisiert die Mentor-Praeferenzen des Benutzers.",
)
async def update_preferences(
    request: UpdatePreferencesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> PreferencesResponse:
    """Aktualisiert die Mentor-Praeferenzen."""
    service = await get_mentor_service(db)

    # Nur gesetzte Werte übernehmen
    updates = {}
    if request.enabled is not None:
        updates["enabled"] = request.enabled
    if request.show_shortcuts is not None:
        updates["show_shortcuts"] = request.show_shortcuts
    if request.show_automation_tips is not None:
        updates["show_automation_tips"] = request.show_automation_tips
    if request.show_pattern_insights is not None:
        updates["show_pattern_insights"] = request.show_pattern_insights
    if request.experience_level is not None:
        # Validieren
        if request.experience_level not in ["beginner", "intermediate", "advanced"]:
            raise HTTPException(
                status_code=400,
                detail="Ungültiger Erfahrungslevel. Erlaubt: beginner, intermediate, advanced",
            )
        updates["experience_level"] = request.experience_level
    if request.max_tips_per_session is not None:
        updates["max_tips_per_session"] = request.max_tips_per_session
    if request.tip_frequency_hours is not None:
        updates["tip_frequency_hours"] = request.tip_frequency_hours

    prefs = await service.update_mentor_preferences(
        user_id=current_user.id,
        updates=updates,
    )

    return PreferencesResponse(
        enabled=prefs.enabled,
        show_shortcuts=prefs.show_shortcuts,
        show_automation_tips=prefs.show_automation_tips,
        show_pattern_insights=prefs.show_pattern_insights,
        experience_level=prefs.experience_level.value,
        dismissed_tips_count=len(prefs.dismissed_tips),
        max_tips_per_session=prefs.max_tips_per_session,
        tip_frequency_hours=prefs.tip_frequency_hours,
    )


@router.get(
    "/dismissed",
    response_model=List[str],
    summary="Verworfene Tipps abrufen",
    description="Holt die Liste der verworfenen Tipp-IDs.",
)
async def get_dismissed_tips(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[str]:
    """Holt die Liste der verworfenen Tipps."""
    service = await get_mentor_service(db)

    return await service.get_tip_history(
        user_id=current_user.id,
        limit=limit,
    )


@router.post(
    "/dismissed/restore/{tip_id}",
    response_model=SuccessResponse,
    summary="Verworfenen Tipp wiederherstellen",
    description="Stellt einen verworfenen Tipp wieder her.",
)
async def restore_dismissed_tip(
    tip_id: str = Path(..., min_length=3, max_length=64),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> SuccessResponse:
    """Stellt einen verworfenen Tipp wieder her."""
    from app.db.models import User as UserModel
    from sqlalchemy import select

    stmt = select(UserModel).where(UserModel.id == current_user.id)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    preferences = user.preferences or {}
    mentor_prefs = preferences.get("mentor", {})
    dismissed = set(mentor_prefs.get("dismissed_tips", []))

    if tip_id not in dismissed:
        return SuccessResponse(
            success=False,
            message=f"Tipp '{tip_id}' war nicht verworfen.",
        )

    dismissed.remove(tip_id)
    mentor_prefs["dismissed_tips"] = list(dismissed)
    preferences["mentor"] = mentor_prefs
    user.preferences = preferences

    await db.commit()

    logger.info(
        "tip_restored",
        user_id=str(current_user.id),
        tip_id=tip_id,
    )

    return SuccessResponse(
        success=True,
        message=f"Tipp '{tip_id}' wurde wiederhergestellt.",
    )
