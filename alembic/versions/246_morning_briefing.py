# -*- coding: utf-8 -*-
"""Morning Briefing Cache und AI Chat Sessions Tabellen.

Revision ID: 246
Revises: 245
Create Date: 2026-02-21

Phase 4.1: Proaktives Benachrichtigungs-System
- morning_briefing_cache: Gecachte Tages-Briefings pro Firma
- ai_chat_sessions: Chat-Session-Persistenz für den KI-Assistenten
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "246"
down_revision = "245"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Erstellt die Morning Briefing und AI Chat Tabellen."""

    # ==========================================================================
    # Tabelle: morning_briefing_cache
    # Gecachte Tages-Briefings pro Firma mit automatischem Ablauf
    # ==========================================================================
    op.create_table(
        "morning_briefing_cache",

        # Primärschlüssel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Primärschlüssel",
        ),

        # Multi-Tenant: Firmen-Zuordnung
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="Mandanten-Zuordnung (RESTRICT: Firma darf nicht gelöscht werden solange Cache existiert)",
        ),

        # Datum des Briefings (ein Briefing pro Firma und Tag)
        sa.Column(
            "briefing_date",
            sa.Date(),
            nullable=False,
            comment="Datum des Tages-Briefings",
        ),

        # Briefing-Inhalt als JSONB
        sa.Column(
            "briefing_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment="Vollständiges Briefing als JSONB (Sektionen, Alerts, Score)",
        ),

        # Zeitstempel
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Zeitpunkt der Briefing-Generierung",
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Ablaufzeitpunkt des Cache (danach wird neu generiert)",
        ),

        # Metadaten
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Erstellungszeitpunkt des Eintrags",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Letzter Änderungszeitpunkt",
        ),

        # Unique-Constraint: ein Briefing pro Firma und Tag
        sa.UniqueConstraint(
            "company_id",
            "briefing_date",
            name="uq_morning_briefing_company_date",
        ),
    )

    # Index für schnelle Abfragen nach Firma + Datum
    op.create_index(
        "ix_morning_briefing_cache_company_date",
        "morning_briefing_cache",
        ["company_id", "briefing_date"],
        unique=False,
    )

    # Index für Ablauf-Prüfungen (Hintergrund-Cleanup)
    op.create_index(
        "ix_morning_briefing_cache_expires_at",
        "morning_briefing_cache",
        ["expires_at"],
        unique=False,
    )

    # ==========================================================================
    # Tabelle: ai_chat_sessions
    # Persistente Chat-Sessions für den KI-Assistenten
    # ==========================================================================
    op.create_table(
        "ai_chat_sessions",

        # Primärschlüssel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Primärschlüssel",
        ),

        # Multi-Tenant: Firmen-Zuordnung
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="Mandanten-Zuordnung",
        ),

        # Benutzer-Zuordnung
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="Benutzer dem die Session gehört",
        ),

        # Session-Identifikator (Frontend-seitig generiert)
        sa.Column(
            "session_key",
            sa.String(length=100),
            nullable=False,
            comment="Frontend-seitige Session-ID (z.B. 'session_abc123')",
        ),

        # Session-Metadaten
        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("'Neue Konversation'"),
            comment="Session-Titel (aus erster Nachricht generiert)",
        ),

        # Chat-Verlauf als JSONB-Array
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment="Gesprächsverlauf als JSONB-Array [{role, content, timestamp}]",
        ),

        # Statistiken (denormalisiert für schnelle Abfragen)
        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Anzahl Nachrichten (exkl. System-Prompt)",
        ),

        # Zeitstempel
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Erstellungszeitpunkt der Session",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Letzter Aktivitätszeitpunkt",
        ),

        # Soft-Delete (DSGVO: Benutzer kann Chatverlauf löschen)
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="DSGVO: Zeitpunkt der Löschung (Soft-Delete)",
        ),

        # Unique-Constraint: session_key muss pro Firma eindeutig sein
        sa.UniqueConstraint(
            "company_id",
            "session_key",
            name="uq_ai_chat_sessions_company_key",
        ),
    )

    # Index für Benutzer-spezifische Abfragen (neueste Sessions)
    op.create_index(
        "ix_ai_chat_sessions_user_updated",
        "ai_chat_sessions",
        ["user_id", "updated_at"],
        unique=False,
    )

    # Index für Firma-spezifische Abfragen
    op.create_index(
        "ix_ai_chat_sessions_company_updated",
        "ai_chat_sessions",
        ["company_id", "updated_at"],
        unique=False,
    )

    # Index für Soft-Delete-Filter
    op.create_index(
        "ix_ai_chat_sessions_active",
        "ai_chat_sessions",
        ["user_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Entfernt die Morning Briefing und AI Chat Tabellen."""

    # Indexes und Tabellen in umgekehrter Reihenfolge löschen
    op.drop_index("ix_ai_chat_sessions_active", table_name="ai_chat_sessions")
    op.drop_index("ix_ai_chat_sessions_company_updated", table_name="ai_chat_sessions")
    op.drop_index("ix_ai_chat_sessions_user_updated", table_name="ai_chat_sessions")
    op.drop_table("ai_chat_sessions")

    op.drop_index("ix_morning_briefing_cache_expires_at", table_name="morning_briefing_cache")
    op.drop_index("ix_morning_briefing_cache_company_date", table_name="morning_briefing_cache")
    op.drop_table("morning_briefing_cache")
