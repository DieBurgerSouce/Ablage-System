# -*- coding: utf-8 -*-
"""
Unit Tests fuer Feature-Flag API Endpoints.

Testet alle 8 REST-Endpoints fuer Feature-Flag Verwaltung:
- Flags auflisten (GET /)
- Flag erstellen (POST /)
- Flag abrufen (GET /{flag_id})
- Flag aktualisieren (PATCH /{flag_id})
- Flag loeschen (DELETE /{flag_id})
- Kill-Switch (POST /{key}/kill-switch)
- Flag evaluieren (GET /evaluate/{key})
- Alle Flags evaluieren (GET /evaluate-all)

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app.api.v1.feature_flags import (
    list_feature_flags,
    create_feature_flag,
    get_feature_flag,
    update_feature_flag,
    delete_feature_flag,
    activate_kill_switch,
    evaluate_feature_flag,
    evaluate_all_feature_flags,
    FeatureFlagCreate,
    FeatureFlagUpdate,
    FeatureFlagResponse,
)

# Test-Konstanten
TEST_USER_UUID = UUID("00000000-0000-0000-0000-000000000001")
TEST_FLAG_UUID = UUID("00000000-0000-0000-0000-000000000010")
NOW_UTC = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)

pytestmark = [pytest.mark.unit, pytest.mark.api]


# ========================= Mock Fixtures =========================


@pytest.fixture
def mock_user() -> Mock:
    """Mock-Superuser fuer Authentifizierung."""
    user = Mock()
    user.id = TEST_USER_UUID
    user.is_superuser = True
    user.tier = "premium"
    return user


@pytest.fixture
def mock_regular_user() -> Mock:
    """Mock-Benutzer ohne Superuser-Rechte."""
    user = Mock()
    user.id = UUID("00000000-0000-0000-0000-000000000002")
    user.is_superuser = False
    user.tier = "free"
    return user


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock-Datenbank-Session."""
    return AsyncMock()


@pytest.fixture(autouse=True)
def _bypass_rate_limiter() -> None:
    """Deaktiviert den slowapi Rate Limiter (kein Redis in Unit Tests)."""
    with patch(
        "app.core.rate_limiting.limiter._check_request_limit",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def mock_request() -> Request:
    """Echtes Starlette Request Objekt (benoetigt fuer slowapi Rate Limiter)."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/admin/feature-flags",
        "headers": Headers({}).raw,
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    # slowapi erwartet diese State-Attribute nach dem Rate-Limit-Check
    request.state.view_rate_limit = None
    request.state._rate_limiting_complete = True
    return request


@pytest.fixture
def mock_flag() -> Mock:
    """Mock FeatureFlag mit Standardwerten."""
    flag = Mock()
    flag.id = TEST_FLAG_UUID
    flag.key = "test_feature"
    flag.name = "Test Feature"
    flag.description = "Eine Test-Feature-Flag"
    flag.enabled = True
    flag.rollout_percentage = 100
    flag.target_tiers = ["premium"]
    flag.target_users = []
    flag.variants = {}
    flag.starts_at = None
    flag.ends_at = None
    flag.config = {"max_requests": 1000}
    flag.created_at = NOW_UTC
    flag.updated_at = NOW_UTC
    return flag


# ========================= List Flags Tests =========================


class TestListFeatureFlags:
    """Tests fuer GET /admin/feature-flags (Flags auflisten)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_list_flags_success(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_flag: Mock,
    ) -> None:
        """Erfolgreiche Auflistung von Feature-Flags."""
        service = AsyncMock()
        service.get_all.return_value = [mock_flag]
        service.count.return_value = 1
        mock_get_service.return_value = service

        with patch(
            "app.api.v1.feature_flags.FeatureFlagResponse.model_validate",
            return_value=FeatureFlagResponse(
                id=mock_flag.id,
                key=mock_flag.key,
                name=mock_flag.name,
                description=mock_flag.description,
                enabled=mock_flag.enabled,
                rollout_percentage=mock_flag.rollout_percentage,
                target_tiers=mock_flag.target_tiers,
                target_users=mock_flag.target_users,
                variants=mock_flag.variants,
                starts_at=mock_flag.starts_at,
                ends_at=mock_flag.ends_at,
                config=mock_flag.config,
                created_at=mock_flag.created_at,
                updated_at=mock_flag.updated_at,
            ),
        ):
            result = await list_feature_flags(
                request=mock_request,
                enabled_only=False,
                limit=100,
                offset=0,
                db=mock_db,
                current_user=mock_user,
            )

        assert result.total == 1
        assert len(result.flags) == 1
        assert result.flags[0].key == "test_feature"
        assert result.flags[0].enabled is True

        service.get_all.assert_called_once_with(
            enabled_only=False,
            limit=100,
            offset=0,
        )
        service.count.assert_called_once_with(enabled_only=False)

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_list_flags_error(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Fehler beim Auflisten von Flags fuehrt zu 500."""
        service = AsyncMock()
        service.get_all.side_effect = RuntimeError("DB-Fehler")
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await list_feature_flags(
                request=mock_request,
                enabled_only=False,
                limit=100,
                offset=0,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 500
        assert "Fehler beim Auflisten" in exc_info.value.detail


# ========================= Create Flag Tests =========================


class TestCreateFeatureFlag:
    """Tests fuer POST /admin/feature-flags (Flag erstellen)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_create_flag_success(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_flag: Mock,
    ) -> None:
        """Feature-Flag wird erfolgreich erstellt."""
        service = AsyncMock()
        service.get_by_key.return_value = None  # Kein Duplikat
        service.create.return_value = mock_flag
        mock_get_service.return_value = service

        data = FeatureFlagCreate(
            key="new_feature",
            name="Neues Feature",
            description="Beschreibung",
            enabled=False,
            rollout_percentage=0,
        )

        with patch(
            "app.api.v1.feature_flags.FeatureFlagResponse.model_validate",
            return_value=FeatureFlagResponse(
                id=mock_flag.id,
                key=mock_flag.key,
                name=mock_flag.name,
                description=mock_flag.description,
                enabled=mock_flag.enabled,
                rollout_percentage=mock_flag.rollout_percentage,
                target_tiers=mock_flag.target_tiers,
                target_users=mock_flag.target_users,
                variants=mock_flag.variants,
                starts_at=mock_flag.starts_at,
                ends_at=mock_flag.ends_at,
                config=mock_flag.config,
                created_at=mock_flag.created_at,
                updated_at=mock_flag.updated_at,
            ),
        ):
            result = await create_feature_flag(
                request=mock_request,
                data=data,
                db=mock_db,
                current_user=mock_user,
            )

        assert result.id == TEST_FLAG_UUID
        assert result.key == "test_feature"

        service.get_by_key.assert_called_once_with("new_feature")
        service.create.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_create_flag_duplicate_key(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_flag: Mock,
    ) -> None:
        """Doppelter Key fuehrt zu 409 Conflict."""
        service = AsyncMock()
        service.get_by_key.return_value = mock_flag  # Duplikat existiert
        mock_get_service.return_value = service

        data = FeatureFlagCreate(
            key="test_feature",
            name="Test Feature",
        )

        with pytest.raises(HTTPException) as exc_info:
            await create_feature_flag(
                request=mock_request,
                data=data,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 409
        assert "existiert bereits" in exc_info.value.detail


# ========================= Get Flag Tests =========================


class TestGetFeatureFlag:
    """Tests fuer GET /admin/feature-flags/{flag_id} (Flag abrufen)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_get_flag_by_id(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_flag: Mock,
    ) -> None:
        """Feature-Flag wird erfolgreich abgerufen."""
        service = AsyncMock()
        service.get_by_id.return_value = mock_flag
        mock_get_service.return_value = service

        with patch(
            "app.api.v1.feature_flags.FeatureFlagResponse.model_validate",
            return_value=FeatureFlagResponse(
                id=mock_flag.id,
                key=mock_flag.key,
                name=mock_flag.name,
                description=mock_flag.description,
                enabled=mock_flag.enabled,
                rollout_percentage=mock_flag.rollout_percentage,
                target_tiers=mock_flag.target_tiers,
                target_users=mock_flag.target_users,
                variants=mock_flag.variants,
                starts_at=mock_flag.starts_at,
                ends_at=mock_flag.ends_at,
                config=mock_flag.config,
                created_at=mock_flag.created_at,
                updated_at=mock_flag.updated_at,
            ),
        ):
            result = await get_feature_flag(
                request=mock_request,
                flag_id=TEST_FLAG_UUID,
                db=mock_db,
                current_user=mock_user,
            )

        assert result.id == TEST_FLAG_UUID
        assert result.key == "test_feature"

        service.get_by_id.assert_called_once_with(TEST_FLAG_UUID)

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_get_flag_not_found(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Nicht existierendes Flag fuehrt zu 404."""
        service = AsyncMock()
        service.get_by_id.return_value = None
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await get_feature_flag(
                request=mock_request,
                flag_id=TEST_FLAG_UUID,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert "nicht gefunden" in exc_info.value.detail


# ========================= Update Flag Tests =========================


class TestUpdateFeatureFlag:
    """Tests fuer PATCH /admin/feature-flags/{flag_id} (Flag aktualisieren)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_update_flag(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
        mock_flag: Mock,
    ) -> None:
        """Feature-Flag wird erfolgreich aktualisiert."""
        service = AsyncMock()
        service.update_flag.return_value = mock_flag
        mock_get_service.return_value = service

        data = FeatureFlagUpdate(
            enabled=False,
            rollout_percentage=50,
        )

        with patch(
            "app.api.v1.feature_flags.FeatureFlagResponse.model_validate",
            return_value=FeatureFlagResponse(
                id=mock_flag.id,
                key=mock_flag.key,
                name=mock_flag.name,
                description=mock_flag.description,
                enabled=mock_flag.enabled,
                rollout_percentage=mock_flag.rollout_percentage,
                target_tiers=mock_flag.target_tiers,
                target_users=mock_flag.target_users,
                variants=mock_flag.variants,
                starts_at=mock_flag.starts_at,
                ends_at=mock_flag.ends_at,
                config=mock_flag.config,
                created_at=mock_flag.created_at,
                updated_at=mock_flag.updated_at,
            ),
        ):
            result = await update_feature_flag(
                request=mock_request,
                flag_id=TEST_FLAG_UUID,
                data=data,
                db=mock_db,
                current_user=mock_user,
            )

        assert result.id == TEST_FLAG_UUID

        call_kwargs = service.update_flag.call_args[1]
        assert call_kwargs["flag_id"] == TEST_FLAG_UUID
        assert "enabled" in call_kwargs["updates"]
        assert "rollout_percentage" in call_kwargs["updates"]


# ========================= Delete Flag Tests =========================


class TestDeleteFeatureFlag:
    """Tests fuer DELETE /admin/feature-flags/{flag_id} (Flag loeschen)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_delete_flag(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Feature-Flag wird erfolgreich geloescht."""
        service = AsyncMock()
        service.delete_flag.return_value = True
        mock_get_service.return_value = service

        # Sollte keine Exception werfen (204 No Content)
        await delete_feature_flag(
            request=mock_request,
            flag_id=TEST_FLAG_UUID,
            db=mock_db,
            current_user=mock_user,
        )

        service.delete_flag.assert_called_once_with(TEST_FLAG_UUID)

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_delete_flag_not_found(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Nicht existierendes Flag fuehrt zu 404."""
        service = AsyncMock()
        service.delete_flag.return_value = False
        mock_get_service.return_value = service

        with pytest.raises(HTTPException) as exc_info:
            await delete_feature_flag(
                request=mock_request,
                flag_id=TEST_FLAG_UUID,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc_info.value.status_code == 404
        assert "nicht gefunden" in exc_info.value.detail


# ========================= Kill Switch Tests =========================


class TestKillSwitch:
    """Tests fuer POST /admin/feature-flags/{key}/kill-switch."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_kill_switch(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Kill-Switch wird erfolgreich aktiviert."""
        service = AsyncMock()
        service.kill_switch.return_value = True
        mock_get_service.return_value = service

        result = await activate_kill_switch(
            request=mock_request,
            key="test_feature",
            db=mock_db,
            current_user=mock_user,
        )

        assert result["key"] == "test_feature"
        assert result["status"] == "deactivated"

        service.kill_switch.assert_called_once_with("test_feature")


# ========================= Evaluate Flag Tests =========================


class TestEvaluateFeatureFlag:
    """Tests fuer GET /feature-flags/evaluate/{key} (User-Endpoint)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_evaluate_flag_user(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_regular_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Feature-Flag wird fuer Benutzer evaluiert."""
        service = AsyncMock()
        service.evaluate.return_value = {
            "flag_key": "test_feature",
            "enabled": True,
            "variant": "a",
            "reason": "evaluated",
        }
        mock_get_service.return_value = service

        result = await evaluate_feature_flag(
            request=mock_request,
            key="test_feature",
            db=mock_db,
            current_user=mock_regular_user,
        )

        assert result.flag_key == "test_feature"
        assert result.enabled is True
        assert result.variant == "a"
        assert result.reason == "evaluated"

        service.evaluate.assert_called_once()


# ========================= Evaluate All Flags Tests =========================


class TestEvaluateAllFeatureFlags:
    """Tests fuer GET /feature-flags/evaluate-all (User-Endpoint)."""

    @pytest.mark.asyncio
    @patch("app.api.v1.feature_flags.get_feature_flag_service")
    async def test_evaluate_all_flags(
        self,
        mock_get_service: Mock,
        mock_request: Request,
        mock_regular_user: Mock,
        mock_db: AsyncMock,
    ) -> None:
        """Alle Feature-Flags werden fuer Benutzer evaluiert."""
        service = AsyncMock()
        service.evaluate_all.return_value = {
            "test_feature_1": {
                "enabled": True,
                "variant": None,
                "reason": "enabled_for_all",
            },
            "test_feature_2": {
                "enabled": False,
                "variant": None,
                "reason": "disabled",
            },
        }
        mock_get_service.return_value = service

        result = await evaluate_all_feature_flags(
            request=mock_request,
            db=mock_db,
            current_user=mock_regular_user,
        )

        assert "test_feature_1" in result
        assert "test_feature_2" in result
        assert result["test_feature_1"]["enabled"] is True
        assert result["test_feature_2"]["enabled"] is False

        service.evaluate_all.assert_called_once()
