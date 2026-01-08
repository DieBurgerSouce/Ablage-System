# -*- coding: utf-8 -*-
"""
Add Position-Weighted Click Analytics to SearchAnalytics.

Revision ID: 050_add_position_weighted_analytics
Revises: 049_fix_banking_numeric_types
Create Date: 2025-12-17

Diese Migration fuegt zwei neue Felder hinzu fuer Position-Weighted Click Analytics:

1. weighted_click_score (Float): Kumulierter gewichteter Klick-Score
   - Verwendet exponentiellen Decay basierend auf Klick-Position
   - Position 1 = 1.0, Position 5 = 0.55, Position 10 = 0.26
   - Formel: exp(-0.15 * (position - 1))

2. click_positions (JSONB): Liste aller Klick-Positionen
   - Ermoeglicht detaillierte Analyse des Klickverhaltens
   - Beispiel: [1, 3, 5] = Klicks auf Position 1, 3 und 5

Diese Metriken ermoeglichen:
- Weighted CTR (Click-Through Rate) Berechnung
- Bessere Bewertung der Suchqualitaet (Klicks auf Position 1 wertvoller)
- Identifikation von Queries mit schlechtem Ranking
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add position-weighted click analytics columns."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # weighted_click_score: Kumulierter gewichteter Score
    op.add_column(
        'search_analytics',
        sa.Column(
            'weighted_click_score',
            sa.Float(),
            nullable=True,
            server_default='0.0'
        )
    )

    # click_positions: Liste der Klick-Positionen (JSONB fuer Postgres, JSON fuer SQLite)
    if is_postgres:
        op.add_column(
            'search_analytics',
            sa.Column(
                'click_positions',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
                server_default='[]'
            )
        )
    else:
        op.add_column(
            'search_analytics',
            sa.Column(
                'click_positions',
                sa.JSON(),
                nullable=True,
                server_default='[]'
            )
        )

    # Index fuer Abfragen nach weighted_click_score (z.B. Top-Queries)
    op.create_index(
        'ix_search_analytics_weighted_score',
        'search_analytics',
        ['weighted_click_score'],
        postgresql_where=sa.text('weighted_click_score > 0')
    )

    # Setze Default-Werte fuer bestehende Datensaetze
    # weighted_click_score bleibt 0 (keine historischen Positionsdaten)
    # click_positions wird leeres Array
    if is_postgres:
        op.execute("""
            UPDATE search_analytics
            SET weighted_click_score = 0.0,
                click_positions = '[]'::jsonb
            WHERE weighted_click_score IS NULL
        """)


def downgrade() -> None:
    """Remove position-weighted click analytics columns."""
    # Index entfernen
    op.drop_index('ix_search_analytics_weighted_score', table_name='search_analytics')

    # Spalten entfernen
    op.drop_column('search_analytics', 'click_positions')
    op.drop_column('search_analytics', 'weighted_click_score')
