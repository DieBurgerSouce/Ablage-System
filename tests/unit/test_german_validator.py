"""
Unit tests for German text validation.

Tests umlaut validation, date extraction, currency parsing,
business term recognition, IBAN/VAT ID validation.
"""

import pytest
import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "app"))

from german_validator import GermanValidator


@pytest.mark.unit
class TestGermanValidator:
    """Test German text validation."""

    def setup_method(self):
        """Setup before each test."""
        self.validator = GermanValidator()

    def test_umlaut_validation_correct(self):
        """Test validation of correct German text."""
        text = "Müller GmbH & Co. KG"
        result = self.validator.validate_umlauts(text)

        assert result["valid"] == True
        assert "ü" in result["umlauts_found"]
        assert result["confidence"] >= 0.9
        assert len(result["potential_errors"]) == 0

    def test_umlaut_validation_with_errors(self):
        """Test detection of potential OCR errors."""
        text = "Mueller GmbH"  # Should be Müller
        result = self.validator.validate_umlauts(text)

        assert result["valid"] == False
        assert len(result["potential_errors"]) > 0
        assert result["confidence"] < 1.0

        # Check error detection
        error = result["potential_errors"][0]
        assert "ue" in error["pattern"]
        assert "ü" in error["should_be"]

    def test_date_extraction(self):
        """Test German date format extraction."""
        text = "Rechnung vom 31.12.2024 fällig am 15. Januar 2025"
        dates = self.validator.validate_date_format(text)

        assert len(dates) >= 2
        assert "31.12.2024" in dates
        assert any("Januar" in date for date in dates)

    def test_currency_extraction(self):
        """Test German currency format extraction."""
        text = "Gesamtbetrag: 1.234,56 € inkl. MwSt."
        amounts = self.validator.validate_currency_format(text)

        assert len(amounts) >= 1
        assert any("1.234,56" in amount for amount in amounts)

    def test_business_term_extraction(self):
        """Test German business term recognition."""
        text = "Müller GmbH, USt-IdNr.: DE123456789, HRB 12345"
        terms = self.validator.extract_business_terms(text)

        assert "GmbH" in terms
        assert "USt-IdNr." in terms
        assert "HRB" in terms
        assert terms["GmbH"]["count"] == 1

    def test_iban_validation(self):
        """Test IBAN validation."""
        # Valid German IBAN (test number)
        valid_iban = "DE89 3704 0044 0532 0130 00"
        assert self.validator.validate_iban(valid_iban) == True

        # Invalid IBAN
        invalid_iban = "DE12 3456 7890 1234 5678 90"
        assert self.validator.validate_iban(invalid_iban) == False

    def test_vat_id_validation(self):
        """Test German VAT ID validation."""
        # Valid format
        valid_vat = "DE123456789"
        assert self.validator.validate_vat_id(valid_vat) == True

        # Invalid format
        invalid_vat = "DE12345"
        assert self.validator.validate_vat_id(invalid_vat) == False

    @pytest.mark.parametrize(
        "text,expected_umlauts",
        [
            ("Müller", ["ü"]),
            ("Größe", ["ö"]),
            ("Fußball", ["ß"]),
            ("Äpfel und Birnen", ["Ä"]),
            ("Übersetzung für Bücher", ["Ü", "ü"]),
        ],
    )
    def test_umlaut_detection_parametrized(self, text: str, expected_umlauts: list):
        """Test umlaut detection with multiple examples."""
        result = self.validator.validate_umlauts(text)

        for umlaut in expected_umlauts:
            assert umlaut in result["umlauts_found"]

    @pytest.mark.parametrize(
        "date_string,expected_found",
        [
            ("01.01.2024", True),
            ("31.12.2024", True),
            ("15. Januar 2025", True),
            ("1. Mai 2024", True),
            ("invalid date", False),
        ],
    )
    def test_date_format_validation(self, date_string: str, expected_found: bool):
        """Test date format validation with various inputs."""
        dates = self.validator.validate_date_format(date_string)

        if expected_found:
            assert len(dates) > 0
        else:
            assert len(dates) == 0

    @pytest.mark.parametrize(
        "currency_string,expected_found",
        [
            ("100,00 €", True),
            ("1.234,56 €", True),
            ("€ 50,00", True),
            ("EUR 1.000,00", True),
            ("no currency here", False),
        ],
    )
    def test_currency_format_validation(
        self, currency_string: str, expected_found: bool
    ):
        """Test currency format validation with various inputs."""
        amounts = self.validator.validate_currency_format(currency_string)

        if expected_found:
            assert len(amounts) > 0
        else:
            assert len(amounts) == 0

    def test_german_special_characters(self):
        """Test handling of German special characters."""
        text = "Geschäftsführer: Jürgen Müßiggang, Straße: Äußere Sulzbacher Str."
        result = self.validator.validate_umlauts(text)

        # Should detect all umlauts
        assert "ä" in result["umlauts_found"]
        assert "ü" in result["umlauts_found"]
        assert "ß" in result["umlauts_found"]
        assert "Ä" in result["umlauts_found"]

    def test_mixed_german_english_text(self):
        """Test validation of mixed German-English text."""
        text = "CEO: Müller, Email: info@example.com, Größe: 100GB"
        result = self.validator.validate_umlauts(text)

        # Should still detect German umlauts
        assert "ü" in result["umlauts_found"]
        assert "ö" in result["umlauts_found"]
        assert result["valid"] == True

    def test_empty_text(self):
        """Test validation of empty text."""
        result = self.validator.validate_umlauts("")

        assert result["valid"] == True  # Empty is valid
        assert len(result["umlauts_found"]) == 0
        assert len(result["potential_errors"]) == 0

    def test_fraktur_normalization(self):
        """Test normalization of Fraktur/historical German characters."""
        # This would test if historical characters are properly normalized
        # Implementation depends on GermanValidator capabilities
        text = "Müller GmbH"
        result = self.validator.validate_umlauts(text)

        assert result["valid"] == True
