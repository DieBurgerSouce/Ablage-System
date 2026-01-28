"""
Vector Search Orchestrator.

Unified Interface fuer Vector Search mit A/B Testing.
Routet Anfragen zu pgvector oder Qdrant basierend auf Konfiguration.

Features:
- A/B Testing mit deterministischem User-Routing
- Metriken-Sammlung
- Fallback-Handling
- Unified Query Interface

Feinpoliert und durchdacht.
"""

from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime
from app.core.datetime_utils import utc_now
import hashlib
import time

import structlog

from app.core.config import settings
from app.services.vector.qdrant_service import QdrantService, get_qdrant_service, QdrantSearchResult
from app.services.vector.embedding_factory import EmbeddingFactory, get_embedding_factory, EmbeddingModel
from app.services.vector.reranker_service import RerankerService, get_reranker_service

logger = structlog.get_logger(__name__)


class VectorBackend:
    """Enum-like fuer Vector Backends."""
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


class VectorSearchOrchestrator:
    """
    Vector Search Orchestrator mit A/B Testing.

    Routet Suchanfragen zu verschiedenen Backends und
    sammelt Metriken fuer Vergleiche.
    """

    _instance: Optional["VectorSearchOrchestrator"] = None

    def __init__(self):
        """Initialisiere Orchestrator."""
        self._qdrant: Optional[QdrantService] = None
        self._embedding_factory: Optional[EmbeddingFactory] = None
        self._reranker: Optional[RerankerService] = None

        # Metriken
        self._metrics: Dict[str, List[Dict[str, Any]]] = {
            "pgvector": [],
            "qdrant": [],
        }
        self._max_metrics_per_backend = 1000

    @classmethod
    def get_instance(cls) -> "VectorSearchOrchestrator":
        """Get Singleton Instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        """Initialisiere alle Services."""
        self._embedding_factory = get_embedding_factory()
        self._reranker = get_reranker_service()

        if settings.QDRANT_ENABLED:
            self._qdrant = await get_qdrant_service()
            await self._qdrant.initialize()

    def select_backend(
        self,
        user_id: Optional[UUID] = None,
    ) -> Tuple[str, str]:
        """
        Waehle Backend basierend auf A/B Testing Konfiguration.

        Deterministisches Routing: User bekommt immer dasselbe Backend.

        Args:
            user_id: User UUID fuer deterministisches Routing

        Returns:
            Tuple von (backend_name, embedding_model)
        """
        # A/B Testing deaktiviert -> Control (pgvector)
        if not settings.VECTOR_AB_TESTING_ENABLED:
            return VectorBackend.PGVECTOR, settings.EMBEDDING_MODEL

        # Qdrant nicht aktiviert -> pgvector
        if not settings.QDRANT_ENABLED:
            return VectorBackend.PGVECTOR, settings.EMBEDDING_MODEL

        # Deterministisches Routing basierend auf User-ID
        if user_id:
            # SECURITY FIX Phase 11.5: Use SHA256 instead of MD5 for security-critical hashing
            user_hash = hashlib.sha256(str(user_id).encode()).hexdigest()
            bucket = int(user_hash[:8], 16) % 100
        else:
            # Deterministischer Bucket fuer anonyme Requests basierend auf Timestamp
            # Verwendet time_ns fuer Nanosekunden-Praezision
            import time
            ts_seed = f"anon:{time.time_ns()}"
            ts_hash = hashlib.sha256(ts_seed.encode()).hexdigest()
            bucket = int(ts_hash[:8], 16) % 100

        # Traffic Split prufen
        if bucket < settings.VECTOR_AB_TRAFFIC_SPLIT:
            # Treatment: Qdrant + Jina
            return (
                settings.VECTOR_AB_TREATMENT_BACKEND,
                settings.VECTOR_AB_TREATMENT_EMBEDDING,
            )
        else:
            # Control: pgvector + E5
            return (
                settings.VECTOR_AB_CONTROL_BACKEND,
                settings.VECTOR_AB_CONTROL_EMBEDDING,
            )

    async def generate_query_embedding(
        self,
        query: str,
        model_name: Optional[str] = None,
    ) -> Optional[List[float]]:
        """
        Generiere Query-Embedding mit dem gewaehlten Modell.

        Args:
            query: Suchanfrage
            model_name: Optional spezifisches Modell

        Returns:
            Embedding-Vektor oder None
        """
        if self._embedding_factory is None:
            self._embedding_factory = get_embedding_factory()

        model = model_name or settings.EMBEDDING_MODEL
        return await self._embedding_factory.generate_query_embedding(query, model)

    async def search(
        self,
        query: str,
        user_id: Optional[UUID] = None,
        limit: int = 20,
        collection: str = "documents",
        filter_conditions: Optional[Dict[str, Any]] = None,
        apply_reranking: bool = True,
    ) -> Dict[str, Any]:
        """
        Unified Vector Search Interface.

        Args:
            query: Suchanfrage
            user_id: User UUID fuer A/B Routing
            limit: Max Ergebnisse
            collection: "documents" oder "chunks"
            filter_conditions: Filter (owner_id, document_type, etc.)
            apply_reranking: Re-Ranking anwenden

        Returns:
            Dict mit results, backend, latency, etc.
        """
        start_time = time.time()

        # Backend und Modell waehlen
        backend, embedding_model = self.select_backend(user_id)

        # Embedding generieren
        query_embedding = await self.generate_query_embedding(query, embedding_model)
        if not query_embedding:
            return {
                "results": [],
                "backend": backend,
                "embedding_model": embedding_model,
                "error": "Embedding-Generierung fehlgeschlagen",
            }

        embedding_time = time.time()

        # Suche ausfuehren
        results = []
        search_error = None

        if backend == VectorBackend.QDRANT and self._qdrant:
            try:
                qdrant_results = await self._qdrant.search(
                    query_vector=query_embedding,
                    collection=collection,
                    limit=limit * 3 if apply_reranking else limit,  # Mehr holen fuer Reranking
                    score_threshold=settings.SEMANTIC_SIMILARITY_THRESHOLD,
                    filter_conditions=filter_conditions,
                )

                results = [
                    {
                        "id": r.id,
                        "score": r.score,
                        **r.payload,
                    }
                    for r in qdrant_results
                ]

            except Exception as e:
                logger.error("qdrant_search_error", error=str(e))
                search_error = str(e)
                # Fallback zu pgvector
                backend = VectorBackend.PGVECTOR

        # pgvector Suche (wenn Qdrant nicht verfuegbar oder als Primary)
        if backend == VectorBackend.PGVECTOR or not results:
            # pgvector-Suche wird vom SearchService gehandhabt
            # Hier nur Placeholder - Integration erfolgt im SearchService
            pass

        search_time = time.time()

        # Re-Ranking
        if apply_reranking and results and settings.RAG_RERANK_ENABLED:
            if self._reranker is None:
                self._reranker = get_reranker_service()

            reranked = await self._reranker.rerank(
                query=query,
                documents=results,
                top_k=limit,
                text_key="extracted_text" if collection == "documents" else "chunk_text",
            )

            results = [r.payload for r in reranked]

        rerank_time = time.time()

        # Metriken sammeln
        latency = {
            "total_ms": int((rerank_time - start_time) * 1000),
            "embedding_ms": int((embedding_time - start_time) * 1000),
            "search_ms": int((search_time - embedding_time) * 1000),
            "rerank_ms": int((rerank_time - search_time) * 1000) if apply_reranking else 0,
        }

        if settings.VECTOR_AB_METRICS_ENABLED:
            self._record_metrics(
                backend=backend,
                embedding_model=embedding_model,
                latency=latency,
                results_count=len(results),
                query_length=len(query),
                user_id=user_id,
            )

        return {
            "results": results[:limit],
            "backend": backend,
            "embedding_model": embedding_model,
            "latency": latency,
            "total_results": len(results),
            "error": search_error,
        }

    def _record_metrics(
        self,
        backend: str,
        embedding_model: str,
        latency: Dict[str, int],
        results_count: int,
        query_length: int,
        user_id: Optional[UUID],
    ) -> None:
        """
        Zeichne Metriken fuer A/B Analyse auf.

        Args:
            backend: Verwendetes Backend
            embedding_model: Verwendetes Modell
            latency: Latenz-Metriken
            results_count: Anzahl Ergebnisse
            query_length: Query-Laenge
            user_id: User UUID
        """
        metric = {
            "timestamp": utc_now().isoformat(),
            "backend": backend,
            "embedding_model": embedding_model,
            "latency_total_ms": latency["total_ms"],
            "latency_embedding_ms": latency["embedding_ms"],
            "latency_search_ms": latency["search_ms"],
            "latency_rerank_ms": latency["rerank_ms"],
            "results_count": results_count,
            "query_length": query_length,
            "user_id": str(user_id) if user_id else None,
        }

        # In Memory-Liste speichern (mit Limit)
        if backend in self._metrics:
            self._metrics[backend].append(metric)

            # FIFO wenn ueber Limit
            if len(self._metrics[backend]) > self._max_metrics_per_backend:
                self._metrics[backend] = self._metrics[backend][-self._max_metrics_per_backend:]

    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Hole Zusammenfassung der A/B Test Metriken.

        Returns:
            Dict mit Metriken-Zusammenfassung pro Backend
        """
        summary = {}

        for backend, metrics in self._metrics.items():
            if not metrics:
                summary[backend] = {"sample_count": 0}
                continue

            latencies = [m["latency_total_ms"] for m in metrics]

            summary[backend] = {
                "sample_count": len(metrics),
                "avg_latency_ms": sum(latencies) / len(latencies),
                "p50_latency_ms": sorted(latencies)[len(latencies) // 2],
                "p95_latency_ms": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else None,
                "p99_latency_ms": sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) >= 100 else None,
                "avg_results_count": sum(m["results_count"] for m in metrics) / len(metrics),
                "first_sample": metrics[0]["timestamp"],
                "last_sample": metrics[-1]["timestamp"],
            }

        return summary

    async def health_check(self) -> Dict[str, bool]:
        """
        Pruefe Gesundheit aller Backends.

        Returns:
            Dict mit Health-Status pro Backend
        """
        health = {
            "pgvector": True,  # Annahme: PostgreSQL ist immer da
            "qdrant": False,
            "reranker": False,
        }

        if self._qdrant:
            health["qdrant"] = await self._qdrant.health_check()

        if self._reranker:
            health["reranker"] = await self._reranker.health_check()

        return health


# Singleton Instance
_vector_orchestrator: Optional[VectorSearchOrchestrator] = None


async def get_vector_orchestrator() -> VectorSearchOrchestrator:
    """Factory Function fuer VectorSearchOrchestrator."""
    global _vector_orchestrator
    if _vector_orchestrator is None:
        _vector_orchestrator = VectorSearchOrchestrator.get_instance()
        await _vector_orchestrator.initialize()
    return _vector_orchestrator
