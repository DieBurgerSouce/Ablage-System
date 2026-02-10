"""
Unit Tests für Cache Admin API Endpoints.

Testet die Cache-Management-Endpunkte unter /api/v1/admin/cache.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from starlette.requests import Request
from starlette.datastructures import Headers
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.cache_admin import (
    get_metrics,
    invalidate,
    warm_cache,
    CacheInvalidateRequest,
)
from app.db.models import User

pytestmark = [pytest.mark.unit, pytest.mark.api]


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def mock_user() -> User:
    """Mock Superuser für Tests."""
    user = MagicMock(spec=User)
    user.id = 1
    user.is_superuser = True
    return user


@pytest.fixture
def mock_db() -> AsyncSession:
    """Mock AsyncSession."""
    db = MagicMock(spec=AsyncSession)
    return db


@pytest.fixture
def mock_request() -> Request:
    """Mock Starlette Request."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/admin/cache",
        "headers": Headers({}).raw,
        "query_string": b"",
        "root_path": "",
        "client": ("127.0.0.1", 12345),
    }
    request = Request(scope)
    request.state.view_rate_limit = None
    request.state._rate_limiting_complete = True
    return request


@pytest.fixture(autouse=True)
def _bypass_rate_limiter():
    """Bypass rate limiter für alle Tests."""
    with patch("app.core.rate_limiting.limiter._check_request_limit", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = None
        yield mock_check


# ============================================================
# Tests: GET /api/v1/admin/cache/metrics
# ============================================================


class TestGetCacheMetrics:
    """Tests für Cache Metrics Endpoint."""

    @pytest.mark.asyncio
    async def test_get_cache_metrics_success(self, mock_request: Request, mock_user: User):
        """
        GET Metrics - Success.

        Verifiziert:
        - get_cache_metrics() wird aufgerufen
        - Response enthält L1/L2 Metriken
        """
        mock_metrics = {
            "l1": {
                "total_keys": 42,
                "memory_usage": 1024,
                "hit_rate": 0.85,
            },
            "l2": {
                "total_keys": 100,
                "memory_usage": 4096,
                "hit_rate": 0.75,
            },
        }

        with patch("app.api.v1.cache_admin.get_cache_metrics", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_metrics

            result = await get_metrics(request=mock_request, current_user=mock_user)

            # Result is a CacheMetricsResponse Pydantic model, not a dict
            assert result.l1 == mock_metrics["l1"]
            assert result.l2 == mock_metrics["l2"]
            mock_get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cache_metrics_error(self, mock_request: Request, mock_user: User):
        """
        GET Metrics - Error.

        Verifiziert:
        - Bei Exception wird HTTPException 500 geworfen
        """
        with patch("app.api.v1.cache_admin.get_cache_metrics", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Redis connection failed")

            with pytest.raises(HTTPException) as exc_info:
                await get_metrics(request=mock_request, current_user=mock_user)

            assert exc_info.value.status_code == 500
            assert "Fehler beim Abrufen der Cache-Metriken" in exc_info.value.detail


# ============================================================
# Tests: POST /api/v1/admin/cache/invalidate
# ============================================================


class TestInvalidateCache:
    """Tests für Cache Invalidierung Endpoint."""

    @pytest.mark.asyncio
    async def test_invalidate_by_pattern(self, mock_request: Request, mock_user: User):
        """
        Invalidate - Pattern.

        Verifiziert:
        - invalidate_cache(pattern) wird aufgerufen
        - Success Response
        """
        body = CacheInvalidateRequest(pattern="doc:*")

        with patch("app.api.v1.cache_admin.invalidate_cache", new_callable=AsyncMock) as mock_inv:
            # invalidate_cache returns an int (deleted count)
            mock_inv.return_value = 15

            result = await invalidate(request=mock_request, body=body, current_user=mock_user)

            # Returns CacheInvalidateResponse Pydantic model
            assert result.deleted_keys == 15
            assert result.scope == "pattern:doc:*"
            mock_inv.assert_called_once_with("doc:*")

    @pytest.mark.asyncio
    async def test_invalidate_by_scope_all(self, mock_request: Request, mock_user: User):
        """
        Invalidate - Scope All.

        Verifiziert:
        - invalidate_all_caches() wird aufgerufen
        """
        body = CacheInvalidateRequest(scope="all")

        with patch("app.api.v1.cache_admin.invalidate_all_caches", new_callable=AsyncMock) as mock_inv:
            # invalidate_all_caches returns a dict with "total" key
            mock_inv.return_value = {"total": 50, "l1": 20, "l2": 30}

            result = await invalidate(request=mock_request, body=body, current_user=mock_user)

            # Returns CacheInvalidateResponse Pydantic model
            assert result.deleted_keys == 50
            assert result.scope == "all"
            assert result.details == {"total": 50, "l1": 20, "l2": 30}
            mock_inv.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_by_scope_search(self, mock_request: Request, mock_user: User):
        """
        Invalidate - Scope Search.

        Verifiziert:
        - invalidate_search_cache() wird aufgerufen
        """
        body = CacheInvalidateRequest(scope="search")

        with patch("app.api.v1.cache_admin.invalidate_search_cache", new_callable=AsyncMock) as mock_inv:
            # invalidate_search_cache returns an int (deleted count)
            mock_inv.return_value = 25

            result = await invalidate(request=mock_request, body=body, current_user=mock_user)

            # Returns CacheInvalidateResponse Pydantic model
            assert result.deleted_keys == 25
            assert result.scope == "search"
            mock_inv.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalidate_by_document_id(self, mock_request: Request, mock_user: User):
        """
        Invalidate - Document ID.

        Verifiziert:
        - invalidate_document_cache(id, cascade=True) wird aufgerufen
        """
        # document_id is Optional[str], not int
        body = CacheInvalidateRequest(document_id="123")

        with patch("app.api.v1.cache_admin.invalidate_document_cache", new_callable=AsyncMock) as mock_inv:
            # invalidate_document_cache returns a dict with "total" key
            mock_inv.return_value = {"total": 10, "document": 5, "related": 5}

            result = await invalidate(request=mock_request, body=body, current_user=mock_user)

            # Returns CacheInvalidateResponse Pydantic model
            assert result.deleted_keys == 10
            assert result.scope == "document:123"
            assert result.details == {"total": 10, "document": 5, "related": 5}
            mock_inv.assert_called_once_with("123", cascade=True)

    @pytest.mark.asyncio
    async def test_invalidate_by_user_id(self, mock_request: Request, mock_user: User):
        """
        Invalidate - User ID.

        Verifiziert:
        - invalidate_user_cache(id, cascade=True) wird aufgerufen
        """
        # user_id is Optional[str], not int
        body = CacheInvalidateRequest(user_id="456")

        with patch("app.api.v1.cache_admin.invalidate_user_cache", new_callable=AsyncMock) as mock_inv:
            # invalidate_user_cache returns a dict with "total" key
            mock_inv.return_value = {"total": 8, "user": 3, "related": 5}

            result = await invalidate(request=mock_request, body=body, current_user=mock_user)

            # Returns CacheInvalidateResponse Pydantic model
            assert result.deleted_keys == 8
            assert result.scope == "user:456"
            assert result.details == {"total": 8, "user": 3, "related": 5}
            mock_inv.assert_called_once_with("456", cascade=True)

    @pytest.mark.asyncio
    async def test_invalidate_no_params_error(self, mock_request: Request, mock_user: User):
        """
        Invalidate - Keine Parameter.

        Verifiziert:
        - HTTPException 400 bei fehlenden Parametern
        """
        body = CacheInvalidateRequest()

        with pytest.raises(HTTPException) as exc_info:
            await invalidate(request=mock_request, body=body, current_user=mock_user)

        assert exc_info.value.status_code == 400
        assert "Bitte pattern, scope, document_id oder user_id angeben" in exc_info.value.detail


# ============================================================
# Tests: POST /api/v1/admin/cache/warm
# ============================================================


class TestWarmCache:
    """Tests für Cache Warming Endpoint."""

    @pytest.mark.asyncio
    async def test_warm_caches_success(
        self, mock_request: Request, mock_db: AsyncSession, mock_user: User
    ):
        """
        Warm Caches - Success.

        Verifiziert:
        - CacheWarmingService.warm_caches() wird aufgerufen
        - Success Response
        """
        mock_service = AsyncMock()
        # warm_caches returns a dict with warmed entry counts
        mock_service.warm_caches = AsyncMock(return_value={"documents": 50, "users": 30, "folders": 20})

        # CacheWarmingService is imported inside the function, so patch at source
        with patch("app.services.cache.cache_warming_service.CacheWarmingService") as mock_cls:
            mock_cls.return_value = mock_service

            result = await warm_cache(request=mock_request, db=mock_db, current_user=mock_user)

            # Returns CacheWarmResponse Pydantic model
            assert result.warmed_entries == {"documents": 50, "users": 30, "folders": 20}
            mock_cls.assert_called_once_with(mock_db)
            mock_service.warm_caches.assert_called_once()

    @pytest.mark.asyncio
    async def test_warm_caches_error(
        self, mock_request: Request, mock_db: AsyncSession, mock_user: User
    ):
        """
        Warm Caches - Error.

        Verifiziert:
        - Bei Exception wird HTTPException 500 geworfen
        """
        mock_service = AsyncMock()
        mock_service.warm_caches = AsyncMock(side_effect=Exception("Warming failed"))

        # CacheWarmingService is imported inside the function, so patch at source
        with patch("app.services.cache.cache_warming_service.CacheWarmingService") as mock_cls:
            mock_cls.return_value = mock_service

            with pytest.raises(HTTPException) as exc_info:
                await warm_cache(request=mock_request, db=mock_db, current_user=mock_user)

            assert exc_info.value.status_code == 500
            assert "Fehler beim Cache-Warming" in exc_info.value.detail
