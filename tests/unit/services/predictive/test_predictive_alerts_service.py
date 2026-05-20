# -*- coding: utf-8 -*-
"""
Tests fuer Predictive Alerts Service.

Testet:
- Alert-Generierung
- Alert-Verwaltung
- Alert-Statistiken
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.predictive.predictive_alerts_service import (
    PredictiveAlertsService,
    PredictiveAlert,
    PredictiveAlertType,
    PredictiveAlertSeverity,
    get_predictive_alerts_service,
)
from app.services.predictive.system_health_predictor import (
    PredictionResult,
    PredictionSeverity,
    MetricType,
)
from app.services.predictive.ocr_quality_forecaster import (
    DegradationAlert,
    OCRBackend,
    QualityMetric,
)


class TestPredictiveAlertCreation:
    """Tests fuer Alert-Erstellung."""

    def test_create_alert(self) -> None:
        """Alert sollte korrekt erstellt werden."""
        alert = PredictiveAlert(
            id=uuid4(),
            alert_type=PredictiveAlertType.GPU_VRAM_OVERFLOW,
            severity=PredictiveAlertSeverity.WARNING,
            title="GPU VRAM Ueberlauf droht",
            message="VRAM wird in 10 Minuten erschoepft",
            recommendation="Reduziere Batch-Size",
            eta_minutes=10.0,
            confidence=0.85,
            source="system_health"
        )

        assert alert.alert_type == PredictiveAlertType.GPU_VRAM_OVERFLOW
        assert alert.severity == PredictiveAlertSeverity.WARNING
        assert alert.acknowledged is False

    def test_alert_to_dict(self) -> None:
        """Alert sollte korrekt serialisiert werden."""
        alert_id = uuid4()
        alert = PredictiveAlert(
            id=alert_id,
            alert_type=PredictiveAlertType.QUEUE_OVERFLOW,
            severity=PredictiveAlertSeverity.CRITICAL,
            title="Queue Ueberlauf",
            message="Queue wird ueberlaufen",
            recommendation="Starte Worker",
            eta_minutes=5.0,
            confidence=0.90,
            source="system_health"
        )

        d = alert.to_dict()

        assert d["id"] == str(alert_id)
        assert d["alert_type"] == "queue_overflow"
        assert d["severity"] == "critical"
        assert d["eta_minutes"] == 5.0


class TestServiceInitialization:
    """Tests fuer Service-Initialisierung."""

    def test_init_with_default_predictors(self) -> None:
        """Service sollte mit Default-Predictors initialisiert werden."""
        service = PredictiveAlertsService()

        assert service.health_predictor is not None
        assert service.quality_forecaster is not None

    def test_init_with_custom_predictors(self) -> None:
        """Service sollte mit Custom-Predictors initialisiert werden."""
        mock_health = MagicMock()
        mock_quality = MagicMock()

        service = PredictiveAlertsService(
            health_predictor=mock_health,
            quality_forecaster=mock_quality
        )

        assert service.health_predictor is mock_health
        assert service.quality_forecaster is mock_quality


class TestAlertFromPrediction:
    """Tests fuer Alert-Erstellung aus Predictions."""

    def test_create_alert_from_prediction(self) -> None:
        """Alert sollte aus Prediction erstellt werden."""
        service = PredictiveAlertsService()

        prediction = PredictionResult(
            metric=MetricType.GPU_VRAM,
            current_value=13.5,
            predicted_value=14.4,
            threshold=14.4,
            eta_minutes=8.5,
            trend=0.1,
            severity=PredictionSeverity.WARNING,
            recommendation="Reduziere Batch-Size",
            confidence=0.88
        )

        alert = service._create_alert_from_prediction(
            prediction,
            PredictiveAlertType.GPU_VRAM_OVERFLOW
        )

        assert alert.alert_type == PredictiveAlertType.GPU_VRAM_OVERFLOW
        assert alert.severity == PredictiveAlertSeverity.WARNING
        assert alert.eta_minutes == 8.5
        assert alert.source == "system_health"

    def test_create_alert_from_degradation(self) -> None:
        """Alert sollte aus Degradation erstellt werden."""
        service = PredictiveAlertsService()

        degradation = DegradationAlert(
            backend=OCRBackend.DEEPSEEK,
            metric=QualityMetric.CER,
            current_value=0.045,
            threshold=0.05,
            trend_per_day=0.005,
            days_to_threshold=1.0,
            severity="critical",
            recommendation="Sofortiges Retraining",
            confidence=0.92
        )

        alert = service._create_alert_from_degradation(degradation)

        assert alert.alert_type == PredictiveAlertType.OCR_QUALITY_DEGRADATION
        assert alert.severity == PredictiveAlertSeverity.CRITICAL
        assert alert.source == "ocr_quality"
        assert "deepseek" in alert.title.lower()


class TestAlertGeneration:
    """Tests fuer Alert-Generierung."""

    @pytest.mark.asyncio
    async def test_generate_all_alerts_empty(self) -> None:
        """Ohne Probleme sollten keine Alerts generiert werden."""
        mock_health = MagicMock()
        mock_health.get_all_predictions = AsyncMock(return_value=[])

        mock_quality = MagicMock()
        mock_quality.get_all_degradation_alerts = AsyncMock(return_value=[])

        service = PredictiveAlertsService(
            health_predictor=mock_health,
            quality_forecaster=mock_quality
        )

        alerts = await service.generate_all_alerts()

        assert alerts == []

    @pytest.mark.asyncio
    async def test_generate_all_alerts_with_warnings(self) -> None:
        """Bei Warnings sollten Alerts generiert werden."""
        prediction = PredictionResult(
            metric=MetricType.GPU_VRAM,
            current_value=13.5,
            predicted_value=14.4,
            threshold=14.4,
            eta_minutes=5.0,
            trend=0.2,
            severity=PredictionSeverity.WARNING,
            recommendation="Reduziere",
            confidence=0.85
        )

        mock_health = MagicMock()
        mock_health.get_all_predictions = AsyncMock(return_value=[prediction])

        mock_quality = MagicMock()
        mock_quality.get_all_degradation_alerts = AsyncMock(return_value=[])

        service = PredictiveAlertsService(
            health_predictor=mock_health,
            quality_forecaster=mock_quality
        )

        alerts = await service.generate_all_alerts()

        assert len(alerts) == 1
        assert alerts[0].severity == PredictiveAlertSeverity.WARNING


class TestAlertManagement:
    """Tests fuer Alert-Verwaltung."""

    def test_get_active_alerts_empty(self) -> None:
        """Ohne Alerts sollte leere Liste zurueckgegeben werden."""
        service = PredictiveAlertsService()

        alerts = service.get_active_alerts()

        assert alerts == []

    @pytest.mark.asyncio
    async def test_get_active_alerts_with_filter(self) -> None:
        """Filter sollten funktionieren."""
        mock_health = MagicMock()
        mock_health.get_all_predictions = AsyncMock(return_value=[
            PredictionResult(
                metric=MetricType.GPU_VRAM,
                current_value=13.5,
                predicted_value=14.4,
                threshold=14.4,
                eta_minutes=5.0,
                trend=0.2,
                severity=PredictionSeverity.WARNING,
                recommendation="",
                confidence=0.85
            ),
            PredictionResult(
                metric=MetricType.QUEUE_DEPTH,
                current_value=400,
                predicted_value=500,
                threshold=500,
                eta_minutes=3.0,
                trend=30,
                severity=PredictionSeverity.CRITICAL,
                recommendation="",
                confidence=0.90
            )
        ])

        mock_quality = MagicMock()
        mock_quality.get_all_degradation_alerts = AsyncMock(return_value=[])

        service = PredictiveAlertsService(
            health_predictor=mock_health,
            quality_forecaster=mock_quality
        )

        await service.generate_all_alerts()

        # Alle Alerts
        all_alerts = service.get_active_alerts()
        assert len(all_alerts) == 2

        # Nur Critical
        critical_alerts = service.get_active_alerts(
            severity_filter=PredictiveAlertSeverity.CRITICAL
        )
        assert len(critical_alerts) == 1

    def test_acknowledge_alert(self) -> None:
        """Alert sollte acknowledged werden koennen."""
        service = PredictiveAlertsService()

        # Fuege Alert manuell hinzu
        alert = PredictiveAlert(
            id=uuid4(),
            alert_type=PredictiveAlertType.GPU_VRAM_OVERFLOW,
            severity=PredictiveAlertSeverity.WARNING,
            title="Test",
            message="Test",
            recommendation="Test",
            eta_minutes=10.0,
            confidence=0.85,
            source="test"
        )
        service._active_alerts[alert.id] = alert

        user_id = uuid4()
        success = service.acknowledge_alert(alert.id, user_id)

        assert success is True
        assert alert.acknowledged is True
        assert alert.acknowledged_by == user_id
        assert alert.id not in service._active_alerts

    def test_acknowledge_nonexistent_alert(self) -> None:
        """Nicht existierender Alert sollte False zurueckgeben."""
        service = PredictiveAlertsService()

        success = service.acknowledge_alert(uuid4())

        assert success is False

    def test_dismiss_alert(self) -> None:
        """Alert sollte dismissed werden koennen."""
        service = PredictiveAlertsService()

        # Fuege Alert hinzu
        alert = PredictiveAlert(
            id=uuid4(),
            alert_type=PredictiveAlertType.DISK_EXHAUSTION,
            severity=PredictiveAlertSeverity.INFO,
            title="Test",
            message="Test",
            recommendation="Test",
            eta_minutes=None,
            confidence=0.75,
            source="test"
        )
        service._active_alerts[alert.id] = alert

        success = service.dismiss_alert(alert.id)

        assert success is True
        assert alert.id not in service._active_alerts


class TestAlertStatistics:
    """Tests fuer Alert-Statistiken."""

    def test_get_alert_stats_empty(self) -> None:
        """Leere Statistiken sollten korrekt sein."""
        service = PredictiveAlertsService()

        stats = service.get_alert_stats()

        assert stats["total_active"] == 0
        assert stats["by_severity"]["critical"] == 0
        assert stats["by_severity"]["warning"] == 0
        assert stats["by_severity"]["info"] == 0

    def test_get_alert_stats_with_alerts(self) -> None:
        """Statistiken sollten Alerts zaehlen."""
        service = PredictiveAlertsService()

        # Fuege verschiedene Alerts hinzu
        for severity in [
            PredictiveAlertSeverity.CRITICAL,
            PredictiveAlertSeverity.WARNING,
            PredictiveAlertSeverity.WARNING,
            PredictiveAlertSeverity.INFO
        ]:
            alert = PredictiveAlert(
                id=uuid4(),
                alert_type=PredictiveAlertType.GPU_VRAM_OVERFLOW,
                severity=severity,
                title="Test",
                message="Test",
                recommendation="Test",
                eta_minutes=10.0,
                confidence=0.85,
                source="test"
            )
            service._active_alerts[alert.id] = alert

        stats = service.get_alert_stats()

        assert stats["total_active"] == 4
        assert stats["by_severity"]["critical"] == 1
        assert stats["by_severity"]["warning"] == 2
        assert stats["by_severity"]["info"] == 1


class TestAlertCleanup:
    """Tests fuer Alert-Cleanup."""

    def test_clear_old_alerts(self) -> None:
        """Alte Alerts sollten geloescht werden."""
        service = PredictiveAlertsService()

        # Fuege alten Alert hinzu
        old_alert = PredictiveAlert(
            id=uuid4(),
            alert_type=PredictiveAlertType.GPU_VRAM_OVERFLOW,
            severity=PredictiveAlertSeverity.INFO,
            title="Old",
            message="Old",
            recommendation="Old",
            eta_minutes=None,
            confidence=0.80,
            source="test",
            created_at=datetime.utcnow() - timedelta(hours=48)
        )
        service._active_alerts[old_alert.id] = old_alert

        # Fuege neuen Alert hinzu
        new_alert = PredictiveAlert(
            id=uuid4(),
            alert_type=PredictiveAlertType.QUEUE_OVERFLOW,
            severity=PredictiveAlertSeverity.WARNING,
            title="New",
            message="New",
            recommendation="New",
            eta_minutes=5.0,
            confidence=0.85,
            source="test",
            created_at=datetime.utcnow()
        )
        service._active_alerts[new_alert.id] = new_alert

        removed = service.clear_old_alerts(max_age_hours=24)

        assert removed == 1
        assert old_alert.id not in service._active_alerts
        assert new_alert.id in service._active_alerts


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_predictive_alerts_service_singleton(self) -> None:
        """get_predictive_alerts_service sollte Singleton zurueckgeben."""
        svc1 = get_predictive_alerts_service()
        svc2 = get_predictive_alerts_service()

        assert svc1 is svc2
