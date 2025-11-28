"""Surya-Docling OCR Agent - CPU-only implementation with German text support.

This version uses the new surya-ocr 0.17.0 API with DetectionPredictor,
FoundationPredictor, and RecognitionPredictor classes.
"""

import asyncio
from typing import Any, Dict, List
from pathlib import Path
import structlog

from PIL import Image
import pypdfium2 as pdfium

from app.agents.base import OCRAgent

logger = structlog.get_logger(__name__)


class SuryaDoclingAgent(OCRAgent):
    """Surya OCR agent with working German text recognition (CPU-only)."""

    def __init__(self):
        """Initialize Surya OCR models."""
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

    def _load_models(self):
        """Load Surya models if not already loaded."""
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
        try:
            # Extract parameters
            image_path = input_data.get("image_path")
            if not image_path:
                raise ValueError("image_path is required in input_data")

            language = input_data.get("language", "de")

            # Ensure models are loaded
            await asyncio.get_event_loop().run_in_executor(None, self._load_models)

            # Load images
            images = await asyncio.get_event_loop().run_in_executor(
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
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self._process_single_image, image, language
                )

                # Collect results
                page_data = {
                    "page_number": idx + 1,
                    "text_blocks": result["text_blocks"],
                    "full_text": result["full_text"]
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

            # Check for German characters if German language was used
            if language == "de" and full_text:
                german_chars = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
                found_chars = [char for char in german_chars if char in full_text]
                if found_chars:
                    logger.info("german_chars_detected", chars=found_chars)

            return {
                "text": full_text,
                "confidence": round(avg_confidence, 3),
                "pages": pages_data,
                "page_count": len(images),
                "language": language,
                "model": "surya-ocr-0.17.0",
                "success": bool(full_text)
            }

        except Exception as e:
            logger.error("surya_ocr_processing_error", error=str(e), exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "error": str(e),
                "success": False,
                "model": "surya-ocr-0.17.0"
            }

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
