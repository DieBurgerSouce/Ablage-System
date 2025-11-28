"""Embedding-Service fuer semantische Dokumentensuche.

GPU-beschleunigte Generierung von Embeddings mit multilingual-e5-large.
Singleton-Muster fuer effiziente Modellnutzung.
"""

from typing import List, Optional, TypedDict, Union
from datetime import datetime, timezone
import threading
import asyncio

import structlog
import torch
import numpy as np

from app.core.config import settings


class EmbeddingModelInfo(TypedDict, total=False):
    """Typisierte Modell-Informationen."""
    model_name: str
    dimension: int
    max_length: int
    device: str
    loaded: bool
    gpu_name: str
    gpu_memory_allocated_mb: float
    gpu_memory_total_mb: float

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Service fuer semantische Embeddings.

    Verwendet multilingual-e5-large (1024 Dimensionen) fuer deutsche Dokumente.
    GPU-beschleunigt mit VRAM-Management fuer RTX 4080.

    Hinweis: E5-Modelle benoetigen spezielle Praefixe:
    - "query: " fuer Suchanfragen
    - "passage: " fuer Dokumente/Texte
    """

    _instance: Optional['EmbeddingService'] = None
    _lock = threading.Lock()
    _model = None
    _tokenizer = None
    _initialized = False

    def __new__(cls) -> 'EmbeddingService':
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

        self.model_name = settings.EMBEDDING_MODEL
        self.dimension = settings.EMBEDDING_DIMENSION
        self.max_length = settings.EMBEDDING_MAX_LENGTH
        self.batch_size = settings.EMBEDDING_BATCH_SIZE

        # Device-Auswahl
        if settings.ENABLE_GPU and torch.cuda.is_available():
            self.device = torch.device("cuda")
            logger.info(
                "embedding_service_gpu_enabled",
                device=torch.cuda.get_device_name(0),
                vram_total_gb=torch.cuda.get_device_properties(0).total_memory / 1024**3
            )
        else:
            self.device = torch.device("cpu")
            logger.info("embedding_service_cpu_mode")

        self._initialized = True

    def _ensure_model_loaded(self) -> None:
        """Modell laden falls noch nicht geschehen (Lazy Loading)."""
        if self._model is not None:
            return

        with self._lock:
            if self._model is not None:
                return

            logger.info(
                "embedding_model_loading",
                model=self.model_name,
                device=str(self.device)
            )

            try:
                from sentence_transformers import SentenceTransformer

                # Modell laden
                self._model = SentenceTransformer(
                    self.model_name,
                    device=str(self.device)
                )

                # Max sequence length setzen
                self._model.max_seq_length = self.max_length

                # Warmup mit leerem Text (kompiliert CUDA-Kernel)
                if self.device.type == "cuda":
                    _ = self._model.encode(["warmup"], show_progress_bar=False)
                    torch.cuda.synchronize()

                logger.info(
                    "embedding_model_loaded",
                    model=self.model_name,
                    dimension=self._model.get_sentence_embedding_dimension(),
                    max_length=self._model.max_seq_length
                )

            except Exception as e:
                logger.error(
                    "embedding_model_load_failed",
                    model=self.model_name,
                    error=str(e)
                )
                raise RuntimeError(f"Embedding-Modell konnte nicht geladen werden: {e}")

    def _check_gpu_memory(self, required_mb: float = 2000) -> bool:
        """GPU-Speicher pruefen (Threshold: 85% VRAM)."""
        if self.device.type != "cuda":
            return True

        allocated = torch.cuda.memory_allocated() / 1024**2  # MB
        total = torch.cuda.get_device_properties(0).total_memory / 1024**2  # MB
        available = total - allocated
        threshold = total * settings.GPU_MEMORY_FRACTION

        if allocated > threshold:
            logger.warning(
                "gpu_memory_high",
                allocated_mb=allocated,
                total_mb=total,
                threshold_mb=threshold
            )
            torch.cuda.empty_cache()

        return available >= required_mb

    def generate_embedding(
        self,
        text: str,
        is_query: bool = False
    ) -> List[float]:
        """Embedding fuer einzelnen Text generieren.

        Args:
            text: Zu kodierender Text
            is_query: True fuer Suchanfragen (verwendet "query: " Praefix)

        Returns:
            Liste von Floats (1024 Dimensionen)
        """
        self._ensure_model_loaded()

        # E5-Praefix hinzufuegen
        prefix = "query: " if is_query else "passage: "
        prefixed_text = prefix + text

        try:
            # GPU-Speicher pruefen
            self._check_gpu_memory()

            embedding = self._model.encode(
                prefixed_text,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False
            )

            return embedding.tolist()

        except torch.cuda.OutOfMemoryError:
            logger.error("gpu_oom_single_embedding")
            torch.cuda.empty_cache()

            # CPU-Fallback
            if self.device.type == "cuda":
                logger.info("falling_back_to_cpu")
                cpu_model = self._model.to("cpu")
                embedding = cpu_model.encode(
                    prefixed_text,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False
                )
                self._model.to(self.device)
                return embedding.tolist()
            raise

    def generate_query_embedding(self, query: str) -> List[float]:
        """Embedding fuer Suchanfrage generieren.

        Verwendet automatisch "query: " Praefix fuer E5-Modell.
        """
        return self.generate_embedding(query, is_query=True)

    def generate_document_embedding(self, text: str) -> List[float]:
        """Embedding fuer Dokument generieren.

        Verwendet automatisch "passage: " Praefix fuer E5-Modell.
        """
        return self.generate_embedding(text, is_query=False)

    def generate_batch_embeddings(
        self,
        texts: List[str],
        is_query: bool = False,
        batch_size: Optional[int] = None
    ) -> List[List[float]]:
        """Batch-Embeddings generieren mit GPU-Speicher-Management.

        Args:
            texts: Liste von Texten
            is_query: True fuer Suchanfragen
            batch_size: Optionale Batch-Groesse (Standard: aus Config)

        Returns:
            Liste von Embeddings
        """
        if not texts:
            return []

        self._ensure_model_loaded()

        batch_size = batch_size or self.batch_size
        prefix = "query: " if is_query else "passage: "
        prefixed_texts = [prefix + t for t in texts]

        all_embeddings = []

        for i in range(0, len(prefixed_texts), batch_size):
            batch = prefixed_texts[i:i + batch_size]

            try:
                # GPU-Speicher pruefen
                if not self._check_gpu_memory():
                    # Batch-Groesse reduzieren bei Speicherknappheit
                    batch_size = max(1, batch_size // 2)
                    logger.warning(
                        "reducing_batch_size",
                        new_batch_size=batch_size
                    )

                embeddings = self._model.encode(
                    batch,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    batch_size=batch_size,
                    show_progress_bar=False
                )

                all_embeddings.extend(embeddings.tolist())

            except torch.cuda.OutOfMemoryError:
                logger.error(
                    "gpu_oom_batch",
                    batch_start=i,
                    batch_size=len(batch)
                )
                torch.cuda.empty_cache()

                # Einzeln verarbeiten als Fallback
                for idx, text in enumerate(batch):
                    try:
                        emb = self._model.encode(
                            text,
                            convert_to_numpy=True,
                            normalize_embeddings=True,
                            show_progress_bar=False
                        )
                        all_embeddings.append(emb.tolist())
                    except torch.cuda.OutOfMemoryError:
                        logger.error("single_embedding_oom", batch_idx=idx)
                        torch.cuda.empty_cache()
                        # Zero-Vektor als Fallback bei OOM
                        all_embeddings.append([0.0] * self.dimension)
                    except Exception as e:
                        logger.error("single_embedding_failed", error=str(e))
                        all_embeddings.append([0.0] * self.dimension)
                    finally:
                        # Speicher nach jeder Iteration freigeben
                        if self.device.type == "cuda" and idx % 4 == 3:
                            torch.cuda.empty_cache()

        return all_embeddings

    async def generate_embedding_async(
        self,
        text: str,
        is_query: bool = False
    ) -> List[float]:
        """Async-Wrapper fuer Embedding-Generierung."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_embedding(text, is_query)
        )

    async def generate_batch_embeddings_async(
        self,
        texts: List[str],
        is_query: bool = False
    ) -> List[List[float]]:
        """Async-Wrapper fuer Batch-Embedding-Generierung."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_batch_embeddings(texts, is_query)
        )

    def get_model_info(self) -> EmbeddingModelInfo:
        """Modell-Informationen abrufen."""
        self._ensure_model_loaded()

        info: EmbeddingModelInfo = {
            "model_name": self.model_name,
            "dimension": self.dimension,
            "max_length": self.max_length,
            "device": str(self.device),
            "loaded": self._model is not None
        }

        if self.device.type == "cuda":
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["gpu_memory_allocated_mb"] = torch.cuda.memory_allocated() / 1024**2
            info["gpu_memory_total_mb"] = torch.cuda.get_device_properties(0).total_memory / 1024**2

        return info

    def unload_model(self) -> None:
        """Modell aus Speicher entfernen."""
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None

                if self.device.type == "cuda":
                    torch.cuda.empty_cache()

                logger.info("embedding_model_unloaded")


# Singleton-Instanz
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Embedding-Service-Instanz abrufen (Dependency Injection)."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
