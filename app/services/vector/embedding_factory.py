"""
Embedding Factory Service.

Multi-Model Embedding Generation fuer A/B Testing:
- intfloat/multilingual-e5-large (Standard, 1024D)
- jinaai/jina-embeddings-v2-base-de (Deutsch-optimiert, 8k Kontext)

Features:
- Lazy Model Loading
- GPU Memory Management
- Model Switching
- Query vs Document Prefixes

Feinpoliert und durchdacht.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, List, Dict, Any, Tuple
from enum import Enum
import asyncio
import threading

import structlog
import torch
import numpy as np

from app.core.config import settings
from app.core.safe_errors import safe_error_log

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

logger = structlog.get_logger(__name__)


class EmbeddingModel(str, Enum):
    """Verfuegbare Embedding-Modelle."""
    E5_LARGE = "intfloat/multilingual-e5-large"
    JINA_DE = "jinaai/jina-embeddings-v2-base-de"


class ModelConfig:
    """Konfiguration fuer ein Embedding-Modell."""

    def __init__(
        self,
        model_id: str,
        dimension: int,
        max_length: int,
        query_prefix: str = "",
        passage_prefix: str = "",
        trust_remote_code: bool = False,
        gpu_memory_mb: int = 2000,
    ):
        self.model_id = model_id
        self.dimension = dimension
        self.max_length = max_length
        self.query_prefix = query_prefix
        self.passage_prefix = passage_prefix
        self.trust_remote_code = trust_remote_code
        self.gpu_memory_mb = gpu_memory_mb


# Model Configurations
MODEL_CONFIGS: Dict[str, ModelConfig] = {
    EmbeddingModel.E5_LARGE: ModelConfig(
        model_id="intfloat/multilingual-e5-large",
        dimension=1024,
        max_length=512,
        query_prefix="query: ",
        passage_prefix="passage: ",
        trust_remote_code=False,
        gpu_memory_mb=2000,
    ),
    EmbeddingModel.JINA_DE: ModelConfig(
        model_id="jinaai/jina-embeddings-v2-base-de",
        dimension=1024,
        max_length=8192,  # 8k Token-Kontext!
        query_prefix="",  # Jina braucht keine Prefixes
        passage_prefix="",
        trust_remote_code=True,  # Required fuer Jina
        gpu_memory_mb=1500,
    ),
}


class EmbeddingFactory:
    """
    Multi-Model Embedding Factory.

    Verwaltet mehrere Embedding-Modelle mit GPU Memory Management.
    Nur EIN Modell gleichzeitig auf GPU geladen (wegen VRAM-Limits).
    """

    _instance: Optional["EmbeddingFactory"] = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialisiere EmbeddingFactory."""
        self._models: Dict[str, SentenceTransformer] = {}
        self._current_model: Optional[str] = None
        self._device: Optional[str] = None
        self._model_lock = asyncio.Lock()

        # Bestimme Device
        if torch.cuda.is_available() and settings.ENABLE_GPU:
            self._device = "cuda"
        else:
            self._device = "cpu"

        logger.info(
            "embedding_factory_init",
            device=self._device,
            gpu_available=torch.cuda.is_available()
        )

    @classmethod
    def get_instance(cls) -> "EmbeddingFactory":
        """Get Singleton Instance (thread-safe)."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _get_config(self, model_name: str) -> ModelConfig:
        """Hole Model-Konfiguration."""
        # Normalisiere Model-Name
        if model_name in MODEL_CONFIGS:
            return MODEL_CONFIGS[model_name]

        # Suche nach Model-ID
        for key, config in MODEL_CONFIGS.items():
            if config.model_id == model_name:
                return config

        # Fallback zu E5-Large
        logger.warning(
            "embedding_model_not_found",
            model=model_name,
            fallback=EmbeddingModel.E5_LARGE
        )
        return MODEL_CONFIGS[EmbeddingModel.E5_LARGE]

    async def _load_model(self, model_name: str) -> SentenceTransformer:
        """
        Lade Modell (lazy loading mit GPU Memory Management).

        Args:
            model_name: Model-ID oder Enum-Name

        Returns:
            SentenceTransformer Modell
        """
        config = self._get_config(model_name)
        model_id = config.model_id

        # Bereits geladen?
        if model_id in self._models:
            return self._models[model_id]

        # GPU Memory Check: Anderes Modell entladen wenn noetig
        if self._current_model and self._current_model != model_id:
            await self._unload_model(self._current_model)

        try:
            from sentence_transformers import SentenceTransformer

            logger.info(
                "embedding_model_loading",
                model=model_id,
                device=self._device,
                trust_remote_code=config.trust_remote_code
            )

            # Modell laden
            model = SentenceTransformer(
                model_id,
                device=self._device,
                trust_remote_code=config.trust_remote_code,
            )

            # Auf GPU verschieben falls verfuegbar
            if self._device == "cuda":
                model = model.to(self._device)
                # Warmup
                _ = model.encode(["Warmup-Text fuer GPU-Initialisierung"])

            self._models[model_id] = model
            self._current_model = model_id

            logger.info(
                "embedding_model_loaded",
                model=model_id,
                device=self._device,
                max_length=config.max_length
            )

            return model

        except Exception as e:
            logger.error(
                "embedding_model_load_error",
                model=model_id,
                **safe_error_log(e)
            )
            raise

    async def _unload_model(self, model_id: str) -> None:
        """
        Entlade Modell aus GPU Memory.

        Args:
            model_id: Model-ID zum Entladen
        """
        if model_id not in self._models:
            return

        try:
            logger.info("embedding_model_unloading", model=model_id)

            model = self._models.pop(model_id)
            del model

            # GPU Memory freigeben
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()

            if self._current_model == model_id:
                self._current_model = None

            logger.info("embedding_model_unloaded", model=model_id)

        except Exception as e:
            logger.error(
                "embedding_model_unload_error",
                model=model_id,
                **safe_error_log(e)
            )

    async def generate_embedding(
        self,
        text: str,
        model_name: str = EmbeddingModel.E5_LARGE,
        is_query: bool = False,
    ) -> Optional[List[float]]:
        """
        Generiere Embedding fuer einen Text.

        Args:
            text: Zu embeddenber Text
            model_name: Modell-Name
            is_query: True fuer Query-Embedding (mit query: Prefix)

        Returns:
            Embedding-Vektor als Liste oder None bei Fehler
        """
        async with self._model_lock:
            try:
                config = self._get_config(model_name)
                model = await self._load_model(model_name)

                # Prefix hinzufuegen
                if is_query and config.query_prefix:
                    text = f"{config.query_prefix}{text}"
                elif not is_query and config.passage_prefix:
                    text = f"{config.passage_prefix}{text}"

                # Embedding generieren
                embedding = model.encode(
                    text,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )

                return embedding.tolist()

            except Exception as e:
                logger.error(
                    "embedding_generation_error",
                    model=model_name,
                    text_length=len(text),
                    **safe_error_log(e)
                )
                return None

    async def generate_batch_embeddings(
        self,
        texts: List[str],
        model_name: str = EmbeddingModel.E5_LARGE,
        is_query: bool = False,
        batch_size: int = 8,
    ) -> List[Optional[List[float]]]:
        """
        Generiere Embeddings fuer mehrere Texte.

        Args:
            texts: Liste von Texten
            model_name: Modell-Name
            is_query: True fuer Query-Embeddings
            batch_size: Batch-Groesse

        Returns:
            Liste von Embedding-Vektoren
        """
        async with self._model_lock:
            try:
                config = self._get_config(model_name)
                model = await self._load_model(model_name)

                # Prefixes hinzufuegen
                prefix = config.query_prefix if is_query else config.passage_prefix
                if prefix:
                    texts = [f"{prefix}{t}" for t in texts]

                # Batch Embedding
                embeddings = model.encode(
                    texts,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=batch_size,
                )

                return [e.tolist() for e in embeddings]

            except torch.cuda.OutOfMemoryError:
                logger.warning(
                    "embedding_batch_oom",
                    batch_size=batch_size,
                    texts_count=len(texts)
                )
                # Fallback: Einzeln verarbeiten
                torch.cuda.empty_cache()
                return [
                    await self.generate_embedding(t, model_name, is_query)
                    for t in texts
                ]

            except Exception as e:
                logger.error(
                    "embedding_batch_error",
                    model=model_name,
                    texts_count=len(texts),
                    **safe_error_log(e)
                )
                return [None] * len(texts)

    async def generate_query_embedding(
        self,
        query: str,
        model_name: str = EmbeddingModel.E5_LARGE,
    ) -> Optional[List[float]]:
        """
        Generiere Query-Embedding (mit query: Prefix).

        Args:
            query: Suchanfrage
            model_name: Modell-Name

        Returns:
            Query-Embedding oder None
        """
        return await self.generate_embedding(query, model_name, is_query=True)

    async def generate_document_embedding(
        self,
        document_text: str,
        model_name: str = EmbeddingModel.E5_LARGE,
    ) -> Optional[List[float]]:
        """
        Generiere Document-Embedding (mit passage: Prefix).

        Args:
            document_text: Dokument-Text
            model_name: Modell-Name

        Returns:
            Document-Embedding oder None
        """
        return await self.generate_embedding(document_text, model_name, is_query=False)

    def get_model_info(self, model_name: str) -> Dict[str, Any]:
        """
        Hole Informationen ueber ein Modell.

        Args:
            model_name: Modell-Name

        Returns:
            Dict mit Modell-Informationen
        """
        config = self._get_config(model_name)
        is_loaded = config.model_id in self._models

        return {
            "model_id": config.model_id,
            "dimension": config.dimension,
            "max_length": config.max_length,
            "query_prefix": config.query_prefix,
            "passage_prefix": config.passage_prefix,
            "gpu_memory_mb": config.gpu_memory_mb,
            "is_loaded": is_loaded,
            "is_current": self._current_model == config.model_id,
            "device": self._device,
        }

    def get_available_models(self) -> List[Dict[str, Any]]:
        """Hole Liste aller verfuegbaren Modelle."""
        return [
            self.get_model_info(model.value)
            for model in EmbeddingModel
        ]

    async def cleanup(self) -> None:
        """Entlade alle Modelle und gib GPU Memory frei."""
        async with self._model_lock:
            for model_id in list(self._models.keys()):
                await self._unload_model(model_id)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()


# Singleton Instance
_embedding_factory: Optional[EmbeddingFactory] = None


def get_embedding_factory() -> EmbeddingFactory:
    """Factory Function fuer EmbeddingFactory."""
    global _embedding_factory
    if _embedding_factory is None:
        _embedding_factory = EmbeddingFactory.get_instance()
    return _embedding_factory
