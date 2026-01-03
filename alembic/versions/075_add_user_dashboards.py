"""Add user dashboards and widget permissions tables.

Revision ID: 075_add_user_dashboards
Revises: 074_add_erp_connections
Create Date: 2026-01-02

Dashboard-Persistenz-Infrastruktur:
- user_dashboards: Personalisierte Dashboard-Layouts pro User
- dashboard_widgets: Widget-Konfiguration und Positionierung
- widget_permissions: Berechtigungen fuer Widget-Typen
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "075_add_user_dashboards"
down_revision = ("074_add_erp_connections", "streckengeschaeft_002", "streckengeschaeft_003")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==========================================================================
    # User Dashboards - Personalisierte Dashboard-Layouts
    # ==========================================================================
    op.create_table(
        "user_dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),

        # Dashboard-Metadaten
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),

        # Layout-Konfiguration (Grid-Settings)
        sa.Column("columns", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("row_height", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("compact_type", sa.String(20), nullable=True),  # vertical, horizontal, null

        # Globale Filter-Einstellungen
        sa.Column("default_date_range", sa.String(20), nullable=True),  # 7d, 30d, 90d, ytd
        sa.Column("default_company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),

        # Sharing (zukuenftig)
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("shared_with_roles", postgresql.JSONB(), nullable=True),  # ["admin", "editor"]

        # Zeitstempel
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Indizes fuer user_dashboards
    op.create_index("ix_user_dashboards_user_id", "user_dashboards", ["user_id"])
    op.create_index("ix_user_dashboards_is_default", "user_dashboards", ["user_id", "is_default"])

    # Constraint: Nur ein Default-Dashboard pro User
    op.execute("""
        CREATE UNIQUE INDEX ix_user_dashboards_one_default
        ON user_dashboards (user_id)
        WHERE is_default = true
    """)

    # ==========================================================================
    # Dashboard Widgets - Widget-Instanzen auf Dashboards
    # ==========================================================================
    op.create_table(
        "dashboard_widgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("dashboard_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user_dashboards.id", ondelete="CASCADE"), nullable=False),

        # Widget-Typ (Referenz zum Registry)
        sa.Column("widget_type", sa.String(50), nullable=False),

        # Grid-Position (react-grid-layout kompatibel)
        sa.Column("position_x", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("min_width", sa.Integer(), nullable=True),
        sa.Column("min_height", sa.Integer(), nullable=True),
        sa.Column("max_width", sa.Integer(), nullable=True),
        sa.Column("max_height", sa.Integer(), nullable=True),

        # Widget-spezifische Konfiguration
        sa.Column("config", postgresql.JSONB(), nullable=True),  # Widget-spezifische Optionen
        sa.Column("title_override", sa.String(100), nullable=True),  # Benutzerdefinierter Titel

        # Widget-Filter (ueberschreibt Dashboard-Filter)
        sa.Column("filter_overrides", postgresql.JSONB(), nullable=True),

        # Status
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_collapsed", sa.Boolean(), nullable=False, server_default="false"),

        # Sortierung (fuer nicht-grid-basierte Layouts)
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),

        # Zeitstempel
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Indizes fuer dashboard_widgets
    op.create_index("ix_dashboard_widgets_dashboard_id", "dashboard_widgets", ["dashboard_id"])
    op.create_index("ix_dashboard_widgets_widget_type", "dashboard_widgets", ["widget_type"])
    op.create_index("ix_dashboard_widgets_sort_order", "dashboard_widgets", ["dashboard_id", "sort_order"])

    # ==========================================================================
    # Widget Permissions - Berechtigungen pro Widget-Typ
    # ==========================================================================
    op.create_table(
        "widget_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Widget-Typ
        sa.Column("widget_type", sa.String(50), nullable=False),

        # Erforderliche Berechtigung
        sa.Column("required_permission", sa.String(100), nullable=False),

        # Beschreibung
        sa.Column("description", sa.String(255), nullable=True),

        # Zeitstempel
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    # Unique constraint: Eine Permission pro Widget-Typ
    op.create_unique_constraint(
        "uq_widget_permissions_unique",
        "widget_permissions",
        ["widget_type", "required_permission"]
    )

    op.create_index("ix_widget_permissions_widget_type", "widget_permissions", ["widget_type"])

    # ==========================================================================
    # Seed Widget Permissions
    # ==========================================================================
    op.execute("""
        INSERT INTO widget_permissions (id, widget_type, required_permission, description) VALUES
        (gen_random_uuid(), 'system-status', 'admin.system.view', 'System-Status Widget erfordert Admin-Berechtigung'),
        (gen_random_uuid(), 'finance-status', 'finance.view', 'Finanz-Status Widget erfordert Finanz-Berechtigung'),
        (gen_random_uuid(), 'open-invoices', 'finance.invoices.view', 'Offene Rechnungen Widget erfordert Rechnungs-Berechtigung'),
        (gen_random_uuid(), 'cashflow', 'finance.reports.view', 'Cashflow Widget erfordert Report-Berechtigung'),
        (gen_random_uuid(), 'aging-report', 'finance.reports.view', 'Aging Report Widget erfordert Report-Berechtigung'),
        (gen_random_uuid(), 'upload', 'documents.create', 'Upload Widget erfordert Dokument-Erstellung'),
        (gen_random_uuid(), 'recent-documents', 'documents.view', 'Letzte Dokumente Widget erfordert Dokument-Ansicht')
    """)

    # ==========================================================================
    # Dashboard Templates - Vordefinierte Dashboard-Vorlagen
    # ==========================================================================
    op.create_table(
        "dashboard_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),

        # Template-Metadaten
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),  # default, finance, admin, custom

        # Zielgruppe
        sa.Column("for_roles", postgresql.JSONB(), nullable=True),  # ["admin", "editor", "viewer"]

        # Template-Konfiguration
        sa.Column("layout", postgresql.JSONB(), nullable=False),  # Widget-Definitionen
        sa.Column("preview_image_url", sa.String(500), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),  # Nicht loeschbar

        # Zeitstempel
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )

    op.create_index("ix_dashboard_templates_category", "dashboard_templates", ["category"])
    op.create_index("ix_dashboard_templates_is_active", "dashboard_templates", ["is_active"])

    # ==========================================================================
    # Seed Default Templates
    # ==========================================================================
    op.execute("""
        INSERT INTO dashboard_templates (id, name, description, category, for_roles, layout, is_system) VALUES
        (
            gen_random_uuid(),
            'Admin Dashboard',
            'Vollstaendiges Dashboard fuer Administratoren mit System-Status und allen KPIs',
            'default',
            '["admin"]',
            '[
                {"widget_type": "system-status", "x": 0, "y": 0, "w": 4, "h": 3},
                {"widget_type": "finance-status", "x": 4, "y": 0, "w": 4, "h": 3},
                {"widget_type": "today", "x": 8, "y": 0, "w": 4, "h": 3},
                {"widget_type": "upload", "x": 0, "y": 3, "w": 6, "h": 4},
                {"widget_type": "recent-documents", "x": 6, "y": 3, "w": 6, "h": 4},
                {"widget_type": "quick-links", "x": 0, "y": 7, "w": 12, "h": 2}
            ]'::jsonb,
            true
        ),
        (
            gen_random_uuid(),
            'Editor Dashboard',
            'Workflow-fokussiertes Dashboard fuer Sachbearbeiter',
            'default',
            '["editor"]',
            '[
                {"widget_type": "today", "x": 0, "y": 0, "w": 6, "h": 3},
                {"widget_type": "upload", "x": 6, "y": 0, "w": 6, "h": 3},
                {"widget_type": "recent-documents", "x": 0, "y": 3, "w": 8, "h": 4},
                {"widget_type": "quick-links", "x": 8, "y": 3, "w": 4, "h": 4}
            ]'::jsonb,
            true
        ),
        (
            gen_random_uuid(),
            'Finanz Dashboard',
            'Dashboard mit Fokus auf Finanzkennzahlen',
            'finance',
            '["admin", "editor"]',
            '[
                {"widget_type": "finance-status", "x": 0, "y": 0, "w": 6, "h": 3},
                {"widget_type": "open-invoices", "x": 6, "y": 0, "w": 6, "h": 3},
                {"widget_type": "cashflow", "x": 0, "y": 3, "w": 6, "h": 4},
                {"widget_type": "aging-report", "x": 6, "y": 3, "w": 6, "h": 4}
            ]'::jsonb,
            true
        )
    """)


def downgrade() -> None:
    op.drop_table("dashboard_templates")
    op.drop_table("widget_permissions")
    op.drop_table("dashboard_widgets")
    op.drop_table("user_dashboards")
