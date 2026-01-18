"""Add skonto tracking and partial payment support.

Revision ID: 094_add_skonto_and_partial_payments
Revises: 093_add_invoice_tracking
Create Date: 2026-01-16

Features:
- Skonto-Felder zu invoice_tracking (Frühzahlerrabatt)
- PaymentTransaction Tabelle für Teilzahlungen
- Automatische Skonto-Berechnung
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add skonto fields and payment_transactions table."""

    # 1. Add Skonto fields to invoice_tracking
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "skonto_percentage",
            sa.Float(),
            nullable=True,
            comment="Skonto-Prozentsatz (z.B. 2.0 fuer 2%)"
        )
    )
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "skonto_days",
            sa.Integer(),
            nullable=True,
            comment="Tage nach Rechnungsdatum fuer Skonto-Berechtigung"
        )
    )
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "skonto_deadline",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Berechnetes Skonto-Ablaufdatum"
        )
    )
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "skonto_amount",
            sa.Float(),
            nullable=True,
            comment="Berechneter Skonto-Betrag in EUR"
        )
    )
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "skonto_used",
            sa.Boolean(),
            default=False,
            nullable=False,
            server_default="false",
            comment="True wenn Skonto bei Zahlung abgezogen wurde"
        )
    )
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "net_payment_days",
            sa.Integer(),
            nullable=True,
            comment="Zahlungsziel netto (z.B. 30 Tage)"
        )
    )

    # Add is_partial_payment flag if not exists
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "is_partial_payment",
            sa.Boolean(),
            default=False,
            nullable=False,
            server_default="false",
            comment="True wenn Teilzahlung erwartet/erfolgt"
        )
    )

    # Add outstanding_amount for easier queries
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "outstanding_amount",
            sa.Float(),
            nullable=True,
            comment="Ausstehender Betrag (amount - paid_amount)"
        )
    )

    # Index for skonto deadline queries (wichtig für Alerts)
    op.create_index(
        "ix_invoice_tracking_skonto_deadline",
        "invoice_tracking",
        ["skonto_deadline"],
        unique=False,
        postgresql_where=sa.text("skonto_deadline IS NOT NULL AND skonto_used = false")
    )

    # 2. Create payment_transactions table for partial payments
    op.create_table(
        "payment_transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Link to invoice
        sa.Column(
            "invoice_tracking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoice_tracking.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # Payment details
        sa.Column(
            "transaction_date",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "amount",
            sa.Float(),
            nullable=False,
            comment="Zahlungsbetrag in EUR"
        ),
        sa.Column(
            "payment_reference",
            sa.String(255),
            nullable=True,
            comment="Verwendungszweck/Referenz"
        ),
        # Payment method
        sa.Column(
            "payment_method",
            sa.String(50),
            nullable=False,
            default="bank_transfer",
            server_default="bank_transfer",
            comment="bank_transfer, credit_card, cash, sepa_direct_debit, paypal"
        ),
        # Bank transaction link (optional)
        sa.Column(
            "bank_transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bank_transactions.id", ondelete="SET NULL"),
            nullable=True,
            comment="Verknuepfung mit Bank-Transaktion"
        ),
        # Skonto tracking
        sa.Column(
            "skonto_deducted",
            sa.Float(),
            nullable=True,
            default=0.0,
            comment="Abgezogener Skonto-Betrag"
        ),
        # Reconciliation status
        sa.Column(
            "reconciliation_status",
            sa.String(20),
            nullable=False,
            default="pending",
            server_default="pending",
            comment="pending, matched, manual, failed"
        ),
        sa.Column(
            "reconciled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "reconciled_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Notes
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Interne Notizen"
        ),
        # Audit
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="Multi-Tenant Isolation"
        ),
    )

    # Indexes for payment_transactions
    op.create_index(
        "ix_payment_transactions_date",
        "payment_transactions",
        ["transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_payment_transactions_status",
        "payment_transactions",
        ["reconciliation_status"],
        unique=False,
    )

    # Add entity_id to invoice_tracking for direct entity link
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_entities.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
            comment="Verknuepfung mit BusinessEntity (Kunde/Lieferant)"
        )
    )

    # Add company_id to invoice_tracking for multi-tenant
    op.add_column(
        "invoice_tracking",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,  # nullable for existing data
            index=True,
            comment="Multi-Tenant Isolation"
        )
    )


def downgrade() -> None:
    """Remove skonto and partial payment support."""
    # Drop payment_transactions table
    op.drop_index("ix_payment_transactions_status", table_name="payment_transactions")
    op.drop_index("ix_payment_transactions_date", table_name="payment_transactions")
    op.drop_table("payment_transactions")

    # Drop columns from invoice_tracking
    op.drop_column("invoice_tracking", "company_id")
    op.drop_column("invoice_tracking", "entity_id")
    op.drop_index("ix_invoice_tracking_skonto_deadline", table_name="invoice_tracking")
    op.drop_column("invoice_tracking", "outstanding_amount")
    op.drop_column("invoice_tracking", "is_partial_payment")
    op.drop_column("invoice_tracking", "net_payment_days")
    op.drop_column("invoice_tracking", "skonto_used")
    op.drop_column("invoice_tracking", "skonto_amount")
    op.drop_column("invoice_tracking", "skonto_deadline")
    op.drop_column("invoice_tracking", "skonto_days")
    op.drop_column("invoice_tracking", "skonto_percentage")
