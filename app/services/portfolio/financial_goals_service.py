"""Financial Goals Service fuer Ziel-Management.

Verwaltet finanzielle Ziele:
- Ziel-Erstellung (Altersvorsorge, Notgroschen, Immobilie, etc.)
- Fortschritts-Tracking
- Prognosen und Empfehlungen
- Auto-Completion bei Zielerreichung
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, timedelta
from typing import Optional, Any, List, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FinancialGoal as FinancialGoalModel


@dataclass
class FinancialGoal:
    """Finanzielles Ziel."""

    id: UUID
    name: str
    goal_type: str  # retirement, emergency_fund, property, education, debt_free
    target_value: Decimal
    target_date: date
    current_value: Decimal
    status: str  # active, paused, completed, cancelled


@dataclass
class GoalProgress:
    """Fortschritt eines Ziels."""

    goal_id: UUID
    progress_percent: Decimal
    remaining_amount: Decimal
    months_remaining: int
    monthly_savings_required: Decimal
    is_on_track: bool
    projected_completion_date: Optional[date]


class FinancialGoalsService:
    """Service fuer Finanzielle Ziele.

    Verwaltet Erstellung, Tracking und Prognosen
    fuer verschiedene Arten von finanziellen Zielen.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialisiert den Service.

        Args:
            db: Async Database Session
        """
        self.db = db

    async def create_goal(
        self,
        space_id: UUID,
        name: str,
        goal_type: str,
        target_value: Decimal,
        target_date: date,
        initial_value: Decimal = Decimal("0"),
    ) -> FinancialGoalModel:
        """Erstellt ein neues finanzielles Ziel.

        Args:
            space_id: UUID des Privat-Space
            name: Name des Ziels
            goal_type: Art des Ziels
            target_value: Zielwert
            target_date: Zieldatum
            initial_value: Aktueller Startwert

        Returns:
            Erstelltes FinancialGoalModel
        """
        # Progress berechnen
        progress_percent = self._calc_progress_percent(initial_value, target_value)
        months_remaining = self._calc_months_remaining(target_date)
        monthly_required = self._calc_monthly_savings_required(
            target_value - initial_value, months_remaining
        )

        goal = FinancialGoalModel(
            space_id=space_id,
            name=name,
            goal_type=goal_type,
            target_value=target_value,
            target_date=target_date,
            current_value=initial_value,
            progress_percent=progress_percent,
            months_remaining=months_remaining,
            monthly_savings_required=monthly_required,
            is_on_track=True,
            status="active",
        )

        # In DB speichern
        self.db.add(goal)
        await self.db.commit()
        await self.db.refresh(goal)

        return goal

    async def update_progress(self, goal_id: UUID, new_value: Decimal) -> GoalProgress:
        """Aktualisiert den Fortschritt eines Ziels.

        Args:
            goal_id: UUID des Ziels
            new_value: Neuer aktueller Wert

        Returns:
            Aktualisierter GoalProgress
        """
        goal = await self._get_goal(goal_id)
        goal.current_value = new_value

        # Progress berechnen
        progress_percent = self._calc_progress_percent(new_value, goal.target_value)
        goal.progress_percent = progress_percent

        # Auto-Complete wenn Ziel erreicht
        if new_value >= goal.target_value and goal.status == "active":
            goal.status = "completed"

        await self.db.commit()

        return GoalProgress(
            goal_id=goal_id,
            progress_percent=progress_percent,
            remaining_amount=max(goal.target_value - new_value, Decimal("0")),
            months_remaining=self._calc_months_remaining(goal.target_date),
            monthly_savings_required=self._calc_monthly_savings_required(
                goal.target_value - new_value,
                self._calc_months_remaining(goal.target_date)
            ),
            is_on_track=self._calc_is_on_track(goal),
            projected_completion_date=self._calc_projected_completion_date(goal),
        )

    async def complete_goal(self, goal_id: UUID) -> None:
        """Markiert ein Ziel als abgeschlossen.

        Args:
            goal_id: UUID des Ziels
        """
        goal = await self._get_goal(goal_id)
        goal.status = "completed"
        await self.db.commit()

    async def get_goals_summary(self, space_id: UUID) -> Dict[str, Any]:
        """Erstellt eine Zusammenfassung aller Ziele.

        Args:
            space_id: UUID des Privat-Space

        Returns:
            Dictionary mit Zusammenfassung
        """
        goals = await self._get_all_goals(space_id)

        active_goals = [g for g in goals if g.status == "active"]
        completed_goals = [g for g in goals if g.status == "completed"]

        return {
            "total_goals": len(goals),
            "active_goals": len(active_goals),
            "completed_goals": len(completed_goals),
            "on_track_count": sum(1 for g in goals if getattr(g, 'is_on_track', True)),
            "total_target_value": sum(g.target_value for g in goals),
            "total_current_value": sum(g.current_value for g in goals),
        }

    def _calc_progress_percent(self, current: Decimal, target: Decimal) -> Decimal:
        """Berechnet den Fortschritt in Prozent."""
        if target <= 0:
            return Decimal("100.00")

        result = (current / target) * 100
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_months_remaining(self, target_date: date) -> int:
        """Berechnet die verbleibenden Monate bis zum Zieldatum."""
        today = date.today()
        if target_date <= today:
            return 0

        delta = target_date - today
        return max(int(delta.days / 30), 0)

    def _calc_monthly_savings_required(self, remaining: Decimal, months: int) -> Decimal:
        """Berechnet die benoetigte monatliche Sparrate."""
        if remaining <= 0:
            return Decimal("0")

        if months <= 0:
            return remaining  # Alles sofort noetig

        result = remaining / Decimal(str(months))
        return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calc_is_on_track(self, goal: Any) -> bool:
        """Prueft ob das Ziel auf Kurs ist."""
        if goal.current_value >= goal.target_value:
            return True

        # Berechne erwarteten Fortschritt basierend auf Zeit
        created_at = getattr(goal, 'created_at', date.today() - timedelta(days=365))
        if isinstance(created_at, date):
            start_date = created_at
        else:
            start_date = created_at.date() if hasattr(created_at, 'date') else date.today()

        total_days = (goal.target_date - start_date).days
        elapsed_days = (date.today() - start_date).days

        if total_days <= 0 or elapsed_days <= 0:
            return True

        expected_progress = (Decimal(str(elapsed_days)) / Decimal(str(total_days))) * 100
        actual_progress = self._calc_progress_percent(goal.current_value, goal.target_value)

        # Auf Kurs wenn aktueller Fortschritt >= erwarteter Fortschritt
        return actual_progress >= expected_progress

    def _calc_projected_completion_date(self, goal: Any) -> Optional[date]:
        """Berechnet das voraussichtliche Abschlussdatum."""
        if goal.current_value >= goal.target_value:
            return date.today()

        if goal.current_value <= 0:
            return None  # Kann nicht berechnet werden

        # Berechne Sparrate basierend auf bisherigem Fortschritt
        created_at = getattr(goal, 'created_at', date.today() - timedelta(days=365))
        if isinstance(created_at, date):
            start_date = created_at
        else:
            start_date = created_at.date() if hasattr(created_at, 'date') else date.today()

        elapsed_days = (date.today() - start_date).days
        if elapsed_days <= 0:
            return None

        # Taeglliche Sparrate
        daily_rate = goal.current_value / Decimal(str(elapsed_days))

        # Verbleibender Betrag
        remaining = goal.target_value - goal.current_value

        # Tage bis Abschluss
        days_to_completion = int(remaining / daily_rate)

        return date.today() + timedelta(days=days_to_completion)

    def _recommend_emergency_fund(self, monthly_expenses: Decimal) -> Decimal:
        """Empfiehlt Notgroschen basierend auf Ausgaben.

        Standard-Empfehlung: 3-6 Monatsausgaben
        """
        # Mitte nehmen: 4.5 Monate
        return (monthly_expenses * Decimal("4.5")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def _recommend_retirement_goal(
        self,
        annual_income: Decimal,
        current_age: int,
        retirement_age: int
    ) -> Decimal:
        """Empfiehlt Altersvorsorge-Ziel basierend auf Einkommen.

        Vereinfachte Formel: 25x letzte Jahresausgaben
        """
        # Annahme: 70% des Einkommens als Ausgaben
        annual_expenses = annual_income * Decimal("0.70")

        # 25x Regel (4% Entnahmerate)
        return (annual_expenses * 25).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    def _recommend_savings_rate(self, monthly_income: Decimal) -> Decimal:
        """Empfiehlt Sparquote.

        Standard: 15% des Nettoeinkommens
        """
        return (monthly_income * Decimal("0.15")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    async def _get_goal(self, goal_id: UUID) -> Optional[FinancialGoalModel]:
        """Laedt ein Ziel aus der DB.

        Args:
            goal_id: UUID des Ziels

        Returns:
            FinancialGoalModel oder None
        """
        result = await self.db.execute(
            select(FinancialGoalModel).where(FinancialGoalModel.id == goal_id)
        )
        return result.scalar_one_or_none()

    async def _get_all_goals(self, space_id: UUID) -> List[FinancialGoalModel]:
        """Laedt alle Ziele eines Space.

        Args:
            space_id: UUID des Privat-Space

        Returns:
            Liste von FinancialGoalModel
        """
        result = await self.db.execute(
            select(FinancialGoalModel)
            .where(FinancialGoalModel.space_id == space_id)
            .order_by(FinancialGoalModel.priority.asc(), FinancialGoalModel.target_date.asc())
        )
        return list(result.scalars().all())

    async def recalculate_all_goals(self, space_id: UUID) -> int:
        """Berechnet alle Ziele eines Space neu.

        Aktualisiert Progress, verbleibende Monate, Sparrate und On-Track Status.

        Args:
            space_id: UUID des Privat-Space

        Returns:
            Anzahl aktualisierter Ziele
        """
        goals = await self._get_all_goals(space_id)
        count = 0

        for goal in goals:
            if goal.status != "active":
                continue

            # Progress berechnen
            goal.progress_percent = self._calc_progress_percent(goal.current_value, goal.target_value)
            goal.months_remaining = self._calc_months_remaining(goal.target_date)
            goal.monthly_savings_required = self._calc_monthly_savings_required(
                goal.target_value - goal.current_value,
                goal.months_remaining
            )
            goal.is_on_track = self._calc_is_on_track(goal)
            goal.projected_completion_date = self._calc_projected_completion_date(goal)

            # Auto-Complete wenn Ziel erreicht
            if goal.current_value >= goal.target_value:
                goal.status = "completed"

            count += 1

        await self.db.commit()
        return count

    async def recalculate_all_spaces_goals(self) -> int:
        """Berechnet Ziele aller Spaces neu.

        Wird von Celery Beat taeglich ausgefuehrt.

        Returns:
            Gesamtanzahl aktualisierter Ziele
        """
        from app.db.models import PrivatSpace

        # Hole alle aktiven Spaces
        result = await self.db.execute(
            select(PrivatSpace.id).where(PrivatSpace.deleted_at == None)
        )
        space_ids = [row[0] for row in result.all()]

        total_count = 0
        for space_id in space_ids:
            count = await self.recalculate_all_goals(space_id)
            total_count += count

        return total_count

    async def get_goals_at_risk(self) -> List[FinancialGoalModel]:
        """Findet alle gefaehrdeten Ziele.

        Ein Ziel ist gefaehrdet wenn:
        - is_on_track == False
        - Weniger als 6 Monate verbleiben
        - Progress unter 50% bei weniger als 12 Monaten verbleibend

        Returns:
            Liste gefaehrdeter Ziele
        """
        result = await self.db.execute(
            select(FinancialGoalModel)
            .where(FinancialGoalModel.status == "active")
        )
        all_goals = result.scalars().all()

        at_risk = []
        for goal in all_goals:
            months = self._calc_months_remaining(goal.target_date)
            progress = float(self._calc_progress_percent(goal.current_value, goal.target_value))

            # Kriterien fuer gefaehrdete Ziele
            is_at_risk = (
                not goal.is_on_track or
                (months < 6 and progress < 80) or
                (months < 12 and progress < 50)
            )

            if is_at_risk:
                at_risk.append(goal)

        return at_risk
