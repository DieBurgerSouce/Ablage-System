# -*- coding: utf-8 -*-
"""
Communication Hub Database Models.

Vision 2026+ Feature #1: Kommunikations-Hub (360° Entity View)
Modelle für Telefon-Notizen und Kommunikationshistorie.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class CommunicationType(str, Enum):
    """Typ der Kommunikation."""
    PHONE_CALL = "phone_call"          # Telefonat
    EMAIL = "email"                    # E-Mail
    MEETING = "meeting"                # Meeting
    VIDEO_CALL = "video_call"          # Videoanruf
    LETTER = "letter"                  # Brief
    FAX = "fax"                        # Fax
    CHAT = "chat"                      # Chat/Messenger
    INTERNAL_NOTE = "internal_note"    # Interne Notiz
    OTHER = "other"                    # Sonstiges


class CommunicationDirection(str, Enum):
    """Richtung der Kommunikation."""
    INBOUND = "inbound"    # Eingehend (Kunde/Lieferant -> Uns)
    OUTBOUND = "outbound"  # Ausgehend (Wir -> Kunde/Lieferant)
    INTERNAL = "internal"  # Intern


class CommunicationSentiment(str, Enum):
    """Stimmung/Ergebnis der Kommunikation."""
    POSITIVE = "positive"     # Positiv (zufrieden, Lob, Bestätigung)
    NEUTRAL = "neutral"       # Neutral (Informationsaustausch)
    NEGATIVE = "negative"     # Negativ (Beschwerde, Problem)
    ESCALATION = "escalation" # Eskalation erforderlich


class PhoneNote(Base):
    """
    Telefon-Notiz für Geschäftspartner.

    Erfasst alle Telefonkontakte mit Kunden/Lieferanten
    inklusive Gespraechsnotizen und Follow-ups.
    """
    __tablename__ = "phone_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Entity Reference (Geschäftspartner)
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Call Details
    call_type = Column(
        String(20),
        nullable=False,
        default=CommunicationType.PHONE_CALL.value,
    )
    direction = Column(
        String(20),
        nullable=False,
        default=CommunicationDirection.INBOUND.value,
    )

    # Contact Information
    contact_person = Column(String(255), nullable=True)  # Name des Ansprechpartners
    phone_number = Column(String(50), nullable=True)     # Telefonnummer
    duration_minutes = Column(Integer, nullable=True)    # Gespraechsdauer

    # Content
    subject = Column(String(255), nullable=False)        # Betreff
    notes = Column(Text, nullable=True)                  # Gespraechsnotizen
    summary = Column(String(500), nullable=True)         # Kurzzusammenfassung

    # Sentiment/Outcome
    sentiment = Column(
        String(20),
        nullable=True,
        default=CommunicationSentiment.NEUTRAL.value,
    )

    # Follow-up
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(DateTime(timezone=True), nullable=True)
    follow_up_notes = Column(Text, nullable=True)
    follow_up_completed = Column(Boolean, default=False)
    follow_up_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Related Documents (optional)
    related_document_ids = Column(CrossDBJSON, default=list)

    # Metadata
    tags = Column(CrossDBJSON, default=list)
    custom_fields = Column(CrossDBJSON, default=dict)

    # Timestamps
    call_datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # User References
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_to_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    entity = relationship("BusinessEntity", backref="phone_notes")
    company = relationship("Company", backref="phone_notes")
    created_by = relationship("User", foreign_keys=[created_by_id])
    assigned_to = relationship("User", foreign_keys=[assigned_to_id])

    # Indexes
    __table_args__ = (
        Index("ix_phone_notes_entity_company", "entity_id", "company_id"),
        Index("ix_phone_notes_call_datetime", "call_datetime"),
        Index("ix_phone_notes_follow_up", "follow_up_required", "follow_up_completed"),
        Index("ix_phone_notes_created_by", "created_by_id"),
        CheckConstraint(
            "call_type IN ('phone_call', 'email', 'meeting', 'video_call', 'letter', 'fax', 'chat', 'internal_note', 'other')",
            name="ck_phone_notes_call_type",
        ),
        CheckConstraint(
            "direction IN ('inbound', 'outbound', 'internal')",
            name="ck_phone_notes_direction",
        ),
        CheckConstraint(
            "sentiment IN ('positive', 'neutral', 'negative', 'escalation')",
            name="ck_phone_notes_sentiment",
        ),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "entity_id": str(self.entity_id),
            "company_id": str(self.company_id),
            "call_type": self.call_type,
            "direction": self.direction,
            "contact_person": self.contact_person,
            "phone_number": self.phone_number,
            "duration_minutes": self.duration_minutes,
            "subject": self.subject,
            "notes": self.notes,
            "summary": self.summary,
            "sentiment": self.sentiment,
            "follow_up_required": self.follow_up_required,
            "follow_up_date": self.follow_up_date.isoformat() if self.follow_up_date else None,
            "follow_up_notes": self.follow_up_notes,
            "follow_up_completed": self.follow_up_completed,
            "related_document_ids": self.related_document_ids or [],
            "tags": self.tags or [],
            "call_datetime": self.call_datetime.isoformat() if self.call_datetime else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by_id": str(self.created_by_id) if self.created_by_id else None,
            "assigned_to_id": str(self.assigned_to_id) if self.assigned_to_id else None,
        }


class CommunicationSummary(Base):
    """
    Aggregierte Kommunikations-Zusammenfassung pro Entity.

    Wird automatisch aktualisiert für schnelle Dashboard-Anzeigen.
    """
    __tablename__ = "communication_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Entity Reference
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Communication Counts
    total_communications = Column(Integer, default=0)
    phone_calls_count = Column(Integer, default=0)
    emails_count = Column(Integer, default=0)
    meetings_count = Column(Integer, default=0)
    other_count = Column(Integer, default=0)

    # Direction Counts
    inbound_count = Column(Integer, default=0)
    outbound_count = Column(Integer, default=0)

    # Sentiment Breakdown
    positive_count = Column(Integer, default=0)
    neutral_count = Column(Integer, default=0)
    negative_count = Column(Integer, default=0)
    escalation_count = Column(Integer, default=0)

    # Open Items
    open_follow_ups = Column(Integer, default=0)
    overdue_follow_ups = Column(Integer, default=0)

    # Last Communication
    last_communication_at = Column(DateTime(timezone=True), nullable=True)
    last_communication_type = Column(String(20), nullable=True)
    last_communication_sentiment = Column(String(20), nullable=True)

    # Timestamps
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    entity = relationship("BusinessEntity", backref="communication_summary", uselist=False)

    __table_args__ = (
        Index("ix_comm_summary_entity", "entity_id"),
        Index("ix_comm_summary_company", "company_id"),
    )
