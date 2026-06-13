# -*- coding: utf-8 -*-
"""
Unit Tests fuer PortalDocumentService.

Getestet wird der ECHTE Service-Vertrag:
    upload_document(portal_user, filename, content: bytes, content_type?, ...)
        -> PortalDocument   (schreibt Datei nach storage_path/<company>/<entity>/...)
    get_documents(entity_id, company_id, ...)         -> tuple[list[dict], int]
    get_document_detail(document_id, entity_id, company_id) -> Optional[dict]
    get_document_content(document_id, entity_id, company_id)
        -> Optional[tuple[bytes, str, str]]   (None statt Exception bei not-found)
    delete_document(document_id, portal_user)         -> bool

Die fruehere Datei nutzte eine erfundene API (storage-Service, download_document,
file_size/uploaded_by_id/original_filename/portal_user_id-Kwargs) - existiert nicht.

Feinpoliert und durchdacht - Portal Document Tests.
"""

import os
import tempfile
from uuid import UUID, uuid4

import pytest

from app.services.portal.portal_document_service import (
    PortalDocumentService,
    get_portal_document_service,
    MAX_FILE_SIZE,
)
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def storage_dir():
    """Temporaeres Storage-Verzeichnis (Uploads schreiben hierhin)."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def document_service(mock_db, storage_dir) -> PortalDocumentService:
    """PortalDocumentService mit gemockter DB + Temp-Storage."""
    return PortalDocumentService(mock_db, storage_path=storage_dir)


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_portal_document_service Factory."""

    def test_get_portal_document_service_returns_instance(self, mock_db):
        service = get_portal_document_service(mock_db)
        assert isinstance(service, PortalDocumentService)
        assert service.db is mock_db


# ========================= Upload Document Tests =========================


class TestUploadDocument:
    """Tests fuer upload_document() Methode."""

    @pytest.mark.asyncio
    async def test_upload_pdf_success(
        self, document_service, mock_db, sample_portal_user
    ):
        """Sollte PDF erfolgreich hochladen und auf Platte schreiben."""
        doc = await document_service.upload_document(
            portal_user=sample_portal_user,
            filename="rechnung.pdf",
            content=b"%PDF-1.4 test content",
            content_type="application/pdf",
        )

        assert doc is not None
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_image_success(
        self, document_service, mock_db, sample_portal_user
    ):
        """Sollte Bild erfolgreich hochladen."""
        await document_service.upload_document(
            portal_user=sample_portal_user,
            filename="beleg.png",
            content=b"\x89PNG\r\n\x1a\n test content",
            content_type="image/png",
        )
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_with_description_and_type(
        self, document_service, mock_db, sample_portal_user
    ):
        """Sollte Dokument mit Beschreibung und Typ hochladen."""
        await document_service.upload_document(
            portal_user=sample_portal_user,
            filename="vertrag.pdf",
            content=b"%PDF-1.4 contract",
            content_type="application/pdf",
            description="Signierter Vertrag",
            document_type="contract",
        )
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_with_complaint_reference(
        self, document_service, mock_db, sample_portal_user
    ):
        """Sollte Dokument mit Reklamationsbezug hochladen."""
        complaint_id = uuid4()
        await document_service.upload_document(
            portal_user=sample_portal_user,
            filename="nachweis.pdf",
            content=b"%PDF-1.4 proof",
            content_type="application/pdf",
            complaint_id=complaint_id,
        )
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_invalid_extension(
        self, document_service, mock_db, sample_portal_user
    ):
        """Sollte Fehler bei nicht erlaubter Dateiendung werfen."""
        with pytest.raises(ValueError, match="Dateityp nicht erlaubt"):
            await document_service.upload_document(
                portal_user=sample_portal_user,
                filename="virus.exe",
                content=b"executable content",
                content_type="application/x-msdownload",
            )
        mock_db.add.assert_not_called()

    def test_validate_file_too_large(self, document_service):
        """_validate_file lehnt Dateien > MAX_FILE_SIZE ab."""
        is_valid, error = document_service._validate_file(
            filename="huge.pdf",
            content_type="application/pdf",
            file_size=MAX_FILE_SIZE + 1,
        )
        assert is_valid is False
        assert "Datei zu gross" in error


# ========================= Get Documents Tests =========================


class TestGetDocuments:
    """Tests fuer get_documents() Methode (gibt (list[dict], int))."""

    @pytest.mark.asyncio
    async def test_get_documents_success(
        self, document_service, mock_db, sample_portal_document, entity_id, company_id
    ):
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_portal_document]),
        ]

        result, total = await document_service.get_documents(
            entity_id=entity_id, company_id=company_id
        )

        assert total == 1
        assert len(result) == 1
        assert result[0]["original_filename"] == sample_portal_document.original_filename

    @pytest.mark.asyncio
    async def test_get_documents_filter_by_type(
        self, document_service, mock_db, sample_portal_document, entity_id, company_id
    ):
        sample_portal_document.document_type = "invoice"
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=1),
            create_mock_result(scalars_list=[sample_portal_document]),
        ]

        result, total = await document_service.get_documents(
            entity_id=entity_id, company_id=company_id, document_type="invoice"
        )

        assert total == 1
        for doc in result:
            assert doc["document_type"] == "invoice"

    @pytest.mark.asyncio
    async def test_get_documents_empty(
        self, document_service, mock_db, entity_id, company_id
    ):
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=0),
            create_mock_result(scalars_list=[]),
        ]

        result, total = await document_service.get_documents(
            entity_id=entity_id, company_id=company_id
        )

        assert total == 0
        assert result == []


# ========================= Get Document Detail Tests =========================


class TestGetDocumentDetail:
    """Tests fuer get_document_detail() Methode (gibt dict | None)."""

    @pytest.mark.asyncio
    async def test_get_document_detail_success(
        self, document_service, mock_db, sample_portal_document, entity_id, company_id
    ):
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_portal_document
        )

        result = await document_service.get_document_detail(
            document_id=sample_portal_document.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        assert result["id"] == str(sample_portal_document.id)

    @pytest.mark.asyncio
    async def test_get_document_detail_not_found(
        self, document_service, mock_db, entity_id, company_id
    ):
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await document_service.get_document_detail(
            document_id=uuid4(), entity_id=entity_id, company_id=company_id
        )

        assert result is None


# ========================= Get Document Content (Download) Tests =========================


class TestGetDocumentContent:
    """Tests fuer get_document_content() Methode."""

    @pytest.mark.asyncio
    async def test_get_content_success(
        self, document_service, mock_db, sample_portal_document, entity_id, company_id,
        storage_dir,
    ):
        """Sollte (content, filename, mime) zurueckgeben wenn Datei existiert."""
        # Datei real auf Platte anlegen, storage_path relativ setzen
        rel_path = "doc.pdf"
        full = os.path.join(storage_dir, rel_path)
        with open(full, "wb") as f:
            f.write(b"%PDF-1.4 stored content")
        sample_portal_document.storage_path = rel_path
        sample_portal_document.mime_type = "application/pdf"

        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_portal_document
        )

        out = await document_service.get_document_content(
            document_id=sample_portal_document.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert out is not None
        content, filename, mime_type = out
        assert content == b"%PDF-1.4 stored content"
        assert filename == sample_portal_document.original_filename
        assert mime_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_get_content_not_found(
        self, document_service, mock_db, entity_id, company_id
    ):
        """Sollte None zurueckgeben wenn Dokument nicht gefunden (keine Exception)."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        out = await document_service.get_document_content(
            document_id=uuid4(), entity_id=entity_id, company_id=company_id
        )

        assert out is None


# ========================= Delete Document Tests =========================


class TestDeleteDocument:
    """Tests fuer delete_document() Methode (gibt bool)."""

    @pytest.mark.asyncio
    async def test_delete_document_success(
        self, document_service, mock_db, sample_portal_document, sample_portal_user
    ):
        """Sollte ausstehendes Dokument loeschen (-> True)."""
        sample_portal_document.storage_path = None  # keine Datei zum Entfernen
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_portal_document
        )

        result = await document_service.delete_document(
            document_id=sample_portal_document.id,
            portal_user=sample_portal_user,
        )

        assert result is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_document_not_found_returns_false(
        self, document_service, mock_db, sample_portal_user
    ):
        """Sollte False zurueckgeben wenn nicht loeschbar (nicht gefunden / verarbeitet)."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await document_service.delete_document(
            document_id=uuid4(),
            portal_user=sample_portal_user,
        )

        assert result is False
        mock_db.delete.assert_not_called()


# ========================= Entity Isolation Tests =========================


class TestEntityIsolation:
    """Tests fuer Entity-Isolation bei Dokumenten."""

    @pytest.mark.asyncio
    async def test_cannot_see_other_entity_documents(
        self, document_service, mock_db, other_entity_id, company_id
    ):
        mock_db.execute.side_effect = [
            create_mock_result(scalar_value=0),
            create_mock_result(scalars_list=[]),
        ]

        result, total = await document_service.get_documents(
            entity_id=other_entity_id, company_id=company_id
        )

        assert total == 0
        assert result == []

    @pytest.mark.asyncio
    async def test_cannot_get_other_entity_document_content(
        self, document_service, mock_db, other_entity_id, company_id
    ):
        """Fremde Entity -> Query liefert None -> get_document_content None."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        out = await document_service.get_document_content(
            document_id=uuid4(), entity_id=other_entity_id, company_id=company_id
        )

        assert out is None


# ========================= Security Tests =========================


class TestSecurityPathTraversal:
    """Tests fuer Path Traversal Angriffe (CWE-22).

    _validate_file lehnt Pfad-Trenner / .. / Null-Bytes im Dateinamen ab.
    """

    @pytest.mark.parametrize(
        "malicious_filename",
        [
            "../../etc/passwd",
            "/etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "..%2F..%2Fetc%2Fpasswd",  # enthaelt '..'
            "legitimate.pdf\x00../../etc/passwd",  # Null-Byte
        ],
    )
    @pytest.mark.asyncio
    async def test_upload_rejects_path_traversal(
        self, document_service, mock_db, sample_portal_user, malicious_filename
    ):
        with pytest.raises(ValueError, match="(Ungueltiger|nicht erlaubt)"):
            await document_service.upload_document(
                portal_user=sample_portal_user,
                filename=malicious_filename,
                content=b"%PDF-1.4 test content",
                content_type="application/pdf",
            )
        mock_db.add.assert_not_called()


class TestSecurityFileTypeEnforcement:
    """Tests fuer Datei-Typ-Durchsetzung (Allowlist).

    Der Service erzwingt eine Endungs-Allowlist; Content-basiertes
    Magic-Byte-Sniffing ist bewusst NICHT implementiert (dokumentierte Grenze).
    """

    @pytest.mark.asyncio
    async def test_upload_double_extension_rejected(
        self, document_service, mock_db, sample_portal_user
    ):
        """Doppelte Endung document.pdf.exe -> letzte Endung .exe nicht erlaubt."""
        with pytest.raises(ValueError, match="Dateityp nicht erlaubt"):
            await document_service.upload_document(
                portal_user=sample_portal_user,
                filename="document.pdf.exe",
                content=b"%PDF-1.4 test content",
                content_type="application/pdf",
            )
        mock_db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_upload_disallowed_extension_rejected(
        self, document_service, mock_db, sample_portal_user
    ):
        """.zip ist nicht in der Allowlist."""
        with pytest.raises(ValueError, match="Dateityp nicht erlaubt"):
            await document_service.upload_document(
                portal_user=sample_portal_user,
                filename="archiv.zip",
                content=b"PK\x03\x04 zip content",
                content_type="application/zip",
            )
        mock_db.add.assert_not_called()
