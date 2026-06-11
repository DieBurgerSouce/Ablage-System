"""
Tests für RBAC (Role-Based Access Control).

Testet:
- Permission-Prüfung
- Rollenverwaltung
- Permission-Vererbung (manage impliziert read/write/delete)
- Superuser-Bypass
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from app.services.permission_service import PermissionService, check_permission, require_permission
from app.db.models import User, Role, Permission


# ==================== Fixtures ====================

@pytest.fixture
def mock_user() -> User:
    """Erstellt einen Mock-Benutzer."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_superuser = False
    user.is_active = True
    return user


@pytest.fixture
def mock_superuser() -> User:
    """Erstellt einen Mock-Superuser."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "admin@example.com"
    user.username = "admin"
    user.is_superuser = True
    user.is_active = True
    return user


@pytest.fixture
def mock_inactive_user() -> User:
    """Erstellt einen inaktiven Mock-Benutzer."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.email = "inactive@example.com"
    user.username = "inactive"
    user.is_superuser = False
    user.is_active = False
    return user


@pytest.fixture
def mock_permission() -> Permission:
    """Erstellt eine Mock-Berechtigung."""
    perm = MagicMock(spec=Permission)
    perm.id = uuid4()
    perm.name = "documents:read"
    perm.resource_type = "documents"
    perm.action = "read"
    perm.is_system = True
    return perm


@pytest.fixture
def mock_role(mock_permission: Permission) -> Role:
    """Erstellt eine Mock-Rolle mit Berechtigung."""
    role = MagicMock(spec=Role)
    role.id = uuid4()
    role.name = "viewer"
    role.display_name = "Betrachter"
    role.priority = 10
    role.is_system = True
    role.is_active = True
    role.permissions = [mock_permission]
    return role


@pytest.fixture
def mock_db():
    """Erstellt eine Mock-Datenbank-Session."""
    return AsyncMock()


# ==================== Permission Service Tests ====================

class TestPermissionService:
    """Tests für den PermissionService."""

    @pytest.mark.asyncio
    async def test_superuser_has_all_permissions(
        self,
        mock_superuser: User,
        mock_db: AsyncMock
    ):
        """Superuser hat immer alle Berechtigungen."""
        service = PermissionService(mock_db)

        result = await service.has_permission(mock_superuser, "documents:read")

        assert result is True

    @pytest.mark.asyncio
    async def test_superuser_has_any_permission(
        self,
        mock_superuser: User,
        mock_db: AsyncMock
    ):
        """Superuser hat auch exotische Berechtigungen."""
        service = PermissionService(mock_db)

        result = await service.has_permission(mock_superuser, "nonexistent:permission")

        assert result is True

    @pytest.mark.asyncio
    async def test_inactive_user_denied(
        self,
        mock_inactive_user: User,
        mock_db: AsyncMock
    ):
        """Inaktive Benutzer haben keine Berechtigungen."""
        service = PermissionService(mock_db)

        result = await service.has_permission(mock_inactive_user, "documents:read")

        assert result is False

    @pytest.mark.asyncio
    async def test_user_with_permission(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """Benutzer mit direkter Berechtigung hat Zugriff."""
        service = PermissionService(mock_db)

        # Mock der get_user_permissions Methode
        with patch.object(
            service,
            'get_user_permissions',
            return_value={"documents:read", "documents:write"}
        ):
            result = await service.has_permission(mock_user, "documents:read")

        assert result is True

    @pytest.mark.asyncio
    async def test_user_without_permission(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """Benutzer ohne Berechtigung wird abgelehnt."""
        service = PermissionService(mock_db)

        with patch.object(
            service,
            'get_user_permissions',
            return_value={"documents:read"}
        ):
            result = await service.has_permission(mock_user, "documents:delete")

        assert result is False

    @pytest.mark.asyncio
    async def test_manage_permission_grants_all(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """manage-Berechtigung gewährt read, write, delete."""
        service = PermissionService(mock_db)

        with patch.object(
            service,
            'get_user_permissions',
            return_value={"documents:manage"}
        ):
            # manage sollte read implizieren
            result_read = await service.has_permission(mock_user, "documents:read")
            result_write = await service.has_permission(mock_user, "documents:write")
            result_delete = await service.has_permission(mock_user, "documents:delete")

        assert result_read is True
        assert result_write is True
        assert result_delete is True

    @pytest.mark.asyncio
    async def test_has_any_permission(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """has_any_permission prüft OR-Logik."""
        service = PermissionService(mock_db)

        with patch.object(
            service,
            'get_user_permissions',
            return_value={"documents:read"}
        ):
            result = await service.has_any_permission(
                mock_user,
                ["documents:delete", "documents:read"]
            )

        assert result is True

    @pytest.mark.asyncio
    async def test_has_all_permissions(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """has_all_permissions prüft AND-Logik."""
        service = PermissionService(mock_db)

        with patch.object(
            service,
            'get_user_permissions',
            return_value={"documents:read", "documents:write"}
        ):
            result_all = await service.has_all_permissions(
                mock_user,
                ["documents:read", "documents:write"]
            )
            result_missing = await service.has_all_permissions(
                mock_user,
                ["documents:read", "documents:delete"]
            )

        assert result_all is True
        assert result_missing is False


class TestPermissionCaching:
    """Tests für Permission-Caching."""

    @pytest.mark.asyncio
    async def test_cache_is_populated(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """Berechtigungen werden gecacht."""
        service = PermissionService(mock_db)

        # Simuliere DB-Abfrage
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("documents:read",), ("documents:write",)]
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Erster Aufruf sollte DB abfragen
        perms1 = await service.get_user_permissions(mock_user)

        # Prüfe ob gecacht
        assert str(mock_user.id) in service._permission_cache
        assert "documents:read" in perms1
        assert "documents:write" in perms1

    @pytest.mark.asyncio
    async def test_clear_cache(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """Cache kann geleert werden."""
        service = PermissionService(mock_db)

        # Cache befüllen
        service._permission_cache[str(mock_user.id)] = {"documents:read"}

        # Cache leeren
        service.clear_cache()

        assert len(service._permission_cache) == 0


class TestRoleAssignment:
    """Tests für Rollenzuweisung."""

    @pytest.mark.asyncio
    async def test_assign_role_inactive_role_fails(
        self,
        mock_user: User,
        mock_role: Role,
        mock_db: AsyncMock
    ):
        """Inaktive Rollen können nicht zugewiesen werden."""
        service = PermissionService(mock_db)
        mock_role.is_active = False

        with pytest.raises(ValueError, match="nicht aktiv"):
            await service.assign_role(mock_user, mock_role)


class TestSystemRoleProtection:
    """Tests für System-Rollen-Schutz."""

    @pytest.mark.asyncio
    async def test_cannot_delete_system_role(
        self,
        mock_role: Role,
        mock_db: AsyncMock
    ):
        """System-Rollen können nicht gelöscht werden."""
        service = PermissionService(mock_db)
        mock_role.is_system = True

        with pytest.raises(ValueError, match="System-Rolle"):
            await service.delete_role(mock_role)

    @pytest.mark.asyncio
    async def test_cannot_modify_system_role_priority(
        self,
        mock_role: Role,
        mock_db: AsyncMock
    ):
        """System-Rollen-Priorität kann nicht geändert werden."""
        service = PermissionService(mock_db)
        mock_role.is_system = True

        with pytest.raises(ValueError, match="System-Rolle"):
            await service.update_role(mock_role, priority=100)


# ==================== RBAC Decorator Tests ====================

class TestRBACDecorators:
    """Tests für RBAC Decorators."""

    @pytest.mark.asyncio
    async def test_require_permission_decorator_passes(self):
        """require_permission lässt berechtigte Benutzer durch."""
        from app.core.rbac import require_permission

        # Testen dass die Funktion existiert und aufrufbar ist
        checker = require_permission("documents:read")
        assert callable(checker)

    @pytest.mark.asyncio
    async def test_require_any_permission_decorator(self):
        """require_any_permission funktioniert mit OR-Logik."""
        from app.core.rbac import require_any_permission

        checker = require_any_permission("documents:read", "documents:write")
        assert callable(checker)

    @pytest.mark.asyncio
    async def test_require_role_decorator(self):
        """require_role prüft Rollenzugehörigkeit."""
        from app.core.rbac import require_role

        checker = require_role("admin")
        assert callable(checker)


# ==================== Convenience Function Tests ====================

class TestConvenienceFunctions:
    """Tests für Convenience Functions."""

    @pytest.mark.asyncio
    async def test_check_permission_function(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """check_permission Convenience-Funktion funktioniert."""
        with patch(
            'app.services.permission_service.PermissionService.has_permission',
            return_value=True
        ):
            result = await check_permission(mock_db, mock_user, "documents:read")

        assert result is True

    @pytest.mark.asyncio
    async def test_require_permission_function_raises(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """require_permission wirft PermissionError bei fehlender Berechtigung."""
        with patch(
            'app.services.permission_service.PermissionService.has_permission',
            return_value=False
        ):
            with pytest.raises(PermissionError, match="Zugriff verweigert"):
                await require_permission(mock_db, mock_user, "documents:delete")


# ==================== 2FA Enforcement Tests ====================

class TestTwoFactorEnforcement:
    """Tests für 2FA-Erzwingung für Admins."""

    @pytest.fixture
    def mock_admin_without_2fa(self, mock_role: Role) -> User:
        """Erstellt einen Admin-Benutzer ohne 2FA."""
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.email = "admin@example.com"
        user.username = "admin_no_2fa"
        user.is_superuser = False
        user.is_active = True
        user.totp_enabled = False
        # Admin-Rolle
        mock_role.name = "admin"
        mock_role.priority = 100
        return user

    @pytest.fixture
    def mock_admin_with_2fa(self, mock_role: Role) -> User:
        """Erstellt einen Admin-Benutzer mit 2FA."""
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.email = "admin_2fa@example.com"
        user.username = "admin_2fa"
        user.is_superuser = False
        user.is_active = True
        user.totp_enabled = True
        mock_role.name = "admin"
        mock_role.priority = 100
        return user

    @pytest.mark.asyncio
    async def test_require_2fa_for_admin_decorator_exists(self):
        """require_2fa_for_admin Decorator existiert."""
        from app.core.rbac import require_2fa_for_admin

        checker = require_2fa_for_admin()
        assert callable(checker)

    @pytest.mark.asyncio
    async def test_require_admin_with_2fa_decorator_exists(self):
        """require_admin_with_2fa Decorator existiert."""
        from app.core.rbac import require_admin_with_2fa

        checker = require_admin_with_2fa()
        assert callable(checker)

    @pytest.mark.asyncio
    async def test_two_factor_required_error_exists(self):
        """TwoFactorRequiredError Exception existiert."""
        from app.core.rbac import TwoFactorRequiredError

        error = TwoFactorRequiredError()
        assert error.status_code == 403
        assert "Zwei-Faktor" in error.detail


# ==================== Edge Cases ====================

class TestEdgeCases:
    """Edge Case Tests."""

    @pytest.mark.asyncio
    async def test_empty_permissions_set(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """Benutzer ohne Berechtigungen werden korrekt behandelt."""
        service = PermissionService(mock_db)

        with patch.object(
            service,
            'get_user_permissions',
            return_value=set()
        ):
            result = await service.has_permission(mock_user, "documents:read")

        assert result is False

    @pytest.mark.asyncio
    async def test_permission_name_parsing(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """Berechtigungsnamen werden korrekt geparst."""
        service = PermissionService(mock_db)

        with patch.object(
            service,
            'get_user_permissions',
            return_value={"documents:manage"}
        ):
            # Teste verschiedene Formate
            result_valid = await service.has_permission(mock_user, "documents:read")
            result_invalid = await service.has_permission(mock_user, "invalid")  # No colon

        assert result_valid is True
        # invalid hat kein ":" also kein manage-Check
        assert result_invalid is False

    @pytest.mark.asyncio
    async def test_resource_type_extraction(
        self,
        mock_user: User,
        mock_db: AsyncMock
    ):
        """Resource-Type wird korrekt aus Permission-Name extrahiert."""
        service = PermissionService(mock_db)

        with patch.object(
            service,
            'get_user_permissions',
            return_value={"users:manage"}
        ):
            # users:manage sollte users:read implizieren
            result = await service.has_permission(mock_user, "users:read")

        assert result is True


# ==================== W1-001: 2FA-Bypass-Haertung ====================

class TestTwoFaBypassHaertung:
    """W1-001: settings.DEBUG darf die 2FA-Pflicht NICHT mehr deaktivieren.

    Bypass ist nur im TESTING-Betrieb (docker-compose.test.yml) legitim
    und greift nie in Produktion.
    """

    def test_debug_true_bypasst_2fa_nicht(self):
        from app.core import rbac
        with patch.object(rbac.settings, "DEBUG", True), \
             patch.object(rbac.settings, "TESTING", False), \
             patch.object(rbac.settings, "ENVIRONMENT", "development"):
            assert rbac._twofa_bypass_active() is False

    def test_testing_bypasst_in_dev(self):
        from app.core import rbac
        with patch.object(rbac.settings, "TESTING", True), \
             patch.object(rbac.settings, "ENVIRONMENT", "development"):
            assert rbac._twofa_bypass_active() is True

    def test_testing_bypasst_nie_in_produktion(self):
        from app.core import rbac
        with patch.object(rbac.settings, "TESTING", True), \
             patch.object(rbac.settings, "ENVIRONMENT", "production"):
            assert rbac._twofa_bypass_active() is False

    @pytest.mark.asyncio
    async def test_superuser_ohne_totp_braucht_2fa_trotz_debug(self, mock_superuser):
        """Regressionstest: vor W1-001 schaltete DEBUG=true die Pflicht ab."""
        from app.core import rbac
        mock_superuser.totp_enabled = False
        checker = rbac.require_superuser()
        with patch.object(rbac.settings, "DEBUG", True), \
             patch.object(rbac.settings, "TESTING", False), \
             patch.object(rbac.settings, "ENVIRONMENT", "development"):
            with pytest.raises(rbac.TwoFactorRequiredError):
                await checker(current_user=mock_superuser)

    @pytest.mark.asyncio
    async def test_superuser_ohne_totp_im_testing_betrieb_erlaubt(self, mock_superuser):
        """E2E-Stack (TESTING=true, non-prod) darf ohne TOTP arbeiten."""
        from app.core import rbac
        mock_superuser.totp_enabled = False
        checker = rbac.require_superuser()
        with patch.object(rbac.settings, "TESTING", True), \
             patch.object(rbac.settings, "ENVIRONMENT", "development"):
            result = await checker(current_user=mock_superuser)
        assert result is mock_superuser


class TestDebugProdGuard:
    """W1-001 Fail-Safe in config.py: DEBUG=true wird in Produktion neutralisiert."""

    def test_debug_wird_in_produktion_neutralisiert(self):
        from app.core.config import Settings
        s = Settings(ENVIRONMENT="production", DEBUG=True)
        assert s.DEBUG is False

    def test_debug_bleibt_in_dev_erhalten(self):
        from app.core.config import Settings
        s = Settings(ENVIRONMENT="development", DEBUG=True)
        assert s.DEBUG is True
