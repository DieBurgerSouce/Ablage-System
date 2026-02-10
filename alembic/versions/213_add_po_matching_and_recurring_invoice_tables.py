"""Add PO matching and recurring invoice tables

Revision ID: 213
Revises: 212
Create Date: 2026-02-10

4 neue Tabellen fuer Phase D Features:
- purchase_order_matches: 3-Way PO Matching
- match_discrepancies: Abweichungen im PO Match
- recurring_invoices: Wiederkehrende Rechnungen / Abo-Erkennung
- recurring_invoice_occurrences: Einzelne Abo-Instanzen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "213"
down_revision = "212"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Enums ---
    match_status = postgresql.ENUM(
        "pending", "partial", "full", "discrepancy", "rejected", "approved",
        name="match_status", create_type=False,
    )
    discrepancy_category = postgresql.ENUM(
        "amount", "quantity", "item", "date", "price",
        name="discrepancy_category", create_type=False,
    )
    discrepancy_severity = postgresql.ENUM(
        "info", "warning", "error", "critical",
        name="discrepancy_severity", create_type=False,
    )
    recurring_invoice_status = postgresql.ENUM(
        "active", "paused", "cancelled", "expired",
        name="recurring_invoice_status", create_type=False,
    )
    recurring_interval_type = postgresql.ENUM(
        "monthly", "quarterly", "half_yearly", "yearly",
        name="recurring_interval_type", create_type=False,
    )
    detection_method = postgresql.ENUM(
        "auto", "manual",
        name="detection_method", create_type=False,
    )
    occurrence_status = postgresql.ENUM(
        "expected", "matched", "missing", "late", "overpaid", "underpaid",
        name="occurrence_status", create_type=False,
    )
    occurrence_match_method = postgresql.ENUM(
        "auto", "manual",
        name="occurrence_match_method", create_type=False,
    )

    # Create all enum types
    match_status.create(op.get_bind(), checkfirst=True)
    discrepancy_category.create(op.get_bind(), checkfirst=True)
    discrepancy_severity.create(op.get_bind(), checkfirst=True)
    recurring_invoice_status.create(op.get_bind(), checkfirst=True)
    recurring_interval_type.create(op.get_bind(), checkfirst=True)
    detection_method.create(op.get_bind(), checkfirst=True)
    occurrence_status.create(op.get_bind(), checkfirst=True)
    occurrence_match_method.create(op.get_bind(), checkfirst=True)

    # --- purchase_order_matches ---
    op.create_table(
        "purchase_order_matches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivery_note_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_chain_id", sa.String(100), nullable=True),
        sa.Column("vendor_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=True),
        sa.Column("order_number", sa.String(100), nullable=True),
        sa.Column("order_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("po_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("dn_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("invoice_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("match_status", match_status, nullable=False, server_default="pending"),
        sa.Column("match_score", sa.Float, server_default="0.0"),
        sa.Column("auto_matched", sa.Boolean, server_default="false"),
        sa.Column("amount_tolerance_percent", sa.Float, server_default="2.0"),
        sa.Column("quantity_tolerance_percent", sa.Float, server_default="1.0"),
        sa.Column("line_items_comparison", postgresql.JSONB, server_default="[]"),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_purchase_order_matches_company_id", "purchase_order_matches", ["company_id"])
    op.create_index("ix_purchase_order_matches_purchase_order_id", "purchase_order_matches", ["purchase_order_id"])
    op.create_index("ix_purchase_order_matches_delivery_note_id", "purchase_order_matches", ["delivery_note_id"])
    op.create_index("ix_purchase_order_matches_invoice_id", "purchase_order_matches", ["invoice_id"])
    op.create_index("ix_purchase_order_matches_document_chain_id", "purchase_order_matches", ["document_chain_id"])
    op.create_index("ix_purchase_order_matches_vendor_entity_id", "purchase_order_matches", ["vendor_entity_id"])
    op.create_index("ix_purchase_order_matches_order_number", "purchase_order_matches", ["order_number"])
    op.create_index("ix_po_match_company_status", "purchase_order_matches", ["company_id", "match_status"])
    op.create_index("ix_po_match_vendor", "purchase_order_matches", ["company_id", "vendor_entity_id"])
    op.create_index("ix_po_match_order_number", "purchase_order_matches", ["company_id", "order_number"])
    op.create_index("ix_po_match_created", "purchase_order_matches", ["company_id", "created_at"])

    # --- match_discrepancies ---
    op.create_table(
        "match_discrepancies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchase_order_matches.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", discrepancy_category, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("expected_value", sa.String(500), nullable=True),
        sa.Column("actual_value", sa.String(500), nullable=True),
        sa.Column("expected_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("actual_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("deviation_percent", sa.Float, nullable=True),
        sa.Column("severity", discrepancy_severity, nullable=False, server_default="warning"),
        sa.Column("resolved", sa.Boolean, server_default="false"),
        sa.Column("resolved_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_match_discrepancies_match_id", "match_discrepancies", ["match_id"])
    op.create_index("ix_discrepancy_match_category", "match_discrepancies", ["match_id", "category"])
    op.create_index("ix_discrepancy_unresolved", "match_discrepancies", ["match_id", "resolved"])

    # --- recurring_invoices ---
    op.create_table(
        "recurring_invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vendor_entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("business_entities.id", ondelete="SET NULL"), nullable=True),
        sa.Column("vendor_name", sa.String(255), nullable=False),
        sa.Column("interval_type", recurring_interval_type, nullable=False, server_default="monthly"),
        sa.Column("interval_months", sa.Integer, nullable=False, server_default="1"),
        sa.Column("expected_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("tolerance_percent", sa.Float, server_default="5.0"),
        sa.Column("first_seen_date", sa.Date, nullable=True),
        sa.Column("last_seen_date", sa.Date, nullable=True),
        sa.Column("next_expected_date", sa.Date, nullable=True),
        sa.Column("cancellation_deadline", sa.Date, nullable=True),
        sa.Column("notice_period_days", sa.Integer, nullable=True),
        sa.Column("auto_renewal", sa.Boolean, server_default="true"),
        sa.Column("detection_confidence", sa.Float, server_default="0.0"),
        sa.Column("detection_method", detection_method, nullable=False, server_default="manual"),
        sa.Column("match_count", sa.Integer, server_default="0"),
        sa.Column("price_history", postgresql.JSONB, server_default="[]"),
        sa.Column("last_price_change_date", sa.Date, nullable=True),
        sa.Column("price_change_percent", sa.Float, nullable=True),
        sa.Column("status", recurring_invoice_status, nullable=False, server_default="active"),
        sa.Column("price_increase_alerted", sa.Boolean, server_default="false"),
        sa.Column("missing_invoice_alerted", sa.Boolean, server_default="false"),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("document_type", sa.String(100), nullable=True),
        sa.Column("reference_pattern", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint("interval_months > 0", name="ck_recurring_invoice_interval_positive"),
        sa.CheckConstraint("tolerance_percent >= 0", name="ck_recurring_invoice_tolerance_positive"),
    )
    op.create_index("ix_recurring_invoices_company_id", "recurring_invoices", ["company_id"])
    op.create_index("ix_recurring_invoices_vendor_entity_id", "recurring_invoices", ["vendor_entity_id"])
    op.create_index("ix_recurring_invoice_company_status", "recurring_invoices", ["company_id", "status"])
    op.create_index("ix_recurring_invoice_company_vendor", "recurring_invoices", ["company_id", "vendor_name"])
    op.create_index("ix_recurring_invoice_next_expected", "recurring_invoices", ["company_id", "next_expected_date"])

    # --- recurring_invoice_occurrences ---
    op.create_table(
        "recurring_invoice_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("recurring_invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recurring_invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("invoice_tracking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoice_tracking.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expected_date", sa.Date, nullable=False),
        sa.Column("actual_date", sa.Date, nullable=True),
        sa.Column("expected_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("amount_deviation", sa.Numeric(15, 2), nullable=True),
        sa.Column("status", occurrence_status, nullable=False, server_default="expected"),
        sa.Column("match_confidence", sa.Float, nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matched_by", occurrence_match_method, nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_recurring_invoice_occurrences_recurring_invoice_id", "recurring_invoice_occurrences", ["recurring_invoice_id"])
    op.create_index("ix_recurring_invoice_occurrences_document_id", "recurring_invoice_occurrences", ["document_id"])
    op.create_index("ix_occurrence_recurring_date", "recurring_invoice_occurrences", ["recurring_invoice_id", "expected_date"])
    op.create_index("ix_occurrence_status", "recurring_invoice_occurrences", ["recurring_invoice_id", "status"])
    op.create_index("ix_occurrence_document", "recurring_invoice_occurrences", ["document_id"])


def downgrade() -> None:
    op.drop_table("recurring_invoice_occurrences")
    op.drop_table("recurring_invoices")
    op.drop_table("match_discrepancies")
    op.drop_table("purchase_order_matches")

    # Drop enums
    for enum_name in [
        "occurrence_match_method",
        "occurrence_status",
        "detection_method",
        "recurring_interval_type",
        "recurring_invoice_status",
        "discrepancy_severity",
        "discrepancy_category",
        "match_status",
    ]:
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
