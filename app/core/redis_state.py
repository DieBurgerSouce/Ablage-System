"""
Redis State Manager for Agent System.

Manages:
- Agent state tracking
- Task progress tracking
- Workflow state persistence
- Event publishing/subscribing
- Result caching
- Metrics counters
"""

import asyncio
import json
import structlog
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

logger = structlog.get_logger(__name__)


class RedisStateManager:
    """
    Async Redis client for state management, caching, and event publishing.

    Singleton pattern - use get_instance() to access.
    """

    _instance: Optional["RedisStateManager"] = None

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis connection."""
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub = None

    @classmethod
    def get_instance(cls) -> "RedisStateManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def connect(self) -> None:
        """Establish Redis connection."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            logger.info("redis_connected", url=self.redis_url.split('@')[-1])

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None
            logger.info("redis_disconnected")

    async def ping(self) -> bool:
        """Check Redis connection."""
        try:
            if self._redis:
                await self._redis.ping()
                return True
            return False
        except Exception as e:
            logger.error("redis_ping_failed", error=str(e))
            return False

    async def _ensure_connection(self) -> None:
        """Ensure Redis connection is established (auto-connect if needed)."""
        if self._redis is None:
            await self.connect()

    # =========================================================================
    # AGENT STATE MANAGEMENT
    # =========================================================================

    async def set_agent_status(
        self, agent_id: str, status: str, metadata: Optional[Dict] = None
    ) -> None:
        """
        Set agent status.

        Args:
            agent_id: Agent identifier
            status: Status (idle, running, success, failed)
            metadata: Optional metadata
        """
        await self._ensure_connection()

        key = f"agent:{agent_id}:status"
        data = {
            "status": status,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        await self._redis.setex(
            key,
            timedelta(hours=24),  # Status expires after 24h
            json.dumps(data),
        )

        logger.debug("agent_status_set", agent_id=agent_id, status=status)

    async def get_agent_status(self, agent_id: str) -> Optional[Dict]:
        """Get agent status."""
        await self._ensure_connection()

        key = f"agent:{agent_id}:status"
        data = await self._redis.get(key)

        if data:
            return json.loads(data)
        return None

    async def get_all_agents_status(self) -> List[Dict]:
        """Get status of all agents."""
        await self._ensure_connection()

        keys = await self._redis.keys("agent:*:status")
        statuses = []

        for key in keys:
            data = await self._redis.get(key)
            if data:
                agent_id = key.split(":")[1]
                status_data = json.loads(data)
                statuses.append({"agent_id": agent_id, **status_data})

        return statuses

    # =========================================================================
    # TASK STATE TRACKING
    # =========================================================================

    async def set_task_state(
        self, task_id: str, state: str, data: Optional[Dict] = None
    ) -> None:
        """
        Set task state.

        Args:
            task_id: Celery task ID
            state: State (pending, running, success, failed)
            data: Task data
        """
        await self._ensure_connection()

        key = f"task:{task_id}"
        task_data = {
            "state": state,
            "updated_at": datetime.utcnow().isoformat(),
            "data": data or {},
        }

        await self._redis.setex(
            key,
            timedelta(hours=72),  # Task state expires after 72h
            json.dumps(task_data),
        )

    async def get_task_state(self, task_id: str) -> Optional[Dict]:
        """Get task state."""
        await self._ensure_connection()

        key = f"task:{task_id}"
        data = await self._redis.get(key)

        if data:
            return json.loads(data)
        return None

    async def track_task_progress(
        self, task_id: str, progress: float, message: Optional[str] = None
    ) -> None:
        """
        Track task progress (0.0 to 1.0).

        Args:
            task_id: Task ID
            progress: Progress percentage (0.0-1.0)
            message: Optional status message
        """
        await self._ensure_connection()

        key = f"task:{task_id}:progress"
        data = {
            "progress": min(1.0, max(0.0, progress)),
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self._redis.setex(key, timedelta(hours=1), json.dumps(data))

    async def get_task_progress(self, task_id: str) -> Optional[Dict]:
        """Get task progress."""
        await self._ensure_connection()

        key = f"task:{task_id}:progress"
        data = await self._redis.get(key)

        if data:
            return json.loads(data)
        return None

    # =========================================================================
    # WORKFLOW STATE PERSISTENCE
    # =========================================================================

    async def set_workflow_state(
        self, document_id: str, phase: str, state_data: Dict
    ) -> None:
        """
        Set workflow phase state.

        Args:
            document_id: Document ID
            phase: Workflow phase (classification, preprocessing, ocr, etc.)
            state_data: Phase state data
        """
        await self._ensure_connection()

        key = f"workflow:{document_id}"
        field = phase

        await self._redis.hset(key, field, json.dumps(state_data))
        await self._redis.expire(key, timedelta(days=7))  # 7 days retention

    async def get_workflow_state(self, document_id: str) -> Optional[Dict]:
        """Get complete workflow state."""
        await self._ensure_connection()

        key = f"workflow:{document_id}"
        data = await self._redis.hgetall(key)

        if data:
            return {phase: json.loads(state) for phase, state in data.items()}
        return None

    async def get_workflow_phase(
        self, document_id: str, phase: str
    ) -> Optional[Dict]:
        """Get specific workflow phase state."""
        key = f"workflow:{document_id}"
        data = await self._redis.hget(key, phase)

        if data:
            return json.loads(data)
        return None

    # =========================================================================
    # EVENT PUBLISHING/SUBSCRIBING
    # =========================================================================

    async def publish_event(
        self, event_type: str, data: Dict, channel: str = "events"
    ) -> int:
        """
        Publish event to Redis pub/sub.

        Args:
            event_type: Event type (document.uploaded, ocr.completed, etc.)
            data: Event data
            channel: Channel name

        Returns:
            Number of subscribers who received the message
        """
        await self._ensure_connection()

        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": data,
        }

        subscribers = await self._redis.publish(channel, json.dumps(event))

        logger.debug(
            "event_published", event_type=event_type, channel=channel, subscribers=subscribers
        )

        return subscribers

    async def subscribe_to_events(
        self, patterns: List[str], callback: callable
    ) -> None:
        """
        Subscribe to event patterns.

        Args:
            patterns: List of channel patterns (e.g., ['events', 'ocr.*'])
            callback: Async callback function(channel, message)
        """
        if not self._pubsub:
            self._pubsub = self._redis.pubsub()

        # Subscribe to patterns
        for pattern in patterns:
            await self._pubsub.psubscribe(pattern)

        logger.info("subscribed_to_events", patterns=patterns)

        # Listen for messages
        async for message in self._pubsub.listen():
            if message["type"] == "pmessage":
                channel = message["channel"]
                data = json.loads(message["data"])
                await callback(channel, data)

    # =========================================================================
    # RESULT CACHING
    # =========================================================================

    async def cache_result(
        self, key: str, value: Dict, ttl: int = 3600
    ) -> None:
        """
        Cache result.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        cache_key = f"cache:{key}"
        await self._redis.setex(cache_key, timedelta(seconds=ttl), json.dumps(value))

    async def get_cached_result(self, key: str) -> Optional[Dict]:
        """Get cached result."""
        cache_key = f"cache:{key}"
        data = await self._redis.get(cache_key)

        if data:
            return json.loads(data)
        return None

    async def invalidate_cache(self, pattern: str) -> int:
        """
        Invalidate cache entries matching pattern.

        Args:
            pattern: Pattern to match (e.g., 'cache:document:*')

        Returns:
            Number of keys deleted
        """
        keys = await self._redis.keys(f"cache:{pattern}")
        if keys:
            return await self._redis.delete(*keys)
        return 0

    # =========================================================================
    # METRICS COUNTERS
    # =========================================================================

    async def increment_counter(
        self, metric_key: str, amount: int = 1, ttl: Optional[int] = None
    ) -> int:
        """
        Increment counter metric.

        Args:
            metric_key: Metric key (e.g., 'ocr.documents_processed')
            amount: Increment amount
            ttl: Optional TTL in seconds

        Returns:
            New counter value
        """
        key = f"metric:{metric_key}"
        new_value = await self._redis.incrby(key, amount)

        if ttl:
            await self._redis.expire(key, timedelta(seconds=ttl))

        return new_value

    async def get_counter(self, metric_key: str) -> int:
        """Get counter value."""
        key = f"metric:{metric_key}"
        value = await self._redis.get(key)
        return int(value) if value else 0

    async def reset_counter(self, metric_key: str) -> None:
        """Reset counter to 0."""
        key = f"metric:{metric_key}"
        await self._redis.set(key, 0)

    # =========================================================================
    # DISTRIBUTED LOCKS
    # =========================================================================

    async def acquire_lock(
        self, lock_key: str, timeout: int = 60, blocking: bool = True
    ) -> bool:
        """
        Acquire distributed lock.

        Args:
            lock_key: Lock key
            timeout: Lock timeout in seconds
            blocking: Wait for lock if True

        Returns:
            True if lock acquired
        """
        await self._ensure_connection()

        key = f"lock:{lock_key}"

        if blocking:
            # Wait for lock
            while True:
                acquired = await self._redis.setnx(key, "1")
                if acquired:
                    await self._redis.expire(key, timedelta(seconds=timeout))
                    return True
                await asyncio.sleep(0.1)
        else:
            # Try once
            acquired = await self._redis.setnx(key, "1")
            if acquired:
                await self._redis.expire(key, timedelta(seconds=timeout))
            return acquired

    async def release_lock(self, lock_key: str) -> None:
        """Release distributed lock."""
        key = f"lock:{lock_key}"
        await self._redis.delete(key)


# =============================================================================
# CONTEXT MANAGER
# =============================================================================


class RedisContext:
    """Context manager for Redis connections."""

    def __init__(self, redis_url: Optional[str] = None):
        self.manager = RedisStateManager(redis_url)

    async def __aenter__(self) -> RedisStateManager:
        await self.manager.connect()
        return self.manager

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.manager.disconnect()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


async def get_redis() -> RedisStateManager:
    """Get Redis state manager instance."""
    manager = RedisStateManager.get_instance()
    await manager.connect()
    return manager
