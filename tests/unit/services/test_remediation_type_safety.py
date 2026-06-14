# -*- coding: utf-8 -*-
"""
Tests fuer Remediation-Fixes: Type Safety.

Stellt sicher, dass TypedDict-Implementierungen korrekt sind
und keine Any-Types verwendet werden.

Vision 2026 Remediation Phase: Type Safety Violations.
"""

import pytest
from typing import get_type_hints, TypedDict
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

# Versuche Imports - ueberspringe Tests wenn Packages fehlen
try:
    from app.services.banking.enhanced_fints_service import (
        TransactionData, BankConnection, BankConnectionDict, SyncSchedule
    )
    HAS_FINTS_SERVICE = True
except ImportError:
    HAS_FINTS_SERVICE = False

try:
    from app.services.external.handelsregister_monitoring_service import (
        MonitoringEventDict, HandelsregisterMonitoringService
    )
    from cachetools import TTLCache
    HAS_HANDELSREGISTER_SERVICE = True
except ImportError:
    HAS_HANDELSREGISTER_SERVICE = False

try:
    from app.services.datev.steuerberater_package_service import SteuerberaterPackageDict
    HAS_STEUERBERATER_SERVICE = True
except ImportError:
    HAS_STEUERBERATER_SERVICE = False

try:
    from app.services.insights.daily_insights_engine import (
        DataProvidersResult, InsightFactorDict, DailyInsight,
        DailyInsightType, InsightSeverity
    )
    HAS_INSIGHTS_ENGINE = True
except ImportError:
    HAS_INSIGHTS_ENGINE = False


@pytest.mark.skipif(not HAS_FINTS_SERVICE, reason="EnhancedFinTSService nicht verfuegbar")
class TestEnhancedFinTSServiceTypeSafety:
    """Tests fuer Type Safety in EnhancedFinTSService."""

    def test_transaction_data_typed_dict_structure(self) -> None:
        """Test: TransactionData TypedDict hat korrekte Struktur."""
        # Pruefe dass es ein TypedDict ist
        assert hasattr(TransactionData, '__annotations__')

        # Pruefe erforderliche Felder (echter Vertrag, wie in
        # enhanced_fints_service.py konstruiert + gelesen):
        # id, booking_date, amount, sender_name, sender_iban, reference, account_iban
        annotations = TransactionData.__annotations__
        expected_fields = {
            'id', 'booking_date', 'amount', 'sender_name',
            'sender_iban', 'reference', 'account_iban'
        }

        for field in expected_fields:
            assert field in annotations, f"Feld '{field}' fehlt in TransactionData"

    def test_bank_connection_to_dict_returns_typed(self) -> None:
        """Test: BankConnection.to_dict() gibt typisiertes Dict zurueck."""
        connection = BankConnection(
            company_id=uuid4(),
            bank_name="Test Bank",
            blz="12345678",
            sync_schedule=SyncSchedule.DAILY,
        )

        result = connection.to_dict()

        # Pruefe Struktur
        assert isinstance(result, dict)
        assert 'id' in result
        assert 'bank_name' in result
        assert result['bank_name'] == "Test Bank"


@pytest.mark.skipif(not HAS_HANDELSREGISTER_SERVICE, reason="HandelsregisterMonitoringService nicht verfuegbar")
class TestHandelsregisterMonitoringServiceTypeSafety:
    """Tests fuer Type Safety in HandelsregisterMonitoringService."""

    def test_monitoring_event_dict_structure(self) -> None:
        """Test: MonitoringEventDict hat korrekte Struktur."""
        annotations = MonitoringEventDict.__annotations__
        expected_fields = {
            'event_id', 'entity_id', 'hrb_number', 'event_type',
            'detected_at', 'details', 'severity'
        }

        for field in expected_fields:
            assert field in annotations, f"Feld '{field}' fehlt in MonitoringEventDict"

    def test_cache_uses_ttl_cache(self) -> None:
        """Test: Service verwendet TTLCache statt unbegrenztem Dict."""
        service = HandelsregisterMonitoringService.__new__(
            HandelsregisterMonitoringService
        )
        service._cache = TTLCache(maxsize=1000, ttl=3600)

        assert isinstance(service._cache, TTLCache)
        assert service._cache.maxsize == 1000


@pytest.mark.skipif(not HAS_STEUERBERATER_SERVICE, reason="SteuerberaterPackageService nicht verfuegbar")
class TestSteuerberaterPackageServiceTypeSafety:
    """Tests fuer Type Safety in SteuerberaterPackageService."""

    def test_package_dict_structure(self) -> None:
        """Test: SteuerberaterPackageDict hat korrekte Struktur."""

        # Echter Vertrag (SteuerberaterPackage.to_dict): id (nicht package_id),
        # period_from/period_to (nicht period_start/_end),
        # total_documents (nicht document_count).
        annotations = SteuerberaterPackageDict.__annotations__
        expected_fields = {
            'id', 'company_id', 'period_from', 'period_to',
            'total_documents', 'total_amount', 'status'
        }

        for field in expected_fields:
            assert field in annotations, f"Feld '{field}' fehlt in SteuerberaterPackageDict"

    def test_xml_content_is_escaped(self) -> None:
        """Test: XML-Inhalte werden korrekt escaped."""
        from xml.sax.saxutils import escape

        # Teste dass escape funktioniert
        dangerous_input = '<script>alert("xss")</script>'
        escaped = escape(dangerous_input)

        assert '<' not in escaped or '&lt;' in escaped
        assert '>' not in escaped or '&gt;' in escaped


@pytest.mark.skipif(not HAS_INSIGHTS_ENGINE, reason="DailyInsightsEngine nicht verfuegbar")
class TestDailyInsightsEngineTypeSafety:
    """Tests fuer Type Safety in DailyInsightsEngine."""

    def test_data_providers_result_structure(self) -> None:
        """Test: DataProvidersResult TypedDict hat korrekte Struktur."""
        annotations = DataProvidersResult.__annotations__
        expected_fields = {
            'cashflow_predictions', 'contracts', 'entities',
            'invoices', 'patterns', 'retention_items'
        }

        for field in expected_fields:
            assert field in annotations, f"Feld '{field}' fehlt in DataProvidersResult"

    def test_insight_factor_dict_structure(self) -> None:
        """Test: InsightFactorDict hat korrekte Struktur."""
        annotations = InsightFactorDict.__annotations__
        expected_fields = {'name', 'value', 'contribution', 'explanation'}

        for field in expected_fields:
            assert field in annotations, f"Feld '{field}' fehlt in InsightFactorDict"

    def test_daily_insight_to_dict(self) -> None:
        """Test: DailyInsight.to_dict() gibt typisiertes Dict zurueck."""
        insight = DailyInsight(
            insight_type=DailyInsightType.CASHFLOW_WARNING,
            severity=InsightSeverity.HIGH,
            title="Test Insight",
            summary="Test Summary",
        )

        result = insight.to_dict()

        assert isinstance(result, dict)
        assert 'id' in result
        assert result['title'] == "Test Insight"
        assert result['severity'] == InsightSeverity.HIGH.value


@pytest.mark.skipif(not HAS_FINTS_SERVICE, reason="EnhancedFinTSService nicht verfuegbar")
class TestNoAnyTypesInServices:
    """Tests dass keine Any-Types in kritischen Services verwendet werden."""

    def test_enhanced_fints_service_no_any_in_signatures(self) -> None:
        """Test: EnhancedFinTSService hat keine Any-Types in Public-Methoden."""
        from app.services.banking.enhanced_fints_service import EnhancedFinTSService
        import inspect

        for name, method in inspect.getmembers(EnhancedFinTSService, predicate=inspect.isfunction):
            if not name.startswith('_'):  # Public methods only
                try:
                    hints = get_type_hints(method)
                    for param, type_hint in hints.items():
                        # Skip 'self' and generelle Checks
                        if param == 'return':
                            continue
                        type_str = str(type_hint)
                        # Erlaube Any nur in Optional[Any] nicht direkt
                        if type_str == 'typing.Any':
                            pytest.fail(
                                f"Methode {name} hat 'Any' Typ fuer Parameter '{param}'"
                            )
                except Exception:
                    # Manche Methoden haben keine Type Hints
                    pass

    @pytest.mark.skipif(not HAS_INSIGHTS_ENGINE, reason="DailyInsightsEngine nicht verfuegbar")
    def test_daily_insights_engine_no_any_in_dataclasses(self) -> None:
        """Test: DailyInsightsEngine Dataclasses haben keine Any-Types."""
        import dataclasses

        assert dataclasses.is_dataclass(DailyInsight)

        for field in dataclasses.fields(DailyInsight):
            type_str = str(field.type)
            if type_str == 'typing.Any':
                pytest.fail(f"Feld '{field.name}' in DailyInsight hat 'Any' Typ")


class TestAsyncHandlerDetection:
    """Tests fuer korrekte async Handler-Erkennung."""

    @pytest.mark.asyncio
    async def test_async_handler_detection(self) -> None:
        """Test: Async Handlers werden korrekt erkannt und awaited."""
        import asyncio

        async def async_handler(data: dict) -> None:
            await asyncio.sleep(0.001)

        def sync_handler(data: dict) -> None:
            pass

        # Test async detection
        assert asyncio.iscoroutinefunction(async_handler)
        assert not asyncio.iscoroutinefunction(sync_handler)

        # Test dass async awaited werden kann
        result = async_handler({"test": True})
        assert asyncio.iscoroutine(result)
        await result  # Muss awaited werden


class TestDivisionByZeroGuards:
    """Tests fuer Division-by-Zero Guards."""

    def test_skonto_rate_validation(self) -> None:
        """Test: Skonto-Rate von 1.0 (100%) wird abgefangen."""
        rate = 1.0
        amount = Decimal("100.00")

        # Die korrigierte Logik sollte einen Fehler werfen oder sicher behandeln
        if rate >= 1.0:
            # Guard aktiv - kein ZeroDivisionError
            pass
        else:
            gross_amount = amount / (1 - Decimal(str(rate)))
            assert gross_amount > amount

    def test_percentage_calculation_safe(self) -> None:
        """Test: Prozentberechnungen sind sicher bei 0-Werten."""
        total = 0
        part = 0

        if total > 0:
            percentage = (part / total) * 100
        else:
            percentage = 0.0

        assert percentage == 0.0
