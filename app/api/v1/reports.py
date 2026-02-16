# -*- coding: utf-8 -*-
"""
Report Builder API Endpoints.

Ermöglicht Nutzern, eigene Reports zu erstellen, zu verwalten und auszuführen.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Union

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.core.safe_errors import safe_error_detail
from app.core.types import JSONValue
from app.db.models import User
from app.services.reports import (
    ReportBuilderService,
    ReportCatalogService,
    ReportRendererService,
    ReportSchedulerService,
    ReportTemplateService,
)
from app.services.reports.report_templates import (
    CASHFLOW_FORECAST_TEMPLATE,
    COST_ANALYSIS_TEMPLATE,
    DOCUMENT_VOLUME_TEMPLATE,
    ReportTemplate as PreBuiltTemplate,
    get_all_templates,
    get_template_by_id as get_prebuilt_template_by_id,
)
from app.services.reports.pdf_export_service import PdfExportService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


# =============================================================================
# ENUMS
# =============================================================================


class ReportType(str, Enum):
    DOCUMENT = "document"
    FINANCE = "finance"
    OCR = "ocr"
    CUSTOM = "custom"


class DataSource(str, Enum):
    DOCUMENTS = "documents"
    INVOICES = "invoices"
    ENTITIES = "entities"


class ExportFormat(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"
    CSV = "csv"
    JSON = "json"


class FilterOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IN = "in"
    BETWEEN = "between"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class ChartType(str, Enum):
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    AREA = "area"
    SCATTER = "scatter"


class AggregationType(str, Enum):
    SUM = "sum"
    AVG = "avg"
    COUNT = "count"
    MIN = "min"
    MAX = "max"


# =============================================================================
# TYPED VALUE ALIASES (replaces Any)
# =============================================================================

FilterValue = Union[str, int, float, bool, List[str]]
# JSONValue imported from app.core.types
# Note: JSONValue removed - use JSONValue from core.types instead


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class ReportColumnCreate(BaseModel):
    field_path: str = Field(..., description="Pfad zum Feld, z.B. 'extracted_data.invoice_number'")
    display_name: str = Field(..., description="Anzeigename der Spalte")
    data_type: str = Field(..., description="Datentyp: string|number|date|currency|boolean")
    format_pattern: Optional[str] = Field(None, description="Formatierung, z.B. '#,##0.00 EUR'")
    width: Optional[int] = Field(None, description="Spaltenbreite in Pixel")
    sort_order: int = Field(0, description="Reihenfolge der Spalte")
    is_visible: bool = Field(True, description="Ist die Spalte sichtbar?")
    aggregation: Optional[AggregationType] = Field(None, description="Aggregationstyp")


class ReportColumnUpdate(BaseModel):
    field_path: Optional[str] = None
    display_name: Optional[str] = None
    data_type: Optional[str] = None
    format_pattern: Optional[str] = None
    width: Optional[int] = None
    sort_order: Optional[int] = None
    is_visible: Optional[bool] = None
    aggregation: Optional[AggregationType] = None


class ReportColumnResponse(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    field_path: str
    display_name: str
    data_type: str
    format_pattern: Optional[str]
    width: Optional[int]
    sort_order: int
    is_visible: bool
    aggregation: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ReportFilterCreate(BaseModel):
    field_path: str = Field(..., description="Pfad zum Feld")
    operator: FilterOperator = Field(..., description="Filter-Operator")
    value: Optional[FilterValue] = Field(None, description="Wert für den Filter")
    logic_operator: str = Field("AND", description="Logische Verknüpfung: AND|OR")
    group_id: Optional[int] = Field(None, description="Gruppen-ID für verschachtelte Filter")
    sort_order: int = Field(0, description="Reihenfolge")
    is_dynamic: bool = Field(False, description="Dynamischer Wert?")
    dynamic_source: Optional[str] = Field(None, description="Quelle für dynamischen Wert")


class ReportFilterUpdate(BaseModel):
    field_path: Optional[str] = None
    operator: Optional[FilterOperator] = None
    value: Optional[FilterValue] = None
    logic_operator: Optional[str] = None
    group_id: Optional[int] = None
    sort_order: Optional[int] = None
    is_dynamic: Optional[bool] = None
    dynamic_source: Optional[str] = None


class ReportFilterResponse(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    field_path: str
    operator: str
    value: Optional[FilterValue]
    logic_operator: str
    group_id: Optional[int]
    sort_order: int
    is_dynamic: bool
    dynamic_source: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class ReportChartCreate(BaseModel):
    chart_type: ChartType = Field(..., description="Chart-Typ")
    title: Optional[str] = Field(None, description="Chart-Titel")
    x_axis_field: Optional[str] = Field(None, description="Feld für X-Achse")
    y_axis_fields: List[str] = Field(..., description="Felder für Y-Achse")
    group_by_field: Optional[str] = Field(None, description="Gruppierungsfeld")
    colors: Optional[List[str]] = Field(None, description="Benutzerdefinierte Farben")
    show_legend: bool = Field(True, description="Legende anzeigen?")
    show_labels: bool = Field(False, description="Datenlabels anzeigen?")
    position: str = Field("bottom", description="Position: top|bottom|separate_sheet")
    width_percent: int = Field(100, description="Breite in Prozent")
    height_px: int = Field(300, description="Höhe in Pixel")
    sort_order: int = Field(0, description="Reihenfolge")


class ReportChartUpdate(BaseModel):
    chart_type: Optional[ChartType] = None
    title: Optional[str] = None
    x_axis_field: Optional[str] = None
    y_axis_fields: Optional[List[str]] = None
    group_by_field: Optional[str] = None
    colors: Optional[List[str]] = None
    show_legend: Optional[bool] = None
    show_labels: Optional[bool] = None
    position: Optional[str] = None
    width_percent: Optional[int] = None
    height_px: Optional[int] = None
    sort_order: Optional[int] = None


class ReportChartResponse(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    chart_type: str
    title: Optional[str]
    x_axis_field: Optional[str]
    y_axis_fields: List[str]
    group_by_field: Optional[str]
    colors: Optional[List[str]]
    show_legend: bool
    show_labels: bool
    position: str
    width_percent: int
    height_px: int
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


class ReportTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Name des Reports")
    description: Optional[str] = Field(None, description="Beschreibung")
    report_type: ReportType = Field(..., description="Report-Typ")
    data_source: DataSource = Field(..., description="Datenquelle")
    default_format: ExportFormat = Field(ExportFormat.EXCEL, description="Standard-Exportformat")
    company_id: Optional[uuid.UUID] = Field(None, description="Mandanten-ID (optional)")
    is_public: bool = Field(False, description="Öffentlich sichtbar?")
    layout_config: Optional[Dict[str, JSONValue]] = Field(None, description="Layout-Konfiguration")
    sort_config: Optional[List[Dict[str, JSONValue]]] = Field(None, description="Sortierung")
    group_by_config: Optional[List[str]] = Field(None, description="Gruppierung")


class ReportTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    report_type: Optional[ReportType] = None
    data_source: Optional[DataSource] = None
    default_format: Optional[ExportFormat] = None
    is_public: Optional[bool] = None
    layout_config: Optional[Dict[str, JSONValue]] = None
    sort_config: Optional[List[Dict[str, JSONValue]]] = None
    group_by_config: Optional[List[str]] = None


class ReportTemplateResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    company_id: Optional[uuid.UUID]
    name: str
    description: Optional[str]
    report_type: str
    data_source: str
    default_format: str
    is_public: bool
    is_scheduled: bool
    schedule_config: Optional[Dict[str, JSONValue]]
    layout_config: Optional[Dict[str, JSONValue]]
    sort_config: Optional[List[Dict[str, JSONValue]]]
    group_by_config: Optional[List[str]]
    created_at: datetime
    updated_at: datetime
    last_executed_at: Optional[datetime]
    columns: Optional[List[ReportColumnResponse]] = None
    filters: Optional[List[ReportFilterResponse]] = None
    charts: Optional[List[ReportChartResponse]] = None

    model_config = ConfigDict(from_attributes=True)


class ReportShareCreate(BaseModel):
    shared_with_user_id: uuid.UUID = Field(..., description="User-ID mit dem geteilt wird")
    can_view: bool = Field(True, description="Kann ansehen?")
    can_execute: bool = Field(True, description="Kann ausführen?")
    can_edit: bool = Field(False, description="Kann bearbeiten?")
    can_delete: bool = Field(False, description="Kann löschen?")


class ReportShareResponse(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    shared_with_user_id: uuid.UUID
    can_view: bool
    can_execute: bool
    can_edit: bool
    can_delete: bool
    shared_by_id: Optional[uuid.UUID]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleConfigCreate(BaseModel):
    cron_expression: str = Field(..., description="Cron-Ausdruck, z.B. '0 8 * * *'")
    timezone: str = Field("Europe/Berlin", description="Zeitzone")
    recipients: Optional[List[str]] = Field(None, description="E-Mail-Empfänger")
    format: ExportFormat = Field(ExportFormat.EXCEL, description="Export-Format")


class ReportExecutionResponse(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID
    executed_by_id: Optional[uuid.UUID]
    status: str
    format: str
    trigger_type: str
    row_count: Optional[int]
    file_size_bytes: Optional[int]
    download_url: Optional[str]
    download_expires_at: Optional[datetime]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportPreviewResponse(BaseModel):
    template_id: uuid.UUID
    columns: List[Dict[str, JSONValue]]
    sample_rows: List[Dict[str, JSONValue]]
    total_count: int


class ReportExecuteRequest(BaseModel):
    format: ExportFormat = Field(ExportFormat.EXCEL, description="Export-Format")
    runtime_filters: Optional[Dict[str, FilterValue]] = Field(None, description="Laufzeit-Filter")


class FieldDefinition(BaseModel):
    path: str
    display_name: str
    data_type: str
    category: str


class DataSourceDefinition(BaseModel):
    id: str
    name: str
    description: str


class OperatorDefinition(BaseModel):
    id: str
    name: str
    types: List[str]


class AggregationDefinition(BaseModel):
    id: str
    name: str
    types: List[str]


class ColumnOrderItem(BaseModel):
    id: uuid.UUID
    sort_order: int


# =============================================================================
# SERVICE INSTANCES
# =============================================================================


def get_template_service() -> ReportTemplateService:
    return ReportTemplateService()


def get_builder_service() -> ReportBuilderService:
    return ReportBuilderService()


def get_renderer_service() -> ReportRendererService:
    return ReportRendererService()


def get_scheduler_service() -> ReportSchedulerService:
    return ReportSchedulerService()


def get_catalog_service() -> ReportCatalogService:
    return ReportCatalogService()


def get_pdf_export_service() -> PdfExportService:
    return PdfExportService()


# =============================================================================
# PRE-BUILT TEMPLATES SCHEMAS
# =============================================================================


class PreBuiltColumnResponse(BaseModel):
    key: str
    label: str
    format_type: str


class PreBuiltChartResponse(BaseModel):
    chart_type: str
    x_axis: str
    y_axis: str
    title: str


class PreBuiltTemplateResponse(BaseModel):
    template_id: str
    name: str
    description: str
    category: str
    columns: List[PreBuiltColumnResponse]
    default_filters: Dict[str, str]
    charts: List[PreBuiltChartResponse]
    grouping: List[str]
    supports_comparison: bool
    supports_export: List[str]


# =============================================================================
# TEMPLATE ENDPOINTS
# =============================================================================


@router.get("/templates/prebuilt", response_model=List[PreBuiltTemplateResponse])
async def get_prebuilt_templates() -> List[PreBuiltTemplateResponse]:
    """
    Gibt alle vorkonfigurierten Report-Templates zurück.

    Enthält:
    - Kostenauswertung (Cost Analysis)
    - Cashflow-Prognose (Cashflow Forecast)
    - Dokumenten-Volumen (Document Volume)
    """
    templates = get_all_templates()

    return [
        PreBuiltTemplateResponse(
            template_id=t.template_id,
            name=t.name,
            description=t.description,
            category=t.category,
            columns=[
                PreBuiltColumnResponse(
                    key=col.key,
                    label=col.label,
                    format_type=col.format_type,
                )
                for col in t.columns
            ],
            default_filters=t.default_filters,
            charts=[
                PreBuiltChartResponse(
                    chart_type=chart.chart_type,
                    x_axis=chart.x_axis,
                    y_axis=chart.y_axis,
                    title=chart.title,
                )
                for chart in t.charts
            ],
            grouping=t.grouping,
            supports_comparison=t.supports_comparison,
            supports_export=t.supports_export,
        )
        for t in templates
    ]


@router.get("/templates/prebuilt/{template_id}", response_model=PreBuiltTemplateResponse)
async def get_prebuilt_template(template_id: str) -> PreBuiltTemplateResponse:
    """Holt ein spezifisches Pre-Built Template."""
    template = get_prebuilt_template_by_id(template_id)

    if not template:
        raise HTTPException(status_code=404, detail="Pre-Built Template nicht gefunden")

    return PreBuiltTemplateResponse(
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        category=template.category,
        columns=[
            PreBuiltColumnResponse(
                key=col.key,
                label=col.label,
                format_type=col.format_type,
            )
            for col in template.columns
        ],
        default_filters=template.default_filters,
        charts=[
            PreBuiltChartResponse(
                chart_type=chart.chart_type,
                x_axis=chart.x_axis,
                y_axis=chart.y_axis,
                title=chart.title,
            )
            for chart in template.charts
        ],
        grouping=template.grouping,
        supports_comparison=template.supports_comparison,
        supports_export=template.supports_export,
    )


@router.get("/templates", response_model=List[ReportTemplateResponse])
async def list_templates(
    report_type: Optional[ReportType] = Query(None, description="Filter nach Report-Typ"),
    include_public: bool = Query(True, description="Öffentliche Templates einschließen?"),
    include_shared: bool = Query(True, description="Geteilte Templates einschließen?"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> List[ReportTemplateResponse]:
    """Listet alle Report-Templates des Nutzers."""
    templates = await service.list_templates(
        db=db,
        user_id=current_user.id,
        report_type=report_type.value if report_type else None,
        include_public=include_public,
        include_shared=include_shared,
        limit=limit,
        offset=offset,
    )
    return [ReportTemplateResponse.model_validate(t) for t in templates]


@router.post("/templates", response_model=ReportTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: ReportTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportTemplateResponse:
    """Erstellt ein neues Report-Template."""
    template = await service.create_template(
        db=db,
        user_id=current_user.id,
        name=data.name,
        report_type=data.report_type.value,
        data_source=data.data_source.value,
        company_id=data.company_id,
        description=data.description,
        default_format=data.default_format.value,
        is_public=data.is_public,
        layout_config=data.layout_config,
        sort_config=data.sort_config,
        group_by_config=data.group_by_config,
    )
    return ReportTemplateResponse.model_validate(template)


@router.get("/templates/{template_id}", response_model=ReportTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportTemplateResponse:
    """Holt ein Report-Template mit allen Details."""
    template = await service.get_template(
        db=db,
        template_id=template_id,
        user_id=current_user.id,
        include_relations=True,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    response = ReportTemplateResponse.model_validate(template)
    response.columns = [ReportColumnResponse.model_validate(c) for c in template.columns]
    response.filters = [ReportFilterResponse.model_validate(f) for f in template.filters]
    response.charts = [ReportChartResponse.model_validate(ch) for ch in template.charts]
    return response


@router.put("/templates/{template_id}", response_model=ReportTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    data: ReportTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportTemplateResponse:
    """Aktualisiert ein Report-Template."""
    updates = data.model_dump(exclude_unset=True)

    # Enum-Werte konvertieren
    if "report_type" in updates and updates["report_type"]:
        updates["report_type"] = updates["report_type"].value
    if "data_source" in updates and updates["data_source"]:
        updates["data_source"] = updates["data_source"].value
    if "default_format" in updates and updates["default_format"]:
        updates["default_format"] = updates["default_format"].value

    template = await service.update_template(
        db=db,
        template_id=template_id,
        user_id=current_user.id,
        **updates,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden oder keine Berechtigung")

    return ReportTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> Response:
    """Löscht ein Report-Template."""
    success = await service.delete_template(
        db=db,
        template_id=template_id,
        user_id=current_user.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Template nicht gefunden oder keine Berechtigung")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/templates/{template_id}/clone", response_model=ReportTemplateResponse, status_code=status.HTTP_201_CREATED)
async def clone_template(
    template_id: uuid.UUID,
    new_name: Optional[str] = Query(None, description="Name für die Kopie"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportTemplateResponse:
    """Klont ein Report-Template."""
    template = await service.clone_template(
        db=db,
        template_id=template_id,
        user_id=current_user.id,
        new_name=new_name,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    return ReportTemplateResponse.model_validate(template)


# =============================================================================
# COLUMN ENDPOINTS
# =============================================================================


@router.get("/templates/{template_id}/columns", response_model=List[ReportColumnResponse])
async def list_columns(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> List[ReportColumnResponse]:
    """Listet Spalten eines Templates."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=True)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    return [ReportColumnResponse.model_validate(c) for c in template.columns]


@router.post("/templates/{template_id}/columns", response_model=ReportColumnResponse, status_code=status.HTTP_201_CREATED)
async def add_column(
    template_id: uuid.UUID,
    data: ReportColumnCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportColumnResponse:
    """Fuegt eine Spalte zu einem Template hinzu."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=False)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    column = await service.add_column(
        db=db,
        template_id=template_id,
        field_path=data.field_path,
        display_name=data.display_name,
        data_type=data.data_type,
        format_pattern=data.format_pattern,
        width=data.width,
        sort_order=data.sort_order,
        is_visible=data.is_visible,
        aggregation=data.aggregation.value if data.aggregation else None,
    )
    return ReportColumnResponse.model_validate(column)


@router.put("/templates/{template_id}/columns/reorder", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def reorder_columns(
    template_id: uuid.UUID,
    orders: List[ColumnOrderItem],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> Response:
    """Sortiert Spalten neu."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=False)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    await service.reorder_columns(
        db=db,
        template_id=template_id,
        column_orders=[{"id": o.id, "sort_order": o.sort_order} for o in orders],
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/templates/{template_id}/columns/{column_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_column(
    template_id: uuid.UUID,
    column_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> Response:
    """Löscht eine Spalte."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=False)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    success = await service.delete_column(db, column_id)
    if not success:
        raise HTTPException(status_code=404, detail="Spalte nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# FILTER ENDPOINTS
# =============================================================================


@router.get("/templates/{template_id}/filters", response_model=List[ReportFilterResponse])
async def list_filters(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> List[ReportFilterResponse]:
    """Listet Filter eines Templates."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=True)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    return [ReportFilterResponse.model_validate(f) for f in template.filters]


@router.post("/templates/{template_id}/filters", response_model=ReportFilterResponse, status_code=status.HTTP_201_CREATED)
async def add_filter(
    template_id: uuid.UUID,
    data: ReportFilterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportFilterResponse:
    """Fuegt einen Filter zu einem Template hinzu."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=False)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    filter_obj = await service.add_filter(
        db=db,
        template_id=template_id,
        field_path=data.field_path,
        operator=data.operator.value,
        value=data.value,
        logic_operator=data.logic_operator,
        group_id=data.group_id,
        sort_order=data.sort_order,
        is_dynamic=data.is_dynamic,
        dynamic_source=data.dynamic_source,
    )
    return ReportFilterResponse.model_validate(filter_obj)


@router.delete("/templates/{template_id}/filters/{filter_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_filter(
    template_id: uuid.UUID,
    filter_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> Response:
    """Löscht einen Filter."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=False)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    success = await service.delete_filter(db, filter_id)
    if not success:
        raise HTTPException(status_code=404, detail="Filter nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# CHART ENDPOINTS
# =============================================================================


@router.post("/templates/{template_id}/charts", response_model=ReportChartResponse, status_code=status.HTTP_201_CREATED)
async def add_chart(
    template_id: uuid.UUID,
    data: ReportChartCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportChartResponse:
    """Fuegt einen Chart zu einem Template hinzu."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=False)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    chart = await service.add_chart(
        db=db,
        template_id=template_id,
        chart_type=data.chart_type.value,
        y_axis_fields=data.y_axis_fields,
        title=data.title,
        x_axis_field=data.x_axis_field,
        group_by_field=data.group_by_field,
        colors=data.colors,
        show_legend=data.show_legend,
        show_labels=data.show_labels,
        position=data.position,
        width_percent=data.width_percent,
        height_px=data.height_px,
        sort_order=data.sort_order,
    )
    return ReportChartResponse.model_validate(chart)


@router.delete("/templates/{template_id}/charts/{chart_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_chart(
    template_id: uuid.UUID,
    chart_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> Response:
    """Löscht einen Chart."""
    template = await service.get_template(db, template_id, current_user.id, include_relations=False)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    success = await service.delete_chart(db, chart_id)
    if not success:
        raise HTTPException(status_code=404, detail="Chart nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# EXECUTION ENDPOINTS
# =============================================================================


@router.post("/templates/{template_id}/preview", response_model=ReportPreviewResponse)
async def preview_report(
    template_id: uuid.UUID,
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    template_service: ReportTemplateService = Depends(get_template_service),
    builder_service: ReportBuilderService = Depends(get_builder_service),
) -> ReportPreviewResponse:
    """Erstellt eine Vorschau des Reports."""
    template = await template_service.get_template(db, template_id, current_user.id, include_relations=True)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    preview = await builder_service.preview_report(db, template, limit=limit)

    return ReportPreviewResponse(
        template_id=preview.template_id,
        columns=preview.columns,
        sample_rows=[row.data for row in preview.sample_rows],
        total_count=preview.total_count,
    )


@router.post("/templates/{template_id}/execute", response_model=ReportExecutionResponse)
async def execute_report(
    template_id: uuid.UUID,
    data: ReportExecuteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    template_service: ReportTemplateService = Depends(get_template_service),
    builder_service: ReportBuilderService = Depends(get_builder_service),
    scheduler_service: ReportSchedulerService = Depends(get_scheduler_service),
    pdf_service: PdfExportService = Depends(get_pdf_export_service),
) -> ReportExecutionResponse:
    """
    Führt einen Report aus und exportiert ihn im gewünschten Format.

    Unterstützt Excel, CSV, JSON und PDF (mit report_templates.py für PDF-Formatierung).
    """
    template = await template_service.get_template(db, template_id, current_user.id, include_relations=True)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    # Execution erstellen
    execution = await scheduler_service.create_execution(
        db=db,
        template_id=template_id,
        executed_by_id=current_user.id,
        format=data.format.value,
        trigger_type="manual",
        filter_snapshot=[f.__dict__ for f in template.filters] if template.filters else None,
    )

    try:
        # Status auf running setzen
        await scheduler_service.update_execution_status(db, execution.id, "running")

        # Report ausführen
        result = await builder_service.execute_report(
            db=db,
            template=template,
            user_id=current_user.id,
            runtime_filters=data.runtime_filters,
        )

        # Bei PDF: PDF generieren mit report_templates.py Strukturen
        file_size_bytes: Optional[int] = None
        if data.format == ExportFormat.PDF:
            # Konvertiere ReportResult zu PDF
            from app.services.reports.report_templates import ReportColumn as PdfColumn

            pdf_columns = [
                PdfColumn(
                    key=col.get("field_path", col.get("key", f"col_{idx}")),
                    label=col.get("display_name", col.get("label", f"Column {idx}")),
                    format_type=col.get("data_type", col.get("format_type", "text")),
                )
                for idx, col in enumerate(result.columns)
            ]

            # Convert rows to dict format
            pdf_data = [row.data for row in result.rows]

            # Try to find pre-built template chart configs
            chart_bytes: Optional[List[bytes]] = None
            prebuilt_template: Optional[PreBuiltTemplate] = None

            # Match by template name (since DB template_id may not match pre-built template_id)
            template_name_lower = result.template_name.lower()
            if "kosten" in template_name_lower or "cost" in template_name_lower:
                prebuilt_template = COST_ANALYSIS_TEMPLATE
            elif "cashflow" in template_name_lower:
                prebuilt_template = CASHFLOW_FORECAST_TEMPLATE
            elif "dokument" in template_name_lower or "volume" in template_name_lower:
                prebuilt_template = DOCUMENT_VOLUME_TEMPLATE

            # Generate charts if template has chart configs and data is available
            if prebuilt_template and prebuilt_template.charts and pdf_data:
                try:
                    chart_bytes = pdf_service.generate_charts_from_config(
                        chart_configs=prebuilt_template.charts,
                        data=pdf_data,
                    )
                    if not chart_bytes:
                        chart_bytes = None  # Empty list -> None
                    logger.info(
                        "charts_generated_for_pdf",
                        template_name=result.template_name,
                        chart_count=len(chart_bytes) if chart_bytes else 0,
                    )
                except Exception as e:
                    logger.warning(
                        "chart_generation_failed",
                        template_name=result.template_name,
                        error=str(e),
                    )
                    chart_bytes = None

            # Generate PDF
            pdf_bytes = await pdf_service.generate_report_pdf(
                title=result.template_name,
                subtitle=f"Erstellt am {result.executed_at.strftime('%d.%m.%Y %H:%M')}",
                columns=pdf_columns,
                data=pdf_data,
                charts=chart_bytes,
                company_name="Ablage-System",
            )

            file_size_bytes = len(pdf_bytes)

            logger.info(
                "pdf_report_generated",
                template_id=str(template_id),
                size_bytes=file_size_bytes,
            )

        # Execution aktualisieren (ohne Datei-Upload für jetzt)
        execution = await scheduler_service.update_execution_status(
            db=db,
            execution_id=execution.id,
            status="completed",
            row_count=result.total_count,
            file_size_bytes=file_size_bytes,
        )

    except Exception as e:
        logger.exception("Report execution failed", template_id=str(template_id))
        await scheduler_service.update_execution_status(
            db=db,
            execution_id=execution.id,
            status="failed",
            error_message=safe_error_detail(e, "Report"),
        )
        raise HTTPException(status_code=500, detail=safe_error_detail(e, "Vorgang"))

    return ReportExecutionResponse.model_validate(execution)


@router.get("/executions", response_model=List[ReportExecutionResponse])
async def list_executions(
    template_id: Optional[uuid.UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scheduler_service: ReportSchedulerService = Depends(get_scheduler_service),
) -> List[ReportExecutionResponse]:
    """Listet Report-Ausführungen."""
    executions = await scheduler_service.list_executions(
        db=db,
        template_id=template_id,
        user_id=current_user.id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [ReportExecutionResponse.model_validate(e) for e in executions]


@router.get("/executions/{execution_id}", response_model=ReportExecutionResponse)
async def get_execution(
    execution_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scheduler_service: ReportSchedulerService = Depends(get_scheduler_service),
) -> ReportExecutionResponse:
    """Holt Details einer Report-Ausführung."""
    execution = await scheduler_service.get_execution(db, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution nicht gefunden")

    return ReportExecutionResponse.model_validate(execution)


# =============================================================================
# SHARING ENDPOINTS
# =============================================================================


@router.post("/templates/{template_id}/share", response_model=ReportShareResponse, status_code=status.HTTP_201_CREATED)
async def share_template(
    template_id: uuid.UUID,
    data: ReportShareCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> ReportShareResponse:
    """Teilt ein Template mit einem anderen Benutzer."""
    share = await service.share_template(
        db=db,
        template_id=template_id,
        shared_by_id=current_user.id,
        shared_with_user_id=data.shared_with_user_id,
        can_view=data.can_view,
        can_execute=data.can_execute,
        can_edit=data.can_edit,
        can_delete=data.can_delete,
    )
    if not share:
        raise HTTPException(status_code=404, detail="Template nicht gefunden oder keine Berechtigung")

    return ReportShareResponse.model_validate(share)


@router.delete("/templates/{template_id}/share/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def revoke_share(
    template_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> Response:
    """Widerruft eine Freigabe."""
    success = await service.revoke_share(
        db=db,
        template_id=template_id,
        user_id=current_user.id,
        shared_with_user_id=user_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Freigabe nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/shared", response_model=List[ReportTemplateResponse])
async def list_shared_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    service: ReportTemplateService = Depends(get_template_service),
) -> List[ReportTemplateResponse]:
    """Listet alle mit mir geteilten Templates."""
    templates = await service.list_shared_with_me(db, current_user.id)
    return [ReportTemplateResponse.model_validate(t) for t in templates]


# =============================================================================
# SCHEDULE ENDPOINTS
# =============================================================================


@router.post("/templates/{template_id}/schedule", response_model=ReportTemplateResponse)
async def enable_schedule(
    template_id: uuid.UUID,
    data: ScheduleConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    template_service: ReportTemplateService = Depends(get_template_service),
    scheduler_service: ReportSchedulerService = Depends(get_scheduler_service),
) -> ReportTemplateResponse:
    """Aktiviert einen Zeitplan für einen Report."""
    template = await scheduler_service.enable_schedule(
        db=db,
        template_id=template_id,
        user_id=current_user.id,
        cron_expression=data.cron_expression,
        timezone_str=data.timezone,
        recipients=data.recipients,
        format=data.format.value,
    )
    if not template:
        raise HTTPException(status_code=400, detail="Ungültige Cron-Expression oder Template nicht gefunden")

    return ReportTemplateResponse.model_validate(template)


@router.delete("/templates/{template_id}/schedule", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def disable_schedule(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    scheduler_service: ReportSchedulerService = Depends(get_scheduler_service),
) -> Response:
    """Deaktiviert einen Zeitplan."""
    success = await scheduler_service.disable_schedule(db, template_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/schedule-presets", response_model=List[Dict[str, JSONValue]])
async def get_schedule_presets(
    scheduler_service: ReportSchedulerService = Depends(get_scheduler_service),
) -> List[Dict[str, JSONValue]]:
    """Gibt vordefinierte Zeitplan-Optionen zurück."""
    return scheduler_service.get_schedule_presets()


# =============================================================================
# METADATA ENDPOINTS
# =============================================================================


@router.get("/data-sources", response_model=List[DataSourceDefinition])
async def get_data_sources(
    builder_service: ReportBuilderService = Depends(get_builder_service),
) -> List[DataSourceDefinition]:
    """Gibt verfügbare Datenquellen zurück."""
    sources = builder_service.get_available_data_sources()
    return [DataSourceDefinition(**s) for s in sources]


@router.get("/data-sources/{source}/fields", response_model=List[FieldDefinition])
async def get_data_source_fields(
    source: DataSource,
    builder_service: ReportBuilderService = Depends(get_builder_service),
) -> List[FieldDefinition]:
    """Gibt verfügbare Felder für eine Datenquelle zurück."""
    fields = builder_service.get_available_fields(source.value)
    return [FieldDefinition(**f) for f in fields]


@router.get("/operators", response_model=List[OperatorDefinition])
async def get_operators(
    builder_service: ReportBuilderService = Depends(get_builder_service),
) -> List[OperatorDefinition]:
    """Gibt verfügbare Filter-Operatoren zurück."""
    operators = builder_service.get_available_operators()
    return [OperatorDefinition(**o) for o in operators]


@router.get("/aggregations", response_model=List[AggregationDefinition])
async def get_aggregations(
    builder_service: ReportBuilderService = Depends(get_builder_service),
) -> List[AggregationDefinition]:
    """Gibt verfügbare Aggregationen zurück."""
    aggs = builder_service.get_available_aggregations()
    return [AggregationDefinition(**a) for a in aggs]


@router.get("/formats", response_model=List[Dict[str, JSONValue]])
async def get_formats(
    renderer_service: ReportRendererService = Depends(get_renderer_service),
) -> List[Dict[str, JSONValue]]:
    """Gibt unterstützte Export-Formate zurück."""
    return renderer_service.get_supported_formats()


# =============================================================================
# CATALOG SCHEMAS
# =============================================================================


class CatalogColumnDefinition(BaseModel):
    field_path: str
    display_name: str
    data_type: str


class CatalogChartDefinition(BaseModel):
    chart_type: str
    title: Optional[str]
    x_axis_field: Optional[str]
    y_axis_fields: List[str]


class CatalogTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    report_type: str
    data_source: str
    icon: str
    default_columns: List[CatalogColumnDefinition]
    default_filters: Optional[List[Dict[str, JSONValue]]] = None
    default_charts: Optional[List[CatalogChartDefinition]] = None
    tags: List[str]


class CatalogCategoryResponse(BaseModel):
    id: str
    name: str
    description: str
    template_count: int


class CatalogListResponse(BaseModel):
    templates: List[CatalogTemplateResponse]
    categories: List[CatalogCategoryResponse]
    total: int


class InstantiateRequest(BaseModel):
    name: Optional[str] = Field(None, description="Name für den neuen Report")


# =============================================================================
# CATALOG ENDPOINTS
# =============================================================================


@router.get("/catalog", response_model=CatalogListResponse)
async def get_catalog(
    category: Optional[str] = Query(None, description="Filter nach Kategorie"),
    catalog_service: ReportCatalogService = Depends(get_catalog_service),
) -> CatalogListResponse:
    """Gibt den Template-Katalog zurück."""
    templates = catalog_service.get_catalog(category=category)
    categories = catalog_service.get_categories()

    return CatalogListResponse(
        templates=[CatalogTemplateResponse(**t) for t in templates],
        categories=[CatalogCategoryResponse(**c) for c in categories],
        total=len(templates),
    )


@router.get("/catalog/{template_id}")
async def get_catalog_template(
    template_id: str,
    catalog_service: ReportCatalogService = Depends(get_catalog_service),
) -> CatalogTemplateResponse:
    """Gibt Details eines Katalog-Templates zurück."""
    template = catalog_service.get_template_preview(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    return CatalogTemplateResponse(**template)


@router.post("/catalog/{template_id}/instantiate", response_model=ReportTemplateResponse, status_code=status.HTTP_201_CREATED)
async def instantiate_catalog_template(
    template_id: str,
    data: Optional[InstantiateRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    catalog_service: ReportCatalogService = Depends(get_catalog_service),
) -> ReportTemplateResponse:
    """Erstellt einen neuen Report aus einem Katalog-Template."""
    new_name = data.name if data else None

    result = await catalog_service.instantiate_template(
        template_id=template_id,
        user_id=current_user.id,
        new_name=new_name,
        db=db,
    )

    if not result:
        raise HTTPException(status_code=404, detail="Template nicht gefunden")

    return ReportTemplateResponse.model_validate(result)
