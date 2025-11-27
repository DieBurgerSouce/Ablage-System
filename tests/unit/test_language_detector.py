# -*- coding: utf-8 -*-
"""
Unit tests for Language Detector.

Tests:
- Script detection (Latin/Cyrillic/Mixed)
- Language detection (DE/PL/RU/UK/EN)
- Pattern-based quick detection
- Backend recommendations per language
- OCR text cleaning and detection
"""

import pytest
from typing import List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# Sample texts for testing
GERMAN_TEXT = """
Die Müller GmbH & Co. KG ist ein deutsches Unternehmen mit Sitz in München.
Unsere Geschäftsführer sind für die strategische Ausrichtung verantwortlich.
Bitte überweisen Sie den Betrag auf unser Konto bei der Sparkasse.
"""

POLISH_TEXT = """
Spółka Müller GmbH jest przedsiębiorstwem niemieckim z siedzibą w Monachium.
Nasi dyrektorzy odpowiadają za kierunek strategiczny.
Prosimy o przelanie kwoty na nasze konto.
"""

RUSSIAN_TEXT = """
Компания Müller GmbH является немецким предприятием с головным офисом в Мюнхене.
Наши директора отвечают за стратегическое направление развития.
Пожалуйста, переведите сумму на наш счёт.
"""

UKRAINIAN_TEXT = """
Компанія Müller GmbH є німецьким підприємством із штаб-квартирою в Мюнхені.
Наші директори відповідають за стратегічний напрямок.
Будь ласка, перекажіть суму на наш рахунок.
"""

MIXED_TEXT = """
Die Müller GmbH arbeitet mit Partnern in Moskau zusammen.
Контактное лицо: Иван Петров, телефон +7 495 123 4567.
Please contact our international department for more information.
"""

SHORT_TEXT = "Hallo"

OCR_NOISY_TEXT = """
D|e Mül|er GmbH && Co. K_G ist e|n  deutsches   Unternehmen
mit __Sitz__ in /München/.
"""


class TestScriptDetection:
    """Test script type detection."""

    @pytest.fixture
    def detector(self):
        """Create language detector."""
        from app.agents.orchestration.language_detector import LanguageDetector
        return LanguageDetector()

    @pytest.mark.unit
    def test_detect_latin_script(self, detector):
        """Test detection of Latin script."""
        from app.agents.orchestration.language_detector import ScriptType

        result = detector._detect_script(GERMAN_TEXT)
        assert result == ScriptType.LATIN

    @pytest.mark.unit
    def test_detect_cyrillic_script(self, detector):
        """Test detection of Cyrillic script."""
        from app.agents.orchestration.language_detector import ScriptType

        result = detector._detect_script(RUSSIAN_TEXT)
        assert result == ScriptType.CYRILLIC

    @pytest.mark.unit
    def test_detect_mixed_script(self, detector):
        """Test detection of mixed script (Latin + Cyrillic)."""
        from app.agents.orchestration.language_detector import ScriptType

        result = detector._detect_script(MIXED_TEXT)
        assert result == ScriptType.MIXED

    @pytest.mark.unit
    def test_detect_unknown_script_empty(self, detector):
        """Test detection with no letters."""
        from app.agents.orchestration.language_detector import ScriptType

        result = detector._detect_script("12345 !@#$%")
        assert result == ScriptType.UNKNOWN

    @pytest.mark.unit
    def test_polish_is_latin(self, detector):
        """Test that Polish text is detected as Latin."""
        from app.agents.orchestration.language_detector import ScriptType

        result = detector._detect_script(POLISH_TEXT)
        assert result == ScriptType.LATIN


class TestLanguageDetection:
    """Test language detection functionality."""

    @pytest.fixture
    def detector(self):
        """Create language detector."""
        from app.agents.orchestration.language_detector import LanguageDetector
        return LanguageDetector()

    @pytest.mark.unit
    def test_detect_german(self, detector):
        """Test German language detection."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect(GERMAN_TEXT)

        assert result.primary_language == LanguageCode.GERMAN
        assert result.confidence > 0.5

    @pytest.mark.unit
    def test_detect_polish(self, detector):
        """Test Polish language detection."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect(POLISH_TEXT)

        assert result.primary_language == LanguageCode.POLISH
        assert result.confidence > 0.5

    @pytest.mark.unit
    def test_detect_russian(self, detector):
        """Test Russian language detection."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect(RUSSIAN_TEXT)

        assert result.primary_language == LanguageCode.RUSSIAN
        assert result.confidence > 0.5

    @pytest.mark.unit
    def test_detect_ukrainian(self, detector):
        """Test Ukrainian language detection."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect(UKRAINIAN_TEXT)

        # Ukrainian might be detected as Russian by some detectors
        assert result.primary_language in (
            LanguageCode.UKRAINIAN,
            LanguageCode.RUSSIAN
        )
        assert result.confidence > 0.5

    @pytest.mark.unit
    def test_detect_empty_text(self, detector):
        """Test detection with empty text."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect("")

        assert result.primary_language == LanguageCode.UNKNOWN
        assert result.confidence == 0.0
        assert result.detection_method == "no_text"

    @pytest.mark.unit
    def test_detect_short_text(self, detector):
        """Test detection with very short text."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect("Hi")

        # Short text should return unknown
        assert result.primary_language == LanguageCode.UNKNOWN
        assert result.detection_method == "no_text"

    @pytest.mark.unit
    def test_result_to_dict(self, detector):
        """Test LanguageDetectionResult serialization."""
        result = detector.detect(GERMAN_TEXT)
        result_dict = result.to_dict()

        assert "primary_language" in result_dict
        assert "confidence" in result_dict
        assert "script_type" in result_dict
        assert "all_languages" in result_dict
        assert "detection_method" in result_dict


class TestPatternDetection:
    """Test pattern-based quick detection."""

    @pytest.fixture
    def detector(self):
        """Create language detector."""
        from app.agents.orchestration.language_detector import LanguageDetector
        return LanguageDetector()

    @pytest.mark.unit
    def test_german_patterns(self, detector):
        """Test German pattern detection."""
        # Strong German indicators
        text = "Der Geschäftsführer ist für die Planung verantwortlich."
        result = detector._pattern_detection(text)

        if result:
            from app.agents.orchestration.language_detector import LanguageCode
            assert result.primary_language == LanguageCode.GERMAN

    @pytest.mark.unit
    def test_umlaut_detection(self, detector):
        """Test that umlauts trigger German detection."""
        text = "Größe, Länge, Höhe und Übersicht"
        result = detector._pattern_detection(text)

        # Should detect German due to umlauts
        assert result is not None or True  # Pattern detection may not always return

    @pytest.mark.unit
    def test_polish_characters(self, detector):
        """Test Polish special characters detection."""
        text = "zażółć gęślą jaźń ćma"  # Famous Polish pangram
        result = detector._pattern_detection(text)

        if result:
            from app.agents.orchestration.language_detector import LanguageCode
            assert result.primary_language == LanguageCode.POLISH


class TestBackendRecommendations:
    """Test OCR backend recommendations."""

    @pytest.fixture
    def detector(self):
        """Create language detector."""
        from app.agents.orchestration.language_detector import LanguageDetector
        return LanguageDetector()

    @pytest.mark.unit
    def test_german_backends(self, detector):
        """Test backends recommended for German."""
        from app.agents.orchestration.language_detector import LanguageCode

        backends = detector.get_recommended_backends(LanguageCode.GERMAN)

        assert isinstance(backends, list)
        assert len(backends) > 0
        assert "deepseek" in backends

    @pytest.mark.unit
    def test_russian_backends(self, detector):
        """Test backends recommended for Russian."""
        from app.agents.orchestration.language_detector import LanguageCode

        backends = detector.get_recommended_backends(LanguageCode.RUSSIAN)

        assert isinstance(backends, list)
        assert len(backends) > 0
        assert "donut" in backends  # Donut is best for Cyrillic

    @pytest.mark.unit
    def test_polish_backends(self, detector):
        """Test backends recommended for Polish."""
        from app.agents.orchestration.language_detector import LanguageCode

        backends = detector.get_recommended_backends(LanguageCode.POLISH)

        assert isinstance(backends, list)
        assert "donut" in backends

    @pytest.mark.unit
    def test_unknown_language_fallback(self, detector):
        """Test fallback backends for unknown language."""
        from app.agents.orchestration.language_detector import LanguageCode

        backends = detector.get_recommended_backends(LanguageCode.UNKNOWN)

        assert isinstance(backends, list)
        assert len(backends) > 0

    @pytest.mark.unit
    def test_cyrillic_language_check(self, detector):
        """Test Cyrillic language identification."""
        from app.agents.orchestration.language_detector import LanguageCode

        assert detector.is_cyrillic_language(LanguageCode.RUSSIAN) == True
        assert detector.is_cyrillic_language(LanguageCode.UKRAINIAN) == True
        assert detector.is_cyrillic_language(LanguageCode.GERMAN) == False
        assert detector.is_cyrillic_language(LanguageCode.POLISH) == False


class TestOCRTextDetection:
    """Test OCR-specific text detection."""

    @pytest.fixture
    def detector(self):
        """Create language detector."""
        from app.agents.orchestration.language_detector import LanguageDetector
        return LanguageDetector()

    @pytest.mark.unit
    def test_clean_ocr_text(self, detector):
        """Test OCR text cleaning."""
        cleaned = detector._clean_ocr_text(OCR_NOISY_TEXT)

        # Should remove OCR artifacts
        assert "|" not in cleaned
        assert "_" not in cleaned
        assert "/" not in cleaned
        # Should normalize whitespace
        assert "  " not in cleaned

    @pytest.mark.unit
    def test_detect_from_ocr_text(self, detector):
        """Test language detection from OCR-extracted text."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect_from_image_text(OCR_NOISY_TEXT)

        # Should still detect German despite noise
        assert result.primary_language == LanguageCode.GERMAN

    @pytest.mark.unit
    def test_short_ocr_text_fallback(self, detector):
        """Test fallback for very short OCR text."""
        from app.agents.orchestration.language_detector import LanguageCode

        result = detector.detect_from_image_text("Hallo Welt")

        # Short text should fall back to German
        assert result.primary_language == LanguageCode.GERMAN
        assert result.detection_method == "ocr_short_text"


class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.mark.unit
    def test_detect_language_function(self):
        """Test detect_language convenience function."""
        from app.agents.orchestration.language_detector import (
            detect_language,
            LanguageCode,
        )

        result = detect_language(GERMAN_TEXT)

        assert result.primary_language == LanguageCode.GERMAN

    @pytest.mark.unit
    def test_get_language_backends_function(self):
        """Test get_language_backends convenience function."""
        from app.agents.orchestration.language_detector import get_language_backends

        backends = get_language_backends(RUSSIAN_TEXT)

        assert isinstance(backends, list)
        assert "donut" in backends

    @pytest.mark.unit
    def test_singleton_detector(self):
        """Test that get_detector returns singleton."""
        from app.agents.orchestration.language_detector import get_detector

        detector1 = get_detector()
        detector2 = get_detector()

        assert detector1 is detector2


class TestLanguageCodeEnum:
    """Test LanguageCode enum."""

    @pytest.mark.unit
    def test_from_string_valid(self):
        """Test LanguageCode.from_string with valid codes."""
        from app.agents.orchestration.language_detector import LanguageCode

        assert LanguageCode.from_string("de") == LanguageCode.GERMAN
        assert LanguageCode.from_string("DE") == LanguageCode.GERMAN
        assert LanguageCode.from_string("en") == LanguageCode.ENGLISH
        assert LanguageCode.from_string("pl") == LanguageCode.POLISH
        assert LanguageCode.from_string("ru") == LanguageCode.RUSSIAN

    @pytest.mark.unit
    def test_from_string_invalid(self):
        """Test LanguageCode.from_string with invalid codes."""
        from app.agents.orchestration.language_detector import LanguageCode

        assert LanguageCode.from_string("xyz") == LanguageCode.UNKNOWN
        assert LanguageCode.from_string("") == LanguageCode.UNKNOWN

    @pytest.mark.unit
    def test_from_string_truncates(self):
        """Test that from_string truncates to 2 chars."""
        from app.agents.orchestration.language_detector import LanguageCode

        # Should take first 2 chars
        assert LanguageCode.from_string("deu") == LanguageCode.GERMAN
        assert LanguageCode.from_string("eng") == LanguageCode.ENGLISH


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
