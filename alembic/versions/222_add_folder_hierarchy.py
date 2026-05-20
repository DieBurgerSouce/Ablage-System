"""Add folder hierarchy tables.

Erstellt die Tabellen fuer die geschaeftliche Ordnerstruktur:
- folders: Hierarchische Ordner mit Materialized Path
- folder_permissions: Berechtigungen mit Vererbung
- folder_documents: Zuordnung Dokumente ↔ Ordner

Revision ID: 222_add_folder_hierarchy
Revises: 221_merge_heads
Create Date: 2026-02-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "222_add_folder_hierarchy"
down_revision: Union[str, Sequence[str]] = "221_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ================================================================
    # folders
    # ================================================================
    op.create_table(
        "folders",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), server_default="Folder"),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("path", sa.String(4000), nullable=False),
        sa.Column("level", sa.Integer, server_default="0"),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("folder_type", sa.String(50), server_default="geschaeftlich", nullable=False),
        sa.Column("folder_metadata", postgresql.JSONB, server_default="{}"),
        sa.Column("document_count", sa.Integer, server_default="0"),
        sa.Column("subfolder_count", sa.Integer, server_default="0"),
        sa.Column("is_locked", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "created_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_folders_company_id", "folders", ["company_id"])
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])
    op.create_index("ix_folders_path", "folders", ["path"])
    op.create_index("ix_folders_folder_type", "folders", ["folder_type"])
    op.create_index("ix_folders_deleted_at", "folders", ["deleted_at"])
    op.create_index("ix_folders_company_parent", "folders", ["company_id", "parent_id"])
    op.create_index("ix_folders_company_name", "folders", ["company_id", "name"])
    op.create_index("ix_folders_sort_order", "folders", ["parent_id", "sort_order"])

    # ================================================================
    # folder_permissions
    # ================================================================
    op.create_table(
        "folder_permissions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "folder_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("permission_level", sa.String(20), server_default="read", nullable=False),
        sa.Column("inherited", sa.Boolean, server_default="false"),
        sa.Column(
            "inherited_from_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "granted_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_folder_user_permission", "folder_permissions", ["folder_id", "user_id"]
    )
    op.create_index("ix_folder_permissions_folder_id", "folder_permissions", ["folder_id"])
    op.create_index("ix_folder_permissions_user_id", "folder_permissions", ["user_id"])
    op.create_index("ix_folder_permissions_inherited", "folder_permissions", ["inherited"])

    # ================================================================
    # folder_documents
    # ================================================================
    op.create_table(
        "folder_documents",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "folder_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("folders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer, server_default="0"),
        sa.Column("is_primary", sa.Boolean, server_default="true"),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column(
            "added_by_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_folder_document", "folder_documents", ["folder_id", "document_id"]
    )
    op.create_index("ix_folder_documents_folder_id", "folder_documents", ["folder_id"])
    op.create_index("ix_folder_documents_document_id", "folder_documents", ["document_id"])
    op.create_index(
        "ix_folder_documents_is_primary", "folder_documents", ["document_id", "is_primary"]
    )
    op.create_index(
        "ix_folder_documents_sort_order", "folder_documents", ["folder_id", "sort_order"]
    )


def downgrade() -> None:
    op.drop_table("folder_documents")
    op.drop_table("folder_permissions")
    op.drop_table("folders")
