"""
Extended Annotation & Comment Models (Satellite).

Erweitert das bestehende Annotations-System um:
- BoundingBoxAnnotation: Praezise PDF-Markierungen mit Bounding-Boxes
- CommentReply: Verschachtelte Antworten auf Kommentar-Threads
- CommentTask: Aufgaben aus Kommentaren erstellen und verfolgen
- AnnotationType Enum: Differenzierte Annotationstypen

Baut auf CommentThread (models_comments.py) und DocumentAnnotation (models.py) auf.
"""

from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON

# Import canonical model classes to avoid duplicate __tablename__ definitions.
# These are defined in models_annotations.py (primary) and re-exported here
# so that existing imports from this module continue to work.
from app.db.models_annotations import (
    CommentReply,  # noqa: F401
    CommentTask,  # noqa: F401
    MentionNotification,  # noqa: F401
)
from app.db.models_base import SoftDeleteMixin

# ============================================================================
# Enums
# ============================================================================


class AnnotationType(str, Enum):
    """Typ der Annotation auf einem Dokument."""

    COMMENT = "comment"
    HIGHLIGHT = "highlight"
    BOUNDING_BOX = "bounding_box"
    PIN = "pin"
    TASK = "task"


class CommentTaskStatus(str, Enum):
    """Status einer Kommentar-Aufgabe."""

    OFFEN = "offen"
    IN_BEARBEITUNG = "in_bearbeitung"
    ERLEDIGT = "erledigt"


# ============================================================================
# BoundingBoxAnnotation (PDF-Markierungen)
# ============================================================================


class BoundingBoxAnnotation(SoftDeleteMixin, Base):
    """Bounding-Box-Annotation auf einer PDF-Seite.

    Speichert praezise Positionsdaten für Markierungen:
    - Koordinaten (x, y) und Dimensionen (width, height)
    - Verschiedene Annotationstypen (Highlight, Box, Pin, etc.)
    - Optionale Verknüpfung mit einem Kommentar-Thread
    """

    __tablename__ = "bounding_box_annotations"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number = Column(
        Integer,
        nullable=False,
        comment="Seitennummer (1-basiert)",
    )

    # Positionsdaten (relative Koordinaten 0.0 - 1.0)
    x = Column(
        Float,
        nullable=False,
        comment="X-Position (0.0 - 1.0 relativ zur Seitenbreite)",
    )
    y = Column(
        Float,
        nullable=False,
        comment="Y-Position (0.0 - 1.0 relativ zur Seitenhöhe)",
    )
    width = Column(
        Float,
        nullable=False,
        comment="Breite der Markierung (0.0 - 1.0)",
    )
    height = Column(
        Float,
        nullable=False,
        comment="Höhe der Markierung (0.0 - 1.0)",
    )

    # Annotation-Metadaten
    annotation_type = Column(
        String(30),
        default=AnnotationType.BOUNDING_BOX.value,
        nullable=False,
    )
    label = Column(
        String(500),
        nullable=True,
        comment="Beschriftung der Markierung",
    )
    color = Column(
        String(20),
        default="#FFD700",
        nullable=False,
        comment="Hex-Farbe der Markierung",
    )

    # Zuordnung
    author_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comment_threads.id", ondelete="SET NULL"),
        nullable=True,
        comment="Verknüpfter Kommentar-Thread",
    )

    # Soft-Delete
    is_deleted = Column(Boolean, default=False, nullable=False)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    document = relationship("Document")
    author = relationship("User", foreign_keys=[author_id])
    thread = relationship("CommentThread")

    __table_args__ = (
        Index(
            "ix_bbox_annotations_document_page",
            "document_id",
            "page_number",
        ),
        Index("ix_bbox_annotations_thread_id", "thread_id"),
        Index("ix_bbox_annotations_author_id", "author_id"),
        Index(
            "ix_bbox_annotations_document_created",
            "document_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<BoundingBoxAnnotation {self.id} "
            f"page={self.page_number} "
            f"type={self.annotation_type}>"
        )



# NOTE: CommentTask and MentionNotification were previously defined here but have been
# moved to imports from app.db.models_annotations (see top of file) to avoid
# duplicate __tablename__ definitions that crash SQLAlchemy at startup.
