"""Unit-Tests fuer den Document-Service.

Testet CRUD-Operationen und Batch-Verarbeitung mit Mocks.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from uuid import uuid4
from datetime import datetime, timezone
import json

from app.db.schemas import (
    SearchFilters, SortField, SortOrder, DocumentType, ProcessingStatus,
    DocumentSummary, DocumentDetailResponse, BatchOperationResult,
    TagOperation, ExportFormat
)

# Check if document service dependencies are available
try:
    from app.services.document_service import DocumentService
    from app.db.models import Document
    DOCUMENT_SERVICE_AVAILABLE = True
except ImportError:
    DOCUMENT_SERVICE_AVAILABLE = False

# Check if reportlab is available (optional dependency for PDF export)
try:
    import reportlab
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

requires_document_service = pytest.mark.skipif(
    not DOCUMENT_SERVICE_AVAILABLE,
    reason="Document service dependencies not installed (pgvector)"
)

requires_reportlab = pytest.mark.skipif(
    not REPORTLAB_AVAILABLE,
    reason="reportlab not installed (optional PDF export dependency)"
)


class TestDocumentService:
    """Tests fuer DocumentService."""

    @pytest.fixture
    def mock_document(self):
        """Mock Document Objekt."""
        doc = Mock()
        doc.id = uuid4()
        doc.filename = "test.pdf"
        doc.original_filename = "test_original.pdf"
        doc.file_path = "/uploads/test.pdf"
        doc.file_size = 1024
        doc.mime_type = "application/pdf"
        doc.checksum = "abc123"
        doc.document_type = "invoice"
        doc.status = "completed"
        doc.page_count = 2
        doc.extracted_text = "Test Dokument Inhalt"
        doc.ocr_backend_used = "deepseek"
        doc.ocr_confidence = 0.95
        doc.processing_duration_ms = 1500
        doc.has_umlauts = True
        doc.german_validation_score = 0.9
        doc.detected_language = "de"
        doc.document_metadata = {"key": "value"}
        doc.tags = []
        doc.upload_date = datetime.now(timezone.utc)
        doc.processed_date = datetime.now(timezone.utc)
        doc.created_at = datetime.now(timezone.utc)
        doc.updated_at = datetime.now(timezone.utc)
        doc.current_version_number = 1
        doc.total_versions = 1
        doc.embedding = [0.1] * 1024
        doc.embedding_updated_at = datetime.now(timezone.utc)
        doc.embedding_model = "multilingual-e5-large"
        doc.owner_id = uuid4()
        return doc

    @pytest.fixture
    def mock_tag(self):
        """Mock Tag Objekt."""
        tag = Mock()
        tag.id = uuid4()
        tag.name = "Finanzen"
        tag.description = "Finanzielle Dokumente"
        tag.color = "#4a9eff"
        tag.created_at = datetime.now(timezone.utc)
        return tag

    def test_document_summary_creation(self, mock_document):
        """Test DocumentSummary Erstellung."""
        summary = DocumentSummary(
            id=mock_document.id,
            filename=mock_document.filename,
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            file_size=mock_document.file_size,
            page_count=mock_document.page_count,
            ocr_confidence=mock_document.ocr_confidence,
            created_at=mock_document.created_at,
            tags=["Finanzen"],
            has_embedding=True
        )

        assert summary.filename == "test.pdf"
        assert summary.document_type == DocumentType.INVOICE
        assert summary.status == ProcessingStatus.COMPLETED
        assert summary.has_embedding is True

    def test_batch_operation_result(self):
        """Test BatchOperationResult Erstellung."""
        result = BatchOperationResult(
            success=True,
            operation="delete",
            total_requested=5,
            processed=5,
            failed=0,
            errors=[],
            message="5 Dokument(e) erfolgreich geloescht"
        )

        assert result.success is True
        assert result.operation == "delete"
        assert result.processed == 5
        assert result.failed == 0

    def test_batch_operation_result_with_errors(self):
        """Test BatchOperationResult mit Fehlern."""
        from app.db.schemas import BatchOperationError

        errors = [
            BatchOperationError(
                document_id=uuid4(),
                error="Dokument nicht gefunden",
                error_code="NOT_FOUND"
            )
        ]

        result = BatchOperationResult(
            success=False,
            operation="delete",
            total_requested=5,
            processed=4,
            failed=1,
            errors=errors,
            message="4 von 5 Dokument(en) geloescht"
        )

        assert result.success is False
        assert result.failed == 1
        assert len(result.errors) == 1

    def test_tag_operation_enum(self):
        """Test TagOperation Enum."""
        assert TagOperation.ADD.value == "add"
        assert TagOperation.REMOVE.value == "remove"
        assert TagOperation.SET.value == "set"

    def test_export_format_enum(self):
        """Test ExportFormat Enum."""
        assert ExportFormat.JSON.value == "json"
        assert ExportFormat.CSV.value == "csv"
        assert ExportFormat.ZIP.value == "zip"

    @requires_document_service
    def test_document_service_init(self):
        """Test DocumentService Initialisierung."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        # Service sollte ohne Fehler instanziiert werden
        assert service is not None

    @requires_document_service
    def test_build_filter_conditions_empty(self):
        """Test Filter-Bedingungen ohne Filter."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        conditions = service._build_filter_conditions(SearchFilters())
        # Leere Filter sollten leere Liste ergeben
        assert isinstance(conditions, list)

    @requires_document_service
    def test_build_filter_conditions_with_filters(self):
        """Test Filter-Bedingungen mit Filtern."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        filters = SearchFilters(
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            confidence_min=0.8
        )

        conditions = service._build_filter_conditions(filters)
        # Sollte 3 Bedingungen haben
        assert len(conditions) == 3

    @requires_document_service
    def test_get_sort_column(self):
        """Test Sortier-Spalten-Ermittlung."""
        from app.services.document_service import DocumentService
        from app.db.models import Document
        service = DocumentService()

        # Verschiedene Sortierfelder testen
        col_created = service._get_sort_column(SortField.CREATED_AT)
        assert col_created == Document.created_at

        col_filename = service._get_sort_column(SortField.FILENAME)
        assert col_filename == Document.filename

        col_size = service._get_sort_column(SortField.FILE_SIZE)
        assert col_size == Document.file_size

    @requires_document_service
    def test_export_json_format(self, mock_document):
        """Test JSON-Export Format."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        mock_document.tags = []
        documents = [mock_document]

        data, content_type = service._export_json(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/json"

        # JSON parsen und pruefen
        parsed = json.loads(data.decode("utf-8"))
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["filename"] == "test.pdf"
        assert "extracted_text" in parsed[0]
        assert "metadata" in parsed[0]

    @requires_document_service
    def test_export_json_without_text(self, mock_document):
        """Test JSON-Export ohne Text."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        mock_document.tags = []
        documents = [mock_document]

        data, content_type = service._export_json(
            documents, include_text=False, include_metadata=True
        )

        parsed = json.loads(data.decode("utf-8"))
        assert "extracted_text" not in parsed[0]
        assert "metadata" in parsed[0]

    @requires_document_service
    def test_export_csv_format(self, mock_document):
        """Test CSV-Export Format."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        mock_document.tags = []
        documents = [mock_document]

        data, content_type = service._export_csv(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "text/csv"

        # CSV pruefen
        csv_content = data.decode("utf-8")
        assert "id" in csv_content
        assert "filename" in csv_content
        assert "test.pdf" in csv_content

    @requires_document_service
    def test_export_zip_format(self, mock_document):
        """Test ZIP-Export Format."""
        from app.services.document_service import DocumentService
        import zipfile
        import io

        service = DocumentService()

        mock_document.tags = []
        documents = [mock_document]

        data, content_type = service._export_zip(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/zip"

        # ZIP validieren
        zip_buffer = io.BytesIO(data)
        with zipfile.ZipFile(zip_buffer, "r") as zf:
            names = zf.namelist()
            assert len(names) == 1
            assert names[0].endswith(".json")


@requires_document_service
@pytest.mark.asyncio
class TestDocumentServiceAsync:
    """Async-Tests fuer DocumentService."""

    @pytest.fixture
    def mock_db_session(self):
        """Mock Database Session."""
        session = AsyncMock()
        return session

    @pytest.fixture
    def mock_document(self):
        """Mock Document Objekt."""
        doc = Mock()
        doc.id = uuid4()
        doc.filename = "test.pdf"
        doc.original_filename = "test_original.pdf"
        doc.file_path = "/uploads/test.pdf"
        doc.file_size = 1024
        doc.mime_type = "application/pdf"
        doc.checksum = "abc123"
        doc.document_type = "invoice"
        doc.status = "completed"
        doc.page_count = 2
        doc.extracted_text = "Test Dokument Inhalt"
        doc.ocr_backend_used = "deepseek"
        doc.ocr_confidence = 0.95
        doc.processing_duration_ms = 1500
        doc.has_umlauts = True
        doc.german_validation_score = 0.9
        doc.detected_language = "de"
        doc.document_metadata = {}
        doc.tags = []
        doc.upload_date = datetime.now(timezone.utc)
        doc.processed_date = datetime.now(timezone.utc)
        doc.created_at = datetime.now(timezone.utc)
        doc.updated_at = datetime.now(timezone.utc)
        doc.current_version_number = 1
        doc.total_versions = 1
        doc.embedding = None
        doc.embedding_updated_at = None
        doc.embedding_model = None
        doc.owner_id = uuid4()
        return doc

    async def test_get_document_not_found(self, mock_db_session):
        """Test Dokument-Abruf wenn nicht gefunden."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        # Mock execute to return no result (scalar_one_or_none is sync)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await service.get_document(
            mock_db_session,
            document_id=uuid4(),
            user_id=uuid4()
        )

        assert result is None

    async def test_get_document_found(self, mock_db_session, mock_document):
        """Test Dokument-Abruf wenn gefunden."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        # Mock execute to return document (scalar_one_or_none is sync)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        result = await service.get_document(
            mock_db_session,
            document_id=mock_document.id,
            user_id=mock_document.owner_id
        )

        assert result is not None
        assert result.filename == "test.pdf"

    async def test_delete_document_not_found(self, mock_db_session):
        """Test Dokument-Loeschung wenn nicht gefunden."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        result = await service.delete_document(
            mock_db_session,
            document_id=uuid4(),
            user_id=uuid4()
        )

        assert result is False

    async def test_delete_document_success(self, mock_db_session, mock_document):
        """Test erfolgreiche Dokument-Loeschung."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = mock_document
        mock_db_session.execute.return_value = mock_result

        result = await service.delete_document(
            mock_db_session,
            document_id=mock_document.id,
            user_id=mock_document.owner_id
        )

        assert result is True
        mock_db_session.delete.assert_called_once()
        mock_db_session.commit.assert_called_once()

    async def test_batch_delete_all_success(self, mock_db_session, mock_document):
        """Test Batch-Loeschung - alle erfolgreich."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        doc_ids = [uuid4(), uuid4()]

        # batch_delete makes two execute calls:
        # 1. SELECT to find IDs (uses fetchall())
        # 2. DELETE (uses rowcount)
        mock_select_result = Mock()
        mock_select_result.fetchall.return_value = [(doc_id,) for doc_id in doc_ids]

        mock_delete_result = Mock()
        mock_delete_result.rowcount = 2

        mock_db_session.execute = AsyncMock(side_effect=[mock_select_result, mock_delete_result])

        result = await service.batch_delete(
            mock_db_session,
            document_ids=doc_ids,
            user_id=mock_document.owner_id
        )

        assert result.success is True
        assert result.processed == 2
        assert result.failed == 0

    async def test_batch_delete_partial_failure(self, mock_db_session, mock_document):
        """Test Batch-Loeschung mit Teil-Fehlern."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        doc_ids = [uuid4(), uuid4(), uuid4()]

        # batch_delete makes two execute calls:
        # 1. SELECT to find IDs - only first 2 found
        # 2. DELETE - deletes 2
        mock_select_result = Mock()
        mock_select_result.fetchall.return_value = [(doc_ids[0],), (doc_ids[1],)]

        mock_delete_result = Mock()
        mock_delete_result.rowcount = 2

        mock_db_session.execute = AsyncMock(side_effect=[mock_select_result, mock_delete_result])

        result = await service.batch_delete(
            mock_db_session,
            document_ids=doc_ids,
            user_id=mock_document.owner_id
        )

        assert result.success is False
        assert result.failed == 1

    async def test_ensure_tags_exist_empty(self, mock_db_session):
        """Test Tag-Erstellung mit leerer Liste."""
        from app.services.document_service import DocumentService
        service = DocumentService()

        result = await service._ensure_tags_exist(mock_db_session, [])
        assert result == []


class TestSearchFilters:
    """Tests fuer SearchFilters."""

    def test_empty_filters(self):
        """Test leere Filter."""
        filters = SearchFilters()

        assert filters.document_type is None
        assert filters.status is None
        assert filters.date_from is None
        assert filters.date_to is None
        assert filters.confidence_min is None
        assert filters.has_embedding is None
        assert filters.language is None
        assert filters.tags is None

    def test_full_filters(self):
        """Test vollstaendige Filter."""
        filters = SearchFilters(
            document_type=DocumentType.INVOICE,
            status=ProcessingStatus.COMPLETED,
            date_from=datetime(2024, 1, 1),
            date_to=datetime(2024, 12, 31),
            confidence_min=0.8,
            has_embedding=True,
            language="de",
            tags=["Finanzen", "2024"]
        )

        assert filters.document_type == DocumentType.INVOICE
        assert filters.status == ProcessingStatus.COMPLETED
        assert filters.confidence_min == 0.8
        assert len(filters.tags) == 2

    def test_filters_model_dump(self):
        """Test Filter Serialisierung."""
        filters = SearchFilters(
            document_type=DocumentType.CONTRACT,
            confidence_min=0.9
        )

        dumped = filters.model_dump(exclude_none=True)

        assert "document_type" in dumped
        assert "confidence_min" in dumped
        assert "status" not in dumped  # None values excluded


@requires_document_service
@requires_reportlab
class TestPDFExport:
    """Tests fuer PDF-Export Funktionalitaet."""

    @pytest.fixture
    def mock_document(self):
        """Mock Document Objekt fuer PDF-Export."""
        doc = Mock()
        doc.id = uuid4()
        doc.filename = "test_rechnung.pdf"
        doc.original_filename = "Rechnung_2024.pdf"
        doc.file_path = "/uploads/test.pdf"
        doc.file_size = 2048
        doc.mime_type = "application/pdf"
        doc.checksum = "abc123"
        doc.document_type = "invoice"
        doc.status = "completed"
        doc.page_count = 3
        doc.extracted_text = "Rechnung Nr. 2024-001\nBetrag: 1.234,56 EUR\nDatum: 15.01.2024"
        doc.ocr_backend_used = "deepseek"
        doc.ocr_confidence = 0.92
        doc.processing_duration_ms = 2500
        doc.has_umlauts = True
        doc.german_validation_score = 0.95
        doc.detected_language = "de"
        doc.document_metadata = {"invoice_number": "2024-001"}
        doc.tags = []
        doc.upload_date = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        doc.processed_date = datetime(2024, 1, 15, 10, 32, tzinfo=timezone.utc)
        doc.created_at = datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        doc.updated_at = datetime(2024, 1, 15, 10, 32, tzinfo=timezone.utc)
        doc.current_version_number = 1
        doc.total_versions = 1
        doc.embedding = [0.1] * 1024
        doc.embedding_updated_at = datetime(2024, 1, 15, 10, 33, tzinfo=timezone.utc)
        doc.embedding_model = "multilingual-e5-large"
        doc.owner_id = uuid4()
        return doc

    @pytest.fixture
    def mock_tag(self):
        """Mock Tag Objekt."""
        tag = Mock()
        tag.id = uuid4()
        tag.name = "Finanzen"
        tag.description = "Finanzielle Dokumente"
        tag.color = "#4a9eff"
        tag.created_at = datetime.now(timezone.utc)
        return tag

    def test_export_pdf_format(self, mock_document):
        """Test PDF-Export Format."""
        from app.services.document_service import DocumentService

        service = DocumentService()
        mock_document.tags = []
        documents = [mock_document]

        data, content_type = service._export_pdf(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/pdf"
        assert isinstance(data, bytes)
        assert len(data) > 0

        # PDF Signatur pruefen (PDF beginnt mit %PDF)
        assert data[:4] == b'%PDF'

    def test_export_pdf_without_text(self, mock_document):
        """Test PDF-Export ohne Text."""
        from app.services.document_service import DocumentService

        service = DocumentService()
        mock_document.tags = []
        documents = [mock_document]

        data, content_type = service._export_pdf(
            documents, include_text=False, include_metadata=True
        )

        assert content_type == "application/pdf"
        assert len(data) > 0
        assert data[:4] == b'%PDF'

    def test_export_pdf_with_tags(self, mock_document, mock_tag):
        """Test PDF-Export mit Tags."""
        from app.services.document_service import DocumentService

        service = DocumentService()
        mock_document.tags = [mock_tag]
        documents = [mock_document]

        data, content_type = service._export_pdf(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/pdf"
        assert len(data) > 0

    def test_export_pdf_multiple_documents(self, mock_document):
        """Test PDF-Export mit mehreren Dokumenten."""
        from app.services.document_service import DocumentService

        service = DocumentService()
        mock_document.tags = []

        # Mehrere Dokumente erstellen
        doc1 = Mock()
        for attr in dir(mock_document):
            if not attr.startswith('_'):
                setattr(doc1, attr, getattr(mock_document, attr))
        doc1.id = uuid4()
        doc1.filename = "doc1.pdf"

        doc2 = Mock()
        for attr in dir(mock_document):
            if not attr.startswith('_'):
                setattr(doc2, attr, getattr(mock_document, attr))
        doc2.id = uuid4()
        doc2.filename = "doc2.pdf"

        documents = [doc1, doc2]

        data, content_type = service._export_pdf(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/pdf"
        # PDF mit mehreren Dokumenten sollte groesser sein
        assert len(data) > 1000

    def test_export_pdf_with_german_umlauts(self, mock_document):
        """Test PDF-Export mit deutschen Umlauten."""
        from app.services.document_service import DocumentService

        service = DocumentService()
        mock_document.tags = []
        mock_document.extracted_text = "Äpfel, Öl und Übung kosten über 100€"
        mock_document.filename = "Übersicht_Äußerungen.pdf"
        documents = [mock_document]

        data, content_type = service._export_pdf(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/pdf"
        assert len(data) > 0

    def test_export_pdf_empty_documents(self):
        """Test PDF-Export mit leerer Dokumentenliste."""
        from app.services.document_service import DocumentService

        service = DocumentService()
        documents = []

        data, content_type = service._export_pdf(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/pdf"
        # Sollte trotzdem gueltige PDF sein (evtl. nur Titelseite)
        assert data[:4] == b'%PDF'

    def test_export_pdf_long_text(self, mock_document):
        """Test PDF-Export mit sehr langem Text."""
        from app.services.document_service import DocumentService

        service = DocumentService()
        mock_document.tags = []
        # Sehr langer Text
        mock_document.extracted_text = "Dies ist ein Test. " * 1000
        documents = [mock_document]

        data, content_type = service._export_pdf(
            documents, include_text=True, include_metadata=True
        )

        assert content_type == "application/pdf"
        assert len(data) > 0

    def test_export_format_enum_has_pdf(self):
        """Test dass ExportFormat PDF enthaelt."""
        assert ExportFormat.PDF.value == "pdf"
