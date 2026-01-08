"""Add Vector Search A/B Testing Tables.

Revision ID: 043_add_vector_ab_testing
Revises: 042_add_llm_review_fields
Create Date: 2024-12-16

A/B Testing zwischen pgvector und Qdrant.
Metriken-Sammlung fuer datengetriebene Backend-Auswahl.

Neue Tabellen:
- vector_ab_experiments: Experiment-Definitionen
- vector_search_metrics: Per-Request Metriken

Features:
- Deterministisches User-Routing
- Latenz-Tracking (embedding, search, rerank)
- Relevance-Metriken (click-through, feedback)
- Statistical Significance Berechnung
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create vector A/B testing tables."""

    # Check if we're using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # JSON type based on dialect
    if is_postgres:
        json_type = postgresql.JSONB
    else:
        json_type = sa.JSON

    # UUID type based on dialect
    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
    else:
        uuid_type = sa.String(36)

    # =========================================================================
    # CREATE VECTOR_AB_EXPERIMENTS TABLE
    # =========================================================================

    op.create_table(
        "vector_ab_experiments",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Varianten
        sa.Column("control_backend", sa.String(50), default="pgvector", nullable=False),
        sa.Column("treatment_backend", sa.String(50), nullable=False),
        sa.Column("control_embedding_model", sa.String(100), default="intfloat/multilingual-e5-large"),
        sa.Column("treatment_embedding_model", sa.String(100), nullable=True),

        # Traffic Split (0-100%)
        sa.Column("traffic_percentage", sa.Integer, default=10, nullable=False),

        # Status: draft, running, paused, completed
        sa.Column("status", sa.String(20), default="draft", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),

        # Metriken-Ziele
        sa.Column("primary_metric", sa.String(50), default="latency_p95"),
        sa.Column("secondary_metrics", json_type, nullable=True),

        # Ergebnis
        sa.Column("winner", sa.String(50), nullable=True),  # control, treatment, inconclusive
        sa.Column("statistical_significance", sa.Float, nullable=True),
        sa.Column("results_summary", json_type, nullable=True),

        # Audit
        sa.Column("created_by", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Index fuer aktive Experiments
    op.create_index(
        "ix_vector_ab_experiments_status",
        "vector_ab_experiments",
        ["status"],
        unique=False
    )

    # =========================================================================
    # CREATE VECTOR_SEARCH_METRICS TABLE
    # =========================================================================

    op.create_table(
        "vector_search_metrics",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("experiment_id", uuid_type, sa.ForeignKey("vector_ab_experiments.id", ondelete="SET NULL"), nullable=True),

        # Request-Info
        sa.Column("user_id", uuid_type, nullable=True),
        sa.Column("query_hash", sa.String(64), nullable=True),
        sa.Column("query_length", sa.Integer, nullable=True),

        # Backend-Info
        sa.Column("backend", sa.String(50), nullable=False),  # pgvector, qdrant
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("collection", sa.String(50), nullable=True),  # documents, chunks

        # Latenz (ms)
        sa.Column("latency_total_ms", sa.Integer, nullable=True),
        sa.Column("latency_embedding_ms", sa.Integer, nullable=True),
        sa.Column("latency_search_ms", sa.Integer, nullable=True),
        sa.Column("latency_rerank_ms", sa.Integer, nullable=True),

        # Ergebnisse
        sa.Column("results_count", sa.Integer, nullable=True),
        sa.Column("top_score", sa.Float, nullable=True),

        # Relevance (optional, falls User-Feedback)
        sa.Column("clicked_result_position", sa.Integer, nullable=True),
        sa.Column("feedback_score", sa.Float, nullable=True),  # 1-5 Sterne
        sa.Column("feedback_text", sa.Text, nullable=True),

        # Fehler
        sa.Column("error_occurred", sa.Boolean, default=False),
        sa.Column("error_message", sa.Text, nullable=True),

        # Timestamp
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes fuer Analyse
    op.create_index(
        "ix_vector_search_metrics_experiment",
        "vector_search_metrics",
        ["experiment_id"],
        unique=False
    )

    op.create_index(
        "ix_vector_search_metrics_backend",
        "vector_search_metrics",
        ["backend"],
        unique=False
    )

    op.create_index(
        "ix_vector_search_metrics_created",
        "vector_search_metrics",
        ["created_at"],
        unique=False
    )

    # Compound Index fuer A/B Analyse
    op.create_index(
        "ix_vector_search_metrics_ab_analysis",
        "vector_search_metrics",
        ["experiment_id", "backend", "created_at"],
        unique=False
    )

    # =========================================================================
    # ADD EMBEDDING_MODEL COLUMN TO DOCUMENTS (optional, fuer Multi-Model)
    # =========================================================================

    # Pruefe ob Spalte bereits existiert
    try:
        op.add_column(
            "documents",
            sa.Column("qdrant_indexed_at", sa.DateTime(timezone=True), nullable=True)
        )
    except Exception:
        pass  # Spalte existiert bereits

    try:
        op.add_column(
            "rag_document_chunks",
            sa.Column("qdrant_indexed_at", sa.DateTime(timezone=True), nullable=True)
        )
    except Exception:
        pass  # Spalte existiert bereits


def downgrade() -> None:
    """Remove vector A/B testing tables."""

    # Drop columns from existing tables
    try:
        op.drop_column("documents", "qdrant_indexed_at")
    except Exception:
        pass

    try:
        op.drop_column("rag_document_chunks", "qdrant_indexed_at")
    except Exception:
        pass

    # Drop indexes
    op.drop_index("ix_vector_search_metrics_ab_analysis", table_name="vector_search_metrics")
    op.drop_index("ix_vector_search_metrics_created", table_name="vector_search_metrics")
    op.drop_index("ix_vector_search_metrics_backend", table_name="vector_search_metrics")
    op.drop_index("ix_vector_search_metrics_experiment", table_name="vector_search_metrics")
    op.drop_index("ix_vector_ab_experiments_status", table_name="vector_ab_experiments")

    # Drop tables
    op.drop_table("vector_search_metrics")
    op.drop_table("vector_ab_experiments")
