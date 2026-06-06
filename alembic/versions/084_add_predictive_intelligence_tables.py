"""Add predictive intelligence tables for KPI History and Projections.

Revision ID: 084_add_predictive_intelligence_tables
Revises: 083_add_notification_rules
Create Date: 2026-01-09

Enterprise Features - PROACTIVE Intelligence:
- KPI History: Taegliche Snapshots aller KPIs fuer Trend-Analyse
- Projection Cache: Vorausberechnete KPI-Projektionen (3/6/12 Monate)
- User Thresholds: Personalisierte Schwellenwerte pro User
- Early Warnings: Proaktive Warnungen bei zukuenftigen Schwellenwertbruechen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '084'
down_revision = '083'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # KPI History - Taegliche Snapshots aller KPIs
    # ==================================================
    # Ermoeglicht Trend-Analyse und Projektionen in die Zukunft

    op.create_table(
        'privat_kpi_history',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('space_id', UUID(as_uuid=True), nullable=False,
                  comment='Referenz auf privat_spaces'),
        sa.Column('kpi_name', sa.String(100), nullable=False,
                  comment='Name des KPI (z.B. dti, financial_health_score, net_worth)'),
        sa.Column('kpi_value', sa.Numeric(15, 4), nullable=False,
                  comment='Numerischer Wert des KPI'),
        sa.Column('kpi_unit', sa.String(20), nullable=True,
                  comment='Einheit: percent, currency, ratio, score'),
        sa.Column('components', JSONB, nullable=True,
                  comment='Aufschluesselung in Komponenten (z.B. Health Score Dimensionen)'),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'),
                  comment='Zeitpunkt der Aufzeichnung'),
        sa.Column('source', sa.String(50), nullable=False, server_default='automated',
                  comment='Quelle: automated, manual, recalculated'),
        sa.Column('extra_data', JSONB, nullable=True,
                  comment='Zusaetzliche Kontextdaten'),
    )

    # Unique constraint: Ein KPI pro Space pro Tag.
    # Funktionaler Ausdruck (recorded_at::date) -> UNIQUE INDEX statt CONSTRAINT
    # (SQL-Constraints erlauben keine Ausdruecke; alembic create_unique_constraint
    # mit sa.text() wirft ArgumentError).
    # timestamptz->date ist nicht immutable (TimeZone-abhaengig); auch extract(epoch)
    # gilt als STABLE. Mit fixem UTC ist die Tagesableitung aber deterministisch ->
    # eigene IMMUTABLE-Funktion, damit der funktionale Unique-Index zulaessig ist
    # ("ein KPI pro Space pro UTC-Tag").
    op.execute(
        "CREATE OR REPLACE FUNCTION kpi_history_utc_day(ts timestamptz) RETURNS date "
        "LANGUAGE sql IMMUTABLE AS $func$ SELECT (ts AT TIME ZONE 'UTC')::date $func$"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_kpi_history_space_kpi_date "
        "ON privat_kpi_history (space_id, kpi_name, kpi_history_utc_day(recorded_at))"
    )

    # Foreign key zu privat_spaces
    op.create_foreign_key(
        'fk_kpi_history_space',
        'privat_kpi_history', 'privat_spaces',
        ['space_id'], ['id'],
        ondelete='CASCADE'
    )

    # Indexes fuer schnelle Abfragen
    op.create_index('ix_kpi_history_space_id', 'privat_kpi_history', ['space_id'])
    op.create_index('ix_kpi_history_kpi_name', 'privat_kpi_history', ['kpi_name'])
    op.create_index('ix_kpi_history_recorded_at', 'privat_kpi_history', ['recorded_at'])
    op.create_index('ix_kpi_history_space_kpi', 'privat_kpi_history',
                    ['space_id', 'kpi_name', 'recorded_at'])
    # Index fuer Trend-Abfragen (letzte N Monate) - DESC-Ausdruck via Roh-SQL
    op.execute(
        "CREATE INDEX ix_kpi_history_trend_lookup "
        "ON privat_kpi_history (space_id, kpi_name, recorded_at DESC)"
    )

    # ==================================================
    # KPI Projections Cache - Vorausberechnete Prognosen
    # ==================================================
    # Gecachte Projektionen fuer 3/6/12 Monate in die Zukunft

    op.create_table(
        'privat_projections',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('space_id', UUID(as_uuid=True), nullable=False,
                  comment='Referenz auf privat_spaces'),
        sa.Column('kpi_name', sa.String(100), nullable=False,
                  comment='Name des projizierten KPI'),
        sa.Column('projection_months', sa.Integer(), nullable=False,
                  comment='Projektionszeitraum in Monaten (3, 6, 12)'),
        sa.Column('projection_method', sa.String(50), nullable=False, server_default='linear',
                  comment='Methode: linear, exponential, seasonal, ensemble'),
        sa.Column('current_value', sa.Numeric(15, 4), nullable=False,
                  comment='Aktueller Wert zum Berechnungszeitpunkt'),
        sa.Column('projected_values', JSONB, nullable=False,
                  comment='Monatliche Projektionen: [{month: 1, value: X, confidence: 0.9}, ...]'),
        sa.Column('threshold_breaches', JSONB, nullable=True,
                  comment='Erkannte zukuenftige Schwellenwertbrueche: [{month: 3, threshold_name: "DTI_CRITICAL", severity: "WARNING"}]'),
        sa.Column('trend_direction', sa.String(20), nullable=False,
                  comment='Trendrichtung: rising, falling, stable, volatile'),
        sa.Column('trend_strength', sa.Numeric(5, 4), nullable=True,
                  comment='Trendstaerke 0-1 (R-squared der Regression)'),
        sa.Column('seasonality_detected', sa.Boolean(), nullable=False, server_default='false',
                  comment='Wurde Saisonalitaet erkannt?'),
        sa.Column('confidence_overall', sa.Numeric(3, 2), nullable=False,
                  comment='Gesamt-Konfidenz der Projektion 0-1'),
        sa.Column('data_points_used', sa.Integer(), nullable=False,
                  comment='Anzahl historischer Datenpunkte fuer Berechnung'),
        sa.Column('calculated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'),
                  comment='Zeitpunkt der Berechnung'),
        sa.Column('valid_until', sa.DateTime(timezone=True), nullable=False,
                  comment='Gueltig bis (danach neu berechnen)'),
        sa.Column('extra_data', JSONB, nullable=True,
                  comment='Zusaetzliche Metadaten'),
    )

    # Foreign key zu privat_spaces
    op.create_foreign_key(
        'fk_projections_space',
        'privat_projections', 'privat_spaces',
        ['space_id'], ['id'],
        ondelete='CASCADE'
    )

    # Unique constraint: Eine Projektion pro Space/KPI/Zeitraum
    op.create_unique_constraint(
        'uq_projections_space_kpi_months',
        'privat_projections',
        ['space_id', 'kpi_name', 'projection_months']
    )

    # Indexes
    op.create_index('ix_projections_space_id', 'privat_projections', ['space_id'])
    op.create_index('ix_projections_kpi_name', 'privat_projections', ['kpi_name'])
    op.create_index('ix_projections_valid_until', 'privat_projections', ['valid_until'])
    op.create_index('ix_projections_with_breaches', 'privat_projections',
                    ['space_id'], postgresql_where=sa.text("threshold_breaches IS NOT NULL AND threshold_breaches != '[]'::jsonb"))

    # ==================================================
    # User Thresholds - Personalisierte Schwellenwerte
    # ==================================================
    # HINWEIS (Reconcile 2026-06): `privat_user_thresholds` wird KANONISCH in
    # Migration 087_add_personalized_thresholds angelegt (Schema
    # threshold_type/default_value/current_value/...; Constraint
    # uq_user_threshold_type) - exakt so wie das ORM-Modell PrivatUserThreshold
    # und die reale DB es fuehren (verifiziert). Die hier zuvor (084) erzeugte
    # abweichende Variante (threshold_name/profession_type/
    # uq_user_thresholds_user_name) war ein Squash-Duplikat, das nie der
    # Realitaet entsprach und `alembic upgrade head` from-scratch mit
    # "relation already exists" brach. Daher hier ENTFERNT.

    # ==================================================
    # Early Warnings - Proaktive Warnungen
    # ==================================================
    # Speichert erkannte zukuenftige Probleme

    op.create_table(
        'privat_early_warnings',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('space_id', UUID(as_uuid=True), nullable=False,
                  comment='Referenz auf privat_spaces'),
        sa.Column('projection_id', UUID(as_uuid=True), nullable=True,
                  comment='Referenz auf die zugrundeliegende Projektion'),
        sa.Column('kpi_name', sa.String(100), nullable=False,
                  comment='Betroffener KPI'),
        sa.Column('warning_type', sa.String(50), nullable=False,
                  comment='Typ: threshold_breach, trend_reversal, volatility_spike, seasonal_anomaly'),
        sa.Column('severity', sa.String(20), nullable=False,
                  comment='Schweregrad: info, warning, critical'),
        sa.Column('current_value', sa.Numeric(15, 4), nullable=False,
                  comment='Aktueller Wert'),
        sa.Column('projected_value', sa.Numeric(15, 4), nullable=False,
                  comment='Projizierter Wert zum Breach-Zeitpunkt'),
        sa.Column('threshold_value', sa.Numeric(15, 4), nullable=True,
                  comment='Schwellenwert der ueberschritten wird'),
        sa.Column('threshold_name', sa.String(100), nullable=True,
                  comment='Name des Schwellenwerts'),
        sa.Column('breach_date', sa.Date(), nullable=False,
                  comment='Prognostiziertes Datum der Schwellenwert-Verletzung'),
        sa.Column('days_until_breach', sa.Integer(), nullable=False,
                  comment='Tage bis zur Verletzung'),
        sa.Column('title', sa.String(255), nullable=False,
                  comment='Titel der Warnung (deutsch)'),
        sa.Column('description', sa.Text(), nullable=True,
                  comment='Detaillierte Beschreibung'),
        sa.Column('recommendation', sa.Text(), nullable=True,
                  comment='Handlungsempfehlung'),
        sa.Column('potential_impact', sa.Numeric(15, 2), nullable=True,
                  comment='Geschaetzter finanzieller Impact'),
        sa.Column('action_url', sa.String(255), nullable=True,
                  comment='Link zur entsprechenden Aktion'),
        sa.Column('confidence', sa.Numeric(3, 2), nullable=False,
                  comment='Konfidenz der Warnung 0-1'),
        sa.Column('is_dismissed', sa.Boolean(), nullable=False, server_default='false',
                  comment='Wurde die Warnung verworfen?'),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_reason', sa.Text(), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false',
                  comment='Wurde das Problem behoben?'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Warnung verfaellt (z.B. wenn Breach-Datum erreicht)'),
        sa.Column('extra_data', JSONB, nullable=True,
                  comment='Zusaetzliche Metadaten'),
    )

    # Foreign keys
    op.create_foreign_key(
        'fk_early_warnings_space',
        'privat_early_warnings', 'privat_spaces',
        ['space_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_early_warnings_projection',
        'privat_early_warnings', 'privat_projections',
        ['projection_id'], ['id'],
        ondelete='SET NULL'
    )

    # Indexes
    op.create_index('ix_early_warnings_space_id', 'privat_early_warnings', ['space_id'])
    op.create_index('ix_early_warnings_kpi_name', 'privat_early_warnings', ['kpi_name'])
    op.create_index('ix_early_warnings_severity', 'privat_early_warnings', ['severity'])
    op.create_index('ix_early_warnings_breach_date', 'privat_early_warnings', ['breach_date'])
    op.create_index('ix_early_warnings_active', 'privat_early_warnings',
                    ['space_id', 'severity', 'breach_date'],
                    postgresql_where=sa.text('is_dismissed = false AND is_resolved = false'))
    op.create_index('ix_early_warnings_days_until', 'privat_early_warnings',
                    ['days_until_breach'],
                    postgresql_where=sa.text('is_dismissed = false AND is_resolved = false'))

    # ==================================================
    # AI Decisions - Explanation Column hinzufuegen
    # ==================================================
    # Fuer Decision Explainability (Phase 3)

    # Idempotent: explanation/what_if_data koennen von einer frueheren Migration
    # bereits existieren (from-scratch-Inkonsistenz -> DuplicateColumnError).
    op.execute("ALTER TABLE ai_decisions ADD COLUMN IF NOT EXISTS explanation JSONB")
    op.execute(
        "COMMENT ON COLUMN ai_decisions.explanation IS "
        "'Strukturierte Erklaerung: {factors: [...], main_reason: ..., confidence_source: ...}'"
    )
    op.execute("ALTER TABLE ai_decisions ADD COLUMN IF NOT EXISTS what_if_data JSONB")
    op.execute(
        "COMMENT ON COLUMN ai_decisions.what_if_data IS "
        "'What-If Simulationsdaten fuer die Entscheidung'"
    )


def downgrade() -> None:
    # ==================================================
    # Remove AI Decisions columns
    # ==================================================
    op.drop_column('ai_decisions', 'what_if_data')
    op.drop_column('ai_decisions', 'explanation')

    # ==================================================
    # Drop Early Warnings
    # ==================================================
    op.drop_index('ix_early_warnings_days_until', table_name='privat_early_warnings')
    op.drop_index('ix_early_warnings_active', table_name='privat_early_warnings')
    op.drop_index('ix_early_warnings_breach_date', table_name='privat_early_warnings')
    op.drop_index('ix_early_warnings_severity', table_name='privat_early_warnings')
    op.drop_index('ix_early_warnings_kpi_name', table_name='privat_early_warnings')
    op.drop_index('ix_early_warnings_space_id', table_name='privat_early_warnings')
    op.drop_constraint('fk_early_warnings_projection', 'privat_early_warnings', type_='foreignkey')
    op.drop_constraint('fk_early_warnings_space', 'privat_early_warnings', type_='foreignkey')
    op.drop_table('privat_early_warnings')

    # ==================================================
    # Drop User Thresholds
    # ==================================================
    # `privat_user_thresholds` gehoert kanonisch zu Migration 087 (siehe upgrade);
    # hier nichts zu droppen.

    # ==================================================
    # Drop Projections
    # ==================================================
    op.drop_index('ix_projections_with_breaches', table_name='privat_projections')
    op.drop_index('ix_projections_valid_until', table_name='privat_projections')
    op.drop_index('ix_projections_kpi_name', table_name='privat_projections')
    op.drop_index('ix_projections_space_id', table_name='privat_projections')
    op.drop_constraint('uq_projections_space_kpi_months', 'privat_projections', type_='unique')
    op.drop_constraint('fk_projections_space', 'privat_projections', type_='foreignkey')
    op.drop_table('privat_projections')

    # ==================================================
    # Drop KPI History
    # ==================================================
    op.drop_index('ix_kpi_history_trend_lookup', table_name='privat_kpi_history')
    op.drop_index('ix_kpi_history_space_kpi', table_name='privat_kpi_history')
    op.drop_index('ix_kpi_history_recorded_at', table_name='privat_kpi_history')
    op.drop_index('ix_kpi_history_kpi_name', table_name='privat_kpi_history')
    op.drop_index('ix_kpi_history_space_id', table_name='privat_kpi_history')
    op.drop_constraint('fk_kpi_history_space', 'privat_kpi_history', type_='foreignkey')
    # War frueher ein Unique-Constraint, ist jetzt ein funktionaler Unique-Index
    op.drop_index('uq_kpi_history_space_kpi_date', table_name='privat_kpi_history')
    op.drop_table('privat_kpi_history')
    op.execute("DROP FUNCTION IF EXISTS kpi_history_utc_day(timestamptz)")
