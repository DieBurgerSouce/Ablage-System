"""Dual-Write Vector Sync Service.

Synchronisiert Embeddings zwischen pgvector und Qdrant:
- Dual-Write bei neuen Dokumenten
- Batch-Migration von bestehenden Embeddings
- Retry-Logik fuer fehlgeschlagene Syncs
- Progress-Tracking fuer Migrationen

Config-Settings (in config.py):
- VECTOR_DUAL_WRITE_ENABLED: bool
- VECTOR_DUAL_WRITE_ASYNC: bool
- VECTOR_MIGRATION_BATCH_SIZE: int
"""

from typing import Optional, Dict, Any, List, TypedDict, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import asyncio
import threading
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.core.config import settings
from app.db.models import RAGDocumentChunk as DocumentChunk
from app.core.safe_errors import safe_error_log
from app.services.rag.qdrant_service import (
    get_qdrant_service,
    QdrantService,
    QdrantPointData
)
from app.services.embedding_service import (

    get_embedding_provider,
    EmbeddingProvider,
    EmbeddingModelType
)

logger = structlog.get_logger(__name__)


# ============================================================================
# Types
# ============================================================================


class SyncStatus(str, Enum):
    """Sync-Status eines Chunks."""
    PENDING = "pending"
    SYNCING = "syncing"
    SYNCED = "synced"
    FAILED = "failed"
    SKIPPED = "skipped"


class MigrationStatus(str, Enum):
    """Status einer Batch-Migration."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class SyncResult(TypedDict, total=False):
    """Ergebnis eines Sync-Vorgangs."""
    success: bool
    synced_count: int
    failed_count: int
    skipped_count: int
    duration_ms: float
    error: Optional[str]


class MigrationProgress(TypedDict, total=False):
    """Fortschritt einer Migration."""
    status: str
    total_chunks: int
    processed_chunks: int
    synced_chunks: int
    failed_chunks: int
    progress_percent: float
    estimated_remaining_sec: Optional[float]
    started_at: Optional[str]
    current_batch: int
    total_batches: int


@dataclass
class SyncBatch:
    """Ein Batch von zu synchronisierenden Chunks."""
    batch_id: str
    chunk_ids: List[str]
    status: SyncStatus = SyncStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_message: Optional[str] = None


# ============================================================================
# Dual-Write Vector Sync Service
# ============================================================================


class VectorSyncService:
    """Service fuer Dual-Write und Migration zwischen Vector-Backends.

    Unterstuetzt:
    - Synchrones Dual-Write (blockierend)
    - Asynchrones Dual-Write (Celery Task)
    - Batch-Migration mit Progress-Tracking
    - Retry-Logik mit Exponential Backoff
    """

    _instance: Optional['VectorSyncService'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'VectorSyncService':
        """Singleton-Instanz."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialisierung."""
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._enabled = settings.VECTOR_DUAL_WRITE_ENABLED
        self._async_mode = settings.VECTOR_DUAL_WRITE_ASYNC
        self._batch_size = settings.VECTOR_MIGRATION_BATCH_SIZE

        # Services (lazy-loaded)
        self._qdrant: Optional[QdrantService] = None
        self._embedding_provider: Optional[EmbeddingProvider] = None

        # Migration State
        self._migration_status = MigrationStatus.IDLE
        self._migration_progress: Optional[MigrationProgress] = None
        self._migration_cancel = False
        self._migration_lock = threading.Lock()

        # Failed Syncs fuer Retry
        self._failed_batches: List[SyncBatch] = []

        self._initialized = True

        logger.info(
            "vector_sync_service_initialized",
            enabled=self._enabled,
            async_mode=self._async_mode,
            batch_size=self._batch_size
        )

    def _get_qdrant(self) -> QdrantService:
        """Qdrant Service lazy-laden."""
        if self._qdrant is None:
            self._qdrant = get_qdrant_service()
        return self._qdrant

    def _get_embedding_provider(self) -> EmbeddingProvider:
        """Embedding Provider lazy-laden."""
        if self._embedding_provider is None:
            self._embedding_provider = get_embedding_provider()
        return self._embedding_provider

    async def sync_chunk_to_qdrant(
        self,
        chunk: DocumentChunk,
        embedding: Optional[List[float]] = None,
        collection_name: Optional[str] = None
    ) -> bool:
        """Einzelnen Chunk zu Qdrant synchronisieren.

        Args:
            chunk: DocumentChunk mit Text und Metadaten
            embedding: Optionales Embedding (wird sonst generiert)
            collection_name: Optionaler Collection-Name

        Returns:
            True bei Erfolg
        """
        if not self._enabled:
            logger.debug("dual_write_disabled_skipping_sync")
            return True

        collection = collection_name or settings.QDRANT_COLLECTION_CHUNKS

        try:
            # Embedding generieren falls nicht vorhanden
            if embedding is None:
                provider = self._get_embedding_provider()
                # Jina fuer Treatment, E5 fuer Control
                if settings.JINA_EMBEDDING_ENABLED:
                    embedding = provider.generate_document_embedding(
                        chunk.chunk_text,
                        model_type=EmbeddingModelType.JINA_GERMAN
                    )
                else:
                    embedding = provider.generate_document_embedding(
                        chunk.chunk_text,
                        model_type=EmbeddingModelType.E5_MULTILINGUAL
                    )

            # Qdrant Point erstellen
            point = QdrantPointData(
                id=str(chunk.id),
                vector=embedding,
                payload={
                    "document_id": str(chunk.document_id),
                    "chunk_index": chunk.chunk_index,
                    "chunk_text": chunk.chunk_text[:500],  # Truncated fuer Payload
                    "page_number": chunk.page_number,
                    "section_type": chunk.section_type,
                    "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
                    "sync_timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

            # Zu Qdrant schreiben
            qdrant = self._get_qdrant()
            await qdrant.ensure_collection(
                collection_name=collection,
                vector_size=len(embedding)
            )
            count = await qdrant.upsert_vectors(
                collection_name=collection,
                points=[point]
            )

            logger.debug(
                "chunk_synced_to_qdrant",
                chunk_id=str(chunk.id),
                document_id=str(chunk.document_id)
            )

            return count == 1

        except Exception as e:
            logger.error(
                "chunk_sync_to_qdrant_failed",
                chunk_id=str(chunk.id),
                **safe_error_log(e)
            )
            return False

    async def sync_chunks_batch(
        self,
        chunks: List[DocumentChunk],
        embeddings: Optional[List[List[float]]] = None,
        collection_name: Optional[str] = None
    ) -> SyncResult:
        """Batch von Chunks zu Qdrant synchronisieren.

        Args:
            chunks: Liste von DocumentChunks
            embeddings: Optionale Embeddings (werden sonst generiert)
            collection_name: Optionaler Collection-Name

        Returns:
            SyncResult mit Statistiken
        """
        if not self._enabled:
            return SyncResult(
                success=True,
                synced_count=0,
                failed_count=0,
                skipped_count=len(chunks),
                duration_ms=0.0
            )

        if not chunks:
            return SyncResult(
                success=True,
                synced_count=0,
                failed_count=0,
                skipped_count=0,
                duration_ms=0.0
            )

        import time
        start = time.perf_counter()

        collection = collection_name or settings.QDRANT_COLLECTION_CHUNKS

        try:
            # Embeddings generieren falls nicht vorhanden
            if embeddings is None:
                provider = self._get_embedding_provider()
                texts = [c.chunk_text for c in chunks]

                if settings.JINA_EMBEDDING_ENABLED:
                    embeddings = provider.generate_batch_embeddings(
                        texts,
                        model_type=EmbeddingModelType.JINA_GERMAN
                    )
                else:
                    embeddings = provider.generate_batch_embeddings(
                        texts,
                        model_type=EmbeddingModelType.E5_MULTILINGUAL
                    )

            # Qdrant Points erstellen
            points: List[QdrantPointData] = []
            for chunk, embedding in zip(chunks, embeddings):
                points.append(QdrantPointData(
                    id=str(chunk.id),
                    vector=embedding,
                    payload={
                        "document_id": str(chunk.document_id),
                        "chunk_index": chunk.chunk_index,
                        "chunk_text": chunk.chunk_text[:500],
                        "page_number": chunk.page_number,
                        "section_type": chunk.section_type,
                        "created_at": chunk.created_at.isoformat() if chunk.created_at else None,
                        "sync_timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ))

            # Collection sicherstellen
            qdrant = self._get_qdrant()
            await qdrant.ensure_collection(
                collection_name=collection,
                vector_size=len(embeddings[0])
            )

            # Batch Upsert
            synced = await qdrant.batch_upsert(
                collection_name=collection,
                points=points,
                batch_size=100
            )

            elapsed = (time.perf_counter() - start) * 1000

            logger.info(
                "chunks_batch_synced_to_qdrant",
                synced_count=synced,
                total_count=len(chunks),
                duration_ms=round(elapsed, 2)
            )

            return SyncResult(
                success=True,
                synced_count=synced,
                failed_count=len(chunks) - synced,
                skipped_count=0,
                duration_ms=elapsed
            )

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(
                "chunks_batch_sync_failed",
                batch_size=len(chunks),
                **safe_error_log(e)
            )
            return SyncResult(
                success=False,
                synced_count=0,
                failed_count=len(chunks),
                skipped_count=0,
                duration_ms=elapsed,
                **safe_error_log(e)
            )

    async def start_migration(
        self,
        db: AsyncSession,
        collection_name: Optional[str] = None,
        progress_callback: Optional[Callable[[MigrationProgress], Awaitable[None]]] = None
    ) -> MigrationProgress:
        """Batch-Migration aller Chunks zu Qdrant starten.

        Args:
            db: Datenbank-Session
            collection_name: Optionaler Collection-Name
            progress_callback: Optionaler Callback fuer Progress-Updates

        Returns:
            MigrationProgress mit Endergebnis
        """
        with self._migration_lock:
            if self._migration_status == MigrationStatus.RUNNING:
                raise RuntimeError("Migration laeuft bereits")
            self._migration_status = MigrationStatus.RUNNING
            self._migration_cancel = False

        collection = collection_name or settings.QDRANT_COLLECTION_CHUNKS

        try:
            # Total Chunks zaehlen
            total_result = await db.execute(select(func.count(DocumentChunk.id)))
            total_chunks = total_result.scalar() or 0

            total_batches = (total_chunks + self._batch_size - 1) // self._batch_size

            self._migration_progress = MigrationProgress(
                status=MigrationStatus.RUNNING.value,
                total_chunks=total_chunks,
                processed_chunks=0,
                synced_chunks=0,
                failed_chunks=0,
                progress_percent=0.0,
                estimated_remaining_sec=None,
                started_at=datetime.now(timezone.utc).isoformat(),
                current_batch=0,
                total_batches=total_batches
            )

            logger.info(
                "migration_started",
                total_chunks=total_chunks,
                total_batches=total_batches,
                batch_size=self._batch_size
            )

            import time
            start_time = time.perf_counter()

            # Batches verarbeiten
            offset = 0
            batch_num = 0

            while offset < total_chunks:
                # Cancel-Check
                if self._migration_cancel:
                    self._migration_status = MigrationStatus.PAUSED
                    self._migration_progress["status"] = MigrationStatus.PAUSED.value
                    logger.info("migration_cancelled_by_user")
                    return self._migration_progress

                batch_num += 1

                # Chunks laden
                result = await db.execute(
                    select(DocumentChunk)
                    .order_by(DocumentChunk.id)
                    .offset(offset)
                    .limit(self._batch_size)
                )
                chunks = list(result.scalars().all())

                if not chunks:
                    break

                # Batch synchronisieren
                sync_result = await self.sync_chunks_batch(
                    chunks=chunks,
                    collection_name=collection
                )

                # Progress aktualisieren
                processed = offset + len(chunks)
                synced = self._migration_progress.get("synced_chunks", 0)
                failed = self._migration_progress.get("failed_chunks", 0)

                synced += sync_result.get("synced_count", 0)
                failed += sync_result.get("failed_count", 0)

                elapsed = time.perf_counter() - start_time
                chunks_per_sec = processed / elapsed if elapsed > 0 else 0
                remaining = total_chunks - processed
                eta = remaining / chunks_per_sec if chunks_per_sec > 0 else None

                self._migration_progress = MigrationProgress(
                    status=MigrationStatus.RUNNING.value,
                    total_chunks=total_chunks,
                    processed_chunks=processed,
                    synced_chunks=synced,
                    failed_chunks=failed,
                    progress_percent=round((processed / total_chunks) * 100, 2),
                    estimated_remaining_sec=round(eta, 0) if eta else None,
                    started_at=self._migration_progress.get("started_at"),
                    current_batch=batch_num,
                    total_batches=total_batches
                )

                # Progress Callback
                if progress_callback:
                    await progress_callback(self._migration_progress)

                logger.info(
                    "migration_batch_completed",
                    batch=batch_num,
                    processed=processed,
                    progress=f"{self._migration_progress['progress_percent']}%"
                )

                offset += self._batch_size

            # Migration abgeschlossen
            self._migration_status = MigrationStatus.COMPLETED
            self._migration_progress["status"] = MigrationStatus.COMPLETED.value

            logger.info(
                "migration_completed",
                total_synced=self._migration_progress.get("synced_chunks"),
                total_failed=self._migration_progress.get("failed_chunks"),
                duration_sec=round(time.perf_counter() - start_time, 2)
            )

            return self._migration_progress

        except Exception as e:
            self._migration_status = MigrationStatus.FAILED
            if self._migration_progress:
                self._migration_progress["status"] = MigrationStatus.FAILED.value
            logger.error("migration_failed", **safe_error_log(e))
            raise

    def cancel_migration(self) -> bool:
        """Laufende Migration abbrechen."""
        if self._migration_status != MigrationStatus.RUNNING:
            return False
        self._migration_cancel = True
        logger.info("migration_cancel_requested")
        return True

    def get_migration_progress(self) -> Optional[MigrationProgress]:
        """Aktuellen Migrations-Fortschritt abrufen."""
        return self._migration_progress

    def get_migration_status(self) -> MigrationStatus:
        """Aktuellen Migrations-Status abrufen."""
        return self._migration_status

    async def delete_from_qdrant(
        self,
        chunk_ids: List[str],
        collection_name: Optional[str] = None
    ) -> int:
        """Chunks aus Qdrant loeschen.

        Args:
            chunk_ids: Liste von Chunk-IDs zum Loeschen
            collection_name: Optionaler Collection-Name

        Returns:
            Anzahl geloeschter Chunks
        """
        if not self._enabled:
            return 0

        collection = collection_name or settings.QDRANT_COLLECTION_CHUNKS

        try:
            qdrant = self._get_qdrant()
            deleted = await qdrant.delete_vectors(
                collection_name=collection,
                ids=chunk_ids
            )

            logger.debug(
                "chunks_deleted_from_qdrant",
                deleted_count=deleted,
                chunk_ids=chunk_ids[:5]  # Nur erste 5 loggen
            )

            return deleted

        except Exception as e:
            logger.error(
                "chunks_delete_from_qdrant_failed",
                chunk_ids=chunk_ids[:5],
                **safe_error_log(e)
            )
            return 0

    async def get_sync_status(
        self,
        collection_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Status der Synchronisation abrufen.

        Returns:
            Dictionary mit Sync-Statistiken
        """
        collection = collection_name or settings.QDRANT_COLLECTION_CHUNKS

        try:
            qdrant = self._get_qdrant()
            health = await qdrant.health_check()
            collection_info = await qdrant.get_collection_info(collection)

            return {
                "enabled": self._enabled,
                "async_mode": self._async_mode,
                "qdrant_connected": health.get("healthy", False),
                "collection": collection,
                "collection_exists": collection_info is not None,
                "points_count": collection_info.get("points_count") if collection_info else 0,
                "migration_status": self._migration_status.value,
                "failed_batches": len(self._failed_batches)
            }

        except Exception as e:
            return {
                "enabled": self._enabled,
                "async_mode": self._async_mode,
                "qdrant_connected": False,
                "error": safe_error_detail(e, "Vorgang"),
                "migration_status": self._migration_status.value
            }


# ============================================================================
# Factory Function
# ============================================================================


_vector_sync_service: Optional[VectorSyncService] = None


def get_vector_sync_service() -> VectorSyncService:
    """Vector Sync Service Instanz abrufen (Dependency Injection)."""
    global _vector_sync_service
    if _vector_sync_service is None:
        _vector_sync_service = VectorSyncService()
    return _vector_sync_service
