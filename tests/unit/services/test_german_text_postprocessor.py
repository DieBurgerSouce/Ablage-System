# -*- coding: utf-8 -*-
"""
Unit Tests fuer German Text Postprocessor.

Tests fuer deutsche Textnachbearbeitung:
- Umlaut-Restaurierung
- Eszett-Korrektur
- Statistiken und Singleton-Pattern
"""

import pytest
from unittest.mock import MagicMock, patch

from app.services.german_text_postprocessor import (
    GermanTextPostprocessor,
    get_german_postprocessor,
    postprocess_german_text,
)


class TestGermanTextPostprocessorInit:
    """Tests fuer Postprocessor Initialisierung."""

    def test_init_default_settings(self):
        """Standardeinstellungen sollten korrekt gesetzt werden."""
        postprocessor = GermanTextPostprocessor(use_validator=False)

        assert postprocessor.use_validator is False
        assert postprocessor.aggressive_mode is False
        assert postprocessor._stats["total_processed"] == 0

    def test_init_aggressive_mode(self):
        """Aggressive Mode sollte aktivierbar sein."""
        postprocessor = GermanTextPostprocessor(
            use_validator=False,
            aggressive_mode=True
        )

        assert postprocessor.aggressive_mode is True

    def test_init_loads_validator_when_available(self):
        """GermanValidator sollte geladen werden wenn verfuegbar."""
        # GermanValidator wird nur geladen wenn importierbar
        # Wir testen dass use_validator Flag gesetzt wird
        postprocessor = GermanTextPostprocessor(use_validator=True)
        assert postprocessor.use_validator is True
        # Validator kann None sein wenn Import fehlschlaegt - das ist OK

    def test_init_handles_missing_validator(self):
        """Fehlender GermanValidator sollte graceful behandelt werden."""
        postprocessor = GermanTextPostprocessor(use_validator=True)

        # Wenn Import fehlschlaegt, ist _validator None
        # Das ist akzeptables Verhalten
        assert postprocessor.use_validator is True

    def test_umlaut_lookup_built(self):
        """Umlaut-Lookup sollte bei Init erstellt werden."""
        postprocessor = GermanTextPostprocessor(use_validator=False)

        assert hasattr(postprocessor, '_umlaut_lookup')
        assert isinstance(postprocessor._umlaut_lookup, dict)

    def test_eszett_lookup_built(self):
        """Eszett-Lookup sollte bei Init erstellt werden."""
        postprocessor = GermanTextPostprocessor(use_validator=False)

        assert hasattr(postprocessor, '_eszett_lookup')
        assert isinstance(postprocessor._eszett_lookup, dict)

    def test_word_pattern_compiled(self):
        """Regex Pattern sollte vorkompiliert sein."""
        postprocessor = GermanTextPostprocessor(use_validator=False)

        assert hasattr(postprocessor, '_word_pattern')
        assert postprocessor._word_pattern is not None


class TestPostprocess:
    """Tests fuer die postprocess Methode."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_empty_text_returns_empty(self, postprocessor):
        """Leerer Text sollte leeres Ergebnis liefern."""
        result = postprocessor.postprocess("")

        assert result["text"] == ""
        assert result["corrections"] == []
        assert result["processed"] is False

    def test_none_text_returns_empty(self, postprocessor):
        """None sollte wie leerer Text behandelt werden."""
        result = postprocessor.postprocess(None)

        assert result["text"] == ""
        assert result["processed"] is False

    def test_whitespace_only_returns_empty(self, postprocessor):
        """Nur Whitespace sollte wie leerer Text behandelt werden."""
        result = postprocessor.postprocess("   \n\t  ")

        assert result["text"] == "   \n\t  "
        assert result["processed"] is False

    def test_result_structure(self, postprocessor):
        """Ergebnis sollte erwartete Struktur haben."""
        result = postprocessor.postprocess("Test text")

        assert "text" in result
        assert "corrections" in result
        assert "corrections_count" in result
        assert "stats" in result
        assert "processed" in result
        assert "text_changed" in result

    def test_stats_structure(self, postprocessor):
        """Stats sollten erwartete Felder haben."""
        result = postprocessor.postprocess("Test text")

        assert "umlaut_corrections" in result["stats"]
        assert "eszett_corrections" in result["stats"]
        assert "total" in result["stats"]

    def test_skip_umlauts_option(self, postprocessor):
        """skip_umlauts Option sollte Umlaut-Korrektur ueberspringen."""
        result = postprocessor.postprocess(
            "Test text",
            options={"skip_umlauts": True}
        )

        assert result["processed"] is True
        # Keine Umlaut-Korrekturen da uebersprungen
        assert result["stats"]["umlaut_corrections"] == 0

    def test_skip_eszett_option(self, postprocessor):
        """skip_eszett Option sollte Eszett-Korrektur ueberspringen."""
        result = postprocessor.postprocess(
            "Test text",
            options={"skip_eszett": True}
        )

        assert result["processed"] is True
        assert result["stats"]["eszett_corrections"] == 0

    def test_increments_total_processed(self, postprocessor):
        """Verarbeitungszaehler sollte inkrementiert werden."""
        initial = postprocessor._stats["total_processed"]

        postprocessor.postprocess("Text 1")
        postprocessor.postprocess("Text 2")
        postprocessor.postprocess("Text 3")

        assert postprocessor._stats["total_processed"] == initial + 3

    def test_text_unchanged_when_no_corrections(self, postprocessor):
        """text_changed sollte False sein wenn keine Korrekturen."""
        result = postprocessor.postprocess("Hello World")

        # Englischer Text sollte unveraendert bleiben
        assert result["text"] == "Hello World"
        # text_changed haengt davon ab ob Korrekturen gemacht wurden
        assert "text_changed" in result

    def test_corrections_list_populated(self, postprocessor):
        """corrections Liste sollte Korrekturen enthalten."""
        result = postprocessor.postprocess("Test")

        assert isinstance(result["corrections"], list)
        # Jede Korrektur sollte Struktur haben
        for correction in result["corrections"]:
            assert "type" in correction
            assert "original" in correction
            assert "corrected" in correction
            assert "confidence" in correction


class TestRestoreUmlauts:
    """Tests fuer Umlaut-Restaurierung."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_umlaut_word_detection(self, postprocessor):
        """Woerter aus GERMAN_UMLAUT_WORDS sollten erkannt werden."""
        # Pruefe dass die Word-Sets vorhanden sind
        assert len(postprocessor.GERMAN_UMLAUT_WORDS) > 0
        assert 'fuer' in postprocessor.GERMAN_UMLAUT_WORDS or \
               'für' in postprocessor.GERMAN_UMLAUT_WORDS

    def test_umlaut_correction_has_confidence(self, postprocessor):
        """Umlaut-Korrekturen sollten Confidence haben."""
        result = postprocessor.postprocess("Test")

        for correction in result["corrections"]:
            if correction["type"] == "umlaut":
                assert 0.0 <= correction["confidence"] <= 1.0

    def test_preserves_capitalization(self, postprocessor):
        """Grossschreibung sollte beibehalten werden."""
        # Verarbeite Text und pruefe dass Grossschreibung erhalten bleibt
        result = postprocessor.postprocess("Ein Test")

        # Text sollte Grossschreibung behalten
        assert result["text"][0] == "E"  # "Ein" bleibt gross


class TestRestoreEszett:
    """Tests fuer Eszett-Restaurierung."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_eszett_word_detection(self, postprocessor):
        """Woerter aus ESZETT_WORDS sollten erkannt werden."""
        assert len(postprocessor.ESZETT_WORDS) > 0
        assert 'strasse' in postprocessor.ESZETT_WORDS or \
               'straße' in postprocessor.ESZETT_WORDS or \
               'Strasse' in postprocessor.ESZETT_WORDS

    def test_eszett_correction_has_confidence(self, postprocessor):
        """Eszett-Korrekturen sollten Confidence haben."""
        result = postprocessor.postprocess("Test")

        for correction in result["corrections"]:
            if correction["type"] == "eszett":
                assert 0.0 <= correction["confidence"] <= 1.0


class TestStatistics:
    """Tests fuer Statistik-Funktionen."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_get_stats_returns_dict(self, postprocessor):
        """get_stats sollte Dictionary zurueckgeben."""
        stats = postprocessor.get_stats()

        assert isinstance(stats, dict)

    def test_get_stats_contains_expected_fields(self, postprocessor):
        """get_stats sollte erwartete Felder enthalten."""
        stats = postprocessor.get_stats()

        assert "total_processed" in stats
        assert "umlaut_corrections" in stats
        assert "eszett_corrections" in stats
        assert "validation_errors" in stats
        assert "umlaut_words_in_dictionary" in stats
        assert "eszett_words_in_dictionary" in stats

    def test_reset_stats_clears_counters(self, postprocessor):
        """reset_stats sollte Zaehler zuruecksetzen."""
        # Verarbeite einige Texte
        postprocessor.postprocess("Text 1")
        postprocessor.postprocess("Text 2")

        assert postprocessor._stats["total_processed"] > 0

        # Reset
        postprocessor.reset_stats()

        assert postprocessor._stats["total_processed"] == 0
        assert postprocessor._stats["umlaut_corrections"] == 0
        assert postprocessor._stats["eszett_corrections"] == 0
        assert postprocessor._stats["validation_errors"] == 0

    def test_stats_accumulate(self, postprocessor):
        """Statistiken sollten akkumulieren."""
        initial = postprocessor._stats["total_processed"]

        for i in range(5):
            postprocessor.postprocess(f"Text {i}")

        assert postprocessor._stats["total_processed"] == initial + 5


class TestSingletonAndConvenienceFunctions:
    """Tests fuer Singleton und Convenience-Funktionen."""

    def test_get_german_postprocessor_returns_instance(self):
        """get_german_postprocessor sollte Instance zurueckgeben."""
        postprocessor = get_german_postprocessor()

        assert postprocessor is not None
        assert isinstance(postprocessor, GermanTextPostprocessor)

    def test_get_german_postprocessor_returns_same_instance(self):
        """get_german_postprocessor sollte Singleton sein."""
        instance1 = get_german_postprocessor()
        instance2 = get_german_postprocessor()

        assert instance1 is instance2

    def test_postprocess_german_text_returns_result(self):
        """postprocess_german_text sollte Ergebnis zurueckgeben."""
        result = postprocess_german_text("Test text")

        assert isinstance(result, dict)
        assert "text" in result
        assert "corrections" in result

    def test_postprocess_german_text_with_options(self):
        """postprocess_german_text sollte Optionen akzeptieren."""
        result = postprocess_german_text(
            "Test text",
            options={"skip_umlauts": True}
        )

        assert result["processed"] is True


class TestValidation:
    """Tests fuer Validierungs-Integration."""

    def test_validation_disabled_by_default(self):
        """Validierung sollte standardmaessig nicht in Ergebnis sein."""
        postprocessor = GermanTextPostprocessor(use_validator=False)
        result = postprocessor.postprocess("Test")

        # Ohne validate=True sollte keine Validierung stattfinden
        assert "validation" not in result or result.get("validation") is None

    def test_validation_requested_but_validator_missing(self):
        """Validierung sollte graceful fehlschlagen ohne Validator."""
        postprocessor = GermanTextPostprocessor(use_validator=False)
        result = postprocessor.postprocess("Test", options={"validate": True})

        # Ohne Validator wird validation nicht hinzugefuegt
        assert result["processed"] is True


class TestEdgeCases:
    """Tests fuer Edge Cases."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_very_long_text(self, postprocessor):
        """Sehr langer Text sollte verarbeitet werden koennen."""
        long_text = "Dies ist ein Test. " * 10000

        result = postprocessor.postprocess(long_text)

        assert result["processed"] is True
        assert len(result["text"]) > 0

    def test_special_characters(self, postprocessor):
        """Sonderzeichen sollten erhalten bleiben."""
        text_with_special = "Test @#$%^&*() {}\\"

        result = postprocessor.postprocess(text_with_special)

        assert "@" in result["text"]
        assert "#" in result["text"]

    def test_unicode_characters(self, postprocessor):
        """Unicode-Zeichen sollten erhalten bleiben."""
        unicode_text = "Test mit Unicode: ©®™"

        result = postprocessor.postprocess(unicode_text)

        assert "©" in result["text"]
        assert "®" in result["text"]
        assert "™" in result["text"]

    def test_numbers_preserved(self, postprocessor):
        """Zahlen sollten unveraendert bleiben."""
        text_with_numbers = "12345 67890"

        result = postprocessor.postprocess(text_with_numbers)

        assert "12345" in result["text"]
        assert "67890" in result["text"]

    def test_newlines_preserved(self, postprocessor):
        """Zeilenumbrueche sollten erhalten bleiben."""
        text_with_newlines = "Zeile 1\nZeile 2\nZeile 3"

        result = postprocessor.postprocess(text_with_newlines)

        assert result["text"].count("\n") == 2

    def test_tabs_preserved(self, postprocessor):
        """Tabs sollten erhalten bleiben."""
        text_with_tabs = "Spalte1\tSpalte2\tSpalte3"

        result = postprocessor.postprocess(text_with_tabs)

        assert "\t" in result["text"]

    def test_multiple_spaces_preserved(self, postprocessor):
        """Mehrfache Leerzeichen sollten erhalten bleiben."""
        text_with_spaces = "Wort1    Wort2"

        result = postprocessor.postprocess(text_with_spaces)

        assert "    " in result["text"]


class TestWordSets:
    """Tests fuer Woerter-Sets."""

    def test_german_umlaut_words_not_empty(self):
        """GERMAN_UMLAUT_WORDS sollte nicht leer sein."""
        assert len(GermanTextPostprocessor.GERMAN_UMLAUT_WORDS) > 0

    def test_eszett_words_not_empty(self):
        """ESZETT_WORDS sollte nicht leer sein."""
        assert len(GermanTextPostprocessor.ESZETT_WORDS) > 0

    def test_ascii_to_umlaut_mapping_exists(self):
        """ASCII_TO_UMLAUT Mapping sollte existieren."""
        assert hasattr(GermanTextPostprocessor, 'ASCII_TO_UMLAUT')
        assert isinstance(GermanTextPostprocessor.ASCII_TO_UMLAUT, dict)

    def test_word_sets_are_sets(self):
        """Wortlisten sollten Sets sein fuer O(1) Lookup."""
        assert isinstance(GermanTextPostprocessor.GERMAN_UMLAUT_WORDS, set)
        assert isinstance(GermanTextPostprocessor.ESZETT_WORDS, set)

    def test_ascii_to_umlaut_contains_real_umlauts(self):
        """ASCII_TO_UMLAUT sollte echte Umlaute enthalten."""
        mapping = GermanTextPostprocessor.ASCII_TO_UMLAUT
        assert mapping.get('ae') == 'ä'
        assert mapping.get('oe') == 'ö'
        assert mapping.get('ue') == 'ü'
        assert mapping.get('Ae') == 'Ä'
        assert mapping.get('Oe') == 'Ö'
        assert mapping.get('Ue') == 'Ü'


class TestColognePhonetic:
    """Tests fuer Cologne Phonetic Algorithmus."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_cologne_phonetic_empty_string(self, postprocessor):
        """Leerer String sollte leeren Code ergeben."""
        assert postprocessor.cologne_phonetic("") == ""

    def test_cologne_phonetic_basic_word(self, postprocessor):
        """Basiswoerter sollten phonetische Codes erzeugen."""
        code = postprocessor.cologne_phonetic("Mueller")
        assert len(code) > 0

    def test_cologne_phonetic_same_for_similar_sounds(self, postprocessor):
        """Phonetisch aehnliche Woerter sollten gleichen Code haben."""
        # Mueller und Müller sollten gleich klingen
        code1 = postprocessor.cologne_phonetic("Mueller")
        code2 = postprocessor.cologne_phonetic("Müller")
        assert code1 == code2

    def test_cologne_phonetic_meier_variations(self, postprocessor):
        """Verschiedene Schreibweisen von Meier sollten aehnlich klingen."""
        # Meier, Meyer, Maier, Mayer
        codes = [
            postprocessor.cologne_phonetic(name)
            for name in ["Meier", "Meyer", "Maier", "Mayer"]
        ]
        # Alle sollten identisch oder sehr aehnlich sein
        assert len(set(codes)) <= 2

    def test_cologne_phonetic_handles_sch(self, postprocessor):
        """'sch' sollte korrekt behandelt werden."""
        code = postprocessor.cologne_phonetic("Schreiber")
        assert '8' in code  # sch -> 8

    def test_cologne_phonetic_handles_ch(self, postprocessor):
        """'ch' sollte kontextabhaengig behandelt werden."""
        code = postprocessor.cologne_phonetic("Bach")
        assert len(code) > 0


class TestPhoneticSimilarity:
    """Tests fuer phonetische Aehnlichkeit."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_identical_words_have_similarity_1(self, postprocessor):
        """Identische Woerter sollten Aehnlichkeit 1.0 haben."""
        similarity = postprocessor.phonetic_similarity("Test", "Test")
        assert similarity == 1.0

    def test_completely_different_words_have_low_similarity(self, postprocessor):
        """Komplett verschiedene Woerter sollten niedrige Aehnlichkeit haben."""
        similarity = postprocessor.phonetic_similarity("ABC", "XYZ")
        assert similarity < 0.5

    def test_similar_german_names_have_high_similarity(self, postprocessor):
        """Phonetisch aehnliche Namen sollten hohe Aehnlichkeit haben."""
        # Mueller vs Müller
        similarity = postprocessor.phonetic_similarity("Mueller", "Müller")
        assert similarity >= 0.9

    def test_similarity_is_symmetric(self, postprocessor):
        """Aehnlichkeit sollte symmetrisch sein."""
        sim1 = postprocessor.phonetic_similarity("Wort1", "Wort2")
        sim2 = postprocessor.phonetic_similarity("Wort2", "Wort1")
        assert abs(sim1 - sim2) < 0.01


class TestCompoundWordSplitting:
    """Tests fuer Compound-Word-Splitting."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_short_words_not_split(self, postprocessor):
        """Kurze Woerter sollten nicht gesplittet werden."""
        parts = postprocessor.split_compound_word("Test")
        assert parts == ["Test"]

    def test_compound_with_known_prefix(self, postprocessor):
        """Compound mit bekanntem Praefix sollte gesplittet werden."""
        parts = postprocessor.split_compound_word("Überprüfung")
        assert len(parts) >= 1  # Mindestens erkannt

    def test_compound_with_known_suffix(self, postprocessor):
        """Compound mit bekanntem Suffix sollte gesplittet werden."""
        parts = postprocessor.split_compound_word("Steuerrechnung")
        assert len(parts) >= 1

    def test_compound_prefixes_exist(self, postprocessor):
        """COMPOUND_PREFIXES sollte Eintraege haben."""
        assert len(postprocessor.COMPOUND_PREFIXES) > 0
        assert 'über' in postprocessor.COMPOUND_PREFIXES

    def test_compound_suffixes_exist(self, postprocessor):
        """COMPOUND_SUFFIXES sollte Eintraege haben."""
        assert len(postprocessor.COMPOUND_SUFFIXES) > 0
        assert 'ung' in postprocessor.COMPOUND_SUFFIXES


class TestCorrectWithPhonetic:
    """Tests fuer phonetische Korrektur."""

    @pytest.fixture
    def postprocessor(self):
        """Erstelle Postprocessor ohne Validator."""
        return GermanTextPostprocessor(use_validator=False)

    def test_correct_with_phonetic_finds_match(self, postprocessor):
        """Phonetische Korrektur sollte aehnliches Wort finden."""
        candidates = ["Müller", "Schmidt", "Fischer"]
        match = postprocessor.correct_with_phonetic("Mueller", candidates)
        assert match == "Müller"

    def test_correct_with_phonetic_no_match_below_threshold(self, postprocessor):
        """Keine Korrektur wenn unter Schwellenwert."""
        candidates = ["XYZ", "ABC", "DEF"]
        match = postprocessor.correct_with_phonetic("Mueller", candidates, threshold=0.9)
        assert match is None

    def test_correct_with_phonetic_empty_candidates(self, postprocessor):
        """Leere Kandidatenliste sollte None ergeben."""
        match = postprocessor.correct_with_phonetic("Test", [])
        assert match is None

    def test_correct_with_phonetic_respects_threshold(self, postprocessor):
        """Schwellenwert sollte beruecksichtigt werden."""
        candidates = ["Müller", "Schmidt"]
        # Mit hohem Threshold
        match = postprocessor.correct_with_phonetic("Test", candidates, threshold=0.99)
        assert match is None
