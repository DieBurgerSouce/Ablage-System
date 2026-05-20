# -*- coding: utf-8 -*-
"""
Custom Field Definition satellite model for Ablage-System.

Ermoeglicht benutzerdefinierte Felder pro Dokumenttyp und Mandant.
Feldtypen: Text, Zahl, Datum, Boolean, Dropdown, Multi-Select, Lookup.

Baut auf dem Document-Modell (models.py) auf.
Die eigentlichen Feldwerte werden als JSONB in documents.custom_field_values gespeichert.
"""

import uuid
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON


# ============================================================================
# Enums
# ============================================================================


class FieldType(str, Enum):
    """Typ eines benutzerdefinierten Feldes."""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOLEAN = "boolean"
    DROPDOWN = "dropdown"
    MULTI_SELECT = "multi_select"
    LOOKUP = "lookup"


# ============================================================================
# Custom Field Definition
# ============================================================================


class CustomFieldDefinition(Base):
    """Definition eines benutzerdefinierten Feldes.

    Definiert Name, Typ, Validierungsregeln und Anzeigeoptionen
    fuer ein benutzerdefiniertes Feld. Gilt pro Mandant und optional
    pro Dokumenttyp.

    Die tatsaechlichen Werte werden als JSONB in documents.custom_field_values
    gespeichert, nicht in einer separaten Tabelle.
    """
    __tablename__ = "custom_field_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Identifikation
    name = Column(
        String(64),
        nullable=False,
        comment="Interner Name (snake_case, eindeutig pro document_type+company)",
    )
    label = Column(
        String(200),
        nullable=False,
        comment="Anzeige-Label (deutsch)",
    )
    description = Column(
        String(500),
        nullable=True,
        comment="Optionale Beschreibung fuer Benutzer",
    )
    field_type = Column(
        String(20),
        nullable=False,
        comment="Feldtyp: text, number, date, boolean, dropdown, multi_select, lookup",
    )

    # Geltungsbereich
    document_type = Column(
        String(50),
        nullable=True,
        comment="Dokumenttyp-Filter (None = alle Typen)",
    )

    # Validierung
    required = Column(Boolean, default=False, nullable=False)
    default_value = Column(String(500), nullable=True)
    validation_rules = Column(
        CrossDBJSON,
        nullable=True,
        comment="Validierungsregeln: {min, max, pattern, min_length, max_length}",
    )

    # Dropdown/Multi-Select Optionen
    dropdown_options = Column(
        CrossDBJSON,
        nullable=True,
        comment="Optionsliste: [{value, label}]",
    )

    # Lookup-Konfiguration
    lookup_entity = Column(
        String(100),
        nullable=True,
        comment="Lookup-Zielentitaet (z.B. 'business_entity', 'document')",
    )

    # Anzeige
    sort_order = Column(Integer, default=0, nullable=False)
    is_searchable = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="In Volltextsuche einschliessen",
    )
    is_filterable = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Als Filter in Dokumentliste anbieten",
    )

    # Mandant und Ersteller
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    company = relationship("Company", backref="custom_field_definitions")
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        # Eindeutiger Name pro Mandant und Dokumenttyp
        UniqueConstraint(
            "company_id", "document_type", "name",
            name="uq_custom_field_company_doctype_name",
        ),
        Index("ix_custom_field_def_company_id", "company_id"),
        Index("ix_custom_field_def_document_type", "document_type"),
        Index("ix_custom_field_def_is_active", "is_active"),
        Index(
            "ix_custom_field_def_company_active",
            "company_id", "is_active", "document_type",
        ),
    )
