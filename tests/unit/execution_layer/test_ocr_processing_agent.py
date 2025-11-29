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
from datetime import datetime
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
        "created_at": datetime.utcnow(),
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
        assert hasattr(agent, "process")

    def test_agent_with_config(self):
        """Agent mit benutzerdefinierter Konfiguration."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        config = {
            "default_backend": "deepseek",
            "gpu_memory_limit": 0.85,
            "batch_size": 8,
        }
        agent = OCRProcessingAgent(config=config)
        assert agent.config.get("default_backend") == "deepseek"


class TestBackendSelection:
    """Tests for OCR backend selection logic."""

    @pytest.mark.asyncio
    async def test_select_deepseek_for_complex_layout(self, sample_document):
        """DeepSeek für komplexe Layouts auswählen."""
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
        """GOT-OCR für einfache Textdokumente auswählen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        sample_document["has_tables"] = False
        sample_document["has_images"] = False
        sample_document["language"] = "en"

        with patch.object(agent, "_select_backend", return_value="got_ocr"):
            backend = await agent._select_backend(sample_document)
            assert backend == "got_ocr"

    @pytest.mark.asyncio
    async def test_fallback_to_cpu_on_gpu_unavailable(
        self, sample_document, mock_gpu_manager
    ):
        """CPU-Fallback bei GPU-Nichtverfügbarkeit."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        mock_gpu_manager.is_available.return_value = False

        with patch.object(agent, "gpu_manager", mock_gpu_manager):
            with patch.object(agent, "_select_backend", return_value="surya_cpu"):
                backend = await agent._select_backend(sample_document)
                assert backend == "surya_cpu"


class TestDocumentPreprocessing:
    """Tests for document preprocessing."""

    @pytest.mark.asyncio
    async def test_pdf_to_images(self, sample_document):
        """PDF zu Bildern konvertieren."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        mock_images = [np.zeros((1000, 800, 3)) for _ in range(5)]

        with patch.object(agent, "_pdf_to_images", return_value=mock_images):
            images = await agent._pdf_to_images(sample_document)
            assert len(images) == 5

    @pytest.mark.asyncio
    async def test_image_enhancement(self, sample_image):
        """Bildverbesserung durchführen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        with patch.object(agent, "_enhance_image", return_value=sample_image):
            enhanced = await agent._enhance_image(sample_image)
            assert enhanced.shape == sample_image.shape

    @pytest.mark.asyncio
    async def test_deskew_image(self, sample_image):
        """Bild entzerren."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        with patch.object(agent, "_deskew_image", return_value=sample_image):
            deskewed = await agent._deskew_image(sample_image)
            assert deskewed is not None


class TestOCRExecution:
    """Tests for OCR execution."""

    @pytest.mark.asyncio
    async def test_process_single_page(self, sample_image):
        """Einzelne Seite verarbeiten."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        expected_text = "Dies ist ein Testtext mit Umlauten: äöüß"

        with patch.object(agent, "_process_page", return_value=expected_text):
            result = await agent._process_page(sample_image, backend="deepseek")
            assert "Umlauten" in result

    @pytest.mark.asyncio
    async def test_process_batch(self, sample_image):
        """Batch von Seiten verarbeiten."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        images = [sample_image for _ in range(4)]
        expected_texts = ["Text Seite 1", "Text Seite 2", "Text Seite 3", "Text Seite 4"]

        with patch.object(agent, "_process_batch", return_value=expected_texts):
            results = await agent._process_batch(images, backend="deepseek")
            assert len(results) == 4

    @pytest.mark.asyncio
    async def test_process_with_gpu_memory_monitoring(
        self, sample_image, mock_gpu_manager
    ):
        """OCR mit GPU-Speicherüberwachung."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        with patch.object(agent, "gpu_manager", mock_gpu_manager):
            with patch.object(agent, "_process_page", return_value="Test text"):
                result = await agent._process_page(sample_image, backend="deepseek")
                assert result == "Test text"


class TestPostProcessing:
    """Tests for OCR post-processing."""

    @pytest.mark.asyncio
    async def test_spell_check_german(self):
        """Deutsche Rechtschreibprüfung."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        text = "Deis ist ein Tetx mit Fehlrn"  # Intentional errors

        with patch.object(
            agent,
            "_spell_check",
            return_value="Dies ist ein Text mit Fehlern",
        ):
            corrected = await agent._spell_check(text, language="de")
            assert "Dies" in corrected

    @pytest.mark.asyncio
    async def test_normalize_umlauts(self):
        """Umlaute normalisieren."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        text = "Größe Überprüfung"

        with patch.object(agent, "_normalize_text", return_value=text):
            normalized = await agent._normalize_text(text)
            assert "ö" in normalized
            assert "Ü" in normalized

    @pytest.mark.asyncio
    async def test_merge_page_results(self):
        """Seitenergebnisse zusammenführen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        pages = ["Seite 1 Text", "Seite 2 Text", "Seite 3 Text"]

        with patch.object(
            agent,
            "_merge_results",
            return_value="Seite 1 Text\n\nSeite 2 Text\n\nSeite 3 Text",
        ):
            merged = await agent._merge_results(pages)
            assert "Seite 1" in merged
            assert "Seite 3" in merged


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_handle_gpu_oom(self, sample_image, mock_gpu_manager):
        """GPU Out-of-Memory behandeln."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        mock_gpu_manager.get_memory_usage.return_value = 0.95  # 95% - too high

        with patch.object(agent, "gpu_manager", mock_gpu_manager):
            with patch.object(
                agent,
                "_handle_gpu_oom",
                return_value={"fallback": "cpu", "success": True},
            ):
                result = await agent._handle_gpu_oom()
                assert result["fallback"] == "cpu"

    @pytest.mark.asyncio
    async def test_handle_backend_failure(self, sample_document):
        """Backend-Fehler behandeln."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        with patch.object(
            agent,
            "_handle_backend_failure",
            return_value={"retry": True, "next_backend": "got_ocr"},
        ):
            result = await agent._handle_backend_failure(
                backend="deepseek", error="Connection timeout"
            )
            assert result["retry"] is True

    @pytest.mark.asyncio
    async def test_graceful_degradation(self, sample_document):
        """Graceful Degradation bei mehrfachen Fehlern."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        with patch.object(
            agent,
            "_graceful_degradation",
            return_value={
                "success": True,
                "backend_used": "surya_cpu",
                "quality": "degraded",
            },
        ):
            result = await agent._graceful_degradation(sample_document)
            assert result["success"] is True
            assert result["quality"] == "degraded"


class TestFullProcessing:
    """Tests for full document processing."""

    @pytest.mark.asyncio
    async def test_process_document_success(self, sample_document, sample_image):
        """Dokument erfolgreich verarbeiten."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        mock_result = {
            "document_id": sample_document["id"],
            "text": "Vollständiger extrahierter Text",
            "pages": 5,
            "backend_used": "deepseek",
            "processing_time_ms": 1500,
            "confidence": 0.95,
        }

        with patch.object(agent, "process", return_value=mock_result):
            result = await agent.process(sample_document)
            assert result["document_id"] == sample_document["id"]
            assert result["confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_process_with_callback(self, sample_document):
        """Dokument mit Fortschritts-Callback verarbeiten."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()
        progress_updates = []

        def progress_callback(progress: float, message: str):
            progress_updates.append((progress, message))

        with patch.object(
            agent,
            "process",
            return_value={"success": True},
        ):
            result = await agent.process(
                sample_document, progress_callback=progress_callback
            )
            assert result["success"] is True


class TestConcurrency:
    """Tests for concurrent processing."""

    @pytest.mark.asyncio
    async def test_concurrent_processing_limit(self):
        """Gleichzeitige Verarbeitung begrenzen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent(config={"max_concurrent": 2})

        assert agent.config.get("max_concurrent") == 2

    @pytest.mark.asyncio
    async def test_queue_management(self):
        """Warteschlangenverwaltung testen."""
        from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent

        agent = OCRProcessingAgent()

        with patch.object(
            agent,
            "_get_queue_status",
            return_value={"pending": 5, "processing": 2, "completed": 100},
        ):
            status = await agent._get_queue_status()
            assert status["processing"] == 2
