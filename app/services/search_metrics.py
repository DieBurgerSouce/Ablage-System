# -*- coding: utf-8 -*-
"""
Prometheus Metriken für Such-Service.

Erfasst:
- Suchanfragen nach Typ (FTS, Semantic, Hybrid)
- Suchlatenz und Ergebnismengen
- Cache-Hit/Miss-Raten
- Embedding-Generierung
- Zero-Result-Queries

Feinpoliert und durchdacht - Observability für Suche in Produktion.
"""

import threading
import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Optional

import structlog

logger = structlog.get_logger(__name__)

# Thread-Safety für Singleton
_search_metrics_lock = threading.Lock()

# Optional Prometheus integration
PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        Counter,
        Histogram,
        Gauge,
        CollectorRegistry,
        generate_latest,
        CONTENT_TYPE_LATEST,
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.info("prometheus_client nicht installiert - Such-Metriken deaktiviert")


# =============================================================================
# Metric Definitions
# =============================================================================

if PROMETHEUS_AVAILABLE:
    # Registry für alle Such-Metriken
    SEARCH_REGISTRY = CollectorRegistry()

    # -------------------------------------------------------------------------
    # Such-Anfragen Metriken
    # -------------------------------------------------------------------------

    SEARCH_REQUESTS_TOTAL = Counter(
        "search_requests_total",
        "Gesamtzahl der Suchanfragen",
        ["search_type", "status", "cached"],
        registry=SEARCH_REGISTRY,
    )

    SEARCH_DURATION_SECONDS = Histogram(
        "search_duration_seconds",
        "Dauer der Suchanfrage in Sekunden",
        ["search_type"],
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=SEARCH_REGISTRY,
    )

    SEARCH_RESULTS_COUNT = Histogram(
        "search_results_count",
        "Anzahl der Suchergebnisse",
        ["search_type"],
        buckets=[0, 1, 5, 10, 20, 50, 100, 200, 500, 1000],
        registry=SEARCH_REGISTRY,
    )

    ZERO_RESULT_SEARCHES_TOTAL = Counter(
        "search_zero_results_total",
        "Suchanfragen ohne Ergebnisse",
        ["search_type"],
        registry=SEARCH_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Cache Metriken
    # -------------------------------------------------------------------------

    SEARCH_CACHE_OPERATIONS = Counter(
        "search_cache_operations_total",
        "Cache-Operationen",
        ["operation", "result"],  # operation: lookup, store; result: hit, miss, error
        registry=SEARCH_REGISTRY,
    )

    SEARCH_CACHE_SIZE = Gauge(
        "search_cache_entries",
        "Geschätzte Anzahl der Cache-Einträge",
        registry=SEARCH_REGISTRY,
    )

    SEARCH_CACHE_INVALIDATIONS = Counter(
        "search_cache_invalidations_total",
        "Cache-Invalidierungen",
        ["reason"],  # reason: document_update, document_delete, batch_delete, batch_tag, admin
        registry=SEARCH_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Embedding Metriken
    # -------------------------------------------------------------------------

    EMBEDDING_GENERATION_SECONDS = Histogram(
        "search_embedding_generation_seconds",
        "Zeit für Embedding-Generierung",
        ["source"],  # source: query, document
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
        registry=SEARCH_REGISTRY,
    )

    EMBEDDING_CACHE_HITS = Counter(
        "search_embedding_cache_hits_total",
        "Embedding-Cache-Treffer",
        registry=SEARCH_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Ähnliche Dokumente Metriken
    # -------------------------------------------------------------------------

    SIMILAR_DOCUMENT_REQUESTS_TOTAL = Counter(
        "search_similar_requests_total",
        "Anfragen für ähnliche Dokumente",
        ["status", "cached"],
        registry=SEARCH_REGISTRY,
    )

    SIMILAR_DOCUMENT_COUNT = Histogram(
        "search_similar_count",
        "Anzahl gefundener ähnlicher Dokumente",
        buckets=[0, 1, 2, 5, 10, 20, 50],
        registry=SEARCH_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Filter Metriken
    # -------------------------------------------------------------------------

    SEARCH_FILTER_USAGE = Counter(
        "search_filter_usage_total",
        "Verwendung von Such-Filtern",
        ["filter_type"],  # document_type, date, status, tags, confidence, language, embedding
        registry=SEARCH_REGISTRY,
    )

    # -------------------------------------------------------------------------
    # Analytics Metriken
    # -------------------------------------------------------------------------

    SEARCH_ANALYTICS_LOGGED = Counter(
        "search_analytics_logged_total",
        "Geloggte Such-Analytics Einträge",
        registry=SEARCH_REGISTRY,
    )

    SEARCH_CLICK_LOGGED = Counter(
        "search_click_logged_total",
        "Geloggte Klicks auf Suchergebnisse",
        ["is_download"],
        registry=SEARCH_REGISTRY,
    )


# =============================================================================
# SearchMetrics Class
# =============================================================================

class SearchMetrics:
    """
    Zentrale Klasse für Such-Metriken.

    Kapselt alle Prometheus-Operationen und bietet
    Fallback wenn Prometheus nicht verfügbar.
    """

    def __init__(self) -> None:
        """Initialisiere SearchMetrics."""
        self.enabled = PROMETHEUS_AVAILABLE

        if self.enabled:
            logger.info("Prometheus Such-Metriken aktiviert")
        else:
            logger.info("Prometheus nicht verfügbar - Metriken nur als Logs")

    # -------------------------------------------------------------------------
    # Such-Anfragen
    # -------------------------------------------------------------------------

    def record_search(
        self,
        search_type: str,
        duration_seconds: float,
        results_count: int,
        cached: bool = False,
        success: bool = True,
    ) -> None:
        """
        Erfasse Suchanfrage.

        Args:
            search_type: fts, semantic, hybrid
            duration_seconds: Dauer in Sekunden
            results_count: Anzahl der Ergebnisse
            cached: War es ein Cache-Hit?
            success: War die Suche erfolgreich?
        """
        status = "success" if success else "error"
        cached_str = "true" if cached else "false"

        if self.enabled:
            SEARCH_REQUESTS_TOTAL.labels(
                search_type=search_type,
                status=status,
                cached=cached_str,
            ).inc()

            SEARCH_DURATION_SECONDS.labels(search_type=search_type).observe(duration_seconds)
            SEARCH_RESULTS_COUNT.labels(search_type=search_type).observe(results_count)

            if results_count == 0 and success:
                ZERO_RESULT_SEARCHES_TOTAL.labels(search_type=search_type).inc()
        else:
            logger.debug(
                "search_request",
                search_type=search_type,
                duration_ms=int(duration_seconds * 1000),
                results=results_count,
                cached=cached,
            )

    @contextmanager
    def measure_search(self, search_type: str):
        """Context Manager zur Zeitmessung von Suchen."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            if self.enabled:
                SEARCH_DURATION_SECONDS.labels(search_type=search_type).observe(duration)

    # -------------------------------------------------------------------------
    # Cache
    # -------------------------------------------------------------------------

    def record_cache_hit(self) -> None:
        """Erfasse Cache-Treffer."""
        if self.enabled:
            SEARCH_CACHE_OPERATIONS.labels(operation="lookup", result="hit").inc()

    def record_cache_miss(self) -> None:
        """Erfasse Cache-Miss."""
        if self.enabled:
            SEARCH_CACHE_OPERATIONS.labels(operation="lookup", result="miss").inc()

    def record_cache_store(self, success: bool = True) -> None:
        """Erfasse Cache-Speicherung."""
        if self.enabled:
            result = "success" if success else "error"
            SEARCH_CACHE_OPERATIONS.labels(operation="store", result=result).inc()

    def record_cache_invalidation(self, reason: str, count: int = 1) -> None:
        """
        Erfasse Cache-Invalidierung.

        Args:
            reason: Grund (document_update, document_delete, batch_delete, batch_tag, admin)
            count: Anzahl der invalidierten Einträge
        """
        if self.enabled:
            SEARCH_CACHE_INVALIDATIONS.labels(reason=reason).inc(count)
        else:
            logger.debug("cache_invalidation", reason=reason, count=count)

    def set_cache_size(self, size: int) -> None:
        """Setze geschätzte Cache-Größe."""
        if self.enabled:
            SEARCH_CACHE_SIZE.set(size)

    # -------------------------------------------------------------------------
    # Embeddings
    # -------------------------------------------------------------------------

    def record_embedding_generation(
        self,
        duration_seconds: float,
        source: str = "query",
    ) -> None:
        """
        Erfasse Embedding-Generierung.

        Args:
            duration_seconds: Dauer in Sekunden
            source: query oder document
        """
        if self.enabled:
            EMBEDDING_GENERATION_SECONDS.labels(source=source).observe(duration_seconds)
        else:
            logger.debug(
                "embedding_generated",
                source=source,
                duration_ms=int(duration_seconds * 1000),
            )

    @contextmanager
    def measure_embedding(self, source: str = "query"):
        """Context Manager zur Zeitmessung von Embedding-Generierung."""
        start = time.time()
        try:
            yield
        finally:
            duration = time.time() - start
            if self.enabled:
                EMBEDDING_GENERATION_SECONDS.labels(source=source).observe(duration)

    def record_embedding_cache_hit(self) -> None:
        """Erfasse Embedding-Cache-Treffer."""
        if self.enabled:
            EMBEDDING_CACHE_HITS.inc()

    # -------------------------------------------------------------------------
    # Ähnliche Dokumente
    # -------------------------------------------------------------------------

    def record_similar_documents(
        self,
        count: int,
        duration_seconds: float,
        cached: bool = False,
        success: bool = True,
    ) -> None:
        """
        Erfasse Anfrage für ähnliche Dokumente.

        Args:
            count: Anzahl gefundener ähnlicher Dokumente
            duration_seconds: Dauer in Sekunden
            cached: War es ein Cache-Hit?
            success: War die Anfrage erfolgreich?
        """
        status = "success" if success else "error"
        cached_str = "true" if cached else "false"

        if self.enabled:
            SIMILAR_DOCUMENT_REQUESTS_TOTAL.labels(
                status=status,
                cached=cached_str,
            ).inc()
            SIMILAR_DOCUMENT_COUNT.observe(count)
        else:
            logger.debug(
                "similar_documents_request",
                count=count,
                duration_ms=int(duration_seconds * 1000),
                cached=cached,
            )

    # -------------------------------------------------------------------------
    # Filter
    # -------------------------------------------------------------------------

    def record_filter_usage(self, filter_type: str) -> None:
        """
        Erfasse Verwendung eines Such-Filters.

        Args:
            filter_type: document_type, date, status, tags, confidence, language, embedding
        """
        if self.enabled:
            SEARCH_FILTER_USAGE.labels(filter_type=filter_type).inc()

    def record_filters_from_request(
        self,
        document_type: bool = False,
        date: bool = False,
        status: bool = False,
        tags: bool = False,
        confidence: bool = False,
        language: bool = False,
        embedding: bool = False,
    ) -> None:
        """Erfasse alle verwendeten Filter aus einer Anfrage."""
        if document_type:
            self.record_filter_usage("document_type")
        if date:
            self.record_filter_usage("date")
        if status:
            self.record_filter_usage("status")
        if tags:
            self.record_filter_usage("tags")
        if confidence:
            self.record_filter_usage("confidence")
        if language:
            self.record_filter_usage("language")
        if embedding:
            self.record_filter_usage("embedding")

    # -------------------------------------------------------------------------
    # Analytics
    # -------------------------------------------------------------------------

    def record_analytics_logged(self) -> None:
        """Erfasse geloggte Analytics."""
        if self.enabled:
            SEARCH_ANALYTICS_LOGGED.inc()

    def record_click_logged(self, is_download: bool = False) -> None:
        """Erfasse geloggten Klick."""
        if self.enabled:
            SEARCH_CLICK_LOGGED.labels(is_download=str(is_download).lower()).inc()

    # -------------------------------------------------------------------------
    # Export
    # -------------------------------------------------------------------------

    def get_metrics(self) -> bytes:
        """Hole alle Such-Metriken als Prometheus-Format."""
        if self.enabled:
            return generate_latest(SEARCH_REGISTRY)
        else:
            return b"# Prometheus not available\n"

    def get_content_type(self) -> str:
        """Hole Content-Type für Metriken."""
        if self.enabled:
            return CONTENT_TYPE_LATEST
        else:
            return "text/plain"


# =============================================================================
# Singleton Instance
# =============================================================================

_search_metrics: Optional[SearchMetrics] = None


def get_search_metrics() -> SearchMetrics:
    """Hole globale SearchMetrics Instanz (thread-safe)."""
    global _search_metrics
    if _search_metrics is not None:
        return _search_metrics
    with _search_metrics_lock:
        if _search_metrics is None:
            logger.info("search_metrics_initialisierung")
            _search_metrics = SearchMetrics()
    return _search_metrics


# =============================================================================
# Decorators
# =============================================================================

def track_search(search_type: str = "unknown"):
    """Decorator zum Tracking von Such-Funktionen."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            metrics = get_search_metrics()
            start = time.time()
            cached = False
            results_count = 0
            success = True

            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start

                # Extract info from result
                if hasattr(result, 'total'):
                    results_count = result.total
                elif isinstance(result, list):
                    results_count = len(result)

                # Check if cached (look for cache_hit in result or kwargs)
                cached = kwargs.get('skip_cache', False) is False and results_count > 0

                return result
            except Exception:
                success = False
                raise
            finally:
                duration = time.time() - start
                metrics.record_search(
                    search_type=search_type,
                    duration_seconds=duration,
                    results_count=results_count,
                    cached=cached,
                    success=success,
                )

        return async_wrapper
    return decorator
