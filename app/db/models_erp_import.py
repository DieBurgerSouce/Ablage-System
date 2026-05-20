"""ERP-Integration und Import Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Text, Float, ForeignKey, Index, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models_base import Base, CrossDBJSON


# =============================================================================
# ERP Integration Models - Feature 04: Odoo-Integration
# =============================================================================


class ERPType(str, Enum):
    """Unterstützte ERP-Systeme."""
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
    """Synchronisierbare Entitätstypen."""
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
    für die Integration mit externen ERP-Systemen.
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

    Speichert Details zu jedem Sync-Lauf für Auditing,
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
    benötigen.
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

    # Priorität
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
    """Verknüpfung lokaler Entitäten mit ERP-IDs.

    Speichert die Zuordnung zwischen lokalen und
    Remote-Entitäten für Delta-Sync und Konflikt-Erkennung.
    """
    __tablename__ = "erp_entity_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("erp_connections.id", ondelete="CASCADE"),
        nullable=False
    )

    # Entitäts-Verknüpfung
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
        {"comment": "Verknüpfung lokaler Entitäten mit ERP-IDs"}
    )

    def __repr__(self) -> str:
        return f"<ERPEntityMapping {self.entity_type} local={self.local_id} remote={self.remote_id}>"


# =============================================================================
# ODOO INTEGRATION - Phase 6: Webhooks, Extended Sync, AI Feedback
# =============================================================================


class OdooWebhookEvent(Base):
    """Odoo Webhook Events für idempotente Verarbeitung.

    Speichert empfangene Webhooks für:
    - Idempotenz-Prüfung (doppelte Events ignorieren)
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

    # Event-Identifikation (für Idempotenz)
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
    """Sync-Status pro Datentyp für erweiterte Odoo-Synchronisation.

    Trackt den Sync-Zustand für:
    - Projects
    - Timesheet
    - Inventory/Stock Moves
    - Products

    Ermöglicht Delta-Sync und Fehler-Tracking.
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

    Für Tracking und Retry-Logik.
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
    """IMAP Server-Konfigurationen für E-Mail-Import.

    Speichert verschluesselte Credentials und Sync-Einstellungen
    für automatischen E-Mail-Import.
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
        {"comment": "IMAP Server-Konfigurationen für E-Mail-Import"}
    )

    def __repr__(self) -> str:
        return f"<EmailImportConfig {self.name} ({self.imap_server})>"


class FolderImportConfig(Base):
    """Hotfolder-Konfigurationen für Ordner-Import.

    Überwacht lokale Ordner oder Netzwerkpfade auf neue Dateien
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

    # Polling (Backup für Watchdog)
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
        {"comment": "Hotfolder-Konfigurationen für Ordner-Import"}
    )

    def __repr__(self) -> str:
        return f"<FolderImportConfig {self.name} ({self.watch_path})>"


class ImportRule(Base):
    """Filter- und Routing-Regeln für Import.

    Ermöglicht automatische Klassifizierung, Ordner-Zuweisung
    und weitere Aktionen basierend auf Bedingungen.
    """
    __tablename__ = "import_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Regel-Identität
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(Integer, default=100, index=True)

    # Quelle (auf welche Configs diese Regel angewendet wird)
    applies_to_email_configs = Column(CrossDBJSON, default=list)
    applies_to_folder_configs = Column(CrossDBJSON, default=list)
    applies_to_all = Column(Boolean, default=False)

    # Bedingungen (JSON-Struktur für flexible Matching)
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
        {"comment": "Filter- und Routing-Regeln für Import"}
    )

    def __repr__(self) -> str:
        return f"<ImportRule {self.name} (priority={self.priority})>"


class ImportLog(Base):
    """Import-Historie mit Status-Tracking.

    Protokolliert jeden Import-Vorgang für Audit und Fehleranalyse.
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
    file_hash = Column(String(64), nullable=True, index=True)  # SHA256 für Deduplizierung
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
