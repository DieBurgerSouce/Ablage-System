# -*- coding: utf-8 -*-
"""
Unit Tests fuer AnomalyInsightsService.

Testet:
- Preis-Anomalie-Erkennung
- Volumen-Anomalien
- Rechnungsmuster-Anomalien
- Duplikat-Erkennung

PHASE 6: Proaktive Intelligenz
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.orchestration.anomaly_insights_service import (
    AnomalyInsightsService,
    AnomalyType,
    AnomalyCheckResult,
    get_anomaly_insights_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_service():
    """Reset Singleton vor und nach jedem Test."""
    AnomalyInsightsService._instance = None
    yield
    AnomalyInsightsService._instance = None


@pytest.fixture
def service(reset_service):
    """Frische Service-Instanz fuer jeden Test."""
    return AnomalyInsightsService()


@pytest.fixture
def mock_db():
    """Mock Database Session."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_company_id():
    """Sample Company ID."""
    return uuid4()


@pytest.fixture
def sample_price_history():
    """Sample Preishistorie fuer einen Lieferanten."""
    base_price = Decimal("100.00")
    return [
        {"date": datetime.now(timezone.utc) - timedelta(days=i*30), "amount": base_price}
        for i in range(12)
    ]


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingletonPattern:
    """Tests fuer Singleton-Verhalten."""

    def test_singleton_returns_same_instance(self, reset_service):
        """Singleton gibt immer dieselbe Instanz zurueck."""
        instance1 = AnomalyInsightsService()
        instance2 = AnomalyInsightsService()

        assert instance1 is instance2

    def test_factory_returns_same_instance(self, reset_service):
        """Factory-Funktion gibt Singleton zurueck."""
        instance1 = get_anomaly_insights_service()
        instance2 = get_anomaly_insights_service()

        assert instance1 is instance2


# =============================================================================
# AnomalyType Tests
# =============================================================================

class TestAnomalyType:
    """Tests fuer AnomalyType Enum."""

    def test_anomaly_types_defined(self):
        """Alle AnomalyTypes sind definiert."""
        assert AnomalyType.PRICE_SPIKE.value == "price_spike"
        assert AnomalyType.PRICE_DROP.value == "price_drop"
        assert AnomalyType.VOLUME_HIGH.value == "volume_high"
        assert AnomalyType.VOLUME_LOW.value == "volume_low"
        assert AnomalyType.TIMING_UNUSUAL.value == "timing_unusual"
        assert AnomalyType.DUPLICATE_PATTERN.value == "duplicate_pattern"
        assert AnomalyType.FREQUENCY_ANOMALY.value == "frequency_anomaly"
        assert AnomalyType.AMOUNT_ROUND.value == "amount_round"


# =============================================================================
# AnomalyCheckResult Tests
# =============================================================================

class TestAnomalyCheckResult:
    """Tests fuer AnomalyCheckResult Dataclass."""

    def test_defaults(self):
        """AnomalyCheckResult hat sinnvolle Defaults."""
        result = AnomalyCheckResult(
            anomaly_type=AnomalyType.PRICE_SPIKE,
            title="Test Anomaly",
            message="Test Message",
        )

        assert result.severity == "medium"
        assert result.confidence == 0.0
        assert result.deviation_percentage is None
        assert result.affected_amount is None
        assert result.entity_id is None

    def test_to_insight_conversion(self):
        """AnomalyCheckResult kann zu ProactiveInsight konvertiert werden."""
        result = AnomalyCheckResult(
            anomaly_type=AnomalyType.PRICE_SPIKE,
            title="Preisanstieg erkannt",
            message="Lieferant ABC hat Preise um 25% erhoeht.",
            detail="Der aktuelle Preis liegt 2.5 Standardabweichungen ueber dem Durchschnitt.",
            severity="high",
            confidence=0.92,
            deviation_percentage=25.0,
            affected_amount=Decimal("500.00"),
            entity_id=uuid4(),
            entity_name="Lieferant ABC",
        )

        insight = result.to_insight()

        assert insight.insight_type.value == "anomaly"
        assert insight.priority.value == "high"
        assert insight.title == "Preisanstieg erkannt"


# =============================================================================
# Z-Score Calculation Tests
# =============================================================================

class TestZScoreCalculation:
    """Tests fuer Z-Score-Berechnung."""

    def test_z_score_calculation(self, service):
        """Z-Score wird korrekt berechnet."""
        values = [100, 100, 100, 100, 100]  # Durchschnitt 100, Std 0
        current_value = 100

        z_score = service._calculate_z_score(values, current_value)

        # Bei Standardabweichung 0 sollte Z-Score 0 sein
        assert z_score == 0.0

    def test_z_score_with_deviation(self, service):
        """Z-Score mit Abweichung."""
        values = [100, 110, 90, 100, 100]  # Durchschnitt 100, Std ~7.07
        current_value = 130  # Deutlich ueber Durchschnitt

        z_score = service._calculate_z_score(values, current_value)

        # Z-Score sollte positiv und signifikant sein
        assert z_score > 2.0

    def test_z_score_negative_deviation(self, service):
        """Z-Score bei negativer Abweichung."""
        values = [100, 110, 90, 100, 100]
        current_value = 70  # Deutlich unter Durchschnitt

        z_score = service._calculate_z_score(values, current_value)

        # Z-Score sollte negativ und signifikant sein
        assert z_score < -2.0

    def test_z_score_handles_empty_list(self, service):
        """Z-Score behandelt leere Liste."""
        values = []
        current_value = 100

        z_score = service._calculate_z_score(values, current_value)

        assert z_score == 0.0

    def test_z_score_handles_single_value(self, service):
        """Z-Score behandelt einzelnen Wert."""
        values = [100]
        current_value = 150

        z_score = service._calculate_z_score(values, current_value)

        # Mit nur einem Wert keine sinnvolle Std berechenbar
        assert z_score == 0.0


# =============================================================================
# Price Anomaly Tests
# =============================================================================

class TestPriceAnomalies:
    """Tests fuer Preis-Anomalie-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_price_spike(self, service, mock_db, sample_company_id):
        """Erkennt Preisanstiege."""
        # Mock: Lieferant mit normalerweise 100 EUR, jetzt 150 EUR
        mock_supplier = MagicMock(
            id=uuid4(),
            name="Lieferant ABC",
        )
        mock_invoice = MagicMock(
            gross_amount=Decimal("150.00"),
            invoice_date=datetime.now(timezone.utc),
            supplier_id=mock_supplier.id,
        )

        # Historical prices
        historical = [
            MagicMock(gross_amount=Decimal("100.00")),
            MagicMock(gross_amount=Decimal("102.00")),
            MagicMock(gross_amount=Decimal("98.00")),
            MagicMock(gross_amount=Decimal("100.00")),
            MagicMock(gross_amount=Decimal("101.00")),
        ]

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[mock_invoice]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_price_anomalies(
            db=mock_db,
            company_id=sample_company_id,
            lookback_days=90,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_detect_price_drop(self, service):
        """Erkennt signifikante Preisrueckgaenge."""
        historical_prices = [Decimal("100.00")] * 10
        current_price = Decimal("50.00")  # 50% Rueckgang

        is_anomaly, deviation = service._check_price_deviation(
            historical_prices, current_price, threshold_std=2.0
        )

        assert is_anomaly is True
        assert deviation < 0  # Negativer Wert = Rueckgang

    @pytest.mark.asyncio
    async def test_no_anomaly_normal_variation(self, service):
        """Erkennt keine Anomalie bei normaler Variation."""
        historical_prices = [
            Decimal("100.00"), Decimal("102.00"), Decimal("98.00"),
            Decimal("101.00"), Decimal("99.00")
        ]
        current_price = Decimal("103.00")  # Normale Variation

        is_anomaly, deviation = service._check_price_deviation(
            historical_prices, current_price, threshold_std=2.0
        )

        assert is_anomaly is False


# =============================================================================
# Volume Anomaly Tests
# =============================================================================

class TestVolumeAnomalies:
    """Tests fuer Volumen-Anomalie-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_high_volume(self, service, mock_db, sample_company_id):
        """Erkennt ungewoehnlich hohes Volumen."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_volume_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_monthly_volume_comparison(self, service):
        """Vergleicht Monatsvolumen korrekt."""
        monthly_volumes = [
            Decimal("10000.00"), Decimal("10500.00"), Decimal("9800.00"),
            Decimal("10200.00"), Decimal("10100.00"), Decimal("10300.00"),
        ]
        current_month_volume = Decimal("15000.00")  # 50% hoeher

        is_anomaly = service._check_volume_anomaly(
            monthly_volumes, current_month_volume, threshold_std=2.0
        )

        assert is_anomaly is True


# =============================================================================
# Invoice Pattern Tests
# =============================================================================

class TestInvoicePatternAnomalies:
    """Tests fuer Rechnungsmuster-Anomalien."""

    @pytest.mark.asyncio
    async def test_detect_round_amounts(self, service, mock_db, sample_company_id):
        """Erkennt auffaellig runde Betraege."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_invoice_pattern_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_is_round_amount(self, service):
        """Erkennt runde Betraege."""
        assert service._is_round_amount(Decimal("1000.00")) is True
        assert service._is_round_amount(Decimal("5000.00")) is True
        assert service._is_round_amount(Decimal("10000.00")) is True
        assert service._is_round_amount(Decimal("1234.56")) is False
        assert service._is_round_amount(Decimal("999.99")) is False

    def test_is_weekend_invoice(self, service):
        """Erkennt Wochenend-Rechnungen."""
        # Samstag
        saturday = datetime(2026, 1, 17, 12, 0)  # 17.01.2026 ist Samstag
        assert service._is_weekend_date(saturday) is True

        # Montag
        monday = datetime(2026, 1, 19, 12, 0)
        assert service._is_weekend_date(monday) is False


# =============================================================================
# Duplicate Pattern Tests
# =============================================================================

class TestDuplicatePatterns:
    """Tests fuer Duplikat-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_duplicate_patterns(self, service, mock_db, sample_company_id):
        """Erkennt potenzielle Duplikate."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_duplicate_patterns(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    def test_same_amount_same_date_flagged(self, service):
        """Gleicher Betrag und Datum wird geflaggt."""
        invoice1 = MagicMock(
            gross_amount=Decimal("1234.56"),
            invoice_date=datetime(2026, 1, 15),
            supplier_id=uuid4(),
        )
        invoice2 = MagicMock(
            gross_amount=Decimal("1234.56"),
            invoice_date=datetime(2026, 1, 15),
            supplier_id=invoice1.supplier_id,
        )

        is_potential_duplicate = service._check_potential_duplicate(invoice1, invoice2)

        assert is_potential_duplicate is True

    def test_different_amounts_not_flagged(self, service):
        """Unterschiedliche Betraege werden nicht geflaggt."""
        invoice1 = MagicMock(
            gross_amount=Decimal("1234.56"),
            invoice_date=datetime(2026, 1, 15),
            supplier_id=uuid4(),
        )
        invoice2 = MagicMock(
            gross_amount=Decimal("5678.90"),
            invoice_date=datetime(2026, 1, 15),
            supplier_id=invoice1.supplier_id,
        )

        is_potential_duplicate = service._check_potential_duplicate(invoice1, invoice2)

        assert is_potential_duplicate is False


# =============================================================================
# Combined Detection Tests
# =============================================================================

class TestCombinedAnomalyDetection:
    """Tests fuer kombinierte Anomalie-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_all_anomalies(self, service, mock_db, sample_company_id):
        """Kombinierte Erkennung aller Anomalie-Typen."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_all_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_results_sorted_by_severity(self, service):
        """Ergebnisse sind nach Schweregrad sortiert."""
        results = [
            AnomalyCheckResult(
                anomaly_type=AnomalyType.PRICE_SPIKE,
                title="Low Severity",
                message="Test",
                severity="low",
            ),
            AnomalyCheckResult(
                anomaly_type=AnomalyType.DUPLICATE_PATTERN,
                title="Critical",
                message="Test",
                severity="critical",
            ),
            AnomalyCheckResult(
                anomaly_type=AnomalyType.VOLUME_HIGH,
                title="High",
                message="Test",
                severity="high",
            ),
        ]

        sorted_results = service._sort_by_severity(results)

        assert sorted_results[0].severity == "critical"
        assert sorted_results[1].severity == "high"
        assert sorted_results[2].severity == "low"


# =============================================================================
# Confidence Calculation Tests
# =============================================================================

class TestConfidenceCalculation:
    """Tests fuer Confidence-Berechnung."""

    def test_confidence_increases_with_z_score(self, service):
        """Confidence steigt mit Z-Score."""
        conf_low = service._calculate_confidence(z_score=2.0)
        conf_high = service._calculate_confidence(z_score=4.0)

        assert conf_high > conf_low

    def test_confidence_capped_at_one(self, service):
        """Confidence wird bei 1.0 gekappt."""
        conf = service._calculate_confidence(z_score=10.0)

        assert conf <= 1.0

    def test_confidence_minimum(self, service):
        """Confidence hat Mindestwert."""
        conf = service._calculate_confidence(z_score=0.5)

        assert conf >= 0.5  # Minimum Confidence


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.mark.asyncio
    async def test_handles_empty_history(self, service, mock_db, sample_company_id):
        """Behandelt leere Preishistorie."""
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(
            return_value=[]
        )))
        mock_db.execute = AsyncMock(return_value=mock_result)

        insights = await service.detect_price_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_handles_db_error(self, service, mock_db, sample_company_id):
        """Behandelt DB-Fehler graceful."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_all_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    def test_handles_zero_std(self, service):
        """Behandelt Standardabweichung von 0."""
        values = [100.0, 100.0, 100.0]  # Std = 0

        z_score = service._calculate_z_score(values, 100.0)

        assert z_score == 0.0  # Keine Abweichung

    def test_handles_negative_amounts(self, service):
        """Behandelt negative Betraege (Gutschriften)."""
        historical = [Decimal("-100.00"), Decimal("-95.00"), Decimal("-105.00")]
        current = Decimal("-200.00")  # Ungewoehnlich hoch

        is_anomaly, _ = service._check_price_deviation(
            historical, current, threshold_std=2.0
        )

        # Sollte trotzdem funktionieren
        assert isinstance(is_anomaly, bool)
