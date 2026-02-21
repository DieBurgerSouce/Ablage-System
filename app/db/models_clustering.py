# -*- coding: utf-8 -*-
"""Dokumenten-Clustering Models.

Automatische Gruppierung aehnlicher Dokumente fuer intelligente
Ablage-Vorschlaege und Cluster-Visualisierung.

Features:
- Hierarchische Cluster mit Parent-Child-Beziehungen
- Cluster-Suggestions bei Upload (Top-3 aehnlichste Dokumente)
- Automatisches Clustering via DBSCAN
- Graph-Visualisierung mit Knoten und Kanten

Feinpoliert und durchdacht - Deutsche Dokumente mit hoechster Genauigkeit.
"""

import uuid
from typing import Optional

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

from app.db.models import Base, CrossDBJSON, CrossDBVector


# =============================================================================
# MODELS
# =============================================================================


class DocumentCluster(Base):
    """Dokumenten-Cluster fuer automatische Gruppierung.

    Cluster koennen hierarchisch organisiert sein (parent_cluster_id)
    und optional an eine Business Entity gebunden werden.
    Der Centroid repraesentiert den Mittelpunkt aller Dokument-Embeddings.
    """

    __tablename__ = "document_clusters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(
        String(255),
        nullable=False,
        comment="Anzeigename des Clusters",
    )
    description = Column(
        Text,
        nullable=True,
        comment="Optionale Beschreibung des Clusters",
    )
    cluster_type = Column(
        String(50),
        nullable=False,
        default="auto",
        comment="Cluster-Typ: auto, manual, entity, category",
    )
    centroid = Column(
        CrossDBVector(1024),
        nullable=True,
        comment="Cluster-Zentrum als Durchschnitt aller Dokument-Embeddings",
    )
    document_count = Column(
        Integer,
        nullable=False,
        default=0,
        comment="Anzahl der Dokumente im Cluster",
    )
    avg_similarity = Column(
        Float,
        nullable=True,
        comment="Durchschnittliche Intra-Cluster-Aehnlichkeit (0.0-1.0)",
    )

    # Multi-Tenant Isolation
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung fuer Multi-Company Isolation",
    )

    # Optionale Entity-Bindung
    business_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Optionale Zuordnung zu einer Business Entity",
    )

    # Hierarchische Cluster
    parent_cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_clusters.id", ondelete="SET NULL"),
        nullable=True,
        comment="Uebergeordneter Cluster fuer hierarchische Struktur",
    )

    metadata = Column(
        CrossDBJSON,
        nullable=True,
        default=dict,
        comment="Zusaetzliche Metadaten zum Cluster",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Ob der Cluster aktiv ist",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    company = relationship("Company")
    business_entity = relationship("BusinessEntity")
    parent_cluster = relationship(
        "DocumentCluster",
        remote_side="DocumentCluster.id",
        backref="child_clusters",
    )
    memberships = relationship(
        "DocumentClusterMembership",
        back_populates="cluster",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_document_clusters_company_type",
            "company_id",
            "cluster_type",
        ),
        {"comment": "Dokumenten-Cluster fuer automatische Gruppierung und Visualisierung"},
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentCluster("
            f"id={self.id}, "
            f"name={self.name!r}, "
            f"type={self.cluster_type}, "
            f"docs={self.document_count}"
            f")>"
        )


class DocumentClusterMembership(Base):
    """Zuordnung eines Dokuments zu einem Cluster.

    Jedes Dokument kann mehreren Clustern angehoeren.
    Der similarity_score gibt an, wie aehnlich das Dokument zum Cluster-Zentroid ist.
    """

    __tablename__ = "document_cluster_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Zugeordnetes Dokument",
    )
    cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_clusters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Zugeordneter Cluster",
    )
    similarity_score = Column(
        Float,
        nullable=False,
        comment="Aehnlichkeit zum Cluster-Zentroid (0.0-1.0)",
    )
    assigned_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Zeitpunkt der Zuordnung",
    )
    assigned_by = Column(
        String(50),
        nullable=False,
        default="auto",
        comment="Zuordnungsquelle: auto, user, system",
    )
    confidence = Column(
        Float,
        nullable=False,
        default=0.0,
        comment="Konfidenz der Zuordnung (0.0-1.0)",
    )

    # Relationships
    document = relationship("Document")
    cluster = relationship("DocumentCluster", back_populates="memberships")

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "cluster_id",
            name="uq_cluster_membership_doc_cluster",
        ),
        {
            "comment": "Zuordnungen von Dokumenten zu Clustern mit Aehnlichkeitswert",
        },
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentClusterMembership("
            f"doc={self.document_id}, "
            f"cluster={self.cluster_id}, "
            f"similarity={self.similarity_score:.2f}"
            f")>"
        )


class ClusterSuggestion(Base):
    """Vorschlag fuer Cluster-/Entity-/Kategorie-Zuordnung bei Upload.

    Wird generiert, wenn ein neues Dokument hochgeladen wird.
    Basiert auf der Aehnlichkeit zu bestehenden Dokumenten (pgvector).
    """

    __tablename__ = "cluster_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Dokument, fuer das der Vorschlag gilt",
    )
    suggested_cluster_id = Column(
        UUID(as_uuid=True),
        ForeignKey("document_clusters.id", ondelete="SET NULL"),
        nullable=True,
        comment="Vorgeschlagener Cluster",
    )
    suggested_entity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("business_entities.id", ondelete="SET NULL"),
        nullable=True,
        comment="Vorgeschlagene Business Entity",
    )
    suggested_category = Column(
        String(100),
        nullable=True,
        comment="Vorgeschlagene Kategorie/Dokumenttyp",
    )
    similarity_score = Column(
        Float,
        nullable=False,
        comment="Aehnlichkeitswert zum Referenz-Dokument (0.0-1.0)",
    )
    reference_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
        comment="Das aehnliche Referenz-Dokument",
    )
    status = Column(
        String(20),
        nullable=False,
        default="pending",
        comment="Status: pending, accepted, rejected, ignored",
    )
    responded_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Zeitpunkt der Nutzer-Reaktion",
    )

    # Multi-Tenant Isolation
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment="Mandanten-Zuordnung fuer Multi-Company Isolation",
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    document = relationship(
        "Document",
        foreign_keys=[document_id],
    )
    reference_document = relationship(
        "Document",
        foreign_keys=[reference_document_id],
    )
    suggested_cluster = relationship("DocumentCluster")
    suggested_entity = relationship("BusinessEntity")
    company = relationship("Company")

    __table_args__ = (
        Index(
            "ix_cluster_suggestions_doc_status",
            "document_id",
            "status",
        ),
        {
            "comment": "Cluster-/Entity-/Kategorie-Vorschlaege bei Dokument-Upload",
        },
    )

    def __repr__(self) -> str:
        return (
            f"<ClusterSuggestion("
            f"id={self.id}, "
            f"doc={self.document_id}, "
            f"score={self.similarity_score:.2f}, "
            f"status={self.status}"
            f")>"
        )
