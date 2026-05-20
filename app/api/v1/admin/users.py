"""
User Administration API Endpoints.

Provides user management for admins:
- List users with filtering and pagination
- Create, update, delete users
- Role and tier management
- Password reset
- User activity tracking
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_superuser
from app.db.models import User
from app.db.schemas import (
    UserAdminView,
    UserListFilters,
    UserListResponse,
    UserAdminCreate,
    UserAdminUpdate,
    UserPasswordReset,
    UserActivityResponse,
    UserRole,
    UserStatus,
    UserTier,
    UserSortField,
    SortOrder,
    MessageResponse,
)
from app.services.admin.user_admin_service import UserAdminService


router = APIRouter(prefix="/users", tags=["Admin - Benutzerverwaltung"])


# ==================== List Users ====================

@router.get(
    "",
    response_model=UserListResponse,
    summary="Benutzer auflisten",
    description="Listet alle Benutzer mit Filter- und Paginierungsoptionen auf"
)
async def list_users(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
    search: Optional[str] = Query(
        None,
        min_length=1,
        max_length=100,
        description="Suche in E-Mail, Benutzername, Name (max. 100 Zeichen)"
    ),
    role: Optional[UserRole] = Query(None, description="Nach Rolle filtern"),
    status_filter: Optional[UserStatus] = Query(None, alias="status", description="Nach Status filtern"),
    tier: Optional[UserTier] = Query(None, description="Nach Tier filtern"),
    include_workload: bool = Query(False, description="Workload-Statistiken einschließen"),
    sort_by: UserSortField = Query(UserSortField.CREATED_AT, description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """
    Listet alle Benutzer im System auf.

    Nur für Administratoren zugänglich.

    **Filter:**
    - **search**: Sucht in E-Mail, Benutzername und vollständigem Namen
    - **role**: Filtert nach Benutzerrolle (superuser, admin, user)
    - **status**: Filtert nach Status (active, inactive, deactivated)
    - **tier**: Filtert nach Tier (free, premium, admin)

    **Sortierung:**
    - Standardmäßig nach Erstellungsdatum absteigend
    - Sortierbare Felder: created_at, email, username, last_login
    """
    filters = UserListFilters(
        search=search,
        role=role,
        status=status_filter,
        tier=tier,
    )

    return await UserAdminService.list_users(
        db=db,
        page=page,
        per_page=per_page,
        filters=filters,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# ==================== Get Single User ====================

@router.get(
    "/{user_id}",
    response_model=UserAdminView,
    summary="Benutzer abrufen",
    description="Ruft detaillierte Informationen zu einem Benutzer ab"
)
async def get_user(
    user_id: UUID,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Ruft detaillierte Informationen zu einem bestimmten Benutzer ab.

    Nur für Administratoren zugänglich.
    """
    user = await UserAdminService.get_user(db, user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    return user


# ==================== Create User ====================

@router.post(
    "",
    response_model=UserAdminView,
    status_code=status.HTTP_201_CREATED,
    summary="Benutzer erstellen",
    description="Erstellt einen neuen Benutzer im System"
)
async def create_user(
    data: UserAdminCreate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Erstellt einen neuen Benutzer.

    Nur für Administratoren zugänglich.

    **Pflichtfelder:**
    - **email**: Eindeutige E-Mail-Adresse
    - **username**: Eindeutiger Benutzername
    - **password**: Passwort (min. 8 Zeichen)

    **Optionale Felder:**
    - **full_name**: Vollständiger Name
    - **tier**: Benutzer-Tier (free, premium, admin)
    - **is_superuser**: Superuser-Status
    - **daily_quota**: Tägliches Dokumentenlimit
    - **notes**: Interne Notizen
    """
    # Get client IP
    ip_address = request.client.host if request.client else None

    try:
        user = await UserAdminService.create_user(
            db=db,
            data=data,
            admin=admin,
            ip_address=ip_address,
        )
        return UserAdminView.from_orm_with_computed(user)
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("user_admin_validation_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen.",
        )


# ==================== Update User ====================

@router.patch(
    "/{user_id}",
    response_model=UserAdminView,
    summary="Benutzer aktualisieren",
    description="Aktualisiert Benutzerinformationen"
)
async def update_user(
    user_id: UUID,
    data: UserAdminUpdate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Aktualisiert Benutzerinformationen.

    Nur für Administratoren zugänglich.
    Alle Felder sind optional - nur angegebene Felder werden aktualisiert.
    """
    ip_address = request.client.host if request.client else None

    user = await UserAdminService.update_user(
        db=db,
        user_id=user_id,
        data=data,
        admin=admin,
        ip_address=ip_address,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    return UserAdminView.from_orm_with_computed(user)


# ==================== Deactivate User ====================

@router.post(
    "/{user_id}/deactivate",
    response_model=UserAdminView,
    summary="Benutzer deaktivieren",
    description="Deaktiviert ein Benutzerkonto"
)
async def deactivate_user(
    user_id: UUID,
    request: Request,
    reason: Optional[str] = Query(None, description="Grund für Deaktivierung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Deaktiviert ein Benutzerkonto.

    Der Benutzer kann sich nach der Deaktivierung nicht mehr anmelden.
    Diese Aktion kann rückgängig gemacht werden.
    """
    ip_address = request.client.host if request.client else None

    try:
        user = await UserAdminService.deactivate_user(
            db=db,
            user_id=user_id,
            admin=admin,
            reason=reason,
            ip_address=ip_address,
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Benutzer nicht gefunden",
            )

        return UserAdminView.from_orm_with_computed(user)

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("user_admin_validation_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen.",
        )


# ==================== Activate User ====================

@router.post(
    "/{user_id}/activate",
    response_model=UserAdminView,
    summary="Benutzer aktivieren",
    description="Reaktiviert ein deaktiviertes Benutzerkonto"
)
async def activate_user(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Reaktiviert ein deaktiviertes Benutzerkonto.

    Der Benutzer kann sich nach der Aktivierung wieder anmelden.
    """
    ip_address = request.client.host if request.client else None

    user = await UserAdminService.activate_user(
        db=db,
        user_id=user_id,
        admin=admin,
        ip_address=ip_address,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    return UserAdminView.from_orm_with_computed(user)


# ==================== Reset Password ====================

@router.post(
    "/{user_id}/reset-password",
    response_model=UserPasswordReset,
    summary="Passwort zurücksetzen",
    description="Setzt das Passwort eines Benutzers zurück"
)
async def reset_password(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserPasswordReset:
    """
    Setzt das Passwort eines Benutzers zurück.

    Generiert ein temporäres Passwort, das der Benutzer
    bei der nächsten Anmeldung ändern muss.

    **Wichtig:** Das temporäre Passwort wird nur einmal angezeigt!
    """
    ip_address = request.client.host if request.client else None

    result = await UserAdminService.reset_password(
        db=db,
        user_id=user_id,
        admin=admin,
        ip_address=ip_address,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    return result


# ==================== Change Role ====================

@router.post(
    "/{user_id}/change-role",
    response_model=UserAdminView,
    summary="Rolle ändern",
    description="Ändert den Superuser-Status eines Benutzers"
)
async def change_role(
    user_id: UUID,
    is_superuser: bool,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Ändert den Superuser-Status eines Benutzers.

    - **is_superuser=true**: Macht den Benutzer zum Administrator
    - **is_superuser=false**: Entfernt Administratorrechte

    **Hinweis:** Sie können sich nicht selbst herabstufen.
    """
    ip_address = request.client.host if request.client else None

    try:
        user = await UserAdminService.change_role(
            db=db,
            user_id=user_id,
            is_superuser=is_superuser,
            admin=admin,
            ip_address=ip_address,
        )

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Benutzer nicht gefunden",
            )

        return UserAdminView.from_orm_with_computed(user)

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("user_admin_validation_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen.",
        )


# ==================== Get User Activity ====================

@router.get(
    "/{user_id}/activity",
    response_model=UserActivityResponse,
    summary="Benutzeraktivität abrufen",
    description="Ruft die letzten Aktivitäten eines Benutzers ab"
)
async def get_user_activity(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl Einträge"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserActivityResponse:
    """
    Ruft die letzten Aktivitäten eines Benutzers ab.

    Zeigt Audit-Log-Einträge für den angegebenen Benutzer.
    """
    return await UserAdminService.get_user_activity(
        db=db,
        user_id=user_id,
        limit=limit,
    )


# ==================== Delete User ====================

@router.delete(
    "/{user_id}",
    response_model=MessageResponse,
    summary="Benutzer löschen",
    description="Löscht einen Benutzer dauerhaft"
)
async def delete_user(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Löscht einen Benutzer dauerhaft aus dem System.

    **WARNUNG:** Diese Aktion kann nicht rückgängig gemacht werden!

    Es wird empfohlen, Benutzer stattdessen zu deaktivieren,
    um die Nachverfolgbarkeit zu gewährleisten.
    """
    ip_address = request.client.host if request.client else None

    try:
        deleted = await UserAdminService.delete_user(
            db=db,
            user_id=user_id,
            admin=admin,
            ip_address=ip_address,
        )

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Benutzer nicht gefunden",
            )

        return MessageResponse(
            message="Benutzer wurde dauerhaft gelöscht",
            detail="Diese Aktion kann nicht rückgängig gemacht werden",
        )

    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("user_admin_validation_error", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Anfrage. Bitte Eingaben prüfen.",
        )


# ==================== Unlock Account ====================

@router.post(
    "/unlock-account",
    response_model=MessageResponse,
    summary="Account entsperren",
    description="Entsperrt ein durch fehlgeschlagene Logins gesperrtes Konto"
)
async def unlock_account(
    request: Request,
    email: Optional[str] = Query(None, description="E-Mail des Benutzers zum Entsperren"),
    ip: Optional[str] = Query(None, description="IP-Adresse zum Entsperren"),
    admin: User = Depends(get_current_superuser),
) -> MessageResponse:
    """
    Entsperrt ein durch zu viele fehlgeschlagene Login-Versuche gesperrtes Konto.

    **Parameter (mindestens einer erforderlich):**
    - **email**: E-Mail-Adresse des zu entsperrenden Benutzers
    - **ip**: IP-Adresse zum Entsperren

    Nach der Entsperrung kann sich der Benutzer sofort wieder anmelden.
    Diese Aktion wird im Audit-Log protokolliert.
    """
    from app.core.account_lockout import admin_unlock_account, get_lockout_status

    if not email and not ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens E-Mail oder IP-Adresse erforderlich",
        )

    # Get current lockout status
    status_info = await get_lockout_status(ip=ip, username=email)

    if not status_info["is_locked"] and status_info["failed_attempts"] == 0:
        return MessageResponse(
            message="Konto ist nicht gesperrt",
            detail=f"Keine Sperre für {email or ip} gefunden",
        )

    # Unlock the account
    success = await admin_unlock_account(
        ip=ip,
        username=email,
        admin_user=admin.email,
    )

    if success:
        return MessageResponse(
            message="Konto erfolgreich entsperrt",
            detail=f"Sperre für {email or ip} wurde aufgehoben. "
                   f"(Vorherige Fehlversuche: {status_info['failed_attempts']})",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Entsperrung fehlgeschlagen",
        )


@router.get(
    "/lockout-status",
    summary="Lockout-Status abrufen",
    description="Zeigt den Lockout-Status für eine E-Mail oder IP"
)
async def get_account_lockout_status(
    email: Optional[str] = Query(None, description="E-Mail des Benutzers"),
    ip: Optional[str] = Query(None, description="IP-Adresse"),
    admin: User = Depends(get_current_superuser),
) -> dict:
    """
    Zeigt den aktuellen Lockout-Status für eine E-Mail-Adresse oder IP.

    **Hinweis:** Mindestens ein Parameter erforderlich.

    Gibt Details zurück:
    - Anzahl fehlgeschlagener Versuche
    - Ob derzeit gesperrt
    - Verbleibende Sperrzeit
    """
    from app.core.account_lockout import get_lockout_status

    if not email and not ip:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens E-Mail oder IP-Adresse erforderlich",
        )

    return await get_lockout_status(ip=ip, username=email)


# ==================== User Quotas Management ====================

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from app.db.models import RateLimitOverride
from app.core.safe_errors import safe_error_log


class UserQuotasResponse(BaseModel):
    """Response model for user quotas."""
    user_id: str
    email: str
    tier: str

    # Base quotas (from User model)
    daily_quota: int
    documents_processed_today: int
    daily_quota_remaining: int

    # Rate limit overrides (from User model, null = tier default)
    rate_limit_hourly_override: Optional[int] = None
    rate_limit_daily_override: Optional[int] = None

    # Detailed overrides (from RateLimitOverride model)
    has_custom_override: bool = False
    override_details: Optional[dict] = None

    # Computed effective limits
    effective_limits: dict

    model_config = ConfigDict(from_attributes=True)


class UserQuotasUpdate(BaseModel):
    """Request model for updating user quotas."""
    daily_quota: Optional[int] = Field(None, ge=1, le=10000, description="Tägliches Dokumentenlimit")
    rate_limit_hourly: Optional[int] = Field(None, ge=1, le=1000, description="Stündliches Rate-Limit")
    rate_limit_daily: Optional[int] = Field(None, ge=1, le=10000, description="Tägliches Rate-Limit")
    reset_daily_usage: bool = Field(False, description="Tagesnutzung zurücksetzen")

    # Override settings (set to create/update RateLimitOverride)
    ocr_hourly: Optional[int] = Field(None, ge=1, le=1000, description="Max OCR-Anfragen pro Stunde")
    ocr_daily: Optional[int] = Field(None, ge=1, le=10000, description="Max OCR-Anfragen pro Tag")
    batch_hourly: Optional[int] = Field(None, ge=1, le=100, description="Max Batch-Operationen pro Stunde")
    api_per_minute: Optional[int] = Field(None, ge=1, le=1000, description="Max API-Anfragen pro Minute")


@router.get(
    "/{user_id}/quotas",
    response_model=UserQuotasResponse,
    summary="Benutzer-Quotas abrufen",
    description="Ruft alle Quota-Einstellungen und Nutzung für einen Benutzer ab"
)
async def get_user_quotas(
    user_id: UUID,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserQuotasResponse:
    """
    Ruft alle Quota-Einstellungen für einen Benutzer ab.

    Zeigt:
    - **Basis-Quotas**: Tägliches Dokumentenlimit und aktuelle Nutzung
    - **Rate-Limits**: Individuelle Overrides (falls vorhanden)
    - **Effektive Limits**: Kombination aus Tier-Defaults und Overrides

    Die effektiven Limits werden automatisch berechnet basierend auf:
    1. Tier-Standardwerten (free/premium/admin)
    2. Individuellen Overrides (falls gesetzt)
    """
    # Get user
    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    # Get rate limit override if exists
    override_result = await db.execute(
        select(RateLimitOverride).where(RateLimitOverride.user_id == user_id)
    )
    override = override_result.scalar_one_or_none()

    # Calculate effective limits based on tier
    from app.services.admin.rate_limit_service import RateLimitService
    tier_defaults = RateLimitService.get_tier_defaults(user.tier or "free")

    effective_limits = {
        "ocr_hourly": override.ocr_hourly if override and override.ocr_hourly else tier_defaults.ocr_hourly,
        "ocr_daily": override.ocr_daily if override and override.ocr_daily else tier_defaults.ocr_daily,
        "batch_hourly": override.batch_hourly if override and override.batch_hourly else tier_defaults.batch_hourly,
        "api_per_minute": override.api_per_minute if override and override.api_per_minute else tier_defaults.api_per_minute,
        "daily_documents": user.daily_quota,
    }

    # Build override details if exists
    override_details = None
    if override:
        override_details = {
            "ocr_hourly": override.ocr_hourly,
            "ocr_daily": override.ocr_daily,
            "batch_hourly": override.batch_hourly,
            "api_per_minute": override.api_per_minute,
            "valid_until": override.valid_until.isoformat() if override.valid_until else None,
            "reason": override.reason,
            "created_at": override.created_at.isoformat() if override.created_at else None,
        }

    return UserQuotasResponse(
        user_id=str(user.id),
        email=user.email,
        tier=user.tier or "free",
        daily_quota=user.daily_quota,
        documents_processed_today=user.documents_processed_today or 0,
        daily_quota_remaining=max(0, user.daily_quota - (user.documents_processed_today or 0)),
        rate_limit_hourly_override=user.rate_limit_hourly,
        rate_limit_daily_override=user.rate_limit_daily,
        has_custom_override=override is not None,
        override_details=override_details,
        effective_limits=effective_limits,
    )


@router.put(
    "/{user_id}/quotas",
    response_model=UserQuotasResponse,
    summary="Benutzer-Quotas aktualisieren",
    description="Aktualisiert Quota-Einstellungen für einen Benutzer"
)
async def update_user_quotas(
    user_id: UUID,
    data: UserQuotasUpdate,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserQuotasResponse:
    """
    Aktualisiert Quota-Einstellungen für einen Benutzer.

    **Aktualisierbare Felder:**
    - **daily_quota**: Maximale Dokumente pro Tag
    - **rate_limit_hourly**: Stündliches Rate-Limit (Override)
    - **rate_limit_daily**: Tägliches Rate-Limit (Override)
    - **reset_daily_usage**: Setzt Tagesnutzung auf 0 zurück

    **OCR-spezifische Overrides:**
    - **ocr_hourly**: Max OCR-Anfragen pro Stunde
    - **ocr_daily**: Max OCR-Anfragen pro Tag
    - **batch_hourly**: Max Batch-Operationen pro Stunde
    - **api_per_minute**: Max API-Anfragen pro Minute

    Nur angegebene Felder werden aktualisiert.
    """
    # Get user
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden",
        )

    # Build update dict for User model
    user_updates = {}
    if data.daily_quota is not None:
        user_updates["daily_quota"] = data.daily_quota
    if data.rate_limit_hourly is not None:
        user_updates["rate_limit_hourly"] = data.rate_limit_hourly
    if data.rate_limit_daily is not None:
        user_updates["rate_limit_daily"] = data.rate_limit_daily
    if data.reset_daily_usage:
        user_updates["documents_processed_today"] = 0

    # Update User if any changes
    if user_updates:
        await db.execute(
            update(User).where(User.id == user_id).values(**user_updates)
        )

    # Handle RateLimitOverride updates
    override_updates = {}
    if data.ocr_hourly is not None:
        override_updates["ocr_hourly"] = data.ocr_hourly
    if data.ocr_daily is not None:
        override_updates["ocr_daily"] = data.ocr_daily
    if data.batch_hourly is not None:
        override_updates["batch_hourly"] = data.batch_hourly
    if data.api_per_minute is not None:
        override_updates["api_per_minute"] = data.api_per_minute

    if override_updates:
        # Check if override exists
        override_result = await db.execute(
            select(RateLimitOverride).where(RateLimitOverride.user_id == user_id)
        )
        existing_override = override_result.scalar_one_or_none()

        if existing_override:
            # Update existing override
            await db.execute(
                update(RateLimitOverride)
                .where(RateLimitOverride.user_id == user_id)
                .values(**override_updates)
            )
        else:
            # Create new override
            from datetime import datetime, timezone
            new_override = RateLimitOverride(
                user_id=user_id,
                created_by_id=admin.id,
                reason=f"Erstellt via Admin-Quotas-Endpoint durch {admin.email}",
                **override_updates
            )
            db.add(new_override)

    await db.commit()

    # Log the action
    from app.core.audit_logger import AuditLogger

    ip_address = request.client.host if request.client else None
    await AuditLogger.log_admin_action(
        db=db,
        admin_id=admin.id,
        action="user.quotas.updated",
        target_user_id=user_id,
        details={
            "user_updates": user_updates,
            "override_updates": override_updates,
        },
        ip_address=ip_address,
    )

    # Return updated quotas
    return await get_user_quotas(user_id, admin, db)
