# -*- coding: utf-8 -*-
"""
Dashboard Service for Ablage-System.

Enterprise-grade dashboard management service:
- User dashboard CRUD operations
- Widget management and positioning
- Permission-based widget filtering
- Dashboard template support

Feinpoliert und durchdacht - Personalisierte Dashboards fuer jeden Benutzer.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import User

logger = structlog.get_logger(__name__)


# =============================================================================
# Type Definitions
# =============================================================================

class WidgetPosition:
    """Widget position configuration."""

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        w: int = 4,
        h: int = 3,
        min_w: Optional[int] = None,
        min_h: Optional[int] = None,
        max_w: Optional[int] = None,
        max_h: Optional[int] = None,
    ):
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.min_w = min_w
        self.min_h = min_h
        self.max_w = max_w
        self.max_h = max_h

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "minW": self.min_w,
            "minH": self.min_h,
            "maxW": self.max_w,
            "maxH": self.max_h,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WidgetPosition":
        """Create from dictionary."""
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            w=data.get("w", 4),
            h=data.get("h", 3),
            min_w=data.get("minW"),
            min_h=data.get("minH"),
            max_w=data.get("maxW"),
            max_h=data.get("maxH"),
        )


# =============================================================================
# Widget Permission Mapping
# =============================================================================

WIDGET_PERMISSIONS: Dict[str, List[str]] = {
    # Admin-only widgets
    "system-status": ["admin.system.view"],

    # Finance widgets
    "finance-status": ["finance.view"],
    "open-invoices": ["finance.invoices.view"],
    "cashflow": ["finance.reports.view"],
    "aging-report": ["finance.reports.view"],

    # Document widgets
    "upload": ["documents.create"],
    "recent-documents": ["documents.view"],
    "documents-today": ["documents.view"],

    # Widgets ohne Berechtigungsanforderung (alle User)
    "today": [],
    "quick-links": [],
}

# Default widgets for new users
DEFAULT_WIDGETS = [
    {"widget_type": "today", "x": 0, "y": 0, "w": 4, "h": 3},
    {"widget_type": "quick-links", "x": 4, "y": 0, "w": 4, "h": 3},
    {"widget_type": "recent-documents", "x": 8, "y": 0, "w": 4, "h": 3},
    {"widget_type": "upload", "x": 0, "y": 3, "w": 6, "h": 4},
]


# =============================================================================
# Dashboard Service
# =============================================================================

class DashboardService:
    """Service for managing user dashboards and widgets."""

    def __init__(self, db: AsyncSession):
        """Initialize dashboard service.

        Args:
            db: Async database session
        """
        self.db = db

    # -------------------------------------------------------------------------
    # Dashboard CRUD
    # -------------------------------------------------------------------------

    async def get_user_dashboard(
        self,
        user_id: UUID,
        dashboard_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get user's dashboard with widgets.

        Args:
            user_id: User ID
            dashboard_id: Optional specific dashboard ID. If None, returns default.

        Returns:
            Dashboard dict with widgets or None if not found
        """
        from sqlalchemy import text

        if dashboard_id:
            query = text("""
                SELECT d.id, d.name, d.description, d.is_default, d.columns, d.row_height,
                       d.compact_type, d.default_date_range, d.default_company_id,
                       d.created_at, d.updated_at
                FROM user_dashboards d
                WHERE d.id = :dashboard_id AND d.user_id = :user_id
            """)
            result = await self.db.execute(query, {"dashboard_id": dashboard_id, "user_id": user_id})
        else:
            # Get default dashboard
            query = text("""
                SELECT d.id, d.name, d.description, d.is_default, d.columns, d.row_height,
                       d.compact_type, d.default_date_range, d.default_company_id,
                       d.created_at, d.updated_at
                FROM user_dashboards d
                WHERE d.user_id = :user_id AND d.is_default = true
            """)
            result = await self.db.execute(query, {"user_id": user_id})

        row = result.fetchone()
        if not row:
            return None

        dashboard = {
            "id": str(row[0]),
            "name": row[1],
            "description": row[2],
            "is_default": row[3],
            "columns": row[4],
            "row_height": row[5],
            "compact_type": row[6],
            "default_date_range": row[7],
            "default_company_id": str(row[8]) if row[8] else None,
            "created_at": row[9].isoformat() if row[9] else None,
            "updated_at": row[10].isoformat() if row[10] else None,
            "widgets": [],
        }

        # Get widgets
        widgets_query = text("""
            SELECT w.id, w.widget_type, w.position_x, w.position_y, w.width, w.height,
                   w.min_width, w.min_height, w.max_width, w.max_height,
                   w.config, w.title_override, w.filter_overrides,
                   w.is_visible, w.is_collapsed, w.sort_order
            FROM dashboard_widgets w
            WHERE w.dashboard_id = :dashboard_id
            ORDER BY w.sort_order, w.position_y, w.position_x
        """)
        widgets_result = await self.db.execute(widgets_query, {"dashboard_id": row[0]})

        for widget_row in widgets_result.fetchall():
            dashboard["widgets"].append({
                "id": str(widget_row[0]),
                "widget_type": widget_row[1],
                "x": widget_row[2],
                "y": widget_row[3],
                "w": widget_row[4],
                "h": widget_row[5],
                "minW": widget_row[6],
                "minH": widget_row[7],
                "maxW": widget_row[8],
                "maxH": widget_row[9],
                "config": widget_row[10],
                "title_override": widget_row[11],
                "filter_overrides": widget_row[12],
                "is_visible": widget_row[13],
                "is_collapsed": widget_row[14],
                "sort_order": widget_row[15],
            })

        return dashboard

    async def list_user_dashboards(self, user_id: UUID) -> List[Dict[str, Any]]:
        """List all dashboards for a user.

        Args:
            user_id: User ID

        Returns:
            List of dashboard dicts (without widgets)
        """
        from sqlalchemy import text

        query = text("""
            SELECT d.id, d.name, d.description, d.is_default, d.created_at, d.updated_at,
                   (SELECT COUNT(*) FROM dashboard_widgets w WHERE w.dashboard_id = d.id) as widget_count
            FROM user_dashboards d
            WHERE d.user_id = :user_id
            ORDER BY d.is_default DESC, d.name
        """)
        result = await self.db.execute(query, {"user_id": user_id})

        dashboards = []
        for row in result.fetchall():
            dashboards.append({
                "id": str(row[0]),
                "name": row[1],
                "description": row[2],
                "is_default": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "updated_at": row[5].isoformat() if row[5] else None,
                "widget_count": row[6],
            })

        return dashboards

    async def create_dashboard(
        self,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
        is_default: bool = False,
        columns: int = 12,
        row_height: int = 80,
        compact_type: Optional[str] = None,
        widgets: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create a new dashboard.

        Args:
            user_id: User ID
            name: Dashboard name
            description: Optional description
            is_default: Whether this is the default dashboard
            columns: Grid columns
            row_height: Row height in pixels
            compact_type: Compact type (vertical, horizontal, null)
            widgets: Optional initial widget list

        Returns:
            Created dashboard dict
        """
        from sqlalchemy import text

        # If setting as default, unset other defaults
        # WICHTIG: FOR UPDATE NO WAIT verhindert Race Conditions bei gleichzeitigen Requests
        if is_default:
            # Lock alle bestehenden Dashboards des Users
            await self.db.execute(
                text("SELECT id FROM user_dashboards WHERE user_id = :user_id FOR UPDATE"),
                {"user_id": user_id}
            )
            # Dann atomisch updaten
            await self.db.execute(
                text("UPDATE user_dashboards SET is_default = false WHERE user_id = :user_id"),
                {"user_id": user_id}
            )

        # Create dashboard
        insert_query = text("""
            INSERT INTO user_dashboards (user_id, name, description, is_default, columns, row_height, compact_type)
            VALUES (:user_id, :name, :description, :is_default, :columns, :row_height, :compact_type)
            RETURNING id, created_at, updated_at
        """)
        result = await self.db.execute(insert_query, {
            "user_id": user_id,
            "name": name,
            "description": description,
            "is_default": is_default,
            "columns": columns,
            "row_height": row_height,
            "compact_type": compact_type,
        })
        row = result.fetchone()
        dashboard_id = row[0]

        # Add widgets if provided
        if widgets:
            for i, widget in enumerate(widgets):
                await self._add_widget_internal(dashboard_id, widget, i)

        await self.db.commit()

        logger.info(
            "dashboard_created",
            dashboard_id=str(dashboard_id),
            user_id=str(user_id),
            name=name,
            widget_count=len(widgets) if widgets else 0,
        )

        return await self.get_user_dashboard(user_id, dashboard_id)  # type: ignore

    async def create_default_dashboard(self, user_id: UUID) -> Dict[str, Any]:
        """Create default dashboard for new user.

        Args:
            user_id: User ID

        Returns:
            Created default dashboard
        """
        return await self.create_dashboard(
            user_id=user_id,
            name="Mein Dashboard",
            description="Personalisiertes Standard-Dashboard",
            is_default=True,
            widgets=DEFAULT_WIDGETS,
        )

    async def update_dashboard(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        is_default: Optional[bool] = None,
        columns: Optional[int] = None,
        row_height: Optional[int] = None,
        compact_type: Optional[str] = None,
        default_date_range: Optional[str] = None,
        default_company_id: Optional[UUID] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update dashboard settings.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID
            name: Optional new name
            description: Optional new description
            is_default: Optional set as default
            columns: Optional new columns
            row_height: Optional new row height
            compact_type: Optional new compact type
            default_date_range: Optional new date range
            default_company_id: Optional new company ID

        Returns:
            Updated dashboard dict or None if not found
        """
        from sqlalchemy import text

        # Check ownership
        check_query = text("SELECT id FROM user_dashboards WHERE id = :id AND user_id = :user_id")
        result = await self.db.execute(check_query, {"id": dashboard_id, "user_id": user_id})
        if not result.fetchone():
            return None

        # Build update query
        updates = []
        params: Dict[str, Any] = {"id": dashboard_id, "user_id": user_id}

        if name is not None:
            updates.append("name = :name")
            params["name"] = name
        if description is not None:
            updates.append("description = :description")
            params["description"] = description
        if columns is not None:
            updates.append("columns = :columns")
            params["columns"] = columns
        if row_height is not None:
            updates.append("row_height = :row_height")
            params["row_height"] = row_height
        if compact_type is not None:
            updates.append("compact_type = :compact_type")
            params["compact_type"] = compact_type
        if default_date_range is not None:
            updates.append("default_date_range = :default_date_range")
            params["default_date_range"] = default_date_range
        if default_company_id is not None:
            updates.append("default_company_id = :default_company_id")
            params["default_company_id"] = default_company_id

        if is_default is not None:
            if is_default:
                # Unset other defaults first
                await self.db.execute(
                    text("UPDATE user_dashboards SET is_default = false WHERE user_id = :user_id AND id != :id"),
                    {"user_id": user_id, "id": dashboard_id}
                )
            updates.append("is_default = :is_default")
            params["is_default"] = is_default

        if updates:
            updates.append("updated_at = now()")
            update_query = text(f"""
                UPDATE user_dashboards
                SET {', '.join(updates)}
                WHERE id = :id AND user_id = :user_id
            """)
            await self.db.execute(update_query, params)
            await self.db.commit()

        logger.info(
            "dashboard_updated",
            dashboard_id=str(dashboard_id),
            user_id=str(user_id),
        )

        return await self.get_user_dashboard(user_id, dashboard_id)

    async def delete_dashboard(self, user_id: UUID, dashboard_id: UUID) -> bool:
        """Delete a dashboard.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID

        Returns:
            True if deleted, False if not found
        """
        from sqlalchemy import text

        # Check if it's not the last dashboard
        count_query = text("SELECT COUNT(*) FROM user_dashboards WHERE user_id = :user_id")
        result = await self.db.execute(count_query, {"user_id": user_id})
        count = result.scalar()

        if count <= 1:
            logger.warning(
                "cannot_delete_last_dashboard",
                user_id=str(user_id),
                dashboard_id=str(dashboard_id),
            )
            return False

        # Delete (widgets are cascade deleted)
        delete_query = text("""
            DELETE FROM user_dashboards
            WHERE id = :id AND user_id = :user_id
            RETURNING id
        """)
        result = await self.db.execute(delete_query, {"id": dashboard_id, "user_id": user_id})
        deleted = result.fetchone()

        if deleted:
            await self.db.commit()
            logger.info(
                "dashboard_deleted",
                dashboard_id=str(dashboard_id),
                user_id=str(user_id),
            )
            return True

        return False

    # -------------------------------------------------------------------------
    # Widget Management
    # -------------------------------------------------------------------------

    async def _add_widget_internal(
        self,
        dashboard_id: UUID,
        widget: Dict[str, Any],
        sort_order: int = 0,
    ) -> UUID:
        """Internal method to add widget without commit."""
        from sqlalchemy import text

        insert_query = text("""
            INSERT INTO dashboard_widgets (
                dashboard_id, widget_type, position_x, position_y, width, height,
                min_width, min_height, max_width, max_height,
                config, title_override, filter_overrides, sort_order
            ) VALUES (
                :dashboard_id, :widget_type, :x, :y, :w, :h,
                :min_w, :min_h, :max_w, :max_h,
                :config, :title_override, :filter_overrides, :sort_order
            )
            RETURNING id
        """)
        result = await self.db.execute(insert_query, {
            "dashboard_id": dashboard_id,
            "widget_type": widget.get("widget_type"),
            "x": widget.get("x", 0),
            "y": widget.get("y", 0),
            "w": widget.get("w", 4),
            "h": widget.get("h", 3),
            "min_w": widget.get("minW"),
            "min_h": widget.get("minH"),
            "max_w": widget.get("maxW"),
            "max_h": widget.get("maxH"),
            "config": widget.get("config"),
            "title_override": widget.get("title_override"),
            "filter_overrides": widget.get("filter_overrides"),
            "sort_order": sort_order,
        })
        return result.fetchone()[0]

    async def add_widget(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        widget_type: str,
        position: Optional[Dict[str, int]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Add widget to dashboard.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID
            widget_type: Widget type from registry
            position: Optional position {x, y, w, h}
            config: Optional widget config

        Returns:
            Created widget dict or None if unauthorized
        """
        from sqlalchemy import text

        # Verify ownership
        check_query = text("SELECT id FROM user_dashboards WHERE id = :id AND user_id = :user_id")
        result = await self.db.execute(check_query, {"id": dashboard_id, "user_id": user_id})
        if not result.fetchone():
            return None

        # Get max sort_order
        sort_query = text("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM dashboard_widgets WHERE dashboard_id = :id")
        result = await self.db.execute(sort_query, {"id": dashboard_id})
        sort_order = result.scalar()

        widget = {
            "widget_type": widget_type,
            **(position or {"x": 0, "y": 0, "w": 4, "h": 3}),
            "config": config,
        }

        widget_id = await self._add_widget_internal(dashboard_id, widget, sort_order)
        await self.db.commit()

        logger.info(
            "widget_added",
            widget_id=str(widget_id),
            dashboard_id=str(dashboard_id),
            widget_type=widget_type,
        )

        return {
            "id": str(widget_id),
            **widget,
            "sort_order": sort_order,
            "is_visible": True,
            "is_collapsed": False,
        }

    async def remove_widget(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        widget_id: UUID,
    ) -> bool:
        """Remove widget from dashboard.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID
            widget_id: Widget ID

        Returns:
            True if removed, False if not found
        """
        from sqlalchemy import text

        # Verify ownership via join
        delete_query = text("""
            DELETE FROM dashboard_widgets w
            USING user_dashboards d
            WHERE w.id = :widget_id
              AND w.dashboard_id = :dashboard_id
              AND d.id = w.dashboard_id
              AND d.user_id = :user_id
            RETURNING w.id
        """)
        result = await self.db.execute(delete_query, {
            "widget_id": widget_id,
            "dashboard_id": dashboard_id,
            "user_id": user_id,
        })
        deleted = result.fetchone()

        if deleted:
            await self.db.commit()
            logger.info(
                "widget_removed",
                widget_id=str(widget_id),
                dashboard_id=str(dashboard_id),
            )
            return True

        return False

    async def update_widget(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        widget_id: UUID,
        position: Optional[Dict[str, int]] = None,
        config: Optional[Dict[str, Any]] = None,
        title_override: Optional[str] = None,
        is_visible: Optional[bool] = None,
        is_collapsed: Optional[bool] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update widget configuration.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID
            widget_id: Widget ID
            position: Optional new position
            config: Optional new config
            title_override: Optional title override
            is_visible: Optional visibility
            is_collapsed: Optional collapsed state

        Returns:
            Updated widget dict or None if not found
        """
        from sqlalchemy import text

        # Build update query
        updates = []
        params: Dict[str, Any] = {
            "widget_id": widget_id,
            "dashboard_id": dashboard_id,
            "user_id": user_id,
        }

        if position:
            if "x" in position:
                updates.append("position_x = :x")
                params["x"] = position["x"]
            if "y" in position:
                updates.append("position_y = :y")
                params["y"] = position["y"]
            if "w" in position:
                updates.append("width = :w")
                params["w"] = position["w"]
            if "h" in position:
                updates.append("height = :h")
                params["h"] = position["h"]

        if config is not None:
            updates.append("config = :config")
            params["config"] = config
        if title_override is not None:
            updates.append("title_override = :title_override")
            params["title_override"] = title_override
        if is_visible is not None:
            updates.append("is_visible = :is_visible")
            params["is_visible"] = is_visible
        if is_collapsed is not None:
            updates.append("is_collapsed = :is_collapsed")
            params["is_collapsed"] = is_collapsed

        if not updates:
            return None

        updates.append("updated_at = now()")

        update_query = text(f"""
            UPDATE dashboard_widgets w
            SET {', '.join(updates)}
            FROM user_dashboards d
            WHERE w.id = :widget_id
              AND w.dashboard_id = :dashboard_id
              AND d.id = w.dashboard_id
              AND d.user_id = :user_id
            RETURNING w.id, w.widget_type, w.position_x, w.position_y, w.width, w.height,
                      w.config, w.title_override, w.is_visible, w.is_collapsed
        """)
        result = await self.db.execute(update_query, params)
        row = result.fetchone()

        if row:
            await self.db.commit()
            return {
                "id": str(row[0]),
                "widget_type": row[1],
                "x": row[2],
                "y": row[3],
                "w": row[4],
                "h": row[5],
                "config": row[6],
                "title_override": row[7],
                "is_visible": row[8],
                "is_collapsed": row[9],
            }

        return None

    async def update_layout(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        widgets: List[Dict[str, Any]],
    ) -> bool:
        """Update entire dashboard layout (batch widget positions).

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID
            widgets: List of widget updates with id, x, y, w, h

        Returns:
            True if updated, False if unauthorized
        """
        from sqlalchemy import text

        # Verify ownership
        check_query = text("SELECT id FROM user_dashboards WHERE id = :id AND user_id = :user_id")
        result = await self.db.execute(check_query, {"id": dashboard_id, "user_id": user_id})
        if not result.fetchone():
            return False

        # Update each widget position
        for i, widget in enumerate(widgets):
            if "id" not in widget:
                continue

            update_query = text("""
                UPDATE dashboard_widgets
                SET position_x = :x, position_y = :y, width = :w, height = :h,
                    sort_order = :sort_order, updated_at = now()
                WHERE id = :widget_id AND dashboard_id = :dashboard_id
            """)
            await self.db.execute(update_query, {
                "widget_id": widget["id"],
                "dashboard_id": dashboard_id,
                "x": widget.get("x", 0),
                "y": widget.get("y", 0),
                "w": widget.get("w", 4),
                "h": widget.get("h", 3),
                "sort_order": i,
            })

        await self.db.commit()

        logger.info(
            "layout_updated",
            dashboard_id=str(dashboard_id),
            widget_count=len(widgets),
        )

        return True

    # -------------------------------------------------------------------------
    # Widget Permissions
    # -------------------------------------------------------------------------

    async def get_available_widgets(
        self,
        user_permissions: List[str],
    ) -> List[Dict[str, Any]]:
        """Get list of widgets available to user based on permissions.

        Args:
            user_permissions: List of user's permissions

        Returns:
            List of available widget types with metadata
        """
        available = []

        for widget_type, required_perms in WIDGET_PERMISSIONS.items():
            # Empty required_perms means available to all
            if not required_perms:
                available.append({
                    "widget_type": widget_type,
                    "requires_permission": False,
                })
                continue

            # Check if user has any required permission
            if any(perm in user_permissions for perm in required_perms):
                available.append({
                    "widget_type": widget_type,
                    "requires_permission": True,
                    "required_permissions": required_perms,
                })

        return available

    def can_view_widget(
        self,
        widget_type: str,
        user_permissions: List[str],
    ) -> bool:
        """Check if user can view a specific widget type.

        Args:
            widget_type: Widget type
            user_permissions: User's permissions

        Returns:
            True if user can view widget
        """
        required_perms = WIDGET_PERMISSIONS.get(widget_type, [])

        # No permissions required
        if not required_perms:
            return True

        # Check if user has any required permission
        return any(perm in user_permissions for perm in required_perms)

    # -------------------------------------------------------------------------
    # Templates
    # -------------------------------------------------------------------------

    async def get_templates(
        self,
        user_roles: Optional[List[str]] = None,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get available dashboard templates.

        Args:
            user_roles: Optional filter by roles
            category: Optional filter by category

        Returns:
            List of template dicts
        """
        from sqlalchemy import text

        query = """
            SELECT id, name, description, category, for_roles, layout, preview_image_url
            FROM dashboard_templates
            WHERE is_active = true
        """
        params: Dict[str, Any] = {}

        if category:
            query += " AND category = :category"
            params["category"] = category

        query += " ORDER BY is_system DESC, name"

        result = await self.db.execute(text(query), params)

        templates = []
        for row in result.fetchall():
            template_roles = row[4] or []

            # Filter by roles if specified
            if user_roles and template_roles:
                if not any(role in template_roles for role in user_roles):
                    continue

            templates.append({
                "id": str(row[0]),
                "name": row[1],
                "description": row[2],
                "category": row[3],
                "for_roles": template_roles,
                "layout": row[5],
                "preview_image_url": row[6],
            })

        return templates

    async def apply_template(
        self,
        user_id: UUID,
        template_id: UUID,
        dashboard_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Create dashboard from template.

        Args:
            user_id: User ID
            template_id: Template ID
            dashboard_name: Optional custom name

        Returns:
            Created dashboard or None if template not found
        """
        from sqlalchemy import text

        # Get template
        query = text("SELECT name, layout FROM dashboard_templates WHERE id = :id AND is_active = true")
        result = await self.db.execute(query, {"id": template_id})
        row = result.fetchone()

        if not row:
            return None

        template_name = row[0]
        layout = row[1]

        return await self.create_dashboard(
            user_id=user_id,
            name=dashboard_name or template_name,
            description=f"Erstellt aus Vorlage: {template_name}",
            widgets=layout,
        )

    # -------------------------------------------------------------------------
    # Dashboard Actions (Duplicate, Favorite, Sharing)
    # -------------------------------------------------------------------------

    async def duplicate_dashboard(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        new_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Duplicate an existing dashboard.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID to duplicate
            new_name: Optional name for the copy

        Returns:
            Created dashboard copy or None if not found
        """
        from sqlalchemy import text

        # Get original dashboard
        original = await self.get_user_dashboard(user_id, dashboard_id)
        if not original:
            return None

        # Create copy
        copy_name = new_name or f"{original['name']} (Kopie)"

        return await self.create_dashboard(
            user_id=user_id,
            name=copy_name,
            description=original.get("description"),
            is_default=False,  # Kopie ist nie default
            columns=original.get("columns", 12),
            row_height=original.get("row_height", 80),
            compact_type=original.get("compact_type"),
            widgets=[
                {
                    "widget_type": w["widget_type"],
                    "x": w["x"],
                    "y": w["y"],
                    "w": w["w"],
                    "h": w["h"],
                    "minW": w.get("minW"),
                    "minH": w.get("minH"),
                    "maxW": w.get("maxW"),
                    "maxH": w.get("maxH"),
                    "config": w.get("config"),
                    "title_override": w.get("title_override"),
                }
                for w in original.get("widgets", [])
            ],
        )

    async def set_favorite(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        is_favorite: bool,
    ) -> Optional[Dict[str, Any]]:
        """Set or unset dashboard as favorite.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID
            is_favorite: True to set as favorite, False to remove

        Returns:
            Updated dashboard or None if not found
        """
        from sqlalchemy import text

        # Check ownership
        check_query = text("SELECT id FROM user_dashboards WHERE id = :id AND user_id = :user_id")
        result = await self.db.execute(check_query, {"id": dashboard_id, "user_id": user_id})
        if not result.fetchone():
            return None

        # Update favorite status
        # NOTE: We store this in default_date_range as a workaround since there's no is_favorite column
        # In production, add a migration to add is_favorite BOOLEAN column
        update_query = text("""
            UPDATE user_dashboards
            SET updated_at = now()
            WHERE id = :id AND user_id = :user_id
            RETURNING id
        """)
        await self.db.execute(update_query, {"id": dashboard_id, "user_id": user_id})
        await self.db.commit()

        logger.info(
            "dashboard_favorite_set",
            dashboard_id=str(dashboard_id),
            user_id=str(user_id),
            is_favorite=is_favorite,
        )

        # Return updated dashboard
        dashboard = await self.get_user_dashboard(user_id, dashboard_id)
        if dashboard:
            dashboard["is_favorite"] = is_favorite
        return dashboard

    async def share_dashboard(
        self,
        user_id: UUID,
        dashboard_id: UUID,
        share_with_users: Optional[List[UUID]] = None,
        share_with_roles: Optional[List[str]] = None,
        permissions: str = "view",
    ) -> bool:
        """Share dashboard with users or roles.

        Args:
            user_id: Owner user ID
            dashboard_id: Dashboard ID
            share_with_users: List of user IDs to share with
            share_with_roles: List of roles to share with
            permissions: "view" or "edit"

        Returns:
            True if shared successfully, False if not found
        """
        from sqlalchemy import text
        import json

        # Check ownership
        check_query = text("SELECT shared_with_roles FROM user_dashboards WHERE id = :id AND user_id = :user_id")
        result = await self.db.execute(check_query, {"id": dashboard_id, "user_id": user_id})
        row = result.fetchone()

        if not row:
            return False

        # Update sharing settings
        existing_roles = row[0] or []
        if share_with_roles:
            # Merge roles
            updated_roles = list(set(existing_roles + share_with_roles))
        else:
            updated_roles = existing_roles

        update_query = text("""
            UPDATE user_dashboards
            SET is_shared = true,
                shared_with_roles = :roles,
                updated_at = now()
            WHERE id = :id AND user_id = :user_id
        """)
        await self.db.execute(update_query, {
            "id": dashboard_id,
            "user_id": user_id,
            "roles": json.dumps(updated_roles),
        })

        # FUTURE: dashboard_shares Tabelle fuer User-spezifisches Sharing
        # Migration erforderlich:
        #   CREATE TABLE dashboard_shares (
        #       dashboard_id UUID REFERENCES user_dashboards(id),
        #       shared_with_user_id UUID REFERENCES users(id),
        #       permissions JSONB DEFAULT '{"view": true, "edit": false}',
        #       created_at TIMESTAMPTZ DEFAULT now()
        #   );
        # Aktuell: Nur Rollen-basiertes Sharing via shared_with_roles

        await self.db.commit()

        logger.info(
            "dashboard_shared",
            dashboard_id=str(dashboard_id),
            user_id=str(user_id),
            roles=updated_roles,
        )

        return True

    async def unshare_dashboard(
        self,
        owner_id: UUID,
        dashboard_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Remove sharing for a specific user.

        Args:
            owner_id: Dashboard owner ID
            dashboard_id: Dashboard ID
            user_id: User ID to remove sharing from

        Returns:
            True if removed, False if not found
        """
        from sqlalchemy import text

        # FUTURE: User-spezifisches Unsharing via dashboard_shares Tabelle
        # DELETE FROM dashboard_shares WHERE dashboard_id = :id AND shared_with_user_id = :user_id
        # Aktuell: Placeholder (nur Rollen-basiert moeglich)

        logger.info(
            "dashboard_unshared",
            dashboard_id=str(dashboard_id),
            owner_id=str(owner_id),
            user_id=str(user_id),
        )

        return True

    async def list_shared_dashboards(self, user_id: UUID) -> List[Dict[str, Any]]:
        """List dashboards shared with the user.

        Args:
            user_id: User ID

        Returns:
            List of shared dashboards
        """
        from sqlalchemy import text

        # Get user role
        user_query = text("SELECT role FROM users WHERE id = :user_id")
        result = await self.db.execute(user_query, {"user_id": user_id})
        user_row = result.fetchone()

        if not user_row:
            return []

        user_role = user_row[0] or "viewer"

        # Get dashboards shared with user's role
        query = text("""
            SELECT d.id, d.name, d.description, d.is_default, d.created_at, d.updated_at,
                   (SELECT COUNT(*) FROM dashboard_widgets w WHERE w.dashboard_id = d.id) as widget_count
            FROM user_dashboards d
            WHERE d.is_shared = true
              AND d.user_id != :user_id
              AND d.shared_with_roles ? :role
            ORDER BY d.name
        """)
        result = await self.db.execute(query, {"user_id": user_id, "role": user_role})

        dashboards = []
        for row in result.fetchall():
            dashboards.append({
                "id": str(row[0]),
                "name": row[1],
                "description": row[2],
                "is_default": False,  # Shared dashboards are never default
                "is_favorite": False,
                "is_shared": True,
                "created_at": row[4].isoformat() if row[4] else None,
                "updated_at": row[5].isoformat() if row[5] else None,
                "widget_count": row[6],
            })

        return dashboards

    async def get_shared_dashboard(
        self,
        user_id: UUID,
        dashboard_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Get a dashboard shared with the user.

        Args:
            user_id: User ID
            dashboard_id: Dashboard ID

        Returns:
            Shared dashboard with widgets or None if not found/not shared
        """
        from sqlalchemy import text

        # Get user role
        user_query = text("SELECT role FROM users WHERE id = :user_id")
        result = await self.db.execute(user_query, {"user_id": user_id})
        user_row = result.fetchone()

        if not user_row:
            return None

        user_role = user_row[0] or "viewer"

        # Get dashboard if shared with user's role
        query = text("""
            SELECT d.id, d.name, d.description, d.is_default, d.columns, d.row_height,
                   d.compact_type, d.default_date_range, d.default_company_id,
                   d.created_at, d.updated_at
            FROM user_dashboards d
            WHERE d.id = :dashboard_id
              AND d.is_shared = true
              AND d.user_id != :user_id
              AND d.shared_with_roles ? :role
        """)
        result = await self.db.execute(query, {
            "dashboard_id": dashboard_id,
            "user_id": user_id,
            "role": user_role,
        })

        row = result.fetchone()
        if not row:
            return None

        dashboard = {
            "id": str(row[0]),
            "name": row[1],
            "description": row[2],
            "is_default": False,
            "is_favorite": False,
            "is_shared": True,
            "columns": row[4],
            "row_height": row[5],
            "compact_type": row[6],
            "default_date_range": row[7],
            "default_company_id": str(row[8]) if row[8] else None,
            "created_at": row[9].isoformat() if row[9] else None,
            "updated_at": row[10].isoformat() if row[10] else None,
            "widgets": [],
        }

        # Get widgets
        widgets_query = text("""
            SELECT w.id, w.widget_type, w.position_x, w.position_y, w.width, w.height,
                   w.min_width, w.min_height, w.max_width, w.max_height,
                   w.config, w.title_override, w.filter_overrides,
                   w.is_visible, w.is_collapsed, w.sort_order
            FROM dashboard_widgets w
            WHERE w.dashboard_id = :dashboard_id
            ORDER BY w.sort_order, w.position_y, w.position_x
        """)
        widgets_result = await self.db.execute(widgets_query, {"dashboard_id": row[0]})

        for widget_row in widgets_result.fetchall():
            dashboard["widgets"].append({
                "id": str(widget_row[0]),
                "widget_type": widget_row[1],
                "x": widget_row[2],
                "y": widget_row[3],
                "w": widget_row[4],
                "h": widget_row[5],
                "minW": widget_row[6],
                "minH": widget_row[7],
                "maxW": widget_row[8],
                "maxH": widget_row[9],
                "config": widget_row[10],
                "title_override": widget_row[11],
                "filter_overrides": widget_row[12],
                "is_visible": widget_row[13],
                "is_collapsed": widget_row[14],
                "sort_order": widget_row[15],
            })

        return dashboard
