# -*- coding: utf-8 -*-
"""
Autonomous Trust System API - Multi-Level Trust für KI-Aktionen.

Endpoints für:
- Trust-Level Management
- Pending Approvals Queue
- Proposal Approve/Reject/Rollback
- Trust Metrics und Empfehlungen
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from app.core.types import JSONDict
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.rbac import require_permission
from app.db.models import User, UserCompany, Company
from app.services.ai.trust_level_service import (
    TrustLevelService,
    TrustLevel,
    TrustLevelConfig,
    TrustMetrics,
    TrustLevelRecommendation,
    TRUST_LEVEL_CONFIGS,
    get_trust_level_service,
)
from app.services.ai.delayed_acceptance_service import (
    DelayedAcceptanceService,
    ProposalType,
    ProposalStatus,
    get_delayed_acceptance_service,
)
from app.services.ai.amount_tier_service import (
    AmountTierService,
    AmountTier,
    ApprovalMode,
    get_amount_tier_service,
    DEFAULT_TIERS,
)

router = APIRouter(prefix="/autonomous", tags=["Autonomous Trust System"])


# =============================================================================
# Helper Functions - Multi-Tenant Security
# =============================================================================


async def get_user_company_id(db: AsyncSession, user: User) -> Optional[uuid.UUID]:
    """
    Ermittelt die Company-ID des Users via UserCompany-Tabelle.

    SECURITY: Diese Funktion stellt Multi-Tenant-Isolation sicher.
    """
    from sqlalchemy import select

    # Superuser sehen alle Daten (company_id = None bedeutet kein Filter)
    if user.is_superuser:
        return None

    # Hole aktuelle Firma (is_current=True)
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

    # Fallback: Erste verfügbare Firma
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


class TrustLevelResponse(BaseModel):
    """Aktuelles Trust-Level."""
    level: str
    level_name: str
    is_enabled: bool
    immediate_threshold: float
    delayed_threshold: float
    delay_hours: int
    require_confirmation: bool
    allow_auto_apply: bool
    document_type: Optional[str] = None


class TrustLevelUpdateRequest(BaseModel):
    """Update für Trust-Level."""
    level: str = Field(..., pattern="^(assistance|auto_accept|confidence|autonomous)$")
    document_type: Optional[str] = None
    reason: Optional[str] = None


class TrustMetricsResponse(BaseModel):
    """Trust-Metriken."""
    total_decisions: int
    auto_applied: int
    approved: int
    rejected: int
    corrected: int
    approval_rate: float
    error_rate: float
    avg_confidence: float
    days_without_error: int
    last_error_at: Optional[datetime] = None


class TrustRecommendationResponse(BaseModel):
    """Trust-Level Empfehlung."""
    current_level: str
    recommended_level: str
    reason: str
    confidence: float
    can_upgrade: bool
    upgrade_requirements: JSONDict


class PendingApprovalResponse(BaseModel):
    """Ausstehende Genehmigung."""
    id: str
    proposal_type: str
    target_id: str
    proposed_value: JSONDict
    confidence: float
    delay_hours: int
    status: str
    created_at: datetime
    scheduled_at: datetime
    reasoning: Optional[str] = None
    time_remaining_hours: Optional[float] = None


class ApprovalActionRequest(BaseModel):
    """Anfrage für Approve/Reject."""
    reason: Optional[str] = None


class ProposalHistoryResponse(BaseModel):
    """Proposal-Historie Eintrag."""
    id: str
    proposal_type: str
    target_id: str
    proposed_value: JSONDict
    confidence: float
    status: str
    created_at: datetime
    scheduled_at: datetime
    executed_at: Optional[datetime] = None
    executed_by: Optional[str] = None
    can_rollback: bool


class AmountTierSchema(BaseModel):
    """Eine Betrags-Freigabestufe."""
    name: str
    max_amount: str  # As string for JSON serialization
    approval_mode: str
    min_trust_level: str


class AmountTiersResponse(BaseModel):
    """Response mit Betrags-Freigabestufen."""
    tiers: List[AmountTierSchema]
    is_default: bool = True


class AmountTiersUpdateRequest(BaseModel):
    """Request zum Aktualisieren von Betrags-Freigabestufen."""
    tiers: List[AmountTierSchema] = Field(..., min_length=2, max_length=5)


class ApprovalModeResponse(BaseModel):
    """Response mit dem bestimmten Freigabemodus."""
    approval_mode: str
    tier_name: str
    amount: str


# =============================================================================
# Trust Level Endpoints
# =============================================================================


@router.get("/trust-level", response_model=TrustLevelResponse)
async def get_trust_level(
    document_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrustLevelResponse:
    """
    Holt das aktuelle Trust-Level für die Company.

    Optional kann ein spezifischer Dokumenttyp angegeben werden.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_trust_level_service(db)
    config = await service.get_trust_config(company_id, document_type)

    level_names = {
        TrustLevel.LEVEL_1_ASSISTANCE: "Assistenz-Modus",
        TrustLevel.LEVEL_2_AUTO_ACCEPT: "Auto-Accept (24h)",
        TrustLevel.LEVEL_3_CONFIDENCE: "Confidence-basiert",
        TrustLevel.LEVEL_4_AUTONOMOUS: "Volle Autonomie",
    }

    return TrustLevelResponse(
        level=config.level.value,
        level_name=level_names.get(config.level, config.level.value),
        is_enabled=True,
        immediate_threshold=config.immediate_threshold,
        delayed_threshold=config.delayed_threshold,
        delay_hours=config.delay_hours,
        require_confirmation=config.require_confirmation,
        allow_auto_apply=config.allow_auto_apply,
        document_type=document_type,
    )


@router.patch("/trust-level", response_model=JSONDict)
async def update_trust_level(
    request: TrustLevelUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("admin:full")),
) -> JSONDict:
    """
    Aktualisiert das Trust-Level für die Company.

    Nur für Admins. Erfordert explizite Begruendung.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    try:
        trust_level = TrustLevel(request.level)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiges Trust-Level: {request.level}",
        )

    service = get_trust_level_service(db)
    success = await service.set_trust_level(
        company_id=company_id,
        trust_level=trust_level,
        document_type=request.document_type,
        updated_by_id=current_user.id,
        reason=request.reason,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren des Trust-Levels",
        )

    return {
        "success": True,
        "message": f"Trust-Level auf '{request.level}' aktualisiert",
        "document_type": request.document_type,
    }


@router.get("/trust-level/metrics", response_model=TrustMetricsResponse)
async def get_trust_metrics(
    document_type: Optional[str] = None,
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrustMetricsResponse:
    """
    Holt Trust-Metriken für die Company.

    Berechnet Erfolgsraten, Fehlerquoten und andere KPIs.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_trust_level_service(db)
    metrics = await service.get_trust_metrics(company_id, document_type, days)

    return TrustMetricsResponse(
        total_decisions=metrics.total_decisions,
        auto_applied=metrics.auto_applied,
        approved=metrics.approved,
        rejected=metrics.rejected,
        corrected=metrics.corrected,
        approval_rate=round(metrics.approval_rate, 4),
        error_rate=round(metrics.error_rate, 4),
        avg_confidence=round(metrics.avg_confidence, 4),
        days_without_error=metrics.days_without_error,
        last_error_at=metrics.last_error_at,
    )


@router.get("/trust-level/recommendation", response_model=TrustRecommendationResponse)
async def get_trust_recommendation(
    document_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TrustRecommendationResponse:
    """
    Holt Empfehlung für Trust-Level Anpassung.

    Basierend auf historischen Metriken.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_trust_level_service(db)
    recommendation = await service.evaluate_trust_level(company_id, document_type)

    return TrustRecommendationResponse(
        current_level=recommendation.current_level.value,
        recommended_level=recommendation.recommended_level.value,
        reason=recommendation.reason,
        confidence=recommendation.confidence,
        can_upgrade=recommendation.can_upgrade,
        upgrade_requirements=recommendation.upgrade_requirements,
    )


@router.get("/trust-level/levels", response_model=List[TrustLevelResponse])
async def list_trust_levels(
    current_user: User = Depends(get_current_user),
) -> List[TrustLevelResponse]:
    """
    Listet alle verfügbaren Trust-Level mit Beschreibung.
    """
    level_names = {
        TrustLevel.LEVEL_1_ASSISTANCE: "Assistenz-Modus",
        TrustLevel.LEVEL_2_AUTO_ACCEPT: "Auto-Accept (24h)",
        TrustLevel.LEVEL_3_CONFIDENCE: "Confidence-basiert",
        TrustLevel.LEVEL_4_AUTONOMOUS: "Volle Autonomie",
    }

    return [
        TrustLevelResponse(
            level=config.level.value,
            level_name=level_names.get(config.level, config.level.value),
            is_enabled=True,
            immediate_threshold=config.immediate_threshold,
            delayed_threshold=config.delayed_threshold,
            delay_hours=config.delay_hours,
            require_confirmation=config.require_confirmation,
            allow_auto_apply=config.allow_auto_apply,
        )
        for config in TRUST_LEVEL_CONFIGS.values()
    ]


# =============================================================================
# Pending Approvals Endpoints
# =============================================================================


@router.get("/pending-approvals", response_model=List[PendingApprovalResponse])
async def get_pending_approvals(
    proposal_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[PendingApprovalResponse]:
    """
    Listet ausstehende Genehmigungen.

    Zeigt alle Proposals die auf Bestätigung oder Timeout warten.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    # Parse proposal_type
    pt = None
    if proposal_type:
        try:
            pt = ProposalType(proposal_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Proposal-Typ: {proposal_type}",
            )

    service = get_delayed_acceptance_service(db)
    proposals = await service.get_pending_proposals(
        company_id=company_id,
        proposal_type=pt,
        limit=limit,
        offset=offset,
    )

    from app.core.datetime_utils import utc_now
    now = utc_now()

    return [
        PendingApprovalResponse(
            id=str(p.id),
            proposal_type=p.proposal_type.value,
            target_id=str(p.target_id),
            proposed_value=p.proposed_value,
            confidence=p.confidence,
            delay_hours=p.delay_hours,
            status=p.status.value,
            created_at=p.created_at,
            scheduled_at=p.scheduled_at,
            reasoning=p.reasoning,
            time_remaining_hours=max(0, (p.scheduled_at - now).total_seconds() / 3600) if p.scheduled_at > now else 0,
        )
        for p in proposals
    ]


@router.post("/approve/{proposal_id}", response_model=JSONDict)
async def approve_proposal(
    proposal_id: uuid.UUID,
    request: Optional[ApprovalActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Genehmigt einen Vorschlag manuell.

    Führt die vorgeschlagene Aktion sofort aus.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_delayed_acceptance_service(db)
    result = await service.approve_proposal(
        proposal_id=proposal_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return {
        "success": True,
        "message": result.message,
        "status": result.status.value,
        "can_rollback": result.can_rollback,
    }


@router.post("/reject/{proposal_id}", response_model=JSONDict)
async def reject_proposal(
    proposal_id: uuid.UUID,
    request: Optional[ApprovalActionRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Lehnt einen Vorschlag ab.

    Der Vorschlag wird nicht ausgeführt und als abgelehnt markiert.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    reason = request.reason if request else None

    service = get_delayed_acceptance_service(db)
    result = await service.reject_proposal(
        proposal_id=proposal_id,
        user_id=current_user.id,
        company_id=company_id,
        reason=reason,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return {
        "success": True,
        "message": result.message,
        "status": result.status.value,
    }


@router.post("/rollback/{proposal_id}", response_model=JSONDict)
async def rollback_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Macht einen ausgeführten Vorschlag rückgängig.

    Nur möglich innerhalb von 7 Tagen nach Ausführung.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_delayed_acceptance_service(db)
    result = await service.rollback_proposal(
        proposal_id=proposal_id,
        user_id=current_user.id,
        company_id=company_id,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return {
        "success": True,
        "message": result.message,
        "status": result.status.value,
    }


@router.get("/history", response_model=List[ProposalHistoryResponse])
async def get_proposal_history(
    target_id: Optional[uuid.UUID] = None,
    proposal_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ProposalHistoryResponse]:
    """
    Holt Proposal-Historie.

    Zeigt vergangene Proposals mit Status und Ausführungsdetails.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    # Parse proposal_type
    pt = None
    if proposal_type:
        try:
            pt = ProposalType(proposal_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Proposal-Typ: {proposal_type}",
            )

    # Parse status
    ps = None
    if status_filter:
        try:
            ps = ProposalStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ungültiger Status: {status_filter}",
            )

    service = get_delayed_acceptance_service(db)
    proposals = await service.get_proposal_history(
        company_id=company_id,
        target_id=target_id,
        proposal_type=pt,
        status=ps,
        days=days,
        limit=limit,
    )

    from app.core.datetime_utils import utc_now
    now = utc_now()

    return [
        ProposalHistoryResponse(
            id=str(p.id),
            proposal_type=p.proposal_type.value,
            target_id=str(p.target_id),
            proposed_value=p.proposed_value,
            confidence=p.confidence,
            status=p.status.value,
            created_at=p.created_at,
            scheduled_at=p.scheduled_at,
            executed_at=p.executed_at,
            executed_by=p.executed_by,
            can_rollback=(
                p.status in [ProposalStatus.APPROVED, ProposalStatus.AUTO_ACCEPTED]
                and p.rollback_until is not None
                and p.rollback_until > now
            ),
        )
        for p in proposals
    ]


@router.get("/statistics", response_model=JSONDict)
async def get_proposal_statistics(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Holt Statistiken über Proposals.

    Zeigt Verteilung nach Typ, Status und Confidence.
    """
    company_id = await get_user_company_id(db, current_user)

    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_delayed_acceptance_service(db)

    # Hole alle Proposals der letzten X Tage
    proposals = await service.get_proposal_history(
        company_id=company_id,
        days=days,
        limit=1000,
    )

    # Berechne Statistiken
    total = len(proposals)
    by_status = {}
    by_type = {}
    avg_confidence = 0.0
    auto_accepted_count = 0
    manual_approved_count = 0
    rejected_count = 0

    for p in proposals:
        # Nach Status
        status_key = p.status.value
        by_status[status_key] = by_status.get(status_key, 0) + 1

        # Nach Typ
        type_key = p.proposal_type.value
        by_type[type_key] = by_type.get(type_key, 0) + 1

        # Confidence
        avg_confidence += p.confidence

        # Counts
        if p.status == ProposalStatus.AUTO_ACCEPTED:
            auto_accepted_count += 1
        elif p.status == ProposalStatus.APPROVED:
            manual_approved_count += 1
        elif p.status == ProposalStatus.REJECTED:
            rejected_count += 1

    avg_confidence = avg_confidence / total if total > 0 else 0.0
    auto_rate = auto_accepted_count / total if total > 0 else 0.0
    approval_rate = (auto_accepted_count + manual_approved_count) / total if total > 0 else 0.0
    rejection_rate = rejected_count / total if total > 0 else 0.0

    return {
        "period_days": days,
        "total_proposals": total,
        "by_status": by_status,
        "by_type": by_type,
        "avg_confidence": round(avg_confidence, 4),
        "auto_acceptance_rate": round(auto_rate, 4),
        "approval_rate": round(approval_rate, 4),
        "rejection_rate": round(rejection_rate, 4),
        "pending_count": by_status.get("pending", 0),
    }


# =============================================================================
# Amount Tier Endpoints
# =============================================================================


@router.get("/amount-tiers", response_model=AmountTiersResponse, summary="Betrags-Freigabestufen abrufen")
async def get_amount_tiers(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AmountTiersResponse:
    """
    Gibt die konfigurierten Betrags-Freigabestufen zurück.

    Zeigt die aktuelle Konfiguration für betragsbasierte Auto-Approvals.
    """
    company_id = await get_user_company_id(db, user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    service = get_amount_tier_service(db)
    tiers = await service.get_tiers(company_id)

    # Check if custom or default
    is_default = len(tiers) == len(DEFAULT_TIERS) and all(
        t.name == dt.name and t.max_amount == dt.max_amount
        for t, dt in zip(tiers, DEFAULT_TIERS)
    )

    return AmountTiersResponse(
        tiers=[
            AmountTierSchema(
                name=t.name,
                max_amount=str(t.max_amount),
                approval_mode=t.approval_mode,
                min_trust_level=t.min_trust_level,
            )
            for t in tiers
        ],
        is_default=is_default,
    )


@router.put("/amount-tiers", response_model=AmountTiersResponse, summary="Betrags-Freigabestufen aktualisieren")
async def update_amount_tiers(
    request: AmountTiersUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("admin:full")),
) -> AmountTiersResponse:
    """
    Aktualisiert die Betrags-Freigabestufen für die Company.

    Validiert:
    - Mindestens 2 Stufen
    - Aufsteigende Obergrenzwerte
    - Letzte Stufe muss 'explicit' sein
    """
    company_id = await get_user_company_id(db, user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    try:
        from decimal import Decimal

        # Convert request tiers to service tiers
        tiers = [
            AmountTier(
                name=t.name,
                max_amount=Decimal(t.max_amount),
                approval_mode=t.approval_mode,
                min_trust_level=t.min_trust_level,
            )
            for t in request.tiers
        ]

        service = get_amount_tier_service(db)
        saved = await service.update_tiers(company_id, tiers)

        return AmountTiersResponse(
            tiers=[
                AmountTierSchema(
                    name=t.name,
                    max_amount=str(t.max_amount),
                    approval_mode=t.approval_mode,
                    min_trust_level=t.min_trust_level,
                )
                for t in saved
            ],
            is_default=False,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Aktualisieren der Betrags-Freigabestufen",
        )


@router.post("/amount-tiers/check", response_model=ApprovalModeResponse, summary="Freigabemodus ermitteln")
async def check_approval_mode(
    amount: float = Query(..., gt=0, description="Betrag in EUR"),
    trust_level: str = Query("assistance", description="Trust-Level"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApprovalModeResponse:
    """
    Ermittelt den Freigabemodus basierend auf Betrag und Trust-Level.

    Prüft welche Freigabestufe für einen bestimmten Betrag und Trust-Level
    angewendet werden soll.
    """
    company_id = await get_user_company_id(db, user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Company-Zuordnung gefunden",
        )

    from decimal import Decimal

    service = get_amount_tier_service(db)
    approval_mode = await service.get_approval_mode(
        company_id,
        Decimal(str(amount)),
        trust_level,
    )

    # Find the tier name
    tiers = await service.get_tiers(company_id)
    tier_name = next(
        (t.name for t in tiers if t.approval_mode == approval_mode),
        "Unbekannt",
    )

    return ApprovalModeResponse(
        approval_mode=approval_mode,
        tier_name=tier_name,
        amount=str(amount),
    )
