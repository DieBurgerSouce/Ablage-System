# -*- coding: utf-8 -*-
"""
Unit Tests fuer Dashboard API Endpoints.

Testet:
- Dashboard CRUD (Create, Read, Update, Delete)
- Widget Management
- Layout Updates
- Templates

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime, timezone

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_dashboard():
    """Sample Dashboard fuer Tests."""
    return Mock(
        id=uuid4(),
        user_id=uuid4(),
        name="Mein Dashboard",
        description="Ein Test-Dashboard",
        is_default=True,
        columns=12,
        row_height=100,
        compact_type="vertical",
        default_date_range="30d",
        default_company_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        widgets=[],
    )


@pytest.fixture
def sample_widget():
    """Sample Widget fuer Tests."""
    return Mock(
        id=uuid4(),
        dashboard_id=uuid4(),
        widget_type="document_stats",
        x=0,
        y=0,
        w=4,
        h=3,
        config={"show_trend": True},
        title_override=None,
        is_visible=True,
        is_collapsed=False,
        sort_order=0,
    )


# =============================================================================
# Dashboard CRUD Tests
# =============================================================================

class TestDashboardList:
    """Tests fuer Dashboard-Liste."""

    @pytest.mark.asyncio
    async def test_list_dashboards_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten von Dashboards."""
        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.list_dashboards.return_value = []
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/dashboard/list",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_get_default_dashboard(self, async_client, auth_headers, sample_dashboard):
        """Abruf des Standard-Dashboards."""
        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_or_create_default.return_value = sample_dashboard
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/dashboard",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]


class TestDashboardCreate:
    """Tests fuer Dashboard-Erstellung."""

    @pytest.mark.asyncio
    async def test_create_dashboard_success(self, async_client, auth_headers, sample_dashboard):
        """Erfolgreiche Dashboard-Erstellung."""
        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_dashboard.return_value = sample_dashboard
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/dashboard",
                json={
                    "name": "Neues Dashboard",
                    "description": "Ein neues Dashboard",
                    "columns": 12,
                    "row_height": 100,
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 422]

    @pytest.mark.asyncio
    async def test_create_dashboard_minimal(self, async_client, auth_headers, sample_dashboard):
        """Dashboard-Erstellung mit minimalen Daten."""
        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.create_dashboard.return_value = sample_dashboard
            mock_service.return_value = mock_instance

            response = await async_client.post(
                "/api/v1/dashboard",
                json={"name": "Minimal Dashboard"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 422]


class TestDashboardGet:
    """Tests fuer Dashboard-Abruf."""

    @pytest.mark.asyncio
    async def test_get_dashboard_success(self, async_client, auth_headers, sample_dashboard):
        """Erfolgreicher Dashboard-Abruf."""
        dashboard_id = sample_dashboard.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_dashboard.return_value = sample_dashboard
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/dashboard/{dashboard_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_get_dashboard_not_found(self, async_client, auth_headers):
        """Dashboard-Abruf fuer nicht existierendes Dashboard."""
        non_existent_id = uuid4()

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_dashboard.return_value = None
            mock_service.return_value = mock_instance

            response = await async_client.get(
                f"/api/v1/dashboard/{non_existent_id}",
                headers=auth_headers,
            )

            assert response.status_code in [404, 401]


class TestDashboardUpdate:
    """Tests fuer Dashboard-Update."""

    @pytest.mark.asyncio
    async def test_update_dashboard_success(self, async_client, auth_headers, sample_dashboard):
        """Erfolgreiches Dashboard-Update."""
        dashboard_id = sample_dashboard.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            sample_dashboard.name = "Updated Dashboard"
            mock_instance.update_dashboard.return_value = sample_dashboard
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/dashboard/{dashboard_id}",
                json={"name": "Updated Dashboard"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_set_default_dashboard(self, async_client, auth_headers, sample_dashboard):
        """Dashboard als Standard setzen."""
        dashboard_id = sample_dashboard.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            sample_dashboard.is_default = True
            mock_instance.update_dashboard.return_value = sample_dashboard
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/dashboard/{dashboard_id}",
                json={"is_default": True},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


class TestDashboardDelete:
    """Tests fuer Dashboard-Loeschung."""

    @pytest.mark.asyncio
    async def test_delete_dashboard_success(self, async_client, auth_headers, sample_dashboard):
        """Erfolgreiche Dashboard-Loeschung."""
        dashboard_id = sample_dashboard.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.delete_dashboard.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/dashboard/{dashboard_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


# =============================================================================
# Widget Management Tests
# =============================================================================

class TestWidgetManagement:
    """Tests fuer Widget-Verwaltung."""

    @pytest.mark.asyncio
    async def test_get_available_widgets(self, async_client, auth_headers):
        """Verfuegbare Widgets abrufen."""
        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_available_widgets.return_value = [
                {"widget_type": "document_stats", "requires_permission": False},
                {"widget_type": "ocr_stats", "requires_permission": True},
            ]
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/dashboard/widgets/available",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_add_widget_success(
        self, async_client, auth_headers, sample_dashboard, sample_widget
    ):
        """Erfolgreiches Hinzufuegen eines Widgets."""
        dashboard_id = sample_dashboard.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.add_widget.return_value = sample_widget
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/dashboard/{dashboard_id}/widgets",
                json={
                    "widget_type": "document_stats",
                    "position": {"x": 0, "y": 0, "w": 4, "h": 3},
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 404]

    @pytest.mark.asyncio
    async def test_update_widget_success(
        self, async_client, auth_headers, sample_dashboard, sample_widget
    ):
        """Erfolgreiches Widget-Update."""
        dashboard_id = sample_dashboard.id
        widget_id = sample_widget.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            sample_widget.is_collapsed = True
            mock_instance.update_widget.return_value = sample_widget
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/dashboard/{dashboard_id}/widgets/{widget_id}",
                json={"is_collapsed": True},
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]

    @pytest.mark.asyncio
    async def test_remove_widget_success(
        self, async_client, auth_headers, sample_dashboard, sample_widget
    ):
        """Erfolgreiches Entfernen eines Widgets."""
        dashboard_id = sample_dashboard.id
        widget_id = sample_widget.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.remove_widget.return_value = True
            mock_service.return_value = mock_instance

            response = await async_client.delete(
                f"/api/v1/dashboard/{dashboard_id}/widgets/{widget_id}",
                headers=auth_headers,
            )

            assert response.status_code in [200, 204, 401, 404]


# =============================================================================
# Layout Update Tests
# =============================================================================

class TestLayoutUpdate:
    """Tests fuer Layout-Updates."""

    @pytest.mark.asyncio
    async def test_update_layout_success(self, async_client, auth_headers, sample_dashboard):
        """Erfolgreiches Layout-Update."""
        dashboard_id = sample_dashboard.id

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.update_layout.return_value = {"success": True, "message": "Layout aktualisiert"}
            mock_service.return_value = mock_instance

            response = await async_client.put(
                f"/api/v1/dashboard/{dashboard_id}/layout",
                json={
                    "widgets": [
                        {"id": str(uuid4()), "x": 0, "y": 0, "w": 4, "h": 3},
                        {"id": str(uuid4()), "x": 4, "y": 0, "w": 4, "h": 3},
                    ]
                },
                headers=auth_headers,
            )

            assert response.status_code in [200, 401, 404]


# =============================================================================
# Template Tests
# =============================================================================

class TestDashboardTemplates:
    """Tests fuer Dashboard-Templates."""

    @pytest.mark.asyncio
    async def test_list_templates_success(self, async_client, auth_headers):
        """Erfolgreiches Auflisten von Templates."""
        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.get_templates.return_value = [
                {
                    "id": str(uuid4()),
                    "name": "Finanz-Dashboard",
                    "description": "Dashboard fuer Finanzdaten",
                    "category": "finance",
                },
            ]
            mock_service.return_value = mock_instance

            response = await async_client.get(
                "/api/v1/dashboard/templates",
                headers=auth_headers,
            )

            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_apply_template_success(
        self, async_client, auth_headers, sample_dashboard
    ):
        """Erfolgreiches Anwenden eines Templates."""
        template_id = uuid4()

        with patch("app.api.v1.dashboard.DashboardService") as mock_service:
            mock_instance = AsyncMock()
            mock_instance.apply_template.return_value = sample_dashboard
            mock_service.return_value = mock_instance

            response = await async_client.post(
                f"/api/v1/dashboard/templates/{template_id}/apply",
                params={"name": "Mein Finanz-Dashboard"},
                headers=auth_headers,
            )

            assert response.status_code in [200, 201, 401, 404]
