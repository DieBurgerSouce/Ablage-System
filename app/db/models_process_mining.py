# -*- coding: utf-8 -*-
"""
Process Mining database models for Ablage-System.

Vision 2.0 Feature: Process Mining & Autonome Automatisierung
Unterstuetzt:
- Event-Tracking fuer Dokumenten-Lebenszyklus
- Prozess-Discovery
- Bottleneck-Erkennung
- Automatisierungs-Vorschlaege

Feinpoliert und durchdacht.
"""

import uuid
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Date,
    Boolean,
    Text,
    Numeric,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class EventType(str, Enum):
    """Ereignistypen im Dokumenten-Lebenszyklus."""
    # Upload/Import
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_IMPORTED = "document_imported"
    EMAIL_RECEIVED = "email_received"

    # OCR-Verarbeitung
    OCR_STARTED = "ocr_started"
    OCR_COMPLETED = "ocr_completed"
    OCR_FAILED = "ocr_failed"
    OCR_BACKEND_SELECTED = "ocr_backend_selected"

    # Klassifikation
    CLASSIFICATION_STARTED = "classification_started"
    CLASSIFICATION_COMPLETED = "classification_completed"
    CLASSIFICATION_CORRECTED = "classification_corrected"

    # Validierung
    VALIDATION_STARTED = "validation_started"
    VALIDATION_COMPLETED = "validation_completed"
    VALIDATION_FAILED = "validation_failed"
    MANUAL_CORRECTION = "manual_correction"

    # Freigabe
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_REJECTED = "approval_rejected"

    # Archivierung
    ARCHIVE_STARTED = "archive_started"
    ARCHIVE_COMPLETED = "archive_completed"

    # Entity-Linking
    ENTITY_LINKED = "entity_linked"
    ENTITY_UNLINKED = "entity_unlinked"

    # Export
    EXPORTED_DATEV = "exported_datev"
    EXPORTED_PDF = "exported_pdf"

    # Sonstige
    VIEWED = "viewed"
    DOWNLOADED = "downloaded"
    SHARED = "shared"
    DELETED = "deleted"


class ActorType(str, Enum):
    """Wer hat die Aktion ausgeloest."""
    SYSTEM = "system"        # Automatischer Prozess
    USER = "user"            # Manueller Benutzer
    AUTOMATION = "automation"  # Automatisierte Regel
    SCHEDULED = "scheduled"  # Geplante Aufgabe
    API = "api"              # Externer API-Aufruf


class SuggestionStatus(str, Enum):
    """Status eines Automatisierungsvorschlags."""
    PENDING = "pending"      # Neu, warten auf Entscheidung
    ACTIVATED = "activated"  # Aktiviert
    REJECTED = "rejected"    # Abgelehnt
    EXPIRED = "expired"      # Abgelaufen (nicht mehr relevant)


class SuggestionType(str, Enum):
    """Typen von Automatisierungsvorschlaegen."""
    AUTO_CLASSIFICATION = "auto_classification"
    AUTO_ROUTING = "auto_routing"
    AUTO_APPROVAL = "auto_approval"
    AUTO_ARCHIVE = "auto_archive"
    AUTO_ENTITY_LINK = "auto_entity_link"
    BULK_OPERATION = "bulk_operation"
    WORKFLOW_OPTIMIZATION = "workflow_optimization"


class ProcessEvent(Base):
    """
    Ereignis im Dokumenten-Lebenszyklus.

    Trackt jede Aktion fuer Process Mining und Analyse.
    """
    __tablename__ = "process_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Referenzen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Event-Details
    event_type = Column(String(50), nullable=False, index=True)
    event_subtype = Column(String(50), nullable=True)

    # Akteur
    actor_type = Column(
        String(20),
        nullable=False,
        default=ActorType.SYSTEM.value,
        index=True,
    )
    actor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Zeitstempel
    timestamp = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Dauer und Verkettung
    duration_ms = Column(Integer, nullable=True)  # Dauer der Aktion
    previous_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("process_events.id", ondelete="SET NULL"),
        nullable=True,
    )
    time_since_previous_ms = Column(Integer, nullable=True)

    # Process Mining Felder (XES-kompatibel)
    process_instance_id = Column(String(100), nullable=True, index=True)
    activity_name = Column(String(100), nullable=True, index=True)
    resource = Column(String(100), nullable=True)  # Bearbeiter/System

    # Status
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)

    # Zusaetzliche Daten
    metadata = Column(CrossDBJSON, default=dict)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    document = relationship("Document", backref="process_events")
    actor = relationship("User", foreign_keys=[actor_id])
    company = relationship("Company", backref="process_events")
    previous_event = relationship("ProcessEvent", remote_side=[id])

    __table_args__ = (
        Index("ix_process_events_company_timestamp", "company_id", "timestamp"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id) if self.document_id else None,
            "entity_id": str(self.entity_id) if self.entity_id else None,
            "event_type": self.event_type,
            "event_subtype": self.event_subtype,
            "actor_type": self.actor_type,
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "duration_ms": self.duration_ms,
            "time_since_previous_ms": self.time_since_previous_ms,
            "process_instance_id": self.process_instance_id,
            "activity_name": self.activity_name,
            "resource": self.resource,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata or {},
        }


class AutomationSuggestion(Base):
    """
    Automatisierungsvorschlag basierend auf Process Mining.

    Speichert erkannte Muster und Vorschlaege zur Optimierung.
    """
    __tablename__ = "automation_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Vorschlagsdetails
    suggestion_type = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    pattern_description = Column(Text, nullable=True)

    # Bewertung
    confidence = Column(Numeric(5, 4), nullable=False)
    potential_savings_hours = Column(Numeric(10, 2), nullable=True)
    potential_savings_cost = Column(Numeric(15, 2), nullable=True)

    # Betroffene Schritte
    affected_steps = Column(CrossDBJSON, default=list)
    trigger_conditions = Column(CrossDBJSON, default=dict)
    suggested_actions = Column(CrossDBJSON, default=list)

    # Beispiele
    sample_documents = Column(CrossDBJSON, default=list)
    frequency_per_week = Column(Integer, nullable=True)

    # Status
    status = Column(
        String(30),
        nullable=False,
        default=SuggestionStatus.PENDING.value,
        index=True,
    )

    # Aktivierung
    activated_at = Column(DateTime(timezone=True), nullable=True)
    activated_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Ablehnung
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    rejected_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason = Column(Text, nullable=True)

    # Verknuepfung zur erstellten Regel
    automation_rule_id = Column(UUID(as_uuid=True), nullable=True)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    activated_by = relationship("User", foreign_keys=[activated_by_id])
    rejected_by = relationship("User", foreign_keys=[rejected_by_id])
    company = relationship("Company", backref="automation_suggestions")

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "suggestion_type": self.suggestion_type,
            "title": self.title,
            "description": self.description,
            "pattern_description": self.pattern_description,
            "confidence": float(self.confidence) if self.confidence else 0,
            "potential_savings_hours": float(self.potential_savings_hours) if self.potential_savings_hours else None,
            "potential_savings_cost": float(self.potential_savings_cost) if self.potential_savings_cost else None,
            "affected_steps": self.affected_steps or [],
            "trigger_conditions": self.trigger_conditions or {},
            "suggested_actions": self.suggested_actions or [],
            "sample_documents": self.sample_documents or [],
            "frequency_per_week": self.frequency_per_week,
            "status": self.status,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "rejected_at": self.rejected_at.isoformat() if self.rejected_at else None,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ProcessMetric(Base):
    """
    Aggregierte Prozess-Metriken.

    Taeglich berechnete Statistiken fuer Dashboard und Reporting.
    """
    __tablename__ = "process_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Zeitraum
    metric_date = Column(Date, nullable=False, index=True)

    # Metrik-Typ
    metric_type = Column(String(50), nullable=False, index=True)
    # Typen: throughput, duration, bottleneck, success_rate, automation_rate

    # Prozess-Referenz
    process_name = Column(String(100), nullable=True)
    activity_name = Column(String(100), nullable=True)

    # Zaehler
    event_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)

    # Zeitstatistiken
    avg_duration_ms = Column(Integer, nullable=True)
    min_duration_ms = Column(Integer, nullable=True)
    max_duration_ms = Column(Integer, nullable=True)
    p50_duration_ms = Column(Integer, nullable=True)
    p95_duration_ms = Column(Integer, nullable=True)

    # Automatisierung
    manual_action_count = Column(Integer, default=0)
    automated_action_count = Column(Integer, default=0)

    # Bottleneck-Score (0-1)
    bottleneck_score = Column(Numeric(5, 4), nullable=True)

    # Zusaetzliche Daten
    metadata = Column(CrossDBJSON, default=dict)

    # Multi-Tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    company = relationship("Company", backref="process_metrics")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "metric_date", "metric_type", "process_name", "activity_name",
            name="uq_process_metrics",
        ),
        Index("ix_process_metrics_company_date", "company_id", "metric_date"),
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "id": str(self.id),
            "metric_date": self.metric_date.isoformat() if self.metric_date else None,
            "metric_type": self.metric_type,
            "process_name": self.process_name,
            "activity_name": self.activity_name,
            "event_count": self.event_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "avg_duration_ms": self.avg_duration_ms,
            "min_duration_ms": self.min_duration_ms,
            "max_duration_ms": self.max_duration_ms,
            "p50_duration_ms": self.p50_duration_ms,
            "p95_duration_ms": self.p95_duration_ms,
            "manual_action_count": self.manual_action_count,
            "automated_action_count": self.automated_action_count,
            "bottleneck_score": float(self.bottleneck_score) if self.bottleneck_score else None,
            "automation_rate": (
                self.automated_action_count / (self.manual_action_count + self.automated_action_count)
                if (self.manual_action_count + self.automated_action_count) > 0
                else 0
            ),
        }
