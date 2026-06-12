# -*- coding: utf-8 -*-
"""
Integration Tests fuer GoBD Archive API Endpoints.

Tests fuer das GoBD-konforme Archivierungssystem:
- Dokumentenarchivierung mit SHA-256 Signatur
- Integritaetspruefung
- Unveraenderbarkeitsschutz (Immutability)
- Aufbewahrungsfristen-Verwaltung
- Verfahrensdokumentation

W3b (2026-06-12): Komplett auf echte Vertraege modernisiert:
- Rate-Limiter fail-open via Settings-Override (W3-Triage: TestClient-IP
  'testclient' nicht whitelisted -> fail-closed maskierte alles als 503).
- Auth-Override-Ziel korrigiert: der Archive-Router bindet
  ``get_current_user`` (NICHT get_current_active_user); ueber die
  Dependency-Kette deckt das auch get_current_active_user/
  get_current_superuser fuer den documents-Router ab.
- ``require_company``-Override liefert ein Objekt mit ``.id`` (Handler
  nutzen ``company.id`` fuer IDOR-Checks), nicht die nackte UUID.
- Dummy-Bearer-Header -> CSRF-bearer_token_bypass fuer POST/PUT/PATCH.
- Service-Mocks an echte Response-Schemas angepasst (ArchiveResponse braucht
  archived_at; VerificationResponse braucht last_verification_at/
  verification_failed_reason; ProcedureDocVersionResponse hat version:str,
  generated_at, generated_by, content_hash).
- /archive/categories liefert {"categories": [{value, display_name, ...}]}
  (Inhalts-Drift gegen alten flachen Dict-Vertrag).
"""

import pytest
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock, MagicMock, patch

from pathlib import Path
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.main import app
from app.db.models import RetentionCategory


def _error_message(response) -> str:
    """Fehlertext aus der einheitlichen deutschen Fehler-Response lesen.

    register_exception_handlers formt HTTPException(detail=...) in
    {"fehler", "nachricht", "status_code", ...} um.
    """
    body = response.json()
    return str(body.get("nachricht") or body.get("detail") or "")


@pytest.fixture(autouse=True)
def _rate_limiter_fail_open(monkeypatch):
    """Rate-Limiter lokal fail-open stellen (W3-Triage-Rezept)."""
    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "RATE_LIMIT_FAIL_CLOSED", False)
    monkeypatch.setattr(app_settings, "RATE_LIMIT_FAIL_CLOSED_CRITICAL", False)


@pytest.fixture
def mock_user():
    """Create mock authenticated user."""
    user = Mock()
    user.id = uuid4()
    user.email = "testuser@ablage.de"
    user.username = "testuser"
    user.is_active = True
    user.is_superuser = False
    return user


@pytest.fixture
def mock_admin_user():
    """Create mock admin user."""
    user = Mock()
    user.id = uuid4()
    user.email = "admin@ablage.de"
    user.username = "admin"
    user.is_active = True
    user.is_superuser = True
    return user


@pytest.fixture
def mock_company():
    """Create mock company."""
    company = Mock()
    company.id = uuid4()
    company.name = "Test GmbH"
    company.short_name = "TEST"
    return company


@pytest.fixture
def mock_document(mock_company):
    """Create mock document."""
    doc = Mock()
    doc.id = uuid4()
    doc.company_id = mock_company.id
    doc.filename = "rechnung_2025_001.pdf"
    doc.original_filename = "Rechnung_2025_001.pdf"
    doc.mime_type = "application/pdf"
    doc.checksum = "abc123checksum456def"
    doc.extracted_text = "Rechnung Nr. 2025-001 Betrag: 1.234,56 EUR"
    doc.file_size = 54321
    doc.is_archived = False
    doc.archived_at = None
    doc.archive = None
    return doc


@pytest.fixture
def mock_archive(mock_document, mock_user):
    """Create mock archive (Felder gemaess ArchiveResponse-Schema)."""
    archive = Mock()
    archive.id = uuid4()
    archive.document_id = mock_document.id
    archive.company_id = mock_document.company_id
    archive.content_hash = "a" * 64  # SHA-256 hex
    archive.hash_algorithm = "SHA-256"
    archive.signature_timestamp = datetime.now(timezone.utc)
    archive.signature_certificate = None
    archive.retention_category = RetentionCategory.INVOICE.value
    archive.retention_years = 10
    archive.retention_expires_at = date.today() + timedelta(days=10 * 365)
    archive.archived_at = datetime.now(timezone.utc)
    archive.archived_by_id = mock_user.id
    archive.is_verified = True
    # VerificationResponse verlangt last_verification_at als datetime
    # (Pflichtfeld) und verification_failed_reason als Optional[str].
    archive.last_verification_at = datetime.now(timezone.utc)
    archive.verification_failed_reason = None
    archive.retention_reminder_sent = False
    archive.archive_metadata = {}
    return archive


def _make_db_session(document):
    """AsyncSession-Mock: direkte Document-Lookups liefern ``document``.

    Der POST /archive/documents-Handler macht VOR dem Service-Aufruf einen
    eigenen IDOR-Check via ``db.execute(select(Document)...)`` -- das Result
    muss ein synchrones ``scalar_one_or_none()`` haben.
    """
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = document
    exec_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=exec_result)
    return session


def _apply_overrides(user, company, document):
    """Dependency-Overrides setzen (Router bindet get_current_user!)."""
    from app.api.dependencies import get_current_user, get_db
    from app.middleware.company_context import require_company

    mock_db_session = _make_db_session(document)

    async def mock_get_db():
        yield mock_db_session

    async def mock_require_company():
        # Handler nutzen company.id -> Objekt mit .id, nicht die UUID
        return company

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_company] = mock_require_company


@pytest.fixture
def client(mock_user, mock_company, mock_document):
    """Test-Client (normaler User) mit Dependency-Overrides.

    Dummy-Bearer-Header -> CSRF-bearer_token_bypass fuer mutierende
    Requests; Auth kommt aus den Overrides.
    """
    _apply_overrides(mock_user, mock_company, mock_document)
    yield TestClient(app, headers={"Authorization": "Bearer test-token"})
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(mock_admin_user, mock_company, mock_document):
    """Test-Client fuer Admin-User (is_superuser=True -> Superuser-Kette)."""
    _apply_overrides(mock_admin_user, mock_company, mock_document)
    yield TestClient(app, headers={"Authorization": "Bearer test-token"})
    app.dependency_overrides.clear()


class TestArchiveDocumentEndpoint:
    """Tests fuer POST /api/v1/archive/documents"""

    def test_archive_document_success(self, client, mock_document, mock_archive):
        """Dokument erfolgreich archivieren."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.archive_document = AsyncMock(return_value=mock_archive)

            response = client.post(
                "/api/v1/archive/documents",
                json={
                    "document_id": str(mock_document.id),
                    "retention_category": "invoice",
                }
            )

            assert response.status_code == 201
            data = response.json()
            assert data["document_id"] == str(mock_document.id)
            assert data["content_hash"] == "a" * 64
            assert data["retention_category"] == "invoice"
            assert "retention_expires_at" in data

    def test_archive_document_not_found(self, client, mock_document):
        """Fehler wenn Dokument nicht existiert."""
        from app.core.exceptions import DocumentNotFoundError

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.archive_document = AsyncMock(
                side_effect=DocumentNotFoundError("Dokument nicht gefunden")
            )

            response = client.post(
                "/api/v1/archive/documents",
                json={
                    "document_id": str(mock_document.id),
                    "retention_category": "invoice",
                }
            )

            assert response.status_code == 404

    def test_archive_document_already_archived(self, client, mock_document):
        """Fehler wenn Dokument bereits archiviert."""
        from app.core.exceptions import ArchiveError

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.archive_document = AsyncMock(
                side_effect=ArchiveError("Dokument ist bereits archiviert")
            )

            response = client.post(
                "/api/v1/archive/documents",
                json={
                    "document_id": str(mock_document.id),
                    "retention_category": "invoice",
                }
            )

            assert response.status_code == 400


class TestGetArchiveEndpoint:
    """Tests fuer GET /api/v1/archive/documents/{document_id}"""

    def test_get_archive_success(self, client, mock_document, mock_archive):
        """Archiv-Informationen erfolgreich abrufen."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_archive = AsyncMock(return_value=mock_archive)

            response = client.get(
                f"/api/v1/archive/documents/{mock_document.id}"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["document_id"] == str(mock_document.id)
            assert "content_hash" in data
            assert "retention_expires_at" in data

    def test_get_archive_not_found(self, client):
        """404 wenn Dokument nicht archiviert."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_archive = AsyncMock(return_value=None)

            response = client.get(
                f"/api/v1/archive/documents/{uuid4()}"
            )

            assert response.status_code == 404


class TestVerifyIntegrityEndpoint:
    """Tests fuer POST /api/v1/archive/documents/{document_id}/verify"""

    def test_verify_integrity_success(self, client, mock_document, mock_archive):
        """Integritaetspruefung erfolgreich."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            # Handler ruft get_archive VOR (IDOR) und NACH der Verifikation
            mock_service.get_archive = AsyncMock(return_value=mock_archive)
            mock_service.verify_document_integrity = AsyncMock(return_value=True)

            response = client.post(
                f"/api/v1/archive/documents/{mock_document.id}/verify"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_verified"] is True
            assert data["last_verification_at"] is not None
            assert "bestätigt" in data["message"]

    def test_verify_integrity_failed(self, client, mock_document, mock_archive):
        """Integritaetspruefung fehlgeschlagen - Hash stimmt nicht."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_archive = AsyncMock(return_value=mock_archive)
            mock_service.verify_document_integrity = AsyncMock(return_value=False)

            response = client.post(
                f"/api/v1/archive/documents/{mock_document.id}/verify"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_verified"] is False
            assert "WARNUNG" in data["message"]

    def test_verify_not_archived(self, client):
        """Fehler wenn Dokument nicht archiviert."""
        from app.core.exceptions import ArchiveError

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_archive = AsyncMock(return_value=None)
            mock_service.verify_document_integrity = AsyncMock(
                side_effect=ArchiveError("Dokument ist nicht archiviert")
            )

            response = client.post(
                f"/api/v1/archive/documents/{uuid4()}/verify"
            )

            assert response.status_code == 400


class TestArchiveStatisticsEndpoint:
    """Tests fuer GET /api/v1/archive/statistics"""

    def test_get_statistics_success(self, client):
        """Archiv-Statistiken erfolgreich abrufen."""
        mock_stats = {
            "total_archived": 150,
            "by_category": {
                "invoice": 80,
                "contract": 50,
                "correspondence": 20,
            },
            "expiring_soon_90_days": 5,
            "verification_failed": 0,
        }

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_archive_statistics = AsyncMock(return_value=mock_stats)

            response = client.get("/api/v1/archive/statistics")

            assert response.status_code == 200
            data = response.json()
            assert data["total_archived"] == 150
            assert "by_category" in data
            assert data["by_category"]["invoice"] == 80


class TestExpiringArchivesEndpoint:
    """Tests fuer GET /api/v1/archive/expiring"""

    def test_get_expiring_archives(self, client, mock_archive):
        """Bald ablaufende Archive abrufen."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_expiring_archives = AsyncMock(return_value=[mock_archive])

            response = client.get(
                "/api/v1/archive/expiring",
                params={"days": 90}
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["document_id"] == str(mock_archive.document_id)
            assert data[0]["days_until_expiry"] > 0


class TestRetentionSettingsEndpoints:
    """Tests fuer Aufbewahrungsfristen-Einstellungen."""

    def test_get_retention_settings(self, client):
        """Alle Aufbewahrungsfristen-Einstellungen abrufen."""
        # Felder gemaess RetentionSettingResponse (model_validate liest
        # ALLE Schema-Felder vom Objekt -- Mock-Auto-Attribute waeren
        # keine gueltigen str/int/bool und ergaeben 500er)
        mock_setting = Mock()
        mock_setting.id = uuid4()
        mock_setting.category = RetentionCategory.INVOICE.value
        mock_setting.display_name = "Rechnungen"
        mock_setting.description = "Ein- und ausgehende Rechnungen"
        mock_setting.retention_years = 10
        mock_setting.legal_basis = "§147 AO, §14b UStG"
        mock_setting.reminder_days_before = 90
        mock_setting.auto_delete_enabled = False
        mock_setting.requires_approval_for_delete = True

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_retention_settings = AsyncMock(return_value=[mock_setting])

            response = client.get("/api/v1/archive/retention-settings")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["category"] == "invoice"
            assert data[0]["retention_years"] == 10

    def test_update_retention_setting_admin_only(self, client):
        """Nur Admins duerfen Aufbewahrungsfristen aendern -> 403."""
        response = client.put(
            "/api/v1/archive/retention-settings/invoice",
            json={
                "retention_years": 12,
                "reminder_days_before": 60,
                "auto_delete_enabled": False,
            }
        )

        # Normaler User (is_superuser=False) -> get_current_superuser blockt
        assert response.status_code == 403


class TestRetentionCategoriesEndpoint:
    """Tests fuer GET /api/v1/archive/categories"""

    def test_get_categories(self, client):
        """Alle verfuegbaren Kategorien abrufen (echter Vertrag).

        Response-Form: {"categories": [{value, display_name, description,
        default_years, legal_basis}, ...]} -- NICHT mehr der alte flache
        {kategorie: beschreibung}-Dict.
        """
        response = client.get("/api/v1/archive/categories")

        assert response.status_code == 200
        data = response.json()
        categories = {c["value"]: c for c in data["categories"]}

        assert "invoice" in categories
        assert "contract" in categories
        assert "correspondence" in categories

        # Deutsche Anzeige + Inhalte
        assert categories["invoice"]["display_name"] == "Rechnung"
        assert "Rechnungen" in categories["invoice"]["description"]
        assert categories["invoice"]["default_years"] == 10
        assert "§147 AO" in categories["invoice"]["legal_basis"]


class TestProcedureDocumentationEndpoints:
    """Tests fuer Verfahrensdokumentation Endpoints."""

    def test_generate_documentation_admin_only(self, client):
        """Nur Admins duerfen Verfahrensdokumentation generieren -> 403."""
        response = client.post(
            "/api/v1/archive/procedure-documentation",
            json={"change_summary": "Test-Generierung"}
        )

        # Normaler User (is_superuser=False) -> get_current_superuser blockt
        assert response.status_code == 403

    def test_get_current_documentation(self, client, mock_company):
        """Aktuelle Verfahrensdokumentation abrufen."""
        # Felder gemaess ProcedureDocDetailResponse (version ist str!)
        mock_doc = Mock()
        mock_doc.id = uuid4()
        mock_doc.version = "1.0"
        mock_doc.generated_at = datetime.now(timezone.utc)
        mock_doc.generated_by = "system"
        mock_doc.content_hash = "b" * 64
        mock_doc.change_summary = "Initiale Version"
        mock_doc.company_id = mock_company.id
        mock_doc.content = {"title": "Verfahrensdokumentation"}
        mock_doc.change_details = None

        with patch("app.api.v1.archive.procedure_doc_service") as mock_service:
            mock_service.get_latest_version = AsyncMock(return_value=mock_doc)

            response = client.get("/api/v1/archive/procedure-documentation")

            assert response.status_code == 200
            data = response.json()
            assert data["version"] == "1.0"
            assert data["content"] == {"title": "Verfahrensdokumentation"}

    def test_get_documentation_history(self, client, mock_company):
        """Versionshistorie abrufen."""
        def _version(version: str, days_ago: int, summary: str) -> Mock:
            v = Mock()
            v.id = uuid4()
            v.version = version
            v.generated_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
            v.generated_by = "system"
            v.content_hash = "c" * 64
            v.change_summary = summary
            v.company_id = mock_company.id
            return v

        mock_v1 = _version("1.0", 30, "Initiale Version")
        mock_v2 = _version("2.0", 0, "Update Sicherheitsrichtlinien")

        with patch("app.api.v1.archive.procedure_doc_service") as mock_service:
            mock_service.get_version_history = AsyncMock(
                return_value=[mock_v2, mock_v1]
            )

            response = client.get("/api/v1/archive/procedure-documentation/history")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["version"] == "2.0"


class TestImmutabilityProtection:
    """Tests fuer Unveraenderbarkeitsschutz bei archivierten Dokumenten."""

    def test_update_archived_document_forbidden(self, client, mock_document):
        """Update eines archivierten Dokuments wird abgelehnt."""
        from app.core.exceptions import ImmutabilityViolationError

        with patch("app.api.v1.documents.archive_service") as mock_service:
            mock_service.validate_modification_allowed = AsyncMock(
                side_effect=ImmutabilityViolationError(
                    "Dokument ist archiviert und darf nicht veraendert werden"
                )
            )

            # Versuche Update
            response = client.patch(
                f"/api/v1/documents/{mock_document.id}",
                json={"language": "de"}
            )

            # Sollte 403 Forbidden sein (aus dem Immutability-Check,
            # CSRF ist via Bearer-Header umgangen)
            assert response.status_code == 403
            assert "archiviert" in _error_message(response)

    def test_delete_archived_document_forbidden(self, client, mock_document):
        """Loeschen eines archivierten Dokuments wird abgelehnt."""
        from app.core.exceptions import ImmutabilityViolationError

        with patch("app.api.v1.documents.archive_service") as mock_service:
            mock_service.validate_modification_allowed = AsyncMock(
                side_effect=ImmutabilityViolationError(
                    "Dokument ist archiviert und darf nicht geloescht werden"
                )
            )

            response = client.delete(
                f"/api/v1/documents/{mock_document.id}"
            )

            # Sollte 403 Forbidden sein
            assert response.status_code == 403
            assert "archiviert" in _error_message(response)


class TestGoBDCompliance:
    """End-to-End Tests fuer GoBD-Compliance."""

    def test_archive_workflow_complete(self, client, mock_document, mock_archive):
        """Kompletter Archivierungs-Workflow."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            # 1. Dokument archivieren
            mock_service.archive_document = AsyncMock(return_value=mock_archive)

            response = client.post(
                "/api/v1/archive/documents",
                json={
                    "document_id": str(mock_document.id),
                    "retention_category": "invoice",
                }
            )
            assert response.status_code == 201
            archive_data = response.json()

            # 2. Integritaet pruefen
            mock_service.get_archive = AsyncMock(return_value=mock_archive)
            mock_service.verify_document_integrity = AsyncMock(return_value=True)

            response = client.post(
                f"/api/v1/archive/documents/{mock_document.id}/verify"
            )
            assert response.status_code == 200
            assert response.json()["is_verified"] is True

            # 3. Archiv-Info abrufen
            response = client.get(
                f"/api/v1/archive/documents/{mock_document.id}"
            )
            assert response.status_code == 200
            data = response.json()
            assert data["content_hash"] == archive_data["content_hash"]

    def test_retention_categories_complete(self, client):
        """Alle gesetzlich vorgeschriebenen Kategorien sind vorhanden."""
        response = client.get("/api/v1/archive/categories")

        assert response.status_code == 200
        categories = {c["value"] for c in response.json()["categories"]}

        # GoBD-relevante Kategorien
        required_categories = [
            "invoice",           # Rechnungen (§147 AO, §14b UStG)
            "contract",          # Vertraege (§147 AO, §257 HGB)
            "correspondence",    # Geschaeftsbriefe (§257 HGB)
            "booking_document",  # Buchungsbelege (§147 AO)
            "annual_report",     # Jahresabschluesse (§257 HGB)
            "tax_document",      # Steuerunterlagen (§147 AO)
        ]

        for cat in required_categories:
            assert cat in categories, f"Kategorie '{cat}' fehlt"


class TestGermanLanguageMessages:
    """Tests fuer deutsche Fehlermeldungen."""

    def test_archive_error_german(self, client, mock_document):
        """Fehlermeldungen sind auf Deutsch."""
        from app.core.exceptions import ArchiveError

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.archive_document = AsyncMock(
                side_effect=ArchiveError("Dokument ist bereits archiviert")
            )

            response = client.post(
                "/api/v1/archive/documents",
                json={
                    "document_id": str(mock_document.id),
                    "retention_category": "invoice",
                }
            )

            assert response.status_code == 400
            # Fehlermeldung sollte Deutsch sein (einheitliche Fehler-Response)
            detail = _error_message(response)
            assert detail, "Fehler-Response ohne nachricht/detail"
            has_german = any(word in detail.lower() for word in
                           ["archiv", "dokument", "fehler", "bereits"])
            assert has_german or "ä" in detail or "ö" in detail or "ü" in detail
