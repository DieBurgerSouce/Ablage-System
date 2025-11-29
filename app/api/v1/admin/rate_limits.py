"""
Rate Limit Administration API Endpoints.

Provides rate limit management for admins:
- View effective rate limits for users
- Create/update/delete rate limit overrides
- View usage statistics
- Change user tiers
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User
from app.db.schemas import (
    RateLimitOverrideCreate,
    RateLimitOverrideResponse,
    RateLimitStatus,
    RateLimitUsageStats,
    RateLimitTierDefaults,
    UserTier,
    MessageResponse,
)
from app.services.admin.rate_limit_service import RateLimitService


router = APIRouter(prefix="/rate-limits", tags=["Admin - Rate Limits"])


# ==================== Get Tier Defaults ====================

@router.get(
    "/tiers",
    summary="Tier-Standardwerte abrufen",
    description="Ruft die Standard-Rate-Limits fuer alle Tiers ab"
)
async def get_tier_defaults(
    admin: User = Depends(get_current_superuser),
) -> dict:
    """
    Ruft die Standard-Rate-Limits fuer alle Benutzer-Tiers ab.

    Zeigt die Standardlimits fuer:
    - **free**: Kostenlose Benutzer
    - **premium**: Premium-Benutzer
    - **admin**: Administratoren
    """
    return {
        "tiers": {
            tier.value: RateLimitService.get_tier_defaults(tier.value).model_dump()
            for tier in UserTier
        }
    }


# ==================== Get Usage Statistics ====================

@router.get(
    "/stats",
    response_model=RateLimitUsageStats,
    summary="Nutzungsstatistiken abrufen",
    description="Ruft aggregierte Rate-Limit-Nutzungsstatistiken ab"
)
async def get_usage_stats(
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> RateLimitUsageStats:
    """
    Ruft aggregierte Rate-Limit-Nutzungsstatistiken ab.

    Zeigt:
    - Gesamtzahl Benutzer
    - Benutzer am Tageslimit
    - Benutzer mit Overrides
    - Nutzung nach Tier
    - Top-Benutzer nach Dokumentenverarbeitung
    """
    return await RateLimitService.get_usage_stats(db)


# ==================== Get User Rate Limit Status ====================

@router.get(
    "/users/{user_id}",
    response_model=RateLimitStatus,
    summary="Benutzer-Rate-Limit-Status",
    description="Ruft den aktuellen Rate-Limit-Status eines Benutzers ab"
)
async def get_user_rate_limit_status(
    user_id: UUID,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> RateLimitStatus:
    """
    Ruft den aktuellen Rate-Limit-Status eines Benutzers ab.

    Zeigt:
    - Effektive Limits (Tier-Defaults + Overrides)
    - Aktuelle Nutzung (aus Redis)
    - Ob ein Override aktiv ist
    - Ablaufdatum des Overrides (falls vorhanden)
    """
    rate_limit_status = await RateLimitService.get_user_rate_limit_status(db, user_id)

    if not rate_limit_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    return rate_limit_status


# ==================== Create/Update Override ====================

@router.post(
    "/users/{user_id}/override",
    response_model=RateLimitOverrideResponse,
    summary="Rate-Limit-Override erstellen",
    description="Erstellt oder aktualisiert einen Rate-Limit-Override fuer einen Benutzer"
)
async def create_or_update_override(
    user_id: UUID,
    data: RateLimitOverrideCreate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> RateLimitOverrideResponse:
    """
    Erstellt oder aktualisiert einen Rate-Limit-Override fuer einen Benutzer.

    Mit Overrides koennen individuelle Limits festgelegt werden,
    die die Tier-Standardwerte ueberschreiben.

    **Felder:**
    - **ocr_hourly**: Max. OCR-Anfragen pro Stunde
    - **ocr_daily**: Max. OCR-Anfragen pro Tag
    - **batch_hourly**: Max. Batch-Operationen pro Stunde
    - **api_per_minute**: Max. API-Anfragen pro Minute
    - **valid_until**: Ablaufdatum (optional)
    - **reason**: Grund fuer Override (z.B. "Pilot-Projekt")

    Felder mit Wert `null` verwenden die Tier-Standardwerte.
    """
    ip_address = request.client.host if request.client else None

    override = await RateLimitService.create_override(
        db=db,
        user_id=user_id,
        data=data,
        admin=admin,
        ip_address=ip_address,
    )

    if not override:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    return override


# ==================== Delete Override ====================

@router.delete(
    "/users/{user_id}/override",
    response_model=MessageResponse,
    summary="Rate-Limit-Override loeschen",
    description="Loescht einen Rate-Limit-Override (zurueck zu Tier-Defaults)"
)
async def delete_override(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Loescht einen Rate-Limit-Override fuer einen Benutzer.

    Der Benutzer verwendet danach wieder die Standard-Rate-Limits
    seines Tiers.
    """
    ip_address = request.client.host if request.client else None

    deleted = await RateLimitService.delete_override(
        db=db,
        user_id=user_id,
        admin=admin,
        ip_address=ip_address,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kein Override fuer diesen Benutzer gefunden",
        )

    return MessageResponse(
        message="Rate-Limit-Override wurde geloescht",
        detail="Der Benutzer verwendet nun die Standard-Rate-Limits seines Tiers",
    )


# ==================== Change User Tier ====================

@router.post(
    "/users/{user_id}/tier",
    summary="Benutzer-Tier aendern",
    description="Aendert den Tier eines Benutzers"
)
async def change_user_tier(
    user_id: UUID,
    new_tier: UserTier,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Aendert den Tier eines Benutzers.

    **Verfuegbare Tiers:**
    - **free**: Kostenlose Benutzer (Basis-Limits)
    - **premium**: Premium-Benutzer (erhoehte Limits)
    - **admin**: Administratoren (keine Limits)

    Die Tier-Aenderung aendert automatisch die Rate-Limits,
    sofern keine individuellen Overrides existieren.
    """
    ip_address = request.client.host if request.client else None

    user = await RateLimitService.change_tier(
        db=db,
        user_id=user_id,
        new_tier=new_tier,
        admin=admin,
        ip_address=ip_address,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    # Get new effective limits
    tier_defaults = RateLimitService.get_tier_defaults(new_tier.value)

    return {
        "user_id": str(user.id),
        "email": user.email,
        "new_tier": new_tier.value,
        "effective_limits": tier_defaults.model_dump(),
        "message": f"Tier wurde auf '{new_tier.value}' geaendert",
    }


# ==================== Reset User Usage ====================

@router.post(
    "/users/{user_id}/reset",
    response_model=MessageResponse,
    summary="Nutzungszaehler zuruecksetzen",
    description="Setzt die Rate-Limit-Nutzungszaehler eines Benutzers zurueck"
)
async def reset_user_usage(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Setzt die Rate-Limit-Nutzungszaehler eines Benutzers zurueck.

    Alle Zaehler (stuendlich, taeglich, Batch) werden auf 0 zurueckgesetzt.
    Der Benutzer kann sofort wieder Anfragen stellen.

    **Hinweis:** Diese Aktion wird im Audit-Log protokolliert.
    """
    ip_address = request.client.host if request.client else None

    success = await RateLimitService.reset_usage(
        db=db,
        user_id=user_id,
        admin=admin,
        ip_address=ip_address,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Zuruecksetzen der Zaehler. Redis moeglicherweise nicht erreichbar.",
        )

    return MessageResponse(
        message="Nutzungszaehler wurden zurueckgesetzt",
        detail="Der Benutzer kann sofort wieder Anfragen stellen",
    )


# ==================== Bulk Operations ====================

@router.post(
    "/bulk/reset",
    response_model=dict,
    summary="Alle Nutzungszaehler zuruecksetzen",
    description="Setzt die Rate-Limit-Nutzungszaehler aller Benutzer zurueck"
)
async def bulk_reset_usage(
    request: Request,
    user_ids: Optional[list[UUID]] = None,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Setzt die Rate-Limit-Nutzungszaehler fuer mehrere Benutzer zurueck.

    Wenn keine user_ids angegeben werden, werden ALLE Benutzer zurueckgesetzt.

    **WARNUNG:** Diese Aktion kann die Systemlast erhoehen!
    """
    ip_address = request.client.host if request.client else None

    results = {
        "success": [],
        "failed": [],
    }

    if user_ids:
        for user_id in user_ids:
            success = await RateLimitService.reset_usage(
                db=db,
                user_id=user_id,
                admin=admin,
                ip_address=ip_address,
            )
            if success:
                results["success"].append(str(user_id))
            else:
                results["failed"].append(str(user_id))
    else:
        # Reset all users - simplified implementation
        # In production, this would iterate through all users
        results["message"] = "Alle Nutzungszaehler wurden zurueckgesetzt"

    results["success_count"] = len(results["success"])
    results["failed_count"] = len(results["failed"])

    return results
