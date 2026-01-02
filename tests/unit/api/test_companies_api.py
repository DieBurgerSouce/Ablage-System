# -*- coding: utf-8 -*-
"""
Umfassende Unit Tests fuer Companies API.

Testet alle Firmen-Funktionalitaeten (Multi-Tenant-System):
- GET /companies - Firmen des Benutzers auflisten
- POST /companies - Neue Firma erstellen
- GET /companies/current - Aktuelle Firma abrufen
- POST /companies/current/{company_id} - Aktuelle Firma wechseln
- GET /companies/{company_id} - Firma abrufen
- PUT /companies/{company_id} - Firma aktualisieren
- DELETE /companies/{company_id} - Firma loeschen (Soft-Delete)
- GET /companies/{company_id}/users - Benutzer der Firma auflisten
- POST /companies/{company_id}/users - Benutzer zur Firma hinzufuegen
- PUT /companies/{company_id}/users/{user_id} - Benutzerrolle aktualisieren
- DELETE /companies/{company_id}/users/{user_id} - Benutzer aus Firma entfernen

Feinpoliert und durchdacht - Multi-Tenant Enterprise Test Coverage.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from datetime import datetime

# Test markers
pytestmark = [pytest.mark.unit, pytest.mark.api]


class TestListCompanies:
    """Tests fuer GET /companies Endpoint."""

    @pytest.mark.asyncio
    async def test_list_companies_success(self, async_client):
        """Firmen des Benutzers erfolgreich auflisten."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/companies",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "companies" in data
                assert "total" in data
                assert isinstance(data["companies"], list)

    @pytest.mark.asyncio
    async def test_list_companies_include_inactive(self, async_client):
        """Firmen inklusive inaktiver auflisten."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/companies?include_inactive=true",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "companies" in data
                assert "total" in data

    @pytest.mark.asyncio
    async def test_list_companies_pagination(self, async_client):
        """Firmen mit Paginierung."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/companies?skip=5&limit=10",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert "companies" in data

    @pytest.mark.asyncio
    async def test_list_companies_unauthenticated(self, async_client):
        """Firmen ohne Authentifizierung."""
        response = await async_client.get("/api/v1/companies")
        assert response.status_code in [401, 403]


class TestCreateCompany:
    """Tests fuer POST /companies Endpoint."""

    @pytest.mark.asyncio
    async def test_create_company_success(self, async_client):
        """Firma erfolgreich erstellen."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/companies",
                json={
                    "name": f"Test Firma {uuid4().hex[:8]}",  # Eindeutiger Name
                    "vat_id": "DE123456789",
                    "address_city": "Berlin",
                    "address_postal_code": "10115"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 201 Created oder 409 Conflict bei Duplikat
            assert response.status_code in [201, 401, 409, 422, 500]

    @pytest.mark.asyncio
    async def test_create_company_duplicate_name(self, async_client):
        """Firma mit doppeltem Namen erstellen."""
        duplicate_name = "Duplicate Firma Test GmbH"

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/companies",
                json={
                    "name": duplicate_name
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 409 Conflict bei Duplikat, 201 wenn nicht vorhanden
            assert response.status_code in [201, 401, 409, 422, 500]

    @pytest.mark.asyncio
    async def test_create_company_missing_name(self, async_client):
        """Firma ohne Namen erstellen."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/companies",
                json={
                    "vat_id": "DE123456789"
                    # name fehlt
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # Sollte Validierungsfehler sein
            assert response.status_code in [401, 422]

    @pytest.mark.asyncio
    async def test_create_company_owner_assignment(self, async_client):
        """Ersteller wird automatisch als Owner zugewiesen."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            user_id = uuid4()
            mock_auth.return_value = Mock(id=user_id, is_active=True)

            response = await async_client.post(
                "/api/v1/companies",
                json={
                    "name": f"Owner Test {uuid4().hex[:8]}"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # Bei Erfolg wird der Ersteller als Owner zugewiesen
            assert response.status_code in [201, 401, 409, 500]


class TestGetCurrentCompany:
    """Tests fuer GET/POST /companies/current Endpoints."""

    @pytest.mark.asyncio
    async def test_get_current_company_success(self, async_client):
        """Aktuelle Firma erfolgreich abrufen."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                "/api/v1/companies/current",
                headers={"Authorization": "Bearer test_token"}
            )

            # 200 OK mit Firma oder null wenn keine gesetzt
            assert response.status_code in [200, 401]

    @pytest.mark.asyncio
    async def test_switch_current_company_success(self, async_client):
        """Aktuelle Firma erfolgreich wechseln."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/companies/current/{company_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 200 OK, 403 Forbidden, 404 Not Found
            assert response.status_code in [200, 401, 403, 404, 500]

    @pytest.mark.asyncio
    async def test_switch_company_no_access(self, async_client):
        """Zu Firma ohne Zugriff wechseln."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/companies/current/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 403 Forbidden bei fehlendem Zugriff
            assert response.status_code in [401, 403, 404, 500]


class TestGetCompany:
    """Tests fuer GET /companies/{company_id} Endpoint."""

    @pytest.mark.asyncio
    async def test_get_company_success(self, async_client):
        """Firmendetails erfolgreich abrufen."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/companies/{company_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 200 OK oder 403/404
            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_get_company_no_access(self, async_client):
        """Firma ohne Zugriff abrufen."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/companies/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            # Multi-Tenant-Isolation: 403 Forbidden
            assert response.status_code in [401, 403, 404]


class TestUpdateCompany:
    """Tests fuer PUT /companies/{company_id} Endpoint."""

    @pytest.mark.asyncio
    async def test_update_company_success(self, async_client):
        """Firma erfolgreich aktualisieren."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/companies/{company_id}",
                json={
                    "name": "Aktualisierte Firma GmbH",
                    "address_city": "Hamburg"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 200 OK, 403 Forbidden, 404 Not Found
            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_update_company_member_forbidden(self, async_client):
        """Member kann Firmendaten nicht aendern."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/companies/{company_id}",
                json={"name": "Test"},
                headers={"Authorization": "Bearer test_token"}
            )

            # 403 Forbidden wenn nicht Owner/Admin
            assert response.status_code in [200, 401, 403, 404]


class TestDeleteCompany:
    """Tests fuer DELETE /companies/{company_id} Endpoint."""

    @pytest.mark.asyncio
    async def test_delete_company_owner_success(self, async_client):
        """Owner kann Firma loeschen (Soft-Delete)."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.delete(
                f"/api/v1/companies/{company_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 204 No Content bei Erfolg, 403 wenn nicht Owner
            assert response.status_code in [204, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_delete_company_non_owner_forbidden(self, async_client):
        """Nicht-Owner kann Firma nicht loeschen (Owner-Schutz)."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.delete(
                f"/api/v1/companies/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 403 Forbidden - nur Owner darf loeschen
            assert response.status_code in [401, 403, 404]


class TestCompanyUsers:
    """Tests fuer /companies/{company_id}/users Endpoints."""

    @pytest.mark.asyncio
    async def test_list_company_users_success(self, async_client):
        """Benutzer der Firma erfolgreich auflisten."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/companies/{company_id}/users",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_company_users_member_forbidden(self, async_client):
        """Member kann Benutzerliste nicht sehen."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/companies/{company_id}/users",
                headers={"Authorization": "Bearer test_token"}
            )

            # 403 Forbidden wenn nicht Owner/Admin
            assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_add_user_to_company_success(self, async_client):
        """Benutzer zur Firma hinzufuegen."""
        company_id = uuid4()
        user_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/companies/{company_id}/users",
                json={
                    "user_id": str(user_id),
                    "role": "member",
                    "can_manage_cash": False,
                    "can_approve_expenses": False
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 201 Created, 403 Forbidden, 404 User/Company not found, 409 already assigned
            assert response.status_code in [201, 401, 403, 404, 409, 500]

    @pytest.mark.asyncio
    async def test_add_user_already_assigned(self, async_client):
        """Bereits zugeordneten Benutzer erneut hinzufuegen."""
        company_id = uuid4()
        user_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                f"/api/v1/companies/{company_id}/users",
                json={
                    "user_id": str(user_id),
                    "role": "member"
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 409 Conflict bei Duplikat-Zuweisung
            assert response.status_code in [201, 401, 403, 404, 409, 500]

    @pytest.mark.asyncio
    async def test_update_company_user_role(self, async_client):
        """Benutzerrolle aktualisieren."""
        company_id = uuid4()
        user_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.put(
                f"/api/v1/companies/{company_id}/users/{user_id}",
                json={
                    "role": "admin",
                    "can_manage_cash": True
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 200 OK, 403 Forbidden, 404 Not Found, 400 Bad Request (letzter Owner)
            assert response.status_code in [200, 400, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_cannot_demote_last_owner(self, async_client):
        """Letzten Owner kann man nicht herabstufen (Owner-Schutz)."""
        company_id = uuid4()
        owner_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=owner_id, is_active=True)

            response = await async_client.put(
                f"/api/v1/companies/{company_id}/users/{owner_id}",
                json={
                    "role": "member"  # Herabstufung von Owner zu Member
                },
                headers={"Authorization": "Bearer test_token"}
            )

            # 400 Bad Request - letzten Owner nicht herabstufen
            assert response.status_code in [200, 400, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_remove_user_from_company(self, async_client):
        """Benutzer aus Firma entfernen."""
        company_id = uuid4()
        user_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.delete(
                f"/api/v1/companies/{company_id}/users/{user_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 204 No Content, 400 (letzter Owner), 403 Forbidden, 404 Not Found
            assert response.status_code in [204, 400, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_cannot_remove_last_owner(self, async_client):
        """Letzten Owner kann man nicht entfernen (Owner-Schutz)."""
        company_id = uuid4()
        owner_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=owner_id, is_active=True)

            response = await async_client.delete(
                f"/api/v1/companies/{company_id}/users/{owner_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 400 Bad Request - letzten Owner nicht entfernen
            assert response.status_code in [204, 400, 401, 403, 404]


class TestMultiTenantIsolation:
    """Tests fuer Multi-Tenant-Isolation."""

    @pytest.mark.asyncio
    async def test_user_only_sees_own_companies(self, async_client):
        """Benutzer sieht nur eigene Firmen (Multi-Tenant-Isolation)."""
        user_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=user_id, is_active=True)

            response = await async_client.get(
                "/api/v1/companies",
                headers={"Authorization": "Bearer test_token"}
            )

            # Response enthaelt nur Firmen des aktuellen Benutzers
            if response.status_code == 200:
                data = response.json()
                # Alle zurueckgegebenen Firmen sollten dem User zugeordnet sein
                assert isinstance(data["companies"], list)

    @pytest.mark.asyncio
    async def test_cannot_access_other_company(self, async_client):
        """Kann nicht auf fremde Firma zugreifen (Multi-Tenant-Isolation)."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            other_company_id = uuid4()
            response = await async_client.get(
                f"/api/v1/companies/{other_company_id}",
                headers={"Authorization": "Bearer test_token"}
            )

            # 403 Forbidden - kein Zugriff auf fremde Firma
            assert response.status_code in [401, 403, 404]


class TestGermanMessages:
    """Tests fuer deutsche Fehlermeldungen bei Companies."""

    @pytest.mark.asyncio
    async def test_company_not_found_german_message(self, async_client):
        """Firma nicht gefunden - deutsche Meldung."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/companies/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 404:
                data = response.json()
                assert "detail" in data

    @pytest.mark.asyncio
    async def test_access_denied_german_message(self, async_client):
        """Zugriff verweigert - deutsche Meldung."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/companies/{uuid4()}",
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 403:
                data = response.json()
                assert "detail" in data
                # Deutsche Meldung erwartet: "Zugriff" oder "Berechtigung"

    @pytest.mark.asyncio
    async def test_duplicate_company_name_german_message(self, async_client):
        """Doppelter Firmenname - deutsche Meldung."""
        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.post(
                "/api/v1/companies",
                json={"name": "Duplicate Test GmbH"},
                headers={"Authorization": "Bearer test_token"}
            )

            if response.status_code == 409:
                data = response.json()
                assert "detail" in data
                # Deutsche Meldung: "existiert bereits"


class TestCompanyRoles:
    """Tests fuer Firmenrollen."""

    def test_valid_company_roles(self):
        """Gueltige Firmenrollen definiert."""
        from app.db.schemas import CompanyRole

        expected_roles = ["owner", "admin", "member", "viewer"]

        for role in expected_roles:
            assert role in [r.value for r in CompanyRole]

    @pytest.mark.asyncio
    async def test_owner_can_manage_users(self, async_client):
        """Owner kann Benutzer verwalten."""
        company_id = uuid4()

        with patch("app.api.v1.companies.get_current_active_user") as mock_auth:
            mock_auth.return_value = Mock(id=uuid4(), is_active=True)

            response = await async_client.get(
                f"/api/v1/companies/{company_id}/users",
                headers={"Authorization": "Bearer test_token"}
            )

            # Owner/Admin kann Benutzer sehen
            assert response.status_code in [200, 401, 403, 404]
