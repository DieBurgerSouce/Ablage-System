"""
Database Models - SQLAlchemy ORM
Enterprise-grade PostgreSQL schema for document management
Priority: P0 - CRITICAL
Created: 2024-11-22
"""
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
import uuid
import enum


# Helper function for timezone-aware datetime (Python 3.12+ compatible)
def utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

Base = declarative_base()


# ============================================================================
# ENUMS
# ============================================================================

class DocumentType(str, enum.Enum):
    """Supported document types"""
    INVOICE = "invoice"
    DELIVERY_NOTE = "delivery_note"
    CONTRACT = "contract"
    RECEIPT = "receipt"
    LETTER = "letter"
    OTHER = "other"


class ProcessingStatus(str, enum.Enum):
    """Document processing status"""
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class OCRBackend(str, enum.Enum):
    """Available OCR backends"""
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    SURYA = "surya"
    AUTO = "auto"


class UserRole(str, enum.Enum):
    """User authorization roles"""
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"
    API_USER = "api_user"


# ============================================================================
# USER MANAGEMENT
# ============================================================================

class User(Base):
    """User accounts with GDPR compliance"""
    __tablename__ = "users"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)  # bcrypt

    # Profile
    full_name = Column(String(255))
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)

    # Settings
    preferred_language = Column(String(2), default="de")
    display_mode = Column(String(20), default="dark")  # dark/light/whitescreen/blackscreen

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    last_login = Column(DateTime)

    # GDPR
    gdpr_consent = Column(Boolean, default=False, nullable=False)
    gdpr_consent_date = Column(DateTime)
    deletion_requested_at = Column(DateTime)  # Soft delete with 30-day grace period

    # Relationships
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username} ({self.email})>"


class APIKey(Base):
    """API keys for programmatic access"""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Key data
    key_hash = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Permissions
    scopes = Column(ARRAY(String), default=["documents:read"])  # ["documents:read", "documents:write", ...]

    # Rate limiting
    rate_limit_per_minute = Column(Integer, default=100)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime)
    last_used_at = Column(DateTime)

    # Timestamps
    created_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="api_keys")

    def __repr__(self):
        return f"<APIKey {self.name} ({self.user_id})>"


# ============================================================================
# DOCUMENT MANAGEMENT
# ============================================================================

class Document(Base):
    """Main document entity with full metadata"""
    __tablename__ = "documents"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Ownership
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # File metadata
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    content_type = Column(String(100), nullable=False)
    file_hash_sha256 = Column(String(64), index=True)  # For deduplication

    # Storage
    storage_path = Column(String(500), nullable=False)  # MinIO object key
    storage_bucket = Column(String(100), default="documents")
    thumbnail_path = Column(String(500))  # MinIO thumbnail key

    # Classification
    document_type = Column(SQLEnum(DocumentType), default=DocumentType.OTHER, nullable=False, index=True)
    language = Column(String(2), default="de")
    page_count = Column(Integer, default=1)

    # Processing status
    status = Column(SQLEnum(ProcessingStatus), default=ProcessingStatus.UPLOADED, nullable=False, index=True)
    processing_started_at = Column(DateTime)
    processing_completed_at = Column(DateTime)
    processing_duration_seconds = Column(Float)

    # OCR results
    ocr_backend_used = Column(SQLEnum(OCRBackend))
    ocr_confidence_avg = Column(Float)  # 0.0 - 1.0
    extracted_text = Column(Text)

    # Structured data extraction
    extracted_data = Column(JSONB)  # Template-based extraction results

    # German text processing
    contains_umlauts = Column(Boolean, default=False)
    contains_fraktur = Column(Boolean, default=False)
    normalized_text = Column(Text)  # After German text normalization

    # Search
    search_vector = Column(Text)  # PostgreSQL tsvector for full-text search (stored as text for now)

    # Metadata
    tags = Column(ARRAY(String), default=[])
    metadata = Column(JSONB, default={})  # Additional custom metadata

    # Timestamps
    created_at = Column(DateTime, default=utc_now, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    # GDPR
    contains_personal_data = Column(Boolean, default=False)
    gdpr_retention_until = Column(DateTime)  # Auto-delete after this date

    # Relationships
    owner = relationship("User", back_populates="documents")
    processing_logs = relationship("ProcessingLog", back_populates="document", cascade="all, delete-orphan")
    validations = relationship("ValidationResult", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Document {self.original_filename} ({self.document_type.value})>"


# ============================================================================
# PROCESSING & LOGGING
# ============================================================================

class ProcessingLog(Base):
    """Detailed processing logs for audit trail"""
    __tablename__ = "processing_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Processing details
    step_name = Column(String(100), nullable=False)  # "upload", "ocr", "normalization", etc.
    backend_used = Column(String(50))
    started_at = Column(DateTime, default=utc_now, nullable=False, index=True)  # Added index for performance
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)

    # Status
    success = Column(Boolean, nullable=False)
    error_message = Column(Text)  # TODO: Sanitize to remove PII before storing
    error_stacktrace = Column(Text)  # WARNING: May contain sensitive paths/data!

    # GPU metrics (if applicable)
    gpu_memory_used_mb = Column(Float)
    gpu_utilization_percent = Column(Float)

    # Results
    output_data = Column(JSONB)  # Step-specific output

    # Relationships
    document = relationship("Document", back_populates="processing_logs")

    def __repr__(self):
        return f"<ProcessingLog {self.step_name} for {self.document_id}>"


class ValidationResult(Base):
    """Validation results for extracted data"""
    __tablename__ = "validation_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Validation type
    validator_name = Column(String(100), nullable=False)  # "german_text", "invoice_ustg", "math_validation"

    # Results
    is_valid = Column(Boolean, nullable=False)
    confidence_score = Column(Float)  # 0.0 - 1.0

    # Details
    validation_errors = Column(JSONB, default=[])  # List of errors found
    validation_warnings = Column(JSONB, default=[])  # List of warnings
    validation_details = Column(JSONB)  # Additional validator-specific data

    # Timestamp
    validated_at = Column(DateTime, default=utc_now, nullable=False)

    # Relationships
    document = relationship("Document", back_populates="validations")

    def __repr__(self):
        return f"<ValidationResult {self.validator_name} for {self.document_id}>"


# ============================================================================
# AUDIT & COMPLIANCE
# ============================================================================

class AuditLog(Base):
    """GDPR Art. 30 compliant audit trail"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Who
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    ip_address = Column(String(45))  # IPv6 compatible
    user_agent = Column(String(500))

    # What
    action = Column(String(100), nullable=False, index=True)  # "document_upload", "document_view", "data_export", etc.
    resource_type = Column(String(50))  # "document", "user", "api_key"
    resource_id = Column(UUID(as_uuid=True), index=True)

    # Details
    action_details = Column(JSONB)  # WARNING: Ensure PII is scrubbed before storing!
    success = Column(Boolean, nullable=False)
    error_message = Column(Text)  # WARNING: May contain sensitive data!

    # When
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)

    # GDPR
    contains_personal_data = Column(Boolean, default=False)
    legal_basis = Column(String(100))  # "consent", "contract", "legal_obligation"

    # Relationships
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog {self.action} by {self.user_id} at {self.timestamp}>"


class GDPRDataExport(Base):
    """Track GDPR data export requests (Art. 15)"""
    __tablename__ = "gdpr_data_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Request
    requested_at = Column(DateTime, default=utc_now, nullable=False)
    request_ip = Column(String(45))

    # Processing
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    started_processing_at = Column(DateTime)
    completed_at = Column(DateTime)

    # Export data
    export_file_path = Column(String(500))  # MinIO path to ZIP file
    file_size_bytes = Column(Integer)
    expires_at = Column(DateTime)  # Auto-delete after 30 days

    # Access
    downloaded_at = Column(DateTime)
    download_count = Column(Integer, default=0)

    def __repr__(self):
        return f"<GDPRDataExport for {self.user_id} ({self.status})>"


# ============================================================================
# SYSTEM METRICS
# ============================================================================

class SystemMetric(Base):
    """System performance and usage metrics"""
    __tablename__ = "system_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Metric type
    metric_name = Column(String(100), nullable=False, index=True)  # "gpu_memory_usage", "document_processing_time", etc.
    metric_category = Column(String(50), index=True)  # "gpu", "api", "storage", "database"

    # Value
    value = Column(Float, nullable=False)
    unit = Column(String(20))  # "GB", "seconds", "percent", "count"

    # Context
    tags = Column(JSONB, default={})  # {"backend": "deepseek", "document_type": "invoice"}

    # Timestamp
    timestamp = Column(DateTime, default=utc_now, nullable=False, index=True)

    def __repr__(self):
        return f"<SystemMetric {self.metric_name}={self.value}{self.unit}>"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def init_db(engine):
    """Initialize database schema"""
    Base.metadata.create_all(engine)
    print("[OK] Database schema initialized")


def drop_all(engine):
    """Drop all tables (DANGEROUS!)"""
    Base.metadata.drop_all(engine)
    print("[!] All tables dropped")
