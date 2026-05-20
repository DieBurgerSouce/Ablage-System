# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Document Export Service.

Testet:
- JSON-Export: Korrekte Struktur und Encoding
- CSV-Export: Spalten und UTF-8
- ZIP-Export: Einzelne JSON-Dateien pro Dokument
- Batch Export: Fehlende Dokumente, Berechtigungspruefung
- include_text/include_metadata Flags

Feinpoliert und durchdacht - Document Export Tests.
"""

import csv
import io
import json
import zipfile
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4, UUID

from app.services.document_services.export_service import DocumentExportService
from app.db.schemas import ExportFormat

pytestmark = [pytest.mark.unit]


# ========================= Fixtures =========================


@pytest.fixture
def export_service() -> DocumentExportService:
    return DocumentExportService()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_user_id() -> UUID:
    return uuid4()


@pytest.fixture
def mock_document() -> Mock:
    """Mock Document mit allen relevanten Feldern."""
    doc = Mock()
    doc.id = uuid4()
    doc.filename = "Rechnung_2024.pdf"
    doc.document_type = "invoice"
    doc.status = "processed"
    doc.created_at = datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc)
    doc.file_size = 1024000
    doc.page_count = 3
    doc.ocr_confidence = 0.95
    doc.extracted_text = "Rechnung Nr. 12345\nBetrag: 1.234,56 EUR"
    doc.document_metadata = {"invoice_number": "12345"}
    doc.detected_language = "de"
    doc.has_umlauts = True
    doc.ocr_backend_used = "deepseek"
    doc.tags = []
    return doc


@pytest.fixture
def mock_document_with_tags(mock_document) -> Mock:
    """Mock Document mit Tags."""
    tag1 = Mock()
    tag1.name = "Rechnung"
    tag2 = Mock()
    tag2.name = "2024"
    mock_document.tags = [tag1, tag2]
    return mock_document


# ========================= JSON Export Tests =========================


class TestJsonExport:
    """Tests fuer JSON-Export."""

    def test_json_export_basic(self, export_service, mock_document):
        """JSON-Export mit Grunddaten."""
        data, content_type = export_service._export_json(
            [mock_document], include_text=True, include_metadata=True
        )

        assert content_type == "application/json"
        parsed = json.loads(data.decode("utf-8"))
        assert len(parsed) == 1
        assert parsed[0]["filename"] == "Rechnung_2024.pdf"
        assert parsed[0]["document_type"] == "invoice"
        assert parsed[0]["extracted_text"] == mock_document.extracted_text

    def test_json_export_without_text(self, export_service, mock_document):
        """JSON-Export ohne extrahierten Text."""
        data, _ = export_service._export_json(
            [mock_document], include_text=False, include_metadata=True
        )
        parsed = json.loads(data.decode("utf-8"))
        assert "extracted_text" not in parsed[0]

    def test_json_export_without_metadata(self, export_service, mock_document):
        """JSON-Export ohne Metadaten."""
        data, _ = export_service._export_json(
            [mock_document], include_text=True, include_metadata=False
        )
        parsed = json.loads(data.decode("utf-8"))
        assert "metadata" not in parsed[0]
        assert "detected_language" not in parsed[0]

    def test_json_export_with_tags(self, export_service, mock_document_with_tags):
        """JSON-Export mit Tags."""
        data, _ = export_service._export_json(
            [mock_document_with_tags], include_text=False, include_metadata=False
        )
        parsed = json.loads(data.decode("utf-8"))
        assert "Rechnung" in parsed[0]["tags"]
        assert "2024" in parsed[0]["tags"]

    def test_json_export_empty_list(self, export_service):
        """JSON-Export mit leerer Liste."""
        data, content_type = export_service._export_json(
            [], include_text=True, include_metadata=True
        )
        assert content_type == "application/json"
        parsed = json.loads(data.decode("utf-8"))
        assert parsed == []

    def test_json_export_utf8_encoding(self, export_service, mock_document):
        """JSON-Export mit Umlauten ist UTF-8 kodiert."""
        mock_document.extracted_text = "Ueberprüfung der Aerzte"
        data, _ = export_service._export_json(
            [mock_document], include_text=True, include_metadata=False
        )
        decoded = data.decode("utf-8")
        assert "Ueberprüfung" in decoded


# ========================= CSV Export Tests =========================


class TestCsvExport:
    """Tests fuer CSV-Export."""

    def test_csv_export_basic(self, export_service, mock_document):
        """CSV-Export mit Grunddaten."""
        data, content_type = export_service._export_csv(
            [mock_document], include_text=False, include_metadata=False
        )

        assert content_type == "text/csv"
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["filename"] == "Rechnung_2024.pdf"

    def test_csv_export_includes_text_column(self, export_service, mock_document):
        """CSV-Export enthaelt extracted_text-Spalte wenn gewuenscht."""
        data, _ = export_service._export_csv(
            [mock_document], include_text=True, include_metadata=False
        )
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        assert "extracted_text" in rows[0]

    def test_csv_export_truncates_long_text(self, export_service, mock_document):
        """CSV-Export kuerzt lange Texte auf 1000 Zeichen."""
        mock_document.extracted_text = "x" * 2000
        data, _ = export_service._export_csv(
            [mock_document], include_text=True, include_metadata=False
        )
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        assert rows[0]["extracted_text"].endswith("...")
        assert len(rows[0]["extracted_text"]) <= 1010  # 1000 + "..."

    def test_csv_export_metadata_columns(self, export_service, mock_document):
        """CSV-Export enthaelt Metadaten-Spalten wenn gewuenscht."""
        data, _ = export_service._export_csv(
            [mock_document], include_text=False, include_metadata=True
        )
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        assert "detected_language" in rows[0]
        assert "has_umlauts" in rows[0]


# ========================= ZIP Export Tests =========================


class TestZipExport:
    """Tests fuer ZIP-Export."""

    def test_zip_export_contains_files(self, export_service, mock_document):
        """ZIP-Export enthaelt Dateien pro Dokument."""
        data, content_type = export_service._export_zip(
            [mock_document], include_text=True, include_metadata=True
        )

        assert content_type == "application/zip"
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            assert len(names) == 1
            # Dateiname basiert auf Dokumentname
            assert names[0].endswith(".json")

    def test_zip_export_file_content(self, export_service, mock_document):
        """ZIP-Export-Dateien enthalten korrektes JSON."""
        data, _ = export_service._export_zip(
            [mock_document], include_text=True, include_metadata=True
        )

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            content = json.loads(zf.read(zf.namelist()[0]))
            assert content["filename"] == "Rechnung_2024.pdf"
            assert content["extracted_text"] == mock_document.extracted_text

    def test_zip_export_multiple_documents(self, export_service, mock_document):
        """ZIP-Export mit mehreren Dokumenten."""
        doc2 = Mock()
        doc2.id = uuid4()
        doc2.filename = "Vertrag_2024.pdf"
        doc2.document_type = "contract"
        doc2.status = "processed"
        doc2.created_at = datetime.now(timezone.utc)
        doc2.file_size = 2048000
        doc2.page_count = 5
        doc2.ocr_confidence = 0.88
        doc2.extracted_text = "Vertrag..."
        doc2.document_metadata = {}
        doc2.detected_language = "de"
        doc2.has_umlauts = False
        doc2.tags = []

        data, _ = export_service._export_zip(
            [mock_document, doc2], include_text=False, include_metadata=False
        )

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            assert len(zf.namelist()) == 2


# ========================= Batch Export Tests =========================


class TestBatchExport:
    """Tests fuer batch_export Methode."""

    @pytest.mark.asyncio
    async def test_batch_export_all_found(
        self, export_service, mock_db, sample_user_id, mock_document
    ):
        """Alle Dokumente gefunden -> keine Errors."""
        doc_id = mock_document.id
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        if True:
            data, content_type, result = await export_service.batch_export(
                db=mock_db,
                document_ids=[doc_id],
                user_id=sample_user_id,
                format=ExportFormat.JSON,
            )

        assert result.success is True
        assert result.processed == 1
        assert result.failed == 0
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_batch_export_some_not_found(
        self, export_service, mock_db, sample_user_id, mock_document
    ):
        """Einige Dokumente nicht gefunden -> Errors in Result."""
        found_id = mock_document.id
        missing_id = uuid4()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        if True:
            data, content_type, result = await export_service.batch_export(
                db=mock_db,
                document_ids=[found_id, missing_id],
                user_id=sample_user_id,
                format=ExportFormat.JSON,
            )

        assert result.success is False
        assert result.processed == 1
        assert result.failed == 1
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_batch_export_csv_format(
        self, export_service, mock_db, sample_user_id, mock_document
    ):
        """CSV-Format wird korrekt verwendet."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        if True:
            data, content_type, result = await export_service.batch_export(
                db=mock_db,
                document_ids=[mock_document.id],
                user_id=sample_user_id,
                format=ExportFormat.CSV,
            )

        assert content_type == "text/csv"
        assert result.format == ExportFormat.CSV

    @pytest.mark.asyncio
    async def test_batch_export_file_size_tracked(
        self, export_service, mock_db, sample_user_id, mock_document
    ):
        """Export-Groesse wird im Result erfasst."""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_document]
        mock_db.execute = AsyncMock(return_value=mock_result)

        if True:
            data, _, result = await export_service.batch_export(
                db=mock_db,
                document_ids=[mock_document.id],
                user_id=sample_user_id,
                format=ExportFormat.JSON,
            )

        assert result.file_size_bytes == len(data)
        assert result.file_size_bytes > 0
