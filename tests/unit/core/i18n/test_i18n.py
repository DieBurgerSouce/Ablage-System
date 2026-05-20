# -*- coding: utf-8 -*-
"""
Tests for i18n Module

Tests:
- Translation function with interpolation
- Language detection from Accept-Language header
- Thread-safe language context
- Fallback behavior
"""

import pytest
from unittest.mock import MagicMock, patch

from app.core.i18n import (
    t,
    tn,
    get_language,
    set_language,
    get_available_languages,
    detect_language_from_header,
    TranslationContext,
    SUPPORTED_LANGUAGES,
    DEFAULT_LANGUAGE,
    FALLBACK_LANGUAGE,
)


class TestTranslationFunction:
    """Tests for the t() translation function."""

    def setup_method(self) -> None:
        """Reset language to default before each test."""
        set_language(DEFAULT_LANGUAGE)

    def test_translate_german(self) -> None:
        """Test German translation."""
        set_language("de")
        assert t("document.not_found") == "Dokument nicht gefunden"

    def test_translate_english(self) -> None:
        """Test English translation."""
        set_language("en")
        assert t("document.not_found") == "Document not found"

    def test_translate_with_interpolation(self) -> None:
        """Test translation with interpolation values."""
        set_language("de")
        result = t("document.page_count", count=5)
        assert result == "5 Seiten"

        set_language("en")
        result = t("document.page_count", count=5)
        assert result == "5 pages"

    def test_translate_with_float_interpolation(self) -> None:
        """Test translation with float interpolation."""
        set_language("de")
        result = t("document.file_too_large", size_mb=25.5, max_mb=50.0)
        assert "25.5MB" in result
        assert "50.0MB" in result

    def test_fallback_to_german(self) -> None:
        """Test fallback to German for missing translations."""
        set_language("en")
        # If English translation doesn't exist, should fall back to German
        # This tests the fallback mechanism
        result = t("common.success")
        assert result in ["Success", "Erfolgreich"]  # Either is valid

    def test_missing_key_returns_key(self) -> None:
        """Test that missing keys return the key itself."""
        result = t("nonexistent.key.here")
        assert result == "nonexistent.key.here"

    def test_translate_namespace_function(self) -> None:
        """Test the tn() function with explicit namespace."""
        set_language("de")
        result = tn("document", "not_found")
        assert result == "Dokument nicht gefunden"


class TestLanguageDetection:
    """Tests for Accept-Language header parsing."""

    def test_detect_german(self) -> None:
        """Test detection of German language."""
        assert detect_language_from_header("de-DE,de;q=0.9,en;q=0.8") == "de"
        assert detect_language_from_header("de") == "de"
        assert detect_language_from_header("de-AT") == "de"

    def test_detect_english(self) -> None:
        """Test detection of English language."""
        assert detect_language_from_header("en-US,en;q=0.9") == "en"
        assert detect_language_from_header("en") == "en"
        assert detect_language_from_header("en-GB,en;q=0.9") == "en"

    def test_detect_with_quality_values(self) -> None:
        """Test detection respects quality values."""
        # English has higher quality, should return English
        assert detect_language_from_header("de;q=0.5,en;q=0.9") == "en"
        # German has higher quality, should return German
        assert detect_language_from_header("de;q=0.9,en;q=0.5") == "de"

    def test_detect_unsupported_language(self) -> None:
        """Test fallback for unsupported languages."""
        assert detect_language_from_header("fr-FR,fr;q=0.9") == DEFAULT_LANGUAGE
        assert detect_language_from_header("ja,zh;q=0.9") == DEFAULT_LANGUAGE

    def test_detect_empty_header(self) -> None:
        """Test handling of empty header."""
        assert detect_language_from_header("") == DEFAULT_LANGUAGE
        assert detect_language_from_header(None) == DEFAULT_LANGUAGE

    def test_detect_complex_header(self) -> None:
        """Test parsing of complex Accept-Language header."""
        header = "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7,fr;q=0.5"
        assert detect_language_from_header(header) == "de"

    def test_detect_mixed_supported_unsupported(self) -> None:
        """Test with mix of supported and unsupported languages."""
        # French first (unsupported), then German
        assert detect_language_from_header("fr;q=1.0,de;q=0.9") == "de"


class TestLanguageContext:
    """Tests for language context management."""

    def setup_method(self) -> None:
        """Reset language to default before each test."""
        set_language(DEFAULT_LANGUAGE)

    def test_set_get_language(self) -> None:
        """Test setting and getting language."""
        set_language("de")
        assert get_language() == "de"

        set_language("en")
        assert get_language() == "en"

    def test_set_unsupported_language(self) -> None:
        """Test that unsupported languages fall back to default."""
        set_language("fr")
        assert get_language() == DEFAULT_LANGUAGE

    def test_translation_context_manager(self) -> None:
        """Test TranslationContext context manager."""
        set_language("de")

        with TranslationContext("en"):
            assert get_language() == "en"
            assert t("document.not_found") == "Document not found"

        # Should restore previous language
        assert get_language() == "de"

    def test_nested_context_managers(self) -> None:
        """Test nested TranslationContext managers."""
        set_language("de")

        with TranslationContext("en"):
            assert get_language() == "en"

            with TranslationContext("de"):
                assert get_language() == "de"

            assert get_language() == "en"

        assert get_language() == "de"

    def test_get_available_languages(self) -> None:
        """Test getting list of available languages."""
        languages = get_available_languages()
        assert "de" in languages
        assert "en" in languages
        assert len(languages) == len(SUPPORTED_LANGUAGES)


class TestConstants:
    """Tests for i18n constants."""

    def test_supported_languages(self) -> None:
        """Test supported languages constant."""
        assert "de" in SUPPORTED_LANGUAGES
        assert "en" in SUPPORTED_LANGUAGES

    def test_default_language(self) -> None:
        """Test default language is German."""
        assert DEFAULT_LANGUAGE == "de"

    def test_fallback_language(self) -> None:
        """Test fallback language is German."""
        assert FALLBACK_LANGUAGE == "de"


class TestGermanSpecificTranslations:
    """Tests for German-specific translations with umlauts."""

    def setup_method(self) -> None:
        """Set language to German."""
        set_language("de")

    def test_umlaut_preservation(self) -> None:
        """Test that umlauts are preserved in translations."""
        result = t("auth.password_changed")
        # Should contain German umlaut characters (represented as ae, oe, ue in the catalog)
        # Note: The catalog uses "ae" instead of "ä" for safety
        assert "geaendert" in result or "geändert" in result

    def test_german_error_messages(self) -> None:
        """Test German error messages."""
        assert t("error.forbidden") == "Zugriff verweigert"
        assert t("error.not_found") == "Nicht gefunden"


class TestErrorHandling:
    """Tests for error handling in translations."""

    def setup_method(self) -> None:
        """Reset language to default."""
        set_language(DEFAULT_LANGUAGE)

    def test_missing_interpolation_value(self) -> None:
        """Test handling of missing interpolation values."""
        # Should not raise, should return string with placeholder
        result = t("document.page_count")  # Missing 'count'
        # The function should handle this gracefully
        assert isinstance(result, str)

    def test_extra_interpolation_values(self) -> None:
        """Test that extra interpolation values are ignored."""
        result = t("document.not_found", extra_param="ignored")
        assert result == "Dokument nicht gefunden"
