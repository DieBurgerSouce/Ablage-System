# -*- coding: utf-8 -*-
"""
Model Pre-Loading Service fuer OCR Backends.

Laedt ML-Modelle beim Application-Startup vor um Cold-Start-Latenz zu vermeiden.
Die erste OCR-Anfrage wird dadurch deutlich schneller (10-30s weniger Wartezeit).

Features:
- Konfigurierbare Model-Auswahl
- GPU-aware Loading (prueft VRAM vor dem Laden)
- Background Loading mit Timeout
- Health-Status fuer Monitoring
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class PreloadStatus(str, Enum):
    """Status des Model Pre-Loading."""
    PENDING = "pending"
    LOADING = "loading"
    LOADED = "loaded"
    FAILED = "failed"
    SKIPPED = "skipped"


class PreloadConfig:
    """Konfiguration fuer Model Pre-Loading."""

    # Welche Modelle sollen vorgeladen werden?
    # Default: Nur leichtgewichtige Modelle die schnell laden
    DEFAULT_PRELOAD_MODELS = ["surya_docling"]

    # Mit GPU: Auch GPU-Modelle vorladen
    GPU_PRELOAD_MODELS = ["surya_gpu", "got_ocr"]

    # Timeout fuer einzelnes Model Loading (10 Minuten)
    MODEL_LOAD_TIMEOUT_SECONDS = 600

    # Minimaler freier VRAM (GB) vor GPU-Model-Loading
    MIN_FREE_VRAM_GB = 8.0

    # Ob Pre-Loading aktiviert ist
    ENABLED = True


class ModelPreloader:
    """
    Service zum Vorladen von OCR-Modellen beim Application-Startup.

    Verwendung:
        preloader = ModelPreloader()
        await preloader.preload_models(["surya_docling", "got_ocr"])
        status = preloader.get_status()
    """

    _instance: Optional["ModelPreloader"] = None

    def __init__(self):
        self._status: Dict[str, PreloadStatus] = {}
        self._load_times: Dict[str, float] = {}
        self._errors: Dict[str, str] = {}
        self._loaded_agents: Dict[str, Any] = {}
        self._preload_started: bool = False
        self._preload_completed: bool = False

    @classmethod
    def get_instance(cls) -> "ModelPreloader":
        """Singleton-Instanz holen."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def preload_models(
        self,
        models: Optional[List[str]] = None,
        include_gpu_models: bool = True,
        background: bool = False
    ) -> Dict[str, PreloadStatus]:
        """
        Lade OCR-Modelle vor.

        Args:
            models: Liste der zu ladenden Modelle (default: auto-select)
            include_gpu_models: Ob GPU-Modelle geladen werden sollen
            background: Ob im Background geladen werden soll

        Returns:
            Dict mit Status pro Modell
        """
        if not PreloadConfig.ENABLED:
            logger.info("model_preload_disabled")
            return {}

        self._preload_started = True

        # Bestimme zu ladende Modelle
        if models is None:
            models = list(PreloadConfig.DEFAULT_PRELOAD_MODELS)
            if include_gpu_models and self._check_gpu_available():
                models.extend(PreloadConfig.GPU_PRELOAD_MODELS)

        # Dedupliziere
        models = list(dict.fromkeys(models))

        logger.info(
            "model_preload_starting",
            models=models,
            include_gpu=include_gpu_models
        )

        if background:
            # Background-Loading: Nicht blockierend
            asyncio.create_task(self._preload_all(models))
            return {m: PreloadStatus.LOADING for m in models}
        else:
            # Synchron laden
            return await self._preload_all(models)

    async def _preload_all(self, models: List[str]) -> Dict[str, PreloadStatus]:
        """Lade alle angegebenen Modelle."""
        results = {}

        for model_name in models:
            self._status[model_name] = PreloadStatus.LOADING

            try:
                start_time = time.perf_counter()

                # Model-spezifisches Loading mit Timeout
                await asyncio.wait_for(
                    self._load_single_model(model_name),
                    timeout=PreloadConfig.MODEL_LOAD_TIMEOUT_SECONDS
                )

                load_time = time.perf_counter() - start_time
                self._load_times[model_name] = load_time
                self._status[model_name] = PreloadStatus.LOADED

                logger.info(
                    "model_preloaded",
                    model=model_name,
                    load_time_seconds=round(load_time, 2)
                )

                results[model_name] = PreloadStatus.LOADED

            except asyncio.TimeoutError:
                self._status[model_name] = PreloadStatus.FAILED
                self._errors[model_name] = f"Timeout nach {PreloadConfig.MODEL_LOAD_TIMEOUT_SECONDS}s"
                logger.error(
                    "model_preload_timeout",
                    model=model_name,
                    timeout_seconds=PreloadConfig.MODEL_LOAD_TIMEOUT_SECONDS
                )
                results[model_name] = PreloadStatus.FAILED

            except Exception as e:
                self._status[model_name] = PreloadStatus.FAILED
                self._errors[model_name] = str(e)
                logger.error(
                    "model_preload_failed",
                    model=model_name,
                    error_type=type(e).__name__,
                    error=str(e),
                    exc_info=True  # Include traceback for debugging
                )
                results[model_name] = PreloadStatus.FAILED

        self._preload_completed = True
        logger.info(
            "model_preload_complete",
            total=len(models),
            loaded=sum(1 for s in results.values() if s == PreloadStatus.LOADED),
            failed=sum(1 for s in results.values() if s == PreloadStatus.FAILED)
        )

        return results

    async def _load_single_model(self, model_name: str) -> None:
        """
        Lade ein einzelnes Model.

        Erstellt Agent-Instanz und ruft dessen Model-Loading auf.
        """
        agent = None

        try:
            if model_name == "surya_docling":
                from app.agents.ocr.surya_docling_agent import SuryaDoclingAgent
                agent = SuryaDoclingAgent()
                # Trigger model loading
                agent._load_models()

            elif model_name == "surya_gpu":
                # Pruefe VRAM vor GPU-Model
                if not self._check_vram_available(8.0):
                    self._status[model_name] = PreloadStatus.SKIPPED
                    logger.warning(
                        "model_preload_skipped_vram",
                        model=model_name,
                        required_vram_gb=8.0
                    )
                    return

                from app.agents.ocr.surya_gpu_agent import SuryaGPUAgent
                agent = SuryaGPUAgent()
                agent._load_models()

            elif model_name == "got_ocr":
                # Pruefe VRAM
                if not self._check_vram_available(10.0):
                    self._status[model_name] = PreloadStatus.SKIPPED
                    logger.warning(
                        "model_preload_skipped_vram",
                        model=model_name,
                        required_vram_gb=10.0
                    )
                    return

                from app.agents.ocr.got_ocr_agent import GOTOCRAgent
                agent = GOTOCRAgent()
                await agent._load_model("cuda")

            elif model_name == "deepseek":
                # DeepSeek braucht sehr viel VRAM (12-24GB)
                if not self._check_vram_available(12.0):
                    self._status[model_name] = PreloadStatus.SKIPPED
                    logger.warning(
                        "model_preload_skipped_vram",
                        model=model_name,
                        required_vram_gb=12.0
                    )
                    return

                from app.agents.ocr.deepseek_agent import DeepSeekAgent
                agent = DeepSeekAgent()
                await agent._load_model()

            else:
                logger.warning("model_preload_unknown", model=model_name)
                self._status[model_name] = PreloadStatus.SKIPPED
                return

            # Agent-Referenz behalten fuer spaetere Nutzung
            if agent:
                self._loaded_agents[model_name] = agent

        except ImportError as e:
            logger.warning(
                "model_preload_import_error",
                model=model_name,
                error=str(e)
            )
            self._status[model_name] = PreloadStatus.SKIPPED
            self._errors[model_name] = f"Import-Fehler: {e}"

    def _check_gpu_available(self) -> bool:
        """Pruefe ob GPU verfuegbar ist."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _check_vram_available(self, required_gb: float) -> bool:
        """Pruefe ob genuegend VRAM verfuegbar ist."""
        try:
            import torch
            if not torch.cuda.is_available():
                return False

            total_memory = torch.cuda.get_device_properties(0).total_memory
            allocated_memory = torch.cuda.memory_allocated(0)
            free_memory_gb = (total_memory - allocated_memory) / (1024 ** 3)

            return free_memory_gb >= required_gb

        except ImportError:
            # torch not available
            return False
        except Exception as e:
            logger.debug("vram_check_failed", error_type=type(e).__name__, error=str(e))
            return False

    def get_status(self) -> Dict[str, Any]:
        """
        Hole aktuellen Pre-Loading Status.

        Returns:
            Dict mit Status-Informationen
        """
        return {
            "enabled": PreloadConfig.ENABLED,
            "preload_started": self._preload_started,
            "preload_completed": self._preload_completed,
            "models": {
                name: {
                    "status": self._status.get(name, PreloadStatus.PENDING).value,
                    "load_time_seconds": self._load_times.get(name),
                    "error": self._errors.get(name),
                }
                for name in set(self._status.keys()) | set(self._load_times.keys())
            },
            "summary": {
                "total": len(self._status),
                "loaded": sum(1 for s in self._status.values() if s == PreloadStatus.LOADED),
                "failed": sum(1 for s in self._status.values() if s == PreloadStatus.FAILED),
                "skipped": sum(1 for s in self._status.values() if s == PreloadStatus.SKIPPED),
            }
        }

    def get_preloaded_agent(self, model_name: str) -> Optional[Any]:
        """
        Hole vorgeladenen Agent (falls verfuegbar).

        Args:
            model_name: Name des Models

        Returns:
            Agent-Instanz oder None
        """
        return self._loaded_agents.get(model_name)

    def is_model_loaded(self, model_name: str) -> bool:
        """Pruefe ob Model geladen ist."""
        return self._status.get(model_name) == PreloadStatus.LOADED

    async def cleanup(self) -> None:
        """Raeume vorgeladene Modelle auf."""
        for name, agent in self._loaded_agents.items():
            try:
                if hasattr(agent, "cleanup"):
                    await agent.cleanup()
                logger.debug("preloaded_agent_cleanup", model=name)
            except Exception as e:
                logger.warning(
                    "preloaded_agent_cleanup_error",
                    model=name,
                    error=str(e)
                )

        self._loaded_agents.clear()
        self._status.clear()
        self._load_times.clear()
        self._errors.clear()
        self._preload_started = False
        self._preload_completed = False


def get_model_preloader() -> ModelPreloader:
    """Hole Singleton-Instanz des ModelPreloader."""
    return ModelPreloader.get_instance()


async def preload_ocr_models(
    include_gpu: bool = True,
    background: bool = True
) -> Dict[str, PreloadStatus]:
    """
    Convenience-Funktion zum Vorladen der OCR-Modelle.

    Args:
        include_gpu: Ob GPU-Modelle geladen werden sollen
        background: Ob im Background geladen werden soll

    Returns:
        Dict mit Status pro Modell
    """
    preloader = get_model_preloader()
    return await preloader.preload_models(
        include_gpu_models=include_gpu,
        background=background
    )
