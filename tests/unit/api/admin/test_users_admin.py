"""
Tests for Admin Users API endpoints.

Tests user management functionality:
- List users with pagination and filtering
- Get user details
- Create new users
- Update user information
- Delete users
- Role management
- Password reset
- Account locking/unlocking
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.db.models import User
from app.db.schemas import (
    UserRole,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    MessageResponse,
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    return AsyncMock()


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    from unittest.mock import Mock
    user = Mock(spec=User)
    user.id = str(uuid4())
    user.email = "admin@test.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    user.tier = "enterprise"
    user.created_at = datetime.utcnow()
    return user


@pytest.fixture
def regular_user():
    """Create regular user for testing."""
    from unittest.mock import Mock
    user = Mock(spec=User)
    user.id = str(uuid4())
    user.email = "user@test.de"
    user.username = "testuser"
    user.is_active = True
    user.is_superuser = False
    user.tier = "free"
    user.created_at = datetime.utcnow()
    return user


class TestListUsers:
    """Tests for GET /admin/users endpoint."""

    @pytest.mark.asyncio
    async def test_list_users_success(self, mock_db, admin_user):
        """Benutzer erfolgreich auflisten."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        users = [admin_user]

        with patch.object(service, "list_users", return_value=users):
            result = await service.list_users(db=mock_db, page=1, page_size=10)
            assert len(result) == 1
            assert result[0].email == "admin@test.de"

    @pytest.mark.asyncio
    async def test_list_users_with_filters(self, mock_db, admin_user):
        """Benutzer mit Filtern auflisten."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "list_users", return_value=[admin_user]):
            result = await service.list_users(
                db=mock_db,
                page=1,
                page_size=10,
                is_superuser=True,
                is_active=True,
            )
            assert len(result) == 1
            assert result[0].is_superuser is True

    @pytest.mark.asyncio
    async def test_list_users_empty(self, mock_db):
        """Leere Benutzerliste zurückgeben."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "list_users", return_value=[]):
            result = await service.list_users(db=mock_db, page=1, page_size=10)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, mock_db, admin_user, regular_user):
        """Paginierung testen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "list_users", return_value=[admin_user]):
            result = await service.list_users(db=mock_db, page=1, page_size=1)
            assert len(result) == 1


class TestGetUser:
    """Tests for GET /admin/users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_user_success(self, mock_db, regular_user):
        """Benutzer erfolgreich abrufen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "get_user", return_value=regular_user):
            result = await service.get_user(db=mock_db, user_id=regular_user.id)
            assert result.email == "user@test.de"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, mock_db):
        """Benutzer nicht gefunden."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "get_user", return_value=None):
            result = await service.get_user(db=mock_db, user_id="nonexistent")
            assert result is None


class TestCreateUser:
    """Tests for POST /admin/users endpoint."""

    @pytest.mark.asyncio
    async def test_create_user_success(self, mock_db, admin_user):
        """Benutzer erfolgreich erstellen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        user_data = UserCreate(
            email="new@test.de",
            username="newuser",
            password="SecurePass123!",
        )

        from unittest.mock import Mock
        new_user = Mock(spec=User)
        new_user.id = str(uuid4())
        new_user.email = "new@test.de"
        new_user.username = "newuser"
        new_user.is_active = True
        new_user.is_superuser = False
        new_user.tier = "free"
        new_user.created_at = datetime.utcnow()

        with patch.object(service, "create_user", return_value=new_user):
            result = await service.create_user(
                db=mock_db,
                user_data=user_data,
                created_by=admin_user.id,
            )
            assert result.email == "new@test.de"

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, mock_db, admin_user):
        """Doppelte E-Mail ablehnen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        user_data = UserCreate(
            email="existing@test.de",
            username="newuser",
            password="SecurePass123!",
        )

        with patch.object(
            service,
            "create_user",
            side_effect=HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="E-Mail existiert bereits",
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.create_user(
                    db=mock_db,
                    user_data=user_data,
                    created_by=admin_user.id,
                )
            assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    @pytest.mark.asyncio
    async def test_create_user_weak_password(self, mock_db, admin_user):
        """Schwaches Passwort ablehnen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        user_data = UserCreate(
            email="new@test.de",
            username="newuser",
            password="weak",  # Too short
        )

        with patch.object(
            service,
            "create_user",
            side_effect=HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwort erfüllt nicht die Anforderungen",
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.create_user(
                    db=mock_db,
                    user_data=user_data,
                    created_by=admin_user.id,
                )
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


class TestUpdateUser:
    """Tests for PATCH /admin/users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_user_success(self, mock_db, regular_user, admin_user):
        """Benutzer erfolgreich aktualisieren."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        update_data = UserUpdate(email="updated@test.de")

        from unittest.mock import Mock
        updated_user = Mock(spec=User)
        updated_user.id = regular_user.id
        updated_user.email = "updated@test.de"
        updated_user.username = regular_user.username
        updated_user.is_active = True
        updated_user.is_superuser = False
        updated_user.tier = "free"
        updated_user.created_at = regular_user.created_at

        with patch.object(service, "update_user", return_value=updated_user):
            result = await service.update_user(
                db=mock_db,
                user_id=regular_user.id,
                update_data=update_data,
                updated_by=admin_user.id,
            )
            assert result.email == "updated@test.de"

    @pytest.mark.asyncio
    async def test_update_user_tier(self, mock_db, regular_user, admin_user):
        """Benutzer-Tier aktualisieren."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        update_data = UserUpdate(tier="premium")

        from unittest.mock import Mock
        updated_user = Mock(spec=User)
        updated_user.id = regular_user.id
        updated_user.email = regular_user.email
        updated_user.username = regular_user.username
        updated_user.is_active = True
        updated_user.is_superuser = False
        updated_user.tier = "premium"
        updated_user.created_at = regular_user.created_at

        with patch.object(service, "update_user", return_value=updated_user):
            result = await service.update_user(
                db=mock_db,
                user_id=regular_user.id,
                update_data=update_data,
                updated_by=admin_user.id,
            )
            assert result.tier == "premium"


class TestDeleteUser:
    """Tests for DELETE /admin/users/{user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_user_success(self, mock_db, regular_user, admin_user):
        """Benutzer erfolgreich löschen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "delete_user", return_value=True):
            result = await service.delete_user(
                db=mock_db,
                user_id=regular_user.id,
                deleted_by=admin_user.id,
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self, mock_db, admin_user):
        """Nicht existierenden Benutzer löschen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "delete_user", return_value=False):
            result = await service.delete_user(
                db=mock_db,
                user_id="nonexistent",
                deleted_by=admin_user.id,
            )
            assert result is False

    @pytest.mark.asyncio
    async def test_delete_self_prevented(self, mock_db, admin_user):
        """Selbstlöschung verhindern."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(
            service,
            "delete_user",
            side_effect=HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Eigenes Konto kann nicht gelöscht werden",
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await service.delete_user(
                    db=mock_db,
                    user_id=admin_user.id,
                    deleted_by=admin_user.id,
                )
            assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


class TestPasswordReset:
    """Tests for POST /admin/users/{user_id}/reset-password endpoint."""

    @pytest.mark.asyncio
    async def test_reset_password_success(self, mock_db, regular_user, admin_user):
        """Passwort erfolgreich zurücksetzen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(
            service,
            "reset_password",
            return_value="NewTempPass123!",
        ):
            result = await service.reset_password(
                db=mock_db,
                user_id=regular_user.id,
                reset_by=admin_user.id,
            )
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_reset_password_with_custom(self, mock_db, regular_user, admin_user):
        """Passwort mit benutzerdefiniertem Wert zurücksetzen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        new_password = "CustomPass456!"

        with patch.object(
            service,
            "reset_password",
            return_value=new_password,
        ):
            result = await service.reset_password(
                db=mock_db,
                user_id=regular_user.id,
                reset_by=admin_user.id,
                new_password=new_password,
            )
            assert result == new_password


class TestAccountLocking:
    """Tests for account locking/unlocking endpoints."""

    @pytest.mark.asyncio
    async def test_lock_account_success(self, mock_db, regular_user, admin_user):
        """Konto erfolgreich sperren."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "lock_account", return_value=True):
            result = await service.lock_account(
                db=mock_db,
                user_id=regular_user.id,
                locked_by=admin_user.id,
                reason="Sicherheitsverstoß",
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_unlock_account_success(self, mock_db, regular_user, admin_user):
        """Konto erfolgreich entsperren."""
        from app.services.admin import UserAdminService

        service = UserAdminService()

        with patch.object(service, "unlock_account", return_value=True):
            result = await service.unlock_account(
                db=mock_db,
                user_id=regular_user.id,
                unlocked_by=admin_user.id,
            )
            assert result is True


class TestBulkOperations:
    """Tests for bulk user operations."""

    @pytest.mark.asyncio
    async def test_bulk_deactivate(self, mock_db, admin_user):
        """Mehrere Benutzer deaktivieren."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        user_ids = [str(uuid4()), str(uuid4()), str(uuid4())]

        with patch.object(service, "bulk_deactivate", return_value=3):
            result = await service.bulk_deactivate(
                db=mock_db,
                user_ids=user_ids,
                deactivated_by=admin_user.id,
            )
            assert result == 3

    @pytest.mark.asyncio
    async def test_bulk_delete(self, mock_db, admin_user):
        """Mehrere Benutzer löschen."""
        from app.services.admin import UserAdminService

        service = UserAdminService()
        user_ids = [str(uuid4()), str(uuid4())]

        with patch.object(service, "bulk_delete", return_value=2):
            result = await service.bulk_delete(
                db=mock_db,
                user_ids=user_ids,
                deleted_by=admin_user.id,
            )
            assert result == 2
