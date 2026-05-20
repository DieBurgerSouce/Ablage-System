"""Document Intelligence Services.

Dieses Modul bietet KI-basierte Services für intelligente Dokumentenanalyse:
- LLMNERService: Named Entity Recognition via LLM (Qwen3-14B)
- DeadlineExtractionService: Fristen-Erkennung aus OCR-Text
"""

from app.services.document_intelligence.llm_ner_service import (
    LLMNERService,
    NERResult,
    ExtractedEntity,
    EntityType,
    get_llm_ner_service,
)
from app.services.document_intelligence.deadline_extraction_service import (
    DeadlineExtractionService,
    ParsedDeadline,
    DeadlineExtractionResult,
    GermanDateParser,
    DeadlineTypeClassifier,
    get_deadline_extraction_service,
)

__all__ = [
    # NER Service
    "LLMNERService",
    "NERResult",
    "ExtractedEntity",
    "EntityType",
    "get_llm_ner_service",
    # Deadline Extraction
    "DeadlineExtractionService",
    "ParsedDeadline",
    "DeadlineExtractionResult",
    "GermanDateParser",
    "DeadlineTypeClassifier",
    "get_deadline_extraction_service",
]
