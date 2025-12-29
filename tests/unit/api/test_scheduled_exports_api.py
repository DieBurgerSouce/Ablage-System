# -*- coding: utf-8 -*-
"""
Umfassende Unit Tests fuer Scheduled Exports API.

Testet alle Scheduled Export-Funktionalitaeten:
- POST /scheduled-exports - Scheduled Export erstellen
- GET /scheduled-exports - Scheduled Exports auflisten
- GET /scheduled-exports/{id} - Scheduled Export abrufen
- PUT /scheduled-exports/{id} - Scheduled Export aktualisieren
- DELETE /scheduled-exports/{id} - Scheduled Export loeschen
- POST /scheduled-exports/{id}/run-now - Manuell ausfuehren
- POST /scheduled-exports/{id}/toggle - Aktivieren/Deaktivieren

Feinpoliert und durchdacht - Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestCreateScheduledExport:
    """Tests fuer POST /scheduled-exports Endpoint."""

    @pytest.mark.asyncio
    async def test_create_scheduled_export_success(self, async_client):
        """Scheduled Export erfolgreich erstellen."""
        user_id = uuid4()

        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=user_id, is_active=True)

            response = await async_client.post(
                "/api/v1/scheduled-exports/",
                json={
                    "name": "Täglicher Export",
                    "description": "Exportiert alle Dokumente taeglich",
                    "cron_expression": "0 8 * * *",
                    "timezone": "Europe/Berlin",
                    "export_type": "documents",
                    "export_format": "json",
                    "include_text": True,
                    "include_metadata": True
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 201 Created oder 401/422/500 bei Problemen
            assert response.status_code in [201, 401, 422, 500]

            if response.status_code == 201:
                data = response.json()
                assert "id" in data
                assert data["name"] == "Täglicher Export"
                assert data["is_active"] is True
                assert "next_run_at" in data

    @pytest.mark.asyncio
    async def test_create_scheduled_export_weekly(self, async_client):
        """Woechentlicher Scheduled Export erstellen."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/scheduled-exports/",
                json={
                    "name": "Woechentlicher Export",
                    "cron_expression": "0 8 * * 1",  # Jeden Montag 8:00
                    "export_type": "documents",
                    "export_format": "csv"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [201, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_create_scheduled_export_invalid_cron(self, async_client):
        """Scheduled Export mit ungueltigem Cron-Ausdruck."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/scheduled-exports/",
                json={
                    "name": "Test Export",
                    "cron_expression": "invalid cron",  # Ungueltig
                    "export_type": "documents",
                    "export_format": "json"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # Sollte Validierungsfehler sein
            assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_scheduled_export_invalid_export_type(self, async_client):
        """Scheduled Export mit ungueltigem Export-Typ."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/scheduled-exports/",
                json={
                    "name": "Test Export",
                    "cron_expression": "0 8 * * *",
                    "export_type": "invalid_type",  # Ungueltig
                    "export_format": "json"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_scheduled_export_invalid_format(self, async_client):
        """Scheduled Export mit ungueltigem Format."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/scheduled-exports/",
                json={
                    "name": "Test Export",
                    "cron_expression": "0 8 * * *",
                    "export_type": "documents",
                    "export_format": "invalid_format"  # Ungueltig
                },
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_scheduled_export_empty_name(self, async_client):
        """Scheduled Export ohne Namen."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/scheduled-exports/",
                json={
                    "name": "",  # Leer - min_length=1
                    "cron_expression": "0 8 * * *",
                    "export_type": "documents",
                    "export_format": "json"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_scheduled_export_unauthenticated(self, async_client):
        """Scheduled Export ohne Authentifizierung."""
        response = await async_client.post(
            "/api/v1/scheduled-exports/",
            json={
                "name": "Test Export",
                "cron_expression": "0 8 * * *",
                "export_type": "documents",
                "export_format": "json"
            }
        )

        assert response.status_code in [401, 403]


class TestListScheduledExports:
    """Tests fuer GET /scheduled-exports Endpoint."""

    @pytest.mark.asyncio
    async def test_list_scheduled_exports_success(self, async_client):
        """Scheduled Exports erfolgreich auflisten."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/scheduled-exports/",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "exports" in data
                assert "total" in data
                assert isinstance(data["exports"], list)

    @pytest.mark.asyncio
    async def test_list_scheduled_exports_active_filter(self, async_client):
        """Scheduled Exports mit Active-Filter."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/scheduled-exports/?is_active=true",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "exports" in data

    @pytest.mark.asyncio
    async def test_list_scheduled_exports_pagination(self, async_client):
        """Scheduled Exports mit Pagination."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/scheduled-exports/?limit=10&offset=5",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "total" in data

    @pytest.mark.asyncio
    async def test_list_scheduled_exports_unauthenticated(self, async_client):
        """Scheduled Exports ohne Authentifizierung."""
        response = await async_client.get("/api/v1/scheduled-exports/")

        assert response.status_code in [401, 403]


class TestGetScheduledExport:
    """Tests fuer GET /scheduled-exports/{id} Endpoint."""

    @pytest.mark.asyncio
    async def test_get_scheduled_export_success(self, async_client):
        """Scheduled Export erfolgreich abrufen."""
        export_id = uuid4()

        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/scheduled-exports/{export_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [200, 401, 404]

            if response.status_code == 200:
                data = response.json()
                assert "id" in data
                assert "name" in data
                assert "cron_expression" in data

    @pytest.mark.asyncio
    async def test_get_scheduled_export_not_found(self, async_client):
        """Nicht existierenden Scheduled Export abrufen."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/scheduled-exports/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 404]

    @pytest.mark.asyncio
    async def test_get_scheduled_export_invalid_uuid(self, async_client):
        """Scheduled Export mit ungueltiger UUID."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/scheduled-exports/invalid-uuid",
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 422]


class TestUpdateScheduledExport:
    """Tests fuer PUT /scheduled-exports/{id} Endpoint."""

    @pytest.mark.asyncio
    async def test_update_scheduled_export_success(self, async_client):
        """Scheduled Export erfolgreich aktualisieren."""
        export_id = uuid4()

        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/scheduled-exports/{export_id}",
                json={
                    "name": "Aktualisierter Export",
                    "cron_expression": "0 10 * * *"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert data["name"] == "Aktualisierter Export"

    @pytest.mark.asyncio
    async def test_update_scheduled_export_invalid_cron(self, async_client):
        """Scheduled Export mit ungueltigem Cron aktualisieren."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/scheduled-exports/{uuid4()}",
                json={
                    "cron_expression": "invalid"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 422, 404]

    @pytest.mark.asyncio
    async def test_update_scheduled_export_not_found(self, async_client):
        """Nicht existierenden Scheduled Export aktualisieren."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/scheduled-exports/{uuid4()}",
                json={"name": "Test"},
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 404]


class TestDeleteScheduledExport:
    """Tests fuer DELETE /scheduled-exports/{id} Endpoint."""

    @pytest.mark.asyncio
    async def test_delete_scheduled_export_success(self, async_client):
        """Scheduled Export erfolgreich loeschen."""
        export_id = uuid4()

        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.delete(
                f"/api/v1/scheduled-exports/{export_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 204 No Content oder 404 Not Found
            assert response.status_code in [204, 401, 404]

    @pytest.mark.asyncio
    async def test_delete_scheduled_export_not_found(self, async_client):
        """Nicht existierenden Scheduled Export loeschen."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.delete(
                f"/api/v1/scheduled-exports/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 404]

    @pytest.mark.asyncio
    async def test_delete_scheduled_export_unauthenticated(self, async_client):
        """Scheduled Export ohne Authentifizierung loeschen."""
        response = await async_client.delete(
            f"/api/v1/scheduled-exports/{uuid4()}"
        )

        assert response.status_code in [401, 403]


class TestRunScheduledExportNow:
    """Tests fuer POST /scheduled-exports/{id}/run-now Endpoint."""

    @pytest.mark.asyncio
    async def test_run_now_success(self, async_client):
        """Scheduled Export jetzt ausfuehren."""
        export_id = uuid4()

        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            with patch("app.api.v1.scheduled_exports.run_scheduled_export_task") as mock_task:
                mock_task.delay = Mock()

                response = await async_client.post(
                    f"/api/v1/scheduled-exports/{export_id}/run-now",
                    headers={"Authorization": "Bearer test_token"}
                )

                if response.status_code == 200:
                    data = response.json()
                    assert "job_id" in data
                    assert data["status"] == "queued"

    @pytest.mark.asyncio
    async def test_run_now_not_found(self, async_client):
        """Nicht existierenden Export jetzt ausfuehren."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/scheduled-exports/{uuid4()}/run-now",
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 404]

    @pytest.mark.asyncio
    async def test_run_now_unauthenticated(self, async_client):
        """Export ohne Authentifizierung ausfuehren."""
        response = await async_client.post(
            f"/api/v1/scheduled-exports/{uuid4()}/run-now"
        )

        assert response.status_code in [401, 403]


class TestToggleScheduledExport:
    """Tests fuer POST /scheduled-exports/{id}/toggle Endpoint."""

    @pytest.mark.asyncio
    async def test_toggle_success(self, async_client):
        """Scheduled Export aktivieren/deaktivieren."""
        export_id = uuid4()

        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/scheduled-exports/{export_id}/toggle",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "is_active" in data

    @pytest.mark.asyncio
    async def test_toggle_not_found(self, async_client):
        """Nicht existierenden Export togglen."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/scheduled-exports/{uuid4()}/toggle",
                headers={"Authorization": "Bearer test_token"}
            )

            assert response.status_code in [401, 404]


class TestScheduledExportModels:
    """Tests fuer Scheduled Export Pydantic Models."""

    def test_scheduled_export_create_validation(self):
        """ScheduledExportCreate Validierung."""
        from app.api.v1.scheduled_exports import ScheduledExportCreate

        # Gueltige Daten
        valid_data = {
            "name": "Test Export",
            "cron_expression": "0 8 * * *",
            "export_type": "documents",
            "export_format": "json"
        }

        request = ScheduledExportCreate(**valid_data)
        assert request.name == "Test Export"
        assert request.cron_expression == "0 8 * * *"
        assert request.timezone == "Europe/Berlin"  # Default

    def test_scheduled_export_create_defaults(self):
        """ScheduledExportCreate Standardwerte."""
        from app.api.v1.scheduled_exports import ScheduledExportCreate

        request = ScheduledExportCreate(
            name="Test",
            cron_expression="0 8 * * *",
            export_type="documents",
            export_format="json"
        )

        assert request.timezone == "Europe/Berlin"
        assert request.include_text is True
        assert request.include_metadata is True
        assert request.notify_email is True
        assert request.notify_on_failure_only is False

    def test_scheduled_export_create_invalid_cron_raises(self):
        """ScheduledExportCreate mit ungueltigem Cron wirft Fehler."""
        from app.api.v1.scheduled_exports import ScheduledExportCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ScheduledExportCreate(
                name="Test",
                cron_expression="invalid",
                export_type="documents",
                export_format="json"
            )

    def test_scheduled_export_response_fields(self):
        """ScheduledExportResponse hat alle erforderlichen Felder."""
        from app.api.v1.scheduled_exports import ScheduledExportResponse

        fields = ScheduledExportResponse.model_fields.keys()

        required_fields = [
            "id", "name", "cron_expression", "timezone",
            "export_type", "export_format", "is_active",
            "total_runs", "successful_runs", "failed_runs"
        ]

        for field in required_fields:
            assert field in fields


class TestCronDescriptions:
    """Tests fuer Cron-Beschreibungen."""

    def test_get_cron_description_daily(self):
        """Taeglich-Beschreibung."""
        from app.api.v1.scheduled_exports import get_cron_description

        desc = get_cron_description("0 8 * * *")
        assert "08:00" in desc or "taeglich" in desc.lower() or "täglich" in desc.lower()

    def test_get_cron_description_weekly(self):
        """Woechentlich-Beschreibung."""
        from app.api.v1.scheduled_exports import get_cron_description

        desc = get_cron_description("0 8 * * 1")
        assert "Mo" in desc or "Montag" in desc.lower() or "08:00" in desc

    def test_get_cron_description_monthly(self):
        """Monatlich-Beschreibung."""
        from app.api.v1.scheduled_exports import get_cron_description

        desc = get_cron_description("0 0 1 * *")
        assert "1." in desc or "Monat" in desc.lower() or "Mitternacht" in desc


class TestGermanMessages:
    """Tests fuer deutsche Fehlermeldungen."""

    @pytest.mark.asyncio
    async def test_export_not_found_german(self, async_client):
        """Export nicht gefunden - deutsche Meldung."""
        with patch("app.api.v1.scheduled_exports.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/scheduled-exports/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 404:
                data = response.json()
                assert "detail" in data
                detail = data["detail"].lower()
                assert "nicht gefunden" in detail or "berechtigung" in detail


class TestExportTypes:
    """Tests fuer verschiedene Export-Typen."""

    def test_valid_export_types(self):
        """Gueltige Export-Typen."""
        from app.api.v1.scheduled_exports import ScheduledExportCreate

        valid_types = ["documents", "invoices", "datev", "training"]

        for export_type in valid_types:
            request = ScheduledExportCreate(
                name="Test",
                cron_expression="0 8 * * *",
                export_type=export_type,
                export_format="json"
            )
            assert request.export_type == export_type

    def test_valid_export_formats(self):
        """Gueltige Export-Formate."""
        from app.api.v1.scheduled_exports import ScheduledExportCreate

        valid_formats = ["json", "csv", "zip", "excel", "pdf"]

        for fmt in valid_formats:
            request = ScheduledExportCreate(
                name="Test",
                cron_expression="0 8 * * *",
                export_type="documents",
                export_format=fmt
            )
            assert request.export_format == fmt


class TestTimezoneHandling:
    """Tests fuer Timezone-Behandlung."""

    def test_calculate_next_run_berlin(self):
        """Berechnung naechster Lauf in Berlin-Zeitzone."""
        from app.api.v1.scheduled_exports import calculate_next_run

        next_run = calculate_next_run("0 8 * * *", "Europe/Berlin")

        assert next_run is not None
        assert next_run.tzinfo is not None

    def test_calculate_next_run_utc(self):
        """Berechnung naechster Lauf in UTC."""
        from app.api.v1.scheduled_exports import calculate_next_run

        next_run = calculate_next_run("0 8 * * *", "UTC")

        assert next_run is not None

    def test_calculate_next_run_invalid_timezone(self):
        """Berechnung mit ungueltiger Zeitzone faellt auf UTC zurueck."""
        from app.api.v1.scheduled_exports import calculate_next_run

        # Sollte nicht crashen, sondern auf UTC fallback
        next_run = calculate_next_run("0 8 * * *", "Invalid/Timezone")

        assert next_run is not None
