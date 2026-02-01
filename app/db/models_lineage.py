# -*- coding: utf-8 -*-
"""
Document Lineage database models for Ablage-System.

Datenherkunfts-Tracking fuer Dokumente:
- Import-Quelle (Email/Ordner/API/Manuell)
- Verarbeitungsschritte (OCR -> Klassifikation -> Extraktion)
- Entity-Linking mit Konfidenz
- Aenderungen mit Zeitstempel und Benutzer

Feinpoliert und durchdacht - Enterprise-grade Document Lineage.
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
    Float,
    Text,
    ForeignKey,
    Index,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class LineageEventType(str, Enum):
    """Typen von Lineage-Ereignissen."""

    # Import-Ereignisse
    IMPORT = "import"                    # Dokument importiert

    # OCR-Verarbeitung
    OCR_START = "ocr_start"              # OCR-Verarbeitung gestartet
    OCR_COMPLETE = "ocr_complete"        # OCR-Verarbeitung abgeschlossen
    OCR_FAILED = "ocr_failed"            # OCR-Verarbeitung fehlgeschlagen

    # Klassifikation
    CLASSIFICATION = "classification"    # Dokumenttyp klassifiziert

    # Datenextraktion
    EXTRACTION = "extraction"            # Daten extrahiert (Betrag, Datum, etc.)

    # Entity-Linking
    ENTITY_LINK = "entity_link"          # Mit Geschaeftspartner verknuepft
    ENTITY_UNLINK = "entity_unlink"      # Verknuepfung entfernt

    # Modifikationen
    MODIFICATION = "modification"        # Manuelle Aenderung
    METADATA_UPDATE = "metadata_update"  # Metadaten aktualisiert
    TAG_CHANGE = "tag_change"            # Tags geaendert

    # Workflow-Ereignisse
    APPROVAL = "approval"                # Genehmigung
    REJECTION = "rejection"              # Ablehnung
    ESCALATION = "escalation"            # Eskalation

    # Export
    EXPORT = "export"                    # Dokument exportiert

    # Archivierung
    ARCHIVE = "archive"                  # Archiviert
    RESTORE = "restore"                  # Wiederhergestellt

    # Loeschung
    SOFT_DELETE = "soft_delete"          # Soft-Delete (GDPR)
    HARD_DELETE = "hard_delete"          # Endgueltige Loeschung


class ImportSourceType(str, Enum):
    """Typen von Import-Quellen."""

    MANUAL_UPLOAD = "manual_upload"      # Manueller Upload via UI
    EMAIL = "email"                      # Email-Import
    FOLDER = "folder"                    # Ordner-Import (Watchfolder)
    API = "api"                          # API-Upload
    SCAN = "scan"                        # Scanner-Integration
    INTEGRATION = "integration"          # Externe Integration (ERP, etc.)


class DocumentLineageEvent(Base):
    """
    Einzelnes Lineage-Ereignis fuer ein Dokument.

    Speichert alle Ereignisse in der Verarbeitungskette eines Dokuments
    mit vollstaendiger Nachverfolgbarkeit.
    """
    __tablename__ = "document_lineage_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Ereignis-Typ
    event_type = Column(
        String(50),
        nullable=False,
        index=True,
    )

    # Ereignis-Details (strukturiert)
    event_data = Column(CrossDBJSON, default=dict)

    # Verarbeitungsdauer (in Millisekunden)
    duration_ms = Column(Integer, nullable=True)

    # Konfidenz (fuer OCR, Klassifikation, Entity-Linking)
    confidence = Column(Float, nullable=True)

    # Benutzer, der das Ereignis ausgeloest hat (optional)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Multi-Tenant Support
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Quell-Service/System
    source_service = Column(String(100), nullable=True)

    # Korrelations-ID fuer zusammengehoerende Ereignisse
    correlation_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Zeitstempel
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )

    # Relationships
    document = relationship("Document", backref="lineage_events")
    user = relationship("User", backref="lineage_events")
    company = relationship("Company", backref="lineage_events")

    # Indexes fuer effiziente Abfragen
    __table_args__ = (
        Index("ix_lineage_document_created", "document_id", "created_at"),
        Index("ix_lineage_document_type", "document_id", "event_type"),
        Index("ix_lineage_company_created", "company_id", "created_at"),
        Index("ix_lineage_correlation", "correlation_id"),
        CheckConstraint(
            "event_type IN ('import', 'ocr_start', 'ocr_complete', 'ocr_failed', "
            "'classification', 'extraction', 'entity_link', 'entity_unlink', "
            "'modification', 'metadata_update', 'tag_change', 'approval', "
            "'rejection', 'escalation', 'export', 'archive', 'restore', "
            "'soft_delete', 'hard_delete')",
            name="ck_lineage_event_type",
        ),
    )

    def to_dict(self) -> dict:
        """Konvertiert das Ereignis in ein Dictionary fuer API-Responses."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "event_type": self.event_type,
            "event_data": self.event_data or {},
            "duration_ms": self.duration_ms,
            "confidence": self.confidence,
            "user_id": str(self.user_id) if self.user_id else None,
            "company_id": str(self.company_id),
            "source_service": self.source_service,
            "correlation_id": str(self.correlation_id) if self.correlation_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class DocumentLineageSummary(Base):
    """
    Zusammenfassung der Lineage fuer ein Dokument.

    Cache-Tabelle fuer schnelle Abfragen der wichtigsten Lineage-Informationen.
    Wird bei jedem Lineage-Event aktualisiert.
    """
    __tablename__ = "document_lineage_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Dokument-Referenz (1:1)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Import-Informationen
    import_source_type = Column(String(50), nullable=True)
    import_source_details = Column(CrossDBJSON, default=dict)
    imported_at = Column(DateTime(timezone=True), nullable=True)
    imported_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # OCR-Informationen
    ocr_backend = Column(String(50), nullable=True)
    ocr_duration_ms = Column(Integer, nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    ocr_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Klassifikation
    classification_confidence = Column(Float, nullable=True)
    classified_at = Column(DateTime(timezone=True), nullable=True)

    # Entity-Linking
    current_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    entity_link_confidence = Column(Float, nullable=True)
    entity_linked_at = Column(DateTime(timezone=True), nullable=True)
    entity_link_count = Column(Integer, default=0)

    # Modifikations-Statistiken
    modification_count = Column(Integer, default=0)
    last_modified_at = Column(DateTime(timezone=True), nullable=True)
    last_modified_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Gesamte Verarbeitungsdauer
    total_processing_duration_ms = Column(Integer, default=0)

    # Anzahl der Ereignisse
    total_event_count = Column(Integer, default=0)

    # Workflow-Status
    approval_count = Column(Integer, default=0)
    rejection_count = Column(Integer, default=0)

    # Export-Statistiken
    export_count = Column(Integer, default=0)
    last_exported_at = Column(DateTime(timezone=True), nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zeitstempel
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    document = relationship("Document", backref="lineage_summary")
    imported_by = relationship("User", foreign_keys=[imported_by_id])
    last_modified_by = relationship("User", foreign_keys=[last_modified_by_id])
    current_entity = relationship("BusinessEntity")
    company = relationship("Company", backref="lineage_summaries")

    __table_args__ = (
        Index("ix_lineage_summary_company", "company_id"),
    )

    def to_dict(self) -> dict:
        """Konvertiert die Zusammenfassung in ein Dictionary."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "import": {
                "source_type": self.import_source_type,
                "source_details": self.import_source_details or {},
                "imported_at": self.imported_at.isoformat() if self.imported_at else None,
                "imported_by_id": str(self.imported_by_id) if self.imported_by_id else None,
            },
            "ocr": {
                "backend": self.ocr_backend,
                "duration_ms": self.ocr_duration_ms,
                "confidence": self.ocr_confidence,
                "completed_at": self.ocr_completed_at.isoformat() if self.ocr_completed_at else None,
            },
            "classification": {
                "confidence": self.classification_confidence,
                "classified_at": self.classified_at.isoformat() if self.classified_at else None,
            },
            "entity_linking": {
                "current_entity_id": str(self.current_entity_id) if self.current_entity_id else None,
                "confidence": self.entity_link_confidence,
                "linked_at": self.entity_linked_at.isoformat() if self.entity_linked_at else None,
                "link_count": self.entity_link_count,
            },
            "modifications": {
                "count": self.modification_count,
                "last_modified_at": self.last_modified_at.isoformat() if self.last_modified_at else None,
                "last_modified_by_id": str(self.last_modified_by_id) if self.last_modified_by_id else None,
            },
            "statistics": {
                "total_processing_duration_ms": self.total_processing_duration_ms,
                "total_event_count": self.total_event_count,
                "approval_count": self.approval_count,
                "rejection_count": self.rejection_count,
                "export_count": self.export_count,
            },
            "last_exported_at": self.last_exported_at.isoformat() if self.last_exported_at else None,
            "company_id": str(self.company_id),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
