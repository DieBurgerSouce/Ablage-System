"""Surya-Docling OCR Agent - Layout preservation and structure recognition."""

from typing import Any, Dict

from app.agents.base import OCRAgent


class SuryaDoclingAgent(OCRAgent):
    """Surya+Docling pipeline for layout-aware OCR."""

    def __init__(self):
        super().__init__(name="surya_docling_agent", gpu_required=False, vram_gb=0)

    async def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process with Surya+Docling pipeline."""
        # TODO: Implement Surya+Docling pipeline
        #  1. Layout detection with Surya
        #  2. Text extraction with Docling
        #  3. Structure preservation
        return {
            "text": "[SURYA+DOCLING PLACEHOLDER]",
            "confidence": 0.88,
            "layout": {"sections": [], "tables": []},
        }
