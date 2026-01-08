"""Enhance tags table for admin management.

Revision ID: 038_enhance_tags_for_admin_management
Revises: 037_add_company_settings
Create Date: 2024-12-13

Aenderungen:
- icon: Lucide Icon-Name fuer visuelle Darstellung
- is_system: System-Tags koennen nicht geloescht werden
- is_active: Aktiv/Inaktiv Status
- tune_id: Optionale Verknuepfung mit Tunes fuer OCR-Feintuning
- updated_at: Zeitstempel fuer Aenderungen

Seed-Daten:
- Alte Default-Tags entfernen
- Neue System-Tags: Eingangsrechnung, Ausgangsrechnung
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None

# Fixed UUIDs fuer idempotente Migration
# SECURITY NOTE (T.4): Diese UUIDs sind Konstanten und daher sicher fuer f-string SQL.
# NIEMALS dynamische/user-supplied Werte auf diese Weise verwenden!
# Fuer neue Migrationen: Verwende sa.text() mit :parameter Binding.
EINGANGSRECHNUNG_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUSGANGSRECHNUNG_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")


def upgrade() -> None:
    """Enhance tags table with new columns and seed system tags."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
    else:
        uuid_type = sa.String(36)

    # =========================================================================
    # ALTER EXISTING COLOR COLUMN (varchar(7) -> varchar(50))
    # =========================================================================

    # Existing color column is varchar(7) for hex codes like #4CAF50
    # We need varchar(50) to support Tailwind classes like bg-green-500
    op.alter_column(
        "tags",
        "color",
        type_=sa.String(50),
        existing_type=sa.String(7),
        existing_nullable=True
    )

    # =========================================================================
    # ADD NEW COLUMNS TO TAGS TABLE
    # =========================================================================

    # icon - Lucide icon name
    op.add_column(
        "tags",
        sa.Column("icon", sa.String(50), nullable=True, server_default="Tag")
    )

    # is_system - System tags cannot be deleted
    op.add_column(
        "tags",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false")
    )

    # is_active - Active/Inactive status
    op.add_column(
        "tags",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true")
    )

    # tune_id - Optional link to Tunes for OCR fine-tuning
    op.add_column(
        "tags",
        sa.Column("tune_id", uuid_type, nullable=True)
    )

    # updated_at - Timestamp for changes
    op.add_column(
        "tags",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True
        )
    )

    # =========================================================================
    # ADD FOREIGN KEY CONSTRAINT
    # =========================================================================

    op.create_foreign_key(
        "fk_tags_tune_id",
        "tags",
        "tunes",
        ["tune_id"],
        ["id"],
        ondelete="SET NULL"
    )

    # =========================================================================
    # ADD INDEXES
    # =========================================================================

    op.create_index("ix_tags_is_system", "tags", ["is_system"])
    op.create_index("ix_tags_is_active", "tags", ["is_active"])
    op.create_index("ix_tags_tune_id", "tags", ["tune_id"])

    # =========================================================================
    # REMOVE OLD DEFAULT TAGS
    # =========================================================================

    op.execute("""
        DELETE FROM tags
        WHERE name IN (
            'Rechnung', 'Vertrag', 'Persönlich', 'Geschäftlich',
            'Steuer', 'Archiv', 'Brief', 'Formular'
        )
        AND NOT EXISTS (
            SELECT 1 FROM document_tags WHERE document_tags.tag_id = tags.id
        );
    """)

    # =========================================================================
    # SEED NEW SYSTEM TAGS
    # =========================================================================

    if is_postgres:
        op.execute(f"""
            INSERT INTO tags (id, name, description, icon, color, is_system, is_active, created_at, updated_at)
            VALUES
                (
                    '{EINGANGSRECHNUNG_ID}',
                    'Eingangsrechnung',
                    'Eingehende Rechnungen von Lieferanten und Dienstleistern',
                    'ArrowDownLeft',
                    'bg-green-500',
                    true,
                    true,
                    NOW(),
                    NOW()
                ),
                (
                    '{AUSGANGSRECHNUNG_ID}',
                    'Ausgangsrechnung',
                    'Ausgehende Rechnungen an Kunden',
                    'ArrowUpRight',
                    'bg-blue-500',
                    true,
                    true,
                    NOW(),
                    NOW()
                )
            ON CONFLICT (name) DO UPDATE SET
                is_system = true,
                icon = EXCLUDED.icon,
                color = EXCLUDED.color,
                description = EXCLUDED.description,
                updated_at = NOW();
        """)
    else:
        # SQLite fallback
        op.execute(f"""
            INSERT OR REPLACE INTO tags (id, name, description, icon, color, is_system, is_active, created_at, updated_at)
            VALUES
                (
                    '{EINGANGSRECHNUNG_ID}',
                    'Eingangsrechnung',
                    'Eingehende Rechnungen von Lieferanten und Dienstleistern',
                    'ArrowDownLeft',
                    'bg-green-500',
                    1,
                    1,
                    datetime('now'),
                    datetime('now')
                ),
                (
                    '{AUSGANGSRECHNUNG_ID}',
                    'Ausgangsrechnung',
                    'Ausgehende Rechnungen an Kunden',
                    'ArrowUpRight',
                    'bg-blue-500',
                    1,
                    1,
                    datetime('now'),
                    datetime('now')
                );
        """)


def downgrade() -> None:
    """Revert tag enhancements."""

    # Remove system tags
    op.execute(f"""
        DELETE FROM tags
        WHERE id IN ('{EINGANGSRECHNUNG_ID}', '{AUSGANGSRECHNUNG_ID}');
    """)

    # Drop indexes
    op.drop_index("ix_tags_tune_id", table_name="tags")
    op.drop_index("ix_tags_is_active", table_name="tags")
    op.drop_index("ix_tags_is_system", table_name="tags")

    # Drop foreign key
    op.drop_constraint("fk_tags_tune_id", "tags", type_="foreignkey")

    # Drop columns
    op.drop_column("tags", "updated_at")
    op.drop_column("tags", "tune_id")
    op.drop_column("tags", "is_active")
    op.drop_column("tags", "is_system")
    op.drop_column("tags", "icon")

    # Re-seed old default tags
    op.execute("""
        INSERT INTO tags (id, name, description, color, created_at) VALUES
            (gen_random_uuid(), 'Rechnung', 'Rechnungen und Quittungen', '#4CAF50', NOW()),
            (gen_random_uuid(), 'Vertrag', 'Verträge und Vereinbarungen', '#2196F3', NOW()),
            (gen_random_uuid(), 'Persönlich', 'Persönliche Dokumente', '#FF9800', NOW()),
            (gen_random_uuid(), 'Geschäftlich', 'Geschäftsdokumente', '#9C27B0', NOW()),
            (gen_random_uuid(), 'Steuer', 'Steuerrelevante Dokumente', '#F44336', NOW()),
            (gen_random_uuid(), 'Archiv', 'Archivierte Dokumente', '#607D8B', NOW()),
            (gen_random_uuid(), 'Brief', 'Briefe und Korrespondenz', '#00BCD4', NOW()),
            (gen_random_uuid(), 'Formular', 'Formulare und Anträge', '#795548', NOW())
        ON CONFLICT (name) DO NOTHING;
    """)
