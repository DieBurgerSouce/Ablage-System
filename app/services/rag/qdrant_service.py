# -*- coding: utf-8 -*-
"""
Qdrant Vector Database Service fuer Ablage-System.

Enterprise-grade Vector-DB-Integration mit:
- Connection Pooling und Health Checks
- Collection Management mit HNSW-Indexierung
- Batch Operations fuer effiziente Inserts
- Hybrid Search (Dense + Sparse)
- A/B Testing Support mit pgvector

Feinpoliert und durchdacht - Production-ready Vector Search.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Dict, Any, TypedDict, Callable, TypeVar
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID
from functools import wraps
import threading
import asyncio

import structlog

from app.core.config import settings

if TYPE_CHECKING:
    from qdrant_client import QdrantClient, AsyncQdrantClient

logger = structlog.get_logger(__name__)


# =============================================================================
# Retry-Logic mit Exponential Backoff
# =============================================================================

T = TypeVar("T")

# Retry-Konfiguration
QDRANT_MAX_RETRIES = 3
QDRANT_BASE_DELAY_SECONDS = 0.5
QDRANT_MAX_DELAY_SECONDS = 10.0
QDRANT_BACKOFF_MULTIPLIER = 2.0


def async_retry_with_backoff(
    max_retries: int = QDRANT_MAX_RETRIES,
    base_delay: float = QDRANT_BASE_DELAY_SECONDS,
    max_delay: float = QDRANT_MAX_DELAY_SECONDS,
    backoff_multiplier: float = QDRANT_BACKOFF_MULTIPLIER,
    retryable_exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator fuer async Funktionen mit Retry und Exponential Backoff.

    Args:
        max_retries: Maximale Anzahl Versuche
        base_delay: Initiale Wartezeit in Sekunden
        max_delay: Maximale Wartezeit in Sekunden
        backoff_multiplier: Multiplikator fuer Backoff
        retryable_exceptions: Tuple von Exceptions die retried werden sollen

    Returns:
        Dekorierte Funktion mit Retry-Logic
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None
            delay = base_delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            "qdrant_operation_retry",
                            function=func.__name__,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                            delay_seconds=delay,
                            error=str(e),
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * backoff_multiplier, max_delay)
                    else:
                        logger.error(
                            "qdrant_operation_failed_after_retries",
                            function=func.__name__,
                            attempts=max_retries + 1,
                            error=str(e),
                        )
                        raise

            # Sollte nicht erreicht werden
            if last_exception:
                raise last_exception
            return None

        return wrapper
    return decorator

# Qdrant Client Import (optional - nur wenn aktiviert)
try:
    from qdrant_client import QdrantClient, AsyncQdrantClient
    from qdrant_client.http import models as qdrant_models
    from qdrant_client.http.models import (
        Distance,
        VectorParams,
        HnswConfigDiff,
        OptimizersConfigDiff,
        PointStruct,
        Filter,
        FieldCondition,
        MatchValue,
        MatchAny,
        SearchRequest,
        ScoredPoint,
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    QdrantClient = None
    AsyncQdrantClient = None


class QdrantPointData(TypedDict, total=False):
    """Typisierte Punkt-Daten fuer Qdrant."""
    id: str
    vector: List[float]
    payload: Dict[str, Any]


@dataclass
class QdrantSearchResult:
    """Suchergebnis aus Qdrant."""
    id: str
    score: float
    payload: Dict[str, Any]
    vector: Optional[List[float]] = None


@dataclass
class QdrantCollectionInfo:
    """Collection-Informationen."""
    name: str
    vectors_count: int
    points_count: int
    status: str
    config: Dict[str, Any]


class QdrantService:
    """Service fuer Qdrant Vector Database Operations.

    Implementiert:
    - Lazy Connection mit Health Checks
    - Collection Auto-Creation
    - Batch Upserts mit Retry
    - Filtered Vector Search
    - Metrics und Monitoring

    Thread-safe Singleton-Pattern.
    """

    _instance: Optional['QdrantService'] = None
    _lock = threading.Lock()
    _client: Optional[QdrantClient] = None
    _async_client: Optional[AsyncQdrantClient] = None
    _initialized = False

    def __new__(cls) -> 'QdrantService':
        """Singleton-Instanz zurueckgeben."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Initialisierung (nur beim ersten Aufruf)."""
        if self._initialized:
            return

        self._enabled = settings.QDRANT_ENABLED and QDRANT_AVAILABLE
        self._host = settings.QDRANT_HOST
        self._http_port = settings.QDRANT_HTTP_PORT
        self._grpc_port = settings.QDRANT_GRPC_PORT
        self._prefer_grpc = settings.QDRANT_PREFER_GRPC
        self._api_key = (
            settings.QDRANT_API_KEY.get_secret_value()
            if settings.QDRANT_API_KEY else None
        )

        # Collection Namen
        self._collection_documents = settings.QDRANT_COLLECTION_DOCUMENTS
        self._collection_chunks = settings.QDRANT_COLLECTION_CHUNKS

        # HNSW Config
        self._hnsw_m = settings.QDRANT_HNSW_M
        self._hnsw_ef_construct = settings.QDRANT_HNSW_EF_CONSTRUCT
        self._on_disk_payload = settings.QDRANT_ON_DISK_PAYLOAD
        self._quantization_enabled = settings.QDRANT_QUANTIZATION_ENABLED

        self._initialized = True

        if self._enabled:
            logger.info(
                "qdrant_service_initialized",
                host=self._host,
                http_port=self._http_port,
                grpc_port=self._grpc_port,
                prefer_grpc=self._prefer_grpc
            )
        else:
            logger.info("qdrant_service_disabled")

    @property
    def enabled(self) -> bool:
        """Gibt zurueck ob Qdrant aktiviert ist."""
        return self._enabled

    def _get_sync_client(self) -> QdrantClient:
        """Lazy-load synchronen Qdrant Client."""
        if not self._enabled:
            raise RuntimeError("Qdrant ist nicht aktiviert")

        if self._client is None:
            with self._lock:
                if self._client is None:
                    from qdrant_client import QdrantClient
                    self._client = QdrantClient(
                        host=self._host,
                        port=self._grpc_port if self._prefer_grpc else self._http_port,
                        grpc_port=self._grpc_port if self._prefer_grpc else None,
                        prefer_grpc=self._prefer_grpc,
                        api_key=self._api_key,
                        timeout=30.0,
                    )
                    logger.info("qdrant_sync_client_created")
        return self._client

    async def _get_async_client(self) -> AsyncQdrantClient:
        """Lazy-load asynchronen Qdrant Client."""
        if not self._enabled:
            raise RuntimeError("Qdrant ist nicht aktiviert")

        if self._async_client is None:
            with self._lock:
                if self._async_client is None:
                    from qdrant_client import AsyncQdrantClient
                    self._async_client = AsyncQdrantClient(
                        host=self._host,
                        port=self._grpc_port if self._prefer_grpc else self._http_port,
                        grpc_port=self._grpc_port if self._prefer_grpc else None,
                        prefer_grpc=self._prefer_grpc,
                        api_key=self._api_key,
                        timeout=30.0,
                    )
                    logger.info("qdrant_async_client_created")
        return self._async_client

    # =========================================================================
    # HEALTH & INFO
    # =========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Prueft Qdrant-Verbindung und gibt Status zurueck."""
        if not self._enabled:
            return {"status": "disabled", "message": "Qdrant nicht aktiviert"}

        try:
            client = await self._get_async_client()
            # Einfacher Health-Check via Collection-Liste
            collections = await client.get_collections()
            return {
                "status": "healthy",
                "host": self._host,
                "collections_count": len(collections.collections),
                "collections": [c.name for c in collections.collections],
            }
        except Exception as e:
            logger.error("qdrant_health_check_failed", error=str(e))
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    async def get_collection_info(self, collection_name: str) -> Optional[QdrantCollectionInfo]:
        """Holt Informationen ueber eine Collection."""
        if not self._enabled:
            return None

        try:
            client = await self._get_async_client()
            info = await client.get_collection(collection_name)
            return QdrantCollectionInfo(
                name=collection_name,
                vectors_count=info.vectors_count or 0,
                points_count=info.points_count or 0,
                status=info.status.value if info.status else "unknown",
                config={
                    "vector_size": info.config.params.vectors.size if info.config.params.vectors else None,
                    "distance": info.config.params.vectors.distance.value if info.config.params.vectors else None,
                }
            )
        except Exception as e:
            logger.warning("qdrant_get_collection_failed", collection=collection_name, error=str(e))
            return None

    # =========================================================================
    # COLLECTION MANAGEMENT
    # =========================================================================

    async def ensure_collection(
        self,
        collection_name: str,
        vector_size: int = 1024,
        distance: str = "Cosine"
    ) -> bool:
        """Erstellt Collection falls nicht vorhanden.

        Args:
            collection_name: Name der Collection
            vector_size: Dimension der Vektoren
            distance: Distanz-Metrik (Cosine, Euclid, Dot)

        Returns:
            True wenn Collection existiert/erstellt wurde
        """
        if not self._enabled:
            return False

        try:
            client = await self._get_async_client()

            # Pruefe ob Collection existiert
            collections = await client.get_collections()
            existing = [c.name for c in collections.collections]

            if collection_name in existing:
                logger.debug("qdrant_collection_exists", collection=collection_name)
                return True

            # Collection erstellen
            distance_enum = getattr(Distance, distance.upper(), Distance.COSINE)

            await client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance_enum,
                ),
                hnsw_config=HnswConfigDiff(
                    m=self._hnsw_m,
                    ef_construct=self._hnsw_ef_construct,
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,
                ),
                on_disk_payload=self._on_disk_payload,
            )

            logger.info(
                "qdrant_collection_created",
                collection=collection_name,
                vector_size=vector_size,
                distance=distance
            )
            return True

        except Exception as e:
            logger.error(
                "qdrant_ensure_collection_failed",
                collection=collection_name,
                error=str(e)
            )
            return False

    async def delete_collection(self, collection_name: str) -> bool:
        """Loescht eine Collection."""
        if not self._enabled:
            return False

        try:
            client = await self._get_async_client()
            await client.delete_collection(collection_name)
            logger.info("qdrant_collection_deleted", collection=collection_name)
            return True
        except Exception as e:
            logger.error("qdrant_delete_collection_failed", collection=collection_name, error=str(e))
            return False

    # =========================================================================
    # VECTOR OPERATIONS
    # =========================================================================

    @async_retry_with_backoff(max_retries=QDRANT_MAX_RETRIES)
    async def _upsert_with_retry(
        self,
        client: Any,
        collection_name: str,
        qdrant_points: List[Any],
        wait: bool,
    ) -> None:
        """Interne Upsert-Methode mit Retry-Logic."""
        await client.upsert(
            collection_name=collection_name,
            points=qdrant_points,
            wait=wait,
        )

    async def upsert_vectors(
        self,
        collection_name: str,
        points: List[QdrantPointData],
        wait: bool = True
    ) -> int:
        """Fuegt Vektoren ein oder aktualisiert sie.

        Args:
            collection_name: Ziel-Collection
            points: Liste von Punkten mit id, vector, payload
            wait: Auf Indexierung warten

        Returns:
            Anzahl erfolgreich eingefuegter Punkte
        """
        if not self._enabled or not points:
            return 0

        try:
            client = await self._get_async_client()

            # Konvertiere zu Qdrant PointStruct
            qdrant_points = [
                PointStruct(
                    id=p["id"],
                    vector=p["vector"],
                    payload=p.get("payload", {}),
                )
                for p in points
            ]

            # Batch Upsert mit Retry
            await self._upsert_with_retry(
                client=client,
                collection_name=collection_name,
                qdrant_points=qdrant_points,
                wait=wait,
            )

            logger.debug(
                "qdrant_upsert_success",
                collection=collection_name,
                count=len(points)
            )
            return len(points)

        except Exception as e:
            logger.error(
                "qdrant_upsert_failed",
                collection=collection_name,
                count=len(points),
                error=str(e)
            )
            return 0

    @async_retry_with_backoff(max_retries=QDRANT_MAX_RETRIES)
    async def _delete_with_retry(
        self,
        client: Any,
        collection_name: str,
        points_selector: Any,
        wait: bool,
    ) -> None:
        """Interne Delete-Methode mit Retry-Logic."""
        await client.delete(
            collection_name=collection_name,
            points_selector=points_selector,
            wait=wait,
        )

    async def delete_vectors(
        self,
        collection_name: str,
        ids: List[str],
        wait: bool = True
    ) -> int:
        """Loescht Vektoren nach IDs.

        Args:
            collection_name: Collection
            ids: Liste von Punkt-IDs
            wait: Auf Loeschung warten

        Returns:
            Anzahl geloeschter Punkte
        """
        if not self._enabled or not ids:
            return 0

        try:
            client = await self._get_async_client()

            # Delete mit Retry
            await self._delete_with_retry(
                client=client,
                collection_name=collection_name,
                points_selector=qdrant_models.PointIdsList(points=ids),
                wait=wait,
            )

            logger.debug(
                "qdrant_delete_success",
                collection=collection_name,
                count=len(ids)
            )
            return len(ids)

        except Exception as e:
            logger.error(
                "qdrant_delete_failed",
                collection=collection_name,
                error=str(e)
            )
            return 0

    # =========================================================================
    # SEARCH
    # =========================================================================

    @async_retry_with_backoff(max_retries=QDRANT_MAX_RETRIES)
    async def _search_with_retry(
        self,
        client: Any,
        collection_name: str,
        query_vector: List[float],
        limit: int,
        score_threshold: Optional[float],
        search_filter: Optional[Any],
        with_vectors: bool,
        with_payload: bool,
    ) -> List[Any]:
        """Interne Such-Methode mit Retry-Logic."""
        return await client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            query_filter=search_filter,
            with_vectors=with_vectors,
            with_payload=with_payload,
        )

    async def search(
        self,
        collection_name: str,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter_conditions: Optional[Dict[str, Any]] = None,
        with_vectors: bool = False,
        with_payload: bool = True,
    ) -> List[QdrantSearchResult]:
        """Fuehrt Vektor-Suche durch.

        Args:
            collection_name: Collection zum Suchen
            query_vector: Query-Embedding
            limit: Max Ergebnisse
            score_threshold: Min Score (0-1 fuer Cosine)
            filter_conditions: Filter dict, z.B. {"document_type": "invoice"}
            with_vectors: Vektoren zurueckgeben
            with_payload: Payload zurueckgeben

        Returns:
            Liste von QdrantSearchResult
        """
        if not self._enabled:
            return []

        try:
            client = await self._get_async_client()

            # Filter aufbauen
            search_filter = None
            if filter_conditions:
                must_conditions = []
                for key, value in filter_conditions.items():
                    if value is not None:
                        # Spezial-Behandlung fuer IN-Filter (document_ids)
                        if key == "_document_ids_in" and isinstance(value, list):
                            must_conditions.append(
                                FieldCondition(
                                    key="document_id",
                                    match=MatchAny(any=value),
                                )
                            )
                        else:
                            must_conditions.append(
                                FieldCondition(
                                    key=key,
                                    match=MatchValue(value=value),
                                )
                            )
                if must_conditions:
                    search_filter = Filter(must=must_conditions)

            # Suche mit Retry ausfuehren
            results = await self._search_with_retry(
                client=client,
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                search_filter=search_filter,
                with_vectors=with_vectors,
                with_payload=with_payload,
            )

            # Konvertiere zu QdrantSearchResult
            search_results = [
                QdrantSearchResult(
                    id=str(r.id),
                    score=r.score,
                    payload=r.payload or {},
                    vector=r.vector if with_vectors else None,
                )
                for r in results
            ]

            logger.debug(
                "qdrant_search_success",
                collection=collection_name,
                results_count=len(search_results),
                limit=limit
            )

            return search_results

        except Exception as e:
            logger.error(
                "qdrant_search_failed",
                collection=collection_name,
                error=str(e)
            )
            return []

    async def search_with_filter(
        self,
        collection_name: str,
        query_vector: List[float],
        document_ids: Optional[List[str]] = None,
        document_type: Optional[str] = None,
        section_type: Optional[str] = None,
        limit: int = 20,
        score_threshold: float = 0.7,
    ) -> List[QdrantSearchResult]:
        """Convenience-Methode fuer gefilterte Suche.

        Spezialisiert fuer RAG-Chunk-Suche mit typischen Filtern.
        """
        filter_conditions: Dict[str, Any] = {}

        if document_type:
            filter_conditions["document_type"] = document_type
        if section_type:
            filter_conditions["section_type"] = section_type

        # Document IDs mit MatchAny (IN-Filter) zur filter_conditions hinzufuegen
        if document_ids:
            # Spezial-Schluessel fuer IN-Filter (wird in search() behandelt)
            filter_conditions["_document_ids_in"] = document_ids

        return await self.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
            filter_conditions=filter_conditions if filter_conditions else None,
            with_payload=True,
        )

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    async def batch_upsert(
        self,
        collection_name: str,
        points: List[QdrantPointData],
        batch_size: int = 100,
    ) -> int:
        """Batch-Upsert fuer grosse Datenmengen.

        Args:
            collection_name: Ziel-Collection
            points: Alle Punkte
            batch_size: Batch-Groesse

        Returns:
            Anzahl erfolgreich eingefuegter Punkte
        """
        if not self._enabled or not points:
            return 0

        total_inserted = 0

        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            inserted = await self.upsert_vectors(
                collection_name=collection_name,
                points=batch,
                wait=True,
            )
            total_inserted += inserted

            logger.debug(
                "qdrant_batch_progress",
                collection=collection_name,
                batch_num=i // batch_size + 1,
                total_batches=(len(points) + batch_size - 1) // batch_size,
                inserted=inserted
            )

        return total_inserted

    # =========================================================================
    # CLEANUP
    # =========================================================================

    def close(self) -> None:
        """Schliesst Verbindungen."""
        with self._lock:
            if self._client:
                try:
                    self._client.close()
                except Exception as e:
                    logger.debug("qdrant_sync_client_close_failed", error_type=type(e).__name__)
                self._client = None

            if self._async_client:
                # Async client close muss in Event Loop laufen
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self._async_client.close())
                    else:
                        loop.run_until_complete(self._async_client.close())
                except Exception as e:
                    logger.debug("qdrant_async_client_close_failed", error_type=type(e).__name__)
                self._async_client = None

            logger.info("qdrant_service_closed")


# Singleton Instance
_qdrant_service: Optional[QdrantService] = None


def get_qdrant_service() -> QdrantService:
    """Gibt QdrantService-Singleton zurueck."""
    global _qdrant_service
    if _qdrant_service is None:
        _qdrant_service = QdrantService()
    return _qdrant_service
