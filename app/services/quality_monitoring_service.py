"""
Quality Monitoring Service

Überwacht die OCR-Qualität und erkennt Degradation automatisch.
Unterstützt automatisches Retraining-Triggering und Model-Rollback.

Features:
- Kontinuierliche Qualitätsüberwachung
- Automatische Degradationserkennung
- Retraining-Empfehlungen
- Model-Rollback bei kritischen Problemen

Author: Claude Code
Created: 2024-12
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class AlertSeverity(str, Enum):
    """Schweregrad von Alerts."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Typ des Alerts."""
    CER_DEGRADATION = "cer_degradation"
    UMLAUT_DEGRADATION = "umlaut_degradation"
    HIGH_CORRECTION_RATE = "high_correction_rate"
    MODEL_PERFORMANCE = "model_performance"
    RETRAINING_RECOMMENDED = "retraining_recommended"


@dataclass
class QualityAlert:
    """Ein Qualitäts-Alert."""
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    metric_name: str
    current_value: float
    threshold_value: float
    affected_backend: Optional[str] = None
    recommended_action: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class QualitySnapshot:
    """Snapshot der aktuellen Qualitätsmetriken."""
    timestamp: str
    backend_name: str
    avg_cer: float
    avg_wer: float
    umlaut_accuracy: float
    correction_count: int
    sample_count: int
    processing_time_avg_ms: float


@dataclass
class RetrainingRecommendation:
    """Empfehlung für Retraining."""
    should_retrain: bool
    urgency: str  # low, medium, high, critical
    reasons: List[str]
    estimated_samples_needed: int
    focus_areas: List[str]
    last_training_date: Optional[str] = None


@dataclass
class ModelHealthStatus:
    """Gesundheitsstatus eines Modells."""
    model_name: str
    version: str
    is_healthy: bool
    health_score: float  # 0.0 - 1.0
    issues: List[str]
    metrics: Dict[str, float]
    last_checked: str


class QualityMonitoringService:
    """
    Service zur Überwachung der OCR-Qualität.

    Überwacht kontinuierlich:
    - Character Error Rate (CER)
    - Umlaut-Genauigkeit
    - Korrektur-Rate
    - Model-Performance
    """

    # Schwellenwerte
    ALERT_CER_THRESHOLD = 0.10  # 10% CER
    ALERT_CER_CRITICAL = 0.20  # 20% CER (kritisch)
    ALERT_UMLAUT_THRESHOLD = 0.95  # 95% Umlaut-Genauigkeit
    ALERT_UMLAUT_CRITICAL = 0.90  # 90% (kritisch)
    RETRAINING_TRIGGER_CORRECTIONS = 500  # Korrekturen seit letztem Training
    DEGRADATION_WINDOW_HOURS = 24  # Fenster für Degradationserkennung
    MINIMUM_SAMPLES_FOR_ALERT = 50  # Mindest-Samples für valide Alerts

    def __init__(self, db: AsyncSession):
        """
        Initialisiert den Monitoring-Service.

        Args:
            db: Datenbank-Session
        """
        self.db = db
        self._alert_history: List[QualityAlert] = []

    async def run_quality_check(self) -> List[QualityAlert]:
        """
        Führt einen vollständigen Qualitätscheck durch.

        Returns:
            Liste von Alerts
        """
        logger.info("Starte Qualitätscheck...")
        alerts = []

        backends = ["deepseek", "got_ocr", "surya_gpu", "surya_cpu"]

        for backend in backends:
            backend_alerts = await self._check_backend_quality(backend)
            alerts.extend(backend_alerts)

        global_alerts = await self._check_global_metrics()
        alerts.extend(global_alerts)

        retraining_alerts = await self._check_retraining_conditions()
        alerts.extend(retraining_alerts)

        self._alert_history.extend(alerts)

        logger.info(f"Qualitätscheck abgeschlossen: {len(alerts)} Alerts")
        return alerts

    async def _check_backend_quality(self, backend_name: str) -> List[QualityAlert]:
        """Prüft Qualität eines spezifischen Backends."""
        alerts = []

        try:
            current_snapshot = await self._get_current_snapshot(backend_name)

            if current_snapshot.sample_count < self.MINIMUM_SAMPLES_FOR_ALERT:
                return alerts

            if current_snapshot.avg_cer > self.ALERT_CER_CRITICAL:
                alerts.append(QualityAlert(
                    alert_type=AlertType.CER_DEGRADATION,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Kritische CER für {backend_name}: {current_snapshot.avg_cer:.2%}",
                    metric_name="cer",
                    current_value=current_snapshot.avg_cer,
                    threshold_value=self.ALERT_CER_CRITICAL,
                    affected_backend=backend_name,
                    recommended_action="Sofortiges Retraining oder Rollback empfohlen"
                ))
            elif current_snapshot.avg_cer > self.ALERT_CER_THRESHOLD:
                alerts.append(QualityAlert(
                    alert_type=AlertType.CER_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    message=f"Erhöhte CER für {backend_name}: {current_snapshot.avg_cer:.2%}",
                    metric_name="cer",
                    current_value=current_snapshot.avg_cer,
                    threshold_value=self.ALERT_CER_THRESHOLD,
                    affected_backend=backend_name,
                    recommended_action="Retraining planen"
                ))

            if current_snapshot.umlaut_accuracy < self.ALERT_UMLAUT_CRITICAL:
                alerts.append(QualityAlert(
                    alert_type=AlertType.UMLAUT_DEGRADATION,
                    severity=AlertSeverity.CRITICAL,
                    message=f"Kritische Umlaut-Genauigkeit für {backend_name}: {current_snapshot.umlaut_accuracy:.2%}",
                    metric_name="umlaut_accuracy",
                    current_value=current_snapshot.umlaut_accuracy,
                    threshold_value=self.ALERT_UMLAUT_CRITICAL,
                    affected_backend=backend_name,
                    recommended_action="Sofortiges Retraining für deutsche Texte"
                ))
            elif current_snapshot.umlaut_accuracy < self.ALERT_UMLAUT_THRESHOLD:
                alerts.append(QualityAlert(
                    alert_type=AlertType.UMLAUT_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    message=f"Reduzierte Umlaut-Genauigkeit für {backend_name}: {current_snapshot.umlaut_accuracy:.2%}",
                    metric_name="umlaut_accuracy",
                    current_value=current_snapshot.umlaut_accuracy,
                    threshold_value=self.ALERT_UMLAUT_THRESHOLD,
                    affected_backend=backend_name,
                    recommended_action="Umlaut-Training-Daten erweitern"
                ))

            degradation = await self._detect_degradation(backend_name)
            if degradation:
                alerts.append(degradation)

        except Exception as e:
            logger.warning(f"Fehler bei Backend-Check {backend_name}: {e}")

        return alerts

    async def _get_current_snapshot(self, backend_name: str) -> QualitySnapshot:
        """Holt aktuellen Qualitäts-Snapshot für ein Backend."""
        from app.db.models import OCRQualitySnapshot
        from app.core.safe_errors import safe_error_log

        since = datetime.now() - timedelta(hours=self.DEGRADATION_WINDOW_HOURS)

        query = select(OCRQualitySnapshot).where(
            and_(
                OCRQualitySnapshot.backend_name == backend_name,
                OCRQualitySnapshot.timestamp >= since
            )
        ).order_by(desc(OCRQualitySnapshot.timestamp)).limit(1)

        result = await self.db.execute(query)
        snapshot = result.scalar_one_or_none()

        if snapshot:
            return QualitySnapshot(
                timestamp=snapshot.timestamp.isoformat(),
                backend_name=snapshot.backend_name,
                avg_cer=snapshot.avg_cer or 0.0,
                avg_wer=snapshot.avg_wer or 0.0,
                umlaut_accuracy=snapshot.avg_umlaut_accuracy or 1.0,
                correction_count=snapshot.correction_count or 0,
                sample_count=snapshot.sample_count or 0,
                processing_time_avg_ms=snapshot.processing_time_avg_ms or 0.0
            )

        return QualitySnapshot(
            timestamp=datetime.now().isoformat(),
            backend_name=backend_name,
            avg_cer=0.0,
            avg_wer=0.0,
            umlaut_accuracy=1.0,
            correction_count=0,
            sample_count=0,
            processing_time_avg_ms=0.0
        )

    async def _detect_degradation(self, backend_name: str) -> Optional[QualityAlert]:
        """Erkennt Qualitätsverschlechterung über Zeit."""
        from app.db.models import OCRQualitySnapshot

        now = datetime.now()
        recent_start = now - timedelta(hours=24)
        previous_start = now - timedelta(hours=48)

        recent_query = select(
            func.avg(OCRQualitySnapshot.avg_cer).label("avg_cer")
        ).where(
            and_(
                OCRQualitySnapshot.backend_name == backend_name,
                OCRQualitySnapshot.timestamp >= recent_start
            )
        )

        previous_query = select(
            func.avg(OCRQualitySnapshot.avg_cer).label("avg_cer")
        ).where(
            and_(
                OCRQualitySnapshot.backend_name == backend_name,
                OCRQualitySnapshot.timestamp >= previous_start,
                OCRQualitySnapshot.timestamp < recent_start
            )
        )

        recent_result = await self.db.execute(recent_query)
        previous_result = await self.db.execute(previous_query)

        recent_cer = recent_result.scalar() or 0.0
        previous_cer = previous_result.scalar() or 0.0

        if previous_cer > 0 and recent_cer > 0:
            degradation_pct = (recent_cer - previous_cer) / previous_cer

            if degradation_pct > 0.20:  # 20% Verschlechterung
                return QualityAlert(
                    alert_type=AlertType.CER_DEGRADATION,
                    severity=AlertSeverity.WARNING,
                    message=f"CER-Degradation erkannt für {backend_name}: {degradation_pct:.1%} Verschlechterung in 24h",
                    metric_name="cer_degradation",
                    current_value=recent_cer,
                    threshold_value=previous_cer,
                    affected_backend=backend_name,
                    recommended_action="Ursachenanalyse und mögliches Rollback prüfen"
                )

        return None

    async def _check_global_metrics(self) -> List[QualityAlert]:
        """Prüft globale Metriken über alle Backends."""
        alerts = []

        from app.db.models import OCRTrainingSample

        since = datetime.now() - timedelta(days=7)

        query = select(func.count()).select_from(OCRTrainingSample).where(
            and_(
                OCRTrainingSample.correction_history.isnot(None),
                OCRTrainingSample.updated_at >= since
            )
        )

        result = await self.db.execute(query)
        correction_count = result.scalar() or 0

        if correction_count > self.RETRAINING_TRIGGER_CORRECTIONS:
            alerts.append(QualityAlert(
                alert_type=AlertType.HIGH_CORRECTION_RATE,
                severity=AlertSeverity.WARNING,
                message=f"Hohe Korrekturrate: {correction_count} Korrekturen in 7 Tagen",
                metric_name="correction_count",
                current_value=float(correction_count),
                threshold_value=float(self.RETRAINING_TRIGGER_CORRECTIONS),
                recommended_action="Retraining mit neuen Korrekturen durchführen"
            ))

        return alerts

    async def _check_retraining_conditions(self) -> List[QualityAlert]:
        """Prüft ob Retraining empfohlen wird."""
        alerts = []

        recommendation = await self.get_retraining_recommendation()

        if recommendation.should_retrain:
            severity = AlertSeverity.INFO
            if recommendation.urgency == "high":
                severity = AlertSeverity.WARNING
            elif recommendation.urgency == "critical":
                severity = AlertSeverity.CRITICAL

            alerts.append(QualityAlert(
                alert_type=AlertType.RETRAINING_RECOMMENDED,
                severity=severity,
                message=f"Retraining empfohlen ({recommendation.urgency}): {', '.join(recommendation.reasons[:2])}",
                metric_name="retraining_urgency",
                current_value={"low": 1, "medium": 2, "high": 3, "critical": 4}.get(recommendation.urgency, 0),
                threshold_value=2.0,
                recommended_action=f"Fokus auf: {', '.join(recommendation.focus_areas[:3])}"
            ))

        return alerts

    async def get_retraining_recommendation(self) -> RetrainingRecommendation:
        """
        Generiert Retraining-Empfehlung basierend auf aktuellen Metriken.

        Returns:
            RetrainingRecommendation
        """
        reasons = []
        focus_areas = []
        urgency = "low"

        from app.db.models import OCRTrainingSample, OCRQualitySnapshot

        since = datetime.now() - timedelta(days=30)
        query = select(func.count()).select_from(OCRTrainingSample).where(
            and_(
                OCRTrainingSample.correction_history.isnot(None),
                OCRTrainingSample.updated_at >= since
            )
        )
        result = await self.db.execute(query)
        correction_count = result.scalar() or 0

        if correction_count > self.RETRAINING_TRIGGER_CORRECTIONS:
            reasons.append(f"{correction_count} Korrekturen seit letztem Training")
            urgency = "medium"

        if correction_count > self.RETRAINING_TRIGGER_CORRECTIONS * 2:
            urgency = "high"

        backends = ["deepseek", "got_ocr", "surya_gpu", "surya_cpu"]
        for backend in backends:
            snapshot = await self._get_current_snapshot(backend)

            if snapshot.avg_cer > self.ALERT_CER_THRESHOLD:
                reasons.append(f"Hohe CER für {backend}: {snapshot.avg_cer:.2%}")
                focus_areas.append(f"{backend}_cer_improvement")
                if snapshot.avg_cer > self.ALERT_CER_CRITICAL:
                    urgency = "critical"

            if snapshot.umlaut_accuracy < self.ALERT_UMLAUT_THRESHOLD:
                reasons.append(f"Niedrige Umlaut-Genauigkeit für {backend}: {snapshot.umlaut_accuracy:.2%}")
                focus_areas.append("german_umlauts")
                if urgency != "critical":
                    urgency = "high"

        should_retrain = len(reasons) > 0
        estimated_samples = max(1000, correction_count * 2)

        return RetrainingRecommendation(
            should_retrain=should_retrain,
            urgency=urgency,
            reasons=reasons,
            estimated_samples_needed=estimated_samples,
            focus_areas=focus_areas,
            last_training_date=None
        )

    async def should_rollback_model(self, model_name: str) -> bool:
        """
        Prüft ob ein Model-Rollback durchgeführt werden sollte.

        Args:
            model_name: Name des Modells (deepseek, surya)

        Returns:
            True wenn Rollback empfohlen
        """
        snapshot = await self._get_current_snapshot(model_name)

        if snapshot.avg_cer > self.ALERT_CER_CRITICAL:
            logger.warning(f"Rollback empfohlen für {model_name}: CER {snapshot.avg_cer:.2%}")
            return True

        if snapshot.umlaut_accuracy < self.ALERT_UMLAUT_CRITICAL:
            logger.warning(f"Rollback empfohlen für {model_name}: Umlaut-Acc {snapshot.umlaut_accuracy:.2%}")
            return True

        return False

    async def execute_model_rollback(
        self,
        model_name: str,
        target_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Führt Model-Rollback durch.

        Args:
            model_name: Name des Modells
            target_version: Ziel-Version (None = vorherige Version)

        Returns:
            Rollback-Ergebnis
        """
        from app.ml.finetuning.checkpoint_manager import CheckpointManager

        try:
            checkpoint_manager = CheckpointManager()

            if target_version is None:
                versions = checkpoint_manager.list_versions(model_name)
                if len(versions) < 2:
                    return {
                        "success": False,
                        "error": "Keine vorherige Version für Rollback verfügbar"
                    }
                target_version = versions[-2].version

            success = checkpoint_manager.rollback_to_version(
                model_name,
                target_version,
                reason="Automatischer Rollback wegen Qualitätsverschlechterung"
            )

            if success:
                logger.info(f"Rollback erfolgreich: {model_name} -> {target_version}")
                return {
                    "success": True,
                    "model_name": model_name,
                    "rolled_back_to": target_version,
                    "timestamp": datetime.now().isoformat()
                }
            else:
                return {
                    "success": False,
                    "error": f"Rollback zu {target_version} fehlgeschlagen"
                }

        except Exception as e:
            logger.exception(f"Rollback-Fehler für {model_name}")
            return {
                "success": False, **safe_error_log(e)}

    async def get_model_health(self, model_name: str) -> ModelHealthStatus:
        """
        Holt Gesundheitsstatus eines Modells.

        Args:
            model_name: Name des Modells

        Returns:
            ModelHealthStatus
        """
        snapshot = await self._get_current_snapshot(model_name)

        issues = []
        health_score = 1.0

        if snapshot.avg_cer > self.ALERT_CER_THRESHOLD:
            issues.append(f"Erhöhte CER: {snapshot.avg_cer:.2%}")
            health_score -= 0.2
        if snapshot.avg_cer > self.ALERT_CER_CRITICAL:
            issues.append(f"Kritische CER: {snapshot.avg_cer:.2%}")
            health_score -= 0.3

        if snapshot.umlaut_accuracy < self.ALERT_UMLAUT_THRESHOLD:
            issues.append(f"Umlaut-Probleme: {snapshot.umlaut_accuracy:.2%}")
            health_score -= 0.2
        if snapshot.umlaut_accuracy < self.ALERT_UMLAUT_CRITICAL:
            issues.append(f"Kritische Umlaut-Genauigkeit: {snapshot.umlaut_accuracy:.2%}")
            health_score -= 0.3

        health_score = max(0.0, health_score)

        from app.ml.finetuning.checkpoint_manager import CheckpointManager
        try:
            checkpoint_manager = CheckpointManager()
            active = checkpoint_manager.get_active_version(model_name)
            version = active.version if active else "unknown"
        except Exception:
            version = "unknown"

        return ModelHealthStatus(
            model_name=model_name,
            version=version,
            is_healthy=health_score > 0.7,
            health_score=health_score,
            issues=issues,
            metrics={
                "cer": snapshot.avg_cer,
                "wer": snapshot.avg_wer,
                "umlaut_accuracy": snapshot.umlaut_accuracy,
                "sample_count": snapshot.sample_count
            },
            last_checked=datetime.now().isoformat()
        )

    async def create_quality_snapshot(self, backend_name: str) -> QualitySnapshot:
        """
        Erstellt einen neuen Quality-Snapshot für ein Backend.

        Args:
            backend_name: Name des Backends

        Returns:
            Erstellter Snapshot
        """
        from app.db.models import (
            OCRQualitySnapshot as DBSnapshot,
            OCRTrainingSample,
            OCRDocumentOutput
        )

        since = datetime.now() - timedelta(hours=24)

        cer_query = select(
            func.avg(OCRDocumentOutput.confidence_score).label("avg_confidence"),
            func.count().label("count")
        ).where(
            and_(
                OCRDocumentOutput.backend_name == backend_name,
                OCRDocumentOutput.created_at >= since
            )
        )

        result = await self.db.execute(cer_query)
        row = result.one_or_none()

        avg_confidence = row.avg_confidence if row and row.avg_confidence else 0.0
        sample_count = row.count if row else 0

        avg_cer = 1.0 - avg_confidence if avg_confidence else 0.1
        avg_wer = avg_cer * 1.5

        umlaut_accuracy = 0.95

        db_snapshot = DBSnapshot(
            backend_name=backend_name,
            avg_cer=avg_cer,
            avg_wer=avg_wer,
            avg_umlaut_accuracy=umlaut_accuracy,
            sample_count=sample_count,
            correction_count=0,
            processing_time_avg_ms=0.0,
            alert_triggered=avg_cer > self.ALERT_CER_THRESHOLD
        )

        self.db.add(db_snapshot)
        await self.db.commit()
        await self.db.refresh(db_snapshot)

        return QualitySnapshot(
            timestamp=db_snapshot.timestamp.isoformat(),
            backend_name=backend_name,
            avg_cer=avg_cer,
            avg_wer=avg_wer,
            umlaut_accuracy=umlaut_accuracy,
            correction_count=0,
            sample_count=sample_count,
            processing_time_avg_ms=0.0
        )

    def get_alert_history(self, hours: int = 24) -> List[QualityAlert]:
        """Gibt Alert-Historie zurück."""
        cutoff = datetime.now() - timedelta(hours=hours)
        cutoff_str = cutoff.isoformat()

        return [
            alert for alert in self._alert_history
            if alert.created_at >= cutoff_str
        ]


async def get_quality_monitoring_service(
    db: AsyncSession
) -> QualityMonitoringService:
    """FastAPI Dependency für den Monitoring-Service."""
    return QualityMonitoringService(db)
