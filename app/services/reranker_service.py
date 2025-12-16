"""Reranker-Service fuer RAG Search mit GPU/CPU Dual-Stack.

GPU-beschleunigtes Reranking mit BGE-Reranker-v2-m3 (primaer)
und CPU-Fallback mit MiniLM Cross-Encoder.

Singleton-Muster fuer effiziente Modellnutzung.
"""

from typing import List, Optional, TypedDict
from dataclasses import dataclass
import threading
import asyncio

import structlog

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

from app.core.config import settings

logger = structlog.get_logger(__name__)

# Metriken-Import (optional)
try:
    from app.services.rag.metrics import record_rerank, record_rerank_fallback
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


class RerankerModelInfo(TypedDict, total=False):
    """Typisierte Modell-Informationen."""
    gpu_model: str
    cpu_model: str
    gpu_loaded: bool
    cpu_loaded: bool
    device: str
    gpu_vram_mb: float


@dataclass
class RerankedResult:
    """Einzelnes Reranking-Ergebnis."""
    index: int
    score: float
    text: str


class RerankerService:
    """Service fuer Cross-Encoder Reranking mit GPU/CPU Fallback.

    Implementiert Dual-Stack:
    - GPU: BGE-Reranker-v2-m3 (~1GB VRAM)
    - CPU: MiniLM Cross-Encoder (~300MB RAM)

    Features:
    - Lazy Model Loading
    - Automatischer GPU->CPU Fallback bei VRAM-Knappheit
    - Thread-safe Singleton
    - Statistik-Tracking
    """

    _instance: Optional['RerankerService'] = None
    _lock = threading.Lock()
    _gpu_model = None
    _cpu_model = None
    _initialized = False

    # Model configurations
    GPU_MODEL_NAME = getattr(settings, 'RERANKER_GPU_MODEL', "BAAI/bge-reranker-v2-m3")
    CPU_MODEL_NAME = getattr(settings, 'RERANKER_CPU_MODEL', "cross-encoder/ms-marco-MiniLM-L-12-v2")
    GPU_VRAM_REQUIREMENT_GB = getattr(settings, 'RERANKER_GPU_VRAM_GB', 1.0)

    def __new__(cls) -> 'RerankerService':
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

        # Device availability check
        self._gpu_available = (
            TORCH_AVAILABLE and
            getattr(settings, 'ENABLE_GPU', True) and
            torch is not None and
            torch.cuda.is_available() and
            getattr(settings, 'RAG_RERANK_ENABLED', True)
        )

        # Batch size and max length
        self._batch_size = getattr(settings, 'RERANKER_BATCH_SIZE', 8)
        self._max_length = getattr(settings, 'RERANKER_MAX_LENGTH', 512)

        # Stats tracking
        self._stats = {
            "gpu_rerank_count": 0,
            "cpu_rerank_count": 0,
            "gpu_fallback_count": 0,
            "total_documents_reranked": 0,
            "total_queries": 0,
        }

        logger.info(
            "reranker_service_initialized",
            gpu_available=self._gpu_available,
            gpu_model=self.GPU_MODEL_NAME,
            cpu_model=self.CPU_MODEL_NAME,
            enabled=getattr(settings, 'RAG_RERANK_ENABLED', True)
        )

        self._initialized = True

    def _check_gpu_vram(self, required_gb: float) -> bool:
        """Pruefe ob genuegend VRAM fuer Reranker verfuegbar ist."""
        if not TORCH_AVAILABLE or torch is None or not torch.cuda.is_available():
            return False

        try:
            allocated = torch.cuda.memory_allocated(0) / 1024**3  # GB
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3  # GB
            threshold = total * getattr(settings, 'GPU_MEMORY_FRACTION', 0.85)
            available = threshold - allocated

            return available >= required_gb

        except Exception as e:
            logger.warning("gpu_vram_check_failed", error=str(e))
            return False

    def _ensure_gpu_model_loaded(self) -> bool:
        """GPU-Modell laden falls moeglich und noch nicht geladen."""
        if not self._gpu_available:
            return False

        if self._gpu_model is not None:
            return True

        with self._lock:
            if self._gpu_model is not None:
                return True

            # Check VRAM availability
            if not self._check_gpu_vram(self.GPU_VRAM_REQUIREMENT_GB):
                logger.warning(
                    "gpu_reranker_vram_insufficient",
                    required_gb=self.GPU_VRAM_REQUIREMENT_GB
                )
                return False

            try:
                from sentence_transformers import CrossEncoder

                logger.info(
                    "gpu_reranker_loading",
                    model=self.GPU_MODEL_NAME
                )

                self._gpu_model = CrossEncoder(
                    self.GPU_MODEL_NAME,
                    max_length=self._max_length,
                    device="cuda"
                )

                # Warmup inference (kompiliert CUDA-Kernel)
                _ = self._gpu_model.predict([("warmup query", "warmup document")])
                if torch is not None:
                    torch.cuda.synchronize()

                vram_after = 0.0
                if torch is not None and torch.cuda.is_available():
                    vram_after = torch.cuda.memory_allocated(0) / 1024**3

                logger.info(
                    "gpu_reranker_loaded",
                    model=self.GPU_MODEL_NAME,
                    vram_after_load_gb=round(vram_after, 2)
                )
                return True

            except Exception as e:
                logger.error(
                    "gpu_reranker_load_failed",
                    model=self.GPU_MODEL_NAME,
                    error=str(e)
                )
                return False

    def _ensure_cpu_model_loaded(self) -> bool:
        """CPU-Modell laden falls noch nicht geladen."""
        if self._cpu_model is not None:
            return True

        with self._lock:
            if self._cpu_model is not None:
                return True

            try:
                from sentence_transformers import CrossEncoder

                logger.info(
                    "cpu_reranker_loading",
                    model=self.CPU_MODEL_NAME
                )

                self._cpu_model = CrossEncoder(
                    self.CPU_MODEL_NAME,
                    max_length=self._max_length,
                    device="cpu"
                )

                # Warmup
                _ = self._cpu_model.predict([("warmup query", "warmup document")])

                logger.info("cpu_reranker_loaded", model=self.CPU_MODEL_NAME)
                return True

            except Exception as e:
                logger.error(
                    "cpu_reranker_load_failed",
                    model=self.CPU_MODEL_NAME,
                    error=str(e)
                )
                return False

    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None
    ) -> List[RerankedResult]:
        """Dokumente mit Cross-Encoder reranken.

        Versucht zuerst GPU, faellt auf CPU zurueck bei:
        - GPU nicht verfuegbar
        - VRAM-Knappheit
        - GPU-Modell-Fehler

        Args:
            query: Suchanfrage
            documents: Liste von Dokumenttexten
            top_k: Anzahl Top-Ergebnisse (None = alle)

        Returns:
            Liste von RerankedResult sortiert nach Score (absteigend)
        """
        if not documents:
            return []

        if not getattr(settings, 'RAG_RERANK_ENABLED', True):
            # Reranking deaktiviert - Original-Reihenfolge beibehalten
            return [
                RerankedResult(index=i, score=1.0 - (i * 0.01), text=doc)
                for i, doc in enumerate(documents)
            ]

        top_k = top_k or getattr(settings, 'RAG_RERANK_TOP_K', 10)
        self._stats["total_queries"] += 1

        # Versuche GPU-Reranking
        if self._gpu_available:
            try:
                gpu_loaded = self._ensure_gpu_model_loaded()
                if gpu_loaded and self._gpu_model is not None:
                    results = self._rerank_with_model(
                        self._gpu_model, query, documents, "gpu"
                    )
                    self._stats["gpu_rerank_count"] += 1
                    self._stats["total_documents_reranked"] += len(documents)

                    return results[:top_k] if top_k else results

            except Exception as e:
                fallback_reason = "error"
                if TORCH_AVAILABLE and torch is not None:
                    if "OutOfMemoryError" in str(type(e).__name__):
                        logger.warning("gpu_reranker_oom", falling_back_to="cpu")
                        torch.cuda.empty_cache()
                        fallback_reason = "oom"
                    else:
                        logger.warning(
                            "gpu_reranker_error",
                            error=str(e),
                            falling_back_to="cpu"
                        )
                self._stats["gpu_fallback_count"] += 1

                # Prometheus Fallback-Metrik
                if METRICS_AVAILABLE:
                    record_rerank_fallback(reason=fallback_reason)

        # CPU-Fallback
        if self._ensure_cpu_model_loaded() and self._cpu_model is not None:
            results = self._rerank_with_model(
                self._cpu_model, query, documents, "cpu"
            )
            self._stats["cpu_rerank_count"] += 1
            self._stats["total_documents_reranked"] += len(documents)

            return results[:top_k] if top_k else results

        # Letzter Fallback: Original-Reihenfolge
        logger.error("reranker_all_backends_failed")
        return [
            RerankedResult(index=i, score=1.0 - (i * 0.01), text=doc)
            for i, doc in enumerate(documents)
        ]

    def _rerank_with_model(
        self,
        model,  # CrossEncoder
        query: str,
        documents: List[str],
        backend: str
    ) -> List[RerankedResult]:
        """Reranking mit spezifischem Modell durchfuehren."""
        import time
        start_time = time.time()

        # Erstelle Query-Document Paare
        pairs = [(query, doc) for doc in documents]

        # Scores berechnen
        scores = model.predict(
            pairs,
            show_progress_bar=False,
            batch_size=self._batch_size
        )

        # Ergebnisse erstellen und sortieren
        results = [
            RerankedResult(index=i, score=float(score), text=doc)
            for i, (score, doc) in enumerate(zip(scores, documents))
        ]

        # Nach Score sortieren (absteigend)
        results.sort(key=lambda x: x.score, reverse=True)

        elapsed_ms = (time.time() - start_time) * 1000

        logger.debug(
            "rerank_complete",
            backend=backend,
            documents_count=len(documents),
            latency_ms=round(elapsed_ms, 1),
            top_score=round(results[0].score, 4) if results else 0
        )

        # Prometheus Metriken
        if METRICS_AVAILABLE:
            record_rerank(
                backend=backend,
                latency_ms=elapsed_ms,
                documents_count=len(documents),
                status="success"
            )

        return results

    async def rerank_async(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None
    ) -> List[RerankedResult]:
        """Async-Wrapper fuer Reranking."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.rerank(query, documents, top_k)
        )

    def get_stats(self) -> dict:
        """Statistiken abrufen."""
        return {
            **self._stats,
            "gpu_model_loaded": self._gpu_model is not None,
            "cpu_model_loaded": self._cpu_model is not None,
            "gpu_available": self._gpu_available,
            "gpu_model": self.GPU_MODEL_NAME,
            "cpu_model": self.CPU_MODEL_NAME,
        }

    def get_model_info(self) -> RerankerModelInfo:
        """Detaillierte Modell-Informationen abrufen."""
        info: RerankerModelInfo = {
            "gpu_model": self.GPU_MODEL_NAME,
            "cpu_model": self.CPU_MODEL_NAME,
            "gpu_loaded": self._gpu_model is not None,
            "cpu_loaded": self._cpu_model is not None,
            "device": "cuda" if self._gpu_available else "cpu",
        }

        if TORCH_AVAILABLE and torch is not None and torch.cuda.is_available():
            info["gpu_vram_mb"] = torch.cuda.memory_allocated(0) / 1024**2

        return info

    def unload_gpu_model(self) -> None:
        """GPU-Modell aus Speicher entfernen (fuer OCR VRAM-Freigabe)."""
        with self._lock:
            if self._gpu_model is not None:
                del self._gpu_model
                self._gpu_model = None
                if TORCH_AVAILABLE and torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("gpu_reranker_unloaded")

    def unload_all_models(self) -> None:
        """Alle Modelle aus Speicher entfernen."""
        with self._lock:
            if self._gpu_model is not None:
                del self._gpu_model
                self._gpu_model = None
                if TORCH_AVAILABLE and torch is not None and torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("gpu_reranker_unloaded")

            if self._cpu_model is not None:
                del self._cpu_model
                self._cpu_model = None
                logger.info("cpu_reranker_unloaded")

    def is_available(self) -> bool:
        """Pruefe ob Reranking verfuegbar ist (min. ein Backend)."""
        if not getattr(settings, 'RAG_RERANK_ENABLED', True):
            return False

        # GPU oder CPU muss ladbar sein
        return self._gpu_available or True  # CPU ist immer verfuegbar


# Singleton-Instanz
_reranker_service: Optional[RerankerService] = None


def get_reranker_service() -> RerankerService:
    """Reranker-Service-Instanz abrufen (Dependency Injection)."""
    global _reranker_service
    if _reranker_service is None:
        _reranker_service = RerankerService()
    return _reranker_service
