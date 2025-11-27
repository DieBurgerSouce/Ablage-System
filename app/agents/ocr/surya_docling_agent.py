"""Surya-Docling OCR Agent - WORKING implementation with German text support."""

import os
import io
import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path
import logging

from PIL import Image
import pypdfium2 as pdfium

# Surya imports - using the working approach
from surya.detection import batch_text_detection
from surya.recognition import batch_recognition
from surya.model.detection.segformer import load_model as load_det_model
from surya.model.detection.segformer import load_processor as load_det_processor
from surya.model.recognition.model import load_model as load_rec_model
from surya.model.recognition.processor import load_processor as load_rec_processor

from app.agents.base import OCRAgent

# Configure logging
logger = logging.getLogger(__name__)


class SuryaDoclingAgent(OCRAgent):
    """Surya OCR agent with working German text recognition."""

    def __init__(self):
        """Initialize Surya OCR models."""
        super().__init__(name="surya_docling_agent", gpu_required=False, vram_gb=0)

        # Models will be loaded on first use
        self._models_loaded = False
        self._det_model = None
        self._det_processor = None
        self._rec_model = None
        self._rec_processor = None

        # Language settings - German primary
        self.default_language = "de"

        logger.info("SuryaDoclingAgent initialized (models will be loaded on first use)")

    def _load_models(self):
        """Load Surya models if not already loaded."""
        if self._models_loaded:
            return

        try:
            logger.info("Loading Surya models...")

            # Load detection model
            self._det_model = load_det_model()
            self._det_processor = load_det_processor()
            logger.info("Detection model loaded")

            # Load recognition model
            self._rec_model = load_rec_model()
            self._rec_processor = load_rec_processor()
            logger.info("Recognition model loaded")

            self._models_loaded = True
            logger.info("All Surya models loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load Surya models: {e}")
            raise

    def _load_image(self, image_path: str) -> List[Image.Image]:
        """Load image(s) from file path, handling both PDFs and images."""
        path = Path(image_path)
        images = []

        if not path.exists():
            raise FileNotFoundError(f"File not found: {image_path}")

        if path.suffix.lower() == '.pdf':
            # Handle PDF files
            logger.info(f"Processing PDF file: {image_path}")
            try:
                pdf = pdfium.PdfDocument(image_path)
                for page_num in range(len(pdf)):
                    page = pdf[page_num]
                    # Render at 300 DPI for good quality
                    pil_image = page.render(scale=300/72).to_pil()
                    images.append(pil_image)
                    logger.debug(f"Loaded PDF page {page_num + 1}/{len(pdf)}")
                pdf.close()
            except Exception as e:
                logger.error(f"Failed to load PDF: {e}")
                raise
        else:
            # Handle image files (PNG, JPG, etc.)
            logger.info(f"Processing image file: {image_path}")
            try:
                image = Image.open(image_path)
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(image)
            except Exception as e:
                logger.error(f"Failed to load image: {e}")
                raise

        return images

    def _process_single_image(self, image: Image.Image, language: str = None) -> Dict[str, Any]:
        """Process a single image using the working Surya approach."""
        if language is None:
            language = self.default_language

        # Step 1: Detect text regions
        predictions = batch_text_detection([image], self._det_model, self._det_processor)

        if not predictions or len(predictions) == 0:
            return {"text_blocks": [], "full_text": ""}

        pred = predictions[0]
        if len(pred.bboxes) == 0:
            return {"text_blocks": [], "full_text": ""}

        text_blocks = []
        all_text = []

        # Step 2: Process each region individually (workaround for Surya batch bug)
        for i, bbox in enumerate(pred.bboxes):
            # Get bounding box coordinates
            x1, y1, x2, y2 = int(bbox.bbox[0]), int(bbox.bbox[1]), int(bbox.bbox[2]), int(bbox.bbox[3])

            # Ensure coordinates are valid
            x1, x2 = max(0, x1), min(image.width, x2)
            y1, y2 = max(0, y1), min(image.height, y2)

            if x2 <= x1 or y2 <= y1:
                continue

            # Crop the image to the bounding box
            cropped = image.crop((x1, y1, x2, y2))

            try:
                # Process single region with single language code
                rec_preds, conf_scores = batch_recognition(
                    [cropped],      # Single image slice
                    [language],     # Single language code
                    self._rec_model,
                    self._rec_processor
                )

                # Extract text from prediction
                text = None
                confidence = 0.0

                if rec_preds and len(rec_preds) > 0:
                    pred_item = rec_preds[0]

                    # Handle different return formats
                    if isinstance(pred_item, str):
                        text = pred_item
                    elif hasattr(pred_item, 'text'):
                        text = pred_item.text
                    else:
                        text = str(pred_item) if pred_item else None

                    if conf_scores and len(conf_scores) > 0:
                        confidence = float(conf_scores[0])

                if text and text.strip():
                    text_blocks.append({
                        "text": text,
                        "confidence": round(confidence, 3),
                        "bbox": [x1, y1, x2, y2]
                    })
                    all_text.append(text)
                    logger.debug(f"Region {i+1}: '{text}' (conf: {confidence:.2f})")

            except Exception as e:
                logger.debug(f"Failed to process region {i+1}: {e}")
                continue

        return {
            "text_blocks": text_blocks,
            "full_text": "\n".join(all_text)
        }

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

            logger.info(f"Loaded {len(images)} page(s) for OCR processing")

            # Process each page
            all_text = []
            pages_data = []
            total_confidence = 0.0
            total_blocks = 0

            for idx, image in enumerate(images):
                logger.info(f"Processing page {idx + 1}/{len(images)}")

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

            logger.info(f"OCR completed. Extracted {len(full_text)} characters from {len(images)} page(s)")

            # Check for German characters if German language was used
            if language == "de" and full_text:
                german_chars = ['ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü', 'ß']
                found_chars = [char for char in german_chars if char in full_text]
                if found_chars:
                    logger.info(f"German characters detected: {', '.join(found_chars)}")

            return {
                "text": full_text,
                "confidence": round(avg_confidence, 3),
                "pages": pages_data,
                "page_count": len(images),
                "language": language,
                "model": "surya-ocr",
                "success": bool(full_text)
            }

        except Exception as e:
            logger.error(f"Error in Surya OCR processing: {str(e)}", exc_info=True)
            return {
                "text": "",
                "confidence": 0.0,
                "error": str(e),
                "success": False,
                "model": "surya-ocr"
            }

    async def cleanup(self):
        """Clean up resources."""
        # Models are kept in memory for reuse
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
            "status": "ready" if self._models_loaded else "not_loaded"
        }