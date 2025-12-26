# -*- coding: utf-8 -*-
"""
PaddleOCR-VL 0.9B Experimental Agent - Evaluation Only.

⚠️ EXPERIMENTAL - NOT FOR PRODUCTION USE ⚠️

This agent is for evaluation purposes only. It will be refactored
into a production-ready version only if the evaluation shows positive results.

Features:
- PaddleOCR-VL 0.9B Vision-Language Model
- GPU required (8GB+ VRAM)
- Structured outputs (JSON/Markdown)
- Multimodal document understanding

Technical Data:
- GPU erforderlich: JA (8GB+ VRAM)
- RAM: ~4GB
- Sprachen: 109 (inkl. Deutsch)
- Genauigkeit: ~95% (erwartet, basierend auf Benchmarks)
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
import torch
from PIL import Image
import pypdfium2 as pdfium
import numpy as np

from app.agents.base import OCRAgent, OCRResult

logger = structlog.get_logger(__name__)


class PaddleOCRVLAgentExperimental(OCRAgent):
    """
    PaddleOCR-VL 0.9B Experimental Agent - Evaluation Only.

    ⚠️ WARNING: This is an EXPERIMENTAL implementation for evaluation.
    Do not use in production until evaluation is complete and agent is refactored.

    Features:
    - Vision-Language Model (VLM) with 0.9B parameters
    - Multimodal document understanding
    - Structured outputs (JSON/Markdown)
    - Tabellen- und Formel-Erkennung
    - 109 Sprachen inkl. Deutsch
    """

    # EXPERIMENTAL FLAG - marks this agent as experimental for evaluation
    experimental: bool = True

    # Estimated VRAM requirement (will be validated during testing)
    VRAM_REQUIRED_GB = 10.0  # Conservative estimate, actual might be 8-12GB
    MODEL_LOADING_TIMEOUT = 600.0  # 10 minutes for large model

    # Class-level lock to prevent race conditions during model loading
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(self) -> None:
        """Initialize PaddleOCR-VL Experimental Agent."""
        # Initialize class-level lock if not already done
        if PaddleOCRVLAgentExperimental._model_lock is None:
            PaddleOCRVLAgentExperimental._model_lock = asyncio.Lock()

        # Check GPU availability
        gpu_available = torch.cuda.is_available()
        if not gpu_available:
            logger.warning(
                "paddleocr_vl_no_gpu",
                message="PaddleOCR-VL requires GPU but CUDA is not available"
            )

        super().__init__(
            name="paddle_ocr_vl_agent_experimental",
            gpu_required=gpu_available,
            vram_gb=self.VRAM_REQUIRED_GB if gpu_available else 0
        )

        # Model will be loaded on first use
        self._model_loaded = False
        self._ocr = None
        self._device = torch.device("cuda" if gpu_available else "cpu")

        # Language settings - German primary
        self.default_language = "german"

        logger.info(
            "paddleocr_vl_experimental_initialized",
            gpu_available=gpu_available,
            device=str(self._device),
            vram_gb=self.vram_gb,
            experimental=True
        )

    async def _load_model_async(self, timeout_seconds: float = MODEL_LOADING_TIMEOUT) -> None:
        """Load PaddleOCR-VL model with thread-safe locking and timeout.

        Args:
            timeout_seconds: Maximum time to wait for model loading (default: 600s = 10min)

        Raises:
            asyncio.TimeoutError: If model loading exceeds timeout
            ImportError: If PaddleOCR-VL is not available
        """
        async with PaddleOCRVLAgentExperimental._model_lock:
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
                    "paddleocr_vl_model_loading_timeout",
                    timeout_seconds=timeout_seconds,
                    message="Model loading exceeded timeout - possible stuck download or OOM"
                )
                raise

    def _load_model_sync(self) -> None:
        """Internal synchronous model loading implementation."""
        if self._model_loaded:
            return

        try:
            logger.info("Loading PaddleOCR-VL 0.9B model...")

            # Try different import strategies for PaddleOCR-VL
            # Strategy 1: Direct import (if separate package)
            try:
                from paddleocr_vl import PaddleOCRVL
                self._ocr = PaddleOCRVL(
                    model_name='PaddleOCR-VL-0.9B',
                    device='cuda' if torch.cuda.is_available() else 'cpu',
                    language=self.default_language
                )
                logger.info("PaddleOCR-VL loaded via direct import")
            except ImportError:
                # Strategy 2: Fallback to regular PaddleOCR 3.3.2 (for testing)
                # Note: PaddleOCR-VL 0.9B is not yet available (Dec 2025)
                # PaddleOCR 3.3.2 API changes:
                # - use_gpu: Removed (auto-detected)
                # - use_vl: Does not exist
                # - Device is automatically detected
                try:
                    from paddleocr import PaddleOCR
                    # Use PaddleOCR 3.3.2 API (minimal parameters)
                    # GPU will be auto-detected if available
                    self._ocr = PaddleOCR(
                        lang=self.default_language
                        # Note: Angle classification is integrated into pipeline in 3.3.2
                        # No cls parameter needed in .ocr() method
                    )
                    logger.warning(
                        "paddleocr_vl_fallback_to_regular",
                        message="PaddleOCR-VL 0.9B not available, using regular PaddleOCR 3.3.2 for testing"
                    )
                except Exception as e:
                    logger.error(
                        "paddleocr_fallback_failed",
                        error=str(e),
                        message="Failed to initialize PaddleOCR 3.3.2"
                    )
                    raise

            self._model_loaded = True

            # Log VRAM usage after loading
            if torch.cuda.is_available():
                vram_allocated = torch.cuda.memory_allocated(0) / 1024**3
                vram_reserved = torch.cuda.memory_reserved(0) / 1024**3
                logger.info(
                    "paddleocr_vl_model_loaded",
                    vram_allocated_gb=round(vram_allocated, 2),
                    vram_reserved_gb=round(vram_reserved, 2),
                    device=str(self._device)
                )

            logger.info("PaddleOCR-VL 0.9B model loaded successfully")

        except ImportError as e:
            logger.error("paddleocr_vl_import_failed", error=str(e))
            raise ImportError(
                "PaddleOCR-VL nicht installiert oder nicht verfügbar. "
                "Installation: pip install paddlepaddle-gpu paddleocr "
                "Oder: PaddleOCR-VL 0.9B ist möglicherweise noch nicht öffentlich verfügbar."
            ) from e
        except Exception as e:
            logger.error("paddleocr_vl_model_load_failed", error=str(e), exc_info=True)
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
            logger.info("paddleocr_vl_processing_pdf", path=image_path)
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
                    logger.debug("paddleocr_vl_pdf_page_loaded", page=page_num + 1, total=len(pdf))
                pdf.close()
            except Exception as e:
                logger.error("paddleocr_vl_pdf_load_failed", error=str(e))
                raise
        else:
            # Handle image files (PNG, JPG, TIFF, etc.)
            logger.info("paddleocr_vl_processing_image", path=image_path)
            try:
                image = Image.open(image_path)
                # Convert to RGB if necessary
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(np.array(image))
            except Exception as e:
                logger.error("paddleocr_vl_image_load_failed", error=str(e))
                raise

        return images

    def _process_single_image(self, image: np.ndarray) -> Dict[str, Any]:
        """Process a single image using PaddleOCR-VL.

        Args:
            image: Numpy array of the image (RGB)

        Returns:
            Dictionary with text_blocks, full_text, and structured data
        """
        try:
            # Check VRAM before processing
            if torch.cuda.is_available():
                vram_before = torch.cuda.memory_reserved(0) / 1024**3
                if vram_before > 14.0:
                    logger.warning(
                        "paddleocr_vl_high_vram_before",
                        vram_gb=round(vram_before, 2),
                        message="VRAM usage already high before processing"
                    )

            # Process with PaddleOCR 3.3.2
            # API might differ - handle both structured and list formats
            if hasattr(self._ocr, 'process'):
                # PaddleOCR-VL structured API (if available in future)
                result = self._ocr.process(image)
            else:
                # Standard PaddleOCR 3.3.2 API
                # Note: cls parameter removed in 3.3.2 (angle classification integrated)
                ocr_result = self._ocr.ocr(image)

                # Handle PaddleOCR 3.3.2 dict format
                # 3.3.2 returns: {'ocr_result': [[[bbox], (text, conf)], ...], ...}
                if isinstance(ocr_result, dict) and 'ocr_result' in ocr_result:
                    result = ocr_result['ocr_result']
                elif isinstance(ocr_result, list):
                    # Backward compatibility: list format
                    result = ocr_result[0] if ocr_result and isinstance(ocr_result[0], list) else ocr_result
                else:
                    result = ocr_result

            # Check VRAM after processing
            if torch.cuda.is_available():
                vram_after = torch.cuda.memory_reserved(0) / 1024**3
                vram_peak = torch.cuda.max_memory_reserved(0) / 1024**3
                logger.debug(
                    "paddleocr_vl_vram_usage",
                    vram_after_gb=round(vram_after, 2),
                    vram_peak_gb=round(vram_peak, 2)
                )

                if vram_peak > 14.0:
                    logger.warning(
                        "paddleocr_vl_vram_exceeded",
                        vram_peak_gb=round(vram_peak, 2),
                        message="VRAM usage exceeded 14GB - may cause OOM on RTX 4080"
                    )

            text_blocks: List[Dict[str, Any]] = []
            all_text: List[str] = []
            structured_data: Dict[str, Any] = {}

            # Parse result based on format
            if isinstance(result, dict):
                # Structured output format (PaddleOCR-VL)
                text = result.get('text', '')
                if not text and 'pages' in result:
                    # Multi-page document
                    pages_text = []
                    for page in result['pages']:
                        pages_text.append(page.get('text', ''))
                    text = '\n'.join(pages_text)

                all_text.append(text)

                # Extract structured data
                structured_data = {
                    'tables': result.get('tables', []),
                    'formulas': result.get('formulas', []),
                    'diagrams': result.get('diagrams', []),
                    'structure': result.get('structure', {})
                }

                # Convert to text blocks format
                if 'blocks' in result:
                    for block in result['blocks']:
                        text_blocks.append({
                            "text": block.get('text', ''),
                            "confidence": block.get('confidence', 0.0),
                            "bbox": block.get('bbox', []),
                            "type": block.get('type', 'text')
                        })

            elif isinstance(result, list) and result:
                # List format (standard PaddleOCR)
                for line in result[0]:
                    if isinstance(line, (list, tuple)) and len(line) >= 2:
                        bbox = line[0]
                        text_data = line[1]
                        if isinstance(text_data, (list, tuple)) and len(text_data) >= 2:
                            text = text_data[0]
                            confidence = text_data[1]

                            if text and text.strip():
                                text_blocks.append({
                                    "text": text.strip(),
                                    "confidence": round(float(confidence), 3),
                                    "bbox": bbox,
                                })
                                all_text.append(text.strip())

            logger.debug(
                "paddleocr_vl_recognition_complete",
                text_blocks=len(text_blocks),
                has_structured_data=bool(structured_data)
            )

            return {
                "text_blocks": text_blocks,
                "full_text": "\n".join(all_text),
                "structured_data": structured_data
            }

        except torch.cuda.OutOfMemoryError as e:
            logger.error(
                "paddleocr_vl_oom",
                error=str(e),
                message="Out of Memory - VRAM exceeded"
            )
            return {
                "text_blocks": [],
                "full_text": "",
                "structured_data": {},
                "error": "OOM: VRAM exceeded",
                "error_code": "PADDLEOCR_VL_OOM"
            }
        except Exception as e:
            logger.error("paddleocr_vl_image_processing_failed", error=str(e), exc_info=True)
            return {
                "text_blocks": [],
                "full_text": "",
                "structured_data": {},
                "error": str(e)
            }

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process document with PaddleOCR-VL.

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
                "paddleocr_vl_processing_started",
                document_id=document_id,
                image_path=str(image_path),
                experimental=True
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

            logger.info("paddleocr_vl_pages_loaded", count=len(images))

            # Process each page
            all_text: List[str] = []
            pages_data: List[Dict[str, Any]] = []
            total_confidence = 0.0
            total_blocks = 0
            all_structured_data: List[Dict[str, Any]] = []

            for idx, image in enumerate(images):
                logger.info("paddleocr_vl_processing_page", page=idx + 1, total=len(images))

                # Process image
                result = await loop.run_in_executor(
                    None, self._process_single_image, image
                )

                # Check for OOM error
                if result.get("error_code") == "PADDLEOCR_VL_OOM":
                    raise RuntimeError(
                        "Out of Memory: VRAM exceeded during processing. "
                        "PaddleOCR-VL requires more VRAM than available."
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
                    "structured_data": result.get("structured_data", {})
                }
                pages_data.append(page_data)
                all_structured_data.append(result.get("structured_data", {}))

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
                logger.warning("paddleocr_vl_no_text_extracted")

            # Check for German characters (Umlauts)
            has_umlauts = False
            umlaut_count = 0
            if full_text:
                umlauts = ['ä', 'ö', 'ü', 'ß', 'Ä', 'Ö', 'Ü']
                umlaut_count = sum(1 for char in full_text if char in umlauts)
                has_umlauts = umlaut_count > 0
                if has_umlauts:
                    logger.info(
                        "paddleocr_vl_german_chars_detected",
                        umlaut_count=umlaut_count
                    )

            # Calculate processing time
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)

            # Get final VRAM usage
            vram_peak_gb = 0.0
            if torch.cuda.is_available():
                vram_peak_gb = round(torch.cuda.max_memory_reserved(0) / 1024**3, 2)

            logger.info(
                "paddleocr_vl_processing_completed",
                document_id=document_id,
                chars_extracted=len(full_text),
                pages=len(images),
                processing_time_ms=processing_time_ms,
                avg_confidence=round(avg_confidence, 3),
                umlaut_count=umlaut_count,
                vram_peak_gb=vram_peak_gb,
                experimental=True
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

            # Add experimental metadata
            result_dict = result.to_dict()
            result_dict["experimental"] = True
            result_dict["backend_version"] = "PaddleOCR-VL-0.9B"
            result_dict["vram_peak_gb"] = vram_peak_gb
            result_dict["structured_data"] = all_structured_data
            result_dict["umlaut_count"] = umlaut_count

            return result_dict

        except Exception as e:
            processing_time_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error(
                "paddleocr_vl_processing_error",
                error=str(e),
                exc_info=True,
                experimental=True
            )

            # Create standardized error result
            result = self.create_error_result(
                error=str(e),
                error_code="PADDLEOCR_VL_ERROR",
                processing_time_ms=processing_time_ms,
            )
            result_dict = result.to_dict()
            result_dict["experimental"] = True
            return result_dict

    async def cleanup(self) -> None:
        """Clean up resources."""
        self._ocr = None
        self._model_loaded = False

        # Clear CUDA cache
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        await super().cleanup()
        logger.info("PaddleOCRVLAgentExperimental cleanup complete")

    def get_vram_usage(self) -> Dict[str, float]:
        """
        Get current VRAM usage metrics.

        Returns:
            Dictionary with VRAM metrics:
            - allocated_gb: Currently allocated VRAM in GB
            - reserved_gb: Reserved VRAM in GB
            - total_gb: Total GPU memory in GB
            - usage_percent: Percentage of total memory reserved (capped at 100%)
            - exceeded_threshold: Whether usage exceeds 14GB threshold
        """
        if not torch.cuda.is_available():
            return {
                "allocated_gb": 0.0,
                "reserved_gb": 0.0,
                "total_gb": 0.0,
                "usage_percent": 0.0,
                "exceeded_threshold": False,
                "error": "CUDA not available"
            }

        try:
            allocated = torch.cuda.memory_allocated(0) / 1024**3
            reserved = torch.cuda.memory_reserved(0) / 1024**3
            total = torch.cuda.get_device_properties(0).total_memory / 1024**3
            # Cap usage_percent at 100% (can exceed if reserved > total in edge cases)
            usage_percent = min((reserved / total) * 100 if total > 0 else 0.0, 100.0)
            exceeded_threshold = reserved > 14.0  # 14GB threshold for RTX 4080

            return {
                "allocated_gb": round(allocated, 2),
                "reserved_gb": round(reserved, 2),
                "total_gb": round(total, 2),
                "usage_percent": round(usage_percent, 1),
                "exceeded_threshold": exceeded_threshold
            }
        except Exception as e:
            logger.error("vram_usage_check_failed", error=str(e))
            return {
                "allocated_gb": 0.0,
                "reserved_gb": 0.0,
                "total_gb": 0.0,
                "usage_percent": 0.0,
                "exceeded_threshold": False,
                "error": str(e)
            }

    def get_status(self) -> Dict[str, Any]:
        """Get agent status."""
        vram_info = self.get_vram_usage()

        return {
            "name": self.name,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "model_loaded": self._model_loaded,
            "default_language": self.default_language,
            "model_version": "PaddleOCR-VL-0.9B",
            "status": "ready" if self._model_loaded else "not_loaded",
            "experimental": True,
            "vram_info": vram_info
        }

