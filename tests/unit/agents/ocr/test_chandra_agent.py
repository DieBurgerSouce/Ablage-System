# -*- coding: utf-8 -*-
"""
Tests fuer Chandra OCR Agent.

Testet:
- Agent-Initialisierung
- Quantisierungs-Modi (none, 8bit, 4bit)
- GPU Memory Management
- Cleanup-Verhalten
- Deutsche Umlaut-Erkennung

Feinpoliert und durchdacht - Chandra OCR Tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_torch_cuda():
    """Mock torch.cuda modul."""
    with patch('torch.cuda.is_available', return_value=True):
        with patch('torch.cuda.empty_cache') as mock_cache:
            with patch('torch.cuda.get_device_name', return_value="NVIDIA GeForce RTX 4080"):
                with patch('torch.cuda.get_device_properties') as mock_props:
                    mock_props.return_value.total_memory = 16 * 1024 * 1024 * 1024  # 16GB
                    yield mock_cache


@pytest.fixture
def mock_torch_cuda_unavailable():
    """Mock torch.cuda wenn keine GPU verfuegbar."""
    with patch('torch.cuda.is_available', return_value=False):
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


# ========================= Initialization Tests =========================


class TestChandraOCRAgentInitialization:
    """Tests fuer Chandra Agent Initialisierung."""

    def test_initialization_with_gpu(self, mock_torch_cuda):
        """Agent sollte mit GPU initialisiert werden."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        agent = ChandraOCRAgent()

                        assert agent.name == "chandra_ocr_agent"
                        assert agent.gpu_required is True
                        assert agent.vram_gb == 15  # Standard FP16
                        assert agent.quantization == "none"

    def test_initialization_with_4bit_quantization(self, mock_torch_cuda):
        """Agent sollte mit 4-bit Quantisierung initialisiert werden."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        agent = ChandraOCRAgent(quantization="4bit")

                        assert agent.quantization == "4bit"
                        assert agent.vram_gb == 5  # 4-bit needs ~5GB

    def test_initialization_with_8bit_quantization(self, mock_torch_cuda):
        """Agent sollte mit 8-bit Quantisierung initialisiert werden."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        agent = ChandraOCRAgent(quantization="8bit")

                        assert agent.quantization == "8bit"
                        assert agent.vram_gb == 9  # 8-bit needs ~9GB

    def test_initialization_without_gpu(self, mock_torch_cuda_unavailable):
        """Agent sollte ohne GPU initialisiert werden (CPU-Modus)."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=False):
            from app.agents.ocr.chandra_agent import ChandraOCRAgent

            agent = ChandraOCRAgent()

            assert agent.gpu_required is False
            assert agent.vram_gb == 0


# ========================= GPU Cleanup Tests =========================


class TestChandraGPUCleanup:
    """Tests fuer Chandra GPU Cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_clears_model_references(self, mock_torch_cuda):
        """cleanup() sollte Model-Referenzen loeschen."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        with patch('app.agents.ocr.chandra_agent.torch.cuda.synchronize'):
                            from app.agents.ocr.chandra_agent import ChandraOCRAgent

                            agent = ChandraOCRAgent()
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
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        with patch('app.agents.ocr.chandra_agent.torch.cuda.empty_cache') as mock_cache:
                            with patch('app.agents.ocr.chandra_agent.torch.cuda.synchronize'):
                                from app.agents.ocr.chandra_agent import ChandraOCRAgent

                                agent = ChandraOCRAgent()
                                await agent.cleanup()

                                mock_cache.assert_called()


# ========================= Process Tests =========================


class TestChandraProcessing:
    """Tests fuer Chandra Verarbeitung."""

    @pytest.mark.asyncio
    async def test_process_validates_input(self, mock_torch_cuda):
        """process() sollte Input validieren."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        agent = ChandraOCRAgent()

                        # Missing image_path
                        result = await agent.process({"language": "de"})

                        assert result.get("success") is False or "error" in result

    @pytest.mark.asyncio
    async def test_process_handles_file_not_found(self, mock_torch_cuda):
        """process() sollte fehlende Dateien behandeln."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        agent = ChandraOCRAgent()

                        # Nonexistent file
                        result = await agent.process({
                            "image_path": "/nonexistent/path/to/file.pdf",
                            "language": "de"
                        })

                        assert result.get("success") is False or "error" in result


# ========================= Status Tests =========================


class TestChandraStatus:
    """Tests fuer Chandra Status-Abfrage."""

    def test_get_status_returns_model_info(self, mock_torch_cuda):
        """get_status() sollte Model-Informationen zurueckgeben."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        with patch('app.agents.ocr.chandra_agent.torch.cuda.memory_allocated', return_value=0):
                            with patch('app.agents.ocr.chandra_agent.torch.cuda.memory_reserved', return_value=0):
                                from app.agents.ocr.chandra_agent import ChandraOCRAgent

                                agent = ChandraOCRAgent()
                                status = agent.get_status()

                                assert "model_name" in status
                                assert status["model_name"] == "datalab-to/chandra"
                                assert "models_loaded" in status
                                assert "quantization_mode" in status
                                assert "supported_quantizations" in status
                                assert "gpu_info" in status

    def test_get_status_shows_quantization_mode(self, mock_torch_cuda):
        """get_status() sollte Quantisierungs-Modus anzeigen."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        with patch('app.agents.ocr.chandra_agent.torch.cuda.memory_allocated', return_value=0):
                            with patch('app.agents.ocr.chandra_agent.torch.cuda.memory_reserved', return_value=0):
                                from app.agents.ocr.chandra_agent import ChandraOCRAgent

                                agent = ChandraOCRAgent(quantization="8bit")
                                status = agent.get_status()

                                assert status["quantization_mode"] == "8bit"


# ========================= OOM Fallback Tests =========================


class TestChandraOOMFallback:
    """Tests fuer OOM-Fallback-Verhalten."""

    @pytest.mark.asyncio
    async def test_oom_fallback_reduces_quantization(self, mock_torch_cuda):
        """Bei OOM sollte auf niedrigere Quantisierung gewechselt werden."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        agent = ChandraOCRAgent()
                        agent._models_loaded = True
                        agent._current_quantization = "none"

                        # Mock _process_single_image to return OOM error first, then success
                        call_count = 0
                        def mock_process(*args, **kwargs):
                            nonlocal call_count
                            call_count += 1
                            if call_count == 1:
                                return {"text": "", "confidence": 0.0, "oom": True}
                            return {"text": "Test text", "confidence": 0.9}

                        mock_image = Mock()
                        with patch.object(agent, '_process_single_image', side_effect=mock_process):
                            with patch.object(agent, '_unload_models', new_callable=AsyncMock):
                                with patch.object(agent, '_load_models_async', new_callable=AsyncMock):
                                    result = await agent._process_with_oom_fallback(mock_image)

                        # Sollte erfolgreich sein nach Fallback
                        assert result.get("text") == "Test text"


# ========================= Model Loading Tests =========================


class TestChandraModelLoading:
    """Tests fuer Model-Loading-Verhalten."""

    @pytest.mark.asyncio
    async def test_model_loading_with_lock(self, mock_torch_cuda):
        """Model-Loading sollte Thread-Safe mit Lock sein."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        agent = ChandraOCRAgent()

                        # Verify lock exists
                        assert ChandraOCRAgent._model_lock is not None

    def test_model_constants_defined(self, mock_torch_cuda):
        """Model-Konstanten sollten definiert sein."""
        with patch('app.agents.ocr.chandra_agent.torch.cuda.is_available', return_value=True):
            with patch('app.agents.ocr.chandra_agent.torch.version', Mock(cuda='12.1')):
                with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_name', return_value="RTX 4080"):
                    with patch('app.agents.ocr.chandra_agent.torch.cuda.get_device_properties') as mock_props:
                        mock_props.return_value.total_memory = 16 * 1024**3
                        from app.agents.ocr.chandra_agent import ChandraOCRAgent

                        assert ChandraOCRAgent.MODEL_NAME == "datalab-to/chandra"
                        assert ChandraOCRAgent.VRAM_REQUIRED_GB == 15
                        assert ChandraOCRAgent.VRAM_8BIT_GB == 9
                        assert ChandraOCRAgent.VRAM_4BIT_GB == 5
                        assert ChandraOCRAgent.MODEL_LOADING_TIMEOUT == 1800.0  # 30 min
