"""Add company_id to OCR training tables for multi-tenant isolation.

Revision ID: 237
Revises: 236
Create Date: 2026-02-19

Fuegt company_id zu den 4 globalen OCR-Training-Tabellen hinzu,
damit Trainings-Daten mandantenspezifisch isoliert werden koennen.

Tabellen:
- ocr_training_samples
- ocr_training_batches
- ocr_training_batch_items  (Join-Tabelle; erbt Scope vom Batch, aber direkte FK fuer Query-Filtering)
- ocr_model_deployments

nullable=True initial, da bestehende Zeilen keine company_id haben.
Eine Folge-Migration kann NOT NULL setzen, nachdem Backfill abgeschlossen ist.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "237"
down_revision = "236"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # ocr_training_samples
    # ------------------------------------------------------------------
    op.add_column(
        "ocr_training_samples",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ocr_training_samples_company_id",
        "ocr_training_samples",
        ["company_id"],
    )
    op.create_index(
        "ix_ocr_training_samples_company_status",
        "ocr_training_samples",
        ["company_id", "status"],
    )

    # ------------------------------------------------------------------
    # ocr_training_batches
    # ------------------------------------------------------------------
    op.add_column(
        "ocr_training_batches",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ocr_training_batches_company_id",
        "ocr_training_batches",
        ["company_id"],
    )
    op.create_index(
        "ix_ocr_training_batches_company_status",
        "ocr_training_batches",
        ["company_id", "status"],
    )

    # ------------------------------------------------------------------
    # ocr_training_batch_items
    # ------------------------------------------------------------------
    op.add_column(
        "ocr_training_batch_items",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ocr_training_batch_items_company_id",
        "ocr_training_batch_items",
        ["company_id"],
    )
    op.create_index(
        "ix_ocr_training_batch_items_company_status",
        "ocr_training_batch_items",
        ["company_id", "status"],
    )

    # ------------------------------------------------------------------
    # ocr_model_deployments
    # ------------------------------------------------------------------
    op.add_column(
        "ocr_model_deployments",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_ocr_model_deployments_company_id",
        "ocr_model_deployments",
        ["company_id"],
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # ocr_model_deployments
    # ------------------------------------------------------------------
    op.drop_index("ix_ocr_model_deployments_company_id", table_name="ocr_model_deployments")
    op.drop_constraint(
        "ocr_model_deployments_company_id_fkey",
        "ocr_model_deployments",
        type_="foreignkey",
    )
    op.drop_column("ocr_model_deployments", "company_id")

    # ------------------------------------------------------------------
    # ocr_training_batch_items
    # ------------------------------------------------------------------
    op.drop_index("ix_ocr_training_batch_items_company_status", table_name="ocr_training_batch_items")
    op.drop_index("ix_ocr_training_batch_items_company_id", table_name="ocr_training_batch_items")
    op.drop_constraint(
        "ocr_training_batch_items_company_id_fkey",
        "ocr_training_batch_items",
        type_="foreignkey",
    )
    op.drop_column("ocr_training_batch_items", "company_id")

    # ------------------------------------------------------------------
    # ocr_training_batches
    # ------------------------------------------------------------------
    op.drop_index("ix_ocr_training_batches_company_status", table_name="ocr_training_batches")
    op.drop_index("ix_ocr_training_batches_company_id", table_name="ocr_training_batches")
    op.drop_constraint(
        "ocr_training_batches_company_id_fkey",
        "ocr_training_batches",
        type_="foreignkey",
    )
    op.drop_column("ocr_training_batches", "company_id")

    # ------------------------------------------------------------------
    # ocr_training_samples
    # ------------------------------------------------------------------
    op.drop_index("ix_ocr_training_samples_company_status", table_name="ocr_training_samples")
    op.drop_index("ix_ocr_training_samples_company_id", table_name="ocr_training_samples")
    op.drop_constraint(
        "ocr_training_samples_company_id_fkey",
        "ocr_training_samples",
        type_="foreignkey",
    )
    op.drop_column("ocr_training_samples", "company_id")
