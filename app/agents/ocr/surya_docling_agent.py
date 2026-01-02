"""Surya-Docling OCR Agent - CPU-only implementation with German text support.

This version uses the new surya-ocr 0.17.0 API with DetectionPredictor,
FoundationPredictor, and RecognitionPredictor classes.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional
from pathlib import Path
import structlog

from PIL import Image
import pypdfium2 as pdfium

from app.agents.base import OCRAgent, OCRResult
from app.ml.metrics import get_ml_metrics

logger = structlog.get_logger(__name__)


class SuryaDoclingAgent(OCRAgent):
    """Surya OCR agent with working German text recognition (CPU-only)."""

    # Class-level lock to prevent race conditions during model loading
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(self):
        """Initialize Surya OCR models."""
        # Initialize class-level lock if not already done
        if SuryaDoclingAgent._model_lock is None:
            SuryaDoclingAgent._model_lock = asyncio.Lock()

        super().__init__(name="surya_docling_agent", gpu_required=False, vram_gb=0)

        # Models will be loaded on first use
        self._models_loaded = False
        self._det_predictor = None
        self._rec_predictor = None
        self._foundation_predictor = None
        self._task_name = None

        # Language settings - German primary
        self.default_language = "de"

        logger.info("SuryaDoclingAgent initialized (models will be loaded on first use)")

    async def _load_models_async(self, timeout_seconds: float = 600.0):
        """Load Surya models with thread-safe locking and timeout.

        SECURITY FIX: Uses asyncio.Lock to prevent race conditions when
        multiple concurrent requests try to load models simultaneously.

        Args:
            timeout_seconds: Maximum time to wait for model loading (default: 600s = 10min)

        Raises:
            asyncio.TimeoutError: If model loading exceeds timeout
        """
        async with SuryaDoclingAgent._model_lock:
            # Double-check pattern: re-check inside lock
            if self._models_loaded:
                return

            loop = asyncio.get_running_loop()
            try:
                # Run sync loading in thread pool with timeout
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._load_models_sync),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    "surya_model_loading_timeout",
                    timeout_seconds=timeout_seconds,
                    message="Model loading exceeded timeout - possible stuck download or OOM"
                )
                raise

    def _load_models(self):
        """Synchronous model loading - prefer _load_models_async() for concurrent access."""
        if self._models_loaded:
            return
        self._load_models_sync()

    def _load_models_sync(self):
        """Internal synchronous model loading implementation."""
        if self._models_loaded:
            return

        try:
            logger.info("Loading Surya 0.17.0 models...")

            # Import new surya API
            from surya.detection import DetectionPredictor
            from surya.recognition import RecognitionPredictor
            from surya.foundation import FoundationPredictor
            from surya.common.surya.schema import TaskNames

            # Store task name for OCR
            self._task_name = TaskNames.ocr_with_boxes

            # Load foundation predictor (required by recognition)
            self._foundation_predictor = FoundationPredictor()
            logger.info("Foundation predictor loaded")

            # Load detection predictor
            self._det_predictor = DetectionPredictor()
            logger.info("Detection predictor loaded")

            # Load recognition predictor with foundation
            self._rec_predictor = RecognitionPredictor(self._foundation_predictor)
            logger.info("Recognition predictor loaded")

            self._models_loaded = True
            logger.info("All Surya 0.17.0 models loaded successfully (CPU mode)")

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

    def _process_single_image(self, image: Image.Image, language: str = None) -> Dict[str, Any]:
        """Process a single image using the new Surya 0.17.0 API."""
        if language is None:
            language = self.default_language

        try:
            # Run OCR using the callable RecognitionPredictor
            predictions = self._rec_predictor(
                [image],
                task_names=[self._task_name],
                det_predictor=self._det_predictor,
            )

            text_blocks = []
            all_text = []

            # Process recognition results
            if predictions and len(predictions) > 0:
                pred = predictions[0]

                # Extract text lines from OCRResult
                if hasattr(pred, 'text_lines'):
                    for line in pred.text_lines:
                        text = line.text if hasattr(line, 'text') else str(line)
                        confidence = line.confidence if hasattr(line, 'confidence') else 0.0
                        bbox = line.bbox if hasattr(line, 'bbox') else []

                        if text and text.strip():
                            text_blocks.append({
                                "text": text,
                                "confidence": round(float(confidence), 3),
                                "bbox": list(bbox) if bbox else []
                            })
                            all_text.append(text)

            logger.debug("recognition_complete", text_blocks=len(text_blocks))

            return {
                "text_blocks": text_blocks,
                "full_text": "\n".join(all_text)
            }

        except Exception as e:
            logger.error("image_processing_failed", error=str(e))
            return {"text_blocks": [], "full_text": "", "error": str(e)}

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process document with Surya OCR pipeline.

        Args:
            input_data: Dictionary containing:
                - image_path: Path to the image or PDF file
                - language: Optional language hint (default: "de")

        Returns:
            Dictionary containing:
                - text: Extracted text
                - confidence: Overall confidence score
                - pages: Per-page OCR results
                - success: Whether OCR was successful
        """
        # Start timing
        start_time = time.perf_counter()
        metrics = get_ml_metrics()

        try:
            # Extract parameters
            image_path = input_data.get("image_path")
            if not image_path:
                raise ValueError("image_path is required in input_data")

            language = input_data.get("language", "de")

            # Ensure models are loaded
            await asyncio.get_running_loop().run_in_executor(None, self._load_models)

            # Load images
            images = await asyncio.get_running_loop().run_in_executor(
                None, self._load_image, image_path
            )

            if not images:
                raise ValueError(f"No images could be loaded from {image_path}")

            logger.info("pages_loaded_for_ocr", count=len(images))

            # Process each page
            all_text = []
            pages_data = []
            total_confidence = 0.0
            total_blocks = 0

            for idx, image in enumerate(images):
                logger.info("processing_page", page=idx + 1, total=len(images))

                # Process image
                result = await asyncio.get_running_loop().run_in_executor(
                    None, self._process_single_image, image, language
                )

                # Collect results with page-level confidence
                page_confidences = [block["confidence"] for block in result["text_blocks"]]
                page_confidence = float(sum(page_confidences) / len(page_confidences)) if page_confidences else 0.0

                # Identify low confidence blocks for this page
                low_confidence_blocks = [
                    {"block_idx": i, "confidence": block["confidence"], "text_preview": block.get("text", "")[:50]}
                    for i, block in enumerate(result["text_blocks"])
                    if block["confidence"] < 0.7
                ]

                page_data = {
                    "page_number": idx + 1,
                    "text_blocks": result["text_blocks"],
                    "full_text": result["full_text"],
                    # NEW: Page-level confidence metrics
                    "page_confidence": round(page_confidence, 3),
                    "block_count": len(result["text_blocks"]),
                    "low_confidence_blocks": low_confidence_blocks[:10],  # Limit to 10
                    "min_block_confidence": round(min(page_confidences), 3) if page_confidences else 0.0,
                    "max_block_confidence": round(max(page_confidences), 3) if page_confidences else 0.0,
                }
                pages_data.append(page_data)

                if result["full_text"]:
                    all_text.append(result["full_text"])

                # Calculate confidence
                for block in result["text_blocks"]:
                    total_confidence += block["confidence"]
                    total_blocks += 1

            # Calculate average confidence
            avg_confidence = (total_confidence / total_blocks) if total_blocks > 0 else 0.0

            # Combine all text with page breaks
            full_text = "\n\n--- Page Break ---\n\n".join(all_text) if all_text else ""

            if not full_text:
                logger.warning("No text extracted from document")

            logger.info("ocr_completed", chars_extracted=len(full_text), pages=len(images))

            # German text postprocessing
            has_umlauts = False
            german_validation_score = 0.0

            if language == "de" and full_text:
                try:
                    from app.services.german_text_postprocessor import get_german_postprocessor
                    postprocessor = get_german_postprocessor()
                    german_result = postprocessor.postprocess(full_text)
                    full_text = german_result["text"]

                    # Extract German quality metrics
                    stats = german_result.get("stats", {})
                    german_validation_score = stats.get("quality_score", 0.0)
                    has_umlauts = any(c in full_text for c in "äöüÄÖÜß")

                    corrections = german_result.get("corrections", [])
                    if corrections:
                        logger.debug(
                            "surya_german_postprocessing",
                            corrections_count=len(corrections),
                            umlaut_fixes=stats.get("umlaut_corrections", 0),
                            eszett_fixes=stats.get("eszett_corrections", 0)
                        )
                except ImportError:
                    logger.debug("german_postprocessor_not_available")
                    # Fallback: Check for German characters
                    has_umlauts = any(c in full_text for c in "äöüÄÖÜß")
                except Exception as e:
                    logger.warning(
                        "surya_german_postprocessing_error",
                        error=str(e)
                    )
                    # Track postprocessor error in metrics
                    metrics.record_ocr_postprocessor_error(
                        backend="surya",
                        postprocessor="german_text"
                    )
                    # Fallback: Check for German characters
                    has_umlauts = any(c in full_text for c in "äöüÄÖÜß")

            # Calculate processing time
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Record metrics
            metrics.record_ocr_inference_time("surya", processing_time_ms / 1000.0)
            metrics.record_ocr_confidence_score("surya", avg_confidence)

            # Erstelle standardisiertes OCRResult
            result = self.create_success_result(
                text=full_text,
                confidence=round(avg_confidence, 3),
                processing_time_ms=processing_time_ms,
                page_count=len(images),
                language=language,
                pages=pages_data,
                has_umlauts=has_umlauts,
                german_validation_score=german_validation_score,
            )

            return result.to_dict()

        except Exception as e:
            logger.error("surya_ocr_processing_error", error=str(e), exc_info=True)

            # Erstelle standardisiertes Fehler-Result
            result = self.create_error_result(
                error=str(e),
                error_code="SURYA_DOCLING_ERROR",
            )
            return result.to_dict()

    async def cleanup(self):
        """Clean up resources."""
        # Release model references
        self._det_predictor = None
        self._rec_predictor = None
        self._foundation_predictor = None
        self._models_loaded = False

        await super().cleanup()
        logger.info("SuryaDoclingAgent cleanup called")

    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            "name": self.name,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "models_loaded": self._models_loaded,
            "default_language": self.default_language,
            "model_version": "surya-ocr-0.17.0",
            "status": "ready" if self._models_loaded else "not_loaded"
        }
