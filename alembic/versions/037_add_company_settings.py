"""Add company_settings table for invoice direction detection.

Revision ID: 037_add_company_settings
Revises: 036_fix_embedding_dimensions
Create Date: 2024-12-12

Neue Tabelle:
- company_settings (Singleton fuer Firmendetails)

Verwendet fuer:
- Erkennung von Eingangs- vs. Ausgangsrechnungen
- Abgleich von Absender/Empfaenger gegen eigene Firmendaten
- Alternative Firmennamen fuer flexible Erkennung
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "037_add_company_settings"
down_revision = "036_fix_embedding_dimensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add company_settings table."""

    # Check if we're using PostgreSQL
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # UUID type based on dialect
    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # CREATE COMPANY_SETTINGS TABLE
    # =========================================================================
    op.create_table(
        "company_settings",
        sa.Column("id", uuid_type, primary_key=True),

        # Firmenidentifikation
        sa.Column("company_name", sa.String(255), nullable=False, comment="Offizieller Firmenname"),
        sa.Column(
            "alternative_names",
            json_type,
            nullable=True,
            server_default="[]",
            comment="Alternative Schreibweisen fuer Dokumentenerkennung"
        ),

        # Adresse
        sa.Column("street", sa.String(255), nullable=True, comment="Strasse mit Hausnummer"),
        sa.Column("postal_code", sa.String(20), nullable=True, comment="PLZ"),
        sa.Column("city", sa.String(100), nullable=True, comment="Stadt"),
        sa.Column("country", sa.String(100), nullable=True, server_default="Deutschland", comment="Land"),

        # Steueridentifikation
        sa.Column("vat_id", sa.String(50), nullable=True, comment="USt-IdNr. (z.B. DE123456789)"),
        sa.Column("tax_number", sa.String(50), nullable=True, comment="Steuernummer"),

        # Bankverbindung
        sa.Column("iban", sa.String(34), nullable=True, comment="IBAN"),
        sa.Column("bic", sa.String(11), nullable=True, comment="BIC/SWIFT"),

        # Kontaktdaten
        sa.Column("email", sa.String(255), nullable=True, comment="Zentrale E-Mail-Adresse"),
        sa.Column("phone", sa.String(50), nullable=True, comment="Telefonnummer"),
        sa.Column("website", sa.String(255), nullable=True, comment="Webseite"),

        # Handelsregister
        sa.Column("commercial_register", sa.String(100), nullable=True, comment="Handelsregister-Nr."),
        sa.Column("court", sa.String(100), nullable=True, comment="Registergericht"),

        # Metadata
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("updated_by_id", uuid_type, nullable=True),

        # Foreign key
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    # Index for updated_at (fuer Audit-Logs)
    op.create_index("ix_company_settings_updated", "company_settings", ["updated_at"])


def downgrade() -> None:
    """Remove company_settings table."""
    op.drop_index("ix_company_settings_updated", table_name="company_settings")
    op.drop_table("company_settings")
