# -*- coding: utf-8 -*-
"""
Annotation Enhancement satellite models for Ablage-System.

Erweitert das bestehende DocumentAnnotation-System um:
- Verbesserte Annotationstypen (Bounding Box, Pfeile, Stempel)
- Kommentar-Antworten mit Verschachtelung
- Aufgaben aus Kommentaren
- @Mention-Benachrichtigungen

Baut auf DocumentAnnotation (models.py) und CommentThread (models_comments.py) auf.
"""

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
    """Typ der Annotation."""
    COMMENT = "comment"
    HIGHLIGHT = "highlight"
    BOUNDING_BOX = "bounding_box"
    ARROW = "arrow"
    STAMP = "stamp"


class CommentTaskStatus(str, Enum):
    """Status einer Kommentar-Aufgabe."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# ============================================================================
# Comment Reply (Verschachtelte Antworten)
# ============================================================================


class CommentReply(Base):
    """Verschachtelte Antwort auf einen Kommentar-Thread.

    Unterstuetzt beliebig tiefe Verschachtelung ueber parent_reply_id
    und @mentions mit Benachrichtigungen.
    """
    __tablename__ = "comment_replies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_thread_id = Column(
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
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Inhalt
    content = Column(Text, nullable=False)
    mentions = Column(CrossDBJSON, default=list, comment="Liste von erwaehnten User-IDs")

    # Bearbeitungs-Tracking
    is_edited = Column(Boolean, default=False)
    edited_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    thread = relationship("CommentThread", backref="replies")
    author = relationship("User", foreign_keys=[author_id], backref="comment_replies")
    parent_reply = relationship(
        "CommentReply",
        remote_side=[id],
        backref="child_replies",
    )

    __table_args__ = (
        Index("ix_comment_replies_thread_id", "comment_thread_id"),
        Index("ix_comment_replies_parent_id", "parent_reply_id"),
        Index("ix_comment_replies_author_id", "author_id"),
        Index("ix_comment_replies_company_id", "company_id"),
        Index("ix_comment_replies_created_at", "created_at"),
    )


# ============================================================================
# Comment Task (Aufgabe aus Kommentar)
# ============================================================================


class CommentTask(Base):
    """Aufgabe die aus einem Kommentar oder einer Antwort erstellt wird.

    Ermoeglicht 'Bitte pruefen' -> erzeugt Task mit Zuweisung,
    Faelligkeitsdatum und Status-Tracking.
    """
    __tablename__ = "comment_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_thread_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comment_threads.id", ondelete="SET NULL"),
        nullable=True,
    )
    reply_id = Column(
        UUID(as_uuid=True),
        ForeignKey("comment_replies.id", ondelete="SET NULL"),
        nullable=True,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Ersteller und Zuweisung
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_to = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Aufgaben-Details
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        String(30),
        default=CommentTaskStatus.OPEN.value,
        nullable=False,
    )

    # Termine
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    thread = relationship("CommentThread", backref="tasks")
    reply = relationship("CommentReply", backref="tasks")
    creator = relationship("User", foreign_keys=[created_by], backref="created_comment_tasks")
    assignee = relationship("User", foreign_keys=[assigned_to], backref="assigned_comment_tasks")

    __table_args__ = (
        Index("ix_comment_tasks_thread_id", "comment_thread_id"),
        Index("ix_comment_tasks_company_id", "company_id"),
        Index("ix_comment_tasks_assigned_to", "assigned_to"),
        Index("ix_comment_tasks_status", "status"),
        Index("ix_comment_tasks_due_date", "due_date"),
    )


# ============================================================================
# Mention Notification (Erwaehnungs-Benachrichtigung)
# ============================================================================


class MentionNotification(Base):
    """Benachrichtigung bei @mention in Kommentaren oder Antworten.

    Speichert Erwaehnungen mit Quell-Referenz (Kommentar, Antwort, Annotation)
    und Gelesen-Status.
    """
    __tablename__ = "mention_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
