# -*- coding: utf-8 -*-
"""
Private Contract database models for Ablage-System.

P5.1: Vertragsmanagement fuer das Privat-Modul.
Unterstuetzt persoenliche Vertraege wie Mobilfunk, Versicherung,
Miete, Strom, Internet, Fitness, Streaming etc.

Feinpoliert und durchdacht - Enterprise-grade Private Contract Management.
"""

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON
from app.db.models_base import SoftDeleteMixin


class PrivatContractCategory(str, Enum):
    """Vertragskategorie fuer private Vertraege."""
    MOBILFUNK = "mobilfunk"
    INTERNET = "internet"
    STROM = "strom"
    GAS = "gas"
    WASSER = "wasser"
    VERSICHERUNG = "versicherung"
    MIETE = "miete"
    FITNESS = "fitness"
    STREAMING = "streaming"
    ZEITSCHRIFT = "zeitschrift"
    VEREIN = "verein"
    CLOUD_SPEICHER = "cloud_speicher"
    SOFTWARE = "software"
    LEASING = "leasing"
    WARTUNG = "wartung"
    SONSTIGE = "sonstige"


class PrivatContractStatus(str, Enum):
    """Status eines privaten Vertrags."""
    AKTIV = "aktiv"
    GEKUENDIGT = "gekuendigt"
    AUSGELAUFEN = "ausgelaufen"
    ENTWURF = "entwurf"


class PrivatContract(SoftDeleteMixin, Base):
    """
    Private Vertraege im Privat-Modul.

    Trackt persoenliche Vertraege mit automatischer
    Kuendigungsfrist-Berechnung und Erinnerungen.
    """
    __tablename__ = "privat_contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(
        UUID(as_uuid=True),
        ForeignKey("privat_spaces.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Vertragspartner
    partner_name = Column(String(255), nullable=False)
    contract_number = Column(String(100), nullable=True)

    # Klassifikation
    category = Column(String(50), nullable=False, default=PrivatContractCategory.SONSTIGE.value)
    status = Column(String(30), nullable=False, default=PrivatContractStatus.AKTIV.value)

    # Beschreibung
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Laufzeit
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    duration_months = Column(Integer, nullable=True)

    # Kuendigung
    cancellation_notice_days = Column(Integer, nullable=True)
    next_cancellation_date = Column(Date, nullable=True)
    auto_renewal = Column(Boolean, default=False)
    renewal_period_months = Column(Integer, nullable=True)

    # Kosten
    monthly_cost = Column(Numeric(10, 2), nullable=True)
    yearly_cost = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), default="EUR")

    # OCR-Extraktion
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    extraction_confidence = Column(Numeric(5, 4), nullable=True)
    raw_extracted_fields = Column(CrossDBJSON, default=dict)

    # Erinnerungen
    reminder_days_before = Column(CrossDBJSON, default=lambda: [30, 14, 7])
    last_reminder_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Notizen
    notes = Column(Text, nullable=True)
    tags = Column(CrossDBJSON, default=list)

    # Status
    is_active = Column(Boolean, default=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    space = relationship("PrivatSpace", backref="contracts")
    document = relationship("Document", backref="privat_contracts")

    __table_args__ = (
        Index("ix_privat_contracts_space_id", "space_id"),
        Index("ix_privat_contracts_category", "category"),
        Index("ix_privat_contracts_status", "status"),
        Index("ix_privat_contracts_next_cancel", "next_cancellation_date"),
        Index("ix_privat_contracts_is_active", "is_active"),
    )


class PrivatContractReminder(Base):
    """
    Erinnerungen fuer private Vertraege.

    Speichert geplante und gesendete Erinnerungen
    fuer Kuendigungsfristen.
    """
    __tablename__ = "privat_contract_reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(
        UUID(as_uuid=True),
        ForeignKey("privat_contracts.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Erinnerungsdetails
    reminder_date = Column(Date, nullable=False)
    days_before_deadline = Column(Integer, nullable=False)
    reminder_type = Column(String(50), default="kuendigungsfrist")

    # Status
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    alert_id = Column(UUID(as_uuid=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    contract = relationship("PrivatContract", backref="reminders")

    __table_args__ = (
        Index("ix_privat_contract_reminders_contract", "contract_id"),
        Index("ix_privat_contract_reminders_date", "reminder_date"),
        Index("ix_privat_contract_reminders_unsent", "is_sent", "reminder_date"),
    )
