# -*- coding: utf-8 -*-
"""
Integration Tests fuer GoBD Archive API Endpoints.

Tests fuer das GoBD-konforme Archivierungssystem:
- Dokumentenarchivierung mit SHA-256 Signatur
- Integritaetspruefung
- Unveraenderbarkeitsschutz (Immutability)
- Aufbewahrungsfristen-Verwaltung
- Verfahrensdokumentation
"""

import pytest
from datetime import date, datetime, timedelta
from uuid import uuid4
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock, MagicMock, patch

from pathlib import Path
import sys

# Add app to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.main import app
from app.db.models import RetentionCategory


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
    """Create mock archive."""
    archive = Mock()
    archive.id = uuid4()
    archive.document_id = mock_document.id
    archive.company_id = mock_document.company_id
    archive.content_hash = "a" * 64  # SHA-256 hex
    archive.hash_algorithm = "SHA-256"
    archive.signature_timestamp = datetime.now()
    archive.signature_certificate = None
    archive.retention_category = RetentionCategory.INVOICE.value
    archive.retention_years = 10
    archive.retention_expires_at = date.today() + timedelta(days=10 * 365)
    archive.archived_by_id = mock_user.id
    archive.is_verified = True
    archive.last_verification_at = None
    archive.retention_reminder_sent = False
    archive.archive_metadata = {}
    return archive


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


@pytest.fixture
def client(mock_user, mock_company):
    """Create test client with dependency overrides."""
    from app.api.dependencies import get_current_user, get_db
    from app.middleware.company_context import require_company

    # Mock db session
    mock_db_session = AsyncMock()

    async def mock_get_db():
        yield mock_db_session

    async def mock_require_company():
        return mock_company.id

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_company] = mock_require_company

    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(mock_admin_user, mock_company):
    """Create test client for admin user."""
    from app.api.dependencies import get_current_user, get_current_superuser, get_db
    from app.middleware.company_context import require_company

    mock_db_session = AsyncMock()

    async def mock_get_db():
        yield mock_db_session

    async def mock_require_company():
        return mock_company.id

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_current_superuser] = lambda: mock_admin_user
    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_company] = mock_require_company

    yield TestClient(app)

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
            assert data["content_hash"] is not None
            assert data["retention_category"] == "invoice"
            assert "retention_expires_at" in data

    def test_archive_document_not_found(self, client):
        """Fehler wenn Dokument nicht existiert."""
        from app.core.exceptions import DocumentNotFoundError

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.archive_document = AsyncMock(
                side_effect=DocumentNotFoundError("Dokument nicht gefunden")
            )

            response = client.post(
                "/api/v1/archive/documents",
                json={
                    "document_id": str(uuid4()),
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

    def test_verify_integrity_success(self, client, mock_document):
        """Integritaetspruefung erfolgreich."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.verify_document_integrity = AsyncMock(return_value=True)

            response = client.post(
                f"/api/v1/archive/documents/{mock_document.id}/verify"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is True
            assert "verified_at" in data

    def test_verify_integrity_failed(self, client, mock_document):
        """Integritaetspruefung fehlgeschlagen - Hash stimmt nicht."""
        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.verify_document_integrity = AsyncMock(return_value=False)

            response = client.post(
                f"/api/v1/archive/documents/{mock_document.id}/verify"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["is_valid"] is False

    def test_verify_not_archived(self, client):
        """Fehler wenn Dokument nicht archiviert."""
        from app.core.exceptions import ArchiveError

        with patch("app.api.v1.archive.archive_service") as mock_service:
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


class TestRetentionSettingsEndpoints:
    """Tests fuer Aufbewahrungsfristen-Einstellungen."""

    def test_get_retention_settings(self, client):
        """Alle Aufbewahrungsfristen-Einstellungen abrufen."""
        mock_setting = Mock()
        mock_setting.category = RetentionCategory.INVOICE.value
        mock_setting.display_name = "Rechnungen"
        mock_setting.retention_years = 10
        mock_setting.legal_basis = "§147 AO, §14b UStG"
        mock_setting.reminder_days_before = 90
        mock_setting.auto_delete_enabled = False

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.get_retention_settings = AsyncMock(return_value=[mock_setting])

            response = client.get("/api/v1/archive/retention-settings")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 1
            assert data[0]["category"] == "invoice"
            assert data[0]["retention_years"] == 10

    def test_update_retention_setting_admin_only(self, client):
        """Nur Admins duerfen Aufbewahrungsfristen aendern."""
        # Normaler User sollte 403 erhalten
        response = client.put(
            "/api/v1/archive/retention-settings/invoice",
            json={
                "retention_years": 12,
                "reminder_days_before": 60,
                "auto_delete_enabled": False,
            }
        )

        # Entweder 403 Forbidden oder 401/422 je nach Implementation
        assert response.status_code in [401, 403, 422]


class TestRetentionCategoriesEndpoint:
    """Tests fuer GET /api/v1/archive/categories"""

    def test_get_categories(self, client):
        """Alle verfuegbaren Kategorien abrufen."""
        response = client.get("/api/v1/archive/categories")

        assert response.status_code == 200
        data = response.json()
        assert "invoice" in data
        assert "contract" in data
        assert "correspondence" in data

        # Deutsche Beschreibungen
        assert "Rechnungen" in data["invoice"]


class TestProcedureDocumentationEndpoints:
    """Tests fuer Verfahrensdokumentation Endpoints."""

    def test_generate_documentation_admin_only(self, client):
        """Nur Admins duerfen Verfahrensdokumentation generieren."""
        response = client.post(
            "/api/v1/archive/procedure-documentation",
            json={"change_summary": "Test-Generierung"}
        )

        # Normaler User sollte 403 erhalten
        assert response.status_code in [401, 403, 422]

    def test_get_current_documentation(self, client):
        """Aktuelle Verfahrensdokumentation abrufen."""
        mock_doc = Mock()
        mock_doc.id = uuid4()
        mock_doc.version = 1
        mock_doc.content = {"title": "Verfahrensdokumentation"}
        mock_doc.content_hash = "b" * 64
        mock_doc.created_at = datetime.now()
        mock_doc.change_summary = "Initiale Version"

        with patch("app.api.v1.archive.procedure_doc_service") as mock_service:
            mock_service.get_latest_version = AsyncMock(return_value=mock_doc)

            response = client.get("/api/v1/archive/procedure-documentation")

            assert response.status_code == 200
            data = response.json()
            assert data["version"] == 1
            assert "content" in data

    def test_get_documentation_history(self, client):
        """Versionshistorie abrufen."""
        mock_v1 = Mock()
        mock_v1.id = uuid4()
        mock_v1.version = 1
        mock_v1.created_at = datetime.now() - timedelta(days=30)
        mock_v1.change_summary = "Initiale Version"

        mock_v2 = Mock()
        mock_v2.id = uuid4()
        mock_v2.version = 2
        mock_v2.created_at = datetime.now()
        mock_v2.change_summary = "Update Sicherheitsrichtlinien"

        with patch("app.api.v1.archive.procedure_doc_service") as mock_service:
            mock_service.get_version_history = AsyncMock(
                return_value=[mock_v2, mock_v1]
            )

            response = client.get("/api/v1/archive/procedure-documentation/history")

            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["version"] == 2


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
                json={"status": "processed"}
            )

            # Sollte 403 Forbidden sein
            assert response.status_code == 403

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
            mock_service.verify_document_integrity = AsyncMock(return_value=True)

            response = client.post(
                f"/api/v1/archive/documents/{mock_document.id}/verify"
            )
            assert response.status_code == 200
            assert response.json()["is_valid"] is True

            # 3. Archiv-Info abrufen
            mock_service.get_archive = AsyncMock(return_value=mock_archive)

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
        categories = response.json()

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

    def test_archive_error_german(self, client):
        """Fehlermeldungen sind auf Deutsch."""
        from app.core.exceptions import ArchiveError

        with patch("app.api.v1.archive.archive_service") as mock_service:
            mock_service.archive_document = AsyncMock(
                side_effect=ArchiveError("Dokument ist bereits archiviert")
            )

            response = client.post(
                "/api/v1/archive/documents",
                json={
                    "document_id": str(uuid4()),
                    "retention_category": "invoice",
                }
            )

            assert response.status_code == 400
            # Fehlermeldung sollte Deutsch sein
            data = response.json()
            assert "detail" in data
            # Die Meldung sollte deutsche Woerter enthalten
            detail = str(data.get("detail", ""))
            # Prüfe auf typische deutsche Wörter oder Umlaute
            has_german = any(word in detail.lower() for word in
                           ["archiv", "dokument", "fehler", "bereits"])
            assert has_german or "ä" in detail or "ö" in detail or "ü" in detail
