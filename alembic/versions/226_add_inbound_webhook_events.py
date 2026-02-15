"""add_inbound_webhook_events

Revision ID: 226
Revises: 225
Create Date: 2026-02-15

Phase 3.2: Inbound Webhook Receiver - DATEV + Carrier Provider Events.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "226"
down_revision = "225"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, comment="datev, dhl, dpd, ups, gls"),
        sa.Column(
            "config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("erp_connections.id", ondelete="SET NULL"),
            nullable=True,
            comment="ERP-Verbindung (fuer DATEV), nullable fuer Carrier-Provider",
        ),
        sa.Column("event_id", sa.String(255), nullable=False, comment="Externe Event-ID (Idempotenz)"),
        sa.Column("event_type", sa.String(100), nullable=False, comment="Provider-spezifischer Event-Typ"),
        sa.Column("action", sa.String(50), nullable=False, comment="create, update, delete, status_change"),
        sa.Column("payload_hash", sa.String(64), nullable=False, comment="SHA-256 Hash des Payloads"),
        sa.Column("payload_preview", postgresql.JSONB(), nullable=True, comment="Sanitized Preview (keine PII)"),
        sa.Column("external_ref", sa.String(255), nullable=True, comment="Tracking-Nr, Rechnungs-Nr, etc."),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("task_id", sa.String(100), nullable=True, comment="Celery Task-ID"),
        sa.Column("internal_event_type", sa.String(100), nullable=True, comment="EventType-Wert nach Mapping"),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id", name="uq_inbound_webhook_provider_event_id"),
        comment="Inbound webhook events from external providers (DATEV, carriers)",
    )

    # Indexes
    op.create_index("ix_inbound_webhook_events_config_id", "inbound_webhook_events", ["config_id"])
    op.create_index("ix_inbound_webhook_events_status", "inbound_webhook_events", ["status"])
    op.create_index("ix_inbound_webhook_events_external_ref", "inbound_webhook_events", ["external_ref"])
    op.create_index("ix_inbound_webhook_events_received_at", "inbound_webhook_events", ["received_at"])
    op.create_index("ix_inbound_webhook_provider_status", "inbound_webhook_events", ["provider", "status"])


def downgrade() -> None:
    op.drop_index("ix_inbound_webhook_provider_status", table_name="inbound_webhook_events")
    op.drop_index("ix_inbound_webhook_events_received_at", table_name="inbound_webhook_events")
    op.drop_index("ix_inbound_webhook_events_external_ref", table_name="inbound_webhook_events")
    op.drop_index("ix_inbound_webhook_events_status", table_name="inbound_webhook_events")
    op.drop_index("ix_inbound_webhook_events_config_id", table_name="inbound_webhook_events")
    op.drop_table("inbound_webhook_events")
