"""Add Bulk OCR Processing tables.

Revision ID: 030_add_bulk_processing
Revises: 029_add_ocr_training
Create Date: 2024-12-04

Bulk Processing System fuer Massenverarbeitung aller Trainings-Dokumente:
- ocr_bulk_processing_jobs (Job-Tracking)
- ocr_document_outputs (OCR-Output pro Backend/Dokument)

Features:
- Job-Management (Start, Pause, Resume)
- Checkpointing fuer Wiederaufnahme
- GPU-Queue-Management
- Fortschrittsverfolgung mit ETA
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add bulk processing tables."""

    # Check if we're using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # UUID type based on dialect
    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. CREATE OCR_BULK_PROCESSING_JOBS TABLE
    # =========================================================================
    op.create_table(
        "ocr_bulk_processing_jobs",
        sa.Column("id", uuid_type, primary_key=True),

        # Job Identifikation
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Status
        sa.Column("status", sa.String(20), default="pending", nullable=False),

        # Backend-Konfiguration
        sa.Column("backends", json_type, nullable=False),  # ["deepseek", "got-ocr", ...]

        # Fortschritt
        sa.Column("total_documents", sa.Integer, default=0),
        sa.Column("processed_documents", sa.Integer, default=0),
        sa.Column("failed_documents", sa.Integer, default=0),

        # Aktueller Stand
        sa.Column("current_backend", sa.String(50), nullable=True),
        sa.Column("current_backend_index", sa.Integer, default=0),
        sa.Column("current_document_index", sa.Integer, default=0),

        # Pro-Backend Statistiken
        sa.Column("documents_per_backend", json_type, default=dict),

        # Konfiguration
        sa.Column("configuration", json_type, default=dict),

        # Fehlerlog
        sa.Column("error_log", json_type, default=list),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checkpoint_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # Indexes fuer ocr_bulk_processing_jobs
    op.create_index("ix_ocr_bulk_processing_jobs_status", "ocr_bulk_processing_jobs", ["status"])
    op.create_index("ix_ocr_bulk_processing_jobs_created", "ocr_bulk_processing_jobs", ["created_at"])

    # =========================================================================
    # 2. CREATE OCR_DOCUMENT_OUTPUTS TABLE
    # =========================================================================
    op.create_table(
        "ocr_document_outputs",
        sa.Column("id", uuid_type, primary_key=True),

        # Referenzen
        sa.Column(
            "training_sample_id",
            uuid_type,
            sa.ForeignKey("ocr_training_samples.id", ondelete="CASCADE"),
            nullable=False
        ),
        sa.Column(
            "bulk_job_id",
            uuid_type,
            sa.ForeignKey("ocr_bulk_processing_jobs.id", ondelete="SET NULL"),
            nullable=True
        ),

        # Backend Identifikation
        sa.Column("backend_name", sa.String(50), nullable=False),
        sa.Column("backend_version", sa.String(50), nullable=True),

        # OCR Output
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("structured_output", json_type, nullable=True),

        # Qualitaetsmetriken
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("processing_time_ms", sa.Integer, nullable=True),
        sa.Column("gpu_memory_mb", sa.Integer, nullable=True),

        # Fehler
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("success", sa.Boolean, default=True),

        # Timestamps
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes fuer ocr_document_outputs
    op.create_index("ix_ocr_document_outputs_sample", "ocr_document_outputs", ["training_sample_id"])
    op.create_index("ix_ocr_document_outputs_backend", "ocr_document_outputs", ["backend_name"])
    op.create_index("ix_ocr_document_outputs_job", "ocr_document_outputs", ["bulk_job_id"])
    op.create_index(
        "ix_ocr_document_outputs_sample_backend",
        "ocr_document_outputs",
        ["training_sample_id", "backend_name"],
        unique=True
    )

    # =========================================================================
    # 3. ADD target_backend TO ocr_training_batches
    # =========================================================================
    # Fuer Backend-spezifische Stichproben
    op.add_column(
        "ocr_training_batches",
        sa.Column("target_backend", sa.String(50), nullable=True)
    )
    op.create_index(
        "ix_ocr_training_batches_target_backend",
        "ocr_training_batches",
        ["target_backend"]
    )

    # =========================================================================
    # 4. CREATE OCR_QUALITY_SNAPSHOTS TABLE (fuer Monitoring)
    # =========================================================================
    op.create_table(
        "ocr_quality_snapshots",
        sa.Column("id", uuid_type, primary_key=True),

        # Identifikation
        sa.Column("backend_name", sa.String(50), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), server_default=sa.func.now()),

        # Sample Counts
        sa.Column("sample_count", sa.Integer, default=0),

        # Qualitaetsmetriken
        sa.Column("avg_cer", sa.Float, nullable=True),
        sa.Column("avg_wer", sa.Float, nullable=True),
        sa.Column("avg_umlaut_accuracy", sa.Float, nullable=True),
        sa.Column("avg_processing_time_ms", sa.Float, nullable=True),

        # Percentiles
        sa.Column("p50_cer", sa.Float, nullable=True),
        sa.Column("p90_cer", sa.Float, nullable=True),
        sa.Column("p99_cer", sa.Float, nullable=True),

        # Korrekturen
        sa.Column("correction_count", sa.Integer, default=0),
        sa.Column("correction_types", json_type, default=dict),

        # Alert Status
        sa.Column("alert_triggered", sa.Boolean, default=False),
        sa.Column("alert_reason", sa.String(255), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes fuer ocr_quality_snapshots
    op.create_index("ix_ocr_quality_snapshots_backend", "ocr_quality_snapshots", ["backend_name"])
    op.create_index("ix_ocr_quality_snapshots_time", "ocr_quality_snapshots", ["snapshot_time"])
    op.create_index(
        "ix_ocr_quality_snapshots_backend_time",
        "ocr_quality_snapshots",
        ["backend_name", "snapshot_time"]
    )

    # =========================================================================
    # 5. CREATE OCR_MODEL_DEPLOYMENTS TABLE (fuer A/B Testing)
    # =========================================================================
    op.create_table(
        "ocr_model_deployments",
        sa.Column("id", uuid_type, primary_key=True),

        # Model Identifikation
        sa.Column("model_name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("model_type", sa.String(50), nullable=False),  # base, finetuned, lora

        # Deployment Info
        sa.Column("is_active", sa.Boolean, default=False),
        sa.Column("is_default", sa.Boolean, default=False),
        sa.Column("traffic_percentage", sa.Float, default=0.0),  # Fuer A/B Testing

        # Performance Metrics
        sa.Column("performance_metrics", json_type, default=dict),

        # Checkpoint Info
        sa.Column("checkpoint_path", sa.String(500), nullable=True),
        sa.Column("training_job_id", uuid_type, nullable=True),

        # Rollback Info
        sa.Column("previous_version", sa.String(50), nullable=True),
        sa.Column("rollback_reason", sa.Text, nullable=True),

        # Timestamps
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        # Audit
        sa.Column("deployed_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    # Indexes fuer ocr_model_deployments
    op.create_index("ix_ocr_model_deployments_model", "ocr_model_deployments", ["model_name"])
    op.create_index("ix_ocr_model_deployments_active", "ocr_model_deployments", ["is_active"])
    op.create_index(
        "ix_ocr_model_deployments_model_version",
        "ocr_model_deployments",
        ["model_name", "version"],
        unique=True
    )


def downgrade() -> None:
    """Remove bulk processing tables."""

    # Drop ocr_model_deployments
    op.drop_index("ix_ocr_model_deployments_model_version", table_name="ocr_model_deployments")
    op.drop_index("ix_ocr_model_deployments_active", table_name="ocr_model_deployments")
    op.drop_index("ix_ocr_model_deployments_model", table_name="ocr_model_deployments")
    op.drop_table("ocr_model_deployments")

    # Drop ocr_quality_snapshots
    op.drop_index("ix_ocr_quality_snapshots_backend_time", table_name="ocr_quality_snapshots")
    op.drop_index("ix_ocr_quality_snapshots_time", table_name="ocr_quality_snapshots")
    op.drop_index("ix_ocr_quality_snapshots_backend", table_name="ocr_quality_snapshots")
    op.drop_table("ocr_quality_snapshots")

    # Remove target_backend from ocr_training_batches
    op.drop_index("ix_ocr_training_batches_target_backend", table_name="ocr_training_batches")
    op.drop_column("ocr_training_batches", "target_backend")

    # Drop ocr_document_outputs
    op.drop_index("ix_ocr_document_outputs_sample_backend", table_name="ocr_document_outputs")
    op.drop_index("ix_ocr_document_outputs_job", table_name="ocr_document_outputs")
    op.drop_index("ix_ocr_document_outputs_backend", table_name="ocr_document_outputs")
    op.drop_index("ix_ocr_document_outputs_sample", table_name="ocr_document_outputs")
    op.drop_table("ocr_document_outputs")

    # Drop ocr_bulk_processing_jobs
    op.drop_index("ix_ocr_bulk_processing_jobs_created", table_name="ocr_bulk_processing_jobs")
    op.drop_index("ix_ocr_bulk_processing_jobs_status", table_name="ocr_bulk_processing_jobs")
    op.drop_table("ocr_bulk_processing_jobs")
