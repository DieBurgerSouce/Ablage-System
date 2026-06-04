# -*- coding: utf-8 -*-
"""
Tests fuer CashFlowService.

Testet:
- Prognose-Erstellung
- Szenario-Berechnung
- Taegliche Projektion
- Alert-Generierung
"""

import pytest
from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.banking.cash_flow_service import (
    CashFlowService,
    CashFlowEntry,
    CashFlowProjection,
    ForecastPeriod,
    ForecastScenario,
)
from app.services.banking.models import CashFlowDirection


class TestCashFlowEntry:
    """Tests fuer CashFlowEntry Dataclass."""

    def test_create_inflow_entry(self):
        """Sollte Einnahmen-Eintrag erstellen."""
        entry = CashFlowEntry(
            date=date.today(),
            amount=Decimal("1000.00"),
            direction=CashFlowDirection.INFLOW,
            source="receivable",
            reference="RE-2024-001",
        )

        assert entry.amount == Decimal("1000.00")
        assert entry.direction == CashFlowDirection.INFLOW
        assert entry.probability == 1.0

    def test_create_outflow_entry(self):
        """Sollte Ausgaben-Eintrag erstellen."""
        entry = CashFlowEntry(
            date=date.today() + timedelta(days=7),
            amount=Decimal("500.00"),
            direction=CashFlowDirection.OUTFLOW,
            source="payable",
            probability=0.9,
        )

        assert entry.amount == Decimal("500.00")
        assert entry.direction == CashFlowDirection.OUTFLOW
        assert entry.probability == 0.9


class TestCashFlowProjection:
    """Tests fuer CashFlowProjection Dataclass."""

    def test_create_empty_projection(self):
        """Sollte leere Projektion erstellen."""
        projection = CashFlowProjection(
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
        )

        assert projection.total_inflow == Decimal("0.00")
        assert projection.total_outflow == Decimal("0.00")
        assert projection.net_flow == Decimal("0.00")
        assert len(projection.entries) == 0


class TestCashFlowServiceScenarios:
    """Tests fuer Szenario-Anpassungen."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    def test_apply_optimistic_scenario(self, service: CashFlowService):
        """Sollte optimistisches Szenario anwenden."""
        entries = [
            CashFlowEntry(
                date=date.today(),
                amount=Decimal("1000.00"),
                direction=CashFlowDirection.INFLOW,
                source="receivable",
                probability=0.8,
            ),
            CashFlowEntry(
                date=date.today(),
                amount=Decimal("500.00"),
                direction=CashFlowDirection.OUTFLOW,
                source="payable",
                probability=1.0,
            ),
        ]

        adjusted = service._apply_scenario(entries, ForecastScenario.OPTIMISTIC)

        # Einnahmen sollten hoeher gewichtet werden (0.8 * 1.1 = 0.88)
        inflow = [e for e in adjusted if e.direction == CashFlowDirection.INFLOW][0]
        assert inflow.probability == pytest.approx(0.88, rel=0.01)

        # Ausgaben sollten niedriger gewichtet werden (1.0 * 0.9 = 0.9)
        outflow = [e for e in adjusted if e.direction == CashFlowDirection.OUTFLOW][0]
        assert outflow.probability == pytest.approx(0.9, rel=0.01)

    def test_apply_pessimistic_scenario(self, service: CashFlowService):
        """Sollte pessimistisches Szenario anwenden."""
        entries = [
            CashFlowEntry(
                date=date.today(),
                amount=Decimal("1000.00"),
                direction=CashFlowDirection.INFLOW,
                source="receivable",
                probability=1.0,
            ),
            CashFlowEntry(
                date=date.today(),
                amount=Decimal("500.00"),
                direction=CashFlowDirection.OUTFLOW,
                source="payable",
                probability=0.8,
            ),
        ]

        adjusted = service._apply_scenario(entries, ForecastScenario.PESSIMISTIC)

        # Einnahmen sollten niedriger gewichtet werden (1.0 * 0.8 = 0.8)
        inflow = [e for e in adjusted if e.direction == CashFlowDirection.INFLOW][0]
        assert inflow.probability == pytest.approx(0.8, rel=0.01)

        # Ausgaben sollten hoeher gewichtet werden (0.8 * 1.15 = 0.92)
        outflow = [e for e in adjusted if e.direction == CashFlowDirection.OUTFLOW][0]
        assert outflow.probability == pytest.approx(0.92, rel=0.01)

    def test_realistic_scenario_no_change(self, service: CashFlowService):
        """Sollte realistisches Szenario unveraendert lassen."""
        entries = [
            CashFlowEntry(
                date=date.today(),
                amount=Decimal("1000.00"),
                direction=CashFlowDirection.INFLOW,
                source="receivable",
                probability=0.5,
            ),
        ]

        adjusted = service._apply_scenario(entries, ForecastScenario.REALISTIC)

        assert adjusted[0].probability == 0.5


class TestCashFlowProjectionCalculation:
    """Tests fuer Projektions-Berechnung."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    def test_calculate_simple_projection(self, service: CashFlowService):
        """Sollte einfache Projektion berechnen."""
        today = date.today()

        projection = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=7),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            entries=[
                CashFlowEntry(
                    date=today + timedelta(days=1),
                    amount=Decimal("1000.00"),
                    direction=CashFlowDirection.INFLOW,
                    source="receivable",
                    probability=1.0,
                ),
                CashFlowEntry(
                    date=today + timedelta(days=3),
                    amount=Decimal("400.00"),
                    direction=CashFlowDirection.OUTFLOW,
                    source="payable",
                    probability=1.0,
                ),
            ],
        )

        result = service._calculate_projection(projection, Decimal("500.00"))

        assert result.total_inflow == Decimal("1000.00")
        assert result.total_outflow == Decimal("400.00")
        assert result.net_flow == Decimal("600.00")
        assert result.days_negative == 0

    def test_calculate_projection_with_negative_days(self, service: CashFlowService):
        """Sollte negative Tage zaehlen."""
        today = date.today()

        projection = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=5),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            entries=[
                CashFlowEntry(
                    date=today + timedelta(days=1),
                    amount=Decimal("2000.00"),
                    direction=CashFlowDirection.OUTFLOW,
                    source="payable",
                    probability=1.0,
                ),
                CashFlowEntry(
                    date=today + timedelta(days=4),
                    amount=Decimal("3000.00"),
                    direction=CashFlowDirection.INFLOW,
                    source="receivable",
                    probability=1.0,
                ),
            ],
        )

        result = service._calculate_projection(projection, Decimal("500.00"))

        # Tag 0: 500, Tag 1: -1500, Tag 2: -1500, Tag 3: -1500, Tag 4: +1500
        assert result.days_negative > 0
        assert result.min_balance < 0

    def test_calculate_projection_with_probability(self, service: CashFlowService):
        """Sollte Wahrscheinlichkeiten beruecksichtigen."""
        today = date.today()

        projection = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=2),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            entries=[
                CashFlowEntry(
                    date=today + timedelta(days=1),
                    amount=Decimal("1000.00"),
                    direction=CashFlowDirection.INFLOW,
                    source="receivable",
                    probability=0.5,  # 50% Wahrscheinlichkeit
                ),
            ],
        )

        result = service._calculate_projection(projection, Decimal("0.00"))

        # 1000 * 0.5 = 500
        assert result.total_inflow == Decimal("500.00")


class TestAlertGeneration:
    """Tests fuer Alert-Generierung."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    def test_generate_liquidity_critical_alert(self, service: CashFlowService):
        """Sollte kritischen Alert bei negativem Saldo generieren."""
        today = date.today()

        short_term = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=7),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            min_balance=Decimal("-5000.00"),
            min_balance_date=today + timedelta(days=3),
            days_negative=4,
        )

        mid_term = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=30),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            days_negative=10,
        )

        long_term = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=90),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
        )

        alerts = service._generate_alerts(short_term, mid_term, long_term)

        critical_alerts = [a for a in alerts if a["level"] == "critical"]
        assert len(critical_alerts) >= 1
        assert "Liquiditaetsengpass" in critical_alerts[0]["message"]

    def test_generate_positive_alert(self, service: CashFlowService):
        """Sollte positiven Alert bei gutem Cash-Flow generieren."""
        today = date.today()

        short_term = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=7),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            min_balance=Decimal("10000.00"),
            days_negative=0,
        )

        mid_term = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=30),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            days_negative=0,
        )

        long_term = CashFlowProjection(
            start_date=today,
            end_date=today + timedelta(days=90),
            period=ForecastPeriod.DAILY,
            scenario=ForecastScenario.REALISTIC,
            net_flow=Decimal("50000.00"),
            days_negative=0,
        )

        alerts = service._generate_alerts(short_term, mid_term, long_term)

        info_alerts = [a for a in alerts if a["level"] == "info"]
        assert len(info_alerts) >= 1


class TestScenarioRecommendation:
    """Tests fuer Szenario-Empfehlungen."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    def test_stable_recommendation(self, service: CashFlowService):
        """Sollte 'Stabil' empfehlen wenn alles gut."""
        scenarios = {
            "optimistic": {"days_negative": 0, "min_balance": 10000},
            "realistic": {"days_negative": 0, "min_balance": 5000},
            "pessimistic": {"days_negative": 0, "min_balance": 1000},
        }

        recommendation = service._get_scenario_recommendation(scenarios)

        assert "Stabil" in recommendation

    def test_warning_recommendation(self, service: CashFlowService):
        """Sollte Warnung bei pessimistischem Risiko."""
        scenarios = {
            "optimistic": {"days_negative": 0, "min_balance": 10000},
            "realistic": {"days_negative": 0, "min_balance": 5000},
            "pessimistic": {"days_negative": 5, "min_balance": -1000},
        }

        recommendation = service._get_scenario_recommendation(scenarios)

        assert "Risiko" in recommendation or "Vorsicht" in recommendation

    def test_critical_recommendation(self, service: CashFlowService):
        """Sollte kritische Warnung bei starkem Risiko."""
        scenarios = {
            "optimistic": {"days_negative": 5, "min_balance": 1000},
            "realistic": {"days_negative": 10, "min_balance": -2000},
            "pessimistic": {"days_negative": 20, "min_balance": -10000},
        }

        recommendation = service._get_scenario_recommendation(scenarios)

        assert "Vorsicht" in recommendation


# =============================================================================
# ASYNC DB TESTS
# =============================================================================


class TestAsyncCashFlowForecast:
    """Tests fuer async get_cash_flow_forecast."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.fixture
    def sample_receivable_documents(self, sample_user_id):
        """Sample Forderungs-Dokumente."""
        today = date.today()
        documents = []

        doc1 = MagicMock()
        doc1.id = uuid4()
        doc1.owner_id = sample_user_id
        doc1.document_type = "invoice"
        doc1.deleted_at = None
        doc1.extracted_data = {
            "invoice_number": "RE-2024-001",
            "creditor_name": "Kunde A",
            "total_amount": "5000.00",
            "due_date": (today + timedelta(days=10)).isoformat(),
        }
        documents.append(doc1)

        doc2 = MagicMock()
        doc2.id = uuid4()
        doc2.owner_id = sample_user_id
        doc2.document_type = "invoice"
        doc2.deleted_at = None
        doc2.extracted_data = {
            "invoice_number": "RE-2024-002",
            "creditor_name": "Kunde B",
            "total_amount": "3000.00",
            "due_date": (today + timedelta(days=20)).isoformat(),
        }
        documents.append(doc2)

        return documents

    @pytest.fixture
    def sample_payable_documents(self, sample_user_id):
        """Sample Verbindlichkeiten-Dokumente."""
        today = date.today()
        documents = []

        doc1 = MagicMock()
        doc1.id = uuid4()
        doc1.owner_id = sample_user_id
        doc1.document_type = "supplier_invoice"
        doc1.deleted_at = None
        doc1.extracted_data = {
            "invoice_number": "LR-2024-001",
            "creditor_name": "Lieferant A",
            "total_amount": "2500.00",
            "due_date": (today + timedelta(days=5)).isoformat(),
        }
        documents.append(doc1)

        return documents

    @pytest.mark.asyncio
    async def test_get_cash_flow_forecast_empty(
        self, service: CashFlowService, mock_db, sample_user_id
    ):
        """Sollte leere Prognose bei keinen Daten zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        projection = await service.get_cash_flow_forecast(
            db=mock_db,
            company_id=sample_user_id,
            days_ahead=30,
        )

        assert projection.total_inflow == Decimal("0.00")
        assert projection.total_outflow == Decimal("0.00")
        assert projection.start_date == date.today()

    @pytest.mark.asyncio
    async def test_get_cash_flow_forecast_with_starting_balance(
        self, service: CashFlowService, mock_db, sample_user_id
    ):
        """Sollte Prognose mit Anfangssaldo berechnen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        projection = await service.get_cash_flow_forecast(
            db=mock_db,
            company_id=sample_user_id,
            days_ahead=7,
            starting_balance=Decimal("10000.00"),
        )

        # Erste Tag sollte den Anfangssaldo haben
        first_day = projection.start_date
        assert first_day in projection.daily_balances

    @pytest.mark.asyncio
    async def test_get_cash_flow_forecast_different_scenarios(
        self, service: CashFlowService, mock_db, sample_user_id
    ):
        """Sollte verschiedene Szenarien unterstuetzen."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        for scenario in [ForecastScenario.OPTIMISTIC, ForecastScenario.REALISTIC, ForecastScenario.PESSIMISTIC]:
            projection = await service.get_cash_flow_forecast(
                db=mock_db,
                company_id=sample_user_id,
                days_ahead=30,
                scenario=scenario,
            )

            assert projection.scenario == scenario


class TestAsyncCashFlowSummary:
    """Tests fuer async get_cash_flow_summary."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_cash_flow_summary(
        self, service: CashFlowService, mock_db, sample_user_id
    ):
        """Sollte Cash-Flow-Zusammenfassung zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        summary = await service.get_cash_flow_summary(
            db=mock_db,
            company_id=sample_user_id,
        )

        assert "short_term" in summary
        assert "mid_term" in summary
        assert "long_term" in summary
        assert "alerts" in summary
        assert "generated_at" in summary

        # Perioden pruefen
        assert summary["short_term"]["period"] == "7 Tage"
        assert summary["mid_term"]["period"] == "30 Tage"
        assert summary["long_term"]["period"] == "90 Tage"


class TestAsyncDailyForecast:
    """Tests fuer async get_daily_forecast."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_get_daily_forecast(
        self, service: CashFlowService, mock_db, sample_user_id
    ):
        """Sollte taegliche Prognose zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        daily = await service.get_daily_forecast(
            db=mock_db,
            company_id=sample_user_id,
            days=7,
        )

        # 7 Tage + heute = 8 Eintraege
        assert len(daily) >= 7

        # Jeder Eintrag sollte die erforderlichen Felder haben
        for entry in daily:
            assert "date" in entry
            assert "inflow" in entry
            assert "outflow" in entry
            assert "net" in entry
            assert "balance" in entry


class TestAsyncCompareScenarios:
    """Tests fuer async compare_scenarios."""

    @pytest.fixture
    def service(self) -> CashFlowService:
        return CashFlowService()

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        return db

    @pytest.fixture
    def sample_user_id(self):
        return uuid4()

    @pytest.mark.asyncio
    async def test_compare_scenarios(
        self, service: CashFlowService, mock_db, sample_user_id
    ):
        """Sollte Szenario-Vergleich zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        comparison = await service.compare_scenarios(
            db=mock_db,
            company_id=sample_user_id,
            days_ahead=30,
        )

        assert "scenarios" in comparison
        assert "recommendation" in comparison
        assert "period_days" in comparison

        # Alle 3 Szenarien sollten vorhanden sein
        assert "optimistic" in comparison["scenarios"]
        assert "realistic" in comparison["scenarios"]
        assert "pessimistic" in comparison["scenarios"]

        # Jedes Szenario sollte die erforderlichen Metriken haben
        for scenario_name, scenario_data in comparison["scenarios"].items():
            assert "total_inflow" in scenario_data
            assert "total_outflow" in scenario_data
            assert "net_flow" in scenario_data
            assert "min_balance" in scenario_data
            assert "days_negative" in scenario_data


class TestCashFlowPaymentBehaviorWeights:
    """Tests fuer Zahlungsverhaltens-Gewichte."""

    def test_default_weights_exist(self):
        """Sollte Standard-Gewichte haben."""
        service = CashFlowService()

        assert "on_time" in service.PAYMENT_BEHAVIOR_WEIGHTS
        assert "late_7" in service.PAYMENT_BEHAVIOR_WEIGHTS
        assert "late_14" in service.PAYMENT_BEHAVIOR_WEIGHTS
        assert "late_30" in service.PAYMENT_BEHAVIOR_WEIGHTS
        assert "late_60" in service.PAYMENT_BEHAVIOR_WEIGHTS
        assert "default" in service.PAYMENT_BEHAVIOR_WEIGHTS

    def test_weights_are_decreasing(self):
        """Sollte abnehmende Gewichte fuer spaetere Zahlungen haben."""
        service = CashFlowService()
        weights = service.PAYMENT_BEHAVIOR_WEIGHTS

        assert weights["on_time"] >= weights["late_7"]
        assert weights["late_7"] >= weights["late_14"]
        assert weights["late_14"] >= weights["late_30"]
        assert weights["late_30"] >= weights["late_60"]


class TestForecastEnums:
    """Tests fuer Forecast Enums."""

    def test_forecast_period_values(self):
        """Sollte korrekte Perioden-Werte haben."""
        assert ForecastPeriod.DAILY.value == "daily"
        assert ForecastPeriod.WEEKLY.value == "weekly"
        assert ForecastPeriod.MONTHLY.value == "monthly"

    def test_forecast_scenario_values(self):
        """Sollte korrekte Szenario-Werte haben."""
        assert ForecastScenario.OPTIMISTIC.value == "optimistic"
        assert ForecastScenario.REALISTIC.value == "realistic"
        assert ForecastScenario.PESSIMISTIC.value == "pessimistic"

    def test_all_periods_count(self):
        """Sollte 3 Perioden haben."""
        assert len(ForecastPeriod) == 3

    def test_all_scenarios_count(self):
        """Sollte 3 Szenarien haben."""
        assert len(ForecastScenario) == 3
