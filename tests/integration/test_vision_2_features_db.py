# -*- coding: utf-8 -*-
"""
Integration Tests: Vision 2.0 Features - Database Operations (gemockt).

W3 (2026-06-12): Komplett auf die ECHTEN Service-Vertraege modernisiert
(15 Drift-Failures). Die alte Fassung testete erfundene APIs
(``CommunicationHubService()`` ohne db, ``get_timeline``,
``get_company_metrics``, ``get_user_preferences``, ``run_scenario``).
Reale Vertraege (G1 company_id-Rollout: db kommt in den Konstruktor):
- CommunicationHubService(db).get_communication_hub(entity_id, company_id, ...)
- IndustryBenchmarkService(db).get_company_benchmark(company_id, ...)
- AIMentorService(db).get_mentor_preferences/dismiss_tip/analyze_behavior_patterns
- LiquidityScenarioService(db).run_monte_carlo(company_id, ...)
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

if TYPE_CHECKING:
    pass


# =============================================================================
# Test Fixtures / Helpers
# =============================================================================

def _empty_result() -> MagicMock:
    """DB-Result-Mock: alle Konsum-Pfade liefern 'leer'."""
    res = MagicMock()
    res.scalar.return_value = 0
    res.scalar_one_or_none.return_value = None
    res.scalars.return_value.all.return_value = []
    res.all.return_value = []
    res.first.return_value = None
    res.one_or_none.return_value = None
    return res


@pytest.fixture
def mock_db_session() -> AsyncMock:
    """Mock async database session (alle Queries leer)."""
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_empty_result())
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def sample_company_id() -> uuid.UUID:
    """Sample company ID for tests."""
    return uuid.UUID("12345678-1234-1234-1234-123456789012")


@pytest.fixture
def sample_user_id() -> uuid.UUID:
    """Sample user ID for tests."""
    return uuid.UUID("87654321-4321-4321-4321-210987654321")


@pytest.fixture
def sample_entity_id() -> uuid.UUID:
    """Sample business entity ID for tests."""
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


# =============================================================================
# Communication Hub Database Tests
# =============================================================================

class TestCommunicationHubDB:
    """Database tests for CommunicationHubService."""

    @pytest.mark.asyncio
    async def test_entity_access_check_filters_by_company(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        """Multi-Tenant: Access-Check-Query filtert auf company_id."""
        from app.services.communication_hub_service import CommunicationHubService

        service = CommunicationHubService(mock_db_session)

        hub = await service.get_communication_hub(
            entity_id=sample_entity_id,
            company_id=sample_company_id,
            include_sections=["entity"],
        )

        # Kein Dokument der Company verknuepft -> Entity bleibt leer
        assert hub.entity == {}
        # Die Access-Check-Query enthaelt den company_id-Filter
        first_stmt = mock_db_session.execute.call_args_list[0].args[0]
        assert "company_id" in str(first_stmt)

    @pytest.mark.asyncio
    async def test_get_communication_hub_loads_entity(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        """Hub laedt Entity-Daten wenn Zugriff erlaubt."""
        from app.services.communication_hub_service import CommunicationHubService

        service = CommunicationHubService(mock_db_session)

        # Access-Check liefert 1 Dokument, Entity-Query die Entity
        access_result = _empty_result()
        access_result.scalar.return_value = 1

        entity = MagicMock()
        entity.id = sample_entity_id
        entity.name = "Test Entity"
        entity.display_name = "Test Entity GmbH"
        entity.short_name = "TE"
        entity.entity_type = "customer"
        entity.vat_id = None
        entity.iban = None
        entity.email = "info@test-entity.de"
        entity.phone = None
        entity.full_address = "Teststr. 1, 80331 München"
        entity.is_active = True
        entity.verified = True
        entity.risk_score = 10
        entity.payment_behavior_score = 90
        entity.document_count = 3
        entity.total_invoice_amount = 1500.0
        entity.first_document_date = None
        entity.last_document_date = None
        entity.lexware_ids = {}
        entity.notes = None

        entity_result = _empty_result()
        entity_result.scalar_one_or_none.return_value = entity

        mock_db_session.execute.side_effect = [access_result, entity_result]

        hub = await service.get_communication_hub(
            entity_id=sample_entity_id,
            company_id=sample_company_id,
            include_sections=["entity"],
        )

        assert hub.entity["name"] == "Test Entity"
        assert hub.entity["display_name"] == "Test Entity GmbH"
        assert hub.entity["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_communication_hub_all_sections_empty_db(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        """Alle Sektionen mit leerer DB: kein Crash, leere Strukturen."""
        from app.services.communication_hub_service import (
            CommunicationHubData,
            CommunicationHubService,
        )

        service = CommunicationHubService(mock_db_session)

        hub = await service.get_communication_hub(
            entity_id=sample_entity_id,
            company_id=sample_company_id,
        )

        assert isinstance(hub, CommunicationHubData)
        assert hub.timeline == []
        assert hub.recent_documents == []
        assert hub.phone_notes == []


# =============================================================================
# Industry Benchmark Database Tests
# =============================================================================

class TestIndustryBenchmarkDB:
    """Database tests for IndustryBenchmarkService."""

    @pytest.mark.asyncio
    async def test_unknown_company_raises_german_error(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Unbekannte Firma -> deutscher ValueError."""
        from app.services.analytics.industry_benchmark_service import (
            IndustryBenchmarkService,
        )

        service = IndustryBenchmarkService(mock_db_session)

        with pytest.raises(ValueError, match="Firma nicht gefunden"):
            await service.get_company_benchmark(company_id=sample_company_id)

    @pytest.mark.asyncio
    async def test_get_company_benchmark_handles_zero_invoices(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Keine Rechnungen -> Fallback-Metriken statt Crash."""
        from app.services.analytics.industry_benchmark_service import (
            CompanyBenchmarkReport,
            Industry,
            IndustryBenchmarkService,
        )

        company = MagicMock()
        company.id = sample_company_id
        company.name = "Test GmbH"

        company_result = _empty_result()
        company_result.scalar_one_or_none.return_value = company

        def execute_side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            # Erste Query: Company; alle weiteren: leere Aggregate
            if mock_db_session.execute.call_count == 1:
                return company_result
            return _empty_result()

        mock_db_session.execute.side_effect = None
        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)

        service = IndustryBenchmarkService(mock_db_session)
        report = await service.get_company_benchmark(
            company_id=sample_company_id,
            industry=Industry.MANUFACTURING,
        )

        assert isinstance(report, CompanyBenchmarkReport)
        assert report.company_name == "Test GmbH"
        assert report.industry == Industry.MANUFACTURING
        assert 0.0 <= report.overall_score <= 100.0
        assert 0 <= report.overall_percentile <= 100

    @pytest.mark.asyncio
    async def test_benchmark_report_structure(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Report enthaelt Metriken, Level und Empfehlungen."""
        from app.services.analytics.industry_benchmark_service import (
            Industry,
            IndustryBenchmarkService,
            PerformanceLevel,
        )

        company = MagicMock()
        company.id = sample_company_id
        company.name = "Test GmbH"

        company_result = _empty_result()
        company_result.scalar_one_or_none.return_value = company

        results = [company_result]

        def execute_side_effect(*args, **kwargs):  # noqa: ANN002, ANN003
            if results:
                return results.pop(0)
            return _empty_result()

        mock_db_session.execute = AsyncMock(side_effect=execute_side_effect)

        service = IndustryBenchmarkService(mock_db_session)
        report = await service.get_company_benchmark(
            company_id=sample_company_id,
            industry=Industry.OTHER,
        )

        assert isinstance(report.metrics, list)
        assert len(report.metrics) > 0
        assert isinstance(report.overall_level, PerformanceLevel)
        assert isinstance(report.recommendations, list)


# =============================================================================
# AI Mentor Database Tests
# =============================================================================

class TestAIMentorDB:
    """Database tests for AIMentorService."""

    @pytest.mark.asyncio
    async def test_get_mentor_preferences_defaults_without_user(
        self,
        mock_db_session: AsyncMock,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Kein User/keine Preferences -> Default-Praeferenzen."""
        from app.services.ai.mentor_service import (
            AIMentorService,
            MentorPreferences,
            UserExperience,
        )

        service = AIMentorService(mock_db_session)

        prefs = await service.get_mentor_preferences(user_id=sample_user_id)

        assert isinstance(prefs, MentorPreferences)
        assert prefs.enabled is True
        assert prefs.experience_level == UserExperience.BEGINNER

    @pytest.mark.asyncio
    async def test_dismiss_tip_persists_in_preferences(
        self,
        mock_db_session: AsyncMock,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Verworfener Tipp landet in User.preferences['mentor']."""
        from app.services.ai.mentor_service import AIMentorService

        user = MagicMock()
        user.id = sample_user_id
        user.preferences = {}

        user_result = _empty_result()
        user_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = user_result

        service = AIMentorService(mock_db_session)
        success = await service.dismiss_tip(
            user_id=sample_user_id,
            tip_id="tip_shortcut_001",
        )

        assert success is True
        assert "tip_shortcut_001" in user.preferences["mentor"]["dismissed_tips"]
        mock_db_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dismiss_tip_rejects_invalid_tip_id(
        self,
        mock_db_session: AsyncMock,
        sample_user_id: uuid.UUID,
    ) -> None:
        """Ungueltiges tip_id-Format wird ohne DB-Zugriff abgelehnt."""
        from app.services.ai.mentor_service import AIMentorService

        service = AIMentorService(mock_db_session)
        success = await service.dismiss_tip(
            user_id=sample_user_id,
            tip_id="'; DROP TABLE users; --",
        )

        assert success is False
        mock_db_session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_analyze_behavior_patterns_empty_log(
        self,
        mock_db_session: AsyncMock,
        sample_user_id: uuid.UUID,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Leeres Behavior-Log -> leere Musterliste, kein Crash."""
        from app.services.ai.mentor_service import AIMentorService

        service = AIMentorService(mock_db_session)
        patterns = await service.analyze_behavior_patterns(
            user_id=sample_user_id,
            company_id=sample_company_id,
        )

        assert isinstance(patterns, list)
        assert patterns == []


# =============================================================================
# Liquidity Scenario Database Tests
# =============================================================================

def _forecast(
    current_balance: float,
    days: int,
    inflows: float,
    outflows: float,
) -> dict:
    """Baut eine Basis-Prognose wie PredictiveCashFlowService sie liefert."""
    return {
        "current_balance": current_balance,
        "forecast": [
            {
                "date": f"2026-07-{day + 1:02d}",
                "inflows": inflows,
                "outflows": outflows,
            }
            for day in range(days)
        ],
    }


class TestLiquidityScenarioDB:
    """Database tests for LiquidityScenarioService."""

    @pytest.mark.asyncio
    async def test_monte_carlo_simulation_bounds(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Monte Carlo: Perzentile sind geordnet (P5 <= P50 <= P95)."""
        from app.services.finanzki.liquidity_scenario_service import (
            LiquidityScenarioService,
            MonteCarloResult,
        )

        service = LiquidityScenarioService(mock_db_session)
        service.cashflow_service.forecast_with_seasonality = AsyncMock(
            return_value=_forecast(50000.0, days=5, inflows=1000.0, outflows=800.0)
        )

        result = await service.run_monte_carlo(
            company_id=sample_company_id,
            forecast_days=5,
            iterations=100,  # Reduced for test
        )

        assert isinstance(result, MonteCarloResult)
        assert result.iterations == 100
        assert result.percentiles["p5"] <= result.percentiles["p50"]
        assert result.percentiles["p50"] <= result.percentiles["p95"]
        assert 0.0 <= result.probability_negative <= 1.0

    @pytest.mark.asyncio
    async def test_monte_carlo_detects_certain_shortfall(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Nur Abfluesse ohne Startguthaben -> Unterdeckung sicher."""
        from app.services.finanzki.liquidity_scenario_service import (
            LiquidityScenarioService,
        )

        service = LiquidityScenarioService(mock_db_session)
        service.cashflow_service.forecast_with_seasonality = AsyncMock(
            return_value=_forecast(0.0, days=5, inflows=0.0, outflows=1000.0)
        )

        result = await service.run_monte_carlo(
            company_id=sample_company_id,
            forecast_days=5,
            iterations=50,
        )

        assert result.probability_negative == 1.0
        assert result.percentiles["p95"] < 0


# =============================================================================
# Transaction / Error Handling Tests
# =============================================================================

class TestTransactionRollback:
    """Tests for error handling without unintended commits."""

    @pytest.mark.asyncio
    async def test_communication_hub_tolerates_db_error(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
        sample_entity_id: uuid.UUID,
    ) -> None:
        """Hub faengt Sektions-Fehler ab und committet NICHT."""
        from app.services.communication_hub_service import (
            CommunicationHubData,
            CommunicationHubService,
        )

        service = CommunicationHubService(mock_db_session)
        mock_db_session.execute.side_effect = Exception("DB Error")

        # Realer Vertrag: Sektions-Fehler werden gesammelt, kein Raise
        hub = await service.get_communication_hub(
            entity_id=sample_entity_id,
            company_id=sample_company_id,
        )

        assert isinstance(hub, CommunicationHubData)
        assert hub.entity.get("error") is not None  # Entity-Fehler markiert
        mock_db_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_benchmark_propagates_db_error_without_commit(
        self,
        mock_db_session: AsyncMock,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Company-Load-Fehler propagiert, nichts wird committet."""
        from app.services.analytics.industry_benchmark_service import (
            IndustryBenchmarkService,
        )

        service = IndustryBenchmarkService(mock_db_session)
        mock_db_session.execute.side_effect = Exception("DB Error")

        with pytest.raises(Exception, match="DB Error"):
            await service.get_company_benchmark(company_id=sample_company_id)

        mock_db_session.commit.assert_not_called()


# =============================================================================
# Concurrent Access Tests
# =============================================================================

class TestConcurrentAccess:
    """Tests for concurrent database access handling."""

    @pytest.mark.asyncio
    async def test_concurrent_hub_requests(
        self,
        sample_company_id: uuid.UUID,
    ) -> None:
        """Mehrere parallele Hub-Anfragen laufen fehlerfrei durch."""
        import asyncio

        from app.services.communication_hub_service import CommunicationHubService

        entity_ids = [uuid.uuid4() for _ in range(5)]

        async def _one_request(eid: uuid.UUID):
            session = AsyncMock()
            session.execute = AsyncMock(return_value=_empty_result())
            session.commit = AsyncMock()
            service = CommunicationHubService(session)
            return await service.get_communication_hub(
                entity_id=eid,
                company_id=sample_company_id,
                include_sections=["entity", "timeline"],
            )

        results = await asyncio.gather(
            *[_one_request(eid) for eid in entity_ids],
            return_exceptions=True,
        )

        for result in results:
            assert not isinstance(result, Exception)


# =============================================================================
# Data Integrity Tests
# =============================================================================

class TestDataIntegrity:
    """Tests for data integrity in database operations."""

    @pytest.mark.asyncio
    async def test_tip_history_returns_dismissed_tips_limited(
        self,
        mock_db_session: AsyncMock,
        sample_user_id: uuid.UUID,
    ) -> None:
        """get_tip_history liefert dismissed_tips und respektiert limit."""
        from app.services.ai.mentor_service import AIMentorService

        user = MagicMock()
        user.id = sample_user_id
        user.preferences = {
            "mentor": {"dismissed_tips": [f"tip_{i:03d}" for i in range(10)]},
        }

        user_result = _empty_result()
        user_result.scalar_one_or_none.return_value = user
        mock_db_session.execute.return_value = user_result

        service = AIMentorService(mock_db_session)
        history = await service.get_tip_history(user_id=sample_user_id, limit=3)

        assert len(history) == 3
        assert history == ["tip_000", "tip_001", "tip_002"]
