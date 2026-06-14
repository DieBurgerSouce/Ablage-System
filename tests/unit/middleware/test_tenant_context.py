"""
Unit tests fuer TenantContextMiddleware.

Testet Mandanten-Kontext-Extraktion und -Propagierung.
"""

import pytest
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock

from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.middleware.tenant_context import TenantContextMiddleware


class TestTenantContextMiddleware:
    """Tests fuer TenantContextMiddleware."""

    @pytest.mark.asyncio
    async def test_exempt_path_skips_tenant_check(self) -> None:
        """Test: Ausgenommene Pfade ueberspringen Mandanten-Pruefung."""
        # Mock Request - request.state als echtes Objekt, damit hasattr
        # aussagekraeftig ist (MagicMock erzeugt jedes Attribut on-the-fly).
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/health"
        request.state = SimpleNamespace()

        # Mock next handler
        call_next = AsyncMock(return_value=Response())

        # Middleware
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(request, call_next)

        # Verify
        assert response is not None
        call_next.assert_called_once()
        # tenant_id sollte nicht gesetzt werden (Exempt-Pfad short-circuited)
        assert not hasattr(request.state, "tenant_id")

    @pytest.mark.asyncio
    async def test_tenant_context_set_from_company_id(self) -> None:
        """Test: tenant_id wird aus company_id gesetzt."""
        company_id = uuid4()

        # Mock Request
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/documents"
        request.state = MagicMock()
        request.state.company_id = company_id
        request.method = "GET"

        # Mock next handler
        call_next = AsyncMock(return_value=Response())

        # Middleware
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(request, call_next)

        # Verify
        assert response is not None
        call_next.assert_called_once()
        assert request.state.tenant_id == company_id

    @pytest.mark.asyncio
    async def test_tenant_context_set_from_string_uuid(self) -> None:
        """Test: tenant_id wird aus String-UUID konvertiert."""
        company_id = str(uuid4())

        # Mock Request
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/documents"
        request.state = MagicMock()
        request.state.company_id = company_id
        request.method = "GET"

        # Mock next handler
        call_next = AsyncMock(return_value=Response())

        # Middleware
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(request, call_next)

        # Verify
        assert response is not None
        call_next.assert_called_once()
        # tenant_id sollte als UUID gesetzt werden
        assert request.state.tenant_id is not None
        assert str(request.state.tenant_id) == company_id

    @pytest.mark.asyncio
    async def test_missing_tenant_context_logs_warning(self) -> None:
        """Test: Fehlender Mandanten-Kontext wird geloggt."""
        # Mock Request
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/documents"
        request.state = MagicMock()
        request.state.company_id = None
        request.method = "GET"

        # Mock next handler
        call_next = AsyncMock(return_value=Response())

        # Middleware
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(request, call_next)

        # Verify - Request wird trotzdem durchgelassen
        assert response is not None
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_invalid_uuid_returns_400(self) -> None:
        """Test: Ungueltige UUID gibt 400 zurueck."""
        # Mock Request
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/documents"
        request.state = MagicMock()
        request.state.company_id = "invalid-uuid"
        request.method = "GET"

        # Mock next handler
        call_next = AsyncMock(return_value=Response())

        # Middleware
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(request, call_next)

        # Verify
        assert isinstance(response, JSONResponse)
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_exempt_paths_list(self) -> None:
        """Test: Alle ausgenommenen Pfade werden korrekt behandelt."""
        exempt_paths = [
            "/api/v1/health",
            "/api/v1/auth/login",
            "/api/v1/auth/register",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/metrics",
        ]

        # Mock next handler
        call_next = AsyncMock(return_value=Response())

        # Middleware
        middleware = TenantContextMiddleware(app=MagicMock())

        for path in exempt_paths:
            # Mock Request - echtes state-Objekt fuer aussagekraeftiges hasattr
            request = MagicMock(spec=Request)
            request.url.path = path
            request.state = SimpleNamespace()

            # Execute
            response = await middleware.dispatch(request, call_next)

            # Verify
            assert response is not None
            # tenant_id sollte nicht gesetzt werden
            assert not hasattr(request.state, "tenant_id")

    @pytest.mark.asyncio
    async def test_error_handling_returns_500(self) -> None:
        """Test: Unerwartete Fehler geben 500 zurueck."""

        # state-Objekt, dessen company_id-Zugriff einen unerwarteten Fehler
        # wirft -> getattr(request.state, "company_id", None) propagiert die
        # RuntimeError in den except-Exception-Zweig der Middleware.
        # (Globales builtins.getattr zu patchen ist zu breit und bricht
        # JSONResponse/structlog -> stattdessen gezielt am state-Objekt.)
        class _RaisingState:
            @property
            def company_id(self):  # type: ignore[no-untyped-def]
                raise RuntimeError("Unexpected error")

        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/documents"
        request.state = _RaisingState()
        request.method = "GET"

        # Mock next handler
        call_next = AsyncMock(return_value=Response())

        # Middleware
        middleware = TenantContextMiddleware(app=MagicMock())

        # Execute
        response = await middleware.dispatch(request, call_next)

        # Verify
        assert isinstance(response, JSONResponse)
        assert response.status_code == 500
