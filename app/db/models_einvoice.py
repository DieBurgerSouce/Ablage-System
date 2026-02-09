# -*- coding: utf-8 -*-
"""
E-Invoice Database Models - E-Rechnung 2025 Compliance.

Erweiterte Modelle fuer:
- E-Invoice Status Tracking (Peppol/Email)
- Transmission History
- Peppol Participant Registry
- Acknowledgment Tracking

Migration: 148 (add_einvoice_transmission)
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, ForeignKey, Index,
    Integer, Numeric, UniqueConstraint, CheckConstraint, event
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.models import Base, CrossDBJSON


# =============================================================================
# ENUMS
# =============================================================================

class EInvoiceTransmissionStatus(str, Enum):
    """Status einer E-Rechnungsuebertragung."""
    DRAFT = "draft"  # Entwurf, noch nicht gesendet
    QUEUED = "queued"  # In Warteschlange fuer Versand
    SENDING = "sending"  # Wird gerade gesendet
    SENT = "sent"  # Erfolgreich gesendet
    DELIVERED = "delivered"  # Zugestellt (Empfaenger bestaetigt)
    ACKNOWLEDGED = "acknowledged"  # Geschaeftlich bestaetigt (MDN)
    REJECTED = "rejected"  # Abgelehnt durch Empfaenger
    FAILED = "failed"  # Technischer Fehler beim Versand
    CANCELLED = "cancelled"  # Manuell abgebrochen


class EInvoiceTransmissionChannel(str, Enum):
    """Uebertragungskanal fuer E-Rechnungen."""
    PEPPOL = "peppol"  # Peppol AS4 Network
    EMAIL = "email"  # Fallback via E-Mail
    PORTAL = "portal"  # Upload auf Behoerdenportal
    MANUAL = "manual"  # Manueller Download/Upload
    API = "api"  # Direkter API-Aufruf


class PeppolDocumentType(str, Enum):
    """Peppol Document Types (BIS 3.0)."""
    INVOICE = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2::Invoice"
    CREDIT_NOTE = "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2::CreditNote"
    INVOICE_RESPONSE = "urn:oasis:names:specification:ubl:schema:xsd:ApplicationResponse-2"


# =============================================================================
# E-INVOICE TRANSMISSION
# =============================================================================

class EInvoiceTransmission(Base):
    """
    Tracking einer E-Rechnungsuebertragung.

    Speichert alle Versandversuche und deren Status.
    Pro EInvoice kann es mehrere Transmissions geben (Retry, etc.).
    """
    __tablename__ = "einvoice_transmissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenz zur E-Rechnung
    einvoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("einvoice_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Transmission Details
    channel = Column(String(20), nullable=False)  # EInvoiceTransmissionChannel
    status = Column(String(30), nullable=False, default=EInvoiceTransmissionStatus.DRAFT.value)

    # Peppol-spezifisch
    peppol_message_id = Column(String(255), nullable=True, unique=True)  # AS4 Message ID
    peppol_conversation_id = Column(String(255), nullable=True)  # Conversation ID
    peppol_endpoint_id = Column(String(100), nullable=True)  # Empfaenger Peppol ID
    peppol_process_id = Column(String(255), nullable=True)  # Peppol Process ID
    peppol_document_type = Column(String(255), nullable=True)  # Document Type ID

    # Email-spezifisch (Fallback)
    email_recipient = Column(String(255), nullable=True)
    email_message_id = Column(String(255), nullable=True)
    email_subject = Column(String(500), nullable=True)

    # Timing
    queued_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    # Response/Acknowledgment
    mdn_received = Column(Boolean, default=False)  # Message Disposition Notification
    mdn_content = Column(Text, nullable=True)  # MDN XML/Content
    business_response = Column(CrossDBJSON, default=dict)  # Invoice Response Details

    # Fehlerbehandlung
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_details = Column(CrossDBJSON, default=dict)

    # Audit
    initiated_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)

    # Relationships
    einvoice = relationship("EInvoiceDocument", back_populates="transmissions")
    initiated_by = relationship("User", foreign_keys=[initiated_by_id])

    __table_args__ = (
        Index("ix_einvoice_transmissions_status", "status"),
        Index("ix_einvoice_transmissions_channel", "channel"),
        Index("ix_einvoice_transmissions_company_status", "company_id", "status"),
        Index("ix_einvoice_transmissions_peppol_msg", "peppol_message_id"),
    )

    def mark_sent(self) -> None:
        """Markiert als gesendet."""
        self.status = EInvoiceTransmissionStatus.SENT.value
        self.sent_at = datetime.now(timezone.utc)

    def mark_delivered(self) -> None:
        """Markiert als zugestellt."""
        self.status = EInvoiceTransmissionStatus.DELIVERED.value
        self.delivered_at = datetime.now(timezone.utc)

    def mark_acknowledged(self, mdn_content: Optional[str] = None) -> None:
        """Markiert als bestaetigt."""
        self.status = EInvoiceTransmissionStatus.ACKNOWLEDGED.value
        self.acknowledged_at = datetime.now(timezone.utc)
        self.mdn_received = True
        if mdn_content:
            self.mdn_content = mdn_content

    def mark_failed(self, error: str, error_code: Optional[str] = None) -> None:
        """Markiert als fehlgeschlagen."""
        self.status = EInvoiceTransmissionStatus.FAILED.value
        self.last_error = error
        self.error_code = error_code
        self.retry_count += 1

    def can_retry(self) -> bool:
        """Prueft ob Retry moeglich ist."""
        return self.retry_count < self.max_retries and self.status == EInvoiceTransmissionStatus.FAILED.value


# =============================================================================
# PEPPOL PARTICIPANT REGISTRY
# =============================================================================

class PeppolParticipant(Base):
    """
    Peppol Teilnehmer-Registry (Cache).

    Speichert bekannte Peppol-Teilnehmer fuer schnellen Lookup.
    """
    __tablename__ = "peppol_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Peppol Identifiers
    participant_id = Column(String(100), nullable=False, unique=True)  # z.B. "0204:04011000-12345-67"
    scheme_id = Column(String(20), nullable=False, default="0204")  # Leitweg-ID Scheme
    endpoint_url = Column(String(500), nullable=True)  # SMP Endpoint

    # Entity Reference (optional - wenn lokaler Geschaeftskontakt)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)

    # Metadata from SMP
    participant_name = Column(String(500), nullable=True)
    supported_document_types = Column(CrossDBJSON, default=list)  # Liste von Document Type IDs
    capabilities = Column(CrossDBJSON, default=dict)  # SMP Capabilities

    # Status
    is_active = Column(Boolean, default=True)
    last_verified_at = Column(DateTime(timezone=True), nullable=True)
    verification_error = Column(Text, nullable=True)

    # Audit
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)

    # Relationships - Entity disabled: FK references "entities.id" but table is "business_entities"
    # entity = relationship("Entity", backref="peppol_participants")

    __table_args__ = (
        Index("ix_peppol_participants_scheme_id", "scheme_id", "participant_id"),
        Index("ix_peppol_participants_entity", "entity_id"),
    )


# =============================================================================
# INCOMING E-INVOICE
# =============================================================================

class IncomingEInvoice(Base):
    """
    Eingehende E-Rechnungen (Empfang via Peppol/Email/Portal).

    Speichert empfangene E-Rechnungen vor Verarbeitung.
    """
    __tablename__ = "incoming_einvoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Herkunft
    channel = Column(String(20), nullable=False)  # peppol, email, portal
    received_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Peppol-spezifisch
    peppol_message_id = Column(String(255), nullable=True, unique=True)
    peppol_sender_id = Column(String(100), nullable=True)
    peppol_document_type = Column(String(255), nullable=True)

    # Email-spezifisch
    email_sender = Column(String(255), nullable=True)
    email_subject = Column(String(500), nullable=True)
    email_message_id = Column(String(255), nullable=True)

    # Content
    format = Column(String(50), nullable=False)  # xrechnung_cii, xrechnung_ubl, zugferd
    xml_content = Column(Text, nullable=False)
    xml_hash = Column(String(64), nullable=False)
    original_filename = Column(String(255), nullable=True)
    has_pdf_attachment = Column(Boolean, default=False)
    pdf_storage_path = Column(String(500), nullable=True)

    # Extracted Basic Data (fuer schnelle Uebersicht)
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(DateTime, nullable=True)
    seller_name = Column(String(255), nullable=True)
    buyer_reference = Column(String(100), nullable=True)  # Leitweg-ID
    total_amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), default="EUR")

    # Validation
    is_valid = Column(Boolean, nullable=True)
    validation_errors = Column(CrossDBJSON, default=list)
    validation_warnings = Column(CrossDBJSON, default=list)

    # Processing Status
    status = Column(String(30), nullable=False, default="received")  # received, validated, linked, processed, rejected
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Linking
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)  # Verknuepftes Dokument
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)  # Erkannter Absender

    # Audit
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    processed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)

    # Relationships
    document = relationship("Document", backref="incoming_einvoice")
    # Entity disabled: FK references "entities.id" but table is "business_entities"
    # entity = relationship("Entity", backref="incoming_einvoices")
    processed_by = relationship("User", foreign_keys=[processed_by_id])

    __table_args__ = (
        Index("ix_incoming_einvoices_status", "status"),
        Index("ix_incoming_einvoices_company_status", "company_id", "status"),
        Index("ix_incoming_einvoices_invoice_number", "invoice_number"),
        Index("ix_incoming_einvoices_received_at", "received_at"),
    )


# =============================================================================
# EXTEND EINVOICE DOCUMENT WITH TRANSMISSION RELATIONSHIP
# =============================================================================

# Note: This needs to be added to the existing EInvoiceDocument model in models.py
# via a separate migration or by extending the model directly.
#
# Add to EInvoiceDocument:
# transmissions = relationship("EInvoiceTransmission", back_populates="einvoice", cascade="all, delete-orphan")
