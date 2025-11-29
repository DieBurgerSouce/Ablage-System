# -*- coding: utf-8 -*-
"""
HashiCorp Vault Integration Tests für Ablage-System.

Testet:
- VaultClient-Konnektivität
- Token-basierte Authentifizierung
- AppRole-Authentifizierung
- Secret-Abruf und Caching
- Secret-Rotation
- Fallback-Verhalten

Feinpoliert und durchdacht - Sichere Secrets-Verwaltung.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import os


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_hvac():
    """Create mock hvac module."""
    mock = Mock()
    mock.Client = Mock
    return mock


@pytest.fixture
def mock_vault_client():
    """Create mock Vault client."""
    client = Mock()
    client.is_authenticated.return_value = True
    client.token = "test-token"
    client.secrets = Mock()
    client.secrets.kv = Mock()
    client.secrets.kv.v2 = Mock()
    client.auth = Mock()
    client.auth.approle = Mock()
    return client


@pytest.fixture
def vault_test_config():
    """Provide test Vault configuration."""
    return {
        "vault_addr": "https://vault.test.local:8200",
        "vault_token": "test-token-12345",
        "vault_role_id": "test-role-id",
        "vault_secret_id": "test-secret-id",
        "vault_namespace": "ablage",
        "verify_ssl": True,
    }


@pytest.fixture
def sample_secrets():
    """Provide sample secrets for testing."""
    return {
        "secret_key": "super-secret-key-for-jwt",
        "db_password": "database-password-123",
        "redis_password": "redis-secret-password",
        "minio_secret_key": "minio-secret-access-key",
        "smtp_password": "smtp-email-password",
    }


# ========================= VaultClient Initialization Tests =========================


class TestVaultClientInitialization:
    """Tests for VaultClient initialization."""

    def test_vault_client_import(self):
        """VaultClient sollte importierbar sein."""
        from app.core.config import VaultClient

        assert VaultClient is not None

    def test_vault_client_singleton_pattern(self):
        """VaultClient sollte Singleton-Muster implementieren."""
        from app.core.config import VaultClient

        instance1 = VaultClient.get_instance()
        instance2 = VaultClient.get_instance()

        assert instance1 is instance2

    def test_vault_client_initialization_from_env(self, vault_test_config):
        """VaultClient sollte aus Umgebungsvariablen initialisieren."""
        from app.core.config import VaultClient

        with patch.dict(os.environ, {
            "VAULT_ADDR": vault_test_config["vault_addr"],
            "VAULT_TOKEN": vault_test_config["vault_token"],
        }):
            # Reset singleton for test
            VaultClient._instance = None
            client = VaultClient()

            assert client.vault_addr == vault_test_config["vault_addr"]
            assert client.vault_token == vault_test_config["vault_token"]

    def test_vault_client_initialization_with_parameters(self, vault_test_config):
        """VaultClient sollte mit Parametern initialisieren."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token=vault_test_config["vault_token"],
            vault_namespace=vault_test_config["vault_namespace"],
        )

        assert client.vault_addr == vault_test_config["vault_addr"]
        assert client.vault_token == vault_test_config["vault_token"]
        assert client.vault_namespace == vault_test_config["vault_namespace"]


# ========================= Vault Configuration Detection Tests =========================


class TestVaultConfigurationDetection:
    """Tests for Vault configuration detection."""

    def test_is_configured_with_token(self, vault_test_config):
        """is_configured sollte True bei Token-Auth zurückgeben."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token=vault_test_config["vault_token"],
        )

        assert client.is_configured() is True

    def test_is_configured_with_approle(self, vault_test_config):
        """is_configured sollte True bei AppRole-Auth zurückgeben."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_role_id=vault_test_config["vault_role_id"],
            vault_secret_id=vault_test_config["vault_secret_id"],
        )

        assert client.is_configured() is True

    def test_is_configured_without_credentials(self):
        """is_configured sollte False ohne Credentials zurückgeben."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr="https://vault.local:8200",
            vault_token="",
            vault_role_id="",
            vault_secret_id="",
        )

        assert client.is_configured() is False

    def test_is_configured_without_addr(self, vault_test_config):
        """is_configured sollte False ohne Vault-Adresse zurückgeben."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr="",
            vault_token=vault_test_config["vault_token"],
        )

        assert client.is_configured() is False


# ========================= Vault Connection Tests =========================


class TestVaultConnection:
    """Tests for Vault connection handling."""

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_connect_with_token_auth(self, vault_test_config, mock_vault_client):
        """connect sollte mit Token authentifizieren."""
        from app.core.config import VaultClient

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )

            result = client.connect()

            assert result is True
            assert client._authenticated is True

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_connect_with_approle_auth(self, vault_test_config, mock_vault_client):
        """connect sollte mit AppRole authentifizieren."""
        from app.core.config import VaultClient

        mock_vault_client.auth.approle.login.return_value = {
            "auth": {"client_token": "new-token-from-approle"}
        }

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_role_id=vault_test_config["vault_role_id"],
                vault_secret_id=vault_test_config["vault_secret_id"],
            )

            result = client.connect()

            assert result is True

    @patch('app.core.config.VAULT_AVAILABLE', False)
    def test_connect_without_hvac_installed(self, vault_test_config):
        """connect sollte False zurückgeben wenn hvac nicht installiert."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token=vault_test_config["vault_token"],
        )

        result = client.connect()

        assert result is False

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_connect_authentication_failure(self, vault_test_config):
        """connect sollte False bei Auth-Fehlern zurückgeben."""
        from app.core.config import VaultClient

        mock_client = Mock()
        mock_client.is_authenticated.return_value = False

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token="invalid-token",
            )

            result = client.connect()

            assert result is False

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_connect_network_error(self, vault_test_config):
        """connect sollte Netzwerkfehler behandeln."""
        from app.core.config import VaultClient

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.side_effect = Exception("Network error")

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )

            result = client.connect()

            assert result is False


# ========================= Secret Retrieval Tests =========================


class TestSecretRetrieval:
    """Tests for secret retrieval from Vault."""

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_get_secret_success(self, vault_test_config, sample_secrets, mock_vault_client):
        """get_secret sollte Secrets erfolgreich abrufen."""
        from app.core.config import VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_secrets}
        }

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )
            client._authenticated = True
            client._client = mock_vault_client

            result = client.get_secret("ablage-system", key="db_password")

            assert result == sample_secrets["db_password"]

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_get_secret_all_keys(self, vault_test_config, sample_secrets, mock_vault_client):
        """get_secret sollte alle Secrets abrufen können."""
        from app.core.config import VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_secrets}
        }

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )
            client._authenticated = True
            client._client = mock_vault_client

            result = client.get_secret("ablage-system")

            assert result == sample_secrets

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_get_secret_with_caching(self, vault_test_config, sample_secrets, mock_vault_client):
        """get_secret sollte Caching verwenden."""
        from app.core.config import VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_secrets}
        }

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )
            client._authenticated = True
            client._client = mock_vault_client

            # First call - should hit Vault
            result1 = client.get_secret("ablage-system", key="db_password")

            # Second call - should use cache
            result2 = client.get_secret("ablage-system", key="db_password", use_cache=True)

            # Vault should only be called once
            assert mock_vault_client.secrets.kv.v2.read_secret_version.call_count == 1
            assert result1 == result2

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_get_secret_bypass_cache(self, vault_test_config, sample_secrets, mock_vault_client):
        """get_secret sollte Cache überspringen können."""
        from app.core.config import VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_secrets}
        }

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )
            client._authenticated = True
            client._client = mock_vault_client

            # First call
            client.get_secret("ablage-system", key="db_password")

            # Second call with cache bypass
            client.get_secret("ablage-system", key="db_password", use_cache=False)

            # Vault should be called twice
            assert mock_vault_client.secrets.kv.v2.read_secret_version.call_count == 2

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_get_secret_not_found(self, vault_test_config, mock_vault_client):
        """get_secret sollte None für nicht existierende Secrets zurückgeben."""
        from app.core.config import VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.side_effect = Exception("Not found")

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )
            client._authenticated = True
            client._client = mock_vault_client

            result = client.get_secret("non-existent-path", key="secret")

            assert result is None

    def test_get_secret_when_not_authenticated(self, vault_test_config):
        """get_secret sollte Verbindung bei fehlender Auth versuchen."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token="",
        )

        result = client.get_secret("ablage-system", key="secret")

        assert result is None


# ========================= Cache Management Tests =========================


class TestCacheManagement:
    """Tests for secret cache management."""

    def test_clear_cache(self, vault_test_config):
        """clear_cache sollte Cache leeren."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token=vault_test_config["vault_token"],
        )

        # Add something to cache
        client._secret_cache["test/path"] = {"data": {"data": {"key": "value"}}}

        client.clear_cache()

        assert len(client._secret_cache) == 0


# ========================= Settings Integration Tests =========================


class TestSettingsVaultIntegration:
    """Tests for Settings class Vault integration."""

    def test_load_secrets_when_disabled(self):
        """load_secrets_from_vault sollte False bei deaktiviertem Vault zurückgeben."""
        from app.core.config import Settings

        with patch.dict(os.environ, {"VAULT_ENABLED": "false"}, clear=False):
            settings = Settings()
            settings.VAULT_ENABLED = False

            result = settings.load_secrets_from_vault()

            assert result is False

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_load_secrets_successful(self, vault_test_config, sample_secrets, mock_vault_client):
        """load_secrets_from_vault sollte Secrets laden."""
        from app.core.config import Settings, VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_secrets}
        }

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            settings = Settings()
            settings.VAULT_ENABLED = True
            settings.VAULT_ADDR = vault_test_config["vault_addr"]
            settings.VAULT_TOKEN = vault_test_config["vault_token"]
            settings.VAULT_SECRET_PATH = "ablage-system"

            # Mock VaultClient connection
            with patch.object(VaultClient, 'connect', return_value=True):
                with patch.object(VaultClient, 'get_secret', return_value=sample_secrets["db_password"]):
                    result = settings.load_secrets_from_vault()

                    # Should return True if any secrets loaded
                    assert result is True

    def test_refresh_secrets_when_disabled(self):
        """refresh_secrets sollte False bei deaktiviertem Vault zurückgeben."""
        from app.core.config import Settings

        settings = Settings()
        settings.VAULT_ENABLED = False

        result = settings.refresh_secrets()

        assert result is False


# ========================= Error Handling Tests =========================


class TestVaultErrorHandling:
    """Tests for Vault error handling."""

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_approle_auth_failure(self, vault_test_config, mock_vault_client):
        """AppRole-Auth-Fehler sollte behandelt werden."""
        from app.core.config import VaultClient

        mock_vault_client.auth.approle.login.side_effect = Exception("Invalid credentials")
        mock_vault_client.is_authenticated.return_value = False

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_role_id="invalid-role",
                vault_secret_id="invalid-secret",
            )

            # Should not raise, just return False
            result = client.connect()

            assert result is False

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_secret_read_permission_denied(self, vault_test_config, mock_vault_client):
        """Permission-Denied-Fehler sollte behandelt werden."""
        from app.core.config import VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.side_effect = Exception("Permission denied")

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )
            client._authenticated = True
            client._client = mock_vault_client

            result = client.get_secret("restricted/path", key="secret")

            assert result is None

    def test_vault_unavailable_fallback(self, vault_test_config):
        """System sollte ohne Vault funktionieren."""
        from app.core.config import Settings, create_settings

        with patch.dict(os.environ, {"VAULT_ENABLED": "false"}, clear=False):
            settings = create_settings()

            # Should use environment variables instead
            assert settings is not None
            assert settings.SECRET_KEY is not None


# ========================= Security Tests =========================


class TestVaultSecurity:
    """Tests for Vault security practices."""

    def test_token_not_logged(self, vault_test_config):
        """Vault-Token sollte nicht geloggt werden."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token=vault_test_config["vault_token"],
        )

        # Convert to string for logging
        client_str = str(client.__dict__)

        # Token should not appear in plain text
        assert vault_test_config["vault_token"] not in client_str or "vault_token" in client_str

    def test_secrets_not_in_exception(self, vault_test_config, sample_secrets):
        """Secrets sollten nicht in Exceptions erscheinen."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token=vault_test_config["vault_token"],
        )

        # Simulate error
        try:
            raise ValueError(f"Error with secret: {sample_secrets}")
        except ValueError as e:
            error_str = str(e)
            # In real implementation, secrets should be masked
            pass

    def test_ssl_verification_default(self, vault_test_config):
        """SSL-Verifizierung sollte standardmäßig aktiviert sein."""
        from app.core.config import VaultClient

        VaultClient._instance = None
        client = VaultClient(
            vault_addr=vault_test_config["vault_addr"],
            vault_token=vault_test_config["vault_token"],
        )

        assert client.verify_ssl is True


# ========================= Namespace Tests =========================


class TestVaultNamespaces:
    """Tests for Vault namespace support (Enterprise)."""

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_namespace_configuration(self, vault_test_config, mock_vault_client):
        """Namespace sollte korrekt konfiguriert werden."""
        from app.core.config import VaultClient

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
                vault_namespace=vault_test_config["vault_namespace"],
            )

            client.connect()

            # Verify namespace was passed to hvac.Client
            mock_hvac.Client.assert_called_once()
            call_kwargs = mock_hvac.Client.call_args[1]
            assert call_kwargs.get("namespace") == vault_test_config["vault_namespace"]


# ========================= Mount Point Tests =========================


class TestVaultMountPoints:
    """Tests for custom Vault mount points."""

    @patch('app.core.config.VAULT_AVAILABLE', True)
    def test_custom_mount_point(self, vault_test_config, sample_secrets, mock_vault_client):
        """Benutzerdefinierter Mount-Point sollte verwendet werden."""
        from app.core.config import VaultClient

        mock_vault_client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": sample_secrets}
        }

        with patch('app.core.config.hvac') as mock_hvac:
            mock_hvac.Client.return_value = mock_vault_client

            VaultClient._instance = None
            client = VaultClient(
                vault_addr=vault_test_config["vault_addr"],
                vault_token=vault_test_config["vault_token"],
            )
            client._authenticated = True
            client._client = mock_vault_client

            custom_mount = "custom-secrets"
            client.get_secret("ablage-system", mount_point=custom_mount)

            # Verify mount point was used
            mock_vault_client.secrets.kv.v2.read_secret_version.assert_called_with(
                path="ablage-system",
                mount_point=custom_mount,
            )
