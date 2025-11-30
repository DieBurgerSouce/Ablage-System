"""
Rate Limit Middleware for Ablage-System OCR API
Custom middleware for advanced rate limiting with user roles and German error messages

Created: 2025-11-26
Features:
- Dynamic rate limits based on user role (free, premium, admin)
- IP whitelisting for trusted services
- German error messages
- Detailed logging and monitoring
- WebSocket endpoint exclusion
"""

from typing import Callable, Optional
from datetime import datetime, timezone

import structlog
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.rate_limiting import (
    limiter,
    ip_whitelist,
    rate_limit_metrics,
    get_remote_address,
    RedisRateLimitStorage
)
from app.core.config import settings

logger = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Custom rate limit middleware with role-based limits and German error messages.

    Features:
    - Dynamic rate limits based on user tier
    - IP whitelisting
    - WebSocket exclusion
    - German error messages
    - Prometheus metrics integration
    """

    # Paths excluded from rate limiting
    EXCLUDED_PATHS = {
        "/health",  # Health check endpoint
        "/docs",  # API documentation
        "/redoc",  # API documentation
        "/openapi.json",  # OpenAPI schema
        "/ws",  # WebSocket endpoints
        "/metrics",  # Prometheus metrics
    }

    # WebSocket path prefixes
    WEBSOCKET_PREFIXES = [
        "/ws/",
        "/websocket/",
    ]

    def __init__(
        self,
        app: ASGIApp,
        redis_storage: Optional[RedisRateLimitStorage] = None
    ):
        """
        Initialize rate limit middleware.

        Args:
            app: ASGI application
            redis_storage: Optional Redis storage backend
        """
        super().__init__(app)
        self.redis_storage = redis_storage

    def is_excluded_path(self, path: str) -> bool:
        """
        Check if path is excluded from rate limiting.

        Args:
            path: Request path

        Returns:
            True if path should be excluded
        """
        # Check exact matches
        if path in self.EXCLUDED_PATHS:
            return True

        # Check WebSocket prefixes
        for prefix in self.WEBSOCKET_PREFIXES:
            if path.startswith(prefix):
                return True

        return False

    def is_websocket_request(self, request: Request) -> bool:
        """
        Check if request is a WebSocket upgrade request.

        Args:
            request: FastAPI request object

        Returns:
            True if WebSocket request
        """
        upgrade_header = request.headers.get("upgrade", "").lower()
        return upgrade_header == "websocket"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """
        Process request with rate limiting.

        Args:
            request: FastAPI request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response object
        """
        # Record request for metrics
        rate_limit_metrics.record_request()

        # Skip rate limiting if disabled
        if not settings.RATE_LIMIT_ENABLED:
            return await call_next(request)

        # Skip excluded paths
        if self.is_excluded_path(request.url.path):
            return await call_next(request)

        # Skip WebSocket requests
        if self.is_websocket_request(request):
            logger.debug(
                "rate_limit_skipped_websocket",
                path=request.url.path
            )
            return await call_next(request)

        # Check IP whitelist
        client_ip = get_remote_address(request)
        if ip_whitelist.is_whitelisted(client_ip):
            rate_limit_metrics.record_whitelisted()
            logger.debug(
                "rate_limit_whitelisted",
                ip=client_ip,
                path=request.url.path
            )
            return await call_next(request)

        # Get user information for tier-based limiting
        user = getattr(request.state, "user", None)
        user_tier = self._get_user_tier(user)

        # Determine rate limit based on endpoint and user tier
        rate_limit = self._get_rate_limit_for_endpoint(
            request.url.path,
            user_tier
        )

        # Check rate limit
        is_allowed, retry_after = await self._check_rate_limit(
            request=request,
            rate_limit=rate_limit,
            user=user
        )

        if not is_allowed:
            rate_limit_metrics.record_rate_limited()
            return self._create_rate_limit_error_response(
                request=request,
                retry_after=retry_after
            )

        # Add rate limit headers to response
        response = await call_next(request)
        self._add_rate_limit_headers(response, rate_limit)

        return response

    def _get_user_tier(self, user: Optional[object]) -> str:
        """
        Get user tier for rate limiting.

        Args:
            user: User object from request state

        Returns:
            User tier string (free, premium, admin)
        """
        if not user:
            return "free"

        if getattr(user, "is_admin", False):
            return "admin"

        return getattr(user, "tier", "free")

    def _get_rate_limit_for_endpoint(
        self,
        path: str,
        user_tier: str
    ) -> dict:
        """
        Determine rate limit configuration for endpoint and user tier.

        Args:
            path: Request path
            user_tier: User tier (free, premium, admin)

        Returns:
            Rate limit configuration dictionary
        """
        # Authentication endpoints (IP-based)
        if path.startswith("/api/v1/auth/login"):
            return {"limit": 5, "window": 900}  # 5 per 15 minutes

        if path.startswith("/api/v1/auth/register"):
            return {"limit": 3, "window": 3600}  # 3 per hour

        if path.startswith("/api/v1/auth/refresh"):
            return {"limit": 20, "window": 60}  # 20 per minute

        # OCR endpoints (tier-based)
        if path.startswith("/ocr/process") or path.startswith("/api/v1/ocr/process"):
            if user_tier == "admin":
                return {"limit": 10000, "window": 3600}  # Unlimited
            elif user_tier == "premium":
                return {"limit": 100, "window": 3600}  # 100 per hour
            else:
                return {"limit": 10, "window": 3600}  # 10 per hour (free)

        if path.startswith("/ocr/batch") or path.startswith("/api/v1/ocr/batch"):
            if user_tier == "admin":
                return {"limit": 1000, "window": 3600}  # Unlimited
            elif user_tier == "premium":
                return {"limit": 50, "window": 3600}  # 50 per hour
            else:
                return {"limit": 5, "window": 3600}  # 5 per hour (free)

        # GPU status endpoint
        if path.startswith("/gpu/status"):
            return {"limit": 60, "window": 60}  # 60 per minute

        # General API endpoints
        return {"limit": 100, "window": 60}  # 100 per minute (default)

    async def _check_rate_limit(
        self,
        request: Request,
        rate_limit: dict,
        user: Optional[object]
    ) -> tuple[bool, Optional[int]]:
        """
        Check if request exceeds rate limit.

        Args:
            request: FastAPI request object
            rate_limit: Rate limit configuration
            user: User object

        Returns:
            Tuple of (is_allowed, retry_after_seconds)
        """
        # Build rate limit key
        if user and hasattr(user, "id"):
            key_prefix = f"user:{user.id}"
        else:
            key_prefix = f"ip:{get_remote_address(request)}"

        # Create unique key for endpoint and time window
        window_start = int(datetime.now(timezone.utc).timestamp() / rate_limit["window"])
        rate_limit_key = f"ratelimit:{key_prefix}:{request.url.path}:{window_start}"

        # Check Redis if available
        if self.redis_storage and self.redis_storage.is_available:
            try:
                current_count = await self.redis_storage.increment(
                    rate_limit_key,
                    rate_limit["window"]
                )

                if current_count > rate_limit["limit"]:
                    # Calculate retry after
                    retry_after = rate_limit["window"] - (
                        int(datetime.now(timezone.utc).timestamp()) % rate_limit["window"]
                    )
                    return False, retry_after

                return True, None

            except Exception as e:
                logger.error(
                    "rate_limit_check_error",
                    key=rate_limit_key,
                    error=str(e)
                )
                rate_limit_metrics.record_error()
                # Fail-open: allow request on error
                return True, None

        # If Redis not available, allow request (graceful degradation)
        logger.warning(
            "rate_limit_redis_unavailable",
            path=request.url.path,
            action="allowing_request"
        )
        return True, None

    def _create_rate_limit_error_response(
        self,
        request: Request,
        retry_after: Optional[int]
    ) -> JSONResponse:
        """
        Create German error response for rate limit exceeded.

        Args:
            request: FastAPI request object
            retry_after: Seconds until rate limit resets

        Returns:
            JSONResponse with German error message
        """
        user = getattr(request.state, "user", None)
        user_id = user.id if user else None

        # Log rate limit violation
        logger.warning(
            "rate_limit_exceeded",
            path=request.url.path,
            user_id=user_id,
            ip=get_remote_address(request),
            retry_after=retry_after
        )

        # Create German error message
        retry_after_seconds = retry_after or 60

        error_response = {
            "fehler": "Ratenlimit überschritten",
            "nachricht": (
                "Sie haben zu viele Anfragen gesendet. "
                f"Bitte versuchen Sie es in {retry_after_seconds} Sekunden erneut."
            ),
            "details": {
                "pfad": request.url.path,
                "wiederholen_nach_sekunden": retry_after_seconds,
                "zeitstempel": datetime.now(timezone.utc).isoformat()
            },
            "hinweis": (
                "Wenn Sie häufiger auf diese API zugreifen müssen, "
                "erwägen Sie ein Upgrade auf einen Premium-Account."
            )
        }

        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=error_response,
            headers={
                "Retry-After": str(retry_after_seconds),
                "X-RateLimit-Reset": str(
                    int(datetime.now(timezone.utc).timestamp()) + retry_after_seconds
                ),
                "Content-Type": "application/json; charset=utf-8"
            }
        )

    def _add_rate_limit_headers(
        self,
        response: Response,
        rate_limit: dict
    ) -> None:
        """
        Add rate limit information headers to response.

        Standard Headers (RFC 6585 / IETF draft-polli-ratelimit-headers):
        - X-RateLimit-Limit: Maximum requests allowed in window
        - X-RateLimit-Window: Window size in seconds
        - X-RateLimit-Reset: Unix timestamp when limit resets

        Args:
            response: Response object
            rate_limit: Rate limit configuration
        """
        import time

        # Standard rate limit headers
        response.headers["X-RateLimit-Limit"] = str(rate_limit["limit"])
        response.headers["X-RateLimit-Window"] = str(rate_limit["window"])

        # Calculate reset timestamp (current time + window)
        reset_timestamp = int(time.time()) + rate_limit["window"]
        response.headers["X-RateLimit-Reset"] = str(reset_timestamp)

        # Policy header (IETF draft format)
        response.headers["X-RateLimit-Policy"] = f"{rate_limit['limit']};w={rate_limit['window']}"


class DevelopmentRateLimitBypass(BaseHTTPMiddleware):
    """
    Middleware to bypass rate limiting in development mode.

    This middleware should be added before RateLimitMiddleware
    when running in development mode.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """
        Bypass rate limiting in development mode.

        Args:
            request: FastAPI request object
            call_next: Next middleware/endpoint in chain

        Returns:
            Response object
        """
        if settings.DEBUG:
            logger.debug(
                "rate_limit_bypassed_development_mode",
                path=request.url.path
            )

        return await call_next(request)


# ==================== Role-Based Rate Limit Checker ====================

class RoleBasedRateLimitChecker:
    """Helper class to check rate limits based on user roles."""

    def __init__(self, redis_storage: Optional[RedisRateLimitStorage] = None):
        """
        Initialize role-based rate limit checker.

        Args:
            redis_storage: Optional Redis storage backend
        """
        self.redis_storage = redis_storage

    async def check_user_quota(
        self,
        user_id: str,
        quota_type: str,
        tier: str = "free"
    ) -> dict:
        """
        Check user's remaining quota for a specific action.

        Args:
            user_id: User identifier
            quota_type: Type of quota (e.g., "ocr_daily", "batch_hourly")
            tier: User tier (free, premium, admin)

        Returns:
            Dictionary with quota information
        """
        # Define quotas per tier
        quotas = {
            "free": {
                "ocr_hourly": 10,
                "ocr_daily": 50,
                "batch_hourly": 5
            },
            "premium": {
                "ocr_hourly": 100,
                "ocr_daily": 1000,
                "batch_hourly": 50
            },
            "admin": {
                "ocr_hourly": 10000,
                "ocr_daily": 100000,
                "batch_hourly": 1000
            }
        }

        # Define time windows for quota types
        quota_windows = {
            "ocr_hourly": 3600,      # 1 hour
            "ocr_daily": 86400,       # 24 hours
            "batch_hourly": 3600      # 1 hour
        }

        max_quota = quotas.get(tier, {}).get(quota_type, 0)
        window = quota_windows.get(quota_type, 3600)

        if not self.redis_storage or not self.redis_storage.is_available:
            return {
                "allowed": True,
                "remaining": max_quota,
                "limit": max_quota,
                "reason": "redis_unavailable"
            }

        # Build Redis key for quota tracking
        # Use time-windowed key to auto-expire old quota data
        window_start = int(datetime.now(timezone.utc).timestamp() / window)
        quota_key = f"quota:{user_id}:{quota_type}:{window_start}"

        try:
            # Get current usage from Redis
            current_usage = await self._get_quota_usage(quota_key)
            remaining = max(0, max_quota - current_usage)

            # Calculate reset time
            current_time = int(datetime.now(timezone.utc).timestamp())
            reset_at = (window_start + 1) * window
            seconds_until_reset = reset_at - current_time

            return {
                "allowed": remaining > 0,
                "remaining": remaining,
                "limit": max_quota,
                "used": current_usage,
                "tier": tier,
                "reset_in_seconds": seconds_until_reset,
                "reset_at_timestamp": reset_at
            }

        except Exception as e:
            logger.error(
                "quota_check_failed",
                user_id=user_id,
                quota_type=quota_type,
                error=str(e)
            )
            # Fail-open: allow request on error
            return {
                "allowed": True,
                "remaining": max_quota,
                "limit": max_quota,
                "reason": "quota_check_error",
                "error": str(e)
            }

    async def _get_quota_usage(self, quota_key: str) -> int:
        """
        Get current quota usage from Redis.

        Args:
            quota_key: Redis key for quota tracking

        Returns:
            Current usage count
        """
        if not self.redis_storage or not self.redis_storage.is_available:
            return 0

        try:
            # Use the Redis storage's internal connection
            if self.redis_storage._redis:
                value = await self.redis_storage._redis.get(quota_key)
                return int(value) if value else 0
        except Exception as e:
            logger.warning(
                "quota_usage_query_failed",
                key=quota_key,
                error=str(e)
            )

        return 0

    async def increment_quota(
        self,
        user_id: str,
        quota_type: str
    ) -> bool:
        """
        Increment quota usage for a user action.

        Args:
            user_id: User identifier
            quota_type: Type of quota (e.g., "ocr_daily", "batch_hourly")

        Returns:
            True if increment successful
        """
        # Define time windows for quota types
        quota_windows = {
            "ocr_hourly": 3600,
            "ocr_daily": 86400,
            "batch_hourly": 3600
        }

        window = quota_windows.get(quota_type, 3600)
        window_start = int(datetime.now(timezone.utc).timestamp() / window)
        quota_key = f"quota:{user_id}:{quota_type}:{window_start}"

        if not self.redis_storage or not self.redis_storage.is_available:
            logger.warning(
                "quota_increment_skipped",
                reason="redis_unavailable",
                user_id=user_id,
                quota_type=quota_type
            )
            return False

        try:
            # Increment counter with expiry
            await self.redis_storage.increment(quota_key, window)
            return True

        except Exception as e:
            logger.error(
                "quota_increment_failed",
                user_id=user_id,
                quota_type=quota_type,
                error=str(e)
            )
            return False


# ==================== Monitoring Functions ====================

def get_rate_limit_stats() -> dict:
    """
    Get rate limiting statistics for monitoring.

    Returns:
        Dictionary with rate limit statistics
    """
    return {
        "metrics": rate_limit_metrics.get_stats(),
        "whitelist": {
            "total_ips": len(ip_whitelist.get_all()),
            "ips": list(ip_whitelist.get_all())
        },
        "configuration": {
            "enabled": settings.RATE_LIMIT_ENABLED,
            "redis_available": (
                limiter.storage is not None
                if hasattr(limiter, "storage") else False
            ),
            "default_limit": settings.RATE_LIMIT_REQUESTS_PER_MINUTE
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
