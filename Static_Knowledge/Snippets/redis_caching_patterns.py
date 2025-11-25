"""
Redis Caching Patterns for Ablage-System

Comprehensive caching strategies using Redis for:
- OCR result caching
- Document metadata caching
- Session management
- Rate limiting
- Distributed locking
"""

import asyncio
import json
import hashlib
from typing import Optional, Any, Callable
from datetime import timedelta
from functools import wraps
import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import LockError


# ============================================================================
# Connection Management
# ============================================================================

class RedisConnectionPool:
    """Singleton Redis connection pool."""

    _pool: Optional[redis.ConnectionPool] = None
    _client: Optional[Redis] = None

    @classmethod
    async def get_client(cls) -> Redis:
        """Get Redis client with connection pooling."""
        if cls._client is None:
            cls._pool = redis.ConnectionPool.from_url(
                "redis://localhost:6379/0",
                max_connections=50,
                decode_responses=True
            )
            cls._client = Redis(connection_pool=cls._pool)
        return cls._client

    @classmethod
    async def close(cls):
        """Close connection pool."""
        if cls._client:
            await cls._client.close()
            cls._client = None
            cls._pool = None


# ============================================================================
# Caching Decorator
# ============================================================================

def cached(
    ttl: int = 3600,
    key_prefix: str = "",
    serialize_fn: Callable = json.dumps,
    deserialize_fn: Callable = json.loads
):
    """
    Decorator for caching function results in Redis.

    Args:
        ttl: Time-to-live in seconds (default: 1 hour)
        key_prefix: Prefix for cache keys
        serialize_fn: Function to serialize value
        deserialize_fn: Function to deserialize value

    Usage:
        @cached(ttl=3600, key_prefix="ocr_result")
        async def process_document(document_id: str):
            # Expensive OCR processing
            return result
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = _generate_cache_key(
                key_prefix or func.__name__,
                args,
                kwargs
            )

            redis_client = await RedisConnectionPool.get_client()

            # Try to get from cache
            cached_value = await redis_client.get(cache_key)
            if cached_value is not None:
                return deserialize_fn(cached_value)

            # Cache miss - call function
            result = await func(*args, **kwargs)

            # Store in cache
            serialized = serialize_fn(result)
            await redis_client.setex(cache_key, ttl, serialized)

            return result

        return wrapper
    return decorator


def _generate_cache_key(prefix: str, args: tuple, kwargs: dict) -> str:
    """Generate deterministic cache key from function arguments."""
    # Create a string representation of args and kwargs
    key_parts = [prefix]

    # Add positional arguments
    for arg in args:
        if isinstance(arg, (str, int, float, bool)):
            key_parts.append(str(arg))
        else:
            # Hash complex objects
            key_parts.append(hashlib.md5(
                json.dumps(arg, sort_keys=True).encode()
            ).hexdigest()[:8])

    # Add keyword arguments (sorted for consistency)
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")

    return ":".join(key_parts)


# ============================================================================
# OCR Result Caching
# ============================================================================

class OCRResultCache:
    """Cache OCR processing results."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.key_prefix = "ocr:result"
        self.default_ttl = 3600  # 1 hour

    async def get(self, document_id: str, backend: str) -> Optional[dict]:
        """Get cached OCR result."""
        key = f"{self.key_prefix}:{document_id}:{backend}"
        cached = await self.redis.get(key)
        return json.loads(cached) if cached else None

    async def set(
        self,
        document_id: str,
        backend: str,
        result: dict,
        ttl: Optional[int] = None
    ):
        """Cache OCR result."""
        key = f"{self.key_prefix}:{document_id}:{backend}"
        ttl = ttl or self.default_ttl
        await self.redis.setex(key, ttl, json.dumps(result))

    async def invalidate(self, document_id: str, backend: Optional[str] = None):
        """
        Invalidate cached OCR results.

        Args:
            document_id: Document to invalidate
            backend: Specific backend (if None, invalidate all backends)
        """
        if backend:
            key = f"{self.key_prefix}:{document_id}:{backend}"
            await self.redis.delete(key)
        else:
            # Delete all backends for this document
            pattern = f"{self.key_prefix}:{document_id}:*"
            keys = []
            async for key in self.redis.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)


# ============================================================================
# Document Metadata Caching
# ============================================================================

class DocumentMetadataCache:
    """Cache frequently accessed document metadata."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.key_prefix = "doc:meta"
        self.default_ttl = 1800  # 30 minutes

    async def get(self, document_id: str) -> Optional[dict]:
        """Get cached document metadata."""
        key = f"{self.key_prefix}:{document_id}"
        data = await self.redis.hgetall(key)
        return data if data else None

    async def set(self, document_id: str, metadata: dict, ttl: Optional[int] = None):
        """Cache document metadata using Redis hash."""
        key = f"{self.key_prefix}:{document_id}"
        ttl = ttl or self.default_ttl

        # Store as hash for efficient partial updates
        await self.redis.hset(key, mapping=metadata)
        await self.redis.expire(key, ttl)

    async def update_field(self, document_id: str, field: str, value: str):
        """Update single field in cached metadata."""
        key = f"{self.key_prefix}:{document_id}"
        await self.redis.hset(key, field, value)

    async def delete(self, document_id: str):
        """Delete cached metadata."""
        key = f"{self.key_prefix}:{document_id}"
        await self.redis.delete(key)


# ============================================================================
# Rate Limiting
# ============================================================================

class RateLimiter:
    """Token bucket rate limiter using Redis."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> tuple[bool, int]:
        """
        Check if rate limit is exceeded.

        Args:
            key: Unique identifier (e.g., user_id, ip_address)
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            (allowed, remaining): Whether request is allowed and remaining quota
        """
        rate_key = f"rate_limit:{key}"

        # Use sliding window with sorted set
        now = asyncio.get_event_loop().time()
        window_start = now - window_seconds

        # Remove old entries
        await self.redis.zremrangebyscore(rate_key, 0, window_start)

        # Count requests in current window
        request_count = await self.redis.zcard(rate_key)

        if request_count < max_requests:
            # Add current request
            await self.redis.zadd(rate_key, {str(now): now})
            await self.redis.expire(rate_key, window_seconds)
            remaining = max_requests - request_count - 1
            return True, remaining
        else:
            remaining = 0
            return False, remaining


# Example usage
async def check_ocr_rate_limit(user_id: str) -> bool:
    """Check if user can process another OCR request (10/hour limit)."""
    redis_client = await RedisConnectionPool.get_client()
    limiter = RateLimiter(redis_client)

    allowed, remaining = await limiter.check_rate_limit(
        key=f"user:{user_id}:ocr",
        max_requests=10,
        window_seconds=3600  # 1 hour
    )

    if not allowed:
        raise Exception(f"Rate limit exceeded. Try again later.")

    return allowed


# ============================================================================
# Distributed Locking
# ============================================================================

class DistributedLock:
    """
    Distributed lock using Redis for preventing concurrent document processing.

    Prevents multiple workers from processing the same document simultaneously.
    """

    def __init__(self, redis_client: Redis, lock_name: str, timeout: int = 300):
        """
        Args:
            redis_client: Redis client
            lock_name: Unique lock identifier
            timeout: Lock timeout in seconds (default: 5 minutes)
        """
        self.redis = redis_client
        self.lock_name = f"lock:{lock_name}"
        self.timeout = timeout
        self.lock = None

    async def __aenter__(self):
        """Acquire lock."""
        self.lock = self.redis.lock(
            self.lock_name,
            timeout=self.timeout,
            blocking_timeout=10  # Wait up to 10s for lock
        )
        acquired = await self.lock.acquire()
        if not acquired:
            raise LockError(f"Could not acquire lock: {self.lock_name}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Release lock."""
        if self.lock:
            try:
                await self.lock.release()
            except LockError:
                # Lock already released or expired
                pass


# Example usage
async def process_document_with_lock(document_id: str):
    """Process document with distributed lock to prevent duplicate processing."""
    redis_client = await RedisConnectionPool.get_client()

    async with DistributedLock(redis_client, f"process:{document_id}"):
        # Only one worker can execute this block at a time
        result = await expensive_ocr_processing(document_id)
        return result


# ============================================================================
# Session Management
# ============================================================================

class SessionStore:
    """Redis-backed session storage."""

    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        self.key_prefix = "session"
        self.default_ttl = 86400  # 24 hours

    async def create_session(self, session_id: str, data: dict) -> None:
        """Create new session."""
        key = f"{self.key_prefix}:{session_id}"
        await self.redis.setex(key, self.default_ttl, json.dumps(data))

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session data."""
        key = f"{self.key_prefix}:{session_id}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None

    async def update_session(self, session_id: str, data: dict) -> None:
        """Update session data and refresh TTL."""
        key = f"{self.key_prefix}:{session_id}"
        await self.redis.setex(key, self.default_ttl, json.dumps(data))

    async def delete_session(self, session_id: str) -> None:
        """Delete session."""
        key = f"{self.key_prefix}:{session_id}"
        await self.redis.delete(key)

    async def extend_session(self, session_id: str, additional_seconds: int = None):
        """Extend session TTL."""
        key = f"{self.key_prefix}:{session_id}"
        ttl = additional_seconds or self.default_ttl
        await self.redis.expire(key, ttl)


# ============================================================================
# Cache Warming
# ============================================================================

async def warm_cache_on_startup():
    """Pre-populate cache with frequently accessed data on application startup."""
    redis_client = await RedisConnectionPool.get_client()

    # Example: Cache frequently used document templates
    from app.db.repositories import TemplateRepository

    templates = await TemplateRepository.get_all_active()

    for template in templates:
        cache_key = f"template:{template.id}"
        await redis_client.setex(
            cache_key,
            86400,  # 24 hours
            json.dumps(template.to_dict())
        )

    print(f"Cache warmed with {len(templates)} templates")


# ============================================================================
# Cache Invalidation
# ============================================================================

async def invalidate_document_cache(document_id: str):
    """
    Invalidate all caches related to a document.

    Call this when:
    - Document is updated
    - Document is deleted
    - OCR is re-run
    """
    redis_client = await RedisConnectionPool.get_client()

    # Patterns to invalidate
    patterns = [
        f"ocr:result:{document_id}:*",
        f"doc:meta:{document_id}",
        f"doc:extracted_text:{document_id}",
    ]

    keys_to_delete = []
    for pattern in patterns:
        async for key in redis_client.scan_iter(match=pattern):
            keys_to_delete.append(key)

    if keys_to_delete:
        await redis_client.delete(*keys_to_delete)
        print(f"Invalidated {len(keys_to_delete)} cache keys for document {document_id}")


# ============================================================================
# Practical Examples
# ============================================================================

# Example 1: Cached OCR processing
@cached(ttl=3600, key_prefix="ocr_result")
async def get_ocr_result(document_id: str, backend: str) -> dict:
    """Get OCR result with automatic caching."""
    # This will only execute if not in cache
    from app.services.ocr import OCRService
    return await OCRService.process(document_id, backend)


# Example 2: Rate-limited endpoint
async def upload_document_endpoint(user_id: str, file: bytes):
    """Rate-limited document upload."""
    # Check rate limit: 10 uploads per hour
    allowed = await check_ocr_rate_limit(user_id)
    if not allowed:
        raise HTTPException(429, "Rate limit exceeded")

    # Process upload
    return await process_upload(file)


# Example 3: Prevent duplicate processing
async def expensive_ocr_processing(document_id: str):
    """Placeholder for actual OCR processing."""
    # Simulate expensive operation
    await asyncio.sleep(2)
    return {"text": "extracted text", "confidence": 0.95}


# See also:
# - Static_Knowledge/Snippets/fastapi_patterns.md
# - Dynamic_Knowledge/Logs/performance_log.jsonl
# - Static_Knowledge/Skills/gpu_management_skill.yaml
