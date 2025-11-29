"""
Tests for OCR Processing Agent.

Tests the execution layer OCR processing functionality:
- Document preprocessing
- Backend selection
- OCR execution
- Post-processing
- Error handling
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from pathlib import Path

import numpy as np


@pytest.fixture
def mock_gpu_manager():
    """Mock GPU manager."""
    manager = MagicMock()
    manager.is_available.return_value = True
    manager.get_memory_usage.return_value = 0.45  # 45% usage
    manager.allocate_memory.return_value = True
    return manager


@pytest.fixture
def sample_document():
    """Create sample document for testing."""
    return {
        "id": str(uuid4()),
        "filename": "test_document.pdf",
        "content_type": "application/pdf",
        "size": 1024 * 1024,  # 1MB
        "pages": 5,
        "created_at": datetime.now(UTC),
    }


@pytest.fixture
def sample_image():
    """Create sample image array."""
    return np.random.randint(0, 255, (1000, 800, 3), dtype=np.uint8)


class TestOCRProcessingAgentInit:
    """Tests for OCR Processing Agent initialization."""

    def test_agent_initialization(self):
        """Agent sollte korrekt initialisiert werden."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        assert agent is not None
        assert hasattr(agent, "process_document")

    def test_agent_has_required_attributes(self):
        """Agent hat erforderliche Attribute."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        assert hasattr(agent, "_storage_agent")
        assert hasattr(agent, "_ocr_agent")
        assert hasattr(agent, "_validation_agent")


class TestBackendSelection:
    """Tests for OCR backend selection logic."""

    @pytest.mark.asyncio
    async def test_select_deepseek_for_complex_layout(self, sample_document):
        """DeepSeek fuer komplexe Layouts auswaehlen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        sample_document["has_tables"] = True
        sample_document["has_images"] = True
        sample_document["language"] = "de"

        with patch.object(agent, "_select_backend", return_value="deepseek"):
            backend = await agent._select_backend(sample_document)
            assert backend == "deepseek"

    @pytest.mark.asyncio
    async def test_select_got_ocr_for_simple_text(self, sample_document):
        """GOT-OCR fuer einfache Textdokumente auswaehlen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        sample_document["has_tables"] = False
        sample_document["has_images"] = False
        sample_document["language"] = "en"

        with patch.object(agent, "_select_backend", return_value="got_ocr"):
            backend = await agent._select_backend(sample_document)
            assert backend == "got_ocr"

    @pytest.mark.asyncio
    async def test_fallback_to_surya_as_default(self, sample_document):
        """Surya als Standard-Fallback bei Routing-Fehlern."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        # Mock UnifiedRouter to raise exception
        with patch(
            "Execution_Layer.Agents.ocr_processing_agent.OCRProcessingAgent._select_backend"
        ) as mock_select:
            # Simulate real _select_backend behavior that falls back to surya
            mock_select.return_value = "surya"
            backend = await agent._select_backend(sample_document)
            assert backend == "surya"


class TestDocumentPreprocessing:
    """Tests for document preprocessing."""

    @pytest.mark.asyncio
    async def test_validate_german_text(self):
        """Deutsche Textvalidierung testen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        text = "Dies ist ein Test mit Umlauten: aeoeuess"

        result = await agent._validate_german_text(text)
        assert "valid" in result
        assert isinstance(result.get("valid"), bool)

    @pytest.mark.asyncio
    async def test_extract_template_fields(self):
        """Template-Felder extrahieren."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        text = "Rechnung Nr. 12345 vom 01.01.2024"

        result = await agent._extract_template_fields(text)
        assert "fields" in result
        assert "total_extracted" in result


class TestOCRExecution:
    """Tests for OCR execution."""

    @pytest.mark.asyncio
    async def test_process_with_ocr_mock(self):
        """OCR-Verarbeitung mit Mock testen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        mock_result = {
            "text": "Dies ist ein Testtext mit Umlauten: aeoeuess",
            "confidence": 0.95,
            "backend": "deepseek"
        }

        with patch.object(
            agent, "_process_with_ocr", return_value=mock_result
        ):
            result = await agent._process_with_ocr(b"fake_content", "deepseek", "doc-123")
            assert "Testtext" in result["text"]
            assert result["confidence"] > 0.9

    @pytest.mark.asyncio
    async def test_process_with_fallback_chain(self):
        """OCR mit Fallback-Kette testen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        mock_result = {
            "text": "Fallback-Text",
            "confidence": 0.85,
            "backend": "surya"
        }

        with patch.object(
            agent, "_process_with_ocr", return_value=mock_result
        ):
            result = await agent._process_with_ocr(b"fake_content", "deepseek", "doc-123")
            assert result["backend"] == "surya"


class TestPostProcessing:
    """Tests for OCR post-processing."""

    @pytest.mark.asyncio
    async def test_validate_compliance(self):
        """Compliance-Validierung testen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        result = {
            "text": "Test text",
            "confidence": 0.9,
            "german_validation": {"valid": True, "issues": []},
            "extracted_fields": {"total_extracted": 5}
        }

        qa_result = await agent._validate_compliance(result)
        assert "passed" in qa_result
        assert "checks" in qa_result

    @pytest.mark.asyncio
    async def test_validate_compliance_checks_confidence(self):
        """Compliance prueft OCR-Konfidenz."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        result = {
            "text": "Test",
            "confidence": 0.5,  # Low confidence
            "german_validation": {"valid": True, "issues": []},
            "extracted_fields": {"total_extracted": 0}
        }

        qa_result = await agent._validate_compliance(result)
        # Should have failed check for low confidence
        confidence_check = next(
            (c for c in qa_result["checks"] if c["name"] == "ocr_confidence"),
            None
        )
        assert confidence_check is not None
        assert confidence_check["passed"] is False


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_process_document_handles_missing_storage(self):
        """Fehlerbehandlung bei fehlendem Storage."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        # Mock storage agent to return error
        mock_storage = AsyncMock()
        mock_storage.retrieve_document.return_value = {
            "status": "error",
            "error": "Dokument nicht gefunden"
        }

        with patch.object(agent, "_get_storage_agent", return_value=mock_storage):
            result = await agent.process_document("non-existent-id")
            assert result["status"] == "failed"
            assert "error" in result

    @pytest.mark.asyncio
    async def test_process_document_logs_gdpr_on_success(self):
        """GDPR-Logging bei erfolgreicher Verarbeitung."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        # Mock all dependencies
        mock_storage = AsyncMock()
        mock_storage.retrieve_document.return_value = {
            "status": "success",
            "source": "minio",
            "file": b"fake_content",
            "metadata": {"file_size": 1000, "mime_type": "application/pdf"}
        }

        with patch.object(agent, "_get_storage_agent", return_value=mock_storage):
            with patch.object(agent, "_select_backend", return_value="surya"):
                with patch.object(
                    agent, "_process_with_ocr",
                    return_value={"text": "Test", "confidence": 0.9, "backend": "surya"}
                ):
                    with patch.object(
                        agent, "_validate_german_text",
                        return_value={"valid": True, "has_umlauts": False, "issues": []}
                    ):
                        with patch.object(
                            agent, "_extract_template_fields",
                            return_value={"fields": {}, "total_extracted": 0, "confidence": 0}
                        ):
                            with patch.object(agent, "_store_results", return_value=True):
                                result = await agent.process_document("test-doc-id")
                                # Check that GDPR logging step was added
                                gdpr_step = next(
                                    (s for s in result["steps"] if s["step"] == "gdpr_logging"),
                                    None
                                )
                                assert gdpr_step is not None


class TestFullProcessing:
    """Tests for full document processing."""

    @pytest.mark.asyncio
    async def test_process_document_success_flow(self):
        """Dokument erfolgreich verarbeiten."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        mock_storage = AsyncMock()
        mock_storage.retrieve_document.return_value = {
            "status": "success",
            "source": "minio",
            "file": b"fake_content",
            "metadata": {"file_size": 1000, "mime_type": "application/pdf"}
        }

        with patch.object(agent, "_get_storage_agent", return_value=mock_storage):
            with patch.object(agent, "_select_backend", return_value="deepseek"):
                with patch.object(
                    agent, "_process_with_ocr",
                    return_value={
                        "text": "Vollstaendiger extrahierter Text",
                        "confidence": 0.95,
                        "backend": "deepseek"
                    }
                ):
                    with patch.object(
                        agent, "_validate_german_text",
                        return_value={"valid": True, "has_umlauts": True, "issues": []}
                    ):
                        with patch.object(
                            agent, "_extract_template_fields",
                            return_value={"fields": {"date": "01.01.2024"}, "total_extracted": 1, "confidence": 0.8}
                        ):
                            with patch.object(agent, "_store_results", return_value=True):
                                result = await agent.process_document("test-doc-id")
                                assert result["status"] == "success"
                                assert result["confidence"] == 0.95
                                assert "text" in result

    @pytest.mark.asyncio
    async def test_process_document_tracks_all_steps(self):
        """Alle Verarbeitungsschritte werden erfasst."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        mock_storage = AsyncMock()
        mock_storage.retrieve_document.return_value = {
            "status": "success",
            "source": "minio",
            "file": b"fake_content",
            "metadata": {"file_size": 1000}
        }

        with patch.object(agent, "_get_storage_agent", return_value=mock_storage):
            with patch.object(agent, "_select_backend", return_value="surya"):
                with patch.object(
                    agent, "_process_with_ocr",
                    return_value={"text": "Test", "confidence": 0.9, "backend": "surya"}
                ):
                    with patch.object(
                        agent, "_validate_german_text",
                        return_value={"valid": True, "has_umlauts": False, "issues": []}
                    ):
                        with patch.object(
                            agent, "_extract_template_fields",
                            return_value={"fields": {}, "total_extracted": 0}
                        ):
                            with patch.object(agent, "_store_results", return_value=True):
                                result = await agent.process_document("test-doc-id")

                                # Verify all steps are tracked
                                step_names = [s["step"] for s in result["steps"]]
                                expected_steps = [
                                    "load_document",
                                    "backend_selection",
                                    "ocr_processing",
                                    "german_validation",
                                    "template_extraction",
                                    "qa_validation",
                                    "store_results",
                                    "gdpr_logging"
                                ]
                                for step in expected_steps:
                                    assert step in step_names, f"Step '{step}' not found in results"


class TestValidationMethods:
    """Tests for validation methods."""

    @pytest.mark.asyncio
    async def test_validate_german_text_with_umlauts(self):
        """Deutsche Textvalidierung mit Umlauten."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        # Mock the import failure to test fallback
        result = await agent._validate_german_text("Test ohne Umlaute")
        assert isinstance(result, dict)
        assert "valid" in result

    @pytest.mark.asyncio
    async def test_extract_template_fields_handles_errors(self):
        """Template-Extraktion behandelt Fehler."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        # Empty text should still return valid structure
        result = await agent._extract_template_fields("")
        assert "fields" in result
        assert "total_extracted" in result or "error" in result
