API RATE LIMITING & THROTTLING GUIDE - TEIL 1
Complete Rate Limiting Strategy for Production APIs

📋 TABLE OF CONTENTS

Introduction
Rate Limiting Strategies
Token Bucket Algorithm
Redis-based Implementation


🎯 INTRODUCTION
Why Rate Limiting Matters
┌─────────────────────────────────────────────────────────┐
│         RATE LIMITING BENEFITS                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🛡️ Protection                                          │
│     - Prevent abuse and DoS attacks                     │
│     - Protect backend resources                         │
│     - Ensure fair usage across users                    │
│     - Prevent cost overruns                             │
│                                                         │
│  ⚡ Performance                                          │
│     - Maintain consistent API performance               │
│     - Prevent resource exhaustion                       │
│     - Enable predictable scaling                        │
│     - Optimize infrastructure costs                     │
│                                                         │
│  💰 Monetization                                         │
│     - Enforce tier limits                               │
│     - Encourage plan upgrades                           │
│     - Control costs per user                            │
│     - Enable usage-based billing                        │
│                                                         │
│  📊 Quality of Service                                   │
│     - Guarantee service levels                          │
│     - Prevent noisy neighbors                           │
│     - Maintain SLA compliance                           │
│     - Enable priority queuing                           │
│                                                         │
└─────────────────────────────────────────────────────────┘
Rate Limiting Architecture
┌──────────────────────────────────────────────────────────────┐
│              RATE LIMITING ARCHITECTURE                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Client Request                                              │
│       ↓                                                      │
│  ┌─────────────────────────────────────────────┐           │
│  │         API Gateway / Load Balancer         │           │
│  └─────────────────────────────────────────────┘           │
│       ↓                                                      │
│  ┌─────────────────────────────────────────────┐           │
│  │       Rate Limiting Middleware              │           │
│  │  ┌────────────────────────────────────┐    │           │
│  │  │ 1. Extract identifier (API key,    │    │           │
│  │  │    user ID, IP)                    │    │           │
│  │  │ 2. Check Redis for current usage   │    │           │
│  │  │ 3. Apply algorithm (Token Bucket,  │    │           │
│  │  │    Leaky Bucket, etc.)             │    │           │
│  │  │ 4. Update counters                 │    │           │
│  │  │ 5. Add response headers            │    │           │
│  │  └────────────────────────────────────┘    │           │
│  └─────────────────────────────────────────────┘           │
│       ↓                        ↓                             │
│  Allowed                   Rate Limited                      │
│       ↓                        ↓                             │
│  Process Request           Return 429                        │
│       ↓                                                      │
│  ┌─────────────────────────────────────────────┐           │
│  │           Redis (State Storage)             │           │
│  │  - User counters                            │           │
│  │  - Token buckets                            │           │
│  │  - Sliding windows                          │           │
│  │  - Whitelist/Blacklist                      │           │
│  └─────────────────────────────────────────────┘           │
│                                                              │
└──────────────────────────────────────────────────────────────┘

📊 RATE LIMITING STRATEGIES
1. Fixed Window Counter
python# strategies/fixed_window.py

"""
Fixed Window Counter Strategy

Simple but has edge case issues
"""

from datetime import datetime
from typing import Optional
from redis import Redis


class FixedWindowRateLimiter:
    """
    Fixed Window Counter implementation.
    
    Divides time into fixed windows (e.g., 1 minute).
    Counts requests in current window.
    
    Pros:
    - Simple to implement
    - Memory efficient
    - Easy to understand
    
    Cons:
    - Traffic spikes at window boundaries
    - Can allow 2x limit at boundaries
    
    Example Issue:
        Limit: 100 req/min
        User sends 100 requests at 00:00:59
        User sends 100 requests at 00:01:00
        → 200 requests in 2 seconds!
    """
    
    def __init__(
        self,
        redis_client: Redis,
        max_requests: int = 100,
        window_seconds: int = 60
    ):
        """
        Initialize fixed window limiter.
        
        Args:
            redis_client: Redis connection
            max_requests: Max requests per window
            window_seconds: Window size in seconds
        """
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
    
    def is_allowed(self, identifier: str) -> tuple[bool, dict]:
        """
        Check if request is allowed.
        
        Args:
            identifier: Unique identifier (user ID, API key, IP)
        
        Returns:
            Tuple of (allowed, metadata)
        """
        # Get current window
        current_window = int(datetime.now().timestamp() / self.window_seconds)
        key = f"rate_limit:fixed:{identifier}:{current_window}"
        
        # Increment counter
        current_count = self.redis.incr(key)
        
        # Set expiry on first request in window
        if current_count == 1:
            self.redis.expire(key, self.window_seconds * 2)
        
        # Check limit
        allowed = current_count <= self.max_requests
        
        metadata = {
            "limit": self.max_requests,
            "remaining": max(0, self.max_requests - current_count),
            "reset": (current_window + 1) * self.window_seconds,
            "current": current_count
        }
        
        return allowed, metadata


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    limiter = FixedWindowRateLimiter(
        redis_client=redis,
        max_requests=100,
        window_seconds=60
    )
    
    # Test
    user_id = "user_123"
    allowed, meta = limiter.is_allowed(user_id)
    
    print(f"Allowed: {allowed}")
    print(f"Limit: {meta['limit']}")
    print(f"Remaining: {meta['remaining']}")
    print(f"Reset at: {datetime.fromtimestamp(meta['reset'])}")
2. Sliding Window Log
python# strategies/sliding_window_log.py

"""
Sliding Window Log Strategy

More accurate but memory intensive
"""

import time
from typing import Optional
from redis import Redis


class SlidingWindowLogRateLimiter:
    """
    Sliding Window Log implementation.
    
    Maintains a log of all request timestamps.
    Counts requests in sliding time window.
    
    Pros:
    - Very accurate
    - No boundary issues
    - Precise tracking
    
    Cons:
    - Memory intensive (stores all timestamps)
    - Slower for high request volumes
    - Redis memory grows with traffic
    
    Best for:
    - Low to medium traffic APIs
    - When accuracy is critical
    - Premium tier enforcement
    """
    
    def __init__(
        self,
        redis_client: Redis,
        max_requests: int = 100,
        window_seconds: int = 60
    ):
        """
        Initialize sliding window log limiter.
        
        Args:
            redis_client: Redis connection
            max_requests: Max requests per window
            window_seconds: Window size in seconds
        """
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
    
    def is_allowed(self, identifier: str) -> tuple[bool, dict]:
        """
        Check if request is allowed.
        
        Args:
            identifier: Unique identifier
        
        Returns:
            Tuple of (allowed, metadata)
        """
        key = f"rate_limit:sliding_log:{identifier}"
        now = time.time()
        window_start = now - self.window_seconds
        
        # Use Redis pipeline for atomic operations
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(key, 0, window_start)
        
        # Count requests in window
        pipe.zcard(key)
        
        # Add current request
        pipe.zadd(key, {str(now): now})
        
        # Set expiry
        pipe.expire(key, self.window_seconds + 10)
        
        results = pipe.execute()
        current_count = results[1]
        
        # Check if allowed (before adding current request)
        allowed = current_count < self.max_requests
        
        metadata = {
            "limit": self.max_requests,
            "remaining": max(0, self.max_requests - current_count - 1),
            "reset": int(now + self.window_seconds),
            "current": current_count + 1 if allowed else current_count
        }
        
        # If not allowed, remove the request we just added
        if not allowed:
            self.redis.zrem(key, str(now))
        
        return allowed, metadata


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    limiter = SlidingWindowLogRateLimiter(
        redis_client=redis,
        max_requests=100,
        window_seconds=60
    )
    
    # Simulate requests
    user_id = "user_123"
    
    for i in range(5):
        allowed, meta = limiter.is_allowed(user_id)
        print(f"Request {i+1}: Allowed={allowed}, Remaining={meta['remaining']}")
        time.sleep(0.1)
3. Sliding Window Counter
python# strategies/sliding_window_counter.py

"""
Sliding Window Counter Strategy

Best balance of accuracy and performance
"""

import time
from typing import Optional
from redis import Redis


class SlidingWindowCounterRateLimiter:
    """
    Sliding Window Counter implementation.
    
    Combines fixed window efficiency with sliding window accuracy.
    Uses weighted count from previous and current window.
    
    Algorithm:
        weight = (window_size - elapsed_in_current) / window_size
        count = current_window_count + (previous_window_count * weight)
    
    Pros:
    - Good accuracy (much better than fixed window)
    - Memory efficient (only 2 counters)
    - Good performance
    - Industry standard (used by Stripe, GitHub, etc.)
    
    Cons:
    - Slightly less accurate than sliding log
    - More complex than fixed window
    
    Best for:
    - Most production APIs
    - High traffic scenarios
    - Good accuracy requirements
    """
    
    def __init__(
        self,
        redis_client: Redis,
        max_requests: int = 100,
        window_seconds: int = 60
    ):
        """
        Initialize sliding window counter limiter.
        
        Args:
            redis_client: Redis connection
            max_requests: Max requests per window
            window_seconds: Window size in seconds
        """
        self.redis = redis_client
        self.max_requests = max_requests
        self.window_seconds = window_seconds
    
    def is_allowed(self, identifier: str) -> tuple[bool, dict]:
        """
        Check if request is allowed.
        
        Args:
            identifier: Unique identifier
        
        Returns:
            Tuple of (allowed, metadata)
        """
        now = time.time()
        current_window = int(now / self.window_seconds)
        previous_window = current_window - 1
        
        # Calculate position in current window (0.0 to 1.0)
        elapsed_in_current = now - (current_window * self.window_seconds)
        weight_previous = (self.window_seconds - elapsed_in_current) / self.window_seconds
        
        # Keys for current and previous windows
        current_key = f"rate_limit:sliding:{identifier}:{current_window}"
        previous_key = f"rate_limit:sliding:{identifier}:{previous_window}"
        
        # Get counts
        pipe = self.redis.pipeline()
        pipe.get(previous_key)
        pipe.get(current_key)
        results = pipe.execute()
        
        previous_count = int(results[0] or 0)
        current_count = int(results[1] or 0)
        
        # Calculate weighted count
        estimated_count = (previous_count * weight_previous) + current_count
        
        # Check if allowed
        allowed = estimated_count < self.max_requests
        
        if allowed:
            # Increment current window
            pipe = self.redis.pipeline()
            pipe.incr(current_key)
            pipe.expire(current_key, self.window_seconds * 2)
            pipe.execute()
            current_count += 1
            estimated_count += 1
        
        metadata = {
            "limit": self.max_requests,
            "remaining": max(0, int(self.max_requests - estimated_count)),
            "reset": int((current_window + 1) * self.window_seconds),
            "current": int(estimated_count)
        }
        
        return allowed, metadata


# ============================================
# PERFORMANCE COMPARISON
# ============================================

def compare_strategies():
    """Compare different rate limiting strategies"""
    from redis import Redis
    import time
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    strategies = {
        "Fixed Window": FixedWindowRateLimiter(redis, 100, 60),
        "Sliding Log": SlidingWindowLogRateLimiter(redis, 100, 60),
        "Sliding Counter": SlidingWindowCounterRateLimiter(redis, 100, 60)
    }
    
    results = {}
    
    for name, limiter in strategies.items():
        start = time.time()
        
        # Simulate 1000 requests
        allowed_count = 0
        for i in range(1000):
            allowed, _ = limiter.is_allowed(f"test_{name}")
            if allowed:
                allowed_count += 1
        
        elapsed = time.time() - start
        
        results[name] = {
            "time": elapsed,
            "allowed": allowed_count,
            "requests_per_sec": 1000 / elapsed
        }
    
    # Print comparison
    print("\n" + "="*60)
    print("RATE LIMITING STRATEGY COMPARISON")
    print("="*60)
    
    for name, data in results.items():
        print(f"\n{name}:")
        print(f"  Time: {data['time']:.4f}s")
        print(f"  Allowed: {data['allowed']}/1000")
        print(f"  Throughput: {data['requests_per_sec']:.0f} req/s")


if __name__ == "__main__":
    compare_strategies()

🪣 TOKEN BUCKET ALGORITHM
1. Token Bucket Implementation
python# algorithms/token_bucket.py

"""
Token Bucket Algorithm

Industry-standard, flexible rate limiting
"""

import time
from typing import Optional, Tuple
from dataclasses import dataclass
from redis import Redis
import json


@dataclass
class TokenBucketConfig:
    """Token bucket configuration"""
    capacity: int  # Maximum tokens in bucket
    refill_rate: float  # Tokens added per second
    initial_tokens: Optional[int] = None  # Initial tokens (defaults to capacity)
    
    def __post_init__(self):
        if self.initial_tokens is None:
            self.initial_tokens = self.capacity


class TokenBucketRateLimiter:
    """
    Token Bucket Algorithm implementation.
    
    How it works:
    1. Bucket holds tokens (max = capacity)
    2. Tokens refill at constant rate
    3. Each request consumes 1 token
    4. Request allowed if tokens available
    5. Tokens refill even when bucket is full (up to capacity)
    
    Characteristics:
    - Allows bursts up to capacity
    - Smooth refill over time
    - Handles variable request costs
    - Industry standard (AWS, Google Cloud use this)
    
    Example:
        capacity = 100 tokens
        refill_rate = 10 tokens/second
        
        t=0s:  100 tokens (send 100 requests) → 0 tokens
        t=1s:  10 tokens (refilled) → can send 10 requests
        t=10s: 100 tokens (bucket full) → can send 100 requests
    
    Pros:
    - Allows controlled bursts
    - Smooth rate limiting
    - Flexible (supports different request costs)
    - Precise refill
    
    Cons:
    - More complex than counters
    - Requires float arithmetic
    - Slightly more Redis operations
    
    Best for:
    - APIs with bursty traffic patterns
    - Different endpoint costs
    - Premium tier with burst allowances
    - When UX matters (allows occasional bursts)
    """
    
    def __init__(
        self,
        redis_client: Redis,
        config: TokenBucketConfig
    ):
        """
        Initialize token bucket limiter.
        
        Args:
            redis_client: Redis connection
            config: Token bucket configuration
        """
        self.redis = redis_client
        self.config = config
    
    def _get_bucket_state(self, identifier: str) -> dict:
        """
        Get current bucket state from Redis.
        
        Args:
            identifier: Unique identifier
        
        Returns:
            Bucket state dictionary
        """
        key = f"rate_limit:token_bucket:{identifier}"
        data = self.redis.get(key)
        
        if data:
            return json.loads(data)
        else:
            # Initialize new bucket
            return {
                "tokens": self.config.initial_tokens,
                "last_refill": time.time()
            }
    
    def _save_bucket_state(
        self,
        identifier: str,
        state: dict,
        ttl: int = 3600
    ):
        """
        Save bucket state to Redis.
        
        Args:
            identifier: Unique identifier
            state: Bucket state
            ttl: Time to live in seconds
        """
        key = f"rate_limit:token_bucket:{identifier}"
        self.redis.setex(
            key,
            ttl,
            json.dumps(state)
        )
    
    def _refill_tokens(self, state: dict) -> dict:
        """
        Calculate token refill.
        
        Args:
            state: Current bucket state
        
        Returns:
            Updated state with refilled tokens
        """
        now = time.time()
        elapsed = now - state["last_refill"]
        
        # Calculate tokens to add
        tokens_to_add = elapsed * self.config.refill_rate
        
        # Update tokens (capped at capacity)
        state["tokens"] = min(
            self.config.capacity,
            state["tokens"] + tokens_to_add
        )
        state["last_refill"] = now
        
        return state
    
    def consume(
        self,
        identifier: str,
        tokens: int = 1
    ) -> Tuple[bool, dict]:
        """
        Try to consume tokens.
        
        Args:
            identifier: Unique identifier
            tokens: Number of tokens to consume
        
        Returns:
            Tuple of (allowed, metadata)
        """
        # Get current state
        state = self._get_bucket_state(identifier)
        
        # Refill tokens based on elapsed time
        state = self._refill_tokens(state)
        
        # Check if enough tokens
        allowed = state["tokens"] >= tokens
        
        if allowed:
            # Consume tokens
            state["tokens"] -= tokens
        
        # Save updated state
        self._save_bucket_state(identifier, state)
        
        # Calculate time until next token
        time_per_token = 1.0 / self.config.refill_rate
        tokens_needed = tokens if not allowed else 0
        retry_after = int(time_per_token * (tokens_needed - state["tokens"]))
        
        metadata = {
            "limit": self.config.capacity,
            "remaining": int(state["tokens"]),
            "reset": int(time.time() + retry_after) if retry_after > 0 else None,
            "retry_after": retry_after if retry_after > 0 else None,
            "refill_rate": self.config.refill_rate
        }
        
        return allowed, metadata
    
    def peek(self, identifier: str) -> dict:
        """
        Check bucket state without consuming.
        
        Args:
            identifier: Unique identifier
        
        Returns:
            Current bucket metadata
        """
        state = self._get_bucket_state(identifier)
        state = self._refill_tokens(state)
        
        return {
            "limit": self.config.capacity,
            "remaining": int(state["tokens"]),
            "refill_rate": self.config.refill_rate
        }


# ============================================
# LUA SCRIPT VERSION (Atomic, Faster)
# ============================================

class TokenBucketLuaRateLimiter:
    """
    Token Bucket using Lua script for atomic operations.
    
    Much faster and more reliable than Python version.
    All operations are atomic in Redis.
    """
    
    # Lua script for token bucket
    TOKEN_BUCKET_SCRIPT = """
    local key = KEYS[1]
    local capacity = tonumber(ARGV[1])
    local refill_rate = tonumber(ARGV[2])
    local tokens_requested = tonumber(ARGV[3])
    local now = tonumber(ARGV[4])
    
    local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
    local tokens = tonumber(bucket[1])
    local last_refill = tonumber(bucket[2])
    
    -- Initialize if doesn't exist
    if not tokens then
        tokens = capacity
        last_refill = now
    end
    
    -- Refill tokens
    local elapsed = now - last_refill
    local tokens_to_add = elapsed * refill_rate
    tokens = math.min(capacity, tokens + tokens_to_add)
    
    -- Check if enough tokens
    local allowed = 0
    if tokens >= tokens_requested then
        tokens = tokens - tokens_requested
        allowed = 1
    end
    
    -- Save state
    redis.call('HSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    
    -- Return: allowed, tokens, capacity, refill_rate
    return {allowed, math.floor(tokens), capacity, refill_rate}
    """
    
    def __init__(
        self,
        redis_client: Redis,
        config: TokenBucketConfig
    ):
        """Initialize Lua-based token bucket limiter"""
        self.redis = redis_client
        self.config = config
        
        # Register Lua script
        self.script = self.redis.register_script(self.TOKEN_BUCKET_SCRIPT)
    
    def consume(
        self,
        identifier: str,
        tokens: int = 1
    ) -> Tuple[bool, dict]:
        """
        Try to consume tokens using Lua script.
        
        Args:
            identifier: Unique identifier
            tokens: Number of tokens to consume
        
        Returns:
            Tuple of (allowed, metadata)
        """
        key = f"rate_limit:token_bucket_lua:{identifier}"
        
        # Execute Lua script
        result = self.script(
            keys=[key],
            args=[
                self.config.capacity,
                self.config.refill_rate,
                tokens,
                time.time()
            ]
        )
        
        allowed = bool(result[0])
        remaining = int(result[1])
        capacity = int(result[2])
        refill_rate = float(result[3])
        
        metadata = {
            "limit": capacity,
            "remaining": remaining,
            "refill_rate": refill_rate
        }
        
        return allowed, metadata


# ============================================
# EXAMPLE USAGE & COMPARISON
# ============================================

if __name__ == "__main__":
    from redis import Redis
    import time
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    # Configuration
    config = TokenBucketConfig(
        capacity=100,      # 100 tokens max
        refill_rate=10.0   # 10 tokens per second
    )
    
    # ============================================
    # Test Python version
    # ============================================
    
    print("="*60)
    print("TOKEN BUCKET - PYTHON VERSION")
    print("="*60)
    
    limiter_py = TokenBucketRateLimiter(redis, config)
    
    # Burst test
    print("\nBurst test (100 requests immediately):")
    user_id = "user_python"
    
    for i in range(5):
        allowed, meta = limiter_py.consume(user_id)
        print(f"  Request {i+1}: Allowed={allowed}, Remaining={meta['remaining']}")
    
    # Wait and test refill
    print("\nWaiting 2 seconds for refill...")
    time.sleep(2)
    
    allowed, meta = limiter_py.consume(user_id)
    print(f"  After 2s: Allowed={allowed}, Remaining={meta['remaining']}")
    print(f"  Expected ~20 tokens refilled (10 tokens/sec * 2 sec)")
    
    # ============================================
    # Test Lua version
    # ============================================
    
    print("\n" + "="*60)
    print("TOKEN BUCKET - LUA VERSION")
    print("="*60)
    
    limiter_lua = TokenBucketLuaRateLimiter(redis, config)
    
    # Burst test
    print("\nBurst test (100 requests immediately):")
    user_id = "user_lua"
    
    for i in range(5):
        allowed, meta = limiter_lua.consume(user_id)
        print(f"  Request {i+1}: Allowed={allowed}, Remaining={meta['remaining']}")
    
    # Performance comparison
    print("\n" + "="*60)
    print("PERFORMANCE COMPARISON")
    print("="*60)
    
    iterations = 1000
    
    # Python version
    start = time.time()
    for i in range(iterations):
        limiter_py.consume(f"perf_test_py_{i % 10}")
    py_time = time.time() - start
    
    # Lua version
    start = time.time()
    for i in range(iterations):
        limiter_lua.consume(f"perf_test_lua_{i % 10}")
    lua_time = time.time() - start
    
    print(f"\nPython version: {py_time:.4f}s ({iterations/py_time:.0f} req/s)")
    print(f"Lua version: {lua_time:.4f}s ({iterations/lua_time:.0f} req/s)")
    print(f"Speedup: {py_time/lua_time:.2f}x")
2. Variable Cost Token Bucket
python# algorithms/variable_cost_token_bucket.py

"""
Variable Cost Token Bucket

Different endpoints consume different amounts of tokens
"""

from typing import Dict, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

from algorithms.token_bucket import (
    TokenBucketConfig,
    TokenBucketLuaRateLimiter
)


class EndpointCost(Enum):
    """Endpoint cost tiers"""
    LIGHT = 1      # Simple reads
    MEDIUM = 5     # Complex queries
    HEAVY = 10     # OCR processing
    PREMIUM = 50   # Batch operations


@dataclass
class EndpointConfig:
    """Endpoint configuration"""
    path: str
    cost: int
    description: str


class VariableCostRateLimiter:
    """
    Rate limiter with variable endpoint costs.
    
    Different endpoints consume different amounts of tokens.
    Useful for APIs with varying complexity.
    
    Example:
        GET /users -> 1 token
        POST /ocr/process -> 10 tokens
        POST /ocr/batch -> 50 tokens
    """
    
    # Define endpoint costs
    ENDPOINTS: Dict[str, EndpointConfig] = {
        # Authentication
        "POST:/auth/login": EndpointConfig(
            "POST:/auth/login",
            EndpointCost.LIGHT.value,
            "User login"
        ),
        
        # User operations
        "GET:/users": EndpointConfig(
            "GET:/users",
            EndpointCost.LIGHT.value,
            "List users"
        ),
        "GET:/users/{id}": EndpointConfig(
            "GET:/users/{id}",
            EndpointCost.LIGHT.value,
            "Get user"
        ),
        
        # Document operations
        "POST:/documents/upload": EndpointConfig(
            "POST:/documents/upload",
            EndpointCost.MEDIUM.value,
            "Upload document"
        ),
        "GET:/documents": EndpointConfig(
            "GET:/documents",
            EndpointCost.LIGHT.value,
            "List documents"
        ),
        
        # OCR operations (expensive!)
        "POST:/ocr/process": EndpointConfig(
            "POST:/ocr/process",
            EndpointCost.HEAVY.value,
            "Process single document with OCR"
        ),
        "POST:/ocr/batch": EndpointConfig(
            "POST:/ocr/batch",
            EndpointCost.PREMIUM.value,
            "Batch OCR processing"
        ),
        
        # Default for unlisted endpoints
        "DEFAULT": EndpointConfig(
            "DEFAULT",
            EndpointCost.LIGHT.value,
            "Default cost"
        )
    }
    
    def __init__(
        self,
        token_bucket: TokenBucketLuaRateLimiter
    ):
        """
        Initialize variable cost rate limiter.
        
        Args:
            token_bucket: Underlying token bucket limiter
        """
        self.token_bucket = token_bucket
    
    def get_endpoint_cost(
        self,
        method: str,
        path: str
    ) -> int:
        """
        Get cost for endpoint.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
        
        Returns:
            Token cost for this endpoint
        """
        # Normalize path (remove IDs, etc.)
        normalized_path = self._normalize_path(path)
        endpoint_key = f"{method}:{normalized_path}"
        
        # Look up cost
        endpoint = self.ENDPOINTS.get(
            endpoint_key,
            self.ENDPOINTS["DEFAULT"]
        )
        
        return endpoint.cost
    
    def _normalize_path(self, path: str) -> str:
        """
        Normalize path by replacing IDs with placeholders.
        
        Args:
            path: Request path
        
        Returns:
            Normalized path
        
        Example:
            /users/123 -> /users/{id}
            /documents/abc-def/result -> /documents/{id}/result
        """
        parts = path.split('/')
        normalized = []
        
        for part in parts:
            # Check if part looks like an ID
            if self._looks_like_id(part):
                normalized.append('{id}')
            else:
                normalized.append(part)
        
        return '/'.join(normalized)
    
    def _looks_like_id(self, part: str) -> bool:
        """Check if path part looks like an ID"""
        if not part:
            return False
        
        # UUID pattern
        if len(part) > 20 and '-' in part:
            return True
        
        # Numeric ID
        if part.isdigit():
            return True
        
        # Short alphanumeric
        if len(part) > 10 and part.replace('-', '').replace('_', '').isalnum():
            return True
        
        return False
    
    def check_request(
        self,
        identifier: str,
        method: str,
        path: str
    ) -> Tuple[bool, dict]:
        """
        Check if request is allowed.
        
        Args:
            identifier: User identifier
            method: HTTP method
            path: Request path
        
        Returns:
            Tuple of (allowed, metadata)
        """
        # Get endpoint cost
        cost = self.get_endpoint_cost(method, path)
        
        # Check token bucket
        allowed, metadata = self.token_bucket.consume(identifier, cost)
        
        # Add endpoint info to metadata
        metadata["endpoint_cost"] = cost
        metadata["endpoint"] = f"{method}:{path}"
        
        return allowed, metadata


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    # Create token bucket (1000 tokens, 100/second refill)
    config = TokenBucketConfig(capacity=1000, refill_rate=100.0)
    token_bucket = TokenBucketLuaRateLimiter(redis, config)
    
    # Create variable cost limiter
    limiter = VariableCostRateLimiter(token_bucket)
    
    # Test different endpoints
    user_id = "user_123"
    
    endpoints = [
        ("GET", "/users"),
        ("POST", "/documents/upload"),
        ("POST", "/ocr/process"),
        ("POST", "/ocr/batch"),
    ]
    
    print("="*60)
    print("VARIABLE COST RATE LIMITING")
    print("="*60)
    print(f"\nUser: {user_id}")
    print(f"Initial tokens: {config.capacity}\n")
    
    for method, path in endpoints:
        allowed, meta = limiter.check_request(user_id, method, path)
        
        print(f"{method:6} {path:25} Cost: {meta['endpoint_cost']:3} tokens")
        print(f"  → Allowed: {allowed}, Remaining: {meta['remaining']}")
        print()

🔴 REDIS-BASED IMPLEMENTATION
1. Production-Ready Rate Limiter
python# core/rate_limiting/redis_limiter.py

"""
Production-Ready Redis Rate Limiter

Complete implementation with all features
"""

from typing import Optional, Dict, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import time
from redis import Redis
from loguru import logger

from algorithms.token_bucket import (
    TokenBucketConfig,
    TokenBucketLuaRateLimiter
)


class RateLimitTier(Enum):
    """Rate limit tiers"""
    FREE = "free"
    BASIC = "basic"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class TierConfig:
    """Configuration for a rate limit tier"""
    name: str
    capacity: int          # Max tokens
    refill_rate: float     # Tokens per second
    description: str
    cost_multiplier: float = 1.0  # Cost adjustment


class RateLimiter:
    """
    Production-ready rate limiter.
    
    Features:
    - Multiple tiers (Free, Basic, Pro, Enterprise)
    - Token bucket algorithm
    - Variable endpoint costs
    - Redis-based storage
    - Monitoring hooks
    - Whitelist support
    - Custom headers
    """
    
    # Tier configurations
    TIERS: Dict[RateLimitTier, TierConfig] = {
        RateLimitTier.FREE: TierConfig(
            name="Free",
            capacity=100,
            refill_rate=1.0,  # 1 token/second = 60/min
            description="Free tier: 100 burst, 60/min sustained"
        ),
        RateLimitTier.BASIC: TierConfig(
            name="Basic",
            capacity=500,
            refill_rate=10.0,  # 600/min
            description="Basic tier: 500 burst, 600/min sustained"
        ),
        RateLimitTier.PRO: TierConfig(
            name="Pro",
            capacity=2000,
            refill_rate=50.0,  # 3000/min
            description="Pro tier: 2000 burst, 3000/min sustained"
        ),
        RateLimitTier.ENTERPRISE: TierConfig(
            name="Enterprise",
            capacity=10000,
            refill_rate=200.0,  # 12000/min
            description="Enterprise tier: 10000 burst, 12000/min sustained"
        ),
    }
    
    def __init__(
        self,
        redis_client: Redis,
        default_tier: RateLimitTier = RateLimitTier.FREE,
        enable_monitoring: bool = True
    ):
        """
        Initialize rate limiter.
        
        Args:
            redis_client: Redis connection
            default_tier: Default tier for users
            enable_monitoring: Enable monitoring hooks
        """
        self.redis = redis_client
        self.default_tier = default_tier
        self.enable_monitoring = enable_monitoring
        
        # Create token bucket limiters for each tier
        self.limiters: Dict[RateLimitTier, TokenBucketLuaRateLimiter] = {}
        
        for tier, config in self.TIERS.items():
            bucket_config = TokenBucketConfig(
                capacity=config.capacity,
                refill_rate=config.refill_rate
            )
            self.limiters[tier] = TokenBucketLuaRateLimiter(
                redis_client,
                bucket_config
            )
        
        logger.info("Rate limiter initialized with {} tiers", len(self.TIERS))
    
    def get_user_tier(self, identifier: str) -> RateLimitTier:
        """
        Get tier for user.
        
        Args:
            identifier: User identifier
        
        Returns:
            User's rate limit tier
        """
        # Check Redis for user tier
        key = f"rate_limit:tier:{identifier}"
        tier_name = self.redis.get(key)
        
        if tier_name:
            try:
                return RateLimitTier(tier_name.decode() if isinstance(tier_name, bytes) else tier_name)
            except ValueError:
                logger.warning(f"Invalid tier for {identifier}: {tier_name}")
        
        return self.default_tier
    
    def set_user_tier(
        self,
        identifier: str,
        tier: RateLimitTier,
        ttl: Optional[int] = None
    ):
        """
        Set tier for user.
        
        Args:
            identifier: User identifier
            tier: Rate limit tier
            ttl: Optional expiration in seconds
        """
        key = f"rate_limit:tier:{identifier}"
        
        if ttl:
            self.redis.setex(key, ttl, tier.value)
        else:
            self.redis.set(key, tier.value)
        
        logger.info(f"Set tier for {identifier}: {tier.value}")
    
    def is_whitelisted(self, identifier: str) -> bool:
        """
        Check if identifier is whitelisted.
        
        Args:
            identifier: User identifier
        
        Returns:
            True if whitelisted
        """
        key = f"rate_limit:whitelist:{identifier}"
        return bool(self.redis.exists(key))
    
    def check_rate_limit(
        self,
        identifier: str,
        cost: int = 1
    ) -> Tuple[bool, Dict]:
        """
        Check if request is allowed.
        
        Args:
            identifier: User identifier
            cost: Token cost of request
        
        Returns:
            Tuple of (allowed, metadata)
        """
        # Check whitelist
        if self.is_whitelisted(identifier):
            return True, {
                "whitelisted": True,
                "limit": float('inf'),
                "remaining": float('inf')
            }
        
        # Get user tier
        tier = self.get_user_tier(identifier)
        tier_config = self.TIERS[tier]
        
        # Get limiter for tier
        limiter = self.limiters[tier]
        
        # Apply cost multiplier
        adjusted_cost = int(cost * tier_config.cost_multiplier)
        
        # Check limit
        allowed, metadata = limiter.consume(identifier, adjusted_cost)
        
        # Add tier info
        metadata["tier"] = tier.value
        metadata["tier_name"] = tier_config.name
        metadata["cost"] = adjusted_cost
        
        # Monitoring
        if self.enable_monitoring:
            self._record_request(identifier, tier, allowed, cost)
        
        return allowed, metadata
    
    def _record_request(
        self,
        identifier: str,
        tier: RateLimitTier,
        allowed: bool,
        cost: int
    ):
        """
        Record request for monitoring.
        
        Args:
            identifier: User identifier
            tier: User tier
            allowed: Whether request was allowed
            cost: Request cost
        """
        # Increment counters
        date_key = time.strftime("%Y-%m-%d")
        
        # Total requests
        self.redis.hincrby(
            f"rate_limit:stats:{date_key}",
            "total_requests",
            1
        )
        
        # Allowed/blocked
        status = "allowed" if allowed else "blocked"
        self.redis.hincrby(
            f"rate_limit:stats:{date_key}",
            status,
            1
        )
        
        # Per-tier stats
        self.redis.hincrby(
            f"rate_limit:stats:{date_key}:tier",
            tier.value,
            1
        )
        
        # Set expiry (keep stats for 30 days)
        self.redis.expire(f"rate_limit:stats:{date_key}", 86400 * 30)
    
    def get_stats(self, date: Optional[str] = None) -> Dict:
        """
        Get rate limiting statistics.
        
        Args:
            date: Date in YYYY-MM-DD format (default: today)
        
        Returns:
            Statistics dictionary
        """
        if not date:
            date = time.strftime("%Y-%m-%d")
        
        stats_key = f"rate_limit:stats:{date}"
        tier_key = f"rate_limit:stats:{date}:tier"
        
        stats = self.redis.hgetall(stats_key)
        tier_stats = self.redis.hgetall(tier_key)
        
        # Decode if bytes
        if stats and isinstance(list(stats.keys())[0], bytes):
            stats = {k.decode(): int(v) for k, v in stats.items()}
            tier_stats = {k.decode(): int(v) for k, v in tier_stats.items()}
        
        total = int(stats.get('total_requests', 0))
        allowed = int(stats.get('allowed', 0))
        blocked = int(stats.get('blocked', 0))
        
        return {
            "date": date,
            "total_requests": total,
            "allowed": allowed,
            "blocked": blocked,
            "block_rate": (blocked / total * 100) if total > 0 else 0,
            "tier_breakdown": tier_stats
        }


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    # Initialize limiter
    limiter = RateLimiter(redis)
    
    # Set up different users
    limiter.set_user_tier("free_user", RateLimitTier.FREE)
    limiter.set_user_tier("pro_user", RateLimitTier.PRO)
    
    # Test requests
    print("="*60)
    print("RATE LIMITER TEST")
    print("="*60)
    
    # Free user
    print("\nFree User:")
    for i in range(5):
        allowed, meta = limiter.check_rate_limit("free_user", cost=1)
        print(f"  Request {i+1}: Allowed={allowed}, "
              f"Remaining={meta['remaining']}, "
              f"Tier={meta['tier_name']}")
    
    # Pro user
    print("\nPro User:")
    for i in range(5):
        allowed, meta = limiter.check_rate_limit("pro_user", cost=10)
        print(f"  Request {i+1}: Allowed={allowed}, "
              f"Remaining={meta['remaining']}, "
              f"Tier={meta['tier_name']}")
    
    # Statistics
    print("\n" + "="*60)
    print("STATISTICS")
    print("="*60)
    stats = limiter.get_stats()
    print(f"\nDate: {stats['date']}")
    print(f"Total requests: {stats['total_requests']}")
    print(f"Allowed: {stats['allowed']}")
    print(f"Blocked: {stats['blocked']}")
    print(f"Block rate: {stats['block_rate']:.2f}%")
    print(f"\nPer-tier breakdown:")
    for tier, count in stats['tier_breakdown'].items():
        print(f"  {tier}: {count}")



API RATE LIMITING & THROTTLING GUIDE - TEIL 2
Per-User Limits, Headers, Middleware & Monitoring

📋 TABLE OF CONTENTS (TEIL 2)

Per-User vs Global Limits
Custom Rate Limit Headers
FastAPI Middleware Integration
Rate Limit Monitoring


👥 PER-USER VS GLOBAL LIMITS
1. Multi-Level Rate Limiting
python# core/rate_limiting/multi_level.py

"""
Multi-Level Rate Limiting

Implements both per-user and global rate limits
"""

from typing import Optional, Dict, Tuple, List
from dataclasses import dataclass
from enum import Enum
from redis import Redis
from loguru import logger

from core.rate_limiting.redis_limiter import (
    RateLimiter,
    RateLimitTier
)


class LimitScope(Enum):
    """Rate limit scope"""
    GLOBAL = "global"          # All users combined
    PER_USER = "per_user"      # Individual user
    PER_IP = "per_ip"          # Per IP address
    PER_ENDPOINT = "per_endpoint"  # Per API endpoint
    PER_API_KEY = "per_api_key"    # Per API key


@dataclass
class RateLimitResult:
    """Rate limit check result"""
    allowed: bool
    metadata: Dict
    limiting_scope: Optional[LimitScope] = None
    retry_after: Optional[int] = None


class MultiLevelRateLimiter:
    """
    Multi-level rate limiting system.
    
    Applies multiple rate limits simultaneously:
    1. Global limit (prevent system overload)
    2. Per-user limit (fair usage)
    3. Per-IP limit (prevent abuse)
    4. Per-endpoint limit (protect expensive operations)
    
    Request is allowed only if ALL limits pass.
    
    Example Configuration:
        Global: 10,000 req/min (system capacity)
        Per-user: 100 req/min (fair usage)
        Per-IP: 200 req/min (prevent IP abuse)
        Per-endpoint /ocr: 50 req/min (expensive operation)
    """
    
    def __init__(
        self,
        redis_client: Redis,
        user_limiter: RateLimiter,
        global_limit: Optional[int] = None,
        global_window: int = 60
    ):
        """
        Initialize multi-level limiter.
        
        Args:
            redis_client: Redis connection
            user_limiter: Per-user rate limiter
            global_limit: Global requests per window (None = disabled)
            global_window: Window size in seconds
        """
        self.redis = redis_client
        self.user_limiter = user_limiter
        self.global_limit = global_limit
        self.global_window = global_window
        
        logger.info(
            "Multi-level limiter initialized: "
            f"global={global_limit}/{global_window}s"
        )
    
    def check_limits(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        cost: int = 1
    ) -> RateLimitResult:
        """
        Check all applicable rate limits.
        
        Args:
            user_id: User identifier
            ip_address: IP address
            endpoint: API endpoint
            api_key: API key
            cost: Request cost in tokens
        
        Returns:
            RateLimitResult with combined check
        """
        # Check global limit first (fastest to reject)
        if self.global_limit:
            allowed, meta = self._check_global_limit()
            if not allowed:
                return RateLimitResult(
                    allowed=False,
                    metadata=meta,
                    limiting_scope=LimitScope.GLOBAL,
                    retry_after=meta.get('retry_after')
                )
        
        # Check IP limit
        if ip_address:
            allowed, meta = self._check_ip_limit(ip_address, cost)
            if not allowed:
                return RateLimitResult(
                    allowed=False,
                    metadata=meta,
                    limiting_scope=LimitScope.PER_IP,
                    retry_after=meta.get('retry_after')
                )
        
        # Check endpoint limit
        if endpoint:
            allowed, meta = self._check_endpoint_limit(endpoint, cost)
            if not allowed:
                return RateLimitResult(
                    allowed=False,
                    metadata=meta,
                    limiting_scope=LimitScope.PER_ENDPOINT,
                    retry_after=meta.get('retry_after')
                )
        
        # Check API key limit
        if api_key:
            allowed, meta = self._check_api_key_limit(api_key, cost)
            if not allowed:
                return RateLimitResult(
                    allowed=False,
                    metadata=meta,
                    limiting_scope=LimitScope.PER_API_KEY,
                    retry_after=meta.get('retry_after')
                )
        
        # Check per-user limit (most specific)
        if user_id:
            allowed, meta = self.user_limiter.check_rate_limit(user_id, cost)
            if not allowed:
                return RateLimitResult(
                    allowed=False,
                    metadata=meta,
                    limiting_scope=LimitScope.PER_USER,
                    retry_after=meta.get('retry_after')
                )
            
            # All checks passed - return user limit metadata
            return RateLimitResult(
                allowed=True,
                metadata=meta,
                limiting_scope=LimitScope.PER_USER
            )
        
        # No user_id but other checks passed
        return RateLimitResult(
            allowed=True,
            metadata={"limit": "unlimited"},
            limiting_scope=None
        )
    
    def _check_global_limit(self) -> Tuple[bool, Dict]:
        """
        Check global rate limit.
        
        Uses simple counter for performance.
        
        Returns:
            Tuple of (allowed, metadata)
        """
        import time
        
        current_window = int(time.time() / self.global_window)
        key = f"rate_limit:global:{current_window}"
        
        # Increment counter
        current = self.redis.incr(key)
        
        # Set expiry on first request
        if current == 1:
            self.redis.expire(key, self.global_window * 2)
        
        allowed = current <= self.global_limit
        
        metadata = {
            "limit": self.global_limit,
            "remaining": max(0, self.global_limit - current),
            "reset": (current_window + 1) * self.global_window,
            "scope": "global"
        }
        
        if not allowed:
            metadata["retry_after"] = self.global_window
        
        return allowed, metadata
    
    def _check_ip_limit(
        self,
        ip_address: str,
        cost: int
    ) -> Tuple[bool, Dict]:
        """
        Check per-IP rate limit.
        
        Prevents abuse from single IP.
        Typically more generous than per-user.
        
        Args:
            ip_address: IP address
            cost: Request cost
        
        Returns:
            Tuple of (allowed, metadata)
        """
        # Use token bucket with IP-specific limit
        # Typically 2-3x user limit
        from algorithms.token_bucket import (
            TokenBucketConfig,
            TokenBucketLuaRateLimiter
        )
        
        config = TokenBucketConfig(
            capacity=300,      # Higher than per-user
            refill_rate=5.0    # 5 per second = 300/min
        )
        
        limiter = TokenBucketLuaRateLimiter(self.redis, config)
        allowed, metadata = limiter.consume(
            f"ip:{ip_address}",
            cost
        )
        
        metadata["scope"] = "per_ip"
        
        return allowed, metadata
    
    def _check_endpoint_limit(
        self,
        endpoint: str,
        cost: int
    ) -> Tuple[bool, Dict]:
        """
        Check per-endpoint rate limit.
        
        Different endpoints can have different limits.
        Protects expensive operations.
        
        Args:
            endpoint: API endpoint path
            cost: Request cost
        
        Returns:
            Tuple of (allowed, metadata)
        """
        # Get endpoint-specific limit
        endpoint_limits = {
            "/ocr/process": (50, 1.0),      # 50 capacity, 1/sec
            "/ocr/batch": (10, 0.1),        # 10 capacity, 0.1/sec
            "/documents/upload": (100, 2.0), # 100 capacity, 2/sec
        }
        
        capacity, refill_rate = endpoint_limits.get(
            endpoint,
            (1000, 20.0)  # Default: generous
        )
        
        from algorithms.token_bucket import (
            TokenBucketConfig,
            TokenBucketLuaRateLimiter
        )
        
        config = TokenBucketConfig(
            capacity=capacity,
            refill_rate=refill_rate
        )
        
        limiter = TokenBucketLuaRateLimiter(self.redis, config)
        allowed, metadata = limiter.consume(
            f"endpoint:{endpoint}",
            cost
        )
        
        metadata["scope"] = "per_endpoint"
        metadata["endpoint"] = endpoint
        
        return allowed, metadata
    
    def _check_api_key_limit(
        self,
        api_key: str,
        cost: int
    ) -> Tuple[bool, Dict]:
        """
        Check per-API-key rate limit.
        
        Useful for service-to-service authentication.
        
        Args:
            api_key: API key
            cost: Request cost
        
        Returns:
            Tuple of (allowed, metadata)
        """
        # API keys might have different tiers
        # For now, use same logic as user limiter
        allowed, metadata = self.user_limiter.check_rate_limit(
            f"apikey:{api_key}",
            cost
        )
        
        metadata["scope"] = "per_api_key"
        
        return allowed, metadata


# ============================================
# COMPOSITE IDENTIFIER RATE LIMITING
# ============================================

class CompositeRateLimiter:
    """
    Rate limiting with composite identifiers.
    
    Combines multiple identifiers for more granular control.
    
    Examples:
        - user_id + endpoint: Different limits per user per endpoint
        - user_id + ip: Prevent account sharing
        - api_key + endpoint: Different limits per key per endpoint
    """
    
    def __init__(self, redis_client: Redis):
        """Initialize composite limiter"""
        self.redis = redis_client
    
    def check_limit(
        self,
        identifiers: List[str],
        capacity: int,
        refill_rate: float,
        cost: int = 1
    ) -> Tuple[bool, Dict]:
        """
        Check rate limit with composite identifier.
        
        Args:
            identifiers: List of identifier parts
            capacity: Token bucket capacity
            refill_rate: Refill rate (tokens/second)
            cost: Request cost
        
        Returns:
            Tuple of (allowed, metadata)
        
        Example:
            # Limit user on specific endpoint
            check_limit(
                ["user_123", "/ocr/process"],
                capacity=50,
                refill_rate=1.0
            )
        """
        from algorithms.token_bucket import (
            TokenBucketConfig,
            TokenBucketLuaRateLimiter
        )
        
        # Create composite key
        composite_key = ":".join(identifiers)
        
        config = TokenBucketConfig(
            capacity=capacity,
            refill_rate=refill_rate
        )
        
        limiter = TokenBucketLuaRateLimiter(self.redis, config)
        return limiter.consume(composite_key, cost)


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    # Setup
    user_limiter = RateLimiter(redis)
    multi_limiter = MultiLevelRateLimiter(
        redis_client=redis,
        user_limiter=user_limiter,
        global_limit=10000,  # 10k req/min globally
        global_window=60
    )
    
    print("="*60)
    print("MULTI-LEVEL RATE LIMITING TEST")
    print("="*60)
    
    # Test scenarios
    scenarios = [
        {
            "name": "Normal user request",
            "user_id": "user_123",
            "ip_address": "192.168.1.100",
            "endpoint": "/users",
            "cost": 1
        },
        {
            "name": "OCR request (expensive)",
            "user_id": "user_123",
            "ip_address": "192.168.1.100",
            "endpoint": "/ocr/process",
            "cost": 10
        },
        {
            "name": "Batch OCR (very expensive)",
            "user_id": "pro_user",
            "ip_address": "192.168.1.101",
            "endpoint": "/ocr/batch",
            "cost": 50
        },
    ]
    
    for scenario in scenarios:
        print(f"\n{scenario['name']}:")
        print(f"  User: {scenario['user_id']}")
        print(f"  IP: {scenario['ip_address']}")
        print(f"  Endpoint: {scenario['endpoint']}")
        print(f"  Cost: {scenario['cost']}")
        
        result = multi_limiter.check_limits(**scenario)
        
        print(f"  → Allowed: {result.allowed}")
        print(f"  → Limited by: {result.limiting_scope.value if result.limiting_scope else 'None'}")
        print(f"  → Remaining: {result.metadata.get('remaining', 'N/A')}")
        
        if not result.allowed and result.retry_after:
            print(f"  → Retry after: {result.retry_after}s")
2. Dynamic Limit Adjustment
python# core/rate_limiting/dynamic_limits.py

"""
Dynamic Rate Limit Adjustment

Adjust limits based on system load and user behavior
"""

from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from redis import Redis
from loguru import logger


@dataclass
class SystemMetrics:
    """System metrics for dynamic adjustment"""
    cpu_usage: float        # 0-100
    memory_usage: float     # 0-100
    request_rate: float     # requests/second
    error_rate: float       # 0-100
    queue_depth: int        # pending tasks


class DynamicRateLimiter:
    """
    Dynamically adjust rate limits based on system load.
    
    Features:
    - Reduce limits when system is under stress
    - Increase limits when system has capacity
    - Per-user behavior analysis
    - Automatic throttling during incidents
    """
    
    def __init__(
        self,
        redis_client: Redis,
        base_capacity: int = 100,
        base_refill_rate: float = 10.0
    ):
        """
        Initialize dynamic limiter.
        
        Args:
            redis_client: Redis connection
            base_capacity: Base token capacity
            base_refill_rate: Base refill rate
        """
        self.redis = redis_client
        self.base_capacity = base_capacity
        self.base_refill_rate = base_refill_rate
    
    def get_adjusted_limits(
        self,
        user_id: str,
        metrics: SystemMetrics
    ) -> Dict[str, float]:
        """
        Get adjusted limits based on system metrics.
        
        Args:
            user_id: User identifier
            metrics: Current system metrics
        
        Returns:
            Adjusted limits dictionary
        """
        # Start with base values
        capacity = float(self.base_capacity)
        refill_rate = float(self.base_refill_rate)
        
        # Adjust based on CPU usage
        if metrics.cpu_usage > 80:
            # High CPU - reduce by 50%
            capacity *= 0.5
            refill_rate *= 0.5
            logger.warning(f"High CPU ({metrics.cpu_usage}%) - reducing limits")
        elif metrics.cpu_usage > 60:
            # Medium CPU - reduce by 25%
            capacity *= 0.75
            refill_rate *= 0.75
        
        # Adjust based on memory usage
        if metrics.memory_usage > 80:
            capacity *= 0.7
            refill_rate *= 0.7
            logger.warning(f"High memory ({metrics.memory_usage}%) - reducing limits")
        
        # Adjust based on error rate
        if metrics.error_rate > 10:
            # High error rate - significantly reduce
            capacity *= 0.5
            refill_rate *= 0.5
            logger.warning(f"High error rate ({metrics.error_rate}%) - reducing limits")
        
        # Adjust based on queue depth
        if metrics.queue_depth > 1000:
            capacity *= 0.6
            refill_rate *= 0.6
            logger.warning(f"High queue depth ({metrics.queue_depth}) - reducing limits")
        
        # User-specific adjustments
        user_behavior = self._analyze_user_behavior(user_id)
        
        if user_behavior["is_good_citizen"]:
            # Reward good behavior
            capacity *= 1.2
            refill_rate *= 1.2
        elif user_behavior["is_abusive"]:
            # Penalize abuse
            capacity *= 0.3
            refill_rate *= 0.3
            logger.warning(f"Abusive behavior detected for {user_id}")
        
        return {
            "capacity": int(capacity),
            "refill_rate": refill_rate,
            "adjustment_reason": self._get_adjustment_reason(metrics, user_behavior)
        }
    
    def _analyze_user_behavior(self, user_id: str) -> Dict:
        """
        Analyze user behavior.
        
        Args:
            user_id: User identifier
        
        Returns:
            Behavior analysis
        """
        # Get user stats from last hour
        key = f"user_behavior:{user_id}"
        
        stats = self.redis.hgetall(key)
        
        if not stats:
            return {
                "is_good_citizen": False,
                "is_abusive": False,
                "total_requests": 0
            }
        
        total_requests = int(stats.get(b'total_requests', 0))
        rejected_requests = int(stats.get(b'rejected_requests', 0))
        
        if total_requests == 0:
            rejection_rate = 0
        else:
            rejection_rate = rejected_requests / total_requests
        
        # Good citizen: low rejection rate, moderate usage
        is_good_citizen = (
            total_requests > 10 and
            total_requests < 1000 and
            rejection_rate < 0.05
        )
        
        # Abusive: high rejection rate or excessive requests
        is_abusive = (
            rejection_rate > 0.5 or
            total_requests > 10000
        )
        
        return {
            "is_good_citizen": is_good_citizen,
            "is_abusive": is_abusive,
            "total_requests": total_requests,
            "rejection_rate": rejection_rate
        }
    
    def _get_adjustment_reason(
        self,
        metrics: SystemMetrics,
        user_behavior: Dict
    ) -> str:
        """Generate human-readable adjustment reason"""
        reasons = []
        
        if metrics.cpu_usage > 60:
            reasons.append(f"high CPU ({metrics.cpu_usage}%)")
        
        if metrics.memory_usage > 60:
            reasons.append(f"high memory ({metrics.memory_usage}%)")
        
        if metrics.error_rate > 5:
            reasons.append(f"high errors ({metrics.error_rate}%)")
        
        if user_behavior["is_good_citizen"]:
            reasons.append("good user behavior (bonus)")
        
        if user_behavior["is_abusive"]:
            reasons.append("abusive behavior (penalty)")
        
        return ", ".join(reasons) if reasons else "normal operation"
    
    def record_user_request(
        self,
        user_id: str,
        allowed: bool
    ):
        """
        Record user request for behavior analysis.
        
        Args:
            user_id: User identifier
            allowed: Whether request was allowed
        """
        key = f"user_behavior:{user_id}"
        
        # Increment counters
        self.redis.hincrby(key, 'total_requests', 1)
        
        if not allowed:
            self.redis.hincrby(key, 'rejected_requests', 1)
        
        # Set expiry (1 hour rolling window)
        self.redis.expire(key, 3600)


# ============================================
# CIRCUIT BREAKER INTEGRATION
# ============================================

class CircuitBreakerRateLimiter:
    """
    Rate limiter with circuit breaker pattern.
    
    Automatically opens circuit (blocks all requests)
    when error threshold is exceeded.
    """
    
    def __init__(
        self,
        redis_client: Redis,
        error_threshold: float = 50.0,  # %
        check_window: int = 60  # seconds
    ):
        """
        Initialize circuit breaker limiter.
        
        Args:
            redis_client: Redis connection
            error_threshold: Error rate threshold to open circuit
            check_window: Window for error rate calculation
        """
        self.redis = redis_client
        self.error_threshold = error_threshold
        self.check_window = check_window
    
    def is_circuit_open(self, identifier: str) -> bool:
        """
        Check if circuit is open for identifier.
        
        Args:
            identifier: User/endpoint identifier
        
        Returns:
            True if circuit is open (blocking)
        """
        key = f"circuit_breaker:{identifier}"
        return bool(self.redis.get(key))
    
    def check_and_update_circuit(
        self,
        identifier: str,
        success: bool
    ) -> bool:
        """
        Update circuit state based on request result.
        
        Args:
            identifier: User/endpoint identifier
            success: Whether request succeeded
        
        Returns:
            True if circuit is open (blocking)
        """
        import time
        
        window_key = f"circuit_stats:{identifier}:{int(time.time() / self.check_window)}"
        
        # Increment counters
        self.redis.hincrby(window_key, 'total', 1)
        
        if not success:
            self.redis.hincrby(window_key, 'errors', 1)
        
        self.redis.expire(window_key, self.check_window * 2)
        
        # Check error rate
        stats = self.redis.hgetall(window_key)
        
        if stats:
            total = int(stats.get(b'total', 0))
            errors = int(stats.get(b'errors', 0))
            
            if total > 10:  # Minimum requests before checking
                error_rate = (errors / total) * 100
                
                if error_rate > self.error_threshold:
                    # Open circuit
                    circuit_key = f"circuit_breaker:{identifier}"
                    self.redis.setex(
                        circuit_key,
                        self.check_window,
                        "open"
                    )
                    logger.warning(
                        f"Circuit opened for {identifier}: "
                        f"error_rate={error_rate:.1f}%"
                    )
                    return True
        
        return False


if __name__ == "__main__":
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    # Test dynamic limits
    limiter = DynamicRateLimiter(redis)
    
    # Simulate different system states
    scenarios = [
        {
            "name": "Normal operation",
            "metrics": SystemMetrics(
                cpu_usage=30,
                memory_usage=40,
                request_rate=100,
                error_rate=1,
                queue_depth=50
            )
        },
        {
            "name": "High load",
            "metrics": SystemMetrics(
                cpu_usage=85,
                memory_usage=90,
                request_rate=500,
                error_rate=15,
                queue_depth=2000
            )
        },
    ]
    
    print("="*60)
    print("DYNAMIC RATE LIMITING TEST")
    print("="*60)
    
    for scenario in scenarios:
        print(f"\n{scenario['name']}:")
        print(f"  CPU: {scenario['metrics'].cpu_usage}%")
        print(f"  Memory: {scenario['metrics'].memory_usage}%")
        print(f"  Error rate: {scenario['metrics'].error_rate}%")
        
        limits = limiter.get_adjusted_limits("user_123", scenario['metrics'])
        
        print(f"  → Capacity: {limits['capacity']}")
        print(f"  → Refill rate: {limits['refill_rate']:.2f} tokens/sec")
        print(f"  → Reason: {limits['adjustment_reason']}")

📋 CUSTOM RATE LIMIT HEADERS
1. Standard Rate Limit Headers
python# core/rate_limiting/headers.py

"""
Rate Limit HTTP Headers

Standard headers for communicating rate limits to clients
"""

from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RateLimitHeaders:
    """
    Rate limit headers following industry standards.
    
    Implements:
    - IETF Draft Standard (RateLimit-*)
    - X-RateLimit-* (de facto standard)
    - Retry-After (RFC 7231)
    """
    
    # Current limits
    limit: int                  # Max requests per window
    remaining: int              # Remaining requests
    reset: int                  # Unix timestamp when limit resets
    
    # Optional metadata
    used: Optional[int] = None  # Requests used
    retry_after: Optional[int] = None  # Seconds until retry
    
    # Scope information
    scope: Optional[str] = None        # e.g., "user", "ip", "global"
    policy: Optional[str] = None       # e.g., "100;w=60" (100 per 60s)
    
    def to_dict(self, standard: str = "both") -> Dict[str, str]:
        """
        Convert to header dictionary.
        
        Args:
            standard: Which standard to use
                - "ietf": Use RateLimit-* headers
                - "x-ratelimit": Use X-RateLimit-* headers
                - "both": Use both (default)
        
        Returns:
            Dictionary of headers
        """
        headers = {}
        
        # IETF Draft Standard
        if standard in ("ietf", "both"):
            headers.update({
                "RateLimit-Limit": str(self.limit),
                "RateLimit-Remaining": str(self.remaining),
                "RateLimit-Reset": str(self.reset),
            })
            
            if self.policy:
                headers["RateLimit-Policy"] = self.policy
        
        # X-RateLimit-* (de facto standard)
        if standard in ("x-ratelimit", "both"):
            headers.update({
                "X-RateLimit-Limit": str(self.limit),
                "X-RateLimit-Remaining": str(self.remaining),
                "X-RateLimit-Reset": str(self.reset),
            })
            
            if self.used is not None:
                headers["X-RateLimit-Used"] = str(self.used)
        
        # Retry-After (when rate limited)
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        
        # Custom scope header
        if self.scope:
            headers["X-RateLimit-Scope"] = self.scope
        
        return headers
    
    @classmethod
    def from_metadata(
        cls,
        metadata: Dict,
        retry_after: Optional[int] = None
    ) -> 'RateLimitHeaders':
        """
        Create headers from rate limiter metadata.
        
        Args:
            metadata: Metadata from rate limiter
            retry_after: Optional retry-after value
        
        Returns:
            RateLimitHeaders instance
        """
        limit = metadata.get('limit', 0)
        remaining = metadata.get('remaining', 0)
        reset = metadata.get('reset', 0)
        scope = metadata.get('scope')
        
        # Calculate used
        used = limit - remaining
        
        # Build policy string
        # Format: "limit;w=window" (e.g., "100;w=60" = 100 per 60 seconds)
        refill_rate = metadata.get('refill_rate')
        if refill_rate and limit:
            window = int(limit / refill_rate)
            policy = f"{limit};w={window}"
        else:
            policy = None
        
        return cls(
            limit=limit,
            remaining=remaining,
            reset=reset,
            used=used,
            retry_after=retry_after,
            scope=scope,
            policy=policy
        )


# ============================================
# RESPONSE BUILDER
# ============================================

class RateLimitResponse:
    """Build rate limit responses"""
    
    @staticmethod
    def success_response(
        data: Dict,
        headers: RateLimitHeaders
    ) -> Dict:
        """
        Build successful response with rate limit headers.
        
        Args:
            data: Response data
            headers: Rate limit headers
        
        Returns:
            Response dictionary
        """
        return {
            "data": data,
            "headers": headers.to_dict(),
            "status_code": 200
        }
    
    @staticmethod
    def rate_limited_response(
        headers: RateLimitHeaders,
        message: Optional[str] = None
    ) -> Dict:
        """
        Build 429 Too Many Requests response.
        
        Args:
            headers: Rate limit headers
            message: Optional custom message
        
        Returns:
            Response dictionary
        """
        if not message:
            if headers.retry_after:
                message = f"Rate limit exceeded. Retry after {headers.retry_after} seconds."
            else:
                reset_time = datetime.fromtimestamp(headers.reset)
                message = f"Rate limit exceeded. Resets at {reset_time.isoformat()}."
        
        return {
            "error": {
                "code": "rate_limit_exceeded",
                "message": message,
                "retry_after": headers.retry_after,
                "limit": headers.limit,
                "reset": headers.reset
            },
            "headers": headers.to_dict(),
            "status_code": 429
        }


# ============================================
# HEADER EXAMPLES
# ============================================

def demonstrate_headers():
    """Demonstrate different header formats"""
    
    metadata = {
        "limit": 100,
        "remaining": 75,
        "reset": 1704067200,  # 2024-01-01 00:00:00
        "refill_rate": 10.0,
        "scope": "user"
    }
    
    print("="*60)
    print("RATE LIMIT HEADERS DEMONSTRATION")
    print("="*60)
    
    # Create headers
    headers = RateLimitHeaders.from_metadata(metadata)
    
    # IETF Standard
    print("\nIETF Standard Headers:")
    print("-" * 60)
    for key, value in headers.to_dict("ietf").items():
        print(f"  {key}: {value}")
    
    # X-RateLimit Standard
    print("\nX-RateLimit Headers:")
    print("-" * 60)
    for key, value in headers.to_dict("x-ratelimit").items():
        print(f"  {key}: {value}")
    
    # Both
    print("\nBoth Standards:")
    print("-" * 60)
    for key, value in headers.to_dict("both").items():
        print(f"  {key}: {value}")
    
    # Rate Limited Response
    print("\n" + "="*60)
    print("RATE LIMITED RESPONSE (429)")
    print("="*60)
    
    limited_headers = RateLimitHeaders.from_metadata(
        {**metadata, "remaining": 0},
        retry_after=60
    )
    
    response = RateLimitResponse.rate_limited_response(limited_headers)
    
    print(f"\nStatus: {response['status_code']}")
    print("\nHeaders:")
    for key, value in response['headers'].items():
        print(f"  {key}: {value}")
    
    print("\nBody:")
    import json
    print(json.dumps(response['error'], indent=2))


if __name__ == "__main__":
    demonstrate_headers()

🔌 FASTAPI MIDDLEWARE INTEGRATION
1. Rate Limiting Middleware
python# middleware/rate_limiting.py

"""
FastAPI Rate Limiting Middleware

Production-ready middleware with all features
"""

from typing import Optional, Callable, List
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from loguru import logger
import time

from core.rate_limiting.multi_level import (
    MultiLevelRateLimiter,
    RateLimitResult
)
from core.rate_limiting.headers import (
    RateLimitHeaders,
    RateLimitResponse
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for FastAPI.
    
    Features:
    - Automatic user/IP detection
    - Standard headers
    - Whitelist support
    - Bypass for health checks
    - Comprehensive logging
    """
    
    def __init__(
        self,
        app: ASGIApp,
        limiter: MultiLevelRateLimiter,
        get_identifier: Optional[Callable] = None,
        bypass_paths: Optional[List[str]] = None,
        enable_headers: bool = True
    ):
        """
        Initialize middleware.
        
        Args:
            app: FastAPI application
            limiter: Rate limiter instance
            get_identifier: Function to extract user identifier
            bypass_paths: Paths to bypass rate limiting
            enable_headers: Add rate limit headers to responses
        """
        super().__init__(app)
        self.limiter = limiter
        self.get_identifier = get_identifier or self._default_identifier
        self.bypass_paths = bypass_paths or ["/health", "/metrics", "/docs", "/openapi.json"]
        self.enable_headers = enable_headers
        
        logger.info("Rate limiting middleware initialized")
    
    async def dispatch(
        self,
        request: Request,
        call_next: Callable
    ) -> Response:
        """
        Process request with rate limiting.
        
        Args:
            request: FastAPI request
            call_next: Next middleware/handler
        
        Returns:
            Response with rate limit headers
        """
        # Check if path should bypass rate limiting
        if self._should_bypass(request):
            return await call_next(request)
        
        # Extract identifiers
        user_id = self.get_identifier(request)
        ip_address = self._get_ip(request)
        endpoint = f"{request.method}:{request.url.path}"
        api_key = self._get_api_key(request)
        
        # Determine request cost
        cost = self._get_request_cost(request)
        
        # Check rate limits
        result = self.limiter.check_limits(
            user_id=user_id,
            ip_address=ip_address,
            endpoint=endpoint,
            api_key=api_key,
            cost=cost
        )
        
        # Log rate limit check
        logger.debug(
            f"Rate limit check: user={user_id}, ip={ip_address}, "
            f"endpoint={endpoint}, allowed={result.allowed}"
        )
        
        # If rate limited, return 429
        if not result.allowed:
            headers_obj = RateLimitHeaders.from_metadata(
                result.metadata,
                retry_after=result.retry_after
            )
            
            logger.warning(
                f"Rate limit exceeded: user={user_id}, "
                f"scope={result.limiting_scope.value}, "
                f"retry_after={result.retry_after}s"
            )
            
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": {
                        "code": "rate_limit_exceeded",
                        "message": f"Rate limit exceeded. Limited by: {result.limiting_scope.value}",
                        "retry_after": result.retry_after,
                        "scope": result.limiting_scope.value
                    }
                },
                headers=headers_obj.to_dict()
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        if self.enable_headers:
            headers_obj = RateLimitHeaders.from_metadata(result.metadata)
            
            for key, value in headers_obj.to_dict().items():
                response.headers[key] = value
        
        return response
    
    def _should_bypass(self, request: Request) -> bool:
        """Check if request should bypass rate limiting"""
        path = request.url.path
        
        # Check bypass paths
        for bypass_path in self.bypass_paths:
            if path.startswith(bypass_path):
                return True
        
        return False
    
    def _default_identifier(self, request: Request) -> Optional[str]:
        """
        Default user identifier extraction.
        
        Priority:
        1. Authenticated user ID
        2. API key
        3. None (will use IP only)
        """
        # Check for user in request state (set by auth middleware)
        if hasattr(request.state, "user"):
            return f"user:{request.state.user.id}"
        
        # Check for API key
        api_key = self._get_api_key(request)
        if api_key:
            return f"apikey:{api_key}"
        
        return None
    
    def _get_ip(self, request: Request) -> str:
        """
        Extract IP address from request.
        
        Handles X-Forwarded-For, X-Real-IP headers
        """
        # Check X-Forwarded-For
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take first IP (client)
            return forwarded.split(",")[0].strip()
        
        # Check X-Real-IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Use direct client
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _get_api_key(self, request: Request) -> Optional[str]:
        """Extract API key from request"""
        # Check header
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return api_key
        
        # Check query parameter
        return request.query_params.get("api_key")
    
    def _get_request_cost(self, request: Request) -> int:
        """
        Determine request cost.
        
        Can be overridden for custom cost calculation.
        """
        # Expensive endpoints
        expensive_endpoints = {
            "/ocr/process": 10,
            "/ocr/batch": 50,
            "/documents/upload": 5,
        }
        
        for endpoint, cost in expensive_endpoints.items():
            if request.url.path.startswith(endpoint):
                return cost
        
        # Default cost
        return 1


# ============================================
# DECORATOR FOR ROUTE-SPECIFIC LIMITS
# ============================================

from functools import wraps
from fastapi import Depends


def rate_limit(
    max_requests: int,
    window_seconds: int = 60,
    scope: str = "user"
):
    """
    Decorator for route-specific rate limits.
    
    Args:
        max_requests: Max requests per window
        window_seconds: Window size in seconds
        scope: Limit scope (user, ip, global)
    
    Example:
        @app.get("/expensive")
        @rate_limit(max_requests=10, window_seconds=60)
        async def expensive_endpoint():
            return {"data": "result"}
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get request from kwargs
            request = kwargs.get('request')
            
            if not request:
                # Try to find in args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if request:
                # Apply rate limit
                # (Implementation would use limiter from dependency injection)
                pass
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# ============================================
# FASTAPI APPLICATION SETUP
# ============================================

def create_app_with_rate_limiting():
    """Example FastAPI app with rate limiting"""
    from fastapi import FastAPI
    from redis import Redis
    
    # Create app
    app = FastAPI(title="OCR API with Rate Limiting")
    
    # Setup rate limiter
    redis_client = Redis(host='localhost', port=6379, decode_responses=True)
    
    from core.rate_limiting.redis_limiter import RateLimiter
    
    user_limiter = RateLimiter(redis_client)
    multi_limiter = MultiLevelRateLimiter(
        redis_client=redis_client,
        user_limiter=user_limiter,
        global_limit=10000,
        global_window=60
    )
    
    # Add middleware
    app.add_middleware(
        RateLimitMiddleware,
        limiter=multi_limiter,
        bypass_paths=["/health", "/docs", "/openapi.json"]
    )
    
    # Routes
    @app.get("/health")
    async def health():
        """Health check (bypasses rate limiting)"""
        return {"status": "healthy"}
    
    @app.get("/users")
    async def list_users(request: Request):
        """List users (light endpoint)"""
        return {"users": []}
    
    @app.post("/ocr/process")
    async def process_ocr(request: Request):
        """Process OCR (expensive endpoint)"""
        return {"result": "processing"}
    
    return app


if __name__ == "__main__":
    import uvicorn
    
    app = create_app_with_rate_limiting()
    
    print("="*60)
    print("FASTAPI RATE LIMITING EXAMPLE")
    print("="*60)
    print("\nStarting server...")
    print("Try these endpoints:")
    print("  GET  http://localhost:8000/health")
    print("  GET  http://localhost:8000/users")
    print("  POST http://localhost:8000/ocr/process")
    print("\nWatch the rate limit headers in responses!")
    print("="*60)
    
    uvicorn.run(app, host="0.0.0.0", port=8000)




API RATE LIMITING & THROTTLING GUIDE - TEIL 3 (FINAL)
Monitoring, Whitelisting, Testing & Best Practices

📋 TABLE OF CONTENTS (TEIL 3)

Rate Limit Monitoring
Bypass Mechanisms (Whitelisting)
Testing Strategies
Best Practices & Troubleshooting
Complete Setup Guide


📊 RATE LIMIT MONITORING
1. Metrics Collection
python# monitoring/metrics.py

"""
Rate Limiting Metrics Collection

Prometheus-compatible metrics for monitoring
"""

from typing import Dict, Optional
from dataclasses import dataclass
from datetime import datetime
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Summary,
    CollectorRegistry
)
from redis import Redis
from loguru import logger


@dataclass
class RateLimitMetrics:
    """Rate limiting metrics"""
    
    # Counters
    requests_total: Counter
    requests_allowed: Counter
    requests_blocked: Counter
    
    # By scope
    requests_by_scope: Counter
    blocked_by_scope: Counter
    
    # By tier
    requests_by_tier: Counter
    blocked_by_tier: Counter
    
    # Latency
    check_duration: Histogram
    
    # Current state
    active_limiters: Gauge
    tokens_remaining: Gauge


class RateLimitMonitor:
    """
    Monitor rate limiting metrics.
    
    Features:
    - Prometheus metrics
    - Real-time statistics
    - Alerting thresholds
    - Historical data
    """
    
    def __init__(
        self,
        redis_client: Redis,
        registry: Optional[CollectorRegistry] = None
    ):
        """
        Initialize monitor.
        
        Args:
            redis_client: Redis connection
            registry: Prometheus registry (None = default)
        """
        self.redis = redis_client
        self.registry = registry or CollectorRegistry()
        
        # Initialize metrics
        self.metrics = self._create_metrics()
        
        logger.info("Rate limit monitor initialized")
    
    def _create_metrics(self) -> RateLimitMetrics:
        """Create Prometheus metrics"""
        
        return RateLimitMetrics(
            # Total requests
            requests_total=Counter(
                'rate_limit_requests_total',
                'Total rate limit checks',
                ['endpoint', 'method'],
                registry=self.registry
            ),
            
            # Allowed requests
            requests_allowed=Counter(
                'rate_limit_requests_allowed_total',
                'Allowed requests',
                ['endpoint', 'method'],
                registry=self.registry
            ),
            
            # Blocked requests
            requests_blocked=Counter(
                'rate_limit_requests_blocked_total',
                'Blocked requests',
                ['endpoint', 'method', 'reason'],
                registry=self.registry
            ),
            
            # By scope
            requests_by_scope=Counter(
                'rate_limit_requests_by_scope_total',
                'Requests by scope',
                ['scope'],
                registry=self.registry
            ),
            
            blocked_by_scope=Counter(
                'rate_limit_blocked_by_scope_total',
                'Blocked by scope',
                ['scope'],
                registry=self.registry
            ),
            
            # By tier
            requests_by_tier=Counter(
                'rate_limit_requests_by_tier_total',
                'Requests by tier',
                ['tier'],
                registry=self.registry
            ),
            
            blocked_by_tier=Counter(
                'rate_limit_blocked_by_tier_total',
                'Blocked by tier',
                ['tier'],
                registry=self.registry
            ),
            
            # Latency
            check_duration=Histogram(
                'rate_limit_check_duration_seconds',
                'Rate limit check duration',
                ['scope'],
                registry=self.registry
            ),
            
            # Gauges
            active_limiters=Gauge(
                'rate_limit_active_limiters',
                'Number of active rate limiters',
                registry=self.registry
            ),
            
            tokens_remaining=Gauge(
                'rate_limit_tokens_remaining',
                'Tokens remaining',
                ['identifier', 'tier'],
                registry=self.registry
            )
        )
    
    def record_request(
        self,
        allowed: bool,
        endpoint: str,
        method: str,
        scope: Optional[str] = None,
        tier: Optional[str] = None,
        reason: Optional[str] = None,
        duration: Optional[float] = None
    ):
        """
        Record rate limit check.
        
        Args:
            allowed: Whether request was allowed
            endpoint: API endpoint
            method: HTTP method
            scope: Limit scope
            tier: User tier
            reason: Block reason if not allowed
            duration: Check duration in seconds
        """
        # Total requests
        self.metrics.requests_total.labels(
            endpoint=endpoint,
            method=method
        ).inc()
        
        # Allowed/blocked
        if allowed:
            self.metrics.requests_allowed.labels(
                endpoint=endpoint,
                method=method
            ).inc()
        else:
            self.metrics.requests_blocked.labels(
                endpoint=endpoint,
                method=method,
                reason=reason or "unknown"
            ).inc()
        
        # By scope
        if scope:
            self.metrics.requests_by_scope.labels(scope=scope).inc()
            
            if not allowed:
                self.metrics.blocked_by_scope.labels(scope=scope).inc()
        
        # By tier
        if tier:
            self.metrics.requests_by_tier.labels(tier=tier).inc()
            
            if not allowed:
                self.metrics.blocked_by_tier.labels(tier=tier).inc()
        
        # Duration
        if duration and scope:
            self.metrics.check_duration.labels(scope=scope).observe(duration)
    
    def update_tokens(
        self,
        identifier: str,
        tier: str,
        tokens: int
    ):
        """
        Update tokens remaining gauge.
        
        Args:
            identifier: User identifier
            tier: User tier
            tokens: Tokens remaining
        """
        self.metrics.tokens_remaining.labels(
            identifier=identifier,
            tier=tier
        ).set(tokens)
    
    def get_statistics(
        self,
        time_range: str = "1h"
    ) -> Dict:
        """
        Get rate limiting statistics.
        
        Args:
            time_range: Time range (1h, 24h, 7d)
        
        Returns:
            Statistics dictionary
        """
        # Get from Redis
        stats_key = f"rate_limit:stats:{time_range}"
        stats = self.redis.hgetall(stats_key)
        
        if not stats:
            return {
                "time_range": time_range,
                "total": 0,
                "allowed": 0,
                "blocked": 0,
                "block_rate": 0.0
            }
        
        # Decode if bytes
        if stats and isinstance(list(stats.keys())[0], bytes):
            stats = {k.decode(): int(v) for k, v in stats.items()}
        
        total = int(stats.get('total', 0))
        allowed = int(stats.get('allowed', 0))
        blocked = int(stats.get('blocked', 0))
        
        return {
            "time_range": time_range,
            "total": total,
            "allowed": allowed,
            "blocked": blocked,
            "block_rate": (blocked / total * 100) if total > 0 else 0.0,
            "by_scope": self._get_scope_stats(time_range),
            "by_tier": self._get_tier_stats(time_range)
        }
    
    def _get_scope_stats(self, time_range: str) -> Dict:
        """Get statistics by scope"""
        key = f"rate_limit:stats:{time_range}:scope"
        stats = self.redis.hgetall(key)
        
        if stats and isinstance(list(stats.keys())[0], bytes):
            return {k.decode(): int(v) for k, v in stats.items()}
        
        return stats or {}
    
    def _get_tier_stats(self, time_range: str) -> Dict:
        """Get statistics by tier"""
        key = f"rate_limit:stats:{time_range}:tier"
        stats = self.redis.hgetall(key)
        
        if stats and isinstance(list(stats.keys())[0], bytes):
            return {k.decode(): int(v) for k, v in stats.items()}
        
        return stats or {}
    
    def check_alerts(self) -> list[Dict]:
        """
        Check for alert conditions.
        
        Returns:
            List of active alerts
        """
        alerts = []
        
        # Get recent stats
        stats = self.get_statistics("1h")
        
        # High block rate
        if stats['block_rate'] > 50:
            alerts.append({
                "severity": "critical",
                "title": "High Rate Limit Block Rate",
                "message": f"Block rate is {stats['block_rate']:.1f}% in last hour",
                "metric": "block_rate",
                "value": stats['block_rate'],
                "threshold": 50
            })
        elif stats['block_rate'] > 30:
            alerts.append({
                "severity": "warning",
                "title": "Elevated Rate Limit Block Rate",
                "message": f"Block rate is {stats['block_rate']:.1f}% in last hour",
                "metric": "block_rate",
                "value": stats['block_rate'],
                "threshold": 30
            })
        
        # High total requests
        if stats['total'] > 100000:
            alerts.append({
                "severity": "info",
                "title": "High Request Volume",
                "message": f"{stats['total']} requests in last hour",
                "metric": "total_requests",
                "value": stats['total'],
                "threshold": 100000
            })
        
        return alerts


# ============================================
# GRAFANA DASHBOARD EXPORT
# ============================================

GRAFANA_DASHBOARD = {
    "dashboard": {
        "title": "Rate Limiting Dashboard",
        "tags": ["rate-limiting", "api"],
        "timezone": "browser",
        "panels": [
            {
                "title": "Request Rate",
                "type": "graph",
                "targets": [
                    {
                        "expr": "rate(rate_limit_requests_total[5m])",
                        "legendFormat": "{{endpoint}}"
                    }
                ]
            },
            {
                "title": "Block Rate",
                "type": "graph",
                "targets": [
                    {
                        "expr": "rate(rate_limit_requests_blocked_total[5m]) / rate(rate_limit_requests_total[5m]) * 100",
                        "legendFormat": "Block Rate %"
                    }
                ]
            },
            {
                "title": "Requests by Tier",
                "type": "pie",
                "targets": [
                    {
                        "expr": "sum by (tier) (rate_limit_requests_by_tier_total)",
                        "legendFormat": "{{tier}}"
                    }
                ]
            },
            {
                "title": "Check Duration",
                "type": "graph",
                "targets": [
                    {
                        "expr": "histogram_quantile(0.95, rate(rate_limit_check_duration_seconds_bucket[5m]))",
                        "legendFormat": "p95"
                    }
                ]
            }
        ]
    }
}


# ============================================
# ALERTING RULES
# ============================================

PROMETHEUS_ALERTS = """
groups:
  - name: rate_limiting
    interval: 30s
    rules:
      # High block rate
      - alert: HighRateLimitBlockRate
        expr: |
          (
            sum(rate(rate_limit_requests_blocked_total[5m]))
            /
            sum(rate(rate_limit_requests_total[5m]))
          ) * 100 > 50
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High rate limit block rate"
          description: "Rate limit block rate is {{ $value | humanize }}%"
      
      # Elevated block rate
      - alert: ElevatedRateLimitBlockRate
        expr: |
          (
            sum(rate(rate_limit_requests_blocked_total[5m]))
            /
            sum(rate(rate_limit_requests_total[5m]))
          ) * 100 > 30
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Elevated rate limit block rate"
          description: "Rate limit block rate is {{ $value | humanize }}%"
      
      # High request volume
      - alert: HighRequestVolume
        expr: sum(rate(rate_limit_requests_total[5m])) > 1000
        for: 5m
        labels:
          severity: info
        annotations:
          summary: "High request volume"
          description: "Request rate is {{ $value | humanize }} req/s"
      
      # Slow rate limit checks
      - alert: SlowRateLimitChecks
        expr: |
          histogram_quantile(0.95,
            rate(rate_limit_check_duration_seconds_bucket[5m])
          ) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Slow rate limit checks"
          description: "p95 check duration is {{ $value | humanize }}s"
"""


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    from prometheus_client import start_http_server
    import time
    
    # Setup
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    monitor = RateLimitMonitor(redis)
    
    # Start Prometheus metrics server
    start_http_server(8001)
    print("Metrics available at http://localhost:8001/metrics")
    
    # Simulate some requests
    print("\nSimulating requests...")
    
    for i in range(100):
        allowed = i % 10 != 0  # Block every 10th request
        
        monitor.record_request(
            allowed=allowed,
            endpoint="/api/users",
            method="GET",
            scope="user",
            tier="free",
            reason="rate_limit" if not allowed else None,
            duration=0.001
        )
        
        time.sleep(0.1)
    
    # Get statistics
    print("\n" + "="*60)
    print("STATISTICS")
    print("="*60)
    
    stats = monitor.get_statistics("1h")
    print(f"\nTime Range: {stats['time_range']}")
    print(f"Total Requests: {stats['total']}")
    print(f"Allowed: {stats['allowed']}")
    print(f"Blocked: {stats['blocked']}")
    print(f"Block Rate: {stats['block_rate']:.1f}%")
    
    # Check alerts
    print("\n" + "="*60)
    print("ALERTS")
    print("="*60)
    
    alerts = monitor.check_alerts()
    if alerts:
        for alert in alerts:
            print(f"\n[{alert['severity'].upper()}] {alert['title']}")
            print(f"  {alert['message']}")
    else:
        print("\nNo active alerts")
    
    print("\n" + "="*60)
    print("Prometheus metrics available at http://localhost:8001/metrics")
    print("Press Ctrl+C to stop...")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")
2. Real-Time Dashboard
python# monitoring/dashboard.py

"""
Real-Time Rate Limiting Dashboard

Simple web dashboard for monitoring
"""

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from redis import Redis
import asyncio
import json
from datetime import datetime
from typing import Dict, List

from monitoring.metrics import RateLimitMonitor


class RateLimitDashboard:
    """Real-time rate limiting dashboard"""
    
    def __init__(
        self,
        redis_client: Redis,
        monitor: RateLimitMonitor
    ):
        """
        Initialize dashboard.
        
        Args:
            redis_client: Redis connection
            monitor: Rate limit monitor
        """
        self.redis = redis_client
        self.monitor = monitor
        self.app = self._create_app()
    
    def _create_app(self) -> FastAPI:
        """Create FastAPI application"""
        app = FastAPI(title="Rate Limiting Dashboard")
        
        @app.get("/", response_class=HTMLResponse)
        async def dashboard():
            """Serve dashboard HTML"""
            return self._get_html()
        
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket for real-time updates"""
            await websocket.accept()
            
            try:
                while True:
                    # Get current stats
                    stats = self.monitor.get_statistics("1h")
                    alerts = self.monitor.check_alerts()
                    
                    # Send to client
                    await websocket.send_json({
                        "timestamp": datetime.now().isoformat(),
                        "stats": stats,
                        "alerts": alerts
                    })
                    
                    # Update every second
                    await asyncio.sleep(1)
                    
            except Exception as e:
                print(f"WebSocket error: {e}")
        
        @app.get("/api/stats")
        async def get_stats():
            """Get current statistics"""
            return self.monitor.get_statistics("1h")
        
        @app.get("/api/alerts")
        async def get_alerts():
            """Get active alerts"""
            return self.monitor.check_alerts()
        
        return app
    
    def _get_html(self) -> str:
        """Get dashboard HTML"""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>Rate Limiting Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        h1 {
            margin-bottom: 30px;
            color: #fff;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: #16213e;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #0f3460;
        }
        
        .stat-label {
            font-size: 14px;
            color: #8892b0;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #64ffda;
        }
        
        .stat-subtitle {
            font-size: 12px;
            color: #8892b0;
            margin-top: 4px;
        }
        
        .alerts {
            background: #16213e;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #0f3460;
            margin-bottom: 20px;
        }
        
        .alert {
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 4px;
            border-left: 4px solid;
        }
        
        .alert-critical {
            background: rgba(255, 71, 87, 0.1);
            border-color: #ff4757;
        }
        
        .alert-warning {
            background: rgba(255, 159, 64, 0.1);
            border-color: #ffa502;
        }
        
        .alert-info {
            background: rgba(99, 205, 218, 0.1);
            border-color: #63cdda;
        }
        
        .alert-title {
            font-weight: bold;
            margin-bottom: 4px;
        }
        
        .alert-message {
            font-size: 14px;
            color: #8892b0;
        }
        
        .chart-container {
            background: #16213e;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #0f3460;
            margin-bottom: 20px;
        }
        
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 8px;
        }
        
        .status-ok { background: #2ecc71; }
        .status-warning { background: #ffa502; }
        .status-critical { background: #ff4757; }
        
        .last-update {
            text-align: center;
            color: #8892b0;
            font-size: 12px;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚦 Rate Limiting Dashboard</h1>
        
        <div id="alerts"></div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Requests</div>
                <div class="stat-value" id="total-requests">-</div>
                <div class="stat-subtitle">Last hour</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Allowed</div>
                <div class="stat-value" id="allowed-requests">-</div>
                <div class="stat-subtitle" id="allowed-percent">-</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Blocked</div>
                <div class="stat-value" id="blocked-requests">-</div>
                <div class="stat-subtitle" id="blocked-percent">-</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Block Rate</div>
                <div class="stat-value" id="block-rate">-</div>
                <div class="stat-subtitle">Percentage blocked</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h3>Requests by Scope</h3>
            <div id="scope-stats"></div>
        </div>
        
        <div class="chart-container">
            <h3>Requests by Tier</h3>
            <div id="tier-stats"></div>
        </div>
        
        <div class="last-update">
            Last updated: <span id="last-update">-</span>
        </div>
    </div>
    
    <script>
        const ws = new WebSocket('ws://' + window.location.host + '/ws');
        
        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };
        
        function updateDashboard(data) {
            const stats = data.stats;
            const alerts = data.alerts;
            
            // Update stats
            document.getElementById('total-requests').textContent = 
                stats.total.toLocaleString();
            
            document.getElementById('allowed-requests').textContent = 
                stats.allowed.toLocaleString();
            
            document.getElementById('allowed-percent').textContent = 
                `${((stats.allowed / stats.total) * 100).toFixed(1)}%`;
            
            document.getElementById('blocked-requests').textContent = 
                stats.blocked.toLocaleString();
            
            document.getElementById('blocked-percent').textContent = 
                `${stats.block_rate.toFixed(1)}%`;
            
            document.getElementById('block-rate').textContent = 
                `${stats.block_rate.toFixed(1)}%`;
            
            // Update alerts
            const alertsContainer = document.getElementById('alerts');
            if (alerts.length > 0) {
                alertsContainer.innerHTML = '<div class="alerts">' +
                    alerts.map(alert => `
                        <div class="alert alert-${alert.severity}">
                            <div class="alert-title">
                                <span class="status-indicator status-${alert.severity}"></span>
                                ${alert.title}
                            </div>
                            <div class="alert-message">${alert.message}</div>
                        </div>
                    `).join('') +
                    '</div>';
            } else {
                alertsContainer.innerHTML = '';
            }
            
            // Update scope stats
            const scopeStats = document.getElementById('scope-stats');
            scopeStats.innerHTML = Object.entries(stats.by_scope || {})
                .map(([scope, count]) => `
                    <div style="margin: 10px 0;">
                        ${scope}: ${count.toLocaleString()}
                    </div>
                `).join('');
            
            // Update tier stats
            const tierStats = document.getElementById('tier-stats');
            tierStats.innerHTML = Object.entries(stats.by_tier || {})
                .map(([tier, count]) => `
                    <div style="margin: 10px 0;">
                        ${tier}: ${count.toLocaleString()}
                    </div>
                `).join('');
            
            // Update timestamp
            document.getElementById('last-update').textContent = 
                new Date(data.timestamp).toLocaleTimeString();
        }
    </script>
</body>
</html>
        """


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    import uvicorn
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    monitor = RateLimitMonitor(redis)
    dashboard = RateLimitDashboard(redis, monitor)
    
    print("="*60)
    print("RATE LIMITING DASHBOARD")
    print("="*60)
    print("\nStarting dashboard server...")
    print("Dashboard: http://localhost:8002")
    print("API: http://localhost:8002/api/stats")
    print("\nPress Ctrl+C to stop...")
    print("="*60)
    
    uvicorn.run(dashboard.app, host="0.0.0.0", port=8002)

🔓 BYPASS MECHANISMS (WHITELISTING)
1. Whitelist Management
python# core/rate_limiting/whitelist.py

"""
Whitelist Management

Bypass rate limiting for trusted users/IPs
"""

from typing import List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
from redis import Redis
from loguru import logger


@dataclass
class WhitelistEntry:
    """Whitelist entry"""
    identifier: str
    type: str  # user, ip, api_key
    reason: str
    added_by: str
    added_at: datetime
    expires_at: Optional[datetime] = None


class WhitelistManager:
    """
    Manage rate limiting whitelist.
    
    Features:
    - Multiple identifier types (user, IP, API key)
    - Temporary and permanent entries
    - Audit logging
    - Auto-expiration
    """
    
    def __init__(self, redis_client: Redis):
        """
        Initialize whitelist manager.
        
        Args:
            redis_client: Redis connection
        """
        self.redis = redis_client
        logger.info("Whitelist manager initialized")
    
    def add(
        self,
        identifier: str,
        type: str,
        reason: str,
        added_by: str,
        expires_in: Optional[int] = None
    ) -> WhitelistEntry:
        """
        Add identifier to whitelist.
        
        Args:
            identifier: Identifier to whitelist
            type: Type (user, ip, api_key)
            reason: Reason for whitelisting
            added_by: Who added this entry
            expires_in: Optional expiration in seconds
        
        Returns:
            WhitelistEntry
        """
        now = datetime.now()
        expires_at = now + timedelta(seconds=expires_in) if expires_in else None
        
        entry = WhitelistEntry(
            identifier=identifier,
            type=type,
            reason=reason,
            added_by=added_by,
            added_at=now,
            expires_at=expires_at
        )
        
        # Store in Redis
        key = f"rate_limit:whitelist:{type}:{identifier}"
        
        self.redis.hset(key, mapping={
            "type": type,
            "reason": reason,
            "added_by": added_by,
            "added_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else ""
        })
        
        # Set expiration if specified
        if expires_in:
            self.redis.expire(key, expires_in)
        
        # Add to set for listing
        self.redis.sadd(f"rate_limit:whitelist:{type}:all", identifier)
        
        # Log
        logger.info(
            f"Whitelisted {type} '{identifier}': {reason} "
            f"(by {added_by}, expires: {expires_at or 'never'})"
        )
        
        return entry
    
    def remove(
        self,
        identifier: str,
        type: str
    ) -> bool:
        """
        Remove identifier from whitelist.
        
        Args:
            identifier: Identifier to remove
            type: Type (user, ip, api_key)
        
        Returns:
            True if removed, False if not found
        """
        key = f"rate_limit:whitelist:{type}:{identifier}"
        
        # Check if exists
        if not self.redis.exists(key):
            return False
        
        # Remove
        self.redis.delete(key)
        self.redis.srem(f"rate_limit:whitelist:{type}:all", identifier)
        
        logger.info(f"Removed {type} '{identifier}' from whitelist")
        
        return True
    
    def is_whitelisted(
        self,
        identifier: str,
        type: str
    ) -> bool:
        """
        Check if identifier is whitelisted.
        
        Args:
            identifier: Identifier to check
            type: Type (user, ip, api_key)
        
        Returns:
            True if whitelisted
        """
        key = f"rate_limit:whitelist:{type}:{identifier}"
        return bool(self.redis.exists(key))
    
    def get(
        self,
        identifier: str,
        type: str
    ) -> Optional[WhitelistEntry]:
        """
        Get whitelist entry.
        
        Args:
            identifier: Identifier
            type: Type
        
        Returns:
            WhitelistEntry or None
        """
        key = f"rate_limit:whitelist:{type}:{identifier}"
        data = self.redis.hgetall(key)
        
        if not data:
            return None
        
        # Decode if bytes
        if isinstance(list(data.keys())[0], bytes):
            data = {k.decode(): v.decode() for k, v in data.items()}
        
        return WhitelistEntry(
            identifier=identifier,
            type=data['type'],
            reason=data['reason'],
            added_by=data['added_by'],
            added_at=datetime.fromisoformat(data['added_at']),
            expires_at=datetime.fromisoformat(data['expires_at']) if data['expires_at'] else None
        )
    
    def list(
        self,
        type: Optional[str] = None
    ) -> List[WhitelistEntry]:
        """
        List all whitelist entries.
        
        Args:
            type: Optional type filter
        
        Returns:
            List of WhitelistEntry
        """
        entries = []
        
        types = [type] if type else ['user', 'ip', 'api_key']
        
        for t in types:
            identifiers = self.redis.smembers(f"rate_limit:whitelist:{t}:all")
            
            for identifier in identifiers:
                if isinstance(identifier, bytes):
                    identifier = identifier.decode()
                
                entry = self.get(identifier, t)
                if entry:
                    entries.append(entry)
        
        return entries
    
    def cleanup_expired(self) -> int:
        """
        Clean up expired entries.
        
        Returns:
            Number of entries removed
        """
        removed = 0
        now = datetime.now()
        
        for entry in self.list():
            if entry.expires_at and entry.expires_at < now:
                self.remove(entry.identifier, entry.type)
                removed += 1
        
        if removed > 0:
            logger.info(f"Cleaned up {removed} expired whitelist entries")
        
        return removed


# ============================================
# IP RANGE WHITELISTING
# ============================================

import ipaddress

class IPRangeWhitelist:
    """
    Whitelist IP ranges (CIDR notation).
    
    Useful for:
    - Internal network ranges
    - Office IPs
    - Partner networks
    """
    
    def __init__(self, redis_client: Redis):
        """Initialize IP range whitelist"""
        self.redis = redis_client
        self.ranges: List[ipaddress.IPv4Network] = []
        self._load_ranges()
    
    def _load_ranges(self):
        """Load ranges from Redis"""
        ranges = self.redis.smembers("rate_limit:whitelist:ip_ranges")
        
        self.ranges = []
        for r in ranges:
            if isinstance(r, bytes):
                r = r.decode()
            try:
                self.ranges.append(ipaddress.IPv4Network(r))
            except ValueError:
                logger.warning(f"Invalid IP range: {r}")
    
    def add_range(
        self,
        cidr: str,
        description: str
    ):
        """
        Add IP range.
        
        Args:
            cidr: CIDR notation (e.g., "192.168.1.0/24")
            description: Description of range
        """
        # Validate
        try:
            network = ipaddress.IPv4Network(cidr)
        except ValueError as e:
            raise ValueError(f"Invalid CIDR: {e}")
        
        # Add to Redis
        self.redis.sadd("rate_limit:whitelist:ip_ranges", cidr)
        self.redis.hset(
            "rate_limit:whitelist:ip_ranges:meta",
            cidr,
            description
        )
        
        # Reload
        self._load_ranges()
        
        logger.info(f"Added IP range {cidr}: {description}")
    
    def remove_range(self, cidr: str):
        """Remove IP range"""
        self.redis.srem("rate_limit:whitelist:ip_ranges", cidr)
        self.redis.hdel("rate_limit:whitelist:ip_ranges:meta", cidr)
        
        # Reload
        self._load_ranges()
        
        logger.info(f"Removed IP range {cidr}")
    
    def is_whitelisted(self, ip: str) -> bool:
        """
        Check if IP is in whitelisted range.
        
        Args:
            ip: IP address
        
        Returns:
            True if in whitelisted range
        """
        try:
            ip_addr = ipaddress.IPv4Address(ip)
        except ValueError:
            return False
        
        for network in self.ranges:
            if ip_addr in network:
                return True
        
        return False
    
    def list_ranges(self) -> List[Dict]:
        """List all whitelisted ranges"""
        ranges = []
        
        meta = self.redis.hgetall("rate_limit:whitelist:ip_ranges:meta")
        
        if isinstance(list(meta.keys())[0], bytes):
            meta = {k.decode(): v.decode() for k, v in meta.items()}
        
        for cidr, description in meta.items():
            ranges.append({
                "cidr": cidr,
                "description": description
            })
        
        return ranges


# ============================================
# EXAMPLE USAGE
# ============================================

if __name__ == "__main__":
    from redis import Redis
    
    redis = Redis(host='localhost', port=6379, decode_responses=True)
    
    # Whitelist manager
    whitelist = WhitelistManager(redis)
    
    print("="*60)
    print("WHITELIST MANAGEMENT")
    print("="*60)
    
    # Add entries
    print("\nAdding whitelist entries...")
    
    whitelist.add(
        identifier="admin_user",
        type="user",
        reason="System administrator",
        added_by="system"
    )
    
    whitelist.add(
        identifier="partner_api_key",
        type="api_key",
        reason="Trusted partner integration",
        added_by="admin",
        expires_in=86400  # 24 hours
    )
    
    # Check
    print("\nChecking whitelist...")
    print(f"admin_user whitelisted: {whitelist.is_whitelisted('admin_user', 'user')}")
    print(f"random_user whitelisted: {whitelist.is_whitelisted('random_user', 'user')}")
    
    # List
    print("\n" + "="*60)
    print("CURRENT WHITELIST")
    print("="*60)
    
    for entry in whitelist.list():
        print(f"\n{entry.type}: {entry.identifier}")
        print(f"  Reason: {entry.reason}")
        print(f"  Added by: {entry.added_by}")
        print(f"  Added at: {entry.added_at}")
        print(f"  Expires: {entry.expires_at or 'Never'}")
    
    # IP ranges
    print("\n" + "="*60)
    print("IP RANGE WHITELIST")
    print("="*60)
    
    ip_whitelist = IPRangeWhitelist(redis)
    
    # Add ranges
    ip_whitelist.add_range("192.168.1.0/24", "Office network")
    ip_whitelist.add_range("10.0.0.0/8", "Internal network")
    
    # Check IPs
    test_ips = ["192.168.1.100", "10.5.10.20", "8.8.8.8"]
    
    print("\nTesting IPs:")
    for ip in test_ips:
        whitelisted = ip_whitelist.is_whitelisted(ip)
        print(f"  {ip}: {'✓ Whitelisted' if whitelisted else '✗ Not whitelisted'}")
    
    # List ranges
    print("\nWhitelisted ranges:")
    for range_info in ip_whitelist.list_ranges():
        print(f"  {range_info['cidr']}: {range_info['description']}")

        


