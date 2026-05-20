# -*- coding: utf-8 -*-
"""
Unit Tests fuer KPIOrchestrationService.

Testet:
- Singleton-Pattern (Thread-safe)
- Dataclass-Strukturen mit korrekten Defaults
- Service Lazy-Loading (Thread-safe)
- Event Publishing Order (nach db.commit)
"""

import pytest
import threading
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# Singleton Pattern Tests
# =============================================================================

class TestKPIOrchestrationServiceSingleton:
    """Tests fuer Thread-safe Singleton-Pattern."""

    def test_singleton_instance_same_object(self) -> None:
        """Testet dass get_kpi_orchestration_service immer die gleiche Instanz liefert."""
        from app.services.privat.kpi_orchestrator import (
            KPIOrchestrationService,
            get_kpi_orchestration_service,
        )

        service1 = get_kpi_orchestration_service()
        service2 = get_kpi_orchestration_service()
        service3 = KPIOrchestrationService()  # Direkter Konstruktor

        # Alle drei muessen identisch sein (selbe Objekt-ID)
        assert service1 is service2
        assert service2 is service3
        assert id(service1) == id(service2) == id(service3)

    def test_singleton_thread_safety(self) -> None:
        """Testet dass Singleton-Pattern thread-safe ist."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService

        instances: list = []
        errors: list = []

        def create_instance():
            try:
                instance = KPIOrchestrationService()
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
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService

        service = KPIOrchestrationService()

        # Alle internen Attribute muessen existieren
        assert hasattr(service, '_initialized')
        assert service._initialized is True
        assert hasattr(service, '_service_lock')
        assert hasattr(service, '_property_service')
        assert hasattr(service, '_vehicle_service')
        assert hasattr(service, '_loan_service')
        assert hasattr(service, '_investment_service')
        assert hasattr(service, '_insurance_service')
        assert hasattr(service, '_financial_health_service')


# =============================================================================
# Dataclass Tests
# =============================================================================

class TestKPIOrchestrationDataClasses:
    """Tests fuer Datenstrukturen mit korrekten Defaults."""

    def test_entity_kpi_result_dataclass(self) -> None:
        """Testet EntityKPIResult mit echten Feldwerten."""
        from app.services.privat.kpi_orchestrator import EntityKPIResult

        entity_id = uuid4()
        result = EntityKPIResult(
            entity_type="property",
            entity_id=entity_id,
            success=True,
            calculated_kpis={
                "gross_yield": 5.2,
                "net_yield": 4.1,
                "estimated_value": 350000.0,
            },
        )

        # Basis-Assertions
        assert result.entity_type == "property"
        assert result.entity_id == entity_id
        assert result.success is True

        # KPI-Werte pruefen
        assert "gross_yield" in result.calculated_kpis
        assert result.calculated_kpis["gross_yield"] == 5.2
        assert result.calculated_kpis["net_yield"] == 4.1

        # Defaults pruefen
        assert result.error is None
        assert isinstance(result.calculated_at, datetime)

    def test_entity_kpi_result_error_case(self) -> None:
        """Testet EntityKPIResult im Fehlerfall."""
        from app.services.privat.kpi_orchestrator import EntityKPIResult

        result = EntityKPIResult(
            entity_type="vehicle",
            entity_id=uuid4(),
            success=False,
            error="Fahrzeugdaten unvollstaendig",
        )

        assert result.success is False
        assert result.error == "Fahrzeugdaten unvollstaendig"
        assert result.calculated_kpis == {}  # Default empty dict

    def test_space_kpi_result_dataclass(self) -> None:
        """Testet SpaceKPIResult mit allen Feldern."""
        from app.services.privat.kpi_orchestrator import (
            SpaceKPIResult,
            EntityKPIResult,
        )

        space_id = uuid4()
        prop_result = EntityKPIResult(
            entity_type="property",
            entity_id=uuid4(),
            success=True,
            calculated_kpis={"yield": 5.0},
        )

        result = SpaceKPIResult(space_id=space_id)
        result.property_results = [prop_result]
        result.financial_health_score = Decimal("75.50")
        result.financial_health_dimensions = {
            "liquidity": Decimal("80"),
            "assets": Decimal("70"),
        }
        result.total_calculated = 1
        result.total_errors = 0

        # Assertions
        assert result.space_id == space_id
        assert len(result.property_results) == 1
        assert result.property_results[0].success is True
        assert result.financial_health_score == Decimal("75.50")
        assert result.financial_health_dimensions["liquidity"] == Decimal("80")

        # Default Listen pruefen
        assert result.vehicle_results == []
        assert result.loan_results == []
        assert result.investment_results == []
        assert result.insurance_results == []

    def test_batch_kpi_result_defaults(self) -> None:
        """Testet BatchKPIResult mit korrekten Defaults (wichtig: errors hat default_factory)."""
        from app.services.privat.kpi_orchestrator import BatchKPIResult

        # Ohne Argumente - alle Defaults
        result = BatchKPIResult()

        assert result.total_spaces == 0
        assert result.spaces_processed == 0
        assert result.spaces_skipped == 0
        assert result.total_entities_calculated == 0
        assert result.total_errors == 0
        assert result.errors == []  # KRITISCH: default_factory=list
        assert result.properties_calculated == 0
        assert result.vehicles_calculated == 0
        assert result.loans_calculated == 0
        assert result.investments_calculated == 0
        assert result.insurances_calculated == 0
        assert result.average_health_score is None
        assert result.duration_seconds == 0.0
        assert isinstance(result.calculated_at, datetime)

    def test_batch_kpi_result_with_values(self) -> None:
        """Testet BatchKPIResult mit gesetzten Werten."""
        from app.services.privat.kpi_orchestrator import BatchKPIResult

        result = BatchKPIResult(
            total_spaces=10,
            spaces_processed=8,
            spaces_skipped=2,
            total_entities_calculated=45,
            properties_calculated=15,
            vehicles_calculated=10,
            loans_calculated=8,
            investments_calculated=7,
            insurances_calculated=5,
            average_health_score=Decimal("72.35"),
            duration_seconds=12.5,
        )
        result.errors.append("Space xyz: Timeout")

        assert result.total_spaces == 10
        assert result.spaces_processed == 8
        assert result.spaces_skipped == 2
        assert result.total_entities_calculated == 45
        assert len(result.errors) == 1
        assert result.errors[0] == "Space xyz: Timeout"
        assert result.average_health_score == Decimal("72.35")


# =============================================================================
# Service Getter Tests (Thread-safe Lazy Loading)
# =============================================================================

class TestKPIOrchestrationServiceGetters:
    """Tests fuer thread-safe Lazy Loading der Sub-Services."""

    def test_service_getters_exist(self) -> None:
        """Testet dass alle Service-Getter existieren."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService

        service = KPIOrchestrationService()

        # Private Getter-Methoden
        assert hasattr(service, '_get_property_service')
        assert hasattr(service, '_get_vehicle_service')
        assert hasattr(service, '_get_loan_service')
        assert hasattr(service, '_get_investment_service')
        assert hasattr(service, '_get_insurance_service')
        assert hasattr(service, '_get_financial_health_service')

    def test_service_getters_are_lazy(self) -> None:
        """Testet dass Services erst bei Bedarf geladen werden (lazy)."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService

        service = KPIOrchestrationService()

        # Vor dem ersten Aufruf sind alle Services None
        assert service._property_service is None
        assert service._vehicle_service is None
        assert service._loan_service is None
        assert service._investment_service is None
        assert service._insurance_service is None
        assert service._financial_health_service is None


# =============================================================================
# API Method Tests
# =============================================================================

class TestKPIOrchestrationAPIMethods:
    """Tests fuer oeffentliche API-Methoden."""

    def test_recalculate_all_for_space_signature(self) -> None:
        """Testet die Signatur von recalculate_all_for_space."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService
        import inspect

        service = KPIOrchestrationService()
        method = service.recalculate_all_for_space
        sig = inspect.signature(method)

        # Parameter pruefen
        params = list(sig.parameters.keys())
        assert 'db' in params
        assert 'space_id' in params
        assert 'include_properties' in params
        assert 'include_vehicles' in params
        assert 'include_loans' in params
        assert 'include_investments' in params
        assert 'include_insurances' in params
        assert 'include_financial_health' in params
        assert 'defer_events' in params  # KRITISCH: Neuer Parameter fuer Event-Ordering

        # Defaults pruefen
        assert sig.parameters['include_properties'].default is True
        assert sig.parameters['defer_events'].default is False

    def test_recalculate_all_spaces_signature(self) -> None:
        """Testet die Signatur von recalculate_all_spaces (Batch-Operation)."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService
        import inspect

        service = KPIOrchestrationService()
        method = service.recalculate_all_spaces
        sig = inspect.signature(method)

        params = list(sig.parameters.keys())
        assert 'db' in params
        assert 'space_ids' in params

        # space_ids ist optional
        assert sig.parameters['space_ids'].default is None

    def test_recalculate_single_entity_signature(self) -> None:
        """Testet die Signatur von recalculate_single_entity."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService
        import inspect

        service = KPIOrchestrationService()
        method = service.recalculate_single_entity
        sig = inspect.signature(method)

        params = list(sig.parameters.keys())
        assert 'db' in params
        assert 'entity_type' in params
        assert 'entity_id' in params
        assert 'recalculate_health' in params

        # recalculate_health ist True by default
        assert sig.parameters['recalculate_health'].default is True


# =============================================================================
# Prometheus Metriken Tests
# =============================================================================

class TestKPIOrchestrationMetrics:
    """Tests fuer Prometheus Metriken."""

    def test_metrics_defined(self) -> None:
        """Testet dass alle Prometheus Metriken korrekt definiert sind."""
        from app.services.privat.kpi_orchestrator import (
            KPI_ORCHESTRATION_RUNS,
            KPI_ORCHESTRATION_DURATION,
            KPI_ENTITIES_PROCESSED,
        )
        from prometheus_client import Counter, Histogram, Gauge

        # Typ-Assertions
        assert isinstance(KPI_ORCHESTRATION_RUNS, Counter)
        assert isinstance(KPI_ORCHESTRATION_DURATION, Histogram)
        assert isinstance(KPI_ENTITIES_PROCESSED, Gauge)

    def test_metrics_labels(self) -> None:
        """Testet dass Metriken die korrekten Labels haben."""
        from app.services.privat.kpi_orchestrator import (
            KPI_ORCHESTRATION_RUNS,
            KPI_ORCHESTRATION_DURATION,
            KPI_ENTITIES_PROCESSED,
        )

        # Counter hat operation_type und status Labels
        assert 'operation_type' in KPI_ORCHESTRATION_RUNS._labelnames
        assert 'status' in KPI_ORCHESTRATION_RUNS._labelnames

        # Histogram hat operation_type Label
        assert 'operation_type' in KPI_ORCHESTRATION_DURATION._labelnames

        # Gauge hat entity_type Label
        assert 'entity_type' in KPI_ENTITIES_PROCESSED._labelnames


# =============================================================================
# Event Publishing Tests
# =============================================================================

class TestKPIOrchestrationEvents:
    """Tests fuer Event-Publishing."""

    def test_event_types_available(self) -> None:
        """Testet dass alle benoetigten EventTypes verfuegbar sind."""
        from app.services.events.event_bus import EventType

        # Diese Events werden vom KPI Orchestrator verwendet
        assert hasattr(EventType, 'SYSTEM_KPI_RECALCULATION')
        assert EventType.SYSTEM_KPI_RECALCULATION.value == "system.kpi_recalculation"

    def test_defer_events_parameter_exists(self) -> None:
        """Testet dass defer_events Parameter existiert (Event-Ordering Fix)."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService
        import inspect

        service = KPIOrchestrationService()
        sig = inspect.signature(service.recalculate_all_for_space)

        # defer_events muss existieren
        assert 'defer_events' in sig.parameters

        # Default ist False (Events werden sofort publiziert)
        assert sig.parameters['defer_events'].default is False


# =============================================================================
# Internal Method Tests
# =============================================================================

class TestKPIOrchestrationInternalMethods:
    """Tests fuer interne Methoden."""

    def test_calculate_methods_exist(self) -> None:
        """Testet dass alle internen _calculate_* Methoden existieren."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService

        service = KPIOrchestrationService()

        # Alle _calculate Methoden
        assert hasattr(service, '_calculate_property_kpis')
        assert hasattr(service, '_calculate_vehicle_kpis')
        assert hasattr(service, '_calculate_loan_kpis')
        assert hasattr(service, '_calculate_investment_kpis')
        assert hasattr(service, '_calculate_insurance_kpis')
        assert hasattr(service, '_calculate_financial_health')

        # Alle sind callable
        assert callable(service._calculate_property_kpis)
        assert callable(service._calculate_vehicle_kpis)
        assert callable(service._calculate_loan_kpis)
        assert callable(service._calculate_investment_kpis)
        assert callable(service._calculate_insurance_kpis)
        assert callable(service._calculate_financial_health)

    def test_publish_events_method_exists(self) -> None:
        """Testet dass Event-Publishing Methode existiert."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService

        service = KPIOrchestrationService()

        assert hasattr(service, '_publish_recalculation_events')
        assert callable(service._publish_recalculation_events)

    def test_get_space_id_for_entity_exists(self) -> None:
        """Testet dass Helper-Methode existiert."""
        from app.services.privat.kpi_orchestrator import KPIOrchestrationService

        service = KPIOrchestrationService()

        assert hasattr(service, '_get_space_id_for_entity')
        assert callable(service._get_space_id_for_entity)
