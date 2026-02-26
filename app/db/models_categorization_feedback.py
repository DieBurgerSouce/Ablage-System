# -*- coding: utf-8 -*-
"""
Kategorisierungs-Feedback Modell fuer Lern-Pipeline.

Speichert Nutzer-Korrekturen, damit der AutoCategorizationEngine
aus manuellen Korrekturen lernen und kuenftige Vorschlaege
verbessern kann.

Feinpoliert und durchdacht - Enterprise Self-Learning Kategorisierung.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base


# =============================================================================
# ENUMS
# =============================================================================


class CategorizationSource(str, Enum):
    """Quelle der Kategorisierungs-Entscheidung."""

    AUTO_HIGH_CONFIDENCE = "auto_high_confidence"   # Automatisch, hohe Confidence
    AUTO_LOW_CONFIDENCE = "auto_low_confidence"     # Automatisch, niedrige Confidence
    USER_CORRECTION = "user_correction"             # Nutzer hat korrigiert
    BULK_ACCEPT = "bulk_accept"                     # Massenakzeptanz


# =============================================================================
# MODELS
# =============================================================================


class CategorizationFeedback(Base):
    """
    Speichert Nutzer-Korrekturen fuer Lern-Pipeline.

    Wenn ein Nutzer eine Kategorie aendert, wird die urspruengliche
    Vorhersage und die Korrektur gespeichert. Dieses Feedback fliesst
    in die Gewichtungsanpassung des AutoCategorizationEngine ein.

    Multi-Tenant: Immer gefiltert nach company_id.
    GDPR: Kein PII wird gespeichert (nur IDs und Kategorien).
    """

    __tablename__ = "categorization_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Multi-Tenancy
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung fuer Multi-Company Isolation",
    )

    # Dokument-Referenz
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Referenz auf verarbeitetes Dokument (SET NULL bei Loeschung)",
    )

    # Vorhergesagte und tatsaechliche Kategorie
    predicted_category = Column(
        String(100),
        nullable=False,
        comment="Vom Engine vorhergesagte Kategorie (z.B. 'invoice', 'contract')",
    )
    actual_category = Column(
        String(100),
        nullable=False,
        comment="Tatsaechliche Kategorie nach Nutzer-Korrektur",
    )
    confidence = Column(
        Float,
        nullable=False,
        comment="Confidence-Score der urspruenglichen Vorhersage (0.0-1.0)",
    )
    was_correct = Column(
        Boolean,
        nullable=False,
        comment="True wenn Vorhersage korrekt war, False bei Korrektur",
    )

    # Kontext fuer Lern-Pipeline
    vendor_name = Column(
        String(255),
        nullable=True,
        comment="Anonymisierter Lieferantenname fuer Muster-Erkennung",
    )
    vendor_entity_id = Column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="FK zu business_entities fuer lieferantenbezogene Lernmuster",
    )
    document_type = Column(
        String(50),
        nullable=True,
        comment="Dokumenttyp zum Zeitpunkt der Kategorisierung",
    )

    # Quelle der Entscheidung
    source = Column(
        String(50),
        nullable=False,
        default=CategorizationSource.AUTO_HIGH_CONFIDENCE.value,
        comment="Wie wurde kategorisiert: auto_high_confidence, user_correction, bulk_accept",
    )

    # Nutzer der die Korrektur vorgenommen hat (anonymisiert via ID)
    corrected_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Nutzer der die Korrektur vorgenommen hat",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document = relationship("Document", foreign_keys=[document_id])
    corrected_by = relationship("User", foreign_keys=[corrected_by_id])

    __table_args__ = (
        Index("ix_cat_feedback_company_id", "company_id"),
        Index("ix_cat_feedback_document_id", "document_id"),
        Index("ix_cat_feedback_vendor_entity", "vendor_entity_id"),
        Index("ix_cat_feedback_created_at", "created_at"),
        # Compound: Vendor + Kategorie fuer Lern-Queries
        Index(
            "ix_cat_feedback_vendor_category",
            "vendor_entity_id",
            "actual_category",
        ),
        # Compound: Company + korrekte Vorhersagen (fuer Accuracy-Berechnung)
        Index(
            "ix_cat_feedback_company_correct",
            "company_id",
            "was_correct",
            "created_at",
        ),
    )
