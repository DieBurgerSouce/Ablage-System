"""Unit Tests fuer VectorSyncService.

Testet den Dual-Write Vector Sync Service.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timezone
import uuid

# Pre-import um Modul zu laden (wichtig fuer patch-Pfad)
import app.services.rag.vector_sync_service  # noqa: F401


# Mock settings vor dem Import
@pytest.fixture(autouse=True)
def mock_settings():
    """Mock settings fuer alle Tests."""
    with patch('app.services.rag.vector_sync_service.settings') as mock:
        mock.VECTOR_DUAL_WRITE_ENABLED = True
        mock.VECTOR_DUAL_WRITE_ASYNC = False
        mock.VECTOR_MIGRATION_BATCH_SIZE = 100
        mock.QDRANT_COLLECTION_CHUNKS = "chunks"
        mock.JINA_EMBEDDING_ENABLED = False
        yield mock


@pytest.fixture
def reset_singleton():
    """Reset VectorSyncService Singleton zwischen Tests."""
    from app.services.rag.vector_sync_service import VectorSyncService

    # Reset vor dem Test
    VectorSyncService._instance = None

    yield

    # Cleanup nach dem Test
    VectorSyncService._instance = None


@pytest.fixture
def mock_qdrant_service():
    """Mock fuer Qdrant Service."""
    with patch('app.services.rag.vector_sync_service.get_qdrant_service') as mock:
        qdrant = MagicMock()
        qdrant.ensure_collection = AsyncMock(return_value=True)
        qdrant.upsert_vectors = AsyncMock(return_value=1)
        qdrant.batch_upsert = AsyncMock(return_value=10)
        qdrant.delete_vectors = AsyncMock(return_value=1)
        qdrant.health_check = AsyncMock(return_value={"healthy": True})
        qdrant.get_collection_info = AsyncMock(return_value={"points_count": 100})
        mock.return_value = qdrant
        yield qdrant


@pytest.fixture
def mock_embedding_provider():
    """Mock fuer Embedding Provider."""
    with patch('app.services.rag.vector_sync_service.get_embedding_provider') as mock:
        provider = MagicMock()
        provider.generate_document_embedding = MagicMock(return_value=[0.1] * 1024)
        provider.generate_batch_embeddings = MagicMock(
            return_value=[[0.1] * 1024 for _ in range(10)]
        )
        mock.return_value = provider
        yield provider


@pytest.fixture
def sample_chunk():
    """Erstellt einen Sample DocumentChunk."""
    chunk = MagicMock()
    chunk.id = uuid.uuid4()
    chunk.document_id = uuid.uuid4()
    chunk.chunk_text = "Sample chunk text for testing"
    chunk.chunk_index = 0
    chunk.page_number = 1
    chunk.section_type = "paragraph"
    chunk.created_at = datetime.now(timezone.utc)
    return chunk


class TestVectorSyncServiceInit:
    """Tests fuer VectorSyncService Initialisierung."""

    def test_singleton_pattern(self, mock_settings, reset_singleton):
        """Test dass VectorSyncService Singleton ist."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service1 = VectorSyncService()
        service2 = VectorSyncService()

        assert service1 is service2

    def test_initialization_with_settings(self, mock_settings, reset_singleton):
        """Test Initialisierung mit Settings."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()

        assert service._enabled is True
        assert service._async_mode is False
        assert service._batch_size == 100

    def test_get_vector_sync_service_returns_singleton(self, mock_settings, reset_singleton):
        """Test dass get_vector_sync_service() Singleton zurueckgibt."""
        from app.services.rag.vector_sync_service import get_vector_sync_service

        service1 = get_vector_sync_service()
        service2 = get_vector_sync_service()

        assert service1 is service2

    def test_disabled_service(self, mock_settings, reset_singleton):
        """Test deaktivierter Service."""
        mock_settings.VECTOR_DUAL_WRITE_ENABLED = False

        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()

        assert service._enabled is False


class TestVectorSyncServiceSingleChunk:
    """Tests fuer Einzelner Chunk Sync."""

    @pytest.mark.asyncio
    async def test_sync_chunk_to_qdrant(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service,
        mock_embedding_provider,
        sample_chunk
    ):
        """Test einzelnen Chunk synchronisieren."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        result = await service.sync_chunk_to_qdrant(sample_chunk)

        assert result is True
        mock_qdrant_service.upsert_vectors.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_chunk_with_provided_embedding(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service,
        mock_embedding_provider,
        sample_chunk
    ):
        """Test Chunk mit vorgegebenem Embedding synchronisieren."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        embedding = [0.5] * 1024
        result = await service.sync_chunk_to_qdrant(sample_chunk, embedding=embedding)

        assert result is True
        # Embedding Provider sollte nicht aufgerufen werden
        mock_embedding_provider.generate_document_embedding.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_chunk_disabled(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service,
        sample_chunk
    ):
        """Test dass deaktivierter Service nicht synchronisiert."""
        mock_settings.VECTOR_DUAL_WRITE_ENABLED = False

        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        result = await service.sync_chunk_to_qdrant(sample_chunk)

        assert result is True  # Gibt True zurueck (no-op)
        mock_qdrant_service.upsert_vectors.assert_not_called()


class TestVectorSyncServiceBatch:
    """Tests fuer Batch Sync."""

    @pytest.mark.asyncio
    async def test_sync_chunks_batch(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service,
        mock_embedding_provider,
        sample_chunk
    ):
        """Test Batch von Chunks synchronisieren."""
        from app.services.rag.vector_sync_service import VectorSyncService

        # 10 Chunks erstellen
        chunks = []
        for i in range(10):
            chunk = MagicMock()
            chunk.id = uuid.uuid4()
            chunk.document_id = uuid.uuid4()
            chunk.chunk_text = f"Chunk {i}"
            chunk.chunk_index = i
            chunk.page_number = 1
            chunk.section_type = "paragraph"
            chunk.created_at = datetime.now(timezone.utc)
            chunks.append(chunk)

        service = VectorSyncService()
        result = await service.sync_chunks_batch(chunks)

        assert result["success"] is True
        assert result["synced_count"] == 10

    @pytest.mark.asyncio
    async def test_sync_empty_batch(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service
    ):
        """Test Sync mit leerer Batch."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        result = await service.sync_chunks_batch([])

        assert result["success"] is True
        assert result["synced_count"] == 0
        mock_qdrant_service.batch_upsert.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_batch_disabled(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service,
        sample_chunk
    ):
        """Test dass deaktivierter Service Batch ueberspringt."""
        mock_settings.VECTOR_DUAL_WRITE_ENABLED = False

        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        result = await service.sync_chunks_batch([sample_chunk])

        assert result["success"] is True
        assert result["skipped_count"] == 1


class TestVectorSyncServiceDelete:
    """Tests fuer Delete-Operationen."""

    @pytest.mark.asyncio
    async def test_delete_from_qdrant(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service
    ):
        """Test Chunks aus Qdrant loeschen."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        result = await service.delete_from_qdrant(["id1", "id2", "id3"])

        assert result == 1  # Mock gibt 1 zurueck
        mock_qdrant_service.delete_vectors.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_disabled(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service
    ):
        """Test Delete bei deaktiviertem Service."""
        mock_settings.VECTOR_DUAL_WRITE_ENABLED = False

        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        result = await service.delete_from_qdrant(["id1"])

        assert result == 0
        mock_qdrant_service.delete_vectors.assert_not_called()


class TestVectorSyncServiceMigration:
    """Tests fuer Migration."""

    @pytest.mark.asyncio
    async def test_migration_status_initial(
        self,
        mock_settings,
        reset_singleton
    ):
        """Test initialer Migration-Status."""
        from app.services.rag.vector_sync_service import (
            VectorSyncService, MigrationStatus
        )

        service = VectorSyncService()

        assert service.get_migration_status() == MigrationStatus.IDLE
        assert service.get_migration_progress() is None

    def test_cancel_migration_when_not_running(
        self,
        mock_settings,
        reset_singleton
    ):
        """Test Cancel wenn keine Migration laeuft."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        result = service.cancel_migration()

        assert result is False


class TestVectorSyncServiceStatus:
    """Tests fuer Status-Abruf."""

    @pytest.mark.asyncio
    async def test_get_sync_status(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service
    ):
        """Test Sync-Status abrufen."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        status = await service.get_sync_status()

        assert "enabled" in status
        assert "async_mode" in status
        assert "qdrant_connected" in status
        assert "collection" in status

    @pytest.mark.asyncio
    async def test_get_sync_status_reflects_config(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service
    ):
        """Test dass Status Config widerspiegelt."""
        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        status = await service.get_sync_status()

        assert status["enabled"] is True
        assert status["async_mode"] is False
        assert status["collection"] == "chunks"

    @pytest.mark.asyncio
    async def test_get_sync_status_with_error(
        self,
        mock_settings,
        reset_singleton,
        mock_qdrant_service
    ):
        """Test Status bei Qdrant-Fehler."""
        mock_qdrant_service.health_check = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        from app.services.rag.vector_sync_service import VectorSyncService

        service = VectorSyncService()
        status = await service.get_sync_status()

        assert status["qdrant_connected"] is False
        assert "error" in status


class TestSyncResult:
    """Tests fuer SyncResult TypedDict."""

    def test_sync_result_success(self):
        """Test SyncResult bei Erfolg."""
        from app.services.rag.vector_sync_service import SyncResult

        result: SyncResult = {
            "success": True,
            "synced_count": 10,
            "failed_count": 0,
            "skipped_count": 0,
            "duration_ms": 100.5
        }

        assert result["success"] is True
        assert result["synced_count"] == 10

    def test_sync_result_with_error(self):
        """Test SyncResult mit Fehler."""
        from app.services.rag.vector_sync_service import SyncResult

        result: SyncResult = {
            "success": False,
            "synced_count": 5,
            "failed_count": 5,
            "skipped_count": 0,
            "duration_ms": 200.0,
            "error": "Partial failure"
        }

        assert result["success"] is False
        assert result["error"] == "Partial failure"


class TestMigrationProgress:
    """Tests fuer MigrationProgress TypedDict."""

    def test_migration_progress_creation(self):
        """Test MigrationProgress Erstellung."""
        from app.services.rag.vector_sync_service import MigrationProgress

        progress: MigrationProgress = {
            "status": "running",
            "total_chunks": 1000,
            "processed_chunks": 250,
            "synced_chunks": 240,
            "failed_chunks": 10,
            "progress_percent": 25.0,
            "current_batch": 3,
            "total_batches": 10
        }

        assert progress["status"] == "running"
        assert progress["progress_percent"] == 25.0


class TestMigrationStatus:
    """Tests fuer MigrationStatus Enum."""

    def test_migration_status_values(self):
        """Test MigrationStatus Werte."""
        from app.services.rag.vector_sync_service import MigrationStatus

        assert MigrationStatus.IDLE.value == "idle"
        assert MigrationStatus.RUNNING.value == "running"
        assert MigrationStatus.PAUSED.value == "paused"
        assert MigrationStatus.COMPLETED.value == "completed"
        assert MigrationStatus.FAILED.value == "failed"
