# -*- coding: utf-8 -*-
"""Unit Tests fuer SupplierPerformanceService.

Tests:
- get_performance() - Erfolgsfall mit Top-5 Ranking
- get_performance() - Keine Lieferanten
- get_widget_data() - Widget-Format
- _calculate_supplier_metrics() - Puenktlichkeits-Berechnung
- Kritische Lieferanten (punctuality < 70%)
- Preistrend UP (>2% Aenderung)
- Preistrend STABLE (-2% bis 2%)
- DB-Fehler Resilienz
"""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from app.services.dashboard.supplier_performance_service import (
    SupplierPerformanceService,
    SupplierPerformanceResult,
    SupplierMetrics,
    TrendDirection,
    get_supplier_performance_service,
)
from app.db.models import BusinessEntity, InvoiceTracking

pytestmark = [pytest.mark.unit]

# Test-Konstanten
TEST_USER_UUID = UUID("12345678-1234-5678-1234-567812345678")
TEST_COMPANY_UUID = UUID("87654321-4321-8765-4321-876543218765")


@pytest.fixture
def service() -> SupplierPerformanceService:
    """SupplierPerformanceService Fixture."""
    return SupplierPerformanceService()


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock AsyncSession."""
    return AsyncMock()


class TestGetPerformance:
    """Tests fuer get_performance()."""

    @pytest.mark.asyncio
    async def test_get_performance_success(self, service, mock_db):
        """Erfolgreiche Performance-Berechnung mit Top-5 Ranking."""
        # Mock Suppliers
        supplier1 = MagicMock(spec=BusinessEntity)
        supplier1.id = uuid4()
        supplier1.name = "Lieferant A"

        supplier2 = MagicMock(spec=BusinessEntity)
        supplier2.id = uuid4()
        supplier2.name = "Lieferant B"

        supplier3 = MagicMock(spec=BusinessEntity)
        supplier3.id = uuid4()
        supplier3.name = "Lieferant C"

        # Mock Metrics
        metrics1 = SupplierMetrics(
            entity_id=str(supplier1.id),
            entity_name="Lieferant A",
            punctuality_score=95.0,
            accuracy_score=98.0,
            total_orders=50,
            total_volume=Decimal("10000.00"),
        )

        metrics2 = SupplierMetrics(
            entity_id=str(supplier2.id),
            entity_name="Lieferant B",
            punctuality_score=85.0,
            accuracy_score=90.0,
            total_orders=30,
            total_volume=Decimal("5000.00"),
        )

        metrics3 = SupplierMetrics(
            entity_id=str(supplier3.id),
            entity_name="Lieferant C",
            punctuality_score=75.0,
            accuracy_score=88.0,
            total_orders=20,
            total_volume=Decimal("3000.00"),
        )

        # Patch Methods
        with patch.object(
            service,
            "_get_suppliers",
            return_value=[supplier1, supplier2, supplier3],
        ), patch.object(
            service,
            "_calculate_supplier_metrics",
            side_effect=[metrics1, metrics2, metrics3],
        ), patch.object(
            service,
            "_calculate_price_trend",
            return_value=[],
        ):
            result = await service.get_performance(
                mock_db,
                TEST_USER_UUID,
                TEST_COMPANY_UUID,
                period_days=90,
            )

        # Assertions
        assert isinstance(result, SupplierPerformanceResult)
        assert result.period_days == 90
        assert result.total_suppliers == 3
        assert result.active_suppliers == 3

        # Overall Metrics (Durchschnitt)
        expected_punctuality = (95.0 + 85.0 + 75.0) / 3
        expected_accuracy = (98.0 + 90.0 + 88.0) / 3
        assert result.overall_punctuality == pytest.approx(expected_punctuality, rel=0.01)
        assert result.overall_accuracy == pytest.approx(expected_accuracy, rel=0.01)

        # Top 5 - sortiert nach kombiniertem Score
        assert len(result.top_suppliers) == 3
        assert result.top_suppliers[0].entity_name == "Lieferant A"  # 96.5%
        assert result.top_suppliers[1].entity_name == "Lieferant B"  # 87.5%
        assert result.top_suppliers[2].entity_name == "Lieferant C"  # 81.5%

    @pytest.mark.asyncio
    async def test_get_performance_no_suppliers(self, service, mock_db):
        """Keine Lieferanten -> Nullwerte."""
        with patch.object(
            service,
            "_get_suppliers",
            return_value=[],
        ), patch.object(
            service,
            "_calculate_price_trend",
            return_value=[],
        ):
            result = await service.get_performance(
                mock_db,
                TEST_USER_UUID,
                TEST_COMPANY_UUID,
                period_days=30,
            )

        assert result.total_suppliers == 0
        assert result.active_suppliers == 0
        assert result.overall_punctuality == 0.0
        assert result.overall_accuracy == 0.0
        assert len(result.top_suppliers) == 0


class TestGetWidgetData:
    """Tests fuer get_widget_data()."""

    @pytest.mark.asyncio
    async def test_get_widget_data(self, service, mock_db):
        """Widget-Dict Format verifizieren."""
        # Mock Performance Result
        mock_result = SupplierPerformanceResult(
            generated_at=datetime(2026, 2, 10, 12, 0, 0),
            period_days=90,
            overall_punctuality=88.5,
            overall_accuracy=92.3,
            total_suppliers=10,
            active_suppliers=8,
            avg_price_change=2.5,
            top_suppliers=[
                SupplierMetrics(
                    entity_id="uuid-1",
                    entity_name="Top Lieferant",
                    punctuality_score=95.0,
                    accuracy_score=98.0,
                    total_orders=100,
                    total_volume=Decimal("25000.50"),
                    avg_price_trend=3.2,
                    trend_direction=TrendDirection.UP,
                )
            ],
            price_trend_data=[],
            critical_suppliers=[],
        )

        with patch.object(
            service,
            "get_performance",
            return_value=mock_result,
        ):
            widget_data = await service.get_widget_data(
                mock_db,
                TEST_USER_UUID,
                TEST_COMPANY_UUID,
                period_days=90,
            )

        # Assertions
        assert isinstance(widget_data, Dict)
        assert widget_data["generatedAt"] == "2026-02-10T12:00:00"
        assert widget_data["periodDays"] == 90
        assert widget_data["overallPunctuality"] == 88.5
        assert widget_data["overallAccuracy"] == 92.3
        assert widget_data["totalSuppliers"] == 10
        assert widget_data["activeSuppliers"] == 8
        assert widget_data["avgPriceChange"] == 2.5
        assert widget_data["criticalCount"] == 0

        # Top Suppliers Format
        assert len(widget_data["topSuppliers"]) == 1
        top = widget_data["topSuppliers"][0]
        assert top["id"] == "uuid-1"
        assert top["name"] == "Top Lieferant"
        assert top["punctuality"] == 95.0
        assert top["accuracy"] == 98.0
        assert top["orders"] == 100
        assert top["volume"] == 25000.50
        assert top["priceTrend"] == 3.2
        assert top["trendDirection"] == "up"


class TestPunctualityCalculation:
    """Tests fuer Puenktlichkeits-Berechnung."""

    @pytest.mark.asyncio
    async def test_punctuality_calculation(self, service, mock_db):
        """Puenktlichkeit via _calculate_supplier_metrics testen."""
        # Mock Supplier
        supplier = MagicMock(spec=BusinessEntity)
        supplier.id = uuid4()
        supplier.name = "Test Lieferant"

        # Mock Invoices: 3 on-time, 1 late
        cutoff = date.today() - timedelta(days=90)

        invoice1 = MagicMock(spec=InvoiceTracking)
        invoice1.due_date = date.today() - timedelta(days=5)
        invoice1.paid_at = datetime.now() - timedelta(days=6)  # On-time
        invoice1.amount = Decimal("1000.00")
        invoice1.created_at = datetime.now()

        invoice2 = MagicMock(spec=InvoiceTracking)
        invoice2.due_date = date.today() - timedelta(days=10)
        invoice2.paid_at = datetime.now() - timedelta(days=3)  # Late
        invoice2.amount = Decimal("2000.00")
        invoice2.created_at = datetime.now()

        invoice3 = MagicMock(spec=InvoiceTracking)
        invoice3.due_date = date.today() - timedelta(days=20)
        invoice3.paid_at = datetime.now() - timedelta(days=21)  # On-time
        invoice3.amount = Decimal("1500.00")
        invoice3.created_at = datetime.now()

        invoice4 = MagicMock(spec=InvoiceTracking)
        invoice4.due_date = date.today() - timedelta(days=30)
        invoice4.paid_at = datetime.now() - timedelta(days=31)  # On-time
        invoice4.amount = Decimal("3000.00")
        invoice4.created_at = datetime.now()

        # Mock DB Query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            invoice1,
            invoice2,
            invoice3,
            invoice4,
        ]
        mock_db.execute.return_value = mock_result

        # Echte Modell-Spalten (entity_id existiert, Richtung via
        # Entity-JOIN) - keine Phantom-Attribut-Patches mehr noetig.
        metrics = await service._calculate_supplier_metrics(
            mock_db,
            supplier,
            cutoff,
            TEST_COMPANY_UUID,
        )

        # Assertions: 3 on-time, 1 late -> 75%
        assert metrics.total_orders == 4
        assert metrics.on_time_deliveries == 3
        assert metrics.late_deliveries == 1
        assert metrics.punctuality_score == pytest.approx(75.0, rel=0.01)


class TestCriticalSuppliers:
    """Tests fuer kritische Lieferanten."""

    @pytest.mark.asyncio
    async def test_critical_suppliers(self, service, mock_db):
        """Lieferant mit punctuality < 70% in critical_suppliers."""
        # Mock Supplier
        supplier1 = MagicMock(spec=BusinessEntity)
        supplier1.id = uuid4()
        supplier1.name = "Kritischer Lieferant"

        supplier2 = MagicMock(spec=BusinessEntity)
        supplier2.id = uuid4()
        supplier2.name = "Guter Lieferant"

        # Mock Metrics
        critical_metrics = SupplierMetrics(
            entity_id=str(supplier1.id),
            entity_name="Kritischer Lieferant",
            punctuality_score=65.0,  # < 70% -> kritisch
            accuracy_score=85.0,
            total_orders=20,
        )

        good_metrics = SupplierMetrics(
            entity_id=str(supplier2.id),
            entity_name="Guter Lieferant",
            punctuality_score=90.0,
            accuracy_score=95.0,
            total_orders=30,
        )

        with patch.object(
            service,
            "_get_suppliers",
            return_value=[supplier1, supplier2],
        ), patch.object(
            service,
            "_calculate_supplier_metrics",
            side_effect=[critical_metrics, good_metrics],
        ), patch.object(
            service,
            "_calculate_price_trend",
            return_value=[],
        ):
            result = await service.get_performance(
                mock_db,
                TEST_USER_UUID,
                TEST_COMPANY_UUID,
                period_days=90,
            )

        # Assertions
        assert len(result.critical_suppliers) == 1
        assert result.critical_suppliers[0].entity_name == "Kritischer Lieferant"
        assert result.critical_suppliers[0].punctuality_score == 65.0


class TestPriceTrend:
    """Tests fuer Preistrend-Berechnung."""

    @pytest.mark.asyncio
    async def test_price_trend_up(self, service, mock_db):
        """Preistrend UP bei >2% Aenderung."""
        # Mock Supplier
        supplier = MagicMock(spec=BusinessEntity)
        supplier.id = uuid4()
        supplier.name = "Teurer Lieferant"

        cutoff = date.today() - timedelta(days=90)

        # Mock Invoices: Erste Haelfte billig, zweite Haelfte teuer
        invoices = []
        base_time = datetime.now() - timedelta(days=60)

        # Erste Haelfte: 1000 EUR
        for i in range(3):
            inv = MagicMock(spec=InvoiceTracking)
            inv.due_date = date.today()
            inv.paid_at = datetime.now()
            inv.amount = Decimal("1000.00")
            inv.created_at = base_time + timedelta(days=i * 5)
            invoices.append(inv)

        # Zweite Haelfte: 1500 EUR (+50% -> >2%)
        for i in range(3):
            inv = MagicMock(spec=InvoiceTracking)
            inv.due_date = date.today()
            inv.paid_at = datetime.now()
            inv.amount = Decimal("1500.00")
            inv.created_at = base_time + timedelta(days=30 + i * 5)
            invoices.append(inv)

        # Mock DB
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = invoices
        mock_db.execute.return_value = mock_result

        # Echte Modell-Spalten (entity_id existiert, Richtung via
        # Entity-JOIN) - keine Phantom-Attribut-Patches mehr noetig.
        metrics = await service._calculate_supplier_metrics(
            mock_db,
            supplier,
            cutoff,
            TEST_COMPANY_UUID,
        )

        # Assertions
        assert metrics.trend_direction == TrendDirection.UP
        assert metrics.avg_price_trend > 2.0  # 50% Anstieg

    @pytest.mark.asyncio
    async def test_price_trend_stable(self, service, mock_db):
        """Preistrend STABLE bei -2% bis 2% Aenderung."""
        # Mock Supplier
        supplier = MagicMock(spec=BusinessEntity)
        supplier.id = uuid4()
        supplier.name = "Stabiler Lieferant"

        cutoff = date.today() - timedelta(days=90)

        # Mock Invoices: Gleichbleibende Preise
        invoices = []
        base_time = datetime.now() - timedelta(days=60)

        for i in range(6):
            inv = MagicMock(spec=InvoiceTracking)
            inv.due_date = date.today()
            inv.paid_at = datetime.now()
            inv.amount = Decimal("1000.00")
            inv.created_at = base_time + timedelta(days=i * 5)
            invoices.append(inv)

        # Mock DB
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = invoices
        mock_db.execute.return_value = mock_result

        # Echte Modell-Spalten (entity_id existiert, Richtung via
        # Entity-JOIN) - keine Phantom-Attribut-Patches mehr noetig.
        metrics = await service._calculate_supplier_metrics(
            mock_db,
            supplier,
            cutoff,
            TEST_COMPANY_UUID,
        )

        # Assertions
        assert metrics.trend_direction == TrendDirection.STABLE
        assert -2.0 <= metrics.avg_price_trend <= 2.0


class TestErrorResilience:
    """Tests fuer Fehlerbehandlung."""

    @pytest.mark.asyncio
    async def test_db_error_resilience(self, service, mock_db):
        """DB-Fehler bei _get_suppliers -> Graceful Handling."""
        # Mock DB Error
        with patch.object(
            service,
            "_get_suppliers",
            side_effect=Exception("DB Connection Lost"),
        ):
            with pytest.raises(Exception) as exc_info:
                await service.get_performance(
                    mock_db,
                    TEST_USER_UUID,
                    TEST_COMPANY_UUID,
                    period_days=90,
                )

            assert "DB Connection Lost" in str(exc_info.value)


class TestSingleton:
    """Tests fuer Singleton-Factory."""

    def test_get_supplier_performance_service(self):
        """get_supplier_performance_service liefert Singleton."""
        service1 = get_supplier_performance_service()
        service2 = get_supplier_performance_service()

        assert isinstance(service1, SupplierPerformanceService)
        assert service1 is service2  # Same instance
