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

from datetime import datetime, timezone, date, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from decimal import Decimal
import uuid

from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Date, Time, Boolean, Float, Numeric, Text, JSON, ForeignKey, Index, Table, CheckConstraint, UniqueConstraint, text, Enum as SQLAlchemyEnum, event
from sqlalchemy.dialects.postgresql import UUID, JSONB, TSVECTOR
from sqlalchemy.types import TypeDecorator
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import relationship, declarative_base, backref, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
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
    """Document type classification - 15 Types fuer Enterprise-Klassifikation.

    Phase 1.2: Erweitert um Bank Statement, Tax Document, Dunning Letter,
    Purchase Order, Credit Note.
    """
    # === RECHNUNGSWESEN ===
    INVOICE = "invoice"              # Rechnung (Ein-/Ausgang)
    CREDIT_NOTE = "credit_note"      # Gutschrift
    RECEIPT = "receipt"              # Quittung/Kassenbon
    DUNNING_LETTER = "dunning"       # Mahnung (Zahlungserinnerung bis 3. Mahnung)

    # === BESTELLWESEN ===
    ORDER = "order"                  # Bestellung (allgemein)
    PURCHASE_ORDER = "purchase_order"  # Bestellauftrag (formell)
    OFFER = "offer"                  # Angebot
    DELIVERY_NOTE = "delivery_note"  # Lieferschein

    # === VERTRAEGE & DOKUMENTE ===
    CONTRACT = "contract"            # Vertrag
    FORM = "form"                    # Formular
    LETTER = "letter"                # Brief/Korrespondenz
    REPORT = "report"                # Bericht

    # === FINANZ & STEUER ===
    BANK_STATEMENT = "bank_statement"  # Kontoauszug
    TAX_DOCUMENT = "tax_document"      # Steuerdokument (USt-Voranmeldung, etc.)

    # === SONSTIGES ===
    OTHER = "other"                  # Sonstiges (bekannt aber nicht kategorisiert)
    UNKNOWN = "unknown"              # Unbekannt (Klassifikation fehlgeschlagen)


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

    # GoBD Archivierung (Feature 02)
    is_archived = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="GoBD: Dokument ist revisionssicher archiviert"
    )
    archived_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="GoBD: Zeitpunkt der Archivierung"
    )

    # Multi-Company Support (Multi-Tenant Isolation)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung fuer Multi-Company Isolation"
    )

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

    # =========================================================================
    # Document Chain (Auftragsketten-Tracking)
    # Angebot -> Auftrag -> Lieferschein -> Rechnung -> Gutschrift
    # =========================================================================
    chain_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Auftragsketten-ID (z.B. CHAIN-2026-00001)"
    )
    chain_position = Column(
        Integer,
        nullable=True,
        comment="Position in Kette: 1=Angebot, 2=Auftrag, 3=Lieferschein, 4=Rechnung, 5=Gutschrift"
    )
    chain_root_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Erstes Dokument der Kette (Root)"
    )

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
    company = relationship("Company", back_populates="documents")
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

    # GoBD Archive Relationship (Feature 02)
    archive = relationship(
        "DocumentArchive",
        back_populates="document",
        uselist=False,
        cascade="all, delete-orphan"
    )

    # Document Chain Relationship (self-referential)
    chain_root_document = relationship(
        "Document",
        remote_side="Document.id",
        foreign_keys=[chain_root_document_id],
        backref="chain_children",
        uselist=False
    )

    # OCR Self-Learning Feedbacks (Phase 1.3)
    ocr_feedbacks = relationship(
        "OCRCorrectionFeedback",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="dynamic"
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
        # GoBD Archivierung (Feature 02)
        Index("ix_documents_is_archived", "is_archived"),
        # Document Chain (Auftragsketten-Tracking)
        Index("ix_documents_chain_id", "chain_id"),
        Index("ix_documents_chain_position", "chain_id", "chain_position"),
        Index("ix_documents_chain_root", "chain_root_document_id"),
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
    # MFA Rate Limiting (Brute-Force-Schutz)
    totp_failed_attempts = Column(Integer, default=0, nullable=False,
                                  comment="Anzahl fehlgeschlagener TOTP-Versuche")
    totp_lockout_until = Column(DateTime(timezone=True), nullable=True,
                               comment="Sperre bis zu diesem Zeitpunkt")

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

    # GoBD: Steuerberater/Pruefer zeitlich begrenzter Zugang
    access_until = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Zeitliche Begrenzung des Zugangs (fuer Steuerberater/Pruefer)"
    )
    invited_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", use_alter=True, name="fk_user_invited_by"),
        nullable=True,
        comment="Benutzer, der diesen Account eingeladen hat"
    )
    invited_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Einladung"
    )
    access_scope = Column(
        CrossDBJSON,
        nullable=True,
        comment="Eingeschraenkter Zugriff (z.B. nur bestimmte Firmen, Zeitraeume)"
    )

    # Relationships
    documents = relationship("Document", back_populates="owner", foreign_keys="Document.owner_id")
    api_keys = relationship("APIKey", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    deactivated_by = relationship("User", remote_side="User.id", foreign_keys=[deactivated_by_id])
    invited_by = relationship(
        "User",
        remote_side="User.id",
        foreign_keys=[invited_by_id],
        backref="invited_users"
    )
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
    result_data = Column(CrossDBJSON, default=dict)
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

    # Cancellation support (Export Improvements Task 3)
    is_cancelled = Column(Boolean, default=False)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="batch_jobs")
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_batch_jobs_status", "status"),
        Index("ix_batch_jobs_user_id", "user_id"),
        Index("ix_batch_jobs_created_at", "created_at"),
    )


class ScheduledExport(Base):
    """Scheduled exports for automated recurring exports.

    Allows users to configure automatic exports on a schedule (cron-based).
    Part of Export Improvements Task 4.
    """
    __tablename__ = "scheduled_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Schedule (Cron-Format)
    cron_expression = Column(String(100), nullable=False)  # "0 8 * * 1" = Montag 08:00
    timezone = Column(String(50), default="Europe/Berlin")

    # Export-Konfiguration
    export_type = Column(String(50), nullable=False)  # "documents", "invoices", "datev"
    export_format = Column(String(20), nullable=False)  # "csv", "excel", "zip", "json"
    filter_config = Column(CrossDBJSON, nullable=True)  # Date range, categories, tags, etc.
    include_text = Column(Boolean, default=True)
    include_metadata = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(20), nullable=True)  # success, failed, partial
    last_run_job_id = Column(UUID(as_uuid=True), ForeignKey("batch_jobs.id"), nullable=True)

    # Notification
    notify_email = Column(Boolean, default=True)
    notify_on_failure_only = Column(Boolean, default=False)
    notification_email = Column(String(255), nullable=True)  # Override user email

    # Statistics
    total_runs = Column(Integer, default=0)
    successful_runs = Column(Integer, default=0)
    failed_runs = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="scheduled_exports")
    last_run_job = relationship("BatchJob", foreign_keys=[last_run_job_id])

    # Indexes
    __table_args__ = (
        Index("ix_scheduled_exports_user_id", "user_id"),
        Index("ix_scheduled_exports_is_active", "is_active"),
        Index("ix_scheduled_exports_next_run_at", "next_run_at"),
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

    SECURITY:
    - Diese Tabelle sollte mit DB-Level-Triggers gegen UPDATE/DELETE geschützt sein (siehe Migration 017).
    - Multi-Tenant Isolation via company_id (Migration 134)
    """
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    # Multi-Tenant Support (SECURITY FIX - Migration 134)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,  # NULL fuer System-Events (Migrations, Cron-Jobs)
        index=True
    )

    # Action details
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(UUID(as_uuid=True))

    # Request details
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    request_method = Column(String(10))
    request_path = Column(String(255))

    # Success/Error tracking
    success = Column(Boolean, default=True, nullable=False)
    error_message = Column(String(2000), nullable=True)

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
    company = relationship("Company", backref="audit_logs")

    # Indexes
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_created_at", "created_at"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_sequence", "sequence_number"),
        Index("ix_audit_logs_company_created", "company_id", "created_at"),
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

    # Query details - WICHTIG: 'query' ist reservierter SQLAlchemy-Name!
    search_query = Column(String(500), nullable=False)
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
        Index("ix_search_analytics_query_pattern", "search_query", postgresql_ops={"search_query": "varchar_pattern_ops"}),
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
    user = relationship("User", backref="gdpr_consent_logs")

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
    user = relationship("User", backref="system_notifications")

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
            # SECURITY FIX Phase 11.2: Use SHA256 instead of MD5 for security-critical hashing
            hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16) % 100
            return hash_value < self.rollout_percentage

        return False

    def get_variant_for_user(self, user_id: str) -> Optional[str]:
        """Ermittelt A/B Test Variante fuer Benutzer."""
        if not self.variants:
            return None

        import hashlib
        hash_input = f"{self.key}:variant:{user_id}".encode()
        # SECURITY FIX Phase 11.2: Use SHA256 instead of MD5 for security-critical hashing
        hash_value = int(hashlib.sha256(hash_input).hexdigest(), 16) % 100

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

    # Lexware Integration
    lexware_ids = Column(
        CrossDBJSON,
        default=dict,
        comment="Lexware IDs per company: {folie: {kd_nr, matchcode, lief_nr}, messer: {...}}"
    )
    company_presence = Column(
        CrossDBJSON,
        default=list,
        comment="List of company short_names where entity exists: ['folie', 'messer']"
    )
    primary_customer_number = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Primary customer number for display (e.g., 12345)"
    )
    primary_supplier_number = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Primary supplier number for display"
    )

    # Risk Scoring (fuer Zahlungsverhalten-Analyse)
    risk_score = Column(
        Float,
        nullable=True,
        comment="Overall risk score 0-100 (100 = highest risk)"
    )
    risk_factors = Column(
        CrossDBJSON,
        default=dict,
        comment="Risk factor breakdown: {payment_delay, default_rate, ...}"
    )
    payment_behavior_score = Column(
        Float,
        nullable=True,
        comment="Payment behavior score 0-100 (100 = best payer)"
    )
    risk_calculated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp of last risk calculation"
    )

    # Auto-Filing Support (Phase 11.1)
    default_folder_id = Column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
        comment="Default folder for auto-filing documents from this entity",
    )

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
    # default_folder relationship disabled - Folder model not implemented yet
    # default_folder = relationship("Folder", foreign_keys=[default_folder_id])

    # Indexes
    __table_args__ = (
        Index("ix_business_entities_name", "name"),
        Index("ix_business_entities_vat_id", "vat_id"),
        Index("ix_business_entities_iban", "iban"),
        Index("ix_business_entities_postal_code", "postal_code"),
        Index("ix_business_entities_entity_type", "entity_type"),
        Index("ix_business_entities_is_active", "is_active"),
        Index("ix_business_entities_deleted_at", "deleted_at"),
        Index("ix_business_entities_default_folder_id", "default_folder_id"),
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
# INVOICE TRACKING MODEL (Rechnungsverfolgung)
# ============================================================================

class InvoiceStatus(str, Enum):
    """Rechnungsstatus fuer Zahlungsverfolgung."""
    OPEN = "open"           # Neu erstellt, noch nicht versandt
    SENT = "sent"           # Versandt, noch nicht faellig
    PAID = "paid"           # Vollstaendig bezahlt
    OVERDUE = "overdue"     # Faellig und nicht bezahlt
    DUNNING = "dunning"     # Im Mahnverfahren
    CANCELLED = "cancelled" # Storniert
    PARTIAL = "partial"     # Teilweise bezahlt


class InvoiceTracking(Base):
    """
    Rechnungsverfolgung fuer Risk Scoring, Skonto und Teilzahlungen.

    Verknuepft Dokumente (Rechnungen) mit Zahlungsinformationen
    fuer die Berechnung von Risiko-Scores.

    Enterprise Features (Januar 2026):
    - Skonto-Tracking mit Deadline-Alerts
    - Teilzahlungs-Verwaltung
    - Ausstehender Betrag Tracking
    """
    __tablename__ = "invoice_tracking"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Document reference
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Invoice identification
    invoice_number = Column(String(100), index=True, nullable=True)
    invoice_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)

    # Amount information
    amount = Column(Float, default=0.0)
    currency = Column(String(3), default="EUR")

    # Payment status
    status = Column(
        String(20),
        default=InvoiceStatus.OPEN.value,
        index=True,
        nullable=False
    )

    # Payment tracking
    paid_at = Column(DateTime(timezone=True), nullable=True)
    paid_amount = Column(Float, nullable=True)

    # ==========================================================================
    # SKONTO TRACKING (P0 Feature - Januar 2026)
    # ==========================================================================
    skonto_percentage = Column(
        Float,
        nullable=True,
        comment="Skonto-Prozentsatz (z.B. 2.0 fuer 2%)"
    )
    skonto_days = Column(
        Integer,
        nullable=True,
        comment="Tage fuer Skonto-Frist ab Rechnungsdatum"
    )
    skonto_deadline = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Berechnete Skonto-Frist (invoice_date + skonto_days)"
    )
    skonto_amount = Column(
        Float,
        nullable=True,
        comment="Berechneter Skonto-Betrag"
    )
    skonto_used = Column(
        Boolean,
        default=False,
        comment="True wenn Skonto genutzt wurde"
    )
    skonto_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Skonto-Nutzung"
    )
    net_days = Column(
        Integer,
        nullable=True,
        comment="Zahlungsziel netto (z.B. 30 Tage)"
    )

    # ==========================================================================
    # TEILZAHLUNGS-TRACKING (P0 Feature - Januar 2026)
    # ==========================================================================
    outstanding_amount = Column(
        Float,
        nullable=True,
        comment="Ausstehender Betrag (amount - paid_amount)"
    )
    is_partial_payment = Column(
        Boolean,
        default=False,
        comment="True wenn Teilzahlung(en) erfasst"
    )

    # Dunning tracking (Mahnwesen)
    dunning_level = Column(Integer, default=0)
    last_dunning_at = Column(DateTime(timezone=True), nullable=True)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Mandanten-Zuordnung"
    )

    # Audit fields
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    document = relationship(
        "Document",
        backref=backref("invoice_tracking", uselist=False, cascade="all, delete-orphan")
    )
    company = relationship("Company", backref="invoice_trackings")
    payment_transactions = relationship(
        "PaymentTransaction",
        back_populates="invoice_tracking",
        cascade="all, delete-orphan",
        order_by="PaymentTransaction.transaction_date.asc()"
    )

    # Indexes
    __table_args__ = (
        Index("ix_invoice_tracking_document_id", "document_id"),
        Index("ix_invoice_tracking_status", "status"),
        Index("ix_invoice_tracking_due_date", "due_date"),
        Index("ix_invoice_tracking_invoice_number", "invoice_number"),
        Index("ix_invoice_tracking_skonto_deadline", "skonto_deadline"),
        Index("ix_invoice_tracking_company_id", "company_id"),
        Index("ix_invoice_tracking_partial", "is_partial_payment", "status"),
    )

    @property
    def is_overdue(self) -> bool:
        """Prueft ob Rechnung ueberfaellig ist."""
        if self.status in (InvoiceStatus.PAID.value, InvoiceStatus.CANCELLED.value):
            return False
        if self.due_date:
            return datetime.now(self.due_date.tzinfo) > self.due_date
        return False

    @property
    def days_overdue(self) -> int:
        """Anzahl Tage ueberfaellig (0 wenn nicht ueberfaellig)."""
        if not self.is_overdue or not self.due_date:
            return 0
        delta = datetime.now(self.due_date.tzinfo) - self.due_date
        return max(0, delta.days)

    @property
    def skonto_still_valid(self) -> bool:
        """Prueft ob Skonto noch nutzbar ist."""
        if not self.skonto_deadline or self.skonto_used:
            return False
        return datetime.now(self.skonto_deadline.tzinfo) <= self.skonto_deadline

    @property
    def days_until_skonto_expires(self) -> Optional[int]:
        """Tage bis Skonto ablaeuft (None wenn kein Skonto oder abgelaufen)."""
        if not self.skonto_deadline or self.skonto_used:
            return None
        delta = self.skonto_deadline - datetime.now(self.skonto_deadline.tzinfo)
        return max(0, delta.days) if delta.days >= 0 else None


class PaymentTransaction(Base):
    """
    Teilzahlung fuer eine Rechnung.

    Ermoeglicht mehrere Zahlungen pro Rechnung mit:
    - Skonto-Abzug Tracking
    - Bank-Reconciliation
    - Audit Trail
    """
    __tablename__ = "payment_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Reference to invoice
    invoice_tracking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Payment details
    transaction_date = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Float, nullable=False, comment="Gezahlter Betrag")
    payment_reference = Column(String(200), nullable=True, comment="Verwendungszweck/Referenz")
    payment_method = Column(
        String(30),
        default="bank_transfer",
        comment="Zahlungsmethode: bank_transfer, cash, credit_card, direct_debit"
    )

    # Skonto
    skonto_deducted = Column(
        Float,
        nullable=True,
        comment="Abgezogener Skonto-Betrag"
    )

    # Bank reconciliation
    bank_transaction_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Verknuepfte Bank-Transaktion ID"
    )
    reconciliation_status = Column(
        String(20),
        default="pending",
        comment="pending, matched, unmatched"
    )
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    reconciled_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Notes
    notes = Column(Text, nullable=True)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    invoice_tracking = relationship(
        "InvoiceTracking",
        back_populates="payment_transactions"
    )
    company = relationship("Company", backref="payment_transactions")
    created_by = relationship("User", foreign_keys=[created_by_id])
    reconciled_by = relationship("User", foreign_keys=[reconciled_by_id])

    # Indexes
    __table_args__ = (
        Index("ix_payment_transactions_invoice", "invoice_tracking_id"),
        Index("ix_payment_transactions_date", "transaction_date"),
        Index("ix_payment_transactions_bank", "bank_transaction_id"),
        Index("ix_payment_transactions_company", "company_id"),
        Index("ix_payment_transactions_reconciliation", "reconciliation_status"),
    )


class DocumentChainDiscrepancy(Base):
    """
    Abweichungen in Dokumentenketten.

    Erfasst Unterschiede zwischen verknuepften Dokumenten:
    - Betragsabweichungen (Angebot vs Rechnung)
    - Mengenabweichungen
    - Preisabweichungen
    """
    __tablename__ = "document_chain_discrepancies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Chain reference
    chain_id = Column(String(100), nullable=False, index=True)

    # Documents involved
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

    # Discrepancy details
    discrepancy_type = Column(
        String(30),
        nullable=False,
        comment="amount, quantity, price, date, missing_item"
    )
    field_name = Column(String(100), nullable=True, comment="Betroffenes Feld")
    expected_value = Column(String(500), nullable=True)
    actual_value = Column(String(500), nullable=True)
    difference_amount = Column(Float, nullable=True, comment="Numerische Differenz")
    difference_percentage = Column(Float, nullable=True, comment="Prozentuale Differenz")

    # Severity
    severity = Column(
        String(20),
        default="warning",
        comment="info, warning, error, critical"
    )
    description = Column(Text, nullable=True)

    # Resolution
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    resolution_notes = Column(Text, nullable=True)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    source_document = relationship("Document", foreign_keys=[source_document_id])
    target_document = relationship("Document", foreign_keys=[target_document_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    company = relationship("Company", backref="chain_discrepancies")

    # Indexes
    __table_args__ = (
        Index("ix_chain_discrepancies_chain", "chain_id"),
        Index("ix_chain_discrepancies_type", "discrepancy_type"),
        Index("ix_chain_discrepancies_severity", "severity"),
        Index("ix_chain_discrepancies_resolved", "is_resolved"),
        Index("ix_chain_discrepancies_company", "company_id"),
    )


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
    - Auftragsketten (Angebot -> Auftrag -> Lieferschein -> Rechnung)

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
    confidence = Column(Float, default=1.0)  # 0.0-1.0 (legacy)
    confidence_score = Column(Float, nullable=True, comment="Konfidenz bei Auto-Detection (0.0-1.0)")

    # Chain reference (fuer Auftragsketten)
    chain_id = Column(
        String(100),
        nullable=True,
        index=True,
        comment="Auftragsketten-ID (z.B. CHAIN-2026-00001)"
    )

    # Ordering (fuer CHILD_OF Beziehungen)
    sequence_number = Column(Integer, nullable=True)  # Seitennummer/Reihenfolge

    # Detection metadata
    detected_by = Column(String(50), nullable=True)  # "algorithm", "user", "ocr_reference"
    detection_details = Column(CrossDBJSON, default=dict)
    auto_detected = Column(
        Boolean,
        default=False,
        comment="True wenn automatisch erkannt (nicht manuell)"
    )

    # User interaction / Validation
    user_confirmed = Column(Boolean, default=False)
    user_rejected = Column(Boolean, default=False)
    validated = Column(
        Boolean,
        default=False,
        comment="True wenn manuell validiert oder manuell erstellt"
    )
    validated_at = Column(DateTime(timezone=True), nullable=True)
    validated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Wer hat validiert"
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Firmen-Zuordnung fuer Multi-Tenant"
    )

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
    created_by = relationship("User", foreign_keys=[created_by_id])
    validated_by = relationship("User", foreign_keys=[validated_by_id])
    company = relationship("Company", backref="document_relationships")

    # Indexes and constraints
    __table_args__ = (
        Index("ix_document_relationships_source", "source_document_id"),
        Index("ix_document_relationships_target", "target_document_id"),
        Index("ix_document_relationships_type", "relationship_type"),
        Index("ix_document_relationships_confidence", "confidence"),
        Index("ix_document_relationships_chain", "chain_id"),
        Index("ix_document_relationships_company", "company_id"),
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

    # Kalender-Sync (Phase 6D)
    calendar_sync = Column(CrossDBJSON, nullable=True, comment="Sync-Konfiguration (Provider, URL, Kategorien)")
    calendar_oauth_tokens = Column(CrossDBJSON, nullable=True, comment="Verschluesselte OAuth-Tokens nach Provider")
    calendar_sync_state = Column(CrossDBJSON, nullable=True, comment="Sync-State Mapping {uid: external_event_id}")

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
        end_time = self.completed_at or datetime.now(timezone.utc)
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
        elapsed_hours = (datetime.now(timezone.utc) - self.started_at).total_seconds() / 3600
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
    transmissions = relationship("EInvoiceTransmission", back_populates="einvoice", cascade="all, delete-orphan")

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


# =============================================================================
# DATEV CONNECT INTEGRATION (Migration 145)
# =============================================================================


class DATEVConnectionStatus(str, Enum):
    """DATEV Connection Status."""
    pending = "pending"
    connecting = "connecting"
    connected = "connected"
    disconnected = "disconnected"
    error = "error"
    token_expired = "token_expired"


class DATEVSyncType(str, Enum):
    """DATEV Sync Operation Types."""
    stammdaten_push = "stammdaten_push"
    stammdaten_pull = "stammdaten_pull"
    buchungsstapel = "buchungsstapel"
    belegbilder = "belegbilder"
    kontierung = "kontierung"
    kontenplan = "kontenplan"


class DATEVKontierungStatus(str, Enum):
    """Status of Kontierung Suggestion."""
    suggested = "suggested"
    accepted = "accepted"
    rejected = "rejected"
    modified = "modified"


class DATEVConnection(Base):
    """
    DATEVconnect API Connection.

    Verwaltet OAuth2-Verbindung zu DATEVconnect fuer bidirektionale Synchronisation.
    Unterstuetzt Buchungsstapel, Belegbilder und Stammdaten-Sync.

    SECURITY: Alle Credentials werden verschluesselt gespeichert (AES-256-GCM).
    """

    __tablename__ = "datev_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-Tenant Isolation"
    )
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Ersteller der Verbindung"
    )

    # Connection Name
    name = Column(String(100), nullable=False, comment="Anzeigename der Verbindung")
    description = Column(Text, nullable=True)

    # DATEV Identifiers
    mandant_nr = Column(String(10), nullable=False, comment="DATEV Mandantennummer")
    berater_nr = Column(String(10), nullable=False, comment="DATEV Beraternummer")
    kontenrahmen = Column(
        String(10),
        nullable=False,
        default="SKR03",
        comment="Kontenrahmen (SKR03/SKR04)"
    )
    wirtschaftsjahr_beginn = Column(
        Integer,
        nullable=False,
        default=1,
        comment="Monat des Wirtschaftsjahresbeginns (1-12)"
    )

    # OAuth2 Credentials (encrypted)
    client_id = Column(String(100), nullable=True)
    client_secret_encrypted = Column(Text, nullable=True, comment="AES-256-GCM encrypted")
    access_token_encrypted = Column(Text, nullable=True, comment="AES-256-GCM encrypted")
    refresh_token_encrypted = Column(Text, nullable=True, comment="AES-256-GCM encrypted")
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Connection Configuration
    environment = Column(
        String(20),
        nullable=False,
        default="production",
        comment="production or sandbox"
    )
    api_version = Column(String(10), nullable=True, default="v1")
    webhook_url = Column(String(500), nullable=True, comment="Callback URL for notifications")

    # Sync Configuration
    auto_kontierung = Column(Boolean, default=False, comment="Automatische Kontierungsvorschlaege")
    auto_beleg_upload = Column(Boolean, default=True, comment="Automatischer Belegbilder-Upload")
    sync_interval_minutes = Column(Integer, default=60, comment="Sync-Intervall in Minuten")
    last_buchung_nr = Column(Integer, nullable=True, comment="Letzte verwendete Buchungsnummer")

    # Status
    connection_status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, connecting, connected, disconnected, error, token_expired"
    )
    last_connection_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    # Audit
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="datev_connections")
    created_by = relationship("User", backref="datev_connections_created")
    buchungen = relationship("DATEVBuchung", back_populates="connection", cascade="all, delete-orphan")
    sync_history = relationship("DATEVSyncHistory", back_populates="connection", cascade="all, delete-orphan")
    kontenplan = relationship("DATEVKontenplan", back_populates="connection", cascade="all, delete-orphan")
    beleglinks = relationship("DATEVBeleglink", back_populates="connection", cascade="all, delete-orphan")
    kontierung_patterns = relationship("DATEVKontierungPattern", back_populates="connection", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_datev_connections_company_id", "company_id"),
        Index("ix_datev_connections_mandant_berater", "mandant_nr", "berater_nr"),
        Index("ix_datev_connections_status", "connection_status"),
        UniqueConstraint("company_id", "mandant_nr", "berater_nr", name="uq_datev_connection_per_mandant"),
    )


class DATEVKontenplan(Base):
    """
    DATEV Kontenplan Cache.

    Lokaler Cache des DATEV Kontenplans fuer schnelle Kontierungsvorschlaege.
    Wird periodisch mit DATEV synchronisiert.
    """

    __tablename__ = "datev_kontenplan"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Konto
    kontonummer = Column(String(10), nullable=False, comment="Kontennummer (z.B. 4400)")
    bezeichnung = Column(String(200), nullable=False, comment="Kontobezeichnung")
    kontenrahmen = Column(String(10), nullable=False, comment="SKR03 oder SKR04")
    kontotyp = Column(
        String(50),
        nullable=True,
        comment="sachkonto, personenkonto, erloes, aufwand, etc."
    )

    # Steuer
    steuerschluessel_default = Column(String(5), nullable=True, comment="Standard-Steuerschluessel")
    mwst_satz = Column(Float, nullable=True, comment="Standard-MwSt-Satz")

    # Hierarchie
    kontenklasse = Column(Integer, nullable=True, comment="0-9 Kontenklasse")
    is_sammelkonto = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # Sync
    synced_at = Column(DateTime(timezone=True), nullable=True)
    datev_konto_id = Column(String(50), nullable=True, comment="DATEV interne ID")

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("DATEVConnection", back_populates="kontenplan")

    __table_args__ = (
        Index("ix_datev_kontenplan_connection_id", "connection_id"),
        Index("ix_datev_kontenplan_kontonummer", "kontonummer"),
        Index("ix_datev_kontenplan_lookup", "connection_id", "kontonummer", "kontenrahmen"),
        UniqueConstraint("connection_id", "kontonummer", name="uq_datev_konto_per_connection"),
    )


class DATEVBuchung(Base):
    """
    DATEV Buchungssatz.

    Repraesentiert einen Buchungssatz fuer den DATEV Export.
    GoBD-konform mit SHA-256 Hash fuer Unveraenderbarkeit nach Festschreibung.

    SECURITY: Festgeschriebene Buchungen sind immutable (gobd_festgeschrieben=True).
    """

    __tablename__ = "datev_buchungen"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknuepftes Quelldokument"
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknuepfter Geschaeftspartner"
    )

    # Buchungssatz
    buchungsnummer = Column(Integer, nullable=True, comment="Fortlaufende Nummer im Stapel")
    belegdatum = Column(Date, nullable=False, comment="Datum des Belegs")
    buchungsdatum = Column(Date, nullable=True, comment="Datum der Buchung")
    valutadatum = Column(Date, nullable=True, comment="Valutadatum")

    # Betraege
    betrag_soll = Column(Float, nullable=False, comment="Soll-Betrag (immer positiv)")
    betrag_haben = Column(Float, nullable=False, comment="Haben-Betrag (immer positiv)")
    waehrung = Column(String(3), nullable=False, default="EUR")

    # Konten
    konto_soll = Column(String(10), nullable=False, comment="Soll-Konto")
    konto_haben = Column(String(10), nullable=False, comment="Haben-Konto")
    steuerschluessel = Column(String(5), nullable=True, comment="DATEV Steuerschluessel")
    kostenstelle_1 = Column(String(20), nullable=True)
    kostenstelle_2 = Column(String(20), nullable=True)
    kostentraeger = Column(String(20), nullable=True)

    # Buchungstext
    buchungstext = Column(String(120), nullable=True, comment="Buchungstext (max 120 Zeichen)")
    belegnummer = Column(String(36), nullable=True, comment="Belegnummer/Rechnungsnummer")

    # GoBD Compliance
    gobd_festgeschrieben = Column(
        Boolean,
        default=False,
        comment="True = unveraenderbar (GoBD-konform)"
    )
    gobd_hash = Column(String(64), nullable=True, comment="SHA-256 Hash fuer Unveraenderbarkeit")
    festgeschrieben_at = Column(DateTime(timezone=True), nullable=True)
    festgeschrieben_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Sync Status
    sync_status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, synced, error"
    )
    synced_at = Column(DateTime(timezone=True), nullable=True)
    datev_buchung_id = Column(String(50), nullable=True, comment="ID nach DATEV-Sync")
    sync_error = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    connection = relationship("DATEVConnection", back_populates="buchungen")
    document = relationship("Document", backref="datev_buchungen")
    entity = relationship("BusinessEntity", backref="datev_buchungen")

    __table_args__ = (
        Index("ix_datev_buchungen_connection_id", "connection_id"),
        Index("ix_datev_buchungen_document_id", "document_id"),
        Index("ix_datev_buchungen_entity_id", "entity_id"),
        Index("ix_datev_buchungen_belegdatum", "belegdatum"),
        Index("ix_datev_buchungen_sync_status", "sync_status"),
        Index("ix_datev_buchungen_gobd", "gobd_festgeschrieben"),
        CheckConstraint(
            "sync_status IN ('pending', 'synced', 'error')",
            name="ck_datev_buchungen_sync_status"
        ),
    )


class DATEVBeleglink(Base):
    """
    DATEV Belegbild-Verknuepfung.

    Verknuepft hochgeladene Belegbilder mit DATEV-Buchungen.
    Ermoeglicht den Upload zu DATEV Unternehmen Online (DUO).
    """

    __tablename__ = "datev_beleglinks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    buchung_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_buchungen.id", ondelete="CASCADE"),
        nullable=True,
        comment="Verknuepfte Buchung"
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="Quelldokument mit Belegbild"
    )

    # Upload Status
    upload_status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, uploaded, error"
    )
    uploaded_at = Column(DateTime(timezone=True), nullable=True)
    datev_beleg_id = Column(String(100), nullable=True, comment="DATEV Beleg-ID nach Upload")
    upload_error = Column(Text, nullable=True)

    # File Info
    original_filename = Column(String(255), nullable=True)
    file_hash = Column(String(64), nullable=True, comment="SHA-256 des Belegbilds")
    file_size_bytes = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("DATEVConnection", back_populates="beleglinks")
    buchung = relationship("DATEVBuchung", backref="beleglinks")
    document = relationship("Document", backref="datev_beleglinks")

    __table_args__ = (
        Index("ix_datev_beleglinks_connection_id", "connection_id"),
        Index("ix_datev_beleglinks_buchung_id", "buchung_id"),
        Index("ix_datev_beleglinks_document_id", "document_id"),
        Index("ix_datev_beleglinks_upload_status", "upload_status"),
        CheckConstraint(
            "upload_status IN ('pending', 'uploaded', 'error')",
            name="ck_datev_beleglinks_upload_status"
        ),
    )


class DATEVKontierungPattern(Base):
    """
    ML-basierte Kontierungsmuster.

    Lernt aus historischen Buchungen und User-Korrekturen um
    intelligente Kontierungsvorschlaege zu generieren.

    Matching-Kriterien: Lieferant, Betrag-Range, Stichwort.
    """

    __tablename__ = "datev_kontierung_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Matching-Kriterien
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=True,
        comment="Optionaler Geschaeftspartner-Match"
    )
    pattern_type = Column(
        String(50),
        nullable=False,
        comment="entity, keyword, amount_range, document_type"
    )
    keyword_pattern = Column(String(200), nullable=True, comment="Regex-Pattern fuer Buchungstext")
    amount_min = Column(Float, nullable=True)
    amount_max = Column(Float, nullable=True)
    document_type = Column(String(50), nullable=True, comment="Dokumenttyp-Filter")

    # Kontierung
    konto_soll = Column(String(10), nullable=False)
    konto_haben = Column(String(10), nullable=False)
    steuerschluessel = Column(String(5), nullable=True)
    kostenstelle = Column(String(20), nullable=True)

    # ML Metrics
    confidence = Column(Float, nullable=False, default=0.5, comment="0.0-1.0 Konfidenz")
    usage_count = Column(Integer, default=0, comment="Wie oft wurde dieses Pattern verwendet")
    success_count = Column(Integer, default=0, comment="Wie oft wurde es akzeptiert")
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    connection = relationship("DATEVConnection", back_populates="kontierung_patterns")
    entity = relationship("BusinessEntity", backref="datev_kontierung_patterns")

    __table_args__ = (
        Index("ix_datev_kontierung_patterns_connection_id", "connection_id"),
        Index("ix_datev_kontierung_patterns_entity_id", "entity_id"),
        Index("ix_datev_kontierung_patterns_confidence", "confidence"),
        Index("ix_datev_kontierung_patterns_lookup", "connection_id", "entity_id", "pattern_type"),
    )


class DATEVSyncHistory(Base):
    """
    DATEV Sync-Historie.

    Protokolliert alle Sync-Operationen fuer Audit und Debugging.
    """

    __tablename__ = "datev_sync_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("datev_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    triggered_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Sync Details
    sync_type = Column(
        String(50),
        nullable=False,
        comment="stammdaten_push, stammdaten_pull, buchungsstapel, belegbilder, kontierung, kontenplan"
    )
    direction = Column(String(10), nullable=False, default="push", comment="push or pull")

    # Results
    status = Column(
        String(20),
        nullable=False,
        default="running",
        comment="running, completed, partial, failed"
    )
    items_total = Column(Integer, default=0)
    items_success = Column(Integer, default=0)
    items_failed = Column(Integer, default=0)
    items_skipped = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Error Handling
    error_message = Column(Text, nullable=True)
    error_details = Column(CrossDBJSON, nullable=True, default=dict)

    # Metadata
    sync_metadata = Column(CrossDBJSON, nullable=True, default=dict, comment="Zusaetzliche Sync-Infos")  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Relationships
    connection = relationship("DATEVConnection", back_populates="sync_history")
    user = relationship("User", backref="datev_sync_triggered")

    __table_args__ = (
        Index("ix_datev_sync_history_connection_id", "connection_id"),
        Index("ix_datev_sync_history_started_at", "started_at"),
        Index("ix_datev_sync_history_status", "status"),
        Index("ix_datev_sync_history_sync_type", "sync_type"),
        CheckConstraint(
            "status IN ('running', 'completed', 'partial', 'failed')",
            name="ck_datev_sync_history_status"
        ),
        CheckConstraint(
            "direction IN ('push', 'pull')",
            name="ck_datev_sync_history_direction"
        ),
    )


# =============================================================================
# FINANCE DOCUMENT HISTORY
# =============================================================================


class FinanceDocumentHistory(Base):
    """Immutable Audit-Log fuer Finanz-Dokumente.

    Trackt alle Aenderungen an Finanz-Dokumenten fuer Enterprise-Compliance:
    - Erstellung, Bearbeitung, Loeschung
    - Kategorie- und Jahr-Aenderungen
    - Frist-Aenderungen
    - OCR-Verarbeitung

    WICHTIG: Diese Tabelle ist append-only!
    Ein Datenbank-Trigger sollte UPDATE und DELETE verhindern.
    """
    __tablename__ = "finance_document_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Benutzer, der die Aenderung vorgenommen hat
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Aktion
    action = Column(
        String(50),
        nullable=False,
        comment="created, updated, deleted, restored, category_changed, year_changed, etc."
    )

    # Aenderungsdetails
    old_values = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Vorherige Werte (bei Updates)"
    )
    new_values = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Neue Werte (bei Updates)"
    )

    # Betroffene Felder
    changed_fields = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Liste der geaenderten Felder"
    )

    # Kontext
    ip_address = Column(String(45), nullable=True, comment="IP-Adresse des Benutzers")
    user_agent = Column(String(500), nullable=True, comment="Browser/Client Info")

    # Zusaetzliche Metadaten
    # Note: DB column is 'metadata', but we use 'extra_metadata' as Python attribute
    # because 'metadata' is reserved in SQLAlchemy's Declarative API
    extra_metadata = Column(
        'metadata',  # Actual DB column name
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Zusaetzliche Kontext-Informationen"
    )

    # Beschreibung (menschenlesbar, auf Deutsch)
    description = Column(
        Text,
        nullable=True,
        comment="Menschenlesbare Beschreibung der Aenderung"
    )

    # Zeitstempel (immutable)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    document = relationship("Document", backref="finance_history")
    user = relationship("User", backref="finance_document_changes")

    # Indexes
    __table_args__ = (
        Index("ix_finance_doc_history_document_id", "document_id"),
        Index("ix_finance_doc_history_user_id", "user_id"),
        Index("ix_finance_doc_history_action", "action"),
        Index("ix_finance_doc_history_created_at", "created_at"),
        Index("ix_finance_doc_history_doc_created", "document_id", "created_at"),
        CheckConstraint(
            "action IN ('created', 'updated', 'deleted', 'restored', "
            "'category_changed', 'year_changed', 'ocr_completed', "
            "'deadline_set', 'deadline_removed', 'bulk_update')",
            name="ck_finance_doc_history_action"
        ),
    )


# =============================================================================
# KASSE-MODUL: ENUMS
# =============================================================================


class CashEntryType(str, Enum):
    """Typ der Kassenbuchung - GoBD-konform."""

    # Einnahmen
    INCOME = "income"                    # Allgemeine Einnahme
    DEPOSIT = "deposit"                  # Kasseneinlage von Bank
    REFUND_RECEIVED = "refund_received"  # Erstattung erhalten

    # Ausgaben
    EXPENSE = "expense"                  # Allgemeine Ausgabe
    WITHDRAWAL = "withdrawal"            # Kassenentnahme zur Bank
    ENTERTAINMENT = "entertainment"      # Bewirtungskosten (70% abzugsfaehig)
    TRAVEL = "travel"                    # Reisekosten
    OFFICE = "office"                    # Buerobedarf
    FUEL = "fuel"                        # Tankkosten
    PARKING = "parking"                  # Parkgebuehren
    POSTAGE = "postage"                  # Porto
    TIPS = "tips"                        # Trinkgeld
    GIFTS = "gifts"                      # Geschenke

    # Sonder
    DIFFERENCE_PLUS = "difference_plus"   # Kassenmehrbestand
    DIFFERENCE_MINUS = "difference_minus" # Kassenfehlbestand
    CANCELLATION = "cancellation"         # Stornobuchung (Gegenbuchung)
    OPENING = "opening"                   # Eroeffnungsbuchung


class ExpenseReportStatus(str, Enum):
    """Status einer Spesenabrechnung - Workflow."""

    DRAFT = "draft"           # Entwurf
    SUBMITTED = "submitted"   # Eingereicht
    IN_REVIEW = "in_review"   # In Pruefung
    APPROVED = "approved"     # Genehmigt
    REJECTED = "rejected"     # Abgelehnt
    PAID = "paid"             # Ausgezahlt


class ExpenseType(str, Enum):
    """Typ einer Spesenposition."""

    RECEIPT = "receipt"       # Belegausgabe
    MILEAGE = "mileage"       # Kilometergeld (0,30 EUR/km)
    PER_DIEM = "per_diem"     # Verpflegungspauschale (14/28 EUR)
    FLAT_RATE = "flat_rate"   # Sonstige Pauschale


# =============================================================================
# KASSE-MODUL: MULTI-COMPANY
# =============================================================================


class Company(Base):
    """Firma/Mandant fuer Multi-Company Support.

    Ersetzt das bisherige CompanySettings-Singleton und ermoeglicht
    die Verwaltung mehrerer Firmen pro Installation.

    Jede Firma hat eigene Kassen, Spesenfreigaben und Einstellungen.
    Row-Level Security (RLS) isoliert Mandanten-Daten.
    """

    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    name = Column(String(255), nullable=False)
    short_name = Column(String(50), nullable=True)
    display_name = Column(String(255), nullable=True)

    # Rechtsform & Register
    legal_form = Column(String(50), nullable=True)  # GmbH, UG, AG, etc.
    commercial_register = Column(String(100), nullable=True)
    court = Column(String(100), nullable=True)

    # Steuer
    vat_id = Column(String(20), unique=True, nullable=True)  # DE123456789
    tax_number = Column(String(50), nullable=True)

    # Adresse
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")

    # Kontakt
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    website = Column(String(255), nullable=True)

    # Banking (Hauptkonto)
    iban = Column(String(34), nullable=True)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)

    # Alternative Namen fuer OCR-Erkennung
    alternative_names = Column(CrossDBJSON, default=list)

    # Einstellungen
    default_currency = Column(String(3), default="EUR")
    fiscal_year_start = Column(Integer, default=1)  # Monat (1=Januar)
    kontenrahmen = Column(String(10), default="SKR03")  # SKR03 oder SKR04

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    # ==================== Subscription/Multi-Tenant ====================
    # Abonnement-Stufe: free, basic, professional, enterprise
    subscription_tier = Column(String(50), nullable=False, default="free")
    subscription_started_at = Column(DateTime(timezone=True), nullable=True)
    subscription_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Billing-Informationen
    billing_email = Column(String(255), nullable=True)
    billing_address = Column(CrossDBJSON, default=dict)
    payment_method = Column(String(50), nullable=True)  # invoice, sepa, card

    # Tenant-Limits (ueberschreibbar pro Tier)
    max_users = Column(Integer, nullable=False, default=5)
    max_documents_per_month = Column(Integer, nullable=False, default=100)
    max_storage_gb = Column(Integer, nullable=False, default=5)

    # Aktivierte Features als JSON-Array
    features_enabled = Column(CrossDBJSON, default=lambda: ["ocr", "search", "export"])

    # Auto-Filing Rules (Phase 11.2)
    filing_rules = Column(
        CrossDBJSON,
        default=dict,
        comment="Custom auto-filing rules: {'invoice': {'folder_id': 'uuid', 'folder_name': '...'}, ...}",
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user_associations = relationship("UserCompany", back_populates="company", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="company", cascade="all, delete-orphan")
    cash_registers = relationship("CashRegister", back_populates="company", cascade="all, delete-orphan")
    expense_reports = relationship("ExpenseReport", back_populates="company", cascade="all, delete-orphan")
    # Document Template relationships - imported from app.db.models.document_template
    document_templates = relationship("DocumentTemplate", back_populates="company", cascade="all, delete-orphan")
    # Tenant Rate Limit relationships
    rate_limits = relationship("TenantRateLimit", back_populates="company", cascade="all, delete-orphan")
    usage_metrics = relationship("TenantUsageMetrics", back_populates="company", cascade="all, delete-orphan")
    rate_limit_violations = relationship("RateLimitViolation", back_populates="company", cascade="all, delete-orphan")
    # BPMN Process Engine relationships (models in bpmn_models/bpmn.py, same Base)
    bpmn_process_definitions = relationship("ProcessDefinition", back_populates="company", cascade="all, delete-orphan")
    bpmn_process_instances = relationship("ProcessInstance", back_populates="company", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_companies_vat_id", "vat_id"),
        Index("ix_companies_is_active", "is_active"),
        Index("ix_companies_is_default", "is_default"),
        Index("ix_companies_deleted_at", "deleted_at"),
        Index("ix_companies_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Company {self.name} ({self.id})>"


class UserCompany(Base):
    """Zuordnung User <-> Company mit granularen Berechtigungen.

    Ermoeglicht Multi-Mandanten-Faehigkeit: Ein User kann
    Zugriff auf mehrere Firmen haben, mit unterschiedlichen Rechten.
    """

    __tablename__ = "user_companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Rolle
    role = Column(String(50), default="member")  # owner, admin, member, viewer

    # Granulare Berechtigungen fuer Kasse-Modul
    can_manage_cash = Column(Boolean, default=False)      # Kassenbuchungen erstellen
    can_approve_expenses = Column(Boolean, default=False) # Spesen genehmigen
    can_export_datev = Column(Boolean, default=False)     # DATEV-Export
    can_manage_settings = Column(Boolean, default=False)  # Firmeneinstellungen

    # Aktive Firma fuer Session
    is_current = Column(Boolean, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="company_associations")
    company = relationship("Company", back_populates="user_associations")

    __table_args__ = (
        Index("ix_user_companies_user_id", "user_id"),
        Index("ix_user_companies_company_id", "company_id"),
        Index("ix_user_companies_is_current", "is_current"),
        Index("ix_user_companies_role", "role"),
        # UniqueConstraint wird in Migration erstellt
    )

    def __repr__(self) -> str:
        return f"<UserCompany user={self.user_id} company={self.company_id} role={self.role}>"


# =============================================================================
# KASSE-MODUL: KASSENBUCH (GoBD-KONFORM!)
# =============================================================================


class CashRegister(Base):
    """Kasse/Bargeldbestand.

    Eine Firma kann mehrere Kassen haben (Hauptkasse, Portokasse, Nebenkasse).
    Jede Kasse fuehrt ein eigenes Kassenbuch mit fortlaufender Nummerierung.
    """

    __tablename__ = "cash_registers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Identifikation
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    register_number = Column(String(50), nullable=True)  # Interne Kassennummer

    # Waehrung & Limits
    currency = Column(String(3), default="EUR")
    max_balance = Column(Numeric(15, 2), nullable=True)  # Maximaler Kassenbestand
    warning_threshold = Column(Numeric(15, 2), nullable=True)  # Warnschwelle

    # Aktueller Stand (denormalisiert fuer Performance)
    current_balance = Column(Numeric(15, 2), default=0)
    balance_date = Column(DateTime(timezone=True), nullable=True)
    last_reconciliation_date = Column(DateTime(timezone=True), nullable=True)

    # Banking-Verknuepfung (fuer Entnahmen/Einlagen)
    linked_bank_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bank_accounts.id", ondelete="SET NULL"),
        nullable=True
    )

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="cash_registers")
    entries = relationship("CashEntry", back_populates="cash_register", order_by="CashEntry.entry_number")
    linked_bank_account = relationship("BankAccount")
    counts = relationship("CashCount", back_populates="cash_register")

    __table_args__ = (
        Index("ix_cash_registers_company_id", "company_id"),
        Index("ix_cash_registers_is_active", "is_active"),
        Index("ix_cash_registers_deleted_at", "deleted_at"),
        # Name muss pro Firma eindeutig sein
        Index("ix_cash_registers_company_name", "company_id", "name", unique=True),
    )

    def __repr__(self) -> str:
        return f"<CashRegister {self.name} ({self.current_balance} {self.currency})>"


class CashEntry(Base):
    """Kassenbucheintrag - APPEND-ONLY fuer GoBD-Compliance!

    WICHTIG: Diese Tabelle erlaubt KEINE Updates oder Deletes!
    Nach GoBD muessen Kassenbuchungen unveraenderbar sein.
    Stornierungen erfolgen durch Gegenbuchung mit Verweis auf Original.

    Constraints:
    - entry_date darf NICHT in der Zukunft liegen
    - amount darf NICHT 0 sein
    - entry_number ist fortlaufend pro Kasse/Jahr - KEINE Luecken!
    - balance_after muss bei JEDER Buchung korrekt berechnet werden
    """

    __tablename__ = "cash_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),  # RESTRICT - nicht CASCADE!
        nullable=False
    )
    cash_register_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cash_registers.id", ondelete="RESTRICT"),  # RESTRICT!
        nullable=False
    )

    # Fortlaufende Nummer (pro Kasse/Jahr) - KEINE LUECKEN!
    entry_number = Column(Integer, nullable=False)
    fiscal_year = Column(Integer, nullable=False)

    # Buchungsdaten
    entry_date = Column(Date, nullable=False)  # Buchungsdatum
    value_date = Column(Date, nullable=False)  # Wertstellungsdatum

    # Betrag (positiv = Einnahme, negativ = Ausgabe)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")

    # Saldo NACH dieser Buchung (fuer Kassensturz)
    balance_after = Column(Numeric(15, 2), nullable=False)

    # Kategorisierung
    entry_type = Column(String(50), nullable=False)  # CashEntryType
    category_id = Column(UUID(as_uuid=True), ForeignKey("cash_categories.id"), nullable=True)

    # Steuer
    tax_rate = Column(Numeric(5, 2), nullable=True)      # 0, 7, 19
    tax_amount = Column(Numeric(15, 2), nullable=True)   # MwSt-Betrag
    net_amount = Column(Numeric(15, 2), nullable=True)   # Netto-Betrag
    is_tax_deductible = Column(Boolean, default=True)
    deductible_percentage = Column(Integer, default=100)  # z.B. 70 bei Bewirtung

    # Beschreibung
    description = Column(Text, nullable=False)
    reference_number = Column(String(100), nullable=True)  # Belegnummer

    # Geschaeftspartner
    counterparty_name = Column(String(255), nullable=True)
    counterparty_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True)

    # Verknuepfungen
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    bank_transaction_id = Column(UUID(as_uuid=True), ForeignKey("bank_transactions.id"), nullable=True)
    expense_report_id = Column(UUID(as_uuid=True), ForeignKey("expense_reports.id"), nullable=True)

    # Storno-Handling (Gegenbuchung statt Loeschung!)
    is_cancelled = Column(Boolean, default=False)
    cancelled_by_entry_id = Column(UUID(as_uuid=True), ForeignKey("cash_entries.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # GoBD Audit Trail für Stornierungen
    cancelled_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User der die Stornierung durchgeführt hat"
    )
    cancelled_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Stornierung (GoBD Audit Trail)"
    )

    # Bewirtungskosten-Spezifika (JSON)
    entertainment_data = Column(CrossDBJSON, nullable=True)
    # Schema: {"participants": ["Name1", "Name2"], "occasion": "Projektbesprechung", "location": "Restaurant XY"}

    # DATEV-Export
    datev_exported_at = Column(DateTime(timezone=True), nullable=True)
    datev_export_batch_id = Column(UUID(as_uuid=True), nullable=True)

    # Buchungskonten (SKR03/SKR04)
    debit_account = Column(String(10), nullable=True)   # Soll-Konto
    credit_account = Column(String(10), nullable=True)  # Haben-Konto
    cost_center = Column(String(50), nullable=True)     # Kostenstelle

    # Audit (UNVERAENDERBAR!)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Relationships
    cash_register = relationship("CashRegister", back_populates="entries")
    category = relationship("CashCategory")
    document = relationship("Document")
    bank_transaction = relationship("BankTransaction")
    counterparty = relationship("BusinessEntity")
    cancellation_entry = relationship("CashEntry", remote_side=[id])

    __table_args__ = (
        # Eindeutige Nummerierung pro Kasse/Jahr
        Index("ix_cash_entries_unique_number", "cash_register_id", "fiscal_year", "entry_number", unique=True),
        Index("ix_cash_entries_company_id", "company_id"),
        Index("ix_cash_entries_register_id", "cash_register_id"),
        Index("ix_cash_entries_date", "entry_date"),
        Index("ix_cash_entries_type", "entry_type"),
        Index("ix_cash_entries_document_id", "document_id"),
        Index("ix_cash_entries_cancelled", "is_cancelled"),
        Index("ix_cash_entries_datev", "datev_exported_at"),
        # Constraint: Betrag darf nicht 0 sein
        CheckConstraint("amount != 0", name="ck_cash_entries_amount_not_zero"),
        # Constraint: Kein Buchungsdatum in der Zukunft
        CheckConstraint("entry_date <= CURRENT_DATE", name="ck_cash_entries_no_future_date"),
    )

    def __repr__(self) -> str:
        return f"<CashEntry #{self.entry_number}/{self.fiscal_year} {self.amount} {self.currency}>"


class CashCategory(Base):
    """Kategorie fuer Kassenausgaben mit SKR-Kontenzuordnung.

    Vordefinierte Kategorien mit Mapping zu SKR03/SKR04 Konten.
    Unterstuetzt hierarchische Kategorien fuer detaillierte Auswertungen.
    """

    __tablename__ = "cash_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True  # NULL = System-Default Kategorien
    )

    # Identifikation
    name = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=True)  # Englischer Name
    description = Column(Text, nullable=True)
    icon = Column(String(50), nullable=True)   # Icon-Name
    color = Column(String(7), nullable=True)   # Hex-Farbe

    # Hierarchie
    parent_id = Column(UUID(as_uuid=True), ForeignKey("cash_categories.id"), nullable=True)
    level = Column(Integer, default=0)
    path = Column(String(500), nullable=True)  # Materialisierter Pfad

    # Buchhaltung (SKR03/SKR04)
    skr03_account = Column(String(10), nullable=True)
    skr04_account = Column(String(10), nullable=True)
    default_tax_rate = Column(Numeric(5, 2), default=19)

    # Spezielle Typen
    category_type = Column(String(50), nullable=True)  # entertainment, travel, office, etc.
    is_entertainment = Column(Boolean, default=False)   # Bewirtungskosten?
    is_travel_expense = Column(Boolean, default=False)  # Reisekosten?
    deductible_percentage = Column(Integer, default=100)  # z.B. 70 bei Bewirtung

    # Vorsteuer
    allows_vat_deduction = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)  # System-Kategorie (nicht loeschbar)
    sort_order = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    parent = relationship("CashCategory", remote_side=[id])

    __table_args__ = (
        Index("ix_cash_categories_company_id", "company_id"),
        Index("ix_cash_categories_parent_id", "parent_id"),
        Index("ix_cash_categories_is_active", "is_active"),
        Index("ix_cash_categories_type", "category_type"),
        Index("ix_cash_categories_sort", "sort_order"),
    )

    def __repr__(self) -> str:
        return f"<CashCategory {self.name} (SKR03: {self.skr03_account})>"


class CashCount(Base):
    """Zaehlprotokoll fuer Kassensturz.

    Dokumentiert den physischen Bargeldbestand bei Kassensturz.
    Berechnet Differenz zu Soll-Bestand aus Kassenbuch.
    Bei Differenz wird automatisch eine Ausgleichsbuchung erstellt.
    """

    __tablename__ = "cash_counts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    cash_register_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cash_registers.id", ondelete="CASCADE"),
        nullable=False
    )

    # Zeitpunkt
    count_date = Column(Date, nullable=False)
    count_time = Column(Time, nullable=False)

    # Muenzen (Stueckzahl)
    coins_1_cent = Column(Integer, default=0)
    coins_2_cent = Column(Integer, default=0)
    coins_5_cent = Column(Integer, default=0)
    coins_10_cent = Column(Integer, default=0)
    coins_20_cent = Column(Integer, default=0)
    coins_50_cent = Column(Integer, default=0)
    coins_1_euro = Column(Integer, default=0)
    coins_2_euro = Column(Integer, default=0)

    # Scheine (Stueckzahl)
    notes_5_euro = Column(Integer, default=0)
    notes_10_euro = Column(Integer, default=0)
    notes_20_euro = Column(Integer, default=0)
    notes_50_euro = Column(Integer, default=0)
    notes_100_euro = Column(Integer, default=0)
    notes_200_euro = Column(Integer, default=0)
    notes_500_euro = Column(Integer, default=0)

    # Soll-Bestand (aus Kassenbuch)
    expected_total = Column(Numeric(15, 2), nullable=False)

    # Bei Differenz automatisch erstellte Buchung
    difference_entry_id = Column(UUID(as_uuid=True), ForeignKey("cash_entries.id"), nullable=True)
    difference_explanation = Column(Text, nullable=True)

    # Signatur
    counted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    verified_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    cash_register = relationship("CashRegister", back_populates="counts")
    difference_entry = relationship("CashEntry")
    counted_by = relationship("User", foreign_keys=[counted_by_id])
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index("ix_cash_counts_company_id", "company_id"),
        Index("ix_cash_counts_register_id", "cash_register_id"),
        Index("ix_cash_counts_date", "count_date"),
    )

    @property
    def total_coins(self) -> float:
        """Berechnet Summe aller Muenzen."""
        return (
            self.coins_1_cent * 0.01 +
            self.coins_2_cent * 0.02 +
            self.coins_5_cent * 0.05 +
            self.coins_10_cent * 0.10 +
            self.coins_20_cent * 0.20 +
            self.coins_50_cent * 0.50 +
            self.coins_1_euro * 1.00 +
            self.coins_2_euro * 2.00
        )

    @property
    def total_notes(self) -> float:
        """Berechnet Summe aller Scheine."""
        return (
            self.notes_5_euro * 5 +
            self.notes_10_euro * 10 +
            self.notes_20_euro * 20 +
            self.notes_50_euro * 50 +
            self.notes_100_euro * 100 +
            self.notes_200_euro * 200 +
            self.notes_500_euro * 500
        )

    @property
    def counted_total(self) -> float:
        """Berechnet Gesamtsumme (Ist-Bestand)."""
        return self.total_coins + self.total_notes

    @property
    def difference(self) -> float:
        """Berechnet Differenz (Ist - Soll)."""
        return self.counted_total - float(self.expected_total)

    def __repr__(self) -> str:
        return f"<CashCount {self.count_date} Ist={self.counted_total} Soll={self.expected_total}>"


# =============================================================================
# KASSE-MODUL: SPESENABRECHNUNG
# =============================================================================


class ExpenseReport(Base):
    """Spesenabrechnung eines Mitarbeiters.

    Sammelt alle Spesenpositionen eines Zeitraums mit Workflow:
    Entwurf -> Eingereicht -> In Pruefung -> Genehmigt/Abgelehnt -> Ausgezahlt
    """

    __tablename__ = "expense_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Identifikation
    report_number = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Zeitraum
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Mitarbeiter
    employee_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    employee_name = Column(String(255), nullable=True)  # Denormalisiert

    # Betraege (berechnet aus Positionen)
    total_amount = Column(Numeric(15, 2), default=0)
    total_vat = Column(Numeric(15, 2), default=0)
    total_deductible = Column(Numeric(15, 2), default=0)

    # Reisekosten-Pauschalen
    travel_days = Column(Integer, default=0)
    travel_allowance_total = Column(Numeric(15, 2), default=0)

    # Kilometergeld
    total_kilometers = Column(Numeric(10, 2), default=0)
    mileage_allowance_total = Column(Numeric(15, 2), default=0)

    # Status-Workflow
    status = Column(String(50), default="draft")

    # Workflow-Timestamps
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    review_notes = Column(Text, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    paid_at = Column(DateTime(timezone=True), nullable=True)
    paid_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    payment_method = Column(String(50), nullable=True)
    payment_reference = Column(String(100), nullable=True)

    # Verknuepfung zu Kassenbuch
    cash_entry_id = Column(UUID(as_uuid=True), ForeignKey("cash_entries.id"), nullable=True)

    # DATEV
    datev_exported_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Soft-Delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="expense_reports")
    employee = relationship("User", foreign_keys=[employee_id])
    items = relationship(
        "ExpenseItem",
        back_populates="expense_report",
        cascade="all, delete-orphan",
        order_by="ExpenseItem.expense_date"
    )
    cash_entry = relationship("CashEntry", foreign_keys=[cash_entry_id])

    __table_args__ = (
        Index("ix_expense_reports_company_id", "company_id"),
        Index("ix_expense_reports_employee_id", "employee_id"),
        Index("ix_expense_reports_status", "status"),
        Index("ix_expense_reports_period", "period_start", "period_end"),
        Index("ix_expense_reports_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ExpenseReport {self.report_number} ({self.status})>"


class ExpenseItem(Base):
    """Einzelposition einer Spesenabrechnung.

    Unterstuetzt verschiedene Typen:
    - RECEIPT: Belegausgabe (mit gescanntem Beleg)
    - MILEAGE: Kilometergeld (0,30 EUR/km)
    - PER_DIEM: Verpflegungspauschale (14/28 EUR)
    - FLAT_RATE: Sonstige Pauschale
    """

    __tablename__ = "expense_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expense_report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("expense_reports.id", ondelete="CASCADE"),
        nullable=False
    )

    # Kategorisierung
    category_id = Column(UUID(as_uuid=True), ForeignKey("cash_categories.id"), nullable=True)
    expense_type = Column(String(50), nullable=False)  # ExpenseType

    # Datum
    expense_date = Column(Date, nullable=False)

    # Betrag
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(3), default="EUR")

    # Steuer
    tax_rate = Column(Numeric(5, 2), nullable=True)
    tax_amount = Column(Numeric(15, 2), nullable=True)
    net_amount = Column(Numeric(15, 2), nullable=True)

    # Abzugsfaehigkeit
    is_deductible = Column(Boolean, default=True)
    deductible_percentage = Column(Integer, default=100)
    deductible_amount = Column(Numeric(15, 2), nullable=True)

    # Beschreibung
    description = Column(Text, nullable=False)

    # Beleg
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    receipt_number = Column(String(100), nullable=True)

    # Geschaeftspartner
    vendor_name = Column(String(255), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True)

    # Bewirtung (wenn expense_type = receipt & category = entertainment)
    entertainment_participants = Column(CrossDBJSON, nullable=True)  # ["Name1", "Name2"]
    entertainment_occasion = Column(Text, nullable=True)
    entertainment_location = Column(String(255), nullable=True)

    # Kilometergeld (wenn expense_type = mileage)
    mileage_from = Column(String(255), nullable=True)
    mileage_to = Column(String(255), nullable=True)
    mileage_kilometers = Column(Numeric(10, 2), nullable=True)
    mileage_rate = Column(Numeric(5, 2), default=0.30)  # EUR/km
    mileage_vehicle_type = Column(String(50), nullable=True)  # pkw, motorrad
    mileage_license_plate = Column(String(20), nullable=True)

    # Verpflegungspauschale (wenn expense_type = per_diem)
    per_diem_hours = Column(Numeric(4, 1), nullable=True)
    per_diem_rate = Column(Numeric(5, 2), nullable=True)  # 14 oder 28
    per_diem_breakfast_provided = Column(Boolean, default=False)
    per_diem_lunch_provided = Column(Boolean, default=False)
    per_diem_dinner_provided = Column(Boolean, default=False)

    # Buchhaltung
    skr_account = Column(String(10), nullable=True)
    cost_center = Column(String(50), nullable=True)

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    expense_report = relationship("ExpenseReport", back_populates="items")
    category = relationship("CashCategory")
    document = relationship("Document")
    vendor = relationship("BusinessEntity")

    __table_args__ = (
        Index("ix_expense_items_report_id", "expense_report_id"),
        Index("ix_expense_items_date", "expense_date"),
        Index("ix_expense_items_document_id", "document_id"),
        Index("ix_expense_items_type", "expense_type"),
    )

    def __repr__(self) -> str:
        return f"<ExpenseItem {self.expense_date} {self.amount} {self.currency}>"


# =============================================================================
# STRECKENGESCHÄFT / DREIECKSGESCHÄFT MODELS
# =============================================================================


class TransactionType(str, Enum):
    """Classification type for drop shipment transactions."""
    STANDARD = "standard"              # Normal warehouse transaction
    DROP_SHIPMENT = "drop_shipment"    # Streckengeschäft (2 parties)
    TRIANGULAR_EU = "triangular_eu"    # EU Dreiecksgeschäft §25b UStG
    CHAIN_TRANSACTION = "chain_transaction"  # Reihengeschäft (3+ parties)
    UNKNOWN = "unknown"                # Needs manual classification


class DropShipmentCompanyRole(str, Enum):
    """Role of German company in the transaction."""
    FIRST_SUPPLIER = "first_supplier"    # Erster Lieferer
    INTERMEDIATE = "intermediate"         # Zwischenhändler (mittlerer Abnehmer)
    FINAL_BUYER = "final_buyer"          # Letzter Abnehmer
    NOT_APPLICABLE = "not_applicable"    # Standard transaction


class MovingDelivery(str, Enum):
    """Which delivery is the moving delivery (§3 Abs. 6a UStG)."""
    TO_INTERMEDIATE = "to_intermediate"      # Lieferung AN den Zwischenhändler
    FROM_INTERMEDIATE = "from_intermediate"  # Lieferung VOM Zwischenhändler
    UNDETERMINED = "undetermined"            # Noch nicht bestimmt


class ConfidenceLevel(str, Enum):
    """Classification confidence level."""
    DEFINITIVE = "definitive"       # 100% - ERP marker, legal reference
    HIGH = "high"                   # 90-99% - Strong indicators
    MEDIUM = "medium"               # 70-89% - Multiple weak indicators
    LOW = "low"                     # 50-69% - Single weak indicator
    MANUAL_REQUIRED = "manual_required"  # <50% - Conflicting signals


class VatCategoryType(str, Enum):
    """VAT treatment category for drop shipment."""
    STANDARD_DE = "standard_de"           # Normal German VAT (19% or 7%)
    INTRA_COMMUNITY = "intra_community"   # Innergemeinschaftliche Lieferung
    REVERSE_CHARGE = "reverse_charge"     # Steuerschuldnerschaft Empfänger
    EXPORT = "export"                     # Ausfuhr Drittland (steuerfrei)
    TRIANGULAR_MIDDLE = "triangular_middle"  # §25b Zwischenhändler
    TRIANGULAR_FINAL = "triangular_final"    # §25b Endabnehmer


class DropShipmentClassification(Base):
    """
    Drop shipment classification at document level.
    Implements detection of Streckengeschäft, Dreiecksgeschäft (§25b UStG),
    and Reihengeschäfte (§3 Abs. 6a UStG).
    """
    __tablename__ = "drop_shipment_classifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
                        nullable=False, index=True)

    # Classification results
    transaction_type = Column(String(30), nullable=False, default=TransactionType.UNKNOWN.value)
    company_role = Column(String(30), nullable=False, default=DropShipmentCompanyRole.NOT_APPLICABLE.value)
    moving_delivery = Column(String(30), default=MovingDelivery.UNDETERMINED.value)
    vat_category = Column(String(30), nullable=False, default=VatCategoryType.STANDARD_DE.value)

    # Confidence and validation
    confidence_level = Column(String(20), nullable=False, default=ConfidenceLevel.MANUAL_REQUIRED.value)
    confidence_score = Column(Integer, nullable=False, default=0)
    is_validated = Column(Boolean, default=False)
    validated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Indicators that triggered classification (JSONB)
    indicators = Column(CrossDBJSON, nullable=False, default=list)
    conflicts = Column(CrossDBJSON, nullable=True)

    # EU parties involved (for triangular transactions)
    party_count = Column(Integer, default=2)
    eu_countries_involved = Column(CrossDBJSON, nullable=True)  # ["DE", "AT", "NL"]

    # DATEV integration
    datev_account_debit = Column(String(10), nullable=True)
    datev_account_credit = Column(String(10), nullable=True)
    datev_tax_code = Column(String(5), nullable=True)
    zm_relevant = Column(Boolean, default=False)
    zm_marker = Column(String(1), nullable=True)  # '1' for triangular

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Soft-Delete (GDPR/GoBD compliance)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="false")
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    document = relationship("Document", backref="drop_shipment_classification")
    deleter = relationship("User", foreign_keys=[deleted_by])
    validator = relationship("User", foreign_keys=[validated_by])
    positions = relationship("DropShipmentPosition", back_populates="classification",
                            cascade="all, delete-orphan")
    parties = relationship("TransactionParty", back_populates="classification",
                          cascade="all, delete-orphan")
    proof_documents = relationship("ProofDocument", back_populates="classification",
                                   cascade="all, delete-orphan")
    audit_logs = relationship("ClassificationAuditLog", back_populates="classification",
                             cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_classification_type", "transaction_type"),
        Index("ix_classification_confidence", "confidence_level", "is_validated"),
        Index("ix_classification_zm", "zm_relevant", "created_at"),
        CheckConstraint("confidence_score >= 0 AND confidence_score <= 100",
                       name="valid_confidence_score"),
        CheckConstraint("party_count >= 2 AND party_count <= 10",
                       name="valid_party_count"),
    )

    def __repr__(self) -> str:
        return f"<DropShipmentClassification {self.transaction_type} {self.confidence_level}>"


class DropShipmentPosition(Base):
    """
    Position-level classification for mixed invoices (Mischbestellungen).
    A single invoice can contain both warehouse and drop-shipment positions.
    """
    __tablename__ = "drop_shipment_positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"),
                        nullable=False)

    # Position identification
    position_number = Column(Integer, nullable=False)
    article_number = Column(String(100), nullable=True)
    article_description = Column(Text, nullable=True)
    quantity = Column(Numeric(12, 3), nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True)
    line_total = Column(Numeric(12, 2), nullable=True)

    # Position-level classification
    is_drop_shipment = Column(Boolean, nullable=False, default=False)
    warehouse_code = Column(String(20), nullable=True)
    erp_position_type = Column(String(10), nullable=True)  # TAS, TAN, etc.

    # VAT treatment for this position
    vat_category = Column(String(30), nullable=True)
    vat_rate = Column(Numeric(5, 2), nullable=True)

    # DATEV account for this position
    datev_revenue_account = Column(String(10), nullable=True)
    datev_expense_account = Column(String(10), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="positions")
    document = relationship("Document")

    __table_args__ = (
        Index("ix_positions_drop_ship", "is_drop_shipment"),
        # Unique constraint: one entry per position per document
        # Note: handled in migration
    )

    def __repr__(self) -> str:
        return f"<DropShipmentPosition {self.position_number} drop={self.is_drop_shipment}>"


class VatIdRegistry(Base):
    """
    VAT ID registry for party identification and VIES validation.
    Caches EU VIES validation results.
    """
    __tablename__ = "vat_id_registry"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vat_id = Column(String(20), nullable=False, unique=True)
    country_code = Column(String(2), nullable=False, index=True)
    company_name = Column(String(255), nullable=True)

    # Validation status (VIES check)
    is_valid = Column(Boolean, nullable=True)
    last_validated = Column(DateTime(timezone=True), nullable=True)
    validation_response = Column(CrossDBJSON, nullable=True)

    # Internal reference (links to BusinessEntity, which unifies customers and suppliers)
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    business_entity = relationship("BusinessEntity")

    def __repr__(self) -> str:
        return f"<VatIdRegistry {self.vat_id} valid={self.is_valid}>"


class TransactionParty(Base):
    """
    Party information extracted from documents for drop shipment classification.
    Tracks all parties in the transaction chain.
    """
    __tablename__ = "transaction_parties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)

    # Party role in the chain
    party_role = Column(String(30), nullable=False)  # seller, buyer, ship_to, bill_to, carrier
    sequence_number = Column(Integer, nullable=False)  # Position in chain: 1=first, 2=middle, 3=last

    # Party identification
    company_name = Column(String(255), nullable=True)
    vat_id = Column(String(20), nullable=True)
    country_code = Column(String(2), nullable=True)

    # Address
    street = Column(String(255), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), nullable=True)

    # Source of extraction
    source_field = Column(String(50), nullable=True)  # invoice_address, delivery_address, cmr_consignee

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="parties")

    def __repr__(self) -> str:
        return f"<TransactionParty {self.party_role} {self.company_name}>"


class ProofDocument(Base):
    """
    Document evidence chain for proof archive.
    Tracks required proofs for tax-free treatment (Gelangensnachweis, CMR, etc.)
    """
    __tablename__ = "proof_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"),
                        nullable=True)

    # Proof type: invoice, delivery_note, cmr, gelangensbestaetigung, speditionsauftrag, vat_id_proof
    proof_type = Column(String(50), nullable=False)

    is_present = Column(Boolean, default=False)
    is_complete = Column(Boolean, default=False)
    missing_fields = Column(CrossDBJSON, nullable=True)  # Array of missing field names

    # For CMR: Field 24 extraction
    cmr_field_24_signed = Column(Boolean, nullable=True)
    cmr_field_24_date = Column(Date, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="proof_documents")
    document = relationship("Document")

    def __repr__(self) -> str:
        return f"<ProofDocument {self.proof_type} present={self.is_present}>"


class ClassificationAuditLog(Base):
    """
    Immutable audit log for classification changes.
    Required for GoBD compliance and tax audit trail.
    """
    __tablename__ = "classification_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    classification_id = Column(UUID(as_uuid=True),
                               ForeignKey("drop_shipment_classifications.id", ondelete="CASCADE"),
                               nullable=False, index=True)

    # Action: created, auto_classified, manually_validated, overridden, exported_datev, zm_reported
    action = Column(String(50), nullable=False)

    previous_value = Column(CrossDBJSON, nullable=True)
    new_value = Column(CrossDBJSON, nullable=True)
    reason = Column(Text, nullable=True)

    performed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())

    # System info for audit
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    # Relationships
    classification = relationship("DropShipmentClassification", back_populates="audit_logs")
    user = relationship("User")

    def __repr__(self) -> str:
        return f"<ClassificationAuditLog {self.action} at {self.performed_at}>"


class DatevStreckengeschaeftAccount(Base):
    """
    DATEV account mapping configuration for drop shipment transactions.
    Maps company role and transaction type to SKR03/SKR04 accounts.
    """
    __tablename__ = "datev_streckengeschaeft_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    kontenrahmen = Column(String(5), nullable=False)  # SKR03, SKR04
    company_role = Column(String(30), nullable=False)
    transaction_type = Column(String(30), nullable=False)

    # Account numbers
    revenue_account = Column(String(10), nullable=True)
    expense_account = Column(String(10), nullable=True)
    tax_code = Column(String(5), nullable=True)

    # UStVA mapping
    ustva_kennzahl = Column(String(5), nullable=True)
    zm_kennzeichen = Column(String(1), nullable=True)

    description_de = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        # Unique constraint for mapping lookup
        Index("ix_datev_account_lookup", "kontenrahmen", "company_role", "transaction_type"),
    )

    def __repr__(self) -> str:
        return f"<DatevStreckengeschaeftAccount {self.kontenrahmen} {self.transaction_type}>"


class ClassificationIndicator(Base):
    """
    Classification indicator configuration.
    Defines detection patterns and weights for automatic classification.
    """
    __tablename__ = "classification_indicators"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    indicator_code = Column(String(50), nullable=False, unique=True)
    indicator_name_de = Column(String(100), nullable=False)
    indicator_name_en = Column(String(100), nullable=True)

    weight = Column(Integer, nullable=False, default=50)
    is_definitive = Column(Boolean, default=False)
    applies_to_incoming = Column(Boolean, default=True)
    applies_to_outgoing = Column(Boolean, default=True)

    detection_pattern = Column(Text, nullable=True)  # Regex pattern
    detection_field = Column(String(50), nullable=True)

    is_active = Column(Boolean, default=True)

    __table_args__ = (
        CheckConstraint("weight >= 0 AND weight <= 100", name="valid_indicator_weight"),
    )

    def __repr__(self) -> str:
        return f"<ClassificationIndicator {self.indicator_code} weight={self.weight}>"


class ZmSubmissionStatus(str, Enum):
    """Status der ZM-Meldung."""
    DRAFT = "draft"               # Entwurf (noch nicht eingereicht)
    SUBMITTED = "submitted"       # Bei BZSt eingereicht
    CONFIRMED = "confirmed"       # Eingang bestätigt
    CORRECTED = "corrected"       # Korrigierte Meldung eingereicht
    CANCELLED = "cancelled"       # Storniert


class ZmSubmission(Base):
    """
    Zusammenfassende Meldung (ZM) Einreichungsstatus.
    Trackt den Status der monatlichen ZM-Meldung pro Periode.

    Die ZM muss bis zum 25. des Folgemonats beim BZSt eingereicht werden.
    """
    __tablename__ = "zm_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Periode (z.B. "2024-12" für Dezember 2024)
    period = Column(String(7), nullable=False, index=True)

    # User/Company
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                    nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="SET NULL"),
                       nullable=True)

    # Status und Submission Details
    status = Column(String(20), nullable=False, default=ZmSubmissionStatus.DRAFT.value)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # BZSt-Referenz (nach Einreichung)
    bzst_reference = Column(String(100), nullable=True)
    bzst_response_code = Column(String(20), nullable=True)
    bzst_response_message = Column(Text, nullable=True)

    # Inhalt der Meldung (Snapshot zum Zeitpunkt der Einreichung)
    total_amount = Column(Numeric(15, 2), nullable=True)
    record_count = Column(Integer, nullable=True)
    triangular_count = Column(Integer, nullable=True)
    countries_involved = Column(CrossDBJSON, nullable=True)  # ["AT", "NL", ...]

    # Deadline (25. des Folgemonats)
    deadline = Column(Date, nullable=False)
    is_late = Column(Boolean, default=False)

    # Korrektur-Referenz (falls dies eine Korrekturmeldung ist)
    original_submission_id = Column(UUID(as_uuid=True),
                                   ForeignKey("zm_submissions.id", ondelete="SET NULL"),
                                   nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    submitter = relationship("User", foreign_keys=[submitted_by])
    company = relationship("Company")
    original_submission = relationship("ZmSubmission", remote_side=[id])

    __table_args__ = (
        # Unique constraint: Eine Meldung pro Periode pro User
        Index("ix_zm_submission_period_user", "period", "user_id", unique=True),
        Index("ix_zm_submission_status", "status"),
        Index("ix_zm_submission_deadline", "deadline"),
    )

    def __repr__(self) -> str:
        return f"<ZmSubmission {self.period} status={self.status}>"


# =============================================================================
# PERSONAL-MODUL: ENTERPRISE HR
# =============================================================================


class EmploymentType(str, Enum):
    """Beschaeftigungsart."""
    FULL_TIME = "full_time"               # Vollzeit
    PART_TIME = "part_time"               # Teilzeit
    MINI_JOB = "mini_job"                 # Minijob (520 EUR)
    TEMPORARY = "temporary"               # Befristet
    TRAINEE = "trainee"                   # Auszubildender
    INTERN = "intern"                     # Praktikant
    FREELANCE = "freelance"               # Freiberuflich
    WORKING_STUDENT = "working_student"   # Werkstudent


class EmployeeStatus(str, Enum):
    """Mitarbeiter-Status."""
    ONBOARDING = "onboarding"             # In Einarbeitung
    ACTIVE = "active"                     # Aktiv
    ON_LEAVE = "on_leave"                 # Beurlaubt
    SICK = "sick"                         # Langzeitkrank
    NOTICE_PERIOD = "notice_period"       # In Kuendigung
    TERMINATED = "terminated"             # Ausgeschieden


class LeaveType(str, Enum):
    """Abwesenheitstyp."""
    VACATION = "vacation"                 # Urlaub
    SICK = "sick"                         # Krank
    SICK_CHILD = "sick_child"             # Kind krank
    PARENTAL = "parental"                 # Elternzeit
    SPECIAL = "special"                   # Sonderurlaub
    UNPAID = "unpaid"                     # Unbezahlter Urlaub
    TRAINING = "training"                 # Weiterbildung
    BUSINESS_TRIP = "business_trip"       # Dienstreise
    HOME_OFFICE = "home_office"           # Homeoffice


class LeaveRequestStatus(str, Enum):
    """Urlaubsantrag-Status."""
    DRAFT = "draft"                       # Entwurf
    SUBMITTED = "submitted"               # Eingereicht
    APPROVED = "approved"                 # Genehmigt
    REJECTED = "rejected"                 # Abgelehnt
    CANCELLED = "cancelled"               # Storniert


class ContractStatus(str, Enum):
    """Arbeitsvertrag-Status."""
    DRAFT = "draft"                       # Entwurf
    PENDING_SIGNATURE = "pending_signature"  # Warten auf Unterschrift
    ACTIVE = "active"                     # Aktiv
    TERMINATED = "terminated"             # Beendet


class TrainingStatus(str, Enum):
    """Weiterbildungs-Status."""
    PLANNED = "planned"                   # Geplant
    REGISTERED = "registered"             # Angemeldet
    IN_PROGRESS = "in_progress"           # Laufend
    COMPLETED = "completed"               # Abgeschlossen
    CANCELLED = "cancelled"               # Abgebrochen


class ReviewStatus(str, Enum):
    """Beurteilungs-Status."""
    DRAFT = "draft"                       # Entwurf
    PENDING_EMPLOYEE = "pending_employee" # Warten auf Mitarbeiter-Kommentar
    PENDING_HR = "pending_hr"             # Warten auf HR-Freigabe
    COMPLETED = "completed"               # Abgeschlossen


class OnboardingTaskStatus(str, Enum):
    """Onboarding-Aufgaben-Status."""
    PENDING = "pending"                   # Ausstehend
    IN_PROGRESS = "in_progress"           # In Bearbeitung
    COMPLETED = "completed"               # Erledigt
    SKIPPED = "skipped"                   # Uebersprungen


class HRDocumentCategory(str, Enum):
    """HR-Dokument Kategorien."""
    VERTRAEGE = "vertraege"               # Vertraege & Stammdaten
    STAMMDATEN = "stammdaten"             # Stammdaten
    LOHN = "lohn"                         # Lohn & Gehalt
    URLAUB = "urlaub"                     # Urlaub & Abwesenheit
    WEITERBILDUNG = "weiterbildung"       # Weiterbildung
    BEURTEILUNG = "beurteilung"           # Beurteilung
    SONSTIGES = "sonstiges"               # Sonstiges


class Department(Base):
    """Abteilung mit hierarchischer Struktur.

    Ermoeglicht die Abbildung einer Organisationsstruktur mit
    beliebig tiefer Verschachtelung (parent_id).
    """

    __tablename__ = "departments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True
    )

    # Identifikation
    name = Column(String(100), nullable=False)
    short_name = Column(String(20), nullable=True)
    description = Column(Text, nullable=True)
    cost_center = Column(String(50), nullable=True)

    # Manager (wird spaeter gesetzt, da Employee noch nicht existiert)
    manager_id = Column(UUID(as_uuid=True), nullable=True)

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company")
    parent = relationship("Department", remote_side=[id], backref="children")

    __table_args__ = (
        Index("ix_departments_company_id", "company_id"),
        Index("ix_departments_parent_id", "parent_id"),
        Index("ix_departments_is_active", "is_active"),
        Index("ix_departments_deleted_at", "deleted_at"),
        Index("ix_departments_company_name", "company_id", "name"),
    )

    def __repr__(self) -> str:
        return f"<Department {self.name}>"


class Position(Base):
    """Stelle/Rolle innerhalb einer Firma.

    Definiert Stellenbezeichnungen mit optionalem Gehaltsrahmen
    und Zuordnung zu einer Abteilung.
    """

    __tablename__ = "positions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True
    )

    # Bezeichnung
    title = Column(String(200), nullable=False)
    title_en = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)

    # Klassifizierung
    level = Column(Integer, default=1)  # Hierarchie-Ebene
    job_family = Column(String(100), nullable=True)  # z.B. "Engineering", "Sales"

    # Gehaltsrahmen
    salary_band_min = Column(Numeric(10, 2), nullable=True)
    salary_band_max = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company")
    department = relationship("Department")

    __table_args__ = (
        Index("ix_positions_company_id", "company_id"),
        Index("ix_positions_department_id", "department_id"),
        Index("ix_positions_is_active", "is_active"),
        Index("ix_positions_title", "title"),
    )

    def __repr__(self) -> str:
        return f"<Position {self.title}>"


class Employee(Base):
    """Mitarbeiter-Stammdaten.

    Zentrale Entitaet fuer alle HR-Daten eines Mitarbeiters.
    Kann optional mit einem User-Account verknuepft sein.
    """

    __tablename__ = "employees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Verknuepfung zum User (falls Mitarbeiter auch Systemzugang hat)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Identifikation
    employee_number = Column(String(50), nullable=False)  # Personalnummer

    # Persoenliche Daten
    salutation = Column(String(20), nullable=True)  # Herr/Frau
    title = Column(String(50), nullable=True)  # Dr., Prof., etc.
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    birth_name = Column(String(100), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    place_of_birth = Column(String(100), nullable=True)
    nationality = Column(String(50), nullable=True)
    gender = Column(String(20), nullable=True)

    # Kontakt (geschaeftlich)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    mobile = Column(String(50), nullable=True)

    # Kontakt (privat)
    private_email = Column(String(255), nullable=True)
    private_phone = Column(String(50), nullable=True)

    # Adresse (privat)
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")

    # Notfall-Kontakt
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(50), nullable=True)
    emergency_contact_relation = Column(String(50), nullable=True)

    # Organisatorisch
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True
    )
    position_id = Column(
        UUID(as_uuid=True),
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True
    )
    supervisor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True
    )

    # Beschaeftigung
    employment_type = Column(String(30), default=EmploymentType.FULL_TIME.value)
    status = Column(String(30), default=EmployeeStatus.ACTIVE.value)
    hire_date = Column(Date, nullable=True)
    probation_end_date = Column(Date, nullable=True)
    termination_date = Column(Date, nullable=True)

    # Arbeitszeit
    weekly_hours = Column(Numeric(5, 2), default=40)
    vacation_days_per_year = Column(Integer, default=30)

    # Steuer & Sozialversicherung
    tax_id = Column(String(20), nullable=True)  # Steuer-ID
    tax_class = Column(String(5), nullable=True)  # Steuerklasse
    social_security_number = Column(String(20), nullable=True)
    health_insurance = Column(String(100), nullable=True)
    health_insurance_number = Column(String(50), nullable=True)

    # Banking
    iban = Column(String(34), nullable=True)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)

    # Profilbild
    photo_path = Column(String(500), nullable=True)

    # Flexible Felder
    custom_fields = Column(CrossDBJSON, default=dict)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Soft-Delete (GDPR/GoBD)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    user = relationship("User", foreign_keys=[user_id])
    department = relationship("Department", foreign_keys=[department_id])
    position = relationship("Position")
    supervisor = relationship("Employee", remote_side=[id], foreign_keys=[supervisor_id])

    # Bidirectional relationships
    contracts = relationship("EmploymentContract", back_populates="employee", order_by="EmploymentContract.start_date.desc()")
    leave_requests = relationship("LeaveRequest", back_populates="employee", foreign_keys="LeaveRequest.employee_id", order_by="LeaveRequest.start_date.desc()")
    absences = relationship("Absence", back_populates="employee", order_by="Absence.start_date.desc()")
    time_entries = relationship("TimeEntry", back_populates="employee", order_by="TimeEntry.date.desc()")
    trainings = relationship("Training", back_populates="employee", order_by="Training.start_date.desc()")
    performance_reviews = relationship("PerformanceReview", back_populates="employee", foreign_keys="PerformanceReview.employee_id")
    onboarding_tasks = relationship("OnboardingTask", back_populates="employee", foreign_keys="OnboardingTask.employee_id", order_by="OnboardingTask.sort_order")
    hr_documents = relationship("HRDocument", back_populates="employee")

    __table_args__ = (
        Index("ix_employees_company_id", "company_id"),
        Index("ix_employees_user_id", "user_id"),
        Index("ix_employees_department_id", "department_id"),
        Index("ix_employees_position_id", "position_id"),
        Index("ix_employees_supervisor_id", "supervisor_id"),
        Index("ix_employees_status", "status"),
        Index("ix_employees_employee_number", "company_id", "employee_number"),
        Index("ix_employees_email", "email"),
        Index("ix_employees_deleted_at", "deleted_at"),
        Index("ix_employees_name", "last_name", "first_name"),
    )

    @property
    def full_name(self) -> str:
        """Vollstaendiger Name."""
        parts = []
        if self.title:
            parts.append(self.title)
        parts.append(self.first_name)
        parts.append(self.last_name)
        return " ".join(parts)

    @property
    def is_deleted(self) -> bool:
        """Prueft ob Mitarbeiter geloescht ist."""
        return self.deleted_at is not None

    def __repr__(self) -> str:
        return f"<Employee {self.employee_number}: {self.first_name} {self.last_name}>"


class EmploymentContract(Base):
    """Arbeitsvertrag mit Versionshistorie.

    Jede Vertragsaenderung erzeugt eine neue Version.
    is_current markiert den aktuell gueltigen Vertrag.
    """

    __tablename__ = "employment_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Versionierung
    version = Column(Integer, default=1)
    is_current = Column(Boolean, default=True)
    supersedes_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employment_contracts.id", ondelete="SET NULL"),
        nullable=True
    )

    # Vertragsdetails
    contract_type = Column(String(30), nullable=False)  # EmploymentType
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # Null = unbefristet

    # Position
    position_id = Column(
        UUID(as_uuid=True),
        ForeignKey("positions.id", ondelete="SET NULL"),
        nullable=True
    )
    job_title = Column(String(200), nullable=False)
    job_description = Column(Text, nullable=True)

    # Arbeitszeit
    weekly_hours = Column(Numeric(5, 2), nullable=False)
    vacation_days = Column(Integer, nullable=False)

    # Verguetung
    salary_type = Column(String(20), default="monthly")  # monthly, hourly
    base_salary = Column(Numeric(10, 2), nullable=False)
    salary_currency = Column(String(3), default="EUR")
    bonus_eligible = Column(Boolean, default=False)
    bonus_target = Column(Numeric(10, 2), nullable=True)

    # Zusatzleistungen
    benefits = Column(CrossDBJSON, default=list)  # ["company_car", "phone", "pension"]

    # Kuendigung
    notice_period_employee = Column(String(50), nullable=True)  # z.B. "1 Monat zum Monatsende"
    notice_period_employer = Column(String(50), nullable=True)

    # Dokument-Referenz
    contract_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Workflow
    status = Column(String(30), default=ContractStatus.DRAFT.value)
    signed_date = Column(Date, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    employee = relationship("Employee", back_populates="contracts")
    position = relationship("Position")
    supersedes = relationship("EmploymentContract", remote_side=[id])
    contract_document = relationship("Document")

    __table_args__ = (
        Index("ix_employment_contracts_employee_id", "employee_id"),
        Index("ix_employment_contracts_is_current", "is_current"),
        Index("ix_employment_contracts_status", "status"),
        Index("ix_employment_contracts_start_date", "start_date"),
    )

    def __repr__(self) -> str:
        return f"<EmploymentContract v{self.version} {self.job_title}>"


class LeaveRequest(Base):
    """Urlaubsantrag mit Workflow.

    Status-Workflow: draft -> submitted -> approved/rejected -> cancelled
    """

    __tablename__ = "leave_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Zeitraum
    leave_type = Column(String(30), nullable=False)  # LeaveType
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    start_half_day = Column(Boolean, default=False)  # Erster Tag nur halbtags
    end_half_day = Column(Boolean, default=False)    # Letzter Tag nur halbtags

    # Berechnung
    total_days = Column(Numeric(5, 2), nullable=False)

    # Beschreibung
    reason = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    # Vertretung
    substitute_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True
    )

    # Workflow
    status = Column(String(30), default=LeaveRequestStatus.DRAFT.value)

    submitted_at = Column(DateTime(timezone=True), nullable=True)

    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_comment = Column(Text, nullable=True)

    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    rejected_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="leave_requests", foreign_keys=[employee_id])
    substitute = relationship("Employee", foreign_keys=[substitute_id])

    __table_args__ = (
        Index("ix_leave_requests_company_id", "company_id"),
        Index("ix_leave_requests_employee_id", "employee_id"),
        Index("ix_leave_requests_status", "status"),
        Index("ix_leave_requests_dates", "start_date", "end_date"),
        Index("ix_leave_requests_leave_type", "leave_type"),
    )

    def __repr__(self) -> str:
        return f"<LeaveRequest {self.leave_type} {self.start_date} - {self.end_date}>"


class Absence(Base):
    """Tatsaechliche Abwesenheit (aus genehmigtem Antrag oder Krankheit).

    Wird automatisch aus genehmigten LeaveRequests erzeugt oder
    manuell fuer Krankheitsfaelle angelegt.
    """

    __tablename__ = "absences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    absence_type = Column(String(30), nullable=False)  # LeaveType
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    total_days = Column(Numeric(5, 2), nullable=False)

    # Verknuepfung zum Urlaubsantrag (optional)
    leave_request_id = Column(
        UUID(as_uuid=True),
        ForeignKey("leave_requests.id", ondelete="SET NULL"),
        nullable=True
    )

    # Bei Krankheit
    sick_note_received = Column(Boolean, default=False)
    sick_note_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    sick_note_valid_from = Column(Date, nullable=True)
    sick_note_valid_until = Column(Date, nullable=True)

    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="absences")
    leave_request = relationship("LeaveRequest")
    sick_note_document = relationship("Document")

    __table_args__ = (
        Index("ix_absences_company_id", "company_id"),
        Index("ix_absences_employee_id", "employee_id"),
        Index("ix_absences_dates", "start_date", "end_date"),
        Index("ix_absences_type", "absence_type"),
        Index("ix_absences_leave_request_id", "leave_request_id"),
    )

    def __repr__(self) -> str:
        return f"<Absence {self.absence_type} {self.start_date} - {self.end_date}>"


class TimeEntry(Base):
    """Zeiterfassung.

    Erfasst Arbeitszeiten eines Mitarbeiters mit optionaler
    Genehmigung durch den Vorgesetzten.
    """

    __tablename__ = "time_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    break_duration_minutes = Column(Integer, default=0)

    # Berechnete Werte
    total_hours = Column(Numeric(5, 2), nullable=True)
    overtime_hours = Column(Numeric(5, 2), default=0)

    # Kategorisierung
    work_type = Column(String(50), default="regular")  # regular, overtime, holiday, on_call
    project_id = Column(String(100), nullable=True)
    cost_center = Column(String(50), nullable=True)

    notes = Column(Text, nullable=True)

    # Status
    is_approved = Column(Boolean, default=False)
    approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="time_entries")

    __table_args__ = (
        Index("ix_time_entries_company_id", "company_id"),
        Index("ix_time_entries_employee_id", "employee_id"),
        Index("ix_time_entries_date", "date"),
        Index("ix_time_entries_employee_date", "employee_id", "date"),
        Index("ix_time_entries_is_approved", "is_approved"),
    )

    def __repr__(self) -> str:
        return f"<TimeEntry {self.date} {self.total_hours}h>"


class Training(Base):
    """Weiterbildung/Schulung.

    Erfasst Schulungen, Zertifizierungen und Fortbildungen
    eines Mitarbeiters.
    """

    __tablename__ = "trainings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    provider = Column(String(200), nullable=True)
    location = Column(String(200), nullable=True)

    # Zeitraum
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    duration_hours = Column(Numeric(6, 2), nullable=True)

    # Kosten
    cost = Column(Numeric(10, 2), nullable=True)
    cost_currency = Column(String(3), default="EUR")
    cost_covered_by = Column(String(50), default="company")  # company, employee, shared

    # Ergebnis
    status = Column(String(30), default=TrainingStatus.PLANNED.value)
    certificate_received = Column(Boolean, default=False)
    certificate_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    certificate_valid_until = Column(Date, nullable=True)

    # Bewertung
    rating = Column(Integer, nullable=True)  # 1-5
    feedback = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="trainings")
    certificate_document = relationship("Document")

    __table_args__ = (
        Index("ix_trainings_company_id", "company_id"),
        Index("ix_trainings_employee_id", "employee_id"),
        Index("ix_trainings_status", "status"),
        Index("ix_trainings_start_date", "start_date"),
    )

    def __repr__(self) -> str:
        return f"<Training {self.title}>"


class PerformanceReview(Base):
    """Mitarbeiterbeurteilung.

    Erfasst Leistungsbeurteilungen mit Ratings, Zielen
    und Entwicklungsplaenen.
    """

    __tablename__ = "performance_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Beurteilungszeitraum
    review_period_start = Column(Date, nullable=False)
    review_period_end = Column(Date, nullable=False)
    review_date = Column(Date, nullable=True)

    # Bewerter
    reviewer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=False
    )

    # Typ
    review_type = Column(String(50), default="annual")  # annual, probation, project, ad_hoc

    # Bewertungen
    overall_rating = Column(Integer, nullable=True)  # 1-5
    ratings = Column(CrossDBJSON, default=dict)  # {"performance": 4, "teamwork": 5, ...}

    # Freitext
    achievements = Column(Text, nullable=True)
    areas_for_improvement = Column(Text, nullable=True)
    development_plan = Column(Text, nullable=True)
    employee_comments = Column(Text, nullable=True)

    # Ziele
    goals_previous_period = Column(CrossDBJSON, default=list)
    goals_next_period = Column(CrossDBJSON, default=list)

    # Workflow
    status = Column(String(30), default=ReviewStatus.DRAFT.value)

    employee_acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    hr_approved_at = Column(DateTime(timezone=True), nullable=True)
    hr_approved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Dokument
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="performance_reviews", foreign_keys=[employee_id])
    reviewer = relationship("Employee", foreign_keys=[reviewer_id])
    document = relationship("Document")

    __table_args__ = (
        Index("ix_performance_reviews_company_id", "company_id"),
        Index("ix_performance_reviews_employee_id", "employee_id"),
        Index("ix_performance_reviews_reviewer_id", "reviewer_id"),
        Index("ix_performance_reviews_status", "status"),
        Index("ix_performance_reviews_period", "review_period_start", "review_period_end"),
    )

    def __repr__(self) -> str:
        return f"<PerformanceReview {self.review_type} {self.review_period_start}>"


class OnboardingTask(Base):
    """Onboarding-Aufgabe fuer neue Mitarbeiter.

    Definiert Checklisten-Elemente fuer den Onboarding-Prozess.
    """

    __tablename__ = "onboarding_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )

    # Aufgabe
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="general")  # it, hr, department, training, general

    # Zuweisung
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True
    )
    due_date = Column(Date, nullable=True)

    # Sortierung
    sort_order = Column(Integer, default=0)
    is_mandatory = Column(Boolean, default=True)

    # Status
    status = Column(String(30), default=OnboardingTaskStatus.PENDING.value)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company")
    employee = relationship("Employee", back_populates="onboarding_tasks", foreign_keys=[employee_id])
    assigned_to = relationship("Employee", foreign_keys=[assigned_to_id])

    __table_args__ = (
        Index("ix_onboarding_tasks_company_id", "company_id"),
        Index("ix_onboarding_tasks_employee_id", "employee_id"),
        Index("ix_onboarding_tasks_status", "status"),
        Index("ix_onboarding_tasks_category", "category"),
        Index("ix_onboarding_tasks_due_date", "due_date"),
    )

    def __repr__(self) -> str:
        return f"<OnboardingTask {self.title}>"


class HRDocument(Base):
    """HR-Dokument-Zuordnung mit Kategorien.

    Verknuepft Dokumente mit Mitarbeitern und kategorisiert sie
    nach HR-spezifischen Kategorien.
    """

    __tablename__ = "hr_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False
    )

    # Kategorisierung
    category = Column(String(50), nullable=False)  # HRDocumentCategory
    subcategory = Column(String(50), nullable=True)

    # Metadaten
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    is_current = Column(Boolean, default=True)

    # Beschreibung
    title = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    employee = relationship("Employee", back_populates="hr_documents")
    document = relationship("Document")

    __table_args__ = (
        Index("ix_hr_documents_employee_id", "employee_id"),
        Index("ix_hr_documents_document_id", "document_id"),
        Index("ix_hr_documents_category", "category"),
        Index("ix_hr_documents_employee_category", "employee_id", "category"),
        Index("ix_hr_documents_is_current", "is_current"),
    )


# =============================================================================
# PRIVAT-MODUL: Persoenliches Dokumentenmanagement
# =============================================================================

class PrivatSpaceType(str, Enum):
    """Typ des privaten Bereichs."""
    PERSONAL = "personal"
    SHARED = "shared"


class PrivatAccessLevel(str, Enum):
    """Zugriffsebenen fuer Privat-Bereiche."""
    NONE = "none"
    VIEW = "view"
    EDIT = "edit"
    MANAGE = "manage"


class PrivatDocumentType(str, Enum):
    """Dokumenttypen im Privat-Bereich."""
    # Immobilien
    PROPERTY_DEED = "property_deed"
    PURCHASE_CONTRACT = "purchase_contract"
    RENTAL_AGREEMENT = "rental_agreement"
    UTILITY_BILL = "utility_bill"
    PROPERTY_TAX = "property_tax"
    # Fahrzeuge
    VEHICLE_REGISTRATION = "vehicle_registration"
    VEHICLE_TITLE = "vehicle_title"
    INSURANCE_POLICY = "insurance_policy"
    SERVICE_RECORD = "service_record"
    FUEL_RECEIPT = "fuel_receipt"
    # Versicherungen
    INSURANCE_CONTRACT = "insurance_contract"
    INSURANCE_CLAIM = "insurance_claim"
    PENSION_STATEMENT = "pension_statement"
    # Steuern
    TAX_RETURN = "tax_return"
    TAX_ASSESSMENT = "tax_assessment"
    # Allgemein
    BANK_STATEMENT = "bank_statement"
    INVESTMENT_REPORT = "investment_report"
    LOAN_AGREEMENT = "loan_agreement"
    OTHER = "other"


class PrivatDeadlineType(str, Enum):
    """Typen von Fristen."""
    EXPIRY = "expiry"
    PAYMENT = "payment"
    RENEWAL = "renewal"
    CANCELLATION = "cancellation"
    REVIEW = "review"
    CUSTOM = "custom"


class PrivatEmergencyAccessStatus(str, Enum):
    """Status des Notfallzugriffs."""
    PENDING = "pending"
    ACTIVE = "active"
    GRANTED = "granted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class PrivatSpace(Base):
    """Privater Bereich - Container fuer private Dokumente."""
    __tablename__ = "privat_spaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Typ und Owner
    space_type = Column(String(20), nullable=False, default=PrivatSpaceType.PERSONAL.value)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)

    # Identifikation
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="Lock")
    color = Column(String(7), default="#6366F1")

    # Verschluesselung
    encryption_enabled = Column(Boolean, default=True)
    encryption_key_hash = Column(String(64), nullable=True)

    # Statistiken
    document_count = Column(Integer, default=0)
    folder_count = Column(Integer, default=0)
    total_size_bytes = Column(BigInteger, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], backref="privat_spaces")
    company = relationship("Company", foreign_keys=[company_id])
    folders = relationship("PrivatFolder", back_populates="space", cascade="all, delete-orphan")
    access_grants = relationship("PrivatSpaceAccess", back_populates="space", cascade="all, delete-orphan")
    documents = relationship("PrivatDocument", back_populates="space", cascade="all, delete-orphan")
    properties = relationship("PrivatProperty", back_populates="space", cascade="all, delete-orphan")
    vehicles = relationship("PrivatVehicle", back_populates="space", cascade="all, delete-orphan")
    insurances = relationship("PrivatInsurance", back_populates="space", cascade="all, delete-orphan")
    loans = relationship("PrivatLoan", back_populates="space", cascade="all, delete-orphan")
    investments = relationship("PrivatInvestment", back_populates="space", cascade="all, delete-orphan")
    deadlines = relationship("PrivatDeadline", back_populates="space", cascade="all, delete-orphan")
    emergency_contacts = relationship("PrivatEmergencyContact", back_populates="space", cascade="all, delete-orphan")
    # Enterprise Intelligence
    recurring_payments = relationship("PrivatRecurringPayment", back_populates="space", cascade="all, delete-orphan")
    coverage_gaps = relationship("PrivatCoverageGap", back_populates="space", cascade="all, delete-orphan")
    # Predictive Intelligence
    kpi_history = relationship("PrivatKPIHistory", back_populates="space", cascade="all, delete-orphan")
    projections = relationship("PrivatProjection", back_populates="space", cascade="all, delete-orphan")
    early_warnings = relationship("PrivatEarlyWarning", back_populates="space", cascade="all, delete-orphan")
    tasks = relationship("PrivatTask", back_populates="space", cascade="all, delete-orphan")
    # Portfolio & Financial Goals (Enterprise Feature)
    portfolio_snapshots = relationship("PortfolioSnapshot", back_populates="space", cascade="all, delete-orphan")
    financial_goals = relationship("FinancialGoal", back_populates="space", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_spaces_owner_id", "owner_id"),
        Index("ix_privat_spaces_company_id", "company_id"),
        Index("ix_privat_spaces_type", "space_type"),
        Index("ix_privat_spaces_deleted_at", "deleted_at"),
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def is_active(self) -> bool:
        """Returns True if space is not soft-deleted (inverse of is_deleted)."""
        return self.deleted_at is None


class PrivatSpaceAccess(Base):
    """Zugriffsberechtigung fuer Privat-Bereiche."""
    __tablename__ = "privat_space_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Zugriffsebene
    access_level = Column(String(20), nullable=False, default=PrivatAccessLevel.VIEW.value)

    # Wer hat Zugriff erteilt
    granted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Zeitliche Begrenzung
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="access_grants")
    user = relationship("User", foreign_keys=[user_id], backref="privat_access_grants")
    granted_by = relationship("User", foreign_keys=[granted_by_id])

    __table_args__ = (
        Index("ix_privat_space_access_space_id", "space_id"),
        Index("ix_privat_space_access_user_id", "user_id"),
        Index("ix_privat_space_access_expires_at", "expires_at"),
    )

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        from datetime import datetime, timezone
        return self.expires_at < datetime.now(timezone.utc)


class PrivatFolder(Base):
    """Flexible Ordnerstruktur fuer private Dokumente."""
    __tablename__ = "privat_folders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="CASCADE"), nullable=True)

    # Ordner-Info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(50), default="Folder")
    color = Column(String(7), nullable=True)

    # Materialized Path
    path = Column(String(2000), nullable=False)
    level = Column(Integer, default=0)

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Kategorie-Typ
    category_type = Column(String(50), nullable=True)

    # Statistiken
    document_count = Column(Integer, default=0)
    subfolder_count = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="folders")
    parent = relationship("PrivatFolder", remote_side=[id], backref="children")
    documents = relationship("PrivatDocument", back_populates="folder")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_privat_folders_space_id", "space_id"),
        Index("ix_privat_folders_parent_id", "parent_id"),
        Index("ix_privat_folders_path", "path"),
        Index("ix_privat_folders_category_type", "category_type"),
        Index("ix_privat_folders_deleted_at", "deleted_at"),
    )


class PrivatDocument(Base):
    """Privates Dokument mit optionaler zusaetzlicher Verschluesselung."""
    __tablename__ = "privat_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Verknuepfung zum System-Dokument
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    # Dokument-Info
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    document_type = Column(String(50), default=PrivatDocumentType.OTHER.value)

    # Datei-Info
    file_path = Column(String(500), nullable=True)
    file_name = Column(String(255), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Zusaetzliche Verschluesselung
    extra_encrypted = Column(Boolean, default=False)
    encryption_salt = Column(String(64), nullable=True)
    encryption_hint = Column(String(255), nullable=True)

    # Fristenmanagement
    expiry_date = Column(Date, nullable=True)
    reminder_days = Column(Integer, nullable=True)
    reminder_sent = Column(Boolean, default=False)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)

    # Metadaten
    doc_metadata = Column(CrossDBJSON, default=dict)  # 'metadata' ist SQLAlchemy reserved!
    tags = Column(CrossDBJSON, default=list)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Status - konsistent mit anderen Privat-Entitaeten
    is_active = Column(Boolean, default=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="documents")
    folder = relationship("PrivatFolder", back_populates="documents")
    document = relationship("Document")
    created_by = relationship("User", foreign_keys=[created_by_id])
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])
    deadlines = relationship("PrivatDeadline", back_populates="privat_document", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_documents_space_id", "space_id"),
        Index("ix_privat_documents_folder_id", "folder_id"),
        Index("ix_privat_documents_document_type", "document_type"),
        Index("ix_privat_documents_expiry_date", "expiry_date"),
        Index("ix_privat_documents_deleted_at", "deleted_at"),
        Index("ix_privat_documents_is_active", "is_active"),
    )


class PrivatProperty(Base):
    """Immobilien-Stammdaten."""
    __tablename__ = "privat_properties"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Stammdaten
    name = Column(String(255), nullable=False)
    property_type = Column(String(50), nullable=False)

    # Adresse
    street = Column(String(255), nullable=True)
    street_number = Column(String(20), nullable=True)
    postal_code = Column(String(10), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(2), default="DE")

    # Kaufdaten
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(15, 2), nullable=True)
    notary_costs = Column(Numeric(10, 2), nullable=True)
    land_transfer_tax = Column(Numeric(10, 2), nullable=True)

    # Laufende Daten
    current_value = Column(Numeric(15, 2), nullable=True)
    value_date = Column(Date, nullable=True)

    # Grundbuch
    land_register_entry = Column(String(100), nullable=True)
    cadastral_district = Column(String(100), nullable=True)
    parcel_number = Column(String(50), nullable=True)

    # Flaeche
    living_area_sqm = Column(Numeric(10, 2), nullable=True)
    plot_area_sqm = Column(Numeric(10, 2), nullable=True)

    # Finanzierung
    loan_id = Column(UUID(as_uuid=True), ForeignKey("privat_loans.id", ondelete="SET NULL"), nullable=True)

    # Status
    is_rented = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    calculated_yield = Column(Numeric(6, 2), nullable=True)  # Bruttomietrendite %
    calculated_net_yield = Column(Numeric(6, 2), nullable=True)  # Nettomietrendite %
    value_appreciation = Column(Numeric(15, 2), nullable=True)  # Wertzuwachs absolut
    value_appreciation_rate = Column(Numeric(6, 2), nullable=True)  # Wertzuwachs %
    total_costs_ytd = Column(Numeric(12, 2), nullable=True)  # Nebenkosten Year-to-Date
    calculated_roi = Column(Numeric(8, 2), nullable=True)  # Gesamt-ROI %
    annual_roi = Column(Numeric(6, 2), nullable=True)  # Jaehrlicher ROI %
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="properties")
    folder = relationship("PrivatFolder")
    loan = relationship("PrivatLoan", foreign_keys=[loan_id])
    tenants = relationship("PrivatTenant", back_populates="property", cascade="all, delete-orphan")
    rental_incomes = relationship("PrivatRentalIncome", back_populates="property", cascade="all, delete-orphan")
    utility_statements = relationship("PrivatUtilityStatement", back_populates="property", cascade="all, delete-orphan")
    deadlines = relationship("PrivatDeadline", back_populates="property", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_properties_space_id", "space_id"),
        Index("ix_privat_properties_is_active", "is_active"),
        Index("ix_privat_properties_is_rented", "is_rented"),
    )


class PrivatTenant(Base):
    """Mieter einer Immobilie."""
    __tablename__ = "privat_tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=False)

    # Mieterdaten
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=True)
    phone = Column(String(30), nullable=True)

    # Mietvertrag
    contract_start = Column(Date, nullable=False)
    contract_end = Column(Date, nullable=True)
    monthly_rent = Column(Numeric(10, 2), nullable=False)
    deposit = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    property = relationship("PrivatProperty", back_populates="tenants")


class PrivatRentalIncome(Base):
    """Mieteinnahmen-Tracking."""
    __tablename__ = "privat_rental_incomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("privat_tenants.id", ondelete="SET NULL"), nullable=True)

    # Zahlung
    payment_date = Column(Date, nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    payment_type = Column(String(30), default="rent")

    # Referenz
    reference = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    property = relationship("PrivatProperty", back_populates="rental_incomes")
    tenant = relationship("PrivatTenant")


class PrivatUtilityStatement(Base):
    """Nebenkostenabrechnungen."""
    __tablename__ = "privat_utility_statements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=False)

    # Abrechnungszeitraum
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Betraege
    total_costs = Column(Numeric(10, 2), nullable=False)
    prepayments = Column(Numeric(10, 2), nullable=False)
    balance = Column(Numeric(10, 2), nullable=False)

    # Details
    cost_breakdown = Column(CrossDBJSON, default=dict)

    # Dokument-Referenz
    document_id = Column(UUID(as_uuid=True), ForeignKey("privat_documents.id", ondelete="SET NULL"), nullable=True)

    # Status
    is_settled = Column(Boolean, default=False)
    settled_date = Column(Date, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    property = relationship("PrivatProperty", back_populates="utility_statements")
    document = relationship("PrivatDocument")


class PrivatVehicle(Base):
    """Fahrzeug-Stammdaten."""
    __tablename__ = "privat_vehicles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Fahrzeugdaten
    name = Column(String(255), nullable=False)
    license_plate = Column(String(20), nullable=True)
    vin = Column(String(17), nullable=True)

    # Details
    make = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    year = Column(Integer, nullable=True)
    fuel_type = Column(String(30), nullable=True)

    # Kauf/Leasing
    purchase_date = Column(Date, nullable=True)
    purchase_price = Column(Numeric(12, 2), nullable=True)
    is_leased = Column(Boolean, default=False)
    lease_end = Column(Date, nullable=True)
    monthly_rate = Column(Numeric(10, 2), nullable=True)

    # Versicherung
    insurance_company = Column(String(100), nullable=True)
    insurance_number = Column(String(50), nullable=True)
    insurance_type = Column(String(30), nullable=True)
    insurance_premium = Column(Numeric(10, 2), nullable=True)

    # Fristen
    tuev_due = Column(Date, nullable=True)
    inspection_due = Column(Date, nullable=True)

    # Kilometerstand
    current_mileage = Column(Integer, nullable=True)
    mileage_date = Column(Date, nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    current_estimated_value = Column(Numeric(12, 2), nullable=True)  # Geschaetzter Restwert
    depreciation_monthly = Column(Numeric(10, 2), nullable=True)  # Monatliche Abschreibung
    tco_total = Column(Numeric(12, 2), nullable=True)  # Total Cost of Ownership
    tco_per_km = Column(Numeric(6, 3), nullable=True)  # Kosten pro Kilometer
    next_service_date = Column(Date, nullable=True)  # Naechster geplanter Service
    next_service_km = Column(Integer, nullable=True)  # Service bei km-Stand
    average_fuel_consumption = Column(Numeric(5, 2), nullable=True)  # Durchschnittsverbrauch l/100km
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="vehicles")
    folder = relationship("PrivatFolder")
    fuel_logs = relationship("PrivatFuelLog", back_populates="vehicle", cascade="all, delete-orphan")
    deadlines = relationship("PrivatDeadline", back_populates="vehicle", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_vehicles_space_id", "space_id"),
        Index("ix_privat_vehicles_tuev_due", "tuev_due"),
        Index("ix_privat_vehicles_is_active", "is_active"),
    )


class PrivatFuelLog(Base):
    """Tankbelege/Ladungen."""
    __tablename__ = "privat_fuel_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("privat_vehicles.id", ondelete="CASCADE"), nullable=False)

    # Tankung
    date = Column(Date, nullable=False)
    mileage = Column(Integer, nullable=True)
    liters = Column(Numeric(6, 2), nullable=True)
    price_per_unit = Column(Numeric(6, 3), nullable=True)
    total_cost = Column(Numeric(8, 2), nullable=False)

    # Tankstelle
    station = Column(String(100), nullable=True)

    # Beleg
    receipt_document_id = Column(UUID(as_uuid=True), ForeignKey("privat_documents.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    vehicle = relationship("PrivatVehicle", back_populates="fuel_logs")
    receipt_document = relationship("PrivatDocument")


class PrivatInsurance(Base):
    """Versicherungspolicen."""
    __tablename__ = "privat_insurances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Police
    name = Column(String(255), nullable=False)
    insurance_type = Column(String(50), nullable=False)
    policy_number = Column(String(50), nullable=True)

    # Versicherer
    company = Column(String(100), nullable=False)
    agent_name = Column(String(100), nullable=True)
    agent_phone = Column(String(30), nullable=True)

    # Laufzeit
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_auto_renew = Column(Boolean, default=True)
    cancellation_period_months = Column(Integer, nullable=True)

    # Praemie
    premium_amount = Column(Numeric(10, 2), nullable=True)
    premium_frequency = Column(String(20), default="yearly")

    # Leistungen
    coverage_amount = Column(Numeric(15, 2), nullable=True)
    coverage_details = Column(CrossDBJSON, default=dict)
    deductible = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    coverage_gap_analysis = Column(CrossDBJSON, nullable=True)  # Deckungsluecken-Analyse
    # Format: {"gaps": [{"type": "haftpflicht", "recommended": 10000000, "current": 5000000, "gap": 5000000, "severity": "high"}]}
    cancellation_deadline = Column(Date, nullable=True)  # Berechnete Kuendigungsfrist
    annual_premium_total = Column(Numeric(10, 2), nullable=True)  # Jaehrliche Gesamtpraemie
    coverage_adequacy_score = Column(Numeric(5, 2), nullable=True)  # Deckungsadaequanz-Score 0-100
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="insurances")
    folder = relationship("PrivatFolder")
    deadlines = relationship("PrivatDeadline", back_populates="insurance", cascade="all, delete-orphan")
    coverage_gaps = relationship("PrivatCoverageGap", back_populates="insurance", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_insurances_space_id", "space_id"),
        Index("ix_privat_insurances_type", "insurance_type"),
        Index("ix_privat_insurances_end_date", "end_date"),
        Index("ix_privat_insurances_is_active", "is_active"),
    )


class PrivatLoan(Base):
    """Kredite/Darlehen."""
    __tablename__ = "privat_loans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Kredit
    name = Column(String(255), nullable=False)
    loan_type = Column(String(50), nullable=False)
    loan_number = Column(String(50), nullable=True)

    # Bank
    bank_name = Column(String(100), nullable=False)

    # Konditionen
    principal_amount = Column(Numeric(15, 2), nullable=False)
    interest_rate = Column(Numeric(5, 3), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)

    # Tilgung
    monthly_payment = Column(Numeric(10, 2), nullable=True)
    current_balance = Column(Numeric(15, 2), nullable=True)
    balance_date = Column(Date, nullable=True)

    # Sondertilgung
    special_repayment_allowed = Column(Boolean, default=False)
    special_repayment_limit = Column(Numeric(10, 2), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # =========================================================================
    # Berechnete KPIs (Enterprise Feature)
    # =========================================================================
    amortization_schedule = Column(CrossDBJSON, nullable=True)  # Tilgungsplan
    # Format: [{"date": "2024-01", "payment": 1000, "principal": 300, "interest": 700, "balance": 99000}, ...]
    projected_payoff_date = Column(Date, nullable=True)  # Voraussichtliches Rueckzahlungsdatum
    total_interest_projected = Column(Numeric(15, 2), nullable=True)  # Erwartete Gesamtzinsen
    interest_saved_with_extra = Column(Numeric(12, 2), nullable=True)  # Ersparnis bei Sondertilgung
    effective_annual_rate = Column(Numeric(5, 3), nullable=True)  # Effektiver Jahreszins
    remaining_term_months = Column(Integer, nullable=True)  # Verbleibende Laufzeit in Monaten
    last_kpi_calculation = Column(DateTime(timezone=True), nullable=True)  # Letzte Berechnung

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="loans")
    folder = relationship("PrivatFolder")
    properties = relationship("PrivatProperty", back_populates="loan", foreign_keys="PrivatProperty.loan_id")
    deadlines = relationship("PrivatDeadline", back_populates="loan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_loans_space_id", "space_id"),
        Index("ix_privat_loans_type", "loan_type"),
        Index("ix_privat_loans_end_date", "end_date"),
        Index("ix_privat_loans_is_active", "is_active"),
    )


class PrivatInvestment(Base):
    """Investments/Geldanlagen."""
    __tablename__ = "privat_investments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    folder_id = Column(UUID(as_uuid=True), ForeignKey("privat_folders.id", ondelete="SET NULL"), nullable=True)

    # Investment
    name = Column(String(255), nullable=False)
    investment_type = Column(String(50), nullable=False)

    # Bank/Depot
    institution = Column(String(100), nullable=True)
    account_number = Column(String(50), nullable=True)

    # Werte
    purchase_value = Column(Numeric(15, 2), nullable=True)
    purchase_date = Column(Date, nullable=True)
    current_value = Column(Numeric(15, 2), nullable=True)
    value_date = Column(Date, nullable=True)

    # Details
    isin = Column(String(12), nullable=True)
    quantity = Column(Numeric(15, 6), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="investments")
    folder = relationship("PrivatFolder")

    __table_args__ = (
        Index("ix_privat_investments_space_id", "space_id"),
        Index("ix_privat_investments_type", "investment_type"),
        Index("ix_privat_investments_is_active", "is_active"),
    )


class PrivatDeadline(Base):
    """Fristen mit Erinnerungen."""
    __tablename__ = "privat_deadlines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)

    # Verknuepfungen
    document_id = Column(UUID(as_uuid=True), ForeignKey("privat_documents.id", ondelete="CASCADE"), nullable=True)
    property_id = Column(UUID(as_uuid=True), ForeignKey("privat_properties.id", ondelete="CASCADE"), nullable=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("privat_vehicles.id", ondelete="CASCADE"), nullable=True)
    insurance_id = Column(UUID(as_uuid=True), ForeignKey("privat_insurances.id", ondelete="CASCADE"), nullable=True)
    loan_id = Column(UUID(as_uuid=True), ForeignKey("privat_loans.id", ondelete="CASCADE"), nullable=True)

    # Frist
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    deadline_type = Column(String(30), default=PrivatDeadlineType.CUSTOM.value)
    due_date = Column(Date, nullable=False)

    # Erinnerungen
    reminder_days = Column(CrossDBJSON, default=[30, 7, 1])
    reminders_sent = Column(CrossDBJSON, default=list)

    # Wiederholung
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(String(50), nullable=True)
    next_occurrence = Column(Date, nullable=True)

    # Status
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # iCal
    ical_uid = Column(String(100), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    space = relationship("PrivatSpace", back_populates="deadlines")
    privat_document = relationship("PrivatDocument", back_populates="deadlines")
    property = relationship("PrivatProperty", back_populates="deadlines")
    vehicle = relationship("PrivatVehicle", back_populates="deadlines")
    insurance = relationship("PrivatInsurance", back_populates="deadlines")
    loan = relationship("PrivatLoan", back_populates="deadlines")
    created_by = relationship("User", foreign_keys=[created_by_id])
    notifications = relationship("PrivatDeadlineNotification", back_populates="deadline", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_deadlines_space_id", "space_id"),
        Index("ix_privat_deadlines_due_date", "due_date"),
        Index("ix_privat_deadlines_is_active", "is_active"),
        Index("ix_privat_deadlines_is_completed", "is_completed"),
    )


class PrivatDeadlineNotification(Base):
    """Gesendete Frist-Benachrichtigungen."""
    __tablename__ = "privat_deadline_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deadline_id = Column(UUID(as_uuid=True), ForeignKey("privat_deadlines.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Benachrichtigung
    days_before = Column(Integer, nullable=False)
    notification_type = Column(String(30), default="email")

    # Status
    sent_at = Column(DateTime(timezone=True), server_default=func.now())
    delivered = Column(Boolean, default=False)
    read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    deadline = relationship("PrivatDeadline", back_populates="notifications")
    user = relationship("User")

    __table_args__ = (
        Index("ix_privat_deadline_notifications_deadline_id", "deadline_id"),
        Index("ix_privat_deadline_notifications_user_id", "user_id"),
        Index("ix_privat_deadline_notifications_sent_at", "sent_at"),
    )


class PrivatEmergencyContact(Base):
    """Vertrauenspersonen fuer Notfallzugriff/Vererbung."""
    __tablename__ = "privat_emergency_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)

    # Vertrauensperson
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=True)
    contact_relationship = Column(String(50), nullable=True)  # 'relationship' ist SQLAlchemy reserved!

    # Zugriffskonfiguration
    access_level = Column(String(20), default=PrivatAccessLevel.VIEW.value)
    access_folders = Column(CrossDBJSON, default=list)

    # Aktivierung
    activation_delay_days = Column(Integer, default=30)
    requires_verification = Column(Boolean, default=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Token
    activation_token_hash = Column(String(64), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    space = relationship("PrivatSpace", back_populates="emergency_contacts")
    access_requests = relationship("PrivatEmergencyAccessRequest", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_privat_emergency_contacts_space_id", "space_id"),
        Index("ix_privat_emergency_contacts_email", "email"),
        Index("ix_privat_emergency_contacts_is_active", "is_active"),
    )


class PrivatEmergencyAccessRequest(Base):
    """Anfrage auf Notfallzugriff."""
    __tablename__ = "privat_emergency_access_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("privat_emergency_contacts.id", ondelete="CASCADE"), nullable=False)

    # Status
    status = Column(String(20), default=PrivatEmergencyAccessStatus.PENDING.value)

    # Zeitplanung
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    activation_scheduled_for = Column(DateTime(timezone=True), nullable=True)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Begruendung
    reason = Column(Text, nullable=True)

    # Verifizierung
    verification_code = Column(String(20), nullable=True)
    verification_document_id = Column(UUID(as_uuid=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Widerruf
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    revoke_reason = Column(Text, nullable=True)

    # IP/Geraet
    request_ip = Column(String(45), nullable=True)
    request_user_agent = Column(String(500), nullable=True)

    # Relationships
    contact = relationship("PrivatEmergencyContact", back_populates="access_requests")
    revoked_by = relationship("User")

    __table_args__ = (
        Index("ix_privat_emergency_access_requests_contact_id", "contact_id"),
        Index("ix_privat_emergency_access_requests_status", "status"),
        Index("ix_privat_emergency_access_requests_activation", "activation_scheduled_for"),
    )


# =============================================================================
# VALIDATION QUEUE SYSTEM
# Enterprise-Grade Validierungssystem fuer OCR-Ergebnisse und extrahierte Daten
# =============================================================================

class ValidationStatus(str, Enum):
    """Validierungs-Status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class SampleSource(str, Enum):
    """Quelle der Stichproben-Auswahl."""
    AUTOMATIC = "automatic"
    RULE_BASED = "rule_based"
    MANUAL = "manual"
    LOW_CONFIDENCE = "low_confidence"


class ValidationRuleType(str, Enum):
    """Typ der Validierungsregel."""
    CONFIDENCE_THRESHOLD = "confidence_threshold"
    FIELD_PATTERN = "field_pattern"
    DOCUMENT_TYPE = "document_type"
    FIRST_OCCURRENCE = "first_occurrence"
    ERROR_PATTERN = "error_pattern"


class ValidationSampleConfig(Base):
    """Konfiguration fuer prozent-basierte Stichproben."""
    __tablename__ = "validation_sample_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Konfiguration
    name = Column(String(100), nullable=False, default="Standard")
    description = Column(Text, nullable=True)
    sample_percentage = Column(Integer, nullable=False, default=10)
    stratify_by_document_type = Column(Boolean, default=True)
    stratify_by_ocr_backend = Column(Boolean, default=False)
    min_confidence_threshold = Column(Float, default=0.85)

    # Zeitraum
    is_active = Column(Boolean, default=True)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # Statistik
    documents_sampled = Column(Integer, default=0)
    last_sample_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])


class ValidationRule(Base):
    """Regelbasierte Stichproben-Definition."""
    __tablename__ = "validation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Regel-Identifikation
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Regel-Definition
    rule_type = Column(String(50), nullable=False)
    conditions = Column(CrossDBJSON, nullable=False, default=dict)

    # Prioritaet und Status
    priority = Column(Integer, nullable=False, default=5)
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False)

    # Statistik
    documents_matched = Column(Integer, default=0)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])
    queue_items = relationship("ValidationQueueItem", back_populates="sample_rule")

    __table_args__ = (
        Index("ix_validation_rules_active", "is_active"),
        Index("ix_validation_rules_type", "rule_type"),
        Index("ix_validation_rules_priority", "priority"),
    )


class ValidationQueueItem(Base):
    """Warteschlangen-Eintrag fuer Validierung."""
    __tablename__ = "validation_queue_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    # Status und Zuweisung
    status = Column(String(50), nullable=False, default=ValidationStatus.PENDING.value)
    priority = Column(Integer, nullable=False, default=5)
    assigned_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    # Stichproben-Quelle
    sample_source = Column(String(50), nullable=False, default=SampleSource.AUTOMATIC.value)
    sample_rule_id = Column(UUID(as_uuid=True), ForeignKey("validation_rules.id", ondelete="SET NULL"), nullable=True)

    # Confidence Metriken
    overall_confidence = Column(Float, nullable=True)
    min_field_confidence = Column(Float, nullable=True)
    fields_below_threshold = Column(Integer, default=0)
    total_fields = Column(Integer, default=0)

    # Dokumenttyp (kopiert fuer Filterung ohne Join)
    document_type = Column(String(50), nullable=True)
    document_name = Column(String(255), nullable=True)

    # Validierungsergebnis
    validation_notes = Column(Text, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    rejection_category = Column(String(50), nullable=True)
    validated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    validated_at = Column(DateTime(timezone=True), nullable=True)

    # Zeit-Tracking
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    validation_duration_seconds = Column(Integer, nullable=True)

    # Korrekturen-Zaehler
    corrections_made = Column(Integer, default=0)
    umlaut_corrections = Column(Integer, default=0)
    format_corrections = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    document = relationship("Document", backref="validation_queue_items")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], backref="assigned_validations")
    validated_by = relationship("User", foreign_keys=[validated_by_id], backref="completed_validations")
    created_by = relationship("User", foreign_keys=[created_by_id])
    sample_rule = relationship("ValidationRule", back_populates="queue_items")
    field_reviews = relationship("ValidationFieldReview", back_populates="queue_item", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_vqi_status", "status"),
        Index("ix_vqi_priority", "priority"),
        Index("ix_vqi_assigned_to", "assigned_to_id"),
        Index("ix_vqi_document", "document_id"),
        Index("ix_vqi_confidence", "overall_confidence"),
        Index("ix_vqi_sample_source", "sample_source"),
        Index("ix_vqi_created_at", "created_at"),
        Index("ix_vqi_document_type", "document_type"),
        Index("ix_vqi_status_priority", "status", "priority", "created_at"),
        Index("ix_vqi_assigned_status", "assigned_to_id", "status"),
        Index("ix_vqi_validated_date", "validated_at", "validated_by_id"),
    )

    @property
    def is_pending(self) -> bool:
        """Prueft ob Item noch ausstehend ist."""
        return self.status == ValidationStatus.PENDING.value

    @property
    def is_completed(self) -> bool:
        """Prueft ob Item abgeschlossen ist."""
        return self.status in [ValidationStatus.APPROVED.value, ValidationStatus.REJECTED.value]


class ValidationFieldReview(Base):
    """Feld-Review fuer ein Validierungs-Item."""
    __tablename__ = "validation_field_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Queue-Item Referenz
    queue_item_id = Column(UUID(as_uuid=True), ForeignKey("validation_queue_items.id", ondelete="CASCADE"), nullable=False)

    # Feld-Identifikation
    field_key = Column(String(100), nullable=False)
    field_label = Column(String(255), nullable=False)
    field_type = Column(String(50), nullable=True)

    # Werte
    original_value = Column(Text, nullable=True)
    corrected_value = Column(Text, nullable=True)
    was_corrected = Column(Boolean, default=False)

    # Confidence
    confidence_score = Column(Float, nullable=True)
    confidence_threshold = Column(Float, default=0.85)
    is_below_threshold = Column(Boolean, default=False)

    # Validierung
    validation_status = Column(String(50), default="pending")
    validation_errors = Column(CrossDBJSON, default=list)
    umlaut_issues = Column(CrossDBJSON, default=list)
    format_issues = Column(CrossDBJSON, default=list)

    # OCR-Metadaten fuer PDF-Highlighting
    bounding_box = Column(CrossDBJSON, nullable=True)
    ocr_backend = Column(String(50), nullable=True)

    # Audit
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    queue_item = relationship("ValidationQueueItem", back_populates="field_reviews")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])

    __table_args__ = (
        Index("ix_vfr_queue_item", "queue_item_id"),
        Index("ix_vfr_field_key", "field_key"),
        Index("ix_vfr_below_threshold", "is_below_threshold"),
        Index("ix_vfr_was_corrected", "was_corrected"),
    )

    @property
    def needs_review(self) -> bool:
        """Prueft ob Feld Review benoetigt."""
        return self.is_below_threshold or len(self.validation_errors) > 0


class ValidationAnalytics(Base):
    """Aggregierte Statistiken fuer Validierungen."""
    __tablename__ = "validation_analytics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zeitraum
    date = Column(Date, nullable=False)
    hour = Column(Integer, nullable=True)

    # Editor (NULL = Gesamtstatistik)
    editor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)

    # Dokumenttyp (NULL = Alle Typen)
    document_type = Column(String(50), nullable=True)

    # Metriken: Anzahl
    items_validated = Column(Integer, default=0)
    items_approved = Column(Integer, default=0)
    items_rejected = Column(Integer, default=0)
    items_skipped = Column(Integer, default=0)

    # Metriken: Zeit
    avg_validation_time_seconds = Column(Integer, nullable=True)
    min_validation_time_seconds = Column(Integer, nullable=True)
    max_validation_time_seconds = Column(Integer, nullable=True)
    total_validation_time_seconds = Column(Integer, default=0)

    # Metriken: Korrekturen
    corrections_made = Column(Integer, default=0)
    umlaut_corrections = Column(Integer, default=0)
    format_corrections = Column(Integer, default=0)
    fields_reviewed = Column(Integer, default=0)

    # Metriken: Confidence
    avg_confidence_before = Column(Float, nullable=True)
    avg_confidence_after = Column(Float, nullable=True)
    confidence_improvement = Column(Float, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    editor = relationship("User", foreign_keys=[editor_id])

    __table_args__ = (
        Index("ix_va_date", "date"),
        Index("ix_va_editor", "editor_id"),
        Index("ix_va_document_type", "document_type"),
        Index("ix_va_date_editor", "date", "editor_id"),
    )


# =============================================================================
# COLLABORATION-MODUL: COMMENTS, ACTIVITIES, NOTIFICATIONS
# =============================================================================


class DocumentComment(Base):
    """Kommentare zu Dokumenten fuer Collaboration.

    Multi-Tenant Support:
    - company_id: Firmenzugehoerigkeit (Migration 103)

    Feld-Referenz (Inline-Kommentare):
    - field_reference: Optionaler Feldname fuer Inline-Kommentare auf Extraktionsfeldern
      (z.B. "invoice_number", "total_amount", "vendor_name")

    Soft Delete mit Timestamp:
    - deleted_at: Zeitpunkt des Loeschens (NULL = nicht geloescht)
    - deleted_by_id: User der den Kommentar geloescht hat
    - is_deleted: Legacy-Flag (wird parallel gepflegt)
    """
    __tablename__ = "document_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("document_comments.id", ondelete="CASCADE"), nullable=True)

    # Multi-Tenant Support (Migration 103)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Feld-Referenz fuer Inline-Kommentare (Migration 103)
    field_reference = Column(String(100), nullable=True)

    content = Column(Text, nullable=False)
    mentions = Column(CrossDBJSON, default=list)  # [{"userId": "...", "userName": "...", "startIndex": 0, "endIndex": 10}]
    reactions = Column(CrossDBJSON, default=list)  # [{"emoji": "👍", "count": 2, "userIds": ["..."]}]

    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)  # Legacy-Flag

    # Soft Delete mit Timestamp (Migration 103)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    deleted_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="comments")
    user = relationship("User", backref="document_comments", foreign_keys=[user_id])
    parent = relationship("DocumentComment", remote_side=[id], backref="replies")
    company = relationship("Company", backref="document_comments")
    deleted_by = relationship("User", foreign_keys=[deleted_by_id])

    __table_args__ = (
        Index("ix_doc_comment_document", "document_id"),
        Index("ix_doc_comment_user", "user_id"),
        Index("ix_doc_comment_parent", "parent_id"),
        Index("ix_doc_comment_created", "created_at"),
        Index("ix_doc_comment_company", "company_id"),
        Index("ix_doc_comment_company_document", "company_id", "document_id"),
    )

    def __repr__(self) -> str:
        return f"<DocumentComment {self.id} on {self.document_id}>"


class ActivityType(str, Enum):
    """Aktivitaetstypen fuer Document Activity Log."""
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_UPDATED = "document_updated"
    DOCUMENT_VIEWED = "document_viewed"
    DOCUMENT_DOWNLOADED = "document_downloaded"
    COMMENT_ADDED = "comment_added"
    COMMENT_REPLIED = "comment_replied"
    STATUS_CHANGED = "status_changed"
    TAGS_CHANGED = "tags_changed"
    METADATA_UPDATED = "metadata_updated"
    DOCUMENT_SHARED = "document_shared"


class DocumentActivity(Base):
    """Aktivitaetslog fuer Dokumente."""
    __tablename__ = "document_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    activity_type = Column(String(50), nullable=False)
    description = Column(String(500), nullable=False)
    activity_metadata = Column("metadata", CrossDBJSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", backref="activities")
    user = relationship("User", backref="document_activities")

    __table_args__ = (
        Index("ix_doc_activity_document", "document_id"),
        Index("ix_doc_activity_user", "user_id"),
        Index("ix_doc_activity_type", "activity_type"),
        Index("ix_doc_activity_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<DocumentActivity {self.activity_type} on {self.document_id}>"


class NotificationType(str, Enum):
    """Benachrichtigungstypen."""
    MENTION = "mention"
    COMMENT_REPLY = "comment_reply"
    DOCUMENT_SHARED = "document_shared"
    TASK_ASSIGNED = "task_assigned"
    TASK_COMPLETED = "task_completed"
    TASK_ESCALATED = "task_escalated"
    TASK_REMINDER = "task_reminder"
    DOCUMENT_APPROVED = "document_approved"
    DOCUMENT_REJECTED = "document_rejected"


class UserNotification(Base):
    """Benutzer-Benachrichtigungen."""
    __tablename__ = "user_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    from_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)

    notification_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(500), nullable=True)

    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="notifications")
    from_user = relationship("User", foreign_keys=[from_user_id])
    document = relationship("Document", backref="notifications")

    __table_args__ = (
        Index("ix_notification_user", "user_id"),
        Index("ix_notification_unread", "user_id", "is_read"),
        Index("ix_notification_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<UserNotification {self.notification_type} for {self.user_id}>"


# =============================================================================
# COLLABORATION MODELS - Task Assignment System
# =============================================================================


class TaskStatus(str, Enum):
    """Status einer zugewiesenen Aufgabe."""
    OPEN = "open"                  # Neu erstellt, noch nicht begonnen
    IN_PROGRESS = "in_progress"    # In Bearbeitung
    COMPLETED = "completed"        # Erledigt
    CANCELLED = "cancelled"        # Abgebrochen
    BLOCKED = "blocked"            # Blockiert (wartet auf etwas)


class TaskPriority(str, Enum):
    """Prioritaet einer Aufgabe."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class DocumentTask(Base):
    """Aufgaben-Zuweisung fuer Dokumente.

    Ermoeglicht Team-Collaboration durch:
    - Zuweisung von Aufgaben an Benutzer ("Bitte pruefen")
    - Deadlines mit automatischer Eskalation
    - Status-Tracking
    - Benachrichtigungen bei Aenderungen
    """
    __tablename__ = "document_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aufgaben-Details
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    task_type = Column(String(50), nullable=False, default="review")  # review, approve, process, other

    # Zuweisung
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Status und Prioritaet
    status = Column(String(20), nullable=False, default=TaskStatus.OPEN.value)
    priority = Column(String(20), nullable=False, default=TaskPriority.NORMAL.value)

    # Deadlines
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    reminder_sent = Column(Boolean, default=False)  # "Bald faellig" Erinnerung gesendet
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)  # Letzte Ueberfaellig-Erinnerung
    escalated = Column(Boolean, default=False)
    escalated_at = Column(DateTime(timezone=True), nullable=True)
    escalated_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Completion-Details
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    completion_notes = Column(Text, nullable=True)

    # Metadaten
    task_metadata = Column(CrossDBJSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="tasks")
    company = relationship("Company", backref="document_tasks")
    created_by = relationship("User", foreign_keys=[created_by_id], backref="created_tasks")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id], backref="assigned_tasks")
    completed_by = relationship("User", foreign_keys=[completed_by_id])
    escalated_to = relationship("User", foreign_keys=[escalated_to_id])

    __table_args__ = (
        Index("ix_task_document", "document_id"),
        Index("ix_task_assigned", "assigned_to_id"),
        Index("ix_task_status", "status"),
        Index("ix_task_due_date", "due_date"),
        Index("ix_task_company_status", "company_id", "status"),
        Index("ix_task_assigned_status", "assigned_to_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<DocumentTask {self.id} '{self.title}' -> {self.assigned_to_id}>"


# =============================================================================
# NOTIFICATION PREFERENCES & DIGEST SYSTEM
# =============================================================================


class NotificationChannel(str, Enum):
    """Verfuegbare Benachrichtigungskanaele."""
    IN_APP = "in_app"        # In-App Benachrichtigung (Glocke)
    EMAIL = "email"          # Email
    WEBSOCKET = "websocket"  # Real-time WebSocket
    SLACK = "slack"          # Slack Integration
    SMS = "sms"              # SMS (future)


class DigestFrequency(str, Enum):
    """Haeufigkeit fuer Email-Digest."""
    IMMEDIATE = "immediate"  # Sofort senden
    HOURLY = "hourly"        # Stuendlich
    DAILY = "daily"          # Taeglich
    WEEKLY = "weekly"        # Woechentlich
    DISABLED = "disabled"    # Deaktiviert


class NotificationPreference(Base):
    """Benutzer-Praeferenzen fuer Benachrichtigungen.

    Ermoeglicht granulare Kontrolle ueber:
    - Welche Benachrichtigungstypen empfangen werden
    - Ueber welche Kanaele (In-App, Email, Slack, etc.)
    - Digest-Einstellungen (sofort, taeglich, woechentlich)
    """
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Notification Type (z.B. "mention", "task_assigned", "document_shared")
    notification_type = Column(String(50), nullable=False)

    # Kanal-Einstellungen (JSON: {"in_app": true, "email": false, "slack": true})
    enabled_channels = Column(CrossDBJSON, default=lambda: {
        "in_app": True,
        "email": True,
        "websocket": True,
        "slack": False,
        "sms": False
    })

    # Digest-Einstellung fuer diesen Typ
    digest_frequency = Column(String(20), default=DigestFrequency.IMMEDIATE.value)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="notification_preferences")

    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_user_notification_type"),
        Index("ix_notif_pref_user", "user_id"),
        Index("ix_notif_pref_type", "notification_type"),
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference {self.user_id} - {self.notification_type}>"


class NotificationDigestQueue(Base):
    """Queue fuer Digest-Benachrichtigungen.

    Sammelt Benachrichtigungen fuer spaetere Zustellung als Digest.
    Wird von einem Celery Task periodisch verarbeitet.
    """
    __tablename__ = "notification_digest_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Originale Notification-Daten
    notification_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(500), nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True)
    from_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Digest-Metadaten
    digest_frequency = Column(String(20), nullable=False)  # daily, weekly
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)  # Wann soll Digest gesendet werden

    # Status
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    document = relationship("Document")
    from_user = relationship("User", foreign_keys=[from_user_id])

    __table_args__ = (
        Index("ix_digest_queue_user_unsent", "user_id", "is_sent"),
        Index("ix_digest_queue_scheduled", "scheduled_for", "is_sent"),
    )

    def __repr__(self) -> str:
        return f"<NotificationDigestQueue {self.id} for {self.user_id}>"


# =============================================================================
# ESCALATION SYSTEM
# =============================================================================


class EscalationRule(Base):
    """Eskalationsregeln fuer automatische Weiterleitung.

    Definiert wann und an wen Aufgaben eskaliert werden:
    - Nach X Stunden/Tagen ohne Reaktion
    - An Vorgesetzten oder bestimmten Benutzer
    - Mit optionaler Benachrichtigung
    """
    __tablename__ = "escalation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Regel-Details
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)

    # Trigger-Bedingungen
    task_type = Column(String(50), nullable=True)  # null = alle Typen
    priority = Column(String(20), nullable=True)   # null = alle Prioritaeten

    # Eskalations-Timeout (in Stunden)
    timeout_hours = Column(Integer, nullable=False, default=24)

    # Eskalations-Ziel
    escalate_to_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    escalate_to_role = Column(String(50), nullable=True)  # "manager", "admin", etc.

    # Benachrichtigungs-Optionen
    notify_original_assignee = Column(Boolean, default=True)
    notify_escalation_target = Column(Boolean, default=True)
    notify_task_creator = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Prioritaet der Regel (niedrigere Zahl = hoehere Prioritaet)
    rule_priority = Column(Integer, default=100)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="escalation_rules")
    escalate_to_user = relationship("User")

    __table_args__ = (
        Index("ix_escalation_company_active", "company_id", "is_active"),
        Index("ix_escalation_task_type", "task_type"),
    )

    def __repr__(self) -> str:
        return f"<EscalationRule {self.name} ({self.timeout_hours}h)>"


# =============================================================================
# GoBD COMPLIANCE MODELS (Feature 02)
# =============================================================================
# GoBD (Grundsaetze zur ordnungsmaessigen Fuehrung und Aufbewahrung von
# Buechern, Aufzeichnungen und Unterlagen in elektronischer Form sowie
# zum Datenzugriff) - German legal requirements for electronic document
# archiving and retention.
# =============================================================================


class RetentionCategory(str, Enum):
    """GoBD Aufbewahrungskategorien nach deutschem Recht."""
    INVOICE = "invoice"                    # Rechnungen - 10 Jahre (§147 AO, §14b UStG)
    CONTRACT = "contract"                  # Vertraege - 10 Jahre (§147 AO, §257 HGB)
    CORRESPONDENCE = "correspondence"      # Geschaeftsbriefe - 6 Jahre (§257 HGB)
    BOOKING_DOCUMENT = "booking_document"  # Buchungsbelege - 10 Jahre (§147 AO)
    ANNUAL_REPORT = "annual_report"        # Jahresabschluesse - 10 Jahre (§257 HGB)
    TAX_DOCUMENT = "tax_document"          # Steuerbelege - 10 Jahre (§147 AO)
    EMPLOYEE_DOCUMENT = "employee_document"  # Personalakten - 10 Jahre (§257 HGB)
    OTHER = "other"                        # Sonstiges - 6 Jahre (§147 AO)


class HashAlgorithm(str, Enum):
    """Unterstuetzte Hash-Algorithmen fuer Dokumentensignaturen."""
    SHA256 = "SHA-256"
    SHA384 = "SHA-384"
    SHA512 = "SHA-512"


class DocumentAccessType(str, Enum):
    """Typen von Dokumentzugriffen fuer GoBD Audit-Trail."""
    VIEW = "view"                    # Dokument angesehen (Metadaten)
    DOWNLOAD = "download"            # Dokument heruntergeladen
    PREVIEW = "preview"              # Vorschau/Thumbnail angezeigt
    PRINT = "print"                  # Dokument gedruckt
    EXPORT = "export"                # Dokument exportiert (DATEV, PDF, etc.)
    SHARE = "share"                  # Dokument geteilt
    SEARCH_HIT = "search_hit"        # In Suchergebnis aufgetaucht
    OCR_ACCESS = "ocr_access"        # OCR-Text abgerufen
    METADATA_UPDATE = "metadata_update"  # Metadaten geaendert (erlaubt!)
    ANNOTATION = "annotation"        # Anmerkung hinzugefuegt


class DocumentAccessLog(Base):
    """GoBD-konformes Dokumenten-Zugriffsprotokoll.

    Erfasst JEDEN Zugriff auf ein Dokument fuer:
    - GoBD-Nachvollziehbarkeit: Wer hat wann was zugegriffen?
    - DSGVO Art. 30: Verarbeitungsverzeichnis
    - Interne Compliance: Zugriffskontrolle und Reporting

    WICHTIG: Diese Tabelle sollte IMMUTABLE sein (kein UPDATE/DELETE).
    """
    __tablename__ = "document_access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zugriffsdetails
    access_type = Column(
        String(30),
        nullable=False,
        comment="Art des Zugriffs: view, download, export, etc."
    )
    access_reason = Column(
        String(255),
        nullable=True,
        comment="Optionaler Grund/Kontext des Zugriffs"
    )

    # Request-Kontext (fuer Audit)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_id = Column(
        String(36),
        nullable=True,
        comment="Korrelations-ID zur Request-Verfolgung"
    )

    # Ergebnis
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(String(500), nullable=True)
    bytes_transferred = Column(
        BigInteger,
        nullable=True,
        comment="Uebertragene Bytes (bei Download/Export)"
    )

    # Zeitstempel (immutable!)
    accessed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Zusaetzliche Metadaten
    access_metadata = Column(
        CrossDBJSON,
        default=dict,
        comment="Zusaetzliche Kontext-Infos (Format, Export-Typ, etc.)"
    )

    # Sequenznummer fuer Immutabilitaets-Nachweis
    sequence_number = Column(
        BigInteger,
        unique=True,
        nullable=True,
        comment="Aufsteigende Sequenz fuer Lueckendetektion"
    )

    # Relationships
    document = relationship("Document", backref="access_logs")
    user = relationship("User", backref="document_accesses")
    company = relationship("Company", backref="document_access_logs")

    __table_args__ = (
        Index("ix_document_access_logs_document_id", "document_id"),
        Index("ix_document_access_logs_user_id", "user_id"),
        Index("ix_document_access_logs_company_id", "company_id"),
        Index("ix_document_access_logs_accessed_at", "accessed_at"),
        Index("ix_document_access_logs_access_type", "access_type"),
        Index("ix_document_access_logs_sequence", "sequence_number"),
        # Composite index fuer typische Abfragen
        Index(
            "ix_document_access_logs_doc_time",
            "document_id", "accessed_at"
        ),
        {"comment": "GoBD-konformes Dokumenten-Zugriffsprotokoll"}
    )

    def __repr__(self) -> str:
        return f"<DocumentAccessLog {self.id} doc={self.document_id} type={self.access_type}>"


class DocumentArchive(Base):
    """GoBD-konforme Archivierung: Revisionssichere Speicherung mit Hash-Signatur.

    Erfuellt GoBD-Kriterien:
    - Nachvollziehbarkeit: Vollstaendiger Audit-Trail
    - Unveraenderbarkeit: SHA-256 Hash-Signatur des Dokument-Inhalts
    - Vollstaendigkeit: Aufbewahrungsfristen-Management
    - Ordnung: Kategorisierung nach Dokumenttyp
    """
    __tablename__ = "document_archives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen (RESTRICT: Archivierte Dokumente duerfen nicht geloescht werden)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False
    )

    # Signatur (GoBD: Unveraenderbarkeit)
    content_hash = Column(
        String(128),
        nullable=False,
        comment="SHA-256 Hash des Dokument-Inhalts"
    )
    hash_algorithm = Column(
        String(20),
        nullable=False,
        default=HashAlgorithm.SHA256.value
    )
    signature_timestamp = Column(DateTime(timezone=True), nullable=False)
    signature_certificate = Column(
        Text,
        nullable=True,
        comment="TSA-Zertifikat (optional fuer qualifizierte Zeitstempel)"
    )

    # Aufbewahrungsfristen (GoBD: Ordnung + Aufbewahrung)
    retention_category = Column(
        String(50),
        nullable=False,
        comment="Kategorie: invoice, contract, correspondence, etc."
    )
    retention_years = Column(Integer, nullable=False, default=10)
    retention_expires_at = Column(Date, nullable=False)
    retention_reminder_sent = Column(Boolean, nullable=False, default=False)
    retention_reminder_at = Column(DateTime(timezone=True), nullable=True)

    # Verifikationsstatus
    is_verified = Column(Boolean, nullable=False, default=True)
    last_verification_at = Column(DateTime(timezone=True), nullable=True)
    verification_failed_reason = Column(Text, nullable=True)

    # Audit (GoBD: Nachvollziehbarkeit)
    archived_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    archived_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metadaten
    archive_metadata = Column(CrossDBJSON, default=dict)

    # Relationships
    document = relationship("Document", back_populates="archive")
    company = relationship("Company", backref="document_archives")
    archived_by = relationship("User", backref="archived_documents")

    __table_args__ = (
        Index("ix_document_archives_company_id", "company_id"),
        Index("ix_document_archives_retention_expires", "retention_expires_at"),
        Index("ix_document_archives_retention_category", "retention_category"),
        Index("ix_document_archives_is_verified", "is_verified"),
        Index("ix_document_archives_archived_at", "archived_at"),
        {"comment": "GoBD-konforme Archivierung: Revisionssichere Speicherung mit Hash-Signatur"}
    )

    def __repr__(self) -> str:
        return f"<DocumentArchive {self.id} doc={self.document_id} hash={self.content_hash[:16]}...>"


class ProcedureDocumentationVersion(Base):
    """GoBD Verfahrensdokumentation: Automatisch generierte und versionierte Systemdokumentation.

    Die Verfahrensdokumentation beschreibt:
    - Wie Dokumente im System verarbeitet werden
    - Welche Sicherheitsmassnahmen implementiert sind
    - Wie die Aufbewahrungsfristen eingehalten werden
    - Aenderungshistorie des Systems

    Wird automatisch bei relevanten Systemupdates generiert.
    """
    __tablename__ = "procedure_documentation_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Versionierung
    version = Column(
        String(20),
        nullable=False,
        comment="Semantic Version (z.B. 2.1.0)"
    )
    content = Column(
        CrossDBJSON,
        nullable=False,
        comment="Verfahrensdokumentation als strukturiertes JSON"
    )

    # Metadaten
    generated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    generated_by = Column(String(50), nullable=False, default="system")

    # Signatur fuer Unveraenderbarkeit
    content_hash = Column(String(128), nullable=False)

    # Aenderungshistorie
    change_summary = Column(
        Text,
        nullable=True,
        comment="Zusammenfassung der Aenderungen zur Vorversion"
    )
    change_details = Column(CrossDBJSON, nullable=True)

    # Referenz zur Company (Multi-Tenant, NULL = System-weit)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", backref="procedure_documentation_versions")

    __table_args__ = (
        Index("ix_procedure_docs_version", "version"),
        Index("ix_procedure_docs_company_id", "company_id"),
        Index("ix_procedure_docs_generated_at", "generated_at"),
        {"comment": "GoBD Verfahrensdokumentation: Automatisch generierte Systemdokumentation"}
    )

    def __repr__(self) -> str:
        return f"<ProcedureDocVersion {self.version} generated={self.generated_at}>"


class RetentionSetting(Base):
    """GoBD Aufbewahrungsfristen-Konfiguration pro Dokumentkategorie.

    Definiert die gesetzlichen Aufbewahrungsfristen nach deutschem Recht:
    - §147 AO (Abgabenordnung): 10 Jahre fuer Buchfuehrungsunterlagen
    - §257 HGB (Handelsgesetzbuch): 6-10 Jahre je nach Dokumenttyp
    - §14b UStG (Umsatzsteuergesetz): 10 Jahre fuer Rechnungen
    """
    __tablename__ = "retention_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kategorie-Definition
    category = Column(
        String(50),
        nullable=False,
        unique=True,
        comment="Technischer Name: invoice, contract, correspondence, etc."
    )
    display_name = Column(
        String(100),
        nullable=False,
        comment="Anzeigename auf Deutsch"
    )
    description = Column(Text, nullable=True)

    # Aufbewahrungsfristen
    retention_years = Column(Integer, nullable=False, default=10)
    legal_basis = Column(
        String(255),
        nullable=True,
        comment="Gesetzliche Grundlage: z.B. §147 AO, §257 HGB"
    )

    # Warnungen und Auto-Aktionen
    reminder_days_before = Column(
        Integer,
        nullable=False,
        default=90,
        comment="Tage vor Ablauf fuer Erinnerung"
    )
    auto_delete_enabled = Column(Boolean, nullable=False, default=False)
    requires_approval_for_delete = Column(Boolean, nullable=False, default=True)

    # Audit
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    updated_by = relationship("User", backref="retention_setting_updates")

    __table_args__ = (
        {"comment": "GoBD Aufbewahrungsfristen-Konfiguration pro Dokumentkategorie"}
    )

    def __repr__(self) -> str:
        return f"<RetentionSetting {self.category} years={self.retention_years}>"


# ============================================================================
# GoBD Phase 4: Steuerberater-Zugang (Tax Advisor Access)
# ============================================================================

class TaxAdvisorInviteStatus(str, Enum):
    """Status einer Steuerberater-Einladung."""
    PENDING = "pending"       # Einladung gesendet, noch nicht akzeptiert
    ACCEPTED = "accepted"     # Einladung akzeptiert, Benutzer erstellt
    EXPIRED = "expired"       # Token abgelaufen
    REVOKED = "revoked"       # Einladung widerrufen


class TaxAdvisorInvite(Base):
    """GoBD Steuerberater-Einladungen fuer temporaeren Prueferzugang.

    Ermoeglicht Administratoren, Steuerberatern zeitlich begrenzten
    Lesezugriff auf archivierte Dokumente zu gewaehren.

    Flow:
    1. Admin erstellt Einladung mit E-Mail des Steuerberaters
    2. Steuerberater erhaelt E-Mail mit Einladungslink
    3. Steuerberater registriert sich ueber den Link
    4. Nach Registrierung hat Steuerberater access_duration_days Tage Zugang
    5. Nach Ablauf wird Zugang automatisch deaktiviert

    GoBD-Konformitaet:
    - Nachvollziehbarkeit: Alle Aktivitaeten werden protokolliert
    - Zeitliche Begrenzung: Zugang laeuft automatisch ab
    - Eingeschraenkter Zugriff: Nur Lesezugriff auf relevante Dokumente
    """
    __tablename__ = "tax_advisor_invites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Invite-Token (SHA-256 Hash fuer Sicherheit)
    token_hash = Column(
        String(128),
        unique=True,
        nullable=False,
        comment="SHA-256 Hash des Invite-Tokens"
    )

    # Referenzen
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Firma, fuer die der Zugang gilt"
    )
    invited_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Einladender Admin"
    )

    # Steuerberater-Daten
    email = Column(
        String(255),
        nullable=False,
        index=True,
        comment="E-Mail des Steuerberaters"
    )
    full_name = Column(
        String(255),
        nullable=True,
        comment="Name des Steuerberaters"
    )
    tax_firm_name = Column(
        String(255),
        nullable=True,
        comment="Name der Steuerkanzlei"
    )
    tax_advisor_id = Column(
        String(50),
        nullable=True,
        comment="Steuerberater-ID der Kammer (optional)"
    )

    # Zugangsparameter
    access_duration_days = Column(
        Integer,
        nullable=False,
        default=30,
        comment="Zugang in Tagen ab Akzeptierung"
    )
    access_scope = Column(
        CrossDBJSON,
        nullable=True,
        comment="Eingeschraenkter Zugriff (z.B. nur bestimmte Zeitraeume, Dokumenttypen)"
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default=TaxAdvisorInviteStatus.PENDING.value,
        index=True
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Ablaufdatum des Invite-Tokens (Standard: 7 Tage)"
    )

    # Audit
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    accepted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Akzeptierung"
    )
    accepted_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Erstellter Benutzer nach Akzeptierung"
    )

    # Relationships
    company = relationship("Company", backref="tax_advisor_invites")
    invited_by = relationship(
        "User",
        foreign_keys=[invited_by_id],
        backref="sent_tax_advisor_invites"
    )
    accepted_user = relationship(
        "User",
        foreign_keys=[accepted_user_id],
        backref="tax_advisor_invite"
    )

    __table_args__ = (
        Index("ix_tax_advisor_invites_status_expires", "status", "expires_at"),
        {"comment": "GoBD Steuerberater-Einladungen fuer temporaeren Prueferzugang"}
    )

    def __repr__(self) -> str:
        return f"<TaxAdvisorInvite {self.email} status={self.status}>"


class TaxAdvisorAccessLog(Base):
    """GoBD Steuerberater-Zugriffsprotokolle (revisionssicher).

    Protokolliert alle Aktivitaeten von Steuerberatern fuer:
    - GoBD-konforme Nachvollziehbarkeit
    - Pruefungsrelevante Dokumentation
    - Sicherheitsmonitoring

    Diese Logs sind revisionssicher und koennen nicht geaendert werden.
    """
    __tablename__ = "tax_advisor_access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktion
    action = Column(
        String(50),
        nullable=False,
        index=True,
        comment="document_view, archive_export, integrity_check, etc."
    )
    resource_type = Column(
        String(50),
        nullable=False,
        comment="document, archive, procedure_doc"
    )
    resource_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="ID der zugegriffenen Ressource"
    )

    # Details
    details = Column(
        CrossDBJSON,
        nullable=True,
        comment="Zusaetzliche Metadaten (Dateiname, Exportformat, etc.)"
    )
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Timestamp (immutable)
    accessed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True
    )

    # Relationships
    user = relationship("User", backref="tax_advisor_access_logs")
    company = relationship("Company", backref="tax_advisor_access_logs")

    __table_args__ = (
        Index("ix_tax_advisor_logs_user_action", "user_id", "action"),
        Index("ix_tax_advisor_logs_company_date", "company_id", "accessed_at"),
        {"comment": "GoBD Steuerberater-Zugriffsprotokolle (revisionssicher)"}
    )

    def __repr__(self) -> str:
        return f"<TaxAdvisorAccessLog {self.action} user={self.user_id}>"


# =============================================================================
# ERP Integration Models - Feature 04: Odoo-Integration
# =============================================================================


class ERPType(str, Enum):
    """Unterstuetzte ERP-Systeme."""
    ODOO = "odoo"
    LEXWARE = "lexware"
    SAP_B1 = "sap_b1"
    CUSTOM = "custom"


class ERPSyncDirection(str, Enum):
    """Synchronisationsrichtung."""
    PUSH = "push"
    PULL = "pull"
    BIDIRECTIONAL = "bidirectional"


class ERPConnectionStatus(str, Enum):
    """Verbindungsstatus."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    AUTHENTICATING = "authenticating"
    RATE_LIMITED = "rate_limited"


class ERPSyncStatus(str, Enum):
    """Sync-Status."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class ERPConflictStatus(str, Enum):
    """Konflikt-Status."""
    PENDING = "pending"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class ERPConflictResolution(str, Enum):
    """Konflikt-Aufloesung."""
    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"
    MERGED = "merged"
    MANUAL = "manual"


class ERPEntityType(str, Enum):
    """Synchronisierbare Entitaetstypen."""
    CUSTOMER = "customer"
    SUPPLIER = "supplier"
    INVOICE = "invoice"
    PAYMENT = "payment"
    PRODUCT = "product"
    DOCUMENT = "document"
    ORDER = "order"


class ERPConnection(Base):
    """ERP-Verbindungskonfiguration pro Firma.

    Speichert alle Verbindungsdetails und Sync-Einstellungen
    fuer die Integration mit externen ERP-Systemen.
    """
    __tablename__ = "erp_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Verbindungsdetails
    erp_type = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    url = Column(String(500), nullable=False)
    database_name = Column(String(255), nullable=True)

    # Credentials (verschluesselt)
    username = Column(String(255), nullable=False)
    encrypted_api_key = Column(Text, nullable=False)
    encryption_key_id = Column(String(100), nullable=True)

    # Sync-Einstellungen
    sync_direction = Column(String(20), nullable=False, default="bidirectional")
    sync_interval_minutes = Column(Integer, nullable=False, default=15)
    enabled_entities = Column(CrossDBJSON, nullable=False, default=list)

    # Rate Limiting
    max_requests_per_minute = Column(Integer, nullable=False, default=60)
    batch_size = Column(Integer, nullable=False, default=100)

    # Retry-Einstellungen
    max_retries = Column(Integer, nullable=False, default=3)
    retry_delay_seconds = Column(Integer, nullable=False, default=5)

    # Timeouts
    connect_timeout_seconds = Column(Integer, nullable=False, default=30)
    read_timeout_seconds = Column(Integer, nullable=False, default=60)

    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    connection_status = Column(String(30), nullable=False, default="disconnected")
    last_error = Column(Text, nullable=True)
    last_successful_connection = Column(DateTime(timezone=True), nullable=True)

    # Sync-Status
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_full_sync_at = Column(DateTime(timezone=True), nullable=True)
    next_scheduled_sync = Column(DateTime(timezone=True), nullable=True, index=True)

    # Metadaten
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    company = relationship("Company", backref="erp_connections")
    creator = relationship("User", foreign_keys=[created_by], backref="created_erp_connections")
    updater = relationship("User", foreign_keys=[updated_by], backref="updated_erp_connections")
    sync_history = relationship("ERPSyncHistory", back_populates="connection", cascade="all, delete-orphan")
    field_mappings = relationship("ERPFieldMapping", back_populates="connection", cascade="all, delete-orphan")
    conflicts = relationship("ERPConflict", back_populates="connection", cascade="all, delete-orphan")
    entity_mappings = relationship("ERPEntityMapping", back_populates="connection", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "ERP-Verbindungskonfiguration pro Firma"}
    )

    def __repr__(self) -> str:
        return f"<ERPConnection {self.name} type={self.erp_type}>"


class ERPSyncHistory(Base):
    """Protokoll aller ERP-Sync-Vorgaenge.

    Speichert Details zu jedem Sync-Lauf fuer Auditing,
    Debugging und Monitoring.
    """
    __tablename__ = "erp_sync_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Sync-Details
    sync_type = Column(String(20), nullable=False)  # full, delta, manual
    entity = Column(String(50), nullable=False, index=True)
    direction = Column(String(20), nullable=False)

    # Ergebnis
    status = Column(String(20), nullable=False, index=True)
    records_synced = Column(Integer, nullable=False, default=0)
    records_created = Column(Integer, nullable=False, default=0)
    records_updated = Column(Integer, nullable=False, default=0)
    records_deleted = Column(Integer, nullable=False, default=0)
    records_failed = Column(Integer, nullable=False, default=0)

    # Konflikte
    conflicts_detected = Column(Integer, nullable=False, default=0)
    conflicts_resolved = Column(Integer, nullable=False, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Fehlerdetails
    error_message = Column(Text, nullable=True)
    error_details = Column(CrossDBJSON, nullable=True)
    failed_records = Column(CrossDBJSON, nullable=True)

    # Metadaten
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    task_id = Column(String(100), nullable=True)

    # Relationships
    connection = relationship("ERPConnection", back_populates="sync_history")
    triggered_by_user = relationship("User", backref="triggered_erp_syncs")
    conflicts = relationship("ERPConflict", back_populates="sync_history")

    __table_args__ = (
        Index("ix_erp_sync_history_connection_entity", "connection_id", "entity"),
        {"comment": "Protokoll aller ERP-Sync-Vorgaenge"}
    )

    def __repr__(self) -> str:
        return f"<ERPSyncHistory {self.entity} status={self.status}>"


class ERPFieldMapping(Base):
    """Feld-Mapping zwischen Ablage-System und ERP.

    Konfiguriert wie Felder zwischen den Systemen
    gemappt und transformiert werden.
    """
    __tablename__ = "erp_field_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False
    )

    # Mapping-Definition
    entity = Column(String(50), nullable=False)
    local_field = Column(String(100), nullable=False)
    remote_field = Column(String(100), nullable=False)
    direction = Column(String(20), nullable=False, default="bidirectional")

    # Transformation
    transformer = Column(String(50), nullable=True)
    transformer_config = Column(CrossDBJSON, nullable=True)

    # Validierung
    required = Column(Boolean, nullable=False, default=False)
    default_value = Column(Text, nullable=True)

    # Metadaten
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    connection = relationship("ERPConnection", back_populates="field_mappings")

    __table_args__ = (
        UniqueConstraint("connection_id", "entity", "local_field", name="uq_erp_field_mappings_unique"),
        Index("ix_erp_field_mappings_connection_entity", "connection_id", "entity"),
        {"comment": "Feld-Mapping zwischen Ablage-System und ERP"}
    )

    def __repr__(self) -> str:
        return f"<ERPFieldMapping {self.local_field} -> {self.remote_field}>"


class ERPConflict(Base):
    """Sync-Konflikte zur manuellen Aufloesung.

    Speichert Konflikte die bei der bidirektionalen
    Synchronisation auftreten und manuelle Intervention
    benoetigen.
    """
    __tablename__ = "erp_conflicts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    sync_history_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_sync_history.id", ondelete="SET NULL"),
        nullable=True
    )

    # Konflikt-Details
    entity = Column(String(50), nullable=False, index=True)
    local_id = Column(String(100), nullable=False)
    remote_id = Column(String(100), nullable=False)

    # Daten
    local_data = Column(CrossDBJSON, nullable=False)
    remote_data = Column(CrossDBJSON, nullable=False)
    diff = Column(CrossDBJSON, nullable=True)

    # Zeitstempel
    local_modified_at = Column(DateTime(timezone=True), nullable=True)
    remote_modified_at = Column(DateTime(timezone=True), nullable=True)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Aufloesung
    status = Column(String(20), nullable=False, default="pending", index=True)
    resolution = Column(String(30), nullable=True)
    resolved_data = Column(CrossDBJSON, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Prioritaet
    priority = Column(String(20), nullable=False, default="normal", index=True)

    # Relationships
    connection = relationship("ERPConnection", back_populates="conflicts")
    sync_history = relationship("ERPSyncHistory", back_populates="conflicts")
    resolver = relationship("User", backref="resolved_erp_conflicts")

    __table_args__ = (
        {"comment": "ERP-Sync-Konflikte zur manuellen Aufloesung"}
    )

    def __repr__(self) -> str:
        return f"<ERPConflict {self.entity} local={self.local_id} remote={self.remote_id}>"


class ERPEntityMapping(Base):
    """Verknuepfung lokaler Entitaeten mit ERP-IDs.

    Speichert die Zuordnung zwischen lokalen und
    Remote-Entitaeten fuer Delta-Sync und Konflikt-Erkennung.
    """
    __tablename__ = "erp_entity_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False
    )

    # Entitaets-Verknuepfung
    entity_type = Column(String(50), nullable=False)
    local_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    remote_id = Column(String(100), nullable=False, index=True)

    # Sync-Status
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    local_version = Column(Integer, nullable=False, default=1)
    remote_version = Column(String(100), nullable=True)

    # Checksums
    local_checksum = Column(String(64), nullable=True)
    remote_checksum = Column(String(64), nullable=True)

    # Metadaten
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    connection = relationship("ERPConnection", back_populates="entity_mappings")

    __table_args__ = (
        UniqueConstraint("connection_id", "entity_type", "local_id", name="uq_erp_entity_mappings_local"),
        UniqueConstraint("connection_id", "entity_type", "remote_id", name="uq_erp_entity_mappings_remote"),
        Index("ix_erp_entity_mappings_connection_entity", "connection_id", "entity_type"),
        {"comment": "Verknuepfung lokaler Entitaeten mit ERP-IDs"}
    )

    def __repr__(self) -> str:
        return f"<ERPEntityMapping {self.entity_type} local={self.local_id} remote={self.remote_id}>"


# =============================================================================
# ODOO INTEGRATION - Phase 6: Webhooks, Extended Sync, AI Feedback
# =============================================================================


class OdooWebhookEvent(Base):
    """Odoo Webhook Events fuer idempotente Verarbeitung.

    Speichert empfangene Webhooks fuer:
    - Idempotenz-Pruefung (doppelte Events ignorieren)
    - Retry-Logik bei Fehlern
    - Audit-Trail
    """
    __tablename__ = "odoo_webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Event-Identifikation (fuer Idempotenz)
    event_id = Column(String(255), nullable=False, index=True, comment="Odoo webhook event ID")
    event_type = Column(String(100), nullable=False, index=True, comment="customer, supplier, invoice, etc.")
    action = Column(String(50), nullable=False, comment="create, update, delete")

    # Payload-Tracking
    payload_hash = Column(String(64), nullable=False, comment="SHA-256 hash of payload")
    payload_preview = Column(CrossDBJSON, nullable=True, comment="Sanitized preview (no PII)")
    odoo_record_id = Column(String(100), nullable=True, index=True, comment="ID of record in Odoo")

    # Verarbeitungsstatus
    status = Column(String(30), nullable=False, default="pending", index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processing_attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Task-Tracking
    task_id = Column(String(100), nullable=True, comment="Celery task ID")

    # Zeitstempel
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    connection = relationship("ERPConnection", backref="webhook_events")

    __table_args__ = (
        UniqueConstraint("connection_id", "event_id", name="uq_odoo_webhook_event_id"),
        Index("ix_odoo_webhook_events_status_received", "status", "received_at"),
        {"comment": "Odoo webhook events for idempotent processing"}
    )

    def __repr__(self) -> str:
        return f"<OdooWebhookEvent {self.event_type}/{self.action} status={self.status}>"


class OdooSyncStatus(Base):
    """Sync-Status pro Datentyp fuer erweiterte Odoo-Synchronisation.

    Trackt den Sync-Zustand fuer:
    - Projects
    - Timesheet
    - Inventory/Stock Moves
    - Products

    Ermoeglicht Delta-Sync und Fehler-Tracking.
    """
    __tablename__ = "odoo_sync_status"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False
    )

    # Datentyp-Identifikation
    data_type = Column(String(50), nullable=False, comment="projects, timesheet, inventory, products")

    # Sync-Status
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_successful_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_sync_cursor = Column(String(255), nullable=True, comment="Cursor/offset for incremental sync")
    sync_state = Column(CrossDBJSON, nullable=True, comment="Additional state data")

    # Statistiken
    total_records_synced = Column(BigInteger, nullable=False, default=0)
    records_synced_today = Column(Integer, nullable=False, default=0)
    last_record_count = Column(Integer, nullable=True)

    # Fehler-Tracking
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    is_paused = Column(Boolean, nullable=False, default=False, comment="Paused due to errors")

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    connection = relationship("ERPConnection", backref="sync_statuses")

    __table_args__ = (
        UniqueConstraint("connection_id", "data_type", name="uq_odoo_sync_status_type"),
        Index("ix_odoo_sync_status_connection", "connection_id"),
        {"comment": "Extended sync status per data type for Odoo"}
    )

    def __repr__(self) -> str:
        return f"<OdooSyncStatus {self.data_type} last_sync={self.last_sync_at}>"


class OdooAIFeedback(Base):
    """AI-Feedback das zu Odoo gepusht wird.

    Speichert:
    - Risk Scores
    - Payment Suggestions
    - Skonto Predictions

    Fuer Tracking und Retry-Logik.
    """
    __tablename__ = "odoo_ai_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Feedback-Typ und Daten
    feedback_type = Column(String(50), nullable=False, index=True, comment="risk_score, payment_suggestion, skonto_prediction")
    feedback_data = Column(CrossDBJSON, nullable=False, comment="The feedback data (sanitized)")
    odoo_field = Column(String(100), nullable=True, comment="Target field in Odoo")

    # Push-Status
    status = Column(String(30), nullable=False, default="pending", index=True)
    pushed_at = Column(DateTime(timezone=True), nullable=True)
    push_attempts = Column(Integer, nullable=False, default=0)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Odoo-Antwort
    odoo_record_id = Column(String(100), nullable=True, comment="ID of updated record in Odoo")
    odoo_response = Column(CrossDBJSON, nullable=True, comment="Sanitized response")

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    connection = relationship("ERPConnection", backref="ai_feedbacks")
    entity = relationship("BusinessEntity", backref="odoo_ai_feedbacks")

    __table_args__ = (
        Index("ix_odoo_ai_feedback_status_created", "status", "created_at"),
        {"comment": "AI feedback pushed to Odoo (risk scores, suggestions)"}
    )

    def __repr__(self) -> str:
        return f"<OdooAIFeedback {self.feedback_type} status={self.status}>"


# =============================================================================
# EMAIL & FOLDER IMPORT MODELS
# =============================================================================


class EmailImportConfig(Base):
    """IMAP Server-Konfigurationen fuer E-Mail-Import.

    Speichert verschluesselte Credentials und Sync-Einstellungen
    fuer automatischen E-Mail-Import.
    """
    __tablename__ = "email_import_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Konfigurationsname
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # IMAP Server-Einstellungen
    imap_server = Column(String(255), nullable=False)
    imap_port = Column(Integer, default=993)
    use_ssl = Column(Boolean, default=True)
    use_starttls = Column(Boolean, default=False)

    # Verschluesselte Credentials (AES-256-GCM)
    username_encrypted = Column(String(500), nullable=False)
    password_encrypted = Column(String(500), nullable=False)

    # IMAP-Ordner
    imap_folder = Column(String(255), default="INBOX")
    processed_folder = Column(String(255), nullable=True)
    error_folder = Column(String(255), nullable=True)

    # Sync-Einstellungen
    sync_interval_minutes = Column(Integer, default=15)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    last_uid = Column(BigInteger, default=0)

    # Filter-Einstellungen
    filter_from_addresses = Column(CrossDBJSON, default=list)
    filter_subject_patterns = Column(CrossDBJSON, default=list)
    filter_attachment_types = Column(CrossDBJSON, default=list)

    # Verarbeitungs-Optionen
    extract_attachments_only = Column(Boolean, default=True)
    include_email_body_as_document = Column(Boolean, default=False)
    auto_classify = Column(Boolean, default=True)
    auto_ocr = Column(Boolean, default=True)
    default_folder_id = Column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, index=True)
    connection_status = Column(String(50), default="pending")
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, default=0)

    # Statistiken
    total_emails_processed = Column(Integer, default=0)
    total_documents_created = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="email_import_configs")
    company = relationship("Company", backref="email_import_configs")
    # default_folder relationship is disabled - Folder model not implemented yet
    import_logs = relationship("ImportLog", back_populates="email_config", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_email_import_configs_user_name"),
        {"comment": "IMAP Server-Konfigurationen fuer E-Mail-Import"}
    )

    def __repr__(self) -> str:
        return f"<EmailImportConfig {self.name} ({self.imap_server})>"


class FolderImportConfig(Base):
    """Hotfolder-Konfigurationen fuer Ordner-Import.

    Ueberwacht lokale Ordner oder Netzwerkpfade auf neue Dateien
    und importiert diese automatisch.
    """
    __tablename__ = "folder_import_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Konfigurationsname
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Ordner-Einstellungen
    watch_path = Column(String(1000), nullable=False)
    is_network_path = Column(Boolean, default=False)
    network_credentials_encrypted = Column(String(500), nullable=True)

    # Verhalten
    recursive = Column(Boolean, default=False)
    include_patterns = Column(CrossDBJSON, default=lambda: ["*.pdf", "*.jpg", "*.png", "*.tiff"])
    exclude_patterns = Column(CrossDBJSON, default=lambda: ["*.tmp", "~*", "._*"])

    # Verarbeitung nach Import
    move_after_processing = Column(Boolean, default=True)
    processed_subfolder = Column(String(255), default="processed")
    error_subfolder = Column(String(255), default="error")
    delete_after_processing = Column(Boolean, default=False)

    # Import-Optionen
    auto_classify = Column(Boolean, default=True)
    auto_ocr = Column(Boolean, default=True)
    default_folder_id = Column(UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True)
    preserve_filename = Column(Boolean, default=True)

    # Polling (Backup fuer Watchdog)
    poll_interval_seconds = Column(Integer, default=60)
    last_poll_at = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, index=True)
    watcher_status = Column(String(50), default="stopped")
    last_error = Column(Text, nullable=True)

    # Statistiken
    files_processed_today = Column(Integer, default=0)
    total_files_processed = Column(Integer, default=0)
    total_documents_created = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="folder_import_configs")
    company = relationship("Company", backref="folder_import_configs")
    # default_folder relationship is disabled - Folder model not implemented yet
    import_logs = relationship("ImportLog", back_populates="folder_config", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("user_id", "watch_path", name="uq_folder_import_configs_user_path"),
        {"comment": "Hotfolder-Konfigurationen fuer Ordner-Import"}
    )

    def __repr__(self) -> str:
        return f"<FolderImportConfig {self.name} ({self.watch_path})>"


class ImportRule(Base):
    """Filter- und Routing-Regeln fuer Import.

    Ermoeglicht automatische Klassifizierung, Ordner-Zuweisung
    und weitere Aktionen basierend auf Bedingungen.
    """
    __tablename__ = "import_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Regel-Identitaet
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Integer, default=100, index=True)

    # Quelle (auf welche Configs diese Regel angewendet wird)
    applies_to_email_configs = Column(CrossDBJSON, default=list)
    applies_to_folder_configs = Column(CrossDBJSON, default=list)
    applies_to_all = Column(Boolean, default=False)

    # Bedingungen (JSON-Struktur fuer flexible Matching)
    # Format:
    # {
    #   "operator": "AND" | "OR",
    #   "rules": [
    #     {"field": "sender_email", "operator": "contains", "value": "@lieferant.de"},
    #     {"field": "subject", "operator": "regex", "value": "Rechnung.*\\d{6}"},
    #   ]
    # }
    conditions = Column(CrossDBJSON, nullable=False, default=dict)

    # Aktionen
    # Format:
    # {
    #   "assign_folder_id": "uuid",
    #   "assign_tags": ["uuid1", "uuid2"],
    #   "assign_document_type": "invoice",
    #   "skip_ocr": false,
    #   "priority_ocr": true,
    #   "notify_users": ["uuid1"],
    # }
    actions = Column(CrossDBJSON, nullable=False, default=dict)

    # Status
    is_active = Column(Boolean, default=True, index=True)
    match_count = Column(Integer, default=0)
    last_matched_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="import_rules")
    matched_logs = relationship("ImportLog", back_populates="matched_rule")

    __table_args__ = (
        {"comment": "Filter- und Routing-Regeln fuer Import"}
    )

    def __repr__(self) -> str:
        return f"<ImportRule {self.name} (priority={self.priority})>"


class ImportLog(Base):
    """Import-Historie mit Status-Tracking.

    Protokolliert jeden Import-Vorgang fuer Audit und Fehleranalyse.
    """
    __tablename__ = "import_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Quell-Referenz
    source_type = Column(String(20), nullable=False, index=True)  # 'email' oder 'folder'
    email_config_id = Column(UUID(as_uuid=True), ForeignKey("email_import_configs.id", ondelete="SET NULL"), nullable=True, index=True)
    folder_config_id = Column(UUID(as_uuid=True), ForeignKey("folder_import_configs.id", ondelete="SET NULL"), nullable=True, index=True)

    # Import-Batch-Info
    batch_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    celery_task_id = Column(String(100), nullable=True)

    # Email-spezifische Details
    email_uid = Column(BigInteger, nullable=True)
    email_message_id = Column(String(255), nullable=True)
    email_from = Column(String(255), nullable=True)
    email_subject = Column(String(500), nullable=True)
    email_date = Column(DateTime(timezone=True), nullable=True)

    # Folder-spezifische Details
    original_path = Column(String(1000), nullable=True)
    original_filename = Column(String(255), nullable=True)
    file_modified_at = Column(DateTime(timezone=True), nullable=True)

    # Verarbeitungs-Ergebnis
    status = Column(String(50), nullable=False, index=True)  # pending, processing, completed, failed, skipped
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)  # SHA256 fuer Deduplizierung
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(100), nullable=True)

    # Regel-Matching
    matched_rule_id = Column(UUID(as_uuid=True), ForeignKey("import_rules.id", ondelete="SET NULL"), nullable=True)
    applied_actions = Column(CrossDBJSON, default=dict)

    # Fehler-Tracking
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    retry_count = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    processing_duration_ms = Column(Integer, nullable=True)

    # Relationships
    user = relationship("User", backref="import_logs")
    email_config = relationship("EmailImportConfig", back_populates="import_logs")
    folder_config = relationship("FolderImportConfig", back_populates="import_logs")
    document = relationship("Document", backref="import_log")
    matched_rule = relationship("ImportRule", back_populates="matched_logs")

    __table_args__ = (
        {"comment": "Import-Historie mit Status-Tracking"}
    )

    def __repr__(self) -> str:
        return f"<ImportLog {self.source_type} status={self.status}>"


# =============================================================================
# AI Autonomy Models (Feature 07)
# =============================================================================

class AIConfidenceThreshold(Base):
    """Admin-konfigurierbare Konfidenz-Schwellenwerte.

    Definiert pro Entscheidungstyp ab welcher Konfidenz automatisch
    angewendet wird (auto), nur vorgeschlagen (suggest) oder
    manuell geprueft werden muss (manual).
    """
    __tablename__ = "ai_confidence_thresholds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Decision Type (unique per company)
    decision_type = Column(String(50), nullable=False, index=True)
    # Types: categorization, accounting, matching, anomaly, prediction, duplicate

    # Schwellenwerte (0.0 - 1.0)
    auto_threshold = Column(Float, default=0.95)  # Ab hier automatisch
    suggest_threshold = Column(Float, default=0.80)  # Ab hier vorschlagen
    # Unter suggest_threshold = manuelle Review

    # Feature-Toggle
    is_enabled = Column(Boolean, default=True)
    allow_auto_apply = Column(Boolean, default=True)

    # Beschreibung fuer Admin-UI
    display_name = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)

    # Audit
    updated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="ai_thresholds")
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        UniqueConstraint("company_id", "decision_type", name="uq_ai_threshold_company_type"),
        {"comment": "Admin-konfigurierbare KI-Konfidenz-Schwellenwerte"}
    )

    def __repr__(self) -> str:
        return f"<AIConfidenceThreshold {self.decision_type} auto={self.auto_threshold}>"


class AIDecision(Base):
    """KI-Entscheidung mit vollstaendigem Audit-Trail.

    Speichert jede KI-Entscheidung mit Konfidenz, Erklaerung und
    Review-Status fuer GoBD-Compliance und Self-Learning.
    """
    __tablename__ = "ai_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)

    # Decision Type
    decision_type = Column(String(50), nullable=False, index=True)
    # Types: categorization, accounting, matching, anomaly, prediction, duplicate

    # Entscheidungs-Details
    decision_value = Column(CrossDBJSON, nullable=False)
    # Beispiel categorization: {"category": "invoice_incoming", "subcategory": "supplier_invoice"}
    # Beispiel accounting: {"debit_account": "4000", "credit_account": "1600", "tax_code": "VSt19"}
    # Beispiel matching: {"matched_document_id": "...", "match_type": "invoice_delivery"}

    # Confidence
    confidence = Column(Float, nullable=False)  # 0.0 - 1.0
    calibrated_confidence = Column(Float, nullable=True)  # Nach Kalibrierung
    confidence_level = Column(String(20), nullable=False, index=True)  # auto, suggest, manual

    # Explainable AI
    explanation = Column(CrossDBJSON, nullable=True)
    # Beispiel: {"reasons": ["Keyword 'Rechnung' gefunden", "Lieferant bekannt"], "features": {...}}
    features_used = Column(CrossDBJSON, nullable=True)  # Welche Features verwendet
    model_version = Column(String(50), nullable=True)  # Modell-Version fuer Reproduzierbarkeit

    # Autonomie-Status
    auto_applied = Column(Boolean, default=False)  # Automatisch angewendet?
    requires_review = Column(Boolean, default=True, index=True)  # Muss geprueft werden?
    is_final = Column(Boolean, default=False)  # Wurde final entschieden?

    # Review-Informationen
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_action = Column(String(20), nullable=True)  # approved, rejected, modified
    review_comment = Column(Text, nullable=True)

    # Bei Modifikation: Was wurde geaendert?
    modified_value = Column(CrossDBJSON, nullable=True)

    # Timing
    processing_time_ms = Column(Integer, nullable=True)

    # Audit/Compliance
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="ai_decisions")
    document = relationship("Document", backref="ai_decisions")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    feedback = relationship("AILearningFeedback", back_populates="ai_decision", uselist=False)

    __table_args__ = (
        Index("ix_ai_decisions_pending_review", "decision_type", "requires_review", "is_final"),
        {"comment": "KI-Entscheidungen mit vollstaendigem Audit-Trail"}
    )

    def __repr__(self) -> str:
        return f"<AIDecision {self.decision_type} conf={self.confidence:.2f} level={self.confidence_level}>"


class AILearningFeedback(Base):
    """Self-Learning Feedback aus User-Korrekturen.

    Speichert Korrekturen und Ablehnungen um die KI-Modelle
    kontinuierlich zu verbessern.
    """
    __tablename__ = "ai_learning_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ai_decision_id = Column(UUID(as_uuid=True), ForeignKey("ai_decisions.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Feedback-Typ
    feedback_type = Column(String(20), nullable=False, index=True)
    # Types: approved, corrected, rejected

    # Original vs. Korrigiert
    original_value = Column(CrossDBJSON, nullable=False)
    corrected_value = Column(CrossDBJSON, nullable=True)  # Nur bei 'corrected'

    # Korrektur-Details
    correction_reason = Column(Text, nullable=True)
    correction_category = Column(String(50), nullable=True)  # z.B. "wrong_category", "missing_info"

    # Wer hat korrigiert
    corrector_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Learning-Status
    processed_for_learning = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    learning_batch_id = Column(String(50), nullable=True)

    # Gewichtung fuer Learning
    learning_weight = Column(Float, default=1.0)  # Hoeher = wichtiger

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    ai_decision = relationship("AIDecision", back_populates="feedback")
    company = relationship("Company", backref="ai_learning_feedback")
    corrector = relationship("User", foreign_keys=[corrector_id])

    __table_args__ = (
        {"comment": "Self-Learning Feedback aus User-Korrekturen"}
    )

    def __repr__(self) -> str:
        return f"<AILearningFeedback {self.feedback_type} processed={self.processed_for_learning}>"


class DocumentMatch(Base):
    """Smart Matching zwischen zusammengehoerenden Dokumenten.

    Speichert KI-erkannte Verbindungen zwischen Dokumenten,
    z.B. Rechnung <-> Lieferschein <-> Bestellung.
    """
    __tablename__ = "document_matches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Quell- und Ziel-Dokument
    source_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    target_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)

    # Match-Typ
    match_type = Column(String(50), nullable=False, index=True)
    # Types: invoice_delivery, invoice_order, delivery_order, invoice_contract, etc.

    # Match-Qualitaet
    match_confidence = Column(Float, nullable=False)
    match_score = Column(Float, nullable=True)  # Detaillierter Score
    match_features = Column(CrossDBJSON, nullable=True)
    # Beispiel: {"order_number": 0.95, "customer": 0.90, "amount": 0.85, "date": 0.70}

    # Verknuepfungs-Status
    auto_linked = Column(Boolean, default=False)
    is_confirmed = Column(Boolean, default=False, index=True)
    is_rejected = Column(Boolean, default=False)

    # Wer hat verknuepft/bestaetigt
    linked_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Referenz zur AI-Entscheidung
    ai_decision_id = Column(UUID(as_uuid=True), ForeignKey("ai_decisions.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="document_matches")
    source_document = relationship("Document", foreign_keys=[source_document_id], backref="matches_as_source")
    target_document = relationship("Document", foreign_keys=[target_document_id], backref="matches_as_target")
    linked_by = relationship("User", foreign_keys=[linked_by_id])
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])
    ai_decision = relationship("AIDecision", backref="document_match")

    __table_args__ = (
        UniqueConstraint("source_document_id", "target_document_id", name="uq_document_match_pair"),
        {"comment": "Smart Matching zwischen Dokumenten"}
    )

    def __repr__(self) -> str:
        return f"<DocumentMatch {self.match_type} conf={self.match_confidence:.2f}>"


class PaymentPrediction(Base):
    """Zahlungsvorhersagen fuer Rechnungen.

    Prognostiziert basierend auf Historie wann eine Rechnung
    bezahlt wird fuer Cashflow-Planung.
    """
    __tablename__ = "payment_predictions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    business_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True, index=True)

    # Vorhersage
    predicted_payment_date = Column(Date, nullable=False, index=True)
    predicted_days = Column(Integer, nullable=False)  # Tage ab Rechnungsdatum
    confidence = Column(Float, nullable=False)

    # Vorhersage-Details
    prediction_features = Column(CrossDBJSON, nullable=True)
    # Beispiel: {"historical_avg_days": 25, "invoice_amount": 5000, "payment_terms": "net30"}

    # Modell-Info
    model_version = Column(String(50), nullable=True)
    prediction_date = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Tatsaechliche Zahlung (fuer Learning)
    actual_payment_date = Column(Date, nullable=True)
    actual_days = Column(Integer, nullable=True)
    prediction_error_days = Column(Integer, nullable=True)  # Differenz

    # Status
    is_paid = Column(Boolean, default=False, index=True)
    is_overdue = Column(Boolean, default=False)

    # Referenz zur AI-Entscheidung
    ai_decision_id = Column(UUID(as_uuid=True), ForeignKey("ai_decisions.id", ondelete="SET NULL"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="payment_predictions")
    document = relationship("Document", backref="payment_predictions")
    business_entity = relationship("BusinessEntity", backref="payment_predictions")
    ai_decision = relationship("AIDecision", backref="payment_prediction")

    __table_args__ = (
        {"comment": "Zahlungsvorhersagen fuer Cashflow-Planung"}
    )

    def __repr__(self) -> str:
        return f"<PaymentPrediction predicted={self.predicted_payment_date} conf={self.confidence:.2f}>"


# =============================================================================
# AUTONOMOUS TRUST SYSTEM MODELS (Phase 2.1)
# Multi-Level Trust fuer autonome KI-Aktionen
# =============================================================================


class AutonomousTrustConfig(Base):
    """Trust-Level Konfiguration pro Company.

    Speichert das aktuelle Trust-Level und Konfiguration fuer
    autonome KI-Aktionen. Kann global oder pro Dokumenttyp sein.

    Trust-Level:
    - LEVEL_1_ASSISTANCE: Alle Aktionen erfordern Bestaetigung
    - LEVEL_2_AUTO_ACCEPT: >90% Confidence, 24h Auto-Accept
    - LEVEL_3_CONFIDENCE: >95% sofort, 80-95% verzoegert (4h)
    - LEVEL_4_AUTONOMOUS: Volle Autonomie, nur Exceptions
    """
    __tablename__ = "autonomous_trust_config"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Trust Level
    trust_level = Column(
        String(50),
        nullable=False,
        default="assistance",
        comment="Trust-Level: assistance, auto_accept, confidence, autonomous"
    )

    # Optional: Spezifisch fuer Dokumenttyp
    document_type = Column(
        String(50),
        nullable=True,
        comment="Optional: Spezifisches Level fuer diesen Dokumenttyp"
    )

    # Konfiguration
    is_enabled = Column(Boolean, default=True)

    # Schwellenwerte (Override der Defaults)
    immediate_threshold = Column(
        Float,
        nullable=True,
        comment="Ab hier sofortige Aktion (Override)"
    )
    delayed_threshold = Column(
        Float,
        nullable=True,
        comment="Ab hier verzoegerte Aktion (Override)"
    )
    delay_hours = Column(
        Integer,
        nullable=True,
        comment="Wartezeit in Stunden (Override)"
    )

    # Metriken-Snapshot (wird periodisch aktualisiert)
    metrics_snapshot = Column(
        CrossDBJSON,
        nullable=True,
        comment="Letzter Metriken-Snapshot (total_decisions, approval_rate, etc.)"
    )
    metrics_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Trust-Level Aenderungshistorie
    level_changed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der letzten Level-Aenderung"
    )
    change_reason = Column(
        Text,
        nullable=True,
        comment="Grund fuer letzte Level-Aenderung"
    )

    # Audit
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="autonomous_trust_configs")
    updated_by = relationship("User", foreign_keys=[updated_by_id])

    __table_args__ = (
        UniqueConstraint("company_id", "document_type", name="uq_trust_config_company_doctype"),
        {"comment": "Trust-Level Konfiguration fuer autonome KI-Aktionen"}
    )

    def __repr__(self) -> str:
        return f"<AutonomousTrustConfig company={self.company_id} level={self.trust_level} doc_type={self.document_type}>"


class AutonomousProposalQueue(Base):
    """Queue fuer verzoegerte Auto-Akzeptanz.

    Speichert Vorschlaege, die nicht sofort ausgefuehrt werden:
    - Level 2: 24h Wartezeit bei >90% Confidence
    - Level 3: 4h Wartezeit bei 80-95% Confidence

    Features:
    - Timeout-Handling mit automatischer Ausfuehrung
    - User-Intervention (vorzeitige Genehmigung/Ablehnung)
    - Rollback-Faehigkeit fuer 7 Tage
    """
    __tablename__ = "autonomous_proposal_queue"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Proposal Details
    proposal_type = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Typ: file_document, approve_payment, send_dunning, update_master_data, assign_entity, classify_document"
    )
    target_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="ID des Ziel-Objekts (Document, Invoice, Entity, etc.)"
    )
    proposed_value = Column(
        CrossDBJSON,
        nullable=False,
        comment="Vorgeschlagener Wert als JSON"
    )

    # Confidence und Timing
    confidence = Column(Float, nullable=False)
    delay_hours = Column(
        Integer,
        nullable=False,
        comment="Urspruengliche Verzoegerung in Stunden"
    )
    scheduled_at = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Geplante Ausfuehrungszeit"
    )

    # Status
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        index=True,
        comment="pending, approved, rejected, auto_accepted, expired, rolled_back, cancelled"
    )

    # Ausfuehrung
    executed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Ausfuehrung"
    )
    executed_by = Column(
        String(100),
        nullable=True,
        comment="User-ID oder 'system' bei Auto-Accept"
    )

    # Rollback
    rollback_until = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Bis wann Rollback moeglich ist"
    )

    # Referenzen
    ai_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_decisions.id", ondelete="SET NULL"),
        nullable=True,
        comment="Referenz zur urspruenglichen AI-Decision"
    )
    reasoning = Column(
        Text,
        nullable=True,
        comment="Begruendung des Vorschlags"
    )
    proposal_metadata = Column(
        CrossDBJSON,
        nullable=True,
        comment="Zusaetzliche Metadaten"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="autonomous_proposals")
    ai_decision = relationship("AIDecision", backref="proposal_queue_items")

    __table_args__ = (
        {"comment": "Queue fuer verzoegerte Auto-Akzeptanz mit Rollback"}
    )

    def __repr__(self) -> str:
        return f"<AutonomousProposalQueue {self.proposal_type} status={self.status} conf={self.confidence:.2f}>"


# =============================================================================
# REPORT BUILDER MODELS (Feature 08)
# =============================================================================


class ReportTemplate(Base):
    """Report-Template Definition.

    Speichert die Konfiguration eines benutzerdefinierten Reports.
    """
    __tablename__ = "report_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Basis-Informationen
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Report-Typ und Datenquelle
    report_type = Column(String(50), nullable=False, index=True)  # document|finance|ocr|custom
    data_source = Column(String(50), nullable=False)  # documents|invoices|entities|ocr_results
    default_format = Column(String(20), nullable=False, default="excel")  # pdf|excel|csv|json

    # Sichtbarkeit
    is_public = Column(Boolean, nullable=False, default=False, index=True)

    # Zeitplan-Konfiguration
    is_scheduled = Column(Boolean, nullable=False, default=False, index=True)
    schedule_config = Column(CrossDBJSON, nullable=True)  # {cron, timezone, recipients}

    # Layout-Konfiguration
    layout_config = Column(CrossDBJSON, nullable=True)  # {orientation, margins, header, footer}

    # Sortierung und Gruppierung
    sort_config = Column(CrossDBJSON, nullable=True)  # [{field, direction}]
    group_by_config = Column(CrossDBJSON, nullable=True)  # [field_paths]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="report_templates")
    company = relationship("Company", backref="report_templates")
    columns = relationship("ReportColumn", back_populates="template", cascade="all, delete-orphan", order_by="ReportColumn.sort_order")
    filters = relationship("ReportFilter", back_populates="template", cascade="all, delete-orphan", order_by="ReportFilter.sort_order")
    charts = relationship("ReportChart", back_populates="template", cascade="all, delete-orphan", order_by="ReportChart.sort_order")
    executions = relationship("ReportExecution", back_populates="template", cascade="all, delete-orphan", order_by="desc(ReportExecution.created_at)")
    shares = relationship("ReportShare", back_populates="template", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "Report-Template Definitionen fuer Report Builder"}
    )

    def __repr__(self) -> str:
        return f"<ReportTemplate '{self.name}' type={self.report_type}>"


class ReportColumn(Base):
    """Spalten-Konfiguration fuer Report-Templates.

    Definiert welche Felder im Report angezeigt werden und wie.
    """
    __tablename__ = "report_columns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)

    # Feld-Definition
    field_path = Column(String(255), nullable=False)  # z.B. "extracted_data.invoice_number"
    display_name = Column(String(255), nullable=False)  # z.B. "Rechnungsnummer"
    data_type = Column(String(50), nullable=False)  # string|number|date|currency|boolean

    # Formatierung
    format_pattern = Column(String(100), nullable=True)  # z.B. "#,##0.00 EUR"
    width = Column(Integer, nullable=True)  # Spaltenbreite

    # Reihenfolge und Sichtbarkeit
    sort_order = Column(Integer, nullable=False, default=0)
    is_visible = Column(Boolean, nullable=False, default=True)

    # Aggregation
    aggregation = Column(String(20), nullable=True)  # none|sum|avg|count|min|max

    # Bedingte Formatierung
    conditional_format = Column(CrossDBJSON, nullable=True)  # [{condition, style}]

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="columns")

    __table_args__ = (
        Index("ix_report_columns_sort_order", "template_id", "sort_order"),
        {"comment": "Spalten-Konfiguration fuer Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportColumn '{self.display_name}' path={self.field_path}>"


class ReportFilter(Base):
    """Filter-Bedingungen fuer Report-Templates.

    Definiert Filterbedingungen die auf die Daten angewendet werden.
    """
    __tablename__ = "report_filters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)

    # Filter-Definition
    field_path = Column(String(255), nullable=False)  # z.B. "status"
    operator = Column(String(50), nullable=False)  # eq|ne|gt|lt|gte|lte|contains|in|between|is_null
    value = Column(CrossDBJSON, nullable=True)  # Wert(e) je nach Operator

    # Logische Verknuepfung
    logic_operator = Column(String(10), nullable=False, default="AND")  # AND|OR
    group_id = Column(Integer, nullable=True)  # Fuer verschachtelte Gruppen

    # Reihenfolge
    sort_order = Column(Integer, nullable=False, default=0)

    # Dynamische Werte
    is_dynamic = Column(Boolean, nullable=False, default=False)
    dynamic_source = Column(String(100), nullable=True)  # z.B. "current_user", "today", "last_30_days"

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="filters")

    __table_args__ = (
        {"comment": "Filter-Bedingungen fuer Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportFilter {self.field_path} {self.operator} {self.value}>"


class ReportChart(Base):
    """Chart-Konfiguration fuer Report-Templates.

    Definiert Visualisierungen die im Report angezeigt werden.
    """
    __tablename__ = "report_charts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)

    # Chart-Typ
    chart_type = Column(String(50), nullable=False)  # bar|line|pie|area|scatter
    title = Column(String(255), nullable=True)

    # Daten-Mapping
    x_axis_field = Column(String(255), nullable=True)  # Kategorie/X-Achse
    y_axis_fields = Column(CrossDBJSON, nullable=False)  # Liste von Feldern fuer Y-Achse
    group_by_field = Column(String(255), nullable=True)  # Optional: Gruppierung

    # Styling
    colors = Column(CrossDBJSON, nullable=True)  # Benutzerdefinierte Farben
    show_legend = Column(Boolean, nullable=False, default=True)
    show_labels = Column(Boolean, nullable=False, default=False)

    # Position
    position = Column(String(20), nullable=False, default="bottom")  # top|bottom|separate_sheet
    width_percent = Column(Integer, nullable=False, default=100)
    height_px = Column(Integer, nullable=False, default=300)

    # Reihenfolge
    sort_order = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="charts")

    __table_args__ = (
        {"comment": "Chart-Konfiguration fuer Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportChart '{self.title}' type={self.chart_type}>"


class ReportExecution(Base):
    """Ausfuehrungs-Historie fuer Report-Templates.

    Speichert wann ein Report ausgefuehrt wurde und das Ergebnis.
    """
    __tablename__ = "report_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    executed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Ausfuehrung
    status = Column(String(50), nullable=False, default="pending", index=True)  # pending|running|completed|failed
    format = Column(String(20), nullable=False)  # pdf|excel|csv|json
    trigger_type = Column(String(50), nullable=False)  # manual|scheduled|api

    # Ergebnis
    row_count = Column(Integer, nullable=True)
    file_size_bytes = Column(BigInteger, nullable=True)
    file_path = Column(String(500), nullable=True)  # MinIO Pfad
    download_url = Column(String(1000), nullable=True)  # Signierte URL
    download_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Fehler-Details
    error_message = Column(Text, nullable=True)
    error_details = Column(CrossDBJSON, nullable=True)

    # Filter-Snapshot
    filter_snapshot = Column(CrossDBJSON, nullable=True)

    # Performance-Metriken
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    template = relationship("ReportTemplate", back_populates="executions")
    executed_by = relationship("User", backref="report_executions")

    __table_args__ = (
        {"comment": "Ausfuehrungs-Historie fuer Report-Templates"}
    )

    def __repr__(self) -> str:
        return f"<ReportExecution status={self.status} rows={self.row_count}>"


class ReportShare(Base):
    """Freigaben fuer Report-Templates.

    Ermoeglicht das Teilen von Reports mit anderen Benutzern.
    """
    __tablename__ = "report_shares"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False, index=True)
    shared_with_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    shared_with_group_id = Column(UUID(as_uuid=True), nullable=True)  # Falls Gruppen-Support existiert

    # Berechtigungen
    can_view = Column(Boolean, nullable=False, default=True)
    can_execute = Column(Boolean, nullable=False, default=True)
    can_edit = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)

    # Wer hat geteilt
    shared_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    template = relationship("ReportTemplate", back_populates="shares")
    shared_with_user = relationship("User", foreign_keys=[shared_with_user_id], backref="shared_reports")
    shared_by = relationship("User", foreign_keys=[shared_by_id], backref="reports_shared_by_me")

    __table_args__ = (
        Index("uq_report_shares_template_user", "template_id", "shared_with_user_id", unique=True),
        {"comment": "Freigaben fuer Report-Templates"}
    )


# =============================================================================
# WORKFLOW-AUTOMATION MODELS (Feature 09)
# =============================================================================


class Workflow(Base):
    """Workflow-Definitionen fuer Automatisierung.

    Ermoeglicht das Erstellen von Multi-Step-Workflows mit:
    - Trigger (Document Events, Schedule, Condition, Manual, Webhook)
    - Conditions (AND/OR-Logik, wiederverwendet ImportRule Pattern)
    - Actions (20+ Aktionstypen)
    - Branching, Delays, Parallel Execution
    """
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Basis-Informationen
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Template-Funktion
    is_template = Column(Boolean, default=False, nullable=False, index=True)
    template_category = Column(String(50), nullable=True, index=True)
    # Categories: document, finance, notification, reporting, approval

    # Trigger-Konfiguration
    trigger_type = Column(String(30), nullable=False, index=True)
    # Types: document_event, schedule, condition, manual, webhook
    trigger_config = Column(CrossDBJSON, nullable=False, default=dict)

    # ReactFlow Graph Definition
    nodes = Column(CrossDBJSON, nullable=False, default=list)
    edges = Column(CrossDBJSON, nullable=False, default=list)
    variables = Column(CrossDBJSON, nullable=True)

    # Webhook-Trigger
    webhook_secret = Column(String(64), nullable=True)
    webhook_path = Column(String(100), nullable=True, unique=True)

    # Ausfuehrungs-Einstellungen
    max_concurrent_executions = Column(Integer, default=10, nullable=False)
    timeout_seconds = Column(Integer, default=3600, nullable=False)
    retry_config = Column(CrossDBJSON, nullable=True)
    error_handling = Column(String(20), default="stop", nullable=False)
    enable_audit_log = Column(Boolean, default=True, nullable=False)

    # Statistiken
    execution_count = Column(Integer, default=0, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    avg_execution_time_ms = Column(Integer, nullable=True)

    # Naechste geplante Ausfuehrung
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Audit
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="workflows")
    company = relationship("Company", backref="workflows")
    created_by = relationship("User", foreign_keys=[created_by_id])
    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.step_order")
    executions = relationship("WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "Workflow-Definitionen fuer Automatisierung"}
    )


class WorkflowStep(Base):
    """Einzelne Schritte pro Workflow.

    Schritt-Typen:
    - condition: Bedingungspruefung mit AND/OR-Logik
    - action: Aktion ausfuehren (move_folder, send_notification, etc.)
    - branch: If-Then-Else Verzweigung
    - delay: Zeitverzoegerung
    - parallel: Parallele Ausfuehrung
    - loop: Schleife (optional)
    """
    __tablename__ = "workflow_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)

    # Basis-Informationen
    step_order = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Step-Typ
    step_type = Column(String(30), nullable=False, index=True)
    # Types: condition, action, branch, delay, parallel, loop

    # Step-Konfiguration (JSONB)
    config = Column(CrossDBJSON, nullable=False, default=dict)

    # Retry/Error Handling
    retry_on_failure = Column(Boolean, default=True, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)
    retry_backoff_seconds = Column(Integer, default=60, nullable=False)
    continue_on_error = Column(Boolean, default=False, nullable=False)
    fallback_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)

    # ReactFlow Position
    position_x = Column(Float, nullable=True)
    position_y = Column(Float, nullable=True)
    node_data = Column(CrossDBJSON, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    workflow = relationship("Workflow", back_populates="steps")
    fallback_step = relationship("WorkflowStep", remote_side=[id])
    step_executions = relationship("WorkflowStepExecution", back_populates="workflow_step", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_workflow_steps_order", "workflow_id", "step_order"),
        {"comment": "Einzelne Schritte pro Workflow"}
    )


class WorkflowExecution(Base):
    """Ausfuehrungs-Historie fuer Workflows.

    Trackt jeden Workflow-Lauf mit:
    - Trigger-Kontext
    - Status und Fortschritt
    - Ergebnis und Fehler
    - Timing-Informationen
    """
    __tablename__ = "workflow_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True)

    # Wer hat ausgeloest
    triggered_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Trigger-Kontext
    trigger_type = Column(String(30), nullable=False, index=True)
    trigger_source = Column(String(255), nullable=True)
    trigger_data = Column(CrossDBJSON, nullable=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)

    # Ausfuehrungs-Status
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Status: pending, running, completed, failed, cancelled, paused
    current_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)
    progress_percent = Column(Integer, default=0, nullable=False)

    # Ergebnisse
    result = Column(CrossDBJSON, nullable=True)
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="SET NULL"), nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True, index=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Celery-Integration
    celery_task_id = Column(String(100), nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Runtime-Variablen
    variables = Column(CrossDBJSON, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
    company = relationship("Company", backref="workflow_executions")
    triggered_by = relationship("User", foreign_keys=[triggered_by_id])
    document = relationship("Document", backref="workflow_executions")
    current_step = relationship("WorkflowStep", foreign_keys=[current_step_id])
    error_step = relationship("WorkflowStep", foreign_keys=[error_step_id])
    step_executions = relationship("WorkflowStepExecution", back_populates="workflow_execution", cascade="all, delete-orphan", order_by="WorkflowStepExecution.execution_order")

    __table_args__ = (
        {"comment": "Ausfuehrungs-Historie fuer Workflows"}
    )


class WorkflowStepExecution(Base):
    """Schritt-Level Audit Trail fuer Workflow-Ausfuehrungen.

    Trackt jeden einzelnen Schritt mit:
    - Input/Output-Daten
    - Fehler-Details
    - Timing
    - Retry-Informationen
    """
    __tablename__ = "workflow_step_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="CASCADE"), nullable=False, index=True)
    workflow_step_id = Column(UUID(as_uuid=True), ForeignKey("workflow_steps.id", ondelete="CASCADE"), nullable=False, index=True)

    # Ausfuehrungs-Reihenfolge
    execution_order = Column(Integer, nullable=False)

    # Status
    status = Column(String(20), nullable=False, default="pending", index=True)
    # Status: pending, running, completed, failed, skipped

    # Input/Output
    input_data = Column(CrossDBJSON, nullable=True)
    output_data = Column(CrossDBJSON, nullable=True)

    # Fehler-Details
    error_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_details = Column(CrossDBJSON, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Retry-Info
    retry_attempt = Column(Integer, default=0, nullable=False)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)

    # Branch-Entscheidung
    branch_result = Column(Boolean, nullable=True)
    branch_reason = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    workflow_execution = relationship("WorkflowExecution", back_populates="step_executions")
    workflow_step = relationship("WorkflowStep", back_populates="step_executions")

    __table_args__ = (
        Index("ix_workflow_step_execs_order", "workflow_execution_id", "execution_order"),
        {"comment": "Schritt-Level Audit Trail fuer Workflow-Ausfuehrungen"}
    )


# ==================================================
# PWA Push Notification Models
# ==================================================

class PushSubscription(Base):
    """Push Subscription fuer Web Push Notifications.

    Speichert Web Push Subscription Daten pro Geraet/Browser.
    Ermoeglicht Benachrichtigungen auch wenn App nicht geoeffnet ist.
    """

    __tablename__ = "push_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Web Push Subscription data
    endpoint = Column(Text, nullable=False, unique=True, index=True)
    p256dh_key = Column(Text, nullable=False)
    auth_key = Column(Text, nullable=False)
    expiration_time = Column(BigInteger, nullable=True)

    # Device information
    device_name = Column(String(255), nullable=True)
    device_type = Column(String(50), nullable=True, index=True)  # mobile, tablet, desktop
    browser = Column(String(100), nullable=True)
    os = Column(String(100), nullable=True)
    user_agent = Column(Text, nullable=True)

    # Subscription preferences
    preferences = Column(CrossDBJSON, nullable=False, default=dict)

    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="push_subscriptions")
    notification_history = relationship("NotificationHistory", back_populates="subscription", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "Web Push Subscriptions fuer PWA Notifications"}
    )


class NotificationTemplate(Base):
    """Notification Template fuer vordefinierte Benachrichtigungen.

    Ermoeglicht wiederverwendbare Notification-Vorlagen mit Variablen.
    """

    __tablename__ = "notification_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Template identification
    name = Column(String(100), nullable=False, unique=True, index=True)
    category = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Notification content
    title_template = Column(String(255), nullable=False)
    body_template = Column(Text, nullable=False)
    icon = Column(String(255), nullable=True)
    badge = Column(String(255), nullable=True)
    image = Column(String(255), nullable=True)

    # Actions
    actions = Column(CrossDBJSON, nullable=True)

    # Behavior
    tag = Column(String(100), nullable=True)
    require_interaction = Column(Boolean, nullable=False, default=False)
    silent = Column(Boolean, nullable=False, default=False)
    vibrate_pattern = Column(CrossDBJSON, nullable=True)

    # Default preferences
    default_enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(String(20), nullable=False, default="normal")

    # Status
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    notification_history = relationship("NotificationHistory", back_populates="template")

    __table_args__ = (
        {"comment": "Vordefinierte Notification Templates"}
    )


class NotificationHistory(Base):
    """History fuer gesendete Push Notifications.

    Ermoeglicht Tracking von Delivery und Click-Through.
    """

    __tablename__ = "notification_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("push_subscriptions.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("notification_templates.id", ondelete="SET NULL"), nullable=True, index=True)

    # Notification content (snapshot)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    data = Column(CrossDBJSON, nullable=True)

    # Delivery status
    status = Column(String(20), nullable=False, default="pending", index=True)  # pending, sent, delivered, clicked, failed
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    clicked_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    subscription = relationship("PushSubscription", back_populates="notification_history")
    template = relationship("NotificationTemplate", back_populates="notification_history")

    __table_args__ = (
        {"comment": "Tracking fuer gesendete Push Notifications"}
    )


class NotificationRulePriority(str, Enum):
    """Prioritaet einer Notification Rule."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class NotificationRuleActionType(str, Enum):
    """Aktionstyp fuer Notification Rules."""
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"
    WEBHOOK = "webhook"


class NotificationRule(Base):
    """Notification Rules fuer Event-basierte Benachrichtigungen.

    Ermoeglicht benutzerdefinierte Regeln, wann und wie Benachrichtigungen
    ausgeloest werden sollen. Teil des Enterprise Notification Rule Engine.

    Beispiel-Conditions:
    {
        "operator": "AND",
        "conditions": [
            {"field": "amount", "op": "gt", "value": 1000},
            {"field": "category", "op": "eq", "value": "insurance"}
        ]
    }

    Beispiel-Actions:
    {
        "actions": [
            {"type": "in_app", "template_id": "...", "priority": "high"},
            {"type": "push", "title": "...", "body": "..."},
            {"type": "email", "template": "payment_alert"}
        ]
    }
    """

    __tablename__ = "notification_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Rule identification
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)

    # Event matching
    event_type = Column(String(100), nullable=False, index=True,
                        comment="Event-Typ z.B. document.ocr_completed, insurance.deadline_approaching")
    event_source = Column(String(50), nullable=True,
                          comment="Optional: Quelle filtern (z.B. privat, business)")

    # Conditions (JSONB fuer komplexe Filter)
    conditions = Column(CrossDBJSON, nullable=False, default=dict,
                        comment="JSON-Bedingungen mit Operatoren (AND, OR, NOT)")

    # Actions (JSONB fuer mehrere Aktionen)
    actions = Column(CrossDBJSON, nullable=False, default=list,
                     comment="Liste von auszufuehrenden Aktionen")

    # Scheduling
    quiet_hours_start = Column(Time, nullable=True,
                               comment="Start der Ruhezeit (z.B. 22:00)")
    quiet_hours_end = Column(Time, nullable=True,
                             comment="Ende der Ruhezeit (z.B. 08:00)")
    timezone = Column(String(50), nullable=False, default="Europe/Berlin")

    # Rate limiting
    cooldown_minutes = Column(Integer, nullable=True, default=0,
                              comment="Mindestabstand zwischen Benachrichtigungen")
    max_per_day = Column(Integer, nullable=True,
                         comment="Maximale Anzahl pro Tag (NULL = unbegrenzt)")

    # Priority
    priority = Column(String(20), nullable=False, default=NotificationRulePriority.NORMAL.value)

    # Statistics
    trigger_count = Column(Integer, nullable=False, default=0)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    last_matched_event_id = Column(UUID(as_uuid=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="notification_rules")

    __table_args__ = (
        Index("ix_notification_rules_user_enabled", "user_id", "enabled"),
        Index("ix_notification_rules_event_type", "event_type"),
        {"comment": "Benutzerdefinierte Notification-Regeln fuer Events"}
    )

    def __repr__(self) -> str:
        return f"<NotificationRule {self.name} ({self.event_type})>"


# =============================================================================
# ENTERPRISE INTELLIGENCE SYSTEM
# Phase 4: LLM Cache, Event Log, Recurring Payments, Coverage Gaps
# =============================================================================

class RecurringPaymentFrequency(str, Enum):
    """Haeufigkeit wiederkehrender Zahlungen."""
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMIANNUAL = "semiannual"
    YEARLY = "yearly"


class RecurringPaymentCategory(str, Enum):
    """Kategorie wiederkehrender Zahlungen."""
    SUBSCRIPTION = "subscription"
    UTILITY = "utility"
    RENT = "rent"
    INSURANCE = "insurance"
    LOAN = "loan"
    SAVINGS = "savings"
    SALARY = "salary"
    OTHER = "other"


class CoverageGapType(str, Enum):
    """Typ der Versicherungsluecke."""
    MISSING = "missing"
    UNDERCOVERED = "undercovered"
    EXPIRED = "expired"
    OVERLAPPING = "overlapping"


class CoverageGapSeverity(str, Enum):
    """Schweregrad der Versicherungsluecke."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class LLMCache(Base):
    """Semantisches Caching fuer LLM-Antworten.

    Reduziert LLM-Aufrufe durch Wiederverwendung aehnlicher Antworten.
    Nutzt Embedding-basierte Aehnlichkeitssuche.
    """

    __tablename__ = "llm_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_hash = Column(String(64), nullable=False, unique=True, index=True,
                         comment="SHA-256 Hash des normalisierten Prompts")
    prompt_text = Column(Text, nullable=False, comment="Originaler Prompt-Text")
    prompt_embedding = Column(CrossDBJSON, nullable=True,
                              comment="Embedding-Vektor fuer semantische Suche")
    response = Column(Text, nullable=False, comment="LLM-Antwort")
    model = Column(String(50), nullable=False, index=True,
                   comment="Verwendetes Modell")
    model_version = Column(String(50), nullable=True, comment="Modell-Version")
    temperature = Column(Numeric(3, 2), nullable=True, comment="Verwendete Temperature")
    hit_count = Column(Integer, nullable=False, default=0, comment="Anzahl Cache-Hits")
    last_hit_at = Column(DateTime(timezone=True), nullable=True,
                         comment="Zeitpunkt des letzten Hits")
    token_count_prompt = Column(Integer, nullable=True, comment="Token-Anzahl im Prompt")
    token_count_response = Column(Integer, nullable=True,
                                  comment="Token-Anzahl in der Antwort")
    latency_ms = Column(Integer, nullable=True,
                        comment="Original-Antwortzeit in Millisekunden")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True,
                        comment="Ablaufzeitpunkt")
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusaetzliche Metadaten")

    __table_args__ = (
        Index("ix_llm_cache_created_at", "created_at"),
        Index("ix_llm_cache_expires_at", "expires_at"),
        Index("ix_llm_cache_hit_count", "hit_count"),
        {"comment": "Semantisches LLM-Antwort-Caching"}
    )


class EventLog(Base):
    """Event Log fuer Event Bus Historie.

    Persistiert alle Events fuer Audit, Replay und Debugging.
    """

    __tablename__ = "event_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True,
                      comment="Eindeutige Event-ID")
    event_type = Column(String(100), nullable=False, index=True,
                        comment="Event-Typ")
    source = Column(String(100), nullable=False, index=True,
                    comment="Quelle des Events")
    correlation_id = Column(UUID(as_uuid=True), nullable=True,
                            comment="Korrelations-ID")
    user_id = Column(UUID(as_uuid=True), nullable=True,
                     comment="Benutzer-ID")
    space_id = Column(UUID(as_uuid=True), nullable=True,
                      comment="Privat-Space-ID")
    payload = Column(CrossDBJSON, nullable=False, comment="Event-Payload")
    processed = Column(Boolean, nullable=False, default=False,
                       comment="Wurde verarbeitet?")
    processed_at = Column(DateTime(timezone=True), nullable=True,
                          comment="Verarbeitungszeitpunkt")
    handler_count = Column(Integer, nullable=False, default=0,
                           comment="Anzahl Handler")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_event_log_correlation_id", "correlation_id"),
        Index("ix_event_log_user_id", "user_id"),
        Index("ix_event_log_space_id", "space_id"),
        Index("ix_event_log_created_at", "created_at"),
        Index("ix_event_log_unprocessed", "event_type", "created_at",
              postgresql_where=text("processed = false")),
        {"comment": "Event Bus Historie fuer Audit und Replay"}
    )


class PrivatRecurringPayment(Base):
    """Erkannte wiederkehrende Zahlungen.

    Automatisch erkannte oder manuell definierte regelmaessige Zahlungen
    fuer Cashflow-Prognosen und Anomalie-Erkennung.
    """

    __tablename__ = "privat_recurring_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    name = Column(String(255), nullable=False, comment="Name der Zahlung")
    payee = Column(String(255), nullable=True, comment="Zahlungsempfaenger")
    expected_amount = Column(Numeric(10, 2), nullable=False,
                             comment="Erwarteter Betrag")
    amount_variance = Column(Numeric(10, 2), nullable=True,
                             comment="Tolerierte Abweichung")
    frequency = Column(String(20), nullable=False, index=True,
                       comment="Haeufigkeit")
    expected_day = Column(Integer, nullable=True,
                          comment="Erwarteter Tag im Zyklus")
    category = Column(String(50), nullable=True, index=True,
                      comment="Kategorie")
    last_occurrence = Column(Date, nullable=True, comment="Letztes Auftreten")
    next_expected = Column(Date, nullable=True, comment="Naechstes erwartetes Datum")
    occurrence_count = Column(Integer, nullable=False, default=0,
                              comment="Anzahl Vorkommen")
    confidence = Column(Numeric(3, 2), nullable=False, default=0.0,
                        comment="Erkennungs-Konfidenz")
    is_active = Column(Boolean, nullable=False, default=True,
                       comment="Ist aktiv?")
    is_income = Column(Boolean, nullable=False, default=False,
                       comment="Ist Einnahme?")
    linked_account_id = Column(UUID(as_uuid=True), nullable=True,
                               comment="Verknuepftes Bankkonto")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusaetzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="recurring_payments")

    __table_args__ = (
        Index("ix_recurring_payments_next_expected", "next_expected"),
        Index("ix_recurring_payments_confidence", "confidence"),
        {"comment": "Erkannte wiederkehrende Zahlungen"}
    )


class PrivatCoverageGap(Base):
    """Versicherungsluecken-Analyse.

    Identifizierte Deckungsluecken mit Empfehlungen.
    """

    __tablename__ = "privat_coverage_gaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True)
    insurance_id = Column(UUID(as_uuid=True),
                          ForeignKey("privat_insurances.id", ondelete="SET NULL"),
                          nullable=True, comment="Referenz auf Versicherung")
    insurance_type = Column(String(50), nullable=False, index=True,
                            comment="Versicherungstyp")
    gap_type = Column(String(50), nullable=False,
                      comment="Lueckentyp")
    recommended_coverage = Column(Numeric(15, 2), nullable=True,
                                  comment="Empfohlene Deckungssumme")
    current_coverage = Column(Numeric(15, 2), nullable=True,
                              comment="Aktuelle Deckungssumme")
    gap_amount = Column(Numeric(15, 2), nullable=True,
                        comment="Differenz zur Empfehlung")
    severity = Column(String(20), nullable=False, index=True,
                      comment="Schweregrad")
    risk_description = Column(Text, nullable=True,
                              comment="Risikobeschreibung")
    recommendation = Column(Text, nullable=True,
                            comment="Handlungsempfehlung")
    estimated_monthly_cost = Column(Numeric(10, 2), nullable=True,
                                    comment="Geschaetzte Monatskosten")
    priority_score = Column(Integer, nullable=True,
                            comment="Prioritaets-Score 1-100")
    is_resolved = Column(Boolean, nullable=False, default=False,
                         comment="Behoben?")
    resolved_at = Column(DateTime(timezone=True), nullable=True,
                         comment="Behebungszeitpunkt")
    last_analysis_at = Column(DateTime(timezone=True), server_default=func.now(),
                              nullable=False, comment="Letzte Analyse")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusaetzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="coverage_gaps")
    insurance = relationship("PrivatInsurance", back_populates="coverage_gaps")

    __table_args__ = (
        Index("ix_coverage_gaps_unresolved", "space_id", "severity",
              postgresql_where=text("is_resolved = false")),
        Index("ix_coverage_gaps_priority", "priority_score"),
        {"comment": "Versicherungsluecken-Analyse"}
    )


# =============================================================================
# PREDICTIVE INTELLIGENCE: KPI History, Projections, Early Warnings
# =============================================================================


class KPIUnit(str, Enum):
    """Einheit fuer KPIs."""
    PERCENT = "percent"
    CURRENCY = "currency"
    RATIO = "ratio"
    SCORE = "score"
    MONTHS = "months"
    COUNT = "count"
    NUMBER = "number"
    DAYS = "days"
    YEARS = "years"


class ProjectionMethod(str, Enum):
    """Methode fuer KPI-Projektionen."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    SEASONAL = "seasonal"
    ENSEMBLE = "ensemble"


class TrendDirection(str, Enum):
    """Trendrichtung."""
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    VOLATILE = "volatile"


class WarningSeverity(str, Enum):
    """Schweregrad von Early Warnings."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class WarningType(str, Enum):
    """Typ der Early Warning."""
    THRESHOLD_BREACH = "threshold_breach"
    TREND_REVERSAL = "trend_reversal"
    VOLATILITY_SPIKE = "volatility_spike"
    SEASONAL_ANOMALY = "seasonal_anomaly"
    GOAL_AT_RISK = "goal_at_risk"


class ProfessionType(str, Enum):
    """Berufstypen fuer personalisierte Schwellenwerte."""
    EMPLOYEE = "employee"
    CIVIL_SERVANT = "civil_servant"
    FREELANCER = "freelancer"
    ENTREPRENEUR = "entrepreneur"
    RETIREE = "retiree"


class RiskProfile(str, Enum):
    """Risikoprofil des Users."""
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class PrivatKPIHistory(Base):
    """KPI History - Taegliche Snapshots aller KPIs fuer Trend-Analyse.

    Ermoeglicht die Projektion von KPIs in die Zukunft basierend auf
    historischen Trends. Ein Eintrag pro KPI pro Space pro Tag.
    """

    __tablename__ = "privat_kpi_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    kpi_name = Column(String(100), nullable=False, index=True,
                      comment="Name des KPI (z.B. dti, financial_health_score)")
    kpi_value = Column(Numeric(15, 4), nullable=False, comment="Numerischer Wert")
    kpi_unit = Column(String(20), nullable=True,
                      comment="Einheit: percent, currency, ratio, score")
    components = Column(CrossDBJSON, nullable=True,
                        comment="Aufschluesselung in Komponenten")
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False,
                         comment="Zeitpunkt der Aufzeichnung")
    source = Column(String(50), nullable=False, default="automated",
                    comment="Quelle: automated, manual, recalculated")
    extra_data = Column(CrossDBJSON, nullable=True,
                        comment="Zusaetzliche Kontextdaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="kpi_history")

    __table_args__ = (
        Index("ix_kpi_history_space_kpi", "space_id", "kpi_name", "recorded_at"),
        Index("ix_kpi_history_recorded_at", "recorded_at"),
        # Note: UniqueConstraint auf space_id + kpi_name + recorded_at (Tag-Ebene wird in Migration gehandhabt)
        UniqueConstraint("space_id", "kpi_name", "recorded_at",
                         name="uq_kpi_history_space_kpi_date"),
        {"comment": "Taegliche KPI-Snapshots fuer Trend-Analyse"}
    )


class PrivatProjection(Base):
    """KPI Projections Cache - Vorausberechnete Prognosen.

    Gecachte Projektionen fuer 3/6/12 Monate in die Zukunft.
    Werden taeglich neu berechnet und invalidiert.
    """

    __tablename__ = "privat_projections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    kpi_name = Column(String(100), nullable=False, index=True,
                      comment="Name des projizierten KPI")
    projection_months = Column(Integer, nullable=False,
                               comment="Projektionszeitraum in Monaten (3, 6, 12)")
    projection_method = Column(String(50), nullable=False, default=ProjectionMethod.LINEAR.value,
                               comment="Methode: linear, exponential, seasonal, ensemble")
    current_value = Column(Numeric(15, 4), nullable=False,
                           comment="Aktueller Wert zum Berechnungszeitpunkt")
    projected_values = Column(CrossDBJSON, nullable=False,
                              comment="Monatliche Projektionen: [{month, value, confidence}]")
    threshold_breaches = Column(CrossDBJSON, nullable=True,
                                comment="Erkannte zukuenftige Schwellenwertbrueche")
    trend_direction = Column(String(20), nullable=False,
                             comment="Trendrichtung: rising, falling, stable, volatile")
    trend_strength = Column(Numeric(5, 4), nullable=True,
                            comment="Trendstaerke 0-1 (R-squared)")
    seasonality_detected = Column(Boolean, nullable=False, default=False,
                                  comment="Wurde Saisonalitaet erkannt?")
    confidence_overall = Column(Numeric(3, 2), nullable=False,
                                comment="Gesamt-Konfidenz 0-1")
    data_points_used = Column(Integer, nullable=False,
                              comment="Anzahl historischer Datenpunkte")
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False,
                           comment="Zeitpunkt der Berechnung")
    valid_until = Column(DateTime(timezone=True), nullable=False,
                         comment="Gueltig bis")
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusaetzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="projections")
    early_warnings = relationship("PrivatEarlyWarning", back_populates="projection",
                                  cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("space_id", "kpi_name", "projection_months",
                         name="uq_projections_space_kpi_months"),
        Index("ix_projections_valid_until", "valid_until"),
        Index("ix_projections_with_breaches", "space_id",
              postgresql_where=text("threshold_breaches IS NOT NULL")),
        {"comment": "Vorausberechnete KPI-Projektionen"}
    )

    @property
    def is_valid(self) -> bool:
        """Prueft ob Projektion noch gueltig ist."""
        from datetime import datetime, timezone
        return self.valid_until > datetime.now(timezone.utc)


class PrivatEarlyWarning(Base):
    """Early Warnings - Proaktive Warnungen bei zukuenftigen Problemen.

    Speichert erkannte zukuenftige Schwellenwert-Verletzungen mit
    Empfehlungen und Zeitrahmen. Kern des PROAKTIVEN Systems.
    """

    __tablename__ = "privat_early_warnings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    projection_id = Column(UUID(as_uuid=True),
                           ForeignKey("privat_projections.id", ondelete="SET NULL"),
                           nullable=True, comment="Zugrundeliegende Projektion")
    kpi_name = Column(String(100), nullable=False, index=True,
                      comment="Betroffener KPI")
    warning_type = Column(String(50), nullable=False,
                          comment="Typ: threshold_breach, trend_reversal, etc.")
    severity = Column(String(20), nullable=False, index=True,
                      comment="Schweregrad: info, warning, critical")
    current_value = Column(Numeric(15, 4), nullable=False,
                           comment="Aktueller Wert")
    projected_value = Column(Numeric(15, 4), nullable=False,
                             comment="Projizierter Wert zum Breach-Zeitpunkt")
    threshold_value = Column(Numeric(15, 4), nullable=True,
                             comment="Schwellenwert der ueberschritten wird")
    threshold_name = Column(String(100), nullable=True,
                            comment="Name des Schwellenwerts")
    breach_date = Column(Date, nullable=False, index=True,
                         comment="Prognostiziertes Datum der Verletzung")
    days_until_breach = Column(Integer, nullable=False,
                               comment="Tage bis zur Verletzung")
    title = Column(String(255), nullable=False,
                   comment="Titel der Warnung (deutsch)")
    description = Column(Text, nullable=True,
                         comment="Detaillierte Beschreibung")
    recommendation = Column(Text, nullable=True,
                            comment="Handlungsempfehlung")
    potential_impact = Column(Numeric(15, 2), nullable=True,
                              comment="Geschaetzter finanzieller Impact")
    action_url = Column(String(255), nullable=True,
                        comment="Link zur entsprechenden Aktion")
    confidence = Column(Numeric(3, 2), nullable=False,
                        comment="Konfidenz der Warnung 0-1")
    is_dismissed = Column(Boolean, nullable=False, default=False,
                          comment="Wurde die Warnung verworfen?")
    dismissed_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_reason = Column(Text, nullable=True)
    is_resolved = Column(Boolean, nullable=False, default=False,
                         comment="Wurde das Problem behoben?")
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True,
                        comment="Warnung verfaellt")
    extra_data = Column(CrossDBJSON, nullable=True, comment="Zusaetzliche Metadaten")

    # Relationships
    space = relationship("PrivatSpace", back_populates="early_warnings")
    projection = relationship("PrivatProjection", back_populates="early_warnings")

    __table_args__ = (
        Index("ix_early_warnings_active", "space_id", "severity", "breach_date",
              postgresql_where=text("is_dismissed = false AND is_resolved = false")),
        Index("ix_early_warnings_days_until", "days_until_breach",
              postgresql_where=text("is_dismissed = false AND is_resolved = false")),
        {"comment": "Proaktive Warnungen bei zukuenftigen Problemen"}
    )

    @property
    def is_active(self) -> bool:
        """Prueft ob die Warnung aktiv ist."""
        return not self.is_dismissed and not self.is_resolved


class PrivatTask(Base):
    """Orchestrator-Tasks - Aufgaben aus der Cross-Module-Orchestrierung.

    Generische Tasks die vom CrossModuleOrchestrator erstellt werden,
    wenn automatische Aktionen Benutzereingriff erfordern oder
    manuelle Follow-Ups notwendig sind.
    """

    __tablename__ = "privat_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"),
                      nullable=False, index=True, comment="Referenz auf privat_spaces")
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True, comment="Zugewiesener Benutzer")

    # Task-Identifikation
    task_type = Column(String(50), nullable=False, index=True,
                       comment="Typ: review, action, follow_up, reminder, approval")
    title = Column(String(255), nullable=False,
                   comment="Kurzer Titel der Aufgabe")
    description = Column(Text, nullable=True,
                         comment="Ausfuehrliche Beschreibung")
    category = Column(String(50), nullable=True, index=True,
                      comment="Kategorie: financial, insurance, property, loan, general")

    # Prioritaet und Dringlichkeit
    priority = Column(String(20), nullable=False, default="medium",
                      comment="Prioritaet: low, medium, high, critical")
    due_date = Column(DateTime(timezone=True), nullable=True,
                      comment="Faelligkeitsdatum")

    # Herkunft aus Orchestration
    source_action_id = Column(UUID(as_uuid=True), nullable=True,
                              comment="ID der ausloesenden OrchestrationAction")
    source_reason = Column(Text, nullable=True,
                           comment="Grund fuer Task-Erstellung")
    source_module = Column(String(50), nullable=True,
                           comment="Ausloesendes Modul: financial_health, insurance, loan, etc.")

    # Status-Tracking
    status = Column(String(30), nullable=False, default="pending",
                    comment="Status: pending, in_progress, completed, cancelled, snoozed")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_reason = Column(Text, nullable=True)

    # Snooze-Funktion (wie bei MahnTask)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)
    snooze_count = Column(Integer, default=0)
    snooze_reason = Column(String(255), nullable=True)

    # Ergebnis
    result_notes = Column(Text, nullable=True,
                          comment="Notizen nach Abschluss")
    result_action_taken = Column(String(100), nullable=True,
                                 comment="Getroffene Massnahme")

    # Verknuepfte Entitaeten
    related_entity_type = Column(String(50), nullable=True,
                                 comment="Typ der verknuepften Entitaet: property, loan, insurance")
    related_entity_id = Column(UUID(as_uuid=True), nullable=True,
                               comment="ID der verknuepften Entitaet")

    # Metadaten
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    extra_data = Column(CrossDBJSON, nullable=True,
                        comment="Zusaetzliche Metadaten vom Orchestrator")

    # Relationships
    space = relationship("PrivatSpace", back_populates="tasks")
    user = relationship("User", backref="privat_tasks")

    __table_args__ = (
        Index("ix_privat_tasks_pending", "user_id", "status", "priority",
              postgresql_where=text("status IN ('pending', 'in_progress')")),
        Index("ix_privat_tasks_due", "due_date",
              postgresql_where=text("status = 'pending'")),
        Index("ix_privat_tasks_source", "source_action_id"),
        CheckConstraint("status IN ('pending', 'in_progress', 'completed', 'cancelled', 'snoozed')",
                        name="chk_privat_task_status"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')",
                        name="chk_privat_task_priority"),
        {"comment": "Orchestrator-generierte Tasks fuer Benutzeraktionen"}
    )

    @property
    def is_overdue(self) -> bool:
        """Prueft ob Task ueberfaellig ist."""
        from datetime import datetime, timezone
        if self.due_date and self.status in ("pending", "in_progress"):
            return self.due_date < datetime.now(timezone.utc)
        return False

    @property
    def is_snoozed(self) -> bool:
        """Prueft ob Task zur Zeit snoozt."""
        from datetime import datetime, timezone
        if self.snoozed_until and self.status == "snoozed":
            return self.snoozed_until > datetime.now(timezone.utc)
        return False


# =============================================================================
# PORTFOLIO SNAPSHOT MODEL (Enterprise Feature)
# =============================================================================

class PortfolioSnapshot(Base):
    """Monatlicher Snapshot der Vermoegensuebersicht.

    Speichert aggregierte Vermoegensstaende zu bestimmten Zeitpunkten
    fuer historische Analyse und Reporting.
    """
    __tablename__ = "portfolio_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)
    snapshot_date = Column(Date, nullable=False, index=True, comment="Datum des Snapshots")

    # Vermoegenswerte (Assets)
    total_real_estate = Column(Numeric(14, 2), nullable=False, default=0,
                               comment="Gesamtwert Immobilien")
    total_vehicles = Column(Numeric(14, 2), nullable=False, default=0,
                            comment="Gesamtwert Fahrzeuge")
    total_investments = Column(Numeric(14, 2), nullable=False, default=0,
                               comment="Gesamtwert Investments (Aktien, ETFs, Fonds)")
    total_cash = Column(Numeric(14, 2), nullable=False, default=0,
                        comment="Barvermoegen und Bankguthaben")
    total_other_assets = Column(Numeric(14, 2), nullable=False, default=0,
                                comment="Sonstige Vermoegenswerte")

    # Verbindlichkeiten (Liabilities)
    total_mortgages = Column(Numeric(14, 2), nullable=False, default=0,
                             comment="Hypotheken und Immobilienkredite")
    total_loans = Column(Numeric(14, 2), nullable=False, default=0,
                         comment="Sonstige Kredite (Auto, Konsum)")
    total_other_liabilities = Column(Numeric(14, 2), nullable=False, default=0,
                                     comment="Sonstige Verbindlichkeiten")

    # Aggregierte Werte
    total_assets = Column(Numeric(14, 2), nullable=False, default=0,
                          comment="Summe aller Vermoegenswerte")
    total_liabilities = Column(Numeric(14, 2), nullable=False, default=0,
                               comment="Summe aller Verbindlichkeiten")
    net_worth = Column(Numeric(14, 2), nullable=False, default=0,
                       comment="Nettovermoegen (Assets - Liabilities)")

    # Veraenderungen zum Vormonat
    net_worth_change_absolute = Column(Numeric(14, 2), nullable=True,
                                       comment="Absolute Aenderung zum Vormonat in EUR")
    net_worth_change_percent = Column(Numeric(8, 4), nullable=True,
                                      comment="Prozentuale Aenderung zum Vormonat")

    # Kennzahlen
    debt_to_assets_ratio = Column(Numeric(8, 4), nullable=False, default=0,
                                  comment="Verschuldungsgrad (Liabilities/Assets)")
    liquidity_ratio = Column(Numeric(8, 4), nullable=False, default=0,
                             comment="Liquiditaetsquote (Cash/Liabilities)")

    # Asset Allocation als JSON
    asset_allocation = Column(CrossDBJSON, nullable=True,
                              comment="Vermoegensverteilung als JSON (z.B. {'real_estate': 45, 'investments': 30, ...})")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    space = relationship("PrivatSpace", back_populates="portfolio_snapshots")

    __table_args__ = (
        Index("ix_portfolio_snapshots_space_date", "space_id", "snapshot_date"),
        UniqueConstraint("space_id", "snapshot_date", name="uq_portfolio_snapshot_space_date"),
        {"comment": "Monatliche Vermoegenssnapshots fuer historische Analyse"}
    )

    @property
    def total_equity(self) -> float:
        """Eigenkapitalquote berechnen."""
        if self.total_assets and self.total_assets > 0:
            return float(self.net_worth / self.total_assets)
        return 0.0


# =============================================================================
# FINANCIAL GOAL MODEL (Enterprise Feature)
# =============================================================================

class FinancialGoalType(str, Enum):
    """Typ der finanziellen Ziele."""
    RETIREMENT = "retirement"           # Altersvorsorge
    EDUCATION = "education"             # Ausbildung/Studium
    PROPERTY_PURCHASE = "property"      # Immobilienkauf
    DEBT_FREE = "debt_free"             # Schuldenfreiheit
    EMERGENCY_FUND = "emergency_fund"   # Notgroschen
    TRAVEL = "travel"                   # Reisen
    VEHICLE = "vehicle"                 # Fahrzeugkauf
    RENOVATION = "renovation"           # Renovierung
    INVESTMENT = "investment"           # Investment-Ziel
    CUSTOM = "custom"                   # Benutzerdefiniert


class FinancialGoalStatus(str, Enum):
    """Status der finanziellen Ziele."""
    ACTIVE = "active"           # Aktiv - wird verfolgt
    PAUSED = "paused"           # Pausiert
    COMPLETED = "completed"     # Erreicht
    CANCELLED = "cancelled"     # Abgebrochen


class FinancialGoal(Base):
    """Finanzielle Ziele mit Progress-Tracking.

    Ermoeglicht das Setzen von Sparzielen mit automatischer
    Fortschrittsverfolgung und Prognosen.
    """
    __tablename__ = "financial_goals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(UUID(as_uuid=True), ForeignKey("privat_spaces.id", ondelete="CASCADE"), nullable=False)

    # Ziel-Definition
    name = Column(String(200), nullable=False, comment="Name des Ziels")
    description = Column(Text, nullable=True, comment="Beschreibung")
    goal_type = Column(String(50), nullable=False, default=FinancialGoalType.CUSTOM.value,
                       comment="Typ des Ziels")
    icon = Column(String(50), nullable=True, default="Target", comment="Icon fuer UI")
    color = Column(String(7), nullable=True, default="#10B981", comment="Farbe fuer UI")

    # Zielwerte
    target_value = Column(Numeric(14, 2), nullable=False, comment="Zielbetrag in EUR")
    target_date = Column(Date, nullable=False, comment="Zieldatum")

    # Tracking
    current_value = Column(Numeric(14, 2), nullable=False, default=0,
                           comment="Aktueller Betrag")
    progress_percent = Column(Numeric(8, 4), nullable=False, default=0,
                              comment="Fortschritt in Prozent (0-100)")

    # Berechnete/Prognostizierte Werte
    monthly_savings_required = Column(Numeric(12, 2), nullable=True,
                                      comment="Erforderliche monatliche Sparrate")
    months_remaining = Column(Integer, nullable=True,
                              comment="Verbleibende Monate bis Zieldatum")
    is_on_track = Column(Boolean, nullable=False, default=True,
                         comment="Liegt das Ziel im Plan?")
    projected_completion_date = Column(Date, nullable=True,
                                       comment="Prognostiziertes Erreichen basierend auf aktuellem Tempo")

    # Verknuepfte Assets (optional)
    linked_assets = Column(CrossDBJSON, nullable=True,
                           comment="Verknuepfte Assets als JSON (z.B. [{'type': 'investment', 'id': '...'}])")

    # Status und Prioritaet
    status = Column(String(20), nullable=False, default=FinancialGoalStatus.ACTIVE.value)
    priority = Column(Integer, nullable=False, default=1, comment="Prioritaet (1=hoechste)")

    # Automatische Aktualisierung
    auto_update_enabled = Column(Boolean, nullable=False, default=True,
                                 comment="Automatische Fortschrittsaktualisierung?")
    last_auto_update = Column(DateTime(timezone=True), nullable=True,
                              comment="Letzte automatische Aktualisierung")

    # Benachrichtigungen
    notify_on_milestone = Column(Boolean, nullable=False, default=True,
                                 comment="Benachrichtigung bei Meilensteinen?")
    notify_on_delay = Column(Boolean, nullable=False, default=True,
                             comment="Benachrichtigung bei Verzoegerung?")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="Zeitpunkt der Zielerreichung")

    # Relationships
    space = relationship("PrivatSpace", back_populates="financial_goals")
    contributions = relationship("FinancialGoalContribution", back_populates="goal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_financial_goals_space", "space_id"),
        Index("ix_financial_goals_status", "status"),
        Index("ix_financial_goals_target_date", "target_date"),
        Index("ix_financial_goals_on_track", "is_on_track",
              postgresql_where=text("status = 'active'")),
        {"comment": "Finanzielle Ziele mit Progress-Tracking"}
    )

    @property
    def is_completed(self) -> bool:
        """Prueft ob Ziel erreicht wurde."""
        return self.status == FinancialGoalStatus.COMPLETED.value or \
               (self.current_value >= self.target_value if self.target_value else False)

    @property
    def is_overdue(self) -> bool:
        """Prueft ob Zieldatum ueberschritten."""
        from datetime import date
        return date.today() > self.target_date and not self.is_completed

    @property
    def remaining_amount(self) -> float:
        """Verbleibender Betrag bis zum Ziel."""
        return float(max(self.target_value - self.current_value, 0))


class FinancialGoalContribution(Base):
    """Beitraege/Einzahlungen zu einem Finanzziel.

    Trackt individuelle Beitraege zum Fortschritt eines Ziels.
    """
    __tablename__ = "financial_goal_contributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_id = Column(UUID(as_uuid=True), ForeignKey("financial_goals.id", ondelete="CASCADE"), nullable=False)

    # Beitrag
    amount = Column(Numeric(14, 2), nullable=False, comment="Beitragsbetrag in EUR")
    contribution_date = Column(Date, nullable=False, server_default=func.current_date(),
                               comment="Datum des Beitrags")

    # Quelle
    source_type = Column(String(50), nullable=True, comment="Quelle (manual, automatic, transfer)")
    source_description = Column(String(255), nullable=True, comment="Beschreibung der Quelle")

    # Verknuepfte Transaktion (optional)
    linked_transaction_id = Column(UUID(as_uuid=True), nullable=True,
                                   comment="Verknuepfte Transaktion falls automatisch")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Notes
    note = Column(Text, nullable=True, comment="Optionale Notiz")

    # Relationships
    goal = relationship("FinancialGoal", back_populates="contributions")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_goal_contributions_goal", "goal_id"),
        Index("ix_goal_contributions_date", "contribution_date"),
        {"comment": "Beitraege zu finanziellen Zielen"}
    )


# =============================================================================
# Approval System - Enterprise Genehmigungssystem
# =============================================================================

class ApprovalRuleType(str, Enum):
    """Typen von Approval-Regeln."""
    AMOUNT_THRESHOLD = "amount_threshold"  # Betragsschwelle
    CATEGORY = "category"  # Nach Kategorie
    SUPPLIER = "supplier"  # Nach Lieferant
    COST_CENTER = "cost_center"  # Nach Kostenstelle
    DOCUMENT_TYPE = "document_type"  # Nach Dokumenttyp
    RISK_LEVEL = "risk_level"  # Nach Risikostufe
    CUSTOM = "custom"  # Benutzerdefiniert


class ApprovalStatus(str, Enum):
    """Status einer Genehmigungsanfrage."""
    PENDING = "pending"  # Ausstehend
    APPROVED = "approved"  # Genehmigt
    REJECTED = "rejected"  # Abgelehnt
    ESCALATED = "escalated"  # Eskaliert
    EXPIRED = "expired"  # Abgelaufen
    CANCELLED = "cancelled"  # Storniert


class ApprovalPriority(str, Enum):
    """Prioritaet einer Genehmigung."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ApprovalRule(Base):
    """Regeln fuer automatisches Approval-Routing.

    Enterprise Feature: Definiert wann und wer genehmigen muss basierend auf:
    - Betragsschwellen
    - Kategorien/Kostenstellon
    - Lieferanten
    - Risikostufen
    """
    __tablename__ = "approval_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Regel-Definition
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    rule_type = Column(SQLAlchemyEnum(ApprovalRuleType), nullable=False, index=True)

    # Entitaets-Typen, auf die Regel angewendet wird
    entity_types = Column(CrossDBJSON, nullable=False, default=list)
    # z.B.: ["invoice", "expense", "purchase_order", "document"]

    # Bedingungen (JSON)
    conditions = Column(CrossDBJSON, nullable=False, default=dict)
    # Beispiele:
    # {"amount_greater_than": 5000, "amount_less_than": 50000}
    # {"category_in": ["IT", "Marketing"]}
    # {"supplier_risk_level": "high"}
    # {"cost_center_id": "uuid..."}

    # Genehmiger-Chain (JSON Array)
    approval_chain = Column(CrossDBJSON, nullable=False, default=list)
    # Beispiel: [
    #   {"step": 1, "type": "role", "value": "manager", "required": true},
    #   {"step": 2, "type": "user", "value": "uuid...", "required": true},
    #   {"step": 3, "type": "role", "value": "cfo", "required": false, "threshold": 10000}
    # ]

    # Eskalation
    escalation_after_hours = Column(Integer, nullable=True)
    escalation_to_role = Column(String(50), nullable=True)

    # SLA
    sla_hours = Column(Integer, nullable=True, default=48)  # Max. Bearbeitungszeit

    # Prioritaet und Reihenfolge
    priority = Column(Integer, default=100, nullable=False)  # Niedrig = Hoehere Prioritaet
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", backref="approval_rules")
    created_by = relationship("User", foreign_keys=[created_by_id])
    approval_requests = relationship("ApprovalRequest", back_populates="triggered_by_rule")

    __table_args__ = (
        Index("ix_approval_rules_company_active", "company_id", "is_active"),
        Index("ix_approval_rules_priority", "priority"),
        {"comment": "Regeln fuer automatisches Approval-Routing"}
    )


class ApprovalRequest(Base):
    """Genehmigungsanfrage mit Multi-Step Approval Chain.

    Enterprise Feature: Trackt den kompletten Genehmigungsprozess mit:
    - Multi-Level Genehmigungen
    - Eskalation bei Zeitüberschreitung
    - Vollstaendiger Audit Trail
    - Integration mit Workflows
    """
    __tablename__ = "approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Entitaet, die genehmigt werden soll
    entity_type = Column(String(50), nullable=False, index=True)
    # z.B.: "invoice", "expense", "document", "purchase_order", "contract"
    entity_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Optionale Workflow-Verknuepfung
    workflow_execution_id = Column(UUID(as_uuid=True), ForeignKey("workflow_executions.id", ondelete="SET NULL"), nullable=True)

    # Regel, die diese Anfrage ausgeloest hat
    triggered_by_rule_id = Column(UUID(as_uuid=True), ForeignKey("approval_rules.id", ondelete="SET NULL"), nullable=True)

    # Anfrage-Details
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(14, 2), nullable=True)  # Betrag falls relevant
    currency = Column(String(3), default="EUR", nullable=False)

    # Status
    status = Column(SQLAlchemyEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False, index=True)
    priority = Column(SQLAlchemyEnum(ApprovalPriority), default=ApprovalPriority.NORMAL, nullable=False, index=True)

    # Approval Chain Fortschritt
    current_step = Column(Integer, default=1, nullable=False)
    total_steps = Column(Integer, nullable=False)
    approval_chain = Column(CrossDBJSON, nullable=False, default=list)
    # Kopie der Chain zum Zeitpunkt der Erstellung

    # SLA und Timing
    due_date = Column(DateTime(timezone=True), nullable=True, index=True)
    escalation_date = Column(DateTime(timezone=True), nullable=True)
    is_escalated = Column(Boolean, default=False, nullable=False)

    # Ergebnis
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Wer hat die Anfrage erstellt
    requested_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Zusaetzliche Daten
    request_metadata = Column(CrossDBJSON, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    company = relationship("Company", backref="approval_requests")
    workflow_execution = relationship("WorkflowExecution", backref="approval_requests")
    triggered_by_rule = relationship("ApprovalRule", back_populates="approval_requests")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    approval_steps = relationship("ApprovalStep", back_populates="approval_request", cascade="all, delete-orphan", order_by="ApprovalStep.step_number")

    __table_args__ = (
        Index("ix_approval_requests_entity", "entity_type", "entity_id"),
        Index("ix_approval_requests_status", "company_id", "status"),
        Index("ix_approval_requests_due", "due_date"),
        {"comment": "Genehmigungsanfragen mit Multi-Step Chain"}
    )


class ApprovalStep(Base):
    """Einzelner Schritt im Genehmigungsprozess.

    Trackt jeden Genehmiger und seine Entscheidung.
    """
    __tablename__ = "approval_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_request_id = Column(UUID(as_uuid=True), ForeignKey("approval_requests.id", ondelete="CASCADE"), nullable=False, index=True)

    # Schritt-Nummer
    step_number = Column(Integer, nullable=False)

    # Genehmiger
    approver_type = Column(String(20), nullable=False)  # "user", "role", "group"
    approver_value = Column(String(255), nullable=False)  # User-ID, Rollenname, etc.
    assigned_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Status dieses Schritts
    status = Column(SQLAlchemyEnum(ApprovalStatus), default=ApprovalStatus.PENDING, nullable=False, index=True)
    is_required = Column(Boolean, default=True, nullable=False)

    # Entscheidung
    decision = Column(String(20), nullable=True)  # "approved", "rejected"
    decision_date = Column(DateTime(timezone=True), nullable=True)
    decision_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decision_notes = Column(Text, nullable=True)

    # Delegation
    delegated_to_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    delegated_at = Column(DateTime(timezone=True), nullable=True)
    delegation_reason = Column(Text, nullable=True)

    # Erinnerungen
    reminder_sent_count = Column(Integer, default=0, nullable=False)
    last_reminder_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    approval_request = relationship("ApprovalRequest", back_populates="approval_steps")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    decision_by = relationship("User", foreign_keys=[decision_by_id])
    delegated_to = relationship("User", foreign_keys=[delegated_to_id])

    __table_args__ = (
        Index("ix_approval_steps_request_number", "approval_request_id", "step_number"),
        Index("ix_approval_steps_assigned", "assigned_user_id", "status"),
        {"comment": "Einzelne Schritte im Genehmigungsprozess"}
    )


class ApprovalDelegation(Base):
    """Genehmigungsdelegation / Stellvertretung.

    Ermoeglicht es Benutzern, ihre Genehmigungsrechte
    temporaer an Stellvertreter zu delegieren.
    """
    __tablename__ = "approval_delegations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)

    # Delegierender Benutzer
    delegator_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Stellvertreter
    delegate_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Zeitraum
    start_date = Column(DateTime(timezone=True), nullable=True)
    end_date = Column(DateTime(timezone=True), nullable=True)

    # Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    reason = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    delegator = relationship("User", foreign_keys=[delegator_user_id])
    delegate = relationship("User", foreign_keys=[delegate_user_id])
    company = relationship("Company", backref="approval_delegations")

    __table_args__ = (
        Index("ix_approval_delegations_delegator_active", "delegator_user_id", "is_active"),
        {"comment": "Genehmigungsdelegation / Stellvertretung"}
    )


# =============================================================================
# Privat-Modul: Personalized Thresholds (Phase 0 Critical Fix)
# =============================================================================

class PrivatUserProfile(Base):
    """User-Profil fuer personalisierte Schwellenwert-Berechnung.

    Speichert Berufsprofil, Risikotoleranz und Praeferenzen
    fuer die automatische Anpassung von Schwellenwerten.
    """
    __tablename__ = "privat_user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    # Profession and Risk
    profession_type = Column(String(50), nullable=False, default="employee")
    risk_tolerance = Column(String(50), nullable=False, default="moderate")
    income_stability = Column(Numeric(3, 2), nullable=False, default=0.7)  # 0-1

    # Demographics
    age_group = Column(String(20), nullable=True)  # "18-30", "31-45", etc.
    household_size = Column(Integer, nullable=False, default=2)

    # Financial Situation
    has_dependents = Column(Boolean, nullable=False, default=False)
    is_homeowner = Column(Boolean, nullable=False, default=False)
    has_pension_plan = Column(Boolean, nullable=False, default=True)

    # Preferences
    prefers_aggressive_alerts = Column(Boolean, nullable=False, default=False)
    prefers_conservative_targets = Column(Boolean, nullable=False, default=True)

    # Learning data
    feedback_history = Column(CrossDBJSON, nullable=True, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref=backref("privat_profile", uselist=False))
    thresholds = relationship("PrivatUserThreshold", back_populates="profile", cascade="all, delete-orphan")

    __table_args__ = (
        {"comment": "User-Profile fuer personalisierte Schwellenwerte (Privat-Modul)"}
    )


class PrivatUserThreshold(Base):
    """Personalisierter Schwellenwert fuer einen User.

    Speichert sowohl Default- als auch aktuellen Wert,
    sowie Tracking-Daten fuer Effektivitaetsmessung.
    """
    __tablename__ = "privat_user_thresholds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id = Column(UUID(as_uuid=True), ForeignKey("privat_user_profiles.id", ondelete="CASCADE"), nullable=True, index=True)

    # Threshold identification
    threshold_type = Column(String(50), nullable=False)  # e.g., "dti_warning", "emergency_fund_min"

    # Values
    default_value = Column(Numeric(10, 4), nullable=False)
    current_value = Column(Numeric(10, 4), nullable=False)

    # Adjustment tracking
    adjustment_source = Column(String(50), nullable=False)  # system_default, user_preference, learned_behavior
    adjustment_reason = Column(Text, nullable=True)

    # Confidence and Effectiveness
    confidence = Column(Numeric(3, 2), nullable=False, default=0.7)  # 0-1
    times_triggered = Column(Integer, nullable=False, default=0)
    times_acted_on = Column(Integer, nullable=False, default=0)
    effectiveness_score = Column(Numeric(3, 2), nullable=False, default=1.0)  # 0-1

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    profile = relationship("PrivatUserProfile", back_populates="thresholds")

    __table_args__ = (
        UniqueConstraint("user_id", "threshold_type", name="uq_user_threshold_type"),
        Index("ix_user_thresholds_type", "threshold_type"),
        Index("ix_user_thresholds_user_type", "user_id", "threshold_type"),
        {"comment": "Personalisierte Schwellenwerte pro User (Privat-Modul)"}
    )


class PrivatThresholdAdjustment(Base):
    """Audit-Log fuer Schwellenwert-Anpassungen.

    Trackt alle Aenderungen an Schwellenwerten mit Rollback-Support.
    """
    __tablename__ = "privat_threshold_adjustments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    threshold_type = Column(String(50), nullable=False, index=True)

    # Values
    previous_value = Column(Numeric(10, 4), nullable=False)
    new_value = Column(Numeric(10, 4), nullable=False)

    # Adjustment details
    adjustment_source = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    confidence = Column(Numeric(3, 2), nullable=False, default=0.7)

    # Rollback support
    can_rollback = Column(Boolean, nullable=False, default=True)
    rolled_back = Column(Boolean, nullable=False, default=False)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
    rolled_back_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamp
    applied_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    __table_args__ = (
        Index("ix_threshold_adjustments_user_type", "user_id", "threshold_type"),
        {"comment": "Audit-Log fuer Schwellenwert-Aenderungen (Privat-Modul)"}
    )


class PrivatThresholdRecommendation(Base):
    """AI-generierte Empfehlung fuer Schwellenwert-Anpassung.

    Empfehlungen haben ein Ablaufdatum und koennen akzeptiert
    oder abgelehnt werden.
    """
    __tablename__ = "privat_threshold_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    threshold_type = Column(String(50), nullable=False)

    # Values
    current_value = Column(Numeric(10, 4), nullable=False)
    recommended_value = Column(Numeric(10, 4), nullable=False)

    # Recommendation details
    reason = Column(Text, nullable=False)
    confidence = Column(Numeric(3, 2), nullable=False, default=0.7)
    potential_impact = Column(Text, nullable=True)

    # Status
    accepted = Column(Boolean, nullable=True)  # null = pending
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Validity
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_threshold_recommendations_pending", "user_id", "accepted", postgresql_where=text("accepted IS NULL")),
        {"comment": "AI-Empfehlungen fuer Schwellenwert-Anpassungen (Privat-Modul)"}
    )


# =============================================================================
# Document Template Models
# =============================================================================

class TemplateCategory(str, Enum):
    """Kategorien fuer Dokumentvorlagen."""
    INVOICE = "invoice"
    OFFER = "offer"
    CONTRACT = "contract"
    LETTER = "letter"
    REMINDER = "reminder"
    DUNNING = "dunning"
    CONFIRMATION = "confirmation"
    REPORT = "report"
    CERTIFICATE = "certificate"
    OTHER = "other"


class TemplateOutputFormat(str, Enum):
    """Ausgabeformate fuer generierte Dokumente."""
    PDF = "pdf"
    DOCX = "docx"
    HTML = "html"
    MARKDOWN = "markdown"


class VariableType(str, Enum):
    """Typen fuer Template-Variablen."""
    TEXT = "text"
    NUMBER = "number"
    CURRENCY = "currency"
    DATE = "date"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    SELECT = "select"
    ENTITY = "entity"  # Referenz auf BusinessEntity
    DOCUMENT = "document"  # Referenz auf anderes Dokument


class DocumentTemplate(Base):
    """
    Dokumentvorlage mit Platzhaltern und Metadaten.

    Unterstuetzt:
    - Jinja2-Syntax fuer Platzhalter: {{ variable_name }}
    - Bedingte Bloecke: {% if condition %}...{% endif %}
    - Schleifen: {% for item in items %}...{% endfor %}
    """
    __tablename__ = "document_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Identifikation
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False)  # Kurzcode wie "INV-STANDARD"
    description = Column(Text, nullable=True)
    category = Column(SQLAlchemyEnum(TemplateCategory, name="templatecategory"), default=TemplateCategory.OTHER)

    # Vorlage
    content = Column(Text, nullable=False)  # Jinja2 Template
    header_content = Column(Text, nullable=True)  # Optional header
    footer_content = Column(Text, nullable=True)  # Optional footer

    # Styling
    css_styles = Column(Text, nullable=True)
    page_size = Column(String(20), default="A4")  # A4, Letter, etc.
    orientation = Column(String(20), default="portrait")  # portrait, landscape
    margins = Column(CrossDBJSON, default=lambda: {"top": 20, "right": 15, "bottom": 20, "left": 15})  # mm

    # Ausgabeformat
    output_format = Column(SQLAlchemyEnum(TemplateOutputFormat, name="templateoutputformat"), default=TemplateOutputFormat.PDF)

    # Variablen-Definition (Schema)
    variables = Column(CrossDBJSON, default=list, comment="Schema der Template-Variablen")
    # Format: [{"name": "kunde", "type": "entity", "label": "Kunde", "required": true, "default": null, "options": [...]}]

    # Versionierung
    version = Column(Integer, default=1)
    is_latest = Column(Boolean, default=True)
    parent_template_id = Column(UUID(as_uuid=True), ForeignKey("document_templates.id"), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)  # Default fuer Kategorie

    # Nutzungsstatistik
    usage_count = Column(Integer, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Metadaten
    tags = Column(CrossDBJSON, default=list)
    template_metadata = Column(CrossDBJSON, default=dict)  # 'metadata' is SQLAlchemy reserved

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    company = relationship("Company", back_populates="document_templates")
    created_by = relationship("User", foreign_keys=[created_by_id])
    parent_template = relationship(
        "DocumentTemplate",
        remote_side=[id],
        backref=backref("child_versions", lazy="dynamic"),
    )
    generated_documents = relationship("GeneratedDocument", back_populates="template", lazy="dynamic")

    __table_args__ = (
        UniqueConstraint("company_id", "code", "version", name="uq_template_code_version"),
        Index("ix_template_company", "company_id"),
        Index("ix_template_category", "category"),
        Index("ix_template_code", "code"),
        Index("ix_template_is_active", "is_active"),
        Index("ix_template_is_default", "is_default"),
        {"comment": "Dokumentvorlagen mit Jinja2-Syntax (Vorlagen-System)"}
    )

    def __repr__(self) -> str:
        return f"<DocumentTemplate {self.code} v{self.version}>"


class GeneratedDocument(Base):
    """
    Generiertes Dokument aus einer Vorlage.

    Speichert:
    - Die verwendeten Variablen-Werte
    - Referenz zur Vorlage
    - Generiertes Dokument (als Datei oder in Storage)
    """
    __tablename__ = "generated_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("document_templates.id"), nullable=False, index=True)

    # Generierte Datei
    title = Column(String(500), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(500), nullable=True)  # MinIO path
    file_size = Column(Integer, nullable=True)

    # Verwendete Werte
    variable_values = Column(CrossDBJSON, default=dict, comment="Verwendete Variablen-Werte bei Generierung")
    # Format: {"kunde": {"id": "...", "name": "..."}, "datum": "2026-01-17", "betrag": 1500.00}

    # Template-Version zum Zeitpunkt der Generierung
    template_version = Column(Integer, nullable=False)
    template_snapshot = Column(CrossDBJSON, nullable=True, comment="Snapshot des Templates bei Generierung (optional)")

    # Referenzen
    linked_entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True, index=True)
    linked_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True, index=True)

    # Status
    is_finalized = Column(Boolean, default=False)  # Unveraenderbar
    is_sent = Column(Boolean, default=False)  # Per Email versendet
    sent_at = Column(DateTime(timezone=True), nullable=True)
    sent_to = Column(CrossDBJSON, default=list)  # Email-Adressen

    # Metadaten
    gen_doc_metadata = Column(CrossDBJSON, default=dict)  # 'metadata' is SQLAlchemy reserved

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Relationships
    company = relationship("Company")
    template = relationship("DocumentTemplate", back_populates="generated_documents")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_generated_company", "company_id"),
        Index("ix_generated_template", "template_id"),
        Index("ix_generated_entity", "linked_entity_id"),
        Index("ix_generated_document", "linked_document_id"),
        Index("ix_generated_created", "created_at"),
        {"comment": "Aus Vorlagen generierte Dokumente (Vorlagen-System)"}
    )

    def __repr__(self) -> str:
        return f"<GeneratedDocument {self.title}>"


class TemplateSnippet(Base):
    """
    Wiederverwendbare Textbausteine fuer Templates.

    z.B. Standard-Fusszeilen, AGBs, Grussformeln.
    """
    __tablename__ = "template_snippets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    # Identifikation
    name = Column(String(255), nullable=False)
    code = Column(String(50), nullable=False)  # z.B. "AGB-FOOTER"
    description = Column(Text, nullable=True)
    category = Column(String(100), default="general")

    # Inhalt
    content = Column(Text, nullable=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_snippet_code"),
        Index("ix_snippet_company", "company_id"),
        Index("ix_snippet_category", "category"),
        Index("ix_snippet_is_active", "is_active"),
        {"comment": "Wiederverwendbare Textbausteine fuer Templates (Vorlagen-System)"}
    )

    def __repr__(self) -> str:
        return f"<TemplateSnippet {self.code}>"


# =============================================================================
# KNOWLEDGE MANAGEMENT SYSTEM
# =============================================================================


class NoteType(str, Enum):
    """Typen von Knowledge Notes."""

    GENERAL = "general"
    PROCEDURE = "procedure"  # Prozessbeschreibung
    FAQ = "faq"
    TEMPLATE = "template"
    MEETING_NOTES = "meeting_notes"
    DECISION = "decision"
    DOCUMENTATION = "documentation"


class ContentFormat(str, Enum):
    """Format des Note-Inhalts."""

    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN = "plain"


class KnowledgeLinkType(str, Enum):
    """Typen von Knowledge Links."""

    RELATED = "related"  # Allgemein verwandt
    REFERENCES = "references"  # Referenziert
    REPLACES = "replaces"  # Ersetzt
    CONTINUES = "continues"  # Fortsetzung
    CONTRADICTS = "contradicts"  # Widerspricht
    EXPLAINS = "explains"  # Erklaert


class LinkableType(str, Enum):
    """Typen von verlinkbaren Objekten."""

    NOTE = "note"
    DOCUMENT = "document"
    ENTITY = "entity"
    CHECKLIST = "checklist"


class KnowledgeNote(Base):
    """
    Wiki-artige Notiz im Knowledge Management System.

    Features:
    - Markdown-Content
    - Hierarchische Struktur (parent_note_id)
    - Polymorph verknuepfbar (Document, Entity, Company)
    - Tags fuer Kategorisierung
    - Full-Text-Suche (via DB Index)
    """

    __tablename__ = "knowledge_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Content
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=True)
    content_format = Column(String(20), default=ContentFormat.MARKDOWN.value)

    # Kategorisierung
    note_type = Column(String(50), nullable=False, default=NoteType.GENERAL.value)

    # Polymorph Verknuepfungen
    linked_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_project_id = Column(UUID(as_uuid=True), nullable=True)

    # Hierarchie
    parent_note_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_notes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Metadaten
    is_pinned = Column(Boolean, default=False)
    is_template = Column(Boolean, default=False)
    view_count = Column(Integer, default=0)
    tags = Column(CrossDBJSON, default=list)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    updated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    linked_document = relationship("Document", foreign_keys=[linked_document_id])
    linked_entity = relationship("BusinessEntity", foreign_keys=[linked_entity_id])
    linked_company = relationship("Company", foreign_keys=[linked_company_id])
    parent_note = relationship(
        "KnowledgeNote",
        remote_side=[id],
        foreign_keys=[parent_note_id],
        back_populates="child_notes",
    )
    child_notes = relationship(
        "KnowledgeNote",
        back_populates="parent_note",
        foreign_keys=[parent_note_id],
    )
    created_by = relationship("User", foreign_keys=[created_by_id])
    updated_by = relationship("User", foreign_keys=[updated_by_id])
    checklists = relationship(
        "KnowledgeChecklist",
        back_populates="linked_note",
        foreign_keys="KnowledgeChecklist.linked_note_id",
    )

    __table_args__ = (
        Index("ix_knowledge_notes_linked_document_id", "linked_document_id"),
        Index("ix_knowledge_notes_linked_entity_id", "linked_entity_id"),
        Index("ix_knowledge_notes_linked_company_id", "linked_company_id"),
        Index("ix_knowledge_notes_parent_note_id", "parent_note_id"),
        Index("ix_knowledge_notes_note_type", "note_type"),
        Index("ix_knowledge_notes_is_pinned", "is_pinned"),
        Index("ix_knowledge_notes_created_by_id", "created_by_id"),
        Index("ix_knowledge_notes_deleted_at", "deleted_at"),
        {"comment": "Wiki-artige Notizen (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        return f"<KnowledgeNote {self.title[:50]} ({self.id})>"


class KnowledgeChecklist(Base):
    """
    Checkliste im Knowledge Management System.

    Features:
    - Titel und Beschreibung
    - Verknuepfbar mit Documents, Entities, Notes
    - Template-Funktion fuer wiederverwendbare Checklisten
    """

    __tablename__ = "knowledge_checklists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Content
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Polymorph Verknuepfungen
    linked_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_note_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_notes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    is_template = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    items = relationship(
        "KnowledgeChecklistItem",
        back_populates="checklist",
        cascade="all, delete-orphan",
        order_by="KnowledgeChecklistItem.sort_order",
    )
    linked_document = relationship("Document", foreign_keys=[linked_document_id])
    linked_entity = relationship("BusinessEntity", foreign_keys=[linked_entity_id])
    linked_company = relationship("Company", foreign_keys=[linked_company_id])
    linked_note = relationship(
        "KnowledgeNote",
        foreign_keys=[linked_note_id],
        back_populates="checklists",
    )
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_knowledge_checklists_linked_document_id", "linked_document_id"),
        Index("ix_knowledge_checklists_linked_entity_id", "linked_entity_id"),
        Index("ix_knowledge_checklists_linked_company_id", "linked_company_id"),
        Index("ix_knowledge_checklists_linked_note_id", "linked_note_id"),
        Index("ix_knowledge_checklists_deleted_at", "deleted_at"),
        {"comment": "Checklisten (Knowledge Management)"}
    )

    @property
    def is_completed(self) -> bool:
        """Prueft ob alle Items abgehakt sind."""
        if not self.items:
            return False
        return all(item.is_completed for item in self.items)

    @property
    def completion_percentage(self) -> float:
        """Berechnet den Fortschritt in Prozent."""
        if not self.items:
            return 0.0
        completed = sum(1 for item in self.items if item.is_completed)
        return (completed / len(self.items)) * 100

    def __repr__(self) -> str:
        return f"<KnowledgeChecklist {self.title[:50]} ({self.id})>"


class KnowledgeChecklistItem(Base):
    """Einzelnes Item in einer Checklist."""

    __tablename__ = "knowledge_checklist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    checklist_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_checklists.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Content
    text = Column(String(1000), nullable=False)
    description = Column(Text, nullable=True)

    # Status
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Optional: Deadline
    due_date = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    checklist = relationship("KnowledgeChecklist", back_populates="items")
    completed_by = relationship("User", foreign_keys=[completed_by_id])

    __table_args__ = (
        Index("ix_knowledge_checklist_items_checklist_id", "checklist_id"),
        Index("ix_knowledge_checklist_items_is_completed", "is_completed"),
        Index("ix_knowledge_checklist_items_sort_order", "sort_order"),
        {"comment": "Checklist Items (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        status = "✓" if self.is_completed else "○"
        return f"<KnowledgeChecklistItem {status} {self.text[:30]} ({self.id})>"


class KnowledgeLink(Base):
    """
    Verknuepfung im Knowledge Graph.

    Ermoeglicht die Verbindung verschiedener Objekte:
    - Note <-> Note
    - Note <-> Document
    - Note <-> Entity
    - Document <-> Entity
    """

    __tablename__ = "knowledge_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source (polymorph)
    source_type = Column(String(50), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)

    # Target (polymorph)
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)

    # Beziehungstyp
    link_type = Column(String(50), nullable=False, default=KnowledgeLinkType.RELATED.value)

    # Metadaten
    description = Column(String(500), nullable=True)
    confidence = Column(Float, nullable=True)  # Fuer automatisch erstellte Links
    is_bidirectional = Column(Boolean, default=True)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_knowledge_links_source", "source_type", "source_id"),
        Index("ix_knowledge_links_target", "target_type", "target_id"),
        Index("ix_knowledge_links_link_type", "link_type"),
        UniqueConstraint(
            "source_type", "source_id", "target_type", "target_id", "link_type",
            name="uq_knowledge_links_source_target_type",
        ),
        {"comment": "Knowledge Graph Links (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        return f"<KnowledgeLink {self.source_type}:{self.source_id} --[{self.link_type}]--> {self.target_type}:{self.target_id}>"


class KnowledgeTag(Base):
    """Tag fuer Kategorisierung von Knowledge Items."""

    __tablename__ = "knowledge_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), nullable=True)  # Hex #FF0000
    description = Column(String(500), nullable=True)
    usage_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_knowledge_tags_name", "name"),
        Index("ix_knowledge_tags_usage_count", "usage_count"),
        {"comment": "Tags fuer Knowledge Items (Knowledge Management)"}
    )

    def __repr__(self) -> str:
        return f"<KnowledgeTag {self.name} ({self.usage_count} uses)>"


# ============================================================================
# SLACK INTEGRATION MODELS
# Slack-Kanal-Konfiguration und Benachrichtigungsverlauf
# ============================================================================


class SlackChannelType(str, Enum):
    """Typ des Slack-Kanals."""
    PUBLIC = "public"
    PRIVATE = "private"
    DM = "dm"  # Direct Message


class SlackChannel(Base):
    """
    Slack-Kanal-Konfiguration fuer Benachrichtigungen.

    Ermoeglicht Multi-Kanal-Routing basierend auf:
    - Notification-Typ (document_processed, approval_required, etc.)
    - Firma (Multi-Tenant)
    - Prioritaet
    """

    __tablename__ = "slack_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kanal-Identifikation
    channel_id = Column(String(50), nullable=False, comment="Slack Channel ID (z.B. C01234567)")
    channel_name = Column(String(100), nullable=False, comment="Kanal-Name ohne #")
    channel_type = Column(
        String(20),
        default=SlackChannelType.PUBLIC.value,
        comment="Kanal-Typ: public, private, dm"
    )

    # Multi-Tenant Support
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        comment="Firmen-spezifischer Kanal (NULL = global)"
    )

    # Routing-Konfiguration
    notification_types = Column(
        CrossDBJSON,
        default=[],
        comment="Notification-Typen die an diesen Kanal gehen"
    )
    min_priority = Column(
        String(20),
        default="normal",
        comment="Mindest-Prioritaet: low, normal, high, urgent"
    )
    is_default = Column(Boolean, default=False, comment="Standard-Kanal fuer nicht-routbare Nachrichten")

    # Formatierung
    include_context = Column(Boolean, default=True, comment="Kontext-Details einschliessen")
    mention_users = Column(
        CrossDBJSON,
        default=[],
        comment="Slack User-IDs die bei Nachrichten erwaehnt werden"
    )
    custom_icon = Column(String(100), nullable=True, comment="Custom Emoji als Icon")

    # Status
    is_active = Column(Boolean, default=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0)

    # Audit
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="slack_channels")
    created_by = relationship("User", foreign_keys=[created_by_id])
    messages = relationship("SlackMessageLog", back_populates="channel", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_slack_channels_company", "company_id"),
        Index("ix_slack_channels_active", "is_active"),
        Index("ix_slack_channels_channel_id", "channel_id"),
        UniqueConstraint("channel_id", "company_id", name="uq_slack_channels_channel_company"),
        {"comment": "Slack-Kanal-Konfiguration fuer Benachrichtigungen"}
    )

    def __repr__(self) -> str:
        return f"<SlackChannel #{self.channel_name} ({self.channel_id})>"


class SlackMessageStatus(str, Enum):
    """Status einer Slack-Nachricht."""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


class SlackMessageLog(Base):
    """
    Log fuer gesendete Slack-Nachrichten.

    Ermoeglicht:
    - Nachverfolgung von Benachrichtigungen
    - Rate Limit Monitoring
    - Fehleranalyse
    - Audit Trail
    """

    __tablename__ = "slack_message_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Kanal-Referenz
    channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("slack_channels.id", ondelete="SET NULL"),
        nullable=True
    )
    slack_channel_id = Column(String(50), nullable=False, comment="Slack Channel ID als Backup")

    # Nachricht
    message_ts = Column(String(50), nullable=True, comment="Slack Message Timestamp/ID")
    thread_ts = Column(String(50), nullable=True, comment="Thread Timestamp wenn Antwort")
    notification_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message_preview = Column(String(500), nullable=True, comment="Erste 500 Zeichen")
    priority = Column(String(20), default="normal")

    # Status
    status = Column(
        String(20),
        default=SlackMessageStatus.PENDING.value,
    )
    error_message = Column(String(500), nullable=True)
    retry_count = Column(Integer, default=0)

    # Referenz zum Ausloesenden Objekt (polymorph)
    reference_type = Column(String(50), nullable=True, comment="document, approval, workflow, etc.")
    reference_id = Column(UUID(as_uuid=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    channel = relationship("SlackChannel", back_populates="messages")

    __table_args__ = (
        Index("ix_slack_messages_channel", "channel_id"),
        Index("ix_slack_messages_status", "status"),
        Index("ix_slack_messages_created", "created_at"),
        Index("ix_slack_messages_notification_type", "notification_type"),
        Index("ix_slack_messages_reference", "reference_type", "reference_id"),
        {"comment": "Log fuer gesendete Slack-Nachrichten"}
    )

    def __repr__(self) -> str:
        return f"<SlackMessageLog {self.notification_type} -> {self.slack_channel_id} ({self.status})>"


class SlackUserMapping(Base):
    """
    Mapping zwischen Ablage-System Benutzern und Slack User-IDs.

    Ermoeglicht:
    - Direkte Benachrichtigungen an Benutzer
    - @mentions in Kanal-Nachrichten
    - Berechtigungs-Pruefung fuer Slack-Aktionen
    """

    __tablename__ = "slack_user_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User-Referenzen
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    slack_user_id = Column(String(50), nullable=False, comment="Slack User ID (z.B. U01234567)")
    slack_username = Column(String(100), nullable=True, comment="Slack Display Name")

    # Benachrichtigungs-Praeferenzen
    dm_enabled = Column(Boolean, default=False, comment="Direkte Nachrichten erlauben")
    dm_notification_types = Column(
        CrossDBJSON,
        default=[],
        comment="Notification-Typen die als DM gesendet werden"
    )
    mention_on_approval = Column(Boolean, default=True, comment="Bei Freigabe-Anfragen erwaehnen")
    quiet_hours_start = Column(String(5), nullable=True, comment="Ruhezeit Start (HH:MM)")
    quiet_hours_end = Column(String(5), nullable=True, comment="Ruhezeit Ende (HH:MM)")

    # Verifizierung
    is_verified = Column(Boolean, default=False, comment="Slack-Account verifiziert")
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="slack_mapping", uselist=False)

    __table_args__ = (
        Index("ix_slack_user_mappings_slack_user", "slack_user_id"),
        UniqueConstraint("slack_user_id", name="uq_slack_user_mappings_slack_user"),
        {"comment": "Mapping Ablage-System User <-> Slack User"}
    )

    def __repr__(self) -> str:
        return f"<SlackUserMapping User:{self.user_id} -> Slack:{self.slack_user_id}>"


# ==================== Shipping/Paketdienst Models ====================


class ShipmentCarrier(str, Enum):
    """Unterstuetzte Paketdienste."""
    DHL = "dhl"
    DPD = "dpd"
    HERMES = "hermes"
    UPS = "ups"
    GLS = "gls"
    FEDEX = "fedex"
    DEUTSCHE_POST = "deutsche_post"
    UNKNOWN = "unknown"


class ShipmentDirection(str, Enum):
    """Sendungsrichtung."""
    INBOUND = "inbound"    # Eingehend (Wareneingang)
    OUTBOUND = "outbound"  # Ausgehend (Versand an Kunden)
    RETURN = "return"      # Retoure


class ShipmentStatusEnum(str, Enum):
    """Standardisierte Sendungsstatus."""
    UNKNOWN = "unknown"
    LABEL_CREATED = "label_created"          # Label erstellt, noch nicht abgeholt
    PICKED_UP = "picked_up"                  # Vom Carrier abgeholt
    IN_TRANSIT = "in_transit"                # Unterwegs
    OUT_FOR_DELIVERY = "out_for_delivery"    # In Zustellung
    DELIVERED = "delivered"                  # Zugestellt
    DELIVERY_ATTEMPT = "delivery_attempt"    # Zustellversuch (nicht angetroffen)
    HELD_AT_LOCATION = "held_at_location"    # Liegt zur Abholung bereit
    RETURNED = "returned"                    # Zurueck an Absender
    EXCEPTION = "exception"                  # Problem/Ausnahme
    CUSTOMS = "customs"                      # Im Zoll


class Shipment(Base):
    """
    Sendungsverfolgung fuer Paketdienste.

    Features:
    - Multi-Carrier Support (DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post)
    - Automatische Carrier-Erkennung anhand Tracking-Nummer
    - Verknuepfung mit Business Entities und Dokumenten
    - Kosten-Tracking und Analyse

    Multi-Tenant: Alle Abfragen MUESSEN company_id filtern!
    """

    __tablename__ = "shipments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenant: PFLICHT
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tracking-Daten
    tracking_number = Column(String(50), nullable=False)
    carrier = Column(String(20), nullable=False, default=ShipmentCarrier.UNKNOWN.value)
    direction = Column(String(20), nullable=False, default=ShipmentDirection.INBOUND.value)
    status = Column(String(30), nullable=False, default=ShipmentStatusEnum.UNKNOWN.value)
    status_description = Column(String(255), nullable=True)

    # Tracking URL (oeffentlich)
    tracking_url = Column(String(500), nullable=True)

    # Zeitpunkte
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    actual_delivery = Column(DateTime(timezone=True), nullable=True)
    last_tracking_update = Column(DateTime(timezone=True), nullable=True)

    # Herkunft/Ziel
    origin = Column(String(100), nullable=True)
    destination = Column(String(100), nullable=True)

    # Details
    weight_kg = Column(Float, nullable=True)
    service_type = Column(String(100), nullable=True)  # z.B. "DHL Paket", "Express"
    reference = Column(String(100), nullable=True)  # z.B. Bestellnummer
    notes = Column(Text, nullable=True)

    # Kosten (optional)
    shipping_cost = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="EUR")

    # Verknuepfungen
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknuepfter Kunde/Lieferant"
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknuepfter Lieferschein/Rechnung"
    )

    # Raw API Response (fuer Debugging)
    raw_tracking_data = Column(CrossDBJSON, default={})

    # Soft Delete
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company")
    entity = relationship("BusinessEntity", backref="shipments")
    document = relationship("Document", backref="shipments")
    events = relationship("ShipmentEvent", back_populates="shipment", order_by="desc(ShipmentEvent.timestamp)")
    creator = relationship("User")

    __table_args__ = (
        # Composite Index fuer Multi-Tenant
        Index("ix_shipments_company_status", "company_id", "status"),
        Index("ix_shipments_company_carrier", "company_id", "carrier"),
        Index("ix_shipments_company_direction", "company_id", "direction"),
        Index("ix_shipments_tracking", "tracking_number"),
        Index("ix_shipments_entity", "entity_id"),
        Index("ix_shipments_document", "document_id"),
        Index("ix_shipments_estimated_delivery", "estimated_delivery"),
        Index("ix_shipments_created", "created_at"),
        # Unique: Tracking-Nummer pro Company
        UniqueConstraint("company_id", "tracking_number", name="uq_shipments_company_tracking"),
        {"comment": "Sendungsverfolgung fuer Paketdienste"}
    )

    def __repr__(self) -> str:
        return f"<Shipment {self.carrier}:{self.tracking_number} ({self.status})>"


class ShipmentEvent(Base):
    """
    Einzelnes Tracking-Event fuer eine Sendung.

    Chronologischer Verlauf aller Status-Aenderungen.
    """

    __tablename__ = "shipment_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Sendungs-Referenz
    shipment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shipments.id", ondelete="CASCADE"),
        nullable=False
    )

    # Event-Daten
    timestamp = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(30), nullable=False)
    description = Column(String(500), nullable=True)

    # Ort
    location = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country_code = Column(String(3), nullable=True)

    # Original-Status vom Carrier
    raw_status = Column(String(100), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    shipment = relationship("Shipment", back_populates="events")

    __table_args__ = (
        Index("ix_shipment_events_shipment", "shipment_id"),
        Index("ix_shipment_events_timestamp", "timestamp"),
        Index("ix_shipment_events_status", "status"),
        # Unique: Ein Event pro Sendung und Zeitstempel
        UniqueConstraint("shipment_id", "timestamp", name="uq_shipment_events_shipment_timestamp"),
        {"comment": "Tracking-Events fuer Sendungen"}
    )


# =============================================================================
# Business Contract Models (from app.db.models.contract)
# =============================================================================

class ContractType(str, Enum):
    """Types of business contracts."""
    SERVICE = "service"  # Dienstleistungsvertrag
    SUPPLY = "supply"  # Liefervertrag
    FRAMEWORK = "framework"  # Rahmenvertrag
    MAINTENANCE = "maintenance"  # Wartungsvertrag
    LICENSE = "license"  # Lizenzvertrag
    LEASE = "lease"  # Mietvertrag (Geschaeftsraeume)
    CONSULTING = "consulting"  # Beratungsvertrag
    COOPERATION = "cooperation"  # Kooperationsvertrag
    NDA = "nda"  # Geheimhaltungsvereinbarung
    PURCHASE = "purchase"  # Kaufvertrag
    OTHER = "other"


class ContractStatus(str, Enum):
    """Contract lifecycle status."""
    DRAFT = "draft"  # Entwurf
    PENDING_SIGNATURE = "pending_signature"  # Unterschrift ausstehend
    ACTIVE = "active"  # Aktiv
    SUSPENDED = "suspended"  # Ausgesetzt
    EXPIRING_SOON = "expiring_soon"  # Laeuft bald ab
    EXPIRED = "expired"  # Abgelaufen
    TERMINATED = "terminated"  # Gekuendigt
    RENEWED = "renewed"  # Verlaengert


class RenewalOptionStatus(str, Enum):
    """Status of renewal options."""
    AVAILABLE = "available"  # Verfuegbar
    PENDING = "pending"  # Entscheidung ausstehend
    EXERCISED = "exercised"  # Ausgeubt
    DECLINED = "declined"  # Abgelehnt
    EXPIRED = "expired"  # Abgelaufen


class MilestoneType(str, Enum):
    """Types of contract milestones."""
    CONTRACT_START = "contract_start"
    CONTRACT_END = "contract_end"
    RENEWAL_OPTION = "renewal_option"
    NOTICE_DEADLINE = "notice_deadline"
    PRICE_ADJUSTMENT = "price_adjustment"
    SERVICE_LEVEL_REVIEW = "service_level_review"
    DELIVERABLE_DUE = "deliverable_due"
    PAYMENT_DUE = "payment_due"
    AUDIT = "audit"
    CUSTOM = "custom"


class AmendmentStatus(str, Enum):
    """Status of contract amendments."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class BusinessContract(Base):
    """
    Business Contract entity for B2B contract management.

    Supports:
    - Contract lifecycle tracking
    - Automatic deadline calculations
    - Renewal options management
    - Multi-tenant operation
    """
    __tablename__ = "business_contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )

    # Contract identification
    contract_number: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    contract_type: Mapped[ContractType] = mapped_column(
        SQLAlchemyEnum(ContractType), default=ContractType.OTHER
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Contract parties
    party_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True
    )
    party_a_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_a_signatory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    party_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_entities.id"), nullable=True
    )
    party_b_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    party_b_signatory: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Contract timeline
    contract_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    duration_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Termination and renewal
    notice_period_days: Mapped[int] = mapped_column(Integer, default=30)
    notice_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    auto_renewal: Mapped[bool] = mapped_column(Boolean, default=False)
    renewal_period_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_renewals: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_renewal_count: Mapped[int] = mapped_column(Integer, default=0)

    # Financial terms
    total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    monthly_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    payment_terms: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Price adjustments
    price_adjustment_clause: Mapped[bool] = mapped_column(Boolean, default=False)
    price_adjustment_index: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "VPI", "Verbraucherpreisindex"
    price_adjustment_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    price_adjustment_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # Legal terms
    governing_law: Mapped[str] = mapped_column(String(100), default="Deutsches Recht")
    jurisdiction: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    arbitration_clause: Mapped[bool] = mapped_column(Boolean, default=False)

    # Document references
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )

    # Status and workflow
    status: Mapped[ContractStatus] = mapped_column(
        SQLAlchemyEnum(ContractStatus), default=ContractStatus.DRAFT
    )
    signed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    terminated_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    termination_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notifications
    reminder_days: Mapped[List[int]] = mapped_column(
        JSONB, default=lambda: [90, 60, 30, 14, 7]
    )
    last_reminder_sent: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notification_emails: Mapped[List[str]] = mapped_column(
        JSONB, default=list
    )

    # Metadata
    tags: Mapped[List[str]] = mapped_column(JSONB, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    key_contacts: Mapped[List[dict]] = mapped_column(JSONB, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    company = relationship("Company", foreign_keys=[company_id])
    party_a = relationship("BusinessEntity", foreign_keys=[party_a_id])
    party_b = relationship("BusinessEntity", foreign_keys=[party_b_id])
    document = relationship("Document", foreign_keys=[document_id])
    created_by = relationship("User", foreign_keys=[created_by_id])
    milestones = relationship(
        "ContractMilestone", back_populates="contract", cascade="all, delete-orphan"
    )
    amendments = relationship(
        "ContractAmendment", back_populates="contract", cascade="all, delete-orphan"
    )
    renewal_options = relationship(
        "ContractRenewalOption", back_populates="contract", cascade="all, delete-orphan"
    )

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint("company_id", "contract_number", name="uq_contract_number"),
        Index("ix_contract_company", "company_id"),
        Index("ix_contract_status", "status"),
        Index("ix_contract_end_date", "end_date"),
        Index("ix_contract_notice_deadline", "notice_deadline"),
        Index("ix_contract_party_a", "party_a_id"),
        Index("ix_contract_party_b", "party_b_id"),
    )

    @hybrid_property
    def days_until_end(self) -> Optional[int]:
        """Calculate days until contract ends."""
        if not self.end_date:
            return None
        delta = self.end_date - date.today()
        return delta.days

    @hybrid_property
    def days_until_notice_deadline(self) -> Optional[int]:
        """Calculate days until notice deadline."""
        if not self.notice_deadline:
            return None
        delta = self.notice_deadline - date.today()
        return delta.days

    @hybrid_property
    def is_expiring_soon(self) -> bool:
        """Check if contract is expiring within 90 days."""
        if not self.end_date:
            return False
        return 0 < (self.end_date - date.today()).days <= 90

    @hybrid_property
    def is_notice_deadline_critical(self) -> bool:
        """Check if notice deadline is within 30 days."""
        if not self.notice_deadline:
            return False
        days = (self.notice_deadline - date.today()).days
        return 0 < days <= 30

    def calculate_notice_deadline(self) -> Optional[date]:
        """Calculate notice deadline based on end date and notice period."""
        if not self.end_date:
            return None
        return self.end_date - timedelta(days=self.notice_period_days)

    def update_notice_deadline(self) -> None:
        """Update the notice deadline field."""
        self.notice_deadline = self.calculate_notice_deadline()


class ContractMilestone(Base):
    """
    Contract milestones for tracking key dates and events.
    """
    __tablename__ = "contract_milestones"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_contracts.id"), nullable=False
    )

    milestone_type: Mapped[MilestoneType] = mapped_column(
        SQLAlchemyEnum(MilestoneType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Completion tracking
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completion_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Notifications
    reminder_days_before: Mapped[List[int]] = mapped_column(
        JSONB, default=lambda: [14, 7, 1]
    )
    last_reminder_sent: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Linked task (optional)
    linked_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="milestones")

    __table_args__ = (
        Index("ix_milestone_contract", "contract_id"),
        Index("ix_milestone_scheduled", "scheduled_date"),
        Index("ix_milestone_type", "milestone_type"),
    )

    @hybrid_property
    def days_until_due(self) -> int:
        """Calculate days until milestone is due."""
        delta = self.scheduled_date - date.today()
        return delta.days

    @hybrid_property
    def is_overdue(self) -> bool:
        """Check if milestone is overdue and not completed."""
        return not self.is_completed and self.scheduled_date < date.today()


class ContractRenewalOption(Base):
    """
    Tracks available renewal options for a contract.
    """
    __tablename__ = "contract_renewal_options"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_contracts.id"), nullable=False
    )

    # Option details
    option_number: Mapped[int] = mapped_column(Integer, nullable=False)
    renewal_duration_months: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pricing
    price_adjustment_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # "fixed", "percentage", "index"
    price_adjustment_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    new_monthly_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )

    # Deadlines
    exercise_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    renewal_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    notice_required_days: Mapped[int] = mapped_column(Integer, default=30)

    # Status
    status: Mapped[RenewalOptionStatus] = mapped_column(
        SQLAlchemyEnum(RenewalOptionStatus), default=RenewalOptionStatus.AVAILABLE
    )
    exercised_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    exercised_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="renewal_options")
    exercised_by = relationship("User", foreign_keys=[exercised_by_id])

    __table_args__ = (
        UniqueConstraint(
            "contract_id", "option_number", name="uq_contract_renewal_option"
        ),
        Index("ix_renewal_contract", "contract_id"),
        Index("ix_renewal_deadline", "exercise_deadline"),
        Index("ix_renewal_status", "status"),
    )

    @hybrid_property
    def days_until_deadline(self) -> int:
        """Calculate days until exercise deadline."""
        delta = self.exercise_deadline - date.today()
        return delta.days

    @hybrid_property
    def is_deadline_critical(self) -> bool:
        """Check if deadline is within 30 days and option still available."""
        if self.status != RenewalOptionStatus.AVAILABLE:
            return False
        return 0 < self.days_until_deadline <= 30


class ContractAmendment(Base):
    """
    Tracks contract amendments and changes.
    """
    __tablename__ = "contract_amendments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("business_contracts.id"), nullable=False
    )

    # Amendment identification
    amendment_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amendment_date: Mapped[date] = mapped_column(Date, nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Changes
    changes_summary: Mapped[str] = mapped_column(Text, nullable=False)
    affected_clauses: Mapped[List[str]] = mapped_column(JSONB, default=list)
    changes_detail: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Financial impact
    value_change: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )
    new_total_value: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2), nullable=True
    )

    # Document
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )

    # Status
    status: Mapped[AmendmentStatus] = mapped_column(
        SQLAlchemyEnum(AmendmentStatus), default=AmendmentStatus.DRAFT
    )
    approved_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    approved_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    # Relationships
    contract = relationship("BusinessContract", back_populates="amendments")
    document = relationship("Document", foreign_keys=[document_id])
    approved_by = relationship("User", foreign_keys=[approved_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint(
            "contract_id", "amendment_number", name="uq_contract_amendment_number"
        ),
        Index("ix_amendment_contract", "contract_id"),
        Index("ix_amendment_status", "status"),
        Index("ix_amendment_effective", "effective_date"),
    )


# Event Listeners for BusinessContract
@event.listens_for(BusinessContract, 'before_insert')
@event.listens_for(BusinessContract, 'before_update')
def contract_before_save(mapper, connection, target: BusinessContract):
    """Auto-calculate notice deadline before saving."""
    if target.end_date and target.notice_period_days:
        target.notice_deadline = target.calculate_notice_deadline()

    # Auto-update status based on dates
    today = date.today()
    if target.status not in [ContractStatus.DRAFT, ContractStatus.TERMINATED]:
        if target.end_date:
            if target.end_date < today:
                target.status = ContractStatus.EXPIRED
            elif (target.end_date - today).days <= 90:
                target.status = ContractStatus.EXPIRING_SOON
            elif target.status == ContractStatus.EXPIRING_SOON:
                target.status = ContractStatus.ACTIVE


# =============================================================================
# MULTI-TENANT SUBSCRIPTION SYSTEM (Migration 104)
# =============================================================================


class SubscriptionTier(str, Enum):
    """Abonnement-Stufen fuer Multi-Tenant SaaS."""
    FREE = "free"
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class TenantRateLimit(Base):
    """Tenant-spezifische Rate Limit Konfiguration.

    Ermoeglicht individuelle Rate-Limits pro Mandant und Endpoint-Pattern.
    Wird durch SubscriptionTierDefaults mit Defaults befuellt.
    """
    __tablename__ = "tenant_rate_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Endpoint-spezifische Limits
    endpoint_pattern = Column(
        String(255),
        nullable=False,
        comment="Endpoint-Pattern (z.B. /api/v1/documents/*)"
    )
    requests_per_minute = Column(Integer, nullable=False, default=100)
    requests_per_hour = Column(Integer, nullable=False, default=1000)
    requests_per_day = Column(Integer, nullable=False, default=10000)

    # Burst-Limits
    burst_limit = Column(
        Integer,
        nullable=False,
        default=50,
        comment="Max Requests in 1 Sekunde"
    )

    # Spezielle Limits
    ocr_requests_per_hour = Column(Integer, nullable=True, comment="OCR-spezifisches Limit")
    batch_requests_per_hour = Column(Integer, nullable=True, comment="Batch-Operations Limit")
    export_requests_per_day = Column(Integer, nullable=True, comment="Export-Limit pro Tag")

    # Flags
    is_custom = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True wenn manuell angepasst"
    )
    is_active = Column(Boolean, nullable=False, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    company = relationship("Company", back_populates="rate_limits")
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        UniqueConstraint("company_id", "endpoint_pattern", name="uq_tenant_rate_limits_company_endpoint"),
        Index("ix_tenant_rate_limits_endpoint", "endpoint_pattern"),
    )

    def __repr__(self) -> str:
        return f"<TenantRateLimit {self.company_id}:{self.endpoint_pattern}>"


class TenantUsageMetrics(Base):
    """Aggregierte Nutzungsmetriken pro Tenant fuer Dashboard und Analytics.

    Wird automatisch durch Celery-Tasks befuellt (hourly, daily, monthly).
    """
    __tablename__ = "tenant_usage_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zeitraum
    period_type = Column(
        String(20),
        nullable=False,
        comment="hourly, daily, monthly"
    )
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # API Metriken
    total_requests = Column(BigInteger, nullable=False, default=0)
    rate_limited_requests = Column(BigInteger, nullable=False, default=0)
    failed_requests = Column(BigInteger, nullable=False, default=0)
    avg_response_time_ms = Column(Float, nullable=True)
    p95_response_time_ms = Column(Float, nullable=True)
    p99_response_time_ms = Column(Float, nullable=True)

    # OCR Metriken
    documents_processed = Column(Integer, nullable=False, default=0)
    pages_processed = Column(Integer, nullable=False, default=0)
    ocr_processing_time_ms = Column(BigInteger, nullable=False, default=0)

    # Storage Metriken
    storage_used_bytes = Column(BigInteger, nullable=False, default=0)
    documents_stored = Column(Integer, nullable=False, default=0)

    # User Metriken
    active_users = Column(Integer, nullable=False, default=0)
    unique_sessions = Column(Integer, nullable=False, default=0)

    # Endpoint-Breakdown
    endpoint_breakdown = Column(
        CrossDBJSON,
        nullable=True,
        comment="Requests pro Endpoint"
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="usage_metrics")

    __table_args__ = (
        UniqueConstraint("company_id", "period_type", "period_start", name="uq_tenant_metrics_period"),
        Index("ix_tenant_metrics_period", "period_type", "period_start"),
        Index("ix_tenant_metrics_company_period", "company_id", "period_type", "period_start"),
    )

    def __repr__(self) -> str:
        return f"<TenantUsageMetrics {self.company_id}:{self.period_type}:{self.period_start}>"


class RateLimitViolation(Base):
    """Log fuer Rate-Limit-Verletzungen.

    Wird fuer Security-Monitoring und Abuse-Detection verwendet.
    """
    __tablename__ = "rate_limit_violations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Violation Details
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    ip_address = Column(String(45), nullable=False)
    user_agent = Column(String(500), nullable=True)

    # Limit Info
    limit_type = Column(
        String(50),
        nullable=False,
        comment="minute, hour, day, burst"
    )
    limit_value = Column(Integer, nullable=False)
    current_count = Column(Integer, nullable=False)
    retry_after_seconds = Column(Integer, nullable=True)

    # Timestamp
    occurred_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", back_populates="rate_limit_violations")
    user = relationship("User")

    __table_args__ = (
        Index("ix_rate_violations_time", "occurred_at"),
        Index("ix_rate_violations_endpoint", "endpoint"),
    )

    def __repr__(self) -> str:
        return f"<RateLimitViolation {self.endpoint}@{self.occurred_at}>"


class SubscriptionTierDefaults(Base):
    """Default-Konfiguration fuer Subscription Tiers.

    Definiert die Standard-Limits und Features pro Tier.
    Admin kann diese anpassen.
    """
    __tablename__ = "subscription_tier_defaults"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier = Column(String(50), nullable=False, unique=True)

    # Limits
    max_users = Column(Integer, nullable=False)
    max_documents_per_month = Column(Integer, nullable=False)
    max_storage_gb = Column(Integer, nullable=False)

    # Rate Limits
    requests_per_minute = Column(Integer, nullable=False)
    requests_per_hour = Column(Integer, nullable=False)
    requests_per_day = Column(Integer, nullable=False)
    ocr_requests_per_hour = Column(Integer, nullable=False)
    batch_requests_per_hour = Column(Integer, nullable=False)

    # Features
    features_enabled = Column(CrossDBJSON, nullable=False)

    # Pricing (fuer Billing-Vorbereitung)
    price_monthly_eur = Column(Numeric(10, 2), nullable=True)
    price_yearly_eur = Column(Numeric(10, 2), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<SubscriptionTierDefaults {self.tier}>"


# ==================== Business Contacts ====================


class ContactType(str, Enum):
    """Kontakttyp fuer BusinessContact."""
    CUSTOMER = "customer"      # Kunde
    SUPPLIER = "supplier"      # Lieferant
    PARTNER = "partner"        # Partner
    PROSPECT = "prospect"      # Interessent
    OTHER = "other"            # Sonstige


class ContactRole(str, Enum):
    """Rolle eines Kontakts bei einem Dokument."""
    SENDER = "sender"          # Absender
    RECIPIENT = "recipient"    # Empfaenger
    MENTIONED = "mentioned"    # Erwaehnt
    CC = "cc"                  # CC


class DocumentContact(Base):
    """
    Verknuepfung zwischen Dokumenten und Geschaeftskontakten.

    Ermoeglicht:
    - Mehrere Kontakte pro Dokument (Sender, Empfaenger, Erwaehnt)
    - Mehrere Dokumente pro Kontakt
    - Automatische Erkennung mit Confidence-Score
    """
    __tablename__ = "document_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("business_contacts.id", ondelete="CASCADE"), nullable=False, index=True)

    # Role and detection
    role = Column(String(20), nullable=False, default=ContactRole.MENTIONED.value)
    confidence = Column(Float, nullable=True)  # 0.0-1.0 fuer auto-detected
    is_auto_detected = Column(Boolean, default=False)

    # Metadata
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    confirmed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("Document", backref="contact_links")
    contact = relationship("BusinessContact", back_populates="document_links")
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])

    __table_args__ = (
        UniqueConstraint("document_id", "contact_id", "role", name="uq_doc_contact_role"),
    )

    def __repr__(self) -> str:
        return f"<DocumentContact doc={self.document_id} contact={self.contact_id} role={self.role}>"


class BusinessContact(Base):
    """
    Geschaeftskontakt mit automatischer Erkennung.

    Zentrales Model fuer alle Geschaeftskontakte mit:
    - Automatischer Erkennung aus Dokumenten (OCR)
    - Deduplizierung und Zusammenfuehrung
    - Umfangreichen Kontaktinformationen
    - Verknuepfung zu Dokumenten
    """
    __tablename__ = "business_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Basic identification
    name = Column(String(255), nullable=False, index=True)
    name_normalized = Column(String(255), nullable=True, index=True)  # Fuer Fuzzy-Matching
    contact_type = Column(String(20), nullable=False, default=ContactType.CUSTOMER.value)
    company_form = Column(String(50), nullable=True)  # GmbH, AG, etc.

    # Tax identifiers
    tax_id = Column(String(30), nullable=True)  # Steuernummer
    vat_id = Column(String(20), nullable=True, index=True)  # USt-IdNr
    registration_number = Column(String(50), nullable=True)  # HRB

    # Business numbers
    customer_number = Column(String(50), nullable=True, index=True)
    supplier_number = Column(String(50), nullable=True, index=True)

    # Address
    street = Column(String(255), nullable=True)
    house_number = Column(String(20), nullable=True)
    address_addition = Column(String(100), nullable=True)  # c/o, Gebaeude, etc.
    postal_code = Column(String(10), nullable=True, index=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), default="Deutschland")

    # Contact details
    email = Column(String(255), nullable=True, index=True)
    phone = Column(String(30), nullable=True)
    fax = Column(String(30), nullable=True)
    website = Column(String(255), nullable=True)

    # Banking
    bank_name = Column(String(100), nullable=True)
    iban = Column(String(34), nullable=True, index=True)
    bic = Column(String(11), nullable=True)

    # Additional data
    contact_persons = Column(CrossDBJSON, default=list)  # [{"name": "...", "role": "...", "email": "..."}]
    parent_company_id = Column(UUID(as_uuid=True), ForeignKey("business_contacts.id"), nullable=True)
    notes = Column(Text, nullable=True)
    tags = Column(CrossDBJSON, default=list)
    custom_fields = Column(CrossDBJSON, default=dict)

    # Ownership and source
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True)
    source = Column(String(50), default="manual")  # manual, ocr, import, api
    auto_detected = Column(Boolean, default=False)
    auto_detection_confidence = Column(Float, nullable=True)
    first_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    merged_into_id = Column(UUID(as_uuid=True), ForeignKey("business_contacts.id"), nullable=True)

    # Statistics (denormalized for performance)
    document_count = Column(Integer, default=0)
    total_invoice_amount = Column(Numeric(15, 2), default=0)
    last_document_date = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id], backref="business_contacts")
    company = relationship("Company", backref="business_contacts")
    first_document = relationship("Document", foreign_keys=[first_document_id])
    parent_company = relationship("BusinessContact", remote_side=[id], foreign_keys=[parent_company_id])
    merged_into = relationship("BusinessContact", remote_side=[id], foreign_keys=[merged_into_id])
    document_links = relationship("DocumentContact", back_populates="contact", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_business_contacts_owner_active", "owner_id", "is_active"),
        Index("ix_business_contacts_company_active", "company_id", "is_active"),
        Index("ix_business_contacts_name_normalized", "name_normalized"),
    )

    @hybrid_property
    def formatted_address(self) -> Optional[str]:
        """Formatierte Adresse."""
        parts = []
        if self.street:
            street_full = self.street
            if self.house_number:
                street_full += f" {self.house_number}"
            parts.append(street_full)
        if self.address_addition:
            parts.append(self.address_addition)
        if self.postal_code or self.city:
            location = f"{self.postal_code or ''} {self.city or ''}".strip()
            parts.append(location)
        if self.country and self.country != "Deutschland":
            parts.append(self.country)
        return ", ".join(parts) if parts else None

    @hybrid_property
    def display_name(self) -> str:
        """Anzeigename mit optionaler Rechtsform."""
        if self.company_form and self.company_form not in self.name:
            return f"{self.name} {self.company_form}"
        return self.name

    def __repr__(self) -> str:
        return f"<BusinessContact {self.name} ({self.contact_type})>"


# =============================================================================
# DATA LOSS PREVENTION (DLP) MODELS
# Enterprise Security: Policies, Audit, Access Control
# =============================================================================

class DLPActionType(str, Enum):
    """Moegliche DLP-Aktionen."""
    ALLOW = "allow"
    BLOCK = "block"
    WATERMARK = "watermark"
    NOTIFY = "notify"
    AUDIT_ONLY = "audit_only"


class SensitiveDataTypeEnum(str, Enum):
    """Typen sensibler Daten fuer DLP-Erkennung."""
    CREDIT_CARD = "credit_card"
    IBAN = "iban"
    SSN = "ssn"
    EMAIL = "email"
    PHONE = "phone"
    TAX_ID = "tax_id"
    DATE_OF_BIRTH = "date_of_birth"
    HEALTH_DATA = "health_data"
    FINANCIAL_DATA = "financial_data"


class DLPPolicyModel(Base):
    """
    DLP Policy Datenbank-Modell.

    Persistiert DLP-Policies in der Datenbank statt nur im Memory.
    Ermoeglicht Multi-Tenant Isolation und Audit-Trail.

    SECURITY:
    - Policies werden serverseitig validiert
    - company_id ist Pflichtfeld fuer Multi-Tenant Isolation
    - Alle Aenderungen werden im Audit-Log protokolliert
    """
    __tablename__ = "dlp_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Policy Identification
    policy_id = Column(String(64), nullable=False, index=True,
                       comment="Human-readable Policy-ID (z.B. 'confidential-docs')")
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    # Multi-Tenant (KRITISCH!)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung - PFLICHT fuer Isolation"
    )

    # Zugriffsbedingungen
    allowed_roles = Column(CrossDBJSON, default=["admin"],
                          comment="Rollen die Zugriff haben")
    blocked_roles = Column(CrossDBJSON, default=[],
                          comment="Rollen die explizit blockiert sind")

    # Zeit-basierte Einschraenkungen
    time_restrictions = Column(CrossDBJSON, nullable=True,
                              comment="{'start': '09:00', 'end': '18:00', 'weekdays': [0-6]}")

    # Dokument-Filter
    document_types = Column(CrossDBJSON, default=["all"],
                           comment="Betroffene Dokumenttypen")
    tags_required = Column(CrossDBJSON, default=[],
                          comment="Dokument muss diese Tags haben")
    tags_blocked = Column(CrossDBJSON, default=[],
                         comment="Dokument darf diese Tags nicht haben")

    # Aktionen
    action = Column(String(20), default=DLPActionType.ALLOW.value, nullable=False)
    require_watermark = Column(Boolean, default=False, nullable=False)
    watermark_config = Column(CrossDBJSON, nullable=True,
                             comment="Wasserzeichen-Konfiguration")

    # Benachrichtigungen
    notify_admin = Column(Boolean, default=False, nullable=False)
    notify_user = Column(Boolean, default=False, nullable=False)
    log_access = Column(Boolean, default=True, nullable=False)

    # Prioritaet (niedrigere Zahl = hoehere Prioritaet)
    priority = Column(Integer, default=100, nullable=False, index=True)

    # Audit
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="dlp_policies")
    created_by = relationship("User", backref="created_dlp_policies")

    __table_args__ = (
        UniqueConstraint("company_id", "policy_id", name="uq_dlp_policy_company_id"),
        Index("ix_dlp_policies_company_enabled", "company_id", "enabled"),
        Index("ix_dlp_policies_company_priority", "company_id", "priority"),
        {"comment": "DLP Policies fuer Enterprise Security"}
    )

    def __repr__(self) -> str:
        return f"<DLPPolicy {self.policy_id} ({self.action})>"


class DLPAuditLog(Base):
    """
    DLP-spezifisches Audit-Log.

    Protokolliert alle DLP-relevanten Events:
    - Zugriffspruefungen (erlaubt/blockiert)
    - Policy-Aenderungen
    - Wasserzeichen-Anwendung
    - Sensible Daten gefunden

    SECURITY:
    - Keine sensiblen Daten werden geloggt (nur Typen und Counts)
    - Immutable (nur INSERT erlaubt)
    - company_id fuer Multi-Tenant Isolation
    """
    __tablename__ = "dlp_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Event-Kontext
    event_type = Column(String(50), nullable=False, index=True,
                       comment="access_check, policy_change, watermark_applied, sensitive_data_found")
    action_type = Column(String(20), nullable=True,
                        comment="download, view, print, export")

    # Ergebnis
    result = Column(String(20), nullable=False,
                   comment="allowed, blocked, watermarked, notified")
    reason = Column(String(500), nullable=True)

    # Betroffene Entities
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True, index=True)
    policy_id = Column(UUID(as_uuid=True), ForeignKey("dlp_policies.id", ondelete="SET NULL"), nullable=True)

    # Multi-Tenant (KRITISCH!)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung - PFLICHT"
    )

    # Sensitive Data Info (NUR Typen und Counts, KEINE Werte!)
    sensitive_data_types = Column(CrossDBJSON, nullable=True,
                                  comment="{'credit_card': 2, 'iban': 1} - NUR Counts!")

    # Request-Kontext
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)

    # Metadata (HINWEIS: 'metadata' ist SQLAlchemy reserviert!)
    log_metadata = Column(CrossDBJSON, default=dict)

    # Timestamp (immutable)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", backref="dlp_audit_logs")
    document = relationship("Document", backref="dlp_audit_logs")
    policy = relationship("DLPPolicyModel", backref="audit_logs")
    company = relationship("Company", backref="dlp_audit_logs")

    __table_args__ = (
        Index("ix_dlp_audit_company_created", "company_id", "created_at"),
        Index("ix_dlp_audit_company_event", "company_id", "event_type"),
        Index("ix_dlp_audit_user_created", "user_id", "created_at"),
        Index("ix_dlp_audit_document", "document_id"),
        {"comment": "DLP Audit-Log fuer Compliance und Forensik"}
    )

    def __repr__(self) -> str:
        return f"<DLPAuditLog {self.event_type} ({self.result}) at {self.created_at}>"


# =============================================================================
# BPMN Process Engine Models - Enums
# =============================================================================
# NOTE: The BPMN table models are in app/db/models/bpmn.py but due to Python
# module resolution (models.py takes precedence over models/), we define the
# enums here and the table models import Base from here.


class ProcessStatus(str, Enum):
    """Status eines BPMN Prozess-Instances."""
    CREATED = "created"          # Erstellt, noch nicht gestartet
    RUNNING = "running"          # Läuft aktuell
    SUSPENDED = "suspended"      # Pausiert (z.B. wegen Timer)
    COMPLETED = "completed"      # Erfolgreich abgeschlossen
    TERMINATED = "terminated"    # Manuell abgebrochen
    FAILED = "failed"            # Fehlgeschlagen


class BpmnTaskStatus(str, Enum):
    """Status eines BPMN Tasks (unterscheidet sich von TaskStatus)."""
    PENDING = "pending"          # Wartet auf Aktivierung
    ACTIVE = "active"            # Bereit zur Bearbeitung
    ASSIGNED = "assigned"        # Benutzer zugewiesen
    IN_PROGRESS = "in_progress"  # In Bearbeitung
    COMPLETED = "completed"      # Abgeschlossen
    FAILED = "failed"            # Fehlgeschlagen
    SKIPPED = "skipped"          # Übersprungen (z.B. Gateway)
    ESCALATED = "escalated"      # Eskaliert


class TaskType(str, Enum):
    """BPMN Task-Typen."""
    USER_TASK = "user_task"              # Manuelle Aufgabe
    SERVICE_TASK = "service_task"        # Automatische Aufgabe
    SCRIPT_TASK = "script_task"          # Script-Ausführung
    SEND_TASK = "send_task"              # Nachricht senden
    RECEIVE_TASK = "receive_task"        # Nachricht empfangen
    MANUAL_TASK = "manual_task"          # Reine manuelle Aufgabe
    BUSINESS_RULE_TASK = "business_rule" # DMN-Entscheidung
    CALL_ACTIVITY = "call_activity"      # Subprocess aufrufen


class GatewayType(str, Enum):
    """BPMN Gateway-Typen."""
    EXCLUSIVE = "exclusive"      # XOR - Nur ein Pfad
    PARALLEL = "parallel"        # AND - Alle Pfade
    INCLUSIVE = "inclusive"      # OR - Ein oder mehrere Pfade
    EVENT_BASED = "event_based"  # Basierend auf Events


class EventType(str, Enum):
    """BPMN Event-Typen."""
    START = "start"
    END = "end"
    INTERMEDIATE_CATCH = "intermediate_catch"
    INTERMEDIATE_THROW = "intermediate_throw"
    BOUNDARY = "boundary"


class EventTrigger(str, Enum):
    """BPMN Event-Trigger."""
    NONE = "none"
    TIMER = "timer"
    MESSAGE = "message"
    SIGNAL = "signal"
    ERROR = "error"
    ESCALATION = "escalation"
    CONDITIONAL = "conditional"
    COMPENSATION = "compensation"


# Verfuegbare BPMN Modelle in app/db/models/bpmn.py:
# - ProcessDefinition, ProcessInstance, ProcessTask
# - ProcessHistory, ProcessTimerJob, ProcessVariableHistory


# =============================================================================
# GDPR Consent Management Models - Phase 7
# =============================================================================


class GDPRConsentVersion(Base):
    """Versionierte Consent-Texte fuer DSGVO-konforme Einwilligungen.

    Speichert verschiedene Versionen von Einwilligungstexten mit SHA-256 Hash
    zur Nachweisbarkeit welchen Text der User akzeptiert hat.
    """
    __tablename__ = "gdpr_consent_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Scope und Version
    scope = Column(String(100), nullable=False, index=True,
                   comment="Consent-Scope (personal_data, financial_data, etc.)")
    version = Column(String(50), nullable=False,
                     comment="Versionsnummer z.B. '1.0', '2.0'")

    # Consent-Text
    title = Column(String(255), nullable=False,
                   comment="Titel der Einwilligung")
    description = Column(Text, nullable=False,
                         comment="Kurzbeschreibung")
    full_text = Column(Text, nullable=False,
                       comment="Vollstaendiger Consent-Text")
    text_hash = Column(String(64), nullable=False, index=True,
                       comment="SHA-256 Hash des Textes")

    # Sprache und Status
    language = Column(String(10), nullable=False, default="de",
                      comment="Sprachcode (de, en, etc.)")
    is_active = Column(Boolean, nullable=False, default=True, index=True,
                       comment="Aktive Version fuer diesen Scope")

    # Gueltigkeit
    effective_from = Column(DateTime(timezone=True), nullable=False,
                            default=func.now(),
                            comment="Ab wann gueltig")
    effective_until = Column(DateTime(timezone=True), nullable=True,
                             comment="Bis wann gueltig (NULL = unbegrenzt)")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="SET NULL"),
                           nullable=True)

    # Relationships
    created_by = relationship("User", backref="created_consent_versions")
    consent_scopes = relationship("GDPRConsentScope", back_populates="consent_version")

    __table_args__ = (
        UniqueConstraint("scope", "version", name="uq_gdpr_consent_versions_scope_version"),
        Index("ix_gdpr_consent_versions_scope_active", "scope", "is_active",
              postgresql_where=text("is_active = true")),
        {"comment": "Versionierte DSGVO Consent-Texte"}
    )

    def __repr__(self) -> str:
        return f"<GDPRConsentVersion {self.scope} v{self.version}>"


class GDPRConsentScope(Base):
    """Granulare Einwilligungen pro User und Scope.

    Speichert fuer jeden User welche Einwilligungen erteilt oder
    widerrufen wurden, mit vollstaendigem Audit-Trail.
    """
    __tablename__ = "gdpr_consent_scopes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # User und Company
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=True, index=True,
                        comment="Optional fuer company-spezifische Consents")

    # Scope und Status
    scope = Column(String(100), nullable=False, index=True,
                   comment="personal_data, financial_data, analytics, marketing, etc.")
    consent_given = Column(Boolean, nullable=False, default=False,
                           comment="True wenn Einwilligung erteilt")

    # Referenz auf akzeptierte Version
    consent_version_id = Column(UUID(as_uuid=True),
                                ForeignKey("gdpr_consent_versions.id", ondelete="SET NULL"),
                                nullable=True)
    consent_text_hash = Column(String(64), nullable=True,
                               comment="SHA-256 des akzeptierten Textes")

    # Zeitstempel
    granted_at = Column(DateTime(timezone=True), nullable=True,
                        comment="Wann erteilt")
    withdrawn_at = Column(DateTime(timezone=True), nullable=True,
                          comment="Wann widerrufen")
    valid_from = Column(DateTime(timezone=True), nullable=False,
                        default=func.now())
    valid_until = Column(DateTime(timezone=True), nullable=True,
                         comment="Ablaufdatum der Einwilligung")

    # Einwilligungsmethode
    consent_method = Column(String(50), nullable=True,
                            comment="web_form, api, paper, verbal, double_opt_in")
    ip_address = Column(String(45), nullable=True,
                        comment="IPv4/IPv6 bei Erteilung")
    user_agent = Column(String(500), nullable=True,
                        comment="Browser User-Agent")

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    user = relationship("User", backref="gdpr_consent_scopes")
    company = relationship("Company", backref="company_gdpr_consent_scopes")
    consent_version = relationship("GDPRConsentVersion", back_populates="consent_scopes")
    history = relationship("GDPRConsentHistory", back_populates="consent_scope",
                           order_by="desc(GDPRConsentHistory.created_at)")

    __table_args__ = (
        Index("ix_gdpr_consent_scopes_user_scope_active", "user_id", "scope",
              postgresql_where=text("withdrawn_at IS NULL")),
        {"comment": "Granulare DSGVO Einwilligungen pro User/Scope"}
    )

    def __repr__(self) -> str:
        status = "granted" if self.consent_given and not self.withdrawn_at else "withdrawn"
        return f"<GDPRConsentScope {self.scope} ({status})>"


class GDPRDataSubjectRequest(Base):
    """Betroffenenrechte-Anfragen nach DSGVO Art. 15-21.

    Trackt Anfragen von Betroffenen zu:
    - Art. 15: Auskunftsrecht
    - Art. 16: Recht auf Berichtigung
    - Art. 17: Recht auf Loeschung
    - Art. 18: Recht auf Einschraenkung
    - Art. 20: Recht auf Datenuebertragbarkeit
    - Art. 21: Widerspruchsrecht
    """
    __tablename__ = "gdpr_data_subject_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Betroffener
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="SET NULL"),
                        nullable=True, index=True)

    # Anfragetyp (Art. 15-21 DSGVO)
    request_type = Column(String(50), nullable=False, index=True,
                          comment="access, erasure, rectification, portability, restriction, objection")
    status = Column(String(50), nullable=False, default="pending", index=True,
                    comment="pending, in_progress, completed, rejected, cancelled")

    # Antragsdaten
    requester_email = Column(String(255), nullable=False,
                             comment="Email des Antragstellers")
    requester_name = Column(String(255), nullable=True)
    verification_token = Column(String(255), nullable=True,
                                comment="Token zur Verifizierung der Identitaet")
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Details
    description = Column(Text, nullable=True,
                         comment="Beschreibung der Anfrage")
    affected_data_categories = Column(CrossDBJSON, nullable=True,
                                      comment='["personal", "financial", "documents"]')
    rectification_details = Column(CrossDBJSON, nullable=True,
                                   comment="Details fuer Art. 16 Berichtigung")

    # Bearbeitung
    assigned_to_id = Column(UUID(as_uuid=True),
                            ForeignKey("users.id", ondelete="SET NULL"),
                            nullable=True)
    response_notes = Column(Text, nullable=True,
                            comment="Interne Notizen zur Bearbeitung")
    rejection_reason = Column(Text, nullable=True,
                              comment="Grund bei Ablehnung")

    # Ergebnis
    export_file_path = Column(String(500), nullable=True,
                              comment="Pfad zum Export bei Portabilitaet")
    export_format = Column(String(20), nullable=True,
                           comment="json, csv, xml")

    # Zeitstempel (DSGVO: 30 Tage Frist!)
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    due_date = Column(DateTime(timezone=True), nullable=False,
                      comment="Frist: requested_at + 30 Tage")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="dsr_requests")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id],
                               backref="assigned_dsr_requests")
    company = relationship("Company", backref="dsr_requests")
    exports = relationship("GDPRDataExport", back_populates="request")

    __table_args__ = (
        Index("ix_gdpr_dsr_pending_overdue", "due_date", "status",
              postgresql_where=text("status IN ('pending', 'in_progress')")),
        {"comment": "DSGVO Betroffenenrechte-Anfragen (Art. 15-21)"}
    )

    def __repr__(self) -> str:
        return f"<GDPRDataSubjectRequest {self.request_type} ({self.status})>"


class GDPRDataExport(Base):
    """Datenexport-Logs fuer DSGVO Art. 20 Portabilitaet.

    Trackt alle Datenexporte die im Rahmen von Betroffenenrechte-Anfragen
    oder auf Userwunsch erstellt wurden.
    """
    __tablename__ = "gdpr_data_exports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Betroffener
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)
    company_id = Column(UUID(as_uuid=True),
                        ForeignKey("companies.id", ondelete="SET NULL"),
                        nullable=True, index=True)
    request_id = Column(UUID(as_uuid=True),
                        ForeignKey("gdpr_data_subject_requests.id", ondelete="SET NULL"),
                        nullable=True, index=True,
                        comment="Referenz auf DSR falls vorhanden")

    # Export-Details
    export_type = Column(String(50), nullable=False,
                         comment="full, partial, category")
    data_categories = Column(CrossDBJSON, nullable=False,
                             comment='["documents", "comments", "settings"]')
    format = Column(String(20), nullable=False, default="json",
                    comment="json, csv, xml")

    # Datei
    file_path = Column(String(500), nullable=True,
                       comment="Pfad zur Export-Datei")
    file_size_bytes = Column(BigInteger, nullable=True)
    file_hash = Column(String(64), nullable=True,
                       comment="SHA-256 der Export-Datei")

    # Status
    status = Column(String(50), nullable=False, default="pending", index=True,
                    comment="pending, processing, completed, failed, expired, downloaded")
    error_message = Column(Text, nullable=True)

    # Download-Tracking
    download_count = Column(Integer, nullable=False, default=0)
    last_downloaded_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False,
                        comment="Export verfaellt nach 7 Tagen")

    # Zeitstempel
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="gdpr_exports")
    company = relationship("Company", backref="gdpr_exports")
    request = relationship("GDPRDataSubjectRequest", back_populates="exports")

    __table_args__ = (
        Index("ix_gdpr_exports_expired", "expires_at", "status",
              postgresql_where=text("status = 'completed'")),
        {"comment": "DSGVO Datenexport-Logs (Art. 20 Portabilitaet)"}
    )

    def __repr__(self) -> str:
        return f"<GDPRDataExport {self.export_type} ({self.status})>"


class GDPRConsentHistory(Base):
    """Audit-Trail fuer Einwilligungsaenderungen.

    Dokumentiert jede Aenderung an Einwilligungen fuer
    vollstaendige Nachweisbarkeit (DSGVO Art. 7).
    """
    __tablename__ = "gdpr_consent_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    consent_scope_id = Column(UUID(as_uuid=True),
                              ForeignKey("gdpr_consent_scopes.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True),
                     ForeignKey("users.id", ondelete="SET NULL"),
                     nullable=True, index=True)

    # Aenderung
    action = Column(String(50), nullable=False, index=True,
                    comment="granted, withdrawn, updated, expired, version_changed")
    previous_value = Column(Boolean, nullable=True,
                            comment="Vorheriger Consent-Status")
    new_value = Column(Boolean, nullable=False,
                       comment="Neuer Consent-Status")
    consent_version_id = Column(UUID(as_uuid=True),
                                ForeignKey("gdpr_consent_versions.id", ondelete="SET NULL"),
                                nullable=True)

    # Kontext
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)
    reason = Column(Text, nullable=True,
                    comment="Grund bei Widerruf")

    # Timestamp (immutable)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    consent_scope = relationship("GDPRConsentScope", back_populates="history")
    user = relationship("User", backref="consent_history")
    consent_version = relationship("GDPRConsentVersion", backref="history_entries")

    __table_args__ = (
        Index("ix_gdpr_consent_history_created_at", "created_at"),
        {"comment": "Audit-Trail fuer DSGVO Einwilligungsaenderungen"}
    )

    def __repr__(self) -> str:
        return f"<GDPRConsentHistory {self.action} at {self.created_at}>"


# ============================================================================
# SAVED FILTERS - Server-side Filter Persistence with Sharing
# Phase 4.5: Frontend UX Enhancement
# ============================================================================

class SavedFilter(Base):
    """Gespeicherte Filter fuer Server-seitige Persistenz mit Sharing.

    Ersetzt die LocalStorage-basierte Implementierung durch eine
    persistente Loesung mit Multi-Tenant-Isolation und Sharing-Option.

    Features:
    - Pro Feature (documents, invoices, entities, transactions)
    - Sharing innerhalb einer Company
    - Default-Filter pro User
    - Usage-Tracking fuer Sortierung nach Haeufigkeit

    Usage:
        # Eigene Filter
        filters = db.query(SavedFilter).filter(
            SavedFilter.user_id == current_user.id,
            SavedFilter.feature == "documents"
        ).all()

        # Geteilte Filter der Company
        shared = db.query(SavedFilter).filter(
            SavedFilter.company_id == current_user.company_id,
            SavedFilter.is_shared == True,
            SavedFilter.feature == "documents"
        ).all()
    """
    __tablename__ = "saved_filters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Owner and tenant
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Feature this filter applies to
    feature = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Feature scope: documents, invoices, entities, transactions, etc."
    )

    # Filter configuration as JSONB
    filter_config = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment="Flexible filter config: {status: [], tags: [], dateRange: {}, search: ''}"
    )

    # Sharing and default settings
    is_shared = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="If true, visible to all users in the same company"
    )
    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="If true, auto-applied when opening the feature"
    )

    # Usage tracking for sorting by popularity/recency
    use_count = Column(Integer, nullable=False, default=0)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Soft delete
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", backref="saved_filters")
    company = relationship("Company", backref="saved_filters")

    __table_args__ = (
        Index("ix_saved_filters_user_feature", "user_id", "feature", "deleted_at"),
        Index("ix_saved_filters_company_shared", "company_id", "feature", "is_shared", "deleted_at"),
        {"comment": "Server-side saved filters with sharing support"}
    )

    def __repr__(self) -> str:
        return f"<SavedFilter {self.name} ({self.feature})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "feature": self.feature,
            "filter_config": self.filter_config,
            "is_shared": self.is_shared,
            "is_default": self.is_default,
            "use_count": self.use_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_own": True,  # Will be set by service
        }


# ============================================================================
# APP CONFIG - Key-Value Store for Application Configuration
# Used by MLOps, OCR Self-Learning, and other system-wide settings
# ============================================================================

class AppConfig(Base):
    """System-weite Konfigurationsspeicherung als Key-Value Store.

    Flexibler JSONB-basierter Speicher fuer:
    - MLOps Model Registry
    - OCR Confidence Adjustments
    - Feature Flags
    - System-weite Einstellungen

    Usage:
        # Speichern
        config = AppConfig(
            key="mlops_model_registry",
            value={"deepseek": [...], "got_ocr": [...]},
            description="MLOps Model Versioning"
        )
        db.add(config)

        # Laden
        config = await db.execute(
            select(AppConfig).where(AppConfig.key == "mlops_model_registry")
        )
        registry = config.scalar_one_or_none()
    """
    __tablename__ = "app_config"

    key = Column(
        String(255),
        primary_key=True,
        nullable=False,
        comment="Eindeutiger Schluessel fuer die Konfiguration"
    )
    value = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment="JSONB-Wert der Konfiguration"
    )
    description = Column(
        Text,
        nullable=True,
        comment="Beschreibung der Konfiguration"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    __table_args__ = (
        {"comment": "System-weite Konfiguration als Key-Value Store"}
    )

    def __repr__(self) -> str:
        return f"<AppConfig key={self.key}>"


# =============================================================================
# DPIA (Data Protection Impact Assessment) Models
# =============================================================================


class DPIAStatus(str, Enum):
    """DPIA Status enum."""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DPIARiskLevel(str, Enum):
    """DPIA Risk Level enum."""
    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    MINIMAL = "minimal"


class DPIALegalBasis(str, Enum):
    """DPIA Legal Basis enum (Art. 6 DSGVO)."""
    CONSENT = "consent"
    CONTRACT = "contract"
    LEGAL_OBLIGATION = "legal_obligation"
    VITAL_INTERESTS = "vital_interests"
    PUBLIC_INTEREST = "public_interest"
    LEGITIMATE_INTEREST = "legitimate_interest"


class DPIAMeasureType(str, Enum):
    """DPIA Mitigation Measure Type enum."""
    TECHNICAL = "technical"
    ORGANIZATIONAL = "organizational"
    CONTRACTUAL = "contractual"
    LEGAL = "legal"


class DPIAImplementationStatus(str, Enum):
    """DPIA Implementation Status enum."""
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    IMPLEMENTED = "implemented"


class DPIA(Base):
    """
    Data Protection Impact Assessment (Art. 35 DSGVO).

    Vollstaendige DPIA-Dokumentation mit Risikobewertung,
    Massnahmen und DPO-Konsultation.
    """
    __tablename__ = "dpias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    version = Column(String(20), nullable=False, default="1.0")
    status = Column(
        String(20),
        nullable=False,
        default=DPIAStatus.DRAFT.value
    )

    # Verantwortlichkeiten
    controller_name = Column(String(255), nullable=False)
    controller_contact = Column(String(255), nullable=True)
    dpo_name = Column(String(255), nullable=False)
    dpo_contact = Column(String(255), nullable=True)
    assessment_date = Column(DateTime(timezone=True), nullable=True)
    assessor_name = Column(String(255), nullable=True)

    # Bewertungen
    necessity_assessment = Column(Text, nullable=True)
    proportionality_assessment = Column(Text, nullable=True)
    overall_risk_level = Column(
        String(20),
        nullable=True,
        default=DPIARiskLevel.MEDIUM.value
    )

    # Aufsichtsbehoerde
    supervisory_authority_consultation = Column(Boolean, default=False)
    supervisory_authority_response = Column(Text, nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="dpias")
    created_by = relationship("User", foreign_keys=[created_by_id])
    processing_operations = relationship(
        "DPIAProcessingOperation",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    data_subject_groups = relationship(
        "DPIADataSubjectGroup",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    risks = relationship(
        "DPIARisk",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    mitigation_measures = relationship(
        "DPIAMitigationMeasure",
        back_populates="dpia",
        cascade="all, delete-orphan"
    )
    consultation = relationship(
        "DPIAConsultation",
        back_populates="dpia",
        uselist=False,
        cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "DPIAAuditLog",
        back_populates="dpia",
        cascade="all, delete-orphan",
        order_by="desc(DPIAAuditLog.created_at)"
    )

    __table_args__ = (
        Index("ix_dpias_company_status", "company_id", "status"),
        {"comment": "Data Protection Impact Assessments (Art. 35 DSGVO)"}
    )

    def __repr__(self) -> str:
        return f"<DPIA {self.id} title={self.title} status={self.status}>"


class DPIAProcessingOperation(Base):
    """Verarbeitungstaetigkeit innerhalb einer DPIA."""
    __tablename__ = "dpia_processing_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    purpose = Column(Text, nullable=True)
    legal_basis = Column(String(50), nullable=True)
    data_categories = Column(CrossDBJSON, default=list)  # Array of strings
    retention_period = Column(String(255), nullable=True)
    automated_decision_making = Column(Boolean, default=False)
    profiling = Column(Boolean, default=False)
    data_transfer_outside_eu = Column(Boolean, default=False)
    transfer_countries = Column(CrossDBJSON, default=list)  # Array of strings
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    dpia = relationship("DPIA", back_populates="processing_operations")

    def __repr__(self) -> str:
        return f"<DPIAProcessingOperation {self.id} name={self.name}>"


class DPIADataSubjectGroup(Base):
    """Betroffenengruppe innerhalb einer DPIA."""
    __tablename__ = "dpia_data_subject_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    estimated_count = Column(Integer, nullable=True)
    includes_vulnerable = Column(Boolean, default=False)
    includes_children = Column(Boolean, default=False)

    # Relationship
    dpia = relationship("DPIA", back_populates="data_subject_groups")

    def __repr__(self) -> str:
        return f"<DPIADataSubjectGroup {self.id} name={self.name}>"


class DPIARisk(Base):
    """Risikobewertung innerhalb einer DPIA."""
    __tablename__ = "dpia_risks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    risk_id = Column(String(50), nullable=False)  # e.g., R1, R2
    description = Column(Text, nullable=False)
    affected_rights = Column(CrossDBJSON, default=list)  # Array of strings
    likelihood = Column(Integer, nullable=False)  # 1-5
    impact = Column(Integer, nullable=False)  # 1-5
    inherent_risk = Column(String(20), nullable=True)
    residual_risk = Column(String(20), nullable=True)
    mitigation_measures = Column(CrossDBJSON, default=list)  # Array of measure IDs

    # Relationship
    dpia = relationship("DPIA", back_populates="risks")

    @property
    def risk_score(self) -> int:
        """Berechne Risiko-Score (1-25)."""
        return self.likelihood * self.impact

    def __repr__(self) -> str:
        return f"<DPIARisk {self.id} risk_id={self.risk_id}>"


class DPIAMitigationMeasure(Base):
    """Risikominderungsmassnahme innerhalb einer DPIA."""
    __tablename__ = "dpia_mitigation_measures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    measure_id = Column(String(50), nullable=False)  # e.g., M1, M2
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    measure_type = Column(String(30), nullable=True)
    addresses_risks = Column(CrossDBJSON, default=list)  # Array of risk IDs
    implementation_status = Column(
        String(30),
        default=DPIAImplementationStatus.PLANNED.value
    )
    responsible_person = Column(String(255), nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    effectiveness = Column(Text, nullable=True)

    # Relationship
    dpia = relationship("DPIA", back_populates="mitigation_measures")

    def __repr__(self) -> str:
        return f"<DPIAMitigationMeasure {self.id} measure_id={self.measure_id}>"


class DPIAConsultation(Base):
    """DPO-Konsultation zu einer DPIA."""
    __tablename__ = "dpia_consultations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        unique=True  # One consultation per DPIA
    )
    dpo_name = Column(String(255), nullable=False)
    consultation_date = Column(DateTime(timezone=True), nullable=False)
    opinion = Column(Text, nullable=True)
    recommendations = Column(CrossDBJSON, default=list)  # Array of strings
    approval = Column(Boolean, nullable=False)
    conditions = Column(CrossDBJSON, default=list)  # Array of strings

    # Relationship
    dpia = relationship("DPIA", back_populates="consultation")

    def __repr__(self) -> str:
        return f"<DPIAConsultation {self.id} approval={self.approval}>"


class DPIAAuditLog(Base):
    """Audit-Trail fuer DPIA-Aenderungen."""
    __tablename__ = "dpia_audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dpia_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dpias.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    action = Column(String(50), nullable=False)
    user_name = Column(String(255), nullable=True)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    dpia = relationship("DPIA", back_populates="audit_logs")

    def __repr__(self) -> str:
        return f"<DPIAAuditLog {self.id} action={self.action}>"


# ============================================================================
# ZERO-TOUCH OCR MODELS (Feature 1 - Phase 1)
# ============================================================================

class ZeroTouchResult(Base):
    """Zero-Touch OCR Ergebnis - Automatische Dokumentverarbeitung."""
    __tablename__ = "zero_touch_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Confidence scores
    ocr_confidence = Column(Float, nullable=True)
    classification_type = Column(String(50), nullable=True)
    classification_confidence = Column(Float, default=0.0)
    extraction_confidence = Column(Float, default=0.0)
    extracted_fields = Column(CrossDBJSON, default=dict)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True
    )
    entity_confidence = Column(Float, nullable=True)
    overall_confidence = Column(Float, default=0.0)

    # Processing flags
    auto_processed = Column(Boolean, default=False)
    requires_review = Column(Boolean, default=True)
    review_completed = Column(Boolean, default=False)
    reviewed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Business object
    business_object_type = Column(String(50), nullable=True)
    business_object_id = Column(UUID(as_uuid=True), nullable=True)

    # Performance
    total_processing_ms = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="zero_touch_result")
    company = relationship("Company", backref="zero_touch_results")
    entity = relationship("BusinessEntity", backref="zero_touch_results")
    reviewed_by = relationship("User", backref="zero_touch_reviews")

    __table_args__ = (
        Index("ix_zero_touch_company_created", "company_id", "created_at"),
        Index(
            "ix_zero_touch_auto_processed",
            "company_id", "auto_processed",
            postgresql_where=text("auto_processed = true"),
        ),
        Index(
            "ix_zero_touch_requires_review",
            "company_id", "requires_review",
            postgresql_where=text("requires_review = true AND review_completed = false"),
        ),
    )

    def __repr__(self) -> str:
        return f"<ZeroTouchResult {self.id} confidence={self.overall_confidence} auto={self.auto_processed}>"


# ============================================================================
# NLQ 2.0 MODELS (Feature 2 - Phase 1)
# ============================================================================

class NLQQueryLog(Base):
    """Natural Language Query Log - Protokollierung von NLQ-Abfragen."""
    __tablename__ = "nlq_query_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Query data
    natural_query = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=True)
    sanitized_sql = Column(Text, nullable=True)
    query_intent = Column(String(100), nullable=True)

    # Execution
    execution_time_ms = Column(Integer, default=0)
    result_count = Column(Integer, default=0)
    was_cached = Column(Boolean, default=False)
    error_message = Column(Text, nullable=True)

    # Visualization
    visualization_type = Column(String(50), nullable=True)  # bar, line, pie, table, kpi
    visualization_config = Column(CrossDBJSON, default=dict)

    # Feedback
    feedback_rating = Column(Integer, nullable=True)  # 1-5
    feedback_comment = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="nlq_queries")
    company = relationship("Company", backref="nlq_queries")

    __table_args__ = (
        Index("ix_nlq_queries_company_created", "company_id", "created_at"),
        Index("ix_nlq_queries_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<NLQQueryLog {self.id} intent={self.query_intent}>"


# ============================================================================
# SMART INBOX MODELS (Feature 3 - Phase 1)
# ============================================================================

class SmartInboxItemSource(str, Enum):
    """Quelle eines Smart Inbox Items."""
    VALIDATION_QUEUE = "validation_queue"
    ALERT = "alert"
    DEADLINE = "deadline"
    OCR_RESULT = "ocr_result"
    TASK = "task"
    APPROVAL = "approval"
    INVOICE = "invoice"
    WORKFLOW = "workflow"


class SmartInboxItemStatus(str, Enum):
    """Status eines Smart Inbox Items."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"
    SNOOZED = "snoozed"


class SmartInboxItem(Base):
    """Smart Inbox Item - KI-priorisierte Aufgabe."""
    __tablename__ = "smart_inbox_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Source
    source_type = Column(String(50), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=True)

    # Content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)

    # Priority
    raw_priority = Column(Float, default=50.0)
    ml_priority = Column(Float, default=50.0)
    urgency_score = Column(Float, default=0.0)
    importance_score = Column(Float, default=0.0)

    # Status
    status = Column(String(20), default=SmartInboxItemStatus.PENDING)
    deadline = Column(DateTime(timezone=True), nullable=True)
    snoozed_until = Column(DateTime(timezone=True), nullable=True)

    # Actions
    recommended_actions = Column(CrossDBJSON, default=list)
    completed_action = Column(String(100), nullable=True)

    # Context
    context_data = Column(CrossDBJSON, default=dict)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="smart_inbox_items")
    company = relationship("Company", backref="smart_inbox_items")
    document = relationship("Document", backref="smart_inbox_items")
    entity = relationship("BusinessEntity", backref="smart_inbox_items")

    __table_args__ = (
        Index("ix_smart_inbox_user_status", "user_id", "status"),
        Index("ix_smart_inbox_company_created", "company_id", "created_at"),
        Index(
            "ix_smart_inbox_pending_priority",
            "user_id", "ml_priority",
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_smart_inbox_snoozed",
            "user_id", "snoozed_until",
            postgresql_where=text("status = 'snoozed'"),
        ),
    )

    def __repr__(self) -> str:
        return f"<SmartInboxItem {self.id} priority={self.ml_priority} status={self.status}>"


class UserBehaviorLog(Base):
    """User Behavior Log - Lerndaten fuer ML-Priorisierung."""
    __tablename__ = "user_behavior_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Reference
    inbox_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("smart_inbox_items.id", ondelete="CASCADE"),
        nullable=True
    )

    # Behavior
    action = Column(String(50), nullable=False)  # viewed, clicked, dismissed, completed, snoozed
    source_type = Column(String(50), nullable=True)
    time_spent_ms = Column(Integer, default=0)
    context_page = Column(String(200), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="behavior_logs")
    company = relationship("Company", backref="behavior_logs")
    inbox_item = relationship("SmartInboxItem", backref="behavior_logs")

    __table_args__ = (
        Index("ix_behavior_logs_user_created", "user_id", "created_at"),
        Index("ix_behavior_logs_company_created", "company_id", "created_at"),
        Index("ix_behavior_logs_item", "inbox_item_id"),
    )

    def __repr__(self) -> str:
        return f"<UserBehaviorLog {self.id} action={self.action}>"


# ============================================================================
# CEO DASHBOARD MODELS (Feature 4 - Phase 2)
# ============================================================================

class CompanyHealthSnapshot(Base):
    """Taeglicher Gesundheits-Snapshot eines Unternehmens."""
    __tablename__ = "company_health_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    snapshot_date = Column(Date, nullable=False)

    # Health scores (0-100)
    health_score_overall = Column(Float, default=0.0)
    health_score_financial = Column(Float, default=0.0)
    health_score_operations = Column(Float, default=0.0)
    health_score_risk = Column(Float, default=0.0)
    health_score_compliance = Column(Float, default=0.0)

    # KPIs
    documents_count = Column(Integer, default=0)
    invoices_pending = Column(Integer, default=0)
    invoices_overdue = Column(Integer, default=0)
    pending_amount = Column(Numeric(12, 2), default=0)
    overdue_amount = Column(Numeric(12, 2), default=0)
    auto_process_rate = Column(Float, default=0.0)
    active_alerts = Column(Integer, default=0)
    critical_alerts = Column(Integer, default=0)

    # Additional metrics
    metrics_data = Column(CrossDBJSON, default=dict)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="health_snapshots")

    __table_args__ = (
        UniqueConstraint("company_id", "snapshot_date", name="uq_health_snapshot_company_date"),
        Index("ix_health_snapshot_company_date", "company_id", "snapshot_date"),
    )

    def __repr__(self) -> str:
        return f"<CompanyHealthSnapshot {self.snapshot_date} score={self.health_score_overall}>"


# ============================================================================
# KNOWLEDGE GRAPH MODELS (Feature 5 - Phase 2)
# ============================================================================

class GraphEdge(Base):
    """Knowledge Graph Kante - Beziehung zwischen Entitaeten."""
    __tablename__ = "graph_edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Source node
    source_type = Column(String(50), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)

    # Target node
    target_type = Column(String(50), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)

    # Edge metadata
    edge_type = Column(String(50), nullable=False)
    properties = Column(CrossDBJSON, default=dict)
    weight = Column(Float, default=1.0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="graph_edges")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "source_type", "source_id",
            "target_type", "target_id", "edge_type",
            name="uq_graph_edge_unique"
        ),
        Index("ix_graph_edges_source", "company_id", "source_type", "source_id"),
        Index("ix_graph_edges_target", "company_id", "target_type", "target_id"),
        Index("ix_graph_edges_type", "company_id", "edge_type"),
    )

    def __repr__(self) -> str:
        return f"<GraphEdge {self.source_type}:{self.source_id} -[{self.edge_type}]-> {self.target_type}:{self.target_id}>"


# ============================================================================
# MERKLE TREE AUDIT MODELS (Feature 6 - Phase 2)
# ============================================================================

class MerkleTreeNode(Base):
    """Merkle Tree Knoten fuer kryptografischen Audit-Trail."""
    __tablename__ = "merkle_tree_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tree identification
    tree_id = Column(String(100), nullable=False)
    level = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False)

    # Hash data
    hash_value = Column(String(64), nullable=False)
    left_child_hash = Column(String(64), nullable=True)
    right_child_hash = Column(String(64), nullable=True)

    # Statistics
    entry_count = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="merkle_tree_nodes")

    __table_args__ = (
        UniqueConstraint("company_id", "tree_id", "level", "position", name="uq_merkle_node"),
        Index("ix_merkle_tree_id", "company_id", "tree_id", "level", "position"),
    )

    def __repr__(self) -> str:
        return f"<MerkleTreeNode tree={self.tree_id} level={self.level} pos={self.position}>"


# ============================================================================
# AI ETHICS MODELS (Feature 7 - Phase 2)
# ============================================================================

class AIEthicsAudit(Base):
    """KI-Ethik Audit - Protokollierung ethischer Pruefungen."""
    __tablename__ = "ai_ethics_audits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Audit details
    audit_type = Column(String(50), nullable=False)
    decision_type = Column(String(100), nullable=True)
    decision_id = Column(UUID(as_uuid=True), nullable=True)
    result = Column(String(20), nullable=False)  # passed, warning, failed
    fairness_score = Column(Float, nullable=True)
    details = Column(CrossDBJSON, default=dict)
    recommendations = Column(CrossDBJSON, default=list)

    # Creator
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="ai_ethics_audits")
    created_by = relationship("User", backref="ai_ethics_audits")

    __table_args__ = (
        Index("ix_ai_ethics_company_created", "company_id", "created_at"),
        Index("ix_ai_ethics_type", "company_id", "audit_type"),
    )

    def __repr__(self) -> str:
        return f"<AIEthicsAudit {self.id} type={self.audit_type} result={self.result}>"


class BiasReport(Base):
    """Bias-Bericht - Erkennungsergebnisse fuer Voreingenommenheit."""
    __tablename__ = "bias_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Report details
    report_type = Column(String(50), nullable=False)
    overall_fairness = Column(Float, nullable=False)
    dimensions = Column(CrossDBJSON, default=list)
    affected_entities = Column(Integer, default=0)
    recommendations = Column(CrossDBJSON, default=list)

    # Timestamps
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", backref="bias_reports")

    __table_args__ = (
        Index("ix_bias_reports_company_generated", "company_id", "generated_at"),
    )

    def __repr__(self) -> str:
        return f"<BiasReport {self.id} fairness={self.overall_fairness}>"


# ============================================================================
# EVENT SOURCING MODELS (Feature 8 - Phase 3)
# ============================================================================

class DomainEvent(Base):
    """Domain Event fuer Event-Sourcing (Hybrid-Ansatz)."""
    __tablename__ = "domain_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aggregate
    aggregate_type = Column(String(50), nullable=False)  # document, invoice, payment, entity
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    sequence_number = Column(BigInteger, nullable=False)

    # Event
    event_type = Column(String(100), nullable=False)
    event_data = Column(CrossDBJSON, nullable=False)
    event_metadata = Column(CrossDBJSON, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Causation
    correlation_id = Column(UUID(as_uuid=True), nullable=True)
    causation_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="domain_events")

    __table_args__ = (
        UniqueConstraint("aggregate_type", "aggregate_id", "sequence_number", name="uq_event_sequence"),
        Index("ix_domain_events_aggregate", "company_id", "aggregate_type", "aggregate_id", "sequence_number"),
        Index("ix_domain_events_type", "company_id", "event_type"),
        Index("ix_domain_events_correlation", "correlation_id"),
    )

    def __repr__(self) -> str:
        return f"<DomainEvent {self.event_type} seq={self.sequence_number}>"


class EventSnapshot(Base):
    """Snapshot des Aggregatzustands fuer Performance."""
    __tablename__ = "event_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aggregate
    aggregate_type = Column(String(50), nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    sequence_number = Column(BigInteger, nullable=False)

    # Snapshot data
    state = Column(CrossDBJSON, nullable=False)
    version = Column(Integer, default=1)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="event_snapshots")

    __table_args__ = (
        Index("ix_event_snapshots_aggregate", "company_id", "aggregate_type", "aggregate_id"),
    )

    def __repr__(self) -> str:
        return f"<EventSnapshot {self.aggregate_type}:{self.aggregate_id} seq={self.sequence_number}>"


# ============================================================================
# EXTERNAL ENRICHMENT MODELS (Feature 12 - Phase 4)
# ============================================================================

class ExternalEnrichmentResult(Base):
    """Externes Datenanreicherungsergebnis."""
    __tablename__ = "external_enrichment_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Source
    source = Column(String(100), nullable=False)  # handelsregister, bundesanzeiger
    source_url = Column(String(500), nullable=True)
    raw_data = Column(CrossDBJSON, default=dict)
    enriched_data = Column(CrossDBJSON, default=dict)

    # Status
    status = Column(String(20), default="completed")  # pending, completed, failed
    confidence = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)

    # Cache
    cached_until = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="enrichment_results")
    entity = relationship("BusinessEntity", backref="enrichment_results")

    __table_args__ = (
        Index("ix_enrichment_entity_source", "entity_id", "source"),
        Index("ix_enrichment_company_created", "company_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ExternalEnrichmentResult {self.source} entity={self.entity_id}>"


# ============================================================================
# DOCUMENT ANNOTATIONS MODELS (Feature 14 - Phase 4)
# ============================================================================

class AnnotationType(str, Enum):
    """Typ einer Dokument-Annotation."""
    HIGHLIGHT = "highlight"
    COMMENT = "comment"
    DRAWING = "drawing"
    STAMP = "stamp"
    APPROVAL = "approval"
    REJECTION = "rejection"
    SIGNATURE = "signature"


class DocumentAnnotation(Base):
    """Dokument-Annotation - Markierungen, Kommentare, Zeichnungen."""
    __tablename__ = "document_annotations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Annotation type and content
    annotation_type = Column(String(20), nullable=False)
    content = Column(Text, nullable=True)
    svg_data = Column(Text, nullable=True)

    # Position
    page = Column(Integer, nullable=False, default=1)
    position = Column(CrossDBJSON, default=dict)  # {x, y, width, height}
    color = Column(String(20), nullable=True)

    # Threading
    parent_annotation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_annotations.id", ondelete="CASCADE"),
        nullable=True
    )
    mentioned_user_ids = Column(CrossDBJSON, default=list)

    # Status
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="annotations")
    company = relationship("Company", backref="document_annotations")
    user = relationship("User", foreign_keys=[user_id], backref="annotations_created")
    resolved_by = relationship("User", foreign_keys=[resolved_by_id], backref="annotations_resolved")
    parent = relationship("DocumentAnnotation", remote_side=[id], backref="replies")

    __table_args__ = (
        Index("ix_annotations_document_page", "document_id", "page"),
        Index("ix_annotations_company_created", "company_id", "created_at"),
        Index("ix_annotations_parent", "parent_annotation_id"),
    )

    def __repr__(self) -> str:
        return f"<DocumentAnnotation {self.id} type={self.annotation_type} page={self.page}>"


# ============================================================================
# LIFE EVENTS MODELS (Feature 16 - Phase 4)
# ============================================================================

class LifeEventType(str, Enum):
    """Typ eines Lebensereignisses."""
    UMZUG = "umzug"
    HEIRAT = "heirat"
    KIND = "kind"
    JOBWECHSEL = "jobwechsel"
    RUHESTAND = "ruhestand"
    TODESFALL = "todesfall"
    IMMOBILIENKAUF = "immobilienkauf"
    SCHEIDUNG = "scheidung"


class LifeEventStatus(str, Enum):
    """Status eines Lebensereignisses."""
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


class LifeEvent(Base):
    """Lebensereignis - Proaktiver Lebensberater."""
    __tablename__ = "life_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Event details
    event_type = Column(String(30), nullable=False)
    status = Column(String(20), default=LifeEventStatus.DETECTED.value)
    detection_source = Column(String(100), nullable=True)  # document_analysis, user_input, pattern
    detection_confidence = Column(Float, default=0.0)

    # Content
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(Date, nullable=True)

    # Checklist and recommendations
    checklist = Column(CrossDBJSON, default=list)  # [{id, task, completed, due_date}]
    recommendations = Column(CrossDBJSON, default=list)  # [{title, description, priority, url}]
    financial_impact = Column(CrossDBJSON, default=dict)  # {estimated_cost, savings_potential, tax_impact}

    # Related documents
    related_document_ids = Column(CrossDBJSON, default=list)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="life_events")
    company = relationship("Company", backref="life_events")

    __table_args__ = (
        Index("ix_life_events_user_status", "user_id", "status"),
        Index("ix_life_events_company_created", "company_id", "created_at"),
        Index("ix_life_events_type", "company_id", "event_type"),
    )

    def __repr__(self) -> str:
        return f"<LifeEvent {self.event_type} status={self.status}>"


# ============================================================================
# VISION 2.0 SUPPLEMENTARY MODELS (Feature Gap Fixes)
# ============================================================================


class DocumentEntityLink(Base):
    """Verknuepfung zwischen Document und BusinessEntity.

    Ermoeglicht M:N Beziehungen zwischen Dokumenten und Geschaeftspartnern
    mit Typ-Klassifikation und Confidence-Score.

    Link Types:
    - invoice_sender: Entity hat Rechnung gesendet
    - invoice_recipient: Entity ist Rechnungsempfaenger
    - mentioned: Entity wird im Dokument erwaehnt
    - extracted: Entity wurde aus OCR-Text extrahiert
    - manual: Manuell vom Benutzer verknuepft
    """
    __tablename__ = "document_entity_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Link metadata
    link_type = Column(String(50), nullable=True)
    confidence = Column(Float, default=1.0)
    link_metadata = Column(CrossDBJSON, default=dict)  # Renamed: 'metadata' is reserved in SQLAlchemy

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    document = relationship("Document", backref="entity_links")
    entity = relationship("BusinessEntity", backref="document_links")
    company = relationship("Company", backref="document_entity_links")
    created_by = relationship("User")

    __table_args__ = (
        Index("ix_doc_entity_links_company_type", "company_id", "link_type"),
        # Ein Document kann mit einem Entity nur einmal pro Link-Type verknuepft sein
        # Note: Constraint created in migration
    )

    def __repr__(self) -> str:
        return f"<DocumentEntityLink doc={self.document_id} entity={self.entity_id} type={self.link_type}>"


class RiskScoreHistory(Base):
    """Historische Risk-Scores fuer Geschaeftspartner.

    Ermoeglicht Trend-Analyse und Explainability fuer AI Ethics.
    Jeder Eintrag speichert den Score mit allen Faktoren.

    Triggers:
    - scheduled: Taegliche/woechentliche Berechnung
    - invoice_paid: Nach Zahlungseingang
    - dunning_increased: Nach Mahnstufe-Erhoehung
    - manual: Manuelle Neuberechnung
    """
    __tablename__ = "risk_score_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Score data
    score = Column(Float, nullable=False)
    risk_level = Column(String(20), nullable=True)  # low, medium, high, critical
    factors = Column(CrossDBJSON, default=dict)  # {"payment_delay": 25, ...}

    # Context
    trigger_event = Column(String(100), nullable=True)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    entity = relationship("BusinessEntity", backref="risk_score_history")
    company = relationship("Company", backref="risk_score_history")

    __table_args__ = (
        Index("ix_risk_score_history_entity_date", "entity_id", "calculated_at"),
        Index("ix_risk_score_history_company_date", "company_id", "calculated_at"),
    )

    def __repr__(self) -> str:
        return f"<RiskScoreHistory entity={self.entity_id} score={self.score} level={self.risk_level}>"

# Aliases for backward compatibility
Comment = DocumentComment

# Import additional model modules to ensure they are discovered by SQLAlchemy/Alembic
# Phase 6: PSD2/FinTS Banking Integration
from app.db.models_banking_connection import (
    BankConnection,
    ConnectedBankAccount,
    ImportedTransaction,
    TransactionSplitAllocation,
    BankSyncLog,
    PaymentInitiation,
    ReconciliationRule,
    SupportedBank,
)
# Phase 7: Enterprise Features (Feb 2026)
from app.db.models_einvoice import (
    EInvoiceTransmission, PeppolParticipant, IncomingEInvoice,
)
from app.db.models_autonomy import (
    AutonomySettings, PendingAction, AutonomyDecisionLog, AutonomyMetrics,
)
from app.db.models_esg import (
    ESGCarbonFootprint, ESGSupplierRating, ESGCertification, ESGReport, ESGGoal,
)
from app.db.models_fx import (
    ExchangeRate, FXGainLossEntry,
)
from app.db.models_gl_posting import (
    GLAccount, JournalEntry, JournalEntryLine, TaxPeriod,
)
from app.db.models_portal import (
    PortalUser, PortalSession, PortalComplaint, PortalMessage, PortalDocument, PortalPaymentConfirmation,
)
from app.db.models_workflow_stage import (
    WorkflowStage, DocumentWorkflowItem,
)
from app.db.models_notification_template import (
    NotificationMessageTemplate,
)
# Ensure cross-referencing satellite models are all loaded before configure_mappers()
from app.db.models_alert import Alert, AlertRule  # noqa: F401 - needed by models_fraud
from app.db.models_fraud import FraudScanResult, IBANBaseline, IBANChangeRequest  # noqa: F401
from app.db.models_inventory import Warehouse, InventoryItem, StockLevel, InventoryMovement  # noqa: F401
from app.db.models_contract import Contract  # noqa: F401
from app.db.models_invoice import Invoice  # noqa: F401
from app.db.models_delegation import Delegation  # noqa: F401
