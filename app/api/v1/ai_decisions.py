# -*- coding: utf-8 -*-
"""
AI Decision Explorer API - Explainable AI Entscheidungen.

Jede KI-Entscheidung ist:
- Transparent erklärt
- Mit Faktoren begründet
- Mit Alternativen versehen
- Durch Feedback verbesserbar

Vision 2026 Q2 - AI Decision Explorer UI API
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Union
from uuid import UUID

from app.core.types import JSONDict
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.db.models import User, AIDecision, Document
from app.core.german_messages import HTTPErrors
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ai-decisions", tags=["AI Decisions"])


# =============================================================================
# Schemas
# =============================================================================

class ExplanationFactorSchema(BaseModel):
    """Schema für einen Erklärungsfaktor."""
    name: str = Field(..., description="Name des Faktors")
    contribution: float = Field(..., description="Beitrag zur Entscheidung (0.0-1.0)")
    value: Optional[Union[str, int, float, bool]] = Field(None, description="Wert des Faktors")
    explanation: str = Field("", description="Erklärungstext")
    visualization_type: str = Field("bar", description="Visualisierungstyp")


class AlternativeSchema(BaseModel):
    """Schema für eine Alternative."""
    value: Union[str, int, float, bool] = Field(..., description="Alternativer Wert")
    confidence: float = Field(..., description="Confidence für diese Alternative")
    reason: str = Field("", description="Grund warum nicht gewählt")


class AIDecisionSchema(BaseModel):
    """Schema für eine AI-Entscheidung."""
    id: UUID
    document_id: Optional[UUID]
    decision_type: str
    decision_value: JSONDict
    confidence: float
    confidence_level: str
    explanation: JSONDict
    auto_applied: bool
    requires_review: bool
    is_final: bool
    user_feedback: Optional[str]
    user_correction: Optional[JSONDict]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class AIDecisionDetailSchema(AIDecisionSchema):
    """Detailansicht einer AI-Entscheidung."""
    factors: List[ExplanationFactorSchema] = []
    alternatives: List[AlternativeSchema] = []
    document_info: Optional[JSONDict] = None


class AIDecisionListResponse(BaseModel):
    """Response für Entscheidungsliste."""
    items: List[AIDecisionSchema]
    total: int
    page: int
    page_size: int
    has_more: bool


class FeedbackRequest(BaseModel):
    """Request für Benutzer-Feedback."""
    feedback_type: str = Field(
        ...,
        description="Typ: 'correct', 'incorrect', 'helpful', 'not_helpful'"
    )
    correction: Optional[JSONDict] = Field(
        None,
        description="Korrektur wenn 'incorrect'"
    )
    comment: Optional[str] = Field(None, description="Freitext-Kommentar")


class DecisionStatsSchema(BaseModel):
    """Schema für Entscheidungsstatistiken."""
    total_decisions: int
    auto_applied: int
    requires_review: int
    correct_feedback: int
    incorrect_feedback: int
    avg_confidence: float
    by_type: Dict[str, int]
    by_confidence_level: Dict[str, int]


class DecisionExplanationRequest(BaseModel):
    """Request für Entscheidungserklärung."""
    decision_type: str = Field(..., description="Typ der Entscheidung")
    context: JSONDict = Field(
        default_factory=dict,
        description="Kontext-Daten für Erklärung"
    )


class DecisionExplanationResponse(BaseModel):
    """Response mit detaillierter Erklärung."""
    headline: str
    summary: str
    main_reason: str
    factors: List[ExplanationFactorSchema]
    alternatives: List[AlternativeSchema]
    confidence_level: str
    confidence_percent: float
    confidence_reasoning: str
    suggested_next_steps: List[str]


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/", response_model=AIDecisionListResponse)
async def list_ai_decisions(
    page: int = Query(1, ge=1, description="Seitennummer"),
    page_size: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
    document_id: Optional[UUID] = Query(None, description="Filter nach Dokument"),
    decision_type: Optional[str] = Query(None, description="Filter nach Entscheidungstyp"),
    confidence_min: Optional[float] = Query(None, ge=0, le=1, description="Minimale Confidence"),
    requires_review: Optional[bool] = Query(None, description="Nur Review-Entscheidungen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AIDecisionListResponse:
    """
    Listet AI-Entscheidungen mit Filterung und Paginierung.

    Filter:
    - document_id: Entscheidungen für bestimmtes Dokument
    - decision_type: classify, categorize, extract, link_entity, etc.
    - confidence_min: Mindest-Confidence
    - requires_review: Nur zur Überprüfung markierte
    """
    # Query aufbauen
    conditions = [AIDecision.company_id == current_user.company_id]

    if document_id:
        conditions.append(AIDecision.document_id == document_id)
    if decision_type:
        conditions.append(AIDecision.decision_type == decision_type)
    if confidence_min is not None:
        conditions.append(AIDecision.confidence >= confidence_min)
    if requires_review is not None:
        conditions.append(AIDecision.requires_review == requires_review)

    # Count total
    count_stmt = select(func.count()).select_from(AIDecision).where(and_(*conditions))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginated query
    offset = (page - 1) * page_size
    stmt = (
        select(AIDecision)
        .where(and_(*conditions))
        .order_by(desc(AIDecision.created_at))
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(stmt)
    decisions = result.scalars().all()

    return AIDecisionListResponse(
        items=[AIDecisionSchema.model_validate(d) for d in decisions],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(decisions)) < total,
    )


@router.get("/stats", response_model=DecisionStatsSchema)
async def get_decision_stats(
    days: int = Query(30, ge=1, le=365, description="Zeitraum in Tagen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DecisionStatsSchema:
    """
    Liefert Statistiken zu AI-Entscheidungen.

    Umfasst:
    - Gesamtzahl Entscheidungen
    - Automatisch angewendet vs. Review
    - Feedback-Verteilung
    - Durchschnittliche Confidence
    - Verteilung nach Typ
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Basis-Query
    base_condition = and_(
        AIDecision.company_id == current_user.company_id,
        AIDecision.created_at >= cutoff_date,
    )

    # Total
    total_stmt = select(func.count()).select_from(AIDecision).where(base_condition)
    total_result = await db.execute(total_stmt)
    total = total_result.scalar() or 0

    # Auto-applied
    auto_stmt = select(func.count()).select_from(AIDecision).where(
        and_(base_condition, AIDecision.auto_applied == True)
    )
    auto_result = await db.execute(auto_stmt)
    auto_applied = auto_result.scalar() or 0

    # Requires review
    review_stmt = select(func.count()).select_from(AIDecision).where(
        and_(base_condition, AIDecision.requires_review == True)
    )
    review_result = await db.execute(review_stmt)
    requires_review = review_result.scalar() or 0

    # Feedback counts
    correct_stmt = select(func.count()).select_from(AIDecision).where(
        and_(base_condition, AIDecision.user_feedback == "correct")
    )
    correct_result = await db.execute(correct_stmt)
    correct_feedback = correct_result.scalar() or 0

    incorrect_stmt = select(func.count()).select_from(AIDecision).where(
        and_(base_condition, AIDecision.user_feedback == "incorrect")
    )
    incorrect_result = await db.execute(incorrect_stmt)
    incorrect_feedback = incorrect_result.scalar() or 0

    # Average confidence
    avg_stmt = select(func.avg(AIDecision.confidence)).where(base_condition)
    avg_result = await db.execute(avg_stmt)
    avg_confidence = float(avg_result.scalar() or 0)

    # By type
    type_stmt = (
        select(AIDecision.decision_type, func.count())
        .where(base_condition)
        .group_by(AIDecision.decision_type)
    )
    type_result = await db.execute(type_stmt)
    by_type = {row[0]: row[1] for row in type_result.fetchall()}

    # By confidence level
    level_stmt = (
        select(AIDecision.confidence_level, func.count())
        .where(base_condition)
        .group_by(AIDecision.confidence_level)
    )
    level_result = await db.execute(level_stmt)
    by_confidence_level = {row[0]: row[1] for row in level_result.fetchall()}

    return DecisionStatsSchema(
        total_decisions=total,
        auto_applied=auto_applied,
        requires_review=requires_review,
        correct_feedback=correct_feedback,
        incorrect_feedback=incorrect_feedback,
        avg_confidence=avg_confidence,
        by_type=by_type,
        by_confidence_level=by_confidence_level,
    )


@router.get("/{decision_id}", response_model=AIDecisionDetailSchema)
async def get_ai_decision(
    decision_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> AIDecisionDetailSchema:
    """
    Liefert detaillierte Informationen zu einer AI-Entscheidung.

    Enthält:
    - Vollständige Erklärung
    - Alle Faktoren mit Gewichtung
    - Betrachtete Alternativen
    - Dokument-Kontext
    """
    stmt = select(AIDecision).where(
        and_(
            AIDecision.id == decision_id,
            AIDecision.company_id == current_user.company_id,
        )
    )

    result = await db.execute(stmt)
    decision = result.scalars().first()

    if not decision:
        raise HTTPException(
            status_code=404,
            detail=HTTPErrors.DOCUMENT_NOT_FOUND,
        )

    # Basis-Schema
    detail = AIDecisionDetailSchema.model_validate(decision)

    # Faktoren aus Explanation extrahieren
    explanation = decision.explanation or {}
    if "factors" in explanation:
        detail.factors = [
            ExplanationFactorSchema(**f) for f in explanation["factors"]
        ]

    # Alternativen extrahieren
    if "alternatives" in explanation:
        detail.alternatives = [
            AlternativeSchema(**a) for a in explanation["alternatives"]
        ]

    # Dokument-Info laden
    if decision.document_id:
        doc_stmt = select(Document).where(Document.id == decision.document_id)
        doc_result = await db.execute(doc_stmt)
        doc = doc_result.scalars().first()

        if doc:
            detail.document_info = {
                "id": str(doc.id),
                "filename": doc.original_filename,
                "document_type": doc.document_type,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }

    return detail


@router.post("/{decision_id}/feedback")
async def submit_feedback(
    decision_id: UUID,
    feedback: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONDict:
    """
    Übermittelt Benutzer-Feedback zu einer AI-Entscheidung.

    Feedback-Typen:
    - correct: Entscheidung war richtig
    - incorrect: Entscheidung war falsch (mit Korrektur)
    - helpful: Erklärung war hilfreich
    - not_helpful: Erklärung war nicht hilfreich
    """
    stmt = select(AIDecision).where(
        and_(
            AIDecision.id == decision_id,
            AIDecision.company_id == current_user.company_id,
        )
    )

    result = await db.execute(stmt)
    decision = result.scalars().first()

    if not decision:
        raise HTTPException(
            status_code=404,
            detail=HTTPErrors.DOCUMENT_NOT_FOUND,
        )

    # Feedback speichern
    decision.user_feedback = feedback.feedback_type
    decision.feedback_at = datetime.now(timezone.utc)
    decision.feedback_by_id = current_user.id

    if feedback.correction:
        decision.user_correction = feedback.correction

    if feedback.comment:
        # Comment in explanation hinzufügen
        explanation = decision.explanation or {}
        explanation["user_comment"] = feedback.comment
        decision.explanation = explanation

    await db.commit()

    logger.info(
        "ai_decision_feedback_received",
        decision_id=str(decision_id),
        feedback_type=feedback.feedback_type,
        has_correction=bool(feedback.correction),
    )

    return {
        "status": "success",
        "message": "Feedback erfolgreich gespeichert",
        "decision_id": str(decision_id),
    }


@router.post("/{decision_id}/accept")
async def accept_decision(
    decision_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONDict:
    """
    Akzeptiert eine AI-Entscheidung (markiert als final).

    Setzt:
    - is_final = True
    - auto_applied = True
    - requires_review = False
    """
    stmt = select(AIDecision).where(
        and_(
            AIDecision.id == decision_id,
            AIDecision.company_id == current_user.company_id,
        )
    )

    result = await db.execute(stmt)
    decision = result.scalars().first()

    if not decision:
        raise HTTPException(
            status_code=404,
            detail=HTTPErrors.DOCUMENT_NOT_FOUND,
        )

    decision.is_final = True
    decision.auto_applied = True
    decision.requires_review = False
    decision.accepted_at = datetime.now(timezone.utc)
    decision.accepted_by_id = current_user.id

    await db.commit()

    logger.info(
        "ai_decision_accepted",
        decision_id=str(decision_id),
    )

    return {
        "status": "success",
        "message": "Entscheidung akzeptiert",
        "decision_id": str(decision_id),
    }


@router.post("/{decision_id}/reject")
async def reject_decision(
    decision_id: UUID,
    correction: Optional[JSONDict] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> JSONDict:
    """
    Lehnt eine AI-Entscheidung ab.

    Optional mit Korrektur, die für zukünftiges Lernen verwendet wird.
    """
    stmt = select(AIDecision).where(
        and_(
            AIDecision.id == decision_id,
            AIDecision.company_id == current_user.company_id,
        )
    )

    result = await db.execute(stmt)
    decision = result.scalars().first()

    if not decision:
        raise HTTPException(
            status_code=404,
            detail=HTTPErrors.DOCUMENT_NOT_FOUND,
        )

    decision.is_final = True
    decision.auto_applied = False
    decision.user_feedback = "incorrect"
    decision.rejected_at = datetime.now(timezone.utc)
    decision.rejected_by_id = current_user.id

    if correction:
        decision.user_correction = correction

    await db.commit()

    logger.info(
        "ai_decision_rejected",
        decision_id=str(decision_id),
        has_correction=bool(correction),
    )

    return {
        "status": "success",
        "message": "Entscheidung abgelehnt",
        "decision_id": str(decision_id),
    }


@router.post("/explain", response_model=DecisionExplanationResponse)
async def explain_decision(
    request: DecisionExplanationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> DecisionExplanationResponse:
    """
    Generiert eine detaillierte Erklärung für einen Entscheidungstyp.

    Nutzt den ExplainabilityService um menschenlesbare Erklärungen
    mit Faktoren und Alternativen zu generieren.
    """
    from app.services.orchestration.explainability_service import (
        get_explainability_service,
    )

    explainability = get_explainability_service()

    try:
        if request.decision_type == "health_score":
            explanation = await explainability.explain_health_score(request.context)
        elif request.decision_type == "early_warning":
            explanation = await explainability.explain_early_warning(request.context)
        elif request.decision_type == "recommendation":
            explanation = await explainability.explain_recommendation(
                request.context.get("id") or UUID("00000000-0000-0000-0000-000000000000"),
                request.context,
            )
        else:
            # Generische Erklärung
            explanation = await explainability._explain_generic(request.context)

        return DecisionExplanationResponse(
            headline=explanation.headline,
            summary=explanation.summary,
            main_reason=explanation.main_reason,
            factors=[
                ExplanationFactorSchema(
                    name=f.name,
                    contribution=f.impact_weight,
                    value=f.current_value,
                    explanation=f.description,
                    visualization_type=f.visualization_type,
                )
                for f in explanation.factors
            ],
            alternatives=[
                AlternativeSchema(
                    value=a.name,
                    confidence=a.estimated_impact,
                    reason=a.why_not_chosen,
                )
                for a in explanation.alternatives
            ],
            confidence_level=explanation.confidence_level.value,
            confidence_percent=explanation.confidence_percent,
            confidence_reasoning=explanation.confidence_reasoning,
            suggested_next_steps=explanation.suggested_next_steps,
        )

    except Exception as e:
        logger.error("explain_decision_error", **safe_error_log(e))
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(e, "KI-Erklärung"),
        )


@router.get("/document/{document_id}", response_model=List[AIDecisionSchema])
async def get_document_decisions(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> List[AIDecisionSchema]:
    """
    Listet alle AI-Entscheidungen für ein bestimmtes Dokument.

    Zeigt die komplette Entscheidungshistorie inkl. Klassifikation,
    Entity-Linking, Kategorisierung, etc.
    """
    stmt = (
        select(AIDecision)
        .where(
            and_(
                AIDecision.document_id == document_id,
                AIDecision.company_id == current_user.company_id,
            )
        )
        .order_by(AIDecision.created_at.asc())
    )

    result = await db.execute(stmt)
    decisions = result.scalars().all()

    return [AIDecisionSchema.model_validate(d) for d in decisions]


# Import für timedelta
from datetime import timedelta
