# -*- coding: utf-8 -*-
"""
Unit Tests fuer Tax Authority Export API (Feature 20).

Testet:
- GET /api/v1/archive/export/tax-authority/tables
- POST /api/v1/archive/export/tax-authority/preview
- POST /api/v1/archive/export/tax-authority
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
import pytest
from fastapi import status


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_company():
    """Mock Company fuer Tests."""
    company = MagicMock()
    company.id = uuid4()
    company.name = "Test GmbH"
    return company


@pytest.fixture
def mock_export_result():
    """Mock ExportResult fuer Tests."""
    from app.services.compliance.tax_authority_export_service import (
        ExportResult,
        ExportFormat,
        ExportStatistics,
    )

    return ExportResult(
        success=True,
        export_id="test-export-123",
        format=ExportFormat.GDPDU,
        period_start=date(2024, 1, 1),
        period_end=date(2024, 12, 31),
        company_name="Test GmbH",
        files=["index.xml", "rechnungen.csv", "bankbewegungen.csv"],
        archive_path="/tmp/export.zip",
        statistics=ExportStatistics(
            total_records=150,
            invoices_count=50,
            transactions_count=80,
            documents_count=15,
            audit_entries_count=5,
        ),
    )


# =============================================================================
# GET /export/tax-authority/tables Tests
# =============================================================================


class TestListTaxExportTables:
    """Tests fuer GET /archive/export/tax-authority/tables."""

    @pytest.mark.asyncio
    async def test_returns_table_definitions(self, client, superuser_headers):
        """Test: Tabellendefinitionen werden zurueckgegeben."""
        response = await client.get(
            "/api/v1/archive/export/tax-authority/tables",
            headers=superuser_headers,
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "tables" in data
        assert "total_tables" in data
        assert data["total_tables"] >= 4

        # Pruefe Tabellenstruktur
        table = data["tables"][0]
        assert "name" in table
        assert "description" in table
        assert "category" in table
        assert "fields" in table

    @pytest.mark.asyncio
    async def test_requires_superuser(self, client, auth_headers):
        """Test: Nur Superuser duerfen zugreifen."""
        response = await client.get(
            "/api/v1/archive/export/tax-authority/tables",
            headers=auth_headers,
        )

        # Normaler User sollte 403 bekommen
        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_401_UNAUTHORIZED,
        ]

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client):
        """Test: Authentifizierung erforderlich."""
        response = await client.get("/api/v1/archive/export/tax-authority/tables")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# =============================================================================
# POST /export/tax-authority/preview Tests
# =============================================================================


class TestPreviewTaxExport:
    """Tests fuer POST /archive/export/tax-authority/preview."""

    @pytest.mark.asyncio
    async def test_returns_preview(
        self, client, superuser_headers, mock_company
    ):
        """Test: Vorschau wird zurueckgegeben."""
        with patch(
            "app.api.v1.archive.require_company"
        ) as mock_require_company:
            mock_require_company.return_value = mock_company

            with patch(
                "app.api.v1.archive.get_tax_authority_export_service"
            ) as mock_service:
                service = AsyncMock()
                service.count_records_by_category.return_value = {
                    "rechnungen": 50,
                    "bankbewegungen": 80,
                    "belege": 15,
                    "aenderungsprotokoll": 5,
                }
                mock_service.return_value = service

                response = await client.post(
                    "/api/v1/archive/export/tax-authority/preview",
                    json={
                        "period_start": "2024-01-01",
                        "period_end": "2024-12-31",
                    },
                    headers=superuser_headers,
                )

                assert response.status_code == status.HTTP_200_OK
                data = response.json()
                assert data["estimated_records"] == 150
                assert "categories" in data
                assert data["categories"]["rechnungen"] == 50

    @pytest.mark.asyncio
    async def test_validates_date_range(self, client, superuser_headers):
        """Test: Datumsbereich wird validiert."""
        response = await client.post(
            "/api/v1/archive/export/tax-authority/preview",
            json={
                "period_start": "invalid-date",
                "period_end": "2024-12-31",
            },
            headers=superuser_headers,
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# =============================================================================
# POST /export/tax-authority Tests
# =============================================================================


class TestCreateTaxExport:
    """Tests fuer POST /archive/export/tax-authority."""

    @pytest.mark.asyncio
    async def test_creates_export(
        self, client, superuser_headers, mock_company, mock_export_result
    ):
        """Test: Export wird erstellt."""
        with patch(
            "app.api.v1.archive.require_company"
        ) as mock_require_company:
            mock_require_company.return_value = mock_company

            with patch(
                "app.api.v1.archive.get_tax_authority_export_service"
            ) as mock_service:
                service = AsyncMock()
                service.create_gdpdu_export.return_value = mock_export_result
                mock_service.return_value = service

                # Mock file reading
                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = (
                        b"PK\x03\x04"  # ZIP magic bytes
                    )

                    response = await client.post(
                        "/api/v1/archive/export/tax-authority",
                        json={
                            "period_start": "2024-01-01",
                            "period_end": "2024-12-31",
                        },
                        headers=superuser_headers,
                    )

                    # Sollte ZIP zurueckgeben
                    assert response.status_code == status.HTTP_200_OK
                    assert (
                        response.headers.get("content-type") == "application/zip"
                        or "attachment" in response.headers.get("content-disposition", "")
                    )

    @pytest.mark.asyncio
    async def test_handles_export_failure(
        self, client, superuser_headers, mock_company
    ):
        """Test: Fehler bei Export wird behandelt."""
        from app.services.compliance.tax_authority_export_service import (
            ExportResult,
            ExportFormat,
            ExportStatistics,
        )

        failed_result = ExportResult(
            success=False,
            export_id="failed-export",
            format=ExportFormat.GDPDU,
            period_start=date(2024, 1, 1),
            period_end=date(2024, 12, 31),
            company_name="Test GmbH",
            files=[],
            error="Export fehlgeschlagen: Keine Daten gefunden",
            statistics=ExportStatistics(
                total_records=0,
                invoices_count=0,
                transactions_count=0,
                documents_count=0,
                audit_entries_count=0,
            ),
        )

        with patch(
            "app.api.v1.archive.require_company"
        ) as mock_require_company:
            mock_require_company.return_value = mock_company

            with patch(
                "app.api.v1.archive.get_tax_authority_export_service"
            ) as mock_service:
                service = AsyncMock()
                service.create_gdpdu_export.return_value = failed_result
                mock_service.return_value = service

                response = await client.post(
                    "/api/v1/archive/export/tax-authority",
                    json={
                        "period_start": "2024-01-01",
                        "period_end": "2024-12-31",
                    },
                    headers=superuser_headers,
                )

                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_requires_superuser_permission(self, client, auth_headers):
        """Test: Nur Superuser duerfen exportieren."""
        response = await client.post(
            "/api/v1/archive/export/tax-authority",
            json={
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
            },
            headers=auth_headers,
        )

        assert response.status_code in [
            status.HTTP_403_FORBIDDEN,
            status.HTTP_401_UNAUTHORIZED,
        ]
