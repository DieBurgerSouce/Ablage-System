"""Financial Goals Service für Sparziele und Progress-Tracking.

Enterprise Feature: Finanzielle Ziele mit:
- Sparziele definieren
- Automatische Fortschrittsverfolgung
- Prognosen basierend auf bisherigem Tempo
- Beitrags-Tracking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.core.datetime_utils import utc_now
from decimal import Decimal
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    FinancialGoal,
    FinancialGoalContribution,
    FinancialGoalStatus,
    FinancialGoalType,
    PrivatSpace,
)

logger = logging.getLogger(__name__)


@dataclass
class GoalProgress:
    """Fortschrittsberechnung für ein Finanzziel."""

    current_value: Decimal
    target_value: Decimal
    progress_percent: float
    remaining_amount: Decimal
    months_remaining: int
    monthly_savings_required: Decimal
    is_on_track: bool
    projected_completion_date: Optional[date]
    average_monthly_contribution: Decimal


@dataclass
class GoalSummary:
    """Zusammenfassung aller Finanzziele."""

    total_goals: int
    active_goals: int
    completed_goals: int
    total_target_value: Decimal
    total_current_value: Decimal
    overall_progress_percent: float
    goals_on_track: int
    goals_at_risk: int


class FinancialGoalsService:
    """Service für Finanzziel-Management und Progress-Tracking.

    Ermöglicht das Setzen von Sparzielen mit automatischer
    Fortschrittsverfolgung und Prognosen.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Financial Goals Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    # ==========================================================================
    # CRUD Operationen
    # ==========================================================================

    async def create_goal(
        self,
        space_id: UUID,
        name: str,
        target_value: Decimal,
        target_date: date,
        goal_type: str = FinancialGoalType.CUSTOM.value,
        description: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
        priority: int = 1,
        initial_value: Decimal = Decimal("0"),
    ) -> FinancialGoal:
        """Erstellt ein neues Finanzziel.

        Args:
            space_id: ID des Privat-Space
            name: Name des Ziels
            target_value: Zielbetrag
            target_date: Zieldatum
            goal_type: Typ des Ziels
            description: Optionale Beschreibung
            icon: Icon für UI
            color: Farbe für UI
            priority: Priorität (1=hoechste)
            initial_value: Startwert (bereits angespart)

        Returns:
            Erstelltes FinancialGoal
        """
        # Progress berechnen
        progress_percent = Decimal("0")
        if target_value > 0:
            progress_percent = (initial_value / target_value) * 100

        # Monate bis Zieldatum
        today = date.today()
        months_remaining = (target_date.year - today.year) * 12 + (
            target_date.month - today.month
        )
        months_remaining = max(months_remaining, 0)

        # Erforderliche monatliche Sparrate
        remaining_amount = target_value - initial_value
        monthly_savings_required = Decimal("0")
        if months_remaining > 0:
            monthly_savings_required = remaining_amount / months_remaining

        goal = FinancialGoal(
            space_id=space_id,
            name=name,
            description=description,
            goal_type=goal_type,
            icon=icon or "Target",
            color=color or "#10B981",
            target_value=target_value,
            target_date=target_date,
            current_value=initial_value,
            progress_percent=progress_percent,
            monthly_savings_required=monthly_savings_required,
            months_remaining=months_remaining,
            is_on_track=True,
            priority=priority,
            status=FinancialGoalStatus.ACTIVE.value,
        )

        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)

        logger.info(f"Finanzziel '{name}' erstellt: Ziel {target_value} EUR bis {target_date}")

        return goal

    async def get_goal(
        self,
        goal_id: UUID,
        space_id: Optional[UUID] = None,
    ) -> Optional[FinancialGoal]:
        """Holt ein Finanzziel nach ID.

        SECURITY: space_id SOLLTE für Multi-Tenant Isolation übergeben werden.
        Wenn space_id gegeben, wird zusätzlich validiert.

        Args:
            goal_id: ID des Ziels
            space_id: Optional: ID des Privat-Space für Multi-Tenant Validierung

        Returns:
            FinancialGoal oder None
        """
        query = select(FinancialGoal).where(FinancialGoal.id == goal_id)

        # SECURITY: space_id Filter für Multi-Tenant Isolation
        if space_id is not None:
            query = query.where(FinancialGoal.space_id == space_id)

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_goals_for_space(
        self,
        space_id: UUID,
        status_filter: Optional[str] = None,
        include_completed: bool = False,
    ) -> Sequence[FinancialGoal]:
        """Holt alle Finanzziele eines Spaces.

        Args:
            space_id: ID des Privat-Space
            status_filter: Optional: Nur bestimmten Status
            include_completed: Auch abgeschlossene Ziele?

        Returns:
            Liste von FinancialGoals
        """
        query = select(FinancialGoal).where(FinancialGoal.space_id == space_id)

        if status_filter:
            query = query.where(FinancialGoal.status == status_filter)
        elif not include_completed:
            query = query.where(
                FinancialGoal.status.in_([
                    FinancialGoalStatus.ACTIVE.value,
                    FinancialGoalStatus.PAUSED.value,
                ])
            )

        query = query.order_by(FinancialGoal.priority.asc(), FinancialGoal.target_date.asc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def update_goal(
        self,
        goal_id: UUID,
        space_id: Optional[UUID] = None,
        **kwargs: object,
    ) -> Optional[FinancialGoal]:
        """Aktualisiert ein Finanzziel.

        SECURITY: space_id SOLLTE für Multi-Tenant Isolation übergeben werden.

        Args:
            goal_id: ID des Ziels
            space_id: Optional: ID des Privat-Space für Multi-Tenant Validierung
            **kwargs: Zu aktualisierende Felder

        Returns:
            Aktualisiertes FinancialGoal oder None
        """
        goal = await self.get_goal(goal_id, space_id=space_id)
        if not goal:
            return None

        for key, value in kwargs.items():
            if hasattr(goal, key):
                setattr(goal, key, value)

        # Progress neu berechnen falls target_value oder current_value geändert
        if "target_value" in kwargs or "current_value" in kwargs:
            await self._recalculate_progress(goal)

        goal.updated_at = utc_now()

        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def delete_goal(
        self,
        goal_id: UUID,
        space_id: Optional[UUID] = None,
    ) -> bool:
        """Löscht ein Finanzziel.

        SECURITY: space_id SOLLTE für Multi-Tenant Isolation übergeben werden.

        Args:
            goal_id: ID des Ziels
            space_id: Optional: ID des Privat-Space für Multi-Tenant Validierung

        Returns:
            True wenn erfolgreich
        """
        goal = await self.get_goal(goal_id, space_id=space_id)
        if not goal:
            logger.warning(
                "financial_goal_delete_failed",
                goal_id=str(goal_id),
                space_id=str(space_id) if space_id else "not_provided",
                reason="not_found_or_wrong_space",
            )
            return False

        await self.db.delete(goal)
        await self.db.commit()

        logger.info(f"Finanzziel {goal_id} gelöscht")
        return True

    # ==========================================================================
    # Beitrags-Management
    # ==========================================================================

    async def add_contribution(
        self,
        goal_id: UUID,
        amount: Decimal,
        space_id: Optional[UUID] = None,
        contribution_date: Optional[date] = None,
        source_type: str = "manual",
        source_description: Optional[str] = None,
        note: Optional[str] = None,
        created_by_id: Optional[UUID] = None,
    ) -> Optional[FinancialGoalContribution]:
        """Fuegt einen Beitrag zu einem Finanzziel hinzu.

        SECURITY: space_id SOLLTE für Multi-Tenant Isolation übergeben werden.

        Args:
            goal_id: ID des Ziels
            amount: Beitragsbetrag
            space_id: Optional: ID des Privat-Space für Multi-Tenant Validierung
            contribution_date: Datum (Standard: heute)
            source_type: Quelle (manual, automatic, transfer)
            source_description: Beschreibung der Quelle
            note: Optionale Notiz
            created_by_id: ID des erstellenden Users

        Returns:
            Erstellter Beitrag oder None wenn Ziel nicht gefunden
        """
        # SECURITY: Validiere dass Goal zum Space gehoert
        goal = await self.get_goal(goal_id, space_id=space_id)
        if not goal:
            logger.warning(
                "add_contribution_failed",
                goal_id=str(goal_id),
                space_id=str(space_id) if space_id else "not_provided",
                reason="goal_not_found_or_wrong_space",
            )
            return None

        if contribution_date is None:
            contribution_date = date.today()

        contribution = FinancialGoalContribution(
            goal_id=goal_id,
            amount=amount,
            contribution_date=contribution_date,
            source_type=source_type,
            source_description=source_description,
            note=note,
            created_by_id=created_by_id,
        )

        self.db.add(contribution)

        # Ziel aktualisieren
        if goal:
            goal.current_value = (goal.current_value or Decimal("0")) + amount
            await self._recalculate_progress(goal)

            # Prüfen ob Ziel erreicht
            if goal.current_value >= goal.target_value:
                goal.status = FinancialGoalStatus.COMPLETED.value
                goal.completed_at = utc_now()
                logger.info(f"Finanzziel '{goal.name}' erreicht!")

        await self.db.commit()
        await self.db.refresh(contribution)

        logger.info(f"Beitrag von {amount} EUR zu Ziel {goal_id} hinzugefuegt")

        return contribution

    async def get_contributions(
        self,
        goal_id: UUID,
        space_id: Optional[UUID] = None,
        limit: int = 100,
    ) -> Sequence[FinancialGoalContribution]:
        """Holt alle Beitraege zu einem Finanzziel.

        SECURITY: space_id SOLLTE für Multi-Tenant Isolation übergeben werden.

        Args:
            goal_id: ID des Ziels
            space_id: Optional: ID des Privat-Space für Multi-Tenant Validierung
            limit: Max Anzahl

        Returns:
            Liste von Contributions (leer wenn Goal nicht gefunden/falsche Space)
        """
        # SECURITY: Validiere dass Goal zum Space gehoert (wenn space_id gegeben)
        if space_id is not None:
            goal = await self.get_goal(goal_id, space_id=space_id)
            if not goal:
                logger.warning(
                    "get_contributions_unauthorized",
                    goal_id=str(goal_id),
                    space_id=str(space_id),
                    reason="goal_not_found_or_wrong_space",
                )
                return []

        result = await self.db.execute(
            select(FinancialGoalContribution)
            .where(FinancialGoalContribution.goal_id == goal_id)
            .order_by(FinancialGoalContribution.contribution_date.desc())
            .limit(limit)
        )
        return result.scalars().all()

    # ==========================================================================
    # Progress-Berechnung
    # ==========================================================================

    async def _recalculate_progress(self, goal: FinancialGoal) -> None:
        """Berechnet den Fortschritt eines Ziels neu.

        Args:
            goal: Das Finanzziel
        """
        today = date.today()

        # Progress Prozent
        if goal.target_value and goal.target_value > 0:
            goal.progress_percent = (
                (goal.current_value or Decimal("0")) / goal.target_value * 100
            )
        else:
            goal.progress_percent = Decimal("0")

        # Verbleibende Monate
        months_remaining = (goal.target_date.year - today.year) * 12 + (
            goal.target_date.month - today.month
        )
        goal.months_remaining = max(months_remaining, 0)

        # Erforderliche monatliche Sparrate
        remaining = max(goal.target_value - (goal.current_value or Decimal("0")), Decimal("0"))
        if goal.months_remaining > 0:
            goal.monthly_savings_required = remaining / goal.months_remaining
        else:
            goal.monthly_savings_required = remaining

        # On-Track Berechnung basierend auf bisherigem Tempo
        avg_monthly = await self._calculate_average_monthly_contribution(goal.id)

        if goal.months_remaining > 0 and goal.monthly_savings_required:
            goal.is_on_track = avg_monthly >= goal.monthly_savings_required * Decimal("0.9")
        else:
            goal.is_on_track = goal.current_value >= goal.target_value

        # Projiziertes Completion Date
        if avg_monthly > 0 and remaining > 0:
            months_needed = int(remaining / avg_monthly) + 1
            goal.projected_completion_date = today + timedelta(days=months_needed * 30)
        else:
            goal.projected_completion_date = None

        goal.last_auto_update = utc_now()

    async def _calculate_average_monthly_contribution(
        self, goal_id: UUID
    ) -> Decimal:
        """Berechnet den durchschnittlichen monatlichen Beitrag.

        Args:
            goal_id: ID des Ziels

        Returns:
            Durchschnittlicher Beitrag pro Monat
        """
        # Letzte 6 Monate betrachten
        cutoff = date.today() - timedelta(days=180)

        result = await self.db.execute(
            select(func.sum(FinancialGoalContribution.amount)).where(
                and_(
                    FinancialGoalContribution.goal_id == goal_id,
                    FinancialGoalContribution.contribution_date >= cutoff,
                )
            )
        )
        total = result.scalar() or Decimal("0")

        # Durch 6 Monate teilen
        return Decimal(str(total)) / 6

    async def calculate_goal_progress(
        self,
        goal_id: UUID,
        space_id: Optional[UUID] = None,
    ) -> GoalProgress:
        """Berechnet detaillierten Fortschritt für ein Ziel.

        SECURITY: space_id SOLLTE für Multi-Tenant Isolation übergeben werden.

        Args:
            goal_id: ID des Ziels
            space_id: Optional: ID des Privat-Space für Multi-Tenant Validierung

        Returns:
            GoalProgress mit allen Details

        Raises:
            ValueError: Wenn Ziel nicht gefunden oder falscher Space
        """
        goal = await self.get_goal(goal_id, space_id=space_id)
        if not goal:
            logger.warning(
                "calculate_goal_progress_failed",
                goal_id=str(goal_id),
                space_id=str(space_id) if space_id else "not_provided",
                reason="goal_not_found_or_wrong_space",
            )
            raise ValueError(f"Ziel {goal_id} nicht gefunden")

        avg_monthly = await self._calculate_average_monthly_contribution(goal_id)

        remaining = max(goal.target_value - (goal.current_value or Decimal("0")), Decimal("0"))
        today = date.today()
        months_remaining = (goal.target_date.year - today.year) * 12 + (
            goal.target_date.month - today.month
        )
        months_remaining = max(months_remaining, 0)

        monthly_required = Decimal("0")
        if months_remaining > 0:
            monthly_required = remaining / months_remaining

        progress_percent = float(goal.progress_percent or 0)

        # Projiziertes Datum
        projected_date = None
        if avg_monthly > 0 and remaining > 0:
            months_needed = int(remaining / avg_monthly) + 1
            projected_date = today + timedelta(days=months_needed * 30)

        is_on_track = avg_monthly >= monthly_required * Decimal("0.9") if monthly_required > 0 else True

        return GoalProgress(
            current_value=goal.current_value or Decimal("0"),
            target_value=goal.target_value,
            progress_percent=progress_percent,
            remaining_amount=remaining,
            months_remaining=months_remaining,
            monthly_savings_required=monthly_required,
            is_on_track=is_on_track,
            projected_completion_date=projected_date,
            average_monthly_contribution=avg_monthly,
        )

    # ==========================================================================
    # Zusammenfassungen
    # ==========================================================================

    async def get_goals_summary(self, space_id: UUID) -> GoalSummary:
        """Erstellt eine Zusammenfassung aller Finanzziele.

        Args:
            space_id: ID des Privat-Space

        Returns:
            GoalSummary mit Statistiken
        """
        goals = await self.get_goals_for_space(space_id, include_completed=True)

        total_goals = len(goals)
        active_goals = sum(1 for g in goals if g.status == FinancialGoalStatus.ACTIVE.value)
        completed_goals = sum(1 for g in goals if g.status == FinancialGoalStatus.COMPLETED.value)

        total_target = sum(g.target_value or Decimal("0") for g in goals)
        total_current = sum(g.current_value or Decimal("0") for g in goals)

        overall_progress = 0.0
        if total_target > 0:
            overall_progress = float(total_current / total_target * 100)

        active = [g for g in goals if g.status == FinancialGoalStatus.ACTIVE.value]
        goals_on_track = sum(1 for g in active if g.is_on_track)
        goals_at_risk = len(active) - goals_on_track

        return GoalSummary(
            total_goals=total_goals,
            active_goals=active_goals,
            completed_goals=completed_goals,
            total_target_value=total_target,
            total_current_value=total_current,
            overall_progress_percent=overall_progress,
            goals_on_track=goals_on_track,
            goals_at_risk=goals_at_risk,
        )

    # ==========================================================================
    # Batch-Operationen
    # ==========================================================================

    async def recalculate_all_goals(self, space_id: UUID) -> int:
        """Berechnet alle Ziele eines Spaces neu.

        Args:
            space_id: ID des Privat-Space

        Returns:
            Anzahl der aktualisierten Ziele
        """
        goals = await self.get_goals_for_space(space_id)
        count = 0

        for goal in goals:
            try:
                await self._recalculate_progress(goal)
                count += 1
            except Exception as e:
                logger.error(f"Fehler bei Neuberechnung von Ziel {goal.id}: {e}")
                continue

        await self.db.commit()

        logger.info(f"{count} Finanzziele für Space {space_id} neu berechnet")
        return count

    async def recalculate_all_spaces_goals(self) -> int:
        """Berechnet alle Ziele aller Spaces neu.

        Wird typischerweise täglich via Celery Beat ausgeführt.

        Returns:
            Anzahl der aktualisierten Ziele
        """
        result = await self.db.execute(
            select(PrivatSpace.id).where(PrivatSpace.deleted_at.is_(None))
        )
        space_ids = result.scalars().all()

        total_count = 0
        for space_id in space_ids:
            try:
                count = await self.recalculate_all_goals(space_id)
                total_count += count
            except Exception as e:
                logger.error(f"Fehler bei Space {space_id}: {e}")
                continue

        logger.info(f"Insgesamt {total_count} Finanzziele neu berechnet")
        return total_count

    async def get_goals_at_risk(self, space_id: Optional[UUID] = None) -> Sequence[FinancialGoal]:
        """Holt alle gefaehrdeten Ziele.

        Args:
            space_id: Optional: Nur für bestimmten Space

        Returns:
            Liste von gefaehrdeten FinancialGoals
        """
        query = (
            select(FinancialGoal)
            .where(
                and_(
                    FinancialGoal.status == FinancialGoalStatus.ACTIVE.value,
                    FinancialGoal.is_on_track == False,
                )
            )
            .order_by(FinancialGoal.target_date.asc())
        )

        if space_id:
            query = query.where(FinancialGoal.space_id == space_id)

        result = await self.db.execute(query)
        return result.scalars().all()
