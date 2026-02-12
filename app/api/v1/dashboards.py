"""
Personalized Dashboards API - Enterprise Edition.

Features:
- Dashboard CRUD (Create, Read, Update, Delete)
- Widget Management (Add, Remove, Configure)
- Layout Persistence (Grid Positions, Sizes)
- Dashboard Sharing (Role-based, User-specific)
- Favorites & Presets
- Duplication & Templates

Feinpoliert und durchdacht - Enterprise-grade Dashboard-Management.
"""

import structlog
from typing import Dict, List, Optional

from app.core.types import JSONDict
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.dashboard_service import DashboardService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class LayoutItem(BaseModel):
    """Grid-Layout Item (react-grid-layout compatible)."""

    i: str = Field(..., description="Widget ID")
    x: int = Field(..., ge=0, le=11, description="X-Position (0-11 in 12-column grid)")
    y: int = Field(..., ge=0, description="Y-Position")
    w: int = Field(..., ge=1, le=12, description="Width in grid units")
    h: int = Field(..., ge=1, le=10, description="Height in grid units")
    minW: Optional[int] = Field(None, ge=1, le=12, description="Minimum width")
    minH: Optional[int] = Field(None, ge=1, le=10, description="Minimum height")
    maxW: Optional[int] = Field(None, ge=1, le=12, description="Maximum width")
    maxH: Optional[int] = Field(None, ge=1, le=10, description="Maximum height")
    static: bool = Field(default=False, description="Widget cannot be moved/resized")


class WidgetCreate(BaseModel):
    """Schema für Widget-Erstellung."""

    widget_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-z0-9_-]+$",
        description="Widget-Typ (z.B. document_count, invoice_summary)",
    )
    position: Optional[LayoutItem] = Field(None, description="Initiale Position (optional)")
    config: Optional[JSONDict] = Field(default_factory=dict, description="Widget-Konfiguration")
    title_override: Optional[str] = Field(None, max_length=100, description="Benutzerdefinierter Titel")

    @field_validator("widget_type")
    @classmethod
    def validate_widget_type(cls, v: str) -> str:
        """Validiere Widget-Typ Format."""
        allowed_types = {
            "document_count",
            "invoice_summary",
            "ocr_quality",
            "entity_list",
            "cashflow_chart",
            "recent_documents",
            "risk_overview",
            "workflow_status",
            "custom_chart",
            "system_status",
            "today",
            "quick_links",
            "upload",
            "finance_status",
            "open_invoices",
            "aging_report",
        }
        if v not in allowed_types:
            raise ValueError(f"Ungültiger Widget-Typ: {v}")
        return v


class WidgetUpdate(BaseModel):
    """Schema für Widget-Update."""

    position: Optional[LayoutItem] = None
    config: Optional[JSONDict] = None
    title_override: Optional[str] = Field(None, max_length=100)
    is_visible: Optional[bool] = None
    is_collapsed: Optional[bool] = None


class WidgetResponse(BaseModel):
    """Widget Response Schema."""

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
    """Schema für Dashboard-Erstellung."""

    name: str = Field(..., min_length=1, max_length=100, description="Dashboard-Name")
    description: Optional[str] = Field(None, max_length=500, description="Beschreibung")
    is_default: bool = Field(default=False, description="Als Standard-Dashboard setzen")
    columns: int = Field(default=12, ge=1, le=24, description="Grid-Spalten")
    row_height: int = Field(default=80, ge=20, le=200, description="Zeilenhöhe in Pixeln")
    compact_type: Optional[str] = Field(
        None,
        pattern="^(vertical|horizontal)$",
        description="Kompaktierungs-Modus",
    )
    widgets: Optional[List[JSONDict]] = Field(
        default_factory=list,
        description="Initiale Widgets",
    )


class DashboardUpdate(BaseModel):
    """Schema für Dashboard-Update."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_default: Optional[bool] = None
    columns: Optional[int] = Field(None, ge=1, le=24)
    row_height: Optional[int] = Field(None, ge=20, le=200)
    compact_type: Optional[str] = None
    default_date_range: Optional[str] = None
    default_company_id: Optional[str] = None


class DashboardResponse(BaseModel):
    """Dashboard Response Schema."""

    id: str
    name: str
    description: Optional[str] = None
    is_default: bool
    is_favorite: bool = False
    is_shared: bool = False
    columns: int
    row_height: int
    compact_type: Optional[str] = None
    default_date_range: Optional[str] = None
    default_company_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    shared_with_count: int = 0
    widgets: List[WidgetResponse] = []


class DashboardListItem(BaseModel):
    """Dashboard List Item Schema."""

    id: str
    name: str
    description: Optional[str] = None
    is_default: bool
    is_favorite: bool = False
    is_shared: bool = False
    widget_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    source: str = "own"  # own, shared


class LayoutUpdate(BaseModel):
    """Schema für Layout-Batch-Update."""

    widgets: List[LayoutItem] = Field(..., description="Komplettes Layout mit allen Widget-Positionen")


class ShareRequest(BaseModel):
    """Schema für Dashboard-Sharing."""

    user_ids: Optional[List[str]] = Field(default_factory=list, description="User-IDs zum Teilen")
    roles: Optional[List[str]] = Field(default_factory=list, description="Rollen zum Teilen")
    permissions: str = Field(
        default="view",
        pattern="^(view|edit)$",
        description="Berechtigungsstufe",
    )

    @field_validator("user_ids")
    @classmethod
    def validate_user_ids(cls, v: List[str]) -> List[str]:
        """Validiere User-IDs Format."""
        for user_id in v:
            try:
                UUID(user_id)
            except ValueError:
                raise ValueError(f"Ungültige User-ID: {user_id}")
        return v


class ShareResponse(BaseModel):
    """Share Response Schema."""

    dashboard_id: str
    shared_with_users: List[str]
    shared_with_roles: List[str]
    success: bool
    message: str


class PresetResponse(BaseModel):
    """Preset Response Schema."""

    id: str
    name: str
    description: Optional[str] = None
    category: str
    for_roles: Optional[List[str]] = None
    preview_image_url: Optional[str] = None
    widget_count: int


class AvailableWidget(BaseModel):
    """Available Widget Type Schema."""

    widget_type: str
    display_name: str
    description: Optional[str] = None
    requires_permission: bool
    required_permissions: Optional[List[str]] = None
    default_size: Dict[str, int]  # {"w": 4, "h": 3}


# =============================================================================
# Dashboard CRUD Endpoints
# =============================================================================


@router.get("", response_model=List[DashboardListItem])
async def list_dashboards(
    include_shared: bool = Query(default=True, description="Mit mir geteilte Dashboards einbeziehen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DashboardListItem]:
    """
    Listet alle eigenen Dashboards auf (optional inkl. geteilte).

    **Returns:**
    - Liste aller Dashboards mit Metadaten
    - `source` Feld zeigt an ob `own` oder `shared`
    """
    service = DashboardService(db)

    # Eigene Dashboards
    own_dashboards = await service.list_user_dashboards(current_user.id)
    result = [DashboardListItem(**d, source="own") for d in own_dashboards]

    # Geteilte Dashboards
    if include_shared:
        shared = await service.list_shared_dashboards(current_user.id)
        result.extend([DashboardListItem(**d, source="shared") for d in shared])

    logger.info(
        "dashboards_listed",
        user_id=str(current_user.id),
        count=len(result),
        include_shared=include_shared,
    )

    return result


@router.post("", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    data: DashboardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Erstellt ein neues Dashboard.

    **Body:**
    - `name`: Dashboard-Name (erforderlich)
    - `description`: Beschreibung (optional)
    - `is_default`: Als Standard setzen (optional, default: false)
    - `widgets`: Initiale Widget-Liste (optional)

    **Returns:**
    - Erstelltes Dashboard mit allen Widgets
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
        "dashboard_created",
        dashboard_id=dashboard["id"],
        user_id=str(current_user.id),
        name=data.name,
    )

    return DashboardResponse(**dashboard)


@router.get("/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Ruft ein spezifisches Dashboard ab.

    **Returns:**
    - Dashboard mit allen Widgets und Layout-Informationen

    **Errors:**
    - 404: Dashboard nicht gefunden oder keine Berechtigung
    """
    service = DashboardService(db)

    # Prüfe ob eigenes oder geteiltes Dashboard
    dashboard = await service.get_user_dashboard(current_user.id, dashboard_id)

    if not dashboard:
        # Prüfe ob geteilt
        dashboard = await service.get_shared_dashboard(current_user.id, dashboard_id)

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    return DashboardResponse(**dashboard)


@router.patch("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: UUID,
    data: DashboardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Aktualisiert Dashboard-Einstellungen.

    **Body:** Alle Felder optional (Partial Update)
    - `name`: Neuer Name
    - `description`: Neue Beschreibung
    - `is_default`: Als Standard setzen
    - `columns`, `row_height`, `compact_type`: Grid-Einstellungen

    **Errors:**
    - 404: Dashboard nicht gefunden
    - 400: Ungültige Company-ID
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

    logger.info(
        "dashboard_updated",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
    )

    return DashboardResponse(**dashboard)


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Löscht ein Dashboard.

    **Rules:**
    - Mindestens ein Dashboard muss existieren
    - Nur eigene Dashboards können gelöscht werden

    **Errors:**
    - 400: Letztes Dashboard kann nicht gelöscht werden
    - 404: Dashboard nicht gefunden
    """
    service = DashboardService(db)

    deleted = await service.delete_dashboard(current_user.id, dashboard_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dashboard konnte nicht gelöscht werden. Mindestens ein Dashboard muss existieren.",
        )

    logger.info(
        "dashboard_deleted",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Dashboard Actions
# =============================================================================


@router.post("/{dashboard_id}/duplicate", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_dashboard(
    dashboard_id: UUID,
    name: Optional[str] = Query(None, description="Name für das duplizierte Dashboard"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Dupliziert ein Dashboard.

    **Query Params:**
    - `name`: Name für Kopie (optional, default: "{Original-Name} (Kopie)")

    **Returns:**
    - Neues Dashboard mit allen Widgets
    """
    service = DashboardService(db)

    duplicated = await service.duplicate_dashboard(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        new_name=name,
    )

    if not duplicated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    logger.info(
        "dashboard_duplicated",
        original_id=str(dashboard_id),
        new_id=duplicated["id"],
        user_id=str(current_user.id),
    )

    return DashboardResponse(**duplicated)


@router.patch("/{dashboard_id}/favorite", response_model=DashboardResponse)
async def set_favorite_dashboard(
    dashboard_id: UUID,
    is_favorite: bool = Query(..., description="Als Favorit setzen oder entfernen"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Setzt oder entfernt Dashboard als Favorit.

    **Query Params:**
    - `is_favorite`: true = Favorit setzen, false = entfernen

    **Returns:**
    - Aktualisiertes Dashboard
    """
    service = DashboardService(db)

    dashboard = await service.set_favorite(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        is_favorite=is_favorite,
    )

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    logger.info(
        "dashboard_favorite_toggled",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
        is_favorite=is_favorite,
    )

    return DashboardResponse(**dashboard)


# =============================================================================
# Sharing Endpoints
# =============================================================================


@router.post("/{dashboard_id}/share", response_model=ShareResponse)
async def share_dashboard(
    dashboard_id: UUID,
    data: ShareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ShareResponse:
    """
    Teilt ein Dashboard mit anderen Usern oder Rollen.

    **Body:**
    - `user_ids`: Liste von User-IDs (optional)
    - `roles`: Liste von Rollen (z.B. ["editor", "viewer"]) (optional)
    - `permissions`: "view" oder "edit" (default: "view")

    **Returns:**
    - Bestätigung mit Liste der geteilten User/Rollen

    **Errors:**
    - 404: Dashboard nicht gefunden
    - 400: Keine User-IDs oder Rollen angegeben
    """
    service = DashboardService(db)

    if not data.user_ids and not data.roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mindestens User-IDs oder Rollen müssen angegeben werden",
        )

    # Convert string IDs to UUIDs
    user_uuids = [UUID(uid) for uid in data.user_ids] if data.user_ids else []

    result = await service.share_dashboard(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        share_with_users=user_uuids,
        share_with_roles=data.roles,
        permissions=data.permissions,
    )

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    logger.info(
        "dashboard_shared",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
        shared_with_users=len(user_uuids),
        shared_with_roles=len(data.roles) if data.roles else 0,
    )

    return ShareResponse(
        dashboard_id=str(dashboard_id),
        shared_with_users=data.user_ids or [],
        shared_with_roles=data.roles or [],
        success=True,
        message="Dashboard erfolgreich geteilt",
    )


@router.delete("/{dashboard_id}/share/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unshare_dashboard(
    dashboard_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Entfernt Sharing für einen bestimmten User.

    **Errors:**
    - 404: Dashboard nicht gefunden oder nicht geteilt mit diesem User
    """
    service = DashboardService(db)

    removed = await service.unshare_dashboard(
        owner_id=current_user.id,
        dashboard_id=dashboard_id,
        user_id=user_id,
    )

    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sharing nicht gefunden",
        )

    logger.info(
        "dashboard_unshared",
        dashboard_id=str(dashboard_id),
        owner_id=str(current_user.id),
        removed_user_id=str(user_id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/shared", response_model=List[DashboardListItem])
async def list_shared_dashboards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DashboardListItem]:
    """
    Listet alle mit mir geteilten Dashboards auf.

    **Returns:**
    - Liste der geteilten Dashboards mit `source="shared"`
    """
    service = DashboardService(db)
    shared = await service.list_shared_dashboards(current_user.id)

    return [DashboardListItem(**d, source="shared") for d in shared]


# =============================================================================
# Layout Endpoints
# =============================================================================


@router.patch("/{dashboard_id}/layout", status_code=status.HTTP_200_OK)
async def update_layout(
    dashboard_id: UUID,
    data: LayoutUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONDict:
    """
    Aktualisiert das komplette Layout (alle Widget-Positionen).

    **Use Case:** Drag & Drop, Resize Events

    **Body:**
    - `widgets`: Array von Layout-Items mit ID, x, y, w, h

    **Returns:**
    - Erfolgsbestätigung

    **Errors:**
    - 404: Dashboard nicht gefunden
    """
    service = DashboardService(db)

    # Convert LayoutItems to dicts
    widgets_data = [item.model_dump() for item in data.widgets]

    updated = await service.update_layout(
        user_id=current_user.id,
        dashboard_id=dashboard_id,
        widgets=widgets_data,
    )

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard nicht gefunden",
        )

    logger.info(
        "layout_updated",
        dashboard_id=str(dashboard_id),
        user_id=str(current_user.id),
        widget_count=len(widgets_data),
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
    Listet alle verfügbaren Widget-Typen für den aktuellen User.

    **Returns:**
    - Liste aller Widgets mit Berechtigungsinformationen
    - Nur Widgets mit ausreichenden Permissions werden angezeigt
    """
    service = DashboardService(db)

    # Get user permissions (in production from RBAC)
    user_permissions = await _get_user_permissions(current_user)

    widgets = await service.get_available_widgets(user_permissions)

    # Add display names and default sizes
    enriched_widgets = []
    for widget in widgets:
        enriched_widgets.append(
            AvailableWidget(
                widget_type=widget["widget_type"],
                display_name=_get_widget_display_name(widget["widget_type"]),
                description=_get_widget_description(widget["widget_type"]),
                requires_permission=widget["requires_permission"],
                required_permissions=widget.get("required_permissions"),
                default_size=_get_default_widget_size(widget["widget_type"]),
            )
        )

    return enriched_widgets


@router.post("/{dashboard_id}/widgets", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
async def add_widget(
    dashboard_id: UUID,
    data: WidgetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WidgetResponse:
    """
    Fügt ein neues Widget zum Dashboard hinzu.

    **Body:**
    - `widget_type`: Widget-Typ (erforderlich)
    - `position`: Initiale Position (optional, auto-platziert wenn fehlt)
    - `config`: Widget-spezifische Konfiguration (optional)
    - `title_override`: Benutzerdefinierter Titel (optional)

    **Returns:**
    - Erstelltes Widget mit ID und Position

    **Errors:**
    - 403: Keine Berechtigung für diesen Widget-Typ
    - 404: Dashboard nicht gefunden
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

    logger.info(
        "widget_added",
        widget_id=widget["id"],
        dashboard_id=str(dashboard_id),
        widget_type=data.widget_type,
    )

    return WidgetResponse(**widget)


@router.patch("/{dashboard_id}/widgets/{widget_id}", response_model=WidgetResponse)
async def update_widget(
    dashboard_id: UUID,
    widget_id: UUID,
    data: WidgetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WidgetResponse:
    """
    Aktualisiert Widget-Konfiguration.

    **Body:** Alle Felder optional (Partial Update)
    - `position`: Neue Position
    - `config`: Neue Konfiguration
    - `title_override`: Neuer Titel
    - `is_visible`: Sichtbarkeit
    - `is_collapsed`: Eingeklappt-Status

    **Errors:**
    - 404: Widget oder Dashboard nicht gefunden
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


@router.delete("/{dashboard_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_widget(
    dashboard_id: UUID,
    widget_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """
    Entfernt ein Widget vom Dashboard.

    **Errors:**
    - 404: Widget nicht gefunden
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

    logger.info(
        "widget_removed",
        widget_id=str(widget_id),
        dashboard_id=str(dashboard_id),
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# =============================================================================
# Preset Endpoints
# =============================================================================


@router.get("/presets", response_model=List[PresetResponse])
async def list_presets(
    category: Optional[str] = Query(None, description="Filter nach Kategorie (default, finance, admin)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[PresetResponse]:
    """
    Listet verfügbare Dashboard-Presets/Templates auf.

    **Query Params:**
    - `category`: Optional Filter nach Kategorie

    **Returns:**
    - Liste aller Templates für die User-Rolle
    """
    service = DashboardService(db)

    # Get user roles (in production from RBAC)
    user_roles = [getattr(current_user, "role", "viewer")]

    templates = await service.get_templates(
        user_roles=user_roles,
        category=category,
    )

    # Convert to PresetResponse
    presets = []
    for template in templates:
        presets.append(
            PresetResponse(
                id=template["id"],
                name=template["name"],
                description=template["description"],
                category=template["category"],
                for_roles=template["for_roles"],
                preview_image_url=template.get("preview_image_url"),
                widget_count=len(template["layout"]) if template.get("layout") else 0,
            )
        )

    return presets


@router.post("/from-preset/{preset_id}", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_from_preset(
    preset_id: UUID,
    name: Optional[str] = Query(None, description="Benutzerdefinierter Name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Erstellt ein Dashboard von einem Preset/Template.

    **Query Params:**
    - `name`: Name für das neue Dashboard (optional, nutzt Template-Name wenn fehlt)

    **Returns:**
    - Erstelltes Dashboard mit allen Widgets vom Template

    **Errors:**
    - 404: Template nicht gefunden
    """
    service = DashboardService(db)

    dashboard = await service.apply_template(
        user_id=current_user.id,
        template_id=preset_id,
        dashboard_name=name,
    )

    if not dashboard:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template nicht gefunden",
        )

    logger.info(
        "dashboard_from_preset",
        preset_id=str(preset_id),
        dashboard_id=dashboard["id"],
        user_id=str(current_user.id),
    )

    return DashboardResponse(**dashboard)


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_user_permissions(user: User) -> List[str]:
    """
    Ermittelt Benutzerberechtigungen.

    In Production würde dies aus dem RBAC-System kommen.
    Hier vereinfachte Role-basierte Permissions.
    """
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


def _get_widget_display_name(widget_type: str) -> str:
    """Gibt deutschen Anzeigenamen für Widget-Typ zurück."""
    names = {
        "document_count": "Dokument-Anzahl",
        "invoice_summary": "Rechnungsübersicht",
        "ocr_quality": "OCR-Qualität",
        "entity_list": "Geschäftspartner",
        "cashflow_chart": "Cashflow-Diagramm",
        "recent_documents": "Letzte Dokumente",
        "risk_overview": "Risiko-Übersicht",
        "workflow_status": "Workflow-Status",
        "custom_chart": "Benutzerdefiniertes Diagramm",
        "system_status": "System-Status",
        "today": "Heute",
        "quick_links": "Schnellzugriff",
        "upload": "Upload",
        "finance_status": "Finanz-Status",
        "open_invoices": "Offene Rechnungen",
        "aging_report": "Fälligkeitsübersicht",
    }
    return names.get(widget_type, widget_type.replace("_", " ").title())


def _get_widget_description(widget_type: str) -> Optional[str]:
    """Gibt deutsche Beschreibung für Widget-Typ zurück."""
    descriptions = {
        "document_count": "Zeigt die Anzahl der Dokumente nach Kategorien",
        "invoice_summary": "Übersicht über offene und bezahlte Rechnungen",
        "ocr_quality": "Qualitätsmetriken der OCR-Verarbeitung",
        "entity_list": "Liste der Geschäftspartner mit Statistiken",
        "cashflow_chart": "Visualisierung des Cashflows über Zeit",
        "recent_documents": "Zuletzt hochgeladene oder verarbeitete Dokumente",
        "risk_overview": "Risiko-Scores der Geschäftspartner",
        "workflow_status": "Status laufender Workflows",
        "custom_chart": "Benutzerdefinierte Datenvisualisierung",
        "system_status": "System-Metriken und Gesundheit",
        "today": "Heutige Aufgaben und Ereignisse",
        "quick_links": "Schnellzugriff auf häufige Aktionen",
        "upload": "Dokument-Upload Widget",
        "finance_status": "Finanzielle Kennzahlen",
        "open_invoices": "Liste offener Rechnungen",
        "aging_report": "Fälligkeiten nach Zeitraum",
    }
    return descriptions.get(widget_type)


def _get_default_widget_size(widget_type: str) -> Dict[str, int]:
    """Gibt Standard-Größe für Widget-Typ zurück."""
    sizes = {
        "document_count": {"w": 4, "h": 3},
        "invoice_summary": {"w": 6, "h": 4},
        "ocr_quality": {"w": 6, "h": 3},
        "entity_list": {"w": 8, "h": 5},
        "cashflow_chart": {"w": 8, "h": 4},
        "recent_documents": {"w": 6, "h": 4},
        "risk_overview": {"w": 6, "h": 4},
        "workflow_status": {"w": 4, "h": 3},
        "custom_chart": {"w": 6, "h": 4},
        "system_status": {"w": 4, "h": 3},
        "today": {"w": 4, "h": 3},
        "quick_links": {"w": 4, "h": 3},
        "upload": {"w": 6, "h": 4},
        "finance_status": {"w": 6, "h": 3},
        "open_invoices": {"w": 8, "h": 5},
        "aging_report": {"w": 6, "h": 4},
    }
    return sizes.get(widget_type, {"w": 4, "h": 3})
