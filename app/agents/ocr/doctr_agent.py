# -*- coding: utf-8 -*-
"""
docTR OCR Agent - CPU-optimized OCR with German language support.

Mindee's Document Text Recognition (docTR):
- CPU-optimized (no GPU required)
- German model available (db_resnet50 + crnn_vgg16_bn)
- RAM: ~1GB
- Two-Stage Architecture: Detection + Recognition

Best for:
- German documents with Umlauts
- Low-resource environments
- CPU-only deployments

Feinpoliert und durchdacht - CPU-optimiert für deutsche Dokumente.
"""

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
from PIL import Image
import pypdfium2 as pdfium

from app.agents.base import OCRAgent, OCRResult
from app.core.safe_errors import safe_error_log, safe_error_detail

logger = structlog.get_logger(__name__)

# Dependency availability check
DOCTR_AVAILABLE = False
try:
    from doctr.io import DocumentFile
    from doctr.models import ocr_predictor
    DOCTR_AVAILABLE = True
except ImportError:
    logger.warning(
        "doctr_not_available",
        message="python-doctr nicht installiert. Installieren mit: pip install 'python-doctr[torch]'"
    )


def is_doctr_available() -> bool:
    """Check if docTR is available for use.

    Returns:
        True if docTR is installed and can be imported
    """
    return DOCTR_AVAILABLE


class DocTRAgent(OCRAgent):
    """
    docTR OCR Agent - CPU-optimiert mit deutschem Modell.

    Verwendet Mindee's docTR-Bibliothek für effiziente
    Textextraktion auf CPU mit spezieller Unterstützung
    für deutsche Dokumente und Umlaute.

    Features:
    - Kein GPU erforderlich
    - ~1GB RAM Verbrauch
    - Deutsches Sprachmodell
    - Two-Stage: Detection (db_resnet50) + Recognition (crnn_vgg16_bn)
    """

    # Model Configuration
    DETECTION_MODEL = "db_resnet50"       # ~100MB, high accuracy
    RECOGNITION_MODEL = "crnn_vgg16_bn"   # ~60MB, multilingual
    RAM_REQUIRED_MB = 1024                # ~1GB
    MODEL_LOADING_TIMEOUT = 300.0         # 5 minutes for model download

    # German Umlaut characters for validation
    GERMAN_UMLAUTS = "aouAOUs"

    # Class-level lock for thread-safe model loading
    _model_lock: Optional[asyncio.Lock] = None

    def __init__(
        self,
        det_arch: str = DETECTION_MODEL,
        reco_arch: str = RECOGNITION_MODEL,
        assume_straight_pages: bool = True,
    ):
        """
        Initialize docTR OCR Agent.

        Args:
            det_arch: Detection architecture (default: db_resnet50)
            reco_arch: Recognition architecture (default: crnn_vgg16_bn)
            assume_straight_pages: Optimize for scanned documents (faster)
        """
        # Initialize class-level lock if not already done
        if DocTRAgent._model_lock is None:
            DocTRAgent._model_lock = asyncio.Lock()

        # Base class: CPU-only, no VRAM required
        super().__init__(
            name="doctr_agent",
            gpu_required=False,
            vram_gb=0
        )

        # Configuration
        self.det_arch = det_arch
        self.reco_arch = reco_arch
        self.assume_straight_pages = assume_straight_pages

        # Model references (lazy-loaded)
        self._model = None
        self._models_loaded = False

        # Language settings
        self.default_language = "de"

        # Validate dependencies
        if not DOCTR_AVAILABLE:
            logger.warning(
                "doctr_agent_dependency_missing",
                message="docTR wird beim ersten Aufruf nicht verfügbar sein"
            )

        logger.info(
            "doctr_agent_initialized",
            det_arch=det_arch,
            reco_arch=reco_arch,
            assume_straight_pages=assume_straight_pages,
            doctr_available=DOCTR_AVAILABLE
        )

    async def _load_models_async(self, timeout_seconds: float = MODEL_LOADING_TIMEOUT) -> None:
        """Load docTR models with thread-safe locking and timeout.

        SECURITY FIX: Uses asyncio.Lock to prevent race conditions when
        multiple concurrent requests try to load models simultaneously.

        Args:
            timeout_seconds: Maximum time to wait for model loading (default: 300s = 5min)

        Raises:
            asyncio.TimeoutError: If model loading exceeds timeout
            ImportError: If docTR not installed
        """
        async with DocTRAgent._model_lock:
            # Double-check pattern: re-check inside lock
            if self._models_loaded:
                return

            loop = asyncio.get_event_loop()
            try:
                # Run sync loading in thread pool with timeout
                await asyncio.wait_for(
                    loop.run_in_executor(None, self._load_models_sync),
                    timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    "doctr_model_loading_timeout",
                    timeout_seconds=timeout_seconds,
                    message="Model loading exceeded timeout - possible stuck download or OOM"
                )
                raise

    def _load_models(self) -> None:
        """Synchronous model loading - prefer _load_models_async() for concurrent access."""
        if self._models_loaded:
            return
        self._load_models_sync()

    def _load_models_sync(self) -> None:
        """Internal synchronous model loading implementation."""
        if self._models_loaded:
            return

        if not DOCTR_AVAILABLE:
            raise ImportError(
                "docTR ist nicht installiert. Installieren mit: pip install 'python-doctr[torch]'"
            )

        try:
            logger.info(
                "doctr_loading_models",
                det_arch=self.det_arch,
                reco_arch=self.reco_arch
            )

            # Import and create predictor
            from doctr.models import ocr_predictor

            self._model = ocr_predictor(
                det_arch=self.det_arch,
                reco_arch=self.reco_arch,
                pretrained=True,
                assume_straight_pages=self.assume_straight_pages
            )

            self._models_loaded = True
            logger.info(
                "doctr_models_loaded",
                det_arch=self.det_arch,
                reco_arch=self.reco_arch,
                message="docTR Modelle erfolgreich geladen (CPU mode)"
            )

        except Exception as e:
            logger.error("doctr_models_load_failed", **safe_error_log(e))
            raise

    def _load_image(self, image_path: str) -> List[Image.Image]:
        """Load image(s) from file path, handling both PDFs and images.

        Args:
            image_path: Path to image or PDF file

        Returns:
            List of PIL Images (one per page)

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        path = Path(image_path)
        images: List[Image.Image] = []

        if not path.exists():
            raise FileNotFoundError(f"Datei nicht gefunden: {image_path}")

        if path.suffix.lower() == '.pdf':
            # Handle PDF files using pypdfium2 for consistency
            logger.info("doctr_processing_pdf", path=image_path)
            try:
                pdf = pdfium.PdfDocument(image_path)
                for page_num in range(len(pdf)):
                    page = pdf[page_num]
                    # Render at 300 DPI for good quality
                    pil_image = page.render(scale=300/72).to_pil()
                    # Convert to RGB if necessary
                    if pil_image.mode != 'RGB':
                        pil_image = pil_image.convert('RGB')
                    images.append(pil_image)
                    logger.debug(
                        "doctr_pdf_page_loaded",
                        page=page_num + 1,
                        total=len(pdf)
                    )
                pdf.close()
            except Exception as e:
                logger.error("doctr_pdf_load_failed", **safe_error_log(e))
                raise
        else:
            # Handle image files (PNG, JPG, TIFF, etc.)
            logger.info("doctr_processing_image", path=image_path)
            try:
                image = Image.open(image_path)
                # Convert to RGB if necessary (docTR requires RGB)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(image)
            except Exception as e:
                logger.error("doctr_image_load_failed", **safe_error_log(e))
                raise

        return images

    def _process_single_image(
        self,
        image: Image.Image,
        language: str = "de"
    ) -> Dict[str, Any]:
        """Process a single image using docTR.

        Args:
            image: PIL Image to process
            language: Language hint (default: German)

        Returns:
            Dictionary with text, confidence, word_count, text_blocks
        """
        try:
            # Import DocumentFile for processing
            from doctr.io import DocumentFile

            # Convert PIL Image to docTR document format
            # docTR expects numpy array, so convert through temporary save
            import numpy as np
            image_array = np.array(image)

            # Create document from numpy array
            doc = DocumentFile.from_images([image_array])

            # Run OCR
            result = self._model(doc)

            # Extract text and confidence from result
            text_blocks: List[Dict[str, Any]] = []
            all_text: List[str] = []
            total_confidence = 0.0
            word_count = 0

            # Process pages (should be 1 for single image)
            for page in result.pages:
                for block in page.blocks:
                    for line in block.lines:
                        line_words: List[str] = []
                        line_confidence = 0.0

                        for word in line.words:
                            word_text = word.value
                            word_conf = word.confidence

                            line_words.append(word_text)
                            total_confidence += word_conf
                            word_count += 1

                            # Store individual word with confidence
                            text_blocks.append({
                                "text": word_text,
                                "confidence": round(float(word_conf), 3),
                                "type": "word",
                                "geometry": word.geometry if hasattr(word, 'geometry') else None
                            })

                        # Combine words into line
                        line_text = ' '.join(line_words)
                        if line_text.strip():
                            all_text.append(line_text)

            # Calculate average confidence
            avg_confidence = (total_confidence / word_count) if word_count > 0 else 0.0

            logger.debug(
                "doctr_image_processed",
                word_count=word_count,
                confidence=round(avg_confidence, 3)
            )

            return {
                "text": "\n".join(all_text),
                "confidence": avg_confidence,
                "word_count": word_count,
                "text_blocks": text_blocks
            }

        except Exception as e:
            logger.error("doctr_image_processing_failed", **safe_error_log(e))
            return {
                "text": "",
                "confidence": 0.0,
                "word_count": 0,
                "text_blocks": [], **safe_error_log(e)}

    def _detect_umlauts(self, text: str) -> Tuple[bool, List[str]]:
        """Detect German umlauts in text.

        Args:
            text: Text to check for umlauts

        Returns:
            Tuple of (has_umlauts, list_of_found_umlauts)
        """
        german_chars = ['a', 'o', 'u', 'A', 'O', 'U', 's']
        found_chars = [char for char in german_chars if char in text]
        return len(found_chars) > 0, found_chars

    def _postprocess_german(self, text: str) -> str:
        """German-specific text post-processing.

        Applies corrections common for German OCR:
        - Normalize whitespace
        - Basic cleanup

        Args:
            text: Raw extracted text

        Returns:
            Processed text
        """
        if not text:
            return text

        # Normalize whitespace
        import re
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r' +', ' ', text)

        # Normalize line endings
        text = text.replace('\r\n', '\n')
        text = text.replace('\r', '\n')

        # Remove extra blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process document with docTR OCR pipeline.

        Args:
            input_data: Dictionary containing:
                - image_path: Path to the image or PDF file (required)
                - language: Optional language hint (default: "de")
                - document_id: Optional document identifier

        Returns:
            Standardized OCRResult as dictionary containing:
                - success: bool
                - text: Extracted text
                - confidence: Overall confidence (0.0-1.0)
                - pages: Per-page results
                - has_umlauts: German umlaut detection
        """
        start_time = time.time()

        try:
            # Validate dependencies
            if not DOCTR_AVAILABLE:
                raise ImportError(
                    "docTR ist nicht installiert. Installieren mit: pip install 'python-doctr[torch]'"
                )

            # Extract parameters
            image_path = input_data.get("image_path")
            if not image_path:
                raise ValueError("image_path ist erforderlich in input_data")

            language = input_data.get("language", self.default_language)
            document_id = input_data.get("document_id", "unknown")

            logger.info(
                "doctr_processing_started",
                image_path=image_path,
                language=language,
                document_id=document_id
            )

            # Load models (thread-safe with timeout)
            await self._load_models_async()

            # Load images
            loop = asyncio.get_event_loop()
            images = await loop.run_in_executor(None, self._load_image, image_path)

            if not images:
                raise ValueError(f"Keine Bilder konnten geladen werden aus {image_path}")

            logger.info("doctr_pages_loaded", count=len(images))

            # Process each page
            all_text: List[str] = []
            pages_data: List[Dict[str, Any]] = []
            total_confidence = 0.0
            total_words = 0

            for idx, image in enumerate(images):
                logger.info(
                    "doctr_processing_page",
                    page=idx + 1,
                    total=len(images)
                )

                # Process single image
                result = await loop.run_in_executor(
                    None,
                    self._process_single_image,
                    image,
                    language
                )

                # Collect results
                page_text = result.get("text", "")
                page_confidence = result.get("confidence", 0.0)
                page_word_count = result.get("word_count", 0)

                # Calculate weighted confidence contribution
                total_confidence += page_confidence * page_word_count
                total_words += page_word_count

                # Identify low confidence words
                low_conf_blocks = [
                    block for block in result.get("text_blocks", [])
                    if block.get("confidence", 1.0) < 0.7
                ]

                page_data = {
                    "page_number": idx + 1,
                    "text": page_text,
                    "page_confidence": round(page_confidence, 3),
                    "word_count": page_word_count,
                    "low_confidence_count": len(low_conf_blocks),
                    "text_blocks": result.get("text_blocks", [])[:100],  # Limit for performance
                }
                pages_data.append(page_data)

                if page_text.strip():
                    all_text.append(page_text)

            # Combine all text with page breaks
            full_text = "\n\n--- Page Break ---\n\n".join(all_text) if all_text else ""

            # Calculate average confidence
            avg_confidence = (total_confidence / total_words) if total_words > 0 else 0.0

            # German post-processing
            full_text = self._postprocess_german(full_text)

            # Detect German umlauts
            has_umlauts, found_umlauts = self._detect_umlauts(full_text)
            if found_umlauts:
                logger.info("doctr_german_chars_detected", chars=found_umlauts)

            # Calculate processing time
            processing_time_ms = int((time.time() - start_time) * 1000)

            # Create standardized success result
            result = self.create_success_result(
                text=full_text,
                confidence=round(avg_confidence, 3),
                processing_time_ms=processing_time_ms,
                page_count=len(images),
                language=language,
                pages=pages_data,
                has_umlauts=has_umlauts,
            )

            logger.info(
                "doctr_processing_completed",
                chars_extracted=len(full_text),
                words=total_words,
                pages=len(images),
                has_umlauts=has_umlauts,
                confidence=round(avg_confidence, 3),
                processing_time_ms=processing_time_ms
            )

            return result.to_dict()

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "doctr_processing_failed",
                **safe_error_log(e),
                processing_time_ms=processing_time_ms,
                exc_info=True
            )

            # Create standardized error result (PII-frei)
            result = self.create_error_result(
                error=safe_error_detail(e, "docTR-OCR"),
                error_code="DOCTR_OCR_ERROR",
                processing_time_ms=processing_time_ms
            )
            return result.to_dict()

    async def cleanup(self) -> None:
        """Clean up resources and release memory."""
        logger.info("doctr_cleanup_started")

        # Release model reference
        self._model = None
        self._models_loaded = False

        # Call parent cleanup
        await super().cleanup()
        logger.info("doctr_cleanup_completed")

    def get_status(self) -> Dict[str, Any]:
        """Get agent status with model information.

        Returns:
            Dictionary with agent status details
        """
        return {
            "name": self.name,
            "gpu_required": self.gpu_required,
            "vram_gb": self.vram_gb,
            "models_loaded": self._models_loaded,
            "default_language": self.default_language,
            "det_arch": self.det_arch,
            "reco_arch": self.reco_arch,
            "assume_straight_pages": self.assume_straight_pages,
            "ram_required_mb": self.RAM_REQUIRED_MB,
            "doctr_available": DOCTR_AVAILABLE,
            "status": "ready" if self._models_loaded else "not_loaded"
        }
