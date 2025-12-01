# -*- coding: utf-8 -*-
"""
Unit Tests für Token Error Analyzer.

Tests für OCR Token-Level Error Analysis:
- Fehleridentifikation
- Muster-Erkennung
- Empfehlungsgenerierung
- Berichtformatierung
"""

import pytest
from unittest.mock import MagicMock

from app.services.token_error_analyzer import (
    TokenErrorAnalyzer,
    TokenError,
    ErrorPattern,
    ErrorAnalysisResult,
    get_token_error_analyzer,
    analyze_ocr_tokens,
)


class TestTokenErrorAnalyzerInit:
    """Tests für Analyzer Initialisierung."""

    def test_init_default_settings(self):
        """Standardeinstellungen sollten korrekt gesetzt werden."""
        analyzer = TokenErrorAnalyzer()

        assert analyzer.low_confidence_threshold == 0.7
        assert analyzer.context_window == 5

    def test_init_custom_settings(self):
        """Benutzerdefinierte Einstellungen sollten akzeptiert werden."""
        analyzer = TokenErrorAnalyzer(
            low_confidence_threshold=0.8,
            context_window=10
        )

        assert analyzer.low_confidence_threshold == 0.8
        assert analyzer.context_window == 10


class TestAnalyze:
    """Tests für die analyze Methode."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_analyze_empty_result(self, analyzer):
        """Leeres OCR-Ergebnis sollte valides Result liefern."""
        result = analyzer.analyze({})

        assert isinstance(result, ErrorAnalysisResult)
        assert result.total_tokens == 0
        assert result.error_count == 0
        assert result.severity == "low"

    def test_analyze_with_text_only(self, analyzer):
        """Text ohne Confidence-Daten sollte verarbeitet werden."""
        ocr_result = {"text": "Dies ist ein Test."}

        result = analyzer.analyze(ocr_result)

        assert result.total_tokens == 0  # Keine Token-Confidences
        assert len(result.recommendations) > 0

    def test_analyze_with_confidence_data(self, analyzer):
        """OCR-Ergebnis mit Confidence-Daten sollte analysiert werden."""
        ocr_result = {
            "text": "Dies ist ein Test mit niedrigem Vertrauen.",
            "confidence_data": {
                "mean_confidence": 0.75,
                "min_confidence": 0.4,
                "total_tokens": 8,
                "token_confidences": [0.9, 0.8, 0.7, 0.4, 0.5, 0.6, 0.7, 0.8],
                "low_confidence_positions": [
                    {"position": 15, "confidence": 0.4},
                    {"position": 20, "confidence": 0.5},
                    {"position": 25, "confidence": 0.6},
                ]
            }
        }

        result = analyzer.analyze(ocr_result)

        assert result.total_tokens == 8
        assert result.mean_confidence == 0.75
        assert result.min_confidence == 0.4
        assert len(result.errors) >= 3  # Mindestens die low_conf_positions

    def test_analyze_returns_correct_structure(self, analyzer):
        """Analyse sollte alle erwarteten Felder enthalten."""
        result = analyzer.analyze({"text": "Test"})

        assert hasattr(result, 'total_tokens')
        assert hasattr(result, 'error_count')
        assert hasattr(result, 'error_rate')
        assert hasattr(result, 'mean_confidence')
        assert hasattr(result, 'min_confidence')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'patterns')
        assert hasattr(result, 'word_errors')
        assert hasattr(result, 'recommendations')
        assert hasattr(result, 'severity')


class TestIdentifyErrors:
    """Tests für Fehleridentifikation."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_identify_low_confidence_errors(self, analyzer):
        """Niedrige Confidence sollte als Fehler erkannt werden."""
        errors = analyzer._identify_errors(
            text="Das ist ein Test.",
            token_confidences=[0.9, 0.3, 0.8, 0.7],
            low_conf_positions=[{"position": 4, "confidence": 0.3}]
        )

        assert len(errors) >= 1
        assert any(e.confidence == 0.3 for e in errors)

    def test_identify_known_ocr_errors(self, analyzer):
        """Bekannte OCR-Fehler sollten erkannt werden."""
        text = "Dies ist teh Test mit rnit Fehler."

        errors = analyzer._find_pattern_errors(text)

        assert len(errors) >= 1

    def test_errors_sorted_by_position(self, analyzer):
        """Fehler sollten nach Position sortiert sein."""
        errors = analyzer._identify_errors(
            text="Eins zwei drei vier fünf.",
            token_confidences=[0.9, 0.5, 0.9, 0.4, 0.9],
            low_conf_positions=[
                {"position": 15, "confidence": 0.4},
                {"position": 5, "confidence": 0.5},
            ]
        )

        positions = [e.position for e in errors]
        assert positions == sorted(positions)


class TestFindWordAtPosition:
    """Tests für Wort-Positions-Mapping."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_find_word_at_start(self, analyzer):
        """Wort am Anfang sollte gefunden werden."""
        word, idx = analyzer._find_word_at_position("Hello World", 0)
        assert word == "Hello"
        assert idx == 0

    def test_find_word_in_middle(self, analyzer):
        """Wort in der Mitte sollte gefunden werden."""
        word, idx = analyzer._find_word_at_position("Hello World Test", 6)
        assert word == "World"
        assert idx == 1

    def test_find_word_at_end(self, analyzer):
        """Wort am Ende sollte gefunden werden."""
        word, idx = analyzer._find_word_at_position("Hello World", 10)
        assert word == "World"
        assert idx == 1

    def test_find_word_empty_string(self, analyzer):
        """Leerer String sollte leeres Wort ergeben."""
        word, idx = analyzer._find_word_at_position("", 0)
        assert word == ""
        assert idx == -1

    def test_find_word_negative_position(self, analyzer):
        """Negative Position sollte leeres Wort ergeben."""
        word, idx = analyzer._find_word_at_position("Hello", -5)
        assert word == ""
        assert idx == -1


class TestClassifyErrorType:
    """Tests für Fehlertyp-Klassifizierung."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_critical_confidence(self, analyzer):
        """Sehr niedrige Confidence sollte kritisch sein."""
        error_type = analyzer._classify_error_type("word", 0.2)
        assert error_type == "critical_confidence"

    def test_very_low_confidence(self, analyzer):
        """Niedrige Confidence sollte very_low sein."""
        error_type = analyzer._classify_error_type("word", 0.4)
        assert error_type == "very_low_confidence"

    def test_low_confidence(self, analyzer):
        """Moderate niedrige Confidence sollte low sein."""
        error_type = analyzer._classify_error_type("word", 0.6)
        assert error_type == "low_confidence"

    def test_character_confusion(self, analyzer):
        """Zeichen-Verwechslung sollte erkannt werden."""
        error_type = analyzer._classify_error_type("O0l1", 0.8)
        assert error_type == "character_confusion"

    def test_umlaut_suspect(self, analyzer):
        """Umlaut-Verdacht sollte erkannt werden."""
        error_type = analyzer._classify_error_type("fuer", 0.8)
        assert error_type == "umlaut_suspect"

    def test_eszett_suspect(self, analyzer):
        """Eszett-Verdacht sollte erkannt werden."""
        error_type = analyzer._classify_error_type("strasse", 0.8)
        assert error_type == "eszett_suspect"


class TestSuggestCorrection:
    """Tests für Korrekturvorschläge."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_suggest_known_error(self, analyzer):
        """Bekannte Fehler sollten Vorschläge haben."""
        suggestion = analyzer._suggest_correction("GrnbH")
        assert suggestion == "GmbH"

    def test_suggest_umlaut_correction(self, analyzer):
        """Umlaute sollten vorgeschlagen werden."""
        suggestion = analyzer._suggest_correction("fuer")
        assert suggestion == "für"

    def test_suggest_multiple_umlauts(self, analyzer):
        """Mehrere Umlaute sollten korrigiert werden."""
        suggestion = analyzer._suggest_correction("Ueberpruefer")
        assert suggestion == "Überprüfer"

    def test_no_suggestion_for_correct_word(self, analyzer):
        """Korrekte Wörter sollten keine Vorschläge haben."""
        suggestion = analyzer._suggest_correction("Hallo")
        assert suggestion is None


class TestDetectErrorPatterns:
    """Tests für Muster-Erkennung."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_detect_patterns_from_errors(self, analyzer):
        """Muster sollten aus Fehlern erkannt werden."""
        errors = [
            TokenError(0, "word1", 0.5, "", "low_confidence", None),
            TokenError(5, "word2", 0.4, "", "low_confidence", None),
            TokenError(10, "word3", 0.6, "", "umlaut_suspect", None),
        ]

        patterns = analyzer._detect_error_patterns("test text", errors)

        assert len(patterns) > 0
        # low_confidence sollte 2x vorkommen
        low_conf_pattern = next((p for p in patterns if p.pattern == "low_confidence"), None)
        assert low_conf_pattern is not None
        assert low_conf_pattern.frequency == 2

    def test_patterns_sorted_by_frequency(self, analyzer):
        """Muster sollten nach Häufigkeit sortiert sein."""
        errors = [
            TokenError(0, "w1", 0.5, "", "type_a", None),
            TokenError(5, "w2", 0.5, "", "type_b", None),
            TokenError(10, "w3", 0.5, "", "type_a", None),
            TokenError(15, "w4", 0.5, "", "type_a", None),
        ]

        patterns = analyzer._detect_error_patterns("", errors)

        frequencies = [p.frequency for p in patterns]
        assert frequencies == sorted(frequencies, reverse=True)


class TestGenerateRecommendations:
    """Tests für Empfehlungsgenerierung."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_low_confidence_recommendation(self, analyzer):
        """Niedrige Confidence sollte Empfehlung generieren."""
        recommendations = analyzer._generate_recommendations(
            errors=[],
            patterns=[],
            mean_confidence=0.5
        )

        assert any("Niedrige" in r for r in recommendations)

    def test_umlaut_pattern_recommendation(self, analyzer):
        """Umlaut-Muster sollten Empfehlung generieren."""
        patterns = [ErrorPattern("ae/ä OCR-Problem", 5, ["fuer", "ueber"])]

        recommendations = analyzer._generate_recommendations(
            errors=[],
            patterns=patterns,
            mean_confidence=0.9
        )

        assert any("Umlaut" in r for r in recommendations)

    def test_many_errors_recommendation(self, analyzer):
        """Viele Fehler sollten Empfehlung generieren."""
        errors = [TokenError(i, f"word{i}", 0.5, "", "low", None) for i in range(25)]

        recommendations = analyzer._generate_recommendations(
            errors=errors,
            patterns=[],
            mean_confidence=0.9
        )

        assert any("Viele Fehler" in r for r in recommendations)

    def test_no_issues_recommendation(self, analyzer):
        """Ohne Probleme sollte positive Empfehlung kommen."""
        recommendations = analyzer._generate_recommendations(
            errors=[],
            patterns=[],
            mean_confidence=0.95
        )

        assert any("Keine signifikanten" in r for r in recommendations)


class TestCalculateSeverity:
    """Tests für Schweregrad-Berechnung."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_critical_severity(self, analyzer):
        """Kritischer Schweregrad sollte erkannt werden."""
        severity = analyzer._calculate_severity(
            error_count=30,
            total_tokens=100,
            min_confidence=0.2
        )
        assert severity == "critical"

    def test_high_severity(self, analyzer):
        """Hoher Schweregrad sollte erkannt werden."""
        severity = analyzer._calculate_severity(
            error_count=15,
            total_tokens=100,
            min_confidence=0.4
        )
        assert severity == "high"

    def test_medium_severity(self, analyzer):
        """Mittlerer Schweregrad sollte erkannt werden."""
        severity = analyzer._calculate_severity(
            error_count=7,
            total_tokens=100,
            min_confidence=0.6
        )
        assert severity == "medium"

    def test_low_severity(self, analyzer):
        """Niedriger Schweregrad sollte erkannt werden."""
        severity = analyzer._calculate_severity(
            error_count=2,
            total_tokens=100,
            min_confidence=0.8
        )
        assert severity == "low"

    def test_zero_tokens(self, analyzer):
        """Null Tokens sollten low Schweregrad ergeben."""
        severity = analyzer._calculate_severity(
            error_count=0,
            total_tokens=0,
            min_confidence=0.0
        )
        assert severity == "low"


class TestFormatReport:
    """Tests für Berichtformatierung."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_format_basic_report(self, analyzer):
        """Basis-Bericht sollte formatiert werden."""
        result = ErrorAnalysisResult(
            total_tokens=100,
            error_count=5,
            error_rate=0.05,
            mean_confidence=0.85,
            min_confidence=0.6,
            errors=[],
            patterns=[],
            word_errors={},
            recommendations=["Test Empfehlung"],
            severity="low"
        )

        report = analyzer.format_report(result)

        assert "TOKEN-LEVEL ERROR ANALYSIS" in report
        assert "100" in report  # total_tokens
        assert "5" in report  # error_count
        assert "Test Empfehlung" in report
        assert "LOW" in report  # severity

    def test_format_verbose_report(self, analyzer):
        """Ausführlicher Bericht sollte mehr Details enthalten."""
        result = ErrorAnalysisResult(
            total_tokens=100,
            error_count=5,
            error_rate=0.05,
            mean_confidence=0.85,
            min_confidence=0.6,
            errors=[TokenError(0, "test", 0.5, "context", "low_confidence", "fix")],
            patterns=[ErrorPattern("test_pattern", 3, ["ex1", "ex2"])],
            word_errors={},
            recommendations=["Empfehlung"],
            severity="medium"
        )

        report = analyzer.format_report(result, verbose=True)

        assert "ERKANNTE MUSTER" in report
        assert "TOP 10 FEHLER" in report
        assert "test_pattern" in report


class TestSingletonAndConvenienceFunctions:
    """Tests für Singleton und Convenience-Funktionen."""

    def test_get_token_error_analyzer_returns_instance(self):
        """get_token_error_analyzer sollte Instance zurückgeben."""
        analyzer = get_token_error_analyzer()

        assert analyzer is not None
        assert isinstance(analyzer, TokenErrorAnalyzer)

    def test_get_token_error_analyzer_returns_same_instance(self):
        """get_token_error_analyzer sollte Singleton sein."""
        instance1 = get_token_error_analyzer()
        instance2 = get_token_error_analyzer()

        assert instance1 is instance2

    def test_analyze_ocr_tokens_returns_result(self):
        """analyze_ocr_tokens sollte ErrorAnalysisResult zurückgeben."""
        result = analyze_ocr_tokens({"text": "Test"})

        assert isinstance(result, ErrorAnalysisResult)


class TestEdgeCases:
    """Tests für Edge Cases."""

    @pytest.fixture
    def analyzer(self):
        """Erstelle Analyzer."""
        return TokenErrorAnalyzer()

    def test_very_long_text(self, analyzer):
        """Sehr langer Text sollte verarbeitet werden."""
        long_text = "Dies ist ein Test. " * 1000
        ocr_result = {"text": long_text}

        result = analyzer.analyze(ocr_result)

        assert result is not None

    def test_special_characters_in_text(self, analyzer):
        """Sonderzeichen sollten verarbeitet werden."""
        text = "Test mit €, §, © und ™ Zeichen."
        ocr_result = {"text": text}

        result = analyzer.analyze(ocr_result)

        assert result is not None

    def test_unicode_text(self, analyzer):
        """Unicode-Text sollte verarbeitet werden."""
        text = "Test mit Ümläuten und Ẅëîrd Ćhàrąçtèrs."
        ocr_result = {"text": text}

        result = analyzer.analyze(ocr_result)

        assert result is not None

    def test_empty_confidence_lists(self, analyzer):
        """Leere Confidence-Listen sollten verarbeitet werden."""
        ocr_result = {
            "text": "Test",
            "confidence_data": {
                "mean_confidence": 0.0,
                "min_confidence": 0.0,
                "total_tokens": 0,
                "token_confidences": [],
                "low_confidence_positions": [],
            }
        }

        result = analyzer.analyze(ocr_result)

        assert result.error_count == 0
