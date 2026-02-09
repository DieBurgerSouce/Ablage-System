"""Notification Template Model - Satellitenmodell fuer Benachrichtigungsvorlagen.

Dieses Modul enthaelt das Datenmodell fuer wiederverwendbare
Benachrichtigungsvorlagen mit Jinja2-Templates.

Satellite Pattern: Separate Datei, NICHT in models.py.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class NotificationMessageTemplate(Base):
    """Vorlage fuer Benachrichtigungen mit Variablenunterstuetzung.

    Jinja2-basierte Template-Engine fuer Multi-Channel Benachrichtigungen.
    Getrennt von NotificationTemplate (Push-Notifications) in models.py.

    Attributes:
        id: Eindeutige UUID
        name: Eindeutiger Name der Vorlage
        category: Kategorie (approval, document, escalation, system)
        subject_template: Jinja2-Template fuer Betreff
        body_template: Jinja2-Template fuer Nachrichtentext
        variables: JSON mit required/optional Variablenlisten
        channels: JSON-Array mit unterstuetzten Kanaelen
        is_active: Ob Vorlage aktiv ist (Soft-Delete)
        created_by_id: Ersteller-User-ID
        created_at: Erstellungszeitpunkt
        updated_at: Letztes Update
    """

    __tablename__ = "notification_message_templates"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    name = Column(
        String(200),
        nullable=False,
        unique=True,
        index=True,
    )
    category = Column(
        String(50),
        nullable=False,
        index=True,
    )
    subject_template = Column(
        Text,
        nullable=False,
    )
    body_template = Column(
        Text,
        nullable=False,
    )
    variables = Column(
        CrossDBJSON,
        nullable=True,
        comment="JSON mit required/optional Variablen",
    )
    channels = Column(
        CrossDBJSON,
        nullable=True,
        comment="JSON-Array mit unterstuetzten Notification-Channels",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    created_by = relationship(
        "User",
        foreign_keys=[created_by_id],
        back_populates=None,
    )

    def __repr__(self) -> str:
        """String-Repraesentation."""
        return (
            f"<NotificationMessageTemplate(id={self.id}, "
            f"name='{self.name}', category='{self.category}')>"
        )


# Index fuer Abfragen nach Kategorie + Aktiv-Status
Index(
    "ix_notification_msg_templates_category_active",
    NotificationMessageTemplate.category,
    NotificationMessageTemplate.is_active,
)
