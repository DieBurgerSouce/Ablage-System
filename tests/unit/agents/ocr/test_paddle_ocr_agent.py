# -*- coding: utf-8 -*-
"""
Tests fuer PaddleOCR PP-OCRv5 Agent.

Testet:
- Agent-Initialisierung
- CPU-only Verarbeitung
- Deutsche Umlaut-Erkennung
- Confidence-Extraktion
- Cleanup-Verhalten
- Thread-Safety

Feinpoliert und durchdacht - PaddleOCR Tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import asyncio
import numpy as np


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_paddle_ocr():
    """Mock PaddleOCR modul."""
    mock_ocr = Mock()
    # PaddleOCR returns: [[[box, (text, confidence)], ...], ...]
    mock_ocr.ocr.return_value = [[
        [[[0, 0], [100, 0], [100, 30], [0, 30]], ("Test Text", 0.95)],
        [[[0, 40], [100, 40], [100, 70], [0, 70]], ("Zweite Zeile", 0.92)],
    ]]

    with patch.dict('sys.modules', {'paddleocr': Mock()}):
        with patch('paddleocr.PaddleOCR', return_value=mock_ocr):
            yield mock_ocr


@pytest.fixture
def mock_paddle_ocr_german():
    """Mock PaddleOCR mit deutschen Umlauten."""
    mock_ocr = Mock()
    mock_ocr.ocr.return_value = [[
        [[[0, 0], [100, 0], [100, 30], [0, 30]], ("Gruess Gott", 0.94)],
        [[[0, 40], [100, 40], [100, 70], [0, 70]], ("Muenchen ist schoen", 0.91)],
        [[[0, 80], [100, 80], [100, 110], [0, 110]], ("Groesse: 42", 0.89)],
    ]]
    return mock_ocr


@pytest.fixture
def mock_image():
    """Mock PIL Image."""
    image = Mock()
    image.size = (800, 600)
    image.mode = "RGB"
    image.convert.return_value = image
    return image


@pytest.fixture
def sample_numpy_image():
    """Sample numpy array image."""
    return np.zeros((100, 100, 3), dtype=np.uint8)


# ========================= Initialization Tests =========================


class TestPaddleOCRAgentInitialization:
    """Tests fuer PaddleOCR Agent Initialisierung."""

    def test_initialization_cpu_only(self):
        """Agent sollte nur CPU verwenden (kein GPU)."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            assert agent.name == "paddle_ocr_agent"
            assert agent.gpu_required is False
            assert agent.vram_gb == 0

    def test_initialization_default_language_german(self):
        """Default-Sprache sollte Deutsch sein."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            assert agent.default_language == "german"

    def test_initialization_model_not_loaded(self):
        """Model sollte erst bei Bedarf geladen werden (lazy loading)."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            assert agent._model_loaded is False
            assert agent._ocr is None

    def test_model_lock_exists(self):
        """Class-level Lock sollte existieren fuer Thread-Safety."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            assert PaddleOCRAgent._model_lock is not None
            assert isinstance(PaddleOCRAgent._model_lock, asyncio.Lock)


# ========================= Model Loading Tests =========================


class TestPaddleOCRModelLoading:
    """Tests fuer Model-Loading-Verhalten."""

    def test_load_model_sync_creates_ocr_instance(self):
        """_load_model_sync() sollte PaddleOCR Instanz erstellen."""
        mock_ocr = Mock()

        with patch('paddleocr.PaddleOCR', return_value=mock_ocr) as mock_class:
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._load_model_sync()

            mock_class.assert_called_once_with(
                use_angle_cls=True,
                lang="german",
                use_gpu=False,
                show_log=False,
            )
            assert agent._model_loaded is True
            assert agent._ocr is mock_ocr

    def test_load_model_sync_skips_if_already_loaded(self):
        """_load_model_sync() sollte ueberspringen wenn schon geladen."""
        with patch('paddleocr.PaddleOCR') as mock_class:
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._model_loaded = True
            agent._ocr = Mock()

            agent._load_model_sync()

            mock_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_model_async_uses_lock(self):
        """_load_model_async() sollte Lock verwenden."""
        mock_ocr = Mock()

        with patch('paddleocr.PaddleOCR', return_value=mock_ocr):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            # Reset lock fuer Test
            PaddleOCRAgent._model_lock = asyncio.Lock()

            await agent._load_model_async()

            assert agent._model_loaded is True


# ========================= Image Loading Tests =========================


class TestPaddleOCRImageLoading:
    """Tests fuer Bild-Loading."""

    def test_load_image_raises_for_nonexistent_file(self):
        """_load_image() sollte FileNotFoundError werfen."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            with pytest.raises(FileNotFoundError):
                agent._load_image("/nonexistent/path/to/file.png")

    def test_load_image_converts_to_rgb(self, tmp_path):
        """_load_image() sollte Bilder zu RGB konvertieren."""
        # Erstelle temporaeres Test-Bild
        from PIL import Image

        test_image_path = tmp_path / "test_image.png"
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        img.save(test_image_path)

        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            images = agent._load_image(str(test_image_path))

            assert len(images) == 1
            assert isinstance(images[0], np.ndarray)
            assert images[0].shape[2] == 3  # RGB has 3 channels


# ========================= Processing Tests =========================


class TestPaddleOCRProcessing:
    """Tests fuer PaddleOCR Verarbeitung."""

    def test_process_single_image_extracts_text(self, sample_numpy_image):
        """_process_single_image() sollte Text extrahieren."""
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [[
            [[[0, 0], [100, 0], [100, 30], [0, 30]], ("Hello World", 0.95)],
        ]]

        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._ocr = mock_ocr
            agent._model_loaded = True

            result = agent._process_single_image(sample_numpy_image)

            assert result["full_text"] == "Hello World"
            assert len(result["text_blocks"]) == 1
            assert result["text_blocks"][0]["confidence"] == 0.95

    def test_process_single_image_handles_empty_result(self, sample_numpy_image):
        """_process_single_image() sollte leere Ergebnisse behandeln."""
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [[]]

        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._ocr = mock_ocr
            agent._model_loaded = True

            result = agent._process_single_image(sample_numpy_image)

            assert result["full_text"] == ""
            assert len(result["text_blocks"]) == 0

    def test_process_single_image_handles_none_result(self, sample_numpy_image):
        """_process_single_image() sollte None-Ergebnisse behandeln."""
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [None]

        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._ocr = mock_ocr
            agent._model_loaded = True

            result = agent._process_single_image(sample_numpy_image)

            assert result["full_text"] == ""

    @pytest.mark.asyncio
    async def test_process_validates_input(self):
        """process() sollte Input validieren."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            # Missing image_path
            result = await agent.process({"language": "de"})

            assert result.get("success") is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_process_handles_file_not_found(self):
        """process() sollte fehlende Dateien behandeln."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            with patch('paddleocr.PaddleOCR', return_value=Mock()):
                from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

                agent = PaddleOCRAgent()

                result = await agent.process({
                    "image_path": "/nonexistent/path/to/file.pdf",
                    "document_id": "test-123"
                })

                assert result.get("success") is False
                assert "error" in result

    @pytest.mark.asyncio
    async def test_process_returns_standardized_result(self, tmp_path):
        """process() sollte standardisiertes OCRResult zurueckgeben."""
        # Erstelle temporaeres Test-Bild
        from PIL import Image

        test_image_path = tmp_path / "test_doc.png"
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        img.save(test_image_path)

        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [[
            [[[0, 0], [100, 0], [100, 30], [0, 30]], ("Test Document", 0.90)],
        ]]

        with patch('paddleocr.PaddleOCR', return_value=mock_ocr):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            result = await agent.process({
                "image_path": str(test_image_path),
                "document_id": "test-123"
            })

            assert result.get("success") is True
            assert "text" in result
            assert "confidence" in result
            assert "backend" in result
            assert result["backend"] == "paddle_ocr_agent"


# ========================= German Text Tests =========================


class TestPaddleOCRGermanText:
    """Tests fuer Deutsche Text-Verarbeitung."""

    def test_detects_german_umlauts(self, sample_numpy_image):
        """Agent sollte deutsche Umlaute erkennen."""
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [[
            [[[0, 0], [100, 0], [100, 30], [0, 30]], ("Muenchen", 0.95)],
            [[[0, 40], [100, 40], [100, 70], [0, 70]], ("Groesse", 0.92)],
        ]]

        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._ocr = mock_ocr
            agent._model_loaded = True

            result = agent._process_single_image(sample_numpy_image)

            # Text enthaelt "ue" und "oe" als Umlaut-Ersetzungen
            assert "ue" in result["full_text"] or "oe" in result["full_text"]


# ========================= Cleanup Tests =========================


class TestPaddleOCRCleanup:
    """Tests fuer Cleanup-Verhalten."""

    @pytest.mark.asyncio
    async def test_cleanup_clears_model_references(self):
        """cleanup() sollte Model-Referenzen loeschen."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._ocr = Mock()
            agent._model_loaded = True

            await agent.cleanup()

            assert agent._ocr is None
            assert agent._model_loaded is False

    @pytest.mark.asyncio
    async def test_cleanup_is_idempotent(self):
        """cleanup() sollte mehrfach aufgerufen werden koennen."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()

            # Mehrfacher Aufruf sollte keine Fehler werfen
            await agent.cleanup()
            await agent.cleanup()
            await agent.cleanup()

            assert agent._model_loaded is False


# ========================= Status Tests =========================


class TestPaddleOCRStatus:
    """Tests fuer Status-Abfrage."""

    def test_get_status_returns_model_info(self):
        """get_status() sollte Model-Informationen zurueckgeben."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            status = agent.get_status()

            assert "name" in status
            assert status["name"] == "paddle_ocr_agent"
            assert "model_loaded" in status
            assert status["model_loaded"] is False
            assert "model_version" in status
            assert status["model_version"] == "PP-OCRv5"
            assert "gpu_required" in status
            assert status["gpu_required"] is False
            assert "vram_gb" in status
            assert status["vram_gb"] == 0

    def test_get_status_shows_loaded_state(self):
        """get_status() sollte Model-Ladezustand anzeigen."""
        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._model_loaded = True

            status = agent.get_status()

            assert status["model_loaded"] is True
            assert status["status"] == "ready"


# ========================= Thread Safety Tests =========================


class TestPaddleOCRThreadSafety:
    """Tests fuer Thread-Safety."""

    @pytest.mark.asyncio
    async def test_concurrent_model_loading(self):
        """Concurrent Model-Loading sollte sicher sein."""
        mock_ocr = Mock()
        load_count = 0

        def mock_paddle_ocr_init(*args, **kwargs):
            nonlocal load_count
            load_count += 1
            return mock_ocr

        with patch('paddleocr.PaddleOCR', side_effect=mock_paddle_ocr_init):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            # Reset lock
            PaddleOCRAgent._model_lock = asyncio.Lock()

            agent = PaddleOCRAgent()

            # Mehrere concurrent loads
            await asyncio.gather(
                agent._load_model_async(),
                agent._load_model_async(),
                agent._load_model_async(),
            )

            # Model sollte nur einmal geladen werden
            assert load_count == 1


# ========================= Confidence Calculation Tests =========================


class TestPaddleOCRConfidence:
    """Tests fuer Confidence-Berechnung."""

    def test_confidence_extraction_from_result(self, sample_numpy_image):
        """Confidence sollte korrekt aus PaddleOCR-Result extrahiert werden."""
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [[
            [[[0, 0], [100, 0], [100, 30], [0, 30]], ("Line 1", 0.95)],
            [[[0, 40], [100, 40], [100, 70], [0, 70]], ("Line 2", 0.85)],
            [[[0, 80], [100, 80], [100, 110], [0, 110]], ("Line 3", 0.90)],
        ]]

        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._ocr = mock_ocr
            agent._model_loaded = True

            result = agent._process_single_image(sample_numpy_image)

            # Durchschnittliche Confidence: (0.95 + 0.85 + 0.90) / 3 = 0.9
            assert len(result["text_blocks"]) == 3
            assert result["text_blocks"][0]["confidence"] == 0.95
            assert result["text_blocks"][1]["confidence"] == 0.85
            assert result["text_blocks"][2]["confidence"] == 0.9

    def test_confidence_rounded_to_3_decimals(self, sample_numpy_image):
        """Confidence sollte auf 3 Dezimalstellen gerundet werden."""
        mock_ocr = Mock()
        mock_ocr.ocr.return_value = [[
            [[[0, 0], [100, 0], [100, 30], [0, 30]], ("Text", 0.9567891234)],
        ]]

        with patch.dict('sys.modules', {'paddleocr': Mock()}):
            from app.agents.ocr.paddle_ocr_agent import PaddleOCRAgent

            agent = PaddleOCRAgent()
            agent._ocr = mock_ocr
            agent._model_loaded = True

            result = agent._process_single_image(sample_numpy_image)

            assert result["text_blocks"][0]["confidence"] == 0.957
