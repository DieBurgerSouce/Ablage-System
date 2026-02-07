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
from typing import Optional, List, Dict, Any, Union
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


# ============================================================================
# CHAT SHARING
# ============================================================================

class ChatSessionAccessLevel(str, Enum):
    """Zugriffsebenen fuer Chat Session Sharing."""
    VIEW = "view"
    CONTRIBUTE = "contribute"
    MANAGE = "manage"


class ChatSessionShareRequest(BaseModel):
    """Request zum Teilen einer Chat Session."""
    user_id: UUID = Field(..., description="ID des Benutzers der Zugriff erhaelt")
    access_level: ChatSessionAccessLevel = Field(
        default=ChatSessionAccessLevel.VIEW,
        description="Zugriffsebene: view, contribute, manage"
    )


class ChatSessionCollaboratorResponse(BaseModel):
    """Response fuer einen Collaborator."""
    user_id: str
    username: str
    email: Optional[str]
    access_level: str
    is_owner: bool
    granted_at: Optional[str]


class ChatSessionSharedResponse(RAGChatSessionResponse):
    """Chat Session Response mit Sharing-Infos."""
    access_level: str = Field(..., description="Eigenes Zugriffslevel")
    is_shared: bool = Field(default=True, description="Session ist geteilt")
    collaborator_count: int = Field(default=0, description="Anzahl Collaborators")


# ============================================================================
# BUSINESS INTELLIGENCE
# ============================================================================

class BIQueryType(str, Enum):
    """Types of business intelligence queries."""
    DOCUMENT_SEARCH = "document_search"
    INVOICE_ANALYSIS = "invoice_analysis"
    ENTITY_STATISTICS = "entity_statistics"
    PAYMENT_PREDICTION = "payment_prediction"
    TREND_ANALYSIS = "trend_analysis"
    SUMMARY = "summary"


class BITimeRange(str, Enum):
    """Predefined time ranges for analysis."""
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_QUARTER = "last_quarter"
    LAST_YEAR = "last_year"
    THIS_MONTH = "this_month"
    THIS_QUARTER = "this_quarter"
    THIS_YEAR = "this_year"
    ALL_TIME = "all_time"
    CUSTOM = "custom"


class BIQueryRequest(BaseModel):
    """Request fuer eine Business Intelligence Anfrage."""
    query: str = Field(..., min_length=3, max_length=1000, description="Natuerlichsprachige Anfrage")
    time_range: Optional[BITimeRange] = Field(default=BITimeRange.THIS_YEAR, description="Zeitraum fuer Analyse")
    custom_start_date: Optional[datetime] = Field(None, description="Start-Datum bei custom time_range")
    custom_end_date: Optional[datetime] = Field(None, description="End-Datum bei custom time_range")
    entity_id: Optional[UUID] = Field(None, description="Optional: Filter auf spezifische Entitaet")
    entity_name: Optional[str] = Field(None, max_length=255, description="Optional: Entitaetsname fuer Suche")
    include_suggestions: bool = Field(default=True, description="Follow-up Vorschlaege einschliessen")


class BIDocumentResult(BaseModel):
    """Einzelnes Dokumenten-Suchergebnis."""
    document_id: UUID
    filename: str
    document_type: Optional[str]
    entity_name: Optional[str]
    created_at: datetime
    match_reason: str
    relevance_score: float = Field(ge=0.0, le=1.0)


class BIInvoiceAnalysis(BaseModel):
    """Ergebnis einer Rechnungsanalyse."""
    total_count: int = Field(ge=0)
    total_amount: float
    paid_count: int = Field(ge=0)
    paid_amount: float
    open_count: int = Field(ge=0)
    open_amount: float
    overdue_count: int = Field(ge=0)
    overdue_amount: float
    average_payment_days: Optional[float]
    by_month: List[Dict[str, Any]] = Field(default_factory=list)
    by_entity: List[Dict[str, Any]] = Field(default_factory=list)


class BIEntityStatistics(BaseModel):
    """Statistiken fuer eine Geschaeftsentitaet."""
    entity_id: UUID
    entity_name: str
    entity_type: str
    document_count: int = Field(ge=0)
    invoice_count: int = Field(ge=0)
    total_revenue: float
    total_open: float
    average_payment_days: Optional[float]
    risk_score: Optional[int] = Field(None, ge=0, le=100)
    last_activity: Optional[datetime]


class BIPaymentPrediction(BaseModel):
    """Zahlungsvorhersage fuer eine Entitaet."""
    entity_id: Optional[UUID]
    entity_name: Optional[str]
    predicted_days: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    historical_avg_days: float
    recent_trend: str = Field(..., description="improving, stable, worsening, unknown")
    factors: List[str] = Field(default_factory=list)


class BITrendDataPoint(BaseModel):
    """Einzelner Datenpunkt in einer Trend-Analyse."""
    period: str
    value: float
    count: int = Field(ge=0)
    change_percent: Optional[float]


class BITrendAnalysis(BaseModel):
    """Ergebnis einer Trend-Analyse."""
    metric: str
    time_range: str
    total: float
    average: float
    trend_direction: str = Field(..., description="up, down, stable")
    change_percent: float
    data_points: List[BITrendDataPoint] = Field(default_factory=list)


class BIQueryResponse(BaseModel):
    """Antwort auf eine Business Intelligence Anfrage."""
    query_type: BIQueryType
    summary: str = Field(..., description="Menschenlesbare Zusammenfassung auf Deutsch")
    data: Optional[Dict[str, object]] = Field(None, description="Strukturierte Daten je nach query_type")
    suggestions: List[str] = Field(default_factory=list, description="Follow-up Fragen")
    query_time_ms: int = Field(ge=0)

    model_config = ConfigDict(from_attributes=True)


class BIChatRequest(BaseModel):
    """Chat-Anfrage mit optionalem BI-Kontext."""
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[UUID] = None
    context_type: Optional[RAGContextType] = None
    context_id: Optional[str] = None
    enable_bi: bool = Field(default=True, description="Business Intelligence aktivieren")
    time_range: Optional[BITimeRange] = Field(default=None, description="Zeitraum fuer BI-Anfragen")
    realtime: bool = Field(default=False, description="Realtime-Modus verwenden")


class BIChatResponse(BaseModel):
    """Chat-Antwort mit RAG- und BI-Kontext."""
    session_id: UUID
    message: str
    thinking_content: Optional[str] = None
    sources: List["RAGChunkSearchResult"] = Field(default_factory=list, description="RAG-Quellen")
    bi_insights: Optional[BIQueryResponse] = Field(None, description="Business Intelligence Ergebnisse")
    model_used: str
    tokens_input: int
    tokens_output: int
    generation_time_ms: int

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# AI ASSISTANT ACTIONS
# ============================================================================

class AIActionType(str, Enum):
    """Typen von AI-Aktionen."""
    # Read-Only Actions (Viewer+)
    SEARCH_DOCUMENTS = "search_documents"
    ANALYZE_ENTITY = "analyze_entity"
    GENERATE_REPORT = "generate_report"
    EXPLAIN_DOCUMENT = "explain_document"

    # Supervised Actions (Editor+)
    CATEGORIZE_DOCUMENT = "categorize_document"
    TAG_DOCUMENT = "tag_document"
    LINK_ENTITY = "link_entity"
    CREATE_REMINDER = "create_reminder"

    # Autonomous Actions (Admin only)
    APPROVE_VALIDATION = "approve_validation"
    TRIGGER_OCR = "trigger_ocr"
    SEND_NOTIFICATION = "send_notification"
    BULK_CATEGORIZE = "bulk_categorize"


class AIActionAutonomyLevel(str, Enum):
    """Autonomie-Stufen fuer AI-Aktionen."""
    VIEWER = "viewer"      # Read-Only
    EDITOR = "editor"      # Supervised (Vorschlag + Bestaetigung)
    ADMIN = "admin"        # Autonomous (selbststaendig)


class AIActionStatus(str, Enum):
    """Status einer AI-Aktion."""
    PENDING = "pending"
    SUGGESTED = "suggested"     # Wartet auf User-Bestaetigung
    CONFIRMED = "confirmed"     # User hat bestaetigt
    EXECUTING = "executing"
    COMPLETED = "completed"
    REJECTED = "rejected"       # User hat abgelehnt
    FAILED = "failed"


class AIActionParameter(BaseModel):
    """Parameter einer AI-Aktion."""
    name: str = Field(..., description="Parameter-Name")
    value: Union[str, int, float, bool] = Field(..., description="Parameter-Wert")
    label: str = Field(..., description="Anzeige-Label auf Deutsch")
    editable: bool = Field(default=False, description="Kann vom User geaendert werden")


class AIActionRequest(BaseModel):
    """Request fuer eine AI-Aktion."""
    action_type: AIActionType
    context_type: Optional[str] = Field(None, description="Kontext-Typ (document, entity, etc.)")
    context_id: Optional[UUID] = Field(None, description="Kontext-ID (Document-ID, Entity-ID)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Aktions-Parameter")
    auto_execute: bool = Field(default=False, description="Direkt ausfuehren ohne Bestaetigung")


class AIActionSuggestion(BaseModel):
    """Vorgeschlagene AI-Aktion (fuer Editor-Level)."""
    action_id: UUID
    action_type: AIActionType
    title: str = Field(..., description="Titel der Aktion auf Deutsch")
    description: str = Field(..., description="Beschreibung was passiert")
    parameters: List[AIActionParameter] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence-Score")
    requires_confirmation: bool = Field(default=True)
    estimated_impact: str = Field(..., description="Geschaetzter Einfluss")


class AIActionConfirmRequest(BaseModel):
    """Bestaetigung einer vorgeschlagenen Aktion."""
    action_id: UUID
    confirmed: bool = Field(..., description="True = bestaetigen, False = ablehnen")
    modified_parameters: Optional[Dict[str, Any]] = Field(None, description="Geaenderte Parameter")


class AIActionResult(BaseModel):
    """Ergebnis einer AI-Aktion."""
    action_id: UUID
    action_type: AIActionType
    status: AIActionStatus
    message: str = Field(..., description="Ergebnis-Nachricht auf Deutsch")
    details: Optional[Dict[str, Any]] = Field(None, description="Zusaetzliche Details")
    affected_items: List[UUID] = Field(default_factory=list, description="Betroffene IDs")
    execution_time_ms: int = Field(ge=0)


class AIActionListResponse(BaseModel):
    """Liste verfuegbarer AI-Aktionen basierend auf Rolle."""
    available_actions: List[Dict[str, Any]] = Field(default_factory=list)
    autonomy_level: AIActionAutonomyLevel
    pending_suggestions: int = Field(ge=0, description="Anzahl wartender Vorschlaege")


class AIContextInfo(BaseModel):
    """Kontext-Information fuer AI-Assistent."""
    page_type: str = Field(..., description="Aktueller Seitentyp")
    document_id: Optional[UUID] = Field(None)
    entity_id: Optional[UUID] = Field(None)
    suggestions: List[str] = Field(default_factory=list, description="Kontext-spezifische Vorschlaege")
    available_actions: List[AIActionType] = Field(default_factory=list)
