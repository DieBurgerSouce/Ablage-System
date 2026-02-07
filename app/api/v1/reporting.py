"""
Executive Reporting API Endpoints

FastAPI Router fuer Geschaeftsfuehrung Dashboard und Reporting.
"""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_current_user, get_db, get_current_company_id
from app.api.schemas.reporting import (
    KPIResponse,
    DepartmentBreakdown,
    TrendResponse,
    ExecutiveSummaryResponse,
)
from app.db.models import User
from app.services.reporting import (
    get_kpis,
    get_department_breakdown,
    get_trend,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/reporting",
    tags=["Executive Reporting"],
)


@router.get(
    "/kpis",
    response_model=KPIResponse,
    summary="Hole Key Performance Indicators",
    description="Liefert aktuelle KPIs fuer Geschaeftsfuehrung Dashboard",
)
async def get_kpis_endpoint(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> KPIResponse:
    """
    Hole Key Performance Indicators.

    Liefert:
    - Dokumentenanzahl aktueller/letzter Monat + Trend
    - Durchschnittliche Verarbeitungszeit + Trend
    - OCR-Genauigkeit + Trend
    - Geschaetzte Kosten pro Dokument
    - Anzahl aktiver Benutzer
    - Ausstehende Pruefungen
    """
    try:
        kpis = await get_kpis(company_id=company_id, db=db)
        logger.info(
            "kpis_abgerufen",
            user_id=str(current_user.id),
            company_id=str(company_id),
        )
        return kpis
    except Exception as e:
        logger.error(
            "kpis_abruf_fehler",
            error=str(e),
            user_id=str(current_user.id),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der KPIs",
        )


@router.get(
    "/departments",
    response_model=List[DepartmentBreakdown],
    summary="Hole Abteilungsstatistiken",
    description="Liefert Statistiken gruppiert nach Abteilungen/Bereichen",
)
async def get_departments_endpoint(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> List[DepartmentBreakdown]:
    """
    Hole Abteilungsstatistiken.

    Gruppiert Dokumente nach Typ (als Proxy fuer Abteilung) und liefert:
    - Dokumentenanzahl
    - Durchschnittliche Verarbeitungszeit
    - Durchschnittliche OCR-Genauigkeit
    - Ausstehende Dokumente
    """
    try:
        departments = await get_department_breakdown(company_id=company_id, db=db)
        logger.info(
            "abteilungsstatistiken_abgerufen",
            user_id=str(current_user.id),
            company_id=str(company_id),
            count=len(departments),
        )
        return departments
    except Exception as e:
        logger.error(
            "abteilungsstatistiken_fehler",
            error=str(e),
            user_id=str(current_user.id),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Abteilungsstatistiken",
        )


@router.get(
    "/trends/{metric}",
    response_model=TrendResponse,
    summary="Hole Trend-Daten",
    description="Liefert taegliche Trend-Daten fuer eine Metrik",
)
async def get_trend_endpoint(
    metric: str,
    days: int = Query(default=30, ge=1, le=365, description="Anzahl Tage zurueck"),
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> TrendResponse:
    """
    Hole Trend-Daten fuer eine Metrik.

    Unterstuetzte Metriken:
    - documents: Anzahl Dokumente pro Tag
    - processing_time: Durchschnittliche Verarbeitungszeit pro Tag
    - accuracy: Durchschnittliche OCR-Genauigkeit pro Tag

    Args:
        metric: Name der Metrik
        days: Anzahl Tage zurueck (1-365)
    """
    # Validiere Metrik
    valid_metrics = {"documents", "processing_time", "accuracy"}
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltige Metrik. Erlaubt: {', '.join(valid_metrics)}",
        )

    try:
        trend = await get_trend(
            company_id=company_id,
            metric=metric,
            days=days,
            db=db,
        )
        logger.info(
            "trend_abgerufen",
            user_id=str(current_user.id),
            company_id=str(company_id),
            metric=metric,
            days=days,
            data_points=len(trend.data),
        )
        return trend
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "trend_abruf_fehler",
            error=str(e),
            user_id=str(current_user.id),
            company_id=str(company_id),
            metric=metric,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Trend-Daten",
        )


@router.get(
    "/summary",
    response_model=ExecutiveSummaryResponse,
    summary="Hole Executive Summary",
    description="Liefert vollstaendige Zusammenfassung mit KPIs, Abteilungen und Trends",
)
async def get_summary_endpoint(
    current_user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    db: AsyncSession = Depends(get_db),
) -> ExecutiveSummaryResponse:
    """
    Hole Executive Summary.

    Kombiniert alle Reporting-Daten:
    - KPIs
    - Abteilungsstatistiken
    - Dokumente-Trend (30 Tage)
    - Verarbeitungszeit-Trend (30 Tage)
    """
    try:
        # Hole alle Daten parallel
        kpis = await get_kpis(company_id=company_id, db=db)
        departments = await get_department_breakdown(company_id=company_id, db=db)
        doc_trend = await get_trend(
            company_id=company_id,
            metric="documents",
            days=30,
            db=db,
        )
        proc_trend = await get_trend(
            company_id=company_id,
            metric="processing_time",
            days=30,
            db=db,
        )

        summary = ExecutiveSummaryResponse(
            kpis=kpis,
            departments=departments,
            document_trend=doc_trend,
            processing_trend=proc_trend,
            generated_at=kpis.model_dump()["documents_this_month"].__class__.__name__,  # Dummy - wird unten ersetzt
        )

        # Setze generated_at
        from datetime import datetime, timezone
        summary.generated_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "executive_summary_abgerufen",
            user_id=str(current_user.id),
            company_id=str(company_id),
        )
        return summary

    except Exception as e:
        logger.error(
            "executive_summary_fehler",
            error=str(e),
            user_id=str(current_user.id),
            company_id=str(company_id),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fehler beim Abrufen der Executive Summary",
        )
