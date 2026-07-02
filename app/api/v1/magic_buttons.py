# -*- coding: utf-8 -*-
"""
Magic Buttons API Endpoints.

Ein-Klick-Aktionen für Enterprise-Workflows:
- POST /magic/daily-close/preview - Vorschau Tages-Abschluss
- POST /magic/daily-close/execute - Tages-Abschluss ausführen
- POST /magic/monthly-report/preview - Vorschau Monats-Report
- POST /magic/monthly-report/execute - Monats-Report erstellen
- POST /magic/clear-open-items/preview - Vorschau Offene Posten
- POST /magic/clear-open-items/execute - Offene Posten bereinigen
- POST /magic/create-contact/preview - Vorschau Kontakt erstellen
- POST /magic/create-contact/execute - Kontakt aus Dokument erstellen
"""

from datetime import date
from typing import Optional, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.api.dependencies import get_db, get_current_active_user, get_user_company_id
from app.services.magic_buttons_service import (
    get_magic_buttons_service,
    MagicButtonType,
    MagicButtonStatus,
    MagicButtonPreview,
    MagicButtonResult,
)


logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/magic", tags=["Magic Buttons"])


# =============================================================================
# Response Models
# =============================================================================

class PreviewItemResponse(BaseModel):
    """Ein Item in der Vorschau."""
    type: Optional[str] = None
    field: Optional[str] = None
    count: Optional[int] = None
    value: Optional[str] = None
    amount: Optional[float] = None
    label: str


class MagicPreviewResponse(BaseModel):
    """API Response für Magic-Button-Vorschau."""
    button_type: str
    title: str
    description: str

    document_count: int = 0
    transaction_count: int = 0
    entity_count: int = 0
    invoice_count: int = 0

    estimated_amount: float = 0.0
    estimated_duration_seconds: int = 0

    warnings: List[str] = Field(default_factory=list)
    items: List[PreviewItemResponse] = Field(default_factory=list)

    can_execute: bool = True
    block_reason: Optional[str] = None
    message: str


class MagicResultDetailResponse(BaseModel):
    """Detail einer ausgeführten Aktion."""
    step: str
    processed: Optional[int] = None
    matched: Optional[int] = None
    linked: Optional[int] = None
    increased: Optional[int] = None
    skipped: Optional[int] = None
    filename: Optional[str] = None
    document_count: Optional[int] = None
    export_id: Optional[str] = None
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    entity_type: Optional[str] = None
    document_linked: Optional[bool] = None


class MagicResultResponse(BaseModel):
    """API Response für Magic-Button-Ergebnis."""
    button_type: str
    status: str
    title: str
    message: str

    processed_count: int = 0
    success_count: int = 0
    error_count: int = 0
    skipped_count: int = 0

    total_amount: float = 0.0

    details: List[MagicResultDetailResponse] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)

    duration_ms: int = 0

    export_file_id: Optional[str] = None
    export_filename: Optional[str] = None


class MagicButtonInfoResponse(BaseModel):
    """Info zu einem Magic Button."""
    type: str
    title: str
    description: str
    icon: str
    color: str


# =============================================================================
# Request Models
# =============================================================================

class DailyCloseRequest(BaseModel):
    """Request für Tages-Abschluss."""
    target_date: Optional[date] = Field(None, description="Zieldatum (default: heute)")
    auto_match: bool = Field(True, description="Transaktionen automatisch abgleichen")
    auto_assign: bool = Field(True, description="Dokumente automatisch zuordnen")


class MonthlyReportRequest(BaseModel):
    """Request für Monats-Report."""
    year: int = Field(..., ge=2020, le=2100, description="Jahr")
    month: int = Field(..., ge=1, le=12, description="Monat")
    include_datev: bool = Field(True, description="DATEV-Export erstellen")
    include_pdf_archive: bool = Field(False, description="PDF-Archiv erstellen")


class ClearOpenItemsRequest(BaseModel):
    """Request für Offene Posten bereinigen."""
    auto_reconcile: bool = Field(True, description="Automatisch abgleichen")
    send_reminders: bool = Field(False, description="Zahlungserinnerungen senden")
    increase_dunning: bool = Field(False, description="Mahnstufen erhöhen")


class CreateContactRequest(BaseModel):
    """Request für Kontakt erstellen."""
    document_id: UUID = Field(..., description="Dokument-ID")
    entity_type: str = Field("supplier", description="Entity-Typ (supplier/customer)")
    override_name: Optional[str] = Field(None, description="Name überschreiben")


# =============================================================================
# Helper Functions
# =============================================================================

def _preview_to_response(preview: MagicButtonPreview) -> MagicPreviewResponse:
    """Konvertiert Preview zu Response."""
    items = []
    for item in preview.items:
        items.append(PreviewItemResponse(
            type=item.get("type"),
            field=item.get("field"),
            count=item.get("count"),
            value=str(item.get("value")) if item.get("value") else None,
            amount=item.get("amount"),
            label=item.get("label", ""),
        ))

    message = "Bereit zur Ausführung"
    if not preview.can_execute:
        message = preview.block_reason or "Kann nicht ausgeführt werden"
    elif preview.warnings:
        message = f"Warnung: {preview.warnings[0]}"

    return MagicPreviewResponse(
        button_type=preview.button_type.value,
        title=preview.title,
        description=preview.description,
        document_count=preview.document_count,
        transaction_count=preview.transaction_count,
        entity_count=preview.entity_count,
        invoice_count=preview.invoice_count,
        estimated_amount=float(preview.estimated_amount),
        estimated_duration_seconds=preview.estimated_duration_seconds,
        warnings=preview.warnings,
        items=items,
        can_execute=preview.can_execute,
        block_reason=preview.block_reason,
        message=message,
    )


def _result_to_response(result: MagicButtonResult) -> MagicResultResponse:
    """Konvertiert Result zu Response."""
    details = []
    for detail in result.details:
        details.append(MagicResultDetailResponse(
            step=detail.get("step", "unknown"),
            processed=detail.get("processed"),
            matched=detail.get("matched"),
            linked=detail.get("linked"),
            increased=detail.get("increased"),
            skipped=detail.get("skipped"),
            filename=detail.get("filename"),
            document_count=detail.get("document_count"),
            export_id=detail.get("export_id"),
            entity_id=detail.get("entity_id"),
            entity_name=detail.get("entity_name"),
            entity_type=detail.get("entity_type"),
            document_linked=detail.get("document_linked"),
        ))

    return MagicResultResponse(
        button_type=result.button_type.value,
        status=result.status.value,
        title=result.title,
        message=result.message,
        processed_count=result.processed_count,
        success_count=result.success_count,
        error_count=result.error_count,
        skipped_count=result.skipped_count,
        total_amount=float(result.total_amount),
        details=details,
        errors=result.errors,
        duration_ms=result.duration_ms,
        export_file_id=result.export_file_id,
        export_filename=result.export_filename,
    )


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get(
    "/buttons",
    response_model=List[MagicButtonInfoResponse],
    summary="Verfügbare Magic Buttons",
    description="Liste aller verfügbaren Ein-Klick-Aktionen"
)
async def list_magic_buttons(
    current_user: User = Depends(get_current_active_user),
) -> List[MagicButtonInfoResponse]:
    """Liste aller Magic Buttons."""
    return [
        MagicButtonInfoResponse(
            type="daily_close",
            title="Tages-Abschluss",
            description="Verarbeitet alle heutigen Belege und gleicht Transaktionen ab",
            icon="CheckCircle",
            color="green",
        ),
        MagicButtonInfoResponse(
            type="monthly_report",
            title="Monats-Report",
            description="Erstellt DATEV-Export und Zusammenfassung für Steuerberater",
            icon="FileText",
            color="blue",
        ),
        MagicButtonInfoResponse(
            type="clear_open_items",
            title="Offene Posten",
            description="Gleicht Zahlungen ab und verwaltet Mahnungen",
            icon="RefreshCw",
            color="orange",
        ),
        MagicButtonInfoResponse(
            type="create_contact",
            title="Kontakt erstellen",
            description="Erstellt Kunden/Lieferanten aus Dokumentdaten",
            icon="UserPlus",
            color="purple",
        ),
    ]


# =============================================================================
# TAGES-ABSCHLUSS
# =============================================================================

@router.post(
    "/daily-close/preview",
    response_model=MagicPreviewResponse,
    summary="Vorschau Tages-Abschluss",
    description="Zeigt was beim Tages-Abschluss verarbeitet wird"
)
async def preview_daily_close(
    target_date: Optional[date] = Query(None, description="Datum (default: heute)"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicPreviewResponse:
    """Vorschau für Tages-Abschluss."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        preview = await service.preview_daily_close(
            db=db,
            company_id=company_id,
            target_date=target_date,
        )
        return _preview_to_response(preview)

    except Exception as e:
        logger.exception("daily_close_preview_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vorschau konnte nicht erstellt werden"
        )


@router.post(
    "/daily-close/execute",
    response_model=MagicResultResponse,
    summary="Tages-Abschluss ausführen",
    description="Führt den Tages-Abschluss aus"
)
async def execute_daily_close(
    request: DailyCloseRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicResultResponse:
    """Führt Tages-Abschluss aus."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        result = await service.execute_daily_close(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            target_date=request.target_date,
            auto_match=request.auto_match,
            auto_assign=request.auto_assign,
        )
        return _result_to_response(result)

    except Exception as e:
        logger.exception("daily_close_execute_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tages-Abschluss fehlgeschlagen"
        )


# =============================================================================
# MONATS-REPORT
# =============================================================================

@router.post(
    "/monthly-report/preview",
    response_model=MagicPreviewResponse,
    summary="Vorschau Monats-Report",
    description="Zeigt was im Monats-Report enthalten sein wird"
)
async def preview_monthly_report(
    year: int = Query(..., ge=2020, le=2100, description="Jahr"),
    month: int = Query(..., ge=1, le=12, description="Monat"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicPreviewResponse:
    """Vorschau für Monats-Report."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        preview = await service.preview_monthly_report(
            db=db,
            company_id=company_id,
            year=year,
            month=month,
        )
        return _preview_to_response(preview)

    except Exception as e:
        logger.exception("monthly_report_preview_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vorschau konnte nicht erstellt werden"
        )


@router.post(
    "/monthly-report/execute",
    response_model=MagicResultResponse,
    summary="Monats-Report erstellen",
    description="Erstellt den Monats-Report inkl. DATEV-Export"
)
async def execute_monthly_report(
    request: MonthlyReportRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicResultResponse:
    """Erstellt Monats-Report."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        result = await service.execute_monthly_report(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            year=request.year,
            month=request.month,
            include_datev=request.include_datev,
            include_pdf_archive=request.include_pdf_archive,
        )
        return _result_to_response(result)

    except Exception as e:
        logger.exception("monthly_report_execute_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Monats-Report fehlgeschlagen"
        )


# =============================================================================
# OFFENE POSTEN
# =============================================================================

@router.post(
    "/clear-open-items/preview",
    response_model=MagicPreviewResponse,
    summary="Vorschau Offene Posten",
    description="Zeigt offene Posten die bereinigt werden"
)
async def preview_clear_open_items(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicPreviewResponse:
    """Vorschau für Offene-Posten-Bereinigung."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        preview = await service.preview_clear_open_items(
            db=db,
            company_id=company_id,
        )
        return _preview_to_response(preview)

    except Exception as e:
        logger.exception("clear_open_items_preview_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vorschau konnte nicht erstellt werden"
        )


@router.post(
    "/clear-open-items/execute",
    response_model=MagicResultResponse,
    summary="Offene Posten bereinigen",
    description="Gleicht Zahlungen ab und verwaltet Mahnungen"
)
async def execute_clear_open_items(
    request: ClearOpenItemsRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicResultResponse:
    """Bereinigt offene Posten."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        result = await service.execute_clear_open_items(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            auto_reconcile=request.auto_reconcile,
            send_reminders=request.send_reminders,
            increase_dunning=request.increase_dunning,
        )
        return _result_to_response(result)

    except Exception as e:
        logger.exception("clear_open_items_execute_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bereinigung fehlgeschlagen"
        )


# =============================================================================
# KONTAKT ERSTELLEN
# =============================================================================

@router.post(
    "/create-contact/preview",
    response_model=MagicPreviewResponse,
    summary="Vorschau Kontakt erstellen",
    description="Zeigt extrahierte Daten für neuen Kontakt"
)
async def preview_create_contact(
    document_id: UUID = Query(..., description="Dokument-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicPreviewResponse:
    """Vorschau für Kontakt-Erstellung."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        preview = await service.preview_create_contact(
            db=db,
            company_id=company_id,
            document_id=document_id,
        )
        return _preview_to_response(preview)

    except Exception as e:
        logger.exception("create_contact_preview_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vorschau konnte nicht erstellt werden"
        )


@router.post(
    "/create-contact/execute",
    response_model=MagicResultResponse,
    summary="Kontakt erstellen",
    description="Erstellt Kunden/Lieferanten aus Dokumentdaten"
)
async def execute_create_contact(
    request: CreateContactRequest = Body(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MagicResultResponse:
    """Erstellt Kontakt aus Dokument."""
    company_id = await get_user_company_id(db, current_user)
    if not company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Keine Firma zugeordnet"
        )

    service = get_magic_buttons_service()

    try:
        result = await service.execute_create_contact(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            document_id=request.document_id,
            entity_type=request.entity_type,
            override_name=request.override_name,
        )
        return _result_to_response(result)

    except Exception as e:
        logger.exception("create_contact_execute_failed", user_id=str(current_user.id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Kontakt-Erstellung fehlgeschlagen"
        )
