# -*- coding: utf-8 -*-
"""
Unit-Tests für Document Service.

Testet:
- CRUD-Operationen (Create, Read, Update, Delete)
- Filterung und Pagination
- Batch-Operationen (Delete, Tag, Export)
- Export-Formate (JSON, CSV, ZIP, PDF)
- Cache-Invalidierung
- Fehlerbehandlung

Feinpoliert und durchdacht - Umfassende Service-Tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json
import csv
import io
import zipfile


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_db_session():
    """Create mock database session."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.delete = AsyncMock()
    session.rollback = AsyncMock()
    session.add = Mock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def sample_user_id() -> UUID:
    """Provide sample user ID."""
    return uuid4()


@pytest.fixture
def sample_document_id() -> UUID:
    """Provide sample document ID."""
    return uuid4()


@pytest.fixture
def mock_document(sample_document_id, sample_user_id):
    """Create mock document."""
    doc = Mock()
    doc.id = sample_document_id
    doc.owner_id = sample_user_id
    doc.filename = "test_document.pdf"
    doc.original_filename = "Original Test Document.pdf"
    doc.file_path = "/documents/test_document.pdf"
    doc.file_size = 1024 * 100  # 100 KB
    doc.mime_type = "application/pdf"
    doc.checksum = "abc123def456"
    doc.document_type = "invoice"
    doc.status = "completed"
    doc.page_count = 3
    doc.extracted_text = "Dies ist ein Testdokument mit deutschen Umlauten: ä, ö, ü, ß"
    doc.ocr_backend_used = "deepseek"
    doc.ocr_confidence = 0.95
    doc.processing_duration_ms = 1500.0
    doc.has_umlauts = True
    doc.german_validation_score = 0.98
    doc.detected_language = "de"
    doc.document_metadata = {"source": "scan", "priority": "high"}
    doc.tags = []
    doc.upload_date = datetime.now(timezone.utc) - timedelta(days=1)
    doc.processed_date = datetime.now(timezone.utc)
    doc.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    doc.updated_at = datetime.now(timezone.utc)
    doc.current_version_number = 1
    doc.total_versions = 1
    doc.embedding = [0.1, 0.2, 0.3]  # Mock embedding
    doc.embedding_updated_at = datetime.now(timezone.utc)
    doc.embedding_model = "multilingual-e5-large"
    # Quick Classification Feature (hinzugefuegt Januar 2026)
    doc.quick_classification_status = "completed"
    doc.quick_classification_result = {"document_type": "invoice", "confidence": 0.95}
    return doc


@pytest.fixture
def mock_tag():
    """Create mock tag."""
    tag = Mock()
    tag.id = uuid4()
    tag.name = "rechnung"
    tag.description = "Rechnungsdokumente"
    tag.color = "#FF5733"
    tag.created_at = datetime.now(timezone.utc)
    return tag


@pytest.fixture
def document_service():
    """Create DocumentService instance."""
    from app.services.document_service import DocumentService
    return DocumentService()


# ========================= CRUD Tests =========================


class TestDocumentServiceGetDocument:
    """Tests for get_document method."""

    @pytest.mark.asyncio
    async def test_get_document_success(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Dokument erfolgreich abrufen."""
        # Setup mock
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        # Execute
        result = await document_service.get_document(
            mock_db_session,
            mock_document.id,
            sample_user_id
        )

        # Verify
        assert result is not None
        assert result.id == mock_document.id
        assert result.filename == mock_document.filename
        mock_db_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_document_not_found(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Nicht existierendes Dokument sollte None zurückgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await document_service.get_document(
            mock_db_session,
            uuid4(),
            sample_user_id
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_document_wrong_owner(
        self, document_service, mock_db_session, mock_document
    ):
        """Dokument eines anderen Benutzers sollte nicht gefunden werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await document_service.get_document(
            mock_db_session,
            mock_document.id,
            uuid4()  # Different user
        )

        assert result is None


class TestDocumentServiceListDocuments:
    """Tests for list_documents method."""

    @pytest.mark.asyncio
    async def test_list_documents_success(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Dokumentenliste erfolgreich abrufen."""
        # Setup mocks
        mock_docs_result = Mock()
        mock_docs_result.scalars.return_value.all.return_value = [mock_document]

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_docs_result, mock_count_result]

        # Execute
        result = await document_service.list_documents(
            mock_db_session,
            sample_user_id,
            page=1,
            per_page=20
        )

        # Verify
        assert result.total == 1
        assert result.page == 1
        assert result.per_page == 20
        assert len(result.documents) == 1
        assert result.has_next is False
        assert result.has_prev is False

    @pytest.mark.asyncio
    async def test_list_documents_pagination(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Pagination sollte korrekt funktionieren."""
        # 25 total documents, page 2 of 3
        mock_docs_result = Mock()
        mock_docs_result.scalars.return_value.all.return_value = [mock_document] * 10

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 25

        mock_db_session.execute.side_effect = [mock_docs_result, mock_count_result]

        result = await document_service.list_documents(
            mock_db_session,
            sample_user_id,
            page=2,
            per_page=10
        )

        assert result.total == 25
        assert result.page == 2
        assert result.total_pages == 3
        assert result.has_next is True
        assert result.has_prev is True

    @pytest.mark.asyncio
    async def test_list_documents_with_filters(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Filterung sollte angewendet werden."""
        from app.db.schemas import SearchFilters, DocumentType

        mock_docs_result = Mock()
        mock_docs_result.scalars.return_value.all.return_value = [mock_document]

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 1

        mock_db_session.execute.side_effect = [mock_docs_result, mock_count_result]

        filters = SearchFilters(
            document_type=DocumentType.INVOICE,
            language="de",
            confidence_min=0.8
        )

        result = await document_service.list_documents(
            mock_db_session,
            sample_user_id,
            filters=filters
        )

        assert result.total == 1
        assert "document_type" in result.filters_applied

    @pytest.mark.asyncio
    async def test_list_documents_empty(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Leere Liste bei keinen Dokumenten."""
        mock_docs_result = Mock()
        mock_docs_result.scalars.return_value.all.return_value = []

        mock_count_result = Mock()
        mock_count_result.scalar.return_value = 0

        mock_db_session.execute.side_effect = [mock_docs_result, mock_count_result]

        result = await document_service.list_documents(
            mock_db_session,
            sample_user_id
        )

        assert result.total == 0
        assert len(result.documents) == 0
        assert result.total_pages == 0


class TestDocumentServiceUpdateDocument:
    """Tests for update_document method."""

    @pytest.mark.asyncio
    async def test_update_document_success(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Dokument erfolgreich aktualisieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        # Mock search service
        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            result = await document_service.update_document(
                mock_db_session,
                mock_document.id,
                sample_user_id,
                language="de"
            )

            assert result is not None
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_document_not_found(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Update auf nicht existierendes Dokument sollte None zurückgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await document_service.update_document(
            mock_db_session,
            uuid4(),
            sample_user_id,
            language="en"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_update_document_with_tags(
        self, document_service, mock_db_session, mock_document, sample_user_id, mock_tag
    ):
        """Dokument-Tags aktualisieren."""
        # Set mock_document.tags to include the mock_tag for response
        mock_document.tags = [mock_tag]

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        # Mock tag query - returns mock_tag with all required attributes
        mock_tags_result = Mock()
        mock_tags_result.scalars.return_value.all.return_value = [mock_tag]

        mock_db_session.execute.side_effect = [mock_result, mock_tags_result]

        # Ensure db.refresh keeps the tags
        async def mock_refresh(obj):
            obj.tags = [mock_tag]

        mock_db_session.refresh = AsyncMock(side_effect=mock_refresh)

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            result = await document_service.update_document(
                mock_db_session,
                mock_document.id,
                sample_user_id,
                tags=["rechnung", "wichtig"]
            )

            assert result is not None


class TestDocumentServiceDeleteDocument:
    """Tests for delete_document method."""

    @pytest.mark.asyncio
    async def test_delete_document_success(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Dokument erfolgreich löschen."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            result = await document_service.delete_document(
                mock_db_session,
                mock_document.id,
                sample_user_id
            )

            assert result is True
            mock_db_session.delete.assert_called_once_with(mock_document)
            mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_document_not_found(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Löschen eines nicht existierenden Dokuments sollte False zurückgeben."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await document_service.delete_document(
            mock_db_session,
            uuid4(),
            sample_user_id
        )

        assert result is False
        mock_db_session.delete.assert_not_called()


# ========================= Batch Operation Tests =========================


class TestDocumentServiceBatchDelete:
    """Tests for batch_delete method."""

    @pytest.mark.asyncio
    async def test_batch_delete_success(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Batch-Löschung erfolgreich durchführen."""
        doc_ids = [uuid4(), uuid4(), uuid4()]

        # Mock found documents
        mock_found_result = Mock()
        mock_found_result.fetchall.return_value = [(doc_ids[0],), (doc_ids[1],), (doc_ids[2],)]

        # Mock delete result
        mock_delete_result = Mock()
        mock_delete_result.rowcount = 3

        mock_db_session.execute.side_effect = [mock_found_result, mock_delete_result]

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            result = await document_service.batch_delete(
                mock_db_session,
                doc_ids,
                sample_user_id
            )

            assert result.success is True
            assert result.processed == 3
            assert result.failed == 0
            # Default ist soft_delete=True, daher "soft_delete" als operation
            assert result.operation == "soft_delete"

    @pytest.mark.asyncio
    async def test_batch_delete_partial_success(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Batch-Löschung mit einigen nicht gefundenen Dokumenten."""
        doc_ids = [uuid4(), uuid4(), uuid4()]

        # Only 2 of 3 found
        mock_found_result = Mock()
        mock_found_result.fetchall.return_value = [(doc_ids[0],), (doc_ids[1],)]

        mock_delete_result = Mock()
        mock_delete_result.rowcount = 2

        mock_db_session.execute.side_effect = [mock_found_result, mock_delete_result]

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            result = await document_service.batch_delete(
                mock_db_session,
                doc_ids,
                sample_user_id
            )

            assert result.success is False
            assert result.processed == 2
            assert result.failed == 1
            assert len(result.errors) == 1

    @pytest.mark.asyncio
    async def test_batch_delete_empty_list(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Batch-Löschung mit leerer Liste."""
        result = await document_service.batch_delete(
            mock_db_session,
            [],
            sample_user_id
        )

        assert result.success is True
        assert result.processed == 0
        assert result.total_requested == 0

    @pytest.mark.asyncio
    async def test_batch_delete_database_error(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Batch-Löschung bei Datenbankfehler."""
        doc_ids = [uuid4()]
        mock_db_session.execute.side_effect = Exception("Database error")

        result = await document_service.batch_delete(
            mock_db_session,
            doc_ids,
            sample_user_id
        )

        assert result.success is False
        assert result.failed == 1
        mock_db_session.rollback.assert_called_once()


class TestDocumentServiceBatchTag:
    """Tests for batch_tag method."""

    @pytest.mark.asyncio
    async def test_batch_tag_add_success(
        self, document_service, mock_db_session, mock_document, sample_user_id, mock_tag
    ):
        """Tags hinzufügen erfolgreich."""
        from app.db.schemas import TagOperation

        mock_document.tags = []

        # Mock document lookup - scalars().all() returns a LIST of documents
        mock_doc_result = Mock()
        mock_doc_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_doc_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            with patch.object(document_service, '_ensure_tags_exist', new_callable=AsyncMock) as mock_ensure_tags:
                mock_ensure_tags.return_value = [mock_tag]

                result = await document_service.batch_tag(
                    mock_db_session,
                    [mock_document.id],
                    ["rechnung"],
                    sample_user_id,
                    operation=TagOperation.ADD
                )

                assert result.success is True
                assert result.processed == 1

    @pytest.mark.asyncio
    async def test_batch_tag_remove_success(
        self, document_service, mock_db_session, mock_document, sample_user_id, mock_tag
    ):
        """Tags entfernen erfolgreich."""
        from app.db.schemas import TagOperation

        mock_document.tags = [mock_tag]

        # Mock document lookup - scalars().all() returns a LIST of documents
        mock_doc_result = Mock()
        mock_doc_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_doc_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            with patch.object(document_service, '_ensure_tags_exist', new_callable=AsyncMock) as mock_ensure_tags:
                mock_ensure_tags.return_value = [mock_tag]

                result = await document_service.batch_tag(
                    mock_db_session,
                    [mock_document.id],
                    ["rechnung"],
                    sample_user_id,
                    operation=TagOperation.REMOVE
                )

                assert result.success is True

    @pytest.mark.asyncio
    async def test_batch_tag_set_success(
        self, document_service, mock_db_session, mock_document, sample_user_id, mock_tag
    ):
        """Tags komplett ersetzen erfolgreich."""
        from app.db.schemas import TagOperation

        mock_document.tags = []

        # Mock document lookup - scalars().all() returns a LIST of documents
        mock_doc_result = Mock()
        mock_doc_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_doc_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            with patch.object(document_service, '_ensure_tags_exist', new_callable=AsyncMock) as mock_ensure_tags:
                mock_ensure_tags.return_value = [mock_tag]

                result = await document_service.batch_tag(
                    mock_db_session,
                    [mock_document.id],
                    ["rechnung"],
                    sample_user_id,
                    operation=TagOperation.SET
                )

                assert result.success is True


# ========================= Export Tests =========================


class TestDocumentServiceBatchExport:
    """Tests for batch_export method."""

    @pytest.mark.asyncio
    async def test_export_json(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """JSON-Export erfolgreich."""
        from app.db.schemas import ExportFormat

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_result

        data, content_type, result = await document_service.batch_export(
            mock_db_session,
            [mock_document.id],
            sample_user_id,
            format=ExportFormat.JSON
        )

        assert content_type == "application/json"
        assert result.success is True
        assert result.processed == 1

        # Verify JSON is valid
        parsed = json.loads(data.decode("utf-8"))
        assert len(parsed) == 1
        assert parsed[0]["filename"] == mock_document.filename

    @pytest.mark.asyncio
    async def test_export_csv(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """CSV-Export erfolgreich."""
        from app.db.schemas import ExportFormat

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_result

        data, content_type, result = await document_service.batch_export(
            mock_db_session,
            [mock_document.id],
            sample_user_id,
            format=ExportFormat.CSV
        )

        assert content_type == "text/csv"
        assert result.success is True

        # Verify CSV is valid
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1

    @pytest.mark.asyncio
    async def test_export_zip(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """ZIP-Export erfolgreich."""
        from app.db.schemas import ExportFormat

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_result

        data, content_type, result = await document_service.batch_export(
            mock_db_session,
            [mock_document.id],
            sample_user_id,
            format=ExportFormat.ZIP
        )

        assert content_type == "application/zip"
        assert result.success is True

        # Verify ZIP is valid
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert len(zf.namelist()) == 1

    @pytest.mark.asyncio
    async def test_export_with_missing_documents(
        self, document_service, mock_db_session, sample_user_id
    ):
        """Export mit fehlenden Dokumenten."""
        from app.db.schemas import ExportFormat

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        doc_ids = [uuid4(), uuid4()]

        data, content_type, result = await document_service.batch_export(
            mock_db_session,
            doc_ids,
            sample_user_id,
            format=ExportFormat.JSON
        )

        assert result.processed == 0
        assert result.failed == 2
        assert len(result.errors) == 2

    @pytest.mark.asyncio
    async def test_export_without_text(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Export ohne extrahierten Text."""
        from app.db.schemas import ExportFormat

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_result

        data, content_type, result = await document_service.batch_export(
            mock_db_session,
            [mock_document.id],
            sample_user_id,
            format=ExportFormat.JSON,
            include_text=False
        )

        parsed = json.loads(data.decode("utf-8"))
        assert "extracted_text" not in parsed[0]


# ========================= Filter Tests =========================


class TestDocumentServiceFilters:
    """Tests for filter building."""

    def test_build_filter_conditions_document_type(self, document_service):
        """Filter nach Dokumenttyp."""
        from app.db.schemas import SearchFilters, DocumentType

        filters = SearchFilters(document_type=DocumentType.INVOICE)
        conditions = document_service._build_filter_conditions(filters)

        assert len(conditions) == 1

    def test_build_filter_conditions_date_range(self, document_service):
        """Filter nach Datumsbereich."""
        from app.db.schemas import SearchFilters

        filters = SearchFilters(
            date_from=datetime.now(timezone.utc) - timedelta(days=7),
            date_to=datetime.now(timezone.utc)
        )
        conditions = document_service._build_filter_conditions(filters)

        assert len(conditions) == 2

    def test_build_filter_conditions_confidence(self, document_service):
        """Filter nach Konfidenz."""
        from app.db.schemas import SearchFilters

        filters = SearchFilters(confidence_min=0.8)
        conditions = document_service._build_filter_conditions(filters)

        assert len(conditions) == 1

    def test_build_filter_conditions_has_embedding(self, document_service):
        """Filter nach Embedding-Verfügbarkeit."""
        from app.db.schemas import SearchFilters

        filters = SearchFilters(has_embedding=True)
        conditions = document_service._build_filter_conditions(filters)

        assert len(conditions) == 1

    def test_build_filter_conditions_language(self, document_service):
        """Filter nach Sprache."""
        from app.db.schemas import SearchFilters

        filters = SearchFilters(language="de")
        conditions = document_service._build_filter_conditions(filters)

        assert len(conditions) == 1

    def test_build_filter_conditions_multiple(self, document_service):
        """Mehrere Filter kombiniert."""
        from app.db.schemas import SearchFilters, DocumentType, ProcessingStatus

        filters = SearchFilters(
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            language="de",
            confidence_min=0.8,
            has_embedding=True
        )
        conditions = document_service._build_filter_conditions(filters)

        assert len(conditions) == 5


# ========================= Sort Tests =========================


class TestDocumentServiceSorting:
    """Tests for sorting."""

    def test_get_sort_column_created_at(self, document_service):
        """Sortierung nach Erstellungsdatum."""
        from app.db.schemas import SortField
        from app.db.models import Document

        column = document_service._get_sort_column(SortField.CREATED_AT)
        assert column.key == Document.created_at.key

    def test_get_sort_column_filename(self, document_service):
        """Sortierung nach Dateiname."""
        from app.db.schemas import SortField
        from app.db.models import Document

        column = document_service._get_sort_column(SortField.FILENAME)
        assert column.key == Document.filename.key

    def test_get_sort_column_file_size(self, document_service):
        """Sortierung nach Dateigröße."""
        from app.db.schemas import SortField
        from app.db.models import Document

        column = document_service._get_sort_column(SortField.FILE_SIZE)
        assert column.key == Document.file_size.key


# ========================= Conversion Tests =========================


class TestDocumentServiceConversions:
    """Tests for document conversions."""

    def test_to_summary(self, document_service, mock_document):
        """Dokument zu Summary konvertieren."""
        summary = document_service._to_summary(mock_document)

        assert summary.id == mock_document.id
        assert summary.filename == mock_document.filename
        assert summary.file_size == mock_document.file_size
        assert summary.has_embedding is True

    def test_to_detail_response(self, document_service, mock_document):
        """Dokument zu DetailResponse konvertieren."""
        response = document_service._to_detail_response(mock_document)

        assert response.id == mock_document.id
        assert response.filename == mock_document.filename
        assert response.extracted_text == mock_document.extracted_text
        assert response.ocr_confidence == mock_document.ocr_confidence
        assert response.has_embedding is True

    def test_to_summary_without_embedding(self, document_service, mock_document):
        """Summary ohne Embedding."""
        mock_document.embedding = None
        summary = document_service._to_summary(mock_document)

        assert summary.has_embedding is False


# ========================= Tag Management Tests =========================


class TestDocumentServiceTagManagement:
    """Tests for tag management."""

    @pytest.mark.asyncio
    async def test_ensure_tags_exist_new_tags(
        self, document_service, mock_db_session
    ):
        """Neue Tags erstellen."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        tags = await document_service._ensure_tags_exist(
            mock_db_session,
            ["neu1", "neu2"]
        )

        assert len(tags) == 2
        assert mock_db_session.add.call_count == 2
        mock_db_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_tags_exist_existing_tags(
        self, document_service, mock_db_session, mock_tag
    ):
        """Vorhandene Tags verwenden."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_tag]
        mock_db_session.execute.return_value = mock_result

        tags = await document_service._ensure_tags_exist(
            mock_db_session,
            [mock_tag.name]
        )

        assert len(tags) == 1
        assert tags[0] == mock_tag
        mock_db_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_ensure_tags_exist_empty_list(
        self, document_service, mock_db_session
    ):
        """Leere Tag-Liste."""
        tags = await document_service._ensure_tags_exist(
            mock_db_session,
            []
        )

        assert len(tags) == 0
        mock_db_session.execute.assert_not_called()


# ========================= Cache Invalidation Tests =========================


class TestDocumentServiceCacheInvalidation:
    """Tests for cache invalidation."""

    @pytest.mark.asyncio
    async def test_update_invalidates_cache(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Update sollte Cache invalidieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            await document_service.update_document(
                mock_db_session,
                mock_document.id,
                sample_user_id,
                language="en"
            )

            mock_search_service.invalidate_document_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_invalidates_cache(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Delete sollte Cache invalidieren."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            await document_service.delete_document(
                mock_db_session,
                mock_document.id,
                sample_user_id
            )

            mock_search_service.invalidate_document_cache.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_invalidation_failure_handled(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Cache-Invalidierungsfehler sollte abgefangen werden."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search_service.invalidate_document_cache.side_effect = Exception("Cache error")
            mock_search.return_value = mock_search_service

            # Should not raise
            result = await document_service.update_document(
                mock_db_session,
                mock_document.id,
                sample_user_id,
                language="en"
            )

            assert result is not None

    @pytest.mark.asyncio
    async def test_delete_calls_central_cache_invalidation(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Delete sollte zentrale Cache-Invalidation aufrufen."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            with patch('app.services.document_service.invalidate_on_document_change') as mock_invalidate:
                mock_invalidate.return_value = {"deleted": 5}

                await document_service.delete_document(
                    mock_db_session,
                    mock_document.id,
                    sample_user_id
                )

                mock_invalidate.assert_called_once_with(
                    str(mock_document.id),
                    change_type="delete"
                )

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Refactored: soft_delete_document delegiert an GDPRService, Cache-Invalidation dort via _invalidate_central_cache Methode")
    async def test_soft_delete_calls_central_cache_invalidation(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Soft-Delete sollte zentrale Cache-Invalidation aufrufen.

        NOTE: Test uebersprungen - Cache-Invalidation wurde refactored.
        Die Logik liegt jetzt in DocumentGDPRService._invalidate_central_cache()
        und wird in test_document_gdpr_service.py getestet.
        """
        mock_document.deleted_at = None
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            with patch('app.services.document_service.invalidate_on_document_change') as mock_invalidate:
                mock_invalidate.return_value = {"deleted": 5}

                await document_service.soft_delete_document(
                    mock_db_session,
                    mock_document.id,
                    sample_user_id,
                    reason="test"
                )

                mock_invalidate.assert_called_once_with(
                    str(mock_document.id),
                    change_type="delete"
                )

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Refactored: Cache-Invalidation via _invalidate_central_cache Methode in GDPRService, Fehlerbehandlung dort getestet")
    async def test_central_cache_invalidation_failure_handled(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """Zentrale Cache-Invalidierungsfehler sollte abgefangen werden.

        NOTE: Test uebersprungen - Cache-Invalidation refactored.
        Fehlerbehandlung liegt jetzt in DocumentGDPRService._invalidate_central_cache().
        """
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        with patch('app.services.document_service._get_search_service') as mock_search:
            mock_search_service = AsyncMock()
            mock_search.return_value = mock_search_service

            with patch('app.services.document_service.invalidate_on_document_change') as mock_invalidate:
                mock_invalidate.side_effect = Exception("Central cache error")

                # Should not raise, delete should still succeed
                result = await document_service.delete_document(
                    mock_db_session,
                    mock_document.id,
                    sample_user_id
                )

                assert result is True
                mock_db_session.delete.assert_called_once()


# ========================= Edge Cases =========================


class TestDocumentServiceEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_document_with_no_tags(self, document_service, mock_document):
        """Dokument ohne Tags."""
        mock_document.tags = None
        summary = document_service._to_summary(mock_document)

        assert summary.tags == []

    @pytest.mark.asyncio
    async def test_document_with_no_metadata(self, document_service, mock_document):
        """Dokument ohne Metadaten."""
        mock_document.document_metadata = None
        response = document_service._to_detail_response(mock_document)

        assert response.document_metadata == {}

    @pytest.mark.asyncio
    async def test_document_with_no_document_type(self, document_service, mock_document):
        """Dokument ohne Dokumenttyp."""
        mock_document.document_type = None
        summary = document_service._to_summary(mock_document)

        # Should default to OTHER
        assert summary.document_type.value == "other"

    @pytest.mark.asyncio
    async def test_export_json_with_special_characters(
        self, document_service, mock_db_session, mock_document, sample_user_id
    ):
        """JSON-Export mit Sonderzeichen (Umlaute)."""
        from app.db.schemas import ExportFormat

        mock_document.extracted_text = "Prüfung der Änderungen: äöüß"
        mock_document.filename = "Prüfbericht_2024.pdf"

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db_session.execute.return_value = mock_result

        data, content_type, result = await document_service.batch_export(
            mock_db_session,
            [mock_document.id],
            sample_user_id,
            format=ExportFormat.JSON
        )

        # Verify umlauts are preserved
        content = data.decode("utf-8")
        assert "äöüß" in content
        assert "Prüfbericht" in content


# ========================= Dependency Injection Tests =========================


class TestDocumentServiceDependencyInjection:
    """Tests for dependency injection."""

    def test_get_document_service_singleton(self):
        """get_document_service sollte Singleton zurückgeben."""
        from app.services.document_service import get_document_service

        service1 = get_document_service()
        service2 = get_document_service()

        assert service1 is service2

    def test_document_service_initialization(self, document_service):
        """DocumentService sollte korrekt initialisiert werden."""
        assert document_service is not None
        assert hasattr(document_service, 'get_document')
        assert hasattr(document_service, 'list_documents')
        assert hasattr(document_service, 'batch_delete')
        assert hasattr(document_service, 'batch_export')
