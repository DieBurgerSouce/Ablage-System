"""
Permission Service für Role-Based Access Control (RBAC).

Stellt Funktionen zur Berechtigungsprüfung und Rollenverwaltung bereit.
Alle Fehlermeldungen auf Deutsch für Benutzerinteraktionen.

J.6 SECURITY FIX: Redis-basierter Permission-Cache für Multi-Worker-Synchronisation.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from uuid import UUID

from sqlalchemy import select, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from app.core.safe_errors import safe_error_log
from app.db.models import (
    User,
    Role,
    Permission,
    user_roles,
    role_permissions,
    ResourceType,
    PermissionAction,
)

# J.6 SECURITY FIX: Redis für Multi-Worker-synchronized Permission Cache
# P1.1 SECURITY FIX: Tenant-isolierte Cache Keys - company_id:user_id
PERMISSION_CACHE_PREFIX = "permission_cache:"
PERMISSION_CACHE_TTL = 30  # Sekunden - kurz genug um Änderungen schnell zu propagieren

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
        # J.6 SECURITY FIX: In-Memory Cache nur als Fallback
        # Primär wird Redis verwendet für Multi-Worker-Synchronisation
        self._permission_cache: Dict[str, Set[str]] = {}
        # SECURITY FIX: Lock für thread-safe Cache-Zugriff bei concurrent requests
        self._cache_lock = asyncio.Lock()
        self._redis_client: Optional[Any] = None
        # FAANG-AUDIT FIX: Instanz-Variablen für Redis-Fallback-Tracking
        # WICHTIG: Als Instanz-Variablen, damit jede Service-Instanz eigenen Zustand hat
        self._redis_fallback_mode: bool = False
        self._redis_fallback_logged: bool = False

    async def _get_redis_client(self) -> Optional[Any]:
        """
        J.6 SECURITY FIX: Lazy-load Redis client.

        FAANG-AUDIT FIX: Logging + Health-Flag bei Redis-Fallback.
        Bei Redis-Ausfall wird jetzt:
        1. Eine WARNING geloggt (einmalig um Log-Spam zu vermeiden)
        2. Ein Class-Flag gesetzt für Health-Check Abfragen
        3. In-Memory Cache verwendet (mit Race-Condition Warnung)
        """
        if self._redis_client is None:
            try:
                from app.core.redis_state import get_redis

                self._redis_client = await get_redis()
                # Redis ist verfügbar - Fallback-Modus zurücksetzen
                if self._redis_fallback_mode:
                    logger.info(
                        "permission_cache_redis_restored",
                        message="Redis-Verbindung wiederhergestellt, Multi-Worker-Sync aktiv"
                    )
                    self._redis_fallback_mode = False
                    self._redis_fallback_logged = False
            except Exception as e:
                # FAANG-AUDIT FIX: Warnung loggen bei Redis-Fallback
                if not self._redis_fallback_logged:
                    logger.warning(
                        "permission_cache_redis_fallback",
                        **safe_error_log(e),
                        message="Redis nicht verfügbar - Fallback auf In-Memory Cache. "
                                "WARNUNG: Bei Multi-Worker-Deployment können Permission-Updates "
                                "zwischen Workern bis zu 30s inkonsistent sein!",
                        impact="security",
                        severity="high"
                    )
                    self._redis_fallback_logged = True
                self._redis_fallback_mode = True
        return self._redis_client

    def is_redis_available(self) -> bool:
        """
        FAANG-AUDIT FIX: Health-Check Methode für Redis-Verfügbarkeit.

        Returns:
            True wenn Redis verfügbar, False wenn Im In-Memory Fallback-Modus
        """
        return not self._redis_fallback_mode

    def _build_cache_key(self, user_id: str, company_id: Optional[str] = None) -> str:
        """P1.1 SECURITY FIX: Tenant-isolierte Cache-Keys generieren.

        Cache-Keys enthalten company_id um Cross-Tenant Leaks zu verhindern.
        Format: permission_cache:{company_id}:{user_id}

        Args:
            user_id: User-UUID als String
            company_id: Company-UUID als String (optional, default "global")

        Returns:
            Cache-Key mit Tenant-Isolation
        """
        tenant_id = company_id if company_id else "global"
        return f"{PERMISSION_CACHE_PREFIX}{tenant_id}:{user_id}"

    async def _get_cached_permissions_redis(
        self, user_id: str, company_id: Optional[str] = None
    ) -> Optional[Set[str]]:
        """J.6 SECURITY FIX: Permissions aus Redis Cache laden.
        P1.1 FIX: Tenant-isolierte Cache Keys.
        """
        redis = await self._get_redis_client()
        if redis is None:
            return None

        try:
            key = self._build_cache_key(user_id, company_id)
            data = await redis.get(key)
            if data:
                return set(json.loads(data))
        except Exception as e:
            logger.warning("permission_cache_redis_read_error", **safe_error_log(e))
        return None

    async def _set_cached_permissions_redis(
        self, user_id: str, permissions: Set[str], company_id: Optional[str] = None
    ) -> None:
        """J.6 SECURITY FIX: Permissions in Redis Cache speichern.
        P1.1 FIX: Tenant-isolierte Cache Keys.
        """
        redis = await self._get_redis_client()
        if redis is None:
            return

        try:
            key = self._build_cache_key(user_id, company_id)
            await redis.setex(key, PERMISSION_CACHE_TTL, json.dumps(list(permissions)))
        except Exception as e:
            logger.warning("permission_cache_redis_write_error", **safe_error_log(e))

    async def _invalidate_cache_redis(
        self, user_id: Optional[str] = None, company_id: Optional[str] = None
    ) -> None:
        """J.6 SECURITY FIX: Cache in Redis invalidieren.
        P1.1 FIX: Tenant-isolierte Invalidierung.
        """
        redis = await self._get_redis_client()
        if redis is None:
            return

        try:
            if user_id and company_id:
                # Spezifischer User in spezifischer Company
                key = self._build_cache_key(user_id, company_id)
                await redis.delete(key)
            elif user_id:
                # Alle Companies für diesen User
                pattern = f"{PERMISSION_CACHE_PREFIX}*:{user_id}"
                async for key in redis.scan_iter(match=pattern):
                    await redis.delete(key)
            elif company_id:
                # P1.1: Alle User in dieser Company invalidieren
                pattern = f"{PERMISSION_CACHE_PREFIX}{company_id}:*"
                async for key in redis.scan_iter(match=pattern):
                    await redis.delete(key)
            else:
                # Alle Permission-Cache-Keys löschen
                pattern = f"{PERMISSION_CACHE_PREFIX}*"
                async for key in redis.scan_iter(match=pattern):
                    await redis.delete(key)
        except Exception as e:
            logger.warning("permission_cache_redis_invalidate_error", **safe_error_log(e))

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

    async def get_user_permissions(
        self, user: User, company_id: Optional[UUID] = None
    ) -> Set[str]:
        """
        Holt alle Berechtigungen eines Benutzers aus allen zugewiesenen Rollen.

        J.6 SECURITY FIX: Redis-basierter Cache für Multi-Worker-Synchronisation.
        P1.1 SECURITY FIX: Tenant-isolierte Cache Keys mit company_id.
        Falls Redis nicht verfügbar, Fallback auf In-Memory mit Lock.

        Args:
            user: Der Benutzer
            company_id: Company-ID für Tenant-Isolation (optional)

        Returns:
            Set aller Berechtigungsnamen
        """
        user_id_str = str(user.id)
        company_id_str = str(company_id) if company_id else None

        # P1.1 FIX: Tenant-isolierter Cache-Key
        cache_key = self._build_cache_key(user_id_str, company_id_str)

        # J.6 FIX: Erst Redis-Cache prüfen (Multi-Worker-synchronized)
        redis_cached = await self._get_cached_permissions_redis(user_id_str, company_id_str)
        if redis_cached is not None:
            return redis_cached

        # Fallback: In-Memory Cache (auch tenant-isoliert)
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

            # J.6 FIX: In Redis UND In-Memory cachen (P1.1: tenant-isoliert)
            await self._set_cached_permissions_redis(user_id_str, permissions, company_id_str)
            self._permission_cache[cache_key] = permissions

            logger.debug(
                "user_permissions_loaded",
                user_id=user_id_str,
                company_id=company_id_str,
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

        # J.6 FIX: Async Cache-Invalidierung für Redis-Sync
        await self._clear_user_cache_async(user)

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
            # J.6 SECURITY FIX: Async cache invalidation (wie assign_role)
            await self._clear_user_cache_async(user)

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

        # P.3 SECURITY FIX: ALLE Caches invalidieren (In-Memory UND Redis)
        # Vorher wurde nur In-Memory geleert, Redis blieb 30s stale!
        self._permission_cache.clear()  # In-Memory
        await self._invalidate_cache_redis()  # P.3 FIX: Redis ebenfalls invalidieren

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

        # J.6 FIX: Cache in Redis UND In-Memory löschen
        await self._invalidate_cache_redis()  # Alle User betroffen
        self._permission_cache.clear()

        logger.info(
            "role_deleted",
            role_id=str(role.id),
            name=role.name
        )

        return True

    async def _clear_user_cache_async(
        self, user: User, company_id: Optional[UUID] = None
    ) -> None:
        """
        Löscht den Permission-Cache für einen Benutzer (async).

        J.6 FIX: Löscht Cache in Redis UND In-Memory.
        P1.1 FIX: Tenant-isolierte Cache Invalidierung.

        Args:
            user: Der Benutzer
            company_id: Company-ID (wenn None, alle Companies invalidieren)
        """
        user_id_str = str(user.id)
        company_id_str = str(company_id) if company_id else None

        # J.6 FIX: Redis-Cache invalidieren (P1.1: tenant-aware)
        await self._invalidate_cache_redis(user_id_str, company_id_str)

        # P1.1: In-Memory Cache - wenn company_id angegeben, nur diesen Key löschen
        if company_id_str:
            cache_key = self._build_cache_key(user_id_str, company_id_str)
            self._permission_cache.pop(cache_key, None)
        else:
            # Alle Company-spezifischen Keys für diesen User löschen
            keys_to_remove = [
                k for k in self._permission_cache.keys()
                if k.endswith(f":{user_id_str}")
            ]
            for key in keys_to_remove:
                self._permission_cache.pop(key, None)

    def _clear_user_cache(self, user: User) -> None:
        """
        Löscht den Permission-Cache für einen Benutzer (sync fallback).

        Note: Bevorzuge _clear_user_cache_async() in async Contexten
        für vollständige Redis-Invalidierung.
        P1.1: Diese Methode leert ALLE Company-Keys für den User (In-Memory).

        Args:
            user: Der Benutzer
        """
        user_id_str = str(user.id)
        # P1.1: Alle Company-spezifischen Keys für diesen User löschen
        keys_to_remove = [
            k for k in self._permission_cache.keys()
            if k.endswith(f":{user_id_str}")
        ]
        for key in keys_to_remove:
            self._permission_cache.pop(key, None)

    async def invalidate_company_cache_async(self, company_id: UUID) -> None:
        """
        P1.1 SECURITY: Invalidiert alle Permission-Caches einer Company.

        Sollte aufgerufen werden bei:
        - Company-weiten Rollen-Änderungen
        - Company-Löschung
        - Massen-Benutzer-Updates

        Args:
            company_id: Company-ID
        """
        company_id_str = str(company_id)

        # Redis-Cache für diese Company invalidieren
        await self._invalidate_cache_redis(company_id=company_id_str)

        # In-Memory: Alle Keys dieser Company löschen
        keys_to_remove = [
            k for k in self._permission_cache.keys()
            if k.startswith(f"{PERMISSION_CACHE_PREFIX}{company_id_str}:")
        ]
        for key in keys_to_remove:
            self._permission_cache.pop(key, None)

        logger.info(
            "company_permission_cache_invalidated",
            company_id=company_id_str,
            cleared_keys=len(keys_to_remove)
        )

    async def clear_cache_async(self) -> None:
        """
        Löscht den gesamten Permission-Cache (async-safe).

        J.6 FIX: Löscht Cache in Redis UND In-Memory.
        """
        async with self._cache_lock:
            await self._invalidate_cache_redis()  # Alle löschen
            self._permission_cache.clear()
            logger.debug("permission_cache_cleared_async")

    def clear_cache(self) -> None:
        """
        Löscht den gesamten Permission-Cache (sync version).

        Warnung: Sollte nicht während aktiver async Operations verwendet werden.
        Bevorzuge clear_cache_async() in async Contexten.
        Note: Redis-Cache wird hier NICHT gelöscht (nur async).
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
