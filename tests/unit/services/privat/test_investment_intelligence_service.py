# -*- coding: utf-8 -*-
"""
Unit-Tests fuer InvestmentIntelligenceService

Testet:
- Investment-Performance-Berechnung (Absolut, %, CAGR)
- Portfolio-Allokation
- Diversifikations-Analyse (Herfindahl-Index)
- Risiko-Profil-Bestimmung
- Rebalancing-Empfehlungen
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.privat.investment_intelligence_service import (
    InvestmentIntelligenceService,
    get_investment_intelligence_service,
    InvestmentPerformance,
    PortfolioAllocation,
    DiversificationAnalysis,
    RiskProfile,
    PortfolioAnalytics,
    INVESTMENT_TYPE_RISK_SCORES,
    RISK_CATEGORIES,
)


class TestInvestmentPerformanceCalculation:
    """Tests fuer Investment-Performance-Berechnung."""

    @pytest.fixture
    def service(self) -> InvestmentIntelligenceService:
        """Erstellt eine Service-Instanz."""
        return InvestmentIntelligenceService()

    @pytest.fixture
    def mock_investment(self) -> MagicMock:
        """Erstellt ein Mock-Investment."""
        investment = MagicMock()
        investment.id = uuid4()
        investment.name = "Test ETF"
        investment.purchase_value = Decimal("10000")
        investment.current_value = Decimal("12000")
        investment.purchase_date = date.today() - timedelta(days=365)
        investment.investment_type = "etf"
        return investment

    def test_calculate_single_performance_basic(
        self,
        service: InvestmentIntelligenceService,
        mock_investment: MagicMock,
    ) -> None:
        """Grundlegende Performance-Berechnung."""
        result = service._calculate_single_performance(mock_investment)

        assert isinstance(result, InvestmentPerformance)
        assert result.investment_id == mock_investment.id
        assert result.investment_name == "Test ETF"
        assert result.purchase_value == Decimal("10000")
        assert result.current_value == Decimal("12000")
        assert result.absolute_gain == Decimal("2000")
        assert result.percentage_gain == Decimal("20.00")
        assert result.holding_days == 365
        assert result.risk_score == 45  # ETF Risiko-Score
        assert result.risk_category == "moderat"

    def test_calculate_single_performance_negative(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Performance-Berechnung bei Verlust."""
        investment = MagicMock()
        investment.id = uuid4()
        investment.name = "Verlust-Aktie"
        investment.purchase_value = Decimal("10000")
        investment.current_value = Decimal("7000")
        investment.purchase_date = date.today() - timedelta(days=180)
        investment.investment_type = "aktie"

        result = service._calculate_single_performance(investment)

        assert result.absolute_gain == Decimal("-3000")
        assert result.percentage_gain == Decimal("-30.00")
        assert result.risk_score == 70  # Aktie Risiko-Score
        assert result.risk_category == "riskant"

    def test_calculate_single_performance_cagr(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """CAGR-Berechnung ueber mehrere Jahre."""
        investment = MagicMock()
        investment.id = uuid4()
        investment.name = "Langzeit-Investment"
        investment.purchase_value = Decimal("10000")
        investment.current_value = Decimal("20000")  # Verdoppelung
        investment.purchase_date = date.today() - timedelta(days=5 * 365)  # 5 Jahre
        investment.investment_type = "aktie"

        result = service._calculate_single_performance(investment)

        # CAGR bei Verdoppelung in 5 Jahren: ca. 14.87%
        assert result.cagr is not None
        assert Decimal("14") <= result.cagr <= Decimal("16")

    def test_calculate_single_performance_no_purchase_date(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Performance ohne Kaufdatum."""
        investment = MagicMock()
        investment.id = uuid4()
        investment.name = "Ohne Datum"
        investment.purchase_value = Decimal("5000")
        investment.current_value = Decimal("6000")
        investment.purchase_date = None
        investment.investment_type = "tagesgeld"

        result = service._calculate_single_performance(investment)

        assert result.holding_days == 0
        assert result.cagr is None
        assert result.risk_score == 5  # Tagesgeld

    def test_calculate_single_performance_zero_purchase(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Performance mit Kaufwert 0."""
        investment = MagicMock()
        investment.id = uuid4()
        investment.name = "Geschenk"
        investment.purchase_value = Decimal("0")
        investment.current_value = Decimal("1000")
        investment.purchase_date = date.today() - timedelta(days=30)
        investment.investment_type = "sonstige"

        result = service._calculate_single_performance(investment)

        assert result.percentage_gain == Decimal("0")  # Division durch 0 vermieden

    @pytest.mark.asyncio
    async def test_calculate_investment_performance_not_found(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Performance-Berechnung fuer nicht existierendes Investment."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        db_mock.execute.return_value = result_mock

        result = await service.calculate_investment_performance(db_mock, uuid4())

        assert result is None


class TestPortfolioAllocation:
    """Tests fuer Portfolio-Allokation."""

    @pytest.fixture
    def service(self) -> InvestmentIntelligenceService:
        return InvestmentIntelligenceService()

    @pytest.mark.asyncio
    async def test_calculate_allocation_empty_portfolio(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Allokation bei leerem Portfolio."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = result_mock

        result = await service.calculate_allocation(db_mock, uuid4())

        assert isinstance(result, PortfolioAllocation)
        assert result.total_value == Decimal("0")
        assert result.investment_count == 0

    @pytest.mark.asyncio
    async def test_calculate_allocation_single_investment(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Allokation mit einem Investment."""
        investment = MagicMock()
        investment.current_value = Decimal("10000")
        investment.investment_type = "etf"

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [investment]
        db_mock.execute.return_value = result_mock

        result = await service.calculate_allocation(db_mock, uuid4())

        assert result.total_value == Decimal("10000")
        assert result.investment_count == 1
        assert result.by_type_percentages["etf"] == Decimal("100.0")
        assert result.by_risk_category_percentages["moderat"] == Decimal("100.0")

    @pytest.mark.asyncio
    async def test_calculate_allocation_multiple_investments(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Allokation mit mehreren Investments."""
        inv1 = MagicMock()
        inv1.current_value = Decimal("5000")
        inv1.investment_type = "tagesgeld"

        inv2 = MagicMock()
        inv2.current_value = Decimal("3000")
        inv2.investment_type = "etf"

        inv3 = MagicMock()
        inv3.current_value = Decimal("2000")
        inv3.investment_type = "aktie"

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [inv1, inv2, inv3]
        db_mock.execute.return_value = result_mock

        result = await service.calculate_allocation(db_mock, uuid4())

        assert result.total_value == Decimal("10000")
        assert result.investment_count == 3
        assert result.by_type_percentages["tagesgeld"] == Decimal("50.0")
        assert result.by_type_percentages["etf"] == Decimal("30.0")
        assert result.by_type_percentages["aktie"] == Decimal("20.0")


class TestDiversificationAnalysis:
    """Tests fuer Diversifikations-Analyse."""

    @pytest.fixture
    def service(self) -> InvestmentIntelligenceService:
        return InvestmentIntelligenceService()

    @pytest.mark.asyncio
    async def test_analyze_diversification_empty(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Diversifikation bei leerem Portfolio."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = result_mock

        result = await service.analyze_diversification(db_mock, uuid4())

        assert result.herfindahl_index == Decimal("10000")
        assert result.diversification_score == Decimal("0")
        assert result.rating == "kritisch"

    @pytest.mark.asyncio
    async def test_analyze_diversification_single_position(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Diversifikation mit einer Position (keine Diversifikation)."""
        investment = MagicMock()
        investment.name = "Einziges Investment"
        investment.current_value = Decimal("10000")
        investment.investment_type = "aktie"

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [investment]
        db_mock.execute.return_value = result_mock

        result = await service.analyze_diversification(db_mock, uuid4())

        # HHI = 10000 (100%^2 * 10000) fuer eine Position
        assert result.herfindahl_index == Decimal("10000")
        assert result.largest_position_percentage == Decimal("100.0")
        assert result.rating in ["kritisch", "schlecht"]

    @pytest.mark.asyncio
    async def test_analyze_diversification_well_diversified(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Gut diversifiziertes Portfolio."""
        investments = []
        types = ["tagesgeld", "etf", "aktie", "anleihe", "immobilienfonds"]

        for i, inv_type in enumerate(types):
            inv = MagicMock()
            inv.name = f"Investment {i}"
            inv.current_value = Decimal("2000")  # Gleichmaessig verteilt
            inv.investment_type = inv_type
            investments.append(inv)

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = investments
        db_mock.execute.return_value = result_mock

        result = await service.analyze_diversification(db_mock, uuid4())

        # HHI = 5 * (20%^2) * 10000 = 2000
        assert result.herfindahl_index == Decimal("2000")
        assert result.unique_types == 5
        assert result.largest_position_percentage == Decimal("20.0")
        assert result.rating in ["gut", "moderat"]

    def test_rate_diversification(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Diversifikations-Rating."""
        # Sehr gut: HHI < 1000, 5+ Typen, groesste Position <= 25%
        assert service._rate_diversification(Decimal("800"), 6, Decimal("20")) == "sehr_gut"

        # Gut
        assert service._rate_diversification(Decimal("1200"), 4, Decimal("30")) == "gut"

        # Moderat
        assert service._rate_diversification(Decimal("2000"), 3, Decimal("40")) == "moderat"

        # Schlecht
        assert service._rate_diversification(Decimal("3500"), 2, Decimal("60")) == "schlecht"

        # Kritisch
        assert service._rate_diversification(Decimal("5000"), 1, Decimal("80")) == "kritisch"


class TestRiskProfile:
    """Tests fuer Risiko-Profil-Analyse."""

    @pytest.fixture
    def service(self) -> InvestmentIntelligenceService:
        return InvestmentIntelligenceService()

    @pytest.mark.asyncio
    async def test_analyze_risk_profile_empty(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Risiko-Profil bei leerem Portfolio."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = result_mock

        result = await service.analyze_risk_profile(db_mock, uuid4())

        assert result.risk_category == "unbestimmt"
        assert result.volatility_estimate == "unbekannt"

    @pytest.mark.asyncio
    async def test_analyze_risk_profile_conservative(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Konservatives Risiko-Profil."""
        inv = MagicMock()
        inv.current_value = Decimal("10000")
        inv.investment_type = "tagesgeld"  # Risiko-Score: 5

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [inv]
        db_mock.execute.return_value = result_mock

        result = await service.analyze_risk_profile(db_mock, uuid4())

        assert result.weighted_risk_score < Decimal("25")
        assert result.risk_category == "konservativ"
        assert result.volatility_estimate == "niedrig"
        assert result.safe_percentage == Decimal("100.0")

    @pytest.mark.asyncio
    async def test_analyze_risk_profile_aggressive(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Aggressives Risiko-Profil."""
        inv = MagicMock()
        inv.current_value = Decimal("10000")
        inv.investment_type = "krypto"  # Risiko-Score: 95

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [inv]
        db_mock.execute.return_value = result_mock

        result = await service.analyze_risk_profile(db_mock, uuid4())

        assert result.weighted_risk_score >= Decimal("65")
        assert result.risk_category == "aggressiv"
        assert result.volatility_estimate == "sehr_hoch"
        assert result.risky_percentage == Decimal("100.0")

    def test_determine_portfolio_risk_category(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Portfolio-Risikokategorie bestimmen."""
        assert service._determine_portfolio_risk_category(Decimal("10")) == "konservativ"
        assert service._determine_portfolio_risk_category(Decimal("30")) == "ausgewogen"
        assert service._determine_portfolio_risk_category(Decimal("55")) == "wachstum"
        assert service._determine_portfolio_risk_category(Decimal("80")) == "aggressiv"

    def test_estimate_volatility(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Volatilitaets-Schaetzung."""
        assert service._estimate_volatility(Decimal("10")) == "niedrig"
        assert service._estimate_volatility(Decimal("30")) == "moderat"
        assert service._estimate_volatility(Decimal("55")) == "hoch"
        assert service._estimate_volatility(Decimal("85")) == "sehr_hoch"


class TestRebalancing:
    """Tests fuer Rebalancing-Empfehlungen."""

    @pytest.fixture
    def service(self) -> InvestmentIntelligenceService:
        return InvestmentIntelligenceService()

    @pytest.mark.asyncio
    async def test_generate_rebalancing_no_investments(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Rebalancing bei leerem Portfolio."""
        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db_mock.execute.return_value = result_mock

        result = await service.generate_rebalancing_recommendations(db_mock, uuid4())

        assert result == []

    @pytest.mark.asyncio
    async def test_generate_rebalancing_balanced(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Kein Rebalancing noetig bei ausgeglichenem Portfolio."""
        # Ausgewogenes Portfolio: 40% sicher, 40% moderat, 20% riskant
        inv1 = MagicMock()
        inv1.current_value = Decimal("4000")
        inv1.investment_type = "tagesgeld"

        inv2 = MagicMock()
        inv2.current_value = Decimal("4000")
        inv2.investment_type = "etf"

        inv3 = MagicMock()
        inv3.current_value = Decimal("2000")
        inv3.investment_type = "aktie"

        db_mock = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [inv1, inv2, inv3]
        db_mock.execute.return_value = result_mock

        result = await service.generate_rebalancing_recommendations(
            db_mock, uuid4(), target_profile="ausgewogen"
        )

        # Keine signifikanten Abweichungen
        assert len(result) == 0


class TestRiskCategories:
    """Tests fuer Risiko-Kategorien-Zuordnung."""

    @pytest.fixture
    def service(self) -> InvestmentIntelligenceService:
        return InvestmentIntelligenceService()

    def test_get_risk_category_safe(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Sichere Investment-Typen."""
        safe_types = ["tagesgeld", "festgeld", "sparbuch", "anleihe"]
        for inv_type in safe_types:
            assert service._get_risk_category(inv_type) == "sicher"

    def test_get_risk_category_moderate(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Moderate Investment-Typen."""
        moderate_types = ["etf", "indexfonds", "mischfonds"]
        for inv_type in moderate_types:
            assert service._get_risk_category(inv_type) == "moderat"

    def test_get_risk_category_risky(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Riskante Investment-Typen."""
        risky_types = ["aktie", "krypto", "bitcoin", "optionen"]
        for inv_type in risky_types:
            assert service._get_risk_category(inv_type) == "riskant"

    def test_get_risk_category_unknown(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Unbekannter Investment-Typ faellt auf Score zurueck."""
        # "sonstige" hat Score 50 -> moderat
        result = service._get_risk_category("sonstige")
        assert result == "moderat"


class TestPortfolioHealthScore:
    """Tests fuer Portfolio-Health-Score-Berechnung."""

    @pytest.fixture
    def service(self) -> InvestmentIntelligenceService:
        return InvestmentIntelligenceService()

    def test_calculate_portfolio_health_score_excellent(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Exzellenter Health Score."""
        diversification = MagicMock()
        diversification.diversification_score = Decimal("90")

        risk_profile = MagicMock()
        risk_profile.risk_category = "ausgewogen"

        score = service._calculate_portfolio_health_score(
            diversification,
            risk_profile,
            gain_pct=Decimal("25"),  # Gute Performance
            investment_count=12,  # Viele Investments
        )

        # Maximale Punkte: 40 (Div) + 15 (Count) + 25 (Perf) + 20 (Risk) = 100
        assert score >= Decimal("80")

    def test_calculate_portfolio_health_score_poor(
        self,
        service: InvestmentIntelligenceService,
    ) -> None:
        """Schlechter Health Score."""
        diversification = MagicMock()
        diversification.diversification_score = Decimal("10")

        risk_profile = MagicMock()
        risk_profile.risk_category = "aggressiv"

        score = service._calculate_portfolio_health_score(
            diversification,
            risk_profile,
            gain_pct=Decimal("-20"),  # Verlust
            investment_count=1,  # Nur ein Investment
        )

        assert score <= Decimal("30")


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_instance(self) -> None:
        """Service ist ein Singleton."""
        service1 = InvestmentIntelligenceService()
        service2 = InvestmentIntelligenceService()
        assert service1 is service2

    def test_get_investment_intelligence_service(self) -> None:
        """Factory-Funktion gibt Singleton zurueck."""
        service1 = get_investment_intelligence_service()
        service2 = get_investment_intelligence_service()
        assert service1 is service2
        assert isinstance(service1, InvestmentIntelligenceService)
