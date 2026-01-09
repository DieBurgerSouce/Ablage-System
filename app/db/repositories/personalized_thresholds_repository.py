# -*- coding: utf-8 -*-
"""
Personalized Thresholds Repository.

PHASE 0 CRITICAL FIX: Ersetzt In-Memory Storage durch DB-Persistenz.

Dieses Repository stellt die Datenschicht fuer den PersonalizedThresholdsService
bereit. Alle Operationen sind async und verwenden SQLAlchemy 2.0 Syntax.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.db.models import (
    PrivatUserProfile,
    PrivatUserThreshold,
    PrivatThresholdAdjustment,
    PrivatThresholdRecommendation,
)
from app.db.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


class PrivatUserProfileRepository(BaseRepository[PrivatUserProfile]):
    """Repository fuer User-Profile."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, PrivatUserProfile)

    async def get_by_user_id(self, user_id: UUID) -> Optional[PrivatUserProfile]:
        """Holt Profil nach User-ID."""
        result = await self.db.execute(
            select(PrivatUserProfile).where(PrivatUserProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: UUID,
        profile_data: Dict[str, Any],
    ) -> PrivatUserProfile:
        """Erstellt oder aktualisiert ein Profil."""
        existing = await self.get_by_user_id(user_id)

        if existing:
            # Update existing
            for field, value in profile_data.items():
                if hasattr(existing, field):
                    setattr(existing, field, value)
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)

            logger.info("user_profile_updated", user_id=str(user_id))
            return existing
        else:
            # Create new
            profile_data["user_id"] = user_id
            profile = await self.create(profile_data)

            logger.info("user_profile_created", user_id=str(user_id))
            return profile


class PrivatUserThresholdRepository(BaseRepository[PrivatUserThreshold]):
    """Repository fuer User-Thresholds."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, PrivatUserThreshold)

    async def get_by_user_id(self, user_id: UUID) -> List[PrivatUserThreshold]:
        """Holt alle Thresholds eines Users."""
        result = await self.db.execute(
            select(PrivatUserThreshold).where(PrivatUserThreshold.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_by_user_and_type(
        self,
        user_id: UUID,
        threshold_type: str,
    ) -> Optional[PrivatUserThreshold]:
        """Holt einen spezifischen Threshold eines Users."""
        result = await self.db.execute(
            select(PrivatUserThreshold).where(
                and_(
                    PrivatUserThreshold.user_id == user_id,
                    PrivatUserThreshold.threshold_type == threshold_type,
                )
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        user_id: UUID,
        threshold_type: str,
        threshold_data: Dict[str, Any],
    ) -> PrivatUserThreshold:
        """Erstellt oder aktualisiert einen Threshold."""
        existing = await self.get_by_user_and_type(user_id, threshold_type)

        if existing:
            # Update existing
            for field, value in threshold_data.items():
                if hasattr(existing, field):
                    setattr(existing, field, value)
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(existing)

            logger.debug(
                "threshold_updated",
                user_id=str(user_id),
                threshold_type=threshold_type,
            )
            return existing
        else:
            # Create new
            threshold_data["user_id"] = user_id
            threshold_data["threshold_type"] = threshold_type
            threshold = await self.create(threshold_data)

            logger.debug(
                "threshold_created",
                user_id=str(user_id),
                threshold_type=threshold_type,
            )
            return threshold

    async def bulk_upsert(
        self,
        user_id: UUID,
        thresholds: List[Dict[str, Any]],
    ) -> List[PrivatUserThreshold]:
        """Erstellt oder aktualisiert mehrere Thresholds."""
        results = []
        for threshold_data in thresholds:
            threshold_type = threshold_data.pop("threshold_type")
            result = await self.upsert(user_id, threshold_type, threshold_data)
            results.append(result)
        return results

    async def record_trigger(
        self,
        user_id: UUID,
        threshold_type: str,
    ) -> None:
        """Zeichnet auf, dass ein Threshold getriggert wurde."""
        threshold = await self.get_by_user_and_type(user_id, threshold_type)
        if threshold:
            threshold.times_triggered += 1
            threshold.last_used_at = datetime.now(timezone.utc)
            await self.db.commit()

    async def record_action(
        self,
        user_id: UUID,
        threshold_type: str,
        action_taken: bool,
    ) -> None:
        """Zeichnet auf, ob User auf Threshold-Alert reagiert hat."""
        threshold = await self.get_by_user_and_type(user_id, threshold_type)
        if threshold:
            if action_taken:
                threshold.times_acted_on += 1

            # Update effectiveness score
            if threshold.times_triggered > 0:
                threshold.effectiveness_score = Decimal(
                    str(threshold.times_acted_on / threshold.times_triggered)
                )

            await self.db.commit()

    async def delete_by_user(self, user_id: UUID) -> int:
        """Loescht alle Thresholds eines Users (fuer GDPR)."""
        thresholds = await self.get_by_user_id(user_id)
        count = len(thresholds)

        for threshold in thresholds:
            await self.db.delete(threshold)

        await self.db.commit()

        logger.info(
            "user_thresholds_deleted",
            user_id=str(user_id),
            count=count,
        )
        return count


class PrivatThresholdAdjustmentRepository(BaseRepository[PrivatThresholdAdjustment]):
    """Repository fuer Threshold-Adjustments (Audit Log)."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, PrivatThresholdAdjustment)

    async def get_by_user_id(
        self,
        user_id: UUID,
        limit: int = 20,
    ) -> List[PrivatThresholdAdjustment]:
        """Holt Adjustments eines Users, sortiert nach Datum."""
        result = await self.db.execute(
            select(PrivatThresholdAdjustment)
            .where(PrivatThresholdAdjustment.user_id == user_id)
            .order_by(PrivatThresholdAdjustment.applied_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_user_and_type(
        self,
        user_id: UUID,
        threshold_type: str,
        limit: int = 10,
    ) -> List[PrivatThresholdAdjustment]:
        """Holt Adjustments fuer einen spezifischen Threshold."""
        result = await self.db.execute(
            select(PrivatThresholdAdjustment)
            .where(
                and_(
                    PrivatThresholdAdjustment.user_id == user_id,
                    PrivatThresholdAdjustment.threshold_type == threshold_type,
                )
            )
            .order_by(PrivatThresholdAdjustment.applied_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def rollback(
        self,
        adjustment_id: UUID,
        rolled_back_by: UUID,
    ) -> Optional[PrivatThresholdAdjustment]:
        """Markiert ein Adjustment als rolled back."""
        adjustment = await self.get_by_id(adjustment_id)

        if not adjustment or not adjustment.can_rollback or adjustment.rolled_back:
            return None

        adjustment.rolled_back = True
        adjustment.rolled_back_at = datetime.now(timezone.utc)
        adjustment.rolled_back_by = rolled_back_by

        await self.db.commit()
        await self.db.refresh(adjustment)

        logger.info(
            "adjustment_rolled_back",
            adjustment_id=str(adjustment_id),
            rolled_back_by=str(rolled_back_by),
        )

        return adjustment


class PrivatThresholdRecommendationRepository(BaseRepository[PrivatThresholdRecommendation]):
    """Repository fuer Threshold-Recommendations."""

    def __init__(self, db: AsyncSession):
        super().__init__(db, PrivatThresholdRecommendation)

    async def get_pending_by_user(
        self,
        user_id: UUID,
    ) -> List[PrivatThresholdRecommendation]:
        """Holt ausstehende Empfehlungen eines Users."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(PrivatThresholdRecommendation)
            .where(
                and_(
                    PrivatThresholdRecommendation.user_id == user_id,
                    PrivatThresholdRecommendation.accepted.is_(None),
                    PrivatThresholdRecommendation.expires_at > now,
                )
            )
            .order_by(PrivatThresholdRecommendation.created_at.desc())
        )
        return list(result.scalars().all())

    async def accept(
        self,
        recommendation_id: UUID,
    ) -> Optional[PrivatThresholdRecommendation]:
        """Akzeptiert eine Empfehlung."""
        recommendation = await self.get_by_id(recommendation_id)

        if not recommendation or recommendation.accepted is not None:
            return None

        recommendation.accepted = True
        recommendation.accepted_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(recommendation)

        logger.info(
            "recommendation_accepted",
            recommendation_id=str(recommendation_id),
            threshold_type=recommendation.threshold_type,
        )

        return recommendation

    async def reject(
        self,
        recommendation_id: UUID,
    ) -> Optional[PrivatThresholdRecommendation]:
        """Lehnt eine Empfehlung ab."""
        recommendation = await self.get_by_id(recommendation_id)

        if not recommendation or recommendation.accepted is not None:
            return None

        recommendation.accepted = False
        recommendation.accepted_at = datetime.now(timezone.utc)

        await self.db.commit()
        await self.db.refresh(recommendation)

        logger.info(
            "recommendation_rejected",
            recommendation_id=str(recommendation_id),
            threshold_type=recommendation.threshold_type,
        )

        return recommendation

    async def cleanup_expired(self) -> int:
        """Loescht abgelaufene, nicht bearbeitete Empfehlungen."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(PrivatThresholdRecommendation)
            .where(
                and_(
                    PrivatThresholdRecommendation.expires_at < now,
                    PrivatThresholdRecommendation.accepted.is_(None),
                )
            )
        )
        expired = list(result.scalars().all())
        count = len(expired)

        for rec in expired:
            await self.db.delete(rec)

        await self.db.commit()

        if count > 0:
            logger.info("expired_recommendations_cleaned", count=count)

        return count
