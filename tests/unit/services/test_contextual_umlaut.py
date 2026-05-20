# -*- coding: utf-8 -*-
"""
Unit Tests fuer Contextual Umlaut Restoration.

Testet die kontextuelle Umlaut-Restaurierung:
- Kandidaten-Erkennung
- Heuristik-basierte Korrektur
- Fraktur-Normalisierung
"""

import pytest
from app.services.contextual_umlaut_restorer import (
    UmlautCandidate,
    UmlautCorrectionResult,
    ContextualUmlautRestorer,
    NO_UMLAUT_WORDS,
    FRAKTUR_TO_MODERN,
    restore_umlauts,
)


class TestUmlautCandidate:
    """Tests fuer UmlautCandidate Dataclass."""

    def test_create_candidate(self):
        """Kandidat wird korrekt erstellt."""
        candidate = UmlautCandidate(
            position=5,
            original="ae",
            replacement="\u00e4",
            word="fuer",
            context_left="text ",
            context_right=" mehr"
        )
        assert candidate.position == 5
        assert candidate.original == "ae"
        assert candidate.replacement == "\u00e4"


class TestContextualUmlautRestorer:
    """Tests fuer ContextualUmlautRestorer."""

    @pytest.fixture
    def restorer(self):
        """Erstelle Restorer ohne BERT fuer schnelle Tests."""
        return ContextualUmlautRestorer(enable_bert=False)

    def test_init_without_bert(self, restorer):
        """Initialisierung ohne BERT funktioniert."""
        assert restorer._enable_bert is False
        assert restorer._model is None

    def test_find_candidates_basic(self, restorer):
        """Grundlegende Kandidaten-Erkennung."""
        text = "fuer die Strasse"
        candidates = restorer._find_candidates(text)

        assert len(candidates) >= 1
        # "ue" in "fuer" sollte gefunden werden
        ue_candidates = [c for c in candidates if c.original == "ue"]
        assert len(ue_candidates) >= 1

    def test_find_candidates_excludes_no_umlaut_words(self, restorer):
        """Woerter in NO_UMLAUT_WORDS werden ignoriert."""
        text = "Boeing fliegt nach Israel"
        candidates = restorer._find_candidates(text)

        # Boeing und Israel sollten keine Kandidaten erzeugen
        words = [c.word.lower() for c in candidates]
        assert "boeing" not in words
        assert "israel" not in words

    def test_restore_empty_text(self, restorer):
        """Leerer Text wird korrekt behandelt."""
        result = restorer.restore("")
        assert result.corrected_text == ""
        assert result.method == "none"
        assert len(result.corrections) == 0

    def test_restore_no_candidates(self, restorer):
        """Text ohne Umlaut-Kandidaten bleibt unveraendert."""
        text = "Hallo Welt"
        result = restorer.restore(text)
        assert result.corrected_text == text
        assert result.method == "none"

    def test_restore_with_heuristics(self, restorer):
        """Heuristik-basierte Korrektur funktioniert."""
        text = "fuer die Kunden"
        result = restorer.restore(text)

        # Sollte "fuer" zu "f\u00fcr" korrigieren via Postprocessor
        assert result.method in ["dictionary", "simple"]

    def test_normalize_fraktur(self, restorer):
        """Fraktur-Zeichen werden normalisiert."""
        # Langes s
        text = "Stra\u017fe"  # Mit langem s
        normalized = restorer.normalize_fraktur(text)
        assert "\u017f" not in normalized

    def test_normalize_fraktur_ligatures(self, restorer):
        """Fraktur-Ligaturen werden aufgeloest."""
        text = "E\uFB00ekt"  # ff-Ligatur
        normalized = restorer.normalize_fraktur(text)
        assert "ff" in normalized


class TestNoUmlautWords:
    """Tests fuer NO_UMLAUT_WORDS Set."""

    def test_contains_common_exceptions(self):
        """Haeufige Ausnahmen sind enthalten."""
        assert "boeing" in NO_UMLAUT_WORDS
        assert "israel" in NO_UMLAUT_WORDS
        assert "queen" in NO_UMLAUT_WORDS
        assert "phoenix" in NO_UMLAUT_WORDS


class TestFrakturMapping:
    """Tests fuer FRAKTUR_TO_MODERN Mapping."""

    def test_contains_common_mappings(self):
        """Haeufige Fraktur-Zeichen sind gemappt."""
        assert '\u017F' in FRAKTUR_TO_MODERN  # Langes s
        assert '\uFB00' in FRAKTUR_TO_MODERN  # ff Ligatur


class TestConvenienceFunction:
    """Tests fuer Convenience-Funktionen."""

    def test_restore_umlauts_function(self):
        """restore_umlauts Funktion funktioniert."""
        text = "Hallo Welt"
        result = restore_umlauts(text, use_bert=False)
        assert isinstance(result, str)


class TestUmlautCorrectionResult:
    """Tests fuer UmlautCorrectionResult Dataclass."""

    def test_create_result(self):
        """Result wird korrekt erstellt."""
        result = UmlautCorrectionResult(
            original_text="fuer",
            corrected_text="f\u00fcr",
            corrections=[{"original": "ue", "corrected": "\u00fc"}],
            method="dictionary",
            confidence=0.9
        )
        assert result.original_text == "fuer"
        assert result.corrected_text == "f\u00fcr"
        assert len(result.corrections) == 1
        assert result.method == "dictionary"
        assert result.confidence == 0.9
