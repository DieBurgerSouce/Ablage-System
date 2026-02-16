"""GoBD Compliance Models - Erweiterte Modelle für revisionssichere Archivierung.

Dieses Modul erweitert die GoBD-Konformitaet mit:
- AuditChainEntry: Blockchain-ähnliche Hash-Kette für Audit-Trail
- RetentionPolicy: Aufbewahrungsrichtlinien mit automatischen Aktionen
- ArchiveIntegrityCheck: Protokollierung von Integritätsprüfungen
- TimestampAuthority: RFC 3161 Zeitstempel-Konfiguration

GoBD = Grundsätze zur ordnungsmäßigen Führung und Aufbewahrung
       von Buechern, Aufzeichnungen und Unterlagen in elektronischer
       Form sowie zum Datenzugriff
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column, String, DateTime, Text, Integer, Boolean, ForeignKey, Index,
    UniqueConstraint, CheckConstraint, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.models import Base, CrossDBJSON


class AuditChainEventType(str, Enum):
    """Typen von Ereignissen in der Audit-Chain."""
    # Dokument-Ereignisse
    DOCUMENT_CREATED = "document_created"
    DOCUMENT_ARCHIVED = "document_archived"
    DOCUMENT_ACCESSED = "document_accessed"
    DOCUMENT_MODIFIED = "document_modified"
    DOCUMENT_DELETED = "document_deleted"
    DOCUMENT_EXPORTED = "document_exported"

    # Integritäts-Ereignisse
    INTEGRITY_CHECK_PASSED = "integrity_check_passed"
    INTEGRITY_CHECK_FAILED = "integrity_check_failed"
    HASH_RECALCULATED = "hash_recalculated"

    # Aufbewahrungsfrist-Ereignisse
    RETENTION_PERIOD_SET = "retention_period_set"
    RETENTION_PERIOD_EXTENDED = "retention_period_extended"
    RETENTION_EXPIRED = "retention_expired"
    RETENTION_DELETION_APPROVED = "retention_deletion_approved"

    # Zugriffs-Ereignisse
    TAX_ADVISOR_ACCESS = "tax_advisor_access"
    AUDITOR_ACCESS = "auditor_access"
    EXPORT_CREATED = "export_created"

    # System-Ereignisse
    SYSTEM_STARTUP = "system_startup"
    CHAIN_VERIFICATION = "chain_verification"
    CHAIN_REPAIR = "chain_repair"


class IntegrityCheckStatus(str, Enum):
    """Status einer Integritätsprüfung."""
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    REPAIRED = "repaired"


class AuditChainEntry(Base):
    """Blockchain-ähnliche Audit-Chain für GoBD-konforme Nachvollziehbarkeit.

    Jeder Eintrag enthält:
    - Hash des vorherigen Eintrags (Chain)
    - Hash des Ereignis-Inhalts
    - Kombinierter Hash (previous + content)
    - Sequenznummer (lückenlos)

    Die Kette ist APPEND-ONLY und IMMUTABLE!
    Manipulationsversuche werden durch Hash-Verifikation erkannt.
    """
    __tablename__ = "gobd_audit_chain"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Chain-Verkettung
    sequence_number = Column(
        Integer,
        nullable=False,
        comment="Lückenlose Sequenznummer (startet bei 1)"
    )
    previous_hash = Column(
        String(128),
        nullable=True,
        comment="SHA-256 Hash des vorherigen Eintrags (NULL für Genesis)"
    )
    content_hash = Column(
        String(128),
        nullable=False,
        comment="SHA-256 Hash des Ereignis-Inhalts"
    )
    combined_hash = Column(
        String(128),
        nullable=False,
        comment="SHA-256(previous_hash + content_hash)"
    )

    # Ereignis-Details
    event_type = Column(
        String(50),
        nullable=False,
        comment="Typ des Ereignisses (AuditChainEventType)"
    )
    event_data = Column(
        CrossDBJSON,
        nullable=False,
        default=dict,
        comment="Ereignis-Payload (keine PII!)"
    )

    # Referenzen (optional)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Benutzer der das Ereignis ausgeloest hat"
    )

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # RFC 3161 Timestamp (optional)
    tsa_timestamp = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="RFC 3161 Zeitstempel von TSA"
    )
    tsa_token = Column(
        Text,
        nullable=True,
        comment="Base64-encoded TSA Response Token"
    )
    tsa_provider = Column(
        String(100),
        nullable=True,
        comment="Name des TSA-Providers"
    )

    # Verifikation
    is_verified = Column(Boolean, default=True, nullable=False)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_error = Column(Text, nullable=True)

    # Relationships
    document = relationship("Document", backref="audit_chain_entries")
    company = relationship("Company", backref="gobd_audit_chain")
    user = relationship("User", backref="gobd_audit_entries")

    __table_args__ = (
        # Eindeutige Sequenz pro Company
        UniqueConstraint("company_id", "sequence_number", name="uq_audit_chain_company_sequence"),
        # Indizes
        Index("ix_audit_chain_company_seq", "company_id", "sequence_number"),
        Index("ix_audit_chain_combined_hash", "combined_hash"),
        Index("ix_audit_chain_event_type", "event_type"),
        Index("ix_audit_chain_document_id", "document_id"),
        Index("ix_audit_chain_created_at", "created_at"),
        # Check: Genesis hat keine previous_hash
        CheckConstraint(
            "(sequence_number = 1 AND previous_hash IS NULL) OR (sequence_number > 1 AND previous_hash IS NOT NULL)",
            name="ck_audit_chain_genesis"
        ),
        {"comment": "GoBD Audit-Chain: Blockchain-ähnliche verkettete Ereignis-Protokollierung"}
    )

    def __repr__(self) -> str:
        return f"<AuditChainEntry seq={self.sequence_number} type={self.event_type}>"


class RetentionPolicy(Base):
    """GoBD Aufbewahrungsrichtlinie für Dokumenttypen.

    Definiert automatische Aktionen basierend auf Aufbewahrungsfristen:
    - Warnungen vor Ablauf
    - Automatische Kennzeichnung
    - Löschfreigabe-Workflow
    """
    __tablename__ = "gobd_retention_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Richtlinien-Definition
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    document_category = Column(
        String(50),
        nullable=False,
        comment="Dokumentkategorie: invoice, contract, etc."
    )

    # Aufbewahrungsfrist
    retention_years = Column(
        Integer,
        nullable=False,
        default=10,
        comment="Aufbewahrungsdauer in Jahren"
    )
    legal_basis = Column(
        String(255),
        nullable=True,
        comment="Gesetzliche Grundlage: §147 AO, §257 HGB, etc."
    )

    # Warnungen
    warning_days_before = Column(
        Integer,
        default=180,
        nullable=False,
        comment="Tage vor Ablauf für erste Warnung"
    )
    critical_days_before = Column(
        Integer,
        default=30,
        nullable=False,
        comment="Tage vor Ablauf für kritische Warnung"
    )

    # Automatische Aktionen
    auto_delete_after_expiry = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Automatisch löschen nach Ablauf (GEFAEHRLICH!)"
    )
    require_approval_for_delete = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Freigabe vor Löschung erforderlich"
    )
    approval_roles = Column(
        CrossDBJSON,
        default=list,
        nullable=False,
        comment="Rollen die Löschung freigeben können"
    )

    # Benachrichtigungen
    notify_on_warning = Column(Boolean, default=True, nullable=False)
    notification_recipients = Column(
        CrossDBJSON,
        default=list,
        nullable=False,
        comment="User-IDs oder Rollen für Benachrichtigungen"
    )

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    company = relationship("Company", backref="gobd_retention_policies")
    created_by = relationship("User", backref="created_retention_policies")

    __table_args__ = (
        UniqueConstraint("company_id", "document_category", name="uq_retention_policy_category"),
        Index("ix_retention_policies_company", "company_id"),
        Index("ix_retention_policies_category", "document_category"),
        {"comment": "GoBD Aufbewahrungsrichtlinien pro Dokumentkategorie"}
    )

    def __repr__(self) -> str:
        return f"<RetentionPolicy {self.document_category} years={self.retention_years}>"


class ArchiveIntegrityCheck(Base):
    """Protokollierung von Integritätsprüfungen für Dokument-Archive.

    Erfasst regelmäßige und Ad-hoc Verifikationen der Hash-Signaturen.
    Bei Fehlern wird ein Alert ausgeloest.
    """
    __tablename__ = "gobd_archive_integrity_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    archive_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_archives.id", ondelete="CASCADE"),
        nullable=False
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Prüfungs-Details
    check_type = Column(
        String(50),
        nullable=False,
        default="scheduled",
        comment="scheduled, manual, repair_verification"
    )
    status = Column(
        String(20),
        nullable=False,
        default=IntegrityCheckStatus.PENDING.value
    )

    # Hash-Vergleich
    expected_hash = Column(String(128), nullable=False)
    actual_hash = Column(String(128), nullable=True)
    hash_match = Column(Boolean, nullable=True)

    # TSA-Verifikation (falls vorhanden)
    tsa_verified = Column(Boolean, nullable=True)
    tsa_verification_error = Column(Text, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)

    # Fehler-Details
    error_message = Column(Text, nullable=True)
    error_details = Column(CrossDBJSON, nullable=True)

    # Triggered User (bei manueller Prüfung)
    triggered_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Relationships
    archive = relationship("DocumentArchive", backref="integrity_checks")
    company = relationship("Company", backref="gobd_integrity_checks")
    triggered_by = relationship("User", backref="triggered_integrity_checks")

    __table_args__ = (
        Index("ix_integrity_checks_archive", "archive_id"),
        Index("ix_integrity_checks_company", "company_id"),
        Index("ix_integrity_checks_status", "status"),
        Index("ix_integrity_checks_started_at", "started_at"),
        {"comment": "GoBD Integritätsprüfungen für Dokument-Archive"}
    )

    def __repr__(self) -> str:
        return f"<IntegrityCheck {self.id} archive={self.archive_id} status={self.status}>"


class TimestampAuthorityConfig(Base):
    """RFC 3161 Zeitstempel-Dienst Konfiguration.

    Erlaubt Konfiguration verschiedener TSA-Provider für
    qualifizierte Zeitstempel (eIDAS-konform).
    """
    __tablename__ = "gobd_tsa_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Provider-Info
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    provider_type = Column(
        String(50),
        nullable=False,
        default="rfc3161",
        comment="rfc3161, qualified_eidas"
    )

    # Endpoint-Konfiguration
    endpoint_url = Column(String(500), nullable=False)
    auth_type = Column(
        String(20),
        nullable=False,
        default="none",
        comment="none, basic, certificate"
    )
    # Credentials verschluesselt in separater Tabelle/Vault gespeichert
    credentials_vault_key = Column(
        String(255),
        nullable=True,
        comment="Key im Vault für Credentials"
    )

    # Zertifikats-Info (für Verifikation)
    issuer_certificate = Column(Text, nullable=True)
    certificate_chain = Column(Text, nullable=True)
    certificate_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Einstellungen
    timeout_seconds = Column(Integer, default=30, nullable=False)
    retry_count = Column(Integer, default=3, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Statistiken
    total_requests = Column(Integer, default=0, nullable=False)
    successful_requests = Column(Integer, default=0, nullable=False)
    failed_requests = Column(Integer, default=0, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="gobd_tsa_configs")

    __table_args__ = (
        Index("ix_tsa_configs_company", "company_id"),
        Index("ix_tsa_configs_is_default", "company_id", "is_default"),
        {"comment": "RFC 3161 TSA-Provider Konfiguration für qualifizierte Zeitstempel"}
    )

    def __repr__(self) -> str:
        return f"<TSAConfig {self.name} endpoint={self.endpoint_url[:50]}...>"


class RetentionDeletionRequest(Base):
    """Löschanfrage für abgelaufene Dokumente.

    Dokumente mit abgelaufener Aufbewahrungsfrist müssen
    explizit zur Löschung freigegeben werden (GoBD-Compliance).
    """
    __tablename__ = "gobd_retention_deletion_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    archive_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_archives.id", ondelete="CASCADE"),
        nullable=False
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False
    )

    # Anfrage-Details
    reason = Column(Text, nullable=False)
    retention_expired_at = Column(DateTime(timezone=True), nullable=False)

    # Status
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="pending, approved, rejected, executed"
    )

    # Anfrage
    requested_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    requested_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    # Freigabe
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    approval_comment = Column(Text, nullable=True)

    # Ablehnung
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    rejection_reason = Column(Text, nullable=True)

    # Ausführung
    executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_log = Column(CrossDBJSON, nullable=True)

    # Relationships
    archive = relationship("DocumentArchive", backref="deletion_requests")
    company = relationship("Company", backref="gobd_deletion_requests")
    requested_by = relationship("User", foreign_keys=[requested_by_id], backref="deletion_requests")
    approved_by = relationship("User", foreign_keys=[approved_by_id], backref="deletion_approvals")
    rejected_by = relationship("User", foreign_keys=[rejected_by_id], backref="deletion_rejections")

    __table_args__ = (
        Index("ix_deletion_requests_archive", "archive_id"),
        Index("ix_deletion_requests_company", "company_id"),
        Index("ix_deletion_requests_status", "status"),
        {"comment": "GoBD Löschanfragen für abgelaufene Dokumente"}
    )

    def __repr__(self) -> str:
        return f"<DeletionRequest {self.id} archive={self.archive_id} status={self.status}>"
