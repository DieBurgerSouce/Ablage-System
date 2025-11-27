# -*- coding: utf-8 -*-
"""
Donut OCR Agent - Document Understanding Transformer.

Multilinguale OCR mit Transformer-basiertem End-to-End Ansatz:
- 100+ Sprachen unterstützt (inkl. Kyrillisch)
- Dokumentstruktur-Verständnis
- Formulare und Tabellen
- SafeTensors für sicheres Laden

Best for:
- Multilinguale Dokumente (DE/PL/RU/+)
- Strukturierte Formulare
- Dokumente mit komplexem Layout
- Non-Latin Schriftsysteme (Kyrillisch)

Feinpoliert und durchdacht - Multilinguale OCR für globale Dokumente.
"""

import asyncio
import structlog
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from app.agents.base import AgentResourceError, OCRAgent
from app.gpu_manager import GPUManager

logger = structlog.get_logger(__name__)

# Check for required dependencies
TRANSFORMERS_AVAILABLE = False
TORCH_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    logger.warning("PyTorch nicht verfügbar")

try:
    from transformers import (
        DonutProcessor,
        VisionEncoderDecoderModel,
    )
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    logger.warning(
        "Transformers nicht verfügbar für Donut. "
        "Installieren mit: pip install transformers>=4.36.0"
    )


class DonutOCRAgent(OCRAgent):
    """
    Donut (Document Understanding Transformer) OCR Agent.

    End-to-End Document Understanding ohne separate Text-Erkennung:
    - Vision Encoder + Text Decoder Architektur
    - Multilinguale Unterstützung (100+ Sprachen)
    - Dokumentstruktur-Verständnis
    - SafeTensors für sichere Modell-Persistenz

    Requires:
    - ~8GB VRAM (GPU) oder CPU-Fallback
    - transformers >= 4.36.0
    - PyTorch mit CUDA (optional)
    """

    # Model configuration
    # Base model: naver-clova-ix/donut-base
    # Fine-tuned variants available:
    # - naver-clova-ix/donut-base-finetuned-docvqa (Document QA)
    # - naver-clova-ix/donut-base-finetuned-cord-v2 (Receipt parsing)
    MODEL_NAME = "naver-clova-ix/donut-base"
    VRAM_REQUIRED_GB = 8
    MAX_BATCH_SIZE = 8

    # Supported languages (subset of 100+)
    SUPPORTED_LANGUAGES = [
        "de", "en", "pl", "ru", "uk", "cs",  # Priority languages
        "fr", "it", "es", "pt", "nl",  # Western European
        "ja", "ko", "zh",  # East Asian
    ]

    # Task prompts for different document types
    TASK_PROMPTS = {
        "ocr": "<s_cord-v2>",  # General OCR
        "docvqa": "<s_docvqa><s_question>{question}</s_question><s_answer>",
        "classification": "<s_classification>",
        "parsing": "<s_cord-v2>",  # Structured parsing
    }

    def __init__(
        self,
        model_name: Optional[str] = None,
        use_gpu: bool = True,
        use_safetensors: bool = True,
    ) -> None:
        """
        Initialize Donut OCR Agent.

        Args:
            model_name: HuggingFace model name (default: donut-base)
            use_gpu: Whether to use GPU if available
            use_safetensors: Use SafeTensors for secure model loading
        """
        super().__init__(
            name="donut_ocr_agent",
            gpu_required=False,  # Can run on CPU
            vram_gb=self.VRAM_REQUIRED_GB if use_gpu else 0,
        )

        self.model_name = model_name or self.MODEL_NAME
        self.use_gpu = use_gpu
        self.use_safetensors = use_safetensors

        self.gpu_manager = GPUManager()
        self.model = None
        self.processor = None
        self._model_loaded = False
        self._device = None

        # Validate dependencies
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "Donut benötigt transformers>=4.36.0. "
                "Installieren mit: pip install transformers>=4.36.0 sentencepiece"
            )

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process document with Donut OCR.

        Input:
            document_id: str - Document identifier
            image_path: str - Path to image file
            language: str - Language hint (default: "auto")
            task: str - Task type (ocr, docvqa, parsing)
            question: str - Question for docvqa task
            options: dict - Additional options

        Returns:
            text: str - Extracted text
            confidence: float - Confidence score
            structure: dict - Document structure
            language_detected: str - Detected language
        """
        self.validate_input(input_data, ["document_id", "image_path"])

        document_id = input_data["document_id"]
        image_path = Path(input_data["image_path"])
        language = input_data.get("language", "auto")
        task = input_data.get("task", "ocr")
        options = input_data.get("options", {})

        self.logger.info(
            "donut_processing_started",
            document_id=document_id,
            image_path=str(image_path),
            language=language,
            task=task,
        )

        start_time = asyncio.get_event_loop().time()

        try:
            # Load model if needed
            await self._ensure_model_loaded()

            # Load image
            image = await self._load_image(image_path)

            # Run inference
            result = await self._run_inference(image, task, language, options)

            # Calculate processing time
            processing_time = asyncio.get_event_loop().time() - start_time

            # Build response
            response = {
                "text": result.get("text", ""),
                "confidence": result.get("confidence", 0.0),
                "structure": result.get("structure", {}),
                "language_detected": result.get("language", language),
                "task": task,
                "model": self.model_name,
                "processing_time_ms": int(processing_time * 1000),
                "device": str(self._device),
            }

            self.logger.info(
                "donut_processing_completed",
                document_id=document_id,
                text_length=len(response["text"]),
                confidence=response["confidence"],
                processing_time_ms=response["processing_time_ms"],
            )

            return response

        except Exception as e:
            self.logger.error(
                "donut_processing_error",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            raise

    async def _ensure_model_loaded(self) -> None:
        """Ensure model is loaded and ready."""
        if self._model_loaded:
            return

        self.logger.info("lade_donut_modell", model=self.model_name)

        # Determine device
        if self.use_gpu and TORCH_AVAILABLE and torch.cuda.is_available():
            # Check GPU allocation
            allocation = self.gpu_manager.allocate_for_backend("donut")
            if allocation.get("success"):
                self._device = torch.device("cuda")
                self.logger.info("Donut auf GPU geladen")
            else:
                self._device = torch.device("cpu")
                self.logger.warning("GPU nicht verfügbar, nutze CPU")
        else:
            self._device = torch.device("cpu")
            self.logger.info("Donut auf CPU geladen")

        # Load processor and model
        await asyncio.to_thread(self._load_model_sync)

        self._model_loaded = True

    def _load_model_sync(self) -> None:
        """Synchronous model loading (run in thread)."""
        from transformers import DonutProcessor, VisionEncoderDecoderModel

        # Load processor
        self.processor = DonutProcessor.from_pretrained(
            self.model_name,
            use_fast=True,
        )

        # Load model with SafeTensors if available
        try:
            self.model = VisionEncoderDecoderModel.from_pretrained(
                self.model_name,
                use_safetensors=self.use_safetensors,
            )
        except Exception as e:
            # Fallback to standard loading
            logger.warning("safetensors_unavailable_fallback", error=str(e))
            self.model = VisionEncoderDecoderModel.from_pretrained(
                self.model_name,
            )

        # Move to device
        self.model.to(self._device)
        self.model.eval()

        logger.info("donut_modell_geladen", device=str(self._device))

    async def _load_image(self, image_path: Path) -> Image.Image:
        """Load and preprocess image."""
        def _load() -> Image.Image:
            if not image_path.exists():
                raise FileNotFoundError(f"Bild nicht gefunden: {image_path}")

            image = Image.open(image_path).convert("RGB")

            # Resize if too large (Donut max input size)
            max_size = 1920
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, Image.Resampling.LANCZOS)

            return image

        return await asyncio.to_thread(_load)

    async def _run_inference(
        self,
        image: Image.Image,
        task: str,
        language: str,
        options: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run Donut inference."""
        def _inference() -> Dict[str, Any]:
            import torch

            # Get task prompt
            prompt = self.TASK_PROMPTS.get(task, self.TASK_PROMPTS["ocr"])

            # Handle docvqa task
            if task == "docvqa" and "question" in options:
                prompt = prompt.format(question=options["question"])

            # Prepare inputs
            pixel_values = self.processor(
                image,
                return_tensors="pt",
            ).pixel_values.to(self._device)

            # Prepare decoder input
            decoder_input_ids = self.processor.tokenizer(
                prompt,
                add_special_tokens=False,
                return_tensors="pt",
            ).input_ids.to(self._device)

            # Generate
            with torch.no_grad():
                outputs = self.model.generate(
                    pixel_values,
                    decoder_input_ids=decoder_input_ids,
                    max_length=self.model.decoder.config.max_position_embeddings,
                    early_stopping=True,
                    pad_token_id=self.processor.tokenizer.pad_token_id,
                    eos_token_id=self.processor.tokenizer.eos_token_id,
                    use_cache=True,
                    num_beams=1,  # Greedy for speed
                    bad_words_ids=[[self.processor.tokenizer.unk_token_id]],
                    return_dict_in_generate=True,
                    output_scores=True,
                )

            # Decode output
            sequence = outputs.sequences[0]
            text = self.processor.batch_decode([sequence])[0]

            # Clean up text
            text = text.replace(self.processor.tokenizer.eos_token, "")
            text = text.replace(self.processor.tokenizer.pad_token, "")

            # Remove task tokens
            for token in self.TASK_PROMPTS.values():
                base_token = token.split("{")[0]  # Handle format strings
                text = text.replace(base_token, "")

            text = text.strip()

            # Calculate confidence from scores
            confidence = self._calculate_confidence(outputs)

            # Parse structure if available
            structure = self._parse_structure(text, task)

            return {
                "text": text,
                "confidence": confidence,
                "structure": structure,
                "language": language if language != "auto" else "detected",
            }

        return await asyncio.to_thread(_inference)

    def _calculate_confidence(self, outputs: Any) -> float:
        """Calculate confidence score from model outputs."""
        try:
            import torch

            if hasattr(outputs, "scores") and outputs.scores:
                # Average log probability
                scores = torch.stack(outputs.scores, dim=0)
                probs = torch.softmax(scores, dim=-1)
                max_probs = probs.max(dim=-1).values
                confidence = max_probs.mean().item()
                return min(max(confidence, 0.0), 1.0)
        except Exception:
            pass

        return 0.85  # Default confidence

    def _parse_structure(self, text: str, task: str) -> Dict[str, Any]:
        """Parse structured output from model."""
        structure: Dict[str, Any] = {"raw_output": text}

        if task == "parsing":
            # Try to parse as JSON-like structure
            try:
                import json
                import re

                # Look for JSON-like patterns
                json_match = re.search(r"\{.*\}", text, re.DOTALL)
                if json_match:
                    structure["parsed"] = json.loads(json_match.group())
            except (json.JSONDecodeError, AttributeError):
                pass

        return structure

    async def health_check(self) -> bool:
        """Check if Donut agent is healthy."""
        if not TRANSFORMERS_AVAILABLE:
            return False

        if not self._model_loaded:
            try:
                await self._ensure_model_loaded()
            except Exception as e:
                logger.error("donut_health_check_failed", error=str(e))
                return False

        return self.model is not None and self.processor is not None

    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages."""
        return self.SUPPORTED_LANGUAGES

    def is_language_supported(self, language: str) -> bool:
        """Check if a language is explicitly supported."""
        return language.lower() in self.SUPPORTED_LANGUAGES

    async def process_batch(
        self,
        images: List[Path],
        task: str = "ocr",
        language: str = "auto",
    ) -> List[Dict[str, Any]]:
        """
        Process multiple images in batch.

        Args:
            images: List of image paths
            task: Task type
            language: Language hint

        Returns:
            List of results
        """
        results = []

        # Process in batches
        batch_size = min(self.MAX_BATCH_SIZE, len(images))

        for i in range(0, len(images), batch_size):
            batch = images[i : i + batch_size]
            batch_results = await asyncio.gather(
                *[
                    self.process({
                        "document_id": f"batch_{i+j}",
                        "image_path": str(img),
                        "task": task,
                        "language": language,
                    })
                    for j, img in enumerate(batch)
                ]
            )
            results.extend(batch_results)

        return results

    def unload_model(self) -> None:
        """Unload model to free memory."""
        if self.model is not None:
            del self.model
            self.model = None

        if self.processor is not None:
            del self.processor
            self.processor = None

        if TORCH_AVAILABLE:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        self._model_loaded = False
        self.gpu_manager.release("donut")

        logger.info("Donut-Modell entladen")


# Convenience function
def is_donut_available() -> bool:
    """Check if Donut is available."""
    return TRANSFORMERS_AVAILABLE and TORCH_AVAILABLE
