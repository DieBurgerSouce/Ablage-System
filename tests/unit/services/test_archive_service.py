"""
Unit Tests fuer GoBD Archive Service - Revisionssichere Dokumentenarchivierung.

Tests:
- Dokumentenarchivierung mit SHA-256 Hash
- Integritaetspruefung (Hash-Verifikation)
- Immutability-Enforcement
- Aufbewahrungsfristen-Berechnung
- Ablaufende Archive
- Statistiken
"""

import hashlib
import pytest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.archive_service import ArchiveService, DEFAULT_RETENTION_YEARS
from app.core.exceptions import (
    DocumentNotFoundError,
    ArchiveError,
    ImmutabilityViolationError,
)
from app.db.models import RetentionCategory, HashAlgorithm


@pytest.fixture
def archive_service():
    """Create ArchiveService instance."""
    return ArchiveService()


@pytest.fixture
def mock_document():
    """Create mock document object."""
    doc = MagicMock()
    doc.id = uuid4()
    doc.company_id = uuid4()
    doc.filename = "test_document.pdf"
    doc.original_filename = "Rechnung_2025_001.pdf"
    doc.mime_type = "application/pdf"
    doc.checksum = "abc123checksum"
    doc.extracted_text = "Dies ist ein Test-Dokument mit Umlauten: äöüß"
    doc.file_size = 12345
    doc.is_archived = False
    doc.archived_at = None
    doc.archive = None
    return doc


@pytest.fixture
def mock_archived_document(mock_document):
    """Create mock archived document."""
    mock_document.is_archived = True
    mock_document.archived_at = datetime.now(timezone.utc)

    archive = MagicMock()
    archive.id = uuid4()
    archive.document_id = mock_document.id
    archive.company_id = mock_document.company_id
    archive.content_hash = "a" * 64  # SHA-256 hex
    archive.hash_algorithm = HashAlgorithm.SHA256.value
    archive.signature_timestamp = datetime.now(timezone.utc)
    archive.retention_category = RetentionCategory.INVOICE.value
    archive.retention_years = 10
    archive.retention_expires_at = date.today() + timedelta(days=10 * 365)
    archive.is_verified = True
    archive.last_verification_at = None
    archive.verification_failed_reason = None
    archive.retention_reminder_sent = False

    mock_document.archive = archive
    return mock_document


@pytest.fixture
def mock_db():
    """Create mock database session."""
    db = AsyncMock()
    return db


class TestArchiveDocument:
    """Tests fuer archive_document Methode."""

    @pytest.mark.asyncio
    async def test_archive_document_success(self, archive_service, mock_document, mock_db):
        """Dokument erfolgreich archivieren mit SHA-256."""
        user_id = uuid4()

        # Mock DB execute for document query
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute.return_value = mock_result

        # Mock _get_retention_years to return an actual integer
        with patch.object(archive_service, '_get_retention_years', return_value=10):
            archive = await archive_service.archive_document(
                mock_db,
                mock_document.id,
                user_id,
                retention_category=RetentionCategory.INVOICE.value,
            )

        # Prüfe Archiv-Erstellung
        assert archive is not None
        assert archive.document_id == mock_document.id
        assert archive.company_id == mock_document.company_id
        assert archive.hash_algorithm == HashAlgorithm.SHA256.value
        assert archive.retention_category == RetentionCategory.INVOICE.value
        assert archive.retention_years == 10  # Standard für Rechnungen
        assert archive.content_hash is not None
        assert len(archive.content_hash) == 64  # SHA-256 hex length

        # Dokument als archiviert markiert
        assert mock_document.is_archived is True
        assert mock_document.archived_at is not None

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_document_not_found(self, archive_service, mock_db):
        """Fehler wenn Dokument nicht existiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(DocumentNotFoundError):
            await archive_service.archive_document(
                mock_db, uuid4(), uuid4()
            )

    @pytest.mark.asyncio
    async def test_archive_document_already_archived(
        self, archive_service, mock_archived_document, mock_db
    ):
        """Fehler wenn Dokument bereits archiviert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archived_document
        mock_db.execute.return_value = mock_result

        with pytest.raises(ArchiveError) as exc_info:
            await archive_service.archive_document(
                mock_db, mock_archived_document.id, uuid4()
            )

        assert "bereits archiviert" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_archive_with_metadata(self, archive_service, mock_document, mock_db):
        """Archivierung mit zusaetzlichen Metadaten."""
        user_id = uuid4()
        metadata = {"source": "scan", "scanner_id": "SCANNER-001"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute.return_value = mock_result

        # Mock _get_retention_years to return an actual integer
        with patch.object(archive_service, '_get_retention_years', return_value=10):
            archive = await archive_service.archive_document(
                mock_db,
                mock_document.id,
                user_id,
                retention_category=RetentionCategory.CONTRACT.value,
                metadata=metadata,
            )

        assert archive.archive_metadata == metadata
        assert archive.retention_category == RetentionCategory.CONTRACT.value


class TestVerifyDocumentIntegrity:
    """Tests fuer verify_document_integrity Methode."""

    @pytest.mark.asyncio
    async def test_verify_integrity_success(
        self, archive_service, mock_archived_document, mock_db
    ):
        """Integritaetspruefung erfolgreich."""
        # Berechne erwarteten Hash
        hasher = hashlib.sha256()
        hasher.update(mock_archived_document.filename.encode("utf-8"))
        hasher.update(mock_archived_document.original_filename.encode("utf-8"))
        hasher.update(mock_archived_document.mime_type.encode("utf-8"))
        hasher.update(mock_archived_document.checksum.encode("utf-8"))
        hasher.update(mock_archived_document.extracted_text.encode("utf-8"))
        hasher.update(str(mock_archived_document.file_size).encode("utf-8"))
        expected_hash = hasher.hexdigest()

        # Setze korrekten Hash im Archiv
        mock_archived_document.archive.content_hash = expected_hash

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archived_document
        mock_db.execute.return_value = mock_result

        is_valid = await archive_service.verify_document_integrity(
            mock_db, mock_archived_document.id
        )

        assert is_valid is True
        assert mock_archived_document.archive.is_verified is True
        assert mock_archived_document.archive.last_verification_at is not None
        assert mock_archived_document.archive.verification_failed_reason is None

    @pytest.mark.asyncio
    async def test_verify_integrity_failed(
        self, archive_service, mock_archived_document, mock_db
    ):
        """Integritaetspruefung fehlgeschlagen - Hash stimmt nicht."""
        # Falscher Hash im Archiv
        mock_archived_document.archive.content_hash = "invalid_hash_" + "0" * 51

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archived_document
        mock_db.execute.return_value = mock_result

        is_valid = await archive_service.verify_document_integrity(
            mock_db, mock_archived_document.id
        )

        assert is_valid is False
        assert mock_archived_document.archive.is_verified is False
        assert "Hash-Mismatch" in mock_archived_document.archive.verification_failed_reason

    @pytest.mark.asyncio
    async def test_verify_integrity_not_archived(
        self, archive_service, mock_document, mock_db
    ):
        """Fehler wenn Dokument nicht archiviert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute.return_value = mock_result

        with pytest.raises(ArchiveError) as exc_info:
            await archive_service.verify_document_integrity(
                mock_db, mock_document.id
            )

        assert "nicht archiviert" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_verify_integrity_document_not_found(self, archive_service, mock_db):
        """Fehler wenn Dokument nicht existiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(DocumentNotFoundError):
            await archive_service.verify_document_integrity(mock_db, uuid4())


class TestImmutability:
    """Tests fuer Unveraenderbarkeit (Immutability)."""

    @pytest.mark.asyncio
    async def test_check_immutability_archived(
        self, archive_service, mock_archived_document, mock_db
    ):
        """Archiviertes Dokument ist unveraenderbar."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = True  # is_archived
        mock_db.execute.return_value = mock_result

        is_immutable = await archive_service.check_immutability(
            mock_db, mock_archived_document.id
        )

        assert is_immutable is True

    @pytest.mark.asyncio
    async def test_check_immutability_not_archived(
        self, archive_service, mock_document, mock_db
    ):
        """Nicht-archiviertes Dokument ist veraenderbar."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = False  # is_archived
        mock_db.execute.return_value = mock_result

        is_immutable = await archive_service.check_immutability(
            mock_db, mock_document.id
        )

        assert is_immutable is False

    @pytest.mark.asyncio
    async def test_validate_modification_allowed_success(
        self, archive_service, mock_document, mock_db
    ):
        """Modifikation erlaubt fuer nicht-archiviertes Dokument."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = False  # is_archived
        mock_db.execute.return_value = mock_result

        # Sollte keine Exception werfen
        await archive_service.validate_modification_allowed(
            mock_db, mock_document.id
        )

    @pytest.mark.asyncio
    async def test_validate_modification_denied_for_archived(
        self, archive_service, mock_archived_document, mock_db
    ):
        """ImmutabilityViolationError fuer archiviertes Dokument."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = True  # is_archived
        mock_db.execute.return_value = mock_result

        with pytest.raises(ImmutabilityViolationError) as exc_info:
            await archive_service.validate_modification_allowed(
                mock_db, mock_archived_document.id
            )

        assert "archiviert" in str(exc_info.value)
        assert "GoBD" in str(exc_info.value)


class TestRetentionCalculation:
    """Tests fuer Aufbewahrungsfristen-Berechnung."""

    def test_default_retention_years(self):
        """Standard-Aufbewahrungsfristen nach deutschem Recht."""
        assert DEFAULT_RETENTION_YEARS[RetentionCategory.INVOICE.value] == 10
        assert DEFAULT_RETENTION_YEARS[RetentionCategory.CONTRACT.value] == 10
        assert DEFAULT_RETENTION_YEARS[RetentionCategory.CORRESPONDENCE.value] == 6
        assert DEFAULT_RETENTION_YEARS[RetentionCategory.BOOKING_DOCUMENT.value] == 10
        assert DEFAULT_RETENTION_YEARS[RetentionCategory.ANNUAL_REPORT.value] == 10
        assert DEFAULT_RETENTION_YEARS[RetentionCategory.TAX_DOCUMENT.value] == 10
        assert DEFAULT_RETENTION_YEARS[RetentionCategory.OTHER.value] == 6

    @pytest.mark.asyncio
    async def test_retention_expiry_calculation(
        self, archive_service, mock_document, mock_db
    ):
        """Ablaufdatum wird korrekt berechnet."""
        user_id = uuid4()
        today = date.today()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute.return_value = mock_result

        # Mock _get_retention_years to return an actual integer
        with patch.object(archive_service, '_get_retention_years', return_value=10):
            archive = await archive_service.archive_document(
                mock_db,
                mock_document.id,
                user_id,
                retention_category=RetentionCategory.INVOICE.value,
            )

        expected_expiry = today + timedelta(days=10 * 365)
        assert archive.retention_expires_at == expected_expiry


class TestExpiringArchives:
    """Tests fuer ablaufende Archive."""

    @pytest.mark.asyncio
    async def test_get_expiring_archives(self, archive_service, mock_db):
        """Bald ablaufende Archive abrufen."""
        company_id = uuid4()

        mock_archive1 = MagicMock()
        mock_archive1.id = uuid4()
        mock_archive1.retention_expires_at = date.today() + timedelta(days=30)

        mock_archive2 = MagicMock()
        mock_archive2.id = uuid4()
        mock_archive2.retention_expires_at = date.today() + timedelta(days=60)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_archive1, mock_archive2]
        mock_db.execute.return_value = mock_result

        expiring = await archive_service.get_expiring_archives(
            mock_db, company_id, days_until_expiry=90
        )

        assert len(expiring) == 2

    @pytest.mark.asyncio
    async def test_mark_reminder_sent(self, archive_service, mock_db):
        """Archive als erinnert markieren."""
        archive_id = uuid4()

        mock_archive = MagicMock()
        mock_archive.id = archive_id
        mock_archive.retention_reminder_sent = False
        mock_archive.retention_reminder_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archive
        mock_db.execute.return_value = mock_result

        await archive_service.mark_reminder_sent(mock_db, archive_id)

        assert mock_archive.retention_reminder_sent is True
        assert mock_archive.retention_reminder_at is not None
        mock_db.commit.assert_called_once()


class TestArchiveStatistics:
    """Tests fuer Archiv-Statistiken."""

    @pytest.mark.asyncio
    async def test_get_archive_statistics(self, archive_service, mock_db):
        """Archiv-Statistiken abrufen."""
        company_id = uuid4()

        # Mock die verschiedenen Queries
        mock_db.execute.side_effect = [
            # Total count
            MagicMock(scalar=MagicMock(return_value=100)),
            # By category
            MagicMock(all=MagicMock(return_value=[
                (RetentionCategory.INVOICE.value, 50),
                (RetentionCategory.CONTRACT.value, 30),
                (RetentionCategory.CORRESPONDENCE.value, 20),
            ])),
            # Expiring soon
            MagicMock(scalar=MagicMock(return_value=5)),
            # Unverified
            MagicMock(scalar=MagicMock(return_value=2)),
        ]

        stats = await archive_service.get_archive_statistics(mock_db, company_id)

        assert stats["total_archived"] == 100
        assert stats["expiring_soon_90_days"] == 5
        assert stats["verification_failed"] == 2
        assert RetentionCategory.INVOICE.value in stats["by_category"]


class TestHashAlgorithms:
    """Tests fuer verschiedene Hash-Algorithmen."""

    @pytest.mark.asyncio
    async def test_sha256_hash_calculation(self, archive_service, mock_document):
        """SHA-256 Hash-Berechnung."""
        content_hash = await archive_service._compute_document_hash(
            mock_document, algorithm=HashAlgorithm.SHA256.value
        )

        assert len(content_hash) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in content_hash)

    @pytest.mark.asyncio
    async def test_sha384_hash_calculation(self, archive_service, mock_document):
        """SHA-384 Hash-Berechnung."""
        content_hash = await archive_service._compute_document_hash(
            mock_document, algorithm=HashAlgorithm.SHA384.value
        )

        assert len(content_hash) == 96  # SHA-384 hex length

    @pytest.mark.asyncio
    async def test_sha512_hash_calculation(self, archive_service, mock_document):
        """SHA-512 Hash-Berechnung."""
        content_hash = await archive_service._compute_document_hash(
            mock_document, algorithm=HashAlgorithm.SHA512.value
        )

        assert len(content_hash) == 128  # SHA-512 hex length

    @pytest.mark.asyncio
    async def test_hash_includes_german_characters(self, archive_service, mock_document):
        """Hash beruecksichtigt deutsche Umlaute korrekt."""
        mock_document.extracted_text = "Prüfung der Äquivalenz mit Größenangabe"

        hash1 = await archive_service._compute_document_hash(mock_document)

        # Aendere Umlaute
        mock_document.extracted_text = "Prufung der Aquivalenz mit Grossenangabe"
        hash2 = await archive_service._compute_document_hash(mock_document)

        assert hash1 != hash2  # Hashes muessen unterschiedlich sein

    @pytest.mark.asyncio
    async def test_hash_deterministic(self, archive_service, mock_document):
        """Hash ist deterministisch bei gleichen Daten."""
        hash1 = await archive_service._compute_document_hash(mock_document)
        hash2 = await archive_service._compute_document_hash(mock_document)

        assert hash1 == hash2


class TestRetentionSettings:
    """Tests fuer Aufbewahrungsfristen-Einstellungen."""

    @pytest.mark.asyncio
    async def test_get_retention_settings(self, archive_service, mock_db):
        """Alle Aufbewahrungsfristen-Einstellungen abrufen."""
        mock_setting1 = MagicMock()
        mock_setting1.category = RetentionCategory.INVOICE.value
        mock_setting1.retention_years = 10

        mock_setting2 = MagicMock()
        mock_setting2.category = RetentionCategory.CONTRACT.value
        mock_setting2.retention_years = 10

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_setting1, mock_setting2]
        mock_db.execute.return_value = mock_result

        settings = await archive_service.get_retention_settings(mock_db)

        assert len(settings) == 2

    @pytest.mark.asyncio
    async def test_update_retention_setting(self, archive_service, mock_db):
        """Aufbewahrungsfristen-Einstellung aktualisieren."""
        admin_id = uuid4()

        mock_setting = MagicMock()
        mock_setting.category = RetentionCategory.OTHER.value
        mock_setting.retention_years = 6
        mock_setting.reminder_days_before = 90
        mock_setting.auto_delete_enabled = False

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_db.execute.return_value = mock_result

        updated = await archive_service.update_retention_setting(
            mock_db,
            category=RetentionCategory.OTHER.value,
            retention_years=8,
            reminder_days_before=120,
            auto_delete_enabled=True,
            updated_by_id=admin_id,
        )

        assert mock_setting.retention_years == 8
        assert mock_setting.reminder_days_before == 120
        assert mock_setting.auto_delete_enabled is True
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_retention_setting_not_found(self, archive_service, mock_db):
        """Fehler wenn Kategorie nicht existiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ArchiveError) as exc_info:
            await archive_service.update_retention_setting(
                mock_db,
                category="invalid_category",
                retention_years=10,
                reminder_days_before=90,
                auto_delete_enabled=False,
                updated_by_id=uuid4(),
            )

        assert "nicht gefunden" in str(exc_info.value)


class TestGetArchive:
    """Tests fuer get_archive Methode."""

    @pytest.mark.asyncio
    async def test_get_archive_exists(self, archive_service, mock_db):
        """Archiv-Informationen abrufen."""
        doc_id = uuid4()

        mock_archive = MagicMock()
        mock_archive.id = uuid4()
        mock_archive.document_id = doc_id

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_archive
        mock_db.execute.return_value = mock_result

        archive = await archive_service.get_archive(mock_db, doc_id)

        assert archive is not None
        assert archive.document_id == doc_id

    @pytest.mark.asyncio
    async def test_get_archive_not_exists(self, archive_service, mock_db):
        """None wenn kein Archiv existiert."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        archive = await archive_service.get_archive(mock_db, uuid4())

        assert archive is None


class TestGoBDCompliance:
    """GoBD-Compliance Tests."""

    @pytest.mark.asyncio
    async def test_gobd_nachvollziehbarkeit(self, archive_service, mock_document, mock_db):
        """Nachvollziehbarkeit: Archivierung wird dokumentiert."""
        user_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db.execute.return_value = mock_result

        # Mock _get_retention_years to return an actual integer
        with patch.object(archive_service, '_get_retention_years', return_value=6):
            archive = await archive_service.archive_document(
                mock_db, mock_document.id, user_id
            )

        # Wer, wann, was
        assert archive.archived_by_id == user_id
        assert archive.signature_timestamp is not None
        assert archive.content_hash is not None

    @pytest.mark.asyncio
    async def test_gobd_unveraenderbarkeit(self, archive_service, mock_archived_document, mock_db):
        """Unveraenderbarkeit: Archivierte Dokumente koennen nicht modifiziert werden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = True
        mock_db.execute.return_value = mock_result

        with pytest.raises(ImmutabilityViolationError):
            await archive_service.validate_modification_allowed(
                mock_db, mock_archived_document.id
            )

    @pytest.mark.asyncio
    async def test_gobd_vollstaendigkeit(self, archive_service, mock_document):
        """Vollstaendigkeit: Hash beinhaltet alle relevanten Daten."""
        # Alle Felder werden in Hash einbezogen
        hash1 = await archive_service._compute_document_hash(mock_document)

        # Aendere ein Feld
        original_text = mock_document.extracted_text
        mock_document.extracted_text = "Geaenderter Text"
        hash2 = await archive_service._compute_document_hash(mock_document)

        # Hashes muessen unterschiedlich sein
        assert hash1 != hash2

        # Aendere zurueck
        mock_document.extracted_text = original_text
        hash3 = await archive_service._compute_document_hash(mock_document)

        # Sollte wieder gleich sein
        assert hash1 == hash3

    def test_gobd_ordnung(self):
        """Ordnung: Kategorisierung nach Dokumenttyp."""
        # Alle GoBD-relevanten Kategorien sind definiert
        categories = [cat.value for cat in RetentionCategory]

        assert "invoice" in categories  # Rechnungen
        assert "contract" in categories  # Vertraege
        assert "booking_document" in categories  # Buchungsbelege
        assert "annual_report" in categories  # Jahresabschluesse
        assert "tax_document" in categories  # Steuerunterlagen
        assert "correspondence" in categories  # Geschaeftsbriefe
