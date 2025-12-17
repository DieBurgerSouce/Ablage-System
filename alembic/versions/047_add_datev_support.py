"""Add DATEV export support.

Revision ID: 047_add_datev_support
Revises: 046_add_banking_tables
Create Date: 2025-12-17

DATEV Buchungsstapel Export fuer Ablage-System:
- datev_configurations: Steuerberater-Konfiguration (Berater-Nr., Mandanten-Nr., Kontenrahmen)
- datev_vendor_mappings: Lieferanten-spezifische Kontozuordnung
- datev_exports: Export-Historie fuer Audit-Trail
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '047_add_datev_support'
down_revision = '046_add_banking_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add DATEV export tables."""

    # Check dialect
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. DATEV_CONFIGURATIONS - Steuerberater-Konfiguration
    # =========================================================================
    op.create_table(
        "datev_configurations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("user_id", uuid_type, nullable=True, comment="Benutzer-spezifische Konfiguration"),

        # DATEV Pflichtfelder
        sa.Column("berater_nr", sa.String(7), nullable=False, comment="Beraternummer (max. 7-stellig)"),
        sa.Column("mandanten_nr", sa.String(5), nullable=False, comment="Mandantennummer (max. 5-stellig)"),
        sa.Column("wj_beginn", sa.Date, nullable=False, comment="Wirtschaftsjahr-Beginn"),

        # Kontenrahmen
        sa.Column("kontenrahmen", sa.String(10), nullable=False, default="SKR03",
                  comment="SKR03 oder SKR04"),

        # Standardkonten Eingangsrechnungen
        sa.Column("incoming_expense_account", sa.String(10), nullable=True,
                  comment="Aufwandskonto Eingang (z.B. 4200 Wareneingang)"),
        sa.Column("incoming_creditor_account", sa.String(10), nullable=True,
                  comment="Kreditorenkonto Eingang (z.B. 70000)"),

        # Standardkonten Ausgangsrechnungen
        sa.Column("outgoing_revenue_account", sa.String(10), nullable=True,
                  comment="Erloeskonto Ausgang (z.B. 8400)"),
        sa.Column("outgoing_debtor_account", sa.String(10), nullable=True,
                  comment="Debitorenkonto Ausgang (z.B. 10000)"),

        # Sammelkonten
        sa.Column("sammelkonto_kreditoren", sa.String(10), default="1600",
                  comment="Sammelkonto Kreditoren"),
        sa.Column("sammelkonto_debitoren", sa.String(10), default="1400",
                  comment="Sammelkonto Debitoren"),

        # Optionale Einstellungen
        sa.Column("sachkontenlange", sa.Integer, default=4,
                  comment="Laenge Sachkonten (4-8 Stellen)"),
        sa.Column("buchungstext_format", sa.String(100), default="{invoice_number}",
                  comment="Format fuer Buchungstext"),

        # Status
        sa.Column("is_default", sa.Boolean, default=False,
                  comment="Standard-Konfiguration"),
        sa.Column("is_active", sa.Boolean, default=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.CheckConstraint("kontenrahmen IN ('SKR03', 'SKR04')", name="ck_datev_config_kontenrahmen"),
        sa.CheckConstraint("sachkontenlange BETWEEN 4 AND 8", name="ck_datev_config_sachkontenlange"),
    )

    op.create_index("ix_datev_configurations_user_id", "datev_configurations", ["user_id"])
    op.create_index("ix_datev_configurations_is_default", "datev_configurations", ["is_default"])
    op.create_index("ix_datev_configurations_is_active", "datev_configurations", ["is_active"])

    # =========================================================================
    # 2. DATEV_VENDOR_MAPPINGS - Lieferanten-Kontozuordnung
    # =========================================================================
    op.create_table(
        "datev_vendor_mappings",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("config_id", uuid_type, nullable=False),

        # Lieferanten-Identifikation (mehrere Match-Optionen)
        sa.Column("vendor_name", sa.String(255), nullable=True,
                  comment="Firmenname (Fuzzy-Match)"),
        sa.Column("vendor_vat_id", sa.String(50), nullable=True,
                  comment="USt-IdNr (exakter Match)"),
        sa.Column("vendor_iban", sa.String(34), nullable=True,
                  comment="IBAN (exakter Match)"),
        sa.Column("business_entity_id", uuid_type, nullable=True,
                  comment="Verknuepfter Geschaeftspartner"),

        # Kontozuordnung
        sa.Column("expense_account", sa.String(10), nullable=False,
                  comment="Aufwandskonto"),
        sa.Column("creditor_account", sa.String(10), nullable=True,
                  comment="Personenkonto (Kreditor)"),
        sa.Column("cost_center", sa.String(20), nullable=True,
                  comment="Kostenstelle"),
        sa.Column("cost_object", sa.String(20), nullable=True,
                  comment="Kostentraeger"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["config_id"], ["datev_configurations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["business_entity_id"], ["business_entities.id"],
                                ondelete="SET NULL"),
    )

    op.create_index("ix_datev_vendor_mappings_config_id", "datev_vendor_mappings", ["config_id"])
    op.create_index("ix_datev_vendor_mappings_vendor_vat_id", "datev_vendor_mappings", ["vendor_vat_id"])
    op.create_index("ix_datev_vendor_mappings_vendor_iban", "datev_vendor_mappings", ["vendor_iban"])
    op.create_index("ix_datev_vendor_mappings_business_entity_id", "datev_vendor_mappings",
                    ["business_entity_id"])

    # =========================================================================
    # 3. DATEV_EXPORTS - Export-Historie
    # =========================================================================
    op.create_table(
        "datev_exports",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("config_id", uuid_type, nullable=False),
        sa.Column("exported_by_id", uuid_type, nullable=True),

        # Export-Details
        sa.Column("export_type", sa.String(50), nullable=False, default="buchungsstapel",
                  comment="buchungsstapel, stammdaten"),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("document_count", sa.Integer, default=0),

        # Zeitraum
        sa.Column("period_from", sa.Date, nullable=True),
        sa.Column("period_to", sa.Date, nullable=True),

        # Datei-Metadaten
        sa.Column("content_hash", sa.String(64), nullable=True,
                  comment="SHA256 der Export-Datei"),
        sa.Column("file_size_bytes", sa.Integer, nullable=True),

        # Status
        sa.Column("status", sa.String(20), default="completed",
                  comment="completed, failed, partial"),
        sa.Column("error_message", sa.Text, nullable=True),

        # Inkludierte Dokumente
        sa.Column("included_documents", json_type, nullable=True, default=list,
                  comment="Array von Dokument-UUIDs"),
        sa.Column("skipped_documents", json_type, nullable=True, default=list,
                  comment="Array von uebersprungenen Dokument-UUIDs"),
        sa.Column("warnings", json_type, nullable=True, default=list,
                  comment="Array von Warnmeldungen"),

        # Audit
        sa.Column("exported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["config_id"], ["datev_configurations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exported_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('completed', 'failed', 'partial')",
            name="ck_datev_exports_status"
        ),
    )

    op.create_index("ix_datev_exports_config_id", "datev_exports", ["config_id"])
    op.create_index("ix_datev_exports_exported_by_id", "datev_exports", ["exported_by_id"])
    op.create_index("ix_datev_exports_exported_at", "datev_exports", ["exported_at"])
    op.create_index("ix_datev_exports_period", "datev_exports", ["period_from", "period_to"])
    op.create_index("ix_datev_exports_status", "datev_exports", ["status"])


def downgrade() -> None:
    """Remove DATEV export tables."""
    op.drop_table("datev_exports")
    op.drop_table("datev_vendor_mappings")
    op.drop_table("datev_configurations")
