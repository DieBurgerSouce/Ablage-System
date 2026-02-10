# -*- coding: utf-8 -*-
"""Chat Action Models - Satellite Model fuer RAG Agent Aktionen.

Tracking von Tool-Calls aus dem Chat-System.
Migration: 212_chat_actions.py

Feinpoliert und durchdacht - Deutsche Praezision.
"""

import uuid
from datetime import datetime
from typing import Optional, Dict

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base


class ChatToolAction(Base):
    """
    Tool-Aktionen aus dem RAG Chat Agent Mode.

    Speichert alle Tool-Calls die der LLM im Chat vorschlaegt
    oder ausfuehrt, mit vollstaendigem Tracking fuer Audit.
    """
    __tablename__ = "chat_tool_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Session-Beziehung
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Chat Session in der die Aktion aufgetreten ist"
    )

    # Optionale Message-Referenz
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("rag_chat_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="Assistant-Message die die Aktion vorgeschlagen hat"
    )

    # Tool-Information
    tool_name = Column(
        String(50),
        nullable=False,
        index=True,
        comment="Name des aufgerufenen Tools"
    )

    parameters = Column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Tool-Parameter als JSON"
    )

    # Status-Tracking
    status = Column(
        String(30),
        nullable=False,
        index=True,
        comment="pending_confirmation, confirmed, executed, rejected, failed"
    )

    # Ergebnis
    result = Column(
        JSONB,
        nullable=True,
        comment="Ergebnis nach Ausfuehrung"
    )

    error_message = Column(
        Text,
        nullable=True,
        comment="Fehlermeldung bei failed status"
    )

    # Bestaetigung
    requires_confirmation = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Muss vom User bestaetigt werden"
    )

    confirmed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User der die Aktion bestaetigt hat"
    )

    # Timestamps
    executed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Ausfuehrung"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Zeitpunkt der Erstellung"
    )

    # Relationships
    session = relationship("RAGChatSession", backref="tool_actions")
    message = relationship("RAGChatMessage", backref="tool_actions")
    confirmed_by = relationship("User")

    __table_args__ = (
        Index("ix_chat_tool_actions_session_status", "session_id", "status"),
        Index("ix_chat_tool_actions_created", "created_at"),
        {"comment": "Tool-Aktionen aus dem RAG Chat Agent Mode"}
    )

    def __repr__(self) -> str:
        return (
            f"<ChatToolAction("
            f"tool={self.tool_name}, "
            f"status={self.status}, "
            f"session={self.session_id}"
            f")>"
        )

    def to_dict(self) -> Dict[str, object]:
        """Konvertiert zu Dictionary fuer API.

        Returns:
            Dictionary mit allen relevanten Feldern
        """
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "message_id": str(self.message_id) if self.message_id else None,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "status": self.status,
            "result": self.result,
            "error_message": self.error_message,
            "requires_confirmation": self.requires_confirmation,
            "confirmed_by_id": str(self.confirmed_by_id) if self.confirmed_by_id else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
