"""Banking Multi-Tenant Migration: Add company_id to banking models.

Revision ID: 232
Revises: 231
Create Date: 2026-02-16

This migration adds company_id column to all banking tables for multi-tenant isolation:
- bank_accounts
- bank_imports
- payment_batches
- payment_orders
- dunning_records

Backfills company_id from user's company association and adds indexes for performance.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "232"
down_revision = "231"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add company_id to banking tables for multi-tenant support."""
    tables = ["bank_accounts", "bank_imports", "payment_batches", "payment_orders", "dunning_records"]

    # Step 1: Add nullable company_id column to all tables
    for table in tables:
        op.add_column(table, sa.Column("company_id", UUID(as_uuid=True), nullable=True))

    # Step 2: Backfill company_id from user_companies (many-to-many, use current company)
    for table in tables:
        op.execute(f"""
            UPDATE {table} SET company_id = (
                SELECT uc.company_id FROM user_companies uc
                WHERE uc.user_id = {table}.user_id
                ORDER BY uc.is_current DESC NULLS LAST, uc.created_at DESC
                LIMIT 1
            ) WHERE company_id IS NULL
        """)

    # Step 2b: For any remaining NULL company_id (users without company), use first company
    for table in tables:
        op.execute(f"""
            UPDATE {table} SET company_id = (
                SELECT id FROM companies ORDER BY created_at LIMIT 1
            ) WHERE company_id IS NULL
        """)

    # Step 3: Make company_id NOT NULL after backfill (only if rows exist)
    for table in tables:
        op.alter_column(table, "company_id", nullable=False)

    # Step 4: Add foreign key constraints
    for table in tables:
        op.create_foreign_key(
            f"fk_{table}_company_id",
            table,
            "companies",
            ["company_id"],
            ["id"],
            ondelete="CASCADE"
        )

    # Step 5: Add single-column indexes
    for table in tables:
        op.create_index(f"ix_{table}_company_id", table, ["company_id"])

    # Step 6: Add composite indexes for frequently queried combinations
    op.create_index(
        "ix_bank_accounts_company_id_is_active",
        "bank_accounts",
        ["company_id", "is_active"]
    )
    op.create_index(
        "ix_dunning_records_company_id_status",
        "dunning_records",
        ["company_id", "status"]
    )


def downgrade() -> None:
    """Remove company_id columns and related indexes."""
    # Drop composite indexes first
    op.drop_index("ix_dunning_records_company_id_status", table_name="dunning_records")
    op.drop_index("ix_bank_accounts_company_id_is_active", table_name="bank_accounts")

    # Drop single-column indexes and constraints
    tables = ["dunning_records", "payment_orders", "payment_batches", "bank_imports", "bank_accounts"]
    for table in tables:
        op.drop_index(f"ix_{table}_company_id", table_name=table)
        op.drop_constraint(f"fk_{table}_company_id", table, type_="foreignkey")
        op.drop_column(table, "company_id")
