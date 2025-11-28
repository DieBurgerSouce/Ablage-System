"""Unit-Tests fuer den Embedding-Service.

Testet die Embedding-Generierung mit Mocks fuer GPU-unabhaengige Tests.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import List
import numpy as np
import sys

# Check if sentence_transformers is available
try:
    import sentence_transformers
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Skip marker for tests requiring sentence_transformers
requires_sentence_transformers = pytest.mark.skipif(
    not SENTENCE_TRANSFORMERS_AVAILABLE,
    reason="sentence_transformers not installed"
)


class TestEmbeddingServiceBasic:
    """Grundlegende Tests fuer EmbeddingService ohne Modell-Loading."""

    def test_embedding_dimension_constant(self):
        """Test dass Embedding-Dimension korrekt ist."""
        from app.core.config import settings
        assert settings.EMBEDDING_DIMENSION == 1024

    def test_embedding_model_name(self):
        """Test Modellname aus Settings."""
        from app.core.config import settings
        assert "e5" in settings.EMBEDDING_MODEL.lower() or "multilingual" in settings.EMBEDDING_MODEL.lower()

    def test_get_embedding_service_singleton(self):
        """Test dass get_embedding_service Singleton zurueckgibt."""
        from app.services.embedding_service import get_embedding_service

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2


class TestEmbeddingServiceWithMocks:
    """Tests mit vollstaendig gemockten Dependencies."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        from app.services.embedding_service import EmbeddingService
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None
        yield
        # Cleanup
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None

    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_init_creates_cpu_device(self, mock_settings, mock_torch):
        """Test CPU-Device Erstellung."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_torch.cuda.is_available.return_value = False

        # Create mock device
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        assert service.model_name == "test-model"
        assert service.dimension == 1024
        mock_torch.device.assert_called_with("cpu")

    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_init_creates_gpu_device_when_available(self, mock_settings, mock_torch):
        """Test GPU-Device Erstellung wenn verfuegbar."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = True
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_name.return_value = "Test GPU"

        mock_props = Mock()
        mock_props.total_memory = 16 * 1024**3
        mock_torch.cuda.get_device_properties.return_value = mock_props

        mock_gpu_device = Mock()
        mock_gpu_device.type = "cuda"
        mock_torch.device.return_value = mock_gpu_device

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        mock_torch.device.assert_called_with("cuda")

    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_check_gpu_memory_cpu_mode(self, mock_settings, mock_torch):
        """Test GPU-Memory Check im CPU-Modus."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_torch.cuda.is_available.return_value = False

        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # CPU mode should always return True
        result = service._check_gpu_memory()
        assert result is True

    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_generate_batch_embeddings_empty_returns_empty(self, mock_settings, mock_torch):
        """Test Batch-Embedding mit leerer Liste gibt leere Liste zurueck."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_torch.cuda.is_available.return_value = False

        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        result = service.generate_batch_embeddings([])
        assert result == []


@requires_sentence_transformers
class TestEmbeddingServiceIntegration:
    """Integrationstests die das echte Modell-Loading mocken."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        from app.services.embedding_service import EmbeddingService
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None
        yield
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_generate_document_embedding(self, mock_settings, mock_torch, mock_st_class):
        """Test Embedding-Generierung fuer Dokument."""
        # Setup settings
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        # Setup torch
        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        # Setup model
        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()
        embedding = service.generate_document_embedding("Test Dokument Text")

        assert isinstance(embedding, list)
        assert len(embedding) == 1024
        # Verify passage prefix was added
        call_args = mock_model.encode.call_args
        assert "passage: " in call_args[0][0]

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_generate_query_embedding(self, mock_settings, mock_torch, mock_st_class):
        """Test Embedding-Generierung fuer Suchanfrage."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()
        embedding = service.generate_query_embedding("Rechnung 2024")

        assert isinstance(embedding, list)
        assert len(embedding) == 1024
        # Verify query prefix was added
        call_args = mock_model.encode.call_args
        assert "query: " in call_args[0][0]

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_generate_batch_embeddings(self, mock_settings, mock_torch, mock_st_class):
        """Test Batch-Embedding-Generierung."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(3, 1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()
        texts = ["Text 1", "Text 2", "Text 3"]
        embeddings = service.generate_batch_embeddings(texts)

        assert isinstance(embeddings, list)
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == 1024

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_get_model_info(self, mock_settings, mock_torch, mock_st_class):
        """Test Modell-Info Abruf."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()
        info = service.get_model_info()

        assert "model_name" in info
        assert "dimension" in info
        assert "max_length" in info
        assert "device" in info
        assert "loaded" in info

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_unload_model(self, mock_settings, mock_torch, mock_st_class):
        """Test Modell-Entladung."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # Force model loading
        service._ensure_model_loaded()
        assert service._model is not None

        # Unload model
        service.unload_model()
        assert service._model is None


@requires_sentence_transformers
@pytest.mark.asyncio
class TestEmbeddingServiceAsync:
    """Async-Tests fuer EmbeddingService."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        from app.services.embedding_service import EmbeddingService
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None
        yield
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    async def test_generate_embedding_async(self, mock_settings, mock_torch, mock_st_class):
        """Test asynchrone Embedding-Generierung."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()
        embedding = await service.generate_embedding_async("Test text", is_query=False)

        assert isinstance(embedding, list)
        assert len(embedding) == 1024

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    async def test_generate_batch_embeddings_async(self, mock_settings, mock_torch, mock_st_class):
        """Test asynchrone Batch-Embedding-Generierung."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(2, 1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()
        embeddings = await service.generate_batch_embeddings_async(["Text 1", "Text 2"])

        assert isinstance(embeddings, list)
        assert len(embeddings) == 2


@requires_sentence_transformers
class TestEmbeddingServiceEdgeCases:
    """Edge-Case-Tests fuer EmbeddingService."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset Singleton vor jedem Test."""
        from app.services.embedding_service import EmbeddingService
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None
        yield
        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        EmbeddingService._model = None

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_german_umlauts_handling(self, mock_settings, mock_torch, mock_st_class):
        """Test korrekte Verarbeitung deutscher Umlaute."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # Test with German umlauts
        german_text = "Rechnungsbetrag: 1.234,56 EUR - Überweisung an Müller GmbH"
        embedding = service.generate_document_embedding(german_text)

        assert isinstance(embedding, list)
        assert len(embedding) == 1024
        # Verify text was passed correctly
        call_args = mock_model.encode.call_args
        assert "Müller" in call_args[0][0] or "Muller" in call_args[0][0]

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_whitespace_only_text(self, mock_settings, mock_torch, mock_st_class):
        """Test Verhalten bei nur-Leerzeichen Text."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # Test with whitespace-only text
        whitespace_text = "   \t\n   "
        embedding = service.generate_document_embedding(whitespace_text)

        # Should still generate embedding (model handles empty/whitespace)
        assert isinstance(embedding, list)
        assert len(embedding) == 1024

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_special_characters_handling(self, mock_settings, mock_torch, mock_st_class):
        """Test Verarbeitung von Sonderzeichen."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # Test with various special characters
        special_text = "€1.000 @firma.de §§1-5 ½ ¾ © ® ™ \"quoted\" 'apostrophe'"
        embedding = service.generate_document_embedding(special_text)

        assert isinstance(embedding, list)
        assert len(embedding) == 1024

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_mixed_batch_with_empty_strings(self, mock_settings, mock_torch, mock_st_class):
        """Test Batch mit gemischtem Content inkl. leerer Strings."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        # Return embeddings for all texts including empty ones
        mock_model.encode.return_value = np.random.randn(4, 1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # Mixed batch with empty and whitespace strings
        texts = ["Normal text", "", "   ", "Another valid text"]
        embeddings = service.generate_batch_embeddings(texts)

        assert isinstance(embeddings, list)
        assert len(embeddings) == 4
        for emb in embeddings:
            assert len(emb) == 1024

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_very_short_text(self, mock_settings, mock_torch, mock_st_class):
        """Test Verarbeitung sehr kurzer Texte (einzelne Zeichen)."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # Single character text
        embedding = service.generate_document_embedding("a")

        assert isinstance(embedding, list)
        assert len(embedding) == 1024

    @patch("sentence_transformers.SentenceTransformer")
    @patch("app.services.embedding_service.torch")
    @patch("app.services.embedding_service.settings")
    def test_numeric_only_text(self, mock_settings, mock_torch, mock_st_class):
        """Test Verarbeitung von nur-numerischem Text."""
        mock_settings.EMBEDDING_MODEL = "test-model"
        mock_settings.EMBEDDING_DIMENSION = 1024
        mock_settings.EMBEDDING_MAX_LENGTH = 512
        mock_settings.EMBEDDING_BATCH_SIZE = 32
        mock_settings.ENABLE_GPU = False
        mock_settings.GPU_MEMORY_FRACTION = 0.85

        mock_torch.cuda.is_available.return_value = False
        mock_cpu_device = Mock()
        mock_cpu_device.type = "cpu"
        mock_torch.device.return_value = mock_cpu_device

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1024).astype(np.float32)
        mock_model.get_sentence_embedding_dimension.return_value = 1024
        mock_model.max_seq_length = 512
        mock_st_class.return_value = mock_model

        from app.services.embedding_service import EmbeddingService
        service = EmbeddingService()

        # Numeric-only text (like invoice numbers)
        numeric_text = "12345678901234567890"
        embedding = service.generate_document_embedding(numeric_text)

        assert isinstance(embedding, list)
        assert len(embedding) == 1024
