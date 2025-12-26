# -*- coding: utf-8 -*-
"""
Tests fuer DocumentReportService.

Testet:
- PDF-Berichtgenerierung
- Style-Konfiguration
- Tabellenerstellung
- Entity-Extraktion
- Uebersetzungsfunktionen
"""

import pytest
from datetime import datetime
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from io import BytesIO

from app.services.document_report_service import (
    DocumentReportService,
    get_document_report_service,
)


class TestDocumentReportServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_service(self):
        """Sollte Service korrekt initialisieren."""
        service = DocumentReportService()

        assert service.styles is not None
        assert service.title_style is not None
        assert service.heading_style is not None
        assert service.body_style is not None

    def test_custom_styles_defined(self):
        """Sollte benutzerdefinierte Styles haben."""
        service = DocumentReportService()

        assert service.subtitle_style is not None
        assert service.label_style is not None
        assert service.value_style is not None
        assert service.text_style is not None


class TestTranslateStatus:
    """Tests fuer _translate_status Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_translate_pending(self, service: DocumentReportService):
        """Sollte pending uebersetzen."""
        result = service._translate_status("pending")
        assert result == "Ausstehend"

    def test_translate_processing(self, service: DocumentReportService):
        """Sollte processing uebersetzen."""
        result = service._translate_status("processing")
        assert result == "In Verarbeitung"

    def test_translate_completed(self, service: DocumentReportService):
        """Sollte completed uebersetzen."""
        result = service._translate_status("completed")
        assert result == "Abgeschlossen"

    def test_translate_failed(self, service: DocumentReportService):
        """Sollte failed uebersetzen."""
        result = service._translate_status("failed")
        assert result == "Fehlgeschlagen"

    def test_translate_unknown_status(self, service: DocumentReportService):
        """Sollte unbekannten Status unveraendert zurueckgeben."""
        result = service._translate_status("unknown_status")
        assert result == "unknown_status"


class TestTranslateAction:
    """Tests fuer _translate_action Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_translate_document_created(self, service: DocumentReportService):
        """Sollte document_created uebersetzen."""
        result = service._translate_action("document_created")
        assert result == "Erstellt"

    def test_translate_ocr_started(self, service: DocumentReportService):
        """Sollte ocr_started uebersetzen."""
        result = service._translate_action("ocr_started")
        assert result == "OCR gestartet"

    def test_translate_ocr_completed(self, service: DocumentReportService):
        """Sollte ocr_completed uebersetzen."""
        result = service._translate_action("ocr_completed")
        assert result == "OCR abgeschlossen"

    def test_translate_unknown_action(self, service: DocumentReportService):
        """Sollte unbekannte Aktion unveraendert zurueckgeben."""
        result = service._translate_action("custom_action")
        assert result == "custom_action"


class TestFormatSize:
    """Tests fuer _format_size Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_format_none(self, service: DocumentReportService):
        """Sollte None als Strich formatieren."""
        result = service._format_size(None)
        assert result == "-"

    def test_format_bytes(self, service: DocumentReportService):
        """Sollte Bytes korrekt formatieren."""
        result = service._format_size(500)
        assert result == "500 Bytes"

    def test_format_kilobytes(self, service: DocumentReportService):
        """Sollte Kilobytes korrekt formatieren."""
        result = service._format_size(2048)
        assert "KB" in result

    def test_format_megabytes(self, service: DocumentReportService):
        """Sollte Megabytes korrekt formatieren."""
        result = service._format_size(2 * 1024 * 1024)
        assert "MB" in result


class TestGetConfidenceColor:
    """Tests fuer _get_confidence_color Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_high_confidence_green(self, service: DocumentReportService):
        """Sollte Gruen fuer hohe Confidence zurueckgeben."""
        from reportlab.lib import colors
        result = service._get_confidence_color(0.95)
        assert result == colors.HexColor('#38a169')

    def test_medium_confidence_orange(self, service: DocumentReportService):
        """Sollte Orange fuer mittlere Confidence zurueckgeben."""
        from reportlab.lib import colors
        result = service._get_confidence_color(0.75)
        assert result == colors.HexColor('#d69e2e')

    def test_low_confidence_red(self, service: DocumentReportService):
        """Sollte Rot fuer niedrige Confidence zurueckgeben."""
        from reportlab.lib import colors
        result = service._get_confidence_color(0.5)
        assert result == colors.HexColor('#e53e3e')


class TestExtractEntities:
    """Tests fuer _extract_entities Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_extract_entities_with_metadata(self, service: DocumentReportService):
        """Sollte Entitaeten aus Metadaten extrahieren."""
        document = MagicMock()
        document.document_metadata = {
            "dates": ["2024-01-15", "2024-02-20"],
            "amounts": ["1.234,56 EUR", "500,00 EUR"],
            "ibans": ["DE89370400440532013000"],
            "vat_ids": ["DE123456789"],
            "emails": ["test@example.com"],
            "phones": ["+49 123 456789"]
        }

        result = service._extract_entities(document)

        assert "dates" in result
        assert len(result["dates"]) == 2
        assert "ibans" in result
        assert "DE89370400440532013000" in result["ibans"]

    def test_extract_entities_empty_metadata(self, service: DocumentReportService):
        """Sollte leeres Dict bei fehlenden Metadaten zurueckgeben."""
        document = MagicMock()
        document.document_metadata = {}

        result = service._extract_entities(document)

        assert result == {}

    def test_extract_entities_none_metadata(self, service: DocumentReportService):
        """Sollte leeres Dict bei None Metadaten zurueckgeben."""
        document = MagicMock()
        document.document_metadata = None

        result = service._extract_entities(document)

        assert result == {}


class TestCreateInfoTable:
    """Tests fuer _create_info_table Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_create_info_table(self, service: DocumentReportService):
        """Sollte Info-Tabelle erstellen."""
        document = MagicMock()
        document.filename = "test.pdf"
        document.original_filename = "original.pdf"
        document.id = uuid4()
        document.document_type = "invoice"
        document.status = "completed"
        document.file_size = 1024
        document.page_count = 5
        document.created_at = datetime.now()
        document.processed_date = datetime.now()

        table = service._create_info_table(document)

        assert table is not None

    def test_create_info_table_with_missing_fields(
        self, service: DocumentReportService
    ):
        """Sollte mit fehlenden Feldern funktionieren."""
        document = MagicMock()
        document.filename = None
        document.original_filename = None
        document.id = uuid4()
        document.document_type = None
        document.status = "pending"
        document.file_size = None
        document.page_count = None
        document.created_at = None
        document.processed_date = None

        table = service._create_info_table(document)

        assert table is not None


class TestCreateOCRTable:
    """Tests fuer _create_ocr_table Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_create_ocr_table(self, service: DocumentReportService):
        """Sollte OCR-Tabelle erstellen."""
        document = MagicMock()
        document.ocr_backend_used = "deepseek"
        document.ocr_confidence = 0.92
        document.extracted_text = "Dies ist ein Testtext mit einigen Woertern."

        table = service._create_ocr_table(document)

        assert table is not None

    def test_create_ocr_table_no_confidence(self, service: DocumentReportService):
        """Sollte mit fehlender Confidence funktionieren."""
        document = MagicMock()
        document.ocr_backend_used = None
        document.ocr_confidence = None
        document.extracted_text = ""

        table = service._create_ocr_table(document)

        assert table is not None


class TestCreateGermanValidationTable:
    """Tests fuer _create_german_validation_table Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_create_german_table(self, service: DocumentReportService):
        """Sollte deutsche Validierungstabelle erstellen."""
        document = MagicMock()
        document.detected_language = "de"
        document.has_umlauts = True

        table = service._create_german_validation_table(document)

        assert table is not None


class TestCreateEntitiesTable:
    """Tests fuer _create_entities_table Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_create_entities_table_with_data(self, service: DocumentReportService):
        """Sollte Entitaeten-Tabelle erstellen."""
        entities = {
            "dates": ["2024-01-15", "2024-02-20"],
            "amounts": ["1.234,56 EUR"]
        }

        table = service._create_entities_table(entities)

        # Sollte eine Tabelle sein, nicht ein Paragraph
        from reportlab.platypus import Table
        assert isinstance(table, Table)

    def test_create_entities_table_empty(self, service: DocumentReportService):
        """Sollte Paragraph bei leeren Entitaeten zurueckgeben."""
        entities = {}

        result = service._create_entities_table(entities)

        from reportlab.platypus import Paragraph
        assert isinstance(result, Paragraph)

    def test_create_entities_table_truncates_values(
        self, service: DocumentReportService
    ):
        """Sollte zu viele Werte kuerzen."""
        entities = {
            "dates": [f"2024-01-{i:02d}" for i in range(1, 15)]  # 14 Werte
        }

        table = service._create_entities_table(entities)

        # Tabelle sollte erstellt werden, mit Hinweis auf weitere
        assert table is not None


class TestCreateHistoryTable:
    """Tests fuer _create_history_table Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    def test_create_history_table(self, service: DocumentReportService):
        """Sollte Historie-Tabelle erstellen."""
        history = []
        for i in range(5):
            entry = MagicMock()
            entry.created_at = datetime.now()
            entry.action = "document_created"
            entry.details = {"message": f"Eintrag {i}"}
            history.append(entry)

        table = service._create_history_table(history)

        assert table is not None

    def test_create_history_table_truncates_details(
        self, service: DocumentReportService
    ):
        """Sollte lange Details kuerzen."""
        entry = MagicMock()
        entry.created_at = datetime.now()
        entry.action = "document_created"
        entry.details = {"message": "A" * 100}  # Sehr langer Text

        table = service._create_history_table([entry])

        assert table is not None


@pytest.mark.asyncio
class TestGenerateDocumentReport:
    """Tests fuer generate_document_report Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def sample_document(self):
        document = MagicMock()
        document.id = uuid4()
        document.filename = "test.pdf"
        document.original_filename = "original_test.pdf"
        document.document_type = "invoice"
        document.status = "completed"
        document.file_size = 1024
        document.page_count = 3
        document.created_at = datetime.now()
        document.processed_date = datetime.now()
        document.ocr_backend_used = "deepseek"
        document.ocr_confidence = 0.92
        document.extracted_text = "Testtext fuer den Bericht."
        document.tags = []
        document.document_metadata = {}
        document.has_umlauts = True
        document.detected_language = "de"
        return document

    async def test_generate_report_not_found(
        self, service: DocumentReportService, mock_db
    ):
        """Sollte Fehler werfen wenn Dokument nicht gefunden."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="nicht gefunden"):
            await service.generate_document_report(
                db=mock_db,
                document_id=uuid4(),
                user_id=uuid4()
            )

    async def test_generate_report_success(
        self, service: DocumentReportService, mock_db, sample_document
    ):
        """Sollte PDF-Bericht generieren."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_document
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        pdf_bytes = await service.generate_document_report(
            db=mock_db,
            document_id=sample_document.id,
            user_id=uuid4(),
            include_text=True,
            include_history=True,
            include_entities=True
        )

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0
        # PDF Magic Number pruefen
        assert pdf_bytes[:4] == b'%PDF'

    async def test_generate_report_without_text(
        self, service: DocumentReportService, mock_db, sample_document
    ):
        """Sollte Bericht ohne Text generieren."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_document
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        pdf_bytes = await service.generate_document_report(
            db=mock_db,
            document_id=sample_document.id,
            user_id=uuid4(),
            include_text=False,
            include_history=False,
            include_entities=False
        )

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0


class TestGeneratePDF:
    """Tests fuer _generate_pdf Methode."""

    @pytest.fixture
    def service(self):
        return DocumentReportService()

    @pytest.fixture
    def sample_document(self):
        document = MagicMock()
        document.id = uuid4()
        document.filename = "test.pdf"
        document.original_filename = "original.pdf"
        document.document_type = "invoice"
        document.status = "completed"
        document.file_size = 2048
        document.page_count = 2
        document.created_at = datetime.now()
        document.processed_date = datetime.now()
        document.ocr_backend_used = "got_ocr"
        document.ocr_confidence = 0.88
        document.extracted_text = "Extrahierter Text mit Umlauten: aeoeue."
        document.tags = []
        document.document_metadata = None
        document.has_umlauts = True
        document.detected_language = "de"
        return document

    def test_generate_pdf_basic(
        self, service: DocumentReportService, sample_document
    ):
        """Sollte grundlegendes PDF generieren."""
        pdf_bytes = service._generate_pdf(
            document=sample_document,
            history=[],
            include_text=True,
            include_history=False,
            include_entities=False
        )

        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes.startswith(b'%PDF')

    def test_generate_pdf_with_long_text(
        self, service: DocumentReportService, sample_document
    ):
        """Sollte langen Text kuerzen."""
        sample_document.extracted_text = "A" * 10000  # Sehr langer Text

        pdf_bytes = service._generate_pdf(
            document=sample_document,
            history=[],
            include_text=True,
            include_history=False,
            include_entities=False
        )

        assert isinstance(pdf_bytes, bytes)

    def test_generate_pdf_with_special_characters(
        self, service: DocumentReportService, sample_document
    ):
        """Sollte Sonderzeichen im Text behandeln."""
        sample_document.extracted_text = "Text mit <html> & \"Anfuehrungszeichen\""

        pdf_bytes = service._generate_pdf(
            document=sample_document,
            history=[],
            include_text=True,
            include_history=False,
            include_entities=False
        )

        assert isinstance(pdf_bytes, bytes)


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_document_report_service_singleton(self):
        """Sollte immer gleiche Instanz zurueckgeben."""
        # Reset singleton
        import app.services.document_report_service as module
        module._report_service = None

        svc1 = get_document_report_service()
        svc2 = get_document_report_service()

        assert svc1 is svc2
