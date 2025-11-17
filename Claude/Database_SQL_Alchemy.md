🐍 SQLALCHEMY ORM MODELS - COMPLETE IMPLEMENTATION
Python ORM Layer für das gesamte Database Schema

📁 PROJEKT-STRUKTUR
/backend/
├── models/
│   ├── __init__.py              # Exports all models
│   ├── base.py                  # Base classes & Mixins
│   ├── enums.py                 # All enum types
│   ├── auth.py                  # User, Role, Permission, etc.
│   ├── documents.py             # Document-related models
│   ├── suppliers.py             # Supplier models
│   ├── workflows.py             # Workflow automation
│   ├── extraction.py            # ML/AI & Extraction
│   ├── notifications.py         # Notifications & Email
│   ├── integrations.py          # Webhooks, Integrations
│   ├── monitoring.py            # Metrics, Logs, Errors
│   └── config.py                # System settings
│
├── database.py                  # Database connection & session
└── utils/
    ├── security.py              # Password hashing, etc.
    └── validators.py            # Custom validators

🔧 BASE SETUP
/backend/database.py
python"""
Database connection and session management
"""

from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool
import os

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@localhost:5432/ocr_system"
)

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,  # Verify connections before using
    pool_recycle=3600,   # Recycle connections after 1 hour
    echo=False,          # Set to True for SQL logging
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
)

# Base class for all models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database sessions.
    Use with FastAPI Depends.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database (create all tables).
    Only use in development!
    """
    Base.metadata.create_all(bind=engine)


# Enable PostgreSQL extensions
@event.listens_for(engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    """Enable required PostgreSQL extensions on connection"""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\";")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"pg_trgm\";")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"btree_gin\";")
        cursor.execute("CREATE EXTENSION IF NOT EXISTS \"hstore\";")
        dbapi_connection.commit()
    except Exception as e:
        print(f"Error enabling extensions: {e}")
    finally:
        cursor.close()

/backend/models/enums.py
python"""
All enum types used in the database
"""

import enum


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackendType(str, enum.Enum):
    DEEPSEEK = "deepseek"
    GOT_OCR = "got_ocr"
    CPU_SURYA = "cpu_surya"


class DocumentType(str, enum.Enum):
    INVOICE = "invoice"
    CONTRACT = "contract"
    DELIVERY_NOTE = "delivery_note"
    ORDER = "order"
    RECEIPT = "receipt"
    LETTER = "letter"
    FORM = "form"
    UNKNOWN = "unknown"


class ComplexityLevel(str, enum.Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ConfidenceLevel(str, enum.Enum):
    HIGH = "high"        # >95%
    MEDIUM = "medium"    # 80-95%
    LOW = "low"          # 60-80%
    VERY_LOW = "very_low"  # <60%


class RelationType(str, enum.Enum):
    CORRECTS = "corrects"
    REPLACES = "replaces"
    REFERENCES = "references"
    ATTACHMENT_TO = "attachment_to"
    DELIVERY_FOR = "delivery_for"
    ORDER_FOR = "order_for"
    CREDIT_NOTE_FOR = "credit_note_for"
    REMINDER_FOR = "reminder_for"
    DUPLICATE_OF = "duplicate_of"


class WorkflowTrigger(str, enum.Enum):
    MANUAL = "manual"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_PROCESSED = "document_processed"
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
    SUPPLIER_DETECTED = "supplier_detected"
    SCHEDULE = "schedule"
    WEBHOOK = "webhook"


class StepType(str, enum.Enum):
    CLASSIFY_DOCUMENT = "classify_document"
    EXTRACT_DATA = "extract_data"
    VALIDATE_DATA = "validate_data"
    SEND_NOTIFICATION = "send_notification"
    SEND_EMAIL = "send_email"
    CALL_WEBHOOK = "call_webhook"
    UPDATE_FIELD = "update_field"
    ASSIGN_USER = "assign_user"
    CREATE_RELATION = "create_relation"
    EXPORT_DOCUMENT = "export_document"
    CONDITIONAL = "conditional"
    WAIT = "wait"


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class RuleType(str, enum.Enum):
    REGEX = "regex"
    POSITION = "position"
    TEMPLATE = "template"
    ML_MODEL = "ml_model"


class NotificationType(str, enum.Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    DOCUMENT_PROCESSED = "document_processed"
    REVIEW_NEEDED = "review_needed"
    WORKFLOW_COMPLETED = "workflow_completed"
    SYSTEM_ALERT = "system_alert"


class NotificationChannel(str, enum.Enum):
    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"
    SMS = "sms"


class EmailStatus(str, enum.Enum):
    QUEUED = "queued"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    BOUNCED = "bounced"


class WebhookEvent(str, enum.Enum):
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_PROCESSED = "document.processed"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_DELETED = "document.deleted"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"


class ExportFormat(str, enum.Enum):
    PDF = "pdf"
    JSON = "json"
    XML = "xml"
    CSV = "csv"
    EXCEL = "excel"
    ZIP = "zip"


class IntegrationType(str, enum.Enum):
    ACCOUNTING = "accounting"
    ERP = "erp"
    STORAGE = "storage"
    EMAIL = "email"
    CUSTOM = "custom"


class ErrorSeverity(str, enum.Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TaskFrequency(str, enum.Enum):
    MINUTELY = "minutely"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"

/backend/models/base.py
python"""
Base model classes and mixins
"""

from datetime import datetime
from typing import Any, Dict
from sqlalchemy import Column, DateTime, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr
import uuid


class TimestampMixin:
    """Adds created_at and updated_at timestamps"""
    
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now()
    )


class SoftDeleteMixin:
    """Adds soft delete functionality"""
    
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
    
    def soft_delete(self):
        """Mark record as deleted"""
        self.deleted_at = datetime.utcnow()
    
    def restore(self):
        """Restore soft-deleted record"""
        self.deleted_at = None


class UUIDMixin:
    """Adds UUID primary key"""
    
    @declared_attr
    def id(cls):
        return Column(
            UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
            nullable=False
        )


class BaseModel(UUIDMixin, TimestampMixin):
    """
    Base model with UUID primary key and timestamps.
    All models should inherit from this.
    """
    
    __abstract__ = True
    
    def to_dict(self, exclude: set = None) -> Dict[str, Any]:
        """
        Convert model to dictionary.
        
        Args:
            exclude: Set of field names to exclude
        """
        exclude = exclude or set()
        result = {}
        
        for column in self.__table__.columns:
            if column.name not in exclude:
                value = getattr(self, column.name)
                
                # Convert UUID to string
                if isinstance(value, uuid.UUID):
                    value = str(value)
                # Convert datetime to ISO format
                elif isinstance(value, datetime):
                    value = value.isoformat()
                # Convert enum to value
                elif hasattr(value, 'value'):
                    value = value.value
                
                result[column.name] = value
        
        return result
    
    def update_from_dict(self, data: Dict[str, Any], exclude: set = None):
        """
        Update model from dictionary.
        
        Args:
            data: Dictionary with field values
            exclude: Set of field names to exclude
        """
        exclude = exclude or {'id', 'created_at', 'updated_at'}
        
        for key, value in data.items():
            if key not in exclude and hasattr(self, key):
                setattr(self, key, value)
    
    def __repr__(self) -> str:
        """String representation"""
        return f"<{self.__class__.__name__}(id={self.id})>"

/backend/utils/security.py
python"""
Security utilities for password hashing, etc.
"""

from passlib.context import CryptContext
import secrets
import hashlib

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate API key.
    
    Returns:
        tuple: (full_key, key_hash, key_prefix)
    """
    # Generate random key
    key = secrets.token_urlsafe(32)
    
    # Hash for storage
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    # Prefix for identification
    key_prefix = key[:8]
    
    return key, key_hash, key_prefix


def generate_session_token() -> str:
    """Generate secure session token"""
    return secrets.token_urlsafe(64)


def hash_file(file_path: str) -> str:
    """Generate SHA-256 hash of a file"""
    sha256_hash = hashlib.sha256()
    
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    
    return sha256_hash.hexdigest()

👥 AUTH MODELS
/backend/models/auth.py
python"""
Authentication and authorization models
"""

from sqlalchemy import (
    Column, String, Boolean, Integer, Text, ForeignKey,
    Table, DateTime, ARRAY, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from .base import BaseModel, SoftDeleteMixin
from ..utils.security import hash_password, verify_password
from datetime import datetime, timedelta
import uuid


# Association tables for many-to-many relationships
user_roles = Table(
    'user_roles',
    BaseModel.metadata,
    Column('user_id', UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('assigned_at', DateTime(timezone=True), server_default='now()'),
    Column('assigned_by', UUID(as_uuid=True), ForeignKey('users.id')),
    Column('expires_at', DateTime(timezone=True))
)

role_permissions = Table(
    'role_permissions',
    BaseModel.metadata,
    Column('role_id', UUID(as_uuid=True), ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    Column('permission_id', UUID(as_uuid=True), ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True),
    Column('granted_at', DateTime(timezone=True), server_default='now()')
)


class User(BaseModel, SoftDeleteMixin):
    """User model for authentication"""
    
    __tablename__ = 'users'
    
    # Authentication
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    username = Column(String(100), unique=True, index=True)
    
    # Profile
    first_name = Column(String(100))
    last_name = Column(String(100))
    display_name = Column(String(200))
    avatar_url = Column(Text)
    
    # Contact
    phone = Column(String(50))
    department = Column(String(100))
    job_title = Column(String(100))
    
    # Settings
    language = Column(String(10), default='de')
    timezone = Column(String(50), default='Europe/Berlin')
    preferences = Column(JSONB, default={})
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    email_verified_at = Column(DateTime(timezone=True))
    
    # Security
    two_factor_enabled = Column(Boolean, default=False, nullable=False)
    two_factor_secret = Column(String(100))
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    last_login_ip = Column(INET)
    
    # Relationships
    roles = relationship(
        'Role',
        secondary=user_roles,
        back_populates='users',
        lazy='selectin'
    )
    
    api_keys = relationship('APIKey', back_populates='user', cascade='all, delete-orphan')
    sessions = relationship('Session', back_populates='user', cascade='all, delete-orphan')
    notifications = relationship('Notification', back_populates='user', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        CheckConstraint(
            "email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$'",
            name='valid_email'
        ),
    )
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.password_hash = hash_password(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify password"""
        return verify_password(password, self.password_hash)
    
    def is_locked(self) -> bool:
        """Check if account is locked"""
        if self.locked_until:
            return datetime.utcnow() < self.locked_until
        return False
    
    def lock_account(self, duration_minutes: int = 30):
        """Lock account for specified duration"""
        self.locked_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
    
    def unlock_account(self):
        """Unlock account"""
        self.locked_until = None
        self.failed_login_attempts = 0
    
    def has_permission(self, permission_name: str) -> bool:
        """Check if user has specific permission"""
        for role in self.roles:
            if any(p.name == permission_name for p in role.permissions):
                return True
        return False
    
    def has_role(self, role_name: str) -> bool:
        """Check if user has specific role"""
        return any(r.name == role_name for r in self.roles)
    
    @property
    def full_name(self) -> str:
        """Get full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.display_name or self.username or self.email


class Role(BaseModel):
    """Role model for authorization"""
    
    __tablename__ = 'roles'
    
    name = Column(String(50), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # Hierarchy
    level = Column(Integer, nullable=False, default=0)
    
    # System roles can't be deleted
    is_system = Column(Boolean, default=False, nullable=False)
    
    # Relationships
    users = relationship(
        'User',
        secondary=user_roles,
        back_populates='roles'
    )
    
    permissions = relationship(
        'Permission',
        secondary=role_permissions,
        back_populates='roles',
        lazy='selectin'
    )


class Permission(BaseModel):
    """Permission model for fine-grained access control"""
    
    __tablename__ = 'permissions'
    
    name = Column(String(100), nullable=False, unique=True, index=True)
    resource = Column(String(50), nullable=False, index=True)
    action = Column(String(50), nullable=False)
    description = Column(Text)
    
    # Relationships
    roles = relationship(
        'Role',
        secondary=role_permissions,
        back_populates='permissions'
    )


class APIKey(BaseModel):
    """API Key model for programmatic access"""
    
    __tablename__ = 'api_keys'
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    
    # Key
    key_hash = Column(String(255), nullable=False, unique=True)
    key_prefix = Column(String(10), nullable=False)
    
    # Metadata
    name = Column(String(100), nullable=False)
    description = Column(Text)
    
    # Permissions
    allowed_ips = Column(ARRAY(INET))
    rate_limit = Column(Integer, default=1000)  # Requests per hour
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True))
    
    # Usage tracking
    last_used_at = Column(DateTime(timezone=True))
    total_requests = Column(Integer, default=0, nullable=False)
    
    revoked_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship('User', back_populates='api_keys')
    
    def is_valid(self) -> bool:
        """Check if API key is valid"""
        if not self.is_active or self.revoked_at:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True
    
    def revoke(self):
        """Revoke API key"""
        self.is_active = False
        self.revoked_at = datetime.utcnow()


class Session(BaseModel):
    """User session model"""
    
    __tablename__ = 'sessions'
    
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Session data
    session_token = Column(String(255), nullable=False, unique=True, index=True)
    refresh_token = Column(String(255), unique=True)
    
    # Client info
    ip_address = Column(INET)
    user_agent = Column(Text)
    device_info = Column(JSONB)
    
    # Timing
    last_activity_at = Column(DateTime(timezone=True), server_default='now()')
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Security
    is_valid = Column(Boolean, default=True, nullable=False)
    
    # Relationships
    user = relationship('User', back_populates='sessions')
    
    def is_expired(self) -> bool:
        """Check if session is expired"""
        return datetime.utcnow() > self.expires_at
    
    def invalidate(self):
        """Invalidate session"""
        self.is_valid = False
    
    def refresh(self, duration_hours: int = 24):
        """Refresh session expiry"""
        self.expires_at = datetime.utcnow() + timedelta(hours=duration_hours)
        self.last_activity_at = datetime.utcnow()

📄 DOCUMENT MODELS
/backend/models/documents.py
python"""
Document management models
"""

from sqlalchemy import (
    Column, String, Integer, Boolean, Text, ForeignKey,
    BigInteger, Date, DECIMAL, CheckConstraint, Table
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from .base import BaseModel, SoftDeleteMixin
from .enums import (
    DocumentStatus, DocumentType, ComplexityLevel, 
    ConfidenceLevel, RelationType, JobStatus, BackendType
)


# Association table for document tags
document_tags = Table(
    'document_tags',
    BaseModel.metadata,
    Column('document_id', UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True),
    Column('tag_id', UUID(as_uuid=True), ForeignKey('tags.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', Column(DateTime(timezone=True), server_default='now()')),
    Column('added_by', UUID(as_uuid=True), ForeignKey('users.id'))
)


class Document(BaseModel, SoftDeleteMixin):
    """Main document model"""
    
    __tablename__ = 'documents'
    
    # Document Identity
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA-256
    
    # Storage
    storage_path = Column(Text, nullable=False)
    storage_bucket = Column(String(100), default='original-documents')
    thumbnail_path = Column(Text)
    
    # Classification
    document_type = Column(String, default=DocumentType.UNKNOWN.value)
    document_subtype = Column(String(100))
    complexity = Column(String)
    language_code = Column(String(10), default='de')
    
    # Document Metadata
    page_count = Column(Integer, default=1, nullable=False)
    detected_supplier_id = Column(UUID(as_uuid=True), ForeignKey('suppliers.id'))
    document_date = Column(Date)
    document_number = Column(String(100))
    
    # Category
    category_id = Column(UUID(as_uuid=True), ForeignKey('categories.id'))
    
    # Status & Processing
    status = Column(String, default=DocumentStatus.UPLOADED.value, index=True)
    current_job_id = Column(UUID(as_uuid=True), ForeignKey('processing_jobs.id'))
    
    # Confidence & Quality
    overall_confidence = Column(DECIMAL(5, 2))
    confidence_level = Column(String)
    needs_review = Column(Boolean, default=False, index=True)
    review_notes = Column(Text)
    
    # Business Context
    source = Column(String(100))  # 'email', 'upload', 'api', 'scanner'
    source_reference = Column(String(255))
    assigned_to = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    project_id = Column(UUID(as_uuid=True))
    
    # Extracted Data
    extracted_data = Column(JSONB)  # Quick access fields
    full_ocr_result = Column(JSONB)  # Complete OCR output
    
    # Foreign Keys
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    supplier = relationship('Supplier', back_populates='documents')
    category = relationship('Category', back_populates='documents')
    assigned_user = relationship('User', foreign_keys=[assigned_to])
    created_by_user = relationship('User', foreign_keys=[created_by])
    
    processing_jobs = relationship('ProcessingJob', back_populates='document', foreign_keys='ProcessingJob.document_id')
    current_job = relationship('ProcessingJob', foreign_keys=[current_job_id])
    
    pages = relationship('DocumentPage', back_populates='document', cascade='all, delete-orphan')
    versions = relationship('DocumentVersion', back_populates='document', cascade='all, delete-orphan')
    
    tags = relationship('Tag', secondary=document_tags, back_populates='documents')
    
    # Relations as source
    relations_as_source = relationship(
        'DocumentRelation',
        foreign_keys='DocumentRelation.source_document_id',
        back_populates='source_document',
        cascade='all, delete-orphan'
    )
    
    # Relations as target
    relations_as_target = relationship(
        'DocumentRelation',
        foreign_keys='DocumentRelation.target_document_id',
        back_populates='target_document',
        cascade='all, delete-orphan'
    )
    
    notifications = relationship('Notification', back_populates='document')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('overall_confidence BETWEEN 0 AND 100', name='valid_confidence'),
        CheckConstraint('page_count > 0', name='valid_pages'),
        CheckConstraint('file_size > 0', name='valid_file_size'),
    )
    
    def get_confidence_level(self) -> ConfidenceLevel:
        """Calculate confidence level from percentage"""
        if not self.overall_confidence:
            return ConfidenceLevel.VERY_LOW
        
        conf = float(self.overall_confidence)
        if conf >= 95:
            return ConfidenceLevel.HIGH
        elif conf >= 80:
            return ConfidenceLevel.MEDIUM
        elif conf >= 60:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.VERY_LOW


class ProcessingJob(BaseModel):
    """Processing job tracking"""
    
    __tablename__ = 'processing_jobs'
    
    # Relations
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    parent_job_id = Column(UUID(as_uuid=True), ForeignKey('processing_jobs.id'))
    
    # Job Configuration
    backend_type = Column(String, nullable=False, index=True)
    backend_version = Column(String(50))
    processing_options = Column(JSONB)
    
    # Status
    status = Column(String, default=JobStatus.PENDING.value, index=True)
    priority = Column(Integer, default=5, nullable=False)
    
    # Timing
    queued_at = Column(DateTime(timezone=True), server_default='now()', index=True)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    processing_time_ms = Column(Integer)
    
    # Results
    success = Column(Boolean)
    error_message = Column(Text)
    error_code = Column(String(50))
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    
    # Resource Usage
    vram_used_mb = Column(Integer)
    ram_used_mb = Column(Integer)
    cpu_cores_used = Column(Integer)
    
    # Foreign Keys
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    document = relationship('Document', back_populates='processing_jobs', foreign_keys=[document_id])
    parent_job = relationship('ProcessingJob', remote_side='ProcessingJob.id')
    events = relationship('JobEvent', back_populates='job', cascade='all, delete-orphan')
    ocr_result = relationship('OCRResult', back_populates='job', uselist=False, cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('priority BETWEEN 1 AND 10', name='valid_priority'),
        CheckConstraint('retry_count <= max_retries', name='valid_retry'),
    )


class JobEvent(BaseModel):
    """Job event log"""
    
    __tablename__ = 'job_events'
    
    job_id = Column(UUID(as_uuid=True), ForeignKey('processing_jobs.id', ondelete='CASCADE'), nullable=False, index=True)
    
    event_type = Column(String(50), nullable=False)
    event_message = Column(Text)
    event_data = Column(JSONB)
    
    # Relationships
    job = relationship('ProcessingJob', back_populates='events')


class OCRResult(BaseModel):
    """OCR results storage"""
    
    __tablename__ = 'ocr_results'
    
    # Relations
    job_id = Column(UUID(as_uuid=True), ForeignKey('processing_jobs.id', ondelete='CASCADE'), nullable=False, unique=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Raw Output
    raw_text = Column(Text)
    formatted_text = Column(Text)
    full_json = Column(JSONB)
    
    # Confidence Metrics
    overall_confidence = Column(DECIMAL(5, 2))
    avg_word_confidence = Column(DECIMAL(5, 2))
    min_word_confidence = Column(DECIMAL(5, 2))
    
    # Text Statistics
    total_characters = Column(Integer)
    total_words = Column(Integer)
    total_lines = Column(Integer)
    detected_language = Column(String(10))
    
    # Layout Information
    layout_blocks = Column(JSONB)
    bounding_boxes = Column(JSONB)
    reading_order = Column(JSONB)
    
    # Extracted Entities
    extracted_tables = Column(ARRAY(JSONB))
    extracted_fields = Column(JSONB)
    extracted_dates = Column(ARRAY(Date))
    extracted_amounts = Column(ARRAY(DECIMAL(15, 2)))
    
    # Quality Indicators
    has_low_confidence_words = Column(Boolean, default=False, nullable=False)
    low_confidence_word_count = Column(Integer, default=0, nullable=False)
    suspected_errors = Column(ARRAY(Text))
    
    # Processing Metadata
    processing_time_ms = Column(Integer)
    
    # Relationships
    job = relationship('ProcessingJob', back_populates='ocr_result')
    document = relationship('Document')


class DocumentPage(BaseModel):
    """Individual pages of multi-page documents"""
    
    __tablename__ = 'document_pages'
    
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    
    # Page info
    page_number = Column(Integer, nullable=False)
    
    # Storage
    image_path = Column(Text, nullable=False)
    thumbnail_path = Column(Text)
    
    # OCR per page
    ocr_text = Column(Text)
    ocr_confidence = Column(DECIMAL(5, 2))
    ocr_data = Column(JSONB)
    
    # Dimensions
    width_px = Column(Integer)
    height_px = Column(Integer)
    dpi = Column(Integer)
    
    # Processing
    processed_at = Column(DateTime(timezone=True))
    processing_time_ms = Column(Integer)
    
    # Relationships
    document = relationship('Document', back_populates='pages')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('page_number > 0', name='valid_page_number'),
    )


class DocumentVersion(BaseModel):
    """Document version history"""
    
    __tablename__ = 'document_versions'
    
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    
    version_number = Column(Integer, nullable=False)
    change_type = Column(String(50), nullable=False)
    
    # Snapshot
    data_snapshot = Column(JSONB, nullable=False)
    
    # Changes
    changed_fields = Column(ARRAY(Text))
    change_description = Column(Text)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    document = relationship('Document', back_populates='versions')


class DocumentRelation(BaseModel):
    """Relations between documents"""
    
    __tablename__ = 'document_relations'
    
    source_document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    target_document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id', ondelete='CASCADE'), nullable=False)
    
    relation_type = Column(String, nullable=False, index=True)
    
    # Metadata
    confidence = Column(DECIMAL(5, 2))
    notes = Column(Text)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    source_document = relationship('Document', foreign_keys=[source_document_id], back_populates='relations_as_source')
    target_document = relationship('Document', foreign_keys=[target_document_id], back_populates='relations_as_target')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('source_document_id != target_document_id', name='no_self_relation'),
    )


class Category(BaseModel):
    """Hierarchical document categories"""
    
    __tablename__ = 'categories'
    
    parent_id = Column(UUID(as_uuid=True), ForeignKey('categories.id', ondelete='CASCADE'))
    
    name = Column(String(100), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    
    # Path for hierarchical queries
    path = Column(Text, nullable=False, unique=True)
    
    # UI
    icon = Column(String(50))
    color = Column(String(7))
    
    # Ordering
    sort_order = Column(Integer, default=0, nullable=False)
    
    # Relationships
    parent = relationship('Category', remote_side='Category.id', backref='children')
    documents = relationship('Document', back_populates='category')


class Tag(BaseModel):
    """Flexible tagging system"""
    
    __tablename__ = 'tags'
    
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7))
    description = Column(Text)
    
    # Relationships
    documents = relationship('Document', secondary=document_tags, back_populates='tags')
    
    
    🏢 SUPPLIER MODELS
/backend/models/suppliers.py
python"""
Supplier/Vendor management models
"""

from sqlalchemy import (
    Column, String, Boolean, Text, ForeignKey,
    Integer, DECIMAL, Date, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from .base import BaseModel, SoftDeleteMixin
from .enums import DocumentType


class Supplier(BaseModel, SoftDeleteMixin):
    """
    Supplier/Vendor master data.
    Stores information about companies that send documents.
    """
    
    __tablename__ = 'suppliers'
    
    # Identity
    name = Column(String(255), nullable=False, index=True)
    legal_name = Column(String(255))  # Official registered company name
    supplier_number = Column(String(50), unique=True, index=True)
    
    # Contact
    email = Column(String(255))
    phone = Column(String(50))
    website = Column(String(255))
    
    # Address
    street = Column(String(255))
    postal_code = Column(String(20))
    city = Column(String(100))
    country = Column(String(2), default='DE')  # ISO 3166-1 alpha-2
    
    # Tax & Legal
    tax_id = Column(String(50))  # Steuernummer
    vat_id = Column(String(50))  # USt-IdNr
    commercial_register = Column(String(100))  # Handelsregister
    
    # Classification
    industry = Column(String(100))
    tags = Column(ARRAY(Text))
    
    # Document Recognition
    name_variations = Column(ARRAY(Text))  # Alternative names for fuzzy matching
    logo_hash = Column(String(64))  # SHA-256 of logo for visual recognition
    typical_sender_emails = Column(ARRAY(Text))  # Email addresses commonly used
    
    # Statistics (updated by triggers)
    total_documents = Column(Integer, default=0, nullable=False)
    first_document_date = Column(Date)
    last_document_date = Column(Date)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    notes = Column(Text)
    
    # Relationships
    documents = relationship('Document', back_populates='supplier')
    contacts = relationship('SupplierContact', back_populates='supplier', cascade='all, delete-orphan')
    templates = relationship('SupplierTemplate', back_populates='supplier', cascade='all, delete-orphan')
    extraction_rules = relationship('ExtractionRule', back_populates='supplier', cascade='all, delete-orphan')
    
    def __repr__(self) -> str:
        return f"<Supplier(id={self.id}, name='{self.name}')>"
    
    @property
    def full_address(self) -> str:
        """Get formatted address"""
        parts = [
            self.street,
            f"{self.postal_code} {self.city}" if self.postal_code and self.city else None,
            self.country
        ]
        return ", ".join(filter(None, parts))
    
    def add_name_variation(self, variation: str):
        """Add a name variation for better matching"""
        if not self.name_variations:
            self.name_variations = []
        if variation not in self.name_variations:
            self.name_variations.append(variation)
    
    def add_sender_email(self, email: str):
        """Add a typical sender email"""
        if not self.typical_sender_emails:
            self.typical_sender_emails = []
        if email not in self.typical_sender_emails:
            self.typical_sender_emails.append(email)


class SupplierContact(BaseModel):
    """
    Contact persons at supplier companies.
    Useful for follow-ups, questions, etc.
    """
    
    __tablename__ = 'supplier_contacts'
    
    supplier_id = Column(
        UUID(as_uuid=True),
        ForeignKey('suppliers.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Contact Information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    job_title = Column(String(100))
    department = Column(String(100))
    
    # Contact Details
    email = Column(String(255))
    phone = Column(String(50))
    mobile = Column(String(50))
    
    # Status
    is_primary = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Notes
    notes = Column(Text)
    
    # Relationships
    supplier = relationship('Supplier', back_populates='contacts')
    
    @property
    def full_name(self) -> str:
        """Get full name"""
        return f"{self.first_name} {self.last_name}"
    
    def __repr__(self) -> str:
        return f"<SupplierContact(id={self.id}, name='{self.full_name}')>"


class SupplierTemplate(BaseModel):
    """
    Document layout templates for specific suppliers.
    Stores patterns and rules for extracting data from supplier documents.
    """
    
    __tablename__ = 'supplier_templates'
    
    supplier_id = Column(
        UUID(as_uuid=True),
        ForeignKey('suppliers.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Template Identity
    template_name = Column(String(255), nullable=False)
    document_type = Column(String, nullable=False, index=True)
    
    # Field Extraction Rules
    field_patterns = Column(JSONB, nullable=False)
    """
    JSON structure for field extraction rules:
    {
        "invoice_number": {
            "pattern": "Rechnung(?:snummer)?:?\\s*([A-Z0-9-]+)",
            "position": {"x": 450, "y": 100, "tolerance": 20},
            "validation": "^[A-Z]{2}[0-9]{6}$"
        },
        "total_amount": {
            "pattern": "Gesamt(?:betrag)?:?\\s*([0-9.,]+)\\s*€",
            "position": {"x": 450, "y": 600, "tolerance": 30},
            "data_type": "decimal"
        },
        "invoice_date": {
            "pattern": "Datum:?\\s*([0-9]{2}\\.[0-9]{2}\\.[0-9]{4})",
            "position": {"x": 450, "y": 150, "tolerance": 15},
            "data_type": "date",
            "format": "DD.MM.YYYY"
        }
    }
    """
    
    # Layout Information
    typical_layout = Column(JSONB)
    """
    Expected document structure:
    {
        "page_size": "A4",
        "sections": {
            "header": {"y_start": 0, "y_end": 200},
            "items": {"y_start": 200, "y_end": 700},
            "footer": {"y_start": 700, "y_end": 842}
        },
        "table_regions": [
            {"x": 50, "y": 300, "width": 500, "height": 400}
        ]
    }
    """
    
    confidence_threshold = Column(DECIMAL(5, 2), default=80.00, nullable=False)
    
    # Validation Rules
    validation_rules = Column(JSONB)
    """
    Business logic validation:
    {
        "total_must_equal_sum": true,
        "date_format": "DD.MM.YYYY",
        "required_fields": ["invoice_number", "total_amount", "invoice_date"],
        "custom_checks": [
            {
                "field": "total_amount",
                "condition": "greater_than",
                "value": 0
            }
        ]
    }
    """
    
    # Usage Statistics
    usage_count = Column(Integer, default=0, nullable=False)
    success_rate = Column(DECIMAL(5, 2))  # Percentage of successful extractions
    last_used_at = Column(DateTime(timezone=True))
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    supplier = relationship('Supplier', back_populates='templates')
    
    def __repr__(self) -> str:
        return f"<SupplierTemplate(id={self.id}, supplier_id={self.supplier_id}, type={self.document_type})>"
    
    def get_field_pattern(self, field_name: str) -> dict:
        """Get extraction pattern for a specific field"""
        return self.field_patterns.get(field_name, {})
    
    def add_field_pattern(self, field_name: str, pattern_config: dict):
        """Add or update a field extraction pattern"""
        if not self.field_patterns:
            self.field_patterns = {}
        self.field_patterns[field_name] = pattern_config
    
    def validate_extracted_data(self, data: dict) -> tuple[bool, list[str]]:
        """
        Validate extracted data against validation rules.
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []
        
        if not self.validation_rules:
            return True, []
        
        # Check required fields
        required_fields = self.validation_rules.get('required_fields', [])
        for field in required_fields:
            if field not in data or data[field] is None:
                errors.append(f"Required field missing: {field}")
        
        # Custom checks
        custom_checks = self.validation_rules.get('custom_checks', [])
        for check in custom_checks:
            field = check.get('field')
            condition = check.get('condition')
            value = check.get('value')
            
            if field in data:
                field_value = data[field]
                
                if condition == 'greater_than' and field_value <= value:
                    errors.append(f"{field} must be greater than {value}")
                elif condition == 'less_than' and field_value >= value:
                    errors.append(f"{field} must be less than {value}")
                elif condition == 'equals' and field_value != value:
                    errors.append(f"{field} must equal {value}")
        
        return len(errors) == 0, errors
    
    def increment_usage(self, success: bool):
        """Update usage statistics"""
        self.usage_count += 1
        
        if self.success_rate is None:
            self.success_rate = 100.0 if success else 0.0
        else:
            # Exponential moving average
            alpha = 0.1  # Smoothing factor
            new_value = 100.0 if success else 0.0
            self.success_rate = alpha * new_value + (1 - alpha) * float(self.success_rate)
        
        self.last_used_at = datetime.utcnow()

💡 USAGE EXAMPLES FÜR SUPPLIER MODELS
python"""
Examples of using the Supplier models
"""

from sqlalchemy.orm import Session
from models.suppliers import Supplier, SupplierContact, SupplierTemplate
from models.enums import DocumentType


# =============================================================================
# CREATING A SUPPLIER
# =============================================================================

def create_supplier_example(db: Session):
    """Create a new supplier with complete information"""
    
    supplier = Supplier(
        name="Mustermann GmbH",
        legal_name="Mustermann Handel GmbH",
        supplier_number="MUST-001",
        email="info@mustermann.de",
        phone="+49 123 456789",
        website="https://www.mustermann.de",
        street="Musterstraße 123",
        postal_code="42651",
        city="Solingen",
        country="DE",
        tax_id="123/456/78901",
        vat_id="DE123456789",
        commercial_register="HRB 12345",
        industry="Großhandel",
        tags=["Lieferant", "Premium"],
        name_variations=["Mustermann", "Mustermann Handel"],
        typical_sender_emails=["rechnung@mustermann.de", "buchhaltung@mustermann.de"],
        is_active=True
    )
    
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    
    print(f"Created supplier: {supplier.name} (ID: {supplier.id})")
    return supplier


# =============================================================================
# ADDING CONTACTS
# =============================================================================

def add_supplier_contacts(db: Session, supplier: Supplier):
    """Add contact persons to a supplier"""
    
    # Primary contact
    primary_contact = SupplierContact(
        supplier_id=supplier.id,
        first_name="Hans",
        last_name="Müller",
        job_title="Leiter Buchhaltung",
        department="Finance",
        email="h.mueller@mustermann.de",
        phone="+49 123 456789",
        mobile="+49 171 1234567",
        is_primary=True,
        is_active=True
    )
    
    # Secondary contact
    secondary_contact = SupplierContact(
        supplier_id=supplier.id,
        first_name="Anna",
        last_name="Schmidt",
        job_title="Sachbearbeiterin",
        department="Finance",
        email="a.schmidt@mustermann.de",
        phone="+49 123 456789",
        is_primary=False,
        is_active=True
    )
    
    db.add_all([primary_contact, secondary_contact])
    db.commit()
    
    print(f"Added {len(supplier.contacts)} contacts to {supplier.name}")


# =============================================================================
# CREATING EXTRACTION TEMPLATE
# =============================================================================

def create_invoice_template(db: Session, supplier: Supplier):
    """Create a template for extracting invoice data from this supplier"""
    
    template = SupplierTemplate(
        supplier_id=supplier.id,
        template_name="Standard Invoice Template",
        document_type=DocumentType.INVOICE.value,
        field_patterns={
            "invoice_number": {
                "pattern": r"Rechnung(?:snummer)?:?\s*([A-Z0-9-]+)",
                "position": {"x": 450, "y": 100, "tolerance": 20},
                "validation": r"^RE[0-9]{8}$"
            },
            "invoice_date": {
                "pattern": r"Datum:?\s*([0-9]{2}\.[0-9]{2}\.[0-9]{4})",
                "position": {"x": 450, "y": 150, "tolerance": 15},
                "data_type": "date",
                "format": "DD.MM.YYYY"
            },
            "total_amount": {
                "pattern": r"Gesamt(?:betrag)?:?\s*([0-9.,]+)\s*€",
                "position": {"x": 450, "y": 600, "tolerance": 30},
                "data_type": "decimal"
            },
            "net_amount": {
                "pattern": r"Netto(?:betrag)?:?\s*([0-9.,]+)\s*€",
                "data_type": "decimal"
            },
            "vat_amount": {
                "pattern": r"MwSt\.?:?\s*([0-9.,]+)\s*€",
                "data_type": "decimal"
            }
        },
        typical_layout={
            "page_size": "A4",
            "sections": {
                "header": {"y_start": 0, "y_end": 200},
                "items": {"y_start": 200, "y_end": 700},
                "footer": {"y_start": 700, "y_end": 842}
            },
            "logo_position": {"x": 50, "y": 50, "width": 150, "height": 80}
        },
        confidence_threshold=85.00,
        validation_rules={
            "required_fields": ["invoice_number", "invoice_date", "total_amount"],
            "date_format": "DD.MM.YYYY",
            "custom_checks": [
                {
                    "field": "total_amount",
                    "condition": "greater_than",
                    "value": 0
                },
                {
                    "field": "invoice_number",
                    "condition": "matches_pattern",
                    "value": "^RE[0-9]{8}$"
                }
            ]
        },
        is_active=True
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    print(f"Created template: {template.template_name}")
    return template


# =============================================================================
# FINDING SUPPLIERS
# =============================================================================

def find_supplier_by_name(db: Session, search_term: str):
    """Find supplier using fuzzy name matching"""
    
    # Using PostgreSQL's similarity function (requires pg_trgm extension)
    from sqlalchemy import func
    
    suppliers = db.query(Supplier).filter(
        Supplier.deleted_at.is_(None),
        Supplier.is_active == True,
        func.similarity(Supplier.name, search_term) > 0.3
    ).order_by(
        func.similarity(Supplier.name, search_term).desc()
    ).limit(10).all()
    
    return suppliers


def find_supplier_by_email(db: Session, email: str):
    """Find supplier by sender email"""
    
    suppliers = db.query(Supplier).filter(
        Supplier.deleted_at.is_(None),
        Supplier.typical_sender_emails.contains([email])
    ).all()
    
    return suppliers


# =============================================================================
# WORKING WITH TEMPLATES
# =============================================================================

def get_best_template_for_document(
    db: Session,
    supplier_id: UUID,
    document_type: DocumentType
):
    """Get the best template for a supplier and document type"""
    
    template = db.query(SupplierTemplate).filter(
        SupplierTemplate.supplier_id == supplier_id,
        SupplierTemplate.document_type == document_type.value,
        SupplierTemplate.is_active == True
    ).order_by(
        SupplierTemplate.success_rate.desc(),
        SupplierTemplate.usage_count.desc()
    ).first()
    
    return template


def validate_extraction_with_template(
    template: SupplierTemplate,
    extracted_data: dict
):
    """Validate extracted data using template rules"""
    
    is_valid, errors = template.validate_extracted_data(extracted_data)
    
    if is_valid:
        print("✅ Extraction is valid!")
        template.increment_usage(success=True)
    else:
        print("❌ Validation errors:")
        for error in errors:
            print(f"  - {error}")
        template.increment_usage(success=False)
    
    return is_valid, errors


# =============================================================================
# SUPPLIER STATISTICS
# =============================================================================

def get_supplier_statistics(db: Session, supplier: Supplier):
    """Get comprehensive statistics for a supplier"""
    
    from sqlalchemy import func
    from models.documents import Document
    
    stats = db.query(
        func.count(Document.id).label('total_docs'),
        func.avg(Document.overall_confidence).label('avg_confidence'),
        func.min(Document.document_date).label('first_doc'),
        func.max(Document.document_date).label('last_doc')
    ).filter(
        Document.detected_supplier_id == supplier.id,
        Document.deleted_at.is_(None)
    ).first()
    
    return {
        'supplier_name': supplier.name,
        'total_documents': stats.total_docs or 0,
        'average_confidence': float(stats.avg_confidence or 0),
        'first_document_date': stats.first_doc,
        'last_document_date': stats.last_doc,
        'active_templates': len([t for t in supplier.templates if t.is_active]),
        'contacts': len([c for c in supplier.contacts if c.is_active])
    }
    
    
 
 ⚙️ WORKFLOW MODELS
/backend/models/workflows.py
python"""
Workflow automation models for intelligent document processing
"""

from sqlalchemy import (
    Column, String, Boolean, Text, ForeignKey,
    Integer, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from .base import BaseModel, SoftDeleteMixin
from .enums import (
    WorkflowTrigger, StepType, ExecutionStatus
)


class Workflow(BaseModel, SoftDeleteMixin):
    """
    Workflow definition for automating document processing tasks.
    
    A workflow consists of multiple steps that are executed in sequence
    when triggered by specific events (e.g., document upload, OCR completion).
    """
    
    __tablename__ = 'workflows'
    
    # Identity
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Trigger Configuration
    trigger_type = Column(String, nullable=False, index=True)
    trigger_config = Column(JSONB)
    """
    Trigger configuration examples:
    
    document_uploaded:
    {
        "document_types": ["invoice", "contract"],
        "suppliers": ["supplier_id_1", "supplier_id_2"],
        "file_extensions": [".pdf", ".jpg"]
    }
    
    document_processed:
    {
        "document_types": ["invoice"],
        "min_confidence": 80
    }
    
    confidence_below_threshold:
    {
        "threshold": 80,
        "document_types": ["invoice"]
    }
    
    schedule:
    {
        "cron": "0 9 * * *",  # Daily at 9 AM
        "timezone": "Europe/Berlin"
    }
    """
    
    # Conditions (JSONLogic format)
    conditions = Column(JSONB)
    """
    JSONLogic conditions for workflow execution:
    {
        "and": [
            {"==": [{"var": "document.type"}, "invoice"]},
            {">": [{"var": "document.total_amount"}, 1000]},
            {"in": [{"var": "document.supplier_id"}, ["uuid1", "uuid2"]]}
        ]
    }
    """
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_system = Column(Boolean, default=False, nullable=False)
    
    # Statistics
    total_executions = Column(Integer, default=0, nullable=False)
    successful_executions = Column(Integer, default=0, nullable=False)
    failed_executions = Column(Integer, default=0, nullable=False)
    last_executed_at = Column(DateTime(timezone=True))
    
    # Foreign Keys
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    steps = relationship(
        'WorkflowStep',
        back_populates='workflow',
        cascade='all, delete-orphan',
        order_by='WorkflowStep.step_order'
    )
    executions = relationship(
        'WorkflowExecution',
        back_populates='workflow',
        cascade='all, delete-orphan'
    )
    
    def __repr__(self) -> str:
        return f"<Workflow(id={self.id}, name='{self.name}')>"
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_executions == 0:
            return 0.0
        return (self.successful_executions / self.total_executions) * 100
    
    def should_trigger(self, context: Dict[str, Any]) -> bool:
        """
        Check if workflow should be triggered based on conditions.
        
        Args:
            context: Dictionary with current context (document, event data, etc.)
        
        Returns:
            bool: True if workflow should execute
        """
        if not self.is_active:
            return False
        
        # If no conditions, always trigger
        if not self.conditions:
            return True
        
        # Evaluate JSONLogic conditions
        try:
            from json_logic import jsonLogic
            result = jsonLogic(self.conditions, context)
            return bool(result)
        except Exception as e:
            print(f"Error evaluating workflow conditions: {e}")
            return False
    
    def increment_stats(self, success: bool):
        """Update execution statistics"""
        self.total_executions += 1
        if success:
            self.successful_executions += 1
        else:
            self.failed_executions += 1
        self.last_executed_at = datetime.utcnow()


class WorkflowStep(BaseModel):
    """
    Individual step within a workflow.
    
    Steps are executed in order and can perform various actions
    like data extraction, validation, notifications, etc.
    """
    
    __tablename__ = 'workflow_steps'
    
    workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey('workflows.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Step Definition
    name = Column(String(255), nullable=False)
    step_type = Column(String, nullable=False, index=True)
    step_config = Column(JSONB, nullable=False)
    """
    Step configuration examples by type:
    
    classify_document:
    {
        "use_ml_model": true,
        "confidence_threshold": 0.8
    }
    
    extract_data:
    {
        "fields": ["invoice_number", "total_amount", "invoice_date"],
        "use_template": true,
        "template_id": "uuid"
    }
    
    validate_data:
    {
        "rules": {
            "invoice_number": {"required": true, "pattern": "^RE[0-9]+$"},
            "total_amount": {"required": true, "min": 0}
        }
    }
    
    send_notification:
    {
        "user_id": "uuid",
        "template": "document_processed",
        "channels": ["email", "in_app"]
    }
    
    send_email:
    {
        "to": "{{document.supplier.email}}",
        "template_id": "uuid",
        "subject": "Document processed: {{document.filename}}"
    }
    
    call_webhook:
    {
        "webhook_id": "uuid",
        "method": "POST",
        "payload": {
            "document_id": "{{document.id}}",
            "status": "{{document.status}}"
        }
    }
    
    update_field:
    {
        "field": "status",
        "value": "reviewed"
    }
    
    assign_user:
    {
        "user_id": "uuid",
        "role": "reviewer"
    }
    
    conditional:
    {
        "condition": {">=": [{"var": "confidence"}, 95]},
        "true_step": 5,  # Step to jump to if true
        "false_step": 6  # Step to jump to if false
    }
    
    wait:
    {
        "duration_seconds": 300,
        "reason": "Waiting for user review"
    }
    """
    
    # Execution Order
    step_order = Column(Integer, nullable=False)
    
    # Conditions (execute step only if conditions met)
    conditions = Column(JSONB)
    
    # Error Handling
    on_error = Column(String(50), default='fail', nullable=False)  # 'fail', 'continue', 'retry'
    max_retries = Column(Integer, default=0, nullable=False)
    retry_delay_seconds = Column(Integer, default=60, nullable=False)
    
    # Timeout
    timeout_seconds = Column(Integer, default=300, nullable=False)
    
    # Relationships
    workflow = relationship('Workflow', back_populates='steps')
    step_executions = relationship(
        'WorkflowStepExecution',
        back_populates='step',
        cascade='all, delete-orphan'
    )
    
    # Constraints
    __table_args__ = (
        CheckConstraint("on_error IN ('fail', 'continue', 'retry')", name='valid_error_handling'),
    )
    
    def __repr__(self) -> str:
        return f"<WorkflowStep(id={self.id}, name='{self.name}', order={self.step_order})>"
    
    def should_execute(self, context: Dict[str, Any]) -> bool:
        """Check if step should execute based on conditions"""
        if not self.conditions:
            return True
        
        try:
            from json_logic import jsonLogic
            result = jsonLogic(self.conditions, context)
            return bool(result)
        except Exception as e:
            print(f"Error evaluating step conditions: {e}")
            return False


class WorkflowExecution(BaseModel):
    """
    Tracks execution of a workflow instance.
    
    Each time a workflow is triggered, a new execution record is created
    to track the progress and results.
    """
    
    __tablename__ = 'workflow_executions'
    
    workflow_id = Column(
        UUID(as_uuid=True),
        ForeignKey('workflows.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey('documents.id', ondelete='SET NULL'),
        index=True
    )
    
    # Execution Context
    trigger_event = Column(String(100))
    trigger_data = Column(JSONB)
    
    # Status
    status = Column(String, default=ExecutionStatus.PENDING.value, index=True)
    
    # Timing
    started_at = Column(DateTime(timezone=True), server_default='now()', index=True)
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    
    # Results
    success = Column(Boolean)
    error_message = Column(Text)
    
    # Execution Log
    execution_log = Column(JSONB, default=list)
    """
    Detailed step-by-step execution log:
    [
        {
            "step_id": "uuid",
            "step_name": "Extract Data",
            "started_at": "2025-01-15T10:00:00Z",
            "completed_at": "2025-01-15T10:00:02Z",
            "status": "completed",
            "output": {...}
        },
        ...
    ]
    """
    
    # Relationships
    workflow = relationship('Workflow', back_populates='executions')
    document = relationship('Document')
    step_executions = relationship(
        'WorkflowStepExecution',
        back_populates='execution',
        cascade='all, delete-orphan'
    )
    
    def __repr__(self) -> str:
        return f"<WorkflowExecution(id={self.id}, workflow_id={self.workflow_id}, status={self.status})>"
    
    def add_log_entry(self, entry: Dict[str, Any]):
        """Add entry to execution log"""
        if not self.execution_log:
            self.execution_log = []
        
        entry['timestamp'] = datetime.utcnow().isoformat()
        self.execution_log.append(entry)
    
    def complete(self, success: bool, error_message: Optional[str] = None):
        """Mark execution as completed"""
        self.completed_at = datetime.utcnow()
        self.success = success
        self.error_message = error_message
        
        if success:
            self.status = ExecutionStatus.COMPLETED.value
        else:
            self.status = ExecutionStatus.FAILED.value
        
        # Calculate duration
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)


class WorkflowStepExecution(BaseModel):
    """
    Tracks execution of individual workflow steps.
    
    Provides detailed information about each step's execution,
    including inputs, outputs, timing, and errors.
    """
    
    __tablename__ = 'workflow_step_executions'
    
    execution_id = Column(
        UUID(as_uuid=True),
        ForeignKey('workflow_executions.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    step_id = Column(
        UUID(as_uuid=True),
        ForeignKey('workflow_steps.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Status
    status = Column(String, default=ExecutionStatus.PENDING.value)
    
    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    
    # Results
    success = Column(Boolean)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0, nullable=False)
    
    # Input/Output
    input_data = Column(JSONB)
    output_data = Column(JSONB)
    
    # Relationships
    execution = relationship('WorkflowExecution', back_populates='step_executions')
    step = relationship('WorkflowStep', back_populates='step_executions')
    
    def __repr__(self) -> str:
        return f"<WorkflowStepExecution(id={self.id}, step_id={self.step_id}, status={self.status})>"
    
    def start(self, input_data: Optional[Dict[str, Any]] = None):
        """Mark step execution as started"""
        self.status = ExecutionStatus.RUNNING.value
        self.started_at = datetime.utcnow()
        self.input_data = input_data or {}
    
    def complete(
        self,
        success: bool,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ):
        """Mark step execution as completed"""
        self.completed_at = datetime.utcnow()
        self.success = success
        self.output_data = output_data or {}
        self.error_message = error_message
        
        if success:
            self.status = ExecutionStatus.COMPLETED.value
        else:
            self.status = ExecutionStatus.FAILED.value
        
        # Calculate duration
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)
    
    def should_retry(self, max_retries: int) -> bool:
        """Check if step should be retried"""
        return (
            not self.success and
            self.retry_count < max_retries and
            self.status == ExecutionStatus.FAILED.value
        )

💡 WORKFLOW UTILITIES
/backend/utils/workflow_engine.py
python"""
Workflow execution engine
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from models.workflows import (
    Workflow, WorkflowStep, WorkflowExecution, WorkflowStepExecution
)
from models.documents import Document
from models.enums import ExecutionStatus, StepType
import asyncio
from datetime import datetime


class WorkflowEngine:
    """
    Engine for executing workflows.
    
    Handles workflow triggering, step execution, error handling,
    and result tracking.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    async def trigger_workflow(
        self,
        workflow: Workflow,
        document: Optional[Document] = None,
        trigger_event: str = 'manual',
        trigger_data: Optional[Dict[str, Any]] = None
    ) -> WorkflowExecution:
        """
        Trigger a workflow execution.
        
        Args:
            workflow: Workflow to execute
            document: Optional document context
            trigger_event: Event that triggered the workflow
            trigger_data: Additional trigger context
        
        Returns:
            WorkflowExecution instance
        """
        # Create execution record
        execution = WorkflowExecution(
            workflow_id=workflow.id,
            document_id=document.id if document else None,
            trigger_event=trigger_event,
            trigger_data=trigger_data or {},
            status=ExecutionStatus.PENDING.value
        )
        
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)
        
        # Execute asynchronously
        asyncio.create_task(self.execute_workflow(execution))
        
        return execution
    
    async def execute_workflow(self, execution: WorkflowExecution):
        """Execute all steps of a workflow"""
        
        workflow = execution.workflow
        
        # Build execution context
        context = self._build_context(execution)
        
        # Check if workflow should run based on conditions
        if not workflow.should_trigger(context):
            execution.add_log_entry({
                'level': 'info',
                'message': 'Workflow conditions not met, skipping execution'
            })
            execution.status = ExecutionStatus.SKIPPED.value
            self.db.commit()
            return
        
        # Update status to running
        execution.status = ExecutionStatus.RUNNING.value
        self.db.commit()
        
        execution.add_log_entry({
            'level': 'info',
            'message': f'Starting workflow execution: {workflow.name}'
        })
        
        try:
            # Execute steps in order
            for step in workflow.steps:
                # Check if step should execute
                if not step.should_execute(context):
                    execution.add_log_entry({
                        'level': 'info',
                        'message': f'Skipping step {step.name} (conditions not met)'
                    })
                    continue
                
                # Execute step
                step_result = await self.execute_step(execution, step, context)
                
                # Update context with step output
                context['previous_step_output'] = step_result.output_data
                
                # Handle step failure
                if not step_result.success:
                    if step.on_error == 'fail':
                        raise Exception(f"Step {step.name} failed: {step_result.error_message}")
                    elif step.on_error == 'continue':
                        execution.add_log_entry({
                            'level': 'warning',
                            'message': f'Step {step.name} failed but continuing'
                        })
                        continue
                    # 'retry' is handled in execute_step
            
            # Mark as successful
            execution.complete(success=True)
            workflow.increment_stats(success=True)
            
            execution.add_log_entry({
                'level': 'info',
                'message': 'Workflow completed successfully'
            })
            
        except Exception as e:
            # Mark as failed
            execution.complete(success=False, error_message=str(e))
            workflow.increment_stats(success=False)
            
            execution.add_log_entry({
                'level': 'error',
                'message': f'Workflow failed: {str(e)}'
            })
        
        finally:
            self.db.commit()
    
    async def execute_step(
        self,
        execution: WorkflowExecution,
        step: WorkflowStep,
        context: Dict[str, Any]
    ) -> WorkflowStepExecution:
        """Execute a single workflow step"""
        
        # Create step execution record
        step_execution = WorkflowStepExecution(
            execution_id=execution.id,
            step_id=step.id
        )
        
        self.db.add(step_execution)
        self.db.commit()
        self.db.refresh(step_execution)
        
        # Prepare input data
        input_data = self._prepare_step_input(step, context)
        step_execution.start(input_data)
        self.db.commit()
        
        retry_count = 0
        last_error = None
        
        while retry_count <= step.max_retries:
            try:
                # Execute step based on type
                output_data = await self._execute_step_action(step, input_data, context)
                
                # Mark as successful
                step_execution.complete(success=True, output_data=output_data)
                self.db.commit()
                
                execution.add_log_entry({
                    'level': 'info',
                    'message': f'Step {step.name} completed successfully',
                    'duration_ms': step_execution.duration_ms
                })
                
                return step_execution
                
            except asyncio.TimeoutError:
                last_error = f"Step timed out after {step.timeout_seconds} seconds"
                
            except Exception as e:
                last_error = str(e)
            
            # Handle retry
            retry_count += 1
            step_execution.retry_count = retry_count
            
            if retry_count <= step.max_retries:
                execution.add_log_entry({
                    'level': 'warning',
                    'message': f'Step {step.name} failed, retrying ({retry_count}/{step.max_retries})',
                    'error': last_error
                })
                
                # Wait before retry
                await asyncio.sleep(step.retry_delay_seconds)
            else:
                # Max retries reached
                step_execution.complete(
                    success=False,
                    error_message=last_error
                )
                self.db.commit()
                
                execution.add_log_entry({
                    'level': 'error',
                    'message': f'Step {step.name} failed after {retry_count} retries',
                    'error': last_error
                })
                
                return step_execution
    
    async def _execute_step_action(
        self,
        step: WorkflowStep,
        input_data: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the actual step action based on step type"""
        
        step_type = StepType(step.step_type)
        config = step.step_config
        
        if step_type == StepType.CLASSIFY_DOCUMENT:
            return await self._classify_document(config, context)
        
        elif step_type == StepType.EXTRACT_DATA:
            return await self._extract_data(config, context)
        
        elif step_type == StepType.VALIDATE_DATA:
            return await self._validate_data(config, context)
        
        elif step_type == StepType.SEND_NOTIFICATION:
            return await self._send_notification(config, context)
        
        elif step_type == StepType.SEND_EMAIL:
            return await self._send_email(config, context)
        
        elif step_type == StepType.CALL_WEBHOOK:
            return await self._call_webhook(config, context)
        
        elif step_type == StepType.UPDATE_FIELD:
            return await self._update_field(config, context)
        
        elif step_type == StepType.ASSIGN_USER:
            return await self._assign_user(config, context)
        
        elif step_type == StepType.WAIT:
            return await self._wait(config)
        
        else:
            raise ValueError(f"Unknown step type: {step_type}")
    
    def _build_context(self, execution: WorkflowExecution) -> Dict[str, Any]:
        """Build execution context from execution data"""
        context = {
            'execution_id': str(execution.id),
            'workflow_id': str(execution.workflow_id),
            'trigger_event': execution.trigger_event,
            'trigger_data': execution.trigger_data or {},
        }
        
        # Add document context if available
        if execution.document:
            doc = execution.document
            context['document'] = {
                'id': str(doc.id),
                'filename': doc.filename,
                'type': doc.document_type,
                'status': doc.status,
                'confidence': float(doc.overall_confidence) if doc.overall_confidence else None,
                'supplier_id': str(doc.detected_supplier_id) if doc.detected_supplier_id else None,
                'extracted_data': doc.extracted_data or {}
            }
        
        return context
    
    def _prepare_step_input(
        self,
        step: WorkflowStep,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare input data for a step"""
        # Template substitution in config
        import json
        from string import Template
        
        config_str = json.dumps(step.step_config)
        template = Template(config_str)
        
        # Simple template substitution (for basic cases)
        # For complex cases, use a proper template engine
        try:
            rendered = template.safe_substitute(context)
            return json.loads(rendered)
        except:
            return step.step_config
    
    # Step action implementations
    async def _classify_document(self, config: dict, context: dict) -> dict:
        """Classify document step"""
        # TODO: Implement document classification
        return {'classification': 'invoice', 'confidence': 0.95}
    
    async def _extract_data(self, config: dict, context: dict) -> dict:
        """Extract data step"""
        # TODO: Implement data extraction
        return {'extracted_fields': {}}
    
    async def _validate_data(self, config: dict, context: dict) -> dict:
        """Validate data step"""
        # TODO: Implement validation
        return {'valid': True, 'errors': []}
    
    async def _send_notification(self, config: dict, context: dict) -> dict:
        """Send notification step"""
        # TODO: Implement notification sending
        return {'notification_sent': True}
    
    async def _send_email(self, config: dict, context: dict) -> dict:
        """Send email step"""
        # TODO: Implement email sending
        return {'email_sent': True}
    
    async def _call_webhook(self, config: dict, context: dict) -> dict:
        """Call webhook step"""
        # TODO: Implement webhook call
        return {'webhook_called': True, 'response_code': 200}
    
    async def _update_field(self, config: dict, context: dict) -> dict:
        """Update document field step"""
        document_id = context.get('document', {}).get('id')
        if document_id:
            doc = self.db.query(Document).get(document_id)
            if doc:
                field = config.get('field')
                value = config.get('value')
                setattr(doc, field, value)
                self.db.commit()
                return {'field_updated': True, 'field': field, 'value': value}
        return {'field_updated': False}
    
    async def _assign_user(self, config: dict, context: dict) -> dict:
        """Assign user to document step"""
        document_id = context.get('document', {}).get('id')
        user_id = config.get('user_id')
        
        if document_id and user_id:
            doc = self.db.query(Document).get(document_id)
            if doc:
                doc.assigned_to = user_id
                self.db.commit()
                return {'user_assigned': True, 'user_id': user_id}
        return {'user_assigned': False}
    
    async def _wait(self, config: dict) -> dict:
        """Wait step"""
        duration = config.get('duration_seconds', 60)
        await asyncio.sleep(duration)
        return {'waited_seconds': duration}

📝 WORKFLOW USAGE EXAMPLES
/backend/examples/workflow_examples.py
python"""
Examples of creating and using workflows
"""

from sqlalchemy.orm import Session
from models.workflows import Workflow, WorkflowStep
from models.enums import WorkflowTrigger, StepType
from utils.workflow_engine import WorkflowEngine


# =============================================================================
# EXAMPLE 1: Auto-assign high-value invoices
# =============================================================================

def create_high_value_invoice_workflow(db: Session):
    """
    Workflow that automatically assigns invoices over 10,000€ to the CFO for review.
    """
    
    workflow = Workflow(
        name="High Value Invoice Review",
        description="Automatically assign invoices over 10,000€ to CFO",
        trigger_type=WorkflowTrigger.DOCUMENT_PROCESSED.value,
        trigger_config={
            "document_types": ["invoice"]
        },
        conditions={
            "and": [
                {"==": [{"var": "document.type"}, "invoice"]},
                {">": [{"var": "document.extracted_data.total_amount"}, 10000]}
            ]
        },
        is_active=True
    )
    
    db.add(workflow)
    db.flush()  # Get workflow ID
    
    # Step 1: Send notification to CFO
    step1 = WorkflowStep(
        workflow_id=workflow.id,
        name="Notify CFO",
        step_type=StepType.SEND_NOTIFICATION.value,
        step_config={
            "user_role": "cfo",
            "template": "high_value_invoice",
            "channels": ["email", "in_app"],
            "priority": "high"
        },
        step_order=1,
        on_error='continue'
    )
    
    # Step 2: Assign to CFO
    step2 = WorkflowStep(
        workflow_id=workflow.id,
        name="Assign to CFO",
        step_type=StepType.ASSIGN_USER.value,
        step_config={
            "user_role": "cfo"
        },
        step_order=2,
        on_error='fail'
    )
    
    # Step 3: Set review flag
    step3 = WorkflowStep(
        workflow_id=workflow.id,
        name="Set Review Flag",
        step_type=StepType.UPDATE_FIELD.value,
        step_config={
            "field": "needs_review",
            "value": True
        },
        step_order=3
    )
    
    db.add_all([step1, step2, step3])
    db.commit()
    
    print(f"Created workflow: {workflow.name}")
    return workflow


# =============================================================================
# EXAMPLE 2: Low confidence document review
# =============================================================================

def create_low_confidence_review_workflow(db: Session):
    """
    Workflow for documents with low OCR confidence.
    """
    
    workflow = Workflow(
        name="Low Confidence Review",
        description="Flag and assign documents with low OCR confidence",
        trigger_type=WorkflowTrigger.DOCUMENT_PROCESSED.value,
        conditions={
            "<": [{"var": "document.confidence"}, 80]
        },
        is_active=True
    )
    
    db.add(workflow)
    db.flush()
    
    # Step 1: Classify confidence level
    step1 = WorkflowStep(
        workflow_id=workflow.id,
        name="Categorize Confidence",
        step_type=StepType.CONDITIONAL.value,
        step_config={
            "condition": {"<": [{"var": "document.confidence"}, 60]},
            "true_label": "very_low",
            "false_label": "low"
        },
        step_order=1
    )
    
    # Step 2: Assign based on confidence
    step2 = WorkflowStep(
        workflow_id=workflow.id,
        name="Assign Reviewer",
        step_type=StepType.ASSIGN_USER.value,
        step_config={
            "user_role": "{{confidence_level}}_reviewer"  # Template
        },
        step_order=2
    )
    
    # Step 3: Send notification
    step3 = WorkflowStep(
        workflow_id=workflow.id,
        name="Notify Reviewer",
        step_type=StepType.SEND_NOTIFICATION.value,
        step_config={
            "template": "review_needed",
            "channels": ["in_app"]
        },
        step_order=3
    )
    
    db.add_all([step1, step2, step3])
    db.commit()
    
    return workflow


# =============================================================================
# EXAMPLE 3: Automated data extraction and validation
# =============================================================================

def create_invoice_processing_workflow(db: Session):
    """
    Complete invoice processing workflow with extraction and validation.
    """
    
    workflow = Workflow(
        name="Automated Invoice Processing",
        description="Extract, validate, and process invoice data",
        trigger_type=WorkflowTrigger.DOCUMENT_UPLOADED.value,
        trigger_config={
            "document_types": ["invoice"]
        },
        is_active=True
    )
    
    db.add(workflow)
    db.flush()
    
    # Step 1: Extract invoice data
    step1 = WorkflowStep(
        workflow_id=workflow.id,
        name="Extract Invoice Data",
        step_type=StepType.EXTRACT_DATA.value,
        step_config={
            "fields": [
                "invoice_number",
                "invoice_date",
                "due_date",
                "supplier_name",
                "total_amount",
                "net_amount",
                "vat_amount",
                "line_items"
            ],
            "use_template": True
        },
        step_order=1,
        on_error='retry',
        max_retries=2
    )
    
    # Step 2: Validate extracted data
    step2 = WorkflowStep(
        workflow_id=workflow.id,
        name="Validate Data",
        step_type=StepType.VALIDATE_DATA.value,
        step_config={
            "rules": {
                "invoice_number": {
                    "required": True,
                    "pattern": "^[A-Z0-9-]+"
                },
                "total_amount": {
                    "required": True,
                    "min": 0,
                    "must_equal_sum": True  # total = net + vat
                },
                "invoice_date": {
                    "required": True,
                    "format": "date"
                }
            }
        },
        step_order=2,
        on_error='continue'
    )
    
    # Step 3: Check validation results
    step3 = WorkflowStep(
        workflow_id=workflow.id,
        name="Check Validation",
        step_type=StepType.CONDITIONAL.value,
        step_config={
            "condition": {"==": [{"var": "previous_step_output.valid"}, True]},
            "true_step": 4,  # Continue to approval
            "false_step": 6  # Go to manual review
        },
        step_order=3
    )
    
    # Step 4: Auto-approve if valid and under threshold
    step4 = WorkflowStep(
        workflow_id=workflow.id,
        name="Auto Approve",
        step_type=StepType.UPDATE_FIELD.value,
        step_config={
            "field": "status",
            "value": "approved"
        },
        step_order=4,
        conditions={
            "and": [
                {"==": [{"var": "previous_step_output.valid"}, True]},
                {"<": [{"var": "document.extracted_data.total_amount"}, 5000]}
            ]
        }
    )
    
    # Step 5: Send to accounting system
    step5 = WorkflowStep(
        workflow_id=workflow.id,
        name="Export to Accounting",
        step_type=StepType.CALL_WEBHOOK.value,
        step_config={
            "webhook_id": "accounting_system",
            "method": "POST",
            "payload": {
                "invoice_data": "{{document.extracted_data}}"
            }
        },
        step_order=5
    )
    
    # Step 6: Manual review for validation errors
    step6 = WorkflowStep(
        workflow_id=workflow.id,
        name="Manual Review",
        step_type=StepType.ASSIGN_USER.value,
        step_config={
            "user_role": "accountant"
        },
        step_order=6
    )
    
    db.add_all([step1, step2, step3, step4, step5, step6])
    db.commit()
    
    return workflow


# =============================================================================
# EXECUTING WORKFLOWS
# =============================================================================

async def execute_workflow_example(db: Session, document_id: str):
    """Example of triggering a workflow"""
    
    from models.documents import Document
    
    # Get document
    document = db.query(Document).get(document_id)
    
    # Find applicable workflows
    workflows = db.query(Workflow).filter(
        Workflow.is_active == True,
        Workflow.trigger_type == WorkflowTrigger.DOCUMENT_PROCESSED.value
    ).all()
    
    # Initialize engine
    engine = WorkflowEngine(db)
    
    # Trigger each applicable workflow
    for workflow in workflows:
        context = {
            'document': {
                'id': str(document.id),
                'type': document.document_type,
                'confidence': float(document.overall_confidence or 0),
                'extracted_data': document.extracted_data or {}
            }
        }
        
        if workflow.should_trigger(context):
            print(f"Triggering workflow: {workflow.name}")
            execution = await engine.trigger_workflow(
                workflow=workflow,
                document=document,
                trigger_event='document_processed'
            )
            print(f"Created execution: {execution.id}")




🤖 EXTRACTION & ML MODELS
/backend/models/extraction.py
python"""
Machine Learning and Data Extraction models
"""

from sqlalchemy import (
    Column, String, Boolean, Text, ForeignKey,
    Integer, DECIMAL, Date, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from .base import BaseModel, SoftDeleteMixin
from .enums import RuleType, DocumentType
import re


class ExtractionRule(BaseModel):
    """
    Custom rules for extracting specific fields from documents.
    
    Rules can be regex-based, position-based, template-based, or ML model-based.
    Each rule targets a specific field (e.g., invoice_number, total_amount).
    """
    
    __tablename__ = 'extraction_rules'
    
    # Association
    supplier_id = Column(
        UUID(as_uuid=True),
        ForeignKey('suppliers.id', ondelete='CASCADE'),
        index=True
    )
    document_type = Column(String, index=True)
    
    # Rule Identity
    rule_name = Column(String(255), nullable=False)
    field_name = Column(String(100), nullable=False, index=True)
    
    # Rule Definition
    rule_type = Column(String, nullable=False)
    rule_config = Column(JSONB, nullable=False)
    """
    Rule configuration examples by type:
    
    REGEX:
    {
        "pattern": "Rechnung(?:snummer)?:?\\s*([A-Z0-9-]+)",
        "flags": "i",  # Case insensitive
        "group": 1,  # Which regex group to extract
        "preprocess": {
            "strip": true,
            "uppercase": false
        }
    }
    
    POSITION:
    {
        "x": 450,
        "y": 100,
        "width": 200,
        "height": 30,
        "tolerance": 10,
        "page": 1,  # Which page (1-indexed)
        "anchor_text": "Rechnungsnummer",  # Optional: find relative to this text
        "relative_offset": {"x": 100, "y": 0}  # Offset from anchor
    }
    
    TEMPLATE:
    {
        "template_id": "uuid",
        "field_mapping": {
            "source_field": "target_field"
        },
        "transformations": [
            {"type": "strip"},
            {"type": "replace", "pattern": ",", "replacement": "."}
        ]
    }
    
    ML_MODEL:
    {
        "model_name": "invoice_field_extractor",
        "model_version": "1.2.0",
        "endpoint": "http://ml-service/predict",
        "confidence_threshold": 0.85,
        "fallback_rule_id": "uuid"  # Fallback if confidence too low
    }
    """
    
    # Validation
    validation_regex = Column(String(500))
    required = Column(Boolean, default=False, nullable=False)
    
    # Quality Metrics
    success_rate = Column(DECIMAL(5, 2))  # Percentage of successful extractions
    avg_confidence = Column(DECIMAL(5, 2))  # Average confidence score
    usage_count = Column(Integer, default=0, nullable=False)
    
    # Priority (higher = try first)
    priority = Column(Integer, default=0, nullable=False)
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    version = Column(Integer, default=1, nullable=False)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    supplier = relationship('Supplier', back_populates='extraction_rules')
    versions = relationship(
        'ExtractionRuleVersion',
        back_populates='rule',
        cascade='all, delete-orphan'
    )
    
    def __repr__(self) -> str:
        return f"<ExtractionRule(id={self.id}, field='{self.field_name}', type={self.rule_type})>"
    
    def extract(self, text: str, image_data: Optional[Dict] = None) -> Tuple[Optional[str], float]:
        """
        Extract field value from text or image data.
        
        Args:
            text: OCR text to extract from
            image_data: Optional image/position data
        
        Returns:
            tuple: (extracted_value, confidence)
        """
        rule_type = RuleType(self.rule_type)
        
        if rule_type == RuleType.REGEX:
            return self._extract_regex(text)
        elif rule_type == RuleType.POSITION:
            return self._extract_position(image_data)
        elif rule_type == RuleType.TEMPLATE:
            return self._extract_template(text, image_data)
        elif rule_type == RuleType.ML_MODEL:
            return self._extract_ml_model(text, image_data)
        else:
            return None, 0.0
    
    def _extract_regex(self, text: str) -> Tuple[Optional[str], float]:
        """Extract using regex pattern"""
        pattern = self.rule_config.get('pattern')
        flags_str = self.rule_config.get('flags', '')
        group = self.rule_config.get('group', 1)
        
        if not pattern:
            return None, 0.0
        
        # Build regex flags
        flags = 0
        if 'i' in flags_str:
            flags |= re.IGNORECASE
        if 'm' in flags_str:
            flags |= re.MULTILINE
        if 's' in flags_str:
            flags |= re.DOTALL
        
        try:
            match = re.search(pattern, text, flags)
            if match:
                value = match.group(group) if group else match.group(0)
                
                # Preprocessing
                preprocess = self.rule_config.get('preprocess', {})
                if preprocess.get('strip'):
                    value = value.strip()
                if preprocess.get('uppercase'):
                    value = value.upper()
                if preprocess.get('lowercase'):
                    value = value.lower()
                
                # Validate if validation regex is set
                if self.validation_regex:
                    if not re.match(self.validation_regex, value):
                        return None, 0.5  # Found but invalid
                
                return value, 0.95  # High confidence for regex match
            
        except re.error as e:
            print(f"Regex error in rule {self.rule_name}: {e}")
        
        return None, 0.0
    
    def _extract_position(self, image_data: Optional[Dict]) -> Tuple[Optional[str], float]:
        """Extract from specific position in image"""
        if not image_data:
            return None, 0.0
        
        # TODO: Implement position-based extraction
        # This would need bounding box data from OCR
        x = self.rule_config.get('x')
        y = self.rule_config.get('y')
        width = self.rule_config.get('width')
        height = self.rule_config.get('height')
        tolerance = self.rule_config.get('tolerance', 10)
        
        # Find text within bounding box
        # Return extracted text and confidence
        
        return None, 0.0
    
    def _extract_template(self, text: str, image_data: Optional[Dict]) -> Tuple[Optional[str], float]:
        """Extract using template matching"""
        # TODO: Implement template-based extraction
        return None, 0.0
    
    def _extract_ml_model(self, text: str, image_data: Optional[Dict]) -> Tuple[Optional[str], float]:
        """Extract using ML model"""
        # TODO: Implement ML model prediction
        # This would call an external ML service
        return None, 0.0
    
    def validate_value(self, value: str) -> bool:
        """Validate extracted value"""
        if not value and self.required:
            return False
        
        if value and self.validation_regex:
            return bool(re.match(self.validation_regex, value))
        
        return True
    
    def update_metrics(self, success: bool, confidence: Optional[float] = None):
        """Update rule performance metrics"""
        self.usage_count += 1
        
        # Update success rate (exponential moving average)
        if self.success_rate is None:
            self.success_rate = 100.0 if success else 0.0
        else:
            alpha = 0.1  # Smoothing factor
            new_value = 100.0 if success else 0.0
            self.success_rate = float(alpha * new_value + (1 - alpha) * float(self.success_rate))
        
        # Update average confidence
        if confidence is not None:
            if self.avg_confidence is None:
                self.avg_confidence = confidence
            else:
                self.avg_confidence = float(alpha * confidence + (1 - alpha) * float(self.avg_confidence))


class ExtractionRuleVersion(BaseModel):
    """
    Version history for extraction rules.
    
    Tracks changes to rules over time, allowing rollback and performance comparison.
    """
    
    __tablename__ = 'extraction_rule_versions'
    
    rule_id = Column(
        UUID(as_uuid=True),
        ForeignKey('extraction_rules.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    version = Column(Integer, nullable=False)
    rule_config = Column(JSONB, nullable=False)
    
    # Performance Comparison
    performance_delta = Column(JSONB)
    """
    Performance improvement metrics:
    {
        "success_rate_before": 78.5,
        "success_rate_after": 85.2,
        "avg_confidence_before": 0.82,
        "avg_confidence_after": 0.89,
        "improvement_percentage": 8.5
    }
    """
    
    notes = Column(Text)
    
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Relationships
    rule = relationship('ExtractionRule', back_populates='versions')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('version > 0', name='valid_version'),
    )
    
    def __repr__(self) -> str:
        return f"<ExtractionRuleVersion(id={self.id}, rule_id={self.rule_id}, version={self.version})>"


class TrainingData(BaseModel):
    """
    Training data for ML model improvement.
    
    Stores ground truth examples for training and evaluating extraction models.
    Human-validated examples are the gold standard for model training.
    """
    
    __tablename__ = 'training_data'
    
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey('documents.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Field Information
    field_name = Column(String(100), nullable=False, index=True)
    expected_value = Column(Text, nullable=False)  # Ground truth
    extracted_value = Column(Text)  # What the system extracted
    
    # Context
    extraction_method = Column(String(100))  # Which rule/model was used
    was_correct = Column(Boolean)
    
    # Image Region (for position-based training)
    bounding_box = Column(JSONB)
    """
    Bounding box coordinates:
    {
        "x": 450,
        "y": 100,
        "width": 200,
        "height": 30,
        "page": 1
    }
    """
    
    # Validation
    validated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    validated_at = Column(DateTime(timezone=True))
    
    # Training Status
    used_for_training = Column(Boolean, default=False, nullable=False, index=True)
    training_batch_id = Column(String(100))
    
    # Relationships
    document = relationship('Document')
    validator = relationship('User', foreign_keys=[validated_by])
    
    def __repr__(self) -> str:
        return f"<TrainingData(id={self.id}, field='{self.field_name}', validated={self.validated_at is not None})>"
    
    def mark_validated(self, user_id: UUID, is_correct: bool):
        """Mark as human-validated"""
        self.validated_by = user_id
        self.validated_at = datetime.utcnow()
        self.was_correct = is_correct
    
    def mark_used_for_training(self, batch_id: str):
        """Mark as used in training batch"""
        self.used_for_training = True
        self.training_batch_id = batch_id


class ModelPerformance(BaseModel):
    """
    Track ML model performance metrics over time.
    
    Stores daily/hourly performance metrics for each model to track
    improvements, regressions, and overall quality.
    """
    
    __tablename__ = 'model_performance'
    
    model_name = Column(String(100), nullable=False, index=True)
    model_version = Column(String(50), nullable=False, index=True)
    
    # Time Window
    metric_date = Column(Date, nullable=False, index=True)
    hour_of_day = Column(Integer)  # NULL = full day, 0-23 = specific hour
    
    # Classification Metrics
    accuracy = Column(DECIMAL(5, 2))  # Overall accuracy
    precision_score = Column(DECIMAL(5, 2))  # Precision (TP / (TP + FP))
    recall = Column(DECIMAL(5, 2))  # Recall/Sensitivity (TP / (TP + FN))
    f1_score = Column(DECIMAL(5, 2))  # F1 Score (harmonic mean of precision and recall)
    
    # Per-Field Metrics
    field_metrics = Column(JSONB)
    """
    Performance per field:
    {
        "invoice_number": {
            "accuracy": 0.95,
            "precision": 0.92,
            "recall": 0.97,
            "f1_score": 0.94,
            "avg_confidence": 0.89,
            "total_predictions": 150,
            "correct_predictions": 142
        },
        "total_amount": {
            "accuracy": 0.88,
            ...
        }
    }
    """
    
    # Volume Metrics
    total_predictions = Column(Integer, nullable=False, default=0)
    correct_predictions = Column(Integer, nullable=False, default=0)
    
    # Confidence
    avg_confidence = Column(DECIMAL(5, 2))
    
    # Constraints
    __table_args__ = (
        CheckConstraint('hour_of_day IS NULL OR (hour_of_day BETWEEN 0 AND 23)', name='valid_hour'),
    )
    
    def __repr__(self) -> str:
        return f"<ModelPerformance(model='{self.model_name}', version='{self.model_version}', date={self.metric_date})>"
    
    @classmethod
    def record_metrics(
        cls,
        db_session,
        model_name: str,
        model_version: str,
        predictions: List[Dict[str, Any]],
        date: Optional[Date] = None,
        hour: Optional[int] = None
    ):
        """
        Record performance metrics for a batch of predictions.
        
        Args:
            db_session: Database session
            model_name: Name of the model
            model_version: Version of the model
            predictions: List of prediction results with ground truth
            date: Date to record metrics for (defaults to today)
            hour: Hour to record metrics for (None = full day)
        """
        if date is None:
            date = datetime.utcnow().date()
        
        # Calculate overall metrics
        total = len(predictions)
        correct = sum(1 for p in predictions if p.get('correct', False))
        
        accuracy = (correct / total * 100) if total > 0 else 0
        
        # Calculate per-field metrics
        field_metrics = {}
        fields = set(p.get('field_name') for p in predictions)
        
        for field in fields:
            field_preds = [p for p in predictions if p.get('field_name') == field]
            field_correct = sum(1 for p in field_preds if p.get('correct', False))
            field_total = len(field_preds)
            
            field_metrics[field] = {
                'accuracy': (field_correct / field_total * 100) if field_total > 0 else 0,
                'total_predictions': field_total,
                'correct_predictions': field_correct,
                'avg_confidence': sum(p.get('confidence', 0) for p in field_preds) / field_total if field_total > 0 else 0
            }
        
        # Create or update performance record
        perf = db_session.query(cls).filter(
            cls.model_name == model_name,
            cls.model_version == model_version,
            cls.metric_date == date,
            cls.hour_of_day == hour
        ).first()
        
        if not perf:
            perf = cls(
                model_name=model_name,
                model_version=model_version,
                metric_date=date,
                hour_of_day=hour
            )
            db_session.add(perf)
        
        perf.accuracy = accuracy
        perf.total_predictions = total
        perf.correct_predictions = correct
        perf.field_metrics = field_metrics
        perf.avg_confidence = sum(p.get('confidence', 0) for p in predictions) / total if total > 0 else 0
        
        db_session.commit()
        
        return perf

🛠️ EXTRACTION UTILITIES
/backend/utils/extraction_engine.py
python"""
Extraction engine for applying rules and managing ML models
"""

from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from models.extraction import ExtractionRule, TrainingData
from models.documents import Document
from models.suppliers import Supplier
from models.enums import RuleType
import uuid


class ExtractionEngine:
    """
    Engine for extracting structured data from documents.
    
    Manages rule application, fallback strategies, and confidence scoring.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def extract_fields(
        self,
        document: Document,
        ocr_text: str,
        image_data: Optional[Dict] = None,
        fields: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract specified fields from document.
        
        Args:
            document: Document to extract from
            ocr_text: OCR text content
            image_data: Optional image/position data
            fields: List of fields to extract (None = all available)
        
        Returns:
            Dictionary of extracted field values with confidence scores
        """
        results = {}
        
        # Get applicable extraction rules
        rules = self._get_applicable_rules(document, fields)
        
        # Group rules by field
        rules_by_field = {}
        for rule in rules:
            if rule.field_name not in rules_by_field:
                rules_by_field[rule.field_name] = []
            rules_by_field[rule.field_name].append(rule)
        
        # Extract each field
        for field_name, field_rules in rules_by_field.items():
            # Sort by priority
            field_rules.sort(key=lambda r: r.priority, reverse=True)
            
            best_value = None
            best_confidence = 0.0
            best_rule = None
            
            # Try each rule until we get a good result
            for rule in field_rules:
                try:
                    value, confidence = rule.extract(ocr_text, image_data)
                    
                    if value and confidence > best_confidence:
                        # Validate extracted value
                        if rule.validate_value(value):
                            best_value = value
                            best_confidence = confidence
                            best_rule = rule
                            
                            # If confidence is high enough, stop trying more rules
                            if confidence >= 0.95:
                                break
                
                except Exception as e:
                    print(f"Error applying rule {rule.rule_name}: {e}")
                    continue
            
            # Store result
            if best_value is not None:
                results[field_name] = {
                    'value': best_value,
                    'confidence': best_confidence,
                    'rule_id': str(best_rule.id) if best_rule else None,
                    'rule_name': best_rule.rule_name if best_rule else None
                }
                
                # Update rule metrics
                if best_rule:
                    best_rule.update_metrics(success=True, confidence=best_confidence)
            else:
                results[field_name] = {
                    'value': None,
                    'confidence': 0.0,
                    'rule_id': None,
                    'rule_name': None
                }
                
                # Update metrics for all failed rules
                for rule in field_rules:
                    rule.update_metrics(success=False)
        
        self.db.commit()
        
        return results
    
    def _get_applicable_rules(
        self,
        document: Document,
        fields: Optional[List[str]] = None
    ) -> List[ExtractionRule]:
        """Get extraction rules applicable to this document"""
        
        query = self.db.query(ExtractionRule).filter(
            ExtractionRule.is_active == True,
            ExtractionRule.document_type == document.document_type
        )
        
        # Supplier-specific rules take priority
        if document.detected_supplier_id:
            rules = query.filter(
                ExtractionRule.supplier_id == document.detected_supplier_id
            ).all()
            
            # Also get generic rules (no supplier)
            generic_rules = query.filter(
                ExtractionRule.supplier_id.is_(None)
            ).all()
            
            rules.extend(generic_rules)
        else:
            # Only generic rules
            rules = query.filter(
                ExtractionRule.supplier_id.is_(None)
            ).all()
        
        # Filter by specific fields if requested
        if fields:
            rules = [r for r in rules if r.field_name in fields]
        
        return rules
    
    def create_training_data(
        self,
        document: Document,
        field_name: str,
        expected_value: str,
        extracted_value: Optional[str] = None,
        extraction_method: Optional[str] = None,
        bounding_box: Optional[Dict] = None
    ) -> TrainingData:
        """
        Create a training data entry.
        
        Args:
            document: Source document
            field_name: Name of the field
            expected_value: Ground truth value
            extracted_value: What the system extracted
            extraction_method: Which rule/model was used
            bounding_box: Optional position data
        
        Returns:
            TrainingData instance
        """
        training_data = TrainingData(
            document_id=document.id,
            field_name=field_name,
            expected_value=expected_value,
            extracted_value=extracted_value,
            extraction_method=extraction_method,
            bounding_box=bounding_box,
            was_correct=(expected_value == extracted_value) if extracted_value else None
        )
        
        self.db.add(training_data)
        self.db.commit()
        self.db.refresh(training_data)
        
        return training_data
    
    def get_training_dataset(
        self,
        field_name: Optional[str] = None,
        validated_only: bool = True,
        limit: Optional[int] = None
    ) -> List[TrainingData]:
        """
        Get training dataset for ML model training.
        
        Args:
            field_name: Filter by specific field (None = all fields)
            validated_only: Only include human-validated examples
            limit: Maximum number of examples
        
        Returns:
            List of training data
        """
        query = self.db.query(TrainingData).filter(
            TrainingData.used_for_training == False
        )
        
        if field_name:
            query = query.filter(TrainingData.field_name == field_name)
        
        if validated_only:
            query = query.filter(TrainingData.validated_at.isnot(None))
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def suggest_rule_improvements(
        self,
        field_name: str,
        min_usage: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Analyze rules and suggest improvements based on performance.
        
        Args:
            field_name: Field to analyze
            min_usage: Minimum usage count to consider
        
        Returns:
            List of suggestions with analysis
        """
        suggestions = []
        
        # Get all rules for this field
        rules = self.db.query(ExtractionRule).filter(
            ExtractionRule.field_name == field_name,
            ExtractionRule.usage_count >= min_usage
        ).all()
        
        for rule in rules:
            success_rate = float(rule.success_rate or 0)
            
            # Low success rate
            if success_rate < 70:
                suggestions.append({
                    'rule_id': str(rule.id),
                    'rule_name': rule.rule_name,
                    'issue': 'low_success_rate',
                    'success_rate': success_rate,
                    'recommendation': 'Review and update rule pattern or disable rule',
                    'priority': 'high'
                })
            
            # Medium success rate
            elif success_rate < 85:
                suggestions.append({
                    'rule_id': str(rule.id),
                    'rule_name': rule.rule_name,
                    'issue': 'medium_success_rate',
                    'success_rate': success_rate,
                    'recommendation': 'Consider optimizing rule or adding validation',
                    'priority': 'medium'
                })
            
            # Low confidence
            avg_conf = float(rule.avg_confidence or 0)
            if avg_conf < 0.7:
                suggestions.append({
                    'rule_id': str(rule.id),
                    'rule_name': rule.rule_name,
                    'issue': 'low_confidence',
                    'avg_confidence': avg_conf,
                    'recommendation': 'Rule extracts values but with low confidence',
                    'priority': 'medium'
                })
        
        return suggestions

📝 EXTRACTION EXAMPLES
/backend/examples/extraction_examples.py
python"""
Examples of using extraction rules and training data
"""

from sqlalchemy.orm import Session
from models.extraction import ExtractionRule, TrainingData, ModelPerformance
from models.enums import RuleType, DocumentType
from models.documents import Document
from models.suppliers import Supplier
from utils.extraction_engine import ExtractionEngine
from datetime import date
import uuid


# =============================================================================
# EXAMPLE 1: Create regex-based extraction rule
# =============================================================================

def create_invoice_number_rule(db: Session, supplier: Supplier):
    """
    Create a rule to extract invoice numbers using regex.
    Works for invoices with format: RE20250001, RE-2025-0001, etc.
    """
    
    rule = ExtractionRule(
        supplier_id=supplier.id,
        document_type=DocumentType.INVOICE.value,
        rule_name="Invoice Number Extraction",
        field_name="invoice_number",
        rule_type=RuleType.REGEX.value,
        rule_config={
            "pattern": r"Rechnung(?:snummer)?:?\s*([A-Z]{2}[-]?[0-9]{4}[-]?[0-9]{4})",
            "flags": "i",
            "group": 1,
            "preprocess": {
                "strip": True,
                "uppercase": True
            }
        },
        validation_regex=r"^[A-Z]{2}[-]?[0-9]{4}[-]?[0-9]{4}$",
        required=True,
        priority=10,
        is_active=True
    )
    
    db.add(rule)
    db.commit()
    db.refresh(rule)
    
    print(f"Created rule: {rule.rule_name}")
    return rule


# =============================================================================
# EXAMPLE 2: Create position-based rule
# =============================================================================

def create_total_amount_position_rule(db: Session, supplier: Supplier):
    """
    Create a rule to extract total amount from fixed position.
    Useful when supplier always puts total in same location.
    """
    
    rule = ExtractionRule(
        supplier_id=supplier.id,
        document_type=DocumentType.INVOICE.value,
        rule_name="Total Amount (Position-Based)",
        field_name="total_amount",
        rule_type=RuleType.POSITION.value,
        rule_config={
            "x": 450,
            "y": 600,
            "width": 150,
            "height": 30,
            "tolerance": 15,
            "page": 1,
            "anchor_text": "Gesamtbetrag",
            "relative_offset": {"x": 100, "y": 0}
        },
        validation_regex=r"^\d+[.,]\d{2}$",
        required=True,
        priority=8,
        is_active=True
    )
    
    db.add(rule)
    db.commit()
    
    return rule


# =============================================================================
# EXAMPLE 3: Create multiple rules for same field (fallback strategy)
# =============================================================================

def create_invoice_date_rules(db: Session, supplier: Supplier):
    """
    Create multiple rules for invoice date with different patterns.
    Rules are tried in priority order until one succeeds.
    """
    
    # Rule 1: Primary pattern (DD.MM.YYYY)
    rule1 = ExtractionRule(
        supplier_id=supplier.id,
        document_type=DocumentType.INVOICE.value,
        rule_name="Invoice Date (DD.MM.YYYY)",
        field_name="invoice_date",
        rule_type=RuleType.REGEX.value,
        rule_config={
            "pattern": r"Datum:?\s*([0-3][0-9]\.[0-1][0-9]\.[0-9]{4})",
            "group": 1
        },
        validation_regex=r"^[0-3][0-9]\.[0-1][0-9]\.[0-9]{4}$",
        priority=10  # Highest priority
    )
    
    # Rule 2: Alternative pattern (YYYY-MM-DD)
    rule2 = ExtractionRule(
        supplier_id=supplier.id,
        document_type=DocumentType.INVOICE.value,
        rule_name="Invoice Date (YYYY-MM-DD)",
        field_name="invoice_date",
        rule_type=RuleType.REGEX.value,
        rule_config={
            "pattern": r"Datum:?\s*([0-9]{4}-[0-1][0-9]-[0-3][0-9])",
            "group": 1
        },
        validation_regex=r"^[0-9]{4}-[0-1][0-9]-[0-3][0-9]$",
        priority=8  # Lower priority (fallback)
    )
    
    # Rule 3: Flexible pattern (any date format)
    rule3 = ExtractionRule(
        supplier_id=supplier.id,
        document_type=DocumentType.INVOICE.value,
        rule_name="Invoice Date (Flexible)",
        field_name="invoice_date",
        rule_type=RuleType.REGEX.value,
        rule_config={
            "pattern": r"Datum:?\s*([0-9]{1,2}[\./-][0-9]{1,2}[\./-][0-9]{2,4})",
            "group": 1
        },
        priority=5  # Lowest priority (last resort)
    )
    
    db.add_all([rule1, rule2, rule3])
    db.commit()
    
    print(f"Created 3 fallback rules for invoice_date")
    return [rule1, rule2, rule3]


# =============================================================================
# EXAMPLE 4: Extract data from document
# =============================================================================

def extract_invoice_data(db: Session, document: Document):
    """
    Extract structured data from an invoice document.
    """
    
    # Get OCR text (assuming it's already been processed)
    ocr_text = document.full_ocr_result.get('text', '') if document.full_ocr_result else ''
    
    # Initialize extraction engine
    engine = ExtractionEngine(db)
    
    # Extract all fields
    results = engine.extract_fields(
        document=document,
        ocr_text=ocr_text,
        fields=['invoice_number', 'invoice_date', 'total_amount', 'supplier_name']
    )
    
    print("Extraction Results:")
    print("=" * 50)
    
    for field, data in results.items():
        value = data['value']
        confidence = data['confidence']
        rule_name = data.get('rule_name', 'N/A')
        
        print(f"{field}:")
        print(f"  Value: {value}")
        print(f"  Confidence: {confidence:.2%}")
        print(f"  Rule: {rule_name}")
        print()
    
    # Store in document
    document.extracted_data = {
        field: data['value']
        for field, data in results.items()
        if data['value'] is not None
    }
    
    # Calculate overall confidence
    confidences = [data['confidence'] for data in results.values() if data['confidence'] > 0]
    if confidences:
        document.overall_confidence = sum(confidences) / len(confidences) * 100
    
    db.commit()
    
    return results


# =============================================================================
# EXAMPLE 5: Create training data
# =============================================================================

def create_training_examples(db: Session):
    """
    Create training data for ML model improvement.
    """
    
    # Assuming we have processed documents
    documents = db.query(Document).filter(
        Document.document_type == DocumentType.INVOICE.value
    ).limit(10).all()
    
    engine = ExtractionEngine(db)
    
    for doc in documents:
        # Extract data
        results = extract_invoice_data(db, doc)
        
        # Create training data for each field
        for field_name, data in results.items():
            # In production, you would have ground truth from manual validation
            # For this example, we assume the extraction was correct
            
            training_data = engine.create_training_data(
                document=doc,
                field_name=field_name,
                expected_value=data['value'],  # Ground truth
                extracted_value=data['value'],  # What system extracted
                extraction_method=data.get('rule_name')
            )
            
            # Simulate human validation
            # In reality, this would be done through a UI
            if data['confidence'] > 0.9:
                training_data.mark_validated(
                    user_id=uuid.uuid4(),  # Would be actual user ID
                    is_correct=True
                )
    
    db.commit()
    print(f"Created training examples for {len(documents)} documents")


# =============================================================================
# EXAMPLE 6: Analyze rule performance
# =============================================================================

def analyze_rule_performance(db: Session, field_name: str = "invoice_number"):
    """
    Analyze extraction rule performance and get improvement suggestions.
    """
    
    engine = ExtractionEngine(db)
    
    # Get suggestions
    suggestions = engine.suggest_rule_improvements(
        field_name=field_name,
        min_usage=5
    )
    
    print(f"\nRule Performance Analysis for '{field_name}'")
    print("=" * 70)
    
    if not suggestions:
        print("✅ All rules are performing well!")
    else:
        for suggestion in suggestions:
            priority = suggestion['priority']
            emoji = "🔴" if priority == 'high' else "🟡"
            
            print(f"\n{emoji} {suggestion['rule_name']}")
            print(f"   Issue: {suggestion['issue']}")
            print(f"   Recommendation: {suggestion['recommendation']}")
            
            if 'success_rate' in suggestion:
                print(f"   Success Rate: {suggestion['success_rate']:.1f}%")
            if 'avg_confidence' in suggestion:
                print(f"   Avg Confidence: {suggestion['avg_confidence']:.2f}")


# =============================================================================
# EXAMPLE 7: Record model performance metrics
# =============================================================================

def record_model_metrics_example(db: Session):
    """
    Record daily performance metrics for an ML model.
    """
    
    # Simulate prediction results
    predictions = [
        {
            'field_name': 'invoice_number',
            'predicted': 'RE20250001',
            'actual': 'RE20250001',
            'correct': True,
            'confidence': 0.95
        },
        {
            'field_name': 'invoice_number',
            'predicted': 'RE20250002',
            'actual': 'RE20250003',  # Wrong
            'correct': False,
            'confidence': 0.82
        },
        {
            'field_name': 'total_amount',
            'predicted': '1234.56',
            'actual': '1234.56',
            'correct': True,
            'confidence': 0.91
        },
        # ... more predictions
    ]
    
    # Record metrics
    perf = ModelPerformance.record_metrics(
        db_session=db,
        model_name='invoice_extractor',
        model_version='2.1.0',
        predictions=predictions,
        date=date.today()
    )
    
    print(f"Recorded metrics for {perf.model_name} v{perf.model_version}")
    print(f"  Accuracy: {perf.accuracy:.1f}%")
    print(f"  Total Predictions: {perf.total_predictions}")
    print(f"  Correct: {perf.correct_predictions}")
    print(f"  Field Metrics:")
    
    for field, metrics in perf.field_metrics.items():
        print(f"    {field}: {metrics['accuracy']:.1f}% accuracy")


# =============================================================================
# EXAMPLE 8: Get training dataset
# =============================================================================

def export_training_dataset(db: Session, field_name: str = "invoice_number"):
    """
    Export validated training data for ML model training.
    """
    
    engine = ExtractionEngine(db)
    
    # Get validated training data
    training_data = engine.get_training_dataset(
        field_name=field_name,
        validated_only=True,
        limit=1000
    )
    
    print(f"Found {len(training_data)} validated training examples for '{field_name}'")
    
    # Export to format suitable for ML training
    dataset = []
    for td in training_data:
        dataset.append({
            'document_id': str(td.document_id),
            'field_name': td.field_name,
            'expected_value': td.expected_value,
            'extracted_value': td.extracted_value,
            'was_correct': td.was_correct,
            'bounding_box': td.bounding_box,
            'validated_at': td.validated_at.isoformat() if td.validated_at else None
        })
    
    # In production, save to file or send to ML pipeline
    import json
    with open(f'training_data_{field_name}.json', 'w') as f:
        json.dump(dataset, f, indent=2)
    
    print(f"Exported to training_data_{field_name}.json")
    
    # Mark as used
    for td in training_data:
        td.mark_used_for_training(batch_id=f"batch_{date.today()}")
    
    db.commit()

📬 NOTIFICATION & EMAIL MODELS
/backend/models/notifications.py
python"""
Notification and email communication models
"""

from sqlalchemy import (
    Column, String, Boolean, Text, ForeignKey,
    Integer, Time, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from .base import BaseModel
from .enums import (
    NotificationType, NotificationChannel, EmailStatus
)


class Notification(BaseModel):
    """
    In-app notifications for users.
    
    Stores notifications that appear in the user interface,
    such as document processing completions, review requests, etc.
    """
    
    __tablename__ = 'notifications'
    
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Notification Content
    type = Column(String, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # Context
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey('documents.id', ondelete='CASCADE'),
        index=True
    )
    link_url = Column(Text)
    action_button_text = Column(String(100))
    action_button_url = Column(Text)
    
    # Metadata
    metadata = Column(JSONB)
    """
    Additional context data:
    {
        "workflow_id": "uuid",
        "job_id": "uuid",
        "supplier_name": "Company XYZ",
        "confidence_score": 0.85,
        "custom_data": {...}
    }
    """
    
    # Status
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True))
    
    # Delivery
    delivered_at = Column(DateTime(timezone=True))
    
    # Expiration
    expires_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship('User', back_populates='notifications')
    document = relationship('Document', back_populates='notifications')
    
    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type})>"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
    
    def is_expired(self) -> bool:
        """Check if notification has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @classmethod
    def create_document_processed(
        cls,
        user_id: UUID,
        document_id: UUID,
        document_filename: str,
        confidence: float
    ):
        """Factory method for document processed notification"""
        return cls(
            user_id=user_id,
            document_id=document_id,
            type=NotificationType.DOCUMENT_PROCESSED.value,
            title="Document Processed",
            message=f"Your document '{document_filename}' has been processed successfully.",
            metadata={
                'confidence': confidence,
                'filename': document_filename
            },
            link_url=f"/documents/{document_id}",
            action_button_text="View Document",
            action_button_url=f"/documents/{document_id}",
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
    
    @classmethod
    def create_review_needed(
        cls,
        user_id: UUID,
        document_id: UUID,
        document_filename: str,
        confidence: float,
        reason: str = "Low confidence"
    ):
        """Factory method for review needed notification"""
        return cls(
            user_id=user_id,
            document_id=document_id,
            type=NotificationType.REVIEW_NEEDED.value,
            title="Document Review Required",
            message=f"Document '{document_filename}' needs your review. Reason: {reason}",
            metadata={
                'confidence': confidence,
                'reason': reason,
                'filename': document_filename
            },
            link_url=f"/documents/{document_id}/review",
            action_button_text="Review Now",
            action_button_url=f"/documents/{document_id}/review",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
    
    @classmethod
    def create_workflow_completed(
        cls,
        user_id: UUID,
        workflow_name: str,
        workflow_id: UUID,
        success: bool,
        document_id: Optional[UUID] = None
    ):
        """Factory method for workflow completion notification"""
        status = "completed successfully" if success else "failed"
        notification_type = NotificationType.WORKFLOW_COMPLETED if success else NotificationType.ERROR
        
        return cls(
            user_id=user_id,
            document_id=document_id,
            type=notification_type.value,
            title=f"Workflow {status}",
            message=f"Workflow '{workflow_name}' has {status}.",
            metadata={
                'workflow_id': str(workflow_id),
                'workflow_name': workflow_name,
                'success': success
            },
            link_url=f"/workflows/{workflow_id}/executions",
            expires_at=datetime.utcnow() + timedelta(days=14)
        )


class NotificationPreference(BaseModel):
    """
    User preferences for notifications.
    
    Controls which types of notifications users want to receive
    and through which channels (email, in-app, etc.).
    """
    
    __tablename__ = 'notification_preferences'
    
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        unique=True
    )
    
    # Channel Preferences
    email_enabled = Column(Boolean, default=True, nullable=False)
    in_app_enabled = Column(Boolean, default=True, nullable=False)
    
    # Type Preferences (JSONB for flexibility)
    preferences = Column(JSONB, default={
        'document_processed': {'email': True, 'in_app': True},
        'review_needed': {'email': True, 'in_app': True},
        'workflow_completed': {'email': False, 'in_app': True},
        'system_alert': {'email': True, 'in_app': True}
    })
    """
    Preferences structure:
    {
        "document_processed": {
            "email": true,
            "in_app": true,
            "threshold": {
                "confidence_below": 80  # Only notify if confidence < 80%
            }
        },
        "review_needed": {
            "email": true,
            "in_app": true,
            "batch": true,  # Send batched digest instead of individual
            "batch_frequency": "daily"
        },
        "workflow_completed": {
            "email": false,
            "in_app": true,
            "only_failures": true  # Only notify on failures
        },
        "system_alert": {
            "email": true,
            "in_app": true,
            "min_severity": "warning"  # Only warning and above
        }
    }
    """
    
    # Quiet Hours
    quiet_hours_start = Column(Time)
    quiet_hours_end = Column(Time)
    quiet_hours_timezone = Column(String(50), default='Europe/Berlin')
    
    # Relationships
    user = relationship('User')
    
    def __repr__(self) -> str:
        return f"<NotificationPreference(id={self.id}, user_id={self.user_id})>"
    
    def should_notify(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if user should receive notification.
        
        Args:
            notification_type: Type of notification
            channel: Communication channel
            context: Additional context for conditional logic
        
        Returns:
            bool: True if notification should be sent
        """
        # Check if channel is globally enabled
        if channel == NotificationChannel.EMAIL and not self.email_enabled:
            return False
        if channel == NotificationChannel.IN_APP and not self.in_app_enabled:
            return False
        
        # Check type-specific preferences
        type_key = notification_type.value
        type_prefs = self.preferences.get(type_key, {})
        
        # Check if this channel is enabled for this type
        channel_key = channel.value
        if not type_prefs.get(channel_key, True):
            return False
        
        # Apply conditional logic based on context
        if context:
            # Example: Only notify if confidence below threshold
            if 'threshold' in type_prefs:
                threshold = type_prefs['threshold']
                if 'confidence_below' in threshold:
                    confidence = context.get('confidence', 100)
                    if confidence >= threshold['confidence_below']:
                        return False
            
            # Example: Only notify on failures
            if type_prefs.get('only_failures', False):
                if context.get('success', True):
                    return False
        
        # Check quiet hours
        if self.is_quiet_hours() and channel == NotificationChannel.EMAIL:
            return False
        
        return True
    
    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours"""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        from zoneinfo import ZoneInfo
        
        # Get current time in user's timezone
        tz = ZoneInfo(self.quiet_hours_timezone)
        now = datetime.now(tz).time()
        
        # Check if within quiet hours
        if self.quiet_hours_start < self.quiet_hours_end:
            # Normal case: e.g., 22:00 - 08:00
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            # Crosses midnight: e.g., 22:00 - 08:00
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end
    
    def get_preference(self, notification_type: str, channel: str) -> bool:
        """Get preference for specific type and channel"""
        type_prefs = self.preferences.get(notification_type, {})
        return type_prefs.get(channel, False)
    
    def set_preference(self, notification_type: str, channel: str, enabled: bool):
        """Set preference for specific type and channel"""
        if notification_type not in self.preferences:
            self.preferences[notification_type] = {}
        
        self.preferences[notification_type][channel] = enabled


class EmailQueue(BaseModel):
    """
    Queue for outgoing emails.
    
    Manages email delivery with retry logic, tracking, and error handling.
    """
    
    __tablename__ = 'email_queue'
    
    # Recipient
    to_address = Column(String(255), nullable=False, index=True)
    to_name = Column(String(255))
    cc_addresses = Column(ARRAY(Text))
    bcc_addresses = Column(ARRAY(Text))
    
    # Content
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)
    
    # Template
    template_id = Column(UUID(as_uuid=True), ForeignKey('email_templates.id'))
    template_data = Column(JSONB)
    
    # Attachments
    attachments = Column(JSONB)
    """
    Attachment structure:
    [
        {
            "filename": "invoice.pdf",
            "content_type": "application/pdf",
            "path": "/path/to/file",
            "size": 12345
        }
    ]
    """
    
    # Status
    status = Column(String, default=EmailStatus.QUEUED.value, nullable=False, index=True)
    
    # Delivery
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    next_attempt_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True
    )
    
    sent_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    
    # Metadata
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'))
    
    # Relationships
    template = relationship('EmailTemplate')
    user = relationship('User')
    document = relationship('Document')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('attempts <= max_attempts', name='valid_attempts'),
    )
    
    def __repr__(self) -> str:
        return f"<EmailQueue(id={self.id}, to='{self.to_address}', status={self.status})>"
    
    def mark_sending(self):
        """Mark email as currently being sent"""
        self.status = EmailStatus.SENDING.value
        self.attempts += 1
    
    def mark_sent(self):
        """Mark email as successfully sent"""
        self.status = EmailStatus.SENT.value
        self.sent_at = datetime.utcnow()
        self.error_message = None
    
    def mark_failed(self, error_message: str):
        """Mark email as failed"""
        self.error_message = error_message
        
        if self.attempts >= self.max_attempts:
            self.status = EmailStatus.FAILED.value
        else:
            # Schedule retry with exponential backoff
            self.status = EmailStatus.QUEUED.value
            backoff_minutes = (2 ** self.attempts) * 5  # 5, 10, 20, 40 minutes
            self.next_attempt_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)
    
    def mark_bounced(self):
        """Mark email as bounced"""
        self.status = EmailStatus.BOUNCED.value
    
    @classmethod
    def create_from_template(
        cls,
        template: 'EmailTemplate',
        to_address: str,
        template_data: Dict[str, Any],
        to_name: Optional[str] = None,
        user_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None
    ):
        """
        Create email from template.
        
        Args:
            template: Email template to use
            to_address: Recipient email
            template_data: Data to fill in template
            to_name: Recipient name
            user_id: Associated user
            document_id: Associated document
        
        Returns:
            EmailQueue instance
        """
        # Render template
        subject = template.render_subject(template_data)
        body_html = template.render_body_html(template_data)
        body_text = template.render_body_text(template_data) if template.body_text else None
        
        return cls(
            to_address=to_address,
            to_name=to_name,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            template_id=template.id,
            template_data=template_data,
            user_id=user_id,
            document_id=document_id
        )


class EmailTemplate(BaseModel):
    """
    Reusable email templates.
    
    Defines templates with variable substitution for common email types.
    Uses Jinja2-style templating syntax.
    """
    
    __tablename__ = 'email_templates'
    
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)
    
    # Variables used in template
    variables = Column(ARRAY(Text))
    """
    List of available template variables:
    ['user_name', 'document_title', 'confidence', 'review_url']
    """
    
    # Categorization
    category = Column(String(100), index=True)
    
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    def __repr__(self) -> str:
        return f"<EmailTemplate(id={self.id}, name='{self.name}')>"
    
    def render_subject(self, data: Dict[str, Any]) -> str:
        """Render subject with template data"""
        from jinja2 import Template
        template = Template(self.subject)
        return template.render(**data)
    
    def render_body_html(self, data: Dict[str, Any]) -> str:
        """Render HTML body with template data"""
        from jinja2 import Template
        template = Template(self.body_html)
        return template.render(**data)
    
    def render_body_text(self, data: Dict[str, Any]) -> Optional[str]:
        """Render plain text body with template data"""
        if not self.body_text:
            return None
        
        from jinja2 import Template
        template = Template(self.body_text)
        return template.render(**data)
    
    def validate_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate template data has all required variables.
        
        Returns:
            tuple: (is_valid, missing_variables)
        """
        if not self.variables:
            return True, []
        
        missing = [var for var in self.variables if var not in data]
        return len(missing) == 0, missing
    
    def preview(self, sample_data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Generate preview with sample data.
        
        Args:
            sample_data: Optional sample data, uses defaults if not provided
        
        Returns:
            dict with rendered subject and body
        """
        # Default sample data
        if sample_data is None:
            sample_data = {
                var: f"[{var}]"
                for var in (self.variables or [])
            }
        
        return {
            'subject': self.render_subject(sample_data),
            'body_html': self.render_body_html(sample_data),
            'body_text': self.render_body_text(sample_data) if self.body_text else None
        }

🛠️ NOTIFICATION UTILITIES
/backend/utils/notification_service.py
python"""
Notification service for sending notifications across channels
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from models.notifications import (
    Notification, NotificationPreference, EmailQueue, EmailTemplate
)
from models.auth import User
from models.documents import Document
from models.enums import NotificationType, NotificationChannel
from datetime import datetime
import uuid


class NotificationService:
    """
    Service for managing notifications across all channels.
    
    Handles notification creation, delivery, and user preferences.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def send_notification(
        self,
        user_id: UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        channels: List[NotificationChannel] = None,
        document_id: Optional[UUID] = None,
        link_url: Optional[str] = None,
        action_button_text: Optional[str] = None,
        action_button_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        email_template: Optional[str] = None,
        email_data: Optional[Dict[str, Any]] = None
    ):
        """
        Send notification through appropriate channels based on user preferences.
        
        Args:
            user_id: Recipient user ID
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            channels: Channels to send through (None = check preferences)
            document_id: Associated document
            link_url: Link URL
            action_button_text: Action button text
            action_button_url: Action button URL
            metadata: Additional metadata
            email_template: Email template name (for email channel)
            email_data: Data for email template
        """
        # Get user preferences
        prefs = self.get_or_create_preferences(user_id)
        
        # Determine which channels to use
        if channels is None:
            channels = []
            context = metadata or {}
            
            if prefs.should_notify(notification_type, NotificationChannel.IN_APP, context):
                channels.append(NotificationChannel.IN_APP)
            
            if prefs.should_notify(notification_type, NotificationChannel.EMAIL, context):
                channels.append(NotificationChannel.EMAIL)
        
        # Send through each channel
        for channel in channels:
            if channel == NotificationChannel.IN_APP:
                self._send_in_app(
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    document_id=document_id,
                    link_url=link_url,
                    action_button_text=action_button_text,
                    action_button_url=action_button_url,
                    metadata=metadata
                )
            
            elif channel == NotificationChannel.EMAIL:
                self._send_email(
                    user_id=user_id,
                    template_name=email_template or 'generic_notification',
                    template_data=email_data or {
                        'title': title,
                        'message': message,
                        'link_url': link_url
                    },
                    document_id=document_id
                )
    
    def _send_in_app(
        self,
        user_id: UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        document_id: Optional[UUID] = None,
        link_url: Optional[str] = None,
        action_button_text: Optional[str] = None,
        action_button_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Send in-app notification"""
        notification = Notification(
            user_id=user_id,
            type=notification_type.value,
            title=title,
            message=message,
            document_id=document_id,
            link_url=link_url,
            action_button_text=action_button_text,
            action_button_url=action_button_url,
            metadata=metadata,
            delivered_at=datetime.utcnow()
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        return notification
    
    def _send_email(
        self,
        user_id: UUID,
        template_name: str,
        template_data: Dict[str, Any],
        document_id: Optional[UUID] = None
    ):
        """Queue email for sending"""
        # Get user
        user = self.db.query(User).get(user_id)
        if not user:
            return None
        
        # Get template
        template = self.db.query(EmailTemplate).filter(
            EmailTemplate.name == template_name,
            EmailTemplate.is_active == True
        ).first()
        
        if not template:
            print(f"Email template '{template_name}' not found")
            return None
        
        # Create email
        email = EmailQueue.create_from_template(
            template=template,
            to_address=user.email,
            to_name=user.full_name,
            template_data=template_data,
            user_id=user_id,
            document_id=document_id
        )
        
        self.db.add(email)
        self.db.commit()
        self.db.refresh(email)
        
        return email
    
    def get_or_create_preferences(self, user_id: UUID) -> NotificationPreference:
        """Get user preferences or create with defaults"""
        prefs = self.db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id
        ).first()
        
        if not prefs:
            prefs = NotificationPreference(user_id=user_id)
            self.db.add(prefs)
            self.db.commit()
            self.db.refresh(prefs)
        
        return prefs
    
    def get_unread_count(self, user_id: UUID) -> int:
        """Get count of unread notifications"""
        return self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).count()
    
    def get_recent_notifications(
        self,
        user_id: UUID,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[Notification]:
        """Get recent notifications for user"""
        query = self.db.query(Notification).filter(
            Notification.user_id == user_id
        )
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        return query.order_by(
            Notification.created_at.desc()
        ).limit(limit).all()
    
    def mark_all_as_read(self, user_id: UUID):
        """Mark all notifications as read for user"""
        self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({
            'is_read': True,
            'read_at': datetime.utcnow()
        })
        
        self.db.commit()
    
    def delete_old_notifications(self, days: int = 30):
        """Delete notifications older than specified days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        deleted = self.db.query(Notification).filter(
            Notification.created_at < cutoff,
            Notification.is_read == True
        ).delete()
        
        self.db.commit()
        
        return deleted


class EmailService:
    """
    Service for processing email queue.
    
    Handles actual email sending with SMTP.
    """
    
    def __init__(self, db: Session, smtp_config: Dict[str, Any]):
        self.db = db
        self.smtp_config = smtp_config
    
    def process_queue(self, batch_size: int = 10):
        """
        Process pending emails in queue.
        
        Args:
            batch_size: Number of emails to process in one batch
        """
        # Get pending emails
        emails = self.db.query(EmailQueue).filter(
            EmailQueue.status == EmailStatus.QUEUED.value,
            EmailQueue.next_attempt_at <= datetime.utcnow()
        ).limit(batch_size).all()
        
        for email in emails:
            try:
                self.send_email(email)
            except Exception as e:
                print(f"Error sending email {email.id}: {e}")
    
    def send_email(self, email: EmailQueue):
        """
        Send a single email.
        
        Args:
            email: EmailQueue instance
        """
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        
        email.mark_sending()
        self.db.commit()
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = email.subject
            msg['From'] = self.smtp_config['from_address']
            msg['To'] = email.to_address
            
            if email.to_name:
                msg['To'] = f"{email.to_name} <{email.to_address}>"
            
            # CC and BCC
            if email.cc_addresses:
                msg['Cc'] = ', '.join(email.cc_addresses)
            
            # Add plain text
            if email.body_text:
                part1 = MIMEText(email.body_text, 'plain', 'utf-8')
                msg.attach(part1)
            
            # Add HTML
            part2 = MIMEText(email.body_html, 'html', 'utf-8')
            msg.attach(part2)
            
            # Add attachments
            if email.attachments:
                for attachment in email.attachments:
                    self._add_attachment(msg, attachment)
            
            # Send email
            with smtplib.SMTP(
                self.smtp_config['host'],
                self.smtp_config['port']
            ) as server:
                if self.smtp_config.get('use_tls', True):
                    server.starttls()
                
                if self.smtp_config.get('username'):
                    server.login(
                        self.smtp_config['username'],
                        self.smtp_config['password']
                    )
                
                # Build recipient list
                recipients = [email.to_address]
                if email.cc_addresses:
                    recipients.extend(email.cc_addresses)
                if email.bcc_addresses:
                    recipients.extend(email.bcc_addresses)
                
                server.send_message(msg, to_addrs=recipients)
            
            # Mark as sent
            email.mark_sent()
            self.db.commit()
            
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            email.mark_failed(error_msg)
            self.db.commit()
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            email.mark_failed(error_msg)
            self.db.commit()
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]):
        """Add attachment to email message"""
        with open(attachment['path'], 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename={attachment["filename"]}'
        )
        
        msg.attach(part)

📝 NOTIFICATION EXAMPLES
/backend/examples/notification_examples.py
python"""
Examples of using notifications and email system
"""

from sqlalchemy.orm import Session
from models.notifications import (
    Notification, NotificationPreference, EmailQueue, EmailTemplate
)
from models.enums import NotificationType, NotificationChannel
from utils.notification_service import NotificationService, EmailService
from datetime import time
import uuid


# =============================================================================
# EXAMPLE 1: Send document processed notification
# =============================================================================

def send_document_processed_notification(db: Session, user_id: UUID, document):
    """
    Send notification when document processing is complete.
    """
    service = NotificationService(db)
    
    service.send_notification(
        user_id=user_id,
        notification_type=NotificationType.DOCUMENT_PROCESSED,
        title="Document Processed",
        message=f"Your document '{document.filename}' has been processed successfully.",
        document_id=document.id,
        link_url=f"/documents/{document.id}",
        action_button_text="View Document",
        action_button_url=f"/documents/{document.id}",
        metadata={
            'confidence': float(document.overall_confidence or 0),
            'document_type': document.document_type
        },
        email_template='document_processed',
        email_data={
            'user_name': 'John Doe',  # Would get from user object
            'document_title': document.filename,
            'confidence': float(document.overall_confidence or 0),
            'view_url': f"https://app.example.com/documents/{document.id}"
        }
    )
    
    print(f"Sent document processed notification for {document.filename}")


# =============================================================================
# EXAMPLE 2: Send review needed notification
# =============================================================================

def send_review_needed_notification(db: Session, user_id: UUID, document):
    """
    Send notification when document needs manual review.
    """
    service = NotificationService(db)
    
    confidence = float(document.overall_confidence or 0)
    reason = f"Low confidence ({confidence:.1f}%)" if confidence < 80 else "Manual review required"
    
    service.send_notification(
        user_id=user_id,
        notification_type=NotificationType.REVIEW_NEEDED,
        title="Document Review Required",
        message=f"Document '{document.filename}' needs your review. {reason}",
        document_id=document.id,
        link_url=f"/documents/{document.id}/review",
        action_button_text="Review Now",
        action_button_url=f"/documents/{document.id}/review",
        metadata={
            'confidence': confidence,
            'reason': reason
        },
        email_template='review_needed',
        email_data={
            'user_name': 'John Doe',
            'document_title': document.filename,
            'confidence': confidence,
            'reason': reason,
            'review_url': f"https://app.example.com/documents/{document.id}/review"
        }
    )


# =============================================================================
# EXAMPLE 3: Configure user notification preferences
# =============================================================================

def configure_user_preferences(db: Session, user_id: UUID):
    """
    Configure custom notification preferences for a user.
    """
    service = NotificationService(db)
    prefs = service.get_or_create_preferences(user_id)
    
    # Enable email for important notifications only
    prefs.email_enabled = True
    prefs.in_app_enabled = True
    
    # Set quiet hours (no emails between 22:00 and 08:00)
    prefs.quiet_hours_start = time(22, 0)
    prefs.quiet_hours_end = time(8, 0)
    prefs.quiet_hours_timezone = 'Europe/Berlin'
    
    # Customize per-type preferences
    prefs.preferences = {
        'document_processed': {
            'email': False,  # No email for routine processing
            'in_app': True
        },
        'review_needed': {
            'email': True,  # Email for reviews
            'in_app': True,
            'batch': False  # Don't batch, send immediately
        },
        'workflow_completed': {
            'email': False,
            'in_app': True,
            'only_failures': True  # Only notify on failures
        },
        'system_alert': {
            'email': True,
            'in_app': True,
            'min_severity': 'warning'
        }
    }
    
    db.commit()
    print(f"Updated preferences for user {user_id}")


# =============================================================================
# EXAMPLE 4: Create email templates
# =============================================================================

def create_email_templates(db: Session):
    """
    Create standard email templates.
    """
    
    # Document processed template
    template1 = EmailTemplate(
        name='document_processed',
        category='documents',
        description='Sent when document processing is complete',
        subject='Document "{{ document_title }}" processed',
        body_html='''
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Document Processed Successfully ✅</h2>
            <p>Hi {{ user_name }},</p>
            <p>Your document <strong>{{ document_title }}</strong> has been processed.</p>
            <p><strong>Confidence:</strong> {{ confidence }}%</p>
            <p>
                <a href="{{ view_url }}" 
                   style="background-color: #4CAF50; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Document
                </a>
            </p>
            <p style="color: #666; font-size: 12px;">
                This is an automated message from the OCR System.
            </p>
        </body>
        </html>
        ''',
        body_text='''
        Document Processed Successfully
        
        Hi {{ user_name }},
        
        Your document "{{ document_title }}" has been processed.
        
        Confidence: {{ confidence }}%
        
        View document: {{ view_url }}
        
        ---
        This is an automated message from the OCR System.
        ''',
        variables=['user_name', 'document_title', 'confidence', 'view_url'],
        is_active=True
    )
    
    # Review needed template
    template2 = EmailTemplate(
        name='review_needed',
        category='documents',
        description='Sent when document needs manual review',
        subject='Review Required: {{ document_title }}',
        body_html='''
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Document Review Required ⚠️</h2>
            <p>Hi {{ user_name }},</p>
            <p>Document <strong>{{ document_title }}</strong> needs your review.</p>
            <p><strong>Reason:</strong> {{ reason }}</p>
            <p><strong>Confidence:</strong> {{ confidence }}%</p>
            <p>
                <a href="{{ review_url }}" 
                   style="background-color: #FF9800; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    Review Now
                </a>
            </p>
            <p style="color: #666; font-size: 12px;">
                Please review as soon as possible to ensure accuracy.
            </p>
        </body>
        </html>
        ''',
        body_text='''
        Document Review Required
        
        Hi {{ user_name }},
        
        Document "{{ document_title }}" needs your review.
        
        Reason: {{ reason }}
        Confidence: {{ confidence }}%
        
        Review now: {{ review_url }}
        
        Please review as soon as possible to ensure accuracy.
        ''',
        variables=['user_name', 'document_title', 'confidence', 'reason', 'review_url'],
        is_active=True
    )
    
    # Workflow completed template
    template3 = EmailTemplate(
        name='workflow_completed',
        category='workflows',
        description='Sent when workflow execution completes',
        subject='Workflow {{ workflow_name }} {{ status }}',
        body_html='''
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Workflow {{ status_emoji }} {{ status }}</h2>
            <p>Hi {{ user_name }},</p>
            <p>Workflow <strong>{{ workflow_name }}</strong> has {{ status }}.</p>
            {% if error_message %}
            <p style="color: #f44336;"><strong>Error:</strong> {{ error_message }}</p>
            {% endif %}
            <p>
                <a href="{{ workflow_url }}" 
                   style="background-color: #2196F3; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Details
                </a>
            </p>
        </body>
        </html>
        ''',
        body_text='''
        Workflow {{ status }}
        
        Hi {{ user_name }},
        
        Workflow "{{ workflow_name }}" has {{ status }}.
        
        {% if error_message %}
        Error: {{ error_message }}
        {% endif %}
        
        View details: {{ workflow_url }}
        ''',
        variables=['user_name', 'workflow_name', 'status', 'status_emoji', 'error_message', 'workflow_url'],
        is_active=True
    )
    
    db.add_all([template1, template2, template3])
    db.commit()
    
    print("Created 3 email templates")


# =============================================================================
# EXAMPLE 5: Get user notifications
# =============================================================================

def get_user_notifications(db: Session, user_id: UUID):
    """
    Retrieve notifications for a user.
    """
    service = NotificationService(db)
    
    # Get unread count
    unread_count = service.get_unread_count(user_id)
    print(f"Unread notifications: {unread_count}")
    
    # Get recent notifications
    notifications = service.get_recent_notifications(
        user_id=user_id,
        limit=10,
        unread_only=False
    )
    
    print(f"\nRecent notifications:")
    for notif in notifications:
        status = "📌 Unread" if not notif.is_read else "✓ Read"
        print(f"{status} - {notif.title}")
        print(f"   {notif.message}")
        print(f"   Created: {notif.created_at}")
        print()


# =============================================================================
# EXAMPLE 6: Process email queue
# =============================================================================

def process_email_queue_example(db: Session):
    """
    Process pending emails in the queue.
    """
    smtp_config = {
        'host': 'smtp.gmail.com',
        'port': 587,
        'use_tls': True,
        'from_address': 'noreply@example.com',
        'username': 'your-email@gmail.com',
        'password': 'your-app-password'
    }
    
    email_service = EmailService(db, smtp_config)
    
    # Process up to 20 emails
    email_service.process_queue(batch_size=20)
    
    # Check queue status
    pending = db.query(EmailQueue).filter(
        EmailQueue.status == 'queued'
    ).count()
    
    failed = db.query(EmailQueue).filter(
        EmailQueue.status == 'failed'
    ).count()
    
    print(f"Email Queue Status:")
    print(f"  Pending: {pending}")
    print(f"  Failed: {failed}")


# =============================================================================
# EXAMPLE 7: Batch notifications
# =============================================================================

def send_batch_notifications(db: Session, user_ids: List[UUID], message: str):
    """
    Send same notification to multiple users.
    """
    service = NotificationService(db)
    
    for user_id in user_ids:
        service.send_notification(
            user_id=user_id,
            notification_type=NotificationType.INFO,
            title="System Announcement",
            message=message,
            channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            email_template='generic_notification',
            email_data={
                'user_name': 'User',  # Would get from user object
                'title': 'System Announcement',
                'message': message
            }
        )
    
    print(f"Sent batch notification to {len(user_ids)} users")


# =============================================================================
# EXAMPLE 8: Cleanup old notifications
# =============================================================================

def cleanup_old_notifications(db: Session):
    """
    Clean up old read notifications.
    """
    service = NotificationService(db)
    
    # Delete notifications older than 30 days
    deleted = service.delete_old_notifications(days=30)
    
    print(f"Deleted {deleted} old notifications")



📬 NOTIFICATION & EMAIL MODELS
/backend/models/notifications.py
python"""
Notification and email communication models
"""

from sqlalchemy import (
    Column, String, Boolean, Text, ForeignKey,
    Integer, Time, CheckConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from .base import BaseModel
from .enums import (
    NotificationType, NotificationChannel, EmailStatus
)


class Notification(BaseModel):
    """
    In-app notifications for users.
    
    Stores notifications that appear in the user interface,
    such as document processing completions, review requests, etc.
    """
    
    __tablename__ = 'notifications'
    
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    
    # Notification Content
    type = Column(String, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # Context
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey('documents.id', ondelete='CASCADE'),
        index=True
    )
    link_url = Column(Text)
    action_button_text = Column(String(100))
    action_button_url = Column(Text)
    
    # Metadata
    metadata = Column(JSONB)
    """
    Additional context data:
    {
        "workflow_id": "uuid",
        "job_id": "uuid",
        "supplier_name": "Company XYZ",
        "confidence_score": 0.85,
        "custom_data": {...}
    }
    """
    
    # Status
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True))
    
    # Delivery
    delivered_at = Column(DateTime(timezone=True))
    
    # Expiration
    expires_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship('User', back_populates='notifications')
    document = relationship('Document', back_populates='notifications')
    
    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type})>"
    
    def mark_as_read(self):
        """Mark notification as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = datetime.utcnow()
    
    def is_expired(self) -> bool:
        """Check if notification has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @classmethod
    def create_document_processed(
        cls,
        user_id: UUID,
        document_id: UUID,
        document_filename: str,
        confidence: float
    ):
        """Factory method for document processed notification"""
        return cls(
            user_id=user_id,
            document_id=document_id,
            type=NotificationType.DOCUMENT_PROCESSED.value,
            title="Document Processed",
            message=f"Your document '{document_filename}' has been processed successfully.",
            metadata={
                'confidence': confidence,
                'filename': document_filename
            },
            link_url=f"/documents/{document_id}",
            action_button_text="View Document",
            action_button_url=f"/documents/{document_id}",
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
    
    @classmethod
    def create_review_needed(
        cls,
        user_id: UUID,
        document_id: UUID,
        document_filename: str,
        confidence: float,
        reason: str = "Low confidence"
    ):
        """Factory method for review needed notification"""
        return cls(
            user_id=user_id,
            document_id=document_id,
            type=NotificationType.REVIEW_NEEDED.value,
            title="Document Review Required",
            message=f"Document '{document_filename}' needs your review. Reason: {reason}",
            metadata={
                'confidence': confidence,
                'reason': reason,
                'filename': document_filename
            },
            link_url=f"/documents/{document_id}/review",
            action_button_text="Review Now",
            action_button_url=f"/documents/{document_id}/review",
            expires_at=datetime.utcnow() + timedelta(days=7)
        )
    
    @classmethod
    def create_workflow_completed(
        cls,
        user_id: UUID,
        workflow_name: str,
        workflow_id: UUID,
        success: bool,
        document_id: Optional[UUID] = None
    ):
        """Factory method for workflow completion notification"""
        status = "completed successfully" if success else "failed"
        notification_type = NotificationType.WORKFLOW_COMPLETED if success else NotificationType.ERROR
        
        return cls(
            user_id=user_id,
            document_id=document_id,
            type=notification_type.value,
            title=f"Workflow {status}",
            message=f"Workflow '{workflow_name}' has {status}.",
            metadata={
                'workflow_id': str(workflow_id),
                'workflow_name': workflow_name,
                'success': success
            },
            link_url=f"/workflows/{workflow_id}/executions",
            expires_at=datetime.utcnow() + timedelta(days=14)
        )


class NotificationPreference(BaseModel):
    """
    User preferences for notifications.
    
    Controls which types of notifications users want to receive
    and through which channels (email, in-app, etc.).
    """
    
    __tablename__ = 'notification_preferences'
    
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        unique=True
    )
    
    # Channel Preferences
    email_enabled = Column(Boolean, default=True, nullable=False)
    in_app_enabled = Column(Boolean, default=True, nullable=False)
    
    # Type Preferences (JSONB for flexibility)
    preferences = Column(JSONB, default={
        'document_processed': {'email': True, 'in_app': True},
        'review_needed': {'email': True, 'in_app': True},
        'workflow_completed': {'email': False, 'in_app': True},
        'system_alert': {'email': True, 'in_app': True}
    })
    """
    Preferences structure:
    {
        "document_processed": {
            "email": true,
            "in_app": true,
            "threshold": {
                "confidence_below": 80  # Only notify if confidence < 80%
            }
        },
        "review_needed": {
            "email": true,
            "in_app": true,
            "batch": true,  # Send batched digest instead of individual
            "batch_frequency": "daily"
        },
        "workflow_completed": {
            "email": false,
            "in_app": true,
            "only_failures": true  # Only notify on failures
        },
        "system_alert": {
            "email": true,
            "in_app": true,
            "min_severity": "warning"  # Only warning and above
        }
    }
    """
    
    # Quiet Hours
    quiet_hours_start = Column(Time)
    quiet_hours_end = Column(Time)
    quiet_hours_timezone = Column(String(50), default='Europe/Berlin')
    
    # Relationships
    user = relationship('User')
    
    def __repr__(self) -> str:
        return f"<NotificationPreference(id={self.id}, user_id={self.user_id})>"
    
    def should_notify(
        self,
        notification_type: NotificationType,
        channel: NotificationChannel,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if user should receive notification.
        
        Args:
            notification_type: Type of notification
            channel: Communication channel
            context: Additional context for conditional logic
        
        Returns:
            bool: True if notification should be sent
        """
        # Check if channel is globally enabled
        if channel == NotificationChannel.EMAIL and not self.email_enabled:
            return False
        if channel == NotificationChannel.IN_APP and not self.in_app_enabled:
            return False
        
        # Check type-specific preferences
        type_key = notification_type.value
        type_prefs = self.preferences.get(type_key, {})
        
        # Check if this channel is enabled for this type
        channel_key = channel.value
        if not type_prefs.get(channel_key, True):
            return False
        
        # Apply conditional logic based on context
        if context:
            # Example: Only notify if confidence below threshold
            if 'threshold' in type_prefs:
                threshold = type_prefs['threshold']
                if 'confidence_below' in threshold:
                    confidence = context.get('confidence', 100)
                    if confidence >= threshold['confidence_below']:
                        return False
            
            # Example: Only notify on failures
            if type_prefs.get('only_failures', False):
                if context.get('success', True):
                    return False
        
        # Check quiet hours
        if self.is_quiet_hours() and channel == NotificationChannel.EMAIL:
            return False
        
        return True
    
    def is_quiet_hours(self) -> bool:
        """Check if current time is within quiet hours"""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        
        from zoneinfo import ZoneInfo
        
        # Get current time in user's timezone
        tz = ZoneInfo(self.quiet_hours_timezone)
        now = datetime.now(tz).time()
        
        # Check if within quiet hours
        if self.quiet_hours_start < self.quiet_hours_end:
            # Normal case: e.g., 22:00 - 08:00
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:
            # Crosses midnight: e.g., 22:00 - 08:00
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end
    
    def get_preference(self, notification_type: str, channel: str) -> bool:
        """Get preference for specific type and channel"""
        type_prefs = self.preferences.get(notification_type, {})
        return type_prefs.get(channel, False)
    
    def set_preference(self, notification_type: str, channel: str, enabled: bool):
        """Set preference for specific type and channel"""
        if notification_type not in self.preferences:
            self.preferences[notification_type] = {}
        
        self.preferences[notification_type][channel] = enabled


class EmailQueue(BaseModel):
    """
    Queue for outgoing emails.
    
    Manages email delivery with retry logic, tracking, and error handling.
    """
    
    __tablename__ = 'email_queue'
    
    # Recipient
    to_address = Column(String(255), nullable=False, index=True)
    to_name = Column(String(255))
    cc_addresses = Column(ARRAY(Text))
    bcc_addresses = Column(ARRAY(Text))
    
    # Content
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)
    
    # Template
    template_id = Column(UUID(as_uuid=True), ForeignKey('email_templates.id'))
    template_data = Column(JSONB)
    
    # Attachments
    attachments = Column(JSONB)
    """
    Attachment structure:
    [
        {
            "filename": "invoice.pdf",
            "content_type": "application/pdf",
            "path": "/path/to/file",
            "size": 12345
        }
    ]
    """
    
    # Status
    status = Column(String, default=EmailStatus.QUEUED.value, nullable=False, index=True)
    
    # Delivery
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    next_attempt_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True
    )
    
    sent_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    
    # Metadata
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'))
    
    # Relationships
    template = relationship('EmailTemplate')
    user = relationship('User')
    document = relationship('Document')
    
    # Constraints
    __table_args__ = (
        CheckConstraint('attempts <= max_attempts', name='valid_attempts'),
    )
    
    def __repr__(self) -> str:
        return f"<EmailQueue(id={self.id}, to='{self.to_address}', status={self.status})>"
    
    def mark_sending(self):
        """Mark email as currently being sent"""
        self.status = EmailStatus.SENDING.value
        self.attempts += 1
    
    def mark_sent(self):
        """Mark email as successfully sent"""
        self.status = EmailStatus.SENT.value
        self.sent_at = datetime.utcnow()
        self.error_message = None
    
    def mark_failed(self, error_message: str):
        """Mark email as failed"""
        self.error_message = error_message
        
        if self.attempts >= self.max_attempts:
            self.status = EmailStatus.FAILED.value
        else:
            # Schedule retry with exponential backoff
            self.status = EmailStatus.QUEUED.value
            backoff_minutes = (2 ** self.attempts) * 5  # 5, 10, 20, 40 minutes
            self.next_attempt_at = datetime.utcnow() + timedelta(minutes=backoff_minutes)
    
    def mark_bounced(self):
        """Mark email as bounced"""
        self.status = EmailStatus.BOUNCED.value
    
    @classmethod
    def create_from_template(
        cls,
        template: 'EmailTemplate',
        to_address: str,
        template_data: Dict[str, Any],
        to_name: Optional[str] = None,
        user_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None
    ):
        """
        Create email from template.
        
        Args:
            template: Email template to use
            to_address: Recipient email
            template_data: Data to fill in template
            to_name: Recipient name
            user_id: Associated user
            document_id: Associated document
        
        Returns:
            EmailQueue instance
        """
        # Render template
        subject = template.render_subject(template_data)
        body_html = template.render_body_html(template_data)
        body_text = template.render_body_text(template_data) if template.body_text else None
        
        return cls(
            to_address=to_address,
            to_name=to_name,
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            template_id=template.id,
            template_data=template_data,
            user_id=user_id,
            document_id=document_id
        )


class EmailTemplate(BaseModel):
    """
    Reusable email templates.
    
    Defines templates with variable substitution for common email types.
    Uses Jinja2-style templating syntax.
    """
    
    __tablename__ = 'email_templates'
    
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    
    subject = Column(String(500), nullable=False)
    body_html = Column(Text, nullable=False)
    body_text = Column(Text)
    
    # Variables used in template
    variables = Column(ARRAY(Text))
    """
    List of available template variables:
    ['user_name', 'document_title', 'confidence', 'review_url']
    """
    
    # Categorization
    category = Column(String(100), index=True)
    
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    
    def __repr__(self) -> str:
        return f"<EmailTemplate(id={self.id}, name='{self.name}')>"
    
    def render_subject(self, data: Dict[str, Any]) -> str:
        """Render subject with template data"""
        from jinja2 import Template
        template = Template(self.subject)
        return template.render(**data)
    
    def render_body_html(self, data: Dict[str, Any]) -> str:
        """Render HTML body with template data"""
        from jinja2 import Template
        template = Template(self.body_html)
        return template.render(**data)
    
    def render_body_text(self, data: Dict[str, Any]) -> Optional[str]:
        """Render plain text body with template data"""
        if not self.body_text:
            return None
        
        from jinja2 import Template
        template = Template(self.body_text)
        return template.render(**data)
    
    def validate_data(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate template data has all required variables.
        
        Returns:
            tuple: (is_valid, missing_variables)
        """
        if not self.variables:
            return True, []
        
        missing = [var for var in self.variables if var not in data]
        return len(missing) == 0, missing
    
    def preview(self, sample_data: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        """
        Generate preview with sample data.
        
        Args:
            sample_data: Optional sample data, uses defaults if not provided
        
        Returns:
            dict with rendered subject and body
        """
        # Default sample data
        if sample_data is None:
            sample_data = {
                var: f"[{var}]"
                for var in (self.variables or [])
            }
        
        return {
            'subject': self.render_subject(sample_data),
            'body_html': self.render_body_html(sample_data),
            'body_text': self.render_body_text(sample_data) if self.body_text else None
        }

🛠️ NOTIFICATION UTILITIES
/backend/utils/notification_service.py
python"""
Notification service for sending notifications across channels
"""

from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from models.notifications import (
    Notification, NotificationPreference, EmailQueue, EmailTemplate
)
from models.auth import User
from models.documents import Document
from models.enums import NotificationType, NotificationChannel
from datetime import datetime
import uuid


class NotificationService:
    """
    Service for managing notifications across all channels.
    
    Handles notification creation, delivery, and user preferences.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def send_notification(
        self,
        user_id: UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        channels: List[NotificationChannel] = None,
        document_id: Optional[UUID] = None,
        link_url: Optional[str] = None,
        action_button_text: Optional[str] = None,
        action_button_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        email_template: Optional[str] = None,
        email_data: Optional[Dict[str, Any]] = None
    ):
        """
        Send notification through appropriate channels based on user preferences.
        
        Args:
            user_id: Recipient user ID
            notification_type: Type of notification
            title: Notification title
            message: Notification message
            channels: Channels to send through (None = check preferences)
            document_id: Associated document
            link_url: Link URL
            action_button_text: Action button text
            action_button_url: Action button URL
            metadata: Additional metadata
            email_template: Email template name (for email channel)
            email_data: Data for email template
        """
        # Get user preferences
        prefs = self.get_or_create_preferences(user_id)
        
        # Determine which channels to use
        if channels is None:
            channels = []
            context = metadata or {}
            
            if prefs.should_notify(notification_type, NotificationChannel.IN_APP, context):
                channels.append(NotificationChannel.IN_APP)
            
            if prefs.should_notify(notification_type, NotificationChannel.EMAIL, context):
                channels.append(NotificationChannel.EMAIL)
        
        # Send through each channel
        for channel in channels:
            if channel == NotificationChannel.IN_APP:
                self._send_in_app(
                    user_id=user_id,
                    notification_type=notification_type,
                    title=title,
                    message=message,
                    document_id=document_id,
                    link_url=link_url,
                    action_button_text=action_button_text,
                    action_button_url=action_button_url,
                    metadata=metadata
                )
            
            elif channel == NotificationChannel.EMAIL:
                self._send_email(
                    user_id=user_id,
                    template_name=email_template or 'generic_notification',
                    template_data=email_data or {
                        'title': title,
                        'message': message,
                        'link_url': link_url
                    },
                    document_id=document_id
                )
    
    def _send_in_app(
        self,
        user_id: UUID,
        notification_type: NotificationType,
        title: str,
        message: str,
        document_id: Optional[UUID] = None,
        link_url: Optional[str] = None,
        action_button_text: Optional[str] = None,
        action_button_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Send in-app notification"""
        notification = Notification(
            user_id=user_id,
            type=notification_type.value,
            title=title,
            message=message,
            document_id=document_id,
            link_url=link_url,
            action_button_text=action_button_text,
            action_button_url=action_button_url,
            metadata=metadata,
            delivered_at=datetime.utcnow()
        )
        
        self.db.add(notification)
        self.db.commit()
        self.db.refresh(notification)
        
        return notification
    
    def _send_email(
        self,
        user_id: UUID,
        template_name: str,
        template_data: Dict[str, Any],
        document_id: Optional[UUID] = None
    ):
        """Queue email for sending"""
        # Get user
        user = self.db.query(User).get(user_id)
        if not user:
            return None
        
        # Get template
        template = self.db.query(EmailTemplate).filter(
            EmailTemplate.name == template_name,
            EmailTemplate.is_active == True
        ).first()
        
        if not template:
            print(f"Email template '{template_name}' not found")
            return None
        
        # Create email
        email = EmailQueue.create_from_template(
            template=template,
            to_address=user.email,
            to_name=user.full_name,
            template_data=template_data,
            user_id=user_id,
            document_id=document_id
        )
        
        self.db.add(email)
        self.db.commit()
        self.db.refresh(email)
        
        return email
    
    def get_or_create_preferences(self, user_id: UUID) -> NotificationPreference:
        """Get user preferences or create with defaults"""
        prefs = self.db.query(NotificationPreference).filter(
            NotificationPreference.user_id == user_id
        ).first()
        
        if not prefs:
            prefs = NotificationPreference(user_id=user_id)
            self.db.add(prefs)
            self.db.commit()
            self.db.refresh(prefs)
        
        return prefs
    
    def get_unread_count(self, user_id: UUID) -> int:
        """Get count of unread notifications"""
        return self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).count()
    
    def get_recent_notifications(
        self,
        user_id: UUID,
        limit: int = 20,
        unread_only: bool = False
    ) -> List[Notification]:
        """Get recent notifications for user"""
        query = self.db.query(Notification).filter(
            Notification.user_id == user_id
        )
        
        if unread_only:
            query = query.filter(Notification.is_read == False)
        
        return query.order_by(
            Notification.created_at.desc()
        ).limit(limit).all()
    
    def mark_all_as_read(self, user_id: UUID):
        """Mark all notifications as read for user"""
        self.db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({
            'is_read': True,
            'read_at': datetime.utcnow()
        })
        
        self.db.commit()
    
    def delete_old_notifications(self, days: int = 30):
        """Delete notifications older than specified days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        deleted = self.db.query(Notification).filter(
            Notification.created_at < cutoff,
            Notification.is_read == True
        ).delete()
        
        self.db.commit()
        
        return deleted


class EmailService:
    """
    Service for processing email queue.
    
    Handles actual email sending with SMTP.
    """
    
    def __init__(self, db: Session, smtp_config: Dict[str, Any]):
        self.db = db
        self.smtp_config = smtp_config
    
    def process_queue(self, batch_size: int = 10):
        """
        Process pending emails in queue.
        
        Args:
            batch_size: Number of emails to process in one batch
        """
        # Get pending emails
        emails = self.db.query(EmailQueue).filter(
            EmailQueue.status == EmailStatus.QUEUED.value,
            EmailQueue.next_attempt_at <= datetime.utcnow()
        ).limit(batch_size).all()
        
        for email in emails:
            try:
                self.send_email(email)
            except Exception as e:
                print(f"Error sending email {email.id}: {e}")
    
    def send_email(self, email: EmailQueue):
        """
        Send a single email.
        
        Args:
            email: EmailQueue instance
        """
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        
        email.mark_sending()
        self.db.commit()
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = email.subject
            msg['From'] = self.smtp_config['from_address']
            msg['To'] = email.to_address
            
            if email.to_name:
                msg['To'] = f"{email.to_name} <{email.to_address}>"
            
            # CC and BCC
            if email.cc_addresses:
                msg['Cc'] = ', '.join(email.cc_addresses)
            
            # Add plain text
            if email.body_text:
                part1 = MIMEText(email.body_text, 'plain', 'utf-8')
                msg.attach(part1)
            
            # Add HTML
            part2 = MIMEText(email.body_html, 'html', 'utf-8')
            msg.attach(part2)
            
            # Add attachments
            if email.attachments:
                for attachment in email.attachments:
                    self._add_attachment(msg, attachment)
            
            # Send email
            with smtplib.SMTP(
                self.smtp_config['host'],
                self.smtp_config['port']
            ) as server:
                if self.smtp_config.get('use_tls', True):
                    server.starttls()
                
                if self.smtp_config.get('username'):
                    server.login(
                        self.smtp_config['username'],
                        self.smtp_config['password']
                    )
                
                # Build recipient list
                recipients = [email.to_address]
                if email.cc_addresses:
                    recipients.extend(email.cc_addresses)
                if email.bcc_addresses:
                    recipients.extend(email.bcc_addresses)
                
                server.send_message(msg, to_addrs=recipients)
            
            # Mark as sent
            email.mark_sent()
            self.db.commit()
            
        except smtplib.SMTPException as e:
            error_msg = f"SMTP error: {str(e)}"
            email.mark_failed(error_msg)
            self.db.commit()
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            email.mark_failed(error_msg)
            self.db.commit()
    
    def _add_attachment(self, msg: MIMEMultipart, attachment: Dict[str, Any]):
        """Add attachment to email message"""
        with open(attachment['path'], 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename={attachment["filename"]}'
        )
        
        msg.attach(part)

📝 NOTIFICATION EXAMPLES
/backend/examples/notification_examples.py
python"""
Examples of using notifications and email system
"""

from sqlalchemy.orm import Session
from models.notifications import (
    Notification, NotificationPreference, EmailQueue, EmailTemplate
)
from models.enums import NotificationType, NotificationChannel
from utils.notification_service import NotificationService, EmailService
from datetime import time
import uuid


# =============================================================================
# EXAMPLE 1: Send document processed notification
# =============================================================================

def send_document_processed_notification(db: Session, user_id: UUID, document):
    """
    Send notification when document processing is complete.
    """
    service = NotificationService(db)
    
    service.send_notification(
        user_id=user_id,
        notification_type=NotificationType.DOCUMENT_PROCESSED,
        title="Document Processed",
        message=f"Your document '{document.filename}' has been processed successfully.",
        document_id=document.id,
        link_url=f"/documents/{document.id}",
        action_button_text="View Document",
        action_button_url=f"/documents/{document.id}",
        metadata={
            'confidence': float(document.overall_confidence or 0),
            'document_type': document.document_type
        },
        email_template='document_processed',
        email_data={
            'user_name': 'John Doe',  # Would get from user object
            'document_title': document.filename,
            'confidence': float(document.overall_confidence or 0),
            'view_url': f"https://app.example.com/documents/{document.id}"
        }
    )
    
    print(f"Sent document processed notification for {document.filename}")


# =============================================================================
# EXAMPLE 2: Send review needed notification
# =============================================================================

def send_review_needed_notification(db: Session, user_id: UUID, document):
    """
    Send notification when document needs manual review.
    """
    service = NotificationService(db)
    
    confidence = float(document.overall_confidence or 0)
    reason = f"Low confidence ({confidence:.1f}%)" if confidence < 80 else "Manual review required"
    
    service.send_notification(
        user_id=user_id,
        notification_type=NotificationType.REVIEW_NEEDED,
        title="Document Review Required",
        message=f"Document '{document.filename}' needs your review. {reason}",
        document_id=document.id,
        link_url=f"/documents/{document.id}/review",
        action_button_text="Review Now",
        action_button_url=f"/documents/{document.id}/review",
        metadata={
            'confidence': confidence,
            'reason': reason
        },
        email_template='review_needed',
        email_data={
            'user_name': 'John Doe',
            'document_title': document.filename,
            'confidence': confidence,
            'reason': reason,
            'review_url': f"https://app.example.com/documents/{document.id}/review"
        }
    )


# =============================================================================
# EXAMPLE 3: Configure user notification preferences
# =============================================================================

def configure_user_preferences(db: Session, user_id: UUID):
    """
    Configure custom notification preferences for a user.
    """
    service = NotificationService(db)
    prefs = service.get_or_create_preferences(user_id)
    
    # Enable email for important notifications only
    prefs.email_enabled = True
    prefs.in_app_enabled = True
    
    # Set quiet hours (no emails between 22:00 and 08:00)
    prefs.quiet_hours_start = time(22, 0)
    prefs.quiet_hours_end = time(8, 0)
    prefs.quiet_hours_timezone = 'Europe/Berlin'
    
    # Customize per-type preferences
    prefs.preferences = {
        'document_processed': {
            'email': False,  # No email for routine processing
            'in_app': True
        },
        'review_needed': {
            'email': True,  # Email for reviews
            'in_app': True,
            'batch': False  # Don't batch, send immediately
        },
        'workflow_completed': {
            'email': False,
            'in_app': True,
            'only_failures': True  # Only notify on failures
        },
        'system_alert': {
            'email': True,
            'in_app': True,
            'min_severity': 'warning'
        }
    }
    
    db.commit()
    print(f"Updated preferences for user {user_id}")


# =============================================================================
# EXAMPLE 4: Create email templates
# =============================================================================

def create_email_templates(db: Session):
    """
    Create standard email templates.
    """
    
    # Document processed template
    template1 = EmailTemplate(
        name='document_processed',
        category='documents',
        description='Sent when document processing is complete',
        subject='Document "{{ document_title }}" processed',
        body_html='''
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Document Processed Successfully ✅</h2>
            <p>Hi {{ user_name }},</p>
            <p>Your document <strong>{{ document_title }}</strong> has been processed.</p>
            <p><strong>Confidence:</strong> {{ confidence }}%</p>
            <p>
                <a href="{{ view_url }}" 
                   style="background-color: #4CAF50; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Document
                </a>
            </p>
            <p style="color: #666; font-size: 12px;">
                This is an automated message from the OCR System.
            </p>
        </body>
        </html>
        ''',
        body_text='''
        Document Processed Successfully
        
        Hi {{ user_name }},
        
        Your document "{{ document_title }}" has been processed.
        
        Confidence: {{ confidence }}%
        
        View document: {{ view_url }}
        
        ---
        This is an automated message from the OCR System.
        ''',
        variables=['user_name', 'document_title', 'confidence', 'view_url'],
        is_active=True
    )
    
    # Review needed template
    template2 = EmailTemplate(
        name='review_needed',
        category='documents',
        description='Sent when document needs manual review',
        subject='Review Required: {{ document_title }}',
        body_html='''
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Document Review Required ⚠️</h2>
            <p>Hi {{ user_name }},</p>
            <p>Document <strong>{{ document_title }}</strong> needs your review.</p>
            <p><strong>Reason:</strong> {{ reason }}</p>
            <p><strong>Confidence:</strong> {{ confidence }}%</p>
            <p>
                <a href="{{ review_url }}" 
                   style="background-color: #FF9800; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    Review Now
                </a>
            </p>
            <p style="color: #666; font-size: 12px;">
                Please review as soon as possible to ensure accuracy.
            </p>
        </body>
        </html>
        ''',
        body_text='''
        Document Review Required
        
        Hi {{ user_name }},
        
        Document "{{ document_title }}" needs your review.
        
        Reason: {{ reason }}
        Confidence: {{ confidence }}%
        
        Review now: {{ review_url }}
        
        Please review as soon as possible to ensure accuracy.
        ''',
        variables=['user_name', 'document_title', 'confidence', 'reason', 'review_url'],
        is_active=True
    )
    
    # Workflow completed template
    template3 = EmailTemplate(
        name='workflow_completed',
        category='workflows',
        description='Sent when workflow execution completes',
        subject='Workflow {{ workflow_name }} {{ status }}',
        body_html='''
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2>Workflow {{ status_emoji }} {{ status }}</h2>
            <p>Hi {{ user_name }},</p>
            <p>Workflow <strong>{{ workflow_name }}</strong> has {{ status }}.</p>
            {% if error_message %}
            <p style="color: #f44336;"><strong>Error:</strong> {{ error_message }}</p>
            {% endif %}
            <p>
                <a href="{{ workflow_url }}" 
                   style="background-color: #2196F3; color: white; padding: 10px 20px; 
                          text-decoration: none; border-radius: 5px; display: inline-block;">
                    View Details
                </a>
            </p>
        </body>
        </html>
        ''',
        body_text='''
        Workflow {{ status }}
        
        Hi {{ user_name }},
        
        Workflow "{{ workflow_name }}" has {{ status }}.
        
        {% if error_message %}
        Error: {{ error_message }}
        {% endif %}
        
        View details: {{ workflow_url }}
        ''',
        variables=['user_name', 'workflow_name', 'status', 'status_emoji', 'error_message', 'workflow_url'],
        is_active=True
    )
    
    db.add_all([template1, template2, template3])
    db.commit()
    
    print("Created 3 email templates")


# =============================================================================
# EXAMPLE 5: Get user notifications
# =============================================================================

def get_user_notifications(db: Session, user_id: UUID):
    """
    Retrieve notifications for a user.
    """
    service = NotificationService(db)
    
    # Get unread count
    unread_count = service.get_unread_count(user_id)
    print(f"Unread notifications: {unread_count}")
    
    # Get recent notifications
    notifications = service.get_recent_notifications(
        user_id=user_id,
        limit=10,
        unread_only=False
    )
    
    print(f"\nRecent notifications:")
    for notif in notifications:
        status = "📌 Unread" if not notif.is_read else "✓ Read"
        print(f"{status} - {notif.title}")
        print(f"   {notif.message}")
        print(f"   Created: {notif.created_at}")
        print()


# =============================================================================
# EXAMPLE 6: Process email queue
# =============================================================================

def process_email_queue_example(db: Session):
    """
    Process pending emails in the queue.
    """
    smtp_config = {
        'host': 'smtp.gmail.com',
        'port': 587,
        'use_tls': True,
        'from_address': 'noreply@example.com',
        'username': 'your-email@gmail.com',
        'password': 'your-app-password'
    }
    
    email_service = EmailService(db, smtp_config)
    
    # Process up to 20 emails
    email_service.process_queue(batch_size=20)
    
    # Check queue status
    pending = db.query(EmailQueue).filter(
        EmailQueue.status == 'queued'
    ).count()
    
    failed = db.query(EmailQueue).filter(
        EmailQueue.status == 'failed'
    ).count()
    
    print(f"Email Queue Status:")
    print(f"  Pending: {pending}")
    print(f"  Failed: {failed}")


# =============================================================================
# EXAMPLE 7: Batch notifications
# =============================================================================

def send_batch_notifications(db: Session, user_ids: List[UUID], message: str):
    """
    Send same notification to multiple users.
    """
    service = NotificationService(db)
    
    for user_id in user_ids:
        service.send_notification(
            user_id=user_id,
            notification_type=NotificationType.INFO,
            title="System Announcement",
            message=message,
            channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            email_template='generic_notification',
            email_data={
                'user_name': 'User',  # Would get from user object
                'title': 'System Announcement',
                'message': message
            }
        )
    
    print(f"Sent batch notification to {len(user_ids)} users")


# =============================================================================
# EXAMPLE 8: Cleanup old notifications
# =============================================================================

def cleanup_old_notifications(db: Session):
    """
    Clean up old read notifications.
    """
    service = NotificationService(db)
    
    # Delete notifications older than 30 days
    deleted = service.delete_old_notifications(days=30)
    
    print(f"Deleted {deleted} old notifications")





📊 MONITORING & LOGGING MODELS
/backend/models/monitoring.py
python"""
System monitoring, logging, and audit models
"""

from sqlalchemy import (
    Column, String, Boolean, Text, ForeignKey,
    Integer, BigInteger, Float, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from .base import BaseModel
from .enums import ErrorSeverity
import json


class SystemMetric(BaseModel):
    """
    System performance metrics.
    
    Tracks CPU, memory, disk usage, API performance, and other
    system-level metrics for monitoring and capacity planning.
    """
    
    __tablename__ = 'system_metrics'
    
    # Metric Identity
    metric_name = Column(String(100), nullable=False, index=True)
    metric_type = Column(String(50), nullable=False, index=True)  # 'counter', 'gauge', 'histogram'
    
    # Time Bucket
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    bucket = Column(String(20), nullable=False, index=True)  # 'minute', 'hour', 'day'
    
    # Values
    value = Column(Float, nullable=False)
    count = Column(Integer, default=1, nullable=False)
    min_value = Column(Float)
    max_value = Column(Float)
    avg_value = Column(Float)
    
    # Labels/Tags
    labels = Column(JSONB)
    """
    Metric labels for filtering:
    {
        "host": "ocr-worker-01",
        "backend": "deepseek",
        "region": "eu-west-1",
        "environment": "production"
    }
    """
    
    # Constraints
    __table_args__ = (
        Index('idx_metrics_name_time', 'metric_name', 'timestamp'),
        Index('idx_metrics_name_bucket', 'metric_name', 'bucket'),
    )
    
    def __repr__(self) -> str:
        return f"<SystemMetric(name='{self.metric_name}', value={self.value}, timestamp={self.timestamp})>"
    
    @classmethod
    def record_gauge(
        cls,
        db_session,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ):
        """
        Record a gauge metric (point-in-time value).
        
        Examples: CPU usage, memory usage, queue length
        
        Args:
            db_session: Database session
            name: Metric name
            value: Current value
            labels: Optional labels
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        metric = cls(
            metric_name=name,
            metric_type='gauge',
            timestamp=timestamp,
            bucket='minute',
            value=value,
            labels=labels or {}
        )
        
        db_session.add(metric)
        db_session.commit()
        
        return metric
    
    @classmethod
    def record_counter(
        cls,
        db_session,
        name: str,
        increment: int = 1,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ):
        """
        Record a counter metric (cumulative count).
        
        Examples: requests processed, documents uploaded, errors
        
        Args:
            db_session: Database session
            name: Metric name
            increment: Value to add
            labels: Optional labels
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        metric = cls(
            metric_name=name,
            metric_type='counter',
            timestamp=timestamp,
            bucket='minute',
            value=increment,
            count=increment,
            labels=labels or {}
        )
        
        db_session.add(metric)
        db_session.commit()
        
        return metric
    
    @classmethod
    def record_histogram(
        cls,
        db_session,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
        timestamp: Optional[datetime] = None
    ):
        """
        Record a histogram metric (distribution of values).
        
        Examples: request duration, file size, processing time
        
        Args:
            db_session: Database session
            name: Metric name
            value: Observed value
            labels: Optional labels
            timestamp: Optional timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = datetime.utcnow()
        
        metric = cls(
            metric_name=name,
            metric_type='histogram',
            timestamp=timestamp,
            bucket='minute',
            value=value,
            min_value=value,
            max_value=value,
            avg_value=value,
            labels=labels or {}
        )
        
        db_session.add(metric)
        db_session.commit()
        
        return metric


class BackendMetric(BaseModel):
    """
    OCR backend performance metrics.
    
    Tracks performance of different OCR backends (DeepSeek, GOT-OCR, CPU-Surya)
    including accuracy, speed, and resource usage.
    """
    
    __tablename__ = 'backend_metrics'
    
    # Backend
    backend_type = Column(String(50), nullable=False, index=True)
    backend_version = Column(String(50))
    
    # Time Window
    metric_date = Column(Date, nullable=False, index=True)
    hour_of_day = Column(Integer)  # NULL = full day, 0-23 = specific hour
    
    # Performance Metrics
    total_requests = Column(Integer, default=0, nullable=False)
    successful_requests = Column(Integer, default=0, nullable=False)
    failed_requests = Column(Integer, default=0, nullable=False)
    
    # Timing (milliseconds)
    avg_processing_time_ms = Column(Integer)
    min_processing_time_ms = Column(Integer)
    max_processing_time_ms = Column(Integer)
    p50_processing_time_ms = Column(Integer)  # Median
    p95_processing_time_ms = Column(Integer)
    p99_processing_time_ms = Column(Integer)
    
    # Quality Metrics
    avg_confidence = Column(Float)
    avg_accuracy = Column(Float)  # If ground truth available
    
    # Resource Usage
    avg_vram_mb = Column(Integer)
    max_vram_mb = Column(Integer)
    avg_ram_mb = Column(Integer)
    max_ram_mb = Column(Integer)
    avg_cpu_usage = Column(Float)  # Percentage
    
    # Throughput
    total_pages_processed = Column(Integer, default=0, nullable=False)
    total_characters_extracted = Column(BigInteger, default=0, nullable=False)
    
    # Constraints
    __table_args__ = (
        CheckConstraint('hour_of_day IS NULL OR (hour_of_day BETWEEN 0 AND 23)', name='valid_backend_hour'),
    )
    
    def __repr__(self) -> str:
        return f"<BackendMetric(backend='{self.backend_type}', date={self.metric_date})>"
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_requests == 0:
            return 0.0
        return (self.successful_requests / self.total_requests) * 100
    
    @classmethod
    def aggregate_metrics(
        cls,
        db_session,
        backend_type: str,
        date: Date,
        hour: Optional[int] = None
    ):
        """
        Aggregate backend metrics for a time period.
        
        This would typically be called by a background job.
        """
        from models.documents import ProcessingJob
        from sqlalchemy import func
        
        # Query processing jobs for this backend and time period
        query = db_session.query(
            func.count(ProcessingJob.id).label('total'),
            func.count(func.nullif(ProcessingJob.success, False)).label('successful'),
            func.avg(ProcessingJob.processing_time_ms).label('avg_time'),
            func.min(ProcessingJob.processing_time_ms).label('min_time'),
            func.max(ProcessingJob.processing_time_ms).label('max_time'),
            func.avg(ProcessingJob.vram_used_mb).label('avg_vram'),
            func.max(ProcessingJob.vram_used_mb).label('max_vram')
        ).filter(
            ProcessingJob.backend_type == backend_type,
            func.date(ProcessingJob.created_at) == date
        )
        
        if hour is not None:
            query = query.filter(
                func.extract('hour', ProcessingJob.created_at) == hour
            )
        
        result = query.first()
        
        if result.total == 0:
            return None
        
        # Create or update metric
        metric = db_session.query(cls).filter(
            cls.backend_type == backend_type,
            cls.metric_date == date,
            cls.hour_of_day == hour
        ).first()
        
        if not metric:
            metric = cls(
                backend_type=backend_type,
                metric_date=date,
                hour_of_day=hour
            )
            db_session.add(metric)
        
        metric.total_requests = result.total
        metric.successful_requests = result.successful or 0
        metric.failed_requests = result.total - (result.successful or 0)
        metric.avg_processing_time_ms = int(result.avg_time) if result.avg_time else None
        metric.min_processing_time_ms = result.min_time
        metric.max_processing_time_ms = result.max_time
        metric.avg_vram_mb = int(result.avg_vram) if result.avg_vram else None
        metric.max_vram_mb = result.max_vram
        
        db_session.commit()
        
        return metric


class ErrorLog(BaseModel):
    """
    Application error log.
    
    Captures exceptions, errors, and warnings throughout the application
    with full context for debugging.
    """
    
    __tablename__ = 'error_logs'
    
    # Error Details
    severity = Column(String, nullable=False, index=True)
    error_type = Column(String(255), nullable=False, index=True)
    error_message = Column(Text, nullable=False)
    
    # Stack Trace
    stack_trace = Column(Text)
    
    # Context
    context = Column(JSONB)
    """
    Additional error context:
    {
        "user_id": "uuid",
        "document_id": "uuid",
        "job_id": "uuid",
        "request_id": "uuid",
        "url": "/api/documents/upload",
        "method": "POST",
        "function": "process_document",
        "line": 123,
        "file": "processing.py"
    }
    """
    
    # Request Information
    request_path = Column(String(500))
    request_method = Column(String(10))
    request_data = Column(JSONB)
    
    # User Context
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), index=True)
    ip_address = Column(INET)
    user_agent = Column(Text)
    
    # Related Entities
    document_id = Column(UUID(as_uuid=True), ForeignKey('documents.id'))
    job_id = Column(UUID(as_uuid=True), ForeignKey('processing_jobs.id'))
    
    # Resolution
    resolved = Column(Boolean, default=False, nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    resolution_notes = Column(Text)
    
    # Occurrence Count (for duplicate detection)
    occurrence_count = Column(Integer, default=1, nullable=False)
    first_seen_at = Column(DateTime(timezone=True), server_default='now()')
    last_seen_at = Column(DateTime(timezone=True), server_default='now()')
    
    # Relationships
    user = relationship('User', foreign_keys=[user_id])
    resolver = relationship('User', foreign_keys=[resolved_by])
    
    # Indexes
    __table_args__ = (
        Index('idx_error_severity_time', 'severity', 'created_at'),
        Index('idx_error_type_resolved', 'error_type', 'resolved'),
    )
    
    def __repr__(self) -> str:
        return f"<ErrorLog(id={self.id}, type='{self.error_type}', severity={self.severity})>"
    
    def mark_resolved(self, user_id: UUID, notes: Optional[str] = None):
        """Mark error as resolved"""
        self.resolved = True
        self.resolved_at = datetime.utcnow()
        self.resolved_by = user_id
        self.resolution_notes = notes
    
    @classmethod
    def log_error(
        cls,
        db_session,
        severity: ErrorSeverity,
        error_type: str,
        error_message: str,
        stack_trace: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None,
        job_id: Optional[UUID] = None,
        request_path: Optional[str] = None,
        request_method: Optional[str] = None,
        ip_address: Optional[str] = None
    ):
        """
        Log an error to the database.
        
        Implements duplicate detection - if same error already exists,
        increments occurrence count instead of creating new record.
        """
        # Check for duplicate (same type and message in last hour)
        cutoff = datetime.utcnow() - timedelta(hours=1)
        existing = db_session.query(cls).filter(
            cls.error_type == error_type,
            cls.error_message == error_message,
            cls.created_at >= cutoff,
            cls.resolved == False
        ).first()
        
        if existing:
            # Update existing error
            existing.occurrence_count += 1
            existing.last_seen_at = datetime.utcnow()
            db_session.commit()
            return existing
        
        # Create new error
        error = cls(
            severity=severity.value,
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            context=context or {},
            user_id=user_id,
            document_id=document_id,
            job_id=job_id,
            request_path=request_path,
            request_method=request_method,
            ip_address=ip_address
        )
        
        db_session.add(error)
        db_session.commit()
        db_session.refresh(error)
        
        return error


class AuditLog(BaseModel):
    """
    Audit trail for user actions and system events.
    
    Tracks all important actions for security, compliance, and debugging.
    Immutable - records are never updated or deleted.
    """
    
    __tablename__ = 'audit_logs'
    
    # Actor
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.id'), index=True)
    impersonator_id = Column(UUID(as_uuid=True), ForeignKey('users.id'))  # If admin is impersonating
    
    # Action
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50), nullable=False, index=True)
    resource_id = Column(UUID(as_uuid=True), index=True)
    
    # Details
    description = Column(Text, nullable=False)
    
    # Changes (for update actions)
    changes = Column(JSONB)
    """
    Before/after values:
    {
        "before": {"status": "pending", "confidence": 75},
        "after": {"status": "approved", "confidence": 75}
    }
    """
    
    # Context
    ip_address = Column(INET)
    user_agent = Column(Text)
    request_id = Column(String(100))
    
    # Additional Metadata
    metadata = Column(JSONB)
    """
    Additional context:
    {
        "api_key_id": "uuid",
        "session_id": "uuid",
        "reason": "User requested deletion",
        "bulk_operation": true,
        "affected_count": 5
    }
    """
    
    # Relationships
    user = relationship('User', foreign_keys=[user_id])
    impersonator = relationship('User', foreign_keys=[impersonator_id])
    
    # Indexes
    __table_args__ = (
        Index('idx_audit_user_time', 'user_id', 'created_at'),
        Index('idx_audit_resource', 'resource_type', 'resource_id'),
        Index('idx_audit_action_time', 'action', 'created_at'),
    )
    
    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action}', resource={self.resource_type})>"
    
    @classmethod
    def log_action(
        cls,
        db_session,
        user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID,
        description: str,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        impersonator_id: Optional[UUID] = None
    ):
        """
        Log an audit event.
        
        Common actions:
        - create, read, update, delete
        - login, logout, password_reset
        - export, import, sync
        - approve, reject, review
        - assign, unassign
        - enable, disable
        """
        log = cls(
            user_id=user_id,
            impersonator_id=impersonator_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            changes=changes,
            metadata=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        db_session.add(log)
        db_session.commit()
        db_session.refresh(log)
        
        return log


class HealthCheck(BaseModel):
    """
    System health check results.
    
    Stores results of periodic health checks for different system components.
    """
    
    __tablename__ = 'health_checks'
    
    # Component
    component = Column(String(100), nullable=False, index=True)
    
    # Status
    status = Column(String(20), nullable=False, index=True)  # 'healthy', 'degraded', 'down'
    
    # Metrics
    response_time_ms = Column(Integer)
    
    # Details
    details = Column(JSONB)
    """
    Component-specific details:
    {
        "database": {
            "connections": 15,
            "max_connections": 100,
            "slow_queries": 3
        },
        "redis": {
            "memory_used_mb": 256,
            "memory_max_mb": 512,
            "connected_clients": 10
        },
        "storage": {
            "disk_used_gb": 450,
            "disk_total_gb": 1000,
            "disk_usage_percent": 45
        }
    }
    """
    
    # Error
    error_message = Column(Text)
    
    def __repr__(self) -> str:
        return f"<HealthCheck(component='{self.component}', status={self.status})>"
    
    @classmethod
    def check_database(cls, db_session):
        """Check database health"""
        import time
        
        start = time.time()
        
        try:
            # Simple query to test connection
            db_session.execute('SELECT 1')
            
            response_time = int((time.time() - start) * 1000)
            
            # Get connection pool stats
            engine = db_session.bind
            pool = engine.pool
            
            details = {
                'connections_in_use': pool.checkedout(),
                'connections_available': pool.size() - pool.checkedout(),
                'pool_size': pool.size()
            }
            
            status = 'healthy'
            if response_time > 1000:
                status = 'degraded'
            
            health = cls(
                component='database',
                status=status,
                response_time_ms=response_time,
                details=details
            )
            
            db_session.add(health)
            db_session.commit()
            
            return health
            
        except Exception as e:
            health = cls(
                component='database',
                status='down',
                error_message=str(e)
            )
            
            db_session.add(health)
            db_session.commit()
            
            return health
    
    @classmethod
    def check_storage(cls, db_session):
        """Check file storage health"""
        import shutil
        
        try:
            # Check disk usage
            total, used, free = shutil.disk_usage('/')
            
            usage_percent = (used / total) * 100
            
            details = {
                'disk_total_gb': round(total / (1024**3), 2),
                'disk_used_gb': round(used / (1024**3), 2),
                'disk_free_gb': round(free / (1024**3), 2),
                'disk_usage_percent': round(usage_percent, 2)
            }
            
            status = 'healthy'
            if usage_percent > 90:
                status = 'down'
            elif usage_percent > 80:
                status = 'degraded'
            
            health = cls(
                component='storage',
                status=status,
                details=details
            )
            
            db_session.add(health)
            db_session.commit()
            
            return health
            
        except Exception as e:
            health = cls(
                component='storage',
                status='down',
                error_message=str(e)
            )
            
            db_session.add(health)
            db_session.commit()
            
            return health

🛠️ MONITORING UTILITIES
/backend/utils/monitoring_service.py
python"""
Monitoring and metrics collection service
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from models.monitoring import (
    SystemMetric, BackendMetric, ErrorLog, AuditLog, HealthCheck
)
from models.enums import ErrorSeverity
from datetime import datetime, timedelta
import traceback
import uuid


class MonitoringService:
    """
    Service for collecting and querying system metrics and logs.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # =========================================================================
    # METRICS
    # =========================================================================
    
    def record_request(
        self,
        endpoint: str,
        method: str,
        duration_ms: int,
        status_code: int,
        user_id: Optional[UUID] = None
    ):
        """Record API request metric"""
        SystemMetric.record_counter(
            db_session=self.db,
            name='api.requests.total',
            labels={
                'endpoint': endpoint,
                'method': method,
                'status': str(status_code)
            }
        )
        
        SystemMetric.record_histogram(
            db_session=self.db,
            name='api.request.duration',
            value=duration_ms,
            labels={
                'endpoint': endpoint,
                'method': method
            }
        )
    
    def record_document_upload(
        self,
        file_size: int,
        mime_type: str,
        processing_time_ms: int
    ):
        """Record document upload metrics"""
        SystemMetric.record_counter(
            db_session=self.db,
            name='documents.uploaded.total',
            labels={'mime_type': mime_type}
        )
        
        SystemMetric.record_histogram(
            db_session=self.db,
            name='documents.upload.size',
            value=file_size,
            labels={'mime_type': mime_type}
        )
        
        SystemMetric.record_histogram(
            db_session=self.db,
            name='documents.upload.duration',
            value=processing_time_ms,
            labels={'mime_type': mime_type}
        )
    
    def record_ocr_processing(
        self,
        backend: str,
        success: bool,
        duration_ms: int,
        confidence: Optional[float] = None,
        page_count: int = 1
    ):
        """Record OCR processing metrics"""
        status = 'success' if success else 'failure'
        
        SystemMetric.record_counter(
            db_session=self.db,
            name='ocr.processing.total',
            labels={
                'backend': backend,
                'status': status
            }
        )
        
        SystemMetric.record_histogram(
            db_session=self.db,
            name='ocr.processing.duration',
            value=duration_ms,
            labels={'backend': backend}
        )
        
        if confidence is not None:
            SystemMetric.record_histogram(
                db_session=self.db,
                name='ocr.confidence',
                value=confidence,
                labels={'backend': backend}
            )
        
        SystemMetric.record_counter(
            db_session=self.db,
            name='ocr.pages.processed',
            increment=page_count,
            labels={'backend': backend}
        )
    
    def get_metrics(
        self,
        metric_name: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> List[SystemMetric]:
        """Query metrics"""
        if end_time is None:
            end_time = datetime.utcnow()
        
        query = self.db.query(SystemMetric).filter(
            SystemMetric.metric_name == metric_name,
            SystemMetric.timestamp >= start_time,
            SystemMetric.timestamp <= end_time
        )
        
        if labels:
            # Filter by labels (JSONB containment)
            query = query.filter(
                SystemMetric.labels.contains(labels)
            )
        
        return query.order_by(SystemMetric.timestamp).all()
    
    # =========================================================================
    # ERROR LOGGING
    # =========================================================================
    
    def log_exception(
        self,
        exception: Exception,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None,
        document_id: Optional[UUID] = None
    ):
        """Log an exception with full stack trace"""
        error_type = type(exception).__name__
        error_message = str(exception)
        stack_trace = traceback.format_exc()
        
        return ErrorLog.log_error(
            db_session=self.db,
            severity=severity,
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace,
            context=context,
            user_id=user_id,
            document_id=document_id
        )
    
    def log_error(
        self,
        error_type: str,
        error_message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Optional[Dict[str, Any]] = None
    ):
        """Log a custom error"""
        return ErrorLog.log_error(
            db_session=self.db,
            severity=severity,
            error_type=error_type,
            error_message=error_message,
            context=context
        )
    
    def get_recent_errors(
        self,
        severity: Optional[ErrorSeverity] = None,
        resolved: bool = False,
        limit: int = 50
    ) -> List[ErrorLog]:
        """Get recent errors"""
        query = self.db.query(ErrorLog).filter(
            ErrorLog.resolved == resolved
        )
        
        if severity:
            query = query.filter(ErrorLog.severity == severity.value)
        
        return query.order_by(
            ErrorLog.created_at.desc()
        ).limit(limit).all()
    
    def get_error_summary(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """Get summary of errors in last N hours"""
        from sqlalchemy import func
        
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        
        # Count by severity
        severity_counts = self.db.query(
            ErrorLog.severity,
            func.count(ErrorLog.id)
        ).filter(
            ErrorLog.created_at >= cutoff
        ).group_by(ErrorLog.severity).all()
        
        # Count by type (top 10)
        type_counts = self.db.query(
            ErrorLog.error_type,
            func.count(ErrorLog.id)
        ).filter(
            ErrorLog.created_at >= cutoff
        ).group_by(
            ErrorLog.error_type
        ).order_by(
            func.count(ErrorLog.id).desc()
        ).limit(10).all()
        
        # Unresolved count
        unresolved = self.db.query(ErrorLog).filter(
            ErrorLog.resolved == False,
            ErrorLog.created_at >= cutoff
        ).count()
        
        return {
            'time_window_hours': hours,
            'by_severity': {sev: count for sev, count in severity_counts},
            'top_types': [
                {'type': error_type, 'count': count}
                for error_type, count in type_counts
            ],
            'unresolved_count': unresolved
        }
    
    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================
    
    def audit_log(
        self,
        user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID,
        description: str,
        changes: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ):
        """Create audit log entry"""
        return AuditLog.log_action(
            db_session=self.db,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            changes=changes,
            metadata=metadata,
            ip_address=ip_address
        )
    
    def get_audit_trail(
        self,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        action: Optional[str] = None,
        limit: int = 100
    ) -> List[AuditLog]:
        """Query audit trail"""
        query = self.db.query(AuditLog)
        
        if resource_type:
            query = query.filter(AuditLog.resource_type == resource_type)
        
        if resource_id:
            query = query.filter(AuditLog.resource_id == resource_id)
        
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        
        if action:
            query = query.filter(AuditLog.action == action)
        
        return query.order_by(
            AuditLog.created_at.desc()
        ).limit(limit).all()
    
    # =========================================================================
    # HEALTH CHECKS
    # =========================================================================
    
    def check_system_health(self) -> Dict[str, Any]:
        """Perform comprehensive system health check"""
        results = {}
        
        # Check database
        db_health = HealthCheck.check_database(self.db)
        results['database'] = {
            'status': db_health.status,
            'response_time_ms': db_health.response_time_ms,
            'details': db_health.details
        }
        
        # Check storage
        storage_health = HealthCheck.check_storage(self.db)
        results['storage'] = {
            'status': storage_health.status,
            'details': storage_health.details
        }
        
        # Overall status
        statuses = [r['status'] for r in results.values()]
        if 'down' in statuses:
            overall = 'down'
        elif 'degraded' in statuses:
            overall = 'degraded'
        else:
            overall = 'healthy'
        
        return {
            'overall_status': overall,
            'components': results,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    # =========================================================================
    # BACKEND METRICS
    # =========================================================================
    
    def get_backend_performance(
        self,
        backend: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """Get backend performance summary"""
        from sqlalchemy import func
        
        start_date = (datetime.utcnow() - timedelta(days=days)).date()
        
        metrics = self.db.query(BackendMetric).filter(
            BackendMetric.backend_type == backend,
            BackendMetric.metric_date >= start_date,
            BackendMetric.hour_of_day.is_(None)  # Daily aggregates only
        ).all()
        
        if not metrics:
            return {}
        
        total_requests = sum(m.total_requests for m in metrics)
        successful = sum(m.successful_requests for m in metrics)
        
        return {
            'backend': backend,
            'period_days': days,
            'total_requests': total_requests,
            'successful_requests': successful,
            'failed_requests': total_requests - successful,
            'success_rate': (successful / total_requests * 100) if total_requests > 0 else 0,
            'avg_processing_time_ms': int(sum(
                m.avg_processing_time_ms for m in metrics if m.avg_processing_time_ms
            ) / len([m for m in metrics if m.avg_processing_time_ms])) if metrics else 0,
            'avg_confidence': round(sum(
                m.avg_confidence for m in metrics if m.avg_confidence
            ) / len([m for m in metrics if m.avg_confidence]), 2) if metrics else 0,
            'total_pages_processed': sum(m.total_pages_processed for m in metrics)
        }
   





⚙️ CONFIG & SETTINGS MODELS (FINALE!)
/backend/models/config.py
python"""
System configuration and settings models
"""

from sqlalchemy import (
    Column, String, Boolean, Text, ForeignKey,
    Integer, Float, CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime, time
from typing import Dict, Any, Optional, List
from .base import BaseModel
from .enums import TaskFrequency
import json


class SystemConfig(BaseModel):
    """
    Global system configuration.
    
    Stores system-wide settings like email configuration,
    storage settings, OCR backend preferences, etc.
    """
    
    __tablename__ = 'system_config'
    
    # Config Key
    key = Column(String(100), nullable=False, unique=True, index=True)
    
    # Value (polymorphic storage)
    value_string = Column(Text)
    value_int = Column(Integer)
    value_float = Column(Float)
    value_bool = Column(Boolean)
    value_json = Column(JSONB)
    
    # Metadata
    category = Column(String(50), nullable=False, index=True)
    description = Column(Text)
    
    # Value Type
    data_type = Column(String(20), nullable=False)  # 'string', 'int', 'float', 'bool', 'json'
    
    # Validation
    validation_regex = Column(String(500))
    allowed_values = Column(ARRAY(Text))  # For enum-like values
    min_value = Column(Float)
    max_value = Column(Float)
    
    # Access Control
    is_public = Column(Boolean, default=False, nullable=False)  # Can be read by regular users
    is_sensitive = Column(Boolean, default=False, nullable=False)  # Should be encrypted/masked
    
    # Change Tracking
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    def __repr__(self) -> str:
        return f"<SystemConfig(key='{self.key}', category='{self.category}')>"
    
    def get_value(self) -> Any:
        """Get typed value"""
        if self.data_type == 'string':
            return self.value_string
        elif self.data_type == 'int':
            return self.value_int
        elif self.data_type == 'float':
            return self.value_float
        elif self.data_type == 'bool':
            return self.value_bool
        elif self.data_type == 'json':
            return self.value_json
        return None
    
    def set_value(self, value: Any):
        """Set typed value"""
        # Clear all value fields
        self.value_string = None
        self.value_int = None
        self.value_float = None
        self.value_bool = None
        self.value_json = None
        
        # Set appropriate field
        if self.data_type == 'string':
            self.value_string = str(value)
        elif self.data_type == 'int':
            self.value_int = int(value)
        elif self.data_type == 'float':
            self.value_float = float(value)
        elif self.data_type == 'bool':
            self.value_bool = bool(value)
        elif self.data_type == 'json':
            self.value_json = value if isinstance(value, dict) else json.loads(value)
    
    def validate_value(self, value: Any) -> tuple[bool, Optional[str]]:
        """
        Validate value against constraints.
        
        Returns:
            tuple: (is_valid, error_message)
        """
        # Type check
        try:
            if self.data_type == 'int':
                value = int(value)
            elif self.data_type == 'float':
                value = float(value)
            elif self.data_type == 'bool':
                value = bool(value)
        except (ValueError, TypeError) as e:
            return False, f"Invalid type: {str(e)}"
        
        # Allowed values check
        if self.allowed_values and str(value) not in self.allowed_values:
            return False, f"Value must be one of: {', '.join(self.allowed_values)}"
        
        # Range check for numeric values
        if self.data_type in ('int', 'float'):
            if self.min_value is not None and value < self.min_value:
                return False, f"Value must be >= {self.min_value}"
            if self.max_value is not None and value > self.max_value:
                return False, f"Value must be <= {self.max_value}"
        
        # Regex check for strings
        if self.data_type == 'string' and self.validation_regex:
            import re
            if not re.match(self.validation_regex, str(value)):
                return False, "Value does not match required format"
        
        return True, None
    
    @classmethod
    def get_config(cls, db_session, key: str, default: Any = None) -> Any:
        """Get configuration value by key"""
        config = db_session.query(cls).filter(cls.key == key).first()
        if config:
            return config.get_value()
        return default
    
    @classmethod
    def set_config(
        cls,
        db_session,
        key: str,
        value: Any,
        user_id: Optional[UUID] = None
    ) -> 'SystemConfig':
        """Set configuration value"""
        config = db_session.query(cls).filter(cls.key == key).first()
        
        if not config:
            raise ValueError(f"Configuration key '{key}' does not exist")
        
        # Validate
        is_valid, error = config.validate_value(value)
        if not is_valid:
            raise ValueError(f"Invalid value: {error}")
        
        # Update
        config.set_value(value)
        config.updated_by = user_id
        
        db_session.commit()
        
        return config


class FeatureFlag(BaseModel):
    """
    Feature flags for gradual rollouts and A/B testing.
    
    Allows enabling/disabling features for specific users, teams,
    or percentages of the user base.
    """
    
    __tablename__ = 'feature_flags'
    
    # Flag Identity
    name = Column(String(100), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Status
    is_enabled = Column(Boolean, default=False, nullable=False, index=True)
    
    # Rollout Strategy
    rollout_percentage = Column(Integer, default=0, nullable=False)  # 0-100
    """
    Percentage of users to enable for.
    0 = disabled for all
    100 = enabled for all
    50 = enabled for 50% (deterministic based on user ID hash)
    """
    
    # Targeting
    enabled_for_users = Column(ARRAY(UUID))  # Specific user IDs
    enabled_for_teams = Column(ARRAY(UUID))  # Specific team IDs
    enabled_for_roles = Column(ARRAY(Text))  # Specific role names
    
    # Environment Filters
    environments = Column(ARRAY(Text))  # ['development', 'staging', 'production']
    
    # Conditions (JSONLogic)
    conditions = Column(JSONB)
    """
    Advanced conditions:
    {
        "and": [
            {">=": [{"var": "user.created_days_ago"}, 30]},
            {"in": [{"var": "user.subscription"}, ["pro", "enterprise"]]}
        ]
    }
    """
    
    # Metadata
    category = Column(String(50), index=True)  # 'ui', 'backend', 'integration', etc.
    
    # Lifecycle
    start_date = Column(DateTime(timezone=True))
    end_date = Column(DateTime(timezone=True))
    
    # Change Tracking
    updated_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    # Constraints
    __table_args__ = (
        CheckConstraint('rollout_percentage BETWEEN 0 AND 100', name='valid_percentage'),
    )
    
    def __repr__(self) -> str:
        return f"<FeatureFlag(name='{self.name}', enabled={self.is_enabled})>"
    
    def is_enabled_for_user(
        self,
        user_id: UUID,
        user_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if feature is enabled for specific user.
        
        Args:
            user_id: User ID to check
            user_context: Additional user context for condition evaluation
        
        Returns:
            bool: True if feature is enabled for this user
        """
        # Global flag check
        if not self.is_enabled:
            return False
        
        # Date range check
        now = datetime.utcnow()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        
        # Explicit user list
        if self.enabled_for_users and user_id in self.enabled_for_users:
            return True
        
        # Check conditions
        if self.conditions and user_context:
            try:
                from json_logic import jsonLogic
                context = {'user': user_context}
                if not jsonLogic(self.conditions, context):
                    return False
            except Exception as e:
                print(f"Error evaluating feature flag conditions: {e}")
                return False
        
        # Rollout percentage (deterministic hash-based)
        if self.rollout_percentage > 0:
            import hashlib
            
            # Hash user ID to get deterministic value between 0-99
            hash_input = f"{self.name}:{str(user_id)}"
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            bucket = hash_value % 100
            
            if bucket < self.rollout_percentage:
                return True
        
        return False
    
    def enable_for_user(self, user_id: UUID):
        """Add user to enabled list"""
        if not self.enabled_for_users:
            self.enabled_for_users = []
        if user_id not in self.enabled_for_users:
            self.enabled_for_users.append(user_id)
    
    def disable_for_user(self, user_id: UUID):
        """Remove user from enabled list"""
        if self.enabled_for_users and user_id in self.enabled_for_users:
            self.enabled_for_users.remove(user_id)


class ScheduledTask(BaseModel):
    """
    Scheduled background tasks.
    
    Manages cron-like scheduled tasks for cleanup, reports,
    backups, synchronization, etc.
    """
    
    __tablename__ = 'scheduled_tasks'
    
    # Task Identity
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text)
    
    # Task Configuration
    task_type = Column(String(100), nullable=False, index=True)
    task_config = Column(JSONB, nullable=False)
    """
    Task configuration by type:
    
    cleanup_old_documents:
    {
        "days_old": 90,
        "document_types": ["temporary"],
        "delete_permanently": false
    }
    
    generate_report:
    {
        "report_type": "monthly_summary",
        "recipients": ["admin@example.com"],
        "format": "pdf"
    }
    
    sync_integration:
    {
        "integration_id": "uuid",
        "direction": "export",
        "auto_retry": true
    }
    
    backup_database:
    {
        "destination": "s3://backups/",
        "compression": "gzip",
        "retention_days": 30
    }
    
    aggregate_metrics:
    {
        "metrics": ["backend_performance", "user_activity"],
        "period": "hourly"
    }
    """
    
    # Schedule
    frequency = Column(String, nullable=False, index=True)
    cron_expression = Column(String(100))  # For custom schedules
    """
    Cron examples:
    - "0 0 * * *" = Daily at midnight
    - "0 */6 * * *" = Every 6 hours
    - "0 9 * * 1" = Every Monday at 9 AM
    - "*/15 * * * *" = Every 15 minutes
    """
    
    timezone = Column(String(50), default='UTC', nullable=False)
    
    # Execution Window
    start_time = Column(Time)  # Earliest time to run
    end_time = Column(Time)  # Latest time to run
    
    # Status
    is_enabled = Column(Boolean, default=True, nullable=False, index=True)
    
    # Execution Tracking
    last_run_at = Column(DateTime(timezone=True))
    next_run_at = Column(DateTime(timezone=True), index=True)
    last_run_success = Column(Boolean)
    last_run_duration_ms = Column(Integer)
    last_run_error = Column(Text)
    
    # Statistics
    total_runs = Column(Integer, default=0, nullable=False)
    successful_runs = Column(Integer, default=0, nullable=False)
    failed_runs = Column(Integer, default=0, nullable=False)
    
    # Retry Configuration
    retry_on_failure = Column(Boolean, default=True, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    retry_delay_minutes = Column(Integer, default=5, nullable=False)
    
    # Notifications
    notify_on_failure = Column(Boolean, default=True, nullable=False)
    notification_emails = Column(ARRAY(Text))
    
    # Change Tracking
    created_by = Column(UUID(as_uuid=True), ForeignKey('users.id'))
    
    def __repr__(self) -> str:
        return f"<ScheduledTask(name='{self.name}', frequency={self.frequency})>"
    
    def calculate_next_run(self) -> datetime:
        """Calculate next run time based on schedule"""
        from croniter import croniter
        from zoneinfo import ZoneInfo
        
        tz = ZoneInfo(self.timezone)
        base_time = datetime.now(tz)
        
        if self.cron_expression:
            # Use cron expression
            cron = croniter(self.cron_expression, base_time)
            next_run = cron.get_next(datetime)
        else:
            # Use frequency
            freq = TaskFrequency(self.frequency)
            
            if freq == TaskFrequency.MINUTELY:
                next_run = base_time + timedelta(minutes=1)
            elif freq == TaskFrequency.HOURLY:
                next_run = base_time + timedelta(hours=1)
            elif freq == TaskFrequency.DAILY:
                next_run = base_time + timedelta(days=1)
            elif freq == TaskFrequency.WEEKLY:
                next_run = base_time + timedelta(weeks=1)
            elif freq == TaskFrequency.MONTHLY:
                # Approximate - same day next month
                next_run = base_time.replace(month=base_time.month + 1)
            else:
                next_run = base_time + timedelta(days=1)
        
        # Apply execution window constraints
        if self.start_time or self.end_time:
            run_time = next_run.time()
            
            if self.start_time and run_time < self.start_time:
                # Move to start_time
                next_run = next_run.replace(
                    hour=self.start_time.hour,
                    minute=self.start_time.minute,
                    second=0
                )
            
            if self.end_time and run_time > self.end_time:
                # Move to next day at start_time
                next_run = next_run + timedelta(days=1)
                if self.start_time:
                    next_run = next_run.replace(
                        hour=self.start_time.hour,
                        minute=self.start_time.minute,
                        second=0
                    )
        
        return next_run
    
    def mark_executed(
        self,
        success: bool,
        duration_ms: int,
        error_message: Optional[str] = None
    ):
        """Update task after execution"""
        self.last_run_at = datetime.utcnow()
        self.last_run_success = success
        self.last_run_duration_ms = duration_ms
        self.last_run_error = error_message
        
        self.total_runs += 1
        if success:
            self.successful_runs += 1
        else:
            self.failed_runs += 1
        
        # Calculate next run
        self.next_run_at = self.calculate_next_run()
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.total_runs == 0:
            return 0.0
        return (self.successful_runs / self.total_runs) * 100


class SystemParameter(BaseModel):
    """
    Key-value store for system parameters.
    
    Flexible storage for various system-level data that doesn't
    fit other models (e.g., last sync timestamps, temporary flags, etc.).
    """
    
    __tablename__ = 'system_parameters'
    
    # Key
    key = Column(String(255), nullable=False, unique=True, index=True)
    
    # Value
    value = Column(Text, nullable=False)
    
    # Metadata
    description = Column(Text)
    category = Column(String(50), index=True)
    
    # Expiry
    expires_at = Column(DateTime(timezone=True), index=True)
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('key', name='uq_parameter_key'),
    )
    
    def __repr__(self) -> str:
        return f"<SystemParameter(key='{self.key}')>"
    
    def is_expired(self) -> bool:
        """Check if parameter has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @classmethod
    def get(cls, db_session, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get parameter value"""
        param = db_session.query(cls).filter(cls.key == key).first()
        
        if not param:
            return default
        
        if param.is_expired():
            db_session.delete(param)
            db_session.commit()
            return default
        
        return param.value
    
    @classmethod
    def set(
        cls,
        db_session,
        key: str,
        value: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        expires_at: Optional[datetime] = None
    ):
        """Set parameter value"""
        param = db_session.query(cls).filter(cls.key == key).first()
        
        if param:
            param.value = value
            param.description = description
            param.category = category
            param.expires_at = expires_at
        else:
            param = cls(
                key=key,
                value=value,
                description=description,
                category=category,
                expires_at=expires_at
            )
            db_session.add(param)
        
        db_session.commit()
        return param
    
    @classmethod
    def delete(cls, db_session, key: str):
        """Delete parameter"""
        param = db_session.query(cls).filter(cls.key == key).first()
        if param:
            db_session.delete(param)
            db_session.commit()
    
    @classmethod
    def cleanup_expired(cls, db_session) -> int:
        """Delete all expired parameters"""
        deleted = db_session.query(cls).filter(
            cls.expires_at.isnot(None),
            cls.expires_at <= datetime.utcnow()
        ).delete()
        
        db_session.commit()
        return deleted

🛠️ CONFIG UTILITIES
/backend/utils/config_service.py
python"""
Configuration management service
"""

from typing import Any, Optional, Dict, List
from sqlalchemy.orm import Session
from models.config import SystemConfig, FeatureFlag, ScheduledTask, SystemParameter
from models.auth import User
from datetime import datetime
import uuid


class ConfigService:
    """
    Service for managing system configuration.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    # =========================================================================
    # SYSTEM CONFIG
    # =========================================================================
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return SystemConfig.get_config(self.db, key, default)
    
    def set_config(self, key: str, value: Any, user_id: Optional[UUID] = None):
        """Set configuration value"""
        return SystemConfig.set_config(self.db, key, value, user_id)
    
    def get_configs_by_category(self, category: str) -> List[SystemConfig]:
        """Get all configs in a category"""
        return self.db.query(SystemConfig).filter(
            SystemConfig.category == category
        ).all()
    
    def initialize_default_configs(self):
        """Initialize default system configurations"""
        defaults = [
            # Email Settings
            {
                'key': 'email.smtp_host',
                'value_string': 'smtp.gmail.com',
                'data_type': 'string',
                'category': 'email',
                'description': 'SMTP server hostname',
                'is_public': False
            },
            {
                'key': 'email.smtp_port',
                'value_int': 587,
                'data_type': 'int',
                'category': 'email',
                'description': 'SMTP server port',
                'min_value': 1,
                'max_value': 65535
            },
            {
                'key': 'email.from_address',
                'value_string': 'noreply@example.com',
                'data_type': 'string',
                'category': 'email',
                'description': 'Default sender email address'
            },
            
            # OCR Settings
            {
                'key': 'ocr.default_backend',
                'value_string': 'deepseek',
                'data_type': 'string',
                'category': 'ocr',
                'description': 'Default OCR backend',
                'allowed_values': ['deepseek', 'got_ocr', 'cpu_surya']
            },
            {
                'key': 'ocr.confidence_threshold',
                'value_float': 80.0,
                'data_type': 'float',
                'category': 'ocr',
                'description': 'Minimum confidence threshold for auto-approval',
                'min_value': 0.0,
                'max_value': 100.0
            },
            {
                'key': 'ocr.max_retries',
                'value_int': 3,
                'data_type': 'int',
                'category': 'ocr',
                'description': 'Maximum retry attempts for failed OCR jobs',
                'min_value': 0,
                'max_value': 10
            },
            
            # Storage Settings
            {
                'key': 'storage.max_file_size_mb',
                'value_int': 50,
                'data_type': 'int',
                'category': 'storage',
                'description': 'Maximum upload file size in MB',
                'min_value': 1,
                'max_value': 1000
            },
            {
                'key': 'storage.allowed_extensions',
                'value_json': ['.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff'],
                'data_type': 'json',
                'category': 'storage',
                'description': 'Allowed file extensions'
            },
            
            # Security Settings
            {
                'key': 'security.session_timeout_hours',
                'value_int': 24,
                'data_type': 'int',
                'category': 'security',
                'description': 'Session timeout in hours',
                'min_value': 1,
                'max_value': 168
            },
            {
                'key': 'security.max_login_attempts',
                'value_int': 5,
                'data_type': 'int',
                'category': 'security',
                'description': 'Maximum failed login attempts before lockout',
                'min_value': 3,
                'max_value': 10
            },
            {
                'key': 'security.require_2fa',
                'value_bool': False,
                'data_type': 'bool',
                'category': 'security',
                'description': 'Require 2FA for all users'
            },
            
            # Performance Settings
            {
                'key': 'performance.max_concurrent_jobs',
                'value_int': 10,
                'data_type': 'int',
                'category': 'performance',
                'description': 'Maximum concurrent OCR processing jobs',
                'min_value': 1,
                'max_value': 100
            },
            {
                'key': 'performance.cache_enabled',
                'value_bool': True,
                'data_type': 'bool',
                'category': 'performance',
                'description': 'Enable result caching'
            }
        ]
        
        for config_data in defaults:
            existing = self.db.query(SystemConfig).filter(
                SystemConfig.key == config_data['key']
            ).first()
            
            if not existing:
                config = SystemConfig(**config_data)
                self.db.add(config)
        
        self.db.commit()
        print(f"Initialized {len(defaults)} default configurations")
    
    # =========================================================================
    # FEATURE FLAGS
    # =========================================================================
    
    def is_feature_enabled(
        self,
        feature_name: str,
        user_id: Optional[UUID] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if feature is enabled"""
        flag = self.db.query(FeatureFlag).filter(
            FeatureFlag.name == feature_name
        ).first()
        
        if not flag:
            return False
        
        if user_id:
            return flag.is_enabled_for_user(user_id, user_context)
        
        return flag.is_enabled
    
    def create_feature_flag(
        self,
        name: str,
        display_name: str,
        description: str,
        category: str = 'general',
        enabled: bool = False,
        rollout_percentage: int = 0
    ) -> FeatureFlag:
        """Create new feature flag"""
        flag = FeatureFlag(
            name=name,
            display_name=display_name,
            description=description,
            category=category,
            is_enabled=enabled,
            rollout_percentage=rollout_percentage
        )
        
        self.db.add(flag)
        self.db.commit()
        self.db.refresh(flag)
        
        return flag
    
    def update_feature_rollout(
        self,
        feature_name: str,
        rollout_percentage: int,
        user_id: Optional[UUID] = None
    ):
        """Update feature rollout percentage"""
        flag = self.db.query(FeatureFlag).filter(
            FeatureFlag.name == feature_name
        ).first()
        
        if not flag:
            raise ValueError(f"Feature flag '{feature_name}' not found")
        
        flag.rollout_percentage = rollout_percentage
        flag.updated_by = user_id
        
        self.db.commit()
    
    # =========================================================================
    # SCHEDULED TASKS
    # =========================================================================
    
    def get_pending_tasks(self) -> List[ScheduledTask]:
        """Get tasks that are due to run"""
        return self.db.query(ScheduledTask).filter(
            ScheduledTask.is_enabled == True,
            ScheduledTask.next_run_at <= datetime.utcnow()
        ).all()
    
    def create_scheduled_task(
        self,
        name: str,
        task_type: str,
        task_config: Dict[str, Any],
        frequency: str,
        cron_expression: Optional[str] = None,
        user_id: Optional[UUID] = None
    ) -> ScheduledTask:
        """Create new scheduled task"""
        task = ScheduledTask(
            name=name,
            task_type=task_type,
            task_config=task_config,
            frequency=frequency,
            cron_expression=cron_expression,
            created_by=user_id
        )
        
        # Calculate first run
        task.next_run_at = task.calculate_next_run()
        
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        
        return task
    
    def execute_task(self, task: ScheduledTask) -> bool:
        """Execute a scheduled task"""
        print(f"Executing task: {task.name}")
        
        start_time = datetime.utcnow()
        
        try:
            # Task execution logic would go here
            # This would be implemented per task_type
            
            # For now, simulate success
            success = True
            error_message = None
            
        except Exception as e:
            success = False
            error_message = str(e)
            print(f"Task failed: {error_message}")
        
        finally:
            # Calculate duration
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Update task
            task.mark_executed(
                success=success,
                duration_ms=duration_ms,
                error_message=error_message
            )
            
            self.db.commit()
        
        return success

📝 CONFIG EXAMPLES
/backend/examples/config_examples.py
python"""
Examples of using configuration and feature flags
"""

from sqlalchemy.orm import Session
from models.config import SystemConfig, FeatureFlag, ScheduledTask, SystemParameter
from models.enums import TaskFrequency
from utils.config_service import ConfigService
from datetime import datetime, timedelta
import uuid


# =============================================================================
# EXAMPLE 1: Initialize system configuration
# =============================================================================

def initialize_system_config(db: Session):
    """
    Initialize system with default configurations.
    """
    service = ConfigService(db)
    service.initialize_default_configs()
    
    print("System configuration initialized")


# =============================================================================
# EXAMPLE 2: Read and update configuration
# =============================================================================

def manage_config_example(db: Session):
    """
    Read and update configuration values.
    """
    service = ConfigService(db)
    
    # Get configuration
    smtp_host = service.get_config('email.smtp_host')
    print(f"SMTP Host: {smtp_host}")
    
    confidence_threshold = service.get_config('ocr.confidence_threshold', default=80.0)
    print(f"Confidence Threshold: {confidence_threshold}%")
    
    # Update configuration
    service.set_config(
        key='ocr.confidence_threshold',
        value=85.0,
        user_id=uuid.uuid4()  # Would be actual admin user ID
    )
    
    print("Updated confidence threshold to 85%")
    
    # Get all configs in category
    email_configs = service.get_configs_by_category('email')
    print(f"\nEmail Configurations:")
    for config in email_configs:
        print(f"  {config.key}: {config.get_value()}")


# =============================================================================
# EXAMPLE 3: Create and manage feature flags
# =============================================================================

def create_feature_flags(db: Session):
    """
    Create feature flags for gradual rollouts.
    """
    service = ConfigService(db)
    
    # New UI redesign - start with 10% rollout
    ui_redesign = service.create_feature_flag(
        name='ui_redesign_2025',
        display_name='UI Redesign 2025',
        description='New modern user interface design',
        category='ui',
        enabled=True,
        rollout_percentage=10
    )
    
    print(f"Created feature flag: {ui_redesign.name}")
    print(f"  Rollout: {ui_redesign.rollout_percentage}%")
    
    # Advanced OCR features - enabled for specific users only
    advanced_ocr = service.create_feature_flag(
        name='advanced_ocr_features',
        display_name='Advanced OCR Features',
        description='ML-powered extraction and validation',
        category='backend',
        enabled=True,
        rollout_percentage=0  # Manual enable only
    )
    
    # Add specific users to beta
    beta_user_id = uuid.uuid4()  # Example user
    advanced_ocr.enable_for_user(beta_user_id)
    db.commit()
    
    print(f"\nCreated feature flag: {advanced_ocr.name}")
    print(f"  Beta users: {len(advanced_ocr.enabled_for_users or [])}")


# =============================================================================
# EXAMPLE 4: Check feature flag for user
# =============================================================================

def check_feature_for_user(db: Session, user_id: UUID):
    """
    Check if feature is enabled for specific user.
    """
    service = ConfigService(db)
    
    # Check UI redesign (percentage-based rollout)
    is_enabled = service.is_feature_enabled(
        feature_name='ui_redesign_2025',
        user_id=user_id
    )
    
    print(f"UI Redesign enabled for user: {is_enabled}")
    
    # Check with user context (for conditional features)
    user_context = {
        'subscription': 'pro',
        'created_days_ago': 45,
        'total_documents': 150
    }
    
    is_enabled = service.is_feature_enabled(
        feature_name='advanced_ocr_features',
        user_id=user_id,
        user_context=user_context
    )
    
    print(f"Advanced OCR enabled for user: {is_enabled}")


# =============================================================================
# EXAMPLE 5: Gradual feature rollout
# =============================================================================

def gradual_feature_rollout(db: Session):
    """
    Demonstrate gradual feature rollout strategy.
    """
    service = ConfigService(db)
    admin_id = uuid.uuid4()
    
    # Week 1: 5% rollout
    service.update_feature_rollout(
        feature_name='ui_redesign_2025',
        rollout_percentage=5,
        user_id=admin_id
    )
    print("Week 1: Rolled out to 5% of users")
    
    # Week 2: 25% rollout (if no issues)
    service.update_feature_rollout(
        feature_name='ui_redesign_2025',
        rollout_percentage=25,
        user_id=admin_id
    )
    print("Week 2: Rolled out to 25% of users")
    
    # Week 3: 50% rollout
    service.update_feature_rollout(
        feature_name='ui_redesign_2025',
        rollout_percentage=50,
        user_id=admin_id
    )
    print("Week 3: Rolled out to 50% of users")
    
    # Week 4: 100% rollout (full release)
    service.update_feature_rollout(
        feature_name='ui_redesign_2025',
        rollout_percentage=100,
        user_id=admin_id
    )
    print("Week 4: Full rollout to all users!")


# =============================================================================
# EXAMPLE 6: Create scheduled tasks
# =============================================================================

def create_scheduled_tasks(db: Session):
    """
    Create various scheduled background tasks.
    """
    service = ConfigService(db)
    admin_id = uuid.uuid4()
    
    # Daily cleanup of old documents
    cleanup_task = service.create_scheduled_task(
        name='cleanup_old_documents',
        task_type='cleanup_old_documents',
        task_config={
            'days_old': 90,
            'document_types': ['temporary', 'draft'],
            'delete_permanently': False
        },
        frequency=TaskFrequency.DAILY.value,
        cron_expression='0 2 * * *',  # 2 AM daily
        user_id=admin_id
    )
    
    print(f"Created task: {cleanup_task.name}")
    print(f"  Next run: {cleanup_task.next_run_at}")
    
    # Hourly metrics aggregation
    metrics_task = service.create_scheduled_task(
        name='aggregate_metrics',
        task_type='aggregate_metrics',
        task_config={
            'metrics': ['backend_performance', 'user_activity'],
            'period': 'hourly'
        },
        frequency=TaskFrequency.HOURLY.value,
        cron_expression='0 * * * *',  # Every hour
        user_id=admin_id
    )
    
    print(f"\nCreated task: {metrics_task.name}")
    print(f"  Frequency: {metrics_task.frequency}")
    
    # Weekly backup
    backup_task = service.create_scheduled_task(
        name='weekly_database_backup',
        task_type='backup_database',
        task_config={
            'destination': 's3://backups/',
            'compression': 'gzip',
            'retention_days': 30
        },
        frequency=TaskFrequency.WEEKLY.value,
        cron_expression='0 3 * * 0',  # Sundays at 3 AM
        user_id=admin_id
    )
    
    print(f"\nCreated task: {backup_task.name}")
    print(f"  Cron: {backup_task.cron_expression}")


# =============================================================================
# EXAMPLE 7: Execute scheduled tasks
# =============================================================================

def execute_pending_tasks(db: Session):
    """
    Execute all pending scheduled tasks.
    """
    service = ConfigService(db)
    
    # Get pending tasks
    pending_tasks = service.get_pending_tasks()
    
    print(f"Found {len(pending_tasks)} pending tasks")
    
    for task in pending_tasks:
        print(f"\nExecuting: {task.name}")
        
        success = service.execute_task(task)
        
        if success:
            print(f"  ✅ Success (took {task.last_run_duration_ms}ms)")
        else:
            print(f"  ❌ Failed: {task.last_run_error}")
        
        print(f"  Next run: {task.next_run_at}")


# =============================================================================
# EXAMPLE 8: System parameters (key-value store)
# =============================================================================

def use_system_parameters(db: Session):
    """
    Use system parameters for flexible storage.
    """
    
    # Store last sync timestamp
    SystemParameter.set(
        db_session=db,
        key='last_integration_sync',
        value=datetime.utcnow().isoformat(),
        description='Last time integration sync ran',
        category='sync'
    )
    
    # Store temporary maintenance flag
    SystemParameter.set(
        db_session=db,
        key='maintenance_mode',
        value='false',
        description='System maintenance mode flag',
        category='system',
        expires_at=datetime.utcnow() + timedelta(hours=2)
    )
    
    # Read parameters
    last_sync = SystemParameter.get(db, 'last_integration_sync')
    print(f"Last sync: {last_sync}")
    
    maintenance_mode = SystemParameter.get(db, 'maintenance_mode', default='false')
    print(f"Maintenance mode: {maintenance_mode}")
    
    # Cleanup expired parameters
    deleted = SystemParameter.cleanup_expired(db)
    print(f"\nCleaned up {deleted} expired parameters")


# =============================================================================
# EXAMPLE 9: Get task statistics
# =============================================================================

def get_task_statistics(db: Session):
    """
    Get statistics for all scheduled tasks.
    """
    
    tasks = db.query(ScheduledTask).all()
    
    print("Scheduled Task Statistics")
    print("=" * 70)
    
    for task in tasks:
        print(f"\n{task.name}")
        print(f"  Status: {'✅ Enabled' if task.is_enabled else '❌ Disabled'}")
        print(f"  Frequency: {task.frequency}")
        print(f"  Total Runs: {task.total_runs}")
        print(f"  Success Rate: {task.success_rate:.1f}%")
        
        if task.last_run_at:
            print(f"  Last Run: {task.last_run_at}")
            print(f"  Last Status: {'✅ Success' if task.last_run_success else '❌ Failed'}")
            
            if task.last_run_error:
                print(f"  Last Error: {task.last_run_error}")
        
        print(f"  Next Run: {task.next_run_at}")


# =============================================================================
# EXAMPLE 10: Feature flag with conditions
# =============================================================================

def create_conditional_feature_flag(db: Session):
    """
    Create feature flag with advanced conditions.
    """
    
    flag = FeatureFlag(
        name='premium_features',
        display_name='Premium Features',
        description='Advanced features for premium users',
        category='features',
        is_enabled=True,
        rollout_percentage=0,  # Condition-based only
        conditions={
            "or": [
                {"==": [{"var": "user.subscription"}, "pro"]},
                {"==": [{"var": "user.subscription"}, "enterprise"]},
                {
                    "and": [
                        {"==": [{"var": "user.subscription"}, "trial"]},
                        {">=": [{"var": "user.trial_days_remaining"}, 7]}
                    ]
                }
            ]
        }
    )
    
    db.add(flag)
    db.commit()
    
    print(f"Created conditional feature flag: {flag.name}")
    print("Enabled for:")
    print("  - Pro users")
    print("  - Enterprise users")
    print("  - Trial users with 7+ days remaining")

🎉 FINALE: Complete Model Initialization
/backend/init_db.py
python"""
Complete database initialization script
"""

from sqlalchemy.orm import Session
from database import engine, Base, init_db
from models import *  # Import all models
from utils.config_service import ConfigService
from models.enums import *
import uuid


def initialize_database():
    """
    Initialize database with all tables and default data.
    """
    
    print("=" * 70)
    print("DATABASE INITIALIZATION")
    print("=" * 70)
    
    # Create all tables
    print("\n1. Creating database tables...")
    init_db()
    print("   ✅ All tables created")
    
    # Create session
    from database import SessionLocal
    db = SessionLocal()
    
    try:
        # Initialize configurations
        print("\n2. Initializing system configuration...")
        config_service = ConfigService(db)
        config_service.initialize_default_configs()
        print("   ✅ Configuration initialized")
        
        # Create default roles
        print("\n3. Creating default roles...")
        create_default_roles(db)
        print("   ✅ Roles created")
        
        # Create admin user
        print("\n4. Creating admin user...")
        create_admin_user(db)
        print("   ✅ Admin user created")
        
        # Create email templates
        print("\n5. Creating email templates...")
        create_default_email_templates(db)
        print("   ✅ Email templates created")
        
        # Create default categories
        print("\n6. Creating document categories...")
        create_default_categories(db)
        print("   ✅ Categories created")
        
        print("\n" + "=" * 70)
        print("DATABASE INITIALIZATION COMPLETE!")
        print("=" * 70)
        
    finally:
        db.close()


def create_default_roles(db: Session):
    """Create default user roles"""
    from models.auth import Role, Permission
    
    # Define permissions
    permissions_data = [
        ('documents.read', 'documents', 'read', 'View documents'),
        ('documents.create', 'documents', 'create', 'Upload documents'),
        ('documents.update', 'documents', 'update', 'Edit documents'),
        ('documents.delete', 'documents', 'delete', 'Delete documents'),
        ('users.manage', 'users', 'manage', 'Manage users'),
        ('system.admin', 'system', 'admin', 'System administration'),
    ]
    
    permissions = {}
    for name, resource, action, desc in permissions_data:
        perm = Permission(
            name=name,
            resource=resource,
            action=action,
            description=desc
        )
        db.add(perm)
        permissions[name] = perm
    
    db.flush()
    
    # Create roles
    admin_role = Role(
        name='admin',
        display_name='Administrator',
        description='Full system access',
        level=100,
        is_system=True
    )
    admin_role.permissions.extend(permissions.values())
    
    user_role = Role(
        name='user',
        display_name='User',
        description='Regular user',
        level=10,
        is_system=True
    )
    user_role.permissions.extend([
        permissions['documents.read'],
        permissions['documents.create'],
        permissions['documents.update']
    ])
    
    reviewer_role = Role(
        name='reviewer',
        display_name='Reviewer',
        description='Document reviewer',
        level=20,
        is_system=True
    )
    reviewer_role.permissions.extend([
        permissions['documents.read'],
        permissions['documents.update']
    ])
    
    db.add_all([admin_role, user_role, reviewer_role])
    db.commit()


def create_admin_user(db: Session):
    """Create default admin user"""
    from models.auth import User
    
    admin = User(
        email='admin@example.com',
        username='admin',
        first_name='System',
        last_name='Administrator',
        is_active=True,
        is_verified=True
    )
    
    admin.set_password('admin123')  # Change in production!
    
    # Assign admin role
    from models.auth import Role
    admin_role = db.query(Role).filter(Role.name == 'admin').first()
    if admin_role:
        admin.roles.append(admin_role)
    
    db.add(admin)
    db.commit()
    
    print(f"   Admin credentials: admin@example.com / admin123")


def create_default_email_templates(db: Session):
    """Create default email templates"""
    from models.notifications import EmailTemplate
    
    templates = [
        EmailTemplate(
            name='generic_notification',
            category='notifications',
            description='Generic notification email',
            subject='{{ title }}',
            body_html='<html><body><h2>{{ title }}</h2><p>{{ message }}</p></body></html>',
            body_text='{{ title }}\n\n{{ message }}',
            variables=['title', 'message'],
            is_active=True
        )
    ]
    
    db.add_all(templates)
    db.commit()


def create_default_categories(db: Session):
    """Create default document categories"""
    from models.documents import Category
    
    categories = [
        Category(
            name='Invoices',
            slug='invoices',
            path='/invoices',
            icon='receipt',
            color='#4CAF50'
        ),
        Category(
            name='Contracts',
            slug='contracts',
            path='/contracts',
            icon='description',
            color='#2196F3'
        ),
        Category(
            name='Delivery Notes',
            slug='delivery-notes',
            path='/delivery-notes',
            icon='local_shipping',
            color='#FF9800'
        )
    ]
    
    db.add_all(categories)
    db.commit()


if __name__ == '__main__':
    initialize_database()
