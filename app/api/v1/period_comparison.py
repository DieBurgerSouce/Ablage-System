# -*- coding: utf-8 -*-
"""
Period Comparison API Endpoint.

Provides Year-over-Year (YoY), Month-over-Month (MoM), and Quarter-over-Quarter (QoQ)
analytics for dashboard widgets.

Created: 2026-02-08
Status: Production-Ready
"""

from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional

from app.core.types import JSONDict
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.session import get_async_session
from app.api.dependencies import get_current_user
from app.core.safe_errors import safe_error_log, safe_error_detail
from app.services.dashboard.period_comparison_service import (
    PeriodComparisonService,
    ComparisonPeriod,
    PeriodMetrics,
    PeriodComparison,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/period-comparison", tags=["Period Comparison"])


# ==================== Pydantic Schemas ====================

class PeriodMetricsResponse(BaseModel):
    """Response model for period metrics."""
    period_label: str = Field(..., description="Deutsche Periodenbezeichnung (z.B. 'Januar 2026')")
    document_count: int = Field(..., description="Anzahl Dokumente")
    invoice_total: Decimal = Field(..., description="Gesamtsumme Rechnungen (netto)")
    expense_total: Decimal = Field(..., description="Gesamtsumme Ausgaben (netto)")
    ocr_processed: int = Field(..., description="Anzahl OCR-verarbeitete Dokumente")
    avg_processing_time_ms: float = Field(..., description="Durchschnittliche Verarbeitungszeit (ms)")
    approval_count: int = Field(..., description="Anzahl genehmigter Rechnungen")
    approval_avg_days: float = Field(..., description="Durchschnittliche Genehmigungsdauer (Tage)")

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_dataclass(cls, metrics: PeriodMetrics) -> "PeriodMetricsResponse":
        """Convert dataclass to Pydantic model."""
        return cls(
            period_label=metrics.period_label,
            document_count=metrics.document_count,
            invoice_total=metrics.invoice_total,
            expense_total=metrics.expense_total,
            ocr_processed=metrics.ocr_processed,
            avg_processing_time_ms=metrics.avg_processing_time_ms,
            approval_count=metrics.approval_count,
            approval_avg_days=metrics.approval_avg_days,
        )


class PeriodComparisonResponse(BaseModel):
    """Response model for period comparison."""
    current: PeriodMetricsResponse = Field(..., description="Aktuelle Periode")
    previous: PeriodMetricsResponse = Field(..., description="Vorherige Periode")
    deltas: Dict[str, float] = Field(..., description="Prozentuale Veränderungen")
    trend: str = Field(..., description="Gesamttrend: 'up', 'down', oder 'stable'")

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_dataclass(cls, comparison: PeriodComparison) -> "PeriodComparisonResponse":
        """Convert dataclass to Pydantic model."""
        return cls(
            current=PeriodMetricsResponse.from_dataclass(comparison.current),
            previous=PeriodMetricsResponse.from_dataclass(comparison.previous),
            deltas=comparison.deltas,
            trend=comparison.trend,
        )


class PeriodSummaryResponse(BaseModel):
    """Quick summary response for dashboard widgets."""
    period_type: str = Field(..., description="Periodentyp")
    current_period: str = Field(..., description="Aktuelle Periodenbezeichnung")
    previous_period: str = Field(..., description="Vorherige Periodenbezeichnung")
    trend: str = Field(..., description="Gesamttrend")
    deltas: Dict[str, float] = Field(..., description="Prozentuale Veränderungen")
    highlights: JSONDict = Field(..., description="Wichtigste Metriken")

    model_config = ConfigDict(from_attributes=True)


# ==================== API Endpoints ====================

@router.get(
    "/{period_type}",
    response_model=PeriodComparisonResponse,
    summary="Periodenvergleich",
    description="Vergleicht die aktuelle Periode mit der vorherigen (MoM, QoQ, YoY)"
)
async def compare_periods(
    period_type: ComparisonPeriod,
    reference_date: Optional[str] = Query(
        None,
        description="Referenzdatum (ISO 8601 YYYY-MM-DD), Standard: heute"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> PeriodComparisonResponse:
    """
    Vergleicht die aktuelle Periode mit der vorherigen.

    Args:
        period_type: Periodentyp (month, quarter, year)
        reference_date: Optionales Referenzdatum
        current_user: Aktueller authentifizierter Benutzer
        db: Datenbank-Session

    Returns:
        Vergleich mit aktueller und vorheriger Periode sowie Deltas

    Raises:
        HTTPException: Bei ungültigem Datum oder Verarbeitungsfehler
    """
    try:
        # Parse reference date if provided
        ref_date: Optional[date] = None
        if reference_date:
            try:
                ref_date = date.fromisoformat(reference_date)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Ungültiges Datumsformat. Verwenden Sie YYYY-MM-DD."
                )

        service = PeriodComparisonService(db)
        comparison = await service.compare_periods(
            user_id=current_user.id,
            period_type=period_type,
            reference_date=ref_date
        )

        logger.info(
            "period_comparison_success",
            user_id=str(current_user.id),
            period_type=period_type.value,
            trend=comparison.trend
        )

        return PeriodComparisonResponse.from_dataclass(comparison)

    except ValueError as e:
        logger.warning(
            "invalid_period_comparison_request",
            **safe_error_log(e, context="period_comparison"),
            user_id=str(current_user.id)
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Periodenvergleich")
        )
    except Exception as e:
        logger.error(
            "period_comparison_failed",
            **safe_error_log(e, context="period_comparison"),
            user_id=str(current_user.id)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Periodenvergleich")
        )


@router.get(
    "/trend/{metric}",
    response_model=List[PeriodMetricsResponse],
    summary="Trend-Serie abrufen",
    description="Ruft eine Zeitreihe für eine bestimmte Metrik ab (z.B. für Charts)"
)
async def get_trend_series(
    metric: str = Path(
        ...,
        description="Metrik-Name (document_count, invoice_total, etc.)"
    ),
    periods: int = Query(
        12,
        ge=1,
        le=100,
        description="Anzahl der Perioden (1-100)"
    ),
    period_type: ComparisonPeriod = Query(
        ComparisonPeriod.MONTH,
        description="Periodentyp"
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> List[PeriodMetricsResponse]:
    """
    Ruft eine Zeitreihe für eine bestimmte Metrik ab.

    Args:
        metric: Name der Metrik
        periods: Anzahl der Perioden
        period_type: Periodentyp
        current_user: Aktueller authentifizierter Benutzer
        db: Datenbank-Session

    Returns:
        Liste von Metriken in chronologischer Reihenfolge

    Raises:
        HTTPException: Bei ungültiger Metrik oder Verarbeitungsfehler
    """
    try:
        service = PeriodComparisonService(db)
        trend_data = await service.get_trend_series(
            user_id=current_user.id,
            metric=metric,
            periods=periods,
            period_type=period_type
        )

        logger.info(
            "trend_series_success",
            user_id=str(current_user.id),
            metric=metric,
            periods_fetched=len(trend_data)
        )

        return [
            PeriodMetricsResponse.from_dataclass(metrics)
            for metrics in trend_data
        ]

    except ValueError as e:
        logger.warning(
            "invalid_trend_request",
            **safe_error_log(e, context="trend_series"),
            user_id=str(current_user.id),
            metric=metric
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Trend-Abfrage")
        )
    except Exception as e:
        logger.error(
            "trend_series_failed",
            **safe_error_log(e, context="trend_series"),
            user_id=str(current_user.id)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Trend-Abfrage")
        )


@router.get(
    "/summary/{period_type}",
    response_model=PeriodSummaryResponse,
    summary="Perioden-Zusammenfassung",
    description="Liefert eine kompakte Zusammenfassung mit wichtigsten Deltas für Dashboard-Widgets"
)
async def get_period_summary(
    period_type: ComparisonPeriod,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session)
) -> PeriodSummaryResponse:
    """
    Liefert eine kompakte Zusammenfassung für Dashboard-Widgets.

    Args:
        period_type: Periodentyp (month, quarter, year)
        current_user: Aktueller authentifizierter Benutzer
        db: Datenbank-Session

    Returns:
        Kompakte Zusammenfassung mit Trend und Highlights

    Raises:
        HTTPException: Bei Verarbeitungsfehler
    """
    try:
        service = PeriodComparisonService(db)
        summary = await service.get_period_summary(
            user_id=current_user.id,
            period_type=period_type
        )

        logger.info(
            "period_summary_success",
            user_id=str(current_user.id),
            period_type=period_type.value,
            trend=summary["trend"]
        )

        return PeriodSummaryResponse(**summary)

    except Exception as e:
        logger.error(
            "period_summary_failed",
            **safe_error_log(e, context="period_summary"),
            user_id=str(current_user.id)
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Perioden-Zusammenfassung")
        )
