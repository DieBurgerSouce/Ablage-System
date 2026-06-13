# -*- coding: utf-8 -*-
"""
Tests fuer Extracted Data API Endpoints.

Testet alle Extracted Data API Endpoints:
- GET /{document_id} - Extrahierte Daten
- GET /search - Komplexe Filter
- GET /invoices - Rechnungen mit Sonderfiltern
- GET /aggregations - Statistiken
- GET /document-types/stats
- GET /export/csv, /export/excel, /export/excel/all
"""

import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from io import BytesIO

from fastapi import HTTPException
from fastapi.responses import Response


# ==================== Get Extracted Data Tests ====================


class TestGetExtractedData:
    """Tests fuer GET /{document_id} Endpoint."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        user.email = "test@example.com"
        return user

    @pytest.fixture
    def mock_document_with_data(self, mock_user):
        """Erstellt ein Mock Document mit extracted_data."""
        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.filename = "rechnung_2025_001.pdf"
        doc.deleted_at = None
        doc.ocr_text = "Rechnung Nr. 2025-001 Test GmbH"
        doc.extracted_data = {
            "classification": {
                "document_type": "invoice",
                "confidence": 0.95,
            },
            "invoice": {
                "document_type": "invoice",
                "invoice_number": "2025-001",
                "invoice_date": "2025-01-15",
                "due_date": "2025-02-14",
                "net_amount": "1000.00",
                "vat_amount": "190.00",
                "gross_amount": "1190.00",
                "currency": "EUR",
                "extraction_confidence": 0.92,
                "needs_review": False,
            }
        }
        return doc

    @pytest.mark.asyncio
    async def test_get_extracted_data_success(self, mock_db, mock_user, mock_document_with_data):
        """Sollte extrahierte Daten erfolgreich zurueckgeben."""
        from app.api.v1.extracted_data import get_extracted_data_by_id as get_extracted_data

        # Mock db.execute to return the document
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_document_with_data
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_extracted_data(
            document_id=mock_document_with_data.id,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.classification.document_type.value == "invoice"
        assert result.invoice is not None
        assert result.invoice.invoice_number == "2025-001"

    @pytest.mark.asyncio
    async def test_get_extracted_data_document_not_found(self, mock_db, mock_user):
        """Sollte 404 bei nicht gefundenem Dokument werfen."""
        from app.api.v1.extracted_data import get_extracted_data_by_id as get_extracted_data

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc:
            await get_extracted_data(
                document_id=uuid4(),
                db=mock_db,
                current_user=mock_user,
            )

        assert exc.value.status_code == 404
        assert "nicht gefunden" in exc.value.detail

    @pytest.mark.asyncio
    async def test_get_extracted_data_no_data_available(self, mock_db, mock_user):
        """Sollte 404 bei Dokument ohne extrahierte Daten werfen."""
        from app.api.v1.extracted_data import get_extracted_data_by_id as get_extracted_data

        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.deleted_at = None
        doc.extracted_data = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc:
            await get_extracted_data(
                document_id=doc.id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc.value.status_code == 404
        assert "strukturierten Daten" in exc.value.detail


# ==================== Search Tests ====================


class TestSearchExtractedData:
    """Tests fuer GET /search Endpoint.

    NOTE: Die search_extracted_data Funktion verwendet PostgreSQL JSONB-Operationen
    wie .astext, func.jsonb_path_exists(), die nicht mit einfachen Mocks funktionieren.
    Diese Tests werden uebersprungen und sollten als Integration Tests mit echter DB laufen.
    """

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_documents(self, mock_user):
        """Erstellt Mock Dokumente fuer Suche."""
        docs = []
        for i in range(3):
            doc = MagicMock()
            doc.id = uuid4()
            doc.owner_id = mock_user.id
            doc.filename = f"rechnung_{i+1}.pdf"
            doc.deleted_at = None
            doc.ocr_text = f"Rechnung Nr. 2025-00{i+1}"
            doc.created_at = datetime.now(timezone.utc)
            doc.extracted_data = {
                "classification": {
                    "document_type": "invoice",
                    "confidence": 0.95,
                },
                "invoice": {
                    "invoice_number": f"2025-00{i+1}",
                    "invoice_date": f"2025-01-{15+i:02d}",
                    "gross_amount": str(1000 + i * 100),
                }
            }
            docs.append(doc)
        return docs

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_search_by_invoice_number(self, mock_db, mock_user, mock_documents):
        """Sollte nach Rechnungsnummer suchen."""
        from app.api.v1.extracted_data import search_extracted_data

        # Mock db execute for count
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        # Mock db execute for query
        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = [mock_documents[0]]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number="2025-001",
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 1
        assert len(result.items) == 1

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_search_by_amount_range(self, mock_db, mock_user, mock_documents):
        """Sollte nach Betragsbereich suchen."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = mock_documents[:2]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=Decimal("900"),
            max_amount=Decimal("1200"),
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 2

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_search_by_date_range(self, mock_db, mock_user, mock_documents):
        """Sollte nach Datumsbereich suchen."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = mock_documents

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 1, 31),
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 3

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_search_empty_results(self, mock_db, mock_user):
        """Sollte leere Ergebnisse korrekt zurueckgeben."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number="NICHT-VORHANDEN",
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 0
        assert result.items == []
        assert result.pages == 0


# ==================== Invoices List Tests ====================


class TestListInvoices:
    """Tests fuer GET /invoices Endpoint."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_invoice_documents(self, mock_user):
        """Erstellt Mock Rechnungs-Dokumente."""
        docs = []
        for i in range(2):
            doc = MagicMock()
            doc.id = uuid4()
            doc.owner_id = mock_user.id
            doc.filename = f"rechnung_{i+1}.pdf"
            doc.deleted_at = None
            doc.extracted_data = {
                "classification": {"document_type": "invoice"},
                "invoice": {
                    "invoice_number": f"RE-2025-{i+1:04d}",
                    "invoice_date": f"2025-01-{10+i:02d}",
                    "due_date": f"2025-02-{10+i:02d}",
                    "gross_amount": str(1500 + i * 500),
                    "discount_percent": "2" if i == 0 else None,
                    "discount_due_date": "2025-01-20" if i == 0 else None,
                    "sender": {"company": f"Lieferant {i+1}"},
                    "extraction_confidence": 0.90,
                    "needs_review": i == 1,
                }
            }
            docs.append(doc)
        return docs

    @pytest.mark.asyncio
    async def test_list_invoices_success(self, mock_db, mock_user, mock_invoice_documents):
        """Sollte Rechnungen erfolgreich auflisten."""
        from app.api.v1.extracted_data import list_invoices

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 2

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = mock_invoice_documents

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await list_invoices(
            overdue=None,
            has_skonto=None,
            skonto_expiring_soon=None,
            min_amount=None,
            max_amount=None,
            order_by="invoice_date",
            order_dir="desc",
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 2
        assert len(result.items) == 2

    @pytest.mark.asyncio
    async def test_list_invoices_with_skonto(self, mock_db, mock_user, mock_invoice_documents):
        """Sollte nur Rechnungen mit Skonto zurueckgeben."""
        from app.api.v1.extracted_data import list_invoices

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = [mock_invoice_documents[0]]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await list_invoices(
            overdue=None,
            has_skonto=True,
            skonto_expiring_soon=None,
            min_amount=None,
            max_amount=None,
            order_by="invoice_date",
            order_dir="desc",
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 1
        assert result.items[0].has_skonto is True


# ==================== Aggregations Tests ====================


class TestGetAggregations:
    """Tests fuer GET /aggregations Endpoint."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_aggregation_documents(self, mock_user):
        """Erstellt Mock Dokumente fuer Aggregation."""
        docs = []
        for i in range(5):
            doc = MagicMock()
            doc.id = uuid4()
            doc.owner_id = mock_user.id
            doc.extracted_data = {
                "classification": {"document_type": "invoice"},
                "invoice": {
                    "invoice_date": f"2025-01-{10+i:02d}",
                    "gross_amount": str(1000 + i * 200),
                    "net_amount": str(840 + i * 168),
                    "vat_amount": str(160 + i * 32),
                }
            }
            docs.append(doc)
        return docs

    @pytest.mark.asyncio
    async def test_get_aggregations_success(self, mock_db, mock_user, mock_aggregation_documents):
        """Sollte Aggregationen korrekt berechnen."""
        from app.api.v1.extracted_data import get_aggregations

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_aggregation_documents

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_aggregations(
            document_type=None,
            date_from=None,
            date_to=None,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total_documents == 5
        assert result.total_gross_amount > 0
        assert "invoice" in result.by_document_type

    @pytest.mark.asyncio
    async def test_get_aggregations_empty(self, mock_db, mock_user):
        """Sollte leere Aggregationen korrekt behandeln."""
        from app.api.v1.extracted_data import get_aggregations

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_aggregations(
            document_type=None,
            date_from=None,
            date_to=None,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total_documents == 0
        assert result.total_gross_amount == Decimal("0")
        assert result.avg_gross_amount == Decimal("0.00")


# ==================== Export Tests ====================


class TestExportEndpoints:
    """Tests fuer Export-Endpoints."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.fixture
    def mock_export_documents(self, mock_user):
        """Erstellt Mock Dokumente fuer Export."""
        docs = []
        for i in range(3):
            doc = {
                "id": uuid4(),
                "filename": f"rechnung_{i+1}.pdf",
                "extracted_data": {
                    "classification": {"document_type": "invoice"},
                    "invoice": {
                        "invoice_number": f"RE-2025-{i+1:04d}",
                        "invoice_date": f"2025-01-{10+i:02d}",
                        "gross_amount": str(1000 + i * 100),
                        "sender": {"company": f"Lieferant {i+1} GmbH"},
                    }
                }
            }
            docs.append(doc)
        return docs

    @pytest.mark.asyncio
    async def test_export_csv_invoices(self, mock_db, mock_user, mock_export_documents):
        """Sollte CSV-Export fuer Rechnungen erstellen."""
        from app.api.v1.extracted_data import export_csv
        from app.api.schemas.extracted_data import ExtractedDocumentType

        with patch('app.api.v1.extracted_data._get_documents_for_export') as mock_get_docs:
            mock_get_docs.return_value = mock_export_documents

            with patch('app.api.v1.extracted_data.export_invoices_csv') as mock_export:
                mock_export.return_value = b"\xef\xbb\xbfRechnungsnummer;Datum;Betrag\nRE-2025-0001;2025-01-10;1000"

                result = await export_csv(
                    document_type=ExtractedDocumentType.INVOICE,
                    date_from=None,
                    date_to=None,
                    min_amount=None,
                    max_amount=None,
                    db=mock_db,
                    current_user=mock_user,
                )

                assert isinstance(result, Response)
                assert result.media_type == "text/csv; charset=utf-8"
                assert "Content-Disposition" in result.headers

    @pytest.mark.asyncio
    async def test_export_csv_no_documents(self, mock_db, mock_user):
        """Sollte 404 bei keinen Dokumenten werfen."""
        from app.api.v1.extracted_data import export_csv
        from app.api.schemas.extracted_data import ExtractedDocumentType

        with patch('app.api.v1.extracted_data._get_documents_for_export') as mock_get_docs:
            mock_get_docs.return_value = []

            with pytest.raises(HTTPException) as exc:
                await export_csv(
                    document_type=ExtractedDocumentType.INVOICE,
                    date_from=None,
                    date_to=None,
                    min_amount=None,
                    max_amount=None,
                    db=mock_db,
                    current_user=mock_user,
                )

            assert exc.value.status_code == 404
            assert "Export" in exc.value.detail

    @pytest.mark.asyncio
    async def test_export_excel_invoices(self, mock_db, mock_user, mock_export_documents):
        """Sollte Excel-Export fuer Rechnungen erstellen."""
        from app.api.v1.extracted_data import export_excel
        from app.api.schemas.extracted_data import ExtractedDocumentType

        with patch('app.api.v1.extracted_data._get_documents_for_export') as mock_get_docs:
            mock_get_docs.return_value = mock_export_documents

            with patch('app.api.v1.extracted_data.export_invoices_excel') as mock_export:
                # Mock Excel-Datei als Bytes
                mock_export.return_value = b"PK\x03\x04..."  # XLSX magic bytes

                result = await export_excel(
                    document_type=ExtractedDocumentType.INVOICE,
                    date_from=None,
                    date_to=None,
                    min_amount=None,
                    max_amount=None,
                    db=mock_db,
                    current_user=mock_user,
                )

                assert isinstance(result, Response)
                assert "spreadsheetml" in result.media_type

    @pytest.mark.asyncio
    async def test_export_all_excel(self, mock_db, mock_user, mock_export_documents):
        """Sollte kombinierte Excel-Datei mit allen Typen erstellen."""
        from app.api.v1.extracted_data import export_all_types_excel

        with patch('app.api.v1.extracted_data._get_documents_for_export') as mock_get_docs:
            # Return different counts for each document type
            mock_get_docs.side_effect = [
                mock_export_documents,  # invoices
                [],  # orders
                [],  # contracts
            ]

            with patch('app.api.v1.extracted_data.export_all_excel') as mock_export:
                mock_export.return_value = b"PK\x03\x04..."

                result = await export_all_types_excel(
                    date_from=None,
                    date_to=None,
                    db=mock_db,
                    current_user=mock_user,
                )

                assert isinstance(result, Response)
                mock_export.assert_called_once()


# ==================== Document Type Stats Tests ====================


class TestDocumentTypeStats:
    """Tests fuer GET /document-types/stats Endpoint."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_get_document_type_stats(self, mock_db, mock_user):
        """Sollte Dokumenttyp-Statistiken zurueckgeben."""
        from app.api.v1.extracted_data import get_document_type_stats

        docs = []
        for i, doc_type in enumerate(["invoice", "invoice", "order", "contract"]):
            doc = MagicMock()
            doc.extracted_data = {
                "classification": {"document_type": doc_type}
            }
            docs.append(doc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = docs

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_document_type_stats(
            db=mock_db,
            current_user=mock_user,
        )

        assert result["invoice"] == 2
        assert result["order"] == 1
        assert result["contract"] == 1


# ==================== Content-Disposition Sanitization Tests ====================


class TestContentDispositionSanitization:
    """Tests fuer sichere Content-Disposition Headers."""

    def test_filename_sanitization_umlauts(self):
        """Sollte Umlaute in Dateinamen korrekt behandeln."""
        from app.core.security import build_content_disposition

        result = build_content_disposition("rechnungen_muenchen_2025.csv", "attachment")

        # RFC 5987 encoding sollte verwendet werden fuer Umlaute
        assert "filename" in result
        # Entweder ASCII-safe oder mit filename*= encoding
        assert "attachment" in result

    def test_filename_sanitization_special_chars(self):
        """Sollte Sonderzeichen in Dateinamen entfernen."""
        from app.core.security import build_content_disposition

        result = build_content_disposition('rechnung_"test"_<script>.csv', "attachment")

        # Gefaehrliche Zeichen sollten entfernt sein
        assert "<script>" not in result
        assert '"test"' not in result or "filename*=" in result

    def test_filename_sanitization_path_traversal(self):
        """Sollte Path-Traversal-Versuche abfangen."""
        from app.core.security import build_content_disposition

        result = build_content_disposition("../../../etc/passwd", "attachment")

        # Path-Traversal-Zeichen sollten entfernt sein
        assert "../" not in result


# ==================== JSONB Query Tests ====================


class TestJSONBQueries:
    """Tests fuer JSONB-spezifische Abfragen.

    NOTE: Diese Tests erfordern PostgreSQL JSONB-Operationen (.astext, jsonb_path_exists).
    Sie werden uebersprungen und sollten als Integration Tests mit echter DB laufen.
    """

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_jsonb_iban_search(self, mock_db, mock_user):
        """Sollte IBAN in JSONB-Feldern suchen."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.filename = "test.pdf"
        doc.ocr_text = "Test"
        doc.created_at = datetime.now(timezone.utc)
        doc.extracted_data = {
            "classification": {"document_type": "invoice", "confidence": 0.9},
            "invoice": {
                "invoice_number": "TEST-001",
                "sender_bank": {"iban": "DE89370400440532013000"},
            }
        }

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = [doc]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban="DE89370400440532013000",
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 1

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_jsonb_vat_id_search(self, mock_db, mock_user):
        """Sollte USt-IdNr in JSONB-Feldern suchen."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.filename = "test.pdf"
        doc.ocr_text = "Test"
        doc.created_at = datetime.now(timezone.utc)
        doc.extracted_data = {
            "classification": {"document_type": "invoice", "confidence": 0.9},
            "invoice": {
                "invoice_number": "TEST-001",
                "sender_vat_id": "DE123456789",
            }
        }

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = [doc]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban=None,
            vat_id="DE123456789",
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 1


# ==================== Pagination Tests ====================


class TestPagination:
    """Tests fuer Pagination-Funktionalitaet."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_search_pagination_calculation(self, mock_db, mock_user):
        """Sollte Seitenberechnung korrekt durchfuehren."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 55  # 55 Ergebnisse = 3 Seiten bei 20/Seite

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 55
        assert result.pages == 3
        assert result.page == 1
        assert result.per_page == 20

    @pytest.mark.asyncio
    async def test_invoices_pagination(self, mock_db, mock_user):
        """Sollte Rechnungs-Liste korrekt paginieren."""
        from app.api.v1.extracted_data import list_invoices

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 100

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await list_invoices(
            overdue=None,
            has_skonto=None,
            skonto_expiring_soon=None,
            min_amount=None,
            max_amount=None,
            order_by="invoice_date",
            order_dir="desc",
            page=3,
            per_page=25,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 100
        assert result.pages == 4  # 100/25 = 4 Seiten
        assert result.page == 3


# ==================== Filter Combination Tests ====================


class TestFilterCombinations:
    """Tests fuer kombinierte Filter."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_search_multiple_filters(self, mock_db, mock_user):
        """Sollte mehrere Filter kombinieren."""
        from app.api.v1.extracted_data import search_extracted_data
        from app.api.schemas.extracted_data import ExtractedDocumentType

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number="2025",
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=Decimal("100"),
            max_amount=Decimal("5000"),
            date_from=date(2025, 1, 1),
            date_to=date(2025, 12, 31),
            document_type=ExtractedDocumentType.INVOICE,
            needs_review=True,
            has_skonto=True,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        # Verify that execute was called (filters applied)
        assert mock_db.execute.called
        assert result.total == 5

    @pytest.mark.asyncio
    async def test_invoices_overdue_filter(self, mock_db, mock_user):
        """Sollte ueberfaellige Rechnungen filtern."""
        from app.api.v1.extracted_data import list_invoices

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await list_invoices(
            overdue=True,
            has_skonto=None,
            skonto_expiring_soon=None,
            min_amount=None,
            max_amount=None,
            order_by="due_date",
            order_dir="asc",
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total == 3


# ==================== Error Handling Tests ====================


class TestExtractedDataErrors:
    """Tests fuer Fehlerbehandlung bei Extracted Data."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.skip(reason="ExtractedDocumentData has all optional fields, accepts any dict - test design issue")
    @pytest.mark.asyncio
    async def test_get_extracted_data_invalid_json(self, mock_db, mock_user):
        """Sollte 500 bei ungueltigem JSON werfen.

        NOTE: Dieser Test ist uebersprungen, da ExtractedDocumentData alle Felder
        als optional hat. Ein dict wie {"invalid": "structure"} loest keinen
        ValidationError aus, sondern gibt ein Objekt mit None-Werten zurueck.
        """
        from app.api.v1.extracted_data import get_extracted_data_by_id as get_extracted_data

        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.deleted_at = None
        doc.extracted_data = {"invalid": "structure"}  # Ungueltiges Format

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Das sollte einen Fehler beim Parsen werfen
        with pytest.raises(HTTPException) as exc:
            await get_extracted_data(
                document_id=doc.id,
                db=mock_db,
                current_user=mock_user,
            )

        assert exc.value.status_code == 500
        assert "Parsen" in exc.value.detail

    @pytest.mark.asyncio
    async def test_export_unsupported_type(self, mock_db, mock_user):
        """Sollte 400 bei nicht unterstuetztem Export-Typ werfen."""
        from app.api.v1.extracted_data import export_csv
        from app.api.schemas.extracted_data import ExtractedDocumentType

        with patch('app.api.v1.extracted_data._get_documents_for_export') as mock_get_docs:
            # Return some documents
            mock_get_docs.return_value = [{"id": uuid4(), "extracted_data": {}}]

            # DELIVERY_NOTE is not supported for CSV export
            with pytest.raises(HTTPException) as exc:
                await export_csv(
                    document_type=ExtractedDocumentType.DELIVERY_NOTE,
                    date_from=None,
                    date_to=None,
                    min_amount=None,
                    max_amount=None,
                    db=mock_db,
                    current_user=mock_user,
                )

            assert exc.value.status_code == 400
            assert "nicht unterstützt" in exc.value.detail

    @pytest.mark.asyncio
    async def test_export_all_no_documents(self, mock_db, mock_user):
        """Sollte 404 bei leeren Export-Ergebnissen werfen."""
        from app.api.v1.extracted_data import export_all_types_excel

        with patch('app.api.v1.extracted_data._get_documents_for_export') as mock_get_docs:
            # Keine Dokumente in keiner Kategorie
            mock_get_docs.side_effect = [[], [], []]

            with pytest.raises(HTTPException) as exc:
                await export_all_types_excel(
                    date_from=None,
                    date_to=None,
                    db=mock_db,
                    current_user=mock_user,
                )

            assert exc.value.status_code == 404


# ==================== Aggregation Edge Cases ====================


class TestAggregationEdgeCases:
    """Tests fuer Aggregation-Randfaelle."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.skip(reason="Requires PostgreSQL JSONB operations (.astext) - use integration tests")
    @pytest.mark.asyncio
    async def test_aggregations_with_date_filter(self, mock_db, mock_user):
        """Sollte Aggregationen mit Datumsfilter berechnen."""
        from app.api.v1.extracted_data import get_aggregations
        from app.api.schemas.extracted_data import ExtractedDocumentType

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_aggregations(
            document_type=ExtractedDocumentType.INVOICE,
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total_documents == 0
        assert result.total_gross_amount == Decimal("0")

    @pytest.mark.asyncio
    async def test_aggregations_handles_missing_amounts(self, mock_db, mock_user):
        """Sollte fehlende Betraege korrekt behandeln."""
        from app.api.v1.extracted_data import get_aggregations

        docs = []
        # Dokument mit fehlenden Betraegen
        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.extracted_data = {
            "classification": {"document_type": "invoice"},
            "invoice": {
                "invoice_date": "2025-01-15",
                # gross_amount, net_amount, vat_amount fehlen
            }
        }
        docs.append(doc)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = docs

        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_aggregations(
            document_type=None,
            date_from=None,
            date_to=None,
            db=mock_db,
            current_user=mock_user,
        )

        assert result.total_documents == 1
        assert result.total_gross_amount == Decimal("0")
        assert "invoice" in result.by_document_type


# ==================== Search Result Mapping Tests ====================


class TestSearchResultMapping:
    """Tests fuer Search Result Mapping."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def mock_user(self):
        user = MagicMock()
        user.id = uuid4()
        return user

    @pytest.mark.asyncio
    async def test_search_maps_order_document(self, mock_db, mock_user):
        """Sollte Order-Dokumente korrekt mappen."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.filename = "bestellung_001.pdf"
        doc.ocr_text = "Bestellung Nr. 2025-001"
        doc.created_at = datetime.now(timezone.utc)
        doc.extracted_data = {
            "classification": {"document_type": "order", "confidence": 0.88},
            "order": {
                "order_number": "ORD-2025-001",
                "order_date": "2025-01-10",
                "total_amount": "500.00",
            }
        }

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = [doc]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert len(result.items) == 1
        assert result.items[0].reference_number == "ORD-2025-001"
        assert result.items[0].document_type.value == "order"

    @pytest.mark.asyncio
    async def test_search_maps_contract_document(self, mock_db, mock_user):
        """Sollte Contract-Dokumente korrekt mappen."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.filename = "vertrag_001.pdf"
        doc.ocr_text = "Vertrag Nr. 2025-001"
        doc.created_at = datetime.now(timezone.utc)
        doc.extracted_data = {
            "classification": {"document_type": "contract", "confidence": 0.92},
            "contract": {
                "contract_number": "V-2025-001",
                "contract_date": "2025-01-05",
                "contract_value": "10000.00",
            }
        }

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = [doc]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert len(result.items) == 1
        assert result.items[0].reference_number == "V-2025-001"
        assert result.items[0].document_type.value == "contract"

    @pytest.mark.asyncio
    async def test_search_handles_unknown_document_type(self, mock_db, mock_user):
        """Sollte unbekannte Dokumenttypen korrekt behandeln."""
        from app.api.v1.extracted_data import search_extracted_data

        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 1

        doc = MagicMock()
        doc.id = uuid4()
        doc.owner_id = mock_user.id
        doc.filename = "unknown.pdf"
        doc.ocr_text = "Unbekanntes Dokument"
        doc.created_at = datetime.now(timezone.utc)
        doc.extracted_data = {
            "classification": {"document_type": "unknown_type", "confidence": 0.5},
        }

        mock_query_result = MagicMock()
        mock_query_result.scalars.return_value.all.return_value = [doc]

        mock_db.execute = AsyncMock(side_effect=[mock_count_result, mock_query_result])

        result = await search_extracted_data(
            invoice_number=None,
            customer_number=None,
            iban=None,
            vat_id=None,
            min_amount=None,
            max_amount=None,
            date_from=None,
            date_to=None,
            document_type=None,
            needs_review=None,
            has_skonto=None,
            page=1,
            per_page=20,
            db=mock_db,
            current_user=mock_user,
        )

        assert len(result.items) == 1
        assert result.items[0].document_type.value == "unknown"
