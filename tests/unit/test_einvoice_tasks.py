# -*- coding: utf-8 -*-
"""Tests für E-Invoice Services und Celery Tasks."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import uuid4
from datetime import datetime, timezone
from typing import List, Dict, Any

# ============================================================
# Parser Service Tests
# ============================================================

class TestParserService:
    """Tests für EInvoiceParserService."""

    @pytest.mark.asyncio
    async def test_detect_zugferd_format(self):
        """Erkennt ZUGFeRD-Format korrekt."""
        from app.services.einvoice import get_parser_service
        from app.api.schemas.einvoice import EInvoiceFormatDetected

        parser = get_parser_service()

        # Mock ZUGFeRD 2.3 XML
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100">
    <rsm:ExchangedDocumentContext>
        <ram:GuidelineSpecifiedDocumentContextParameter>
            <ram:ID>urn:cen.eu:en16931:2017</ram:ID>
        </ram:GuidelineSpecifiedDocumentContextParameter>
    </rsm:ExchangedDocumentContext>
</rsm:CrossIndustryInvoice>"""

        result = await parser.parse_xml(xml_content)

        assert result.success is True
        assert "zugferd" in result.format_detected.value.lower()

    @pytest.mark.asyncio
    async def test_detect_xrechnung_format(self):
        """Erkennt XRechnung-Format korrekt."""
        from app.services.einvoice import get_parser_service

        parser = get_parser_service()

        # Mock XRechnung CII XML
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100">
    <rsm:ExchangedDocumentContext>
        <ram:GuidelineSpecifiedDocumentContextParameter>
            <ram:ID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</ram:ID>
        </ram:GuidelineSpecifiedDocumentContextParameter>
    </rsm:ExchangedDocumentContext>
</rsm:CrossIndustryInvoice>"""

        result = await parser.parse_xml(xml_content)

        assert result.success is True
        assert "xrechnung" in result.format_detected.value.lower()

    @pytest.mark.asyncio
    async def test_xxe_prevention(self):
        """Verhindert XXE-Angriffe bei XML-Parsing."""
        from app.services.einvoice import get_parser_service

        parser = get_parser_service()

        # XXE-Angriffs-Payload
        malicious_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<rsm:CrossIndustryInvoice xmlns:rsm="test">
    <data>&xxe;</data>
</rsm:CrossIndustryInvoice>"""

        # Sollte XXE-Entity nicht auflösen (sicherer Parser)
        with pytest.raises(Exception):
            await parser.parse_xml(malicious_xml)

    @pytest.mark.asyncio
    async def test_parse_invoice_data(self):
        """Extrahiert Rechnungsdaten aus XML."""
        from app.services.einvoice import get_parser_service

        parser = get_parser_service()

        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
                           xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100">
    <rsm:ExchangedDocument>
        <ram:ID>RE-2024-001</ram:ID>
    </rsm:ExchangedDocument>
</rsm:CrossIndustryInvoice>"""

        result = await parser.parse_xml(xml_content)

        assert result.success is True
        assert result.invoice_data is not None
        assert result.invoice_data.invoice_number == "RE-2024-001"

    @pytest.mark.asyncio
    async def test_parse_empty_xml(self):
        """Behandelt leeres XML korrekt."""
        from app.services.einvoice import get_parser_service

        parser = get_parser_service()

        with pytest.raises(Exception):
            await parser.parse_xml("")


# ============================================================
# Validator Service Tests
# ============================================================

class TestValidatorService:
    """Tests für EInvoiceValidatorService."""

    @pytest.mark.asyncio
    async def test_validate_valid_xml(self):
        """Validiert korrektes XML erfolgreich."""
        from app.services.einvoice import get_validator_service

        validator = get_validator_service()

        valid_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
                           xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
                           xmlns:udt="urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100">
    <rsm:ExchangedDocument>
        <ram:ID>RE-001</ram:ID>
        <ram:IssueDateTime><udt:DateTimeString format="102">20240101</udt:DateTimeString></ram:IssueDateTime>
    </rsm:ExchangedDocument>
    <rsm:SupplyChainTradeTransaction>
        <ram:ApplicableHeaderTradeSettlement>
            <ram:InvoiceCurrencyCode>EUR</ram:InvoiceCurrencyCode>
        </ram:ApplicableHeaderTradeSettlement>
    </rsm:SupplyChainTradeTransaction>
</rsm:CrossIndustryInvoice>"""

        result = await validator.validate_xml(valid_xml)

        assert result.valid is True
        assert result.schema_valid is True

    @pytest.mark.asyncio
    async def test_validate_invalid_xml(self):
        """Erkennt fehlerhaftes XML."""
        from app.services.einvoice import get_validator_service

        validator = get_validator_service()

        invalid_xml = "<invalid>Not closed"

        result = await validator.validate_xml(invalid_xml)

        assert result.valid is False
        assert result.error_count > 0

    @pytest.mark.asyncio
    async def test_business_rule_validation(self):
        """Prüft Geschäftsregeln (z.B. fehlende Pflichtfelder)."""
        from app.services.einvoice import get_validator_service

        validator = get_validator_service()

        # XML ohne Rechnungsnummer (BR-01 Verletzung)
        xml_without_number = """<?xml version="1.0" encoding="UTF-8"?>
<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100">
    <rsm:ExchangedDocument>
        <!-- Keine ID -->
    </rsm:ExchangedDocument>
</rsm:CrossIndustryInvoice>"""

        result = await validator.validate_xml(xml_without_number)

        assert result.valid is False
        # Sollte BR-01 Error enthalten
        br01_found = any(m.rule_id == "BR-01" for m in result.messages)
        assert br01_found is True

    @pytest.mark.asyncio
    async def test_pdfa3_compliance(self):
        """Prüft PDF/A-3 Compliance."""
        from app.services.einvoice import get_validator_service

        validator = get_validator_service()

        # Mock PDF (minimal)
        minimal_pdf = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
trailer << /Size 4 /Root 1 0 R >>
%%EOF"""

        result = await validator.validate_pdf(minimal_pdf)

        # Sollte fehlschlagen (kein embedded XML)
        assert result.valid is False or result.pdf_a_compliant is False


# ============================================================
# Generator Service Tests
# ============================================================

class TestGeneratorService:
    """Tests für ZUGFeRDGeneratorService."""

    @pytest.mark.asyncio
    async def test_generate_minimum_profile(self):
        """Generiert MINIMUM-Profil ZUGFeRD."""
        from app.services.einvoice import get_generator_service
        from app.api.schemas.einvoice import ZUGFeRDProfile
        from app.api.schemas.extracted_data import ExtractedInvoiceData

        generator = get_generator_service()

        # Mock Invoice Data
        invoice_data = ExtractedInvoiceData(
            invoice_number="RE-001",
            invoice_date="2024-01-01",
            gross_amount=100.0,
        )

        xml = await generator.generate_xml_only(invoice_data, profile="MINIMUM")

        assert xml is not None
        assert "RE-001" in xml
        assert "CrossIndustryInvoice" in xml

    @pytest.mark.asyncio
    async def test_generate_en16931_profile(self):
        """Generiert EN16931-Profil ZUGFeRD."""
        from app.services.einvoice import get_generator_service
        from app.api.schemas.extracted_data import ExtractedInvoiceData

        generator = get_generator_service()

        invoice_data = ExtractedInvoiceData(
            invoice_number="RE-002",
            invoice_date="2024-01-15",
            gross_amount=500.0,
            net_amount=420.0,
            vat_amount=80.0,
        )

        xml = await generator.generate_xml_only(invoice_data, profile="EN16931")

        assert xml is not None
        assert "urn:cen.eu:en16931:2017" in xml

    @pytest.mark.asyncio
    async def test_generate_xrechnung_xml(self):
        """Generiert XRechnung UBL XML."""
        from app.services.einvoice import get_generator_service
        from app.api.schemas.extracted_data import ExtractedInvoiceData

        generator = get_generator_service()

        invoice_data = ExtractedInvoiceData(
            invoice_number="XR-001",
            invoice_date="2024-02-01",
            gross_amount=1000.0,
            buyer_reference="99012-12345-67",  # Leitweg-ID
        )

        xml = await generator.generate_xml_only(invoice_data, profile="XRECHNUNG")

        assert xml is not None
        assert "99012-12345-67" in xml  # Leitweg-ID enthalten

    @pytest.mark.asyncio
    async def test_missing_invoice_data(self):
        """Behandelt fehlende Rechnungsdaten."""
        from app.services.einvoice import get_generator_service
        from app.api.schemas.extracted_data import ExtractedInvoiceData

        generator = get_generator_service()

        # Invoice ohne Nummer (sollte fehlschlagen)
        invoice_data = ExtractedInvoiceData(
            invoice_date="2024-01-01",
            gross_amount=100.0,
        )

        # Sollte None zurückgeben oder Exception werfen
        xml = await generator.generate_xml_only(invoice_data, profile="MINIMUM")
        assert xml is None or len(xml) == 0


# ============================================================
# Embedder Service Tests
# ============================================================

class TestEmbedderService:
    """Tests für ZUGFeRDEmbedder."""

    def test_embed_xml_in_pdf(self):
        """Embedded XML in PDF korrekt."""
        from app.services.einvoice import get_zugferd_embedder
        from app.api.schemas.einvoice import ZUGFeRDProfile

        embedder = get_zugferd_embedder()

        if not embedder.available:
            pytest.skip("Kein PDF-Backend (PyMuPDF/pikepdf) verfügbar")

        # Minimal-PDF
        pdf_content = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 4
trailer << /Size 4 /Root 1 0 R >>
%%EOF"""

        xml_content = '<?xml version="1.0"?><test>ZUGFeRD</test>'

        result_pdf, metadata = embedder.embed_xml_in_pdf(
            pdf_content, xml_content, ZUGFeRDProfile.EN16931
        )

        assert result_pdf is not None
        assert len(result_pdf) > len(pdf_content)  # PDF sollte größer sein
        assert metadata["profile"] == "EN16931"
        assert metadata["xml_hash"] is not None

    def test_pymupdf_backend(self):
        """Testet PyMuPDF Backend."""
        from app.services.einvoice import get_zugferd_embedder

        embedder = get_zugferd_embedder()

        # Prüfe welches Backend verwendet wird
        if embedder._backend == "pymupdf":
            assert embedder.available is True
        else:
            pytest.skip("PyMuPDF nicht verfügbar")

    def test_pikepdf_backend(self):
        """Testet pikepdf Backend."""
        from app.services.einvoice import get_zugferd_embedder

        embedder = get_zugferd_embedder()

        if embedder._backend == "pikepdf":
            assert embedder.available is True
        else:
            pytest.skip("pikepdf nicht verfügbar")


# ============================================================
# Celery Task Tests
# ============================================================

class TestEInvoiceTasks:
    """Tests für E-Invoice Celery Tasks."""

    @patch("app.workers.tasks.einvoice_tasks.get_async_session_context")
    @patch("app.services.einvoice.get_parser_service")
    @patch("app.services.storage_service.get_storage_service")
    def test_parse_einvoice_task_success(
        self, mock_storage, mock_parser, mock_db_context
    ):
        """Parse-Task verarbeitet Dokument erfolgreich."""
        from app.workers.tasks.einvoice_tasks import parse_einvoice_task
        from app.api.schemas.einvoice import EInvoiceParseResponse, EInvoiceFormatDetected

        # Mock DB Session
        mock_session = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_session

        # Mock Document
        doc_id = uuid4()
        company_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.company_id = company_id
        mock_doc.original_filename = "rechnung.pdf"
        mock_doc.file_path = "path/to/file.pdf"
        mock_doc.owner_id = uuid4()

        # result.scalar_one_or_none() ist SYNCHRON -> Result als MagicMock,
        # nur db.execute awaitet (AsyncMock).
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute = AsyncMock(return_value=exec_result)

        # Mock Storage
        mock_storage_instance = AsyncMock()
        mock_storage_instance.get_document.return_value = b"%PDF-1.4..."
        mock_storage.return_value = mock_storage_instance

        # Mock Parser
        mock_parser_instance = AsyncMock()
        mock_parse_result = MagicMock()
        mock_parse_result.einvoice_id = uuid4()
        mock_parse_result.format_detected = EInvoiceFormatDetected.ZUGFERD_2_3
        mock_parse_result.profile = None
        mock_parser_instance.parse_and_store.return_value = mock_parse_result
        mock_parser.return_value = mock_parser_instance

        # Task ausführen
        result = parse_einvoice_task(str(doc_id), str(company_id))

        assert result["success"] is True
        assert "einvoice_id" in result
        # Echter Enum-Wert von EInvoiceFormatDetected.ZUGFERD_2_3
        assert result["format"] == "zugferd_2.3"

    @patch("app.workers.tasks.einvoice_tasks.get_async_session_context")
    @patch("app.services.einvoice.get_generator_service")
    @patch("app.services.storage_service.get_storage_service")
    def test_generate_zugferd_task_success(
        self, mock_storage, mock_generator, mock_db_context
    ):
        """ZUGFeRD-Generierung erfolgreich."""
        from app.workers.tasks.einvoice_tasks import generate_zugferd_task

        # Mock DB Session
        mock_session = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_session

        # Mock Document mit extracted_data
        doc_id = uuid4()
        company_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.company_id = company_id
        mock_doc.extracted_data = {"invoice": {"invoice_number": "RE-001"}}

        # result.scalar_one_or_none() ist SYNCHRON -> Result als MagicMock.
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute = AsyncMock(return_value=exec_result)

        # Mock Generator
        mock_generator_instance = AsyncMock()
        einvoice_id = uuid4()
        mock_generator_instance.generate_zugferd_pdf.return_value = (b"%PDF-1.4...", einvoice_id)
        mock_generator.return_value = mock_generator_instance

        # Mock Storage
        mock_storage_instance = AsyncMock()
        mock_storage.return_value = mock_storage_instance

        # Task ausführen
        result = generate_zugferd_task(str(doc_id), "EN16931", str(company_id))

        assert result["success"] is True
        assert result["einvoice_id"] == str(einvoice_id)
        assert result["profile"] == "EN16931"

    @patch("app.workers.tasks.einvoice_tasks.get_async_session_context")
    @patch("app.services.einvoice.get_generator_service")
    @patch("app.services.storage_service.get_storage_service")
    def test_generate_xrechnung_task_success(
        self, mock_storage, mock_generator, mock_db_context
    ):
        """XRechnung-Generierung erfolgreich."""
        from app.workers.tasks.einvoice_tasks import generate_xrechnung_task

        # Mock DB Session
        mock_session = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_session

        # Mock Document
        doc_id = uuid4()
        company_id = uuid4()
        mock_doc = MagicMock()
        mock_doc.id = doc_id
        mock_doc.company_id = company_id
        mock_doc.extracted_data = {"invoice": {"invoice_number": "XR-001"}}

        # result.scalar_one_or_none() ist SYNCHRON -> Result als MagicMock.
        exec_result = MagicMock()
        exec_result.scalar_one_or_none.return_value = mock_doc
        mock_session.execute = AsyncMock(return_value=exec_result)

        # Mock Generator
        mock_generator_instance = AsyncMock()
        einvoice_id = uuid4()
        mock_generator_instance.generate_xrechnung_xml.return_value = ("<xml>test</xml>", einvoice_id)
        mock_generator.return_value = mock_generator_instance

        # Mock Storage
        mock_storage_instance = AsyncMock()
        mock_storage.return_value = mock_storage_instance

        # Task ausführen
        result = generate_xrechnung_task(
            str(doc_id), "CII", "99012-12345-67", str(company_id)
        )

        assert result["success"] is True
        assert result["einvoice_id"] == str(einvoice_id)
        assert result["syntax"] == "CII"
        assert result["leitweg_id"] == "99012-12345-67"

    @patch("app.workers.tasks.einvoice_tasks.get_async_session_context")
    @patch("app.services.einvoice.get_validator_service")
    def test_batch_validate_task(
        self, mock_validator, mock_db_context
    ):
        """Batch-Validierung verarbeitet alle Dokumente."""
        from app.workers.tasks.einvoice_tasks import batch_validate_einvoices_task

        # Mock DB Session
        mock_session = AsyncMock()
        mock_db_context.return_value.__aenter__.return_value = mock_session

        # Mock 3 EInvoiceDocuments
        mock_einvoice1 = MagicMock()
        mock_einvoice1.id = uuid4()
        mock_einvoice1.document_id = uuid4()
        mock_einvoice1.format = "zugferd"
        mock_einvoice1.xml_content = "<xml>valid</xml>"

        mock_einvoice2 = MagicMock()
        mock_einvoice2.id = uuid4()
        mock_einvoice2.document_id = uuid4()
        mock_einvoice2.format = "xrechnung_cii"
        mock_einvoice2.xml_content = "<xml>valid</xml>"

        # result.scalars().all() ist SYNCHRON -> Result als MagicMock.
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [
            mock_einvoice1, mock_einvoice2
        ]
        mock_session.execute = AsyncMock(return_value=exec_result)

        # Mock Validator
        mock_validator_instance = AsyncMock()
        mock_validation_result = MagicMock()
        mock_validation_result.valid = True
        mock_validation_result.messages = []
        mock_validation_result.error_count = 0
        mock_validation_result.warning_count = 0
        mock_validator_instance.validate_xml.return_value = mock_validation_result
        mock_validator.return_value = mock_validator_instance

        # Task ausführen
        result = batch_validate_einvoices_task("all")

        assert result["success"] is True
        assert result["validated_count"] == 2
        assert result["error_count"] == 0

    @pytest.mark.asyncio
    @patch("app.workers.tasks.einvoice_tasks.get_async_session_context")
    async def test_task_error_handling(self, mock_db_context):
        """Tasks behandeln Fehler korrekt."""
        from app.workers.tasks.einvoice_tasks import parse_einvoice_task

        # Mock DB wirft Exception
        mock_db_context.side_effect = Exception("Datenbankfehler")

        # Task sollte Exception abfangen und Fehler zurückgeben
        result = parse_einvoice_task(str(uuid4()), str(uuid4()))

        assert result["success"] is False
        assert "error" in result
        assert "Datenbankfehler" in result["error"] or "Task-Ausführung" in result["error"]
