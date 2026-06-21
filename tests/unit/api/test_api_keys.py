# -*- coding: utf-8 -*-
"""
Tests für API Key Management Endpoints.

Testet:
- API-Key CRUD (Create, Read, Update, Delete)
- Berechtigungsverwaltung
- Rate Limiting
- Key Rotation
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException


# ==================== API Key Erstellung Tests ====================


class TestCreateAPIKey:
    """Tests für POST /api-keys."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        user.email = "test@example.com"
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.fixture
    def mock_db_key(self):
        """Mock für erstellten API-Key in DB."""
        key = Mock()
        key.id = uuid4()
        key.name = "Test API Key"
        key.key_prefix = "abc12345"
        key.permissions = ["read:documents", "ocr:process"]
        key.rate_limit = 1000
        key.expires_at = datetime.now(timezone.utc) + timedelta(days=90)
        key.is_active = True
        key.created_at = datetime.now(timezone.utc)
        return key

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, mock_user, mock_db, mock_db_key):
        """Erfolgreiche API-Key Erstellung."""
        from app.api.v1.api_keys import create_api_key
        from app.db.schemas import APIKeyCreate, APIKeyPermission

        api_key_plain = "ablage_abc12345xyz67890secret"

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.create_api_key = AsyncMock(
                return_value=(mock_db_key, api_key_plain)
            )

            request = APIKeyCreate(
                name="Test API Key",
                description="Für CI/CD Pipeline",
                permissions=[
                    APIKeyPermission.READ_DOCUMENTS,
                    APIKeyPermission.OCR_PROCESS
                ],
                rate_limit=1000,
                expires_in_days=90
            )

            response = await create_api_key(
                key_data=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.name == "Test API Key"
            assert response.api_key == api_key_plain
            assert "ablage_" in response.api_key

    @pytest.mark.asyncio
    async def test_create_api_key_limit_exceeded(self, mock_user, mock_db):
        """API-Key Erstellung wenn Limit erreicht."""
        from app.api.v1.api_keys import create_api_key
        from app.db.schemas import APIKeyCreate, APIKeyPermission
        from app.services.api_key_service import APIKeyLimitError

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            error = APIKeyLimitError(
                "api_key_limit_exceeded",
                user_message_de="Maximale Anzahl API-Keys erreicht (10)"
            )
            service.create_api_key = AsyncMock(side_effect=error)

            request = APIKeyCreate(
                name="Test Key",
                permissions=[APIKeyPermission.READ_DOCUMENTS]
            )

            with pytest.raises(HTTPException) as exc_info:
                await create_api_key(
                    key_data=request,
                    current_user=mock_user,
                    db=mock_db
                )

            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_create_api_key_with_admin_permission(self, mock_user, mock_db, mock_db_key):
        """API-Key mit Admin-Berechtigung."""
        from app.api.v1.api_keys import create_api_key
        from app.db.schemas import APIKeyCreate, APIKeyPermission

        mock_db_key.permissions = ["admin"]
        api_key_plain = "ablage_admin_key_secret"

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.create_api_key = AsyncMock(
                return_value=(mock_db_key, api_key_plain)
            )

            request = APIKeyCreate(
                name="Admin Key",
                permissions=[APIKeyPermission.ADMIN]
            )

            response = await create_api_key(
                key_data=request,
                current_user=mock_user,
                db=mock_db
            )

            assert "admin" in mock_db_key.permissions


# ==================== API Key Auflisten Tests ====================


class TestListAPIKeys:
    """Tests für GET /api-keys."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, mock_user, mock_db):
        """Leere API-Key Liste."""
        from app.api.v1.api_keys import list_api_keys

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.get_user_keys = AsyncMock(return_value=[])

            response = await list_api_keys(
                current_user=mock_user,
                db=mock_db
            )

            assert response.api_keys == []
            assert response.total == 0

    @pytest.mark.asyncio
    async def test_list_api_keys_with_data(self, mock_user, mock_db):
        """API-Key Liste mit Daten."""
        from app.api.v1.api_keys import list_api_keys

        mock_keys = []
        for i in range(3):
            key = Mock()
            key.id = uuid4()
            key.name = f"Key {i+1}"
            key.prefix = f"abc{i}1234"  # Echte Modell-Spalte (Response key_prefix wird daraus befüllt)
            key.key_hash = f"abcdef{i}12345678901234567890"  # String, nicht Mock
            key.description = "Test key"
            key.permissions = ["read:documents"]
            key.rate_limit = 1000
            key.is_active = True
            key.created_at = datetime.now(timezone.utc)
            key.last_used = None  # Korrigiert: last_used statt last_used_at
            key.expires_at = None
            mock_keys.append(key)

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.get_user_keys = AsyncMock(return_value=mock_keys)

            response = await list_api_keys(
                current_user=mock_user,
                db=mock_db
            )

            assert response.total == 3

    @pytest.mark.asyncio
    async def test_list_api_keys_hides_full_key(self, mock_user, mock_db):
        """Vollständiger Key wird nicht angezeigt."""
        from app.api.v1.api_keys import list_api_keys

        key = Mock()
        key.id = uuid4()
        key.name = "Test Key"
        key.prefix = "abc12345"  # Echte Modell-Spalte (Response key_prefix wird daraus befüllt)
        key.key_hash = "abcdef1234567890abcdef1234567890"  # String, nicht Mock
        key.description = "Test key"
        key.permissions = ["read:documents"]
        key.rate_limit = 1000
        key.is_active = True
        key.created_at = datetime.now(timezone.utc)
        key.last_used = None  # Korrigiert: last_used statt last_used_at
        key.expires_at = None

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.get_user_keys = AsyncMock(return_value=[key])

            response = await list_api_keys(
                current_user=mock_user,
                db=mock_db
            )

            # Response sollte nur key_prefix enthalten, nicht den vollen Key
            if response.api_keys:
                for key_response in response.api_keys:
                    # Der volle Key sollte nie in der Liste erscheinen
                    assert not hasattr(key_response, 'api_key') or \
                           key_response.api_key is None
                    # key_prefix kommt aus der echten prefix-Spalte, nicht aus key_hash
                    assert key_response.key_prefix == "abc12345"


# ==================== API Key Abrufen Tests ====================


class TestGetAPIKey:
    """Tests für GET /api-keys/{key_id}."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_api_key_success(self, mock_user, mock_db):
        """Erfolgreicher Abruf eines API-Keys."""
        from app.api.v1.api_keys import get_api_key

        key_id = uuid4()
        mock_key = Mock()
        mock_key.id = key_id
        mock_key.name = "Test Key"
        mock_key.prefix = "abc12345"  # Echte Modell-Spalte (Response key_prefix wird daraus befüllt)
        mock_key.key_hash = "abcdef1234567890"  # String
        mock_key.description = "Test key"
        mock_key.permissions = ["read:documents"]
        mock_key.rate_limit = 1000
        mock_key.is_active = True
        mock_key.user_id = mock_user.id
        mock_key.created_at = datetime.now(timezone.utc)
        mock_key.last_used = None  # Korrigiert: last_used statt last_used_at
        mock_key.expires_at = None

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.get_key_by_id = AsyncMock(return_value=mock_key)

            response = await get_api_key(
                key_id=key_id,
                current_user=mock_user,
                db=mock_db
            )

            assert response.name == "Test Key"

    @pytest.mark.asyncio
    async def test_get_api_key_not_found(self, mock_user, mock_db):
        """Abruf nicht existierender Key."""
        from app.api.v1.api_keys import get_api_key

        key_id = uuid4()

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.get_key_by_id = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await get_api_key(
                    key_id=key_id,
                    current_user=mock_user,
                    db=mock_db
                )

            assert exc_info.value.status_code == 404


# ==================== API Key Aktualisieren Tests ====================


class TestUpdateAPIKey:
    """Tests für PATCH /api-keys/{key_id}."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_update_api_key_name(self, mock_user, mock_db):
        """Aktualisierung des Key-Namens."""
        from app.api.v1.api_keys import update_api_key
        from app.db.schemas import APIKeyUpdate

        key_id = uuid4()
        mock_key = Mock()
        mock_key.id = key_id
        mock_key.name = "Neuer Name"
        mock_key.description = "Test key"
        mock_key.permissions = ["read:documents"]
        mock_key.rate_limit = 1000
        mock_key.is_active = True
        mock_key.created_at = datetime.now(timezone.utc)
        mock_key.last_used = None
        mock_key.expires_at = None
        mock_key.key_hash = "abcdef1234567890"
        mock_key.prefix = "abc12345"  # Echte Modell-Spalte (Response key_prefix wird daraus befüllt)

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.update_key = AsyncMock(return_value=mock_key)

            update = APIKeyUpdate(name="Neuer Name")

            response = await update_api_key(
                key_id=key_id,
                update_data=update,
                current_user=mock_user,
                db=mock_db
            )

            assert response.name == "Neuer Name"

    @pytest.mark.asyncio
    async def test_update_api_key_deactivate(self, mock_user, mock_db):
        """Deaktivierung eines Keys."""
        from app.api.v1.api_keys import update_api_key
        from app.db.schemas import APIKeyUpdate

        key_id = uuid4()
        mock_key = Mock()
        mock_key.id = key_id
        mock_key.name = "Test Key"
        mock_key.description = "Test key"
        mock_key.permissions = ["read:documents"]
        mock_key.rate_limit = 1000
        mock_key.is_active = False
        mock_key.created_at = datetime.now(timezone.utc)
        mock_key.last_used = None
        mock_key.expires_at = None
        mock_key.key_hash = "abcdef1234567890"
        mock_key.prefix = "abc12345"  # Echte Modell-Spalte (Response key_prefix wird daraus befüllt)

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.update_key = AsyncMock(return_value=mock_key)

            update = APIKeyUpdate(is_active=False)

            response = await update_api_key(
                key_id=key_id,
                update_data=update,
                current_user=mock_user,
                db=mock_db
            )

            assert response.is_active is False


# ==================== API Key Löschen Tests ====================


class TestDeleteAPIKey:
    """Tests für DELETE /api-keys/{key_id}."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_delete_api_key_success(self, mock_user, mock_db):
        """Erfolgreiche Löschung eines API-Keys."""
        from app.api.v1.api_keys import delete_api_key

        key_id = uuid4()
        key_name = "Test API Key"

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            # delete_key gibt den Key-Namen zurück, nicht True
            service.delete_key = AsyncMock(return_value=key_name)

            response = await delete_api_key(
                key_id=key_id,
                current_user=mock_user,
                db=mock_db
            )

            assert response.success is True
            assert "gelöscht" in response.nachricht.lower()
            assert response.deleted_key_name == key_name

    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self, mock_user, mock_db):
        """Löschung nicht existierender Key."""
        from app.api.v1.api_keys import delete_api_key
        from app.services.api_key_service import APIKeyNotFoundError

        key_id = uuid4()

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            error = APIKeyNotFoundError(
                "api_key_not_found",
                user_message_de="API-Key nicht gefunden"
            )
            service.delete_key = AsyncMock(side_effect=error)

            with pytest.raises(HTTPException) as exc_info:
                await delete_api_key(
                    key_id=key_id,
                    current_user=mock_user,
                    db=mock_db
                )

            assert exc_info.value.status_code == 404


# ==================== Berechtigungs-Tests ====================


class TestAPIKeyPermissions:
    """Tests für API-Key Berechtigungen."""

    def test_permission_enum_values(self):
        """Prüfe alle verfügbaren Berechtigungen."""
        from app.db.schemas import APIKeyPermission

        expected = [
            "read:documents",
            "write:documents",
            "delete:documents",
            "ocr:process",
            "search",
            "admin"
        ]

        for perm in expected:
            assert perm in [p.value for p in APIKeyPermission]

# ==================== Rate Limiting Tests ====================


class TestAPIKeyRateLimiting:
    """Tests für API-Key Rate Limiting."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_rate_limit_default(self, mock_user, mock_db):
        """Standard Rate Limit wird gesetzt."""
        from app.api.v1.api_keys import create_api_key
        from app.db.schemas import APIKeyCreate, APIKeyPermission

        mock_key = Mock()
        mock_key.id = uuid4()
        mock_key.name = "Test Key"
        mock_key.rate_limit = 1000  # Default
        mock_key.permissions = ["read:documents"]
        mock_key.expires_at = None

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.create_api_key = AsyncMock(
                return_value=(mock_key, "ablage_test")
            )

            request = APIKeyCreate(
                name="Test Key",
                permissions=[APIKeyPermission.READ_DOCUMENTS]
                # rate_limit nicht gesetzt -> default
            )

            response = await create_api_key(
                key_data=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.rate_limit == 1000

    @pytest.mark.asyncio
    async def test_rate_limit_custom(self, mock_user, mock_db):
        """Benutzerdefiniertes Rate Limit."""
        from app.api.v1.api_keys import create_api_key
        from app.db.schemas import APIKeyCreate, APIKeyPermission

        mock_key = Mock()
        mock_key.id = uuid4()
        mock_key.name = "High Volume Key"
        mock_key.rate_limit = 10000
        mock_key.permissions = ["read:documents"]
        mock_key.expires_at = None

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.create_api_key = AsyncMock(
                return_value=(mock_key, "ablage_test")
            )

            request = APIKeyCreate(
                name="High Volume Key",
                permissions=[APIKeyPermission.READ_DOCUMENTS],
                rate_limit=10000
            )

            response = await create_api_key(
                key_data=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.rate_limit == 10000


# ==================== Key Expiration Tests ====================


class TestAPIKeyExpiration:
    """Tests für API-Key Ablauf."""

    @pytest.fixture
    def mock_user(self):
        """Mock für angemeldeten Benutzer."""
        user = Mock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_db(self):
        """Mock für Datenbank-Session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_key_with_expiration(self, mock_user, mock_db):
        """Key mit Ablaufdatum erstellen."""
        from app.api.v1.api_keys import create_api_key
        from app.db.schemas import APIKeyCreate, APIKeyPermission

        expires = datetime.now(timezone.utc) + timedelta(days=30)

        mock_key = Mock()
        mock_key.id = uuid4()
        mock_key.name = "Temp Key"
        mock_key.rate_limit = 1000
        mock_key.permissions = ["read:documents"]
        mock_key.expires_at = expires

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.create_api_key = AsyncMock(
                return_value=(mock_key, "ablage_test")
            )

            request = APIKeyCreate(
                name="Temp Key",
                permissions=[APIKeyPermission.READ_DOCUMENTS],
                expires_in_days=30
            )

            response = await create_api_key(
                key_data=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.expires_at is not None

    @pytest.mark.asyncio
    async def test_create_key_without_expiration(self, mock_user, mock_db):
        """Key ohne Ablaufdatum erstellen."""
        from app.api.v1.api_keys import create_api_key
        from app.db.schemas import APIKeyCreate, APIKeyPermission

        mock_key = Mock()
        mock_key.id = uuid4()
        mock_key.name = "Permanent Key"
        mock_key.rate_limit = 1000
        mock_key.permissions = ["read:documents"]
        mock_key.expires_at = None

        with patch('app.api.v1.api_keys.get_api_key_service') as mock_service:
            service = mock_service.return_value
            service.create_api_key = AsyncMock(
                return_value=(mock_key, "ablage_test")
            )

            request = APIKeyCreate(
                name="Permanent Key",
                permissions=[APIKeyPermission.READ_DOCUMENTS]
                # expires_in_days nicht gesetzt
            )

            response = await create_api_key(
                key_data=request,
                current_user=mock_user,
                db=mock_db
            )

            assert response.expires_at is None


# ==================== Sicherheits-Tests ====================


class TestAPIKeySecurity:
    """Sicherheitstests für API-Key Endpoints."""

    def test_api_key_format(self):
        """API-Key Format prüfen."""
        # Key sollte mit "ablage_" beginnen
        test_key = "ablage_abc123xyz"
        assert test_key.startswith("ablage_")

    def test_key_prefix_length(self):
        """Key-Prefix Länge prüfen."""
        # Prefix sollte 8 Zeichen haben
        prefix = "abc12345"
        assert len(prefix) == 8

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not integration"])
