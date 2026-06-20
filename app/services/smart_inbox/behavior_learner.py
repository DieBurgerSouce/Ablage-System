"""Smart Inbox Behavior Learner - Lernt aus Benutzer-Verhalten.

Analysiert Benutzer-Aktionen um:
- Bevorzugte Kategorien zu identifizieren
- Durchschnittliche Reaktionszeiten zu tracken
- Completion/Dismiss Raten zu berechnen
- Kategorie-Gewichtungen zu bestimmen
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc, case

from app.db.models import UserBehaviorLog, SmartInboxItem

logger = structlog.get_logger(__name__)


@dataclass
class UserPreferences:
    """Benutzer-Präferenzen basierend auf Verhalten."""
    preferred_categories: List[str] = field(default_factory=list)
    avg_response_time_ms: int = 0
    completion_rate: float = 0.0
    dismiss_rate: float = 0.0
    category_weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class Insight:
    """Verhaltens-Insight für Dashboard."""
    title: str  # Deutscher Titel
    description: str  # Deutsche Beschreibung
    metric: str
    value: float
    trend: str  # up, down, stable


class BehaviorLearner:
    """Lernt aus Benutzer-Verhalten zur Verbesserung der Priorisierung."""

    def __init__(self) -> None:
        """Initialisiert den Behavior Learner."""
        self.logger = logger.bind(service="behavior_learner")

    async def log_action(
        self,
        user_id: UUID,
        inbox_item_id: UUID,
        action: str,
        time_spent_ms: int,
        db: AsyncSession,
        source_type: Optional[str] = None,
        context_page: Optional[str] = None,
    ) -> None:
        """
        Protokolliert eine Benutzer-Aktion.

        Args:
            user_id: Benutzer-ID
            inbox_item_id: Smart Inbox Item ID
            action: Aktion (viewed, clicked, dismissed, completed, snoozed)
            time_spent_ms: Verbrachte Zeit in Millisekunden
            db: Async DB Session
            source_type: Optional - Typ der Quelle
            context_page: Optional - Seite/Kontext der Aktion
        """
        self.logger.debug(
            "logging_action",
            user_id=str(user_id),
            inbox_item_id=str(inbox_item_id),
            action=action,
            time_spent_ms=time_spent_ms,
        )

        # Inbox Item laden für company_id
        stmt = select(SmartInboxItem).where(SmartInboxItem.id == inbox_item_id)
        result = await db.execute(stmt)
        inbox_item = result.scalar_one_or_none()

        if not inbox_item:
            self.logger.error(
                "inbox_item_not_found",
                inbox_item_id=str(inbox_item_id),
            )
            return

        # Behavior Log erstellen
        behavior_log = UserBehaviorLog(
            user_id=user_id,
            company_id=inbox_item.company_id,
            inbox_item_id=inbox_item_id,
            action=action,
            source_type=source_type or inbox_item.source_type,
            time_spent_ms=time_spent_ms,
            context_page=context_page,
        )

        db.add(behavior_log)
        await db.commit()

        self.logger.info(
            "action_logged",
            action=action,
            time_spent_ms=time_spent_ms,
        )

    async def get_user_preferences(
        self,
        user_id: UUID,
        db: AsyncSession,
        lookback_days: int = 30,
    ) -> UserPreferences:
        """
        Berechnet Benutzer-Präferenzen aus Verhaltens-Logs.

        Args:
            user_id: Benutzer-ID
            db: Async DB Session
            lookback_days: Anzahl Tage für Analyse (default: 30)

        Returns:
            UserPreferences
        """
        self.logger.debug(
            "calculating_user_preferences",
            user_id=str(user_id),
            lookback_days=lookback_days,
        )

        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # Behavior Logs laden
        stmt = (
            select(UserBehaviorLog)
            .where(
                and_(
                    UserBehaviorLog.user_id == user_id,
                    UserBehaviorLog.created_at >= since,
                )
            )
            .order_by(UserBehaviorLog.created_at.desc())
        )

        result = await db.execute(stmt)
        logs = result.scalars().all()

        if not logs:
            self.logger.info("no_behavior_data", user_id=str(user_id))
            return UserPreferences()

        # Bevorzugte Kategorien ermitteln
        preferred_categories = await self._calculate_preferred_categories(
            user_id, db, since
        )

        # Durchschnittliche Reaktionszeit
        avg_response_time_ms = self._calculate_avg_response_time(logs)

        # Completion/Dismiss Raten
        completion_rate = self._calculate_completion_rate(logs)
        dismiss_rate = self._calculate_dismiss_rate(logs)

        # Kategorie-Gewichtungen
        category_weights = await self._calculate_category_weights(user_id, db, since)

        prefs = UserPreferences(
            preferred_categories=preferred_categories,
            avg_response_time_ms=avg_response_time_ms,
            completion_rate=completion_rate,
            dismiss_rate=dismiss_rate,
            category_weights=category_weights,
        )

        self.logger.info(
            "user_preferences_calculated",
            user_id=str(user_id),
            preferred_categories=preferred_categories,
            completion_rate=completion_rate,
        )

        return prefs

    async def _calculate_preferred_categories(
        self,
        user_id: UUID,
        db: AsyncSession,
        since: datetime,
    ) -> List[str]:
        """Ermittelt bevorzugte Kategorien basierend auf completed-Aktionen."""
        stmt = (
            select(
                SmartInboxItem.category,
                func.count(UserBehaviorLog.id).label("count"),
            )
            .select_from(UserBehaviorLog)
            .join(SmartInboxItem, UserBehaviorLog.inbox_item_id == SmartInboxItem.id)
            .where(
                and_(
                    UserBehaviorLog.user_id == user_id,
                    UserBehaviorLog.created_at >= since,
                    UserBehaviorLog.action == "completed",
                    SmartInboxItem.category.isnot(None),
                )
            )
            .group_by(SmartInboxItem.category)
            .order_by(desc("count"))
            .limit(5)
        )

        result = await db.execute(stmt)
        rows = result.all()

        return [row.category for row in rows if row.category]

    def _calculate_avg_response_time(self, logs: List[UserBehaviorLog]) -> int:
        """Berechnet durchschnittliche Reaktionszeit."""
        if not logs:
            return 0

        total_time = sum(log.time_spent_ms for log in logs if log.time_spent_ms)
        count = len([log for log in logs if log.time_spent_ms > 0])

        if count == 0:
            return 0

        return total_time // count

    def _calculate_completion_rate(self, logs: List[UserBehaviorLog]) -> float:
        """Berechnet Completion Rate."""
        if not logs:
            return 0.0

        total_actions = len(logs)
        completed = len([log for log in logs if log.action == "completed"])

        return completed / total_actions if total_actions > 0 else 0.0

    def _calculate_dismiss_rate(self, logs: List[UserBehaviorLog]) -> float:
        """Berechnet Dismiss Rate."""
        if not logs:
            return 0.0

        total_actions = len(logs)
        dismissed = len([log for log in logs if log.action == "dismissed"])

        return dismissed / total_actions if total_actions > 0 else 0.0

    async def _calculate_category_weights(
        self,
        user_id: UUID,
        db: AsyncSession,
        since: datetime,
    ) -> Dict[str, float]:
        """
        Berechnet Gewichtungen für Kategorien basierend auf Verhalten.

        Kategorien mit hoher Completion Rate bekommen höhere Gewichtung.
        """
        stmt = (
            select(
                SmartInboxItem.category,
                func.count(UserBehaviorLog.id).label("total"),
                func.sum(
                    case(
                        (UserBehaviorLog.action == "completed", 1),
                        else_=0,
                    )
                ).label("completed"),
                func.sum(
                    case(
                        (UserBehaviorLog.action == "dismissed", 1),
                        else_=0,
                    )
                ).label("dismissed"),
            )
            .select_from(UserBehaviorLog)
            .join(SmartInboxItem, UserBehaviorLog.inbox_item_id == SmartInboxItem.id)
            .where(
                and_(
                    UserBehaviorLog.user_id == user_id,
                    UserBehaviorLog.created_at >= since,
                    SmartInboxItem.category.isnot(None),
                )
            )
            .group_by(SmartInboxItem.category)
        )

        result = await db.execute(stmt)
        rows = result.all()

        weights: Dict[str, float] = {}

        for row in rows:
            category = row.category
            total = row.total or 1
            completed = row.completed or 0
            dismissed = row.dismissed or 0

            # Gewichtung basierend auf Completion Rate
            completion_rate = completed / total
            dismiss_rate = dismissed / total

            # Höhere Gewichtung für oft abgeschlossene Kategorien
            # Niedrigere Gewichtung für oft verworfene Kategorien
            weight = 1.0 + (completion_rate * 0.5) - (dismiss_rate * 0.3)

            # Auf sinnvollen Bereich begrenzen (0.5 - 1.5)
            weight = max(0.5, min(1.5, weight))

            weights[category] = weight

        return weights

    async def get_insights(
        self,
        user_id: UUID,
        company_id: UUID,
        db: AsyncSession,
        lookback_days: int = 30,
    ) -> List[Insight]:
        """
        Generiert Verhaltens-Insights für Dashboard.

        Args:
            user_id: Benutzer-ID
            company_id: Company-ID
            db: Async DB Session
            lookback_days: Anzahl Tage für Analyse

        Returns:
            Liste von Insights
        """
        self.logger.debug(
            "generating_insights",
            user_id=str(user_id),
            lookback_days=lookback_days,
        )

        insights: List[Insight] = []

        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        half_period = since + timedelta(days=lookback_days // 2)

        # Preferences laden
        prefs = await self.get_user_preferences(user_id, db, lookback_days)

        # Insight 1: Completion Rate
        # Trend berechnen (erste vs. zweite Hälfte)
        first_half_completion = await self._get_completion_rate_for_period(
            user_id, db, since, half_period
        )
        second_half_completion = await self._get_completion_rate_for_period(
            user_id, db, half_period, datetime.now(timezone.utc)
        )

        completion_trend = self._calculate_trend(
            first_half_completion, second_half_completion
        )

        insights.append(
            Insight(
                title="Erledigungsrate",
                description=f"Sie schließen {prefs.completion_rate:.0%} Ihrer Aufgaben ab",
                metric="completion_rate",
                value=prefs.completion_rate,
                trend=completion_trend,
            )
        )

        # Insight 2: Durchschnittliche Reaktionszeit
        response_trend = self._calculate_response_trend(prefs.avg_response_time_ms)
        insights.append(
            Insight(
                title="Reaktionszeit",
                description=f"Durchschnittlich {prefs.avg_response_time_ms // 1000} Sekunden pro Aufgabe",
                metric="avg_response_time",
                value=float(prefs.avg_response_time_ms),
                trend=response_trend,
            )
        )

    def _calculate_response_trend(self, current_ms: int) -> str:
        """Berechnet Trend für Reaktionszeit."""
        # Unter 5 Sekunden = sehr gut
        if current_ms < 5000:
            return "improving"
        # Unter 30 Sekunden = normal
        elif current_ms < 30000:
            return "stable"
        # Über 30 Sekunden = langsam
        else:
            return "declining"

    def _calculate_completion_trend(self, rate: float) -> str:
        """Berechnet Trend für Completion Rate."""
        if rate >= 0.9:
            return "improving"
        elif rate >= 0.7:
            return "stable"
        else:
            return "declining"

        # Insight 3: Bevorzugte Kategorie
        if prefs.preferred_categories:
            top_category = prefs.preferred_categories[0]
            insights.append(
                Insight(
                    title="Top-Kategorie",
                    description=f"Sie arbeiten am häufigsten mit '{top_category}' Aufgaben",
                    metric="top_category",
                    value=1.0,
                    trend="stable",
                )
            )

        self.logger.info(
            "insights_generated",
            user_id=str(user_id),
            insight_count=len(insights),
        )

        return insights

    async def _get_completion_rate_for_period(
        self,
        user_id: UUID,
        db: AsyncSession,
        start: datetime,
        end: datetime,
    ) -> float:
        """Berechnet Completion Rate für eine Periode."""
        stmt = (
            select(
                func.count(UserBehaviorLog.id).label("total"),
                func.sum(
                    func.case(
                        (UserBehaviorLog.action == "completed", 1),
                        else_=0,
                    )
                ).label("completed"),
            )
            .where(
                and_(
                    UserBehaviorLog.user_id == user_id,
                    UserBehaviorLog.created_at >= start,
                    UserBehaviorLog.created_at < end,
                )
            )
        )

        result = await db.execute(stmt)
        row = result.one()

        total = row.total or 0
        completed = row.completed or 0

        return completed / total if total > 0 else 0.0

    def _calculate_trend(self, first_value: float, second_value: float) -> str:
        """
        Berechnet Trend aus zwei Werten.

        Returns:
            "up", "down", or "stable"
        """
        diff = second_value - first_value

        if abs(diff) < 0.05:  # <5% Unterschied
            return "stable"
        elif diff > 0:
            return "up"
        else:
            return "down"
