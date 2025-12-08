"""
OCR Processing Agents.

Specialized agents for different OCR backends:
- DeepSeekAgent: Complex layouts, multimodal processing (requires GPU)
- GOTOCRAgent: Fast transformer-based OCR (requires GPU)
- SuryaDoclingAgent: Layout analysis and preservation (CPU)
- HybridOCRAgent: Multi-engine fusion for maximum accuracy
- DonutOCRAgent: Multilingual Document Understanding (100+ Sprachen, Kyrillisch)
- PaddleOCRAgent: PP-OCRv5, CPU-optimiert, 106 Sprachen (CPU)
- DocTRAgent: Mindee docTR, CPU-optimiert, deutsches Modell (CPU)
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
        from .qwen_ocr_agent import QwenOCRAgent
        __all__.extend(["DeepSeekAgent", "GOTOCRAgent", "HybridOCRAgent", "QwenOCRAgent"])

        # Chandra OCR - State-of-the-Art 9B VLM von Datalab
        try:
            from .chandra_agent import ChandraOCRAgent
            __all__.append("ChandraOCRAgent")
        except ImportError:
            # Chandra dependencies not installed
            pass

        # OlmOCR-2 - State-of-the-Art 7B VLM von Allen AI
        try:
            from .olmocr_agent import OlmOCRAgent
            __all__.append("OlmOCRAgent")
        except ImportError:
            # OlmOCR dependencies not installed
            pass
except ImportError:
    # PyTorch not available - GPU agents won't be loaded
    pass

# PaddleOCR PP-OCRv5 - CPU-optimiert, immer verfuegbar
try:
    from .paddle_ocr_agent import PaddleOCRAgent
    __all__.append("PaddleOCRAgent")
except ImportError:
    # paddleocr not installed
    pass

# Donut - kann auf GPU oder CPU laufen
try:
    from .donut_agent import DonutOCRAgent, is_donut_available
    __all__.extend(["DonutOCRAgent", "is_donut_available"])
except ImportError:
    # Transformers nicht installiert
    pass

# docTR - CPU-optimiert, deutsches Modell (Mindee)
try:
    from .doctr_agent import DocTRAgent, is_doctr_available
    __all__.extend(["DocTRAgent", "is_doctr_available"])
except ImportError:
    # python-doctr nicht installiert
    pass