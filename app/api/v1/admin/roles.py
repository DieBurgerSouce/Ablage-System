"""
Admin API - Rollenverwaltung (RBAC).

Endpoints für:
- Rollen anzeigen, erstellen, bearbeiten, löschen
- Benutzerrollen zuweisen/entfernen
- Berechtigungen anzeigen
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

# Fix 13: Korrigierte Imports
from app.api.dependencies import get_db, get_current_user
from app.db.models import User, Role, Permission
from app.services.permission_service import PermissionService
from app.core.rbac import require_permission, require_any_permission
from app.core.audit_logger import AuditLogger, AuditEventType

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/roles", tags=["Rollen"])


# ==================== Pydantic Schemas ====================

class PermissionResponse(BaseModel):
    """Permission Antwort-Schema."""
    id: UUID
    name: str
    description: Optional[str]
    resource_type: str
    action: str
    is_system: bool

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(BaseModel):
    """Rolle Antwort-Schema."""
    id: UUID
    name: str
    display_name: str
    description: Optional[str]
    priority: int
    is_system: bool
    is_active: bool
    color: str
    created_at: datetime
    updated_at: datetime
    permissions: List[PermissionResponse] = []
    user_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class RoleCreateRequest(BaseModel):
    """Schema für Rollenerstellung."""
    name: str = Field(..., min_length=2, max_length=50, description="Eindeutiger Rollenname (lowercase)")
    display_name: str = Field(..., min_length=2, max_length=100, description="Anzeigename")
    description: Optional[str] = Field(None, max_length=500, description="Beschreibung")
    priority: int = Field(0, ge=0, le=99, description="Priorität (0-99, höher = mehr Rechte)")
    color: str = Field("#6B7280", pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex-Farbcode")
    permission_names: List[str] = Field(default=[], description="Liste der Berechtigungsnamen")


class RoleUpdateRequest(BaseModel):
    """Schema für Rollenaktualisierung."""
    display_name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    priority: Optional[int] = Field(None, ge=0, le=99)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    is_active: Optional[bool] = None
    permission_names: Optional[List[str]] = None


class UserRoleAssignRequest(BaseModel):
    """Schema für Rollenzuweisung."""
    user_id: UUID = Field(..., description="Benutzer-ID")


class UserRoleResponse(BaseModel):
    """Schema für Benutzer mit Rollen."""
    user_id: UUID
    email: str
    username: str
    roles: List[RoleResponse]

    model_config = ConfigDict(from_attributes=True)


# ==================== Endpoints ====================

@router.get(
    "",
    response_model=List[RoleResponse],
    summary="Alle Rollen auflisten",
    description="Gibt alle verfügbaren Rollen mit ihren Berechtigungen zurück."
)
async def list_roles(
    include_inactive: bool = Query(False, description="Auch inaktive Rollen anzeigen"),
    current_user: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db)
) -> List[RoleResponse]:
    """
    Listet alle Rollen auf.

    Erfordert: roles:read Berechtigung
    """
    service = PermissionService(db)
    roles = await service.get_all_roles(include_inactive=include_inactive)

    result = []
    for role in roles:
        # Count users with this role
        user_count = len(role.users) if hasattr(role, 'users') else 0

        result.append(RoleResponse(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            priority=role.priority,
            is_system=role.is_system,
            is_active=role.is_active,
            color=role.color,
            created_at=role.created_at,
            updated_at=role.updated_at,
            permissions=[
                PermissionResponse(
                    id=p.id,
                    name=p.name,
                    description=p.description,
                    resource_type=p.resource_type,
                    action=p.action,
                    is_system=p.is_system
                ) for p in role.permissions
            ],
            user_count=user_count
        ))

    return result


@router.get(
    "/permissions",
    response_model=List[PermissionResponse],
    summary="Alle Berechtigungen auflisten",
    description="Gibt alle verfügbaren Berechtigungen zurück."
)
async def list_permissions(
    current_user: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db)
) -> List[PermissionResponse]:
    """
    Listet alle Berechtigungen auf.

    Erfordert: roles:read Berechtigung
    """
    service = PermissionService(db)
    permissions = await service.get_all_permissions()

    return [
        PermissionResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            resource_type=p.resource_type,
            action=p.action,
            is_system=p.is_system
        ) for p in permissions
    ]


@router.get(
    "/{role_id}",
    response_model=RoleResponse,
    summary="Rolle nach ID abrufen",
    description="Gibt eine spezifische Rolle mit ihren Berechtigungen zurück."
)
async def get_role(
    role_id: UUID,
    current_user: User = Depends(require_permission("roles:read")),
    db: AsyncSession = Depends(get_db)
) -> RoleResponse:
    """
    Holt eine Rolle nach ID.

    Erfordert: roles:read Berechtigung
    """
    service = PermissionService(db)
    role = await service.get_role_by_id(role_id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rolle nicht gefunden"
        )

    return RoleResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        priority=role.priority,
        is_system=role.is_system,
        is_active=role.is_active,
        color=role.color,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permissions=[
            PermissionResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                resource_type=p.resource_type,
                action=p.action,
                is_system=p.is_system
            ) for p in role.permissions
        ],
        user_count=len(role.users) if hasattr(role, 'users') else 0
    )


@router.post(
    "",
    response_model=RoleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Neue Rolle erstellen",
    description="Erstellt eine neue benutzerdefinierte Rolle."
)
async def create_role(
    request: RoleCreateRequest,
    current_user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db)
) -> RoleResponse:
    """
    Erstellt eine neue Rolle.

    Erfordert: roles:write Berechtigung
    """
    service = PermissionService(db)

    try:
        role = await service.create_role(
            name=request.name,
            display_name=request.display_name,
            description=request.description,
            priority=request.priority,
            color=request.color,
            permission_names=request.permission_names
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("role_admin_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    # Audit-Log
    await AuditLogger.log_async(
        db=db,
        user_id=current_user.id,
        action=AuditEventType.ROLE_ASSIGNED,  # Using existing type
        resource_type="role",
        resource_id=role.id,
        metadata={
            "action": "role_created",
            "role_name": role.name,
            "permissions": request.permission_names
        }
    )

    # Reload with permissions
    role = await service.get_role_by_id(role.id)

    return RoleResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        priority=role.priority,
        is_system=role.is_system,
        is_active=role.is_active,
        color=role.color,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permissions=[
            PermissionResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                resource_type=p.resource_type,
                action=p.action,
                is_system=p.is_system
            ) for p in role.permissions
        ],
        user_count=0
    )


@router.put(
    "/{role_id}",
    response_model=RoleResponse,
    summary="Rolle aktualisieren",
    description="Aktualisiert eine bestehende Rolle."
)
async def update_role(
    role_id: UUID,
    request: RoleUpdateRequest,
    current_user: User = Depends(require_permission("roles:write")),
    db: AsyncSession = Depends(get_db)
) -> RoleResponse:
    """
    Aktualisiert eine Rolle.

    System-Rollen können nur eingeschränkt bearbeitet werden.

    Erfordert: roles:write Berechtigung
    """
    service = PermissionService(db)
    role = await service.get_role_by_id(role_id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rolle nicht gefunden"
        )

    try:
        role = await service.update_role(
            role=role,
            display_name=request.display_name,
            description=request.description,
            priority=request.priority,
            color=request.color,
            is_active=request.is_active,
            permission_names=request.permission_names
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("role_admin_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    # Audit-Log
    await AuditLogger.log_async(
        db=db,
        user_id=current_user.id,
        action=AuditEventType.SETTINGS_UPDATED,
        resource_type="role",
        resource_id=role.id,
        metadata={
            "action": "role_updated",
            "role_name": role.name,
            "changes": request.model_dump(exclude_none=True)
        }
    )

    # Reload with permissions
    role = await service.get_role_by_id(role.id)

    return RoleResponse(
        id=role.id,
        name=role.name,
        display_name=role.display_name,
        description=role.description,
        priority=role.priority,
        is_system=role.is_system,
        is_active=role.is_active,
        color=role.color,
        created_at=role.created_at,
        updated_at=role.updated_at,
        permissions=[
            PermissionResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                resource_type=p.resource_type,
                action=p.action,
                is_system=p.is_system
            ) for p in role.permissions
        ],
        user_count=len(role.users) if hasattr(role, 'users') else 0
    )


@router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Rolle löschen",
    description="Löscht eine benutzerdefinierte Rolle."
)
async def delete_role(
    role_id: UUID,
    current_user: User = Depends(require_any_permission("roles:delete", "roles:manage")),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """
    Löscht eine Rolle.

    System-Rollen können nicht gelöscht werden.

    Erfordert: roles:delete oder roles:manage Berechtigung
    """
    service = PermissionService(db)
    role = await service.get_role_by_id(role_id)

    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rolle nicht gefunden"
        )

    try:
        await service.delete_role(role)
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("role_admin_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    # Audit-Log
    await AuditLogger.log_async(
        db=db,
        user_id=current_user.id,
        action=AuditEventType.SETTINGS_UPDATED,
        resource_type="role",
        resource_id=role_id,
        metadata={
            "action": "role_deleted",
            "role_name": role.name
        }
    )

    logger.info(
        "role_deleted",
        role_id=str(role_id),
        role_name=role.name,
        deleted_by=str(current_user.id)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== User Role Assignment ====================

@router.post(
    "/{role_id}/users",
    status_code=status.HTTP_201_CREATED,
    summary="Rolle einem Benutzer zuweisen",
    description="Weist einem Benutzer eine Rolle zu."
)
async def assign_role_to_user(
    role_id: UUID,
    request: UserRoleAssignRequest,
    current_user: User = Depends(require_permission("users:manage")),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Weist einem Benutzer eine Rolle zu.

    Erfordert: users:manage Berechtigung
    """
    from sqlalchemy import select
    from app.db.models import User as UserModel

    service = PermissionService(db)

    # Get role
    role = await service.get_role_by_id(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rolle nicht gefunden"
        )

    # Get user
    result = await db.execute(
        select(UserModel).where(UserModel.id == request.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"
        )

    # Assign role
    success = await service.assign_role(user, role, assigned_by=current_user)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rolle ist diesem Benutzer bereits zugewiesen"
        )

    # Audit-Log
    await AuditLogger.log_async(
        db=db,
        user_id=current_user.id,
        action=AuditEventType.ROLE_ASSIGNED,
        resource_type="user",
        resource_id=user.id,
        metadata={
            "action": "role_assigned",
            "role_name": role.name,
            "target_user_id": str(user.id),
            "target_user_email": user.email
        }
    )

    return {
        "message": f"Rolle '{role.display_name}' erfolgreich zugewiesen",
        "user_id": str(user.id),
        "role_id": str(role.id)
    }


@router.delete(
    "/{role_id}/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Rolle von Benutzer entfernen",
    description="Entfernt eine Rolle von einem Benutzer."
)
async def remove_role_from_user(
    role_id: UUID,
    user_id: UUID,
    current_user: User = Depends(require_permission("users:manage")),
    db: AsyncSession = Depends(get_db)
) -> Response:
    """
    Entfernt eine Rolle von einem Benutzer.

    Erfordert: users:manage Berechtigung
    """
    from sqlalchemy import select
    from app.db.models import User as UserModel

    service = PermissionService(db)

    # Get role
    role = await service.get_role_by_id(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rolle nicht gefunden"
        )

    # Get user
    result = await db.execute(
        select(UserModel).where(UserModel.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer nicht gefunden"
        )

    # Remove role
    success = await service.remove_role(user, role)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benutzer hat diese Rolle nicht"
        )

    # Audit-Log
    await AuditLogger.log_async(
        db=db,
        user_id=current_user.id,
        action=AuditEventType.ROLE_REVOKED,
        resource_type="user",
        resource_id=user.id,
        metadata={
            "action": "role_removed",
            "role_name": role.name,
            "target_user_id": str(user.id),
            "target_user_email": user.email
        }
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{role_id}/users",
    response_model=List[dict],
    summary="Benutzer mit Rolle auflisten",
    description="Listet alle Benutzer auf, die eine bestimmte Rolle haben."
)
async def list_users_with_role(
    role_id: UUID,
    current_user: User = Depends(require_any_permission("roles:read", "users:read")),
    db: AsyncSession = Depends(get_db)
) -> List[dict]:
    """
    Listet alle Benutzer mit einer bestimmten Rolle auf.

    Erfordert: roles:read oder users:read Berechtigung
    """
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.db.models import User as UserModel, user_roles

    service = PermissionService(db)

    # Get role
    role = await service.get_role_by_id(role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rolle nicht gefunden"
        )

    # Get users with this role
    stmt = (
        select(UserModel)
        .join(user_roles, UserModel.id == user_roles.c.user_id)
        .where(user_roles.c.role_id == role_id)
        .options(selectinload(UserModel.roles))
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    return [
        {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        for user in users
    ]


# ==================== Current User Roles ====================

@router.get(
    "/me/roles",
    response_model=List[RoleResponse],
    summary="Eigene Rollen anzeigen",
    description="Zeigt die Rollen des aktuellen Benutzers."
)
async def get_my_roles(
    current_user: User = Depends(require_permission("documents:read")),  # Minimal permission
    db: AsyncSession = Depends(get_db)
) -> List[RoleResponse]:
    """
    Zeigt die Rollen des aktuellen Benutzers.

    Erfordert: Authentifizierung (minimale Berechtigung)
    """
    service = PermissionService(db)
    roles = await service.get_user_roles(current_user)

    return [
        RoleResponse(
            id=role.id,
            name=role.name,
            display_name=role.display_name,
            description=role.description,
            priority=role.priority,
            is_system=role.is_system,
            is_active=role.is_active,
            color=role.color,
            created_at=role.created_at,
            updated_at=role.updated_at,
            permissions=[
                PermissionResponse(
                    id=p.id,
                    name=p.name,
                    description=p.description,
                    resource_type=p.resource_type,
                    action=p.action,
                    is_system=p.is_system
                ) for p in role.permissions
            ],
            user_count=0  # Don't expose user count for own roles
        )
        for role in roles
    ]


@router.get(
    "/me/permissions",
    response_model=List[str],
    summary="Eigene Berechtigungen anzeigen",
    description="Zeigt alle Berechtigungen des aktuellen Benutzers."
)
async def get_my_permissions(
    current_user: User = Depends(require_permission("documents:read")),  # Minimal permission
    db: AsyncSession = Depends(get_db)
) -> List[str]:
    """
    Zeigt alle Berechtigungen des aktuellen Benutzers.

    Erfordert: Authentifizierung (minimale Berechtigung)
    """
    service = PermissionService(db)
    permissions = await service.get_user_permissions(current_user)

    # Sort for consistent output
    return sorted(list(permissions))
