# -*- coding: utf-8 -*-
"""Add AI Conversations tables for Finance Assistant persistence

Revision ID: 120_add_ai_conversations
Revises: 119_add_dpia_tables
Create Date: 2026-01-25

Tabellen:
- ai_conversations: Konversations-Sessions mit dem KI-Finanzassistenten
- ai_conversation_messages: Einzelne Nachrichten innerhalb einer Konversation
- ai_conversation_actions: Ausgefuehrte Aktionen durch den Assistenten
- ai_conversation_feedbacks: Benutzer-Feedback zu Antworten

Features:
- Persistierung der Chat-History fuer Kontext-Bewahrung
- Aktions-Tracking fuer Audit-Trail
- Feedback-Sammlung fuer kontinuierliche Verbesserung
- Session-basierte Isolierung mit Multi-Tenant Support

Feinpoliert und durchdacht - Deutsche Praezision.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '120_add_ai_conversations'
down_revision = '119_add_dpia_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Message Role Enum
    message_role_enum = postgresql.ENUM(
        'user', 'assistant', 'system',
        name='ai_message_role'
    )
    message_role_enum.create(op.get_bind())

    # Intent Enum
    intent_enum = postgresql.ENUM(
        'search', 'execute_action', 'explain', 'suggest_booking',
        'analyze', 'predict', 'help', 'chat',
        name='ai_assistant_intent'
    )
    intent_enum.create(op.get_bind())

    # Action Status Enum
    action_status_enum = postgresql.ENUM(
        'proposed', 'confirmed', 'executed', 'cancelled', 'failed',
        name='ai_action_status'
    )
    action_status_enum.create(op.get_bind())

    # Feedback Type Enum
    feedback_type_enum = postgresql.ENUM(
        'helpful', 'not_helpful', 'incorrect', 'confusing', 'other',
        name='ai_feedback_type'
    )
    feedback_type_enum.create(op.get_bind())

    # ==========================================================================
    # AI Conversations - Haupt-Session-Tabelle
    # ==========================================================================
    op.create_table(
        'ai_conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', sa.String(64), nullable=False, unique=True,
                  comment='Eindeutige Session-ID fuer Frontend-Zuordnung'),

        # Beziehungen
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Metadaten
        sa.Column('title', sa.String(255), nullable=True,
                  comment='Automatisch generierter oder manueller Titel'),
        sa.Column('context_page', sa.String(255), nullable=True,
                  comment='Seite auf der die Konversation gestartet wurde'),
        sa.Column('language', sa.String(5), nullable=False, server_default='de'),

        # Status
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true',
                  comment='False wenn archiviert'),
        sa.Column('is_starred', sa.Boolean, nullable=False, server_default='false',
                  comment='Vom Benutzer markiert'),

        # Statistiken
        sa.Column('message_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('action_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer, nullable=True,
                  comment='Gesamte Token-Nutzung (fuer Kosten-Tracking)'),

        # Kontext-Daten (JSONB)
        sa.Column('context_data', postgresql.JSONB, nullable=True,
                  comment='Zusaetzlicher Kontext (ausgewaehlte Dokumente, etc.)'),
        sa.Column('preferences', postgresql.JSONB, nullable=True,
                  comment='Benutzer-Praeferenzen fuer diese Session'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('last_message_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('ix_ai_conv_user_active', 'ai_conversations',
                    ['user_id', 'is_active'])
    op.create_index('ix_ai_conv_company', 'ai_conversations', ['company_id'])
    op.create_index('ix_ai_conv_last_msg', 'ai_conversations',
                    ['last_message_at'])
    op.create_index('ix_ai_conv_session', 'ai_conversations', ['session_id'])

    # ==========================================================================
    # AI Conversation Messages - Einzelne Nachrichten
    # ==========================================================================
    op.create_table(
        'ai_conversation_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('ai_conversations.id', ondelete='CASCADE'),
                  nullable=False, index=True),

        # Nachricht
        sa.Column('role', message_role_enum, nullable=False),
        sa.Column('content', sa.Text, nullable=False,
                  comment='Nachrichteninhalt (Markdown-formatiert)'),
        sa.Column('intent', intent_enum, nullable=True,
                  comment='Erkannte Absicht (nur fuer user-Nachrichten)'),
        sa.Column('confidence', sa.Float, nullable=True,
                  comment='Konfidenz der Intent-Erkennung (0.0-1.0)'),

        # Antwort-Metadaten (nur fuer assistant-Nachrichten)
        sa.Column('search_results_count', sa.Integer, nullable=True),
        sa.Column('actions_proposed', sa.Integer, nullable=True),
        sa.Column('processing_time_ms', sa.Integer, nullable=True),
        sa.Column('model_used', sa.String(50), nullable=True,
                  comment='LLM-Modell (ollama/mistral, etc.)'),
        sa.Column('tokens_used', sa.Integer, nullable=True),

        # Erweiterte Daten
        sa.Column('extra_data', postgresql.JSONB, nullable=True,
                  comment='Zusaetzliche Metadaten (Insights, Suggestions, etc.)'),
        sa.Column('referenced_documents', postgresql.JSONB, nullable=True,
                  comment='Array von Dokument-IDs die referenziert wurden'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    op.create_index('ix_ai_msg_conv_created', 'ai_conversation_messages',
                    ['conversation_id', 'created_at'])
    op.create_index('ix_ai_msg_role', 'ai_conversation_messages', ['role'])

    # ==========================================================================
    # AI Conversation Actions - Ausgefuehrte Aktionen
    # ==========================================================================
    op.create_table(
        'ai_conversation_actions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('ai_conversations.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('message_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('ai_conversation_messages.id', ondelete='SET NULL'),
                  nullable=True,
                  comment='Nachricht in der die Aktion vorgeschlagen wurde'),

        # Aktion
        sa.Column('action_type', sa.String(50), nullable=False,
                  comment='payment_run, approve_invoices, categorize_documents, etc.'),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('status', action_status_enum, nullable=False,
                  server_default='proposed'),

        # Parameter und Ergebnis
        sa.Column('parameters', postgresql.JSONB, nullable=False, server_default='{}',
                  comment='Aktionsparameter'),
        sa.Column('result', postgresql.JSONB, nullable=True,
                  comment='Ergebnis nach Ausfuehrung'),
        sa.Column('error_message', sa.Text, nullable=True),

        # Betroffene Entitaeten
        sa.Column('affected_documents', postgresql.JSONB, nullable=True,
                  comment='Array von betroffenen Dokument-IDs'),
        sa.Column('affected_count', sa.Integer, nullable=True),
        sa.Column('success_count', sa.Integer, nullable=True),
        sa.Column('failure_count', sa.Integer, nullable=True),

        # Sicherheit
        sa.Column('requires_confirmation', sa.Boolean, nullable=False,
                  server_default='true'),
        sa.Column('confirmed_by_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column('proposed_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column('executed_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index('ix_ai_action_conv', 'ai_conversation_actions',
                    ['conversation_id', 'proposed_at'])
    op.create_index('ix_ai_action_status', 'ai_conversation_actions', ['status'])
    op.create_index('ix_ai_action_type', 'ai_conversation_actions', ['action_type'])

    # ==========================================================================
    # AI Conversation Feedbacks - Benutzer-Feedback
    # ==========================================================================
    op.create_table(
        'ai_conversation_feedbacks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('message_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('ai_conversation_messages.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False),

        # Feedback
        sa.Column('feedback_type', feedback_type_enum, nullable=False),
        sa.Column('rating', sa.Integer, nullable=True,
                  comment='1-5 Sterne-Bewertung'),
        sa.Column('comment', sa.Text, nullable=True,
                  comment='Optionaler Freitext-Kommentar'),

        # Korrekturen
        sa.Column('correction', sa.Text, nullable=True,
                  comment='Korrigierte Antwort vom Benutzer'),
        sa.Column('expected_intent', sa.String(50), nullable=True,
                  comment='Erwartete Intent falls falsch erkannt'),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.func.now()),

        # Constraints
        sa.CheckConstraint('rating >= 1 AND rating <= 5', name='ck_feedback_rating_range'),
    )

    op.create_index('ix_ai_feedback_msg', 'ai_conversation_feedbacks', ['message_id'])
    op.create_index('ix_ai_feedback_type', 'ai_conversation_feedbacks',
                    ['feedback_type', 'created_at'])

    # ==========================================================================
    # RLS Policies fuer Multi-Tenant Isolation
    # ==========================================================================

    # Enable RLS
    op.execute("ALTER TABLE ai_conversations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversation_messages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversation_actions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversation_feedbacks ENABLE ROW LEVEL SECURITY")

    # Conversations Policy - Company-basiert
    op.execute("""
        CREATE POLICY ai_conversations_isolation ON ai_conversations
        FOR ALL
        USING (company_id = current_setting('app.current_company_id', true)::uuid)
    """)

    # Messages Policy - Via Conversation Join
    op.execute("""
        CREATE POLICY ai_messages_isolation ON ai_conversation_messages
        FOR ALL
        USING (
            conversation_id IN (
                SELECT id FROM ai_conversations
                WHERE company_id = current_setting('app.current_company_id', true)::uuid
            )
        )
    """)

    # Actions Policy - Via Conversation Join
    op.execute("""
        CREATE POLICY ai_actions_isolation ON ai_conversation_actions
        FOR ALL
        USING (
            conversation_id IN (
                SELECT id FROM ai_conversations
                WHERE company_id = current_setting('app.current_company_id', true)::uuid
            )
        )
    """)

    # Feedbacks Policy - Via Message/Conversation Join
    op.execute("""
        CREATE POLICY ai_feedbacks_isolation ON ai_conversation_feedbacks
        FOR ALL
        USING (
            message_id IN (
                SELECT m.id FROM ai_conversation_messages m
                JOIN ai_conversations c ON m.conversation_id = c.id
                WHERE c.company_id = current_setting('app.current_company_id', true)::uuid
            )
        )
    """)


def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS ai_feedbacks_isolation ON ai_conversation_feedbacks")
    op.execute("DROP POLICY IF EXISTS ai_actions_isolation ON ai_conversation_actions")
    op.execute("DROP POLICY IF EXISTS ai_messages_isolation ON ai_conversation_messages")
    op.execute("DROP POLICY IF EXISTS ai_conversations_isolation ON ai_conversations")

    # Disable RLS
    op.execute("ALTER TABLE ai_conversation_feedbacks DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversation_actions DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversation_messages DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_conversations DISABLE ROW LEVEL SECURITY")

    # Drop tables in reverse order
    op.drop_table('ai_conversation_feedbacks')
    op.drop_table('ai_conversation_actions')
    op.drop_table('ai_conversation_messages')
    op.drop_table('ai_conversations')

    # Drop enums
    op.execute('DROP TYPE IF EXISTS ai_feedback_type')
    op.execute('DROP TYPE IF EXISTS ai_action_status')
    op.execute('DROP TYPE IF EXISTS ai_assistant_intent')
    op.execute('DROP TYPE IF EXISTS ai_message_role')
