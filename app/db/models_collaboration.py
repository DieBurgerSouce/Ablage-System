"""
Collaboration Database Models.

Datenbank-Modelle für Echtzeit-Kollaboration:
- document_mentions: @Mentions in Kommentaren
- document_activities: Activity Feed
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.datetime_utils import utc_now
from app.db.base import Base


class DocumentMention(Base):
    """
    Document Mentions Table.

    Speichert @Mentions in Kommentaren und anderen Kontexten.
    """

    __tablename__ = "document_mentions"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    document_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mentioned_user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mentioned_by_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    context = Column(
        Text,
        nullable=False,
        comment="Kontext-Text (z.B. Kommentar-Inhalt)",
    )

    read = Column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
        comment="Wurde die Mention gelesen?",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Indexes für Performance
    __table_args__ = (
        Index(
            "ix_document_mentions_user_read",
            "mentioned_user_id",
            "read",
            "created_at",
        ),
        Index(
            "ix_document_mentions_document_created",
            "document_id",
            "created_at",
        ),
    )


class DocumentActivity(Base):
    """
    Document Activity Table.

    Speichert Aktivitäten für den Activity Feed.
    """

    __tablename__ = "document_activities"

    id = Column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )

    document_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,  # Nullable für System-Aktivitäten ohne Dokument
        index=True,
    )

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Activity Action (viewed, edited, commented, etc.)",
    )

    details = Column(
        Text,
        nullable=False,
        comment="Deutsche Beschreibung der Aktivität",
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        index=True,
    )

    # Indexes für Performance
    __table_args__ = (
        Index(
            "ix_document_activities_document_created",
            "document_id",
            "created_at",
        ),
        Index(
            "ix_document_activities_user_created",
            "user_id",
            "created_at",
        ),
        Index(
            "ix_document_activities_action_created",
            "action",
            "created_at",
        ),
        {"extend_existing": True},
    )
