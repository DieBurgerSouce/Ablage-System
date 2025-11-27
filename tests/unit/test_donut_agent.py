# -*- coding: utf-8 -*-
"""
Unit tests for Donut OCR Agent.

Tests:
- Agent initialization
- Language support
- Model loading (mocked)
- Image processing
- Batch processing
- Task prompts
- Error handling
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestDonutAgentInitialization:
    """Test Donut agent initialization."""

    @pytest.fixture
    def mock_gpu_manager(self):
        """Mock GPUManager."""
        with patch('app.agents.ocr.donut_agent.GPUManager') as mock:
            gpu_manager = Mock()
            gpu_manager.allocate_for_backend.return_value = {"success": True}
            gpu_manager.release = Mock()
            mock.return_value = gpu_manager
            yield gpu_manager

    @pytest.fixture
    def mock_torch(self):
        """Mock torch for CUDA tests."""
        with patch('app.agents.ocr.donut_agent.torch') as mock_torch:
            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.empty_cache = Mock()
            mock_torch.device = lambda x: x
            mock_torch.no_grad.return_value.__enter__ = Mock()
            mock_torch.no_grad.return_value.__exit__ = Mock()
            yield mock_torch

    @pytest.fixture
    def agent(self, mock_gpu_manager, mock_torch):
        """Create Donut agent with mocks."""
        with patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    def test_agent_initialization(self, agent):
        """Test agent initializes with correct defaults."""
        assert agent.name == "donut_ocr_agent"
        assert agent.gpu_required == False  # Can run on CPU
        assert agent.vram_gb == 8
        assert agent._model_loaded == False

    @pytest.mark.unit
    def test_agent_model_configuration(self, agent):
        """Test model configuration constants."""
        assert "donut" in agent.MODEL_NAME.lower()
        assert agent.VRAM_REQUIRED_GB == 8
        assert agent.MAX_BATCH_SIZE == 8

    @pytest.mark.unit
    def test_safetensors_enabled(self, mock_gpu_manager, mock_torch):
        """Test SafeTensors is enabled by default."""
        with patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent

            agent = DonutOCRAgent(use_safetensors=True)

            assert agent.use_safetensors == True


class TestDonutLanguageSupport:
    """Test language support functionality."""

    @pytest.fixture
    def agent(self):
        """Create agent for language tests."""
        with patch('app.agents.ocr.donut_agent.GPUManager'), \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    def test_supported_languages(self, agent):
        """Test supported languages list."""
        languages = agent.get_supported_languages()

        assert isinstance(languages, list)
        assert len(languages) > 0

        # Priority languages
        assert "de" in languages
        assert "en" in languages
        assert "pl" in languages
        assert "ru" in languages
        assert "uk" in languages

        # Asian languages
        assert "ja" in languages
        assert "ko" in languages
        assert "zh" in languages

    @pytest.mark.unit
    def test_german_supported(self, agent):
        """Test German is supported."""
        assert agent.is_language_supported("de") == True
        assert agent.is_language_supported("DE") == True

    @pytest.mark.unit
    def test_polish_supported(self, agent):
        """Test Polish is supported."""
        assert agent.is_language_supported("pl") == True

    @pytest.mark.unit
    def test_russian_supported(self, agent):
        """Test Russian is supported."""
        assert agent.is_language_supported("ru") == True

    @pytest.mark.unit
    def test_ukrainian_supported(self, agent):
        """Test Ukrainian is supported."""
        assert agent.is_language_supported("uk") == True

    @pytest.mark.unit
    def test_unsupported_language(self, agent):
        """Test detection of unsupported language."""
        # Assuming 'xx' is not supported
        assert agent.is_language_supported("xx") == False


class TestDonutTaskPrompts:
    """Test task prompt configuration."""

    @pytest.fixture
    def agent(self):
        """Create agent for prompt tests."""
        with patch('app.agents.ocr.donut_agent.GPUManager'), \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    def test_task_prompts_defined(self, agent):
        """Test task prompts are defined."""
        assert "ocr" in agent.TASK_PROMPTS
        assert "docvqa" in agent.TASK_PROMPTS
        assert "parsing" in agent.TASK_PROMPTS

    @pytest.mark.unit
    def test_ocr_prompt(self, agent):
        """Test OCR task prompt."""
        prompt = agent.TASK_PROMPTS["ocr"]
        assert len(prompt) > 0

    @pytest.mark.unit
    def test_docvqa_prompt_has_placeholder(self, agent):
        """Test DocVQA prompt has question placeholder."""
        prompt = agent.TASK_PROMPTS["docvqa"]
        assert "{question}" in prompt


class TestDonutProcessing:
    """Test document processing."""

    @pytest.fixture
    def mock_agent(self):
        """Create fully mocked agent."""
        with patch('app.agents.ocr.donut_agent.GPUManager') as mock_gm, \
             patch('app.agents.ocr.donut_agent.torch') as mock_torch, \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):

            mock_gm.return_value.allocate_for_backend.return_value = {"success": True}
            mock_gm.return_value.release = Mock()

            mock_torch.cuda.is_available.return_value = True
            mock_torch.cuda.empty_cache = Mock()
            mock_torch.device = lambda x: x

            from app.agents.ocr.donut_agent import DonutOCRAgent
            agent = DonutOCRAgent()

            # Mock model as loaded
            agent._model_loaded = True
            agent.model = Mock()
            agent.processor = Mock()
            agent._device = "cuda"

            yield agent

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_validates_input(self, mock_agent):
        """Test that process validates required input fields."""
        with pytest.raises(ValueError, match="Missing required input keys"):
            await mock_agent.process({})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_validates_document_id(self, mock_agent):
        """Test that process requires document_id."""
        with pytest.raises(ValueError, match="document_id"):
            await mock_agent.process({"image_path": "/some/path.png"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_process_validates_image_path(self, mock_agent):
        """Test that process requires image_path."""
        with pytest.raises(ValueError, match="image_path"):
            await mock_agent.process({"document_id": "doc123"})


class TestDonutImageLoading:
    """Test image loading functionality."""

    @pytest.fixture
    def agent(self):
        """Create agent for image tests."""
        with patch('app.agents.ocr.donut_agent.GPUManager'), \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_nonexistent_image(self, agent):
        """Test error handling for non-existent image."""
        with pytest.raises(FileNotFoundError):
            await agent._load_image(Path("/nonexistent/image.png"))

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_load_valid_image(self, agent, tmp_path):
        """Test loading a valid image file."""
        from PIL import Image

        img_path = tmp_path / "test.png"
        img = Image.new('RGB', (800, 600), color='white')
        img.save(img_path)

        loaded = await agent._load_image(Path(img_path))

        assert loaded.size == (800, 600)
        assert loaded.mode == "RGB"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_large_image_resized(self, agent, tmp_path):
        """Test that large images are resized."""
        from PIL import Image

        # Create large image
        img_path = tmp_path / "large.png"
        img = Image.new('RGB', (3000, 2000), color='white')
        img.save(img_path)

        loaded = await agent._load_image(Path(img_path))

        # Should be resized to max 1920
        assert max(loaded.size) <= 1920


class TestDonutBatchProcessing:
    """Test batch processing functionality."""

    @pytest.fixture
    def agent(self):
        """Create agent for batch tests."""
        with patch('app.agents.ocr.donut_agent.GPUManager') as mock_gm, \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):

            mock_gm.return_value.allocate_for_backend.return_value = {"success": True}

            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    def test_batch_size_limit(self, agent):
        """Test maximum batch size."""
        assert agent.MAX_BATCH_SIZE == 8

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_batch_processing_structure(self, agent, tmp_path):
        """Test batch processing with mocked process."""
        from PIL import Image

        # Create test images
        image_paths = []
        for i in range(3):
            img_path = tmp_path / f"test_{i}.png"
            img = Image.new('RGB', (100, 100), color='white')
            img.save(img_path)
            image_paths.append(img_path)

        # Mock the process method
        agent.process = AsyncMock(return_value={
            "text": "Test text",
            "confidence": 0.9,
        })

        results = await agent.process_batch(image_paths)

        assert len(results) == 3
        assert agent.process.call_count == 3


class TestDonutModelUnloading:
    """Test model unloading functionality."""

    @pytest.fixture
    def agent_with_model(self):
        """Create agent with mocked loaded model."""
        with patch('app.agents.ocr.donut_agent.GPUManager') as mock_gm, \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', False):
            # Set TORCH_AVAILABLE to False to skip the torch.cuda.empty_cache() call
            # which reimports torch internally

            mock_gm.return_value.allocate_for_backend.return_value = {"success": True}
            mock_gm.return_value.release = Mock()

            from app.agents.ocr.donut_agent import DonutOCRAgent
            agent = DonutOCRAgent()

            # Pretend model is loaded
            agent._model_loaded = True
            agent.model = Mock()
            agent.processor = Mock()

            yield agent, mock_gm

    @pytest.mark.unit
    def test_unload_model(self, agent_with_model):
        """Test model unloading clears model and calls GPU release."""
        agent, mock_gm = agent_with_model

        agent.unload_model()

        assert agent._model_loaded == False
        assert agent.model is None
        assert agent.processor is None
        mock_gm.return_value.release.assert_called_with("donut")

    @pytest.mark.unit
    def test_unload_model_already_unloaded(self, agent_with_model):
        """Test unload_model when already unloaded."""
        agent, mock_gm = agent_with_model

        # First unload
        agent.unload_model()

        # Second unload should not fail
        agent.unload_model()

        assert agent._model_loaded == False
        assert agent.model is None


class TestDonutHealthCheck:
    """Test health check functionality."""

    @pytest.fixture
    def agent(self):
        """Create agent for health tests."""
        with patch('app.agents.ocr.donut_agent.GPUManager'), \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_health_check_unloaded(self, agent):
        """Test health check when model not loaded."""
        # Model not loaded, so health check needs to load it
        # Mock the model loading to fail
        agent._ensure_model_loaded = AsyncMock(side_effect=Exception("Load failed"))

        result = await agent.health_check()

        assert result == False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_health_check_loaded(self, agent):
        """Test health check when model is loaded."""
        agent._model_loaded = True
        agent.model = Mock()
        agent.processor = Mock()

        result = await agent.health_check()

        assert result == True


class TestDonutAvailability:
    """Test Donut availability check."""

    @pytest.mark.unit
    def test_donut_available_with_deps(self):
        """Test is_donut_available when deps installed."""
        with patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import is_donut_available

            assert is_donut_available() == True

    @pytest.mark.unit
    def test_donut_unavailable_no_transformers(self):
        """Test is_donut_available without transformers."""
        with patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', False), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import is_donut_available

            assert is_donut_available() == False

    @pytest.mark.unit
    def test_donut_unavailable_no_torch(self):
        """Test is_donut_available without torch."""
        with patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', False):
            from app.agents.ocr.donut_agent import is_donut_available

            assert is_donut_available() == False


class TestDonutConfidenceCalculation:
    """Test confidence score calculation."""

    @pytest.fixture
    def agent(self):
        """Create agent for confidence tests."""
        with patch('app.agents.ocr.donut_agent.GPUManager'), \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    def test_confidence_default(self, agent):
        """Test default confidence when scores not available."""
        mock_outputs = Mock()
        mock_outputs.scores = None

        confidence = agent._calculate_confidence(mock_outputs)

        assert confidence == 0.85  # Default value


class TestDonutStructureParsing:
    """Test structure parsing functionality."""

    @pytest.fixture
    def agent(self):
        """Create agent for structure tests."""
        with patch('app.agents.ocr.donut_agent.GPUManager'), \
             patch('app.agents.ocr.donut_agent.TRANSFORMERS_AVAILABLE', True), \
             patch('app.agents.ocr.donut_agent.TORCH_AVAILABLE', True):
            from app.agents.ocr.donut_agent import DonutOCRAgent
            return DonutOCRAgent()

    @pytest.mark.unit
    def test_parse_structure_ocr_task(self, agent):
        """Test structure parsing for OCR task."""
        text = "Some extracted text"
        structure = agent._parse_structure(text, "ocr")

        assert "raw_output" in structure
        assert structure["raw_output"] == text

    @pytest.mark.unit
    def test_parse_structure_parsing_task(self, agent):
        """Test structure parsing for parsing task."""
        text = 'Some text {"key": "value"} more text'
        structure = agent._parse_structure(text, "parsing")

        assert "raw_output" in structure
        # Should try to parse JSON
        if "parsed" in structure:
            assert structure["parsed"]["key"] == "value"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "unit"])
