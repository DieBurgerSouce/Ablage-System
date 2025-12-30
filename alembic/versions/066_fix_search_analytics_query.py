"""Fix SearchAnalytics query column name - SQLAlchemy reserved.

Revision ID: 066_fix_search_analytics_query
Revises: 065_fix_privat_relationship_column
Create Date: 2024-12-30

'query' ist ein reservierter SQLAlchemy-Name (Base.query property).
Umbenennung zu 'search_query' erforderlich um Konflikte zu vermeiden.
"""
from alembic import op

revision = '066_fix_search_analytics_query'
down_revision = '065_fix_privat_relationship_column'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename query -> search_query in search_analytics."""
    # Drop the old index first
    op.drop_index('ix_search_analytics_query_pattern', table_name='search_analytics')

    # Rename the column
    op.alter_column(
        'search_analytics',
        'query',
        new_column_name='search_query'
    )

    # Recreate the index with new column name
    op.create_index(
        'ix_search_analytics_query_pattern',
        'search_analytics',
        ['search_query'],
        postgresql_ops={'search_query': 'varchar_pattern_ops'}
    )


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
