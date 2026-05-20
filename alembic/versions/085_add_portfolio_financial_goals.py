"""Add Portfolio Snapshots and Financial Goals tables.

Revision ID: 085_add_portfolio_financial_goals
Revises: 084_add_predictive_intelligence_tables
Create Date: 2026-01-09

Enterprise Features - PORTFOLIO INTELLIGENCE:
- Portfolio Snapshots: Monatliche Vermoegensueberblicke fuer historische Analyse
- Financial Goals: Sparziele mit Progress-Tracking und Prognosen
- Goal Contributions: Beitraege zu finanziellen Zielen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '085'
down_revision = '084'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # Portfolio Snapshots - Monatliche Vermoegensueberblicke
    # ==================================================
    # Speichert aggregierte Vermoegensstaende zu bestimmten Zeitpunkten
    # fuer historische Analyse und Reporting

    op.create_table(
        'portfolio_snapshots',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('space_id', UUID(as_uuid=True),
                  sa.ForeignKey('privat_spaces.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False,
                  comment='Datum des Snapshots'),

        # Vermoegenswerte (Assets)
        sa.Column('total_real_estate', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Gesamtwert Immobilien'),
        sa.Column('total_vehicles', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Gesamtwert Fahrzeuge'),
        sa.Column('total_investments', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Gesamtwert Investments (Aktien, ETFs, Fonds)'),
        sa.Column('total_cash', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Barvermoegen und Bankguthaben'),
        sa.Column('total_other_assets', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Sonstige Vermoegenswerte'),

        # Verbindlichkeiten (Liabilities)
        sa.Column('total_mortgages', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Hypotheken und Immobilienkredite'),
        sa.Column('total_loans', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Sonstige Kredite (Auto, Konsum)'),
        sa.Column('total_other_liabilities', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Sonstige Verbindlichkeiten'),

        # Aggregierte Werte
        sa.Column('total_assets', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Summe aller Vermoegenswerte'),
        sa.Column('total_liabilities', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Summe aller Verbindlichkeiten'),
        sa.Column('net_worth', sa.Numeric(14, 2), nullable=False,
                  server_default='0', comment='Nettovermoegen (Assets - Liabilities)'),

        # Veraenderungen zum Vormonat
        sa.Column('net_worth_change_absolute', sa.Numeric(14, 2), nullable=True,
                  comment='Absolute Aenderung zum Vormonat in EUR'),
        sa.Column('net_worth_change_percent', sa.Numeric(8, 4), nullable=True,
                  comment='Prozentuale Aenderung zum Vormonat'),

        # Kennzahlen
        sa.Column('debt_to_assets_ratio', sa.Numeric(8, 4), nullable=False,
                  server_default='0', comment='Verschuldungsgrad (Liabilities/Assets)'),
        sa.Column('liquidity_ratio', sa.Numeric(8, 4), nullable=False,
                  server_default='0', comment='Liquiditaetsquote (Cash/Liabilities)'),

        # Asset Allocation als JSON
        sa.Column('asset_allocation', JSONB, nullable=True,
                  comment='Vermoegensverteilung als JSON'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),

        comment='Monatliche Vermoegenssnapshots fuer historische Analyse'
    )

    # Indices fuer Portfolio Snapshots
    op.create_index('ix_portfolio_snapshots_snapshot_date', 'portfolio_snapshots', ['snapshot_date'])
    op.create_index('ix_portfolio_snapshots_space_date', 'portfolio_snapshots',
                    ['space_id', 'snapshot_date'])

    # Unique Constraint - nur ein Snapshot pro Space und Datum
    op.create_unique_constraint('uq_portfolio_snapshot_space_date', 'portfolio_snapshots',
                                ['space_id', 'snapshot_date'])

    # ==================================================
    # Financial Goals - Sparziele mit Progress-Tracking
    # ==================================================
    # Ermoeglicht das Setzen von Sparzielen mit automatischer
    # Fortschrittsverfolgung und Prognosen

    op.create_table(
        'financial_goals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('space_id', UUID(as_uuid=True),
                  sa.ForeignKey('privat_spaces.id', ondelete='CASCADE'),
                  nullable=False),

        # Ziel-Definition
        sa.Column('name', sa.String(200), nullable=False, comment='Name des Ziels'),
        sa.Column('description', sa.Text(), nullable=True, comment='Beschreibung'),
        sa.Column('goal_type', sa.String(50), nullable=False, server_default='custom',
                  comment='Typ des Ziels (retirement, education, property, debt_free, emergency_fund, travel, vehicle, renovation, investment, custom)'),
        sa.Column('icon', sa.String(50), nullable=True, server_default='Target',
                  comment='Icon fuer UI'),
        sa.Column('color', sa.String(7), nullable=True, server_default='#10B981',
                  comment='Farbe fuer UI'),

        # Zielwerte
        sa.Column('target_value', sa.Numeric(14, 2), nullable=False,
                  comment='Zielbetrag in EUR'),
        sa.Column('target_date', sa.Date(), nullable=False,
                  comment='Zieldatum'),

        # Tracking
        sa.Column('current_value', sa.Numeric(14, 2), nullable=False, server_default='0',
                  comment='Aktueller Betrag'),
        sa.Column('progress_percent', sa.Numeric(8, 4), nullable=False, server_default='0',
                  comment='Fortschritt in Prozent (0-100)'),

        # Berechnete/Prognostizierte Werte
        sa.Column('monthly_savings_required', sa.Numeric(12, 2), nullable=True,
                  comment='Erforderliche monatliche Sparrate'),
        sa.Column('months_remaining', sa.Integer(), nullable=True,
                  comment='Verbleibende Monate bis Zieldatum'),
        sa.Column('is_on_track', sa.Boolean(), nullable=False, server_default='true',
                  comment='Liegt das Ziel im Plan?'),
        sa.Column('projected_completion_date', sa.Date(), nullable=True,
                  comment='Prognostiziertes Erreichen basierend auf aktuellem Tempo'),

        # Verknuepfte Assets (optional)
        sa.Column('linked_assets', JSONB, nullable=True,
                  comment='Verknuepfte Assets als JSON'),

        # Status und Prioritaet
        sa.Column('status', sa.String(20), nullable=False, server_default='active',
                  comment='Status (active, paused, completed, cancelled)'),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='1',
                  comment='Prioritaet (1=hoechste)'),

        # Automatische Aktualisierung
        sa.Column('auto_update_enabled', sa.Boolean(), nullable=False, server_default='true',
                  comment='Automatische Fortschrittsaktualisierung?'),
        sa.Column('last_auto_update', sa.DateTime(timezone=True), nullable=True,
                  comment='Letzte automatische Aktualisierung'),

        # Benachrichtigungen
        sa.Column('notify_on_milestone', sa.Boolean(), nullable=False, server_default='true',
                  comment='Benachrichtigung bei Meilensteinen?'),
        sa.Column('notify_on_delay', sa.Boolean(), nullable=False, server_default='true',
                  comment='Benachrichtigung bei Verzoegerung?'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der Zielerreichung'),

        comment='Finanzielle Ziele mit Progress-Tracking'
    )

    # Indices fuer Financial Goals
    op.create_index('ix_financial_goals_space', 'financial_goals', ['space_id'])
    op.create_index('ix_financial_goals_status', 'financial_goals', ['status'])
    op.create_index('ix_financial_goals_target_date', 'financial_goals', ['target_date'])
    op.create_index('ix_financial_goals_on_track', 'financial_goals', ['is_on_track'],
                    postgresql_where=sa.text("status = 'active'"))

    # ==================================================
    # Financial Goal Contributions - Beitraege zu Zielen
    # ==================================================
    # Trackt individuelle Beitraege zum Fortschritt eines Ziels

    op.create_table(
        'financial_goal_contributions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('goal_id', UUID(as_uuid=True),
                  sa.ForeignKey('financial_goals.id', ondelete='CASCADE'),
                  nullable=False),

        # Beitrag
        sa.Column('amount', sa.Numeric(14, 2), nullable=False,
                  comment='Beitragsbetrag in EUR'),
        sa.Column('contribution_date', sa.Date(), nullable=False,
                  server_default=sa.text('CURRENT_DATE'),
                  comment='Datum des Beitrags'),

        # Quelle
        sa.Column('source_type', sa.String(50), nullable=True,
                  comment='Quelle (manual, automatic, transfer)'),
        sa.Column('source_description', sa.String(255), nullable=True,
                  comment='Beschreibung der Quelle'),

        # Verknuepfte Transaktion (optional)
        sa.Column('linked_transaction_id', UUID(as_uuid=True), nullable=True,
                  comment='Verknuepfte Transaktion falls automatisch'),

        # Audit
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('created_by_id', UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),

        # Notes
        sa.Column('note', sa.Text(), nullable=True, comment='Optionale Notiz'),

        comment='Beitraege zu finanziellen Zielen'
    )

    # Indices fuer Goal Contributions
    op.create_index('ix_goal_contributions_goal', 'financial_goal_contributions', ['goal_id'])
    op.create_index('ix_goal_contributions_date', 'financial_goal_contributions',
                    ['contribution_date'])


def downgrade() -> None:
    # Drop tables in reverse order (dependencies first)
    op.drop_table('financial_goal_contributions')
    op.drop_table('financial_goals')
    op.drop_table('portfolio_snapshots')
