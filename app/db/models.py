"""SQLAlchemy database models for Ablage-System."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Boolean, Float, Text, JSON, ForeignKey, Index, Table
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
    ORDER = "order"
    CONTRACT = "contract"
    DELIVERY_NOTE = "delivery_note"
    RECEIPT = "receipt"
    FORM = "form"
    LETTER = "letter"
    REPORT = "report"
    OTHER = "other"
    UNKNOWN = "unknown"


class UserTier(str, Enum):
    """User subscription tier for rate limiting."""
    FREE = "free"
    PREMIUM = "premium"
    ADMIN = "admin"


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
    data_category = Column(
        String(50),
        nullable=True,
        default="document_content",
        comment="GDPR Datenkategorie für Aufbewahrungsfristen"
    )
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
    document_metadata = Column(CrossDBJSON, default=dict)
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    processed_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Version tracking
    current_version_number = Column(Integer, default=0)
    total_versions = Column(Integer, default=0)

    # Soft-Delete for GDPR (Phase 2.3)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Search vectors (Full-Text Search + Semantic Search)
    search_vector = Column(CrossDBTSVector)  # PostgreSQL tsvector for FTS with german_text config
    embedding = Column(CrossDBVector(1024))  # pgvector for semantic search (multilingual-e5-large)
    embedding_updated_at = Column(DateTime(timezone=True))
    embedding_model = Column(String(100))  # Model used to generate embedding

    # Business Entity and Document Group relationships
    business_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    group_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    page_number_in_group = Column(Integer, nullable=True)  # Seitennummer innerhalb der Gruppe
    is_group_primary = Column(Boolean, default=False)  # Ist das primaere Dokument der Gruppe

    # Structured extracted data (from OCR)
    extracted_data = Column(CrossDBJSON, default=dict)  # Strukturierte OCR-Daten (Rechnungsnr., Datum, etc.)

    # Scan metadata (fuer Gruppierungserkennung)
    scan_timestamp = Column(DateTime(timezone=True), nullable=True)  # Wann wurde gescannt
    scan_batch_id = Column(String(100), nullable=True)  # Scan-Batch ID
    original_filename_sequence = Column(Integer, nullable=True)  # Sequenznummer aus Original-Dateinamen

    # Relationships
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    owner = relationship("User", back_populates="documents", foreign_keys=[owner_id])
    business_entity = relationship("BusinessEntity", back_populates="documents")
    document_group = relationship("DocumentGroup", back_populates="documents", foreign_keys=[group_id])
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
        # Phase 2.3: Index fuer Soft-Delete Queries
        Index("ix_documents_deleted_at", "deleted_at"),
        # Phase 3: Compound Index fuer Owner + Created (haeufige Query)
        Index("ix_documents_owner_created", "owner_id", "created_at"),
        # Phase 8: Additional compound indexes for common query patterns
        Index("ix_documents_status_created", "status", "created_at"),
        Index("ix_documents_owner_status", "owner_id", "status"),
        Index("ix_documents_deleted_owner", "deleted_at", "owner_id"),
        # Business Entity und Group Indexes
        Index("ix_documents_business_entity_id", "business_entity_id"),
        Index("ix_documents_group_id", "group_id"),
        Index("ix_documents_scan_batch_id", "scan_batch_id"),
        Index("ix_documents_entity_created", "business_entity_id", "created_at"),
        Index("ix_documents_group_sequence", "group_id", "page_number_in_group"),
    )

    @property
    def is_deleted(self) -> bool:
        """Check if document is soft-deleted (GDPR Phase 2.3)."""
        return self.deleted_at is not None


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

    # Two-Factor Authentication (2FA/TOTP)
    # Secret ist mit AES-256-GCM verschlüsselt (nonce + ciphertext + tag, Base64-encoded)
    # Länge: ~100 Zeichen für verschlüsselte Daten
    totp_secret = Column(String(256), nullable=True)
    totp_enabled = Column(Boolean, default=False)
    totp_backup_codes = Column(CrossDBJSON, nullable=True)  # Hashed backup codes
    totp_setup_at = Column(DateTime(timezone=True), nullable=True)

    # Admin Console: Tier and Rate Limit Management
    tier = Column(String(20), default=UserTier.FREE)
    rate_limit_hourly = Column(Integer, nullable=True)  # Custom override
    rate_limit_daily = Column(Integer, nullable=True)   # Custom override

    # Admin Console: User Management
    last_activity_at = Column(DateTime(timezone=True))
    password_reset_required = Column(Boolean, default=False)
    deactivated_at = Column(DateTime(timezone=True))
    deactivated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    notes = Column(Text)  # Admin notes about user

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True))

    # GDPR Art. 17 - Right to Erasure (Recht auf Löschung)
    deletion_requested_at = Column(DateTime(timezone=True), nullable=True)
    deletion_scheduled_for = Column(DateTime(timezone=True), nullable=True)
    deletion_reason = Column(String(500), nullable=True)
    deletion_confirmed = Column(Boolean, default=False)

    # Email Verification
    email_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    documents = relationship("Document", back_populates="owner", foreign_keys="Document.owner_id")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    deactivated_by = relationship("User", remote_side="User.id", foreign_keys=[deactivated_by_id])
    roles = relationship(
        "Role",
        secondary="user_roles",
        primaryjoin="User.id == user_roles.c.user_id",
        secondaryjoin="user_roles.c.role_id == Role.id",
        back_populates="users"
    )


class ProcessingJob(Base):
    """Async processing job tracking."""
    __tablename__ = "processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"))

    # Job details
    job_type = Column(String(50), nullable=False)  # ocr, validation, export, etc.
    backend = Column(String(50))
    status = Column(String(50), default=ProcessingStatus.QUEUED, nullable=False)
    progress = Column(Integer, default=0, comment="Fortschritt 0-100%")
    message = Column(String(500), nullable=True, comment="Status-Nachricht")
    priority = Column(Integer, default=5)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Results and errors
    result = Column(CrossDBJSON, default=dict)
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


class BatchJob(Base):
    """Batch job tracking for multiple documents."""
    __tablename__ = "batch_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Batch details
    job_type = Column(String(50), nullable=False)  # ocr, embedding, validation, export
    status = Column(String(50), default=ProcessingStatus.QUEUED, nullable=False)
    priority = Column(Integer, default=5)  # 1=highest, 10=lowest

    # Document tracking
    total_documents = Column(Integer, default=0)
    processed_documents = Column(Integer, default=0)
    failed_documents = Column(Integer, default=0)
    document_ids = Column(CrossDBJSON, default=[])

    # Progress tracking
    progress = Column(Integer, default=0, comment="Fortschritt 0-100%")
    current_document = Column(String(255), nullable=True)
    message = Column(String(500), nullable=True)

    # Configuration
    backend = Column(String(50))
    language = Column(String(10), default="de")
    options = Column(CrossDBJSON, default=dict)

    # Timing
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    estimated_completion = Column(DateTime(timezone=True))

    # Performance metrics
    avg_time_per_document_ms = Column(Integer)
    total_processing_time_ms = Column(Integer)

    # Results
    result_summary = Column(CrossDBJSON, default=dict)
    error_message = Column(Text)
    celery_task_id = Column(String(100))

    # Pause/Resume support
    is_paused = Column(Boolean, default=False)
    paused_at = Column(DateTime(timezone=True))
    resume_from_index = Column(Integer, default=0)

    # Relationships
    user = relationship("User", backref="batch_jobs")

    # Indexes
    __table_args__ = (
        Index("ix_batch_jobs_status", "status"),
        Index("ix_batch_jobs_user_id", "user_id"),
        Index("ix_batch_jobs_created_at", "created_at"),
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
    detected_layout = Column(CrossDBJSON, default=dict)  # Regions, tables, images
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
    detected_layout = Column(CrossDBJSON, default=dict)
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


class Tune(Base):
    """
    Document Context / Tune configuration.
    Defines how a document type should be analyzed and processed.
    """
    __tablename__ = "tunes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(500))
    icon = Column(String(50))  # Lucide icon name
    color = Column(String(50))  # Tailwind class or Hex

    # Intelligence Configuration
    prompt_template = Column(Text, nullable=True)  # Custom system prompt for this tune
    default_backend = Column(String(50), nullable=True)  # Preferred OCR backend

    # Metadata
    is_system = Column(Boolean, default=False)  # System tunes cannot be deleted
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_tunes_name", "name"),
        Index("ix_tunes_is_active", "is_active"),
    )



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
    """
    Audit log for DSGVO compliance.

    Immutability Features (AP6):
    - sequence_number: Eindeutige, aufsteigende Sequenznummer
    - integrity_hash: SHA-256 Hash des Eintrags für Tamper-Detection
    - previous_hash: Hash des vorherigen Eintrags (Blockchain-ähnliche Verkettung)

    SECURITY: Diese Tabelle sollte mit DB-Level-Triggers gegen
    UPDATE/DELETE geschützt sein (siehe Migration 017).
    """
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
    audit_metadata = Column(CrossDBJSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Immutability Fields (AP6: Audit Log Immutabilität)
    # Sequenznummer für geordnete Verkettung
    sequence_number = Column(BigInteger, unique=True, index=True, nullable=True)
    # SHA-256 Hash dieses Eintrags (berechnet aus allen relevanten Feldern)
    integrity_hash = Column(String(64), nullable=True)
    # SHA-256 Hash des vorherigen Eintrags (Verkettung)
    previous_hash = Column(String(64), nullable=True)

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    # Indexes
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_sequence", "sequence_number"),
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
    metric_metadata = Column(CrossDBJSON, default=dict)
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
    filters_used = Column(CrossDBJSON, default=dict)  # Which filters were applied
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


# ============================================================================
# Admin Console Models
# ============================================================================

class AdminAction(Base):
    """Track administrative actions for audit trail.

    Records all admin operations for compliance and accountability.
    Examples: user creation, role changes, password resets, deactivations.
    """
    __tablename__ = "admin_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Action details
    action = Column(String(100), nullable=False)  # create_user, update_user, reset_password, etc.
    action_details = Column(CrossDBJSON, default=dict)  # Specific changes made

    # Request context
    ip_address = Column(String(45))
    user_agent = Column(String(255))

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    admin = relationship("User", foreign_keys=[admin_id], backref="admin_actions_performed")
    target_user = relationship("User", foreign_keys=[target_user_id], backref="admin_actions_received")

    # Indexes
    __table_args__ = (
        Index("ix_admin_actions_admin_id", "admin_id"),
        Index("ix_admin_actions_target_user_id", "target_user_id"),
        Index("ix_admin_actions_created_at", "created_at"),
        Index("ix_admin_actions_action", "action"),
    )


class RateLimitOverride(Base):
    """Custom rate limit overrides per user.

    Allows admins to set custom rate limits that override tier defaults.
    Can be time-limited (valid_until) or permanent.
    """
    __tablename__ = "rate_limit_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    # Rate limit values (null = use tier default)
    ocr_hourly = Column(Integer, nullable=True)
    ocr_daily = Column(Integer, nullable=True)
    batch_hourly = Column(Integer, nullable=True)
    api_per_minute = Column(Integer, nullable=True)

    # Validity period
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True)  # null = permanent

    # Audit trail
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    reason = Column(String(500))  # Why was this override created?

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="rate_limit_override")
    created_by = relationship("User", foreign_keys=[created_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_rate_limit_overrides_user_id", "user_id"),
        Index("ix_rate_limit_overrides_valid_until", "valid_until"),
    )


# ==================== GDPR Compliance Models ====================

class GDPRDeletionRequestStatus(str, Enum):
    """Status für GDPR Löschanfragen (Art. 17 DSGVO)."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class GDPRDeletionRequest(Base):
    """
    GDPR Löschanfrage (Art. 17 DSGVO - Recht auf Löschung).

    Verfolgt Löschanfragen von Benutzern und deren Bearbeitungsstatus.
    Anfragen müssen innerhalb von 30 Tagen bearbeitet werden.
    """
    __tablename__ = "gdpr_deletion_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Request details
    status = Column(String(50), default=GDPRDeletionRequestStatus.PENDING, nullable=False)
    reason = Column(Text, nullable=True)  # Optionaler Grund des Benutzers
    deletion_deadline = Column(DateTime(timezone=True), nullable=False)  # 30 Tage Frist

    # Timestamps
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Audit
    processed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deletion_reason = Column(String(255), nullable=True)  # Warum abgelehnt (falls rejected)

    # Statistics
    documents_deleted = Column(Integer, default=0)
    audit_entries_anonymized = Column(Integer, default=0)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="gdpr_deletion_requests")
    processed_by = relationship("User", foreign_keys=[processed_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_deletion_requests_user_id", "user_id"),
        Index("ix_gdpr_deletion_requests_status", "status"),
        Index("ix_gdpr_deletion_requests_deadline", "deletion_deadline"),
    )


class GDPRBreachLog(Base):
    """
    GDPR Datenschutzvorfall-Log (Art. 33/34 DSGVO).

    Dokumentiert Datenschutzvorfälle und deren Meldung:
    - Art. 33: Meldung an Aufsichtsbehörde (72 Stunden)
    - Art. 34: Meldung an betroffene Personen (bei hohem Risiko)
    """
    __tablename__ = "gdpr_breach_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    breach_id = Column(String(32), unique=True, nullable=False)  # Eindeutige Breach-ID

    # Breach details
    breach_type = Column(String(100), nullable=False)  # unauthorized_access, data_loss, etc.
    affected_records = Column(Integer, default=0)
    description = Column(Text, nullable=False)
    severity = Column(String(20), default="medium")  # low, medium, high, critical

    # Detection & Timeline
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    notification_deadline = Column(DateTime(timezone=True), nullable=False)  # 72 Stunden

    # Notification status
    authority_notified = Column(Boolean, default=False)
    authority_notification_date = Column(DateTime(timezone=True), nullable=True)
    users_notified = Column(Integer, default=0)
    user_notification_date = Column(DateTime(timezone=True), nullable=True)

    # Response
    containment_measures = Column(Text, nullable=True)
    remediation_status = Column(String(50), default="investigating")  # investigating, contained, resolved
    resolution_date = Column(DateTime(timezone=True), nullable=True)

    # Audit
    reported_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    reported_by = relationship("User", backref="reported_breaches")

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_breach_logs_breach_id", "breach_id"),
        Index("ix_gdpr_breach_logs_detected_at", "detected_at"),
        Index("ix_gdpr_breach_logs_severity", "severity"),
        Index("ix_gdpr_breach_logs_remediation_status", "remediation_status"),
    )


class GDPRConsentLog(Base):
    """
    GDPR Einwilligungsprotokoll (Art. 7 DSGVO).

    Dokumentiert Einwilligungen der Benutzer für verschiedene Zwecke.
    """
    __tablename__ = "gdpr_consent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Consent details
    consent_type = Column(String(100), nullable=False)  # data_processing, marketing, analytics
    purpose = Column(String(255), nullable=False)  # Zweck der Einwilligung
    consent_given = Column(Boolean, nullable=False)
    consent_text = Column(Text, nullable=True)  # Text der Einwilligung zum Zeitpunkt

    # Timestamps
    consent_date = Column(DateTime(timezone=True), server_default=func.now())
    withdrawal_date = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Einwilligung läuft ab

    # Source
    source = Column(String(50), default="web")  # web, api, admin
    ip_address = Column(String(45), nullable=True)  # IPv4/IPv6

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="gdpr_consents")

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_consent_logs_user_id", "user_id"),
        Index("ix_gdpr_consent_logs_consent_type", "consent_type"),
        Index("ix_gdpr_consent_logs_consent_date", "consent_date"),
    )


class GDPRProcessingActivity(Base):
    """
    GDPR Verarbeitungsverzeichnis (Art. 30 DSGVO).

    Dokumentiert alle Verarbeitungstätigkeiten gemäß Rechenschaftspflicht.
    Ersetzt die In-Memory-Speicherung in GDPRComplianceManager.

    SECURITY: Dieses Verzeichnis muss bei Audits vorgelegt werden können.
    """
    __tablename__ = "gdpr_processing_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id = Column(String(32), unique=True, nullable=False)  # Hash-basierte ID

    # Document reference
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Subject (anonymized after processing)
    subject_id = Column(String(64), nullable=True)  # Hash des User-IDs

    # Processing details (Art. 30 DSGVO Pflichtangaben)
    data_categories = Column(CrossDBJSON, default=[])  # personal_identifiable, financial, etc.
    processing_purpose = Column(String(100), nullable=False)  # document_digitization, ocr_processing
    legal_basis = Column(String(255), nullable=False)  # Art. 6(1)(b) Contract, etc.

    # Retention
    retention_period_days = Column(Integer, nullable=False)
    retention_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Processing metadata
    processed_by_system = Column(String(100), default="ablage-system-ocr")
    processing_backend = Column(String(50), nullable=True)  # deepseek, got_ocr, etc.

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Data transfer (Art. 30(1)(e) DSGVO)
    data_recipients = Column(CrossDBJSON, default=[])  # Empty if no transfer
    third_country_transfer = Column(Boolean, default=False)

    # Technical measures (Art. 32 DSGVO)
    encryption_applied = Column(Boolean, default=True)
    pseudonymization_applied = Column(Boolean, default=False)

    # Relationships
    document = relationship("Document", backref="gdpr_activities")

    # Indexes
    __table_args__ = (
        Index("ix_gdpr_processing_activities_activity_id", "activity_id"),
        Index("ix_gdpr_processing_activities_document_id", "document_id"),
        Index("ix_gdpr_processing_activities_subject_id", "subject_id"),
        Index("ix_gdpr_processing_activities_created_at", "created_at"),
        Index("ix_gdpr_processing_activities_purpose", "processing_purpose"),
        Index("ix_gdpr_processing_activities_retention", "retention_expires_at"),
    )


# ==================== Password Reset Models ====================

class PasswordResetToken(Base):
    """
    Password Reset Token für sicheren Passwort-Reset.

    Sicherheitsmerkmale:
    - Token wird gehasht gespeichert (SHA-256)
    - Zeitlich begrenzte Gültigkeit (1 Stunde)
    - Einmalige Verwendung
    - Rate-Limiting über MAX_ACTIVE_TOKENS_PER_USER

    OWASP-konform: Token-basierter Reset ohne Sicherheitsfragen.
    """
    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Token (nur Hash gespeichert!)
    token_hash = Column(String(64), nullable=False, unique=True)  # SHA-256 hash

    # Validity
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)  # Null = ungenutzt

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String(45), nullable=True)  # IP bei Anfrage

    # Relationships
    user = relationship("User", backref="password_reset_tokens")

    # Indexes
    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
        Index("ix_password_reset_tokens_token_hash", "token_hash"),
        Index("ix_password_reset_tokens_expires_at", "expires_at"),
    )


# ============================================================================
# GDPR Art. 20 - Data Portability
# ============================================================================

class ExportStatus(str, Enum):
    """Data export status for GDPR Art. 20."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ExportFormat(str, Enum):
    """Supported export formats for GDPR Art. 20."""
    JSON = "json"
    CSV = "csv"


class DataExport(Base):
    """
    GDPR Art. 20 - Data Export Request.

    Ermöglicht Benutzern den Export ihrer Daten in maschinenlesbarem Format.
    Exports sind 7 Tage gültig und werden danach automatisch gelöscht.
    """
    __tablename__ = "data_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Export Status
    status = Column(String(50), default=ExportStatus.PENDING, nullable=False)
    format = Column(String(20), default=ExportFormat.JSON, nullable=False)

    # File Information
    file_path = Column(String(500), nullable=True)  # MinIO path
    file_size_bytes = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # 7 Tage nach Erstellung

    # Download Tracking
    download_count = Column(Integer, default=0)

    # Relationships
    user = relationship("User", backref="data_exports")

    # Indexes
    __table_args__ = (
        Index("ix_data_exports_user_id", "user_id"),
        Index("ix_data_exports_status", "status"),
        Index("ix_data_exports_expires_at", "expires_at"),
    )


# ============================================================================
# Role-Based Access Control (RBAC)
# ============================================================================

class PermissionAction(str, Enum):
    """Verfügbare Permission-Aktionen."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    MANAGE = "manage"  # Vollzugriff inkl. Berechtigungsverwaltung


class ResourceType(str, Enum):
    """Ressourcentypen für Permissions."""
    DOCUMENTS = "documents"
    USERS = "users"
    ROLES = "roles"
    WEBHOOKS = "webhooks"
    API_KEYS = "api_keys"
    AUDIT_LOGS = "audit_logs"
    SYSTEM = "system"
    BACKUPS = "backups"
    OCR = "ocr"
    SEARCH = "search"


# Association table for Role <-> Permission (many-to-many)
role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE")),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE")),
    Index("ix_role_permissions_role_id", "role_id"),
    Index("ix_role_permissions_permission_id", "permission_id")
)


# Association table for User <-> Role (many-to-many)
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")),
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE")),
    Column("assigned_at", DateTime(timezone=True), server_default=func.now()),
    Column("assigned_by_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")),
    Index("ix_user_roles_user_id", "user_id"),
    Index("ix_user_roles_role_id", "role_id")
)


class Permission(Base):
    """
    Granulare Berechtigung für RBAC.

    Berechtigungen definieren, was ein Benutzer mit einer bestimmten
    Ressource tun darf (z.B. documents:read, users:manage).
    """
    __tablename__ = "permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Permission identifier (unique, z.B. "documents:read")
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255), nullable=True)

    # Permission details
    resource_type = Column(String(50), nullable=False)  # documents, users, etc.
    action = Column(String(50), nullable=False)  # read, write, delete, manage

    # System permission (cannot be deleted)
    is_system = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    roles = relationship("Role", secondary=role_permissions, back_populates="permissions")

    # Indexes
    __table_args__ = (
        Index("ix_permissions_name", "name"),
        Index("ix_permissions_resource_action", "resource_type", "action"),
    )


class Role(Base):
    """
    Benutzerrolle für RBAC.

    Rollen gruppieren Berechtigungen und können Benutzern zugewiesen werden.
    Standard-Rollen: admin, manager, analyst, viewer
    """
    __tablename__ = "roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Role identifier
    name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)  # Deutscher Anzeigename
    description = Column(String(500), nullable=True)

    # Role hierarchy (höher = mehr Rechte, z.B. admin=100, viewer=10)
    priority = Column(Integer, default=0)

    # System role (cannot be deleted/modified)
    is_system = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Color for UI display (Hex)
    color = Column(String(7), default="#6B7280")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    permissions = relationship("Permission", secondary=role_permissions, back_populates="roles")
    users = relationship(
        "User",
        secondary=user_roles,
        primaryjoin="Role.id == user_roles.c.role_id",
        secondaryjoin="user_roles.c.user_id == User.id",
        back_populates="roles"
    )

    # Indexes
    __table_args__ = (
        Index("ix_roles_name", "name"),
        Index("ix_roles_priority", "priority"),
    )


# ============================================================================
# Session Management
# ============================================================================

class UserSession(Base):
    """
    Active user session tracking.

    Ermöglicht:
    - Übersicht aller aktiven Sessions
    - Logout von anderen Geräten
    - Erkennung verdächtiger Aktivitäten
    - Session-Widerruf bei Sicherheitsvorfällen
    """
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Token Identification
    token_jti = Column(String(64), unique=True, nullable=False)  # JWT ID für Blacklisting

    # Device Information
    device_name = Column(String(100), nullable=True)  # z.B. "Chrome auf Windows"
    device_type = Column(String(50), nullable=True)   # desktop, mobile, tablet
    ip_address = Column(String(45), nullable=False)   # IPv4 oder IPv6
    user_agent = Column(String(500), nullable=True)
    location = Column(String(100), nullable=True)     # Stadt, Land (GeoIP)

    # Timestamps
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Status
    is_current = Column(Boolean, default=False)  # Markiert aktuelle Session
    revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="sessions")

    # Indexes
    __table_args__ = (
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_token_jti", "token_jti"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )


class EmailVerificationToken(Base):
    """
    Email verification tokens.

    Verwendet für:
    - Neue Benutzerregistrierung (email_verified=False)
    - Email-Adresse ändern (new_email-Feld)
    - Erneute Verifizierung anfordern
    """
    __tablename__ = "email_verification_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Token Data
    token_hash = Column(String(128), nullable=False)  # SHA-256 Hash des Tokens
    email = Column(String(255), nullable=False)  # Email bei Token-Erstellung
    token_type = Column(String(20), nullable=False)  # 'verification' oder 'email_change'
    new_email = Column(String(255), nullable=True)  # Nur für Email-Änderungen

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Security
    ip_address = Column(String(45), nullable=True)

    # Relationships
    user = relationship("User", backref="email_verification_tokens")

    # Indexes
    __table_args__ = (
        Index("ix_email_verification_tokens_user_id", "user_id"),
        Index("ix_email_verification_tokens_token_hash", "token_hash"),
        Index("ix_email_verification_tokens_expires_at", "expires_at"),
    )


# ============================================================================
# Webhook System - Event-Driven Notifications
# ============================================================================

class WebhookEventType(str, Enum):
    """Verfügbare Webhook Event-Typen."""
    # Document Events
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_PROCESSING = "document.processing"
    DOCUMENT_COMPLETED = "document.completed"
    DOCUMENT_FAILED = "document.failed"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    # User Events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    # System Events
    SYSTEM_HEALTH_FAILED = "system.health_check_failed"
    SYSTEM_QUOTA_EXCEEDED = "system.quota_exceeded"
    BATCH_COMPLETED = "batch.completed"


class WebhookDeliveryStatus(str, Enum):
    """Status einer Webhook-Zustellung."""
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookSubscription(Base):
    """
    Webhook-Abonnement für Event-Benachrichtigungen.

    Ermöglicht Benutzern, HTTP-Callbacks für bestimmte Events zu registrieren.
    Unterstützt HMAC-Signierung, Custom Headers und Retry-Konfiguration.
    """
    __tablename__ = "webhook_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Endpoint-Konfiguration
    name = Column(String(100), nullable=False)  # Benutzerfreundlicher Name
    url = Column(String(500), nullable=False)   # Webhook-Ziel-URL
    description = Column(String(500), nullable=True)

    # Event-Filter (Liste von Event-Typen)
    event_types = Column(CrossDBJSON, nullable=False)  # ["document.created", "document.completed"]

    # Sicherheit
    secret = Column(String(100), nullable=False)  # HMAC-Secret für Signierung
    headers = Column(CrossDBJSON, nullable=True)  # Custom Headers {"X-Custom": "value"}

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False)  # Endpoint-Verifizierung

    # Retry-Konfiguration
    max_retries = Column(Integer, default=3)
    retry_delay_seconds = Column(Integer, default=60)

    # Statistiken
    total_deliveries = Column(Integer, default=0)
    successful_deliveries = Column(Integer, default=0)
    failed_deliveries = Column(Integer, default=0)
    last_delivery_at = Column(DateTime(timezone=True), nullable=True)
    last_failure_at = Column(DateTime(timezone=True), nullable=True)
    last_failure_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="webhook_subscriptions")
    deliveries = relationship("WebhookDelivery", back_populates="subscription", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_webhook_subscriptions_user_id", "user_id"),
        Index("ix_webhook_subscriptions_is_active", "is_active"),
        Index("ix_webhook_subscriptions_created_at", "created_at"),
    )


class WebhookDelivery(Base):
    """
    Webhook-Zustellungsprotokoll.

    Dokumentiert jeden Zustellungsversuch mit Response-Details.
    Ermöglicht Debugging und Retry-Tracking.
    """
    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Event-Daten
    event_id = Column(String(64), nullable=False)  # Unique Event ID
    event_type = Column(String(100), nullable=False)
    payload = Column(CrossDBJSON, nullable=False)  # Gesendetes Payload

    # Zustellungsstatus
    status = Column(String(20), default="pending")  # pending, delivered, failed, retrying
    attempt = Column(Integer, default=1)
    max_attempts = Column(Integer, default=4)  # 1 initial + 3 retries

    # Response-Details
    response_status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)  # Truncated auf 1000 Zeichen
    response_time_ms = Column(Integer, nullable=True)

    # Fehlerdetails
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)  # timeout, connection_error, http_error

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    subscription = relationship("WebhookSubscription", back_populates="deliveries")

    # Indexes
    __table_args__ = (
        Index("ix_webhook_deliveries_subscription_id", "subscription_id"),
        Index("ix_webhook_deliveries_event_id", "event_id"),
        Index("ix_webhook_deliveries_status", "status"),
        Index("ix_webhook_deliveries_created_at", "created_at"),
        Index("ix_webhook_deliveries_next_retry_at", "next_retry_at"),
    )


# ============================================================================
# Favorites System - Dokument-Favoriten
# ============================================================================

class DocumentFavorite(Base):
    """
    Favorisierte Dokumente für schnellen Zugriff.

    Ermöglicht Benutzern, Dokumente als Favoriten zu markieren
    und optional Notizen hinzuzufügen.
    """
    __tablename__ = "document_favorites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Optional: Benutzernotiz zum Favorit
    note = Column(String(500), nullable=True)

    # Sortierung (höher = wichtiger)
    priority = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="favorites")
    document = relationship("Document", backref="favorited_by")

    # Indexes und Constraints
    __table_args__ = (
        Index("ix_document_favorites_user_id", "user_id"),
        Index("ix_document_favorites_document_id", "document_id"),
        Index("ix_document_favorites_user_document", "user_id", "document_id", unique=True),
        Index("ix_document_favorites_created_at", "created_at"),
    )


# ============================================================================
# Document Access Control (Sharing)
# ============================================================================

class AccessLevel(str, Enum):
    """
    Zugriffsebenen für Dokument-Sharing.

    - VIEW: Nur lesen (Standard für Shares)
    - COMMENT: Lesen + Kommentieren
    - EDIT: Lesen + Bearbeiten (Text korrigieren, Tags)
    - MANAGE: Vollzugriff (inkl. Weitergabe, Löschen)
    """
    VIEW = "view"
    COMMENT = "comment"
    EDIT = "edit"
    MANAGE = "manage"


class DocumentAccess(Base):
    """
    Dokumentenzugriff für Sharing.

    Ermöglicht:
    - Dokumente mit anderen Benutzern teilen
    - Verschiedene Zugriffsebenen (view, comment, edit, manage)
    - Zeitlich begrenzte Shares
    - Audit-Trail wer geteilt hat
    """
    __tablename__ = "document_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument das geteilt wird
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Benutzer der Zugriff erhält
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Wer hat geteilt
    granted_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Zugriffsebene
    access_level = Column(
        String(20),
        nullable=False,
        default=AccessLevel.VIEW.value
    )

    # Optionale zeitliche Begrenzung
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Ob der Empfänger weitergeben darf
    can_share = Column(Boolean, default=False)

    # Optionale Notiz beim Teilen
    share_note = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="shared_access")
    user = relationship("User", foreign_keys=[user_id], backref="shared_documents")
    granted_by = relationship("User", foreign_keys=[granted_by_id])

    # Indexes und Constraints
    __table_args__ = (
        # Nur eine Zugriffsberechtigung pro Benutzer pro Dokument
        Index(
            "ix_document_access_user_document",
            "user_id", "document_id",
            unique=True
        ),
        Index("ix_document_access_document_id", "document_id"),
        Index("ix_document_access_user_id", "user_id"),
        Index("ix_document_access_expires_at", "expires_at"),
    )

    @property
    def is_expired(self) -> bool:
        """Prüft ob der Zugriff abgelaufen ist."""
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone
        return self.expires_at < datetime.now(timezone.utc)

    def can_view(self) -> bool:
        """Hat mindestens View-Berechtigung."""
        return not self.is_expired

    def can_comment(self) -> bool:
        """Hat Comment- oder höhere Berechtigung."""
        return not self.is_expired and self.access_level in [
            AccessLevel.COMMENT.value,
            AccessLevel.EDIT.value,
            AccessLevel.MANAGE.value
        ]

    def can_edit(self) -> bool:
        """Hat Edit- oder höhere Berechtigung."""
        return not self.is_expired and self.access_level in [
            AccessLevel.EDIT.value,
            AccessLevel.MANAGE.value
        ]

    def can_manage(self) -> bool:
        """Hat Manage-Berechtigung (Vollzugriff)."""
        return not self.is_expired and self.access_level == AccessLevel.MANAGE.value


# =============================================================================
# BACKUP & SYSTEM MODELS
# =============================================================================

class BackupType(str, Enum):
    """Backup-Typen."""
    FULL = "full"
    INCREMENTAL = "incremental"
    POSTGRES = "postgres"
    REDIS = "redis"
    MINIO = "minio"
    CONFIG = "config"


class BackupStatus(str, Enum):
    """Backup-Status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class BackupRecord(Base):
    """
    Backup-Verlauf und -Tracking.

    Speichert Informationen ueber durchgefuehrte Backups:
    - Zeitpunkt und Dauer
    - Typ (Full, Incremental, Component)
    - Groesse und Speicherort
    - Status und Fehler
    """
    __tablename__ = "backup_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Backup-Typ
    backup_type = Column(
        String(20),
        nullable=False,
        default=BackupType.FULL.value
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default=BackupStatus.PENDING.value
    )

    # Zeitstempel
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Groesse in Bytes
    size_bytes = Column(BigInteger, nullable=True)

    # Speicherort (lokal oder remote)
    storage_path = Column(String(500), nullable=True)
    remote_path = Column(String(500), nullable=True)

    # Checksumme fuer Integritaet
    checksum = Column(String(64), nullable=True)

    # Retention bis wann aufbewahren
    retention_until = Column(DateTime(timezone=True), nullable=True)

    # Fehlerdetails bei Fehlschlag
    error_message = Column(Text, nullable=True)

    # Metadata (z.B. DB-Version, Tabellen)
    backup_metadata = Column(JSON, default=dict)

    # Wer hat Backup ausgeloest (NULL = automatisch)
    triggered_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    triggered_by = relationship("User", backref="triggered_backups")

    __table_args__ = (
        Index("ix_backup_records_type_status", "backup_type", "status"),
        Index("ix_backup_records_started_at", "started_at"),
        Index("ix_backup_records_retention", "retention_until"),
    )

    @property
    def duration_seconds(self) -> Optional[float]:
        """Berechnet Backup-Dauer in Sekunden."""
        if self.completed_at and self.started_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def size_human(self) -> str:
        """Gibt Groesse in lesbarem Format zurueck."""
        if not self.size_bytes:
            return "N/A"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(self.size_bytes) < 1024.0:
                return f"{self.size_bytes:.1f} {unit}"
            self.size_bytes /= 1024.0
        return f"{self.size_bytes:.1f} PB"


class NotificationType(str, Enum):
    """Benachrichtigungs-Typen."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    OCR_COMPLETE = "ocr_complete"
    BATCH_COMPLETE = "batch_complete"
    EXPORT_READY = "export_ready"
    SHARE_RECEIVED = "share_received"
    SYSTEM = "system"


class Notification(Base):
    """
    Benutzer-Benachrichtigungen.

    Speichert In-App und E-Mail Benachrichtigungen:
    - OCR-Verarbeitung abgeschlossen
    - Batch-Job fertig
    - Export bereit zum Download
    - Dokument wurde geteilt
    - System-Benachrichtigungen
    """
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Empfaenger
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Typ und Titel
    notification_type = Column(
        String(30),
        nullable=False,
        default=NotificationType.INFO.value
    )
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)

    # Optionale Referenz (z.B. Dokument-ID)
    reference_type = Column(String(50), nullable=True)  # "document", "batch_job", etc.
    reference_id = Column(UUID(as_uuid=True), nullable=True)

    # Status
    read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # E-Mail gesendet?
    email_sent = Column(Boolean, default=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Zusaetzliche Daten
    data = Column(JSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="notifications")

    __table_args__ = (
        Index("ix_notifications_user_read", "user_id", "read"),
        Index("ix_notifications_user_created", "user_id", "created_at"),
        Index("ix_notifications_expires", "expires_at"),
    )

    @property
    def is_expired(self) -> bool:
        """Prueft ob Benachrichtigung abgelaufen ist."""
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone
        return self.expires_at < datetime.now(timezone.utc)


class FeatureFlag(Base):
    """
    Feature Flags fuer A/B Testing und Rollouts.

    Ermoeglicht:
    - Graduelle Feature-Rollouts
    - A/B Tests mit Benutzergruppen
    - Kill-Switches fuer kritische Features
    - Benutzer-spezifische Overrides
    """
    __tablename__ = "feature_flags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Feature-Identifikator (z.B. "new_ocr_pipeline", "dark_mode_v2")
    key = Column(String(100), nullable=False, unique=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # Aktivierungsstatus
    enabled = Column(Boolean, default=False)

    # Rollout-Prozent (0-100)
    rollout_percentage = Column(Integer, default=0)

    # Zielgruppen (JSON Array von User-Tiers oder User-IDs)
    target_tiers = Column(JSON, default=list)  # ["premium", "enterprise"]
    target_users = Column(JSON, default=list)  # Spezifische User-IDs

    # A/B Test Varianten
    variants = Column(JSON, default=dict)  # {"control": 50, "variant_a": 25, "variant_b": 25}

    # Zeitliche Begrenzung
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    # Zusaetzliche Konfiguration
    config = Column(JSON, default=dict)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        Index("ix_feature_flags_key", "key"),
        Index("ix_feature_flags_enabled", "enabled"),
    )

    def is_active(self) -> bool:
        """Prueft ob Feature Flag aktiv ist (zeitlich)."""
        if not self.enabled:
            return False

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False

        return True

    def is_enabled_for_user(self, user_id: str, user_tier: Optional[str] = None) -> bool:
        """Prueft ob Feature fuer bestimmten Benutzer aktiviert ist."""
        if not self.is_active():
            return False

        # Spezifische User-IDs haben Vorrang
        if self.target_users and user_id in self.target_users:
            return True

        # Tier-basierte Aktivierung
        if self.target_tiers and user_tier and user_tier in self.target_tiers:
            return True

        # Rollout-Prozent (deterministisch basierend auf User-ID Hash)
        if self.rollout_percentage > 0:
            import hashlib
            hash_input = f"{self.key}:{user_id}".encode()
            hash_value = int(hashlib.md5(hash_input).hexdigest(), 16) % 100
            return hash_value < self.rollout_percentage

        return False

    def get_variant_for_user(self, user_id: str) -> Optional[str]:
        """Ermittelt A/B Test Variante fuer Benutzer."""
        if not self.variants:
            return None

        import hashlib
        hash_input = f"{self.key}:variant:{user_id}".encode()
        hash_value = int(hashlib.md5(hash_input).hexdigest(), 16) % 100

        cumulative = 0
        for variant_name, percentage in self.variants.items():
            cumulative += percentage
            if hash_value < cumulative:
                return variant_name

        return list(self.variants.keys())[0] if self.variants else None


# ============================================================================
# BUSINESS ENTITY MODELS (Kunden/Lieferanten)
# ============================================================================

class EntityType(str, Enum):
    """Geschaeftspartner-Typ."""
    CUSTOMER = "customer"      # Kunde - erhaelt Dokumente VON uns
    SUPPLIER = "supplier"      # Lieferant - sendet Dokumente AN uns
    BOTH = "both"             # Kann beides sein
    INTERNAL = "internal"      # Interne Entitaet


class BusinessEntity(Base):
    """
    Geschaeftspartner (Kunde/Lieferant).

    Zentrale Entitaet fuer alle Geschaeftsbeziehungen.
    Unterstuetzt automatische Erkennung aus OCR-Text mit 99%+ Praezision.
    """
    __tablename__ = "business_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Entity identification
    entity_type = Column(String(20), nullable=False, default=EntityType.SUPPLIER.value)
    name = Column(String(255), nullable=False, index=True)
    display_name = Column(String(255))
    short_name = Column(String(50))  # Kurzname fuer Anzeige

    # German business identifiers (fuer 99%+ Praezision)
    vat_id = Column(String(20), unique=True, index=True, nullable=True)  # USt-IdNr (DE123456789)
    tax_number = Column(String(30), nullable=True)  # Steuernummer
    trade_register = Column(String(50), nullable=True)  # HRB 12345

    # Banking information
    iban = Column(String(34), index=True, nullable=True)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)

    # Contact information
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), index=True, nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")
    phone = Column(String(30), nullable=True)
    fax = Column(String(30), nullable=True)
    email = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)

    # Matching patterns (fuer Auto-Detection)
    name_aliases = Column(CrossDBJSON, default=list)  # ["ACME GmbH", "ACME AG", "Acme"]
    address_patterns = Column(CrossDBJSON, default=list)  # Alternative Adressen
    email_domains = Column(CrossDBJSON, default=list)  # ["acme.de", "acme.com"]

    # Statistics (werden automatisch aktualisiert)
    document_count = Column(Integer, default=0)
    first_document_date = Column(DateTime(timezone=True), nullable=True)
    last_document_date = Column(DateTime(timezone=True), nullable=True)
    total_invoice_amount = Column(Float, default=0.0)
    currency = Column(String(3), default="EUR")

    # Status and confidence
    is_active = Column(Boolean, default=True)
    verified = Column(Boolean, default=False)  # Manuell verifiziert
    confidence_score = Column(Float, default=0.0)  # 0.0-1.0
    auto_detected = Column(Boolean, default=False)  # Automatisch erkannt

    # Metadata & Audit
    notes = Column(Text, nullable=True)
    custom_fields = Column(CrossDBJSON, default=dict)  # Flexible Zusatzfelder
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    documents = relationship("Document", back_populates="business_entity")

    # Indexes
    __table_args__ = (
        Index("ix_business_entities_name", "name"),
        Index("ix_business_entities_vat_id", "vat_id"),
        Index("ix_business_entities_iban", "iban"),
        Index("ix_business_entities_postal_code", "postal_code"),
        Index("ix_business_entities_entity_type", "entity_type"),
        Index("ix_business_entities_is_active", "is_active"),
        Index("ix_business_entities_deleted_at", "deleted_at"),
    )

    @property
    def is_deleted(self) -> bool:
        """Check if entity is soft-deleted."""
        return self.deleted_at is not None

    @property
    def full_address(self) -> str:
        """Returns formatted full address."""
        parts = []
        if self.street:
            addr = self.street
            if self.street_number:
                addr += f" {self.street_number}"
            parts.append(addr)
        if self.postal_code and self.city:
            parts.append(f"{self.postal_code} {self.city}")
        elif self.city:
            parts.append(self.city)
        if self.country and self.country != "DE":
            parts.append(self.country)
        return ", ".join(parts)


# ============================================================================
# DOCUMENT GROUP MODELS (Zusammengehoerige Dokumente)
# ============================================================================

class DocumentGroupType(str, Enum):
    """Dokumentgruppen-Typ."""
    STAPLED = "stapled"              # Physisch geheftet gewesen
    MULTI_PAGE = "multi_page"        # Mehrseitiger Scan (z.B. PDF mit mehreren Seiten)
    TRANSACTION = "transaction"      # Transaktionsbezogen (z.B. Rechnung + Lieferschein)
    CORRESPONDENCE = "correspondence" # Briefwechsel
    PROJECT = "project"              # Projektbezogen
    MANUAL = "manual"                # Manuell vom Benutzer erstellt


class DocumentGroup(Base):
    """
    Dokumentgruppe fuer zusammengehoerige Dokumente.

    Gruppiert:
    - Physisch geheftete Seiten (waren mit Heftklammer zusammen)
    - Mehrseitige Scans
    - Logisch zusammengehoerige Dokumente (gleiche Transaktion)

    Erkennung mit 99%+ Praezision durch Mehrfach-Validierung.
    """
    __tablename__ = "document_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Group identification
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    group_type = Column(String(30), nullable=False, default=DocumentGroupType.STAPLED.value)

    # Primary document (erstes/wichtigstes Dokument der Gruppe)
    primary_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Detection metadata
    detection_method = Column(String(50), nullable=True)  # "filename_sequence", "timestamp", "content_similarity"
    detection_confidence = Column(Float, default=0.0)  # 0.0-1.0, muss >= 0.99 sein fuer Auto-Gruppierung
    detection_details = Column(CrossDBJSON, default=dict)  # Details zur Erkennung
    detection_signals = Column(CrossDBJSON, default=list)  # Alle Erkennungssignale

    # Content aggregation
    total_pages = Column(Integer, default=1)
    combined_text = Column(Text, nullable=True)  # Kombinierter OCR-Text aller Dokumente
    combined_text_hash = Column(String(64), nullable=True)  # SHA-256 fuer Deduplizierung

    # Business context
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)
    document_date = Column(DateTime(timezone=True), nullable=True)  # Hauptdatum der Gruppe
    reference_number = Column(String(100), nullable=True)  # Referenznummer (Rechnungsnr., etc.)

    # Extracted data (aggregiert aus allen Dokumenten)
    extracted_data = Column(CrossDBJSON, default=dict)

    # User interaction
    user_confirmed = Column(Boolean, default=False)  # Benutzer hat Gruppierung bestaetigt
    user_split = Column(Boolean, default=False)  # Benutzer hat Gruppe aufgeteilt
    confirmation_date = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Validation queue
    needs_review = Column(Boolean, default=False)  # In Warteschlange fuer manuelle Pruefung
    review_priority = Column(Integer, default=5)  # 1=hoechste Prioritaet

    # Audit
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], backref="document_groups")
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])
    business_entity = relationship("BusinessEntity", backref="document_groups")
    documents = relationship("Document", back_populates="document_group", foreign_keys="Document.group_id")
    primary_document = relationship("Document", foreign_keys=[primary_document_id], post_update=True)

    # Indexes
    __table_args__ = (
        Index("ix_document_groups_group_type", "group_type"),
        Index("ix_document_groups_detection_confidence", "detection_confidence"),
        Index("ix_document_groups_business_entity_id", "business_entity_id"),
        Index("ix_document_groups_owner_id", "owner_id"),
        Index("ix_document_groups_needs_review", "needs_review"),
        Index("ix_document_groups_user_confirmed", "user_confirmed"),
        Index("ix_document_groups_created_at", "created_at"),
        Index("ix_document_groups_deleted_at", "deleted_at"),
    )

    @property
    def is_deleted(self) -> bool:
        """Check if group is soft-deleted."""
        return self.deleted_at is not None

    @property
    def is_auto_confirmed(self) -> bool:
        """Check if group was auto-confirmed (99%+ confidence)."""
        return self.detection_confidence >= 0.99 and not self.user_confirmed


# ============================================================================
# DOCUMENT RELATIONSHIP MODEL (Beziehungen zwischen Dokumenten)
# ============================================================================

class RelationshipType(str, Enum):
    """Beziehungstyp zwischen Dokumenten."""
    CHILD_OF = "child_of"           # Seite gehoert zu mehrseitigem Dokument
    REFERENCES = "references"        # Dokument verweist auf anderes (z.B. Rechnung -> Vertrag)
    REPLIES_TO = "replies_to"        # Antwort auf Dokument
    SUPPLEMENTS = "supplements"      # Ergaenzung/Anlage zu Dokument
    SUPERSEDES = "supersedes"        # Ersetzt/Annulliert anderes Dokument
    DUPLICATE_OF = "duplicate_of"    # Ist Duplikat von
    RELATED = "related"              # Allgemeine Beziehung


class DocumentRelationship(Base):
    """
    Beziehung zwischen zwei Dokumenten.

    Ermoeglicht Tracking von:
    - Seitenreihenfolge in mehrseitigen Dokumenten
    - Verweise zwischen Dokumenten (Rechnung -> Vertrag)
    - Duplikat-Erkennung

    Bidirektionale Beziehungen werden als zwei separate Eintraege gespeichert.
    """
    __tablename__ = "document_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Relationship endpoints
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )
    target_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Relationship details
    relationship_type = Column(String(30), nullable=False)
    confidence = Column(Float, default=1.0)  # 0.0-1.0

    # Ordering (fuer CHILD_OF Beziehungen)
    sequence_number = Column(Integer, nullable=True)  # Seitennummer/Reihenfolge

    # Detection metadata
    detected_by = Column(String(50), nullable=True)  # "algorithm", "user", "ocr_reference"
    detection_details = Column(CrossDBJSON, default=dict)

    # User interaction
    user_confirmed = Column(Boolean, default=False)
    user_rejected = Column(Boolean, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    source_document = relationship(
        "Document",
        foreign_keys=[source_document_id],
        backref="outgoing_relationships"
    )
    target_document = relationship(
        "Document",
        foreign_keys=[target_document_id],
        backref="incoming_relationships"
    )
    created_by = relationship("User")

    # Indexes and constraints
    __table_args__ = (
        Index("ix_document_relationships_source", "source_document_id"),
        Index("ix_document_relationships_target", "target_document_id"),
        Index("ix_document_relationships_type", "relationship_type"),
        Index("ix_document_relationships_confidence", "confidence"),
        # Prevent duplicate relationships
        Index(
            "ix_document_relationships_unique",
            "source_document_id", "target_document_id", "relationship_type",
            unique=True
        ),
    )


# ============================================================================
# OCR TRAINING & VALIDATION MODELS
# Enterprise OCR Training System mit Self-Learning
# ============================================================================

class TrainingSampleStatus(str, Enum):
    """Status eines Training-Samples."""
    PENDING = "pending"           # Noch nicht annotiert
    IN_PROGRESS = "in_progress"   # Wird gerade bearbeitet
    ANNOTATED = "annotated"       # Annotiert, wartet auf Verifikation
    VERIFIED = "verified"         # Von Admin verifiziert
    REJECTED = "rejected"         # Abgelehnt (schlechte Qualitaet)


class OCRTrainingSample(Base):
    """
    Ground Truth Training Sample fuer OCR-Benchmarking.

    Speichert Dokumente mit manuell verifiziertem Referenztext
    fuer die Qualitaetsmessung aller OCR-Backends.

    Workflow:
    1. Dokument wird als Sample ausgewaehlt (PENDING)
    2. Editor annotiert Ground Truth (ANNOTATED)
    3. Admin verifiziert (VERIFIED)
    4. Benchmarks laufen gegen verifizierte Samples
    """
    __tablename__ = "ocr_training_samples"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokumentreferenz
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA-256
    thumbnail_path = Column(String(500), nullable=True)

    # Ground Truth (manuell verifizierter Text)
    ground_truth_text = Column(Text, nullable=True)

    # Dokumentklassifikation
    language = Column(String(10), default="de")  # de, nl, pl, en
    document_type = Column(String(50), nullable=True)  # invoice, freight, email, letter
    difficulty = Column(String(20), default="medium")  # easy, medium, hard

    # Dokumenteigenschaften
    has_umlauts = Column(Boolean, default=False)
    has_fraktur = Column(Boolean, default=False)
    has_tables = Column(Boolean, default=False)
    has_handwriting = Column(Boolean, default=False)
    has_stamps = Column(Boolean, default=False)
    has_signatures = Column(Boolean, default=False)

    # Umlaut-Tracking (kritisch fuer Deutsche Dokumente)
    umlaut_words = Column(CrossDBJSON, default=list)  # ["Muenchen", "Groesse", "uebergeben"]

    # Extrahierte Felder (fuer Field-Accuracy)
    extracted_fields = Column(CrossDBJSON, default=dict)  # {invoice_number, date, amount, vat, sender, recipient}

    # Workflow Status
    status = Column(String(20), default=TrainingSampleStatus.PENDING.value, nullable=False)

    # Annotation Tracking
    annotated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    annotation_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    annotated_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    annotated_by = relationship("User", foreign_keys=[annotated_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])
    benchmarks = relationship("OCRBackendBenchmark", back_populates="training_sample", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_training_samples_status", "status"),
        Index("ix_ocr_training_samples_language", "language"),
        Index("ix_ocr_training_samples_document_type", "document_type"),
        Index("ix_ocr_training_samples_file_hash", "file_hash"),
        Index("ix_ocr_training_samples_verified", "status", "verified_at"),
    )


class OCRBackendBenchmark(Base):
    """
    Benchmark-Ergebnis eines OCR-Backends gegen ein Training Sample.

    Speichert:
    - OCR-Output des Backends
    - Qualitaetsmetriken (CER, WER, Umlaut-Accuracy)
    - Verarbeitungszeit und Ressourcenverbrauch
    - Feld-spezifische Genauigkeit
    """
    __tablename__ = "ocr_backend_benchmarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    training_sample_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_samples.id", ondelete="CASCADE"),
        nullable=False
    )

    # Backend Identifikation
    backend_name = Column(String(50), nullable=False)  # deepseek, got_ocr, surya_gpu, surya_cpu
    backend_version = Column(String(50), nullable=True)

    # OCR Output
    raw_text = Column(Text, nullable=True)

    # Qualitaetsmetriken
    confidence_score = Column(Float, nullable=True)  # 0.0-1.0 vom Backend
    cer = Column(Float, nullable=True)  # Character Error Rate
    wer = Column(Float, nullable=True)  # Word Error Rate
    umlaut_accuracy = Column(Float, nullable=True)  # Umlaut-Genauigkeit 0.0-1.0
    capitalization_accuracy = Column(Float, nullable=True)  # Grossschreibung

    # Feld-spezifische Genauigkeit
    field_accuracies = Column(CrossDBJSON, default=dict)  # {invoice_number: 1.0, date: 0.9, amount: 1.0}

    # Fehler-Pattern-Analyse
    error_patterns = Column(CrossDBJSON, default=dict)  # {umlaut_errors: 2, date_format: 1}
    insertions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    substitutions = Column(Integer, default=0)

    # Performance-Metriken
    processing_time_ms = Column(Integer, nullable=True)
    gpu_memory_mb = Column(Integer, nullable=True)

    # Timestamps
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    training_sample = relationship("OCRTrainingSample", back_populates="benchmarks")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_backend_benchmarks_sample", "training_sample_id"),
        Index("ix_ocr_backend_benchmarks_backend", "backend_name"),
        Index("ix_ocr_backend_benchmarks_sample_backend", "training_sample_id", "backend_name"),
        Index("ix_ocr_backend_benchmarks_processed_at", "processed_at"),
        Index("ix_ocr_backend_benchmarks_cer", "cer"),
    )


class CorrectionType(str, Enum):
    """Typ der OCR-Korrektur."""
    UMLAUT = "umlaut"           # Umlaut-Fehler (a->ae, etc.)
    DATE = "date"               # Datumsformat
    AMOUNT = "amount"           # Betrag/Waehrung
    NAME = "name"               # Firmen-/Personenname
    IBAN = "iban"               # IBAN/Bankdaten
    VAT_ID = "vat_id"           # USt-IdNr
    GENERAL = "general"         # Allgemeine Korrektur


class OCRValidationCorrection(Base):
    """
    Feedback-Korrektur aus der Produktion.

    Wenn Benutzer OCR-Fehler korrigieren, wird das Feedback
    gesammelt und fuer Self-Learning verwendet.

    Self-Learning Workflow:
    1. Benutzer korrigiert OCR-Fehler
    2. Korrektur wird gespeichert und analysiert
    3. Fehler-Patterns werden pro Backend aggregiert
    4. OCR Router passt Backend-Auswahl an
    """
    __tablename__ = "ocr_validation_corrections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz (aus Produktion)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Korrektur-Details
    original_text = Column(Text, nullable=False)
    corrected_text = Column(Text, nullable=False)
    correction_type = Column(String(30), default=CorrectionType.GENERAL.value)
    field_corrected = Column(String(50), nullable=True)  # Welches Feld korrigiert

    # Backend das den Fehler gemacht hat
    backend_used = Column(String(50), nullable=False)

    # Kontext
    confidence_before = Column(Float, nullable=True)  # Konfidenz vor Korrektur

    # Self-Learning Status
    applies_to_training = Column(Boolean, default=False)  # Soll in Training einfliessen
    learning_processed = Column(Boolean, default=False)  # Wurde fuer Learning verarbeitet
    learning_processed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    corrector_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", backref="ocr_corrections")
    corrector = relationship("User")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_validation_corrections_document", "document_id"),
        Index("ix_ocr_validation_corrections_backend", "backend_used"),
        Index("ix_ocr_validation_corrections_type", "correction_type"),
        Index("ix_ocr_validation_corrections_learning", "learning_processed"),
        Index("ix_ocr_validation_corrections_created", "created_at"),
    )


class BatchType(str, Enum):
    """Typ des Stichproben-Batches."""
    RANDOM = "random"               # Zufaellige Auswahl
    STRATIFIED = "stratified"       # Stratifiziert nach Typ/Sprache
    TARGETED = "targeted"           # Gezielt nach Kriterien
    LOW_CONFIDENCE = "low_confidence"  # Niedrige Konfidenz-Dokumente


class BatchStatus(str, Enum):
    """Status des Stichproben-Batches."""
    DRAFT = "draft"           # In Erstellung
    READY = "ready"           # Bereit zum Starten
    IN_PROGRESS = "in_progress"  # Wird gerade bearbeitet
    ACTIVE = "active"         # Aktiv, wird bearbeitet
    COMPLETED = "completed"   # Alle Items validiert
    CANCELLED = "cancelled"   # Abgebrochen


class OCRTrainingBatch(Base):
    """
    Stichproben-Batch fuer systematische Validierung.

    Ermoeglicht:
    - Stratifizierte Zufallsauswahl
    - Zuweisung an Bearbeiter
    - Fortschrittsverfolgung
    - Qualitaetskontrolle
    """
    __tablename__ = "ocr_training_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Batch Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    batch_type = Column(String(30), default=BatchType.STRATIFIED.value)

    # Backend-spezifische Validierung (fuer Pro-Backend Stichproben)
    target_backend = Column(String(50), nullable=True)

    # Stratifikations-Konfiguration
    stratification_config = Column(CrossDBJSON, default=dict)  # {by_type: true, by_language: true, type_weights: {...}}

    # Groesse
    target_size = Column(Integer, default=100)  # Ziel-Anzahl
    actual_size = Column(Integer, default=0)    # Tatsaechliche Anzahl

    # Status
    status = Column(String(20), default=BatchStatus.DRAFT.value)

    # Fortschritt (wird automatisch berechnet)
    items_pending = Column(Integer, default=0)
    items_completed = Column(Integer, default=0)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    items = relationship("OCRTrainingBatchItem", back_populates="batch", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_training_batches_status", "status"),
        Index("ix_ocr_training_batches_type", "batch_type"),
        Index("ix_ocr_training_batches_created", "created_at"),
    )

    @property
    def progress_percent(self) -> float:
        """Berechnet Fortschritt in Prozent."""
        if self.actual_size == 0:
            return 0.0
        return (self.items_completed / self.actual_size) * 100


class ItemStatus(str, Enum):
    """Status eines Batch-Items."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class OCRTrainingBatchItem(Base):
    """
    Einzelnes Item in einem Stichproben-Batch.

    Verknuepft Batch mit Training Sample und trackt
    den Validierungs-Fortschritt.
    """
    __tablename__ = "ocr_training_batch_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    batch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_batches.id", ondelete="CASCADE"),
        nullable=False
    )
    training_sample_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_samples.id", ondelete="CASCADE"),
        nullable=False
    )

    # Reihenfolge im Batch
    sequence_number = Column(Integer, nullable=False)

    # Zuweisung
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Status
    status = Column(String(20), default=ItemStatus.PENDING.value)

    # Validierungs-Ergebnis
    validation_notes = Column(Text, nullable=True)
    validation_time_seconds = Column(Integer, nullable=True)  # Wie lange hat Validierung gedauert

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    batch = relationship("OCRTrainingBatch", back_populates="items")
    training_sample = relationship("OCRTrainingSample")
    assigned_to = relationship("User")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_training_batch_items_batch", "batch_id"),
        Index("ix_ocr_training_batch_items_sample", "training_sample_id"),
        Index("ix_ocr_training_batch_items_status", "status"),
        Index("ix_ocr_training_batch_items_assigned", "assigned_to_id"),
        Index("ix_ocr_training_batch_items_sequence", "batch_id", "sequence_number"),
    )


class OCRBackendStatsDaily(Base):
    """
    Taegliche aggregierte Statistiken pro Backend.

    Wird automatisch von Celery Beat generiert.
    Ermoeglicht Trend-Analyse und Performance-Vergleich.
    """
    __tablename__ = "ocr_backend_stats_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    backend_name = Column(String(50), nullable=False)
    report_date = Column(DateTime(timezone=True), nullable=False)

    # Sample-Zaehler
    samples_processed = Column(Integer, default=0)
    samples_verified = Column(Integer, default=0)

    # Durchschnittsmetriken
    avg_cer = Column(Float, nullable=True)
    avg_wer = Column(Float, nullable=True)
    avg_umlaut_accuracy = Column(Float, nullable=True)
    avg_processing_time_ms = Column(Float, nullable=True)

    # Percentile fuer CER
    p50_cer = Column(Float, nullable=True)
    p90_cer = Column(Float, nullable=True)
    p95_cer = Column(Float, nullable=True)

    # Aufschluesselung nach Feld-Typ
    field_accuracy_stats = Column(CrossDBJSON, default=dict)
    # {invoice_number: {avg: 0.95, count: 50}, date: {avg: 0.88, count: 45}}

    # Aufschluesselung nach Dokument-Typ
    document_type_stats = Column(CrossDBJSON, default=dict)
    # {invoice: {cer: 0.02, count: 100}, freight: {cer: 0.05, count: 50}}

    # Aufschluesselung nach Sprache
    language_stats = Column(CrossDBJSON, default=dict)
    # {de: {cer: 0.02, count: 120}, nl: {cer: 0.04, count: 30}}

    # Self-Learning Metriken
    corrections_count = Column(Integer, default=0)
    correction_types = Column(CrossDBJSON, default=dict)
    # {umlaut: 15, date: 5, amount: 3}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_ocr_backend_stats_daily_backend", "backend_name"),
        Index("ix_ocr_backend_stats_daily_date", "report_date"),
        Index("ix_ocr_backend_stats_daily_backend_date", "backend_name", "report_date", unique=True),
    )


# ============================================================================
# BULK OCR PROCESSING MODELS
# Massenverarbeitung aller Trainings-Dokumente
# ============================================================================

class BulkJobStatus(str, Enum):
    """Status eines Bulk-Processing-Jobs."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OCRBulkProcessingJob(Base):
    """
    Bulk OCR Processing Job.

    Trackt den Fortschritt der Massenverarbeitung aller
    Trainings-Dokumente durch alle OCR-Backends.
    """
    __tablename__ = "ocr_bulk_processing_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Job Identifikation
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Status
    status = Column(String(20), default=BulkJobStatus.PENDING.value, nullable=False)

    # Backend-Konfiguration
    backends = Column(CrossDBJSON, nullable=False)  # ["deepseek", "got-ocr", ...]

    # Fortschritt
    total_documents = Column(Integer, default=0)
    processed_documents = Column(Integer, default=0)
    failed_documents = Column(Integer, default=0)

    # Aktueller Stand
    current_backend = Column(String(50), nullable=True)
    current_backend_index = Column(Integer, default=0)
    current_document_index = Column(Integer, default=0)

    # Pro-Backend Statistiken
    documents_per_backend = Column(CrossDBJSON, default=dict)

    # Konfiguration
    configuration = Column(CrossDBJSON, default=dict)

    # Fehlerlog
    error_log = Column(CrossDBJSON, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    last_checkpoint_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    outputs = relationship("OCRDocumentOutput", back_populates="bulk_job")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_bulk_processing_jobs_status", "status"),
        Index("ix_ocr_bulk_processing_jobs_created", "created_at"),
    )

    @property
    def progress_percent(self) -> float:
        """Berechnet Fortschritt in Prozent."""
        if self.total_documents == 0:
            return 0.0
        return (self.processed_documents / self.total_documents) * 100


class OCRDocumentOutput(Base):
    """
    OCR Output fuer ein Dokument durch ein spezifisches Backend.

    Speichert den OCR-Output aller Backends fuer spaetere
    Vergleiche und Ground-Truth-Erstellung.
    """
    __tablename__ = "ocr_document_outputs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    training_sample_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_training_samples.id", ondelete="CASCADE"),
        nullable=False
    )
    bulk_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ocr_bulk_processing_jobs.id", ondelete="SET NULL"),
        nullable=True
    )

    # Backend Identifikation
    backend_name = Column(String(50), nullable=False)
    backend_version = Column(String(50), nullable=True)

    # OCR Output
    raw_text = Column(Text, nullable=True)
    structured_output = Column(CrossDBJSON, nullable=True)

    # Qualitaetsmetriken
    confidence_score = Column(Float, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    gpu_memory_mb = Column(Integer, nullable=True)

    # Fehler
    error_message = Column(Text, nullable=True)
    success = Column(Boolean, default=True)

    # Timestamps
    processed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    training_sample = relationship("OCRTrainingSample")
    bulk_job = relationship("OCRBulkProcessingJob", back_populates="outputs")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_document_outputs_sample", "training_sample_id"),
        Index("ix_ocr_document_outputs_backend", "backend_name"),
        Index("ix_ocr_document_outputs_job", "bulk_job_id"),
        Index("ix_ocr_document_outputs_sample_backend", "training_sample_id", "backend_name", unique=True),
    )


class OCRQualitySnapshot(Base):
    """
    Stuendliche Qualitaets-Snapshots pro Backend.

    Ermoeglicht Trend-Analyse und Quality-Degradation-Erkennung
    fuer das Continuous-Learning-System.
    """
    __tablename__ = "ocr_quality_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    backend_name = Column(String(50), nullable=False)
    snapshot_time = Column(DateTime(timezone=True), server_default=func.now())

    # Sample Counts
    sample_count = Column(Integer, default=0)

    # Qualitaetsmetriken
    avg_cer = Column(Float, nullable=True)
    avg_wer = Column(Float, nullable=True)
    avg_umlaut_accuracy = Column(Float, nullable=True)
    avg_processing_time_ms = Column(Float, nullable=True)

    # Percentiles
    p50_cer = Column(Float, nullable=True)
    p90_cer = Column(Float, nullable=True)
    p99_cer = Column(Float, nullable=True)

    # Korrekturen
    correction_count = Column(Integer, default=0)
    correction_types = Column(CrossDBJSON, default=dict)

    # Alert Status
    alert_triggered = Column(Boolean, default=False)
    alert_reason = Column(String(255), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_ocr_quality_snapshots_backend", "backend_name"),
        Index("ix_ocr_quality_snapshots_time", "snapshot_time"),
        Index("ix_ocr_quality_snapshots_backend_time", "backend_name", "snapshot_time"),
    )


class ModelType(str, Enum):
    """Typ des Modells."""
    BASE = "base"
    FINETUNED = "finetuned"
    LORA = "lora"


class OCRModelDeployment(Base):
    """
    Modell-Deployment-Tracking fuer A/B Testing.

    Ermoeglicht Versionskontrolle und Rollback
    fuer fine-getunte Modelle.
    """
    __tablename__ = "ocr_model_deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Model Identifikation
    model_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    model_type = Column(String(50), default=ModelType.BASE.value)

    # Deployment Info
    is_active = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)
    traffic_percentage = Column(Float, default=0.0)  # Fuer A/B Testing

    # Performance Metrics
    performance_metrics = Column(CrossDBJSON, default=dict)

    # Checkpoint Info
    checkpoint_path = Column(String(500), nullable=True)
    training_job_id = Column(UUID(as_uuid=True), nullable=True)

    # Rollback Info
    previous_version = Column(String(50), nullable=True)
    rollback_reason = Column(Text, nullable=True)

    # Timestamps
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Audit
    deployed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    deployed_by = relationship("User")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_model_deployments_model", "model_name"),
        Index("ix_ocr_model_deployments_active", "is_active"),
        Index("ix_ocr_model_deployments_model_version", "model_name", "version", unique=True),
    )
