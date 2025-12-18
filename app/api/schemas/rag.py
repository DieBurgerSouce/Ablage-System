"""
RAG Intelligence Layer Schemas.

Pydantic Schemas fuer:
- Document Chunks
- Customer Cards
- Chat Sessions/Messages
- Search Requests/Responses
- Batch Jobs
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


# ============================================================================
# ENUMS
# ============================================================================

class RAGSectionType(str, Enum):
    """Chunk Section Types."""
    HEADER = "header"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class RAGChatRole(str, Enum):
    """Chat Message Rollen."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RAGContextType(str, Enum):
    """Chat Context Types."""
    GENERAL = "general"
    CUSTOMER = "customer"
    DOCUMENT = "document"
    REPORT = "report"


class RAGJobType(str, Enum):
    """Batch Job Typen."""
    CUSTOMER_CARD_SYNC = "customer_card_sync"
    REPORT_GENERATION = "report_generation"
    REEMBEDDING = "reembedding"
    CHUNK_DOCUMENTS = "chunk_documents"


class RAGJobStatus(str, Enum):
    """Batch Job Status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RAGSyncStatus(str, Enum):
    """Customer Card Sync Status."""
    PENDING = "pending"
    SYNCING = "syncing"
    COMPLETED = "completed"
    ERROR = "error"


class RAGSearchType(str, Enum):
    """Suchtypen."""
    SEMANTIC = "semantic"
    HYBRID = "hybrid"
    KEYWORD = "keyword"


# ============================================================================
# DOCUMENT CHUNKS
# ============================================================================

class RAGChunkBase(BaseModel):
    """Basis Schema fuer Document Chunks."""
    chunk_text: str = Field(..., min_length=1, description="Text-Inhalt des Chunks")
    page_number: Optional[int] = Field(None, ge=1, description="Seitennummer im Dokument")
    section_type: Optional[RAGSectionType] = Field(None, description="Typ der Sektion")


class RAGChunkCreate(RAGChunkBase):
    """Schema zum Erstellen eines Chunks."""
    document_id: UUID
    chunk_index: int = Field(..., ge=0, description="Index des Chunks im Dokument")
    chunk_tokens: int = Field(..., ge=1, le=8192, description="Anzahl Tokens")
    bounding_box: Optional[Dict[str, float]] = None


class RAGChunkResponse(RAGChunkBase):
    """Schema fuer Chunk Response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    document_id: UUID
    chunk_index: int
    chunk_tokens: int
    embedding_model: str
    embedding_created_at: datetime
    created_at: datetime


class RAGChunkSearchResult(BaseModel):
    """Suchergebnis fuer Chunks."""
    chunk_id: UUID
    document_id: UUID
    chunk_text: str
    chunk_index: int
    page_number: Optional[int]
    section_type: Optional[str]
    similarity: float = Field(..., ge=0, le=1, description="Cosine Similarity Score")
    rerank_score: Optional[float] = Field(None, description="Reranking Score")


# ============================================================================
# CUSTOMER CARDS
# ============================================================================

class RAGCustomerCardBase(BaseModel):
    """Basis Schema fuer Customer Cards."""
    customer_id: str = Field(..., min_length=1, max_length=100)
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_type: Optional[str] = Field(None, max_length=50)


class RAGCustomerCardCreate(RAGCustomerCardBase):
    """Schema zum Erstellen einer Customer Card."""
    summary_text: str
    quick_facts: List[str] = Field(default_factory=list)
    open_invoices: List[Dict[str, Any]] = Field(default_factory=list)
    active_contracts: List[Dict[str, Any]] = Field(default_factory=list)
    recent_orders: List[Dict[str, Any]] = Field(default_factory=list)
    payment_behavior: Optional[str] = None
    flags: List[str] = Field(default_factory=list)
    priority_level: int = Field(default=0, ge=0, le=10)


class RAGCustomerCardResponse(RAGCustomerCardBase):
    """Schema fuer Customer Card Response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    summary_text: str
    quick_facts: List[str]
    open_invoices: List[Dict[str, Any]]
    active_contracts: List[Dict[str, Any]]
    recent_orders: List[Dict[str, Any]]
    total_revenue_ytd: Optional[float]
    total_revenue_last_year: Optional[float]
    average_order_value: Optional[float]
    payment_behavior: Optional[str]
    flags: List[str]
    priority_level: int
    sync_status: RAGSyncStatus
    last_full_sync_at: Optional[datetime]
    source_document_count: int
    created_at: datetime
    updated_at: datetime


class RAGCustomerCardSummary(BaseModel):
    """Kurze Zusammenfassung einer Customer Card."""
    customer_id: str
    customer_name: str
    customer_type: Optional[str]
    priority_level: int
    flags: List[str]
    last_sync_at: Optional[datetime]


# ============================================================================
# CHAT SESSIONS & MESSAGES
# ============================================================================

class RAGChatMessageBase(BaseModel):
    """Basis Schema fuer Chat Messages."""
    role: RAGChatRole
    content: str = Field(..., min_length=1)


class RAGChatMessageCreate(RAGChatMessageBase):
    """Schema zum Erstellen einer Chat Message."""
    attached_document_id: Optional[UUID] = None


class AttachedDocumentInfo(BaseModel):
    """Embedded Info ueber angehaengtes Dokument."""
    id: UUID
    name: str


class RAGChatMessageResponse(RAGChatMessageBase):
    """Schema fuer Chat Message Response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    thinking_content: Optional[str]
    confidence_score: Optional[float]
    model_used: Optional[str]
    tokens_input: Optional[int]
    tokens_output: Optional[int]
    generation_time_ms: Optional[int]
    created_at: datetime
    attached_document: Optional[AttachedDocumentInfo] = None


class RAGChatSessionCreate(BaseModel):
    """Schema zum Erstellen einer Chat Session."""
    title: Optional[str] = Field(None, max_length=255)
    context_type: Optional[RAGContextType] = None
    context_id: Optional[str] = Field(None, max_length=255)


class RAGChatSessionResponse(BaseModel):
    """Schema fuer Chat Session Response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    session_token: str
    title: Optional[str]
    context_type: Optional[str]
    context_id: Optional[str]
    status: str
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime]


class RAGChatSessionWithMessages(RAGChatSessionResponse):
    """Chat Session mit allen Messages."""
    messages: List[RAGChatMessageResponse] = Field(default_factory=list)


# ============================================================================
# CHAT REQUESTS
# ============================================================================

class RAGChatRequest(BaseModel):
    """Request fuer Chat-Nachricht."""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[UUID] = None
    context_type: RAGContextType = Field(default=RAGContextType.GENERAL)
    context_id: Optional[str] = Field(None, max_length=255)
    realtime: bool = Field(default=False, description="Fuer schnellen Telefon-Support")
    stream: bool = Field(default=False, description="Streaming Response aktivieren")


class RAGChatResponse(BaseModel):
    """Response fuer Chat-Nachricht."""
    session_id: UUID
    message: str
    thinking_content: Optional[str] = None
    sources: List[RAGChunkSearchResult] = Field(default_factory=list)
    model_used: str
    generation_time_ms: int


# ============================================================================
# SEARCH REQUESTS
# ============================================================================

class RAGSearchRequest(BaseModel):
    """Request fuer semantische Suche."""
    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=20, ge=1, le=100)
    threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    document_ids: Optional[List[UUID]] = None
    section_types: Optional[List[RAGSectionType]] = None
    search_type: RAGSearchType = Field(default=RAGSearchType.SEMANTIC)
    rerank: bool = Field(default=True)
    rerank_top_k: int = Field(default=10, ge=1, le=50)


class RAGSearchResponse(BaseModel):
    """Response fuer Suche."""
    query: str
    search_type: RAGSearchType
    results: List[RAGChunkSearchResult]
    total_results: int
    search_time_ms: int
    embedding_time_ms: Optional[int] = None
    rerank_time_ms: Optional[int] = None


# ============================================================================
# BATCH JOBS
# ============================================================================

class RAGBatchJobCreate(BaseModel):
    """Schema zum Erstellen eines Batch Jobs."""
    job_type: RAGJobType
    job_name: Optional[str] = Field(None, max_length=255)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    scheduled_at: Optional[datetime] = None


class RAGBatchJobResponse(BaseModel):
    """Schema fuer Batch Job Response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_type: str
    job_name: Optional[str]
    created_by_id: Optional[UUID]
    status: RAGJobStatus
    progress_percent: int
    progress_message: Optional[str]
    items_total: Optional[int]
    items_processed: int
    items_failed: int
    result: Optional[Dict[str, Any]]
    error_message: Optional[str]
    retry_count: int
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class RAGBatchJobSummary(BaseModel):
    """Kurze Zusammenfassung eines Batch Jobs."""
    id: UUID
    job_type: str
    status: RAGJobStatus
    progress_percent: int
    items_processed: int
    items_total: Optional[int]
    started_at: Optional[datetime]


# ============================================================================
# CHUNKING
# ============================================================================

class RAGChunkDocumentRequest(BaseModel):
    """Request zum Chunken eines Dokuments."""
    document_id: UUID
    strategy: str = Field(default="semantic", description="Chunking-Strategie: semantic, fixed, document_type")
    chunk_size: Optional[int] = Field(None, ge=100, le=4096)
    chunk_overlap: Optional[int] = Field(None, ge=0, le=512)
    generate_embeddings: bool = Field(default=True)


class RAGChunkDocumentResponse(BaseModel):
    """Response nach Chunking."""
    document_id: UUID
    chunks_created: int
    total_tokens: int
    strategy_used: str
    processing_time_ms: int


class RAGBulkChunkRequest(BaseModel):
    """Request fuer Bulk-Chunking."""
    document_ids: Optional[List[UUID]] = Field(None, description="Spezifische Dokumente oder alle")
    force: bool = Field(default=False, description="Bereits gechunkte Dokumente ueberschreiben")
    strategy: str = Field(default="semantic")


# ============================================================================
# ANALYTICS
# ============================================================================

class RAGAnalyticsEvent(BaseModel):
    """Analytics Event."""
    event_type: str
    query_text: Optional[str] = None
    results_count: Optional[int] = None
    top_result_score: Optional[float] = None
    total_latency_ms: Optional[int] = None
    llm_model_used: Optional[str] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    feedback_rating: Optional[int] = Field(None, ge=1, le=5)
    feedback_text: Optional[str] = None


class RAGAnalyticsSummary(BaseModel):
    """Analytics Zusammenfassung."""
    period_start: datetime
    period_end: datetime
    total_searches: int
    total_chats: int
    avg_search_latency_ms: float
    avg_chat_latency_ms: float
    avg_feedback_rating: Optional[float]
    top_queries: List[Dict[str, Any]]


# ============================================================================
# LLM MODELS
# ============================================================================

class RAGLLMModelResponse(BaseModel):
    """Schema fuer LLM Model Response."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    model_name: str
    model_type: str
    provider: str
    parameters_billions: Optional[float]
    context_window: Optional[int]
    quantization: Optional[str]
    use_case: Optional[str]
    is_active: bool
    avg_tokens_per_second: Optional[float]
    avg_latency_ms: Optional[int]
