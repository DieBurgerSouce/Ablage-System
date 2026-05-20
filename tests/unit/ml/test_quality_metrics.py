# -*- coding: utf-8 -*-
"""
Unit tests for OCR Quality Metrics Module.

Tests CER/WER calculation, Levenshtein distance,
umlaut accuracy, and capitalization accuracy.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.ml.quality_metrics import (
    OCRQualityCalculator,
    OCRQualityMetrics,
    LevenshteinResult,
    UmlautAnalysis,
    calculate_cer,
    calculate_wer,
    calculate_quality_metrics,
    analyze_umlaut_accuracy,
)


@pytest.mark.unit
class TestLevenshteinDistance:
    """Test Levenshtein distance calculations."""

    def setup_method(self):
        """Setup before each test."""
        self.calculator = OCRQualityCalculator()

    def test_identical_strings(self):
        """Test distance between identical strings."""
        result = self.calculator.levenshtein_distance("hello", "hello")

        assert result.distance == 0
        assert result.insertions == 0
        assert result.deletions == 0
        assert result.substitutions == 0

    def test_single_substitution(self):
        """Test single character substitution."""
        result = self.calculator.levenshtein_distance("hello", "hallo")

        assert result.distance == 1
        assert result.substitutions == 1

    def test_single_insertion(self):
        """Test single character insertion."""
        result = self.calculator.levenshtein_distance("hello", "helllo")

        assert result.distance == 1

    def test_single_deletion(self):
        """Test single character deletion."""
        result = self.calculator.levenshtein_distance("hello", "helo")

        assert result.distance == 1

    def test_empty_strings(self):
        """Test with empty strings."""
        result = self.calculator.levenshtein_distance("", "")
        assert result.distance == 0

        result = self.calculator.levenshtein_distance("hello", "")
        assert result.distance == 5

        result = self.calculator.levenshtein_distance("", "world")
        assert result.distance == 5

    def test_german_umlauts(self):
        """Test with German umlauts."""
        result = self.calculator.levenshtein_distance("Müller", "Mueller")

        # ü -> ue = 1 substitution + 1 insertion or similar
        assert result.distance >= 1

    def test_complex_string(self):
        """Test with longer complex string."""
        reference = "Die Rechnung vom 15. Januar 2024"
        hypothesis = "Die Rechung vom 15 Januar 2024"  # Missing 'n' and '.'

        result = self.calculator.levenshtein_distance(reference, hypothesis)

        assert result.distance == 2


@pytest.mark.unit
class TestCERCalculation:
    """Test Character Error Rate calculation."""

    def setup_method(self):
        """Setup before each test."""
        self.calculator = OCRQualityCalculator()

    def test_perfect_match(self):
        """Test CER for perfect match."""
        cer = calculate_cer("Test", "Test")
        assert cer == 0.0

    def test_complete_mismatch(self):
        """Test CER for completely different strings."""
        cer = calculate_cer("abc", "xyz")
        assert cer == 1.0  # All characters wrong

    def test_partial_error(self):
        """Test CER for partial error."""
        cer = calculate_cer("hello", "hallo")
        # 1 substitution / 5 chars = 0.2
        assert 0.15 <= cer <= 0.25

    def test_empty_reference(self):
        """Test CER with empty reference."""
        cer = calculate_cer("", "text")
        assert cer == 1.0  # Convention: 100% error

    def test_german_text(self):
        """Test CER with German text."""
        reference = "Größe: 42cm"
        hypothesis = "Groesse: 42cm"  # ö -> oe

        cer = calculate_cer(reference, hypothesis)

        # Should have some error due to umlaut conversion
        assert cer > 0


@pytest.mark.unit
class TestWERCalculation:
    """Test Word Error Rate calculation."""

    def setup_method(self):
        """Setup before each test."""
        self.calculator = OCRQualityCalculator()

    def test_perfect_match(self):
        """Test WER for perfect match."""
        wer = calculate_wer("Hello World", "Hello World")
        assert wer == 0.0

    def test_single_word_error(self):
        """Test WER with single word error."""
        wer = calculate_wer("Hello World", "Hello Warld")
        # 1 wrong word / 2 words = 0.5
        assert 0.4 <= wer <= 0.6

    def test_missing_word(self):
        """Test WER with missing word."""
        wer = calculate_wer("Hello World Test", "Hello World")
        # 1 deletion / 3 words ≈ 0.33
        assert 0.25 <= wer <= 0.4

    def test_extra_word(self):
        """Test WER with extra word."""
        wer = calculate_wer("Hello World", "Hello World Extra")
        # 1 insertion / 2 words = 0.5
        assert 0.4 <= wer <= 0.6

    def test_german_business_text(self):
        """Test WER with German business text."""
        reference = "Müller GmbH Rechnung"
        hypothesis = "Mueller GmbH Rechung"

        wer = calculate_wer(reference, hypothesis)

        # 2 wrong words / 3 words ≈ 0.67
        assert wer > 0.5


@pytest.mark.unit
class TestUmlautAnalysis:
    """Test umlaut accuracy analysis."""

    def setup_method(self):
        """Setup before each test."""
        self.calculator = OCRQualityCalculator()

    def test_perfect_umlaut_match(self):
        """Test perfect umlaut recognition."""
        reference = "Müller über größte"
        hypothesis = "Müller über größte"

        analysis = analyze_umlaut_accuracy(reference, hypothesis)

        assert analysis.accuracy == 1.0
        assert analysis.total_umlauts > 0

    def test_missed_umlauts(self):
        """Test missed umlaut detection."""
        reference = "Müller über größte"
        hypothesis = "Mueller uber grosste"

        analysis = analyze_umlaut_accuracy(reference, hypothesis)

        assert analysis.accuracy < 1.0
        assert len(analysis.missed_umlauts) > 0  # missed_umlauts is a list

    def test_no_umlauts(self):
        """Test text without umlauts."""
        reference = "Hello World"
        hypothesis = "Hello World"

        analysis = analyze_umlaut_accuracy(reference, hypothesis)

        assert analysis.accuracy == 1.0  # No umlauts to miss
        assert analysis.total_umlauts == 0

    def test_all_german_umlauts(self):
        """Test all German umlauts and eszett."""
        reference = "ä ö ü Ä Ö Ü ß"
        hypothesis = "ä ö ü Ä Ö Ü ß"

        analysis = analyze_umlaut_accuracy(reference, hypothesis)

        assert analysis.accuracy == 1.0
        assert analysis.total_umlauts == 7


@pytest.mark.unit
class TestFullQualityMetrics:
    """Test complete quality metrics calculation."""

    def test_calculate_quality_metrics(self):
        """Test comprehensive quality metrics."""
        reference = "Müller GmbH Rechnung"
        hypothesis = "Müller GmbH Rechnung"

        metrics = calculate_quality_metrics(reference, hypothesis)

        assert isinstance(metrics, OCRQualityMetrics)
        assert metrics.cer == 0.0
        assert metrics.wer == 0.0
        assert metrics.char_accuracy == 1.0
        assert metrics.word_accuracy == 1.0
        assert metrics.umlaut_accuracy == 1.0

    def test_metrics_with_errors(self):
        """Test metrics with OCR errors."""
        reference = "Größe der Bücher"
        hypothesis = "Groesse der Buecher"

        metrics = calculate_quality_metrics(reference, hypothesis)

        assert metrics.cer > 0
        assert metrics.wer > 0
        assert metrics.umlaut_accuracy < 1.0

    @pytest.mark.parametrize(
        "reference,hypothesis,expected_cer_range",
        [
            ("Test", "Test", (0.0, 0.0)),
            ("Test", "Tast", (0.2, 0.3)),
            ("Hello", "Helo", (0.15, 0.25)),
            # "Größe" (5 chars) -> "Groesse" (7 chars): High CER due to umlaut+eszett replacement
            ("Größe", "Groesse", (0.6, 1.0)),
        ],
    )
    def test_parametrized_cer(self, reference, hypothesis, expected_cer_range):
        """Test CER with various inputs."""
        metrics = calculate_quality_metrics(reference, hypothesis)

        assert expected_cer_range[0] <= metrics.cer <= expected_cer_range[1]
