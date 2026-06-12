# -*- coding: utf-8 -*-
"""
Dashboard-Builder API Endpoints fuer Ablage-System.

Phase 7.3: Dashboard-Builder

Endpunkte:
  GET    /api/v1/dashboards                           - Dashboards auflisten
  POST   /api/v1/dashboards                           - Dashboard erstellen
  GET    /api/v1/dashboards/default                   - Standard-Dashboard der Rolle
  GET    /api/v1/dashboards/widgets/{type}/data       - Live-Daten fuer Widget-Typ
  GET    /api/v1/dashboards/{id}                      - Dashboard mit Widgets
  PUT    /api/v1/dashboards/{id}                      - Dashboard-Layout aktualisieren
  DELETE /api/v1/dashboards/{id}                      - Dashboard loeschen
  POST   /api/v1/dashboards/{id}/share               - Freigabe umschalten
  POST   /api/v1/dashboards/{id}/widgets              - Widget hinzufuegen
  DELETE /api/v1/dashboards/{id}/widgets/{widget_id} - Widget entfernen

Alle user-facing Texte sind auf Deutsch.
Feinpoliert und durchdacht - Enterprise Dashboard-Builder API.
"""

from typing import Dict, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_db
from app.core.safe_errors import safe_error_log
from app.db.models import Company, User
from app.db.models_dashboard import WidgetTypeEnum
from app.middleware.company_context import require_company
from app.services.dashboard_builder_service import DashboardBuilderService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboards", tags=["Dashboard-Builder"])


# =============================================================================
# Pydantic Request / Response Schemas
# =============================================================================


class LayoutItem(BaseModel):
    """Grid-Layout-Position eines Widgets."""

    widget_id: str = Field(..., description="UUID des Widgets")
    x: int = Field(..., ge=0, le=11, description="X-Position im 12-Spalten-Grid")
    y: int = Field(..., ge=0, description="Y-Position (Zeile, 0-basiert)")
    w: int = Field(..., ge=1, le=12, description="Breite (Anzahl Spalten, 1-12)")
    h: int = Field(..., ge=1, description="Hoehe (Anzahl Zeilen, min. 1)")


class CreateDashboardRequest(BaseModel):
    """Request-Schema fuer die Dashboard-Erstellung."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Anzeigename des Dashboards",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Optionale Beschreibung",
    )
    layout: List[LayoutItem] = Field(
        default_factory=list,
        description="Initiales Grid-Layout",
    )
    is_shared: bool = Field(
        default=False,
        description="Firmenweit freigeben",
    )


class UpdateDashboardRequest(BaseModel):
    """Request-Schema fuer die Dashboard-Aktualisierung."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Neuer Anzeigename (optional)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Neue Beschreibung (optional)",
    )
    layout: Optional[List[LayoutItem]] = Field(
        default=None,
        description="Neues Grid-Layout (optional)",
    )


class AddWidgetRequest(BaseModel):
    """Request-Schema fuer das Hinzufuegen eines Widgets."""

    widget_type: str = Field(
        ...,
        description=(
            "Widget-Typ: invoice_status, cashflow_chart, ocr_queue, "
            "kpi_cards, anomaly_summary, recent_documents, open_tasks, "
            "integration_health, active_learning_stats"
        ),
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Anzeigename des Widgets",
    )
    config: Dict[str, object] = Field(
        default_factory=dict,
        description="Widget-spezifische Einstellungen",
    )
    data_source: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Explizite Datenquelle (optional, wird sonst abgeleitet)",
    )
    refresh_interval_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Aktualisierungsintervall in Sekunden (30-3600)",
    )

    @field_validator("widget_type")
    @classmethod
    def validate_widget_type(cls, v: str) -> str:
        """Validiert den Widget-Typ gegen die erlaubte Liste."""
        valid = {wt.value for wt in WidgetTypeEnum}
        if v not in valid:
            raise ValueError(
                f"Ungueltiger Widget-Typ '{v}'. "
                f"Erlaubte Typen: {', '.join(sorted(valid))}"
            )
        return v


class DashboardSummaryResponse(BaseModel):
    """Kurzantwort fuer Dashboard-Liste (ohne Widget-Details)."""

    id: str
    company_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    is_default: bool
    is_shared: bool
    is_owner: bool
    layout: List[Dict[str, object]] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DashboardListResponse(BaseModel):
    """Liste von Dashboards."""

    items: List[DashboardSummaryResponse]
    total: int


class WidgetResponse(BaseModel):
    """Widget-Antwort."""

    id: str
    dashboard_id: str
    widget_type: str
    title: str
    config: Dict[str, object] = Field(default_factory=dict)
    data_source: str
    refresh_interval_seconds: int
    created_at: Optional[str] = None


class DashboardDetailResponse(BaseModel):
    """Vollstaendige Dashboard-Antwort inkl. Widgets."""

    id: str
    company_id: str
    user_id: str
    name: str
    description: Optional[str] = None
    layout: List[Dict[str, object]] = Field(default_factory=list)
    is_default: bool
    is_shared: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    widgets: List[WidgetResponse] = Field(default_factory=list)


class ShareToggleResponse(BaseModel):
    """Antwort nach Freigabe-Umschalten."""

    id: str
    name: str
    is_shared: bool
    message: str
    updated_at: Optional[str] = None


class DeleteResponse(BaseModel):
    """Antwort nach erfolgreichem Loeschen."""

    message: str


class WidgetDataResponse(BaseModel):
    """Live-Daten eines Widget-Typs."""

    widget_type: str
    data: Dict[str, object] = Field(default_factory=dict)
    error: Optional[str] = None


# =============================================================================
# Hilfsfunktionen
# =============================================================================


def _layout_items_to_dicts(items: List[LayoutItem]) -> List[Dict]:
    """Konvertiert LayoutItem-Objekte in native Dicts (fuer JSONB-Speicherung)."""
    return [item.model_dump() for item in items]


def _get_service() -> DashboardBuilderService:
    """Factory fuer den DashboardBuilderService."""
    return DashboardBuilderService()


# =============================================================================
# Endpunkte - Reihenfolge: statische Pfade vor dynamischen!
# =============================================================================


@router.get(
    "/default",
    response_model=DashboardDetailResponse,
    summary="Standard-Dashboard der Benutzerrolle",
    description=(
        "Gibt das Standard-Dashboard fuer die aktuelle Benutzerrolle zurueck. "
        "Existiert noch keines, wird es automatisch mit den Rollen-Standardwidgets erstellt. "
        "Rollen: buchhaltung, management, sachbearbeitung, admin."
    ),
)
async def get_default_dashboard(
    role: str = Query(
        default="sachbearbeitung",
        description="Benutzerrolle (buchhaltung, management, sachbearbeitung, admin)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DashboardDetailResponse:
    """Holt oder erstellt das Standard-Dashboard fuer die angegebene Rolle."""
    logger.info(
        "dashboard_builder.api.get_default",
        user_id=str(current_user.id),
        company_id=str(company.id),
        role=role,
    )

    service = _get_service()
    try:
        dashboard = await service.get_default_dashboard_for_role(
            db=db,
            company_id=company.id,
            user_id=current_user.id,
            role=role,
        )
        await db.commit()
        return DashboardDetailResponse(**dashboard)
    except Exception as exc:
        logger.error(
            "dashboard_builder.api.get_default.failed",
            user_id=str(current_user.id),
            company_id=str(company.id),
            role=role,
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Standard-Dashboard konnte nicht geladen werden.",
        )


@router.get(
    "/widgets/{widget_type}/data",
    response_model=WidgetDataResponse,
    summary="Live-Daten fuer einen Widget-Typ abrufen",
    description=(
        "Holt aktuelle Live-Daten fuer den angegebenen Widget-Typ vom "
        "zustaendigen Fach-Service. Bei temporaeren Fehlern werden leere "
        "Daten mit einer Fehlermeldung zurueckgegeben (Graceful Degradation)."
    ),
)
async def get_widget_data(
    widget_type: str = Path(
        ...,
        description=(
            "Widget-Typ: invoice_status | cashflow_chart | ocr_queue | "
            "kpi_cards | anomaly_summary | recent_documents | "
            "open_tasks | integration_health | active_learning_stats"
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> WidgetDataResponse:
    """Holt Live-Daten fuer einen bestimmten Widget-Typ."""
    logger.info(
        "dashboard_builder.api.get_widget_data",
        widget_type=widget_type,
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    # Widget-Typ validieren
    valid_types = {wt.value for wt in WidgetTypeEnum}
    if widget_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Ungueltiger Widget-Typ '{widget_type}'. "
                f"Erlaubte Typen: {', '.join(sorted(valid_types))}"
            ),
        )

    service = _get_service()
    result = await service.get_widget_data(
        db=db,
        widget_type=widget_type,
        company_id=company.id,
    )
    return WidgetDataResponse(**result)


@router.get(
    "",
    response_model=DashboardListResponse,
    operation_id="builder_list_dashboards",
    summary="Dashboards auflisten",
    description=(
        "Gibt alle sichtbaren Dashboards zurueck: eigene Dashboards des Benutzers "
        "sowie firmenweit freigegebene Dashboards anderer Benutzer."
    ),
)
async def list_dashboards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DashboardListResponse:
    """Listet alle sichtbaren Dashboards des aktuellen Benutzers auf."""
    logger.info(
        "dashboard_builder.api.list",
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    service = _get_service()
    try:
        items = await service.get_dashboards(
            db=db,
            company_id=company.id,
            user_id=current_user.id,
        )
        return DashboardListResponse(
            items=[DashboardSummaryResponse(**item) for item in items],
            total=len(items),
        )
    except Exception as exc:
        logger.error(
            "dashboard_builder.api.list.failed",
            user_id=str(current_user.id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboards konnten nicht geladen werden.",
        )


@router.post(
    "",
    response_model=DashboardDetailResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="builder_create_dashboard",
    summary="Neues Dashboard erstellen",
    description=(
        "Erstellt ein neues benutzerdefiniertes Dashboard. "
        "Das erste Dashboard eines Benutzers wird automatisch als Standard markiert."
    ),
)
async def create_dashboard(
    request: CreateDashboardRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DashboardDetailResponse:
    """Erstellt ein neues Dashboard fuer den aktuellen Benutzer."""
    logger.info(
        "dashboard_builder.api.create",
        user_id=str(current_user.id),
        company_id=str(company.id),
        name=request.name,
    )

    service = _get_service()
    try:
        layout_dicts = _layout_items_to_dicts(request.layout)
        dashboard = await service.create_dashboard(
            db=db,
            company_id=company.id,
            user_id=current_user.id,
            name=request.name,
            layout=layout_dicts,
            description=request.description,
            is_shared=request.is_shared,
        )
        await db.commit()
        # Widgets-Liste ist bei Neuerstellung leer
        dashboard.setdefault("widgets", [])
        return DashboardDetailResponse(**dashboard)
    except Exception as exc:
        await db.rollback()
        logger.error(
            "dashboard_builder.api.create.failed",
            user_id=str(current_user.id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard konnte nicht erstellt werden.",
        )


@router.get(
    "/{dashboard_id}",
    response_model=DashboardDetailResponse,
    operation_id="builder_get_dashboard",
    summary="Dashboard mit Widgets abrufen",
    description="Gibt ein einzelnes Dashboard mit allen zugehoerigen Widgets zurueck.",
)
async def get_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DashboardDetailResponse:
    """Holt ein Dashboard mit allen Widget-Details."""
    logger.info(
        "dashboard_builder.api.get",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    service = _get_service()
    try:
        dashboard = await service.get_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            company_id=company.id,
        )
    except Exception as exc:
        logger.error(
            "dashboard_builder.api.get.failed",
            dashboard_id=str(dashboard_id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard konnte nicht geladen werden.",
        )

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden.",
        )

    return DashboardDetailResponse(**dashboard)


@router.put(
    "/{dashboard_id}",
    response_model=DashboardDetailResponse,
    summary="Dashboard-Layout aktualisieren",
    description=(
        "Aktualisiert Name, Beschreibung oder Grid-Layout eines Dashboards. "
        "Nur der Eigentuemer kann sein Dashboard bearbeiten."
    ),
)
async def update_dashboard(
    request: UpdateDashboardRequest,
    dashboard_id: UUID = Path(..., description="Dashboard-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DashboardDetailResponse:
    """Aktualisiert ein Dashboard (nur Eigentuemer)."""
    logger.info(
        "dashboard_builder.api.update",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    service = _get_service()
    try:
        layout_dicts = (
            _layout_items_to_dicts(request.layout)
            if request.layout is not None
            else None
        )
        dashboard = await service.update_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            company_id=company.id,
            user_id=current_user.id,
            layout=layout_dicts,
            name=request.name,
            description=request.description,
        )
        if dashboard is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard nicht gefunden oder kein Bearbeitungsrecht.",
            )
        await db.commit()

        # Widgets fuer die Antwort laden
        full = await service.get_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            company_id=company.id,
        )
        if not full:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard nach Aktualisierung nicht auffindbar.",
            )
        return DashboardDetailResponse(**full)
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error(
            "dashboard_builder.api.update.failed",
            dashboard_id=str(dashboard_id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard konnte nicht aktualisiert werden.",
        )


@router.delete(
    "/{dashboard_id}",
    response_model=DeleteResponse,
    operation_id="builder_delete_dashboard",
    summary="Dashboard loeschen",
    description=(
        "Loescht ein Dashboard und alle zugehoerigen Widgets. "
        "Das Standard-Dashboard (is_default=true) kann nicht geloescht werden. "
        "Nur der Eigentuemer kann loeschen."
    ),
)
async def delete_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DeleteResponse:
    """Loescht ein Dashboard (nur Eigentuemer, kein Standard-Dashboard)."""
    logger.info(
        "dashboard_builder.api.delete",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    service = _get_service()
    try:
        deleted = await service.delete_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            company_id=company.id,
            user_id=current_user.id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard nicht gefunden oder kein Loeschrecht.",
            )
        await db.commit()
        return DeleteResponse(message="Dashboard wurde erfolgreich geloescht.")
    except HTTPException:
        raise
    except ValueError as exc:
        # Standard-Dashboard-Schutz
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except Exception as exc:
        await db.rollback()
        logger.error(
            "dashboard_builder.api.delete.failed",
            dashboard_id=str(dashboard_id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dashboard konnte nicht geloescht werden.",
        )


@router.post(
    "/{dashboard_id}/share",
    response_model=ShareToggleResponse,
    operation_id="builder_share_dashboard",
    summary="Dashboard-Freigabe umschalten",
    description=(
        "Schaltet die firmenweite Freigabe des Dashboards um (Toggle). "
        "Nur der Eigentuemer kann die Freigabe aendern."
    ),
)
async def share_dashboard(
    dashboard_id: UUID = Path(..., description="Dashboard-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> ShareToggleResponse:
    """Schaltet die Freigabe eines Dashboards um."""
    logger.info(
        "dashboard_builder.api.share",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    service = _get_service()
    try:
        result = await service.share_dashboard(
            db=db,
            dashboard_id=dashboard_id,
            company_id=company.id,
            user_id=current_user.id,
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard nicht gefunden oder kein Aenderungsrecht.",
            )
        await db.commit()

        is_shared: bool = result["is_shared"]
        message = (
            "Dashboard wurde firmenweit freigegeben."
            if is_shared
            else "Dashboard-Freigabe wurde aufgehoben."
        )
        return ShareToggleResponse(
            id=result["id"],
            name=result["name"],
            is_shared=is_shared,
            message=message,
            updated_at=result.get("updated_at"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error(
            "dashboard_builder.api.share.failed",
            dashboard_id=str(dashboard_id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Freigabe-Status konnte nicht geaendert werden.",
        )


@router.post(
    "/{dashboard_id}/widgets",
    response_model=WidgetResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="builder_add_widget",
    summary="Widget zum Dashboard hinzufuegen",
    description=(
        "Fuegt ein neues Widget zum Dashboard hinzu. "
        "Die Datenquelle wird automatisch aus dem Widget-Typ abgeleitet, "
        "wenn nicht explizit angegeben."
    ),
)
async def add_widget(
    request: AddWidgetRequest,
    dashboard_id: UUID = Path(..., description="Dashboard-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> WidgetResponse:
    """Fuegt ein Widget zum Dashboard hinzu."""
    logger.info(
        "dashboard_builder.api.add_widget",
        dashboard_id=str(dashboard_id),
        widget_type=request.widget_type,
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    service = _get_service()
    try:
        widget = await service.add_widget(
            db=db,
            dashboard_id=dashboard_id,
            company_id=company.id,
            widget_type=request.widget_type,
            title=request.title,
            config=dict(request.config),
            data_source=request.data_source,
            refresh_interval_seconds=request.refresh_interval_seconds,
        )
        if widget is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Dashboard nicht gefunden oder kein Zugriff.",
            )
        await db.commit()
        return WidgetResponse(**widget)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        await db.rollback()
        logger.error(
            "dashboard_builder.api.add_widget.failed",
            dashboard_id=str(dashboard_id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Widget konnte nicht hinzugefuegt werden.",
        )


@router.delete(
    "/{dashboard_id}/widgets/{widget_id}",
    response_model=DeleteResponse,
    operation_id="builder_remove_widget",
    summary="Widget vom Dashboard entfernen",
    description="Entfernt ein Widget vom Dashboard.",
)
async def remove_widget(
    dashboard_id: UUID = Path(..., description="Dashboard-UUID"),
    widget_id: UUID = Path(..., description="Widget-UUID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    company: Company = Depends(require_company),
) -> DeleteResponse:
    """Entfernt ein Widget vom Dashboard."""
    logger.info(
        "dashboard_builder.api.remove_widget",
        dashboard_id=str(dashboard_id),
        widget_id=str(widget_id),
        user_id=str(current_user.id),
        company_id=str(company.id),
    )

    service = _get_service()
    try:
        deleted = await service.remove_widget(
            db=db,
            widget_id=widget_id,
            dashboard_id=dashboard_id,
            company_id=company.id,
        )
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Widget nicht gefunden.",
            )
        await db.commit()
        return DeleteResponse(message="Widget wurde erfolgreich entfernt.")
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.error(
            "dashboard_builder.api.remove_widget.failed",
            dashboard_id=str(dashboard_id),
            widget_id=str(widget_id),
            company_id=str(company.id),
            **safe_error_log(exc),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Widget konnte nicht entfernt werden.",
        )
