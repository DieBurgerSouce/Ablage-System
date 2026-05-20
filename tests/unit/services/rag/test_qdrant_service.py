"""Unit Tests fuer QdrantService.

Testet den Qdrant Vector Database Service mit Mocks.
"""

import pytest
import sys
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import List

# Pre-import um Modul zu laden (wichtig fuer patch-Pfad)
import app.services.rag.qdrant_service  # noqa: F401


# Mock settings und QDRANT_AVAILABLE vor dem Import
@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings fuer alle Tests."""
    with patch('app.services.rag.qdrant_service.QDRANT_AVAILABLE', True), \
         patch('app.services.rag.qdrant_service.settings') as mock:
        mock.QDRANT_ENABLED = True
        mock.QDRANT_HOST = "localhost"
        mock.QDRANT_HTTP_PORT = 6333
        mock.QDRANT_GRPC_PORT = 6334
        mock.QDRANT_PREFER_GRPC = False
        mock.QDRANT_API_KEY = None
        mock.QDRANT_COLLECTION_DOCUMENTS = "documents"
        mock.QDRANT_COLLECTION_CHUNKS = "chunks"
        mock.QDRANT_HNSW_M = 16
        mock.QDRANT_HNSW_EF_CONSTRUCT = 100
        mock.QDRANT_ON_DISK_PAYLOAD = False
        mock.QDRANT_QUANTIZATION_ENABLED = False
        yield mock


@pytest.fixture
def reset_singleton():
    """Reset QdrantService Singleton zwischen Tests."""
    from app.services.rag.qdrant_service import QdrantService

    # Reset vor dem Test
    QdrantService._instance = None
    QdrantService._initialized = False
    QdrantService._client = None
    QdrantService._async_client = None

    yield

    # Cleanup nach dem Test
    QdrantService._instance = None
    QdrantService._initialized = False
    QdrantService._client = None
    QdrantService._async_client = None


@pytest.fixture
def mock_qdrant_client():
    """Mock fuer Qdrant Client."""
    import app.services.rag.qdrant_service as qdrant_module

    # Create mock qdrant_models if not present
    mock_qdrant_models = MagicMock()
    mock_qdrant_models.PointsSelector = MagicMock

    # Create Distance enum mock with COSINE attribute
    mock_distance = MagicMock()
    mock_distance.COSINE = "Cosine"
    mock_distance.EUCLID = "Euclid"
    mock_distance.DOT = "Dot"

    with patch.object(qdrant_module, 'QdrantClient', create=True) as mock_sync, \
         patch.object(qdrant_module, 'AsyncQdrantClient', create=True) as mock_async, \
         patch.object(qdrant_module, 'qdrant_models', mock_qdrant_models, create=True), \
         patch.object(qdrant_module, 'PointStruct', MagicMock, create=True), \
         patch.object(qdrant_module, 'VectorParams', MagicMock, create=True), \
         patch.object(qdrant_module, 'Distance', mock_distance, create=True), \
         patch.object(qdrant_module, 'HnswConfigDiff', MagicMock, create=True), \
         patch.object(qdrant_module, 'OptimizersConfigDiff', MagicMock, create=True):

        # Sync Client Mocks
        sync_instance = MagicMock()
        mock_sync.return_value = sync_instance

        # Async Client Mocks - use AsyncMock so all methods are async
        async_instance = AsyncMock()

        # Mock get_collections response
        collections_response = MagicMock()
        collections_response.collections = []
        async_instance.get_collections.return_value = collections_response

        async_instance.create_collection.return_value = None
        async_instance.delete_collection.return_value = True
        async_instance.upsert.return_value = None
        async_instance.delete.return_value = None
        async_instance.search.return_value = []

        mock_async.return_value = async_instance

        yield {
            'sync_class': mock_sync,
            'async_class': mock_async,
            'sync_instance': sync_instance,
            'async_instance': async_instance
        }


class TestQdrantServiceInit:
    """Tests fuer QdrantService Initialisierung."""

    def test_singleton_pattern(self, mock_settings, reset_singleton):
        """Test dass QdrantService Singleton ist."""
        from app.services.rag.qdrant_service import QdrantService

        service1 = QdrantService()
        service2 = QdrantService()

        assert service1 is service2

    def test_initialization_with_default_settings(self, mock_settings, reset_singleton):
        """Test Initialisierung mit Default-Settings."""
        from app.services.rag.qdrant_service import QdrantService

        service = QdrantService()

        assert service._host == "localhost"
        assert service._http_port == 6333
        assert service._grpc_port == 6334
        assert service._prefer_grpc is False

    def test_get_qdrant_service_returns_singleton(self, mock_settings, reset_singleton):
        """Test dass get_qdrant_service() Singleton zurueckgibt."""
        from app.services.rag.qdrant_service import get_qdrant_service

        service1 = get_qdrant_service()
        service2 = get_qdrant_service()

        assert service1 is service2

    def test_disabled_service_returns_noop(self, mock_settings, reset_singleton):
        """Test dass deaktivierter Service keine Operationen durchfuehrt."""
        mock_settings.QDRANT_ENABLED = False

        from app.services.rag.qdrant_service import QdrantService

        service = QdrantService()

        assert service._enabled is False


class TestQdrantServiceCollection:
    """Tests fuer Collection-Management."""

    @pytest.mark.asyncio
    async def test_ensure_collection_creates_if_not_exists(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test dass Collection erstellt wird wenn nicht vorhanden."""
        from app.services.rag.qdrant_service import QdrantService

        # Mock get_collections to return empty list (collection doesn't exist)
        collections_response = MagicMock()
        collections_response.collections = []
        mock_qdrant_client['async_instance'].get_collections.return_value = collections_response

        service = QdrantService()
        result = await service.ensure_collection("test_collection", vector_size=1024)

        assert result is True
        mock_qdrant_client['async_instance'].create_collection.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_collection_skips_if_exists(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test dass existierende Collection nicht neu erstellt wird."""
        from app.services.rag.qdrant_service import QdrantService

        # Mock get_collections to return collection with matching name
        existing_collection = MagicMock()
        existing_collection.name = "test_collection"
        collections_response = MagicMock()
        collections_response.collections = [existing_collection]
        mock_qdrant_client['async_instance'].get_collections.return_value = collections_response

        service = QdrantService()
        result = await service.ensure_collection("test_collection", vector_size=1024)

        assert result is True
        mock_qdrant_client['async_instance'].create_collection.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_collection(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test Collection loeschen."""
        from app.services.rag.qdrant_service import QdrantService

        mock_qdrant_client['async_instance'].delete_collection = AsyncMock(return_value=True)

        service = QdrantService()
        result = await service.delete_collection("test_collection")

        assert result is True


class TestQdrantServiceVectorOperations:
    """Tests fuer Vector-Operationen."""

    @pytest.mark.asyncio
    async def test_upsert_vectors(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test Vector Upsert."""
        from app.services.rag.qdrant_service import QdrantService, QdrantPointData

        mock_qdrant_client['async_instance'].upsert = AsyncMock()

        service = QdrantService()

        points = [
            QdrantPointData(
                id="point1",
                vector=[0.1] * 1024,
                payload={"text": "test"}
            ),
            QdrantPointData(
                id="point2",
                vector=[0.2] * 1024,
                payload={"text": "test2"}
            )
        ]

        result = await service.upsert_vectors("test_collection", points)

        assert result == 2
        mock_qdrant_client['async_instance'].upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_empty_points(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test Upsert mit leerer Punktliste."""
        from app.services.rag.qdrant_service import QdrantService

        service = QdrantService()
        result = await service.upsert_vectors("test_collection", [])

        assert result == 0
        mock_qdrant_client['async_instance'].upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_vectors(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test Vector Search."""
        from app.services.rag.qdrant_service import QdrantService

        # Mock search result
        mock_result = MagicMock()
        mock_result.id = "point1"
        mock_result.score = 0.95
        mock_result.payload = {"text": "result"}
        mock_result.vector = [0.1] * 1024

        mock_qdrant_client['async_instance'].search = AsyncMock(return_value=[mock_result])

        service = QdrantService()
        results = await service.search(
            collection_name="test_collection",
            query_vector=[0.1] * 1024,
            limit=10
        )

        assert len(results) == 1
        assert results[0].id == "point1"
        assert results[0].score == 0.95

    @pytest.mark.asyncio
    async def test_delete_vectors(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test Vector Delete."""
        from app.services.rag.qdrant_service import QdrantService

        mock_qdrant_client['async_instance'].delete = AsyncMock()

        service = QdrantService()
        result = await service.delete_vectors(
            collection_name="test_collection",
            ids=["point1", "point2"]
        )

        assert result == 2


class TestQdrantServiceBatchOperations:
    """Tests fuer Batch-Operationen."""

    @pytest.mark.asyncio
    async def test_batch_upsert_splits_correctly(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test dass Batch-Upsert korrekt aufteilt."""
        from app.services.rag.qdrant_service import QdrantService, QdrantPointData

        mock_qdrant_client['async_instance'].upsert = AsyncMock()

        service = QdrantService()

        # 250 Punkte erstellen (sollte in 3 Batches a 100 aufgeteilt werden)
        points = [
            QdrantPointData(
                id=f"point{i}",
                vector=[0.1] * 1024,
                payload={"index": i}
            )
            for i in range(250)
        ]

        result = await service.batch_upsert(
            collection_name="test_collection",
            points=points,
            batch_size=100
        )

        assert result == 250
        # 3 Batches: 100 + 100 + 50
        assert mock_qdrant_client['async_instance'].upsert.call_count == 3


class TestQdrantServiceHealth:
    """Tests fuer Health-Check."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test Health-Check bei gesundem Service."""
        from app.services.rag.qdrant_service import QdrantService

        # Mock get_collections response for async client
        collections_response = MagicMock()
        collections_response.collections = []
        mock_qdrant_client['async_instance'].get_collections.return_value = collections_response

        service = QdrantService()
        health = await service.health_check()

        assert health["status"] == "healthy"
        assert "host" in health

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_error(
        self, mock_settings, reset_singleton, mock_qdrant_client
    ):
        """Test Health-Check bei Fehler."""
        from app.services.rag.qdrant_service import QdrantService

        # Mock to raise exception
        mock_qdrant_client['async_instance'].get_collections.side_effect = Exception("Connection failed")

        service = QdrantService()
        health = await service.health_check()

        assert health["status"] == "unhealthy"
        assert "error" in health

    @pytest.mark.asyncio
    async def test_health_check_disabled_service(
        self, mock_settings, reset_singleton
    ):
        """Test Health-Check bei deaktiviertem Service."""
        mock_settings.QDRANT_ENABLED = False

        from app.services.rag.qdrant_service import QdrantService

        service = QdrantService()
        health = await service.health_check()

        assert health["status"] == "disabled"
        assert "message" in health


class TestQdrantPointData:
    """Tests fuer QdrantPointData TypedDict."""

    def test_point_data_creation(self):
        """Test QdrantPointData Erstellung."""
        from app.services.rag.qdrant_service import QdrantPointData

        point = QdrantPointData(
            id="test-id",
            vector=[0.1, 0.2, 0.3],
            payload={"key": "value"}
        )

        assert point["id"] == "test-id"
        assert point["vector"] == [0.1, 0.2, 0.3]
        assert point["payload"] == {"key": "value"}

    def test_point_data_without_payload(self):
        """Test QdrantPointData ohne Payload."""
        from app.services.rag.qdrant_service import QdrantPointData

        point = QdrantPointData(
            id="test-id",
            vector=[0.1, 0.2, 0.3]
        )

        assert point["id"] == "test-id"
        assert "payload" not in point


class TestQdrantSearchResult:
    """Tests fuer QdrantSearchResult."""

    def test_search_result_creation(self):
        """Test QdrantSearchResult Erstellung."""
        from app.services.rag.qdrant_service import QdrantSearchResult

        result = QdrantSearchResult(
            id="result-id",
            score=0.95,
            payload={"text": "content"},
            vector=[0.1, 0.2, 0.3]
        )

        assert result.id == "result-id"
        assert result.score == 0.95
        assert result.payload == {"text": "content"}
        assert result.vector == [0.1, 0.2, 0.3]

    def test_search_result_without_optional_fields(self):
        """Test QdrantSearchResult ohne optionale Felder."""
        from app.services.rag.qdrant_service import QdrantSearchResult

        result = QdrantSearchResult(
            id="result-id",
            score=0.5,
            payload={}  # payload ist required
        )

        assert result.id == "result-id"
        assert result.score == 0.5
        assert result.payload == {}
        assert result.vector is None
