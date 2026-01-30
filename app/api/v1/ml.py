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

import structlog
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends, Request
from pydantic import BaseModel, Field, field_validator

from app.api.dependencies import (
    get_current_active_user,
    get_current_superuser,
    check_rate_limit,
)
from app.db.models import User
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)

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
    document_id: str = Field(..., min_length=1, max_length=100, description="Dokument-ID")
    features: Dict[str, float] = Field(..., description="Feature-Werte für das Dokument")
    selected_backend: str = Field(..., min_length=1, max_length=50, description="Gewähltes Backend")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Konfidenz der Entscheidung")
    all_probabilities: Dict[str, float] = Field(..., description="Wahrscheinlichkeiten für alle Backends")

    @field_validator("all_probabilities")
    @classmethod
    def validate_probabilities(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validiere dass Wahrscheinlichkeiten gültig sind."""
        for backend, prob in v.items():
            if not 0.0 <= prob <= 1.0:
                raise ValueError(f"Wahrscheinlichkeit für {backend} muss zwischen 0 und 1 liegen")
        return v


class FeatureContribution(BaseModel):
    """Einzelner Feature-Beitrag zur Entscheidung."""
    feature_name: str
    feature_value: float
    shap_value: float
    contribution_percent: float
    direction: str
    explanation: str


class RoutingExplanationResponse(BaseModel):
    """Routing-Erklärung Response."""
    document_id: str
    selected_backend: str
    confidence: float
    top_contributions: List[FeatureContribution]
    alternative_backends: List[Tuple[str, float]] = Field(
        ..., description="Alternative Backends mit Wahrscheinlichkeiten [(backend, probability), ...]"
    )
    decision_summary: str
    counterfactual: Optional[str] = None


class VariantConfig(BaseModel):
    """Konfiguration einer Experiment-Variante."""
    name: str = Field(..., min_length=1, max_length=50, description="Name der Variante")
    backend: str = Field(..., min_length=1, max_length=50, description="Backend für diese Variante")
    weight: float = Field(default=1.0, ge=0.0, le=100.0, description="Gewichtung der Variante")
    config: Dict[str, float] = Field(default_factory=dict, description="Zusätzliche Konfiguration")


class CreateExperimentRequest(BaseModel):
    """Request zum Erstellen eines Experiments."""
    name: str = Field(..., min_length=1, max_length=100, description="Name des Experiments")
    description: str = Field(default="", max_length=500, description="Beschreibung")
    variants: List[VariantConfig] = Field(..., min_length=2, max_length=10, description="Varianten")
    allocation_method: str = Field(
        default="sticky",
        description="Allokationsmethode: sticky, round_robin, weighted"
    )
    min_samples: int = Field(default=100, ge=10, le=100000, description="Minimale Samples pro Variante")
    duration_days: Optional[int] = Field(default=None, ge=1, le=365, description="Laufzeit in Tagen")

    @field_validator("allocation_method")
    @classmethod
    def validate_allocation_method(cls, v: str) -> str:
        """Validiere Allokationsmethode."""
        valid_methods = {"sticky", "round_robin", "weighted"}
        if v not in valid_methods:
            raise ValueError(f"Ungültige Allokationsmethode. Erlaubt: {valid_methods}")
        return v


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
    variant_name: str = Field(..., min_length=1, max_length=50, description="Name der Variante")
    success: bool = Field(..., description="Ob die Verarbeitung erfolgreich war")
    latency_ms: float = Field(..., ge=0.0, le=600000.0, description="Latenz in Millisekunden")
    accuracy: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="OCR-Genauigkeit")


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
async def get_drift_status(
    request: Request,
    current_user: User = Depends(check_rate_limit),
) -> DriftStatusResponse:
    """
    Hole aktuellen Drift-Status.

    Erfordert Authentifizierung.

    Returns:
        DriftStatusResponse mit aktuellem Status
    """
    try:
        from app.ml.drift_detector import get_drift_detector

        detector = get_drift_detector()
        status = detector.get_current_status()

        return DriftStatusResponse(**status)

    except Exception as e:
        logger.error(
            "drift_status_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Drift-Status konnte nicht abgerufen werden. Bitte später erneut versuchen."
        )


@router.post("/drift/detect", response_model=DriftReportResponse)
async def run_drift_detection(
    request: Request,
    current_user: User = Depends(check_rate_limit),
) -> DriftReportResponse:
    """
    Führe Drift-Detection durch.

    Erfordert Authentifizierung.

    Returns:
        DriftReportResponse mit Ergebnissen
    """
    try:
        from app.ml.drift_detector import get_drift_detector

        detector = get_drift_detector()
        report = detector.detect_drift()

        logger.info(
            "drift_detection_durchgefuehrt",
            user_id=str(current_user.id),
            drift_score=report.overall_drift_score,
            severity=report.severity.value,
        )

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
        logger.error(
            "drift_detection_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Drift-Detection fehlgeschlagen. Bitte später erneut versuchen."
        )


@router.get("/drift/history", response_model=List[DriftReportResponse])
async def get_drift_history(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(check_rate_limit),
) -> List[DriftReportResponse]:
    """
    Hole Drift-History.

    Erfordert Authentifizierung.

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
        logger.error(
            "drift_history_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Drift-History konnte nicht abgerufen werden. Bitte später erneut versuchen."
        )


@router.post("/drift/reset")
async def reset_drift_reference(
    request: Request,
    admin_user: User = Depends(get_current_superuser),
) -> Dict[str, str]:
    """
    Setze Drift-Reference zurück.

    Verwende nach Modell-Retraining.
    **Nur für Administratoren.**

    Returns:
        Bestätigungsnachricht
    """
    try:
        from app.ml.drift_detector import get_drift_detector

        detector = get_drift_detector()
        detector.reset_reference_window()

        logger.info(
            "drift_reference_zurueckgesetzt",
            admin_user_id=str(admin_user.id),
        )

        return {"message": "Reference-Fenster erfolgreich zurückgesetzt"}

    except Exception as e:
        logger.error(
            "drift_reset_fehler",
            admin_user_id=str(admin_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Drift-Reset fehlgeschlagen. Bitte später erneut versuchen."
        )


# =============================================================================
# SHAP Explainability Endpoints
# =============================================================================

@router.post("/explain/routing", response_model=RoutingExplanationResponse)
async def explain_routing_decision(
    request: Request,
    body: ExplainRoutingRequest,
    current_user: User = Depends(check_rate_limit),
) -> RoutingExplanationResponse:
    """
    Erkläre eine Routing-Entscheidung.

    Erfordert Authentifizierung.

    Args:
        request: Routing-Details

    Returns:
        RoutingExplanationResponse mit Erklärung
    """
    try:
        from app.ml.shap_explainer import get_shap_explainer

        explainer = get_shap_explainer()
        explanation = explainer.explain_routing(
            document_id=body.document_id,
            features=body.features,
            selected_backend=body.selected_backend,
            confidence=body.confidence,
            all_probabilities=body.all_probabilities,
        )

        return RoutingExplanationResponse(
            document_id=explanation.document_id,
            selected_backend=explanation.selected_backend,
            confidence=explanation.confidence,
            top_contributions=[
                FeatureContribution(
                    feature_name=fc.feature_name,
                    feature_value=fc.feature_value,
                    shap_value=fc.shap_value,
                    contribution_percent=fc.contribution_percent,
                    direction=fc.direction,
                    explanation=fc.german_explanation,
                )
                for fc in explanation.top_contributions
            ],
            alternative_backends=explanation.alternative_backends,
            decision_summary=explanation.decision_summary,
            counterfactual=explanation.counterfactual,
        )

    except Exception as e:
        logger.error(
            "routing_erklaerung_fehler",
            user_id=str(current_user.id),
            document_id=body.document_id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Routing-Erklärung konnte nicht erstellt werden. Bitte später erneut versuchen."
        )


@router.get("/explain/{document_id}", response_model=RoutingExplanationResponse)
async def get_routing_explanation(
    request: Request,
    document_id: str,
    current_user: User = Depends(check_rate_limit),
) -> RoutingExplanationResponse:
    """
    Hole gespeicherte Routing-Erklärung.

    Erfordert Authentifizierung.

    Args:
        document_id: Dokument-ID

    Returns:
        Gespeicherte Erklärung
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
                FeatureContribution(
                    feature_name=fc.feature_name,
                    feature_value=fc.feature_value,
                    shap_value=fc.shap_value,
                    contribution_percent=fc.contribution_percent,
                    direction=fc.direction,
                    explanation=fc.german_explanation,
                )
                for fc in explanation.top_contributions
            ],
            alternative_backends=explanation.alternative_backends,
            decision_summary=explanation.decision_summary,
            counterfactual=explanation.counterfactual,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "erklaerung_abruf_fehler",
            user_id=str(current_user.id),
            document_id=document_id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Erklärung konnte nicht abgerufen werden. Bitte später erneut versuchen."
        )


@router.get("/explain/importance", response_model=GlobalImportanceResponse)
async def get_global_feature_importance(
    request: Request,
    current_user: User = Depends(check_rate_limit),
) -> GlobalImportanceResponse:
    """
    Hole globale Feature Importance.

    Erfordert Authentifizierung.

    Returns:
        Feature Importance Scores
    """
    try:
        from app.ml.shap_explainer import get_shap_explainer

        explainer = get_shap_explainer()
        importance = explainer.get_global_importance()

        return GlobalImportanceResponse(features=importance)

    except Exception as e:
        logger.error(
            "feature_importance_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Feature Importance konnte nicht abgerufen werden. Bitte später erneut versuchen."
        )


# =============================================================================
# A/B Testing Endpoints
# =============================================================================

@router.post("/experiments", response_model=ExperimentResponse)
async def create_experiment(
    request: Request,
    body: CreateExperimentRequest,
    current_user: User = Depends(check_rate_limit),
) -> ExperimentResponse:
    """
    Erstelle neues A/B Experiment.

    Erfordert Authentifizierung.

    Args:
        request: Experiment-Konfiguration

    Returns:
        Erstelltes Experiment
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager

        manager = get_ab_test_manager()

        # Konvertiere VariantConfig zu Dict für den Manager
        variants_dict = [
            {
                "name": v.name,
                "backend": v.backend,
                "weight": v.weight,
                "config": v.config,
            }
            for v in body.variants
        ]

        experiment = manager.create_experiment(
            name=body.name,
            description=body.description,
            variants=variants_dict,
            allocation_method=body.allocation_method,
            min_samples=body.min_samples,
            duration_days=body.duration_days,
        )

        logger.info(
            "experiment_erstellt",
            user_id=str(current_user.id),
            experiment_name=body.name,
            variant_count=len(body.variants),
        )

        summary = experiment.get_summary()
        return ExperimentResponse(**summary)

    except ValueError as e:
        # SECURITY FIX 28-26: Generische Fehlermeldung
        raise HTTPException(status_code=400, detail="Ungueltige Experiment-Konfiguration.")
    except Exception as e:
        logger.error(
            "experiment_erstellung_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Experiment konnte nicht erstellt werden. Bitte später erneut versuchen."
        )


@router.post("/experiments/{experiment_id}/start")
async def start_experiment(
    request: Request,
    experiment_id: str,
    admin_user: User = Depends(get_current_superuser),
) -> Dict[str, Any]:
    """
    Starte ein Experiment.

    **Nur für Administratoren.**

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
                detail="Experiment konnte nicht gestartet werden. Prüfen Sie den Status."
            )

        logger.info(
            "experiment_gestartet",
            admin_user_id=str(admin_user.id),
            experiment_id=experiment_id,
        )

        return {"message": f"Experiment {experiment_id} gestartet"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "experiment_start_fehler",
            admin_user_id=str(admin_user.id),
            experiment_id=experiment_id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Experiment konnte nicht gestartet werden. Bitte später erneut versuchen."
        )


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    request: Request,
    experiment_id: str,
    current_user: User = Depends(get_current_superuser),  # Y.4 SECURITY FIX: Admin only
) -> ExperimentResponse:
    """
    Hole Experiment-Details (Admin only).

    **REQUIRES ADMIN AUTHENTICATION**

    Args:
        experiment_id: Experiment-ID

    Returns:
        Experiment-Details

    Raises:
        403: Wenn Benutzer kein Admin ist
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
        logger.error(
            "experiment_abruf_fehler",
            user_id=str(current_user.id),
            experiment_id=experiment_id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Experiment konnte nicht abgerufen werden. Bitte später erneut versuchen."
        )


@router.get("/experiments", response_model=List[ExperimentResponse])
async def list_experiments(
    request: Request,
    status: Optional[str] = Query(default=None),
    current_user: User = Depends(get_current_superuser),  # Y.4 SECURITY FIX: Admin only
) -> List[ExperimentResponse]:
    """
    Liste alle Experimente.

    Erfordert Authentifizierung.

    Args:
        status: Optional Filter nach Status (draft, running, completed, stopped)

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
                valid_statuses = [s.value for s in ExperimentStatus]
                raise HTTPException(
                    status_code=400,
                    detail=f"Ungültiger Status: {status}. Erlaubt: {valid_statuses}"
                )

        experiments = manager.list_experiments(status=status_filter)

        return [
            ExperimentResponse(**exp.get_summary())
            for exp in experiments
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "experiment_liste_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Experimente konnten nicht aufgelistet werden. Bitte später erneut versuchen."
        )


@router.post("/experiments/{experiment_id}/record")
async def record_experiment_result(
    request: Request,
    experiment_id: str,
    body: RecordResultRequest,
    current_user: User = Depends(check_rate_limit),
) -> Dict[str, str]:
    """
    Erfasse Experiment-Ergebnis.

    Erfordert Authentifizierung.

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
            variant_name=body.variant_name,
            success=body.success,
            latency_ms=body.latency_ms,
            accuracy=body.accuracy,
        )

        return {"message": "Ergebnis erfasst"}

    except ValueError as e:
        # SECURITY FIX 28-26: Generische Fehlermeldung
        raise HTTPException(status_code=400, detail="Ungueltige Experiment-Ergebnisdaten.")
    except Exception as e:
        logger.error(
            "experiment_ergebnis_fehler",
            user_id=str(current_user.id),
            experiment_id=experiment_id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Ergebnis konnte nicht erfasst werden. Bitte später erneut versuchen."
        )


@router.post("/experiments/{experiment_id}/conclude")
async def conclude_experiment(
    request: Request,
    experiment_id: str,
    admin_user: User = Depends(get_current_superuser),
) -> Dict[str, Any]:
    """
    Schließe Experiment ab.

    **Nur für Administratoren.**

    Args:
        experiment_id: Experiment-ID

    Returns:
        Gewinner-Information
    """
    try:
        from app.ml.ab_testing import get_ab_test_manager

        manager = get_ab_test_manager()
        winner = manager.conclude_experiment(experiment_id)

        logger.info(
            "experiment_abgeschlossen",
            admin_user_id=str(admin_user.id),
            experiment_id=experiment_id,
            winner=winner,
        )

        return {
            "message": f"Experiment {experiment_id} abgeschlossen",
            "winner": winner,
        }

    except ValueError as e:
        # SECURITY FIX 28-26: Generische Fehlermeldung
        raise HTTPException(status_code=400, detail="Experiment-Abschluss fehlgeschlagen.")
    except Exception as e:
        logger.error(
            "experiment_abschluss_fehler",
            admin_user_id=str(admin_user.id),
            experiment_id=experiment_id,
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Experiment konnte nicht abgeschlossen werden. Bitte später erneut versuchen."
        )


# =============================================================================
# Metrics Endpoints
# =============================================================================

@router.get("/metrics")
async def get_prometheus_metrics(
    request: Request,
    current_user: User = Depends(check_rate_limit),
):
    """
    Hole Prometheus-Metriken.

    Erfordert Authentifizierung.

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
        logger.error(
            "metriken_abruf_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Metriken konnten nicht abgerufen werden. Bitte später erneut versuchen."
        )


@router.get("/metrics/summary", response_model=MetricsResponse)
async def get_metrics_summary(
    request: Request,
    current_user: User = Depends(check_rate_limit),
) -> MetricsResponse:
    """
    Hole Metriken-Zusammenfassung.

    Erfordert Authentifizierung.

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
        logger.error(
            "metriken_zusammenfassung_fehler",
            user_id=str(current_user.id),
            **safe_error_log(e),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Metriken-Zusammenfassung konnte nicht abgerufen werden. Bitte später erneut versuchen."
        )
