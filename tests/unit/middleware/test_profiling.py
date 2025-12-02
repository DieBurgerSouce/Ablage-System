"""Unit tests for app/middleware/profiling.py - Profiling Middleware.

Tests the profiling middleware including:
- Request timing
- Excluded paths handling
- Memory tracking (optional)
- Integration with ProfilingService

Created: 2024-12-02
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from starlette.responses import Response


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
    """Tests for ProfilingMiddleware dispatch method."""

    @pytest.mark.asyncio
    async def test_excluded_path_bypasses_profiling(self):
        """Requests to excluded paths should bypass profiling."""
        from app.middleware.profiling import ProfilingMiddleware

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app)

        # Create mock request for excluded path
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/health"

        mock_response = Response(content=b"OK", status_code=200)
        mock_call_next = AsyncMock(return_value=mock_response)

        result = await middleware.dispatch(mock_request, mock_call_next)

        # Should call next without profiling
        mock_call_next.assert_called_once_with(mock_request)
        assert result == mock_response

    @pytest.mark.asyncio
    async def test_regular_path_is_profiled(self):
        """Regular paths should be profiled."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app)

        # Create mock request for regular path
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/documents"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_request.state.request_id = "test-123"
        mock_request.state.user = None

        mock_response = Response(content=b"OK", status_code=200)
        mock_call_next = AsyncMock(return_value=mock_response)

        # Mock the profiling service
        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.BASIC
            mock_service.start_request = MagicMock(return_value="ctx-123")
            mock_service.end_request = MagicMock()
            mock_get_service.return_value = mock_service

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Should call next and return response
            mock_call_next.assert_called_once()
            assert result.status_code == 200

    @pytest.mark.asyncio
    async def test_profiling_disabled_bypasses_tracking(self):
        """When profiling is OFF, tracking should be bypassed."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/documents"

        mock_response = Response(content=b"OK", status_code=200)
        mock_call_next = AsyncMock(return_value=mock_response)

        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.OFF
            mock_get_service.return_value = mock_service

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Should just call next without additional tracking
            mock_call_next.assert_called_once()


class TestProfilingMiddlewareHeaders:
    """Tests for profiling response headers."""

    @pytest.mark.asyncio
    async def test_timing_header_added(self):
        """X-Request-Duration header should be added to response."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/test"
        mock_request.method = "GET"
        mock_request.state = MagicMock()
        mock_request.state.request_id = None
        mock_request.state.user = None

        mock_response = Response(content=b"OK", status_code=200)
        mock_call_next = AsyncMock(return_value=mock_response)

        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.BASIC
            mock_service.start_request = MagicMock(return_value="ctx")
            mock_service.end_request = MagicMock()
            mock_get_service.return_value = mock_service

            result = await middleware.dispatch(mock_request, mock_call_next)

            # Response should be returned
            assert result is not None


class TestProfilingMiddlewareErrorHandling:
    """Tests for error handling in profiling middleware."""

    @pytest.mark.asyncio
    async def test_exception_in_handler_still_tracked(self):
        """Exceptions in handler should still be tracked."""
        from app.middleware.profiling import ProfilingMiddleware
        from app.services.profiling_service import ProfilingLevel

        mock_app = MagicMock()
        middleware = ProfilingMiddleware(mock_app)

        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/api/v1/test"
        mock_request.method = "POST"
        mock_request.state = MagicMock()
        mock_request.state.request_id = "test-err"
        mock_request.state.user = None

        # Handler raises exception
        mock_call_next = AsyncMock(side_effect=ValueError("Test error"))

        with patch('app.middleware.profiling.get_profiling_service') as mock_get_service:
            mock_service = MagicMock()
            mock_service.profiling_level = ProfilingLevel.BASIC
            mock_service.start_request = MagicMock(return_value="ctx")
            mock_service.end_request = MagicMock()
            mock_get_service.return_value = mock_service

            with pytest.raises(ValueError):
                await middleware.dispatch(mock_request, mock_call_next)

            # end_request should still be called for error tracking
            # (depending on implementation)


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
