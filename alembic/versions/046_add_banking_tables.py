"""Add banking integration tables.

Revision ID: 046_add_banking_tables
Revises: 045_add_einvoice_support
Create Date: 2025-12-17

Banking-Integration fuer Ablage-System:
- bank_accounts: Bankkonten (IBAN, Name, FinTS-Credentials optional)
- bank_imports: Import-Historie (MT940, CAMT.053, CSV)
- bank_transactions: Kontobewegungen mit Reconciliation-Status
- payment_orders: SEPA-Zahlungsauftraege
- payment_batches: Sammelzahlungen
- dunning_records: Mahnwesen
- cash_flow_entries: Cash-Flow-Prognosen
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add banking integration tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. BANK_ACCOUNTS - Bankkonten
    # =========================================================================
    op.create_table(
        "bank_accounts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=False),

        # Konto-Identifikation
        sa.Column("account_name", sa.String(255), nullable=False),
        sa.Column("iban", sa.String(34), nullable=False),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("bank_name", sa.String(255), nullable=True),
        sa.Column("account_holder", sa.String(255), nullable=True),
        sa.Column("account_type", sa.String(50), default="checking"),

        # FinTS (optional)
        sa.Column("blz", sa.String(8), nullable=True),
        sa.Column("fints_url", sa.String(500), nullable=True),
        sa.Column("fints_version", sa.String(10), default="3.0"),
        sa.Column("login_id_encrypted", sa.String(500), nullable=True),
        sa.Column("pin_hash", sa.String(255), nullable=True),

        # TAN-Konfiguration
        sa.Column("tan_method", sa.String(50), nullable=True),
        sa.Column("tan_media", sa.String(100), nullable=True),
        sa.Column("tan_mechanism_id", sa.String(20), nullable=True),

        # Sync-Konfiguration
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_from_date", sa.Date, nullable=True),
        sa.Column("auto_sync_enabled", sa.Boolean, default=False),
        sa.Column("sync_interval_hours", sa.Integer, default=24),

        # Saldo
        sa.Column("current_balance", sa.Numeric(15, 2), nullable=True),
        sa.Column("balance_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("currency", sa.String(3), default="EUR"),

        # Status
        sa.Column("is_active", sa.Boolean, default=True),
        sa.Column("connection_status", sa.String(50), default="manual"),
        sa.Column("last_error", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_bank_accounts_user_id", "bank_accounts", ["user_id"])
    op.create_index("ix_bank_accounts_iban", "bank_accounts", ["iban"])
    op.create_index("ix_bank_accounts_is_active", "bank_accounts", ["is_active"])
    op.create_index("ix_bank_accounts_deleted_at", "bank_accounts", ["deleted_at"])

    # =========================================================================
    # 2. BANK_IMPORTS - Import-Historie
    # =========================================================================
    op.create_table(
        "bank_imports",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("bank_account_id", uuid_type, nullable=True),

        # Import-Details
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),

        # Format
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("format_variant", sa.String(100), nullable=True),

        # Ergebnis
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("transaction_count", sa.Integer, default=0),
        sa.Column("duplicate_count", sa.Integer, default=0),
        sa.Column("error_count", sa.Integer, default=0),
        sa.Column("errors", json_type, default=list),

        # Zeitraum
        sa.Column("date_from", sa.Date, nullable=True),
        sa.Column("date_to", sa.Date, nullable=True),

        # Audit
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processing_duration_ms", sa.Integer, nullable=True),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_bank_imports_user_id", "bank_imports", ["user_id"])
    op.create_index("ix_bank_imports_bank_account_id", "bank_imports", ["bank_account_id"])
    op.create_index("ix_bank_imports_format", "bank_imports", ["format"])
    op.create_index("ix_bank_imports_imported_at", "bank_imports", ["imported_at"])
    op.create_index("ix_bank_imports_file_hash", "bank_imports", ["file_hash"])

    # =========================================================================
    # 3. BANK_TRANSACTIONS - Kontobewegungen
    # =========================================================================
    op.create_table(
        "bank_transactions",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("bank_account_id", uuid_type, nullable=False),
        sa.Column("import_id", uuid_type, nullable=True),

        # Transaktions-ID
        sa.Column("transaction_id", sa.String(100), nullable=True),
        sa.Column("booking_date", sa.Date, nullable=False),
        sa.Column("value_date", sa.Date, nullable=False),

        # Betrag
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), default="EUR"),

        # Gegenpartei
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("counterparty_iban", sa.String(34), nullable=True),
        sa.Column("counterparty_bic", sa.String(11), nullable=True),
        sa.Column("counterparty_bank_name", sa.String(255), nullable=True),

        # Verwendungszweck
        sa.Column("reference_text", sa.Text, nullable=True),
        sa.Column("end_to_end_id", sa.String(35), nullable=True),
        sa.Column("mandate_id", sa.String(35), nullable=True),
        sa.Column("creditor_id", sa.String(35), nullable=True),

        # Kategorisierung
        sa.Column("transaction_type", sa.String(50), nullable=True),
        sa.Column("booking_text", sa.String(100), nullable=True),
        sa.Column("prima_nota", sa.String(20), nullable=True),

        # Geparste Referenzen
        sa.Column("parsed_invoice_numbers", json_type, default=list),
        sa.Column("parsed_customer_numbers", json_type, default=list),
        sa.Column("parsed_references", json_type, default=list),

        # Reconciliation
        sa.Column("reconciliation_status", sa.String(50), default="unmatched"),
        sa.Column("matched_document_id", uuid_type, nullable=True),
        sa.Column("matched_invoice_number", sa.String(100), nullable=True),
        sa.Column("match_confidence", sa.Float, nullable=True),
        sa.Column("match_method", sa.String(50), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matched_by_id", uuid_type, nullable=True),

        # Teilzahlungen
        sa.Column("allocated_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("remaining_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("is_partial_payment", sa.Boolean, default=False),
        sa.Column("parent_transaction_id", uuid_type, nullable=True),

        # Rohdaten
        sa.Column("raw_data", json_type, nullable=True),

        # Audit
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["import_id"], ["bank_imports.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_transaction_id"], ["bank_transactions.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_bank_transactions_account_id", "bank_transactions", ["bank_account_id"])
    op.create_index("ix_bank_transactions_booking_date", "bank_transactions", ["booking_date"])
    op.create_index("ix_bank_transactions_amount", "bank_transactions", ["amount"])
    op.create_index("ix_bank_transactions_counterparty_iban", "bank_transactions", ["counterparty_iban"])
    op.create_index("ix_bank_transactions_reconciliation", "bank_transactions", ["reconciliation_status"])
    op.create_index("ix_bank_transactions_matched_doc", "bank_transactions", ["matched_document_id"])
    op.create_index("ix_bank_transactions_import_id", "bank_transactions", ["import_id"])
    op.create_index(
        "ix_bank_transactions_unique",
        "bank_transactions",
        ["bank_account_id", "transaction_id", "booking_date", "amount"],
        unique=True
    )

    # =========================================================================
    # 4. PAYMENT_BATCHES - Sammelzahlungen (vor payment_orders wegen FK)
    # =========================================================================
    op.create_table(
        "payment_batches",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("bank_account_id", uuid_type, nullable=False),

        # Batch-Details
        sa.Column("batch_name", sa.String(255), nullable=True),
        sa.Column("batch_type", sa.String(50), nullable=False),
        sa.Column("payment_count", sa.Integer, default=0),
        sa.Column("total_amount", sa.Numeric(15, 2), default=0),
        sa.Column("currency", sa.String(3), default="EUR"),

        # Ausfuehrung
        sa.Column("requested_execution_date", sa.Date, nullable=True),

        # Status
        sa.Column("status", sa.String(50), default="draft"),

        # TAN
        sa.Column("tan_required", sa.Boolean, default=False),
        sa.Column("tan_challenge", sa.Text, nullable=True),
        sa.Column("tan_challenge_data", sa.LargeBinary, nullable=True),

        # Freigabe
        sa.Column("approved_by_id", uuid_type, nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),

        # SEPA XML
        sa.Column("sepa_xml", sa.Text, nullable=True),
        sa.Column("sepa_message_id", sa.String(35), nullable=True),

        # Ergebnis
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("successful_count", sa.Integer, default=0),
        sa.Column("failed_count", sa.Integer, default=0),

        # Fehler
        sa.Column("last_error", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_payment_batches_user_id", "payment_batches", ["user_id"])
    op.create_index("ix_payment_batches_status", "payment_batches", ["status"])
    op.create_index("ix_payment_batches_created_at", "payment_batches", ["created_at"])

    # =========================================================================
    # 5. PAYMENT_ORDERS - SEPA-Zahlungsauftraege
    # =========================================================================
    op.create_table(
        "payment_orders",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("bank_account_id", uuid_type, nullable=False),

        # Verknuepfte Rechnung
        sa.Column("document_id", uuid_type, nullable=True),
        sa.Column("invoice_number", sa.String(100), nullable=True),

        # Zahlungstyp
        sa.Column("payment_type", sa.String(50), nullable=False),
        sa.Column("sepa_type", sa.String(50), nullable=True),

        # Empfaenger
        sa.Column("beneficiary_name", sa.String(140), nullable=False),
        sa.Column("beneficiary_iban", sa.String(34), nullable=False),
        sa.Column("beneficiary_bic", sa.String(11), nullable=True),

        # Betrag
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), default="EUR"),

        # Zahlungsdetails
        sa.Column("reference", sa.Text, nullable=True),
        sa.Column("end_to_end_id", sa.String(35), nullable=True),
        sa.Column("execution_date", sa.Date, nullable=True),

        # Lastschrift
        sa.Column("mandate_id", sa.String(35), nullable=True),
        sa.Column("mandate_date", sa.Date, nullable=True),
        sa.Column("sequence_type", sa.String(10), nullable=True),
        sa.Column("creditor_id", sa.String(35), nullable=True),

        # Batch
        sa.Column("batch_id", uuid_type, nullable=True),
        sa.Column("batch_sequence", sa.Integer, nullable=True),

        # Status
        sa.Column("status", sa.String(50), default="draft"),

        # TAN
        sa.Column("tan_required", sa.Boolean, default=False),
        sa.Column("tan_challenge", sa.Text, nullable=True),
        sa.Column("tan_challenge_data", sa.LargeBinary, nullable=True),
        sa.Column("tan_entered_at", sa.DateTime(timezone=True), nullable=True),

        # Freigabe
        sa.Column("approved_by_id", uuid_type, nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),

        # Uebermittlung
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bank_reference", sa.String(100), nullable=True),

        # Fehler
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, default=0),

        # Skonto
        sa.Column("uses_skonto", sa.Boolean, default=False),
        sa.Column("skonto_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("original_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("skonto_deadline", sa.Date, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["batch_id"], ["payment_batches.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_payment_orders_user_id", "payment_orders", ["user_id"])
    op.create_index("ix_payment_orders_bank_account", "payment_orders", ["bank_account_id"])
    op.create_index("ix_payment_orders_status", "payment_orders", ["status"])
    op.create_index("ix_payment_orders_document", "payment_orders", ["document_id"])
    op.create_index("ix_payment_orders_execution_date", "payment_orders", ["execution_date"])
    op.create_index("ix_payment_orders_batch", "payment_orders", ["batch_id"])

    # =========================================================================
    # 6. DUNNING_RECORDS - Mahnwesen
    # =========================================================================
    op.create_table(
        "dunning_records",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("document_id", uuid_type, nullable=False),

        # Rechnungsreferenz
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("invoice_date", sa.Date, nullable=True),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("gross_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("outstanding_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency", sa.String(3), default="EUR"),

        # Geschaeftspartner
        sa.Column("business_entity_id", uuid_type, nullable=True),
        sa.Column("debtor_name", sa.String(255), nullable=True),
        sa.Column("debtor_email", sa.String(255), nullable=True),

        # Mahnstufe
        sa.Column("dunning_level", sa.Integer, default=0),

        # Gebuehren
        sa.Column("reminder_fee", sa.Numeric(10, 2), default=0),
        sa.Column("late_interest_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("accrued_interest", sa.Numeric(10, 2), default=0),
        sa.Column("total_outstanding", sa.Numeric(15, 2), nullable=True),

        # Timeline
        sa.Column("first_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("second_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_reminder_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_action_at", sa.DateTime(timezone=True), nullable=True),

        # Status
        sa.Column("status", sa.String(50), default="pending"),

        # Loesung
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", uuid_type, nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),

        # Teilzahlungen
        sa.Column("partial_payment_ids", json_type, default=list),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_dunning_records_user_id", "dunning_records", ["user_id"])
    op.create_index("ix_dunning_records_document", "dunning_records", ["document_id"])
    op.create_index("ix_dunning_records_status", "dunning_records", ["status"])
    op.create_index("ix_dunning_records_due_date", "dunning_records", ["due_date"])
    op.create_index("ix_dunning_records_next_action", "dunning_records", ["next_action_at"])
    op.create_index("ix_dunning_records_level", "dunning_records", ["dunning_level"])

    # =========================================================================
    # 7. CASH_FLOW_ENTRIES - Cash-Flow-Prognosen
    # =========================================================================
    op.create_table(
        "cash_flow_entries",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=False),
        sa.Column("bank_account_id", uuid_type, nullable=True),

        # Eintragstyp
        sa.Column("entry_type", sa.String(50), nullable=False),
        sa.Column("direction", sa.String(10), nullable=False),

        # Referenzen
        sa.Column("document_id", uuid_type, nullable=True),
        sa.Column("payment_order_id", uuid_type, nullable=True),
        sa.Column("transaction_id", uuid_type, nullable=True),

        # Datum
        sa.Column("expected_date", sa.Date, nullable=False),
        sa.Column("actual_date", sa.Date, nullable=True),

        # Betrag
        sa.Column("expected_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("actual_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("currency", sa.String(3), default="EUR"),

        # Wahrscheinlichkeit
        sa.Column("probability", sa.Float, default=1.0),

        # Beschreibung
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),

        # Status
        sa.Column("status", sa.String(50), default="expected"),

        # Gegenpartei
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("business_entity_id", uuid_type, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["bank_account_id"], ["bank_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["payment_order_id"], ["payment_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["transaction_id"], ["bank_transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["business_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_cash_flow_user_id", "cash_flow_entries", ["user_id"])
    op.create_index("ix_cash_flow_expected_date", "cash_flow_entries", ["expected_date"])
    op.create_index("ix_cash_flow_status", "cash_flow_entries", ["status"])
    op.create_index("ix_cash_flow_document", "cash_flow_entries", ["document_id"])
    op.create_index("ix_cash_flow_entry_type", "cash_flow_entries", ["entry_type"])
    op.create_index("ix_cash_flow_direction", "cash_flow_entries", ["direction"])


def downgrade() -> None:
    """Remove banking integration tables."""

    # Drop in reverse order of creation (due to foreign keys)

    # 7. Cash Flow
    op.drop_index("ix_cash_flow_direction", table_name="cash_flow_entries")
    op.drop_index("ix_cash_flow_entry_type", table_name="cash_flow_entries")
    op.drop_index("ix_cash_flow_document", table_name="cash_flow_entries")
    op.drop_index("ix_cash_flow_status", table_name="cash_flow_entries")
    op.drop_index("ix_cash_flow_expected_date", table_name="cash_flow_entries")
    op.drop_index("ix_cash_flow_user_id", table_name="cash_flow_entries")
    op.drop_table("cash_flow_entries")

    # 6. Dunning
    op.drop_index("ix_dunning_records_level", table_name="dunning_records")
    op.drop_index("ix_dunning_records_next_action", table_name="dunning_records")
    op.drop_index("ix_dunning_records_due_date", table_name="dunning_records")
    op.drop_index("ix_dunning_records_status", table_name="dunning_records")
    op.drop_index("ix_dunning_records_document", table_name="dunning_records")
    op.drop_index("ix_dunning_records_user_id", table_name="dunning_records")
    op.drop_table("dunning_records")

    # 5. Payment Orders
    op.drop_index("ix_payment_orders_batch", table_name="payment_orders")
    op.drop_index("ix_payment_orders_execution_date", table_name="payment_orders")
    op.drop_index("ix_payment_orders_document", table_name="payment_orders")
    op.drop_index("ix_payment_orders_status", table_name="payment_orders")
    op.drop_index("ix_payment_orders_bank_account", table_name="payment_orders")
    op.drop_index("ix_payment_orders_user_id", table_name="payment_orders")
    op.drop_table("payment_orders")

    # 4. Payment Batches
    op.drop_index("ix_payment_batches_created_at", table_name="payment_batches")
    op.drop_index("ix_payment_batches_status", table_name="payment_batches")
    op.drop_index("ix_payment_batches_user_id", table_name="payment_batches")
    op.drop_table("payment_batches")

    # 3. Bank Transactions
    op.drop_index("ix_bank_transactions_unique", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_import_id", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_matched_doc", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_reconciliation", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_counterparty_iban", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_amount", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_booking_date", table_name="bank_transactions")
    op.drop_index("ix_bank_transactions_account_id", table_name="bank_transactions")
    op.drop_table("bank_transactions")

    # 2. Bank Imports
    op.drop_index("ix_bank_imports_file_hash", table_name="bank_imports")
    op.drop_index("ix_bank_imports_imported_at", table_name="bank_imports")
    op.drop_index("ix_bank_imports_format", table_name="bank_imports")
    op.drop_index("ix_bank_imports_bank_account_id", table_name="bank_imports")
    op.drop_index("ix_bank_imports_user_id", table_name="bank_imports")
    op.drop_table("bank_imports")

    # 1. Bank Accounts
    op.drop_index("ix_bank_accounts_deleted_at", table_name="bank_accounts")
    op.drop_index("ix_bank_accounts_is_active", table_name="bank_accounts")
    op.drop_index("ix_bank_accounts_iban", table_name="bank_accounts")
    op.drop_index("ix_bank_accounts_user_id", table_name="bank_accounts")
    op.drop_table("bank_accounts")
