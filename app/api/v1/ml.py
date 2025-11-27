# -*- coding: utf-8 -*-
"""
ML API Endpunkte.

Bietet REST-Zugriff auf:
- Drift Detection Status und Reports
- SHAP Erklärungen für Routing
- A/B Test Management
- ML Metriken

Feinpoliert und durchdacht - ML-Observability per API.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ml", tags=["ML"])


# =============================================================================
# Request/Response Models
# =============================================================================

class DriftStatusResponse(BaseModel):
    """Drift-Status Response."""
    reference_samples: int
    current_samples: int
    min_samples_required: int
    ready_for_detection: bool
    last_report: Optional[Dict[str, Any]] = None
    drift_threshold: float


class DriftReportResponse(BaseModel):
    """Drift-Report Response."""
    report_id: str
    timestamp: str
    overall_drift_score: float
    severity: str
    dataset_drift_detected: bool
    feature_drifts: List[Dict[str, Any]]
    prediction_drift: Optional[float]
    samples_reference: int
    samples_current: int
    recommendations: List[str]


class ExplainRoutingRequest(BaseModel):
    """Request für Routing-Erklärung."""
    document_id: str
    features: Dict[str, Any]
    selected_backend: str
    confidence: float
    all_probabilities: Dict[str, float]


class RoutingExplanationResponse(BaseModel):
    """Routing-Erklärung Response."""
    document_id: str
    selected_backend: str
    confidence: float
    top_contributions: List[Dict[str, Any]]
    alternative_backends: List[List[Any]]  # [(backend, probability), ...]
    decision_summary: str
    counterfactual: Optional[str] = None


class CreateExperimentRequest(BaseModel):
    """Request zum Erstellen eines Experiments."""
    name: str
    description: str = ""
    variants: List[Dict[str, Any]]
    allocation_method: str = "sticky"
    min_samples: int = 100
    duration_days: Optional[int] = None


class ExperimentResponse(BaseModel):
    """Experiment Response."""
    experiment_id: str
    name: str
    status: str
    variants: List[Dict[str, Any]]
    total_samples: int
    winner: Optional[str] = None
    significance_reached: bool


class RecordResultRequest(BaseModel):
    """Request zum Erfassen eines Experiment-Ergebnisses."""
    variant_name: str
    success: bool
    latency_ms: float
    accuracy: Optional[float] = None


class GlobalImportanceResponse(BaseModel):
    """Feature Importance Response."""
    features: Dict[str, float]


class MetricsResponse(BaseModel):
    """Metriken Response."""
    routing: Dict[str, Any]
    backends: Dict[str, Any]
    drift: Dict[str, Any]
    experiments: Dict[str, Any]


# =============================================================================
# Drift Detection Endpoints
# =============================================================================

@router.get("/drift/status", response_model=DriftStatusResponse)
async def get_drift_status() -> DriftStatusResponse:
    """
    Hole aktuellen Drift-Status.

    Returns:
        DriftStatusResponse mit aktuellem Status
    """
    try:
        from app.ml.drift_detector import get_drift_detector

        detector = get_drift_detector()
        status = detector.get_current_status()

        return DriftStatusResponse(**status)

    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Drift-Status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drift/detect", response_model=DriftReportResponse)
async def run_drift_detection() -> DriftReportResponse:
    """
    Führe Drift-Detection durch.

    Returns:
        DriftReportResponse mit Ergebnissen
    """
    try:
        from app.ml.drift_detector import get_drift_detector

        detector = get_drift_detector()
        report = detector.detect_drift()

        return DriftReportResponse(
            report_id=report.report_id,
            timestamp=report.timestamp.isoformat(),
            overall_drift_score=report.overall_drift_score,
            severity=report.severity.value,
            dataset_drift_detected=report.dataset_drift_detected,
            feature_drifts=[
                {
                    "feature_name": fd.feature_name,
                    "drift_score": fd.drift_score,
                    "p_value": fd.p_value,
                    "is_drifted": fd.is_drifted,
                }
                for fd in report.feature_drifts
            ],
            prediction_drift=report.prediction_drift,
            samples_reference=report.samples_reference,
            samples_current=report.samples_current,
            recommendations=report.recommendations,
        )

    except Exception as e:
        logger.error(f"Fehler bei Drift-Detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drift/history", response_model=List[DriftReportResponse])
async def get_drift_history(
    limit: int = Query(default=10, ge=1, le=100),
) -> List[DriftReportResponse]:
    """
    Hole Drift-History.

    Args:
        limit: Maximale Anzahl der Reports

    Returns:
        Liste der letzten Drift-Reports
    """
    try:
        from app.ml.drift_detector import get_drift_detector

        detector = get_drift_detector()
        history = detector.get_drift_history(limit=limit)

        return [
            DriftReportResponse(
                report_id=r.report_id,
                timestamp=r.timestamp.isoformat(),
                overall_drift_score=r.overall_drift_score,
                severity=r.severity.value,
                dataset_drift_detected=r.dataset_drift_detected,
                feature_drifts=[
                    {
                        "feature_name": fd.feature_name,
                        "drift_score": fd.drift_score,
                        "is_drifted": fd.is_drifted,
                    }
                    for fd in r.feature_drifts
                ],
                prediction_drift=r.prediction_drift,
                samples_reference=r.samples_reference,
                samples_current=r.samples_current,
                recommendations=r.recommendations,
            )
            for r in history
        ]

    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Drift-History: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/drift/reset")
async def reset_drift_reference() -> Dict[str, str]:
    """
    Setze Drift-Reference zurück.

    Verwende nach Modell-Retraining.

    Returns:
        Bestätigungsnachricht
    """
    try:
        from app.ml.drift_detector import get_drift_detector

        detector = get_drift_detector()
        detector.reset_reference_window()

        return {"message": "Reference-Fenster erfolgreich zurückgesetzt"}

    except Exception as e:
        logger.error(f"Fehler beim Reset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# SHAP Explainability Endpoints
# =============================================================================

@router.post("/explain/routing", response_model=RoutingExplanationResponse)
async def explain_routing_decision(
    request: ExplainRoutingRequest,
) -> RoutingExplanationResponse:
    """
    Erkläre eine Routing-Entscheidung.

    Args:
        request: Routing-Details

    Returns:
        RoutingExplanationResponse mit Erklärung
    """
    try:
        from app.ml.shap_explainer import get_shap_explainer

        explainer = get_shap_explainer()
        explanation = explainer.explain_routing(
            document_id=request.document_id,
            features=request.features,
            selected_backend=request.selected_backend,
            confidence=request.confidence,
            all_probabilities=request.all_probabilities,
        )

        return RoutingExplanationResponse(
            document_id=explanation.document_id,
            selected_backend=explanation.selected_backend,
            confidence=explanation.confidence,
            top_contributions=[
                {
                    "feature_name": fc.feature_name,
                    "feature_value": fc.feature_value,
                    "shap_value": fc.shap_value,
                    "contribution_percent": fc.contribution_percent,
                    "direction": fc.direction,
                    "explanation": fc.german_explanation,
                }
                for fc in explanation.top_contributions
            ],
            alternative_backends=explanation.alternative_backends,
            decision_summary=explanation.decision_summary,
            counterfactual=explanation.counterfactual,
        )

    except Exception as e:
        logger.error(f"Fehler bei Routing-Erklärung: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain/{document_id}", response_model=Optional[RoutingExplanationResponse])
async def get_routing_explanation(document_id: str) -> Optional[RoutingExplanationResponse]:
    """
    Hole gespeicherte Routing-Erklärung.

    Args:
        document_id: Dokument-ID

    Returns:
        Gespeicherte Erklärung oder None
    """
    try:
        from app.ml.shap_explainer import get_shap_explainer

        explainer = get_shap_explainer()
        explanation = explainer.get_explanation(document_id)

        if not explanation:
            raise HTTPException(
                status_code=404,
                detail=f"Keine Erklärung gefunden für Dokument {document_id}"
            )

        return RoutingExplanationResponse(
            document_id=explanation.document_id,
            selected_backend=explanation.selected_backend,
            confidence=explanation.confidence,
            top_contributions=[
                {
                    "feature_name": fc.feature_name,
                    "feature_value": fc.feature_value,
                    "shap_value": fc.shap_value,
                    "contribution_percent": fc.contribution_percent,
                    "direction": fc.direction,
                    "explanation": fc.german_explanation,
                }
                for fc in explanation.top_contributions
            ],
            alternative_backends=explanation.alternative_backends,
            decision_summary=explanation.decision_summary,
            counterfactual=explanation.counterfactual,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Erklärung: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/explain/importance", response_model=GlobalImportanceResponse)
async def get_global_feature_importance() -> GlobalImportanceResponse:
    """
    Hole globale Feature Importance.

    Returns:
        Feature Importance Scores
    """
    try:
        from app.ml.shap_explainer import get_shap_explainer

        explainer = get_shap_explainer()
        importance = explainer.get_global_importance()

        return GlobalImportanceResponse(features=importance)

    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Feature Importance: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# A/B Testing Endpoints
# =============================================================================

@router.post("/experiments", response_model=ExperimentResponse)
async def create_experiment(
    request: CreateExperimentRequest,
) -> ExperimentResponse:
    """
    Erstelle neues A/B Experiment.

    Args:
        request: Experiment-Konfiguration

    Returns:
        Erstelltes Experiment
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager

        manager = get_ab_test_manager()
        experiment = manager.create_experiment(
            name=request.name,
            description=request.description,
            variants=request.variants,
            allocation_method=request.allocation_method,
            min_samples=request.min_samples,
            duration_days=request.duration_days,
        )

        summary = experiment.get_summary()
        return ExperimentResponse(**summary)

    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Experiments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiments/{experiment_id}/start")
async def start_experiment(experiment_id: str) -> Dict[str, Any]:
    """
    Starte ein Experiment.

    Args:
        experiment_id: Experiment-ID

    Returns:
        Bestätigungsnachricht
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager

        manager = get_ab_test_manager()
        success = manager.start_experiment(experiment_id)

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Experiment konnte nicht gestartet werden"
            )

        return {"message": f"Experiment {experiment_id} gestartet"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Starten des Experiments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(experiment_id: str) -> ExperimentResponse:
    """
    Hole Experiment-Details.

    Args:
        experiment_id: Experiment-ID

    Returns:
        Experiment-Details
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager

        manager = get_ab_test_manager()
        experiment = manager.get_experiment(experiment_id)

        if not experiment:
            raise HTTPException(
                status_code=404,
                detail=f"Experiment {experiment_id} nicht gefunden"
            )

        summary = experiment.get_summary()
        return ExperimentResponse(**summary)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Experiments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/experiments", response_model=List[ExperimentResponse])
async def list_experiments(
    status: Optional[str] = Query(default=None),
) -> List[ExperimentResponse]:
    """
    Liste alle Experimente.

    Args:
        status: Optional Filter nach Status

    Returns:
        Liste der Experimente
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager, ExperimentStatus

        manager = get_ab_test_manager()

        status_filter = None
        if status:
            try:
                status_filter = ExperimentStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ungültiger Status: {status}"
                )

        experiments = manager.list_experiments(status=status_filter)

        return [
            ExperimentResponse(**exp.get_summary())
            for exp in experiments
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Auflisten der Experimente: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiments/{experiment_id}/record")
async def record_experiment_result(
    experiment_id: str,
    request: RecordResultRequest,
) -> Dict[str, str]:
    """
    Erfasse Experiment-Ergebnis.

    Args:
        experiment_id: Experiment-ID
        request: Ergebnis-Daten

    Returns:
        Bestätigungsnachricht
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager

        manager = get_ab_test_manager()
        manager.record_result(
            experiment_id=experiment_id,
            variant_name=request.variant_name,
            success=request.success,
            latency_ms=request.latency_ms,
            accuracy=request.accuracy,
        )

        return {"message": "Ergebnis erfasst"}

    except Exception as e:
        logger.error(f"Fehler beim Erfassen des Ergebnisses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/experiments/{experiment_id}/conclude")
async def conclude_experiment(experiment_id: str) -> Dict[str, Any]:
    """
    Schließe Experiment ab.

    Args:
        experiment_id: Experiment-ID

    Returns:
        Gewinner-Information
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager

        manager = get_ab_test_manager()
        winner = manager.conclude_experiment(experiment_id)

        return {
            "message": f"Experiment {experiment_id} abgeschlossen",
            "winner": winner,
        }

    except Exception as e:
        logger.error(f"Fehler beim Abschließen des Experiments: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Metrics Endpoints
# =============================================================================

@router.get("/metrics")
async def get_prometheus_metrics():
    """
    Hole Prometheus-Metriken.

    Returns:
        Metriken im Prometheus-Format
    """
    try:
        from app.ml.metrics import get_ml_metrics
        from fastapi.responses import Response

        metrics = get_ml_metrics()

        # Update GPU metrics before returning
        metrics.update_gpu_metrics()

        return Response(
            content=metrics.get_metrics(),
            media_type=metrics.get_content_type(),
        )

    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Metriken: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/summary", response_model=MetricsResponse)
async def get_metrics_summary() -> MetricsResponse:
    """
    Hole Metriken-Zusammenfassung.

    Returns:
        Zusammenfassung aller ML-Metriken
    """
    try:
        from app.ml.drift_detector import get_drift_detector
        from app.ml.ab_testing import get_ab_test_manager

        drift_detector = get_drift_detector()
        ab_manager = get_ab_test_manager()

        drift_status = drift_detector.get_current_status()
        active_experiments = ab_manager.get_active_experiments()

        return MetricsResponse(
            routing={
                "status": "active",
                "method": "ml_hybrid",
            },
            backends={
                "available": ["deepseek", "got_ocr", "surya", "donut", "tesseract"],
                "default": "deepseek",
            },
            drift={
                "ready": drift_status["ready_for_detection"],
                "last_score": (
                    drift_status["last_report"]["overall_drift_score"]
                    if drift_status["last_report"]
                    else None
                ),
                "samples": drift_status["current_samples"],
            },
            experiments={
                "active_count": len(active_experiments),
                "experiments": [
                    {"id": e.experiment_id, "name": e.name}
                    for e in active_experiments
                ],
            },
        )

    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Metriken-Zusammenfassung: {e}")
        raise HTTPException(status_code=500, detail=str(e))
