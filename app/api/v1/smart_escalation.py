# -*- coding: utf-8 -*-
"""
API Endpoints fuer SmartEscalationService.

KI-gestuetzte intelligente Aufgabenzuweisung:
- Empfehlungen fuer optimale Zuweisung
- Team-Auslastung anzeigen
- User-Scores debuggen/analysieren

Phase 2.3 der Feature-Roadmap (Januar 2026)
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.middleware.company_context import require_company
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User, Company
from app.services.collaboration.smart_escalation_service import (
    AssignmentFactor,
    AssignmentRecommendation,
    CandidateScore,
    FactorWeights,
    get_smart_escalation_service,
)

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/smart-escalation", tags=["Smart Escalation"])


# ============================================================================
# Schemas
# ============================================================================


class FactorWeightsRequest(BaseModel):
    """Benutzerdefinierte Gewichtung der Faktoren."""

    expertise: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Gewicht fuer Expertise (0-1)",
    )
    workload: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Gewicht fuer Auslastung (0-1)",
    )
    availability: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
        description="Gewicht fuer Verfuegbarkeit (0-1)",
    )
    relationship: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Gewicht fuer Kundenbeziehung (0-1)",
    )

    def to_factor_weights(self) -> FactorWeights:
        """Konvertiert zu FactorWeights."""
        return FactorWeights(
            expertise=self.expertise,
            workload=self.workload,
            availability=self.availability,
            relationship=self.relationship,
        )

    def validate_sum(self) -> bool:
        """Validiert dass Summe ~1.0 ist."""
        total = self.expertise + self.workload + self.availability + self.relationship
        return abs(total - 1.0) < 0.01


class CandidateScoreResponse(BaseModel):
    """Score-Details eines Kandidaten."""

    user_id: str
    user_email: str
    user_name: str

    expertise_score: float = Field(ge=0, le=100)
    workload_score: float = Field(ge=0, le=100)
    availability_score: float = Field(ge=0, le=100)
    relationship_score: float = Field(ge=0, le=100)
    total_score: float = Field(ge=0, le=100)

    expertise_details: Dict[str, Any] = Field(default_factory=dict)
    workload_details: Dict[str, Any] = Field(default_factory=dict)
    availability_details: Dict[str, Any] = Field(default_factory=dict)
    relationship_details: Dict[str, Any] = Field(default_factory=dict)

    is_available: bool = True
    unavailability_reason: Optional[str] = None

    @classmethod
    def from_domain(cls, score: CandidateScore) -> "CandidateScoreResponse":
        """Konvertiere Domain-Objekt zu Response."""
        return cls(
            user_id=str(score.user_id),
            user_email=score.user_email,
            user_name=score.user_name,
            expertise_score=round(score.expertise_score, 1),
            workload_score=round(score.workload_score, 1),
            availability_score=round(score.availability_score, 1),
            relationship_score=round(score.relationship_score, 1),
            total_score=round(score.total_score, 1),
            expertise_details=score.expertise_details,
            workload_details=score.workload_details,
            availability_details=score.availability_details,
            relationship_details=score.relationship_details,
            is_available=score.is_available,
            unavailability_reason=score.unavailability_reason,
        )


class AssignmentRecommendationResponse(BaseModel):
    """Empfehlung fuer Aufgabenzuweisung."""

    recommended_user_id: str
    recommended_user_name: str
    confidence: float = Field(ge=0, le=100, description="Konfidenz der Empfehlung")

    candidates: List[CandidateScoreResponse]

    factors_used: List[str]
    weights_used: Dict[str, float]

    explanation: str
    explanation_details: Dict[str, Any]

    @classmethod
    def from_domain(cls, rec: AssignmentRecommendation) -> "AssignmentRecommendationResponse":
        """Konvertiere Domain-Objekt zu Response."""
        return cls(
            recommended_user_id=str(rec.recommended_user_id),
            recommended_user_name=rec.recommended_user_name,
            confidence=round(rec.confidence, 1),
            candidates=[CandidateScoreResponse.from_domain(c) for c in rec.candidates],
            factors_used=[f.value for f in rec.factors_used],
            weights_used={
                "expertise": rec.weights_used.expertise,
                "workload": rec.weights_used.workload,
                "availability": rec.weights_used.availability,
                "relationship": rec.weights_used.relationship,
            },
            explanation=rec.explanation,
            explanation_details=rec.explanation_details,
        )


class TeamMemberWorkload(BaseModel):
    """Auslastung eines Team-Mitglieds."""

    user_id: str
    user_name: str
    open_items: int
    workload_score: float
    is_available: bool
    availability_score: float


class TeamWorkloadResponse(BaseModel):
    """Team-Auslastungsuebersicht."""

    team_members: List[TeamMemberWorkload]
    total_open_items: int
    available_members: int
    total_members: int
    avg_items_per_member: float


class AssignmentRequest(BaseModel):
    """Request fuer Zuweisungsempfehlung."""

    document_id: Optional[str] = Field(
        default=None,
        description="Dokument-ID fuer Kontext",
    )
    document_type: Optional[str] = Field(
        default=None,
        description="Dokumenttyp fuer Expertise-Matching",
    )
    entity_id: Optional[str] = Field(
        default=None,
        description="Entity-ID fuer Relationship-Matching",
    )
    task_type: Optional[str] = Field(
        default=None,
        description="Aufgabentyp (validation, review, etc.)",
    )
    exclude_user_ids: Optional[List[str]] = Field(
        default=None,
        description="User-IDs die ausgeschlossen werden sollen",
    )
    weights: Optional[FactorWeightsRequest] = Field(
        default=None,
        description="Benutzerdefinierte Gewichtung",
    )
    max_candidates: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximale Anzahl Kandidaten",
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/recommend",
    response_model=AssignmentRecommendationResponse,
    summary="Zuweisungsempfehlung holen",
    description="Ermittelt die beste Zuweisung fuer eine Aufgabe basierend auf KI-Faktoren.",
)
async def get_assignment_recommendation(
    request: AssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> AssignmentRecommendationResponse:
    """Ermittle optimale Aufgabenzuweisung."""
    service = get_smart_escalation_service(db)

    # Gewichtung validieren falls angegeben
    weights = None
    if request.weights:
        if not request.weights.validate_sum():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Gewichtungen muessen sich zu 1.0 summieren",
            )
        weights = request.weights.to_factor_weights()

    # Parse UUIDs
    document_id = UUID(request.document_id) if request.document_id else None
    entity_id = UUID(request.entity_id) if request.entity_id else None
    exclude_ids = (
        [UUID(uid) for uid in request.exclude_user_ids]
        if request.exclude_user_ids
        else None
    )

    recommendation = await service.get_assignment_recommendation(
        company_id=company.id,
        document_id=document_id,
        document_type=request.document_type,
        entity_id=entity_id,
        task_type=request.task_type,
        exclude_user_ids=exclude_ids,
        weights=weights,
        max_candidates=request.max_candidates,
    )

    if not recommendation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine geeigneten Kandidaten gefunden",
        )

    logger.info(
        "smart_escalation_recommendation_api",
        company_id=str(company.id),
        user_id=str(current_user.id),
        recommended_user=str(recommendation.recommended_user_id),
        confidence=recommendation.confidence,
    )

    return AssignmentRecommendationResponse.from_domain(recommendation)


@router.get(
    "/recommend",
    response_model=AssignmentRecommendationResponse,
    summary="Zuweisungsempfehlung holen (GET)",
    description="Ermittelt die beste Zuweisung mit Query-Parametern.",
)
async def get_assignment_recommendation_query(
    document_id: Optional[str] = Query(default=None, description="Dokument-ID"),
    document_type: Optional[str] = Query(default=None, description="Dokumenttyp"),
    entity_id: Optional[str] = Query(default=None, description="Entity-ID"),
    task_type: Optional[str] = Query(default=None, description="Aufgabentyp"),
    max_candidates: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> AssignmentRecommendationResponse:
    """Ermittle optimale Aufgabenzuweisung via GET."""
    service = get_smart_escalation_service(db)

    # Parse UUIDs
    doc_uuid = UUID(document_id) if document_id else None
    ent_uuid = UUID(entity_id) if entity_id else None

    recommendation = await service.get_assignment_recommendation(
        company_id=company.id,
        document_id=doc_uuid,
        document_type=document_type,
        entity_id=ent_uuid,
        task_type=task_type,
        max_candidates=max_candidates,
    )

    if not recommendation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Keine geeigneten Kandidaten gefunden",
        )

    return AssignmentRecommendationResponse.from_domain(recommendation)


@router.get(
    "/team-workload",
    response_model=TeamWorkloadResponse,
    summary="Team-Auslastung anzeigen",
    description="Zeigt Auslastungsuebersicht fuer alle Team-Mitglieder.",
)
async def get_team_workload(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> TeamWorkloadResponse:
    """Hole Team-Auslastungsuebersicht."""
    service = get_smart_escalation_service(db)

    overview = await service.get_team_workload_overview(company.id)

    team_members = [
        TeamMemberWorkload(
            user_id=m["user_id"],
            user_name=m["user_name"],
            open_items=m["open_items"],
            workload_score=round(m["workload_score"], 1),
            is_available=m["is_available"],
            availability_score=round(m["availability_score"], 1),
        )
        for m in overview["team_members"]
    ]

    return TeamWorkloadResponse(
        team_members=team_members,
        total_open_items=overview["total_open_items"],
        available_members=overview["available_members"],
        total_members=overview["total_members"],
        avg_items_per_member=round(overview["avg_items_per_member"], 1),
    )


@router.get(
    "/user-scores/{user_id}",
    response_model=CandidateScoreResponse,
    summary="User-Scores anzeigen",
    description="Zeigt alle Scores eines bestimmten Users (fuer Debugging/Analyse).",
)
async def get_user_scores(
    user_id: str,
    document_type: Optional[str] = Query(default=None, description="Dokumenttyp"),
    entity_id: Optional[str] = Query(default=None, description="Entity-ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CandidateScoreResponse:
    """Hole detaillierte Scores eines Users."""
    service = get_smart_escalation_service(db)

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige User-ID",
        )

    ent_uuid = UUID(entity_id) if entity_id else None

    try:
        scores = await service.get_user_scores(
            user_id=user_uuid,
            company_id=company.id,
            document_type=document_type,
            entity_id=ent_uuid,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "User-Score-Abruf"),
        )

    return CandidateScoreResponse.from_domain(scores)


@router.get(
    "/factors",
    response_model=Dict[str, Any],
    summary="Verfuegbare Faktoren anzeigen",
    description="Listet alle verfuegbaren Zuweisungsfaktoren und Standardgewichtungen auf.",
)
async def get_available_factors(
    current_user: User = Depends(get_current_active_user),
) -> Dict[str, Any]:
    """Hole verfuegbare Faktoren und Konfiguration."""
    default_weights = FactorWeights()

    return {
        "factors": [
            {
                "name": f.value,
                "description": _get_factor_description(f),
                "default_weight": getattr(default_weights, f.value),
            }
            for f in AssignmentFactor
        ],
        "default_weights": {
            "expertise": default_weights.expertise,
            "workload": default_weights.workload,
            "availability": default_weights.availability,
            "relationship": default_weights.relationship,
        },
        "score_range": {"min": 0, "max": 100},
        "thresholds": {
            "min_expertise_tasks": 3,
            "max_workload_items": 20,
            "expertise_period_days": 90,
            "relationship_period_days": 180,
        },
    }


def _get_factor_description(factor: AssignmentFactor) -> str:
    """Gibt deutsche Beschreibung fuer Faktor zurueck."""
    descriptions = {
        AssignmentFactor.EXPERTISE: (
            "Erfahrung mit dem Dokumenttyp basierend auf bisheriger Verarbeitungshistorie"
        ),
        AssignmentFactor.WORKLOAD: (
            "Aktuelle Auslastung basierend auf offenen Validierungen und Aufgaben"
        ),
        AssignmentFactor.AVAILABILITY: (
            "Verfuegbarkeit basierend auf Login-Aktivitaet und Status"
        ),
        AssignmentFactor.RELATIONSHIP: (
            "Vorherige Zusammenarbeit mit dem Kunden/Lieferanten"
        ),
    }
    return descriptions.get(factor, factor.value)
