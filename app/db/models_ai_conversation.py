# -*- coding: utf-8 -*-
"""
AI Conversation Models fuer Finance Assistant Persistierung.

Ermoeglicht:
- Chat-History Speicherung
- Aktions-Tracking
- Benutzer-Feedback Sammlung
- Multi-Tenant Isolation

Migration: 120_add_ai_conversations

Feinpoliert und durchdacht - Deutsche Praezision.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Boolean,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base


# =============================================================================
# ENUMS
# =============================================================================


class AIMessageRole(str, Enum):
    """Rolle in der Konversation."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class AIAssistantIntent(str, Enum):
    """Erkannte Benutzerabsicht."""
    SEARCH = "search"
    EXECUTE_ACTION = "execute_action"
    EXPLAIN = "explain"
    SUGGEST_BOOKING = "suggest_booking"
    ANALYZE = "analyze"
    PREDICT = "predict"
    HELP = "help"
    CHAT = "chat"


class AIActionStatus(str, Enum):
    """Status einer vorgeschlagenen Aktion."""
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AIFeedbackType(str, Enum):
    """Typ des Benutzer-Feedbacks."""
    HELPFUL = "helpful"
    NOT_HELPFUL = "not_helpful"
    INCORRECT = "incorrect"
    CONFUSING = "confusing"
    OTHER = "other"


# =============================================================================
# MODELS
# =============================================================================


class AIConversation(Base):
    """
    Konversations-Session mit dem KI-Finanzassistenten.

    Speichert den gesamten Kontext einer Chat-Session fuer
    spaetere Referenz und Kontext-Bewahrung.
    """
    __tablename__ = "ai_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        String(64),
        nullable=False,
        unique=True,
        comment="Eindeutige Session-ID fuer Frontend-Zuordnung"
    )

    # Beziehungen
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Metadaten
    title = Column(
        String(255),
        nullable=True,
        comment="Automatisch generierter oder manueller Titel"
    )
    context_page = Column(
        String(255),
        nullable=True,
        comment="Seite auf der die Konversation gestartet wurde"
    )
    language = Column(String(5), nullable=False, default="de")

    # Status
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="False wenn archiviert"
    )
    is_starred = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Vom Benutzer markiert"
    )

    # Statistiken
    message_count = Column(Integer, nullable=False, default=0)
    action_count = Column(Integer, nullable=False, default=0)
    total_tokens = Column(
        Integer,
        nullable=True,
        comment="Gesamte Token-Nutzung (fuer Kosten-Tracking)"
    )

    # Kontext-Daten
    context_data = Column(
        JSONB,
        nullable=True,
        comment="Zusaetzlicher Kontext (ausgewaehlte Dokumente, etc.)"
    )
    preferences = Column(
        JSONB,
        nullable=True,
        comment="Benutzer-Praeferenzen fuer diese Session"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", backref="ai_conversations")
    company = relationship("Company", backref="ai_conversations")
    messages = relationship(
        "AIConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIConversationMessage.created_at"
    )
    actions = relationship(
        "AIConversationAction",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_ai_conv_user_active", "user_id", "is_active"),
        Index("ix_ai_conv_last_msg", "last_message_at"),
        {"comment": "KI-Finanzassistent Konversations-Sessions"}
    )

    def __repr__(self) -> str:
        return (
            f"<AIConversation("
            f"id={self.id}, "
            f"session_id={self.session_id}, "
            f"messages={self.message_count}"
            f")>"
        )

    def to_summary_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Uebersichts-Dictionary fuer ConversationSummary."""
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "title": self.title or "Neue Konversation",
            "message_count": self.message_count,
            "action_count": self.action_count,
            "is_starred": self.is_starred,
            "is_active": self.is_active,
            "context_page": self.context_page,
            "language": self.language or "de",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
        }

    def to_detail_dict(self) -> Dict[str, Any]:
        """Konvertiere zu vollstaendigem Dictionary fuer ConversationDetail."""
        return {
            "id": str(self.id),
            "session_id": self.session_id,
            "title": self.title,
            "message_count": self.message_count,
            "action_count": self.action_count,
            "is_starred": self.is_starred,
            "is_active": self.is_active,
            "context_page": self.context_page,
            "context_data": self.context_data,
            "preferences": self.preferences,
            "language": self.language or "de",
            "total_tokens": self.total_tokens,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
        }


class AIConversationMessage(Base):
    """
    Einzelne Nachricht innerhalb einer Konversation.

    Speichert sowohl Benutzer- als auch Assistenten-Nachrichten
    mit allen relevanten Metadaten.
    """
    __tablename__ = "ai_conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Nachricht
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(
        Text,
        nullable=False,
        comment="Nachrichteninhalt (Markdown-formatiert)"
    )
    intent = Column(
        String(50),
        nullable=True,
        comment="Erkannte Absicht (nur fuer user-Nachrichten)"
    )
    confidence = Column(
        Float,
        nullable=True,
        comment="Konfidenz der Intent-Erkennung (0.0-1.0)"
    )

    # Antwort-Metadaten (nur fuer assistant-Nachrichten)
    search_results_count = Column(Integer, nullable=True)
    actions_proposed = Column(Integer, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    model_used = Column(
        String(50),
        nullable=True,
        comment="LLM-Modell (ollama/mistral, etc.)"
    )
    tokens_used = Column(Integer, nullable=True)

    # Erweiterte Daten
    extra_data = Column(
        JSONB,
        nullable=True,
        comment="Zusaetzliche Metadaten (Insights, Suggestions, etc.)"
    )
    referenced_documents = Column(
        JSONB,
        nullable=True,
        comment="Array von Dokument-IDs die referenziert wurden"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    conversation = relationship("AIConversation", back_populates="messages")
    feedbacks = relationship(
        "AIConversationFeedback",
        back_populates="message",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_ai_msg_conv_created", "conversation_id", "created_at"),
        {"comment": "Nachrichten im KI-Finanzassistent Chat"}
    )

    def __repr__(self) -> str:
        preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return (
            f"<AIConversationMessage("
            f"role={self.role}, "
            f"content='{preview}'"
            f")>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary fuer API."""
        return {
            "id": str(self.id),
            "role": self.role,
            "content": self.content,
            "intent": self.intent,
            "confidence": self.confidence,
            "search_results_count": self.search_results_count,
            "actions_proposed": self.actions_proposed,
            "processing_time_ms": self.processing_time_ms,
            "model_used": self.model_used,
            "tokens_used": self.tokens_used,
            "metadata": self.extra_data,
            "referenced_documents": self.referenced_documents,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AIConversationAction(Base):
    """
    Vorgeschlagene oder ausgefuehrte Aktion durch den Assistenten.

    Ermoeglicht vollstaendiges Tracking aller Aktionen
    fuer Audit und Rueckverfolgbarkeit.
    """
    __tablename__ = "ai_conversation_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_conversation_messages.id", ondelete="SET NULL"),
        nullable=True,
        comment="Nachricht in der die Aktion vorgeschlagen wurde"
    )

    # Aktion
    action_type = Column(
        String(50),
        nullable=False,
        comment="payment_run, approve_invoices, categorize_documents, etc."
    )
    description = Column(Text, nullable=False)
    status = Column(
        String(20),
        nullable=False,
        default=AIActionStatus.PROPOSED.value
    )

    # Parameter und Ergebnis
    parameters = Column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Aktionsparameter"
    )
    result = Column(
        JSONB,
        nullable=True,
        comment="Ergebnis nach Ausfuehrung"
    )
    error_message = Column(Text, nullable=True)

    # Betroffene Entitaeten
    affected_documents = Column(
        JSONB,
        nullable=True,
        comment="Array von betroffenen Dokument-IDs"
    )
    affected_count = Column(Integer, nullable=True)
    success_count = Column(Integer, nullable=True)
    failure_count = Column(Integer, nullable=True)

    # Sicherheit
    requires_confirmation = Column(Boolean, nullable=False, default=True)
    confirmed_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    proposed_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    conversation = relationship("AIConversation", back_populates="actions")
    confirmed_by = relationship("User")

    __table_args__ = (
        Index("ix_ai_action_conv", "conversation_id", "proposed_at"),
        Index("ix_ai_action_status", "status"),
        Index("ix_ai_action_type", "action_type"),
        {"comment": "Aktionen vom KI-Finanzassistent"}
    )

    def __repr__(self) -> str:
        return (
            f"<AIConversationAction("
            f"type={self.action_type}, "
            f"status={self.status}"
            f")>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary fuer API."""
        return {
            "id": str(self.id),
            "action_type": self.action_type,
            "description": self.description,
            "status": self.status,
            "parameters": self.parameters,
            "result": self.result,
            "error_message": self.error_message,
            "affected_count": self.affected_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "requires_confirmation": self.requires_confirmation,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "proposed_at": self.proposed_at.isoformat() if self.proposed_at else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
        }


class AIConversationFeedback(Base):
    """
    Benutzer-Feedback zu einer Assistenten-Antwort.

    Ermoeglicht kontinuierliche Verbesserung des Assistenten
    basierend auf Benutzer-Rueckmeldungen.
    """
    __tablename__ = "ai_conversation_feedbacks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_conversation_messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    # Feedback
    feedback_type = Column(String(20), nullable=False)
    rating = Column(
        Integer,
        nullable=True,
        comment="1-5 Sterne-Bewertung"
    )
    comment = Column(
        Text,
        nullable=True,
        comment="Optionaler Freitext-Kommentar"
    )

    # Korrekturen
    correction = Column(
        Text,
        nullable=True,
        comment="Korrigierte Antwort vom Benutzer"
    )
    expected_intent = Column(
        String(50),
        nullable=True,
        comment="Erwartete Intent falls falsch erkannt"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    message = relationship("AIConversationMessage", back_populates="feedbacks")
    user = relationship("User")

    __table_args__ = (
        CheckConstraint('rating >= 1 AND rating <= 5', name='ck_feedback_rating_range'),
        Index("ix_ai_feedback_type", "feedback_type", "created_at"),
        {"comment": "Benutzer-Feedback zu KI-Antworten"}
    )

    def __repr__(self) -> str:
        return (
            f"<AIConversationFeedback("
            f"type={self.feedback_type}, "
            f"rating={self.rating}"
            f")>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiere zu Dictionary fuer API."""
        return {
            "id": str(self.id),
            "feedback_type": self.feedback_type,
            "rating": self.rating,
            "comment": self.comment,
            "correction": self.correction,
            "expected_intent": self.expected_intent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
