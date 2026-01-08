"""Add report builder tables.

Revision ID: 078_add_report_builder
Revises: 077_add_ai_autonomy
Create Date: 2026-01-03

Report-Builder-Infrastruktur:
- report_templates: Gespeicherte Report-Definitionen
- report_columns: Spalten-Konfiguration pro Template
- report_filters: Filter-Bedingungen pro Template
- report_charts: Chart-Konfigurationen
- report_executions: Ausfuehrungs-Historie
- report_shares: Freigaben an andere User
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add report builder tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
        uuid_default = sa.text("gen_random_uuid()")
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON
        uuid_default = None

    # =========================================================================
    # 1. REPORT_TEMPLATES - Gespeicherte Report-Definitionen
    # =========================================================================
    op.create_table(
        "report_templates",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("user_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),

        # Basis-Informationen
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # Report-Typ und Datenquelle
        sa.Column("report_type", sa.String(50), nullable=False),  # document|finance|ocr|custom
        sa.Column("data_source", sa.String(50), nullable=False),  # documents|invoices|entities|ocr_results
        sa.Column("default_format", sa.String(20), nullable=False, server_default="excel"),  # pdf|excel|csv|json

        # Sichtbarkeit
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Zeitplan-Konfiguration
        sa.Column("is_scheduled", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("schedule_config", json_type, nullable=True),  # {cron, timezone, recipients}

        # Layout-Konfiguration
        sa.Column("layout_config", json_type, nullable=True),  # {orientation, margins, header, footer}

        # Sortierung
        sa.Column("sort_config", json_type, nullable=True),  # [{field, direction}]

        # Aggregationen (GROUP BY)
        sa.Column("group_by_config", json_type, nullable=True),  # [field_paths]

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Indices fuer report_templates
    op.create_index("ix_report_templates_user_id", "report_templates", ["user_id"])
    op.create_index("ix_report_templates_company_id", "report_templates", ["company_id"])
    op.create_index("ix_report_templates_report_type", "report_templates", ["report_type"])
    op.create_index("ix_report_templates_is_public", "report_templates", ["is_public"])
    op.create_index("ix_report_templates_is_scheduled", "report_templates", ["is_scheduled"])

    # =========================================================================
    # 2. REPORT_COLUMNS - Spalten-Konfiguration pro Template
    # =========================================================================
    op.create_table(
        "report_columns",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("template_id", uuid_type, sa.ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False),

        # Feld-Definition
        sa.Column("field_path", sa.String(255), nullable=False),  # z.B. "extracted_data.invoice_number"
        sa.Column("display_name", sa.String(255), nullable=False),  # z.B. "Rechnungsnummer"
        sa.Column("data_type", sa.String(50), nullable=False),  # string|number|date|currency|boolean

        # Formatierung
        sa.Column("format_pattern", sa.String(100), nullable=True),  # z.B. "#,##0.00 EUR"
        sa.Column("width", sa.Integer, nullable=True),  # Spaltenbreite in px oder Excel-Units

        # Reihenfolge und Sichtbarkeit
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_visible", sa.Boolean, nullable=False, server_default=sa.text("true")),

        # Aggregation (fuer Summenzeilen)
        sa.Column("aggregation", sa.String(20), nullable=True),  # none|sum|avg|count|min|max

        # Bedingte Formatierung
        sa.Column("conditional_format", json_type, nullable=True),  # [{condition, style}]

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indices fuer report_columns
    op.create_index("ix_report_columns_template_id", "report_columns", ["template_id"])
    op.create_index("ix_report_columns_sort_order", "report_columns", ["template_id", "sort_order"])

    # =========================================================================
    # 3. REPORT_FILTERS - Filter-Bedingungen pro Template
    # =========================================================================
    op.create_table(
        "report_filters",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("template_id", uuid_type, sa.ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False),

        # Filter-Definition
        sa.Column("field_path", sa.String(255), nullable=False),  # z.B. "status"
        sa.Column("operator", sa.String(50), nullable=False),  # eq|ne|gt|lt|gte|lte|contains|in|between|is_null
        sa.Column("value", json_type, nullable=True),  # Wert(e) je nach Operator

        # Logische Verknuepfung
        sa.Column("logic_operator", sa.String(10), nullable=False, server_default="AND"),  # AND|OR
        sa.Column("group_id", sa.Integer, nullable=True),  # Fuer verschachtelte Gruppen

        # Reihenfolge
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),

        # Dynamische Werte
        sa.Column("is_dynamic", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("dynamic_source", sa.String(100), nullable=True),  # z.B. "current_user", "today", "last_30_days"

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indices fuer report_filters
    op.create_index("ix_report_filters_template_id", "report_filters", ["template_id"])

    # =========================================================================
    # 4. REPORT_CHARTS - Chart-Konfigurationen
    # =========================================================================
    op.create_table(
        "report_charts",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("template_id", uuid_type, sa.ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False),

        # Chart-Typ
        sa.Column("chart_type", sa.String(50), nullable=False),  # bar|line|pie|area|scatter
        sa.Column("title", sa.String(255), nullable=True),

        # Daten-Mapping
        sa.Column("x_axis_field", sa.String(255), nullable=True),  # Kategorie/X-Achse
        sa.Column("y_axis_fields", json_type, nullable=False),  # Liste von Feldern fuer Y-Achse
        sa.Column("group_by_field", sa.String(255), nullable=True),  # Optional: Gruppierung

        # Styling
        sa.Column("colors", json_type, nullable=True),  # Benutzerdefinierte Farben
        sa.Column("show_legend", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("show_labels", sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Position (fuer PDF/Excel Layout)
        sa.Column("position", sa.String(20), nullable=False, server_default="bottom"),  # top|bottom|separate_sheet
        sa.Column("width_percent", sa.Integer, nullable=False, server_default=sa.text("100")),
        sa.Column("height_px", sa.Integer, nullable=False, server_default=sa.text("300")),

        # Reihenfolge (bei mehreren Charts)
        sa.Column("sort_order", sa.Integer, nullable=False, server_default=sa.text("0")),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indices fuer report_charts
    op.create_index("ix_report_charts_template_id", "report_charts", ["template_id"])

    # =========================================================================
    # 5. REPORT_EXECUTIONS - Ausfuehrungs-Historie
    # =========================================================================
    op.create_table(
        "report_executions",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("template_id", uuid_type, sa.ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("executed_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Ausfuehrung
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),  # pending|running|completed|failed
        sa.Column("format", sa.String(20), nullable=False),  # pdf|excel|csv|json
        sa.Column("trigger_type", sa.String(50), nullable=False),  # manual|scheduled|api

        # Ergebnis
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),  # MinIO Pfad
        sa.Column("download_url", sa.String(1000), nullable=True),  # Signierte URL
        sa.Column("download_expires_at", sa.DateTime(timezone=True), nullable=True),

        # Fehler-Details
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_details", json_type, nullable=True),

        # Filter-Snapshot (was zum Zeitpunkt der Ausfuehrung galt)
        sa.Column("filter_snapshot", json_type, nullable=True),

        # Performance-Metriken
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indices fuer report_executions
    op.create_index("ix_report_executions_template_id", "report_executions", ["template_id"])
    op.create_index("ix_report_executions_executed_by_id", "report_executions", ["executed_by_id"])
    op.create_index("ix_report_executions_status", "report_executions", ["status"])
    op.create_index("ix_report_executions_created_at", "report_executions", ["created_at"])

    # =========================================================================
    # 6. REPORT_SHARES - Freigaben an andere User
    # =========================================================================
    op.create_table(
        "report_shares",
        sa.Column("id", uuid_type, primary_key=True, server_default=uuid_default),
        sa.Column("template_id", uuid_type, sa.ForeignKey("report_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shared_with_user_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("shared_with_group_id", uuid_type, nullable=True),  # Falls Gruppen-Support existiert

        # Berechtigungen
        sa.Column("can_view", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("can_execute", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("can_edit", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("can_delete", sa.Boolean, nullable=False, server_default=sa.text("false")),

        # Wer hat geteilt
        sa.Column("shared_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Indices fuer report_shares
    op.create_index("ix_report_shares_template_id", "report_shares", ["template_id"])
    op.create_index("ix_report_shares_shared_with_user_id", "report_shares", ["shared_with_user_id"])
    op.create_index(
        "uq_report_shares_template_user",
        "report_shares",
        ["template_id", "shared_with_user_id"],
        unique=True,
    )


def downgrade() -> None:
    """Remove report builder tables."""
    op.drop_table("report_shares")
    op.drop_table("report_executions")
    op.drop_table("report_charts")
    op.drop_table("report_filters")
    op.drop_table("report_columns")
    op.drop_table("report_templates")
