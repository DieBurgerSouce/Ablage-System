"""
OCR Processing Agents.

Specialized agents for different OCR backends:
- DeepSeekAgent: Complex layouts, multimodal processing
- GOTOCRAgent: Fast transformer-based OCR
- SuryaDoclingAgent: Layout analysis and preservation
- HybridOCRAgent: Multi-engine fusion for maximum accuracy
"""

from .deepseek_agent import DeepSeekAgent
from .got_ocr_agent import GOTOCRAgent
from .hybrid_agent import HybridOCRAgent
from .surya_docling_agent import SuryaDoclingAgent

__all__ = [
    "DeepSeekAgent",
    "GOTOCRAgent",
    "SuryaDoclingAgent",
    "HybridOCRAgent",
]
