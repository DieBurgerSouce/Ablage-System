# -*- coding: utf-8 -*-
"""
Jahresabschluss-Assistent API Endpoints.

Endpunkte für den Jahresabschluss-Assistenten:
- Sessions erstellen und verwalten
- Vollständigkeitsprüfung durchführen
- Lücken verwalten und beheben
- Steuerberater-Bericht generieren
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.middleware.company_context import require_company
from app.core.safe_errors import safe_error_detail, safe_error_log
from app.db.models import User, Company
from app.db.schemas_year_end import (
    YearEndSessionCreate,
    YearEndSessionResponse,
    YearEndSessionDetailResponse,
    YearEndSessionListResponse,
    YearEndCheckItemResponse,
    YearEndGapResponse,
    YearEndReportResponse,
    ResolveGapRequest,
    UpdateCheckItemRequest,
)
from app.services.year_end.year_end_service import YearEndService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/year-end", tags=["Jahresabschluss"])

_service = YearEndService()


# =============================================================================
# Session Endpoints
# =============================================================================


@router.post(
    "/sessions",
    response_model=YearEndSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Jahresabschluss-Session erstellen",
)
async def create_session(
    body: YearEndSessionCreate,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndSessionResponse:
    """Erstellt eine neue Jahresabschluss-Session für das angegebene Geschäftsjahr."""
    try:
        session = await _service.create_session(
            db=db,
            company_id=company.id,
            fiscal_year=body.fiscal_year,
            user_id=current_user.id,
        )
        return YearEndSessionResponse.model_validate(session)
    except Exception as e:
        logger.error("Fehler beim Erstellen der Session", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )


@router.get(
    "/sessions",
    response_model=YearEndSessionListResponse,
    summary="Jahresabschluss-Sessions auflisten",
)
async def list_sessions(
    page: int = Query(1, ge=1, description="Seitennummer"),
    per_page: int = Query(20, ge=1, le=100, description="Einträge pro Seite"),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndSessionListResponse:
    """Listet alle Jahresabschluss-Sessions des Unternehmens."""
    try:
        sessions, total = await _service.list_sessions(
            db=db,
            company_id=company.id,
            page=page,
            per_page=per_page,
        )
        return YearEndSessionListResponse(
            items=[
                YearEndSessionResponse.model_validate(s)
                for s in sessions
            ],
            total=total,
            page=page,
            per_page=per_page,
        )
    except Exception as e:
        logger.error("Fehler beim Auflisten der Sessions", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )


@router.get(
    "/sessions/{session_id}",
    response_model=YearEndSessionDetailResponse,
    summary="Jahresabschluss-Session-Details abrufen",
)
async def get_session(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndSessionDetailResponse:
    """Ruft Details einer Jahresabschluss-Session ab (inkl. Prüfpunkte und Lücken)."""
    session = await _service.get_session(
        db=db,
        session_id=session_id,
        company_id=company.id,
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Jahresabschluss-Session nicht gefunden",
        )
    return YearEndSessionDetailResponse.model_validate(session)


# =============================================================================
# Check Endpoints
# =============================================================================


@router.post(
    "/sessions/{session_id}/run-checks",
    response_model=YearEndSessionResponse,
    summary="Vollständigkeitsprüfung durchführen",
)
async def run_completeness_check(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndSessionResponse:
    """Führt die automatische Vollständigkeitsprüfung für die Session durch."""
    try:
        session = await _service.run_completeness_check(
            db=db,
            session_id=session_id,
            company_id=company.id,
        )
        return YearEndSessionResponse.model_validate(session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )
    except Exception as e:
        logger.error(
            "Fehler bei Vollständigkeitsprüfung",
            **safe_error_log(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Vollständigkeitsprüfung"),
        )


@router.patch(
    "/check-items/{item_id}",
    response_model=YearEndCheckItemResponse,
    summary="Prüfpunkt aktualisieren",
)
async def update_check_item(
    item_id: UUID,
    body: UpdateCheckItemRequest,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndCheckItemResponse:
    """Aktualisiert den Status eines einzelnen Prüfpunkts."""
    try:
        item = await _service.update_check_item(
            db=db,
            item_id=item_id,
            company_id=company.id,
            status=body.status.value,
            user_id=current_user.id,
            notes=body.notes,
        )
        return YearEndCheckItemResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )
    except Exception as e:
        logger.error("Fehler beim Aktualisieren des Prüfpunkts", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Prüfpunkt"),
        )


# =============================================================================
# Gap Endpoints
# =============================================================================


@router.get(
    "/sessions/{session_id}/gaps",
    response_model=List[YearEndGapResponse],
    summary="Lücken und Unstimmigkeiten auflisten",
)
async def list_gaps(
    session_id: UUID,
    category: Optional[str] = Query(None, description="Nach Kategorie filtern"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Nach Monat filtern"),
    resolved: Optional[bool] = Query(None, description="Nach Loesungsstatus filtern"),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> List[YearEndGapResponse]:
    """Listet alle Lücken und Unstimmigkeiten einer Session."""
    gaps = await _service.get_gaps(
        db=db,
        session_id=session_id,
        company_id=company.id,
        category=category,
        month=month,
        resolved=resolved,
    )
    return [YearEndGapResponse.model_validate(g) for g in gaps]


@router.post(
    "/gaps/{gap_id}/resolve",
    response_model=YearEndGapResponse,
    summary="Lücke als behoben markieren",
)
async def resolve_gap(
    gap_id: UUID,
    body: ResolveGapRequest,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndGapResponse:
    """Markiert eine identifizierte Lücke als behoben."""
    try:
        gap = await _service.resolve_gap(
            db=db,
            gap_id=gap_id,
            company_id=company.id,
            user_id=current_user.id,
            notes=body.notes,
        )
        return YearEndGapResponse.model_validate(gap)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )
    except Exception as e:
        logger.error("Fehler beim Beheben der Lücke", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Lücke"),
        )


# =============================================================================
# Report & Complete Endpoints
# =============================================================================


@router.post(
    "/sessions/{session_id}/report",
    response_model=YearEndReportResponse,
    summary="Steuerberater-Bericht generieren",
)
async def generate_report(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndReportResponse:
    """Generiert einen umfassenden Bericht für den Steuerberater."""
    try:
        report_data = await _service.generate_report_data(
            db=db,
            session_id=session_id,
            company_id=company.id,
        )
        # Session neu laden für Zeitstempel
        session = await _service.get_session(
            db=db,
            session_id=session_id,
            company_id=company.id,
        )
        if session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session nicht gefunden",
            )
        return YearEndReportResponse(
            session_id=session.id,
            fiscal_year=session.fiscal_year,
            report_data=report_data,
            generated_at=session.report_generated_at,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Fehler beim Generieren des Berichts", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Bericht"),
        )


@router.post(
    "/sessions/{session_id}/complete",
    response_model=YearEndSessionResponse,
    summary="Jahresabschluss abschließen",
)
async def complete_session(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
    db: AsyncSession = Depends(get_db),
) -> YearEndSessionResponse:
    """Schließt den Jahresabschluss ab (nur wenn alle kritischen Prüfungen bestanden)."""
    try:
        session = await _service.complete_session(
            db=db,
            session_id=session_id,
            company_id=company.id,
            user_id=current_user.id,
        )
        return YearEndSessionResponse.model_validate(session)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )
    except Exception as e:
        logger.error("Fehler beim Abschließen", **safe_error_log(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=safe_error_detail(e, "Jahresabschluss"),
        )
