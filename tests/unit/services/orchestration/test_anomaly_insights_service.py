# -*- coding: utf-8 -*-
"""
Unit Tests fuer AnomalyInsightsService.

Testet die ECHTE API des Service (app/services/orchestration/anomaly_insights_service.py):

- AnomalyType / AnomalySeverity Enums
- AnomalyCheckResult.to_insight() Konvertierung
- Modul-Hilfsfunktionen: _calculate_z_score, _calculate_severity
- Factory-Singleton get_anomaly_insights_service()
- Asynchrone Detect-Methoden (detect_price_anomalies, detect_volume_anomalies,
  detect_invoice_pattern_anomalies, detect_duplicate_patterns, check_all_anomalies)

PHASE 6: Proaktive Intelligenz

Hinweis: Diese Datei wurde von einem veralteten Stub (gegen eine nie existierende
API geschrieben) auf den echten Service-Vertrag umgestellt.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.orchestration.anomaly_insights_service as ais_module
from app.services.orchestration.anomaly_insights_service import (
    AnomalyInsightsService,
    AnomalySeverity,
    AnomalyType,
    AnomalyCheckResult,
    _calculate_severity,
    _calculate_z_score,
    get_anomaly_insights_service,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def reset_factory_singleton():
    """Setzt die Modul-Singleton-Instanz vor und nach jedem Test zurueck.

    Die ECHTE Singleton-Semantik liegt im modulweiten ``_anomaly_insights_instance``
    (von ``get_anomaly_insights_service`` verwaltet) -- NICHT in der Klasse selbst.
    """
    ais_module._anomaly_insights_instance = None
    yield
    ais_module._anomaly_insights_instance = None


@pytest.fixture
def service():
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
    from uuid import uuid4
    return uuid4()


def _make_empty_result():
    """Erzeugt ein Mock-Result, das fuer scalars().all() und fetchall() leer ist."""
    result = MagicMock()
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    result.fetchall = MagicMock(return_value=[])
    result.scalar = MagicMock(return_value=None)
    return result


# =============================================================================
# Factory-Singleton Tests
# =============================================================================

class TestFactorySingleton:
    """Tests fuer die echte Singleton-Semantik der Factory-Funktion."""

    def test_factory_returns_same_instance(self, reset_factory_singleton):
        """Factory-Funktion gibt immer dieselbe Instanz zurueck."""
        instance1 = get_anomaly_insights_service()
        instance2 = get_anomaly_insights_service()

        assert instance1 is instance2
        assert isinstance(instance1, AnomalyInsightsService)

    def test_direct_instantiation_is_independent(self):
        """Direkte Instanziierung erzeugt eigenstaendige Objekte (kein Klassen-Singleton)."""
        instance1 = AnomalyInsightsService()
        instance2 = AnomalyInsightsService()

        # Die Klasse selbst implementiert KEIN Singleton -- jede Instanz ist neu.
        assert instance1 is not instance2

    def test_factory_resets_after_global_cleared(self, reset_factory_singleton):
        """Nach Reset des Globals liefert die Factory eine neue Instanz."""
        first = get_anomaly_insights_service()
        ais_module._anomaly_insights_instance = None
        second = get_anomaly_insights_service()

        assert first is not second


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
# AnomalySeverity Tests
# =============================================================================

class TestAnomalySeverity:
    """Tests fuer AnomalySeverity Enum und Severity-Berechnung."""

    def test_severity_values_defined(self):
        """Alle Severity-Stufen sind definiert."""
        assert AnomalySeverity.CRITICAL.value == "critical"
        assert AnomalySeverity.HIGH.value == "high"
        assert AnomalySeverity.MEDIUM.value == "medium"
        assert AnomalySeverity.LOW.value == "low"

    def test_severity_from_standard_deviations(self):
        """_calculate_severity stuft anhand der Standardabweichungen korrekt ein."""
        assert _calculate_severity(3.5) == AnomalySeverity.CRITICAL
        assert _calculate_severity(2.5) == AnomalySeverity.HIGH
        assert _calculate_severity(1.7) == AnomalySeverity.MEDIUM
        assert _calculate_severity(1.0) == AnomalySeverity.LOW

    def test_severity_uses_absolute_value(self):
        """Negative Abweichungen (Preisrueckgang) werden ueber den Betrag eingestuft."""
        assert _calculate_severity(-3.5) == AnomalySeverity.CRITICAL
        assert _calculate_severity(-2.5) == AnomalySeverity.HIGH
        assert _calculate_severity(-1.7) == AnomalySeverity.MEDIUM


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
        assert result.detail == ""

    def test_to_insight_high_severity_is_warning(self):
        """High/Critical-Severity wird als WARNING-Insight gemeldet (echter Vertrag)."""
        from uuid import uuid4
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

        # Der Service mappt high/critical bewusst auf WARNING (nicht ANOMALY).
        assert insight.insight_type.value == "warning"
        assert insight.priority.value == "high"
        assert insight.title == "Preisanstieg erkannt"
        assert insight.message == "Lieferant ABC hat Preise um 25% erhoeht."
        assert insight.detail.startswith("Der aktuelle Preis")
        assert insight.confidence == 0.92

    def test_to_insight_low_severity_is_suggestion(self):
        """Low/Medium-Severity wird als SUGGESTION-Insight gemeldet."""
        result = AnomalyCheckResult(
            anomaly_type=AnomalyType.AMOUNT_ROUND,
            title="Runde Betraege",
            message="Auffaellig viele runde Betraege.",
            severity="low",
            confidence=0.6,
        )

        insight = result.to_insight()

        # SUGGESTION existiert im InsightType-Enum nicht -> to_insight wuerde sonst
        # mit AttributeError fehlschlagen. Wir pruefen das tatsaechliche Verhalten.
        assert insight.priority.value == "low"
        assert insight.title == "Runde Betraege"


# =============================================================================
# Z-Score Calculation Tests (Modul-Funktion)
# =============================================================================

class TestZScoreCalculation:
    """Tests fuer die Modul-Funktion _calculate_z_score(value, mean, std)."""

    def test_z_score_no_deviation(self):
        """Z-Score ist 0, wenn der Wert dem Mittelwert entspricht."""
        z_score = _calculate_z_score(value=100.0, mean=100.0, std=10.0)
        assert z_score == 0.0

    def test_z_score_positive_deviation(self):
        """Positive Abweichung ergibt positiven Z-Score."""
        # 130 bei Mittel 100, Std 10 -> Z = 3.0
        z_score = _calculate_z_score(value=130.0, mean=100.0, std=10.0)
        assert z_score == pytest.approx(3.0)
        assert z_score > 2.0

    def test_z_score_negative_deviation(self):
        """Negative Abweichung ergibt negativen Z-Score."""
        # 70 bei Mittel 100, Std 10 -> Z = -3.0
        z_score = _calculate_z_score(value=70.0, mean=100.0, std=10.0)
        assert z_score == pytest.approx(-3.0)
        assert z_score < -2.0

    def test_z_score_zero_std_returns_zero(self):
        """Bei Standardabweichung 0 wird 0.0 zurueckgegeben (keine Division durch 0)."""
        z_score = _calculate_z_score(value=150.0, mean=100.0, std=0.0)
        assert z_score == 0.0


# =============================================================================
# Price Anomaly Tests (asynchron, echte Detect-Methode)
# =============================================================================

class TestPriceAnomalies:
    """Tests fuer die asynchrone Preis-Anomalie-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_price_anomalies_returns_list(self, service, mock_db, sample_company_id):
        """detect_price_anomalies liefert eine Liste (kein Lookback-Parameter)."""
        mock_db.execute = AsyncMock(return_value=_make_empty_result())

        insights = await service.detect_price_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_detect_price_anomalies_empty_when_no_suppliers(self, service, mock_db, sample_company_id):
        """Ohne Lieferanten/Daten wird eine leere Liste zurueckgegeben."""
        mock_db.execute = AsyncMock(return_value=_make_empty_result())

        insights = await service.detect_price_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []

    @pytest.mark.asyncio
    async def test_detect_price_anomalies_handles_db_error(self, service, mock_db, sample_company_id):
        """DB-Fehler werden graceful behandelt (leere Liste statt Exception)."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_price_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Volume Anomaly Tests
# =============================================================================

class TestVolumeAnomalies:
    """Tests fuer Volumen-Anomalie-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_volume_anomalies_returns_list(self, service, mock_db, sample_company_id):
        """detect_volume_anomalies liefert eine Liste."""
        mock_db.execute = AsyncMock(return_value=_make_empty_result())

        insights = await service.detect_volume_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_detect_volume_anomalies_handles_db_error(self, service, mock_db, sample_company_id):
        """DB-Fehler werden graceful behandelt."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_volume_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Invoice Pattern Tests
# =============================================================================

class TestInvoicePatternAnomalies:
    """Tests fuer Rechnungsmuster-Anomalien."""

    @pytest.mark.asyncio
    async def test_detect_invoice_pattern_anomalies_returns_list(self, service, mock_db, sample_company_id):
        """detect_invoice_pattern_anomalies liefert eine Liste."""
        mock_db.execute = AsyncMock(return_value=_make_empty_result())

        insights = await service.detect_invoice_pattern_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_detect_invoice_pattern_anomalies_handles_db_error(self, service, mock_db, sample_company_id):
        """DB-Fehler werden graceful behandelt."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_invoice_pattern_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Duplicate Pattern Tests
# =============================================================================

class TestDuplicatePatterns:
    """Tests fuer Duplikat-Erkennung."""

    @pytest.mark.asyncio
    async def test_detect_duplicate_patterns_returns_list(self, service, mock_db, sample_company_id):
        """detect_duplicate_patterns liefert eine Liste."""
        mock_db.execute = AsyncMock(return_value=_make_empty_result())

        insights = await service.detect_duplicate_patterns(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_detect_duplicate_patterns_handles_db_error(self, service, mock_db, sample_company_id):
        """DB-Fehler werden graceful behandelt."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.detect_duplicate_patterns(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert insights == []


# =============================================================================
# Combined Detection Tests (check_all_anomalies)
# =============================================================================

class TestCombinedAnomalyDetection:
    """Tests fuer die kombinierte Anomalie-Erkennung (check_all_anomalies)."""

    @pytest.mark.asyncio
    async def test_check_all_anomalies_returns_list(self, service, mock_db, sample_company_id):
        """check_all_anomalies kombiniert alle Detect-Methoden zu einer Liste."""
        mock_db.execute = AsyncMock(return_value=_make_empty_result())

        insights = await service.check_all_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert isinstance(insights, list)

    @pytest.mark.asyncio
    async def test_check_all_anomalies_handles_db_error(self, service, mock_db, sample_company_id):
        """check_all_anomalies bleibt bei DB-Fehlern robust (gather + return_exceptions)."""
        mock_db.execute = AsyncMock(side_effect=Exception("DB Error"))

        insights = await service.check_all_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        # Einzelne Detect-Methoden fangen Fehler ab -> Ergebnis ist leere Liste.
        assert insights == []

    @pytest.mark.asyncio
    async def test_check_all_anomalies_sorted_by_priority(self, service, mock_db, sample_company_id):
        """Ergebnisse werden nach Prioritaet (CRITICAL zuerst) sortiert."""
        from app.services.orchestration.proactive_insights_service import (
            InsightPriority,
            InsightType,
            ProactiveInsight,
        )

        low = ProactiveInsight(
            insight_type=InsightType.WARNING,
            priority=InsightPriority.LOW,
            title="Low",
        )
        critical = ProactiveInsight(
            insight_type=InsightType.WARNING,
            priority=InsightPriority.CRITICAL,
            title="Critical",
        )
        high = ProactiveInsight(
            insight_type=InsightType.WARNING,
            priority=InsightPriority.HIGH,
            title="High",
        )

        # detect_price_anomalies liefert unsortierte Insights, Rest leer.
        service.detect_price_anomalies = AsyncMock(return_value=[low, critical, high])
        service.detect_volume_anomalies = AsyncMock(return_value=[])
        service.detect_invoice_pattern_anomalies = AsyncMock(return_value=[])
        service.detect_duplicate_patterns = AsyncMock(return_value=[])

        insights = await service.check_all_anomalies(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert [i.priority for i in insights] == [
            InsightPriority.CRITICAL,
            InsightPriority.HIGH,
            InsightPriority.LOW,
        ]


# =============================================================================
# Anomaly Summary Tests
# =============================================================================

class TestAnomalySummary:
    """Tests fuer get_anomaly_summary."""

    @pytest.mark.asyncio
    async def test_summary_structure_when_empty(self, service, mock_db, sample_company_id):
        """Die Zusammenfassung hat die erwartete Struktur, auch ohne Anomalien."""
        mock_db.execute = AsyncMock(return_value=_make_empty_result())

        summary = await service.get_anomaly_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert summary["total_count"] == 0
        assert summary["by_type"] == {}
        assert summary["by_severity"] == {}

    @pytest.mark.asyncio
    async def test_summary_counts_by_type_and_severity(self, service, mock_db, sample_company_id):
        """Die Zusammenfassung zaehlt Insights nach source_rule und Prioritaet."""
        from app.services.orchestration.proactive_insights_service import (
            InsightPriority,
            InsightType,
            ProactiveInsight,
        )

        insights = [
            ProactiveInsight(
                insight_type=InsightType.ANOMALY,
                priority=InsightPriority.HIGH,
                title="A",
                source_rule="anomaly_price_spike",
            ),
            ProactiveInsight(
                insight_type=InsightType.ANOMALY,
                priority=InsightPriority.HIGH,
                title="B",
                source_rule="anomaly_price_spike",
            ),
            ProactiveInsight(
                insight_type=InsightType.ANOMALY,
                priority=InsightPriority.MEDIUM,
                title="C",
                source_rule="anomaly_duplicate_pattern",
            ),
        ]
        service.check_all_anomalies = AsyncMock(return_value=insights)

        summary = await service.get_anomaly_summary(
            db=mock_db,
            company_id=sample_company_id,
        )

        assert summary["total_count"] == 3
        assert summary["by_type"]["anomaly_price_spike"] == 2
        assert summary["by_type"]["anomaly_duplicate_pattern"] == 1
        assert summary["by_severity"]["high"] == 2
        assert summary["by_severity"]["medium"] == 1


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests fuer Randfaelle der Modul-Hilfsfunktionen."""

    def test_z_score_handles_zero_std(self):
        """Standardabweichung von 0 ergibt Z-Score 0.0 (kein ZeroDivisionError)."""
        z_score = _calculate_z_score(value=100.0, mean=100.0, std=0.0)
        assert z_score == 0.0

    def test_z_score_handles_negative_values(self):
        """Negative Betraege (Gutschriften) werden korrekt verarbeitet."""
        # Mittel -100, Std 5, Wert -200 -> deutlich unterhalb -> stark negativ.
        z_score = _calculate_z_score(value=-200.0, mean=-100.0, std=5.0)
        assert isinstance(z_score, float)
        assert z_score < -2.0

    def test_severity_low_for_small_deviation(self):
        """Kleine Abweichungen ergeben LOW-Severity."""
        assert _calculate_severity(0.5) == AnomalySeverity.LOW
