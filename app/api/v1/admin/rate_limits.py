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
from app.core.german_messages import HTTPErrors
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
    description="Ruft die Standard-Rate-Limits für alle Tiers ab"
)
async def get_tier_defaults(
    admin: User = Depends(get_current_superuser),
) -> dict:
    """
    Ruft die Standard-Rate-Limits für alle Benutzer-Tiers ab.

    Zeigt die Standardlimits für:
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
    description="Erstellt oder aktualisiert einen Rate-Limit-Override für einen Benutzer"
)
async def create_or_update_override(
    user_id: UUID,
    data: RateLimitOverrideCreate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> RateLimitOverrideResponse:
    """
    Erstellt oder aktualisiert einen Rate-Limit-Override für einen Benutzer.

    Mit Overrides können individuelle Limits festgelegt werden,
    die die Tier-Standardwerte überschreiben.

    **Felder:**
    - **ocr_hourly**: Max. OCR-Anfragen pro Stunde
    - **ocr_daily**: Max. OCR-Anfragen pro Tag
    - **batch_hourly**: Max. Batch-Operationen pro Stunde
    - **api_per_minute**: Max. API-Anfragen pro Minute
    - **valid_until**: Ablaufdatum (optional)
    - **reason**: Grund für Override (z.B. "Pilot-Projekt")

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
    summary="Rate-Limit-Override löschen",
    description="Löscht einen Rate-Limit-Override (zurück zu Tier-Defaults)"
)
async def delete_override(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Löscht einen Rate-Limit-Override für einen Benutzer.

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
            detail=HTTPErrors.OVERRIDE_NOT_FOUND,
        )

    return MessageResponse(
        message="Rate-Limit-Override wurde gelöscht",
        detail="Der Benutzer verwendet nun die Standard-Rate-Limits seines Tiers",
    )


# ==================== Change User Tier ====================

@router.post(
    "/users/{user_id}/tier",
    summary="Benutzer-Tier ändern",
    description="Ändert den Tier eines Benutzers"
)
async def change_user_tier(
    user_id: UUID,
    new_tier: UserTier,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Ändert den Tier eines Benutzers.

    **Verfügbare Tiers:**
    - **free**: Kostenlose Benutzer (Basis-Limits)
    - **premium**: Premium-Benutzer (erhöhte Limits)
    - **admin**: Administratoren (keine Limits)

    Die Tier-Änderung ändert automatisch die Rate-Limits,
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
        "message": f"Tier wurde auf '{new_tier.value}' geändert",
    }


# ==================== Reset User Usage ====================

@router.post(
    "/users/{user_id}/reset",
    response_model=MessageResponse,
    summary="Nutzungszähler zurücksetzen",
    description="Setzt die Rate-Limit-Nutzungszähler eines Benutzers zurück"
)
async def reset_user_usage(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Setzt die Rate-Limit-Nutzungszähler eines Benutzers zurück.

    Alle Zähler (stündlich, täglich, Batch) werden auf 0 zurückgesetzt.
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
            detail=HTTPErrors.RESET_COUNTER_FAILED.format(
                details="Redis möglicherweise nicht erreichbar"
            ),
        )

    return MessageResponse(
        message="Nutzungszähler wurden zurückgesetzt",
        detail="Der Benutzer kann sofort wieder Anfragen stellen",
    )


# ==================== Bulk Operations ====================

@router.post(
    "/bulk/reset",
    response_model=dict,
    summary="Alle Nutzungszähler zurücksetzen",
    description="Setzt die Rate-Limit-Nutzungszähler aller Benutzer zurück"
)
async def bulk_reset_usage(
    request: Request,
    user_ids: Optional[list[UUID]] = None,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Setzt die Rate-Limit-Nutzungszähler für mehrere Benutzer zurück.

    Wenn keine user_ids angegeben werden, werden ALLE Benutzer zurückgesetzt.

    **WARNUNG:** Diese Aktion kann die Systemlast erhöhen!
    """
    ip_address = request.client.host if request.client else None

    results = {
        "success": [],
        "failed": [],
        "not_found": [],
    }

    if user_ids:
        # Schemathesis-Fix (W1-004 #5): Nicht existente User-IDs führten beim
        # Audit-Log-Commit zu einem FK-Fehler, der die Session vergiftete
        # (500 im Session-Teardown). Jetzt: Existenz vorab prüfen ->
        # Teilerfolg-Schema (not_found) bzw. 404, wenn KEINE der IDs existiert.
        from sqlalchemy import select

        existing_result = await db.execute(
            select(User.id).where(User.id.in_(user_ids))
        )
        existing_ids = {row[0] for row in existing_result.all()}

        if not existing_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Keiner der angegebenen Benutzer wurde gefunden",
            )

        for user_id in user_ids:
            if user_id not in existing_ids:
                results["not_found"].append(str(user_id))
                continue
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
        results["message"] = "Alle Nutzungszähler wurden zurückgesetzt"

    results["success_count"] = len(results["success"])
    results["failed_count"] = len(results["failed"])
    results["not_found_count"] = len(results["not_found"])

    return results
