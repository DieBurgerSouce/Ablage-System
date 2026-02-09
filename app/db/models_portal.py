"""
SQLAlchemy Models fuer Kundenportal (Phase 5.2).

Separate Authentifizierung und Datenhaltung fuer Kunden-Self-Service.
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, List
from enum import Enum
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, Boolean, Text,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class PortalUserStatus(str, Enum):
    """Status eines Portal-Benutzers."""
    PENDING = "pending"          # Einladung versendet
    ACTIVE = "active"            # Aktiv
    SUSPENDED = "suspended"      # Temporaer gesperrt
    DEACTIVATED = "deactivated"  # Deaktiviert


class ComplaintStatus(str, Enum):
    """Status einer Reklamation."""
    NEW = "new"
    IN_REVIEW = "in_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    RESOLVED = "resolved"
    CLOSED = "closed"


class ComplaintType(str, Enum):
    """Typ einer Reklamation."""
    INVOICE_ERROR = "invoice_error"        # Rechnungsfehler
    DELIVERY_ISSUE = "delivery_issue"      # Lieferproblem
    QUALITY_ISSUE = "quality_issue"        # Qualitaetsmangel
    PAYMENT_DISPUTE = "payment_dispute"    # Zahlungsstreit
    OTHER = "other"                        # Sonstiges


class MessageDirection(str, Enum):
    """Richtung einer Nachricht."""
    INBOUND = "inbound"    # Vom Kunden
    OUTBOUND = "outbound"  # An den Kunden


class PortalUser(Base):
    """
    Kunden-Account fuer das Self-Service Portal.

    Separater Account-Typ von internen Users.
    Wird mit einem Entity (Kunde/Lieferant) verknuepft.
    """
    __tablename__ = "portal_users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfung mit Entity (Kunde oder Lieferant)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Verknuepfung mit Company
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Login-Daten
    email = Column(String(255), nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)

    # Kontaktdaten
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone = Column(String(50))
    position = Column(String(100))  # Position beim Kunden

    # Status und Berechtigungen
    status = Column(
        String(20),
        default=PortalUserStatus.PENDING,
        nullable=False
    )
    can_view_invoices = Column(Boolean, default=True)
    can_confirm_payments = Column(Boolean, default=True)
    can_submit_complaints = Column(Boolean, default=True)
    can_upload_documents = Column(Boolean, default=True)
    can_view_all_entity_data = Column(Boolean, default=False)  # Alle Daten des Kunden sehen

    # Einladung
    invitation_token = Column(String(255), unique=True)
    invitation_sent_at = Column(DateTime(timezone=True))
    invitation_expires_at = Column(DateTime(timezone=True))
    invited_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Sicherheit
    password_changed_at = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))

    # Metadaten
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships (keine back_populates um BusinessEntity nicht zu modifizieren)
    entity = relationship("BusinessEntity")
    company = relationship("Company")
    invited_by = relationship("User", foreign_keys=[invited_by_id])
    complaints = relationship("PortalComplaint", back_populates="submitted_by")
    messages = relationship("PortalMessage", back_populates="portal_user")
    uploaded_documents = relationship("PortalDocument", back_populates="uploaded_by")

    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_portal_users_company_email"),
        Index("ix_portal_users_entity_status", "entity_id", "status"),
    )


class PortalSession(Base):
    """
    Session-Tracking fuer Portal-Benutzer.

    Separate Session-Verwaltung von internen Users.
    """
    __tablename__ = "portal_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    portal_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Session-Token (gehashed)
    session_token_hash = Column(String(255), nullable=False, index=True)
    refresh_token_hash = Column(String(255), index=True)

    # Metadaten
    user_agent = Column(String(500))
    ip_address = Column(String(45))  # IPv6-kompatibel

    # Gueltigkeiten
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)
    refresh_expires_at = Column(DateTime(timezone=True))
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now())

    # Revokation
    revoked_at = Column(DateTime(timezone=True))
    revoked_reason = Column(String(100))

    # Relationships
    portal_user = relationship("PortalUser")

    __table_args__ = (
        Index("ix_portal_sessions_user_active", "portal_user_id", "expires_at"),
    )


class PortalComplaint(Base):
    """
    Reklamationen von Kunden.

    Ermoeglicht Self-Service Reklamationseinreichung mit Tracking.
    """
    __tablename__ = "portal_complaints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfungen
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
    submitted_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        index=True
    )

    # Optionale Verknuepfung mit Dokument/Rechnung
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        index=True
    )
    invoice_tracking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="SET NULL"),
        index=True
    )

    # Referenznummer
    reference_number = Column(String(50), unique=True, nullable=False)

    # Reklamationsdetails
    complaint_type = Column(String(30), nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Status-Workflow
    status = Column(String(20), default=ComplaintStatus.NEW, nullable=False)
    priority = Column(String(20), default="normal")  # low, normal, high, urgent

    # Interne Bearbeitung
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    internal_notes = Column(Text)  # Nur fuer interne Bearbeiter sichtbar
    resolution = Column(Text)      # Loesung/Antwort

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    first_response_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))

    # Zusaetzliche Daten
    complaint_metadata = Column("metadata", CrossDBJSON, default=dict)  # Flexible zusaetzliche Daten

    # Relationships
    company = relationship("Company")
    entity = relationship("BusinessEntity")
    submitted_by = relationship("PortalUser", back_populates="complaints")
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])
    document = relationship("Document")
    messages = relationship("PortalMessage", back_populates="complaint")

    __table_args__ = (
        Index("ix_portal_complaints_status", "company_id", "status"),
        Index("ix_portal_complaints_entity", "entity_id", "status"),
    )


class PortalMessage(Base):
    """
    Kommunikation zwischen Kunde und Unternehmen.

    Kann mit Reklamation verknuepft sein oder allgemeine Kommunikation.
    """
    __tablename__ = "portal_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfungen
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

    # Optional: Verknuepfung mit Reklamation
    complaint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_complaints.id", ondelete="CASCADE"),
        index=True
    )

    # Absender/Empfaenger
    portal_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        index=True
    )
    internal_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # Nachrichteninhalt
    direction = Column(String(20), nullable=False)  # inbound/outbound
    subject = Column(String(255))
    content = Column(Text, nullable=False)

    # Anhaenge
    attachments = Column(CrossDBJSON, default=list)  # Liste von Datei-IDs

    # Status
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True))

    # Metadaten
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company")
    entity = relationship("BusinessEntity")
    complaint = relationship("PortalComplaint", back_populates="messages")
    portal_user = relationship("PortalUser", back_populates="messages")
    internal_user = relationship("User", foreign_keys=[internal_user_id])

    __table_args__ = (
        Index("ix_portal_messages_conversation", "entity_id", "created_at"),
        Index("ix_portal_messages_unread", "entity_id", "is_read"),
    )


class PortalDocument(Base):
    """
    Vom Kunden hochgeladene Dokumente.

    Separate Tabelle fuer klare Trennung und Tracking.
    """
    __tablename__ = "portal_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfungen
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
    uploaded_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        index=True
    )

    # Optionale Verknuepfung mit Reklamation oder Nachricht
    complaint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_complaints.id", ondelete="SET NULL")
    )
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_messages.id", ondelete="SET NULL")
    )

    # Das eigentliche Dokument (nach Verarbeitung)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL")
    )

    # Dateiinformationen
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    storage_path = Column(String(500))  # Pfad im Storage

    # Beschreibung vom Kunden
    description = Column(Text)
    document_type = Column(String(50))  # Vom Kunden angegebener Typ

    # Verarbeitungsstatus
    processing_status = Column(String(20), default="pending")  # pending, processing, completed, failed
    processed_at = Column(DateTime(timezone=True))

    # Metadaten
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company")
    entity = relationship("BusinessEntity")
    uploaded_by = relationship("PortalUser", back_populates="uploaded_documents")
    complaint = relationship("PortalComplaint")
    message = relationship("PortalMessage")
    document = relationship("Document")

    __table_args__ = (
        Index("ix_portal_documents_entity", "entity_id", "created_at"),
    )


class PortalPaymentConfirmation(Base):
    """
    Zahlungsbestaetigungen von Kunden.

    Kunden koennen im Portal angeben, dass sie bezahlt haben.
    """
    __tablename__ = "portal_payment_confirmations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Verknuepfungen
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
    portal_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("portal_users.id", ondelete="SET NULL"),
        index=True
    )

    # Verknuepfung mit Rechnung
    invoice_tracking_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoice_tracking.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Zahlungsdetails (vom Kunden angegeben)
    payment_date = Column(DateTime(timezone=True), nullable=False)
    payment_amount = Column(String(50), nullable=False)  # Als String fuer Flexibilitaet
    payment_reference = Column(String(255))  # Verwendungszweck
    payment_method = Column(String(50))  # bank_transfer, paypal, etc.

    # Anhaenge (z.B. Zahlungsbeleg)
    attachment_ids = Column(CrossDBJSON, default=list)

    # Bearbeitungsstatus
    status = Column(String(20), default="pending")  # pending, verified, rejected
    verified_at = Column(DateTime(timezone=True))
    verified_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL")
    )
    rejection_reason = Column(Text)

    # Metadaten
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company")
    entity = relationship("BusinessEntity")
    portal_user = relationship("PortalUser")
    verified_by = relationship("User", foreign_keys=[verified_by_id])

    __table_args__ = (
        Index("ix_portal_payment_confirmations_invoice", "invoice_tracking_id"),
        Index("ix_portal_payment_confirmations_status", "company_id", "status"),
    )
