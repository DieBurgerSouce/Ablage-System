"""
Expense API Endpoints - Spesenabrechnung.

Verwaltet Spesenabrechnungen:
- CRUD fuer Reports und Items
- Workflow-Endpunkte (Einreichen, Genehmigen, Ablehnen, Auszahlen)
- Berechnungs-Endpunkte (Kilometergeld, Verpflegungspauschale)

Alle Antworten auf Deutsch.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.dependencies import get_db, get_current_active_user
from app.core.rate_limiting import limiter, get_user_identifier
from app.db.models import User, Company, ExpenseReport, ExpenseItem
from app.db.schemas import (
    # Report
    ExpenseReportCreate,
    ExpenseReportUpdate,
    ExpenseReportResponse,
    ExpenseReportListResponse,
    # Items
    ExpenseItemCreate,
    ExpenseItemUpdate,
    ExpenseItemResponse,
    # Workflow
    ExpenseReportApproveRequest,
    ExpenseReportRejectRequest,
    ExpenseReportPayRequest,
    # Calculators
    PerDiemCalculateRequest,
    PerDiemCalculation,
    MileageCalculateRequest,
    MileageCalculation,
    # Enums
    ExpenseReportStatus,
    ExpenseType,
)
from app.middleware.company_context import (
    require_company,
    require_expense_approval_permission,
)
from app.services.expense_service import ExpenseService

logger = structlog.get_logger(__name__)

# ==================== Routers ====================

reports_router = APIRouter(prefix="/expenses/reports", tags=["Spesen - Abrechnungen"])
items_router = APIRouter(prefix="/expenses/items", tags=["Spesen - Positionen"])
workflow_router = APIRouter(prefix="/expenses/reports", tags=["Spesen - Workflow"])
calculators_router = APIRouter(prefix="/expenses/calculate", tags=["Spesen - Rechner"])

# Service Instanz
expense_service = ExpenseService()


# ==================== Report Endpoints ====================

@reports_router.get(
    "",
    response_model=ExpenseReportListResponse,
    summary="Spesenabrechnungen auflisten",
    description="Gibt alle Spesenabrechnungen mit optionaler Filterung zurueck."
)
async def list_reports(
    request: Request,
    employee_id: Optional[UUID] = Query(None, description="Filter nach Mitarbeiter"),
    status_filter: Optional[ExpenseReportStatus] = Query(
        None, description="Filter nach Status", alias="status"
    ),
    start_date: Optional[date] = Query(None, description="Filter Periode ab"),
    end_date: Optional[date] = Query(None, description="Filter Periode bis"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ExpenseReportListResponse:
    """Liste der Spesenabrechnungen."""

    reports, total = await expense_service.get_reports(
        db=db,
        company_id=company.id,
        employee_id=employee_id,
        status=status_filter,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )

    return ExpenseReportListResponse(
        items=[_map_report_to_response(r) for r in reports],
        total=total,
    )


@reports_router.post(
    "",
    response_model=ExpenseReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Spesenabrechnung erstellen",
    description="Erstellt eine neue Spesenabrechnung im Entwurf-Status."
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # SECURITY FIX 30
async def create_report(
    data: ExpenseReportCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ExpenseReportResponse:
    """Erstellt eine neue Spesenabrechnung."""

    report = await expense_service.create_report(
        db=db,
        company_id=company.id,
        data=data,
        user_id=current_user.id,
    )

    return _map_report_to_response(report)


@reports_router.get(
    "/{report_id}",
    response_model=ExpenseReportResponse,
    summary="Spesenabrechnung abrufen",
    description="Gibt Details einer Spesenabrechnung zurueck."
)
async def get_report(
    report_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ExpenseReportResponse:
    """Gibt eine Spesenabrechnung zurueck."""

    report = await expense_service.get_report(
        db=db,
        report_id=report_id,
        company_id=company.id,
    )

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spesenabrechnung nicht gefunden."
        )

    return _map_report_to_response(report)


@reports_router.put(
    "/{report_id}",
    response_model=ExpenseReportResponse,
    summary="Spesenabrechnung aktualisieren",
    description="Aktualisiert eine Spesenabrechnung (nur Entwuerfe)."
)
async def update_report(
    report_id: UUID,
    data: ExpenseReportUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ExpenseReportResponse:
    """Aktualisiert eine Spesenabrechnung."""

    try:
        report = await expense_service.update_report(
            db=db,
            report_id=report_id,
            company_id=company.id,
            data=data,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spesenabrechnung nicht gefunden."
        )

    return _map_report_to_response(report)


@reports_router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Spesenabrechnung loeschen",
    description="Loescht eine Spesenabrechnung (nur Entwuerfe)."
)
async def delete_report(
    report_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> Response:
    """Loescht eine Spesenabrechnung."""

    try:
        success = await expense_service.delete_report(
            db=db,
            report_id=report_id,
            company_id=company.id,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spesenabrechnung nicht gefunden."
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Item Endpoints ====================

@reports_router.post(
    "/{report_id}/items",
    response_model=ExpenseItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Position hinzufuegen",
    description="Fuegt eine Position zu einer Spesenabrechnung hinzu."
)
@limiter.limit("20/minute", key_func=get_user_identifier)  # SECURITY FIX 30
async def add_item(
    report_id: UUID,
    data: ExpenseItemCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ExpenseItemResponse:
    """Fuegt eine Position hinzu."""

    try:
        item = await expense_service.add_item(
            db=db,
            report_id=report_id,
            company_id=company.id,
            data=data,
            user_id=current_user.id,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    return _map_item_to_response(item)


@items_router.put(
    "/{item_id}",
    response_model=ExpenseItemResponse,
    summary="Position aktualisieren",
    description="Aktualisiert eine Position (nur in Entwuerfen)."
)
async def update_item(
    item_id: UUID,
    data: ExpenseItemUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ExpenseItemResponse:
    """Aktualisiert eine Position."""

    try:
        item = await expense_service.update_item(
            db=db,
            item_id=item_id,
            company_id=company.id,
            data=data,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Position nicht gefunden."
        )

    return _map_item_to_response(item)


@items_router.delete(
    "/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Position loeschen",
    description="Loescht eine Position (nur in Entwuerfen)."
)
async def delete_item(
    item_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> Response:
    """Loescht eine Position."""

    try:
        success = await expense_service.delete_item(
            db=db,
            item_id=item_id,
            company_id=company.id,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Position nicht gefunden."
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==================== Workflow Endpoints ====================

@workflow_router.post(
    "/{report_id}/submit",
    response_model=ExpenseReportResponse,
    summary="Spesenabrechnung einreichen",
    description="Reicht eine Spesenabrechnung zur Pruefung ein."
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # SECURITY FIX 30
async def submit_report(
    report_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ExpenseReportResponse:
    """Reicht eine Spesenabrechnung ein."""

    try:
        report = await expense_service.submit_report(
            db=db,
            report_id=report_id,
            company_id=company.id,
            user_id=current_user.id,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    return _map_report_to_response(report)


@workflow_router.post(
    "/{report_id}/approve",
    response_model=ExpenseReportResponse,
    summary="Spesenabrechnung genehmigen",
    description="Genehmigt eine eingereichte Spesenabrechnung."
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # SECURITY FIX 30
async def approve_report(
    report_id: UUID,
    data: ExpenseReportApproveRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_expense_approval_permission),
) -> ExpenseReportResponse:
    """Genehmigt eine Spesenabrechnung."""

    try:
        report = await expense_service.approve_report(
            db=db,
            report_id=report_id,
            company_id=company.id,
            user_id=current_user.id,
            approved_amount=data.approved_amount,
            notes=data.notes,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    return _map_report_to_response(report)


@workflow_router.post(
    "/{report_id}/reject",
    response_model=ExpenseReportResponse,
    summary="Spesenabrechnung ablehnen",
    description="Lehnt eine eingereichte Spesenabrechnung ab."
)
@limiter.limit("10/minute", key_func=get_user_identifier)  # SECURITY FIX 30
async def reject_report(
    report_id: UUID,
    data: ExpenseReportRejectRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_expense_approval_permission),
) -> ExpenseReportResponse:
    """Lehnt eine Spesenabrechnung ab."""

    try:
        report = await expense_service.reject_report(
            db=db,
            report_id=report_id,
            company_id=company.id,
            user_id=current_user.id,
            reason=data.reason,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    return _map_report_to_response(report)


@workflow_router.post(
    "/{report_id}/pay",
    response_model=ExpenseReportResponse,
    summary="Spesenabrechnung auszahlen",
    description="Markiert eine genehmigte Spesenabrechnung als ausgezahlt. "
                "Optional mit Kassenbuchung."
)
@limiter.limit("5/minute", key_func=get_user_identifier)  # SECURITY FIX 30 (stricter for payments)
async def pay_report(
    report_id: UUID,
    data: ExpenseReportPayRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_expense_approval_permission),
) -> ExpenseReportResponse:
    """Zahlt eine Spesenabrechnung aus."""

    try:
        report = await expense_service.mark_as_paid(
            db=db,
            report_id=report_id,
            company_id=company.id,
            user_id=current_user.id,
            register_id=data.register_id,
        )
    except ValueError as e:
        # SECURITY FIX 29: Generic error message - no internal details
        logger.warning("expense_validation_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ungueltige Anfrage. Bitte Eingaben pruefen."
        )

    return _map_report_to_response(report)


# ==================== Calculator Endpoints ====================

@calculators_router.post(
    "/per-diem",
    response_model=PerDiemCalculation,
    summary="Verpflegungspauschale berechnen",
    description="Berechnet die Verpflegungspauschale basierend auf Reisedauer."
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY FIX 30 (calculation can be more frequent)
async def calculate_per_diem(
    data: PerDiemCalculateRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> PerDiemCalculation:
    """Berechnet Verpflegungspauschale."""

    calculation = expense_service.calculate_per_diem(
        travel_start=data.travel_start,
        travel_end=data.travel_end,
        meals_provided=data.meals_provided or {},
        country=data.country or "DE",
    )

    return calculation


@calculators_router.post(
    "/mileage",
    response_model=MileageCalculation,
    summary="Kilometergeld berechnen",
    description="Berechnet das Kilometergeld basierend auf gefahrenen Kilometern."
)
@limiter.limit("30/minute", key_func=get_user_identifier)  # SECURITY FIX 30 (calculation can be more frequent)
async def calculate_mileage(
    data: MileageCalculateRequest,
    request: Request,
    current_user: User = Depends(get_current_active_user),
) -> MileageCalculation:
    """Berechnet Kilometergeld."""

    calculation = expense_service.calculate_mileage(
        kilometers=data.kilometers,
        rate_per_km=data.rate_per_km,
    )

    return calculation


# ==================== Helper Functions ====================

def _map_report_to_response(report: ExpenseReport) -> ExpenseReportResponse:
    """Mappt ExpenseReport auf Response-Schema."""
    return ExpenseReportResponse(
        id=report.id,
        company_id=report.company_id,
        report_number=report.report_number,
        title=report.title,
        description=report.description,
        status=report.status,
        employee_id=report.employee_id,
        employee_name=report.employee.full_name if report.employee else None,
        period_start=report.period_start,
        period_end=report.period_end,
        # Betraege
        total_amount=float(report.total_amount) if report.total_amount else 0.0,
        total_vat=float(report.total_vat) if report.total_vat else 0.0,
        total_deductible=float(report.total_deductible) if report.total_deductible else 0.0,
        travel_days=report.travel_days or 0,
        travel_allowance_total=float(report.travel_allowance_total) if report.travel_allowance_total else 0.0,
        total_kilometers=float(report.total_kilometers) if report.total_kilometers else 0.0,
        mileage_allowance_total=float(report.mileage_allowance_total) if report.mileage_allowance_total else 0.0,
        # Workflow
        submitted_at=report.submitted_at,
        reviewed_at=report.reviewed_at,
        review_notes=report.review_notes,
        approved_at=report.approved_at,
        rejected_at=report.rejected_at,
        rejection_reason=report.rejection_reason,
        paid_at=report.paid_at,
        payment_method=report.payment_method,
        payment_reference=report.payment_reference,
        cash_entry_id=report.cash_entry_id,
        datev_exported_at=report.datev_exported_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _map_item_to_response(item: ExpenseItem) -> ExpenseItemResponse:
    """Mappt ExpenseItem auf Response-Schema."""
    return ExpenseItemResponse(
        id=item.id,
        report_id=item.report_id,
        expense_date=item.expense_date,
        expense_type=ExpenseType(item.expense_type),
        description=item.description,
        amount=item.amount,
        currency=item.currency,
        exchange_rate=item.exchange_rate,
        amount_eur=item.amount_eur,
        tax_rate=item.tax_rate,
        net_amount=item.net_amount,
        tax_amount=item.tax_amount,
        category_id=item.category_id,
        category_name=item.category.name if item.category else None,
        receipt_number=item.receipt_number,
        receipt_document_id=item.receipt_document_id,
        vendor=item.vendor,
        is_entertainment=item.is_entertainment,
        entertainment_data=item.entertainment_data,
        mileage_km=item.mileage_km,
        mileage_from=item.mileage_from,
        mileage_to=item.mileage_to,
        mileage_purpose=item.mileage_purpose,
        per_diem_hours=item.per_diem_hours,
        per_diem_meals_provided=item.per_diem_meals_provided,
        per_diem_country=item.per_diem_country,
        notes=item.notes,
        is_approved=item.is_approved,
        approved_amount=item.approved_amount,
        deductible_amount=item.deductible_amount,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


# ==================== Combined Router ====================

router = APIRouter()
router.include_router(reports_router)
router.include_router(items_router)
router.include_router(workflow_router)
router.include_router(calculators_router)
