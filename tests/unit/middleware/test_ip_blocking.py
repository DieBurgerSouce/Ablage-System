# -*- coding: utf-8 -*-
"""
Unit-Tests für IP Blocking Middleware.

Testet:
- IP-Blockierung aus IncidentResponseService
- IP-Blockierung aus Redis
- Whitelist-Funktionalität
- Client-IP-Extraktion (X-Forwarded-For, X-Real-IP)
- Health-Endpoint-Ausnahmen
- Middleware Ein/Aus-Schalter
- Blockierungs-Response-Format

Feinpoliert und durchdacht - Enterprise-grade Security-Tests.
"""

import pytest
from datetime import datetime, timezone
from typing import Set
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_request():
    """Create mock request object."""
    request = Mock()
    request.url = Mock()
    request.url.path = "/api/v1/documents"
    request.headers = {}
    request.client = Mock()
    request.client.host = "192.168.1.100"
    return request


@pytest.fixture
def mock_call_next():
    """Create mock call_next function."""
    async def _call_next(request):
        response = Mock()
        response.status_code = 200
        return response
    return _call_next


@pytest.fixture
def ip_blocking_middleware():
    """Create IP Blocking Middleware instance."""
    from app.middleware.ip_blocking import IPBlockingMiddleware

    mock_app = Mock()
    middleware = IPBlockingMiddleware(
        app=mock_app,
        enabled=True,
        whitelist={"127.0.0.1", "::1", "localhost"}
    )
    return middleware


@pytest.fixture
def disabled_middleware():
    """Create disabled IP Blocking Middleware."""
    from app.middleware.ip_blocking import IPBlockingMiddleware

    mock_app = Mock()
    middleware = IPBlockingMiddleware(
        app=mock_app,
        enabled=False
    )
    return middleware


# ========================= Initialization Tests =========================


class TestMiddlewareInitialization:
    """Tests for middleware initialization."""

    def test_default_whitelist(self):
        """Standardmaessige Whitelist sollte lokale IPs enthalten."""
        from app.middleware.ip_blocking import IPBlockingMiddleware

        middleware = IPBlockingMiddleware(app=Mock())

        assert "127.0.0.1" in middleware.whitelist
        assert "::1" in middleware.whitelist
        assert "localhost" in middleware.whitelist

    def test_custom_whitelist(self):
        """Benutzerdefinierte Whitelist sollte verwendet werden."""
        from app.middleware.ip_blocking import IPBlockingMiddleware

        custom_whitelist = {"10.0.0.1", "10.0.0.2"}
        middleware = IPBlockingMiddleware(
            app=Mock(),
            whitelist=custom_whitelist
        )

        assert middleware.whitelist == custom_whitelist

    def test_enabled_default(self):
        """Middleware sollte standardmaessig aktiviert sein."""
        from app.middleware.ip_blocking import IPBlockingMiddleware

        middleware = IPBlockingMiddleware(app=Mock())

        assert middleware.enabled is True

    def test_disabled_initialization(self):
        """Middleware kann deaktiviert initialisiert werden."""
        from app.middleware.ip_blocking import IPBlockingMiddleware

        middleware = IPBlockingMiddleware(app=Mock(), enabled=False)

        assert middleware.enabled is False


# ========================= Client IP Extraction Tests =========================


class TestClientIPExtraction:
    """Tests for client IP extraction."""

    def test_get_client_ip_direct(self, ip_blocking_middleware, mock_request):
        """Direkte Client-IP sollte extrahiert werden."""
        mock_request.headers = {}

        ip = ip_blocking_middleware._get_client_ip(mock_request)

        assert ip == "192.168.1.100"

    def test_get_client_ip_x_forwarded_for(self, ip_blocking_middleware, mock_request):
        """X-Forwarded-For Header sollte bevorzugt werden."""
        mock_request.headers = {"x-forwarded-for": "203.0.113.50, 70.41.3.18"}

        ip = ip_blocking_middleware._get_client_ip(mock_request)

        assert ip == "203.0.113.50"

    def test_get_client_ip_x_real_ip(self, ip_blocking_middleware, mock_request):
        """X-Real-IP Header sollte als Fallback verwendet werden."""
        mock_request.headers = {"x-real-ip": "198.51.100.25"}

        ip = ip_blocking_middleware._get_client_ip(mock_request)

        assert ip == "198.51.100.25"

    def test_get_client_ip_priority_x_forwarded_for(self, ip_blocking_middleware, mock_request):
        """X-Forwarded-For sollte vor X-Real-IP priorisiert werden."""
        mock_request.headers = {
            "x-forwarded-for": "203.0.113.50",
            "x-real-ip": "198.51.100.25"
        }

        ip = ip_blocking_middleware._get_client_ip(mock_request)

        assert ip == "203.0.113.50"

    def test_get_client_ip_no_client(self, ip_blocking_middleware, mock_request):
        """Ohne Client sollte 'unknown' zurückgegeben werden."""
        mock_request.headers = {}
        mock_request.client = None

        ip = ip_blocking_middleware._get_client_ip(mock_request)

        assert ip == "unknown"

    def test_get_client_ip_strips_whitespace(self, ip_blocking_middleware, mock_request):
        """Whitespace in IP sollte entfernt werden."""
        mock_request.headers = {"x-forwarded-for": "  203.0.113.50  , 70.41.3.18"}

        ip = ip_blocking_middleware._get_client_ip(mock_request)

        assert ip == "203.0.113.50"


# ========================= Whitelist Tests =========================


class TestWhitelist:
    """Tests for whitelist functionality."""

    @pytest.mark.asyncio
    async def test_whitelisted_ip_allowed(self, ip_blocking_middleware, mock_request, mock_call_next):
        """Whitelisted IP sollte durchgelassen werden."""
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        response = await ip_blocking_middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_custom_whitelist_works(self, mock_request, mock_call_next):
        """Benutzerdefinierte Whitelist sollte funktionieren."""
        from app.middleware.ip_blocking import IPBlockingMiddleware

        middleware = IPBlockingMiddleware(
            app=Mock(),
            whitelist={"10.0.0.1"}
        )
        mock_request.client.host = "10.0.0.1"
        mock_request.headers = {}

        response = await middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200


# ========================= Health Endpoint Tests =========================


class TestHealthEndpoints:
    """Tests for health endpoint exceptions."""

    @pytest.mark.asyncio
    async def test_health_endpoint_always_allowed(self, ip_blocking_middleware, mock_request, mock_call_next):
        """Health-Endpoint sollte immer erreichbar sein."""
        mock_request.url.path = "/health"

        with patch.object(ip_blocking_middleware, '_is_ip_blocked', return_value=(True, "test")):
            response = await ip_blocking_middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_docs_endpoint_always_allowed(self, ip_blocking_middleware, mock_request, mock_call_next):
        """/docs sollte immer erreichbar sein."""
        mock_request.url.path = "/docs"

        with patch.object(ip_blocking_middleware, '_is_ip_blocked', return_value=(True, "test")):
            response = await ip_blocking_middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_openapi_endpoint_always_allowed(self, ip_blocking_middleware, mock_request, mock_call_next):
        """/openapi.json sollte immer erreichbar sein."""
        mock_request.url.path = "/openapi.json"

        with patch.object(ip_blocking_middleware, '_is_ip_blocked', return_value=(True, "test")):
            response = await ip_blocking_middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200


# ========================= Blocking Tests =========================


class TestIPBlocking:
    """Tests for IP blocking functionality."""

    @pytest.mark.asyncio
    async def test_blocked_ip_returns_403(self, ip_blocking_middleware, mock_request, mock_call_next):
        """Blockierte IP sollte 403 erhalten."""
        mock_request.url.path = "/api/v1/documents"
        mock_request.headers = {}

        with patch.object(ip_blocking_middleware, '_is_ip_blocked', return_value=(True, "incident_response_block")):
            response = await ip_blocking_middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_blocked_response_format(self, ip_blocking_middleware, mock_request, mock_call_next):
        """Blockierungs-Response sollte korrektes Format haben."""
        mock_request.url.path = "/api/v1/documents"
        mock_request.headers = {}

        with patch.object(ip_blocking_middleware, '_is_ip_blocked', return_value=(True, "test_block")):
            response = await ip_blocking_middleware.dispatch(mock_request, mock_call_next)

        # Check response is JSONResponse
        assert response.status_code == 403
        assert "X-Blocked-Reason" in response.headers

    @pytest.mark.asyncio
    async def test_unblocked_ip_allowed(self, ip_blocking_middleware, mock_request, mock_call_next):
        """Nicht blockierte IP sollte durchgelassen werden."""
        mock_request.url.path = "/api/v1/documents"
        mock_request.headers = {}

        with patch.object(ip_blocking_middleware, '_is_ip_blocked', return_value=(False, "")):
            response = await ip_blocking_middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200


# ========================= Disabled Middleware Tests =========================


class TestDisabledMiddleware:
    """Tests for disabled middleware."""

    @pytest.mark.asyncio
    async def test_disabled_middleware_passes_all(self, disabled_middleware, mock_request, mock_call_next):
        """Deaktivierte Middleware sollte alles durchlassen."""
        mock_request.url.path = "/api/v1/documents"

        response = await disabled_middleware.dispatch(mock_request, mock_call_next)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_disabled_middleware_no_ip_check(self, disabled_middleware, mock_request, mock_call_next):
        """Deaktivierte Middleware sollte keine IP-Prüfung machen."""
        with patch.object(disabled_middleware, '_is_ip_blocked') as mock_check:
            await disabled_middleware.dispatch(mock_request, mock_call_next)

            mock_check.assert_not_called()


# ========================= IP Block Check Tests =========================


class TestIsIPBlocked:
    """Tests for _is_ip_blocked method."""

    @pytest.mark.asyncio
    async def test_check_incident_response_service(self, ip_blocking_middleware):
        """IncidentResponseService sollte geprüft werden."""
        # Der Import erfolgt innerhalb der Funktion, daher patchen wir das Service-Modul
        with patch('app.services.incident_response_service.get_incident_response_service') as mock_get_service:
            mock_service = Mock()
            mock_service.is_ip_blocked.return_value = True
            mock_get_service.return_value = mock_service

            is_blocked, reason = await ip_blocking_middleware._is_ip_blocked("192.168.1.100")

            assert is_blocked is True
            assert reason == "incident_response_block"

    @pytest.mark.asyncio
    async def test_check_redis_fallback(self, ip_blocking_middleware):
        """Redis sollte als Fallback geprüft werden wenn konfiguriert."""
        import sys

        # Mock das redis_client Modul bevor es importiert wird
        mock_redis_module = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "blocked"
        mock_redis_module.get_redis = AsyncMock(return_value=mock_redis)

        with patch('app.services.incident_response_service.get_incident_response_service') as mock_get_service:
            mock_service = Mock()
            mock_service.is_ip_blocked.return_value = False
            mock_get_service.return_value = mock_service

            with patch.dict(sys.modules, {'app.core.redis_client': mock_redis_module}):
                is_blocked, reason = await ip_blocking_middleware._is_ip_blocked("192.168.1.100")

                assert is_blocked is True
                assert reason == "redis_block"

    @pytest.mark.asyncio
    async def test_not_blocked_when_all_clear(self, ip_blocking_middleware):
        """Sollte False zurückgeben wenn IP nicht blockiert."""
        import sys

        mock_redis_module = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis_module.get_redis = AsyncMock(return_value=mock_redis)

        with patch('app.services.incident_response_service.get_incident_response_service') as mock_get_service:
            mock_service = Mock()
            mock_service.is_ip_blocked.return_value = False
            mock_get_service.return_value = mock_service

            with patch.dict(sys.modules, {'app.core.redis_client': mock_redis_module}):
                is_blocked, reason = await ip_blocking_middleware._is_ip_blocked("192.168.1.100")

                assert is_blocked is False
                assert reason == ""

    @pytest.mark.asyncio
    async def test_incident_service_error_continues(self, ip_blocking_middleware):
        """Fehler beim IncidentService sollte nicht blockieren."""
        import sys

        mock_redis_module = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis_module.get_redis = AsyncMock(return_value=mock_redis)

        with patch('app.services.incident_response_service.get_incident_response_service') as mock_get_service:
            mock_get_service.side_effect = Exception("Service unavailable")

            with patch.dict(sys.modules, {'app.core.redis_client': mock_redis_module}):
                is_blocked, reason = await ip_blocking_middleware._is_ip_blocked("192.168.1.100")

                assert is_blocked is False

    @pytest.mark.asyncio
    async def test_redis_error_continues(self, ip_blocking_middleware):
        """Fehler bei Redis sollte nicht blockieren."""
        import sys

        mock_redis_module = MagicMock()
        mock_redis_module.get_redis = AsyncMock(side_effect=Exception("Redis unavailable"))

        with patch('app.services.incident_response_service.get_incident_response_service') as mock_get_service:
            mock_service = Mock()
            mock_service.is_ip_blocked.return_value = False
            mock_get_service.return_value = mock_service

            with patch.dict(sys.modules, {'app.core.redis_client': mock_redis_module}):
                is_blocked, reason = await ip_blocking_middleware._is_ip_blocked("192.168.1.100")

                assert is_blocked is False


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests for create_ip_blocking_middleware factory."""

    def test_create_middleware_enabled(self):
        """Factory sollte aktivierte Middleware erstellen."""
        from app.middleware.ip_blocking import create_ip_blocking_middleware

        factory = create_ip_blocking_middleware(enabled=True)
        middleware = factory(Mock())

        assert middleware.enabled is True

    def test_create_middleware_disabled(self):
        """Factory sollte deaktivierte Middleware erstellen."""
        from app.middleware.ip_blocking import create_ip_blocking_middleware

        factory = create_ip_blocking_middleware(enabled=False)
        middleware = factory(Mock())

        assert middleware.enabled is False

    def test_create_middleware_with_whitelist(self):
        """Factory sollte Whitelist übernehmen."""
        from app.middleware.ip_blocking import create_ip_blocking_middleware

        custom_whitelist = {"10.0.0.1", "10.0.0.2"}
        factory = create_ip_blocking_middleware(whitelist=custom_whitelist)
        middleware = factory(Mock())

        assert middleware.whitelist == custom_whitelist
