"""Add Surya Model Versions table for Continuous Improvement System.

Revision ID: 040_add_surya_model_versions
Revises: 039_add_quick_classification
Create Date: 2024-12-15

Surya OCR Continuous Improvement System - Model Versioning.

Neue Tabellen:
- surya_model_versions (Checkpoint-Verwaltung mit Metriken)
- surya_training_runs (Training-Durchlaeufe mit Konfiguration)
- surya_ab_tests (A/B Testing fuer Model-Vergleich)

Features:
- Checkpoint-Versionierung mit semantischen Versionen
- Metriken-Tracking (CER, WER, Umlaut-Accuracy)
- A/B Testing mit Traffic-Splitting
- Automatisches Rollback bei Qualitaetsverlust
- Training-History mit Config-Dokumentation
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "040_add_surya_model_versions"
down_revision = "039_add_quick_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Surya model versioning tables."""

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
    # 1. CREATE SURYA_MODEL_VERSIONS TABLE
    # =========================================================================
    op.create_table(
        "surya_model_versions",
        sa.Column("id", uuid_type, primary_key=True),

        # Versions-Identifikation
        sa.Column("version", sa.String(100), nullable=False, unique=True),
        sa.Column("version_major", sa.Integer, nullable=False, default=1),
        sa.Column("version_minor", sa.Integer, nullable=False, default=0),
        sa.Column("version_patch", sa.Integer, nullable=False, default=0),

        # Checkpoint-Pfade
        sa.Column("checkpoint_path", sa.String(500), nullable=False),
        sa.Column("checkpoint_size_mb", sa.Float, nullable=True),

        # Basis-Modell
        sa.Column("base_model", sa.String(100), default="vikp/surya_rec"),
        sa.Column("parent_version_id", uuid_type, sa.ForeignKey("surya_model_versions.id", ondelete="SET NULL"), nullable=True),

        # Qualitaetsmetriken (Benchmark-Ergebnisse)
        sa.Column("cer", sa.Float, nullable=True),  # Character Error Rate
        sa.Column("wer", sa.Float, nullable=True),  # Word Error Rate
        sa.Column("umlaut_accuracy", sa.Float, nullable=True),  # KRITISCH!
        sa.Column("eszett_accuracy", sa.Float, nullable=True),  # SS-Genauigkeit
        sa.Column("capitalization_accuracy", sa.Float, nullable=True),

        # Detaillierte Metriken (JSON)
        sa.Column("metrics_by_document_type", json_type, nullable=True),
        sa.Column("umlaut_confusion_matrix", json_type, nullable=True),
        sa.Column("error_patterns", json_type, nullable=True),

        # Training-Informationen
        sa.Column("training_samples_count", sa.Integer, nullable=True),
        sa.Column("training_epochs", sa.Integer, nullable=True),
        sa.Column("training_config", json_type, nullable=True),
        sa.Column("training_duration_minutes", sa.Float, nullable=True),

        # Deployment-Status
        sa.Column("is_active", sa.Boolean, default=False),
        sa.Column("is_production", sa.Boolean, default=False),
        sa.Column("traffic_percentage", sa.Float, default=0.0),

        # Rollback-Info
        sa.Column("rolled_back_from_id", uuid_type, sa.ForeignKey("surya_model_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("rollback_reason", sa.Text, nullable=True),

        # Audit
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for surya_model_versions
    op.create_index("ix_surya_model_versions_version", "surya_model_versions", ["version"])
    op.create_index("ix_surya_model_versions_is_active", "surya_model_versions", ["is_active"])
    op.create_index("ix_surya_model_versions_is_production", "surya_model_versions", ["is_production"])
    op.create_index("ix_surya_model_versions_created_at", "surya_model_versions", ["created_at"])
    op.create_index("ix_surya_model_versions_umlaut_acc", "surya_model_versions", ["umlaut_accuracy"])
    op.create_index("ix_surya_model_versions_cer", "surya_model_versions", ["cer"])

    # =========================================================================
    # 2. CREATE SURYA_TRAINING_RUNS TABLE
    # =========================================================================
    op.create_table(
        "surya_training_runs",
        sa.Column("id", uuid_type, primary_key=True),

        # Referenz auf resultierendes Modell
        sa.Column("model_version_id", uuid_type, sa.ForeignKey("surya_model_versions.id", ondelete="SET NULL"), nullable=True),

        # Run-Identifikation
        sa.Column("run_name", sa.String(255), nullable=False),
        sa.Column("run_type", sa.String(50), default="incremental"),  # full, incremental, correction_based

        # Trigger-Informationen
        sa.Column("trigger_reason", sa.String(100), nullable=True),  # scheduled, correction_threshold, manual, quality_degradation
        sa.Column("trigger_metrics", json_type, nullable=True),

        # Training-Konfiguration
        sa.Column("config", json_type, nullable=False),
        sa.Column("dataset_config", json_type, nullable=True),

        # Dataset-Statistiken
        sa.Column("training_samples", sa.Integer, default=0),
        sa.Column("validation_samples", sa.Integer, default=0),
        sa.Column("test_samples", sa.Integer, default=0),
        sa.Column("umlaut_samples", sa.Integer, default=0),
        sa.Column("fraktur_samples", sa.Integer, default=0),

        # Training-Fortschritt
        sa.Column("status", sa.String(30), default="pending"),  # pending, running, completed, failed, cancelled
        sa.Column("current_epoch", sa.Integer, default=0),
        sa.Column("total_epochs", sa.Integer, nullable=True),
        sa.Column("current_step", sa.Integer, default=0),
        sa.Column("total_steps", sa.Integer, nullable=True),

        # Loss-Tracking
        sa.Column("training_loss", sa.Float, nullable=True),
        sa.Column("validation_loss", sa.Float, nullable=True),
        sa.Column("best_validation_loss", sa.Float, nullable=True),
        sa.Column("loss_history", json_type, nullable=True),

        # Metriken waehrend Training
        sa.Column("metrics_history", json_type, nullable=True),

        # Ressourcen-Nutzung
        sa.Column("gpu_memory_peak_mb", sa.Integer, nullable=True),
        sa.Column("gpu_utilization_avg", sa.Float, nullable=True),

        # Fehlerbehandlung
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_traceback", sa.Text, nullable=True),

        # Audit
        sa.Column("started_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for surya_training_runs
    op.create_index("ix_surya_training_runs_status", "surya_training_runs", ["status"])
    op.create_index("ix_surya_training_runs_type", "surya_training_runs", ["run_type"])
    op.create_index("ix_surya_training_runs_model", "surya_training_runs", ["model_version_id"])
    op.create_index("ix_surya_training_runs_created", "surya_training_runs", ["created_at"])

    # =========================================================================
    # 3. CREATE SURYA_AB_TESTS TABLE
    # =========================================================================
    op.create_table(
        "surya_ab_tests",
        sa.Column("id", uuid_type, primary_key=True),

        # Test-Identifikation
        sa.Column("test_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Modell-Versionen im Test
        sa.Column("control_version_id", uuid_type, sa.ForeignKey("surya_model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("treatment_version_id", uuid_type, sa.ForeignKey("surya_model_versions.id", ondelete="CASCADE"), nullable=False),

        # Traffic-Konfiguration
        sa.Column("control_traffic_pct", sa.Float, default=80.0),
        sa.Column("treatment_traffic_pct", sa.Float, default=20.0),

        # Test-Status
        sa.Column("status", sa.String(30), default="pending"),  # pending, running, completed, aborted

        # Erfolgskriterien
        sa.Column("success_criteria", json_type, nullable=True),  # z.B. {"umlaut_accuracy_improvement": 0.02, "cer_reduction": 0.01}
        sa.Column("minimum_samples", sa.Integer, default=100),
        sa.Column("minimum_duration_hours", sa.Integer, default=48),

        # Ergebnisse - Control
        sa.Column("control_samples", sa.Integer, default=0),
        sa.Column("control_cer", sa.Float, nullable=True),
        sa.Column("control_wer", sa.Float, nullable=True),
        sa.Column("control_umlaut_accuracy", sa.Float, nullable=True),
        sa.Column("control_metrics", json_type, nullable=True),

        # Ergebnisse - Treatment
        sa.Column("treatment_samples", sa.Integer, default=0),
        sa.Column("treatment_cer", sa.Float, nullable=True),
        sa.Column("treatment_wer", sa.Float, nullable=True),
        sa.Column("treatment_umlaut_accuracy", sa.Float, nullable=True),
        sa.Column("treatment_metrics", json_type, nullable=True),

        # Statistische Analyse
        sa.Column("statistical_significance", sa.Float, nullable=True),  # p-value
        sa.Column("confidence_interval_lower", sa.Float, nullable=True),
        sa.Column("confidence_interval_upper", sa.Float, nullable=True),
        sa.Column("effect_size", sa.Float, nullable=True),

        # Entscheidung
        sa.Column("winner", sa.String(20), nullable=True),  # control, treatment, inconclusive
        sa.Column("decision_reason", sa.Text, nullable=True),
        sa.Column("auto_deployed", sa.Boolean, default=False),

        # Audit
        sa.Column("created_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indexes for surya_ab_tests
    op.create_index("ix_surya_ab_tests_status", "surya_ab_tests", ["status"])
    op.create_index("ix_surya_ab_tests_control", "surya_ab_tests", ["control_version_id"])
    op.create_index("ix_surya_ab_tests_treatment", "surya_ab_tests", ["treatment_version_id"])
    op.create_index("ix_surya_ab_tests_created", "surya_ab_tests", ["created_at"])

    # =========================================================================
    # 4. CREATE SURYA_BENCHMARK_HISTORY TABLE
    # =========================================================================
    op.create_table(
        "surya_benchmark_history",
        sa.Column("id", uuid_type, primary_key=True),

        # Modell-Referenz
        sa.Column("model_version_id", uuid_type, sa.ForeignKey("surya_model_versions.id", ondelete="CASCADE"), nullable=False),

        # Benchmark-Kontext
        sa.Column("benchmark_type", sa.String(50), default="full"),  # full, umlaut_focus, fraktur, quick
        sa.Column("test_fixtures_count", sa.Integer, nullable=True),

        # Aggregierte Metriken
        sa.Column("avg_cer", sa.Float, nullable=True),
        sa.Column("avg_wer", sa.Float, nullable=True),
        sa.Column("avg_umlaut_accuracy", sa.Float, nullable=True),
        sa.Column("avg_processing_time_ms", sa.Float, nullable=True),

        # Percentile
        sa.Column("p50_cer", sa.Float, nullable=True),
        sa.Column("p90_cer", sa.Float, nullable=True),
        sa.Column("p95_cer", sa.Float, nullable=True),
        sa.Column("p99_cer", sa.Float, nullable=True),

        # Detaillierte Ergebnisse
        sa.Column("results_by_fixture", json_type, nullable=True),
        sa.Column("results_by_document_type", json_type, nullable=True),
        sa.Column("umlaut_confusion_details", json_type, nullable=True),

        # Vergleich mit vorheriger Version
        sa.Column("comparison_version_id", uuid_type, sa.ForeignKey("surya_model_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cer_improvement", sa.Float, nullable=True),
        sa.Column("wer_improvement", sa.Float, nullable=True),
        sa.Column("umlaut_accuracy_improvement", sa.Float, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes for surya_benchmark_history
    op.create_index("ix_surya_benchmark_history_model", "surya_benchmark_history", ["model_version_id"])
    op.create_index("ix_surya_benchmark_history_type", "surya_benchmark_history", ["benchmark_type"])
    op.create_index("ix_surya_benchmark_history_created", "surya_benchmark_history", ["created_at"])


def downgrade() -> None:
    """Remove Surya model versioning tables."""

    # Drop tables in reverse order (due to foreign keys)
    op.drop_table("surya_benchmark_history")
    op.drop_table("surya_ab_tests")
    op.drop_table("surya_training_runs")
    op.drop_table("surya_model_versions")
