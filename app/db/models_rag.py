"""RAG Intelligence Layer Models.

Modularisierung Phase 1.1 - Ausgelagert aus app/db/models.py.
Re-Exports erfolgen in models.py für Rückwärtskompatibilität.
"""

from datetime import datetime, timezone
from typing import Optional
from enum import Enum
import uuid

from sqlalchemy import Column, String, Integer, DateTime, Boolean, Float, Text, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models_base import Base, CrossDBJSON, CrossDBVector


# ============================================================================
# RAG INTELLIGENCE LAYER MODELS
# ============================================================================

class RAGSectionType(str, Enum):
    """Chunk Section Types für RAG."""
    HEADER = "header"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class RAGSyncStatus(str, Enum):
    """Synchronisations-Status für Customer Cards."""
    PENDING = "pending"
    SYNCING = "syncing"
    COMPLETED = "completed"
    ERROR = "error"


class RAGChatRole(str, Enum):
    """Chat Message Rollen."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class RAGLLMModelType(str, Enum):
    """LLM Model Typen."""
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANKER = "reranker"


class RAGJobType(str, Enum):
    """RAG Batch Job Typen."""
    CUSTOMER_CARD_SYNC = "customer_card_sync"
    SYNC_CARDS = "sync_cards"  # Alias für CUSTOMER_CARD_SYNC
    REPORT_GENERATION = "report_generation"
    REEMBEDDING = "reembedding"
    CHUNK_DOCUMENTS = "chunk_documents"
    CHUNK_ALL = "chunk_all"
    REBUILD_EMBEDDINGS = "rebuild_embeddings"


class RAGJobStatus(str, Enum):
    """RAG Batch Job Status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Aliase für API-Kompatibilität
RAGBatchJobType = RAGJobType
RAGBatchJobStatus = RAGJobStatus
RAGCardSyncStatus = RAGSyncStatus


class RAGCardPriorityLevel(str, Enum):
    """Customer Card Priority Levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class RAGContextType(str, Enum):
    """Chat Context Types für RAG-Kontext."""
    GENERAL = "general"
    CUSTOMER = "customer"
    DOCUMENT = "document"
    REPORT = "report"


class RAGDocumentChunk(Base):
    """
    Chunked Document für RAG Retrieval.

    Speichert Text-Chunks mit Embeddings für semantische Suche.
    Jedes Dokument wird in mehrere Chunks aufgeteilt basierend auf
    Dokumenttyp und Inhalt (semantic chunking).
    """
    __tablename__ = "rag_document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zum Original-Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Chunk-Metadaten
    chunk_index = Column(Integer, nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_tokens = Column(Integer, nullable=False)

    # Positionierung im Dokument
    page_number = Column(Integer, nullable=True)
    section_type = Column(String(50), nullable=True)  # header, paragraph, table, list, footer
    bounding_box = Column(CrossDBJSON, nullable=True)  # {"x": 0, "y": 0, "width": 100, "height": 50}

    # Embedding (pgvector) - nullable weil Chunks zuerst erstellt und dann asynchron embedded werden
    embedding = Column(CrossDBVector(1024), nullable=True)

    # Embedding-Metadaten
    embedding_model = Column(String(100), nullable=False, default="intfloat/multilingual-e5-large")
    embedding_created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Qdrant Vector Search (A/B Testing mit Jina-DE)
    qdrant_indexed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="chunks")

    __table_args__ = (
        Index("ix_rag_chunks_document_id", "document_id"),
        Index("ix_rag_chunks_section_type", "section_type"),
        Index("ix_rag_chunks_page_number", "page_number"),
        Index("ix_rag_chunks_document_index", "document_id", "chunk_index", unique=True),
    )


class RAGCustomerCard(Base):
    """
    Pre-computed Kunden-Zusammenfassung für Real-Time Zugriff.

    Ermöglicht Instant-Zugriff (< 100ms) auf Kundendaten am Telefon.
    Wird naechtlich per Batch-Job aktualisiert oder bei Bedarf manuell.
    """
    __tablename__ = "rag_customer_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # S.3-S.5 SECURITY FIX: Multi-Tenancy - Customer Cards gehoeren zu einer Company
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Kunden-Identifikation (unique pro Company, nicht global)
    customer_id = Column(String(100), nullable=False)
    customer_name = Column(String(255), nullable=False)
    customer_type = Column(String(50), nullable=True)  # Stammkunde, Neukunde, Inaktiv

    # Pre-Computed Summaries (vom LLM generiert)
    summary_text = Column(Text, nullable=False)
    quick_facts = Column(CrossDBJSON, default=list)

    # Strukturierte Daten
    open_invoices = Column(CrossDBJSON, default=list)
    active_contracts = Column(CrossDBJSON, default=list)
    recent_orders = Column(CrossDBJSON, default=list)

    # Metriken
    total_revenue_ytd = Column(Float, nullable=True)
    total_revenue_last_year = Column(Float, nullable=True)
    average_order_value = Column(Float, nullable=True)
    payment_behavior = Column(String(50), nullable=True)  # Puenktlich, Verzögert, Problematisch

    # Flags und Alerts
    flags = Column(CrossDBJSON, default=list)  # ["Zahlungsverzug", "Vertrag läuft aus"]
    priority_level = Column(Integer, default=0)  # 0-10, höher = wichtiger

    # Synchronisation
    last_full_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_incremental_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String(20), default=RAGSyncStatus.PENDING.value)
    sync_error_message = Column(Text, nullable=True)

    # Source Documents
    source_document_count = Column(Integer, default=0)
    source_document_ids = Column(CrossDBJSON, nullable=True)  # List of UUID strings

    # Alias für last_sync_at Kompatibilität
    @property
    def last_sync_at(self):
        """Alias für last_full_sync_at."""
        return self.last_full_sync_at

    # Embedding für semantische Kundensuche
    card_embedding = Column(CrossDBVector(1024), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # S.3-S.5 SECURITY FIX: Unique constraint pro Company statt global
        UniqueConstraint("company_id", "customer_id", name="uq_rag_customer_cards_company_customer"),
        Index("ix_rag_customer_cards_company_id", "company_id"),
        Index("ix_rag_customer_cards_customer_id", "customer_id"),
        Index("ix_rag_customer_cards_type", "customer_type"),
        Index("ix_rag_customer_cards_priority", "priority_level"),
        Index("ix_rag_customer_cards_sync_status", "sync_status"),
    )


class RAGChatSession(Base):
    """
    Chat Session für RAG-basierte Dokumenten-Interaktion.

    Speichert Konversationskontext für:
    - Allgemeine Dokumentenfragen
    - Kundenspezifische Anfragen (Telefon-Support)
    - Dokumentenanalyse
    """
    __tablename__ = "rag_chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User/Session Identifikation
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    session_token = Column(String(255), nullable=False, unique=True)

    # Session Metadaten
    title = Column(String(255), nullable=True)
    context_type = Column(String(50), nullable=True)  # general, customer, document, report
    context_id = Column(String(255), nullable=True)   # z.B. customer_id oder document_id

    # Session Status
    status = Column(String(20), default="active")  # active, archived, deleted
    message_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="rag_chat_sessions")
    messages = relationship("RAGChatMessage", back_populates="session", cascade="all, delete-orphan")
    shared_access = relationship("ChatSessionAccess", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_rag_chat_sessions_user", "user_id"),
        Index("ix_rag_chat_sessions_context", "context_type", "context_id"),
        Index("ix_rag_chat_sessions_status", "status"),
    )


class RAGChatMessage(Base):
    """
    Einzelne Nachricht in einer RAG Chat Session.

    Speichert User-Fragen und LLM-Antworten mit Quellen-Referenzen
    für Nachvollziehbarkeit.
    """
    __tablename__ = "rag_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zur Session
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_chat_sessions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Optionales angehaengtes Dokument (für User-Nachrichten)
    attached_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Message Content
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)

    # Thinking Content (für LLMs mit Thinking Mode)
    thinking_content = Column(Text, nullable=True)

    # Für Assistant Messages: Quellen
    confidence_score = Column(Float, nullable=True)

    # Model Information
    model_used = Column(String(100), nullable=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)
    generation_time_ms = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("RAGChatSession", back_populates="messages")
    attached_document = relationship("Document", foreign_keys=[attached_document_id])

    __table_args__ = (
        Index("ix_rag_chat_messages_session", "session_id"),
        Index("ix_rag_chat_messages_created", "created_at"),
        Index("ix_rag_chat_messages_role", "role"),
    )


class RAGLLMModel(Base):
    """
    LLM Model Registry für RAG Intelligence Layer.

    Speichert Konfiguration und Performance-Metriken
    für alle verwendeten Modelle (Embedding, Chat, Reranking).
    """
    __tablename__ = "rag_llm_models"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Model Identifikation
    model_name = Column(String(100), nullable=False, unique=True)
    model_type = Column(String(50), nullable=False)  # chat, embedding, reranker
    provider = Column(String(50), nullable=False)    # ollama, llama.cpp, huggingface-tei

    # Model Specs
    parameters_billions = Column(Float, nullable=True)
    context_window = Column(Integer, nullable=True)
    quantization = Column(String(20), nullable=True)  # Q4_K_M, Q8_0, FP16, etc.

    # Resource Requirements
    ram_required_gb = Column(Float, nullable=True)
    vram_required_gb = Column(Float, nullable=True)

    # Performance Metrics
    avg_tokens_per_second = Column(Float, nullable=True)
    avg_latency_ms = Column(Integer, nullable=True)

    # Routing Configuration
    use_case = Column(String(50), nullable=True)  # realtime, batch, embedding, reranking
    priority = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Endpoint Configuration
    endpoint_url = Column(String(255), nullable=True)
    api_key_env_var = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_rag_llm_models_type", "model_type"),
        Index("ix_rag_llm_models_use_case", "use_case"),
        Index("ix_rag_llm_models_active", "is_active"),
    )


class RAGBatchJob(Base):
    """
    Batch Job Tracking für RAG-Operationen.

    Trackt langwierige Jobs wie:
    - Customer Card Synchronisation (naechtlich)
    - Report-Generierung
    - Dokument Re-Embedding
    - Chunk-Generierung
    """
    __tablename__ = "rag_batch_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Job Identifikation
    job_type = Column(String(50), nullable=False)  # customer_card_sync, report_generation, etc.
    job_name = Column(String(255), nullable=True)

    # User der den Job gestartet hat
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Job Parameters
    parameters = Column(CrossDBJSON, default=dict)

    # Status Tracking
    status = Column(String(20), default=RAGJobStatus.PENDING.value)
    progress_percent = Column(Integer, default=0)
    progress_message = Column(Text, nullable=True)
    items_total = Column(Integer, nullable=True)
    items_processed = Column(Integer, default=0)
    items_failed = Column(Integer, default=0)

    # Results
    result = Column(CrossDBJSON, nullable=True)
    output_file_path = Column(String(500), nullable=True)

    # Error Handling
    error_message = Column(Text, nullable=True)
    error_stack = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Timing
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    created_by = relationship("User", backref="rag_batch_jobs")

    __table_args__ = (
        Index("ix_rag_batch_jobs_status", "status"),
        Index("ix_rag_batch_jobs_type", "job_type"),
        Index("ix_rag_batch_jobs_scheduled", "scheduled_at"),
        Index("ix_rag_batch_jobs_created_by", "created_by_id"),
        Index("ix_rag_batch_jobs_type_status", "job_type", "status"),
    )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Berechnet Job-Dauer in Sekunden."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_finished(self) -> bool:
        """Prüft ob Job abgeschlossen ist."""
        return self.status in [RAGJobStatus.COMPLETED.value, RAGJobStatus.FAILED.value, RAGJobStatus.CANCELLED.value]


class RAGAnalytics(Base):
    """
    Analytics und Metriken für RAG-Nutzung.

    Trackt Performance und User-Interaktionen für:
    - Optimierung der Suche
    - Modell-Vergleiche
    - Feedback-Auswertung
    """
    __tablename__ = "rag_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Event Type
    event_type = Column(String(50), nullable=False)  # search, chat, report, customer_card_view

    # Context
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    session_id = Column(UUID(as_uuid=True), nullable=True)

    # Query/Request Details
    query_text = Column(Text, nullable=True)
    query_embedding = Column(CrossDBVector(1024), nullable=True)

    # Results
    results_count = Column(Integer, nullable=True)
    top_result_score = Column(Float, nullable=True)

    # Performance
    total_latency_ms = Column(Integer, nullable=True)
    embedding_latency_ms = Column(Integer, nullable=True)
    search_latency_ms = Column(Integer, nullable=True)
    rerank_latency_ms = Column(Integer, nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)

    # Model Info
    llm_model_used = Column(String(100), nullable=True)
    tokens_input = Column(Integer, nullable=True)
    tokens_output = Column(Integer, nullable=True)

    # User Feedback
    feedback_rating = Column(Integer, nullable=True)  # 1-5
    feedback_text = Column(Text, nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="rag_analytics")

    __table_args__ = (
        Index("ix_rag_analytics_event_type", "event_type"),
        Index("ix_rag_analytics_created", "created_at"),
        Index("ix_rag_analytics_user", "user_id"),
        Index("ix_rag_analytics_event_created", "event_type", "created_at"),
    )
