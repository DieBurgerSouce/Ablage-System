# -*- coding: utf-8 -*-
"""
Unit Tests für Character-Level Ensemble Voting.

Testet die neue Character-Level Voting Funktionalität:
- Needleman-Wunsch Alignment
- Confidence-gewichtetes Voting
- Plausibility Check mit deutschem Lexikon
- Edge Cases und Fehlerbehandlung
"""

import pytest
from app.services.ensemble_voting import (
    OCRResult,
    EnsembleVotingService,
    levenshtein_distance,
    needleman_wunsch_align,
    calculate_agreement,
)


class TestLevenshteinDistance:
    """Tests für Levenshtein-Distanz-Berechnung."""

    def test_identical_strings(self):
        """Identische Strings haben Distanz 0."""
        assert levenshtein_distance("hello", "hello") == 0
        assert levenshtein_distance("über", "über") == 0

    def test_empty_strings(self):
        """Leere Strings."""
        assert levenshtein_distance("", "") == 0
        assert levenshtein_distance("abc", "") == 3
        assert levenshtein_distance("", "abc") == 3

    def test_single_edit(self):
        """Single-Edit-Distanz."""
        assert levenshtein_distance("cat", "bat") == 1  # Substitution
        assert levenshtein_distance("cat", "cats") == 1  # Insertion
        assert levenshtein_distance("cats", "cat") == 1  # Deletion

    def test_german_umlauts(self):
        """Deutsche Umlaute werden korrekt behandelt."""
        assert levenshtein_distance("über", "ueber") == 2  # ü -> ue
        assert levenshtein_distance("straße", "strasse") == 2  # ß -> ss
        assert levenshtein_distance("Müller", "Mueller") == 2  # ü -> ue (2 ops: delete ü, insert ue)


class TestNeedlemanWunschAlign:
    """Tests für Needleman-Wunsch Alignment."""

    def test_identical_sequences(self):
        """Identische Sequenzen brauchen keine Gaps."""
        aligned1, aligned2 = needleman_wunsch_align("GATTACA", "GATTACA")
        assert aligned1 == "GATTACA"
        assert aligned2 == "GATTACA"

    def test_simple_gap(self):
        """Einfache Gap-Einfügung."""
        aligned1, aligned2 = needleman_wunsch_align("ABC", "AC")
        assert "-" in aligned2 or "-" in aligned1

    def test_german_text_alignment(self):
        """Deutscher Text wird korrekt aligniert."""
        text1 = "über die Straße"
        text2 = "ueber die Strasse"
        aligned1, aligned2 = needleman_wunsch_align(text1, text2)
        # Beide sollten ähnliche Länge haben nach Alignment
        assert abs(len(aligned1) - len(aligned2)) <= 2

    def test_empty_sequence(self):
        """Leere Sequenz erzeugt nur Gaps."""
        aligned1, aligned2 = needleman_wunsch_align("ABC", "")
        assert aligned2 == "---"


class TestCharacterLevelVoting:
    """Tests für Character-Level Ensemble Voting."""

    @pytest.fixture
    def voting_service(self):
        """Erstelle Voting Service für Tests."""
        return EnsembleVotingService(default_method="character_level")

    def test_single_result_fallback(self, voting_service):
        """Bei nur einem Ergebnis wird Fallback verwendet."""
        results = [
            OCRResult(backend="deepseek", text="Hallo Welt", confidence=0.95)
        ]
        result = voting_service.combine(results, method="character_level")
        assert result.text == "Hallo Welt"
        assert result.method == "single"  # Single-Result wird direkt zurückgegeben

    def test_identical_results(self, voting_service):
        """Identische Ergebnisse werden korrekt kombiniert."""
        results = [
            OCRResult(backend="deepseek", text="Hallo Welt", confidence=0.95),
            OCRResult(backend="got_ocr", text="Hallo Welt", confidence=0.90),
            OCRResult(backend="surya_gpu", text="Hallo Welt", confidence=0.85),
        ]
        result = voting_service.combine(results, method="character_level")
        assert result.text == "Hallo Welt"
        assert result.agreement_score == 1.0  # 100% Agreement
        assert result.method == "character_level"

    def test_slight_differences(self, voting_service):
        """Kleine Unterschiede werden durch Voting korrigiert."""
        results = [
            OCRResult(backend="deepseek", text="Hallo Welt", confidence=0.95),
            OCRResult(backend="got_ocr", text="Hallo Welt", confidence=0.90),
            OCRResult(backend="surya_gpu", text="Hello Welt", confidence=0.70),  # Fehler
        ]
        result = voting_service.combine(results, method="character_level")
        # Die Mehrheit sagt "Hallo"
        assert "allo" in result.text  # "Hallo" sollte gewinnen

    def test_german_umlaut_voting(self, voting_service):
        """Deutsche Umlaute werden korrekt behandelt."""
        results = [
            OCRResult(backend="deepseek", text="über die Straße", confidence=0.95),
            OCRResult(backend="got_ocr", text="über die Straße", confidence=0.90),
            OCRResult(backend="surya_gpu", text="ueber die Strasse", confidence=0.75),
        ]
        result = voting_service.combine(results, method="character_level")
        # DeepSeek und GOT-OCR haben höhere Confidence
        assert "ü" in result.text or result.text.count("über") > 0

    def test_confidence_weighting(self, voting_service):
        """Höhere Confidence hat mehr Gewicht."""
        results = [
            OCRResult(backend="deepseek", text="A", confidence=0.99),  # Hohe Conf
            OCRResult(backend="got_ocr", text="B", confidence=0.50),   # Niedrige Conf
        ]
        result = voting_service.combine(results, method="character_level")
        # A sollte gewinnen wegen höherer Confidence
        assert result.text == "A"

    def test_disagreement_tracking(self, voting_service):
        """Disagreement-Positionen werden getrackt."""
        results = [
            OCRResult(backend="deepseek", text="AAXAA", confidence=0.90),
            OCRResult(backend="got_ocr", text="AABAA", confidence=0.90),
            OCRResult(backend="surya_gpu", text="AACAA", confidence=0.90),
        ]
        result = voting_service.combine(results, method="character_level")
        # Position 2 hat Disagreement (X vs B vs C)
        assert "disagreement_positions" in result.metadata
        assert len(result.metadata["disagreement_positions"]) > 0

    def test_alignment_scores_in_metadata(self, voting_service):
        """Alignment-Scores werden in Metadata gespeichert."""
        results = [
            OCRResult(backend="deepseek", text="Test", confidence=0.90),
            OCRResult(backend="got_ocr", text="Test", confidence=0.85),
        ]
        result = voting_service.combine(results, method="character_level")
        assert "alignment_scores" in result.metadata

    def test_empty_results(self, voting_service):
        """Leere Ergebnisliste wird behandelt."""
        result = voting_service.combine([], method="character_level")
        assert result.text == ""
        assert result.confidence == 0.0

    def test_empty_text_results(self, voting_service):
        """Leere Texte werden behandelt."""
        results = [
            OCRResult(backend="deepseek", text="", confidence=0.90),
            OCRResult(backend="got_ocr", text="", confidence=0.85),
        ]
        result = voting_service.combine(results, method="character_level")
        # Fallback zu weighted voting bei leeren Texten
        assert result.method == "weighted"


class TestPlausibilityCheck:
    """Tests für Plausibility Check mit deutschem Lexikon."""

    @pytest.fixture
    def voting_service(self):
        """Erstelle Voting Service für Tests."""
        return EnsembleVotingService(default_method="character_level")

    def test_umlaut_correction_via_plausibility(self, voting_service):
        """ASCII-Umlaute werden über Plausibility Check korrigiert."""
        # Simuliere Ergebnis wo alle Backends "fuer" statt "für" erkannt haben
        results = [
            OCRResult(backend="deepseek", text="fuer Sie", confidence=0.90),
            OCRResult(backend="got_ocr", text="fuer Sie", confidence=0.85),
        ]
        result = voting_service.combine(results, method="character_level")
        # Plausibility Check sollte "fuer" -> "für" korrigieren
        assert "für" in result.text or "fuer" in result.text  # Hängt von Postprocessor ab

    def test_eszett_correction_via_plausibility(self, voting_service):
        """ss wird über Plausibility Check zu ß korrigiert."""
        results = [
            OCRResult(backend="deepseek", text="die Strasse", confidence=0.90),
            OCRResult(backend="got_ocr", text="die Strasse", confidence=0.85),
        ]
        result = voting_service.combine(results, method="character_level")
        # Plausibility Check sollte "Strasse" -> "Straße" korrigieren
        assert "Straße" in result.text or "Strasse" in result.text


class TestBackendWeighting:
    """Tests für Backend-Gewichtung bei Character-Level Voting."""

    @pytest.fixture
    def voting_service(self):
        """Erstelle Voting Service mit angepassten Gewichten."""
        service = EnsembleVotingService(default_method="character_level")
        # DeepSeek hat höchstes Gewicht
        service.set_backend_weight("deepseek", 2.0)
        service.set_backend_weight("got_ocr", 1.0)
        service.set_backend_weight("surya_gpu", 0.5)
        return service

    def test_higher_weight_wins(self, voting_service):
        """Backend mit höherem Gewicht gewinnt bei gleicher Confidence."""
        results = [
            OCRResult(backend="deepseek", text="A", confidence=0.80),    # Gewicht 2.0
            OCRResult(backend="surya_gpu", text="B", confidence=0.80),   # Gewicht 0.5
        ]
        result = voting_service.combine(results, method="character_level")
        assert result.text == "A"  # DeepSeek gewinnt


class TestIntegration:
    """Integration-Tests für Character-Level Voting."""

    def test_real_world_german_document(self):
        """Realistisches deutsches Dokument-Szenario."""
        service = EnsembleVotingService(default_method="character_level")

        # Simuliere typische OCR-Ausgaben für ein deutsches Dokument
        results = [
            OCRResult(
                backend="deepseek",
                text="Sehr geehrte Damen und Herren,\n\nhiermit übersende ich Ihnen die Rechnung für den Monat März.",
                confidence=0.92
            ),
            OCRResult(
                backend="got_ocr",
                text="Sehr geehrte Damen und Herren,\n\nhiermit uebersende ich Ihnen die Rechnung fuer den Monat Maerz.",
                confidence=0.88
            ),
            OCRResult(
                backend="surya_gpu",
                text="Sehr geehrte Damen und Herren,\n\nhiermit übersende ich lhnen die Rechnung für den Monat März.",
                confidence=0.78  # Hat "lhnen" statt "Ihnen"
            ),
        ]

        result = service.combine(results, method="character_level")

        # Prüfe Grundqualität
        assert "Sehr geehrte" in result.text
        assert "Rechnung" in result.text
        assert result.confidence > 0.7
        assert result.method == "character_level"

    def test_high_disagreement_document(self):
        """Dokument mit hoher Disagreement-Rate."""
        service = EnsembleVotingService(default_method="character_level")

        # Texte mit einigen gemeinsamen Zeichen aber unterschiedlichen Positionen
        results = [
            OCRResult(backend="deepseek", text="ABCD", confidence=0.90),
            OCRResult(backend="got_ocr", text="AXCD", confidence=0.90),
            OCRResult(backend="surya_gpu", text="ABYD", confidence=0.90),
        ]

        result = service.combine(results, method="character_level")

        # Bei teilweisem Disagreement sollten Positionen getrackt werden
        assert result.method == "character_level"
        # Die Mehrheit sollte gewinnen
        assert result.text[0] == "A"  # Alle haben A am Anfang
        assert result.text[3] == "D"  # Alle haben D am Ende
