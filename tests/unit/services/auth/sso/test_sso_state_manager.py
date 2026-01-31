# -*- coding: utf-8 -*-
"""
Unit tests for SSO State Manager.

Tests fuer:
- OIDC State Storage/Retrieval/Deletion
- SAML Request Storage/Retrieval/Deletion
- Redis Integration
- In-Memory Fallback
- TTL und Expiration
- One-time-use (delete after get)
- Cleanup und Statistiken

Feinpoliert und durchdacht - Enterprise SSO State Management.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.auth.sso.sso_state_manager import (
    SSOStateManager,
    STATE_TTL_SECONDS,
    OIDC_STATE_PREFIX,
    SAML_REQUEST_PREFIX,
    get_sso_state_manager,
    cleanup_sso_states,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_redis():
    """Erstellt einen Mock Redis Client."""
    redis = AsyncMock()
    redis.setex = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.getdel = AsyncMock(return_value=None)
    redis.delete = AsyncMock(return_value=1)
    redis.scan_iter = MagicMock(return_value=iter([]))
    return redis


@pytest.fixture
def state_manager_redis(mock_redis):
    """SSO State Manager mit Redis."""
    return SSOStateManager(redis_client=mock_redis)


@pytest.fixture
def state_manager_fallback():
    """SSO State Manager ohne Redis (In-Memory Fallback)."""
    return SSOStateManager(redis_client=None)


@pytest.fixture
def sample_oidc_state():
    """Beispiel OIDC State fuer Tests."""
    from app.services.auth.sso.oidc_service import OIDCState

    return OIDCState(
        state="test_state_abc123",
        nonce="test_nonce_xyz789",
        code_verifier="test_code_verifier_pkce",
        provider_id=uuid4(),
        redirect_uri="https://app.example.com/callback",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )


@pytest.fixture
def sample_saml_request():
    """Beispiel SAML Request fuer Tests."""
    from app.services.auth.sso.saml_service import SAMLRequest

    return SAMLRequest(
        request_id="_id" + uuid4().hex,
        provider_id=uuid4(),
        relay_state="https://app.example.com/dashboard",
        created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(minutes=10),
    )


# =============================================================================
# Initialization Tests
# =============================================================================


class TestSSOStateManagerInit:
    """Tests fuer Initialisierung."""

    def test_init_with_redis(self, mock_redis):
        """Initialisierung mit Redis Client."""
        manager = SSOStateManager(redis_client=mock_redis)

        assert manager._redis is mock_redis
        assert manager._using_fallback is False

    def test_init_without_redis_uses_fallback(self):
        """Initialisierung ohne Redis aktiviert Fallback."""
        manager = SSOStateManager(redis_client=None)

        assert manager._redis is None
        assert manager._using_fallback is True
        assert manager._fallback_storage == {}

    def test_is_using_fallback_property(self):
        """Property is_using_fallback funktioniert korrekt."""
        manager_redis = SSOStateManager(redis_client=AsyncMock())
        manager_fallback = SSOStateManager(redis_client=None)

        assert manager_redis.is_using_fallback is False
        assert manager_fallback.is_using_fallback is True


# =============================================================================
# OIDC State - Redis Tests
# =============================================================================


class TestOIDCStateRedis:
    """Tests fuer OIDC State mit Redis."""

    @pytest.mark.asyncio
    async def test_store_oidc_state_redis(
        self, state_manager_redis, sample_oidc_state, mock_redis
    ):
        """OIDC State wird in Redis gespeichert."""
        await state_manager_redis.store_oidc_state(
            state="test_state",
            data=sample_oidc_state,
            ttl=600,
        )

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == f"{OIDC_STATE_PREFIX}test_state"
        assert call_args[0][1] == 600
        # Verify JSON is valid
        json.loads(call_args[0][2])

    @pytest.mark.asyncio
    async def test_get_oidc_state_redis_with_delete(
        self, state_manager_redis, sample_oidc_state, mock_redis
    ):
        """OIDC State wird aus Redis geholt und geloescht."""
        mock_redis.getdel = AsyncMock(
            return_value=sample_oidc_state.model_dump_json()
        )

        result = await state_manager_redis.get_oidc_state(
            state="test_state",
            delete=True,
        )

        mock_redis.getdel.assert_called_once_with(
            f"{OIDC_STATE_PREFIX}test_state"
        )
        assert result is not None
        assert result.state == sample_oidc_state.state
        assert result.nonce == sample_oidc_state.nonce

    @pytest.mark.asyncio
    async def test_get_oidc_state_redis_without_delete(
        self, state_manager_redis, sample_oidc_state, mock_redis
    ):
        """OIDC State wird aus Redis geholt ohne Loeschung."""
        mock_redis.get = AsyncMock(
            return_value=sample_oidc_state.model_dump_json()
        )

        result = await state_manager_redis.get_oidc_state(
            state="test_state",
            delete=False,
        )

        mock_redis.get.assert_called_once_with(f"{OIDC_STATE_PREFIX}test_state")
        mock_redis.getdel.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_oidc_state_not_found_redis(
        self, state_manager_redis, mock_redis
    ):
        """OIDC State nicht gefunden gibt None zurueck."""
        mock_redis.getdel = AsyncMock(return_value=None)

        result = await state_manager_redis.get_oidc_state(
            state="nonexistent",
            delete=True,
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_oidc_state_redis(
        self, state_manager_redis, mock_redis
    ):
        """OIDC State wird explizit aus Redis geloescht."""
        mock_redis.delete = AsyncMock(return_value=1)

        result = await state_manager_redis.delete_oidc_state(state="test_state")

        mock_redis.delete.assert_called_once_with(
            f"{OIDC_STATE_PREFIX}test_state"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_oidc_state_not_found_redis(
        self, state_manager_redis, mock_redis
    ):
        """Loeschen von nicht existierendem OIDC State gibt False zurueck."""
        mock_redis.delete = AsyncMock(return_value=0)

        result = await state_manager_redis.delete_oidc_state(
            state="nonexistent"
        )

        assert result is False


# =============================================================================
# SAML Request - Redis Tests
# =============================================================================


class TestSAMLRequestRedis:
    """Tests fuer SAML Request mit Redis."""

    @pytest.mark.asyncio
    async def test_store_saml_request_redis(
        self, state_manager_redis, sample_saml_request, mock_redis
    ):
        """SAML Request wird in Redis gespeichert."""
        await state_manager_redis.store_saml_request(
            request_id="test_request_id",
            data=sample_saml_request,
            ttl=600,
        )

        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == f"{SAML_REQUEST_PREFIX}test_request_id"
        assert call_args[0][1] == 600

    @pytest.mark.asyncio
    async def test_get_saml_request_redis_with_delete(
        self, state_manager_redis, sample_saml_request, mock_redis
    ):
        """SAML Request wird aus Redis geholt und geloescht."""
        mock_redis.getdel = AsyncMock(
            return_value=sample_saml_request.model_dump_json()
        )

        result = await state_manager_redis.get_saml_request(
            request_id="test_request_id",
            delete=True,
        )

        mock_redis.getdel.assert_called_once_with(
            f"{SAML_REQUEST_PREFIX}test_request_id"
        )
        assert result is not None
        assert result.request_id == sample_saml_request.request_id

    @pytest.mark.asyncio
    async def test_get_saml_request_redis_without_delete(
        self, state_manager_redis, sample_saml_request, mock_redis
    ):
        """SAML Request wird aus Redis geholt ohne Loeschung."""
        mock_redis.get = AsyncMock(
            return_value=sample_saml_request.model_dump_json()
        )

        result = await state_manager_redis.get_saml_request(
            request_id="test_request_id",
            delete=False,
        )

        mock_redis.get.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_saml_request_redis(
        self, state_manager_redis, mock_redis
    ):
        """SAML Request wird explizit aus Redis geloescht."""
        mock_redis.delete = AsyncMock(return_value=1)

        result = await state_manager_redis.delete_saml_request(
            request_id="test_request_id"
        )

        assert result is True


# =============================================================================
# OIDC State - In-Memory Fallback Tests
# =============================================================================


class TestOIDCStateFallback:
    """Tests fuer OIDC State mit In-Memory Fallback."""

    @pytest.mark.asyncio
    async def test_store_oidc_state_fallback(
        self, state_manager_fallback, sample_oidc_state
    ):
        """OIDC State wird im Fallback-Speicher gespeichert."""
        await state_manager_fallback.store_oidc_state(
            state="test_state",
            data=sample_oidc_state,
            ttl=600,
        )

        key = f"{OIDC_STATE_PREFIX}test_state"
        assert key in state_manager_fallback._fallback_storage
        json_data, expires_at = state_manager_fallback._fallback_storage[key]
        assert json_data == sample_oidc_state.model_dump_json()
        assert expires_at > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_get_oidc_state_fallback_with_delete(
        self, state_manager_fallback, sample_oidc_state
    ):
        """OIDC State wird aus Fallback geholt und geloescht."""
        await state_manager_fallback.store_oidc_state(
            state="test_state",
            data=sample_oidc_state,
        )

        result = await state_manager_fallback.get_oidc_state(
            state="test_state",
            delete=True,
        )

        assert result is not None
        assert result.state == sample_oidc_state.state
        # Sollte geloescht sein
        key = f"{OIDC_STATE_PREFIX}test_state"
        assert key not in state_manager_fallback._fallback_storage

    @pytest.mark.asyncio
    async def test_get_oidc_state_fallback_without_delete(
        self, state_manager_fallback, sample_oidc_state
    ):
        """OIDC State wird aus Fallback geholt ohne Loeschung."""
        await state_manager_fallback.store_oidc_state(
            state="test_state",
            data=sample_oidc_state,
        )

        result = await state_manager_fallback.get_oidc_state(
            state="test_state",
            delete=False,
        )

        assert result is not None
        # Sollte noch vorhanden sein
        key = f"{OIDC_STATE_PREFIX}test_state"
        assert key in state_manager_fallback._fallback_storage

    @pytest.mark.asyncio
    async def test_get_oidc_state_fallback_expired(
        self, state_manager_fallback, sample_oidc_state
    ):
        """Abgelaufener OIDC State im Fallback gibt None zurueck."""
        key = f"{OIDC_STATE_PREFIX}expired_state"
        expired_at = datetime.utcnow() - timedelta(seconds=1)
        state_manager_fallback._fallback_storage[key] = (
            sample_oidc_state.model_dump_json(),
            expired_at,
        )

        result = await state_manager_fallback.get_oidc_state(
            state="expired_state",
            delete=True,
        )

        assert result is None
        # Abgelaufener Eintrag sollte geloescht sein
        assert key not in state_manager_fallback._fallback_storage

    @pytest.mark.asyncio
    async def test_delete_oidc_state_fallback(
        self, state_manager_fallback, sample_oidc_state
    ):
        """OIDC State wird explizit aus Fallback geloescht."""
        await state_manager_fallback.store_oidc_state(
            state="test_state",
            data=sample_oidc_state,
        )

        result = await state_manager_fallback.delete_oidc_state(
            state="test_state"
        )

        assert result is True
        key = f"{OIDC_STATE_PREFIX}test_state"
        assert key not in state_manager_fallback._fallback_storage


# =============================================================================
# SAML Request - In-Memory Fallback Tests
# =============================================================================


class TestSAMLRequestFallback:
    """Tests fuer SAML Request mit In-Memory Fallback."""

    @pytest.mark.asyncio
    async def test_store_saml_request_fallback(
        self, state_manager_fallback, sample_saml_request
    ):
        """SAML Request wird im Fallback-Speicher gespeichert."""
        await state_manager_fallback.store_saml_request(
            request_id="test_request",
            data=sample_saml_request,
            ttl=600,
        )

        key = f"{SAML_REQUEST_PREFIX}test_request"
        assert key in state_manager_fallback._fallback_storage

    @pytest.mark.asyncio
    async def test_get_saml_request_fallback_with_delete(
        self, state_manager_fallback, sample_saml_request
    ):
        """SAML Request wird aus Fallback geholt und geloescht."""
        await state_manager_fallback.store_saml_request(
            request_id="test_request",
            data=sample_saml_request,
        )

        result = await state_manager_fallback.get_saml_request(
            request_id="test_request",
            delete=True,
        )

        assert result is not None
        key = f"{SAML_REQUEST_PREFIX}test_request"
        assert key not in state_manager_fallback._fallback_storage


# =============================================================================
# Redis Failure Fallback Tests
# =============================================================================


class TestRedisFailureFallback:
    """Tests fuer Fallback bei Redis-Fehlern."""

    @pytest.mark.asyncio
    async def test_store_oidc_falls_back_on_redis_error(
        self, mock_redis, sample_oidc_state
    ):
        """Store faellt auf In-Memory zurueck bei Redis-Fehler."""
        mock_redis.setex = AsyncMock(
            side_effect=ConnectionError("Redis nicht erreichbar")
        )
        manager = SSOStateManager(redis_client=mock_redis)

        # Sollte nicht fehlschlagen
        await manager.store_oidc_state(
            state="test_state",
            data=sample_oidc_state,
        )

        # Sollte im Fallback sein
        key = f"{OIDC_STATE_PREFIX}test_state"
        assert key in manager._fallback_storage
        assert manager._using_fallback is True

    @pytest.mark.asyncio
    async def test_get_oidc_falls_back_on_redis_error(
        self, mock_redis, sample_oidc_state
    ):
        """Get faellt auf In-Memory zurueck bei Redis-Fehler."""
        mock_redis.getdel = AsyncMock(
            side_effect=ConnectionError("Redis nicht erreichbar")
        )
        manager = SSOStateManager(redis_client=mock_redis)

        # Direkt in Fallback speichern
        key = f"{OIDC_STATE_PREFIX}test_state"
        expires_at = datetime.utcnow() + timedelta(minutes=10)
        manager._fallback_storage[key] = (
            sample_oidc_state.model_dump_json(),
            expires_at,
        )

        result = await manager.get_oidc_state(state="test_state", delete=True)

        assert result is not None
        assert result.state == sample_oidc_state.state


# =============================================================================
# Cleanup Tests
# =============================================================================


class TestCleanup:
    """Tests fuer Cleanup-Funktionalitaet."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_in_fallback(
        self, state_manager_fallback, sample_oidc_state, sample_saml_request
    ):
        """Cleanup entfernt abgelaufene Eintraege im Fallback."""
        now = datetime.utcnow()

        # Abgelaufene Eintraege
        state_manager_fallback._fallback_storage[
            f"{OIDC_STATE_PREFIX}expired1"
        ] = (sample_oidc_state.model_dump_json(), now - timedelta(seconds=1))
        state_manager_fallback._fallback_storage[
            f"{SAML_REQUEST_PREFIX}expired2"
        ] = (sample_saml_request.model_dump_json(), now - timedelta(seconds=1))

        # Gueltige Eintraege
        state_manager_fallback._fallback_storage[
            f"{OIDC_STATE_PREFIX}valid"
        ] = (sample_oidc_state.model_dump_json(), now + timedelta(minutes=5))

        cleaned = await state_manager_fallback.cleanup_expired()

        assert cleaned == 2
        assert f"{OIDC_STATE_PREFIX}expired1" not in state_manager_fallback._fallback_storage
        assert f"{SAML_REQUEST_PREFIX}expired2" not in state_manager_fallback._fallback_storage
        assert f"{OIDC_STATE_PREFIX}valid" in state_manager_fallback._fallback_storage

    @pytest.mark.asyncio
    async def test_cleanup_with_redis_returns_zero(self, state_manager_redis):
        """Cleanup mit Redis gibt 0 zurueck (Redis handhabt TTL)."""
        cleaned = await state_manager_redis.cleanup_expired()

        assert cleaned == 0


# =============================================================================
# Statistics Tests
# =============================================================================


class TestStatistics:
    """Tests fuer Statistiken."""

    @pytest.mark.asyncio
    async def test_get_stats_fallback(
        self, state_manager_fallback, sample_oidc_state, sample_saml_request
    ):
        """Stats zeigen Fallback-Informationen."""
        await state_manager_fallback.store_oidc_state("s1", sample_oidc_state)
        await state_manager_fallback.store_oidc_state("s2", sample_oidc_state)
        await state_manager_fallback.store_saml_request("r1", sample_saml_request)

        stats = await state_manager_fallback.get_stats()

        assert stats["using_fallback"] is True
        assert stats["fallback_entry_count"] == 3
        assert stats["active_oidc_states"] == 2
        assert stats["active_saml_requests"] == 1

    @pytest.mark.asyncio
    async def test_get_stats_redis(self, state_manager_redis, mock_redis):
        """Stats zeigen Redis-Informationen."""

        async def mock_scan_iter(match=None):
            if OIDC_STATE_PREFIX in match:
                for k in ["key1", "key2"]:
                    yield k
            elif SAML_REQUEST_PREFIX in match:
                for k in ["key3"]:
                    yield k

        mock_redis.scan_iter = mock_scan_iter

        stats = await state_manager_redis.get_stats()

        assert stats["using_fallback"] is False
        assert stats["redis_oidc_states"] == 2
        assert stats["redis_saml_requests"] == 1


# =============================================================================
# Singleton Tests
# =============================================================================


class TestSingleton:
    """Tests fuer Singleton-Funktionen."""

    def test_get_sso_state_manager_creates_singleton(self):
        """get_sso_state_manager erstellt Singleton."""
        # Reset singleton
        import app.services.auth.sso.sso_state_manager as module
        module._state_manager = None

        manager1 = get_sso_state_manager()
        manager2 = get_sso_state_manager()

        assert manager1 is manager2

        # Cleanup
        module._state_manager = None

    @pytest.mark.asyncio
    async def test_cleanup_sso_states_uses_singleton(self):
        """cleanup_sso_states verwendet Singleton."""
        import app.services.auth.sso.sso_state_manager as module
        module._state_manager = None

        # Erstelle Singleton mit Fallback
        manager = get_sso_state_manager(redis_client=None)

        # Fuege abgelaufenen State hinzu
        key = f"{OIDC_STATE_PREFIX}expired"
        manager._fallback_storage[key] = (
            "{}",
            datetime.utcnow() - timedelta(seconds=1),
        )

        cleaned = await cleanup_sso_states()

        assert cleaned == 1

        # Cleanup
        module._state_manager = None


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_custom_ttl(self, state_manager_fallback, sample_oidc_state):
        """Benutzerdefinierter TTL wird respektiert."""
        await state_manager_fallback.store_oidc_state(
            state="short_lived",
            data=sample_oidc_state,
            ttl=1,  # 1 Sekunde
        )

        # Sofort sollte es verfuegbar sein
        result = await state_manager_fallback.get_oidc_state(
            state="short_lived",
            delete=False,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_concurrent_access(
        self, state_manager_fallback, sample_oidc_state
    ):
        """Concurrent Zugriff funktioniert ohne Fehler."""
        states = [f"state_{i}" for i in range(10)]

        # Concurrent Store
        await asyncio.gather(*[
            state_manager_fallback.store_oidc_state(s, sample_oidc_state)
            for s in states
        ])

        # Concurrent Get
        results = await asyncio.gather(*[
            state_manager_fallback.get_oidc_state(s, delete=False)
            for s in states
        ])

        assert all(r is not None for r in results)

    @pytest.mark.asyncio
    async def test_special_characters_in_state(
        self, state_manager_fallback, sample_oidc_state
    ):
        """Special Characters in State ID werden korrekt behandelt."""
        special_state = "state_with_special_+/=chars"

        await state_manager_fallback.store_oidc_state(
            state=special_state,
            data=sample_oidc_state,
        )

        result = await state_manager_fallback.get_oidc_state(
            state=special_state,
            delete=True,
        )

        assert result is not None
        assert result.state == sample_oidc_state.state

    @pytest.mark.asyncio
    async def test_unicode_in_relay_state(
        self, state_manager_fallback
    ):
        """Unicode in Relay State wird korrekt behandelt."""
        from app.services.auth.sso.saml_service import SAMLRequest

        saml_request = SAMLRequest(
            request_id="_id123",
            provider_id=uuid4(),
            relay_state="https://app.example.com/dashboard?name=Muenchen&desc=Groesse",
        )

        await state_manager_fallback.store_saml_request(
            request_id="test_unicode",
            data=saml_request,
        )

        result = await state_manager_fallback.get_saml_request(
            request_id="test_unicode",
            delete=True,
        )

        assert result is not None
        assert "Muenchen" in result.relay_state

    @pytest.mark.asyncio
    async def test_double_delete_returns_false(
        self, state_manager_fallback, sample_oidc_state
    ):
        """Doppeltes Loeschen gibt beim zweiten Mal False zurueck."""
        await state_manager_fallback.store_oidc_state(
            state="test",
            data=sample_oidc_state,
        )

        first_delete = await state_manager_fallback.delete_oidc_state("test")
        second_delete = await state_manager_fallback.delete_oidc_state("test")

        assert first_delete is True
        assert second_delete is False

    @pytest.mark.asyncio
    async def test_get_after_delete_returns_none(
        self, state_manager_fallback, sample_oidc_state
    ):
        """Get nach Delete gibt None zurueck."""
        await state_manager_fallback.store_oidc_state(
            state="test",
            data=sample_oidc_state,
        )

        # Erstes Get mit delete=True
        first_result = await state_manager_fallback.get_oidc_state(
            state="test",
            delete=True,
        )

        # Zweites Get sollte None sein (bereits geloescht)
        second_result = await state_manager_fallback.get_oidc_state(
            state="test",
            delete=True,
        )

        assert first_result is not None
        assert second_result is None


# =============================================================================
# TTL Validation Tests
# =============================================================================


class TestTTLValidation:
    """Tests fuer TTL-Verhalten."""

    def test_default_ttl_constant(self):
        """Default TTL ist 600 Sekunden (10 Minuten)."""
        assert STATE_TTL_SECONDS == 600

    @pytest.mark.asyncio
    async def test_redis_receives_correct_ttl(
        self, state_manager_redis, sample_oidc_state, mock_redis
    ):
        """Redis erhaelt korrekten TTL."""
        await state_manager_redis.store_oidc_state(
            state="test",
            data=sample_oidc_state,
            ttl=300,  # 5 Minuten
        )

        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 300  # TTL Parameter

    @pytest.mark.asyncio
    async def test_fallback_respects_ttl(
        self, state_manager_fallback, sample_oidc_state
    ):
        """Fallback respektiert TTL fuer Expiration."""
        ttl = 120
        before = datetime.utcnow()

        await state_manager_fallback.store_oidc_state(
            state="test",
            data=sample_oidc_state,
            ttl=ttl,
        )

        after = datetime.utcnow()

        key = f"{OIDC_STATE_PREFIX}test"
        _, expires_at = state_manager_fallback._fallback_storage[key]

        # Expires_at sollte zwischen before+ttl und after+ttl liegen
        expected_min = before + timedelta(seconds=ttl)
        expected_max = after + timedelta(seconds=ttl)
        assert expected_min <= expires_at <= expected_max
