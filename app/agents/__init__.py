"""
Multi-Agent System for Ablage-System OCR.

This package contains all specialized agents for document processing,
organized by category:

- ocr: OCR processing agents (DeepSeek, GOT-OCR, Surya, Hybrid)
- preprocessing: Document preprocessing agents
- postprocessing: Result enhancement agents
- orchestration: Workflow coordination agents
- intelligence: AI-powered analysis agents
- monitoring: System health and performance agents
- integration: External system integration agents
"""

__version__ = "1.0.0"
__all__ = [
    "BaseAgent",
    "OCRAgent",
    "PreprocessingAgent",
    "PostprocessingAgent",
    "OrchestrationAgent",
    "IntelligenceAgent",
    "MonitoringAgent",
]
