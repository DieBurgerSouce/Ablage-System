"""RAG Intelligence Layer Services.

Dieses Paket enthaelt alle Services fuer den RAG Intelligence Layer:
- Document Chunking
- LLM Inference
- Chat System (Phase 4)
- Customer Cards (Phase 5)
- RAG Search
- Prompt Templates
"""

from app.services.rag.chunking_service import (
    DocumentChunkingService,
    get_chunking_service,
)
from app.services.rag.llm_service import (
    LLMService,
    LLMMessage,
    LLMResponse,
    LLMContextType,
    ModelRouter,
    get_llm_service,
)
from app.services.rag.search_service import (
    RAGSearchService,
    SearchResult,
    SearchResponse,
    get_rag_search_service,
)
from app.services.rag.prompt_templates import (
    SYSTEM_PROMPT_GENERAL,
    SYSTEM_PROMPT_TELEFON,
    SYSTEM_PROMPT_CUSTOMER_CARD,
    build_rag_context,
    build_chat_prompt,
    build_customer_card_prompt,
    build_classification_prompt,
    build_query_enhancement_prompt,
    build_extraction_prompt,
    build_report_prompt,
)
from app.services.rag.customer_card_service import (
    CustomerCardService,
    CustomerCardResult,
    CustomerSearchResult,
    get_customer_card_service,
)
from app.services.rag.excel_generator import (
    ExcelReportGenerator,
    get_excel_generator,
)
from app.services.rag.word_generator import (
    WordReportGenerator,
    get_word_generator,
)
from app.services.rag.metrics import (
    RAGMetricsService,
    get_rag_metrics_service,
    record_search,
    record_llm,
    record_chunking,
)

__all__ = [
    # Chunking
    "DocumentChunkingService",
    "get_chunking_service",
    # LLM
    "LLMService",
    "LLMMessage",
    "LLMResponse",
    "LLMContextType",
    "ModelRouter",
    "get_llm_service",
    # Search
    "RAGSearchService",
    "SearchResult",
    "SearchResponse",
    "get_rag_search_service",
    # Prompts
    "SYSTEM_PROMPT_GENERAL",
    "SYSTEM_PROMPT_TELEFON",
    "SYSTEM_PROMPT_CUSTOMER_CARD",
    "build_rag_context",
    "build_chat_prompt",
    "build_customer_card_prompt",
    "build_classification_prompt",
    "build_query_enhancement_prompt",
    "build_extraction_prompt",
    "build_report_prompt",
    # Customer Cards
    "CustomerCardService",
    "CustomerCardResult",
    "CustomerSearchResult",
    "get_customer_card_service",
    # Report Generators
    "ExcelReportGenerator",
    "get_excel_generator",
    "WordReportGenerator",
    "get_word_generator",
    # Metrics
    "RAGMetricsService",
    "get_rag_metrics_service",
    "record_search",
    "record_llm",
    "record_chunking",
]
