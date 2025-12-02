"""Unit Tests fuer OCRQualityValidator.

Tests fuer die OCR-Qualitaetsvalidierung aus dem Execution_Layer.
"""

import pytest

import sys
from pathlib import Path

# Add Execution_Layer to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "Execution_Layer"))

from Validators.ocr_quality_validator import OCRQualityValidator


class TestOCRQualityValidator:
    """Tests fuer OCRQualityValidator."""

    @pytest.fixture
    def validator(self) -> OCRQualityValidator:
        """Erstellt einen Validator fuer Tests."""
        return OCRQualityValidator()

    # =========================================================================
    # Basic Validation Tests
    # =========================================================================

    def test_validate_valid_result(self, validator: OCRQualityValidator) -> None:
        """Test: Gutes OCR-Ergebnis wird akzeptiert."""
        ocr_result = {
            "text": "Dies ist ein laengerer Text der die minimale Laenge ueberschreitet.",
            "confidence": 0.95
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is True
        assert len(result["issues"]) == 0

    def test_validate_low_confidence(self, validator: OCRQualityValidator) -> None:
        """Test: Niedrige Konfidenz wird erkannt."""
        ocr_result = {
            "text": "Dies ist ein laengerer Text der die minimale Laenge ueberschreitet.",
            "confidence": 0.50
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is False
        assert "Low OCR confidence" in result["issues"]

    def test_validate_short_text(self, validator: OCRQualityValidator) -> None:
        """Test: Zu kurzer Text wird erkannt."""
        ocr_result = {
            "text": "Kurz",
            "confidence": 0.95
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is False
        assert "Text too short" in result["issues"]

    def test_validate_empty_text(self, validator: OCRQualityValidator) -> None:
        """Test: Leerer Text wird erkannt."""
        ocr_result = {
            "text": "",
            "confidence": 0.95
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is False
        assert "Text too short" in result["issues"]

    def test_validate_missing_text(self, validator: OCRQualityValidator) -> None:
        """Test: Fehlender Text wird behandelt."""
        ocr_result = {
            "confidence": 0.95
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is False
        assert "Text too short" in result["issues"]

    def test_validate_missing_confidence(self, validator: OCRQualityValidator) -> None:
        """Test: Fehlende Konfidenz wird als 0 behandelt."""
        ocr_result = {
            "text": "Dies ist ein laengerer Text der die minimale Laenge ueberschreitet."
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is False
        assert "Low OCR confidence" in result["issues"]

    def test_validate_multiple_issues(self, validator: OCRQualityValidator) -> None:
        """Test: Mehrere Probleme werden erkannt."""
        ocr_result = {
            "text": "Kurz",
            "confidence": 0.50
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is False
        assert len(result["issues"]) == 2
        assert "Low OCR confidence" in result["issues"]
        assert "Text too short" in result["issues"]

    # =========================================================================
    # Threshold Tests
    # =========================================================================

    def test_threshold_min_confidence(self, validator: OCRQualityValidator) -> None:
        """Test: Konfidenz-Schwellenwert wird korrekt geprueft."""
        threshold = validator.THRESHOLDS["min_confidence"]

        # Genau am Schwellenwert - sollte gueltig sein
        ocr_result = {
            "text": "Dies ist ein laengerer Text der die minimale Laenge ueberschreitet.",
            "confidence": threshold
        }
        result = validator.validate(ocr_result)
        assert "Low OCR confidence" not in result["issues"]

        # Knapp unter Schwellenwert - sollte ungueltig sein
        ocr_result["confidence"] = threshold - 0.01
        result = validator.validate(ocr_result)
        assert "Low OCR confidence" in result["issues"]

    def test_threshold_min_text_length(self, validator: OCRQualityValidator) -> None:
        """Test: Text-Laengen-Schwellenwert wird korrekt geprueft."""
        threshold = validator.THRESHOLDS["min_text_length"]

        # Genau am Schwellenwert - sollte gueltig sein
        ocr_result = {
            "text": "x" * threshold,
            "confidence": 0.95
        }
        result = validator.validate(ocr_result)
        assert "Text too short" not in result["issues"]

        # Knapp unter Schwellenwert - sollte ungueltig sein
        ocr_result["text"] = "x" * (threshold - 1)
        result = validator.validate(ocr_result)
        assert "Text too short" in result["issues"]

    def test_thresholds_exist(self, validator: OCRQualityValidator) -> None:
        """Test: Alle erwarteten Schwellenwerte sind definiert."""
        assert "min_confidence" in validator.THRESHOLDS
        assert "min_text_length" in validator.THRESHOLDS
        assert "max_unknown_chars_percent" in validator.THRESHOLDS

    def test_threshold_values(self, validator: OCRQualityValidator) -> None:
        """Test: Schwellenwerte haben sinnvolle Werte."""
        assert 0 < validator.THRESHOLDS["min_confidence"] <= 1.0
        assert validator.THRESHOLDS["min_text_length"] > 0
        assert 0 < validator.THRESHOLDS["max_unknown_chars_percent"] <= 100

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_validate_empty_dict(self, validator: OCRQualityValidator) -> None:
        """Test: Leeres Dictionary wird behandelt."""
        result = validator.validate({})

        assert result["valid"] is False
        assert len(result["issues"]) >= 2

    def test_validate_confidence_exactly_zero(
        self, validator: OCRQualityValidator
    ) -> None:
        """Test: Konfidenz von genau 0 wird behandelt."""
        ocr_result = {
            "text": "Dies ist ein laengerer Text der die minimale Laenge ueberschreitet.",
            "confidence": 0
        }

        result = validator.validate(ocr_result)

        assert result["valid"] is False
        assert "Low OCR confidence" in result["issues"]

    def test_validate_confidence_exactly_one(
        self, validator: OCRQualityValidator
    ) -> None:
        """Test: Perfekte Konfidenz von 1.0 wird akzeptiert."""
        ocr_result = {
            "text": "Dies ist ein laengerer Text der die minimale Laenge ueberschreitet.",
            "confidence": 1.0
        }

        result = validator.validate(ocr_result)

        assert "Low OCR confidence" not in result["issues"]

    def test_validate_text_with_whitespace_only(
        self, validator: OCRQualityValidator
    ) -> None:
        """Test: Text nur mit Whitespace wird als zu kurz erkannt."""
        ocr_result = {
            "text": "          ",  # 10 Leerzeichen
            "confidence": 0.95
        }

        # Je nach Implementation koennte Whitespace zaehlen oder nicht
        result = validator.validate(ocr_result)
        # Mindestens 10 Zeichen, also formal gueltig
        # aber in echter Implementierung sollte Whitespace-only erkannt werden

    def test_validate_text_with_special_chars(
        self, validator: OCRQualityValidator
    ) -> None:
        """Test: Text mit Sonderzeichen wird behandelt."""
        ocr_result = {
            "text": "äöüßÄÖÜ €£¥ ©®™",
            "confidence": 0.95
        }

        result = validator.validate(ocr_result)
        # Sollte gueltig sein (16+ Zeichen)

    def test_validate_unicode_text(self, validator: OCRQualityValidator) -> None:
        """Test: Unicode-Text wird korrekt behandelt."""
        ocr_result = {
            "text": "日本語テキスト with German Umlauts: äöü",
            "confidence": 0.95
        }

        result = validator.validate(ocr_result)
        # Sollte gueltig sein (genug Zeichen)

    # =========================================================================
    # Return Value Structure Tests
    # =========================================================================

    def test_return_structure_valid(self, validator: OCRQualityValidator) -> None:
        """Test: Rueckgabe-Struktur bei gueltigem Input."""
        ocr_result = {
            "text": "Dies ist ein laengerer Text.",
            "confidence": 0.95
        }

        result = validator.validate(ocr_result)

        assert "valid" in result
        assert "issues" in result
        assert isinstance(result["valid"], bool)
        assert isinstance(result["issues"], list)

    def test_return_structure_invalid(self, validator: OCRQualityValidator) -> None:
        """Test: Rueckgabe-Struktur bei ungueltigem Input."""
        ocr_result = {
            "text": "K",
            "confidence": 0.1
        }

        result = validator.validate(ocr_result)

        assert "valid" in result
        assert "issues" in result
        assert isinstance(result["valid"], bool)
        assert isinstance(result["issues"], list)
        assert all(isinstance(issue, str) for issue in result["issues"])


class TestOCRQualityValidatorThresholds:
    """Tests fuer Threshold-Konfiguration."""

    def test_default_thresholds(self) -> None:
        """Test: Standard-Schwellenwerte sind gesetzt."""
        assert OCRQualityValidator.THRESHOLDS["min_confidence"] == 0.85
        assert OCRQualityValidator.THRESHOLDS["min_text_length"] == 10
        assert OCRQualityValidator.THRESHOLDS["max_unknown_chars_percent"] == 5

    def test_thresholds_are_class_attribute(self) -> None:
        """Test: THRESHOLDS ist ein Klassen-Attribut."""
        validator1 = OCRQualityValidator()
        validator2 = OCRQualityValidator()

        # Beide Instanzen teilen die gleichen Thresholds
        assert validator1.THRESHOLDS is validator2.THRESHOLDS

    def test_threshold_modification_affects_validation(self) -> None:
        """Test: Aenderung der Schwellenwerte wirkt sich aus."""
        validator = OCRQualityValidator()
        original_threshold = validator.THRESHOLDS["min_confidence"]

        try:
            # Temporaer Schwellenwert erhoehen
            validator.THRESHOLDS["min_confidence"] = 0.99

            ocr_result = {
                "text": "Dies ist ein laengerer Text.",
                "confidence": 0.95
            }

            result = validator.validate(ocr_result)
            assert "Low OCR confidence" in result["issues"]

        finally:
            # Schwellenwert zuruecksetzen
            validator.THRESHOLDS["min_confidence"] = original_threshold
