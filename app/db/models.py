"""SQLAlchemy database models for Ablage-System."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import Column, String, Integer, DateTime, Boolean, Float, Text, JSON, ForeignKey, Index, Table
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.types import TypeDecorator
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func


class CrossDBJSON(TypeDecorator):
    """Cross-database JSON type - uses JSONB on PostgreSQL, JSON on SQLite."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())


class CrossDBTSVector(TypeDecorator):
    """Cross-database TSVector type - uses TSVECTOR on PostgreSQL, Text on SQLite."""
    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(TSVECTOR())
        return dialect.type_descriptor(Text())


class CrossDBVector(TypeDecorator):
    """Cross-database Vector type - uses pgvector on PostgreSQL, Text on SQLite."""
    impl = Text
    cache_ok = True

    def __init__(self, dim: int = 1024):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())


Base = declarative_base()

# Association table for document tags
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE")),
    Index("ix_document_tags_document_id", "document_id"),
    Index("ix_document_tags_tag_id", "tag_id")
)


class ProcessingStatus(str, Enum):
    """Document processing status enum."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OCRBackend(str, Enum):
    """Available OCR backends."""
    AUTO = "auto"
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    SURYA = "surya"
    SURYA_GPU = "surya_gpu"


class DocumentType(str, Enum):
    """Document type classification."""
    INVOICE = "invoice"
    CONTRACT = "contract"
    RECEIPT = "receipt"
    FORM = "form"
    LETTER = "letter"
    REPORT = "report"
    OTHER = "other"


class Document(Base):
    """Document model for storing uploaded documents."""
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    checksum = Column(String(64))  # SHA256 hash

    # Document metadata
    document_type = Column(String(50), default=DocumentType.OTHER)
    status = Column(String(50), default=ProcessingStatus.PENDING, nullable=False)
    page_count = Column(Integer)

    # OCR results
    extracted_text = Column(Text)
    ocr_backend_used = Column(String(50))
    ocr_confidence = Column(Float)
    processing_duration_ms = Column(Integer)

    # German validation
    has_umlauts = Column(Boolean, default=False)
    german_validation_score = Column(Float)
    detected_language = Column(String(10))

    # Metadata and dates
    document_metadata = Column(CrossDBJSON, default={})
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    processed_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Version tracking
    current_version_number = Column(Integer, default=0)
    total_versions = Column(Integer, default=0)

    # Search vectors (Full-Text Search + Semantic Search)
    search_vector = Column(CrossDBTSVector)  # PostgreSQL tsvector for FTS with german_text config
    embedding = Column(CrossDBVector(1024))  # pgvector for semantic search (multilingual-e5-large)
    embedding_updated_at = Column(DateTime(timezone=True))
    embedding_model = Column(String(100))  # Model used to generate embedding

    # Relationships
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    owner = relationship("User", back_populates="documents")
    tags = relationship("Tag", secondary=document_tags, back_populates="documents")
    processing_jobs = relationship("ProcessingJob", back_populates="document", cascade="all, delete-orphan")
    ocr_results = relationship("OCRResult", back_populates="document", cascade="all, delete-orphan")
    ocr_versions = relationship(
        "OCRResultVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="OCRResultVersion.version_number.desc()"
    )

    # Indexes
    __table_args__ = (
        Index("ix_documents_status", "status"),
        Index("ix_documents_upload_date", "upload_date"),
        Index("ix_documents_owner_id", "owner_id"),
        Index("ix_documents_checksum", "checksum"),
    )


class User(Base):
    """User model for authentication and ownership."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))

    # User settings
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    preferred_language = Column(String(10), default="de")
    preferred_ocr_backend = Column(String(50), default=OCRBackend.AUTO)

    # Quota settings
    daily_quota = Column(Integer, default=100)
    documents_processed_today = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))

    # Relationships
    documents = relationship("Document", back_populates="owner")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")


class ProcessingJob(Base):
    """Async processing job tracking."""
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))

    # Job details
    job_type = Column(String(50), nullable=False)  # ocr, validation, export, etc.
    backend = Column(String(50))
    status = Column(String(50), default=ProcessingStatus.QUEUED, nullable=False)
    priority = Column(Integer, default=5)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Results and errors
    result = Column(CrossDBJSON, default={})
    error_message = Column(Text)
    worker_id = Column(String(100))

    # Relationships
    document = relationship("Document", back_populates="processing_jobs")

    # Indexes
    __table_args__ = (
        Index("ix_processing_jobs_status", "status"),
        Index("ix_processing_jobs_created_at", "created_at"),
        Index("ix_processing_jobs_document_id", "document_id"),
    )


class OCRResult(Base):
    """Detailed OCR results with layout and confidence data."""
    __tablename__ = "ocr_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))
    job_id = Column(UUID(as_uuid=True), ForeignKey("processing_jobs.id", ondelete="SET NULL"))

    # OCR details
    backend = Column(String(50), nullable=False)
    extracted_text = Column(Text)
    confidence_score = Column(Float)
    word_count = Column(Integer)
    char_count = Column(Integer)

    # Layout detection
    detected_layout = Column(CrossDBJSON, default={})  # Regions, tables, images
    bounding_boxes = Column(CrossDBJSON, default=[])   # Word/line bounding boxes
    page_number = Column(Integer)

    # German specific results
    detected_dates = Column(CrossDBJSON, default=[])
    detected_amounts = Column(CrossDBJSON, default=[])
    detected_ibans = Column(CrossDBJSON, default=[])
    detected_vat_ids = Column(CrossDBJSON, default=[])
    business_terms = Column(CrossDBJSON, default=[])

    # Metadata
    processing_time_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", back_populates="ocr_results")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_results_document_id", "document_id"),
        Index("ix_ocr_results_confidence", "confidence_score"),
    )


class OCRResultVersion(Base):
    """OCR result version history for document versioning.

    Stores snapshots of OCR results to enable version tracking,
    comparison, and rollback functionality.
    """
    __tablename__ = "ocr_result_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    ocr_result_id = Column(UUID(as_uuid=True), ForeignKey("ocr_results.id", ondelete="SET NULL"))

    # Version metadata
    version_number = Column(Integer, nullable=False)
    is_current = Column(Boolean, default=False, nullable=False)
    is_rollback = Column(Boolean, default=False)
    rollback_from_version = Column(Integer)  # If rollback, from which version

    # OCR data snapshot (copied from OCRResult for historical preservation)
    backend = Column(String(50), nullable=False)
    extracted_text = Column(Text)
    confidence_score = Column(Float)
    word_count = Column(Integer)
    char_count = Column(Integer)

    # German-specific data
    detected_dates = Column(CrossDBJSON, default=[])
    detected_amounts = Column(CrossDBJSON, default=[])
    detected_ibans = Column(CrossDBJSON, default=[])
    detected_vat_ids = Column(CrossDBJSON, default=[])
    business_terms = Column(CrossDBJSON, default=[])

    # Layout data
    detected_layout = Column(CrossDBJSON, default={})
    bounding_boxes = Column(CrossDBJSON, default=[])

    # Processing metadata
    processing_time_ms = Column(Integer)
    german_validation_score = Column(Float)
    has_umlauts = Column(Boolean, default=False)

    # Version metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    version_note = Column(String(500))  # Optional user note for this version

    # Relationships
    document = relationship("Document", back_populates="ocr_versions")
    created_by = relationship("User")

    # Indexes for efficient queries
    __table_args__ = (
        Index("ix_ocr_versions_document_id", "document_id"),
        Index("ix_ocr_versions_version_number", "document_id", "version_number"),
        Index("ix_ocr_versions_is_current", "document_id", "is_current"),
        Index("ix_ocr_versions_created_at", "created_at"),
    )


class Tag(Base):
    """Document tags for categorization."""
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    color = Column(String(7))  # Hex color code

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    documents = relationship("Document", secondary=document_tags, back_populates="tags")


class APIKey(Base):
    """API key management for programmatic access."""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))

    key_hash = Column(String(255), unique=True, nullable=False)
    name = Column(String(100))
    description = Column(String(255))

    # Permissions and limits
    is_active = Column(Boolean, default=True)
    permissions = Column(CrossDBJSON, default=[])
    rate_limit = Column(Integer, default=1000)  # Requests per hour

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))

    # Relationships
    user = relationship("User", back_populates="api_keys")


class AuditLog(Base):
    """Audit log for DSGVO compliance."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Action details
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(UUID(as_uuid=True))

    # Request details
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    request_method = Column(String(10))
    request_path = Column(String(255))

    # Additional data
    audit_metadata = Column(CrossDBJSON, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    # Indexes
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )


class SystemMetrics(Base):
    """System performance and usage metrics."""
    __tablename__ = "system_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Metric details
    metric_type = Column(String(50), nullable=False)  # gpu_usage, memory, processing_speed
    metric_value = Column(Float, nullable=False)
    metric_unit = Column(String(20))

    # Context
    backend = Column(String(50))
    worker_id = Column(String(100))

    # Metadata
    metric_metadata = Column(CrossDBJSON, default={})
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_system_metrics_timestamp", "timestamp"),
        Index("ix_system_metrics_type", "metric_type"),
    )


class SearchAnalytics(Base):
    """Search analytics for tracking search patterns and performance.

    Tracks search queries, result counts, and user engagement to
    improve search quality and understand usage patterns.
    """
    __tablename__ = "search_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Query details
    query = Column(String(500), nullable=False)
    search_type = Column(String(20), nullable=False)  # fts, semantic, hybrid
    query_length = Column(Integer)

    # Filter tracking
    filters_used = Column(CrossDBJSON, default={})  # Which filters were applied
    has_document_type_filter = Column(Boolean, default=False)
    has_date_filter = Column(Boolean, default=False)
    has_tag_filter = Column(Boolean, default=False)
    has_status_filter = Column(Boolean, default=False)

    # Results
    total_results = Column(Integer, default=0)
    results_returned = Column(Integer, default=0)  # Actual page size
    page_number = Column(Integer, default=1)

    # Performance metrics
    execution_time_ms = Column(Integer)  # Total query time
    fts_time_ms = Column(Integer)  # FTS component time
    semantic_time_ms = Column(Integer)  # Embedding lookup time

    # User engagement (updated via separate endpoints)
    clicked_results = Column(Integer, default=0)
    first_click_position = Column(Integer)  # Position of first clicked result
    downloaded_count = Column(Integer, default=0)

    # Session tracking
    session_id = Column(String(100))  # To group searches in a session
    is_refinement = Column(Boolean, default=False)  # Is this a refined search?
    previous_query_id = Column(UUID(as_uuid=True))  # If refined, link to previous

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    user_agent = Column(String(255))
    ip_address = Column(String(45))  # For aggregate analysis only

    # Relationships
    user = relationship("User")

    # Indexes for efficient analytics queries
    __table_args__ = (
        Index("ix_search_analytics_created_at", "created_at"),
        Index("ix_search_analytics_user_id", "user_id"),
        Index("ix_search_analytics_search_type", "search_type"),
        Index("ix_search_analytics_query_pattern", "query", postgresql_ops={"query": "varchar_pattern_ops"}),
    )
