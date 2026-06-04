# -*- coding: utf-8 -*-
"""
Unit-Tests für Permission Service (RBAC).

Testet:
- Berechtigungsprüfung (has_permission)
- Rollenverwaltung (assign, remove)
- Permission-Caching und Cache-Invalidierung
- Superuser-Überprüfung (immer alle Berechtigungen)
- Manage-Permission-Vererbung
- Role CRUD-Operationen
- Thread-Safety des Caches
- Convenience-Funktionen (check_permission, require_permission)

Feinpoliert und durchdacht - Enterprise-grade RBAC-Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Set, List
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db():
    """Create mock async database session."""
    db = AsyncMock()
    db.add = Mock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def sample_user():
    """Create sample user object."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_active = True
    user.is_superuser = False
    return user


@pytest.fixture
def superuser():
    """Create superuser object."""
    user = Mock()
    user.id = uuid4()
    user.email = "admin@example.com"
    user.is_active = True
    user.is_superuser = True
    return user


@pytest.fixture
def inactive_user():
    """Create inactive user object."""
    user = Mock()
    user.id = uuid4()
    user.email = "inactive@example.com"
    user.is_active = False
    user.is_superuser = False
    return user


@pytest.fixture
def sample_role():
    """Create sample role object."""
    role = Mock()
    role.id = uuid4()
    role.name = "editor"
    role.display_name = "Editor"
    role.description = "Can edit documents"
    role.is_active = True
    role.is_system = False
    role.priority = 50
    role.color = "#3B82F6"
    role.permissions = []
    return role


@pytest.fixture
def system_role():
    """Create system role object."""
    role = Mock()
    role.id = uuid4()
    role.name = "admin"
    role.display_name = "Administrator"
    role.description = "Full system access"
    role.is_active = True
    role.is_system = True
    role.priority = 100
    role.color = "#EF4444"
    role.permissions = []
    return role


@pytest.fixture
def sample_permission():
    """Create sample permission object."""
    perm = Mock()
    perm.id = uuid4()
    perm.name = "documents:read"
    perm.resource_type = "documents"
    perm.action = "read"
    perm.description = "Read documents"
    return perm


@pytest.fixture
def permission_service(mock_db):
    """Create Permission Service instance."""
    from app.services.permission_service import PermissionService
    return PermissionService(mock_db)


# ========================= has_permission Tests =========================


class TestHasPermission:
    """Tests for permission checking."""

    @pytest.mark.asyncio
    async def test_superuser_has_all_permissions(self, permission_service, superuser):
        """Superuser sollte immer alle Berechtigungen haben."""
        result = await permission_service.has_permission(superuser, "documents:delete")

        assert result is True

    @pytest.mark.asyncio
    async def test_inactive_user_denied(self, permission_service, inactive_user):
        """Inaktive Benutzer sollten keine Berechtigungen haben."""
        result = await permission_service.has_permission(inactive_user, "documents:read")

        assert result is False

    @pytest.mark.asyncio
    async def test_has_direct_permission(self, permission_service, sample_user, mock_db):
        """Benutzer mit direkter Berechtigung sollte True bekommen."""
        # Mock permission query
        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",), ("documents:write",)]
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_permission(sample_user, "documents:read")

        assert result is True

    @pytest.mark.asyncio
    async def test_missing_permission_denied(self, permission_service, sample_user, mock_db):
        """Benutzer ohne Berechtigung sollte False bekommen."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",)]
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_permission(sample_user, "documents:delete")

        assert result is False

    @pytest.mark.asyncio
    async def test_manage_permission_implies_all(self, permission_service, sample_user, mock_db):
        """manage-Berechtigung sollte read/write/delete implizieren."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:manage",)]
        mock_db.execute.return_value = mock_result

        # manage should imply read
        assert await permission_service.has_permission(sample_user, "documents:read") is True

        # manage should imply write
        permission_service._permission_cache.clear()
        mock_db.execute.return_value = mock_result
        assert await permission_service.has_permission(sample_user, "documents:write") is True

        # manage should imply delete
        permission_service._permission_cache.clear()
        mock_db.execute.return_value = mock_result
        assert await permission_service.has_permission(sample_user, "documents:delete") is True


# ========================= has_any_permission Tests =========================


class TestHasAnyPermission:
    """Tests for checking if user has any of multiple permissions."""

    @pytest.mark.asyncio
    async def test_has_any_permission_one_match(self, permission_service, sample_user, mock_db):
        """Sollte True zurückgeben wenn eine Berechtigung passt."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",)]
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_any_permission(
            sample_user,
            ["documents:read", "documents:write", "documents:delete"]
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_has_any_permission_none_match(self, permission_service, sample_user, mock_db):
        """Sollte False zurückgeben wenn keine Berechtigung passt."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("users:read",)]
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_any_permission(
            sample_user,
            ["documents:read", "documents:write"]
        )

        assert result is False


# ========================= has_all_permissions Tests =========================


class TestHasAllPermissions:
    """Tests for checking if user has all required permissions."""

    @pytest.mark.asyncio
    async def test_has_all_permissions_success(self, permission_service, sample_user, mock_db):
        """Sollte True zurückgeben wenn alle Berechtigungen vorhanden."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",), ("documents:write",)]
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_all_permissions(
            sample_user,
            ["documents:read", "documents:write"]
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_has_all_permissions_missing_one(self, permission_service, sample_user, mock_db):
        """Sollte False zurückgeben wenn eine Berechtigung fehlt."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",)]
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_all_permissions(
            sample_user,
            ["documents:read", "documents:write"]
        )

        assert result is False


# ========================= Permission Cache Tests =========================


class TestPermissionCache:
    """Tests for permission caching."""

    @pytest.mark.asyncio
    async def test_cache_populated_on_first_query(self, permission_service, sample_user, mock_db):
        """Cache sollte bei erster Abfrage befüllt werden."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",)]
        mock_db.execute.return_value = mock_result

        # First call - should hit database
        await permission_service.get_user_permissions(sample_user)

        assert permission_service._build_cache_key(str(sample_user.id)) in permission_service._permission_cache

    @pytest.mark.asyncio
    async def test_cache_used_on_subsequent_queries(self, permission_service, sample_user, mock_db):
        """Cache sollte bei wiederholten Abfragen verwendet werden."""
        # Pre-populate cache (P1.1: tenant-isolierter Key permission_cache:global:{id})
        permission_service._permission_cache[permission_service._build_cache_key(str(sample_user.id))] = {"documents:read"}

        # This should NOT hit the database
        permissions = await permission_service.get_user_permissions(sample_user)

        assert "documents:read" in permissions
        mock_db.execute.assert_not_called()

    def test_clear_user_cache(self, permission_service, sample_user):
        """Cache für einzelnen User sollte löschbar sein."""
        cache_key = permission_service._build_cache_key(str(sample_user.id))
        permission_service._permission_cache[cache_key] = {"documents:read"}

        permission_service._clear_user_cache(sample_user)

        assert cache_key not in permission_service._permission_cache

    def test_clear_all_cache(self, permission_service, sample_user, superuser):
        """Gesamter Cache sollte löschbar sein."""
        permission_service._permission_cache[str(sample_user.id)] = {"documents:read"}
        permission_service._permission_cache[str(superuser.id)] = {"admin"}

        permission_service.clear_cache()

        assert len(permission_service._permission_cache) == 0


# ========================= Role Assignment Tests =========================


class TestRoleAssignment:
    """Tests for role assignment and removal."""

    @pytest.mark.asyncio
    async def test_assign_role_success(self, permission_service, sample_user, sample_role, mock_db):
        """Rolle sollte erfolgreich zugewiesen werden."""
        # Mock "not already assigned" check
        mock_result = Mock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await permission_service.assign_role(sample_user, sample_role)

        assert result is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_assign_role_already_assigned(self, permission_service, sample_user, sample_role, mock_db):
        """Bereits zugewiesene Rolle sollte False zurückgeben."""
        mock_result = Mock()
        mock_result.fetchone.return_value = (sample_user.id, sample_role.id)
        mock_db.execute.return_value = mock_result

        result = await permission_service.assign_role(sample_user, sample_role)

        assert result is False

    @pytest.mark.asyncio
    async def test_assign_inactive_role_fails(self, permission_service, sample_user, sample_role, mock_db):
        """Inaktive Rolle sollte nicht zuweisbar sein."""
        sample_role.is_active = False

        with pytest.raises(ValueError) as exc_info:
            await permission_service.assign_role(sample_user, sample_role)

        assert "nicht aktiv" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_remove_role_success(self, permission_service, sample_user, sample_role, mock_db):
        """Rolle sollte erfolgreich entfernt werden."""
        mock_result = Mock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        result = await permission_service.remove_role(sample_user, sample_role)

        assert result is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_role_not_assigned(self, permission_service, sample_user, sample_role, mock_db):
        """Entfernen nicht zugewiesener Rolle sollte False zurückgeben."""
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        result = await permission_service.remove_role(sample_user, sample_role)

        assert result is False


# ========================= Role CRUD Tests =========================


class TestRoleCRUD:
    """Tests for role CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_role_by_name(self, permission_service, sample_role, mock_db):
        """Rolle sollte nach Namen gefunden werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_role
        mock_db.execute.return_value = mock_result

        result = await permission_service.get_role_by_name("editor")

        assert result == sample_role

    @pytest.mark.asyncio
    async def test_get_role_by_name_not_found(self, permission_service, mock_db):
        """Nicht existierende Rolle sollte None zurückgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await permission_service.get_role_by_name("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_roles(self, permission_service, sample_role, mock_db):
        """Alle Rollen sollten auflistbar sein."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [sample_role]
        mock_db.execute.return_value = mock_result

        roles = await permission_service.get_all_roles()

        assert len(roles) == 1

    @pytest.mark.asyncio
    async def test_create_role_success(self, permission_service, mock_db):
        """Rolle sollte erfolgreich erstellt werden."""
        # Mock "not exists" check
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        role = await permission_service.create_role(
            name="new_role",
            display_name="New Role",
            description="Test role",
            priority=25
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_role_duplicate_name(self, permission_service, sample_role, mock_db):
        """Doppelter Rollenname sollte Fehler werfen."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_role
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError) as exc_info:
            await permission_service.create_role(
                name="editor",
                display_name="Editor"
            )

        assert "existiert bereits" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_delete_role_success(self, permission_service, sample_role, mock_db):
        """Nicht-System-Rolle sollte löschbar sein."""
        result = await permission_service.delete_role(sample_role)

        assert result is True
        mock_db.delete.assert_called_once_with(sample_role)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_system_role_fails(self, permission_service, system_role, mock_db):
        """System-Rolle sollte nicht löschbar sein."""
        with pytest.raises(ValueError) as exc_info:
            await permission_service.delete_role(system_role)

        assert "System-Rolle" in str(exc_info.value)


# ========================= Update Role Tests =========================


class TestUpdateRole:
    """Tests for role updates."""

    @pytest.mark.asyncio
    async def test_update_role_display_name(self, permission_service, sample_role, mock_db):
        """Display-Name sollte aktualisierbar sein."""
        await permission_service.update_role(sample_role, display_name="Updated Editor")

        assert sample_role.display_name == "Updated Editor"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_role_priority(self, permission_service, sample_role, mock_db):
        """Priorität sollte aktualisierbar sein."""
        await permission_service.update_role(sample_role, priority=75)

        assert sample_role.priority == 75

    @pytest.mark.asyncio
    async def test_update_role_deactivate(self, permission_service, sample_role, mock_db):
        """Rolle sollte deaktivierbar sein."""
        await permission_service.update_role(sample_role, is_active=False)

        assert sample_role.is_active is False

    @pytest.mark.asyncio
    async def test_update_system_role_limited(self, permission_service, system_role, mock_db):
        """System-Rolle sollte nur eingeschränkt änderbar sein."""
        with pytest.raises(ValueError) as exc_info:
            await permission_service.update_role(
                system_role,
                display_name="Cannot Change",
                priority=200
            )

        assert "System-Rolle" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_update_system_role_description_allowed(self, permission_service, system_role, mock_db):
        """System-Rolle: Nur Beschreibung/Farbe änderbar."""
        # This should NOT raise
        await permission_service.update_role(
            system_role,
            description="Updated description",
            color="#FF0000"
        )

        assert system_role.description == "Updated description"
        assert system_role.color == "#FF0000"


# ========================= Convenience Functions Tests =========================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_check_permission_function(self, mock_db, sample_user):
        """check_permission Convenience-Funktion."""
        from app.services.permission_service import check_permission

        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",)]
        mock_db.execute.return_value = mock_result

        result = await check_permission(mock_db, sample_user, "documents:read")

        assert result is True

    @pytest.mark.asyncio
    async def test_require_permission_success(self, mock_db, sample_user):
        """require_permission sollte bei vorhandener Berechtigung nicht werfen."""
        from app.services.permission_service import require_permission

        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",)]
        mock_db.execute.return_value = mock_result

        # Should not raise
        await require_permission(mock_db, sample_user, "documents:read")

    @pytest.mark.asyncio
    async def test_require_permission_denied(self, mock_db, sample_user):
        """require_permission sollte bei fehlender Berechtigung werfen."""
        from app.services.permission_service import require_permission

        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        with pytest.raises(PermissionError) as exc_info:
            await require_permission(mock_db, sample_user, "admin:settings")

        assert "Zugriff verweigert" in str(exc_info.value)


# ========================= Get User Roles Tests =========================


class TestGetUserRoles:
    """Tests for retrieving user roles."""

    @pytest.mark.asyncio
    async def test_get_user_roles(self, permission_service, sample_user, sample_role, mock_db):
        """Alle Rollen eines Benutzers sollten abrufbar sein."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [sample_role]
        mock_db.execute.return_value = mock_result

        roles = await permission_service.get_user_roles(sample_user)

        assert len(roles) == 1
        assert roles[0] == sample_role

    @pytest.mark.asyncio
    async def test_get_user_roles_empty(self, permission_service, sample_user, mock_db):
        """Benutzer ohne Rollen sollte leere Liste bekommen."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        roles = await permission_service.get_user_roles(sample_user)

        assert len(roles) == 0


# ========================= Get All Permissions Tests =========================


class TestGetAllPermissions:
    """Tests for retrieving all permissions."""

    @pytest.mark.asyncio
    async def test_get_all_permissions(self, permission_service, sample_permission, mock_db):
        """Alle Berechtigungen sollten abrufbar sein."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [sample_permission]
        mock_db.execute.return_value = mock_result

        permissions = await permission_service.get_all_permissions()

        assert len(permissions) == 1


# ========================= Thread Safety Tests =========================


class TestThreadSafety:
    """Tests for thread safety of cache operations."""

    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, permission_service, mock_db):
        """Cache sollte bei konkurrierendem Zugriff funktionieren."""
        import asyncio

        # Create multiple users
        users = [Mock(id=uuid4(), is_active=True, is_superuser=False) for _ in range(10)]

        mock_result = Mock()
        mock_result.fetchall.return_value = [("documents:read",)]
        mock_db.execute.return_value = mock_result

        # Concurrent permission checks
        tasks = [
            permission_service.get_user_permissions(user)
            for user in users
        ]

        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        for result in results:
            assert "documents:read" in result

    def test_cache_clear_during_read(self, permission_service, sample_user):
        """Cache-Clear während Lesen sollte nicht crashen."""
        permission_service._permission_cache[str(sample_user.id)] = {"documents:read"}

        # Simulate clearing cache while it might be accessed
        permission_service.clear_cache()

        # Should not crash
        assert str(sample_user.id) not in permission_service._permission_cache


# ========================= Edge Cases =========================


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_permission_name(self, permission_service, sample_user, mock_db):
        """Leerer Berechtigungsname sollte False zurückgeben."""
        mock_result = Mock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_permission(sample_user, "")

        assert result is False

    @pytest.mark.asyncio
    async def test_permission_without_colon(self, permission_service, sample_user, mock_db):
        """Berechtigung ohne Doppelpunkt sollte funktionieren."""
        mock_result = Mock()
        mock_result.fetchall.return_value = [("admin",)]
        mock_db.execute.return_value = mock_result

        result = await permission_service.has_permission(sample_user, "admin")

        assert result is True

    @pytest.mark.asyncio
    async def test_role_with_special_characters(self, permission_service, mock_db):
        """Rollenname sollte normalisiert werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        added_role = None
        def capture_add(obj):
            nonlocal added_role
            added_role = obj
        mock_db.add.side_effect = capture_add

        await permission_service.create_role(
            name="Team Leader",  # Has space
            display_name="Team Leader"
        )

        # Name should be normalized
        assert added_role.name == "team_leader"
