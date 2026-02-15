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
# CommentReply (Verschachtelte Antworten)
# ============================================================================


class CommentReply(Base):
    """Verschachtelte Antwort auf einen Kommentar-Thread.

    Unterstuetzt beliebig tiefe Verschachtelung ueber parent_reply_id.
    @Mentions werden als UUID-Liste in mentions gespeichert.
    """

    __tablename__ = "comment_replies"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comment_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_reply_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comment_replies.id", ondelete="CASCADE"),
        nullable=True,
        comment="Eltern-Antwort fuer verschachtelte Antworten",
    )
    author_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Inhalt
    content = Column(Text, nullable=False)
    mentions = Column(
        CrossDBJSON,
        default=list,
        comment="Liste der erwaehnten User-UUIDs",
    )

    # Bearbeitungsstatus
    is_edited = Column(Boolean, default=False, nullable=False)
    edited_at = Column(DateTime(timezone=True), nullable=True)

    # Soft-Delete
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    thread = relationship("CommentThread", backref="replies")
    author = relationship("User", foreign_keys=[author_id])
    parent_reply = relationship(
        "CommentReply",
        remote_side=[id],
        backref="child_replies",
    )

    __table_args__ = (
        Index("ix_comment_replies_thread_id", "thread_id"),
        Index("ix_comment_replies_parent_reply_id", "parent_reply_id"),
        Index("ix_comment_replies_author_id", "author_id"),
        Index(
            "ix_comment_replies_thread_created",
            "thread_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<CommentReply {self.id} thread={self.thread_id}>"


# ============================================================================
# BoundingBoxAnnotation (PDF-Markierungen)
# ============================================================================


class BoundingBoxAnnotation(Base):
    """Bounding-Box-Annotation auf einer PDF-Seite.

    Speichert praezise Positionsdaten fuer Markierungen:
    - Koordinaten (x, y) und Dimensionen (width, height)
    - Verschiedene Annotationstypen (Highlight, Box, Pin, etc.)
    - Optionale Verknuepfung mit einem Kommentar-Thread
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
        comment="Y-Position (0.0 - 1.0 relativ zur Seitenhoehe)",
    )
    width = Column(
        Float,
        nullable=False,
        comment="Breite der Markierung (0.0 - 1.0)",
    )
    height = Column(
        Float,
        nullable=False,
        comment="Hoehe der Markierung (0.0 - 1.0)",
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
        comment="Verknuepfter Kommentar-Thread",
    )

    # Soft-Delete
    is_deleted = Column(Boolean, default=False, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

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


# ============================================================================
# CommentTask (Aufgaben aus Kommentaren)
# ============================================================================


class CommentTask(Base):
    """Aufgabe erstellt aus einem Kommentar-Thread.

    Ermoeglicht es, direkt aus Kommentaren Aufgaben zu erstellen
    und diese Benutzern zuzuweisen mit Faelligkeitsdatum.
    """

    __tablename__ = "comment_tasks"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comment_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_to_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Aufgabendetails
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        String(50),
        default=CommentTaskStatus.OFFEN.value,
        nullable=False,
    )

    # Zeitverwaltung
    due_date = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Faelligkeitsdatum der Aufgabe",
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Erledigung",
    )

    # Ersteller
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    thread = relationship("CommentThread", backref="tasks")
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    __table_args__ = (
        Index("ix_comment_tasks_thread_id", "thread_id"),
        Index(
            "ix_comment_tasks_assigned_status",
            "assigned_to_user_id",
            "status",
        ),
        Index("ix_comment_tasks_due_date", "due_date"),
        Index("ix_comment_tasks_created_by", "created_by_user_id"),
    )

    def __repr__(self) -> str:
        return f"<CommentTask {self.id} status={self.status}>"


# ============================================================================
# MentionNotification (Erwaehnungs-Benachrichtigung)
# ============================================================================


class MentionNotification(Base):
    """Benachrichtigung bei @mention in Kommentaren oder Antworten.

    Speichert Erwaehnungen mit Quell-Referenz (Kommentar, Antwort, Annotation)
    und Gelesen-Status.
    """

    __tablename__ = "mention_notifications"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Beteiligte Benutzer
    mentioned_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    mentioning_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Quelle der Erwaehnung
    source_type = Column(
        String(50),
        nullable=False,
        comment="Quell-Typ: comment, reply, annotation",
    )
    source_id = Column(
        UUID(as_uuid=True),
        nullable=False,
        comment="ID des Quell-Objekts",
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Gelesen-Status
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    mentioned_user = relationship(
        "User",
        foreign_keys=[mentioned_user_id],
        backref="received_mentions",
    )
    mentioning_user = relationship(
        "User",
        foreign_keys=[mentioning_user_id],
        backref="sent_mentions",
    )
    document = relationship("Document", backref="mention_notifications")

    __table_args__ = (
        Index("ix_mention_notif_company_id", "company_id"),
        Index("ix_mention_notif_mentioned_user", "mentioned_user_id", "is_read"),
        Index("ix_mention_notif_document_id", "document_id"),
        Index("ix_mention_notif_created_at", "created_at"),
    )
