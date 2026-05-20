# -*- coding: utf-8 -*-
"""
Active Learning Database Models fuer Ablage-System.

Phase 2.4: Uncertainty Sampling Pipeline
- ActiveLearningQueue: Priorisierte Review-Queue fuer OCR-Korrekturen
- ActiveLearningMetrics: Tagesbasierte Impact-Metriken

System identifiziert Dokumente mit niedrigem OCR-Confidence und priorisiert
sie fuer menschliche Pruefung, um maximalen Lerneffekt zu erzielen.

Feinpoliert und durchdacht - Enterprise Active Learning fuer deutsche Dokumente.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# =============================================================================
# MODELS
# =============================================================================


class ActiveLearningQueue(Base):
    """
    Priorisierte Review-Queue fuer OCR-Korrekturen.

    Jeder Eintrag repraesentiert ein Dokument, das fuer menschliche Pruefung
    priorisiert wurde. Das Scoring beruecksichtigt Unsicherheit, Haeufigkeit
    des Fehlermusters, Aktualitaet und Diversitaet.
    """
    __tablename__ = "active_learning_queue"

    # Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Beziehungen
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Dokument fuer Review",
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Company fuer RLS und Tenant-Isolation",
    )
    reviewed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Benutzer der die Pruefung durchgefuehrt hat",
    )

    # Scoring
    priority_score = Column(
        Float,
        nullable=False,
        comment="Gesamt-Prioritaet (0-1, hoeher = wertvoller fuer Training)",
    )
    uncertainty_score = Column(
        Float,
        nullable=False,
        comment="OCR-Unsicherheit (Inverse der Confidence)",
    )
    estimated_impact = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Geschaetzte Anzahl zukuenftiger Fehler die diese Korrektur verhindert",
    )

    # Queue-Grund und OCR-Kontext
    queue_reason = Column(
        String(100),
        nullable=False,
        comment="Grund: low_confidence, high_frequency_pattern, edge_case, user_nominated",
    )
    ocr_backend = Column(
        String(50),
        nullable=True,
        comment="Verwendetes OCR-Backend",
    )
    ocr_confidence = Column(
        Float,
        nullable=True,
        comment="Original OCR-Confidence (0.0-1.0)",
    )
    field_focus = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Felder die Aufmerksamkeit brauchen: ['amount', 'date', 'supplier']",
    )

    # Status und Review
    status = Column(
        String(20),
        nullable=False,
        default="queued",
        comment="Status: queued, in_review, reviewed, skipped",
    )
    reviewed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Pruefung",
    )
    correction_data = Column(
        CrossDBJSON,
        nullable=True,
        comment="Korrekturdaten: {field: {original: ..., corrected: ...}}",
    )
    training_batch_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        comment="Training-Batch der diese Korrektur konsumiert hat",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    document = relationship("Document")
    company = relationship("Company")
    reviewed_by = relationship("User")

    # Indexes
    __table_args__ = (
        Index(
            "ix_al_queue_company_status_priority",
            "company_id",
            "status",
            priority_score.desc(),
        ),
        {"comment": "Active Learning Queue fuer priorisierte OCR-Korrekturen"},
    )

    def __repr__(self) -> str:
        return (
            f"<ActiveLearningQueue("
            f"id={self.id}, "
            f"status={self.status}, "
            f"priority={self.priority_score:.2f}, "
            f"reason={self.queue_reason}"
            f")>"
        )

    @property
    def is_actionable(self) -> bool:
        """Prueft ob das Item noch bearbeitbar ist."""
        return self.status in ("queued", "in_review")


class ActiveLearningMetrics(Base):
    """
    Tagesbasierte Impact-Metriken fuer Active Learning.

    Aggregiert Korrekturdaten pro Tag und Company um den Lerneffekt
    messbar zu machen: 'X Korrekturen haben Y zukuenftige Fehler verhindert.'
    """
    __tablename__ = "active_learning_metrics"

    # Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Identifikation
    metric_date = Column(
        Date,
        nullable=False,
        comment="Tag fuer den die Metriken gelten",
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Company fuer Tenant-Isolation",
    )

    # Zaehler
    total_reviewed = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl gepruefter Items an diesem Tag",
    )
    total_corrections = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl tatsaechlicher Korrekturen (nicht uebersprungen)",
    )
    estimated_errors_prevented = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Geschaetzte verhinderte zukuenftige Fehler",
    )

    # Confidence-Tracking
    avg_confidence_before = Column(
        Float,
        nullable=True,
        comment="Durchschnittliche OCR-Confidence vor Training",
    )
    avg_confidence_after = Column(
        Float,
        nullable=True,
        comment="Durchschnittliche OCR-Confidence nach Training",
    )

    # Fehlermuster-Analyse
    top_error_patterns = Column(
        CrossDBJSON,
        nullable=False,
        default=list,
        comment="Haeufigste Fehlermuster: [{pattern: ..., count: ...}]",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    company = relationship("Company")

    # Constraints
    __table_args__ = (
        UniqueConstraint(
            "metric_date",
            "company_id",
            name="uq_al_metrics_date_company",
        ),
        {"comment": "Active Learning Impact-Metriken pro Tag und Company"},
    )

    def __repr__(self) -> str:
        return (
            f"<ActiveLearningMetrics("
            f"date={self.metric_date}, "
            f"reviewed={self.total_reviewed}, "
            f"corrections={self.total_corrections}, "
            f"prevented={self.estimated_errors_prevented}"
            f")>"
        )
