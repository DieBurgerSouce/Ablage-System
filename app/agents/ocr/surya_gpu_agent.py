"""Surya OCR Agent with GPU acceleration for RTX 4080.

This version uses the new surya-ocr 0.17.0 API with DetectionPredictor,
FoundationPredictor, and RecognitionPredictor classes with GPU support.
"""

import asyncio
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import structlog

import torch
from PIL import Image
import pypdfium2 as pdfium

from app.agents.base import OCRAgent, OCRResult

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
        self._det_predictor = None
        self._rec_predictor = None
        self._foundation_predictor = None
        self._task_name = None

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

            # Import new surya 0.17.0 API
            from surya.detection import DetectionPredictor
            from surya.recognition import RecognitionPredictor
            from surya.foundation import FoundationPredictor
            from surya.common.surya.schema import TaskNames

            # Store task name for OCR
            self._task_name = TaskNames.ocr_with_boxes

            # Load foundation predictor (required by recognition)
            # Surya 0.17.0 automatically uses GPU if available
            self._foundation_predictor = FoundationPredictor()
            logger.info("foundation_predictor_loaded")

            # Load detection predictor
            self._det_predictor = DetectionPredictor()
            logger.info("detection_predictor_loaded")

            # Load recognition predictor with foundation
            self._rec_predictor = RecognitionPredictor(self._foundation_predictor)
            logger.info("recognition_predictor_loaded")

            # Log VRAM usage
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                logger.info("models_loaded_vram", vram_used_gb=round(allocated, 1))

            self._models_loaded = True
            logger.info("All Surya 0.17.0 models loaded successfully with GPU optimization")

        except Exception as e:
            logger.error("surya_models_load_failed", error=str(e))
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

        try:
            # Run OCR using the callable RecognitionPredictor
            predictions = self._rec_predictor(
                [image],
                task_names=[self._task_name],
                det_predictor=self._det_predictor,
            )

            text_lines = []
            confidences = []

            # Process recognition results
            if predictions and len(predictions) > 0:
                pred = predictions[0]

                # Extract text lines from OCRResult
                if hasattr(pred, 'text_lines'):
                    for line in pred.text_lines:
                        text = line.text if hasattr(line, 'text') else str(line)
                        confidence = line.confidence if hasattr(line, 'confidence') else 0.0

                        if text and text.strip():
                            text_lines.append(text)
                            confidences.append(float(confidence))

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

        except Exception as e:
            logger.error("image_processing_failed", error=str(e))
            return {"text": "", "confidence": 0.0, "text_regions": 0, "german_chars_found": [], "error": str(e)}

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
            pages_data = []  # NEW: Page-level data

            for i, image in enumerate(images):
                logger.info("processing_page", page=i+1, total=len(images))

                # GPU memory management for multi-page documents
                if torch.cuda.is_available() and i > 0:
                    torch.cuda.empty_cache()

                result = self._process_single_image(image, language)
                all_text.append(result["text"])
                all_confidences.append(result["confidence"])

                # NEW: Collect page-level confidence data
                page_data = {
                    "page_number": i + 1,
                    "text": result["text"],
                    "page_confidence": round(result["confidence"], 3),
                    "text_regions": result.get("text_regions", 0),
                    "german_chars_found": result.get("german_chars_found", []),
                }
                pages_data.append(page_data)

            # Combine results
            full_text = "\n\n".join(all_text)
            avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0

            # NEW: Calculate confidence statistics
            min_page_confidence = min(all_confidences) if all_confidences else 0.0
            max_page_confidence = max(all_confidences) if all_confidences else 0.0
            low_confidence_pages = [p["page_number"] for p in pages_data if p["page_confidence"] < 0.7]

            # Final GPU memory cleanup
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                final_memory = torch.cuda.memory_allocated() / 1024**3
                logger.info("processing_complete", final_vram_gb=round(final_memory, 1))

            logger.info("ocr_completed", chars_extracted=len(full_text), pages=len(images))

            # Pruefe auf deutsche Zeichen
            has_umlauts = any(c in full_text for c in "äöüÄÖÜß")

            # Erstelle standardisiertes OCRResult
            result = self.create_success_result(
                text=full_text,
                confidence=avg_confidence,
                processing_time_ms=0,  # Could add timing if needed
                page_count=len(images),
                language=language,
                pages=pages_data,
                has_umlauts=has_umlauts,
            )

            return result.to_dict()

        except Exception as e:
            logger.error("ocr_processing_failed", error=str(e))
            # GPU memory cleanup on error
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Erstelle standardisiertes Fehler-Result
            result = self.create_error_result(
                error=str(e),
                error_code="SURYA_OCR_ERROR",
            )
            return result.to_dict()

    def get_status(self) -> Dict[str, Any]:
        """Get agent status including GPU information."""
        status = super().get_status()

        # Add version info
        status["model_version"] = "surya-ocr-0.17.0"

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
        self._det_predictor = None
        self._rec_predictor = None
        self._foundation_predictor = None
        self._models_loaded = False

        # Force GPU memory cleanup
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.info("GPU memory cleared")

        await super().cleanup()
