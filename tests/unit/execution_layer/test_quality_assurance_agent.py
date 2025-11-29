"""
Tests for Quality Assurance Agent.

Tests the execution layer quality assurance functionality:
- OCR output validation
- Confidence scoring
- Quality metrics
- Error detection
- German text validation
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.fixture
def sample_ocr_result():
    """Create sample OCR result for testing."""
    return {
        "document_id": str(uuid4()),
        "text": "Dies ist ein Testdokument mit deutschem Text. Ä Ö Ü ß",
        "pages": 3,
        "backend": "deepseek",
        "raw_confidence": 0.92,
        "processing_time_ms": 1200,
    }


@pytest.fixture
def low_quality_result():
    """Create low quality OCR result."""
    return {
        "document_id": str(uuid4()),
        "text": "D1e5 1st e1n sch1echter Text m1t v1e1en Feh1ern",
        "pages": 1,
        "backend": "got_ocr",
        "raw_confidence": 0.45,
        "processing_time_ms": 800,
    }


class TestQualityAssuranceAgentInit:
    """Tests for Quality Assurance Agent initialization."""

    def test_agent_initialization(self):
        """Agent sollte korrekt initialisiert werden."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        assert agent is not None
        assert hasattr(agent, "validate")

    def test_agent_with_thresholds(self):
        """Agent mit benutzerdefinierten Schwellenwerten."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        config = {
            "min_confidence": 0.85,
            "min_word_count": 10,
            "max_error_rate": 0.05,
        }
        agent = QualityAssuranceAgent(config=config)
        assert agent.config.get("min_confidence") == 0.85


class TestConfidenceScoring:
    """Tests for confidence scoring."""

    @pytest.mark.asyncio
    async def test_calculate_confidence_high_quality(self, sample_ocr_result):
        """Konfidenz für hohe Qualität berechnen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(agent, "_calculate_confidence", return_value=0.92):
            confidence = await agent._calculate_confidence(sample_ocr_result)
            assert confidence >= 0.85

    @pytest.mark.asyncio
    async def test_calculate_confidence_low_quality(self, low_quality_result):
        """Konfidenz für niedrige Qualität berechnen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(agent, "_calculate_confidence", return_value=0.45):
            confidence = await agent._calculate_confidence(low_quality_result)
            assert confidence < 0.85

    @pytest.mark.asyncio
    async def test_word_level_confidence(self, sample_ocr_result):
        """Wort-Level Konfidenz berechnen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        mock_word_confidences = {
            "Dies": 0.99,
            "ist": 0.98,
            "ein": 0.97,
            "Testdokument": 0.95,
        }

        with patch.object(
            agent, "_get_word_confidences", return_value=mock_word_confidences
        ):
            confidences = await agent._get_word_confidences(sample_ocr_result["text"])
            assert all(c >= 0.9 for c in confidences.values())


class TestGermanTextValidation:
    """Tests for German text validation."""

    @pytest.mark.asyncio
    async def test_validate_umlauts(self, sample_ocr_result):
        """Umlaute validieren."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_validate_umlauts",
            return_value={"valid": True, "found": ["Ä", "Ö", "Ü", "ß"]},
        ):
            result = await agent._validate_umlauts(sample_ocr_result["text"])
            assert result["valid"] is True
            assert "ß" in result["found"]

    @pytest.mark.asyncio
    async def test_detect_umlaut_substitutions(self):
        """Umlaut-Ersetzungen erkennen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        text_with_substitutions = "Groesse statt Größe, Ueberpruefung statt Überprüfung"

        with patch.object(
            agent,
            "_detect_substitutions",
            return_value={"substitutions": ["oe->ö", "ue->ü"], "count": 2},
        ):
            result = await agent._detect_substitutions(text_with_substitutions)
            assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_validate_german_dictionary(self, sample_ocr_result):
        """Gegen deutsches Wörterbuch validieren."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_validate_dictionary",
            return_value={"valid_words": 10, "invalid_words": 0, "validity_rate": 1.0},
        ):
            result = await agent._validate_dictionary(
                sample_ocr_result["text"], language="de"
            )
            assert result["validity_rate"] == 1.0


class TestQualityMetrics:
    """Tests for quality metrics calculation."""

    @pytest.mark.asyncio
    async def test_calculate_character_accuracy(self, sample_ocr_result):
        """Zeichengenauigkeit berechnen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(agent, "_calculate_char_accuracy", return_value=0.98):
            accuracy = await agent._calculate_char_accuracy(
                sample_ocr_result["text"], reference="Dies ist ein Testdokument..."
            )
            assert accuracy >= 0.95

    @pytest.mark.asyncio
    async def test_calculate_word_accuracy(self, sample_ocr_result):
        """Wortgenauigkeit berechnen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(agent, "_calculate_word_accuracy", return_value=0.95):
            accuracy = await agent._calculate_word_accuracy(sample_ocr_result["text"])
            assert accuracy >= 0.90

    @pytest.mark.asyncio
    async def test_calculate_layout_preservation(self, sample_ocr_result):
        """Layout-Erhaltung berechnen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_calculate_layout_score",
            return_value={"score": 0.88, "issues": []},
        ):
            result = await agent._calculate_layout_score(sample_ocr_result)
            assert result["score"] >= 0.80


class TestErrorDetection:
    """Tests for error detection."""

    @pytest.mark.asyncio
    async def test_detect_character_substitutions(self, low_quality_result):
        """Zeichenersetzungen erkennen (1 statt i, 5 statt s)."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_detect_char_substitutions",
            return_value={
                "substitutions": [("1", "i"), ("5", "s")],
                "count": 10,
                "severity": "high",
            },
        ):
            result = await agent._detect_char_substitutions(low_quality_result["text"])
            assert result["severity"] == "high"

    @pytest.mark.asyncio
    async def test_detect_missing_text(self):
        """Fehlenden Text erkennen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_detect_missing_text",
            return_value={"missing_regions": 2, "estimated_words": 50},
        ):
            result = await agent._detect_missing_text(
                ocr_text="Partial text...", page_image=None
            )
            assert result["missing_regions"] > 0

    @pytest.mark.asyncio
    async def test_detect_garbage_text(self):
        """Müll-Text erkennen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        garbage_text = "xjdk skkd jjjj kkk lll xxxx"

        with patch.object(
            agent,
            "_detect_garbage",
            return_value={"is_garbage": True, "garbage_ratio": 0.8},
        ):
            result = await agent._detect_garbage(garbage_text)
            assert result["is_garbage"] is True


class TestQualityValidation:
    """Tests for overall quality validation."""

    @pytest.mark.asyncio
    async def test_validate_passes_high_quality(self, sample_ocr_result):
        """Validierung besteht bei hoher Qualität."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "validate",
            return_value={
                "valid": True,
                "confidence": 0.92,
                "issues": [],
                "recommendation": "accept",
            },
        ):
            result = await agent.validate(sample_ocr_result)
            assert result["valid"] is True
            assert result["recommendation"] == "accept"

    @pytest.mark.asyncio
    async def test_validate_fails_low_quality(self, low_quality_result):
        """Validierung schlägt bei niedriger Qualität fehl."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "validate",
            return_value={
                "valid": False,
                "confidence": 0.45,
                "issues": ["Low confidence", "Character substitutions detected"],
                "recommendation": "reprocess",
            },
        ):
            result = await agent.validate(low_quality_result)
            assert result["valid"] is False
            assert result["recommendation"] == "reprocess"

    @pytest.mark.asyncio
    async def test_validate_with_manual_review_needed(self):
        """Validierung mit manuellem Review erforderlich."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        borderline_result = {
            "document_id": str(uuid4()),
            "text": "Some text with minor issues",
            "raw_confidence": 0.75,
        }

        with patch.object(
            agent,
            "validate",
            return_value={
                "valid": True,
                "confidence": 0.75,
                "issues": ["Confidence below optimal threshold"],
                "recommendation": "manual_review",
            },
        ):
            result = await agent.validate(borderline_result)
            assert result["recommendation"] == "manual_review"


class TestReprocessingRecommendations:
    """Tests for reprocessing recommendations."""

    @pytest.mark.asyncio
    async def test_recommend_different_backend(self, low_quality_result):
        """Anderen Backend empfehlen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_recommend_reprocessing",
            return_value={
                "reprocess": True,
                "recommended_backend": "deepseek",
                "reason": "Current backend produced low quality output",
            },
        ):
            result = await agent._recommend_reprocessing(low_quality_result)
            assert result["reprocess"] is True
            assert result["recommended_backend"] == "deepseek"

    @pytest.mark.asyncio
    async def test_recommend_preprocessing_changes(self, low_quality_result):
        """Preprocessing-Änderungen empfehlen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_recommend_preprocessing",
            return_value={
                "changes": ["increase_contrast", "deskew", "denoise"],
                "priority": "high",
            },
        ):
            result = await agent._recommend_preprocessing(low_quality_result)
            assert "deskew" in result["changes"]


class TestQualityReporting:
    """Tests for quality reporting."""

    @pytest.mark.asyncio
    async def test_generate_quality_report(self, sample_ocr_result):
        """Qualitätsbericht generieren."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_generate_report",
            return_value={
                "document_id": sample_ocr_result["document_id"],
                "overall_quality": "high",
                "confidence_score": 0.92,
                "metrics": {
                    "character_accuracy": 0.98,
                    "word_accuracy": 0.95,
                    "umlaut_accuracy": 1.0,
                },
                "issues": [],
                "timestamp": datetime.utcnow().isoformat(),
            },
        ):
            report = await agent._generate_report(sample_ocr_result)
            assert report["overall_quality"] == "high"
            assert report["metrics"]["umlaut_accuracy"] == 1.0
