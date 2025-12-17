"""Add Business Document Profiles for Auto Ground-Truth Pipeline.

Revision ID: 041_add_business_profiles
Revises: 040_add_surya_model_versions
Create Date: 2024-12-16

Smart Ground-Truth Pipeline fuer Enterprise-Scale (500+ Docs/Tag).

Neue Tabellen:
- business_document_profiles (Dokumenttyp-Profile mit Auto-Accept Schwellenwerten)
- coverage_snapshots (Taegliche Coverage-Snapshots fuer Trend-Analyse)

Erweiterungen:
- ocr_training_samples: Neue Felder fuer Auto-Accept Pipeline
  - business_priority, auto_accepted, auto_acceptance_confidence
  - source, needs_spot_check, spot_check_passed

Bei 500+ Docs/Tag ist manuelle Annotation unrealistisch.
OCR-Ergebnisse mit Confidence > 95% werden automatisch als Ground-Truth akzeptiert.
10% Stichproben-Review fuer Qualitaetssicherung.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "041_add_business_profiles"
down_revision = "040_add_surya_model_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add business document profiles and auto-accept pipeline tables."""

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
    # 1. CREATE BUSINESS_DOCUMENT_PROFILES TABLE
    # =========================================================================
    op.create_table(
        "business_document_profiles",
        sa.Column("id", uuid_type, primary_key=True),

        # Dokumenttyp-Identifikation
        sa.Column("document_type", sa.String(50), nullable=False, unique=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Business-Gewichtung
        sa.Column("estimated_daily_volume", sa.Integer, default=100),
        sa.Column("business_criticality", sa.Float, default=1.0),

        # Auto-Annotation Schwellenwerte
        sa.Column("auto_accept_confidence", sa.Float, default=0.95),
        sa.Column("min_text_length", sa.Integer, default=50),
        sa.Column("require_umlaut_validation", sa.Boolean, default=True),

        # Training-Gewichtung
        sa.Column("training_weight", sa.Float, default=1.0),
        sa.Column("target_coverage", sa.Float, default=0.90),

        # Validierungsregeln
        sa.Column("validation_rules", json_type, default=dict),

        # Statistiken
        sa.Column("current_sample_count", sa.Integer, default=0),
        sa.Column("verified_sample_count", sa.Integer, default=0),
        sa.Column("auto_accepted_count", sa.Integer, default=0),
        sa.Column("coverage_percentage", sa.Float, default=0.0),

        # Aktivierung
        sa.Column("is_active", sa.Boolean, default=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes fuer business_document_profiles
    op.create_index("ix_business_document_profiles_type", "business_document_profiles", ["document_type"])
    op.create_index("ix_business_document_profiles_active", "business_document_profiles", ["is_active"])
    op.create_index("ix_business_document_profiles_criticality", "business_document_profiles", ["business_criticality"])

    # =========================================================================
    # 2. CREATE COVERAGE_SNAPSHOTS TABLE
    # =========================================================================
    op.create_table(
        "coverage_snapshots",
        sa.Column("id", uuid_type, primary_key=True),

        # Snapshot-Datum
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False),

        # Aggregierte Metriken
        sa.Column("total_documents_processed", sa.Integer, default=0),
        sa.Column("total_auto_accepted", sa.Integer, default=0),
        sa.Column("total_manually_verified", sa.Integer, default=0),
        sa.Column("total_rejected", sa.Integer, default=0),

        # Coverage pro Dokumenttyp
        sa.Column("coverage_by_type", json_type, default=dict),

        # Gewichtete Gesamt-Coverage
        sa.Column("weighted_coverage", sa.Float, default=0.0),

        # Qualitaetsmetriken
        sa.Column("auto_accept_avg_confidence", sa.Float, nullable=True),
        sa.Column("spot_check_success_rate", sa.Float, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Indexes fuer coverage_snapshots
    op.create_index("ix_coverage_snapshots_date", "coverage_snapshots", ["snapshot_date"])
    op.create_index("ix_coverage_snapshots_weighted", "coverage_snapshots", ["weighted_coverage"])

    # =========================================================================
    # 3. EXTEND OCR_TRAINING_SAMPLES TABLE
    # =========================================================================

    # Add Auto-Accept Pipeline columns
    op.add_column("ocr_training_samples", sa.Column("business_priority", sa.Float, default=1.0))
    op.add_column("ocr_training_samples", sa.Column("auto_accepted", sa.Boolean, default=False))
    op.add_column("ocr_training_samples", sa.Column("auto_acceptance_confidence", sa.Float, nullable=True))
    op.add_column("ocr_training_samples", sa.Column("source", sa.String(30), default="manual"))
    op.add_column("ocr_training_samples", sa.Column("needs_spot_check", sa.Boolean, default=False))
    op.add_column("ocr_training_samples", sa.Column("spot_check_passed", sa.Boolean, nullable=True))
    op.add_column("ocr_training_samples", sa.Column("spot_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ocr_training_samples", sa.Column("spot_checked_by_id", uuid_type, nullable=True))

    # Add foreign key for spot_checked_by_id
    op.create_foreign_key(
        "fk_ocr_training_samples_spot_checked_by",
        "ocr_training_samples",
        "users",
        ["spot_checked_by_id"],
        ["id"],
        ondelete="SET NULL"
    )

    # Add new indexes for Auto-Accept Pipeline
    op.create_index("ix_ocr_training_samples_auto_accepted", "ocr_training_samples", ["auto_accepted"])
    op.create_index("ix_ocr_training_samples_source", "ocr_training_samples", ["source"])
    op.create_index("ix_ocr_training_samples_spot_check", "ocr_training_samples", ["needs_spot_check", "spot_check_passed"])
    op.create_index("ix_ocr_training_samples_priority", "ocr_training_samples", ["business_priority"])

    # =========================================================================
    # 4. SEED DEFAULT BUSINESS DOCUMENT PROFILES
    # =========================================================================
    # Using raw SQL for dialect-independent UUID generation

    if is_postgres:
        op.execute("""
            INSERT INTO business_document_profiles (
                id, document_type, display_name, description,
                estimated_daily_volume, business_criticality,
                auto_accept_confidence, min_text_length, require_umlaut_validation,
                training_weight, target_coverage, is_active
            ) VALUES
            (
                gen_random_uuid(),
                'invoice',
                'Rechnung',
                'Geschaeftsrechnungen - hoechste Prioritaet fuer OCR-Training',
                300, 1.5, 0.95, 100, true, 4.5, 0.90, true
            ),
            (
                gen_random_uuid(),
                'contract',
                'Vertrag',
                'Vertraege und Vereinbarungen',
                100, 1.3, 0.95, 200, true, 1.3, 0.90, true
            ),
            (
                gen_random_uuid(),
                'letter',
                'Brief',
                'Geschaeftsbriefe und allgemeine Korrespondenz',
                100, 1.0, 0.93, 50, true, 1.0, 0.90, true
            ),
            (
                gen_random_uuid(),
                'delivery_note',
                'Lieferschein',
                'Lieferscheine und Versanddokumente',
                50, 0.8, 0.92, 50, true, 0.4, 0.85, true
            ),
            (
                gen_random_uuid(),
                'order_confirmation',
                'Auftragsbestaetigung',
                'Auftragsbestaetigungen und Bestellungen',
                50, 1.2, 0.94, 80, true, 0.6, 0.90, true
            )
        """)


def downgrade() -> None:
    """Remove business document profiles and auto-accept pipeline tables."""

    # Remove indexes from ocr_training_samples
    op.drop_index("ix_ocr_training_samples_priority", table_name="ocr_training_samples")
    op.drop_index("ix_ocr_training_samples_spot_check", table_name="ocr_training_samples")
    op.drop_index("ix_ocr_training_samples_source", table_name="ocr_training_samples")
    op.drop_index("ix_ocr_training_samples_auto_accepted", table_name="ocr_training_samples")

    # Remove foreign key
    op.drop_constraint("fk_ocr_training_samples_spot_checked_by", "ocr_training_samples", type_="foreignkey")

    # Remove columns from ocr_training_samples
    op.drop_column("ocr_training_samples", "spot_checked_by_id")
    op.drop_column("ocr_training_samples", "spot_checked_at")
    op.drop_column("ocr_training_samples", "spot_check_passed")
    op.drop_column("ocr_training_samples", "needs_spot_check")
    op.drop_column("ocr_training_samples", "source")
    op.drop_column("ocr_training_samples", "auto_acceptance_confidence")
    op.drop_column("ocr_training_samples", "auto_accepted")
    op.drop_column("ocr_training_samples", "business_priority")

    # Drop coverage_snapshots
    op.drop_index("ix_coverage_snapshots_weighted", table_name="coverage_snapshots")
    op.drop_index("ix_coverage_snapshots_date", table_name="coverage_snapshots")
    op.drop_table("coverage_snapshots")

    # Drop business_document_profiles
    op.drop_index("ix_business_document_profiles_criticality", table_name="business_document_profiles")
    op.drop_index("ix_business_document_profiles_active", table_name="business_document_profiles")
    op.drop_index("ix_business_document_profiles_type", table_name="business_document_profiles")
    op.drop_table("business_document_profiles")
