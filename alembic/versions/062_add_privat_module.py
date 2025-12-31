"""Add Privat-Modul tables for personal document management.

Revision ID: 062_add_privat_module
Revises: 061_add_personnel_module
Create Date: 2024-12-30

Privat-Modul fuer Ablage-System:
- privat_spaces: Private Bereiche (personal + shared)
- privat_space_access: Zugriffsberechtigungen
- privat_folders: Flexible Ordnerstruktur (materialized path)
- privat_documents: Dokumente mit Extra-Verschluesselung
- privat_properties: Immobilien-Stammdaten
- privat_tenants: Mieter
- privat_rental_incomes: Mieteinnahmen
- privat_utility_statements: Nebenkostenabrechnungen
- privat_vehicles: Fahrzeuge
- privat_fuel_logs: Tankbelege
- privat_insurances: Versicherungen
- privat_loans: Kredite
- privat_investments: Geldanlagen
- privat_deadlines: Fristen mit Erinnerungen
- privat_deadline_notifications: Frist-Benachrichtigungen
- privat_emergency_contacts: Vertrauenspersonen fuer Notfallzugriff
- privat_emergency_access_requests: Notfallzugriff-Anfragen

Sicherheit:
- Standard-Verschluesselung fuer alle Dokumente
- Optionale Extra-Verschluesselung mit User-Passwort (PBKDF2 + AES-256-GCM)
- Zugriff nur fuer Admins und explizit berechtigte User
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '062_add_privat_module'
down_revision = '061_add_personnel_module'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Privat-Modul tables."""

    # Check dialect for cross-database compatibility
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        json_type = postgresql.JSONB
    else:
        uuid_type = sa.String(36)
        json_type = sa.JSON

    # =========================================================================
    # 1. PRIVAT_SPACES - Private Bereiche
    # =========================================================================
    op.create_table(
        "privat_spaces",
        sa.Column("id", uuid_type, primary_key=True),

        # Typ und Owner
        sa.Column("space_type", sa.String(20), nullable=False, server_default="personal"),  # personal, shared
        sa.Column("owner_id", uuid_type, nullable=True),  # NULL bei shared spaces
        sa.Column("company_id", uuid_type, nullable=True),  # Fuer shared spaces

        # Identifikation
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), server_default="Lock"),
        sa.Column("color", sa.String(7), server_default="#6366F1"),

        # Verschluesselung
        sa.Column("encryption_enabled", sa.Boolean, server_default="true"),
        sa.Column("encryption_key_hash", sa.String(64), nullable=True),

        # Statistiken
        sa.Column("document_count", sa.Integer, server_default="0"),
        sa.Column("folder_count", sa.Integer, server_default="0"),
        sa.Column("total_size_bytes", sa.BigInteger, server_default="0"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_privat_spaces_owner_id", "privat_spaces", ["owner_id"])
    op.create_index("ix_privat_spaces_company_id", "privat_spaces", ["company_id"])
    op.create_index("ix_privat_spaces_type", "privat_spaces", ["space_type"])
    op.create_index("ix_privat_spaces_deleted_at", "privat_spaces", ["deleted_at"])

    # =========================================================================
    # 2. PRIVAT_SPACE_ACCESS - Zugriffsberechtigungen
    # =========================================================================
    op.create_table(
        "privat_space_access",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),

        # Zugriffsebene: none, view, edit, manage
        sa.Column("access_level", sa.String(20), nullable=False, server_default="view"),

        # Wer hat Zugriff erteilt
        sa.Column("granted_by_id", uuid_type, nullable=True),

        # Zeitliche Begrenzung
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("space_id", "user_id", name="uq_privat_space_access_space_user"),
    )

    op.create_index("ix_privat_space_access_space_id", "privat_space_access", ["space_id"])
    op.create_index("ix_privat_space_access_user_id", "privat_space_access", ["user_id"])
    op.create_index("ix_privat_space_access_expires_at", "privat_space_access", ["expires_at"])

    # =========================================================================
    # 3. PRIVAT_FOLDERS - Flexible Ordnerstruktur
    # =========================================================================
    op.create_table(
        "privat_folders",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("parent_id", uuid_type, nullable=True),

        # Ordner-Info
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("icon", sa.String(50), server_default="Folder"),
        sa.Column("color", sa.String(7), nullable=True),

        # Materialized Path fuer schnelle Queries
        sa.Column("path", sa.String(2000), nullable=False),
        sa.Column("level", sa.Integer, server_default="0"),

        # Sortierung
        sa.Column("sort_order", sa.Integer, server_default="0"),

        # Kategorie-Typ (fuer vordefinierte Kategorien)
        sa.Column("category_type", sa.String(50), nullable=True),  # immobilien, fahrzeuge, versicherungen, steuern

        # Statistiken
        sa.Column("document_count", sa.Integer, server_default="0"),
        sa.Column("subfolder_count", sa.Integer, server_default="0"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["privat_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_folders_space_id", "privat_folders", ["space_id"])
    op.create_index("ix_privat_folders_parent_id", "privat_folders", ["parent_id"])
    op.create_index("ix_privat_folders_path", "privat_folders", ["path"])
    op.create_index("ix_privat_folders_category_type", "privat_folders", ["category_type"])
    op.create_index("ix_privat_folders_deleted_at", "privat_folders", ["deleted_at"])

    # =========================================================================
    # 4. PRIVAT_DOCUMENTS - Private Dokumente
    # =========================================================================
    op.create_table(
        "privat_documents",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("folder_id", uuid_type, nullable=True),

        # Verknuepfung zum System-Dokument (optional)
        sa.Column("document_id", uuid_type, nullable=True),

        # Dokument-Info
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("document_type", sa.String(50), server_default="other"),

        # Datei-Info (falls kein verlinktes Document)
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),

        # Zusaetzliche Verschluesselung (optional)
        sa.Column("extra_encrypted", sa.Boolean, server_default="false"),
        sa.Column("encryption_salt", sa.String(64), nullable=True),
        sa.Column("encryption_hint", sa.String(255), nullable=True),

        # Fristenmanagement
        sa.Column("expiry_date", sa.Date, nullable=True),
        sa.Column("reminder_days", sa.Integer, nullable=True),
        sa.Column("reminder_sent", sa.Boolean, server_default="false"),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),

        # Metadaten
        sa.Column("metadata", json_type, server_default="{}"),
        sa.Column("tags", json_type, server_default="[]"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["privat_folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_documents_space_id", "privat_documents", ["space_id"])
    op.create_index("ix_privat_documents_folder_id", "privat_documents", ["folder_id"])
    op.create_index("ix_privat_documents_document_type", "privat_documents", ["document_type"])
    op.create_index("ix_privat_documents_expiry_date", "privat_documents", ["expiry_date"])
    op.create_index("ix_privat_documents_deleted_at", "privat_documents", ["deleted_at"])

    # =========================================================================
    # 5. PRIVAT_PROPERTIES - Immobilien
    # =========================================================================
    op.create_table(
        "privat_properties",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("folder_id", uuid_type, nullable=True),

        # Stammdaten
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("property_type", sa.String(50), nullable=False),  # apartment, house, commercial, land

        # Adresse
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("street_number", sa.String(20), nullable=True),
        sa.Column("postal_code", sa.String(10), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(2), server_default="DE"),

        # Kaufdaten
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("purchase_price", sa.Numeric(15, 2), nullable=True),
        sa.Column("notary_costs", sa.Numeric(10, 2), nullable=True),
        sa.Column("land_transfer_tax", sa.Numeric(10, 2), nullable=True),

        # Laufende Daten
        sa.Column("current_value", sa.Numeric(15, 2), nullable=True),
        sa.Column("value_date", sa.Date, nullable=True),

        # Grundbuch
        sa.Column("land_register_entry", sa.String(100), nullable=True),
        sa.Column("cadastral_district", sa.String(100), nullable=True),
        sa.Column("parcel_number", sa.String(50), nullable=True),

        # Flaeche
        sa.Column("living_area_sqm", sa.Numeric(10, 2), nullable=True),
        sa.Column("plot_area_sqm", sa.Numeric(10, 2), nullable=True),

        # Finanzierung
        sa.Column("loan_id", uuid_type, nullable=True),

        # Status
        sa.Column("is_rented", sa.Boolean, server_default="false"),
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["privat_folders.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_properties_space_id", "privat_properties", ["space_id"])
    op.create_index("ix_privat_properties_is_active", "privat_properties", ["is_active"])
    op.create_index("ix_privat_properties_is_rented", "privat_properties", ["is_rented"])

    # =========================================================================
    # 6. PRIVAT_TENANTS - Mieter
    # =========================================================================
    op.create_table(
        "privat_tenants",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("property_id", uuid_type, nullable=False),

        # Mieterdaten
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),

        # Mietvertrag
        sa.Column("contract_start", sa.Date, nullable=False),
        sa.Column("contract_end", sa.Date, nullable=True),  # NULL = unbefristet
        sa.Column("monthly_rent", sa.Numeric(10, 2), nullable=False),
        sa.Column("deposit", sa.Numeric(10, 2), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["property_id"], ["privat_properties.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_privat_tenants_property_id", "privat_tenants", ["property_id"])
    op.create_index("ix_privat_tenants_is_active", "privat_tenants", ["is_active"])

    # =========================================================================
    # 7. PRIVAT_RENTAL_INCOMES - Mieteinnahmen
    # =========================================================================
    op.create_table(
        "privat_rental_incomes",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("property_id", uuid_type, nullable=False),
        sa.Column("tenant_id", uuid_type, nullable=True),

        # Zahlung
        sa.Column("payment_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("payment_type", sa.String(30), server_default="rent"),  # rent, deposit, utility

        # Referenz
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["property_id"], ["privat_properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["privat_tenants.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_rental_incomes_property_id", "privat_rental_incomes", ["property_id"])
    op.create_index("ix_privat_rental_incomes_payment_date", "privat_rental_incomes", ["payment_date"])

    # =========================================================================
    # 8. PRIVAT_UTILITY_STATEMENTS - Nebenkostenabrechnungen
    # =========================================================================
    op.create_table(
        "privat_utility_statements",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("property_id", uuid_type, nullable=False),

        # Abrechnungszeitraum
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),

        # Betraege
        sa.Column("total_costs", sa.Numeric(10, 2), nullable=False),
        sa.Column("prepayments", sa.Numeric(10, 2), nullable=False),
        sa.Column("balance", sa.Numeric(10, 2), nullable=False),  # + Nachzahlung, - Guthaben

        # Details
        sa.Column("cost_breakdown", json_type, server_default="{}"),

        # Dokument-Referenz
        sa.Column("document_id", uuid_type, nullable=True),

        # Status
        sa.Column("is_settled", sa.Boolean, server_default="false"),
        sa.Column("settled_date", sa.Date, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["property_id"], ["privat_properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["privat_documents.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_utility_statements_property_id", "privat_utility_statements", ["property_id"])
    op.create_index("ix_privat_utility_statements_period", "privat_utility_statements", ["period_start", "period_end"])

    # =========================================================================
    # 9. PRIVAT_VEHICLES - Fahrzeuge
    # =========================================================================
    op.create_table(
        "privat_vehicles",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("folder_id", uuid_type, nullable=True),

        # Fahrzeugdaten
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("license_plate", sa.String(20), nullable=True),
        sa.Column("vin", sa.String(17), nullable=True),  # Fahrgestellnummer

        # Details
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("fuel_type", sa.String(30), nullable=True),  # diesel, petrol, electric, hybrid

        # Kauf/Leasing
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("purchase_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_leased", sa.Boolean, server_default="false"),
        sa.Column("lease_end", sa.Date, nullable=True),
        sa.Column("monthly_rate", sa.Numeric(10, 2), nullable=True),

        # Versicherung
        sa.Column("insurance_company", sa.String(100), nullable=True),
        sa.Column("insurance_number", sa.String(50), nullable=True),
        sa.Column("insurance_type", sa.String(30), nullable=True),  # liability, partial, full
        sa.Column("insurance_premium", sa.Numeric(10, 2), nullable=True),

        # Fristen
        sa.Column("tuev_due", sa.Date, nullable=True),
        sa.Column("inspection_due", sa.Date, nullable=True),

        # Kilometerstand
        sa.Column("current_mileage", sa.Integer, nullable=True),
        sa.Column("mileage_date", sa.Date, nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["privat_folders.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_vehicles_space_id", "privat_vehicles", ["space_id"])
    op.create_index("ix_privat_vehicles_tuev_due", "privat_vehicles", ["tuev_due"])
    op.create_index("ix_privat_vehicles_is_active", "privat_vehicles", ["is_active"])

    # =========================================================================
    # 10. PRIVAT_FUEL_LOGS - Tankbelege
    # =========================================================================
    op.create_table(
        "privat_fuel_logs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("vehicle_id", uuid_type, nullable=False),

        # Tankung
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("mileage", sa.Integer, nullable=True),
        sa.Column("liters", sa.Numeric(6, 2), nullable=True),
        sa.Column("price_per_unit", sa.Numeric(6, 3), nullable=True),
        sa.Column("total_cost", sa.Numeric(8, 2), nullable=False),

        # Tankstelle
        sa.Column("station", sa.String(100), nullable=True),

        # Beleg
        sa.Column("receipt_document_id", uuid_type, nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),

        sa.ForeignKeyConstraint(["vehicle_id"], ["privat_vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["receipt_document_id"], ["privat_documents.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_fuel_logs_vehicle_id", "privat_fuel_logs", ["vehicle_id"])
    op.create_index("ix_privat_fuel_logs_date", "privat_fuel_logs", ["date"])

    # =========================================================================
    # 11. PRIVAT_INSURANCES - Versicherungen
    # =========================================================================
    op.create_table(
        "privat_insurances",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("folder_id", uuid_type, nullable=True),

        # Police
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("insurance_type", sa.String(50), nullable=False),  # life, health, liability, household, legal
        sa.Column("policy_number", sa.String(50), nullable=True),

        # Versicherer
        sa.Column("company", sa.String(100), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=True),
        sa.Column("agent_phone", sa.String(30), nullable=True),

        # Laufzeit
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("is_auto_renew", sa.Boolean, server_default="true"),
        sa.Column("cancellation_period_months", sa.Integer, nullable=True),

        # Praemie
        sa.Column("premium_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("premium_frequency", sa.String(20), server_default="yearly"),  # monthly, quarterly, yearly

        # Leistungen
        sa.Column("coverage_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("coverage_details", json_type, server_default="{}"),
        sa.Column("deductible", sa.Numeric(10, 2), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["privat_folders.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_insurances_space_id", "privat_insurances", ["space_id"])
    op.create_index("ix_privat_insurances_type", "privat_insurances", ["insurance_type"])
    op.create_index("ix_privat_insurances_end_date", "privat_insurances", ["end_date"])
    op.create_index("ix_privat_insurances_is_active", "privat_insurances", ["is_active"])

    # =========================================================================
    # 12. PRIVAT_LOANS - Kredite
    # =========================================================================
    op.create_table(
        "privat_loans",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("folder_id", uuid_type, nullable=True),

        # Kredit
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("loan_type", sa.String(50), nullable=False),  # mortgage, personal, car
        sa.Column("loan_number", sa.String(50), nullable=True),

        # Bank
        sa.Column("bank_name", sa.String(100), nullable=False),

        # Konditionen
        sa.Column("principal_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("interest_rate", sa.Numeric(5, 3), nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),

        # Tilgung
        sa.Column("monthly_payment", sa.Numeric(10, 2), nullable=True),
        sa.Column("current_balance", sa.Numeric(15, 2), nullable=True),
        sa.Column("balance_date", sa.Date, nullable=True),

        # Sondertilgung
        sa.Column("special_repayment_allowed", sa.Boolean, server_default="false"),
        sa.Column("special_repayment_limit", sa.Numeric(10, 2), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["privat_folders.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_loans_space_id", "privat_loans", ["space_id"])
    op.create_index("ix_privat_loans_type", "privat_loans", ["loan_type"])
    op.create_index("ix_privat_loans_end_date", "privat_loans", ["end_date"])
    op.create_index("ix_privat_loans_is_active", "privat_loans", ["is_active"])

    # Nachtraeglich FK von properties zu loans
    op.create_foreign_key(
        "fk_privat_properties_loan_id",
        "privat_properties", "privat_loans",
        ["loan_id"], ["id"],
        ondelete="SET NULL"
    )

    # =========================================================================
    # 13. PRIVAT_INVESTMENTS - Geldanlagen
    # =========================================================================
    op.create_table(
        "privat_investments",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),
        sa.Column("folder_id", uuid_type, nullable=True),

        # Investment
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("investment_type", sa.String(50), nullable=False),  # stocks, bonds, funds, etf, crypto, savings

        # Bank/Depot
        sa.Column("institution", sa.String(100), nullable=True),
        sa.Column("account_number", sa.String(50), nullable=True),

        # Werte
        sa.Column("purchase_value", sa.Numeric(15, 2), nullable=True),
        sa.Column("purchase_date", sa.Date, nullable=True),
        sa.Column("current_value", sa.Numeric(15, 2), nullable=True),
        sa.Column("value_date", sa.Date, nullable=True),

        # Details
        sa.Column("isin", sa.String(12), nullable=True),
        sa.Column("quantity", sa.Numeric(15, 6), nullable=True),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["folder_id"], ["privat_folders.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_investments_space_id", "privat_investments", ["space_id"])
    op.create_index("ix_privat_investments_type", "privat_investments", ["investment_type"])
    op.create_index("ix_privat_investments_is_active", "privat_investments", ["is_active"])

    # =========================================================================
    # 14. PRIVAT_DEADLINES - Fristen
    # =========================================================================
    op.create_table(
        "privat_deadlines",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),

        # Verknuepfungen (eine davon)
        sa.Column("document_id", uuid_type, nullable=True),
        sa.Column("property_id", uuid_type, nullable=True),
        sa.Column("vehicle_id", uuid_type, nullable=True),
        sa.Column("insurance_id", uuid_type, nullable=True),
        sa.Column("loan_id", uuid_type, nullable=True),

        # Frist
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("deadline_type", sa.String(30), server_default="custom"),  # expiry, payment, renewal, cancellation, review, custom
        sa.Column("due_date", sa.Date, nullable=False),

        # Erinnerungen
        sa.Column("reminder_days", json_type, server_default="[30, 7, 1]"),
        sa.Column("reminders_sent", json_type, server_default="[]"),

        # Wiederholung
        sa.Column("is_recurring", sa.Boolean, server_default="false"),
        sa.Column("recurrence_pattern", sa.String(50), nullable=True),  # yearly, monthly, weekly
        sa.Column("next_occurrence", sa.Date, nullable=True),

        # Status
        sa.Column("is_completed", sa.Boolean, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # iCal
        sa.Column("ical_uid", sa.String(100), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column("created_by_id", uuid_type, nullable=True),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["privat_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["privat_properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["privat_vehicles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["insurance_id"], ["privat_insurances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["loan_id"], ["privat_loans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_deadlines_space_id", "privat_deadlines", ["space_id"])
    op.create_index("ix_privat_deadlines_due_date", "privat_deadlines", ["due_date"])
    op.create_index("ix_privat_deadlines_is_active", "privat_deadlines", ["is_active"])
    op.create_index("ix_privat_deadlines_is_completed", "privat_deadlines", ["is_completed"])

    # =========================================================================
    # 15. PRIVAT_DEADLINE_NOTIFICATIONS - Frist-Benachrichtigungen
    # =========================================================================
    op.create_table(
        "privat_deadline_notifications",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("deadline_id", uuid_type, nullable=False),
        sa.Column("user_id", uuid_type, nullable=False),

        # Benachrichtigung
        sa.Column("days_before", sa.Integer, nullable=False),
        sa.Column("notification_type", sa.String(30), server_default="email"),  # email, push, in_app

        # Status
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("delivered", sa.Boolean, server_default="false"),
        sa.Column("read", sa.Boolean, server_default="false"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(["deadline_id"], ["privat_deadlines.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_privat_deadline_notifications_deadline_id", "privat_deadline_notifications", ["deadline_id"])
    op.create_index("ix_privat_deadline_notifications_user_id", "privat_deadline_notifications", ["user_id"])
    op.create_index("ix_privat_deadline_notifications_sent_at", "privat_deadline_notifications", ["sent_at"])

    # =========================================================================
    # 16. PRIVAT_EMERGENCY_CONTACTS - Notfallzugriff-Kontakte
    # =========================================================================
    op.create_table(
        "privat_emergency_contacts",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("space_id", uuid_type, nullable=False),

        # Vertrauensperson
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("relationship", sa.String(50), nullable=True),  # spouse, child, lawyer, etc.

        # Zugriffskonfiguration
        sa.Column("access_level", sa.String(20), server_default="view"),
        sa.Column("access_folders", json_type, server_default="[]"),  # Leere Liste = alle

        # Aktivierung
        sa.Column("activation_delay_days", sa.Integer, server_default="30"),
        sa.Column("requires_verification", sa.Boolean, server_default="true"),

        # Status
        sa.Column("is_active", sa.Boolean, server_default="true"),

        # Token fuer spaetere Aktivierung
        sa.Column("activation_token_hash", sa.String(64), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),

        sa.ForeignKeyConstraint(["space_id"], ["privat_spaces.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_privat_emergency_contacts_space_id", "privat_emergency_contacts", ["space_id"])
    op.create_index("ix_privat_emergency_contacts_email", "privat_emergency_contacts", ["email"])
    op.create_index("ix_privat_emergency_contacts_is_active", "privat_emergency_contacts", ["is_active"])

    # =========================================================================
    # 17. PRIVAT_EMERGENCY_ACCESS_REQUESTS - Notfallzugriff-Anfragen
    # =========================================================================
    op.create_table(
        "privat_emergency_access_requests",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("contact_id", uuid_type, nullable=False),

        # Status: pending, active, granted, revoked, expired
        sa.Column("status", sa.String(20), server_default="pending"),

        # Zeitplanung
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("activation_scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),

        # Begruendung
        sa.Column("reason", sa.Text, nullable=True),

        # Verifizierung
        sa.Column("verification_code", sa.String(20), nullable=True),
        sa.Column("verification_document_id", uuid_type, nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),

        # Widerruf
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_id", uuid_type, nullable=True),
        sa.Column("revoke_reason", sa.Text, nullable=True),

        # IP/Geraet
        sa.Column("request_ip", sa.String(45), nullable=True),
        sa.Column("request_user_agent", sa.String(500), nullable=True),

        sa.ForeignKeyConstraint(["contact_id"], ["privat_emergency_contacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_privat_emergency_access_requests_contact_id", "privat_emergency_access_requests", ["contact_id"])
    op.create_index("ix_privat_emergency_access_requests_status", "privat_emergency_access_requests", ["status"])
    op.create_index("ix_privat_emergency_access_requests_activation", "privat_emergency_access_requests", ["activation_scheduled_for"])

    # =========================================================================
    # 18. NEUE PERMISSION UND ROLLE FUER PRIVAT-MODUL
    # =========================================================================
    # Neue Permissions hinzufuegen
    if is_postgres:
        op.execute("""
            INSERT INTO permissions (id, name, resource_type, action, is_system, created_at, updated_at)
            VALUES
                (gen_random_uuid(), 'privat:read', 'privat', 'read', true, NOW(), NOW()),
                (gen_random_uuid(), 'privat:write', 'privat', 'write', true, NOW(), NOW()),
                (gen_random_uuid(), 'privat:manage', 'privat', 'manage', true, NOW(), NOW()),
                (gen_random_uuid(), 'privat:admin', 'privat', 'admin', true, NOW(), NOW())
            ON CONFLICT (name) DO NOTHING;
        """)

        # Neue Rolle: privat_user
        op.execute("""
            INSERT INTO roles (id, name, display_name, description, priority, is_system, is_active, color, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                'privat_user',
                'Privat-Nutzer',
                'Zugriff auf persoenlichen Privat-Bereich',
                25,
                true,
                true,
                '#6B7280',
                NOW(),
                NOW()
            )
            ON CONFLICT (name) DO NOTHING;
        """)

        # Permissions zur Rolle zuweisen
        op.execute("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = 'privat_user'
            AND p.name IN ('privat:read', 'privat:write')
            ON CONFLICT DO NOTHING;
        """)

        # Admin-Rolle bekommt alle Privat-Permissions
        op.execute("""
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r, permissions p
            WHERE r.name = 'admin'
            AND p.name IN ('privat:read', 'privat:write', 'privat:manage', 'privat:admin')
            ON CONFLICT DO NOTHING;
        """)


def downgrade() -> None:
    """Remove Privat-Modul tables."""

    # Tabellen in umgekehrter Reihenfolge loeschen
    op.drop_table("privat_emergency_access_requests")
    op.drop_table("privat_emergency_contacts")
    op.drop_table("privat_deadline_notifications")
    op.drop_table("privat_deadlines")
    op.drop_table("privat_investments")

    # FK von properties entfernen bevor loans geloescht wird
    op.drop_constraint("fk_privat_properties_loan_id", "privat_properties", type_="foreignkey")

    op.drop_table("privat_loans")
    op.drop_table("privat_insurances")
    op.drop_table("privat_fuel_logs")
    op.drop_table("privat_vehicles")
    op.drop_table("privat_utility_statements")
    op.drop_table("privat_rental_incomes")
    op.drop_table("privat_tenants")
    op.drop_table("privat_properties")
    op.drop_table("privat_documents")
    op.drop_table("privat_folders")
    op.drop_table("privat_space_access")
    op.drop_table("privat_spaces")

    # Permissions und Rolle entfernen
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("""
            DELETE FROM role_permissions
            WHERE permission_id IN (SELECT id FROM permissions WHERE name LIKE 'privat:%');
        """)
        op.execute("DELETE FROM permissions WHERE name LIKE 'privat:%';")
        op.execute("DELETE FROM roles WHERE name = 'privat_user';")
