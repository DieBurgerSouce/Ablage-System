"""Add ondelete cascade/set_null to ForeignKey constraints.

Revision ID: 256
Revises: 255
Create Date: 2026-02-26
"""
from alembic import op

revision = "256"
down_revision = "255"
branch_labels = None
depends_on = None

# FK changes: (table, column, ref_table, ondelete)
FK_CHANGES = [
    # models_cash_company.py - CashEntry
    ("cash_entries", "category_id", "cash_categories", "SET NULL"),
    ("cash_entries", "counterparty_id", "business_entities", "SET NULL"),
    ("cash_entries", "document_id", "documents", "SET NULL"),
    ("cash_entries", "bank_transaction_id", "bank_transactions", "SET NULL"),
    ("cash_entries", "expense_report_id", "expense_reports", "SET NULL"),
    ("cash_entries", "cancelled_by_entry_id", "cash_entries", "SET NULL"),
    ("cash_entries", "created_by_id", "users", "RESTRICT"),
    # CashCategory
    ("cash_categories", "parent_id", "cash_categories", "SET NULL"),
    # CashCount
    ("cash_counts", "difference_entry_id", "cash_entries", "SET NULL"),
    ("cash_counts", "counted_by_id", "users", "RESTRICT"),
    ("cash_counts", "verified_by_id", "users", "SET NULL"),
    # ExpenseReport
    ("expense_reports", "employee_id", "users", "RESTRICT"),
    ("expense_reports", "submitted_by_id", "users", "SET NULL"),
    ("expense_reports", "reviewed_by_id", "users", "SET NULL"),
    ("expense_reports", "approved_by_id", "users", "SET NULL"),
    ("expense_reports", "rejected_by_id", "users", "SET NULL"),
    ("expense_reports", "paid_by_id", "users", "SET NULL"),
    ("expense_reports", "cash_entry_id", "cash_entries", "SET NULL"),
    ("expense_reports", "created_by_id", "users", "SET NULL"),
    ("expense_reports", "deleted_by_id", "users", "SET NULL"),
    # ExpenseItem
    ("expense_items", "category_id", "cash_categories", "SET NULL"),
    ("expense_items", "document_id", "documents", "SET NULL"),
    ("expense_items", "vendor_id", "business_entities", "SET NULL"),
    # models_entity_business.py - BusinessContract
    ("business_contracts", "company_id", "companies", "CASCADE"),
    ("business_contracts", "party_a_id", "business_entities", "SET NULL"),
    ("business_contracts", "party_b_id", "business_entities", "SET NULL"),
    ("business_contracts", "document_id", "documents", "SET NULL"),
    ("business_contracts", "created_by_id", "users", "SET NULL"),
    # ContractMilestone
    ("contract_milestones", "contract_id", "business_contracts", "CASCADE"),
    # ContractRenewalOption
    ("contract_renewal_options", "contract_id", "business_contracts", "CASCADE"),
    ("contract_renewal_options", "exercised_by_id", "users", "SET NULL"),
    # ContractAmendment
    ("contract_amendments", "contract_id", "business_contracts", "CASCADE"),
    ("contract_amendments", "document_id", "documents", "SET NULL"),
    ("contract_amendments", "approved_by_id", "users", "SET NULL"),
    ("contract_amendments", "created_by_id", "users", "SET NULL"),
    # DocumentContact
    ("document_contacts", "confirmed_by_id", "users", "SET NULL"),
    # BusinessContact
    ("business_contacts", "parent_company_id", "business_contacts", "SET NULL"),
    ("business_contacts", "owner_id", "users", "CASCADE"),
    ("business_contacts", "company_id", "companies", "SET NULL"),
    ("business_contacts", "first_document_id", "documents", "SET NULL"),
    ("business_contacts", "merged_into_id", "business_contacts", "SET NULL"),
    # models.py - Document
    ("documents", "owner_id", "users", "CASCADE"),
    # BatchJob
    ("batch_jobs", "cancelled_by_id", "users", "SET NULL"),
    # ScheduledExport
    ("scheduled_exports", "last_run_job_id", "batch_jobs", "SET NULL"),
]


def upgrade() -> None:
    for table, column, ref_table, ondelete in FK_CHANGES:
        constraint_name = f"{table}_{column}_fkey"
        op.drop_constraint(constraint_name, table, type_="foreignkey")
        op.create_foreign_key(
            constraint_name, table, ref_table,
            [column], ["id"], ondelete=ondelete,
        )


def downgrade() -> None:
    for table, column, ref_table, _ in FK_CHANGES:
        constraint_name = f"{table}_{column}_fkey"
        op.drop_constraint(constraint_name, table, type_="foreignkey")
        op.create_foreign_key(
            constraint_name, table, ref_table,
            [column], ["id"],
        )
