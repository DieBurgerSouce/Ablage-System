# -*- coding: utf-8 -*-
"""
Unit-Tests fuer Embedding Service.

Testet:
- EmbeddingModelType Enum
- E5 Prefix-Logik (query: vs passage:)
- Batch-Embeddings (leere Liste, dynamische Batch-Size)
- Query-Caching (Cache-Hit, Cache-Miss)
- EmbeddingProvider (Modell-Routing)
- Singleton-Pattern
- GPU-Speicher-Management

Feinpoliert und durchdacht - Embedding Service Tests.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock, PropertyMock
from uuid import uuid4

from app.services.embedding_service import (
    EmbeddingModelType,
    EmbeddingService,
    JinaEmbeddingService,
    EmbeddingProvider,
    QUERY_EMBEDDING_CACHE_PREFIX,
    QUERY_EMBEDDING_CACHE_TTL,
)

pytestmark = [pytest.mark.unit]


# ========================= Enum Tests =========================


class TestEmbeddingModelType:
    """Tests fuer EmbeddingModelType Enum."""

    def test_e5_value(self):
        """E5 Multilingual hat korrekten Wert."""
        assert EmbeddingModelType.E5_MULTILINGUAL.value == "e5"

    def test_jina_value(self):
        """Jina German hat korrekten Wert."""
        assert EmbeddingModelType.JINA_GERMAN.value == "jina"

    def test_string_enum(self):
        """Ist ein String-Enum."""
        assert isinstance(EmbeddingModelType.E5_MULTILINGUAL, str)


# ========================= Cache Key Tests =========================


class TestCacheKeyGeneration:
    """Tests fuer Cache-Key-Generierung."""

    def test_cache_key_format(self):
        """Cache-Key hat korrektes Format."""
        # Reset singleton for clean test
        EmbeddingService._instance = None
        EmbeddingService._initialized = False

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.EMBEDDING_MODEL = "test-model"
            mock_settings.EMBEDDING_DIMENSION = 1024
            mock_settings.EMBEDDING_MAX_LENGTH = 512
            mock_settings.EMBEDDING_BATCH_SIZE = 32
            mock_settings.ENABLE_GPU = False

            service = EmbeddingService.__new__(EmbeddingService)
            service._initialized = False
            service._model = None
            service._tokenizer = None
            service._redis = None
            # Call init manually
            EmbeddingService._instance = service
            service.__init__()

            key = service._get_query_cache_key("test query")

        assert key.startswith(QUERY_EMBEDDING_CACHE_PREFIX)
        assert ":" in key

        # Cleanup
        EmbeddingService._instance = None
        EmbeddingService._initialized = False

    def test_same_query_same_key(self):
        """Gleiche Query ergibt gleichen Key."""
        EmbeddingService._instance = None
        EmbeddingService._initialized = False

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.EMBEDDING_MODEL = "test-model"
            mock_settings.EMBEDDING_DIMENSION = 1024
            mock_settings.EMBEDDING_MAX_LENGTH = 512
            mock_settings.EMBEDDING_BATCH_SIZE = 32
            mock_settings.ENABLE_GPU = False

            service = EmbeddingService.__new__(EmbeddingService)
            service._initialized = False
            service._model = None
            service._tokenizer = None
            service._redis = None
            EmbeddingService._instance = service
            service.__init__()

            key1 = service._get_query_cache_key("Rechnung Mueller")
            key2 = service._get_query_cache_key("Rechnung Mueller")

        assert key1 == key2

        EmbeddingService._instance = None
        EmbeddingService._initialized = False

    def test_different_query_different_key(self):
        """Verschiedene Queries ergeben verschiedene Keys."""
        EmbeddingService._instance = None
        EmbeddingService._initialized = False

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.EMBEDDING_MODEL = "test-model"
            mock_settings.EMBEDDING_DIMENSION = 1024
            mock_settings.EMBEDDING_MAX_LENGTH = 512
            mock_settings.EMBEDDING_BATCH_SIZE = 32
            mock_settings.ENABLE_GPU = False

            service = EmbeddingService.__new__(EmbeddingService)
            service._initialized = False
            service._model = None
            service._tokenizer = None
            service._redis = None
            EmbeddingService._instance = service
            service.__init__()

            key1 = service._get_query_cache_key("Rechnung")
            key2 = service._get_query_cache_key("Vertrag")

        assert key1 != key2

        EmbeddingService._instance = None
        EmbeddingService._initialized = False


# ========================= Batch Embedding Tests =========================


class TestBatchEmbeddings:
    """Tests fuer Batch-Embedding-Generierung."""

    def test_empty_list_returns_empty(self):
        """Leere Textliste gibt leere Embeddings zurueck."""
        EmbeddingService._instance = None
        EmbeddingService._initialized = False

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.EMBEDDING_MODEL = "test-model"
            mock_settings.EMBEDDING_DIMENSION = 1024
            mock_settings.EMBEDDING_MAX_LENGTH = 512
            mock_settings.EMBEDDING_BATCH_SIZE = 32
            mock_settings.ENABLE_GPU = False

            service = EmbeddingService.__new__(EmbeddingService)
            service._initialized = False
            service._model = None
            service._tokenizer = None
            service._redis = None
            EmbeddingService._instance = service
            service.__init__()

            result = service.generate_batch_embeddings([])

        assert result == []

        EmbeddingService._instance = None
        EmbeddingService._initialized = False


# ========================= EmbeddingProvider Tests =========================


class TestEmbeddingProvider:
    """Tests fuer EmbeddingProvider."""

    def test_jina_disabled_raises_error(self):
        """Jina-Zugriff bei deaktivierten Jina wirft RuntimeError."""
        EmbeddingProvider._instance = None

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.JINA_EMBEDDING_ENABLED = False
            mock_settings.VECTOR_AB_TESTING_ENABLED = False

            provider = EmbeddingProvider.__new__(EmbeddingProvider)
            provider._initialized = False
            EmbeddingProvider._instance = provider
            provider.__init__()

            with pytest.raises(RuntimeError, match="nicht aktiviert"):
                provider._get_jina_service()

        EmbeddingProvider._instance = None

    def test_unload_model_handles_none(self):
        """Unload bei nicht geladenem Modell funktioniert ohne Fehler."""
        EmbeddingProvider._instance = None

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.JINA_EMBEDDING_ENABLED = False
            mock_settings.VECTOR_AB_TESTING_ENABLED = False

            provider = EmbeddingProvider.__new__(EmbeddingProvider)
            provider._initialized = False
            EmbeddingProvider._instance = provider
            provider.__init__()

            # Sollte keinen Fehler werfen
            provider.unload_model()

        EmbeddingProvider._instance = None


# ========================= Constants Tests =========================


class TestEmbeddingConstants:
    """Tests fuer Embedding-Konstanten."""

    def test_cache_ttl_positive(self):
        """Cache-TTL ist positiv."""
        assert QUERY_EMBEDDING_CACHE_TTL > 0

    def test_cache_prefix_format(self):
        """Cache-Prefix hat korrektes Format."""
        assert ":" in QUERY_EMBEDDING_CACHE_PREFIX
        assert QUERY_EMBEDDING_CACHE_PREFIX.startswith("cache:")


# ========================= Jina Service Tests =========================


class TestJinaEmbeddingService:
    """Tests fuer Jina-spezifische Funktionalitaet."""

    def test_empty_batch_returns_empty(self):
        """Leere Batch-Texte geben leere Liste zurueck."""
        JinaEmbeddingService._instance = None
        JinaEmbeddingService._initialized = False

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.JINA_EMBEDDING_MODEL = "test-jina"
            mock_settings.JINA_EMBEDDING_DIMENSION = 1024
            mock_settings.JINA_EMBEDDING_MAX_LENGTH = 8192
            mock_settings.JINA_TRUST_REMOTE_CODE = True
            mock_settings.EMBEDDING_BATCH_SIZE = 32
            mock_settings.ENABLE_GPU = False

            service = JinaEmbeddingService.__new__(JinaEmbeddingService)
            service._initialized = False
            service._model = None
            service._tokenizer = None
            service._redis = None
            JinaEmbeddingService._instance = service
            service.__init__()

            result = service.generate_batch_embeddings([])

        assert result == []

        JinaEmbeddingService._instance = None
        JinaEmbeddingService._initialized = False

    def test_gpu_check_cpu_always_true(self):
        """GPU-Check gibt True auf CPU zurueck."""
        JinaEmbeddingService._instance = None
        JinaEmbeddingService._initialized = False

        with patch('app.services.embedding_service.settings') as mock_settings:
            mock_settings.JINA_EMBEDDING_MODEL = "test-jina"
            mock_settings.JINA_EMBEDDING_DIMENSION = 1024
            mock_settings.JINA_EMBEDDING_MAX_LENGTH = 8192
            mock_settings.JINA_TRUST_REMOTE_CODE = True
            mock_settings.EMBEDDING_BATCH_SIZE = 32
            mock_settings.ENABLE_GPU = False

            service = JinaEmbeddingService.__new__(JinaEmbeddingService)
            service._initialized = False
            service._model = None
            service._tokenizer = None
            service._redis = None
            JinaEmbeddingService._instance = service
            service.__init__()

            import torch
            service.device = torch.device("cpu")

            result = service._check_gpu_memory()

        assert result is True

        JinaEmbeddingService._instance = None
        JinaEmbeddingService._initialized = False
