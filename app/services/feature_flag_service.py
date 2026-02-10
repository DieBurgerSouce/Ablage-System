"""
Service fuer Feature-Flag Verwaltung und Evaluation.

Bietet:
- CRUD-Operationen fuer Feature-Flags
- Cached Feature-Flag Evaluation
- Kill-Switch-Funktion
- Gradual Rollout Support
"""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional
from uuid import UUID
from datetime import datetime

from app.db.models import FeatureFlag
from app.core.cache import cache_get, cache_set, invalidate_cache
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

# Cache prefix for feature flags
FEATURE_FLAG_CACHE_PREFIX = "cache:ff"
FEATURE_FLAG_CACHE_TTL = 60  # 1 minute cache for flag evaluations


class FeatureFlagService:
    """Service fuer Feature-Flag Verwaltung."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_all(
        self,
        enabled_only: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[FeatureFlag]:
        """Alle Feature-Flags abrufen."""
        try:
            stmt = select(FeatureFlag).order_by(FeatureFlag.created_at.desc())
            if enabled_only:
                stmt = stmt.where(FeatureFlag.enabled == True)  # noqa: E712
            stmt = stmt.limit(limit).offset(offset)
            result = await self.db.execute(stmt)
            return list(result.scalars().all())
        except Exception as e:
            logger.error("get_all_feature_flags_failed", **safe_error_log(e))
            return []

    async def count(self, enabled_only: bool = False) -> int:
        """Anzahl der Feature-Flags zaehlen."""
        try:
            from sqlalchemy import func as sa_func
            stmt = select(sa_func.count(FeatureFlag.id))
            if enabled_only:
                stmt = stmt.where(FeatureFlag.enabled == True)  # noqa: E712
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none() or 0
        except Exception as e:
            logger.error("count_feature_flags_failed", **safe_error_log(e))
            return 0

    async def get_by_key(self, key: str) -> Optional[FeatureFlag]:
        """Feature-Flag anhand des Keys abrufen."""
        try:
            stmt = select(FeatureFlag).where(FeatureFlag.key == key)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("get_feature_flag_failed", **safe_error_log(e), key=key)
            return None

    async def get_by_id(self, flag_id: UUID) -> Optional[FeatureFlag]:
        """Feature-Flag anhand der ID abrufen."""
        try:
            stmt = select(FeatureFlag).where(FeatureFlag.id == flag_id)
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error("get_feature_flag_by_id_failed", **safe_error_log(e))
            return None

    async def create(
        self,
        key: str,
        name: str,
        description: Optional[str] = None,
        enabled: bool = False,
        rollout_percentage: int = 0,
        target_tiers: Optional[List[str]] = None,
        target_users: Optional[List[str]] = None,
        variants: Optional[Dict[str, int]] = None,
        starts_at: Optional[datetime] = None,
        ends_at: Optional[datetime] = None,
        config: Optional[Dict[str, object]] = None,
        created_by_id: Optional[UUID] = None,
    ) -> FeatureFlag:
        """Neues Feature-Flag erstellen."""
        try:
            flag = FeatureFlag(
                key=key,
                name=name,
                description=description,
                enabled=enabled,
                rollout_percentage=rollout_percentage,
                target_tiers=target_tiers or [],
                target_users=target_users or [],
                variants=variants or {},
                starts_at=starts_at,
                ends_at=ends_at,
                config=config or {},
                created_by_id=created_by_id,
            )
            self.db.add(flag)
            await self.db.commit()
            await self.db.refresh(flag)

            # Invalidate flag cache
            await invalidate_cache(f"{FEATURE_FLAG_CACHE_PREFIX}:*")

            logger.info("feature_flag_created", key=key, enabled=enabled)
            return flag
        except Exception as e:
            await self.db.rollback()
            logger.error("create_feature_flag_failed", **safe_error_log(e), key=key)
            raise ValueError(f"Fehler beim Erstellen des Feature-Flags: {key}")

    async def update_flag(
        self,
        flag_id: UUID,
        updates: Dict[str, object],
        updated_by_id: Optional[UUID] = None,
    ) -> Optional[FeatureFlag]:
        """Feature-Flag aktualisieren."""
        try:
            flag = await self.get_by_id(flag_id)
            if flag is None:
                return None

            allowed_fields = {
                "name", "description", "enabled", "rollout_percentage",
                "target_tiers", "target_users", "variants",
                "starts_at", "ends_at", "config",
            }

            for field, value in updates.items():
                if field in allowed_fields:
                    setattr(flag, field, value)

            if updated_by_id:
                flag.updated_by_id = updated_by_id

            await self.db.commit()
            await self.db.refresh(flag)

            # Invalidate flag cache
            await invalidate_cache(f"{FEATURE_FLAG_CACHE_PREFIX}:*")

            logger.info(
                "feature_flag_updated",
                key=flag.key,
                updates=list(updates.keys()),
            )
            return flag
        except Exception as e:
            await self.db.rollback()
            logger.error("update_feature_flag_failed", **safe_error_log(e))
            raise ValueError("Fehler beim Aktualisieren des Feature-Flags")

    async def delete_flag(self, flag_id: UUID) -> bool:
        """Feature-Flag loeschen."""
        try:
            flag = await self.get_by_id(flag_id)
            if flag is None:
                return False

            await self.db.delete(flag)
            await self.db.commit()

            await invalidate_cache(f"{FEATURE_FLAG_CACHE_PREFIX}:*")

            logger.info("feature_flag_deleted", key=flag.key)
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error("delete_feature_flag_failed", **safe_error_log(e))
            return False

    async def kill_switch(self, key: str) -> bool:
        """Sofort-Deaktivierung eines Feature-Flags (Kill-Switch).

        Deaktiviert das Flag und setzt rollout_percentage auf 0.
        """
        try:
            flag = await self.get_by_key(key)
            if flag is None:
                logger.warning("kill_switch_flag_not_found", key=key)
                return False

            flag.enabled = False
            flag.rollout_percentage = 0
            await self.db.commit()

            await invalidate_cache(f"{FEATURE_FLAG_CACHE_PREFIX}:*")

            logger.warning("feature_flag_kill_switch_activated", key=key)
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error("kill_switch_failed", **safe_error_log(e), key=key)
            return False

    async def evaluate(
        self,
        key: str,
        user_id: str,
        user_tier: Optional[str] = None,
    ) -> Dict[str, object]:
        """Feature-Flag fuer einen Benutzer evaluieren.

        Verwendet Cache fuer schnelle Evaluation.

        Returns:
            Dict mit enabled, variant, flag_key
        """
        # Check cache first
        cache_key = f"{FEATURE_FLAG_CACHE_PREFIX}:{key}:{user_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # Load from DB
        flag = await self.get_by_key(key)
        if flag is None:
            result: Dict[str, object] = {
                "flag_key": key,
                "enabled": False,
                "variant": None,
                "reason": "flag_not_found",
            }
            await cache_set(cache_key, result, ttl=FEATURE_FLAG_CACHE_TTL)
            return result

        enabled = flag.is_enabled_for_user(user_id, user_tier)
        variant = flag.get_variant_for_user(user_id) if enabled and flag.variants else None

        result = {
            "flag_key": key,
            "enabled": enabled,
            "variant": variant,
            "reason": "evaluated",
        }

        await cache_set(cache_key, result, ttl=FEATURE_FLAG_CACHE_TTL)

        logger.debug(
            "feature_flag_evaluated",
            key=key,
            enabled=enabled,
            variant=variant,
        )

        return result

    async def evaluate_all(
        self,
        user_id: str,
        user_tier: Optional[str] = None,
    ) -> Dict[str, Dict[str, object]]:
        """Alle aktiven Feature-Flags fuer einen Benutzer evaluieren."""
        flags = await self.get_all(enabled_only=True)
        results: Dict[str, Dict[str, object]] = {}

        for flag in flags:
            enabled = flag.is_enabled_for_user(user_id, user_tier)
            variant = (
                flag.get_variant_for_user(user_id)
                if enabled and flag.variants
                else None
            )
            results[flag.key] = {
                "enabled": enabled,
                "variant": variant,
            }

        return results


def get_feature_flag_service(db: AsyncSession) -> FeatureFlagService:
    """Factory fuer FeatureFlagService."""
    return FeatureFlagService(db)
