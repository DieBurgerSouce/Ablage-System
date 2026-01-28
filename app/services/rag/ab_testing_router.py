"""A/B Testing Traffic-Router fuer Vector Search.

Entscheidet, welches Backend (pgvector vs Qdrant) und welches
Embedding-Modell (E5 vs Jina) fuer eine Anfrage verwendet wird.

Features:
- Konsistentes Hashing fuer reproduzierbare Zuordnung
- User/Session-basiertes Bucketing
- Prometheus-Metriken fuer Experiment-Tracking
- Graduelle Traffic-Splits (0-100%)

Config-Settings (in config.py):
- VECTOR_AB_TESTING_ENABLED: bool
- VECTOR_AB_TRAFFIC_SPLIT: int (0-100)
- VECTOR_AB_CONTROL_BACKEND: str (pgvector oder qdrant)
- VECTOR_AB_TREATMENT_BACKEND: str (pgvector oder qdrant)
- VECTOR_AB_CONTROL_EMBEDDING: str (Modellname)
- VECTOR_AB_TREATMENT_EMBEDDING: str (Modellname)
"""

from typing import Optional, Dict, Any, Literal, TypedDict, NamedTuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import threading
import time

import structlog
from prometheus_client import Counter, Histogram, Gauge

from app.core.config import settings
from app.services.embedding_service import EmbeddingModelType

logger = structlog.get_logger(__name__)


# ============================================================================
# Prometheus Metriken
# ============================================================================

# Counter: Gesamtzahl der Vector-Suchen pro Variante und Backend
vector_search_total = Counter(
    'vector_search_total',
    'Gesamtzahl der Vector-Suchen',
    ['variant', 'backend']
)

# Counter: Fehler pro Variante und Backend
vector_search_errors_total = Counter(
    'vector_search_errors_total',
    'Anzahl der Fehler bei Vector-Suchen',
    ['variant', 'backend']
)

# Histogram: Latenz der Vector-Suchen in Sekunden
vector_search_latency_seconds = Histogram(
    'vector_search_latency_seconds',
    'Latenz der Vector-Suchen in Sekunden',
    ['variant', 'backend'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Gauge: A/B Testing aktiviert (0 oder 1)
ablage_ab_testing_enabled = Gauge(
    'ablage_ab_testing_enabled',
    'A/B Testing aktiviert (1) oder deaktiviert (0)'
)

# Gauge: Aktueller Traffic-Split Prozentsatz (0-100)
ablage_ab_testing_traffic_split = Gauge(
    'ablage_ab_testing_traffic_split',
    'Traffic-Split Prozentsatz fuer Treatment-Variante (0-100)'
)


# ============================================================================
# Types
# ============================================================================


class ExperimentVariant(str, Enum):
    """Experiment-Varianten."""
    CONTROL = "control"
    TREATMENT = "treatment"


class VectorBackend(str, Enum):
    """Verfuegbare Vector Backends."""
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"


class ABAssignment(NamedTuple):
    """A/B Test Zuordnung mit allen notwendigen Infos."""
    variant: ExperimentVariant
    backend: VectorBackend
    embedding_model: EmbeddingModelType
    bucket_id: int
    assignment_reason: str


class ABTestResult(TypedDict, total=False):
    """Ergebnis einer A/B Test Suche fuer Metriken."""
    variant: str
    backend: str
    embedding_model: str
    query_time_ms: float
    result_count: int
    avg_score: float
    user_id: Optional[str]
    session_id: Optional[str]
    query_hash: str
    timestamp: str


@dataclass
class ABTestMetrics:
    """Aggregierte Metriken pro Variante."""
    variant: ExperimentVariant
    total_requests: int = 0
    total_latency_ms: float = 0.0
    total_results: int = 0
    total_score: float = 0.0
    errors: int = 0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def avg_latency_ms(self) -> float:
        """Durchschnittliche Latenz."""
        return self.total_latency_ms / self.total_requests if self.total_requests > 0 else 0.0

    @property
    def avg_results(self) -> float:
        """Durchschnittliche Anzahl Ergebnisse."""
        return self.total_results / self.total_requests if self.total_requests > 0 else 0.0

    @property
    def avg_score(self) -> float:
        """Durchschnittlicher Score."""
        return self.total_score / self.total_results if self.total_results > 0 else 0.0


# ============================================================================
# A/B Testing Router
# ============================================================================


class ABTestingRouter:
    """Router fuer A/B Testing zwischen Vector-Backends.

    Verwendet konsistentes Hashing fuer deterministische Zuordnung:
    - Gleicher User -> Gleiche Variante (fuer konsistente UX)
    - Traffic-Split konfigurierbar (0-100%)
    - Fallback auf Control bei Fehlern
    """

    _instance: Optional['ABTestingRouter'] = None
    _lock = threading.Lock()

    def __new__(cls) -> 'ABTestingRouter':
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

        self._enabled = settings.VECTOR_AB_TESTING_ENABLED
        self._traffic_split = settings.VECTOR_AB_TRAFFIC_SPLIT

        # Control-Konfiguration
        self._control_backend = VectorBackend(settings.VECTOR_AB_CONTROL_BACKEND)
        self._control_embedding = self._parse_embedding_model(
            settings.VECTOR_AB_CONTROL_EMBEDDING
        )

        # Treatment-Konfiguration
        self._treatment_backend = VectorBackend(settings.VECTOR_AB_TREATMENT_BACKEND)
        self._treatment_embedding = self._parse_embedding_model(
            settings.VECTOR_AB_TREATMENT_EMBEDDING
        )

        # In-Memory Metriken (fuer schnellen Zugriff, Redis fuer Persistenz)
        self._metrics: Dict[ExperimentVariant, ABTestMetrics] = {
            ExperimentVariant.CONTROL: ABTestMetrics(variant=ExperimentVariant.CONTROL),
            ExperimentVariant.TREATMENT: ABTestMetrics(variant=ExperimentVariant.TREATMENT),
        }
        self._metrics_lock = threading.Lock()
        self._config_lock = threading.Lock()  # Lock fuer Konfigurationsaenderungen

        # Prometheus Gauges initialisieren
        ablage_ab_testing_enabled.set(1 if self._enabled else 0)
        ablage_ab_testing_traffic_split.set(self._traffic_split)

        self._initialized = True

        logger.info(
            "ab_testing_router_initialized",
            enabled=self._enabled,
            traffic_split=self._traffic_split,
            control_backend=self._control_backend.value,
            control_embedding=self._control_embedding.value,
            treatment_backend=self._treatment_backend.value,
            treatment_embedding=self._treatment_embedding.value
        )

    def _parse_embedding_model(self, model_name: str) -> EmbeddingModelType:
        """Modellname zu EmbeddingModelType konvertieren."""
        if "jina" in model_name.lower():
            return EmbeddingModelType.JINA_GERMAN
        return EmbeddingModelType.E5_MULTILINGUAL

    def _compute_bucket(self, identifier: str) -> int:
        """Konsistentes Bucket basierend auf Identifier berechnen.

        Args:
            identifier: User-ID, Session-ID oder anderer stabiler Identifier

        Returns:
            Bucket-Nummer (0-99)
        """
        # SHA256 fuer gleichmaessige Verteilung
        hash_bytes = hashlib.sha256(identifier.encode()).digest()
        # Erste 4 Bytes als Integer, modulo 100 fuer Bucket
        bucket = int.from_bytes(hash_bytes[:4], byteorder='big') % 100
        return bucket

    def get_assignment(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        document_id: Optional[str] = None,
        force_variant: Optional[ExperimentVariant] = None
    ) -> ABAssignment:
        """A/B Test Zuordnung fuer eine Anfrage ermitteln.

        Prioritaet fuer Identifier:
        1. force_variant (fuer Testing/Debugging)
        2. user_id (stabiles User-Bucketing)
        3. session_id (Session-Konsistenz)
        4. document_id (Query-Konsistenz)
        5. Random (fuer anonyme Anfragen)

        Args:
            user_id: User-Identifier (bevorzugt)
            session_id: Session-Identifier
            document_id: Dokument-ID fuer Query
            force_variant: Erzwungene Variante (Testing)

        Returns:
            ABAssignment mit allen Details
        """
        # A/B Testing deaktiviert -> Control
        if not self._enabled:
            return ABAssignment(
                variant=ExperimentVariant.CONTROL,
                backend=self._control_backend,
                embedding_model=self._control_embedding,
                bucket_id=-1,
                assignment_reason="ab_testing_disabled"
            )

        # Erzwungene Variante
        if force_variant is not None:
            if force_variant == ExperimentVariant.TREATMENT:
                return ABAssignment(
                    variant=ExperimentVariant.TREATMENT,
                    backend=self._treatment_backend,
                    embedding_model=self._treatment_embedding,
                    bucket_id=-1,
                    assignment_reason="forced_treatment"
                )
            return ABAssignment(
                variant=ExperimentVariant.CONTROL,
                backend=self._control_backend,
                embedding_model=self._control_embedding,
                bucket_id=-1,
                assignment_reason="forced_control"
            )

        # Identifier bestimmen
        identifier: str
        reason_prefix: str

        if user_id:
            identifier = f"user:{user_id}"
            reason_prefix = "user_bucket"
        elif session_id:
            identifier = f"session:{session_id}"
            reason_prefix = "session_bucket"
        elif document_id:
            identifier = f"doc:{document_id}"
            reason_prefix = "document_bucket"
        else:
            # Deterministischer Bucket fuer anonyme Anfragen basierend auf Timestamp
            # Verwendet time_ns fuer Nanosekunden-Praezision und hashlib fuer deterministische Verteilung
            import hashlib
            import time
            ts_seed = f"anon:{time.time_ns()}"
            ts_hash = int(hashlib.md5(ts_seed.encode()).hexdigest()[:8], 16)
            identifier = f"timestamp:{ts_hash}"
            reason_prefix = "timestamp_bucket"

        # Bucket berechnen
        bucket = self._compute_bucket(identifier)

        # Traffic-Split: Bucket < traffic_split -> Treatment
        if bucket < self._traffic_split:
            return ABAssignment(
                variant=ExperimentVariant.TREATMENT,
                backend=self._treatment_backend,
                embedding_model=self._treatment_embedding,
                bucket_id=bucket,
                assignment_reason=f"{reason_prefix}:treatment"
            )
        else:
            return ABAssignment(
                variant=ExperimentVariant.CONTROL,
                backend=self._control_backend,
                embedding_model=self._control_embedding,
                bucket_id=bucket,
                assignment_reason=f"{reason_prefix}:control"
            )

    def is_treatment(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> bool:
        """Schnelle Pruefung ob Treatment-Variante.

        Convenience-Methode fuer einfache Checks.
        """
        assignment = self.get_assignment(user_id=user_id, session_id=session_id)
        return assignment.variant == ExperimentVariant.TREATMENT

    def record_result(
        self,
        assignment: ABAssignment,
        query_time_ms: float,
        result_count: int,
        avg_score: float,
        error: bool = False
    ) -> None:
        """Suchergebnis fuer Metriken aufzeichnen.

        Args:
            assignment: A/B Zuordnung
            query_time_ms: Query-Dauer in Millisekunden
            result_count: Anzahl zurueckgegebener Ergebnisse
            avg_score: Durchschnittlicher Relevanz-Score
            error: True wenn Fehler aufgetreten
        """
        if not settings.VECTOR_AB_METRICS_ENABLED:
            return

        variant_str = assignment.variant.value
        backend_str = assignment.backend.value

        # Prometheus-Metriken aktualisieren
        vector_search_total.labels(variant=variant_str, backend=backend_str).inc()
        vector_search_latency_seconds.labels(
            variant=variant_str, backend=backend_str
        ).observe(query_time_ms / 1000.0)  # Millisekunden zu Sekunden

        if error:
            vector_search_errors_total.labels(
                variant=variant_str, backend=backend_str
            ).inc()

        # In-Memory Metriken aktualisieren
        with self._metrics_lock:
            metrics = self._metrics[assignment.variant]
            metrics.total_requests += 1
            metrics.total_latency_ms += query_time_ms
            metrics.total_results += result_count
            metrics.total_score += avg_score * result_count
            if error:
                metrics.errors += 1
            metrics.last_updated = datetime.now(timezone.utc)

        logger.debug(
            "ab_test_result_recorded",
            variant=variant_str,
            backend=backend_str,
            query_time_ms=query_time_ms,
            result_count=result_count,
            avg_score=avg_score,
            error=error
        )

    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Aktuelle Metriken abrufen.

        Returns:
            Dictionary mit Metriken pro Variante
        """
        with self._metrics_lock:
            return {
                variant.value: {
                    "total_requests": metrics.total_requests,
                    "avg_latency_ms": round(metrics.avg_latency_ms, 2),
                    "avg_results": round(metrics.avg_results, 2),
                    "avg_score": round(metrics.avg_score, 4),
                    "errors": metrics.errors,
                    "error_rate": round(
                        metrics.errors / metrics.total_requests
                        if metrics.total_requests > 0 else 0, 4
                    ),
                    "last_updated": metrics.last_updated.isoformat()
                }
                for variant, metrics in self._metrics.items()
            }

    def reset_metrics(self) -> None:
        """Metriken zuruecksetzen (fuer neue Experiment-Phase)."""
        with self._metrics_lock:
            self._metrics = {
                ExperimentVariant.CONTROL: ABTestMetrics(variant=ExperimentVariant.CONTROL),
                ExperimentVariant.TREATMENT: ABTestMetrics(variant=ExperimentVariant.TREATMENT),
            }
        logger.info("ab_test_metrics_reset")

    def update_traffic_split(self, new_split: int) -> None:
        """Traffic-Split zur Laufzeit aendern (0-100).

        Ermoeglicht graduelle Rollouts ohne Restart.
        Thread-safe durch Config-Lock.

        Args:
            new_split: Neuer Prozentsatz fuer Treatment (0-100)
        """
        if not 0 <= new_split <= 100:
            raise ValueError(f"Traffic-Split muss zwischen 0 und 100 liegen: {new_split}")

        with self._config_lock:
            old_split = self._traffic_split
            self._traffic_split = new_split
            # Prometheus Gauge aktualisieren
            ablage_ab_testing_traffic_split.set(new_split)

        logger.info(
            "ab_test_traffic_split_updated",
            old_split=old_split,
            new_split=new_split
        )

    def get_status(self) -> Dict[str, Any]:
        """Status des A/B Testing Systems."""
        return {
            "enabled": self._enabled,
            "traffic_split": self._traffic_split,
            "control": {
                "backend": self._control_backend.value,
                "embedding_model": self._control_embedding.value
            },
            "treatment": {
                "backend": self._treatment_backend.value,
                "embedding_model": self._treatment_embedding.value
            },
            "metrics": self.get_metrics()
        }


# ============================================================================
# Context Manager fuer A/B Test Timing
# ============================================================================


class ABTestContext:
    """Context Manager fuer A/B Test Tracking.

    Automatisches Timing und Metrik-Recording.

    Beispiel:
        router = get_ab_testing_router()
        assignment = router.get_assignment(user_id=user.id)

        async with ABTestContext(router, assignment) as ctx:
            results = await search(...)
            ctx.set_results(results)
    """

    def __init__(
        self,
        router: ABTestingRouter,
        assignment: ABAssignment
    ) -> None:
        """Initialisierung."""
        self.router = router
        self.assignment = assignment
        self.start_time: float = 0.0
        self.result_count: int = 0
        self.avg_score: float = 0.0
        self.error: bool = False

    def __enter__(self) -> 'ABTestContext':
        """Context betreten - Start Timing."""
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context verlassen - Metriken aufzeichnen."""
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000

        if exc_type is not None:
            self.error = True

        self.router.record_result(
            assignment=self.assignment,
            query_time_ms=elapsed_ms,
            result_count=self.result_count,
            avg_score=self.avg_score,
            error=self.error
        )

    async def __aenter__(self) -> 'ABTestContext':
        """Async Context betreten."""
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async Context verlassen."""
        self.__exit__(exc_type, exc_val, exc_tb)

    def set_results(
        self,
        result_count: int,
        avg_score: float = 0.0
    ) -> None:
        """Ergebnisse setzen fuer Metriken."""
        self.result_count = result_count
        self.avg_score = avg_score


# ============================================================================
# Factory Function
# ============================================================================


def get_ab_testing_router() -> ABTestingRouter:
    """A/B Testing Router Instanz abrufen (Dependency Injection).

    Nutzt den Klassen-Level Singleton von ABTestingRouter.
    Thread-safe durch Double-Checked Locking in __new__.
    """
    return ABTestingRouter()
