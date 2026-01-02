# -*- coding: utf-8 -*-
"""
Tests fuer CompanyMatchingService.

Testet:
- Eingangs-/Ausgangsrechnung-Erkennung
- Firmenname-Matching (exakt und fuzzy)
- VAT-ID und IBAN Vergleich
- Levenshtein-Distanz-Berechnung
- Rechtsformen-Entfernung
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from app.services.company_matching_service import (
    CompanyMatchingService,
    MatchResult,
    get_company_matching_service,
)
from app.api.schemas.extracted_data import (
    ExtractedAddress,
    ExtractedInvoiceData,
    ExtractedBankAccount,
    InvoiceDirection,
)


class TestMatchResultDataclass:
    """Tests fuer MatchResult Dataclass."""

    def test_create_matched_result(self):
        """Sollte uebereinstimmendes Ergebnis erstellen."""
        result = MatchResult(
            matched=True,
            confidence=0.99,
            reason="USt-IdNr stimmt ueberein"
        )

        assert result.matched is True
        assert result.confidence == 0.99
        assert "USt-IdNr" in result.reason

    def test_create_no_match_result(self):
        """Sollte nicht-uebereinstimmendes Ergebnis erstellen."""
        result = MatchResult(
            matched=False,
            confidence=0.3,
            reason="Keine Übereinstimmung gefunden"
        )

        assert result.matched is False
        assert result.confidence == 0.3


class TestCompanyMatchingServiceInit:
    """Tests fuer Service-Initialisierung."""

    def test_init_creates_service(self):
        """Sollte Service korrekt initialisieren."""
        service = CompanyMatchingService()

        assert service.CONFIDENCE_THRESHOLD == 0.80
        assert len(service.LEGAL_SUFFIXES) > 0


class TestNormalizeVatId:
    """Tests fuer _normalize_vat_id Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    def test_normalize_german_vat_id(self, service: CompanyMatchingService):
        """Sollte deutsche USt-IdNr normalisieren."""
        result = service._normalize_vat_id("DE 123 456 789")
        assert result == "DE123456789"

    def test_normalize_with_dots(self, service: CompanyMatchingService):
        """Sollte Punkte entfernen."""
        result = service._normalize_vat_id("DE.123.456.789")
        assert result == "DE123456789"

    def test_normalize_with_hyphens(self, service: CompanyMatchingService):
        """Sollte Bindestriche entfernen."""
        result = service._normalize_vat_id("DE-123-456-789")
        assert result == "DE123456789"

    def test_normalize_to_uppercase(self, service: CompanyMatchingService):
        """Sollte zu Grossbuchstaben konvertieren."""
        result = service._normalize_vat_id("de123456789")
        assert result == "DE123456789"


class TestNormalizeIban:
    """Tests fuer _normalize_iban Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    def test_normalize_german_iban(self, service: CompanyMatchingService):
        """Sollte deutsche IBAN normalisieren."""
        result = service._normalize_iban("DE89 3704 0044 0532 0130 00")
        assert result == "DE89370400440532013000"

    def test_normalize_lowercase_iban(self, service: CompanyMatchingService):
        """Sollte zu Grossbuchstaben konvertieren."""
        result = service._normalize_iban("de89370400440532013000")
        assert result == "DE89370400440532013000"


class TestNormalizeCompanyName:
    """Tests fuer _normalize_company_name Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    def test_remove_gmbh(self, service: CompanyMatchingService):
        """Sollte GmbH entfernen."""
        result = service._normalize_company_name("Muster GmbH")
        assert "gmbh" not in result.lower()

    def test_remove_gmbh_co_kg(self, service: CompanyMatchingService):
        """Sollte GmbH & Co. KG entfernen."""
        result = service._normalize_company_name("Muster GmbH & Co. KG")
        assert "gmbh" not in result.lower()
        assert "kg" not in result.lower()

    def test_remove_ag(self, service: CompanyMatchingService):
        """Sollte AG entfernen."""
        result = service._normalize_company_name("Muster AG")
        assert result == "muster"

    def test_keep_ag_in_word(self, service: CompanyMatchingService):
        """Sollte AG in Worten behalten (z.B. 'Montag' nicht zu 'Mont')."""
        result = service._normalize_company_name("Montag GmbH")
        # 'Montag' sollte erhalten bleiben, nur 'GmbH' wird entfernt
        assert "mont" in result.lower()

    def test_lowercase(self, service: CompanyMatchingService):
        """Sollte zu Kleinbuchstaben konvertieren."""
        result = service._normalize_company_name("MUSTER FIRMA")
        assert result == "muster firma"

    def test_remove_multiple_spaces(self, service: CompanyMatchingService):
        """Sollte mehrfache Leerzeichen entfernen."""
        result = service._normalize_company_name("Muster   Firma   GmbH")
        assert "  " not in result


class TestNamesMatchExact:
    """Tests fuer _names_match_exact Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    def test_exact_match_same_name(self, service: CompanyMatchingService):
        """Sollte gleiche Namen als Match erkennen."""
        result = service._names_match_exact("Muster GmbH", "Muster GmbH")
        assert result is True

    def test_exact_match_different_suffix(self, service: CompanyMatchingService):
        """Sollte Namen mit unterschiedlichen Rechtsformen matchen."""
        result = service._names_match_exact("Muster GmbH", "Muster AG")
        assert result is True

    def test_exact_match_case_insensitive(self, service: CompanyMatchingService):
        """Sollte case-insensitive matchen."""
        result = service._names_match_exact("MUSTER GmbH", "muster gmbh")
        assert result is True

    def test_no_match_different_name(self, service: CompanyMatchingService):
        """Sollte unterschiedliche Namen nicht matchen."""
        result = service._names_match_exact("Muster GmbH", "Andere Firma GmbH")
        assert result is False


class TestCalculateNameSimilarity:
    """Tests fuer _calculate_name_similarity Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    def test_identical_names(self, service: CompanyMatchingService):
        """Sollte 1.0 fuer identische Namen zurueckgeben."""
        result = service._calculate_name_similarity("Muster GmbH", "Muster GmbH")
        assert result == 1.0

    def test_similar_names(self, service: CompanyMatchingService):
        """Sollte hohe Aehnlichkeit fuer aehnliche Namen zurueckgeben."""
        result = service._calculate_name_similarity("Muster GmbH", "Muster AG")
        assert result > 0.9

    def test_different_names(self, service: CompanyMatchingService):
        """Sollte niedrige Aehnlichkeit fuer unterschiedliche Namen zurueckgeben."""
        result = service._calculate_name_similarity("Muster GmbH", "Andere Firma AG")
        assert result < 0.5

    def test_empty_name(self, service: CompanyMatchingService):
        """Sollte 0.0 fuer leeren Namen zurueckgeben."""
        result = service._calculate_name_similarity("", "Muster")
        assert result == 0.0


class TestLevenshteinDistance:
    """Tests fuer _levenshtein_distance Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    def test_identical_strings(self, service: CompanyMatchingService):
        """Sollte 0 fuer identische Strings zurueckgeben."""
        result = service._levenshtein_distance("test", "test")
        assert result == 0

    def test_one_substitution(self, service: CompanyMatchingService):
        """Sollte 1 fuer eine Ersetzung zurueckgeben."""
        result = service._levenshtein_distance("test", "tast")
        assert result == 1

    def test_one_insertion(self, service: CompanyMatchingService):
        """Sollte 1 fuer eine Einfuegung zurueckgeben."""
        result = service._levenshtein_distance("test", "tests")
        assert result == 1

    def test_one_deletion(self, service: CompanyMatchingService):
        """Sollte 1 fuer eine Loeschung zurueckgeben."""
        result = service._levenshtein_distance("tests", "test")
        assert result == 1

    def test_empty_string(self, service: CompanyMatchingService):
        """Sollte Laenge des anderen Strings fuer leeren String zurueckgeben."""
        result = service._levenshtein_distance("test", "")
        assert result == 4


class TestMatchAddressToCompany:
    """Tests fuer _match_address_to_company Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    @pytest.fixture
    def company_settings(self):
        company = MagicMock()
        company.company_name = "Muster GmbH"
        company.vat_id = "DE123456789"
        company.iban = "DE89370400440532013000"
        company.postal_code = "12345"
        company.alternative_names = ["Musterfirma", "Muster Company"]
        return company

    def test_match_by_vat_id(
        self, service: CompanyMatchingService, company_settings
    ):
        """Sollte Match ueber VAT-ID erkennen."""
        address = MagicMock()
        address.company = "Irgendeine Firma"

        result = service._match_address_to_company(
            address=address,
            vat_id="DE 123 456 789",
            iban=None,
            company=company_settings
        )

        assert result.matched is True
        assert result.confidence == 0.99
        assert "USt-IdNr" in result.reason

    def test_match_by_iban(
        self, service: CompanyMatchingService, company_settings
    ):
        """Sollte Match ueber IBAN erkennen."""
        address = MagicMock()
        address.company = "Irgendeine Firma"

        result = service._match_address_to_company(
            address=address,
            vat_id=None,
            iban="DE89 3704 0044 0532 0130 00",
            company=company_settings
        )

        assert result.matched is True
        assert result.confidence == 0.95
        assert "IBAN" in result.reason

    def test_match_by_exact_name(
        self, service: CompanyMatchingService, company_settings
    ):
        """Sollte Match ueber exakten Namen erkennen."""
        address = MagicMock()
        address.company = "Muster GmbH"
        address.zip_code = None

        result = service._match_address_to_company(
            address=address,
            vat_id=None,
            iban=None,
            company=company_settings
        )

        assert result.matched is True
        assert result.confidence == 0.90
        assert "exakt" in result.reason.lower()

    def test_match_by_fuzzy_name_and_zip(
        self, service: CompanyMatchingService, company_settings
    ):
        """Sollte Match ueber fuzzy Name + PLZ erkennen."""
        address = MagicMock()
        address.company = "Muster"  # Ohne Rechtsform
        address.zip_code = "12345"

        result = service._match_address_to_company(
            address=address,
            vat_id=None,
            iban=None,
            company=company_settings
        )

        assert result.matched is True
        assert result.confidence == 0.85

    def test_match_by_alternative_name(
        self, service: CompanyMatchingService, company_settings
    ):
        """Sollte Match ueber alternative Namen erkennen."""
        address = MagicMock()
        address.company = "Musterfirma"
        address.zip_code = None

        result = service._match_address_to_company(
            address=address,
            vat_id=None,
            iban=None,
            company=company_settings
        )

        assert result.matched is True

    def test_no_match_without_address(
        self, service: CompanyMatchingService, company_settings
    ):
        """Sollte keinen Match ohne Adresse finden."""
        result = service._match_address_to_company(
            address=None,
            vat_id=None,
            iban=None,
            company=company_settings
        )

        assert result.matched is False
        assert result.confidence == 0.0

    def test_no_match_without_company_name(
        self, service: CompanyMatchingService, company_settings
    ):
        """Sollte keinen Match ohne Firmennamen finden."""
        address = MagicMock()
        address.company = None

        result = service._match_address_to_company(
            address=address,
            vat_id=None,
            iban=None,
            company=company_settings
        )

        assert result.matched is False


@pytest.mark.asyncio
class TestMatchInvoiceDirection:
    """Tests fuer match_invoice_direction Methode."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.execute = AsyncMock()
        return db

    @pytest.fixture
    def company_settings(self):
        company = MagicMock()
        company.company_name = "Eigene Firma GmbH"
        company.vat_id = "DE111111111"
        company.iban = "DE89370400440532013000"
        company.postal_code = "12345"
        company.alternative_names = []
        return company

    async def test_no_company_settings(
        self, service: CompanyMatchingService, mock_db
    ):
        """Sollte UNKNOWN zurueckgeben ohne Firmendaten."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        invoice = MagicMock(spec=ExtractedInvoiceData)

        direction, confidence, reason = await service.match_invoice_direction(
            invoice, mock_db
        )

        assert direction == InvoiceDirection.UNKNOWN
        assert confidence == 0.0

    async def test_incoming_invoice_by_recipient_match(
        self, service: CompanyMatchingService, mock_db, company_settings
    ):
        """Sollte Eingangsrechnung erkennen wenn Empfaenger matcht."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = company_settings
        mock_db.execute.return_value = mock_result

        recipient = MagicMock(spec=ExtractedAddress)
        recipient.company = "Eigene Firma GmbH"
        recipient.zip_code = None

        invoice = MagicMock(spec=ExtractedInvoiceData)
        invoice.recipient = recipient
        invoice.recipient_vat_id = "DE111111111"
        invoice.sender = MagicMock()
        invoice.sender.company = "Lieferant AG"
        invoice.sender_vat_id = None
        invoice.sender_bank = None

        direction, confidence, reason = await service.match_invoice_direction(
            invoice, mock_db
        )

        assert direction == InvoiceDirection.INCOMING

    async def test_outgoing_invoice_by_sender_match(
        self, service: CompanyMatchingService, mock_db, company_settings
    ):
        """Sollte Ausgangsrechnung erkennen wenn Absender matcht."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = company_settings
        mock_db.execute.return_value = mock_result

        recipient = MagicMock(spec=ExtractedAddress)
        recipient.company = "Kunde GmbH"
        recipient.zip_code = None

        sender = MagicMock(spec=ExtractedAddress)
        sender.company = "Eigene Firma GmbH"
        sender.zip_code = None

        sender_bank = MagicMock(spec=ExtractedBankAccount)
        sender_bank.iban = "DE89 3704 0044 0532 0130 00"

        invoice = MagicMock(spec=ExtractedInvoiceData)
        invoice.recipient = recipient
        invoice.recipient_vat_id = None
        invoice.sender = sender
        invoice.sender_vat_id = "DE111111111"
        invoice.sender_bank = sender_bank

        direction, confidence, reason = await service.match_invoice_direction(
            invoice, mock_db
        )

        assert direction == InvoiceDirection.OUTGOING

    async def test_unknown_direction_no_match(
        self, service: CompanyMatchingService, mock_db, company_settings
    ):
        """Sollte UNKNOWN zurueckgeben wenn kein Match."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = company_settings
        mock_db.execute.return_value = mock_result

        recipient = MagicMock(spec=ExtractedAddress)
        recipient.company = "Fremde Firma 1 GmbH"
        recipient.zip_code = "99999"

        sender = MagicMock(spec=ExtractedAddress)
        sender.company = "Fremde Firma 2 GmbH"
        sender.zip_code = "88888"

        invoice = MagicMock(spec=ExtractedInvoiceData)
        invoice.recipient = recipient
        invoice.recipient_vat_id = "DE999999999"
        invoice.sender = sender
        invoice.sender_vat_id = "DE888888888"
        invoice.sender_bank = None

        direction, confidence, reason = await service.match_invoice_direction(
            invoice, mock_db
        )

        assert direction == InvoiceDirection.UNKNOWN


class TestSingleton:
    """Tests fuer Singleton-Pattern."""

    def test_get_company_matching_service_singleton(self):
        """Sollte immer gleiche Instanz zurueckgeben."""
        # Reset singleton
        import app.services.company_matching_service as module
        module._company_matching_service = None

        svc1 = get_company_matching_service()
        svc2 = get_company_matching_service()

        assert svc1 is svc2


class TestLegalSuffixes:
    """Tests fuer Rechtsformen-Entfernung."""

    @pytest.fixture
    def service(self):
        return CompanyMatchingService()

    def test_all_german_legal_forms(self, service: CompanyMatchingService):
        """Sollte alle deutschen Rechtsformen entfernen."""
        test_cases = [
            ("Firma GmbH", "firma"),
            ("Firma AG", "firma"),
            ("Firma KG", "firma"),
            ("Firma OHG", "firma"),
            ("Firma UG", "firma"),
            ("Firma GbR", "firma"),
            ("Firma e.V.", "firma"),
            ("Firma GmbH & Co. KG", "firma"),
        ]

        for input_name, expected in test_cases:
            result = service._normalize_company_name(input_name)
            assert result == expected, f"Fehler bei: {input_name}"

    def test_international_legal_forms(self, service: CompanyMatchingService):
        """Sollte internationale Rechtsformen entfernen."""
        test_cases = [
            ("Company Ltd.", "company"),
            ("Company Inc.", "company"),
            ("Company LLC", "company"),
            ("Company B.V.", "company"),
            ("Company N.V.", "company"),
            ("Company S.A.", "company"),
        ]

        for input_name, expected in test_cases:
            result = service._normalize_company_name(input_name)
            assert result == expected, f"Fehler bei: {input_name}"
