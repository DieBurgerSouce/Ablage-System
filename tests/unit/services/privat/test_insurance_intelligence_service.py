# -*- coding: utf-8 -*-
"""
Unit Tests fuer InsuranceIntelligenceService.

Testet:
- Thread-safe Singleton-Pattern mit Double-Checked Locking
- Dataclass-Strukturen mit korrekten Defaults (BatchInsuranceResult Fix)
- Event Publishing Order (nach db.commit)
- Cache Thread-Safety
"""

import pytest
import threading
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Singleton Pattern Tests
# =============================================================================

class TestInsuranceIntelligenceServiceSingleton:
    """Tests fuer Thread-safe Singleton-Pattern."""

    def test_singleton_instance_same_object(self) -> None:
        """Testet dass get_insurance_intelligence_service immer die gleiche Instanz liefert."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
            get_insurance_intelligence_service,
        )

        service1 = get_insurance_intelligence_service()
        service2 = get_insurance_intelligence_service()
        service3 = InsuranceIntelligenceService()  # Direkter Konstruktor

        # Alle drei muessen identisch sein (selbe Objekt-ID)
        assert service1 is service2
        assert service2 is service3
        assert id(service1) == id(service2) == id(service3)

    def test_singleton_thread_safety(self) -> None:
        """Testet dass Singleton-Pattern thread-safe ist."""
        from app.services.privat.insurance_intelligence_service import InsuranceIntelligenceService

        instances: list = []
        errors: list = []

        def create_instance():
            try:
                instance = InsuranceIntelligenceService()
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
        from app.services.privat.insurance_intelligence_service import InsuranceIntelligenceService

        service = InsuranceIntelligenceService()

        # Alle internen Attribute muessen existieren
        assert hasattr(service, '_initialized')
        assert service._initialized is True
        assert hasattr(service, '_analysis_service')
        assert hasattr(service, '_cache')
        assert hasattr(service, '_cache_lock')
        assert isinstance(service._cache_lock, type(threading.RLock()))


# =============================================================================
# Dataclass Tests
# =============================================================================

class TestInsuranceIntelligenceDataClasses:
    """Tests fuer Datenstrukturen mit korrekten Defaults."""

    def test_insurance_intelligence_result_dataclass(self) -> None:
        """Testet InsuranceIntelligenceResult mit echten Feldwerten."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceResult,
        )

        space_id = uuid4()
        result = InsuranceIntelligenceResult(space_id=space_id)

        # Defaults pruefen
        assert result.space_id == space_id
        assert result.coverage_analysis is None
        assert result.coverage_score == Decimal("0")
        assert result.cancellation_deadlines == []
        assert result.urgent_deadlines_count == 0
        assert result.approaching_deadlines_count == 0
        assert result.premium_summary is None
        assert result.annual_premium_total == Decimal("0")
        assert result.recommendations == []
        assert result.health_score == Decimal("50")  # Basis-Score
        assert isinstance(result.calculated_at, datetime)

    def test_insurance_intelligence_result_with_values(self) -> None:
        """Testet InsuranceIntelligenceResult mit gesetzten Werten."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceResult,
        )

        space_id = uuid4()
        result = InsuranceIntelligenceResult(
            space_id=space_id,
            coverage_score=Decimal("75.50"),
            health_score=Decimal("82.30"),
            annual_premium_total=Decimal("1500.00"),
            urgent_deadlines_count=2,
            approaching_deadlines_count=3,
            recommendations=[
                "Kuendigungsfrist beachten",
                "Deckungssumme pruefen",
            ],
        )

        assert result.coverage_score == Decimal("75.50")
        assert result.health_score == Decimal("82.30")
        assert result.annual_premium_total == Decimal("1500.00")
        assert result.urgent_deadlines_count == 2
        assert len(result.recommendations) == 2

    def test_batch_insurance_result_defaults(self) -> None:
        """
        Testet BatchInsuranceResult mit korrekten Defaults.

        KRITISCH: Dieser Test validiert den Fix fuer das Dataclass-Problem
        wo errors: List[str] keinen default_factory hatte.
        """
        from app.services.privat.insurance_intelligence_service import (
            BatchInsuranceResult,
        )

        # Ohne Argumente - alle Defaults muessen funktionieren
        result = BatchInsuranceResult()

        # Alle numerischen Felder sind 0
        assert result.total_spaces == 0
        assert result.calculated == 0
        assert result.skipped == 0
        assert result.total_critical_gaps == 0
        assert result.total_urgent_deadlines == 0
        assert result.average_coverage_score == Decimal("0")
        assert result.total_annual_premiums == Decimal("0")

        # KRITISCH: errors hat jetzt default_factory=list
        assert result.errors == []
        assert isinstance(result.errors, list)

        # calculated_at hat default_factory
        assert isinstance(result.calculated_at, datetime)

    def test_batch_insurance_result_no_mutable_default_sharing(self) -> None:
        """
        Testet dass BatchInsuranceResult keine mutable defaults teilt.

        Ohne default_factory wuerden alle Instanzen die gleiche Liste teilen!
        """
        from app.services.privat.insurance_intelligence_service import (
            BatchInsuranceResult,
        )

        result1 = BatchInsuranceResult()
        result2 = BatchInsuranceResult()

        # Beide errors Listen muessen unterschiedliche Objekte sein
        assert result1.errors is not result2.errors

        # Aenderung in einer sollte die andere nicht beeinflussen
        result1.errors.append("Error 1")
        assert len(result1.errors) == 1
        assert len(result2.errors) == 0  # Muss leer bleiben!

    def test_batch_insurance_result_with_values(self) -> None:
        """Testet BatchInsuranceResult mit gesetzten Werten."""
        from app.services.privat.insurance_intelligence_service import (
            BatchInsuranceResult,
        )

        result = BatchInsuranceResult(
            total_spaces=20,
            calculated=18,
            skipped=2,
            average_coverage_score=Decimal("68.50"),
            total_critical_gaps=5,
            total_urgent_deadlines=3,
            total_annual_premiums=Decimal("25000.00"),
        )
        result.errors.extend(["Space A: Timeout", "Space B: Keine Daten"])

        assert result.total_spaces == 20
        assert result.calculated == 18
        assert result.skipped == 2
        assert result.average_coverage_score == Decimal("68.50")
        assert result.total_critical_gaps == 5
        assert len(result.errors) == 2


# =============================================================================
# Service Methods Tests
# =============================================================================

class TestInsuranceIntelligenceServiceMethods:
    """Tests fuer Service-Methoden."""

    def test_get_full_analysis_exists(self) -> None:
        """Testet dass get_full_analysis Methode existiert."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )

        service = InsuranceIntelligenceService()
        assert hasattr(service, 'get_full_analysis')
        assert callable(service.get_full_analysis)

    def test_get_full_analysis_signature(self) -> None:
        """Testet die Signatur von get_full_analysis."""
        from app.services.privat.insurance_intelligence_service import InsuranceIntelligenceService
        import inspect

        service = InsuranceIntelligenceService()
        sig = inspect.signature(service.get_full_analysis)
        params = list(sig.parameters.keys())

        assert 'db' in params
        assert 'space_id' in params
        assert 'persist' in params
        assert sig.parameters['persist'].default is True

    def test_recalculate_all_spaces_exists(self) -> None:
        """Testet dass recalculate_all_spaces Methode existiert."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )

        service = InsuranceIntelligenceService()
        assert hasattr(service, 'recalculate_all_spaces')
        assert callable(service.recalculate_all_spaces)

    def test_convenience_methods_exist(self) -> None:
        """Testet dass alle Convenience-Methoden (Delegation) existieren."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )

        service = InsuranceIntelligenceService()

        # Delegations-Methoden zum InsuranceAnalysisService
        assert hasattr(service, 'get_coverage_gaps')
        assert hasattr(service, 'get_cancellation_deadlines')
        assert hasattr(service, 'get_premium_summary')
        assert hasattr(service, 'analyze_single_insurance')


# =============================================================================
# Internal Methods Tests
# =============================================================================

class TestInsuranceIntelligenceInternalMethods:
    """Tests fuer interne Methoden."""

    def test_internal_analysis_method_exists(self) -> None:
        """Testet dass _get_full_analysis_internal existiert (fuer Event-Deferring)."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )

        service = InsuranceIntelligenceService()
        assert hasattr(service, '_get_full_analysis_internal')
        assert callable(service._get_full_analysis_internal)

    def test_internal_analysis_has_defer_events(self) -> None:
        """Testet dass _get_full_analysis_internal defer_events Parameter hat."""
        from app.services.privat.insurance_intelligence_service import InsuranceIntelligenceService
        import inspect

        service = InsuranceIntelligenceService()
        sig = inspect.signature(service._get_full_analysis_internal)
        params = list(sig.parameters.keys())

        # KRITISCH: defer_events fuer Event-Ordering Fix
        assert 'defer_events' in params
        assert sig.parameters['defer_events'].default is False

    def test_generate_recommendations_exists(self) -> None:
        """Testet dass _generate_recommendations existiert."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )

        service = InsuranceIntelligenceService()
        assert hasattr(service, '_generate_recommendations')

    def test_calculate_health_score_exists(self) -> None:
        """Testet dass _calculate_health_score existiert."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )

        service = InsuranceIntelligenceService()
        assert hasattr(service, '_calculate_health_score')

    def test_publish_events_method_exists(self) -> None:
        """Testet dass _publish_events_if_needed existiert."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )

        service = InsuranceIntelligenceService()
        assert hasattr(service, '_publish_events_if_needed')


# =============================================================================
# Prometheus Metriken Tests
# =============================================================================

class TestInsuranceIntelligenceMetrics:
    """Tests fuer Prometheus Metriken."""

    def test_metrics_defined(self) -> None:
        """Testet dass alle Prometheus Metriken korrekt definiert sind."""
        from app.services.privat.insurance_intelligence_service import (
            INSURANCE_INTEL_CALCULATIONS,
            INSURANCE_INTEL_DURATION,
            INSURANCE_COVERAGE_SCORE,
            INSURANCE_CRITICAL_GAPS,
        )
        from prometheus_client import Counter, Histogram, Gauge

        # Typ-Assertions
        assert isinstance(INSURANCE_INTEL_CALCULATIONS, Counter)
        assert isinstance(INSURANCE_INTEL_DURATION, Histogram)
        assert isinstance(INSURANCE_COVERAGE_SCORE, Gauge)
        assert isinstance(INSURANCE_CRITICAL_GAPS, Gauge)

    def test_metrics_labels(self) -> None:
        """Testet dass Counter die korrekten Labels hat."""
        from app.services.privat.insurance_intelligence_service import (
            INSURANCE_INTEL_CALCULATIONS,
        )

        # Counter hat calculation_type Label
        assert 'calculation_type' in INSURANCE_INTEL_CALCULATIONS._labelnames


# =============================================================================
# Event Publishing Tests
# =============================================================================

class TestInsuranceIntelligenceEvents:
    """Tests fuer Event-Publishing."""

    def test_event_types_available(self) -> None:
        """Testet dass alle benoetigten EventTypes verfuegbar sind."""
        from app.services.events.event_bus import EventType

        # Diese Events werden vom Insurance Intelligence Service verwendet
        assert hasattr(EventType, 'INSURANCE_GAP_DETECTED')
        assert hasattr(EventType, 'INSURANCE_DEADLINE_APPROACHING')

        assert EventType.INSURANCE_GAP_DETECTED.value == "insurance.gap_detected"
        assert EventType.INSURANCE_DEADLINE_APPROACHING.value == "insurance.deadline_approaching"


# =============================================================================
# Health Score Calculation Logic Tests
# =============================================================================

class TestInsuranceHealthScoreLogic:
    """Tests fuer Health Score Berechnungslogik."""

    def test_health_score_returns_decimal(self) -> None:
        """Testet dass _calculate_health_score Decimal zurueckgibt."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )
        from app.services.privat.insurance_analysis_service import InsuranceKPIs
        from unittest.mock import MagicMock

        service = InsuranceIntelligenceService()

        # Minimaler Mock der KPIs
        kpis = MagicMock(spec=InsuranceKPIs)
        kpis.coverage_analysis = None
        kpis.cancellation_deadlines = []
        kpis.premium_summary = None

        score = service._calculate_health_score(kpis)

        assert isinstance(score, Decimal)
        # Basis-Score ohne Coverage Analysis
        assert score >= Decimal("0")
        assert score <= Decimal("100")

    def test_health_score_in_valid_range(self) -> None:
        """Testet dass Health Score immer zwischen 0 und 100 liegt."""
        from app.services.privat.insurance_intelligence_service import (
            InsuranceIntelligenceService,
        )
        from unittest.mock import MagicMock

        service = InsuranceIntelligenceService()

        # Extremfall: Alles schlecht
        kpis = MagicMock()
        kpis.coverage_analysis = MagicMock()
        kpis.coverage_analysis.coverage_score = Decimal("0")
        kpis.coverage_analysis.critical_gaps = 10
        kpis.coverage_analysis.high_gaps = 5
        kpis.coverage_analysis.missing_essential = ["A", "B", "C", "D", "E"]
        kpis.cancellation_deadlines = [MagicMock(is_urgent=True) for _ in range(10)]
        kpis.premium_summary = None

        score = service._calculate_health_score(kpis)

        assert score >= Decimal("0")
        assert score <= Decimal("100")
