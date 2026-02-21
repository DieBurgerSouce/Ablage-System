# -*- coding: utf-8 -*-
"""Change Data Capture (CDC) Models.

Erfasst Datenbankänderungen auf Tabellenebene für Echtzeit-Sync
mit DATEV/Lexware und Event-Streaming.

Satellite-Modell - importiert Base und CrossDBJSON aus app.db.models.
"""

import uuid
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    BigInteger,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class ChangeDataCaptureLog(Base):
    """
    CDC-Protokoll für Tabellenänderungen.

    Erfasst INSERT/UPDATE/DELETE-Operationen auf überwachten Tabellen
    via PostgreSQL-Trigger. Dient als Grundlage für Event-Streaming
    und Echtzeit-Synchronisation mit externen Systemen.
    """
    __tablename__ = "change_data_capture_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Quell-Tabelle und Datensatz
    source_table = Column(String(100), nullable=False, index=True)
    source_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Operation: INSERT, UPDATE, DELETE
    operation = Column(String(10), nullable=False, index=True)

    # Daten-Snapshots
    old_data = Column(CrossDBJSON, nullable=True)
    new_data = Column(CrossDBJSON, nullable=True)
    changed_columns = Column(CrossDBJSON, default=list)

    # Globale Reihenfolge (autoincrement via Sequence)
    sequence_number = Column(
        BigInteger,
        autoincrement=True,
        unique=True,
        nullable=False,
    )

    # Consumer-Tracking
    processed = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    consumer_id = Column(String(100), nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Benutzer-Tracking
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # PostgreSQL Transaction-ID für Gruppierung
    transaction_id = Column(String(100), nullable=True)

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="cdc_logs")
    user = relationship("User", backref="cdc_logs")

    __table_args__ = (
        # Partial-Index: Nur unverarbeitete Events effizient finden
        Index(
            "ix_cdc_unprocessed",
            "processed",
            "created_at",
            postgresql_where=text("processed = false"),
        ),
        # Composite-Index: Änderungshistorie pro Entity
        Index(
            "ix_cdc_source",
            "source_table",
            "source_id",
            "sequence_number",
        ),
        # Composite-Index: Mandantenspezifische Abfragen
        Index(
            "ix_cdc_company_table",
            "company_id",
            "source_table",
            "created_at",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert das CDC-Log in ein Dictionary für API-Responses."""
        return {
            "id": str(self.id),
            "source_table": self.source_table,
            "source_id": str(self.source_id),
            "operation": self.operation,
            "old_data": self.old_data,
            "new_data": self.new_data,
            "changed_columns": self.changed_columns or [],
            "sequence_number": self.sequence_number,
            "processed": self.processed,
            "processed_at": (
                self.processed_at.isoformat() if self.processed_at else None
            ),
            "consumer_id": self.consumer_id,
            "company_id": str(self.company_id) if self.company_id else None,
            "user_id": str(self.user_id) if self.user_id else None,
            "transaction_id": self.transaction_id,
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
        }


class CDCConsumerOffset(Base):
    """
    Consumer-Offset für CDC Event-Verarbeitung.

    Speichert den Verarbeitungsfortschritt jedes Consumers,
    sodass bei Neustart nahtlos weitergemacht werden kann.
    """
    __tablename__ = "cdc_consumer_offsets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Consumer-Identifikation (z.B. 'datev_sync', 'lexware_export')
    consumer_name = Column(String(100), nullable=False, unique=True)

    # Letzte verarbeitete Sequenznummer
    last_sequence_number = Column(BigInteger, default=0)

    # Letzter Verarbeitungszeitpunkt
    last_processed_at = Column(DateTime(timezone=True), nullable=True)

    # Status: active, paused, error
    status = Column(String(20), default="active")

    # Fehlermeldung (bei status='error')
    error_message = Column(Text, nullable=True)

    # Consumer-spezifische Konfiguration
    config = Column(CrossDBJSON, default=dict)

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def to_dict(self) -> dict:
        """Konvertiert den Consumer-Offset in ein Dictionary."""
        return {
            "id": str(self.id),
            "consumer_name": self.consumer_name,
            "last_sequence_number": self.last_sequence_number,
            "last_processed_at": (
                self.last_processed_at.isoformat()
                if self.last_processed_at else None
            ),
            "status": self.status,
            "error_message": self.error_message,
            "config": self.config or {},
            "created_at": (
                self.created_at.isoformat() if self.created_at else None
            ),
            "updated_at": (
                self.updated_at.isoformat() if self.updated_at else None
            ),
        }
