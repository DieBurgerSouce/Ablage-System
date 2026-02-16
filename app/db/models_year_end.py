# -*- coding: utf-8 -*-
"""
Year-End Closing (Jahresabschluss) database models for Ablage-System.

Jahresabschluss-Assistent mit:
- Session-Management für Jahresabschluss-Durchlaeufe
- Checklisten-Items für Vollständigkeitsprüfung
- Lücken-Erkennung und -Nachverfolgung

Feinpoliert und durchdacht - Enterprise-grade Jahresabschluss.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    Numeric,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class YearEndStatus(str, Enum):
    """Status eines Jahresabschluss-Durchlaufs."""
    DRAFT = "draft"                # Entwurf
    IN_PROGRESS = "in_progress"    # In Bearbeitung
    REVIEW = "review"              # Zur Prüfung
    COMPLETED = "completed"        # Abgeschlossen
    EXPORTED = "exported"          # Exportiert


class CheckItemStatus(str, Enum):
    """Status eines einzelnen Prüfpunkts."""
    PENDING = "pending"      # Ausstehend
    PASSED = "passed"        # Bestanden
    WARNING = "warning"      # Warnung
    FAILED = "failed"        # Fehlgeschlagen
    SKIPPED = "skipped"      # Übersprungen


class GapCategory(str, Enum):
    """Kategorie einer erkannten Lücke."""
    MISSING_RECEIPT = "missing_receipt"                  # Fehlender Beleg
    UNMATCHED_TRANSACTION = "unmatched_transaction"      # Nicht zugeordnete Transaktion
    MISSING_INVOICE = "missing_invoice"                  # Fehlende Rechnung
    INCOMPLETE_DATA = "incomplete_data"                  # Unvollständige Daten
    AMOUNT_DISCREPANCY = "amount_discrepancy"            # Betragsdifferenz


class YearEndSession(Base):
    """
    Jahresabschluss-Session.

    Repraesentiert einen kompletten Jahresabschluss-Durchlauf
    für ein bestimmtes Geschäftsjahr und Unternehmen.
    """
    __tablename__ = "year_end_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Geschäftsjahr
    fiscal_year = Column(Integer, nullable=False)

    # Status
    status = Column(
        String(20),
        nullable=False,
        default=YearEndStatus.DRAFT.value,
    )

    # Initiator
    started_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)

    # Abschluss
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Fortschritt
    progress_percent = Column(Integer, default=0)
    total_checks = Column(Integer, default=0)
    passed_checks = Column(Integer, default=0)
    warning_checks = Column(Integer, default=0)
    failed_checks = Column(Integer, default=0)

    # Notizen
    notes = Column(Text, nullable=True)

    # Bericht
    report_generated_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    company = relationship("Company", backref="year_end_sessions")
    started_by_user = relationship("User", foreign_keys=[started_by])
    check_items = relationship(
        "YearEndCheckItem",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="YearEndCheckItem.sort_order",
    )
    gaps = relationship(
        "YearEndGap",
        back_populates="session",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_year_end_sessions_company_year",
            "company_id",
            "fiscal_year",
        ),
    )


class YearEndCheckItem(Base):
    """
    Einzelner Prüfpunkt im Jahresabschluss.

    Repraesentiert einen konkreten Prüfschritt wie
    'Eingangsrechnungen Januar vollständig' oder 'Bankabgleich durchgeführt'.
    """
    __tablename__ = "year_end_check_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session-Zuordnung
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("year_end_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Prüfpunkt-Details
    category = Column(String(100), nullable=False)
    check_name = Column(String(255), nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default=CheckItemStatus.PENDING.value,
    )
    details_json = Column(CrossDBJSON, nullable=True)

    # Prüfung
    checked_at = Column(DateTime(timezone=True), nullable=True)

    # Loesung
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Sortierung
    sort_order = Column(Integer, default=0)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    session = relationship("YearEndSession", back_populates="check_items")
    resolved_by_user = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        Index("ix_year_end_check_items_session_id", "session_id"),
    )


class YearEndGap(Base):
    """
    Erkannte Lücke oder Unstimmigkeit im Jahresabschluss.

    Speichert identifizierte Probleme wie fehlende Belege,
    nicht zugeordnete Transaktionen oder Betragsdifferenzen.
    """
    __tablename__ = "year_end_gaps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session-Zuordnung
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("year_end_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Multi-tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Lücken-Details
    category = Column(
        String(30),
        nullable=False,
    )
    month = Column(Integer, nullable=True)
    description = Column(Text, nullable=False)
    amount = Column(Numeric(12, 2), nullable=True)

    # Verknüpfungen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    transaction_reference = Column(String(255), nullable=True)

    # Loesung
    is_resolved = Column(Boolean, default=False)
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    session = relationship("YearEndSession", back_populates="gaps")
    document = relationship("Document", backref="year_end_gaps")
    resolved_by_user = relationship("User", foreign_keys=[resolved_by])

    __table_args__ = (
        Index("ix_year_end_gaps_session_id", "session_id"),
        Index("ix_year_end_gaps_category", "category"),
        Index("ix_year_end_gaps_month", "month"),
    )
