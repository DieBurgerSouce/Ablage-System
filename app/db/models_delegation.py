# -*- coding: utf-8 -*-
"""
Delegation Models fuer Ablage-System.

Ermoeglicht temporaere Rechte-Uebertragung:
- Krankheitsvertretung
- Urlaubsvertretung
- Projektbasierte Delegation
- Audit-Trail fuer Compliance

Phase 3.2 der Strategischen Roadmap (Januar 2026).
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class DelegationType(str, Enum):
    """Typ der Delegation."""
    FULL = "full"               # Volle Vertretung
    PARTIAL = "partial"         # Nur bestimmte Berechtigungen
    APPROVAL = "approval"       # Nur Genehmigungen
    READ_ONLY = "read_only"     # Nur Lesezugriff
    EMERGENCY = "emergency"     # Notfall-Zugriff


class DelegationStatus(str, Enum):
    """Status einer Delegation."""
    PENDING = "pending"         # Wartet auf Bestaetigung
    ACTIVE = "active"           # Aktiv
    EXPIRED = "expired"         # Abgelaufen
    REVOKED = "revoked"         # Widerrufen
    DECLINED = "declined"       # Abgelehnt vom Delegate


class DelegationReason(str, Enum):
    """Grund fuer die Delegation."""
    VACATION = "vacation"       # Urlaub
    ILLNESS = "illness"         # Krankheit
    PARENTAL_LEAVE = "parental_leave"  # Elternzeit
    BUSINESS_TRIP = "business_trip"    # Geschaeftsreise
    PROJECT = "project"         # Projektbasiert
    TRAINING = "training"       # Weiterbildung
    OTHER = "other"             # Sonstiges


# ============================================================================
# Delegation Model
# ============================================================================


class Delegation(Base):
    """Delegation von Rechten zwischen Benutzern.

    Ermoeglicht:
    - Temporaere Rechte-Uebertragung
    - Granulare Berechtigungssteuerung
    - Vollstaendiger Audit-Trail
    - Automatische Aktivierung/Deaktivierung

    Beispiel-Use-Cases:
    - Urlaubsvertretung: User A delegiert alle Genehmigungsrechte an User B
    - Projektteam: User A delegiert Dokumentzugriff fuer bestimmte Ordner
    - Notfall: Automatische Delegation bei laengerer Inaktivitaet
    """
    __tablename__ = "delegations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Delegator & Delegate
    delegator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User der seine Rechte delegiert"
    )
    delegate_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="User der die Rechte erhaelt"
    )

    # Company (Multi-Tenant)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Delegations-Typ
    delegation_type = Column(
        SQLAlchemyEnum(DelegationType, name="delegation_type"),
        nullable=False,
        default=DelegationType.PARTIAL
    )

    # Berechtigungen (bei PARTIAL)
    permissions = Column(
        CrossDBJSON,
        nullable=True,
        default=list,
        comment="Liste der delegierten Berechtigungen"
    )
    # Format: ["approvals:*", "documents:read", "documents:comment"]

    # Scope (Einschraenkung auf bestimmte Ressourcen)
    scope = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Einschraenkung auf bestimmte Ressourcen"
    )
    # Format: {"folders": ["uuid1", "uuid2"], "tags": ["wichtig"]}

    # Zeitliche Begrenzung
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)

    # Status
    status = Column(
        SQLAlchemyEnum(DelegationStatus, name="delegation_status"),
        nullable=False,
        default=DelegationStatus.PENDING
    )

    # Grund & Beschreibung
    reason = Column(
        SQLAlchemyEnum(DelegationReason, name="delegation_reason"),
        nullable=False,
        default=DelegationReason.OTHER
    )
    reason_text = Column(Text, nullable=True, comment="Freitext-Begruendung")
    notes = Column(Text, nullable=True, comment="Interne Notizen")

    # Bestaetigung
    requires_acceptance = Column(Boolean, default=True,
                                  comment="Muss Delegate bestaetigen?")
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    declined_at = Column(DateTime(timezone=True), nullable=True)
    decline_reason = Column(Text, nullable=True)

    # Widerruf
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    revoke_reason = Column(Text, nullable=True)

    # Benachrichtigungen
    notify_on_activation = Column(Boolean, default=True)
    notify_on_expiry = Column(Boolean, default=True)
    notify_on_usage = Column(Boolean, default=False,
                             comment="Bei jeder Nutzung benachrichtigen")

    # Nutzungsstatistik
    usage_count = Column(
        Integer,
        default=0,
        comment="Wie oft wurde die Delegation genutzt"
    )
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Einschraenkungen
    max_approvals = Column(
        Integer,
        nullable=True,
        comment="Max. Anzahl Genehmigungen (NULL = unbegrenzt)"
    )
    max_amount = Column(
        Float,
        nullable=True,
        comment="Max. Betrag pro Genehmigung"
    )

    # Metadata
    metadata_json = Column(CrossDBJSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    delegator = relationship(
        "User",
        foreign_keys=[delegator_id],
        backref="delegations_given"
    )
    delegate = relationship(
        "User",
        foreign_keys=[delegate_id],
        backref="delegations_received"
    )
    company = relationship("Company", backref="delegations")
    revoked_by = relationship(
        "User",
        foreign_keys=[revoked_by_id]
    )
    audit_logs = relationship(
        "DelegationAuditLog",
        back_populates="delegation",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_delegation_company_status", "company_id", "status"),
        Index("ix_delegation_delegator_active", "delegator_id", "status"),
        Index("ix_delegation_delegate_active", "delegate_id", "status"),
        Index("ix_delegation_validity", "valid_from", "valid_until"),
        CheckConstraint(
            "valid_until > valid_from",
            name="ck_delegation_validity"
        ),
        CheckConstraint(
            "delegator_id != delegate_id",
            name="ck_delegation_different_users"
        ),
    )

    @property
    def is_active(self) -> bool:
        """Prueft ob Delegation aktuell aktiv ist."""
        if self.status != DelegationStatus.ACTIVE:
            return False
        now = datetime.utcnow()
        return self.valid_from <= now <= self.valid_until

    @property
    def is_pending(self) -> bool:
        """Prueft ob auf Bestaetigung wartet."""
        return self.status == DelegationStatus.PENDING

    @property
    def days_remaining(self) -> int:
        """Verbleibende Tage bis zum Ablauf."""
        if not self.is_active:
            return 0
        delta = self.valid_until - datetime.utcnow()
        return max(0, delta.days)


# ============================================================================
# DelegationAuditLog Model
# ============================================================================


class DelegationAuditLog(Base):
    """Audit-Log fuer Delegations-Nutzung.

    Protokolliert jede Nutzung einer Delegation:
    - Welche Aktion wurde durchgefuehrt
    - Auf welche Ressource
    - Mit welchem Ergebnis
    """
    __tablename__ = "delegation_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Delegation
    delegation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("delegations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Aktion
    action = Column(String(100), nullable=False,
                    comment="z.B. approval:execute, document:read")
    resource_type = Column(String(50), nullable=True,
                           comment="z.B. document, approval, invoice")
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    resource_name = Column(String(255), nullable=True)

    # Ergebnis
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)

    # Kontext
    details = Column(CrossDBJSON, default=dict)
    # Format: {"amount": 1234.56, "vendor": "...", ...}

    # Request-Info
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(),
                        nullable=False, index=True)

    # Relationships
    delegation = relationship("Delegation", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_delegation_created", "delegation_id", "created_at"),
        Index("ix_audit_action", "action", "created_at"),
    )


# ============================================================================
# DelegationTemplate Model
# ============================================================================


class DelegationTemplate(Base):
    """Vorlage fuer wiederkehrende Delegationen.

    Ermoeglicht schnelle Erstellung von Standard-Delegationen:
    - Urlaubsvertretung Standard
    - Genehmigungs-Delegation
    - Lesezugriff-Delegation
    """
    __tablename__ = "delegation_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Company (Multi-Tenant)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Template-Details
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Delegations-Einstellungen
    delegation_type = Column(
        SQLAlchemyEnum(DelegationType, name="template_delegation_type"),
        nullable=False
    )
    permissions = Column(CrossDBJSON, default=list)
    scope = Column(CrossDBJSON, default=dict)

    # Default-Werte
    default_duration_days = Column(Integer, default=14)
    requires_acceptance = Column(Boolean, default=True)
    notify_on_activation = Column(Boolean, default=True)
    notify_on_usage = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)
    is_system = Column(Boolean, default=False,
                       comment="System-Template (nicht loeschbar)")

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())

    # Relationships
    company = relationship("Company", backref="delegation_templates")

    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_delegation_template_name"),
    )


