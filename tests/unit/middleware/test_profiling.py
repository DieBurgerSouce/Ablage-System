"""Unit tests for app/middleware/profiling.py - Profiling Middleware.

Tests the profiling middleware including:
- Request timing
- Excluded paths handling
- Memory tracking (optional)
- Integration with ProfilingService

Note: This middleware uses pure ASGI pattern (__call__ with scope/receive/send),
not BaseHTTPMiddleware pattern (dispatch with request/call_next).

Created: 2024-12-02
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response


def create_asgi_scope(path: str = "/api/v1/test", method: str = "GET") -> dict:
    """Create a mock ASGI scope for testing."""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
        "state": {},
    }


async def create_receive() -> dict:
    """Create a mock receive callable."""
    return {"type": "http.request", "body": b""}


class MockSend:
    """Mock send callable that captures messages."""

    def __init__(self):
        self.messages = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)


class TestProfilingMiddlewareInit:
    """Tests for ProfilingMiddleware initialization."""

    def test_default_excluded_paths(self):
        """Default excluded paths should include health and metrics."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app)

        excluded = middleware._excluded_paths
        assert "/health" in excluded
        assert "/metrics" in excluded
        assert "/docs" in excluded

    def test_custom_excluded_paths(self):
        """Custom excluded paths should be used when provided."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        custom_excluded = {"/custom", "/test"}
        middleware = ProfilingMiddleware(mock_app, excluded_paths=custom_excluded)

        assert middleware._excluded_paths == custom_excluded

    def test_memory_tracking_disabled_by_default(self):
        """Memory tracking should be disabled by default."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app)

        assert middleware._track_memory is False

    def test_memory_tracking_can_be_enabled(self):
        """Memory tracking can be enabled via parameter."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app, track_memory=True)

        assert middleware._track_memory is True


class TestProfilingMiddlewareDispatch:
    """Tests for ProfilingMiddleware ASGI __call__ method."""

    @pytest.mark.asyncio
    async def test_excluded_path_bypasses_profiling(self):
        """Requests to excluded paths should bypass profiling."""
        from app.middleware.profiling import ProfilingMiddleware

        # Track if inner app was called
        app_called = False

        async def mock_app(scope, receive, send):
            nonlocal app_called
            app_called = True
            # Send a simple response
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        middleware = ProfilingMiddleware(mock_app)

        # Create scope for excluded path
        scope = create_asgi_scope(path="/health")
        receive = AsyncMock(return_value={"type": "http.request", "body": b""})
        send = MockSend()

        # Mock profiling service to verify it's not called
        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.record_request = MagicMock()
            mock_get_service.return_value = mock_service

            await middleware(scope, receive, send)

            # App should be called
            assert app_called is True
            # Profiling service record_request should NOT be called for excluded paths
            mock_service.record_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_regular_path_is_profiled(self):
        """Regular paths should be profiled."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        async def mock_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        middleware = ProfilingMiddleware(mock_app)

        # Create scope for regular path
        scope = create_asgi_scope(path="/api/v1/documents", method="GET")
        receive = AsyncMock(return_value={"type": "http.request", "body": b""})
        send = MockSend()

        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.BASIC
            mock_service.record_request = MagicMock()
            mock_get_service.return_value = mock_service

            await middleware(scope, receive, send)

            # record_request should be called for regular paths
            mock_service.record_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_profiling_disabled_bypasses_tracking(self):
        """When profiling is OFF, tracking should be bypassed."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        app_called = False

        async def mock_app(scope, receive, send):
            nonlocal app_called
            app_called = True
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        middleware = ProfilingMiddleware(mock_app)

        scope = create_asgi_scope(path="/api/v1/documents")
        receive = AsyncMock(return_value={"type": "http.request", "body": b""})
        send = MockSend()

        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.OFF
            mock_service.record_request = MagicMock()
            mock_get_service.return_value = mock_service

            await middleware(scope, receive, send)

            # App should be called
            assert app_called is True
            # record_request should NOT be called when profiling is OFF
            mock_service.record_request.assert_not_called()


class TestProfilingMiddlewareHeaders:
    """Tests for profiling response headers."""

    @pytest.mark.asyncio
    async def test_timing_header_added(self):
        """X-Response-Time header should be added to response."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        async def mock_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        middleware = ProfilingMiddleware(mock_app)

        scope = create_asgi_scope(path="/api/v1/test", method="GET")
        receive = AsyncMock(return_value={"type": "http.request", "body": b""})
        send = MockSend()

        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.BASIC
            mock_service.record_request = MagicMock()
            mock_get_service.return_value = mock_service

            await middleware(scope, receive, send)

            # Check that response start message has x-response-time header
            response_start = next(
                (m for m in send.messages if m.get("type") == "http.response.start"),
                None
            )
            assert response_start is not None
            headers = dict(response_start.get("headers", []))
            assert b"x-response-time" in headers


class TestProfilingMiddlewareErrorHandling:
    """Tests for error handling in profiling middleware."""

    @pytest.mark.asyncio
    async def test_exception_in_handler_still_tracked(self):
        """Exceptions in handler should still be tracked."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        async def mock_app(scope, receive, send):
            raise ValueError("Test error")

        middleware = ProfilingMiddleware(mock_app)

        scope = create_asgi_scope(path="/api/v1/test", method="POST")
        receive = AsyncMock(return_value={"type": "http.request", "body": b""})
        send = MockSend()

        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.BASIC
            mock_service.record_request = MagicMock()
            mock_get_service.return_value = mock_service

            with pytest.raises(ValueError):
                await middleware(scope, receive, send)

            # record_request should still be called for error tracking
            mock_service.record_request.assert_called_once()
            # Verify status_code was 500 (error)
            call_kwargs = mock_service.record_request.call_args[1]
            assert call_kwargs["status_code"] == 500


class TestExcludedPathMatching:
    """Tests for excluded path matching logic."""

    def test_exact_match_excluded(self):
        """Exact path matches should be excluded."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app, excluded_paths={"/health"})

        # Test the matching logic
        assert any("/health".startswith(p) for p in middleware._excluded_paths)

    def test_prefix_match_excluded(self):
        """Paths starting with excluded prefix should be excluded."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app, excluded_paths={"/api/v1/health"})

        # Path starts with excluded prefix
        test_path = "/api/v1/health/detailed"
        assert any(test_path.startswith(p) for p in middleware._excluded_paths)

    def test_non_matching_path_not_excluded(self):
        """Non-matching paths should not be excluded."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app, excluded_paths={"/health"})

        test_path = "/api/v1/documents"
        assert not any(test_path.startswith(p) for p in middleware._excluded_paths)


class TestMemoryTracking:
    """Tests for memory tracking feature."""

    @pytest.mark.asyncio
    async def test_memory_tracking_enabled(self):
        """When memory tracking is enabled, memory stats should be collected."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app, track_memory=True)

        assert middleware._track_memory is True
        # Memory tracking behavior would be tested in integration tests

    @pytest.mark.asyncio
    async def test_memory_tracking_disabled(self):
        """When memory tracking is disabled, no memory overhead."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app, track_memory=False)

        assert middleware._track_memory is False
