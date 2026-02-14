"""
Comment Enhancement satellite model.

Erweitert das bestehende DocumentComment-System um:
- PDF-Markup Positionierung (Seite, x, y, Breite, Hoehe)
- CommentSuggestion: Vorgeschlagene Aenderungen
- CommentThread: Explizite Thread-Verwaltung mit Status
- CommentAnchor: Verschiedene Anker-Typen (Text, Region, Feld)

Baut auf DocumentComment (models.py) auf und ergaenzt die
Google-Docs-Style Commenting-Funktionalitaet.
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


class CommentAnchorType(str, Enum):
    """Typ des Kommentar-Ankers im PDF."""
    PIN = "pin"             # Punkt-Marker
    HIGHLIGHT = "highlight" # Text-Hervorhebung
    RECTANGLE = "rectangle" # Rechteck-Markierung
    FREEFORM = "freeform"   # Freihand-Markierung
    FIELD = "field"         # Extraktionsfeld-Referenz


class SuggestionStatus(str, Enum):
    """Status einer vorgeschlagenen Aenderung."""
    OFFEN = "offen"
    ANGENOMMEN = "angenommen"
    ABGELEHNT = "abgelehnt"


class ThreadStatus(str, Enum):
    """Status eines Kommentar-Threads."""
    OFFEN = "offen"
    GELOEST = "geloest"
    GESCHLOSSEN = "geschlossen"


# ============================================================================
# Comment Anchor (PDF-Positionierung)
# ============================================================================


class CommentAnchor(Base):
    """PDF-Positionierung fuer einen Kommentar.

    Speichert die exakte Position eines Kommentars auf einer PDF-Seite:
    - Seitennummer
    - Position (x, y) in relativen Koordinaten (0.0 - 1.0)
    - Groesse (width, height) fuer Rechteck-Markierungen
    - Anker-Typ (Pin, Highlight, Rechteck, Freihand)
    """
    __tablename__ = "comment_anchors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_comments.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # PDF-Position
    page_number = Column(Integer, nullable=False, comment="Seitennummer (1-basiert)")
    x = Column(Float, nullable=False, comment="X-Position (0.0 - 1.0 relativ zur Seitenbreite)")
    y = Column(Float, nullable=False, comment="Y-Position (0.0 - 1.0 relativ zur Seitenhoehe)")
    width = Column(Float, nullable=True, comment="Breite der Markierung (0.0 - 1.0)")
    height = Column(Float, nullable=True, comment="Hoehe der Markierung (0.0 - 1.0)")

    # Anker-Typ
    anchor_type = Column(
        String(30),
        default=CommentAnchorType.PIN.value,
        nullable=False,
    )

    # Text-Highlight
    highlighted_text = Column(Text, nullable=True, comment="Markierter Text bei Highlight")
    text_start_offset = Column(Integer, nullable=True, comment="Start-Offset im extrahierten Text")
    text_end_offset = Column(Integer, nullable=True, comment="End-Offset im extrahierten Text")

    # Freihand-Pfad (SVG path data)
    freeform_path = Column(Text, nullable=True, comment="SVG path data fuer Freihand")

    # Farbe der Markierung
    color = Column(String(7), default="#FBBF24", comment="Hex-Farbe der Markierung")

    # Relationship
    comment = relationship("DocumentComment", backref="anchor", uselist=False)

    __table_args__ = (
        Index("ix_comment_anchors_comment_id", "comment_id"),
        Index("ix_comment_anchors_page", "page_number"),
    )


# ============================================================================
# Comment Thread (Explizite Thread-Verwaltung)
# ============================================================================


class CommentThread(Base):
    """Expliziter Kommentar-Thread mit Status.

    Fasst zusammengehoerige Kommentare zu einem Thread zusammen.
    Unterstuetzt Resolve/Reopen-Workflow.
    """
    __tablename__ = "comment_threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Thread-Status
    status = Column(
        String(30),
        default=ThreadStatus.OFFEN.value,
        nullable=False,
    )

    # Zusammenfassung
    subject = Column(String(255), nullable=True, comment="Thread-Betreff")
    reply_count = Column(Integer, default=0)

    # Root-Kommentar
    root_comment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_comments.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Resolve/Reopen
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    document = relationship("Document")
    root_comment = relationship("DocumentComment", foreign_keys=[root_comment_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_comment_threads_document_id", "document_id"),
        Index("ix_comment_threads_company_id", "company_id"),
        Index("ix_comment_threads_status", "status"),
    )


# ============================================================================
# Comment Suggestion (Vorgeschlagene Aenderungen)
# ============================================================================


class CommentSuggestion(Base):
    """Vorgeschlagene Aenderung an einem Dokument.

    Aehnlich wie Google Docs Suggestions - ein User kann eine
    Aenderung vorschlagen, die dann angenommen oder abgelehnt wird.
    """
    __tablename__ = "comment_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    comment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_comments.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Was soll geaendert werden
    field_name = Column(
        String(100),
        nullable=True,
        comment="Betroffenes Extraktionsfeld (z.B. invoice_number)",
    )
    original_value = Column(Text, nullable=True, comment="Aktueller Wert")
    suggested_value = Column(Text, nullable=False, comment="Vorgeschlagener neuer Wert")
    reason = Column(Text, nullable=True, comment="Begruendung fuer die Aenderung")

    # Status
    status = Column(
        String(30),
        default=SuggestionStatus.OFFEN.value,
        nullable=False,
    )

    # Entscheidung
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decision_comment = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    comment = relationship("DocumentComment")
    document = relationship("Document")
    decided_by = relationship("User", foreign_keys=[decided_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_comment_suggestions_comment_id", "comment_id"),
        Index("ix_comment_suggestions_document_id", "document_id"),
        Index("ix_comment_suggestions_status", "status"),
    )
