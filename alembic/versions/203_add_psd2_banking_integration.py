"""Add PSD2/FinTS banking integration tables.

Revision ID: 203_add_psd2_banking_integration
Revises: 202
Create Date: 2026-02-02

Phase 6: Multi-Bank Aggregation with PSD2 OAuth2 and FinTS PIN/TAN support.

New Tables:
- bank_connections: Multi-bank connections (PSD2, FinTS)
- connected_bank_accounts: Individual accounts within connections
- imported_transactions: Transactions from PSD2/FinTS
- transaction_split_allocations: Split payment allocations
- bank_sync_logs: Sync operation logs
- payment_initiations: PSD2 PISP requests
- reconciliation_rules: Auto-reconciliation configuration
- supported_banks: Catalog of supported German banks

SECURITY NOTES:
- All credentials are encrypted with AES-256-GCM
- Never log IBANs, account numbers, or balances
- PSD2 consent tokens have limited TTL
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "203"
down_revision = "202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add PSD2/FinTS banking integration tables."""

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
    # 1. SUPPORTED_BANKS - Catalog of supported German banks
    # =========================================================================
    op.create_table(
        "supported_banks",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        # Bank Identification
        sa.Column("bank_code", sa.String(8), nullable=False),
        sa.Column("bank_name", sa.String(255), nullable=False),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("country_code", sa.String(2), server_default="DE"),
        # Connection Capabilities
        sa.Column("supports_psd2", sa.Boolean, server_default="false"),
        sa.Column("supports_fints", sa.Boolean, server_default="false"),
        # PSD2 Configuration
        sa.Column("psd2_base_url", sa.String(500), nullable=True),
        sa.Column("psd2_sandbox_url", sa.String(500), nullable=True),
        sa.Column("aspsp_id", sa.String(100), nullable=True),
        # FinTS Configuration
        sa.Column("fints_url", sa.String(500), nullable=True),
        sa.Column("fints_version", sa.String(10), server_default="3.0"),
        # Features
        sa.Column("supports_balance", sa.Boolean, server_default="true"),
        sa.Column("supports_transactions", sa.Boolean, server_default="true"),
        sa.Column("supports_payment_initiation", sa.Boolean, server_default="false"),
        sa.Column("supports_batch_payment", sa.Boolean, server_default="false"),
        sa.Column("supports_direct_debit", sa.Boolean, server_default="false"),
        # TAN Methods (FinTS)
        sa.Column("available_tan_methods", json_type, nullable=True),
        # Logo/Branding
        sa.Column("logo_url", sa.String(500), nullable=True),
        sa.Column("primary_color", sa.String(7), nullable=True),
        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("maintenance_message", sa.Text, nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("bank_code", name="uq_supported_banks_bank_code"),
    )

    op.create_index("ix_supported_banks_active", "supported_banks", ["is_active"])
    op.create_index("ix_supported_banks_country", "supported_banks", ["country_code"])

    # =========================================================================
    # 2. BANK_CONNECTIONS - Multi-bank connections
    # =========================================================================
    op.create_table(
        "bank_connections",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=False),
        # Bank Identification
        sa.Column("bank_code", sa.String(8), nullable=False),
        sa.Column("bank_name", sa.String(255), nullable=False),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("country_code", sa.String(2), server_default="DE"),
        # Connection Type
        sa.Column("connection_type", sa.String(20), server_default="fints", nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        # FinTS Configuration (encrypted)
        sa.Column("fints_url", sa.String(500), nullable=True),
        sa.Column("fints_version", sa.String(10), server_default="3.0"),
        sa.Column("encrypted_credentials", sa.Text, nullable=True),
        sa.Column("selected_tan_method", sa.String(50), nullable=True),
        sa.Column("tan_media_name", sa.String(100), nullable=True),
        # PSD2 Configuration
        sa.Column("aspsp_id", sa.String(100), nullable=True),
        sa.Column("consent_id", sa.String(100), nullable=True),
        sa.Column("consent_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_status", sa.String(50), nullable=True),
        # PSD2 OAuth2 Tokens (encrypted)
        sa.Column("encrypted_access_token", sa.Text, nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text, nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        # Sync Configuration
        sa.Column("auto_sync_enabled", sa.Boolean, server_default="true"),
        sa.Column("sync_interval_hours", sa.Integer, server_default="4"),
        sa.Column("sync_from_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_status", sa.String(20), server_default="idle"),
        # Health Monitoring
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_healthy", sa.Boolean, server_default="true"),
        # Feature Flags
        sa.Column("supports_balance", sa.Boolean, server_default="true"),
        sa.Column("supports_transactions", sa.Boolean, server_default="true"),
        sa.Column("supports_payment_initiation", sa.Boolean, server_default="false"),
        sa.Column("supports_direct_debit", sa.Boolean, server_default="false"),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        # Foreign Keys
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_bank_connections_company_id", "bank_connections", ["company_id"])
    op.create_index("ix_bank_connections_status", "bank_connections", ["status"])
    op.create_index("ix_bank_connections_company_status", "bank_connections", ["company_id", "status"])
    op.create_index("ix_bank_connections_next_sync", "bank_connections", ["next_sync_at"])
    op.create_index("ix_bank_connections_consent_expires", "bank_connections", ["consent_expires_at"])

    # =========================================================================
    # 3. BANK_SYNC_LOGS - Sync operation logs (before connected_bank_accounts for FK)
    # =========================================================================
    op.create_table(
        "bank_sync_logs",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("connection_id", uuid_type, nullable=False),
        # Sync Details
        sa.Column("sync_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        # Results
        sa.Column("accounts_synced", sa.Integer, server_default="0"),
        sa.Column("transactions_imported", sa.Integer, server_default="0"),
        sa.Column("transactions_duplicates", sa.Integer, server_default="0"),
        sa.Column("auto_reconciled_count", sa.Integer, server_default="0"),
        # Period
        sa.Column("sync_from_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_to_date", sa.DateTime(timezone=True), nullable=True),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        # Error Tracking
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_details", json_type, nullable=True),
        # Trigger
        sa.Column("triggered_by", sa.String(30), nullable=True),
        sa.Column("triggered_by_user_id", uuid_type, nullable=True),
        # Foreign Keys
        sa.ForeignKeyConstraint(["connection_id"], ["bank_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_sync_logs_connection_started", "bank_sync_logs", ["connection_id", "started_at"])
    op.create_index("ix_sync_logs_status", "bank_sync_logs", ["status"])

    # =========================================================================
    # 4. CONNECTED_BANK_ACCOUNTS - Individual accounts within connections
    # =========================================================================
    op.create_table(
        "connected_bank_accounts",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("connection_id", uuid_type, nullable=False),
        # Account Identification (SECURITY: Sensitive)
        sa.Column("iban", sa.String(34), nullable=False),
        sa.Column("bic", sa.String(11), nullable=True),
        sa.Column("account_number", sa.String(20), nullable=True),
        # Account Details
        sa.Column("account_name", sa.String(255), nullable=True),
        sa.Column("account_type", sa.String(50), server_default="checking"),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("product_name", sa.String(255), nullable=True),
        # Balance
        sa.Column("current_balance", sa.Numeric(15, 2), nullable=True),
        sa.Column("available_balance", sa.Numeric(15, 2), nullable=True),
        sa.Column("credit_limit", sa.Numeric(15, 2), nullable=True),
        sa.Column("balance_updated_at", sa.DateTime(timezone=True), nullable=True),
        # Configuration
        sa.Column("is_primary", sa.Boolean, server_default="false"),
        sa.Column("auto_import", sa.Boolean, server_default="true"),
        sa.Column("auto_reconcile", sa.Boolean, server_default="true"),
        # Link to existing BankAccount
        sa.Column("legacy_bank_account_id", uuid_type, nullable=True),
        # Statistics
        sa.Column("transaction_count", sa.Integer, server_default="0"),
        sa.Column("last_transaction_date", sa.DateTime(timezone=True), nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        # Foreign Keys
        sa.ForeignKeyConstraint(["connection_id"], ["bank_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["legacy_bank_account_id"], ["bank_accounts.id"], ondelete="SET NULL"),
        # Unique Constraint
        sa.UniqueConstraint("connection_id", "iban", name="uq_connection_iban"),
    )

    op.create_index("ix_connected_accounts_connection", "connected_bank_accounts", ["connection_id"])
    op.create_index("ix_connected_accounts_iban", "connected_bank_accounts", ["iban"])

    # =========================================================================
    # 5. IMPORTED_TRANSACTIONS - Transactions from PSD2/FinTS
    # =========================================================================
    op.create_table(
        "imported_transactions",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("account_id", uuid_type, nullable=False),
        # Transaction Identification
        sa.Column("transaction_id", sa.String(100), nullable=True),
        sa.Column("entry_reference", sa.String(100), nullable=True),
        sa.Column("end_to_end_id", sa.String(35), nullable=True),
        # Dates
        sa.Column("booking_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value_date", sa.DateTime(timezone=True), nullable=False),
        # Amount
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        # Counterparty (SECURITY: PII)
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("counterparty_iban", sa.String(34), nullable=True),
        sa.Column("counterparty_bic", sa.String(11), nullable=True),
        # Reference
        sa.Column("reference_text", sa.Text, nullable=True),
        sa.Column("mandate_reference", sa.String(35), nullable=True),
        sa.Column("creditor_id", sa.String(35), nullable=True),
        # Categorization
        sa.Column("transaction_type", sa.String(50), nullable=True),
        sa.Column("booking_text", sa.String(100), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        # Reconciliation
        sa.Column("reconciliation_status", sa.String(30), server_default="pending"),
        sa.Column("reconciliation_match_type", sa.String(30), nullable=True),
        sa.Column("reconciliation_confidence", sa.Float, nullable=True),
        sa.Column("matched_invoice_id", uuid_type, nullable=True),
        sa.Column("matched_document_id", uuid_type, nullable=True),
        sa.Column("matched_entity_id", uuid_type, nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_by_id", uuid_type, nullable=True),
        # Partial Payment
        sa.Column("is_partial_payment", sa.Boolean, server_default="false"),
        sa.Column("allocated_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("remaining_amount", sa.Numeric(15, 2), nullable=True),
        # Raw Data
        sa.Column("raw_data", json_type, nullable=True),
        # Audit
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("sync_log_id", uuid_type, nullable=True),
        # Foreign Keys
        sa.ForeignKeyConstraint(["account_id"], ["connected_bank_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_invoice_id"], ["invoice_tracking.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reconciled_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sync_log_id"], ["bank_sync_logs.id"], ondelete="SET NULL"),
        # Unique Constraint (deduplication)
        sa.UniqueConstraint("account_id", "transaction_id", "booking_date", "amount", name="uq_imported_tx_dedup"),
    )

    op.create_index("ix_imported_tx_account_date", "imported_transactions", ["account_id", "booking_date"])
    op.create_index("ix_imported_tx_reconciliation", "imported_transactions", ["reconciliation_status"])
    op.create_index("ix_imported_tx_transaction_id", "imported_transactions", ["transaction_id"])
    op.create_index("ix_imported_tx_counterparty_iban", "imported_transactions", ["counterparty_iban"])

    # =========================================================================
    # 6. TRANSACTION_SPLIT_ALLOCATIONS - Split payment allocations
    # =========================================================================
    op.create_table(
        "transaction_split_allocations",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("transaction_id", uuid_type, nullable=False),
        sa.Column("invoice_id", uuid_type, nullable=False),
        # Allocation
        sa.Column("allocated_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("allocation_reason", sa.String(255), nullable=True),
        # Confidence
        sa.Column("match_confidence", sa.Float, nullable=True),
        sa.Column("match_method", sa.String(50), nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        # Foreign Keys
        sa.ForeignKeyConstraint(["transaction_id"], ["imported_transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice_tracking.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_split_allocation_transaction", "transaction_split_allocations", ["transaction_id"])
    op.create_index("ix_split_allocation_invoice", "transaction_split_allocations", ["invoice_id"])

    # =========================================================================
    # 7. PAYMENT_INITIATIONS - PSD2 PISP requests
    # =========================================================================
    op.create_table(
        "payment_initiations",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=False),
        sa.Column("connection_id", uuid_type, nullable=True),
        sa.Column("account_id", uuid_type, nullable=True),
        # Payment Type
        sa.Column("payment_type", sa.String(30), nullable=False),
        # Debtor (from)
        sa.Column("debtor_iban", sa.String(34), nullable=False),
        sa.Column("debtor_name", sa.String(140), nullable=True),
        # Creditor (to) - SECURITY: PII
        sa.Column("creditor_name", sa.String(140), nullable=False),
        sa.Column("creditor_iban", sa.String(34), nullable=False),
        sa.Column("creditor_bic", sa.String(11), nullable=True),
        # Amount
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),
        # Reference
        sa.Column("reference", sa.String(140), nullable=True),
        sa.Column("end_to_end_id", sa.String(35), nullable=True),
        # Execution
        sa.Column("requested_execution_date", sa.DateTime(timezone=True), nullable=True),
        # Linked Documents
        sa.Column("invoice_id", uuid_type, nullable=True),
        sa.Column("document_id", uuid_type, nullable=True),
        # Status
        sa.Column("status", sa.String(30), server_default="draft"),
        # PSD2 Response
        sa.Column("psd2_payment_id", sa.String(100), nullable=True),
        sa.Column("psd2_status", sa.String(50), nullable=True),
        sa.Column("sca_redirect_url", sa.Text, nullable=True),
        sa.Column("sca_status", sa.String(30), nullable=True),
        # TAN (FinTS)
        sa.Column("tan_required", sa.Boolean, server_default="false"),
        sa.Column("tan_challenge", sa.Text, nullable=True),
        sa.Column("tan_method", sa.String(50), nullable=True),
        # Approval Workflow
        sa.Column("requires_approval", sa.Boolean, server_default="false"),
        sa.Column("approved_by_id", uuid_type, nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        # Execution Result
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("bank_reference", sa.String(100), nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        # Foreign Keys
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["bank_connections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["account_id"], ["connected_bank_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoice_tracking.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_payment_init_company_status", "payment_initiations", ["company_id", "status"])
    op.create_index("ix_payment_init_execution_date", "payment_initiations", ["requested_execution_date"])

    # =========================================================================
    # 8. RECONCILIATION_RULES - Auto-reconciliation configuration
    # =========================================================================
    op.create_table(
        "reconciliation_rules",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("company_id", uuid_type, nullable=False),
        # Rule Definition
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("priority", sa.Integer, server_default="100"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        # Matching Conditions (JSON)
        sa.Column("conditions", json_type, nullable=False),
        # Action
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("auto_approve_threshold", sa.Float, server_default="0.95"),
        # Target Entity
        sa.Column("default_entity_id", uuid_type, nullable=True),
        # Statistics
        sa.Column("times_matched", sa.Integer, server_default="0"),
        sa.Column("last_matched_at", sa.DateTime(timezone=True), nullable=True),
        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        # Foreign Keys
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["default_entity_id"], ["business_entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_recon_rules_company_priority", "reconciliation_rules", ["company_id", "priority"])
    op.create_index("ix_recon_rules_active", "reconciliation_rules", ["is_active"])

    # =========================================================================
    # 9. SEED SUPPORTED BANKS (German banks)
    # =========================================================================
    supported_banks_table = sa.table(
        "supported_banks",
        sa.column("bank_code", sa.String),
        sa.column("bank_name", sa.String),
        sa.column("bic", sa.String),
        sa.column("supports_psd2", sa.Boolean),
        sa.column("supports_fints", sa.Boolean),
        sa.column("fints_url", sa.String),
        sa.column("supports_payment_initiation", sa.Boolean),
        sa.column("is_active", sa.Boolean),
    )

    op.bulk_insert(
        supported_banks_table,
        [
            # Sparkasse (FinTS)
            {
                "bank_code": "10050000",
                "bank_name": "Berliner Sparkasse",
                "bic": "BELADEBEXXX",
                "supports_psd2": False,
                "supports_fints": True,
                "fints_url": "https://banking.berliner-sparkasse.de/fints30",
                "supports_payment_initiation": True,
                "is_active": True,
            },
            {
                "bank_code": "50050201",
                "bank_name": "Frankfurter Sparkasse",
                "bic": "HELADEF1822",
                "supports_psd2": False,
                "supports_fints": True,
                "fints_url": "https://banking.frankfurter-sparkasse.de/fints30",
                "supports_payment_initiation": True,
                "is_active": True,
            },
            # Volksbank (FinTS)
            {
                "bank_code": "10090000",
                "bank_name": "Berliner Volksbank",
                "bic": "BEVODEBB",
                "supports_psd2": False,
                "supports_fints": True,
                "fints_url": "https://fints.bvb.de/fints",
                "supports_payment_initiation": True,
                "is_active": True,
            },
            # Deutsche Bank (PSD2)
            {
                "bank_code": "10070000",
                "bank_name": "Deutsche Bank",
                "bic": "DEUTDEFF",
                "supports_psd2": True,
                "supports_fints": True,
                "fints_url": "https://fints.deutsche-bank.de/fints",
                "supports_payment_initiation": True,
                "is_active": True,
            },
            # Commerzbank (PSD2)
            {
                "bank_code": "10040000",
                "bank_name": "Commerzbank",
                "bic": "COBADEFF",
                "supports_psd2": True,
                "supports_fints": True,
                "fints_url": "https://fints.commerzbank.de/fints",
                "supports_payment_initiation": True,
                "is_active": True,
            },
            # DKB (FinTS)
            {
                "bank_code": "12030000",
                "bank_name": "DKB Deutsche Kreditbank",
                "bic": "BYLADEM1001",
                "supports_psd2": False,
                "supports_fints": True,
                "fints_url": "https://banking-dkb.s-fints-pt-dkb.de/fints30",
                "supports_payment_initiation": True,
                "is_active": True,
            },
            # ING (PSD2)
            {
                "bank_code": "50010517",
                "bank_name": "ING-DiBa",
                "bic": "INGDDEFF",
                "supports_psd2": True,
                "supports_fints": True,
                "fints_url": "https://fints.ing-diba.de/fints",
                "supports_payment_initiation": True,
                "is_active": True,
            },
            # N26 (PSD2 only)
            {
                "bank_code": "10011001",
                "bank_name": "N26 Bank",
                "bic": "NTSBDEB1",
                "supports_psd2": True,
                "supports_fints": False,
                "fints_url": None,
                "supports_payment_initiation": False,
                "is_active": True,
            },
        ],
    )


def downgrade() -> None:
    """Remove PSD2/FinTS banking integration tables."""

    # Drop tables in reverse order (respecting FK dependencies)
    op.drop_table("reconciliation_rules")
    op.drop_table("payment_initiations")
    op.drop_table("transaction_split_allocations")
    op.drop_table("imported_transactions")
    op.drop_table("connected_bank_accounts")
    op.drop_table("bank_sync_logs")
    op.drop_table("bank_connections")
    op.drop_table("supported_banks")
