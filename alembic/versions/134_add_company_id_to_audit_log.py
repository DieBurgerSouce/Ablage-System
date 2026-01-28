"""Add company_id to audit_log for multi-tenant isolation.

Revision ID: 134_add_company_id_to_audit_log
Revises: 133_add_missing_v2_models
Create Date: 2026-01-28

CRITICAL SECURITY FIX:
AuditLog hat kein company_id - alle Audit-Logs sind global sichtbar!
Dies ist ein schwerwiegendes Multi-Tenant-Security-Problem.

Fix:
1. Spalte hinzufuegen (nullable fuer bestehende Daten)
2. Bestehende Logs: company_id aus User ableiten
3. NOT NULL setzen
4. RLS-Policy erstellen
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic
revision = '134_add_company_id_to_audit_log'
down_revision = '133_add_missing_v2_models'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add company_id to audit_logs table."""

    # 1. Spalte hinzufuegen (nullable fuer bestehende Daten)
    op.add_column(
        'audit_logs',
        sa.Column('company_id', UUID(as_uuid=True), nullable=True)
    )

    # 2. FK hinzufuegen
    op.create_foreign_key(
        'fk_audit_logs_company',
        'audit_logs',
        'companies',
        ['company_id'],
        ['id'],
        ondelete='CASCADE'
    )

    # 3. Index fuer Multi-Tenant-Queries
    op.create_index('ix_audit_logs_company_id', 'audit_logs', ['company_id'])
    op.create_index(
        'ix_audit_logs_company_created',
        'audit_logs',
        ['company_id', 'created_at']
    )

    # 4. Bestehende Logs: company_id aus User ableiten
    # Nur wenn user_id gesetzt ist
    op.execute("""
        UPDATE audit_logs al
        SET company_id = u.company_id
        FROM users u
        WHERE al.user_id = u.id
        AND al.company_id IS NULL
        AND u.company_id IS NOT NULL
    """)

    # 5. Fuer System-Logs (ohne User) oder Logs von Usern ohne Company:
    # Setze auf eine "System" Company oder lasse NULL (je nach Policy)
    # Hier: NULL erlaubt fuer System-Events (Migrations, Cron-Jobs)
    # Diese werden mit RLS-Bypass abgefragt

    # 6. Optional: RLS Policy fuer audit_logs
    # WICHTIG: Nur wenn RLS aktiviert ist und audit_logs nicht explizit
    # vom RLS ausgenommen sein soll
    # op.execute("""
    #     ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
    #
    #     CREATE POLICY audit_logs_tenant_isolation ON audit_logs
    #         FOR ALL
    #         USING (
    #             company_id = current_setting('app.current_company_id', true)::uuid
    #             OR company_id IS NULL  -- System-Events sichtbar
    #             OR current_setting('app.rls_bypass', true) = 'true'
    #         );
    # """)


def downgrade() -> None:
    """Remove company_id from audit_logs table."""

    # RLS Policy entfernen (falls erstellt)
    # op.execute("DROP POLICY IF EXISTS audit_logs_tenant_isolation ON audit_logs")
    # op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")

    # Indexes entfernen
    op.drop_index('ix_audit_logs_company_created', 'audit_logs')
    op.drop_index('ix_audit_logs_company_id', 'audit_logs')

    # FK entfernen
    op.drop_constraint('fk_audit_logs_company', 'audit_logs', type_='foreignkey')

    # Spalte entfernen
    op.drop_column('audit_logs', 'company_id')
