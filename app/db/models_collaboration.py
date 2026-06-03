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
# G4 DB-Hygiene: 'app.db.base' existiert nicht — kanonische Base-Quelle ist
# app.db.models_base (dieselbe Base-Instanz, die app.db.models re-exportiert).
from app.db.models_base import Base

# Import canonical DocumentActivity to avoid duplicate __tablename__
from app.db.models_notification import DocumentActivity  # noqa: F401


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


# NOTE: DocumentActivity was previously defined here but has been moved to an
# import from app.db.models_notification (see top of file) to avoid
# duplicate __tablename__ "document_activities" that crashes SQLAlchemy at startup.
