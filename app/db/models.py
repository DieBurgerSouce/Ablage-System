"""SQLAlchemy database models for Ablage-System."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
import uuid

from sqlalchemy import Column, String, Integer, DateTime, Boolean, Float, Text, JSON, ForeignKey, Index, Table
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

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
    document_metadata = Column(JSONB, default={})
    upload_date = Column(DateTime(timezone=True), server_default=func.now())
    processed_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Version tracking
    current_version_number = Column(Integer, default=0)
    total_versions = Column(Integer, default=0)

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
    result = Column(JSONB, default={})
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
    detected_layout = Column(JSONB, default={})  # Regions, tables, images
    bounding_boxes = Column(JSONB, default=[])   # Word/line bounding boxes
    page_number = Column(Integer)

    # German specific results
    detected_dates = Column(JSONB, default=[])
    detected_amounts = Column(JSONB, default=[])
    detected_ibans = Column(JSONB, default=[])
    detected_vat_ids = Column(JSONB, default=[])
    business_terms = Column(JSONB, default=[])

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
    detected_dates = Column(JSONB, default=[])
    detected_amounts = Column(JSONB, default=[])
    detected_ibans = Column(JSONB, default=[])
    detected_vat_ids = Column(JSONB, default=[])
    business_terms = Column(JSONB, default=[])

    # Layout data
    detected_layout = Column(JSONB, default={})
    bounding_boxes = Column(JSONB, default=[])

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
    permissions = Column(JSONB, default=[])
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
    audit_metadata = Column(JSONB, default={})
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
    metric_metadata = Column(JSONB, default={})
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("ix_system_metrics_timestamp", "timestamp"),
        Index("ix_system_metrics_type", "metric_type"),
    )
