"""Tests fuer den Financial Goals Service.

Testet:
- Ziel-Erstellung und -Verwaltung
- Fortschrittsberechnung
- Prognosen
- Empfehlungen
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

# Import from privat module (migrated from portfolio module)
from app.services.privat.financial_goals_service import FinancialGoalsService
from app.services.privat.financial_goals_service import FinancialGoal
from app.services.privat.financial_goals_service import GoalProgress


class TestGoalCreation:
    """Tests fuer Ziel-Erstellung."""

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
        """Altersvorsorge-Ziel wird erstellt."""
        space_id = uuid4()

        result = await service.create_goal(
            space_id=space_id,
            name="Altersvorsorge",
            goal_type="retirement",
            target_value=Decimal("500000"),
            target_date=date(2045, 1, 1),
        )

        assert mock_db.add.called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_create_emergency_fund_goal(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Notgroschen-Ziel wird erstellt."""
        space_id = uuid4()

        result = await service.create_goal(
            space_id=space_id,
            name="Notgroschen",
            goal_type="emergency_fund",
            target_value=Decimal("15000"),
            target_date=date(2025, 12, 31),
        )

        assert mock_db.add.called

    @pytest.mark.asyncio
    async def test_create_property_goal(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Immobilien-Ziel wird erstellt."""
        space_id = uuid4()

        result = await service.create_goal(
            space_id=space_id,
            name="Eigenheim Anzahlung",
            goal_type="property",
            target_value=Decimal("50000"),
            target_date=date(2028, 6, 1),
        )

        assert mock_db.add.called


class TestProgressCalculation:
    """Tests fuer Fortschrittsberechnung."""

    def setup_method(self) -> None:
        self.service = FinancialGoalsService(db=MagicMock())

    def test_progress_percentage(self) -> None:
        """Fortschrittsprozent wird korrekt berechnet."""
        current_value = Decimal("25000")
        target_value = Decimal("100000")

        result = self.service._calc_progress_percent(current_value, target_value)

        assert result == Decimal("25.00")

    def test_progress_percentage_over_100(self) -> None:
        """Fortschritt ueber 100% ist moeglich."""
        current_value = Decimal("120000")
        target_value = Decimal("100000")

        result = self.service._calc_progress_percent(current_value, target_value)

        assert result == Decimal("120.00")

    def test_progress_percentage_zero_target(self) -> None:
        """Fortschritt bei Ziel=0 gibt 100% zurueck."""
        result = self.service._calc_progress_percent(Decimal("1000"), Decimal("0"))
        assert result == Decimal("100.00")

    def test_months_remaining(self) -> None:
        """Verbleibende Monate werden korrekt berechnet."""
        target_date = date.today() + timedelta(days=365)  # 1 Jahr

        result = self.service._calc_months_remaining(target_date)

        assert 11 <= result <= 13  # ca. 12 Monate

    def test_months_remaining_past_date(self) -> None:
        """Vergangenes Datum gibt 0 zurueck."""
        target_date = date.today() - timedelta(days=30)

        result = self.service._calc_months_remaining(target_date)

        assert result == 0


class TestSavingsCalculation:
    """Tests fuer Spar-Berechnungen."""

    def setup_method(self) -> None:
        self.service = FinancialGoalsService(db=MagicMock())

    def test_monthly_savings_required(self) -> None:
        """Benoetigte monatliche Sparrate wird berechnet."""
        remaining = Decimal("36000")  # 36.000€ fehlen noch
        months = 24  # 24 Monate Zeit

        result = self.service._calc_monthly_savings_required(remaining, months)

        # 36000 / 24 = 1500€/Monat
        assert result == Decimal("1500.00")

    def test_monthly_savings_zero_months(self) -> None:
        """Bei 0 Monaten wird gesamter Betrag benoetigt."""
        remaining = Decimal("10000")
        months = 0

        result = self.service._calc_monthly_savings_required(remaining, months)

        assert result == remaining

    def test_monthly_savings_negative_remaining(self) -> None:
        """Bei ueberschrittenem Ziel wird 0 benoetigt."""
        remaining = Decimal("-5000")  # Ziel ueberschritten
        months = 12

        result = self.service._calc_monthly_savings_required(remaining, months)

        assert result == Decimal("0")


class TestOnTrackCalculation:
    """Tests fuer On-Track Bewertung."""

    def setup_method(self) -> None:
        self.service = FinancialGoalsService(db=MagicMock())

    def test_is_on_track_ahead_of_schedule(self) -> None:
        """Ziel ist auf Kurs - voraus."""
        mock_goal = MagicMock()
        mock_goal.target_value = Decimal("100000")
        mock_goal.current_value = Decimal("60000")
        mock_goal.target_date = date.today() + timedelta(days=365)  # 1 Jahr
        mock_goal.created_at = date.today() - timedelta(days=365)  # Vor 1 Jahr erstellt

        # 60% erreicht in 50% der Zeit = voraus
        result = self.service._calc_is_on_track(mock_goal)

        assert result is True

    def test_is_on_track_behind_schedule(self) -> None:
        """Ziel ist nicht auf Kurs - zurueck."""
        mock_goal = MagicMock()
        mock_goal.target_value = Decimal("100000")
        mock_goal.current_value = Decimal("20000")
        mock_goal.target_date = date.today() + timedelta(days=365)  # 1 Jahr
        mock_goal.created_at = date.today() - timedelta(days=365)  # Vor 1 Jahr erstellt

        # 20% erreicht in 50% der Zeit = zurueck
        result = self.service._calc_is_on_track(mock_goal)

        assert result is False

    def test_is_on_track_completed(self) -> None:
        """Erreichtes Ziel ist immer auf Kurs."""
        mock_goal = MagicMock()
        mock_goal.target_value = Decimal("100000")
        mock_goal.current_value = Decimal("100000")  # Ziel erreicht
        mock_goal.target_date = date.today() + timedelta(days=365)

        result = self.service._calc_is_on_track(mock_goal)

        assert result is True


class TestProjectedCompletion:
    """Tests fuer Abschluss-Prognose."""

    def setup_method(self) -> None:
        self.service = FinancialGoalsService(db=MagicMock())

    def test_projected_completion_date(self) -> None:
        """Voraussichtliches Abschlussdatum wird berechnet."""
        mock_goal = MagicMock()
        mock_goal.target_value = Decimal("100000")
        mock_goal.current_value = Decimal("50000")
        mock_goal.created_at = date.today() - timedelta(days=365)  # Vor 1 Jahr

        # 50k in 1 Jahr = 50k/Jahr Sparrate
        # Noch 50k noetig = noch 1 Jahr
        result = self.service._calc_projected_completion_date(mock_goal)

        expected = date.today() + timedelta(days=365)
        assert abs((result - expected).days) < 60

    def test_projected_completion_no_progress(self) -> None:
        """Ohne Fortschritt gibt None zurueck."""
        mock_goal = MagicMock()
        mock_goal.target_value = Decimal("100000")
        mock_goal.current_value = Decimal("0")
        mock_goal.created_at = date.today() - timedelta(days=30)

        result = self.service._calc_projected_completion_date(mock_goal)

        assert result is None  # Kann nicht berechnet werden


class TestGoalRecommendations:
    """Tests fuer Empfehlungen."""

    def setup_method(self) -> None:
        self.service = FinancialGoalsService(db=MagicMock())

    def test_emergency_fund_recommendation(self) -> None:
        """Notgroschen-Empfehlung basierend auf Ausgaben."""
        monthly_expenses = Decimal("3000")

        result = self.service._recommend_emergency_fund(monthly_expenses)

        # 3-6 Monatsausgaben empfohlen
        assert result >= Decimal("9000")
        assert result <= Decimal("18000")

    def test_retirement_goal_recommendation(self) -> None:
        """Altersvorsorge-Empfehlung basierend auf Einkommen."""
        annual_income = Decimal("60000")
        current_age = 35
        retirement_age = 67

        result = self.service._recommend_retirement_goal(
            annual_income, current_age, retirement_age
        )

        # Sollte substantiellen Betrag empfehlen
        assert result > Decimal("500000")

    def test_savings_rate_recommendation(self) -> None:
        """Sparquoten-Empfehlung."""
        monthly_income = Decimal("5000")

        result = self.service._recommend_savings_rate(monthly_income)

        # 10-20% des Einkommens empfohlen
        assert result >= Decimal("500")
        assert result <= Decimal("1000")


class TestGoalUpdates:
    """Tests fuer Ziel-Aktualisierungen."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_update_goal_progress(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ziel-Fortschritt wird aktualisiert."""
        goal_id = uuid4()
        mock_goal = MagicMock()
        mock_goal.id = goal_id
        mock_goal.target_value = Decimal("100000")
        mock_goal.current_value = Decimal("25000")
        mock_goal.target_date = date.today() + timedelta(days=365)
        mock_goal.created_at = date.today() - timedelta(days=180)
        mock_goal.status = "active"

        with patch.object(service, "_get_goal", return_value=mock_goal):
            await service.update_progress(goal_id, new_value=Decimal("30000"))

            assert mock_goal.current_value == Decimal("30000")
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_update_recalculates_metrics(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Aktualisierung berechnet Metriken neu."""
        goal_id = uuid4()
        mock_goal = MagicMock()
        mock_goal.id = goal_id
        mock_goal.target_value = Decimal("50000")
        mock_goal.current_value = Decimal("10000")
        mock_goal.target_date = date.today() + timedelta(days=365)
        mock_goal.created_at = date.today() - timedelta(days=180)
        mock_goal.status = "active"

        with patch.object(service, "_get_goal", return_value=mock_goal):
            await service.update_progress(goal_id, new_value=Decimal("25000"))

            # Progress sollte aktualisiert sein: 25k / 50k = 50%
            assert mock_goal.progress_percent == Decimal("50.00")


class TestGoalCompletion:
    """Tests fuer Ziel-Abschluss."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> FinancialGoalsService:
        return FinancialGoalsService(db=mock_db)

    @pytest.mark.asyncio
    async def test_mark_goal_completed(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ziel wird als abgeschlossen markiert."""
        goal_id = uuid4()
        mock_goal = MagicMock()
        mock_goal.id = goal_id
        mock_goal.status = "active"

        with patch.object(service, "_get_goal", return_value=mock_goal):
            await service.complete_goal(goal_id)

            assert mock_goal.status == "completed"
            assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_auto_complete_when_target_reached(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ziel wird automatisch abgeschlossen bei Erreichen."""
        goal_id = uuid4()
        mock_goal = MagicMock()
        mock_goal.id = goal_id
        mock_goal.target_value = Decimal("50000")
        mock_goal.current_value = Decimal("45000")
        mock_goal.status = "active"
        mock_goal.target_date = date.today() + timedelta(days=365)
        mock_goal.created_at = date.today() - timedelta(days=180)

        with patch.object(service, "_get_goal", return_value=mock_goal):
            # Update to reach target
            await service.update_progress(goal_id, new_value=Decimal("50000"))

            assert mock_goal.status == "completed"


class TestFinancialGoalsServiceIntegration:
    """Integrationstests fuer den gesamten Service."""

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
    async def test_get_goals_summary(
        self, service: FinancialGoalsService, mock_db: AsyncMock
    ) -> None:
        """Ziel-Zusammenfassung wird erstellt."""
        space_id = uuid4()

        mock_goals = [
            MagicMock(
                goal_type="emergency_fund",
                target_value=Decimal("15000"),
                current_value=Decimal("10000"),
                status="active",
                is_on_track=True,
            ),
            MagicMock(
                goal_type="retirement",
                target_value=Decimal("500000"),
                current_value=Decimal("50000"),
                status="active",
                is_on_track=False,
            ),
            MagicMock(
                goal_type="property",
                target_value=Decimal("50000"),
                current_value=Decimal("50000"),
                status="completed",
                is_on_track=True,
            ),
        ]

        with patch.object(service, "_get_all_goals", return_value=mock_goals):
            result = await service.get_goals_summary(space_id)

            assert result["total_goals"] == 3
            assert result["active_goals"] == 2
            assert result["completed_goals"] == 1
            assert result["on_track_count"] == 2  # emergency_fund + completed
            assert result["total_target_value"] == Decimal("565000")
            assert result["total_current_value"] == Decimal("110000")
