# -*- coding: utf-8 -*-
"""
Integration Tests for DATEV Connect API.

Tests the full DATEVconnect API integration including:
- Connection management with OAuth2
- Sync operations
- Buchungen with GoBD compliance
- ML-based Kontierungsvorschlaege

Feinpoliert und durchdacht - Enterprise-Grade Testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def datev_connection_data():
    """Sample DATEV connection creation data."""
    return {
        "name": "Test-Verbindung",
        "mandant_nr": "12345",
        "berater_nr": "67890",
        "kontenrahmen": "SKR03",
        "wirtschaftsjahr_beginn": 1,
        "auto_kontierung": False,
        "auto_beleg_upload": True,
    }


@pytest.fixture
def mock_datev_oauth_response():
    """Mock OAuth2 response from DATEV."""
    return {
        "access_token": "test_access_token_123",
        "refresh_token": "test_refresh_token_456",
        "token_type": "Bearer",
        "expires_in": 3600,
    }


@pytest.fixture
def buchung_data():
    """Sample Buchung creation data."""
    return {
        "document_id": str(uuid4()),
        "konto_soll": "4400",
        "konto_haben": "70000",
        "betrag": 1250.00,
        "belegdatum": "2026-01-15",
        "buchungstext": "Wareneinkauf Amazon",
        "steuerschluessel": "19",
        "kostenstelle": "K100",
    }


@pytest.fixture
def kontierung_pattern_data():
    """Sample Kontierungsmuster data."""
    return {
        "lieferant_name": "Amazon EU S.a.r.l.",
        "lieferant_steuernr": "LU12345678",
        "konto_soll": "4400",
        "konto_haben": "70000",
        "steuerschluessel": "19",
        "betrag_von": 0,
        "betrag_bis": 10000,
        "confidence": 0.95,
    }


# =============================================================================
# CONNECTION MANAGEMENT TESTS
# =============================================================================

class TestDATEVConnectionManagement:
    """Tests for DATEV connection CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_connection_success(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test successful DATEV connection creation."""
        response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == datev_connection_data["name"]
        assert data["mandant_nr"] == datev_connection_data["mandant_nr"]
        assert data["berater_nr"] == datev_connection_data["berater_nr"]
        assert data["kontenrahmen"] == "SKR03"
        assert data["status"] == "pending"  # Not yet connected via OAuth2

    @pytest.mark.asyncio
    async def test_create_connection_invalid_kontenrahmen(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test connection creation with invalid Kontenrahmen."""
        datev_connection_data["kontenrahmen"] = "INVALID"

        response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_create_connection_invalid_mandant_nr(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test connection creation with invalid Mandantennummer."""
        datev_connection_data["mandant_nr"] = "abc"  # Must be numeric

        response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_connections(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test listing all DATEV connections."""
        response = await async_client.get(
            "/api/v1/datev-connect/connections",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_connection_not_found(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test getting non-existent connection."""
        fake_id = str(uuid4())

        response = await async_client.get(
            f"/api/v1/datev-connect/connections/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_connection_partial(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test partial update of DATEV connection."""
        # First create a connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Update only auto_kontierung
        response = await async_client.patch(
            f"/api/v1/datev-connect/connections/{connection_id}",
            json={"auto_kontierung": True},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["auto_kontierung"] is True

    @pytest.mark.asyncio
    async def test_delete_connection(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test deleting a DATEV connection."""
        # First create a connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Delete it
        response = await async_client.delete(
            f"/api/v1/datev-connect/connections/{connection_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(
            f"/api/v1/datev-connect/connections/{connection_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404


# =============================================================================
# OAUTH2 FLOW TESTS
# =============================================================================

class TestDATEVOAuth2Flow:
    """Tests for DATEV OAuth2 authentication flow."""

    @pytest.mark.asyncio
    async def test_get_authorization_url(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test generating OAuth2 authorization URL."""
        # Create connection first
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Get authorization URL
        response = await async_client.get(
            f"/api/v1/datev-connect/connections/{connection_id}/oauth2/authorize",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "authorization_url" in data
        assert "state" in data
        assert "datev" in data["authorization_url"].lower()

    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_state(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test OAuth2 callback with invalid state (CSRF protection)."""
        # Create connection first
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Try callback with invalid state
        response = await async_client.post(
            f"/api/v1/datev-connect/connections/{connection_id}/oauth2/callback",
            json={"code": "test_code", "state": "invalid_state"},
            headers=auth_headers,
        )

        assert response.status_code == 400  # Invalid CSRF state

    @pytest.mark.asyncio
    @patch("app.services.datev.connect.datev_auth_service.DATEVAuthService.exchange_code_for_tokens")
    async def test_oauth_callback_success(
        self,
        mock_exchange: AsyncMock,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
        mock_datev_oauth_response: dict,
    ):
        """Test successful OAuth2 callback."""
        mock_exchange.return_value = mock_datev_oauth_response

        # Create connection and get auth URL to generate state
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        auth_response = await async_client.get(
            f"/api/v1/datev-connect/connections/{connection_id}/oauth2/authorize",
            headers=auth_headers,
        )
        state = auth_response.json()["state"]

        # Now do the callback with valid state
        response = await async_client.post(
            f"/api/v1/datev-connect/connections/{connection_id}/oauth2/callback",
            json={"code": "valid_code", "state": state},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"

    @pytest.mark.asyncio
    async def test_revoke_connection(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test revoking OAuth2 connection."""
        # Create and "connect" (mock)
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Revoke
        response = await async_client.post(
            f"/api/v1/datev-connect/connections/{connection_id}/oauth2/revoke",
            headers=auth_headers,
        )

        assert response.status_code == 200


# =============================================================================
# BUCHUNGEN TESTS
# =============================================================================

class TestDATEVBuchungen:
    """Tests for DATEV Buchungen management."""

    @pytest.mark.asyncio
    async def test_create_buchung(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
        buchung_data: dict,
    ):
        """Test creating a new Buchung."""
        # Create connection first
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Create Buchung
        response = await async_client.post(
            f"/api/v1/datev-connect/buchungen/{connection_id}",
            json=buchung_data,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["konto_soll"] == buchung_data["konto_soll"]
        assert data["konto_haben"] == buchung_data["konto_haben"]
        assert data["ist_festgeschrieben"] is False

    @pytest.mark.asyncio
    async def test_list_buchungen_with_filter(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test listing Buchungen with filter."""
        # Create connection first
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # List with filter
        response = await async_client.get(
            f"/api/v1/datev-connect/buchungen/{connection_id}",
            params={"festgeschrieben": False, "page_size": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data


# =============================================================================
# GOBD COMPLIANCE TESTS
# =============================================================================

class TestGoBDCompliance:
    """Tests for GoBD compliance features."""

    @pytest.mark.asyncio
    async def test_festschreiben_buchungen(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
        buchung_data: dict,
    ):
        """Test Festschreibung of Buchungen."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Create Buchung
        buchung_response = await async_client.post(
            f"/api/v1/datev-connect/buchungen/{connection_id}",
            json=buchung_data,
            headers=auth_headers,
        )
        buchung_id = buchung_response.json()["id"]

        # Festschreiben
        response = await async_client.post(
            f"/api/v1/datev-connect/gobd/{connection_id}/festschreiben",
            json={"buchung_ids": [buchung_id]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["festgeschrieben_count"] == 1
        assert buchung_id in data["buchung_ids"]
        assert "festschreibung_timestamp" in data

    @pytest.mark.asyncio
    async def test_festschreiben_all_pending(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test Festschreibung of all pending Buchungen."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Festschreiben all
        response = await async_client.post(
            f"/api/v1/datev-connect/gobd/{connection_id}/festschreiben",
            json={"all_pending": True},
            headers=auth_headers,
        )

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_compliance_report(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test GoBD compliance report."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Get report
        response = await async_client.get(
            f"/api/v1/datev-connect/gobd/{connection_id}/report",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_buchungen" in data
        assert "festgeschrieben_count" in data
        assert "integrity_check" in data

    @pytest.mark.asyncio
    async def test_verify_buchung_integrity(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
        buchung_data: dict,
    ):
        """Test Buchung integrity verification."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Create and festschreiben Buchung
        buchung_response = await async_client.post(
            f"/api/v1/datev-connect/buchungen/{connection_id}",
            json=buchung_data,
            headers=auth_headers,
        )
        buchung_id = buchung_response.json()["id"]

        await async_client.post(
            f"/api/v1/datev-connect/gobd/{connection_id}/festschreiben",
            json={"buchung_ids": [buchung_id]},
            headers=auth_headers,
        )

        # Verify integrity
        response = await async_client.get(
            f"/api/v1/datev-connect/gobd/{connection_id}/verify/{buchung_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


# =============================================================================
# KONTIERUNG (ML) TESTS
# =============================================================================

class TestKontierungsvorschlaege:
    """Tests for ML-based Kontierungsvorschlaege."""

    @pytest.mark.asyncio
    async def test_get_kontierungsvorschlag(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test getting Kontierungsvorschlag for document."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        document_id = str(uuid4())

        # Get suggestion (may return empty if no patterns)
        response = await async_client.get(
            f"/api/v1/datev-connect/kontierung/{connection_id}/suggest/{document_id}",
            headers=auth_headers,
        )

        # Either success with suggestion or 404 (no pattern match)
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_learn_kontierungsmuster(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
        kontierung_pattern_data: dict,
    ):
        """Test learning new Kontierungsmuster."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Learn pattern
        learn_data = {
            "document_id": str(uuid4()),
            "lieferant_name": kontierung_pattern_data["lieferant_name"],
            "konto_soll": kontierung_pattern_data["konto_soll"],
            "konto_haben": kontierung_pattern_data["konto_haben"],
            "steuerschluessel": kontierung_pattern_data["steuerschluessel"],
        }

        response = await async_client.post(
            f"/api/v1/datev-connect/kontierung/{connection_id}/learn",
            json=learn_data,
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "pattern_id" in data
        assert "message" in data


# =============================================================================
# SYNC TESTS
# =============================================================================

class TestDATEVSync:
    """Tests for DATEV synchronization."""

    @pytest.mark.asyncio
    async def test_get_sync_status(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test getting sync status."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Get status
        response = await async_client.get(
            f"/api/v1/datev-connect/sync/{connection_id}/status",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "last_sync" in data
        assert "pending_items" in data

    @pytest.mark.asyncio
    async def test_trigger_sync(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test triggering manual sync."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Trigger sync
        response = await async_client.post(
            f"/api/v1/datev-connect/sync/{connection_id}/trigger",
            json={"sync_types": ["stammdaten", "kontenplan"]},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "task_ids" in data

    @pytest.mark.asyncio
    async def test_sync_history(
        self, async_client: AsyncClient, auth_headers: dict, datev_connection_data: dict
    ):
        """Test getting sync history."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Get history
        response = await async_client.get(
            f"/api/v1/datev-connect/sync/{connection_id}/history",
            params={"page_size": 10},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data


# =============================================================================
# SECURITY TESTS
# =============================================================================

class TestDATEVConnectSecurity:
    """Security tests for DATEV Connect API."""

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, async_client: AsyncClient):
        """Test that endpoints require authentication.

        Nutzer-Entscheidung (2026-06-11, W3): Bei fehlender Authentifizierung
        antwortet das Backend mit 403 (FastAPI-HTTPBearer auto_error-Default).
        Diese Konvention BLEIBT bestehen - der Test wurde von 401 auf 403
        angepasst statt das Backend umzustellen.
        """
        response = await async_client.get("/api/v1/datev-connect/connections")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_cross_company_access_denied(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        other_company_auth_headers: dict,
        datev_connection_data: dict,
    ):
        """Test that connections are isolated per company."""
        # Create connection with company A
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Try to access with company B
        response = await async_client.get(
            f"/api/v1/datev-connect/connections/{connection_id}",
            headers=other_company_auth_headers,
        )

        assert response.status_code == 404  # Not found for other company

    @pytest.mark.asyncio
    async def test_sql_injection_prevention(
        self, async_client: AsyncClient, auth_headers: dict
    ):
        """Test SQL injection prevention in connection ID."""
        malicious_id = "'; DROP TABLE datev_connections; --"

        response = await async_client.get(
            f"/api/v1/datev-connect/connections/{malicious_id}",
            headers=auth_headers,
        )

        # Should be 422 (invalid UUID) not 500
        assert response.status_code in [404, 422]

    @pytest.mark.asyncio
    async def test_xss_prevention_in_buchungstext(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
        buchung_data: dict,
    ):
        """Test XSS prevention in Buchungstext."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Try XSS in buchungstext
        buchung_data["buchungstext"] = "<script>alert('xss')</script>"

        response = await async_client.post(
            f"/api/v1/datev-connect/buchungen/{connection_id}",
            json=buchung_data,
            headers=auth_headers,
        )

        if response.status_code == 201:
            # Should be escaped if stored
            data = response.json()
            assert "<script>" not in data["buchungstext"]


# =============================================================================
# MULTI-TENANT TESTS
# =============================================================================

class TestDATEVMultiTenant:
    """Multi-tenant isolation tests."""

    @pytest.mark.asyncio
    async def test_connection_company_isolation(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        auth_headers_company_b: dict,
        datev_connection_data: dict,
    ):
        """Test that connections are isolated between companies."""
        # Create for company A
        await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )

        # Create for company B
        datev_connection_data["name"] = "Company B Connection"
        await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers_company_b,
        )

        # List for company A - should only see A's connection
        response_a = await async_client.get(
            "/api/v1/datev-connect/connections",
            headers=auth_headers,
        )

        # List for company B - should only see B's connection
        response_b = await async_client.get(
            "/api/v1/datev-connect/connections",
            headers=auth_headers_company_b,
        )

        assert len(response_a.json()) != len(response_b.json()) or \
               all(c["name"] != "Company B Connection" for c in response_a.json())


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestDATEVConnectPerformance:
    """Performance tests for DATEV Connect API."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_bulk_buchungen_creation(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
    ):
        """Test performance of bulk Buchungen creation."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Create 50 Buchungen
        import time
        start = time.time()

        for i in range(50):
            buchung = {
                "document_id": str(uuid4()),
                "konto_soll": "4400",
                "konto_haben": "70000",
                "betrag": 100.00 + i,
                "belegdatum": f"2026-01-{(i % 28) + 1:02d}",
                "buchungstext": f"Test Buchung {i}",
            }

            response = await async_client.post(
                f"/api/v1/datev-connect/buchungen/{connection_id}",
                json=buchung,
                headers=auth_headers,
            )
            assert response.status_code == 201

        elapsed = time.time() - start

        # Should complete within 30 seconds
        assert elapsed < 30, f"Bulk creation took {elapsed:.2f}s, expected < 30s"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_festschreiben_performance(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        datev_connection_data: dict,
    ):
        """Test performance of Festschreiben operation."""
        # Create connection
        create_response = await async_client.post(
            "/api/v1/datev-connect/connections",
            json=datev_connection_data,
            headers=auth_headers,
        )
        connection_id = create_response.json()["id"]

        # Create 20 Buchungen
        buchung_ids = []
        for i in range(20):
            buchung = {
                "document_id": str(uuid4()),
                "konto_soll": "4400",
                "konto_haben": "70000",
                "betrag": 100.00 + i,
                "belegdatum": "2026-01-15",
                "buchungstext": f"Test Buchung {i}",
            }

            response = await async_client.post(
                f"/api/v1/datev-connect/buchungen/{connection_id}",
                json=buchung,
                headers=auth_headers,
            )
            buchung_ids.append(response.json()["id"])

        # Festschreiben all
        import time
        start = time.time()

        response = await async_client.post(
            f"/api/v1/datev-connect/gobd/{connection_id}/festschreiben",
            json={"buchung_ids": buchung_ids},
            headers=auth_headers,
        )

        elapsed = time.time() - start

        assert response.status_code == 200
        assert elapsed < 5, f"Festschreiben took {elapsed:.2f}s, expected < 5s"
