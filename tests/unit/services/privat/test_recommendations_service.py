# -*- coding: utf-8 -*-
"""
Unit-Tests fuer RecommendationsService

Testet:
- Refinancing-Empfehlungen (Kredit-Zins > Markt)
- Rebalancing-Empfehlungen
- Versicherungs-Luecken-Erkennung
- Notgroschen-Pruefung
- Frist-Warnungen
- Wert-Aktualisierungs-Hinweise
- Fahrzeug-Wartungs-Erinnerungen
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.privat.recommendations_service import (
    RecommendationsService,
    get_recommendations_service,
    Recommendation,
    RecommendationsSummary,
    RecommendationPriority,
    RecommendationCategory,
    MARKET_INTEREST_RATES,
    REFINANCING_THRESHOLD,
    EMERGENCY_FUND_MONTHS_MIN,
)


class TestRefinancingRecommendations:
    """Tests fuer Refinancing-Empfehlungen."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        """Erstellt eine Service-Instanz."""
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_refinancing_high_rate_loan(
        self,
        service: RecommendationsService,
    ) -> None:
        """Empfehlung bei hohem Kreditzins."""
        loan = MagicMock()
        loan.id = uuid4()
        loan.name = "Hoher Zins Kredit"
        loan.loan_type = "ratenkredit"
        loan.interest_rate = Decimal("12.0")  # Deutlich ueber Markt (7%)
        loan.current_balance = Decimal("10000")
        loan.monthly_payment = Decimal("300")
        loan.is_active = True

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [loan]
        db_mock.execute.return_value = result_mock

        result = await service._check_refinancing_opportunities(db_mock, uuid4())

        assert len(result) == 1
        assert result[0].category == RecommendationCategory.REFINANCING
        assert result[0].priority == RecommendationPriority.CRITICAL  # 5% ueber Markt
        assert "Umschuldung" in result[0].title
        assert result[0].potential_savings is not None

    @pytest.mark.asyncio
    async def test_refinancing_good_rate_loan(
        self,
        service: RecommendationsService,
    ) -> None:
        """Keine Empfehlung bei gutem Kreditzins."""
        loan = MagicMock()
        loan.id = uuid4()
        loan.name = "Guter Kredit"
        loan.loan_type = "ratenkredit"
        loan.interest_rate = Decimal("7.5")  # Nur 0.5% ueber Markt
        loan.current_balance = Decimal("10000")
        loan.monthly_payment = Decimal("300")
        loan.is_active = True

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [loan]
        db_mock.execute.return_value = result_mock

        result = await service._check_refinancing_opportunities(db_mock, uuid4())

        assert len(result) == 0  # Keine Empfehlung

    @pytest.mark.asyncio
    async def test_refinancing_multiple_loans(
        self,
        service: RecommendationsService,
    ) -> None:
        """Mehrere Kredite mit unterschiedlichen Zinsen."""
        loan1 = MagicMock()
        loan1.id = uuid4()
        loan1.name = "Teurer Kredit"
        loan1.loan_type = "privatkredit"
        loan1.interest_rate = Decimal("15.0")  # Hoch
        loan1.current_balance = Decimal("5000")
        loan1.monthly_payment = Decimal("200")
        loan1.is_active = True

        loan2 = MagicMock()
        loan2.id = uuid4()
        loan2.name = "Guenstiger Kredit"
        loan2.loan_type = "autokredit"
        loan2.interest_rate = Decimal("5.0")  # Unter Markt
        loan2.current_balance = Decimal("8000")
        loan2.monthly_payment = Decimal("250")
        loan2.is_active = True

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [loan1, loan2]
        db_mock.execute.return_value = result_mock

        result = await service._check_refinancing_opportunities(db_mock, uuid4())

        # Nur der teure Kredit sollte eine Empfehlung bekommen
        assert len(result) == 1
        assert result[0].resource_name == "Teurer Kredit"


class TestInsuranceGaps:
    """Tests fuer Versicherungs-Luecken."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_insurance_gap_detected(
        self,
        service: RecommendationsService,
    ) -> None:
        """Erkennt fehlende essentielle Versicherungen."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        # Keine Versicherungen vorhanden
        result_mock.all.return_value = []
        db_mock.execute.return_value = result_mock

        result = await service._check_insurance_gaps(db_mock, uuid4())

        # Sollte Haftpflicht, Hausrat und BU vermissen
        assert len(result) >= 2
        categories = [r.title.lower() for r in result]
        assert any("haftpflicht" in cat for cat in categories)

    @pytest.mark.asyncio
    async def test_insurance_gap_with_existing(
        self,
        service: RecommendationsService,
    ) -> None:
        """Keine Luecke bei vorhandener Versicherung."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        # Alle essentiellen Versicherungen vorhanden. Der Service-Schluessel ist
        # "berufsunfähigkeit" (UTF-8-Umlaut); das Substring-Matching findet die
        # ASCII-Schreibweise "berufsunfaehigkeit" NICHT -> hier echte Schreibweise.
        result_mock.all.return_value = [
            ("haftpflicht",),
            ("hausrat",),
            ("berufsunfähigkeit",),
        ]
        db_mock.execute.return_value = result_mock

        result = await service._check_insurance_gaps(db_mock, uuid4())

        # Keine fehlenden essentiellen Versicherungen
        assert len(result) == 0


class TestEmergencyFund:
    """Tests fuer Notgroschen-Pruefung."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_emergency_fund_insufficient(
        self,
        service: RecommendationsService,
    ) -> None:
        """Warnung bei unzureichendem Notgroschen."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        # Nur 2000 EUR liquide Mittel
        result_mock.scalar.return_value = 2000
        db_mock.execute.return_value = result_mock

        result = await service._check_emergency_fund(db_mock, uuid4())

        # Bei 2500 EUR Ausgaben = weniger als 1 Monat
        assert len(result) == 1
        assert result[0].category == RecommendationCategory.EMERGENCY_FUND
        assert result[0].priority == RecommendationPriority.CRITICAL

    @pytest.mark.asyncio
    async def test_emergency_fund_sufficient(
        self,
        service: RecommendationsService,
    ) -> None:
        """Keine Warnung bei ausreichendem Notgroschen."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        # 20000 EUR liquide Mittel = ca. 8 Monate
        result_mock.scalar.return_value = 20000
        db_mock.execute.return_value = result_mock

        result = await service._check_emergency_fund(db_mock, uuid4())

        assert len(result) == 0


class TestDeadlineWarnings:
    """Tests fuer Frist-Warnungen."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_deadline_warning_critical(
        self,
        service: RecommendationsService,
    ) -> None:
        """Kritische Warnung bei Frist in 3 Tagen."""
        deadline = MagicMock()
        deadline.id = uuid4()
        deadline.title = "Wichtige Frist"
        deadline.description = "Muss erledigt werden"
        deadline.due_date = date.today() + timedelta(days=3)
        deadline.is_active = True
        deadline.is_completed = False

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [deadline]
        db_mock.execute.return_value = result_mock

        result = await service._check_upcoming_deadlines(db_mock, uuid4())

        assert len(result) == 1
        assert result[0].priority == RecommendationPriority.CRITICAL
        assert "3 Tagen" in result[0].title

    @pytest.mark.asyncio
    async def test_deadline_warning_medium(
        self,
        service: RecommendationsService,
    ) -> None:
        """Mittlere Warnung bei Frist in 20 Tagen."""
        deadline = MagicMock()
        deadline.id = uuid4()
        deadline.title = "Geplante Frist"
        deadline.description = "Noch Zeit"
        deadline.due_date = date.today() + timedelta(days=20)
        deadline.is_active = True
        deadline.is_completed = False

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [deadline]
        db_mock.execute.return_value = result_mock

        result = await service._check_upcoming_deadlines(db_mock, uuid4())

        assert len(result) == 1
        assert result[0].priority == RecommendationPriority.MEDIUM


class TestStaleValues:
    """Tests fuer veraltete Wert-Hinweise."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_stale_property_value(
        self,
        service: RecommendationsService,
    ) -> None:
        """Hinweis bei altem Immobilienwert."""
        prop = MagicMock()
        prop.id = uuid4()
        prop.name = "Meine Wohnung"
        prop.current_value = Decimal("250000")
        prop.last_kpi_calculation = datetime(2023, 1, 1, tzinfo=timezone.utc)
        prop.deleted_at = None

        db_mock = AsyncMock()

        # Properties Mock
        prop_result = MagicMock()
        prop_result.scalars.return_value.all.return_value = [prop]

        # Investments Mock (leer)
        inv_result = MagicMock()
        inv_result.scalars.return_value.all.return_value = []

        db_mock.execute.side_effect = [prop_result, inv_result]

        result = await service._check_stale_values(db_mock, uuid4())

        assert len(result) >= 1
        assert result[0].category == RecommendationCategory.VALUE_UPDATE


class TestVehicleMaintenance:
    """Tests fuer Fahrzeug-Wartungs-Erinnerungen."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_tuev_overdue(
        self,
        service: RecommendationsService,
    ) -> None:
        """Kritische Warnung bei ueberfaelligem TUeV."""
        vehicle = MagicMock()
        vehicle.id = uuid4()
        vehicle.name = "Mein Auto"
        vehicle.tuev_due = date.today() - timedelta(days=10)  # Ueberfaellig
        vehicle.inspection_due = None
        vehicle.is_active = True

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [vehicle]
        db_mock.execute.return_value = result_mock

        result = await service._check_vehicle_maintenance(db_mock, uuid4())

        assert len(result) == 1
        assert result[0].priority == RecommendationPriority.CRITICAL
        # Echter Titel nutzt UTF-8-Umlaut: "TÜV überfällig: ..."
        assert "überfällig" in result[0].title.lower()

    @pytest.mark.asyncio
    async def test_tuev_upcoming(
        self,
        service: RecommendationsService,
    ) -> None:
        """Warnung bei anstehendem TUeV."""
        vehicle = MagicMock()
        vehicle.id = uuid4()
        vehicle.name = "Mein Auto"
        vehicle.tuev_due = date.today() + timedelta(days=14)  # In 2 Wochen
        vehicle.inspection_due = None
        vehicle.is_active = True

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [vehicle]
        db_mock.execute.return_value = result_mock

        result = await service._check_vehicle_maintenance(db_mock, uuid4())

        assert len(result) == 1
        assert result[0].priority == RecommendationPriority.HIGH
        assert "14 Tagen" in result[0].title

    @pytest.mark.asyncio
    async def test_inspection_upcoming(
        self,
        service: RecommendationsService,
    ) -> None:
        """Warnung bei anstehender Inspektion."""
        vehicle = MagicMock()
        vehicle.id = uuid4()
        vehicle.name = "Mein Auto"
        vehicle.tuev_due = date.today() + timedelta(days=365)  # Weit weg
        vehicle.inspection_due = date.today() + timedelta(days=7)  # Bald
        vehicle.is_active = True

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [vehicle]
        db_mock.execute.return_value = result_mock

        result = await service._check_vehicle_maintenance(db_mock, uuid4())

        assert len(result) == 1
        assert "Inspektion" in result[0].title


class TestRecommendationsSummary:
    """Tests fuer Empfehlungs-Zusammenfassung."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_generate_recommendations_empty(
        self,
        service: RecommendationsService,
    ) -> None:
        """Leere Empfehlungen bei vollem Portfolio."""
        db_mock = AsyncMock()

        # Alle Checks geben leere Listen zurueck
        with patch.multiple(
            service,
            _check_refinancing_opportunities=AsyncMock(return_value=[]),
            _check_rebalancing_needs=AsyncMock(return_value=[]),
            _check_insurance_gaps=AsyncMock(return_value=[]),
            _check_emergency_fund=AsyncMock(return_value=[]),
            _check_upcoming_deadlines=AsyncMock(return_value=[]),
            _check_stale_values=AsyncMock(return_value=[]),
            _check_vehicle_maintenance=AsyncMock(return_value=[]),
        ):
            result = await service.generate_recommendations(db_mock, uuid4())

        assert isinstance(result, RecommendationsSummary)
        assert result.total_count == 0
        assert result.total_potential_savings == Decimal("0")
        assert len(result.critical) == 0
        assert len(result.top_recommendations) == 0

    @pytest.mark.asyncio
    async def test_generate_recommendations_with_items(
        self,
        service: RecommendationsService,
    ) -> None:
        """Empfehlungen mit verschiedenen Prioritaeten."""
        critical_rec = Recommendation(
            id="test_critical",
            category=RecommendationCategory.REFINANCING,
            priority=RecommendationPriority.CRITICAL,
            title="Kritische Empfehlung",
            description="Dringend",
            impact="Hoch",
            resource_type="loan",
            resource_id=uuid4(),
            resource_name="Test Kredit",
            potential_savings=Decimal("5000"),
            current_value=None,
            recommended_value=None,
            suggested_actions=["Aktion 1"],
        )

        medium_rec = Recommendation(
            id="test_medium",
            category=RecommendationCategory.REBALANCING,
            priority=RecommendationPriority.MEDIUM,
            title="Mittlere Empfehlung",
            description="Normal",
            impact="Mittel",
            resource_type="portfolio",
            resource_id=None,
            resource_name="Portfolio",
            potential_savings=None,
            current_value=None,
            recommended_value=None,
            suggested_actions=["Aktion 2"],
        )

        db_mock = AsyncMock()

        with patch.multiple(
            service,
            _check_refinancing_opportunities=AsyncMock(return_value=[critical_rec]),
            _check_rebalancing_needs=AsyncMock(return_value=[medium_rec]),
            _check_insurance_gaps=AsyncMock(return_value=[]),
            _check_emergency_fund=AsyncMock(return_value=[]),
            _check_upcoming_deadlines=AsyncMock(return_value=[]),
            _check_stale_values=AsyncMock(return_value=[]),
            _check_vehicle_maintenance=AsyncMock(return_value=[]),
        ):
            result = await service.generate_recommendations(db_mock, uuid4())

        assert result.total_count == 2
        assert len(result.critical) == 1
        assert len(result.medium) == 1
        assert result.total_potential_savings == Decimal("5000")
        assert len(result.top_recommendations) == 1  # Nur der mit Savings


class TestRecommendationPriority:
    """Tests fuer Prioritaets-Logik."""

    def test_priority_ordering(self) -> None:
        """Prioritaeten sind korrekt geordnet."""
        priorities = [
            RecommendationPriority.CRITICAL,
            RecommendationPriority.HIGH,
            RecommendationPriority.MEDIUM,
            RecommendationPriority.LOW,
            RecommendationPriority.INFO,
        ]

        assert priorities[0].value == "kritisch"
        assert priorities[1].value == "hoch"
        assert priorities[2].value == "mittel"
        assert priorities[3].value == "niedrig"
        assert priorities[4].value == "info"


class TestMarketRates:
    """Tests fuer Markt-Zinssaetze."""

    def test_market_rates_defined(self) -> None:
        """Marktzinsen sind definiert."""
        assert "hypothek" in MARKET_INTEREST_RATES
        assert "autokredit" in MARKET_INTEREST_RATES
        assert "default" in MARKET_INTEREST_RATES

    def test_market_rates_reasonable(self) -> None:
        """Marktzinsen sind realistisch."""
        for rate_type, rate in MARKET_INTEREST_RATES.items():
            assert Decimal("0") <= rate <= Decimal("20")

    def test_refinancing_threshold(self) -> None:
        """Refinancing-Schwellenwert ist definiert."""
        assert REFINANCING_THRESHOLD == Decimal("1.0")


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_instance(self) -> None:
        """Service ist ein Singleton."""
        service1 = RecommendationsService()
        service2 = RecommendationsService()
        assert service1 is service2

    def test_get_recommendations_service(self) -> None:
        """Factory-Funktion gibt Singleton zurueck."""
        service1 = get_recommendations_service()
        service2 = get_recommendations_service()
        assert service1 is service2
        assert isinstance(service1, RecommendationsService)


class TestBatchOperations:
    """Tests fuer Batch-Operationen."""

    @pytest.fixture
    def service(self) -> RecommendationsService:
        return RecommendationsService()

    @pytest.mark.asyncio
    async def test_generate_all_recommendations(
        self,
        service: RecommendationsService,
    ) -> None:
        """Batch-Generierung fuer alle Spaces."""
        space_ids = [uuid4() for _ in range(3)]

        db_mock = AsyncMock()

        # Space-IDs zurueckgeben
        spaces_result = MagicMock()
        spaces_result.all.return_value = [(sid,) for sid in space_ids]
        db_mock.execute.return_value = spaces_result

        with patch.object(
            service,
            'generate_recommendations',
            new_callable=AsyncMock,
        ) as mock_gen:
            mock_summary = MagicMock()
            mock_summary.total_count = 5
            mock_gen.return_value = mock_summary

            result = await service.generate_all_recommendations(db_mock)

        assert result["total_spaces"] == 3
        assert result["processed"] == 3
        assert result["total_recommendations"] == 15
        assert result["errors"] == 0
