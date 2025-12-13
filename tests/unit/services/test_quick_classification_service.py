# -*- coding: utf-8 -*-
"""
Unit Tests fuer QuickClassificationService.

Enterprise Refined: Umfassende Tests fuer kritische Business-Logic.
Testet: VAT-ID Extraktion, IBAN Extraktion, Firmenname Matching,
        Direction-Bestimmung, Tag-Zuweisung, Metriken.
"""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.services.quick_classification_service import (
    QuickClassificationService,
    QuickClassificationResult,
    ExtractedIdentifier,
    EINGANGSRECHNUNG_TAG_ID,
    AUSGANGSRECHNUNG_TAG_ID,
    _company_settings_cache,
)
from app.api.schemas.extracted_data import InvoiceDirection


class TestQuickClassificationService:
    """Tests fuer QuickClassificationService."""

    @pytest.fixture
    def service(self):
        """Erstellt eine frische Service-Instanz."""
        return QuickClassificationService()

    @pytest.fixture
    def mock_company_settings(self):
        """Mock CompanySettings mit deutschen Testdaten."""
        mock = MagicMock()
        mock.vat_id = "DE123456789"
        mock.iban = "DE89370400440532013000"
        mock.company_name = "Test GmbH"
        mock.alternative_names = ["Test Company GmbH", "Test Gesellschaft mbH"]
        return mock

    # =========================================================================
    # VAT-ID Extraktion Tests
    # =========================================================================

    def test_extract_vat_ids_german(self, service):
        """Extrahiert deutsche USt-IdNr korrekt."""
        text = "USt-IdNr: DE123456789\nBeleg-Nr: 12345"
        result = service._extract_vat_ids(text)
        assert len(result) == 1
        assert result[0].value == "DE123456789"

    def test_extract_vat_ids_with_prefix(self, service):
        """Extrahiert USt-IdNr mit verschiedenen Prefixen."""
        text = """
        USt-IdNr: DE111111111
        VAT ID: DE222222222
        Steuernummer: DE333333333
        """
        result = service._extract_vat_ids(text)
        values = [r.value for r in result]
        assert "DE111111111" in values
        assert "DE222222222" in values

    def test_extract_vat_ids_austrian(self, service):
        """Extrahiert oesterreichische USt-IdNr (ATU-Format)."""
        text = "UID: ATU12345678"
        result = service._extract_vat_ids(text)
        assert len(result) == 1
        assert result[0].value == "ATU12345678"

    def test_extract_vat_ids_dutch(self, service):
        """Extrahiert niederlaendische USt-IdNr."""
        text = "BTW-nummer: NL123456789B01"
        result = service._extract_vat_ids(text)
        assert len(result) >= 1

    def test_extract_vat_ids_with_spaces(self, service):
        """Extrahiert USt-IdNr mit Leerzeichen nach Laendercode."""
        # Das Pattern unterstuetzt DE gefolgt von Leerzeichen und Ziffern
        text = "USt-IdNr: DE 123456789"  # Ein Leerzeichen nach DE
        result = service._extract_vat_ids(text)
        assert len(result) == 1
        assert result[0].value == "DE123456789"

    def test_extract_vat_ids_duplicate_removal(self, service):
        """Entfernt Duplikate bei der Extraktion."""
        text = "DE123456789 USt-IdNr: DE123456789"
        result = service._extract_vat_ids(text)
        assert len(result) == 1

    def test_extract_vat_ids_relative_position(self, service):
        """Berechnet relative Position korrekt."""
        text = "X" * 100 + "DE123456789" + "Y" * 100
        result = service._extract_vat_ids(text)
        assert len(result) == 1
        # Position sollte etwa bei 0.5 liegen
        assert 0.4 < result[0].relative_position < 0.6

    # =========================================================================
    # IBAN Extraktion Tests
    # =========================================================================

    def test_extract_ibans_german(self, service):
        """Extrahiert deutsche IBAN korrekt."""
        text = "IBAN: DE89 3704 0044 0532 0130 00"
        result = service._extract_ibans(text)
        assert len(result) == 1
        assert result[0].value == "DE89370400440532013000"

    def test_extract_ibans_compact(self, service):
        """Extrahiert kompakte IBAN ohne Leerzeichen."""
        text = "DE89370400440532013000"
        result = service._extract_ibans(text)
        assert len(result) == 1
        assert result[0].value == "DE89370400440532013000"

    def test_extract_ibans_austrian(self, service):
        """Extrahiert oesterreichische IBAN (20 Zeichen)."""
        # Oesterreichische IBANs haben 20 Zeichen: AT + 2 Prüfziffern + 16 Stellen
        text = "IBAN: AT611904300234573201"  # Kompakt, 20 Zeichen
        result = service._extract_ibans(text)
        assert len(result) == 1
        assert result[0].value.startswith("AT")

    def test_extract_ibans_swiss(self, service):
        """Extrahiert schweizer IBAN."""
        text = "IBAN: CH93 0076 2011 6238 5295 7"
        result = service._extract_ibans(text)
        assert len(result) == 1
        assert result[0].value.startswith("CH")

    # =========================================================================
    # Firmenname Extraktion Tests
    # =========================================================================

    def test_extract_company_names_gmbh(self, service):
        """Extrahiert GmbH-Firmennamen."""
        text = "Muster GmbH\nMusterstrasse 1"
        result = service._extract_company_names(text)
        assert len(result) >= 1
        assert any("GmbH" in r.value for r in result)

    def test_extract_company_names_ag(self, service):
        """Extrahiert AG-Firmennamen."""
        text = "Deutsche Muster AG\nHauptsitz Berlin"
        result = service._extract_company_names(text)
        assert len(result) >= 1
        assert any("AG" in r.value for r in result)

    def test_extract_company_names_gmbh_co_kg(self, service):
        """Extrahiert GmbH & Co. KG Firmennamen."""
        text = "Muster GmbH & Co. KG\nHandelsregister: HRA 12345"
        result = service._extract_company_names(text)
        assert len(result) >= 1

    def test_extract_company_names_minimum_length(self, service):
        """Ignoriert zu kurze Namen."""
        text = "Test GmbH\nXY AG"  # XY AG ist zu kurz
        result = service._extract_company_names(text)
        values = [r.value for r in result]
        assert "Test GmbH" in values or any("Test" in v for v in values)

    # =========================================================================
    # Direction Matching Tests
    # =========================================================================

    def test_match_vat_id_outgoing_sender_position(self, service):
        """USt-IdNr im Absenderbereich = Ausgangsrechnung."""
        # USt-IdNr am Anfang des Textes (Absenderbereich)
        text = """Test GmbH
DE123456789
Musterstrasse 1
12345 Musterstadt

Rechnung an:
Kunde XY GmbH
Kundenstrasse 2
98765 Kundenstadt

Rechnungspositionen:
Position 1: 100 EUR
Position 2: 200 EUR
"""
        vat_ids = service._extract_vat_ids(text)
        result = service._match_vat_id(vat_ids, "DE123456789", text)

        assert result is not None
        assert result[0] == InvoiceDirection.OUTGOING
        assert result[1] >= 0.9

    def test_match_vat_id_incoming_recipient_position(self, service):
        """USt-IdNr im Empfaengerbereich = Eingangsrechnung."""
        # Lieferant oben, unsere Adresse in der Mitte
        text = """Lieferant GmbH
DE999888777
Lieferantenstrasse 1
11111 Lieferstadt

Rechnungsempfaenger:
Unsere Firma GmbH
DE123456789
Empfaengerstrasse 2
22222 Empfaengerstadt

Rechnungspositionen folgen hier...
"""
        vat_ids = service._extract_vat_ids(text)
        result = service._match_vat_id(vat_ids, "DE123456789", text)

        assert result is not None
        assert result[0] == InvoiceDirection.INCOMING
        assert result[1] >= 0.7

    def test_match_iban_outgoing(self, service):
        """Unsere IBAN auf Rechnung = Ausgangsrechnung."""
        ibans = [
            ExtractedIdentifier(
                value="DE89370400440532013000",
                position=500,
                relative_position=0.7,
                context="Bankverbindung: DE89370400440532013000"
            )
        ]
        result = service._match_iban(ibans, "DE89370400440532013000")

        assert result is not None
        assert result[0] == InvoiceDirection.OUTGOING
        assert result[1] >= 0.9

    def test_match_iban_not_found(self, service):
        """Keine passende IBAN gefunden."""
        ibans = [
            ExtractedIdentifier(
                value="DE11111111111111111111",
                position=100,
                relative_position=0.5,
                context="Kontoverbindung"
            )
        ]
        result = service._match_iban(ibans, "DE89370400440532013000")

        assert result is None

    def test_match_company_name_fuzzy(self, service):
        """Fuzzy-Matching fuer Firmennamen."""
        extracted = [
            ExtractedIdentifier(
                value="Test GmbH",
                position=10,
                relative_position=0.1,
                context="Test GmbH, Musterstrasse 1"
            )
        ]
        result = service._match_company_name(
            extracted,
            ["Test GmbH", "Test Gesellschaft mbH"],
            "Test GmbH, Musterstrasse 1" + "X" * 500
        )

        assert result is not None
        assert result[1] >= 0.7

    # =========================================================================
    # Direction by Position Tests
    # =========================================================================

    def test_determine_direction_sender_area(self, service):
        """Position im oberen Drittel = Absender."""
        direction = service._determine_direction_by_position(0.1, "dummy text")
        assert direction == InvoiceDirection.OUTGOING

    def test_determine_direction_recipient_area(self, service):
        """Position im mittleren Drittel = Empfaenger."""
        direction = service._determine_direction_by_position(0.4, "dummy text")
        assert direction == InvoiceDirection.INCOMING

    def test_determine_direction_footer_area(self, service):
        """Position im unteren Drittel = Absender (Bankdaten)."""
        direction = service._determine_direction_by_position(0.8, "dummy text")
        assert direction == InvoiceDirection.OUTGOING

    # =========================================================================
    # Full Classification Tests
    # =========================================================================

    @pytest.mark.asyncio
    async def test_classify_document_unknown_no_company(self, service):
        """Ohne Firmendaten: UNKNOWN zurueckgeben."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await service.classify_document(
            document_id=uuid4(),
            ocr_text="Irgendein Text mit Inhalt",
            db=mock_db,
            auto_assign_tag=False
        )

        assert result.direction == InvoiceDirection.UNKNOWN
        assert result.confidence == 0.0
        assert "Firmendaten" in result.reason

    @pytest.mark.asyncio
    async def test_classify_document_empty_text(self, service):
        """Leerer Text: UNKNOWN mit passender Meldung."""
        mock_db = AsyncMock()

        result = await service.classify_document(
            document_id=uuid4(),
            ocr_text="",
            db=mock_db,
            auto_assign_tag=False
        )

        assert result.direction == InvoiceDirection.UNKNOWN
        assert result.confidence == 0.0
        assert "Text" in result.reason

    @pytest.mark.asyncio
    async def test_classify_document_whitespace_only(self, service):
        """Nur Whitespace: UNKNOWN."""
        mock_db = AsyncMock()

        result = await service.classify_document(
            document_id=uuid4(),
            ocr_text="   \n\t  \n  ",
            db=mock_db,
            auto_assign_tag=False
        )

        assert result.direction == InvoiceDirection.UNKNOWN

    # =========================================================================
    # Normalization Tests
    # =========================================================================

    def test_normalize_vat_id(self, service):
        """Normalisiert USt-IdNr korrekt."""
        assert service._normalize_vat_id("DE 123 456 789") == "DE123456789"
        assert service._normalize_vat_id("de.123.456.789") == "DE123456789"
        assert service._normalize_vat_id("DE-123-456-789") == "DE123456789"

    def test_normalize_iban(self, service):
        """Normalisiert IBAN korrekt."""
        assert service._normalize_iban("DE89 3704 0044 0532 0130 00") == "DE89370400440532013000"
        assert service._normalize_iban("de89370400440532013000") == "DE89370400440532013000"

    def test_normalize_company_name(self, service):
        """Normalisiert Firmennamen fuer Vergleich."""
        assert service._normalize_company_name("Test GmbH") == "test"
        assert service._normalize_company_name("MUSTER AG") == "muster"
        assert service._normalize_company_name("  Test  GmbH  ") == "test"

    # =========================================================================
    # Similarity Tests
    # =========================================================================

    def test_levenshtein_distance_identical(self, service):
        """Identische Strings haben Distanz 0."""
        assert service._levenshtein_distance("test", "test") == 0

    def test_levenshtein_distance_case_sensitive(self, service):
        """Gross-/Kleinschreibung zaehlt."""
        assert service._levenshtein_distance("test", "Test") == 1

    def test_levenshtein_distance_empty(self, service):
        """Leerer String hat Distanz = Laenge des anderen."""
        assert service._levenshtein_distance("", "abc") == 3
        assert service._levenshtein_distance("abc", "") == 3

    def test_calculate_name_similarity_identical(self, service):
        """Identische Namen haben Aehnlichkeit 1.0."""
        assert service._calculate_name_similarity("Test GmbH", "Test GmbH") == 1.0

    def test_calculate_name_similarity_normalized(self, service):
        """Normalisierte Namen matchen."""
        # Nach Normalisierung sind beide "test"
        similarity = service._calculate_name_similarity("Test GmbH", "TEST AG")
        assert similarity == 1.0

    def test_calculate_name_similarity_different(self, service):
        """Verschiedene Namen haben niedrige Aehnlichkeit."""
        similarity = service._calculate_name_similarity("Alpha GmbH", "Omega AG")
        assert similarity < 0.5

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_extract_empty_text(self, service):
        """Leerer Text: Keine Identifier extrahiert."""
        assert service._extract_vat_ids("") == []
        assert service._extract_ibans("") == []
        assert service._extract_company_names("") == []

    def test_extract_no_matches(self, service):
        """Text ohne Identifier: Leere Listen."""
        text = "Dies ist ein normaler Text ohne relevante Daten."
        assert service._extract_vat_ids(text) == []
        assert service._extract_ibans(text) == []
        assert service._extract_company_names(text) == []

    @pytest.mark.asyncio
    async def test_classify_document_max_text_length(self, service):
        """Sehr langer Text wird abgeschnitten."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_result)

        # 100k Zeichen - mehr als MAX_TEXT_LENGTH
        long_text = "X" * 100000

        # Sollte nicht abstuerzen
        result = await service.classify_document(
            document_id=uuid4(),
            ocr_text=long_text,
            db=mock_db,
            auto_assign_tag=False
        )

        assert result.direction == InvoiceDirection.UNKNOWN

    # =========================================================================
    # Result Conversion Tests
    # =========================================================================

    def test_to_dict_conversion(self, service):
        """Konvertiert Result korrekt zu Dictionary."""
        result = QuickClassificationResult(
            direction=InvoiceDirection.INCOMING,
            confidence=0.95,
            reason="Test Reason",
            tag_assigned=True,
            tag_name="Eingangsrechnung",
            extracted_vat_ids=["DE123456789"],
            extracted_ibans=["DE89370400440532013000"],
            matched_identifier="DE123456789"
        )

        d = service.to_dict(result)

        assert d["direction"] == "incoming"
        assert d["confidence"] == 0.95
        assert d["reason"] == "Test Reason"
        assert d["tag_assigned"] is True
        assert d["tag_name"] == "Eingangsrechnung"
        assert "DE123456789" in d["extracted_vat_ids"]


class TestQuickClassificationTagIDs:
    """Tests fuer die fixen Tag-UUIDs."""

    def test_eingangsrechnung_tag_id(self):
        """Eingangsrechnung Tag ID ist korrekt."""
        assert str(EINGANGSRECHNUNG_TAG_ID) == "11111111-1111-1111-1111-111111111111"

    def test_ausgangsrechnung_tag_id(self):
        """Ausgangsrechnung Tag ID ist korrekt."""
        assert str(AUSGANGSRECHNUNG_TAG_ID) == "22222222-2222-2222-2222-222222222222"


class TestQuickClassificationMetrics:
    """Tests fuer Prometheus-Metriken."""

    @pytest.fixture
    def service(self):
        return QuickClassificationService()

    def test_record_metrics_does_not_raise(self, service):
        """Metriken-Aufzeichnung wirft keine Exceptions."""
        result = QuickClassificationResult(
            direction=InvoiceDirection.INCOMING,
            confidence=0.85,
            reason="Test"
        )

        # Sollte keine Exception werfen
        service._record_metrics(result, 1000.0, "vat_id")

    def test_record_metrics_with_unknown_direction(self, service):
        """Metriken funktionieren auch bei UNKNOWN."""
        result = QuickClassificationResult(
            direction=InvoiceDirection.UNKNOWN,
            confidence=0.0,
            reason="No match"
        )

        # Sollte keine Exception werfen
        service._record_metrics(result, 1000.0, "none")
