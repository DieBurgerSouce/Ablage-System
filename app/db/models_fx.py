# -*- coding: utf-8 -*-
"""Database models für Fremdwährungs-Management."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
import uuid

from sqlalchemy import (
    Column, String, Integer, DateTime, Date, Boolean, Numeric,
    ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.models import Base


class RateSource(str, Enum):
    """Quelle des Wechselkurses."""
    ECB = "ecb"
    MANUAL = "manual"


class ExchangeRate(Base):
    """Wechselkurse - ECB Referenzkurse oder manuell erfasst."""
    __tablename__ = "exchange_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    base_currency = Column(String(3), nullable=False, default="EUR")
    target_currency = Column(String(3), nullable=False)
    rate = Column(Numeric(18, 8), nullable=False)  # High precision for FX
    rate_date = Column(Date, nullable=False)
    source = Column(String(20), nullable=False, default="ecb")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("base_currency", "target_currency", "rate_date", "source",
                        name="uq_exchange_rate"),
        Index("ix_exchange_rates_lookup", "base_currency", "target_currency", "rate_date"),
    )


class FXGainLossEntry(Base):
    """Realisierte und unrealisierte Kursgewinne/-verluste."""
    __tablename__ = "fx_gain_loss_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    journal_entry_id = Column(UUID(as_uuid=True), ForeignKey("journal_entries.id"), nullable=True)
    original_currency = Column(String(3), nullable=False)
    original_amount = Column(Numeric(15, 2), nullable=False)
    booking_rate = Column(Numeric(18, 8), nullable=False)  # Rate at booking time
    settlement_rate = Column(Numeric(18, 8), nullable=False)  # Rate at settlement/revaluation
    gain_loss_amount = Column(Numeric(15, 2), nullable=False)  # EUR gain(+) / loss(-)
    gain_loss_account = Column(String(5), nullable=False)  # SKR03: 2650 or 2150
    realized = Column(Boolean, nullable=False, default=True)
    reference_document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_fx_gain_loss_company", "company_id"),
        Index("ix_fx_gain_loss_journal", "journal_entry_id"),
    )
