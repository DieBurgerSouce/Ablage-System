"""SQLAlchemy database models for Ablage-System.

HINWEIS ZU RELATIONSHIPS:
=========================
Dieses Modul verwendet eine Mischung aus `backref` und `back_populates`.
Beide sind funktional äquivalent.

KONVENTION FÜR NEUE RELATIONSHIPS:
- Verwende `back_populates` für explizite bidirektionale Beziehungen
- Definiere die Relationship auf BEIDEN Seiten der Beziehung
- `backref` ist weiterhin akzeptabel für einfache unidirektionale Referenzen

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


# Base, CrossDBJSON, CrossDBTSVector, CrossDBVector are defined in models_base.py
# to avoid circular imports with domain model files (models_*.py).
from app.db.models_base import Base, CrossDBJSON, CrossDBTSVector, CrossDBVector  # noqa: F401

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
    """Document type classification - 15 Types für Enterprise-Klassifikation.

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
        comment="Mandanten-Zuordnung für Multi-Company Isolation"
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
    is_group_primary = Column(Boolean, default=False)  # Ist das primäre Dokument der Gruppe

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

    # Scan metadata (für Gruppierungserkennung)
    scan_timestamp = Column(DateTime(timezone=True), nullable=True)  # Wann wurde gescannt
    scan_batch_id = Column(String(100), nullable=True)  # Scan-Batch ID
    original_filename_sequence = Column(Integer, nullable=True)  # Sequenznummer aus Original-Dateinamen

    # Quick Classification (schnelle Klassifizierung in 2-5 Sekunden)
    # Läuft PARALLEL zum vollständigen OCR, um sofort Tags zuzuweisen
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

    # Custom Fields (benutzerdefinierte Felder, JSONB)
    custom_field_values = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Benutzerdefinierte Feldwerte (JSONB)"
    )

    # Auto-Summary (Phase 2.2: KI-generierte Zusammenfassungen)
    summary = Column(Text, nullable=True, comment="KI-generierte Zusammenfassung (3-5 Saetze)")
    keywords = Column(CrossDBJSON, nullable=False, server_default=text("'[]'::jsonb"), comment="Extrahierte Schluesselwoerter")
    one_liner = Column(String(500), nullable=True, comment="Einzeilige Beschreibung")
    summary_generated_at = Column(DateTime(timezone=True), nullable=True)
    summary_model = Column(String(100), nullable=True, comment="LLM-Modell fuer Zusammenfassung")

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
        # Phase 2.3: Index für Soft-Delete Queries
        Index("ix_documents_deleted_at", "deleted_at"),
        # Phase 3: Compound Index für Owner + Created (häufige Query)
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
        # Auto-Summary (Phase 2.2): Partial Index fuer Dokumente mit Zusammenfassung
        Index(
            "ix_documents_summary_generated",
            "company_id", "summary_generated_at",
            postgresql_where=text("summary IS NOT NULL"),
        ),
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

    # GoBD: Steuerberater/Prüfer zeitlich begrenzter Zugang
    access_until = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Zeitliche Begrenzung des Zugangs (für Steuerberater/Prüfer)"
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
        comment="Eingeschraenkter Zugriff (z.B. nur bestimmte Firmen, Zeiträume)"
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
        nullable=True,  # NULL für System-Events (Migrations, Cron-Jobs)
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

# =============================================================================
# MODULARISIERUNG PHASE 1.1 - Re-Exports
# Alle Domain-Modelle sind in separate Dateien extrahiert.
# Diese Re-Exports stellen volle Backward-Kompatibilitaet sicher.
# =============================================================================


# --- GDPR, DPIA & Compliance ---
from app.db.models_gdpr_compliance import (  # noqa: E402, F401
    GDPRDeletionRequestStatus, GDPRDeletionRequest, GDPRBreachLog,
    GDPRConsentLog, GDPRProcessingActivity,
    RetentionCategory, HashAlgorithm, DocumentAccessType,
    DocumentAccessLog, DocumentArchive, ProcedureDocumentationVersion,
    RetentionSetting, TaxAdvisorInviteStatus, TaxAdvisorInvite,
    TaxAdvisorAccessLog,
    GDPRConsentVersion, GDPRConsentScope, GDPRDataSubjectRequest,
    GDPRDataExport, GDPRConsentHistory,
    DPIAStatus, DPIARiskLevel, DPIALegalBasis, DPIAMeasureType,
    DPIAImplementationStatus, DPIA, DPIAProcessingOperation,
    DPIADataSubjectGroup, DPIARisk, DPIAMitigationMeasure,
    DPIAConsultation, DPIAAuditLog,
)


# --- Auth, Security, Webhooks, Access ---
from app.db.models_auth_access import (  # noqa: E402, F401
    PasswordResetToken, ExportStatus, ExportFormat, DataExport,
    PermissionAction, ResourceType, role_permissions, user_roles,
    Permission, Role, UserSession, EmailVerificationToken,
    WebhookEventType, WebhookDeliveryStatus, WebhookSubscription,
    WebhookSubscriptionDelivery,
    DocumentFavorite, AccessLevel, DocumentAccess,
    ChatSessionAccessLevel, ChatSessionAccess,
    BackupType, BackupStatus, BackupRecord,
)


# --- Entity, Business, Contracts, Multi-Tenancy, DLP, BPMN ---
from app.db.models_entity_business import (  # noqa: E402, F401
    Notification, FeatureFlag,
    EntityType, BusinessEntity, InvoiceStatus, InvoiceTracking,
    PaymentTransaction, DocumentChainDiscrepancy,
    DocumentGroupType, DocumentGroup, RelationshipType, DocumentRelationship,
    ContractType, ContractStatus, RenewalOptionStatus, MilestoneType,
    AmendmentStatus, BusinessContract, ContractMilestone,
    ContractRenewalOption, ContractAmendment,
    SubscriptionTier, TenantRateLimit, TenantUsageMetrics,
    RateLimitViolation, SubscriptionTierDefaults,
    ContactType, ContactRole, DocumentContact, BusinessContact,
    DLPActionType, SensitiveDataTypeEnum, DLPPolicyModel, DLPAuditLog,
    ProcessStatus, BpmnTaskStatus, TaskType,
    GatewayType, EventType, EventTrigger,
    NotificationType,  # INFO/SUCCESS/WARNING version - overridden by notification module below
)
# NOTE: NotificationType from entity_business (INFO/SUCCESS/WARNING) is overridden
# by ActivityNotificationType from notification module below (MENTION/COMMENT_REPLY).
# This matches original models.py behavior where the 2nd definition overwrites the 1st.
# notification's TaskType-like enums.


# --- OCR Training & Validation ---
from app.db.models_ocr_validation import (  # noqa: E402, F401
    TrainingSampleStatus, OCRTrainingSample, OCRBackendBenchmark,
    CorrectionType, OCRValidationCorrection,
    BatchType, BatchStatus, OCRTrainingBatch,
    ItemStatus, OCRTrainingBatchItem, OCRBackendStatsDaily,
    BulkJobStatus, OCRBulkProcessingJob, OCRDocumentOutput,
    OCRQualitySnapshot, ModelType, OCRModelDeployment,
    ValidationStatus, SampleSource, ValidationRuleType,
    ValidationSampleConfig, ValidationRule, ValidationQueueItem,
    ValidationFieldReview, ValidationAnalytics,
)


# --- RAG Intelligence Layer ---
from app.db.models_rag import (  # noqa: E402, F401
    RAGSectionType, RAGSyncStatus, RAGChatRole, RAGLLMModelType,
    RAGJobType, RAGJobStatus, RAGCardPriorityLevel, RAGContextType,
    RAGDocumentChunk, RAGCustomerCard, RAGChatSession, RAGChatMessage,
    RAGLLMModel, RAGBatchJob, RAGAnalytics,
    RAGBatchJobType, RAGBatchJobStatus, RAGCardSyncStatus,
)


# --- Surya Training ---
from app.db.models_surya_training import (  # noqa: E402, F401
    SuryaModelStatus, SuryaTrainingRunStatus, SuryaABTestStatus,
    SuryaModelVersion, SuryaTrainingRun, SuryaABTest, SuryaBenchmarkHistory,
    BusinessDocumentProfile, CoverageSnapshot,
)


# --- Banking ---
from app.db.models_banking import (  # noqa: E402, F401
    EInvoiceFormat, EInvoiceProfile, EInvoiceDocument,
    BankAccount, BankImport, BankTransaction, PaymentBatch,
    PaymentOrder, DunningRecord, MahnungHistory, MahnTask,
    PhoneCallLog, DunningStageConfig, CustomerDunningOverride, CashFlowEntry,
)


# --- DATEV ---
from app.db.models_datev import (  # noqa: E402, F401
    DATEVConfiguration, DATEVVendorMapping, DATEVExport,
    DATEVConnectionStatus, DATEVSyncType, DATEVKontierungStatus,
    DATEVConnection, DATEVKontenplan, DATEVBuchung, DATEVBeleglink,
    DATEVKontierungPattern, DATEVSyncHistory, FinanceDocumentHistory,
)


# --- Cash/Company ---
from app.db.models_cash_company import (  # noqa: E402, F401
    CashEntryType, ExpenseReportStatus, ExpenseType,
    Company, UserCompany, CashRegister, CashEntry,
    CashCategory, CashCount, ExpenseReport, ExpenseItem,
)


# --- DropShipment/Tax ---
from app.db.models_dropship_tax import (  # noqa: E402, F401
    TransactionType, DropShipmentCompanyRole, MovingDelivery,
    ConfidenceLevel, VatCategoryType,
    DropShipmentClassification, DropShipmentPosition,
    VatIdRegistry, TransactionParty, ProofDocument,
    ClassificationAuditLog, DatevStreckengeschaeftAccount,
    ClassificationIndicator, ZmSubmissionStatus, ZmSubmission,
)


# --- HR ---
from app.db.models_hr import (  # noqa: E402, F401
    EmploymentType, EmployeeStatus, LeaveType, LeaveRequestStatus,
    HRContractStatus, TrainingStatus, ReviewStatus, OnboardingTaskStatus,
    HRDocumentCategory,
    Department, Position, Employee, EmploymentContract,
    LeaveRequest, Absence, TimeEntry, Training,
    PerformanceReview, OnboardingTask, HRDocument,
)


# --- Privat Space ---
from app.db.models_privat_space import (  # noqa: E402, F401
    PrivatSpaceType, PrivatAccessLevel, PrivatDocumentType, PrivatDeadlineType,
    PrivatEmergencyAccessStatus,
    PrivatSpace, PrivatSpaceAccess, PrivatFolder, PrivatDocument,
    PrivatProperty, PrivatTenant, PrivatRentalIncome, PrivatUtilityStatement,
    PrivatVehicle, PrivatFuelLog, PrivatInsurance, PrivatLoan,
    PrivatInvestment, PrivatDeadline, PrivatDeadlineNotification,
    PrivatEmergencyContact, PrivatEmergencyAccessRequest,
)


# --- Notifications, Activities, Tasks ---
from app.db.models_notification import (  # noqa: E402, F401
    DocumentComment, ActivityType, DocumentActivity,
    ActivityNotificationType, UserNotification,
    TaskStatus, TaskPriority, DocumentTask,
    NotificationChannel, DigestFrequency, NotificationPreference,
    NotificationDigestQueue,
    PushSubscription, NotificationTemplate, NotificationHistory,
    NotificationRulePriority, NotificationRuleActionType, NotificationRule,
)
# Backward compatibility: Activity notification version (MENTION, COMMENT_REPLY, etc.)
# overwrites core version (INFO, SUCCESS, WARNING) - matches original models.py behavior
NotificationType = ActivityNotificationType

# --- Approval Extended (EscalationRule re-export) ---
from app.db.models_approval_extended import EscalationRule  # noqa: E402, F401

# --- ERP & Import ---
from app.db.models_erp_import import (  # noqa: E402, F401
    ERPType, ERPSyncDirection, ERPConnectionStatus, ERPSyncStatus,
    ERPConflictStatus, ERPConflictResolution, ERPEntityType,
    ERPConnection, ERPSyncHistory, ERPFieldMapping, ERPConflict,
    ERPEntityMapping, OdooWebhookEvent, OdooSyncStatus, OdooAIFeedback,
    EmailImportConfig, FolderImportConfig, ImportRule, ImportLog,
)


# --- AI/ML Intelligence ---
from app.db.models_ai_ml import (  # noqa: E402, F401
    AIConfidenceThreshold, AIDecision, AILearningFeedback,
    DocumentMatch, PaymentPrediction,
    AutonomousTrustConfig, AutonomousProposalQueue,
)


# --- Reports ---
from app.db.models_report import (  # noqa: E402, F401
    ReportTemplate, ReportColumn, ReportFilter, ReportChart,
    ReportExecution, ReportShare,
)


# --- Workflows ---
from app.db.models_workflow import (  # noqa: E402, F401
    Workflow, WorkflowStep, WorkflowExecution, WorkflowStepExecution,
)


# --- Privat Enterprise (KPI, Goals, Approvals) ---
from app.db.models_privat_enterprise import (  # noqa: E402, F401
    RecurringPaymentFrequency, RecurringPaymentCategory,
    CoverageGapType, CoverageGapSeverity,
    LLMCache, EventLog,
    PrivatRecurringPayment, PrivatCoverageGap,
    KPIUnit, ProjectionMethod, TrendDirection,
    WarningSeverity, WarningType, ProfessionType, RiskProfile,
    PrivatKPIHistory, PrivatProjection, PrivatEarlyWarning,
    PrivatTask, PortfolioSnapshot,
    FinancialGoalType, FinancialGoalStatus, FinancialGoal,
    FinancialGoalContribution,
    ApprovalRuleType, ApprovalStatus, ApprovalPriority,
    ApprovalRule, ApprovalRequest, ApprovalStep, ApprovalDelegation,
    PrivatUserProfile, PrivatUserThreshold,
    PrivatThresholdAdjustment, PrivatThresholdRecommendation,
)

# --- Privat Contracts (Vertragsmanagement) ---
from app.db.models_privat_contracts import (  # noqa: E402, F401
    PrivatContractCategory, PrivatContractStatus,
    PrivatContract, PrivatContractReminder,
)


# --- Templates & Knowledge Base ---
from app.db.models_template_knowledge import (  # noqa: E402, F401
    TemplateCategory, TemplateOutputFormat, VariableType,
    DocumentTemplate, GeneratedDocument, TemplateSnippet,
    NoteType, ContentFormat, KnowledgeLinkType, LinkableType,
    KnowledgeNote, KnowledgeChecklist, KnowledgeChecklistItem,
    KnowledgeLink, KnowledgeTag,
)


# --- Slack & Shipment Integration ---
from app.db.models_integration import (  # noqa: E402, F401
    SlackChannelType, SlackChannel, SlackMessageStatus,
    SlackMessageLog, SlackUserMapping,
    ShipmentCarrier, ShipmentDirection, ShipmentStatusEnum,
    Shipment, ShipmentEvent,
)


# --- Diverse System-Modelle ---
from app.db.models_misc import (  # noqa: E402, F401
    CompanySettings, SavedFilter, AppConfig,
    ZeroTouchResult, NLQQueryLog,
    SmartInboxItemSource, SmartInboxItemStatus, SmartInboxItem,
    UserBehaviorLog, CompanyHealthSnapshot,
    GraphEdge, MerkleTreeNode,
    AIEthicsAudit, BiasReport,
    DomainEvent, EventSnapshot,
    ExternalEnrichmentResult,
    AnnotationType, DocumentAnnotation,
    LifeEventType, LifeEventStatus, LifeEvent,
    DocumentEntityLink, RiskScoreHistory,
)

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
from app.db.models_alert import Alert, AlertRule, AlertCategory, AlertSeverity  # noqa: F401
from app.db.models_fraud import FraudScanResult, IBANBaseline, IBANChangeRequest  # noqa: F401
from app.db.models_inventory import Warehouse, InventoryItem, StockLevel, InventoryMovement  # noqa: F401
from app.db.models_contract import Contract  # noqa: F401
from app.db.models_invoice import Invoice  # noqa: F401
from app.db.models_delegation import Delegation  # noqa: F401
# Batch 6: Satellite models from Batches 1-3 features
from app.db.models_barcode import BarcodeDetection  # noqa: F401
from app.db.models_custom_fields import CustomFieldDefinition  # noqa: F401
from app.db.models_approval_matrix import (  # noqa: F401
    ApprovalMatrix, ApprovalChainTemplate, ApprovalAuditLog,
    ApprovalGroup, ApprovalGroupMember,
)
# Phase 1.4: Field-Level Encryption (DSGVO Art. 32)
from app.db.models_encryption import EncryptedFieldMeta, KeyRotationLog  # noqa: F401
