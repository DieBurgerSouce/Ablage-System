# -*- coding: utf-8 -*-
"""
Unit Tests fuer PrivatKIPromptService.

Testet:
- Thread-safe Singleton-Pattern mit Double-Checked Locking
- Dataclass-Strukturen mit korrekten Feldern
- Jinja2 Template-Rendering
- Thread-safe Cache-Mechanismus
"""

import pytest
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Singleton Pattern Tests
# =============================================================================

class TestPrivatKIPromptServiceSingleton:
    """Tests fuer Thread-safe Singleton-Pattern."""

    def test_singleton_instance_same_object(self) -> None:
        """Testet dass get_privat_ki_prompt_service immer die gleiche Instanz liefert."""
        from app.services.privat.ki_prompt_service import (
            PrivatKIPromptService,
            get_privat_ki_prompt_service,
        )

        service1 = get_privat_ki_prompt_service()
        service2 = get_privat_ki_prompt_service()
        service3 = PrivatKIPromptService()  # Direkter Konstruktor

        # Alle drei muessen identisch sein (selbe Objekt-ID)
        assert service1 is service2
        assert service2 is service3
        assert id(service1) == id(service2) == id(service3)

    def test_singleton_thread_safety(self) -> None:
        """Testet dass Singleton-Pattern thread-safe ist."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        instances: list = []
        errors: list = []

        def create_instance():
            try:
                instance = PrivatKIPromptService()
                instances.append(id(instance))
            except Exception as e:
                errors.append(str(e))

        # 100 Threads gleichzeitig starten
        threads = [threading.Thread(target=create_instance) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Keine Fehler
        assert len(errors) == 0, f"Errors: {errors}"

        # Alle Instanzen muessen identisch sein (selbe ID)
        assert len(set(instances)) == 1, (
            f"Multiple instances created: {len(set(instances))} unique IDs"
        )

    def test_singleton_initialization_complete(self) -> None:
        """Testet dass Singleton vollstaendig initialisiert ist."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        # Alle internen Attribute muessen existieren
        assert hasattr(service, '_initialized')
        assert service._initialized is True
        assert hasattr(service, '_llm_service')
        assert hasattr(service, '_template_dir')
        assert hasattr(service, '_jinja_env')
        assert hasattr(service, '_cache')
        assert hasattr(service, '_cache_lock')
        assert isinstance(service._cache_lock, type(threading.RLock()))


# =============================================================================
# Dataclass Tests
# =============================================================================

class TestKIPromptDataClasses:
    """Tests fuer Datenstrukturen mit korrekten Feldern."""

    def test_property_value_analysis_dataclass(self) -> None:
        """Testet PropertyValueAnalysis mit echten Feldwerten."""
        from app.services.privat.ki_prompt_service import PropertyValueAnalysis

        property_id = uuid4()
        analysis = PropertyValueAnalysis(
            property_id=property_id,
            estimated_value_eur=350000.0,
            confidence_percent=75,
            reasoning="Gute Lage in Muenchen-Schwabing, gepflegte Altbauwohnung.",
            market_comparison="Ueber Durchschnitt fuer die Region.",
            value_trend="steigend",
            rental_potential_eur=1200.0,
            roi_estimate_percent=4.1,
            cached=False,
            analysis_time_ms=1234.5,
        )

        # Werte pruefen
        assert analysis.property_id == property_id
        assert analysis.estimated_value_eur == 350000.0
        assert analysis.confidence_percent == 75
        assert analysis.value_trend == "steigend"
        assert analysis.cached is False
        assert analysis.analysis_time_ms == 1234.5

        # Optionale Felder
        assert analysis.rental_potential_eur == 1200.0
        assert analysis.roi_estimate_percent == 4.1
        assert analysis.raw_response is None  # Default

    def test_property_value_analysis_defaults(self) -> None:
        """Testet PropertyValueAnalysis mit minimalen Pflichtfeldern."""
        from app.services.privat.ki_prompt_service import PropertyValueAnalysis

        analysis = PropertyValueAnalysis(
            property_id=uuid4(),
            estimated_value_eur=0.0,
            confidence_percent=0,
            reasoning="",
            market_comparison="",
            value_trend="stabil",
        )

        # Defaults pruefen
        assert analysis.rental_potential_eur is None
        assert analysis.roi_estimate_percent is None
        assert analysis.raw_response is None
        assert analysis.cached is False
        assert analysis.analysis_time_ms == 0.0

    def test_vehicle_depreciation_analysis_dataclass(self) -> None:
        """Testet VehicleDepreciationAnalysis mit echten Feldwerten."""
        from app.services.privat.ki_prompt_service import VehicleDepreciationAnalysis

        vehicle_id = uuid4()
        analysis = VehicleDepreciationAnalysis(
            vehicle_id=vehicle_id,
            current_value_eur=25000.0,
            original_value_eur=40000.0,
            depreciation_percent=37.5,
            remaining_value_percent=62.5,
            optimal_sell_timeframe="innerhalb 12 Monate",
            market_demand="mittel",
            value_factors=["Guter Zustand", "Hoher Kilometerstand", "Beliebtes Modell"],
            cached=False,
        )

        assert analysis.vehicle_id == vehicle_id
        assert analysis.current_value_eur == 25000.0
        assert analysis.original_value_eur == 40000.0
        assert analysis.depreciation_percent == 37.5
        assert analysis.remaining_value_percent == 62.5
        assert analysis.market_demand == "mittel"
        assert len(analysis.value_factors) == 3
        assert "Guter Zustand" in analysis.value_factors

    def test_investment_advice_dataclass(self) -> None:
        """Testet InvestmentAdvice mit echten Feldwerten."""
        from app.services.privat.ki_prompt_service import InvestmentAdvice

        space_id = uuid4()
        advice = InvestmentAdvice(
            space_id=space_id,
            risk_profile="ausgewogen",
            current_allocation_assessment="Gute Diversifikation vorhanden",
            optimization_suggestions=["ETF-Anteil erhoehen", "Anleihen reduzieren"],
            rebalancing_needed=True,
            expected_return_estimate="5-7% p.a.",
            diversification_score=72,
        )

        assert advice.space_id == space_id
        assert advice.risk_profile == "ausgewogen"
        assert advice.rebalancing_needed is True
        assert advice.diversification_score == 72
        assert len(advice.optimization_suggestions) == 2

    def test_insurance_check_result_dataclass(self) -> None:
        """Testet InsuranceCheckResult mit korrekten Defaults."""
        from app.services.privat.ki_prompt_service import InsuranceCheckResult

        space_id = uuid4()
        result = InsuranceCheckResult(
            space_id=space_id,
            coverage_assessment="verbesserungswuerdig",
            identified_gaps=["Berufsunfaehigkeit fehlt"],
            recommendations=["BU-Versicherung abschliessen"],
        )

        assert result.space_id == space_id
        assert result.coverage_assessment == "verbesserungswuerdig"
        assert len(result.identified_gaps) == 1
        assert len(result.recommendations) == 1

        # Default: priority_actions hat default_factory=list
        assert result.priority_actions == []
        assert isinstance(result.priority_actions, list)
        assert result.cost_optimization_potential_eur is None

    def test_insurance_check_result_no_mutable_default_sharing(self) -> None:
        """Testet dass InsuranceCheckResult keine mutable defaults teilt."""
        from app.services.privat.ki_prompt_service import InsuranceCheckResult

        result1 = InsuranceCheckResult(
            space_id=uuid4(),
            coverage_assessment="ausreichend",
            identified_gaps=[],
            recommendations=[],
        )
        result2 = InsuranceCheckResult(
            space_id=uuid4(),
            coverage_assessment="ausreichend",
            identified_gaps=[],
            recommendations=[],
        )

        # priority_actions Listen muessen unterschiedliche Objekte sein
        assert result1.priority_actions is not result2.priority_actions

        # Aenderung in einer sollte die andere nicht beeinflussen
        result1.priority_actions.append("Aktion 1")
        assert len(result1.priority_actions) == 1
        assert len(result2.priority_actions) == 0

    def test_financial_qa_response_dataclass(self) -> None:
        """Testet FinancialQAResponse mit echten Feldwerten."""
        from app.services.privat.ki_prompt_service import FinancialQAResponse

        response = FinancialQAResponse(
            question="Was sind Nebenkosten beim Hauskauf?",
            answer="Nebenkosten umfassen Grunderwerbsteuer, Notar- und Grundbuchkosten.",
            confidence="hoch",
            sources_used=["BGB", "GrEStG"],
            follow_up_suggestions=["Nebenkosten-Rechner nutzen"],
            disclaimer="Diese Antwort ersetzt keine Finanzberatung.",
        )

        assert response.question == "Was sind Nebenkosten beim Hauskauf?"
        assert response.confidence == "hoch"
        assert len(response.sources_used) == 2
        assert len(response.follow_up_suggestions) == 1
        assert "Finanzberatung" in response.disclaimer


# =============================================================================
# Service Methods Tests
# =============================================================================

class TestKIPromptServiceMethods:
    """Tests fuer Service-Methoden."""

    def test_analyze_property_value_exists(self) -> None:
        """Testet dass analyze_property_value Methode existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert hasattr(service, 'analyze_property_value')
        assert callable(service.analyze_property_value)

    def test_analyze_property_value_signature(self) -> None:
        """Testet die Signatur von analyze_property_value."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService
        import inspect

        service = PrivatKIPromptService()
        sig = inspect.signature(service.analyze_property_value)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'property_id' in params
        assert 'use_cache' in params
        assert sig.parameters['use_cache'].default is True

    def test_analyze_vehicle_depreciation_exists(self) -> None:
        """Testet dass analyze_vehicle_depreciation Methode existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert hasattr(service, 'analyze_vehicle_depreciation')
        assert callable(service.analyze_vehicle_depreciation)

    def test_get_investment_advice_exists(self) -> None:
        """Testet dass get_investment_advice Methode existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert hasattr(service, 'get_investment_advice')
        assert callable(service.get_investment_advice)

    def test_check_insurance_coverage_exists(self) -> None:
        """Testet dass check_insurance_coverage Methode existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert hasattr(service, 'check_insurance_coverage')
        assert callable(service.check_insurance_coverage)

    def test_financial_qa_exists(self) -> None:
        """Testet dass financial_qa Methode existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert hasattr(service, 'financial_qa')
        assert callable(service.financial_qa)

    def test_render_template_method_exists(self) -> None:
        """Testet dass _render_template Methode existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert hasattr(service, '_render_template')
        assert callable(service._render_template)

    def test_clear_cache_method_exists(self) -> None:
        """Testet dass clear_cache Methode existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert hasattr(service, 'clear_cache')
        assert callable(service.clear_cache)


# =============================================================================
# Template Tests
# =============================================================================

class TestKIPromptTemplates:
    """Tests fuer Jinja2 Templates."""

    def test_template_directory_exists(self) -> None:
        """Testet dass Template-Verzeichnis existiert."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        assert service._template_dir.exists()
        assert service._template_dir.is_dir()

    def test_required_templates_exist(self) -> None:
        """Testet dass alle erforderlichen Templates existieren."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        required_templates = [
            "property_valuation.j2",
            "vehicle_analysis.j2",
            "investment_advice.j2",
            "insurance_check.j2",
            "financial_qa.j2",
        ]

        for template_name in required_templates:
            template_path = service._template_dir / template_name
            assert template_path.exists(), f"Template {template_name} fehlt"

    def test_template_rendering(self) -> None:
        """Testet Jinja2 Template-Rendering mit echten Variablen."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

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

        # Pruefen dass wichtige Werte im Ergebnis sind
        assert "Musterstrasse" in rendered
        assert "80333" in rendered or "Muenchen" in rendered
        assert "1985" in rendered
        assert isinstance(rendered, str)
        assert len(rendered) > 100  # Sinnvolle Laenge

    def test_jinja_env_configuration(self) -> None:
        """Testet dass Jinja2 Environment korrekt konfiguriert ist."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        # Jinja2 Environment existiert
        assert hasattr(service, '_jinja_env')
        assert service._jinja_env is not None

        # trim_blocks und lstrip_blocks sind aktiviert
        assert service._jinja_env.trim_blocks is True
        assert service._jinja_env.lstrip_blocks is True


# =============================================================================
# Cache Tests
# =============================================================================

class TestKIPromptCache:
    """Tests fuer Thread-safe Cache-Mechanismus."""

    def test_cache_key_generation(self) -> None:
        """Testet Cache-Key Generierung."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        entity_id = uuid4()
        key1 = service._get_cache_key("property", entity_id)
        key2 = service._get_cache_key("property", entity_id)
        key3 = service._get_cache_key("vehicle", entity_id)

        # Gleiche Parameter = gleicher Key
        assert key1 == key2

        # Unterschiedlicher Prefix = unterschiedlicher Key
        assert key1 != key3

        # Key ist ein Hash (32 Zeichen)
        assert len(key1) == 32
        assert isinstance(key1, str)

    def test_cache_set_and_get(self) -> None:
        """Testet Cache-Set und -Get Operationen."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        test_key = "test_key_12345"
        test_data = {"value": 42, "name": "Test"}

        # Setzen
        service._set_cache(test_key, test_data)

        # Holen - gibt eine Kopie zurueck
        retrieved = service._get_from_cache(test_key)

        assert retrieved is not None
        assert retrieved["value"] == 42
        assert retrieved["name"] == "Test"

        # Kopie pruefen (nicht das Original)
        assert retrieved is not test_data

    def test_cache_returns_copy_to_prevent_mutation(self) -> None:
        """Testet dass Cache Kopien zurueckgibt um Mutation zu verhindern."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()
        test_key = "mutation_test_key"
        original_data = {"items": [1, 2, 3]}

        service._set_cache(test_key, original_data)

        # Erste Abfrage
        result1 = service._get_from_cache(test_key)
        result1["items"].append(4)  # Mutieren

        # Zweite Abfrage - sollte nicht mutiert sein
        result2 = service._get_from_cache(test_key)

        assert len(result2["items"]) == 3, "Cache wurde mutiert!"
        assert 4 not in result2["items"]

    def test_clear_cache_all(self) -> None:
        """Testet komplettes Cache-Loeschen."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        # Mehrere Eintraege hinzufuegen
        service._set_cache("key1", {"data": 1})
        service._set_cache("key2", {"data": 2})
        service._set_cache("key3", {"data": 3})

        # Alle loeschen
        count = service.clear_cache()

        assert count >= 3
        assert service._get_from_cache("key1") is None
        assert service._get_from_cache("key2") is None
        assert service._get_from_cache("key3") is None


# =============================================================================
# Prometheus Metrics Tests
# =============================================================================

class TestKIPromptMetrics:
    """Tests fuer Prometheus Metriken."""

    def test_metrics_defined(self) -> None:
        """Testet dass alle Prometheus Metriken korrekt definiert sind."""
        from app.services.privat.ki_prompt_service import (
            KI_ANALYSIS_REQUESTS,
            KI_ANALYSIS_DURATION,
            KI_CACHE_HITS,
            KI_CACHE_MISSES,
        )
        from prometheus_client import Counter, Histogram

        # Typ-Assertions
        assert isinstance(KI_ANALYSIS_REQUESTS, Counter)
        assert isinstance(KI_ANALYSIS_DURATION, Histogram)
        assert isinstance(KI_CACHE_HITS, Counter)
        assert isinstance(KI_CACHE_MISSES, Counter)

    def test_metrics_labels(self) -> None:
        """Testet dass Metriken die korrekten Labels haben."""
        from app.services.privat.ki_prompt_service import (
            KI_ANALYSIS_REQUESTS,
            KI_ANALYSIS_DURATION,
        )

        # Counter hat analysis_type und status Labels
        assert 'analysis_type' in KI_ANALYSIS_REQUESTS._labelnames
        assert 'status' in KI_ANALYSIS_REQUESTS._labelnames

        # Histogram hat analysis_type Label
        assert 'analysis_type' in KI_ANALYSIS_DURATION._labelnames


# =============================================================================
# Internal Methods Tests
# =============================================================================

class TestKIPromptInternalMethods:
    """Tests fuer interne Methoden."""

    def test_parse_json_response_clean_json(self) -> None:
        """Testet JSON-Parsing von sauberem JSON."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        result = service._parse_json_response('{"key": "value", "number": 42}')

        assert result["key"] == "value"
        assert result["number"] == 42

    def test_parse_json_response_markdown_block(self) -> None:
        """Testet JSON-Parsing aus Markdown Code-Block."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        markdown_response = '''```json
{"key": "value", "number": 42}
```'''

        result = service._parse_json_response(markdown_response)

        assert result["key"] == "value"
        assert result["number"] == 42

    def test_parse_json_response_invalid_returns_empty(self) -> None:
        """Testet dass ungueltigem JSON ein leeres Dict zurueckgibt."""
        from app.services.privat.ki_prompt_service import PrivatKIPromptService

        service = PrivatKIPromptService()

        result = service._parse_json_response("Das ist kein JSON")

        assert result == {}
        assert isinstance(result, dict)
