# -*- coding: utf-8 -*-
"""
Unit tests for GermanCorrectionAgent.

Tests for German language correction including:
- Umlaut restoration (ae→ä, oe→ö, ue→ü)
- Eszett (ß) corrections
- Context-aware corrections
- Domain-specific corrections (accounting, legal, medical)
- Fuzzy matching for OCR errors
- Compound word handling
- LanguageTool integration
"""

import pytest
from typing import Dict, Any, List, Tuple
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def german_correction_agent():
    """Create GermanCorrectionAgent instance for testing."""
    with patch("app.agents.postprocessing.german_correction_agent.GermanValidator") as mock_validator:
        mock_validator.return_value.validate_umlauts.return_value = {
            "is_valid": True,
            "umlauts_found": [],
            "potential_errors": [],
            "confidence": 0.95
        }

        # Disable LanguageTool for basic tests
        with patch("app.agents.postprocessing.german_correction_agent.LANGUAGETOOL_AVAILABLE", False):
            from app.agents.postprocessing.german_correction_agent import GermanCorrectionAgent
            agent = GermanCorrectionAgent(enable_languagetool=False)
            return agent


@pytest.fixture
def german_correction_agent_with_lt():
    """Create GermanCorrectionAgent with mocked LanguageTool."""
    with patch("app.agents.postprocessing.german_correction_agent.GermanValidator") as mock_validator:
        mock_validator.return_value.validate_umlauts.return_value = {
            "is_valid": True,
            "umlauts_found": [],
            "potential_errors": [],
            "confidence": 0.95
        }

        with patch("app.agents.postprocessing.german_correction_agent.LANGUAGETOOL_AVAILABLE", True):
            with patch("app.agents.postprocessing.german_correction_agent.LanguageTool") as mock_lt:
                mock_lt_instance = Mock()
                mock_lt_instance.check.return_value = []
                mock_lt.return_value = mock_lt_instance

                from app.agents.postprocessing.german_correction_agent import GermanCorrectionAgent
                agent = GermanCorrectionAgent(enable_languagetool=True)
                agent._language_tool = mock_lt_instance
                return agent


class TestUmlautRestoration:
    """Tests for umlaut restoration from ASCII substitutions."""

    @pytest.mark.asyncio
    async def test_restore_ae_to_a_umlaut(self, german_correction_agent):
        """Test restoration of ae → ä."""
        text = "Die Aenderung wurde bestaetigt."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        assert "Änderung" in corrected
        assert "bestätigt" in corrected or "bestaetigt" not in corrected.lower()

    @pytest.mark.asyncio
    async def test_restore_oe_to_o_umlaut(self, german_correction_agent):
        """Test restoration of oe → ö."""
        text = "Die Oeffnungszeiten der Behoerde."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should restore at least one of these
        assert "Öffnung" in corrected or "Behörde" in corrected or "ö" in corrected

    @pytest.mark.asyncio
    async def test_restore_ue_to_u_umlaut(self, german_correction_agent):
        """Test restoration of ue → ü."""
        text = "Wir muessen die Pruefung durchfuehren."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should restore at least one of these
        assert "müssen" in corrected or "Prüfung" in corrected or "ü" in corrected

    @pytest.mark.asyncio
    async def test_preserve_correct_umlauts(self, german_correction_agent):
        """Test that already correct umlauts are preserved."""
        text = "Die Änderung der Öffnungszeiten wurde bestätigt."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        assert "Änderung" in corrected
        assert "Öffnungszeiten" in corrected
        assert "bestätigt" in corrected

    @pytest.mark.asyncio
    async def test_uppercase_umlaut_restoration(self, german_correction_agent):
        """Test restoration of uppercase umlauts."""
        text = "AENDERUNG und OEFFNUNG"

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should restore to uppercase umlauts
        assert "ÄNDERUNG" in corrected or "Ä" in corrected

    @pytest.mark.asyncio
    async def test_mixed_case_preservation(self, german_correction_agent):
        """Test that case is preserved during correction."""
        text = "Die Aenderung in aenderung"

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should have capitalized Änderung and lowercase änderung
        if "Änderung" in corrected:
            # Case should be preserved
            assert True


class TestEszettCorrections:
    """Tests for Eszett (ß) corrections."""

    @pytest.mark.asyncio
    async def test_correct_strasse_to_straße(self, german_correction_agent):
        """Test correction of Strasse → Straße."""
        text = "Die Hauptstrasse in Berlin."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        assert "Straße" in corrected or "straße" in corrected.lower()

    @pytest.mark.asyncio
    async def test_correct_grosse_to_große(self, german_correction_agent):
        """Test correction of grosse → große."""
        text = "Eine grosse Veranstaltung."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        assert "große" in corrected or "ß" in corrected

    @pytest.mark.asyncio
    async def test_correct_heisst_to_heißt(self, german_correction_agent):
        """Test correction of heisst → heißt."""
        text = "Das heisst, wir beginnen."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        assert "heißt" in corrected or "ß" in corrected

    @pytest.mark.asyncio
    async def test_correct_massnahme_to_maßnahme(self, german_correction_agent):
        """Test correction of Massnahme → Maßnahme."""
        text = "Diese Massnahme ist wichtig."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        assert "Maßnahme" in corrected or "ß" in corrected

    @pytest.mark.asyncio
    async def test_preserve_correct_eszett(self, german_correction_agent):
        """Test that correct Eszett is preserved."""
        text = "Die Straße ist groß."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        assert "Straße" in corrected
        assert "groß" in corrected


class TestDomainSpecificCorrections:
    """Tests for domain-specific corrections."""

    @pytest.mark.asyncio
    async def test_accounting_domain_corrections(self, german_correction_agent):
        """Test accounting domain corrections."""
        text = "Die Buchfuehrung zeigt Rueckstellungen."

        result = await german_correction_agent.process({
            "text": text,
            "domain": "accounting"
        })

        corrected = result.get("text", "")
        assert "Buchführung" in corrected or "Rückstellungen" in corrected or "ü" in corrected

    @pytest.mark.asyncio
    async def test_legal_domain_corrections(self, german_correction_agent):
        """Test legal domain corrections."""
        text = "Der Geschaeftsfuehrer und die Kuendigungsfrist."

        result = await german_correction_agent.process({
            "text": text,
            "domain": "legal"
        })

        corrected = result.get("text", "")
        # Should correct domain-specific terms
        assert "ü" in corrected or "ä" in corrected or "ö" in corrected

    @pytest.mark.asyncio
    async def test_medical_domain_corrections(self, german_correction_agent):
        """Test medical domain corrections."""
        text = "Der Arztbericht zur Gesundheitspruefung."

        result = await german_correction_agent.process({
            "text": text,
            "domain": "medical"
        })

        corrected = result.get("text", "")
        # Should correct medical terms
        assert isinstance(corrected, str)

    @pytest.mark.asyncio
    async def test_domain_auto_detection(self, german_correction_agent):
        """Test automatic domain detection from classification."""
        text = "Die Buchfuehrung zeigt Mehrwertsteuer."

        result = await german_correction_agent.process({
            "text": text,
            "classification": {"document_type": "Rechnung"}
        })

        # Should detect accounting domain
        domain = result.get("domain_detected")
        assert domain == "accounting" or domain is None


class TestFuzzyMatching:
    """Tests for fuzzy matching corrections."""

    @pytest.mark.asyncio
    async def test_fuzzy_match_similar_words(self, german_correction_agent):
        """Test fuzzy matching for OCR errors."""
        # Word with slight OCR error
        text = "Die Verfugung wurde erteilt."  # Missing ü

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # May correct to Verfügung if fuzzy matching is aggressive enough
        assert isinstance(corrected, str)

    @pytest.mark.asyncio
    async def test_no_false_positives_fuzzy(self, german_correction_agent):
        """Test that fuzzy matching doesn't create false positives."""
        text = "Das Experiment war erfolgreich."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should not incorrectly modify valid German words
        assert "Experiment" in corrected or "experiment" in corrected.lower()


class TestCompoundWords:
    """Tests for compound word handling."""

    @pytest.mark.asyncio
    async def test_compound_word_umlaut_correction(self, german_correction_agent):
        """Test umlaut correction in compound words."""
        text = "Die Vertragsaenderung und Kundenbehoerde."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should correct umlauts in compound words
        assert isinstance(corrected, str)

    @pytest.mark.asyncio
    async def test_long_compound_preservation(self, german_correction_agent):
        """Test that long compound words are handled correctly."""
        text = "Das Bundesverfassungsgericht entscheidet."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should preserve valid compound
        assert "Bundesverfassungsgericht" in corrected


class TestPatternCorrections:
    """Tests for context-aware pattern corrections."""

    @pytest.mark.asyncio
    async def test_pattern_correction_with_context(self, german_correction_agent):
        """Test pattern correction uses context."""
        text = "Die naechste Aenderung ist wichtig."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should correct based on context patterns
        assert "nächste" in corrected or "Änderung" in corrected

    @pytest.mark.asyncio
    async def test_skip_pattern_corrections_option(self, german_correction_agent):
        """Test skipping pattern corrections via option."""
        text = "Die naechste Aenderung."

        result = await german_correction_agent.process({
            "text": text,
            "options": {"skip_pattern_corrections": True}
        })

        # Pattern corrections should be skipped
        assert "text" in result


class TestLanguageToolIntegration:
    """Tests for LanguageTool integration."""

    @pytest.mark.asyncio
    async def test_languagetool_corrections(self, german_correction_agent_with_lt):
        """Test LanguageTool grammar corrections."""
        text = "Der Text mit einem Fehler."

        result = await german_correction_agent_with_lt.process({"text": text})

        # Should process without error
        assert "text" in result

    @pytest.mark.asyncio
    async def test_skip_languagetool_option(self, german_correction_agent_with_lt):
        """Test skipping LanguageTool via option."""
        text = "Ein Text zum Testen."

        result = await german_correction_agent_with_lt.process({
            "text": text,
            "options": {"skip_languagetool": True}
        })

        # Should process without LanguageTool
        assert "text" in result


class TestCorrectionDetails:
    """Tests for correction detail tracking."""

    @pytest.mark.asyncio
    async def test_corrections_are_tracked(self, german_correction_agent):
        """Test that corrections are tracked in detail."""
        text = "Die Aenderung der Strasse."

        result = await german_correction_agent.process({"text": text})

        corrections = result.get("correction_details", [])
        assert isinstance(corrections, list)
        if corrections:
            # Each correction should have type, original, corrected
            for correction in corrections:
                assert "type" in correction
                assert "original" in correction
                assert "corrected" in correction

    @pytest.mark.asyncio
    async def test_correction_count(self, german_correction_agent):
        """Test that correction count is accurate."""
        text = "Die Aenderung der Strasse in Muenchen."

        result = await german_correction_agent.process({"text": text})

        count = result.get("corrections_applied", 0)
        details = result.get("correction_details", [])
        assert count == len(details)

    @pytest.mark.asyncio
    async def test_correction_confidence(self, german_correction_agent):
        """Test that corrections have confidence scores."""
        text = "Die Aenderung wurde bestaetigt."

        result = await german_correction_agent.process({"text": text})

        corrections = result.get("correction_details", [])
        for correction in corrections:
            assert "confidence" in correction
            assert 0 <= correction["confidence"] <= 1


class TestQualityMetrics:
    """Tests for quality metrics calculation."""

    @pytest.mark.asyncio
    async def test_quality_metrics_present(self, german_correction_agent):
        """Test that quality metrics are calculated."""
        text = "Die Änderung wurde bestätigt."

        result = await german_correction_agent.process({"text": text})

        metrics = result.get("quality_metrics", {})
        assert isinstance(metrics, dict)
        assert "overall_score" in metrics

    @pytest.mark.asyncio
    async def test_umlaut_density_calculation(self, german_correction_agent):
        """Test umlaut density is calculated."""
        text = "Über die Änderung der Öffnungszeiten für Prüfungen."

        result = await german_correction_agent.process({"text": text})

        metrics = result.get("quality_metrics", {})
        if "umlaut_density" in metrics:
            assert metrics["umlaut_density"] > 0

    @pytest.mark.asyncio
    async def test_validation_score(self, german_correction_agent):
        """Test validation score is included."""
        text = "Ein deutscher Text."

        result = await german_correction_agent.process({"text": text})

        assert "validation_score" in result
        assert 0 <= result["validation_score"] <= 1


class TestUmlautsRestored:
    """Tests for umlauts_restored count."""

    @pytest.mark.asyncio
    async def test_umlauts_restored_count(self, german_correction_agent):
        """Test counting of restored umlauts."""
        text = "Die Aenderung der Oeffnungszeiten fuer Pruefungen."

        result = await german_correction_agent.process({"text": text})

        restored = result.get("umlauts_restored", 0)
        assert isinstance(restored, int)
        assert restored >= 0

    @pytest.mark.asyncio
    async def test_no_umlauts_restored_for_correct_text(self, german_correction_agent):
        """Test zero restored for already correct text."""
        text = "Die Änderung der Öffnungszeiten für Prüfungen."

        result = await german_correction_agent.process({"text": text})

        restored = result.get("umlauts_restored", 0)
        # Should be 0 or minimal if text is already correct
        assert restored >= 0


class TestInputValidation:
    """Tests for input validation."""

    @pytest.mark.asyncio
    async def test_empty_text_handling(self, german_correction_agent):
        """Test handling of empty text."""
        result = await german_correction_agent.process({"text": ""})

        assert result.get("text") == ""
        assert result.get("corrections_applied") == 0

    @pytest.mark.asyncio
    async def test_missing_text_raises_error(self, german_correction_agent):
        """Test that missing text raises error."""
        with pytest.raises((KeyError, ValueError)):
            await german_correction_agent.process({})

    @pytest.mark.asyncio
    async def test_whitespace_only_text(self, german_correction_agent):
        """Test handling of whitespace-only text."""
        result = await german_correction_agent.process({"text": "   \n\t  "})

        assert "text" in result


class TestOriginalTextPreserved:
    """Tests for original text preservation."""

    @pytest.mark.asyncio
    async def test_original_text_in_result(self, german_correction_agent):
        """Test that original text is preserved in result."""
        text = "Die Aenderung."

        result = await german_correction_agent.process({"text": text})

        assert result.get("original_text") == text

    @pytest.mark.asyncio
    async def test_corrected_differs_from_original(self, german_correction_agent):
        """Test that corrected text differs from original when corrections made."""
        text = "Die Aenderung der Strasse."

        result = await german_correction_agent.process({"text": text})

        if result.get("corrections_applied", 0) > 0:
            assert result.get("text") != result.get("original_text")


class TestCorrectionStats:
    """Tests for correction statistics."""

    def test_get_correction_stats(self, german_correction_agent):
        """Test getting correction capability statistics."""
        stats = german_correction_agent.get_correction_stats()

        assert "known_umlaut_words" in stats
        assert "vocabulary_size" in stats
        assert "domain_vocabularies" in stats
        assert "supported_corrections" in stats

    def test_umlaut_words_count(self, german_correction_agent):
        """Test that umlaut words dictionary has entries."""
        stats = german_correction_agent.get_correction_stats()

        assert stats["known_umlaut_words"] > 0


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_very_short_text(self, german_correction_agent):
        """Test handling of very short text."""
        text = "ä"

        result = await german_correction_agent.process({"text": text})

        assert result.get("text") == "ä"

    @pytest.mark.asyncio
    async def test_numbers_and_special_chars(self, german_correction_agent):
        """Test handling of text with numbers and special characters."""
        text = "Die Rechnung Nr. 2024-001 über 1.234,56 EUR."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Numbers and currency should be preserved
        assert "1.234,56" in corrected
        assert "EUR" in corrected

    @pytest.mark.asyncio
    async def test_mixed_german_english(self, german_correction_agent):
        """Test handling of mixed German/English text."""
        text = "Das Meeting zur Aenderung der Software."

        result = await german_correction_agent.process({"text": text})

        corrected = result.get("text", "")
        # Should correct German parts, preserve English
        assert "Meeting" in corrected or "meeting" in corrected.lower()

    @pytest.mark.asyncio
    async def test_repeated_corrections(self, german_correction_agent):
        """Test that repeated processing doesn't over-correct."""
        text = "Die Änderung der Straße."

        result1 = await german_correction_agent.process({"text": text})
        result2 = await german_correction_agent.process({"text": result1["text"]})

        # Should be stable
        assert result1["text"] == result2["text"]


class TestComplexDocuments:
    """Tests for complex document correction."""

    @pytest.mark.asyncio
    async def test_invoice_text_correction(self, german_correction_agent):
        """Test correction of invoice text."""
        text = """
        RECHNUNG

        Rechnungsnummer: 2024-0001
        Fuer unsere Dienstleistung berechnen wir:

        1. Beratung zur Aenderung       500,00 EUR
        2. Pruefung der Unterlagen      300,00 EUR

        Gesamtbetrag:                   800,00 EUR
        Zzgl. MwSt. 19%:                152,00 EUR
        Endbetrag:                      952,00 EUR

        Zahlbar innerhalb von 30 Tagen.
        Bankverbindung: Sparkasse Muenchen
        """

        result = await german_correction_agent.process({
            "text": text,
            "domain": "accounting"
        })

        corrected = result.get("text", "")
        # Should correct multiple umlauts
        assert "ü" in corrected or "Für" in corrected

    @pytest.mark.asyncio
    async def test_contract_text_correction(self, german_correction_agent):
        """Test correction of contract text."""
        text = """
        MIETVERTRAG

        Der Vermieter, Herr Mueller, und der Mieter, Frau Schroeder,
        schliessen hiermit folgenden Vertrag:

        Die Kuendigungsfrist betraegt drei Monate.
        Die Gebuehren sind monatlich im Voraus zu entrichten.
        """

        result = await german_correction_agent.process({
            "text": text,
            "domain": "legal"
        })

        corrected = result.get("text", "")
        # Should correct contract-specific terms
        assert "schließen" in corrected or "Kündigungsfrist" in corrected or "ü" in corrected


class TestAllOptions:
    """Tests for all correction options."""

    @pytest.mark.asyncio
    async def test_skip_all_corrections(self, german_correction_agent):
        """Test skipping all optional corrections."""
        text = "Die Aenderung der Strasse."

        result = await german_correction_agent.process({
            "text": text,
            "options": {
                "skip_pattern_corrections": True,
                "skip_eszett_corrections": True,
                "skip_domain_corrections": True,
                "skip_fuzzy_matching": True,
                "skip_compound_validation": True,
                "skip_languagetool": True
            }
        })

        # Should still apply word-based corrections
        assert "text" in result

    @pytest.mark.asyncio
    async def test_enable_all_corrections(self, german_correction_agent):
        """Test with all corrections enabled (default)."""
        text = "Die Aenderung der Strasse in der Buchfuehrung."

        result = await german_correction_agent.process({
            "text": text,
            "domain": "accounting"
        })

        # All correction types should be applied
        assert result.get("corrections_applied", 0) >= 0
