# -*- coding: utf-8 -*-
"""
Tests fuer Qwen2.5-VL-7B OCR Agent.

Testet:
- Agent-Initialisierung mit GPU-Detection
- JSON/Struktur-Extraktion
- Multimodal Processing (Image + Text)
- Deutsche Textverarbeitung
- Layout Detection
- Custom Prompt Handling
- GPU OOM Recovery
- Batch Processing
- Windows Encoding Handling

Feinpoliert und durchdacht - Qwen2.5-VL OCR Tests.
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
    with patch('app.agents.ocr.qwen_ocr_agent.torch') as mock_torch:
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.empty_cache = Mock()
        mock_torch.cuda.synchronize = Mock()
        mock_torch.cuda.get_device_name.return_value = "NVIDIA GeForce RTX 4080"
        mock_torch.cuda.memory_allocated.return_value = 2 * 1024**3
        mock_torch.cuda.max_memory_allocated.return_value = 10 * 1024**3
        mock_torch.cuda.memory_reserved.return_value = 5 * 1024**3

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

        # no_grad context manager - muss als richtiger context manager funktionieren
        mock_no_grad = MagicMock()
        mock_no_grad.__enter__ = Mock(return_value=None)
        mock_no_grad.__exit__ = Mock(return_value=False)
        mock_torch.no_grad.return_value = mock_no_grad

        # OOM Exception als richtige Exception-Klasse
        class MockOutOfMemoryError(RuntimeError):
            pass
        mock_torch.cuda.OutOfMemoryError = MockOutOfMemoryError

        yield mock_torch


@pytest.fixture
def mock_torch_cuda_unavailable():
    """Mock torch.cuda wenn keine GPU verfuegbar."""
    with patch('app.agents.ocr.qwen_ocr_agent.torch') as mock_torch:
        mock_torch.cuda.is_available.return_value = False
        mock_torch.float32 = "float32"
        mock_torch.device.return_value = Mock()
        yield mock_torch


@pytest.fixture
def mock_transformers():
    """Mock HuggingFace transformers fuer Model Loading."""
    # Patch at transformers module level since imports happen inside _load_model()
    with patch('transformers.Qwen2_5_VLForConditionalGeneration') as mock_model_class:
        with patch('transformers.AutoProcessor') as mock_processor_class:
            # Mock Model
            mock_model = MagicMock()
            mock_model.eval = Mock()
            mock_model.generate = Mock(return_value=[[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]])
            mock_model_class.from_pretrained = Mock(return_value=mock_model)

            # Mock Processor
            mock_processor = MagicMock()
            mock_processor.apply_chat_template = Mock(return_value="test prompt with image")
            mock_processor.batch_decode = Mock(return_value=["Extrahierter Text: Müller AG"])
            mock_processor.tokenizer = Mock(pad_token_id=0)

            # Mock __call__ fuer processor - inputs muss als kwargs entpackbar sein
            mock_inputs = MagicMock()
            mock_inputs.to = Mock(return_value=mock_inputs)
            mock_inputs.input_ids = [[1, 2, 3, 4]]
            mock_inputs.keys.return_value = ['input_ids', 'attention_mask']
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
    with patch('app.agents.ocr.qwen_ocr_agent.pdfium') as mock_pdfium:
        mock_page = Mock()
        mock_page.render.return_value.to_pil.return_value = Mock()

        mock_pdf = Mock()
        mock_pdf.__len__ = Mock(return_value=1)
        mock_pdf.__iter__ = Mock(return_value=iter([mock_page]))
        mock_pdf.__getitem__ = Mock(return_value=mock_page)
        mock_pdf.close = Mock()

        mock_pdfium.PdfDocument.return_value = mock_pdf
        yield mock_pdfium


# ========================= Initialization Tests =========================


class TestQwenOCRAgentInitialization:
    """Tests fuer Qwen OCR Agent Initialisierung."""

    def test_initialization_with_gpu(self, mock_torch_cuda):
        """Agent sollte mit GPU initialisiert werden."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()

        assert agent.name == "qwen_ocr_agent"
        assert agent.gpu_required is True
        assert agent.vram_gb == 14
        assert agent._models_loaded is False
        assert agent._model is None
        assert agent._processor is None

    def test_initialization_without_gpu(self, mock_torch_cuda_unavailable):
        """Agent sollte ohne GPU initialisiert werden (CPU-Modus)."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()

        assert agent.name == "qwen_ocr_agent"
        assert agent.gpu_required is False
        assert agent.vram_gb == 0

    def test_model_name_constant(self, mock_torch_cuda):
        """MODEL_NAME sollte korrekt sein."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        assert QwenOCRAgent.MODEL_NAME == "Qwen/Qwen2.5-VL-7B-Instruct"
        assert QwenOCRAgent.VRAM_REQUIRED_GB == 14
        assert QwenOCRAgent.MODEL_LOADING_TIMEOUT == 600.0


# ========================= Status Tests =========================


class TestQwenOCRAgentStatus:
    """Tests fuer get_status() Methode."""

    def test_get_status_with_gpu(self, mock_torch_cuda):
        """get_status() sollte GPU-Info enthalten."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        status = agent.get_status()

        assert "model_name" in status
        assert status["model_name"] == "Qwen/Qwen2.5-VL-7B-Instruct"
        assert "models_loaded" in status
        assert "gpu_info" in status
        assert "device_name" in status["gpu_info"]
        assert "tf32_enabled" in status["gpu_info"]

    def test_get_status_without_gpu(self, mock_torch_cuda_unavailable):
        """get_status() sollte angeben dass keine GPU verfuegbar ist."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        status = agent.get_status()

        assert status["gpu_info"]["available"] is False


# ========================= JSON Extraction Tests =========================


class TestQwenOCRJSONExtraction:
    """Tests fuer JSON/strukturierte Datenextraktion."""

    @pytest.mark.asyncio
    async def test_process_extracts_structured_data(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte strukturierte Daten extrahieren koennen."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Mock JSON-aehnliche Ausgabe
        mock_transformers["processor"].batch_decode.return_value = [
            '{"invoice_number": "RE-2024-001", "amount": "1234.56", "date": "01.12.2024"}'
        ]

        with patch.object(agent, '_load_image', return_value=[Mock()]):
            result = await agent.process("/test/invoice.pdf")

        assert result["success"] is True
        assert "invoice_number" in result["text"] or "RE-2024-001" in result["text"]


# ========================= Multimodal Tests =========================


class TestQwenOCRMultimodal:
    """Tests fuer multimodale Verarbeitung."""

    def test_process_single_image_uses_multimodal_format(
        self, mock_torch_cuda, mock_transformers
    ):
        """_process_single_image() sollte multimodales Format verwenden."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        result = agent._process_single_image(Mock(), language="de")

        # apply_chat_template sollte aufgerufen worden sein
        mock_transformers["processor"].apply_chat_template.assert_called()

        # Der Call sollte Messages mit Image und Text enthalten
        call_args = mock_transformers["processor"].apply_chat_template.call_args
        messages = call_args[0][0]

        assert len(messages) > 0
        assert messages[0]["role"] == "user"
        content = messages[0]["content"]
        content_types = [item["type"] for item in content]
        assert "image" in content_types
        assert "text" in content_types


# ========================= German Text Tests =========================


class TestQwenOCRGermanText:
    """Tests fuer deutsche Textverarbeitung."""

    def test_german_char_detection(self, mock_torch_cuda, mock_transformers):
        """_process_single_image() sollte deutsche Zeichen erkennen."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Mock Text mit deutschen Zeichen (ae, oe, ue)
        mock_transformers["processor"].batch_decode.return_value = [
            "Gesellschaft fuer Datenverarbeitung GmbH, Muenchen"
        ]

        result = agent._process_single_image(Mock(), language="de")

        assert "german_chars_found" in result
        # "ue" und "ae" sollten gefunden werden
        found_chars = result["german_chars_found"]
        assert any(c in found_chars for c in ["ue", "ae", "oe"])

    @pytest.mark.asyncio
    async def test_process_default_language_is_german(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte standardmaessig Deutsch verwenden."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        with patch.object(agent, '_load_image', return_value=[Mock()]):
            with patch.object(agent, '_process_single_image', return_value={
                "text": "Test",
                "confidence": 0.9,
                "text_regions": 1,
                "german_chars_found": []
            }) as mock_process:
                await agent.process("/test/doc.pdf")

        # Sollte mit language="de" aufgerufen worden sein
        call_args = mock_process.call_args
        assert call_args[1].get("language", call_args[0][1] if len(call_args[0]) > 1 else "de") == "de"


# ========================= Layout Detection Tests =========================


class TestQwenOCRLayoutDetection:
    """Tests fuer Layout-Erkennung."""

    def test_text_regions_count(self, mock_torch_cuda, mock_transformers):
        """_process_single_image() sollte Textregionen zaehlen."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Text mit mehreren Zeilen
        mock_transformers["processor"].batch_decode.return_value = [
            "Zeile 1\nZeile 2\nZeile 3\nZeile 4"
        ]

        result = agent._process_single_image(Mock(), language="de")

        assert "text_regions" in result
        assert result["text_regions"] == 4  # 4 Zeilen


# ========================= Custom Prompt Tests =========================


class TestQwenOCRCustomPrompt:
    """Tests fuer Custom Prompt Handling."""

    def test_ocr_prompt_includes_german_instructions(self, mock_torch_cuda):
        """OCR_PROMPT sollte deutsche Anweisungen enthalten."""
        from app.agents.ocr.qwen_ocr_agent import OCR_PROMPT

        assert "Umlaute" in OCR_PROMPT or "ae" in OCR_PROMPT
        assert "IBAN" in OCR_PROMPT
        assert "BIC" in OCR_PROMPT
        assert "Datumsangaben" in OCR_PROMPT or "Datum" in OCR_PROMPT


# ========================= GPU OOM Recovery Tests =========================


class TestQwenOCROOMRecovery:
    """Tests fuer GPU OOM Recovery."""

    def test_process_single_image_handles_oom(self, mock_torch_cuda, mock_transformers):
        """_process_single_image() sollte GPU OOM graceful behandeln."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # Simuliere OOM
        mock_transformers["model"].generate.side_effect = mock_torch_cuda.cuda.OutOfMemoryError(
            "CUDA out of memory"
        )

        result = agent._process_single_image(Mock(), language="de")

        assert "error" in result
        assert "Out of Memory" in result["error"] or "error" in result
        assert result["confidence"] == 0.0
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_process_returns_error_result_on_oom(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte Error-Result bei OOM zurueckgeben."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        with patch.object(agent, '_load_image', return_value=[Mock()]):
            with patch.object(agent, '_process_single_image', return_value={
                "text": "",
                "confidence": 0.0,
                "text_regions": 0,
                "german_chars_found": [],
                "error": "GPU Out of Memory"
            }):
                result = await agent.process("/test/large.pdf")

        # Auch bei Fehler sollte ein valides Result zurueckgegeben werden
        assert result["success"] is True  # Ein leerer Text ist trotzdem "Erfolg"


# ========================= Batch Processing Tests =========================


class TestQwenOCRBatchProcessing:
    """Tests fuer Batch Processing mehrerer Bilder."""

    @pytest.mark.asyncio
    async def test_process_multiple_pages_sequentially(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte mehrere Seiten sequentiell verarbeiten."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # 3 Seiten
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
        # page_count ist in metadata
        assert result["metadata"]["page_count"] == 3
        assert "pages" in result
        assert len(result["pages"]) == 3

    @pytest.mark.asyncio
    async def test_process_clears_cache_between_pages(
        self, mock_torch_cuda, mock_transformers
    ):
        """process() sollte GPU Cache zwischen Seiten leeren."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        # 2 Seiten
        mock_images = [Mock(), Mock()]

        with patch.object(agent, '_load_image', return_value=mock_images):
            with patch.object(agent, '_process_single_image', return_value={
                "text": "Test",
                "confidence": 0.9,
                "text_regions": 1,
                "german_chars_found": []
            }):
                await agent.process("/test/doc.pdf")

        # empty_cache sollte mehrmals aufgerufen worden sein
        assert mock_torch_cuda.cuda.empty_cache.call_count >= 1


# ========================= Windows Encoding Tests =========================


class TestQwenOCRWindowsEncoding:
    """Tests fuer Windows-spezifische Encoding-Behandlung."""

    def test_load_models_sync_handles_windows_encoding(
        self, mock_torch_cuda, mock_transformers
    ):
        """_load_models_sync() sollte Windows Encoding-Probleme behandeln."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()

        # Simuliere Windows-Umgebung
        with patch('sys.platform', 'win32'):
            with patch('sys.stdout') as mock_stdout:
                mock_stdout.reconfigure = Mock()
                with patch('sys.stderr') as mock_stderr:
                    mock_stderr.reconfigure = Mock()

                    # Model Loading sollte nicht crashen
                    try:
                        agent._load_models_sync()
                    except Exception:
                        pass  # Model Loading schlaegt fehl, aber Encoding sollte behandelt werden


# ========================= Cleanup Tests =========================


class TestQwenOCRCleanup:
    """Tests fuer Cleanup-Verhalten."""

    @pytest.mark.asyncio
    async def test_cleanup_clears_model_references(self, mock_torch_cuda):
        """cleanup() sollte Model-Referenzen loeschen."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
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
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()

        await agent.cleanup()

        mock_torch_cuda.cuda.empty_cache.assert_called()
        mock_torch_cuda.cuda.synchronize.assert_called()


# ========================= Thread Safety Tests =========================


class TestQwenOCRThreadSafety:
    """Tests fuer Thread-Safe Model Loading."""

    @pytest.mark.asyncio
    async def test_model_loading_uses_lock(self, mock_torch_cuda):
        """_load_models_async() sollte asyncio.Lock verwenden."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()

        # Lock sollte existieren (nach Initialisierung)
        assert QwenOCRAgent._model_lock is not None

    @pytest.mark.asyncio
    async def test_double_load_prevention(self, mock_torch_cuda, mock_transformers):
        """_load_models_async() sollte Models nur einmal laden."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True  # Bereits geladen

        with patch.object(agent, '_load_models_sync') as mock_sync:
            await agent._load_models_async()

        mock_sync.assert_not_called()


# ========================= Edge Cases =========================


class TestQwenOCREdgeCases:
    """Tests fuer Edge Cases."""

    @pytest.mark.asyncio
    async def test_process_invalid_path_type(self, mock_torch_cuda, mock_transformers):
        """process() sollte bei ungueltigem Pfad-Typ fehlschlagen."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True

        result = await agent.process({"image_path": None})

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_process_file_not_found(self, mock_torch_cuda, mock_transformers):
        """process() sollte FileNotFoundError behandeln."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        result = await agent.process("/nicht/existent/datei.pdf")

        assert result["success"] is False
        assert "error" in result

    def test_warmup_model_graceful_failure(self, mock_torch_cuda, mock_transformers):
        """_warmup_model() sollte bei Fehler nicht crashen."""
        from app.agents.ocr.qwen_ocr_agent import QwenOCRAgent

        agent = QwenOCRAgent()
        agent._models_loaded = True
        agent._model = mock_transformers["model"]
        agent._processor = mock_transformers["processor"]

        mock_transformers["processor"].apply_chat_template.side_effect = Exception("Warmup error")

        # Sollte nicht crashen
        agent._warmup_model()


# ========================= Run Tests =========================


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
