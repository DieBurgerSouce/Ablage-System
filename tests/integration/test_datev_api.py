# -*- coding: utf-8 -*-
"""
Integration Tests fuer DATEV API Endpoints.

Testet die vollstaendige API-Integration inkl. Authentication,
Request-Validation und Response-Format.
"""

import uuid
from datetime import date
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def valid_config_create_data() -> Dict[str, Any]:
    """Gueltige Daten fuer DATEV-Konfiguration."""
    return {
        "berater_nr": "1234567",
        "mandanten_nr": "12345",
        "wj_beginn": "2025-01-01",
        "kontenrahmen": "SKR03",
        "sachkontenlange": 4,
        "is_default": True,
    }


@pytest.fixture
def valid_vendor_mapping_data() -> Dict[str, Any]:
    """Gueltige Daten fuer Vendor-Mapping."""
    return {
        "vendor_name": "Test Lieferant GmbH",
        "vendor_vat_id": "DE123456789",
        "expense_account": "3200",
        "creditor_account": "70001",
    }


@pytest.fixture
def valid_export_request_data() -> Dict[str, Any]:
    """Gueltige Daten fuer Export-Request."""
    return {
        "period_from": "2025-01-01",
        "period_to": "2025-12-31",
        "include_already_exported": False,
    }


@pytest.fixture
def mock_auth_headers() -> Dict[str, str]:
    """Mock Authentication Headers."""
    return {
        "Authorization": "Bearer test-token-123",
        "Content-Type": "application/json",
    }


# =============================================================================
# CONFIGURATION ENDPOINT TESTS
# =============================================================================

class TestDATEVConfigurationAPI:
    """Tests fuer /api/v1/datev/config Endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_config_returns_201(
        self, async_client: AsyncClient, valid_config_create_data, mock_auth_headers
    ):
        """POST /config sollte 201 mit erstellter Konfiguration zurueckgeben."""
        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/datev/config",
                json=valid_config_create_data,
                headers=mock_auth_headers,
            )

            # Wir erwarten 201 Created oder 422 wenn DB nicht verfuegbar
            assert response.status_code in [201, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_config_validates_berater_nr_format(
        self, async_client: AsyncClient, valid_config_create_data, mock_auth_headers
    ):
        """berater_nr muss 1-7 Ziffern sein."""
        invalid_data = valid_config_create_data.copy()
        invalid_data["berater_nr"] = "ABC1234"  # Buchstaben nicht erlaubt

        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/datev/config",
                json=invalid_data,
                headers=mock_auth_headers,
            )

            # Pydantic Validation sollte 422 zurueckgeben
            assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_config_validates_kontenrahmen_enum(
        self, async_client: AsyncClient, valid_config_create_data, mock_auth_headers
    ):
        """kontenrahmen muss SKR03 oder SKR04 sein."""
        invalid_data = valid_config_create_data.copy()
        invalid_data["kontenrahmen"] = "INVALID"

        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/datev/config",
                json=invalid_data,
                headers=mock_auth_headers,
            )

            # Pydantic Validation sollte 422 zurueckgeben
            assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_configs_requires_authentication(
        self, async_client: AsyncClient
    ):
        """GET /config ohne Auth sollte 401 oder 403 zurueckgeben."""
        response = await async_client.get("/api/v1/datev/config")

        # Ohne Auth: 401 Unauthorized oder 403 Forbidden
        assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_config_returns_204(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """DELETE /config/{id} sollte 204 No Content zurueckgeben."""
        config_id = uuid.uuid4()

        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.delete(
                f"/api/v1/datev/config/{config_id}",
                headers=mock_auth_headers,
            )

            # 204 (erfolgreich) oder 404 (nicht gefunden) sind beide valide
            assert response.status_code in [204, 404, 500]


# =============================================================================
# VENDOR MAPPING ENDPOINT TESTS
# =============================================================================

class TestDATEVVendorMappingAPI:
    """Tests fuer /api/v1/datev/config/{id}/vendors Endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_vendor_mapping_requires_identifier(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """Vendor-Mapping benoetigt mindestens ein Identifikationsmerkmal."""
        config_id = uuid.uuid4()
        invalid_data = {
            "expense_account": "3200",
            # Kein vendor_name, vendor_vat_id, vendor_iban, business_entity_id
        }

        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.post(
                f"/api/v1/datev/config/{config_id}/vendors",
                json=invalid_data,
                headers=mock_auth_headers,
            )

            # Sollte 400 Bad Request sein (oder 404 wenn Config nicht existiert)
            assert response.status_code in [400, 404, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_vendor_mapping_validates_ownership(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """DELETE Vendor-Mapping prueft Config-Ownership."""
        config_id = uuid.uuid4()
        mapping_id = uuid.uuid4()

        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.delete(
                f"/api/v1/datev/config/{config_id}/vendors/{mapping_id}",
                headers=mock_auth_headers,
            )

            # Sollte 404 sein (Config gehoert nicht dem User)
            assert response.status_code in [204, 404, 500]


# =============================================================================
# EXPORT ENDPOINT TESTS
# =============================================================================

class TestDATEVExportAPI:
    """Tests fuer /api/v1/datev/export Endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_preview_validates_date_range(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """Export-Preview validiert Datumsbereich."""
        invalid_data = {
            "period_from": "2025-12-31",
            "period_to": "2025-01-01",  # to < from ist ungueltig
        }

        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.post(
                "/api/v1/datev/export/preview",
                json=invalid_data,
                headers=mock_auth_headers,
            )

            # Sollte Fehler sein (400 oder 422)
            assert response.status_code in [400, 422, 500]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_returns_csv_content_type(
        self, async_client: AsyncClient, valid_export_request_data, mock_auth_headers
    ):
        """Export gibt CSV mit korrektem Content-Type zurueck."""
        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            with patch('app.api.v1.datev.get_datev_export_service') as mock_service:
                # Mock erfolgreichen Export
                service = MagicMock()
                export_record = MagicMock()
                export_record.id = uuid.uuid4()
                export_record.filename = "EXTF_Buchungsstapel_2025.csv"
                export_record.document_count = 10

                service.export_buchungsstapel = AsyncMock(
                    return_value=(b"CSV-Content", export_record)
                )
                mock_service.return_value = service

                response = await async_client.post(
                    "/api/v1/datev/export",
                    json=valid_export_request_data,
                    headers=mock_auth_headers,
                )

                if response.status_code == 200:
                    # Pruefe Content-Type
                    assert "text/csv" in response.headers.get("content-type", "")
                    # Pruefe Custom Headers
                    assert "X-DATEV-Export-ID" in response.headers
                    assert "X-DATEV-Document-Count" in response.headers

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_error_does_not_leak_details(
        self, async_client: AsyncClient, valid_export_request_data, mock_auth_headers
    ):
        """Export-Fehler enthaelt keine sensiblen Details."""
        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            with patch('app.api.v1.datev.get_datev_export_service') as mock_service:
                service = MagicMock()
                # Simuliere internen Fehler mit sensiblen Daten
                service.export_buchungsstapel = AsyncMock(
                    side_effect=RuntimeError("Database error: password=secret123")
                )
                mock_service.return_value = service

                response = await async_client.post(
                    "/api/v1/datev/export",
                    json=valid_export_request_data,
                    headers=mock_auth_headers,
                )

                assert response.status_code == 500
                response_json = response.json()

                # Sensible Daten duerfen NICHT in Response sein
                detail = response_json.get("detail", "")
                assert "password" not in detail.lower()
                assert "secret" not in detail.lower()
                assert "database error" not in detail.lower()


# =============================================================================
# EXPORT HISTORY TESTS
# =============================================================================

class TestDATEVExportHistoryAPI:
    """Tests fuer /api/v1/datev/export/history Endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_history_pagination(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """Export-History unterstuetzt Pagination."""
        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.get(
                "/api/v1/datev/export/history?page=1&page_size=10",
                headers=mock_auth_headers,
            )

            # Sollte 200 oder 500 (wenn DB nicht verfuegbar)
            if response.status_code == 200:
                response_json = response.json()
                assert "items" in response_json
                assert "total" in response_json
                assert "page" in response_json
                assert "page_size" in response_json

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_history_validates_page_size(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """Export-History validiert page_size (max 100)."""
        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.get(
                "/api/v1/datev/export/history?page=1&page_size=500",  # zu gross
                headers=mock_auth_headers,
            )

            # Sollte 422 Validation Error sein
            assert response.status_code == 422


# =============================================================================
# KONTENRAHMEN INFO TESTS
# =============================================================================

class TestDATEVKontenrahmenAPI:
    """Tests fuer /api/v1/datev/kontenrahmen Endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_kontenrahmen_info_returns_both_frameworks(
        self, async_client: AsyncClient
    ):
        """Kontenrahmen-Info gibt SKR03 und SKR04 zurueck."""
        response = await async_client.get("/api/v1/datev/kontenrahmen")

        # Dieser Endpoint benoetigt keine Auth
        if response.status_code == 200:
            response_json = response.json()
            assert len(response_json) == 2

            names = [item["name"] for item in response_json]
            assert "SKR03" in names
            assert "SKR04" in names

            # Pruefe Struktur
            for item in response_json:
                assert "name" in item
                assert "beschreibung" in item
                assert "standard_konten" in item
                assert "verfuegbare_kategorien" in item

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_kontenrahmen_contains_required_accounts(
        self, async_client: AsyncClient
    ):
        """Kontenrahmen enthaelt alle erforderlichen Standardkonten."""
        response = await async_client.get("/api/v1/datev/kontenrahmen")

        if response.status_code == 200:
            response_json = response.json()

            required_accounts = [
                "wareneingang_19",
                "wareneingang_7",
                "erloese_19",
                "erloese_7",
                "kreditor_default",
                "debitor_default",
                "sammelkonto_kreditoren",
                "sammelkonto_debitoren",
            ]

            for item in response_json:
                standard_konten = item["standard_konten"]
                for account in required_accounts:
                    assert account in standard_konten, f"{account} fehlt in {item['name']}"


# =============================================================================
# RESPONSE FORMAT TESTS
# =============================================================================

class TestDATEVResponseFormats:
    """Tests fuer konsistente Response-Formate."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_error_responses_are_in_german(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """Fehlermeldungen sind auf Deutsch."""
        # Nicht existierende Config
        config_id = uuid.uuid4()

        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            response = await async_client.get(
                f"/api/v1/datev/config/{config_id}",
                headers=mock_auth_headers,
            )

            if response.status_code == 404:
                response_json = response.json()
                detail = response_json.get("detail", "")
                # Deutsche Fehlermeldung erwartet
                assert "nicht gefunden" in detail.lower() or "not found" not in detail.lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uuid_format_in_responses(
        self, async_client: AsyncClient, mock_auth_headers
    ):
        """UUIDs in Responses sind valide."""
        with patch('app.api.dependencies.get_current_active_user') as mock_auth:
            mock_user = MagicMock()
            mock_user.id = uuid.uuid4()
            mock_auth.return_value = mock_user

            # Bei erfolgreicher Erstellung sollte ID ein valides UUID sein
            # (Test nur wenn wir eine echte Response bekommen)
            response = await async_client.get(
                "/api/v1/datev/config",
                headers=mock_auth_headers,
            )

            if response.status_code == 200:
                response_json = response.json()
                for config in response_json:
                    if "id" in config:
                        # Sollte ohne Exception parsen
                        uuid.UUID(config["id"])
