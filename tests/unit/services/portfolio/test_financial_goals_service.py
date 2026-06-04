"""Tests fuer den Financial Goals Service.

Testet die ECHTE Service-API (app.services.privat.financial_goals_service):
- Ziel-Erstellung (create_goal) inkl. Progress-/Sparraten-Vorberechnung
- Fortschrittsberechnung (calculate_goal_progress, _recalculate_progress)
- Durchschnittlicher Monatsbeitrag (_calculate_average_monthly_contribution)
- Beitraege (add_contribution) inkl. Auto-Completion
- Updates (update_goal)
- Zusammenfassung (get_goals_summary -> GoalSummary)

Hinweis: Dieser Service ist space-zentriert (PrivatSpace.space_id), nicht
user_id/company_id. Die Tests orientieren sich am tatsaechlichen Code.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

# Import aus dem privat-Modul (von portfolio migriert)
from app.services.privat.financial_goals_service import (
    FinancialGoalsService,
    GoalProgress,
    GoalSummary,
)
from app.db.models import (
    FinancialGoal,
    FinancialGoalStatus,
    FinancialGoalType,
)


def _make_execute_result(
    *,
    scalar_one_or_none=None,
    scalars_all=None,
    scalar=None,
) -> MagicMock:
    """Baut ein Mock-Result, wie es AsyncSession.execute() liefert.

    Deckt die drei im Service genutzten Zugriffsmuster ab:
    - result.scalar_one_or_none()
    - result.scalars().all()
    - result.scalar()
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none
    scalars = MagicMock()
    scalars.all.return_value = scalars_all if scalars_all is not None else []
    result.scalars.return_value = scalars
    result.scalar.return_value = scalar
    return result


class TestGoalCreation:
    """Tests fuer Ziel-Erstellung (create_goal)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_create_retirement_goal(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Altersvorsorge-Ziel wird erstellt und persistiert."""
        space_id = uuid4()

        goal = await service.create_goal(
            space_id=space_id,
            name="Altersvorsorge",
            goal_type=FinancialGoalType.RETIREMENT.value,
            target_value=Decimal("500000"),
            target_date=date(2045, 1, 1),
        )

        assert mock_db.add.called
        assert mock_db.commit.called
        assert goal.name == "Altersvorsorge"
        assert goal.target_value == Decimal("500000")
        assert goal.goal_type == "retirement"
        assert goal.status == FinancialGoalStatus.ACTIVE.value
        # Default-UI-Werte
        assert goal.icon == "Target"
        assert goal.color == "#10B981"

    @pytest.mark.asyncio
    async def test_create_goal_initial_progress(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Startwert fliesst in den Anfangsfortschritt ein."""
        space_id = uuid4()

        goal = await service.create_goal(
            space_id=space_id,
            name="Notgroschen",
            goal_type=FinancialGoalType.EMERGENCY_FUND.value,
            target_value=Decimal("15000"),
            target_date=date.today() + timedelta(days=365),
            initial_value=Decimal("3000"),
        )

        # 3000 / 15000 * 100 = 20%
        assert goal.current_value == Decimal("3000")
        assert goal.progress_percent == Decimal("20")

    @pytest.mark.asyncio
    async def test_create_goal_computes_monthly_savings(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Erforderliche monatliche Sparrate wird bei Erstellung berechnet."""
        space_id = uuid4()
        # Genau 12 Monate in die Zukunft (gleicher Tag im Monat)
        today = date.today()
        target = date(today.year + 1, today.month, 1)

        goal = await service.create_goal(
            space_id=space_id,
            name="Eigenheim Anzahlung",
            goal_type=FinancialGoalType.PROPERTY_PURCHASE.value,
            target_value=Decimal("12000"),
            target_date=target,
        )

        # months_remaining > 0 und Sparrate = remaining / months
        assert goal.months_remaining > 0
        assert goal.monthly_savings_required > Decimal("0")
        assert goal.is_on_track is True


class TestProgressRecalculation:
    """Tests fuer die echte Fortschritts-Neuberechnung (_recalculate_progress)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    def _make_goal(self, current: Decimal, target: Decimal, target_date: date) -> MagicMock:
        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = current
        goal.target_value = target
        goal.target_date = target_date
        return goal

    @pytest.mark.asyncio
    async def test_progress_percent_computed(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """progress_percent = current/target*100."""
        # Kein Beitrag in den letzten 6 Monaten -> avg = 0
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = self._make_goal(
            current=Decimal("25000"),
            target=Decimal("100000"),
            target_date=date.today() + timedelta(days=365),
        )

        await service._recalculate_progress(goal)

        assert goal.progress_percent == Decimal("25")

    @pytest.mark.asyncio
    async def test_progress_percent_over_100(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Fortschritt ueber 100% ist moeglich."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = self._make_goal(
            current=Decimal("120000"),
            target=Decimal("100000"),
            target_date=date.today() + timedelta(days=365),
        )

        await service._recalculate_progress(goal)

        assert goal.progress_percent == Decimal("120")

    @pytest.mark.asyncio
    async def test_progress_percent_zero_target(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ziel=0 ergibt 0% (keine Division durch Null)."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = self._make_goal(
            current=Decimal("1000"),
            target=Decimal("0"),
            target_date=date.today() + timedelta(days=365),
        )

        await service._recalculate_progress(goal)

        assert goal.progress_percent == Decimal("0")

    @pytest.mark.asyncio
    async def test_months_remaining_future(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Verbleibende Monate fuer ein Ziel in ~1 Jahr."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = self._make_goal(
            current=Decimal("0"),
            target=Decimal("12000"),
            target_date=date.today() + timedelta(days=365),
        )

        await service._recalculate_progress(goal)

        assert 11 <= goal.months_remaining <= 13

    @pytest.mark.asyncio
    async def test_months_remaining_past_clamped_to_zero(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Vergangenes Zieldatum liefert 0 verbleibende Monate."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = self._make_goal(
            current=Decimal("0"),
            target=Decimal("12000"),
            target_date=date.today() - timedelta(days=60),
        )

        await service._recalculate_progress(goal)

        assert goal.months_remaining == 0


class TestSavingsCalculation:
    """Tests fuer die monatliche Sparraten-Berechnung in _recalculate_progress."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_monthly_savings_required(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Benoetigte monatliche Sparrate = verbleibend / Monate."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        today = date.today()
        # Exakt 12 Monate in die Zukunft
        target_date = date(today.year + 1, today.month, 1)

        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = Decimal("0")
        goal.target_value = Decimal("12000")
        goal.target_date = target_date

        await service._recalculate_progress(goal)

        # 12000 / months_remaining
        assert goal.monthly_savings_required == Decimal("12000") / goal.months_remaining

    @pytest.mark.asyncio
    async def test_monthly_savings_zero_months_uses_full_remaining(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Bei 0 verbleibenden Monaten wird der gesamte Restbetrag benoetigt."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = Decimal("0")
        goal.target_value = Decimal("10000")
        # Zieldatum in der Vergangenheit -> months_remaining == 0
        goal.target_date = date.today() - timedelta(days=30)

        await service._recalculate_progress(goal)

        assert goal.months_remaining == 0
        assert goal.monthly_savings_required == Decimal("10000")

    @pytest.mark.asyncio
    async def test_monthly_savings_target_exceeded_is_zero(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Bei ueberschrittenem Ziel ist die benoetigte Sparrate 0."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = Decimal("15000")  # > target
        goal.target_value = Decimal("10000")
        goal.target_date = date.today() + timedelta(days=365)

        await service._recalculate_progress(goal)

        # remaining wird auf 0 geklemmt -> Sparrate 0
        assert goal.monthly_savings_required == Decimal("0")


class TestOnTrackCalculation:
    """Tests fuer die On-Track-Bewertung in _recalculate_progress.

    On-Track-Logik (echter Code): avg_monthly >= monatlich_erforderlich * 0.9.
    """

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    def _make_goal(self) -> MagicMock:
        today = date.today()
        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = Decimal("0")
        goal.target_value = Decimal("12000")
        goal.target_date = date(today.year + 1, today.month, 1)  # ~12 Monate
        return goal

    @pytest.mark.asyncio
    async def test_on_track_when_avg_meets_requirement(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ausreichend hoher Durchschnittsbeitrag -> on track."""
        # avg = 6000 (Summe letzter 6 Monate) / 6 = 1000/Monat,
        # benoetigt ~1000/Monat -> on track
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("6000"))
        goal = self._make_goal()

        await service._recalculate_progress(goal)

        assert goal.is_on_track is True

    @pytest.mark.asyncio
    async def test_not_on_track_when_avg_too_low(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Zu niedriger Durchschnittsbeitrag -> nicht on track."""
        # avg = 600 / 6 = 100/Monat, benoetigt ~1000/Monat -> nicht on track
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("600"))
        goal = self._make_goal()

        await service._recalculate_progress(goal)

        assert goal.is_on_track is False

    @pytest.mark.asyncio
    async def test_on_track_when_target_reached_and_no_months_left(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ziel erreicht ohne verbleibende Monate -> on track."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = Decimal("12000")  # erreicht
        goal.target_value = Decimal("12000")
        goal.target_date = date.today() - timedelta(days=1)  # months_remaining == 0

        await service._recalculate_progress(goal)

        assert goal.is_on_track is True


class TestProjectedCompletion:
    """Tests fuer das prognostizierte Abschlussdatum in _recalculate_progress."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_projected_completion_with_contributions(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Mit positivem Durchschnittsbeitrag wird ein Datum prognostiziert."""
        # avg = 12000 / 6 = 2000/Monat; remaining = 6000 -> ~3-4 Monate
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("12000"))
        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = Decimal("6000")
        goal.target_value = Decimal("12000")
        goal.target_date = date.today() + timedelta(days=365)

        await service._recalculate_progress(goal)

        assert goal.projected_completion_date is not None
        assert goal.projected_completion_date > date.today()

    @pytest.mark.asyncio
    async def test_projected_completion_none_without_progress(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ohne Beitraege (avg=0) kann kein Datum prognostiziert werden."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("0"))
        goal = MagicMock()
        goal.id = uuid4()
        goal.current_value = Decimal("0")
        goal.target_value = Decimal("12000")
        goal.target_date = date.today() + timedelta(days=365)

        await service._recalculate_progress(goal)

        assert goal.projected_completion_date is None


class TestAverageMonthlyContribution:
    """Tests fuer _calculate_average_monthly_contribution."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_average_divides_by_six_months(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Summe der letzten 6 Monate wird durch 6 geteilt."""
        mock_db.execute.return_value = _make_execute_result(scalar=Decimal("3000"))

        avg = await service._calculate_average_monthly_contribution(uuid4())

        assert avg == Decimal("500")

    @pytest.mark.asyncio
    async def test_average_zero_when_no_contributions(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Keine Beitraege -> Durchschnitt 0."""
        mock_db.execute.return_value = _make_execute_result(scalar=None)

        avg = await service._calculate_average_monthly_contribution(uuid4())

        assert avg == Decimal("0")


class TestCalculateGoalProgress:
    """Tests fuer die detaillierte Fortschritts-API (calculate_goal_progress)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_returns_goal_progress_dataclass(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """calculate_goal_progress liefert ein GoalProgress mit korrekten Werten."""
        goal_id = uuid4()
        today = date.today()
        goal = MagicMock()
        goal.id = goal_id
        goal.current_value = Decimal("25000")
        goal.target_value = Decimal("100000")
        goal.progress_percent = Decimal("25")
        goal.target_date = date(today.year + 1, today.month, 1)

        # 1. execute -> get_goal (scalar_one_or_none),
        # 2. execute -> _calculate_average_monthly_contribution (scalar)
        mock_db.execute.side_effect = [
            _make_execute_result(scalar_one_or_none=goal),
            _make_execute_result(scalar=Decimal("0")),
        ]

        progress = await service.calculate_goal_progress(goal_id)

        assert isinstance(progress, GoalProgress)
        assert progress.current_value == Decimal("25000")
        assert progress.target_value == Decimal("100000")
        assert progress.progress_percent == 25.0
        assert progress.remaining_amount == Decimal("75000")
        assert progress.months_remaining > 0
        assert progress.average_monthly_contribution == Decimal("0")

    @pytest.mark.asyncio
    async def test_raises_when_goal_not_found(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Unbekanntes Ziel fuehrt zu ValueError."""
        mock_db.execute.return_value = _make_execute_result(scalar_one_or_none=None)

        with pytest.raises(ValueError):
            await service.calculate_goal_progress(uuid4())


class TestGoalUpdates:
    """Tests fuer Ziel-Aktualisierungen (update_goal)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_update_current_value_recalculates_progress(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Aenderung von current_value berechnet den Fortschritt neu."""
        goal_id = uuid4()
        today = date.today()
        goal = MagicMock()
        goal.id = goal_id
        goal.target_value = Decimal("50000")
        goal.current_value = Decimal("10000")
        goal.target_date = date(today.year + 1, today.month, 1)

        # 1. execute -> get_goal
        # 2. execute -> _calculate_average_monthly_contribution (im recalc)
        mock_db.execute.side_effect = [
            _make_execute_result(scalar_one_or_none=goal),
            _make_execute_result(scalar=Decimal("0")),
        ]

        updated = await service.update_goal(goal_id, current_value=Decimal("25000"))

        assert updated is goal
        assert goal.current_value == Decimal("25000")
        # 25000 / 50000 * 100 = 50%
        assert goal.progress_percent == Decimal("50")
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_update_returns_none_when_goal_missing(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Update auf nicht existierendes Ziel liefert None."""
        mock_db.execute.return_value = _make_execute_result(scalar_one_or_none=None)

        result = await service.update_goal(uuid4(), current_value=Decimal("1"))

        assert result is None


class TestContributionsAndCompletion:
    """Tests fuer Beitraege (add_contribution) und Auto-Completion."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        return db

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_add_contribution_increases_current_value(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ein Beitrag erhoeht den aktuellen Betrag des Ziels."""
        goal_id = uuid4()
        today = date.today()
        goal = MagicMock()
        goal.id = goal_id
        goal.name = "Sparziel"
        goal.current_value = Decimal("1000")
        goal.target_value = Decimal("50000")
        goal.target_date = date(today.year + 1, today.month, 1)

        mock_db.execute.side_effect = [
            _make_execute_result(scalar_one_or_none=goal),  # get_goal
            _make_execute_result(scalar=Decimal("0")),       # avg (recalc)
        ]

        contribution = await service.add_contribution(goal_id, amount=Decimal("500"))

        assert contribution is not None
        assert goal.current_value == Decimal("1500")
        assert goal.status != FinancialGoalStatus.COMPLETED.value
        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_add_contribution_auto_completes_goal(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Erreicht der Beitrag den Zielwert, wird das Ziel abgeschlossen."""
        goal_id = uuid4()
        today = date.today()
        goal = MagicMock()
        goal.id = goal_id
        goal.name = "Notgroschen"
        goal.current_value = Decimal("9500")
        goal.target_value = Decimal("10000")
        goal.status = FinancialGoalStatus.ACTIVE.value
        goal.target_date = date(today.year + 1, today.month, 1)

        mock_db.execute.side_effect = [
            _make_execute_result(scalar_one_or_none=goal),  # get_goal
            _make_execute_result(scalar=Decimal("0")),       # avg (recalc)
        ]

        await service.add_contribution(goal_id, amount=Decimal("500"))

        assert goal.current_value == Decimal("10000")
        assert goal.status == FinancialGoalStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_add_contribution_unknown_goal_returns_none(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Beitrag auf unbekanntes Ziel liefert None."""
        mock_db.execute.return_value = _make_execute_result(scalar_one_or_none=None)

        result = await service.add_contribution(uuid4(), amount=Decimal("100"))

        assert result is None


class TestFinancialGoalsServiceIntegration:
    """Integrationstest fuer die Zusammenfassung (get_goals_summary)."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_get_goals_summary(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ziel-Zusammenfassung aggregiert alle Ziele korrekt (GoalSummary)."""
        space_id = uuid4()

        goals = [
            MagicMock(
                goal_type="emergency_fund",
                target_value=Decimal("15000"),
                current_value=Decimal("10000"),
                status=FinancialGoalStatus.ACTIVE.value,
                is_on_track=True,
            ),
            MagicMock(
                goal_type="retirement",
                target_value=Decimal("500000"),
                current_value=Decimal("50000"),
                status=FinancialGoalStatus.ACTIVE.value,
                is_on_track=False,
            ),
            MagicMock(
                goal_type="property",
                target_value=Decimal("50000"),
                current_value=Decimal("50000"),
                status=FinancialGoalStatus.COMPLETED.value,
                is_on_track=True,
            ),
        ]

        # get_goals_summary ruft get_goals_for_space -> db.execute -> scalars().all()
        mock_db.execute.return_value = _make_execute_result(scalars_all=goals)

        summary = await service.get_goals_summary(space_id)

        assert isinstance(summary, GoalSummary)
        assert summary.total_goals == 3
        assert summary.active_goals == 2
        assert summary.completed_goals == 1
        assert summary.total_target_value == Decimal("565000")
        assert summary.total_current_value == Decimal("110000")
        # Nur aktive Ziele zaehlen fuer on_track/at_risk:
        # emergency_fund (on track) + retirement (at risk)
        assert summary.goals_on_track == 1
        assert summary.goals_at_risk == 1
        # 110000 / 565000 * 100
        assert summary.overall_progress_percent == pytest.approx(
            float(Decimal("110000") / Decimal("565000") * 100)
        )
