"""Add barcode_detections table for QR/Barcode pipeline integration.

Revision ID: 230
Revises: 229
Create Date: 2026-02-16

Erstellt die barcode_detections Tabelle fuer die Speicherung
erkannter Barcodes und QR-Codes pro Dokument.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "230"
down_revision = "229"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "barcode_detections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_type", sa.String(30), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("raw_value", sa.String(4096), nullable=False),
        sa.Column(
            "parsed_data",
            postgresql.JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("position_x", sa.Integer, nullable=False, server_default="0"),
        sa.Column("position_y", sa.Integer, nullable=False, server_default="0"),
        sa.Column("position_width", sa.Integer, nullable=False, server_default="0"),
        sa.Column("position_height", sa.Integer, nullable=False, server_default="0"),
        sa.Column("page_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.0"),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        # Constraints
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_barcode_confidence_range",
        ),
        sa.CheckConstraint(
            "page_number >= 1",
            name="ck_barcode_page_positive",
        ),
    )

    # Indexes
    op.create_index(
        "ix_barcode_detections_document_id",
        "barcode_detections",
        ["document_id"],
    )
    op.create_index(
        "ix_barcode_detections_code_type",
        "barcode_detections",
        ["code_type"],
    )
    op.create_index(
        "ix_barcode_detections_category",
        "barcode_detections",
        ["category"],
    )
    op.create_index(
        "ix_barcode_detections_company_id",
        "barcode_detections",
        ["company_id"],
    )
    op.create_index(
        "ix_barcode_detections_created_at",
        "barcode_detections",
        ["created_at"],
    )
    op.create_index(
        "ix_barcode_detections_document_page",
        "barcode_detections",
        ["document_id", "page_number"],
    )
    op.create_index(
        "ix_barcode_detections_category_company",
        "barcode_detections",
        ["category", "company_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_barcode_detections_category_company")
    op.drop_index("ix_barcode_detections_document_page")
    op.drop_index("ix_barcode_detections_created_at")
    op.drop_index("ix_barcode_detections_company_id")
    op.drop_index("ix_barcode_detections_category")
    op.drop_index("ix_barcode_detections_code_type")
    op.drop_index("ix_barcode_detections_document_id")
    op.drop_table("barcode_detections")
