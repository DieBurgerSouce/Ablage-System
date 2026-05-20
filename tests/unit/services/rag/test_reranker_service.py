"""Unit Tests fuer RerankerService.

Testet den Dual-Stack Reranker mit GPU/CPU Fallback.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass

# Mock settings vor dem Import
@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings fuer alle Tests."""
    with patch('app.services.reranker_service.settings') as mock:
        mock.RAG_RERANK_ENABLED = True
        mock.RAG_RERANK_TOP_K = 10
        mock.ENABLE_GPU = False  # CPU-only fuer Tests
        mock.RERANKER_BATCH_SIZE = 8
        mock.RERANKER_MAX_LENGTH = 512
        mock.RERANKER_GPU_MODEL = "BAAI/bge-reranker-v2-m3"
        mock.RERANKER_CPU_MODEL = "cross-encoder/ms-marco-MiniLM-L-12-v2"
        mock.RERANKER_GPU_VRAM_GB = 1.0
        mock.GPU_MEMORY_FRACTION = 0.85
        yield mock


@pytest.fixture
def reset_singleton():
    """Reset RerankerService Singleton zwischen Tests."""
    from app.services.reranker_service import RerankerService

    # Reset vor dem Test
    RerankerService._instance = None
    RerankerService._initialized = False
    RerankerService._gpu_model = None
    RerankerService._cpu_model = None

    yield

    # Cleanup nach dem Test
    RerankerService._instance = None
    RerankerService._initialized = False
    RerankerService._gpu_model = None
    RerankerService._cpu_model = None


class TestRerankerServiceInit:
    """Tests fuer RerankerService Initialisierung."""

    def test_singleton_pattern(self, mock_settings, reset_singleton):
        """Test dass RerankerService Singleton ist."""
        from app.services.reranker_service import RerankerService

        service1 = RerankerService()
        service2 = RerankerService()

        assert service1 is service2

    def test_initialization_sets_flags(self, mock_settings, reset_singleton):
        """Test dass Initialisierung korrekte Flags setzt."""
        from app.services.reranker_service import RerankerService

        service = RerankerService()

        assert service._initialized is True
        assert service._gpu_model is None  # Lazy loading
        assert service._cpu_model is None  # Lazy loading

    def test_get_reranker_service_returns_singleton(self, mock_settings, reset_singleton):
        """Test dass get_reranker_service() Singleton zurueckgibt."""
        from app.services.reranker_service import get_reranker_service

        service1 = get_reranker_service()
        service2 = get_reranker_service()

        assert service1 is service2


class TestRerankerServiceRerank:
    """Tests fuer Reranking-Funktionalitaet."""

    def test_rerank_empty_documents(self, mock_settings, reset_singleton):
        """Test Reranking mit leerer Dokumentliste."""
        from app.services.reranker_service import RerankerService

        service = RerankerService()
        results = service.rerank("test query", [])

        assert results == []

    def test_rerank_disabled_returns_original_order(self, mock_settings, reset_singleton):
        """Test dass deaktiviertes Reranking Original-Reihenfolge behaelt."""
        mock_settings.RAG_RERANK_ENABLED = False

        from app.services.reranker_service import RerankerService

        service = RerankerService()
        documents = ["doc1", "doc2", "doc3"]
        results = service.rerank("query", documents)

        assert len(results) == 3
        assert results[0].index == 0
        assert results[0].text == "doc1"
        assert results[1].index == 1
        assert results[2].index == 2

    @patch('sentence_transformers.CrossEncoder')
    def test_cpu_reranking_sorts_by_score(self, mock_cross_encoder, mock_settings, reset_singleton):
        """Test dass CPU-Reranking nach Score sortiert."""
        # Mock CrossEncoder
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5, 0.9, 0.7]  # Scores fuer 3 Dokumente
        mock_cross_encoder.return_value = mock_model

        from app.services.reranker_service import RerankerService

        service = RerankerService()
        documents = ["low relevance", "high relevance", "medium relevance"]
        results = service.rerank("test query", documents)

        # Sollte nach Score sortiert sein (absteigend)
        assert len(results) == 3
        assert results[0].score == 0.9
        assert results[0].text == "high relevance"
        assert results[1].score == 0.7
        assert results[1].text == "medium relevance"
        assert results[2].score == 0.5
        assert results[2].text == "low relevance"

    @patch('sentence_transformers.CrossEncoder')
    def test_top_k_limiting(self, mock_cross_encoder, mock_settings, reset_singleton):
        """Test dass top_k Ergebnisse korrekt limitiert."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.9, 0.8, 0.7, 0.6, 0.5]
        mock_cross_encoder.return_value = mock_model

        from app.services.reranker_service import RerankerService

        service = RerankerService()
        documents = ["doc1", "doc2", "doc3", "doc4", "doc5"]
        results = service.rerank("query", documents, top_k=3)

        assert len(results) == 3
        assert results[0].score == 0.9
        assert results[2].score == 0.7

    @patch('sentence_transformers.CrossEncoder')
    def test_rerank_preserves_indices(self, mock_cross_encoder, mock_settings, reset_singleton):
        """Test dass Original-Indizes erhalten bleiben."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.3, 0.9, 0.6]  # Index 1 ist am besten
        mock_cross_encoder.return_value = mock_model

        from app.services.reranker_service import RerankerService

        service = RerankerService()
        documents = ["doc_a", "doc_b", "doc_c"]
        results = service.rerank("query", documents)

        # Der hoechste Score (0.9) gehoert zu Index 1 ("doc_b")
        assert results[0].index == 1
        assert results[0].text == "doc_b"


class TestRerankerServiceStats:
    """Tests fuer Statistik-Tracking."""

    def test_stats_tracking(self, mock_settings, reset_singleton):
        """Test dass Statistiken korrekt getrackt werden."""
        from app.services.reranker_service import RerankerService

        service = RerankerService()
        stats = service.get_stats()

        assert "gpu_rerank_count" in stats
        assert "cpu_rerank_count" in stats
        assert "gpu_fallback_count" in stats
        assert "total_documents_reranked" in stats
        assert "total_queries" in stats

    @patch('sentence_transformers.CrossEncoder')
    def test_stats_increment_on_rerank(self, mock_cross_encoder, mock_settings, reset_singleton):
        """Test dass Statistiken bei Reranking inkrementiert werden."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5, 0.9]
        mock_cross_encoder.return_value = mock_model

        from app.services.reranker_service import RerankerService

        service = RerankerService()

        # Initialer Stand
        stats_before = service.get_stats()
        assert stats_before["total_queries"] == 0

        # Reranking durchfuehren
        service.rerank("query", ["doc1", "doc2"])

        # Stats nach Reranking
        stats_after = service.get_stats()
        assert stats_after["total_queries"] == 1
        assert stats_after["total_documents_reranked"] == 2
        assert stats_after["cpu_rerank_count"] == 1  # CPU weil GPU disabled


class TestRerankerServiceModelInfo:
    """Tests fuer Model-Informationen."""

    def test_get_model_info(self, mock_settings, reset_singleton):
        """Test dass Model-Info korrekt zurueckgegeben wird."""
        from app.services.reranker_service import RerankerService

        service = RerankerService()
        info = service.get_model_info()

        assert "gpu_model" in info
        assert "cpu_model" in info
        assert "gpu_loaded" in info
        assert "cpu_loaded" in info
        assert info["gpu_loaded"] is False  # Lazy loading
        assert info["cpu_loaded"] is False  # Lazy loading

    def test_is_available(self, mock_settings, reset_singleton):
        """Test is_available() Methode."""
        from app.services.reranker_service import RerankerService

        service = RerankerService()

        # Mit RAG_RERANK_ENABLED = True sollte es verfuegbar sein
        assert service.is_available() is True

    def test_is_available_disabled(self, mock_settings, reset_singleton):
        """Test is_available() wenn deaktiviert."""
        mock_settings.RAG_RERANK_ENABLED = False

        from app.services.reranker_service import RerankerService

        service = RerankerService()

        assert service.is_available() is False


class TestRerankerServiceModelUnloading:
    """Tests fuer Model-Unloading."""

    @patch('sentence_transformers.CrossEncoder')
    def test_unload_gpu_model(self, mock_cross_encoder, mock_settings, reset_singleton):
        """Test GPU-Model Unloading."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.5]
        mock_cross_encoder.return_value = mock_model

        from app.services.reranker_service import RerankerService

        service = RerankerService()

        # Model laden durch Reranking
        service._cpu_model = mock_model  # Simuliere geladenes Model

        # Unload
        service.unload_all_models()

        assert service._cpu_model is None
        assert service._gpu_model is None


@pytest.mark.asyncio
class TestRerankerServiceAsync:
    """Tests fuer async Reranking."""

    async def test_rerank_async_empty(self, mock_settings, reset_singleton):
        """Test async Reranking mit leerer Liste."""
        from app.services.reranker_service import RerankerService

        service = RerankerService()
        results = await service.rerank_async("query", [])

        assert results == []

    @patch('sentence_transformers.CrossEncoder')
    async def test_rerank_async_returns_results(self, mock_cross_encoder, mock_settings, reset_singleton):
        """Test async Reranking gibt Ergebnisse zurueck."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [0.8, 0.6]
        mock_cross_encoder.return_value = mock_model

        from app.services.reranker_service import RerankerService

        service = RerankerService()
        results = await service.rerank_async("query", ["doc1", "doc2"])

        assert len(results) == 2
        assert results[0].score == 0.8


class TestRerankerServiceFallback:
    """Tests fuer Fallback-Verhalten."""

    def test_fallback_on_all_failures(self, mock_settings, reset_singleton):
        """Test Fallback wenn beide Backends fehlschlagen."""
        from app.services.reranker_service import RerankerService

        service = RerankerService()

        # Simuliere dass beide Model-Loads fehlschlagen
        with patch.object(service, '_ensure_gpu_model_loaded', return_value=False):
            with patch.object(service, '_ensure_cpu_model_loaded', return_value=False):
                documents = ["doc1", "doc2", "doc3"]
                results = service.rerank("query", documents)

                # Sollte Original-Reihenfolge mit absteigenden Scores zurueckgeben
                assert len(results) == 3
                assert results[0].index == 0
                assert results[0].score > results[1].score
                assert results[1].score > results[2].score
