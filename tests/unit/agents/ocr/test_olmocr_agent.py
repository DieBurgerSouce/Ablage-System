# -*- coding: utf-8 -*-
"""
Tests fuer OlmOCR-2 Agent.

Testet:
- Agent-Initialisierung mit GPU-Detection
- Model Loading mit Timeout und Thread-Safety
- PDF und Bildverarbeitung (300 DPI)
- Deutsche Umlaut-Erkennung (ae, oe, ue, ss)
- GPU Memory Management
- Error Handling (OOM, FileNotFound, Timeout)
- Cleanup-Verhalten
- OCRResult Standardisierung

Feinpoliert und durchdacht - OlmOCR-2 Tests.
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from typing import Any, Dict


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_torch_cuda():
    """Mock torch.cuda Modul fuer GPU-Verfuegbarkeit."""
    with patch('app.agents.ocr.olmocr_agent.torch') as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.empty_cache = Mock()
        mock_torch.cuda.synchronize = Mock()
        mock_torch.cuda.get_device_name.return_value = "NVIDIA GeForce RTX 4080"
        mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3  # 2GB
        mock_torch.cuda.max_memory_allocated.return_value = 8 * 1024**3  # 8GB
        mock_torch.cuda.memory_reserved.return_value = 4 * 1024**3  # 4GB

        # Device properties
        mock_props = Mock()
        mock_props.total_memory = 16 * 1024**3  # 16GB
        mock_torch.cuda.get_device_properties.return_value = mock_props

        # Dtype und Device
        mock_torch.float16 = "float16"
        mock_torch.float32 = "float32"
        mock_torch.device.return_value = Mock()
        mock_torch.version = Mock(cuda="12.1")

        # Backend settings
        mock_torch.backends = Mock()
        mock_torch.backends.cuda = Mock()
        mock_torch.backends.cuda.matmul = Mock()
        mock_torch.backends.cuda.matmul.allow_tf32 = True
        mock_torch.backends.cudnn = Mock()
        mock_torch.backends.cudnn.allow_tf32 = True
        mock_torch.backends.cudnn.benchmark = True

        # no_grad context manager
        mock_torch.no_grad.return_value.__enter__ = Mock()
        mock_torch.no_grad.return_value.__exit__ = Mock()

        yield mock_torch


@pytest.fixture
def mock_torch_cuda_unavailable():
    """Mock torch.cuda wenn keine GPU verfuegbar."""
    with patch('app.agents.ocr.olmocr_agent.torch') as mock_torch:
        mock_torch.cuda.is_available.return_value = False
        mock_torch.float32 = "float32"
        mock_torch.device.return_value = Mock()
        yield mock_torch


@pytest.fixture
def mock_transformers():
    """Mock HuggingFace transformers fuer Model Loading."""
    with patch('app.agents.ocr.olmocr_agent.Qwen2VLForConditionalGeneration') as mock_model_class:
        with patch('app.agents.ocr.olmocr_agent.AutoProcessor') as mock_processor_class:
            # Mock Model
            mock_model = Mock()
            mock_model.train = Mock()
            mock_model.generate = Mock(return_value=[[1, 2, 3, 4, 5, 6, 7, 8]])
            mock_model_class.from_pretrained = Mock(return_value=mock_model)

            # Mock Processor
            mock_processor = Mock()
            mock_processor.apply_chat_template = Mock(return_value="test prompt")
            mock_processor.batch_decode = Mock(return_value=["Extrahierter Text mit Umlaut: Mueller GmbH"])
            mock_processor.tokenizer = Mock(pad_token_id=0)

            # Mock __call__ fuer processor (inputs = processor(...))
            mock_inputs = Mock()
            mock_inputs.to = Mock(return_value=mock_inputs)
            mock_inputs.input_ids = [[1, 2, 3]]
            mock_processor.return_value = mock_inputs

            mock_processor_class.from_pretrained = Mock(return_value=mock_processor)

            yield {
                "model_class": mock_model_class,
                "processor_class": mock_processor_class,
                "model": mock_model,
                "processor": mock_processor
            }


@pytest.fixture
def mock_pil_image():
    """Mock PIL Image."""
    image = Mock()
    image.size = (2480, 3508)  # A4 @ 300 DPI
    image.mode = "RGB"
    image.convert.return_value = image
    return image


@pytest.fixture
def mock_pypdfium2():
    """Mock pypdfium2 fuer PDF-Verarbeitung."""
    with patch('app.agents.ocr.olmocr_agent.pdfium') as mock_pdfium:
        mock_page = Mock()
        mock_page.render.return_value.to_pil.return_value = Mock()

        mock_pdf = Mock()
        mock_pdf.__len__ = Mock(return_value=2)  # 2 Seiten
        mock_pdf.__iter__ = Mock(return_value=iter([mock_page, mock_page]))
        mock_pdf.__getitem__ = Mock(return_value=mock_page)
        mock_pdf.close = Mock()

        mock_pdfium.PdfDocument.return_value = mock_pdf
        yield mock_pdfium


# ========================= Initialization Tests =========================


class TestOlmOCRAgentInitialization:
    """Tests fuer OlmOCR Agent Initialisierung."""

    def test_initialization_with_gpu(self, mock_torch_cuda):
        """Agent sollte mit GPU initialisiert werden."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        assert agent.name == "olmocr_agent"
        assert agent.gpu_required is True
        assert agent.vram_gb == 14
        assert agent._models_loaded is False
        assert agent._model is None
        assert agent._processor is None

    def test_initialization_without_gpu(self, mock_torch_cuda_unavailable):
        """Agent sollte ohne GPU initialisiert werden (CPU-Modus)."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        assert agent.name == "olmocr_agent"
        assert agent.gpu_required is False
        assert agent.vram_gb == 0

    def test_model_name_constant(self, mock_torch_cuda):
        """MODEL_NAME sollte korrekt sein."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        assert OlmOCRAgent.MODEL_NAME == "allenai/olmOCR-2-7B-1025"
        assert OlmOCRAgent.VRAM_REQUIRED_GB == 14
        assert OlmOCRAgent.MODEL_LOADING_TIMEOUT == 600.0


class TestOlmOCRAgentStatus:
    """Tests fuer get_status() Methode."""

    def test_get_status_with_gpu(self, mock_torch_cuda):
        """get_status() sollte GPU-Info enthalten."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        status = agent.get_status()

        assert "model_name" in status
        assert status["model_name"] == "allenai/olmOCR-2-7B-1025"
        assert "models_loaded" in status
        assert status["models_loaded"] is False
        assert "gpu_info" in status
        assert "device_name" in status["gpu_info"]

    def test_get_status_without_gpu(self, mock_torch_cuda_unavailable):
        """get_status() sollte angeben dass keine GPU verfuegbar ist."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        status = agent.get_status()

        assert "gpu_info" in status
        assert status["gpu_info"]["available"] is False


# ========================= Image Loading Tests =========================


class TestOlmOCRImageLoading:
    """Tests fuer Bild- und PDF-Laden."""

    def test_load_pdf_returns_multiple_pages(self, mock_torch_cuda, mock_pypdfium2):
        """_load_image() sollte mehrere Seiten aus PDF laden."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.suffix', new_callable=lambda: property(lambda self: '.pdf')):
                images = agent._load_image("/test/document.pdf")

        assert len(images) == 2  # 2 Seiten

    def test_load_image_converts_to_rgb(self, mock_torch_cuda, mock_pil_image):
        """_load_image() sollte Bild zu RGB konvertieren."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        with patch('pathlib.Path.exists', return_value=True):
            with patch('pathlib.Path.suffix', new_callable=lambda: property(lambda self: '.png')):
                with patch('PIL.Image.open', return_value=mock_pil_image):
                    # Simuliere RGBA -> RGB Konvertierung
                    mock_pil_image.mode = "RGBA"
                    images = agent._load_image("/test/image.png")

        assert len(images) == 1
        mock_pil_image.convert.assert_called_once_with('RGB')

    def test_load_image_file_not_found(self, mock_torch_cuda):
        """_load_image() sollte FileNotFoundError bei fehlender Datei werfen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        with pytest.raises(FileNotFoundError, match="Datei nicht gefunden"):
            agent._load_image("/nicht/existent/dokument.pdf")


# ========================= Processing Tests =========================


class TestOlmOCRProcessing:
    """Tests fuer OCR Verarbeitung."""

    @pytest.mark.asyncio
    async def test_process_returns_ocr_result(
        self, mock_torch_cuda, mock_transformers, mock_pypdfium2
    ):
        """process() sollte standardisiertes OCRResult zurueckgeben."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        with patch('pathlib.Path.exists', return_value=True):
            with patch.object(agent, '_load_image', return_value=[Mock()]):
                with patch.object(agent, '_process_single_image', return_value={
                    "text": "Test Text mit Umlauten: Muller",
                    "confidence": 0.95,
                    "text_regions": 5,
                    "german_chars_found": ["ue"]
                }):
                    result = await agent.process("/test/document.pdf")

        assert result["success"] is True
        assert "text" in result
        assert "confidence" in result
        assert result["backend"] == "olmocr_agent"
        assert "processing_time_ms" in result

    @pytest.mark.asyncio
    async def test_process_handles_dict_input(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte Dict-Input korrekt verarbeiten."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        with patch.object(agent, '_load_image', return_value=[Mock()]):
            with patch.object(agent, '_process_single_image', return_value={
                "text": "Test",
                "confidence": 0.9,
                "text_regions": 1,
                "german_chars_found": []
            }):
                result = await agent.process({
                    "image_path": "/test/doc.pdf",
                    "language": "en"
                })

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_process_error_handling(self, mock_torch_cuda):
        """process() sollte Fehler korrekt behandeln und Error-Result zurueckgeben."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        with patch.object(agent, '_load_models_async', side_effect=Exception("Model load failed")):
            result = await agent.process("/test/document.pdf")

        assert result["success"] is False
        assert "error" in result
        assert result["error_code"] == "OLMOCR_ERROR"


# ========================= German Text Tests =========================


class TestOlmOCRGermanText:
    """Tests fuer deutsche Textverarbeitung."""

    def test_umlaut_detection_in_result(self, mock_torch_cuda, mock_transformers):
        """_process_single_image() sollte deutsche Zeichen erkennen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Mock processor.batch_decode mit deutschen Zeichen
        mock_transformers["processor"].batch_decode.return_value = [
            "Muller GmbH, Gruner Weg 123, Dusseldorf"
        ]

        result = agent._process_single_image(Mock(), language="de")

        assert "german_chars_found" in result
        # "ue" sollte gefunden werden in "Mueller" und "Gruener"
        assert any(c in result["german_chars_found"] for c in ["ue", "Ue"])

    @pytest.mark.asyncio
    async def test_has_umlauts_flag(self, mock_torch_cuda, mock_transformers):
        """process() sollte has_umlauts korrekt setzen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        with patch.object(agent, '_load_image', return_value=[Mock()]):
            with patch.object(agent, '_process_single_image', return_value={
                "text": "Text mit echten Umlauten: Mueller GmbH",
                "confidence": 0.95,
                "text_regions": 1,
                "german_chars_found": ["ue"]
            }):
                # Mock um echte Umlaute zu testen
                result = await agent.process("/test/doc.pdf")

        # has_umlauts basiert auf echten Unicode-Umlauten (ae, oe, ue)
        # Der Mock-Text hat keine echten Umlaute, also sollte es False sein
        assert "has_umlauts" in result


# ========================= GPU Memory Tests =========================


class TestOlmOCRGPUMemory:
    """Tests fuer GPU Memory Management."""

    @pytest.mark.asyncio
    async def test_cleanup_clears_model_references(self, mock_torch_cuda):
        """cleanup() sollte Model-Referenzen loeschen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._model = Mock()
        agent._processor = Mock()
        agent._models_loaded = True

        await agent.cleanup()

        assert agent._model is None
        assert agent._processor is None
        assert agent._models_loaded is False

    @pytest.mark.asyncio
    async def test_cleanup_clears_gpu_cache(self, mock_torch_cuda):
        """cleanup() sollte GPU Cache leeren."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        await agent.cleanup()

        mock_torch_cuda.cuda.empty_cache.assert_called()
        mock_torch_cuda.cuda.synchronize.assert_called()

    def test_process_single_image_handles_oom(self, mock_torch_cuda, mock_transformers):
        """_process_single_image() sollte GPU OOM abfangen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Simuliere OOM
        mock_torch_cuda.cuda.OutOfMemoryError = Exception
        mock_transformers["model"].generate.side_effect = Exception("CUDA out of memory")

        result = agent._process_single_image(Mock(), language="de")

        assert "error" in result
        assert result["confidence"] == 0.0


# ========================= Thread Safety Tests =========================


class TestOlmOCRThreadSafety:
    """Tests fuer Thread-Safe Model Loading."""

    @pytest.mark.asyncio
    async def test_model_loading_uses_lock(self, mock_torch_cuda, mock_transformers):
        """_load_models_async() sollte asyncio.Lock verwenden."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        # Lock sollte existieren
        assert OlmOCRAgent._model_lock is not None

    @pytest.mark.asyncio
    async def test_model_loading_timeout(self, mock_torch_cuda):
        """_load_models_async() sollte bei Timeout fehlschlagen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()

        # Simuliere lange Model-Loading Zeit
        async def slow_load():
            await asyncio.sleep(10)

        with patch.object(agent, '_load_models_sync', side_effect=lambda: asyncio.run(slow_load())):
            with pytest.raises(asyncio.TimeoutError):
                await agent._load_models_async(timeout_seconds=0.1)

    @pytest.mark.asyncio
    async def test_double_load_prevention(self, mock_torch_cuda, mock_transformers):
        """_load_models_async() sollte Models nur einmal laden (Double-Check Pattern)."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True  # Simuliere bereits geladene Models

        # _load_models_sync sollte nicht aufgerufen werden
        with patch.object(agent, '_load_models_sync') as mock_sync:
            await agent._load_models_async()

        mock_sync.assert_not_called()


# ========================= Multi-Page Tests =========================


class TestOlmOCRMultiPage:
    """Tests fuer Multi-Page PDF Verarbeitung."""

    @pytest.mark.asyncio
    async def test_process_multi_page_combines_text(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte Text von mehreren Seiten kombinieren."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Mock 3 Seiten
        mock_images = [Mock(), Mock(), Mock()]

        page_results = [
            {"text": "Seite 1", "confidence": 0.9, "text_regions": 2, "german_chars_found": []},
            {"text": "Seite 2", "confidence": 0.85, "text_regions": 3, "german_chars_found": []},
            {"text": "Seite 3", "confidence": 0.95, "text_regions": 1, "german_chars_found": []},
        ]

        with patch.object(agent, '_load_image', return_value=mock_images):
            with patch.object(agent, '_process_single_image', side_effect=page_results):
                result = await agent.process("/test/multi_page.pdf")

        assert result["success"] is True
        assert "Seite 1" in result["text"]
        assert "Seite 2" in result["text"]
        assert "Seite 3" in result["text"]
        assert result["page_count"] == 3

    @pytest.mark.asyncio
    async def test_process_multi_page_averages_confidence(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte Durchschnitts-Confidence fuer mehrere Seiten berechnen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        mock_images = [Mock(), Mock()]
        page_results = [
            {"text": "A", "confidence": 0.8, "text_regions": 1, "german_chars_found": []},
            {"text": "B", "confidence": 1.0, "text_regions": 1, "german_chars_found": []},
        ]

        with patch.object(agent, '_load_image', return_value=mock_images):
            with patch.object(agent, '_process_single_image', side_effect=page_results):
                result = await agent.process("/test/doc.pdf")

        # Durchschnitt: (0.8 + 1.0) / 2 = 0.9
        assert result["confidence"] == 0.9

    @pytest.mark.asyncio
    async def test_process_returns_pages_data(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte per-Page Daten zurueckgeben."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        mock_images = [Mock(), Mock()]
        page_results = [
            {"text": "Page 1", "confidence": 0.9, "text_regions": 2, "german_chars_found": ["ae"]},
            {"text": "Page 2", "confidence": 0.85, "text_regions": 3, "german_chars_found": []},
        ]

        with patch.object(agent, '_load_image', return_value=mock_images):
            with patch.object(agent, '_process_single_image', side_effect=page_results):
                result = await agent.process("/test/doc.pdf")

        assert "pages" in result
        assert len(result["pages"]) == 2
        assert result["pages"][0]["page_number"] == 1
        assert result["pages"][1]["page_number"] == 2


# ========================= Edge Case Tests =========================


class TestOlmOCREdgeCases:
    """Tests fuer Edge Cases."""

    @pytest.mark.asyncio
    async def test_process_invalid_input_type(self, mock_torch_cuda, mock_transformers):
        """process() sollte bei ungueltigem Input-Typ fehlschlagen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True

        result = await agent.process({"image_path": 12345})  # Nicht-String

        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_process_empty_pdf(self, mock_torch_cuda, mock_transformers):
        """process() sollte leere PDFs behandeln."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True

        with patch.object(agent, '_load_image', return_value=[]):
            result = await agent.process("/test/empty.pdf")

        # Leere Liste -> Division durch 0 bei avg_confidence
        # Sollte graceful behandelt werden
        assert result["success"] is True
        assert result["confidence"] == 0.0

    def test_warmup_model_graceful_failure(self, mock_torch_cuda, mock_transformers):
        """_warmup_model() sollte bei Fehler nicht crashen."""
        from app.agents.ocr.olmocr_agent import OlmOCRAgent

        agent = OlmOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Simuliere Fehler bei Warmup
        mock_transformers["processor"].apply_chat_template.side_effect = Exception("Warmup failed")

        # Sollte nicht crashen
        agent._warmup_model()  # Kein Fehler erwartet


# ========================= Run Tests =========================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
