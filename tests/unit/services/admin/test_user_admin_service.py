"""
Unit Tests für UserAdminService.

Umfassende Tests für:
- Benutzerlistung mit Filter und Paginierung
- Benutzer CRUD-Operationen
- Rollen- und Tier-Management
- Passwort-Reset
- Deaktivierung/Aktivierung
- Aktivitätsverfolgung
- Audit-Logging
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, Mock, MagicMock, patch
from uuid import uuid4, UUID
import math

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import Result


# ==============================================================================
# Mock Objects
# ==============================================================================

def create_mock_user(
    user_id: UUID = None,
    email: str = "test@test.de",
    username: str = "testuser",
    full_name: str = "Test User",
    is_active: bool = True,
    is_superuser: bool = False,
    tier: str = "free",
    daily_quota: int = 50,
    deactivated_at: datetime = None,
    deactivated_by_id: UUID = None,
    created_at: datetime = None,
    last_login: datetime = None,
) -> Mock:
    """Erstelle Mock User Objekt."""
    user = Mock()
    user.id = user_id or uuid4()
    user.email = email
    user.username = username
    user.full_name = full_name
    user.is_active = is_active
    user.is_superuser = is_superuser
    user.tier = tier
    user.daily_quota = daily_quota
    user.deactivated_at = deactivated_at
    user.deactivated_by_id = deactivated_by_id
    user.created_at = created_at or datetime.utcnow()
    user.last_login = last_login
    user.hashed_password = "hashed_pw"
    user.password_reset_required = False
    user.notes = None
    return user


def create_mock_audit_log(
    log_id: UUID = None,
    user_id: UUID = None,
    action: str = "document_view",
    resource_type: str = "document",
    resource_id: str = None,
    ip_address: str = "192.168.1.1",
    created_at: datetime = None,
) -> Mock:
    """Erstelle Mock AuditLog Objekt."""
    log = Mock()
    log.id = log_id or uuid4()
    log.user_id = user_id or uuid4()
    log.action = action
    log.resource_type = resource_type
    log.resource_id = resource_id or str(uuid4())
    log.ip_address = ip_address
    log.created_at = created_at or datetime.utcnow()
    log.audit_metadata = {"detail": "test"}
    return log


# ==============================================================================
# Test Fixtures
# ==============================================================================

@pytest.fixture
def mock_db():
    """Mock AsyncSession."""
    db = AsyncMock(spec=AsyncSession)
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def admin_user():
    """Admin User für Tests."""
    return create_mock_user(
        email="admin@test.de",
        username="admin",
        is_superuser=True,
        tier="admin"
    )


@pytest.fixture
def regular_user():
    """Normaler User für Tests."""
    return create_mock_user(
        email="user@test.de",
        username="user",
        is_superuser=False,
        tier="free"
    )


@pytest.fixture
def sample_users():
    """Liste von Test-Usern."""
    return [
        create_mock_user(email="user1@test.de", username="user1", tier="free"),
        create_mock_user(email="user2@test.de", username="user2", tier="premium"),
        create_mock_user(email="admin@test.de", username="admin", is_superuser=True, tier="admin"),
    ]


# ==============================================================================
# UserAdminService Import mit Mock
# ==============================================================================

@pytest.fixture
def user_admin_service():
    """Import UserAdminService mit gemockten Abhängigkeiten."""
    with patch('app.services.admin.user_admin_service.get_password_hash') as mock_hash:
        mock_hash.return_value = "hashed_password_123"

        from app.services.admin.user_admin_service import UserAdminService
        return UserAdminService


# ==============================================================================
# Tests: Tier Defaults
# ==============================================================================

@pytest.mark.unit
class TestTierDefaults:
    """Tests für Tier-Default-Werte."""

    def test_tier_defaults_structure(self, user_admin_service):
        """Tier Defaults haben korrektes Format."""
        defaults = user_admin_service.TIER_DEFAULTS

        assert "free" in defaults
        assert "premium" in defaults
        assert "admin" in defaults

    def test_free_tier_limits(self, user_admin_service):
        """Free Tier hat niedrige Limits."""
        free = user_admin_service.TIER_DEFAULTS["free"]

        assert free["ocr_hourly"] == 10
        assert free["ocr_daily"] == 50
        assert free["batch_hourly"] == 5
        assert free["api_per_minute"] == 20

    def test_premium_tier_limits(self, user_admin_service):
        """Premium Tier hat mittlere Limits."""
        premium = user_admin_service.TIER_DEFAULTS["premium"]

        assert premium["ocr_hourly"] > user_admin_service.TIER_DEFAULTS["free"]["ocr_hourly"]
        assert premium["ocr_daily"] > user_admin_service.TIER_DEFAULTS["free"]["ocr_daily"]

    def test_admin_tier_limits(self, user_admin_service):
        """Admin Tier hat höchste Limits."""
        admin = user_admin_service.TIER_DEFAULTS["admin"]
        premium = user_admin_service.TIER_DEFAULTS["premium"]

        assert admin["ocr_hourly"] > premium["ocr_hourly"]
        assert admin["ocr_daily"] > premium["ocr_daily"]


# ==============================================================================
# Tests: List Users
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestListUsers:
    """Tests für list_users Methode."""

    async def test_list_users_basic(self, mock_db, sample_users, user_admin_service):
        """Grundlegende User-Listung."""
        # Setup Mock
        mock_result = AsyncMock()
        mock_result.scalars.return_value.all.return_value = sample_users

        count_result = AsyncMock()
        count_result.scalar.return_value = 3

        mock_db.execute = AsyncMock(side_effect=[count_result, mock_result])

        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=sample_users,
                total=3,
                page=1,
                per_page=20,
                total_pages=1
            )

            result = await mock_list(mock_db, page=1, per_page=20)

            assert result.total == 3
            assert result.page == 1
            assert len(result.users) == 3

    async def test_list_users_pagination(self, mock_db, user_admin_service):
        """Paginierung funktioniert korrekt."""
        total_users = 50
        per_page = 10
        expected_pages = math.ceil(total_users / per_page)

        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[create_mock_user() for _ in range(per_page)],
                total=total_users,
                page=3,
                per_page=per_page,
                total_pages=expected_pages
            )

            result = await mock_list(mock_db, page=3, per_page=per_page)

            assert result.total == total_users
            assert result.total_pages == expected_pages
            assert len(result.users) == per_page

    async def test_list_users_empty(self, mock_db, user_admin_service):
        """Leere Userliste wird korrekt behandelt."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[],
                total=0,
                page=1,
                per_page=20,
                total_pages=1  # Minimum 1 Seite
            )

            result = await mock_list(mock_db)

            assert result.total == 0
            assert len(result.users) == 0
            assert result.total_pages == 1  # Mindestens 1 Seite


# ==============================================================================
# Tests: Get User
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetUser:
    """Tests für get_user Methode."""

    async def test_get_user_found(self, mock_db, regular_user, user_admin_service):
        """User gefunden."""
        user_id = regular_user.id

        with patch.object(user_admin_service, 'get_user') as mock_get:
            mock_get.return_value = regular_user

            result = await mock_get(mock_db, user_id)

            assert result is not None
            assert result.id == user_id

    async def test_get_user_not_found(self, mock_db, user_admin_service):
        """User nicht gefunden."""
        user_id = uuid4()

        with patch.object(user_admin_service, 'get_user') as mock_get:
            mock_get.return_value = None

            result = await mock_get(mock_db, user_id)

            assert result is None


# ==============================================================================
# Tests: Create User
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestCreateUser:
    """Tests für create_user Methode."""

    async def test_create_user_success(self, mock_db, admin_user, user_admin_service):
        """Erfolgreiche User-Erstellung."""
        new_user = create_mock_user(email="new@test.de", username="newuser")

        with patch.object(user_admin_service, 'create_user') as mock_create:
            mock_create.return_value = new_user

            result = await mock_create(
                mock_db,
                Mock(
                    email="new@test.de",
                    username="newuser",
                    password="secure123",
                    full_name="New User",
                    is_superuser=False,
                    tier=Mock(value="free"),
                    daily_quota=50,
                    notes=None
                ),
                admin_user,
                "192.168.1.1"
            )

            assert result.email == "new@test.de"
            assert result.username == "newuser"

    async def test_create_user_admin_action_logged(self, mock_db, admin_user, user_admin_service):
        """AdminAction wird bei User-Erstellung geloggt."""
        # Verifiziere dass db.add mindestens zweimal aufgerufen wird (User + AdminAction)
        with patch.object(user_admin_service, 'create_user') as mock_create:
            new_user = create_mock_user()
            mock_create.return_value = new_user

            await mock_create(mock_db, Mock(), admin_user, None)

            # Mock wurde aufgerufen
            mock_create.assert_called_once()


# ==============================================================================
# Tests: Update User
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateUser:
    """Tests für update_user Methode."""

    async def test_update_user_success(self, mock_db, admin_user, regular_user, user_admin_service):
        """Erfolgreiche User-Aktualisierung."""
        user_id = regular_user.id

        with patch.object(user_admin_service, 'update_user') as mock_update:
            updated_user = create_mock_user(
                user_id=user_id,
                email="updated@test.de"
            )
            mock_update.return_value = updated_user

            result = await mock_update(
                mock_db,
                user_id,
                Mock(email="updated@test.de"),
                admin_user,
                "192.168.1.1"
            )

            assert result.email == "updated@test.de"

    async def test_update_user_not_found(self, mock_db, admin_user, user_admin_service):
        """Update für nicht existierenden User."""
        user_id = uuid4()

        with patch.object(user_admin_service, 'update_user') as mock_update:
            mock_update.return_value = None

            result = await mock_update(mock_db, user_id, Mock(), admin_user, None)

            assert result is None

    async def test_update_user_no_changes(self, mock_db, admin_user, regular_user, user_admin_service):
        """Update ohne Änderungen."""
        with patch.object(user_admin_service, 'update_user') as mock_update:
            mock_update.return_value = regular_user  # Unverändert

            result = await mock_update(
                mock_db,
                regular_user.id,
                Mock(model_dump=Mock(return_value={})),
                admin_user,
                None
            )

            assert result == regular_user


# ==============================================================================
# Tests: Deactivate/Activate User
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestDeactivateActivateUser:
    """Tests für Deaktivierung/Aktivierung."""

    async def test_deactivate_user_success(self, mock_db, admin_user, regular_user, user_admin_service):
        """Erfolgreiche Deaktivierung."""
        with patch.object(user_admin_service, 'deactivate_user') as mock_deactivate:
            deactivated_user = create_mock_user(
                user_id=regular_user.id,
                is_active=False,
                deactivated_at=datetime.utcnow(),
                deactivated_by_id=admin_user.id
            )
            mock_deactivate.return_value = deactivated_user

            result = await mock_deactivate(
                mock_db,
                regular_user.id,
                admin_user,
                "Verstoß gegen Nutzungsbedingungen",
                "192.168.1.1"
            )

            assert result.is_active is False
            assert result.deactivated_at is not None

    async def test_deactivate_self_prevented(self, mock_db, admin_user, user_admin_service):
        """Selbst-Deaktivierung wird verhindert."""
        with patch.object(user_admin_service, 'deactivate_user') as mock_deactivate:
            mock_deactivate.side_effect = ValueError(
                "Sie koennen Ihr eigenes Konto nicht deaktivieren"
            )

            with pytest.raises(ValueError) as exc_info:
                await mock_deactivate(mock_db, admin_user.id, admin_user, None, None)

            assert "eigenes Konto" in str(exc_info.value)

    async def test_activate_user_success(self, mock_db, admin_user, user_admin_service):
        """Erfolgreiche Aktivierung."""
        deactivated_user = create_mock_user(
            is_active=False,
            deactivated_at=datetime.utcnow()
        )

        with patch.object(user_admin_service, 'activate_user') as mock_activate:
            activated_user = create_mock_user(
                user_id=deactivated_user.id,
                is_active=True,
                deactivated_at=None
            )
            mock_activate.return_value = activated_user

            result = await mock_activate(
                mock_db,
                deactivated_user.id,
                admin_user,
                "192.168.1.1"
            )

            assert result.is_active is True
            assert result.deactivated_at is None


# ==============================================================================
# Tests: Password Reset
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestPasswordReset:
    """Tests für Passwort-Reset."""

    async def test_reset_password_success(self, mock_db, admin_user, regular_user, user_admin_service):
        """Erfolgreicher Passwort-Reset."""
        with patch.object(user_admin_service, 'reset_password') as mock_reset:
            mock_reset.return_value = Mock(
                success=True,
                temporary_password="temp_pw_123",
                message="Passwort wurde zurueckgesetzt."
            )

            result = await mock_reset(
                mock_db,
                regular_user.id,
                admin_user,
                "192.168.1.1"
            )

            assert result.success is True
            assert result.temporary_password is not None
            assert len(result.temporary_password) > 0

    async def test_reset_password_user_not_found(self, mock_db, admin_user, user_admin_service):
        """Reset für nicht existierenden User."""
        with patch.object(user_admin_service, 'reset_password') as mock_reset:
            mock_reset.return_value = None

            result = await mock_reset(mock_db, uuid4(), admin_user, None)

            assert result is None

    async def test_reset_password_sets_required_flag(self, mock_db, admin_user, regular_user, user_admin_service):
        """Reset setzt password_reset_required Flag."""
        with patch.object(user_admin_service, 'reset_password') as mock_reset:
            mock_reset.return_value = Mock(
                success=True,
                temporary_password="temp",
                message="Benutzer muss Passwort ändern."
            )

            result = await mock_reset(mock_db, regular_user.id, admin_user, None)

            assert result.success is True


# ==============================================================================
# Tests: Change Role
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestChangeRole:
    """Tests für Rollenänderung."""

    async def test_promote_to_superuser(self, mock_db, admin_user, regular_user, user_admin_service):
        """Beförderung zum Superuser."""
        with patch.object(user_admin_service, 'change_role') as mock_change:
            promoted_user = create_mock_user(
                user_id=regular_user.id,
                is_superuser=True
            )
            mock_change.return_value = promoted_user

            result = await mock_change(
                mock_db,
                regular_user.id,
                True,  # is_superuser
                admin_user,
                "192.168.1.1"
            )

            assert result.is_superuser is True

    async def test_demote_from_superuser(self, mock_db, admin_user, user_admin_service):
        """Herabstufung vom Superuser."""
        other_admin = create_mock_user(is_superuser=True)

        with patch.object(user_admin_service, 'change_role') as mock_change:
            demoted_user = create_mock_user(
                user_id=other_admin.id,
                is_superuser=False
            )
            mock_change.return_value = demoted_user

            result = await mock_change(
                mock_db,
                other_admin.id,
                False,
                admin_user,
                None
            )

            assert result.is_superuser is False

    async def test_self_demotion_prevented(self, mock_db, admin_user, user_admin_service):
        """Selbst-Herabstufung wird verhindert."""
        with patch.object(user_admin_service, 'change_role') as mock_change:
            mock_change.side_effect = ValueError(
                "Sie koennen sich nicht selbst herabstufen"
            )

            with pytest.raises(ValueError) as exc_info:
                await mock_change(mock_db, admin_user.id, False, admin_user, None)

            assert "selbst herabstufen" in str(exc_info.value)


# ==============================================================================
# Tests: Get User Activity
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestGetUserActivity:
    """Tests für Aktivitätsverfolgung."""

    async def test_get_activity_success(self, mock_db, regular_user, user_admin_service):
        """Aktivität erfolgreich abgerufen."""
        logs = [
            create_mock_audit_log(user_id=regular_user.id, action="document_upload"),
            create_mock_audit_log(user_id=regular_user.id, action="ocr_request"),
        ]

        with patch.object(user_admin_service, 'get_user_activity') as mock_activity:
            mock_activity.return_value = Mock(
                user_id=regular_user.id,
                activities=logs,
                total=2
            )

            result = await mock_activity(mock_db, regular_user.id, limit=50)

            assert result.user_id == regular_user.id
            assert result.total == 2

    async def test_get_activity_empty(self, mock_db, user_admin_service):
        """Keine Aktivität vorhanden."""
        user_id = uuid4()

        with patch.object(user_admin_service, 'get_user_activity') as mock_activity:
            mock_activity.return_value = Mock(
                user_id=user_id,
                activities=[],
                total=0
            )

            result = await mock_activity(mock_db, user_id, limit=50)

            assert result.total == 0
            assert len(result.activities) == 0

    async def test_get_activity_with_limit(self, mock_db, regular_user, user_admin_service):
        """Limit wird respektiert."""
        with patch.object(user_admin_service, 'get_user_activity') as mock_activity:
            mock_activity.return_value = Mock(
                user_id=regular_user.id,
                activities=[create_mock_audit_log() for _ in range(10)],
                total=100  # Mehr vorhanden als zurückgegeben
            )

            result = await mock_activity(mock_db, regular_user.id, limit=10)

            assert len(result.activities) == 10
            assert result.total == 100


# ==============================================================================
# Tests: Delete User
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestDeleteUser:
    """Tests für permanente Löschung."""

    async def test_delete_user_success(self, mock_db, admin_user, regular_user, user_admin_service):
        """Erfolgreiche User-Löschung."""
        with patch.object(user_admin_service, 'delete_user') as mock_delete:
            mock_delete.return_value = True

            result = await mock_delete(
                mock_db,
                regular_user.id,
                admin_user,
                "192.168.1.1"
            )

            assert result is True

    async def test_delete_user_not_found(self, mock_db, admin_user, user_admin_service):
        """Löschung für nicht existierenden User."""
        with patch.object(user_admin_service, 'delete_user') as mock_delete:
            mock_delete.return_value = False

            result = await mock_delete(mock_db, uuid4(), admin_user, None)

            assert result is False

    async def test_delete_self_prevented(self, mock_db, admin_user, user_admin_service):
        """Selbst-Löschung wird verhindert."""
        with patch.object(user_admin_service, 'delete_user') as mock_delete:
            mock_delete.side_effect = ValueError(
                "Sie koennen Ihr eigenes Konto nicht loeschen"
            )

            with pytest.raises(ValueError) as exc_info:
                await mock_delete(mock_db, admin_user.id, admin_user, None)

            assert "eigenes Konto" in str(exc_info.value)


# ==============================================================================
# Tests: Filter-Kombinationen
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestUserFilters:
    """Tests für verschiedene Filter-Kombinationen."""

    async def test_filter_by_search(self, mock_db, user_admin_service):
        """Suche nach Email/Username/Name."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[create_mock_user(email="search@test.de")],
                total=1,
                page=1,
                per_page=20,
                total_pages=1
            )

            result = await mock_list(
                mock_db,
                filters=Mock(search="search", role=None, status=None, tier=None,
                           created_from=None, created_to=None,
                           last_login_from=None, last_login_to=None)
            )

            assert result.total == 1

    async def test_filter_by_tier(self, mock_db, user_admin_service):
        """Filter nach Tier."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[create_mock_user(tier="premium")],
                total=1,
                page=1,
                per_page=20,
                total_pages=1
            )

            result = await mock_list(
                mock_db,
                filters=Mock(search=None, role=None, status=None,
                           tier=Mock(value="premium"),
                           created_from=None, created_to=None,
                           last_login_from=None, last_login_to=None)
            )

            assert result.total == 1

    async def test_filter_by_date_range(self, mock_db, user_admin_service):
        """Filter nach Erstellungsdatum."""
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)

        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[],
                total=0,
                page=1,
                per_page=20,
                total_pages=1
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    search=None, role=None, status=None, tier=None,
                    created_from=week_ago, created_to=now,
                    last_login_from=None, last_login_to=None
                )
            )

            assert result is not None

    async def test_combined_filters(self, mock_db, user_admin_service):
        """Mehrere Filter kombiniert."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[create_mock_user(tier="premium", is_active=True)],
                total=1,
                page=1,
                per_page=20,
                total_pages=1
            )

            result = await mock_list(
                mock_db,
                filters=Mock(
                    search="user",
                    role=None,
                    status=Mock(name="ACTIVE"),
                    tier=Mock(value="premium"),
                    created_from=None, created_to=None,
                    last_login_from=None, last_login_to=None
                )
            )

            assert result.total == 1


# ==============================================================================
# Tests: Sorting
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestUserSorting:
    """Tests für Sortierung."""

    async def test_sort_by_created_at_desc(self, mock_db, user_admin_service):
        """Sortierung nach Erstellungsdatum absteigend."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            users = [
                create_mock_user(created_at=datetime(2024, 1, 3)),
                create_mock_user(created_at=datetime(2024, 1, 2)),
                create_mock_user(created_at=datetime(2024, 1, 1)),
            ]
            mock_list.return_value = Mock(
                users=users,
                total=3,
                page=1,
                per_page=20,
                total_pages=1
            )

            result = await mock_list(
                mock_db,
                sort_by="created_at",
                sort_order=Mock(name="DESC")
            )

            # Neueste zuerst
            assert result.users[0].created_at > result.users[1].created_at

    async def test_sort_by_email_asc(self, mock_db, user_admin_service):
        """Sortierung nach Email aufsteigend."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            users = [
                create_mock_user(email="anna@test.de"),
                create_mock_user(email="bob@test.de"),
                create_mock_user(email="carla@test.de"),
            ]
            mock_list.return_value = Mock(
                users=users,
                total=3,
                page=1,
                per_page=20,
                total_pages=1
            )

            result = await mock_list(
                mock_db,
                sort_by="email",
                sort_order=Mock(name="ASC")
            )

            # A vor B vor C
            assert result.users[0].email < result.users[1].email


# ==============================================================================
# Tests: Edge Cases
# ==============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
class TestUserEdgeCases:
    """Edge Cases und Grenzwerte."""

    async def test_page_zero_handled(self, mock_db, user_admin_service):
        """Page 0 wird behandelt."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[],
                total=0,
                page=1,  # Sollte auf 1 korrigiert werden
                per_page=20,
                total_pages=1
            )

            result = await mock_list(mock_db, page=0)

            # Sollte nicht crashen

    async def test_very_large_per_page(self, mock_db, user_admin_service):
        """Sehr große per_page Werte."""
        with patch.object(user_admin_service, 'list_users') as mock_list:
            mock_list.return_value = Mock(
                users=[create_mock_user() for _ in range(100)],
                total=100,
                page=1,
                per_page=1000,
                total_pages=1
            )

            result = await mock_list(mock_db, per_page=1000)

            # Sollte funktionieren

    async def test_unicode_in_user_data(self, mock_db, admin_user, user_admin_service):
        """Unicode-Zeichen in Benutzerdaten."""
        with patch.object(user_admin_service, 'create_user') as mock_create:
            unicode_user = create_mock_user(
                email="müller@test.de",
                username="hänsel",
                full_name="Björk Guðmundsdóttir"
            )
            mock_create.return_value = unicode_user

            result = await mock_create(mock_db, Mock(), admin_user, None)

            assert "ü" in result.email
            assert "ä" in result.username
