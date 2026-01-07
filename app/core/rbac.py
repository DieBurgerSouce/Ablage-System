"""
RBAC (Role-Based Access Control) Decorators und Dependencies für FastAPI.

Bietet:
- Permission-basierte Dependency Injection
- Dekoratoren für Endpoint-Schutz
- Einfache Integration in FastAPI-Routen

Verwendung:
    @router.get("/admin/users")
    async def list_users(
        current_user: User = Depends(require_permissions("users:read"))
    ):
        ...

    # Oder mit mehreren Berechtigungen:
    @router.delete("/admin/users/{user_id}")
    async def delete_user(
        current_user: User = Depends(require_any_permission(["users:delete", "users:manage"]))
    ):
        ...
"""

from functools import wraps
from typing import Callable, List, Optional, Union
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import User
from app.db.database import get_db
from app.api.dependencies import get_current_user
from app.services.permission_service import PermissionService
from app.core.config import settings

logger = structlog.get_logger(__name__)


class PermissionDeniedError(HTTPException):
    """
    Exception für verweigerte Berechtigungen.

    Verwendet HTTP 403 Forbidden mit deutscher Fehlermeldung.
    """

    def __init__(
        self,
        permission: str,
        detail: Optional[str] = None
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail or f"Zugriff verweigert: Berechtigung '{permission}' erforderlich"
        )
        self.permission = permission


class InsufficientRoleError(HTTPException):
    """
    Exception für unzureichende Rolle.

    Verwendet HTTP 403 Forbidden mit deutscher Fehlermeldung.
    """

    def __init__(
        self,
        required_role: str,
        detail: Optional[str] = None
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail or f"Zugriff verweigert: Rolle '{required_role}' erforderlich"
        )
        self.required_role = required_role


# ==================== Dependency Functions ====================

def require_permission(permission: str) -> Callable:
    """
    FastAPI Dependency für einzelne Berechtigung.

    Args:
        permission: Erforderliche Berechtigung (z.B. "documents:read")

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        PermissionDeniedError: Wenn Berechtigung fehlt

    Beispiel:
        @router.get("/documents")
        async def list_docs(
            user: User = Depends(require_permission("documents:read"))
        ):
            ...
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        service = PermissionService(db)

        if not await service.has_permission(current_user, permission):
            logger.warning(
                "permission_denied",
                user_id=str(current_user.id),
                permission=permission,
                endpoint="unknown"
            )
            raise PermissionDeniedError(permission)

        return current_user

    return permission_checker


def require_permissions(*permissions: str) -> Callable:
    """
    FastAPI Dependency für mehrere Berechtigungen (alle erforderlich).

    Args:
        *permissions: Alle erforderlichen Berechtigungen

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        PermissionDeniedError: Wenn eine Berechtigung fehlt

    Beispiel:
        @router.post("/admin/backup")
        async def create_backup(
            user: User = Depends(require_permissions("backups:write", "system:manage"))
        ):
            ...
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        service = PermissionService(db)

        for permission in permissions:
            if not await service.has_permission(current_user, permission):
                logger.warning(
                    "permission_denied",
                    user_id=str(current_user.id),
                    permission=permission,
                    required_all=list(permissions)
                )
                raise PermissionDeniedError(
                    permission,
                    f"Zugriff verweigert: Alle Berechtigungen erforderlich: {', '.join(permissions)}"
                )

        return current_user

    return permission_checker


def require_any_permission(*permissions: str) -> Callable:
    """
    FastAPI Dependency für mehrere Berechtigungen (mindestens eine erforderlich).

    Args:
        *permissions: Mögliche Berechtigungen (eine reicht)

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        PermissionDeniedError: Wenn keine der Berechtigungen vorhanden

    Beispiel:
        @router.delete("/documents/{id}")
        async def delete_document(
            user: User = Depends(require_any_permission("documents:delete", "documents:manage"))
        ):
            ...
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        service = PermissionService(db)

        for permission in permissions:
            if await service.has_permission(current_user, permission):
                return current_user

        logger.warning(
            "permission_denied",
            user_id=str(current_user.id),
            required_any=list(permissions)
        )
        raise PermissionDeniedError(
            permissions[0],
            f"Zugriff verweigert: Eine der folgenden Berechtigungen erforderlich: {', '.join(permissions)}"
        )

    return permission_checker


def require_role(role_name: str) -> Callable:
    """
    FastAPI Dependency für bestimmte Rolle.

    Args:
        role_name: Erforderlicher Rollenname (z.B. "admin")

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        InsufficientRoleError: Wenn Rolle nicht zugewiesen

    Beispiel:
        @router.get("/admin/dashboard")
        async def admin_dashboard(
            user: User = Depends(require_role("admin"))
        ):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        service = PermissionService(db)
        user_roles = await service.get_user_roles(current_user)

        if any(role.name == role_name for role in user_roles):
            # J.1 SECURITY FIX: Auch normale User mit Rolle muessen 2FA haben fuer Admin-Rollen
            # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
            if role_name in ("admin", "super_admin") and not current_user.totp_enabled and not settings.DEBUG:
                logger.warning(
                    "2fa_required_for_role",
                    user_id=str(current_user.id),
                    role=role_name
                )
                raise TwoFactorRequiredError(
                    f"Fuer die Rolle '{role_name}' ist Zwei-Faktor-Authentifizierung erforderlich."
                )
            return current_user

        # J.1 SECURITY FIX: Superuser hat immer Zugriff, ABER muss 2FA haben fuer Admin-Rollen
        # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
        if current_user.is_superuser:
            if role_name in ("admin", "super_admin", "manager") and not current_user.totp_enabled and not settings.DEBUG:
                logger.warning(
                    "2fa_required_for_superuser",
                    user_id=str(current_user.id),
                    required_role=role_name
                )
                raise TwoFactorRequiredError(
                    "Superuser muessen Zwei-Faktor-Authentifizierung aktivieren fuer privilegierte Aktionen."
                )
            return current_user

        logger.warning(
            "role_denied",
            user_id=str(current_user.id),
            required_role=role_name
        )
        raise InsufficientRoleError(role_name)

    return role_checker


def require_any_role(*role_names: str) -> Callable:
    """
    FastAPI Dependency für mehrere Rollen (mindestens eine erforderlich).

    Args:
        *role_names: Mögliche Rollen (eine reicht)

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        InsufficientRoleError: Wenn keine der Rollen zugewiesen

    Beispiel:
        @router.get("/admin/reports")
        async def view_reports(
            user: User = Depends(require_any_role("admin", "manager"))
        ):
            ...
    """
    async def role_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        # J.1 SECURITY FIX: Superuser hat immer Zugriff, ABER muss 2FA haben fuer Admin-Rollen
        privileged_roles = {"admin", "super_admin", "manager"}
        requires_2fa = bool(set(role_names) & privileged_roles)

        if current_user.is_superuser:
            # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
            if requires_2fa and not current_user.totp_enabled and not settings.DEBUG:
                logger.warning(
                    "2fa_required_for_superuser_any_role",
                    user_id=str(current_user.id),
                    required_any=list(role_names)
                )
                raise TwoFactorRequiredError(
                    "Superuser muessen Zwei-Faktor-Authentifizierung aktivieren fuer privilegierte Aktionen."
                )
            return current_user

        service = PermissionService(db)
        user_roles = await service.get_user_roles(current_user)

        for role in user_roles:
            if role.name in role_names:
                # J.1 SECURITY FIX: Auch normale User muessen 2FA haben fuer Admin-Rollen
                # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
                privileged_roles = {"admin", "super_admin", "manager"}
                if role.name in privileged_roles and not current_user.totp_enabled and not settings.DEBUG:
                    logger.warning(
                        "2fa_required_for_privileged_role",
                        user_id=str(current_user.id),
                        role=role.name
                    )
                    raise TwoFactorRequiredError(
                        "Zwei-Faktor-Authentifizierung erforderlich fuer privilegierte Rollen."
                    )
                return current_user

        logger.warning(
            "role_denied",
            user_id=str(current_user.id),
            required_any=list(role_names)
        )
        raise InsufficientRoleError(
            role_names[0],
            f"Zugriff verweigert: Eine der folgenden Rollen erforderlich: {', '.join(role_names)}"
        )

    return role_checker


def require_min_role_priority(min_priority: int) -> Callable:
    """
    FastAPI Dependency für Mindest-Rollen-Priorität.

    Prüft, ob der Benutzer mindestens eine Rolle mit der angegebenen
    oder höheren Priorität hat.

    Args:
        min_priority: Mindest-Priorität (z.B. 75 für Manager)

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        InsufficientRoleError: Wenn keine Rolle mit ausreichender Priorität

    Beispiel:
        @router.post("/admin/users")
        async def create_user(
            user: User = Depends(require_min_role_priority(75))  # Manager+
        ):
            ...
    """
    async def priority_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        # J.1 SECURITY FIX: Hohe Prioritaet (>=75 = Manager+) erfordert 2FA
        # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
        requires_2fa = min_priority >= 75 and not settings.DEBUG

        # Superuser hat immer Zugriff, aber muss 2FA haben bei hoher Prioritaet
        if current_user.is_superuser:
            if requires_2fa and not current_user.totp_enabled:
                logger.warning(
                    "2fa_required_for_superuser_priority",
                    user_id=str(current_user.id),
                    min_priority=min_priority
                )
                raise TwoFactorRequiredError(
                    "Superuser muessen Zwei-Faktor-Authentifizierung aktivieren fuer privilegierte Aktionen."
                )
            return current_user

        service = PermissionService(db)
        user_roles = await service.get_user_roles(current_user)

        max_priority = max((role.priority for role in user_roles), default=0)

        if max_priority >= min_priority:
            # J.1 SECURITY FIX: Auch normale User muessen 2FA haben bei hoher Prioritaet
            if requires_2fa and not current_user.totp_enabled:
                logger.warning(
                    "2fa_required_for_priority",
                    user_id=str(current_user.id),
                    user_priority=max_priority,
                    min_priority=min_priority
                )
                raise TwoFactorRequiredError(
                    "Zwei-Faktor-Authentifizierung erforderlich fuer privilegierte Rollen."
                )
            return current_user

        logger.warning(
            "role_priority_denied",
            user_id=str(current_user.id),
            required_priority=min_priority,
            user_max_priority=max_priority
        )
        raise InsufficientRoleError(
            f"priority_{min_priority}",
            f"Zugriff verweigert: Mindest-Rollen-Priorität {min_priority} erforderlich"
        )

    return priority_checker


def require_superuser() -> Callable:
    """
    FastAPI Dependency für Superuser-Zugriff.

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        HTTPException 403: Wenn Benutzer kein Superuser

    Beispiel:
        @router.delete("/admin/system/reset")
        async def reset_system(
            user: User = Depends(require_superuser())
        ):
            ...
    """
    async def superuser_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        if not current_user.is_superuser:
            logger.warning(
                "superuser_required",
                user_id=str(current_user.id)
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Zugriff verweigert: Superuser-Rechte erforderlich"
            )

        # J.1 SECURITY FIX: Superuser-Aktionen erfordern IMMER 2FA
        # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
        if not current_user.totp_enabled and not settings.DEBUG:
            logger.warning(
                "2fa_required_for_superuser",
                user_id=str(current_user.id)
            )
            raise TwoFactorRequiredError(
                "Superuser muessen Zwei-Faktor-Authentifizierung aktivieren."
            )

        return current_user

    return superuser_checker


# ==================== Convenience Aliases ====================

# Kurzformen für häufige Berechtigungen
require_document_read = require_permission("documents:read")
require_document_write = require_permission("documents:write")
require_document_delete = require_any_permission("documents:delete", "documents:manage")
require_document_manage = require_permission("documents:manage")

require_user_read = require_permission("users:read")
require_user_write = require_permission("users:write")
require_user_manage = require_permission("users:manage")

require_role_read = require_permission("roles:read")
require_role_write = require_permission("roles:write")
require_role_manage = require_permission("roles:manage")

require_audit_read = require_permission("audit_logs:read")
require_audit_manage = require_permission("audit_logs:manage")

require_backup_read = require_permission("backups:read")
require_backup_write = require_permission("backups:write")
require_backup_manage = require_permission("backups:manage")

require_system_read = require_permission("system:read")
require_system_manage = require_permission("system:manage")

# Finanzen-spezifische Kurzformen
require_finance_read = require_permission("finance:read")
require_finance_write = require_permission("finance:write")
require_finance_delete = require_any_permission("finance:delete", "finance:manage")
require_finance_manage = require_permission("finance:manage")

# Rollen-basierte Kurzformen
require_admin = require_role("admin")
require_manager = require_any_role("admin", "manager")
require_analyst = require_any_role("admin", "manager", "analyst")

# Privat-Modul-spezifische Kurzformen
require_privat_read = require_permission("privat:read")
require_privat_write = require_permission("privat:write")
require_privat_manage = require_permission("privat:manage")
require_privat_admin = require_permission("privat:admin")
require_privat_user = require_any_role("admin", "privat_user")

# Personal/HR-Modul-spezifische Kurzformen (Enterprise Security)
# Employees - mit PII-Schutz
require_employee_read = require_permission("employees:read")
require_employee_read_pii = require_permission("employees:read_pii")
require_employee_write = require_permission("employees:write")
require_employee_delete = require_any_permission("employees:delete", "employees:manage")
require_employee_manage = require_permission("employees:manage")
require_employee_export = require_permission("employees:export")

# Departments
require_department_read = require_permission("departments:read")
require_department_write = require_permission("departments:write")
require_department_delete = require_any_permission("departments:delete", "departments:manage")
require_department_manage = require_permission("departments:manage")

# Positions - mit Gehalts-Schutz
require_position_read = require_permission("positions:read")
require_position_read_salary = require_permission("positions:read_salary")
require_position_write = require_permission("positions:write")
require_position_delete = require_any_permission("positions:delete", "positions:manage")
require_position_manage = require_permission("positions:manage")

# HR-spezifische Rollen-Kurzformen
require_hr_access = require_any_role("admin", "hr_manager", "hr_user")
require_hr_manager = require_any_role("admin", "hr_manager")
require_hr_admin = require_role("admin")


# ==================== 2FA Enforcement ====================

class TwoFactorRequiredError(HTTPException):
    """
    Exception wenn 2FA für privilegierte Operationen erforderlich ist.

    Wird ausgelöst wenn ein Admin-Benutzer keine 2FA aktiviert hat.
    """

    def __init__(
        self,
        detail: Optional[str] = None
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail or "Zwei-Faktor-Authentifizierung erforderlich. Bitte aktivieren Sie 2FA unter /auth/2fa/setup"
        )


def require_2fa_for_admin() -> Callable:
    """
    FastAPI Dependency die 2FA für Admin-Benutzer erzwingt.

    Diese Dependency prüft:
    1. Ob der Benutzer Admin-Rolle oder höhere Priorität (>=75) hat
    2. Wenn ja, ob 2FA aktiviert ist

    Normale Benutzer werden durchgelassen ohne 2FA-Prüfung.

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        TwoFactorRequiredError: Wenn Admin ohne aktivierte 2FA

    Beispiel:
        @router.delete("/admin/critical-data")
        async def delete_critical_data(
            user: User = Depends(require_2fa_for_admin())
        ):
            # Nur Admins MIT 2FA können diese Aktion ausführen
            ...
    """
    async def two_factor_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        # Superuser-Check
        is_privileged = current_user.is_superuser

        if not is_privileged:
            # Prüfe Rollen-Priorität (Admin = 100, Manager = 75)
            service = PermissionService(db)
            user_roles = await service.get_user_roles(current_user)

            if user_roles:
                max_priority = max((role.priority for role in user_roles), default=0)
                is_privileged = max_priority >= 75  # Manager oder höher

        # Privilegierte Benutzer müssen 2FA haben
        # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
        if is_privileged and not current_user.totp_enabled and not settings.DEBUG:
            logger.warning(
                "2fa_required_for_admin",
                user_id=str(current_user.id),
                username=current_user.username,
                is_superuser=current_user.is_superuser
            )
            raise TwoFactorRequiredError()

        return current_user

    return two_factor_checker


def require_admin_with_2fa() -> Callable:
    """
    FastAPI Dependency für Admin-Endpunkte mit 2FA-Pflicht.

    Kombiniert Admin-Rolle UND 2FA-Anforderung in einer Dependency.

    Returns:
        Dependency-Funktion die den Benutzer zurückgibt

    Raises:
        InsufficientRoleError: Wenn Benutzer kein Admin
        TwoFactorRequiredError: Wenn Admin ohne 2FA

    Beispiel:
        @router.post("/admin/system/reset")
        async def reset_system(
            user: User = Depends(require_admin_with_2fa())
        ):
            # Nur Admins MIT 2FA können System zurücksetzen
            ...
    """
    async def admin_2fa_checker(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ) -> User:
        # 1. Prüfe Admin-Rolle
        service = PermissionService(db)
        user_roles = await service.get_user_roles(current_user)

        is_admin = current_user.is_superuser or any(
            role.name == "admin" for role in user_roles
        )

        if not is_admin:
            logger.warning(
                "admin_role_required",
                user_id=str(current_user.id)
            )
            raise InsufficientRoleError("admin")

        # 2. Prüfe 2FA
        # Q.3 SECURITY: 2FA-Check nur in Production erzwingen
        if not current_user.totp_enabled and not settings.DEBUG:
            logger.warning(
                "2fa_required_for_admin_endpoint",
                user_id=str(current_user.id),
                username=current_user.username
            )
            raise TwoFactorRequiredError(
                "Für diesen Administratorbereich ist Zwei-Faktor-Authentifizierung erforderlich."
            )

        return current_user

    return admin_2fa_checker


# Convenience-Aliases für 2FA-geschützte Admin-Endpoints
require_admin_2fa = require_admin_with_2fa()


# ==================== Context Manager für manuelle Prüfung ====================

class PermissionContext:
    """
    Context für manuelle Berechtigungsprüfung innerhalb von Endpoints.

    Verwendung:
        async def my_endpoint(
            current_user: User = Depends(get_current_user),
            db: AsyncSession = Depends(get_db)
        ):
            perm = PermissionContext(db, current_user)

            if await perm.can("documents:delete"):
                # Löschen erlaubt
                ...
            else:
                # Nur anzeigen
                ...
    """

    def __init__(self, db: AsyncSession, user: User):
        """
        Initialisiert den Permission Context.

        Args:
            db: Datenbank-Session
            user: Aktueller Benutzer
        """
        self.service = PermissionService(db)
        self.user = user

    async def can(self, permission: str) -> bool:
        """
        Prüft, ob Benutzer Berechtigung hat.

        Args:
            permission: Zu prüfende Berechtigung

        Returns:
            True wenn Berechtigung vorhanden
        """
        return await self.service.has_permission(self.user, permission)

    async def can_any(self, permissions: List[str]) -> bool:
        """
        Prüft, ob Benutzer mindestens eine Berechtigung hat.

        Args:
            permissions: Liste der zu prüfenden Berechtigungen

        Returns:
            True wenn mindestens eine Berechtigung vorhanden
        """
        return await self.service.has_any_permission(self.user, permissions)

    async def can_all(self, permissions: List[str]) -> bool:
        """
        Prüft, ob Benutzer alle Berechtigungen hat.

        Args:
            permissions: Liste der erforderlichen Berechtigungen

        Returns:
            True wenn alle Berechtigungen vorhanden
        """
        return await self.service.has_all_permissions(self.user, permissions)

    async def require(self, permission: str) -> None:
        """
        Wirft Exception wenn Berechtigung fehlt.

        Args:
            permission: Erforderliche Berechtigung

        Raises:
            PermissionDeniedError: Wenn Berechtigung fehlt
        """
        if not await self.can(permission):
            raise PermissionDeniedError(permission)

    async def get_roles(self) -> List:
        """
        Holt alle Rollen des Benutzers.

        Returns:
            Liste der Benutzerrollen
        """
        return await self.service.get_user_roles(self.user)

    async def has_role(self, role_name: str) -> bool:
        """
        Prüft, ob Benutzer eine bestimmte Rolle hat.

        Args:
            role_name: Zu prüfender Rollenname

        Returns:
            True wenn Rolle zugewiesen
        """
        # J.1 SECURITY FIX: Superuser muss 2FA haben fuer privilegierte Rollen
        privileged_roles = {"admin", "super_admin", "manager", "owner"}
        if self.user.is_superuser:
            if role_name in privileged_roles and not self.user.totp_enabled:
                # Superuser ohne 2FA bekommt KEINE privilegierten Rollen
                return False
            return True

        roles = await self.get_roles()
        return any(role.name == role_name for role in roles)
