# -*- coding: utf-8 -*-
"""
Saved Search Models für Ablage-System.

Gespeicherte Suchen für schnelle Wiederverwendung:
- Benutzerspezifische Such-Templates
- Filter-Persistierung
- Nutzungsstatistiken
- Standard-Suche pro Benutzer

Feinpoliert und durchdacht - Enterprise-grade Saved Search.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


class SavedSearch(Base):
    """
    Gespeicherte Such-Konfigurationen für Benutzer.

    Ermöglicht Speicherung von:
    - Suchbegriff
    - Suchtyp (FTS/Semantic/Hybrid)
    - Filter-Zustand (document_type, status, date_range, etc.)
    - Sortierung
    - Nutzungsstatistiken
    """
    __tablename__ = "saved_searches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Besitzer der gespeicherten Suche"
    )
    name = Column(
        String(200),
        nullable=False,
        comment="Benutzer-definierter Name für die Suche"
    )
    query = Column(
        Text,
        nullable=False,
        comment="Der Suchbegriff / Query String"
    )
    search_type = Column(
        String(20),
        nullable=False,
        default="hybrid",
        comment="Suchtyp: fts, semantic, hybrid"
    )
    filters = Column(
        CrossDBJSON,
        nullable=True,
        comment="Gespeicherter Filter-Zustand (document_type, status, date_range, etc.)"
    )
    sort_field = Column(
        String(50),
        nullable=True,
        comment="Sortierfeld (created_at, relevance, etc.)"
    )
    sort_order = Column(
        String(4),
        nullable=True,
        comment="Sortierreihenfolge: asc oder desc"
    )
    is_default = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Ist dies die Standard-Suche des Benutzers?"
    )
    use_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl der Ausführungen dieser Suche"
    )
    last_used_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der letzten Ausführung"
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="Erstellungszeitpunkt"
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        onupdate=func.now(),
        comment="Letzte Änderung"
    )
    is_shared = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="Mit Team geteilt"
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Firma für Team-Sharing"
    )

    # Relationships
    user = relationship("User", backref="saved_searches")

    # Indexes
    __table_args__ = (
        Index("ix_saved_searches_user_id", "user_id"),
        UniqueConstraint("user_id", "name", name="uq_saved_searches_user_name"),
    )

    def __repr__(self) -> str:
        return f"<SavedSearch(id={self.id}, user_id={self.user_id}, name='{self.name}')>"
