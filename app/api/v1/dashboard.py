"""
Dashboard API Endpoints.

Enterprise-Level Dashboard-Management:
- CRUD für personalisierte Dashboards
- Widget-Management mit Drag & Drop Layout
- Permission-basierte Widget-Filterung
- Dashboard-Templates
- Aggregierte KPIs aus allen Services

Feinpoliert und durchdacht - Personalisierte Dashboards auf Enterprise-Niveau.
"""

import structlog
from datetime import datetime, timedelta
from typing import List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User, Document, InvoiceTracking, Alert
from app.db.models_privat_enterprise import ApprovalRequest, ApprovalStatus
from app.services.dashboard_service import DashboardService
from app.services.banking.cash_flow_service import cash_flow_service
from app.services.approval.approval_service import ApprovalService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class WidgetPositionSchema(BaseModel):
    """Widget-Position im Grid."""

    x: int = Field(default=0, ge=0, description="X-Position im Grid")
    y: int = Field(default=0, ge=0, description="Y-Position im Grid")
    w: int = Field(default=4, ge=1, le=12, description="Breite in Grid-Einheiten")
    h: int = Field(default=3, ge=1, le=10, description="Höhe in Grid-Einheiten")
    minW: Optional[int] = Field(None, description="Minimale Breite")
    minH: Optional[int] = Field(None, description="Minimale Höhe")
    maxW: Optional[int] = Field(None, description="Maximale Breite")
    maxH: Optional[int] = Field(None, description="Maximale Höhe")


class WidgetCreate(BaseModel):
    """Schema für neues Widget."""

    widget_type: str = Field(..., min_length=1, max_length=50)
    position: Optional[WidgetPositionSchema] = None
    config: Optional[JSONDict] = None
    title_override: Optional[str] = Field(None, max_length=100)


class WidgetUpdate(BaseModel):
    """Schema für Widget-Update."""

    position: Optional[WidgetPositionSchema] = None
    config: Optional[JSONDict] = None
    title_override: Optional[str] = None
    is_visible: Optional[bool] = None
    is_collapsed: Optional[bool] = None


class WidgetResponse(BaseModel):
    """Response Schema für Widget."""

    id: str
    widget_type: str
    x: int
    y: int
    w: int
    h: int
    minW: Optional[int] = None
    minH: Optional[int] = None
    maxW: Optional[int] = None
    maxH: Optional[int] = None
    config: Optional[JSONDict] = None
    title_override: Optional[str] = None
    filter_overrides: Optional[JSONDict] = None
    is_visible: bool = True
    is_collapsed: bool = False
    sort_order: int = 0


class DashboardCreate(BaseModel):
    """Schema für neues Dashboard."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_default: bool = False
    columns: int = Field(default=12, ge=1, le=24)
    row_height: int = Field(default=80, ge=20, le=200)
    compact_type: Optional[str] = Field(None, pattern="^(vertical|horizontal)$")
    widgets: Optional[List[JSONDict]] = None


class DashboardUpdate(BaseModel):
    """Schema für Dashboard-Update."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_default: Optional[bool] = None
    columns: Optional[int] = Field(None, ge=1, le=24)
    row_height: Optional[int] = Field(None, ge=20, le=200)
    compact_type: Optional[str] = None
    default_date_range: Optional[str] = None
    default_company_id: Optional[str] = None


class DashboardResponse(BaseModel):
    """Response Schema für Dashboard."""

    id: str
    name: str
    description: Optional[str] = None
    is_default: bool
    columns: int
    row_height: int
    compact_type: Optional[str] = None
    default_date_range: Optional[str] = None
    default_company_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    widgets: List[WidgetResponse] = []


class DashboardListItem(BaseModel):
    """Response Schema für Dashboard-Liste."""

    id: str
    name: str
    description: Optional[str] = None
    is_default: bool
    widget_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LayoutUpdate(BaseModel):
    """Schema für Layout-Update (Batch)."""

    widgets: List[JSONDict] = Field(..., description="Liste von Widget-Positionen mit ID")


class AvailableWidget(BaseModel):
    """Schema für verfügbare Widgets."""

    widget_type: str
    requires_permission: bool
    required_permissions: Optional[List[str]] = None


class TemplateResponse(BaseModel):
    """Response Schema für Dashboard-Template."""

    id: str
    name: str
    description: Optional[str] = None
    category: str
    for_roles: Optional[List[str]] = None
    layout: List[JSONDict]
    preview_image_url: Optional[str] = None


# =============================================================================
# KPI Aggregation Schemas
# =============================================================================


class InvoiceKPIs(BaseModel):
    """Rechnungs-KPIs."""

    total_open: int = Field(description="Anzahl offener Rechnungen")
    total_overdue: int = Field(description="Anzahl überfälliger Rechnungen")
    open_amount: float = Field(description="Offener Gesamtbetrag")
    overdue_amount: float = Field(description="Überfälliger Betrag")
    paid_this_month: int = Field(description="Bezahlte Rechnungen diesen Monat")
    avg_payment_days: float = Field(description="Durchschnittliche Zahlungsdauer")


class CashFlowKPIs(BaseModel):
    """Cashflow-KPIs."""

    current_balance: float = Field(description="Aktueller Kontostand")
    expected_income_30d: float = Field(description="Erwartete Einnahmen 30 Tage")
    expected_expenses_30d: float = Field(description="Erwartete Ausgaben 30 Tage")
    net_cash_flow_30d: float = Field(description="Netto-Cashflow 30 Tage")
    trend: str = Field(description="Trend (positive/negative/stable)")


class AlertKPIs(BaseModel):
    """Alert-KPIs."""

    total_active: int = Field(description="Aktive Alerts gesamt")
    critical: int = Field(description="Kritische Alerts")
    high: int = Field(description="Hohe Prioritaet")
    medium: int = Field(description="Mittlere Prioritaet")
    new_today: int = Field(description="Neue Alerts heute")


class ApprovalKPIs(BaseModel):
    """Genehmigungs-KPIs."""

    pending_total: int = Field(description="Ausstehende Genehmigungen gesamt")
    my_pending: int = Field(description="Meine ausstehenden Genehmigungen")
    overdue: int = Field(description="Überfällige Genehmigungen")
    approved_this_week: int = Field(description="Diese Woche genehmigt")


class OCRQualityKPIs(BaseModel):
    """OCR-Qualitaets-KPIs."""

    documents_today: int = Field(description="Dokumente heute verarbeitet")
    success_rate: Optional[float] = Field(
        default=None, description="Erfolgsquote in Prozent (None = nicht verfügbar)"
    )
    avg_confidence: Optional[float] = Field(
        default=None, description="Durchschnittliche Confidence (None = nicht verfügbar)"
    )
    manual_corrections: Optional[int] = Field(
        default=None, description="Manuelle Korrekturen heute (None = nicht verfügbar)"
    )


class DocumentKPIs(BaseModel):
    """Dokumenten-KPIs."""

    total_documents: int = Field(description="Dokumente gesamt")
    documents_today: int = Field(description="Dokumente heute")
    documents_this_week: int = Field(description="Dokumente diese Woche")
    pending_review: int = Field(description="Zur Prüfung ausstehend")


class AggregatedKPIsResponse(BaseModel):
    """Aggregierte KPIs für Dashboard."""

    invoices: InvoiceKPIs
    cash_flow: CashFlowKPIs
    alerts: AlertKPIs
    approvals: ApprovalKPIs
    ocr_quality: OCRQualityKPIs
    documents: DocumentKPIs
    last_updated: str = Field(description="Zeitpunkt der Datenerhebung")


# =============================================================================
# Dashboard Endpoints
# =============================================================================


@router.get("", response_model=DashboardResponse)
async def get_default_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Gibt das Standard-Dashboard des Benutzers zurück.

    Erstellt automatisch ein Default-Dashboard falls noch keines existiert.
    """
    service = DashboardService(db)
    dashboard = await service.get_user_dashboard(current_user.id)

    if not dashboard:
        # Erstelle Default-Dashboard
        dashboard = await service.create_default_dashboard(current_user.id)
        logger.info(
            "default_dashboard_created",
            user_id=str(current_user.id),
        )

    return DashboardResponse(**dashboard)


@router.get("/list", response_model=List[DashboardListItem])
async def list_dashboards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DashboardListItem]:
    """
    Listet alle Dashboards des Benutzers auf.
    """
    service = DashboardService(db)
    dashboards = await service.list_user_dashboards(current_user.id)
    return [DashboardListItem(**d) for d in dashboards]


@router.get("/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Gibt ein spezifisches Dashboard zurück.
    """
    service = DashboardService(db)
    dashboard = await service.get_user_dashboard(current_user.id, dashboard_id)

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    return DashboardResponse(**dashboard)


@router.post("", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    data: DashboardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Erstellt ein neues Dashboard.
    """
    service = DashboardService(db)
    dashboard = await service.create_dashboard(
        user_id=current_user.id,
        name=data.name,
        description=data.description,
        is_default=data.is_default,
        columns=data.columns,
        row_height=data.row_height,
        compact_type=data.compact_type,
        widgets=data.widgets,
    )

    logger.info(
        "dashboard_created_api",
        dashboard_id=dashboard["id"],
        user_id=str(current_user.id),
    )

    return DashboardResponse(**dashboard)


@router.put("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: UUID,
    data: DashboardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Aktualisiert Dashboard-Einstellungen.
    """
    service = DashboardService(db)

    # Parse company_id if provided
    company_id = None
    if data.default_company_id:
        try:
            company_id = UUID(data.default_company_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ungültige Company-ID",
            )

    dashboard = await service.update_dashboard(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        name=data.name,
        description=data.description,
        is_default=data.is_default,
        columns=data.columns,
        row_height=data.row_height,
        compact_type=data.compact_type,
        default_date_range=data.default_date_range,
        default_company_id=company_id,
    )

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    return DashboardResponse(**dashboard)


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_dashboard(
    dashboard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Löscht ein Dashboard.

    Das letzte Dashboard kann nicht gelöscht werden.
    """
    service = DashboardService(db)
    deleted = await service.delete_dashboard(current_user.id, dashboard_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dashboard konnte nicht gelöscht werden. Mindestens ein Dashboard muss existieren.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Layout Endpoints
# =============================================================================


@router.put("/{dashboard_id}/layout", status_code=status.HTTP_200_OK)
async def update_layout(
    dashboard_id: UUID,
    data: LayoutUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Aktualisiert das komplette Layout (alle Widget-Positionen).

    Wird bei Drag & Drop verwendet.
    """
    service = DashboardService(db)
    updated = await service.update_layout(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        widgets=data.widgets,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    return {"success": True, "message": "Layout aktualisiert"}


# =============================================================================
# Widget Endpoints
# =============================================================================


@router.get("/widgets/available", response_model=List[AvailableWidget])
async def get_available_widgets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[AvailableWidget]:
    """
    Listet alle verfügbaren Widgets basierend auf Benutzerberechtigungen auf.
    """
    service = DashboardService(db)

    # Get user permissions (simplified - in production would come from RBAC)
    user_permissions = await _get_user_permissions(current_user)

    widgets = await service.get_available_widgets(user_permissions)
    return [AvailableWidget(**w) for w in widgets]


@router.post("/{dashboard_id}/widgets", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
async def add_widget(
    dashboard_id: UUID,
    data: WidgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WidgetResponse:
    """
    Fuegt ein neues Widget zum Dashboard hinzu.
    """
    service = DashboardService(db)

    # Check widget permission
    user_permissions = await _get_user_permissions(current_user)
    if not service.can_view_widget(data.widget_type, user_permissions):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Keine Berechtigung für dieses Widget",
        )

    position = data.position.model_dump() if data.position else None
    widget = await service.add_widget(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        widget_type=data.widget_type,
        position=position,
        config=data.config,
    )

    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    return WidgetResponse(**widget)


@router.put("/{dashboard_id}/widgets/{widget_id}", response_model=WidgetResponse)
async def update_widget(
    dashboard_id: UUID,
    widget_id: UUID,
    data: WidgetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WidgetResponse:
    """
    Aktualisiert ein Widget.
    """
    service = DashboardService(db)
    position = data.position.model_dump() if data.position else None

    widget = await service.update_widget(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        widget_id=widget_id,
        position=position,
        config=data.config,
        title_override=data.title_override,
        is_visible=data.is_visible,
        is_collapsed=data.is_collapsed,
    )

    if not widget:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget nicht gefunden",
        )

    return WidgetResponse(**widget)


@router.delete("/{dashboard_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_widget(
    dashboard_id: UUID,
    widget_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Entfernt ein Widget vom Dashboard.
    """
    service = DashboardService(db)
    removed = await service.remove_widget(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        widget_id=widget_id,
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Widget nicht gefunden",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Template Endpoints
# =============================================================================


@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[TemplateResponse]:
    """
    Listet verfügbare Dashboard-Templates auf.
    """
    service = DashboardService(db)

    # Get user roles
    user_roles = [current_user.role] if hasattr(current_user, "role") else ["viewer"]

    templates = await service.get_templates(
        user_roles=user_roles,
        category=category,
    )

    return [TemplateResponse(**t) for t in templates]


@router.post("/templates/{template_id}/apply", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def apply_template(
    template_id: UUID,
    name: Optional[str] = Query(None, description="Benutzerdefinierter Name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Erstellt ein neues Dashboard basierend auf einem Template.
    """
    service = DashboardService(db)
    dashboard = await service.apply_template(
        user_id=current_user.id,
        template_id=template_id,
        dashboard_name=name,
    )

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden",
        )

    logger.info(
        "template_applied",
        template_id=str(template_id),
        user_id=str(current_user.id),
    )

    return DashboardResponse(**dashboard)


# =============================================================================
# KPI Aggregation Endpoints
# =============================================================================


@router.get("/kpis", response_model=AggregatedKPIsResponse)
async def get_aggregated_kpis(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AggregatedKPIsResponse:
    """
    Gibt aggregierte KPIs aus allen Services zurück.

    Kombiniert Daten aus:
    - Rechnungswesen (Invoices)
    - Cashflow/Banking
    - Alert Center
    - Genehmigungsworkflows
    - OCR-Qualitaet
    - Dokumenten-Statistiken
    """
    company_id = getattr(current_user, "company_id", None)
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    # Invoice KPIs
    invoice_kpis = await _get_invoice_kpis(db, company_id, now, month_start)

    # Cash Flow KPIs (simplified - would integrate with banking service)
    cash_flow_kpis = await _get_cash_flow_kpis(db, company_id)

    # Alert KPIs
    alert_kpis = await _get_alert_kpis(db, company_id, today_start)

    # Approval KPIs
    approval_kpis = await _get_approval_kpis(db, current_user.id, company_id, week_start)

    # OCR Quality KPIs
    ocr_kpis = await _get_ocr_quality_kpis(db, company_id, today_start)

    # Document KPIs
    document_kpis = await _get_document_kpis(db, company_id, today_start, week_start)

    return AggregatedKPIsResponse(
        invoices=invoice_kpis,
        cash_flow=cash_flow_kpis,
        alerts=alert_kpis,
        approvals=approval_kpis,
        ocr_quality=ocr_kpis,
        documents=document_kpis,
        last_updated=now.isoformat(),
    )


async def _get_invoice_kpis(
    db: AsyncSession, company_id: Optional[UUID], now: datetime, month_start: datetime
) -> InvoiceKPIs:
    """Berechnet Rechnungs-KPIs."""
    try:
        # Build base query conditions
        conditions = []
        if company_id:
            conditions.append(InvoiceTracking.company_id == company_id)

        # Count open invoices
        open_query = select(func.count(InvoiceTracking.id)).where(
            InvoiceTracking.status.in_(["open", "partially_paid"]),
            *conditions
        )
        open_result = await db.execute(open_query)
        total_open = open_result.scalar() or 0

        # Count overdue invoices
        overdue_query = select(func.count(InvoiceTracking.id)).where(
            InvoiceTracking.status.in_(["open", "partially_paid"]),
            InvoiceTracking.due_date < now,
            *conditions
        )
        overdue_result = await db.execute(overdue_query)
        total_overdue = overdue_result.scalar() or 0

        # Sum open amounts
        open_amount_query = select(func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0.0)).where(
            InvoiceTracking.status.in_(["open", "partially_paid"]),
            *conditions
        )
        open_amount_result = await db.execute(open_amount_query)
        open_amount = float(open_amount_result.scalar() or 0)

        # Sum overdue amounts
        overdue_amount_query = select(func.coalesce(func.sum(InvoiceTracking.outstanding_amount), 0.0)).where(
            InvoiceTracking.status.in_(["open", "partially_paid"]),
            InvoiceTracking.due_date < now,
            *conditions
        )
        overdue_amount_result = await db.execute(overdue_amount_query)
        overdue_amount = float(overdue_amount_result.scalar() or 0)

        # Count paid this month
        paid_query = select(func.count(InvoiceTracking.id)).where(
            InvoiceTracking.status == "paid",
            InvoiceTracking.paid_at >= month_start,
            *conditions
        )
        paid_result = await db.execute(paid_query)
        paid_this_month = paid_result.scalar() or 0

        # Durchschnittliche Zahlungsdauer in Tagen: echte Aggregation über bezahlte
        # Rechnungen (paid_at - invoice_date), company-gefiltert. 0 Rows -> 0.0.
        # Eigenes try/except, damit ein DB-Dialekt ohne EXTRACT('epoch', ...) (z.B.
        # SQLite im Test) die übrigen KPIs nicht mit herunterzieht.
        avg_payment_days = 0.0
        try:
            avg_days_query = select(
                func.avg(
                    func.extract(
                        "epoch",
                        InvoiceTracking.paid_at - InvoiceTracking.invoice_date,
                    )
                    / 86400.0
                )
            ).where(
                InvoiceTracking.status == "paid",
                InvoiceTracking.paid_at.isnot(None),
                InvoiceTracking.invoice_date.isnot(None),
                *conditions,
            )
            avg_days_result = await db.execute(avg_days_query)
            avg_days_value = avg_days_result.scalar()
            if avg_days_value is not None:
                avg_payment_days = round(float(avg_days_value), 1)
        except Exception as e:  # noqa: BLE001 - KPI degradiert auf 0.0
            logger.warning("avg_payment_days_error", error=str(e))

        return InvoiceKPIs(
            total_open=total_open,
            total_overdue=total_overdue,
            open_amount=open_amount,
            overdue_amount=overdue_amount,
            paid_this_month=paid_this_month,
            avg_payment_days=avg_payment_days,
        )
    except Exception as e:
        logger.warning("invoice_kpis_error", error=str(e))
        return InvoiceKPIs(
            total_open=0,
            total_overdue=0,
            open_amount=0.0,
            overdue_amount=0.0,
            paid_this_month=0,
            avg_payment_days=0.0,
        )


async def _get_cash_flow_kpis(db: AsyncSession, company_id: Optional[UUID]) -> CashFlowKPIs:
    """Berechnet Cashflow-KPIs über den CashFlowService (30-Tage-Horizont)."""
    # Ohne Firmenzuordnung keine mandantengetrennten Zahlen -> neutrale 0-Werte.
    if not company_id:
        return CashFlowKPIs(
            current_balance=0.0,
            expected_income_30d=0.0,
            expected_expenses_30d=0.0,
            net_cash_flow_30d=0.0,
            trend="stable",
        )
    try:
        summary = await cash_flow_service.get_cash_flow_summary(db, company_id)
        mid_term = summary.get("mid_term", {})
        income = float(mid_term.get("inflow", 0.0))
        expenses = float(mid_term.get("outflow", 0.0))
        net = float(mid_term.get("net", income - expenses))

        # Trend aus Netto-Cashflow ableiten
        if net > 0:
            trend = "positive"
        elif net < 0:
            trend = "negative"
        else:
            trend = "stable"

        return CashFlowKPIs(
            # current_balance ist NICHT Teil der Cash-Flow-Summary (Interface-Kontrakt M1).
            # Eine dedizierte Kontostand-Lesemethode liefert G4 spaeter nach.
            current_balance=0.0,  # TODO(G4): Kontostand-Lesemethode anbinden
            expected_income_30d=income,
            expected_expenses_30d=expenses,
            net_cash_flow_30d=net,
            trend=trend,
        )
    except Exception as e:  # noqa: BLE001 - KPI degradiert sauber, kein HTTP-500
        logger.warning("cash_flow_kpis_error", error=str(e))
        return CashFlowKPIs(
            current_balance=0.0,
            expected_income_30d=0.0,
            expected_expenses_30d=0.0,
            net_cash_flow_30d=0.0,
            trend="stable",
        )


async def _get_alert_kpis(
    db: AsyncSession, company_id: Optional[UUID], today_start: datetime
) -> AlertKPIs:
    """Berechnet Alert-KPIs."""
    try:
        conditions = [Alert.status.in_(["new", "acknowledged", "in_progress"])]
        if company_id:
            conditions.append(Alert.company_id == company_id)

        # Total active
        total_query = select(func.count(Alert.id)).where(*conditions)
        total_result = await db.execute(total_query)
        total_active = total_result.scalar() or 0

        # By severity
        critical_query = select(func.count(Alert.id)).where(
            Alert.severity == "critical", *conditions
        )
        critical_result = await db.execute(critical_query)
        critical = critical_result.scalar() or 0

        high_query = select(func.count(Alert.id)).where(
            Alert.severity == "high", *conditions
        )
        high_result = await db.execute(high_query)
        high = high_result.scalar() or 0

        medium_query = select(func.count(Alert.id)).where(
            Alert.severity == "medium", *conditions
        )
        medium_result = await db.execute(medium_query)
        medium = medium_result.scalar() or 0

        # New today
        new_today_query = select(func.count(Alert.id)).where(
            Alert.created_at >= today_start,
            Alert.status == "new",
            conditions[0] if len(conditions) == 1 else conditions[1],
        )
        new_today_result = await db.execute(new_today_query)
        new_today = new_today_result.scalar() or 0

        return AlertKPIs(
            total_active=total_active,
            critical=critical,
            high=high,
            medium=medium,
            new_today=new_today,
        )
    except Exception as e:
        logger.warning("alert_kpis_error", error=str(e))
        return AlertKPIs(
            total_active=0,
            critical=0,
            high=0,
            medium=0,
            new_today=0,
        )


async def _get_approval_kpis(
    db: AsyncSession, user_id: UUID, company_id: Optional[UUID], week_start: datetime
) -> ApprovalKPIs:
    """Berechnet Genehmigungs-KPIs über den ApprovalService (+ wochengenaue Zählung)."""
    if not company_id:
        return ApprovalKPIs(
            pending_total=0, my_pending=0, overdue=0, approved_this_week=0
        )
    try:
        service = ApprovalService(db)
        summary = await service.get_approval_summary(
            company_id=company_id, user_id=user_id
        )

        # "Diese Woche genehmigt": eigene fenstergenaue Zählung, da der Service nur
        # all-time-Counts liefert (Interface-Kontrakt M2: total_approved ist all-time).
        approved_week_result = await db.execute(
            select(func.count(ApprovalRequest.id)).where(
                and_(
                    ApprovalRequest.company_id == company_id,
                    ApprovalRequest.status == ApprovalStatus.APPROVED,
                    ApprovalRequest.resolved_at >= week_start,
                )
            )
        )
        approved_this_week = approved_week_result.scalar() or 0

        return ApprovalKPIs(
            pending_total=summary.total_pending,
            my_pending=summary.my_pending,
            overdue=summary.overdue_count,
            approved_this_week=approved_this_week,
        )
    except Exception as e:  # noqa: BLE001 - KPI degradiert, kein HTTP-500
        logger.warning("approval_kpis_error", error=str(e))
        return ApprovalKPIs(
            pending_total=0, my_pending=0, overdue=0, approved_this_week=0
        )


async def _get_ocr_quality_kpis(
    db: AsyncSession, company_id: Optional[UUID], today_start: datetime
) -> OCRQualityKPIs:
    """Berechnet OCR-Qualitaets-KPIs."""
    try:
        conditions = [Document.created_at >= today_start]
        if company_id:
            conditions.append(Document.company_id == company_id)

        # Documents processed today
        docs_today_query = select(func.count(Document.id)).where(
            Document.ocr_result.isnot(None),
            *conditions
        )
        docs_today_result = await db.execute(docs_today_query)
        documents_today = docs_today_result.scalar() or 0

        # TODO(G4): success_rate / avg_confidence / manual_corrections erfordern eine
        # company-gefilterte, DB-gestützte Lese-Methode (z.B.
        # OCRQualityMetricsService.get_ocr_quality_summary(db, company_id, since)).
        # Diese existiert noch nicht (heutiger Service ist prozess-lokal/in-memory und
        # nicht mandantengetrennt). Bis dahin ehrliche None-Werte statt Platzhalterzahlen.
        return OCRQualityKPIs(
            documents_today=documents_today,
            success_rate=None,
            avg_confidence=None,
            manual_corrections=None,
        )
    except Exception as e:
        logger.warning("ocr_kpis_error", error=str(e))
        return OCRQualityKPIs(
            documents_today=0,
            success_rate=None,
            avg_confidence=None,
            manual_corrections=None,
        )


async def _get_document_kpis(
    db: AsyncSession, company_id: Optional[UUID], today_start: datetime, week_start: datetime
) -> DocumentKPIs:
    """Berechnet Dokumenten-KPIs."""
    try:
        conditions = []
        if company_id:
            conditions.append(Document.company_id == company_id)

        # Total documents
        total_query = select(func.count(Document.id)).where(*conditions) if conditions else select(func.count(Document.id))
        total_result = await db.execute(total_query)
        total_documents = total_result.scalar() or 0

        # Documents today
        today_query = select(func.count(Document.id)).where(
            Document.created_at >= today_start,
            *conditions
        )
        today_result = await db.execute(today_query)
        documents_today = today_result.scalar() or 0

        # Documents this week
        week_query = select(func.count(Document.id)).where(
            Document.created_at >= week_start,
            *conditions
        )
        week_result = await db.execute(week_query)
        documents_this_week = week_result.scalar() or 0

        # Pending review
        pending_query = select(func.count(Document.id)).where(
            Document.status == "pending_review",
            *conditions
        )
        pending_result = await db.execute(pending_query)
        pending_review = pending_result.scalar() or 0

        return DocumentKPIs(
            total_documents=total_documents,
            documents_today=documents_today,
            documents_this_week=documents_this_week,
            pending_review=pending_review,
        )
    except Exception as e:
        logger.warning("document_kpis_error", error=str(e))
        return DocumentKPIs(
            total_documents=0,
            documents_today=0,
            documents_this_week=0,
            pending_review=0,
        )


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_user_permissions(user: User) -> List[str]:
    """
    Ermittelt Benutzerberechtigungen.

    In Produktion wuerde dies aus dem RBAC-System kommen.
    """
    # Simplified permission mapping based on role
    role = getattr(user, "role", "viewer")

    permissions = []

    if role == "admin":
        permissions = [
            "admin.system.view",
            "finance.view",
            "finance.invoices.view",
            "finance.reports.view",
            "documents.view",
            "documents.create",
        ]
    elif role == "editor":
        permissions = [
            "finance.view",
            "finance.invoices.view",
            "documents.view",
            "documents.create",
        ]
    else:  # viewer
        permissions = [
            "documents.view",
        ]

    return permissions
