# -*- coding: utf-8 -*-
"""
Unit Tests fuer PortalDocumentService.

Testet:
- upload_document()
- get_documents()
- get_document_detail()
- download_document()
- delete_document()
- Dateityp-Validierung
- Entity-Isolation

Feinpoliert und durchdacht - Portal Document Tests.
"""

from datetime import datetime, timezone, timedelta
from io import BytesIO
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.services.portal.portal_document_service import (
    PortalDocumentService,
    get_portal_document_service,
)
from .conftest import create_mock_result


# ========================= Test Fixtures =========================


@pytest.fixture
def document_service(mock_db: AsyncMock) -> PortalDocumentService:
    """Create PortalDocumentService instance with mocked db."""
    return PortalDocumentService(mock_db)


@pytest.fixture
def mock_storage():
    """Mock storage service."""
    storage = MagicMock()
    storage.upload_file = AsyncMock(return_value="path/to/file.pdf")
    storage.download_file = AsyncMock(return_value=b"%PDF-1.4 mock content")
    storage.delete_file = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def mock_pdf_file():
    """Mock PDF file for upload."""
    return BytesIO(b"%PDF-1.4 test content")


@pytest.fixture
def mock_image_file():
    """Mock image file for upload."""
    return BytesIO(b"\x89PNG\r\n\x1a\n test content")


# ========================= Factory Function Tests =========================


class TestFactoryFunction:
    """Tests fuer get_portal_document_service Factory."""

    def test_get_portal_document_service_returns_instance(self, mock_db: AsyncMock):
        """Factory sollte PortalDocumentService-Instanz zurueckgeben."""
        service = get_portal_document_service(mock_db)

        assert isinstance(service, PortalDocumentService)
        assert service.db is mock_db


# ========================= Upload Document Tests =========================


class TestUploadDocument:
    """Tests fuer upload_document() Methode."""

    @pytest.mark.asyncio
    async def test_upload_pdf_success(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte PDF erfolgreich hochladen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch.object(document_service, "storage", mock_storage):
            doc = await document_service.upload_document(
                entity_id=entity_id,
                company_id=company_id,
                uploaded_by_id=portal_user_id,
                file_content=mock_pdf_file,
                original_filename="rechnung.pdf",
                mime_type="application/pdf",
                file_size=1024,
            )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_image_success(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_image_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Bild erfolgreich hochladen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch.object(document_service, "storage", mock_storage):
            doc = await document_service.upload_document(
                entity_id=entity_id,
                company_id=company_id,
                uploaded_by_id=portal_user_id,
                file_content=mock_image_file,
                original_filename="beleg.png",
                mime_type="image/png",
                file_size=2048,
            )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_with_description(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Dokument mit Beschreibung hochladen."""
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch.object(document_service, "storage", mock_storage):
            await document_service.upload_document(
                entity_id=entity_id,
                company_id=company_id,
                uploaded_by_id=portal_user_id,
                file_content=mock_pdf_file,
                original_filename="vertrag.pdf",
                mime_type="application/pdf",
                file_size=5000,
                description="Signierter Vertrag",
                document_type="contract",
            )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_with_complaint_reference(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Dokument mit Reklamationsbezug hochladen."""
        complaint_id = uuid4()
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch.object(document_service, "storage", mock_storage):
            await document_service.upload_document(
                entity_id=entity_id,
                company_id=company_id,
                uploaded_by_id=portal_user_id,
                file_content=mock_pdf_file,
                original_filename="nachweis.pdf",
                mime_type="application/pdf",
                file_size=3000,
                complaint_id=complaint_id,
            )

        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_invalid_mime_type(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Fehler bei ungueltigem Dateityp werfen."""
        invalid_file = BytesIO(b"executable content")

        with pytest.raises(ValueError, match="Dateityp nicht erlaubt"):
            await document_service.upload_document(
                entity_id=entity_id,
                company_id=company_id,
                uploaded_by_id=portal_user_id,
                file_content=invalid_file,
                original_filename="virus.exe",
                mime_type="application/x-msdownload",
                file_size=1000,
            )

    @pytest.mark.asyncio
    async def test_upload_file_too_large(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Fehler bei zu grosser Datei werfen."""
        # 50MB is typically too large
        large_size = 50 * 1024 * 1024

        with pytest.raises(ValueError, match="Datei zu gross"):
            await document_service.upload_document(
                entity_id=entity_id,
                company_id=company_id,
                uploaded_by_id=portal_user_id,
                file_content=mock_pdf_file,
                original_filename="huge.pdf",
                mime_type="application/pdf",
                file_size=large_size,
            )


# ========================= Get Documents Tests =========================


class TestGetDocuments:
    """Tests fuer get_documents() Methode."""

    @pytest.mark.asyncio
    async def test_get_documents_success(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        sample_portal_document,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Dokumente zurueckgeben."""
        documents = [sample_portal_document]

        count_result = create_mock_result(scalar_value=1)
        list_result = create_mock_result(scalars_list=documents)
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await document_service.get_documents(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 1
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_documents_filter_by_type(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        sample_portal_document,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte nach Dokumenttyp filtern."""
        sample_portal_document.document_type = "invoice"

        count_result = create_mock_result(scalar_value=1)
        list_result = create_mock_result(scalars_list=[sample_portal_document])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await document_service.get_documents(
            entity_id=entity_id,
            company_id=company_id,
            document_type="invoice",
        )

        assert total == 1
        for doc in result:
            assert doc.document_type == "invoice"

    @pytest.mark.asyncio
    async def test_get_documents_empty(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte leere Liste bei keinen Dokumenten."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await document_service.get_documents(
            entity_id=entity_id,
            company_id=company_id,
        )

        assert total == 0
        assert result == []


# ========================= Get Document Detail Tests =========================


class TestGetDocumentDetail:
    """Tests fuer get_document_detail() Methode."""

    @pytest.mark.asyncio
    async def test_get_document_detail_success(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        sample_portal_document,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Dokumentdetails zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_portal_document
        )

        result = await document_service.get_document_detail(
            document_id=sample_portal_document.id,
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is not None
        assert result.id == sample_portal_document.id

    @pytest.mark.asyncio
    async def test_get_document_detail_not_found(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte None zurueckgeben wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        result = await document_service.get_document_detail(
            document_id=uuid4(),
            entity_id=entity_id,
            company_id=company_id,
        )

        assert result is None


# ========================= Download Document Tests =========================


class TestDownloadDocument:
    """Tests fuer download_document() Methode."""

    @pytest.mark.asyncio
    async def test_download_document_success(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        sample_portal_document,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Dokument-Inhalt zurueckgeben."""
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_portal_document
        )

        with patch.object(document_service, "storage", mock_storage):
            content, filename, mime_type = await document_service.download_document(
                document_id=sample_portal_document.id,
                entity_id=entity_id,
                company_id=company_id,
            )

        assert content is not None
        assert filename == sample_portal_document.original_filename
        mock_storage.download_file.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_document_not_found(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht gefunden."""
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await document_service.download_document(
                document_id=uuid4(),
                entity_id=entity_id,
                company_id=company_id,
            )


# ========================= Delete Document Tests =========================


class TestDeleteDocument:
    """Tests fuer delete_document() Methode."""

    @pytest.mark.asyncio
    async def test_delete_document_success(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        sample_portal_document,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Dokument erfolgreich loeschen."""
        sample_portal_document.uploaded_by_id = portal_user_id
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_portal_document
        )
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()

        with patch.object(document_service, "storage", mock_storage):
            await document_service.delete_document(
                document_id=sample_portal_document.id,
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=portal_user_id,
            )

        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_document_not_owner(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        sample_portal_document,
        entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Fehler werfen wenn nicht Eigentuemer."""
        sample_portal_document.uploaded_by_id = uuid4()  # Different user
        mock_db.execute.return_value = create_mock_result(
            scalar_value=sample_portal_document
        )

        other_user_id = uuid4()
        with pytest.raises(ValueError, match="Keine Berechtigung"):
            await document_service.delete_document(
                document_id=sample_portal_document.id,
                entity_id=entity_id,
                company_id=company_id,
                portal_user_id=other_user_id,
            )


# ========================= Entity Isolation Tests =========================


class TestEntityIsolation:
    """Tests fuer Entity-Isolation bei Dokumenten."""

    @pytest.mark.asyncio
    async def test_cannot_see_other_entity_documents(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Entity A sollte keine Dokumente von Entity B sehen."""
        count_result = create_mock_result(scalar_value=0)
        list_result = create_mock_result(scalars_list=[])
        mock_db.execute.side_effect = [count_result, list_result]

        result, total = await document_service.get_documents(
            entity_id=other_entity_id,
            company_id=company_id,
        )

        assert total == 0
        assert result == []

    @pytest.mark.asyncio
    async def test_cannot_download_other_entity_document(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        sample_portal_document,
        other_entity_id: UUID,
        company_id: UUID,
    ):
        """Sollte Dokument anderer Entity nicht herunterladen koennen."""
        # Query returns None for wrong entity
        mock_db.execute.return_value = create_mock_result(scalar_value=None)

        with pytest.raises(ValueError, match="nicht gefunden"):
            await document_service.download_document(
                document_id=sample_portal_document.id,
                entity_id=other_entity_id,
                company_id=company_id,
            )


# ========================= Security Tests =========================


class TestSecurityPathTraversal:
    """Tests fuer Path Traversal Angriffe (CWE-22)."""

    @pytest.mark.asyncio
    async def test_upload_document_path_traversal_parent_dir(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Path Traversal mit ../etc/passwd blockieren."""
        malicious_filename = "../../etc/passwd"

        with pytest.raises(ValueError, match="(Ungueltiger|Invalid|nicht erlaubt)"):
            with patch.object(document_service, "storage", mock_storage):
                await document_service.upload_document(
                    file_content=mock_pdf_file,
                    original_filename=malicious_filename,
                    content_type="application/pdf",
                    entity_id=entity_id,
                    company_id=company_id,
                    portal_user_id=portal_user_id,
                )

    @pytest.mark.asyncio
    async def test_upload_document_path_traversal_absolute_path(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte absolute Pfade blockieren."""
        malicious_filename = "/etc/passwd"

        with pytest.raises(ValueError, match="(Ungueltiger|Invalid|nicht erlaubt)"):
            with patch.object(document_service, "storage", mock_storage):
                await document_service.upload_document(
                    file_content=mock_pdf_file,
                    original_filename=malicious_filename,
                    content_type="application/pdf",
                    entity_id=entity_id,
                    company_id=company_id,
                    portal_user_id=portal_user_id,
                )

    @pytest.mark.asyncio
    async def test_upload_document_path_traversal_windows_path(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Windows-Pfade blockieren."""
        malicious_filename = "..\\..\\windows\\system32\\config\\sam"

        with pytest.raises(ValueError, match="(Ungueltiger|Invalid|nicht erlaubt)"):
            with patch.object(document_service, "storage", mock_storage):
                await document_service.upload_document(
                    file_content=mock_pdf_file,
                    original_filename=malicious_filename,
                    content_type="application/pdf",
                    entity_id=entity_id,
                    company_id=company_id,
                    portal_user_id=portal_user_id,
                )

    @pytest.mark.asyncio
    async def test_upload_document_path_traversal_url_encoded(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte URL-kodierte Path Traversal blockieren."""
        malicious_filename = "..%2F..%2Fetc%2Fpasswd"

        with pytest.raises(ValueError, match="(Ungueltiger|Invalid|nicht erlaubt)"):
            with patch.object(document_service, "storage", mock_storage):
                await document_service.upload_document(
                    file_content=mock_pdf_file,
                    original_filename=malicious_filename,
                    content_type="application/pdf",
                    entity_id=entity_id,
                    company_id=company_id,
                    portal_user_id=portal_user_id,
                )

    @pytest.mark.asyncio
    async def test_upload_document_path_traversal_null_byte(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte Null-Byte Injection blockieren."""
        malicious_filename = "legitimate.pdf\x00../../etc/passwd"

        with pytest.raises(ValueError, match="(Ungueltiger|Invalid|nicht erlaubt)"):
            with patch.object(document_service, "storage", mock_storage):
                await document_service.upload_document(
                    file_content=mock_pdf_file,
                    original_filename=malicious_filename,
                    content_type="application/pdf",
                    entity_id=entity_id,
                    company_id=company_id,
                    portal_user_id=portal_user_id,
                )


class TestSecurityMIMESpoofing:
    """Tests fuer MIME Type Spoofing Angriffe."""

    @pytest.mark.asyncio
    async def test_upload_document_mime_type_mismatch_exe_as_pdf(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte EXE-Datei getarnt als PDF ablehnen."""
        # EXE magic bytes: MZ
        exe_content = BytesIO(b"MZ\x90\x00\x03\x00\x00\x00fake exe content")

        with pytest.raises(ValueError, match="(Dateityp|MIME|nicht erlaubt|ungueltig)"):
            with patch.object(document_service, "storage", mock_storage):
                await document_service.upload_document(
                    file_content=exe_content,
                    original_filename="invoice.pdf",
                    content_type="application/pdf",  # Falscher MIME-Typ
                    entity_id=entity_id,
                    company_id=company_id,
                    portal_user_id=portal_user_id,
                )

    @pytest.mark.asyncio
    async def test_upload_document_double_extension(
        self,
        document_service: PortalDocumentService,
        mock_db: AsyncMock,
        mock_storage,
        mock_pdf_file,
        entity_id: UUID,
        company_id: UUID,
        portal_user_id: UUID,
    ):
        """Sollte doppelte Dateiendungen ablehnen."""
        double_extension_filename = "document.pdf.exe"

        with pytest.raises(ValueError, match="(Dateityp|Erweiterung|nicht erlaubt)"):
            with patch.object(document_service, "storage", mock_storage):
                await document_service.upload_document(
                    file_content=mock_pdf_file,
                    original_filename=double_extension_filename,
                    content_type="application/pdf",
                    entity_id=entity_id,
                    company_id=company_id,
                    portal_user_id=portal_user_id,
                )
