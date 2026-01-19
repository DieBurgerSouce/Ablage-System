"""
Tenant Rate Limits API Endpoints.

API fuer Multi-Tenant Rate Limiting Konfiguration und Metriken.

Endpoints:
- GET /tenant-limits - Eigene Limits abrufen
- GET /tenant-limits/{company_id} - Admin: Limits einer Company
- PATCH /tenant-limits/{company_id} - Admin: Limits anpassen
- DELETE /tenant-limits/{company_id}/custom - Admin: Custom Limits loeschen
- GET /tenant-limits/{company_id}/usage - Usage Metriken
- GET /tenant-limits/{company_id}/violations - Rate Limit Violations

Created: 2026-01-19
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.tenant_rate_limit_service import (
    TenantRateLimitService,
    get_tenant_rate_limit_service,
)

router = APIRouter(prefix="/tenant-limits", tags=["Tenant Rate Limits"])


# ==================== Pydantic Models ====================


class TierDefaultsResponse(BaseModel):
    """Tier-Default-Konfiguration."""
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    ocr_requests_per_hour: int
    batch_requests_per_hour: int
    burst_limit: int
    max_users: int
    max_documents_per_month: int
    max_storage_gb: int
    features: List[str]


class CustomLimitResponse(BaseModel):
    """Custom Rate Limit Konfiguration."""
    id: str
    endpoint_pattern: str
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_limit: int
    is_custom: bool


class CompanyLimitsResponse(BaseModel):
    """Vollstaendige Rate Limit Konfiguration einer Company."""
    company_id: str
    company_name: str
    subscription_tier: str
    subscription_expires_at: Optional[str] = None
    tier_defaults: TierDefaultsResponse
    custom_limits: List[CustomLimitResponse]
    max_users: int
    max_documents_per_month: int
    max_storage_gb: int
    features_enabled: List[str]


class UpdateLimitRequest(BaseModel):
    """Request zum Aktualisieren eines Rate Limits."""
    endpoint_pattern: str = Field(..., description="Endpoint-Pattern (z.B. /api/v1/documents/*)")
    requests_per_minute: Optional[int] = Field(None, ge=1, le=10000)
    requests_per_hour: Optional[int] = Field(None, ge=1, le=100000)
    requests_per_day: Optional[int] = Field(None, ge=1, le=1000000)
    burst_limit: Optional[int] = Field(None, ge=1, le=1000)


class UsageTimelineItem(BaseModel):
    """Ein Datenpunkt in der Usage-Timeline."""
    period_start: str
    total_requests: int
    rate_limited: int
    documents_processed: int


class UsageSummaryResponse(BaseModel):
    """Usage Summary fuer eine Company."""
    company_id: str
    period_type: str
    data_points: int
    total_requests: int
    rate_limited_requests: int
    rate_limit_percentage: float
    avg_response_time_ms: Optional[float] = None
    documents_processed: int
    pages_processed: int
    storage_used_bytes: int
    active_users: int
    timeline: List[UsageTimelineItem]


class ViolationResponse(BaseModel):
    """Eine Rate-Limit-Violation."""
    id: str
    endpoint: str
    method: str
    ip_address: str
    limit_type: str
    limit_value: int
    current_count: int
    occurred_at: str


class RateLimitCheckResponse(BaseModel):
    """Ergebnis einer Rate-Limit-Pruefung."""
    allowed: bool
    remaining: int
    limit: int
    reset_at: str
    limit_type: str
    retry_after: Optional[int] = None


# ==================== Endpoints ====================


@router.get(
    "",
    response_model=CompanyLimitsResponse,
    summary="Eigene Rate Limits abrufen",
    description="Zeigt die Rate Limit Konfiguration der eigenen Company."
)
async def get_own_limits(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Rate Limits fuer die Company des aktuellen Users."""
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt"
        )

    service = TenantRateLimitService(db)
    try:
        limits = await service.get_company_limits(current_user.current_company_id)
        return limits
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get(
    "/{company_id}",
    response_model=CompanyLimitsResponse,
    summary="Rate Limits einer Company (Admin)",
    description="Admin: Zeigt die Rate Limit Konfiguration einer beliebigen Company."
)
async def get_company_limits(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Rate Limits fuer eine spezifische Company (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren koennen fremde Company-Limits einsehen"
        )

    service = TenantRateLimitService(db)
    try:
        limits = await service.get_company_limits(company_id)
        return limits
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.patch(
    "/{company_id}",
    response_model=CustomLimitResponse,
    summary="Rate Limit anpassen (Admin)",
    description="Admin: Erstellt oder aktualisiert ein Custom Rate Limit."
)
async def update_company_limit(
    company_id: UUID,
    request: UpdateLimitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Erstelle oder aktualisiere Custom Rate Limit (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren koennen Rate Limits anpassen"
        )

    service = TenantRateLimitService(db)
    try:
        limit = await service.update_company_limit(
            company_id=company_id,
            endpoint_pattern=request.endpoint_pattern,
            requests_per_minute=request.requests_per_minute,
            requests_per_hour=request.requests_per_hour,
            requests_per_day=request.requests_per_day,
            burst_limit=request.burst_limit,
            created_by_id=current_user.id,
        )
        await db.commit()
        await db.refresh(limit)

        return CustomLimitResponse(
            id=str(limit.id),
            endpoint_pattern=limit.endpoint_pattern,
            requests_per_minute=limit.requests_per_minute,
            requests_per_hour=limit.requests_per_hour,
            requests_per_day=limit.requests_per_day,
            burst_limit=limit.burst_limit,
            is_custom=limit.is_custom,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.delete(
    "/{company_id}/custom",
    summary="Custom Limits zuruecksetzen (Admin)",
    description="Admin: Loescht alle Custom Limits und setzt auf Tier-Defaults zurueck."
)
async def reset_company_limits(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Setze alle Custom Limits auf Tier-Defaults zurueck (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren koennen Limits zuruecksetzen"
        )

    service = TenantRateLimitService(db)
    count = await service.reset_to_tier_defaults(company_id)
    await db.commit()

    return {
        "message": f"{count} Custom-Limits geloescht",
        "company_id": str(company_id),
        "reset_to": "tier_defaults"
    }


@router.get(
    "/{company_id}/usage",
    response_model=UsageSummaryResponse,
    summary="Usage Metriken abrufen",
    description="Zeigt Nutzungsstatistiken fuer eine Company."
)
async def get_usage_metrics(
    company_id: UUID,
    period_type: str = Query("daily", regex="^(hourly|daily|monthly)$"),
    days_back: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Usage Metriken fuer eine Company."""
    # Permission Check: Eigene Company oder Admin
    if not current_user.is_admin and current_user.current_company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff auf fremde Company-Metriken nicht erlaubt"
        )

    service = TenantRateLimitService(db)
    usage = await service.get_usage_summary(
        company_id=company_id,
        period_type=period_type,
        days_back=days_back,
    )
    return usage


@router.get(
    "/{company_id}/violations",
    response_model=List[ViolationResponse],
    summary="Rate Limit Violations abrufen",
    description="Zeigt Rate-Limit-Verletzungen fuer eine Company."
)
async def get_violations(
    company_id: UUID,
    hours_back: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Rate-Limit-Violations fuer eine Company."""
    # Permission Check: Eigene Company oder Admin
    if not current_user.is_admin and current_user.current_company_id != company_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Zugriff auf fremde Company-Violations nicht erlaubt"
        )

    service = TenantRateLimitService(db)
    violations = await service.get_violation_history(
        company_id=company_id,
        hours_back=hours_back,
        limit=limit,
    )
    return violations


@router.post(
    "/check",
    response_model=RateLimitCheckResponse,
    summary="Rate Limit pruefen",
    description="Prueft ob ein Request erlaubt waere (ohne Inkrementierung)."
)
async def check_rate_limit(
    endpoint: str = Query(..., description="Endpoint zu pruefen"),
    method: str = Query("GET", description="HTTP Method"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pruefe ob ein Request das Rate Limit ueberschreiten wuerde."""
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt"
        )

    service = TenantRateLimitService(db)
    result = await service.check_rate_limit(
        company_id=current_user.current_company_id,
        user_id=current_user.id,
        endpoint=endpoint,
        method=method,
        ip_address="127.0.0.1",  # Dummy fuer Check
    )
    return result
