# -*- coding: utf-8 -*-
"""
Unit-Tests für Search API Endpoints.

Testet:
- Faceted Search
- Autocomplete/Suggestions
- Popular Tags
- Recent Searches (Redis)
- Trending Searches
- Search Statistics
- Benutzerauthentifizierung
- Deutsche Error-Messages

Feinpoliert und durchdacht - Umfassende Search-API-Tests.
"""

import pytest
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from pathlib import Path
import sys

from fastapi import HTTPException, status
from httpx import AsyncClient, ASGITransport

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_user():
    """Mock User für Authentifizierung."""
    user = Mock()
    user.id = uuid4()
    user.email = "test@example.com"
    user.is_active = True
    return user


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock()
    return db


@pytest.fixture
def mock_search_service():
    """Mock Search Service."""
    service = Mock()

    # Mock get_facets - muss List[FacetGroup] Format zurückgeben
    service.get_facets = AsyncMock(return_value={
        "facets": [
            {
                "field": "document_type",
                "label": "Dokumenttyp",
                "values": [
                    {"value": "rechnung", "count": 45},
                    {"value": "vertrag", "count": 32},
                    {"value": "brief", "count": 18}
                ],
                "total_distinct": 3
            },
            {
                "field": "status",
                "label": "Status",
                "values": [
                    {"value": "completed", "count": 80},
                    {"value": "pending", "count": 15}
                ],
                "total_distinct": 2
            },
            {
                "field": "tags",
                "label": "Tags",
                "values": [
                    {"value": "wichtig", "count": 25},
                    {"value": "2024", "count": 40}
                ],
                "total_distinct": 2
            }
        ],
        "total_documents": 95
    })

    # Mock get_suggestions
    service.get_suggestions = AsyncMock(return_value={
        "query": "rech",
        "suggestions": [
            {"text": "Rechnung", "type": "document", "highlight": "<mark>Rech</mark>nung"},
            {"text": "Rechnungsnummer", "type": "term", "highlight": "<mark>Rech</mark>nungsnummer"},
            {"text": "Rechnungsdatum", "type": "term", "highlight": "<mark>Rech</mark>nungsdatum"}
        ],
        "total": 3
    })

    return service


@pytest.fixture
def mock_redis_manager():
    """Mock Redis Manager."""
    redis_manager = Mock()
    redis_manager._ensure_connection = AsyncMock()
    redis_manager._redis = Mock()

    # Mock Redis operations
    redis_manager._redis.lrange = AsyncMock(return_value=[
        json.dumps({
            "query": "Rechnung 2024",
            "timestamp": datetime.utcnow().isoformat(),
            "results_count": 15,
            "filters": {"document_type": "rechnung"}
        }),
        json.dumps({
            "query": "Vertrag Kunde",
            "timestamp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "results_count": 8
        })
    ])
    redis_manager._redis.llen = AsyncMock(return_value=2)
    redis_manager._redis.delete = AsyncMock()
    redis_manager._redis.lpush = AsyncMock()
    redis_manager._redis.ltrim = AsyncMock()
    redis_manager._redis.expire = AsyncMock()

    return redis_manager


# ========================= Test App Factory =========================


def create_test_app(mock_user, mock_db, mock_search_service):
    """Create test app with mocked dependencies."""
    from fastapi import FastAPI
    from app.api.v1.search import router

    app = FastAPI()

    async def override_get_current_user():
        return mock_user

    async def override_get_db():
        yield mock_db

    def override_get_search_service():
        return mock_search_service

    from app.api.dependencies import get_current_user, get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    with patch("app.api.v1.search.get_search_service_dep", return_value=mock_search_service):
        app.include_router(router)

    return app


# ========================= Facets Endpoint Tests =========================


class TestSearchFacetsEndpoint:
    """Tests für /search/facets Endpoint."""

    @pytest.mark.asyncio
    async def test_get_facets_success(self, mock_user, mock_db, mock_search_service):
        """Test erfolgreicher Facets-Abruf."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/facets")

            assert response.status_code == 200
            data = response.json()

            assert "facets" in data
            assert "total_documents" in data
            assert data["total_documents"] == 95

    @pytest.mark.asyncio
    async def test_get_facets_with_custom_fields(self, mock_user, mock_db, mock_search_service):
        """Test Facets mit benutzerdefinierten Feldern."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/facets",
                    params={"facet_fields": "document_type,status"}
                )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_facets_invalid_field(self, mock_user, mock_db, mock_search_service):
        """Test Facets mit ungültigem Feld."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/facets",
                    params={"facet_fields": "invalid_field"}
                )

            assert response.status_code == 400
            assert "Ungültiges Facet-Feld" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_facets_with_filters(self, mock_user, mock_db, mock_search_service):
        """Test Facets mit Filtern."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/facets",
                    params={
                        "document_type": "invoice",  # Gültiger DocumentType Enum-Wert
                        "date_from": "2024-01-01T00:00:00"
                    }
                )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_facets_db_error(self, mock_user, mock_db, mock_search_service):
        """Test Facets bei Datenbankfehler."""
        from sqlalchemy.exc import OperationalError

        mock_search_service.get_facets = AsyncMock(
            side_effect=OperationalError("connection error", None, None)
        )

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/facets")

            assert response.status_code == 503
            assert "Datenbankverbindung" in response.json()["detail"]


# ========================= Suggestions Endpoint Tests =========================


class TestSearchSuggestEndpoint:
    """Tests für /search/suggest Endpoint."""

    @pytest.mark.asyncio
    async def test_get_suggestions_success(self, mock_user, mock_db, mock_search_service):
        """Test erfolgreiche Autocomplete-Vorschläge."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/suggest",
                    params={"q": "rech"}
                )

            assert response.status_code == 200
            data = response.json()

            assert "query" in data
            assert "suggestions" in data
            assert "total" in data
            assert data["query"] == "rech"
            assert len(data["suggestions"]) == 3

    @pytest.mark.asyncio
    async def test_get_suggestions_with_limit(self, mock_user, mock_db, mock_search_service):
        """Test Vorschläge mit Limit."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/suggest",
                    params={"q": "rech", "limit": 5}
                )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_suggestions_query_too_short(self, mock_user, mock_db, mock_search_service):
        """Test Vorschläge mit zu kurzem Query."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/suggest",
                    params={"q": "a"}  # Zu kurz (min_length=2)
                )

            assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_get_suggestions_missing_query(self, mock_user, mock_db, mock_search_service):
        """Test Vorschläge ohne Query."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/suggest")

            assert response.status_code == 422  # Required parameter missing


# ========================= Popular Tags Endpoint Tests =========================


class TestPopularTagsEndpoint:
    """Tests für /search/popular-tags Endpoint."""

    @pytest.mark.asyncio
    async def test_get_popular_tags_success(self, mock_user, mock_db, mock_search_service):
        """Test erfolgreicher Popular Tags Abruf."""
        # Mock database query result
        mock_result = Mock()
        mock_result.all = Mock(return_value=[
            ("wichtig", 25),
            ("2024", 40),
            ("rechnung", 35)
        ])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/popular-tags")

            assert response.status_code == 200
            data = response.json()

            assert "tags" in data
            assert "total" in data
            assert len(data["tags"]) == 3

    @pytest.mark.asyncio
    async def test_get_popular_tags_with_limit(self, mock_user, mock_db, mock_search_service):
        """Test Popular Tags mit Limit."""
        mock_result = Mock()
        mock_result.all = Mock(return_value=[("wichtig", 25)])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/popular-tags",
                    params={"limit": 1}
                )

            assert response.status_code == 200


# ========================= Recent Searches Endpoint Tests =========================


class TestRecentSearchesEndpoint:
    """Tests für /search/recent Endpoint."""

    @pytest.mark.asyncio
    async def test_get_recent_searches_success(self, mock_user, mock_db, mock_search_service, mock_redis_manager):
        """Test erfolgreicher Recent Searches Abruf."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis_manager):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/recent")

            assert response.status_code == 200
            data = response.json()

            assert "searches" in data
            assert "total" in data
            assert len(data["searches"]) == 2

    @pytest.mark.asyncio
    async def test_get_recent_searches_redis_error(self, mock_user, mock_db, mock_search_service):
        """Test Recent Searches bei Redis-Fehler (graceful degradation)."""
        mock_redis = Mock()
        mock_redis._ensure_connection = AsyncMock(side_effect=Exception("Redis not available"))

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/recent")

            # Should still succeed with empty list (graceful degradation)
            assert response.status_code == 200
            data = response.json()
            assert data["searches"] == []
            assert "info" in data


# ========================= Clear Search History Tests =========================


class TestClearSearchHistoryEndpoint:
    """Tests für DELETE /search/recent Endpoint."""

    @pytest.mark.asyncio
    async def test_clear_search_history_success(self, mock_user, mock_db, mock_search_service, mock_redis_manager):
        """Test erfolgreiches Löschen der Suchhistorie."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis_manager):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete("/search/recent")

            assert response.status_code == 200
            data = response.json()

            assert data["erfolg"] is True
            assert "gelöschte_einträge" in data
            assert "nachricht" in data

    @pytest.mark.asyncio
    async def test_clear_search_history_redis_error(self, mock_user, mock_db, mock_search_service):
        """Test Löschen bei Redis-Fehler."""
        from redis.exceptions import RedisError

        mock_redis = Mock()
        mock_redis._ensure_connection = AsyncMock()
        mock_redis._redis = Mock()
        mock_redis._redis.llen = AsyncMock(side_effect=RedisError("Connection failed"))

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete("/search/recent")

            assert response.status_code == 503
            assert "Redis nicht verfügbar" in response.json()["detail"]


# ========================= Trending Searches Endpoint Tests =========================


class TestTrendingSearchesEndpoint:
    """Tests für /search/trending Endpoint."""

    @pytest.mark.asyncio
    async def test_get_trending_success(self, mock_user, mock_db, mock_search_service, mock_redis_manager):
        """Test erfolgreicher Trending Searches Abruf."""
        # Mock database query results
        mock_tag_result = Mock()
        mock_tag_result.all = Mock(return_value=[
            ("wichtig", 10),
            ("2024", 8)
        ])

        mock_count_result = Mock()
        mock_count_result.scalar = Mock(return_value=15)

        mock_db.execute = AsyncMock(side_effect=[mock_tag_result, mock_count_result, mock_count_result])

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis_manager):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/trending")

            assert response.status_code == 200
            data = response.json()

            assert "trending_queries" in data
            assert "trending_tags" in data
            assert "recent_activity" in data
            assert "period_days" in data

    @pytest.mark.asyncio
    async def test_get_trending_with_custom_period(self, mock_user, mock_db, mock_search_service, mock_redis_manager):
        """Test Trending mit benutzerdefiniertem Zeitraum."""
        mock_result = Mock()
        mock_result.all = Mock(return_value=[])
        mock_count_result = Mock()
        mock_count_result.scalar = Mock(return_value=0)
        mock_db.execute = AsyncMock(side_effect=[mock_result, mock_count_result, mock_count_result])

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis_manager):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/trending",
                    params={"days": 30, "limit": 5}
                )

            assert response.status_code == 200
            data = response.json()
            assert data["period_days"] == 30


# ========================= Search Stats Endpoint Tests =========================


class TestSearchStatsEndpoint:
    """Tests für /search/stats Endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_success(self, mock_user, mock_db, mock_search_service):
        """Test erfolgreicher Stats Abruf."""
        # Mock database query results
        mock_total = Mock()
        mock_total.scalar = Mock(return_value=100)

        mock_status = Mock()
        mock_status.all = Mock(return_value=[
            ("completed", 80),
            ("pending", 15),
            ("error", 5)
        ])

        mock_confidence = Mock()
        mock_confidence.scalar = Mock(return_value=0.875)

        mock_with_text = Mock()
        mock_with_text.scalar = Mock(return_value=90)

        mock_db.execute = AsyncMock(side_effect=[
            mock_total, mock_status, mock_confidence, mock_with_text
        ])

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/stats")

            assert response.status_code == 200
            data = response.json()

            assert "total_documents" in data
            assert "by_status" in data
            assert "average_confidence" in data
            assert "documents_with_text" in data
            assert "documents_without_text" in data

            assert data["total_documents"] == 100
            assert data["documents_with_text"] == 90
            assert data["documents_without_text"] == 10

    @pytest.mark.asyncio
    async def test_get_stats_db_error(self, mock_user, mock_db, mock_search_service):
        """Test Stats bei Datenbankfehler."""
        from sqlalchemy.exc import OperationalError

        mock_db.execute = AsyncMock(
            side_effect=OperationalError("connection error", None, None)
        )

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/stats")

            assert response.status_code == 503
            assert "Datenbankverbindung" in response.json()["detail"]


# ========================= Authentication Tests =========================


class TestSearchAPIAuthentication:
    """Tests für Authentifizierung der Search API."""

    @pytest.mark.asyncio
    async def test_facets_requires_auth(self):
        """Test Facets Endpoint erfordert Authentifizierung."""
        from app.api.v1.search import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/search/facets")

        # Should fail due to missing authentication
        assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_suggest_requires_auth(self):
        """Test Suggest Endpoint erfordert Authentifizierung."""
        from app.api.v1.search import router
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/search/suggest", params={"q": "test"})

        assert response.status_code in [401, 403, 422]


# ========================= German Response Tests =========================


class TestGermanResponses:
    """Tests für deutsche Antwort-Texte."""

    @pytest.mark.asyncio
    async def test_clear_history_german_response(self, mock_user, mock_db, mock_search_service, mock_redis_manager):
        """Test Clear History Response auf Deutsch."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis_manager):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.delete("/search/recent")

            data = response.json()

            # German field names
            assert "erfolg" in data
            assert "gelöschte_einträge" in data
            assert "nachricht" in data
            assert "Suchhistorie" in data["nachricht"]

    @pytest.mark.asyncio
    async def test_error_messages_german(self, mock_user, mock_db, mock_search_service):
        """Test Fehlermeldungen sind auf Deutsch."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/facets",
                    params={"facet_fields": "invalid_field"}
                )

            assert response.status_code == 400
            error_detail = response.json()["detail"]
            assert "Ungültiges" in error_detail or "Gültige" in error_detail


# ========================= Query Sanitization Tests =========================


class TestQuerySanitization:
    """Tests für Query Sanitization."""

    @pytest.mark.asyncio
    async def test_suggest_sanitizes_query(self, mock_user, mock_db, mock_search_service):
        """Test Autocomplete sanitiert Query."""
        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service), \
             patch("app.core.input_sanitization.sanitize_search_query") as mock_sanitize:
            mock_sanitize.return_value = ("clean_query", [])

            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/suggest",
                    params={"q": "<script>test</script>"}
                )

            # Should call sanitize function
            mock_sanitize.assert_called_once()


# ========================= Edge Cases =========================


class TestSearchAPIEdgeCases:
    """Tests für Grenzfälle."""

    @pytest.mark.asyncio
    async def test_empty_facets(self, mock_user, mock_db, mock_search_service):
        """Test leere Facets Response."""
        mock_search_service.get_facets = AsyncMock(return_value={
            "facets": [],  # Leere Liste, nicht leeres Dict
            "total_documents": 0
        })

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/facets")

            assert response.status_code == 200
            data = response.json()
            assert data["total_documents"] == 0

    @pytest.mark.asyncio
    async def test_no_suggestions_found(self, mock_user, mock_db, mock_search_service):
        """Test keine Vorschläge gefunden."""
        mock_search_service.get_suggestions = AsyncMock(return_value={
            "query": "xyz123",
            "suggestions": [],
            "total": 0
        })

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get(
                    "/search/suggest",
                    params={"q": "xyz123"}
                )

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert len(data["suggestions"]) == 0

    @pytest.mark.asyncio
    async def test_no_popular_tags(self, mock_user, mock_db, mock_search_service):
        """Test keine beliebten Tags vorhanden."""
        mock_result = Mock()
        mock_result.all = Mock(return_value=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.api.v1.search.get_search_service", return_value=mock_search_service):
            from app.api.v1.search import router
            from fastapi import FastAPI

            app = FastAPI()

            async def override_user():
                return mock_user

            async def override_db():
                yield mock_db

            from app.api.dependencies import get_current_user, get_db
            app.dependency_overrides[get_current_user] = override_user
            app.dependency_overrides[get_db] = override_db
            app.include_router(router)

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/search/popular-tags")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 0
            assert len(data["tags"]) == 0


# ========================= Save Search History Helper Tests =========================


class TestSaveSearchToHistory:
    """Tests für save_search_to_history Helper-Funktion."""

    @pytest.mark.asyncio
    async def test_save_search_success(self, mock_redis_manager):
        """Test erfolgreiche Speicherung einer Suche."""
        with patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis_manager):
            from app.api.v1.search import save_search_to_history

            result = await save_search_to_history(
                user_id="user_123",
                query="Rechnung 2024",
                results_count=15,
                filters={"document_type": "rechnung"}
            )

            assert result is True
            mock_redis_manager._redis.lpush.assert_called_once()
            mock_redis_manager._redis.ltrim.assert_called_once()
            mock_redis_manager._redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_empty_query_skipped(self, mock_redis_manager):
        """Test leere Query wird nicht gespeichert."""
        with patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis_manager):
            from app.api.v1.search import save_search_to_history

            result = await save_search_to_history(
                user_id="user_123",
                query="",
                results_count=0
            )

            assert result is False
            mock_redis_manager._redis.lpush.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_search_redis_error(self):
        """Test Fehlerbehandlung bei Redis-Fehler."""
        mock_redis = Mock()
        mock_redis._ensure_connection = AsyncMock(side_effect=Exception("Redis error"))

        with patch("app.core.redis_state.RedisStateManager.get_instance", return_value=mock_redis):
            from app.api.v1.search import save_search_to_history

            result = await save_search_to_history(
                user_id="user_123",
                query="Test",
                results_count=5
            )

            # Should return False on error (graceful degradation)
            assert result is False
