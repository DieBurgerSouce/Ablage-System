"""Surya OCR Agent with GPU acceleration for RTX 4080."""

import os
import io
import asyncio
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import torch
import structlog

from PIL import Image
import pypdfium2 as pdfium

# Surya imports
from surya.detection import batch_text_detection
from surya.recognition import batch_recognition
from surya.model.detection.segformer import load_model as load_det_model
from surya.model.detection.segformer import load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor

from app.agents.base import OCRAgent

logger = structlog.get_logger(__name__)


class SuryaGPUAgent(OCRAgent):
    """Surya OCR agent with GPU acceleration optimized for RTX 4080."""

    def __init__(self):
        """Initialize Surya OCR models with GPU support."""
        # Check GPU availability
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.dtype = torch.float16 if torch.cuda.is_available() else torch.float32

        # Set VRAM requirements based on GPU availability
        gpu_required = torch.cuda.is_available()
        vram_gb = 8 if gpu_required else 0  # Surya needs ~8GB VRAM

        super().__init__(name="surya_gpu_agent", gpu_required=gpu_required, vram_gb=vram_gb)

        # Models will be loaded on first use
        self._models_loaded = False
        self._det_model = None
        self._det_processor = None
        self._rec_model = None
        self._rec_processor = None

        # Language settings - German primary
        self.default_language = "de"

        # GPU optimization settings
        if torch.cuda.is_available():
            # Enable TensorFloat-32 for A100/RTX 30xx/40xx GPUs
            torch.backends.cuda.matmul.allow_tf32 = True
            torch.backends.cudnn.allow_tf32 = True
            # Enable cudNN autotuner for best performance
            torch.backends.cudnn.benchmark = True

            logger.info("gpu_detected", device=torch.cuda.get_device_name(0))
            logger.info("cuda_version", version=torch.version.cuda)
            logger.info("vram_available", vram_gb=round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1))
        else:
            logger.warning("no_gpu_detected_cpu_fallback")

        logger.info("surya_gpu_agent_initialized", device=str(self.device), dtype=str(self.dtype))

    def _load_models(self):
        """Load Surya models with GPU optimization."""
        if self._models_loaded:
            return

        try:
            logger.info("loading_surya_models", device=str(self.device))

            # Clear GPU cache before loading
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Load detection model (Surya functions don't take device/dtype directly)
            self._det_model = load_det_model()
            self._det_processor = load_det_processor()
            logger.info("detection_model_loaded")

            # Load recognition model
            self._rec_model = load_rec_model()
            self._rec_processor = load_rec_processor()
            logger.info("recognition_model_loaded")

            # Move models to GPU if available
            if torch.cuda.is_available():
                self._det_model = self._det_model.to(self.device).to(self.dtype)
                self._rec_model = self._rec_model.to(self.device).to(self.dtype)

                # Log VRAM usage
                allocated = torch.cuda.memory_allocated() / 1024**3
                logger.info("models_loaded_vram", vram_used_gb=round(allocated, 1))

            self._models_loaded = True
            logger.info("All Surya models loaded successfully with GPU optimization")

        except Exception as e:
            logger.error("surya_models_load_failed", error=str(e))
            # Try CPU fallback
            if torch.cuda.is_available():
                logger.warning("GPU loading failed, falling back to CPU")
                self.device = torch.device("cpu")
                self.dtype = torch.float32
                self._load_models_cpu()
            else:
                raise

    def _load_models_cpu(self):
        """Fallback CPU model loading."""
        try:
            logger.info("Loading Surya models on CPU (fallback)...")

            # Load models (Surya functions don't take device/dtype directly)
            self._det_model = load_det_model()
            self._det_processor = load_det_processor()

            self._rec_model = load_rec_model()
            self._rec_processor = load_rec_processor()

            self._models_loaded = True
            logger.info("Surya models loaded on CPU (fallback mode)")

        except Exception as e:
            logger.error("cpu_fallback_failed", error=str(e))
            raise

    def _load_image(self, image_path: str) -> List[Image.Image]:
        """Load image(s) from file path, handling both PDFs and images."""
        path = Path(image_path)
        images = []

        if not path.exists():
            raise FileNotFoundError(f"File not found: {image_path}")

        if path.suffix.lower() == '.pdf':
            # Handle PDF files
            logger.info("processing_pdf", path=image_path)
            try:
                pdf = pdfium.PdfDocument(image_path)
                for page_num in range(len(pdf)):
                    page = pdf[page_num]
                    # Render at 300 DPI for good quality
                    pil_image = page.render(scale=300/72).to_pil()
                    images.append(pil_image)
                    logger.debug("pdf_page_loaded", page=page_num + 1, total=len(pdf))
                pdf.close()
            except Exception as e:
                logger.error("pdf_load_failed", error=str(e))
                raise
        else:
            # Handle image files (PNG, JPG, etc.)
            logger.info("processing_image", path=image_path)
            try:
                image = Image.open(image_path)
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(image)
            except Exception as e:
                logger.error("image_load_failed", error=str(e))
                raise

        return images

    def _process_single_image(self, image: Image.Image, language: str) -> Dict[str, Any]:
        """Process a single image with GPU-optimized text detection and recognition."""
        # Ensure models are loaded
        self._load_models()

        # Clear GPU cache for optimal memory usage
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Text detection with GPU acceleration
        det_predictions = batch_text_detection(
            [image],
            self._det_model,
            self._det_processor
        )

        # Process each text region INDIVIDUALLY with its own language code
        # This is the critical fix for the Surya language bug
        text_lines = []
        confidences = []

        for bbox in det_predictions[0].bboxes:
            # Crop the text region
            x1, y1, x2, y2 = bbox.bbox
            cropped = image.crop((x1, y1, x2, y2))

            # Recognition for SINGLE region with SINGLE language code
            # This avoids the AssertionError: len(langs) != len(texts)
            # batch_recognition returns a tuple: (texts_list, confidences_list)
            rec_result = batch_recognition(
                [cropped],      # Single image slice
                [language],     # Single language code matching the single image
                self._rec_model,
                self._rec_processor
            )

            # Unpack the tuple
            if isinstance(rec_result, tuple) and len(rec_result) == 2:
                rec_preds, conf_scores = rec_result
            else:
                # Fallback if format changes
                rec_preds = rec_result if isinstance(rec_result, list) else [rec_result]
                conf_scores = []

            if rec_preds and len(rec_preds) > 0:
                # rec_preds[0] is directly a string, not an object with .text
                text = rec_preds[0] if isinstance(rec_preds[0], str) else str(rec_preds[0])

                if text:
                    text_lines.append(text)
                    if conf_scores and len(conf_scores) > 0:
                        confidences.append(conf_scores[0])

        # Log GPU memory usage
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1024**3
            max_allocated = torch.cuda.max_memory_allocated() / 1024**3
            logger.debug("gpu_memory", current_gb=round(allocated, 1), peak_gb=round(max_allocated, 1))

        # Combine all text lines
        full_text = "\n".join(text_lines)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0

        # Check for German characters
        german_chars = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
        found_german = [char for char in german_chars if char in full_text]

        if found_german:
            logger.info("german_chars_detected", chars=found_german)

        return {
            "text": full_text,
            "confidence": avg_confidence,
            "text_regions": len(text_lines),
            "german_chars_found": found_german
        }

    async def process(
        self,
        input_data: Union[str, Dict[str, Any]],
        language: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Process document with GPU-accelerated OCR."""
        try:
            # Handle both string path and dict input
            if isinstance(input_data, dict):
                image_path = input_data.get('image_path')
                if not language:
                    language = input_data.get('language', self.default_language)
            else:
                image_path = input_data

            # Use German as default language
            if not language:
                language = self.default_language

            # Ensure image_path is a string, not dict
            if not isinstance(image_path, str):
                raise ValueError(f"Expected string path, got {type(image_path)}: {image_path}")

            # Load images from file
            images = self._load_image(image_path)
            logger.info("pages_loaded_for_ocr", count=len(images))

            # Process each page with GPU optimization
            all_text = []
            all_confidences = []

            for i, image in enumerate(images):
                logger.info("processing_page", page=i+1, total=len(images))

                # GPU memory management for multi-page documents
                if torch.cuda.is_available() and i > 0:
                    torch.cuda.empty_cache()

                result = self._process_single_image(image, language)
                all_text.append(result["text"])
                all_confidences.append(result["confidence"])

            # Combine results
            full_text = "\n\n".join(all_text)
            avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0

            # Final GPU memory cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                final_memory = torch.cuda.memory_allocated() / 1024**3
                logger.info("processing_complete", final_vram_gb=round(final_memory, 1))

            logger.info("ocr_completed", chars_extracted=len(full_text), pages=len(images))

            return {
                "success": True,
                "text": full_text,
                "confidence": avg_confidence,
                "page_count": len(images),
                "backend": "surya_gpu",
                "device": str(self.device),
                "metadata": {
                    "language": language,
                    "gpu_accelerated": torch.cuda.is_available(),
                    "dtype": str(self.dtype)
                }
            }

        except Exception as e:
            logger.error("ocr_processing_failed", error=str(e))
            # GPU memory cleanup on error
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            return {
                "success": False,
                "error": str(e),
                "backend": "surya_gpu",
                "device": str(self.device)
            }

    def get_status(self) -> Dict[str, Any]:
        """Get agent status including GPU information."""
        status = super().get_status()

        # Add GPU-specific status
        if torch.cuda.is_available():
            status["gpu_info"] = {
                "device_name": torch.cuda.get_device_name(0),
                "cuda_version": torch.version.cuda,
                "total_vram_gb": torch.cuda.get_device_properties(0).total_memory / 1024**3,
                "allocated_vram_gb": torch.cuda.memory_allocated() / 1024**3,
                "cached_vram_gb": torch.cuda.memory_reserved() / 1024**3,
                "tf32_enabled": torch.backends.cuda.matmul.allow_tf32,
                "cudnn_benchmark": torch.backends.cudnn.benchmark
            }
        else:
            status["gpu_info"] = {"available": False}

        return status

    async def cleanup(self):
        """Clean up resources and free GPU memory."""
        logger.info("Cleaning up SuryaGPUAgent resources...")

        # Clear model references
        self._det_model = None
        self._rec_model = None
        self._det_processor = None
        self._rec_processor = None
        self._models_loaded = False

        # Force GPU memory cleanup
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("GPU memory cleared")

        await super().cleanup()