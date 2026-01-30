"""
Reranker Service.

BGE-Reranker Cross-Encoder fuer Top-K Re-Ranking.
Verbessert Suchrelevanz signifikant durch paarweises Scoring.

Features:
- HuggingFace TEI Integration
- Fallback bei Fehler
- Timeout Handling
- Batch Re-Ranking

Feinpoliert und durchdacht.
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
import asyncio

import httpx
import structlog

from app.core.config import settings
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


@dataclass
class RerankedResult:
    """Ergebnis nach Re-Ranking."""
    id: str
    original_score: float
    rerank_score: float
    payload: Dict[str, Any]


class RerankerService:
    """
    BGE-Reranker Service via HuggingFace TEI.

    Nutzt BAAI/bge-reranker-v2-m3 fuer Cross-Encoder Re-Ranking.
    CPU-only (GPU reserviert fuer OCR).
    """

    _instance: Optional["RerankerService"] = None

    def __init__(self):
        """Initialisiere RerankerService."""
        self._client: Optional[httpx.AsyncClient] = None
        self._is_available: Optional[bool] = None

    @classmethod
    def get_instance(cls) -> "RerankerService":
        """Get Singleton Instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_enabled(self) -> bool:
        """Prueft ob Reranker aktiviert ist."""
        return settings.RAG_RERANK_ENABLED and bool(settings.RERANKER_SERVICE_URL)

    async def _get_client(self) -> httpx.AsyncClient:
        """Hole oder erstelle HTTP Client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.RERANKER_TIMEOUT),
                limits=httpx.Limits(max_connections=10),
            )
        return self._client

    async def health_check(self) -> bool:
        """
        Pruefe Reranker-Service Verfuegbarkeit.

        Returns:
            True wenn Service erreichbar
        """
        if not self.is_enabled:
            return True  # Nicht aktiviert = kein Problem

        try:
            client = await self._get_client()
            response = await client.get(
                f"{settings.RERANKER_SERVICE_URL}/health",
                timeout=5.0,
            )
            self._is_available = response.status_code == 200
            return self._is_available

        except Exception as e:
            logger.warning(
                "reranker_health_check_failed",
                url=settings.RERANKER_SERVICE_URL,
                **safe_error_log(e)
            )
            self._is_available = False
            return False

    async def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        text_key: str = "text",
        id_key: str = "id",
        score_key: str = "score",
    ) -> List[RerankedResult]:
        """
        Re-Ranke Dokumente basierend auf Query.

        Args:
            query: Suchanfrage
            documents: Liste von Dokumenten mit Text und Score
            top_k: Maximale Anzahl Ergebnisse (default: settings.RAG_RERANK_TOP_K)
            text_key: Schluessel fuer Dokument-Text
            id_key: Schluessel fuer Dokument-ID
            score_key: Schluessel fuer Original-Score

        Returns:
            Liste von RerankedResult sortiert nach rerank_score
        """
        if not self.is_enabled:
            # Reranker deaktiviert - gib Original zurueck
            return [
                RerankedResult(
                    id=str(doc.get(id_key, i)),
                    original_score=doc.get(score_key, 0.0),
                    rerank_score=doc.get(score_key, 0.0),
                    payload=doc,
                )
                for i, doc in enumerate(documents)
            ]

        if not documents:
            return []

        top_k = top_k or settings.RAG_RERANK_TOP_K

        try:
            client = await self._get_client()

            # HuggingFace TEI Rerank API Format
            # POST /rerank mit {"query": "...", "texts": ["...", "..."]}
            texts = [doc.get(text_key, "") for doc in documents]

            response = await client.post(
                f"{settings.RERANKER_SERVICE_URL}/rerank",
                json={
                    "query": query,
                    "texts": texts,
                    "return_text": False,  # Nur Scores
                },
            )

            if response.status_code != 200:
                logger.warning(
                    "reranker_request_failed",
                    status=response.status_code,
                    body=response.text[:200]
                )
                return self._fallback_results(documents, id_key, score_key, top_k)

            # Response Format: [{"index": 0, "score": 0.95}, ...]
            rerank_results = response.json()

            # Ergebnisse zusammenfuegen
            results = []
            for item in rerank_results:
                idx = item.get("index", 0)
                rerank_score = item.get("score", 0.0)

                if idx < len(documents):
                    doc = documents[idx]
                    results.append(RerankedResult(
                        id=str(doc.get(id_key, idx)),
                        original_score=doc.get(score_key, 0.0),
                        rerank_score=float(rerank_score),
                        payload=doc,
                    ))

            # Sortieren nach rerank_score (absteigend)
            results.sort(key=lambda x: x.rerank_score, reverse=True)

            logger.debug(
                "reranker_success",
                query_length=len(query),
                documents_count=len(documents),
                results_count=len(results[:top_k])
            )

            return results[:top_k]

        except httpx.TimeoutException:
            logger.warning(
                "reranker_timeout",
                timeout=settings.RERANKER_TIMEOUT,
                documents_count=len(documents)
            )
            return self._fallback_results(documents, id_key, score_key, top_k)

        except Exception as e:
            logger.error(
                "reranker_error",
                **safe_error_log(e),
                documents_count=len(documents)
            )
            return self._fallback_results(documents, id_key, score_key, top_k)

    def _fallback_results(
        self,
        documents: List[Dict[str, Any]],
        id_key: str,
        score_key: str,
        top_k: int,
    ) -> List[RerankedResult]:
        """
        Fallback: Original-Ranking zurueckgeben.

        Args:
            documents: Originale Dokumente
            id_key: ID-Schluessel
            score_key: Score-Schluessel
            top_k: Max Ergebnisse

        Returns:
            Original-Reihenfolge als RerankedResult
        """
        if not settings.RERANKER_FALLBACK_ON_ERROR:
            return []

        logger.debug("reranker_fallback", documents_count=len(documents))

        results = [
            RerankedResult(
                id=str(doc.get(id_key, i)),
                original_score=doc.get(score_key, 0.0),
                rerank_score=doc.get(score_key, 0.0),  # Original Score verwenden
                payload=doc,
            )
            for i, doc in enumerate(documents)
        ]

        # Nach Original-Score sortieren
        results.sort(key=lambda x: x.original_score, reverse=True)

        return results[:top_k]

    async def rerank_search_results(
        self,
        query: str,
        results: List[Any],
        top_k: Optional[int] = None,
    ) -> List[Any]:
        """
        Re-Ranke Suchergebnisse (Generic Wrapper).

        Erwartet Objekte mit:
        - id: UUID oder String
        - score: Float
        - text oder extracted_text: String

        Args:
            query: Suchanfrage
            results: Suchergebnisse
            top_k: Max Ergebnisse

        Returns:
            Re-Ranked Ergebnisse in Original-Typ
        """
        if not results:
            return []

        # Konvertiere zu Dict-Format
        documents = []
        for r in results:
            doc = {
                "id": str(getattr(r, "id", r.get("id", "")) if hasattr(r, "id") else r.get("id", "")),
                "score": float(getattr(r, "score", r.get("score", 0.0)) if hasattr(r, "score") else r.get("score", 0.0)),
                "original": r,
            }

            # Text extrahieren
            if hasattr(r, "extracted_text"):
                doc["text"] = r.extracted_text or ""
            elif hasattr(r, "text"):
                doc["text"] = r.text or ""
            elif hasattr(r, "chunk_text"):
                doc["text"] = r.chunk_text or ""
            elif isinstance(r, dict):
                doc["text"] = r.get("extracted_text") or r.get("text") or r.get("chunk_text") or ""
            else:
                doc["text"] = ""

            documents.append(doc)

        # Re-Rank
        reranked = await self.rerank(
            query=query,
            documents=documents,
            top_k=top_k,
        )

        # Original-Objekte in neuer Reihenfolge zurueckgeben
        return [r.payload["original"] for r in reranked]

    async def close(self) -> None:
        """Schliesse HTTP Client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton Instance
_reranker_service: Optional[RerankerService] = None


def get_reranker_service() -> RerankerService:
    """Factory Function fuer RerankerService."""
    global _reranker_service
    if _reranker_service is None:
        _reranker_service = RerankerService.get_instance()
    return _reranker_service
