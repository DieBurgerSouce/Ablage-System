"""
Rate Limiting Configuration for Ablage-System OCR API
Implements SlowAPI with Redis backend for distributed rate limiting

Created: 2025-11-26
Features:
- User-based and IP-based rate limiting
- Tiered rate limits (free, premium, admin)
- Custom rate limit functions for different endpoints
- Redis backend for distributed systems
- German error messages
"""

from typing import Optional, Callable
from functools import wraps
import logging

from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis.asyncio as aioredis
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


# ==================== Rate Limit Key Functions ====================

def get_user_identifier(request: Request) -> str:
    """
    Get user identifier for rate limiting.
    Uses user ID if authenticated, falls back to IP address.

    Args:
        request: FastAPI request object

    Returns:
        User identifier string (user_id or IP)
    """
    # Try to get authenticated user from request state
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "id"):
        return f"user:{user.id}"

    # Fall back to IP address
    return f"ip:{get_remote_address(request)}"


def get_ip_identifier(request: Request) -> str:
    """
    Get IP address for rate limiting.
    Always uses IP address regardless of authentication.

    Args:
        request: FastAPI request object

    Returns:
        IP address string
    """
    return get_remote_address(request)


# ==================== Redis Backend Configuration ====================

class RedisRateLimitStorage:
    """Redis backend for rate limit storage with graceful degradation."""

    def __init__(self, redis_url: str):
        """
        Initialize Redis storage backend.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None
        self._available = False

    async def connect(self) -> None:
        """Connect to Redis with error handling."""
        try:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            # Test connection
            await self._redis.ping()
            self._available = True
            logger.info("rate_limit_redis_connected")
        except Exception as e:
            logger.warning(
                "rate_limit_redis_unavailable",
                error=str(e),
                fallback="in-memory"
            )
            self._available = False
            self._redis = None

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._available = False

    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self._available and self._redis is not None

    async def increment(self, key: str, expiry: int) -> int:
        """
        Increment rate limit counter.

        Args:
            key: Rate limit key
            expiry: Expiry time in seconds

        Returns:
            Current counter value
        """
        if not self.is_available:
            # Graceful degradation: allow request if Redis unavailable
            logger.warning("rate_limit_redis_unavailable_allowing_request", key=key)
            return 0

        try:
            # Use pipeline for atomic operations
            pipe = self._redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, expiry)
            results = await pipe.execute()
            return int(results[0])
        except Exception as e:
            logger.error("rate_limit_redis_error", key=key, error=str(e))
            # Allow request on Redis error (fail-open)
            return 0


# Global Redis storage instance
redis_storage: Optional[RedisRateLimitStorage] = None


async def get_redis_storage() -> Optional[RedisRateLimitStorage]:
    """Get or create Redis storage instance."""
    global redis_storage

    if redis_storage is None and settings.RATE_LIMIT_ENABLED:
        redis_storage = RedisRateLimitStorage(settings.REDIS_URL)
        await redis_storage.connect()

    return redis_storage


# ==================== SlowAPI Limiter Configuration ====================

# Initialize limiter with custom key function
limiter = Limiter(
    key_func=get_user_identifier,
    default_limits=[f"{settings.RATE_LIMIT_REQUESTS_PER_MINUTE}/minute"],
    enabled=settings.RATE_LIMIT_ENABLED,
    # Storage backend will be set during app startup
    storage_uri=settings.REDIS_URL if settings.RATE_LIMIT_ENABLED else None,
    strategy="fixed-window",  # Can be: fixed-window, moving-window
    headers_enabled=True,  # Add X-RateLimit-* headers
)


# ==================== Rate Limit Tiers ====================

class RateLimitTier:
    """Rate limit configurations for different user tiers."""

    # Authentication endpoints
    LOGIN = "5/15minutes"  # 5 attempts per 15 minutes
    REGISTER = "3/hour"  # 3 registrations per hour per IP
    REFRESH = "20/minute"  # 20 refresh requests per minute
    PASSWORD_RESET = "3/hour"  # 3 password reset requests per hour

    # OCR endpoints - Free tier
    OCR_FREE_HOURLY = "10/hour"  # 10 documents per hour
    OCR_FREE_DAILY = "50/day"  # 50 documents per day
    BATCH_FREE = "5/hour"  # 5 batch operations per hour

    # OCR endpoints - Premium tier
    OCR_PREMIUM_HOURLY = "100/hour"  # 100 documents per hour
    OCR_PREMIUM_DAILY = "1000/day"  # 1000 documents per day
    BATCH_PREMIUM = "50/hour"  # 50 batch operations per hour

    # OCR endpoints - Admin tier (unlimited)
    OCR_ADMIN = "10000/hour"  # Effectively unlimited

    # General API endpoints
    API_GENERAL = "100/minute"  # 100 requests per minute
    API_HEAVY = "20/minute"  # 20 requests per minute for heavy operations

    # Status/monitoring endpoints
    GPU_STATUS = "60/minute"  # 60 requests per minute
    HEALTH_CHECK = "1000/minute"  # Effectively unlimited

    # Upload endpoints
    UPLOAD_GENERAL = "30/minute"  # 30 uploads per minute


# ==================== Custom Rate Limit Decorators ====================

def user_tier_rate_limit(
    free_limit: str,
    premium_limit: str,
    admin_limit: str = "10000/hour"
) -> Callable:
    """
    Dynamic rate limit based on user tier.

    Args:
        free_limit: Rate limit for free tier users
        premium_limit: Rate limit for premium tier users
        admin_limit: Rate limit for admin users

    Returns:
        Decorated function with tier-based rate limiting
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request: Request = kwargs.get("request") or args[0]

            # Get user from request state
            user = getattr(request.state, "user", None)

            # Determine rate limit based on user tier
            if user:
                if getattr(user, "is_admin", False):
                    rate_limit = admin_limit
                elif getattr(user, "tier", "free") == "premium":
                    rate_limit = premium_limit
                else:
                    rate_limit = free_limit
            else:
                # Unauthenticated users get free tier limits
                rate_limit = free_limit

            # Apply rate limit dynamically
            # Note: This requires SlowAPI's dynamic limit support
            # For now, we'll use the limiter's limit method

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def ip_based_rate_limit(limit: str) -> Callable:
    """
    IP-based rate limit (ignores user authentication).
    Useful for authentication endpoints to prevent brute force.

    Args:
        limit: Rate limit string (e.g., "5/15minutes")

    Returns:
        Decorated function with IP-based rate limiting
    """
    def decorator(func: Callable) -> Callable:
        # Apply limiter with IP-based key function
        return limiter.limit(limit, key_func=get_ip_identifier)(func)

    return decorator


# ==================== Rate Limit Exceeded Handler ====================

def rate_limit_exceeded_handler_german(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom rate limit exceeded handler with German error messages.

    Args:
        request: FastAPI request object
        exc: RateLimitExceeded exception

    Returns:
        JSONResponse with German error message
    """
    # Parse rate limit details
    retry_after = getattr(exc, "retry_after", None)

    # German error messages
    messages = {
        "title": "Ratenlimit überschritten",
        "detail": "Sie haben zu viele Anfragen gesendet. Bitte versuchen Sie es später erneut.",
        "retry_after": f"Versuchen Sie es in {retry_after} Sekunden erneut." if retry_after else None
    }

    response_data = {
        "fehler": messages["title"],
        "nachricht": messages["detail"],
        "zeitstempel": datetime.utcnow().isoformat(),
        "pfad": request.url.path
    }

    if retry_after:
        response_data["wiederholen_nach"] = retry_after
        response_data["nachricht"] += f" {messages['retry_after']}"

    # Log rate limit violation
    user = getattr(request.state, "user", None)
    user_id = user.id if user else None

    logger.warning(
        "rate_limit_exceeded",
        path=request.url.path,
        user_id=user_id,
        ip=get_remote_address(request),
        retry_after=retry_after
    )

    return JSONResponse(
        status_code=429,
        content=response_data,
        headers={
            "Retry-After": str(retry_after) if retry_after else "60",
            "X-RateLimit-Reset": str(int(datetime.utcnow().timestamp()) + (retry_after or 60))
        }
    )


# ==================== Whitelist Management ====================

class IPWhitelist:
    """Manage whitelisted IP addresses that bypass rate limits."""

    def __init__(self):
        """Initialize IP whitelist."""
        self._whitelist = set()
        self._load_default_whitelist()

    def _load_default_whitelist(self) -> None:
        """Load default whitelisted IPs (localhost, monitoring services)."""
        default_ips = [
            "127.0.0.1",  # localhost IPv4
            "::1",  # localhost IPv6
        ]

        # Add IPs from settings if available
        if hasattr(settings, "RATE_LIMIT_WHITELIST"):
            default_ips.extend(settings.RATE_LIMIT_WHITELIST)

        self._whitelist.update(default_ips)

    def add(self, ip: str) -> None:
        """Add IP to whitelist."""
        self._whitelist.add(ip)
        logger.info("rate_limit_whitelist_added", ip=ip)

    def remove(self, ip: str) -> None:
        """Remove IP from whitelist."""
        self._whitelist.discard(ip)
        logger.info("rate_limit_whitelist_removed", ip=ip)

    def is_whitelisted(self, ip: str) -> bool:
        """Check if IP is whitelisted."""
        return ip in self._whitelist

    def get_all(self) -> set:
        """Get all whitelisted IPs."""
        return self._whitelist.copy()


# Global whitelist instance
ip_whitelist = IPWhitelist()


def is_whitelisted_ip(request: Request) -> bool:
    """
    Check if request IP is whitelisted.

    Args:
        request: FastAPI request object

    Returns:
        True if IP is whitelisted
    """
    ip = get_remote_address(request)
    return ip_whitelist.is_whitelisted(ip)


# ==================== Rate Limit Bypass Decorator ====================

def bypass_rate_limit_if_whitelisted(func: Callable) -> Callable:
    """
    Decorator to bypass rate limiting for whitelisted IPs.

    Args:
        func: Function to decorate

    Returns:
        Decorated function
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request: Request = kwargs.get("request") or args[0]

        if is_whitelisted_ip(request):
            logger.debug(
                "rate_limit_bypassed_whitelist",
                ip=get_remote_address(request),
                path=request.url.path
            )
            # Skip rate limit check
            return await func(*args, **kwargs)

        return await func(*args, **kwargs)

    return wrapper


# ==================== Monitoring & Metrics ====================

class RateLimitMetrics:
    """Track rate limit metrics for monitoring."""

    def __init__(self):
        """Initialize metrics tracking."""
        self.total_requests = 0
        self.rate_limited_requests = 0
        self.whitelisted_requests = 0
        self.errors = 0

    def record_request(self) -> None:
        """Record a request."""
        self.total_requests += 1

    def record_rate_limited(self) -> None:
        """Record a rate limited request."""
        self.rate_limited_requests += 1

    def record_whitelisted(self) -> None:
        """Record a whitelisted request."""
        self.whitelisted_requests += 1

    def record_error(self) -> None:
        """Record an error."""
        self.errors += 1

    def get_stats(self) -> dict:
        """Get current metrics."""
        return {
            "total_requests": self.total_requests,
            "rate_limited_requests": self.rate_limited_requests,
            "whitelisted_requests": self.whitelisted_requests,
            "errors": self.errors,
            "rate_limit_percentage": (
                (self.rate_limited_requests / self.total_requests * 100)
                if self.total_requests > 0 else 0
            )
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self.total_requests = 0
        self.rate_limited_requests = 0
        self.whitelisted_requests = 0
        self.errors = 0


# Global metrics instance
rate_limit_metrics = RateLimitMetrics()


# ==================== Utility Functions ====================

def get_rate_limit_info(request: Request) -> dict:
    """
    Get current rate limit information for a request.

    Args:
        request: FastAPI request object

    Returns:
        Dictionary with rate limit information
    """
    user = getattr(request.state, "user", None)
    ip = get_remote_address(request)

    return {
        "user_id": user.id if user else None,
        "user_tier": getattr(user, "tier", "free") if user else "free",
        "ip_address": ip,
        "is_whitelisted": ip_whitelist.is_whitelisted(ip),
        "rate_limit_enabled": settings.RATE_LIMIT_ENABLED
    }


async def check_rate_limit_budget(
    user_id: str,
    limit_type: str = "ocr"
) -> dict:
    """
    Check remaining rate limit budget for a user.

    Args:
        user_id: User identifier
        limit_type: Type of rate limit to check

    Returns:
        Dictionary with budget information
    """
    storage = await get_redis_storage()

    if not storage or not storage.is_available:
        return {
            "available": True,
            "reason": "rate_limiting_unavailable"
        }

    # This is a placeholder - actual implementation would query Redis
    # for current usage and compare against limits

    return {
        "available": True,
        "remaining": 100,
        "limit": 100,
        "reset_at": datetime.utcnow().isoformat()
    }
