"""Smart Inbox Priority Scorer - ML-basierte Priorisierung.

Berechnet ML-Prioritäten basierend auf:
- Basis-Priorität (40%)
- Dringlichkeit (25%)
- Benutzer-Präferenzen (20%)
- Wichtigkeit (15%)
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.db.models import SmartInboxItem, UserBehaviorLog
from app.services.smart_inbox.behavior_learner import BehaviorLearner, UserPreferences
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class ScoredItem:
    """Item mit berechneter Priorität."""
    item_id: UUID
    raw_priority: float
    ml_priority: float
    boost_reasons: List[str]  # Deutsche Erklärungen


class PriorityScorer:
    """ML-basierte Prioritäts-Bewertung für Smart Inbox Items."""

    # Gewichtungen für ML-Priority
    WEIGHT_BASE_PRIORITY = 0.40
    WEIGHT_URGENCY = 0.25
    WEIGHT_USER_PREFERENCE = 0.20
    WEIGHT_IMPORTANCE = 0.15

    def __init__(self) -> None:
        """Initialisiert den Priority Scorer."""
        self.logger = logger.bind(service="priority_scorer")
        self.behavior_learner = BehaviorLearner()

    async def score(
        self,
        items: List[SmartInboxItem],
        user_id: UUID,
        db: AsyncSession,
    ) -> List[ScoredItem]:
        """
        Berechnet ML-Prioritäten für Smart Inbox Items.

        Args:
            items: Liste von SmartInboxItem
            user_id: Benutzer-ID
            db: Async DB Session

        Returns:
            Liste von ScoredItem mit ML-Prioritäten
        """
        self.logger.info(
            "scoring_items",
            user_id=str(user_id),
            item_count=len(items),
        )

        # User Preferences laden
        user_prefs = await self.behavior_learner.get_user_preferences(user_id, db)

        scored_items: List[ScoredItem] = []

        for item in items:
            try:
                scored = await self._score_single_item(item, user_prefs, db)
                scored_items.append(scored)
            except Exception as e:
                self.logger.error(
                    "scoring_failed",
                    item_id=str(item.id),
                    **safe_error_log(e),
                )
                # Fallback: Raw Priority verwenden
                scored_items.append(
                    ScoredItem(
                        item_id=item.id,
                        raw_priority=item.raw_priority,
                        ml_priority=item.raw_priority,
                        boost_reasons=["Scoring fehlgeschlagen - Basis-Priorität verwendet"],
                    )
                )

        self.logger.info(
            "scoring_complete",
            scored_count=len(scored_items),
        )

        return scored_items

    async def _score_single_item(
        self,
        item: SmartInboxItem,
        user_prefs: UserPreferences,
        db: AsyncSession,
    ) -> ScoredItem:
        """
        Berechnet ML-Priorität für ein einzelnes Item.

        Args:
            item: SmartInboxItem
            user_prefs: Benutzer-Präferenzen
            db: Async DB Session

        Returns:
            ScoredItem
        """
        boost_reasons: List[str] = []

        # 1. Basis-Priorität (40%)
        base_score = item.raw_priority * self.WEIGHT_BASE_PRIORITY

        # 2. Dringlichkeit (25%)
        urgency_score, urgency_reasons = self._calculate_urgency_score(item)
        boost_reasons.extend(urgency_reasons)

        # 3. Benutzer-Präferenz (20%)
        user_pref_score, pref_reasons = self._calculate_user_preference_score(
            item, user_prefs
        )
        boost_reasons.extend(pref_reasons)

        # 4. Wichtigkeit (15%)
        importance_score, importance_reasons = await self._calculate_importance_score(
            item, db
        )
        boost_reasons.extend(importance_reasons)

        # Gesamt-Score berechnen
        ml_priority = (
            base_score
            + urgency_score
            + user_pref_score
            + importance_score
        )

        # Auf 0-100 begrenzen
        ml_priority = max(0.0, min(100.0, ml_priority))

        self.logger.debug(
            "item_scored",
            item_id=str(item.id),
            raw_priority=item.raw_priority,
            ml_priority=ml_priority,
            boost_count=len(boost_reasons),
        )

        return ScoredItem(
            item_id=item.id,
            raw_priority=item.raw_priority,
            ml_priority=ml_priority,
            boost_reasons=boost_reasons,
        )

    def _calculate_urgency_score(
        self,
        item: SmartInboxItem,
    ) -> tuple[float, List[str]]:
        """
        Berechnet Dringlichkeits-Score basierend auf Deadline.

        Returns:
            Tuple von (score, reasons)
        """
        reasons: List[str] = []
        max_score = 100.0 * self.WEIGHT_URGENCY

        if not item.deadline:
            return 0.0, reasons

        now = datetime.now(timezone.utc)
        time_until = item.deadline - now

        if time_until.total_seconds() < 0:
            # Überfällig
            score = max_score
            reasons.append("Überfällig - höchste Priorität")
        elif time_until.days == 0:
            # Heute
            score = max_score * 0.9
            reasons.append("Heute fällig")
        elif time_until.days == 1:
            # Morgen
            score = max_score * 0.7
            reasons.append("Morgen fällig")
        elif time_until.days <= 3:
            # In 2-3 Tagen
            score = max_score * 0.5
            reasons.append(f"In {time_until.days} Tagen fällig")
        elif time_until.days <= 7:
            # Diese Woche
            score = max_score * 0.3
            reasons.append("Diese Woche fällig")
        else:
            # Später
            score = max_score * 0.1
            reasons.append(f"Frist in {time_until.days} Tagen")

        return score, reasons

    def _calculate_user_preference_score(
        self,
        item: SmartInboxItem,
        user_prefs: UserPreferences,
    ) -> tuple[float, List[str]]:
        """
        Berechnet Benutzer-Präferenz-Score.

        Returns:
            Tuple von (score, reasons)
        """
        reasons: List[str] = []
        max_score = 100.0 * self.WEIGHT_USER_PREFERENCE

        # Kategorie-Gewichtung
        category = item.category or "unknown"
        category_weight = user_prefs.category_weights.get(category, 1.0)

        score = max_score * category_weight

        if category_weight > 1.2:
            reasons.append(f"Bevorzugte Kategorie: {category}")
        elif category_weight < 0.8:
            # Negative Boosts nicht in Reasons (verwirrt User)
            pass

        # Boost für bevorzugte Kategorien
        if category in user_prefs.preferred_categories[:3]:
            score += max_score * 0.2
            reasons.append("Top-3 Kategorie basierend auf Ihrem Verhalten")

        return score, reasons

    async def _calculate_importance_score(
        self,
        item: SmartInboxItem,
        db: AsyncSession,
    ) -> tuple[float, List[str]]:
        """
        Berechnet Wichtigkeits-Score basierend auf Kontext.

        Returns:
            Tuple von (score, reasons)
        """
        reasons: List[str] = []
        max_score = 100.0 * self.WEIGHT_IMPORTANCE

        score = 0.0

        # Betrag aus Context Data
        if "amount" in item.context_data:
            amount = float(item.context_data.get("amount", 0.0))
            if amount > 10000:
                score += max_score * 0.5
                reasons.append(f"Hoher Betrag: {amount:.2f} EUR")
            elif amount > 5000:
                score += max_score * 0.3
                reasons.append(f"Mittlerer Betrag: {amount:.2f} EUR")

        # Entity Risk Score (falls verfügbar)
        if item.entity_id:
            # TODO: Risk Score aus BusinessEntity laden
            # Für jetzt: Placeholder
            pass

        # Alert Severity
        if item.source_type == "alert":
            severity = item.context_data.get("severity", "medium")
            if severity == "critical":
                score += max_score * 0.6
                reasons.append("Kritischer Alert")
            elif severity == "high":
                score += max_score * 0.4
                reasons.append("Hoher Alert-Schweregrad")

        # Eskalation
        if item.context_data.get("escalated"):
            score += max_score * 0.3
            reasons.append("Eskaliert")

        return score, reasons

    async def recalculate_priorities(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
    ) -> int:
        """
        Neuberechnung aller Prioritäten für einen Benutzer.

        Sollte periodisch aufgerufen werden (z.B. stündlich).

        Args:
            user_id: Benutzer-ID
            company_id: Company-ID
            db: Async DB Session

        Returns:
            Anzahl aktualisierter Items
        """
        self.logger.info(
            "recalculating_priorities",
            user_id=str(user_id),
            company_id=str(company_id),
        )

        # Pending Items laden
        stmt = (
            select(SmartInboxItem)
            .where(
                and_(
                    SmartInboxItem.user_id == user_id,
                    SmartInboxItem.company_id == company_id,
                    SmartInboxItem.status == "pending",
                )
            )
        )

        result = await db.execute(stmt)
        items = result.scalars().all()

        if not items:
            self.logger.info("no_items_to_recalculate")
            return 0

        # Scores berechnen
        scored_items = await self.score(items, user_id, db)

        # Scores in DB schreiben
        update_count = 0
        for scored in scored_items:
            for item in items:
                if item.id == scored.item_id:
                    item.ml_priority = scored.ml_priority
                    update_count += 1
                    break

        await db.commit()

        self.logger.info(
            "recalculation_complete",
            updated_count=update_count,
        )

        return update_count
