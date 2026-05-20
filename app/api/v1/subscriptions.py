"""
Subscription Management API Endpoints.

API für Multi-Tenant Subscription-Verwaltung und Billing-Vorbereitung.

Endpoints:
- GET /subscriptions - Eigene Subscription abrufen
- GET /subscriptions/{company_id} - Admin: Subscription einer Company
- PATCH /subscriptions/{company_id}/tier - Admin: Tier ändern
- PATCH /subscriptions/{company_id}/billing - Admin: Billing-Infos aktualisieren
- POST /subscriptions/{company_id}/extend - Admin: Subscription verlängern
- GET /subscriptions/tiers - Verfügbare Tiers mit Features
- GET /subscriptions/statistics - Admin: Globale Subscription-Statistiken

Created: 2026-01-19
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User, Company, SubscriptionTierDefaults
from app.services.tenant_rate_limit_service import DEFAULT_TIER_CONFIG

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


# ==================== Pydantic Models ====================


class BillingAddressResponse(BaseModel):
    """Rechnungsadresse."""
    street: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = "DE"


class SubscriptionResponse(BaseModel):
    """Subscription-Informationen einer Company."""
    company_id: str
    company_name: str
    subscription_tier: str
    subscription_started_at: Optional[str] = None
    subscription_expires_at: Optional[str] = None
    is_expired: bool
    days_remaining: Optional[int] = None
    billing_email: Optional[str] = None
    billing_address: Optional[BillingAddressResponse] = None
    payment_method: Optional[str] = None
    max_users: int
    max_documents_per_month: int
    max_storage_gb: int
    features_enabled: List[str]


class TierInfoResponse(BaseModel):
    """Informationen zu einem Subscription-Tier."""
    tier: str
    display_name: str
    description: str
    max_users: int
    max_documents_per_month: int
    max_storage_gb: int
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    ocr_requests_per_hour: int
    features: List[str]
    price_monthly_eur: Optional[float] = None
    price_yearly_eur: Optional[float] = None


class ChangeTierRequest(BaseModel):
    """Request zum Ändern des Subscription-Tiers."""
    new_tier: str = Field(..., pattern="^(free|basic|professional|enterprise)$")
    reason: Optional[str] = Field(None, max_length=500)


class UpdateBillingRequest(BaseModel):
    """Request zum Aktualisieren der Billing-Informationen."""
    billing_email: Optional[EmailStr] = None
    billing_address: Optional[BillingAddressResponse] = None
    payment_method: Optional[str] = Field(None, pattern="^(invoice|sepa|card)$")


class ExtendSubscriptionRequest(BaseModel):
    """Request zum Verlängern einer Subscription."""
    months: int = Field(..., ge=1, le=36)
    reason: Optional[str] = Field(None, max_length=500)


class SubscriptionStatisticsResponse(BaseModel):
    """Globale Subscription-Statistiken (Admin)."""
    total_companies: int
    by_tier: dict
    active_subscriptions: int
    expiring_soon: int  # In nächsten 30 Tagen
    expired: int


# ==================== Helper Functions ====================


def _serialize_subscription(company: Company) -> SubscriptionResponse:
    """Serialisiere Company zu SubscriptionResponse."""
    now = datetime.now(timezone.utc)
    expires_at = company.subscription_expires_at
    is_expired = expires_at is not None and expires_at < now
    days_remaining = None

    if expires_at and not is_expired:
        days_remaining = (expires_at - now).days

    billing_address = None
    if company.billing_address:
        billing_address = BillingAddressResponse(**company.billing_address)

    return SubscriptionResponse(
        company_id=str(company.id),
        company_name=company.name,
        subscription_tier=company.subscription_tier or "free",
        subscription_started_at=company.subscription_started_at.isoformat() if company.subscription_started_at else None,
        subscription_expires_at=expires_at.isoformat() if expires_at else None,
        is_expired=is_expired,
        days_remaining=days_remaining,
        billing_email=company.billing_email,
        billing_address=billing_address,
        payment_method=company.payment_method,
        max_users=company.max_users,
        max_documents_per_month=company.max_documents_per_month,
        max_storage_gb=company.max_storage_gb,
        features_enabled=company.features_enabled or [],
    )


# ==================== Endpoints ====================


@router.get(
    "",
    response_model=SubscriptionResponse,
    summary="Eigene Subscription abrufen",
    description="Zeigt die Subscription-Informationen der eigenen Company."
)
async def get_own_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Subscription für die Company des aktuellen Users."""
    if not current_user.current_company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Company ausgewaehlt"
        )

    result = await db.execute(
        select(Company).where(Company.id == current_user.current_company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company nicht gefunden"
        )

    return _serialize_subscription(company)


@router.get(
    "/tiers",
    response_model=List[TierInfoResponse],
    summary="Verfügbare Subscription-Tiers",
    description="Listet alle verfügbaren Tiers mit Features und Preisen."
)
async def get_available_tiers(
    db: AsyncSession = Depends(get_db),
):
    """Hole alle verfügbaren Subscription-Tiers."""
    # Versuche aus DB zu laden, sonst Default-Config
    result = await db.execute(select(SubscriptionTierDefaults))
    db_tiers = {t.tier: t for t in result.scalars().all()}

    tiers = []
    tier_display = {
        "free": ("Free", "Kostenloser Einstieg für kleine Teams"),
        "basic": ("Basic", "Für wachsende Unternehmen"),
        "professional": ("Professional", "Für professionelle Anforderungen"),
        "enterprise": ("Enterprise", "Massgeschneidert für Grossunternehmen"),
    }

    for tier_key, config in DEFAULT_TIER_CONFIG.items():
        display_name, description = tier_display.get(tier_key, (tier_key.title(), ""))

        # Preis aus DB falls vorhanden
        price_monthly = None
        price_yearly = None
        if tier_key in db_tiers:
            db_tier = db_tiers[tier_key]
            price_monthly = float(db_tier.price_monthly_eur) if db_tier.price_monthly_eur else None
            price_yearly = float(db_tier.price_yearly_eur) if db_tier.price_yearly_eur else None

        tiers.append(TierInfoResponse(
            tier=tier_key,
            display_name=display_name,
            description=description,
            max_users=config["max_users"],
            max_documents_per_month=config["max_documents_per_month"],
            max_storage_gb=config["max_storage_gb"],
            requests_per_minute=config["requests_per_minute"],
            requests_per_hour=config["requests_per_hour"],
            requests_per_day=config["requests_per_day"],
            ocr_requests_per_hour=config["ocr_requests_per_hour"],
            features=config["features"],
            price_monthly_eur=price_monthly,
            price_yearly_eur=price_yearly,
        ))

    return tiers


@router.get(
    "/statistics",
    response_model=SubscriptionStatisticsResponse,
    summary="Subscription-Statistiken (Admin)",
    description="Globale Übersicht über alle Subscriptions."
)
async def get_subscription_statistics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole globale Subscription-Statistiken (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Statistiken einsehen"
        )

    now = datetime.now(timezone.utc)
    in_30_days = now + timedelta(days=30)

    # Total Companies
    total_result = await db.execute(
        select(func.count()).select_from(Company).where(Company.deleted_at.is_(None))
    )
    total_companies = total_result.scalar() or 0

    # By Tier
    tier_result = await db.execute(
        select(Company.subscription_tier, func.count())
        .where(Company.deleted_at.is_(None))
        .group_by(Company.subscription_tier)
    )
    by_tier = {tier or "free": count for tier, count in tier_result.all()}

    # Active (not expired)
    active_result = await db.execute(
        select(func.count()).select_from(Company).where(
            Company.deleted_at.is_(None),
            (Company.subscription_expires_at.is_(None)) | (Company.subscription_expires_at > now)
        )
    )
    active_subscriptions = active_result.scalar() or 0

    # Expiring soon (in next 30 days)
    expiring_result = await db.execute(
        select(func.count()).select_from(Company).where(
            Company.deleted_at.is_(None),
            Company.subscription_expires_at.isnot(None),
            Company.subscription_expires_at > now,
            Company.subscription_expires_at <= in_30_days
        )
    )
    expiring_soon = expiring_result.scalar() or 0

    # Expired
    expired_result = await db.execute(
        select(func.count()).select_from(Company).where(
            Company.deleted_at.is_(None),
            Company.subscription_expires_at.isnot(None),
            Company.subscription_expires_at < now
        )
    )
    expired = expired_result.scalar() or 0

    return SubscriptionStatisticsResponse(
        total_companies=total_companies,
        by_tier=by_tier,
        active_subscriptions=active_subscriptions,
        expiring_soon=expiring_soon,
        expired=expired,
    )


@router.get(
    "/{company_id}",
    response_model=SubscriptionResponse,
    summary="Subscription einer Company (Admin)",
    description="Admin: Zeigt die Subscription-Informationen einer beliebigen Company."
)
async def get_company_subscription(
    company_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hole Subscription für eine spezifische Company (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können fremde Subscriptions einsehen"
        )

    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company nicht gefunden"
        )

    return _serialize_subscription(company)


@router.patch(
    "/{company_id}/tier",
    response_model=SubscriptionResponse,
    summary="Tier ändern (Admin)",
    description="Admin: Ändert den Subscription-Tier einer Company."
)
async def change_subscription_tier(
    company_id: UUID,
    request: ChangeTierRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ändere den Subscription-Tier (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Tiers ändern"
        )

    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company nicht gefunden"
        )

    old_tier = company.subscription_tier
    new_tier = request.new_tier

    # Tier-Defaults anwenden
    if new_tier in DEFAULT_TIER_CONFIG:
        tier_config = DEFAULT_TIER_CONFIG[new_tier]
        company.subscription_tier = new_tier
        company.max_users = tier_config["max_users"]
        company.max_documents_per_month = tier_config["max_documents_per_month"]
        company.max_storage_gb = tier_config["max_storage_gb"]
        company.features_enabled = tier_config["features"]

        # Bei Upgrade: Subscription-Start setzen
        if not company.subscription_started_at:
            company.subscription_started_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(company)

    return _serialize_subscription(company)


@router.patch(
    "/{company_id}/billing",
    response_model=SubscriptionResponse,
    summary="Billing-Infos aktualisieren (Admin)",
    description="Admin: Aktualisiert die Billing-Informationen einer Company."
)
async def update_billing_info(
    company_id: UUID,
    request: UpdateBillingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Aktualisiere Billing-Informationen (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Billing-Infos ändern"
        )

    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company nicht gefunden"
        )

    if request.billing_email is not None:
        company.billing_email = request.billing_email

    if request.billing_address is not None:
        company.billing_address = request.billing_address.model_dump()

    if request.payment_method is not None:
        company.payment_method = request.payment_method

    await db.commit()
    await db.refresh(company)

    return _serialize_subscription(company)


@router.post(
    "/{company_id}/extend",
    response_model=SubscriptionResponse,
    summary="Subscription verlängern (Admin)",
    description="Admin: Verlängert die Subscription einer Company."
)
async def extend_subscription(
    company_id: UUID,
    request: ExtendSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verlängere Subscription (Admin only)."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Nur Administratoren können Subscriptions verlängern"
        )

    result = await db.execute(
        select(Company).where(Company.id == company_id)
    )
    company = result.scalar_one_or_none()

    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company nicht gefunden"
        )

    now = datetime.now(timezone.utc)

    # Berechne neues Ablaufdatum
    if company.subscription_expires_at and company.subscription_expires_at > now:
        # Verlängere ab aktuellem Ablaufdatum
        new_expires = company.subscription_expires_at + timedelta(days=30 * request.months)
    else:
        # Verlängere ab jetzt
        new_expires = now + timedelta(days=30 * request.months)

    company.subscription_expires_at = new_expires

    # Falls keine Start-Zeit, setze jetzt
    if not company.subscription_started_at:
        company.subscription_started_at = now

    await db.commit()
    await db.refresh(company)

    return _serialize_subscription(company)
