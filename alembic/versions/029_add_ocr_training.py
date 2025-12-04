"""Add OCR Training and Validation System tables.

Revision ID: 029_add_ocr_training
Revises: 028_add_business_entities
Create Date: 2024-12-03

Enterprise OCR Training System mit Self-Learning.

Neue Tabellen:
- ocr_training_samples (Ground Truth Dokumente)
- ocr_backend_benchmarks (Benchmark-Ergebnisse pro Backend)
- ocr_validation_corrections (Feedback von Korrekturen)
- ocr_training_batches (Stichproben-Batches)
- ocr_training_batch_items (Items in Batches)
- ocr_backend_stats_daily (Taegliche Aggregationen)

Features:
- 4-Way Backend-Vergleich (DeepSeek, GOT-OCR, Surya GPU, Surya CPU)
- Self-Learning durch Korrektur-Feedback
- Stratifizierte Stichproben-Workflow
- Ground Truth Management mit Editor/Admin-Workflow
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "029_add_ocr_training"
down_revision = "028_add_business_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add OCR training tables."""

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
    # 1. CREATE OCR_TRAINING_SAMPLES TABLE
    # =========================================================================
    op.create_table(
        "ocr_training_samples",
        sa.Column("id", uuid_type, primary_key=True),

        # Dokumentreferenz
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),

        # Ground Truth
        sa.Column("ground_truth_text", sa.Text, nullable=True),

        # Dokumentklassifikation
        sa.Column("language", sa.String(10), default="de"),
        sa.Column("document_type", sa.String(50), nullable=True),
        sa.Column("difficulty", sa.String(20), default="medium"),

        # Dokumenteigenschaften
        sa.Column("has_umlauts", sa.Boolean, default=False),
        sa.Column("has_fraktur", sa.Boolean, default=False),
        sa.Column("has_tables", sa.Boolean, default=False),
        sa.Column("has_handwriting", sa.Boolean, default=False),
        sa.Column("has_stamps", sa.Boolean, default=False),
        sa.Column("has_signatures", sa.Boolean, default=False),

        # Umlaut-Tracking
        sa.Column("umlaut_words", json_type, nullable=True),

        # Extrahierte Felder
        sa.Column("extracted_fields", json_type, nullable=True),

        # Workflow Status
        sa.Column("status", sa.String(20), default="pending", nullable=False),

        # Annotation Tracking
        sa.Column("annotated_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("verified_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("annotation_notes", sa.Text, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("annotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for ocr_training_samples
    op.create_index("ix_ocr_training_samples_status", "ocr_training_samples", ["status"])
    op.create_index("ix_ocr_training_samples_language", "ocr_training_samples", ["language"])
    op.create_index("ix_ocr_training_samples_document_type", "ocr_training_samples", ["document_type"])
    op.create_index("ix_ocr_training_samples_file_hash", "ocr_training_samples", ["file_hash"])
    op.create_index("ix_ocr_training_samples_verified", "ocr_training_samples", ["status", "verified_at"])

    # =========================================================================
    # 2. CREATE OCR_BACKEND_BENCHMARKS TABLE
    # =========================================================================
    op.create_table(
        "ocr_backend_benchmarks",
        sa.Column("id", uuid_type, primary_key=True),

        # Referenzen
        sa.Column("training_sample_id", uuid_type, sa.ForeignKey("ocr_training_samples.id", ondelete="CASCADE"), nullable=False),

        # Backend Identifikation
        sa.Column("backend_name", sa.String(50), nullable=False),
        sa.Column("backend_version", sa.String(50), nullable=True),

        # OCR Output
        sa.Column("raw_text", sa.Text, nullable=True),

        # Qualitaetsmetriken
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("cer", sa.Float, nullable=True),
        sa.Column("wer", sa.Float, nullable=True),
        sa.Column("umlaut_accuracy", sa.Float, nullable=True),
        sa.Column("capitalization_accuracy", sa.Float, nullable=True),

        # Feld-spezifische Genauigkeit
        sa.Column("field_accuracies", json_type, nullable=True),

        # Fehler-Pattern-Analyse
        sa.Column("error_patterns", json_type, nullable=True),
        sa.Column("insertions", sa.Integer, default=0),
        sa.Column("deletions", sa.Integer, default=0),
        sa.Column("substitutions", sa.Integer, default=0),

        # Performance-Metriken
        sa.Column("processing_time_ms", sa.Integer, nullable=True),
        sa.Column("gpu_memory_mb", sa.Integer, nullable=True),

        # Timestamps
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes for ocr_backend_benchmarks
    op.create_index("ix_ocr_backend_benchmarks_sample", "ocr_backend_benchmarks", ["training_sample_id"])
    op.create_index("ix_ocr_backend_benchmarks_backend", "ocr_backend_benchmarks", ["backend_name"])
    op.create_index("ix_ocr_backend_benchmarks_sample_backend", "ocr_backend_benchmarks", ["training_sample_id", "backend_name"])
    op.create_index("ix_ocr_backend_benchmarks_processed_at", "ocr_backend_benchmarks", ["processed_at"])
    op.create_index("ix_ocr_backend_benchmarks_cer", "ocr_backend_benchmarks", ["cer"])

    # =========================================================================
    # 3. CREATE OCR_VALIDATION_CORRECTIONS TABLE
    # =========================================================================
    op.create_table(
        "ocr_validation_corrections",
        sa.Column("id", uuid_type, primary_key=True),

        # Dokument-Referenz
        sa.Column("document_id", uuid_type, sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),

        # Korrektur-Details
        sa.Column("original_text", sa.Text, nullable=False),
        sa.Column("corrected_text", sa.Text, nullable=False),
        sa.Column("correction_type", sa.String(30), default="general"),
        sa.Column("field_corrected", sa.String(50), nullable=True),

        # Backend
        sa.Column("backend_used", sa.String(50), nullable=False),

        # Kontext
        sa.Column("confidence_before", sa.Float, nullable=True),

        # Self-Learning Status
        sa.Column("applies_to_training", sa.Boolean, default=False),
        sa.Column("learning_processed", sa.Boolean, default=False),
        sa.Column("learning_processed_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("corrector_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes for ocr_validation_corrections
    op.create_index("ix_ocr_validation_corrections_document", "ocr_validation_corrections", ["document_id"])
    op.create_index("ix_ocr_validation_corrections_backend", "ocr_validation_corrections", ["backend_used"])
    op.create_index("ix_ocr_validation_corrections_type", "ocr_validation_corrections", ["correction_type"])
    op.create_index("ix_ocr_validation_corrections_learning", "ocr_validation_corrections", ["learning_processed"])
    op.create_index("ix_ocr_validation_corrections_created", "ocr_validation_corrections", ["created_at"])

    # =========================================================================
    # 4. CREATE OCR_TRAINING_BATCHES TABLE
    # =========================================================================
    op.create_table(
        "ocr_training_batches",
        sa.Column("id", uuid_type, primary_key=True),

        # Batch Identifikation
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("batch_type", sa.String(30), default="stratified"),

        # Stratifikations-Konfiguration
        sa.Column("stratification_config", json_type, nullable=True),

        # Groesse
        sa.Column("target_size", sa.Integer, default=100),
        sa.Column("actual_size", sa.Integer, default=0),

        # Status
        sa.Column("status", sa.String(20), default="draft"),

        # Fortschritt
        sa.Column("items_pending", sa.Integer, default=0),
        sa.Column("items_completed", sa.Integer, default=0),

        # Audit
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for ocr_training_batches
    op.create_index("ix_ocr_training_batches_status", "ocr_training_batches", ["status"])
    op.create_index("ix_ocr_training_batches_type", "ocr_training_batches", ["batch_type"])
    op.create_index("ix_ocr_training_batches_created", "ocr_training_batches", ["created_at"])

    # =========================================================================
    # 5. CREATE OCR_TRAINING_BATCH_ITEMS TABLE
    # =========================================================================
    op.create_table(
        "ocr_training_batch_items",
        sa.Column("id", uuid_type, primary_key=True),

        # Referenzen
        sa.Column("batch_id", uuid_type, sa.ForeignKey("ocr_training_batches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("training_sample_id", uuid_type, sa.ForeignKey("ocr_training_samples.id", ondelete="CASCADE"), nullable=False),

        # Reihenfolge
        sa.Column("sequence_number", sa.Integer, nullable=False),

        # Zuweisung
        sa.Column("assigned_to_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Status
        sa.Column("status", sa.String(20), default="pending"),

        # Validierungs-Ergebnis
        sa.Column("validation_notes", sa.Text, nullable=True),
        sa.Column("validation_time_seconds", sa.Integer, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for ocr_training_batch_items
    op.create_index("ix_ocr_training_batch_items_batch", "ocr_training_batch_items", ["batch_id"])
    op.create_index("ix_ocr_training_batch_items_sample", "ocr_training_batch_items", ["training_sample_id"])
    op.create_index("ix_ocr_training_batch_items_status", "ocr_training_batch_items", ["status"])
    op.create_index("ix_ocr_training_batch_items_assigned", "ocr_training_batch_items", ["assigned_to_id"])
    op.create_index("ix_ocr_training_batch_items_sequence", "ocr_training_batch_items", ["batch_id", "sequence_number"])

    # =========================================================================
    # 6. CREATE OCR_BACKEND_STATS_DAILY TABLE
    # =========================================================================
    op.create_table(
        "ocr_backend_stats_daily",
        sa.Column("id", uuid_type, primary_key=True),

        # Identifikation
        sa.Column("backend_name", sa.String(50), nullable=False),
        sa.Column("report_date", sa.DateTime(timezone=True), nullable=False),

        # Sample-Zaehler
        sa.Column("samples_processed", sa.Integer, default=0),
        sa.Column("samples_verified", sa.Integer, default=0),

        # Durchschnittsmetriken
        sa.Column("avg_cer", sa.Float, nullable=True),
        sa.Column("avg_wer", sa.Float, nullable=True),
        sa.Column("avg_umlaut_accuracy", sa.Float, nullable=True),
        sa.Column("avg_processing_time_ms", sa.Float, nullable=True),

        # Percentile
        sa.Column("p50_cer", sa.Float, nullable=True),
        sa.Column("p90_cer", sa.Float, nullable=True),
        sa.Column("p95_cer", sa.Float, nullable=True),

        # Aufschluesselungen (JSON)
        sa.Column("field_accuracy_stats", json_type, nullable=True),
        sa.Column("document_type_stats", json_type, nullable=True),
        sa.Column("language_stats", json_type, nullable=True),

        # Self-Learning Metriken
        sa.Column("corrections_count", sa.Integer, default=0),
        sa.Column("correction_types", json_type, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes for ocr_backend_stats_daily
    op.create_index("ix_ocr_backend_stats_daily_backend", "ocr_backend_stats_daily", ["backend_name"])
    op.create_index("ix_ocr_backend_stats_daily_date", "ocr_backend_stats_daily", ["report_date"])
    op.create_index("ix_ocr_backend_stats_daily_backend_date", "ocr_backend_stats_daily", ["backend_name", "report_date"], unique=True)


def downgrade() -> None:
    """Remove OCR training tables."""

    # Drop tables in reverse order (due to foreign keys)
    op.drop_table("ocr_backend_stats_daily")
    op.drop_table("ocr_training_batch_items")
    op.drop_table("ocr_training_batches")
    op.drop_table("ocr_validation_corrections")
    op.drop_table("ocr_backend_benchmarks")
    op.drop_table("ocr_training_samples")
