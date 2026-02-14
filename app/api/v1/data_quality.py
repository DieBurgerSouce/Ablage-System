# -*- coding: utf-8 -*-
"""
Data Quality API Endpoints.

Provides data quality monitoring and cleanup actions.

Endpoints:
- GET /api/v1/data-quality - Get quality report
- GET /api/v1/data-quality/trend - Get quality trend
- GET /api/v1/data-quality/suggestions - Get correction suggestions
- POST /api/v1/data-quality/{category}/fix - Execute cleanup
"""

from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User
from app.services.data_quality_service import (
    DataQualityService,
    get_data_quality_service,
    QualityCategory,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/data-quality", tags=["Datenqualitaet"])


# =============================================================================
# Request/Response Models
# =============================================================================

class FixActionRequest(BaseModel):
    """Request model for fix action."""
    action: str


class FixActionResponse(BaseModel):
    """Response model for fix action."""
    fixed_count: int
    message: str


# =============================================================================
# Endpoints
# =============================================================================

@router.get(
    "",
    response_model=Dict[str, Any],
    summary="Datenqualitaets-Bericht abrufen",
    description="Vollstaendiger Datenqualitaets-Bericht mit allen erkannten Issues und Gesamt-Score.",
)
async def get_data_quality_report(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Ruft vollstaendigen Datenqualitaets-Bericht ab.

    Returns:
        Data Quality Report mit Issues und Score
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen",
        )

    try:
        service = get_data_quality_service(db)
        report = await service.get_quality_report(current_user.company_id)

        logger.info(
            "data_quality_report_retrieved",
            user_id=str(current_user.id),
            company_id=str(current_user.company_id),
            overall_score=report.overall_score,
        )

        return {
            "overall_score": report.overall_score,
            "issues": [
                {
                    "category": issue.category.value,
                    "severity": issue.severity,
                    "title": issue.title,
                    "description": issue.description,
                    "count": issue.count,
                    "action_label": issue.action_label,
                    "action_endpoint": issue.action_endpoint,
                }
                for issue in report.issues
            ],
            "trend": report.trend,
            "last_check": report.last_check.isoformat(),
        }

    except Exception as e:
        logger.error(
            "data_quality_report_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Abrufen des Datenqualitaets-Berichts"),
        )


@router.get(
    "/trend",
    response_model=List[Dict[str, Any]],
    summary="Datenqualitaets-Trend abrufen",
    description="Historischer Trend des Datenqualitaets-Scores ueber mehrere Monate.",
)
async def get_data_quality_trend(
    months: int = Query(6, ge=1, le=24, description="Anzahl Monate"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Ruft Datenqualitaets-Trend ab.

    Args:
        months: Number of months to look back (1-24)

    Returns:
        List of monthly trend points
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen",
        )

    try:
        service = get_data_quality_service(db)
        trend = await service.get_quality_trend(current_user.company_id, months)

        logger.info(
            "data_quality_trend_retrieved",
            user_id=str(current_user.id),
            company_id=str(current_user.company_id),
            months=months,
        )

        return trend

    except Exception as e:
        logger.error(
            "data_quality_trend_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Abrufen des Trends"),
        )


@router.get(
    "/suggestions",
    response_model=List[Dict[str, str]],
    summary="Korrekturvorschlaege abrufen",
    description="Priorisierte Handlungsempfehlungen basierend auf aktuellen Datenqualitaets-Issues.",
)
async def get_correction_suggestions(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, str]]:
    """
    Gibt priorisierte Korrekturvorschlaege zurueck.

    Returns:
        Liste von Vorschlaegen mit Prioritaet, Titel und Beschreibung
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen",
        )

    try:
        service = get_data_quality_service(db)
        suggestions = await service.get_correction_suggestions(
            current_user.company_id,
        )

        logger.info(
            "data_quality_suggestions_retrieved",
            user_id=str(current_user.id),
            company_id=str(current_user.company_id),
            suggestion_count=len(suggestions),
        )

        return suggestions

    except Exception as e:
        logger.error(
            "data_quality_suggestions_failed",
            user_id=str(current_user.id),
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Abrufen der Vorschlaege"),
        )


@router.post(
    "/{category}/fix",
    response_model=FixActionResponse,
    summary="Datenqualitaets-Issue beheben",
    description="Fuehrt Cleanup-Aktion fuer eine bestimmte Issue-Kategorie aus.",
)
async def fix_data_quality_issue(
    category: str,
    request: FixActionRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FixActionResponse:
    """
    Fuehrt Cleanup-Aktion fuer Issue-Kategorie aus.

    Args:
        category: Issue category (uncategorized, duplicates, orphaned_entities, etc.)
        request: Fix action parameters

    Returns:
        Number of items fixed
    """
    if not current_user.company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Benutzer hat keine Firma zugewiesen",
        )

    # Validate category
    try:
        quality_category = QualityCategory(category)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungueltige Kategorie: {category}",
        )

    try:
        service = get_data_quality_service(db)
        fixed_count = await service.fix_issue(
            current_user.company_id,
            quality_category,
            request.action,
        )

        logger.info(
            "data_quality_issue_fixed",
            user_id=str(current_user.id),
            company_id=str(current_user.company_id),
            category=category,
            action=request.action,
            fixed_count=fixed_count,
        )

        return FixActionResponse(
            fixed_count=fixed_count,
            message=f"{fixed_count} Eintraege wurden bereinigt",
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "data_quality_fix_failed",
            user_id=str(current_user.id),
            category=category,
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Fehler beim Beheben des Issues"),
        )
