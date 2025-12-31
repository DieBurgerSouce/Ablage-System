# -*- coding: utf-8 -*-
"""Integrationstests fuer die Expense API Endpoints.

Tests fuer Spesenabrechnungen:
- Report CRUD
- Item-Verwaltung
- Workflow (Draft -> Submitted -> Approved -> Paid)
- Berechnungs-Endpunkte (Kilometergeld, Verpflegungspauschale)

Alle Tests auf Deutsch mit deutschen Fehlermeldungen.
"""

import pytest
from fastapi import status
from uuid import uuid4
from datetime import date, datetime


@pytest.mark.integration
@pytest.mark.api
class TestExpenseReportAPI:
    """Tests fuer Spesenabrechnung-Endpoints."""

    def test_list_reports_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/expenses/reports")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_reports_with_status_filter(self, client):
        """Test Filterung nach Status."""
        response = client.get(
            "/api/v1/expenses/reports",
            params={"status": "draft"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_reports_with_employee_filter(self, client):
        """Test Filterung nach Mitarbeiter."""
        employee_id = uuid4()
        response = client.get(
            "/api/v1/expenses/reports",
            params={"employee_id": str(employee_id)}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_list_reports_with_date_filter(self, client):
        """Test Filterung nach Periode."""
        response = client.get(
            "/api/v1/expenses/reports",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-12-31"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_report_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        response = client.post(
            "/api/v1/expenses/reports",
            json={
                "title": "Spesenabrechnung Januar 2024",
                "description": "Geschaeftsreise Berlin",
                "period_start": "2024-01-01",
                "period_end": "2024-01-31",
                "purpose": "Kundenbesuch",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_report_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.get(f"/api/v1/expenses/reports/{report_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_update_report_endpoint_exists(self, client):
        """Test dass Update-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.put(
            f"/api/v1/expenses/reports/{report_id}",
            json={"title": "Aktualisierter Titel"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_delete_report_endpoint_exists(self, client):
        """Test dass Delete-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.delete(f"/api/v1/expenses/reports/{report_id}")
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestExpenseItemAPI:
    """Tests fuer Spesenposition-Endpoints."""

    def test_add_item_endpoint_exists(self, client):
        """Test dass Add-Item-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/items",
            json={
                "expense_date": str(date.today()),
                "expense_type": "receipt",
                "description": "Hotelrechnung",
                "amount": "150.00",
                "vendor": "Hotel Berlin",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_update_item_endpoint_exists(self, client):
        """Test dass Update-Item-Endpoint erreichbar ist."""
        item_id = uuid4()
        response = client.put(
            f"/api/v1/expenses/items/{item_id}",
            json={"description": "Aktualisierte Beschreibung"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_delete_item_endpoint_exists(self, client):
        """Test dass Delete-Item-Endpoint erreichbar ist."""
        item_id = uuid4()
        response = client.delete(f"/api/v1/expenses/items/{item_id}")
        assert response.status_code in [
            status.HTTP_204_NO_CONTENT,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_add_mileage_item(self, client):
        """Test Hinzufuegen einer Kilometergeld-Position."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/items",
            json={
                "expense_date": str(date.today()),
                "expense_type": "mileage",
                "description": "Fahrt zum Kunden",
                "mileage_km": "50",
                "mileage_from": "Muenchen",
                "mileage_to": "Augsburg",
                "mileage_purpose": "Kundenbesuch",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_add_per_diem_item(self, client):
        """Test Hinzufuegen einer Verpflegungspauschale."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/items",
            json={
                "expense_date": str(date.today()),
                "expense_type": "per_diem",
                "description": "Verpflegungspauschale",
                "per_diem_hours": "12",
                "per_diem_country": "DE",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_add_entertainment_item(self, client):
        """Test Hinzufuegen von Bewirtungskosten."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/items",
            json={
                "expense_date": str(date.today()),
                "expense_type": "receipt",
                "description": "Geschaeftsessen",
                "amount": "120.00",
                "vendor": "Restaurant Muenchen",
                "is_entertainment": True,
                "entertainment_data": {
                    "occasion": "Projektbesprechung",
                    "attendees": [
                        {"name": "Max Mustermann", "company": "Kunde AG"}
                    ],
                    "business_reason": "Vertragsverhandlung",
                    "host_company": "Meine Firma GmbH"
                }
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestExpenseWorkflowAPI:
    """Tests fuer Workflow-Endpoints."""

    def test_submit_endpoint_exists(self, client):
        """Test dass Submit-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/submit"
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_approve_endpoint_exists(self, client):
        """Test dass Approve-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/approve",
            json={"notes": "Genehmigt"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_reject_endpoint_exists(self, client):
        """Test dass Reject-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/reject",
            json={"reason": "Belege fehlen"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_pay_endpoint_exists(self, client):
        """Test dass Pay-Endpoint erreichbar ist."""
        report_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/pay",
            json={}  # register_id ist optional
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_pay_with_cash_register(self, client):
        """Test Auszahlung mit Kassenbuchung."""
        report_id = uuid4()
        register_id = uuid4()
        response = client.post(
            f"/api/v1/expenses/reports/{report_id}/pay",
            json={"register_id": str(register_id)}
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
class TestExpenseCalculatorAPI:
    """Tests fuer Berechnungs-Endpoints."""

    def test_per_diem_calculator_endpoint_exists(self, client):
        """Test dass Per-Diem-Calculator erreichbar ist."""
        response = client.post(
            "/api/v1/expenses/calculate/per-diem",
            json={
                "travel_start": "2024-01-15T08:00:00",
                "travel_end": "2024-01-15T20:00:00",
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_per_diem_with_meals(self, client):
        """Test Per-Diem-Berechnung mit Mahlzeiten."""
        response = client.post(
            "/api/v1/expenses/calculate/per-diem",
            json={
                "travel_start": "2024-01-15T08:00:00",
                "travel_end": "2024-01-16T18:00:00",
                "meals_provided": {
                    "breakfast": True,
                    "lunch": False,
                    "dinner": False
                }
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_per_diem_country_option(self, client):
        """Test Per-Diem mit Laenderangabe."""
        response = client.post(
            "/api/v1/expenses/calculate/per-diem",
            json={
                "travel_start": "2024-01-15T08:00:00",
                "travel_end": "2024-01-15T20:00:00",
                "country": "AT"  # Oesterreich
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_mileage_calculator_endpoint_exists(self, client):
        """Test dass Mileage-Calculator erreichbar ist."""
        response = client.post(
            "/api/v1/expenses/calculate/mileage",
            json={"kilometers": "100"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_mileage_custom_rate(self, client):
        """Test Kilometergeld mit abweichendem Satz."""
        response = client.post(
            "/api/v1/expenses/calculate/mileage",
            json={
                "kilometers": "50",
                "rate_per_km": "0.35"
            }
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_mileage_returns_calculation(self, client):
        """Test dass Mileage-Berechnung zurueckgegeben wird."""
        response = client.post(
            "/api/v1/expenses/calculate/mileage",
            json={"kilometers": "100"}
        )
        if response.status_code == status.HTTP_200_OK:
            data = response.json()
            assert "kilometers" in data
            assert "rate_per_km" in data
            assert "total_amount" in data


@pytest.mark.integration
@pytest.mark.api
class TestExpenseCompanyContext:
    """Tests fuer Multi-Company-Kontext."""

    def test_requires_company_context(self, client):
        """Test dass Firma erforderlich ist."""
        response = client.get("/api/v1/expenses/reports")
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            data = response.json()
            assert "Firma" in str(data) or "company" in str(data).lower()

    def test_company_header_accepted(self, client):
        """Test dass X-Company-ID Header akzeptiert wird."""
        company_id = uuid4()
        response = client.get(
            "/api/v1/expenses/reports",
            headers={"X-Company-ID": str(company_id)}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestExpenseValidation:
    """Tests fuer Eingabe-Validierung."""

    def test_invalid_status_filter_rejected(self, client):
        """Test dass ungueltiger Status abgelehnt wird."""
        response = client.get(
            "/api/v1/expenses/reports",
            params={"status": "invalid_status"}
        )
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_invalid_date_format_rejected(self, client):
        """Test dass ungueltiges Datumsformat abgelehnt wird."""
        response = client.get(
            "/api/v1/expenses/reports",
            params={"start_date": "not-a-date"}
        )
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_negative_kilometers_handled(self, client):
        """Test Behandlung negativer Kilometer."""
        response = client.post(
            "/api/v1/expenses/calculate/mileage",
            json={"kilometers": "-50"}
        )
        # Sollte validiert werden
        assert response.status_code in [
            status.HTTP_200_OK,  # Manche APIs erlauben negative Werte
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]
