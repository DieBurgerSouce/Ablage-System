"""Learning Autonomy Service - Lernende Automatisierung.

Pro User + Pro Aktionstyp ein Autonomie-Level das mit Bestaetigungen waechst:
- manual → suggest → auto_with_undo → full_auto

Jede Bestaetigung erhoeht den Streak-Zaehler.
Bei Erreichen des Schwellenwerts steigt das Level automatisch.
Ablehnungen/Korrekturen senken den Streak und ggf. das Level.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models_learning_autonomy import (
    ActionType,
    AutonomyDecisionLog,
    AutonomyLevelHistory,
    LearningAutonomyLevel,
    UserActionAutonomy,
)

logger = structlog.get_logger(__name__)

# Level-Upgrade-Reihenfolge
LEVEL_ORDER = [
    LearningAutonomyLevel.MANUAL,
    LearningAutonomyLevel.SUGGEST,
    LearningAutonomyLevel.AUTO_WITH_UNDO,
    LearningAutonomyLevel.FULL_AUTO,
]


class LearningAutonomyService:
    """Service fuer lernende Autonomie pro User und Aktionstyp."""

    # ================================================================
    # Level-Abfrage
    # ================================================================

    async def get_autonomy_level(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
    ) -> LearningAutonomyLevel:
        """Aktuelles Autonomie-Level fuer User + Aktionstyp.

        Erstellt automatisch einen Eintrag mit Default 'suggest' falls keiner existiert.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            company_id: Firmen-ID
            action_type: Aktionstyp

        Returns:
            Aktuelles LearningAutonomyLevel
        """
        uaa = await self._get_or_create(db, user_id, company_id, action_type)
        return LearningAutonomyLevel(uaa.current_level)

    async def get_all_levels(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
    ) -> List[Dict]:
        """Alle Autonomie-Levels eines Users abrufen.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            company_id: Firmen-ID

        Returns:
            Liste aller Level-Eintraege
        """
        query = (
            select(UserActionAutonomy)
            .where(
                and_(
                    UserActionAutonomy.user_id == user_id,
                    UserActionAutonomy.company_id == company_id,
                )
            )
            .order_by(UserActionAutonomy.action_type)
        )
        result = await db.execute(query)
        entries = result.scalars().all()

        return [
            {
                "action_type": e.action_type,
                "current_level": e.current_level,
                "is_manually_set": e.is_manually_set,
                "total_suggestions": e.total_suggestions,
                "total_confirmations": e.total_confirmations,
                "total_rejections": e.total_rejections,
                "current_streak": e.current_streak,
                "best_streak": e.best_streak,
                "avg_confidence": round(e.avg_confidence, 3),
                "confirmation_rate": round(
                    e.total_confirmations / max(e.total_suggestions, 1), 3
                ),
            }
            for e in entries
        ]

    # ================================================================
    # Entscheidung aufzeichnen
    # ================================================================

    async def record_confirmation(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
        confidence: float = 0.0,
        document_id: Optional[UUID] = None,
        suggested_value: Optional[str] = None,
    ) -> Dict:
        """Bestaetigung eines Vorschlags aufzeichnen.

        Erhoeht den Streak und prueft ob ein Level-Upgrade faellig ist.

        Returns:
            Dict mit level_changed, new_level, streak
        """
        uaa = await self._get_or_create(db, user_id, company_id, action_type)

        # Metriken aktualisieren
        uaa.total_suggestions += 1
        uaa.total_confirmations += 1
        uaa.current_streak += 1
        uaa.best_streak = max(uaa.best_streak, uaa.current_streak)
        uaa.last_interaction_at = datetime.now(timezone.utc)
        uaa.last_confidence = confidence

        # Rolling Average Confidence
        if uaa.total_suggestions > 0:
            uaa.avg_confidence = (
                (uaa.avg_confidence * (uaa.total_suggestions - 1) + confidence)
                / uaa.total_suggestions
            )

        # Decision-Log
        log = AutonomyDecisionLog(
            user_id=user_id,
            company_id=company_id,
            action_type=action_type,
            autonomy_level_at_time=uaa.current_level,
            document_id=document_id,
            suggested_value=suggested_value,
            suggested_confidence=confidence,
            user_action="confirmed",
            decision_at=datetime.now(timezone.utc),
        )
        db.add(log)

        # Level-Upgrade pruefen
        level_changed = await self._check_level_upgrade(db, uaa)

        await db.flush()

        return {
            "level_changed": level_changed,
            "current_level": uaa.current_level,
            "current_streak": uaa.current_streak,
            "total_confirmations": uaa.total_confirmations,
        }

    async def record_rejection(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
        document_id: Optional[UUID] = None,
        suggested_value: Optional[str] = None,
    ) -> Dict:
        """Ablehnung eines Vorschlags aufzeichnen.

        Setzt den Streak zurueck und prueft ob ein Level-Downgrade noetig ist.

        Returns:
            Dict mit level_changed, new_level
        """
        uaa = await self._get_or_create(db, user_id, company_id, action_type)

        uaa.total_suggestions += 1
        uaa.total_rejections += 1
        uaa.current_streak = 0  # Streak zuruecksetzen
        uaa.last_interaction_at = datetime.now(timezone.utc)

        # Decision-Log
        log = AutonomyDecisionLog(
            user_id=user_id,
            company_id=company_id,
            action_type=action_type,
            autonomy_level_at_time=uaa.current_level,
            document_id=document_id,
            suggested_value=suggested_value,
            user_action="rejected",
            decision_at=datetime.now(timezone.utc),
        )
        db.add(log)

        # Level-Downgrade pruefen
        level_changed = await self._check_level_downgrade(db, uaa)

        await db.flush()

        return {
            "level_changed": level_changed,
            "current_level": uaa.current_level,
            "total_rejections": uaa.total_rejections,
        }

    async def record_correction(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
        suggested_value: str,
        corrected_value: str,
        document_id: Optional[UUID] = None,
    ) -> Dict:
        """Korrektur eines Vorschlags aufzeichnen.

        Zaehlt als Teilbestaetigung (Richtung stimmte, Details nicht).

        Returns:
            Dict mit level_changed, new_level
        """
        uaa = await self._get_or_create(db, user_id, company_id, action_type)

        uaa.total_suggestions += 1
        uaa.total_corrections += 1
        uaa.current_streak = max(0, uaa.current_streak - 1)  # Streak leicht reduzieren
        uaa.last_interaction_at = datetime.now(timezone.utc)

        # Decision-Log
        log = AutonomyDecisionLog(
            user_id=user_id,
            company_id=company_id,
            action_type=action_type,
            autonomy_level_at_time=uaa.current_level,
            document_id=document_id,
            suggested_value=suggested_value,
            corrected_value=corrected_value,
            user_action="corrected",
            decision_at=datetime.now(timezone.utc),
        )
        db.add(log)

        await db.flush()

        return {
            "level_changed": False,
            "current_level": uaa.current_level,
            "total_corrections": uaa.total_corrections,
        }

    async def record_auto_execution(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
        confidence: float,
        document_id: Optional[UUID] = None,
        suggested_value: Optional[str] = None,
    ) -> None:
        """Automatische Ausfuehrung aufzeichnen (bei auto_with_undo oder full_auto)."""
        uaa = await self._get_or_create(db, user_id, company_id, action_type)
        uaa.total_auto_executed += 1
        uaa.last_interaction_at = datetime.now(timezone.utc)
        uaa.last_confidence = confidence

        log = AutonomyDecisionLog(
            user_id=user_id,
            company_id=company_id,
            action_type=action_type,
            autonomy_level_at_time=uaa.current_level,
            document_id=document_id,
            suggested_value=suggested_value,
            suggested_confidence=confidence,
            user_action="auto_executed",
            decision_at=datetime.now(timezone.utc),
        )
        db.add(log)
        await db.flush()

    async def record_undo(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
        document_id: Optional[UUID] = None,
    ) -> Dict:
        """Undo einer automatischen Ausfuehrung aufzeichnen.

        Zu viele Undos fuehren zu Level-Downgrade.
        """
        uaa = await self._get_or_create(db, user_id, company_id, action_type)
        uaa.total_undone += 1
        uaa.current_streak = 0
        uaa.last_interaction_at = datetime.now(timezone.utc)

        log = AutonomyDecisionLog(
            user_id=user_id,
            company_id=company_id,
            action_type=action_type,
            autonomy_level_at_time=uaa.current_level,
            document_id=document_id,
            user_action="undone",
            decision_at=datetime.now(timezone.utc),
        )
        db.add(log)

        # Bei zu vielen Undos: Downgrade
        level_changed = False
        if uaa.total_undone > 3 and uaa.current_level == LearningAutonomyLevel.FULL_AUTO.value:
            level_changed = await self._downgrade_level(db, uaa, "undo_threshold")
        elif uaa.total_undone > 5 and uaa.current_level == LearningAutonomyLevel.AUTO_WITH_UNDO.value:
            level_changed = await self._downgrade_level(db, uaa, "undo_threshold")

        await db.flush()

        return {
            "level_changed": level_changed,
            "current_level": uaa.current_level,
            "total_undone": uaa.total_undone,
        }

    # ================================================================
    # Manuelles Level-Setzen
    # ================================================================

    async def set_level_manually(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
        new_level: str,
    ) -> Dict:
        """Autonomie-Level manuell setzen.

        Args:
            db: Datenbank-Session
            user_id: User-ID
            company_id: Firmen-ID
            action_type: Aktionstyp
            new_level: Neues Level (manual/suggest/auto_with_undo/full_auto)

        Returns:
            Dict mit altem und neuem Level
        """
        uaa = await self._get_or_create(db, user_id, company_id, action_type)

        old_level = uaa.current_level
        uaa.current_level = new_level
        uaa.is_manually_set = True

        # History-Eintrag
        history = AutonomyLevelHistory(
            user_action_autonomy_id=uaa.id,
            previous_level=old_level,
            new_level=new_level,
            change_reason="manual_set",
            confirmations_at_change=uaa.total_confirmations,
            streak_at_change=uaa.current_streak,
            avg_confidence_at_change=uaa.avg_confidence,
        )
        db.add(history)
        await db.flush()

        logger.info(
            "autonomy_level_manually_set",
            user_id=str(user_id),
            action_type=action_type,
            old_level=old_level,
            new_level=new_level,
        )

        return {
            "old_level": old_level,
            "new_level": new_level,
            "is_manually_set": True,
        }

    # ================================================================
    # Vertrauenskurve
    # ================================================================

    async def get_trust_curve(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
        limit: int = 100,
    ) -> List[Dict]:
        """Vertrauenskurve als Zeitreihe fuer die Visualisierung.

        Returns:
            Liste von {timestamp, streak, level, action} Datenpunkten
        """
        query = (
            select(AutonomyDecisionLog)
            .where(
                and_(
                    AutonomyDecisionLog.user_id == user_id,
                    AutonomyDecisionLog.company_id == company_id,
                    AutonomyDecisionLog.action_type == action_type,
                )
            )
            .order_by(AutonomyDecisionLog.suggestion_at.desc())
            .limit(limit)
        )
        result = await db.execute(query)
        logs = result.scalars().all()

        return [
            {
                "timestamp": log.suggestion_at.isoformat() if log.suggestion_at else None,
                "action": log.user_action,
                "level": log.autonomy_level_at_time,
                "confidence": log.suggested_confidence,
            }
            for log in reversed(logs)
        ]

    # ================================================================
    # Interne Methoden
    # ================================================================

    async def _get_or_create(
        self,
        db: AsyncSession,
        user_id: UUID,
        company_id: UUID,
        action_type: str,
    ) -> UserActionAutonomy:
        """Holt oder erstellt einen UserActionAutonomy-Eintrag."""
        query = (
            select(UserActionAutonomy)
            .where(
                and_(
                    UserActionAutonomy.user_id == user_id,
                    UserActionAutonomy.company_id == company_id,
                    UserActionAutonomy.action_type == action_type,
                )
            )
        )
        result = await db.execute(query)
        uaa = result.scalar_one_or_none()

        if not uaa:
            uaa = UserActionAutonomy(
                user_id=user_id,
                company_id=company_id,
                action_type=action_type,
                current_level=LearningAutonomyLevel.SUGGEST.value,
            )
            db.add(uaa)
            await db.flush()

        return uaa

    async def _check_level_upgrade(
        self,
        db: AsyncSession,
        uaa: UserActionAutonomy,
    ) -> bool:
        """Prueft ob ein Level-Upgrade faellig ist."""
        if uaa.is_manually_set:
            return False  # Manuell gesetzte Levels nicht automatisch aendern

        current_idx = next(
            (i for i, l in enumerate(LEVEL_ORDER) if l.value == uaa.current_level),
            -1,
        )

        if current_idx >= len(LEVEL_ORDER) - 1:
            return False  # Bereits auf hoechstem Level

        # Upgrade-Bedingungen pruefen
        if (
            uaa.current_level == LearningAutonomyLevel.SUGGEST.value
            and uaa.current_streak >= uaa.confirmations_for_auto_undo
        ):
            return await self._upgrade_level(db, uaa, "streak_threshold")

        if (
            uaa.current_level == LearningAutonomyLevel.AUTO_WITH_UNDO.value
            and uaa.total_confirmations >= uaa.confirmations_for_full_auto
            and uaa.total_undone <= 2
        ):
            return await self._upgrade_level(db, uaa, "streak_threshold")

        return False

    async def _check_level_downgrade(
        self,
        db: AsyncSession,
        uaa: UserActionAutonomy,
    ) -> bool:
        """Prueft ob ein Level-Downgrade noetig ist."""
        if uaa.is_manually_set:
            return False

        # Zu viele Ablehnungen in Folge
        recent_rejection_rate = uaa.total_rejections / max(uaa.total_suggestions, 1)

        if recent_rejection_rate > 0.3 and uaa.total_suggestions >= 10:
            return await self._downgrade_level(db, uaa, "rejection_rate")

        return False

    async def _upgrade_level(
        self,
        db: AsyncSession,
        uaa: UserActionAutonomy,
        reason: str,
    ) -> bool:
        """Level um eine Stufe erhoehen."""
        current_idx = next(
            (i for i, l in enumerate(LEVEL_ORDER) if l.value == uaa.current_level),
            -1,
        )
        if current_idx < 0 or current_idx >= len(LEVEL_ORDER) - 1:
            return False

        old_level = uaa.current_level
        new_level = LEVEL_ORDER[current_idx + 1].value
        uaa.current_level = new_level

        history = AutonomyLevelHistory(
            user_action_autonomy_id=uaa.id,
            previous_level=old_level,
            new_level=new_level,
            change_reason=reason,
            confirmations_at_change=uaa.total_confirmations,
            streak_at_change=uaa.current_streak,
            avg_confidence_at_change=uaa.avg_confidence,
        )
        db.add(history)

        logger.info(
            "autonomy_level_upgraded",
            user_id=str(uaa.user_id),
            action_type=uaa.action_type,
            old_level=old_level,
            new_level=new_level,
            reason=reason,
            streak=uaa.current_streak,
        )

        return True

    async def _downgrade_level(
        self,
        db: AsyncSession,
        uaa: UserActionAutonomy,
        reason: str,
    ) -> bool:
        """Level um eine Stufe senken."""
        current_idx = next(
            (i for i, l in enumerate(LEVEL_ORDER) if l.value == uaa.current_level),
            -1,
        )
        if current_idx <= 0:
            return False

        old_level = uaa.current_level
        new_level = LEVEL_ORDER[current_idx - 1].value
        uaa.current_level = new_level

        history = AutonomyLevelHistory(
            user_action_autonomy_id=uaa.id,
            previous_level=old_level,
            new_level=new_level,
            change_reason=reason,
            confirmations_at_change=uaa.total_confirmations,
            streak_at_change=uaa.current_streak,
            avg_confidence_at_change=uaa.avg_confidence,
        )
        db.add(history)

        logger.info(
            "autonomy_level_downgraded",
            user_id=str(uaa.user_id),
            action_type=uaa.action_type,
            old_level=old_level,
            new_level=new_level,
            reason=reason,
        )

        return True


# Singleton
_learning_autonomy_service: Optional[LearningAutonomyService] = None


def get_learning_autonomy_service() -> LearningAutonomyService:
    """Singleton-Instanz des LearningAutonomyService."""
    global _learning_autonomy_service
    if _learning_autonomy_service is None:
        _learning_autonomy_service = LearningAutonomyService()
    return _learning_autonomy_service
