# -*- coding: utf-8 -*-
"""
Document Lifecycle database models for Ablage-System.

Dokument-Lebenszyklus mit SLA-Überwachung:
- Stufen: Eingang -> OCR -> Klassifizierung -> Prüfung -> Freigabe -> Buchung -> Archivierung
- SLA-Konfiguration pro Dokumenttyp und Stufe
- Stufen-Übergaenge mit Zeitstempeln und SLA-Einhaltung
- Mandantenfaehig (company_id)

Feinpoliert und durchdacht - Enterprise-grade Document Lifecycle.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class DocumentLifecycleStage(str, Enum):
    """Lebenszyklus-Stufen eines Dokuments."""
    EINGANG = "eingang"                    # Dokument empfangen
    OCR = "ocr"                            # OCR-Verarbeitung
    KLASSIFIZIERUNG = "klassifizierung"    # Klassifikation
    PRUEFUNG = "prüfung"                  # Prüfung/Verifizierung
    FREIGABE = "freigabe"                  # Freigabe/Genehmigung
    BUCHUNG = "buchung"                    # Buchung/Verbuchung
    ARCHIVIERUNG = "archivierung"          # Archiviert


# Ordered stages for validation
STAGE_ORDER = [
    DocumentLifecycleStage.EINGANG,
    DocumentLifecycleStage.OCR,
    DocumentLifecycleStage.KLASSIFIZIERUNG,
    DocumentLifecycleStage.PRUEFUNG,
    DocumentLifecycleStage.FREIGABE,
    DocumentLifecycleStage.BUCHUNG,
    DocumentLifecycleStage.ARCHIVIERUNG,
]

VALID_STAGE_VALUES = ",".join(f"'{s.value}'" for s in DocumentLifecycleStage)


class DocumentLifecycleConfig(Base):
    """
    SLA-Konfiguration pro Dokumenttyp und Lebenszyklus-Stufe.

    Definiert maximale Verweildauer und Eskalationszeiten
    für jede Stufe eines Dokumenttyps.
    """
    __tablename__ = "document_lifecycle_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Mandant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Konfiguration
    document_type = Column(String(50), nullable=False, index=True)
    stage = Column(String(30), nullable=False)
    max_duration_hours = Column(Integer, nullable=False)
    escalation_after_hours = Column(Integer, nullable=True)
    escalation_to_role = Column(String(50), nullable=True)

    # Status
    is_active = Column(Boolean, default=True)

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Beziehungen
    company = relationship("Company", backref="lifecycle_configs")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "document_type", "stage",
            name="uq_lifecycle_config_company_type_stage",
        ),
        Index(
            "ix_lifecycle_config_company_type",
            "company_id", "document_type",
        ),
        CheckConstraint(
            "max_duration_hours > 0",
            name="ck_lifecycle_config_duration_positive",
        ),
    )


class DocumentLifecycleEvent(Base):
    """
    Protokolliert jeden Stufen-Übergang im Dokument-Lebenszyklus.

    Speichert Von/Nach-Stufe, Zeitpunkt, Dauer und SLA-Einhaltung.
    """
    __tablename__ = "document_lifecycle_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Mandant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Stufen-Übergang
    from_stage = Column(String(30), nullable=True)  # None für initialen Eingang
    to_stage = Column(String(30), nullable=False)

    # Zeitstempel und Dauer
    transitioned_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    transitioned_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Dauer in der vorherigen Stufe (Sekunden)
    duration_seconds = Column(Integer, nullable=True)

    # SLA-Einhaltung
    sla_met = Column(Boolean, nullable=True)

    # Optionale Notiz
    note = Column(Text, nullable=True)

    # Beziehungen
    document = relationship("Document", backref="lifecycle_events")
    company = relationship("Company", backref="lifecycle_events")
    transitioned_by = relationship("User")

    __table_args__ = (
        Index(
            "ix_lifecycle_events_document",
            "document_id", "transitioned_at",
        ),
        Index(
            "ix_lifecycle_events_company_stage",
            "company_id", "to_stage",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert das Event in ein Dictionary für API-Antworten."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "from_stage": self.from_stage,
            "to_stage": self.to_stage,
            "transitioned_at": (
                self.transitioned_at.isoformat()
                if self.transitioned_at
                else None
            ),
            "transitioned_by_id": (
                str(self.transitioned_by_id)
                if self.transitioned_by_id
                else None
            ),
            "duration_seconds": self.duration_seconds,
            "sla_met": self.sla_met,
            "note": self.note,
        }
