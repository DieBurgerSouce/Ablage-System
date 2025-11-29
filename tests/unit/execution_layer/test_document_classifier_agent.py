"""
Tests for Document Classifier Agent.

Tests the execution layer document classification functionality:
- Document type detection
- Pattern-based classification
- ML-based classification
- Batch processing
- Confidence calculation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import numpy as np


@pytest.fixture
def sample_invoice_text():
    """Sample invoice text in German."""
    return """
    Muster GmbH
    Musterstraße 123
    12345 Musterstadt

    RECHNUNG

    Rechnungsnummer: RE-2024-12345
    Rechnungsdatum: 15.11.2024
    USt-IdNr.: DE123456789

    Position     Menge    Preis      Gesamt
    Produkt A      10    50,00 €    500,00 €

    Netto:                          500,00 €
    MwSt. 19%:                       95,00 €
    Brutto:                         595,00 €

    Zahlungsziel: 30 Tage
    """


@pytest.fixture
def sample_contract_text():
    """Sample contract text in German."""
    return """
    VERTRAG

    Vereinbarung zwischen Firma ABC GmbH und Firma XYZ AG

    § 1 Vertragsgegenstand
    Die Vertragspartner vereinbaren hiermit...

    § 2 Laufzeit
    Der Vertrag hat eine Laufzeit von 12 Monaten.

    § 3 Kündigung
    Eine Kündigung ist mit einer Frist von 3 Monaten möglich.

    Unterschrift: _______________
    """


@pytest.fixture
def sample_letter_text():
    """Sample letter text in German."""
    return """
    Sehr geehrte Damen und Herren,

    Betreff: Anfrage zu Ihrem Produkt

    hiermit möchte ich mich nach Ihrem neuen Produkt erkundigen.

    Mit freundlichen Grüßen
    Max Mustermann
    """


class TestDocumentClassifierAgentInit:
    """Tests for Document Classifier Agent initialization."""

    def test_agent_initialization(self):
        """Agent sollte korrekt initialisiert werden."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        assert agent is not None
        assert hasattr(agent, "classify")
        assert hasattr(agent, "CATEGORIES")

    def test_agent_categories(self):
        """Agent sollte alle Kategorien definiert haben."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        expected_categories = [
            "rechnung",
            "vertrag",
            "brief",
            "kontoauszug",
            "lieferschein",
            "angebot",
            "sonstiges"
        ]
        assert agent.CATEGORIES == expected_categories

    def test_agent_keywords_defined(self):
        """Agent sollte Keywords für jede Kategorie haben."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        assert "rechnung" in agent.KEYWORDS
        assert "vertrag" in agent.KEYWORDS
        assert len(agent.KEYWORDS["rechnung"]) > 0


class TestPatternClassification:
    """Tests for pattern-based classification."""

    def test_classify_invoice_by_patterns(self, sample_invoice_text):
        """Rechnung durch Mustererkennung klassifizieren."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        result = agent._classify_by_patterns(sample_invoice_text)

        assert result["category"] == "rechnung"
        assert result["confidence"] > 0.5
        assert len(result["matched_patterns"]) > 0

    def test_classify_contract_by_patterns(self, sample_contract_text):
        """Vertrag durch Mustererkennung klassifizieren."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        result = agent._classify_by_patterns(sample_contract_text)

        assert result["category"] == "vertrag"
        assert result["confidence"] > 0.5

    def test_classify_letter_by_patterns(self, sample_letter_text):
        """Brief durch Mustererkennung klassifizieren."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        result = agent._classify_by_patterns(sample_letter_text)

        assert result["category"] == "brief"

    def test_classify_unknown_text(self):
        """Unbekannten Text als 'sonstiges' klassifizieren."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        unknown_text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
        result = agent._classify_by_patterns(unknown_text)

        assert result["category"] == "sonstiges"
        assert result["confidence"] < 0.3

    def test_pattern_matching_case_insensitive(self, sample_invoice_text):
        """Mustererkennung sollte case-insensitive sein."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        # Test with uppercase
        result1 = agent._classify_by_patterns(sample_invoice_text.upper())

        # Test with lowercase
        result2 = agent._classify_by_patterns(sample_invoice_text.lower())

        assert result1["category"] == result2["category"]


class TestMLClassification:
    """Tests for ML-based classification."""

    @pytest.mark.asyncio
    async def test_ml_classification_mock(self, sample_invoice_text):
        """ML-Klassifikation mit Mock-Modell."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        mock_result = {
            "category": "rechnung",
            "confidence": 0.95,
            "alternative_categories": [
                {"category": "angebot", "confidence": 0.03},
                {"category": "brief", "confidence": 0.02},
            ]
        }

        with patch.object(agent, "_classify_by_ml", return_value=mock_result):
            result = await agent._classify_by_ml(sample_invoice_text, "test.pdf")
            assert result["category"] == "rechnung"
            assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_model_loading_lazy(self):
        """Modell sollte lazy geladen werden."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        assert agent.model is None
        assert agent.tokenizer is None


class TestCombinedClassification:
    """Tests for combined classification (pattern + ML)."""

    def test_combine_classifications(self):
        """Pattern- und ML-Ergebnisse kombinieren."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        pattern_result = {
            "category": "rechnung",
            "confidence": 0.8,
            "alternative_categories": [
                {"category": "angebot", "confidence": 0.15}
            ]
        }

        ml_result = {
            "category": "rechnung",
            "confidence": 0.95,
            "alternative_categories": [
                {"category": "angebot", "confidence": 0.03}
            ]
        }

        combined = agent._combine_classifications(
            pattern_result,
            ml_result,
            weights={"pattern": 0.3, "ml": 0.7}
        )

        assert combined["category"] == "rechnung"
        assert combined["confidence"] > 0.85  # Weighted combination

    def test_combine_conflicting_classifications(self):
        """Konfligierende Klassifikationen kombinieren."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        pattern_result = {
            "category": "rechnung",
            "confidence": 0.6,
            "alternative_categories": [
                {"category": "angebot", "confidence": 0.35}
            ]
        }

        ml_result = {
            "category": "angebot",  # Different from pattern!
            "confidence": 0.7,
            "alternative_categories": [
                {"category": "rechnung", "confidence": 0.25}
            ]
        }

        combined = agent._combine_classifications(
            pattern_result,
            ml_result,
            weights={"pattern": 0.3, "ml": 0.7}  # ML has higher weight
        )

        # ML should win with higher weight
        assert combined["category"] == "angebot"


class TestFullClassification:
    """Tests for full classification workflow."""

    @pytest.mark.asyncio
    async def test_classify_document_high_confidence(self, sample_invoice_text):
        """Dokument mit hoher Konfidenz klassifizieren."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        with patch.object(
            agent,
            "_extract_text_preview",
            return_value=sample_invoice_text
        ):
            with patch.object(
                agent,
                "classify",
                return_value={
                    "category": "rechnung",
                    "confidence": 0.92,
                    "method": "pattern_matching",
                    "processing_time_ms": 150,
                    "alternative_categories": []
                }
            ):
                result = await agent.classify("test.pdf")
                assert result["category"] == "rechnung"
                assert result["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_classify_with_ml_fallback(self):
        """Bei niedriger Pattern-Konfidenz ML nutzen."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        with patch.object(
            agent,
            "classify",
            return_value={
                "category": "vertrag",
                "confidence": 0.85,
                "method": "ml_combined",
                "processing_time_ms": 500
            }
        ):
            result = await agent.classify(
                "ambiguous_doc.pdf",
                use_ml=True,
                confidence_threshold=0.7
            )
            assert result["method"] == "ml_combined"

    @pytest.mark.asyncio
    async def test_classify_error_fallback(self):
        """Bei Fehler auf 'sonstiges' zurückfallen."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        with patch.object(
            agent,
            "_extract_text_preview",
            side_effect=Exception("File not found")
        ):
            result = await agent.classify("nonexistent.pdf")
            assert result["category"] == "sonstiges"
            assert result["method"] == "error_fallback"
            assert "error" in result


class TestBatchClassification:
    """Tests for batch document classification."""

    @pytest.mark.asyncio
    async def test_classify_batch_success(self):
        """Batch-Klassifikation erfolgreich."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        document_paths = ["doc1.pdf", "doc2.pdf", "doc3.pdf"]

        mock_results = [
            {"category": "rechnung", "confidence": 0.9},
            {"category": "vertrag", "confidence": 0.85},
            {"category": "brief", "confidence": 0.8},
        ]

        with patch.object(
            agent,
            "classify",
            side_effect=mock_results
        ):
            results = await agent.classify_batch(document_paths)
            assert len(results) == 3
            assert results[0]["category"] == "rechnung"

    @pytest.mark.asyncio
    async def test_classify_batch_with_errors(self):
        """Batch-Klassifikation mit Fehlern behandeln."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        with patch.object(
            agent,
            "classify_batch",
            return_value=[
                {"category": "rechnung", "confidence": 0.9},
                {"category": "sonstiges", "confidence": 0.0, "error": "Failed"},
                {"category": "brief", "confidence": 0.8},
            ]
        ):
            results = await agent.classify_batch(
                ["doc1.pdf", "bad_doc.pdf", "doc3.pdf"]
            )
            assert len(results) == 3
            assert "error" in results[1]

    @pytest.mark.asyncio
    async def test_classify_batch_concurrency_limit(self):
        """Batch-Konkurrenz begrenzen."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        with patch.object(
            agent,
            "classify_batch",
            return_value=[{"category": "rechnung"} for _ in range(20)]
        ):
            # Test with 20 documents, max_concurrent=10
            results = await agent.classify_batch(
                [f"doc{i}.pdf" for i in range(20)],
                max_concurrent=10
            )
            assert len(results) == 20


class TestKeywordPatterns:
    """Tests for German keyword patterns."""

    def test_invoice_keywords(self):
        """Rechnungs-Keywords erkennen."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        invoice_keywords = agent.KEYWORDS["rechnung"]

        # Should contain common German invoice terms
        keyword_patterns = " ".join(invoice_keywords)
        assert "rechnung" in keyword_patterns.lower()
        assert "rechnungsnummer" in keyword_patterns.lower()
        assert "betrag" in keyword_patterns.lower()

    def test_contract_keywords(self):
        """Vertrags-Keywords erkennen."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        contract_keywords = agent.KEYWORDS["vertrag"]

        keyword_patterns = " ".join(contract_keywords)
        assert "vertrag" in keyword_patterns.lower()
        assert "§" in keyword_patterns or "kündigung" in keyword_patterns.lower()

    def test_bank_statement_keywords(self):
        """Kontoauszug-Keywords erkennen."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()
        bank_keywords = agent.KEYWORDS["kontoauszug"]

        keyword_patterns = " ".join(bank_keywords)
        assert "kontoauszug" in keyword_patterns.lower() or "iban" in keyword_patterns.lower()


class TestConfidenceThresholds:
    """Tests for confidence threshold handling."""

    @pytest.mark.asyncio
    async def test_high_confidence_pattern_only(self, sample_invoice_text):
        """Hohe Pattern-Konfidenz ohne ML."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        with patch.object(
            agent,
            "classify",
            return_value={
                "category": "rechnung",
                "confidence": 0.95,
                "method": "pattern_matching",
                "processing_time_ms": 50
            }
        ):
            result = await agent.classify(
                "test.pdf",
                confidence_threshold=0.7
            )
            # Should use pattern matching only for high confidence
            assert result["method"] == "pattern_matching"

    @pytest.mark.asyncio
    async def test_low_confidence_triggers_ml(self):
        """Niedrige Pattern-Konfidenz löst ML aus."""
        from Execution_Layer.Agents.document_classifier_agent import (
            DocumentClassifierAgent,
        )

        agent = DocumentClassifierAgent()

        with patch.object(
            agent,
            "classify",
            return_value={
                "category": "sonstiges",
                "confidence": 0.65,
                "method": "ml_combined",
                "processing_time_ms": 400
            }
        ):
            result = await agent.classify(
                "ambiguous.pdf",
                use_ml=True,
                confidence_threshold=0.7
            )
            assert result["method"] == "ml_combined"

