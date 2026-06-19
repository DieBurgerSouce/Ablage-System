# -*- coding: utf-8 -*-
"""
Ad-Hoc Reporting API Endpoints.

Feature #12: Ermöglicht Nutzern, eigene Reports mit beliebigen
Datenquellen zu erstellen, auszuführen und zu exportieren.

Alle Endpunkte sind mandantenisoliert (company_id).
User-facing Text ist auf Deutsch.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Union

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db, get_user_company_id_dep
from app.core.safe_errors import safe_error_detail
from app.core.types import JSONValue
from app.db.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/reports/adhoc", tags=["Ad-Hoc Reporting"])


# =============================================================================
# TYPE ALIASES (no Any)
# =============================================================================

FilterValue = Union[str, int, float, bool, List[str]]


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================


class ColumnConfig(BaseModel):
    """Spalten-Konfiguration."""
    source: str = Field(..., description="Datenquelle")
    field: str = Field(..., description="Feldname")
    alias: Optional[str] = Field(None, description="Anzeigename")
    visible: bool = Field(True, description="Sichtbar?")
    sort_order: Optional[int] = Field(None, description="Sortierreihenfolge")
    sort_direction: Optional[str] = Field(None, description="asc|desc")


class FilterConfig(BaseModel):
    """Filter-Konfiguration."""
    field: str = Field(..., description="Feldname (source.field oder field)")
    operator: str = Field(..., description="eq|ne|gt|gte|lt|lte|contains|in|is_null|...")
    value: Optional[FilterValue] = Field(None, description="Filterwert")
    logic: str = Field("and", description="and|or")


class GroupingConfig(BaseModel):
    """Gruppierungs-Konfiguration."""
    field: str = Field(..., description="Feldname")
    aggregation: Optional[str] = Field(None, description="sum|count|avg|min|max")


class AggregationConfig(BaseModel):
    """Aggregations-Konfiguration."""
    field: str = Field(..., description="Feldname (source.field)")
    type: str = Field(..., description="sum|count|avg|min|max")
    alias: Optional[str] = Field(None, description="Ergebnis-Alias")


class ChartConfig(BaseModel):
    """Diagramm-Konfiguration."""
    chart_type: str = Field(..., description="bar|line|pie|area|scatter")
    x_field: Optional[str] = Field(None, description="Feld für X-Achse")
    y_field: Optional[str] = Field(None, description="Feld für Y-Achse")
    title: Optional[str] = Field(None, description="Diagramm-Titel")
    colors: Optional[List[str]] = Field(None, description="Benutzerdefinierte Farben")


# --- Request Schemas ---


class AdHocReportCreate(BaseModel):
    """Schema für Report-Erstellung."""
    name: str = Field(..., min_length=1, max_length=300, description="Report-Name")
    description: Optional[str] = Field(None, description="Beschreibung")
    data_sources: List[str] = Field(
        ..., min_length=1,
        description="Datenquellen-Keys: invoices, documents, suppliers, customers, transactions, approvals, workflows",
    )
    columns: List[ColumnConfig] = Field(..., min_length=1, description="Spalten")
    filters: Optional[List[FilterConfig]] = Field(None, description="Filter")
    grouping: Optional[List[GroupingConfig]] = Field(None, description="Gruppierung")
    aggregations: Optional[List[AggregationConfig]] = Field(None, description="Aggregationen")
    chart_config: Optional[ChartConfig] = Field(None, description="Diagramm")
    is_template: bool = Field(False, description="Als Vorlage speichern?")


class AdHocReportUpdate(BaseModel):
    """Schema für Report-Aktualisierung."""
    name: Optional[str] = Field(None, min_length=1, max_length=300)
    description: Optional[str] = None
    data_sources: Optional[List[str]] = None
    columns: Optional[List[ColumnConfig]] = None
    filters: Optional[List[FilterConfig]] = None
    grouping: Optional[List[GroupingConfig]] = None
    aggregations: Optional[List[AggregationConfig]] = None
    chart_config: Optional[ChartConfig] = None
    is_public: Optional[bool] = None
    is_template: Optional[bool] = None


class ShareRequest(BaseModel):
    """Schema für Report-Freigabe."""
    shared_with_user_id: uuid.UUID = Field(..., description="Benutzer-ID")
    can_edit: bool = Field(False, description="Bearbeitungsrecht?")


class ExecuteRequest(BaseModel):
    """Schema für Report-Ausführung mit Parametern."""
    parameter_overrides: Optional[Dict[str, FilterValue]] = Field(
        None, description="Laufzeit-Parameter-Überschreibungen"
    )


class ScheduleCreate(BaseModel):
    """Schema für Zeitplan-Erstellung."""
    frequency: str = Field(..., description="daily|weekly|monthly|quarterly")
    export_format: str = Field("excel", description="pdf|excel|csv")
    recipients: List[str] = Field(..., min_length=1, description="E-Mail-Empfänger")
    time_of_day: str = Field("08:00", description="Uhrzeit (HH:MM)")
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="0=Mo, 6=So")
    day_of_month: Optional[int] = Field(None, ge=1, le=28, description="Tag des Monats")


class ScheduleUpdate(BaseModel):
    """Schema für Zeitplan-Aktualisierung."""
    frequency: Optional[str] = None
    recipients: Optional[List[str]] = None
    export_format: Optional[str] = None
    time_of_day: Optional[str] = None
    day_of_week: Optional[int] = Field(None, ge=0, le=6)
    day_of_month: Optional[int] = Field(None, ge=1, le=28)
    is_active: Optional[bool] = None


# --- Response Schemas ---


class AdHocReportResponse(BaseModel):
    """Response für einen Ad-Hoc Report."""
    id: uuid.UUID
    company_id: uuid.UUID
    created_by: uuid.UUID
    name: str
    description: Optional[str]
    data_sources: List[str]
    columns: List[Dict[str, JSONValue]]
    filters: List[Dict[str, JSONValue]]
    grouping: List[Dict[str, JSONValue]]
    aggregations: List[Dict[str, JSONValue]]
    chart_config: Optional[Dict[str, JSONValue]]
    is_public: bool
    is_template: bool
    execution_count: int
    last_executed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DataSourceResponse(BaseModel):
    """Response für eine Datenquelle."""
    key: str
    label: str
    table: str


class FieldDefinitionResponse(BaseModel):
    """Response für eine Feld-Definition."""
    field: str
    label: str
    type: str
    source: str


class ExecutionResultResponse(BaseModel):
    """Response für eine Report-Ausführung."""
    columns: List[Dict[str, str]]
    rows: List[Dict[str, JSONValue]]
    total_rows: int
    execution_time_ms: int
    execution_id: str


class ShareResponse(BaseModel):
    """Response für eine Freigabe."""
    id: uuid.UUID
    report_id: uuid.UUID
    shared_with_user_id: Optional[uuid.UUID]
    shared_with_role: Optional[str]
    can_edit: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ScheduleResponse(BaseModel):
    """Response für einen Zeitplan."""
    id: uuid.UUID
    report_id: uuid.UUID
    company_id: uuid.UUID
    frequency: str
    day_of_week: Optional[int]
    day_of_month: Optional[int]
    time_of_day: str
    export_format: str
    recipients: List[str]
    is_active: bool
    last_run_at: Optional[datetime]
    next_run_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# SERVICE INSTANCES
# =============================================================================


def _get_service():
    """Lazy import um zirkuläre Importe zu vermeiden."""
    from app.services.adhoc_report_service import get_adhoc_report_service
    return get_adhoc_report_service()


# =============================================================================
# DATA SOURCE ENDPOINTS
# =============================================================================


@router.get("/data-sources", response_model=List[DataSourceResponse])
async def list_data_sources() -> List[DataSourceResponse]:
    """Gibt alle verfügbaren Datenquellen zurück.

    Jede Datenquelle enthält Name und Beschreibung auf Deutsch.
    """
    service = _get_service()
    sources = service.get_data_sources()
    return [DataSourceResponse(**s) for s in sources]


@router.get(
    "/data-sources/{source}/fields",
    response_model=List[FieldDefinitionResponse],
)
async def list_source_fields(source: str) -> List[FieldDefinitionResponse]:
    """Gibt die verfügbaren Felder für eine bestimmte Datenquelle zurück.

    SICHERHEIT: Nur Felder aus der Whitelist werden zurückgegeben.
    """
    service = _get_service()
    try:
        fields = await service.get_available_fields(source)
        return [FieldDefinitionResponse(**f) for f in fields]
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Datenquelle '{source}' nicht gefunden",
        )


# =============================================================================
# REPORT CRUD ENDPOINTS
# =============================================================================


@router.post("", response_model=AdHocReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    data: AdHocReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> AdHocReportResponse:
    """Erstellt einen neuen Ad-Hoc Report.

    Validiert die Konfiguration gegen erlaubte Datenquellen und Spalten.
    """
    service = _get_service()

    col_list = [col.model_dump(exclude_none=True) for col in data.columns]
    filter_list = [f.model_dump(exclude_none=True) for f in data.filters] if data.filters else None
    grouping_list = [g.model_dump(exclude_none=True) for g in data.grouping] if data.grouping else None
    agg_list = [a.model_dump(exclude_none=True) for a in data.aggregations] if data.aggregations else None
    chart_dict = data.chart_config.model_dump(exclude_none=True) if data.chart_config else None

    try:
        report = await service.create_report(
            db=db,
            company_id=company_id,
            user_id=current_user.id,
            name=data.name,
            description=data.description,
            data_sources=data.data_sources,
            columns=col_list,
            filters=filter_list,
            grouping=grouping_list,
            aggregations=agg_list,
            chart_config=chart_dict,
        )
        return AdHocReportResponse.model_validate(report)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=safe_error_detail(e, "Bericht"),
        )


@router.get("", response_model=List[AdHocReportResponse])
async def list_reports(
    include_shared: bool = Query(True, description="Geteilte Reports einschließen?"),
    page: int = Query(1, ge=1, description="Seitennummer (1-basiert)"),
    per_page: int = Query(100, ge=1, le=500, description="Eintraege pro Seite"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> List[AdHocReportResponse]:
    """Listet alle Ad-Hoc Reports des aktuellen Benutzers (eigene + geteilte + öffentliche)."""
    service = _get_service()
    reports = await service.list_reports(
        db=db,
        company_id=company_id,
        user_id=current_user.id,
        include_shared=include_shared,
        limit=per_page,
        offset=(page - 1) * per_page,
    )
    return [AdHocReportResponse.model_validate(r) for r in reports]


@router.get("/{report_id}", response_model=AdHocReportResponse)
async def get_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> AdHocReportResponse:
    """Lädt einen spezifischen Ad-Hoc Report."""
    service = _get_service()
    report = await service.get_report(db, report_id, company_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report nicht gefunden")

    return AdHocReportResponse.model_validate(report)


@router.put("/{report_id}", response_model=AdHocReportResponse)
async def update_report(
    report_id: uuid.UUID,
    data: AdHocReportUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> AdHocReportResponse:
    """Aktualisiert einen Ad-Hoc Report (nur Besitzer oder Bearbeitungsrecht)."""
    service = _get_service()
    updates = data.model_dump(exclude_unset=True)

    # Pydantic-Modelle zu Dicts konvertieren
    if "columns" in updates and updates["columns"]:
        updates["columns"] = [
            col.model_dump(exclude_none=True) if hasattr(col, "model_dump") else col
            for col in updates["columns"]
        ]
    if "filters" in updates and updates["filters"]:
        updates["filters"] = [
            f.model_dump(exclude_none=True) if hasattr(f, "model_dump") else f
            for f in updates["filters"]
        ]
    if "grouping" in updates and updates["grouping"]:
        updates["grouping"] = [
            g.model_dump(exclude_none=True) if hasattr(g, "model_dump") else g
            for g in updates["grouping"]
        ]
    if "aggregations" in updates and updates["aggregations"]:
        updates["aggregations"] = [
            a.model_dump(exclude_none=True) if hasattr(a, "model_dump") else a
            for a in updates["aggregations"]
        ]
    if "chart_config" in updates and updates["chart_config"]:
        cc = updates["chart_config"]
        updates["chart_config"] = cc.model_dump(exclude_none=True) if hasattr(cc, "model_dump") else cc

    try:
        result = await service.update_report(
            db=db,
            report_id=report_id,
            company_id=company_id,
            user_id=current_user.id,
            **updates,
        )
        if not result:
            raise HTTPException(
                status_code=404,
                detail="Report nicht gefunden oder keine Berechtigung",
            )
        return AdHocReportResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Bericht"))


@router.delete(
    "/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_report(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> Response:
    """Löscht einen Ad-Hoc Report (nur Besitzer)."""
    service = _get_service()
    success = await service.delete_report(db, report_id, company_id, current_user.id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Report nicht gefunden oder keine Berechtigung",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# EXECUTION ENDPOINTS
# =============================================================================


@router.post("/{report_id}/execute", response_model=ExecutionResultResponse)
async def execute_report(
    report_id: uuid.UUID,
    data: Optional[ExecuteRequest] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> ExecutionResultResponse:
    """Führt einen Ad-Hoc Report aus und gibt die Daten zurück.

    Für große Reports (>5000 Zeilen) wird empfohlen,
    den Export-Endpunkt zu verwenden.
    """
    service = _get_service()
    param_overrides = data.parameter_overrides if data else None

    try:
        result = await service.execute_report(
            db=db,
            report_id=report_id,
            company_id=company_id,
            user_id=current_user.id,
            parameter_overrides=param_overrides,
        )
        return ExecutionResultResponse(
            columns=result.get("columns", []),
            rows=result.get("rows", []),
            total_rows=result.get("total_rows", 0),
            execution_time_ms=result.get("execution_time_ms", 0),
            execution_id=result.get("execution_id", ""),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Bericht"))
    except Exception as e:
        logger.exception(
            "adhoc_report_execution_failed",
            report_id=str(report_id),
        )
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(e, "Report"),
        )


@router.get("/{report_id}/export/{export_format}")
async def export_report(
    report_id: uuid.UUID,
    export_format: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> Response:
    """Exportiert einen Ad-Hoc Report als PDF, Excel oder CSV.

    Gibt die Datei direkt als Download zurück.
    """
    from app.db.models_adhoc_report import AdHocExportFormat

    valid_formats = {"pdf", "excel", "csv"}
    if export_format not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiges Format: {export_format}. Erlaubt: {', '.join(valid_formats)}",
        )

    service = _get_service()

    try:
        fmt = AdHocExportFormat(export_format)
        file_bytes, content_type = await service.export_report(
            db=db,
            report_id=report_id,
            company_id=company_id,
            user_id=current_user.id,
            export_format=fmt,
        )

        # Report-Name für Dateinamen holen
        report = await service.get_report(db, report_id, company_id)
        report_name = report.name if report else "Ad-Hoc-Report"

        ext_map = {"pdf": "pdf", "excel": "xlsx", "csv": "csv"}
        ext = ext_map.get(export_format, "bin")

        # Dateiname sanitieren
        safe_name = "".join(
            c for c in report_name if c.isalnum() or c in "._- "
        )[:80]
        filename = f"{safe_name}.{ext}"

        return Response(
            content=file_bytes,
            media_type=content_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Bericht"))
    except Exception as e:
        logger.exception(
            "adhoc_report_export_failed",
            report_id=str(report_id),
            format=export_format,
        )
        raise HTTPException(
            status_code=500,
            detail=safe_error_detail(e, "Export"),
        )


# =============================================================================
# SHARING ENDPOINTS
# =============================================================================


@router.post("/{report_id}/share", response_model=ShareResponse, status_code=status.HTTP_201_CREATED)
async def share_report(
    report_id: uuid.UUID,
    data: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> ShareResponse:
    """Teilt einen Report mit einem anderen Benutzer."""
    service = _get_service()
    try:
        share = await service.share_report(
            db=db,
            report_id=report_id,
            owner_id=current_user.id,
            share_with=data.shared_with_user_id,
            can_edit=data.can_edit,
        )
        if not share:
            raise HTTPException(
                status_code=404,
                detail="Report nicht gefunden oder keine Berechtigung",
            )
        return ShareResponse.model_validate(share)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Bericht"))


@router.delete(
    "/{report_id}/share/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_share(
    report_id: uuid.UUID,
    share_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Entfernt eine Report-Freigabe."""
    service = _get_service()
    success = await service.remove_share(
        db=db,
        report_id=report_id,
        owner_id=current_user.id,
        share_id=share_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Freigabe nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# SCHEDULE ENDPOINTS
# =============================================================================


@router.post("/{report_id}/schedule", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    report_id: uuid.UUID,
    data: ScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> ScheduleResponse:
    """Erstellt einen Zeitplan für automatischen Report-Versand per E-Mail."""
    from app.db.models_adhoc_report import (
        AdHocExportFormat,
        ReportScheduleFrequency,
    )

    service = _get_service()

    valid_frequencies = {"daily", "weekly", "monthly", "quarterly"}
    if data.frequency not in valid_frequencies:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Frequenz: {data.frequency}",
        )

    valid_formats = {"pdf", "excel", "csv"}
    if data.export_format not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiges Format: {data.export_format}",
        )

    try:
        schedule = await service.schedule_report(
            db=db,
            report_id=report_id,
            company_id=company_id,
            frequency=ReportScheduleFrequency(data.frequency),
            export_format=AdHocExportFormat(data.export_format),
            recipients=data.recipients,
            time_of_day=data.time_of_day,
            day_of_week=data.day_of_week,
            day_of_month=data.day_of_month,
        )
        return ScheduleResponse.model_validate(schedule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=safe_error_detail(e, "Bericht"))


@router.put("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    schedule_id: uuid.UUID,
    data: ScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> ScheduleResponse:
    """Aktualisiert einen Zeitplan."""
    service = _get_service()
    updates = data.model_dump(exclude_unset=True)
    result = await service.update_schedule(
        db=db,
        schedule_id=schedule_id,
        company_id=company_id,
        **updates,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Zeitplan nicht gefunden")
    return ScheduleResponse.model_validate(result)


@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> Response:
    """Löscht einen Zeitplan."""
    service = _get_service()
    success = await service.delete_schedule(db, schedule_id, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Zeitplan nicht gefunden")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/schedules", response_model=List[ScheduleResponse])
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    company_id: uuid.UUID = Depends(get_user_company_id_dep),
) -> List[ScheduleResponse]:
    """Listet alle Zeitpläne des aktuellen Mandanten."""
    service = _get_service()
    schedules = await service.list_schedules(db, company_id)
    return [ScheduleResponse.model_validate(s) for s in schedules]
