# -*- coding: utf-8 -*-
"""
Budget API Endpoints.

REST API fuer Budgetierung & Controlling:
- CRUD fuer Budgets, Budget-Positionen, Kostenstellen
- Abweichungsberichte (Variance Reports)
- Budget-Alerts
- Auto-Kategorisierung aus OCR

Phase 2.1 der Feature-Roadmap (Januar 2026).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from app.db.models_budget import (
    BudgetPeriodType,
    BudgetStatus,
    BudgetLineStatus,
    AllocationSource,
    AlertSeverity,
)
from app.api.dependencies import get_db, get_current_active_user
from app.services.finance.budget_service import (
    get_budget_service,
    BudgetFilter,
    BudgetCreateRequest,
    BudgetLineCreateRequest,
    AllocationCreateRequest,
    KostenstelleCreateRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/budgets", tags=["Budgets"])


# ============================================================================
# Pydantic Schemas
# ============================================================================


class KostenstelleCreateSchema(BaseModel):
    """Schema fuer Kostenstellen-Erstellung."""
    code: str = Field(..., min_length=1, max_length=50, description="Eindeutiger Code")
    name: str = Field(..., min_length=1, max_length=255, description="Name der Kostenstelle")
    description: Optional[str] = Field(None, max_length=1000)
    parent_id: Optional[UUID] = Field(None, description="Uebergeordnete Kostenstelle")
    responsible_user_id: Optional[UUID] = Field(None, description="Verantwortlicher User")
    category: Optional[str] = Field(None, max_length=100)
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    tags: List[str] = Field(default_factory=list)


class KostenstelleResponse(BaseModel):
    """Response-Schema fuer Kostenstelle."""
    id: UUID
    code: str
    name: str
    description: Optional[str]
    parent_id: Optional[UUID]
    level: int
    path: Optional[str]
    category: Optional[str]
    is_active: bool
    valid_from: Optional[date]
    valid_until: Optional[date]
    tags: List[str]
    created_at: datetime

    class Config:
        from_attributes = True


class KostenstelleTreeNode(BaseModel):
    """Hierarchischer Knoten im Kostenstellen-Baum."""
    id: str
    code: str
    name: str
    level: int
    category: Optional[str]
    children: List["KostenstelleTreeNode"] = Field(default_factory=list)


class BudgetCreateSchema(BaseModel):
    """Schema fuer Budget-Erstellung."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    period_type: BudgetPeriodType = Field(default=BudgetPeriodType.YEARLY)
    year: int = Field(..., ge=2000, le=2100)
    quarter: Optional[int] = Field(None, ge=1, le=4)
    month: Optional[int] = Field(None, ge=1, le=12)
    start_date: date
    end_date: date
    total_planned: float = Field(default=0.0, ge=0)
    currency: str = Field(default="EUR", max_length=3)
    warning_threshold: float = Field(default=80.0, ge=0, le=100)
    critical_threshold: float = Field(default=95.0, ge=0, le=100)
    allow_overspend: bool = Field(default=False)
    previous_budget_id: Optional[UUID] = None


class BudgetResponse(BaseModel):
    """Response-Schema fuer Budget."""
    id: UUID
    name: str
    description: Optional[str]
    period_type: BudgetPeriodType
    year: int
    quarter: Optional[int]
    month: Optional[int]
    start_date: date
    end_date: date
    status: BudgetStatus
    total_planned: float
    total_actual: float
    total_committed: float
    total_remaining: float
    utilization_percent: float
    currency: str
    warning_threshold: float
    critical_threshold: float
    allow_overspend: bool
    created_at: datetime
    approved_at: Optional[datetime]

    class Config:
        from_attributes = True


class BudgetSummaryResponse(BaseModel):
    """Zusammenfassung eines Budgets."""
    budget_id: UUID
    name: str
    period_type: BudgetPeriodType
    year: int
    quarter: Optional[int]
    month: Optional[int]
    status: BudgetStatus
    total_planned: float
    total_actual: float
    total_committed: float
    total_remaining: float
    utilization_percent: float
    lines_count: int
    lines_over_budget: int
    lines_warning: int
    alerts_count: int
    unacknowledged_alerts: int


class BudgetListResponse(BaseModel):
    """Paginierte Budget-Liste."""
    items: List[BudgetResponse]
    total: int
    page: int
    page_size: int


class BudgetLineCreateSchema(BaseModel):
    """Schema fuer Budget-Position-Erstellung."""
    name: str = Field(..., min_length=1, max_length=255)
    category: str = Field(..., min_length=1, max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    account_number: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=1000)
    planned_amount: float = Field(..., ge=0)
    kostenstelle_id: Optional[UUID] = None
    monthly_distribution: Optional[dict] = None
    auto_assign_rules: Optional[List[dict]] = None


class BudgetLineResponse(BaseModel):
    """Response-Schema fuer Budget-Position."""
    id: UUID
    budget_id: UUID
    kostenstelle_id: Optional[UUID]
    kostenstelle_code: Optional[str]
    kostenstelle_name: Optional[str]
    name: str
    category: str
    subcategory: Optional[str]
    account_number: Optional[str]
    description: Optional[str]
    planned_amount: float
    actual_amount: float
    committed_amount: float
    remaining_amount: float
    utilization_percent: float
    status: BudgetLineStatus
    created_at: datetime

    class Config:
        from_attributes = True


class AllocationCreateSchema(BaseModel):
    """Schema fuer Budget-Zuordnung."""
    budget_line_id: UUID
    amount: float = Field(..., gt=0)
    booking_date: date
    kostenstelle_id: Optional[UUID] = None
    document_id: Optional[UUID] = None
    invoice_tracking_id: Optional[UUID] = None
    bank_transaction_id: Optional[UUID] = None
    description: Optional[str] = Field(None, max_length=500)
    reference: Optional[str] = Field(None, max_length=100)
    vendor_name: Optional[str] = Field(None, max_length=255)
    tax_amount: float = Field(default=0.0, ge=0)
    is_committed: bool = Field(default=False)


class AllocationResponse(BaseModel):
    """Response-Schema fuer Budget-Zuordnung."""
    id: UUID
    budget_id: UUID
    budget_line_id: UUID
    kostenstelle_id: Optional[UUID]
    document_id: Optional[UUID]
    amount: float
    tax_amount: float
    net_amount: float
    booking_date: date
    source: AllocationSource
    description: Optional[str]
    reference: Optional[str]
    vendor_name: Optional[str]
    is_committed: bool
    is_processed: bool
    ocr_confidence: Optional[float]
    ocr_extracted_category: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AllocationListResponse(BaseModel):
    """Paginierte Zuordnungs-Liste."""
    items: List[AllocationResponse]
    total: int
    page: int
    page_size: int


class BudgetAlertResponse(BaseModel):
    """Response-Schema fuer Budget-Alert."""
    id: UUID
    budget_id: UUID
    budget_line_id: Optional[UUID]
    severity: AlertSeverity
    title: str
    message: str
    threshold_percent: float
    actual_percent: float
    amount_exceeded: Optional[float]
    is_acknowledged: bool
    acknowledged_at: Optional[datetime]
    notification_sent: bool
    created_at: datetime

    class Config:
        from_attributes = True


class VarianceReportLineSchema(BaseModel):
    """Eine Zeile im Abweichungsbericht."""
    line_id: str
    name: str
    category: str
    subcategory: Optional[str]
    kostenstelle_id: Optional[str]
    kostenstelle_code: Optional[str]
    planned: float
    actual: float
    committed: float
    variance: float
    variance_percent: float
    status: str


class VarianceReportResponse(BaseModel):
    """Abweichungsbericht Response."""
    budget_id: UUID
    period_start: date
    period_end: date
    lines: List[VarianceReportLineSchema]
    total_variance: float
    total_variance_percent: float
    by_category: dict
    by_kostenstelle: dict
    recommendations: List[str]
    generated_at: datetime


class MessageResponse(BaseModel):
    """Einfache Nachricht-Response."""
    message: str


# ============================================================================
# Kostenstellen Endpoints
# ============================================================================


@router.post(
    "/kostenstellen",
    response_model=KostenstelleResponse,
    status_code=201,
    summary="Kostenstelle erstellen",
    description="Erstellt eine neue Kostenstelle"
)
async def create_kostenstelle(
    data: KostenstelleCreateSchema,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> KostenstelleResponse:
    """Erstellt eine neue Kostenstelle."""
    service = get_budget_service()

    try:
        kostenstelle = await service.create_kostenstelle(
            db,
            KostenstelleCreateRequest(
                code=data.code,
                name=data.name,
                company_id=current_user.company_id,
                description=data.description,
                parent_id=data.parent_id,
                responsible_user_id=data.responsible_user_id,
                category=data.category,
                valid_from=data.valid_from,
                valid_until=data.valid_until,
                tags=data.tags,
            )
        )

        return KostenstelleResponse.model_validate(kostenstelle)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("kostenstelle_create_failed")
        raise HTTPException(status_code=500, detail="Fehler beim Erstellen der Kostenstelle")


@router.get(
    "/kostenstellen",
    response_model=List[KostenstelleResponse],
    summary="Kostenstellen auflisten",
    description="Listet alle Kostenstellen der Firma"
)
async def list_kostenstellen(
    include_inactive: bool = Query(False, description="Inaktive einschliessen"),
    parent_id: Optional[UUID] = Query(None, description="Nur Kinder dieser Kostenstelle"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[KostenstelleResponse]:
    """Listet alle Kostenstellen."""
    service = get_budget_service()

    kostenstellen = await service.list_kostenstellen(
        db,
        company_id=current_user.company_id,
        include_inactive=include_inactive,
        parent_id=parent_id,
    )

    return [KostenstelleResponse.model_validate(ks) for ks in kostenstellen]


@router.get(
    "/kostenstellen/tree",
    response_model=List[KostenstelleTreeNode],
    summary="Kostenstellen-Baum",
    description="Gibt hierarchische Kostenstellenstruktur zurueck"
)
async def get_kostenstellen_tree(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[KostenstelleTreeNode]:
    """Gibt Kostenstellen als Baum zurueck."""
    service = get_budget_service()

    tree = await service.get_kostenstelle_tree(db, current_user.company_id)

    return [KostenstelleTreeNode(**node) for node in tree]


# ============================================================================
# Budget Endpoints
# ============================================================================


@router.post(
    "",
    response_model=BudgetResponse,
    status_code=201,
    summary="Budget erstellen",
    description="Erstellt ein neues Budget"
)
async def create_budget(
    data: BudgetCreateSchema,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Erstellt ein neues Budget."""
    service = get_budget_service()

    try:
        budget = await service.create_budget(
            db,
            BudgetCreateRequest(
                name=data.name,
                company_id=current_user.company_id,
                description=data.description,
                period_type=data.period_type,
                year=data.year,
                quarter=data.quarter,
                month=data.month,
                start_date=data.start_date,
                end_date=data.end_date,
                owner_id=current_user.id,
                total_planned=Decimal(str(data.total_planned)),
                currency=data.currency,
                warning_threshold=data.warning_threshold,
                critical_threshold=data.critical_threshold,
                allow_overspend=data.allow_overspend,
                previous_budget_id=data.previous_budget_id,
            )
        )

        return BudgetResponse(
            id=budget.id,
            name=budget.name,
            description=budget.description,
            period_type=budget.period_type,
            year=budget.year,
            quarter=budget.quarter,
            month=budget.month,
            start_date=budget.start_date,
            end_date=budget.end_date,
            status=budget.status,
            total_planned=float(budget.total_planned or 0),
            total_actual=float(budget.total_actual or 0),
            total_committed=float(budget.total_committed or 0),
            total_remaining=float(budget.total_remaining or 0),
            utilization_percent=budget.utilization_percent,
            currency=budget.currency,
            warning_threshold=budget.warning_threshold,
            critical_threshold=budget.critical_threshold,
            allow_overspend=budget.allow_overspend,
            created_at=budget.created_at,
            approved_at=budget.approved_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("budget_create_failed")
        raise HTTPException(status_code=500, detail="Fehler beim Erstellen des Budgets")


@router.get(
    "",
    response_model=BudgetListResponse,
    summary="Budgets auflisten",
    description="Listet Budgets mit Filtern und Paginierung"
)
async def list_budgets(
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Jahr"),
    quarter: Optional[int] = Query(None, ge=1, le=4, description="Quartal"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Monat"),
    period_type: Optional[BudgetPeriodType] = Query(None, description="Perioden-Typ"),
    status: Optional[BudgetStatus] = Query(None, description="Status"),
    page: int = Query(0, ge=0, description="Seite (0-basiert)"),
    page_size: int = Query(25, ge=1, le=100, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetListResponse:
    """Listet Budgets."""
    service = get_budget_service()

    budgets, total = await service.list_budgets(
        db,
        BudgetFilter(
            company_id=current_user.company_id,
            year=year,
            quarter=quarter,
            month=month,
            period_type=period_type,
            status=status,
        ),
        page=page,
        page_size=page_size,
    )

    items = [
        BudgetResponse(
            id=b.id,
            name=b.name,
            description=b.description,
            period_type=b.period_type,
            year=b.year,
            quarter=b.quarter,
            month=b.month,
            start_date=b.start_date,
            end_date=b.end_date,
            status=b.status,
            total_planned=float(b.total_planned or 0),
            total_actual=float(b.total_actual or 0),
            total_committed=float(b.total_committed or 0),
            total_remaining=float(b.total_remaining or 0),
            utilization_percent=b.utilization_percent,
            currency=b.currency,
            warning_threshold=b.warning_threshold,
            critical_threshold=b.critical_threshold,
            allow_overspend=b.allow_overspend,
            created_at=b.created_at,
            approved_at=b.approved_at,
        )
        for b in budgets
    ]

    return BudgetListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{budget_id}",
    response_model=BudgetResponse,
    summary="Budget abrufen",
    description="Ruft ein einzelnes Budget ab"
)
async def get_budget(
    budget_id: UUID = Path(..., description="Budget-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Ruft ein Budget ab."""
    service = get_budget_service()

    budget = await service.get_budget(db, budget_id, include_lines=False)

    if not budget:
        raise HTTPException(status_code=404, detail="Budget nicht gefunden")

    # Pruefe Zugriff
    if budget.company_id != current_user.company_id:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Budget")

    return BudgetResponse(
        id=budget.id,
        name=budget.name,
        description=budget.description,
        period_type=budget.period_type,
        year=budget.year,
        quarter=budget.quarter,
        month=budget.month,
        start_date=budget.start_date,
        end_date=budget.end_date,
        status=budget.status,
        total_planned=float(budget.total_planned or 0),
        total_actual=float(budget.total_actual or 0),
        total_committed=float(budget.total_committed or 0),
        total_remaining=float(budget.total_remaining or 0),
        utilization_percent=budget.utilization_percent,
        currency=budget.currency,
        warning_threshold=budget.warning_threshold,
        critical_threshold=budget.critical_threshold,
        allow_overspend=budget.allow_overspend,
        created_at=budget.created_at,
        approved_at=budget.approved_at,
    )


@router.get(
    "/{budget_id}/summary",
    response_model=BudgetSummaryResponse,
    summary="Budget-Zusammenfassung",
    description="Gibt eine Zusammenfassung des Budgets zurueck"
)
async def get_budget_summary(
    budget_id: UUID = Path(..., description="Budget-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetSummaryResponse:
    """Gibt Budget-Zusammenfassung zurueck."""
    service = get_budget_service()

    summary = await service.get_budget_summary(db, budget_id)

    if not summary:
        raise HTTPException(status_code=404, detail="Budget nicht gefunden")

    return BudgetSummaryResponse(
        budget_id=summary.budget_id,
        name=summary.name,
        period_type=summary.period_type,
        year=summary.year,
        quarter=summary.quarter,
        month=summary.month,
        status=summary.status,
        total_planned=float(summary.total_planned),
        total_actual=float(summary.total_actual),
        total_committed=float(summary.total_committed),
        total_remaining=float(summary.total_remaining),
        utilization_percent=summary.utilization_percent,
        lines_count=summary.lines_count,
        lines_over_budget=summary.lines_over_budget,
        lines_warning=summary.lines_warning,
        alerts_count=summary.alerts_count,
        unacknowledged_alerts=summary.unacknowledged_alerts,
    )


@router.post(
    "/{budget_id}/activate",
    response_model=BudgetResponse,
    summary="Budget aktivieren",
    description="Aktiviert ein Budget (DRAFT -> ACTIVE)"
)
async def activate_budget(
    budget_id: UUID = Path(..., description="Budget-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Aktiviert ein Budget."""
    service = get_budget_service()

    try:
        budget = await service.activate_budget(db, budget_id, current_user.id)

        return BudgetResponse(
            id=budget.id,
            name=budget.name,
            description=budget.description,
            period_type=budget.period_type,
            year=budget.year,
            quarter=budget.quarter,
            month=budget.month,
            start_date=budget.start_date,
            end_date=budget.end_date,
            status=budget.status,
            total_planned=float(budget.total_planned or 0),
            total_actual=float(budget.total_actual or 0),
            total_committed=float(budget.total_committed or 0),
            total_remaining=float(budget.total_remaining or 0),
            utilization_percent=budget.utilization_percent,
            currency=budget.currency,
            warning_threshold=budget.warning_threshold,
            critical_threshold=budget.critical_threshold,
            allow_overspend=budget.allow_overspend,
            created_at=budget.created_at,
            approved_at=budget.approved_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{budget_id}/close",
    response_model=BudgetResponse,
    summary="Budget schliessen",
    description="Schliesst ein Budget ab"
)
async def close_budget(
    budget_id: UUID = Path(..., description="Budget-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetResponse:
    """Schliesst ein Budget."""
    service = get_budget_service()

    try:
        budget = await service.close_budget(db, budget_id)

        return BudgetResponse(
            id=budget.id,
            name=budget.name,
            description=budget.description,
            period_type=budget.period_type,
            year=budget.year,
            quarter=budget.quarter,
            month=budget.month,
            start_date=budget.start_date,
            end_date=budget.end_date,
            status=budget.status,
            total_planned=float(budget.total_planned or 0),
            total_actual=float(budget.total_actual or 0),
            total_committed=float(budget.total_committed or 0),
            total_remaining=float(budget.total_remaining or 0),
            utilization_percent=budget.utilization_percent,
            currency=budget.currency,
            warning_threshold=budget.warning_threshold,
            critical_threshold=budget.critical_threshold,
            allow_overspend=budget.allow_overspend,
            created_at=budget.created_at,
            approved_at=budget.approved_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Budget Lines Endpoints
# ============================================================================


@router.post(
    "/{budget_id}/lines",
    response_model=BudgetLineResponse,
    status_code=201,
    summary="Budget-Position erstellen",
    description="Erstellt eine neue Budget-Position"
)
async def create_budget_line(
    budget_id: UUID = Path(..., description="Budget-ID"),
    data: BudgetLineCreateSchema = ...,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetLineResponse:
    """Erstellt eine Budget-Position."""
    service = get_budget_service()

    try:
        line = await service.create_budget_line(
            db,
            BudgetLineCreateRequest(
                budget_id=budget_id,
                name=data.name,
                category=data.category,
                subcategory=data.subcategory,
                account_number=data.account_number,
                description=data.description,
                planned_amount=Decimal(str(data.planned_amount)),
                kostenstelle_id=data.kostenstelle_id,
                monthly_distribution=data.monthly_distribution,
                auto_assign_rules=data.auto_assign_rules,
            )
        )

        return BudgetLineResponse(
            id=line.id,
            budget_id=line.budget_id,
            kostenstelle_id=line.kostenstelle_id,
            kostenstelle_code=line.kostenstelle.code if line.kostenstelle else None,
            kostenstelle_name=line.kostenstelle.name if line.kostenstelle else None,
            name=line.name,
            category=line.category,
            subcategory=line.subcategory,
            account_number=line.account_number,
            description=line.description,
            planned_amount=float(line.planned_amount),
            actual_amount=float(line.actual_amount or 0),
            committed_amount=float(line.committed_amount or 0),
            remaining_amount=float(line.remaining_amount),
            utilization_percent=line.utilization_percent,
            status=line.status,
            created_at=line.created_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{budget_id}/lines",
    response_model=List[BudgetLineResponse],
    summary="Budget-Positionen auflisten",
    description="Listet alle Positionen eines Budgets"
)
async def list_budget_lines(
    budget_id: UUID = Path(..., description="Budget-ID"),
    category: Optional[str] = Query(None, description="Kategorie-Filter"),
    kostenstelle_id: Optional[UUID] = Query(None, description="Kostenstellen-Filter"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[BudgetLineResponse]:
    """Listet Budget-Positionen."""
    service = get_budget_service()

    lines = await service.list_budget_lines(
        db,
        budget_id,
        category=category,
        kostenstelle_id=kostenstelle_id,
    )

    return [
        BudgetLineResponse(
            id=line.id,
            budget_id=line.budget_id,
            kostenstelle_id=line.kostenstelle_id,
            kostenstelle_code=line.kostenstelle.code if line.kostenstelle else None,
            kostenstelle_name=line.kostenstelle.name if line.kostenstelle else None,
            name=line.name,
            category=line.category,
            subcategory=line.subcategory,
            account_number=line.account_number,
            description=line.description,
            planned_amount=float(line.planned_amount),
            actual_amount=float(line.actual_amount or 0),
            committed_amount=float(line.committed_amount or 0),
            remaining_amount=float(line.remaining_amount),
            utilization_percent=line.utilization_percent,
            status=line.status,
            created_at=line.created_at,
        )
        for line in lines
    ]


# ============================================================================
# Allocations Endpoints
# ============================================================================


@router.post(
    "/{budget_id}/allocations",
    response_model=AllocationResponse,
    status_code=201,
    summary="Budget-Zuordnung erstellen",
    description="Ordnet einen Betrag einer Budget-Position zu"
)
async def create_allocation(
    budget_id: UUID = Path(..., description="Budget-ID"),
    data: AllocationCreateSchema = ...,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AllocationResponse:
    """Erstellt eine Budget-Zuordnung."""
    service = get_budget_service()

    try:
        allocation = await service.create_allocation(
            db,
            AllocationCreateRequest(
                budget_id=budget_id,
                budget_line_id=data.budget_line_id,
                amount=Decimal(str(data.amount)),
                booking_date=data.booking_date,
                source=AllocationSource.MANUAL,
                document_id=data.document_id,
                invoice_tracking_id=data.invoice_tracking_id,
                bank_transaction_id=data.bank_transaction_id,
                kostenstelle_id=data.kostenstelle_id,
                description=data.description,
                reference=data.reference,
                vendor_name=data.vendor_name,
                tax_amount=Decimal(str(data.tax_amount)),
                is_committed=data.is_committed,
                created_by_id=current_user.id,
            )
        )

        return AllocationResponse(
            id=allocation.id,
            budget_id=allocation.budget_id,
            budget_line_id=allocation.budget_line_id,
            kostenstelle_id=allocation.kostenstelle_id,
            document_id=allocation.document_id,
            amount=float(allocation.amount),
            tax_amount=float(allocation.tax_amount or 0),
            net_amount=float(allocation.net_amount or 0),
            booking_date=allocation.booking_date,
            source=allocation.source,
            description=allocation.description,
            reference=allocation.reference,
            vendor_name=allocation.vendor_name,
            is_committed=allocation.is_committed,
            is_processed=allocation.is_processed,
            ocr_confidence=allocation.ocr_confidence,
            ocr_extracted_category=allocation.ocr_extracted_category,
            created_at=allocation.created_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/{budget_id}/allocations",
    response_model=AllocationListResponse,
    summary="Zuordnungen auflisten",
    description="Listet alle Zuordnungen eines Budgets"
)
async def list_allocations(
    budget_id: UUID = Path(..., description="Budget-ID"),
    budget_line_id: Optional[UUID] = Query(None, description="Budget-Position-Filter"),
    date_from: Optional[date] = Query(None, description="Ab Datum"),
    date_to: Optional[date] = Query(None, description="Bis Datum"),
    page: int = Query(0, ge=0, description="Seite"),
    page_size: int = Query(50, ge=1, le=200, description="Eintraege pro Seite"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AllocationListResponse:
    """Listet Zuordnungen."""
    service = get_budget_service()

    allocations, total = await service.list_allocations(
        db,
        budget_id,
        budget_line_id=budget_line_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )

    items = [
        AllocationResponse(
            id=a.id,
            budget_id=a.budget_id,
            budget_line_id=a.budget_line_id,
            kostenstelle_id=a.kostenstelle_id,
            document_id=a.document_id,
            amount=float(a.amount),
            tax_amount=float(a.tax_amount or 0),
            net_amount=float(a.net_amount or 0),
            booking_date=a.booking_date,
            source=a.source,
            description=a.description,
            reference=a.reference,
            vendor_name=a.vendor_name,
            is_committed=a.is_committed,
            is_processed=a.is_processed,
            ocr_confidence=a.ocr_confidence,
            ocr_extracted_category=a.ocr_extracted_category,
            created_at=a.created_at,
        )
        for a in allocations
    ]

    return AllocationListResponse(items=items, total=total, page=page, page_size=page_size)


# ============================================================================
# Variance Report Endpoints
# ============================================================================


@router.get(
    "/{budget_id}/variance-report",
    response_model=VarianceReportResponse,
    summary="Abweichungsbericht",
    description="Generiert Soll/Ist-Abweichungsbericht"
)
async def get_variance_report(
    budget_id: UUID = Path(..., description="Budget-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> VarianceReportResponse:
    """Generiert Abweichungsbericht."""
    service = get_budget_service()

    try:
        report = await service.generate_variance_report(db, budget_id)

        return VarianceReportResponse(
            budget_id=report.budget_id,
            period_start=report.period_start,
            period_end=report.period_end,
            lines=[
                VarianceReportLineSchema(**line_data)
                for line_data in report.lines
            ],
            total_variance=float(report.total_variance),
            total_variance_percent=report.total_variance_percent,
            by_category=report.by_category,
            by_kostenstelle=report.by_kostenstelle,
            recommendations=report.recommendations,
            generated_at=report.generated_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ============================================================================
# Alert Endpoints
# ============================================================================


@router.get(
    "/alerts",
    response_model=List[BudgetAlertResponse],
    summary="Alerts auflisten",
    description="Listet unbestaetigte Budget-Alerts"
)
async def list_alerts(
    severity: Optional[AlertSeverity] = Query(None, description="Schweregrad-Filter"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> List[BudgetAlertResponse]:
    """Listet unbestaetigte Alerts."""
    service = get_budget_service()

    alerts = await service.list_unacknowledged_alerts(
        db,
        company_id=current_user.company_id,
        severity=severity,
    )

    return [
        BudgetAlertResponse(
            id=a.id,
            budget_id=a.budget_id,
            budget_line_id=a.budget_line_id,
            severity=a.severity,
            title=a.title,
            message=a.message,
            threshold_percent=a.threshold_percent,
            actual_percent=a.actual_percent,
            amount_exceeded=float(a.amount_exceeded) if a.amount_exceeded else None,
            is_acknowledged=a.is_acknowledged,
            acknowledged_at=a.acknowledged_at,
            notification_sent=a.notification_sent,
            created_at=a.created_at,
        )
        for a in alerts
    ]


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=BudgetAlertResponse,
    summary="Alert bestaetigen",
    description="Bestaetigt einen Budget-Alert"
)
async def acknowledge_alert(
    alert_id: UUID = Path(..., description="Alert-ID"),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> BudgetAlertResponse:
    """Bestaetigt einen Alert."""
    service = get_budget_service()

    try:
        alert = await service.acknowledge_alert(db, alert_id, current_user.id)

        return BudgetAlertResponse(
            id=alert.id,
            budget_id=alert.budget_id,
            budget_line_id=alert.budget_line_id,
            severity=alert.severity,
            title=alert.title,
            message=alert.message,
            threshold_percent=alert.threshold_percent,
            actual_percent=alert.actual_percent,
            amount_exceeded=float(alert.amount_exceeded) if alert.amount_exceeded else None,
            is_acknowledged=alert.is_acknowledged,
            acknowledged_at=alert.acknowledged_at,
            notification_sent=alert.notification_sent,
            created_at=alert.created_at,
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
