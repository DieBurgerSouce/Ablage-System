# -*- coding: utf-8 -*-
"""
Push Notification Celery Tasks.

Scheduled tasks for push notification management:
- Cleanup expired/failed subscriptions (weekly)
- Subscription health check (daily)
- Push notification statistics (weekly)

Feinpoliert und durchdacht - Enterprise Push Notification Management.
"""

import asyncio
import structlog
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select, delete, func, and_, or_

from app.workers.celery_app import celery_app
from app.db.session import get_async_session_context
from app.db.models import PushSubscription, NotificationHistory
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Maximum consecutive failures before deactivation
MAX_ERROR_COUNT = 5

# Days of inactivity before subscription is considered stale
STALE_SUBSCRIPTION_DAYS = 90

# Days to keep notification history
NOTIFICATION_HISTORY_RETENTION_DAYS = 30


# =============================================================================
# Cleanup Tasks
# =============================================================================


@celery_app.task(
    name="push.cleanup_expired_subscriptions",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def cleanup_expired_push_subscriptions_task(
    self,
    max_error_count: int = MAX_ERROR_COUNT,
    stale_days: int = STALE_SUBSCRIPTION_DAYS,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Cleans up expired and failed push subscriptions.

    Runs weekly on Sunday at 03:00 via Celery Beat.
    Removes subscriptions that:
    - Have exceeded the maximum error count
    - Have been inactive for too long
    - Are explicitly marked as inactive

    Args:
        max_error_count: Maximum errors before removal (default: 5)
        stale_days: Days of inactivity before removal (default: 90)
        dry_run: If True, only count without deleting

    Returns:
        Dict with cleanup statistics
    """
    async def _cleanup_subscriptions() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "total_subscriptions_checked": 0,
                "failed_subscriptions_removed": 0,
                "stale_subscriptions_removed": 0,
                "inactive_subscriptions_removed": 0,
                "total_removed": 0,
                "dry_run": dry_run,
                "cleanup_timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:
                # Count total subscriptions
                total_count = await db.execute(
                    select(func.count(PushSubscription.id))
                )
                stats["total_subscriptions_checked"] = total_count.scalar() or 0

                # Find subscriptions with too many errors
                failed_query = select(PushSubscription.id).where(
                    PushSubscription.error_count >= max_error_count
                )
                failed_result = await db.execute(failed_query)
                failed_ids = [row[0] for row in failed_result.fetchall()]
                stats["failed_subscriptions_removed"] = len(failed_ids)

                # Find stale subscriptions (no activity for stale_days)
                stale_cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
                stale_query = select(PushSubscription.id).where(
                    and_(
                        PushSubscription.is_active == True,
                        or_(
                            PushSubscription.last_used_at.is_(None),
                            PushSubscription.last_used_at < stale_cutoff,
                        ),
                        PushSubscription.created_at < stale_cutoff,
                    )
                )
                stale_result = await db.execute(stale_query)
                stale_ids = [row[0] for row in stale_result.fetchall()]
                # Exclude already counted failed subscriptions
                stale_ids = [sid for sid in stale_ids if sid not in failed_ids]
                stats["stale_subscriptions_removed"] = len(stale_ids)

                # Find explicitly inactive subscriptions
                inactive_query = select(PushSubscription.id).where(
                    PushSubscription.is_active == False
                )
                inactive_result = await db.execute(inactive_query)
                inactive_ids = [row[0] for row in inactive_result.fetchall()]
                # Exclude already counted subscriptions
                inactive_ids = [
                    sid for sid in inactive_ids
                    if sid not in failed_ids and sid not in stale_ids
                ]
                stats["inactive_subscriptions_removed"] = len(inactive_ids)

                # Calculate total
                all_ids_to_remove = set(failed_ids + stale_ids + inactive_ids)
                stats["total_removed"] = len(all_ids_to_remove)

                if not dry_run and all_ids_to_remove:
                    # Delete notification history for these subscriptions first
                    await db.execute(
                        delete(NotificationHistory).where(
                            NotificationHistory.subscription_id.in_(all_ids_to_remove)
                        )
                    )

                    # Delete the subscriptions
                    await db.execute(
                        delete(PushSubscription).where(
                            PushSubscription.id.in_(all_ids_to_remove)
                        )
                    )
                    await db.commit()

                    logger.info(
                        "push_subscriptions_cleaned_up",
                        failed_removed=stats["failed_subscriptions_removed"],
                        stale_removed=stats["stale_subscriptions_removed"],
                        inactive_removed=stats["inactive_subscriptions_removed"],
                        total_removed=stats["total_removed"],
                    )
                else:
                    logger.info(
                        "push_subscriptions_cleanup_dry_run",
                        would_remove=stats["total_removed"],
                    )

            except Exception as e:
                logger.error(
                    "push_subscription_cleanup_error",
                    **safe_error_log(e),
                )
                stats["error"] = safe_error_detail(e, "Cleanup")

            return stats

    try:
        result = asyncio.run(_cleanup_subscriptions())
        logger.info(
            "push_subscription_cleanup_task_completed",
            total_checked=result["total_subscriptions_checked"],
            total_removed=result["total_removed"],
            dry_run=result["dry_run"],
        )
        return result
    except Exception as e:
        logger.error("push_subscription_cleanup_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Health Check Task
# =============================================================================


@celery_app.task(
    name="push.health_check",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def push_subscription_health_check_task(self) -> Dict[str, Any]:
    """
    Performs health check on push subscriptions.

    Runs daily at 06:00 via Celery Beat.
    Generates statistics and identifies problematic subscriptions.

    Returns:
        Dict with health statistics
    """
    async def _health_check() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_subscriptions": 0,
                "active_subscriptions": 0,
                "inactive_subscriptions": 0,
                "subscriptions_with_errors": 0,
                "high_error_subscriptions": 0,
                "subscriptions_by_browser": {},
                "subscriptions_by_device_type": {},
                "avg_error_count": 0.0,
                "health_status": "healthy",
            }

            try:
                # Total subscriptions
                total_result = await db.execute(
                    select(func.count(PushSubscription.id))
                )
                stats["total_subscriptions"] = total_result.scalar() or 0

                if stats["total_subscriptions"] == 0:
                    return stats

                # Active subscriptions
                active_result = await db.execute(
                    select(func.count(PushSubscription.id)).where(
                        PushSubscription.is_active == True
                    )
                )
                stats["active_subscriptions"] = active_result.scalar() or 0
                stats["inactive_subscriptions"] = (
                    stats["total_subscriptions"] - stats["active_subscriptions"]
                )

                # Subscriptions with errors
                error_result = await db.execute(
                    select(func.count(PushSubscription.id)).where(
                        PushSubscription.error_count > 0
                    )
                )
                stats["subscriptions_with_errors"] = error_result.scalar() or 0

                # High error subscriptions (3+ errors)
                high_error_result = await db.execute(
                    select(func.count(PushSubscription.id)).where(
                        PushSubscription.error_count >= 3
                    )
                )
                stats["high_error_subscriptions"] = high_error_result.scalar() or 0

                # Average error count
                avg_result = await db.execute(
                    select(func.avg(PushSubscription.error_count))
                )
                stats["avg_error_count"] = round(float(avg_result.scalar() or 0), 2)

                # Group by browser
                browser_result = await db.execute(
                    select(
                        PushSubscription.browser,
                        func.count(PushSubscription.id)
                    ).group_by(PushSubscription.browser)
                )
                for browser, count in browser_result.fetchall():
                    browser_name = browser or "unknown"
                    stats["subscriptions_by_browser"][browser_name] = count

                # Group by device type
                device_result = await db.execute(
                    select(
                        PushSubscription.device_type,
                        func.count(PushSubscription.id)
                    ).group_by(PushSubscription.device_type)
                )
                for device_type, count in device_result.fetchall():
                    device_name = device_type or "unknown"
                    stats["subscriptions_by_device_type"][device_name] = count

                # Determine health status
                error_rate = (
                    stats["subscriptions_with_errors"] / stats["total_subscriptions"]
                    if stats["total_subscriptions"] > 0
                    else 0
                )
                inactive_rate = (
                    stats["inactive_subscriptions"] / stats["total_subscriptions"]
                    if stats["total_subscriptions"] > 0
                    else 0
                )

                if error_rate > 0.3 or inactive_rate > 0.5:
                    stats["health_status"] = "critical"
                elif error_rate > 0.1 or inactive_rate > 0.3:
                    stats["health_status"] = "warning"
                else:
                    stats["health_status"] = "healthy"

            except Exception as e:
                logger.error(
                    "push_health_check_error",
                    **safe_error_log(e),
                )
                stats["error"] = safe_error_detail(e, "Health check")
                stats["health_status"] = "error"

            return stats

    try:
        result = asyncio.run(_health_check())
        logger.info(
            "push_health_check_completed",
            total=result["total_subscriptions"],
            active=result["active_subscriptions"],
            with_errors=result["subscriptions_with_errors"],
            health_status=result["health_status"],
        )
        return result
    except Exception as e:
        logger.error("push_health_check_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Notification History Cleanup Task
# =============================================================================


@celery_app.task(
    name="push.cleanup_notification_history",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def cleanup_notification_history_task(
    self,
    retention_days: int = NOTIFICATION_HISTORY_RETENTION_DAYS,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Cleans up old notification history records.

    Runs weekly on Sunday at 03:30 via Celery Beat.
    Removes history records older than the retention period.

    Args:
        retention_days: Days to keep notification history (default: 30)
        dry_run: If True, only count without deleting

    Returns:
        Dict with cleanup statistics
    """
    async def _cleanup_history() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "retention_days": retention_days,
                "cutoff_date": None,
                "records_to_delete": 0,
                "records_deleted": 0,
                "dry_run": dry_run,
            }

            try:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
                stats["cutoff_date"] = cutoff_date.isoformat()

                # Count records to delete
                count_result = await db.execute(
                    select(func.count(NotificationHistory.id)).where(
                        NotificationHistory.created_at < cutoff_date
                    )
                )
                stats["records_to_delete"] = count_result.scalar() or 0

                if not dry_run and stats["records_to_delete"] > 0:
                    # Delete old records
                    await db.execute(
                        delete(NotificationHistory).where(
                            NotificationHistory.created_at < cutoff_date
                        )
                    )
                    await db.commit()
                    stats["records_deleted"] = stats["records_to_delete"]

                    logger.info(
                        "notification_history_cleaned_up",
                        records_deleted=stats["records_deleted"],
                        cutoff_date=stats["cutoff_date"],
                    )
                else:
                    logger.info(
                        "notification_history_cleanup_dry_run",
                        would_delete=stats["records_to_delete"],
                    )

            except Exception as e:
                logger.error(
                    "notification_history_cleanup_error",
                    **safe_error_log(e),
                )
                stats["error"] = safe_error_detail(e, "History cleanup")

            return stats

    try:
        result = asyncio.run(_cleanup_history())
        logger.info(
            "notification_history_cleanup_task_completed",
            records_deleted=result.get("records_deleted", 0),
            dry_run=result["dry_run"],
        )
        return result
    except Exception as e:
        logger.error("notification_history_cleanup_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)


# =============================================================================
# Weekly Statistics Task
# =============================================================================


@celery_app.task(
    name="push.generate_weekly_statistics",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
    queue="maintenance",
)
def generate_push_statistics_task(self) -> Dict[str, Any]:
    """
    Generates weekly push notification statistics.

    Runs weekly on Monday at 06:00 via Celery Beat.
    Compiles statistics about push notification delivery and engagement.

    Returns:
        Dict with weekly statistics
    """
    async def _generate_statistics() -> Dict[str, Any]:
        async with get_async_session_context() as db:
            stats = {
                "period_start": None,
                "period_end": None,
                "total_notifications_sent": 0,
                "successful_notifications": 0,
                "failed_notifications": 0,
                "pending_notifications": 0,
                "success_rate": 0.0,
                "unique_users_reached": 0,
                "new_subscriptions": 0,
                "churned_subscriptions": 0,
            }

            try:
                period_end = datetime.now(timezone.utc)
                period_start = period_end - timedelta(days=7)
                stats["period_start"] = period_start.isoformat()
                stats["period_end"] = period_end.isoformat()

                # Total notifications sent in period
                total_result = await db.execute(
                    select(func.count(NotificationHistory.id)).where(
                        NotificationHistory.created_at >= period_start
                    )
                )
                stats["total_notifications_sent"] = total_result.scalar() or 0

                # Successful notifications
                success_result = await db.execute(
                    select(func.count(NotificationHistory.id)).where(
                        and_(
                            NotificationHistory.created_at >= period_start,
                            NotificationHistory.status == "sent",
                        )
                    )
                )
                stats["successful_notifications"] = success_result.scalar() or 0

                # Failed notifications
                failed_result = await db.execute(
                    select(func.count(NotificationHistory.id)).where(
                        and_(
                            NotificationHistory.created_at >= period_start,
                            NotificationHistory.status == "failed",
                        )
                    )
                )
                stats["failed_notifications"] = failed_result.scalar() or 0

                # Pending notifications
                pending_result = await db.execute(
                    select(func.count(NotificationHistory.id)).where(
                        and_(
                            NotificationHistory.created_at >= period_start,
                            NotificationHistory.status == "pending",
                        )
                    )
                )
                stats["pending_notifications"] = pending_result.scalar() or 0

                # Success rate
                if stats["total_notifications_sent"] > 0:
                    stats["success_rate"] = round(
                        (stats["successful_notifications"] / stats["total_notifications_sent"]) * 100,
                        2
                    )

                # Unique users reached
                users_result = await db.execute(
                    select(func.count(func.distinct(PushSubscription.user_id))).where(
                        PushSubscription.last_used_at >= period_start
                    )
                )
                stats["unique_users_reached"] = users_result.scalar() or 0

                # New subscriptions
                new_result = await db.execute(
                    select(func.count(PushSubscription.id)).where(
                        PushSubscription.created_at >= period_start
                    )
                )
                stats["new_subscriptions"] = new_result.scalar() or 0

                # Churned subscriptions (deactivated in period)
                churned_result = await db.execute(
                    select(func.count(PushSubscription.id)).where(
                        and_(
                            PushSubscription.is_active == False,
                            PushSubscription.updated_at >= period_start,
                        )
                    )
                )
                stats["churned_subscriptions"] = churned_result.scalar() or 0

            except Exception as e:
                logger.error(
                    "push_statistics_generation_error",
                    **safe_error_log(e),
                )
                stats["error"] = safe_error_detail(e, "Statistics generation")

            return stats

    try:
        result = asyncio.run(_generate_statistics())
        logger.info(
            "push_statistics_generated",
            total_sent=result["total_notifications_sent"],
            success_rate=result["success_rate"],
            unique_users=result["unique_users_reached"],
            new_subscriptions=result["new_subscriptions"],
        )
        return result
    except Exception as e:
        logger.error("push_statistics_task_failed", **safe_error_log(e))
        raise self.retry(exc=e)
