"""
OCR Backend Sub-Agent - Specialized backend interaction
Implementiert Backend-spezifische OCR-Verarbeitung mit GPU-Management
"""

from typing import List, Dict, Any, Optional
import structlog

logger = structlog.get_logger(__name__)

# Backend configuration with VRAM requirements
BACKEND_CONFIG = {
    "deepseek": {
        "vram_gb": 12,
        "batch_size": 8,
        "memory_per_image_mb": 450,
        "agent_class": "DeepSeekAgent",
        "agent_module": "app.agents.ocr.deepseek_agent"
    },
    "got_ocr": {
        "vram_gb": 10,
        "batch_size": 16,
        "memory_per_image_mb": 300,
        "agent_class": "GOTOCRAgent",
        "agent_module": "app.agents.ocr.got_ocr_agent"
    },
    "surya": {
        "vram_gb": 0,  # CPU-based
        "batch_size": 4,
        "memory_per_image_mb": 0,
        "agent_class": "SuryaDoclingAgent",
        "agent_module": "app.agents.ocr.surya_docling_agent"
    },
    "surya_gpu": {
        "vram_gb": 4,
        "batch_size": 8,
        "memory_per_image_mb": 200,
        "agent_class": "SuryaGPUAgent",
        "agent_module": "app.agents.ocr.surya_gpu_agent"
    },
    "donut": {
        "vram_gb": 6,
        "batch_size": 8,
        "memory_per_image_mb": 250,
        "agent_class": "DonutAgent",
        "agent_module": "app.agents.ocr.donut_agent"
    }
}


class OCRBackendAgent:
    """
    Sub-agent for interacting with specific OCR backends.

    Handles:
    - Model loading/unloading
    - Request batching
    - Backend-specific preprocessing
    - Result post-processing
    """

    def __init__(self, backend_name: str):
        self.backend_name = backend_name.lower()
        self.model = None
        self._config = BACKEND_CONFIG.get(self.backend_name)

        if not self._config:
            raise ValueError(
                f"Unbekanntes Backend: {backend_name}. "
                f"Verfuegbare Backends: {list(BACKEND_CONFIG.keys())}"
            )

        logger.info(
            "ocr_backend_agent_initialized",
            backend=self.backend_name,
            vram_required_gb=self._config["vram_gb"]
        )

    async def load_model(self):
        """
        Lazy load OCR model on first use.

        Dynamically imports and initializes the appropriate OCR agent
        based on backend_name. Uses GPU memory guard for GPU-based backends.
        """
        if self.model is not None:
            return

        logger.info(
            "loading_ocr_model",
            backend=self.backend_name,
            vram_required_gb=self._config["vram_gb"]
        )

        try:
            # Check GPU availability for GPU backends
            if self._config["vram_gb"] > 0:
                await self._check_gpu_availability()

            # Dynamic import based on backend
            module_name = self._config["agent_module"]
            class_name = self._config["agent_class"]

            import importlib
            module = importlib.import_module(module_name)
            agent_class = getattr(module, class_name)

            # Initialize the agent
            self.model = agent_class()

            # Ensure model is loaded (most agents have this method)
            if hasattr(self.model, '_ensure_model_loaded'):
                await self.model._ensure_model_loaded()
            elif hasattr(self.model, 'load_model'):
                await self.model.load_model()
            elif hasattr(self.model, 'initialize'):
                await self.model.initialize()

            logger.info(
                "ocr_model_loaded",
                backend=self.backend_name,
                agent_class=class_name
            )

        except ImportError as e:
            logger.error(
                "ocr_model_import_failed",
                backend=self.backend_name,
                error=str(e)
            )
            raise RuntimeError(
                f"OCR-Backend '{self.backend_name}' konnte nicht geladen werden: {e}"
            )
        except Exception as e:
            logger.error(
                "ocr_model_load_failed",
                backend=self.backend_name,
                error=str(e),
                exc_info=True
            )
            raise

    async def _check_gpu_availability(self):
        """Check if GPU has enough VRAM for this backend."""
        try:
            import torch
            if not torch.cuda.is_available():
                if self.backend_name != "surya":
                    logger.warning(
                        "gpu_not_available_fallback",
                        backend=self.backend_name
                    )
                return

            # Check available VRAM
            device = torch.cuda.current_device()
            total_memory = torch.cuda.get_device_properties(device).total_memory
            allocated = torch.cuda.memory_allocated(device)
            available_gb = (total_memory - allocated) / (1024 ** 3)

            required_gb = self._config["vram_gb"]

            if available_gb < required_gb:
                logger.warning(
                    "gpu_memory_low",
                    available_gb=round(available_gb, 2),
                    required_gb=required_gb,
                    backend=self.backend_name
                )
                # Try to free memory
                torch.cuda.empty_cache()

            logger.info(
                "gpu_memory_check",
                available_gb=round(available_gb, 2),
                required_gb=required_gb,
                backend=self.backend_name
            )

        except ImportError:
            logger.debug("pytorch_not_available")
        except Exception as e:
            logger.warning("gpu_check_failed", error=str(e))

    async def unload_model(self):
        """Unload model to free GPU memory."""
        if self.model is None:
            return

        try:
            # Call agent-specific cleanup if available
            if hasattr(self.model, 'cleanup'):
                await self.model.cleanup()
            elif hasattr(self.model, 'unload'):
                await self.model.unload()

            self.model = None

            # Free GPU memory
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass

            logger.info(
                "ocr_model_unloaded",
                backend=self.backend_name
            )

        except Exception as e:
            logger.error(
                "ocr_model_unload_failed",
                backend=self.backend_name,
                error=str(e)
            )

    async def process_batch(
        self,
        images: List[Any],
        batch_size: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Process images with backend-specific batching.

        Args:
            images: List of images (bytes, PIL.Image, or numpy arrays)
            batch_size: Override default batch size

        Returns:
            List of OCR results with text and confidence
        """
        await self.load_model()

        # Use backend-specific batch size
        batch_size = batch_size or self._config["batch_size"]

        logger.info(
            "ocr_batch_processing_start",
            backend=self.backend_name,
            image_count=len(images),
            batch_size=batch_size
        )

        results = []

        try:
            # Process in batches
            for i in range(0, len(images), batch_size):
                batch = images[i:i + batch_size]

                batch_results = await self._process_single_batch(batch)
                results.extend(batch_results)

                logger.debug(
                    "ocr_batch_completed",
                    batch_index=i // batch_size,
                    batch_size=len(batch),
                    results_count=len(batch_results)
                )

            logger.info(
                "ocr_batch_processing_complete",
                backend=self.backend_name,
                total_results=len(results)
            )

        except Exception as e:
            logger.error(
                "ocr_batch_processing_failed",
                backend=self.backend_name,
                error=str(e),
                exc_info=True
            )
            raise

        return results

    async def _process_single_batch(
        self,
        batch: List[Any]
    ) -> List[Dict[str, Any]]:
        """Process a single batch of images."""
        results = []

        for image in batch:
            try:
                # Use the agent's process method
                if hasattr(self.model, 'process_image'):
                    result = await self.model.process_image(image)
                elif hasattr(self.model, 'process'):
                    result = await self.model.process(image)
                elif hasattr(self.model, 'extract_text'):
                    text = await self.model.extract_text(image)
                    result = {"text": text, "confidence": 0.9}
                else:
                    raise RuntimeError(
                        f"Backend {self.backend_name} hat keine process-Methode"
                    )

                # Normalize result format
                if isinstance(result, str):
                    result = {"text": result, "confidence": 0.9}
                elif isinstance(result, dict):
                    if "text" not in result:
                        result["text"] = result.get("extracted_text", "")
                    if "confidence" not in result:
                        result["confidence"] = result.get("score", 0.9)

                result["backend"] = self.backend_name
                results.append(result)

            except Exception as e:
                logger.error(
                    "ocr_single_image_failed",
                    backend=self.backend_name,
                    error=str(e)
                )
                results.append({
                    "text": "",
                    "confidence": 0.0,
                    "error": str(e),
                    "backend": self.backend_name
                })

        return results

    def get_config(self) -> Dict[str, Any]:
        """Get backend configuration."""
        return {
            "backend": self.backend_name,
            "vram_gb": self._config["vram_gb"],
            "batch_size": self._config["batch_size"],
            "memory_per_image_mb": self._config["memory_per_image_mb"],
            "model_loaded": self.model is not None
        }


# See: Static_Knowledge/Skills/backend_selection_skill.yaml
