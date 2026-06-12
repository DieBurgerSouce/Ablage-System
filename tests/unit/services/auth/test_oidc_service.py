# -*- coding: utf-8 -*-
"""
Unit-Tests fuer OIDC Service.

Testet:
- PKCE Generierung (Code Verifier + Challenge S256)
- Authorization URL Konstruktion
- State Management (Speicherung, Ablauf, Replay-Schutz)
- Token Exchange (Erfolg, Fehler-Responses)
- ID Token Validierung (CWE-347 Fix: JWKS Key Matching!)
- Nonce Validierung
- UserInfo Abruf
- Claims Mapping
- Token Refresh
- Logout URL Generierung

KRITISCH: Test des CWE-347 Fixes (Zeilen 355-364):
Wenn kein JWKS Key passt, MUSS ein ValueError geworfen werden,
NICHT ohne Verifikation dekodieren!

Feinpoliert und durchdacht - Enterprise-grade OIDC Security Tests.
"""

import pytest
import base64
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

import httpx
# Sprint 0 / G02: PyJWT statt python-jose; jwk wurde nirgends benutzt - entfernt.
# KORREKTUR (2026-06-12): jwt WIRD direkt benutzt (create_test_id_token ->
# jwt.encode fuer die CWE-347-Tests) - Import war bei der Migration faelschlich
# mit entfernt worden (NameError: name 'jwt' is not defined).
import jwt
from pydantic import SecretStr

from app.services.auth.sso.oidc_service import (
    OIDCService,
    OIDCState,
    OIDCTokenResponse,
    OIDCUserInfo,
)
from app.services.auth.sso.sso_config_service import (
    SSOProviderConfig,
    SSOProviderType,
    SSOProviderPreset,
    OIDCConfig,
)


# ========================= Test Constants =========================


# RSA key pair for testing JWT signatures (2048-bit test key)
# NEVER use in production - test only!
# KORREKTUR (2026-06-12): Der frueher hier eingebettete PEM-Block war KEIN
# gueltiger RSA-Schluessel (fabrizierte Base64-Bloecke) - PyJWT/cryptography
# lehnen ihn mit InvalidKeyError ab (python-jose hatte das nie signiert,
# weil jwt.encode vorher nie real lief). Stattdessen wird zur Modul-Ladezeit
# ein ECHTES Schluesselpaar generiert und die JWKS-Parameter (n, e) daraus
# abgeleitet, damit Token-Erzeugung und Key-Matching konsistent sind.
from cryptography.hazmat.primitives import serialization as _serialization
from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

_TEST_RSA_KEY = _rsa.generate_private_key(public_exponent=65537, key_size=2048)

TEST_RSA_PRIVATE_KEY = _TEST_RSA_KEY.private_bytes(
    encoding=_serialization.Encoding.PEM,
    format=_serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=_serialization.NoEncryption(),
).decode()

TEST_RSA_PUBLIC_KEY = _TEST_RSA_KEY.public_key().public_bytes(
    encoding=_serialization.Encoding.PEM,
    format=_serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


def _b64url_uint(value: int) -> str:
    """Base64url-Encoding (ohne Padding) fuer JWK-Integer-Parameter."""
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


_TEST_RSA_PUBLIC_NUMBERS = _TEST_RSA_KEY.public_key().public_numbers()
TEST_JWK_N = _b64url_uint(_TEST_RSA_PUBLIC_NUMBERS.n)
TEST_JWK_E = _b64url_uint(_TEST_RSA_PUBLIC_NUMBERS.e)

TEST_KID = "test-key-id-001"
TEST_ISSUER = "https://idp.example.com"
TEST_CLIENT_ID = "test-client-id"


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session():
    """Create mock async database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.add = Mock()
    return session


@pytest.fixture
def sample_company_id() -> UUID:
    """Provide sample company ID."""
    return uuid4()


@pytest.fixture
def sample_provider_id() -> UUID:
    """Provide sample provider ID."""
    return uuid4()


@pytest.fixture
def sample_oidc_config() -> OIDCConfig:
    """Create sample OIDC configuration."""
    return OIDCConfig(
        client_id=TEST_CLIENT_ID,
        client_secret=SecretStr("encrypted_test_secret"),
        authorization_endpoint="https://idp.example.com/oauth2/authorize",
        token_endpoint="https://idp.example.com/oauth2/token",
        userinfo_endpoint="https://idp.example.com/oauth2/userinfo",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
        issuer=TEST_ISSUER,
        scopes=["openid", "profile", "email"],
        response_type="code",
        use_pkce=True,
        claims_mapping={
            "email": "email",
            "name": "name",
            "given_name": "given_name",
            "family_name": "family_name",
        },
    )


@pytest.fixture
def sample_provider_config(sample_provider_id, sample_company_id, sample_oidc_config) -> SSOProviderConfig:
    """Create sample SSO provider configuration."""
    return SSOProviderConfig(
        id=sample_provider_id,
        company_id=sample_company_id,
        name="Test OIDC Provider",
        provider_type=SSOProviderType.OIDC,
        preset=SSOProviderPreset.CUSTOM_OIDC,
        enabled=True,
        is_primary=True,
        oidc_config=sample_oidc_config,
        auto_create_users=True,
        default_role="viewer",
    )


@pytest.fixture
def sample_disabled_provider(sample_provider_id, sample_company_id, sample_oidc_config) -> SSOProviderConfig:
    """Create sample disabled SSO provider."""
    return SSOProviderConfig(
        id=sample_provider_id,
        company_id=sample_company_id,
        name="Disabled OIDC Provider",
        provider_type=SSOProviderType.OIDC,
        preset=SSOProviderPreset.CUSTOM_OIDC,
        enabled=False,
        oidc_config=sample_oidc_config,
    )


@pytest.fixture
def mock_state_manager():
    """Create mock SSOStateManager."""
    from unittest.mock import AsyncMock, MagicMock
    manager = MagicMock()
    manager.store_oidc_state = AsyncMock()
    manager.get_oidc_state = AsyncMock(return_value=None)
    manager.delete_oidc_state = AsyncMock(return_value=True)
    # In-memory state storage for test assertions
    manager._test_states = {}
    return manager


@pytest.fixture
def oidc_service(mock_db_session, mock_state_manager):
    """Create OIDC service instance with mocked dependencies."""
    service = OIDCService(mock_db_session, state_manager=mock_state_manager)
    return service


@pytest.fixture
def sample_jwks() -> Dict[str, Any]:
    """Create sample JWKS response with test key."""
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": TEST_KID,
                "use": "sig",
                "alg": "RS256",
                "n": TEST_JWK_N,
                "e": TEST_JWK_E,
            }
        ]
    }


@pytest.fixture
def sample_jwks_no_matching_key() -> Dict[str, Any]:
    """Create sample JWKS response without matching key."""
    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": "different-key-id",
                "use": "sig",
                "alg": "RS256",
                "n": TEST_JWK_N,
                "e": TEST_JWK_E,
            }
        ]
    }


@pytest.fixture
def sample_token_response() -> Dict[str, Any]:
    """Create sample token response from IdP."""
    return {
        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "test_refresh_token",
        "id_token": None,  # Will be set per test
        "scope": "openid profile email",
    }


@pytest.fixture
def sample_userinfo_response() -> Dict[str, Any]:
    """Create sample userinfo response."""
    return {
        "sub": "user-12345",
        "email": "test@example.com",
        "email_verified": True,
        "name": "Test Benutzer",
        "given_name": "Test",
        "family_name": "Benutzer",
        "preferred_username": "testuser",
        "picture": "https://example.com/avatar.jpg",
        "groups": ["employees", "developers"],
    }


def create_test_id_token(
    nonce: str,
    kid: "str | None" = TEST_KID,
    issuer: str = TEST_ISSUER,
    aud: str = TEST_CLIENT_ID,
    exp_delta: int = 3600,
) -> str:
    """Create a test ID token with specified parameters.

    kid=None erzeugt ein Token OHNE kid-Header (Single-Key-IdP-Szenario).
    """
    now = datetime.utcnow()
    claims = {
        "iss": issuer,
        "sub": "user-12345",
        "aud": aud,
        "exp": int((now + timedelta(seconds=exp_delta)).timestamp()),
        "iat": int(now.timestamp()),
        "nonce": nonce,
        "email": "test@example.com",
        "name": "Test Benutzer",
    }

    headers: Dict[str, Any] = {"alg": "RS256"}
    if kid is not None:
        headers["kid"] = kid

    # For testing, we create a properly signed token
    # In real tests, we mock the validation
    token = jwt.encode(claims, TEST_RSA_PRIVATE_KEY, algorithm="RS256", headers=headers)
    return token


# ========================= PKCE Generation Tests =========================


class TestPKCEGeneration:
    """Tests fuer PKCE Code Verifier und Challenge Generierung."""

    def test_code_verifier_length(self, oidc_service):
        """Test: Code Verifier hat korrekte Laenge (43-128 Zeichen)."""
        verifier = oidc_service._generate_code_verifier()

        assert len(verifier) >= 43
        assert len(verifier) <= 128

    def test_code_verifier_characters(self, oidc_service):
        """Test: Code Verifier enthaelt nur erlaubte Zeichen (RFC 7636)."""
        verifier = oidc_service._generate_code_verifier()

        # URL-safe base64 characters: A-Z, a-z, 0-9, -, _
        allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        for char in verifier:
            assert char in allowed_chars, f"Ungueltiges Zeichen im Verifier: {char}"

    def test_code_verifier_uniqueness(self, oidc_service):
        """Test: Jeder Code Verifier ist einzigartig."""
        verifiers = [oidc_service._generate_code_verifier() for _ in range(100)]

        # All verifiers should be unique
        assert len(set(verifiers)) == 100

    def test_code_challenge_s256_format(self, oidc_service):
        """Test: Code Challenge ist Base64-URL ohne Padding (S256)."""
        verifier = "test_verifier_for_challenge_generation"
        challenge = oidc_service._generate_code_challenge(verifier)

        # Challenge should be base64url encoded without padding
        assert "=" not in challenge
        assert "+" not in challenge
        assert "/" not in challenge

    def test_code_challenge_s256_correct_hash(self, oidc_service):
        """Test: Code Challenge verwendet SHA-256 Hash korrekt."""
        verifier = "test_verifier_abc123"
        challenge = oidc_service._generate_code_challenge(verifier)

        # Manually compute expected challenge
        expected_hash = hashlib.sha256(verifier.encode()).digest()
        expected_challenge = base64.urlsafe_b64encode(expected_hash).decode().rstrip("=")

        assert challenge == expected_challenge

    def test_code_challenge_deterministic(self, oidc_service):
        """Test: Gleicher Verifier ergibt gleiche Challenge."""
        verifier = "deterministic_test_verifier"

        challenge1 = oidc_service._generate_code_challenge(verifier)
        challenge2 = oidc_service._generate_code_challenge(verifier)

        assert challenge1 == challenge2

    def test_code_challenge_different_for_different_verifiers(self, oidc_service):
        """Test: Verschiedene Verifier ergeben verschiedene Challenges."""
        challenge1 = oidc_service._generate_code_challenge("verifier_one")
        challenge2 = oidc_service._generate_code_challenge("verifier_two")

        assert challenge1 != challenge2


# ========================= Authorization Flow Tests =========================


class TestStartAuthorization:
    """Tests fuer Authorization URL Generierung."""

    @pytest.mark.asyncio
    async def test_start_authorization_success(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Erfolgreiche Authorization URL Generierung."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            auth_url, state = await oidc_service.start_authorization(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                redirect_uri="https://app.example.com/callback",
            )

            assert "https://idp.example.com/oauth2/authorize" in auth_url
            assert f"client_id={TEST_CLIENT_ID}" in auth_url
            assert "response_type=code" in auth_url
            assert "scope=openid+profile+email" in auth_url or "scope=openid%20profile%20email" in auth_url
            assert "state=" in auth_url
            assert "nonce=" in auth_url
            assert "code_challenge=" in auth_url
            assert "code_challenge_method=S256" in auth_url
            assert len(state) > 0

    @pytest.mark.asyncio
    async def test_start_authorization_stores_state(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: State wird korrekt in StateManager gespeichert."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            _, state = await oidc_service.start_authorization(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                redirect_uri="https://app.example.com/callback",
            )

            # State should be stored via StateManager
            oidc_service.state_manager.store_oidc_state.assert_called_once()
            call_args = oidc_service.state_manager.store_oidc_state.call_args
            stored_state = call_args[0][1]  # Second positional arg is OIDCState
            assert call_args[0][0] == state  # First positional arg is state string
            assert stored_state.state == state
            assert stored_state.provider_id == sample_provider_id
            assert stored_state.redirect_uri == "https://app.example.com/callback"
            assert stored_state.code_verifier is not None  # PKCE enabled
            assert stored_state.nonce is not None

    @pytest.mark.asyncio
    async def test_start_authorization_provider_not_found(
        self,
        oidc_service,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Fehler wenn Provider nicht gefunden wird."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = None

            with pytest.raises(ValueError, match="nicht gefunden"):
                await oidc_service.start_authorization(
                    provider_id=sample_provider_id,
                    company_id=sample_company_id,
                    redirect_uri="https://app.example.com/callback",
                )

    @pytest.mark.asyncio
    async def test_start_authorization_provider_disabled(
        self,
        oidc_service,
        sample_disabled_provider,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Fehler wenn Provider deaktiviert ist."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_disabled_provider

            with pytest.raises(ValueError, match="deaktiviert"):
                await oidc_service.start_authorization(
                    provider_id=sample_provider_id,
                    company_id=sample_company_id,
                    redirect_uri="https://app.example.com/callback",
                )

    @pytest.mark.asyncio
    async def test_start_authorization_without_pkce(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Authorization ohne PKCE wenn deaktiviert."""
        sample_provider_config.oidc_config.use_pkce = False

        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            auth_url, state = await oidc_service.start_authorization(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                redirect_uri="https://app.example.com/callback",
            )

            assert "code_challenge=" not in auth_url
            assert "code_challenge_method=" not in auth_url
            # Verify state stored without code_verifier
            call_args = oidc_service.state_manager.store_oidc_state.call_args
            stored_state = call_args[0][1]
            assert stored_state.code_verifier is None

    @pytest.mark.asyncio
    async def test_start_authorization_additional_params(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Zusaetzliche Parameter werden angehaengt."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            auth_url, _ = await oidc_service.start_authorization(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                redirect_uri="https://app.example.com/callback",
                additional_params={"prompt": "consent", "login_hint": "test@example.com"},
            )

            assert "prompt=consent" in auth_url
            assert "login_hint=test" in auth_url or "login_hint=test%40example.com" in auth_url


# ========================= State Management Tests =========================


class TestStateManagement:
    """Tests fuer State Verwaltung."""

    def test_state_expiration(self, oidc_service):
        """Test: State hat korrekte Ablaufzeit (10 Minuten)."""
        state = OIDCState(
            state="test_state",
            nonce="test_nonce",
            provider_id=uuid4(),
            redirect_uri="https://app.example.com/callback",
        )

        # Default expiration should be ~10 minutes from creation
        expected_expiration = state.created_at + timedelta(minutes=10)
        delta = abs((state.expires_at - expected_expiration).total_seconds())

        assert delta < 2  # Allow 2 seconds tolerance

    @pytest.mark.asyncio
    async def test_state_consumed_on_callback(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: State wird bei Callback konsumiert (Replay-Schutz)."""
        # First, create a state
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            _, state = await oidc_service.start_authorization(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                redirect_uri="https://app.example.com/callback",
            )

        # State should be stored via StateManager
        oidc_service.state_manager.store_oidc_state.assert_called_once()
        stored_oidc_state = oidc_service.state_manager.store_oidc_state.call_args[0][1]

        # Configure get_oidc_state to return the stored state (simulating Redis)
        oidc_service.state_manager.get_oidc_state = AsyncMock(return_value=stored_oidc_state)

        # Now consume the state (simulate callback with mocked token exchange)
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider, patch.object(
            oidc_service, "_exchange_code", new_callable=AsyncMock
        ) as mock_exchange, patch.object(
            oidc_service, "_validate_id_token", new_callable=AsyncMock
        ) as mock_validate, patch.object(
            oidc_service, "_get_userinfo", new_callable=AsyncMock
        ) as mock_userinfo, patch.object(
            oidc_service.config_service, "record_login", new_callable=AsyncMock
        ) as mock_record:
            mock_get_provider.return_value = sample_provider_config
            mock_exchange.return_value = OIDCTokenResponse(
                access_token="test_access", token_type="Bearer"
            )
            mock_userinfo.return_value = OIDCUserInfo(sub="user-123")

            await oidc_service.handle_callback(
                code="test_code",
                state=state,
                company_id=sample_company_id,
            )

        # State should be retrieved with delete=True (consumed)
        oidc_service.state_manager.get_oidc_state.assert_called_once_with(state, delete=True)

    @pytest.mark.asyncio
    async def test_replay_attack_prevention(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Wiederverwendung von State wird abgelehnt."""
        # Create and consume a state
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            _, state = await oidc_service.start_authorization(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                redirect_uri="https://app.example.com/callback",
            )

        # One-Time-Use simulieren: erster Abruf liefert den gespeicherten
        # State (wie Redis mit delete=True), jeder weitere Abruf None.
        # Der Fixture-Default (immer None) liess schon den ERSTEN legitimen
        # Callback fehlschlagen - der Replay-Schutz wurde nie wirklich getestet.
        stored_oidc_state = oidc_service.state_manager.store_oidc_state.call_args[0][1]
        oidc_service.state_manager.get_oidc_state = AsyncMock(
            side_effect=[stored_oidc_state, None]
        )

        # Consume the state
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider, patch.object(
            oidc_service, "_exchange_code", new_callable=AsyncMock
        ) as mock_exchange, patch.object(
            oidc_service, "_get_userinfo", new_callable=AsyncMock
        ) as mock_userinfo, patch.object(
            oidc_service.config_service, "record_login", new_callable=AsyncMock
        ):
            mock_get_provider.return_value = sample_provider_config
            mock_exchange.return_value = OIDCTokenResponse(
                access_token="test_access", token_type="Bearer"
            )
            mock_userinfo.return_value = OIDCUserInfo(sub="user-123")

            await oidc_service.handle_callback(
                code="test_code",
                state=state,
                company_id=sample_company_id,
            )

        # Try to reuse the same state
        with pytest.raises(ValueError, match="Ungültiger oder abgelaufener State"):
            await oidc_service.handle_callback(
                code="test_code",
                state=state,
                company_id=sample_company_id,
            )

    @pytest.mark.asyncio
    async def test_invalid_state_rejected(self, oidc_service, sample_company_id):
        """Test: Unbekannter State wird abgelehnt."""
        with pytest.raises(ValueError, match="Ungültiger oder abgelaufener State"):
            await oidc_service.handle_callback(
                code="test_code",
                state="invalid_state_that_was_never_created",
                company_id=sample_company_id,
            )

    @pytest.mark.asyncio
    async def test_expired_state_rejected(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Abgelaufener State wird abgelehnt."""
        # Create a state with expired time
        expired_state = OIDCState(
            state="expired_state",
            nonce="test_nonce",
            provider_id=sample_provider_id,
            redirect_uri="https://app.example.com/callback",
            expires_at=datetime.utcnow() - timedelta(minutes=5),
        )
        # Mock StateManager to return expired state
        oidc_service.state_manager.get_oidc_state = AsyncMock(return_value=expired_state)

        with pytest.raises(ValueError, match="abgelaufen"):
            await oidc_service.handle_callback(
                code="test_code",
                state="expired_state",
                company_id=sample_company_id,
            )


# ========================= Token Exchange Tests =========================


class TestTokenExchange:
    """Tests fuer Token Exchange."""

    @pytest.mark.asyncio
    async def test_exchange_code_success(
        self,
        oidc_service,
        sample_oidc_config,
        sample_token_response,
    ):
        """Test: Erfolgreicher Token Exchange."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_token_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt:
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"

            tokens = await oidc_service._exchange_code(
                config=sample_oidc_config,
                code="authorization_code_123",
                redirect_uri="https://app.example.com/callback",
                code_verifier="test_verifier",
            )

            assert tokens.access_token == sample_token_response["access_token"]
            assert tokens.token_type == "Bearer"
            assert tokens.expires_in == 3600
            assert tokens.refresh_token == sample_token_response["refresh_token"]

    @pytest.mark.asyncio
    async def test_exchange_code_includes_verifier(
        self,
        oidc_service,
        sample_oidc_config,
        sample_token_response,
    ):
        """Test: PKCE Verifier wird im Token Request gesendet."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_token_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt:
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"

            await oidc_service._exchange_code(
                config=sample_oidc_config,
                code="authorization_code_123",
                redirect_uri="https://app.example.com/callback",
                code_verifier="pkce_verifier_abc123",
            )

            # Check that code_verifier was sent
            call_kwargs = mock_client.post.call_args
            assert call_kwargs[1]["data"]["code_verifier"] == "pkce_verifier_abc123"

    @pytest.mark.asyncio
    async def test_exchange_code_http_error(
        self,
        oidc_service,
        sample_oidc_config,
    ):
        """Test: HTTP-Fehler beim Token Exchange."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = '{"error": "invalid_grant", "error_description": "Code expired"}'

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt:
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"

            with pytest.raises(ValueError, match="Token-Austausch fehlgeschlagen"):
                await oidc_service._exchange_code(
                    config=sample_oidc_config,
                    code="expired_code",
                    redirect_uri="https://app.example.com/callback",
                    code_verifier=None,
                )

    @pytest.mark.asyncio
    async def test_exchange_code_server_error(
        self,
        oidc_service,
        sample_oidc_config,
    ):
        """Test: Server-Fehler beim Token Exchange."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt:
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"

            with pytest.raises(ValueError, match="500"):
                await oidc_service._exchange_code(
                    config=sample_oidc_config,
                    code="test_code",
                    redirect_uri="https://app.example.com/callback",
                    code_verifier=None,
                )


# ========================= JWKS Caching Tests =========================


class TestJWKSCaching:
    """Tests fuer JWKS Caching."""

    @pytest.mark.asyncio
    async def test_jwks_fetched_on_first_request(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: JWKS wird beim ersten Request geholt."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_jwks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = mock_client

            jwks = await oidc_service._get_jwks(sample_oidc_config)

            assert jwks == sample_jwks
            mock_client.get.assert_called_once_with(sample_oidc_config.jwks_uri)

    @pytest.mark.asyncio
    async def test_jwks_cached(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: JWKS wird gecached (1 Stunde TTL)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_jwks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = mock_client

            # First request
            await oidc_service._get_jwks(sample_oidc_config)

            # Second request should use cache
            await oidc_service._get_jwks(sample_oidc_config)

            # Only one HTTP call
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_jwks_cache_expired(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: Cache wird nach 1 Stunde erneuert."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_jwks

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = mock_client

            # First request
            await oidc_service._get_jwks(sample_oidc_config)

            # Expire the cache
            cache_key = sample_oidc_config.jwks_uri
            oidc_service._jwks_cache_time[cache_key] = datetime.utcnow() - timedelta(hours=2)

            # Second request should fetch again
            await oidc_service._get_jwks(sample_oidc_config)

            # Two HTTP calls
            assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_jwks_no_uri_returns_empty(
        self,
        oidc_service,
        sample_oidc_config,
    ):
        """Test: Keine JWKS-URI gibt leeres Dict zurueck."""
        sample_oidc_config.jwks_uri = None

        jwks = await oidc_service._get_jwks(sample_oidc_config)

        assert jwks == {}

    @pytest.mark.asyncio
    async def test_jwks_fetch_failure_returns_cached(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: Bei Fetch-Fehler wird Cache zurueckgegeben."""
        # First, populate cache
        oidc_service._jwks_cache[sample_oidc_config.jwks_uri] = sample_jwks
        oidc_service._jwks_cache_time[sample_oidc_config.jwks_uri] = datetime.utcnow() - timedelta(hours=2)

        mock_response = Mock()
        mock_response.status_code = 500

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = mock_client

            jwks = await oidc_service._get_jwks(sample_oidc_config)

            # Should return cached value
            assert jwks == sample_jwks


# ========================= ID Token Validation Tests (CRITICAL: CWE-347) =========================


class TestIDTokenValidation:
    """
    Tests fuer ID Token Validierung.

    KRITISCH: Diese Tests pruefen den CWE-347 Fix!
    Wenn kein JWKS Key passt, MUSS ein ValueError geworfen werden.
    """

    @pytest.mark.asyncio
    async def test_validate_id_token_success(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: Erfolgreiche ID Token Validierung mit passendem Key."""
        nonce = "test_nonce_123"

        with patch.object(
            oidc_service, "_get_jwks", new_callable=AsyncMock
        ) as mock_get_jwks, patch(
            "app.services.auth.sso.oidc_service.jwt.decode"
        ) as mock_decode:
            mock_get_jwks.return_value = sample_jwks
            mock_decode.return_value = {
                "sub": "user-12345",
                "email": "test@example.com",
                "nonce": nonce,
            }

            # Create token with matching kid
            id_token = create_test_id_token(nonce=nonce, kid=TEST_KID)

            claims = await oidc_service._validate_id_token(
                config=sample_oidc_config,
                id_token=id_token,
                nonce=nonce,
            )

            assert claims["sub"] == "user-12345"
            assert claims["nonce"] == nonce

    @pytest.mark.asyncio
    async def test_validate_id_token_no_matching_key_cwe347_fix(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks_no_matching_key,
    ):
        """
        KRITISCHER TEST: CWE-347 Fix Validierung.

        Wenn kein JWKS Key zum kid im Token passt,
        MUSS ein ValueError geworfen werden.
        Das Token darf NICHT ohne Verifikation dekodiert werden!
        """
        nonce = "test_nonce_123"

        with patch.object(
            oidc_service, "_get_jwks", new_callable=AsyncMock
        ) as mock_get_jwks:
            mock_get_jwks.return_value = sample_jwks_no_matching_key

            # Create token with kid that doesn't match any key in JWKS
            id_token = create_test_id_token(nonce=nonce, kid="non-existent-key-id")

            with pytest.raises(ValueError, match="Kein passender JWKS"):
                await oidc_service._validate_id_token(
                    config=sample_oidc_config,
                    id_token=id_token,
                    nonce=nonce,
                )

    @pytest.mark.asyncio
    async def test_validate_id_token_empty_jwks_cwe347_fix(
        self,
        oidc_service,
        sample_oidc_config,
    ):
        """
        KRITISCHER TEST: CWE-347 Fix bei leerem JWKS.

        Leeres JWKS bedeutet keine Keys vorhanden.
        Token MUSS abgelehnt werden!
        """
        nonce = "test_nonce_123"

        with patch.object(
            oidc_service, "_get_jwks", new_callable=AsyncMock
        ) as mock_get_jwks:
            mock_get_jwks.return_value = {"keys": []}

            id_token = create_test_id_token(nonce=nonce)

            with pytest.raises(ValueError, match="Kein passender JWKS"):
                await oidc_service._validate_id_token(
                    config=sample_oidc_config,
                    id_token=id_token,
                    nonce=nonce,
                )

    @pytest.mark.asyncio
    async def test_validate_id_token_no_jwks_cwe347_fix(
        self,
        oidc_service,
        sample_oidc_config,
    ):
        """
        KRITISCHER TEST: CWE-347 Fix ohne JWKS.

        Kein JWKS = keine Validierung moeglich.
        Token MUSS abgelehnt werden!
        """
        nonce = "test_nonce_123"

        with patch.object(
            oidc_service, "_get_jwks", new_callable=AsyncMock
        ) as mock_get_jwks:
            mock_get_jwks.return_value = {}  # No JWKS at all

            id_token = create_test_id_token(nonce=nonce)

            with pytest.raises(ValueError, match="Kein passender JWKS"):
                await oidc_service._validate_id_token(
                    config=sample_oidc_config,
                    id_token=id_token,
                    nonce=nonce,
                )

    @pytest.mark.asyncio
    async def test_validate_id_token_nonce_mismatch(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: Nonce-Mismatch wird abgelehnt."""
        with patch.object(
            oidc_service, "_get_jwks", new_callable=AsyncMock
        ) as mock_get_jwks, patch(
            "app.services.auth.sso.oidc_service.jwt.decode"
        ) as mock_decode:
            mock_get_jwks.return_value = sample_jwks
            mock_decode.return_value = {
                "sub": "user-12345",
                "nonce": "wrong_nonce",
            }

            id_token = create_test_id_token(nonce="original_nonce", kid=TEST_KID)

            with pytest.raises(ValueError, match="Nonce stimmt nicht"):
                await oidc_service._validate_id_token(
                    config=sample_oidc_config,
                    id_token=id_token,
                    nonce="expected_nonce",
                )

    @pytest.mark.asyncio
    async def test_validate_id_token_jwt_error(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: JWT-Validierungsfehler wird korrekt behandelt."""
        # Sprint 0 / G02: PyJWT statt python-jose
        from jwt.exceptions import InvalidTokenError as JWTError

        with patch.object(
            oidc_service, "_get_jwks", new_callable=AsyncMock
        ) as mock_get_jwks, patch(
            "app.services.auth.sso.oidc_service.jwt.decode"
        ) as mock_decode:
            mock_get_jwks.return_value = sample_jwks
            mock_decode.side_effect = JWTError("Signature verification failed")

            id_token = create_test_id_token(nonce="test_nonce", kid=TEST_KID)

            with pytest.raises(ValueError, match="ID Token Validierung fehlgeschlagen"):
                await oidc_service._validate_id_token(
                    config=sample_oidc_config,
                    id_token=id_token,
                    nonce="test_nonce",
                )

    @pytest.mark.asyncio
    async def test_validate_id_token_fallback_to_first_key(
        self,
        oidc_service,
        sample_oidc_config,
        sample_jwks,
    ):
        """Test: Fallback auf ersten Key, wenn das Token KEINEN kid-Header hat.

        ANGEPASST (2026-06-12): Frueher testete dieser Test den Fallback bei
        UNBEKANNTEM kid - das widersprach direkt dem CWE-347-Test
        (test_validate_id_token_no_matching_key_cwe347_fix). App-Verhalten ist
        jetzt: Fallback nur ohne kid-Header; unbekannter kid => harter Fehler.
        """
        nonce = "test_nonce_123"

        with patch.object(
            oidc_service, "_get_jwks", new_callable=AsyncMock
        ) as mock_get_jwks, patch(
            "app.services.auth.sso.oidc_service.jwt.decode"
        ) as mock_decode:
            mock_get_jwks.return_value = sample_jwks
            mock_decode.return_value = {
                "sub": "user-12345",
                "nonce": nonce,
            }

            # Token ohne kid-Header (Single-Key-IdP), JWKS hat mindestens
            # einen Key -> Code faellt auf den ersten Key zurueck
            id_token = create_test_id_token(nonce=nonce, kid=None)

            claims = await oidc_service._validate_id_token(
                config=sample_oidc_config,
                id_token=id_token,
                nonce=nonce,
            )

            assert claims["sub"] == "user-12345"


# ========================= UserInfo Tests =========================


class TestGetUserInfo:
    """Tests fuer UserInfo Abruf."""

    @pytest.mark.asyncio
    async def test_get_userinfo_success(
        self,
        oidc_service,
        sample_oidc_config,
        sample_userinfo_response,
    ):
        """Test: Erfolgreicher UserInfo Abruf."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_userinfo_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = mock_client

            user_info = await oidc_service._get_userinfo(
                config=sample_oidc_config,
                access_token="test_access_token",
            )

            assert user_info.sub == "user-12345"
            assert user_info.email == "test@example.com"
            assert user_info.email_verified is True
            assert user_info.name == "Test Benutzer"
            assert user_info.given_name == "Test"
            assert user_info.family_name == "Benutzer"
            assert user_info.groups == ["employees", "developers"]

    @pytest.mark.asyncio
    async def test_get_userinfo_sends_bearer_token(
        self,
        oidc_service,
        sample_oidc_config,
        sample_userinfo_response,
    ):
        """Test: Access Token wird als Bearer Token gesendet."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_userinfo_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = mock_client

            await oidc_service._get_userinfo(
                config=sample_oidc_config,
                access_token="my_access_token",
            )

            call_kwargs = mock_client.get.call_args
            assert call_kwargs[1]["headers"]["Authorization"] == "Bearer my_access_token"

    @pytest.mark.asyncio
    async def test_get_userinfo_failure_returns_unknown(
        self,
        oidc_service,
        sample_oidc_config,
    ):
        """Test: Bei Fehler wird unknown User zurueckgegeben."""
        mock_response = Mock()
        mock_response.status_code = 401

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client:
            mock_get_client.return_value = mock_client

            user_info = await oidc_service._get_userinfo(
                config=sample_oidc_config,
                access_token="invalid_token",
            )

            assert user_info.sub == "unknown"

    @pytest.mark.asyncio
    async def test_get_userinfo_no_endpoint(
        self,
        oidc_service,
        sample_oidc_config,
    ):
        """Test: Ohne UserInfo Endpoint wird unknown zurueckgegeben."""
        sample_oidc_config.userinfo_endpoint = None

        user_info = await oidc_service._get_userinfo(
            config=sample_oidc_config,
            access_token="any_token",
        )

        assert user_info.sub == "unknown"


# ========================= Claims Mapping Tests =========================


class TestClaimsMapping:
    """Tests fuer Claims Mapping."""

    def test_apply_claims_mapping_basic(self, oidc_service):
        """Test: Basis Claims Mapping funktioniert."""
        user_info = OIDCUserInfo(
            sub="user-123",
            raw_claims={
                "email": "original@example.com",
                "custom_email": "custom@example.com",
                "custom_name": "Custom Name",
            },
        )

        mapping = {
            "email": "custom_email",
            "name": "custom_name",
        }

        result = oidc_service._apply_claims_mapping(user_info, mapping)

        assert result.email == "custom@example.com"
        assert result.name == "Custom Name"

    def test_apply_claims_mapping_missing_source(self, oidc_service):
        """Test: Fehlendes Source-Claim wird ignoriert."""
        user_info = OIDCUserInfo(
            sub="user-123",
            email="original@example.com",
            raw_claims={
                "email": "original@example.com",
            },
        )

        mapping = {
            "email": "non_existent_claim",  # Doesn't exist in raw_claims
        }

        result = oidc_service._apply_claims_mapping(user_info, mapping)

        # Should keep original value
        assert result.email == "original@example.com"

    def test_apply_claims_mapping_invalid_target(self, oidc_service):
        """Test: Ungueltiges Target-Attribut wird ignoriert."""
        user_info = OIDCUserInfo(
            sub="user-123",
            raw_claims={
                "some_claim": "some_value",
            },
        )

        mapping = {
            "invalid_attribute": "some_claim",  # Not a valid OIDCUserInfo attribute
        }

        result = oidc_service._apply_claims_mapping(user_info, mapping)

        # Should not raise, just ignore
        assert result.sub == "user-123"

    def test_apply_claims_mapping_empty_mapping(self, oidc_service):
        """Test: Leeres Mapping aendert nichts."""
        user_info = OIDCUserInfo(
            sub="user-123",
            email="original@example.com",
            name="Original Name",
            raw_claims={},
        )

        result = oidc_service._apply_claims_mapping(user_info, {})

        assert result.email == "original@example.com"
        assert result.name == "Original Name"


# ========================= Token Refresh Tests =========================


class TestTokenRefresh:
    """Tests fuer Token Refresh."""

    @pytest.mark.asyncio
    async def test_refresh_token_success(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Erfolgreicher Token Refresh."""
        new_token_response = {
            "access_token": "new_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "new_refresh_token",
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = new_token_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider, patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt:
            mock_get_provider.return_value = sample_provider_config
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"

            tokens = await oidc_service.refresh_token(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                refresh_token="old_refresh_token",
            )

            assert tokens.access_token == "new_access_token"
            assert tokens.refresh_token == "new_refresh_token"

    @pytest.mark.asyncio
    async def test_refresh_token_sends_correct_data(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Refresh Request enthaelt korrekte Daten."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"access_token": "new", "token_type": "Bearer"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider, patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt:
            mock_get_provider.return_value = sample_provider_config
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"

            await oidc_service.refresh_token(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                refresh_token="the_refresh_token",
            )

            call_kwargs = mock_client.post.call_args
            data = call_kwargs[1]["data"]
            assert data["grant_type"] == "refresh_token"
            assert data["refresh_token"] == "the_refresh_token"
            assert data["client_id"] == TEST_CLIENT_ID

    @pytest.mark.asyncio
    async def test_refresh_token_provider_not_found(
        self,
        oidc_service,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Fehler wenn Provider nicht gefunden."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = None

            with pytest.raises(ValueError, match="Provider nicht gefunden"):
                await oidc_service.refresh_token(
                    provider_id=sample_provider_id,
                    company_id=sample_company_id,
                    refresh_token="some_token",
                )

    @pytest.mark.asyncio
    async def test_refresh_token_http_error(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: HTTP-Fehler beim Refresh."""
        mock_response = Mock()
        mock_response.status_code = 400

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider, patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt:
            mock_get_provider.return_value = sample_provider_config
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"

            with pytest.raises(ValueError, match="Token-Refresh fehlgeschlagen"):
                await oidc_service.refresh_token(
                    provider_id=sample_provider_id,
                    company_id=sample_company_id,
                    refresh_token="invalid_token",
                )


# ========================= Logout URL Tests =========================


class TestLogoutURL:
    """Tests fuer Logout URL Generierung."""

    @pytest.mark.asyncio
    async def test_logout_url_basic(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Basis Logout URL wird generiert."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            logout_url = await oidc_service.logout_url(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
            )

            assert "logout" in logout_url
            assert "idp.example.com" in logout_url

    @pytest.mark.asyncio
    async def test_logout_url_with_id_token_hint(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Logout URL mit id_token_hint."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            logout_url = await oidc_service.logout_url(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                id_token_hint="some_id_token",
            )

            assert "id_token_hint=some_id_token" in logout_url

    @pytest.mark.asyncio
    async def test_logout_url_with_redirect(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: Logout URL mit post_logout_redirect_uri."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            logout_url = await oidc_service.logout_url(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                post_logout_redirect_uri="https://app.example.com/logged-out",
            )

            assert "post_logout_redirect_uri=" in logout_url

    @pytest.mark.asyncio
    async def test_logout_url_provider_not_found(
        self,
        oidc_service,
        sample_company_id,
        sample_provider_id,
    ):
        """Test: None wenn Provider nicht gefunden."""
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = None

            logout_url = await oidc_service.logout_url(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
            )

            assert logout_url is None


# ========================= HTTP Client Tests =========================


class TestHTTPClient:
    """Tests fuer HTTP Client Management."""

    @pytest.mark.asyncio
    async def test_http_client_lazy_init(self, oidc_service):
        """Test: HTTP Client wird lazy initialisiert."""
        assert oidc_service._http_client is None

        client = await oidc_service._get_http_client()

        assert client is not None
        assert oidc_service._http_client is client

    @pytest.mark.asyncio
    async def test_http_client_reused(self, oidc_service):
        """Test: HTTP Client wird wiederverwendet."""
        client1 = await oidc_service._get_http_client()
        client2 = await oidc_service._get_http_client()

        assert client1 is client2

    @pytest.mark.asyncio
    async def test_close_clears_client(self, oidc_service):
        """Test: Close setzt Client auf None."""
        # Initialize client
        await oidc_service._get_http_client()
        assert oidc_service._http_client is not None

        # Close
        await oidc_service.close()

        assert oidc_service._http_client is None


# ========================= Full Flow Integration Tests =========================


class TestFullAuthorizationFlow:
    """Integration Tests fuer vollstaendigen Authorization Flow."""

    @pytest.mark.asyncio
    async def test_complete_authorization_callback_flow(
        self,
        oidc_service,
        sample_provider_config,
        sample_company_id,
        sample_provider_id,
        sample_token_response,
        sample_userinfo_response,
        sample_jwks,
    ):
        """Test: Vollstaendiger Flow von Authorization bis UserInfo."""
        # Step 1: Start Authorization
        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider:
            mock_get_provider.return_value = sample_provider_config

            auth_url, state = await oidc_service.start_authorization(
                provider_id=sample_provider_id,
                company_id=sample_company_id,
                redirect_uri="https://app.example.com/callback",
            )

        # Verify state was stored via StateManager
        oidc_service.state_manager.store_oidc_state.assert_called_once()
        stored_state = oidc_service.state_manager.store_oidc_state.call_args[0][1]
        nonce = stored_state.nonce

        # Configure StateManager to return the stored state for callback
        oidc_service.state_manager.get_oidc_state = AsyncMock(return_value=stored_state)

        # Step 2: Handle Callback
        sample_token_response["id_token"] = create_test_id_token(
            nonce=nonce, kid=TEST_KID
        )

        mock_token_response = Mock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = sample_token_response

        mock_userinfo_response_http = Mock()
        mock_userinfo_response_http.status_code = 200
        mock_userinfo_response_http.json.return_value = sample_userinfo_response

        mock_jwks_response = Mock()
        mock_jwks_response.status_code = 200
        mock_jwks_response.json.return_value = sample_jwks

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_token_response)
        mock_client.get = AsyncMock(
            side_effect=[mock_jwks_response, mock_userinfo_response_http]
        )

        with patch.object(
            oidc_service.config_service, "get_provider", new_callable=AsyncMock
        ) as mock_get_provider, patch.object(
            oidc_service, "_get_http_client", new_callable=AsyncMock
        ) as mock_get_client, patch.object(
            oidc_service.config_service, "_decrypt_secret"
        ) as mock_decrypt, patch.object(
            oidc_service.config_service, "record_login", new_callable=AsyncMock
        ) as mock_record, patch(
            "app.services.auth.sso.oidc_service.jwt.decode"
        ) as mock_jwt_decode:
            mock_get_provider.return_value = sample_provider_config
            mock_get_client.return_value = mock_client
            mock_decrypt.return_value = "decrypted_secret"
            mock_jwt_decode.return_value = {
                "sub": "user-12345",
                "nonce": nonce,
                "email": "test@example.com",
            }

            user_info, tokens = await oidc_service.handle_callback(
                code="authorization_code",
                state=state,
                company_id=sample_company_id,
            )

            # Verify results
            assert user_info.sub == "user-12345"
            assert user_info.email == "test@example.com"
            assert tokens.access_token == sample_token_response["access_token"]

            # State should be consumed via StateManager (called with delete=True)
            oidc_service.state_manager.get_oidc_state.assert_called_once_with(state, delete=True)

            # Login should be recorded
            mock_record.assert_called_once()
