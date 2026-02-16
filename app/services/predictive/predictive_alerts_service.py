# -*- coding: utf-8 -*-
"""
Predictive Alerts Service.

Generiert proaktive Alerts basierend auf Vorhersagen:
- System Health Predictions
- OCR Quality Degradation
- Ressourcen-Erschoepfung

Vision 2.0 Feature: Predictive Maintenance (Phase 5)
Feinpoliert und durchdacht.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Literal, Optional, Union
from typing_extensions import TypedDict
from uuid import UUID, uuid4

from app.services.predictive.system_health_predictor import (
    PredictionResult,
    PredictionSeverity,
    SystemHealthPredictor,
    get_health_predictor,
)
from app.services.predictive.ocr_quality_forecaster import (
    DegradationAlert,
    OCRQualityForecaster,
    get_quality_forecaster,
)

logger = logging.getLogger(__name__)

# Type definitions for mypy strict mode
MetadataValue = Union[str, int, float, bool, None]
MetadataDict = Dict[str, MetadataValue]


class PredictiveAlertDict(TypedDict, total=False):
    """Typed dictionary for PredictiveAlert serialization."""
    id: str
    alert_type: str
    severity: str
    title: str
    message: str
    recommendation: str
    eta_minutes: Optional[float]
    confidence: float
    source: str
    created_at: str
    metadata: MetadataDict
    acknowledged: bool
    acknowledged_at: Optional[str]


class AlertStatsDict(TypedDict):
    """Typed dictionary for alert statistics."""
    total_active: int
    by_severity: Dict[str, int]
    by_type: Dict[str, int]
    by_source: Dict[str, int]
    history_count: int


class PredictiveAlertType(str, Enum):
    """Typen von proaktiven Alerts."""
    GPU_VRAM_OVERFLOW = "gpu_vram_overflow"
    QUEUE_OVERFLOW = "queue_overflow"
    DISK_EXHAUSTION = "disk_exhaustion"
    OCR_QUALITY_DEGRADATION = "ocr_quality_degradation"
    WORKER_FAILURE_SPIKE = "worker_failure_spike"
    MEMORY_EXHAUSTION = "memory_exhaustion"


class PredictiveAlertSeverity(str, Enum):
    """Schweregrad von proaktiven Alerts."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class PredictiveAlert:
    """Ein proaktiver Alert basierend auf Vorhersagen."""
    id: UUID
    alert_type: PredictiveAlertType
    severity: PredictiveAlertSeverity
    title: str
    message: str
    recommendation: str
    eta_minutes: Optional[float]
    confidence: float
    source: Literal["system_health", "ocr_quality"]  # Type-safe source
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: MetadataDict = field(default_factory=dict)
    acknowledged: bool = False
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[UUID] = None

    def to_dict(self) -> PredictiveAlertDict:
        """Konvertiert zu Dictionary."""
        return PredictiveAlertDict(
            id=str(self.id),
            alert_type=self.alert_type.value,
            severity=self.severity.value,
            title=self.title,
            message=self.message,
            recommendation=self.recommendation,
            eta_minutes=round(self.eta_minutes, 1) if self.eta_minutes else None,
            confidence=round(self.confidence, 2),
            source=self.source,
            created_at=self.created_at.isoformat(),
            metadata=self.metadata,
            acknowledged=self.acknowledged,
            acknowledged_at=self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        )


class PredictiveAlertsService:
    """
    Generiert und verwaltet proaktive Alerts.

    Kombiniert Vorhersagen aus verschiedenen Quellen und
    erzeugt benutzerfreundliche Warnungen.
    """

    def __init__(
        self,
        health_predictor: Optional[SystemHealthPredictor] = None,
        quality_forecaster: Optional[OCRQualityForecaster] = None
    ) -> None:
        """
        Initialisiert den Service.

        Args:
            health_predictor: System Health Predictor
            quality_forecaster: OCR Quality Forecaster
        """
        self.health_predictor = health_predictor or get_health_predictor()
        self.quality_forecaster = quality_forecaster or get_quality_forecaster()

        # In-Memory Alert Storage (in Produktion: Database)
        self._active_alerts: Dict[UUID, PredictiveAlert] = {}
        self._alert_history: List[PredictiveAlert] = []
        self._max_history_size: int = 1000

        logger.info("predictive_alerts_service_initialized")

    def _convert_prediction_severity(
        self,
        severity: PredictionSeverity
    ) -> PredictiveAlertSeverity:
        """Konvertiert Prediction-Severity zu Alert-Severity."""
        mapping = {
            PredictionSeverity.INFO: PredictiveAlertSeverity.INFO,
            PredictionSeverity.WARNING: PredictiveAlertSeverity.WARNING,
            PredictionSeverity.CRITICAL: PredictiveAlertSeverity.CRITICAL,
        }
        return mapping.get(severity, PredictiveAlertSeverity.INFO)

    def _create_alert_from_prediction(
        self,
        prediction: PredictionResult,
        alert_type: PredictiveAlertType
    ) -> PredictiveAlert:
        """Erstellt Alert aus Prediction."""
        # Titel basierend auf Typ
        titles = {
            PredictiveAlertType.GPU_VRAM_OVERFLOW: "GPU VRAM Überlauf droht",
            PredictiveAlertType.QUEUE_OVERFLOW: "Queue Überlauf droht",
            PredictiveAlertType.DISK_EXHAUSTION: "Festplattenspeicher erschoepft",
            PredictiveAlertType.MEMORY_EXHAUSTION: "Arbeitsspeicher erschoepft",
        }

        # Message mit ETA
        if prediction.eta_minutes is not None:
            if prediction.eta_minutes < 60:
                eta_str = f"in ca. {int(prediction.eta_minutes)} Minuten"
            else:
                eta_str = f"in ca. {prediction.eta_minutes / 60:.1f} Stunden"
            message = f"Basierend auf aktuellem Trend wird {titles.get(alert_type, 'Problem')} {eta_str} auftreten."
        else:
            message = f"Trend zeigt mögliches Problem bei {alert_type.value}."

        return PredictiveAlert(
            id=uuid4(),
            alert_type=alert_type,
            severity=self._convert_prediction_severity(prediction.severity),
            title=titles.get(alert_type, f"Warnung: {alert_type.value}"),
            message=message,
            recommendation=prediction.recommendation,
            eta_minutes=prediction.eta_minutes,
            confidence=prediction.confidence,
            source="system_health",
            metadata={
                "metric": prediction.metric.value,
                "current_value": prediction.current_value,
                "threshold": prediction.threshold,
                "trend": prediction.trend,
            }
        )

    def _create_alert_from_degradation(
        self,
        degradation: DegradationAlert
    ) -> PredictiveAlert:
        """Erstellt Alert aus Degradation-Warnung."""
        severity_mapping = {
            "info": PredictiveAlertSeverity.INFO,
            "warning": PredictiveAlertSeverity.WARNING,
            "critical": PredictiveAlertSeverity.CRITICAL,
        }

        if degradation.days_to_threshold is not None:
            if degradation.days_to_threshold < 1:
                eta_str = f"in weniger als 24 Stunden"
            else:
                eta_str = f"in ca. {degradation.days_to_threshold:.1f} Tagen"
            message = (
                f"OCR-Qualität für Backend '{degradation.backend.value}' verschlechtert sich. "
                f"Kritischer Schwellenwert wird {eta_str} erreicht."
            )
        else:
            message = f"OCR-Qualität für Backend '{degradation.backend.value}' zeigt negativen Trend."

        return PredictiveAlert(
            id=uuid4(),
            alert_type=PredictiveAlertType.OCR_QUALITY_DEGRADATION,
            severity=severity_mapping.get(degradation.severity, PredictiveAlertSeverity.INFO),
            title=f"OCR-Qualität degradiert: {degradation.backend.value}",
            message=message,
            recommendation=degradation.recommendation,
            eta_minutes=degradation.days_to_threshold * 24 * 60 if degradation.days_to_threshold else None,
            confidence=degradation.confidence,
            source="ocr_quality",
            metadata={
                "backend": degradation.backend.value,
                "metric": degradation.metric.value,
                "current_value": degradation.current_value,
                "trend_per_day": degradation.trend_per_day,
            }
        )

    async def generate_all_alerts(self) -> List[PredictiveAlert]:
        """
        Generiert alle proaktiven Alerts basierend auf aktuellen Vorhersagen.

        Returns:
            Liste neuer Alerts
        """
        new_alerts: List[PredictiveAlert] = []

        # System Health Predictions
        try:
            health_predictions = await self.health_predictor.get_all_predictions()

            for prediction in health_predictions:
                # Nur Warnings und Critical erzeugen Alerts
                if prediction.severity in (PredictionSeverity.WARNING, PredictionSeverity.CRITICAL):
                    # Bestimme Alert-Typ
                    from app.services.predictive.system_health_predictor import MetricType

                    type_mapping = {
                        MetricType.GPU_VRAM: PredictiveAlertType.GPU_VRAM_OVERFLOW,
                        MetricType.QUEUE_DEPTH: PredictiveAlertType.QUEUE_OVERFLOW,
                        MetricType.DISK_USAGE: PredictiveAlertType.DISK_EXHAUSTION,
                        MetricType.MEMORY_USAGE: PredictiveAlertType.MEMORY_EXHAUSTION,
                    }
                    alert_type = type_mapping.get(
                        prediction.metric,
                        PredictiveAlertType.GPU_VRAM_OVERFLOW
                    )

                    alert = self._create_alert_from_prediction(prediction, alert_type)
                    new_alerts.append(alert)

        except Exception as e:
            logger.error("health_prediction_failed", **safe_error_log(e))

        # OCR Quality Degradation
        try:
            degradation_alerts = await self.quality_forecaster.get_all_degradation_alerts()

            for degradation in degradation_alerts:
                if degradation.severity in ("warning", "critical"):
                    alert = self._create_alert_from_degradation(degradation)
                    new_alerts.append(alert)

        except Exception as e:
            logger.error("quality_forecast_failed", **safe_error_log(e))

        # Speichere neue Alerts
        for alert in new_alerts:
            self._active_alerts[alert.id] = alert

        logger.info(
            "predictive_alerts_generated",
            count=len(new_alerts),
            critical=sum(1 for a in new_alerts if a.severity == PredictiveAlertSeverity.CRITICAL)
        )

        return new_alerts

    def get_active_alerts(
        self,
        severity_filter: Optional[PredictiveAlertSeverity] = None,
        alert_type_filter: Optional[PredictiveAlertType] = None
    ) -> List[PredictiveAlert]:
        """
        Gibt aktive Alerts zurück.

        Args:
            severity_filter: Optional Severity-Filter
            alert_type_filter: Optional Type-Filter

        Returns:
            Liste aktiver Alerts
        """
        alerts = list(self._active_alerts.values())

        if severity_filter:
            alerts = [a for a in alerts if a.severity == severity_filter]

        if alert_type_filter:
            alerts = [a for a in alerts if a.alert_type == alert_type_filter]

        # Sortiere nach Severity und Erstellungszeit
        severity_order = {
            PredictiveAlertSeverity.CRITICAL: 0,
            PredictiveAlertSeverity.WARNING: 1,
            PredictiveAlertSeverity.INFO: 2,
        }
        alerts.sort(key=lambda a: (severity_order[a.severity], a.created_at))

        return alerts

    def acknowledge_alert(
        self,
        alert_id: UUID,
        user_id: Optional[UUID] = None
    ) -> bool:
        """
        Markiert Alert als bestätigt.

        Args:
            alert_id: Alert-ID
            user_id: Benutzer-ID

        Returns:
            True wenn erfolgreich
        """
        alert = self._active_alerts.get(alert_id)
        if not alert:
            return False

        alert.acknowledged = True
        alert.acknowledged_at = datetime.now(timezone.utc)
        alert.acknowledged_by = user_id

        # In History verschieben
        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history_size:
            self._alert_history.pop(0)

        del self._active_alerts[alert_id]

        logger.info(
            "predictive_alert_acknowledged",
            alert_id=str(alert_id),
            alert_type=alert.alert_type.value
        )

        return True

    def dismiss_alert(self, alert_id: UUID) -> bool:
        """
        Verwirft einen Alert ohne Bestätigung.

        Args:
            alert_id: Alert-ID

        Returns:
            True wenn erfolgreich
        """
        if alert_id in self._active_alerts:
            alert = self._active_alerts.pop(alert_id)
            logger.info(
                "predictive_alert_dismissed",
                alert_id=str(alert_id),
                alert_type=alert.alert_type.value
            )
            return True
        return False

    def get_alert_stats(self) -> AlertStatsDict:
        """
        Gibt Statistiken über Alerts zurück.

        Returns:
            Dict mit Statistiken
        """
        active_alerts = list(self._active_alerts.values())

        by_type: Dict[str, int] = {}
        for alert_type in PredictiveAlertType:
            by_type[alert_type.value] = sum(
                1 for a in active_alerts if a.alert_type == alert_type
            )

        by_source: Dict[str, int] = {}
        for source in ["system_health", "ocr_quality"]:
            by_source[source] = sum(
                1 for a in active_alerts if a.source == source
            )

        return AlertStatsDict(
            total_active=len(active_alerts),
            by_severity={
                "critical": sum(1 for a in active_alerts if a.severity == PredictiveAlertSeverity.CRITICAL),
                "warning": sum(1 for a in active_alerts if a.severity == PredictiveAlertSeverity.WARNING),
                "info": sum(1 for a in active_alerts if a.severity == PredictiveAlertSeverity.INFO),
            },
            by_type=by_type,
            by_source=by_source,
            history_count=len(self._alert_history),
        )

    def clear_old_alerts(self, max_age_hours: int = 24) -> int:
        """
        Entfernt alte Alerts.

        Args:
            max_age_hours: Maximales Alter in Stunden

        Returns:
            Anzahl entfernter Alerts
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        old_ids = [
            alert_id for alert_id, alert in self._active_alerts.items()
            if alert.created_at < cutoff
        ]

        for alert_id in old_ids:
            del self._active_alerts[alert_id]

        if old_ids:
            logger.info("old_predictive_alerts_cleared", count=len(old_ids))

        return len(old_ids)


# Singleton-Instanz
_predictive_alerts_service: Optional[PredictiveAlertsService] = None


def get_predictive_alerts_service() -> PredictiveAlertsService:
    """Gibt Singleton-Instanz des Predictive Alerts Service zurück."""
    global _predictive_alerts_service
    if _predictive_alerts_service is None:
        _predictive_alerts_service = PredictiveAlertsService()
    return _predictive_alerts_service
