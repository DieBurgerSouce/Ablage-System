"""
Partial Results Handler.

Manages saving and resuming partial processing results.
Enables recovery from failures during multi-page document processing.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog

from app.core.redis_state import RedisStateManager
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class PartialResultStatus(str, Enum):
    """Status of partial result."""

    INCOMPLETE = "incomplete"
    COMPLETE = "complete"
    FAILED = "failed"
    RESUMING = "resuming"


@dataclass
class PartialResultItem:
    """Individual item in partial result."""

    item_id: str
    status: str  # "success", "failed", "pending"
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processed_at: Optional[str] = None


@dataclass
class PartialResult:
    """Container for partial processing results."""

    document_id: str
    phase: str
    status: PartialResultStatus
    total_items: int
    successful_items: List[PartialResultItem] = field(default_factory=list)
    failed_items: List[PartialResultItem] = field(default_factory=list)
    pending_items: List[PartialResultItem] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def progress_percent(self) -> float:
        """Calculate processing progress."""
        if self.total_items == 0:
            return 0.0
        processed = len(self.successful_items) + len(self.failed_items)
        return (processed / self.total_items) * 100

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        processed = len(self.successful_items) + len(self.failed_items)
        if processed == 0:
            return 0.0
        return (len(self.successful_items) / processed) * 100

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "document_id": self.document_id,
            "phase": self.phase,
            "status": self.status.value,
            "total_items": self.total_items,
            "successful_items": [
                {
                    "item_id": item.item_id,
                    "status": item.status,
                    "result": item.result,
                    "processed_at": item.processed_at,
                }
                for item in self.successful_items
            ],
            "failed_items": [
                {
                    "item_id": item.item_id,
                    "status": item.status,
                    "error": item.error,
                    "processed_at": item.processed_at,
                }
                for item in self.failed_items
            ],
            "pending_items": [
                {"item_id": item.item_id, "status": item.status}
                for item in self.pending_items
            ],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "progress_percent": round(self.progress_percent, 1),
            "success_rate": round(self.success_rate, 1),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PartialResult":
        """Create from dictionary."""
        return cls(
            document_id=data["document_id"],
            phase=data["phase"],
            status=PartialResultStatus(data["status"]),
            total_items=data["total_items"],
            successful_items=[
                PartialResultItem(
                    item_id=item["item_id"],
                    status=item["status"],
                    result=item.get("result"),
                    processed_at=item.get("processed_at"),
                )
                for item in data.get("successful_items", [])
            ],
            failed_items=[
                PartialResultItem(
                    item_id=item["item_id"],
                    status=item["status"],
                    error=item.get("error"),
                    processed_at=item.get("processed_at"),
                )
                for item in data.get("failed_items", [])
            ],
            pending_items=[
                PartialResultItem(
                    item_id=item["item_id"],
                    status=item["status"],
                )
                for item in data.get("pending_items", [])
            ],
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
        )


class PartialResultHandler:
    """
    Handler for saving and resuming partial processing results.

    Usage:
        handler = PartialResultHandler(redis_manager)

        # Save partial results
        await handler.save_partial_result(
            document_id="doc123",
            phase="ocr",
            successful_items=[...],
            failed_items=[...],
            pending_items=[...],
        )

        # Check if partial results exist
        if await handler.has_partial_result("doc123", "ocr"):
            result = await handler.get_partial_result("doc123", "ocr")
            pending = result.pending_items
    """

    # Redis key prefix for partial results
    KEY_PREFIX = "partial_result"

    # TTL for partial results (7 days)
    TTL_SECONDS = 7 * 24 * 60 * 60

    def __init__(self, redis_manager: Optional[RedisStateManager] = None):
        """
        Initialize partial result handler.

        Args:
            redis_manager: Redis state manager (uses singleton if not provided)
        """
        self._redis = redis_manager

    async def _get_redis(self) -> RedisStateManager:
        """Get Redis manager, connecting if needed."""
        if self._redis is None:
            self._redis = RedisStateManager.get_instance()
        await self._redis._ensure_connection()
        return self._redis

    def _make_key(self, document_id: str, phase: str) -> str:
        """Create Redis key for partial result."""
        return f"{self.KEY_PREFIX}:{document_id}:{phase}"

    async def save_partial_result(
        self,
        document_id: str,
        phase: str,
        total_items: int,
        successful_items: Optional[List[Dict[str, Any]]] = None,
        failed_items: Optional[List[Dict[str, Any]]] = None,
        pending_items: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PartialResult:
        """
        Save partial processing result.

        Args:
            document_id: Document identifier
            phase: Processing phase
            total_items: Total number of items to process
            successful_items: Successfully processed items
            failed_items: Failed items with errors
            pending_items: Items not yet processed
            metadata: Additional metadata

        Returns:
            PartialResult object
        """
        redis = await self._get_redis()

        # Determine status
        processed = len(successful_items or []) + len(failed_items or [])
        if processed >= total_items:
            status = PartialResultStatus.COMPLETE
        elif len(failed_items or []) > 0:
            status = PartialResultStatus.INCOMPLETE
        else:
            status = PartialResultStatus.INCOMPLETE

        # Create partial result
        result = PartialResult(
            document_id=document_id,
            phase=phase,
            status=status,
            total_items=total_items,
            successful_items=[
                PartialResultItem(
                    item_id=item.get("item_id", str(i)),
                    status="success",
                    result=item.get("result"),
                    processed_at=datetime.now(timezone.utc).isoformat(),
                )
                for i, item in enumerate(successful_items or [])
            ],
            failed_items=[
                PartialResultItem(
                    item_id=item.get("item_id", str(i)),
                    status="failed",
                    error=item.get("error"),
                    processed_at=datetime.now(timezone.utc).isoformat(),
                )
                for i, item in enumerate(failed_items or [])
            ],
            pending_items=[
                PartialResultItem(
                    item_id=item.get("item_id", str(i)),
                    status="pending",
                )
                for i, item in enumerate(pending_items or [])
            ],
            metadata=metadata or {},
        )

        # Save to Redis
        key = self._make_key(document_id, phase)
        await redis._redis.setex(
            key,
            self.TTL_SECONDS,
            json.dumps(result.to_dict()),
        )

        logger.info(
            "partial_result_saved",
            document_id=document_id,
            phase=phase,
            total=total_items,
            successful=len(result.successful_items),
            failed=len(result.failed_items),
            pending=len(result.pending_items),
            progress=round(result.progress_percent, 1),
        )

        return result

    async def update_partial_result(
        self,
        document_id: str,
        phase: str,
        item_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[PartialResult]:
        """
        Update a single item in partial result.

        Args:
            document_id: Document identifier
            phase: Processing phase
            item_id: Item identifier
            status: New status ("success" or "failed")
            result: Result data if successful
            error: Error message if failed

        Returns:
            Updated PartialResult or None if not found
        """
        current = await self.get_partial_result(document_id, phase)
        if not current:
            return None

        # Find and update item
        now = datetime.now(timezone.utc).isoformat()

        # Remove from pending
        current.pending_items = [
            item for item in current.pending_items
            if item.item_id != item_id
        ]

        # Add to appropriate list
        if status == "success":
            current.successful_items.append(
                PartialResultItem(
                    item_id=item_id,
                    status="success",
                    result=result,
                    processed_at=now,
                )
            )
        else:
            current.failed_items.append(
                PartialResultItem(
                    item_id=item_id,
                    status="failed",
                    error=error,
                    processed_at=now,
                )
            )

        # Update timestamp and status
        current.updated_at = now
        processed = len(current.successful_items) + len(current.failed_items)
        if processed >= current.total_items:
            current.status = PartialResultStatus.COMPLETE
        else:
            current.status = PartialResultStatus.INCOMPLETE

        # Save updated result
        redis = await self._get_redis()
        key = self._make_key(document_id, phase)
        await redis._redis.setex(
            key,
            self.TTL_SECONDS,
            json.dumps(current.to_dict()),
        )

        return current

    async def get_partial_result(
        self,
        document_id: str,
        phase: str,
    ) -> Optional[PartialResult]:
        """
        Get partial result for document and phase.

        Args:
            document_id: Document identifier
            phase: Processing phase

        Returns:
            PartialResult or None if not found
        """
        redis = await self._get_redis()
        key = self._make_key(document_id, phase)

        data = await redis._redis.get(key)
        if not data:
            return None

        try:
            return PartialResult.from_dict(json.loads(data))
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(
                "partial_result_parse_error",
                document_id=document_id,
                phase=phase,
                **safe_error_log(e),
            )
            return None

    async def has_partial_result(
        self,
        document_id: str,
        phase: str,
    ) -> bool:
        """Check if partial result exists."""
        redis = await self._get_redis()
        key = self._make_key(document_id, phase)
        return await redis._redis.exists(key) > 0

    async def get_pending_items(
        self,
        document_id: str,
        phase: str,
    ) -> Tuple[List[str], Optional[PartialResult]]:
        """
        Get pending item IDs for resumption.

        Args:
            document_id: Document identifier
            phase: Processing phase

        Returns:
            Tuple of (pending_item_ids, partial_result)
        """
        result = await self.get_partial_result(document_id, phase)
        if not result:
            return [], None

        pending_ids = [item.item_id for item in result.pending_items]
        return pending_ids, result

    async def resume_from_partial(
        self,
        document_id: str,
        phase: str,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[PartialResult]]:
        """
        Get data needed to resume processing.

        Args:
            document_id: Document identifier
            phase: Processing phase

        Returns:
            Tuple of (already_processed_results, pending_items, partial_result)
        """
        result = await self.get_partial_result(document_id, phase)
        if not result:
            return [], [], None

        # Update status to resuming
        result.status = PartialResultStatus.RESUMING
        result.updated_at = datetime.now(timezone.utc).isoformat()

        redis = await self._get_redis()
        key = self._make_key(document_id, phase)
        await redis._redis.setex(
            key,
            self.TTL_SECONDS,
            json.dumps(result.to_dict()),
        )

        # Collect already processed results
        processed_results = [
            {
                "item_id": item.item_id,
                "result": item.result,
            }
            for item in result.successful_items
        ]

        # Collect pending items
        pending = [
            {"item_id": item.item_id}
            for item in result.pending_items
        ]

        logger.info(
            "resuming_from_partial",
            document_id=document_id,
            phase=phase,
            already_processed=len(processed_results),
            pending=len(pending),
        )

        return processed_results, pending, result

    async def delete_partial_result(
        self,
        document_id: str,
        phase: str,
    ) -> bool:
        """
        Delete partial result.

        Args:
            document_id: Document identifier
            phase: Processing phase

        Returns:
            True if deleted
        """
        redis = await self._get_redis()
        key = self._make_key(document_id, phase)
        deleted = await redis._redis.delete(key)

        if deleted:
            logger.info(
                "partial_result_deleted",
                document_id=document_id,
                phase=phase,
            )

        return deleted > 0

    async def delete_all_for_document(
        self,
        document_id: str,
    ) -> int:
        """
        Delete all partial results for a document.

        Args:
            document_id: Document identifier

        Returns:
            Number of deleted keys
        """
        redis = await self._get_redis()
        pattern = f"{self.KEY_PREFIX}:{document_id}:*"
        keys = await redis._redis.keys(pattern)

        if keys:
            deleted = await redis._redis.delete(*keys)
            logger.info(
                "partial_results_deleted",
                document_id=document_id,
                count=deleted,
            )
            return deleted

        return 0


# Global instance
_global_handler: Optional[PartialResultHandler] = None


def get_partial_result_handler() -> PartialResultHandler:
    """Get global partial result handler instance."""
    global _global_handler
    if _global_handler is None:
        _global_handler = PartialResultHandler()
    return _global_handler
