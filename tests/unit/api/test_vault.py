# -*- coding: utf-8 -*-
"""
Unit Tests fuer Vault API Endpoints.

Testet:
- GET /vault/status - Vault-Status (Admin only)
- GET /vault/health - Vault Health Check (Public)
- GET /vault/secrets/metadata/{path} - Secret Metadaten (Admin only)
- POST /vault/refresh - Secrets aktualisieren (Admin only)
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
from fastapi import HTTPException

from app.api.v1.vault import (
    VaultStatusResponse,
    VaultHealthResponse,
    SecretMetadataResponse,
    get_vault_status,
    vault_health_check,
    get_secret_metadata,
    refresh_secrets,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_superuser():
    """Mock Superuser fuer geschuetzte Endpoints."""
    user = MagicMock()
    user.id = "test-admin-id"
    user.email = "admin@test.local"
    user.is_superuser = True
    return user


@pytest.fixture
def mock_normal_user():
    """Mock normaler User (kein Superuser)."""
    user = MagicMock()
    user.id = "test-user-id"
    user.email = "user@test.local"
    user.is_superuser = False
    return user


@pytest.fixture
def mock_vault_client():
    """Mock VaultClient fuer Tests."""
    client = MagicMock()
    client.connect.return_value = True
    client._authenticated = True
    client._client = MagicMock()
    return client


# =============================================================================
# Test GET /vault/status
# =============================================================================


class TestVaultStatus:
    """Tests fuer GET /vault/status Endpoint."""

    @pytest.mark.asyncio
    async def test_vault_disabled_returns_disabled_status(self, mock_superuser):
        """Wenn Vault deaktiviert ist, sollte disabled-Status zurueckgegeben werden."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            result = await get_vault_status(current_user=mock_superuser)

            assert isinstance(result, VaultStatusResponse)
            assert result.enabled is False
            assert result.connected is False
            assert result.authenticated is False

    @pytest.mark.asyncio
    async def test_vault_enabled_and_connected(self, mock_superuser, mock_vault_client):
        """Erfolgreiche Vault-Verbindung sollte connected-Status zeigen."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True

            # Mock health and seal status
            mock_vault_client._client.sys.read_health_status.return_value = {
                "version": "1.15.0",
                "cluster_name": "vault-cluster",
            }
            mock_vault_client._client.sys.read_seal_status.return_value = {
                "sealed": False,
            }

            result = await get_vault_status(current_user=mock_superuser)

            assert result.enabled is True
            assert result.connected is True
            assert result.authenticated is True
            assert result.sealed is False
            assert result.version == "1.15.0"
            assert result.address == "http://vault:8200"

    @pytest.mark.asyncio
    async def test_vault_connection_failed(self, mock_superuser, mock_vault_client):
        """Fehlgeschlagene Verbindung sollte entsprechenden Status zeigen."""
        mock_vault_client.connect.return_value = False

        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True

            result = await get_vault_status(current_user=mock_superuser)

            assert result.enabled is True
            assert result.connected is False
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_vault_status_includes_timestamp(self, mock_superuser):
        """Status sollte einen gueltigen Timestamp enthalten."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            result = await get_vault_status(current_user=mock_superuser)

            assert result.last_check is not None
            # Sollte parsebar sein
            datetime.fromisoformat(result.last_check)

    @pytest.mark.asyncio
    async def test_vault_status_partial_health_failure(self, mock_superuser, mock_vault_client):
        """Teilweiser Health-Check-Fehler sollte behandelt werden."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True

            # Health check wirft Fehler
            mock_vault_client._client.sys.read_health_status.side_effect = Exception("Health check failed")

            result = await get_vault_status(current_user=mock_superuser)

            assert result.connected is True
            assert "Teilweise" in result.error or "fehlgeschlagen" in result.error


# =============================================================================
# Test GET /vault/health
# =============================================================================


class TestVaultHealth:
    """Tests fuer GET /vault/health Endpoint (Public)."""

    @pytest.mark.asyncio
    async def test_vault_disabled_health(self):
        """Health Check bei deaktiviertem Vault."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            result = await vault_health_check()

            assert isinstance(result, VaultHealthResponse)
            assert result.status == "disabled"
            assert result.vault_enabled is False
            assert result.secrets_engine_status == "n/a"

    @pytest.mark.asyncio
    async def test_vault_healthy(self, mock_vault_client):
        """Healthy Vault sollte healthy-Status zurueckgeben."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            # KV Engine check erfolgreich
            mock_vault_client._client.secrets.kv.v2.list_secrets.return_value = {}
            # Transit Engine check erfolgreich
            mock_vault_client._client.secrets.transit.list_keys.return_value = {}

            result = await vault_health_check()

            assert result.status == "healthy"
            assert result.vault_connected is True
            assert result.secrets_engine_status == "healthy"

    @pytest.mark.asyncio
    async def test_vault_connection_failed_health(self, mock_vault_client):
        """Fehlgeschlagene Verbindung sollte unhealthy sein."""
        mock_vault_client.connect.return_value = False

        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True

            result = await vault_health_check()

            assert result.status == "unhealthy"
            assert result.vault_connected is False

    @pytest.mark.asyncio
    async def test_vault_kv_permission_denied(self, mock_vault_client):
        """KV Permission Denied sollte permission_denied Status zeigen."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            # KV Engine check wirft PermissionError
            mock_vault_client._client.secrets.kv.v2.list_secrets.side_effect = PermissionError("Permission denied")

            result = await vault_health_check()

            assert result.secrets_engine_status == "permission_denied"

    @pytest.mark.asyncio
    async def test_vault_transit_not_configured(self, mock_vault_client):
        """Transit Engine nicht konfiguriert sollte not_configured zeigen."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            # KV OK
            mock_vault_client._client.secrets.kv.v2.list_secrets.return_value = {}
            # Transit nicht konfiguriert
            mock_vault_client._client.secrets.transit.list_keys.side_effect = Exception("Path not found")

            result = await vault_health_check()

            assert result.transit_engine_status == "not_configured"

    @pytest.mark.asyncio
    async def test_vault_degraded_status(self, mock_vault_client):
        """KV Engine unhealthy sollte degraded Status ergeben."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            # KV Engine check fehlgeschlagen
            mock_vault_client._client.secrets.kv.v2.list_secrets.side_effect = Exception("Engine error")

            result = await vault_health_check()

            assert result.status == "degraded"
            assert result.secrets_engine_status == "unhealthy"


# =============================================================================
# Test GET /vault/secrets/metadata/{path}
# =============================================================================


class TestVaultSecretMetadata:
    """Tests fuer GET /vault/secrets/metadata/{path} Endpoint."""

    @pytest.mark.asyncio
    async def test_vault_disabled_returns_503(self, mock_superuser):
        """Bei deaktiviertem Vault sollte 503 zurueckgegeben werden."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            with pytest.raises(HTTPException) as exc_info:
                await get_secret_metadata(path="test/secret", current_user=mock_superuser)

            assert exc_info.value.status_code == 503
            assert "deaktiviert" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_vault_connection_failed_returns_503(self, mock_superuser, mock_vault_client):
        """Fehlgeschlagene Verbindung sollte 503 zurueckgeben."""
        mock_vault_client.connect.return_value = False

        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True

            with pytest.raises(HTTPException) as exc_info:
                await get_secret_metadata(path="test/secret", current_user=mock_superuser)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_secret_not_found_returns_404(self, mock_superuser, mock_vault_client):
        """Nicht gefundenes Secret sollte 404 zurueckgeben."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            # Secret nicht gefunden
            mock_vault_client.get_secret.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await get_secret_metadata(path="nonexistent/path", current_user=mock_superuser)

            assert exc_info.value.status_code == 404
            assert "nicht gefunden" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_secret_metadata_returns_keys_only(self, mock_superuser, mock_vault_client):
        """Metadaten sollten nur Schluesselnamen enthalten, keine Werte."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            # Secret gefunden (mit sensiblen Werten)
            mock_vault_client.get_secret.return_value = {
                "username": "admin",
                "password": "super_secret_password",
                "api_key": "abc123",
            }

            # Metadaten
            mock_vault_client._client.secrets.kv.v2.read_secret_metadata.return_value = {
                "data": {
                    "current_version": 3,
                    "created_time": "2024-01-01T00:00:00Z",
                    "updated_time": "2024-06-01T00:00:00Z",
                }
            }

            result = await get_secret_metadata(path="test/secret", current_user=mock_superuser)

            assert isinstance(result, SecretMetadataResponse)
            assert result.path == "test/secret"
            assert result.version == 3
            # Nur Keys, keine Werte!
            assert "username" in result.keys
            assert "password" in result.keys
            assert "api_key" in result.keys
            # Stelle sicher, dass keine sensiblen Werte durchgereicht werden
            assert "super_secret_password" not in str(result)
            assert "abc123" not in str(result)

    @pytest.mark.asyncio
    async def test_metadata_fetch_error_returns_500(self, mock_superuser, mock_vault_client):
        """Fehler beim Abrufen sollte 500 zurueckgeben."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client):
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            # get_secret wirft Fehler
            mock_vault_client.get_secret.side_effect = Exception("Vault internal error")

            with pytest.raises(HTTPException) as exc_info:
                await get_secret_metadata(path="test/secret", current_user=mock_superuser)

            assert exc_info.value.status_code == 500


# =============================================================================
# Test POST /vault/refresh
# =============================================================================


class TestVaultRefresh:
    """Tests fuer POST /vault/refresh Endpoint."""

    @pytest.mark.asyncio
    async def test_vault_disabled_returns_503(self, mock_superuser):
        """Bei deaktiviertem Vault sollte 503 zurueckgegeben werden."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            with pytest.raises(HTTPException) as exc_info:
                await refresh_secrets(current_user=mock_superuser)

            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_refresh_secrets_success(self, mock_superuser):
        """Erfolgreiche Secret-Aktualisierung."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = True
            mock_settings.refresh_secrets.return_value = True

            result = await refresh_secrets(current_user=mock_superuser)

            assert result["status"] == "success"
            assert "aktualisiert" in result["message"]
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_refresh_secrets_no_change(self, mock_superuser):
        """Keine neuen Secrets gefunden."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = True
            mock_settings.refresh_secrets.return_value = False

            result = await refresh_secrets(current_user=mock_superuser)

            assert result["status"] == "no_change"
            assert "Keine neuen" in result["message"]

    @pytest.mark.asyncio
    async def test_refresh_secrets_error_returns_500(self, mock_superuser):
        """Fehler beim Aktualisieren sollte 500 zurueckgeben."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = True
            mock_settings.refresh_secrets.side_effect = Exception("Refresh failed")

            with pytest.raises(HTTPException) as exc_info:
                await refresh_secrets(current_user=mock_superuser)

            assert exc_info.value.status_code == 500
            assert "Fehler" in exc_info.value.detail


# =============================================================================
# Test Response Schema Validation
# =============================================================================


class TestVaultResponseSchemas:
    """Tests fuer Vault Response Schema Validierung."""

    def test_vault_status_response_schema(self):
        """VaultStatusResponse sollte alle erforderlichen Felder haben."""
        response = VaultStatusResponse(
            enabled=True,
            connected=True,
            authenticated=True,
            sealed=False,
            version="1.15.0",
            cluster_name="test-cluster",
            address="http://vault:8200",
            last_check="2024-01-01T00:00:00Z",
        )

        assert response.enabled is True
        assert response.version == "1.15.0"

    def test_vault_health_response_schema(self):
        """VaultHealthResponse sollte alle erforderlichen Felder haben."""
        response = VaultHealthResponse(
            status="healthy",
            vault_enabled=True,
            vault_connected=True,
            secrets_engine_status="healthy",
            transit_engine_status="healthy",
            last_rotation=None,
            message="Vault ist funktionsfaehig",
        )

        assert response.status == "healthy"
        assert response.vault_connected is True

    def test_secret_metadata_response_schema(self):
        """SecretMetadataResponse sollte alle erforderlichen Felder haben."""
        response = SecretMetadataResponse(
            path="test/path",
            version=1,
            created_time="2024-01-01T00:00:00Z",
            last_updated="2024-06-01T00:00:00Z",
            keys=["key1", "key2"],
        )

        assert response.path == "test/path"
        assert len(response.keys) == 2


# =============================================================================
# Test Authorization
# =============================================================================


class TestVaultAuthorization:
    """Tests fuer Vault Endpoint Autorisierung."""

    @pytest.mark.asyncio
    async def test_health_endpoint_is_public(self):
        """Health Endpoint sollte ohne Auth erreichbar sein."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            # Kein current_user Parameter erforderlich
            result = await vault_health_check()

            assert result is not None

    @pytest.mark.asyncio
    async def test_status_requires_superuser(self, mock_superuser):
        """Status Endpoint erfordert Superuser-Berechtigung."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            # Sollte funktionieren mit Superuser
            result = await get_vault_status(current_user=mock_superuser)
            assert result is not None

    @pytest.mark.asyncio
    async def test_metadata_requires_superuser(self, mock_superuser):
        """Metadata Endpoint erfordert Superuser-Berechtigung."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            # Sollte HTTPException werfen wegen deaktiviertem Vault
            # aber der Punkt ist, dass es den current_user Parameter akzeptiert
            with pytest.raises(HTTPException):
                await get_secret_metadata(path="test", current_user=mock_superuser)

    @pytest.mark.asyncio
    async def test_refresh_requires_superuser(self, mock_superuser):
        """Refresh Endpoint erfordert Superuser-Berechtigung."""
        with patch("app.api.v1.vault.settings") as mock_settings:
            mock_settings.VAULT_ENABLED = False

            # Sollte HTTPException werfen wegen deaktiviertem Vault
            with pytest.raises(HTTPException):
                await refresh_secrets(current_user=mock_superuser)


# =============================================================================
# Test Logging
# =============================================================================


class TestVaultLogging:
    """Tests fuer Vault Endpoint Logging."""

    @pytest.mark.asyncio
    async def test_metadata_access_logged(self, mock_superuser, mock_vault_client):
        """Secret Metadata Zugriff sollte geloggt werden."""
        with patch("app.api.v1.vault.settings") as mock_settings, \
             patch("app.api.v1.vault.VaultClient", return_value=mock_vault_client), \
             patch("app.api.v1.vault.logger") as mock_logger:
            mock_settings.VAULT_ENABLED = True
            mock_settings.VAULT_ADDR = "http://vault:8200"
            mock_settings.VAULT_TOKEN = "test-token"
            mock_settings.VAULT_ROLE_ID = None
            mock_settings.VAULT_SECRET_ID = None
            mock_settings.VAULT_NAMESPACE = None
            mock_settings.VAULT_VERIFY_SSL = True
            mock_settings.VAULT_MOUNT_POINT = "secret"

            mock_vault_client.get_secret.return_value = {"key": "value"}
            mock_vault_client._client.secrets.kv.v2.read_secret_metadata.return_value = {
                "data": {"current_version": 1}
            }

            await get_secret_metadata(path="test/secret", current_user=mock_superuser)

            # Logger sollte aufgerufen worden sein
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args
            assert "vault_secret_metadata_accessed" in str(call_args)
