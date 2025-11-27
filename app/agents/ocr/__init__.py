"""
OCR Processing Agents.

Specialized agents for different OCR backends:
- DeepSeekAgent: Complex layouts, multimodal processing (requires GPU)
- GOTOCRAgent: Fast transformer-based OCR (requires GPU)
- SuryaDoclingAgent: Layout analysis and preservation (CPU)
- HybridOCRAgent: Multi-engine fusion for maximum accuracy
"""

# Always available (CPU-based)
from .surya_docling_agent import SuryaDoclingAgent

# Conditionally import GPU-based agents
__all__ = ["SuryaDoclingAgent"]

try:
    import torch
    if torch.cuda.is_available():
        from .deepseek_agent import DeepSeekAgent
        from .got_ocr_agent import GOTOCRAgent
        from .hybrid_agent import HybridOCRAgent
        __all__.extend(["DeepSeekAgent", "GOTOCRAgent", "HybridOCRAgent"])
except ImportError:
    # PyTorch not available - GPU agents won't be loaded
    pass