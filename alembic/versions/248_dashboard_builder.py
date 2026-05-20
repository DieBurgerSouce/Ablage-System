# -*- coding: utf-8 -*-
"""Add dashboard_builder_configs and dashboard_builder_widgets tables.

Revision ID: 248
Revises: 247
Create Date: 2026-02-21

Phase 7.3: Dashboard-Builder

Erstellt:
  - dashboard_builder_configs  : Benutzerdefinierte Dashboard-Konfigurationen
  - dashboard_builder_widgets  : Widget-Instanzen auf Dashboards

Standard-Dashboards werden NICHT per Seed gesetzt, da kein
stabiler Company- / User-Datensatz zur Migrationszeit garantiert ist.
Die Anwendungslogik (DashboardBuilderService.get_default_dashboard_for_role)
legt Standard-Widgets dynamisch an.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Revisions-Metadaten
# ---------------------------------------------------------------------------

revision = "248"
down_revision = "247"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    """Erstellt die Dashboard-Builder-Tabellen."""

    # ==========================================================================
    # Tabelle: dashboard_builder_configs
    # ==========================================================================
    op.create_table(
        "dashboard_builder_configs",

        # Primaerschluessel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Eindeutige Dashboard-ID",
        ),

        # Multi-Tenant
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
            comment="Mandanten-Zuordnung",
        ),

        # Eigentuemer
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Eigentuemer-Benutzer",
        ),

        # Metadaten
        sa.Column(
            "name",
            sa.String(255),
            nullable=False,
            comment="Anzeigename des Dashboards",
        ),
        sa.Column(
            "description",
            sa.Text,
            nullable=True,
            comment="Optionale Beschreibung",
        ),

        # Layout als JSONB
        sa.Column(
            "layout",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
            comment=(
                "Grid-Layout als JSONB-Array: "
                '[{"widget_id": "uuid", "x": 0, "y": 0, "w": 6, "h": 4}]'
            ),
        ),

        # Status-Flags
        sa.Column(
            "is_default",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Standarddashboard des Benutzers",
        ),
        sa.Column(
            "is_shared",
            sa.Boolean,
            nullable=False,
            server_default="false",
            comment="Firmenweit freigegeben",
        ),

        # Zeitstempel
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        comment="Dashboard-Builder: Benutzerdefinierte Dashboard-Konfigurationen",
    )

    # Zusammengesetzter Index fuer Abfragen (company + user)
    op.create_index(
        "ix_dashboard_builder_configs_company_user",
        "dashboard_builder_configs",
        ["company_id", "user_id"],
    )

    # Index fuer geteilte Dashboards einer Firma
    op.create_index(
        "ix_dashboard_builder_configs_company_shared",
        "dashboard_builder_configs",
        ["company_id", "is_shared"],
    )

    # Partieller Index: Nur ein Default-Dashboard pro User
    # (PostgreSQL partieller UNIQUE INDEX)
    op.execute(
        """
        CREATE UNIQUE INDEX ix_dashboard_builder_configs_one_default
        ON dashboard_builder_configs (user_id, company_id)
        WHERE is_default = true
        """
    )

    # ==========================================================================
    # Tabelle: dashboard_builder_widgets
    # ==========================================================================
    op.create_table(
        "dashboard_builder_widgets",

        # Primaerschluessel
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            comment="Eindeutige Widget-ID",
        ),

        # Fremdschluessel zum Dashboard (CASCADE beim Loeschen)
        sa.Column(
            "dashboard_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dashboard_builder_configs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
            comment="Zugehoerige Dashboard-Konfiguration",
        ),

        # Widget-Definition
        sa.Column(
            "widget_type",
            sa.String(50),
            nullable=False,
            comment="Widget-Typ (invoice_status, cashflow_chart, ...)",
        ),
        sa.Column(
            "title",
            sa.String(255),
            nullable=False,
            comment="Anzeigename des Widgets",
        ),
        sa.Column(
            "config",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
            comment="Widget-spezifische Einstellungen",
        ),

        # Datenquelle und Aktualisierung
        sa.Column(
            "data_source",
            sa.String(100),
            nullable=False,
            comment="Interner Service/Endpunkt-Name",
        ),
        sa.Column(
            "refresh_interval_seconds",
            sa.Integer,
            nullable=False,
            server_default="300",
            comment="Aktualisierungsintervall in Sekunden",
        ),

        # Zeitstempel
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        # CheckConstraint: erlaubte Widget-Typen
        sa.CheckConstraint(
            "widget_type IN ("
            "'invoice_status', 'cashflow_chart', 'ocr_queue', "
            "'kpi_cards', 'anomaly_summary', 'recent_documents', "
            "'open_tasks', 'integration_health', 'active_learning_stats'"
            ")",
            name="ck_dashboard_builder_widget_type",
        ),

        # CheckConstraint: Minimum-Aktualisierungsintervall
        sa.CheckConstraint(
            "refresh_interval_seconds >= 30",
            name="ck_dashboard_builder_widget_refresh_min",
        ),

        comment="Dashboard-Builder: Widget-Instanzen auf Dashboards",
    )

    # Index: alle Widgets eines Dashboards
    op.create_index(
        "ix_dashboard_builder_widgets_dashboard",
        "dashboard_builder_widgets",
        ["dashboard_id"],
    )

    # Index: Widget-Typ-Verteilung je Dashboard
    op.create_index(
        "ix_dashboard_builder_widgets_type",
        "dashboard_builder_widgets",
        ["dashboard_id", "widget_type"],
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    """Entfernt die Dashboard-Builder-Tabellen (in umgekehrter Reihenfolge)."""

    # Erst Widgets (abhaengige Tabelle)
    op.drop_index(
        "ix_dashboard_builder_widgets_type",
        table_name="dashboard_builder_widgets",
    )
    op.drop_index(
        "ix_dashboard_builder_widgets_dashboard",
        table_name="dashboard_builder_widgets",
    )
    op.drop_table("dashboard_builder_widgets")

    # Dann Configs (Elterntabelle)
    op.execute(
        "DROP INDEX IF EXISTS ix_dashboard_builder_configs_one_default"
    )
    op.drop_index(
        "ix_dashboard_builder_configs_company_shared",
        table_name="dashboard_builder_configs",
    )
    op.drop_index(
        "ix_dashboard_builder_configs_company_user",
        table_name="dashboard_builder_configs",
    )
    op.drop_table("dashboard_builder_configs")
