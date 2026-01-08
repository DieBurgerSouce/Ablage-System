"""Add search analytics table

Revision ID: 006
Revises: 005
Create Date: 2025-11-27

Adds search analytics table for tracking search patterns, performance,
and user engagement metrics.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ========== Create search_analytics table ==========
    op.create_table(
        'search_analytics',
        # Primary key
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),

        # Query details
        sa.Column('query', sa.String(500), nullable=False),
        sa.Column('search_type', sa.String(20), nullable=False),
        sa.Column('query_length', sa.Integer, nullable=True),

        # Filter tracking
        sa.Column('filters_used', postgresql.JSONB, server_default='{}'),
        sa.Column('has_document_type_filter', sa.Boolean, default=False),
        sa.Column('has_date_filter', sa.Boolean, default=False),
        sa.Column('has_tag_filter', sa.Boolean, default=False),
        sa.Column('has_status_filter', sa.Boolean, default=False),

        # Results
        sa.Column('total_results', sa.Integer, default=0),
        sa.Column('results_returned', sa.Integer, default=0),
        sa.Column('page_number', sa.Integer, default=1),

        # Performance metrics
        sa.Column('execution_time_ms', sa.Integer, nullable=True),
        sa.Column('fts_time_ms', sa.Integer, nullable=True),
        sa.Column('semantic_time_ms', sa.Integer, nullable=True),

        # User engagement
        sa.Column('clicked_results', sa.Integer, default=0),
        sa.Column('first_click_position', sa.Integer, nullable=True),
        sa.Column('downloaded_count', sa.Integer, default=0),

        # Session tracking
        sa.Column('session_id', sa.String(100), nullable=True),
        sa.Column('is_refinement', sa.Boolean, default=False),
        sa.Column('previous_query_id', postgresql.UUID(as_uuid=True), nullable=True),

        # Metadata
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()')),
        sa.Column('user_agent', sa.String(255), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
    )

    # ========== Create indexes for analytics queries ==========

    # Time-based queries (most common for dashboards)
    op.create_index(
        'ix_search_analytics_created_at',
        'search_analytics',
        ['created_at']
    )

    # User-specific analytics
    op.create_index(
        'ix_search_analytics_user_id',
        'search_analytics',
        ['user_id']
    )

    # Search type distribution
    op.create_index(
        'ix_search_analytics_search_type',
        'search_analytics',
        ['search_type']
    )

    # Query pattern analysis (prefix matching)
    op.execute("""
        CREATE INDEX ix_search_analytics_query_pattern
        ON search_analytics (query varchar_pattern_ops);
    """)

    # Compound index for time-range + search type analytics
    op.create_index(
        'ix_search_analytics_time_type',
        'search_analytics',
        ['created_at', 'search_type']
    )

    # Session-based analysis
    op.create_index(
        'ix_search_analytics_session',
        'search_analytics',
        ['session_id'],
        postgresql_where=sa.text('session_id IS NOT NULL')
    )

    # ========== Create materialized view for daily statistics ==========
    # WICHTIG: Separate op.execute() calls - PostgreSQL erlaubt keine multiple commands in prepared statements
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS search_analytics_daily AS
        SELECT
            DATE_TRUNC('day', created_at) as date,
            search_type,
            COUNT(*) as total_searches,
            COUNT(DISTINCT user_id) as unique_users,
            AVG(total_results)::INTEGER as avg_results,
            AVG(execution_time_ms)::INTEGER as avg_execution_time_ms,
            AVG(clicked_results)::FLOAT as avg_clicks_per_search,
            SUM(CASE WHEN total_results = 0 THEN 1 ELSE 0 END) as zero_result_searches,
            SUM(CASE WHEN has_document_type_filter THEN 1 ELSE 0 END) as searches_with_type_filter,
            SUM(CASE WHEN has_tag_filter THEN 1 ELSE 0 END) as searches_with_tag_filter,
            SUM(CASE WHEN has_date_filter THEN 1 ELSE 0 END) as searches_with_date_filter
        FROM search_analytics
        GROUP BY DATE_TRUNC('day', created_at), search_type
        ORDER BY date DESC, search_type
    """)
    op.execute("CREATE UNIQUE INDEX ON search_analytics_daily (date, search_type)")

    # ========== Create function to refresh materialized view ==========
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_search_analytics_daily()
        RETURNS void AS $$
        BEGIN
            REFRESH MATERIALIZED VIEW CONCURRENTLY search_analytics_daily;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # ========== Drop function ==========
    op.execute("DROP FUNCTION IF EXISTS refresh_search_analytics_daily;")

    # ========== Drop materialized view ==========
    op.execute("DROP MATERIALIZED VIEW IF EXISTS search_analytics_daily;")

    # ========== Drop indexes ==========
    op.drop_index('ix_search_analytics_session')
    op.drop_index('ix_search_analytics_time_type')
    op.execute("DROP INDEX IF EXISTS ix_search_analytics_query_pattern;")
    op.drop_index('ix_search_analytics_search_type')
    op.drop_index('ix_search_analytics_user_id')
    op.drop_index('ix_search_analytics_created_at')

    # ========== Drop table ==========
    op.drop_table('search_analytics')
