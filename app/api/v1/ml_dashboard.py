"""
ML Progress Dashboard API Endpoints.

Provides OCR Self-Learning progress metrics:
- Learning curve (recognition rate over time)
- Error statistics (by error type)
- Correction impact (accuracy improvement)
- Model performance by document type
- Auto-categorization accuracy
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db, get_current_user, get_user_company_id_dep
from app.db.models import User
from app.services.ml_dashboard_service import get_ml_dashboard_service

router = APIRouter(prefix="/ml-dashboard", tags=["ML Dashboard"])


# ==================== Schemas ====================

class LearningPoint(BaseModel):
    """Learning Curve Data Point."""
    month: Optional[str]
    recognition_rate: float = Field(ge=0, le=100)
    correction_count: int
    avg_confidence_before: float
    avg_confidence_after: float
    improvement: float


class ErrorType(BaseModel):
    """Error Type Statistics."""
    category: str
    description: str
    count: int
    percentage: float


class ErrorStatistics(BaseModel):
    """Error Statistics Response."""
    total_corrections: int
    error_types: List[ErrorType]


class CorrectionImpact(BaseModel):
    """Correction Impact Response."""
    correction_count: int
    avg_confidence_before: float
    avg_confidence_after: float
    accuracy_improvement_percent: float
    summary: str


class ModelPerformance(BaseModel):
    """Model Performance by Document Type."""
    document_type: str
    document_count: int
    correction_count: int
    avg_confidence: float
    accuracy_rate: float


class CategorizationAccuracy(BaseModel):
    """Categorization Accuracy Response."""
    total_documents: int
    auto_categorized: int
    accuracy_rate_percent: float
    trend_percent: float
    trend_direction: str


class MLDashboardData(BaseModel):
    """ML Dashboard Complete Data."""
    period_months: int
    period_start: str
    period_end: str
    learning_curve: List[LearningPoint]
    error_statistics: ErrorStatistics
    correction_impact: CorrectionImpact
    model_performance_by_type: List[ModelPerformance]
    categorization_accuracy: CategorizationAccuracy


# ==================== Endpoints ====================

@router.get(
    "/",
    response_model=MLDashboardData,
    summary="ML Dashboard Übersicht",
    description="Liefert komplette Übersicht über OCR-Self-Learning Fortschritt"
)
async def get_ml_dashboard(
    months: int = Query(6, ge=1, le=24, description="Zeitraum in Monaten"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> MLDashboardData:
    """
    Liefert ML Dashboard Daten.

    **Enthält:**
    - Learning Curve: Erkennungsrate über Zeit
    - Error Statistics: Fehlertypen (Umlaut, Ziffern, etc.)
    - Correction Impact: Wie viel haben Korrekturen verbessert?
    - Model Performance: Genauigkeit pro Dokumenttyp
    - Categorization Accuracy: Auto-Kategorisierung Erfolgsrate

    **Beispiel Summary:**
    "127 Korrekturen, +4.2% Genauigkeit"
    """
    service = get_ml_dashboard_service(db)
    dashboard_data = await service.get_dashboard_data(company_id, months)

    return MLDashboardData(**dashboard_data)


@router.get(
    "/learning-curve",
    response_model=List[LearningPoint],
    summary="Learning Curve",
    description="Erkennungsrate über Zeit (monatlich aggregiert)"
)
async def get_learning_curve(
    months: int = Query(6, ge=1, le=24, description="Zeitraum in Monaten"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[LearningPoint]:
    """
    Liefert Learning Curve.

    Zeigt:
    - Monatliche Erkennungsrate
    - Anzahl Korrekturen pro Monat
    - Durchschnittliche Confidence (vor/nach)
    - Verbesserung in Prozent

    **Nutzung:**
    - Visualisierung als Liniendiagramm
    - Zeigt ob System besser wird über Zeit
    """
    service = get_ml_dashboard_service(db)
    learning_curve = await service.get_learning_curve(company_id, months)

    return [LearningPoint(**point) for point in learning_curve]


@router.get(
    "/error-stats",
    response_model=ErrorStatistics,
    summary="Fehlertyp-Statistiken",
    description="Aggregierte Statistiken nach Fehler-Kategorie"
)
async def get_error_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> ErrorStatistics:
    """
    Liefert Fehlertyp-Statistiken.

    **Fehler-Kategorien:**
    - Umlaut: ä, ö, ü Probleme
    - Digit Swap: 0<->O, 1<->l Verwechslungen
    - Spacing: Leerzeichen-Fehler
    - Case: Groß-/Kleinschreibung
    - OCR Noise: Rauschen/Artefakte
    - Unknown: Nicht kategorisierbar

    **Nutzung:**
    - Zeigt wo OCR am meisten Probleme hat
    - Priorisierung für Model-Training
    """
    service = get_ml_dashboard_service(db)
    error_stats = await service.get_error_statistics(company_id)

    return ErrorStatistics(**error_stats)


@router.get(
    "/correction-impact",
    response_model=CorrectionImpact,
    summary="Korrektur-Impact",
    description="Zeigt wie viel Korrekturen die Genauigkeit verbessert haben"
)
async def get_correction_impact(
    months: int = Query(6, ge=1, le=24, description="Zeitraum in Monaten"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> CorrectionImpact:
    """
    Liefert Korrektur-Impact.

    Zeigt:
    - Anzahl Korrekturen im Zeitraum
    - Durchschnittliche Confidence vor/nach
    - Verbesserung in Prozent

    **Beispiel:**
    "127 Korrekturen, +4.2% Genauigkeit"

    **Interpretation:**
    - Positiver Wert: System wird besser
    - Negativer Wert: Model braucht Re-Training
    """
    service = get_ml_dashboard_service(db)

    # Calculate period start
    from datetime import datetime, timezone, timedelta
    period_start = datetime.now(timezone.utc) - timedelta(days=months * 30)

    correction_impact = await service.get_correction_impact(
        company_id,
        period_start
    )

    return CorrectionImpact(**correction_impact)


@router.get(
    "/model-performance",
    response_model=List[ModelPerformance],
    summary="Model-Performance pro Dokumenttyp",
    description="Zeigt OCR-Genauigkeit aufgeschlüsselt nach Dokumenttyp"
)
async def get_model_performance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    company_id: UUID = Depends(get_user_company_id_dep),
) -> List[ModelPerformance]:
    """
    Liefert Model-Performance pro Dokumenttyp.

    Zeigt:
    - Anzahl Dokumente pro Typ
    - Anzahl Korrekturen
    - Durchschnittliche Confidence
    - Accuracy Rate (inverse Korrekturrate)

    **Nutzung:**
    - Identifiziere welche Dokumenttypen gut/schlecht erkannt werden
    - Priorisierung für spezifisches Model-Training
    """
    service = get_ml_dashboard_service(db)
    performance = await service.get_model_performance_by_type(company_id)

    return [ModelPerformance(**perf) for perf in performance]
