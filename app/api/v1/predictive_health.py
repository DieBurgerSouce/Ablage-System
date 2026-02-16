# -*- coding: utf-8 -*-
"""
Predictive Health API.

Bietet proaktive Systemüberwachung mit Vorhersagen:
- GPU VRAM Overflow Vorhersage
- Queue Overflow Vorhersage
- OCR Qualitaets-Degradation
- Proaktive Alerts

Vision 2.0 Feature: Predictive Maintenance (Phase 5)
Feinpoliert und durchdacht.
"""

import logging
from typing import Dict, List, Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_current_active_user, get_current_superuser
from app.db.models import User
from app.services.predictive.system_health_predictor import (
    MetricType,
    PredictionResult,
    SystemHealthPredictor,
    get_health_predictor,
)
from app.services.predictive.ocr_quality_forecaster import (
    DegradationAlert,
    OCRBackend,
    OCRQualityForecaster,
    QualityMetric,
    get_quality_forecaster,
)
from app.services.predictive.predictive_alerts_service import (
    PredictiveAlert,
    PredictiveAlertSeverity,
    PredictiveAlertType,
    PredictiveAlertsService,
    get_predictive_alerts_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health/predictions", tags=["Predictive Health"])


# ============================================================================
# Request/Response Models
# ============================================================================

class PredictionResponse(BaseModel):
    """Response für eine einzelne Vorhersage."""
    metric: str
    current_value: float
    predicted_value: float
    threshold: float
    eta_minutes: Optional[float]
    trend_per_minute: float
    severity: str
    recommendation: str
    confidence: float
    prediction_time: str


class DegradationAlertResponse(BaseModel):
    """Response für OCR Degradation Alert."""
    backend: str
    metric: str
    current_value: float
    threshold: float
    trend_per_day: float
    days_to_threshold: Optional[float]
    severity: str
    recommendation: str
    confidence: float


class PredictiveAlertResponse(BaseModel):
    """Response für Predictive Alert."""
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
    acknowledged: bool


class AlertStatsResponse(BaseModel):
    """Response für Alert-Statistiken."""
    total_active: int
    by_severity: Dict[str, int]
    by_type: Dict[str, int]
    by_source: Dict[str, int]
    history_count: int


class QualitySummaryResponse(BaseModel):
    """Response für OCR Quality Summary."""
    backend: str
    metrics: Dict[str, Dict[str, float]]


# Type alias for metadata values
MetadataValue = Union[str, int, float, bool, None]
MetadataDict = Dict[str, MetadataValue]


class RecordMetricRequest(BaseModel):
    """Request zum Aufzeichnen einer Metrik."""
    value: float = Field(..., description="Metrik-Wert")
    metadata: Optional[MetadataDict] = Field(default=None)


class RecordQualityRequest(BaseModel):
    """Request zum Aufzeichnen von OCR-Qualitaet."""
    cer: Optional[float] = Field(None, ge=0, le=1, description="Character Error Rate")
    wer: Optional[float] = Field(None, ge=0, le=1, description="Word Error Rate")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Durchschnittliche Confidence")
    umlaut_accuracy: Optional[float] = Field(None, ge=0, le=1, description="Umlaut-Genauigkeit")
    document_count: int = Field(1, ge=1, description="Anzahl Dokumente")


# ============================================================================
# System Health Predictions
# ============================================================================

@router.get("", response_model=List[PredictionResponse])
async def get_all_predictions(
    current_user: User = Depends(get_current_active_user),
) -> List[PredictionResponse]:
    """
    Gibt alle aktuellen System-Vorhersagen zurück.

    Beinhaltet GPU VRAM, Queue-Tiefen und Disk-Auslastung.
    """
    predictor = get_health_predictor()
    predictions = await predictor.get_all_predictions()

    return [
        PredictionResponse(**pred.to_dict())
        for pred in predictions
    ]


@router.get("/gpu", response_model=Optional[PredictionResponse])
async def get_gpu_prediction(
    current_user: User = Depends(get_current_active_user),
) -> Optional[PredictionResponse]:
    """
    Gibt GPU VRAM Overflow-Vorhersage zurück.

    Prognostiziert wann VRAM-Limit erreicht wird basierend auf aktuellem Trend.
    """
    predictor = get_health_predictor()
    prediction = await predictor.predict_gpu_vram_overflow()

    if prediction:
        return PredictionResponse(**prediction.to_dict())
    return None


@router.get("/queues", response_model=List[PredictionResponse])
async def get_queue_predictions(
    current_user: User = Depends(get_current_active_user),
) -> List[PredictionResponse]:
    """
    Gibt Queue Overflow-Vorhersagen zurück.

    Prognostiziert für alle bekannten Queues.
    """
    predictor = get_health_predictor()
    predictions: List[PredictionResponse] = []

    # Hole alle bekannten Queues
    for queue_name in predictor._queue_histories.keys():
        pred = await predictor.predict_queue_overflow(queue_name)
        if pred:
            predictions.append(PredictionResponse(**pred.to_dict()))

    return predictions


@router.get("/disk", response_model=Optional[PredictionResponse])
async def get_disk_prediction(
    current_user: User = Depends(get_current_active_user),
) -> Optional[PredictionResponse]:
    """
    Gibt Disk Space Exhaustion-Vorhersage zurück.
    """
    predictor = get_health_predictor()
    prediction = await predictor.predict_disk_exhaustion()

    if prediction:
        return PredictionResponse(**prediction.to_dict())
    return None


# ============================================================================
# OCR Quality Forecasting
# ============================================================================

@router.get("/ocr/degradation", response_model=List[DegradationAlertResponse])
async def get_ocr_degradation_alerts(
    backend: Optional[str] = Query(None, description="Filter nach Backend"),
    current_user: User = Depends(get_current_active_user),
) -> List[DegradationAlertResponse]:
    """
    Gibt OCR Qualitaets-Degradation Alerts zurück.

    Erkennt wenn CER/WER steigt oder Confidence faellt.
    """
    forecaster = get_quality_forecaster()

    if backend:
        try:
            backend_enum = OCRBackend(backend)
            alerts = await forecaster.detect_degradation(backend_enum)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekanntes Backend: {backend}. Erlaubt: {[b.value for b in OCRBackend]}"
            )
    else:
        alerts = await forecaster.get_all_degradation_alerts()

    return [
        DegradationAlertResponse(**alert.to_dict())
        for alert in alerts
    ]


@router.get("/ocr/summary/{backend}", response_model=QualitySummaryResponse)
async def get_ocr_quality_summary(
    backend: str,
    current_user: User = Depends(get_current_active_user),
) -> QualitySummaryResponse:
    """
    Gibt Qualitaets-Zusammenfassung für ein OCR-Backend zurück.

    Beinhaltet aktuelle Werte und 24h-Statistiken.
    """
    try:
        backend_enum = OCRBackend(backend)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekanntes Backend: {backend}"
        )

    forecaster = get_quality_forecaster()
    summary = forecaster.get_quality_summary(backend_enum)

    return QualitySummaryResponse(**summary)


# ============================================================================
# Proactive Alerts
# ============================================================================

@router.get("/alerts", response_model=List[PredictiveAlertResponse])
async def get_predictive_alerts(
    severity: Optional[str] = Query(None, description="Filter nach Severity"),
    alert_type: Optional[str] = Query(None, description="Filter nach Typ"),
    current_user: User = Depends(get_current_active_user),
) -> List[PredictiveAlertResponse]:
    """
    Gibt alle aktiven proaktiven Alerts zurück.

    Kombiniert System Health und OCR Quality Alerts.
    """
    service = get_predictive_alerts_service()

    severity_filter = None
    if severity:
        try:
            severity_filter = PredictiveAlertSeverity(severity)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekannte Severity: {severity}"
            )

    type_filter = None
    if alert_type:
        try:
            type_filter = PredictiveAlertType(alert_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekannter Alert-Typ: {alert_type}"
            )

    alerts = service.get_active_alerts(severity_filter, type_filter)

    return [
        PredictiveAlertResponse(**alert.to_dict())
        for alert in alerts
    ]


@router.post("/alerts/generate", response_model=List[PredictiveAlertResponse])
async def generate_predictive_alerts(
    current_user: User = Depends(get_current_active_user),
) -> List[PredictiveAlertResponse]:
    """
    Generiert neue proaktive Alerts basierend auf aktuellen Vorhersagen.

    Triggert Analyse aller Metriken und erstellt Alerts bei Problemen.
    """
    service = get_predictive_alerts_service()
    new_alerts = await service.generate_all_alerts()

    logger.info(
        "predictive_alerts_generated_via_api",
        count=len(new_alerts),
        user=current_user.email
    )

    return [
        PredictiveAlertResponse(**alert.to_dict())
        for alert in new_alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge", status_code=status.HTTP_204_NO_CONTENT)
async def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Markiert einen Alert als bestätigt/gelesen.
    """
    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Alert-ID"
        )

    service = get_predictive_alerts_service()
    success = service.acknowledge_alert(alert_uuid, current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden"
        )


@router.delete("/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_alert(
    alert_id: str,
    current_user: User = Depends(get_current_active_user),
) -> None:
    """
    Verwirft einen Alert.
    """
    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungültige Alert-ID"
        )

    service = get_predictive_alerts_service()
    success = service.dismiss_alert(alert_uuid)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert nicht gefunden"
        )


@router.get("/alerts/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    current_user: User = Depends(get_current_active_user),
) -> AlertStatsResponse:
    """
    Gibt Statistiken über proaktive Alerts zurück.
    """
    service = get_predictive_alerts_service()
    stats = service.get_alert_stats()

    return AlertStatsResponse(**stats)


# ============================================================================
# Metric Recording (Admin)
# ============================================================================

@router.post("/metrics/{metric_type}/record", status_code=status.HTTP_204_NO_CONTENT)
async def record_metric(
    metric_type: str,
    request: RecordMetricRequest,
    current_user: User = Depends(get_current_superuser),
) -> None:
    """
    Zeichnet einen Metrik-Wert auf (Admin-only).

    Wird normalerweise von Celery-Tasks aufgerufen.
    """
    try:
        metric = MetricType(metric_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekannter Metrik-Typ: {metric_type}. Erlaubt: {[m.value for m in MetricType]}"
        )

    predictor = get_health_predictor()
    predictor.record_metric(metric, request.value, request.metadata)


@router.post("/metrics/queue/{queue_name}/record", status_code=status.HTTP_204_NO_CONTENT)
async def record_queue_metric(
    queue_name: str,
    depth: int = Query(..., ge=0, description="Queue-Tiefe"),
    current_user: User = Depends(get_current_superuser),
) -> None:
    """
    Zeichnet Queue-Tiefe auf (Admin-only).
    """
    predictor = get_health_predictor()
    predictor.record_queue_metric(queue_name, depth)


@router.post("/ocr/{backend}/record", status_code=status.HTTP_204_NO_CONTENT)
async def record_ocr_quality(
    backend: str,
    request: RecordQualityRequest,
    current_user: User = Depends(get_current_superuser),
) -> None:
    """
    Zeichnet OCR-Qualitaets-Metriken auf (Admin-only).
    """
    try:
        backend_enum = OCRBackend(backend)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unbekanntes Backend: {backend}"
        )

    forecaster = get_quality_forecaster()
    forecaster.record_quality(
        backend=backend_enum,
        cer=request.cer,
        wer=request.wer,
        confidence=request.confidence,
        umlaut_accuracy=request.umlaut_accuracy,
        document_count=request.document_count
    )


# ============================================================================
# Maintenance (Admin)
# ============================================================================

@router.post("/alerts/cleanup", status_code=status.HTTP_204_NO_CONTENT)
async def cleanup_old_alerts(
    max_age_hours: int = Query(24, ge=1, le=168, description="Maximales Alter in Stunden"),
    current_user: User = Depends(get_current_superuser),
) -> None:
    """
    Entfernt alte Alerts (Admin-only).
    """
    service = get_predictive_alerts_service()
    removed = service.clear_old_alerts(max_age_hours)

    logger.info(
        "old_alerts_cleaned_up",
        removed_count=removed,
        max_age_hours=max_age_hours,
        by_user=current_user.email
    )


@router.delete("/metrics/history", status_code=status.HTTP_204_NO_CONTENT)
async def clear_metric_history(
    metric_type: Optional[str] = Query(None, description="Spezifischer Metrik-Typ"),
    current_user: User = Depends(get_current_superuser),
) -> None:
    """
    Löscht Metrik-History (Admin-only).
    """
    predictor = get_health_predictor()

    if metric_type:
        try:
            metric = MetricType(metric_type)
            predictor.clear_history(metric)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unbekannter Metrik-Typ: {metric_type}"
            )
    else:
        predictor.clear_history()

    logger.info(
        "metric_history_cleared",
        metric_type=metric_type or "all",
        by_user=current_user.email
    )
