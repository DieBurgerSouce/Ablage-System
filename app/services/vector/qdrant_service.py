"""
Qdrant Vector Database Service.

Parallele Vector-DB neben pgvector fuer A/B Testing.
Rust-basiert mit 48% besserer p99-Latenz als pgvector.

Features:
- Collection Management (Documents, Chunks)
- Batch Upsert mit Progress Tracking
- Semantic Search mit Filtering
- HNSW Index Konfiguration
- gRPC und REST Support

Feinpoliert und durchdacht.
"""

from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
import asyncio
from datetime import datetime

import structlog
from pydantic import BaseModel, Field

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Lazy import fuer qdrant-client (nur wenn aktiviert)
_qdrant_client = None
_qdrant_models = None


def _get_qdrant_imports():
    """Lazy import von qdrant-client."""
    global _qdrant_client, _qdrant_models
    if _qdrant_client is None:
        try:
            from qdrant_client import QdrantClient, AsyncQdrantClient
            from qdrant_client import models as qdrant_models
            _qdrant_client = (QdrantClient, AsyncQdrantClient)
            _qdrant_models = qdrant_models
        except ImportError:
            logger.warning(
                "qdrant_client_not_installed",
                message="qdrant-client nicht installiert. Installiere mit: pip install qdrant-client"
            )
            raise ImportError("qdrant-client nicht installiert")
    return _qdrant_client, _qdrant_models


class QdrantPoint(BaseModel):
    """Datenmodell fuer einen Qdrant Vector Point."""
    id: str  # UUID als String
    vector: List[float]
    payload: Dict[str, Any] = Field(default_factory=dict)


class QdrantSearchResult(BaseModel):
    """Suchergebnis von Qdrant."""
    id: str
    score: float
    payload: Dict[str, Any]


class QdrantService:
    """
    Qdrant Vector Database Service.

    Thread-safe Singleton fuer Qdrant-Verbindungen.
    """

    _instance: Optional["QdrantService"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        """Initialisiere QdrantService."""
        self._client: Optional[Any] = None
        self._async_client: Optional[Any] = None
        self._initialized = False
        self._collections_created = False

    @classmethod
    async def get_instance(cls) -> "QdrantService":
        """Get Singleton Instance (thread-safe)."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @property
    def is_enabled(self) -> bool:
        """Prueft ob Qdrant aktiviert ist."""
        return settings.QDRANT_ENABLED

    async def initialize(self) -> bool:
        """
        Initialisiere Qdrant-Verbindung und Collections.

        Returns:
            True wenn erfolgreich initialisiert
        """
        if not self.is_enabled:
            logger.debug("qdrant_disabled", message="Qdrant ist nicht aktiviert")
            return False

        if self._initialized:
            return True

        try:
            QdrantClient, AsyncQdrantClient = _get_qdrant_imports()[0]

            # API Key extrahieren
            api_key = None
            if settings.QDRANT_API_KEY:
                api_key = settings.QDRANT_API_KEY.get_secret_value()

            # gRPC oder REST basierend auf Konfiguration
            if settings.QDRANT_PREFER_GRPC:
                self._async_client = AsyncQdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_GRPC_PORT,
                    grpc_port=settings.QDRANT_GRPC_PORT,
                    prefer_grpc=True,
                    api_key=api_key,
                )
            else:
                self._async_client = AsyncQdrantClient(
                    host=settings.QDRANT_HOST,
                    port=settings.QDRANT_HTTP_PORT,
                    prefer_grpc=False,
                    api_key=api_key,
                )

            # Sync Client fuer bestimmte Operationen
            self._client = QdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_HTTP_PORT,
                api_key=api_key,
            )

            # Verbindung testen
            collections = await self._async_client.get_collections()
            logger.info(
                "qdrant_connected",
                host=settings.QDRANT_HOST,
                grpc=settings.QDRANT_PREFER_GRPC,
                collections_count=len(collections.collections)
            )

            self._initialized = True

            # Collections erstellen falls nicht vorhanden
            await self._ensure_collections()

            return True

        except ImportError:
            logger.error("qdrant_import_error", message="qdrant-client nicht installiert")
            return False
        except Exception as e:
            logger.error("qdrant_connection_error", error=str(e))
            return False

    async def _ensure_collections(self) -> None:
        """Erstelle Collections falls nicht vorhanden."""
        if self._collections_created:
            return

        _, models = _get_qdrant_imports()

        # Document Collection
        await self._create_collection_if_not_exists(
            name=settings.QDRANT_COLLECTION_DOCUMENTS,
            vector_size=settings.EMBEDDING_DIMENSION,
        )

        # Chunks Collection
        await self._create_collection_if_not_exists(
            name=settings.QDRANT_COLLECTION_CHUNKS,
            vector_size=settings.EMBEDDING_DIMENSION,
        )

        self._collections_created = True

    async def _create_collection_if_not_exists(
        self,
        name: str,
        vector_size: int,
    ) -> bool:
        """
        Erstelle Collection falls nicht vorhanden.

        Args:
            name: Collection Name
            vector_size: Vektor-Dimension

        Returns:
            True wenn erstellt oder bereits vorhanden
        """
        _, models = _get_qdrant_imports()

        try:
            # Pruefe ob Collection existiert
            collections = await self._async_client.get_collections()
            existing = [c.name for c in collections.collections]

            if name in existing:
                logger.debug("qdrant_collection_exists", collection=name)
                return True

            # HNSW Konfiguration
            hnsw_config = models.HnswConfigDiff(
                m=settings.QDRANT_HNSW_M,
                ef_construct=settings.QDRANT_HNSW_EF_CONSTRUCT,
            )

            # Quantization (optional)
            quantization_config = None
            if settings.QDRANT_QUANTIZATION_ENABLED:
                quantization_config = models.ScalarQuantization(
                    scalar=models.ScalarQuantizationConfig(
                        type=models.ScalarType.INT8,
                        quantile=0.99,
                        always_ram=False,
                    )
                )

            # Collection erstellen
            await self._async_client.create_collection(
                collection_name=name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                    on_disk=settings.QDRANT_ON_DISK_PAYLOAD,
                ),
                hnsw_config=hnsw_config,
                quantization_config=quantization_config,
                on_disk_payload=settings.QDRANT_ON_DISK_PAYLOAD,
            )

            logger.info(
                "qdrant_collection_created",
                collection=name,
                vector_size=vector_size,
                hnsw_m=settings.QDRANT_HNSW_M,
                quantization=settings.QDRANT_QUANTIZATION_ENABLED,
            )
            return True

        except Exception as e:
            logger.error(
                "qdrant_collection_create_error",
                collection=name,
                error=str(e)
            )
            return False

    async def upsert_document(
        self,
        document_id: UUID,
        embedding: List[float],
        payload: Dict[str, Any],
    ) -> bool:
        """
        Fuege Dokument-Embedding in Qdrant ein oder aktualisiere es.

        Args:
            document_id: Dokument-UUID
            embedding: Embedding-Vektor
            payload: Zusaetzliche Metadaten

        Returns:
            True wenn erfolgreich
        """
        if not await self.initialize():
            return False

        _, models = _get_qdrant_imports()

        try:
            point = models.PointStruct(
                id=str(document_id),
                vector=embedding,
                payload={
                    **payload,
                    "document_id": str(document_id),
                    "indexed_at": datetime.utcnow().isoformat(),
                }
            )

            await self._async_client.upsert(
                collection_name=settings.QDRANT_COLLECTION_DOCUMENTS,
                points=[point],
            )

            logger.debug(
                "qdrant_document_upserted",
                document_id=str(document_id)
            )
            return True

        except Exception as e:
            logger.error(
                "qdrant_upsert_error",
                document_id=str(document_id),
                error=str(e)
            )
            return False

    async def upsert_chunk(
        self,
        chunk_id: str,
        document_id: UUID,
        chunk_index: int,
        embedding: List[float],
        payload: Dict[str, Any],
    ) -> bool:
        """
        Fuege Chunk-Embedding in Qdrant ein.

        Args:
            chunk_id: Eindeutige Chunk-ID
            document_id: Parent Document UUID
            chunk_index: Index des Chunks im Dokument
            embedding: Embedding-Vektor
            payload: Zusaetzliche Metadaten

        Returns:
            True wenn erfolgreich
        """
        if not await self.initialize():
            return False

        _, models = _get_qdrant_imports()

        try:
            point = models.PointStruct(
                id=chunk_id,
                vector=embedding,
                payload={
                    **payload,
                    "document_id": str(document_id),
                    "chunk_index": chunk_index,
                    "indexed_at": datetime.utcnow().isoformat(),
                }
            )

            await self._async_client.upsert(
                collection_name=settings.QDRANT_COLLECTION_CHUNKS,
                points=[point],
            )
            return True

        except Exception as e:
            logger.error(
                "qdrant_chunk_upsert_error",
                chunk_id=chunk_id,
                error=str(e)
            )
            return False

    async def batch_upsert_documents(
        self,
        points: List[QdrantPoint],
        batch_size: int = 100,
    ) -> Tuple[int, int]:
        """
        Batch-Upsert von Dokumenten.

        Args:
            points: Liste von QdrantPoint-Objekten
            batch_size: Batch-Groesse

        Returns:
            Tuple von (erfolgreiche, fehlgeschlagene)
        """
        if not await self.initialize():
            return 0, len(points)

        _, models = _get_qdrant_imports()

        success = 0
        failed = 0

        # In Batches aufteilen
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]

            try:
                qdrant_points = [
                    models.PointStruct(
                        id=p.id,
                        vector=p.vector,
                        payload=p.payload,
                    )
                    for p in batch
                ]

                await self._async_client.upsert(
                    collection_name=settings.QDRANT_COLLECTION_DOCUMENTS,
                    points=qdrant_points,
                )
                success += len(batch)

            except Exception as e:
                logger.error(
                    "qdrant_batch_upsert_error",
                    batch_start=i,
                    batch_size=len(batch),
                    error=str(e)
                )
                failed += len(batch)

        logger.info(
            "qdrant_batch_upsert_complete",
            success=success,
            failed=failed,
            total=len(points)
        )
        return success, failed

    async def search(
        self,
        query_vector: List[float],
        collection: str = "documents",
        limit: int = 20,
        score_threshold: float = 0.5,
        filter_conditions: Optional[Dict[str, Any]] = None,
    ) -> List[QdrantSearchResult]:
        """
        Semantische Suche in Qdrant.

        Args:
            query_vector: Query-Embedding
            collection: "documents" oder "chunks"
            limit: Maximale Anzahl Ergebnisse
            score_threshold: Minimaler Similarity Score
            filter_conditions: Optional Filter (owner_id, document_type, etc.)

        Returns:
            Liste von QdrantSearchResult
        """
        if not await self.initialize():
            return []

        _, models = _get_qdrant_imports()

        # Collection Name bestimmen
        collection_name = (
            settings.QDRANT_COLLECTION_DOCUMENTS
            if collection == "documents"
            else settings.QDRANT_COLLECTION_CHUNKS
        )

        # Filter bauen
        query_filter = None
        if filter_conditions:
            must_conditions = []

            if "owner_id" in filter_conditions:
                must_conditions.append(
                    models.FieldCondition(
                        key="owner_id",
                        match=models.MatchValue(value=str(filter_conditions["owner_id"])),
                    )
                )

            if "document_type" in filter_conditions:
                must_conditions.append(
                    models.FieldCondition(
                        key="document_type",
                        match=models.MatchValue(value=filter_conditions["document_type"]),
                    )
                )

            if "document_id" in filter_conditions:
                must_conditions.append(
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=str(filter_conditions["document_id"])),
                    )
                )

            if must_conditions:
                query_filter = models.Filter(must=must_conditions)

        try:
            results = await self._async_client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=query_filter,
            )

            return [
                QdrantSearchResult(
                    id=str(r.id),
                    score=r.score,
                    payload=r.payload or {},
                )
                for r in results
            ]

        except Exception as e:
            logger.error(
                "qdrant_search_error",
                collection=collection_name,
                error=str(e)
            )
            return []

    async def delete_document(self, document_id: UUID) -> bool:
        """
        Loesche Dokument aus Qdrant.

        Args:
            document_id: Dokument-UUID

        Returns:
            True wenn erfolgreich
        """
        if not await self.initialize():
            return False

        _, models = _get_qdrant_imports()

        try:
            # Dokument loeschen
            await self._async_client.delete(
                collection_name=settings.QDRANT_COLLECTION_DOCUMENTS,
                points_selector=models.PointIdsList(
                    points=[str(document_id)],
                ),
            )

            # Zugehoerige Chunks loeschen
            await self._async_client.delete(
                collection_name=settings.QDRANT_COLLECTION_CHUNKS,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=str(document_id)),
                            )
                        ]
                    )
                ),
            )

            logger.info(
                "qdrant_document_deleted",
                document_id=str(document_id)
            )
            return True

        except Exception as e:
            logger.error(
                "qdrant_delete_error",
                document_id=str(document_id),
                error=str(e)
            )
            return False

    async def get_collection_info(self, collection: str = "documents") -> Optional[Dict[str, Any]]:
        """
        Hole Collection-Informationen.

        Args:
            collection: "documents" oder "chunks"

        Returns:
            Dict mit Collection-Info oder None
        """
        if not await self.initialize():
            return None

        collection_name = (
            settings.QDRANT_COLLECTION_DOCUMENTS
            if collection == "documents"
            else settings.QDRANT_COLLECTION_CHUNKS
        )

        try:
            info = await self._async_client.get_collection(collection_name)
            return {
                "name": collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status.value,
                "config": {
                    "vector_size": info.config.params.vectors.size,
                    "distance": info.config.params.vectors.distance.value,
                },
            }
        except Exception as e:
            logger.error(
                "qdrant_collection_info_error",
                collection=collection_name,
                error=str(e)
            )
            return None

    async def health_check(self) -> bool:
        """
        Pruefe Qdrant-Verbindung.

        Returns:
            True wenn gesund
        """
        if not self.is_enabled:
            return True  # Nicht aktiviert = kein Problem

        try:
            if not self._async_client:
                return False
            collections = await self._async_client.get_collections()
            return True
        except Exception:
            return False


# Singleton Instance
_qdrant_service: Optional[QdrantService] = None


async def get_qdrant_service() -> QdrantService:
    """Factory Function fuer QdrantService."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = await QdrantService.get_instance()
    return _qdrant_service
