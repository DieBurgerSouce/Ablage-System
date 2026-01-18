"""Add shipment tracking tables for carrier integration.

Revision ID: 100_add_shipment_tracking
Revises: 099_add_knowledge_management
Create Date: 2026-01-17

Paketdienst-Integration:
- DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post
- Sendungsverfolgung mit Events
- Verknuepfung mit Entities und Dokumenten
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "100_add_shipment_tracking"
down_revision: Union[str, None] = "100_slack_integration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Shipments Table
    op.create_table(
        "shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tracking_number", sa.String(50), nullable=False),
        sa.Column("carrier", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("direction", sa.String(20), nullable=False, server_default="inbound"),
        sa.Column("status", sa.String(30), nullable=False, server_default="unknown"),
        sa.Column("status_description", sa.String(255), nullable=True),
        sa.Column("tracking_url", sa.String(500), nullable=True),
        sa.Column("estimated_delivery", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_delivery", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tracking_update", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin", sa.String(100), nullable=True),
        sa.Column("destination", sa.String(100), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("service_type", sa.String(100), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("shipping_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("raw_tracking_data", postgresql.JSONB(), server_default="{}"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("company_id", "tracking_number", name="uq_shipments_company_tracking"),
        comment="Sendungsverfolgung fuer Paketdienste (DHL, DPD, Hermes, UPS, GLS, FedEx, Deutsche Post)"
    )

    # Shipments Indexes
    op.create_index("ix_shipments_company_id", "shipments", ["company_id"])
    op.create_index("ix_shipments_company_status", "shipments", ["company_id", "status"])
    op.create_index("ix_shipments_company_carrier", "shipments", ["company_id", "carrier"])
    op.create_index("ix_shipments_company_direction", "shipments", ["company_id", "direction"])
    op.create_index("ix_shipments_tracking", "shipments", ["tracking_number"])
    op.create_index("ix_shipments_entity", "shipments", ["entity_id"])
    op.create_index("ix_shipments_document", "shipments", ["document_id"])
    op.create_index("ix_shipments_estimated_delivery", "shipments", ["estimated_delivery"])
    op.create_index("ix_shipments_created", "shipments", ["created_at"])

    # Shipment Events Table
    op.create_table(
        "shipment_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("shipment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country_code", sa.String(3), nullable=True),
        sa.Column("raw_status", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("shipment_id", "timestamp", name="uq_shipment_events_shipment_timestamp"),
        comment="Tracking-Events fuer Sendungen"
    )

    # Shipment Events Indexes
    op.create_index("ix_shipment_events_shipment", "shipment_events", ["shipment_id"])
    op.create_index("ix_shipment_events_timestamp", "shipment_events", ["timestamp"])
    op.create_index("ix_shipment_events_status", "shipment_events", ["status"])

    # RLS Policies (PostgreSQL only)
    op.execute("""
        DO $$
        BEGIN
            -- Enable RLS on shipments
            ALTER TABLE shipments ENABLE ROW LEVEL SECURITY;

            -- Policy: Users can only see shipments from their company
            CREATE POLICY shipments_company_isolation ON shipments
                USING (company_id = current_setting('app.current_company_id', true)::uuid)
                WITH CHECK (company_id = current_setting('app.current_company_id', true)::uuid);

        EXCEPTION
            WHEN others THEN
                RAISE NOTICE 'RLS policy creation skipped: %', SQLERRM;
        END $$;
    """)


def downgrade() -> None:
    # Remove RLS
    op.execute("""
        DO $$
        BEGIN
            DROP POLICY IF EXISTS shipments_company_isolation ON shipments;
            ALTER TABLE shipments DISABLE ROW LEVEL SECURITY;
        EXCEPTION
            WHEN others THEN
                RAISE NOTICE 'RLS policy removal skipped: %', SQLERRM;
        END $$;
    """)

    # Drop indexes
    op.drop_index("ix_shipment_events_status", table_name="shipment_events")
    op.drop_index("ix_shipment_events_timestamp", table_name="shipment_events")
    op.drop_index("ix_shipment_events_shipment", table_name="shipment_events")

    op.drop_index("ix_shipments_created", table_name="shipments")
    op.drop_index("ix_shipments_estimated_delivery", table_name="shipments")
    op.drop_index("ix_shipments_document", table_name="shipments")
    op.drop_index("ix_shipments_entity", table_name="shipments")
    op.drop_index("ix_shipments_tracking", table_name="shipments")
    op.drop_index("ix_shipments_company_direction", table_name="shipments")
    op.drop_index("ix_shipments_company_carrier", table_name="shipments")
    op.drop_index("ix_shipments_company_status", table_name="shipments")
    op.drop_index("ix_shipments_company_id", table_name="shipments")

    # Drop tables
    op.drop_table("shipment_events")
    op.drop_table("shipments")
