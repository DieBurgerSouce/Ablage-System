"""
Tests für Personalized Dashboards API.

Testet:
- Dashboard CRUD
- Widget Management
- Layout Persistence
- Dashboard Sharing
- Favoriten-System
- Preset/Template System
"""

import pytest
from uuid import uuid4
from httpx import AsyncClient


@pytest.mark.asyncio
class TestDashboardCRUD:
    """Tests für Dashboard CRUD Operations."""

    async def test_list_dashboards_empty(self, client: AsyncClient, auth_headers: dict):
        """Leere Dashboard-Liste beim ersten Zugriff."""
        response = await client.get("/api/v1/dashboards", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_create_dashboard(self, client: AsyncClient, auth_headers: dict):
        """Dashboard erstellen."""
        payload = {
            "name": "Test Dashboard",
            "description": "Test-Beschreibung",
            "is_default": True,
            "columns": 12,
            "row_height": 80,
        }

        response = await client.post("/api/v1/dashboards", json=payload, headers=auth_headers)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Dashboard"
        assert data["is_default"] is True
        assert data["columns"] == 12
        assert "id" in data

    async def test_get_dashboard(self, client: AsyncClient, auth_headers: dict):
        """Dashboard abrufen."""
        # Erstelle zuerst ein Dashboard
        create_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Test Dashboard"},
            headers=auth_headers,
        )
        dashboard_id = create_response.json()["id"]

        # Abrufen
        response = await client.get(f"/api/v1/dashboards/{dashboard_id}", headers=auth_headers)
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == dashboard_id
        assert data["name"] == "Test Dashboard"
        assert "widgets" in data

    async def test_update_dashboard(self, client: AsyncClient, auth_headers: dict):
        """Dashboard aktualisieren."""
        # Erstellen
        create_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Original Name"},
            headers=auth_headers,
        )
        dashboard_id = create_response.json()["id"]

        # Aktualisieren
        update_payload = {"name": "Updated Name", "description": "New Description"}
        response = await client.patch(
            f"/api/v1/dashboards/{dashboard_id}",
            json=update_payload,
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "New Description"

    async def test_delete_dashboard(self, client: AsyncClient, auth_headers: dict):
        """Dashboard löschen."""
        # Erstelle zwei Dashboards (mindestens eins muss bleiben)
        await client.post("/api/v1/dashboards", json={"name": "Dashboard 1"}, headers=auth_headers)
        create_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Dashboard 2"},
            headers=auth_headers,
        )
        dashboard_id = create_response.json()["id"]

        # Lösche zweites Dashboard
        response = await client.delete(f"/api/v1/dashboards/{dashboard_id}", headers=auth_headers)
        assert response.status_code == 204

    async def test_cannot_delete_last_dashboard(self, client: AsyncClient, auth_headers: dict):
        """Letztes Dashboard kann nicht gelöscht werden."""
        # Liste Dashboards
        list_response = await client.get("/api/v1/dashboards", headers=auth_headers)
        dashboards = list_response.json()

        if len(dashboards) == 1:
            dashboard_id = dashboards[0]["id"]
            response = await client.delete(f"/api/v1/dashboards/{dashboard_id}", headers=auth_headers)
            assert response.status_code == 400


@pytest.mark.asyncio
class TestDashboardActions:
    """Tests für Dashboard-Aktionen."""

    async def test_duplicate_dashboard(self, client: AsyncClient, auth_headers: dict):
        """Dashboard duplizieren."""
        # Erstelle Original
        create_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Original Dashboard"},
            headers=auth_headers,
        )
        dashboard_id = create_response.json()["id"]

        # Duplizieren
        response = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/duplicate?name=Kopie",
            headers=auth_headers,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Kopie"
        assert data["id"] != dashboard_id
        assert data["is_default"] is False

    async def test_set_favorite(self, client: AsyncClient, auth_headers: dict):
        """Dashboard als Favorit setzen."""
        # Erstellen
        create_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Favorit Test"},
            headers=auth_headers,
        )
        dashboard_id = create_response.json()["id"]

        # Als Favorit setzen
        response = await client.patch(
            f"/api/v1/dashboards/{dashboard_id}/favorite?is_favorite=true",
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["is_favorite"] is True


@pytest.mark.asyncio
class TestWidgetManagement:
    """Tests für Widget-Management."""

    async def test_get_available_widgets(self, client: AsyncClient, auth_headers: dict):
        """Verfügbare Widgets abrufen."""
        response = await client.get("/api/v1/dashboards/widgets/available", headers=auth_headers)
        assert response.status_code == 200

        widgets = response.json()
        assert isinstance(widgets, list)
        assert len(widgets) > 0

        # Prüfe Struktur
        widget = widgets[0]
        assert "widget_type" in widget
        assert "display_name" in widget
        assert "default_size" in widget

    async def test_add_widget(self, client: AsyncClient, auth_headers: dict):
        """Widget hinzufügen."""
        # Dashboard erstellen
        dashboard_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Widget Test"},
            headers=auth_headers,
        )
        dashboard_id = dashboard_response.json()["id"]

        # Widget hinzufügen
        widget_payload = {
            "widget_type": "document_count",
            "position": {"i": "", "x": 0, "y": 0, "w": 4, "h": 3},
            "config": {"chart_type": "bar"},
        }

        response = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json=widget_payload,
            headers=auth_headers,
        )
        assert response.status_code == 201

        data = response.json()
        assert data["widget_type"] == "document_count"
        assert data["x"] == 0
        assert data["y"] == 0
        assert "id" in data

    async def test_update_widget(self, client: AsyncClient, auth_headers: dict):
        """Widget aktualisieren."""
        # Dashboard + Widget erstellen
        dashboard_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Widget Update Test"},
            headers=auth_headers,
        )
        dashboard_id = dashboard_response.json()["id"]

        widget_response = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={"widget_type": "document_count"},
            headers=auth_headers,
        )
        widget_id = widget_response.json()["id"]

        # Widget aktualisieren
        update_payload = {
            "position": {"i": widget_id, "x": 4, "y": 0, "w": 6, "h": 4},
            "title_override": "Meine Dokumente",
        }

        response = await client.patch(
            f"/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}",
            json=update_payload,
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["x"] == 4
        assert data["w"] == 6
        assert data["title_override"] == "Meine Dokumente"

    async def test_remove_widget(self, client: AsyncClient, auth_headers: dict):
        """Widget entfernen."""
        # Dashboard + Widget erstellen
        dashboard_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Widget Remove Test"},
            headers=auth_headers,
        )
        dashboard_id = dashboard_response.json()["id"]

        widget_response = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={"widget_type": "document_count"},
            headers=auth_headers,
        )
        widget_id = widget_response.json()["id"]

        # Widget entfernen
        response = await client.delete(
            f"/api/v1/dashboards/{dashboard_id}/widgets/{widget_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204


@pytest.mark.asyncio
class TestLayoutManagement:
    """Tests für Layout-Management."""

    async def test_update_layout(self, client: AsyncClient, auth_headers: dict):
        """Komplettes Layout aktualisieren."""
        # Dashboard + Widgets erstellen
        dashboard_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Layout Test"},
            headers=auth_headers,
        )
        dashboard_id = dashboard_response.json()["id"]

        # 2 Widgets hinzufügen
        widget1 = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={"widget_type": "document_count"},
            headers=auth_headers,
        )
        widget1_id = widget1.json()["id"]

        widget2 = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={"widget_type": "recent_documents"},
            headers=auth_headers,
        )
        widget2_id = widget2.json()["id"]

        # Layout aktualisieren
        layout_payload = {
            "widgets": [
                {"i": widget1_id, "x": 0, "y": 0, "w": 4, "h": 3},
                {"i": widget2_id, "x": 4, "y": 0, "w": 8, "h": 4},
            ]
        }

        response = await client.patch(
            f"/api/v1/dashboards/{dashboard_id}/layout",
            json=layout_payload,
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True


@pytest.mark.asyncio
class TestDashboardSharing:
    """Tests für Dashboard-Sharing."""

    async def test_share_dashboard_with_roles(self, client: AsyncClient, auth_headers: dict):
        """Dashboard mit Rollen teilen."""
        # Dashboard erstellen
        dashboard_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Shared Dashboard"},
            headers=auth_headers,
        )
        dashboard_id = dashboard_response.json()["id"]

        # Mit Rollen teilen
        share_payload = {"roles": ["editor", "viewer"], "permissions": "view"}

        response = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/share",
            json=share_payload,
            headers=auth_headers,
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert "editor" in data["shared_with_roles"]

    async def test_list_shared_dashboards(self, client: AsyncClient, auth_headers: dict):
        """Mit mir geteilte Dashboards auflisten."""
        response = await client.get("/api/v1/dashboards/shared", headers=auth_headers)
        assert response.status_code == 200

        dashboards = response.json()
        assert isinstance(dashboards, list)


@pytest.mark.asyncio
class TestPresets:
    """Tests für Dashboard-Presets."""

    async def test_list_presets(self, client: AsyncClient, auth_headers: dict):
        """Verfügbare Presets auflisten."""
        response = await client.get("/api/v1/dashboards/presets", headers=auth_headers)
        assert response.status_code == 200

        presets = response.json()
        assert isinstance(presets, list)

    async def test_create_from_preset(self, client: AsyncClient, auth_headers: dict):
        """Dashboard von Preset erstellen."""
        # Hole Presets
        presets_response = await client.get("/api/v1/dashboards/presets", headers=auth_headers)
        presets = presets_response.json()

        if len(presets) > 0:
            preset_id = presets[0]["id"]

            # Dashboard von Preset erstellen
            response = await client.post(
                f"/api/v1/dashboards/from-preset/{preset_id}?name=Mein Admin Dashboard",
                headers=auth_headers,
            )
            assert response.status_code == 201

            data = response.json()
            assert data["name"] == "Mein Admin Dashboard"
            assert len(data["widgets"]) > 0


@pytest.mark.asyncio
class TestValidation:
    """Tests für Input-Validierung."""

    async def test_invalid_widget_type(self, client: AsyncClient, auth_headers: dict):
        """Ungültiger Widget-Typ wird abgelehnt."""
        dashboard_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Test"},
            headers=auth_headers,
        )
        dashboard_id = dashboard_response.json()["id"]

        # Ungültiger Widget-Typ
        response = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={"widget_type": "invalid_widget_type"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_invalid_grid_position(self, client: AsyncClient, auth_headers: dict):
        """Ungültige Grid-Position wird abgelehnt."""
        dashboard_response = await client.post(
            "/api/v1/dashboards",
            json={"name": "Test"},
            headers=auth_headers,
        )
        dashboard_id = dashboard_response.json()["id"]

        # x > 11 ist ungültig in 12-column grid
        response = await client.post(
            f"/api/v1/dashboards/{dashboard_id}/widgets",
            json={
                "widget_type": "document_count",
                "position": {"i": "", "x": 15, "y": 0, "w": 4, "h": 3},
            },
            headers=auth_headers,
        )
        assert response.status_code == 422
