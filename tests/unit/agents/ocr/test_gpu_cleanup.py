# -*- coding: utf-8 -*-
"""
Tests fuer GPU Cleanup in OCR Agents.

Testet:
- GPU Memory Cleanup nach erfolgreicher Verarbeitung
- GPU Memory Cleanup bei Fehlern
- finally Block Verhalten

Feinpoliert und durchdacht - GPU Memory Management Tests.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path


# ========================= Test Fixtures =========================


@pytest.fixture
def mock_torch_cuda():
    """Mock torch.cuda modul.

    Diese Tests laufen im CPU-OCR-Container OHNE GPU (CUDA_VISIBLE_DEVICES='').
    Da der App-Code `is_available()` auf True gemockt bekommt, MUESSEN auch alle
    weiteren CUDA-Aufrufe innerhalb des `if torch.cuda.is_available()`-Zweigs
    gemockt werden (sonst RuntimeError: No CUDA GPUs are available). Der Cleanup-
    Vertrag ruft synchronize() VOR empty_cache() auf -> beides hier mocken.
    """
    with patch('torch.cuda.is_available', return_value=True):
        with patch('torch.cuda.synchronize'):
            with patch('torch.cuda.empty_cache') as mock_cache:
                yield mock_cache


@pytest.fixture
def mock_torch_cuda_unavailable():
    """Mock torch.cuda wenn keine GPU verfuegbar."""
    with patch('torch.cuda.is_available', return_value=False):
        yield


@pytest.fixture
def mock_gpu_manager():
    """Mock GPUManager."""
    manager = Mock()
    manager.allocate_for_backend.return_value = {"success": True, "mode": "gpu"}
    manager.deallocate_backend.return_value = True
    manager.handle_oom_error.return_value = {"recovered": True}
    manager.get_optimal_batch_size.return_value = 4
    return manager


@pytest.fixture
def mock_surya_cuda():
    """Mock saemtliche torch.cuda-Aufrufe im surya_gpu_agent-Modul.

    SuryaGPUAgent.__init__ ruft bei is_available()==True zusaetzlich
    get_device_name/get_device_properties/version.cuda auf, process() ruft
    memory_allocated()/synchronize(). Im CPU-OCR-Container ohne GPU muessen
    daher ALLE diese Aufrufe gemockt werden, nicht nur is_available/empty_cache.
    Gibt den empty_cache-Mock zum Assert zurueck.
    """
    props = MagicMock()
    props.total_memory = 16 * 1024**3
    props.name = "Mock-GPU"
    with patch('app.agents.ocr.surya_gpu_agent.torch.cuda.is_available', return_value=True), \
         patch('app.agents.ocr.surya_gpu_agent.torch.cuda.synchronize'), \
         patch('app.agents.ocr.surya_gpu_agent.torch.cuda.get_device_name', return_value="Mock-GPU"), \
         patch('app.agents.ocr.surya_gpu_agent.torch.cuda.get_device_properties', return_value=props), \
         patch('app.agents.ocr.surya_gpu_agent.torch.cuda.memory_allocated', return_value=0), \
         patch('app.agents.ocr.surya_gpu_agent.torch.cuda.max_memory_allocated', return_value=0), \
         patch('app.agents.ocr.surya_gpu_agent.torch.cuda.memory_reserved', return_value=0), \
         patch('app.agents.ocr.surya_gpu_agent.torch.cuda.empty_cache') as mock_cache:
        yield mock_cache


@pytest.fixture
def mock_image():
    """Mock PIL Image."""
    image = Mock()
    image.size = (800, 600)
    image.mode = "RGB"
    image.convert.return_value = image
    image.copy.return_value = image
    return image


# ========================= GOT-OCR Cleanup Tests =========================


class TestGOTOCRGPUCleanup:
    """Tests fuer GOT-OCR GPU Cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_called_on_success(self, mock_torch_cuda, mock_gpu_manager, mock_image):
        """GPU Cleanup sollte nach erfolgreicher Verarbeitung aufgerufen werden."""
        with patch('app.agents.ocr.got_ocr_agent.GPUManager', return_value=mock_gpu_manager):
            from app.agents.ocr.got_ocr_agent import GOTOCRAgent

            agent = GOTOCRAgent()
            agent._model_loaded = True
            agent.model = Mock()
            agent.processor = Mock()

            # Mock _run_ocr to return valid result
            mock_result = Mock()
            mock_result.text = "Test text"
            mock_result.confidence = 0.9
            mock_result.to_dict.return_value = {"text": "Test text", "confidence": 0.9}

            with patch.object(agent, '_run_ocr', new_callable=AsyncMock, return_value=mock_result):
                with patch.object(agent, '_load_image', new_callable=AsyncMock, return_value=mock_image):
                    with patch.object(agent, '_allocate_device', new_callable=AsyncMock, return_value='cuda'):
                        with patch.object(agent, '_load_model', new_callable=AsyncMock):
                            with patch.object(agent, '_postprocess_german', new_callable=AsyncMock, return_value=mock_result):
                                with patch('pathlib.Path.exists', return_value=True):
                                    await agent.process({
                                        "document_id": "test-123",
                                        "image_path": "/test/image.png"
                                    })

            # Verify empty_cache was called (by finally block)
            mock_torch_cuda.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_called_on_error(self, mock_torch_cuda, mock_gpu_manager):
        """GPU Cleanup sollte auch bei Fehlern aufgerufen werden."""
        with patch('app.agents.ocr.got_ocr_agent.GPUManager', return_value=mock_gpu_manager):
            from app.agents.ocr.got_ocr_agent import GOTOCRAgent

            agent = GOTOCRAgent()
            agent._model_loaded = True
            agent.model = Mock()

            # Mock _load_image to raise exception
            with patch.object(agent, '_load_image', new_callable=AsyncMock, side_effect=ValueError("Test error")):
                with patch.object(agent, '_allocate_device', new_callable=AsyncMock, return_value='cuda'):
                    with patch.object(agent, '_load_model', new_callable=AsyncMock):
                        try:
                            await agent.process({
                                "document_id": "test-123",
                                "image_path": "/test/image.png"
                            })
                        except ValueError:
                            pass  # Expected

            # Verify empty_cache was still called (by finally block)
            mock_torch_cuda.assert_called()

    def test_cleanup_method_exists(self):
        """_cleanup_gpu_resources Methode sollte existieren."""
        with patch('app.agents.ocr.got_ocr_agent.GPUManager'):
            from app.agents.ocr.got_ocr_agent import GOTOCRAgent

            agent = GOTOCRAgent()
            assert hasattr(agent, '_cleanup_gpu_resources')
            assert callable(getattr(agent, '_cleanup_gpu_resources'))


# ========================= DeepSeek Cleanup Tests =========================


class TestDeepSeekGPUCleanup:
    """Tests fuer DeepSeek GPU Cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_method_exists(self):
        """_cleanup_gpu_resources Methode sollte existieren."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager'):
            from app.agents.ocr.deepseek_agent import DeepSeekAgent

            agent = DeepSeekAgent()
            assert hasattr(agent, '_cleanup_gpu_resources')
            assert callable(getattr(agent, '_cleanup_gpu_resources'))

    @pytest.mark.asyncio
    async def test_cleanup_clears_cache(self, mock_torch_cuda):
        """_cleanup_gpu_resources sollte torch.cuda.empty_cache aufrufen."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager'):
            from app.agents.ocr.deepseek_agent import DeepSeekAgent

            agent = DeepSeekAgent()
            await agent._cleanup_gpu_resources()

            mock_torch_cuda.assert_called_once()


# ========================= Surya GPU Cleanup Tests =========================


class TestSuryaGPUCleanup:
    """Tests fuer Surya GPU Agent Cleanup."""

    def test_process_has_finally_block(self):
        """process() sollte einen finally Block haben."""
        import inspect
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        # Get source code of process method
        source = inspect.getsource(SuryaGPUAgent.process)

        # Check that finally block exists
        assert 'finally:' in source, "process() sollte einen finally Block haben"
        assert 'empty_cache' in source, "finally Block sollte empty_cache aufrufen"

    @pytest.mark.asyncio
    async def test_cleanup_called_on_success(self, mock_surya_cuda):
        """GPU Cleanup sollte nach erfolgreicher Verarbeitung aufgerufen werden."""
        mock_cache = mock_surya_cuda
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()
        agent._models_loaded = True

        # Mock _load_image and _process_single_image
        mock_image = Mock()
        with patch.object(agent, '_load_image', return_value=[mock_image]):
            with patch.object(agent, '_process_single_image', return_value={
                "text": "Test text",
                "confidence": 0.9,
                "text_regions": 1,
                "german_chars_found": []
            }):
                result = await agent.process("/test/image.png")

        # Verify empty_cache was called (by finally block)
        assert mock_cache.called

    @pytest.mark.asyncio
    async def test_cleanup_called_on_error(self, mock_surya_cuda):
        """GPU Cleanup sollte auch bei Fehlern aufgerufen werden."""
        mock_cache = mock_surya_cuda
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()

        # Mock _load_image to raise exception
        with patch.object(agent, '_load_image', side_effect=FileNotFoundError("Test error")):
            result = await agent.process("/nonexistent/image.png")

            # Should return error result, not raise
            assert "error" in result or result.get("status") == "error"

        # Verify empty_cache was still called (by finally block)
        assert mock_cache.called


# ========================= Full Cleanup Tests =========================


class TestFullCleanupMethod:
    """Tests fuer vollstaendige cleanup() Methoden."""

    @pytest.mark.asyncio
    async def test_got_ocr_full_cleanup(self, mock_torch_cuda):
        """GOT-OCR cleanup() sollte alle Ressourcen freigeben."""
        with patch('app.agents.ocr.got_ocr_agent.GPUManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            with patch('torch.cuda.synchronize'):
                from app.agents.ocr.got_ocr_agent import GOTOCRAgent

                agent = GOTOCRAgent()
                agent.model = Mock()
                agent.processor = Mock()
                agent._model_loaded = True

                await agent.cleanup()

                assert agent.model is None
                assert agent.processor is None
                assert agent._model_loaded is False
                mock_manager.deallocate_backend.assert_called_once_with("got_ocr")

    @pytest.mark.asyncio
    async def test_deepseek_full_cleanup(self, mock_torch_cuda):
        """DeepSeek cleanup() sollte alle Ressourcen freigeben."""
        with patch('app.agents.ocr.deepseek_agent.GPUManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            with patch('torch.cuda.synchronize'):
                from app.agents.ocr.deepseek_agent import DeepSeekAgent

                agent = DeepSeekAgent()
                agent.model = Mock()
                agent.processor = Mock()
                agent._model_loaded = True

                await agent.cleanup()

                assert agent.model is None
                assert agent.processor is None
                assert agent._model_loaded is False
                mock_manager.deallocate_backend.assert_called_once_with("deepseek")

    @pytest.mark.asyncio
    async def test_surya_full_cleanup(self, mock_surya_cuda):
        """Surya cleanup() sollte alle Ressourcen freigeben."""
        from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent

        agent = SuryaGPUAgent()
        agent._det_predictor = Mock()
        agent._rec_predictor = Mock()
        agent._foundation_predictor = Mock()
        agent._models_loaded = True

        await agent.cleanup()

        assert agent._det_predictor is None
        assert agent._rec_predictor is None
        assert agent._foundation_predictor is None
        assert agent._models_loaded is False
