"""Add Kasse-Modul tables (Kassenbuch + Spesenabrechnung).

Revision ID: 058_add_cash_module
Revises: 057_add_multi_company_support
Create Date: 2024-12-29

Kasse-Modul fuer Ablage-System:
- cash_registers: Kassen/Bargeldbestaende
- cash_entries: Kassenbuchungen (APPEND-ONLY! GoBD-konform)
- cash_categories: Ausgabenkategorien mit SKR03/SKR04 Mapping
- cash_counts: Zaehlprotokolle (Kassensturz)
- expense_reports: Spesenabrechnungen (Workflow)
- expense_items: Spesenpositionen

GoBD-Compliance:
- CashEntry ist APPEND-ONLY - KEINE Updates oder Deletes!
- Stornierung nur durch Gegenbuchung
- entry_date darf nicht in der Zukunft liegen
- entry_number fortlaufend pro Kasse/Jahr
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '058_add_cash_module'
down_revision = '057_add_multi_company_support'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Kasse-Modul tables."""

    # Check dialect for cross-database compatibility
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. CASH_CATEGORIES - Ausgabenkategorien (muss vor cash_entries existieren)
    # =========================================================================
    op.create_table(
        "cash_categories",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, nullable=True),  # NULL = System-Default

        # Identifikation
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), nullable=True),
        sa.Column("color", sa.String(7), nullable=True),

        # Hierarchie
        sa.Column("parent_id", uuid_type, nullable=True),
        sa.Column("level", sa.Integer, server_default="0"),
        sa.Column("path", sa.String(500), nullable=True),

        # Buchhaltung (SKR03/SKR04)
        sa.Column("skr03_account", sa.String(10), nullable=True),
        sa.Column("skr04_account", sa.String(10), nullable=True),
        sa.Column("default_tax_rate", sa.Numeric(5, 2), server_default="19"),

        # Spezielle Typen
        sa.Column("category_type", sa.String(50), nullable=True),
        sa.Column("is_entertainment", sa.Boolean, server_default="false"),
        sa.Column("is_travel_expense", sa.Boolean, server_default="false"),
        sa.Column("deductible_percentage", sa.Integer, server_default="100"),

        # Vorsteuer
        sa.Column("allows_vat_deduction", sa.Boolean, server_default="true"),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_system", sa.Boolean, server_default="false"),
        sa.Column("sort_order", sa.Integer, server_default="0"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["cash_categories.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_cash_categories_company_id", "cash_categories", ["company_id"])
    op.create_index("ix_cash_categories_parent_id", "cash_categories", ["parent_id"])
    op.create_index("ix_cash_categories_is_active", "cash_categories", ["is_active"])
    op.create_index("ix_cash_categories_type", "cash_categories", ["category_type"])
    op.create_index("ix_cash_categories_sort", "cash_categories", ["sort_order"])

    # =========================================================================
    # 2. CASH_REGISTERS - Kassen
    # =========================================================================
    op.create_table(
        "cash_registers",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, nullable=False),

        # Identifikation
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("register_number", sa.String(50), nullable=True),

        # Waehrung & Limits
        sa.Column("currency", sa.String(3), server_default="EUR"),
        sa.Column("max_balance", sa.Numeric(15, 2), nullable=True),
        sa.Column("warning_threshold", sa.Numeric(15, 2), nullable=True),

        # Aktueller Stand
        sa.Column("current_balance", sa.Numeric(15, 2), server_default="0"),
        sa.Column("balance_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciliation_date", sa.DateTime(timezone=True), nullable=True),

        # Banking-Verknuepfung
        sa.Column("linked_bank_account_id", uuid_type, nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("is_default", sa.Boolean, server_default="false"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_bank_account_id"], ["bank_accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_cash_registers_company_id", "cash_registers", ["company_id"])
    op.create_index("ix_cash_registers_is_active", "cash_registers", ["is_active"])
    op.create_index("ix_cash_registers_deleted_at", "cash_registers", ["deleted_at"])
    op.create_index("ix_cash_registers_company_name", "cash_registers", ["company_id", "name"], unique=True)

    # =========================================================================
    # 3. EXPENSE_REPORTS - Spesenabrechnungen (vor cash_entries wegen FK)
    # =========================================================================
    op.create_table(
        "expense_reports",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, nullable=False),

        # Identifikation
        sa.Column("report_number", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Zeitraum
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),

        # Mitarbeiter
        sa.Column("employee_id", uuid_type, nullable=False),
        sa.Column("employee_name", sa.String(255), nullable=True),

        # Betraege
        sa.Column("total_amount", sa.Numeric(15, 2), server_default="0"),
        sa.Column("total_vat", sa.Numeric(15, 2), server_default="0"),
        sa.Column("total_deductible", sa.Numeric(15, 2), server_default="0"),

        # Reisekosten
        sa.Column("travel_days", sa.Integer, server_default="0"),
        sa.Column("travel_allowance_total", sa.Numeric(15, 2), server_default="0"),

        # Kilometergeld
        sa.Column("total_kilometers", sa.Numeric(10, 2), server_default="0"),
        sa.Column("mileage_allowance_total", sa.Numeric(15, 2), server_default="0"),

        # Status
        sa.Column("status", sa.String(50), server_default="draft"),

        # Workflow-Timestamps
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_by_id", uuid_type, nullable=True),

        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", uuid_type, nullable=True),
        sa.Column("review_notes", sa.Text, nullable=True),

        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", uuid_type, nullable=True),

        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by_id", uuid_type, nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),

        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_by_id", uuid_type, nullable=True),
        sa.Column("payment_method", sa.String(50), nullable=True),
        sa.Column("payment_reference", sa.String(100), nullable=True),

        # Verknuepfung zu Kassenbuch (wird spaeter hinzugefuegt)
        sa.Column("cash_entry_id", uuid_type, nullable=True),

        # DATEV
        sa.Column("datev_exported_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["employee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rejected_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["paid_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_expense_reports_company_id", "expense_reports", ["company_id"])
    op.create_index("ix_expense_reports_employee_id", "expense_reports", ["employee_id"])
    op.create_index("ix_expense_reports_status", "expense_reports", ["status"])
    op.create_index("ix_expense_reports_period", "expense_reports", ["period_start", "period_end"])
    op.create_index("ix_expense_reports_created_at", "expense_reports", ["created_at"])

    # =========================================================================
    # 4. CASH_ENTRIES - Kassenbuchungen (GoBD-konform, APPEND-ONLY!)
    # =========================================================================
    op.create_table(
        "cash_entries",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, nullable=False),
        sa.Column("cash_register_id", uuid_type, nullable=False),

        # Fortlaufende Nummer
        sa.Column("entry_number", sa.Integer, nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),

        # Buchungsdaten
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("value_date", sa.Date, nullable=False),

        # Betrag
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),

        # Saldo nach Buchung
        sa.Column("balance_after", sa.Numeric(15, 2), nullable=False),

        # Kategorisierung
        sa.Column("entry_type", sa.String(50), nullable=False),
        sa.Column("category_id", uuid_type, nullable=True),

        # Steuer
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("net_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("is_tax_deductible", sa.Boolean, server_default="true"),
        sa.Column("deductible_percentage", sa.Integer, server_default="100"),

        # Beschreibung
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("reference_number", sa.String(100), nullable=True),

        # Geschaeftspartner
        sa.Column("counterparty_name", sa.String(255), nullable=True),
        sa.Column("counterparty_id", uuid_type, nullable=True),

        # Verknuepfungen
        sa.Column("document_id", uuid_type, nullable=True),
        sa.Column("bank_transaction_id", uuid_type, nullable=True),
        sa.Column("expense_report_id", uuid_type, nullable=True),

        # Storno-Handling
        sa.Column("is_cancelled", sa.Boolean, server_default="false"),
        sa.Column("cancelled_by_entry_id", uuid_type, nullable=True),
        sa.Column("cancellation_reason", sa.Text, nullable=True),

        # Bewirtungskosten
        sa.Column("entertainment_data", json_type, nullable=True),

        # DATEV
        sa.Column("datev_exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("datev_export_batch_id", uuid_type, nullable=True),

        # Buchungskonten
        sa.Column("debit_account", sa.String(10), nullable=True),
        sa.Column("credit_account", sa.String(10), nullable=True),
        sa.Column("cost_center", sa.String(50), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by_id", uuid_type, nullable=False),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["cash_register_id"], ["cash_registers.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["category_id"], ["cash_categories.id"]),
        sa.ForeignKeyConstraint(["counterparty_id"], ["business_entities.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["bank_transaction_id"], ["bank_transactions.id"]),
        sa.ForeignKeyConstraint(["expense_report_id"], ["expense_reports.id"]),
        sa.ForeignKeyConstraint(["cancelled_by_entry_id"], ["cash_entries.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
    )

    op.create_index(
        "ix_cash_entries_unique_number",
        "cash_entries",
        ["cash_register_id", "fiscal_year", "entry_number"],
        unique=True
    )
    op.create_index("ix_cash_entries_company_id", "cash_entries", ["company_id"])
    op.create_index("ix_cash_entries_register_id", "cash_entries", ["cash_register_id"])
    op.create_index("ix_cash_entries_date", "cash_entries", ["entry_date"])
    op.create_index("ix_cash_entries_type", "cash_entries", ["entry_type"])
    op.create_index("ix_cash_entries_document_id", "cash_entries", ["document_id"])
    op.create_index("ix_cash_entries_cancelled", "cash_entries", ["is_cancelled"])
    op.create_index("ix_cash_entries_datev", "cash_entries", ["datev_exported_at"])

    # GoBD Constraints
    if is_postgres:
        op.execute("""
            ALTER TABLE cash_entries
            ADD CONSTRAINT ck_cash_entries_amount_not_zero
            CHECK (amount != 0)
        """)
        op.execute("""
            ALTER TABLE cash_entries
            ADD CONSTRAINT ck_cash_entries_no_future_date
            CHECK (entry_date <= CURRENT_DATE)
        """)

    # =========================================================================
    # 5. CASH_COUNTS - Zaehlprotokolle (Kassensturz)
    # =========================================================================
    op.create_table(
        "cash_counts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("company_id", uuid_type, nullable=False),
        sa.Column("cash_register_id", uuid_type, nullable=False),

        # Zeitpunkt
        sa.Column("count_date", sa.Date, nullable=False),
        sa.Column("count_time", sa.Time, nullable=False),

        # Muenzen
        sa.Column("coins_1_cent", sa.Integer, server_default="0"),
        sa.Column("coins_2_cent", sa.Integer, server_default="0"),
        sa.Column("coins_5_cent", sa.Integer, server_default="0"),
        sa.Column("coins_10_cent", sa.Integer, server_default="0"),
        sa.Column("coins_20_cent", sa.Integer, server_default="0"),
        sa.Column("coins_50_cent", sa.Integer, server_default="0"),
        sa.Column("coins_1_euro", sa.Integer, server_default="0"),
        sa.Column("coins_2_euro", sa.Integer, server_default="0"),

        # Scheine
        sa.Column("notes_5_euro", sa.Integer, server_default="0"),
        sa.Column("notes_10_euro", sa.Integer, server_default="0"),
        sa.Column("notes_20_euro", sa.Integer, server_default="0"),
        sa.Column("notes_50_euro", sa.Integer, server_default="0"),
        sa.Column("notes_100_euro", sa.Integer, server_default="0"),
        sa.Column("notes_200_euro", sa.Integer, server_default="0"),
        sa.Column("notes_500_euro", sa.Integer, server_default="0"),

        # Soll-Bestand
        sa.Column("expected_total", sa.Numeric(15, 2), nullable=False),

        # Differenz
        sa.Column("difference_entry_id", uuid_type, nullable=True),
        sa.Column("difference_explanation", sa.Text, nullable=True),

        # Signatur
        sa.Column("counted_by_id", uuid_type, nullable=False),
        sa.Column("verified_by_id", uuid_type, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("notes", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cash_register_id"], ["cash_registers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["difference_entry_id"], ["cash_entries.id"]),
        sa.ForeignKeyConstraint(["counted_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"]),
    )

    op.create_index("ix_cash_counts_company_id", "cash_counts", ["company_id"])
    op.create_index("ix_cash_counts_register_id", "cash_counts", ["cash_register_id"])
    op.create_index("ix_cash_counts_date", "cash_counts", ["count_date"])

    # =========================================================================
    # 6. EXPENSE_ITEMS - Spesenpositionen
    # =========================================================================
    op.create_table(
        "expense_items",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("expense_report_id", uuid_type, nullable=False),

        # Kategorisierung
        sa.Column("category_id", uuid_type, nullable=True),
        sa.Column("expense_type", sa.String(50), nullable=False),

        # Datum
        sa.Column("expense_date", sa.Date, nullable=False),

        # Betrag
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default="EUR"),

        # Steuer
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("net_amount", sa.Numeric(15, 2), nullable=True),

        # Abzugsfaehigkeit
        sa.Column("is_deductible", sa.Boolean, server_default="true"),
        sa.Column("deductible_percentage", sa.Integer, server_default="100"),
        sa.Column("deductible_amount", sa.Numeric(15, 2), nullable=True),

        # Beschreibung
        sa.Column("description", sa.Text, nullable=False),

        # Beleg
        sa.Column("document_id", uuid_type, nullable=True),
        sa.Column("receipt_number", sa.String(100), nullable=True),

        # Geschaeftspartner
        sa.Column("vendor_name", sa.String(255), nullable=True),
        sa.Column("vendor_id", uuid_type, nullable=True),

        # Bewirtung
        sa.Column("entertainment_participants", json_type, nullable=True),
        sa.Column("entertainment_occasion", sa.Text, nullable=True),
        sa.Column("entertainment_location", sa.String(255), nullable=True),

        # Kilometergeld
        sa.Column("mileage_from", sa.String(255), nullable=True),
        sa.Column("mileage_to", sa.String(255), nullable=True),
        sa.Column("mileage_kilometers", sa.Numeric(10, 2), nullable=True),
        sa.Column("mileage_rate", sa.Numeric(5, 2), server_default="0.30"),
        sa.Column("mileage_vehicle_type", sa.String(50), nullable=True),
        sa.Column("mileage_license_plate", sa.String(20), nullable=True),

        # Verpflegungspauschale
        sa.Column("per_diem_hours", sa.Numeric(4, 1), nullable=True),
        sa.Column("per_diem_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("per_diem_breakfast_provided", sa.Boolean, server_default="false"),
        sa.Column("per_diem_lunch_provided", sa.Boolean, server_default="false"),
        sa.Column("per_diem_dinner_provided", sa.Boolean, server_default="false"),

        # Buchhaltung
        sa.Column("skr_account", sa.String(10), nullable=True),
        sa.Column("cost_center", sa.String(50), nullable=True),

        # Sortierung
        sa.Column("sort_order", sa.Integer, server_default="0"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["expense_report_id"], ["expense_reports.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["cash_categories.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["business_entities.id"]),
    )

    op.create_index("ix_expense_items_report_id", "expense_items", ["expense_report_id"])
    op.create_index("ix_expense_items_date", "expense_items", ["expense_date"])
    op.create_index("ix_expense_items_document_id", "expense_items", ["document_id"])
    op.create_index("ix_expense_items_type", "expense_items", ["expense_type"])

    # =========================================================================
    # 7. ADD FK from expense_reports to cash_entries (nachtraeglich)
    # =========================================================================
    op.create_foreign_key(
        "fk_expense_reports_cash_entry",
        "expense_reports",
        "cash_entries",
        ["cash_entry_id"],
        ["id"]
    )

    # =========================================================================
    # 8. GoBD Trigger: Verhindere UPDATE/DELETE auf cash_entries (PostgreSQL)
    # =========================================================================
    if is_postgres:
        op.execute("""
            CREATE OR REPLACE FUNCTION prevent_cash_entry_modification()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'GoBD-Compliance: Kassenbuchungen duerfen nicht geaendert oder geloescht werden. Verwenden Sie stattdessen eine Stornobuchung.';
            END;
            $$ LANGUAGE plpgsql;
        """)

        op.execute("""
            CREATE TRIGGER cash_entries_prevent_update
            BEFORE UPDATE ON cash_entries
            FOR EACH ROW
            EXECUTE FUNCTION prevent_cash_entry_modification();
        """)

        op.execute("""
            CREATE TRIGGER cash_entries_prevent_delete
            BEFORE DELETE ON cash_entries
            FOR EACH ROW
            EXECUTE FUNCTION prevent_cash_entry_modification();
        """)

    # =========================================================================
    # 9. RLS fuer cash_entries (PostgreSQL)
    # =========================================================================
    if is_postgres:
        op.execute("ALTER TABLE cash_entries ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE cash_registers ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE cash_categories ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE cash_counts ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE expense_reports ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE expense_items ENABLE ROW LEVEL SECURITY")

    # =========================================================================
    # 10. SEED: Default-Kategorien
    # =========================================================================
    op.execute("""
        INSERT INTO cash_categories (id, name, name_en, skr03_account, skr04_account, category_type, is_entertainment, deductible_percentage, is_system, sort_order)
        VALUES
            (gen_random_uuid(), 'Bewirtungskosten', 'Entertainment', '4650', '6640', 'entertainment', true, 70, true, 10),
            (gen_random_uuid(), 'Reisekosten Verpflegung', 'Travel Per Diem', '4664', '6664', 'travel', false, 100, true, 20),
            (gen_random_uuid(), 'Reisekosten Fahrt', 'Travel Transport', '4663', '6663', 'travel', false, 100, true, 21),
            (gen_random_uuid(), 'Reisekosten Unterkunft', 'Travel Accommodation', '4666', '6666', 'travel', false, 100, true, 22),
            (gen_random_uuid(), 'Buerobedarf', 'Office Supplies', '4930', '6815', 'office', false, 100, true, 30),
            (gen_random_uuid(), 'Kraftstoff', 'Fuel', '4530', '6530', 'fuel', false, 100, true, 40),
            (gen_random_uuid(), 'Parkgebuehren', 'Parking', '4540', '6540', 'parking', false, 100, true, 41),
            (gen_random_uuid(), 'Porto/Versand', 'Postage', '4910', '6800', 'postage', false, 100, true, 50),
            (gen_random_uuid(), 'Trinkgeld', 'Tips', '4969', '6859', 'tips', false, 100, true, 60),
            (gen_random_uuid(), 'Geschenke abzugsfaehig', 'Gifts (deductible)', '4630', '6610', 'gifts', false, 100, true, 70),
            (gen_random_uuid(), 'Geschenke nicht abzugsfaehig', 'Gifts (non-deductible)', '4635', '6620', 'gifts', false, 0, true, 71),
            (gen_random_uuid(), 'Sonstige Ausgaben', 'Other Expenses', '4900', '6300', 'other', false, 100, true, 100)
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    """Remove Kasse-Modul tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Drop triggers (PostgreSQL)
    if is_postgres:
        op.execute("DROP TRIGGER IF EXISTS cash_entries_prevent_delete ON cash_entries")
        op.execute("DROP TRIGGER IF EXISTS cash_entries_prevent_update ON cash_entries")
        op.execute("DROP FUNCTION IF EXISTS prevent_cash_entry_modification()")

    # Disable RLS
    if is_postgres:
        op.execute("ALTER TABLE expense_items DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE expense_reports DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE cash_counts DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE cash_categories DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE cash_registers DISABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE cash_entries DISABLE ROW LEVEL SECURITY")

    # Drop FK
    op.drop_constraint("fk_expense_reports_cash_entry", "expense_reports", type_="foreignkey")

    # Drop tables in reverse order
    op.drop_table("expense_items")
    op.drop_table("cash_counts")
    op.drop_table("cash_entries")
    op.drop_table("expense_reports")
    op.drop_table("cash_registers")
    op.drop_table("cash_categories")
