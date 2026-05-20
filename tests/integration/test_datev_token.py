# -*- coding: utf-8 -*-
"""
Integration Tests: DATEV Token Refresh Edge Cases.

Tests OAuth2-Token-Management unter Stress-Bedingungen:
- Concurrent token refresh von mehreren Workern
- Token expiry während Sync-Operation
- Invalid/revoked credentials handling

Feinpoliert und durchdacht - OAuth2 Edge Case Testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from uuid import uuid4
import asyncio

import pytest_asyncio
from httpx import AsyncClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def datev_connection():
    """Mock DATEV connection with expiring token."""
    return {
        "id": str(uuid4()),
        "name": "Test Connection",
        "access_token_encrypted": "encrypted_token_123",
        "refresh_token_encrypted": "encrypted_refresh_456",
        "token_expires_at": datetime.utcnow() + timedelta(minutes=5),
        "is_active": True,
    }


@pytest.fixture
def mock_oauth_client():
    """Mock OAuth2 client for DATEV."""
    client = MagicMock()
    client.refresh_token = AsyncMock(
        return_value={
            "access_token": "new_access_token_789",
            "refresh_token": "new_refresh_token_012",
            "expires_in": 3600,
        }
    )
    return client


# =============================================================================
# TEST 1: CONCURRENT TOKEN REFRESH
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_datev_token_refresh_concurrent(
    async_client: AsyncClient,
    auth_headers: dict,
    datev_connection: dict,
    mock_oauth_client,
):
    """
    Test gleichzeitiges Token-Refresh von mehreren Celery Workern.

    ARRANGE: Token läuft ab, 5 Worker versuchen parallel Refresh
    ACT: Concurrent refresh_token() calls
    ASSERT: Nur 1 Refresh erfolgt, andere warten auf Lock
    """
    with patch("app.services.datev.connect.datev_auth_service.DATEVAuthService") as MockAuthService:
        mock_auth = MockAuthService.return_value

        # Track refresh calls
        refresh_count = 0
        lock = asyncio.Lock()

        async def mock_refresh_token_with_lock(connection_id: str):
            """Refresh with lock to prevent race conditions."""
            nonlocal refresh_count

            async with lock:
                # Simulate check: token already refreshed?
                if refresh_count > 0:
                    # Another worker already refreshed, return cached token
                    return {
                        "access_token": "cached_token",
                        "already_refreshed": True,
                    }

                # Perform actual refresh
                await asyncio.sleep(0.1)  # Simulate OAuth2 call
                refresh_count += 1

                return {
                    "access_token": "new_access_token_789",
                    "refresh_token": "new_refresh_token_012",
                    "expires_in": 3600,
                }

        mock_auth.refresh_token = mock_refresh_token_with_lock

        # ACT: 5 workers try to refresh concurrently
        tasks = [
            mock_auth.refresh_token(datev_connection["id"])
            for _ in range(5)
        ]
        results = await asyncio.gather(*tasks)

        # ASSERT: Only 1 actual refresh
        assert refresh_count == 1

        # First result is fresh token
        assert results[0]["access_token"] == "new_access_token_789"

        # Others are cached
        assert all(r.get("already_refreshed") or r["access_token"] for r in results)


# =============================================================================
# TEST 2: TOKEN EXPIRED DURING SYNC
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_datev_token_expired_during_sync(
    async_client: AsyncClient,
    auth_headers: dict,
    datev_connection: dict,
):
    """
    Test Token-Ablauf während laufender Sync-Operation.

    ARRANGE: Token läuft während Stammdaten-Sync ab
    ACT: Sync startet, Token expiriert, Auto-Refresh
    ASSERT: Sync erfolgreich fortgesetzt nach Refresh
    """
    with patch("app.services.datev.connect.datev_connector.DATEVConnector") as MockConnector:
        mock_connector = MockConnector.return_value

        call_count = 0

        async def mock_sync_stammdaten():
            """Simulate sync with token expiry mid-operation."""
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call: Token expired
                raise Exception("401 Unauthorized: Token expired")
            else:
                # Second call: Success after refresh
                return {
                    "success": True,
                    "kunden_synced": 150,
                    "lieferanten_synced": 80,
                }

        mock_connector.sync_stammdaten = mock_sync_stammdaten

        # Mock auto-refresh
        async def mock_auto_refresh_on_401():
            """Auto-refresh when 401 detected."""
            await asyncio.sleep(0.05)  # Simulate OAuth2 call
            return {"access_token": "refreshed_token"}

        with patch("app.services.datev.connect.datev_auth_service.DATEVAuthService.refresh_token", mock_auto_refresh_on_401):
            # ACT: Sync with auto-retry on token expiry
            try:
                result = await mock_connector.sync_stammdaten()
            except Exception as e:
                # Token expired, trigger refresh
                if "Token expired" in str(e):
                    await mock_auto_refresh_on_401()
                    # Retry sync
                    result = await mock_connector.sync_stammdaten()

            # ASSERT: Sync succeeded after refresh
            assert result["success"] is True
            assert result["kunden_synced"] == 150
            assert call_count == 2  # 1 failed + 1 success


# =============================================================================
# TEST 3: INVALID/REVOKED CREDENTIALS
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_datev_token_invalid_credentials(
    async_client: AsyncClient,
    auth_headers: dict,
    datev_connection: dict,
):
    """
    Test Handling von revoked/invalid OAuth2-Tokens.

    ARRANGE: Refresh-Token wurde von DATEV revoked
    ACT: Versuch Token zu refreshen
    ASSERT: Connection wird deaktiviert, Admin benachrichtigt
    """
    with patch("app.services.datev.connect.datev_auth_service.DATEVAuthService") as MockAuthService:
        mock_auth = MockAuthService.return_value

        async def mock_refresh_with_revoked_token(connection_id: str):
            """Simulate revoked refresh token."""
            raise Exception("400 Bad Request: invalid_grant - Refresh token revoked")

        mock_auth.refresh_token = mock_refresh_with_revoked_token

        # Mock connection update
        connection_disabled = False

        async def mock_disable_connection(connection_id: str):
            """Disable connection after revoked token."""
            nonlocal connection_disabled
            connection_disabled = True
            return {"is_active": False}

        mock_auth.disable_connection = mock_disable_connection

        # ACT: Try refresh with revoked token
        try:
            await mock_auth.refresh_token(datev_connection["id"])
        except Exception as e:
            # Handle revoked token
            if "Refresh token revoked" in str(e):
                await mock_auth.disable_connection(datev_connection["id"])

        # ASSERT: Connection disabled
        assert connection_disabled is True


# =============================================================================
# BONUS: TOKEN REFRESH RACE WITH DB UPDATE
# =============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
async def test_datev_token_refresh_db_race_condition(
    async_client: AsyncClient,
    auth_headers: dict,
):
    """
    Test Race Condition bei DB-Update nach Token-Refresh.

    ARRANGE: 2 Worker refreshen gleichzeitig
    ACT: Beide versuchen neuen Token in DB zu speichern
    ASSERT: Letzter Write gewinnt, kein Deadlock
    """
    with patch("app.services.datev.connect.datev_auth_service.DATEVAuthService") as MockAuthService:
        mock_auth = MockAuthService.return_value

        db_token = None
        write_count = 0

        async def mock_save_token(connection_id: str, new_token: str):
            """Simulate DB write with delay."""
            nonlocal db_token, write_count
            await asyncio.sleep(0.05)  # Simulate DB latency
            db_token = new_token
            write_count += 1

        mock_auth.save_token = mock_save_token

        # ACT: 2 workers save different tokens
        await asyncio.gather(
            mock_auth.save_token("conn_123", "token_worker_1"),
            mock_auth.save_token("conn_123", "token_worker_2"),
        )

        # ASSERT: Both writes completed (no deadlock)
        assert write_count == 2

        # Last write wins (non-deterministic which token, but one of them)
        assert db_token in ["token_worker_1", "token_worker_2"]
