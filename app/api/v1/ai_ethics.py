"""
AI Ethics API Endpoints

REST API fuer KI-Ethik-Layer:
- Bias-Detection
- Explainability
- Fairness-Metriken
- Ethical Guardrails

Feinpoliert und durchdacht - Enterprise AI Ethics.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, get_current_company_id
from app.services.ai_ethics.bias_detector import BiasDetector
from app.services.ai_ethics.explainability_service import ExplainabilityService
from app.services.ai_ethics.ethical_guardrails import EthicalGuardrails
from app.core.safe_errors import safe_error_detail, safe_error_log

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/ai-ethics", tags=["AI Ethics"])


# =============================================================================
# Schemas
# =============================================================================


class GuardrailCheckRequest(BaseModel):
    """Request-Schema fuer Guardrail-Check."""

    action_type: str = Field(..., min_length=3, max_length=100, description="Aktionstyp")
    parameters: Dict[str, Any] = Field(..., description="Aktionsparameter")


# =============================================================================
# AI Ethics Endpoints
# =============================================================================


@router.get(
    "/dashboard",
    response_model=Dict[str, Any],
    summary="AI Ethics Dashboard",
    description="Uebersicht ueber AI Ethics Metriken"
)
async def get_dashboard(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Holt AI Ethics Dashboard.

    **Enthaelt:**
    - Bias-Report Summary
    - Explainability Coverage
    - Guardrail Stats
    - Fairness Score

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ai_ethics.get_dashboard",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    try:
        # Bias Report
        bias_detector = BiasDetector()
        bias_report = await bias_detector.detect_bias(company_id, db)

        # Dashboard-Daten
        dashboard = {
            "fairness_score": bias_report.overall_fairness,
            "bias_dimensions": len(bias_report.dimensions),
            "critical_bias": sum(
                1 for d in bias_report.dimensions if d.fairness_score < 0.7
            ),
            "recommendations": bias_report.recommendations[:3],  # Top 3
            "last_updated": bias_report.generated_at.isoformat(),
        }

        return dashboard
    except Exception as e:
        logger.error(
            "ai_ethics.dashboard_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden des AI Ethics Dashboards",
        )


@router.get(
    "/bias-report",
    response_model=Dict[str, Any],
    summary="Bias-Report",
    description="Vollstaendiger Bias-Report fuer Unternehmen"
)
async def get_bias_report(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Holt Bias-Report.

    **Prueft Bias in:**
    - Entity-Typ (customer vs. supplier)
    - Risk-Score-Verteilung
    - Beziehungsdauer (neu vs. etabliert)

    **Fairness-Score:**
    - 1.0 = komplett fair
    - 0.85-0.99 = akzeptabel
    - < 0.85 = problematisch
    - < 0.70 = kritisch

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ai_ethics.get_bias_report",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    bias_detector = BiasDetector()

    try:
        report = await bias_detector.detect_bias(company_id, db)
        return report.to_dict()
    except Exception as e:
        logger.error(
            "ai_ethics.bias_report_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erstellen des Bias-Reports",
        )


@router.get(
    "/explain/{decision_type}/{decision_id}",
    response_model=Dict[str, Any],
    summary="Erklaerung",
    description="Erklaert KI-Entscheidung"
)
async def explain_decision(
    decision_type: str,
    decision_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Erklaert KI-Entscheidung.

    **Unterstuetzte Decision-Types:**
    - **risk_score**: Risk Score Berechnung fuer Entity
    - **document_classification**: Dokument-Klassifikation
    - **auto_approval**: Automatische Freigabe-Entscheidung

    **Erklaerung enthaelt:**
    - Zusammenfassung in Deutsch
    - Einzelne Faktoren mit Gewichtung
    - Impact (positive/negative/neutral)
    - Konfidenz der Entscheidung
    - Alternative Ansaetze

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ai_ethics.explain_decision",
        decision_type=decision_type,
        decision_id=str(decision_id),
        user_id=str(current_user.id),
    )

    # Validiere Decision-Type
    valid_types = ["risk_score", "document_classification", "auto_approval"]
    if decision_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Decision-Type. Erlaubt: {', '.join(valid_types)}",
        )

    service = ExplainabilityService()

    try:
        explanation = await service.explain_decision(decision_id, decision_type, db)

        if not explanation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Entscheidung nicht gefunden",
            )

        return explanation.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "ai_ethics.explain_failed",
            decision_type=decision_type,
            decision_id=str(decision_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Erklären der Entscheidung",
        )


@router.get(
    "/fairness-metrics",
    response_model=Dict[str, Any],
    summary="Fairness-Metriken",
    description="Allgemeine Fairness-Metriken fuer AI-Systeme"
)
async def get_fairness_metrics(
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Holt Fairness-Metriken.

    **Metriken:**
    - Overall Fairness Score
    - Bias pro Dimension
    - Anzahl betroffener Entities
    - Trend (improving/stable/degrading)

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ai_ethics.get_fairness_metrics",
        user_id=str(current_user.id),
        company_id=str(company_id),
    )

    bias_detector = BiasDetector()

    try:
        report = await bias_detector.detect_bias(company_id, db)

        # Calculate trend based on historical bias reports
        from app.db.models import BiasReport as BiasReportModel
        from sqlalchemy import select
        from datetime import timedelta

        trend = "stable"
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        # Get historical fairness scores from last 7 days
        history_query = select(BiasReportModel.overall_fairness).where(
            BiasReportModel.company_id == company_id,
            BiasReportModel.created_at >= seven_days_ago,
        ).order_by(BiasReportModel.created_at.asc())

        history_result = await db.execute(history_query)
        historical_scores = [row[0] for row in history_result.fetchall()]

        if len(historical_scores) >= 2:
            # Calculate trend from first half vs second half average
            mid = len(historical_scores) // 2
            first_half_avg = sum(historical_scores[:mid]) / mid
            second_half_avg = sum(historical_scores[mid:]) / (len(historical_scores) - mid)
            delta = second_half_avg - first_half_avg

            if delta > 0.02:
                trend = "improving"
            elif delta < -0.02:
                trend = "degrading"

        metrics = {
            "overall_fairness": report.overall_fairness,
            "fairness_level": (
                "excellent" if report.overall_fairness >= 0.95
                else "good" if report.overall_fairness >= 0.85
                else "acceptable" if report.overall_fairness >= 0.70
                else "critical"
            ),
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.fairness_score,
                    "affected_entities": d.affected_entities,
                }
                for d in report.dimensions
            ],
            "trend": trend,
            "last_checked": report.generated_at.isoformat(),
        }

        return metrics
    except Exception as e:
        logger.error(
            "ai_ethics.fairness_metrics_failed",
            user_id=str(current_user.id),
            company_id=str(company_id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Laden der Fairness-Metriken",
        )


@router.post(
    "/guardrail-check",
    response_model=Dict[str, Any],
    summary="Guardrail-Check",
    description="Prueft ob Aktion ethisch vertretbar ist"
)
async def guardrail_check(
    request: GuardrailCheckRequest,
    current_user: User = Depends(get_current_active_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Prueft Aktion mit Ethical Guardrails.

    **Unterstuetzte Actions:**
    - **delete_documents**: Dokument-Loeschung
    - **approve_payment**: Zahlungs-Freigabe
    - **bulk_export**: Daten-Export
    - **auto_approve_invoices**: Auto-Freigabe Rechnungen
    - **change_risk_score**: Risk-Score-Aenderung

    **Request Body:**
    ```json
    {
        "action_type": "approve_payment",
        "parameters": {
            "invoice_id": "uuid-...",
            "amount": 15000.50,
            "entity_id": "uuid-..."
        }
    }
    ```

    **Response:**
    - **allowed**: Aktion erlaubt (bool)
    - **reason**: Begruendung (German)
    - **risk_level**: low/medium/high
    - **requires_human_review**: Manuelle Pruefung erforderlich (bool)

    **Rollen:** Alle authentifizierten Benutzer
    """
    logger.info(
        "ai_ethics.guardrail_check",
        action_type=request.action_type,
        user_id=str(current_user.id),
    )

    guardrails = EthicalGuardrails()

    try:
        result = await guardrails.check_action(
            request.action_type,
            request.parameters,
            company_id,
            db,
        )

        return result.to_dict()
    except Exception as e:
        logger.error(
            "ai_ethics.guardrail_check_failed",
            action_type=request.action_type,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Guardrail-Check",
        )
