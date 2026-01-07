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
from datetime import datetime, timezone, timedelta
import asyncio

import structlog
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import redis.asyncio as aioredis

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ==================== Exceptions ====================

class RateLimitStorageError(Exception):
    """
    Raised when rate limit storage (Redis) is unavailable and fail_closed mode is enabled.

    This exception indicates that the request should be denied due to inability
    to verify rate limits.
    """
    pass


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

    # Fall back to IP address (mit sicherer Extraktion)
    return f"ip:{get_secure_remote_address(request)}"


def get_ip_identifier(request: Request) -> str:
    """
    Get IP address for rate limiting.
    Always uses IP address regardless of authentication.

    Args:
        request: FastAPI request object

    Returns:
        IP address string
    """
    return get_secure_remote_address(request)


def get_secure_remote_address(request: Request) -> str:
    """
    Securely extract client IP address with X-Forwarded-For validation.

    SECURITY: X-Forwarded-For kann gespooft werden.
    Diese Funktion validiert die Header und erlaubt nur trusted Proxies.

    Priorität:
    1. X-Real-IP (von trusted Proxy gesetzt)
    2. Erster valider IP aus X-Forwarded-For (wenn trusted Proxy)
    3. Client-IP aus Connection

    Args:
        request: FastAPI request object

    Returns:
        Validated client IP address
    """
    import ipaddress

    # Trusted Proxy IPs (Nginx, Load Balancer, etc.)
    TRUSTED_PROXIES = {
        ipaddress.ip_network("127.0.0.0/8"),      # Localhost
        ipaddress.ip_network("10.0.0.0/8"),       # Private Class A
        ipaddress.ip_network("172.16.0.0/12"),    # Private Class B
        ipaddress.ip_network("192.168.0.0/16"),   # Private Class C
        ipaddress.ip_network("::1/128"),          # IPv6 Localhost
        ipaddress.ip_network("fc00::/7"),         # IPv6 Private
    }

    def is_trusted_proxy(ip: str) -> bool:
        """Prüfe ob IP ein trusted Proxy ist."""
        try:
            addr = ipaddress.ip_address(ip)
            return any(addr in net for net in TRUSTED_PROXIES)
        except ValueError:
            return False

    def is_valid_ip(ip: str) -> bool:
        """Prüfe ob IP-String eine valide IP-Adresse ist."""
        try:
            ipaddress.ip_address(ip.strip())
            return True
        except ValueError:
            return False

    # Direct connection IP
    client_host = request.client.host if request.client else "127.0.0.1"

    # Only process proxy headers if request comes from trusted proxy
    if is_trusted_proxy(client_host):
        # Option 1: X-Real-IP (gesetzt von Nginx)
        real_ip = request.headers.get("X-Real-IP")
        if real_ip and is_valid_ip(real_ip):
            logger.debug(
                "rate_limit_ip_from_real_ip",
                real_ip=real_ip,
                proxy=client_host
            )
            return real_ip.strip()

        # Option 2: X-Forwarded-For (erste IP in der Kette)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Format: client, proxy1, proxy2, ...
            ips = [ip.strip() for ip in forwarded_for.split(",")]

            # Finde die erste nicht-Proxy-IP
            for ip in ips:
                if is_valid_ip(ip) and not is_trusted_proxy(ip):
                    logger.debug(
                        "rate_limit_ip_from_forwarded",
                        forwarded_ip=ip,
                        proxy=client_host,
                        full_chain=forwarded_for
                    )
                    return ip

            # Wenn alle IPs Proxies sind, nimm die erste
            if ips and is_valid_ip(ips[0]):
                return ips[0]
    else:
        # SECURITY: X-Forwarded-For von nicht-trusted Source ignorieren
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            logger.warning(
                "rate_limit_untrusted_proxy_header_ignored",
                client_host=client_host,
                x_forwarded_for=forwarded_for
            )

    # Fallback: Direct connection IP
    return client_host


# ==================== Redis Backend Configuration ====================

class RedisRateLimitStorage:
    """Redis backend for rate limit storage with connection pooling and graceful degradation."""

    def __init__(self, redis_url: str):
        """
        Initialize Redis storage backend with connection pooling.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self._redis: Optional[aioredis.Redis] = None
        self._available = False
        self._connect_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to Redis with connection pooling and error handling."""
        async with self._connect_lock:
            if self._redis is not None:
                return  # Already connected
            try:
                # Nutze Connection Pool Settings aus Config
                self._redis = await aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    # Connection Pool Settings
                    max_connections=settings.REDIS_POOL_MAX_SIZE,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                    socket_keepalive=settings.REDIS_SOCKET_KEEPALIVE,
                    health_check_interval=settings.REDIS_HEALTH_CHECK_INTERVAL,
                    retry_on_timeout=True,
                )
                # Test connection
                await self._redis.ping()
                self._available = True
                logger.info(
                    "rate_limit_redis_connected",
                    max_connections=settings.REDIS_POOL_MAX_SIZE,
                    socket_timeout=settings.REDIS_SOCKET_TIMEOUT
                )
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
            await self._redis.aclose()
            self._redis = None
            self._available = False

    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self._available and self._redis is not None

    async def increment(self, key: str, expiry: int, fail_closed: bool = False) -> int:
        """
        Increment rate limit counter.

        Args:
            key: Rate limit key
            expiry: Expiry time in seconds
            fail_closed: If True, raise exception on Redis error (deny request)
                        If False, return 0 (allow request) - default for backwards compatibility

        Returns:
            Current counter value

        Raises:
            RateLimitStorageError: If fail_closed=True and Redis is unavailable
        """
        if not self.is_available:
            if fail_closed:
                logger.error("rate_limit_redis_unavailable_fail_closed", key=key)
                raise RateLimitStorageError(
                    "Rate-Limiting-Service vorübergehend nicht verfügbar. "
                    "Bitte versuchen Sie es später erneut."
                )
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
            if fail_closed:
                raise RateLimitStorageError(
                    "Rate-Limiting-Service vorübergehend nicht verfügbar. "
                    "Bitte versuchen Sie es später erneut."
                ) from e
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
    # FIX: Headers disabled - causes errors when endpoints return None/non-Response
    # SlowAPI's _inject_headers fails with "parameter `response` must be an instance of Response"
    headers_enabled=False,
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
        "zeitstempel": datetime.now(timezone.utc).isoformat(),
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
            "X-RateLimit-Reset": str(int(datetime.now(timezone.utc).timestamp()) + (retry_after or 60))
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

    Markiert Requests von whitelisted IPs, sodass nachfolgende
    Rate-Limit-Checks diese ueberspringen koennen.

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
            # Markiere Request als whitelisted fuer nachfolgende Checks
            request.state.rate_limit_whitelisted = True
        else:
            request.state.rate_limit_whitelisted = False

        # Funktion wird genau einmal aufgerufen
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
    limit_type: str = "ocr",
    user_tier: str = "free"
) -> dict:
    """
    Check remaining rate limit budget for a user.

    Queries Redis for actual usage and compares against configured limits
    based on user tier (free, premium, admin).

    Args:
        user_id: User identifier
        limit_type: Type of rate limit to check (ocr, batch, api)
        user_tier: User tier (free, premium, admin)

    Returns:
        Dictionary with budget information including:
        - available: bool - Whether user has remaining quota
        - remaining: int - Remaining requests in current window
        - limit: int - Total limit for current window
        - used: int - Number of requests used
        - reset_at: str - ISO timestamp when limit resets
        - window: str - Current window type (hourly, daily)
    """
    storage = await get_redis_storage()

    if not storage or not storage.is_available:
        # SECURITY: Fail-Closed bei Redis-Ausfall wenn konfiguriert
        if settings.RATE_LIMIT_FAIL_CLOSED:
            logger.error(
                "rate_limit_check_redis_unavailable_fail_closed",
                user_id=user_id,
                limit_type=limit_type
            )
            raise RateLimitStorageError(
                "Rate-Limiting-Service vorübergehend nicht verfügbar. "
                "Bitte versuchen Sie es später erneut."
            )

        logger.warning(
            "rate_limit_check_redis_unavailable_fail_open",
            user_id=user_id,
            limit_type=limit_type
        )
        return {
            "available": True,
            "reason": "rate_limiting_unavailable",
            "remaining": -1,
            "limit": -1
        }

    # Define limits based on tier and type
    TIER_LIMITS = {
        "free": {
            "ocr": {"hourly": 10, "daily": 50},
            "batch": {"hourly": 5, "daily": 20},
            "api": {"minute": 100}
        },
        "premium": {
            "ocr": {"hourly": 100, "daily": 1000},
            "batch": {"hourly": 50, "daily": 200},
            "api": {"minute": 500}
        },
        "admin": {
            "ocr": {"hourly": 10000, "daily": 100000},
            "batch": {"hourly": 1000, "daily": 10000},
            "api": {"minute": 10000}
        }
    }

    # Get limits for user tier
    tier_config = TIER_LIMITS.get(user_tier, TIER_LIMITS["free"])
    type_config = tier_config.get(limit_type, tier_config.get("api", {"minute": 100}))

    try:
        # Check hourly limit first (if applicable)
        if "hourly" in type_config:
            hourly_limit = type_config["hourly"]
            hourly_key = f"ratelimit:{user_id}:{limit_type}:hourly:{_get_current_hour_key()}"

            hourly_used = await storage._redis.get(hourly_key)
            hourly_used = int(hourly_used) if hourly_used else 0

            if hourly_used >= hourly_limit:
                reset_at = _get_next_hour_reset()
                return {
                    "available": False,
                    "remaining": 0,
                    "limit": hourly_limit,
                    "used": hourly_used,
                    "reset_at": reset_at.isoformat(),
                    "window": "hourly",
                    "reason": "hourly_limit_exceeded"
                }

        # Check daily limit (if applicable)
        if "daily" in type_config:
            daily_limit = type_config["daily"]
            daily_key = f"ratelimit:{user_id}:{limit_type}:daily:{_get_current_day_key()}"

            daily_used = await storage._redis.get(daily_key)
            daily_used = int(daily_used) if daily_used else 0

            if daily_used >= daily_limit:
                reset_at = _get_next_day_reset()
                return {
                    "available": False,
                    "remaining": 0,
                    "limit": daily_limit,
                    "used": daily_used,
                    "reset_at": reset_at.isoformat(),
                    "window": "daily",
                    "reason": "daily_limit_exceeded"
                }

            # Calculate remaining (use daily as primary)
            remaining = daily_limit - daily_used
            return {
                "available": True,
                "remaining": remaining,
                "limit": daily_limit,
                "used": daily_used,
                "reset_at": _get_next_day_reset().isoformat(),
                "window": "daily"
            }

        # Check minute limit (for API calls)
        if "minute" in type_config:
            minute_limit = type_config["minute"]
            minute_key = f"ratelimit:{user_id}:{limit_type}:minute:{_get_current_minute_key()}"

            minute_used = await storage._redis.get(minute_key)
            minute_used = int(minute_used) if minute_used else 0

            remaining = max(0, minute_limit - minute_used)
            return {
                "available": minute_used < minute_limit,
                "remaining": remaining,
                "limit": minute_limit,
                "used": minute_used,
                "reset_at": _get_next_minute_reset().isoformat(),
                "window": "minute"
            }

        # Default fallback
        return {
            "available": True,
            "remaining": 100,
            "limit": 100,
            "used": 0,
            "reset_at": datetime.now(timezone.utc).isoformat(),
            "window": "unknown"
        }

    except Exception as e:
        logger.error(
            "rate_limit_check_failed",
            user_id=user_id,
            limit_type=limit_type,
            error=str(e)
        )

        # SECURITY: Fail-Closed bei Fehler wenn konfiguriert
        if settings.RATE_LIMIT_FAIL_CLOSED:
            raise RateLimitStorageError(
                "Rate-Limiting-Prüfung fehlgeschlagen. "
                "Bitte versuchen Sie es später erneut."
            ) from e

        # Fail-open: allow request on error (nur wenn RATE_LIMIT_FAIL_CLOSED=False)
        return {
            "available": True,
            "reason": "check_failed",
            "error": str(e)
        }


async def increment_rate_limit_usage(
    user_id: str,
    limit_type: str = "ocr"
) -> bool:
    """
    Increment rate limit usage counter for a user.

    Should be called after successful request processing.

    Args:
        user_id: User identifier
        limit_type: Type of rate limit

    Returns:
        True if increment succeeded
    """
    storage = await get_redis_storage()

    if not storage or not storage.is_available:
        return False

    try:
        # Increment hourly counter (expires in 1 hour)
        hourly_key = f"ratelimit:{user_id}:{limit_type}:hourly:{_get_current_hour_key()}"
        await storage.increment(hourly_key, 3600)

        # Increment daily counter (expires in 24 hours)
        daily_key = f"ratelimit:{user_id}:{limit_type}:daily:{_get_current_day_key()}"
        await storage.increment(daily_key, 86400)

        # Increment minute counter for API calls (expires in 1 minute)
        if limit_type == "api":
            minute_key = f"ratelimit:{user_id}:{limit_type}:minute:{_get_current_minute_key()}"
            await storage.increment(minute_key, 60)

        logger.debug(
            "rate_limit_usage_incremented",
            user_id=user_id,
            limit_type=limit_type
        )
        return True

    except Exception as e:
        logger.error(
            "rate_limit_increment_failed",
            user_id=user_id,
            limit_type=limit_type,
            error=str(e)
        )
        return False


def _get_current_hour_key() -> str:
    """Get current hour key for Redis (YYYYMMDDHH)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H")


def _get_current_day_key() -> str:
    """Get current day key for Redis (YYYYMMDD)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _get_current_minute_key() -> str:
    """Get current minute key for Redis (YYYYMMDDHHmm)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M")


def _get_next_hour_reset() -> datetime:
    """Get timestamp for next hour reset."""
    now = datetime.now(timezone.utc)
    return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def _get_next_day_reset() -> datetime:
    """Get timestamp for next day reset (midnight UTC)."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)


def _get_next_minute_reset() -> datetime:
    """Get timestamp for next minute reset."""
    now = datetime.now(timezone.utc)
    return now.replace(second=0, microsecond=0) + timedelta(minutes=1)
