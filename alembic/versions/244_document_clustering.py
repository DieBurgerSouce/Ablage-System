"""Dokumenten-Clustering Tabellen.

Revision ID: 244
Revises: 243
Create Date: 2026-02-21

Erstellt die Infrastruktur fuer intelligentes Dokumenten-Clustering:
- document_clusters: Automatisch generierte Cluster (hierarchisch)
- document_cluster_memberships: Zuordnung Dokument->Cluster mit Aehnlichkeit
- cluster_suggestions: Upload-Vorschlaege fuer neue Dokumente

Phase 2.1 der Feature-Roadmap.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "244"
down_revision = "243"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. document_clusters - Automatische Dokument-Gruppierung
    # ------------------------------------------------------------------
    op.create_table(
        "document_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False,
                  comment="Anzeigename des Clusters"),
        sa.Column("description", sa.Text(), nullable=True,
                  comment="Optionale Beschreibung des Clusters"),
        sa.Column("cluster_type", sa.String(50), nullable=False,
                  server_default="auto",
                  comment="Cluster-Typ: auto, manual, entity, category"),
        sa.Column("centroid", postgresql.ARRAY(sa.Float()), nullable=True,
                  comment="Cluster-Zentrum als Embedding-Vektor"),
        sa.Column("document_count", sa.Integer(), nullable=False,
                  server_default="0",
                  comment="Anzahl der Dokumente im Cluster"),
        sa.Column("avg_similarity", sa.Float(), nullable=True,
                  comment="Durchschnittliche Intra-Cluster-Aehnlichkeit (0.0-1.0)"),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("business_entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("business_entities.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("parent_cluster_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("document_clusters.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True,
                  server_default="{}",
                  comment="Zusaetzliche Metadaten zum Cluster"),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default="true",
                  comment="Ob der Cluster aktiv ist"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        comment="Dokumenten-Cluster fuer automatische Gruppierung und Visualisierung",
    )
    op.create_index(
        "ix_document_clusters_company_id",
        "document_clusters",
        ["company_id"],
    )
    op.create_index(
        "ix_document_clusters_company_type",
        "document_clusters",
        ["company_id", "cluster_type"],
    )
    op.create_index(
        "ix_document_clusters_business_entity_id",
        "document_clusters",
        ["business_entity_id"],
    )

    # ------------------------------------------------------------------
    # 2. document_cluster_memberships - Dokument-zu-Cluster Zuordnung
    # ------------------------------------------------------------------
    op.create_table(
        "document_cluster_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("document_clusters.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("similarity_score", sa.Float(), nullable=False,
                  comment="Aehnlichkeit zum Cluster-Zentroid (0.0-1.0)"),
        sa.Column("assigned_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False,
                  comment="Zeitpunkt der Zuordnung"),
        sa.Column("assigned_by", sa.String(50), nullable=False,
                  server_default="auto",
                  comment="Zuordnungsquelle: auto, user, system"),
        sa.Column("confidence", sa.Float(), nullable=False,
                  server_default="0",
                  comment="Konfidenz der Zuordnung (0.0-1.0)"),
        comment="Zuordnungen von Dokumenten zu Clustern mit Aehnlichkeitswert",
    )
    op.create_index(
        "ix_cluster_memberships_document_id",
        "document_cluster_memberships",
        ["document_id"],
    )
    op.create_index(
        "ix_cluster_memberships_cluster_id",
        "document_cluster_memberships",
        ["cluster_id"],
    )
    op.create_unique_constraint(
        "uq_cluster_membership_doc_cluster",
        "document_cluster_memberships",
        ["document_id", "cluster_id"],
    )

    # ------------------------------------------------------------------
    # 3. cluster_suggestions - Upload-Vorschlaege
    # ------------------------------------------------------------------
    op.create_table(
        "cluster_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("suggested_cluster_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("document_clusters.id", ondelete="SET NULL"),
                  nullable=True,
                  comment="Vorgeschlagener Cluster"),
        sa.Column("suggested_entity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("business_entities.id", ondelete="SET NULL"),
                  nullable=True,
                  comment="Vorgeschlagene Business Entity"),
        sa.Column("suggested_category", sa.String(100), nullable=True,
                  comment="Vorgeschlagene Kategorie/Dokumenttyp"),
        sa.Column("similarity_score", sa.Float(), nullable=False,
                  comment="Aehnlichkeitswert zum Referenz-Dokument (0.0-1.0)"),
        sa.Column("reference_document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="SET NULL"),
                  nullable=True,
                  comment="Das aehnliche Referenz-Dokument"),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending",
                  comment="Status: pending, accepted, rejected, ignored"),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Zeitpunkt der Nutzer-Reaktion"),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("companies.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        comment="Cluster-/Entity-/Kategorie-Vorschlaege bei Dokument-Upload",
    )
    op.create_index(
        "ix_cluster_suggestions_document_id",
        "cluster_suggestions",
        ["document_id"],
    )
    op.create_index(
        "ix_cluster_suggestions_doc_status",
        "cluster_suggestions",
        ["document_id", "status"],
    )
    op.create_index(
        "ix_cluster_suggestions_company_id",
        "cluster_suggestions",
        ["company_id"],
    )


def downgrade() -> None:
    # cluster_suggestions
    op.drop_index("ix_cluster_suggestions_company_id",
                  table_name="cluster_suggestions")
    op.drop_index("ix_cluster_suggestions_doc_status",
                  table_name="cluster_suggestions")
    op.drop_index("ix_cluster_suggestions_document_id",
                  table_name="cluster_suggestions")
    op.drop_table("cluster_suggestions")

    # document_cluster_memberships
    op.drop_constraint("uq_cluster_membership_doc_cluster",
                       "document_cluster_memberships", type_="unique")
    op.drop_index("ix_cluster_memberships_cluster_id",
                  table_name="document_cluster_memberships")
    op.drop_index("ix_cluster_memberships_document_id",
                  table_name="document_cluster_memberships")
    op.drop_table("document_cluster_memberships")

    # document_clusters
    op.drop_index("ix_document_clusters_business_entity_id",
                  table_name="document_clusters")
    op.drop_index("ix_document_clusters_company_type",
                  table_name="document_clusters")
    op.drop_index("ix_document_clusters_company_id",
                  table_name="document_clusters")
    op.drop_table("document_clusters")
