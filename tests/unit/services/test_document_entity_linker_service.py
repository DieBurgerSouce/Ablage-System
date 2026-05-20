# -*- coding: utf-8 -*-
"""
Tests fuer DocumentEntityLinkerService.

Testet:
- Pattern-Extraktion (Kundennummern, Lieferantennummern, IBAN, VAT-ID)
- Matching-Strategien mit Confidence-Werten
- Automatische Dokument-Entity-Verknuepfung
- Batch-Verknuepfung
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.services.document_entity_linker_service import (
    DocumentEntityLinkerService,
    LinkingResult,
    MatchResult,
    extract_customer_numbers,
    extract_supplier_numbers,
    extract_matchcodes,
    extract_ibans,
    extract_vat_ids,
)
from app.db.models import Document, BusinessEntity


class TestExtractCustomerNumbers:
    """Tests fuer extract_customer_numbers Funktion."""

    def test_extract_kd_nr_pattern(self):
        """Sollte Kd-Nr Pattern extrahieren."""
        text = "Ihre Kd-Nr: 12345 ist hinterlegt"
        result = extract_customer_numbers(text)
        assert "12345" in result

    def test_extract_kundennummer_pattern(self):
        """Sollte Kundennummer Pattern extrahieren."""
        text = "Kundennummer: 67890"
        result = extract_customer_numbers(text)
        assert "67890" in result

    def test_extract_kunden_nr_pattern(self):
        """Sollte Kunden-Nr Pattern extrahieren."""
        text = "Kunden-Nr.: 11111"
        result = extract_customer_numbers(text)
        assert "11111" in result

    def test_extract_ihre_nummer_pattern(self):
        """Sollte 'Ihre Nummer' Pattern extrahieren."""
        text = "Ihre Kundennummer: 22222"
        result = extract_customer_numbers(text)
        assert "22222" in result

    def test_extract_kundenkonto_pattern(self):
        """Sollte Kundenkonto Pattern extrahieren."""
        text = "Kundenkonto: 33333"
        result = extract_customer_numbers(text)
        assert "33333" in result

    def test_extract_multiple_numbers(self):
        """Sollte mehrere Kundennummern extrahieren."""
        text = """
        Kd-Nr: 12345
        Kundennummer: 67890
        """
        result = extract_customer_numbers(text)
        assert len(result) == 2
        assert "12345" in result
        assert "67890" in result

    def test_extract_no_match_returns_empty(self):
        """Sollte leere Liste bei keinem Match zurueckgeben."""
        text = "Normaler Text ohne Kundennummer"
        result = extract_customer_numbers(text)
        assert result == []

    def test_extract_case_insensitive(self):
        """Sollte case-insensitive matchen."""
        text = "KD-NR: 44444"
        result = extract_customer_numbers(text)
        assert "44444" in result


class TestExtractSupplierNumbers:
    """Tests fuer extract_supplier_numbers Funktion."""

    def test_extract_lief_nr_pattern(self):
        """Sollte Lief-Nr Pattern extrahieren."""
        text = "Lief-Nr: 1001"
        result = extract_supplier_numbers(text)
        assert "1001" in result

    def test_extract_lieferantennummer_pattern(self):
        """Sollte Lieferantennummer Pattern extrahieren."""
        text = "Lieferantennummer: 2002"
        result = extract_supplier_numbers(text)
        assert "2002" in result

    def test_extract_kreditor_nr_pattern(self):
        """Sollte Kreditor-Nr Pattern extrahieren."""
        text = "Kreditor-Nr.: 3003"
        result = extract_supplier_numbers(text)
        assert "3003" in result


class TestExtractMatchcodes:
    """Tests fuer extract_matchcodes Funktion."""

    def test_extract_firma_pattern(self):
        """Sollte Firma: Pattern extrahieren."""
        text = "Firma: Mueller GmbH"
        result = extract_matchcodes(text)
        assert any("Mueller" in code for code in result)

    def test_extract_an_pattern(self):
        """Sollte An: Pattern extrahieren."""
        text = "An: Schulze AG"
        result = extract_matchcodes(text)
        assert any("Schulze" in code for code in result)


class TestExtractIbans:
    """Tests fuer extract_ibans Funktion."""

    def test_extract_german_iban(self):
        """Sollte deutsche IBAN extrahieren."""
        text = "Bankverbindung: DE89 3704 0044 0532 0130 00"
        result = extract_ibans(text)
        assert len(result) >= 1
        assert "DE89370400440532013000" in result

    def test_extract_iban_without_spaces(self):
        """Sollte IBAN ohne Leerzeichen extrahieren."""
        text = "IBAN: DE89370400440532013000"
        result = extract_ibans(text)
        assert "DE89370400440532013000" in result

    def test_extract_multiple_ibans(self):
        """Sollte mehrere IBANs extrahieren."""
        text = """
        Konto 1: DE89370400440532013000
        Konto 2: DE1212341234123412
        """
        result = extract_ibans(text)
        assert len(result) >= 1


class TestExtractVatIds:
    """Tests fuer extract_vat_ids Funktion."""

    def test_extract_german_vat_id(self):
        """Sollte deutsche USt-IdNr extrahieren."""
        text = "USt-IdNr.: DE123456789"
        result = extract_vat_ids(text)
        assert "DE123456789" in result

    def test_extract_de_with_spaces(self):
        """Sollte DE mit Leerzeichen extrahieren."""
        text = "Steuernummer: DE 123 456 789"
        result = extract_vat_ids(text)
        assert "DE123456789" in result

    def test_extract_vat_pattern(self):
        """Sollte VAT Pattern extrahieren."""
        text = "VAT: DE987654321"
        result = extract_vat_ids(text)
        assert "DE987654321" in result


class TestLinkingResult:
    """Tests fuer LinkingResult Dataclass."""

    def test_default_values(self):
        """Sollte korrekte Standardwerte haben."""
        result = LinkingResult()
        assert result.linked_count == 0
        assert result.unlinked_count == 0
        assert result.low_confidence_count == 0
        assert result.error_count == 0
        assert result.already_linked_count == 0
        assert result.details == []

    def test_with_values(self):
        """Sollte Werte korrekt speichern."""
        result = LinkingResult(
            linked_count=10,
            unlinked_count=5,
            low_confidence_count=3,
            error_count=1,
            details=[{"doc_id": "123", "entity_id": "456"}]
        )
        assert result.linked_count == 10
        assert result.unlinked_count == 5
        assert len(result.details) == 1


class TestMatchResult:
    """Tests fuer MatchResult Dataclass."""

    def test_create_match_result(self):
        """Sollte MatchResult korrekt erstellen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()

        result = MatchResult(
            entity=entity,
            confidence=0.99,
            match_type="customer_number",
            match_details="Kundennummer 12345 gefunden"
        )

        assert result.entity == entity
        assert result.confidence == 0.99
        assert result.match_type == "customer_number"
        assert "12345" in result.match_details


class TestDocumentEntityLinkerServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_service(self):
        """Sollte Service korrekt initialisieren."""
        mock_db = MagicMock()
        service = DocumentEntityLinkerService(mock_db)

        assert service.db == mock_db
        assert service.search_service is not None

    def test_confidence_thresholds(self):
        """Sollte korrekte Confidence-Thresholds haben."""
        mock_db = MagicMock()
        service = DocumentEntityLinkerService(mock_db)

        assert service.CUSTOMER_NUMBER_CONFIDENCE == 0.99
        assert service.MATCHCODE_EXACT_CONFIDENCE == 0.95
        assert service.IBAN_CONFIDENCE == 0.90
        assert service.VAT_ID_CONFIDENCE == 0.90
        assert service.NAME_FUZZY_CONFIDENCE == 0.80
        assert service.ADDRESS_CONFIDENCE == 0.75
        assert service.MIN_LINK_CONFIDENCE == 0.75


class TestLinkDocument:
    """Tests fuer link_document Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return DocumentEntityLinkerService(mock_db)

    @pytest.mark.asyncio
    async def test_link_document_not_found(self, service):
        """Sollte None bei nicht gefundenem Dokument zurueckgeben."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.link_document(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_link_document_no_text(self, service):
        """Sollte None bei Dokument ohne Text zurueckgeben."""
        doc = MagicMock(spec=Document)
        doc.id = uuid4()
        doc.extracted_text = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = doc
        service.db.execute = AsyncMock(return_value=mock_result)

        result = await service.link_document(doc.id)
        assert result is None

    @pytest.mark.asyncio
    async def test_link_document_by_customer_number(self, service):
        """Sollte Dokument ueber Kundennummer verknuepfen."""
        doc = MagicMock(spec=Document)
        doc.id = uuid4()
        doc.extracted_text = "Ihre Kd-Nr: 12345 ist hinterlegt"
        doc.business_entity_id = None

        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.primary_customer_number = "12345"

        mock_doc_result = MagicMock()
        mock_doc_result.scalar_one_or_none.return_value = doc
        service.db.execute = AsyncMock(return_value=mock_doc_result)

        service.search_service.find_by_customer_number = AsyncMock(return_value=entity)
        service.search_service.find_by_supplier_number = AsyncMock(return_value=None)

        result = await service.link_document(doc.id)

        assert result is not None
        assert result.entity == entity
        assert result.confidence == 0.99
        assert result.match_type == "customer_number"


class TestTryMatchingStrategies:
    """Tests fuer verschiedene Matching-Strategien."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return DocumentEntityLinkerService(mock_db)

    @pytest.mark.asyncio
    async def test_try_customer_number_match(self, service):
        """Sollte Kundennummer-Match versuchen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()

        service.search_service.find_by_customer_number = AsyncMock(return_value=entity)
        service.search_service.find_by_supplier_number = AsyncMock(return_value=None)

        text = "Kd-Nr: 12345"
        result = await service._try_customer_number_match(text)

        assert result is not None
        assert result.confidence == 0.99
        assert result.match_type == "customer_number"

    @pytest.mark.asyncio
    async def test_try_supplier_number_match(self, service):
        """Sollte Lieferantennummer-Match versuchen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()

        service.search_service.find_by_customer_number = AsyncMock(return_value=None)
        service.search_service.find_by_supplier_number = AsyncMock(return_value=entity)

        text = "Lief-Nr: 1001"
        result = await service._try_customer_number_match(text)

        assert result is not None
        assert result.confidence == 0.99
        assert result.match_type == "supplier_number"

    @pytest.mark.asyncio
    async def test_try_iban_match(self, service):
        """Sollte IBAN-Match versuchen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()

        service.search_service.find_by_iban = AsyncMock(return_value=entity)

        text = "IBAN: DE89370400440532013000"
        result = await service._try_iban_match(text)

        assert result is not None
        assert result.confidence == 0.90
        assert result.match_type == "iban"

    @pytest.mark.asyncio
    async def test_try_vat_id_match(self, service):
        """Sollte VAT-ID-Match versuchen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()

        service.search_service.find_by_vat_id = AsyncMock(return_value=entity)

        text = "USt-IdNr.: DE123456789"
        result = await service._try_vat_id_match(text)

        assert result is not None
        assert result.confidence == 0.90
        assert result.match_type == "vat_id"

    @pytest.mark.asyncio
    async def test_try_matchcode_match_exact(self, service):
        """Sollte exakten Matchcode-Match versuchen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.name = "Mueller GmbH"

        service.search_service.find_by_matchcode = AsyncMock(
            return_value=[(entity, 0.98)]
        )

        text = "Firma: Mueller GmbH"
        result = await service._try_matchcode_match(text)

        assert result is not None
        assert result.confidence == 0.95  # MATCHCODE_EXACT_CONFIDENCE
        assert result.match_type == "matchcode"

    @pytest.mark.asyncio
    async def test_try_matchcode_match_fuzzy(self, service):
        """Sollte Fuzzy-Matchcode-Match versuchen."""
        entity = MagicMock(spec=BusinessEntity)
        entity.id = uuid4()
        entity.name = "Mueller GmbH"

        service.search_service.find_by_matchcode = AsyncMock(
            return_value=[(entity, 0.87)]
        )

        text = "Firma: Müller GmbH"
        result = await service._try_matchcode_match(text)

        assert result is not None
        assert result.confidence == 0.80  # NAME_FUZZY_CONFIDENCE
        assert result.match_type == "matchcode"


class TestLinkAllDocuments:
    """Tests fuer link_all_documents Batch-Methode."""

    @pytest.fixture
    def service(self):
        mock_db = AsyncMock()
        return DocumentEntityLinkerService(mock_db)

    @pytest.mark.asyncio
    async def test_link_all_documents_empty_batch(self, service):
        """Sollte LinkingResult mit Nullen bei leerem Batch zurueckgeben."""
        # Count returns 0
        service.db.scalar = AsyncMock(return_value=0)

        # Empty batch
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        result = await service.link_all_documents()

        assert isinstance(result, LinkingResult)
        assert result.linked_count == 0


class TestFactoryFunction:
    """Tests fuer Factory-Funktion."""

    def test_get_document_entity_linker_service_creates_instance(self):
        """Sollte neue Service-Instanz erstellen."""
        from app.services.document_entity_linker_service import (
            get_document_entity_linker_service,
        )

        mock_db = MagicMock()
        service = get_document_entity_linker_service(mock_db)

        assert isinstance(service, DocumentEntityLinkerService)
        assert service.db == mock_db
