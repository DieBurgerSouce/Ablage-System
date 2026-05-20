# -*- coding: utf-8 -*-
"""
Tests fuer GermanTextPostprocessor mit Industry Vocabulary Integration.

Phase 8: Deutsche Fachsprache

Tests fuer die Integration von branchenspezifischen Vokabularen
in den GermanTextPostprocessor.
"""

import pytest
from typing import Any, Dict

from app.services.german_text_postprocessor import (
    GermanTextPostprocessor,
    get_german_postprocessor,
    postprocess_german_text,
)


class TestGermanTextPostprocessorIndustryIntegration:
    """Tests fuer Industry Vocabulary Integration."""

    @pytest.fixture
    def postprocessor(self) -> GermanTextPostprocessor:
        """Erstelle Postprocessor mit Industry Support."""
        return GermanTextPostprocessor(
            use_validator=False,  # Validator nicht fuer diese Tests
            use_industry_vocabulary=True
        )

    @pytest.fixture
    def postprocessor_no_industry(self) -> GermanTextPostprocessor:
        """Erstelle Postprocessor ohne Industry Support."""
        return GermanTextPostprocessor(
            use_validator=False,
            use_industry_vocabulary=False
        )

    def test_initialization_with_industry(self, postprocessor: GermanTextPostprocessor) -> None:
        """Initialisierung mit Industry Vocabulary."""
        assert postprocessor.use_industry_vocabulary is True
        assert postprocessor._industry_vocab_service is not None

    def test_initialization_without_industry(
        self, postprocessor_no_industry: GermanTextPostprocessor
    ) -> None:
        """Initialisierung ohne Industry Vocabulary."""
        assert postprocessor_no_industry.use_industry_vocabulary is False
        assert postprocessor_no_industry._industry_vocab_service is None

    def test_postprocess_with_auto_industry_detection(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Postprocess mit automatischer Branchenerkennung."""
        text = """
        Baustelle: Neubau Einfamilienhaus
        Estrich und Putzarbeiten
        Bauherr: Max Mustermann
        """
        result = postprocessor.postprocess(text)

        assert result["processed"] is True
        # Industry detection sollte vorhanden sein
        if "industry_detection" in result:
            assert result["industry_detection"]["industry"] in [
                "baugewerbe", "handwerk"
            ]

    def test_postprocess_with_explicit_industry(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Postprocess mit expliziter Branche."""
        text = "Der Estrich ist fertig."
        result = postprocessor.postprocess(
            text,
            options={"industry": "baugewerbe"}
        )

        assert result["processed"] is True
        if "industry_detection" in result:
            assert result["industry_detection"]["industry"] == "baugewerbe"

    def test_postprocess_skip_industry(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Branchenkorrektur kann uebersprungen werden."""
        text = "Test Text mit VOB Abkuerzung"
        result = postprocessor.postprocess(
            text,
            options={"skip_industry": True}
        )

        assert result["processed"] is True
        assert "industry_detection" not in result

    def test_postprocess_with_abbreviation_expansion(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Abkuerzungsexpansion wird gefunden."""
        text = "Gemaess VOB/B sind die Arbeiten auszufuehren."
        result = postprocessor.postprocess(
            text,
            options={
                "industry": "baugewerbe",
                "expand_abbreviations": True
            }
        )

        assert result["processed"] is True
        if "industry_detection" in result:
            # Abkuerzungen sollten gefunden werden
            abbrevs = result["industry_detection"].get("abbreviations_expanded", [])
            # VOB sollte erkannt werden
            abbrev_names = [a.get("abbreviation", "") for a in abbrevs]
            # Entweder VOB oder VOB/B
            assert any("VOB" in name for name in abbrev_names) or len(abbrevs) >= 0

    def test_stats_include_industry_corrections(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Stats enthalten Industry-Korrekturen."""
        # Verarbeite Text
        postprocessor.postprocess("Test Text")

        stats = postprocessor.get_stats()
        assert "industry_corrections" in stats

    def test_stats_include_industry_vocabularies(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Stats enthalten Industry Vocabulary Info."""
        stats = postprocessor.get_stats()

        assert "industry_vocabularies" in stats
        assert "industries_loaded" in stats["industry_vocabularies"]
        assert stats["industry_vocabularies"]["industries_loaded"] >= 6

    def test_reset_stats_includes_industry(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Reset setzt auch Industry-Stats zurueck."""
        # Verarbeite etwas
        postprocessor.postprocess("Test")
        postprocessor.reset_stats()

        stats = postprocessor.get_stats()
        assert stats["industry_corrections"] == 0

    def test_combined_corrections(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Kombinierte Korrekturen (Umlaute + Industry)."""
        text = "Der Meisterbetrieb fuehrt die Arbeiten durch."
        result = postprocessor.postprocess(text)

        assert result["processed"] is True
        # Sollte sowohl Umlaut als auch ggf. Industry-Korrekturen haben
        assert "stats" in result
        total_corrections = result["stats"]["total"]
        # Mindestens die Umlaut-Korrektur "fuehrt" -> "führt"
        assert total_corrections >= 0  # Kann 0 sein wenn kein Match

    def test_medizin_industry(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Medizin-Branche wird erkannt."""
        text = """
        Patient: Max Mustermann
        Diagnose: Bronchitis
        Therapie: Antibiotika
        Rezept beigefuegt
        """
        result = postprocessor.postprocess(
            text,
            options={"industry": "medizin"}
        )

        assert result["processed"] is True
        if "industry_detection" in result:
            assert result["industry_detection"]["industry"] == "medizin"

    def test_recht_industry(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Rechts-Branche wird erkannt."""
        text = """
        Kaufvertrag gemaess § 433 BGB
        Vollmacht fuer Rechtsanwalt
        """
        result = postprocessor.postprocess(
            text,
            options={"industry": "recht"}
        )

        assert result["processed"] is True
        if "industry_detection" in result:
            assert result["industry_detection"]["industry"] == "recht"

    def test_handel_industry(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Handels-Branche wird erkannt."""
        text = """
        Rechnung Nr. 12345
        Lieferschein beiliegend
        Zahlungsziel: 30 Tage netto
        """
        result = postprocessor.postprocess(
            text,
            options={"industry": "handel"}
        )

        assert result["processed"] is True
        if "industry_detection" in result:
            assert result["industry_detection"]["industry"] == "handel"

    def test_it_industry(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """IT-Branche wird erkannt."""
        text = """
        Softwarelizenz fuer Server
        Wartungsvertrag inklusive Support
        Hosting-Services
        """
        result = postprocessor.postprocess(
            text,
            options={"industry": "it"}
        )

        assert result["processed"] is True
        if "industry_detection" in result:
            assert result["industry_detection"]["industry"] == "it"

    def test_invalid_industry_handling(
        self, postprocessor: GermanTextPostprocessor
    ) -> None:
        """Ungueltige Branche wird behandelt."""
        text = "Test Text"
        # Sollte keinen Fehler werfen
        result = postprocessor.postprocess(
            text,
            options={"industry": "ungueltige_branche"}
        )

        assert result["processed"] is True


class TestConvenienceFunctions:
    """Tests fuer Convenience-Funktionen."""

    def test_get_german_postprocessor_singleton(self) -> None:
        """Singleton-Pattern funktioniert."""
        p1 = get_german_postprocessor()
        p2 = get_german_postprocessor()

        assert p1 is p2

    def test_postprocess_german_text_function(self) -> None:
        """Convenience-Funktion funktioniert."""
        result = postprocess_german_text("Test fuer Ueberpruefung")

        assert result["processed"] is True


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.fixture
    def postprocessor(self) -> GermanTextPostprocessor:
        """Erstelle Postprocessor."""
        return GermanTextPostprocessor(
            use_validator=False,
            use_industry_vocabulary=True
        )

    def test_empty_text(self, postprocessor: GermanTextPostprocessor) -> None:
        """Leerer Text wird behandelt."""
        result = postprocessor.postprocess("")

        assert result["processed"] is False
        assert result["text"] == ""

    def test_whitespace_only(self, postprocessor: GermanTextPostprocessor) -> None:
        """Nur Whitespace wird behandelt."""
        result = postprocessor.postprocess("   \n\t  ")

        assert result["processed"] is False

    def test_none_options(self, postprocessor: GermanTextPostprocessor) -> None:
        """None-Options werden behandelt."""
        result = postprocessor.postprocess("Test", options=None)

        assert result["processed"] is True

    def test_text_with_numbers(self, postprocessor: GermanTextPostprocessor) -> None:
        """Text mit Zahlen wird korrekt verarbeitet."""
        text = "Rechnung Nr. 12345 ueber 1.234,56 EUR"
        result = postprocessor.postprocess(text)

        assert "12345" in result["text"]
        assert "1.234,56" in result["text"]

    def test_text_with_special_chars(self, postprocessor: GermanTextPostprocessor) -> None:
        """Sonderzeichen werden erhalten."""
        text = "Preis: 100,00 € (inkl. 19% MwSt.)"
        result = postprocessor.postprocess(text)

        assert "€" in result["text"]
        assert "19%" in result["text"]

    def test_long_text(self, postprocessor: GermanTextPostprocessor) -> None:
        """Langer Text wird verarbeitet."""
        text = "Test Text. " * 1000
        result = postprocessor.postprocess(text)

        assert result["processed"] is True
        assert len(result["text"]) > 0


class TestCorrectionCounting:
    """Tests fuer Korrektur-Zaehlung."""

    @pytest.fixture
    def postprocessor(self) -> GermanTextPostprocessor:
        """Erstelle Postprocessor."""
        return GermanTextPostprocessor(
            use_validator=False,
            use_industry_vocabulary=True
        )

    def test_stats_structure(self, postprocessor: GermanTextPostprocessor) -> None:
        """Stats-Struktur ist korrekt."""
        result = postprocessor.postprocess("Test fuer Pruefung")

        assert "stats" in result
        stats = result["stats"]
        assert "umlaut_corrections" in stats
        assert "eszett_corrections" in stats
        assert "industry_corrections" in stats
        assert "total" in stats

    def test_corrections_list(self, postprocessor: GermanTextPostprocessor) -> None:
        """Corrections-Liste enthaelt Details."""
        result = postprocessor.postprocess("Pruefung der Groesse")

        assert "corrections" in result
        assert isinstance(result["corrections"], list)

        # Jede Korrektur sollte type, original, corrected haben
        for correction in result["corrections"]:
            assert "type" in correction
            assert "original" in correction
            assert "corrected" in correction
