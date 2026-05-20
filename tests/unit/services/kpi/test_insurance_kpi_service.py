"""Tests fuer den Insurance KPI Service.

Testet die Berechnung aller Versicherungs-KPIs:
- Deckungsluecken-Analyse
- Kuendigungsfristen
- Praemien-Entwicklung
- Risiko-Bewertung
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.kpi.insurance_kpi_service import (
    InsuranceKPIService,
    InsuranceGapResult,
    CancellationInfo,
    PremiumTrend,
)


class TestCoverageGapCalculations:
    """Tests fuer Deckungsluecken-Berechnungen."""

    def setup_method(self) -> None:
        """Setup fuer jeden Test."""
        self.service = InsuranceKPIService(db=MagicMock())

    def test_haftpflicht_coverage_gap(self) -> None:
        """Haftpflicht-Deckungsluecke wird erkannt."""
        mock_insurance = MagicMock()
        mock_insurance.insurance_type = "haftpflicht_privat"
        mock_insurance.coverage_amount = Decimal("5000000")  # 5 Mio - unter Empfehlung

        recommended = self.service._get_recommended_coverage(mock_insurance)
        gap = recommended - mock_insurance.coverage_amount

        # Empfohlen: 10 Mio, aktuell: 5 Mio = 5 Mio Luecke
        assert recommended == Decimal("10000000")
        assert gap == Decimal("5000000")

    def test_no_gap_when_sufficient_coverage(self) -> None:
        """Keine Luecke bei ausreichender Deckung."""
        mock_insurance = MagicMock()
        mock_insurance.insurance_type = "haftpflicht_privat"
        mock_insurance.coverage_amount = Decimal("15000000")  # 15 Mio - ueber Empfehlung

        recommended = self.service._get_recommended_coverage(mock_insurance)
        gap = max(recommended - mock_insurance.coverage_amount, Decimal("0"))

        assert gap == Decimal("0")

    def test_gap_severity_critical(self) -> None:
        """Kritische Schwere bei grosser Luecke."""
        gap = Decimal("8000000")  # 8 Mio Luecke
        recommended = Decimal("10000000")  # 10 Mio empfohlen

        result = self.service._calc_severity(gap, recommended)

        # 80% Luecke = kritisch
        assert result == "critical"

    def test_gap_severity_high(self) -> None:
        """Hohe Schwere bei 30% Luecke."""
        gap = Decimal("3000000")  # 3 Mio Luecke
        recommended = Decimal("10000000")  # 10 Mio empfohlen

        result = self.service._calc_severity(gap, recommended)

        # 30% Luecke = high
        assert result == "high"

    def test_gap_severity_medium(self) -> None:
        """Mittlere Schwere bei 15% Luecke."""
        gap = Decimal("1500000")  # 1.5 Mio Luecke
        recommended = Decimal("10000000")  # 10 Mio empfohlen

        result = self.service._calc_severity(gap, recommended)

        # 15% Luecke = medium
        assert result == "medium"

    def test_gap_severity_low(self) -> None:
        """Niedrige Schwere bei kleiner Luecke."""
        gap = Decimal("500000")  # 0.5 Mio Luecke
        recommended = Decimal("10000000")  # 10 Mio empfohlen

        result = self.service._calc_severity(gap, recommended)

        # 5% Luecke = low
        assert result == "low"

    def test_gap_severity_none(self) -> None:
        """Keine Luecke wenn gap <= 0."""
        gap = Decimal("-100000")  # Ueberschuss
        recommended = Decimal("10000000")

        result = self.service._calc_severity(gap, recommended)

        assert result == "none"


class TestCancellationDeadlines:
    """Tests fuer Kuendigungsfristen."""

    def setup_method(self) -> None:
        self.service = InsuranceKPIService(db=MagicMock())

    def test_next_anniversary_future(self) -> None:
        """Naechster Jahrestag liegt in der Zukunft."""
        # Startdatum in der Vergangenheit
        start_date = date(2022, 6, 15)

        result = self.service._calc_next_anniversary(start_date)

        # Naechster Jahrestag sollte in der Zukunft liegen
        assert result > date.today()
        assert result.month == 6
        assert result.day == 15

    def test_next_anniversary_this_year(self) -> None:
        """Jahrestag dieses Jahr wenn noch nicht vorbei."""
        # Startdatum im Dezember - sollte dieses Jahr sein wenn wir im Januar sind
        # oder naechstes Jahr wenn wir nach dem Datum sind
        today = date.today()
        future_month = (today.month % 12) + 1  # Immer naechster Monat
        start_date = date(2020, future_month, 15)

        result = self.service._calc_next_anniversary(start_date)

        assert result >= today

    @pytest.mark.asyncio
    async def test_cancellation_deadline_calculation(self) -> None:
        """Kuendigungsfrist wird korrekt berechnet."""
        insurance_id = uuid4()
        space_id = uuid4()
        mock_insurance = MagicMock()
        mock_insurance.end_date = date.today() + timedelta(days=120)  # In 4 Monaten
        mock_insurance.cancellation_period_months = 3
        mock_insurance.start_date = date(2022, 1, 1)

        with patch.object(
            self.service, "_get_insurance", return_value=mock_insurance
        ):
            result = await self.service.calculate_cancellation_deadline(
                insurance_id, space_id, persist=False
            )

            assert isinstance(result, CancellationInfo)
            # Deadline: 3 Monate (90 Tage) vor Ende
            expected_deadline = mock_insurance.end_date - timedelta(days=90)
            assert result.cancellation_deadline == expected_deadline

    @pytest.mark.asyncio
    async def test_cancellation_deadline_urgent(self) -> None:
        """Dringende Kuendigung wird erkannt."""
        insurance_id = uuid4()
        space_id = uuid4()
        mock_insurance = MagicMock()
        # Deadline ist in 20 Tagen
        mock_insurance.end_date = date.today() + timedelta(days=50)
        mock_insurance.cancellation_period_months = 1  # 30 Tage Frist
        mock_insurance.start_date = date(2022, 1, 1)

        with patch.object(
            self.service, "_get_insurance", return_value=mock_insurance
        ):
            result = await self.service.calculate_cancellation_deadline(
                insurance_id, space_id, persist=False
            )

            # Deadline in 20 Tagen = dringend
            assert result.is_urgent is True


class TestPremiumCalculations:
    """Tests fuer Praemien-Berechnungen."""

    def setup_method(self) -> None:
        self.service = InsuranceKPIService(db=MagicMock())

    def test_estimate_premium_increase(self) -> None:
        """Schaetzung der Praemienerhoehung fuer Deckungserweiterung."""
        mock_insurance = MagicMock()
        mock_insurance.premium_amount = Decimal("500")
        mock_insurance.premium_frequency = "yearly"
        mock_insurance.coverage_amount = Decimal("5000000")

        gap = Decimal("5000000")  # Verdopplung der Deckung

        result = self.service._estimate_premium_increase(mock_insurance, gap)

        # Bei Verdopplung der Deckung: ca. 100% Praemienerhoehung (linear)
        # 500 / 5000000 * 5000000 = 500
        assert result == Decimal("500.00")

    def test_estimate_premium_no_gap(self) -> None:
        """Keine Praemienerhoehung bei keiner Luecke."""
        mock_insurance = MagicMock()
        mock_insurance.premium_amount = Decimal("500")
        mock_insurance.premium_frequency = "yearly"
        mock_insurance.coverage_amount = Decimal("10000000")

        gap = Decimal("0")

        result = self.service._estimate_premium_increase(mock_insurance, gap)

        assert result == Decimal("0")

    def test_premium_trend_rising(self) -> None:
        """Praemientrend wird erkannt - steigend."""
        # Mock mit echten Werten statt MagicMock-Attributen
        mock_current = MagicMock()
        mock_current.insurance_type = "haftpflicht_privat"
        mock_current.premium_amount = Decimal("600")
        mock_current.premium_frequency = "yearly"

        mock_history = MagicMock()
        mock_history.insurance_type = "haftpflicht_privat"
        mock_history.premium_amount = Decimal("500")
        mock_history.premium_frequency = "yearly"

        result = self.service._calc_premium_trend(
            "haftpflicht_privat", [mock_current], [mock_history]
        )

        assert result is not None
        assert result.trend_direction == "rising"
        assert result.change_amount == Decimal("100")

    def test_premium_trend_stable(self) -> None:
        """Praemientrend wird erkannt - stabil."""
        mock_current = MagicMock()
        mock_current.insurance_type = "rechtsschutz"
        mock_current.premium_amount = Decimal("300")
        mock_current.premium_frequency = "yearly"

        mock_history = MagicMock()
        mock_history.insurance_type = "rechtsschutz"
        mock_history.premium_amount = Decimal("300")
        mock_history.premium_frequency = "yearly"

        result = self.service._calc_premium_trend(
            "rechtsschutz", [mock_current], [mock_history]
        )

        assert result is not None
        assert result.trend_direction == "stable"

    def test_premium_trend_falling(self) -> None:
        """Praemientrend wird erkannt - fallend."""
        mock_current = MagicMock()
        mock_current.insurance_type = "hausrat"
        mock_current.premium_amount = Decimal("200")
        mock_current.premium_frequency = "yearly"

        mock_history = MagicMock()
        mock_history.insurance_type = "hausrat"
        mock_history.premium_amount = Decimal("250")
        mock_history.premium_frequency = "yearly"

        result = self.service._calc_premium_trend(
            "hausrat", [mock_current], [mock_history]
        )

        assert result is not None
        assert result.trend_direction == "falling"


class TestRiskExposure:
    """Tests fuer Risiko-Bewertung."""

    def setup_method(self) -> None:
        self.service = InsuranceKPIService(db=MagicMock())

    def test_risk_exposure_haftpflicht(self) -> None:
        """Risiko-Exposure fuer Haftpflicht."""
        insurance_type = "haftpflicht_privat"
        gap = Decimal("5000000")

        result = self.service._calc_risk_exposure(insurance_type, gap)

        assert "5,000,000" in result or "5000000" in result
        assert "haften" in result.lower() or "deckungsluecke" in result.lower()

    def test_risk_exposure_hausrat(self) -> None:
        """Risiko-Exposure fuer Hausrat."""
        insurance_type = "hausrat"
        gap = Decimal("30000")

        result = self.service._calc_risk_exposure(insurance_type, gap)

        assert "30,000" in result or "30000" in result

    def test_risk_exposure_no_gap(self) -> None:
        """Kein Risiko bei keiner Luecke."""
        insurance_type = "haftpflicht_privat"
        gap = Decimal("0")

        result = self.service._calc_risk_exposure(insurance_type, gap)

        assert "abgedeckt" in result.lower()


class TestRecommendedCoverage:
    """Tests fuer empfohlene Deckungssummen."""

    def setup_method(self) -> None:
        self.service = InsuranceKPIService(db=MagicMock())

    def test_haftpflicht_fixed_recommendation(self) -> None:
        """Haftpflicht hat fixe Empfehlung."""
        mock_insurance = MagicMock()
        mock_insurance.insurance_type = "haftpflicht_privat"
        mock_insurance.coverage_amount = Decimal("5000000")

        result = self.service._get_recommended_coverage(mock_insurance)

        assert result == Decimal("10000000")  # 10 Mio empfohlen

    def test_hausrat_sqm_based(self) -> None:
        """Hausrat wird nach Wohnflaeche berechnet."""
        mock_insurance = MagicMock()
        mock_insurance.insurance_type = "hausrat"
        # Service nutzt coverage_details dict, nicht living_space_sqm direkt
        mock_insurance.coverage_details = {"living_space_sqm": 120}

        result = self.service._get_recommended_coverage(mock_insurance)

        # 120 m2 * 650 EUR/m2 = 78.000 EUR
        assert result == Decimal("78000")

    def test_hausrat_default_sqm(self) -> None:
        """Hausrat mit Default-Wohnflaeche."""
        mock_insurance = MagicMock()
        mock_insurance.insurance_type = "hausrat"
        # Leere coverage_details = Default 100m2
        mock_insurance.coverage_details = {}

        result = self.service._get_recommended_coverage(mock_insurance)

        # Default: 100 m2 * 650 = 65.000
        assert result == Decimal("65000")


class TestInsuranceKPIServiceIntegration:
    """Integrationstests fuer den gesamten Service."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_db: AsyncMock) -> InsuranceKPIService:
        return InsuranceKPIService(db=mock_db)

    @pytest.mark.asyncio
    async def test_calculate_coverage_gaps_returns_result(
        self, service: InsuranceKPIService
    ) -> None:
        """calculate_coverage_gaps gibt InsuranceGapResult zurueck."""
        insurance_id = uuid4()
        space_id = uuid4()
        mock_insurance = MagicMock()
        mock_insurance.id = insurance_id
        mock_insurance.insurance_type = "haftpflicht_privat"
        mock_insurance.coverage_amount = Decimal("5000000")
        mock_insurance.premium_amount = Decimal("500")
        mock_insurance.premium_frequency = "yearly"
        mock_insurance.contract_start_date = date(2022, 1, 1)
        mock_insurance.contract_end_date = date.today() + timedelta(days=180)
        mock_insurance.notice_period_months = 3

        with patch.object(
            service, "_get_insurance", return_value=mock_insurance
        ):
            result = await service.calculate_coverage_gaps(insurance_id, space_id)

            assert isinstance(result, InsuranceGapResult)
            assert result.current_coverage == Decimal("5000000")
            assert result.gap_amount == Decimal("5000000")  # 10M - 5M
            assert result.gap_severity in ["low", "medium", "high", "critical"]

    @pytest.mark.asyncio
    async def test_calculate_premium_trends(
        self, service: InsuranceKPIService
    ) -> None:
        """calculate_premium_trends gibt PremiumTrend Liste zurueck."""
        space_id = uuid4()

        # Mock mit korrekten Attributen (premium_amount, premium_frequency)
        mock_haftpflicht = MagicMock()
        mock_haftpflicht.id = uuid4()
        mock_haftpflicht.insurance_type = "haftpflicht_privat"
        mock_haftpflicht.coverage_amount = Decimal("10000000")
        mock_haftpflicht.premium_amount = Decimal("600")
        mock_haftpflicht.premium_frequency = "yearly"

        mock_rechtsschutz = MagicMock()
        mock_rechtsschutz.id = uuid4()
        mock_rechtsschutz.insurance_type = "rechtsschutz"
        mock_rechtsschutz.coverage_amount = Decimal("500000")
        mock_rechtsschutz.premium_amount = Decimal("300")
        mock_rechtsschutz.premium_frequency = "yearly"

        mock_insurances = [mock_haftpflicht, mock_rechtsschutz]

        mock_history_haftpflicht = MagicMock()
        mock_history_haftpflicht.insurance_type = "haftpflicht_privat"
        mock_history_haftpflicht.premium_amount = Decimal("500")
        mock_history_haftpflicht.premium_frequency = "yearly"

        mock_history_rechtsschutz = MagicMock()
        mock_history_rechtsschutz.insurance_type = "rechtsschutz"
        mock_history_rechtsschutz.premium_amount = Decimal("300")
        mock_history_rechtsschutz.premium_frequency = "yearly"

        mock_history = [mock_history_haftpflicht, mock_history_rechtsschutz]

        with patch.object(
            service, "_get_all_insurances", return_value=mock_insurances
        ), patch.object(
            service, "_get_premium_history", return_value=mock_history
        ):
            result = await service.calculate_premium_trends(space_id)

            assert isinstance(result, list)
            assert len(result) == 2
            assert all(isinstance(t, PremiumTrend) for t in result)
