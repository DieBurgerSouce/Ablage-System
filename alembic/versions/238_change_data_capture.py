"""Change Data Capture (CDC) Infrastruktur.

Revision ID: 238
Revises: 237
Create Date: 2026-02-20

Erstellt die CDC-Infrastruktur fuer Echtzeit-Aenderungserfassung:
- change_data_capture_logs: Protokolltabelle fuer alle Aenderungen
- cdc_consumer_offsets: Verarbeitungsfortschritt der Consumer
- cdc_capture_changes(): PostgreSQL Trigger-Funktion
- Trigger auf documents, invoice_tracking, business_entities, bank_transactions
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "238"
down_revision = "237"
branch_labels = None
depends_on = None

# Tabellen, die per CDC ueberwacht werden
MONITORED_TABLES = [
    "documents",
    "invoice_tracking",
    "business_entities",
    "bank_transactions",
]


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. change_data_capture_logs
    # ------------------------------------------------------------------
    op.create_table(
        "change_data_capture_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_table", sa.String(100), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("old_data", postgresql.JSONB, nullable=True),
        sa.Column("new_data", postgresql.JSONB, nullable=True),
        sa.Column("changed_columns", postgresql.JSONB, server_default="[]"),
        sa.Column(
            "sequence_number",
            sa.BigInteger,
            sa.Sequence("cdc_sequence_number_seq"),
            unique=True,
            nullable=False,
        ),
        sa.Column("processed", sa.Boolean, server_default="false"),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumer_id", sa.String(100), nullable=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("transaction_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )

    # Standard-Indexes
    op.create_index(
        "ix_cdc_logs_source_table",
        "change_data_capture_logs",
        ["source_table"],
    )
    op.create_index(
        "ix_cdc_logs_source_id",
        "change_data_capture_logs",
        ["source_id"],
    )
    op.create_index(
        "ix_cdc_logs_operation",
        "change_data_capture_logs",
        ["operation"],
    )
    op.create_index(
        "ix_cdc_logs_processed",
        "change_data_capture_logs",
        ["processed"],
    )
    op.create_index(
        "ix_cdc_logs_company_id",
        "change_data_capture_logs",
        ["company_id"],
    )

    # Composite-Indexes
    op.create_index(
        "ix_cdc_source",
        "change_data_capture_logs",
        ["source_table", "source_id", "sequence_number"],
    )
    op.create_index(
        "ix_cdc_company_table",
        "change_data_capture_logs",
        ["company_id", "source_table", "created_at"],
    )

    # Partial-Index: Nur unverarbeitete Events
    op.execute(
        "CREATE INDEX ix_cdc_unprocessed "
        "ON change_data_capture_logs (processed, created_at) "
        "WHERE processed = false"
    )

    # ------------------------------------------------------------------
    # 2. cdc_consumer_offsets
    # ------------------------------------------------------------------
    op.create_table(
        "cdc_consumer_offsets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("consumer_name", sa.String(100), nullable=False, unique=True),
        sa.Column("last_sequence_number", sa.BigInteger, server_default="0"),
        sa.Column(
            "last_processed_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("status", sa.String(20), server_default="'active'"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("config", postgresql.JSONB, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )

    # ------------------------------------------------------------------
    # 3. Trigger-Funktion: cdc_capture_changes()
    # ------------------------------------------------------------------
    op.execute("""
CREATE OR REPLACE FUNCTION cdc_capture_changes() RETURNS TRIGGER AS $$
DECLARE
    changed_cols jsonb := '[]'::jsonb;
    col_name text;
    old_val text;
    new_val text;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        FOR col_name IN SELECT column_name FROM information_schema.columns
            WHERE table_name = TG_TABLE_NAME AND table_schema = TG_TABLE_SCHEMA
        LOOP
            EXECUTE format('SELECT ($1).%I::text, ($2).%I::text', col_name, col_name)
                INTO old_val, new_val USING OLD, NEW;
            IF old_val IS DISTINCT FROM new_val THEN
                changed_cols := changed_cols || to_jsonb(col_name);
            END IF;
        END LOOP;
    END IF;

    INSERT INTO change_data_capture_logs (
        id, source_table, source_id, operation,
        old_data, new_data, changed_columns,
        sequence_number,
        company_id, user_id, transaction_id, created_at
    ) VALUES (
        gen_random_uuid(),
        TG_TABLE_NAME,
        CASE TG_OP
            WHEN 'DELETE' THEN (OLD.id)::uuid
            ELSE (NEW.id)::uuid
        END,
        TG_OP,
        CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) ELSE NULL END,
        CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) ELSE NULL END,
        changed_cols,
        nextval('cdc_sequence_number_seq'),
        NULLIF(current_setting('app.current_company_id', true), '')::uuid,
        NULLIF(current_setting('app.current_user_id', true), '')::uuid,
        txid_current()::text,
        NOW()
    );

    RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END;
$$ LANGUAGE plpgsql
""")

    # ------------------------------------------------------------------
    # 4. Trigger auf ueberwachte Tabellen
    # ------------------------------------------------------------------
    for table in MONITORED_TABLES:
        op.execute(
            f"CREATE TRIGGER cdc_{table}_trigger "
            f"AFTER INSERT OR UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION cdc_capture_changes()"
        )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Trigger entfernen
    # ------------------------------------------------------------------
    for table in MONITORED_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS cdc_{table}_trigger ON {table}")

    # ------------------------------------------------------------------
    # Trigger-Funktion entfernen
    # ------------------------------------------------------------------
    op.execute("DROP FUNCTION IF EXISTS cdc_capture_changes()")

    # ------------------------------------------------------------------
    # Tabellen entfernen
    # ------------------------------------------------------------------
    op.drop_table("cdc_consumer_offsets")

    # Indexes werden automatisch mit der Tabelle entfernt
    op.drop_table("change_data_capture_logs")

    # Sequence entfernen
    op.execute("DROP SEQUENCE IF EXISTS cdc_sequence_number_seq")
