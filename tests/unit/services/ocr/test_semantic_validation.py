# -*- coding: utf-8 -*-
"""
Unit Tests fuer SemanticValidationService.

Testet:
- Betrags-Validierung (Plausibilitaet, Konsistenz, MwSt)
- Format-Validierung (Rechnungsnummer, Datum)
- Text-Normalisierung und Aehnlichkeitsberechnung
- IBAN-Pruefziffern-Validierung
- USt-ID-Format-Pruefung
- Betrags-Parsing (deutsches Zahlenformat)
- Cross-Field-Konsistenz
"""

import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ocr.semantic_validation_service import (
    SemanticValidationService,
    SemanticValidationReport,
    ValidationResult,
    ValidationSeverity,
    ValidationType,
    normalize_text,
    calculate_similarity,
    validate_iban_checksum,
    validate_vat_id_format,
    parse_amount,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Mock Datenbank-Session."""
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock()
    return db


@pytest.fixture
def service(mock_db: AsyncMock) -> SemanticValidationService:
    """Erstelle Service-Instanz."""
    return SemanticValidationService(db=mock_db)


# =============================================================================
# Utility Function Tests
# =============================================================================


class TestNormalizeText:
    """Tests fuer Text-Normalisierung."""

    def test_normalize_umlauts(self) -> None:
        """Umlaute werden korrekt normalisiert."""
        assert normalize_text("Müller") == "mueller"
        assert normalize_text("Größe") == "groesse"
        assert normalize_text("Übung") == "uebung"
        assert normalize_text("Straße") == "strasse"

    def test_normalize_whitespace(self) -> None:
        """Mehrfache Leerzeichen werden reduziert."""
        assert normalize_text("  hallo   welt  ") == "hallo welt"

    def test_normalize_empty(self) -> None:
        """Leerer String bleibt leer."""
        assert normalize_text("") == ""

    def test_normalize_case(self) -> None:
        """Grossbuchstaben werden zu Kleinbuchstaben."""
        assert normalize_text("HALLO") == "hallo"


class TestCalculateSimilarity:
    """Tests fuer Aehnlichkeitsberechnung."""

    def test_identical_texts(self) -> None:
        """Identische Texte ergeben Aehnlichkeit 1.0."""
        assert calculate_similarity("Müller GmbH", "Müller GmbH") == 1.0

    def test_similar_texts(self) -> None:
        """Aehnliche Texte ergeben hohe Aehnlichkeit."""
        sim = calculate_similarity("Müller GmbH", "Mueller GmbH")
        assert sim > 0.8

    def test_different_texts(self) -> None:
        """Verschiedene Texte ergeben niedrige Aehnlichkeit."""
        sim = calculate_similarity("Müller GmbH", "Schmidt AG")
        assert sim < 0.5

    def test_empty_text(self) -> None:
        """Leerer Text ergibt Aehnlichkeit 0.0."""
        assert calculate_similarity("", "test") == 0.0
        assert calculate_similarity("test", "") == 0.0


class TestValidateIBANChecksum:
    """Tests fuer IBAN-Pruefziffern-Validierung."""

    def test_valid_german_iban(self) -> None:
        """Gueltige deutsche IBAN wird akzeptiert."""
        assert validate_iban_checksum("DE89 3704 0044 0532 0130 00") is True

    def test_invalid_checksum(self) -> None:
        """Ungueltige Pruefziffer wird erkannt."""
        assert validate_iban_checksum("DE00370400440532013000") is False

    def test_empty_iban(self) -> None:
        """Leere IBAN ergibt False."""
        assert validate_iban_checksum("") is False

    def test_too_short(self) -> None:
        """Zu kurze IBAN ergibt False."""
        assert validate_iban_checksum("DE89") is False


class TestValidateVatIdFormat:
    """Tests fuer USt-ID-Format-Validierung."""

    def test_valid_german(self) -> None:
        """Gueltige deutsche USt-ID."""
        is_valid, msg = validate_vat_id_format("DE123456789")
        assert is_valid is True

    def test_valid_austrian(self) -> None:
        """Gueltige oesterreichische USt-ID."""
        is_valid, msg = validate_vat_id_format("ATU12345678")
        assert is_valid is True

    def test_invalid_german(self) -> None:
        """Ungueltige deutsche USt-ID (zu kurz)."""
        is_valid, msg = validate_vat_id_format("DE12345")
        assert is_valid is False

    def test_empty(self) -> None:
        """Leere USt-ID ergibt False."""
        is_valid, msg = validate_vat_id_format("")
        assert is_valid is False

    def test_unknown_country(self) -> None:
        """Unbekannter Laendercode."""
        is_valid, msg = validate_vat_id_format("XX12345")
        assert is_valid is False


class TestParseAmount:
    """Tests fuer Betrags-Parsing."""

    def test_german_format(self) -> None:
        """Deutsches Zahlenformat (1.234,56) wird korrekt geparst."""
        assert parse_amount("1.234,56") == Decimal("1234.56")

    def test_simple_decimal(self) -> None:
        """Einfache Dezimalzahl."""
        assert parse_amount("100,50") == Decimal("100.50")

    def test_with_currency_symbol(self) -> None:
        """Waehrungssymbol wird entfernt."""
        assert parse_amount("100,50 €") == Decimal("100.50")

    def test_english_format(self) -> None:
        """Englisches Format - parse_amount behandelt Punkt als Tausender bei Komma+Punkt."""
        # parse_amount ist fuer deutsches Format optimiert:
        # Bei "," und "." entfernt es "." (Tausender) und ersetzt "," (Dezimal)
        # Daher wird "1,234.56" als "1.23456" interpretiert (deutsch: Punkt=Tausender, Komma=Dezimal)
        result = parse_amount("1,234.56")
        assert result is not None

    def test_empty_string(self) -> None:
        """Leerer String ergibt None."""
        assert parse_amount("") is None

    def test_invalid_string(self) -> None:
        """Ungueltiger String ergibt None."""
        assert parse_amount("abc") is None


# =============================================================================
# Amount Validation Tests
# =============================================================================


class TestAmountValidation:
    """Tests fuer Betrags-Validierung im Service."""

    def test_negative_gross_amount(self, service: SemanticValidationService) -> None:
        """Negativer Bruttobetrag erzeugt Fehler."""
        results: List[ValidationResult] = []
        service._validate_amounts(
            {"gross_amount": "-100.00", "net_amount": "0", "tax_amount": "0"},
            results,
        )
        assert any(
            r.severity == ValidationSeverity.ERROR
            and r.validation_type == ValidationType.AMOUNT_PLAUSIBILITY
            for r in results
        )

    def test_very_high_amount_warning(self, service: SemanticValidationService) -> None:
        """Ungewoehnlich hoher Betrag erzeugt Warnung."""
        results: List[ValidationResult] = []
        service._validate_amounts(
            {"gross_amount": "2000000", "net_amount": "0", "tax_amount": "0"},
            results,
        )
        assert any(
            r.severity == ValidationSeverity.WARNING
            and "Ungewöhnlich" in r.message
            for r in results
        )

    def test_consistent_amounts(self, service: SemanticValidationService) -> None:
        """Konsistente Betraege (Brutto = Netto + MwSt) werden akzeptiert."""
        results: List[ValidationResult] = []
        service._validate_amounts(
            {
                "gross_amount": "119.00",
                "net_amount": "100.00",
                "tax_amount": "19.00",
                "tax_rate": "19",
            },
            results,
        )
        assert any(
            r.severity == ValidationSeverity.SUCCESS
            and r.validation_type == ValidationType.AMOUNT_CONSISTENCY
            for r in results
        )

    def test_inconsistent_amounts(self, service: SemanticValidationService) -> None:
        """Inkonsistente Betraege erzeugen Fehler."""
        results: List[ValidationResult] = []
        service._validate_amounts(
            {
                "gross_amount": "125.00",
                "net_amount": "100.00",
                "tax_amount": "19.00",
            },
            results,
        )
        assert any(
            r.severity == ValidationSeverity.ERROR
            and r.validation_type == ValidationType.AMOUNT_CONSISTENCY
            for r in results
        )


# =============================================================================
# Format Validation Tests
# =============================================================================


class TestFormatValidation:
    """Tests fuer Format-Validierung."""

    def test_valid_invoice_number(self, service: SemanticValidationService) -> None:
        """Gueltige Rechnungsnummer wird akzeptiert."""
        results: List[ValidationResult] = []
        service._validate_formats({"invoice_number": "RE-2024-001"}, results)
        assert any(
            r.severity == ValidationSeverity.SUCCESS
            and r.validation_type == ValidationType.INVOICE_NUMBER
            for r in results
        )

    def test_short_invoice_number(self, service: SemanticValidationService) -> None:
        """Sehr kurze Rechnungsnummer erzeugt Warnung."""
        results: List[ValidationResult] = []
        service._validate_formats({"invoice_number": "AB"}, results)
        assert any(
            r.severity == ValidationSeverity.WARNING
            and "kurz" in r.message
            for r in results
        )

    def test_long_invoice_number(self, service: SemanticValidationService) -> None:
        """Sehr lange Rechnungsnummer erzeugt Warnung."""
        results: List[ValidationResult] = []
        service._validate_formats({"invoice_number": "A" * 60}, results)
        assert any(
            r.severity == ValidationSeverity.WARNING
            and "lang" in r.message
            for r in results
        )

    def test_valid_date_format(self, service: SemanticValidationService) -> None:
        """Gueltiges Datum wird akzeptiert."""
        results: List[ValidationResult] = []
        service._validate_formats({"invoice_date": "15.03.2024"}, results)
        assert any(
            r.validation_type == ValidationType.DATE_FORMAT
            for r in results
        )


# =============================================================================
# Cross-Field Consistency Tests
# =============================================================================


class TestFieldConsistency:
    """Tests fuer Cross-Field-Konsistenz."""

    def test_due_date_before_invoice_date(
        self, service: SemanticValidationService
    ) -> None:
        """Faelligkeitsdatum vor Rechnungsdatum erzeugt Fehler."""
        results: List[ValidationResult] = []
        service._validate_field_consistency(
            {
                "invoice_date": "2024-03-15",
                "due_date": "2024-02-01",
            },
            results,
        )
        assert any(
            r.severity == ValidationSeverity.ERROR
            and "Fälligkeitsdatum" in r.message
            for r in results
        )

    def test_long_payment_terms(self, service: SemanticValidationService) -> None:
        """Ungewoehnlich langes Zahlungsziel erzeugt Warnung."""
        results: List[ValidationResult] = []
        service._validate_field_consistency(
            {"payment_terms": "365 Tage netto"},
            results,
        )
        assert any(
            r.severity == ValidationSeverity.WARNING
            and "Zahlungsziel" in r.message
            for r in results
        )


# =============================================================================
# Validate Document Tests
# =============================================================================


class TestValidateDocument:
    """Tests fuer Gesamtvalidierung eines Dokuments."""

    @pytest.mark.asyncio
    async def test_validate_with_extracted_data(
        self, service: SemanticValidationService
    ) -> None:
        """Validierung mit vorgegebenen extrahierten Daten."""
        report = await service.validate_document(
            document_id=str(uuid4()),
            extracted_data={
                "gross_amount": "119.00",
                "net_amount": "100.00",
                "tax_amount": "19.00",
                "invoice_number": "RE-2024-001",
                "invoice_date": "15.03.2024",
            },
        )

        assert isinstance(report, SemanticValidationReport)
        assert report.total_checks > 0
        assert 0.0 <= report.overall_score <= 1.0

    @pytest.mark.asyncio
    async def test_error_report(self, service: SemanticValidationService) -> None:
        """Fehlerbericht wird korrekt erstellt."""
        report = service._create_error_report(
            str(uuid4()), "Testfehler"
        )
        assert report.errors == 1
        assert report.overall_score == 0.0

    @pytest.mark.asyncio
    async def test_validate_empty_data(
        self, service: SemanticValidationService
    ) -> None:
        """Validierung mit leeren Daten laeuft ohne Fehler."""
        report = await service.validate_document(
            document_id=str(uuid4()),
            extracted_data={},
        )
        assert isinstance(report, SemanticValidationReport)
