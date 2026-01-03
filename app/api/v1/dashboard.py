"""
Dashboard API Endpoints.

Enterprise-Level Dashboard-Management:
- CRUD fuer personalisierte Dashboards
- Widget-Management mit Drag & Drop Layout
- Permission-basierte Widget-Filterung
- Dashboard-Templates

Feinpoliert und durchdacht - Personalisierte Dashboards auf Enterprise-Niveau.
"""

import structlog
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_db
from app.db.models import User
from app.services.dashboard_service import DashboardService

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
    h: int = Field(default=3, ge=1, le=10, description="Hoehe in Grid-Einheiten")
    minW: Optional[int] = Field(None, description="Minimale Breite")
    minH: Optional[int] = Field(None, description="Minimale Hoehe")
    maxW: Optional[int] = Field(None, description="Maximale Breite")
    maxH: Optional[int] = Field(None, description="Maximale Hoehe")


class WidgetCreate(BaseModel):
    """Schema fuer neues Widget."""

    widget_type: str = Field(..., min_length=1, max_length=50)
    position: Optional[WidgetPositionSchema] = None
    config: Optional[Dict[str, Any]] = None
    title_override: Optional[str] = Field(None, max_length=100)


class WidgetUpdate(BaseModel):
    """Schema fuer Widget-Update."""

    position: Optional[WidgetPositionSchema] = None
    config: Optional[Dict[str, Any]] = None
    title_override: Optional[str] = None
    is_visible: Optional[bool] = None
    is_collapsed: Optional[bool] = None


class WidgetResponse(BaseModel):
    """Response Schema fuer Widget."""

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
    config: Optional[Dict[str, Any]] = None
    title_override: Optional[str] = None
    filter_overrides: Optional[Dict[str, Any]] = None
    is_visible: bool = True
    is_collapsed: bool = False
    sort_order: int = 0


class DashboardCreate(BaseModel):
    """Schema fuer neues Dashboard."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    is_default: bool = False
    columns: int = Field(default=12, ge=1, le=24)
    row_height: int = Field(default=80, ge=20, le=200)
    compact_type: Optional[str] = Field(None, pattern="^(vertical|horizontal)$")
    widgets: Optional[List[Dict[str, Any]]] = None


class DashboardUpdate(BaseModel):
    """Schema fuer Dashboard-Update."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_default: Optional[bool] = None
    columns: Optional[int] = Field(None, ge=1, le=24)
    row_height: Optional[int] = Field(None, ge=20, le=200)
    compact_type: Optional[str] = None
    default_date_range: Optional[str] = None
    default_company_id: Optional[str] = None


class DashboardResponse(BaseModel):
    """Response Schema fuer Dashboard."""

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
    """Response Schema fuer Dashboard-Liste."""

    id: str
    name: str
    description: Optional[str] = None
    is_default: bool
    widget_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class LayoutUpdate(BaseModel):
    """Schema fuer Layout-Update (Batch)."""

    widgets: List[Dict[str, Any]] = Field(..., description="Liste von Widget-Positionen mit ID")


class AvailableWidget(BaseModel):
    """Schema fuer verfuegbare Widgets."""

    widget_type: str
    requires_permission: bool
    required_permissions: Optional[List[str]] = None


class TemplateResponse(BaseModel):
    """Response Schema fuer Dashboard-Template."""

    id: str
    name: str
    description: Optional[str] = None
    category: str
    for_roles: Optional[List[str]] = None
    layout: List[Dict[str, Any]]
    preview_image_url: Optional[str] = None


# =============================================================================
# Dashboard Endpoints
# =============================================================================


@router.get("", response_model=DashboardResponse)
async def get_default_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """
    Gibt das Standard-Dashboard des Benutzers zurueck.

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
    Gibt ein spezifisches Dashboard zurueck.
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
                detail="Ungueltige Company-ID",
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


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Loescht ein Dashboard.

    Das letzte Dashboard kann nicht geloescht werden.
    """
    service = DashboardService(db)
    deleted = await service.delete_dashboard(current_user.id, dashboard_id)

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dashboard konnte nicht geloescht werden. Mindestens ein Dashboard muss existieren.",
        )


# =============================================================================
# Layout Endpoints
# =============================================================================


@router.put("/{dashboard_id}/layout", status_code=status.HTTP_200_OK)
async def update_layout(
    dashboard_id: UUID,
    data: LayoutUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
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
    Listet alle verfuegbaren Widgets basierend auf Benutzerberechtigungen auf.
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
            detail="Keine Berechtigung fuer dieses Widget",
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


@router.delete("/{dashboard_id}/widgets/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_widget(
    dashboard_id: UUID,
    widget_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
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
    Listet verfuegbare Dashboard-Templates auf.
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
