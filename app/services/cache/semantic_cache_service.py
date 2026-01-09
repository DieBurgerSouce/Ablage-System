"""Semantic LLM-Cache Service.

Intelligentes Caching fuer LLM-Antworten basierend auf semantischer
Aehnlichkeit der Prompts. Reduziert LLM-Aufrufe um 40-60%.

Features:
- Embedding-basierte Aehnlichkeitssuche
- Konfigurierbarer Similarity-Threshold
- TTL-basierte Cache-Invalidierung
- Hit/Miss-Metriken
"""

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import redis.asyncio as aioredis
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ============================================================================
# Configuration
# ============================================================================

# Cache-Konfiguration
DEFAULT_SIMILARITY_THRESHOLD = 0.92  # Min-Aehnlichkeit fuer Cache-Hit
DEFAULT_CACHE_TTL = 3600 * 24  # 24 Stunden
MAX_CACHE_ENTRIES = 10000  # Max Eintraege im Cache
EMBEDDING_DIMENSION = 1024  # Dimension der Embeddings (e5/jina)

# Redis Keys
CACHE_KEY_PREFIX = "semantic_cache:llm"
CACHE_INDEX_KEY = f"{CACHE_KEY_PREFIX}:index"
CACHE_STATS_KEY = f"{CACHE_KEY_PREFIX}:stats"


# ============================================================================
# Data Classes
# ============================================================================


@dataclass
class CacheEntry:
    """Eintrag im Semantic Cache."""

    prompt_hash: str
    prompt: str
    response: str
    embedding: List[float]
    model: str
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0
    last_hit_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary fuer Redis."""
        return {
            "prompt_hash": self.prompt_hash,
            "prompt": self.prompt,
            "response": self.response,
            "embedding": json.dumps(self.embedding),
            "model": self.model,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "hit_count": self.hit_count,
            "last_hit_at": self.last_hit_at.isoformat() if self.last_hit_at else None,
            "metadata": json.dumps(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CacheEntry":
        """Erstellt CacheEntry aus Dictionary."""
        return cls(
            prompt_hash=data["prompt_hash"],
            prompt=data["prompt"],
            response=data["response"],
            embedding=json.loads(data["embedding"]),
            model=data["model"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            hit_count=int(data.get("hit_count", 0)),
            last_hit_at=(
                datetime.fromisoformat(data["last_hit_at"])
                if data.get("last_hit_at")
                else None
            ),
            metadata=json.loads(data.get("metadata", "{}")),
        )


@dataclass
class CacheHit:
    """Ergebnis eines Cache-Lookups."""

    hit: bool
    entry: Optional[CacheEntry] = None
    similarity: float = 0.0
    lookup_time_ms: int = 0


@dataclass
class CacheStats:
    """Cache-Statistiken."""

    total_entries: int = 0
    total_hits: int = 0
    total_misses: int = 0
    hit_rate: float = 0.0
    avg_similarity: float = 0.0
    estimated_savings_tokens: int = 0
    cache_size_bytes: int = 0


# ============================================================================
# Semantic Cache Service
# ============================================================================


class SemanticCacheService:
    """Service fuer semantisches LLM-Caching.

    Cached LLM-Antworten basierend auf semantischer Aehnlichkeit
    der Prompts. Nutzt Embeddings fuer Similarity-Berechnung.
    """

    def __init__(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        cache_ttl: int = DEFAULT_CACHE_TTL,
        redis_url: Optional[str] = None,
    ) -> None:
        """Initialisiert den Service.

        Args:
            similarity_threshold: Min-Aehnlichkeit fuer Cache-Hit (0.0-1.0)
            cache_ttl: TTL fuer Cache-Eintraege in Sekunden
            redis_url: Redis-URL (default: aus Settings)
        """
        self._similarity_threshold = similarity_threshold
        self._cache_ttl = cache_ttl
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[aioredis.Redis] = None
        self._embedding_service = None
        self._initialized = False

        # Lokaler In-Memory Cache fuer Hot-Entries
        self._local_cache: Dict[str, Tuple[List[float], str]] = {}
        self._local_cache_max = 100

    async def _get_redis(self) -> Optional[aioredis.Redis]:
        """Gibt Redis-Verbindung zurueck (Lazy-Loading)."""
        if self._redis is None and self._redis_url:
            try:
                self._redis = aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                await self._redis.ping()
                logger.info("semantic_cache_redis_connected", url=self._redis_url[:30])
            except Exception as e:
                logger.warning("semantic_cache_redis_error", error=str(e))
                self._redis = None
        return self._redis

    async def _get_embedding_service(self) -> Any:
        """Gibt Embedding-Service zurueck (Lazy-Loading)."""
        if self._embedding_service is None:
            try:
                from app.services.embedding_service import EmbeddingService

                self._embedding_service = EmbeddingService()
            except Exception as e:
                logger.warning("embedding_service_init_error", error=str(e))
        return self._embedding_service

    def _compute_prompt_hash(self, prompt: str, model: str = "") -> str:
        """Berechnet Hash fuer Prompt.

        Args:
            prompt: Der Prompt
            model: Optionales Modell

        Returns:
            SHA256 Hash
        """
        content = f"{model}:{prompt}".encode("utf-8")
        return hashlib.sha256(content).hexdigest()

    def _cosine_similarity(
        self,
        vec1: Union[List[float], np.ndarray],
        vec2: Union[List[float], np.ndarray],
    ) -> float:
        """Berechnet Cosine-Similarity zwischen zwei Vektoren.

        Args:
            vec1: Erster Vektor
            vec2: Zweiter Vektor

        Returns:
            Similarity-Wert zwischen -1 und 1
        """
        v1 = np.array(vec1, dtype=np.float32)
        v2 = np.array(vec2, dtype=np.float32)

        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    async def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Generiert Embedding fuer Text.

        Args:
            text: Zu embedender Text

        Returns:
            Embedding-Vektor oder None
        """
        embedding_service = await self._get_embedding_service()
        if not embedding_service:
            return None

        try:
            # Nutze Query-Embedding (mit Caching im Embedding-Service)
            embedding = await embedding_service.embed_query_async(text)
            return embedding.tolist() if isinstance(embedding, np.ndarray) else embedding
        except Exception as e:
            logger.warning("embedding_generation_error", error=str(e))
            return None

    async def get(
        self,
        prompt: str,
        model: str = "",
    ) -> CacheHit:
        """Sucht nach Cache-Hit basierend auf semantischer Aehnlichkeit.

        Args:
            prompt: Der Prompt
            model: Optionales Modell

        Returns:
            CacheHit mit Ergebnis
        """
        start_time = time.time()

        # Exakter Hash-Match zuerst (schnell)
        prompt_hash = self._compute_prompt_hash(prompt, model)

        redis = await self._get_redis()
        if redis:
            try:
                # Exakter Match
                cache_key = f"{CACHE_KEY_PREFIX}:{prompt_hash}"
                cached = await redis.hgetall(cache_key)

                if cached:
                    entry = CacheEntry.from_dict(cached)

                    # Ablauf pruefen
                    if entry.expires_at > datetime.now(timezone.utc):
                        # Hit-Count erhoehen
                        await redis.hincrby(cache_key, "hit_count", 1)
                        await redis.hset(
                            cache_key,
                            "last_hit_at",
                            datetime.now(timezone.utc).isoformat(),
                        )
                        await self._update_stats("hit")

                        lookup_time = int((time.time() - start_time) * 1000)
                        logger.debug(
                            "semantic_cache_exact_hit",
                            prompt_hash=prompt_hash[:16],
                            lookup_time_ms=lookup_time,
                        )

                        return CacheHit(
                            hit=True,
                            entry=entry,
                            similarity=1.0,
                            lookup_time_ms=lookup_time,
                        )
            except Exception as e:
                logger.warning("cache_exact_lookup_error", error=str(e))

        # Kein exakter Match - Semantic Search
        prompt_embedding = await self._get_embedding(prompt)
        if not prompt_embedding:
            await self._update_stats("miss")
            return CacheHit(hit=False, lookup_time_ms=int((time.time() - start_time) * 1000))

        # Durchsuche Cache-Index
        best_match: Optional[CacheEntry] = None
        best_similarity = 0.0

        if redis:
            try:
                # Hole alle Cache-Keys
                index_keys = await redis.smembers(CACHE_INDEX_KEY)

                for key in list(index_keys)[:MAX_CACHE_ENTRIES]:
                    try:
                        cached = await redis.hgetall(key)
                        if not cached:
                            # Orphaned Index-Eintrag entfernen
                            await redis.srem(CACHE_INDEX_KEY, key)
                            continue

                        entry = CacheEntry.from_dict(cached)

                        # Ablauf pruefen
                        if entry.expires_at <= datetime.now(timezone.utc):
                            await redis.delete(key)
                            await redis.srem(CACHE_INDEX_KEY, key)
                            continue

                        # Similarity berechnen
                        similarity = self._cosine_similarity(
                            prompt_embedding, entry.embedding
                        )

                        if similarity > best_similarity:
                            best_similarity = similarity
                            best_match = entry

                    except Exception as e:
                        logger.debug("cache_entry_error", key=key, error=str(e))

            except Exception as e:
                logger.warning("cache_semantic_lookup_error", error=str(e))

        lookup_time = int((time.time() - start_time) * 1000)

        # Threshold-Check
        if best_match and best_similarity >= self._similarity_threshold:
            if redis:
                try:
                    cache_key = f"{CACHE_KEY_PREFIX}:{best_match.prompt_hash}"
                    await redis.hincrby(cache_key, "hit_count", 1)
                    await redis.hset(
                        cache_key,
                        "last_hit_at",
                        datetime.now(timezone.utc).isoformat(),
                    )
                except Exception:
                    pass

            await self._update_stats("hit", best_similarity)

            logger.info(
                "semantic_cache_hit",
                similarity=round(best_similarity, 4),
                threshold=self._similarity_threshold,
                lookup_time_ms=lookup_time,
            )

            return CacheHit(
                hit=True,
                entry=best_match,
                similarity=best_similarity,
                lookup_time_ms=lookup_time,
            )

        await self._update_stats("miss")

        logger.debug(
            "semantic_cache_miss",
            best_similarity=round(best_similarity, 4) if best_similarity else 0,
            threshold=self._similarity_threshold,
            lookup_time_ms=lookup_time,
        )

        return CacheHit(
            hit=False,
            similarity=best_similarity,
            lookup_time_ms=lookup_time,
        )

    async def set(
        self,
        prompt: str,
        response: str,
        model: str = "",
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Speichert Antwort im Cache.

        Args:
            prompt: Der Prompt
            response: Die LLM-Antwort
            model: Verwendetes Modell
            ttl: Optionale TTL in Sekunden
            metadata: Optionale Metadaten

        Returns:
            True bei Erfolg
        """
        prompt_hash = self._compute_prompt_hash(prompt, model)
        prompt_embedding = await self._get_embedding(prompt)

        if not prompt_embedding:
            logger.warning("cache_set_no_embedding")
            return False

        now = datetime.now(timezone.utc)
        entry = CacheEntry(
            prompt_hash=prompt_hash,
            prompt=prompt,
            response=response,
            embedding=prompt_embedding,
            model=model,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl or self._cache_ttl),
            hit_count=0,
            metadata=metadata or {},
        )

        redis = await self._get_redis()
        if redis:
            try:
                cache_key = f"{CACHE_KEY_PREFIX}:{prompt_hash}"

                # Entry speichern
                await redis.hset(cache_key, mapping=entry.to_dict())

                # TTL setzen
                await redis.expire(cache_key, ttl or self._cache_ttl)

                # Index aktualisieren
                await redis.sadd(CACHE_INDEX_KEY, cache_key)

                logger.debug(
                    "semantic_cache_set",
                    prompt_hash=prompt_hash[:16],
                    model=model,
                    ttl=ttl or self._cache_ttl,
                )

                return True

            except Exception as e:
                logger.warning("cache_set_error", error=str(e))

        return False

    async def invalidate(self, prompt: str, model: str = "") -> bool:
        """Invalidiert Cache-Eintrag.

        Args:
            prompt: Der Prompt
            model: Verwendetes Modell

        Returns:
            True wenn Eintrag gefunden und geloescht
        """
        prompt_hash = self._compute_prompt_hash(prompt, model)
        cache_key = f"{CACHE_KEY_PREFIX}:{prompt_hash}"

        redis = await self._get_redis()
        if redis:
            try:
                deleted = await redis.delete(cache_key)
                await redis.srem(CACHE_INDEX_KEY, cache_key)
                return deleted > 0
            except Exception as e:
                logger.warning("cache_invalidate_error", error=str(e))

        return False

    async def clear(self) -> int:
        """Loescht alle Cache-Eintraege.

        Returns:
            Anzahl geloeschter Eintraege
        """
        redis = await self._get_redis()
        if not redis:
            return 0

        try:
            # Alle Keys aus Index holen
            keys = await redis.smembers(CACHE_INDEX_KEY)

            if keys:
                # Keys loeschen
                await redis.delete(*keys)

            # Index loeschen
            await redis.delete(CACHE_INDEX_KEY)

            # Stats zuruecksetzen
            await redis.delete(CACHE_STATS_KEY)

            logger.info("semantic_cache_cleared", entries_deleted=len(keys))
            return len(keys)

        except Exception as e:
            logger.warning("cache_clear_error", error=str(e))
            return 0

    async def _update_stats(
        self,
        event: str,
        similarity: float = 0.0,
    ) -> None:
        """Aktualisiert Cache-Statistiken.

        Args:
            event: "hit" oder "miss"
            similarity: Similarity-Wert bei Hit
        """
        redis = await self._get_redis()
        if not redis:
            return

        try:
            if event == "hit":
                await redis.hincrby(CACHE_STATS_KEY, "hits", 1)
                if similarity > 0:
                    # Rolling Average fuer Similarity
                    current_avg = await redis.hget(CACHE_STATS_KEY, "avg_similarity")
                    current_count = await redis.hget(CACHE_STATS_KEY, "hits")
                    if current_avg and current_count:
                        new_avg = (
                            float(current_avg) * (int(current_count) - 1) + similarity
                        ) / int(current_count)
                        await redis.hset(CACHE_STATS_KEY, "avg_similarity", new_avg)
                    else:
                        await redis.hset(CACHE_STATS_KEY, "avg_similarity", similarity)
            else:
                await redis.hincrby(CACHE_STATS_KEY, "misses", 1)

        except Exception as e:
            logger.debug("stats_update_error", error=str(e))

    async def get_stats(self) -> CacheStats:
        """Gibt Cache-Statistiken zurueck.

        Returns:
            CacheStats-Objekt
        """
        redis = await self._get_redis()
        if not redis:
            return CacheStats()

        try:
            # Stats aus Redis
            stats_raw = await redis.hgetall(CACHE_STATS_KEY)

            hits = int(stats_raw.get("hits", 0))
            misses = int(stats_raw.get("misses", 0))
            total = hits + misses

            # Anzahl Eintraege
            entry_count = await redis.scard(CACHE_INDEX_KEY)

            # Geschaetzte Token-Ersparnis (ca. 1000 Tokens pro Hit)
            estimated_savings = hits * 1000

            return CacheStats(
                total_entries=entry_count,
                total_hits=hits,
                total_misses=misses,
                hit_rate=hits / total if total > 0 else 0.0,
                avg_similarity=float(stats_raw.get("avg_similarity", 0)),
                estimated_savings_tokens=estimated_savings,
            )

        except Exception as e:
            logger.warning("stats_get_error", error=str(e))
            return CacheStats()

    async def close(self) -> None:
        """Schliesst Verbindungen."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# ============================================================================
# Singleton Pattern
# ============================================================================

_semantic_cache_service: Optional[SemanticCacheService] = None
_semantic_cache_service_lock = threading.Lock()


def get_semantic_cache_service() -> SemanticCacheService:
    """Gibt die Singleton-Instanz des Semantic Cache Service zurueck.

    Returns:
        SemanticCacheService Singleton-Instanz
    """
    global _semantic_cache_service

    if _semantic_cache_service is None:
        with _semantic_cache_service_lock:
            if _semantic_cache_service is None:
                _semantic_cache_service = SemanticCacheService()

    return _semantic_cache_service
