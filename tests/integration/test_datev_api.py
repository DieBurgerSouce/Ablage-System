# -*- coding: utf-8 -*-
"""
Integration Tests fuer DATEV API Endpoints.

Testet die vollstaendige API-Integration inkl. Authentication,
Request-Validation und Response-Format.

W3b (2026-06-12): Komplett auf echte Vertraege modernisiert.
- ``patch('app.api.dependencies.get_current_active_user')`` wirkt NICHT auf
  FastAPI-``Depends``-Referenzen (beim Import gebunden) -> alle Requests
  liefen als 401 durch. Korrektes Muster: ``app.dependency_overrides``
  (siehe test_tunes_upload_flow).
- Rate-Limiter wird via Settings-Override fail-open gestellt (lokal ohne
  Redis maskiert der fail-closed Limiter sonst alles als 503, W3-Triage).
- CSRF: ``mock_auth_headers`` enthaelt einen Dummy-Bearer-Header ->
  bearer_token_bypass der CSRF-Middleware greift fuer POST/PUT/DELETE.
"""

import uuid
from datetime import date, datetime, timezone
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


def _error_message(response) -> str:
    """Fehlertext aus der einheitlichen deutschen Fehler-Response lesen.

    register_exception_handlers formt HTTPException(detail=...) in
    {"fehler", "nachricht", "status_code", ...} um -- das alte
    ``response.json()["detail"]`` existiert dort nicht mehr.
    """
    body = response.json()
    return str(body.get("nachricht") or body.get("detail") or "")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def _rate_limiter_fail_open(monkeypatch):
    """Rate-Limiter lokal fail-open stellen (W3-Triage-Rezept).

    Ohne erreichbares Redis antwortet der fail-closed Rate-Limiter sonst
    pauschal mit 503 und maskiert die echte Endpoint-Antwort. Die Settings
    werden zur Request-Zeit gelesen, daher reicht ein Attribut-Override
    auf dem Settings-Singleton.
    """
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "RATE_LIMIT_FAIL_CLOSED", False)
    monkeypatch.setattr(app_settings, "RATE_LIMIT_FAIL_CLOSED_CRITICAL", False)


@pytest.fixture
def mock_user():
    """Aktiver Standard-Benutzer fuer Auth-Overrides."""
    user = MagicMock()
    user.id = uuid.uuid4()
    user.email = "datev-test@ablage.de"
    user.is_active = True
    user.is_superuser = False
    return user


@pytest.fixture
def mock_db_session():
    """Gemockte AsyncSession mit sinnvollen Defaults.

    - ``execute`` liefert ein Result, dessen ``scalar_one_or_none`` None
      (kein Treffer), ``scalars().all()`` [] und ``scalar()`` 0 zurueckgibt.
    - ``refresh`` setzt created_at/updated_at, wie es die DB-Server-Defaults
      nach einem echten INSERT taeten (sonst scheitert
      ``DATEVConfigurationResponse.model_validate``).
    """
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = None
    exec_result.scalars.return_value.all.return_value = []
    exec_result.scalar.return_value = 0
    session.execute = AsyncMock(return_value=exec_result)
    session.add = MagicMock()

    async def _refresh(obj, *args, **kwargs):
        now = datetime.now(timezone.utc)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = now

    session.refresh = AsyncMock(side_effect=_refresh)
    # Komfort-Zugriff fuer Tests, die den Query-Treffer umstellen wollen
    session.exec_result = exec_result
    return session


@pytest.fixture
def auth_overrides(mock_user, mock_db_session):
    """Auth-, DB- und Export-Rate-Limit-Dependencies ueberschreiben.

    WICHTIG: ``app.dependency_overrides`` statt ``patch()`` -- die Router
    binden die Funktionsobjekte beim Import, Modul-Patches greifen nicht.
    ``get_db_session`` ist identisch mit ``get_db``/``get_async_db``
    (Alias in app/db/database.py), ein Key deckt alle Drei ab.
    """
    from app.api import dependencies
    from app.db.database import get_db_session
    from app.main import app

    async def _db_override():
        yield mock_db_session

    app.dependency_overrides[dependencies.get_current_active_user] = (
        lambda: mock_user
    )
    app.dependency_overrides[dependencies.check_datev_export_rate_limit] = (
        lambda: mock_user
    )
    app.dependency_overrides[get_db_session] = _db_override
    try:
        yield mock_user
    finally:
        app.dependency_overrides.pop(
            dependencies.get_current_active_user, None
        )
        app.dependency_overrides.pop(
            dependencies.check_datev_export_rate_limit, None
        )
        app.dependency_overrides.pop(get_db_session, None)


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
def valid_export_request_data() -> Dict[str, Any]:
    """Gueltige Daten fuer Export-Request."""
    return {
        "period_from": "2025-01-01",
        "period_to": "2025-12-31",
        "include_already_exported": False,
    }


@pytest.fixture
def mock_auth_headers() -> Dict[str, str]:
    """Dummy-Bearer-Header: aktiviert den CSRF-bearer_token_bypass.

    Die eigentliche Authentifizierung laeuft ueber dependency_overrides;
    der Header dient nur dazu, dass die CSRF-Middleware mutierende
    Requests nicht mit 403 blockt.
    """
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
        self,
        async_client: AsyncClient,
        auth_overrides,
        valid_config_create_data,
        mock_auth_headers,
    ):
        """POST /config gibt 201 mit erstellter Konfiguration zurueck."""
        response = await async_client.post(
            "/api/v1/datev/config",
            json=valid_config_create_data,
            headers=mock_auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["berater_nr"] == "1234567"
        assert data["mandanten_nr"] == "12345"
        assert data["kontenrahmen"] == "SKR03"
        assert data["is_default"] is True
        uuid.UUID(data["id"])  # valide UUID

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_config_validates_berater_nr_format(
        self,
        async_client: AsyncClient,
        auth_overrides,
        valid_config_create_data,
        mock_auth_headers,
    ):
        """berater_nr muss aus Ziffern bestehen -> 422."""
        invalid_data = valid_config_create_data.copy()
        invalid_data["berater_nr"] = "ABC1234"  # Buchstaben nicht erlaubt

        response = await async_client.post(
            "/api/v1/datev/config",
            json=invalid_data,
            headers=mock_auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_config_validates_kontenrahmen_enum(
        self,
        async_client: AsyncClient,
        auth_overrides,
        valid_config_create_data,
        mock_auth_headers,
    ):
        """kontenrahmen muss SKR03 oder SKR04 sein -> 422."""
        invalid_data = valid_config_create_data.copy()
        invalid_data["kontenrahmen"] = "INVALID"

        response = await async_client.post(
            "/api/v1/datev/config",
            json=invalid_data,
            headers=mock_auth_headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_get_configs_requires_authentication(
        self, async_client: AsyncClient
    ):
        """GET /config ohne Auth -> 401/403 (Repo-Konvention: 403 bei
        fehlendem Header, HTTPBearer auto_error; Nutzer-Entscheidung W3)."""
        response = await async_client.get("/api/v1/datev/config")

        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_config_returns_204(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_db_session,
        mock_auth_headers,
    ):
        """DELETE /config/{id} gibt 204 No Content zurueck (Soft-Delete)."""
        config_id = uuid.uuid4()
        existing_config = MagicMock()
        existing_config.is_active = True
        mock_db_session.exec_result.scalar_one_or_none.return_value = (
            existing_config
        )

        response = await async_client.delete(
            f"/api/v1/datev/config/{config_id}",
            headers=mock_auth_headers,
        )

        assert response.status_code == 204
        assert existing_config.is_active is False  # Soft-Delete

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_unknown_config_returns_404(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_auth_headers,
    ):
        """DELETE auf fremde/unbekannte Konfiguration -> 404."""
        response = await async_client.delete(
            f"/api/v1/datev/config/{uuid.uuid4()}",
            headers=mock_auth_headers,
        )

        assert response.status_code == 404
        assert "nicht gefunden" in _error_message(response).lower()


# =============================================================================
# VENDOR MAPPING ENDPOINT TESTS
# =============================================================================

class TestDATEVVendorMappingAPI:
    """Tests fuer /api/v1/datev/config/{id}/vendors Endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_vendor_mapping_requires_identifier(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_db_session,
        mock_auth_headers,
    ):
        """Vendor-Mapping ohne Identifikationsmerkmal -> 400."""
        config_id = uuid.uuid4()
        # Config existiert (sonst greift der 404-Ownership-Check zuerst)
        mock_db_session.exec_result.scalar_one_or_none.return_value = (
            MagicMock()
        )
        invalid_data = {
            "expense_account": "3200",
            # Kein vendor_name, vendor_vat_id, vendor_iban, business_entity_id
        }

        response = await async_client.post(
            f"/api/v1/datev/config/{config_id}/vendors",
            json=invalid_data,
            headers=mock_auth_headers,
        )

        assert response.status_code == 400
        assert "Identifikationsmerkmal" in _error_message(response)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_vendor_mapping_validates_ownership(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_auth_headers,
    ):
        """DELETE Vendor-Mapping: fremde Config -> 404 (Ownership-Check)."""
        config_id = uuid.uuid4()
        mapping_id = uuid.uuid4()

        response = await async_client.delete(
            f"/api/v1/datev/config/{config_id}/vendors/{mapping_id}",
            headers=mock_auth_headers,
        )

        assert response.status_code == 404
        assert "nicht gefunden" in _error_message(response).lower()


# =============================================================================
# EXPORT ENDPOINT TESTS
# =============================================================================

class TestDATEVExportAPI:
    """Tests fuer /api/v1/datev/export Endpoints."""

    @pytest.mark.integration
    @pytest.mark.xfail(
        strict=True,
        reason=(
            "ECHTE LUECKE (W3b, 2026-06-12): DATEVExportRequest hat KEINEN "
            "Validator fuer period_to >= period_from; auch Handler/Service "
            "pruefen den Zeitraum nicht (nur steuerberater_package_service "
            "tut das). Ein invertierter Zeitraum liefert still einen leeren "
            "Export statt 400/422. Fix gehoert in app/api/schemas/datev.py "
            "(model_validator) -- danach xfail-Marker entfernen."
        ),
    )
    def test_export_preview_validates_date_range(self):
        """Export-Request muss invertierten Datumsbereich ablehnen."""
        from pydantic import ValidationError

        from app.api.schemas.datev import DATEVExportRequest

        with pytest.raises(ValidationError):
            DATEVExportRequest(
                period_from=date(2025, 12, 31),
                period_to=date(2025, 1, 1),
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_returns_csv_content_type(
        self,
        async_client: AsyncClient,
        auth_overrides,
        valid_export_request_data,
        mock_auth_headers,
    ):
        """Export gibt CSV mit korrektem Content-Type + Headern zurueck."""
        with patch("app.api.v1.datev.get_datev_export_service") as mock_service:
            # get_datev_export_service wird IM Handler aufgerufen ->
            # Modul-Patch greift hier (im Gegensatz zu Depends-Referenzen).
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

        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert response.headers["X-DATEV-Export-ID"] == str(export_record.id)
        assert response.headers["X-DATEV-Document-Count"] == "10"
        assert response.content == b"CSV-Content"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_error_does_not_leak_details(
        self,
        async_client: AsyncClient,
        auth_overrides,
        valid_export_request_data,
        mock_auth_headers,
    ):
        """Export-Fehler enthaelt keine sensiblen Details."""
        with patch("app.api.v1.datev.get_datev_export_service") as mock_service:
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
        body_text = response.text.lower()

        # Sensible Daten duerfen NIRGENDS in der Response auftauchen
        assert "password" not in body_text
        assert "secret" not in body_text
        assert "database error" not in body_text
        # Deutsche, generische Fehlermeldung
        assert "fehlgeschlagen" in _error_message(response).lower()


# =============================================================================
# EXPORT HISTORY TESTS
# =============================================================================

class TestDATEVExportHistoryAPI:
    """Tests fuer /api/v1/datev/export/history Endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_history_pagination(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_auth_headers,
    ):
        """Export-History unterstuetzt Pagination."""
        response = await async_client.get(
            "/api/v1/datev/export/history?page=1&page_size=10",
            headers=mock_auth_headers,
        )

        assert response.status_code == 200
        response_json = response.json()
        assert response_json["items"] == []
        assert response_json["total"] == 0
        assert response_json["page"] == 1
        assert response_json["page_size"] == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_export_history_validates_page_size(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_auth_headers,
    ):
        """Export-History validiert page_size (max 100) -> 422."""
        response = await async_client.get(
            "/api/v1/datev/export/history?page=1&page_size=500",  # zu gross
            headers=mock_auth_headers,
        )

        assert response.status_code == 422


# =============================================================================
# KONTENRAHMEN INFO TESTS
# =============================================================================

class TestDATEVKontenrahmenAPI:
    """Tests fuer /api/v1/datev/kontenrahmen Endpoint."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_kontenrahmen_info_returns_both_frameworks(
        self, async_client: AsyncClient, auth_overrides
    ):
        """Kontenrahmen-Info gibt SKR03 und SKR04 zurueck."""
        response = await async_client.get("/api/v1/datev/kontenrahmen")

        assert response.status_code == 200
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
        self, async_client: AsyncClient, auth_overrides
    ):
        """Kontenrahmen enthaelt alle erforderlichen Standardkonten."""
        response = await async_client.get("/api/v1/datev/kontenrahmen")

        assert response.status_code == 200
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
                assert account in standard_konten, (
                    f"{account} fehlt in {item['name']}"
                )


# =============================================================================
# RESPONSE FORMAT TESTS
# =============================================================================

class TestDATEVResponseFormats:
    """Tests fuer konsistente Response-Formate."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_error_responses_are_in_german(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_auth_headers,
    ):
        """Fehlermeldungen sind auf Deutsch."""
        # Nicht existierende Config
        config_id = uuid.uuid4()

        response = await async_client.get(
            f"/api/v1/datev/config/{config_id}",
            headers=mock_auth_headers,
        )

        assert response.status_code == 404
        assert "nicht gefunden" in _error_message(response).lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_uuid_format_in_responses(
        self,
        async_client: AsyncClient,
        auth_overrides,
        mock_auth_headers,
    ):
        """GET /config liefert eine Liste; IDs sind valide UUIDs."""
        response = await async_client.get(
            "/api/v1/datev/config",
            headers=mock_auth_headers,
        )

        assert response.status_code == 200
        response_json = response.json()
        assert isinstance(response_json, list)
        for config in response_json:
            if "id" in config:
                # Sollte ohne Exception parsen
                uuid.UUID(config["id"])
