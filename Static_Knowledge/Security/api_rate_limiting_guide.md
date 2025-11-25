# API Rate Limiting Guide

**Ablage-System: Enterprise Document Processing Platform**
**Version:** 1.0.0
**Last Updated:** 2025-11-23
**Status:** Production Implementation Guide

---

## Table of Contents

1. [Overview](#overview)
2. [Rate Limiting Strategies](#rate-limiting-strategies)
3. [Algorithms](#algorithms)
4. [Implementation Architecture](#implementation-architecture)
5. [Redis-Based Rate Limiting](#redis-based-rate-limiting)
6. [FastAPI Integration](#fastapi-integration)
7. [Rate Limit Dimensions](#rate-limit-dimensions)
8. [Headers and Client Communication](#headers-and-client-communication)
9. [Bypass Mechanisms](#bypass-mechanisms)
10. [Monitoring and Alerting](#monitoring-and-alerting)
11. [Testing](#testing)
12. [Performance Considerations](#performance-considerations)
13. [Best Practices](#best-practices)
14. [Migration and Rollout](#migration-and-rollout)
15. [Troubleshooting](#troubleshooting)

---

## Overview

### Purpose

API rate limiting protects the Ablage-System from:
- **Abuse and DDoS attacks**: Malicious actors overwhelming the system
- **Resource exhaustion**: GPU/CPU/database overload from excessive requests
- **Fair resource allocation**: Ensuring all users get reasonable access
- **Cost control**: Managing infrastructure costs for on-premises deployment
- **Quality of Service (QoS)**: Maintaining performance for all users

### Philosophy

Rate limiting in Ablage-System follows these principles:

1. **Fair**: All users get proportional access based on their tier
2. **Transparent**: Clear communication via HTTP headers
3. **Graceful**: Informative error messages in German
4. **Distributed**: Works across multiple backend instances
5. **Flexible**: Different limits for different endpoints/users
6. **Monitorable**: Comprehensive metrics for observability

### Scope

This guide covers:
- Token bucket and sliding window algorithms
- Redis-based distributed rate limiting
- FastAPI middleware implementation
- Multi-dimensional rate limiting (user, IP, endpoint, API key)
- Bypass mechanisms for internal services
- Monitoring with Prometheus and Grafana
- Testing strategies
- Performance optimization

---

## Rate Limiting Strategies

### Strategy Matrix

| Strategy | Use Case | Granularity | Complexity |
|----------|----------|-------------|------------|
| **Global** | Protect entire API | All requests | Low |
| **Per-User** | Fair allocation | Individual users | Medium |
| **Per-IP** | Prevent abuse | IP addresses | Medium |
| **Per-Endpoint** | Protect expensive operations | Specific routes | Medium |
| **Adaptive** | Auto-adjust to load | Dynamic | High |
| **Tiered** | SLA-based limits | User subscription | High |

### Implementation Tiers

```python
from enum import Enum
from dataclasses import dataclass

class UserTier(str, Enum):
    """User subscription tiers with different rate limits."""
    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"
    INTERNAL = "internal"  # Internal services, no limits

@dataclass
class RateLimitConfig:
    """Rate limit configuration for a tier."""
    requests_per_second: int
    requests_per_minute: int
    requests_per_hour: int
    requests_per_day: int
    burst_size: int  # Token bucket capacity
    concurrent_requests: int  # Max simultaneous requests

# Default rate limit configurations
RATE_LIMIT_CONFIGS = {
    UserTier.FREE: RateLimitConfig(
        requests_per_second=2,
        requests_per_minute=60,
        requests_per_hour=500,
        requests_per_day=5000,
        burst_size=10,
        concurrent_requests=5
    ),
    UserTier.BASIC: RateLimitConfig(
        requests_per_second=5,
        requests_per_minute=200,
        requests_per_hour=2000,
        requests_per_day=20000,
        burst_size=20,
        concurrent_requests=10
    ),
    UserTier.PROFESSIONAL: RateLimitConfig(
        requests_per_second=10,
        requests_per_minute=500,
        requests_per_hour=10000,
        requests_per_day=100000,
        burst_size=50,
        concurrent_requests=25
    ),
    UserTier.ENTERPRISE: RateLimitConfig(
        requests_per_second=50,
        requests_per_minute=2000,
        requests_per_hour=50000,
        requests_per_day=500000,
        burst_size=100,
        concurrent_requests=100
    ),
    UserTier.INTERNAL: RateLimitConfig(
        requests_per_second=1000,  # Effectively unlimited
        requests_per_minute=60000,
        requests_per_hour=3600000,
        requests_per_day=86400000,
        burst_size=1000,
        concurrent_requests=500
    )
}
```

### Endpoint-Specific Limits

Different endpoints have different costs:

```python
from typing import Dict, Optional

class EndpointLimitMultiplier:
    """Cost multipliers for different endpoint types."""

    # Multipliers applied to base rate limit
    MULTIPLIERS = {
        # Health checks - very permissive
        "GET /health": 0.0,  # No cost
        "GET /metrics": 0.0,  # No cost

        # Read operations - low cost
        "GET /api/v1/documents/": 1.0,  # Base rate
        "GET /api/v1/documents/{id}": 1.0,

        # Write operations - medium cost
        "POST /api/v1/documents/": 2.0,  # 2x cost
        "PUT /api/v1/documents/{id}": 2.0,
        "DELETE /api/v1/documents/{id}": 1.5,

        # OCR operations - high cost (GPU/CPU intensive)
        "POST /api/v1/ocr/process": 10.0,  # 10x cost
        "POST /api/v1/ocr/batch": 20.0,  # 20x cost

        # Search operations - medium-high cost
        "POST /api/v1/search": 5.0,  # 5x cost

        # Admin operations - low cost but restricted by RBAC
        "GET /api/v1/admin/*": 1.0,
        "POST /api/v1/admin/*": 2.0,
    }

    @classmethod
    def get_multiplier(cls, method: str, path: str) -> float:
        """Get cost multiplier for endpoint."""
        key = f"{method} {path}"

        # Exact match
        if key in cls.MULTIPLIERS:
            return cls.MULTIPLIERS[key]

        # Wildcard match
        for pattern, multiplier in cls.MULTIPLIERS.items():
            if pattern.endswith("*") and key.startswith(pattern[:-1]):
                return multiplier

        # Default: standard cost
        return 1.0
```

---

## Algorithms

### Token Bucket Algorithm

The token bucket algorithm is the primary rate limiting algorithm used in Ablage-System.

#### Concept

```
┌─────────────────────────────────────┐
│       Token Bucket                  │
│                                     │
│  ┌───────────────────────────────┐ │
│  │ Tokens: ████████░░░░░░ (8/20) │ │  ← Current tokens
│  └───────────────────────────────┘ │
│                                     │
│  Capacity: 20 tokens               │  ← Burst size
│  Refill Rate: 5 tokens/second      │  ← Sustained rate
│                                     │
└─────────────────────────────────────┘

Request arrives → Consumes 1 token (or cost multiplier)
If tokens available → Allow request
If no tokens → Reject with 429 Too Many Requests
Tokens refill continuously at fixed rate
```

#### Implementation

```python
import time
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

class TokenBucket:
    """Token bucket rate limiter implementation.

    This implementation is thread-safe for single-process use.
    For distributed systems, use RedisTokenBucket instead.
    """

    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        initial_tokens: Optional[int] = None
    ):
        """Initialize token bucket.

        Args:
            capacity: Maximum tokens (burst size)
            refill_rate: Tokens added per second
            initial_tokens: Starting tokens (defaults to capacity)
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.time()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill

        # Calculate tokens to add
        tokens_to_add = elapsed * self.refill_rate

        # Add tokens, cap at capacity
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume tokens.

        Args:
            tokens: Number of tokens to consume (supports fractional)

        Returns:
            True if tokens were consumed, False if insufficient tokens
        """
        self._refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True

        return False

    def peek(self) -> float:
        """Check available tokens without consuming.

        Returns:
            Current number of available tokens
        """
        self._refill()
        return self.tokens

    def time_until_tokens(self, tokens: float = 1.0) -> float:
        """Calculate time until sufficient tokens available.

        Args:
            tokens: Desired number of tokens

        Returns:
            Seconds until tokens available (0 if already available)
        """
        self._refill()

        if self.tokens >= tokens:
            return 0.0

        deficit = tokens - self.tokens
        return deficit / self.refill_rate

    def reset(self) -> None:
        """Reset bucket to full capacity."""
        self.tokens = self.capacity
        self.last_refill = time.time()
```

#### Usage Example

```python
# Create bucket: 10 requests/second, burst of 20
bucket = TokenBucket(capacity=20, refill_rate=10.0)

# Check if request allowed
if bucket.consume(tokens=1.0):
    # Process request
    process_request()
else:
    # Rate limited
    retry_after = bucket.time_until_tokens(1.0)
    raise RateLimitExceeded(retry_after=retry_after)

# Expensive operation consumes more tokens
if bucket.consume(tokens=5.0):  # OCR costs 5x normal request
    process_ocr()
```

### Sliding Window Algorithm

Alternative algorithm that provides smoother rate limiting over time.

#### Concept

```
Time windows:
[======] [======] [======] [======]
   59       60       61       62   (seconds)

Count requests in last N seconds using sliding window:
Current time: 62.5s
Window: 61.5s - 62.5s (1 second window)

Requests in window: 8
Limit: 10 requests/second
Result: ALLOW (2 requests remaining)
```

#### Implementation

```python
from collections import deque
from threading import Lock
import time

class SlidingWindowRateLimiter:
    """Sliding window counter rate limiter.

    More accurate than fixed windows, prevents edge cases
    where users can make 2x requests at window boundaries.
    """

    def __init__(self, max_requests: int, window_seconds: float):
        """Initialize sliding window limiter.

        Args:
            max_requests: Maximum requests in window
            window_seconds: Window size in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: deque = deque()
        self.lock = Lock()

    def _cleanup_old_requests(self, now: float) -> None:
        """Remove requests outside current window."""
        cutoff = now - self.window_seconds

        while self.requests and self.requests[0] < cutoff:
            self.requests.popleft()

    def allow_request(self) -> bool:
        """Check if request is allowed and record it.

        Returns:
            True if request allowed, False if rate limited
        """
        with self.lock:
            now = time.time()
            self._cleanup_old_requests(now)

            if len(self.requests) < self.max_requests:
                self.requests.append(now)
                return True

            return False

    def get_remaining(self) -> int:
        """Get remaining requests in current window."""
        with self.lock:
            now = time.time()
            self._cleanup_old_requests(now)
            return max(0, self.max_requests - len(self.requests))

    def time_until_reset(self) -> float:
        """Get seconds until oldest request expires."""
        with self.lock:
            if not self.requests:
                return 0.0

            now = time.time()
            oldest = self.requests[0]
            reset_time = oldest + self.window_seconds
            return max(0.0, reset_time - now)
```

### Algorithm Comparison

| Feature | Token Bucket | Sliding Window |
|---------|--------------|----------------|
| **Allows bursts** | ✅ Yes | ❌ No |
| **Smooth rate limiting** | ❌ Can be bursty | ✅ Very smooth |
| **Memory usage** | Low (2 floats) | Higher (stores timestamps) |
| **Accuracy** | Good | Excellent |
| **Edge cases** | None | None |
| **Complexity** | Low | Medium |
| **Best for** | General API, GPU workloads | Strict rate limits, billing APIs |

**Recommendation for Ablage-System**: Use **Token Bucket** for most endpoints (allows bursts for batch operations), use **Sliding Window** for billing/admin endpoints requiring strict limits.

---

## Implementation Architecture

### System Architecture

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ HTTP Request
       ▼
┌─────────────────────────────────────────┐
│         FastAPI Application             │
│                                         │
│  ┌───────────────────────────────────┐ │
│  │  RateLimitMiddleware              │ │
│  │  1. Extract identifier (user/IP)  │ │
│  │  2. Check rate limit in Redis     │ │
│  │  3. Allow or reject request       │ │
│  └──────────┬────────────────────────┘ │
│             │                           │
│             ▼                           │
│  ┌───────────────────────────────────┐ │
│  │  Endpoint Handler                 │ │
│  │  (if rate limit passed)           │ │
│  └───────────────────────────────────┘ │
└──────────┬──────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│         Redis Cluster                   │
│                                         │
│  Keys:                                  │
│  - ratelimit:user:{id}:{window}        │
│  - ratelimit:ip:{ip}:{window}          │
│  - ratelimit:endpoint:{path}:{window}  │
│                                         │
│  Values:                                │
│  - Token count (float)                  │
│  - Last refill timestamp                │
│  - Request timestamps (sliding window)  │
└─────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────┐
│      Prometheus Metrics                 │
│  - rate_limit_exceeded_total            │
│  - rate_limit_tokens_remaining          │
│  - rate_limit_check_duration            │
└─────────────────────────────────────────┘
```

### Component Responsibilities

1. **RateLimitMiddleware**: Intercepts all requests, applies rate limiting before routing
2. **RedisTokenBucket**: Distributed token bucket implementation using Redis
3. **RateLimitConfig**: Configuration management for different tiers/endpoints
4. **MetricsCollector**: Records rate limit metrics for monitoring
5. **BypassManager**: Handles whitelisting for internal services

---

## Redis-Based Rate Limiting

### Why Redis?

Redis is ideal for distributed rate limiting because:
- **Atomic operations**: Lua scripting for race-free updates
- **Low latency**: Sub-millisecond response times
- **Distributed**: Works across multiple backend instances
- **Expiry**: Automatic cleanup with TTL
- **Persistence**: Optional persistence for rate limit state

### RedisTokenBucket Implementation

```python
import asyncio
from typing import Optional
import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

class RedisTokenBucket:
    """Distributed token bucket using Redis.

    Uses Redis for atomic operations across multiple backend instances.
    Implements token bucket algorithm with Lua scripting for atomicity.
    """

    # Lua script for atomic token consumption
    CONSUME_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local tokens_requested = tonumber(ARGV[3])
    local now = tonumber(ARGV[4])

    -- Get current state
    local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
    local tokens = tonumber(bucket[1])
    local last_refill = tonumber(bucket[2])

    -- Initialize if doesn't exist
    if tokens == nil then
        tokens = capacity
        last_refill = now
    end

    -- Refill tokens based on elapsed time
    local elapsed = now - last_refill
    local tokens_to_add = elapsed * refill_rate
    tokens = math.min(capacity, tokens + tokens_to_add)

    -- Try to consume
    if tokens >= tokens_requested then
        tokens = tokens - tokens_requested

        -- Update state
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
        redis.call('EXPIRE', key, 3600)  -- 1 hour TTL

        return {1, tokens}  -- Success, remaining tokens
    else
        -- Update last_refill even on failure (for accurate time_until)
        redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
        redis.call('EXPIRE', key, 3600)

        return {0, tokens}  -- Failure, current tokens
    end
    """

    def __init__(
        self,
        redis: Redis,
        key: str,
        capacity: int,
        refill_rate: float
    ):
        """Initialize Redis token bucket.

        Args:
            redis: Redis client (async)
            key: Redis key for this bucket
            capacity: Maximum tokens (burst size)
            refill_rate: Tokens added per second
        """
        self.redis = redis
        self.key = key
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._script_sha: Optional[str] = None

    async def _load_script(self) -> str:
        """Load Lua script into Redis.

        Returns:
            SHA hash of loaded script
        """
        if self._script_sha is None:
            self._script_sha = await self.redis.script_load(self.CONSUME_SCRIPT)
        return self._script_sha

    async def consume(self, tokens: float = 1.0) -> bool:
        """Attempt to consume tokens atomically.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens consumed, False if insufficient
        """
        import time

        try:
            script_sha = await self._load_script()
            now = time.time()

            result = await self.redis.evalsha(
                script_sha,
                1,  # Number of keys
                self.key,
                self.capacity,
                self.refill_rate,
                tokens,
                now
            )

            success = bool(result[0])
            remaining = float(result[1])

            logger.debug(
                "token_bucket_consume",
                key=self.key,
                tokens_requested=tokens,
                success=success,
                remaining=remaining
            )

            return success

        except Exception as e:
            logger.error(
                "redis_token_bucket_error",
                key=self.key,
                error=str(e),
                exc_info=True
            )
            # Fail open: allow request if Redis is down
            return True

    async def peek(self) -> float:
        """Get current token count without consuming.

        Returns:
            Current number of tokens
        """
        import time

        # Use consume with 0 tokens to get current state
        now = time.time()

        bucket = await self.redis.hmget(self.key, 'tokens', 'last_refill')

        if bucket[0] is None:
            return float(self.capacity)

        tokens = float(bucket[0])
        last_refill = float(bucket[1])

        # Calculate refilled tokens
        elapsed = now - last_refill
        tokens_to_add = elapsed * self.refill_rate
        tokens = min(self.capacity, tokens + tokens_to_add)

        return tokens

    async def time_until_tokens(self, tokens: float = 1.0) -> float:
        """Calculate time until sufficient tokens available.

        Args:
            tokens: Desired number of tokens

        Returns:
            Seconds until tokens available (0 if already available)
        """
        current = await self.peek()

        if current >= tokens:
            return 0.0

        deficit = tokens - current
        return deficit / self.refill_rate

    async def reset(self) -> None:
        """Reset bucket to full capacity."""
        import time

        await self.redis.hmset(
            self.key,
            {
                'tokens': self.capacity,
                'last_refill': time.time()
            }
        )
        await self.redis.expire(self.key, 3600)
```

### Redis Key Schema

```python
class RateLimitKeyBuilder:
    """Build Redis keys for rate limiting."""

    PREFIX = "ratelimit"

    @classmethod
    def user_key(cls, user_id: str, window: str = "default") -> str:
        """Key for per-user rate limiting.

        Args:
            user_id: User identifier
            window: Time window (e.g., 'second', 'minute', 'hour', 'day')

        Returns:
            Redis key string
        """
        return f"{cls.PREFIX}:user:{user_id}:{window}"

    @classmethod
    def ip_key(cls, ip: str, window: str = "default") -> str:
        """Key for per-IP rate limiting."""
        return f"{cls.PREFIX}:ip:{ip}:{window}"

    @classmethod
    def endpoint_key(cls, method: str, path: str, window: str = "default") -> str:
        """Key for per-endpoint rate limiting."""
        # Normalize path to avoid too many keys
        normalized_path = path.replace('/', ':')
        return f"{cls.PREFIX}:endpoint:{method}:{normalized_path}:{window}"

    @classmethod
    def api_key_key(cls, api_key_hash: str, window: str = "default") -> str:
        """Key for API key-based rate limiting."""
        return f"{cls.PREFIX}:apikey:{api_key_hash}:{window}"

    @classmethod
    def global_key(cls, window: str = "default") -> str:
        """Key for global rate limiting."""
        return f"{cls.PREFIX}:global:{window}"
```

### Redis Connection Pool

```python
from redis.asyncio import ConnectionPool, Redis
from app.core.config import settings

class RedisManager:
    """Manage Redis connections for rate limiting."""

    _pool: Optional[ConnectionPool] = None

    @classmethod
    async def get_pool(cls) -> ConnectionPool:
        """Get or create Redis connection pool."""
        if cls._pool is None:
            cls._pool = ConnectionPool.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                max_connections=50,
                socket_connect_timeout=2,
                socket_keepalive=True
            )
        return cls._pool

    @classmethod
    async def get_client(cls) -> Redis:
        """Get Redis client from pool."""
        pool = await cls.get_pool()
        return Redis(connection_pool=pool)

    @classmethod
    async def close(cls) -> None:
        """Close Redis connection pool."""
        if cls._pool is not None:
            await cls._pool.disconnect()
            cls._pool = None
```

---

## FastAPI Integration

### Rate Limit Middleware

```python
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import structlog
from typing import Callable
import time

logger = structlog.get_logger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting.

    Applies rate limiting to all requests based on:
    - User ID (from JWT token)
    - IP address (fallback if no user)
    - Endpoint cost multiplier
    - User tier limits
    """

    def __init__(
        self,
        app: ASGIApp,
        redis_client: Redis,
        config: Dict[UserTier, RateLimitConfig]
    ):
        """Initialize rate limit middleware.

        Args:
            app: FastAPI application
            redis_client: Redis client for distributed limiting
            config: Rate limit configurations by tier
        """
        super().__init__(app)
        self.redis = redis_client
        self.config = config

    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """Process request with rate limiting.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware in chain

        Returns:
            HTTP response or 429 Too Many Requests
        """
        start_time = time.time()

        # Extract identifier (user > API key > IP)
        identifier, tier = await self._get_identifier_and_tier(request)

        # Check if bypassed (internal services)
        if await self._should_bypass(request, identifier):
            logger.debug("rate_limit_bypassed", identifier=identifier)
            return await call_next(request)

        # Get endpoint cost multiplier
        cost = self._get_endpoint_cost(request.method, request.url.path)

        # Get rate limit config for tier
        tier_config = self.config.get(tier, self.config[UserTier.FREE])

        # Check rate limit (multiple time windows)
        allowed, retry_after = await self._check_rate_limit(
            identifier=identifier,
            tier_config=tier_config,
            cost=cost
        )

        # Record metrics
        duration = time.time() - start_time
        await self._record_metrics(
            identifier=identifier,
            tier=tier,
            allowed=allowed,
            duration=duration,
            method=request.method,
            path=request.url.path
        )

        if not allowed:
            # Rate limit exceeded
            logger.warning(
                "rate_limit_exceeded",
                identifier=identifier,
                tier=tier,
                method=request.method,
                path=request.url.path,
                retry_after=retry_after
            )

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "fehler": "Anfragelimit überschritten",
                    "nachricht": f"Zu viele Anfragen. Bitte in {retry_after:.1f} Sekunden erneut versuchen.",
                    "retry_after_seconds": retry_after,
                    "tier": tier,
                    "dokumentation": "https://docs.ablage-system.de/rate-limits"
                },
                headers={
                    "Retry-After": str(int(retry_after)),
                    "X-RateLimit-Limit": str(tier_config.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time() + retry_after))
                }
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        await self._add_rate_limit_headers(
            response=response,
            identifier=identifier,
            tier_config=tier_config
        )

        return response

    async def _get_identifier_and_tier(
        self,
        request: Request
    ) -> tuple[str, UserTier]:
        """Extract user identifier and tier from request.

        Priority:
        1. User ID from JWT token
        2. API key from header
        3. IP address (fallback)

        Returns:
            Tuple of (identifier, tier)
        """
        # Try to get user from JWT token
        if hasattr(request.state, "user"):
            user = request.state.user
            return f"user:{user.id}", user.tier

        # Try to get API key from header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # Hash API key for privacy
            import hashlib
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]

            # Look up tier from API key (implement in your service)
            # tier = await api_key_service.get_tier(api_key)
            tier = UserTier.BASIC  # Placeholder

            return f"apikey:{key_hash}", tier

        # Fallback to IP address
        client_ip = request.client.host
        return f"ip:{client_ip}", UserTier.FREE

    async def _should_bypass(
        self,
        request: Request,
        identifier: str
    ) -> bool:
        """Check if request should bypass rate limiting.

        Args:
            request: HTTP request
            identifier: User/IP identifier

        Returns:
            True if should bypass rate limiting
        """
        # Internal service bypass
        if identifier.startswith("user:") and ":internal" in identifier:
            return True

        # Health check endpoints
        if request.url.path in ["/health", "/metrics", "/ready"]:
            return True

        # IP whitelist (for trusted services)
        trusted_ips = getattr(settings, "RATE_LIMIT_BYPASS_IPS", [])
        if request.client.host in trusted_ips:
            return True

        return False

    def _get_endpoint_cost(self, method: str, path: str) -> float:
        """Get cost multiplier for endpoint.

        Args:
            method: HTTP method
            path: Request path

        Returns:
            Cost multiplier
        """
        return EndpointLimitMultiplier.get_multiplier(method, path)

    async def _check_rate_limit(
        self,
        identifier: str,
        tier_config: RateLimitConfig,
        cost: float
    ) -> tuple[bool, float]:
        """Check rate limits across multiple time windows.

        Args:
            identifier: User/IP identifier
            tier_config: Rate limit configuration
            cost: Request cost multiplier

        Returns:
            Tuple of (allowed, retry_after_seconds)
        """
        # Check per-second limit
        bucket_second = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.user_key(identifier, "second"),
            capacity=tier_config.burst_size,
            refill_rate=tier_config.requests_per_second
        )

        if not await bucket_second.consume(cost):
            retry_after = await bucket_second.time_until_tokens(cost)
            return False, retry_after

        # Check per-minute limit
        bucket_minute = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.user_key(identifier, "minute"),
            capacity=tier_config.requests_per_minute,
            refill_rate=tier_config.requests_per_minute / 60.0
        )

        if not await bucket_minute.consume(cost):
            retry_after = await bucket_minute.time_until_tokens(cost)
            return False, retry_after

        # Check per-hour limit
        bucket_hour = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.user_key(identifier, "hour"),
            capacity=tier_config.requests_per_hour,
            refill_rate=tier_config.requests_per_hour / 3600.0
        )

        if not await bucket_hour.consume(cost):
            retry_after = await bucket_hour.time_until_tokens(cost)
            return False, retry_after

        # All limits passed
        return True, 0.0

    async def _add_rate_limit_headers(
        self,
        response: Response,
        identifier: str,
        tier_config: RateLimitConfig
    ) -> None:
        """Add rate limit headers to response.

        Args:
            response: HTTP response
            identifier: User/IP identifier
            tier_config: Rate limit configuration
        """
        # Get remaining tokens from minute bucket
        bucket = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.user_key(identifier, "minute"),
            capacity=tier_config.requests_per_minute,
            refill_rate=tier_config.requests_per_minute / 60.0
        )

        remaining = await bucket.peek()
        reset_time = int(time.time() + 60)  # Next minute

        response.headers["X-RateLimit-Limit"] = str(tier_config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(int(remaining))
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        response.headers["X-RateLimit-Tier"] = tier_config.__class__.__name__

    async def _record_metrics(
        self,
        identifier: str,
        tier: UserTier,
        allowed: bool,
        duration: float,
        method: str,
        path: str
    ) -> None:
        """Record Prometheus metrics for rate limiting.

        Args:
            identifier: User/IP identifier
            tier: User tier
            allowed: Whether request was allowed
            duration: Rate limit check duration
            method: HTTP method
            path: Request path
        """
        from prometheus_client import Counter, Histogram, Gauge

        # Counter for rate limit checks
        rate_limit_checks = Counter(
            'rate_limit_checks_total',
            'Total rate limit checks',
            ['tier', 'allowed', 'method']
        )
        rate_limit_checks.labels(
            tier=tier,
            allowed=str(allowed),
            method=method
        ).inc()

        # Histogram for check duration
        rate_limit_duration = Histogram(
            'rate_limit_check_duration_seconds',
            'Rate limit check duration',
            ['tier']
        )
        rate_limit_duration.labels(tier=tier).observe(duration)

        if not allowed:
            # Counter for exceeded limits
            rate_limit_exceeded = Counter(
                'rate_limit_exceeded_total',
                'Rate limits exceeded',
                ['tier', 'endpoint']
            )
            rate_limit_exceeded.labels(
                tier=tier,
                endpoint=f"{method} {path}"
            ).inc()
```

### FastAPI Application Setup

```python
from fastapi import FastAPI
from app.core.config import settings
from app.middleware.rate_limit import RateLimitMiddleware, RATE_LIMIT_CONFIGS
from app.services.redis_manager import RedisManager

async def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title="Ablage-System API",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc"
    )

    # Get Redis client
    redis = await RedisManager.get_client()

    # Add rate limiting middleware
    app.add_middleware(
        RateLimitMiddleware,
        redis_client=redis,
        config=RATE_LIMIT_CONFIGS
    )

    # Add other middleware...

    return app
```

### Dependency Injection for Endpoints

For fine-grained control, use dependency injection:

```python
from fastapi import Depends, HTTPException, status
from typing import Annotated

async def check_rate_limit(
    request: Request,
    cost: float = 1.0
) -> None:
    """Dependency to check rate limit for endpoint.

    Args:
        request: HTTP request
        cost: Custom cost for this endpoint

    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    # This would be called by middleware, but can also be used directly
    # for endpoints that need custom rate limiting
    pass

# Usage in endpoint
@router.post("/api/v1/ocr/batch")
async def batch_ocr(
    files: List[UploadFile],
    _: Annotated[None, Depends(lambda req: check_rate_limit(req, cost=20.0))]
):
    """Batch OCR endpoint with custom rate limit cost."""
    # Process batch...
    pass
```

---

## Rate Limit Dimensions

### Multi-Dimensional Rate Limiting

Apply rate limits across multiple dimensions simultaneously:

```python
class MultiDimensionalRateLimiter:
    """Apply rate limits across multiple dimensions.

    Checks:
    1. Per-user limits (authenticated users)
    2. Per-IP limits (all requests)
    3. Per-endpoint limits (global per endpoint)
    4. Global limits (entire API)
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    async def check_all_limits(
        self,
        user_id: Optional[str],
        ip_address: str,
        method: str,
        path: str,
        tier: UserTier,
        cost: float = 1.0
    ) -> tuple[bool, Optional[str], float]:
        """Check all rate limit dimensions.

        Args:
            user_id: User ID (None if unauthenticated)
            ip_address: Client IP address
            method: HTTP method
            path: Request path
            tier: User tier
            cost: Request cost

        Returns:
            Tuple of (allowed, dimension_failed, retry_after)
        """
        # 1. Check per-user limit (if authenticated)
        if user_id:
            allowed, retry = await self._check_user_limit(user_id, tier, cost)
            if not allowed:
                return False, "user", retry

        # 2. Check per-IP limit (always)
        allowed, retry = await self._check_ip_limit(ip_address, cost)
        if not allowed:
            return False, "ip", retry

        # 3. Check per-endpoint limit
        allowed, retry = await self._check_endpoint_limit(method, path, cost)
        if not allowed:
            return False, "endpoint", retry

        # 4. Check global limit
        allowed, retry = await self._check_global_limit(cost)
        if not allowed:
            return False, "global", retry

        return True, None, 0.0

    async def _check_user_limit(
        self,
        user_id: str,
        tier: UserTier,
        cost: float
    ) -> tuple[bool, float]:
        """Check per-user rate limit."""
        config = RATE_LIMIT_CONFIGS[tier]

        bucket = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.user_key(user_id, "minute"),
            capacity=config.requests_per_minute,
            refill_rate=config.requests_per_minute / 60.0
        )

        if await bucket.consume(cost):
            return True, 0.0

        retry = await bucket.time_until_tokens(cost)
        return False, retry

    async def _check_ip_limit(
        self,
        ip_address: str,
        cost: float
    ) -> tuple[bool, float]:
        """Check per-IP rate limit (prevents DDoS from single IP)."""
        # More restrictive than user limits
        bucket = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.ip_key(ip_address, "minute"),
            capacity=100,  # Max 100 requests/min per IP
            refill_rate=100.0 / 60.0
        )

        if await bucket.consume(cost):
            return True, 0.0

        retry = await bucket.time_until_tokens(cost)
        return False, retry

    async def _check_endpoint_limit(
        self,
        method: str,
        path: str,
        cost: float
    ) -> tuple[bool, float]:
        """Check per-endpoint global limit (all users combined)."""
        # Protect expensive endpoints from global overload

        # Different limits for different endpoint types
        if "/ocr/" in path:
            # OCR endpoints: max 100 concurrent across all users
            limit = 100
        elif "/search" in path:
            # Search endpoints: max 200 concurrent
            limit = 200
        else:
            # Other endpoints: max 500 concurrent
            limit = 500

        bucket = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.endpoint_key(method, path, "minute"),
            capacity=limit,
            refill_rate=limit / 60.0
        )

        if await bucket.consume(cost):
            return True, 0.0

        retry = await bucket.time_until_tokens(cost)
        return False, retry

    async def _check_global_limit(
        self,
        cost: float
    ) -> tuple[bool, float]:
        """Check global API rate limit (circuit breaker)."""
        # Global limit to prevent total system overload
        # This is a last resort protection

        bucket = RedisTokenBucket(
            redis=self.redis,
            key=RateLimitKeyBuilder.global_key("minute"),
            capacity=5000,  # Max 5000 requests/min globally
            refill_rate=5000.0 / 60.0
        )

        if await bucket.consume(cost):
            return True, 0.0

        retry = await bucket.time_until_tokens(cost)
        return False, retry
```

### Concurrent Request Limiting

Limit active concurrent requests (in addition to rate limits):

```python
import asyncio
from contextlib import asynccontextmanager

class ConcurrentRequestLimiter:
    """Limit number of concurrent requests per user/tier.

    Uses Redis to track active requests across multiple instances.
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    @asynccontextmanager
    async def limit_concurrent(
        self,
        identifier: str,
        max_concurrent: int,
        timeout: float = 30.0
    ):
        """Context manager to limit concurrent requests.

        Args:
            identifier: User/IP identifier
            max_concurrent: Maximum concurrent requests
            timeout: Max time to wait for slot

        Raises:
            HTTPException: 429 if cannot acquire slot
        """
        key = f"concurrent:{identifier}"
        acquired = False

        try:
            # Try to increment counter
            start_time = time.time()

            while time.time() - start_time < timeout:
                current = await self.redis.get(key)
                current = int(current) if current else 0

                if current < max_concurrent:
                    # Try to acquire slot
                    await self.redis.incr(key)
                    await self.redis.expire(key, 300)  # 5 min TTL
                    acquired = True
                    break

                # Wait and retry
                await asyncio.sleep(0.1)

            if not acquired:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Zu viele gleichzeitige Anfragen. Bitte später erneut versuchen."
                )

            # Yield control to endpoint
            yield

        finally:
            # Release slot
            if acquired:
                await self.redis.decr(key)

# Usage in endpoint
@router.post("/api/v1/ocr/process")
async def process_ocr(
    file: UploadFile,
    limiter: ConcurrentRequestLimiter = Depends(),
    user: User = Depends(get_current_user)
):
    """OCR endpoint with concurrent request limiting."""
    tier_config = RATE_LIMIT_CONFIGS[user.tier]

    async with limiter.limit_concurrent(
        identifier=f"user:{user.id}",
        max_concurrent=tier_config.concurrent_requests
    ):
        # Process OCR (only if slot acquired)
        result = await ocr_service.process(file)
        return result
```

---

## Headers and Client Communication

### Standard Rate Limit Headers

Follow RFCdraft standards for rate limit headers:

```python
class RateLimitHeaders:
    """Standard rate limit HTTP headers."""

    # Request quota
    LIMIT = "X-RateLimit-Limit"  # Max requests in window
    REMAINING = "X-RateLimit-Remaining"  # Remaining requests
    RESET = "X-RateLimit-Reset"  # Unix timestamp when limit resets

    # Additional context
    TIER = "X-RateLimit-Tier"  # User tier (free, basic, professional, etc.)
    RETRY_AFTER = "Retry-After"  # Seconds to wait (standard header)

    # Multiple windows (optional)
    LIMIT_SECOND = "X-RateLimit-Limit-Second"
    REMAINING_SECOND = "X-RateLimit-Remaining-Second"
    LIMIT_MINUTE = "X-RateLimit-Limit-Minute"
    REMAINING_MINUTE = "X-RateLimit-Remaining-Minute"
    LIMIT_HOUR = "X-RateLimit-Limit-Hour"
    REMAINING_HOUR = "X-RateLimit-Remaining-Hour"
    LIMIT_DAY = "X-RateLimit-Limit-Day"
    REMAINING_DAY = "X-RateLimit-Remaining-Day"
```

### Example HTTP Response

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 187
X-RateLimit-Reset: 1700000000
X-RateLimit-Tier: professional
X-RateLimit-Limit-Second: 10
X-RateLimit-Remaining-Second: 8
X-RateLimit-Limit-Hour: 10000
X-RateLimit-Remaining-Hour: 9432

{
  "status": "erfolg",
  "nachricht": "Dokument erfolgreich verarbeitet"
}
```

### 429 Too Many Requests Response

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 42
X-RateLimit-Limit: 200
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1700000042
X-RateLimit-Tier: basic

{
  "fehler": "Anfragelimit überschritten",
  "nachricht": "Zu viele Anfragen. Bitte in 42 Sekunden erneut versuchen.",
  "retry_after_seconds": 42.3,
  "tier": "basic",
  "limit": {
    "requests_per_minute": 200,
    "requests_per_hour": 2000,
    "requests_per_day": 20000
  },
  "dokumentation": "https://docs.ablage-system.de/rate-limits",
  "upgrade_url": "https://ablage-system.de/upgrade"
}
```

### Client-Side Handling (Example)

```python
import httpx
import asyncio
from typing import Optional

class AblageSystemClient:
    """Client with automatic rate limit handling."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient()

    async def request_with_retry(
        self,
        method: str,
        path: str,
        max_retries: int = 3,
        **kwargs
    ) -> httpx.Response:
        """Make request with automatic retry on rate limit.

        Args:
            method: HTTP method
            path: Request path
            max_retries: Maximum retry attempts
            **kwargs: Additional request arguments

        Returns:
            HTTP response

        Raises:
            httpx.HTTPStatusError: If final retry fails
        """
        headers = kwargs.get("headers", {})
        headers["X-API-Key"] = self.api_key
        kwargs["headers"] = headers

        for attempt in range(max_retries):
            response = await self.client.request(
                method,
                f"{self.base_url}{path}",
                **kwargs
            )

            if response.status_code == 429:
                # Rate limited
                retry_after = float(response.headers.get("Retry-After", 60))

                print(f"Rate limited. Retrying after {retry_after}s (attempt {attempt + 1}/{max_retries})")

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_after)
                    continue
                else:
                    # Final retry failed
                    response.raise_for_status()

            # Success or non-rate-limit error
            return response

        return response  # Should never reach here

    async def get_rate_limit_status(self) -> dict:
        """Get current rate limit status.

        Returns:
            Dict with limit, remaining, reset timestamp
        """
        response = await self.request_with_retry("GET", "/api/v1/health")

        return {
            "limit": int(response.headers.get("X-RateLimit-Limit", 0)),
            "remaining": int(response.headers.get("X-RateLimit-Remaining", 0)),
            "reset": int(response.headers.get("X-RateLimit-Reset", 0)),
            "tier": response.headers.get("X-RateLimit-Tier", "unknown")
        }
```

---

## Bypass Mechanisms

### Trusted Services Whitelist

```python
from typing import Set
import structlog

logger = structlog.get_logger(__name__)

class RateLimitBypassManager:
    """Manage rate limit bypasses for trusted services."""

    def __init__(self):
        self._bypassed_users: Set[str] = set()
        self._bypassed_ips: Set[str] = set()
        self._bypassed_api_keys: Set[str] = set()

    def add_bypassed_user(self, user_id: str) -> None:
        """Add user ID to bypass list."""
        self._bypassed_users.add(user_id)
        logger.info("rate_limit_bypass_added", user_id=user_id)

    def add_bypassed_ip(self, ip: str) -> None:
        """Add IP address to bypass list."""
        self._bypassed_ips.add(ip)
        logger.info("rate_limit_bypass_added", ip=ip)

    def add_bypassed_api_key(self, api_key_hash: str) -> None:
        """Add API key hash to bypass list."""
        self._bypassed_api_keys.add(api_key_hash)
        logger.info("rate_limit_bypass_added", api_key=api_key_hash[:8] + "...")

    def should_bypass(
        self,
        user_id: Optional[str] = None,
        ip: Optional[str] = None,
        api_key_hash: Optional[str] = None
    ) -> bool:
        """Check if request should bypass rate limiting.

        Args:
            user_id: User ID
            ip: IP address
            api_key_hash: API key hash

        Returns:
            True if should bypass
        """
        if user_id and user_id in self._bypassed_users:
            return True

        if ip and ip in self._bypassed_ips:
            return True

        if api_key_hash and api_key_hash in self._bypassed_api_keys:
            return True

        return False

    def load_from_config(self, config: dict) -> None:
        """Load bypass list from configuration.

        Args:
            config: Configuration dict with bypass lists
        """
        for user_id in config.get("bypassed_users", []):
            self.add_bypassed_user(user_id)

        for ip in config.get("bypassed_ips", []):
            self.add_bypassed_ip(ip)

        for api_key in config.get("bypassed_api_keys", []):
            import hashlib
            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            self.add_bypassed_api_key(api_key_hash)
```

### Configuration File

```yaml
# config/rate_limit_bypass.yaml

bypassed_users:
  - "internal-service-user-123"
  - "monitoring-agent-456"

bypassed_ips:
  - "127.0.0.1"  # Localhost
  - "10.0.0.0/8"  # Internal network (requires CIDR parsing)
  - "192.168.1.100"  # Monitoring server

bypassed_api_keys:
  - "internal-api-key-for-celery-workers"
  - "monitoring-api-key"

# Temporary bypasses (expire after timestamp)
temporary_bypasses:
  - user_id: "user-789"
    expires_at: "2025-12-31T23:59:59Z"
    reason: "Special migration task"
```

### IP Range Support (CIDR)

```python
import ipaddress
from typing import List

class IPRangeBypass:
    """Support for IP range bypasses using CIDR notation."""

    def __init__(self, ranges: List[str]):
        """Initialize with list of CIDR ranges.

        Args:
            ranges: List of CIDR ranges (e.g., ["10.0.0.0/8", "192.168.1.0/24"])
        """
        self.ranges = [ipaddress.ip_network(r) for r in ranges]

    def is_bypassed(self, ip: str) -> bool:
        """Check if IP is in any bypassed range.

        Args:
            ip: IP address to check

        Returns:
            True if IP is in bypassed range
        """
        try:
            ip_addr = ipaddress.ip_address(ip)
            return any(ip_addr in network for network in self.ranges)
        except ValueError:
            return False

# Usage
bypass_ranges = IPRangeBypass([
    "10.0.0.0/8",  # Private network
    "127.0.0.0/8",  # Localhost
    "192.168.0.0/16"  # Private network
])

if bypass_ranges.is_bypassed(client_ip):
    # Bypass rate limiting
    pass
```

---

## Monitoring and Alerting

### Prometheus Metrics

```python
from prometheus_client import Counter, Histogram, Gauge, Info

# Rate limit checks
rate_limit_checks_total = Counter(
    'rate_limit_checks_total',
    'Total rate limit checks',
    ['tier', 'allowed', 'method', 'endpoint']
)

# Rate limit exceeded
rate_limit_exceeded_total = Counter(
    'rate_limit_exceeded_total',
    'Rate limits exceeded',
    ['tier', 'dimension', 'endpoint']  # dimension: user, ip, endpoint, global
)

# Rate limit check duration
rate_limit_check_duration_seconds = Histogram(
    'rate_limit_check_duration_seconds',
    'Rate limit check duration',
    ['tier'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# Current tokens remaining (sampled)
rate_limit_tokens_remaining = Gauge(
    'rate_limit_tokens_remaining',
    'Current tokens remaining',
    ['identifier', 'window']  # window: second, minute, hour, day
)

# Bypassed requests
rate_limit_bypassed_total = Counter(
    'rate_limit_bypassed_total',
    'Bypassed rate limit checks',
    ['reason']  # reason: internal_user, whitelisted_ip, health_check
)

# Redis errors during rate limiting
rate_limit_redis_errors_total = Counter(
    'rate_limit_redis_errors_total',
    'Redis errors during rate limiting',
    ['operation']  # operation: consume, peek, reset
)

# Tier distribution
rate_limit_active_users = Gauge(
    'rate_limit_active_users',
    'Active users by tier',
    ['tier']
)
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Rate Limiting Übersicht",
    "panels": [
      {
        "title": "Anfragen pro Sekunde nach Tier",
        "targets": [
          {
            "expr": "rate(rate_limit_checks_total[1m])",
            "legendFormat": "{{tier}}"
          }
        ]
      },
      {
        "title": "Rate Limit Überschreitungen",
        "targets": [
          {
            "expr": "rate(rate_limit_exceeded_total[5m])",
            "legendFormat": "{{tier}} - {{dimension}}"
          }
        ]
      },
      {
        "title": "Durchschnittliche Check-Dauer",
        "targets": [
          {
            "expr": "rate(rate_limit_check_duration_seconds_sum[1m]) / rate(rate_limit_check_duration_seconds_count[1m])",
            "legendFormat": "{{tier}}"
          }
        ]
      },
      {
        "title": "Verbleibende Tokens (Stichprobe)",
        "targets": [
          {
            "expr": "rate_limit_tokens_remaining{window=\"minute\"}",
            "legendFormat": "{{identifier}}"
          }
        ]
      },
      {
        "title": "Top 10 Rate-Limited Endpoints",
        "targets": [
          {
            "expr": "topk(10, sum by (endpoint) (rate(rate_limit_exceeded_total[5m])))",
            "legendFormat": "{{endpoint}}"
          }
        ]
      },
      {
        "title": "Umgangene Anfragen",
        "targets": [
          {
            "expr": "rate(rate_limit_bypassed_total[1m])",
            "legendFormat": "{{reason}}"
          }
        ]
      }
    ]
  }
}
```

### Alerting Rules

```yaml
# prometheus/alerts/rate_limiting.yml

groups:
  - name: rate_limiting
    interval: 30s
    rules:
      # High rate limit exceeded rate
      - alert: HighRateLimitExceededRate
        expr: |
          rate(rate_limit_exceeded_total[5m]) > 10
        for: 5m
        labels:
          severity: warning
          component: rate_limiting
        annotations:
          summary: "Hohe Rate-Limit-Überschreitungsrate"
          description: "{{ $value }} Überschreitungen pro Sekunde in den letzten 5 Minuten"

      # Specific user hammering API
      - alert: UserHammeringAPI
        expr: |
          sum by (identifier) (rate(rate_limit_exceeded_total{dimension="user"}[5m])) > 5
        for: 10m
        labels:
          severity: warning
          component: rate_limiting
        annotations:
          summary: "Benutzer überschreitet häufig Rate-Limits"
          description: "Benutzer {{ $labels.identifier }} überschreitet Rate-Limits mit {{ $value }} Versuchen/Sekunde"

      # IP-based attack
      - alert: PotentialDDoSAttack
        expr: |
          sum by (identifier) (rate(rate_limit_exceeded_total{dimension="ip"}[1m])) > 50
        for: 2m
        labels:
          severity: critical
          component: rate_limiting
        annotations:
          summary: "Möglicher DDoS-Angriff erkannt"
          description: "IP {{ $labels.identifier }} überschreitet Rate-Limits mit {{ $value }} Versuchen/Sekunde"

      # Redis errors during rate limiting
      - alert: RateLimitRedisErrors
        expr: |
          rate(rate_limit_redis_errors_total[5m]) > 1
        for: 5m
        labels:
          severity: critical
          component: rate_limiting
        annotations:
          summary: "Redis-Fehler bei Rate-Limiting"
          description: "{{ $value }} Redis-Fehler pro Sekunde bei Rate-Limiting-Operationen"

      # Slow rate limit checks
      - alert: SlowRateLimitChecks
        expr: |
          histogram_quantile(0.95, rate(rate_limit_check_duration_seconds_bucket[5m])) > 0.1
        for: 10m
        labels:
          severity: warning
          component: rate_limiting
        annotations:
          summary: "Langsame Rate-Limit-Checks"
          description: "95. Perzentil der Check-Dauer beträgt {{ $value }}s (Ziel: <0.01s)"

      # Global rate limit approaching
      - alert: GlobalRateLimitApproaching
        expr: |
          rate(rate_limit_checks_total{dimension="global"}[1m]) > 4000
        for: 5m
        labels:
          severity: warning
          component: rate_limiting
        annotations:
          summary: "Globales Rate-Limit wird angenähert"
          description: "{{ $value }} Anfragen/Minute (Limit: 5000)"
```

---

## Testing

### Unit Tests

```python
import pytest
import time
from app.services.rate_limit import TokenBucket, RedisTokenBucket

class TestTokenBucket:
    """Unit tests for token bucket algorithm."""

    def test_consume_success(self):
        """Should consume tokens when available."""
        bucket = TokenBucket(capacity=10, refill_rate=5.0)

        assert bucket.consume(1.0) is True
        assert bucket.peek() == 9.0

    def test_consume_failure(self):
        """Should fail when insufficient tokens."""
        bucket = TokenBucket(capacity=10, refill_rate=5.0, initial_tokens=0)

        assert bucket.consume(1.0) is False
        assert bucket.peek() == 0.0

    def test_refill(self):
        """Should refill tokens over time."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0, initial_tokens=0)

        time.sleep(0.5)  # 0.5s * 10 tokens/s = 5 tokens

        tokens = bucket.peek()
        assert 4.5 <= tokens <= 5.5  # Allow small timing variance

    def test_capacity_cap(self):
        """Should not exceed capacity."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0)

        time.sleep(2.0)  # Would add 20 tokens

        assert bucket.peek() == 10.0  # Capped at capacity

    def test_fractional_consumption(self):
        """Should handle fractional token consumption."""
        bucket = TokenBucket(capacity=10, refill_rate=5.0)

        assert bucket.consume(2.5) is True
        assert bucket.peek() == 7.5

    def test_time_until_tokens(self):
        """Should calculate time until tokens available."""
        bucket = TokenBucket(capacity=10, refill_rate=10.0, initial_tokens=0)

        time_needed = bucket.time_until_tokens(5.0)
        assert 0.45 <= time_needed <= 0.55  # 5 tokens / 10 tokens/s = 0.5s

@pytest.mark.asyncio
class TestRedisTokenBucket:
    """Integration tests for Redis token bucket."""

    async def test_consume_success_redis(self, redis_client):
        """Should consume tokens from Redis bucket."""
        bucket = RedisTokenBucket(
            redis=redis_client,
            key="test:bucket:1",
            capacity=10,
            refill_rate=5.0
        )

        assert await bucket.consume(1.0) is True

        remaining = await bucket.peek()
        assert 8.5 <= remaining <= 9.5  # Allow for refill during test

    async def test_distributed_consumption(self, redis_client):
        """Should work correctly across multiple instances."""
        # Simulate two backend instances
        bucket1 = RedisTokenBucket(
            redis=redis_client,
            key="test:bucket:distributed",
            capacity=10,
            refill_rate=5.0
        )
        bucket2 = RedisTokenBucket(
            redis=redis_client,
            key="test:bucket:distributed",  # Same key
            capacity=10,
            refill_rate=5.0
        )

        # Both consume tokens
        await bucket1.consume(3.0)
        await bucket2.consume(3.0)

        # Check total consumption
        remaining = await bucket1.peek()
        assert 3.5 <= remaining <= 4.5  # 10 - 3 - 3 = 4 (+ small refill)

    async def test_redis_failure_fail_open(self, mocker):
        """Should fail open when Redis is unavailable."""
        # Mock Redis to raise exception
        mock_redis = mocker.Mock()
        mock_redis.evalsha.side_effect = Exception("Redis connection failed")

        bucket = RedisTokenBucket(
            redis=mock_redis,
            key="test:bucket:failopen",
            capacity=10,
            refill_rate=5.0
        )

        # Should allow request despite Redis failure
        assert await bucket.consume(1.0) is True
```

### Integration Tests

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.integration
@pytest.mark.asyncio
class TestRateLimitMiddleware:
    """Integration tests for rate limit middleware."""

    async def test_rate_limit_headers_present(self):
        """Should include rate limit headers in response."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/api/v1/health")

            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert "X-RateLimit-Reset" in response.headers

    async def test_rate_limit_enforcement(self):
        """Should enforce rate limits."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Get rate limit from first response
            response = await client.get("/api/v1/health")
            limit = int(response.headers["X-RateLimit-Limit"])

            # Make requests until rate limited
            for i in range(limit + 10):
                response = await client.get("/api/v1/health")

                if response.status_code == 429:
                    # Rate limited - verify headers
                    assert "Retry-After" in response.headers
                    assert response.headers["X-RateLimit-Remaining"] == "0"

                    # Verify error message in German
                    data = response.json()
                    assert "Anfragelimit überschritten" in data["fehler"]
                    break
            else:
                pytest.fail("Rate limit not enforced")

    async def test_different_tiers_different_limits(self):
        """Should apply different limits for different tiers."""
        # Create users with different tiers
        free_user_token = await create_user_token(tier="free")
        pro_user_token = await create_user_token(tier="professional")

        async with AsyncClient(app=app, base_url="http://test") as client:
            # Free user
            response = await client.get(
                "/api/v1/health",
                headers={"Authorization": f"Bearer {free_user_token}"}
            )
            free_limit = int(response.headers["X-RateLimit-Limit"])

            # Professional user
            response = await client.get(
                "/api/v1/health",
                headers={"Authorization": f"Bearer {pro_user_token}"}
            )
            pro_limit = int(response.headers["X-RateLimit-Limit"])

            # Professional should have higher limit
            assert pro_limit > free_limit

    async def test_endpoint_cost_multiplier(self):
        """Should apply cost multipliers to expensive endpoints."""
        async with AsyncClient(app=app, base_url="http://test") as client:
            # Regular endpoint
            response1 = await client.get("/api/v1/documents/")
            remaining_after_normal = int(response1.headers["X-RateLimit-Remaining"])

            # Expensive OCR endpoint (10x cost)
            response2 = await client.post(
                "/api/v1/ocr/process",
                files={"file": ("test.pdf", b"fake pdf content")}
            )
            remaining_after_expensive = int(response2.headers["X-RateLimit-Remaining"])

            # Should have consumed ~10x more tokens
            tokens_consumed = remaining_after_normal - remaining_after_expensive
            assert tokens_consumed >= 9  # Allow small variance

    async def test_bypass_internal_user(self):
        """Should bypass rate limits for internal users."""
        internal_token = await create_user_token(tier="internal")

        async with AsyncClient(app=app, base_url="http://test") as client:
            # Make many requests (would normally be rate limited)
            for _ in range(1000):
                response = await client.get(
                    "/api/v1/health",
                    headers={"Authorization": f"Bearer {internal_token}"}
                )

                # Should never be rate limited
                assert response.status_code == 200
```

### Load Testing

```python
# tests/load/locustfile.py

from locust import HttpUser, task, between
import random

class AblageSystemUser(HttpUser):
    """Locust user for load testing rate limits."""

    wait_time = between(0.1, 0.5)  # Aggressive timing to trigger limits

    def on_start(self):
        """Setup: Get API key."""
        self.api_key = "test-api-key-123"

    @task(10)
    def get_documents(self):
        """Get documents list (10x weight)."""
        self.client.get(
            "/api/v1/documents/",
            headers={"X-API-Key": self.api_key}
        )

    @task(1)
    def process_ocr(self):
        """Process OCR (1x weight, expensive)."""
        self.client.post(
            "/api/v1/ocr/process",
            files={"file": ("test.pdf", b"fake content")},
            headers={"X-API-Key": self.api_key}
        )

    @task(5)
    def search(self):
        """Search documents (5x weight)."""
        self.client.post(
            "/api/v1/search",
            json={"query": "test"},
            headers={"X-API-Key": self.api_key}
        )

    def on_stop(self):
        """Cleanup."""
        pass

# Run with: locust -f tests/load/locustfile.py --host=http://localhost:8000
```

---

## Performance Considerations

### Redis Performance Optimization

```python
# Use Redis pipelining for bulk operations
async def check_multiple_buckets(
    redis: Redis,
    keys: List[str],
    capacity: int,
    refill_rate: float,
    cost: float = 1.0
) -> List[bool]:
    """Check multiple buckets in parallel using pipelining.

    Args:
        redis: Redis client
        keys: List of bucket keys
        capacity: Bucket capacity
        refill_rate: Refill rate
        cost: Token cost

    Returns:
        List of boolean results (allowed/denied)
    """
    pipe = redis.pipeline()

    for key in keys:
        bucket = RedisTokenBucket(redis, key, capacity, refill_rate)
        # Queue consume operation
        pipe.evalsha(
            await bucket._load_script(),
            1,
            key,
            capacity,
            refill_rate,
            cost,
            time.time()
        )

    results = await pipe.execute()

    return [bool(result[0]) for result in results]
```

### Caching Rate Limit Configs

```python
from functools import lru_cache
from typing import Optional

class RateLimitConfigCache:
    """Cache rate limit configurations to avoid repeated lookups."""

    @lru_cache(maxsize=1000)
    def get_user_tier(self, user_id: str) -> UserTier:
        """Get cached user tier.

        Args:
            user_id: User ID

        Returns:
            User tier
        """
        # This would normally query database
        # Cached to avoid repeated database hits
        return self._fetch_user_tier_from_db(user_id)

    @lru_cache(maxsize=100)
    def get_endpoint_config(self, method: str, path: str) -> dict:
        """Get cached endpoint-specific configuration.

        Args:
            method: HTTP method
            path: Request path

        Returns:
            Endpoint configuration dict
        """
        return self._fetch_endpoint_config(method, path)

    def invalidate_user(self, user_id: str) -> None:
        """Invalidate cache for user (e.g., after tier change)."""
        # Clear specific cache entry
        self.get_user_tier.cache_clear()  # Would need custom implementation
```

### Batch Header Updates

```python
async def add_rate_limit_headers_batch(
    responses: List[Response],
    identifiers: List[str],
    tier_configs: List[RateLimitConfig],
    redis: Redis
) -> None:
    """Add rate limit headers to multiple responses efficiently.

    Args:
        responses: List of HTTP responses
        identifiers: List of user/IP identifiers
        tier_configs: List of tier configurations
        redis: Redis client
    """
    # Fetch all remaining tokens in parallel
    keys = [
        RateLimitKeyBuilder.user_key(ident, "minute")
        for ident in identifiers
    ]

    pipe = redis.pipeline()
    for key in keys:
        pipe.hget(key, "tokens")

    tokens_list = await pipe.execute()

    # Update headers
    for response, tokens, config in zip(responses, tokens_list, tier_configs):
        tokens = float(tokens) if tokens else config.requests_per_minute

        response.headers["X-RateLimit-Limit"] = str(config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(int(tokens))
        response.headers["X-RateLimit-Reset"] = str(int(time.time() + 60))
```

### Performance Benchmarks

Expected performance targets:

| Operation | Target Latency (p95) | Target Throughput |
|-----------|---------------------|-------------------|
| Token bucket check (local) | < 1ms | 100k+ checks/sec |
| Token bucket check (Redis) | < 5ms | 20k+ checks/sec |
| Middleware overhead | < 10ms | N/A |
| Redis pipelined checks (10 buckets) | < 15ms | N/A |

---

## Best Practices

### 1. Choose Appropriate Algorithm

- **Token Bucket**: General purpose, allows bursts (recommended for most endpoints)
- **Sliding Window**: Strict limits, smooth rate (use for billing APIs, admin endpoints)
- **Fixed Window**: Simple but has edge case issues (avoid unless necessary)

### 2. Set Reasonable Limits

```python
# Bad: Too restrictive for normal use
BAD_CONFIG = RateLimitConfig(
    requests_per_second=1,  # Too low
    requests_per_minute=10,
    burst_size=1  # No burst allowance
)

# Good: Allows normal usage patterns
GOOD_CONFIG = RateLimitConfig(
    requests_per_second=10,
    requests_per_minute=500,
    burst_size=20  # Allows batch operations
)
```

### 3. Use Multi-Dimensional Limits

Don't rely on a single dimension:

```python
# Bad: Only per-user limit (no protection from DDoS)
await check_user_limit(user_id)

# Good: Multiple dimensions
await check_user_limit(user_id)  # Fair allocation
await check_ip_limit(ip)  # DDoS protection
await check_endpoint_limit(endpoint)  # Protect expensive operations
await check_global_limit()  # Circuit breaker
```

### 4. Fail Open, Not Closed

When Redis/backend fails, allow requests:

```python
try:
    allowed = await bucket.consume(tokens)
except Exception as e:
    logger.error("rate_limit_check_failed", error=str(e))
    # Fail open: allow request
    allowed = True
    # Alert monitoring
    alert_on_call("Rate limiting system degraded")
```

### 5. Provide Clear Error Messages

```python
# Bad: Cryptic error
{"error": "429"}

# Good: Helpful German message with context
{
    "fehler": "Anfragelimit überschritten",
    "nachricht": "Sie haben Ihr Limit von 200 Anfragen pro Minute überschritten. Bitte warten Sie 42 Sekunden.",
    "retry_after_seconds": 42,
    "aktuelles_tier": "basic",
    "upgrade_empfehlung": "Professional-Tier bietet 500 Anfragen/Minute",
    "upgrade_url": "https://ablage-system.de/upgrade",
    "dokumentation": "https://docs.ablage-system.de/rate-limits"
}
```

### 6. Monitor and Alert

Set up alerts for:
- High rate limit exceeded rate (potential attack)
- Specific users repeatedly hitting limits (abuse or integration issue)
- Redis errors during rate limiting (system degradation)
- Slow rate limit checks (performance issue)

### 7. Test Rate Limits

Include rate limiting in:
- Unit tests (algorithm correctness)
- Integration tests (middleware enforcement)
- Load tests (performance under high load)
- Chaos tests (behavior when Redis fails)

### 8. Document Limits

Provide clear documentation for users:

```markdown
# Rate Limits

## Tiers

| Tier | Requests/Second | Requests/Minute | Requests/Hour | Requests/Day | Burst |
|------|-----------------|-----------------|---------------|--------------|-------|
| Free | 2 | 60 | 500 | 5,000 | 10 |
| Basic | 5 | 200 | 2,000 | 20,000 | 20 |
| Professional | 10 | 500 | 10,000 | 100,000 | 50 |
| Enterprise | 50 | 2,000 | 50,000 | 500,000 | 100 |

## Endpoint Costs

Expensive operations consume multiple requests:

- `GET /documents/`: 1x (standard)
- `POST /documents/`: 2x
- `POST /ocr/process`: **10x** (GPU-intensive)
- `POST /ocr/batch`: **20x** (very expensive)
- `POST /search`: 5x

## Headers

Every response includes:
- `X-RateLimit-Limit`: Your current limit
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets

## Handling 429 Responses

When rate limited, wait for `Retry-After` seconds before retrying.
```

### 9. Version Your Rate Limit API

Allow gradual migration when changing rate limits:

```python
# Support multiple API versions with different rate limits
RATE_LIMITS_BY_VERSION = {
    "v1": {  # Legacy, more permissive
        UserTier.FREE: RateLimitConfig(requests_per_minute=100, ...),
    },
    "v2": {  # Current, stricter
        UserTier.FREE: RateLimitConfig(requests_per_minute=60, ...),
    }
}

# Apply based on API version
api_version = request.url.path.split("/")[2]  # /api/v1/... or /api/v2/...
config = RATE_LIMITS_BY_VERSION.get(api_version, RATE_LIMITS_BY_VERSION["v2"])
```

### 10. Consider Cost-Based Limiting

For GPU-intensive operations:

```python
# Track GPU cost, not just request count
class GPUCostTracker:
    """Track GPU resource consumption for rate limiting."""

    async def consume_gpu_cost(
        self,
        user_id: str,
        operation: str,
        cost_gpu_seconds: float
    ) -> bool:
        """Check if user has GPU budget remaining.

        Args:
            user_id: User ID
            operation: Operation type (e.g., "ocr_process")
            cost_gpu_seconds: Estimated GPU seconds for operation

        Returns:
            True if within budget
        """
        # Each tier gets GPU budget (e.g., 100 GPU-seconds/hour)
        budget_per_hour = {
            UserTier.FREE: 10,  # 10 GPU-seconds/hour
            UserTier.PROFESSIONAL: 300,  # 5 GPU-minutes/hour
            UserTier.ENTERPRISE: 3600  # 1 GPU-hour/hour
        }

        tier = await self.get_user_tier(user_id)
        bucket = RedisTokenBucket(
            redis=self.redis,
            key=f"gpu_budget:user:{user_id}:hour",
            capacity=budget_per_hour[tier],
            refill_rate=budget_per_hour[tier] / 3600.0
        )

        return await bucket.consume(cost_gpu_seconds)
```

---

## Migration and Rollout

### Phase 1: Observation (No Enforcement)

```python
class ObservationOnlyRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiting middleware that only observes, doesn't enforce.

    Use during initial rollout to tune limits without affecting users.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Check rate limits but always allow requests."""
        # Check limits
        allowed, retry_after = await self._check_rate_limit(...)

        # Log what would have happened
        if not allowed:
            logger.warning(
                "rate_limit_would_block",
                identifier=identifier,
                retry_after=retry_after,
                endpoint=f"{request.method} {request.url.path}"
            )

            # Increment "would be blocked" metric
            rate_limit_would_block_total.labels(
                tier=tier,
                endpoint=f"{request.method} {request.url.path}"
            ).inc()

        # Always allow
        return await call_next(request)
```

### Phase 2: Soft Enforcement (Warnings)

```python
class SoftEnforcementRateLimitMiddleware(RateLimitMiddleware):
    """Rate limiting with warnings but no blocking.

    Adds warning headers when limits exceeded but allows requests.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        allowed, retry_after = await self._check_rate_limit(...)

        response = await call_next(request)

        if not allowed:
            # Add warning headers
            response.headers["X-RateLimit-Warning"] = "LIMIT_EXCEEDED"
            response.headers["X-RateLimit-Warning-Message"] = (
                f"Sie überschreiten Ihr Rate-Limit. "
                f"In Zukunft werden diese Anfragen blockiert."
            )

            logger.warning("rate_limit_soft_violation", identifier=identifier)

        return response
```

### Phase 3: Full Enforcement

Switch to full enforcement after observing for sufficient time:

```python
# config/settings.py

class Settings(BaseSettings):
    # Rate limiting mode
    RATE_LIMIT_MODE: str = "enforce"  # observe, soft, enforce

    # Gradual rollout percentage
    RATE_LIMIT_ENFORCEMENT_PERCENTAGE: int = 100  # 0-100

# Middleware
if settings.RATE_LIMIT_MODE == "observe":
    app.add_middleware(ObservationOnlyRateLimitMiddleware, ...)
elif settings.RATE_LIMIT_MODE == "soft":
    app.add_middleware(SoftEnforcementRateLimitMiddleware, ...)
else:  # enforce
    app.add_middleware(RateLimitMiddleware, ...)
```

### Gradual Rollout

```python
import random

class GradualRolloutRateLimitMiddleware(RateLimitMiddleware):
    """Enforce rate limiting for percentage of users.

    Allows gradual rollout to detect issues before full deployment.
    """

    def __init__(self, *args, enforcement_percentage: int = 100, **kwargs):
        super().__init__(*args, **kwargs)
        self.enforcement_percentage = enforcement_percentage

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Deterministic selection based on user ID hash
        identifier, tier = await self._get_identifier_and_tier(request)

        import hashlib
        hash_val = int(hashlib.md5(identifier.encode()).hexdigest(), 16)
        user_percentage = hash_val % 100

        if user_percentage < self.enforcement_percentage:
            # Enforce for this user
            return await super().dispatch(request, call_next)
        else:
            # Skip enforcement (observation only)
            logger.debug("rate_limit_not_enforced_gradual", identifier=identifier)
            return await call_next(request)

# Start at 10%, gradually increase
app.add_middleware(
    GradualRolloutRateLimitMiddleware,
    redis_client=redis,
    config=RATE_LIMIT_CONFIGS,
    enforcement_percentage=10  # Increase to 25, 50, 75, 100 over time
)
```

---

## Troubleshooting

### Issue: Rate Limits Too Strict

**Symptoms:**
- Many legitimate users hitting limits
- High rate of 429 responses for normal usage
- User complaints about being blocked

**Solutions:**
1. Analyze actual usage patterns:
```python
# Query Prometheus for actual request rates
avg_requests_per_minute = rate(http_requests_total[5m]) * 60
p95_requests_per_minute = histogram_quantile(0.95, ...)
```

2. Adjust limits based on data:
```python
# If p95 is 150 req/min but limit is 100, increase limit
NEW_LIMIT = int(p95_requests_per_minute * 1.5)  # 50% buffer
```

3. Implement burst allowance:
```python
# Allow short bursts by increasing bucket capacity
config.burst_size = config.requests_per_minute * 0.5  # 50% burst
```

### Issue: Redis Connection Errors

**Symptoms:**
- Rate limiting inconsistent
- Metrics show `rate_limit_redis_errors_total` increasing
- Logs show "Redis connection failed"

**Solutions:**
1. Check Redis health:
```bash
redis-cli -h localhost -p 6379 ping
# Should return PONG
```

2. Verify connection pool settings:
```python
# Increase pool size if exhausted
pool = ConnectionPool.from_url(
    redis_url,
    max_connections=100,  # Increase from 50
    socket_connect_timeout=5,  # Increase timeout
)
```

3. Implement retry logic:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def consume_with_retry(bucket: RedisTokenBucket, tokens: float) -> bool:
    """Consume tokens with automatic retry."""
    return await bucket.consume(tokens)
```

### Issue: Slow Rate Limit Checks

**Symptoms:**
- High latency on all requests
- Metric `rate_limit_check_duration_seconds` > 100ms
- Overall API performance degraded

**Solutions:**
1. Use Redis pipelining for multiple checks:
```python
# Instead of sequential checks
await check_user_limit()  # 5ms
await check_ip_limit()    # 5ms
await check_endpoint_limit()  # 5ms
# Total: 15ms

# Use pipelined checks
await check_all_limits_pipelined()  # 5ms total
```

2. Cache tier lookups:
```python
@lru_cache(maxsize=10000)
def get_user_tier_cached(user_id: str) -> UserTier:
    """Cache tier lookups to avoid DB hits."""
    return get_user_tier_from_db(user_id)
```

3. Use local memory for high-frequency checks:
```python
# For very high request rates, use local token bucket with Redis sync
class HybridTokenBucket:
    """Local token bucket with periodic Redis sync."""

    def __init__(self, ...):
        self.local_bucket = TokenBucket(...)
        self.redis_bucket = RedisTokenBucket(...)
        self.last_sync = time.time()

    async def consume(self, tokens: float) -> bool:
        # Check local first (fast)
        if self.local_bucket.consume(tokens):
            # Sync to Redis periodically
            if time.time() - self.last_sync > 10:
                await self._sync_to_redis()
            return True

        return False
```

### Issue: Bypassed Users Not Working

**Symptoms:**
- Internal users getting rate limited
- Whitelisted IPs being blocked

**Solutions:**
1. Verify bypass logic execution:
```python
logger.info(
    "bypass_check",
    user_id=user_id,
    ip=ip,
    should_bypass=should_bypass,
    bypass_reason=reason
)
```

2. Check bypass configuration:
```python
# Load bypass config on startup and verify
bypass_manager.load_from_config(config)

logger.info(
    "bypass_config_loaded",
    bypassed_users=len(bypass_manager._bypassed_users),
    bypassed_ips=len(bypass_manager._bypassed_ips)
)
```

3. Ensure bypass check happens before rate limit check:
```python
# CORRECT order
if await should_bypass(request):
    return await call_next(request)  # Skip rate limiting

allowed = await check_rate_limit(...)

# WRONG order (bypass never reached)
allowed = await check_rate_limit(...)  # Checked first!

if await should_bypass(request):  # Too late
    return await call_next(request)
```

### Issue: Metrics Not Recording

**Symptoms:**
- Grafana dashboards empty
- Prometheus metrics not appearing

**Solutions:**
1. Verify Prometheus scraping:
```bash
curl http://localhost:8000/metrics | grep rate_limit
# Should show rate_limit_* metrics
```

2. Check metric registration:
```python
# Ensure metrics registered before use
from prometheus_client import REGISTRY

# Verify metric exists
for collector in REGISTRY._collector_to_names:
    print(collector._name)  # Should include rate_limit metrics
```

3. Check label cardinality:
```python
# BAD: Too many unique labels (identifier = user ID)
rate_limit_checks.labels(identifier=user_id, ...)  # Millions of time series!

# GOOD: Limited labels
rate_limit_checks.labels(tier=user_tier, method=method)  # ~20 time series
```

---

## Appendix

### Complete Example: Production-Ready Implementation

```python
# app/middleware/rate_limit_production.py

"""
Production-ready rate limiting middleware for Ablage-System.

Features:
- Multi-dimensional rate limiting (user, IP, endpoint, global)
- Token bucket algorithm with Redis backend
- Cost multipliers for expensive operations
- Bypass mechanisms for internal services
- Comprehensive monitoring and alerting
- Graceful degradation on Redis failure
"""

import time
import asyncio
from typing import Optional, Callable, Dict, Tuple
from enum import Enum
from dataclasses import dataclass

import structlog
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from redis.asyncio import Redis
from prometheus_client import Counter, Histogram, Gauge

logger = structlog.get_logger(__name__)

# ... (Include all classes from above: TokenBucket, RedisTokenBucket,
#      RateLimitConfig, UserTier, etc.)

class ProductionRateLimitMiddleware(BaseHTTPMiddleware):
    """Production-ready rate limiting middleware."""

    def __init__(
        self,
        app,
        redis: Redis,
        config: Dict[UserTier, RateLimitConfig],
        bypass_manager: RateLimitBypassManager,
        mode: str = "enforce"  # observe, soft, enforce
    ):
        super().__init__(app)
        self.redis = redis
        self.config = config
        self.bypass_manager = bypass_manager
        self.mode = mode

        logger.info(
            "rate_limit_middleware_initialized",
            mode=mode,
            tiers=list(config.keys())
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Apply rate limiting to request."""
        start_time = time.time()

        # Extract identifier and tier
        identifier, tier = await self._get_identifier_and_tier(request)

        # Check bypass
        if self.bypass_manager.should_bypass(identifier):
            logger.debug("rate_limit_bypassed", identifier=identifier)
            return await call_next(request)

        # Get endpoint cost
        cost = EndpointLimitMultiplier.get_multiplier(
            request.method,
            str(request.url.path)
        )

        # Check all rate limit dimensions
        tier_config = self.config.get(tier, self.config[UserTier.FREE])
        allowed, dimension, retry_after = await self._check_all_dimensions(
            identifier=identifier,
            tier_config=tier_config,
            cost=cost,
            method=request.method,
            path=str(request.url.path)
        )

        # Record metrics
        duration = time.time() - start_time
        self._record_metrics(
            identifier=identifier,
            tier=tier,
            allowed=allowed,
            duration=duration,
            method=request.method,
            path=str(request.url.path)
        )

        # Handle rate limit exceeded
        if not allowed:
            if self.mode == "observe":
                # Just log, don't block
                logger.warning(
                    "rate_limit_would_block",
                    identifier=identifier,
                    dimension=dimension,
                    retry_after=retry_after
                )
            elif self.mode == "soft":
                # Add warning headers, don't block
                response = await call_next(request)
                response.headers["X-RateLimit-Warning"] = "LIMIT_EXCEEDED"
                return response
            else:  # enforce
                # Block request
                return self._create_rate_limit_response(
                    tier=tier,
                    tier_config=tier_config,
                    retry_after=retry_after
                )

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        await self._add_rate_limit_headers(
            response, identifier, tier_config
        )

        return response

    async def _check_all_dimensions(
        self,
        identifier: str,
        tier_config: RateLimitConfig,
        cost: float,
        method: str,
        path: str
    ) -> Tuple[bool, Optional[str], float]:
        """Check all rate limit dimensions.

        Returns:
            (allowed, failed_dimension, retry_after)
        """
        limiter = MultiDimensionalRateLimiter(self.redis)

        # Extract user ID from identifier if present
        user_id = identifier.split(":")[1] if identifier.startswith("user:") else None
        ip = identifier.split(":")[1] if identifier.startswith("ip:") else "unknown"

        return await limiter.check_all_limits(
            user_id=user_id,
            ip_address=ip,
            method=method,
            path=path,
            tier=tier_config,
            cost=cost
        )

    def _create_rate_limit_response(
        self,
        tier: UserTier,
        tier_config: RateLimitConfig,
        retry_after: float
    ) -> JSONResponse:
        """Create 429 response with helpful German message."""
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "fehler": "Anfragelimit überschritten",
                "nachricht": (
                    f"Sie haben Ihr Anfragelimit überschritten. "
                    f"Bitte warten Sie {int(retry_after)} Sekunden."
                ),
                "retry_after_seconds": retry_after,
                "aktuelles_tier": tier,
                "limits": {
                    "pro_sekunde": tier_config.requests_per_second,
                    "pro_minute": tier_config.requests_per_minute,
                    "pro_stunde": tier_config.requests_per_hour,
                    "pro_tag": tier_config.requests_per_day
                },
                "dokumentation": "https://docs.ablage-system.de/api/rate-limits"
            },
            headers={
                "Retry-After": str(int(retry_after)),
                "X-RateLimit-Limit": str(tier_config.requests_per_minute),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + retry_after))
            }
        )

    # ... (other methods)

# Initialize in app
async def create_app():
    app = FastAPI()

    redis = await RedisManager.get_client()
    bypass_manager = RateLimitBypassManager()
    bypass_manager.load_from_config(settings.RATE_LIMIT_BYPASS_CONFIG)

    app.add_middleware(
        ProductionRateLimitMiddleware,
        redis=redis,
        config=RATE_LIMIT_CONFIGS,
        bypass_manager=bypass_manager,
        mode=settings.RATE_LIMIT_MODE
    )

    return app
```

---

**End of API Rate Limiting Guide**

This guide provides comprehensive coverage of rate limiting implementation for the Ablage-System. For questions or issues, consult the troubleshooting section or refer to the Prometheus metrics and Grafana dashboards for observability.

**Related Documentation:**
- [Advanced Security Hardening Guide](advanced_security_hardening_guide.md)
- [Performance Benchmarking Suite Guide](performance_benchmarking_suite_guide.md)
- [Kubernetes Deployment Guide](kubernetes_deployment_guide.md)
