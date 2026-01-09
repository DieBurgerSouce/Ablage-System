# -*- coding: utf-8 -*-
"""
Unit Tests fuer PrivatKIPromptService.

Testet:
- Singleton-Pattern
- Jinja2 Template-Rendering
- Dataclass-Strukturen
- Cache-Mechanismus
"""

import pytest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession


class TestPrivatKIPromptServiceSingleton:
    """Tests fuer Singleton-Pattern."""

    @pytest.mark.asyncio
    async def test_singleton_instance(self) -> None:
        """Testet dass get_privat_ki_prompt_service immer die gleiche Instanz liefert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
            get_privat_ki_prompt_service,
        )

        service1 = get_privat_ki_prompt_service()
        service2 = get_privat_ki_prompt_service()

        assert service1 is service2

    @pytest.mark.asyncio
    async def test_service_initialization(self) -> None:
        """Testet Service-Initialisierung."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert service is not None
        assert service._template_dir.exists()


class TestKIPromptDataClasses:
    """Tests fuer Datenstrukturen."""

    @pytest.mark.asyncio
    async def test_dataclass_imports(self) -> None:
        """Testet dass alle Datenklassen importierbar sind."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
            PropertyValueAnalysis,
            VehicleDepreciationAnalysis,
            InvestmentAdvice,
            InsuranceCheckResult,
            FinancialQAResponse,
            get_privat_ki_prompt_service,
        )

        assert PrivatKIPromptService is not None
        assert PropertyValueAnalysis is not None
        assert VehicleDepreciationAnalysis is not None
        assert InvestmentAdvice is not None
        assert InsuranceCheckResult is not None
        assert FinancialQAResponse is not None
        assert get_privat_ki_prompt_service is not None

    @pytest.mark.asyncio
    async def test_property_value_analysis_dataclass(self) -> None:
        """Testet PropertyValueAnalysis Datenstruktur."""
        from app.services.privat.ki_prompt_service import (
            PropertyValueAnalysis,
        )

        analysis = PropertyValueAnalysis(
            estimated_value_eur=350000.0,
            confidence_percent=75.0,
            reasoning="Gute Lage in Muenchen-Schwabing, gepflegte Altbauwohnung.",
            market_comparison="Ueber Durchschnitt fuer die Region.",
            value_trend="steigend",
            rental_potential_eur=1200.0,
            roi_estimate_percent=4.1,
            from_cache=False,
        )

        assert analysis.estimated_value_eur == 350000.0
        assert analysis.confidence_percent == 75.0
        assert analysis.value_trend == "steigend"
        assert analysis.from_cache is False

    @pytest.mark.asyncio
    async def test_vehicle_depreciation_analysis_dataclass(self) -> None:
        """Testet VehicleDepreciationAnalysis Datenstruktur."""
        from app.services.privat.ki_prompt_service import (
            VehicleDepreciationAnalysis,
        )

        analysis = VehicleDepreciationAnalysis(
            current_value_eur=25000.0,
            depreciation_percent=35.0,
            remaining_value_percent=65.0,
            optimal_sell_timeframe="innerhalb 12 Monate",
            market_demand="mittel",
            value_factors=["Guter Zustand", "Hoher Kilometerstand", "Beliebtes Modell"],
            from_cache=False,
        )

        assert analysis.current_value_eur == 25000.0
        assert analysis.depreciation_percent == 35.0
        assert analysis.market_demand == "mittel"
        assert len(analysis.value_factors) == 3

    @pytest.mark.asyncio
    async def test_investment_advice_dataclass(self) -> None:
        """Testet InvestmentAdvice Datenstruktur."""
        from app.services.privat.ki_prompt_service import (
            InvestmentAdvice,
        )

        advice = InvestmentAdvice(
            portfolio_health_score=78.0,
            risk_assessment="ausgewogen",
            diversification_score=72.0,
            recommendations=[
                {"priority": "hoch", "action": "Rebalancing", "reasoning": "Uebergewicht Aktien"}
            ],
            rebalancing_needed=True,
            rebalancing_suggestions=["ETF-Anteil erhoehen", "Anleihen reduzieren"],
            tax_optimization_hints=["Freistellungsauftrag nutzen"],
            projected_annual_return_percent=6.5,
            risk_warnings=["Zinsaenderungsrisiko bei Anleihen"],
            from_cache=False,
        )

        assert advice.portfolio_health_score == 78.0
        assert advice.risk_assessment == "ausgewogen"
        assert advice.rebalancing_needed is True
        assert len(advice.recommendations) == 1

    @pytest.mark.asyncio
    async def test_insurance_check_result_dataclass(self) -> None:
        """Testet InsuranceCheckResult Datenstruktur."""
        from app.services.privat.ki_prompt_service import (
            InsuranceCheckResult,
        )

        result = InsuranceCheckResult(
            coverage_score=65.0,
            cost_efficiency_score=80.0,
            critical_gaps=[
                {"insurance_type": "Berufsunfaehigkeit", "priority": "kritisch", "reason": "Fehlende Absicherung"}
            ],
            optimization_suggestions=[
                {"current_insurance": "Hausrat", "suggestion": "Tarif wechseln", "potential_savings_eur": 50}
            ],
            unnecessary_insurances=[],
            recommended_actions=["BU-Versicherung abschliessen", "Hausrat-Tarif pruefen"],
            overall_assessment="Grundlegende Deckung vorhanden, aber wichtige Luecken.",
            from_cache=False,
        )

        assert result.coverage_score == 65.0
        assert result.cost_efficiency_score == 80.0
        assert len(result.critical_gaps) == 1
        assert len(result.recommended_actions) == 2

    @pytest.mark.asyncio
    async def test_financial_qa_response_dataclass(self) -> None:
        """Testet FinancialQAResponse Datenstruktur."""
        from app.services.privat.ki_prompt_service import (
            FinancialQAResponse,
        )

        response = FinancialQAResponse(
            answer="Beim Immobilienkauf muessen Sie Grunderwerbsteuer, Notar- und Grundbuchkosten einplanen.",
            confidence="hoch",
            sources=["BGB", "GrEStG"],
            related_topics=["Nebenkosten", "Finanzierung"],
            action_items=["Nebenkosten-Rechner nutzen", "Finanzierungsangebote vergleichen"],
            warnings=["Zusaetzlich Ruecklagen fuer Renovierung einplanen"],
            consult_expert=True,
            expert_type="Finanzberater",
        )

        assert response.confidence == "hoch"
        assert response.consult_expert is True
        assert response.expert_type == "Finanzberater"
        assert len(response.sources) == 2


class TestKIPromptServiceMethods:
    """Tests fuer Service-Methoden."""

    @pytest.mark.asyncio
    async def test_analyze_property_value_method_exists(self) -> None:
        """Testet dass analyze_property_value Methode existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert hasattr(service, 'analyze_property_value')
        assert callable(getattr(service, 'analyze_property_value'))

    @pytest.mark.asyncio
    async def test_analyze_vehicle_depreciation_method_exists(self) -> None:
        """Testet dass analyze_vehicle_depreciation Methode existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert hasattr(service, 'analyze_vehicle_depreciation')
        assert callable(getattr(service, 'analyze_vehicle_depreciation'))

    @pytest.mark.asyncio
    async def test_get_investment_advice_method_exists(self) -> None:
        """Testet dass get_investment_advice Methode existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert hasattr(service, 'get_investment_advice')
        assert callable(getattr(service, 'get_investment_advice'))

    @pytest.mark.asyncio
    async def test_check_insurance_coverage_method_exists(self) -> None:
        """Testet dass check_insurance_coverage Methode existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert hasattr(service, 'check_insurance_coverage')
        assert callable(getattr(service, 'check_insurance_coverage'))

    @pytest.mark.asyncio
    async def test_financial_qa_method_exists(self) -> None:
        """Testet dass financial_qa Methode existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert hasattr(service, 'financial_qa')
        assert callable(getattr(service, 'financial_qa'))

    @pytest.mark.asyncio
    async def test_render_template_method_exists(self) -> None:
        """Testet dass _render_template Methode existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert hasattr(service, '_render_template')
        assert callable(getattr(service, '_render_template'))


class TestKIPromptTemplates:
    """Tests fuer Jinja2 Templates."""

    @pytest.mark.asyncio
    async def test_template_directory_exists(self) -> None:
        """Testet dass Template-Verzeichnis existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        assert service._template_dir.exists()
        assert service._template_dir.is_dir()

    @pytest.mark.asyncio
    async def test_property_valuation_template_exists(self) -> None:
        """Testet dass property_valuation.j2 existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        template_path = service._template_dir / "property_valuation.j2"
        assert template_path.exists()

    @pytest.mark.asyncio
    async def test_vehicle_analysis_template_exists(self) -> None:
        """Testet dass vehicle_analysis.j2 existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        template_path = service._template_dir / "vehicle_analysis.j2"
        assert template_path.exists()

    @pytest.mark.asyncio
    async def test_investment_advice_template_exists(self) -> None:
        """Testet dass investment_advice.j2 existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        template_path = service._template_dir / "investment_advice.j2"
        assert template_path.exists()

    @pytest.mark.asyncio
    async def test_insurance_check_template_exists(self) -> None:
        """Testet dass insurance_check.j2 existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        template_path = service._template_dir / "insurance_check.j2"
        assert template_path.exists()

    @pytest.mark.asyncio
    async def test_financial_qa_template_exists(self) -> None:
        """Testet dass financial_qa.j2 existiert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()
        template_path = service._template_dir / "financial_qa.j2"
        assert template_path.exists()

    @pytest.mark.asyncio
    async def test_template_rendering(self) -> None:
        """Testet Jinja2 Template-Rendering."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
        )

        service = PrivatKIPromptService()

        rendered = service._render_template(
            "property_valuation.j2",
            address="Musterstrasse 1, 80333 Muenchen",
            year_built=1985,
            living_area_sqm=85,
            rooms=3,
            property_type="Wohnung",
            current_rent=1200,
            purchase_price=350000,
            region="Muenchen-Schwabing",
        )

        assert "Musterstrasse" in rendered
        assert "80333" in rendered
        assert "1985" in rendered
        assert "85" in rendered
        assert "1200" in rendered or "1.200" in rendered


class TestKIPromptMetrics:
    """Tests fuer Prometheus Metriken."""

    @pytest.mark.asyncio
    async def test_metrics_exist(self) -> None:
        """Testet dass Prometheus Metriken definiert sind."""
        from app.services.privat.ki_prompt_service import (
            KI_PROMPT_COUNTER,
            KI_PROMPT_DURATION,
            KI_CACHE_HIT_COUNTER,
        )

        assert KI_PROMPT_COUNTER is not None
        assert KI_PROMPT_DURATION is not None
        assert KI_CACHE_HIT_COUNTER is not None
