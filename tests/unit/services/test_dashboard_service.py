"""Unit Tests for Dashboard Service.

Tests fuer Dashboard-CRUD, Widget-Management und Permissions.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.dashboard_service import (
    DashboardService,
    WIDGET_PERMISSIONS,
    DEFAULT_WIDGETS,
    WidgetPosition,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock async database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def dashboard_service(mock_db):
    """Create a dashboard service instance with mock db."""
    return DashboardService(mock_db)


@pytest.fixture
def sample_user_id():
    """Sample user UUID."""
    return uuid4()


@pytest.fixture
def sample_dashboard_id():
    """Sample dashboard UUID."""
    return uuid4()


# =============================================================================
# Widget Position Tests
# =============================================================================


class TestWidgetPosition:
    """Tests for WidgetPosition class."""

    def test_default_values(self):
        """Test default position values."""
        pos = WidgetPosition()
        assert pos.x == 0
        assert pos.y == 0
        assert pos.w == 4
        assert pos.h == 3
        assert pos.min_w is None
        assert pos.max_w is None

    def test_custom_values(self):
        """Test custom position values."""
        pos = WidgetPosition(x=2, y=3, w=6, h=4, min_w=2, max_w=12)
        assert pos.x == 2
        assert pos.y == 3
        assert pos.w == 6
        assert pos.h == 4
        assert pos.min_w == 2
        assert pos.max_w == 12

    def test_to_dict(self):
        """Test conversion to dictionary."""
        pos = WidgetPosition(x=1, y=2, w=3, h=4)
        result = pos.to_dict()

        assert result["x"] == 1
        assert result["y"] == 2
        assert result["w"] == 3
        assert result["h"] == 4
        assert "minW" in result
        assert "maxW" in result

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {"x": 5, "y": 6, "w": 8, "h": 2, "minW": 4}
        pos = WidgetPosition.from_dict(data)

        assert pos.x == 5
        assert pos.y == 6
        assert pos.w == 8
        assert pos.h == 2
        assert pos.min_w == 4


# =============================================================================
# Widget Permissions Tests
# =============================================================================


class TestWidgetPermissions:
    """Tests for widget permission mapping."""

    def test_admin_widgets_require_permission(self):
        """Test that admin widgets require permissions."""
        assert "admin.system.view" in WIDGET_PERMISSIONS["system-status"]

    def test_finance_widgets_require_permission(self):
        """Test that finance widgets require permissions."""
        assert "finance.view" in WIDGET_PERMISSIONS["finance-status"]
        assert "finance.invoices.view" in WIDGET_PERMISSIONS["open-invoices"]
        assert "finance.reports.view" in WIDGET_PERMISSIONS["cashflow"]
        assert "finance.reports.view" in WIDGET_PERMISSIONS["aging-report"]

    def test_document_widgets_require_permission(self):
        """Test that document widgets require permissions."""
        assert "documents.create" in WIDGET_PERMISSIONS["upload"]
        assert "documents.view" in WIDGET_PERMISSIONS["recent-documents"]

    def test_public_widgets_no_permission(self):
        """Test that public widgets require no permissions."""
        assert WIDGET_PERMISSIONS["today"] == []
        assert WIDGET_PERMISSIONS["quick-links"] == []


class TestCanViewWidget:
    """Tests for can_view_widget method."""

    def test_can_view_public_widget(self, dashboard_service):
        """Test viewing public widgets."""
        assert dashboard_service.can_view_widget("today", []) is True
        assert dashboard_service.can_view_widget("quick-links", []) is True

    def test_can_view_with_permission(self, dashboard_service):
        """Test viewing widgets with required permission."""
        assert dashboard_service.can_view_widget(
            "system-status", ["admin.system.view"]
        ) is True
        assert dashboard_service.can_view_widget(
            "finance-status", ["finance.view"]
        ) is True

    def test_cannot_view_without_permission(self, dashboard_service):
        """Test that widgets are hidden without permission."""
        assert dashboard_service.can_view_widget("system-status", []) is False
        assert dashboard_service.can_view_widget(
            "system-status", ["documents.view"]
        ) is False

    def test_unknown_widget_allowed(self, dashboard_service):
        """Test that unknown widgets are allowed by default."""
        assert dashboard_service.can_view_widget("unknown-widget", []) is True


class TestGetAvailableWidgets:
    """Tests for get_available_widgets method."""

    @pytest.mark.asyncio
    async def test_admin_sees_all_widgets(self, dashboard_service):
        """Test that admin sees all widgets."""
        admin_perms = [
            "admin.system.view",
            "finance.view",
            "finance.invoices.view",
            "finance.reports.view",
            "documents.view",
            "documents.create",
        ]

        widgets = await dashboard_service.get_available_widgets(admin_perms)

        widget_types = [w["widget_type"] for w in widgets]
        assert "system-status" in widget_types
        assert "finance-status" in widget_types
        assert "today" in widget_types
        assert "upload" in widget_types

    @pytest.mark.asyncio
    async def test_viewer_sees_limited_widgets(self, dashboard_service):
        """Test that viewer sees limited widgets."""
        viewer_perms = ["documents.view"]

        widgets = await dashboard_service.get_available_widgets(viewer_perms)

        widget_types = [w["widget_type"] for w in widgets]
        assert "today" in widget_types  # Public
        assert "quick-links" in widget_types  # Public
        assert "recent-documents" in widget_types  # Has permission
        assert "system-status" not in widget_types  # No admin permission
        assert "finance-status" not in widget_types  # No finance permission

    @pytest.mark.asyncio
    async def test_public_widgets_always_included(self, dashboard_service):
        """Test that public widgets are always included."""
        widgets = await dashboard_service.get_available_widgets([])

        widget_types = [w["widget_type"] for w in widgets]
        assert "today" in widget_types
        assert "quick-links" in widget_types


# =============================================================================
# Default Widgets Tests
# =============================================================================


class TestDefaultWidgets:
    """Tests for default widget configuration."""

    def test_default_widgets_defined(self):
        """Test that default widgets are defined."""
        assert len(DEFAULT_WIDGETS) > 0

    def test_default_widgets_have_required_fields(self):
        """Test that default widgets have required fields."""
        for widget in DEFAULT_WIDGETS:
            assert "widget_type" in widget
            assert "x" in widget
            assert "y" in widget
            assert "w" in widget
            assert "h" in widget

    def test_default_widgets_have_valid_types(self):
        """Test that default widget types are valid."""
        valid_types = set(WIDGET_PERMISSIONS.keys())
        for widget in DEFAULT_WIDGETS:
            assert widget["widget_type"] in valid_types


# =============================================================================
# Dashboard CRUD Mock Tests
# =============================================================================


class TestDashboardCRUD:
    """Tests for dashboard CRUD operations."""

    @pytest.mark.asyncio
    async def test_get_user_dashboard_not_found(
        self, dashboard_service, mock_db, sample_user_id
    ):
        """Test getting non-existent dashboard returns None."""
        # Mock empty result
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await dashboard_service.get_user_dashboard(sample_user_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_list_user_dashboards_empty(
        self, dashboard_service, mock_db, sample_user_id
    ):
        """Test listing dashboards for user with none."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result

        result = await dashboard_service.list_user_dashboards(sample_user_id)

        assert result == []

    @pytest.mark.asyncio
    async def test_delete_last_dashboard_fails(
        self, dashboard_service, mock_db, sample_user_id, sample_dashboard_id
    ):
        """Test that deleting the last dashboard fails."""
        # Mock count = 1 (only one dashboard)
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_db.execute.return_value = mock_result

        result = await dashboard_service.delete_dashboard(
            sample_user_id, sample_dashboard_id
        )

        assert result is False


# =============================================================================
# Layout Update Tests
# =============================================================================


class TestLayoutUpdate:
    """Tests for layout update operations."""

    @pytest.mark.asyncio
    async def test_update_layout_unauthorized(
        self, dashboard_service, mock_db, sample_user_id, sample_dashboard_id
    ):
        """Test updating layout for non-owned dashboard fails."""
        # Mock ownership check fails
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await dashboard_service.update_layout(
            sample_user_id,
            sample_dashboard_id,
            [{"id": str(uuid4()), "x": 0, "y": 0, "w": 4, "h": 3}],
        )

        assert result is False


# =============================================================================
# Widget Management Tests
# =============================================================================


class TestWidgetManagement:
    """Tests for widget management operations."""

    @pytest.mark.asyncio
    async def test_add_widget_unauthorized(
        self, dashboard_service, mock_db, sample_user_id, sample_dashboard_id
    ):
        """Test adding widget to non-owned dashboard fails."""
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await dashboard_service.add_widget(
            sample_user_id,
            sample_dashboard_id,
            "today",
            {"x": 0, "y": 0, "w": 4, "h": 3},
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_remove_widget_not_found(
        self, dashboard_service, mock_db, sample_user_id, sample_dashboard_id
    ):
        """Test removing non-existent widget."""
        widget_id = uuid4()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_db.execute.return_value = mock_result

        result = await dashboard_service.remove_widget(
            sample_user_id, sample_dashboard_id, widget_id
        )

        assert result is False
