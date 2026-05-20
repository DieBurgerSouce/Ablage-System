# -*- coding: utf-8 -*-
"""Add company_id to document_groups for Multi-Tenant Isolation.

Revision ID: 251
Revises: 250
Create Date: 2026-02-22

Multi-Tenant Security Fix:
- document_groups hatte nur owner_id (User-Isolation)
- Jetzt company_id fuer Company-Isolation (wie documents, invoice_tracking, etc.)
- 5-Schritt-Pattern: ADD NULL -> Backfill -> SET NOT NULL -> FK -> Indexes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "251"
down_revision = "250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Schritt 1: Column als NULL hinzufuegen
    op.add_column(
        "document_groups",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
            comment="Mandanten-Zuordnung fuer Multi-Company Isolation",
        ),
    )

    # Schritt 2: Backfill - company_id aus owner_id ableiten
    # Ueber user_companies die company_id des Owners ermitteln
    op.execute(
        """
        UPDATE document_groups
        SET company_id = (
            SELECT uc.company_id
            FROM user_companies uc
            WHERE uc.user_id = document_groups.owner_id
            LIMIT 1
        )
        WHERE owner_id IS NOT NULL
        """
    )

    # Fallback: Falls owner_id NULL oder kein user_companies-Eintrag,
    # Default-Company verwenden (erste Company)
    op.execute(
        """
        UPDATE document_groups
        SET company_id = (
            SELECT id FROM companies ORDER BY created_at ASC LIMIT 1
        )
        WHERE company_id IS NULL
        """
    )

    # Schritt 3: NOT NULL setzen
    op.alter_column(
        "document_groups",
        "company_id",
        nullable=False,
    )

    # Schritt 4: Foreign Key
    op.create_foreign_key(
        "fk_document_groups_company_id",
        "document_groups",
        "companies",
        ["company_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # Schritt 5: Indexes
    op.create_index(
        "ix_document_groups_company_id",
        "document_groups",
        ["company_id"],
    )
    op.create_index(
        "ix_document_groups_company_group_type",
        "document_groups",
        ["company_id", "group_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_groups_company_group_type", table_name="document_groups")
    op.drop_index("ix_document_groups_company_id", table_name="document_groups")
    op.drop_constraint("fk_document_groups_company_id", "document_groups", type_="foreignkey")
    op.drop_column("document_groups", "company_id")
