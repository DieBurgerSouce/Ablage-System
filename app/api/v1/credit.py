# -*- coding: utf-8 -*-
"""
Credit Management API Endpoints.

Endpoints für Bonitaetsprüfung und Kreditlimit-Management:
- Bonitaetsprüfung via Creditreform
- Kreditlimit-Verwaltung
- Risiko-Scoring
- Monitoring

Vision 2.0 Feature: Erweiterte Integrationen
Feinpoliert und durchdacht.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.db.models import User, Company
from app.services.external.creditreform_service import CreditreformService, CreditCheckResult
from app.services.external.credit_scoring_service import CreditScoringService, RiskLevel, CreditDecision
from app.services.external.credit_limit_manager import CreditLimitManager
from app.core.safe_errors import safe_error_detail, safe_error_log

import structlog

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/credit", tags=["Credit Management"])


# =============================================================================
# Request/Response Schemas
# =============================================================================

class CreditCheckRequest(BaseModel):
    """Request für Bonitaetsprüfung."""
    company_name: Optional[str] = Field(None, max_length=255)
    crefo_id: Optional[str] = Field(None, max_length=50)
    vat_id: Optional[str] = Field(None, max_length=50)
    street: Optional[str] = Field(None, max_length=255)
    postal_code: Optional[str] = Field(None, max_length=20)
    city: Optional[str] = Field(None, max_length=100)
    use_cache: bool = True


class CreditCheckResponse(BaseModel):
    """Response einer Bonitaetsprüfung."""
    crefo_id: str
    company_name: str
    legal_form: Optional[str]
    address: Optional[dict]
    credit_index: int
    credit_rating: str
    probability_of_default: float
    recommended_credit_limit: Optional[float]
    revenue: Optional[float]
    employees: Optional[int]
    founded_year: Optional[int]
    is_active: bool
    insolvency_status: Optional[str]
    last_updated: datetime
    warnings: List[str]
    negative_features: List[str]


class CreditScoreRequest(BaseModel):
    """Request für Score-Berechnung."""
    entity_id: UUID
    include_external: bool = True


class CreditScoreResponse(BaseModel):
    """Response der Score-Berechnung."""
    entity_id: str
    entity_name: str
    total_score: float
    risk_level: str
    factors: dict
    recommended_credit_limit: float
    base_credit_limit: float
    decision: str
    decision_reason: str
    calculated_at: str
    warnings: List[str]


class CreditLimitResponse(BaseModel):
    """Response für Kreditlimit."""
    entity_id: str
    entity_name: str
    credit_limit: float
    utilized_amount: float
    available_amount: float
    utilization_percent: float
    last_updated: Optional[str]
    risk_level: Optional[str]
    next_review: Optional[str]


class LimitUpdateRequest(BaseModel):
    """Request für Limit-Aktualisierung."""
    include_external: bool = False


class LimitAdjustRequest(BaseModel):
    """Request für manuelle Limit-Anpassung."""
    new_limit: float = Field(..., ge=0, le=10000000)
    reason: str = Field(..., max_length=50)
    reason_details: Optional[str] = Field(None, max_length=500)


class LimitHistoryEntry(BaseModel):
    """Eintrag in der Limit-Historie."""
    previous: float
    new: float
    change_percent: float
    reason: str
    changed_at: str
    changed_by: str
    manual: bool = False


class EntityReviewItem(BaseModel):
    """Entity die Review benötigt."""
    entity_id: str
    entity_name: str
    reason: str
    current_limit: float
    risk_level: Optional[str] = None


class BatchUpdateResponse(BaseModel):
    """Response für Batch-Update."""
    total_entities: int
    updated: int
    errors: int
    changes: List[dict]


# =============================================================================
# Helper Functions
# =============================================================================

def _credit_result_to_response(result: CreditCheckResult) -> CreditCheckResponse:
    """Konvertiere CreditCheckResult zu Response."""
    return CreditCheckResponse(
        crefo_id=result.crefo_id,
        company_name=result.company_name,
        legal_form=result.legal_form,
        address=result.address,
        credit_index=result.credit_index,
        credit_rating=result.credit_rating,
        probability_of_default=result.probability_of_default,
        recommended_credit_limit=float(result.recommended_credit_limit) if result.recommended_credit_limit else None,
        revenue=float(result.revenue) if result.revenue else None,
        employees=result.employees,
        founded_year=result.founded_year,
        is_active=result.is_active,
        insolvency_status=result.insolvency_status,
        last_updated=result.last_updated,
        warnings=result.warnings,
        negative_features=result.negative_features,
    )


# =============================================================================
# Credit Check Endpoints
# =============================================================================

@router.post("/check", response_model=CreditCheckResponse)
async def check_credit(
    data: CreditCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CreditCheckResponse:
    """
    Führe Bonitaetsprüfung via Creditreform durch.

    Benötigt mindestens eine Identifikation:
    - company_name: Firmenname
    - crefo_id: Creditreform-ID (falls bekannt)
    - vat_id: USt-ID

    Das Ergebnis wird 24 Stunden gecacht.
    """
    if not any([data.company_name, data.crefo_id, data.vat_id]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens company_name, crefo_id oder vat_id erforderlich",
        )

    address = None
    if data.street or data.postal_code or data.city:
        address = {
            "street": data.street,
            "postal_code": data.postal_code,
            "city": data.city,
            "country": "DE",
        }

    service = CreditreformService()

    try:
        result = await service.check_credit(
            company_name=data.company_name,
            crefo_id=data.crefo_id,
            vat_id=data.vat_id,
            address=address,
            use_cache=data.use_cache,
        )
    except Exception as e:
        logger.error("Credit check failed", **safe_error_log(e, "Bonitaetsprüfung"))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=safe_error_detail(e, "Bonitaetsprüfung"),
        )

    logger.info(
        "Credit check completed",
        crefo_id=result.crefo_id,
        credit_index=result.credit_index,
    )

    return _credit_result_to_response(result)


@router.get("/entity/{entity_id}/check", response_model=CreditCheckResponse)
async def check_entity_credit(
    entity_id: UUID,
    use_cache: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CreditCheckResponse:
    """
    Bonitaetsprüfung für eine bekannte Entity.

    Verwendet die in der Entity gespeicherten Daten.
    """
    from app.db.models import BusinessEntity
    from sqlalchemy import select, and_

    result = await db.execute(
        select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company.company_id,
            )
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity nicht gefunden",
        )

    service = CreditreformService()

    try:
        check_result = await service.check_credit(
            company_name=entity.name,
            vat_id=getattr(entity, "vat_id", None),
            use_cache=use_cache,
        )
    except Exception as e:
        logger.error("Entity credit check failed", **safe_error_log(e, "Entity-Bonitaetsprüfung"))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=safe_error_detail(e, "Bonitaetsprüfung"),
        )

    return _credit_result_to_response(check_result)


# =============================================================================
# Credit Score Endpoints
# =============================================================================

@router.get("/entity/{entity_id}/score", response_model=CreditScoreResponse)
async def get_entity_score(
    entity_id: UUID,
    include_external: bool = Query(True, description="Externe Daten einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CreditScoreResponse:
    """
    Berechne internen Kredit-Score für Entity.

    Kombiniert:
    - Externe Bonitaetsdaten (Creditreform)
    - Interne Zahlungshistorie
    - Beziehungsdauer
    - Transaktionsvolumen
    - Dokumentenqualitaet
    """
    service = CreditScoringService(db)

    try:
        result = await service.calculate_score(
            entity_id=entity_id,
            company_id=company.company_id,
            include_external=include_external,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Score-Berechnung"),
        )
    except Exception as e:
        logger.error("Score calculation failed", **safe_error_log(e, "Score-Berechnung"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Score-Berechnung"),
        )

    return CreditScoreResponse(**result)


@router.post("/entity/{entity_id}/score/refresh", response_model=CreditScoreResponse)
async def refresh_entity_score(
    entity_id: UUID,
    data: CreditScoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CreditScoreResponse:
    """
    Aktualisiere Kredit-Score (erzwingt Neuberechnung).
    """
    service = CreditScoringService(db)

    result = await service.calculate_score(
        entity_id=entity_id,
        company_id=company.company_id,
        include_external=data.include_external,
    )

    logger.info(
        "Credit score refreshed",
        entity_id=str(entity_id),
        score=result["total_score"],
    )

    return CreditScoreResponse(**result)


# =============================================================================
# Credit Limit Endpoints
# =============================================================================

@router.get("/entity/{entity_id}/limit", response_model=CreditLimitResponse)
async def get_credit_limit(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> CreditLimitResponse:
    """
    Hole aktuelles Kreditlimit für Entity.
    """
    manager = CreditLimitManager(db)

    try:
        result = await manager.get_credit_limit(
            entity_id=entity_id,
            company_id=company.company_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Kreditlimit-Abruf"),
        )

    return CreditLimitResponse(**result)


@router.post("/entity/{entity_id}/limit/update", response_model=dict)
async def update_credit_limit(
    entity_id: UUID,
    data: LimitUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Berechne und aktualisiere Kreditlimit.

    Automatische Anpassungen bis +10% / -20%.
    Größere Änderungen erfordern manuelle Prüfung.
    """
    manager = CreditLimitManager(db)

    try:
        result = await manager.calculate_and_update_limit(
            entity_id=entity_id,
            company_id=company.company_id,
            user_id=current_user.id,
            include_external=data.include_external,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Limit-Aktualisierung"),
        )
    except Exception as e:
        logger.error("Limit update failed", **safe_error_log(e, "Limit-Aktualisierung"))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Limit-Aktualisierung"),
        )

    logger.info(
        "Credit limit updated",
        entity_id=str(entity_id),
        new_limit=result["new_limit"],
    )

    return result


@router.post("/entity/{entity_id}/limit/adjust", response_model=dict)
async def adjust_credit_limit(
    entity_id: UUID,
    data: LimitAdjustRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Manuelle Kreditlimit-Anpassung.

    Erfordert Begruendung.
    """
    manager = CreditLimitManager(db)

    try:
        result = await manager.manual_adjust_limit(
            entity_id=entity_id,
            company_id=company.company_id,
            new_limit=Decimal(str(data.new_limit)),
            user_id=current_user.id,
            reason=data.reason,
            reason_details=data.reason_details,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Limit-Anpassung"),
        )

    logger.info(
        "Credit limit manually adjusted",
        entity_id=str(entity_id),
        new_limit=data.new_limit,
        reason=data.reason,
    )

    return result


@router.get("/entity/{entity_id}/limit/history", response_model=List[LimitHistoryEntry])
async def get_limit_history(
    entity_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[LimitHistoryEntry]:
    """
    Hole Limit-Historie für Entity.
    """
    manager = CreditLimitManager(db)

    history = await manager.get_limit_history(
        entity_id=entity_id,
        company_id=company.company_id,
        limit=limit,
    )

    return [LimitHistoryEntry(**h) for h in history]


# =============================================================================
# Review and Batch Endpoints
# =============================================================================

@router.get("/limits/review", response_model=List[EntityReviewItem])
async def get_entities_for_review(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[EntityReviewItem]:
    """
    Hole Entities die Review benötigen.

    Gruende:
    - Initiales Limit setzen
    - Grosse Limit-Änderung genehmigen
    - Planmaessige Überprüfung fällig
    """
    manager = CreditLimitManager(db)

    entities = await manager.get_entities_for_review(
        company_id=company.company_id,
    )

    return [EntityReviewItem(**e) for e in entities]


@router.post("/limits/batch-update", response_model=BatchUpdateResponse)
async def batch_update_limits(
    include_external: bool = Query(False, description="Externe Daten einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> BatchUpdateResponse:
    """
    Batch-Aktualisierung aller Kreditlimits.

    Achtung: Kann bei vielen Entities lange dauern.
    Mit include_external=true können Kosten entstehen.
    """
    manager = CreditLimitManager(db)

    result = await manager.batch_update_limits(
        company_id=company.company_id,
        include_external=include_external,
    )

    logger.info(
        "Batch credit limit update",
        updated=result["updated"],
        errors=result["errors"],
    )

    return BatchUpdateResponse(**result)


# =============================================================================
# Monitoring Endpoints
# =============================================================================

@router.get("/entity/{entity_id}/monitoring/events", response_model=List[dict])
async def get_monitoring_events(
    entity_id: UUID,
    since: Optional[datetime] = Query(None, description="Nur Ereignisse seit"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> List[dict]:
    """
    Hole Monitoring-Ereignisse für Entity.
    """
    from app.db.models import BusinessEntity
    from sqlalchemy import select, and_

    # Hole Entity für crefo_id
    result = await db.execute(
        select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company.company_id,
            )
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity nicht gefunden",
        )

    # Hole crefo_id aus Metadata
    metadata = entity.metadata or {}
    crefo_id = metadata.get("credit_limit", {}).get("crefo_id")

    if not crefo_id:
        return []

    service = CreditreformService()
    events = await service.get_monitoring_events(crefo_id, since)

    return [e.model_dump() for e in events]


@router.post("/entity/{entity_id}/monitoring/start", response_model=dict)
async def start_monitoring(
    entity_id: UUID,
    webhook_url: Optional[str] = Query(None, description="Webhook für Benachrichtigungen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Starte Monitoring für Entity.

    Überwacht:
    - Insolvenz-Ereignisse
    - Adressänderungen
    - Management-Wechsel
    - Rating-Änderungen
    """
    from app.db.models import BusinessEntity
    from sqlalchemy import select, and_

    result = await db.execute(
        select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company.company_id,
            )
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity nicht gefunden",
        )

    # Hole oder erstelle crefo_id
    metadata = entity.metadata or {}
    crefo_id = metadata.get("credit_limit", {}).get("crefo_id")

    if not crefo_id:
        # Führe zuerst Credit Check durch
        service = CreditreformService()
        check_result = await service.check_credit(company_name=entity.name)
        crefo_id = check_result.crefo_id

        # Speichere crefo_id
        if "credit_limit" not in metadata:
            metadata["credit_limit"] = {}
        metadata["credit_limit"]["crefo_id"] = crefo_id
        entity.metadata = metadata
        await db.flush()

    # Starte Monitoring
    service = CreditreformService()
    monitoring_result = await service.start_monitoring(crefo_id, webhook_url)

    await db.commit()

    logger.info(
        "Credit monitoring started",
        entity_id=str(entity_id),
        crefo_id=crefo_id,
    )

    return monitoring_result


@router.delete("/entity/{entity_id}/monitoring", status_code=status.HTTP_204_NO_CONTENT)
async def stop_monitoring(
    entity_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> None:
    """
    Stoppe Monitoring für Entity.
    """
    from app.db.models import BusinessEntity
    from sqlalchemy import select, and_

    result = await db.execute(
        select(BusinessEntity).where(
            and_(
                BusinessEntity.id == entity_id,
                BusinessEntity.company_id == company.company_id,
            )
        )
    )
    entity = result.scalar_one_or_none()

    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity nicht gefunden",
        )

    metadata = entity.metadata or {}
    crefo_id = metadata.get("credit_limit", {}).get("crefo_id")

    if crefo_id:
        service = CreditreformService()
        await service.stop_monitoring(crefo_id)

    logger.info(
        "Credit monitoring stopped",
        entity_id=str(entity_id),
    )


# =============================================================================
# Statistics Endpoints
# =============================================================================

@router.get("/statistics", response_model=dict)
async def get_credit_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> dict:
    """
    Kredit-Statistiken für das Unternehmen.
    """
    from app.db.models import BusinessEntity
    from sqlalchemy import select

    result = await db.execute(
        select(BusinessEntity)
        .where(BusinessEntity.company_id == company.company_id)
    )
    entities = list(result.scalars().all())

    # Aggregiere Daten
    by_risk_level = {}
    total_limit = 0
    total_utilized = 0
    entities_with_limit = 0
    review_needed = 0

    for entity in entities:
        metadata = entity.metadata or {}
        credit_data = metadata.get("credit_limit", {})

        if credit_data:
            entities_with_limit += 1
            limit = credit_data.get("amount", 0)
            total_limit += limit

            risk = credit_data.get("risk_level", "unknown")
            by_risk_level[risk] = by_risk_level.get(risk, 0) + 1

            if credit_data.get("requires_review"):
                review_needed += 1

    return {
        "total_entities": len(entities),
        "entities_with_limit": entities_with_limit,
        "entities_without_limit": len(entities) - entities_with_limit,
        "total_credit_limit": total_limit,
        "by_risk_level": by_risk_level,
        "review_needed": review_needed,
    }
