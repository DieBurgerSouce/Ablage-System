"""SQLAlchemy database models for Ablage-System.

HINWEIS ZU RELATIONSHIPS:
=========================
Dieses Modul verwendet eine Mischung aus `backref` und `back_populates`.
Beide sind funktional aequivalent.

KONVENTION FUER NEUE RELATIONSHIPS:
- Verwende `back_populates` fuer explizite bidirektionale Beziehungen
- Definiere die Relationship auf BEIDEN Seiten der Beziehung
- `backref` ist weiterhin akzeptabel fuer einfache unidirektionale Referenzen

Beispiel:
    # Parent-Seite
    class User(Base):
        documents = relationship("Document", back_populates="owner")

    # Child-Seite
    class Document(Base):
        owner = relationship("User", back_populates="documents")
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Date, Boolean, Float, Numeric, Text, JSON, ForeignKey, Index, Table, CheckConstraint
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

    # Qdrant Vector Search (A/B Testing mit Jina-DE)
    qdrant_indexed_at = Column(DateTime(timezone=True), nullable=True)

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

    # Quick Classification (schnelle Klassifizierung in 2-5 Sekunden)
    # Laeuft PARALLEL zum vollstaendigen OCR, um sofort Tags zuzuweisen
    quick_classification_status = Column(
        String(20),
        default="pending",
        nullable=False,
        comment="Status: pending, processing, completed, failed"
    )
    quick_classification_result = Column(
        CrossDBJSON,
        nullable=True,
        comment="Ergebnis: {direction, confidence, reason, tag_assigned, user_overridden}"
    )

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

    # User preferences (display, OCR, notifications, privacy settings)
    preferences = Column(CrossDBJSON, nullable=True)

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
    """Document tags for categorization with optional Tune linking."""
    __tablename__ = "tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), unique=True, nullable=False)
    description = Column(String(255))
    icon = Column(String(50), default="Tag")  # Lucide icon name
    color = Column(String(50))  # Tailwind class (bg-*-500) or Hex color code

    # Optional link to Tune for OCR fine-tuning
    tune_id = Column(UUID(as_uuid=True), ForeignKey("tunes.id", ondelete="SET NULL"), nullable=True)

    # Admin management
    is_system = Column(Boolean, default=False)  # System tags cannot be deleted
    is_active = Column(Boolean, default=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    documents = relationship("Document", secondary=document_tags, back_populates="tags")
    tune = relationship("Tune", back_populates="tags")

    # Indexes (synchron mit Migration 038)
    __table_args__ = (
        Index("ix_tags_is_system", "is_system"),
        Index("ix_tags_is_active", "is_active"),
        Index("ix_tags_tune_id", "tune_id"),
    )


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

    # Relationships
    tags = relationship("Tag", back_populates="tune")

    # Indexes (synchron mit Migration 031b_fix_tunes)
    __table_args__ = (
        Index("ix_tunes_name", "name"),
        Index("ix_tunes_is_active", "is_active"),
        Index("ix_tunes_is_system", "is_system"),  # Aus Migration 031b
        Index("ix_tunes_is_active_is_system", "is_active", "is_system"),  # Composite aus 031b
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

    # Position-Weighted Click Analytics
    # Verwendet exponentiellen Decay: Position 1=1.0, Position 5=0.55, Position 10=0.26
    weighted_click_score = Column(Float, default=0.0)  # Kumulierter gewichteter Score
    click_positions = Column(CrossDBJSON, default=list)  # Liste aller Klick-Positionen

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
# CHAT SESSION SHARING
# =============================================================================

class ChatSessionAccessLevel(str, Enum):
    """
    Zugriffsebenen fuer Chat Session Sharing.

    - VIEW: Nur lesen (Chat und Nachrichten ansehen)
    - CONTRIBUTE: Mitarbeiten (Nachrichten senden, mit KI interagieren)
    - MANAGE: Verwalten (Alles + User einladen/entfernen, Chat loeschen)
    """
    VIEW = "view"
    CONTRIBUTE = "contribute"
    MANAGE = "manage"


class ChatSessionAccess(Base):
    """
    Chat Session Zugriff fuer Real-time Collaboration.

    Ermoeglicht:
    - Chats mit anderen Benutzern teilen
    - Verschiedene Zugriffsebenen (view, contribute, manage)
    - Real-time Zusammenarbeit ueber WebSocket
    - Audit-Trail wer geteilt hat
    """
    __tablename__ = "rag_chat_session_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Chat Session die geteilt wird
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_chat_sessions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Benutzer der Zugriff erhaelt
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
        default=ChatSessionAccessLevel.VIEW.value
    )

    # Timestamps
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    session = relationship("RAGChatSession", back_populates="shared_access")
    user = relationship("User", foreign_keys=[user_id], backref="shared_chat_sessions")
    granted_by = relationship("User", foreign_keys=[granted_by_id])

    # Indexes und Constraints
    __table_args__ = (
        # Nur eine Zugriffsberechtigung pro Benutzer pro Session
        Index(
            "ix_chat_session_access_user_session",
            "user_id", "session_id",
            unique=True
        ),
        Index("ix_chat_session_access_session_id", "session_id"),
        Index("ix_chat_session_access_user_id", "user_id"),
    )

    def can_view(self) -> bool:
        """Hat mindestens View-Berechtigung."""
        return True

    def can_contribute(self) -> bool:
        """Hat Contribute- oder hoehere Berechtigung."""
        return self.access_level in [
            ChatSessionAccessLevel.CONTRIBUTE.value,
            ChatSessionAccessLevel.MANAGE.value
        ]

    def can_manage(self) -> bool:
        """Hat Manage-Berechtigung (Vollzugriff)."""
        return self.access_level == ChatSessionAccessLevel.MANAGE.value


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

    # Auto-Accept Pipeline Felder (Phase 1.3)
    business_priority = Column(Float, default=1.0)  # Aus BusinessDocumentProfile.training_weight
    auto_accepted = Column(Boolean, default=False)  # True wenn durch Auto-Accept Pipeline erstellt
    auto_acceptance_confidence = Column(Float, nullable=True)  # OCR Confidence bei Auto-Accept
    source = Column(String(30), default="manual")  # "manual", "auto_accepted", "correction"
    needs_spot_check = Column(Boolean, default=False)  # True fuer 10% Stichproben-Review
    spot_check_passed = Column(Boolean, nullable=True)  # Ergebnis des Stichproben-Reviews
    spot_checked_at = Column(DateTime(timezone=True), nullable=True)
    spot_checked_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # LLM Review Pipeline Felder (Phase 6)
    llm_review_status = Column(String(20), default="pending")  # pending, reviewed, accepted, rejected, needs_human
    llm_review_result = Column(CrossDBJSON, nullable=True)  # {quality_score, issues_found, recommendation, reasoning}
    llm_corrected_text = Column(Text, nullable=True)  # Korrigierter Text vom LLM
    llm_reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Annotation Tracking
    annotated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    annotation_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    annotated_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)  # GDPR Soft-Delete

    # Relationships
    annotated_by = relationship("User", foreign_keys=[annotated_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])
    spot_checked_by = relationship("User", foreign_keys=[spot_checked_by_id])
    benchmarks = relationship("OCRBackendBenchmark", back_populates="training_sample", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_ocr_training_samples_status", "status"),
        Index("ix_ocr_training_samples_language", "language"),
        Index("ix_ocr_training_samples_document_type", "document_type"),
        Index("ix_ocr_training_samples_file_hash", "file_hash"),
        Index("ix_ocr_training_samples_verified", "status", "verified_at"),
        Index("ix_ocr_training_samples_deleted_at", "deleted_at"),
        # Auto-Accept Pipeline Indexes
        Index("ix_ocr_training_samples_auto_accepted", "auto_accepted"),
        Index("ix_ocr_training_samples_source", "source"),
        Index("ix_ocr_training_samples_spot_check", "needs_spot_check", "spot_check_passed"),
        Index("ix_ocr_training_samples_priority", "business_priority"),
        # LLM Review Pipeline Index
        Index("ix_ocr_training_samples_llm_review", "llm_review_status"),
    )

    @property
    def is_deleted(self) -> bool:
        """Check if sample is soft-deleted (GDPR)."""
        return self.deleted_at is not None


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


# ============================================================================
# RAG INTELLIGENCE LAYER MODELS
# ============================================================================

class RAGSectionType(str, Enum):
    """Chunk Section Types fuer RAG."""
    HEADER = "header"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    FOOTER = "footer"
    UNKNOWN = "unknown"


class RAGSyncStatus(str, Enum):
    """Synchronisations-Status fuer Customer Cards."""
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
    SYNC_CARDS = "sync_cards"  # Alias fuer CUSTOMER_CARD_SYNC
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


# Aliase fuer API-Kompatibilitaet
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
    """Chat Context Types fuer RAG-Kontext."""
    GENERAL = "general"
    CUSTOMER = "customer"
    DOCUMENT = "document"
    REPORT = "report"


class RAGDocumentChunk(Base):
    """
    Chunked Document fuer RAG Retrieval.

    Speichert Text-Chunks mit Embeddings fuer semantische Suche.
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
    Pre-computed Kunden-Zusammenfassung fuer Real-Time Zugriff.

    Ermoeglicht Instant-Zugriff (< 100ms) auf Kundendaten am Telefon.
    Wird naechtlich per Batch-Job aktualisiert oder bei Bedarf manuell.
    """
    __tablename__ = "rag_customer_cards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kunden-Identifikation
    customer_id = Column(String(100), nullable=False, unique=True)
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
    payment_behavior = Column(String(50), nullable=True)  # Puenktlich, Verzoegert, Problematisch

    # Flags und Alerts
    flags = Column(CrossDBJSON, default=list)  # ["Zahlungsverzug", "Vertrag laeuft aus"]
    priority_level = Column(Integer, default=0)  # 0-10, hoeher = wichtiger

    # Synchronisation
    last_full_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_incremental_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String(20), default=RAGSyncStatus.PENDING.value)
    sync_error_message = Column(Text, nullable=True)

    # Source Documents
    source_document_count = Column(Integer, default=0)
    source_document_ids = Column(CrossDBJSON, nullable=True)  # List of UUID strings

    # Alias fuer last_sync_at Kompatibilitaet
    @property
    def last_sync_at(self):
        """Alias fuer last_full_sync_at."""
        return self.last_full_sync_at

    # Embedding fuer semantische Kundensuche
    card_embedding = Column(CrossDBVector(1024), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_rag_customer_cards_customer_id", "customer_id"),
        Index("ix_rag_customer_cards_type", "customer_type"),
        Index("ix_rag_customer_cards_priority", "priority_level"),
        Index("ix_rag_customer_cards_sync_status", "sync_status"),
    )


class RAGChatSession(Base):
    """
    Chat Session fuer RAG-basierte Dokumenten-Interaktion.

    Speichert Konversationskontext fuer:
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
    fuer Nachvollziehbarkeit.
    """
    __tablename__ = "rag_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zur Session
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_chat_sessions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Optionales angehaengtes Dokument (fuer User-Nachrichten)
    attached_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Message Content
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)

    # Thinking Content (fuer LLMs mit Thinking Mode)
    thinking_content = Column(Text, nullable=True)

    # Fuer Assistant Messages: Quellen
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
    LLM Model Registry fuer RAG Intelligence Layer.

    Speichert Konfiguration und Performance-Metriken
    fuer alle verwendeten Modelle (Embedding, Chat, Reranking).
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
    Batch Job Tracking fuer RAG-Operationen.

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
        """Prueft ob Job abgeschlossen ist."""
        return self.status in [RAGJobStatus.COMPLETED.value, RAGJobStatus.FAILED.value, RAGJobStatus.CANCELLED.value]


class RAGAnalytics(Base):
    """
    Analytics und Metriken fuer RAG-Nutzung.

    Trackt Performance und User-Interaktionen fuer:
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


# ============================================================================
# COMPANY/SYSTEM SETTINGS MODELS
# Firmeneinstellungen fuer Rechnungserkennung und Systemkonfiguration
# ============================================================================


class CompanySettings(Base):
    """
    Singleton-Tabelle fuer Firmendetails.

    Wird verwendet um zu bestimmen, ob eine hochgeladene Rechnung
    eine Eingangsrechnung (an uns) oder Ausgangsrechnung (von uns) ist.

    Diese Tabelle sollte nur einen einzigen Datensatz haben.
    """
    __tablename__ = "company_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Firmenidentifikation
    company_name = Column(String(255), nullable=False, comment="Offizieller Firmenname")
    alternative_names = Column(
        CrossDBJSON,
        default=[],
        comment="Alternative Schreibweisen fuer Dokumentenerkennung"
    )

    # Adresse
    street = Column(String(255), nullable=True, comment="Strasse mit Hausnummer")
    postal_code = Column(String(20), nullable=True, comment="PLZ")
    city = Column(String(100), nullable=True, comment="Stadt")
    country = Column(String(100), default="Deutschland", comment="Land")

    # Steueridentifikation
    vat_id = Column(String(50), nullable=True, comment="USt-IdNr. (z.B. DE123456789)")
    tax_number = Column(String(50), nullable=True, comment="Steuernummer")

    # Bankverbindung
    iban = Column(String(34), nullable=True, comment="IBAN")
    bic = Column(String(11), nullable=True, comment="BIC/SWIFT")

    # Kontaktdaten
    email = Column(String(255), nullable=True, comment="Zentrale E-Mail-Adresse")
    phone = Column(String(50), nullable=True, comment="Telefonnummer")
    website = Column(String(255), nullable=True, comment="Webseite")

    # Handelsregister
    commercial_register = Column(String(100), nullable=True, comment="Handelsregister-Nr.")
    court = Column(String(100), nullable=True, comment="Registergericht")

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_company_settings_updated", "updated_at"),
    )


# ============================================================================
# SURYA MODEL VERSIONING
# Continuous Improvement System fuer Surya OCR
# ============================================================================

class SuryaModelStatus(str, Enum):
    """Status eines Surya-Modells."""
    TRAINING = "training"       # Im Training
    EVALUATING = "evaluating"   # Wird evaluiert
    READY = "ready"             # Bereit zur Aktivierung
    ACTIVE = "active"           # Aktiv in Produktion
    INACTIVE = "inactive"       # Deaktiviert
    FAILED = "failed"           # Training fehlgeschlagen
    ROLLED_BACK = "rolled_back" # Zurueckgerollt


class SuryaTrainingRunStatus(str, Enum):
    """Status eines Training-Durchlaufs."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SuryaABTestStatus(str, Enum):
    """Status eines A/B Tests."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"


class SuryaModelVersion(Base):
    """
    Versioniertes Surya OCR Model fuer Continuous Improvement.

    Speichert:
    - Checkpoint-Pfade und Versionen
    - Qualitaetsmetriken (CER, WER, Umlaut-Accuracy)
    - Training-Konfiguration
    - Deployment-Status und A/B Testing

    Workflow:
    1. Training erzeugt neue Version (TRAINING)
    2. Benchmark evaluiert Qualitaet (EVALUATING)
    3. A/B Test mit 20% Traffic (ACTIVE + traffic_percentage)
    4. Bei Erfolg: 100% Traffic (ACTIVE + is_production)
    5. Bei Problemen: Rollback zur vorherigen Version
    """
    __tablename__ = "surya_model_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Versions-Identifikation
    version = Column(String(100), nullable=False, unique=True)  # z.B. "v1.0.3_20241215_143022"
    version_major = Column(Integer, nullable=False, default=1)
    version_minor = Column(Integer, nullable=False, default=0)
    version_patch = Column(Integer, nullable=False, default=0)

    # Checkpoint-Pfade
    checkpoint_path = Column(String(500), nullable=False)
    checkpoint_size_mb = Column(Float, nullable=True)

    # Basis-Modell
    base_model = Column(String(100), default="vikp/surya_rec")
    parent_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Qualitaetsmetriken (Benchmark-Ergebnisse)
    cer = Column(Float, nullable=True)  # Character Error Rate (Ziel: < 3%)
    wer = Column(Float, nullable=True)  # Word Error Rate (Ziel: < 8%)
    umlaut_accuracy = Column(Float, nullable=True)  # Umlaut-Genauigkeit (Ziel: 100%)
    eszett_accuracy = Column(Float, nullable=True)  # SS-Genauigkeit
    capitalization_accuracy = Column(Float, nullable=True)

    # Detaillierte Metriken (JSON)
    metrics_by_document_type = Column(CrossDBJSON, default=dict)
    umlaut_confusion_matrix = Column(CrossDBJSON, default=dict)  # {"ae->a": 5, "ue->u": 3}
    error_patterns = Column(CrossDBJSON, default=dict)

    # Training-Informationen
    training_samples_count = Column(Integer, nullable=True)
    training_epochs = Column(Integer, nullable=True)
    training_config = Column(CrossDBJSON, default=dict)
    training_duration_minutes = Column(Float, nullable=True)

    # Deployment-Status
    is_active = Column(Boolean, default=False)  # Ist aktiviert
    is_production = Column(Boolean, default=False)  # Ist Production-Modell
    traffic_percentage = Column(Float, default=0.0)  # A/B Testing Traffic-Anteil

    # Rollback-Info
    rolled_back_from_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )
    rollback_reason = Column(Text, nullable=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    activated_at = Column(DateTime(timezone=True), nullable=True)
    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    parent_version = relationship("SuryaModelVersion", remote_side=[id], foreign_keys=[parent_version_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    training_runs = relationship("SuryaTrainingRun", back_populates="model_version")
    benchmark_history = relationship(
        "SuryaBenchmarkHistory",
        back_populates="model_version",
        foreign_keys="SuryaBenchmarkHistory.model_version_id"
    )

    # Indexes
    __table_args__ = (
        Index("ix_surya_model_versions_version", "version"),
        Index("ix_surya_model_versions_is_active", "is_active"),
        Index("ix_surya_model_versions_is_production", "is_production"),
        Index("ix_surya_model_versions_created_at", "created_at"),
        Index("ix_surya_model_versions_umlaut_acc", "umlaut_accuracy"),
        Index("ix_surya_model_versions_cer", "cer"),
    )

    @property
    def full_version(self) -> str:
        """Gibt vollstaendige Version zurueck."""
        return f"v{self.version_major}.{self.version_minor}.{self.version_patch}"

    @property
    def is_quality_sufficient(self) -> bool:
        """Prueft ob Qualitaetsziele erreicht sind."""
        if self.cer is None or self.umlaut_accuracy is None:
            return False
        return self.cer < 0.03 and self.umlaut_accuracy >= 1.0


class SuryaTrainingRun(Base):
    """
    Training-Durchlauf fuer Surya Fine-Tuning.

    Dokumentiert:
    - Training-Konfiguration und Dataset
    - Fortschritt und Loss-Verlauf
    - Ressourcen-Nutzung
    - Fehlerbehandlung

    Typen:
    - full: Komplettes Training von Grund auf
    - incremental: Inkrementelles Training mit neuen Daten
    - correction_based: Training basierend auf User-Korrektionen
    """
    __tablename__ = "surya_training_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz auf resultierendes Modell
    model_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )

    # Run-Identifikation
    run_name = Column(String(255), nullable=False)
    run_type = Column(String(50), default="incremental")  # full, incremental, correction_based

    # Trigger-Informationen
    trigger_reason = Column(String(100), nullable=True)  # scheduled, correction_threshold, manual, quality_degradation
    trigger_metrics = Column(CrossDBJSON, default=dict)  # Metriken die zum Trigger fuehrten

    # Training-Konfiguration
    config = Column(CrossDBJSON, nullable=False, default=dict)
    dataset_config = Column(CrossDBJSON, default=dict)

    # Dataset-Statistiken
    training_samples = Column(Integer, default=0)
    validation_samples = Column(Integer, default=0)
    test_samples = Column(Integer, default=0)
    umlaut_samples = Column(Integer, default=0)  # Samples mit Umlauten
    fraktur_samples = Column(Integer, default=0)  # Fraktur-Samples

    # Training-Fortschritt
    status = Column(String(30), default=SuryaTrainingRunStatus.PENDING.value)
    current_epoch = Column(Integer, default=0)
    total_epochs = Column(Integer, nullable=True)
    current_step = Column(Integer, default=0)
    total_steps = Column(Integer, nullable=True)

    # Loss-Tracking
    training_loss = Column(Float, nullable=True)
    validation_loss = Column(Float, nullable=True)
    best_validation_loss = Column(Float, nullable=True)
    loss_history = Column(CrossDBJSON, default=list)  # [{epoch: 1, train_loss: 0.5, val_loss: 0.6}]

    # Metriken waehrend Training
    metrics_history = Column(CrossDBJSON, default=list)  # Checkpoint-Metriken

    # Ressourcen-Nutzung
    gpu_memory_peak_mb = Column(Integer, nullable=True)
    gpu_utilization_avg = Column(Float, nullable=True)

    # Fehlerbehandlung
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)

    # Audit
    started_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    model_version = relationship("SuryaModelVersion", back_populates="training_runs")
    started_by = relationship("User", foreign_keys=[started_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_surya_training_runs_status", "status"),
        Index("ix_surya_training_runs_type", "run_type"),
        Index("ix_surya_training_runs_model", "model_version_id"),
        Index("ix_surya_training_runs_created", "created_at"),
    )

    @property
    def progress_percent(self) -> float:
        """Berechnet Training-Fortschritt in Prozent."""
        if self.total_epochs is None or self.total_epochs == 0:
            return 0.0
        return (self.current_epoch / self.total_epochs) * 100

    @property
    def duration_minutes(self) -> Optional[float]:
        """Berechnet bisherige Dauer in Minuten."""
        if self.started_at is None:
            return None
        end_time = self.completed_at or datetime.utcnow()
        delta = end_time - self.started_at
        return delta.total_seconds() / 60


class SuryaABTest(Base):
    """
    A/B Test fuer Surya Model-Vergleich.

    Ermoeglicht:
    - Traffic-Splitting zwischen Control und Treatment
    - Statistische Signifikanz-Berechnung
    - Automatische Entscheidung und Deployment
    - Rollback bei Qualitaetsverlust

    Workflow:
    1. Control (80%) vs Treatment (20%)
    2. Mindestens 100 Samples pro Gruppe
    3. Mindestens 48 Stunden Laufzeit
    4. Entscheidung basierend auf Umlaut-Accuracy und CER
    """
    __tablename__ = "surya_ab_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Test-Identifikation
    test_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Modell-Versionen im Test
    control_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="CASCADE"),
        nullable=False
    )
    treatment_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Traffic-Konfiguration
    control_traffic_pct = Column(Float, default=80.0)
    treatment_traffic_pct = Column(Float, default=20.0)

    # Test-Status
    status = Column(String(30), default=SuryaABTestStatus.PENDING.value)

    # Erfolgskriterien
    success_criteria = Column(CrossDBJSON, default=dict)  # {"umlaut_accuracy_improvement": 0.02}
    minimum_samples = Column(Integer, default=100)
    minimum_duration_hours = Column(Integer, default=48)

    # Ergebnisse - Control
    control_samples = Column(Integer, default=0)
    control_cer = Column(Float, nullable=True)
    control_wer = Column(Float, nullable=True)
    control_umlaut_accuracy = Column(Float, nullable=True)
    control_metrics = Column(CrossDBJSON, default=dict)

    # Ergebnisse - Treatment
    treatment_samples = Column(Integer, default=0)
    treatment_cer = Column(Float, nullable=True)
    treatment_wer = Column(Float, nullable=True)
    treatment_umlaut_accuracy = Column(Float, nullable=True)
    treatment_metrics = Column(CrossDBJSON, default=dict)

    # Statistische Analyse
    statistical_significance = Column(Float, nullable=True)  # p-value
    confidence_interval_lower = Column(Float, nullable=True)
    confidence_interval_upper = Column(Float, nullable=True)
    effect_size = Column(Float, nullable=True)

    # Entscheidung
    winner = Column(String(20), nullable=True)  # control, treatment, inconclusive
    decision_reason = Column(Text, nullable=True)
    auto_deployed = Column(Boolean, default=False)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    control_version = relationship("SuryaModelVersion", foreign_keys=[control_version_id])
    treatment_version = relationship("SuryaModelVersion", foreign_keys=[treatment_version_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_surya_ab_tests_status", "status"),
        Index("ix_surya_ab_tests_control", "control_version_id"),
        Index("ix_surya_ab_tests_treatment", "treatment_version_id"),
        Index("ix_surya_ab_tests_created", "created_at"),
    )

    @property
    def is_ready_for_decision(self) -> bool:
        """Prueft ob Test bereit fuer Entscheidung ist."""
        if self.control_samples < self.minimum_samples:
            return False
        if self.treatment_samples < self.minimum_samples:
            return False
        if self.started_at is None:
            return False
        elapsed_hours = (datetime.utcnow() - self.started_at).total_seconds() / 3600
        return elapsed_hours >= self.minimum_duration_hours

    @property
    def treatment_improvement(self) -> Optional[float]:
        """Berechnet Verbesserung der Treatment-Gruppe."""
        if self.control_umlaut_accuracy is None or self.treatment_umlaut_accuracy is None:
            return None
        return self.treatment_umlaut_accuracy - self.control_umlaut_accuracy


class SuryaBenchmarkHistory(Base):
    """
    Benchmark-History fuer Surya Model Versionen.

    Speichert detaillierte Benchmark-Ergebnisse fuer:
    - Trendanalyse ueber Zeit
    - Vergleich zwischen Versionen
    - Identifikation von Regressionen
    """
    __tablename__ = "surya_benchmark_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Modell-Referenz
    model_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="CASCADE"),
        nullable=False
    )

    # Benchmark-Kontext
    benchmark_type = Column(String(50), default="full")  # full, umlaut_focus, fraktur, quick
    test_fixtures_count = Column(Integer, nullable=True)

    # Aggregierte Metriken
    avg_cer = Column(Float, nullable=True)
    avg_wer = Column(Float, nullable=True)
    avg_umlaut_accuracy = Column(Float, nullable=True)
    avg_processing_time_ms = Column(Float, nullable=True)

    # Percentile
    p50_cer = Column(Float, nullable=True)
    p90_cer = Column(Float, nullable=True)
    p95_cer = Column(Float, nullable=True)
    p99_cer = Column(Float, nullable=True)

    # Detaillierte Ergebnisse
    results_by_fixture = Column(CrossDBJSON, default=dict)
    results_by_document_type = Column(CrossDBJSON, default=dict)
    umlaut_confusion_details = Column(CrossDBJSON, default=dict)

    # Vergleich mit vorheriger Version
    comparison_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("surya_model_versions.id", ondelete="SET NULL"),
        nullable=True
    )
    cer_improvement = Column(Float, nullable=True)
    wer_improvement = Column(Float, nullable=True)
    umlaut_accuracy_improvement = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    model_version = relationship("SuryaModelVersion", back_populates="benchmark_history", foreign_keys=[model_version_id])
    comparison_version = relationship("SuryaModelVersion", foreign_keys=[comparison_version_id])

    # Indexes
    __table_args__ = (
        Index("ix_surya_benchmark_history_model", "model_version_id"),
        Index("ix_surya_benchmark_history_type", "benchmark_type"),
        Index("ix_surya_benchmark_history_created", "created_at"),
    )


# =============================================================================
# BUSINESS DOCUMENT PROFILES - Auto Ground-Truth Pipeline
# =============================================================================

class BusinessDocumentProfile(Base):
    """
    Business Document Profile fuer priorisierte Training-Pipeline.

    Bei 500+ Dokumenten/Tag ist manuelle Annotation unrealistisch.
    Dieses Model definiert:
    - Geschaeftskritische Dokumenttypen (Rechnungen, Vertraege, Briefe)
    - Taegliche Volumen-Schaetzungen
    - Auto-Accept Schwellenwerte fuer High-Confidence OCR

    Beispiel:
        Invoice: daily_volume=300, business_criticality=1.5, auto_accept_confidence=0.95
        Contract: daily_volume=100, business_criticality=1.3, auto_accept_confidence=0.95
        Letter: daily_volume=100, business_criticality=1.0, auto_accept_confidence=0.93
    """
    __tablename__ = "business_document_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokumenttyp-Identifikation
    document_type = Column(String(50), unique=True, nullable=False)  # "invoice", "contract", "letter"
    display_name = Column(String(100), nullable=False)  # "Rechnung", "Vertrag", "Brief"
    description = Column(Text, nullable=True)

    # Business-Gewichtung
    estimated_daily_volume = Column(Integer, default=100)  # Geschaetzte Dokumente pro Tag
    business_criticality = Column(Float, default=1.0)  # 1.5 = hoch, 1.0 = normal, 0.5 = niedrig

    # Auto-Annotation Schwellenwerte
    auto_accept_confidence = Column(Float, default=0.95)  # Minimum Confidence fuer Auto-Accept
    min_text_length = Column(Integer, default=50)  # Minimum Textlaenge fuer gueltige Samples
    require_umlaut_validation = Column(Boolean, default=True)  # Umlaut-Check vor Auto-Accept

    # Training-Gewichtung (berechnet)
    training_weight = Column(Float, default=1.0)  # Wird aus criticality + volume berechnet
    target_coverage = Column(Float, default=0.90)  # Ziel: 90% Abdeckung

    # Validierungsregeln (JSON)
    validation_rules = Column(CrossDBJSON, default=dict)
    # Beispiel: {"required_fields": ["invoice_number", "date", "amount"], "date_patterns": [...]}

    # Statistiken (wird periodisch aktualisiert)
    current_sample_count = Column(Integer, default=0)
    verified_sample_count = Column(Integer, default=0)
    auto_accepted_count = Column(Integer, default=0)
    coverage_percentage = Column(Float, default=0.0)

    # Aktivierung
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_business_document_profiles_type", "document_type"),
        Index("ix_business_document_profiles_active", "is_active"),
        Index("ix_business_document_profiles_criticality", "business_criticality"),
    )

    def calculate_training_weight(self) -> float:
        """Berechnet Training-Gewicht aus Volumen und Kritikalitaet."""
        volume_factor = min(self.estimated_daily_volume / 100.0, 3.0)  # Max 3x
        return volume_factor * self.business_criticality

    def calculate_coverage(self) -> float:
        """Berechnet aktuelle Coverage gegen Ziel."""
        if self.estimated_daily_volume == 0:
            return 1.0
        target_samples = int(self.estimated_daily_volume * self.target_coverage * 0.1)  # 10% Sample-Ratio
        if target_samples == 0:
            return 1.0
        return min(self.verified_sample_count / target_samples, 1.0)


class CoverageSnapshot(Base):
    """
    Taeglicher Coverage-Snapshot fuer Trend-Analyse.

    Celery Beat Task speichert taeglich den Stand der Ground-Truth-Abdeckung
    fuer alle Business-Dokumenttypen.
    """
    __tablename__ = "coverage_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Snapshot-Datum
    snapshot_date = Column(DateTime(timezone=True), nullable=False)

    # Aggregierte Metriken
    total_documents_processed = Column(Integer, default=0)
    total_auto_accepted = Column(Integer, default=0)
    total_manually_verified = Column(Integer, default=0)
    total_rejected = Column(Integer, default=0)

    # Coverage pro Dokumenttyp (JSON)
    coverage_by_type = Column(CrossDBJSON, default=dict)
    # Beispiel: {"invoice": 0.92, "contract": 0.78, "letter": 0.85}

    # Gewichtete Gesamt-Coverage
    weighted_coverage = Column(Float, default=0.0)

    # Qualitaetsmetriken der Auto-Accepts
    auto_accept_avg_confidence = Column(Float, nullable=True)
    spot_check_success_rate = Column(Float, nullable=True)  # Rate der bestandenen Stichproben

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_coverage_snapshots_date", "snapshot_date"),
        Index("ix_coverage_snapshots_weighted", "weighted_coverage"),
    )


# =============================================================================
# E-INVOICING (ZUGFeRD / XRechnung)
# =============================================================================

class EInvoiceFormat(str, Enum):
    """Unterstuetzte E-Rechnungsformate."""
    ZUGFERD = "zugferd"
    XRECHNUNG_CII = "xrechnung_cii"  # UN/CEFACT Cross Industry Invoice
    XRECHNUNG_UBL = "xrechnung_ubl"  # Universal Business Language
    FACTURX = "facturx"


class EInvoiceProfile(str, Enum):
    """ZUGFeRD/Factur-X Profile (EN 16931 Konformitaet)."""
    MINIMUM = "MINIMUM"
    BASIC = "BASIC"
    BASIC_WL = "BASIC_WL"
    EN16931 = "EN16931"
    EXTENDED = "EXTENDED"
    XRECHNUNG = "XRECHNUNG"


class EInvoiceDocument(Base):
    """
    E-Rechnung Metadaten und XML-Speicherung.

    Speichert:
    - Extrahiertes oder generiertes XML (ZUGFeRD/XRechnung)
    - Validierungsergebnisse (KoSIT Validator)
    - Generierungsmetadaten
    - Leitweg-ID fuer schnellen B2G-Lookup

    Jedes Dokument kann null oder eine zugehoerige E-Rechnung haben.
    """
    __tablename__ = "einvoice_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zum Original-Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True  # 1:1 Beziehung
    )

    # E-Invoice Format Information
    format = Column(String(50), nullable=False)  # EInvoiceFormat Wert
    profile = Column(String(50), nullable=True)  # EInvoiceProfile Wert
    version = Column(String(20), nullable=True)  # z.B. "2.3.3", "3.0.2"

    # XML Speicherung
    xml_content = Column(Text, nullable=True)  # Der extrahierte oder generierte XML-Inhalt
    xml_hash = Column(String(64), nullable=True)  # SHA256 fuer Integritaetspruefung

    # Validierung
    is_valid = Column(Boolean, nullable=True)  # null = nicht validiert
    validation_timestamp = Column(DateTime(timezone=True), nullable=True)
    validation_errors = Column(CrossDBJSON, default=list)  # Liste von Validierungsfehlern
    validation_warnings = Column(CrossDBJSON, default=list)  # Liste von Warnungen
    validator_used = Column(String(50), nullable=True)  # "kosit", "mustang", "facturx"

    # Schema/Schematron Validierung separat
    schema_valid = Column(Boolean, nullable=True)  # XSD Schema-Validierung
    schematron_valid = Column(Boolean, nullable=True)  # Business Rules (Schematron)
    pdf_a_compliant = Column(Boolean, nullable=True)  # PDF/A-3 Konformitaet (bei ZUGFeRD)

    # B2G-spezifische Felder (schneller Lookup)
    leitweg_id = Column(String(100), nullable=True, index=True)  # BT-10 Buyer Reference

    # Generierungsmetadaten
    was_generated = Column(Boolean, default=False)  # True wenn wir die E-Rechnung erstellt haben
    was_extracted = Column(Boolean, default=False)  # True wenn aus PDF extrahiert
    generation_timestamp = Column(DateTime(timezone=True), nullable=True)
    generated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Originalquelle (wenn extrahiert)
    source_filename = Column(String(255), nullable=True)  # Original ZUGFeRD-PDF Name
    extraction_method = Column(String(50), nullable=True)  # "facturx", "mustang", "manual"

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="einvoice_data")
    generated_by = relationship("User", foreign_keys=[generated_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_einvoice_docs_document_id", "document_id"),
        Index("ix_einvoice_docs_format", "format"),
        Index("ix_einvoice_docs_leitweg_id", "leitweg_id"),
        Index("ix_einvoice_docs_is_valid", "is_valid"),
        Index("ix_einvoice_docs_was_generated", "was_generated"),
    )

    def mark_validated(
        self,
        is_valid: bool,
        validator: str,
        errors: Optional[List[Dict[str, Any]]] = None,
        warnings: Optional[List[Dict[str, Any]]] = None,
        schema_valid: Optional[bool] = None,
        schematron_valid: Optional[bool] = None
    ) -> None:
        """Markiert die E-Rechnung als validiert."""
        self.is_valid = is_valid
        self.validator_used = validator
        self.validation_timestamp = datetime.now()
        self.validation_errors = errors or []
        self.validation_warnings = warnings or []
        if schema_valid is not None:
            self.schema_valid = schema_valid
        if schematron_valid is not None:
            self.schematron_valid = schematron_valid

    def get_validation_summary(self) -> Dict[str, Any]:
        """Gibt eine Zusammenfassung der Validierung zurueck."""
        return {
            "is_valid": self.is_valid,
            "validator": self.validator_used,
            "validated_at": self.validation_timestamp.isoformat() if self.validation_timestamp else None,
            "error_count": len(self.validation_errors) if self.validation_errors else 0,
            "warning_count": len(self.validation_warnings) if self.validation_warnings else 0,
            "schema_valid": self.schema_valid,
            "schematron_valid": self.schematron_valid,
            "pdf_a_compliant": self.pdf_a_compliant,
        }


# =============================================================================
# BANKING INTEGRATION MODELS
# =============================================================================

class BankAccount(Base):
    """Bankkonto fuer Transaktions-Import und Zahlungen."""
    __tablename__ = "bank_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Konto-Identifikation
    account_name = Column(String(255), nullable=False)
    iban = Column(String(34), nullable=False)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(255), nullable=True)
    account_holder = Column(String(255), nullable=True)
    account_type = Column(String(50), default="checking")

    # FinTS (optional)
    blz = Column(String(8), nullable=True)
    fints_url = Column(String(500), nullable=True)
    fints_version = Column(String(10), default="3.0")
    login_id_encrypted = Column(String(500), nullable=True)
    pin_hash = Column(String(255), nullable=True)

    # TAN-Konfiguration
    tan_method = Column(String(50), nullable=True)
    tan_media = Column(String(100), nullable=True)
    tan_mechanism_id = Column(String(20), nullable=True)

    # Sync-Konfiguration
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    sync_from_date = Column(DateTime(timezone=True), nullable=True)
    auto_sync_enabled = Column(Boolean, default=False)
    sync_interval_hours = Column(Integer, default=24)

    # Saldo
    current_balance = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    balance_date = Column(DateTime(timezone=True), nullable=True)
    currency = Column(String(3), default="EUR")

    # Status
    is_active = Column(Boolean, default=True)
    connection_status = Column(String(50), default="manual")
    last_error = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="bank_accounts")
    transactions = relationship("BankTransaction", back_populates="bank_account", cascade="all, delete-orphan")
    imports = relationship("BankImport", back_populates="bank_account")


class BankImport(Base):
    """Import-Historie fuer Kontoauszuege."""
    __tablename__ = "bank_imports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True)

    # Import-Details
    filename = Column(String(255), nullable=True)
    file_hash = Column(String(64), nullable=True)
    file_size = Column(Integer, nullable=True)

    # Format
    format = Column(String(50), nullable=False)
    format_variant = Column(String(100), nullable=True)

    # Ergebnis
    status = Column(String(50), default="pending")
    transaction_count = Column(Integer, default=0)
    duplicate_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    errors = Column(CrossDBJSON, default=list)

    # Zeitraum
    date_from = Column(DateTime(timezone=True), nullable=True)
    date_to = Column(DateTime(timezone=True), nullable=True)

    # Audit
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    processing_duration_ms = Column(Integer, nullable=True)

    # Relationships
    user = relationship("User", backref="bank_imports")
    bank_account = relationship("BankAccount", back_populates="imports")


class BankTransaction(Base):
    """Importierte Kontobewegungen."""
    __tablename__ = "bank_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)
    import_id = Column(UUID(as_uuid=True), ForeignKey("bank_imports.id", ondelete="SET NULL"), nullable=True)

    # Transaktions-ID
    transaction_id = Column(String(100), nullable=True)
    booking_date = Column(DateTime(timezone=True), nullable=False)
    value_date = Column(DateTime(timezone=True), nullable=False)

    # Betrag
    amount = Column(Numeric(15, 2), nullable=False)  # SECURITY: Numeric fuer Geldbetraege
    currency = Column(String(3), default="EUR")

    # Gegenpartei
    counterparty_name = Column(String(255), nullable=True)
    counterparty_iban = Column(String(34), nullable=True)
    counterparty_bic = Column(String(11), nullable=True)
    counterparty_bank_name = Column(String(255), nullable=True)

    # Verwendungszweck
    reference_text = Column(Text, nullable=True)
    end_to_end_id = Column(String(35), nullable=True)
    mandate_id = Column(String(35), nullable=True)
    creditor_id = Column(String(35), nullable=True)

    # Kategorisierung
    transaction_type = Column(String(50), nullable=True)
    booking_text = Column(String(100), nullable=True)
    prima_nota = Column(String(20), nullable=True)

    # Geparste Referenzen
    parsed_invoice_numbers = Column(CrossDBJSON, default=list)
    parsed_customer_numbers = Column(CrossDBJSON, default=list)
    parsed_references = Column(CrossDBJSON, default=list)

    # Reconciliation
    reconciliation_status = Column(String(50), default="unmatched")
    matched_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    matched_invoice_number = Column(String(100), nullable=True)
    match_confidence = Column(Float, nullable=True)
    match_method = Column(String(50), nullable=True)
    matched_at = Column(DateTime(timezone=True), nullable=True)
    matched_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Teilzahlungen
    allocated_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    remaining_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    is_partial_payment = Column(Boolean, default=False)
    parent_transaction_id = Column(UUID(as_uuid=True), ForeignKey("bank_transactions.id", ondelete="SET NULL"), nullable=True)

    # Rohdaten
    raw_data = Column(CrossDBJSON, nullable=True)

    # Audit
    imported_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    bank_account = relationship("BankAccount", back_populates="transactions")
    matched_document = relationship("Document", backref="matched_transactions")
    matched_by = relationship("User", foreign_keys=[matched_by_id])


class PaymentBatch(Base):
    """Sammelzahlungen."""
    __tablename__ = "payment_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)

    # Batch-Details
    batch_name = Column(String(255), nullable=True)
    batch_type = Column(String(50), nullable=False)
    payment_count = Column(Integer, default=0)
    total_amount = Column(Numeric(15, 2), default=0)  # SECURITY: Numeric fuer Geldbetraege
    currency = Column(String(3), default="EUR")

    # Ausfuehrung
    requested_execution_date = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(String(50), default="draft")

    # TAN
    tan_required = Column(Boolean, default=False)
    tan_challenge = Column(Text, nullable=True)
    tan_challenge_data = Column(Text, nullable=True)

    # Freigabe
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # SEPA XML
    sepa_xml = Column(Text, nullable=True)
    sepa_message_id = Column(String(35), nullable=True)

    # Ergebnis
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    successful_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)

    # Fehler
    last_error = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    payments = relationship("PaymentOrder", back_populates="batch")


class PaymentOrder(Base):
    """SEPA-Zahlungsauftraege."""
    __tablename__ = "payment_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="CASCADE"), nullable=False)

    # Verknuepfte Rechnung
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    invoice_number = Column(String(100), nullable=True)

    # Zahlungstyp
    payment_type = Column(String(50), nullable=False)
    sepa_type = Column(String(50), nullable=True)

    # Empfaenger
    beneficiary_name = Column(String(140), nullable=False)
    beneficiary_iban = Column(String(34), nullable=False)
    beneficiary_bic = Column(String(11), nullable=True)

    # Betrag
    amount = Column(Numeric(15, 2), nullable=False)  # SECURITY: Numeric fuer Geldbetraege
    currency = Column(String(3), default="EUR")

    # Zahlungsdetails
    reference = Column(Text, nullable=True)
    end_to_end_id = Column(String(35), nullable=True)
    execution_date = Column(DateTime(timezone=True), nullable=True)

    # Lastschrift
    mandate_id = Column(String(35), nullable=True)
    mandate_date = Column(DateTime(timezone=True), nullable=True)
    sequence_type = Column(String(10), nullable=True)
    creditor_id = Column(String(35), nullable=True)

    # Batch
    batch_id = Column(UUID(as_uuid=True), ForeignKey("payment_batches.id", ondelete="SET NULL"), nullable=True)
    batch_sequence = Column(Integer, nullable=True)

    # Status
    status = Column(String(50), default="draft")

    # TAN
    tan_required = Column(Boolean, default=False)
    tan_challenge = Column(Text, nullable=True)
    tan_challenge_data = Column(Text, nullable=True)
    tan_entered_at = Column(DateTime(timezone=True), nullable=True)

    # Freigabe
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Uebermittlung
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    bank_reference = Column(String(100), nullable=True)

    # Fehler
    last_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)

    # Skonto
    uses_skonto = Column(Boolean, default=False)
    skonto_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    original_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    skonto_deadline = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    document = relationship("Document", backref="payment_orders")
    batch = relationship("PaymentBatch", back_populates="payments")


class DunningRecord(Base):
    """Mahnwesen-Tracking."""
    __tablename__ = "dunning_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Rechnungsreferenz
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    gross_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    outstanding_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    currency = Column(String(3), default="EUR")

    # Geschaeftspartner
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)
    debtor_name = Column(String(255), nullable=True)
    debtor_email = Column(String(255), nullable=True)

    # Mahnstufe
    dunning_level = Column(Integer, default=0)

    # Gebuehren
    reminder_fee = Column(Numeric(15, 2), default=0)  # SECURITY: Numeric fuer Geldbetraege
    late_interest_rate = Column(Numeric(7, 4), nullable=True)  # Prozentsatz mit 4 Nachkommastellen
    accrued_interest = Column(Numeric(15, 2), default=0)  # SECURITY: Numeric fuer Geldbetraege
    total_outstanding = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege

    # Timeline
    first_reminder_at = Column(DateTime(timezone=True), nullable=True)
    second_reminder_at = Column(DateTime(timezone=True), nullable=True)
    final_reminder_at = Column(DateTime(timezone=True), nullable=True)
    next_action_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    status = Column(String(50), default="pending")

    # B2B/B2C Unterscheidung (BGB §286 Compliance)
    is_b2b = Column(Boolean, default=True, comment="B2B: +9% Zinsen, B2C: +5% Zinsen")
    b2b_pauschale_claimed = Column(Boolean, default=False, comment="EUR40 Pauschale nach §288 Abs. 5 BGB")

    # Mahnstopp (fuer Reklamationen/Disputes)
    mahnstopp = Column(Boolean, default=False, comment="Stoppt automatische Mahnung")
    mahnstopp_reason = Column(String(255), nullable=True)
    mahnstopp_until = Column(DateTime(timezone=True), nullable=True)

    # Loesung
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Teilzahlungen
    partial_payment_ids = Column(CrossDBJSON, default=list)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    document = relationship("Document", backref="dunning_records")
    business_entity = relationship("BusinessEntity", backref="dunning_records")
    history_entries = relationship("MahnungHistory", back_populates="dunning_record", cascade="all, delete-orphan")
    tasks = relationship("MahnTask", back_populates="dunning_record", cascade="all, delete-orphan")
    phone_calls = relationship("PhoneCallLog", back_populates="dunning_record", cascade="all, delete-orphan")


# =============================================================================
# MAHNUNGSWESEN MODELS (Dunning System Extensions)
# =============================================================================


class MahnungHistory(Base):
    """Immutable Audit-Log fuer Mahnvorgaenge.

    WICHTIG: Diese Tabelle ist append-only!
    Ein Datenbank-Trigger sollte UPDATE und DELETE verhindern.
    """
    __tablename__ = "mahnung_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dunning_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dunning_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktion
    action_type = Column(String(50), nullable=False, comment="reminder_sent, escalated, phone_call, payment_received, etc.")
    mahn_stufe = Column(Integer, nullable=False, comment="Mahnstufe zum Zeitpunkt der Aktion")
    action_timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Ausfuehrender
    performed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Details
    notes = Column(Text, nullable=True)
    outcome = Column(String(50), nullable=True, comment="success, failed, pending, etc.")
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Zusaetzliche Metadaten (JSON)
    # HINWEIS: 'metadata' ist in SQLAlchemy reserviert, daher 'action_metadata'
    action_metadata = Column(CrossDBJSON, default=dict)

    # Relationships
    dunning_record = relationship("DunningRecord", back_populates="history_entries")
    performed_by = relationship("User", foreign_keys=[performed_by_id])
    generated_document = relationship("Document", foreign_keys=[document_id])

    # Indexes
    __table_args__ = (
        Index("ix_mahnung_history_action_timestamp", "action_timestamp"),
        Index("ix_mahnung_history_action_type", "action_type"),
    )


class MahnTask(Base):
    """Aufgaben fuer das Mahnungswesen.

    Tasks werden vom taeglichen Mahnlauf erstellt und erscheinen
    im Dashboard zur manuellen Bearbeitung.
    """
    __tablename__ = "mahn_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dunning_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dunning_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aufgabentyp
    task_type = Column(String(50), nullable=False, comment="reminder, escalate, phone_call, review, collection")

    # Zuweisung
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Faelligkeit
    due_date = Column(Date, nullable=False)

    # Status
    status = Column(String(20), default="pending", nullable=False, comment="pending, in_progress, completed, snoozed, cancelled")

    # Snooze (max 3x)
    snoozed_until = Column(Date, nullable=True)
    snooze_count = Column(Integer, default=0)
    snooze_reason = Column(String(255), nullable=True)

    # Abschluss
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completion_notes = Column(Text, nullable=True)

    # Prioritaet (1=hoechste, 5=niedrigste)
    priority = Column(Integer, default=3)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    dunning_record = relationship("DunningRecord", back_populates="tasks")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    completed_by = relationship("User", foreign_keys=[completed_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_mahn_tasks_status", "status"),
        Index("ix_mahn_tasks_due_date", "due_date"),
        Index("ix_mahn_tasks_assigned_user", "assigned_user_id"),
    )


class PhoneCallLog(Base):
    """Telefonkontakt-Protokoll fuer Mahnungswesen.

    Dokumentiert alle telefonischen Kontaktversuche und deren Ergebnis.
    """
    __tablename__ = "phone_call_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dunning_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dunning_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Anrufdaten
    called_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    called_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Kontakt
    contact_name = Column(String(255), nullable=False)
    phone_number = Column(String(50), nullable=True)

    # Ergebnis
    outcome = Column(String(50), nullable=False, comment="reached, not_reached, voicemail, callback_requested, payment_promised, dispute_raised")

    # Notizen
    notes = Column(Text, nullable=True)

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(Date, nullable=True)
    follow_up_notes = Column(String(255), nullable=True)

    # Relationship
    dunning_record = relationship("DunningRecord", back_populates="phone_calls")
    called_by = relationship("User", foreign_keys=[called_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_phone_call_logs_called_at", "called_at"),
    )


class DunningStageConfig(Base):
    """Konfigurierbare Mahnstufen.

    Admin kann eigene Mahnstufen definieren mit:
    - Tagen nach Faelligkeit
    - Aktionstyp (Email, Brief, Telefon)
    - Mahngebuehr
    - Template
    """
    __tablename__ = "dunning_stage_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Stage-Definition
    stage_number = Column(Integer, nullable=False, comment="1-basiert: 1=erste Stufe")
    stage_name = Column(String(100), nullable=False, comment="z.B. Zahlungserinnerung, 1. Mahnung")

    # Trigger
    trigger_days_after_due = Column(Integer, nullable=False, comment="Tage nach Faelligkeit")

    # Aktion
    action_type = Column(String(50), nullable=False, comment="email, letter, phone, escalation")
    template_id = Column(UUID(as_uuid=True), nullable=True, comment="Template-ID fuer Dokument-Generierung")

    # Gebuehren
    fee_amount = Column(Numeric(10, 2), default=0, comment="Mahngebuehr in EUR")

    # Status
    is_active = Column(Boolean, default=True)

    # Sortierung (fuer Drag-and-Drop Reorder)
    sort_order = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="dunning_stage_configs")

    # Indexes und Constraints
    __table_args__ = (
        Index("ix_dunning_stage_configs_user_id", "user_id"),
        Index("ix_dunning_stage_configs_sort_order", "user_id", "sort_order"),
    )


class CustomerDunningOverride(Base):
    """Kundenspezifische Mahneinstellungen.

    Ermoeglicht Sonderbehandlung fuer bestimmte Kunden:
    - Eigene Zahlungsfristen
    - Max. Mahnstufe
    - Ausschluss von automatischer Mahnung
    """
    __tablename__ = "customer_dunning_overrides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )

    # Zahlungsbedingungen
    custom_payment_terms_days = Column(Integer, nullable=True, comment="Abweichende Zahlungsfrist")

    # Mahnung
    max_mahn_stufe = Column(Integer, nullable=True, comment="Max. Eskalationsstufe (z.B. 2 = nie Inkasso)")
    preferred_contact_method = Column(String(50), default="email", comment="email, phone, letter")

    # Ausschluss
    exclude_from_auto_dunning = Column(Boolean, default=False, comment="Keine automatischen Mahnungen")
    exclusion_reason = Column(String(255), nullable=True)

    # Notizen
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    business_entity = relationship("BusinessEntity", backref="dunning_override")

    # Indexes
    __table_args__ = (
        Index("ix_customer_dunning_overrides_entity", "business_entity_id"),
    )


class CashFlowEntry(Base):
    """Cash-Flow-Prognosen."""
    __tablename__ = "cash_flow_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    bank_account_id = Column(UUID(as_uuid=True), ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True)

    # Eintragstyp
    entry_type = Column(String(50), nullable=False)
    direction = Column(String(10), nullable=False)

    # Referenzen
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    payment_order_id = Column(UUID(as_uuid=True), ForeignKey("payment_orders.id", ondelete="SET NULL"), nullable=True)
    transaction_id = Column(UUID(as_uuid=True), ForeignKey("bank_transactions.id", ondelete="SET NULL"), nullable=True)

    # Datum
    expected_date = Column(DateTime(timezone=True), nullable=False)
    actual_date = Column(DateTime(timezone=True), nullable=True)

    # Betrag
    expected_amount = Column(Numeric(15, 2), nullable=False)  # SECURITY: Numeric fuer Geldbetraege
    actual_amount = Column(Numeric(15, 2), nullable=True)  # SECURITY: Numeric fuer Geldbetraege
    currency = Column(String(3), default="EUR")

    # Wahrscheinlichkeit
    probability = Column(Float, default=1.0)

    # Beschreibung
    description = Column(String(255), nullable=True)
    category = Column(String(50), nullable=True)

    # Status
    status = Column(String(50), default="expected")

    # Gegenpartei
    counterparty_name = Column(String(255), nullable=True)
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="cash_flow_entries")
    document = relationship("Document", backref="cash_flow_entries")
    payment_order = relationship("PaymentOrder", backref="cash_flow_entries")
    transaction = relationship("BankTransaction", backref="cash_flow_entries")
    business_entity = relationship("BusinessEntity", backref="cash_flow_entries")


# =============================================================================
# DATEV EXPORT MODELS
# =============================================================================


class DATEVConfiguration(Base):
    """
    DATEV Export Konfiguration.

    Speichert Steuerberater-Zugangsdaten und Konteneinstellungen
    fuer den DATEV Buchungsstapel-Export.

    Jeder Benutzer kann mehrere Konfigurationen haben (z.B. fuer verschiedene
    Mandanten oder Testumgebungen).
    """

    __tablename__ = "datev_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment="Benutzer-spezifische Konfiguration"
    )

    # DATEV Pflichtfelder
    berater_nr = Column(
        String(7),
        nullable=False,
        comment="Beraternummer (max. 7-stellig)"
    )
    mandanten_nr = Column(
        String(5),
        nullable=False,
        comment="Mandantennummer (max. 5-stellig)"
    )
    wj_beginn = Column(
        Date,
        nullable=False,
        comment="Wirtschaftsjahr-Beginn"
    )

    # Kontenrahmen
    kontenrahmen = Column(
        String(10),
        nullable=False,
        default="SKR03",
        comment="SKR03 oder SKR04"
    )

    # Standardkonten Eingangsrechnungen
    incoming_expense_account = Column(
        String(10),
        nullable=True,
        comment="Aufwandskonto Eingang (z.B. 4200)"
    )
    incoming_creditor_account = Column(
        String(10),
        nullable=True,
        comment="Kreditorenkonto Eingang (z.B. 70000)"
    )

    # Standardkonten Ausgangsrechnungen
    outgoing_revenue_account = Column(
        String(10),
        nullable=True,
        comment="Erloeskonto Ausgang (z.B. 8400)"
    )
    outgoing_debtor_account = Column(
        String(10),
        nullable=True,
        comment="Debitorenkonto Ausgang (z.B. 10000)"
    )

    # Sammelkonten
    sammelkonto_kreditoren = Column(
        String(10),
        default="1600",
        comment="Sammelkonto Kreditoren"
    )
    sammelkonto_debitoren = Column(
        String(10),
        default="1400",
        comment="Sammelkonto Debitoren"
    )

    # Optionale Einstellungen
    sachkontenlange = Column(
        Integer,
        default=4,
        comment="Laenge Sachkonten (4-8 Stellen)"
    )
    buchungstext_format = Column(
        String(100),
        default="{invoice_number}",
        comment="Format fuer Buchungstext"
    )

    # Status
    is_default = Column(Boolean, default=False, comment="Standard-Konfiguration")
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="datev_configurations")
    vendor_mappings = relationship(
        "DATEVVendorMapping",
        back_populates="config",
        cascade="all, delete-orphan"
    )
    exports = relationship(
        "DATEVExport",
        back_populates="config",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_datev_configurations_user_id", "user_id"),
        Index("ix_datev_configurations_is_default", "is_default"),
        Index("ix_datev_configurations_is_active", "is_active"),
        CheckConstraint(
            "kontenrahmen IN ('SKR03', 'SKR04')",
            name="ck_datev_config_kontenrahmen"
        ),
        CheckConstraint(
            "sachkontenlange BETWEEN 4 AND 8",
            name="ck_datev_config_sachkontenlange"
        ),
    )


class DATEVVendorMapping(Base):
    """
    Lieferanten-spezifische Kontozuordnung.

    Ermoeglicht individuelle Konten pro Lieferant statt Standardkonten.
    Matching erfolgt ueber verschiedene Kriterien (Name, USt-IdNr, IBAN, Entity).
    """

    __tablename__ = "datev_vendor_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_configurations.id", ondelete="CASCADE"),
        nullable=False
    )

    # Lieferanten-Identifikation (mehrere Match-Optionen)
    vendor_name = Column(
        String(255),
        nullable=True,
        comment="Firmenname (Fuzzy-Match)"
    )
    vendor_vat_id = Column(
        String(50),
        nullable=True,
        comment="USt-IdNr (exakter Match)"
    )
    vendor_iban = Column(
        String(34),
        nullable=True,
        comment="IBAN (exakter Match)"
    )
    business_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknuepfter Geschaeftspartner"
    )

    # Kontozuordnung
    expense_account = Column(
        String(10),
        nullable=False,
        comment="Aufwandskonto"
    )
    creditor_account = Column(
        String(10),
        nullable=True,
        comment="Personenkonto (Kreditor)"
    )
    cost_center = Column(
        String(20),
        nullable=True,
        comment="Kostenstelle"
    )
    cost_object = Column(
        String(20),
        nullable=True,
        comment="Kostentraeger"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    config = relationship("DATEVConfiguration", back_populates="vendor_mappings")
    business_entity = relationship("BusinessEntity", backref="datev_vendor_mappings")

    __table_args__ = (
        Index("ix_datev_vendor_mappings_config_id", "config_id"),
        Index("ix_datev_vendor_mappings_vendor_vat_id", "vendor_vat_id"),
        Index("ix_datev_vendor_mappings_vendor_iban", "vendor_iban"),
        Index("ix_datev_vendor_mappings_business_entity_id", "business_entity_id"),
    )


class DATEVExport(Base):
    """
    DATEV Export Historie.

    Protokolliert alle Exporte fuer Audit und Nachvollziehbarkeit.
    Speichert welche Dokumente wann in welchen Export einbezogen wurden.
    """

    __tablename__ = "datev_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_configurations.id", ondelete="CASCADE"),
        nullable=False
    )
    exported_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Export-Details
    export_type = Column(
        String(50),
        nullable=False,
        default="buchungsstapel",
        comment="buchungsstapel, stammdaten"
    )
    filename = Column(String(255), nullable=False)
    document_count = Column(Integer, default=0)

    # Zeitraum
    period_from = Column(Date, nullable=True)
    period_to = Column(Date, nullable=True)

    # Datei-Metadaten
    content_hash = Column(
        String(64),
        nullable=True,
        comment="SHA256 der Export-Datei"
    )
    file_size_bytes = Column(Integer, nullable=True)

    # Status
    status = Column(
        String(20),
        default="completed",
        comment="completed, failed, partial"
    )
    error_message = Column(Text, nullable=True)

    # Inkludierte Dokumente
    included_documents = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Array von Dokument-UUIDs"
    )
    skipped_documents = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Array von uebersprungenen Dokument-UUIDs"
    )
    warnings = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Array von Warnmeldungen"
    )

    # Audit
    exported_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    config = relationship("DATEVConfiguration", back_populates="exports")
    exported_by = relationship("User", backref="datev_exports")

    __table_args__ = (
        Index("ix_datev_exports_config_id", "config_id"),
        Index("ix_datev_exports_exported_by_id", "exported_by_id"),
        Index("ix_datev_exports_exported_at", "exported_at"),
        Index("ix_datev_exports_period", "period_from", "period_to"),
        Index("ix_datev_exports_status", "status"),
        CheckConstraint(
            "status IN ('completed', 'failed', 'partial')",
            name="ck_datev_exports_status"
        ),
    )
