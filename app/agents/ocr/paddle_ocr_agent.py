# -*- coding: utf-8 -*-
"""PaddleOCR PP-OCRv5 Agent - CPU-optimiertes OCR Backend.

Leichtgewichtiges, ressourceneffizientes OCR mit 106 Sprachen-Support.
Ideal als CPU-Fallback wenn GPU belegt oder nicht verfügbar.

Technische Daten:
- GPU erforderlich: NEIN (CPU-optimiert)
- RAM: ~2GB
- Sprachen: 106 (inkl. Deutsch)
- Genauigkeit: 86.38% (PP-OCRv5 Server)
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from PIL import Image
import pypdfium2 as pdfium
import numpy as np

from app.agents.base import OCRAgent, OCRResult
from app.core.safe_errors import safe_error_log

logger = structlog.get_logger(__name__)


class PaddleOCRAgent(OCRAgent):
    """PaddleOCR PP-OCRv5 Agent - CPU-optimiertes OCR.

    Features:
    - 106 Sprachen mit einem Modell
    - Sehr ressourceneffizient (~2GB RAM)
    - Kein GPU erforderlich
    - Aktiv gepflegt von Baidu
    """

    # Class-level lock to prevent race conditions during model loading
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(self) -> None:
        """Initialisiere PaddleOCR Agent."""
        # Initialize class-level lock if not already done
        if PaddleOCRAgent._model_lock is None:
            PaddleOCRAgent._model_lock = asyncio.Lock()

        super().__init__(name="paddle_ocr_agent", gpu_required=False, vram_gb=0)

        # Model will be loaded on first use
        self._model_loaded = False
        self._ocr = None

        # Language settings - German primary
        self.default_language = "german"

        logger.info("PaddleOCRAgent initialized (model will be loaded on first use)")

    async def _load_model_async(self, timeout_seconds: float = 300.0) -> None:
        """Load PaddleOCR model with thread-safe locking and timeout.

        Args:
            timeout_seconds: Maximum time to wait for model loading (default: 300s = 5min)

        Raises:
            asyncio.TimeoutError: If model loading exceeds timeout
        """
        async with PaddleOCRAgent._model_lock:
            # Double-check pattern: re-check inside lock
            if self._model_loaded:
                return

            loop = asyncio.get_event_loop()
            try:
                # Run sync loading in thread pool with timeout
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._load_model_sync),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    "paddle_ocr_model_loading_timeout",
                    timeout_seconds=timeout_seconds,
                    message="Model loading exceeded timeout - possible stuck download or OOM"
                )
                raise

    def _load_model_sync(self) -> None:
        """Internal synchronous model loading implementation."""
        if self._model_loaded:
            return

        try:
            logger.info("Loading PaddleOCR PP-OCRv5 model (3.3.2 API)...")

            from paddleocr import PaddleOCR

            # Initialize PaddleOCR 3.3.2 with German language support
            # PaddleOCR 3.3.2 API changes:
            # - use_gpu: Removed (auto-detected)
            # - show_log: Removed (use logging configuration)
            # - use_angle_cls: Removed (integrated into pipeline)
            # - lang: Still available for language selection
            # Device (CPU/GPU) is automatically detected
            self._ocr = PaddleOCR(
                lang=self.default_language
                # Note: Angle classification is integrated into pipeline in 3.3.2
                # No cls parameter needed in .ocr() method
            )

            self._model_loaded = True
            logger.info("PaddleOCR PP-OCRv5 model loaded successfully (3.3.2 API, CPU mode)")

        except ImportError as e:
            logger.error("paddle_ocr_import_failed", **safe_error_log(e))
            raise ImportError(
                "PaddleOCR nicht installiert. "
                "Installation: pip install paddlepaddle paddleocr"
            ) from e
        except Exception as e:
            logger.error("paddle_ocr_model_load_failed", **safe_error_log(e))
            raise

    def _load_image(self, image_path: str) -> List[np.ndarray]:
        """Load image(s) from file path, handling both PDFs and images.

        Args:
            image_path: Path to image or PDF file

        Returns:
            List of numpy arrays (one per page)

        Raises:
            FileNotFoundError: If file does not exist
        """
        path = Path(image_path)
        images: List[np.ndarray] = []

        if not path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {image_path}")

        if path.suffix.lower() == '.pdf':
            # Handle PDF files
            logger.info("paddle_ocr_processing_pdf", path=image_path)
            try:
                pdf = pdfium.PdfDocument(image_path)
                for page_num in range(len(pdf)):
                    page = pdf[page_num]
                    # Render at 300 DPI for good quality
                    pil_image = page.render(scale=300/72).to_pil()
                    # Convert to RGB numpy array
                    if pil_image.mode != 'RGB':
                        pil_image = pil_image.convert('RGB')
                    images.append(np.array(pil_image))
                    logger.debug("paddle_ocr_pdf_page_loaded", page=page_num + 1, total=len(pdf))
                pdf.close()
            except Exception as e:
                logger.error("paddle_ocr_pdf_load_failed", **safe_error_log(e))
                raise
        else:
            # Handle image files (PNG, JPG, TIFF, etc.)
            logger.info("paddle_ocr_processing_image", path=image_path)
            try:
                image = Image.open(image_path)
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(np.array(image))
            except Exception as e:
                logger.error("paddle_ocr_image_load_failed", **safe_error_log(e))
                raise

        return images

    def _process_single_image(self, image: np.ndarray) -> Dict[str, Any]:
        """Process a single image using PaddleOCR.

        Args:
            image: Numpy array of the image (RGB)

        Returns:
            Dictionary with text_blocks and full_text
        """
        try:
            # Run OCR with PaddleOCR 3.3.2
            # PaddleOCR 3.3.2 returns: dict with 'ocr_result' key containing [[[bbox], (text, confidence)], ...]
            # Or list format: [[[bbox], (text, confidence)], ...] (backward compatibility)
            ocr_result = self._ocr.ocr(image)  # cls parameter removed in 3.3.2

            text_blocks: List[Dict[str, Any]] = []
            all_text: List[str] = []

            # Handle PaddleOCR 3.3.2 dict format
            if isinstance(ocr_result, dict) and 'ocr_result' in ocr_result:
                result = ocr_result['ocr_result']
            elif isinstance(ocr_result, list):
                # Backward compatibility: list format
                result = ocr_result[0] if ocr_result and isinstance(ocr_result[0], list) else ocr_result
            else:
                result = None

            if result:
                for line in result:
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        # PaddleOCR format: [bounding_box, (text, confidence)]
                        bbox = line[0]  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                        text_data = line[1]
                        if isinstance(text_data, (list, tuple)) and len(text_data) >= 2:
                            text = text_data[0]  # text string
                            confidence = text_data[1]  # confidence float

                            if text and text.strip():
                                text_blocks.append({
                                    "text": text.strip(),
                                    "confidence": round(float(confidence), 3),
                                    "bbox": bbox,
                                })
                                all_text.append(text.strip())

            logger.debug("paddle_ocr_recognition_complete", text_blocks=len(text_blocks))

            return {
                "text_blocks": text_blocks,
                "full_text": "\n".join(all_text)
            }

        except Exception as e:
            logger.error("paddle_ocr_image_processing_failed", **safe_error_log(e))
            return {"text_blocks": [], "full_text": "", **safe_error_log(e)}

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process document with PaddleOCR.

        Args:
            input_data: Dictionary containing:
                - image_path: Path to the image or PDF file
                - language: Optional language hint (default: "german")

        Returns:
            Standardized OCRResult dictionary
        """
        start_time = time.perf_counter()

        try:
            # Extract parameters
            image_path = input_data.get("image_path")
            if not image_path:
                raise ValueError("image_path ist erforderlich in input_data")

            document_id = input_data.get("document_id", "unknown")

            logger.info(
                "paddle_ocr_processing_started",
                document_id=document_id,
                image_path=str(image_path)
            )

            # Ensure model is loaded
            await self._load_model_async()

            # Load images
            loop = asyncio.get_event_loop()
            images = await loop.run_in_executor(
                None, self._load_image, image_path
            )

            if not images:
                raise ValueError(f"Keine Bilder konnten geladen werden: {image_path}")

            logger.info("paddle_ocr_pages_loaded", count=len(images))

            # Process each page
            all_text: List[str] = []
            pages_data: List[Dict[str, Any]] = []
            total_confidence = 0.0
            total_blocks = 0

            for idx, image in enumerate(images):
                logger.info("paddle_ocr_processing_page", page=idx + 1, total=len(images))

                # Process image
                result = await loop.run_in_executor(
                    None, self._process_single_image, image
                )

                # Calculate page-level confidence
                page_confidences = [block["confidence"] for block in result["text_blocks"]]
                page_confidence = (
                    float(sum(page_confidences) / len(page_confidences))
                    if page_confidences
                    else 0.0
                )

                # Identify low confidence blocks
                low_confidence_blocks = [
                    {
                        "block_idx": i,
                        "confidence": block["confidence"],
                        "text_preview": block.get("text", "")[:50]
                    }
                    for i, block in enumerate(result["text_blocks"])
                    if block["confidence"] < 0.7
                ]

                page_data = {
                    "page_number": idx + 1,
                    "text_blocks": result["text_blocks"],
                    "full_text": result["full_text"],
                    "page_confidence": round(page_confidence, 3),
                    "block_count": len(result["text_blocks"]),
                    "low_confidence_blocks": low_confidence_blocks[:10],
                    "min_block_confidence": (
                        round(min(page_confidences), 3) if page_confidences else 0.0
                    ),
                    "max_block_confidence": (
                        round(max(page_confidences), 3) if page_confidences else 0.0
                    ),
                }
                pages_data.append(page_data)

                if result["full_text"]:
                    all_text.append(result["full_text"])

                # Accumulate confidence
                for block in result["text_blocks"]:
                    total_confidence += block["confidence"]
                    total_blocks += 1

            # Calculate average confidence
            avg_confidence = (total_confidence / total_blocks) if total_blocks > 0 else 0.0

            # Combine all text with page breaks
            full_text = "\n\n--- Page Break ---\n\n".join(all_text) if all_text else ""

            if not full_text:
                logger.warning("paddle_ocr_no_text_extracted")

            # Check for German characters (Umlauts)
            has_umlauts = False
            if full_text:
                german_chars = ['ae', 'oe', 'ue', 'Ae', 'Oe', 'Ue', 'ss']
                found_chars = [char for char in german_chars if char in full_text]
                has_umlauts = len(found_chars) > 0
                if found_chars:
                    logger.info("paddle_ocr_german_chars_detected", chars=found_chars)

            # Calculate processing time
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)

            logger.info(
                "paddle_ocr_processing_completed",
                document_id=document_id,
                chars_extracted=len(full_text),
                pages=len(images),
                processing_time_ms=processing_time_ms,
                avg_confidence=round(avg_confidence, 3)
            )

            # Create standardized OCRResult
            result = self.create_success_result(
                text=full_text,
                confidence=round(avg_confidence, 3),
                processing_time_ms=processing_time_ms,
                page_count=len(images),
                language="de",
                pages=pages_data,
                has_umlauts=has_umlauts,
            )

            return result.to_dict()

        except Exception as e:
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "paddle_ocr_processing_error",
                **safe_error_log(e),
                exc_info=True
            )

            # Create standardized error result
            result = self.create_error_result(
                **safe_error_log(e),
                error_code="PADDLE_OCR_ERROR",
                processing_time_ms=processing_time_ms,
            )
            return result.to_dict()

    async def cleanup(self) -> None:
        """Clean up resources."""
        self._ocr = None
        self._model_loaded = False

        await super().cleanup()
        logger.info("PaddleOCRAgent cleanup complete")

    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        return {
            "name": self.name,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "model_loaded": self._model_loaded,
            "default_language": self.default_language,
            "model_version": "PP-OCRv5",
            "status": "ready" if self._model_loaded else "not_loaded"
        }
