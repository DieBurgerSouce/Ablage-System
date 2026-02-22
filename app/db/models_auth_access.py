"""Auth, Security, Webhooks und Access-Modelle - extrahiert aus models.py (Modularisierung Phase 1.1)."""
import uuid
from datetime import datetime
from typing import Optional
from enum import Enum
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, Text, Float, ForeignKey, Index, Table, JSON, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.models_base import Base, CrossDBJSON


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
    deliveries = relationship("WebhookSubscriptionDelivery", back_populates="subscription", cascade="all, delete-orphan")

    # Indexes
    __table_args__ = (
        Index("ix_webhook_subscriptions_user_id", "user_id"),
        Index("ix_webhook_subscriptions_is_active", "is_active"),
        Index("ix_webhook_subscriptions_created_at", "created_at"),
    )


class WebhookSubscriptionDelivery(Base):
    """
    Webhook-Zustellungsprotokoll fuer Subscriptions.

    Dokumentiert jeden Zustellungsversuch mit Response-Details.
    Ermoeglicht Debugging und Retry-Tracking.
    """
    __tablename__ = "webhook_subscription_deliveries"

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
        Index("ix_webhook_sub_deliveries_subscription_id", "subscription_id"),
        Index("ix_webhook_sub_deliveries_event_id", "event_id"),
        Index("ix_webhook_sub_deliveries_status", "status"),
        Index("ix_webhook_sub_deliveries_created_at", "created_at"),
        Index("ix_webhook_sub_deliveries_next_retry_at", "next_retry_at"),
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
    Zugriffsebenen für Chat Session Sharing.

    - VIEW: Nur lesen (Chat und Nachrichten ansehen)
    - CONTRIBUTE: Mitarbeiten (Nachrichten senden, mit KI interagieren)
    - MANAGE: Verwalten (Alles + User einladen/entfernen, Chat löschen)
    """
    VIEW = "view"
    CONTRIBUTE = "contribute"
    MANAGE = "manage"


class ChatSessionAccess(Base):
    """
    Chat Session Zugriff für Real-time Collaboration.

    Ermöglicht:
    - Chats mit anderen Benutzern teilen
    - Verschiedene Zugriffsebenen (view, contribute, manage)
    - Real-time Zusammenarbeit über WebSocket
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
        """Hat Contribute- oder höhere Berechtigung."""
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

    Speichert Informationen über durchgeführte Backups:
    - Zeitpunkt und Dauer
    - Typ (Full, Incremental, Component)
    - Größe und Speicherort
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

    # Größe in Bytes
    size_bytes = Column(BigInteger, nullable=True)

    # Speicherort (lokal oder remote)
    storage_path = Column(String(500), nullable=True)
    remote_path = Column(String(500), nullable=True)

    # Checksumme für Integrität
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
        """Gibt Größe in lesbarem Format zurück."""
        if not self.size_bytes:
            return "N/A"
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(self.size_bytes) < 1024.0:
                return f"{self.size_bytes:.1f} {unit}"
            self.size_bytes /= 1024.0
        return f"{self.size_bytes:.1f} PB"
