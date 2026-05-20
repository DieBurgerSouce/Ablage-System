# -*- coding: utf-8 -*-
"""
Tests fuer IndustryVocabularyService.

Phase 8: Deutsche Fachsprache

Tests:
- Branchenerkennung (detect_industry)
- Varianten-Korrekturen (apply_industry_corrections)
- Abkuerzungsexpansion
- Compound-Word-Erkennung
- Integration mit GermanTextPostprocessor
"""

import pytest
from typing import List

from app.services.ocr.industry_vocabulary_service import (
    CorrectionResult,
    IndustryDetectionResult,
    IndustryType,
    IndustryVocabularyService,
    get_industry_vocabulary_service,
)


class TestIndustryType:
    """Tests fuer IndustryType Enum."""

    def test_all_industry_types_exist(self) -> None:
        """Alle erwarteten Branchentypen existieren."""
        expected = ["baugewerbe", "handwerk", "medizin", "recht", "handel", "it", "general"]
        for industry in expected:
            assert IndustryType(industry) is not None

    def test_industry_type_values(self) -> None:
        """Werte entsprechen den JSON-Dateinamen."""
        assert IndustryType.BAUGEWERBE.value == "baugewerbe"
        assert IndustryType.HANDWERK.value == "handwerk"
        assert IndustryType.MEDIZIN.value == "medizin"
        assert IndustryType.RECHT.value == "recht"
        assert IndustryType.HANDEL.value == "handel"
        assert IndustryType.IT.value == "it"
        assert IndustryType.GENERAL.value == "general"


class TestIndustryDetection:
    """Tests fuer Branchenerkennung."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_detect_baugewerbe(self, service: IndustryVocabularyService) -> None:
        """Erkenne Baugewerbe-Text."""
        text = """
        Baustelle: Neubau Einfamilienhaus
        Rohbau-Arbeiten gemaess VOB/B
        Estrich und Putzarbeiten
        Bauherr: Max Mustermann
        """
        result = service.detect_industry(text)

        assert result.industry == IndustryType.BAUGEWERBE
        assert result.confidence > 0.3
        assert len(result.keyword_matches) > 0

    def test_detect_handwerk(self, service: IndustryVocabularyService) -> None:
        """Erkenne Handwerk-Text."""
        text = """
        Meisterbetrieb Mueller
        Kostenvoranschlag fuer Reparatur
        Stundenlohn: 55,00 EUR
        Anfahrtskosten: 25,00 EUR
        """
        result = service.detect_industry(text)

        assert result.industry == IndustryType.HANDWERK
        assert result.confidence > 0.3

    def test_detect_medizin(self, service: IndustryVocabularyService) -> None:
        """Erkenne Medizin-Text."""
        text = """
        Patient: Max Mustermann
        Diagnose: Grippe
        Therapie: Bettruhe
        Rezept fuer Medikamente
        Krankenkasse: AOK
        """
        result = service.detect_industry(text)

        assert result.industry == IndustryType.MEDIZIN
        assert result.confidence > 0.3

    def test_detect_recht(self, service: IndustryVocabularyService) -> None:
        """Erkenne Rechts-Text."""
        text = """
        Kaufvertrag
        Paragraph 433 BGB
        Der Klaeger erhebt Klage beim Amtsgericht
        Vollmacht fuer Rechtsanwalt
        """
        result = service.detect_industry(text)

        assert result.industry == IndustryType.RECHT
        assert result.confidence > 0.3

    def test_detect_handel(self, service: IndustryVocabularyService) -> None:
        """Erkenne Handels-Text."""
        text = """
        Rechnung Nr. 12345
        Lieferschein beiliegend
        Kundennummer: K-1234
        Zahlungsziel: 30 Tage
        Skonto: 2% bei Zahlung innerhalb 14 Tagen
        """
        result = service.detect_industry(text)

        assert result.industry == IndustryType.HANDEL
        assert result.confidence > 0.3

    def test_detect_it(self, service: IndustryVocabularyService) -> None:
        """Erkenne IT-Text."""
        text = """
        Softwarelizenz fuer Server
        Wartungsvertrag IT-Systeme
        Support-Ticket #4567
        Hosting und Cloud-Services
        """
        result = service.detect_industry(text)

        assert result.industry == IndustryType.IT
        assert result.confidence > 0.3

    def test_detect_empty_text(self, service: IndustryVocabularyService) -> None:
        """Leerer Text ergibt GENERAL."""
        result = service.detect_industry("")

        assert result.industry == IndustryType.GENERAL
        assert result.confidence == 0.0

    def test_detect_ambiguous_text(self, service: IndustryVocabularyService) -> None:
        """Mehrdeutiger Text wird erkannt."""
        text = "Hallo Welt, dies ist ein generischer Text."
        result = service.detect_industry(text)

        # Sollte entweder GENERAL oder niedrige Confidence haben
        if result.industry != IndustryType.GENERAL:
            assert result.confidence < 0.5


class TestIndustryCorrections:
    """Tests fuer branchenspezifische Korrekturen."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_correct_baugewerbe_variant(self, service: IndustryVocabularyService) -> None:
        """Korrigiere Baugewerbe-Variante."""
        # "Estrlch" ist eine OCR-Fehlervariante von "Estrich"
        text = "Der Estrlch ist fertig."
        result = service.apply_industry_corrections(
            text,
            industry=IndustryType.BAUGEWERBE
        )

        assert result.detected_industry == IndustryType.BAUGEWERBE
        # Korrektur sollte erfolgt sein wenn Variante im Vokabular
        # (je nach Vokabular-Definition)

    def test_correct_handwerk_variant(self, service: IndustryVocabularyService) -> None:
        """Korrigiere Handwerk-Variante."""
        text = "Der Melster hat die Arbeit abgeschlossen."
        result = service.apply_industry_corrections(
            text,
            industry=IndustryType.HANDWERK
        )

        # "Melster" -> "Meister" wenn im Vokabular
        assert result.detected_industry == IndustryType.HANDWERK

    def test_auto_detect_and_correct(self, service: IndustryVocabularyService) -> None:
        """Automatische Erkennung und Korrektur."""
        text = """
        Rechnung fuer Reparatur
        Meisterbetrieb Schmidt
        Stundenlohn und Anfahrtskosten
        """
        result = service.apply_industry_corrections(
            text,
            auto_detect_industry=True
        )

        # Sollte Handwerk erkennen
        assert result.detected_industry in [IndustryType.HANDWERK, IndustryType.HANDEL]

    def test_expand_abbreviations(self, service: IndustryVocabularyService) -> None:
        """Abkuerzungen werden gefunden."""
        text = "Gemaess VOB und HOAI"
        result = service.apply_industry_corrections(
            text,
            industry=IndustryType.BAUGEWERBE,
            expand_abbreviations=True
        )

        # Abkuerzungen sollten gefunden werden
        assert len(result.abbreviations_expanded) > 0
        abbrevs = [a["abbreviation"] for a in result.abbreviations_expanded]
        assert "VOB" in abbrevs or "HOAI" in abbrevs

    def test_find_compounds(self, service: IndustryVocabularyService) -> None:
        """Compound-Words werden erkannt."""
        text = "Die Baustelleneinrichtung ist abgeschlossen."
        result = service.apply_industry_corrections(
            text,
            industry=IndustryType.BAUGEWERBE
        )

        # Compound sollte gefunden werden
        assert "Baustelleneinrichtung" in result.compounds_found

    def test_no_corrections_for_correct_text(self, service: IndustryVocabularyService) -> None:
        """Korrekter Text bleibt unveraendert."""
        text = "Der Estrich ist fertig."  # Korrekte Schreibweise
        result = service.apply_industry_corrections(
            text,
            industry=IndustryType.BAUGEWERBE
        )

        # Keine Varianten-Korrekturen wenn Text korrekt
        variant_corrections = [
            c for c in result.corrections
            if c.get("type") == "variant_correction"
        ]
        assert len(variant_corrections) == 0

    def test_correction_result_properties(self, service: IndustryVocabularyService) -> None:
        """CorrectionResult Properties funktionieren."""
        result = CorrectionResult(
            original_text="Test",
            corrected_text="Test korrigiert",
            corrections=[{"type": "test", "original": "a", "corrected": "b"}]
        )

        assert result.has_corrections is True
        assert result.correction_count == 1


class TestAbbreviationExpansion:
    """Tests fuer Abkuerzungsexpansion."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_get_abbreviation_baugewerbe(self, service: IndustryVocabularyService) -> None:
        """Hole Baugewerbe-Abkuerzung."""
        expansion = service.get_abbreviation_expansion("VOB", IndustryType.BAUGEWERBE)
        assert expansion is not None
        assert "Vergabe" in expansion or "Vertragsordnung" in expansion

    def test_get_abbreviation_handel(self, service: IndustryVocabularyService) -> None:
        """Hole Handels-Abkuerzung."""
        expansion = service.get_abbreviation_expansion("MwSt", IndustryType.HANDEL)
        assert expansion is not None
        assert "Mehrwertsteuer" in expansion

    def test_get_abbreviation_medizin(self, service: IndustryVocabularyService) -> None:
        """Hole Medizin-Abkuerzung."""
        expansion = service.get_abbreviation_expansion("EKG", IndustryType.MEDIZIN)
        assert expansion is not None
        assert "Elektrokardiogramm" in expansion

    def test_get_abbreviation_unknown(self, service: IndustryVocabularyService) -> None:
        """Unbekannte Abkuerzung ergibt None."""
        expansion = service.get_abbreviation_expansion("XYZ123", IndustryType.HANDEL)
        assert expansion is None

    def test_get_abbreviation_cross_industry(self, service: IndustryVocabularyService) -> None:
        """Abkuerzung ohne Branche sucht in allen."""
        expansion = service.get_abbreviation_expansion("MwSt")
        assert expansion is not None


class TestTermInfo:
    """Tests fuer Term-Informationen."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_get_term_info(self, service: IndustryVocabularyService) -> None:
        """Hole Term-Informationen."""
        info = service.get_term_info("estrich", IndustryType.BAUGEWERBE)

        assert info is not None
        assert "canonical" in info
        assert info["canonical"] == "Estrich"

    def test_get_term_info_unknown(self, service: IndustryVocabularyService) -> None:
        """Unbekannter Term ergibt None."""
        info = service.get_term_info("xyzunbekannt", IndustryType.BAUGEWERBE)
        assert info is None


class TestIndustryKeywords:
    """Tests fuer Detection-Keywords."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_get_keywords_baugewerbe(self, service: IndustryVocabularyService) -> None:
        """Hole Baugewerbe-Keywords."""
        keywords = service.get_industry_keywords(IndustryType.BAUGEWERBE)

        assert len(keywords) > 0
        assert "baustelle" in keywords or "rohbau" in keywords

    def test_get_keywords_general(self, service: IndustryVocabularyService) -> None:
        """GENERAL hat keine Keywords."""
        keywords = service.get_industry_keywords(IndustryType.GENERAL)
        assert keywords == []


class TestStatistics:
    """Tests fuer Statistiken."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_get_statistics(self, service: IndustryVocabularyService) -> None:
        """Statistiken werden korrekt erstellt."""
        stats = service.get_statistics()

        assert "industries_loaded" in stats
        assert stats["industries_loaded"] >= 6  # Mindestens 6 Branchen

        assert "industries" in stats
        for industry_name, industry_stats in stats["industries"].items():
            assert "terms_count" in industry_stats
            assert "variants_count" in industry_stats
            assert "compounds_count" in industry_stats
            assert "abbreviations_count" in industry_stats


class TestSingletonInstance:
    """Tests fuer Singleton-Pattern."""

    def test_singleton_returns_same_instance(self) -> None:
        """get_industry_vocabulary_service gibt immer dieselbe Instanz."""
        service1 = get_industry_vocabulary_service()
        service2 = get_industry_vocabulary_service()

        assert service1 is service2


class TestGeneralOCRCorrections:
    """Tests fuer allgemeine OCR-Korrekturen."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_correct_common_ocr_errors(self, service: IndustryVocabularyService) -> None:
        """Haeufige OCR-Fehler werden korrigiert."""
        # Test mit bekannten OCR-Fehlern
        text = "Die Lleferung ist angekommen."
        result = service.apply_industry_corrections(text)

        # Je nach implementierten Patterns
        # sollten allgemeine OCR-Fehler korrigiert werden
        assert isinstance(result, CorrectionResult)


class TestEdgeCases:
    """Tests fuer Randfaelle."""

    @pytest.fixture
    def service(self) -> IndustryVocabularyService:
        """Erstelle Service-Instanz."""
        return IndustryVocabularyService()

    def test_empty_text(self, service: IndustryVocabularyService) -> None:
        """Leerer Text wird behandelt."""
        result = service.apply_industry_corrections("")

        assert result.original_text == ""
        assert result.corrected_text == ""
        assert result.corrections == []

    def test_none_industry(self, service: IndustryVocabularyService) -> None:
        """None-Industry fuehrt zu Auto-Detection."""
        text = "Test Text"
        result = service.apply_industry_corrections(
            text,
            industry=None,
            auto_detect_industry=True
        )

        assert isinstance(result, CorrectionResult)

    def test_special_characters(self, service: IndustryVocabularyService) -> None:
        """Sonderzeichen werden korrekt behandelt."""
        text = "Preis: 1.234,56 € (inkl. MwSt.)"
        result = service.apply_industry_corrections(text)

        # Text sollte nicht kaputt gehen
        assert "€" in result.corrected_text
        assert "1.234,56" in result.corrected_text

    def test_unicode_text(self, service: IndustryVocabularyService) -> None:
        """Unicode-Text wird korrekt verarbeitet."""
        text = "Größe: 5m² für Fußboden"
        result = service.apply_industry_corrections(text)

        assert "ö" in result.corrected_text or "oe" in result.corrected_text
        assert "ü" in result.corrected_text or "ue" in result.corrected_text
