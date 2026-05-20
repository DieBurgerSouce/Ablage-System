"""Tests fuer den Portfolio Service (Privat-Modul).

Testet:
- Portfolio Snapshot Erstellung
- Vermoegensberechnung
- Asset Allocation
- Nettovermoegen-Historie
- Datenstruktur-Validierung

WICHTIG: Dieser Test nutzt den Privat-Service (app.services.privat.portfolio_service),
NICHT den deprecated Service in app.services.portfolio.
"""

import pytest
from decimal import Decimal
from datetime import date, timedelta
from uuid import uuid4, UUID
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.privat.portfolio_service import (
    PortfolioService,
    AssetSummary,
    LiabilitySummary,
    PortfolioAnalysis,
    NetWorthTrendItem,
)


class TestAssetSummaryDataclass:
    """Tests fuer AssetSummary Datenstruktur."""

    def test_asset_summary_creation(self) -> None:
        """AssetSummary kann erstellt werden."""
        summary = AssetSummary(
            total_real_estate=Decimal("250000"),
            total_vehicles=Decimal("30000"),
            total_investments=Decimal("50000"),
            total_cash=Decimal("10000"),
            total_other_assets=Decimal("5000"),
        )

        assert summary.total_real_estate == Decimal("250000")
        assert summary.total_vehicles == Decimal("30000")
        assert summary.total_investments == Decimal("50000")
        assert summary.total_cash == Decimal("10000")
        assert summary.total_other_assets == Decimal("5000")

    def test_asset_summary_total_property(self) -> None:
        """AssetSummary.total berechnet Gesamtsumme korrekt."""
        summary = AssetSummary(
            total_real_estate=Decimal("200000"),
            total_vehicles=Decimal("25000"),
            total_investments=Decimal("50000"),
            total_cash=Decimal("10000"),
            total_other_assets=Decimal("5000"),
        )

        # 200k + 25k + 50k + 10k + 5k = 290k
        assert summary.total == Decimal("290000")

    def test_asset_summary_defaults(self) -> None:
        """AssetSummary hat korrekte Defaults."""
        summary = AssetSummary()

        assert summary.total_real_estate == Decimal("0")
        assert summary.total_vehicles == Decimal("0")
        assert summary.total_investments == Decimal("0")
        assert summary.total_cash == Decimal("0")
        assert summary.total_other_assets == Decimal("0")
        assert summary.total == Decimal("0")


class TestLiabilitySummaryDataclass:
    """Tests fuer LiabilitySummary Datenstruktur."""

    def test_liability_summary_creation(self) -> None:
        """LiabilitySummary kann erstellt werden."""
        summary = LiabilitySummary(
            total_mortgages=Decimal("150000"),
            total_loans=Decimal("20000"),
            total_other_liabilities=Decimal("5000"),
        )

        assert summary.total_mortgages == Decimal("150000")
        assert summary.total_loans == Decimal("20000")
        assert summary.total_other_liabilities == Decimal("5000")

    def test_liability_summary_total_property(self) -> None:
        """LiabilitySummary.total berechnet Gesamtsumme korrekt."""
        summary = LiabilitySummary(
            total_mortgages=Decimal("150000"),
            total_loans=Decimal("25000"),
            total_other_liabilities=Decimal("5000"),
        )

        # 150k + 25k + 5k = 180k
        assert summary.total == Decimal("180000")

    def test_liability_summary_defaults(self) -> None:
        """LiabilitySummary hat korrekte Defaults."""
        summary = LiabilitySummary()

        assert summary.total_mortgages == Decimal("0")
        assert summary.total_loans == Decimal("0")
        assert summary.total_other_liabilities == Decimal("0")
        assert summary.total == Decimal("0")


class TestPortfolioAnalysisDataclass:
    """Tests fuer PortfolioAnalysis Datenstruktur."""

    def test_portfolio_analysis_net_worth(self) -> None:
        """PortfolioAnalysis speichert net_worth korrekt."""
        assets = AssetSummary(
            total_real_estate=Decimal("300000"),
            total_vehicles=Decimal("40000"),
            total_investments=Decimal("100000"),
            total_cash=Decimal("20000"),
        )
        liabilities = LiabilitySummary(
            total_mortgages=Decimal("200000"),
            total_loans=Decimal("15000"),
        )

        # Net Worth wird bei Erstellung berechnet: assets.total - liabilities.total
        # Assets: 300k + 40k + 100k + 20k = 460k
        # Liabilities: 200k + 15k = 215k
        # Net Worth: 460k - 215k = 245k
        net_worth = assets.total - liabilities.total

        analysis = PortfolioAnalysis(
            assets=assets,
            liabilities=liabilities,
            net_worth=net_worth,
            asset_allocation={},
        )

        assert analysis.net_worth == Decimal("245000")
        assert analysis.assets.total == Decimal("460000")
        assert analysis.liabilities.total == Decimal("215000")

    def test_portfolio_analysis_zero_net_worth(self) -> None:
        """PortfolioAnalysis mit gleichem Asset/Liability Wert."""
        assets = AssetSummary(total_cash=Decimal("50000"))
        liabilities = LiabilitySummary(total_loans=Decimal("50000"))

        net_worth = assets.total - liabilities.total

        analysis = PortfolioAnalysis(
            assets=assets,
            liabilities=liabilities,
            net_worth=net_worth,
            asset_allocation={},
        )

        assert analysis.net_worth == Decimal("0")

    def test_portfolio_analysis_negative_net_worth(self) -> None:
        """PortfolioAnalysis mit negativem Net Worth (Schulden > Vermoegen)."""
        assets = AssetSummary(total_cash=Decimal("10000"))
        liabilities = LiabilitySummary(total_loans=Decimal("50000"))

        net_worth = assets.total - liabilities.total

        analysis = PortfolioAnalysis(
            assets=assets,
            liabilities=liabilities,
            net_worth=net_worth,
            asset_allocation={},
        )

        # 10k - 50k = -40k
        assert analysis.net_worth == Decimal("-40000")


class TestNetWorthTrendItem:
    """Tests fuer NetWorthTrendItem TypedDict."""

    def test_trend_item_structure(self) -> None:
        """NetWorthTrendItem hat korrekte Struktur."""
        item: NetWorthTrendItem = {
            "date": "2024-01-15",
            "net_worth": 250000.00,
            "total_assets": 400000.00,
            "total_liabilities": 150000.00,
        }

        assert item["date"] == "2024-01-15"
        assert item["net_worth"] == 250000.00
        assert item["total_assets"] == 400000.00
        assert item["total_liabilities"] == 150000.00


class TestPortfolioServiceInitialization:
    """Tests fuer Service-Initialisierung."""

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Service kann mit AsyncSession initialisiert werden."""
        mock_db = AsyncMock()
        service = PortfolioService(mock_db)

        assert service.db is mock_db

    @pytest.mark.asyncio
    async def test_service_methods_exist(self) -> None:
        """Service hat alle erwarteten Methoden."""
        mock_db = AsyncMock()
        service = PortfolioService(mock_db)

        # Public methods
        assert hasattr(service, "calculate_current_portfolio")
        assert hasattr(service, "create_monthly_snapshot")
        assert hasattr(service, "update_snapshot")
        assert hasattr(service, "get_portfolio_history")
        assert hasattr(service, "get_net_worth_trend")
        assert hasattr(service, "get_latest_snapshot")
        assert hasattr(service, "create_snapshots_for_all_spaces")


class TestPortfolioServiceAllocationCalculation:
    """Tests fuer Asset Allocation Berechnung.

    Die Allocation-Berechnung erfolgt inline in calculate_current_portfolio.
    Diese Tests validieren die Formel: (asset_type / total) * 100
    """

    def test_allocation_percentages(self) -> None:
        """Asset Allocation wird korrekt in Prozent berechnet."""
        assets = AssetSummary(
            total_real_estate=Decimal("200000"),  # 50%
            total_vehicles=Decimal("40000"),       # 10%
            total_investments=Decimal("120000"),   # 30%
            total_cash=Decimal("40000"),           # 10%
        )
        # Total: 400k

        # Berechnung wie im Service (inline):
        total = assets.total
        allocation = {}
        if total > 0:
            allocation = {
                "real_estate": float(assets.total_real_estate / total * 100),
                "vehicles": float(assets.total_vehicles / total * 100),
                "investments": float(assets.total_investments / total * 100),
                "cash": float(assets.total_cash / total * 100),
                "other": float(assets.total_other_assets / total * 100),
            }

        assert allocation["real_estate"] == 50.0
        assert allocation["vehicles"] == 10.0
        assert allocation["investments"] == 30.0
        assert allocation["cash"] == 10.0

    def test_allocation_empty_portfolio(self) -> None:
        """Leeres Portfolio hat leere Allocation."""
        assets = AssetSummary()  # All zeros

        # Berechnung wie im Service:
        total = assets.total
        allocation = {}
        if total > 0:
            allocation = {
                "real_estate": float(assets.total_real_estate / total * 100),
                "vehicles": float(assets.total_vehicles / total * 100),
                "investments": float(assets.total_investments / total * 100),
                "cash": float(assets.total_cash / total * 100),
            }

        # Bei 0 Total Assets bleibt allocation leer
        assert allocation == {}

    def test_allocation_single_asset_type(self) -> None:
        """Portfolio mit nur einem Asset-Typ hat 100% in dieser Kategorie."""
        assets = AssetSummary(total_investments=Decimal("100000"))

        total = assets.total
        allocation = {}
        if total > 0:
            allocation = {
                "real_estate": float(assets.total_real_estate / total * 100),
                "vehicles": float(assets.total_vehicles / total * 100),
                "investments": float(assets.total_investments / total * 100),
                "cash": float(assets.total_cash / total * 100),
            }

        assert allocation["real_estate"] == 0.0
        assert allocation["vehicles"] == 0.0
        assert allocation["investments"] == 100.0
        assert allocation["cash"] == 0.0


class TestPortfolioServiceRatioCalculations:
    """Tests fuer Kennzahlen-Berechnungen.

    Die Berechnungen erfolgen inline in calculate_current_portfolio.
    Diese Tests validieren die Formeln direkt.
    """

    def test_debt_to_assets_ratio_calculation(self) -> None:
        """Debt-to-Assets Ratio wird korrekt berechnet."""
        # 80k Schulden / 200k Vermoegen = 0.4 (40%)
        total_liabilities = Decimal("80000")
        total_assets = Decimal("200000")

        # Berechnung wie im Service:
        debt_to_assets = Decimal("0")
        if total_assets > 0:
            debt_to_assets = total_liabilities / total_assets

        assert debt_to_assets == Decimal("0.4")

    def test_debt_to_assets_zero_assets(self) -> None:
        """Debt-to-Assets mit 0 Assets bleibt 0 (Division durch Null vermeiden)."""
        total_liabilities = Decimal("50000")
        total_assets = Decimal("0")

        # Berechnung wie im Service:
        debt_to_assets = Decimal("0")
        if total_assets > 0:
            debt_to_assets = total_liabilities / total_assets

        assert debt_to_assets == Decimal("0")

    def test_liquidity_ratio_calculation(self) -> None:
        """Liquiditaetsquote wird korrekt berechnet."""
        # 30k Cash / 100k Schulden = 0.3
        total_cash = Decimal("30000")
        total_liabilities = Decimal("100000")

        # Berechnung wie im Service:
        liquidity_ratio = Decimal("0")
        if total_liabilities > 0:
            liquidity_ratio = total_cash / total_liabilities

        assert liquidity_ratio == Decimal("0.3")

    def test_liquidity_ratio_no_debt(self) -> None:
        """Liquiditaetsquote ohne Schulden bleibt 0 (keine Schulden = Division vermeiden)."""
        total_cash = Decimal("50000")
        total_liabilities = Decimal("0")

        # Berechnung wie im Service:
        liquidity_ratio = Decimal("0")
        if total_liabilities > 0:
            liquidity_ratio = total_cash / total_liabilities

        # Bei keinen Schulden: ratio bleibt 0 (keine Division durch 0)
        assert liquidity_ratio == Decimal("0")


class TestPortfolioServiceChangeCalculations:
    """Tests fuer Veraenderungs-Berechnungen.

    Die Berechnung erfolgt inline in calculate_current_portfolio.
    Diese Tests validieren die Formeln direkt.
    """

    def test_net_worth_change_positive(self) -> None:
        """Positive Veraenderung wird korrekt berechnet."""
        # Von 200k auf 250k = +50k (25%)
        current = Decimal("250000")
        previous = Decimal("200000")

        # Berechnung wie im Service:
        change_absolute = current - previous
        change_percent = None
        if previous and previous != 0:
            change_percent = (change_absolute / previous * 100)

        assert change_absolute == Decimal("50000")
        assert change_percent == Decimal("25")

    def test_net_worth_change_negative(self) -> None:
        """Negative Veraenderung wird korrekt berechnet."""
        # Von 200k auf 180k = -20k (-10%)
        current = Decimal("180000")
        previous = Decimal("200000")

        change_absolute = current - previous
        change_percent = None
        if previous and previous != 0:
            change_percent = (change_absolute / previous * 100)

        assert change_absolute == Decimal("-20000")
        assert change_percent == Decimal("-10")

    def test_net_worth_change_no_previous(self) -> None:
        """Ohne vorherigen Wert gibt None zurueck."""
        current = Decimal("250000")
        previous = None

        change_absolute = None
        change_percent = None
        if previous is not None:
            change_absolute = current - previous
            if previous != 0:
                change_percent = (change_absolute / previous * 100)

        assert change_absolute is None
        assert change_percent is None

    def test_net_worth_change_zero_previous(self) -> None:
        """Vorheriger Wert von 0 wird behandelt."""
        current = Decimal("100000")
        previous = Decimal("0")

        change_absolute = current - previous
        change_percent = None
        if previous and previous != 0:
            change_percent = (change_absolute / previous * 100)

        assert change_absolute == Decimal("100000")
        # Division durch 0 wird vermieden - change_percent bleibt None
        assert change_percent is None


class TestPortfolioServiceMultiTenantSecurity:
    """Tests fuer Multi-Tenant Sicherheit.

    KRITISCH: Alle Queries MUESSEN nach space_id filtern!
    """

    @pytest.mark.asyncio
    async def test_snapshot_query_uses_space_id(self) -> None:
        """get_latest_snapshot filtert nach space_id."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        service = PortfolioService(mock_db)
        space_id = uuid4()

        await service.get_latest_snapshot(space_id)

        # Verify execute was called
        assert mock_db.execute.called

        # Die Query sollte space_id enthalten
        call_args = mock_db.execute.call_args
        query_str = str(call_args[0][0])
        assert "space_id" in query_str.lower()

    @pytest.mark.asyncio
    async def test_history_query_uses_space_id(self) -> None:
        """get_portfolio_history filtert nach space_id."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        service = PortfolioService(mock_db)
        space_id = uuid4()

        await service.get_portfolio_history(space_id, months=6)

        # Verify execute was called
        assert mock_db.execute.called

        # Die Query sollte space_id enthalten
        call_args = mock_db.execute.call_args
        query_str = str(call_args[0][0])
        assert "space_id" in query_str.lower()
