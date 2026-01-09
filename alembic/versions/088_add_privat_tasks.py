"""Add privat_tasks table for orchestrator-generated tasks.

Revision ID: 088_add_privat_tasks
Revises: 087_add_personalized_thresholds
Create Date: 2026-01-09

Enterprise Feature - CrossModuleOrchestrator Tasks:
- Generische Tasks die vom Orchestrator erstellt werden
- Verknuepfung zu Source-Actions
- Status-Tracking mit Snooze-Funktion
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers
revision = '088'
down_revision = '087'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==================================================
    # PrivatTask - Orchestrator-generierte Tasks
    # ==================================================

    op.create_table(
        'privat_tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),

        # Referenzen
        sa.Column('space_id', UUID(as_uuid=True), nullable=False,
                  comment='Referenz auf privat_spaces'),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False,
                  comment='Zugewiesener Benutzer'),

        # Task-Identifikation
        sa.Column('task_type', sa.String(50), nullable=False,
                  comment='Typ: review, action, follow_up, reminder, approval'),
        sa.Column('title', sa.String(255), nullable=False,
                  comment='Kurzer Titel der Aufgabe'),
        sa.Column('description', sa.Text, nullable=True,
                  comment='Ausfuehrliche Beschreibung'),
        sa.Column('category', sa.String(50), nullable=True,
                  comment='Kategorie: financial, insurance, property, loan, general'),

        # Prioritaet und Dringlichkeit
        sa.Column('priority', sa.String(20), nullable=False, server_default='medium',
                  comment='Prioritaet: low, medium, high, critical'),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True,
                  comment='Faelligkeitsdatum'),

        # Herkunft aus Orchestration
        sa.Column('source_action_id', UUID(as_uuid=True), nullable=True,
                  comment='ID der ausloesenden OrchestrationAction'),
        sa.Column('source_reason', sa.Text, nullable=True,
                  comment='Grund fuer Task-Erstellung'),
        sa.Column('source_module', sa.String(50), nullable=True,
                  comment='Ausloesendes Modul: financial_health, insurance, loan, etc.'),

        # Status-Tracking
        sa.Column('status', sa.String(30), nullable=False, server_default='pending',
                  comment='Status: pending, in_progress, completed, cancelled, snoozed'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_reason', sa.Text, nullable=True),

        # Snooze-Funktion
        sa.Column('snoozed_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('snooze_count', sa.Integer, server_default='0'),
        sa.Column('snooze_reason', sa.String(255), nullable=True),

        # Ergebnis
        sa.Column('result_notes', sa.Text, nullable=True,
                  comment='Notizen nach Abschluss'),
        sa.Column('result_action_taken', sa.String(100), nullable=True,
                  comment='Getroffene Massnahme'),

        # Verknuepfte Entitaeten
        sa.Column('related_entity_type', sa.String(50), nullable=True,
                  comment='Typ der verknuepften Entitaet: property, loan, insurance'),
        sa.Column('related_entity_id', UUID(as_uuid=True), nullable=True,
                  comment='ID der verknuepften Entitaet'),

        # Metadaten
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('NOW()')),
        sa.Column('extra_data', JSONB, nullable=True,
                  comment='Zusaetzliche Metadaten vom Orchestrator'),
    )

    # Foreign Keys
    op.create_foreign_key(
        'fk_privat_tasks_space',
        'privat_tasks', 'privat_spaces',
        ['space_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_privat_tasks_user',
        'privat_tasks', 'users',
        ['user_id'], ['id'],
        ondelete='CASCADE'
    )

    # Indexes
    op.create_index('ix_privat_tasks_space_id', 'privat_tasks', ['space_id'])
    op.create_index('ix_privat_tasks_user_id', 'privat_tasks', ['user_id'])
    op.create_index('ix_privat_tasks_task_type', 'privat_tasks', ['task_type'])
    op.create_index('ix_privat_tasks_category', 'privat_tasks', ['category'])
    op.create_index('ix_privat_tasks_source', 'privat_tasks', ['source_action_id'])

    # Partial index fuer aktive Tasks
    op.create_index(
        'ix_privat_tasks_pending',
        'privat_tasks',
        ['user_id', 'status', 'priority'],
        postgresql_where=sa.text("status IN ('pending', 'in_progress')")
    )

    # Index fuer faellige Tasks
    op.create_index(
        'ix_privat_tasks_due',
        'privat_tasks',
        ['due_date'],
        postgresql_where=sa.text("status = 'pending'")
    )

    # Check Constraints
    op.create_check_constraint(
        'chk_privat_task_status',
        'privat_tasks',
        "status IN ('pending', 'in_progress', 'completed', 'cancelled', 'snoozed')"
    )
    op.create_check_constraint(
        'chk_privat_task_priority',
        'privat_tasks',
        "priority IN ('low', 'medium', 'high', 'critical')"
    )

    # Table comment
    op.execute("""
        COMMENT ON TABLE privat_tasks IS
        'Orchestrator-generierte Tasks fuer Benutzeraktionen im Privat-Modul'
    """)


def downgrade() -> None:
    op.drop_table('privat_tasks')
