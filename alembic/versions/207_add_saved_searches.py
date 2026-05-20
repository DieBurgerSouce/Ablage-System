"""Add Saved Searches.

Revision ID: 207_add_saved_searches
Revises: 206_add_gl_posting_system
Create Date: 2026-02-08

Features:
- saved_searches table for user-specific search templates
- Filter persistence
- Usage statistics (use_count, last_used_at)
- Unique constraint on (user_id, name)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '207_add_saved_searches'
down_revision: str = '206_add_gl_posting_system'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add saved_searches table."""
    op.create_table(
        'saved_searches',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False, comment='Besitzer der gespeicherten Suche'),
        sa.Column('name', sa.String(length=200), nullable=False, comment='Benutzer-definierter Name fuer die Suche'),
        sa.Column('query', sa.Text(), nullable=False, comment='Der Suchbegriff / Query String'),
        sa.Column('search_type', sa.String(length=20), nullable=False, server_default='hybrid', comment='Suchtyp: fts, semantic, hybrid'),
        sa.Column('filters', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='Gespeicherter Filter-Zustand (document_type, status, date_range, etc.)'),
        sa.Column('sort_field', sa.String(length=50), nullable=True, comment='Sortierfeld (created_at, relevance, etc.)'),
        sa.Column('sort_order', sa.String(length=4), nullable=True, comment='Sortierreihenfolge: asc oder desc'),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false'), comment='Ist dies die Standard-Suche des Benutzers?'),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default=sa.text('0'), comment='Anzahl der Ausfuehrungen dieser Suche'),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True, comment='Zeitpunkt der letzten Ausfuehrung'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Erstellungszeitpunkt'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='Letzte Aenderung'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_saved_searches_user_name')
    )
    op.create_index('ix_saved_searches_user_id', 'saved_searches', ['user_id'], unique=False)


def downgrade() -> None:
    """Remove saved_searches table."""
    op.drop_index('ix_saved_searches_user_id', table_name='saved_searches')
    op.drop_table('saved_searches')
