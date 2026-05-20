"""Add enterprise intelligence tables for Phase 4.

Revision ID: 082_add_enterprise_intelligence_tables
Revises: 081_add_privat_module_kpi_fields
Create Date: 2026-01-09

Enterprise Features:
- LLM Cache mit semantischer Aehnlichkeit fuer schnellere Antworten
- Recurring Payments fuer automatische Zahlungserkennung
- Coverage Gaps fuer Versicherungsluecken-Analyse
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '082'
down_revision = '081'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # LLM Cache - Semantisches Caching fuer LLM-Antworten
    # ==================================================

    op.create_table(
        'llm_cache',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('prompt_hash', sa.String(64), nullable=False, unique=True,
                  comment='SHA-256 Hash des normalisierten Prompts'),
        sa.Column('prompt_text', sa.Text(), nullable=False,
                  comment='Originaler Prompt-Text'),
        sa.Column('prompt_embedding', sa.dialects.postgresql.ARRAY(sa.Float()),
                  nullable=True, comment='Embedding-Vektor fuer semantische Suche (384 dim)'),
        sa.Column('response', sa.Text(), nullable=False,
                  comment='LLM-Antwort'),
        sa.Column('model', sa.String(50), nullable=False,
                  comment='Verwendetes Modell (z.B. qwen3:8b)'),
        sa.Column('model_version', sa.String(50), nullable=True,
                  comment='Modell-Version'),
        sa.Column('temperature', sa.Numeric(3, 2), nullable=True,
                  comment='Verwendete Temperature'),
        sa.Column('hit_count', sa.Integer(), nullable=False, server_default='0',
                  comment='Anzahl Cache-Hits'),
        sa.Column('last_hit_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt des letzten Hits'),
        sa.Column('token_count_prompt', sa.Integer(), nullable=True,
                  comment='Token-Anzahl im Prompt'),
        sa.Column('token_count_response', sa.Integer(), nullable=True,
                  comment='Token-Anzahl in der Antwort'),
        sa.Column('latency_ms', sa.Integer(), nullable=True,
                  comment='Original-Antwortzeit in Millisekunden'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Ablaufzeitpunkt (NULL = nie)'),
        sa.Column('extra_data', JSONB, nullable=True,
                  comment='Zusaetzliche Metadaten'),
    )

    # Indexes fuer LLM Cache
    op.create_index('ix_llm_cache_prompt_hash', 'llm_cache', ['prompt_hash'])
    op.create_index('ix_llm_cache_model', 'llm_cache', ['model'])
    op.create_index('ix_llm_cache_created_at', 'llm_cache', ['created_at'])
    op.create_index('ix_llm_cache_expires_at', 'llm_cache', ['expires_at'],
                    postgresql_where=sa.text('expires_at IS NOT NULL'))
    op.create_index('ix_llm_cache_hit_count', 'llm_cache', ['hit_count'])

    # ==================================================
    # Privat Recurring Payments - Erkannte wiederkehrende Zahlungen
    # ==================================================

    op.create_table(
        'privat_recurring_payments',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('space_id', UUID(as_uuid=True), nullable=False,
                  comment='Referenz auf privat_spaces'),
        sa.Column('name', sa.String(255), nullable=False,
                  comment='Name der Zahlung (z.B. Netflix, Miete)'),
        sa.Column('payee', sa.String(255), nullable=True,
                  comment='Zahlungsempfaenger'),
        sa.Column('expected_amount', sa.Numeric(10, 2), nullable=False,
                  comment='Erwarteter Betrag'),
        sa.Column('amount_variance', sa.Numeric(10, 2), nullable=True,
                  comment='Tolerierte Abweichung'),
        sa.Column('frequency', sa.String(20), nullable=False,
                  comment='Haeufigkeit: daily, weekly, monthly, quarterly, yearly'),
        sa.Column('expected_day', sa.Integer(), nullable=True,
                  comment='Erwarteter Tag im Zyklus (1-31 fuer monatlich)'),
        sa.Column('category', sa.String(50), nullable=True,
                  comment='Kategorie: subscription, utility, rent, insurance, etc.'),
        sa.Column('last_occurrence', sa.Date(), nullable=True,
                  comment='Letztes Auftreten'),
        sa.Column('next_expected', sa.Date(), nullable=True,
                  comment='Naechstes erwartetes Datum'),
        sa.Column('occurrence_count', sa.Integer(), nullable=False, server_default='0',
                  comment='Anzahl Vorkommen'),
        sa.Column('confidence', sa.Numeric(3, 2), nullable=False, server_default='0.0',
                  comment='Erkennungs-Konfidenz 0-1'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true',
                  comment='Ist die Zahlung noch aktiv?'),
        sa.Column('is_income', sa.Boolean(), nullable=False, server_default='false',
                  comment='Ist es eine Einnahme (nicht Ausgabe)?'),
        sa.Column('linked_account_id', UUID(as_uuid=True), nullable=True,
                  comment='Verknuepftes Bankkonto'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('extra_data', JSONB, nullable=True,
                  comment='Zusaetzliche Metadaten'),
    )

    # Foreign key zu privat_spaces
    op.create_foreign_key(
        'fk_recurring_payments_space',
        'privat_recurring_payments', 'privat_spaces',
        ['space_id'], ['id'],
        ondelete='CASCADE'
    )

    # Indexes fuer Recurring Payments
    op.create_index('ix_recurring_payments_space_id', 'privat_recurring_payments', ['space_id'])
    op.create_index('ix_recurring_payments_frequency', 'privat_recurring_payments', ['frequency'])
    op.create_index('ix_recurring_payments_next_expected', 'privat_recurring_payments',
                    ['next_expected'], postgresql_where=sa.text('is_active = true'))
    op.create_index('ix_recurring_payments_category', 'privat_recurring_payments', ['category'])
    op.create_index('ix_recurring_payments_confidence', 'privat_recurring_payments', ['confidence'])

    # ==================================================
    # Privat Coverage Gaps - Versicherungsluecken
    # ==================================================

    op.create_table(
        'privat_coverage_gaps',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('space_id', UUID(as_uuid=True), nullable=False,
                  comment='Referenz auf privat_spaces'),
        sa.Column('insurance_id', UUID(as_uuid=True), nullable=True,
                  comment='Referenz auf privat_insurances (NULL = fehlende Versicherung)'),
        sa.Column('insurance_type', sa.String(50), nullable=False,
                  comment='Versicherungstyp: liability, household, legal, health, etc.'),
        sa.Column('gap_type', sa.String(50), nullable=False,
                  comment='Lueckentyp: missing, undercovered, expired, overlapping'),
        sa.Column('recommended_coverage', sa.Numeric(15, 2), nullable=True,
                  comment='Empfohlene Deckungssumme'),
        sa.Column('current_coverage', sa.Numeric(15, 2), nullable=True,
                  comment='Aktuelle Deckungssumme (NULL wenn fehlend)'),
        sa.Column('gap_amount', sa.Numeric(15, 2), nullable=True,
                  comment='Differenz zur Empfehlung'),
        sa.Column('severity', sa.String(20), nullable=False,
                  comment='Schweregrad: low, medium, high, critical'),
        sa.Column('risk_description', sa.Text(), nullable=True,
                  comment='Beschreibung des Risikos'),
        sa.Column('recommendation', sa.Text(), nullable=True,
                  comment='Handlungsempfehlung'),
        sa.Column('estimated_monthly_cost', sa.Numeric(10, 2), nullable=True,
                  comment='Geschaetzte Monatskosten fuer Behebung'),
        sa.Column('priority_score', sa.Integer(), nullable=True,
                  comment='Prioritaets-Score 1-100'),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false',
                  comment='Wurde die Luecke behoben?'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Zeitpunkt der Behebung'),
        sa.Column('last_analysis_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()'),
                  comment='Zeitpunkt der letzten Analyse'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('extra_data', JSONB, nullable=True,
                  comment='Zusaetzliche Metadaten'),
    )

    # Foreign keys
    op.create_foreign_key(
        'fk_coverage_gaps_space',
        'privat_coverage_gaps', 'privat_spaces',
        ['space_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_coverage_gaps_insurance',
        'privat_coverage_gaps', 'privat_insurances',
        ['insurance_id'], ['id'],
        ondelete='SET NULL'
    )

    # Indexes fuer Coverage Gaps
    op.create_index('ix_coverage_gaps_space_id', 'privat_coverage_gaps', ['space_id'])
    op.create_index('ix_coverage_gaps_insurance_type', 'privat_coverage_gaps', ['insurance_type'])
    op.create_index('ix_coverage_gaps_severity', 'privat_coverage_gaps', ['severity'])
    op.create_index('ix_coverage_gaps_unresolved', 'privat_coverage_gaps',
                    ['space_id', 'severity'],
                    postgresql_where=sa.text('is_resolved = false'))
    op.create_index('ix_coverage_gaps_priority', 'privat_coverage_gaps', ['priority_score'],
                    postgresql_where=sa.text('is_resolved = false'))

    # ==================================================
    # Event Log - Fuer Event Bus Historie
    # ==================================================

    op.create_table(
        'event_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', UUID(as_uuid=True), nullable=False, unique=True,
                  comment='Eindeutige Event-ID'),
        sa.Column('event_type', sa.String(100), nullable=False,
                  comment='Event-Typ (z.B. document.ocr_completed)'),
        sa.Column('source', sa.String(100), nullable=False,
                  comment='Quelle des Events'),
        sa.Column('correlation_id', UUID(as_uuid=True), nullable=True,
                  comment='Korrelations-ID fuer zusammengehoerige Events'),
        sa.Column('user_id', UUID(as_uuid=True), nullable=True,
                  comment='Benutzer-ID'),
        sa.Column('space_id', UUID(as_uuid=True), nullable=True,
                  comment='Privat-Space-ID'),
        sa.Column('payload', JSONB, nullable=False,
                  comment='Event-Payload als JSON'),
        sa.Column('processed', sa.Boolean(), nullable=False, server_default='false',
                  comment='Wurde das Event verarbeitet?'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True,
                  comment='Verarbeitungszeitpunkt'),
        sa.Column('handler_count', sa.Integer(), nullable=False, server_default='0',
                  comment='Anzahl der Handler die es verarbeitet haben'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
    )

    # Indexes fuer Event Log
    op.create_index('ix_event_log_event_id', 'event_log', ['event_id'])
    op.create_index('ix_event_log_event_type', 'event_log', ['event_type'])
    op.create_index('ix_event_log_source', 'event_log', ['source'])
    op.create_index('ix_event_log_correlation_id', 'event_log', ['correlation_id'],
                    postgresql_where=sa.text('correlation_id IS NOT NULL'))
    op.create_index('ix_event_log_user_id', 'event_log', ['user_id'],
                    postgresql_where=sa.text('user_id IS NOT NULL'))
    op.create_index('ix_event_log_space_id', 'event_log', ['space_id'],
                    postgresql_where=sa.text('space_id IS NOT NULL'))
    op.create_index('ix_event_log_created_at', 'event_log', ['created_at'])
    op.create_index('ix_event_log_unprocessed', 'event_log', ['event_type', 'created_at'],
                    postgresql_where=sa.text('processed = false'))

    # Partitionierung nach created_at fuer grosse Event-Logs (Kommentar)
    # In Produktion sollte diese Tabelle partitioniert werden:
    # PARTITION BY RANGE (created_at)


def downgrade() -> None:
    # ==================================================
    # Drop Event Log
    # ==================================================

    op.drop_index('ix_event_log_unprocessed', table_name='event_log')
    op.drop_index('ix_event_log_created_at', table_name='event_log')
    op.drop_index('ix_event_log_space_id', table_name='event_log')
    op.drop_index('ix_event_log_user_id', table_name='event_log')
    op.drop_index('ix_event_log_correlation_id', table_name='event_log')
    op.drop_index('ix_event_log_source', table_name='event_log')
    op.drop_index('ix_event_log_event_type', table_name='event_log')
    op.drop_index('ix_event_log_event_id', table_name='event_log')
    op.drop_table('event_log')

    # ==================================================
    # Drop Coverage Gaps
    # ==================================================

    op.drop_index('ix_coverage_gaps_priority', table_name='privat_coverage_gaps')
    op.drop_index('ix_coverage_gaps_unresolved', table_name='privat_coverage_gaps')
    op.drop_index('ix_coverage_gaps_severity', table_name='privat_coverage_gaps')
    op.drop_index('ix_coverage_gaps_insurance_type', table_name='privat_coverage_gaps')
    op.drop_index('ix_coverage_gaps_space_id', table_name='privat_coverage_gaps')
    op.drop_constraint('fk_coverage_gaps_insurance', 'privat_coverage_gaps', type_='foreignkey')
    op.drop_constraint('fk_coverage_gaps_space', 'privat_coverage_gaps', type_='foreignkey')
    op.drop_table('privat_coverage_gaps')

    # ==================================================
    # Drop Recurring Payments
    # ==================================================

    op.drop_index('ix_recurring_payments_confidence', table_name='privat_recurring_payments')
    op.drop_index('ix_recurring_payments_category', table_name='privat_recurring_payments')
    op.drop_index('ix_recurring_payments_next_expected', table_name='privat_recurring_payments')
    op.drop_index('ix_recurring_payments_frequency', table_name='privat_recurring_payments')
    op.drop_index('ix_recurring_payments_space_id', table_name='privat_recurring_payments')
    op.drop_constraint('fk_recurring_payments_space', 'privat_recurring_payments', type_='foreignkey')
    op.drop_table('privat_recurring_payments')

    # ==================================================
    # Drop LLM Cache
    # ==================================================

    op.drop_index('ix_llm_cache_hit_count', table_name='llm_cache')
    op.drop_index('ix_llm_cache_expires_at', table_name='llm_cache')
    op.drop_index('ix_llm_cache_created_at', table_name='llm_cache')
    op.drop_index('ix_llm_cache_model', table_name='llm_cache')
    op.drop_index('ix_llm_cache_prompt_hash', table_name='llm_cache')
    op.drop_table('llm_cache')
