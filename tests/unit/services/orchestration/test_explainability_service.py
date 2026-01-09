# -*- coding: utf-8 -*-
"""
Unit Tests fuer ExplainabilityService.

Testet:
- Singleton-Verhalten
- Explanation Generation
- Factor-Berechnung
- Impact Breakdown
- Template System

PHASE 0.7 CRITICAL FIX: 80%+ Coverage Ziel
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.explainability_service import (
    ExplainabilityService,
    DecisionExplanation,
    ExplanationFactor,
    AlternativeOption,
    ImpactBreakdown,
    FactorType,
    ImpactDirection,
    ConfidenceLevel,
    get_explainability_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset Singleton vor und nach jedem Test."""
    ExplainabilityService._instance = None
    yield
    ExplainabilityService._instance = None


@pytest.fixture
def service(reset_service):
    """Frische Service-Instanz fuer jeden Test."""
    return ExplainabilityService()


@pytest.fixture
def sample_factor():
    """Erstellt einen Beispiel-Faktor."""
    return ExplanationFactor(
        factor_type=FactorType.FINANCIAL,
        name="Zinsersparnis",
        description="Differenz zwischen aktuellem und neuem Zinssatz",
        current_value=4.2,
        reference_value=3.1,
        unit="%",
        impact_direction=ImpactDirection.POSITIVE,
        impact_weight=0.35,
        impact_points=25.0,
    )


@pytest.fixture
def sample_breakdown():
    """Erstellt ein Beispiel-Impact-Breakdown."""
    return ImpactBreakdown(
        immediate_savings=Decimal("0"),
        annual_savings=Decimal("1500"),
        one_time_cost=Decimal("200"),
        ongoing_cost=Decimal("0"),
        time_to_implement="2 Wochen",
        time_to_benefit="Sofort nach Umschuldung",
        risk_before=45.0,
        risk_after=25.0,
    )


@pytest.fixture
def sample_alternative():
    """Erstellt eine Beispiel-Alternative."""
    return AlternativeOption(
        name="Sondertilgung",
        description="Zusaetzliche Tilgungen statt Refinanzierung",
        pros=["Keine Wechselkosten", "Sofort umsetzbar"],
        cons=["Geringere Ersparnis", "Liquiditaetsbindung"],
        why_not_chosen="Geringere Gesamtersparnis von nur 800 EUR",
        estimated_impact=35.0,
    )


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_service):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = ExplainabilityService()
        instance2 = ExplainabilityService()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_explainability_service()
        instance2 = get_explainability_service()

        assert instance1 is instance2

    def test_initialization_only_once(self, reset_service):
        """Initialisierung erfolgt nur einmal."""
        instance = ExplainabilityService()
        original_templates = instance._templates

        instance2 = ExplainabilityService()

        assert instance2._templates is original_templates


# =============================================================================
# ExplanationFactor Tests
# =============================================================================

class TestExplanationFactor:
    """Tests fuer ExplanationFactor."""

    def test_defaults(self):
        """ExplanationFactor hat sinnvolle Defaults."""
        factor = ExplanationFactor()

        assert factor.id is not None
        assert factor.factor_type == FactorType.FINANCIAL
        assert factor.impact_direction == ImpactDirection.NEUTRAL
        assert factor.visualization_type == "bar"

    def test_to_dict(self, sample_factor):
        """to_dict gibt korrektes Dictionary zurueck."""
        result = sample_factor.to_dict()

        assert result["name"] == "Zinsersparnis"
        assert result["factor_type"] == "financial"
        assert result["current_value"] == 4.2
        assert result["reference_value"] == 3.1
        assert result["unit"] == "%"
        assert result["impact_direction"] == "positiv"
        assert result["impact_weight"] == 0.35


# =============================================================================
# AlternativeOption Tests
# =============================================================================

class TestAlternativeOption:
    """Tests fuer AlternativeOption."""

    def test_to_dict(self, sample_alternative):
        """to_dict gibt korrektes Dictionary zurueck."""
        result = sample_alternative.to_dict()

        assert result["name"] == "Sondertilgung"
        assert "Keine Wechselkosten" in result["pros"]
        assert "Geringere Ersparnis" in result["cons"]
        assert "800 EUR" in result["why_not_chosen"]
        assert result["estimated_impact"] == 35.0


# =============================================================================
# ImpactBreakdown Tests
# =============================================================================

class TestImpactBreakdown:
    """Tests fuer ImpactBreakdown."""

    def test_net_benefit_calculation(self, sample_breakdown):
        """Netto-Vorteil wird korrekt berechnet."""
        net = sample_breakdown.net_benefit()

        # 0 + 1500 - 200 - 0 = 1300
        assert net == Decimal("1300")

    def test_net_benefit_negative(self):
        """Negativer Netto-Vorteil moeglich."""
        breakdown = ImpactBreakdown(
            immediate_savings=Decimal("100"),
            annual_savings=Decimal("0"),
            one_time_cost=Decimal("500"),
            ongoing_cost=Decimal("50"),
        )

        net = breakdown.net_benefit()

        assert net == Decimal("-450")

    def test_to_dict(self, sample_breakdown):
        """to_dict gibt korrektes Dictionary zurueck."""
        result = sample_breakdown.to_dict()

        assert result["annual_savings"] == 1500.0
        assert result["one_time_cost"] == 200.0
        assert result["net_benefit"] == 1300.0
        assert result["time_to_implement"] == "2 Wochen"
        assert result["risk_before"] == 45.0
        assert result["risk_after"] == 25.0
        assert result["risk_reduction"] == 20.0  # 45 - 25


# =============================================================================
# DecisionExplanation Tests
# =============================================================================

class TestDecisionExplanation:
    """Tests fuer DecisionExplanation."""

    def test_defaults(self):
        """DecisionExplanation hat sinnvolle Defaults."""
        explanation = DecisionExplanation()

        assert explanation.id is not None
        assert explanation.confidence_level == ConfidenceLevel.MEDIUM
        assert explanation.factors == []
        assert explanation.alternatives == []
        assert explanation.created_at is not None

    def test_to_dict(self, sample_factor, sample_breakdown, sample_alternative):
        """to_dict gibt vollstaendiges Dictionary zurueck."""
        explanation = DecisionExplanation(
            decision_id=uuid4(),
            headline="Refinanzierung spart 23.400 EUR",
            summary="Der aktuelle Zins liegt ueber dem Marktzins.",
            main_reason="Zinsdifferenz von 1.1%",
            factors=[sample_factor],
            impact_breakdown=sample_breakdown,
            alternatives=[sample_alternative],
            confidence_level=ConfidenceLevel.HIGH,
            confidence_percent=85.0,
            confidence_reasoning="Basiert auf 24 Monaten historischer Daten",
            data_quality="24 Monate Zinsentwicklung",
            suggested_next_steps=["Angebote einholen", "Kuendigungsfrist pruefen"],
            action_url="/loans/123/refinance",
        )

        result = explanation.to_dict()

        assert result["headline"] == "Refinanzierung spart 23.400 EUR"
        assert result["main_reason"] == "Zinsdifferenz von 1.1%"
        assert len(result["factors"]) == 1
        assert result["impact_breakdown"]["net_benefit"] == 1300.0
        assert len(result["alternatives"]) == 1
        assert result["confidence"]["level"] == "hoch"
        assert result["confidence"]["percent"] == 85.0
        assert len(result["suggested_next_steps"]) == 2


# =============================================================================
# Service Explanation Generation Tests
# =============================================================================

class TestExplanationGeneration:
    """Tests fuer Explanation-Generierung."""

    @pytest.mark.asyncio
    async def test_explain_recommendation_refinancing(self, service):
        """Refinanzierungs-Erklaerung wird generiert."""
        recommendation_id = uuid4()
        recommendation_data = {
            "category": "refinanzierung",
            "current_rate": 4.2,
            "market_rate": 3.1,
            "remaining_years": 15,
            "remaining_balance": 150000,
            "loan_id": str(uuid4()),
        }

        explanation = await service.explain_recommendation(
            recommendation_id=recommendation_id,
            recommendation_data=recommendation_data,
        )

        assert explanation is not None
        assert explanation.recommendation_id == recommendation_id
        assert explanation.headline != ""

    @pytest.mark.asyncio
    async def test_explain_health_score(self, service):
        """Health Score Breakdown wird generiert."""
        health_score_data = {
            "score": 67.5,
            "components": {
                "debt_management": {"score": 45, "description": "DTI bei 45%"},
                "liquidity": {"score": 60, "description": "Notgroschen 3 Monate"},
                "diversification": {"score": 50, "description": "Portfolio ausgewogen"},
                "insurance": {"score": 70, "description": "Grundabsicherung vorhanden"},
                "retirement": {"score": 55, "description": "Vorsorge aufbauen"},
                "savings": {"score": 65, "description": "Sparrate 12%"},
            },
        }

        explanation = await service.explain_health_score(
            health_score_data=health_score_data,
        )

        assert explanation is not None
        assert "67" in explanation.headline
        assert len(explanation.factors) > 0

    @pytest.mark.asyncio
    async def test_explain_early_warning(self, service):
        """Early Warning Erklaerung wird generiert."""
        warning_data = {
            "kpi_name": "DTI",
            "current_value": 42.0,
            "projected_value": 55.0,
            "threshold_value": 50.0,
            "months_to_breach": 4,
        }

        explanation = await service.explain_early_warning(
            warning_data=warning_data,
        )

        assert explanation is not None
        assert "DTI" in explanation.headline
        assert "4" in explanation.headline  # Monate


# =============================================================================
# Confidence in Explanations Tests
# =============================================================================

class TestConfidenceInExplanations:
    """Tests fuer Konfidenz in generierten Erklaerungen."""

    @pytest.mark.asyncio
    async def test_health_score_explanation_has_confidence(self, service):
        """Health Score Erklaerung hat Konfidenz-Daten."""
        health_score_data = {
            "score": 75.0,
            "components": {
                "debt_management": {"score": 70, "description": ""},
                "liquidity": {"score": 80, "description": ""},
                "diversification": {"score": 75, "description": ""},
                "insurance": {"score": 70, "description": ""},
                "retirement": {"score": 75, "description": ""},
                "savings": {"score": 80, "description": ""},
            },
        }

        explanation = await service.explain_health_score(health_score_data)

        assert explanation.confidence_level in list(ConfidenceLevel)
        assert explanation.confidence_percent >= 0

    @pytest.mark.asyncio
    async def test_refinancing_explanation_has_high_confidence(self, service):
        """Refinanzierungs-Erklaerung hat hohe Konfidenz."""
        recommendation_data = {
            "category": "refinanzierung",
            "current_rate": 4.5,
            "market_rate": 3.0,
            "remaining_years": 10,
            "remaining_balance": 100000,
        }

        explanation = await service.explain_recommendation(
            recommendation_id=uuid4(),
            recommendation_data=recommendation_data,
        )

        # Refinanzierung sollte hohe Konfidenz haben
        assert explanation.confidence_level in [ConfidenceLevel.HIGH, ConfidenceLevel.VERY_HIGH]
        assert explanation.confidence_percent >= 75.0


# =============================================================================
# Template Tests
# =============================================================================

class TestTemplates:
    """Tests fuer Template-System."""

    def test_templates_loaded(self, service):
        """Templates werden geladen."""
        assert service._templates is not None
        assert len(service._templates) > 0

    def test_refinanzierung_template_exists(self, service):
        """Refinanzierung-Template existiert."""
        assert "refinanzierung" in service._templates

        template = service._templates["refinanzierung"]
        assert "headline" in template
        assert "summary" in template
        assert "main_reason" in template

    def test_template_placeholders(self, service):
        """Templates haben korrekte Platzhalter."""
        template = service._templates.get("refinanzierung", {})

        if "headline" in template:
            assert "{savings}" in template["headline"] or "savings" in template["headline"]


# =============================================================================
# Cache Tests
# =============================================================================

class TestCache:
    """Tests fuer Explanation-Cache."""

    def test_cache_initialized(self, service):
        """Cache wird initialisiert."""
        assert hasattr(service, "_explanation_cache")
        assert isinstance(service._explanation_cache, dict)

    @pytest.mark.asyncio
    async def test_cache_stores_explanation(self, service):
        """Erklaerung wird gecached."""
        cache_key = uuid4()
        explanation = DecisionExplanation(
            headline="Test",
        )

        service._cache_explanation(cache_key, explanation)

        assert cache_key in service._explanation_cache
        assert service._explanation_cache[cache_key] is explanation

    @pytest.mark.asyncio
    async def test_cache_retrieval(self, service):
        """Gecachte Erklaerung wird gefunden."""
        cache_key = uuid4()
        explanation = DecisionExplanation(
            headline="Cached Explanation",
        )

        service._cache_explanation(cache_key, explanation)
        cached = service.get_cached_explanation(cache_key)

        assert cached is not None
        assert cached.headline == "Cached Explanation"

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, service):
        """Nicht gecachte ID gibt None zurueck."""
        result = service.get_cached_explanation(uuid4())

        assert result is None


# =============================================================================
# Enums Tests
# =============================================================================

class TestEnums:
    """Tests fuer Enums."""

    def test_factor_type_values(self):
        """FactorType hat erwartete Werte."""
        assert FactorType.FINANCIAL.value == "financial"
        assert FactorType.RISK.value == "risk"
        assert FactorType.TREND.value == "trend"
        assert FactorType.PROJECTION.value == "projection"

    def test_impact_direction_values(self):
        """ImpactDirection hat deutsche Werte."""
        assert ImpactDirection.POSITIVE.value == "positiv"
        assert ImpactDirection.NEGATIVE.value == "negativ"
        assert ImpactDirection.NEUTRAL.value == "neutral"

    def test_confidence_level_values(self):
        """ConfidenceLevel hat deutsche Werte."""
        assert ConfidenceLevel.VERY_HIGH.value == "sehr_hoch"
        assert ConfidenceLevel.HIGH.value == "hoch"
        assert ConfidenceLevel.MEDIUM.value == "mittel"
        assert ConfidenceLevel.LOW.value == "niedrig"
        assert ConfidenceLevel.UNCERTAIN.value == "unsicher"
