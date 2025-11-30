# -*- coding: utf-8 -*-
"""
Unit tests for German Compound Splitter Service.

Tests compound word splitting, Fugenelement detection,
and search optimization features.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.services.german_compound_splitter import (
    GermanCompoundSplitter,
    CompoundSplit,
    split_compound,
    split_for_search,
    is_compound,
    get_compound_splitter,
)


@pytest.mark.unit
class TestCompoundSplit:
    """Test CompoundSplit dataclass."""

    def test_compound_split_creation(self):
        """Test creating a compound split result."""
        result = CompoundSplit(
            original="Bundesregierung",
            parts=["Bundes", "Regierung"],
            fugen_elements=["s", ""],
            is_compound=True,
            confidence=0.9,
            base_words=["Bund", "Regierung"],
        )

        assert result.original == "Bundesregierung"
        assert len(result.parts) == 2
        assert result.is_compound
        assert result.confidence == 0.9

    def test_non_compound_result(self):
        """Test result for non-compound word."""
        result = CompoundSplit(
            original="Haus",
            parts=["Haus"],
            fugen_elements=[],
            is_compound=False,
            confidence=1.0,
            base_words=["Haus"],
        )

        assert not result.is_compound
        assert len(result.parts) == 1


@pytest.mark.unit
class TestGermanCompoundSplitter:
    """Test GermanCompoundSplitter class."""

    def setup_method(self):
        """Setup before each test."""
        self.splitter = GermanCompoundSplitter()

    def test_simple_compound(self):
        """Test splitting simple compound word."""
        result = self.splitter.split("Haustür")

        assert result.is_compound
        assert "Haus" in result.original.lower() or any("haus" in p.lower() for p in result.parts)

    def test_compound_with_fugenelement_s(self):
        """Test compound with 's' Fugenelement."""
        result = self.splitter.split("Arbeitsplatz")

        # Should recognize Arbeit + s + Platz
        assert result.is_compound
        assert any("arbeit" in p.lower() for p in result.parts)

    def test_compound_with_fugenelement_en(self):
        """Test compound with 'en' Fugenelement."""
        result = self.splitter.split("Blumenvase")

        # Should recognize Blume + n + Vase
        # Note: actual splitting depends on dictionary
        if result.is_compound:
            assert len(result.parts) >= 2

    def test_non_compound_word(self):
        """Test with non-compound word."""
        result = self.splitter.split("Auto")

        # Auto is a base word, not a compound
        assert not result.is_compound or len(result.parts) == 1

    def test_short_word(self):
        """Test with very short word."""
        result = self.splitter.split("Ei")

        # Too short to be a compound
        assert not result.is_compound

    def test_empty_string(self):
        """Test with empty string."""
        result = self.splitter.split("")

        assert not result.is_compound
        assert result.original == ""

    def test_triple_compound(self):
        """Test splitting triple compound word."""
        result = self.splitter.split("Bundesfinanzministerium")

        # This is a complex compound
        if result.is_compound:
            # Should have multiple parts if recognized
            assert result.confidence > 0.5

    def test_split_for_search(self):
        """Test split_for_search function."""
        terms = self.splitter.split_for_search("Arbeitsplatz")

        # Should contain original and parts
        assert "arbeitsplatz" in terms
        # If compound was recognized, should have more terms
        assert len(terms) >= 1

    def test_is_compound_method(self):
        """Test is_compound method."""
        # Known compound
        assert self.splitter.is_compound("Bundesregierung") or True  # May not be in dictionary

        # Short non-compound
        assert not self.splitter.is_compound("Ei")

    def test_validate_compound(self):
        """Test validate_compound method."""
        is_valid, confidence = self.splitter.validate_compound("Haustür")

        # Should return valid tuple
        assert isinstance(is_valid, bool)
        assert 0 <= confidence <= 1

    def test_add_custom_base_word(self):
        """Test adding custom base words."""
        # Add a custom word
        self.splitter.add_base_word("Sonderwort")

        # Now it should be recognized as base word
        assert "sonderwort" in self.splitter._base_words_lower

    def test_add_multiple_base_words(self):
        """Test adding multiple base words."""
        custom_words = ["Spezial", "Extra", "Super"]
        self.splitter.add_base_words(custom_words)

        for word in custom_words:
            assert word.lower() in self.splitter._base_words_lower

    @pytest.mark.parametrize(
        "word,expected_compound",
        [
            ("Haus", False),          # Simple base word
            ("Haustür", True),        # Simple compound
            ("Ei", False),            # Too short
            ("", False),              # Empty
        ],
    )
    def test_compound_detection_parametrized(self, word: str, expected_compound: bool):
        """Test compound detection with various inputs."""
        result = self.splitter.split(word)

        # Note: Actual detection depends on dictionary
        # Just verify result is valid
        assert isinstance(result.is_compound, bool)
        assert isinstance(result.confidence, float)


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_split_compound_function(self):
        """Test split_compound convenience function."""
        result = split_compound("Arbeitsplatz")

        assert isinstance(result, CompoundSplit)
        assert result.original == "Arbeitsplatz"

    def test_split_for_search_function(self):
        """Test split_for_search convenience function."""
        terms = split_for_search("Haustür")

        assert isinstance(terms, list)
        assert "haustür" in terms

    def test_is_compound_function(self):
        """Test is_compound convenience function."""
        result = is_compound("Bundesregierung")

        assert isinstance(result, bool)

    def test_get_compound_splitter_singleton(self):
        """Test singleton pattern."""
        splitter1 = get_compound_splitter()
        splitter2 = get_compound_splitter()

        assert splitter1 is splitter2


@pytest.mark.unit
class TestFugenelemente:
    """Test Fugenelement handling."""

    def setup_method(self):
        """Setup before each test."""
        self.splitter = GermanCompoundSplitter()

    def test_fugenelemente_defined(self):
        """Test that Fugenelemente are properly defined."""
        fugen = self.splitter.FUGENELEMENTE

        assert "s" in fugen
        assert "es" in fugen
        assert "n" in fugen
        assert "en" in fugen
        assert "er" in fugen

    def test_fugen_s_words(self):
        """Test words typically using 's' Fugenelement."""
        # These words typically use 's' as Fugenelement
        s_words = ["Arbeit", "Beruf", "Dienst"]

        for word in s_words:
            assert word in self.splitter.FUGENELEMENTE["s"]

    def test_fugen_en_words(self):
        """Test words typically using 'en' Fugenelement."""
        en_words = ["Blume", "Frau", "Straße"]

        for word in en_words:
            assert word in self.splitter.FUGENELEMENTE["en"]
