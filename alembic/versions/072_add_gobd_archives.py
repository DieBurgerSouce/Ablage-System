"""Add GoBD compliance tables for document archiving.

Revision ID: 072_add_gobd_archives
Revises: 071_add_company_id_to_documents
Create Date: 2026-01-02

GoBD-Zertifizierung Features:
- document_archives: Revisionssichere Archivierung mit SHA-256 Signatur
- procedure_documentation_versions: Automatische Verfahrensdokumentation
- audit_logs Erweiterung: GoBD-relevante Felder
- retention_settings: Aufbewahrungsfristen-Konfiguration

Erfuellt GoBD-Kriterien:
- Nachvollziehbarkeit (Audit-Trail)
- Unveraenderbarkeit (Hash-Signatur)
- Vollstaendigkeit (Retention-Management)
- Ordnung (Kategorisierung)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '072'
down_revision = '071'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add GoBD compliance tables."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        uuid_type = postgresql.UUID(as_uuid=True)
        jsonb_type = postgresql.JSONB()
    else:
        uuid_type = sa.String(36)
        jsonb_type = sa.JSON()

    # =========================================================================
    # 1. CREATE document_archives TABLE
    # =========================================================================
    op.create_table(
        "document_archives",
        sa.Column("id", uuid_type, primary_key=True, server_default=sa.text("gen_random_uuid()" if is_postgres else "''") if is_postgres else None),

        # Referenzen
        sa.Column("document_id", uuid_type, sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, unique=True),
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="RESTRICT"), nullable=False),

        # Signatur (GoBD: Unveraenderbarkeit)
        sa.Column("content_hash", sa.String(128), nullable=False, comment="SHA-256 Hash des Dokument-Inhalts"),
        sa.Column("hash_algorithm", sa.String(20), nullable=False, server_default="SHA-256"),
        sa.Column("signature_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signature_certificate", sa.Text(), nullable=True, comment="TSA-Zertifikat (optional)"),

        # Aufbewahrungsfristen (GoBD: Ordnung + Aufbewahrung)
        sa.Column("retention_category", sa.String(50), nullable=False, comment="invoice, contract, correspondence, etc."),
        sa.Column("retention_years", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("retention_expires_at", sa.Date(), nullable=False),
        sa.Column("retention_reminder_sent", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("retention_reminder_at", sa.DateTime(timezone=True), nullable=True),

        # Verifikationsstatus
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_verification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_failed_reason", sa.Text(), nullable=True),

        # Audit (GoBD: Nachvollziehbarkeit)
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("archived_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Metadaten
        sa.Column("archive_metadata", jsonb_type if is_postgres else sa.JSON(), nullable=True),

        comment="GoBD-konforme Archivierung: Revisionssichere Speicherung mit Hash-Signatur"
    )

    # Indizes fuer document_archives
    op.create_index("ix_document_archives_company_id", "document_archives", ["company_id"])
    op.create_index("ix_document_archives_retention_expires", "document_archives", ["retention_expires_at"])
    op.create_index("ix_document_archives_retention_category", "document_archives", ["retention_category"])
    op.create_index("ix_document_archives_is_verified", "document_archives", ["is_verified"])
    op.create_index("ix_document_archives_archived_at", "document_archives", ["archived_at"])

    # =========================================================================
    # 2. CREATE procedure_documentation_versions TABLE
    # =========================================================================
    op.create_table(
        "procedure_documentation_versions",
        sa.Column("id", uuid_type, primary_key=True, server_default=sa.text("gen_random_uuid()" if is_postgres else "''")),

        # Versionierung
        sa.Column("version", sa.String(20), nullable=False, comment="Semantic Version (z.B. 2.1.0)"),
        sa.Column("content", jsonb_type if is_postgres else sa.JSON(), nullable=False, comment="Verfahrensdokumentation als JSON"),

        # Metadaten
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("generated_by", sa.String(50), nullable=False, server_default="system"),

        # Signatur fuer Unveraenderbarkeit
        sa.Column("content_hash", sa.String(128), nullable=False),

        # Aenderungshistorie
        sa.Column("change_summary", sa.Text(), nullable=True, comment="Zusammenfassung der Aenderungen"),
        sa.Column("change_details", jsonb_type if is_postgres else sa.JSON(), nullable=True),

        # Referenz zur Company (Multi-Tenant)
        sa.Column("company_id", uuid_type, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),

        comment="GoBD Verfahrensdokumentation: Automatisch generierte und versionierte Systemdokumentation"
    )

    op.create_index("ix_procedure_docs_version", "procedure_documentation_versions", ["version"])
    op.create_index("ix_procedure_docs_company_id", "procedure_documentation_versions", ["company_id"])
    op.create_index("ix_procedure_docs_generated_at", "procedure_documentation_versions", ["generated_at"])

    # =========================================================================
    # 3. CREATE retention_settings TABLE
    # =========================================================================
    op.create_table(
        "retention_settings",
        sa.Column("id", uuid_type, primary_key=True, server_default=sa.text("gen_random_uuid()" if is_postgres else "''")),

        # Kategorie-Definition
        sa.Column("category", sa.String(50), nullable=False, unique=True, comment="z.B. invoice, contract, correspondence"),
        sa.Column("display_name", sa.String(100), nullable=False, comment="Anzeigename auf Deutsch"),
        sa.Column("description", sa.Text(), nullable=True),

        # Aufbewahrungsfristen
        sa.Column("retention_years", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("legal_basis", sa.String(255), nullable=True, comment="z.B. §147 AO, §257 HGB"),

        # Warnungen und Auto-Aktionen
        sa.Column("reminder_days_before", sa.Integer(), nullable=False, server_default="90", comment="Tage vor Ablauf fuer Warnung"),
        sa.Column("auto_delete_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("requires_approval_for_delete", sa.Boolean(), nullable=False, server_default="true"),

        # Audit
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_by_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        comment="GoBD Aufbewahrungsfristen-Konfiguration pro Dokumentkategorie"
    )

    # =========================================================================
    # 4. EXTEND audit_logs TABLE (if exists)
    # =========================================================================
    # Pruefe ob audit_logs Tabelle existiert
    if is_postgres:
        result = op.get_bind().execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'audit_logs')"
        ))
        audit_logs_exists = result.scalar()
    else:
        audit_logs_exists = False

    if audit_logs_exists:
        # GoBD-relevante Felder hinzufuegen
        op.add_column("audit_logs", sa.Column("gobd_relevant", sa.Boolean(), server_default="false"))
        op.add_column("audit_logs", sa.Column("document_hash", sa.String(128), nullable=True))
        op.add_column("audit_logs", sa.Column("action_details", jsonb_type if is_postgres else sa.JSON(), nullable=True))

        # Index fuer GoBD-relevante Aktionen
        op.create_index("ix_audit_logs_gobd", "audit_logs", ["gobd_relevant"], postgresql_where=sa.text("gobd_relevant = true") if is_postgres else None)

    # =========================================================================
    # 5. ADD is_archived TO documents TABLE
    # =========================================================================
    op.add_column("documents", sa.Column("is_archived", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("documents", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_documents_is_archived", "documents", ["is_archived"])

    # =========================================================================
    # 6. INSERT DEFAULT RETENTION SETTINGS
    # =========================================================================
    op.execute("""
        INSERT INTO retention_settings (id, category, display_name, description, retention_years, legal_basis, reminder_days_before)
        VALUES
            (gen_random_uuid(), 'invoice', 'Rechnung', 'Ein- und ausgehende Rechnungen', 10, '§147 AO, §14b UStG', 90),
            (gen_random_uuid(), 'contract', 'Vertrag', 'Vertraege und Vereinbarungen', 10, '§147 AO, §257 HGB', 180),
            (gen_random_uuid(), 'correspondence', 'Geschaeftsbrief', 'Handels- und Geschaeftsbriefe', 6, '§257 HGB', 60),
            (gen_random_uuid(), 'booking_document', 'Buchungsbeleg', 'Buchungsbelege und Kontoauszuege', 10, '§147 AO', 90),
            (gen_random_uuid(), 'annual_report', 'Jahresabschluss', 'Jahresabschluesse und Bilanzen', 10, '§257 HGB', 365),
            (gen_random_uuid(), 'tax_document', 'Steuerbeleg', 'Steuerbescheide und -erklaerungen', 10, '§147 AO', 90),
            (gen_random_uuid(), 'employee_document', 'Personalakte', 'Personalunterlagen', 10, '§257 HGB', 90),
            (gen_random_uuid(), 'other', 'Sonstiges', 'Sonstige steuerrelevante Dokumente', 6, '§147 AO', 60)
        ON CONFLICT (category) DO NOTHING
    """ if is_postgres else """
        INSERT OR IGNORE INTO retention_settings (id, category, display_name, description, retention_years, legal_basis, reminder_days_before)
        VALUES
            (lower(hex(randomblob(16))), 'invoice', 'Rechnung', 'Ein- und ausgehende Rechnungen', 10, '§147 AO, §14b UStG', 90),
            (lower(hex(randomblob(16))), 'contract', 'Vertrag', 'Vertraege und Vereinbarungen', 10, '§147 AO, §257 HGB', 180),
            (lower(hex(randomblob(16))), 'correspondence', 'Geschaeftsbrief', 'Handels- und Geschaeftsbriefe', 6, '§257 HGB', 60),
            (lower(hex(randomblob(16))), 'booking_document', 'Buchungsbeleg', 'Buchungsbelege und Kontoauszuege', 10, '§147 AO', 90),
            (lower(hex(randomblob(16))), 'annual_report', 'Jahresabschluss', 'Jahresabschluesse und Bilanzen', 10, '§257 HGB', 365),
            (lower(hex(randomblob(16))), 'tax_document', 'Steuerbeleg', 'Steuerbescheide und -erklaerungen', 10, '§147 AO', 90),
            (lower(hex(randomblob(16))), 'employee_document', 'Personalakte', 'Personalunterlagen', 10, '§257 HGB', 90),
            (lower(hex(randomblob(16))), 'other', 'Sonstiges', 'Sonstige steuerrelevante Dokumente', 6, '§147 AO', 60)
    """)


def downgrade() -> None:
    """Remove GoBD compliance tables."""

    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # Remove documents columns
    op.drop_index("ix_documents_is_archived", table_name="documents")
    op.drop_column("documents", "archived_at")
    op.drop_column("documents", "is_archived")

    # Remove audit_logs extensions (if added)
    if is_postgres:
        result = op.get_bind().execute(sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'audit_logs' AND column_name = 'gobd_relevant')"
        ))
        if result.scalar():
            op.drop_index("ix_audit_logs_gobd", table_name="audit_logs")
            op.drop_column("audit_logs", "action_details")
            op.drop_column("audit_logs", "document_hash")
            op.drop_column("audit_logs", "gobd_relevant")

    # Drop tables
    op.drop_table("retention_settings")
    op.drop_table("procedure_documentation_versions")
    op.drop_table("document_archives")
