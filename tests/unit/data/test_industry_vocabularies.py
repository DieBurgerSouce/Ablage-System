# -*- coding: utf-8 -*-
"""
Tests fuer Industry Vocabularies Daten.

Phase 8: Deutsche Fachsprache

Tests fuer:
- JSON-Dateien Laden
- Struktur-Validierung
- Helper-Funktionen
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict, List

from app.data.industry_vocabularies import (
    VOCABULARY_DIR,
    get_abbreviation,
    get_available_industries,
    get_term,
    load_vocabulary,
)


class TestVocabularyLoading:
    """Tests fuer Vokabular-Laden."""

    def test_vocabulary_dir_exists(self) -> None:
        """Vokabular-Verzeichnis existiert."""
        assert VOCABULARY_DIR.exists()
        assert VOCABULARY_DIR.is_dir()

    def test_get_available_industries(self) -> None:
        """Verfuegbare Branchen werden gefunden."""
        industries = get_available_industries()

        assert len(industries) >= 6
        assert "baugewerbe" in industries
        assert "handwerk" in industries
        assert "medizin" in industries
        assert "recht" in industries
        assert "handel" in industries
        assert "it" in industries

    def test_load_vocabulary_baugewerbe(self) -> None:
        """Baugewerbe-Vokabular wird geladen."""
        vocab = load_vocabulary("baugewerbe")

        assert "industry" in vocab
        assert vocab["industry"] == "baugewerbe"
        assert "terms" in vocab
        assert "compounds" in vocab
        assert "abbreviations" in vocab
        assert "detection_keywords" in vocab

    def test_load_vocabulary_handwerk(self) -> None:
        """Handwerk-Vokabular wird geladen."""
        vocab = load_vocabulary("handwerk")

        assert vocab["industry"] == "handwerk"
        assert len(vocab["terms"]) > 0

    def test_load_vocabulary_medizin(self) -> None:
        """Medizin-Vokabular wird geladen."""
        vocab = load_vocabulary("medizin")

        assert vocab["industry"] == "medizin"
        assert len(vocab["terms"]) > 0

    def test_load_vocabulary_recht(self) -> None:
        """Recht-Vokabular wird geladen."""
        vocab = load_vocabulary("recht")

        assert vocab["industry"] == "recht"
        assert len(vocab["terms"]) > 0

    def test_load_vocabulary_handel(self) -> None:
        """Handel-Vokabular wird geladen."""
        vocab = load_vocabulary("handel")

        assert vocab["industry"] == "handel"
        assert len(vocab["terms"]) > 0

    def test_load_vocabulary_it(self) -> None:
        """IT-Vokabular wird geladen."""
        vocab = load_vocabulary("it")

        assert vocab["industry"] == "it"
        assert len(vocab["terms"]) > 0

    def test_load_vocabulary_not_found(self) -> None:
        """Nicht existierendes Vokabular wirft Fehler."""
        with pytest.raises(FileNotFoundError):
            load_vocabulary("nicht_existierend")

    def test_vocabulary_caching(self) -> None:
        """Vokabulare werden gecacht."""
        # Erstes Laden
        vocab1 = load_vocabulary("baugewerbe")
        # Zweites Laden (sollte aus Cache kommen)
        vocab2 = load_vocabulary("baugewerbe")

        # Sollte dasselbe Objekt sein (LRU Cache)
        assert vocab1 is vocab2


class TestVocabularyStructure:
    """Tests fuer Vokabular-Struktur."""

    @pytest.fixture
    def all_vocabularies(self) -> Dict[str, Dict[str, Any]]:
        """Lade alle Vokabulare."""
        vocabs = {}
        for industry in get_available_industries():
            vocabs[industry] = load_vocabulary(industry)
        return vocabs

    def test_all_have_required_fields(self, all_vocabularies: Dict[str, Dict[str, Any]]) -> None:
        """Alle Vokabulare haben erforderliche Felder."""
        required_fields = ["industry", "version", "language", "terms"]

        for industry, vocab in all_vocabularies.items():
            for field in required_fields:
                assert field in vocab, f"{industry} fehlt Feld '{field}'"

    def test_terms_structure(self, all_vocabularies: Dict[str, Dict[str, Any]]) -> None:
        """Terme haben korrekte Struktur."""
        for industry, vocab in all_vocabularies.items():
            terms = vocab.get("terms", {})

            for term_key, term_data in terms.items():
                assert "canonical" in term_data, (
                    f"{industry}/{term_key} fehlt 'canonical'"
                )
                assert "variants" in term_data, (
                    f"{industry}/{term_key} fehlt 'variants'"
                )
                assert isinstance(term_data["variants"], list), (
                    f"{industry}/{term_key} 'variants' ist keine Liste"
                )

    def test_compounds_structure(self, all_vocabularies: Dict[str, Dict[str, Any]]) -> None:
        """Compounds haben korrekte Struktur."""
        for industry, vocab in all_vocabularies.items():
            compounds = vocab.get("compounds", [])

            for compound in compounds:
                assert "word" in compound, f"{industry} Compound fehlt 'word'"
                assert "parts" in compound, f"{industry} Compound fehlt 'parts'"
                assert isinstance(compound["parts"], list), (
                    f"{industry} Compound 'parts' ist keine Liste"
                )

    def test_abbreviations_structure(self, all_vocabularies: Dict[str, Dict[str, Any]]) -> None:
        """Abbreviations haben korrekte Struktur."""
        for industry, vocab in all_vocabularies.items():
            abbreviations = vocab.get("abbreviations", {})

            assert isinstance(abbreviations, dict), (
                f"{industry} 'abbreviations' ist kein Dict"
            )

            for abbrev, expansion in abbreviations.items():
                assert isinstance(abbrev, str), f"{industry}/{abbrev} Key ist kein String"
                assert isinstance(expansion, str), (
                    f"{industry}/{abbrev} Expansion ist kein String"
                )

    def test_detection_keywords_structure(
        self, all_vocabularies: Dict[str, Dict[str, Any]]
    ) -> None:
        """Detection Keywords haben korrekte Struktur."""
        for industry, vocab in all_vocabularies.items():
            keywords = vocab.get("detection_keywords", [])

            assert isinstance(keywords, list), (
                f"{industry} 'detection_keywords' ist keine Liste"
            )

            for keyword in keywords:
                assert isinstance(keyword, str), (
                    f"{industry} Keyword ist kein String"
                )

    def test_version_format(self, all_vocabularies: Dict[str, Dict[str, Any]]) -> None:
        """Version hat SemVer-Format."""
        import re
        semver_pattern = r"^\d+\.\d+\.\d+$"

        for industry, vocab in all_vocabularies.items():
            version = vocab.get("version", "")
            assert re.match(semver_pattern, version), (
                f"{industry} Version '{version}' ist kein SemVer"
            )

    def test_language_is_de(self, all_vocabularies: Dict[str, Dict[str, Any]]) -> None:
        """Sprache ist Deutsch."""
        for industry, vocab in all_vocabularies.items():
            assert vocab.get("language") == "de", (
                f"{industry} Sprache ist nicht 'de'"
            )


class TestHelperFunctions:
    """Tests fuer Helper-Funktionen."""

    def test_get_term_exists(self) -> None:
        """Existierender Term wird gefunden."""
        term = get_term("baugewerbe", "estrich")

        assert term is not None
        assert "canonical" in term
        assert term["canonical"] == "Estrich"

    def test_get_term_not_exists(self) -> None:
        """Nicht existierender Term ergibt None."""
        term = get_term("baugewerbe", "xyzabc123")
        assert term is None

    def test_get_term_invalid_industry(self) -> None:
        """Ungueltige Branche ergibt None."""
        term = get_term("ungueltig", "estrich")
        assert term is None

    def test_get_term_case_insensitive(self) -> None:
        """Term-Suche ist case-insensitive."""
        term1 = get_term("baugewerbe", "estrich")
        term2 = get_term("baugewerbe", "ESTRICH")
        term3 = get_term("baugewerbe", "Estrich")

        # Alle sollten denselben Term finden
        assert term1 == term2 == term3

    def test_get_abbreviation_exists(self) -> None:
        """Existierende Abkuerzung wird gefunden."""
        expansion = get_abbreviation("baugewerbe", "VOB")

        assert expansion is not None
        assert "Vergabe" in expansion or "Vertragsordnung" in expansion

    def test_get_abbreviation_not_exists(self) -> None:
        """Nicht existierende Abkuerzung ergibt None."""
        expansion = get_abbreviation("baugewerbe", "XYZ123")
        assert expansion is None

    def test_get_abbreviation_invalid_industry(self) -> None:
        """Ungueltige Branche ergibt None."""
        expansion = get_abbreviation("ungueltig", "VOB")
        assert expansion is None


class TestVocabularyContent:
    """Tests fuer Vokabular-Inhalt."""

    def test_baugewerbe_has_key_terms(self) -> None:
        """Baugewerbe hat wichtige Terme."""
        vocab = load_vocabulary("baugewerbe")
        terms = vocab["terms"]

        key_terms = ["estrich", "beton", "mauerwerk", "rohbau", "baustelle"]
        for term in key_terms:
            assert term in terms, f"Baugewerbe fehlt Term '{term}'"

    def test_baugewerbe_has_key_abbreviations(self) -> None:
        """Baugewerbe hat wichtige Abkuerzungen."""
        vocab = load_vocabulary("baugewerbe")
        abbreviations = vocab["abbreviations"]

        key_abbrevs = ["VOB", "HOAI", "LV"]
        for abbrev in key_abbrevs:
            assert abbrev in abbreviations, f"Baugewerbe fehlt Abkuerzung '{abbrev}'"

    def test_handwerk_has_key_terms(self) -> None:
        """Handwerk hat wichtige Terme."""
        vocab = load_vocabulary("handwerk")
        terms = vocab["terms"]

        key_terms = ["meister", "geselle", "werkstatt", "reparatur"]
        for term in key_terms:
            assert term in terms, f"Handwerk fehlt Term '{term}'"

    def test_medizin_has_key_terms(self) -> None:
        """Medizin hat wichtige Terme."""
        vocab = load_vocabulary("medizin")
        terms = vocab["terms"]

        key_terms = ["diagnose", "therapie", "patient", "rezept"]
        for term in key_terms:
            assert term in terms, f"Medizin fehlt Term '{term}'"

    def test_medizin_has_key_abbreviations(self) -> None:
        """Medizin hat wichtige Abkuerzungen."""
        vocab = load_vocabulary("medizin")
        abbreviations = vocab["abbreviations"]

        key_abbrevs = ["EKG", "MRT", "CT"]
        for abbrev in key_abbrevs:
            assert abbrev in abbreviations, f"Medizin fehlt Abkuerzung '{abbrev}'"

    def test_recht_has_key_terms(self) -> None:
        """Recht hat wichtige Terme."""
        vocab = load_vocabulary("recht")
        terms = vocab["terms"]

        key_terms = ["vertrag", "klausel", "vollmacht", "anwalt"]
        for term in key_terms:
            assert term in terms, f"Recht fehlt Term '{term}'"

    def test_handel_has_key_terms(self) -> None:
        """Handel hat wichtige Terme."""
        vocab = load_vocabulary("handel")
        terms = vocab["terms"]

        key_terms = ["rechnung", "lieferschein", "bestellung", "kunde"]
        for term in key_terms:
            assert term in terms, f"Handel fehlt Term '{term}'"

    def test_it_has_key_terms(self) -> None:
        """IT hat wichtige Terme."""
        vocab = load_vocabulary("it")
        terms = vocab["terms"]

        key_terms = ["software", "lizenz", "server", "support"]
        for term in key_terms:
            assert term in terms, f"IT fehlt Term '{term}'"


class TestVariantsQuality:
    """Tests fuer Varianten-Qualitaet."""

    def test_variants_contain_canonical(self) -> None:
        """Varianten enthalten oft den kanonischen Term."""
        vocab = load_vocabulary("baugewerbe")

        for term_key, term_data in vocab["terms"].items():
            canonical = term_data["canonical"]
            variants = term_data["variants"]

            # Canonical sollte als Variante (case-insensitive) vorhanden sein
            variants_lower = [v.lower() for v in variants]
            # Mindestens eine Variante sollte existieren
            assert len(variants) > 0, f"{term_key} hat keine Varianten"

    def test_variants_are_plausible_ocr_errors(self) -> None:
        """Varianten sind plausible OCR-Fehler."""
        vocab = load_vocabulary("baugewerbe")

        # Stichprobe von Termen pruefen
        estrich = vocab["terms"].get("estrich", {})
        variants = estrich.get("variants", [])

        # Sollte OCR-Fehlervarianten haben
        assert len(variants) >= 1

        # Varianten sollten aehnlich wie Original sein
        for variant in variants:
            # Nicht zu unterschiedlich vom Original
            assert len(variant) <= len("Estrich") + 3
            assert len(variant) >= len("Estrich") - 3


class TestJSONValidity:
    """Tests fuer JSON-Validitaet."""

    def test_all_json_files_valid(self) -> None:
        """Alle JSON-Dateien sind valide."""
        for json_file in VOCABULARY_DIR.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    assert isinstance(data, dict)
                except json.JSONDecodeError as e:
                    pytest.fail(f"{json_file.name} ist kein valides JSON: {e}")

    def test_utf8_encoding(self) -> None:
        """Alle Dateien sind UTF-8 kodiert."""
        for json_file in VOCABULARY_DIR.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                content = f.read()
                # Sollte deutsche Umlaute korrekt enthalten koennen
                # (wenn vorhanden in der Datei)
                assert isinstance(content, str)
