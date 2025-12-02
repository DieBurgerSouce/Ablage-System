"""
Permission Service für Role-Based Access Control (RBAC).

Stellt Funktionen zur Berechtigungsprüfung und Rollenverwaltung bereit.
Alle Fehlermeldungen auf Deutsch für Benutzerinteraktionen.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from uuid import UUID

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.db.models import (
    User,
    Role,
    Permission,
    user_roles,
    role_permissions,
    ResourceType,
    PermissionAction,
)

logger = structlog.get_logger(__name__)


class PermissionService:
    """
    Service für RBAC-Berechtigungsprüfungen.

    Bietet:
    - Berechtigungsprüfung für Benutzer
    - Rollenverwaltung (zuweisen, entfernen)
    - Permission-Caching für Performance
    """

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den PermissionService.

        Args:
            db: AsyncSession für Datenbankzugriff
        """
        self.db = db
        self._permission_cache: Dict[str, Set[str]] = {}
        # SECURITY FIX: Lock für thread-safe Cache-Zugriff bei concurrent requests
        self._cache_lock = asyncio.Lock()

    async def has_permission(
        self,
        user: User,
        permission_name: str,
        resource_id: Optional[UUID] = None
    ) -> bool:
        """
        Prüft, ob ein Benutzer eine bestimmte Berechtigung hat.

        Superuser haben immer alle Berechtigungen.
        Prüft alle Rollen des Benutzers nach der Berechtigung.

        Args:
            user: Der zu prüfende Benutzer
            permission_name: Berechtigungsname (z.B. "documents:read")
            resource_id: Optionale Ressourcen-ID für ressourcenspezifische Prüfungen

        Returns:
            True wenn Berechtigung vorhanden, sonst False
        """
        # Superuser hat alle Berechtigungen
        if user.is_superuser:
            logger.debug(
                "permission_granted_superuser",
                user_id=str(user.id),
                permission=permission_name
            )
            return True

        # Prüfe ob Benutzer aktiv ist
        if not user.is_active:
            logger.warning(
                "permission_denied_inactive_user",
                user_id=str(user.id),
                permission=permission_name
            )
            return False

        # Hole alle Berechtigungen des Benutzers
        user_permissions = await self.get_user_permissions(user)

        # Prüfe direkte Berechtigung
        if permission_name in user_permissions:
            logger.debug(
                "permission_granted",
                user_id=str(user.id),
                permission=permission_name
            )
            return True

        # Prüfe "manage" Berechtigung (impliziert read/write/delete)
        resource_type = permission_name.split(":")[0] if ":" in permission_name else ""
        manage_permission = f"{resource_type}:manage"
        if manage_permission in user_permissions:
            logger.debug(
                "permission_granted_via_manage",
                user_id=str(user.id),
                permission=permission_name,
                granted_by=manage_permission
            )
            return True

        logger.debug(
            "permission_denied",
            user_id=str(user.id),
            permission=permission_name
        )
        return False

    async def has_any_permission(
        self,
        user: User,
        permission_names: List[str]
    ) -> bool:
        """
        Prüft, ob ein Benutzer mindestens eine der angegebenen Berechtigungen hat.

        Args:
            user: Der zu prüfende Benutzer
            permission_names: Liste der zu prüfenden Berechtigungen

        Returns:
            True wenn mindestens eine Berechtigung vorhanden
        """
        for permission in permission_names:
            if await self.has_permission(user, permission):
                return True
        return False

    async def has_all_permissions(
        self,
        user: User,
        permission_names: List[str]
    ) -> bool:
        """
        Prüft, ob ein Benutzer alle angegebenen Berechtigungen hat.

        Args:
            user: Der zu prüfende Benutzer
            permission_names: Liste der erforderlichen Berechtigungen

        Returns:
            True wenn alle Berechtigungen vorhanden
        """
        for permission in permission_names:
            if not await self.has_permission(user, permission):
                return False
        return True

    async def get_user_permissions(self, user: User) -> Set[str]:
        """
        Holt alle Berechtigungen eines Benutzers aus allen zugewiesenen Rollen.

        SECURITY FIX: Thread-safe mit asyncio.Lock um Race Conditions zu vermeiden.
        Double-checked locking Pattern für optimale Performance.

        Args:
            user: Der Benutzer

        Returns:
            Set aller Berechtigungsnamen
        """
        cache_key = str(user.id)

        # Fast path: Check cache without lock (read is atomic for simple types)
        if cache_key in self._permission_cache:
            return self._permission_cache[cache_key]

        # Slow path: Acquire lock for cache update
        async with self._cache_lock:
            # Double-check: Cache könnte von anderem Request gefüllt worden sein
            if cache_key in self._permission_cache:
                return self._permission_cache[cache_key]

            # Query all permissions via user roles
            stmt = (
                select(Permission.name)
                .join(role_permissions, Permission.id == role_permissions.c.permission_id)
                .join(Role, Role.id == role_permissions.c.role_id)
                .join(user_roles, Role.id == user_roles.c.role_id)
                .where(
                    and_(
                        user_roles.c.user_id == user.id,
                        Role.is_active == True
                    )
                )
            )

            result = await self.db.execute(stmt)
            permissions = set(row[0] for row in result.fetchall())

            # Cache result (innerhalb des Locks)
            self._permission_cache[cache_key] = permissions

            logger.debug(
                "user_permissions_loaded",
                user_id=str(user.id),
                permission_count=len(permissions)
            )

            return permissions

    async def get_user_roles(self, user: User) -> List[Role]:
        """
        Holt alle Rollen eines Benutzers.

        Args:
            user: Der Benutzer

        Returns:
            Liste der zugewiesenen Rollen
        """
        stmt = (
            select(Role)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user.id)
            .options(selectinload(Role.permissions))
        )

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def assign_role(
        self,
        user: User,
        role: Role,
        assigned_by: Optional[User] = None
    ) -> bool:
        """
        Weist einem Benutzer eine Rolle zu.

        Args:
            user: Der Benutzer
            role: Die zuzuweisende Rolle
            assigned_by: Der zuweisende Admin (optional)

        Returns:
            True wenn erfolgreich, False wenn Rolle bereits zugewiesen

        Raises:
            ValueError: Wenn Rolle nicht aktiv ist
        """
        if not role.is_active:
            raise ValueError(f"Rolle '{role.display_name}' ist nicht aktiv")

        # Check if already assigned
        existing = await self.db.execute(
            select(user_roles)
            .where(
                and_(
                    user_roles.c.user_id == user.id,
                    user_roles.c.role_id == role.id
                )
            )
        )
        if existing.fetchone():
            logger.info(
                "role_already_assigned",
                user_id=str(user.id),
                role=role.name
            )
            return False

        # Assign role
        await self.db.execute(
            user_roles.insert().values(
                user_id=user.id,
                role_id=role.id,
                assigned_at=datetime.now(timezone.utc),
                assigned_by_id=assigned_by.id if assigned_by else None
            )
        )
        await self.db.commit()

        # Clear cache
        self._clear_user_cache(user)

        logger.info(
            "role_assigned",
            user_id=str(user.id),
            role=role.name,
            assigned_by=str(assigned_by.id) if assigned_by else None
        )
        return True

    async def remove_role(self, user: User, role: Role) -> bool:
        """
        Entfernt eine Rolle von einem Benutzer.

        Args:
            user: Der Benutzer
            role: Die zu entfernende Rolle

        Returns:
            True wenn erfolgreich, False wenn Rolle nicht zugewiesen war
        """
        result = await self.db.execute(
            delete(user_roles)
            .where(
                and_(
                    user_roles.c.user_id == user.id,
                    user_roles.c.role_id == role.id
                )
            )
        )
        await self.db.commit()

        if result.rowcount > 0:
            # Clear cache
            self._clear_user_cache(user)

            logger.info(
                "role_removed",
                user_id=str(user.id),
                role=role.name
            )
            return True

        logger.info(
            "role_not_assigned",
            user_id=str(user.id),
            role=role.name
        )
        return False

    async def get_all_roles(self, include_inactive: bool = False) -> List[Role]:
        """
        Holt alle verfügbaren Rollen.

        Args:
            include_inactive: Auch inaktive Rollen einschließen

        Returns:
            Liste aller Rollen
        """
        stmt = select(Role).options(selectinload(Role.permissions))

        if not include_inactive:
            stmt = stmt.where(Role.is_active == True)

        stmt = stmt.order_by(Role.priority.desc())

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        """
        Holt eine Rolle nach Namen.

        Args:
            name: Rollenname

        Returns:
            Rolle oder None
        """
        stmt = (
            select(Role)
            .where(Role.name == name)
            .options(selectinload(Role.permissions))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_role_by_id(self, role_id: UUID) -> Optional[Role]:
        """
        Holt eine Rolle nach ID.

        Args:
            role_id: Rollen-ID

        Returns:
            Rolle oder None
        """
        stmt = (
            select(Role)
            .where(Role.id == role_id)
            .options(selectinload(Role.permissions))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_permissions(self) -> List[Permission]:
        """
        Holt alle verfügbaren Berechtigungen.

        Returns:
            Liste aller Berechtigungen
        """
        stmt = select(Permission).order_by(Permission.resource_type, Permission.action)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_role(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        priority: int = 0,
        color: str = "#6B7280",
        permission_names: Optional[List[str]] = None
    ) -> Role:
        """
        Erstellt eine neue Rolle.

        Args:
            name: Eindeutiger Rollenname (lowercase, keine Leerzeichen)
            display_name: Anzeigename
            description: Beschreibung
            priority: Priorität (höher = mehr Rechte)
            color: Hex-Farbcode für UI
            permission_names: Liste der Berechtigungsnamen

        Returns:
            Die erstellte Rolle

        Raises:
            ValueError: Wenn Name bereits existiert
        """
        # Check for existing role
        existing = await self.get_role_by_name(name)
        if existing:
            raise ValueError(f"Rolle mit Name '{name}' existiert bereits")

        # Create role
        role = Role(
            name=name.lower().replace(" ", "_"),
            display_name=display_name,
            description=description,
            priority=priority,
            color=color,
            is_system=False,
            is_active=True
        )
        self.db.add(role)
        await self.db.flush()

        # Assign permissions
        if permission_names:
            for perm_name in permission_names:
                stmt = select(Permission).where(Permission.name == perm_name)
                result = await self.db.execute(stmt)
                permission = result.scalar_one_or_none()
                if permission:
                    await self.db.execute(
                        role_permissions.insert().values(
                            role_id=role.id,
                            permission_id=permission.id
                        )
                    )

        await self.db.commit()

        logger.info(
            "role_created",
            role_id=str(role.id),
            name=role.name,
            permissions=permission_names or []
        )

        return role

    async def update_role(
        self,
        role: Role,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        color: Optional[str] = None,
        is_active: Optional[bool] = None,
        permission_names: Optional[List[str]] = None
    ) -> Role:
        """
        Aktualisiert eine Rolle.

        System-Rollen können nur eingeschränkt bearbeitet werden.

        Args:
            role: Die zu aktualisierende Rolle
            display_name: Neuer Anzeigename
            description: Neue Beschreibung
            priority: Neue Priorität
            color: Neue Farbe
            is_active: Aktivierungsstatus
            permission_names: Neue Berechtigungsliste (ersetzt alle)

        Returns:
            Die aktualisierte Rolle

        Raises:
            ValueError: Wenn System-Rolle nicht geändert werden darf
        """
        if role.is_system:
            # System roles: only description and color can be changed
            if any([display_name, priority is not None, is_active is not None, permission_names]):
                raise ValueError(
                    f"System-Rolle '{role.name}' kann nicht vollständig bearbeitet werden. "
                    "Nur Beschreibung und Farbe sind änderbar."
                )

        if display_name:
            role.display_name = display_name
        if description is not None:
            role.description = description
        if priority is not None and not role.is_system:
            role.priority = priority
        if color:
            role.color = color
        if is_active is not None and not role.is_system:
            role.is_active = is_active

        # Update permissions if provided
        if permission_names is not None and not role.is_system:
            # Remove all existing permissions
            await self.db.execute(
                delete(role_permissions).where(role_permissions.c.role_id == role.id)
            )

            # Add new permissions
            for perm_name in permission_names:
                stmt = select(Permission).where(Permission.name == perm_name)
                result = await self.db.execute(stmt)
                permission = result.scalar_one_or_none()
                if permission:
                    await self.db.execute(
                        role_permissions.insert().values(
                            role_id=role.id,
                            permission_id=permission.id
                        )
                    )

        await self.db.commit()

        # Clear all user caches (role permissions changed)
        self._permission_cache.clear()

        logger.info(
            "role_updated",
            role_id=str(role.id),
            name=role.name
        )

        return role

    async def delete_role(self, role: Role) -> bool:
        """
        Löscht eine Rolle.

        System-Rollen können nicht gelöscht werden.

        Args:
            role: Die zu löschende Rolle

        Returns:
            True wenn erfolgreich

        Raises:
            ValueError: Wenn System-Rolle nicht gelöscht werden darf
        """
        if role.is_system:
            raise ValueError(f"System-Rolle '{role.name}' kann nicht gelöscht werden")

        await self.db.delete(role)
        await self.db.commit()

        # Clear all user caches
        self._permission_cache.clear()

        logger.info(
            "role_deleted",
            role_id=str(role.id),
            name=role.name
        )

        return True

    def _clear_user_cache(self, user: User) -> None:
        """
        Löscht den Permission-Cache für einen Benutzer.

        Note: Dict key deletion ist atomic in CPython, daher kein Lock nötig
        für einzelne User-Einträge.

        Args:
            user: Der Benutzer
        """
        cache_key = str(user.id)
        # pop statt del um KeyError zu vermeiden wenn Key bereits gelöscht
        self._permission_cache.pop(cache_key, None)

    async def clear_cache_async(self) -> None:
        """
        Löscht den gesamten Permission-Cache (async-safe).
        """
        async with self._cache_lock:
            self._permission_cache.clear()
            logger.debug("permission_cache_cleared_async")

    def clear_cache(self) -> None:
        """
        Löscht den gesamten Permission-Cache (sync version).

        Warnung: Sollte nicht während aktiver async Operations verwendet werden.
        Bevorzuge clear_cache_async() in async Contexten.
        """
        self._permission_cache.clear()
        logger.debug("permission_cache_cleared")


# ==================== Convenience Functions ====================

async def check_permission(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_id: Optional[UUID] = None
) -> bool:
    """
    Convenience-Funktion zur Berechtigungsprüfung.

    Args:
        db: Datenbank-Session
        user: Der zu prüfende Benutzer
        permission: Berechtigungsname
        resource_id: Optionale Ressourcen-ID

    Returns:
        True wenn Berechtigung vorhanden
    """
    service = PermissionService(db)
    return await service.has_permission(user, permission, resource_id)


async def require_permission(
    db: AsyncSession,
    user: User,
    permission: str,
    resource_id: Optional[UUID] = None
) -> None:
    """
    Prüft Berechtigung und wirft Exception wenn nicht vorhanden.

    Args:
        db: Datenbank-Session
        user: Der zu prüfende Benutzer
        permission: Erforderliche Berechtigung
        resource_id: Optionale Ressourcen-ID

    Raises:
        PermissionError: Wenn Berechtigung fehlt
    """
    if not await check_permission(db, user, permission, resource_id):
        raise PermissionError(
            f"Zugriff verweigert: Berechtigung '{permission}' erforderlich"
        )
