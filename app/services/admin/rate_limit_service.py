"""Rate Limit Management Service.

Provides rate limit operations for the admin console:
- View effective rate limits for users
- Create/update/delete rate limit overrides
- View usage statistics
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
import math

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
import structlog
import redis.asyncio as redis

from app.db.models import User, RateLimitOverride, AdminAction
from app.db.schemas import (
    RateLimitOverrideCreate,
    RateLimitOverrideResponse,
    RateLimitStatus,
    RateLimitUsageStats,
    RateLimitTierDefaults,
    UserTier,
)
from app.core.config import settings

logger = structlog.get_logger(__name__)


class RateLimitService:
    """Service for rate limit management."""

    # Default rate limits by tier
    TIER_DEFAULTS = {
        UserTier.FREE: RateLimitTierDefaults(
            tier=UserTier.FREE,
            ocr_hourly=10,
            ocr_daily=50,
            batch_hourly=5,
            api_per_minute=20,
        ),
        UserTier.PREMIUM: RateLimitTierDefaults(
            tier=UserTier.PREMIUM,
            ocr_hourly=100,
            ocr_daily=1000,
            batch_hourly=50,
            api_per_minute=100,
        ),
        UserTier.ADMIN: RateLimitTierDefaults(
            tier=UserTier.ADMIN,
            ocr_hourly=10000,
            ocr_daily=100000,
            batch_hourly=1000,
            api_per_minute=1000,
        ),
    }

    @staticmethod
    def get_tier_defaults(tier: str) -> RateLimitTierDefaults:
        """Get default rate limits for a tier.

        Args:
            tier: Tier name

        Returns:
            Tier defaults
        """
        try:
            tier_enum = UserTier(tier)
        except ValueError:
            tier_enum = UserTier.FREE

        return RateLimitService.TIER_DEFAULTS.get(
            tier_enum, RateLimitService.TIER_DEFAULTS[UserTier.FREE]
        )

    @staticmethod
    async def get_user_rate_limit_status(
        db: AsyncSession,
        user_id: UUID,
    ) -> Optional[RateLimitStatus]:
        """Get current rate limit status for a user.

        Args:
            db: Database session
            user_id: User UUID

        Returns:
            Rate limit status or None if user not found
        """
        # Get user with override
        result = await db.execute(
            select(User)
            .where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Get active override
        now = datetime.utcnow()
        override_result = await db.execute(
            select(RateLimitOverride).where(
                and_(
                    RateLimitOverride.user_id == user_id,
                    or_(
                        RateLimitOverride.valid_until.is_(None),
                        RateLimitOverride.valid_until > now,
                    ),
                )
            )
        )
        override = override_result.scalar_one_or_none()

        # Get tier defaults
        defaults = RateLimitService.get_tier_defaults(user.tier or "free")

        # Calculate effective limits
        effective_limits = {
            "ocr_hourly": override.ocr_hourly if override and override.ocr_hourly else (
                user.rate_limit_hourly if user.rate_limit_hourly else defaults.ocr_hourly
            ),
            "ocr_daily": override.ocr_daily if override and override.ocr_daily else (
                user.rate_limit_daily if user.rate_limit_daily else defaults.ocr_daily
            ),
            "batch_hourly": override.batch_hourly if override and override.batch_hourly else defaults.batch_hourly,
            "api_per_minute": override.api_per_minute if override and override.api_per_minute else defaults.api_per_minute,
        }

        # Get current usage from Redis
        current_usage = await RateLimitService._get_current_usage(str(user_id))

        return RateLimitStatus(
            user_id=user_id,
            email=user.email,
            tier=user.tier or "free",
            effective_limits=effective_limits,
            current_usage=current_usage,
            has_override=override is not None,
            override_valid_until=override.valid_until if override else None,
            override_reason=override.reason if override else None,
        )

    @staticmethod
    async def _get_current_usage(user_id: str) -> Dict[str, int]:
        """Get current rate limit usage from Redis.

        Args:
            user_id: User ID string

        Returns:
            Current usage counts
        """
        try:
            # Verwende zentrale settings - REDIS_URL wird automatisch konstruiert
            client = redis.from_url(settings.REDIS_URL)

            # Keys for rate limiting
            keys = {
                "ocr_hourly": f"rate_limit:ocr_hourly:{user_id}",
                "ocr_daily": f"rate_limit:ocr_daily:{user_id}",
                "batch_hourly": f"rate_limit:batch_hourly:{user_id}",
                "api_per_minute": f"rate_limit:api_minute:{user_id}",
            }

            usage = {}
            for name, key in keys.items():
                value = await client.get(key)
                usage[name] = int(value) if value else 0

            await client.close()
            return usage
        except Exception as e:
            logger.warning("redis_usage_fetch_failed", error=str(e))
            return {
                "ocr_hourly": 0,
                "ocr_daily": 0,
                "batch_hourly": 0,
                "api_per_minute": 0,
            }

    @staticmethod
    async def create_override(
        db: AsyncSession,
        user_id: UUID,
        data: RateLimitOverrideCreate,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> Optional[RateLimitOverrideResponse]:
        """Create or update a rate limit override for a user.

        Args:
            db: Database session
            user_id: User to override limits for
            data: Override data
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Created/updated override or None if user not found
        """
        # Check if user exists
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()

        if not user:
            return None

        # Check for existing override
        override_result = await db.execute(
            select(RateLimitOverride).where(RateLimitOverride.user_id == user_id)
        )
        override = override_result.scalar_one_or_none()

        if override:
            # Update existing
            if data.ocr_hourly is not None:
                override.ocr_hourly = data.ocr_hourly
            if data.ocr_daily is not None:
                override.ocr_daily = data.ocr_daily
            if data.batch_hourly is not None:
                override.batch_hourly = data.batch_hourly
            if data.api_per_minute is not None:
                override.api_per_minute = data.api_per_minute
            override.valid_until = data.valid_until
            override.reason = data.reason
            override.updated_at = datetime.utcnow()
            action = "update_rate_limit_override"
        else:
            # Create new
            override = RateLimitOverride(
                user_id=user_id,
                ocr_hourly=data.ocr_hourly,
                ocr_daily=data.ocr_daily,
                batch_hourly=data.batch_hourly,
                api_per_minute=data.api_per_minute,
                valid_until=data.valid_until,
                created_by_id=admin.id,
                reason=data.reason,
            )
            db.add(override)
            action = "create_rate_limit_override"

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user_id,
            action=action,
            action_details={
                "ocr_hourly": data.ocr_hourly,
                "ocr_daily": data.ocr_daily,
                "batch_hourly": data.batch_hourly,
                "api_per_minute": data.api_per_minute,
                "valid_until": data.valid_until.isoformat() if data.valid_until else None,
                "reason": data.reason,
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()
        await db.refresh(override)

        logger.info(
            "rate_limit_override_created",
            user_id=str(user_id),
            admin_id=str(admin.id),
        )

        return RateLimitOverrideResponse.model_validate(override)

    @staticmethod
    async def delete_override(
        db: AsyncSession,
        user_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Delete a rate limit override (revert to tier defaults).

        Args:
            db: Database session
            user_id: User whose override to delete
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            True if deleted, False if not found
        """
        result = await db.execute(
            select(RateLimitOverride).where(RateLimitOverride.user_id == user_id)
        )
        override = result.scalar_one_or_none()

        if not override:
            return False

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user_id,
            action="delete_rate_limit_override",
            action_details={
                "previous_ocr_hourly": override.ocr_hourly,
                "previous_ocr_daily": override.ocr_daily,
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.delete(override)
        await db.commit()

        logger.info(
            "rate_limit_override_deleted",
            user_id=str(user_id),
            admin_id=str(admin.id),
        )

        return True

    @staticmethod
    async def change_tier(
        db: AsyncSession,
        user_id: UUID,
        new_tier: UserTier,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """Change a user's tier.

        Args:
            db: Database session
            user_id: User whose tier to change
            new_tier: New tier
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            Updated user or None if not found
        """
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            return None

        old_tier = user.tier
        user.tier = new_tier.value

        # Log admin action
        admin_action = AdminAction(
            admin_id=admin.id,
            target_user_id=user_id,
            action="change_tier",
            action_details={
                "old_tier": old_tier,
                "new_tier": new_tier.value,
            },
            ip_address=ip_address,
        )
        db.add(admin_action)

        await db.commit()
        await db.refresh(user)

        logger.info(
            "user_tier_changed",
            user_id=str(user_id),
            admin_id=str(admin.id),
            old_tier=old_tier,
            new_tier=new_tier.value,
        )

        return user

    @staticmethod
    async def reset_usage(
        db: AsyncSession,
        user_id: UUID,
        admin: User,
        ip_address: Optional[str] = None,
    ) -> bool:
        """Reset rate limit usage counters for a user.

        Args:
            db: Database session
            user_id: User whose usage to reset
            admin: Admin performing the action
            ip_address: Request IP address

        Returns:
            True if successful
        """
        try:
            # Verwende zentrale settings - REDIS_URL wird automatisch konstruiert
            client = redis.from_url(settings.REDIS_URL)

            # Delete all rate limit keys for user
            keys = [
                f"rate_limit:ocr_hourly:{user_id}",
                f"rate_limit:ocr_daily:{user_id}",
                f"rate_limit:batch_hourly:{user_id}",
                f"rate_limit:api_minute:{user_id}",
            ]

            for key in keys:
                await client.delete(key)

            await client.close()

            # Log admin action
            admin_action = AdminAction(
                admin_id=admin.id,
                target_user_id=user_id,
                action="reset_rate_limit_usage",
                action_details={},
                ip_address=ip_address,
            )
            db.add(admin_action)
            await db.commit()

            logger.info(
                "rate_limit_usage_reset",
                user_id=str(user_id),
                admin_id=str(admin.id),
            )

            return True
        except Exception as e:
            logger.error("rate_limit_reset_failed", error=str(e))
            return False

    @staticmethod
    async def get_usage_stats(db: AsyncSession) -> RateLimitUsageStats:
        """Get aggregated rate limit usage statistics.

        Args:
            db: Database session

        Returns:
            Usage statistics
        """
        # Total users
        total_result = await db.execute(select(func.count()).select_from(User))
        total_users = total_result.scalar() or 0

        # Users with overrides
        override_result = await db.execute(
            select(func.count()).select_from(RateLimitOverride)
        )
        users_with_overrides = override_result.scalar() or 0

        # Users by tier
        tier_result = await db.execute(
            select(User.tier, func.count())
            .group_by(User.tier)
        )
        usage_by_tier = {}
        for row in tier_result.all():
            tier = row[0] or "free"
            defaults = RateLimitService.get_tier_defaults(tier)
            usage_by_tier[tier] = {
                "count": row[1],
                "defaults": {
                    "ocr_hourly": defaults.ocr_hourly,
                    "ocr_daily": defaults.ocr_daily,
                    "batch_hourly": defaults.batch_hourly,
                    "api_per_minute": defaults.api_per_minute,
                },
            }

        # Top users by processed documents today
        top_result = await db.execute(
            select(User.id, User.email, User.documents_processed_today)
            .order_by(User.documents_processed_today.desc())
            .limit(10)
        )
        top_users = [
            {
                "user_id": str(row[0]),
                "email": row[1],
                "documents_today": row[2],
            }
            for row in top_result.all()
        ]

        # Count users at daily limit (processed >= daily_quota)
        at_limit_result = await db.execute(
            select(func.count()).where(
                User.documents_processed_today >= User.daily_quota
            )
        )
        users_at_limit = at_limit_result.scalar() or 0

        return RateLimitUsageStats(
            total_users=total_users,
            users_at_limit=users_at_limit,
            users_with_overrides=users_with_overrides,
            usage_by_tier=usage_by_tier,
            top_users_by_usage=top_users,
        )
