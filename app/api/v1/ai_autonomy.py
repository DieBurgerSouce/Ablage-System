# -*- coding: utf-8 -*-
"""
AI Autonomy API - KI-Entscheidungen und Self-Learning.

Endpoints fuer:
- KI-Entscheidungen einsehen und reviewen
- Konfidenz-Schwellenwerte verwalten
- Accuracy-Statistiken und Reports
- Dokument-Kategorisierung, Matching, Anomalie-Erkennung
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union

from app.core.types import JSONDict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.rbac import require_permission
from app.db.models import User, UserCompany, Company
from app.services.ai.decision_service import (
    AIDecisionService,
    DecisionType,
    ConfidenceLevel,
    ReviewAction,
    get_ai_decision_service,
)
from app.services.ai.auto_categorization_service import (
    AutoCategorizationService,
    get_auto_categorization_service,
)
from app.services.ai.smart_matching_service import (
    SmartMatchingService,
    get_smart_matching_service,
)
from app.services.ai.anomaly_detection_service import (
    AnomalyDetectionService,
    get_anomaly_detection_service,
)
from app.services.ai.duplicate_detection_service import (
    DuplicateDetectionService,
    get_duplicate_detection_service,
)
from app.services.ai.learning_pipeline import (
    AILearningPipeline,
    get_ai_learning_pipeline,
)

router = APIRouter(prefix="/ai", tags=["AI Autonomy"])


# =============================================================================
# Helper Functions - Multi-Tenant Security
# =============================================================================

async def get_user_company_id(db: AsyncSession, user: User) -> Optional[uuid.UUID]:
    """
    Ermittelt die Company-ID des Users via UserCompany-Tabelle.

    SECURITY: Diese Funktion stellt Multi-Tenant-Isolation sicher.
    Nur Firmen mit explizitem UserCompany-Link sind erlaubt.

    Returns:
        Company-ID oder None wenn keine Zuordnung existiert
    """
    from sqlalchemy import select

    # Superuser sehen alle Daten (company_id = None bedeutet kein Filter)
    if user.is_superuser:
        return None

    # 1. Hole aktuelle Firma (is_current=True)
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(UserCompany.is_current == True)
        .where(Company.is_active == True)
        .where(Company.deleted_at.is_(None))
    )
    current_company_id = result.scalar_one_or_none()

    if current_company_id:
        return current_company_id

    # 2. Fallback: Erste verfügbare Firma
    result = await db.execute(
        select(UserCompany.company_id)
        .join(Company, Company.id == UserCompany.company_id)
        .where(UserCompany.user_id == user.id)
        .where(Company.is_active == True)
        .where(Company.deleted_at.is_(None))
        .order_by(UserCompany.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ThresholdResponse(BaseModel):
    """Schwellenwert-Konfiguration."""
    decision_type: str
    auto_threshold: float
    suggest_threshold: float
    is_enabled: bool
    allow_auto_apply: bool
    display_name: Optional[str] = None
    description: Optional[str] = None


class ThresholdUpdateRequest(BaseModel):
    """Update fuer Schwellenwerte."""
    auto_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    suggest_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_enabled: Optional[bool] = None
    allow_auto_apply: Optional[bool] = None


class DecisionResponse(BaseModel):
    """KI-Entscheidung."""
    id: str
    decision_type: str
    document_id: Optional[str]
    decision_value: JSONDict
    confidence: float
    calibrated_confidence: Optional[float]
    confidence_level: str
    auto_applied: bool
    requires_review: bool
    is_final: bool
    explanation: Optional[JSONDict]
    reviewed_by_id: Optional[str]
    reviewed_at: Optional[datetime]
    review_action: Optional[str]
    created_at: datetime


class ReviewRequest(BaseModel):
    """Review-Anfrage."""
    action: str = Field(..., pattern="^(approved|rejected|modified)$")
    modified_value: Optional[JSONDict] = None
    comment: Optional[str] = None


class CategorySuggestion(BaseModel):
    """Kategorie-Vorschlag."""
    category: str
    display_name: str
    confidence: float
    is_primary: bool


class MatchCandidate(BaseModel):
    """Match-Kandidat."""
    document_id: str
    match_type: str
    confidence: float
    feature_scores: Dict[str, float]
    matched_values: JSONDict


class AnomalyItem(BaseModel):
    """Erkannte Anomalie."""
    anomaly_type: str
    severity: str
    confidence: float
    description: str
    recommendation: Optional[str]
    details: JSONDict


class AnomalyCheckResponse(BaseModel):
    """Anomalie-Check Ergebnis."""
    has_anomalies: bool
    is_suspicious: bool
    risk_score: float
    anomalies: List[AnomalyItem]


class DuplicateCandidateResponse(BaseModel):
    """Duplikat-Kandidat."""
    document_id: str
    duplicate_type: str
    similarity: float
    matched_fields: List[str]
    details: Dict[str, object] = {}


class DuplicateCheckResponse(BaseModel):
    """Duplikat-Check Ergebnis."""
    has_duplicates: bool
    candidates: List[DuplicateCandidateResponse]
    best_match: Optional[DuplicateCandidateResponse] = None
    processing_time_ms: int = 0


class AccuracyStatsResponse(BaseModel):
    """Genauigkeits-Statistiken."""
    decision_type: str
    total_decisions: int
    auto_applied: int
    reviewed: int
    approved: int
    corrected: int
    rejected: int
    accuracy_rate: float
    correction_rate: float
    avg_confidence: float


class ThresholdAdjustmentSuggestion(BaseModel):
    """Vorgeschlagene Threshold-Anpassung."""
    decision_type: str
    current_auto: float
    current_suggest: float
    suggested_auto: float
    suggested_suggest: float
    reason: str


# =============================================================================
# Decision Endpoints
# =============================================================================

@router.get("/decisions", response_model=List[DecisionResponse])
async def list_decisions(
    decision_type: Optional[str] = None,
    requires_review: Optional[bool] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DecisionResponse]:
    """
    Listet KI-Entscheidungen.

    Filtert nach Typ und Review-Status.
    """
    from sqlalchemy import select, and_
    from app.db.models import AIDecision

    query = select(AIDecision)

    conditions = []
    if decision_type:
        conditions.append(AIDecision.decision_type == decision_type)
    if requires_review is not None:
        conditions.append(AIDecision.requires_review == requires_review)

    # SECURITY: Multi-Tenant Isolation via UserCompany
    company_id = await get_user_company_id(db, current_user)
    if company_id:
        conditions.append(AIDecision.company_id == company_id)

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(AIDecision.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    decisions = result.scalars().all()

    return [
        DecisionResponse(
            id=str(d.id),
            decision_type=d.decision_type,
            document_id=str(d.document_id) if d.document_id else None,
            decision_value=d.decision_value or {},
            confidence=d.confidence,
            calibrated_confidence=d.calibrated_confidence,
            confidence_level=d.confidence_level,
            auto_applied=d.auto_applied,
            requires_review=d.requires_review,
            is_final=d.is_final,
            explanation=d.explanation,
            reviewed_by_id=str(d.reviewed_by_id) if d.reviewed_by_id else None,
            reviewed_at=d.reviewed_at,
            review_action=d.review_action,
            created_at=d.created_at,
        )
        for d in decisions
    ]


@router.get("/decisions/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DecisionResponse:
    """Holt eine einzelne KI-Entscheidung mit Details."""
    from sqlalchemy import select
    from app.db.models import AIDecision

    result = await db.execute(
        select(AIDecision).where(AIDecision.id == decision_id)
    )
    d = result.scalar_one_or_none()

    if not d:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entscheidung nicht gefunden",
        )

    return DecisionResponse(
        id=str(d.id),
        decision_type=d.decision_type,
        document_id=str(d.document_id) if d.document_id else None,
        decision_value=d.decision_value or {},
        confidence=d.confidence,
        calibrated_confidence=d.calibrated_confidence,
        confidence_level=d.confidence_level,
        auto_applied=d.auto_applied,
        requires_review=d.requires_review,
        is_final=d.is_final,
        explanation=d.explanation,
        reviewed_by_id=str(d.reviewed_by_id) if d.reviewed_by_id else None,
        reviewed_at=d.reviewed_at,
        review_action=d.review_action,
        created_at=d.created_at,
    )


@router.post("/decisions/{decision_id}/review")
async def review_decision(
    decision_id: uuid.UUID,
    request: ReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Reviewed eine KI-Entscheidung.

    Moegliche Aktionen: approved, rejected, modified
    """
    service = get_ai_decision_service()

    try:
        action = ReviewAction(request.action)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Review-Aktion",
        )

    success = await service.review_decision(
        db=db,
        decision_id=decision_id,
        reviewer_id=current_user.id,
        action=action,
        modified_value=request.modified_value,
        comment=request.comment,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entscheidung nicht gefunden",
        )

    return {
        "success": True,
        "message": f"Entscheidung {request.action}",
    }


# =============================================================================
# Threshold Endpoints
# =============================================================================

@router.get("/thresholds", response_model=List[ThresholdResponse])
async def list_thresholds(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ThresholdResponse]:
    """Listet alle Konfidenz-Schwellenwerte."""
    service = get_ai_decision_service()

    # SECURITY: Multi-Tenant via UserCompany
    company_id = await get_user_company_id(db, current_user)
    thresholds = await service.get_thresholds(db, company_id)

    return [
        ThresholdResponse(
            decision_type=dt.value,
            auto_threshold=config.auto_threshold,
            suggest_threshold=config.suggest_threshold,
            is_enabled=config.is_enabled,
            allow_auto_apply=config.allow_auto_apply,
        )
        for dt, config in thresholds.items()
    ]


@router.put("/thresholds/{decision_type}")
async def update_threshold(
    decision_type: str,
    request: ThresholdUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin:full")),
) -> JSONDict:
    """
    Aktualisiert Konfidenz-Schwellenwerte.

    Nur fuer Admins.
    """
    from sqlalchemy import select
    from app.db.models import AIConfidenceThreshold

    # Validiere DecisionType
    try:
        dt = DecisionType(decision_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltiger Entscheidungstyp: {decision_type}",
        )

    # SECURITY: Multi-Tenant via UserCompany
    company_id = await get_user_company_id(db, current_user)

    # Suche existierenden Threshold
    result = await db.execute(
        select(AIConfidenceThreshold).where(
            AIConfidenceThreshold.decision_type == decision_type,
            AIConfidenceThreshold.company_id == company_id,
        )
    )
    threshold = result.scalar_one_or_none()

    if threshold:
        if request.auto_threshold is not None:
            threshold.auto_threshold = request.auto_threshold
        if request.suggest_threshold is not None:
            threshold.suggest_threshold = request.suggest_threshold
        if request.is_enabled is not None:
            threshold.is_enabled = request.is_enabled
        if request.allow_auto_apply is not None:
            threshold.allow_auto_apply = request.allow_auto_apply
        threshold.updated_by_id = current_user.id
    else:
        threshold = AIConfidenceThreshold(
            id=uuid.uuid4(),
            company_id=company_id,
            decision_type=decision_type,
            auto_threshold=request.auto_threshold or 0.95,
            suggest_threshold=request.suggest_threshold or 0.80,
            is_enabled=request.is_enabled if request.is_enabled is not None else True,
            allow_auto_apply=request.allow_auto_apply if request.allow_auto_apply is not None else True,
            updated_by_id=current_user.id,
        )
        db.add(threshold)

    await db.commit()

    return {
        "success": True,
        "message": f"Schwellenwerte fuer {decision_type} aktualisiert",
    }


# =============================================================================
# Document AI Endpoints
# =============================================================================

@router.post("/documents/{document_id}/categorize")
async def categorize_document(
    document_id: uuid.UUID,
    auto_apply: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Kategorisiert ein Dokument mit KI."""
    from sqlalchemy import select
    from app.db.models import Document

    # Lade Dokument
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden",
        )

    if not doc.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dokument hat keinen extrahierten Text",
        )

    service = get_auto_categorization_service()

    ai_result = await service.categorize_document(
        db=db,
        document_id=document_id,
        text=doc.extracted_text,
        company_id=doc.company_id,
        auto_apply_tags=auto_apply,
    )

    return {
        "decision_id": str(ai_result.decision_id),
        "category": ai_result.decision_value.get("category"),
        "display_name": ai_result.decision_value.get("display_name"),
        "confidence": ai_result.confidence,
        "confidence_level": ai_result.confidence_level.value,
        "auto_applied": ai_result.auto_applied,
    }


@router.get("/documents/{document_id}/category-suggestions", response_model=List[CategorySuggestion])
async def get_category_suggestions(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[CategorySuggestion]:
    """Gibt Kategorie-Vorschlaege ohne Persistenz zurueck."""
    from sqlalchemy import select
    from app.db.models import Document

    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()

    if not doc or not doc.extracted_text:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dokument nicht gefunden oder kein Text",
        )

    service = get_auto_categorization_service()
    suggestions = await service.get_category_suggestions(doc.extracted_text)

    return [
        CategorySuggestion(
            category=s["category"],
            display_name=s["display_name"],
            confidence=s["confidence"],
            is_primary=s["is_primary"],
        )
        for s in suggestions
    ]


@router.get("/documents/{document_id}/matches", response_model=List[MatchCandidate])
async def find_document_matches(
    document_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[MatchCandidate]:
    """Findet zusammengehoerige Dokumente."""
    service = get_smart_matching_service()

    company_id = await get_user_company_id(db, current_user)

    result = await service.find_matches(
        db=db,
        document_id=document_id,
        company_id=company_id,
        max_results=limit,
    )

    return [
        MatchCandidate(
            document_id=str(m.target_document_id),
            match_type=m.match_type,
            confidence=round(m.confidence, 3),
            feature_scores={k: round(v, 3) for k, v in m.feature_scores.items()},
            matched_values=m.matched_values,
        )
        for m in result.matches
    ]


@router.get("/documents/{document_id}/anomalies", response_model=AnomalyCheckResponse)
async def check_document_anomalies(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AnomalyCheckResponse:
    """Prueft Dokument auf Anomalien."""
    service = get_anomaly_detection_service()

    company_id = await get_user_company_id(db, current_user)

    result = await service.check_document(
        db=db,
        document_id=document_id,
        company_id=company_id,
    )

    return AnomalyCheckResponse(
        has_anomalies=len(result.anomalies) > 0,
        is_suspicious=result.is_suspicious,
        risk_score=result.overall_risk_score,
        anomalies=[
            AnomalyItem(
                anomaly_type=a.anomaly_type.value,
                severity=a.severity.value,
                confidence=a.confidence,
                description=a.description,
                recommendation=a.recommendation,
                details=a.details,
            )
            for a in result.anomalies
        ],
    )


@router.get("/documents/{document_id}/duplicates", response_model=DuplicateCheckResponse)
async def check_document_duplicates(
    document_id: uuid.UUID,
    include_near: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DuplicateCheckResponse:
    """Prueft Dokument auf Duplikate."""
    service = get_duplicate_detection_service()

    company_id = await get_user_company_id(db, current_user)

    result = await service.check_document(
        db=db,
        document_id=document_id,
        company_id=company_id,
        include_near=include_near,
    )

    def _to_response(c: object) -> DuplicateCandidateResponse:
        return DuplicateCandidateResponse(
            document_id=str(c.document_id),
            duplicate_type=c.duplicate_type,
            similarity=round(c.similarity, 3),
            matched_fields=c.matched_fields,
            details=c.details,
        )

    return DuplicateCheckResponse(
        has_duplicates=result.has_duplicates,
        candidates=[_to_response(c) for c in result.candidates],
        best_match=_to_response(result.best_match) if result.best_match else None,
        processing_time_ms=result.processing_time_ms,
    )


# =============================================================================
# Statistics & Learning Endpoints
# =============================================================================

@router.get("/stats/accuracy", response_model=List[AccuracyStatsResponse])
async def get_accuracy_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AccuracyStatsResponse]:
    """Gibt Genauigkeits-Statistiken zurueck."""
    pipeline = get_ai_learning_pipeline()

    company_id = await get_user_company_id(db, current_user)

    stats = await pipeline.get_learning_stats(
        db=db,
        company_id=company_id,
        days=days,
    )

    return [
        AccuracyStatsResponse(
            decision_type=s.decision_type.value,
            total_decisions=s.total_decisions,
            auto_applied=s.auto_applied,
            reviewed=s.reviewed,
            approved=s.approved,
            corrected=s.corrected,
            rejected=s.rejected,
            accuracy_rate=s.accuracy_rate,
            correction_rate=s.correction_rate,
            avg_confidence=s.avg_confidence,
        )
        for s in stats
    ]


@router.get("/stats/learning")
async def get_learning_progress(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """Gibt Self-Learning Fortschritt zurueck."""
    pipeline = get_ai_learning_pipeline()

    company_id = await get_user_company_id(db, current_user)

    report = await pipeline.generate_accuracy_report(
        db=db,
        company_id=company_id,
        days=days,
    )

    return report


@router.get("/stats/threshold-suggestions", response_model=List[ThresholdAdjustmentSuggestion])
async def get_threshold_suggestions(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin:full")),
) -> List[ThresholdAdjustmentSuggestion]:
    """Gibt Vorschlaege fuer Threshold-Anpassungen zurueck."""
    pipeline = get_ai_learning_pipeline()

    company_id = await get_user_company_id(db, current_user)

    adjustments = await pipeline.suggest_threshold_adjustments(
        db=db,
        company_id=company_id,
        days=days,
    )

    return [
        ThresholdAdjustmentSuggestion(
            decision_type=a.decision_type.value,
            current_auto=a.current_auto,
            current_suggest=a.current_suggest,
            suggested_auto=a.suggested_auto,
            suggested_suggest=a.suggested_suggest,
            reason=a.reason,
        )
        for a in adjustments
    ]


@router.post("/stats/threshold-suggestions/{decision_type}/apply")
async def apply_threshold_suggestion(
    decision_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin:full")),
) -> JSONDict:
    """Wendet einen Threshold-Vorschlag an."""
    pipeline = get_ai_learning_pipeline()

    company_id = await get_user_company_id(db, current_user)

    # Hole aktuelle Vorschlaege
    adjustments = await pipeline.suggest_threshold_adjustments(
        db=db,
        company_id=company_id,
    )

    # Finde den passenden
    adjustment = next(
        (a for a in adjustments if a.decision_type.value == decision_type),
        None,
    )

    if not adjustment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Kein Vorschlag fuer {decision_type} gefunden",
        )

    success = await pipeline.apply_threshold_adjustment(
        db=db,
        adjustment=adjustment,
        company_id=company_id,
        updated_by_id=current_user.id,
    )

    return {
        "success": success,
        "message": f"Schwellenwerte fuer {decision_type} angepasst",
        "new_auto_threshold": adjustment.suggested_auto,
        "new_suggest_threshold": adjustment.suggested_suggest,
    }


@router.get("/pending-review-count")
async def get_pending_review_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, int]:
    """Zaehlt ausstehende Reviews pro Typ."""
    service = get_ai_decision_service()

    company_id = await get_user_company_id(db, current_user)

    counts = await service.get_pending_review_count(
        db=db,
        company_id=company_id,
    )

    return {dt.value: count for dt, count in counts.items()}


# =============================================================================
# Natural Language Query (NLQ) Endpoints
# =============================================================================


class NLQQueryRequest(BaseModel):
    """NLQ-Abfrage-Request."""
    query: str = Field(..., min_length=3, max_length=500, description="Die Abfrage in natuerlicher Sprache")
    limit: int = Field(50, ge=1, le=200, description="Maximale Anzahl Ergebnisse")


class NLQEntityResponse(BaseModel):
    """Extrahierte Entity aus der Abfrage."""
    entity_type: str
    value: Union[str, int, float, bool]
    original_text: str
    confidence: float


class NLQResultResponse(BaseModel):
    """NLQ-Abfrage-Ergebnis."""
    success: bool
    intent: str
    extracted_entities: List[NLQEntityResponse]
    results: Optional[List[JSONDict]] = None
    result_count: int = 0
    aggregation_value: Optional[float] = None
    natural_response: str
    confidence: float
    processing_time_ms: int


@router.post("/nlq/query", response_model=NLQResultResponse)
async def process_nlq_query(
    request: NLQQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NLQResultResponse:
    """
    Verarbeitet eine natuerlichsprachliche Abfrage.

    Beispiele:
    - "Zeige alle Rechnungen von Mueller GmbH ueber 1000 EUR"
    - "Wie viel haben wir letzten Monat fuer Bueroartikel ausgegeben?"
    - "Welche Rechnungen sind seit mehr als 30 Tagen offen?"

    Der Service erkennt automatisch:
    - Firmennamen (validiert gegen DB)
    - Geldbetraege (mit Operatoren: ueber, unter, etc.)
    - Zeitraeume (letzter Monat, diese Woche, etc.)
    - Dokumenttypen (Rechnung, Angebot, etc.)
    - Status (offen, bezahlt, ueberfaellig)
    """
    from app.services.ai.nlq_service import get_nlq_service

    company_id = await get_user_company_id(db, current_user)

    nlq_service = await get_nlq_service(db)
    result = await nlq_service.process_query(
        query=request.query,
        company_id=company_id,
        user_id=current_user.id,
        limit=request.limit,
    )

    return NLQResultResponse(
        success=result.success,
        intent=result.intent.value,
        extracted_entities=[
            NLQEntityResponse(
                entity_type=e.entity_type.value,
                value=e.value if not isinstance(e.value, dict) or "id" not in e.value else {**e.value, "id": str(e.value["id"])},
                original_text=e.original_text,
                confidence=e.confidence,
            )
            for e in result.extracted_entities
        ],
        results=result.results,
        result_count=result.result_count,
        aggregation_value=float(result.aggregation_value) if result.aggregation_value is not None else None,
        natural_response=result.natural_response,
        confidence=result.confidence,
        processing_time_ms=result.processing_time_ms,
    )


@router.get("/nlq/examples")
async def get_nlq_examples(
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Gibt Beispiel-Abfragen fuer NLQ zurueck.

    Hilft Benutzern, die Syntax zu verstehen.
    """
    return {
        "examples": [
            {
                "category": "Suche",
                "queries": [
                    "Zeige alle Rechnungen von letzter Woche",
                    "Finde Dokumente von Mueller GmbH",
                    "Alle offenen Rechnungen ueber 500 EUR",
                ]
            },
            {
                "category": "Aggregation",
                "queries": [
                    "Summe aller Rechnungen diesen Monat",
                    "Durchschnittlicher Rechnungsbetrag letztes Jahr",
                    "Wie viele Lieferscheine wurden erstellt?",
                ]
            },
            {
                "category": "Vergleich",
                "queries": [
                    "Vergleiche Ausgaben Januar mit Februar",
                    "Mehr als letzten Monat?",
                ]
            },
            {
                "category": "Status",
                "queries": [
                    "Ueberfaellige Rechnungen",
                    "Bezahlte Rechnungen diesen Monat",
                    "Offene Betraege von Lieferanten",
                ]
            },
        ],
        "tips": [
            "Verwenden Sie deutsche Begriffe fuer Dokumenttypen (Rechnung, Angebot, etc.)",
            "Betraege koennen mit 'ueber', 'unter', 'mindestens' eingeschraenkt werden",
            "Zeitraeume: 'heute', 'gestern', 'letzte Woche', 'dieser Monat', 'letztes Jahr'",
            "Firmennamen werden automatisch mit der Datenbank abgeglichen",
        ]
    }


# =============================================================================
# Routing Intelligence Endpoints
# =============================================================================


class RoutingRequest(BaseModel):
    """Request fuer Dokument-Routing."""

    document_id: uuid.UUID = Field(..., description="ID des zu routenden Dokuments")


class RoutingDecisionResponse(BaseModel):
    """Response fuer Routing-Entscheidung."""

    document_id: str
    target_type: str  # workflow, department, user, queue
    target_id: Optional[str]
    target_name: str
    priority: str  # critical, high, medium, low
    confidence: float
    reasons: List[str]
    explanation: str
    requires_approval: bool
    suggested_deadline: Optional[datetime] = None
    metadata: JSONDict = {}


class RoutingStatisticsResponse(BaseModel):
    """Response fuer Routing-Statistiken."""

    period_days: int
    folder_distribution: List[JSONDict]
    type_distribution: List[JSONDict]
    custom_rules_count: int
    routing_enabled: bool
    min_confidence: float


@router.post("/routing/route", response_model=RoutingDecisionResponse)
async def route_document(
    request: RoutingRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoutingDecisionResponse:
    """
    Bestimmt das Routing fuer ein Dokument.

    Analysiert:
    - Dokumenttyp
    - Erkannte Entity (Kunde/Lieferant)
    - Betrag
    - Keywords im Text
    - Historische Muster

    Gibt Ziel-Abteilung/Workflow und Prioritaet zurueck.
    """
    from app.services.ai.routing_intelligence_service import get_routing_intelligence_service

    company_id = await get_user_company_id(db, current_user)

    service = get_routing_intelligence_service(db)
    decision = await service.route_document(
        document_id=request.document_id,
        company_id=company_id,
    )

    return RoutingDecisionResponse(
        document_id=str(decision.document_id),
        target_type=decision.target_type.value,
        target_id=decision.target_id,
        target_name=decision.target_name,
        priority=decision.priority.value,
        confidence=decision.confidence,
        reasons=[r.value for r in decision.reasons],
        explanation=decision.explanation,
        requires_approval=decision.requires_approval,
        suggested_deadline=decision.suggested_deadline,
        metadata=decision.metadata,
    )


@router.get("/routing/statistics", response_model=RoutingStatisticsResponse)
async def get_routing_statistics(
    days: int = Query(30, ge=1, le=365, description="Anzahl Tage fuer Statistik"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RoutingStatisticsResponse:
    """
    Gibt Routing-Statistiken zurueck.

    Zeigt:
    - Verteilung nach Ordner
    - Verteilung nach Dokumenttyp
    - Anzahl benutzerdefinierter Regeln
    - Routing-Konfiguration
    """
    from app.services.ai.routing_intelligence_service import get_routing_intelligence_service

    company_id = await get_user_company_id(db, current_user)

    if not company_id and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_routing_intelligence_service(db)
    stats = await service.get_routing_statistics(
        company_id=company_id or uuid.UUID("00000000-0000-0000-0000-000000000000"),
        days=days,
    )

    return RoutingStatisticsResponse(**stats)


# =============================================================================
# Autonomy Configuration Endpoint
# =============================================================================


class AutonomyThresholdsResponse(BaseModel):
    """Response fuer Autonomie-Thresholds."""

    document_classification: float
    entity_linking: float
    invoice_approval: float
    payment_matching: float
    ocr_correction: float
    auto_approval_max_amount: float
    auto_approval_enabled: bool
    routing_enabled: bool
    routing_min_confidence: float
    anomaly_detection_enabled: bool
    anomaly_alert_threshold: float
    suggestions_enabled: bool
    max_suggestions_per_document: int
    nlq_enabled: bool
    nlq_max_results: int
    audit_logging_enabled: bool


@router.get("/autonomy/thresholds", response_model=AutonomyThresholdsResponse)
async def get_autonomy_thresholds(
    current_user: User = Depends(get_current_user),
) -> AutonomyThresholdsResponse:
    """
    Gibt die aktuellen Autonomie-Thresholds zurueck.

    Diese Thresholds bestimmen, ab welcher Confidence-Stufe
    das System automatisch handelt:
    - >= Threshold: Automatische Aktion
    - < Threshold: User-Bestaetigung erforderlich
    """
    from app.core.config import settings

    return AutonomyThresholdsResponse(
        document_classification=settings.AUTONOMY_DOCUMENT_CLASSIFICATION_THRESHOLD,
        entity_linking=settings.AUTONOMY_ENTITY_LINKING_THRESHOLD,
        invoice_approval=settings.AUTONOMY_INVOICE_APPROVAL_THRESHOLD,
        payment_matching=settings.AUTONOMY_PAYMENT_MATCHING_THRESHOLD,
        ocr_correction=settings.AUTONOMY_OCR_CORRECTION_THRESHOLD,
        auto_approval_max_amount=settings.AUTONOMY_AUTO_APPROVAL_MAX_AMOUNT,
        auto_approval_enabled=settings.AUTONOMY_AUTO_APPROVAL_ENABLED,
        routing_enabled=settings.AUTONOMY_ROUTING_ENABLED,
        routing_min_confidence=settings.AUTONOMY_ROUTING_MIN_CONFIDENCE,
        anomaly_detection_enabled=settings.AUTONOMY_ANOMALY_DETECTION_ENABLED,
        anomaly_alert_threshold=settings.AUTONOMY_ANOMALY_ALERT_THRESHOLD,
        suggestions_enabled=settings.AUTONOMY_SUGGESTIONS_ENABLED,
        max_suggestions_per_document=settings.AUTONOMY_MAX_SUGGESTIONS_PER_DOCUMENT,
        nlq_enabled=settings.AUTONOMY_NLQ_ENABLED,
        nlq_max_results=settings.AUTONOMY_NLQ_MAX_RESULTS,
        audit_logging_enabled=settings.AUTONOMY_AUDIT_LOGGING_ENABLED,
    )
