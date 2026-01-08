"""Fix SearchAnalytics query column name - SQLAlchemy reserved.

Revision ID: 066_fix_search_analytics_query
Revises: 065_fix_privat_relationship_column
Create Date: 2024-12-30

'query' ist ein reservierter SQLAlchemy-Name (Base.query property).
Umbenennung zu 'search_query' erforderlich um Konflikte zu vermeiden.
"""
from alembic import op

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename query -> search_query in search_analytics."""
    # All operations are conditional - skip if table/column doesn't exist
    op.execute("""
        DO $$
        BEGIN
            -- Drop old index if exists
            DROP INDEX IF EXISTS ix_search_analytics_query_pattern;

            -- Rename column if 'query' exists
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'search_analytics' AND column_name = 'query'
            ) THEN
                ALTER TABLE search_analytics RENAME COLUMN query TO search_query;
            END IF;

            -- Create index only if search_query column exists
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'search_analytics' AND column_name = 'search_query'
            ) THEN
                CREATE INDEX IF NOT EXISTS ix_search_analytics_query_pattern
                ON search_analytics (search_query varchar_pattern_ops);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Revert search_query -> query in search_analytics."""
    # Drop the new index first
    op.drop_index('ix_search_analytics_query_pattern', table_name='search_analytics')

    # Rename the column back
    op.alter_column(
        'search_analytics',
        'search_query',
        new_column_name='query'
    )

    # Recreate the index with old column name
    op.create_index(
        'ix_search_analytics_query_pattern',
        'search_analytics',
        ['query'],
        postgresql_ops={'query': 'varchar_pattern_ops'}
    )
