"""
DeepSeek-Janus-Pro OCR Agent.

Specialized agent for complex document layouts using DeepSeek's
multimodal vision-language model.

Best for:
- Complex table structures
- Handwritten text and Fraktur fonts
- Mixed German/English documents
- Documents requiring semantic understanding
"""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
from PIL import Image

from app.agents.base import AgentResourceError, OCRAgent
from app.gpu_manager import GPUManager


class DeepSeekAgent(OCRAgent):
    """
    DeepSeek-Janus-Pro OCR processing agent.

    Requires:
    - 12GB VRAM
    - CUDA-capable GPU
    - DeepSeek-Janus-Pro model weights
    """

    # Model configuration
    MODEL_NAME = "deepseek-ai/Janus-Pro-1B"
    VRAM_REQUIRED_GB = 12
    MAX_BATCH_SIZE = 4

    def __init__(self):
        super().__init__(
            name="deepseek_ocr_agent",
            gpu_required=True,
            vram_gb=self.VRAM_REQUIRED_GB,
        )
        self.gpu_manager = GPUManager()
        self.model = None
        self.processor = None
        self._model_loaded = False

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process document with DeepSeek OCR.

        Input:
            document_id: str - Document identifier
            image_path: str - Path to image file
            language: str - Primary language (default: "de")
            options: dict - Additional processing options

        Returns:
            text: str - Extracted text
            confidence: float - Overall confidence score
            layout: dict - Detected layout structure
            entities: list - Extracted business entities
        """
        self.validate_input(input_data, ["document_id", "image_path"])

        document_id = input_data["document_id"]
        image_path = Path(input_data["image_path"])
        language = input_data.get("language", "de")
        options = input_data.get("options", {})

        self.logger.info(
            "deepseek_processing_started",
            document_id=document_id,
            image_path=str(image_path),
            language=language,
        )

        # Allocate GPU resources
        await self._ensure_gpu_allocated()

        # Load model if not already loaded
        await self._load_model()

        try:
            # Load and preprocess image
            image = await self._load_image(image_path)

            # Run OCR inference
            ocr_result = await self._run_inference(image, language, options)

            # Post-process results
            result = await self._postprocess_result(ocr_result, options)

            self.logger.info(
                "deepseek_processing_completed",
                document_id=document_id,
                text_length=len(result["text"]),
                confidence=result["confidence"],
                entities_found=len(result.get("entities", [])),
            )

            return result

        except torch.cuda.OutOfMemoryError as e:
            self.logger.error(
                "deepseek_gpu_oom",
                document_id=document_id,
                error=str(e),
            )
            # Try to recover
            await self._handle_gpu_oom()
            raise AgentResourceError(f"GPU out of memory: {e}")

        except Exception as e:
            self.logger.error(
                "deepseek_processing_error",
                document_id=document_id,
                error=str(e),
                exc_info=True,
            )
            raise

        finally:
            # Cleanup GPU resources if needed
            await self._cleanup_gpu_resources()

    async def _ensure_gpu_allocated(self) -> None:
        """Ensure GPU resources are allocated for DeepSeek."""
        allocation = self.gpu_manager.allocate_for_backend("deepseek")

        if not allocation["success"]:
            raise AgentResourceError(
                f"Failed to allocate GPU for DeepSeek: {allocation.get('reason')}"
            )

        if allocation.get("mode") == "cpu":
            self.logger.warning(
                "deepseek_fallback_cpu",
                reason="GPU not available, falling back to CPU (slow)",
            )

    async def _load_model(self) -> None:
        """Load DeepSeek model and processor."""
        if self._model_loaded:
            return

        self.logger.info("deepseek_loading_model", model_name=self.MODEL_NAME)

        try:
            # Import DeepSeek dependencies (lazy import)
            from transformers import AutoModelForVision2Seq, AutoProcessor

            # Load processor
            self.processor = AutoProcessor.from_pretrained(
                self.MODEL_NAME, trust_remote_code=True
            )

            # Load model to GPU
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = AutoModelForVision2Seq.from_pretrained(
                self.MODEL_NAME,
                trust_remote_code=True,
                torch_dtype=torch.bfloat16 if device == "cuda" else torch.float32,
            ).to(device)

            self.model.eval()  # Inference mode

            # Warm-up inference (compile CUDA kernels)
            if device == "cuda":
                dummy_image = Image.new("RGB", (224, 224), color="white")
                _ = await self._run_inference(
                    dummy_image, language="de", options={"warmup": True}
                )
                torch.cuda.empty_cache()

            self._model_loaded = True
            self.logger.info("deepseek_model_loaded", device=device)

        except Exception as e:
            self.logger.error("deepseek_model_load_failed", error=str(e), exc_info=True)
            raise AgentResourceError(f"Failed to load DeepSeek model: {e}")

    async def _load_image(self, image_path: Path) -> Image.Image:
        """Load and validate image."""
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        try:
            # Use context manager to ensure file handle is closed
            with Image.open(image_path) as img:
                # Convert and create in-memory copy (detaches from file handle)
                image = img.convert("RGB").copy()

            self.logger.debug(
                "image_loaded",
                path=str(image_path),
                size=image.size,
                mode=image.mode,
            )
            return image
        except Exception as e:
            raise ValueError(f"Failed to load image: {e}")

    async def _run_inference(
        self, image: Image.Image, language: str, options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run DeepSeek OCR inference."""
        # Prepare prompt for German OCR
        prompt = self._build_prompt(language, options)

        # Process image and text
        inputs = self.processor(
            text=prompt, images=image, return_tensors="pt"
        ).to(self.model.device)

        # Run inference
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=options.get("max_tokens", 2048),
                temperature=options.get("temperature", 0.1),
                do_sample=False,  # Deterministic for OCR
                pad_token_id=self.processor.tokenizer.eos_token_id,
            )

        # Decode output
        generated_text = self.processor.batch_decode(
            outputs, skip_special_tokens=True
        )[0]

        # Extract confidence (placeholder - DeepSeek doesn't provide confidence)
        confidence = 0.95  # Assume high confidence for DeepSeek

        return {
            "text": generated_text,
            "confidence": confidence,
            "model": self.MODEL_NAME,
        }

    def _build_prompt(self, language: str, options: Dict[str, Any]) -> str:
        """Build OCR prompt for DeepSeek."""
        if language == "de":
            base_prompt = """
            Extrahiere den gesamten Text aus diesem Bild.

            Wichtig:
            - Bewahre die Formatierung (Absätze, Listen)
            - Erkenne deutsche Umlaute korrekt (ä, ö, ü, ß)
            - Erkenne Tabellen und strukturiere sie
            - Extrahiere Datum, Währung, IBAN, USt-IdNr. wenn vorhanden

            Text:
            """
        else:
            base_prompt = """
            Extract all text from this image.

            Important:
            - Preserve formatting (paragraphs, lists)
            - Recognize tables and structure them
            - Extract dates, currency, IBAN, VAT ID if present

            Text:
            """

        # Add task-specific instructions
        if options.get("extract_tables"):
            base_prompt += "\nFocus on accurately extracting table structures."

        if options.get("extract_handwriting"):
            base_prompt += "\nPay special attention to handwritten text."

        return base_prompt.strip()

    async def _postprocess_result(
        self, ocr_result: Dict[str, Any], options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Post-process OCR results."""
        text = ocr_result["text"]

        # Basic text cleaning
        text = text.strip()

        # Extract structured data (placeholder - would use NER, regex)
        entities = []
        if options.get("extract_entities"):
            entities = self._extract_entities(text)

        # Detect layout structure (placeholder)
        layout = {}
        if options.get("detect_layout"):
            layout = self._detect_layout(text)

        return {
            "text": text,
            "confidence": ocr_result["confidence"],
            "entities": entities,
            "layout": layout,
            "model": ocr_result["model"],
        }

    def _extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extract business entities from text (placeholder)."""
        # TODO: Implement with German NER model (spaCy de_core_news_lg)
        return []

    def _detect_layout(self, text: str) -> Dict[str, Any]:
        """Detect document layout structure (placeholder)."""
        # TODO: Implement layout analysis
        return {"type": "unknown", "sections": []}

    async def _handle_gpu_oom(self) -> None:
        """Handle GPU out-of-memory error."""
        self.logger.warning("deepseek_gpu_oom_recovery", action="clearing_cache")

        # Clear CUDA cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Unload model to free memory
        if self.model is not None:
            del self.model
            self.model = None
            self._model_loaded = False

        # Notify GPU manager
        recovery = self.gpu_manager.handle_oom_error()
        self.logger.info("deepseek_gpu_oom_recovered", recovery_info=recovery)

    async def _cleanup_gpu_resources(self) -> None:
        """Cleanup GPU resources after processing."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    async def process_batch(
        self, documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Process multiple documents in batch for better GPU utilization.

        Args:
            documents: List of input documents

        Returns:
            List of OCR results
        """
        batch_size = min(len(documents), self.MAX_BATCH_SIZE)
        batch_size = min(
            batch_size, self.gpu_manager.get_optimal_batch_size("deepseek")
        )

        self.logger.info(
            "deepseek_batch_processing",
            total_documents=len(documents),
            batch_size=batch_size,
        )

        results = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            # Process batch concurrently
            batch_results = await asyncio.gather(
                *[self.process(doc) for doc in batch], return_exceptions=True
            )

            for result in batch_results:
                if isinstance(result, Exception):
                    self.logger.error(
                        "deepseek_batch_item_failed", error=str(result)
                    )
                    results.append({"error": str(result)})
                else:
                    results.append(result["result"])

        return results
