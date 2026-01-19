"""
Tests fuer Risk Intelligence API Endpoints.

Testet erweiterte Risikoanalyse mit Benchmarks, Trends und Netzwerk-Analyse.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import status


class TestRiskIntelligenceAPI:
    """Tests fuer Risk Intelligence API."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = uuid4()
        user.company_id = uuid4()  # Risk Intelligence uses company_id
        user.role = "user"
        return user

    @pytest.fixture
    def mock_admin(self):
        """Mock admin user."""
        user = MagicMock()
        user.id = uuid4()
        user.company_id = uuid4()  # Risk Intelligence uses company_id
        user.role = "admin"
        return user

    @pytest.fixture
    def mock_risk_service(self):
        """Mock RiskIntelligenceService."""
        service = AsyncMock()
        service.get_risk_profile.return_value = {
            "entity_id": str(uuid4()),
            "entity_name": "Test Lieferant GmbH",
            "entity_type": "supplier",
            "industry": "manufacturing",
            "overall_risk_score": 35.0,
            "risk_level": "medium",
            "analysis": {
                "payment_behavior": {"score": 25, "details": "Durchschnittlich 5 Tage Verzoegerung"},
                "financial_health": {"score": 40, "details": "Stabiler Umsatz"},
                "market_position": {"score": 35, "details": "Mittelstaendisch"},
            },
            "recommendations": [
                {
                    "priority": "medium",
                    "category": "payment",
                    "title": "Zahlungsbedingungen pruefen",
                    "description": "Gelegentliche Verzoegerungen beobachtet",
                    "action": "Skonto-Anreize erwaegen",
                }
            ],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }
        service.get_trend_analysis.return_value = {
            "direction": "improving",
            "change_percentage": 10.5,
            "quarters": [
                {"quarter": "Q3/2025", "score": 45},
                {"quarter": "Q4/2025", "score": 40},
                {"quarter": "Q1/2026", "score": 35},
            ],
            "trend_score": 0.85,
        }
        service.get_benchmark_comparison.return_value = {
            "industry": "manufacturing",
            "benchmark": {
                "avg_payment_delay": 14,
                "default_rate": 0.02,
            },
            "actual_payment_delay": 5.0,
            "actual_default_rate": 0.01,
            "delay_deviation": -9.0,
            "default_deviation": -0.01,
            "performance": "above_average",
            "benchmark_score": 0.9,
        }
        service.get_network_analysis.return_value = {
            "connections": [
                {
                    "entity_id": str(uuid4()),
                    "entity_name": "Verbundenes Unternehmen",
                    "relationship": "subsidiary",
                    "risk_score": 25,
                }
            ],
            "connection_count": 1,
            "network_risk_score": 30.0,
            "has_suspicious_connections": False,
        }
        return service

    # ==================== Risk Profile Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_risk_profile_success(
        self,
        mock_user: MagicMock,
        mock_risk_service: AsyncMock,
    ) -> None:
        """Erfolgreicher Abruf eines Risikoprofils."""
        from app.api.v1.risk_intelligence import get_risk_profile

        entity_id = uuid4()

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_risk_service,
        ):
            result = await get_risk_profile(
                entity_id=entity_id,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result is not None
        mock_risk_service.get_comprehensive_risk_profile.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_risk_profile_not_found(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Fehler wenn Entity nicht gefunden."""
        from app.api.v1.risk_intelligence import get_risk_profile
        from fastapi import HTTPException

        mock_service = AsyncMock()
        mock_service.get_comprehensive_risk_profile.return_value = {"error": "Entity nicht gefunden"}

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_risk_profile(
                    entity_id=uuid4(),
                    current_user=mock_user,
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 404

    # ==================== Trend Analysis Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_entity_trend_success(
        self,
        mock_user: MagicMock,
        mock_risk_service: AsyncMock,
    ) -> None:
        """Erfolgreiche Trend-Analyse."""
        from app.api.v1.risk_intelligence import get_entity_trend

        entity_id = uuid4()
        mock_risk_service._analyze_trends.return_value = {
            "direction": "improving",
            "change_percentage": 10.5,
            "trend_score": 0.85,
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_risk_service,
        ):
            result = await get_entity_trend(
                entity_id=entity_id,
                quarters=4,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["trend"]["direction"] == "improving"
        mock_risk_service._analyze_trends.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_entity_trend_stable(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Trend-Analyse mit stabilem Trend."""
        from app.api.v1.risk_intelligence import get_entity_trend

        mock_service = AsyncMock()
        mock_service._analyze_trends.return_value = {
            "direction": "stable",
            "change_percentage": 0.5,
            "trend_score": 0.5,
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_service,
        ):
            result = await get_entity_trend(
                entity_id=uuid4(),
                quarters=4,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["trend"]["direction"] == "stable"

    # ==================== Benchmark Comparison Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_entity_benchmark_success(
        self,
        mock_user: MagicMock,
        mock_risk_service: AsyncMock,
    ) -> None:
        """Erfolgreicher Benchmark-Vergleich."""
        from app.api.v1.risk_intelligence import get_entity_benchmark

        entity_id = uuid4()
        mock_risk_service._compare_with_benchmarks.return_value = {
            "industry": "manufacturing",
            "benchmark": {"avg_payment_delay": 14, "default_rate": 0.02},
            "actual_payment_delay": 5.0,
            "actual_default_rate": 0.01,
            "delay_deviation": -9.0,
            "performance": "above_average",
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_risk_service,
        ):
            result = await get_entity_benchmark(
                entity_id=entity_id,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["benchmark_comparison"]["industry"] == "manufacturing"
        assert result["benchmark_comparison"]["performance"] == "above_average"

    @pytest.mark.asyncio
    async def test_get_entity_benchmark_below_average(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Benchmark-Vergleich unter Durchschnitt."""
        from app.api.v1.risk_intelligence import get_entity_benchmark

        mock_service = AsyncMock()
        mock_service._compare_with_benchmarks.return_value = {
            "industry": "retail",
            "benchmark": {"avg_payment_delay": 14, "default_rate": 0.02},
            "actual_payment_delay": 25.0,
            "actual_default_rate": 0.05,
            "delay_deviation": 11.0,
            "performance": "below_average",
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_service,
        ):
            result = await get_entity_benchmark(
                entity_id=uuid4(),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["benchmark_comparison"]["performance"] == "below_average"

    # ==================== Network Analysis Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_entity_network_success(
        self,
        mock_user: MagicMock,
        mock_risk_service: AsyncMock,
    ) -> None:
        """Erfolgreiche Netzwerk-Analyse."""
        from app.api.v1.risk_intelligence import get_entity_network

        entity_id = uuid4()
        mock_risk_service._analyze_network.return_value = {
            "connections": [],
            "connection_count": 1,
            "network_risk_score": 30.0,
            "has_suspicious_connections": False,
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_risk_service,
        ):
            result = await get_entity_network(
                entity_id=entity_id,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["network"]["connection_count"] == 1
        assert result["network"]["has_suspicious_connections"] is False

    @pytest.mark.asyncio
    async def test_get_entity_network_with_suspicious(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Netzwerk-Analyse mit verdaechtigen Verbindungen."""
        from app.api.v1.risk_intelligence import get_entity_network

        mock_service = AsyncMock()
        mock_service._analyze_network.return_value = {
            "connections": [
                {
                    "entity_id": str(uuid4()),
                    "entity_name": "Shell Company Ltd",
                    "relationship": "supplier",
                    "risk_score": 85,
                    "is_suspicious": True,
                }
            ],
            "connection_count": 1,
            "network_risk_score": 75.0,
            "has_suspicious_connections": True,
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_service,
        ):
            result = await get_entity_network(
                entity_id=uuid4(),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["network"]["has_suspicious_connections"] is True
        assert result["network"]["network_risk_score"] >= 75

    # ==================== Portfolio Risk Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_portfolio_risk(
        self,
        mock_user: MagicMock,
        mock_risk_service: AsyncMock,
    ) -> None:
        """Portfolio-Risikouebersicht abrufen."""
        from app.api.v1.risk_intelligence import get_portfolio_risk

        mock_risk_service.get_portfolio_risk_overview.return_value = {
            "total_entities": 50,
            "risk_distribution": {
                "low": 30,
                "medium": 15,
                "high": 4,
                "critical": 1,
            },
            "high_risk_entities": [
                {"entity_id": str(uuid4()), "name": "Risiko GmbH", "score": 82}
            ],
            "total_exposure": 500000.0,
            "portfolio_risk_score": 28.0,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_risk_service,
        ):
            result = await get_portfolio_risk(
                entity_type=None,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result["total_entities"] == 50
        assert result["risk_distribution"]["low"] == 30
        assert len(result["high_risk_entities"]) == 1
        mock_risk_service.get_portfolio_risk_overview.assert_called_once()

    # ==================== External Sources Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_check_external_sources_success(
        self,
        mock_admin: MagicMock,
        mock_risk_service: AsyncMock,
    ) -> None:
        """Externe Quellen pruefen."""
        from app.api.v1.risk_intelligence import check_external_sources

        entity_id = uuid4()
        mock_risk_service.check_external_sources.return_value = {
            "entity_id": str(entity_id),
            "entity_name": "Test GmbH",
            "sources_checked": [
                {"source": "Handelsregister", "status": "ok", "last_update": "2026-01-15"},
                {"source": "Insolvenzregister", "status": "ok", "last_update": "2026-01-18"},
            ],
            "alerts": [],
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_risk_service,
        ):
            result = await check_external_sources(
                entity_id=entity_id,
                current_user=mock_admin,
                db=AsyncMock(),
            )

        assert len(result["sources_checked"]) == 2
        assert len(result["alerts"]) == 0

    @pytest.mark.asyncio
    async def test_check_external_sources_with_alert(
        self,
        mock_admin: MagicMock,
    ) -> None:
        """Externe Quellen mit Alert."""
        from app.api.v1.risk_intelligence import check_external_sources

        mock_service = AsyncMock()
        mock_service.check_external_sources.return_value = {
            "entity_id": str(uuid4()),
            "entity_name": "Problematische GmbH",
            "sources_checked": [
                {"source": "Handelsregister", "status": "ok"},
                {"source": "Insolvenzregister", "status": "alert"},
            ],
            "alerts": [
                {
                    "type": "insolvency_warning",
                    "message": "Insolvenzverfahren eroeffnet am 2026-01-10",
                    "severity": "critical",
                }
            ],
            "last_checked": datetime.now(timezone.utc).isoformat(),
        }

        with patch(
            "app.api.v1.risk_intelligence.RiskIntelligenceService",
            return_value=mock_service,
        ):
            result = await check_external_sources(
                entity_id=uuid4(),
                current_user=mock_admin,
                db=AsyncMock(),
            )

        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["type"] == "insolvency_warning"

    # ==================== Industry Benchmarks Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_industry_benchmarks(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Branchen-Benchmarks abrufen."""
        from app.api.v1.risk_intelligence import get_industry_benchmarks

        # This endpoint has no parameters
        result = await get_industry_benchmarks()

        # Sollte Liste von Branchen mit Benchmarks zurueckgeben
        assert isinstance(result, list)
        assert len(result) > 0

        # Jeder Eintrag sollte die erwarteten Felder haben
        for benchmark in result:
            assert "industry" in benchmark
            assert "avg_payment_delay" in benchmark
            assert "default_rate" in benchmark


class TestRiskIntelligenceService:
    """Tests fuer RiskIntelligenceService Hilfsmethoden."""

    @pytest.mark.skip(reason="Service-Methoden noch nicht vollstaendig implementiert")
    @pytest.mark.asyncio
    async def test_risk_level_classification(self) -> None:
        """Test der Risiko-Level-Klassifizierung."""
        pass

    @pytest.mark.skip(reason="Service-Methoden noch nicht vollstaendig implementiert")
    @pytest.mark.asyncio
    async def test_trend_direction_calculation(self) -> None:
        """Test der Trend-Richtungsberechnung."""
        pass

    @pytest.mark.skip(reason="Service-Methoden noch nicht vollstaendig implementiert")
    @pytest.mark.asyncio
    async def test_benchmark_score_calculation(self) -> None:
        """Test der Benchmark-Score-Berechnung."""
        pass
