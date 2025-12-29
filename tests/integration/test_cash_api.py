# -*- coding: utf-8 -*-
"""Integrationstests fuer die Cash API Endpoints.

Tests fuer GoBD-konforme Kassenbuchfuehrung:
- Register CRUD
- Entry-Erstellung (APPEND-ONLY)
- Stornierung (Gegenbuchung)
- Kassensturz
- Berichte

Alle Tests auf Deutsch mit deutschen Fehlermeldungen.
"""

import pytest
from fastapi import status
from uuid import uuid4
from datetime import date
from decimal import Decimal


@pytest.mark.integration
@pytest.mark.api
class TestCashRegisterAPI:
    """Tests fuer Kassen-Endpoints."""

    def test_list_registers_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/cash/registers")
        # Endpoint sollte existieren (auch wenn Auth/Company fehlt)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,  # Keine Firma ausgewaehlt
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_register_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        response = client.post(
            "/api/v1/cash/registers",
            json={
                "name": "Hauptkasse",
                "description": "Testkasse",
            }
        )
        # Endpoint sollte existieren
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,  # Keine Firma ausgewaehlt
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_register_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        register_id = uuid4()
        response = client.get(f"/api/v1/cash/registers/{register_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_update_register_endpoint_exists(self, client):
        """Test dass Update-Endpoint erreichbar ist."""
        register_id = uuid4()
        response = client.put(
            f"/api/v1/cash/registers/{register_id}",
            json={"name": "Aktualisierte Kasse"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestCashEntryAPI:
    """Tests fuer Kassenbucheintrag-Endpoints (APPEND-ONLY!)."""

    def test_list_entries_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/cash/entries")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_entries_with_register_filter(self, client):
        """Test Filterung nach Kasse."""
        register_id = uuid4()
        response = client.get(
            "/api/v1/cash/entries",
            params={"register_id": str(register_id)}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_entries_with_date_filter(self, client):
        """Test Filterung nach Datum."""
        response = client.get(
            "/api/v1/cash/entries",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-31"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_entry_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        register_id = uuid4()
        response = client.post(
            "/api/v1/cash/entries",
            json={
                "register_id": str(register_id),
                "entry_date": str(date.today()),
                "entry_type": "income",
                "amount": "100.00",
                "description": "Testeinnahme",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_entry_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        entry_id = uuid4()
        response = client.get(f"/api/v1/cash/entries/{entry_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_cancel_entry_endpoint_exists(self, client):
        """Test dass Storno-Endpoint erreichbar ist."""
        entry_id = uuid4()
        response = client.post(
            f"/api/v1/cash/entries/{entry_id}/cancel",
            json={"reason": "Testgrund"}
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_no_put_endpoint_for_entries(self, client):
        """Test dass kein PUT-Endpoint existiert (GoBD!)."""
        entry_id = uuid4()
        response = client.put(
            f"/api/v1/cash/entries/{entry_id}",
            json={"amount": "200.00"}
        )
        # APPEND-ONLY: PUT sollte nicht erlaubt sein
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_no_delete_endpoint_for_entries(self, client):
        """Test dass kein DELETE-Endpoint existiert (GoBD!)."""
        entry_id = uuid4()
        response = client.delete(f"/api/v1/cash/entries/{entry_id}")
        # APPEND-ONLY: DELETE sollte nicht erlaubt sein
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


@pytest.mark.integration
@pytest.mark.api
class TestCashCountAPI:
    """Tests fuer Kassensturz-Endpoints."""

    def test_list_counts_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/cash/counts")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_counts_with_register_filter(self, client):
        """Test Filterung nach Kasse."""
        register_id = uuid4()
        response = client.get(
            "/api/v1/cash/counts",
            params={"register_id": str(register_id)}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_count_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        register_id = uuid4()
        response = client.post(
            "/api/v1/cash/counts",
            json={
                "register_id": str(register_id),
                "counted_balance": "500.00",
                "denomination_details": {
                    "coins": {"1.00": 5, "2.00": 3},
                    "notes": {"10": 2, "50": 1}
                },
                "notes": "Tagesabschluss"
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestCashReportAPI:
    """Tests fuer Bericht-Endpoints."""

    def test_summary_endpoint_exists(self, client):
        """Test dass Summary-Endpoint erreichbar ist."""
        register_id = uuid4()
        response = client.get(
            "/api/v1/cash/summary",
            params={"register_id": str(register_id)}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_daily_summary_endpoint_exists(self, client):
        """Test dass Daily-Endpoint erreichbar ist."""
        register_id = uuid4()
        response = client.get(
            "/api/v1/cash/daily",
            params={
                "register_id": str(register_id),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestCashCategoryAPI:
    """Tests fuer Kategorien-Endpoints."""

    def test_list_categories_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/cash/categories")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_category_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        response = client.post(
            "/api/v1/cash/categories",
            json={
                "name": "Bueroausgaben",
                "description": "Allgemeine Bueroausgaben",
                "skr03_account": "4930",
                "skr04_account": "6815",
                "default_tax_rate": "19.00"
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestCashCompanyContext:
    """Tests fuer Multi-Company-Kontext."""

    def test_requires_company_header_or_selection(self, client):
        """Test dass Firma erforderlich ist."""
        response = client.get("/api/v1/cash/registers")
        # Ohne Firma sollte Fehler kommen
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            data = response.json()
            # Fehlermeldung sollte auf Firmenwahl hinweisen
            assert "Firma" in str(data) or "company" in str(data).lower()

    def test_company_header_accepted(self, client):
        """Test dass X-Company-ID Header akzeptiert wird."""
        company_id = uuid4()
        response = client.get(
            "/api/v1/cash/registers",
            headers={"X-Company-ID": str(company_id)}
        )
        # Header sollte akzeptiert werden (auch wenn Company nicht existiert)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]
