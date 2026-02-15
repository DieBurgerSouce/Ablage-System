# -*- coding: utf-8 -*-
"""
Automation API Endpoints.

Feature #7: Automation 2.0
- Auto-Filing Regeln (CRUD + Vorschlaege + Training)
- Auto-Matching (Ergebnisse + Bestaetigung + Statistiken)
"""

import structlog
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.automation.auto_filing_service import AutoFilingService
from app.services.automation.auto_matching_service import AutoMatchingService

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/automation",
    tags=["automation"],
)


# =============================================================================
# SCHEMAS - Auto-Filing
# =============================================================================


class AutoFilingRuleCreateRequest(BaseModel):
    """Request zum Erstellen einer Auto-Filing-Regel."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Name der Regel",
    )
    description: Optional[str] = Field(
        None,
        description="Optionale Beschreibung",
    )
    model_type: str = Field(
        "rule",
        description="Modelltyp: 'ml' oder 'rule'",
    )
    confidence_threshold: float = Field(
        0.95,
        gt=0.0,
        le=1.0,
        description="Confidence-Schwelle fuer automatische Ablage",
    )
    target_folder_id: Optional[UUID] = Field(
        None,
        description="Ziel-Ordner-ID",
    )
    target_category: Optional[str] = Field(
        None,
        description="Ziel-Kategorie",
    )
    config: Optional[Dict[str, object]] = Field(
        None,
        description="Zusaetzliche Konfiguration",
    )


class AutoFilingRuleUpdateRequest(BaseModel):
    """Request zum Aktualisieren einer Auto-Filing-Regel."""

    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
    )
    description: Optional[str] = None
    model_type: Optional[str] = None
    confidence_threshold: Optional[float] = Field(None, gt=0.0, le=1.0)
    target_folder_id: Optional[UUID] = None
    target_category: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[Dict[str, object]] = None


class AutoFilingRuleResponse(BaseModel):
    """Response fuer eine Auto-Filing-Regel."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    name: str
    description: Optional[str]
    model_type: str
    confidence_threshold: float
    target_folder_id: Optional[UUID]
    target_category: Optional[str]
    training_sample_count: int
    accuracy: Optional[float]
    is_active: bool
    config: Optional[Dict[str, object]]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class FilingSuggestionResponse(BaseModel):
    """Response fuer einen Ablage-Vorschlag."""

    rule_id: UUID
    rule_name: str
    target_folder_id: Optional[UUID]
    target_category: Optional[str]
    confidence: float
    model_type: str
    auto_file: bool


class AccuracyStatsResponse(BaseModel):
    """Response fuer Accuracy-Statistiken."""

    total_rules: int
    active_rules: int
    avg_accuracy: float
    total_training_samples: int
    rules_above_threshold: int
    rules_below_threshold: int
    rules_by_model_type: Dict[str, int]


# =============================================================================
# SCHEMAS - Auto-Matching
# =============================================================================


class AutoMatchResponse(BaseModel):
    """Response fuer ein Auto-Match-Ergebnis."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    document_id: UUID
    matched_document_id: UUID
    match_type: str
    confidence: float
    match_details: Optional[Dict[str, object]]
    is_confirmed: bool
    confirmed_by_user_id: Optional[UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]


class MatchStatisticsResponse(BaseModel):
    """Response fuer Match-Statistiken."""

    total_matches: int
    confirmed_matches: int
    unconfirmed_matches: int
    avg_confidence: float
    matches_by_type: Dict[str, int]
    confirmation_rate: float


# =============================================================================
# ENDPOINTS - Auto-Filing Regeln
# =============================================================================


@router.get(
    "/filing-rules",
    response_model=List[AutoFilingRuleResponse],
    summary="Auto-Filing-Regeln auflisten",
)
async def list_filing_rules(
    active_only: bool = Query(True, description="Nur aktive Regeln"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AutoFilingRuleResponse]:
    """Listet alle Auto-Filing-Regeln der Firma auf."""
    service = AutoFilingService(db)
    rules = await service.get_rules(
        db, current_user.company_id, active_only=active_only
    )
    return [AutoFilingRuleResponse.model_validate(r) for r in rules]


@router.post(
    "/filing-rules",
    response_model=AutoFilingRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Auto-Filing-Regel erstellen",
)
async def create_filing_rule(
    request: AutoFilingRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoFilingRuleResponse:
    """Erstellt eine neue Auto-Filing-Regel."""
    service = AutoFilingService(db)

    try:
        rule = await service.create_rule(
            db=db,
            company_id=current_user.company_id,
            name=request.name,
            model_type=request.model_type,
            confidence_threshold=request.confidence_threshold,
            target_folder_id=request.target_folder_id,
            target_category=request.target_category,
            description=request.description,
            config=request.config,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    await db.commit()
    return AutoFilingRuleResponse.model_validate(rule)


@router.put(
    "/filing-rules/{rule_id}",
    response_model=AutoFilingRuleResponse,
    summary="Auto-Filing-Regel aktualisieren",
)
async def update_filing_rule(
    rule_id: UUID,
    request: AutoFilingRuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoFilingRuleResponse:
    """Aktualisiert eine Auto-Filing-Regel."""
    service = AutoFilingService(db)

    updates = request.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Keine Aenderungen angegeben",
        )

    rule = await service.update_rule(
        db, current_user.company_id, rule_id, updates
    )

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auto-Filing-Regel nicht gefunden",
        )

    await db.commit()
    return AutoFilingRuleResponse.model_validate(rule)


@router.delete(
    "/filing-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Auto-Filing-Regel loeschen",
)
async def delete_filing_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Loescht eine Auto-Filing-Regel."""
    service = AutoFilingService(db)
    deleted = await service.delete_rule(
        db, current_user.company_id, rule_id
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auto-Filing-Regel nicht gefunden",
        )

    await db.commit()


# =============================================================================
# ENDPOINTS - Auto-Filing Vorschlaege & Training
# =============================================================================


@router.get(
    "/filing-suggestions/{document_id}",
    response_model=List[FilingSuggestionResponse],
    summary="Ablage-Vorschlaege fuer Dokument",
)
async def get_filing_suggestions(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[FilingSuggestionResponse]:
    """Liefert Ablage-Vorschlaege fuer ein Dokument."""
    service = AutoFilingService(db)
    suggestions = await service.classify_document(
        db, current_user.company_id, document_id
    )

    return [
        FilingSuggestionResponse(
            rule_id=s.rule_id,
            rule_name=s.rule_name,
            target_folder_id=s.target_folder_id,
            target_category=s.target_category,
            confidence=s.confidence,
            model_type=s.model_type,
            auto_file=s.auto_file,
        )
        for s in suggestions
    ]


@router.post(
    "/filing-train/{rule_id}",
    summary="Filing-Modell trainieren",
)
async def train_filing_model(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, object]:
    """Trainiert ein Filing-Modell basierend auf historischen Daten."""
    service = AutoFilingService(db)

    try:
        result = await service.train_model(
            db, current_user.company_id, rule_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    await db.commit()
    return result


@router.get(
    "/filing-stats",
    response_model=AccuracyStatsResponse,
    summary="Filing-Accuracy-Statistiken",
)
async def get_filing_accuracy_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AccuracyStatsResponse:
    """Liefert aggregierte Accuracy-Statistiken fuer alle Filing-Modelle."""
    service = AutoFilingService(db)
    stats = await service.get_accuracy_stats(
        db, current_user.company_id
    )

    return AccuracyStatsResponse(
        total_rules=stats.total_rules,
        active_rules=stats.active_rules,
        avg_accuracy=stats.avg_accuracy,
        total_training_samples=stats.total_training_samples,
        rules_above_threshold=stats.rules_above_threshold,
        rules_below_threshold=stats.rules_below_threshold,
        rules_by_model_type=stats.rules_by_model_type,
    )


# =============================================================================
# ENDPOINTS - Auto-Matching
# =============================================================================


@router.get(
    "/matches/{document_id}",
    response_model=List[AutoMatchResponse],
    summary="Matches fuer Dokument",
)
async def get_document_matches(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AutoMatchResponse]:
    """Holt alle Matching-Ergebnisse fuer ein Dokument."""
    service = AutoMatchingService(db)
    matches = await service.get_matches_for_document(
        db, current_user.company_id, document_id
    )
    return [AutoMatchResponse.model_validate(m) for m in matches]


@router.post(
    "/matches/{match_id}/confirm",
    response_model=AutoMatchResponse,
    summary="Match bestaetigen",
)
async def confirm_match(
    match_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AutoMatchResponse:
    """Bestaetigt ein automatisches Match."""
    service = AutoMatchingService(db)
    match = await service.confirm_match(
        db, current_user.company_id, match_id, current_user.id
    )

    if not match:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match nicht gefunden",
        )

    await db.commit()
    return AutoMatchResponse.model_validate(match)


@router.delete(
    "/matches/{match_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Match ablehnen/loeschen",
)
async def reject_match(
    match_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Lehnt ein automatisches Match ab (loescht es)."""
    service = AutoMatchingService(db)
    deleted = await service.reject_match(
        db, current_user.company_id, match_id
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Match nicht gefunden",
        )

    await db.commit()


@router.get(
    "/match-stats",
    response_model=MatchStatisticsResponse,
    summary="Match-Statistiken",
)
async def get_match_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MatchStatisticsResponse:
    """Liefert aggregierte Match-Statistiken."""
    service = AutoMatchingService(db)
    stats = await service.get_match_statistics(
        db, current_user.company_id
    )

    return MatchStatisticsResponse(
        total_matches=stats.total_matches,
        confirmed_matches=stats.confirmed_matches,
        unconfirmed_matches=stats.unconfirmed_matches,
        avg_confidence=stats.avg_confidence,
        matches_by_type=stats.matches_by_type,
        confirmation_rate=stats.confirmation_rate,
    )


@router.get(
    "/unmatched-documents",
    summary="Ungematchte Dokumente",
)
async def get_unmatched_documents(
    document_type: Optional[str] = Query(
        None,
        description="Optionaler Dokumenttyp-Filter",
    ),
    limit: int = Query(
        50,
        ge=1,
        le=200,
        description="Max. Anzahl Ergebnisse",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, object]]:
    """Findet Dokumente ohne Matching-Partner."""
    service = AutoMatchingService(db)
    return await service.get_unmatched_documents(
        db,
        current_user.company_id,
        document_type=document_type,
        limit=limit,
    )
