"""
Knowledge Graph satellite model.

Erweiterte Datenmodelle für den Knowledge Graph:
- KnowledgeGraphRelation: Explizite Beziehungen zwischen Entities
- EntityResolution: Entity-Matching / Deduplizierung
- GraphSnapshot: Graph-Snapshots für Zeitreihen-Analyse

Baut auf dem bestehenden KnowledgeGraphService auf und ergaenzt
persistente Beziehungs-Speicherung (Adjacency List Pattern).
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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.models import Base, CrossDBJSON
from app.db.models_base import SoftDeleteMixin

# ============================================================================
# Enums
# ============================================================================


class RelationType(str, Enum):
    """Beziehungstypen im Knowledge Graph."""
    LIEFERT_AN = "liefert_an"
    SCHULDET = "schuldet"
    BEZIEHT_SICH_AUF = "bezieht_sich_auf"
    ERSETZT = "ersetzt"
    IST_ANLAGE_ZU = "ist_anlage_zu"
    GEHOERT_ZU_VORGANG = "gehoert_zu_vorgang"
    HAT_RECHNUNG = "hat_rechnung"
    BEZAHLT_DURCH = "bezahlt_durch"
    ERSTELLT_VON = "erstellt_von"
    GENEHMIGT_VON = "genehmigt_von"
    VERKNUEPFT_MIT = "verknüpft_mit"
    IST_NACHFOLGER_VON = "ist_nachfolger_von"
    REFERENZIERT = "referenziert"


class EntityMatchStatus(str, Enum):
    """Status der Entity-Resolution."""
    VORGESCHLAGEN = "vorgeschlagen"
    BESTAETIGT = "bestätigt"
    ABGELEHNT = "abgelehnt"
    AUTOMATISCH = "automatisch"


class GraphNodeType(str, Enum):
    """Typen von Knoten im Knowledge Graph."""
    ENTITY = "entity"
    DOCUMENT = "document"
    INVOICE = "invoice"
    TRANSACTION = "transaction"
    FOLDER = "folder"
    USER = "user"
    PROJECT = "project"


# ============================================================================
# Knowledge Graph Relation
# ============================================================================


class KnowledgeGraphRelation(SoftDeleteMixin, Base):
    """Explizite Beziehung zwischen zwei Knoten im Knowledge Graph.

    Speichert gerichtete Beziehungen mit Typ, Stärke und Metadaten.
    Kann automatisch aus OCR-Ergebnissen extrahiert oder manuell erstellt werden.
    """
    __tablename__ = "knowledge_graph_relations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Quelle und Ziel (polymorph - können verschiedene Entity-Typen sein)
    source_id = Column(UUID(as_uuid=True), nullable=False, comment="Quell-Knoten UUID")
    source_type = Column(
        String(50),
        nullable=False,
        comment="Typ: entity, document, invoice, transaction, folder",
    )
    target_id = Column(UUID(as_uuid=True), nullable=False, comment="Ziel-Knoten UUID")
    target_type = Column(String(50), nullable=False)

    # Beziehung
    relation_type = Column(
        String(50),
        nullable=False,
        comment="Beziehungstyp (z.B. liefert_an, schuldet)",
    )
    relation_label = Column(
        String(255),
        nullable=True,
        comment="Menschenlesbares Label",
    )

    # Stärke und Vertrauen
    strength = Column(
        Float,
        default=1.0,
        comment="Beziehungsstärke (0.0 - 1.0)",
    )
    confidence = Column(
        Float,
        default=1.0,
        comment="Extraktions-Confidence (0.0 - 1.0)",
    )

    # Herkunft
    is_auto_extracted = Column(
        Boolean,
        default=False,
        comment="Automatisch aus OCR/AI extrahiert",
    )
    extraction_source = Column(
        String(100),
        nullable=True,
        comment="Quelle: ocr, user, import, rule",
    )
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Dokument aus dem die Beziehung extrahiert wurde",
    )

    # Metadaten
    relation_metadata = Column(CrossDBJSON, default=dict)

    # Zeitliche Gültigkeit
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    source_document = relationship("Document", foreign_keys=[source_document_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_kg_relations_company_id", "company_id"),
        Index("ix_kg_relations_source", "source_id", "source_type"),
        Index("ix_kg_relations_target", "target_id", "target_type"),
        Index("ix_kg_relations_type", "relation_type"),
        Index("ix_kg_relations_confidence", "confidence"),
        Index("ix_kg_relations_deleted_at", "deleted_at"),
        Index(
            "ix_kg_relations_pair",
            "source_id", "target_id", "relation_type",
        ),
    )


# ============================================================================
# Entity Resolution
# ============================================================================


class EntityResolution(Base):
    """Entity-Matching für Deduplizierung.

    Erkennt ob zwei Entities dieselbe reale Person/Firma repraesentieren.
    Z.B. "Mueller GmbH" und "Müller GmbH" sind dieselbe Firma.
    """
    __tablename__ = "entity_resolutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Kandidaten-Paar
    entity_a_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_b_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Matching-Score und Status
    similarity_score = Column(
        Float,
        nullable=False,
        comment="Ähnlichkeitsscore 0.0-1.0",
    )
    match_status = Column(
        String(30),
        default=EntityMatchStatus.VORGESCHLAGEN.value,
        nullable=False,
    )

    # Canonical Entity (Haupteintrag nach Zusammenführung)
    canonical_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Haupt-Entity nach Zusammenführung",
    )

    # Matching-Details
    match_reasons = Column(
        CrossDBJSON,
        default=list,
        comment="Gruende: name_similarity, address_match, tax_id_match, etc.",
    )
    match_method = Column(
        String(50),
        nullable=True,
        comment="Methode: fuzzy_name, tax_id, address, combined",
    )

    # Audit
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    entity_a = relationship("BusinessEntity", foreign_keys=[entity_a_id])
    entity_b = relationship("BusinessEntity", foreign_keys=[entity_b_id])
    canonical_entity = relationship("BusinessEntity", foreign_keys=[canonical_entity_id])
    resolved_by = relationship("User", foreign_keys=[resolved_by_id])

    __table_args__ = (
        UniqueConstraint(
            "entity_a_id", "entity_b_id",
            name="uq_entity_resolution_pair",
        ),
        Index("ix_entity_resolutions_company_id", "company_id"),
        Index("ix_entity_resolutions_status", "match_status"),
        Index("ix_entity_resolutions_score", "similarity_score"),
        Index("ix_entity_resolutions_canonical", "canonical_entity_id"),
    )


# ============================================================================
# Graph Snapshot (für Zeitreihen-Analyse)
# ============================================================================


class GraphSnapshot(Base):
    """Periodischer Snapshot des Knowledge Graph.

    Speichert Graph-Metriken für Trend-Analyse:
    - Wie waechst der Graph über Zeit?
    - Welche Beziehungstypen nehmen zu/ab?
    - Community-Entwicklung
    """
    __tablename__ = "knowledge_graph_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Snapshot-Zeitpunkt
    snapshot_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Graph-Metriken
    total_nodes = Column(Integer, default=0)
    total_edges = Column(Integer, default=0)
    total_entities = Column(Integer, default=0)
    total_documents = Column(Integer, default=0)

    # Beziehungs-Verteilung
    relation_counts = Column(
        CrossDBJSON,
        default=dict,
        comment='{"liefert_an": 42, "schuldet": 15, ...}',
    )

    # Community-Metriken
    community_count = Column(Integer, default=0)
    largest_community_size = Column(Integer, default=0)
    avg_community_size = Column(Float, default=0.0)

    # Qualitaets-Metriken
    avg_confidence = Column(Float, default=0.0)
    auto_extracted_ratio = Column(Float, default=0.0)
    unresolved_entities = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_kg_snapshots_company_id", "company_id"),
        Index("ix_kg_snapshots_snapshot_at", "snapshot_at"),
    )
