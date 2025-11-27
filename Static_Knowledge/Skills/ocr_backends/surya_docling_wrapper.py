"""
Surya + Docling Wrapper - CPU Fallback Pipeline
Layout-aware OCR pipeline for CPU-only processing
Priority: P0 - CRITICAL (graceful degradation)

Surya v1.1: Layout detection and OCR
Docling v1.0: Document structure analysis

Repositories:
- https://github.com/VikParuchuri/surya
- https://github.com/DS4SD/docling
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
import time

import structlog

try:
    from PIL import Image
    DEPENDENCIES_AVAILABLE = True
except ImportError:
    DEPENDENCIES_AVAILABLE = False

logger = structlog.get_logger(__name__)


class SuryaDoclingWrapper:
    """
    CPU-only OCR pipeline using Surya + Docling
    Always available fallback when GPU not available
    """

    def __init__(self):
        """Initialize Surya+Docling wrapper"""
        if not DEPENDENCIES_AVAILABLE:
            raise ImportError(
                "Surya/Docling dependencies not installed. "
                "Install: pip install surya-ocr docling pillow"
            )

        self.surya_model = None
        self.docling_converter = None
        self.is_loaded = False

        # Resource requirements
        self.vram_required_gb = 0.0  # CPU only
        self.cpu_cores_recommended = 4

        logger.info("Surya+Docling wrapper initialized (CPU mode)")

    def load_models(self) -> None:
        """Load Surya and Docling models"""
        if self.is_loaded:
            logger.info("Models already loaded")
            return

        try:
            logger.info("Loading Surya+Docling models...")
            start_time = time.time()

            # NOTE: Real implementation would be:
            # from surya.ocr import load_model
            # from docling.document_converter import DocumentConverter
            #
            # self.surya_model = load_model()
            # self.docling_converter = DocumentConverter()

            # Mock for now
            self._load_mock_models()

            self.is_loaded = True

            load_time = time.time() - start_time
            logger.info("models_loaded", load_time_seconds=round(load_time, 2))

        except Exception as e:
            logger.error("failed_to_load_models", error=str(e))
            raise

    def _load_mock_models(self) -> None:
        """Mock models for testing"""
        logger.warning("Using MOCK Surya+Docling models")

        class MockModel:
            pass

        self.surya_model = MockModel()
        self.docling_converter = MockModel()

    async def process(
        self,
        document_path: Path,
        language: str = "de",
        analyze_layout: bool = True,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Process document with Surya+Docling pipeline

        Args:
            document_path: Path to document
            language: Language code
            analyze_layout: Whether to analyze document layout
            **kwargs: Additional options

        Returns:
            Dict with text, confidence, and metadata
        """
        if not self.is_loaded:
            self.load_models()

        logger.info("processing_document", filename=document_path.name)

        try:
            # Step 1: Document structure analysis with Docling
            if analyze_layout:
                layout_info = self._analyze_layout(document_path)
            else:
                layout_info = None

            # Step 2: OCR with Surya
            images = self._load_document(document_path)
            ocr_results = []

            for i, image in enumerate(images):
                page_result = self._extract_text_from_image(
                    image,
                    language,
                    layout_info.get(i) if layout_info else None
                )
                ocr_results.append(page_result)

            # Step 3: Combine results
            full_text = "\n\n".join(r["text"] for r in ocr_results)
            avg_confidence = sum(r["confidence"] for r in ocr_results) / len(ocr_results)

            return {
                "text": full_text,
                "confidence": avg_confidence,
                "metadata": {
                    "backend": "surya_docling",
                    "pages_processed": len(images),
                    "language": language,
                    "layout_analyzed": analyze_layout,
                    "device": "cpu"
                }
            }

        except Exception as e:
            logger.error("surya_docling_processing_failed", error=str(e))
            raise

    def _analyze_layout(self, document_path: Path) -> Dict[int, Dict]:
        """
        Analyze document layout with Docling

        Args:
            document_path: Path to document

        Returns:
            Dict mapping page number to layout info
        """
        logger.info("Analyzing document layout...")

        # NOTE: Real implementation:
        # result = self.docling_converter.convert(str(document_path))
        # return result.document.pages

        # Mock layout info
        return {
            0: {
                "blocks": [
                    {"type": "header", "bbox": [0, 0, 100, 20]},
                    {"type": "text", "bbox": [0, 20, 100, 80]},
                    {"type": "footer", "bbox": [0, 80, 100, 100]}
                ]
            }
        }

    def _load_document(self, document_path: Path) -> List[Image.Image]:
        """
        Load document and convert to images

        Args:
            document_path: Path to document

        Returns:
            List of PIL Images
        """
        from PIL import Image

        suffix = document_path.suffix.lower()

        if suffix in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']:
            image = Image.open(document_path)
            return [image.convert('RGB')]

        elif suffix == '.pdf':
            # NOTE: Requires pdf2image
            # from pdf2image import convert_from_path
            # return convert_from_path(document_path, dpi=200)  # Lower DPI for CPU

            logger.warning("PDF processing not implemented, using mock")
            return [Image.new('RGB', (800, 1131), color='white')]

        else:
            raise ValueError(f"Unsupported file type: {suffix}")

    def _extract_text_from_image(
        self,
        image: Image.Image,
        language: str = "de",
        layout_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Extract text from image using Surya

        Args:
            image: PIL Image
            language: Language code
            layout_info: Optional layout information from Docling

        Returns:
            Dict with text and confidence
        """
        logger.info("extracting_text", language=language)

        # NOTE: Real implementation:
        # from surya.ocr import run_ocr
        # result = run_ocr(
        #     [image],
        #     [language],
        #     self.surya_model
        # )
        # text = result[0].text
        # confidence = result[0].confidence

        # Simulate CPU processing time (slower than GPU)
        time.sleep(0.75)  # ~750ms per page (CPU is slower)

        # Mock German invoice text
        mock_text = """
        Firma Müller & Söhne GmbH
        Hauptstraße 456
        54321 Köln

        Rechnung-Nr: 2024-042
        Rechnungsdatum: 22.11.2024
        Kundennummer: K-12345

        Sehr geehrte Damen und Herren,

        für unsere Dienstleistungen berechnen wir:

        Pos. Bezeichnung              Menge    Einzelpreis    Gesamt
        1    Beratungsleistung        10 h      120,00 €   1.200,00 €
        2    Materialkosten            1 Psch.   350,00 €     350,00 €

        Zwischensumme (netto):                             1.550,00 €
        zzgl. 19% MwSt.:                                     294,50 €
        Rechnungsbetrag (brutto):                          1.844,50 €

        Zahlbar bis: 06.12.2024
        Verwendungszweck: Rechnung 2024-042

        Bankverbindung:
        IBAN: DE89 3704 0044 0532 0130 00
        BIC: COBADEFFXXX

        Vielen Dank für Ihr Vertrauen.

        Mit freundlichen Grüßen
        Müller & Söhne GmbH
        """

        return {
            "text": mock_text.strip(),
            "confidence": 0.88,  # CPU OCR typically lower confidence
            "layout_used": layout_info is not None
        }

    async def extract_text(
        self,
        document_path: Path,
        **options
    ) -> Dict[str, Any]:
        """
        Alternative method name for compatibility

        Args:
            document_path: Path to document
            **options: Processing options

        Returns:
            OCR result dict
        """
        return await self.process(document_path, **options)

    def get_resource_usage(self) -> Dict[str, Any]:
        """Get current CPU/RAM usage"""
        import psutil

        return {
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_percent": psutil.virtual_memory().percent,
            "device": "cpu"
        }


# Factory function
def create_surya_backend() -> SuryaDoclingWrapper:
    """
    Create Surya+Docling backend instance

    Returns:
        Initialized Surya+Docling wrapper
    """
    backend = SuryaDoclingWrapper()

    # Load models on-demand to save memory
    # backend.load_models()

    return backend
