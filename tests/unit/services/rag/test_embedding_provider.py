"""Unit Tests fuer EmbeddingProvider und JinaEmbeddingService.

Testet Multi-Model Embedding-Generierung mit A/B Testing Support.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import numpy as np


# Mock torch vor dem Import
@pytest.fixture(autouse=True)
def mock_torch():
    """Mock torch fuer alle Tests."""
    with patch('app.services.embedding_service.torch') as mock:
        mock.cuda.is_available.return_value = False
        mock.device.return_value = MagicMock()
        yield mock


# Mock settings vor dem Import
@pytest.fixture(autouse=True)
def mock_settings(mock_torch):
    """Mock settings fuer alle Tests."""
    with patch('app.services.embedding_service.settings') as mock:
        mock.EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
        mock.EMBEDDING_DIMENSION = 1024
        mock.EMBEDDING_MAX_LENGTH = 512
        mock.EMBEDDING_BATCH_SIZE = 32
        mock.ENABLE_GPU = False
        mock.GPU_MEMORY_FRACTION = 0.85
        mock.JINA_EMBEDDING_ENABLED = True
        mock.JINA_EMBEDDING_MODEL = "jinaai/jina-embeddings-v2-base-de"
        mock.JINA_EMBEDDING_DIMENSION = 1024
        mock.JINA_EMBEDDING_MAX_LENGTH = 8192
        mock.JINA_TRUST_REMOTE_CODE = True
        mock.VECTOR_AB_TESTING_ENABLED = True
        yield mock


@pytest.fixture
def reset_singletons():
    """Reset alle Embedding-Singletons zwischen Tests."""
    import app.services.embedding_service as embedding_module
    from app.services.embedding_service import (
        EmbeddingService, JinaEmbeddingService, EmbeddingProvider
    )

    # Reset vor dem Test
    EmbeddingService._instance = None
    EmbeddingService._model = None
    EmbeddingService._initialized = False

    JinaEmbeddingService._instance = None
    JinaEmbeddingService._model = None
    JinaEmbeddingService._initialized = False

    EmbeddingProvider._instance = None

    # Reset auch die globalen Factory-Variablen
    embedding_module._jina_embedding_service = None
    embedding_module._embedding_provider = None

    yield

    # Cleanup nach dem Test
    EmbeddingService._instance = None
    EmbeddingService._model = None
    EmbeddingService._initialized = False

    JinaEmbeddingService._instance = None
    JinaEmbeddingService._model = None
    JinaEmbeddingService._initialized = False

    EmbeddingProvider._instance = None

    embedding_module._jina_embedding_service = None
    embedding_module._embedding_provider = None


@pytest.fixture
def mock_sentence_transformer():
    """Mock fuer SentenceTransformer."""
    # Erstelle Mock-Modell mit korrektem Return-Value fuer encode()
    model_instance = MagicMock()
    # encode() gibt numpy array zurueck, tolist() wird als echte Liste gemockt
    mock_array = MagicMock()
    mock_array.tolist.return_value = [0.1] * 1024
    model_instance.encode.return_value = mock_array
    model_instance.get_sentence_embedding_dimension.return_value = 1024
    model_instance.max_seq_length = 512

    yield model_instance


class TestEmbeddingModelType:
    """Tests fuer EmbeddingModelType Enum."""

    def test_model_type_values(self):
        """Test EmbeddingModelType Werte."""
        from app.services.embedding_service import EmbeddingModelType

        assert EmbeddingModelType.E5_MULTILINGUAL.value == "e5"
        assert EmbeddingModelType.JINA_GERMAN.value == "jina"


class TestEmbeddingService:
    """Tests fuer E5 EmbeddingService."""

    def test_singleton_pattern(self, mock_settings, reset_singletons):
        """Test dass EmbeddingService Singleton ist."""
        from app.services.embedding_service import EmbeddingService

        service1 = EmbeddingService()
        service2 = EmbeddingService()

        assert service1 is service2

    def test_initialization(self, mock_settings, reset_singletons):
        """Test Initialisierung mit Settings."""
        from app.services.embedding_service import EmbeddingService

        service = EmbeddingService()

        assert service.model_name == "intfloat/multilingual-e5-large"
        assert service.dimension == 1024
        assert service.max_length == 512

    def test_get_embedding_service(self, mock_settings, reset_singletons):
        """Test get_embedding_service() Factory."""
        from app.services.embedding_service import get_embedding_service

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2


class TestJinaEmbeddingService:
    """Tests fuer JinaEmbeddingService."""

    def test_singleton_pattern(self, mock_settings, reset_singletons):
        """Test dass JinaEmbeddingService Singleton ist."""
        from app.services.embedding_service import JinaEmbeddingService

        service1 = JinaEmbeddingService()
        service2 = JinaEmbeddingService()

        assert service1 is service2

    def test_initialization(self, mock_settings, reset_singletons):
        """Test Initialisierung mit Settings."""
        from app.services.embedding_service import JinaEmbeddingService

        service = JinaEmbeddingService()

        assert service.model_name == "jinaai/jina-embeddings-v2-base-de"
        assert service.dimension == 1024
        assert service.max_length == 8192
        assert service.trust_remote_code is True

    def test_get_jina_embedding_service(self, mock_settings, reset_singletons):
        """Test get_jina_embedding_service() Factory."""
        from app.services.embedding_service import get_jina_embedding_service

        service1 = get_jina_embedding_service()
        service2 = get_jina_embedding_service()

        assert service1 is service2

    def test_get_jina_service_disabled_raises(self, mock_settings, reset_singletons):
        """Test dass deaktivierter Jina Service Fehler wirft."""
        mock_settings.JINA_EMBEDDING_ENABLED = False

        from app.services.embedding_service import get_jina_embedding_service

        with pytest.raises(RuntimeError) as exc_info:
            get_jina_embedding_service()

        assert "nicht aktiviert" in str(exc_info.value)


class TestEmbeddingProvider:
    """Tests fuer EmbeddingProvider."""

    def test_singleton_pattern(self, mock_settings, reset_singletons):
        """Test dass EmbeddingProvider Singleton ist."""
        from app.services.embedding_service import EmbeddingProvider

        provider1 = EmbeddingProvider()
        provider2 = EmbeddingProvider()

        assert provider1 is provider2

    def test_initialization(self, mock_settings, reset_singletons):
        """Test Initialisierung."""
        from app.services.embedding_service import EmbeddingProvider

        provider = EmbeddingProvider()

        assert provider._e5_service is None  # Lazy loaded
        assert provider._jina_service is None  # Lazy loaded

    def test_get_embedding_provider(self, mock_settings, reset_singletons):
        """Test get_embedding_provider() Factory."""
        from app.services.embedding_service import get_embedding_provider

        provider1 = get_embedding_provider()
        provider2 = get_embedding_provider()

        assert provider1 is provider2


class TestEmbeddingProviderE5:
    """Tests fuer E5-Embedding-Generierung ueber Provider."""

    def test_generate_embedding_e5(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test Embedding-Generierung mit E5."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType, EmbeddingService
        )

        # Mock die E5 Service-Instanz direkt
        mock_e5_service = MagicMock(spec=EmbeddingService)
        # generate_embedding wird aufgerufen, nicht generate_document_embedding
        mock_e5_service.generate_embedding.return_value = [0.1] * 1024

        provider = EmbeddingProvider()
        provider._e5_service = mock_e5_service

        embedding = provider.generate_embedding(
            "Test text",
            model_type=EmbeddingModelType.E5_MULTILINGUAL
        )

        assert isinstance(embedding, list)
        assert len(embedding) == 1024
        mock_e5_service.generate_embedding.assert_called_once_with("Test text", is_query=False)

    def test_generate_query_embedding_e5(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test Query-Embedding mit E5."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType, EmbeddingService
        )

        # Mock die E5 Service-Instanz direkt
        mock_e5_service = MagicMock(spec=EmbeddingService)
        mock_e5_service.generate_query_embedding.return_value = [0.2] * 1024

        provider = EmbeddingProvider()
        provider._e5_service = mock_e5_service

        embedding = provider.generate_query_embedding(
            "Search query",
            model_type=EmbeddingModelType.E5_MULTILINGUAL
        )

        assert isinstance(embedding, list)
        mock_e5_service.generate_query_embedding.assert_called_once_with("Search query")


class TestEmbeddingProviderJina:
    """Tests fuer Jina-Embedding-Generierung ueber Provider."""

    def test_generate_embedding_jina(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test Embedding-Generierung mit Jina."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType, JinaEmbeddingService
        )

        # Mock die Jina Service-Instanz direkt
        mock_jina_service = MagicMock(spec=JinaEmbeddingService)
        # JinaEmbeddingService.generate_embedding() wird aufgerufen
        mock_jina_service.generate_embedding.return_value = [0.3] * 1024

        provider = EmbeddingProvider()
        provider._jina_service = mock_jina_service

        embedding = provider.generate_embedding(
            "Deutscher Testtext",
            model_type=EmbeddingModelType.JINA_GERMAN
        )

        assert isinstance(embedding, list)
        assert len(embedding) == 1024
        mock_jina_service.generate_embedding.assert_called_once_with("Deutscher Testtext")

    def test_jina_disabled_raises(
        self,
        mock_settings,
        reset_singletons
    ):
        """Test dass deaktivierter Jina Service Fehler wirft."""
        mock_settings.JINA_EMBEDDING_ENABLED = False

        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType
        )

        provider = EmbeddingProvider()

        with pytest.raises(RuntimeError) as exc_info:
            provider.generate_embedding(
                "Test",
                model_type=EmbeddingModelType.JINA_GERMAN
            )

        assert "nicht aktiviert" in str(exc_info.value)


class TestEmbeddingProviderBatch:
    """Tests fuer Batch-Embedding-Generierung."""

    def test_generate_batch_embeddings(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test Batch-Embedding-Generierung."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType, EmbeddingService
        )

        # Mock die E5 Service-Instanz direkt
        mock_e5_service = MagicMock(spec=EmbeddingService)
        mock_e5_service.generate_batch_embeddings.return_value = [
            [0.1] * 1024,
            [0.2] * 1024,
            [0.3] * 1024
        ]

        provider = EmbeddingProvider()
        provider._e5_service = mock_e5_service

        embeddings = provider.generate_batch_embeddings(
            ["Text 1", "Text 2", "Text 3"],
            model_type=EmbeddingModelType.E5_MULTILINGUAL
        )

        assert len(embeddings) == 3
        assert all(len(e) == 1024 for e in embeddings)

    def test_batch_embeddings_empty_list(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test Batch-Embedding mit leerer Liste."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType, EmbeddingService
        )

        # Mock die E5 Service-Instanz direkt
        mock_e5_service = MagicMock(spec=EmbeddingService)
        mock_e5_service.generate_batch_embeddings.return_value = []

        provider = EmbeddingProvider()
        provider._e5_service = mock_e5_service

        embeddings = provider.generate_batch_embeddings(
            [],
            model_type=EmbeddingModelType.E5_MULTILINGUAL
        )

        assert embeddings == []


class TestEmbeddingProviderModelInfo:
    """Tests fuer Model-Info Abruf."""

    def test_get_e5_model_info(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test E5 Model Info."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType, EmbeddingService
        )

        # Mock die E5 Service-Instanz direkt
        mock_e5_service = MagicMock(spec=EmbeddingService)
        mock_e5_service.get_model_info.return_value = {
            "model_type": "e5",
            "model_name": "intfloat/multilingual-e5-large",
            "dimension": 1024,
            "max_length": 512,
            "loaded": True,
        }

        provider = EmbeddingProvider()
        provider._e5_service = mock_e5_service

        info = provider.get_model_info(EmbeddingModelType.E5_MULTILINGUAL)

        assert info["model_type"] == "e5"
        assert info["dimension"] == 1024

    def test_get_multi_model_info(
        self,
        mock_settings,
        reset_singletons
    ):
        """Test Multi-Model Info."""
        from app.services.embedding_service import EmbeddingProvider

        provider = EmbeddingProvider()
        info = provider.get_model_info()  # Ohne model_type

        assert "jina_enabled" in info
        assert "ab_testing_enabled" in info


class TestEmbeddingProviderUnload:
    """Tests fuer Model-Unloading."""

    def test_unload_all_models(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test Unload aller Modelle."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingService, JinaEmbeddingService
        )

        # Mock Services direkt erstellen
        mock_e5_service = MagicMock(spec=EmbeddingService)
        mock_jina_service = MagicMock(spec=JinaEmbeddingService)

        provider = EmbeddingProvider()
        provider._e5_service = mock_e5_service
        provider._jina_service = mock_jina_service

        # Unload aufrufen
        provider.unload_model()

        # Beide Services sollten unload_model() aufgerufen haben
        mock_e5_service.unload_model.assert_called_once()
        mock_jina_service.unload_model.assert_called_once()

    def test_unload_specific_model(
        self,
        mock_settings,
        reset_singletons,
        mock_sentence_transformer
    ):
        """Test Unload eines spezifischen Modells."""
        from app.services.embedding_service import (
            EmbeddingProvider, EmbeddingModelType, EmbeddingService,
            JinaEmbeddingService
        )

        # Mock Services direkt erstellen
        mock_e5_service = MagicMock(spec=EmbeddingService)
        mock_jina_service = MagicMock(spec=JinaEmbeddingService)

        provider = EmbeddingProvider()
        provider._e5_service = mock_e5_service
        provider._jina_service = mock_jina_service

        # Nur E5 unloaden
        provider.unload_model(EmbeddingModelType.E5_MULTILINGUAL)

        # Nur E5 sollte unload_model() aufgerufen haben
        mock_e5_service.unload_model.assert_called_once()
        mock_jina_service.unload_model.assert_not_called()


class TestEmbeddingModelInfo:
    """Tests fuer EmbeddingModelInfo TypedDict."""

    def test_model_info_creation(self):
        """Test EmbeddingModelInfo Erstellung."""
        from app.services.embedding_service import EmbeddingModelInfo

        info: EmbeddingModelInfo = {
            "model_name": "test-model",
            "model_type": "e5",
            "dimension": 1024,
            "max_length": 512,
            "device": "cpu",
            "loaded": True
        }

        assert info["model_name"] == "test-model"
        assert info["model_type"] == "e5"
        assert info["dimension"] == 1024


class TestMultiModelEmbeddingInfo:
    """Tests fuer MultiModelEmbeddingInfo TypedDict."""

    def test_multi_model_info_creation(self):
        """Test MultiModelEmbeddingInfo Erstellung."""
        from app.services.embedding_service import MultiModelEmbeddingInfo

        info: MultiModelEmbeddingInfo = {
            "active_model": "e5",
            "jina_enabled": True,
            "ab_testing_enabled": True
        }

        assert info["active_model"] == "e5"
        assert info["jina_enabled"] is True
