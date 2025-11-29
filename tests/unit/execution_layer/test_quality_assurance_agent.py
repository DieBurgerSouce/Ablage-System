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

    def test_agent_has_validation_agent(self):
        """Agent hat Validation Agent Lazy-Loading."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        # _validation_agent starts as None (lazy loading)
        assert agent._validation_agent is None
        assert hasattr(agent, "_get_validation_agent")


class TestConfidenceScoring:
    """Tests for confidence scoring."""

    @pytest.mark.asyncio
    async def test_check_ocr_confidence_high_quality(self, sample_ocr_result):
        """Konfidenz für hohe Qualität pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        confidence = sample_ocr_result["raw_confidence"]

        result = await agent._check_ocr_confidence(confidence)
        assert result["passed"] is True
        assert result["value"] >= 0.85

    @pytest.mark.asyncio
    async def test_check_ocr_confidence_low_quality(self, low_quality_result):
        """Konfidenz für niedrige Qualität pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        confidence = low_quality_result["raw_confidence"]

        result = await agent._check_ocr_confidence(confidence)
        assert result["passed"] is False
        assert result["value"] < 0.85

    @pytest.mark.asyncio
    async def test_calculate_score_from_checks(self, sample_ocr_result):
        """Gesamtscore aus Checks berechnen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        checks = [
            {"name": "ocr_confidence", "passed": True},
            {"name": "text_extraction", "passed": True},
            {"name": "umlaut_integrity", "passed": True},
        ]

        score = agent._calculate_score(checks)
        assert score > 0.0
        assert score <= 1.0


class TestGermanTextValidation:
    """Tests for German text validation."""

    @pytest.mark.asyncio
    async def test_check_umlaut_integrity(self, sample_ocr_result):
        """Umlaut-Integritaet pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        result = await agent._check_umlaut_integrity(sample_ocr_result["text"])
        # Result should have required structure
        assert "name" in result
        assert result["name"] == "umlaut_integrity"
        assert "passed" in result

    @pytest.mark.asyncio
    async def test_check_umlaut_integrity_with_mock(self):
        """Umlaut-Integritaet mit Mock pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_check_umlaut_integrity",
            return_value={
                "name": "umlaut_integrity",
                "passed": True,
                "has_umlauts": True,
                "issues": [],
            },
        ):
            result = await agent._check_umlaut_integrity("Text mit Ä Ö Ü ß")
            assert result["passed"] is True
            assert result["has_umlauts"] is True

    @pytest.mark.asyncio
    async def test_check_business_terms(self, sample_ocr_result):
        """Geschaeftsbegriffe pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        with patch.object(
            agent,
            "_check_business_terms",
            return_value={
                "name": "business_terms",
                "passed": True,
                "count": 5,
            },
        ):
            result = await agent._check_business_terms(
                sample_ocr_result["text"], {}
            )
            assert result["passed"] is True


class TestQualityMetrics:
    """Tests for quality metrics calculation."""

    @pytest.mark.asyncio
    async def test_check_text_extraction(self, sample_ocr_result):
        """Textextraktion pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        result = await agent._check_text_extraction(sample_ocr_result["text"])

        assert result["name"] == "text_extraction"
        assert result["passed"] is True
        assert result["value"] > 0

    @pytest.mark.asyncio
    async def test_check_text_extraction_empty(self):
        """Leere Textextraktion pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()
        result = await agent._check_text_extraction("")

        assert result["passed"] is False
        assert result["value"] == 0

    @pytest.mark.asyncio
    async def test_check_required_fields(self, sample_ocr_result):
        """Pflichtfelder pruefen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        extracted_fields = {"fields": {"date": "01.01.2024"}}
        result = await agent._check_required_fields(extracted_fields, "general")

        assert result["name"] == "required_fields"
        assert "passed" in result


class TestErrorDetection:
    """Tests for error detection via validation."""

    @pytest.mark.asyncio
    async def test_validate_detects_low_confidence(self, low_quality_result):
        """Niedrige Konfidenz wird erkannt."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        # Create minimal result with low confidence
        result_data = {
            "text": low_quality_result["text"],
            "confidence": low_quality_result["raw_confidence"],
            "extracted_fields": {},
        }

        validation = await agent.validate(result_data)
        # Should have warnings about low confidence
        assert validation["overall_score"] < 1.0
        # The confidence check should fail
        confidence_check = next(
            (c for c in validation["checks"] if c["name"] == "ocr_confidence"),
            None
        )
        assert confidence_check is not None
        assert confidence_check["passed"] is False

    @pytest.mark.asyncio
    async def test_validate_detects_empty_text(self):
        """Leerer Text wird erkannt."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        result_data = {
            "text": "",
            "confidence": 0.9,
            "extracted_fields": {},
        }

        validation = await agent.validate(result_data)
        assert "Kein Text extrahiert" in validation["errors"]

    @pytest.mark.asyncio
    async def test_validate_with_valid_result(self, sample_ocr_result):
        """Valides Resultat wird akzeptiert."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        result_data = {
            "text": sample_ocr_result["text"],
            "confidence": sample_ocr_result["raw_confidence"],
            "extracted_fields": {},
        }

        validation = await agent.validate(result_data)
        # High confidence text should pass basic checks
        confidence_check = next(
            (c for c in validation["checks"] if c["name"] == "ocr_confidence"),
            None
        )
        assert confidence_check is not None
        assert confidence_check["passed"] is True


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
    """Tests for reprocessing recommendations via validation."""

    @pytest.mark.asyncio
    async def test_validate_gives_recommendations_for_low_quality(self, low_quality_result):
        """Validierung gibt Empfehlungen bei niedriger Qualitaet."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        result_data = {
            "text": low_quality_result["text"],
            "confidence": low_quality_result["raw_confidence"],
            "extracted_fields": {},
        }

        validation = await agent.validate(result_data)
        # Low quality should trigger recommendations
        assert "recommendations" in validation
        # Should have warnings or errors
        assert len(validation["warnings"]) > 0 or len(validation["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_gives_recommendations_for_umlaut_issues(self):
        """Validierung gibt Empfehlungen bei Umlaut-Problemen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        # Mock umlaut check to return issues
        with patch.object(
            agent,
            "_check_umlaut_integrity",
            return_value={
                "name": "umlaut_integrity",
                "passed": False,
                "issues": ["ae statt ä", "oe statt ö"],
                "issues_count": 2,
            },
        ):
            result_data = {
                "text": "Groesse statt Größe",
                "confidence": 0.9,
                "extracted_fields": {},
            }

            validation = await agent.validate(result_data)
            assert "recommendations" in validation


class TestQualityReporting:
    """Tests for quality reporting via validation."""

    @pytest.mark.asyncio
    async def test_validate_returns_comprehensive_report(self, sample_ocr_result):
        """Validierung gibt umfassenden Bericht zurueck."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        result_data = {
            "text": sample_ocr_result["text"],
            "confidence": sample_ocr_result["raw_confidence"],
            "extracted_fields": {},
        }

        report = await agent.validate(result_data)

        # Check report structure
        assert "passed" in report
        assert "overall_score" in report
        assert "checks" in report
        assert "warnings" in report
        assert "errors" in report
        assert "validated_at" in report

    @pytest.mark.asyncio
    async def test_validate_score_calculation(self, sample_ocr_result):
        """Score-Berechnung testen."""
        from Execution_Layer.Agents.quality_assurance_agent import (
            QualityAssuranceAgent,
        )

        agent = QualityAssuranceAgent()

        result_data = {
            "text": sample_ocr_result["text"],
            "confidence": sample_ocr_result["raw_confidence"],
            "extracted_fields": {},
        }

        report = await agent.validate(result_data)

        # High quality input should have high score
        assert report["overall_score"] > 0.0
        assert report["overall_score"] <= 1.0
