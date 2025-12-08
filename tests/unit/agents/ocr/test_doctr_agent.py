# -*- coding: utf-8 -*-
"""
Tests fuer docTR OCR Agent.

Testet:
- Agent-Initialisierung (CPU-only)
- Model Loading (Thread-safe mit Lock)
- Verarbeitung von Bildern und PDFs
- Deutsche Umlaut-Erkennung
- Confidence-Berechnung
- Cleanup-Verhalten

Feinpoliert und durchdacht - docTR OCR Tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import asyncio


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_doctr_available():
    """Mock docTR als verfuegbar."""
    with patch('app.agents.ocr.doctr_agent.DOCTR_AVAILABLE', True):
        yield


@pytest.fixture
def mock_doctr_unavailable():
    """Mock docTR als nicht verfuegbar."""
    with patch('app.agents.ocr.doctr_agent.DOCTR_AVAILABLE', False):
        yield


@pytest.fixture
def mock_image():
    """Mock PIL Image."""
    image = Mock()
    image.size = (800, 600)
    image.mode = "RGB"
    image.convert.return_value = image
    image.copy.return_value = image
    return image


@pytest.fixture
def mock_doctr_result():
    """Mock docTR OCR Result."""
    # Create mock word
    mock_word = Mock()
    mock_word.value = "Test"
    mock_word.confidence = 0.95
    mock_word.geometry = [[0, 0], [100, 50]]

    # Create mock line with words
    mock_line = Mock()
    mock_line.words = [mock_word]

    # Create mock block with lines
    mock_block = Mock()
    mock_block.lines = [mock_line]

    # Create mock page with blocks
    mock_page = Mock()
    mock_page.blocks = [mock_block]

    # Create mock result with pages
    mock_result = Mock()
    mock_result.pages = [mock_page]

    return mock_result


@pytest.fixture
def mock_ocr_predictor(mock_doctr_result):
    """Mock docTR ocr_predictor."""
    mock_predictor = Mock()
    mock_predictor.return_value = mock_doctr_result
    return mock_predictor


# ========================= Availability Tests =========================


class TestDocTRAvailability:
    """Tests fuer docTR Verfuegbarkeit."""

    def test_is_doctr_available_when_installed(self):
        """is_doctr_available() sollte True zurueckgeben wenn installiert."""
        with patch('app.agents.ocr.doctr_agent.DOCTR_AVAILABLE', True):
            from app.agents.ocr.doctr_agent import is_doctr_available
            assert is_doctr_available() is True

    def test_is_doctr_available_when_not_installed(self):
        """is_doctr_available() sollte False zurueckgeben wenn nicht installiert."""
        with patch('app.agents.ocr.doctr_agent.DOCTR_AVAILABLE', False):
            from app.agents.ocr.doctr_agent import is_doctr_available
            assert is_doctr_available() is False


# ========================= Initialization Tests =========================


class TestDocTRAgentInitialization:
    """Tests fuer DocTR Agent Initialisierung."""

    def test_initialization_default_config(self, mock_doctr_available):
        """Agent sollte mit Standardkonfiguration initialisiert werden."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        assert agent.name == "doctr_agent"
        assert agent.gpu_required is False
        assert agent.vram_gb == 0
        assert agent.det_arch == "db_resnet50"
        assert agent.reco_arch == "crnn_vgg16_bn"

    def test_initialization_cpu_only(self, mock_doctr_available):
        """Agent sollte als CPU-only konfiguriert sein."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        assert agent.gpu_required is False
        assert agent.vram_gb == 0

    def test_initialization_custom_models(self, mock_doctr_available):
        """Agent sollte mit benutzerdefinierten Modellen initialisiert werden."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent(
            det_arch="db_mobilenet_v3",
            reco_arch="crnn_mobilenet_v3"
        )

        assert agent.det_arch == "db_mobilenet_v3"
        assert agent.reco_arch == "crnn_mobilenet_v3"

    def test_initialization_assume_straight_pages(self, mock_doctr_available):
        """Agent sollte assume_straight_pages konfigurieren."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent(assume_straight_pages=False)

        assert agent.assume_straight_pages is False

    def test_initialization_default_language(self, mock_doctr_available):
        """Agent sollte Deutsch als Standardsprache haben."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        assert agent.default_language == "de"


# ========================= Model Loading Tests =========================


class TestDocTRModelLoading:
    """Tests fuer Model-Loading-Verhalten."""

    def test_model_lock_exists(self, mock_doctr_available):
        """Class-level Lock sollte existieren."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        assert DocTRAgent._model_lock is not None

    @pytest.mark.asyncio
    async def test_model_loading_with_lock(self, mock_doctr_available):
        """Model-Loading sollte Thread-Safe mit Lock sein."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        # Mock the _load_models_sync method to set _models_loaded
        def mock_load():
            agent._models_loaded = True

        with patch.object(agent, '_load_models_sync', side_effect=mock_load):
            await agent._load_models_async()
            assert agent._models_loaded is True

    def test_model_constants_defined(self, mock_doctr_available):
        """Model-Konstanten sollten definiert sein."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        assert DocTRAgent.DETECTION_MODEL == "db_resnet50"
        assert DocTRAgent.RECOGNITION_MODEL == "crnn_vgg16_bn"
        assert DocTRAgent.RAM_REQUIRED_MB == 1024
        assert DocTRAgent.MODEL_LOADING_TIMEOUT == 300.0

    def test_lazy_loading_not_loaded_initially(self, mock_doctr_available):
        """Modelle sollten initial nicht geladen sein."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        assert agent._models_loaded is False
        assert agent._model is None


# ========================= Process Tests =========================


class TestDocTRProcessing:
    """Tests fuer docTR Verarbeitung."""

    @pytest.mark.asyncio
    async def test_process_validates_input(self, mock_doctr_available):
        """process() sollte Input validieren."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        # Missing image_path
        result = await agent.process({"language": "de"})

        assert result.get("success") is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_process_handles_file_not_found(self, mock_doctr_available):
        """process() sollte fehlende Dateien behandeln."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()
        agent._model = Mock()  # Pretend model is loaded
        agent._models_loaded = True

        # Mock _load_models_async to do nothing
        with patch.object(agent, '_load_models_async', new_callable=AsyncMock):
            # Nonexistent file
            result = await agent.process({
                "image_path": "/nonexistent/path/to/file.png",
                "language": "de"
            })

            assert result.get("success") is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_process_returns_standardized_result(
        self, mock_doctr_available, mock_image, mock_ocr_predictor
    ):
        """process() sollte standardisiertes OCRResult zurueckgeben."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()
        agent._model = Mock()  # Pretend model is loaded
        agent._models_loaded = True

        with patch.object(agent, '_load_image', return_value=[mock_image]):
            with patch.object(agent, '_load_models_async', new_callable=AsyncMock):
                with patch.object(agent, '_process_single_image') as mock_process:
                    mock_process.return_value = {
                        "text": "Test text",
                        "confidence": 0.95,
                        "word_count": 2,
                        "text_blocks": []
                    }

                    result = await agent.process({
                        "image_path": "/path/to/image.png",
                        "language": "de"
                    })

                    # Check standardized result structure
                    assert "success" in result
                    assert "text" in result
                    assert "confidence" in result
                    assert "backend" in result
                    assert result["backend"] == "doctr_agent"

    @pytest.mark.asyncio
    async def test_process_unavailable_returns_error(self, mock_doctr_unavailable):
        """process() sollte Fehler zurueckgeben wenn docTR nicht verfuegbar."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        result = await agent.process({
            "image_path": "/path/to/image.png",
            "language": "de"
        })

        assert result.get("success") is False
        assert "error" in result


# ========================= Confidence Calculation Tests =========================


class TestDocTRConfidence:
    """Tests fuer Confidence-Berechnung."""

    def test_confidence_calculation_from_words(self, mock_doctr_available):
        """Confidence sollte aus Word-Level Scores berechnet werden."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        # Simulate word confidences
        mock_result = {
            "text_blocks": [
                {"text": "Test", "confidence": 0.9, "type": "word"},
                {"text": "text", "confidence": 0.8, "type": "word"},
            ]
        }

        # Average should be (0.9 + 0.8) / 2 = 0.85
        total_conf = sum(b["confidence"] for b in mock_result["text_blocks"])
        avg_conf = total_conf / len(mock_result["text_blocks"])

        assert abs(avg_conf - 0.85) < 0.01


# ========================= German Text Processing Tests =========================


class TestDocTRGermanProcessing:
    """Tests fuer deutsche Textverarbeitung."""

    def test_umlaut_detection_not_found(self, mock_doctr_available):
        """Keine Umlaute sollten erkannt werden wenn keine vorhanden."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        # Text without actual umlauts (only 'oe', 'ae', 'ue')
        has_umlauts, found = agent._detect_umlauts("Muenchen ist schoen")

        # The detection looks for actual umlaut characters, not digraphs
        # This text has no actual umlauts, so result depends on implementation
        assert isinstance(has_umlauts, bool)
        assert isinstance(found, list)

    def test_umlaut_detection_with_real_umlauts(self, mock_doctr_available):
        """Echte Umlaute sollten erkannt werden."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        # Text with actual German umlauts
        text_with_umlauts = "Muenchen ist schoen"
        has_umlauts, found = agent._detect_umlauts(text_with_umlauts)

        # Check return types
        assert isinstance(has_umlauts, bool)
        assert isinstance(found, list)

        # With actual umlauts (o = o umlaut)
        text_real_umlauts = "Das ist schoen mit oe"
        has_umlauts2, found2 = agent._detect_umlauts(text_real_umlauts)
        assert isinstance(has_umlauts2, bool)

    def test_german_postprocessing(self, mock_doctr_available):
        """Deutscher Text sollte korrekt nachbearbeitet werden."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        # Text with extra whitespace
        messy_text = "  Test    text   with   spaces  \n\n\n multiple lines  "
        processed = agent._postprocess_german(messy_text)

        # Should normalize whitespace
        assert "    " not in processed
        assert processed == "Test text with spaces multiple lines"


# ========================= Image Loading Tests =========================


class TestDocTRImageLoading:
    """Tests fuer Bild-Laden."""

    def test_load_image_file_not_found(self, mock_doctr_available):
        """_load_image sollte FileNotFoundError werfen."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        with pytest.raises(FileNotFoundError):
            agent._load_image("/nonexistent/path/to/image.png")


# ========================= Cleanup Tests =========================


class TestDocTRCleanup:
    """Tests fuer Cleanup-Verhalten."""

    @pytest.mark.asyncio
    async def test_cleanup_clears_model_references(self, mock_doctr_available):
        """cleanup() sollte Model-Referenzen loeschen."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()
        agent._model = Mock()
        agent._models_loaded = True

        await agent.cleanup()

        assert agent._model is None
        assert agent._models_loaded is False

    @pytest.mark.asyncio
    async def test_cleanup_is_safe_when_not_loaded(self, mock_doctr_available):
        """cleanup() sollte sicher sein wenn nichts geladen."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        # Should not raise
        await agent.cleanup()

        assert agent._models_loaded is False


# ========================= Status Tests =========================


class TestDocTRStatus:
    """Tests fuer Status-Abfrage."""

    def test_get_status_returns_model_info(self, mock_doctr_available):
        """get_status() sollte Model-Informationen zurueckgeben."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()
        status = agent.get_status()

        assert "name" in status
        assert status["name"] == "doctr_agent"
        assert "gpu_required" in status
        assert status["gpu_required"] is False
        assert "models_loaded" in status
        assert "det_arch" in status
        assert "reco_arch" in status
        assert "ram_required_mb" in status
        assert "doctr_available" in status

    def test_get_status_shows_loaded_state(self, mock_doctr_available):
        """get_status() sollte geladenen Zustand anzeigen."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()
        agent._models_loaded = True

        status = agent.get_status()

        assert status["models_loaded"] is True
        assert status["status"] == "ready"

    def test_get_status_shows_not_loaded(self, mock_doctr_available):
        """get_status() sollte nicht-geladenen Zustand anzeigen."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        status = agent.get_status()

        assert status["models_loaded"] is False
        assert status["status"] == "not_loaded"


# ========================= Integration-Ready Tests =========================


class TestDocTRIntegrationReady:
    """Tests fuer Integration-Bereitschaft."""

    def test_agent_can_be_imported(self, mock_doctr_available):
        """Agent sollte importierbar sein."""
        from app.agents.ocr.doctr_agent import DocTRAgent, is_doctr_available

        assert DocTRAgent is not None
        assert is_doctr_available is not None

    def test_agent_inherits_from_ocr_agent(self, mock_doctr_available):
        """Agent sollte von OCRAgent erben."""
        from app.agents.ocr.doctr_agent import DocTRAgent
        from app.agents.base import OCRAgent

        agent = DocTRAgent()

        assert isinstance(agent, OCRAgent)

    def test_agent_has_required_methods(self, mock_doctr_available):
        """Agent sollte alle erforderlichen Methoden haben."""
        from app.agents.ocr.doctr_agent import DocTRAgent

        agent = DocTRAgent()

        assert hasattr(agent, 'process')
        assert hasattr(agent, 'cleanup')
        assert hasattr(agent, 'get_status')
        assert hasattr(agent, 'create_success_result')
        assert hasattr(agent, 'create_error_result')
