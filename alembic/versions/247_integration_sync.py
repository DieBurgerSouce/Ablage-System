# -*- coding: utf-8 -*-
"""Integrations-Sync Dashboard: Konfiguration und Sync-Protokoll-Tabellen.

Revision ID: 247
Revises: 246
Create Date: 2026-02-21

Phase 4.4: Integrations-Sync Dashboard
- integration_configs: Konfiguration und aktueller Status pro Integration
- integration_sync_logs: Detaillierte Sync-Protokolle mit Statistiken
- Seed-Daten: Standard-Integrations-Konfigurationen für alle Mandanten
"""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "247"
down_revision = "246"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Standard-Integrationen die für jeden Mandanten angelegt werden
# ---------------------------------------------------------------------------

_DEFAULT_INTEGRATIONS = [
    {
        "integration_type": "datev",
        "display_name": "DATEV Rechenzentrum",
        "sync_interval_minutes": 60,
    },
    {
        "integration_type": "lexware",
        "display_name": "Lexware Office",
        "sync_interval_minutes": 120,
    },
    {
        "integration_type": "banking",
        "display_name": "Banking / Kontoauszüge",
        "sync_interval_minutes": 240,
    },
    {
        "integration_type": "slack",
        "display_name": "Slack Benachrichtigungen",
        "sync_interval_minutes": 30,
    },
    {
        "integration_type": "email",
        "display_name": "E-Mail Import",
        "sync_interval_minutes": 15,
    },
]


def upgrade() -> None:
    """Erstellt Integrations-Sync-Tabellen und legt Standard-Konfigurationen an."""

    # ==========================================================================
    # Table: integration_configs
    # ==========================================================================
    op.create_table(
        "integration_configs",

        # Primärschlüssel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        # Multi-Tenant
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),

        # Integrations-Stammdaten
        sa.Column("integration_type", sa.String(50), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),

        # Letzter Sync-Status (denormalisiert)
        sa.Column(
            "last_sync_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_sync_status",
            sa.String(20),
            nullable=True,
        ),
        sa.Column(
            "last_error_message",
            sa.Text,
            nullable=True,
        ),

        # Sync-Konfiguration
        sa.Column(
            "sync_interval_minutes",
            sa.Integer,
            nullable=False,
            server_default="60",
        ),

        # Zeitstempel
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        # CHECK-Constraints
        sa.CheckConstraint(
            "integration_type IN ('datev','lexware','banking','slack','email')",
            name="ck_integration_configs_type",
        ),
        sa.CheckConstraint(
            "last_sync_status IS NULL OR last_sync_status IN ('success','error','partial')",
            name="ck_integration_configs_last_status",
        ),
        sa.CheckConstraint(
            "sync_interval_minutes > 0",
            name="ck_integration_configs_interval_positive",
        ),

        comment="Konfiguration und aktueller Status externer Integrationen pro Mandant",
    )

    # Index: Mandant + Typ (für Dashboard-Abfragen)
    op.create_index(
        "ix_integration_configs_company_type",
        "integration_configs",
        ["company_id", "integration_type"],
    )

    # Partial-Index: Nur aktive Integrationen
    op.create_index(
        "ix_integration_configs_company_active",
        "integration_configs",
        ["company_id", "is_active"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ==========================================================================
    # Table: integration_sync_logs
    # ==========================================================================
    op.create_table(
        "integration_sync_logs",

        # Primärschlüssel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        # Referenzen
        sa.Column(
            "integration_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integration_configs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
        ),

        # Sync-Art und -Status
        sa.Column("sync_type", sa.String(20), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="started",
        ),

        # Verarbeitungsstatistiken
        sa.Column(
            "items_processed",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "items_failed",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "items_total",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "error_details",
            postgresql.JSONB,
            nullable=True,
            server_default="{}",
        ),

        # Zeitsteuerung
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "duration_seconds",
            sa.Float,
            nullable=True,
        ),

        # CHECK-Constraints
        sa.CheckConstraint(
            "sync_type IN ('full','incremental','manual')",
            name="ck_sync_logs_sync_type",
        ),
        sa.CheckConstraint(
            "status IN ('started','success','error','partial')",
            name="ck_sync_logs_status",
        ),
        sa.CheckConstraint(
            "items_processed >= 0 AND items_failed >= 0 AND items_total >= 0",
            name="ck_sync_logs_items_non_negative",
        ),

        comment="Detaillierte Sync-Protokolle mit Statistiken pro Synchronisations-Lauf",
    )

    # Index: History eines Sync-Laufs nach Mandant + Konfig + Zeit
    op.create_index(
        "ix_sync_logs_company_config_time",
        "integration_sync_logs",
        ["company_id", "integration_config_id", "started_at"],
    )

    # Partial-Index: Fehler-Übersicht im Dashboard
    op.create_index(
        "ix_sync_logs_company_status",
        "integration_sync_logs",
        ["company_id", "status", "started_at"],
        postgresql_where=sa.text("status IN ('error', 'partial')"),
    )

    # Einfacher Index auf company_id für mandanten-weite Abfragen
    op.create_index(
        "ix_sync_logs_company_id",
        "integration_sync_logs",
        ["company_id"],
    )

    # ==========================================================================
    # Seed-Daten: Standard-Integrationen für alle existierenden Mandanten
    # ==========================================================================
    _seed_default_integration_configs()


def _seed_default_integration_configs() -> None:
    """Legt Standard-Integrations-Konfigurationen für alle vorhandenen Mandanten an.

    Verwendet INSERT ... ON CONFLICT DO NOTHING um Idempotenz sicherzustellen.
    Vorhandene Konfigurationen werden nicht überschrieben.
    """
    bind = op.get_bind()

    # Alle existierenden Mandanten abrufen
    companies_result = bind.execute(
        sa.text("SELECT id FROM companies ORDER BY created_at")
    )
    company_rows = companies_result.fetchall()

    if not company_rows:
        # Keine Mandanten vorhanden (Erstinstallation ohne Seed-Daten)
        return

    # Seed-Datensaetze aufbauen.
    # HINWEIS (Reconcile 2026-06): Frueher ein raw INSERT mit :name::uuid/::jsonb-
    # Casts -> asyncpg kann SQLAlchemy-Named-Params + Casts im executemany-Pfad nicht
    # parsen ("syntax error at or near :"). Stattdessen op.bulk_insert mit typisierter
    # Ad-hoc-Tabelle: SQLAlchemy kompiliert die Typen (UUID/JSONB) korrekt fuer asyncpg.
    # integration_configs wird in DIESER Migration frisch angelegt -> leer, daher ist
    # ON CONFLICT nicht noetig (keine Kollision moeglich).
    integration_configs_tbl = sa.table(
        "integration_configs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("company_id", postgresql.UUID(as_uuid=True)),
        sa.column("integration_type", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("config", postgresql.JSONB()),
        sa.column("is_active", sa.Boolean()),
        sa.column("sync_interval_minutes", sa.Integer()),
    )
    rows = []
    for company_row in company_rows:
        company_id = company_row[0]  # asyncpg liefert bereits uuid.UUID
        for integration in _DEFAULT_INTEGRATIONS:
            rows.append({
                "id": uuid.uuid4(),
                "company_id": company_id,
                "integration_type": integration["integration_type"],
                "display_name": integration["display_name"],
                "config": {},
                "is_active": False,  # Standardmaessig deaktiviert bis konfiguriert
                "sync_interval_minutes": integration["sync_interval_minutes"],
            })

    if rows:
        op.bulk_insert(integration_configs_tbl, rows)


def downgrade() -> None:
    """Entfernt alle Integrations-Sync-Tabellen."""
    # Indexes explizit droppen (PostgreSQL Partial-Indexes werden nicht automatisch entfernt)
    op.drop_index("ix_sync_logs_company_id", table_name="integration_sync_logs")
    op.drop_index("ix_sync_logs_company_status", table_name="integration_sync_logs")
    op.drop_index("ix_sync_logs_company_config_time", table_name="integration_sync_logs")
    op.drop_table("integration_sync_logs")

    op.drop_index("ix_integration_configs_company_active", table_name="integration_configs")
    op.drop_index("ix_integration_configs_company_type", table_name="integration_configs")
    op.drop_table("integration_configs")
