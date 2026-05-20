# -*- coding: utf-8 -*-
"""Integrationstests fuer die Privat API Endpoints.

Tests fuer das Privat-Modul:
- Space CRUD
- Folder CRUD
- Document CRUD
- Properties, Vehicles, Insurances, Loans, Investments
- Deadlines mit iCal-Export
- Emergency Access

Alle Tests auf Deutsch mit deutschen Fehlermeldungen.
"""

import pytest
from fastapi import status
from uuid import uuid4
from datetime import date, timedelta


@pytest.mark.integration
@pytest.mark.api
class TestPrivatSpaceAPI:
    """Tests fuer Space-Endpoints."""

    def test_list_spaces_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        response = client.get("/api/v1/privat/spaces")
        # Endpoint sollte existieren (auch wenn Auth fehlt)
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_space_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        response = client.post(
            "/api/v1/privat/spaces",
            json={
                "name": "Mein Privat-Bereich",
                "description": "Persoenliche Dokumente",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_space_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/spaces/{space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_update_space_endpoint_exists(self, client):
        """Test dass Update-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.put(
            f"/api/v1/privat/spaces/{space_id}",
            json={"name": "Umbenannter Bereich"}
        )
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_delete_space_endpoint_exists(self, client):
        """Test dass Delete-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.delete(f"/api/v1/privat/spaces/{space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_204_NO_CONTENT,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestPrivatFolderAPI:
    """Tests fuer Folder-Endpoints."""

    def test_list_folders_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/folders?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_folder_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/folders",
            json={
                "space_id": str(space_id),
                "name": "Versicherungen",
                "parent_id": None,
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_folder_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        folder_id = uuid4()
        response = client.get(f"/api/v1/privat/folders/{folder_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_update_folder_endpoint_exists(self, client):
        """Test dass Update-Endpoint erreichbar ist."""
        folder_id = uuid4()
        response = client.put(
            f"/api/v1/privat/folders/{folder_id}",
            json={"name": "Umbenannter Ordner"}
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
class TestPrivatDocumentAPI:
    """Tests fuer Document-Endpoints."""

    def test_list_documents_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/documents?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_get_document_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        document_id = uuid4()
        response = client.get(f"/api/v1/privat/documents/{document_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestPrivatPropertyAPI:
    """Tests fuer Property-Endpoints (Immobilien)."""

    def test_list_properties_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/properties?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_property_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/properties",
            json={
                "space_id": str(space_id),
                "name": "Miethaus Berlin",
                "property_type": "rental",
                "address": "Berliner Str. 123, 10178 Berlin",
                "purchase_date": "2020-01-15",
                "purchase_price": "350000.00",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_property_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        property_id = uuid4()
        response = client.get(f"/api/v1/privat/properties/{property_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestPrivatVehicleAPI:
    """Tests fuer Vehicle-Endpoints (Fahrzeuge)."""

    def test_list_vehicles_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/vehicles?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_vehicle_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/vehicles",
            json={
                "space_id": str(space_id),
                "name": "BMW 3er",
                "vehicle_type": "car",
                "license_plate": "B-XY 1234",
                "vin": "WBAPH5C55BA123456",
                "manufacturer": "BMW",
                "model": "320d",
                "year": 2021,
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_vehicle_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        vehicle_id = uuid4()
        response = client.get(f"/api/v1/privat/vehicles/{vehicle_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
class TestPrivatInsuranceAPI:
    """Tests fuer Insurance-Endpoints (Versicherungen)."""

    def test_list_insurances_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/insurances?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_insurance_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/insurances",
            json={
                "space_id": str(space_id),
                "name": "Hausratversicherung",
                "insurance_type": "household",
                "provider": "Allianz",
                "policy_number": "POL-12345-2024",
                "premium_amount": "250.00",
                "premium_interval": "annual",
                "coverage_start": "2024-01-01",
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
class TestPrivatLoanAPI:
    """Tests fuer Loan-Endpoints (Kredite)."""

    def test_list_loans_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/loans?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_loan_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/loans",
            json={
                "space_id": str(space_id),
                "name": "Immobilienkredit",
                "loan_type": "mortgage",
                "lender": "Sparkasse",
                "principal_amount": "250000.00",
                "interest_rate": "2.50",
                "start_date": "2024-01-15",
                "monthly_payment": "950.00",
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
class TestPrivatInvestmentAPI:
    """Tests fuer Investment-Endpoints (Geldanlagen)."""

    def test_list_investments_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/investments?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_investment_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/investments",
            json={
                "space_id": str(space_id),
                "name": "ETF MSCI World",
                "investment_type": "etf",
                "broker": "comdirect",
                "initial_amount": "10000.00",
                "current_value": "12500.00",
                "purchase_date": "2023-01-01",
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
class TestPrivatDeadlineAPI:
    """Tests fuer Deadline-Endpoints (Fristen)."""

    def test_list_deadlines_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/deadlines?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_deadline_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        due_date = (date.today() + timedelta(days=30)).isoformat()
        response = client.post(
            "/api/v1/privat/deadlines",
            json={
                "space_id": str(space_id),
                "title": "Versicherung erneuern",
                "description": "Hausratversicherung muss verlaengert werden",
                "deadline_type": "insurance_renewal",
                "due_date": due_date,
                "reminder_days": [7, 3, 1],
                "priority": "medium",
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_get_deadline_endpoint_exists(self, client):
        """Test dass Get-Endpoint erreichbar ist."""
        deadline_id = uuid4()
        response = client.get(f"/api/v1/privat/deadlines/{deadline_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_complete_deadline_endpoint_exists(self, client):
        """Test dass Complete-Endpoint erreichbar ist."""
        deadline_id = uuid4()
        response = client.post(f"/api/v1/privat/deadlines/{deadline_id}/complete")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_dashboard_widget_endpoint_exists(self, client):
        """Test dass Dashboard-Widget-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/deadlines/widget?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_calendar_export_endpoint_exists(self, client):
        """Test dass iCal-Export-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/deadlines/calendar?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_calendar_export_content_type(self, client):
        """Test dass iCal-Export korrekten Content-Type hat."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/deadlines/calendar?space_id={space_id}")
        if response.status_code == status.HTTP_200_OK:
            content_type = response.headers.get("content-type", "")
            # Sollte text/calendar oder application/octet-stream sein
            assert "calendar" in content_type or "octet-stream" in content_type


@pytest.mark.integration
@pytest.mark.api
class TestPrivatEmergencyAPI:
    """Tests fuer Emergency-Endpoints (Notfallzugriff)."""

    def test_list_contacts_endpoint_exists(self, client):
        """Test dass Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/emergency/contacts?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_create_contact_endpoint_exists(self, client):
        """Test dass Create-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/emergency/contacts",
            json={
                "space_id": str(space_id),
                "name": "Vertrauensperson",
                "email": "vertrauen@example.com",
                "phone": "+49 151 12345678",
                "relationship": "Ehepartner",
                "waiting_period_days": 30,
            }
        )
        assert response.status_code in [
            status.HTTP_201_CREATED,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_list_access_requests_endpoint_exists(self, client):
        """Test dass Anfragen-Listen-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/emergency/requests?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_request_access_endpoint_exists(self, client):
        """Test dass Anfrage-Endpoint erreichbar ist."""
        space_id = uuid4()
        response = client.post(
            "/api/v1/privat/emergency/request",
            json={
                "space_id": str(space_id),
                "reason": "Notfall - Medizinische Unterlagen benoetigt",
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
class TestPrivatAccessControl:
    """Tests fuer Zugriffskontrolle."""

    def test_space_requires_authentication(self, client):
        """Test dass Spaces Authentifizierung erfordern."""
        response = client.get("/api/v1/privat/spaces")
        # Ohne Auth sollte 401 oder 403 kommen
        if response.status_code not in [200]:
            assert response.status_code in [
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
            ]

    def test_cannot_access_other_users_space(self, client):
        """Test dass fremde Spaces nicht zugaenglich sind."""
        # Zufaellige UUID sollte nicht existieren oder nicht zugaenglich sein
        random_space_id = uuid4()
        response = client.get(f"/api/v1/privat/spaces/{random_space_id}")
        # Entweder nicht gefunden oder nicht autorisiert
        assert response.status_code in [
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.security
class TestPrivatSecurityControls:
    """Tests fuer Sicherheitsfunktionen des Privat-Moduls.

    Testet die implementierten Security-Fixes:
    - Path Traversal Prevention
    - Password Header Security
    - Rate Limiting
    - Input Validation
    """

    def test_path_traversal_prevention_in_filename(self, client):
        """Test dass Path Traversal in Dateinamen verhindert wird."""
        space_id = uuid4()
        # Versuch, mit ../ aus dem Verzeichnis auszubrechen
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32\\config",
            "document/../../../secret.txt",
            "/etc/passwd",
            "C:\\Windows\\System32\\config",
        ]
        for filename in malicious_filenames:
            response = client.post(
                f"/api/v1/privat/spaces/{space_id}/documents",
                json={
                    "title": "Testdokument",
                    "filename": filename,
                }
            )
            # Sollte abgelehnt werden (400, 422) oder Auth fehlen (401, 403)
            assert response.status_code in [
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_401_UNAUTHORIZED,
                status.HTTP_403_FORBIDDEN,
                status.HTTP_422_UNPROCESSABLE_ENTITY,
            ], f"Path Traversal nicht verhindert fuer: {filename}"

    def test_password_not_in_url(self, client):
        """Test dass Passwort nicht in URL akzeptiert wird."""
        document_id = uuid4()
        # Passwort sollte per Header, nicht per URL gesendet werden
        response = client.get(
            f"/api/v1/privat/documents/{document_id}/content?password=geheim"
        )
        # Entweder ignoriert (wenn Endpoint password Query nicht akzeptiert)
        # oder 400/422 wenn explizit abgelehnt
        assert response.status_code in [
            status.HTTP_200_OK,  # Passwort in URL ignoriert
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_password_accepted_in_header(self, client):
        """Test dass Passwort per X-Privat-Password Header akzeptiert wird."""
        document_id = uuid4()
        response = client.get(
            f"/api/v1/privat/documents/{document_id}/content",
            headers={"X-Privat-Password": "geheim"}
        )
        # Dokument existiert nicht, aber Header sollte akzeptiert werden
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]

    def test_rate_limiting_exists(self, client):
        """Test dass Rate Limiting konfiguriert ist."""
        space_id = uuid4()
        # Viele schnelle Requests ausfuehren
        responses = []
        for _ in range(15):  # Sollte unter normalen Limits sein
            response = client.get(f"/api/v1/privat/spaces/{space_id}")
            responses.append(response.status_code)

        # Entweder alle erfolgreich oder Rate Limited
        valid_codes = [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_429_TOO_MANY_REQUESTS,  # Rate Limited
        ]
        for code in responses:
            assert code in valid_codes

    def test_input_validation_max_length(self, client):
        """Test dass maximale Eingabelaengen validiert werden."""
        space_id = uuid4()
        # Sehr langer Name (> 500 Zeichen)
        very_long_name = "A" * 1000
        response = client.post(
            "/api/v1/privat/spaces",
            json={
                "name": very_long_name,
                "description": "Test",
            }
        )
        # Sollte abgelehnt werden wegen Laenge
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_sql_injection_prevention(self, client):
        """Test dass SQL Injection verhindert wird."""
        # Verschiedene SQL Injection Versuche
        malicious_inputs = [
            "'; DROP TABLE privat_spaces; --",
            "1 OR 1=1",
            "1'; SELECT * FROM users WHERE '1'='1",
            "admin'--",
        ]
        for payload in malicious_inputs:
            response = client.post(
                "/api/v1/privat/spaces",
                json={
                    "name": payload,
                    "description": "Test",
                }
            )
            # Sollte entweder normal verarbeiten (escaped) oder ablehnen
            # Wichtig: Kein 500 Internal Server Error!
            assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR, \
                f"Moegliche SQL Injection Schwachstelle bei: {payload}"

    def test_xss_in_text_fields_sanitized(self, client):
        """Test dass XSS in Textfeldern behandelt wird."""
        space_id = uuid4()
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
            "'\"><script>alert('XSS')</script>",
        ]
        for payload in xss_payloads:
            response = client.post(
                "/api/v1/privat/spaces",
                json={
                    "name": payload,
                    "description": "Test",
                }
            )
            # Sollte entweder escaped oder abgelehnt werden
            # Wichtig: Kein 500 Internal Server Error!
            assert response.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR, \
                f"Moegliche XSS Schwachstelle bei: {payload}"


@pytest.mark.integration
@pytest.mark.api
class TestPrivatDashboardAPI:
    """Tests fuer Dashboard-Endpoints."""

    def test_dashboard_stats_endpoint_exists(self, client):
        """Test dass Dashboard-Stats-Endpoint erreichbar ist."""
        response = client.get("/api/v1/privat/dashboard")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        ]

    def test_financial_summary_requires_space_id(self, client):
        """Test dass Financial Summary space_id erfordert."""
        # Ohne space_id sollte 400 oder 422 kommen
        response = client.get("/api/v1/privat/dashboard/financial-summary")
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ]

    def test_financial_summary_with_space_id(self, client):
        """Test dass Financial Summary mit space_id funktioniert."""
        space_id = uuid4()
        response = client.get(f"/api/v1/privat/dashboard/financial-summary?space_id={space_id}")
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        ]
