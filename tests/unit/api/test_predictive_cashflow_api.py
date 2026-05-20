"""
Tests fuer Predictive Cash-Flow API Endpoints.

Testet ML-basierte Cashflow-Vorhersagen und Liquiditaetsplanung.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import status


class TestPredictiveCashFlowAPI:
    """Tests fuer Predictive Cash-Flow API."""

    @pytest.fixture
    def mock_user(self):
        """Mock authenticated user."""
        user = MagicMock()
        user.id = uuid4()
        user.current_company_id = uuid4()
        user.role = "user"
        return user

    @pytest.fixture
    def mock_admin(self):
        """Mock admin user."""
        user = MagicMock()
        user.id = uuid4()
        user.current_company_id = uuid4()
        user.role = "admin"
        return user

    @pytest.fixture
    def mock_cashflow_service(self):
        """Mock PredictiveCashFlowService."""
        service = AsyncMock()
        service.forecast_liquidity.return_value = {
            "company_id": str(uuid4()),
            "forecast_days": 30,
            "current_balance": 50000.0,
            "min_balance": 15000.0,
            "min_balance_date": (datetime.now(timezone.utc) + timedelta(days=15)).isoformat(),
            "total_expected_inflows": 80000.0,
            "total_expected_outflows": 65000.0,
            "forecast": [
                {
                    "date": (datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d"),
                    "inflows": 2500.0,
                    "outflows": 2000.0,
                    "net_flow": 500.0,
                    "balance": 50000.0 + (500.0 * i),
                    "is_warning": False,
                    "is_critical": False,
                }
                for i in range(30)
            ],
            "warnings": [],
            "currency": "EUR",
        }
        service.predict_payment_date.return_value = {
            "invoice_id": str(uuid4()),
            "predicted_date": (datetime.now(timezone.utc) + timedelta(days=21)).isoformat(),
            "predicted_days": 21,
            "confidence": 0.85,
            "delay_probability": 0.15,
            "factors": {
                "entity_history": 0.3,
                "invoice_amount": 0.2,
                "industry_average": 0.5,
            },
        }
        service.get_payment_recommendations.return_value = [
            {
                "invoice_id": str(uuid4()),
                "invoice_number": "RE-2026-001",
                "amount": 5000.0,
                "due_date": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "days_until_due": 7,
                "urgency": "high",
                "recommendation": "Zahlen Sie jetzt, um 2% Skonto zu nutzen",
                "reason": "Skonto-Frist laeuft in 3 Tagen ab",
                "skonto_savings": 100.0,
                "skonto_deadline": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            }
        ]
        return service

    # ==================== Forecast Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_liquidity_forecast_success(
        self,
        mock_user: MagicMock,
        mock_cashflow_service: AsyncMock,
    ) -> None:
        """Erfolgreiche Liquiditaetsprognose."""
        from app.api.v1.predictive_cashflow import get_liquidity_forecast

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_cashflow_service,
        ):
            result = await get_liquidity_forecast(
                days=30,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result is not None
        mock_cashflow_service.forecast_liquidity.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_liquidity_forecast_no_company(self) -> None:
        """Fehler wenn User keine Company hat."""
        from app.api.v1.predictive_cashflow import get_liquidity_forecast
        from fastapi import HTTPException

        user = MagicMock()
        user.current_company_id = None

        with pytest.raises(HTTPException) as exc_info:
            await get_liquidity_forecast(
                days=30,
                current_user=user,
                db=AsyncMock(),
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.skip(reason="stub - nicht implementiert")
    @pytest.mark.asyncio
    async def test_get_liquidity_forecast_days_validation(self) -> None:
        """Days-Parameter wird validiert (7-365)."""
        # Die Validierung erfolgt durch FastAPI Query-Parameter
        pass

    # ==================== Predict Payment Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_predict_payment_success(
        self,
        mock_user: MagicMock,
        mock_cashflow_service: AsyncMock,
    ) -> None:
        """Erfolgreiche Zahlungsvorhersage."""
        from app.api.v1.predictive_cashflow import predict_payment

        invoice_id = uuid4()

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_cashflow_service,
        ):
            result = await predict_payment(
                invoice_id=invoice_id,
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result is not None
        mock_cashflow_service.predict_payment_date.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_payment_invoice_not_found(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Fehler wenn Rechnung nicht gefunden."""
        from app.api.v1.predictive_cashflow import predict_payment
        from fastapi import HTTPException

        mock_service = AsyncMock()
        mock_service.predict_payment_date.return_value = {"error": "Rechnung nicht gefunden"}

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await predict_payment(
                    invoice_id=uuid4(),
                    current_user=mock_user,
                    db=AsyncMock(),
                )

        assert exc_info.value.status_code == 404

    # ==================== Recommendations Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_get_recommendations_success(
        self,
        mock_user: MagicMock,
        mock_cashflow_service: AsyncMock,
    ) -> None:
        """Erfolgreiche Zahlungsempfehlungen."""
        from app.api.v1.predictive_cashflow import get_payment_recommendations

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_cashflow_service,
        ):
            result = await get_payment_recommendations(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert len(result) == 1
        assert result[0].urgency == "high"
        assert result[0].skonto_savings == 100.0

    @pytest.mark.asyncio
    async def test_get_recommendations_empty(
        self,
        mock_user: MagicMock,
    ) -> None:
        """Leere Empfehlungen wenn keine offenen Rechnungen."""
        from app.api.v1.predictive_cashflow import get_payment_recommendations

        mock_service = AsyncMock()
        mock_service.get_payment_recommendations.return_value = []

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_service,
        ):
            result = await get_payment_recommendations(
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result == []

    # ==================== Scenario Endpoint Tests ====================

    @pytest.mark.asyncio
    async def test_scenario_analysis_delayed_payments(
        self,
        mock_user: MagicMock,
        mock_cashflow_service: AsyncMock,
    ) -> None:
        """Szenario-Analyse: Verzoegerte Zahlungen."""
        from app.api.v1.predictive_cashflow import run_scenario, ScenarioRequest

        mock_cashflow_service.run_scenario.return_value = {
            "scenario_type": "delayed_payments",
            "parameters": {"delay_days": 14},
            "base_min_balance": 25000.0,
            "scenario_min_balance": 15000.0,
            "forecast": [],
            "impact": "moderate",
        }

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_cashflow_service,
        ):
            result = await run_scenario(
                request=ScenarioRequest(
                    scenario_type="delayed_payments",
                    parameters={"delay_days": 14},
                ),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result.scenario_type == "delayed_payments"
        mock_cashflow_service.run_scenario.assert_called_once()

    @pytest.mark.asyncio
    async def test_scenario_analysis_large_expense(
        self,
        mock_user: MagicMock,
        mock_cashflow_service: AsyncMock,
    ) -> None:
        """Szenario-Analyse: Grosse Ausgabe."""
        from app.api.v1.predictive_cashflow import run_scenario, ScenarioRequest

        mock_cashflow_service.run_scenario.return_value = {
            "scenario_type": "large_expense",
            "parameters": {"amount": 25000.0, "date": "2026-02-01"},
            "base_min_balance": 50000.0,
            "scenario_min_balance": 25000.0,
            "forecast": [],
            "impact": "moderate",
        }

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_cashflow_service,
        ):
            result = await run_scenario(
                request=ScenarioRequest(
                    scenario_type="large_expense",
                    parameters={"amount": 25000.0, "date": "2026-02-01"},
                ),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result.scenario_type == "large_expense"

    @pytest.mark.asyncio
    async def test_scenario_analysis_revenue_drop(
        self,
        mock_user: MagicMock,
        mock_cashflow_service: AsyncMock,
    ) -> None:
        """Szenario-Analyse: Umsatzeinbruch."""
        from app.api.v1.predictive_cashflow import run_scenario, ScenarioRequest

        mock_cashflow_service.run_scenario.return_value = {
            "scenario_type": "revenue_drop",
            "parameters": {"percentage": 20},
            "base_min_balance": 50000.0,
            "scenario_min_balance": 35000.0,
            "forecast": [],
            "impact": "minor",
        }

        with patch(
            "app.api.v1.predictive_cashflow.PredictiveCashFlowService",
            return_value=mock_cashflow_service,
        ):
            result = await run_scenario(
                request=ScenarioRequest(
                    scenario_type="revenue_drop",
                    parameters={"percentage": 20},
                ),
                current_user=mock_user,
                db=AsyncMock(),
            )

        assert result.scenario_type == "revenue_drop"


class TestPredictiveCashFlowService:
    """Tests fuer PredictiveCashFlowService Hilfsmethoden."""

    @pytest.mark.skip(reason="Service-Methoden noch nicht vollstaendig implementiert")
    @pytest.mark.asyncio
    async def test_confidence_calculation(self) -> None:
        """Test der Confidence-Berechnung basierend auf historischen Daten."""
        pass

    @pytest.mark.skip(reason="Service-Methoden noch nicht vollstaendig implementiert")
    @pytest.mark.asyncio
    async def test_delay_probability_calculation(self) -> None:
        """Test der Verzoegerungswahrscheinlichkeit."""
        pass
