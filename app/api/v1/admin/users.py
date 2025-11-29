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
    per_page: int = Query(20, ge=1, le=100, description="Eintraege pro Seite"),
    search: Optional[str] = Query(None, description="Suche in E-Mail, Benutzername, Name"),
    role: Optional[UserRole] = Query(None, description="Nach Rolle filtern"),
    status_filter: Optional[UserStatus] = Query(None, alias="status", description="Nach Status filtern"),
    tier: Optional[UserTier] = Query(None, description="Nach Tier filtern"),
    sort_by: str = Query("created_at", description="Sortierfeld"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sortierrichtung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """
    Listet alle Benutzer im System auf.

    Nur fuer Administratoren zugaenglich.

    **Filter:**
    - **search**: Sucht in E-Mail, Benutzername und vollstaendigem Namen
    - **role**: Filtert nach Benutzerrolle (superuser, admin, user)
    - **status**: Filtert nach Status (active, inactive, deactivated)
    - **tier**: Filtert nach Tier (free, premium, admin)

    **Sortierung:**
    - Standardmaessig nach Erstellungsdatum absteigend
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

    Nur fuer Administratoren zugaenglich.
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

    Nur fuer Administratoren zugaenglich.

    **Pflichtfelder:**
    - **email**: Eindeutige E-Mail-Adresse
    - **username**: Eindeutiger Benutzername
    - **password**: Passwort (min. 8 Zeichen)

    **Optionale Felder:**
    - **full_name**: Vollstaendiger Name
    - **tier**: Benutzer-Tier (free, premium, admin)
    - **is_superuser**: Superuser-Status
    - **daily_quota**: Taegliches Dokumentenlimit
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
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

    Nur fuer Administratoren zugaenglich.
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
    reason: Optional[str] = Query(None, description="Grund fuer Deaktivierung"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Deaktiviert ein Benutzerkonto.

    Der Benutzer kann sich nach der Deaktivierung nicht mehr anmelden.
    Diese Aktion kann rueckgaengig gemacht werden.
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
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
    summary="Passwort zuruecksetzen",
    description="Setzt das Passwort eines Benutzers zurueck"
)
async def reset_password(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserPasswordReset:
    """
    Setzt das Passwort eines Benutzers zurueck.

    Generiert ein temporaeres Passwort, das der Benutzer
    bei der naechsten Anmeldung aendern muss.

    **Wichtig:** Das temporaere Passwort wird nur einmal angezeigt!
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
    summary="Rolle aendern",
    description="Aendert den Superuser-Status eines Benutzers"
)
async def change_role(
    user_id: UUID,
    is_superuser: bool,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserAdminView:
    """
    Aendert den Superuser-Status eines Benutzers.

    - **is_superuser=true**: Macht den Benutzer zum Administrator
    - **is_superuser=false**: Entfernt Administratorrechte

    **Hinweis:** Sie koennen sich nicht selbst herabstufen.
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ==================== Get User Activity ====================

@router.get(
    "/{user_id}/activity",
    response_model=UserActivityResponse,
    summary="Benutzeraktivitaet abrufen",
    description="Ruft die letzten Aktivitaeten eines Benutzers ab"
)
async def get_user_activity(
    user_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl Eintraege"),
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> UserActivityResponse:
    """
    Ruft die letzten Aktivitaeten eines Benutzers ab.

    Zeigt Audit-Log-Eintraege fuer den angegebenen Benutzer.
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
    summary="Benutzer loeschen",
    description="Loescht einen Benutzer dauerhaft"
)
async def delete_user(
    user_id: UUID,
    request: Request,
    admin: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """
    Loescht einen Benutzer dauerhaft aus dem System.

    **WARNUNG:** Diese Aktion kann nicht rueckgaengig gemacht werden!

    Es wird empfohlen, Benutzer stattdessen zu deaktivieren,
    um die Nachverfolgbarkeit zu gewaehrleisten.
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
            message="Benutzer wurde dauerhaft geloescht",
            detail="Diese Aktion kann nicht rueckgaengig gemacht werden",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
