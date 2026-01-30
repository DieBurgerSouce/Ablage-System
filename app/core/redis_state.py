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
import atexit
import json
import structlog
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


# MEMORY FIX: Cleanup-Handler um Connection Pool Leaks zu verhindern
_cleanup_registered = False


def _sync_cleanup():
    """Synchroner Cleanup für atexit Handler."""
    try:
        manager = RedisStateManager._instance
        if manager and manager._redis:
            # Erstelle temporären Event-Loop für Cleanup
            asyncio.run(manager.disconnect())
            logger.info("redis_atexit_cleanup_completed")
    except Exception as e:
        # Fehler beim Cleanup nicht propagieren
        logger.warning("redis_atexit_cleanup_failed", **safe_error_log(e))


class RedisStateManager:
    """
    Async Redis client for state management, caching, and event publishing.

    Singleton pattern - use get_instance() to access.
    """

    _instance: Optional["RedisStateManager"] = None

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis connection using centralized settings."""
        # Use settings-based URL if not explicitly provided
        if redis_url:
            self.redis_url = redis_url
        elif settings.REDIS_URL:
            self.redis_url = settings.REDIS_URL
        else:
            # Build URL from settings
            password_part = f":{settings.REDIS_PASSWORD.get_secret_value()}@" if settings.REDIS_PASSWORD else ""
            self.redis_url = f"redis://{password_part}{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"

        self._redis: Optional[aioredis.Redis] = None
        self._pubsub = None

    @classmethod
    def get_instance(cls) -> "RedisStateManager":
        """Get singleton instance."""
        global _cleanup_registered
        if cls._instance is None:
            cls._instance = cls()
            # MEMORY FIX: Registriere Cleanup-Handler beim ersten Instance-Erstellen
            if not _cleanup_registered:
                atexit.register(_sync_cleanup)
                _cleanup_registered = True
                logger.debug("redis_atexit_handler_registered")
        return cls._instance

    async def connect(self) -> None:
        """Establish Redis connection using centralized pool settings."""
        if self._redis is None:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.REDIS_POOL_MAX_SIZE,
                socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_keepalive=settings.REDIS_SOCKET_KEEPALIVE,
                health_check_interval=settings.REDIS_HEALTH_CHECK_INTERVAL,
            )
            logger.info(
                "redis_connected",
                url=self.redis_url.split('@')[-1],
                max_connections=settings.REDIS_POOL_MAX_SIZE,
            )

    async def disconnect(self) -> None:
        """Close Redis connection and cleanup subscriptions."""
        # Cleanup pubsub first
        await self.unsubscribe_all()

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
            logger.error("redis_ping_failed", **safe_error_log(e))
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "updated_at": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        subscribers = await self._redis.publish(channel, json.dumps(event))

        logger.debug(
            "event_published", event_type=event_type, channel=channel, subscribers=subscribers
        )

        return subscribers

    async def subscribe_to_events(
        self, patterns: List[str], callback: callable,
        stop_event: Optional[asyncio.Event] = None
    ) -> None:
        """
        Subscribe to event patterns with cleanup support.

        Args:
            patterns: List of channel patterns (e.g., ['events', 'ocr.*'])
            callback: Async callback function(channel, message)
            stop_event: Optional event to signal subscription stop
        """
        await self._ensure_connection()

        pubsub = None
        try:
            pubsub = self._redis.pubsub()

            # Subscribe to patterns
            for pattern in patterns:
                await pubsub.psubscribe(pattern)

            logger.info("subscribed_to_events", patterns=patterns)

            # Listen for messages with stop support
            while True:
                if stop_event and stop_event.is_set():
                    logger.info("subscription_stop_requested", patterns=patterns)
                    break

                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0  # Check stop_event every second
                )

                if message and message["type"] == "pmessage":
                    channel = message["channel"]
                    try:
                        data = json.loads(message["data"])
                        await callback(channel, data)
                    except json.JSONDecodeError as e:
                        logger.error(
                            "event_parse_error",
                            channel=channel,
                            **safe_error_log(e)
                        )
                    except Exception as e:
                        logger.error(
                            "event_callback_error",
                            channel=channel,
                            **safe_error_log(e)
                        )
        finally:
            if pubsub:
                try:
                    await pubsub.punsubscribe()
                    await pubsub.close()
                    logger.info("pubsub_closed", patterns=patterns)
                except Exception as e:
                    logger.warning("pubsub_cleanup_error", **safe_error_log(e))

    async def unsubscribe_all(self) -> None:
        """Cleanup all pubsub subscriptions."""
        if self._pubsub:
            try:
                await self._pubsub.punsubscribe()
                await self._pubsub.close()
                logger.info("all_pubsub_unsubscribed")
            except Exception as e:
                logger.warning("pubsub_cleanup_error", **safe_error_log(e))
            finally:
                self._pubsub = None

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

    async def invalidate_cache(self, pattern: str, batch_size: int = 100) -> int:
        """
        Invalidate cache entries matching pattern using SCAN (non-blocking).

        Args:
            pattern: Pattern to match (e.g., 'document:*')
            batch_size: Number of keys to process per iteration

        Returns:
            Number of keys deleted
        """
        await self._ensure_connection()

        full_pattern = f"cache:{pattern}"
        deleted_count = 0
        cursor = "0"

        try:
            while True:
                # SCAN is non-blocking and cursor-based (unlike KEYS which blocks)
                cursor, keys = await self._redis.scan(
                    cursor=cursor,
                    match=full_pattern,
                    count=batch_size
                )

                if keys:
                    deleted = await self._redis.delete(*keys)
                    deleted_count += deleted
                    logger.debug(
                        "cache_batch_deleted",
                        pattern=full_pattern,
                        batch_deleted=deleted
                    )

                # cursor returns to "0" when iteration is complete
                if cursor == "0":
                    break

        except Exception as e:
            logger.error(
                "cache_invalidation_error",
                pattern=full_pattern,
                **safe_error_log(e)
            )
            raise

        if deleted_count > 0:
            logger.info(
                "cache_invalidated",
                pattern=full_pattern,
                total_deleted=deleted_count
            )

        return deleted_count

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
    # QUEUE LENGTH MONITORING
    # =========================================================================

    async def get_queue_lengths(
        self, queue_names: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        Get Celery queue lengths for load balancing.

        Args:
            queue_names: Optional list of queue names to check.
                        Defaults to OCR-related queues.

        Returns:
            Dictionary mapping queue name to length
        """
        await self._ensure_connection()

        # Default Celery queues used in Ablage-System
        if queue_names is None:
            queue_names = [
                "ocr_high",
                "ocr_normal",
                "embedding_high",
                "embedding_normal",
                "celery",  # Default queue
            ]

        lengths = {}
        for queue_name in queue_names:
            try:
                # Celery uses Redis lists for queues
                length = await self._redis.llen(queue_name)
                lengths[queue_name] = length
            except Exception as e:
                logger.warning(
                    "queue_length_check_failed",
                    queue=queue_name,
                    **safe_error_log(e)
                )
                lengths[queue_name] = 0

        return lengths

    async def get_total_queue_length(self) -> int:
        """Get total length of all OCR queues."""
        lengths = await self.get_queue_lengths()
        return sum(lengths.values())

    # =========================================================================
    # HUMAN REVIEW QUEUE
    # =========================================================================

    async def add_to_review_queue(
        self,
        document_id: str,
        qa_score: float,
        reasons: List[str],
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add document to human review queue.

        Uses Redis sorted set for priority ordering (lower score = higher priority).
        Stores document_id as member (efficient) and data in separate hash.

        Args:
            document_id: Document ID
            qa_score: QA score (lower = higher priority)
            reasons: List of reasons for review
            metadata: Optional additional metadata
        """
        await self._ensure_connection()

        # Store data in separate hash for efficient lookups
        data_key = f"review_item:{document_id}"
        review_data = {
            "document_id": document_id,
            "qa_score": str(qa_score),
            "reasons": json.dumps(reasons),
            "metadata": json.dumps(metadata or {}),
            "added_at": datetime.now(timezone.utc).isoformat(),
        }

        # Use pipeline for atomicity
        pipe = self._redis.pipeline()
        pipe.hset(data_key, mapping=review_data)
        pipe.expire(data_key, timedelta(days=30))  # Auto-cleanup after 30 days
        pipe.zadd("human_review_queue", {document_id: qa_score})
        await pipe.execute()

        # Publish event for notification systems
        await self.publish_event(
            event_type="document.needs_review",
            data={
                "document_id": document_id,
                "qa_score": qa_score,
                "reasons": reasons,
                "metadata": metadata or {},
            },
            channel="review_events"
        )

        logger.info(
            "document_added_to_review_queue",
            document_id=document_id,
            qa_score=qa_score,
            reasons=reasons
        )

    async def get_review_queue(
        self, limit: int = 50
    ) -> List[Dict]:
        """
        Get documents from review queue (highest priority first).

        Args:
            limit: Maximum number of items to return

        Returns:
            List of review items ordered by priority
        """
        await self._ensure_connection()

        # Get document IDs with scores (lowest scores = highest priority)
        items = await self._redis.zrange(
            "human_review_queue",
            0,
            limit - 1,
            withscores=True
        )

        result = []
        for doc_id, score in items:
            # Fetch data from hash
            data_key = f"review_item:{doc_id}"
            data = await self._redis.hgetall(data_key)

            if data:
                result.append({
                    "document_id": data.get("document_id", doc_id),
                    "qa_score": float(data.get("qa_score", score)),
                    "reasons": json.loads(data.get("reasons", "[]")),
                    "metadata": json.loads(data.get("metadata", "{}")),
                    "added_at": data.get("added_at"),
                    "priority_score": score
                })
            else:
                # Data expired or missing, still return basic info
                result.append({
                    "document_id": doc_id,
                    "qa_score": score,
                    "reasons": [],
                    "metadata": {},
                    "added_at": None,
                    "priority_score": score
                })

        return result

    async def remove_from_review_queue(self, document_id: str) -> bool:
        """
        Remove document from review queue.

        Args:
            document_id: Document ID to remove

        Returns:
            True if removed, False if not found
        """
        await self._ensure_connection()

        # Use pipeline for atomicity
        pipe = self._redis.pipeline()
        pipe.zrem("human_review_queue", document_id)
        pipe.delete(f"review_item:{document_id}")
        results = await pipe.execute()

        removed = results[0] > 0
        if removed:
            logger.info(
                "document_removed_from_review_queue",
                document_id=document_id
            )

        return removed

    async def get_review_queue_length(self) -> int:
        """Get number of documents in review queue."""
        await self._ensure_connection()
        return await self._redis.zcard("human_review_queue")

    # =========================================================================
    # DISTRIBUTED LOCKS
    # =========================================================================

    async def acquire_lock(
        self, lock_key: str, timeout: int = 60, blocking: bool = True,
        max_wait: Optional[float] = None
    ) -> bool:
        """
        Acquire distributed lock.

        Args:
            lock_key: Lock key
            timeout: Lock timeout in seconds
            blocking: Wait for lock if True
            max_wait: Maximum wait time in seconds (default: 2x timeout)

        Returns:
            True if lock acquired, False if timeout/unavailable
        """
        await self._ensure_connection()

        key = f"lock:{lock_key}"

        if max_wait is None:
            max_wait = timeout * 2  # Default: 2x the lock timeout

        if blocking:
            # Wait for lock with timeout
            start_time = asyncio.get_event_loop().time()
            attempt = 0

            while True:
                acquired = await self._redis.setnx(key, "1")
                if acquired:
                    await self._redis.expire(key, timedelta(seconds=timeout))
                    logger.debug(
                        "lock_acquired",
                        lock_key=lock_key,
                        attempts=attempt + 1
                    )
                    return True

                # Check if max_wait exceeded
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= max_wait:
                    logger.warning(
                        "lock_acquisition_timeout",
                        lock_key=lock_key,
                        elapsed_seconds=elapsed,
                        attempts=attempt
                    )
                    return False

                # Exponential backoff with jitter (cap at 1 second)
                delay = min(0.1 * (1.5 ** min(attempt, 10)), 1.0)
                await asyncio.sleep(delay)
                attempt += 1
        else:
            # Try once (non-blocking)
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
