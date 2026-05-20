# -*- coding: utf-8 -*-
"""
Unit-Tests für API Key Service.

Testet:
- Key-Generierung mit kryptographisch sicheren Zufallswerten
- Sichere Hash-Speicherung (SHA-256)
- CRUD-Operationen (Create, Read, Update, Delete)
- Key-Validierung und Expiration
- Revocation (einzeln und alle)
- Rate-Limiting und Berechtigungen pro Key
- Limit von MAX_API_KEYS_PER_USER

Feinpoliert und durchdacht - Enterprise-grade API-Key-Tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Tuple
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID
import hashlib
import secrets


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
def sample_api_key():
    """Create sample API key object."""
    key = Mock()
    key.id = uuid4()
    key.user_id = uuid4()
    key.key_hash = hashlib.sha256(b"ablage_test123").hexdigest()
    key.name = "Test API Key"
    key.description = "Test description"
    key.permissions = ["read:documents", "search"]
    key.rate_limit = 1000
    key.is_active = True
    key.expires_at = None
    key.last_used = None
    key.created_at = datetime.now(timezone.utc)
    return key


@pytest.fixture
def api_key_service():
    """Create API Key Service instance."""
    from app.services.api_key_service import APIKeyService
    return APIKeyService()


# ========================= Key Generation Tests =========================


class TestKeyGeneration:
    """Tests for API key generation."""

    def test_generate_api_key_format(self, api_key_service):
        """API Key sollte korrektes Format haben (ablage_<hex>)."""
        key = api_key_service._generate_api_key()

        assert key.startswith("ablage_")
        assert len(key) == 7 + 64  # prefix + 32 bytes hex

        # Check hex part is valid
        hex_part = key.replace("ablage_", "")
        int(hex_part, 16)  # Should not raise

    def test_generate_api_key_uniqueness(self, api_key_service):
        """Generierte Keys sollten eindeutig sein."""
        keys = [api_key_service._generate_api_key() for _ in range(100)]

        assert len(keys) == len(set(keys))

    def test_generate_api_key_entropy(self, api_key_service):
        """Keys sollten ausreichende Entropie haben (256 bits)."""
        key = api_key_service._generate_api_key()
        hex_part = key.replace("ablage_", "")

        # 32 bytes = 64 hex chars = 256 bits
        assert len(hex_part) == 64

    def test_key_prefix_constant(self, api_key_service):
        """Prefix sollte konstant 'ablage_' sein."""
        from app.services.api_key_service import API_KEY_PREFIX

        assert API_KEY_PREFIX == "ablage_"

        # Verify generated keys use this prefix
        key = api_key_service._generate_api_key()
        assert key.startswith(API_KEY_PREFIX)


# ========================= Hash Tests =========================


class TestKeyHashing:
    """Tests for API key hashing."""

    def test_hash_api_key_sha256(self, api_key_service):
        """Hash sollte SHA-256 verwenden."""
        key = "ablage_test123456789"
        expected_hash = hashlib.sha256(key.encode()).hexdigest()

        actual_hash = api_key_service._hash_api_key(key)

        assert actual_hash == expected_hash

    def test_hash_api_key_deterministic(self, api_key_service):
        """Gleicher Key sollte gleichen Hash produzieren."""
        key = "ablage_test123456789"

        hash1 = api_key_service._hash_api_key(key)
        hash2 = api_key_service._hash_api_key(key)

        assert hash1 == hash2

    def test_hash_api_key_different_inputs(self, api_key_service):
        """Verschiedene Keys sollten verschiedene Hashes haben."""
        key1 = "ablage_key1"
        key2 = "ablage_key2"

        hash1 = api_key_service._hash_api_key(key1)
        hash2 = api_key_service._hash_api_key(key2)

        assert hash1 != hash2

    def test_get_key_prefix(self, api_key_service):
        """Key-Prefix sollte erste 8 Zeichen nach ablage_ sein."""
        key = "ablage_abcdefgh12345678"

        prefix = api_key_service._get_key_prefix(key)

        assert prefix == "abcdefgh"
        assert len(prefix) == 8


# ========================= Create API Key Tests =========================


class TestCreateAPIKey:
    """Tests for API key creation."""

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, api_key_service, mock_db, sample_user):
        """Erfolgreiche Key-Erstellung mit allen Parametern."""
        # Mock count query
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        api_key_obj, plain_key = await api_key_service.create_api_key(
            db=mock_db,
            user_id=sample_user.id,
            name="Test Key",
            description="Test description",
            permissions=["read:documents"],
            rate_limit=500,
            expires_in_days=30
        )

        # Verify key was added
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

        # Verify plain key format
        assert plain_key.startswith("ablage_")

    @pytest.mark.asyncio
    async def test_create_api_key_default_permissions(self, api_key_service, mock_db, sample_user):
        """Ohne Permissions sollten Default-Berechtigungen gesetzt werden."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # Capture the APIKey object being added
        added_key = None
        def capture_add(obj):
            nonlocal added_key
            added_key = obj
        mock_db.add.side_effect = capture_add

        await api_key_service.create_api_key(
            db=mock_db,
            user_id=sample_user.id,
            name="Test Key",
            permissions=None  # Use defaults
        )

        # Verify default permissions
        assert added_key is not None
        assert "read:documents" in added_key.permissions
        assert "search" in added_key.permissions

    @pytest.mark.asyncio
    async def test_create_api_key_with_expiration(self, api_key_service, mock_db, sample_user):
        """Key mit Ablaufdatum sollte korrekt gesetzt werden."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        added_key = None
        def capture_add(obj):
            nonlocal added_key
            added_key = obj
        mock_db.add.side_effect = capture_add

        await api_key_service.create_api_key(
            db=mock_db,
            user_id=sample_user.id,
            name="Expiring Key",
            expires_in_days=7
        )

        assert added_key.expires_at is not None
        # Should expire in approximately 7 days
        expected = datetime.now(timezone.utc) + timedelta(days=7)
        assert abs((added_key.expires_at - expected).total_seconds()) < 5

    @pytest.mark.asyncio
    async def test_create_api_key_limit_reached(self, api_key_service, mock_db, sample_user):
        """Sollte Fehler werfen wenn MAX_API_KEYS_PER_USER erreicht."""
        from app.services.api_key_service import APIKeyLimitError, MAX_API_KEYS_PER_USER

        # Mock 10 existing keys
        mock_result = Mock()
        existing_keys = [Mock() for _ in range(MAX_API_KEYS_PER_USER)]
        mock_result.scalars.return_value.all.return_value = existing_keys
        mock_db.execute.return_value = mock_result

        with pytest.raises(APIKeyLimitError) as exc_info:
            await api_key_service.create_api_key(
                db=mock_db,
                user_id=sample_user.id,
                name="Too Many Keys"
            )

        assert "Maximale Anzahl" in exc_info.value.user_message_de


# ========================= Validate API Key Tests =========================


class TestValidateAPIKey:
    """Tests for API key validation."""

    @pytest.mark.asyncio
    async def test_validate_api_key_success(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Gültiger Key sollte User und APIKey zurückgeben."""
        # Setup mock
        sample_api_key.expires_at = None
        sample_api_key.is_active = True
        sample_user.is_active = True

        mock_result = Mock()
        mock_result.first.return_value = (sample_api_key, sample_user)
        mock_db.execute.return_value = mock_result

        # Use the hash that corresponds to our test key
        test_key = "ablage_" + "a" * 64
        sample_api_key.key_hash = api_key_service._hash_api_key(test_key)

        result = await api_key_service.validate_api_key(mock_db, test_key)

        assert result is not None
        api_key, user = result
        assert api_key == sample_api_key
        assert user == sample_user

    @pytest.mark.asyncio
    async def test_validate_api_key_invalid_prefix(self, api_key_service, mock_db):
        """Key ohne ablage_ Prefix sollte None zurückgeben."""
        invalid_key = "invalid_prefix_key"

        result = await api_key_service.validate_api_key(mock_db, invalid_key)

        assert result is None
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_api_key_not_found(self, api_key_service, mock_db):
        """Nicht existierender Key sollte None zurückgeben."""
        mock_result = Mock()
        mock_result.first.return_value = None
        mock_db.execute.return_value = mock_result

        result = await api_key_service.validate_api_key(mock_db, "ablage_nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_api_key_expired(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Abgelaufener Key sollte None zurückgeben."""
        # Set expired timestamp
        sample_api_key.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        sample_api_key.is_active = True

        mock_result = Mock()
        mock_result.first.return_value = (sample_api_key, sample_user)
        mock_db.execute.return_value = mock_result

        result = await api_key_service.validate_api_key(mock_db, "ablage_test")

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_api_key_updates_last_used(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Validierung sollte last_used aktualisieren."""
        sample_api_key.expires_at = None
        sample_api_key.is_active = True
        sample_api_key.last_used = None

        mock_result = Mock()
        mock_result.first.return_value = (sample_api_key, sample_user)
        mock_db.execute.return_value = mock_result

        await api_key_service.validate_api_key(mock_db, "ablage_test")

        assert sample_api_key.last_used is not None
        mock_db.commit.assert_called_once()


# ========================= Get User Keys Tests =========================


class TestGetUserKeys:
    """Tests for listing user API keys."""

    @pytest.mark.asyncio
    async def test_get_user_keys_returns_list(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Sollte Liste aller Keys eines Users zurückgeben."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [sample_api_key]
        mock_db.execute.return_value = mock_result

        keys = await api_key_service.get_user_keys(mock_db, sample_user.id)

        assert len(keys) == 1
        assert keys[0] == sample_api_key

    @pytest.mark.asyncio
    async def test_get_user_keys_empty(self, api_key_service, mock_db, sample_user):
        """User ohne Keys sollte leere Liste bekommen."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        keys = await api_key_service.get_user_keys(mock_db, sample_user.id)

        assert len(keys) == 0


# ========================= Update API Key Tests =========================


class TestUpdateAPIKey:
    """Tests for API key updates."""

    @pytest.mark.asyncio
    async def test_update_key_name(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Key-Name sollte aktualisiert werden können."""
        # Mock get_key_by_id
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_api_key
        mock_db.execute.return_value = mock_result

        updated_key = await api_key_service.update_key(
            db=mock_db,
            key_id=sample_api_key.id,
            user_id=sample_user.id,
            name="New Name"
        )

        assert sample_api_key.name == "New Name"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_key_permissions(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Key-Berechtigungen sollten aktualisiert werden können."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_api_key
        mock_db.execute.return_value = mock_result

        new_permissions = ["read:documents", "write:documents", "admin"]
        await api_key_service.update_key(
            db=mock_db,
            key_id=sample_api_key.id,
            user_id=sample_user.id,
            permissions=new_permissions
        )

        assert sample_api_key.permissions == new_permissions

    @pytest.mark.asyncio
    async def test_update_key_deactivate(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Key sollte deaktiviert werden können."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_api_key
        mock_db.execute.return_value = mock_result

        await api_key_service.update_key(
            db=mock_db,
            key_id=sample_api_key.id,
            user_id=sample_user.id,
            is_active=False
        )

        assert sample_api_key.is_active is False

    @pytest.mark.asyncio
    async def test_update_key_not_found(self, api_key_service, mock_db, sample_user):
        """Update auf nicht existierenden Key sollte Fehler werfen."""
        from app.services.api_key_service import APIKeyNotFoundError

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(APIKeyNotFoundError) as exc_info:
            await api_key_service.update_key(
                db=mock_db,
                key_id=uuid4(),
                user_id=sample_user.id,
                name="New Name"
            )

        assert "nicht gefunden" in exc_info.value.user_message_de


# ========================= Delete API Key Tests =========================


class TestDeleteAPIKey:
    """Tests for API key deletion."""

    @pytest.mark.asyncio
    async def test_delete_key_success(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Key sollte erfolgreich gelöscht werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_api_key
        mock_db.execute.return_value = mock_result

        deleted_name = await api_key_service.delete_key(
            db=mock_db,
            key_id=sample_api_key.id,
            user_id=sample_user.id
        )

        assert deleted_name == sample_api_key.name
        mock_db.delete.assert_called_once_with(sample_api_key)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_key_not_found(self, api_key_service, mock_db, sample_user):
        """Löschen nicht existierenden Keys sollte Fehler werfen."""
        from app.services.api_key_service import APIKeyNotFoundError

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(APIKeyNotFoundError):
            await api_key_service.delete_key(
                db=mock_db,
                key_id=uuid4(),
                user_id=sample_user.id
            )


# ========================= Revoke All Keys Tests =========================


class TestRevokeAllKeys:
    """Tests for revoking all user keys."""

    @pytest.mark.asyncio
    async def test_revoke_all_keys_success(self, api_key_service, mock_db, sample_user):
        """Alle Keys eines Users sollten deaktiviert werden."""
        mock_result = Mock()
        mock_result.rowcount = 3
        mock_db.execute.return_value = mock_result

        count = await api_key_service.revoke_all_keys(mock_db, sample_user.id)

        assert count == 3
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_all_keys_none_active(self, api_key_service, mock_db, sample_user):
        """Bei keinen aktiven Keys sollte 0 zurückgegeben werden."""
        mock_result = Mock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        count = await api_key_service.revoke_all_keys(mock_db, sample_user.id)

        assert count == 0


# ========================= Permission Tests =========================


class TestAPIKeyPermissions:
    """Tests for API key permission checking."""

    def test_has_permission_direct(self, api_key_service, sample_api_key):
        """Direkte Berechtigung sollte True zurückgeben."""
        sample_api_key.permissions = ["read:documents", "search"]

        result = api_key_service.has_permission(sample_api_key, "read:documents")

        assert result is True

    def test_has_permission_missing(self, api_key_service, sample_api_key):
        """Fehlende Berechtigung sollte False zurückgeben."""
        sample_api_key.permissions = ["read:documents"]

        result = api_key_service.has_permission(sample_api_key, "write:documents")

        assert result is False

    def test_has_permission_admin(self, api_key_service, sample_api_key):
        """Admin-Berechtigung sollte alles erlauben."""
        sample_api_key.permissions = ["admin"]

        assert api_key_service.has_permission(sample_api_key, "read:documents") is True
        assert api_key_service.has_permission(sample_api_key, "write:documents") is True
        assert api_key_service.has_permission(sample_api_key, "delete:documents") is True


# ========================= Singleton Tests =========================


class TestAPIKeyServiceSingleton:
    """Tests for singleton pattern."""

    def test_get_api_key_service_singleton(self):
        """Service sollte als Singleton funktionieren."""
        from app.services.api_key_service import get_api_key_service

        service1 = get_api_key_service()
        service2 = get_api_key_service()

        assert service1 is service2

    def test_get_api_key_service_type(self):
        """Singleton sollte APIKeyService-Instanz sein."""
        from app.services.api_key_service import get_api_key_service, APIKeyService

        service = get_api_key_service()

        assert isinstance(service, APIKeyService)


# ========================= Rate Limit Tests =========================


class TestAPIKeyRateLimit:
    """Tests for rate limit configuration."""

    @pytest.mark.asyncio
    async def test_create_key_with_custom_rate_limit(self, api_key_service, mock_db, sample_user):
        """Key mit benutzerdefiniertem Rate-Limit."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        added_key = None
        def capture_add(obj):
            nonlocal added_key
            added_key = obj
        mock_db.add.side_effect = capture_add

        await api_key_service.create_api_key(
            db=mock_db,
            user_id=sample_user.id,
            name="Rate Limited Key",
            rate_limit=100  # Lower than default
        )

        assert added_key.rate_limit == 100

    @pytest.mark.asyncio
    async def test_update_key_rate_limit(self, api_key_service, mock_db, sample_user, sample_api_key):
        """Rate-Limit sollte aktualisiert werden können."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = sample_api_key
        mock_db.execute.return_value = mock_result

        await api_key_service.update_key(
            db=mock_db,
            key_id=sample_api_key.id,
            user_id=sample_user.id,
            rate_limit=2000
        )

        assert sample_api_key.rate_limit == 2000
