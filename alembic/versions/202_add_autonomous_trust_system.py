"""Add autonomous trust system tables.

Revision ID: 202_add_autonomous_trust_system
Revises: 201_add_odoo_webhooks
Create Date: 2026-02-02

Multi-Level Trust System fuer autonome KI-Aktionen:
- autonomous_trust_config: Trust-Level Konfiguration pro Company
- autonomous_proposal_queue: Queue fuer verzoegerte Auto-Akzeptanz
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "202"
down_revision = "201_add_odoo_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add autonomous trust system tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
        uuid_default = sa.text("gen_random_uuid()")
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON
        uuid_default = None

    # =========================================================================
    # 1. AUTONOMOUS_TRUST_CONFIG - Trust-Level pro Company
    # =========================================================================
    op.create_table(
        "autonomous_trust_config",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=False),

        # Trust Level
        sa.Column(
            "trust_level",
            sa.String(50),
            nullable=False,
            server_default="assistance",
            comment="Trust-Level: assistance, auto_accept, confidence, autonomous"
        ),

        # Optional: Spezifisch fuer Dokumenttyp
        sa.Column(
            "document_type",
            sa.String(50),
            nullable=True,
            comment="Optional: Spezifisches Level fuer diesen Dokumenttyp"
        ),

        # Konfiguration
        sa.Column("is_enabled", sa.Boolean, server_default=sa.text("true")),

        # Schwellenwerte (Override der Defaults)
        sa.Column(
            "immediate_threshold",
            sa.Float,
            nullable=True,
            comment="Ab hier sofortige Aktion (Override)"
        ),
        sa.Column(
            "delayed_threshold",
            sa.Float,
            nullable=True,
            comment="Ab hier verzoegerte Aktion (Override)"
        ),
        sa.Column(
            "delay_hours",
            sa.Integer,
            nullable=True,
            comment="Wartezeit in Stunden (Override)"
        ),

        # Metriken-Snapshot (wird periodisch aktualisiert)
        sa.Column(
            "metrics_snapshot",
            json_type,
            nullable=True,
            comment="Letzter Metriken-Snapshot (total_decisions, approval_rate, etc.)"
        ),
        sa.Column(
            "metrics_updated_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),

        # Trust-Level Aenderungshistorie
        sa.Column(
            "level_changed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Zeitpunkt der letzten Level-Aenderung"
        ),
        sa.Column(
            "change_reason",
            sa.Text,
            nullable=True,
            comment="Grund fuer letzte Level-Aenderung"
        ),

        # Audit
        sa.Column("updated_by_id", uuid_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("company_id", "document_type", name="uq_trust_config_company_doctype"),
    )

    op.create_index("ix_trust_config_company_id", "autonomous_trust_config", ["company_id"])
    op.create_index("ix_trust_config_trust_level", "autonomous_trust_config", ["trust_level"])

    # =========================================================================
    # 2. AUTONOMOUS_PROPOSAL_QUEUE - Queue fuer verzoegerte Aktionen
    # =========================================================================
    op.create_table(
        "autonomous_proposal_queue",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=False),

        # Proposal Details
        sa.Column(
            "proposal_type",
            sa.String(50),
            nullable=False,
            comment="Typ: file_document, approve_payment, send_dunning, update_master_data, assign_entity, classify_document"
        ),
        sa.Column(
            "target_id",
            uuid_type,
            nullable=False,
            comment="ID des Ziel-Objekts (Document, Invoice, Entity, etc.)"
        ),
        sa.Column(
            "proposed_value",
            json_type,
            nullable=False,
            comment="Vorgeschlagener Wert als JSON"
        ),

        # Confidence und Timing
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column(
            "delay_hours",
            sa.Integer,
            nullable=False,
            comment="Urspruengliche Verzoegerung in Stunden"
        ),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Geplante Ausfuehrungszeit"
        ),

        # Status
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="pending, approved, rejected, auto_accepted, expired, rolled_back, cancelled"
        ),

        # Ausfuehrung
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Zeitpunkt der Ausfuehrung"
        ),
        sa.Column(
            "executed_by",
            sa.String(100),
            nullable=True,
            comment="User-ID oder 'system' bei Auto-Accept"
        ),

        # Rollback
        sa.Column(
            "rollback_until",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Bis wann Rollback moeglich ist"
        ),

        # Referenzen
        sa.Column(
            "ai_decision_id",
            uuid_type,
            nullable=True,
            comment="Referenz zur urspruenglichen AI-Decision"
        ),
        sa.Column(
            "reasoning",
            sa.Text,
            nullable=True,
            comment="Begruendung des Vorschlags"
        ),
        sa.Column(
            "metadata",
            json_type,
            nullable=True,
            comment="Zusaetzliche Metadaten"
        ),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_decision_id"], ["ai_decisions.id"], ondelete="SET NULL"),
    )

    # Indizes fuer haeufige Abfragen
    op.create_index("ix_proposal_queue_company_id", "autonomous_proposal_queue", ["company_id"])
    op.create_index("ix_proposal_queue_status", "autonomous_proposal_queue", ["status"])
    op.create_index("ix_proposal_queue_scheduled_at", "autonomous_proposal_queue", ["scheduled_at"])
    op.create_index("ix_proposal_queue_proposal_type", "autonomous_proposal_queue", ["proposal_type"])
    op.create_index("ix_proposal_queue_target_id", "autonomous_proposal_queue", ["target_id"])

    # Partial Index fuer pending Proposals
    if is_postgres:
        op.create_index(
            "ix_proposal_queue_pending",
            "autonomous_proposal_queue",
            ["scheduled_at", "company_id"],
            postgresql_where=sa.text("status = 'pending'"),
        )

    # =========================================================================
    # 3. DEFAULT TRUST LEVELS einfuegen (Global Defaults)
    # =========================================================================
    # Keine Default-Inserts - Trust-Level werden per Company konfiguriert


def downgrade() -> None:
    """Remove autonomous trust system tables."""
    op.drop_table("autonomous_proposal_queue")
    op.drop_table("autonomous_trust_config")
