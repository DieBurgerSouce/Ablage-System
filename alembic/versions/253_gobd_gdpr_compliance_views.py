"""Add GoBD and GDPR compliance SQL views.

gobd_audit_summary: Monatliche Audit-Statistiken pro Company.
gdpr_deletion_status: Uebersicht ueber DSGVO-Loeschanfragen.

Revision ID: 253
Revises: 252
Create Date: 2026-02-22
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "253"
down_revision = "252"
branch_labels = None
depends_on = None


_GOBD_AUDIT_SUMMARY_VIEW = """\
CREATE OR REPLACE VIEW gobd_audit_summary AS
SELECT
    al.company_id,
    DATE_TRUNC('month', al.created_at) AS monat,
    COUNT(*) AS gesamt_eintraege,
    COUNT(*) FILTER (WHERE al.success = TRUE) AS erfolgreiche_aktionen,
    COUNT(*) FILTER (WHERE al.success = FALSE) AS fehlgeschlagene_aktionen,
    COUNT(DISTINCT al.user_id) AS aktive_benutzer,
    COUNT(*) FILTER (WHERE al.action LIKE 'document%%') AS dokument_aktionen,
    COUNT(*) FILTER (WHERE al.action LIKE 'delete%%' OR al.action LIKE 'remove%%') AS loesch_aktionen,
    COUNT(*) FILTER (WHERE al.action LIKE 'export%%') AS export_aktionen,
    COUNT(*) FILTER (WHERE al.action LIKE 'login%%') AS login_aktionen,
    COUNT(*) FILTER (WHERE al.integrity_hash IS NOT NULL) AS hash_verifizierte,
    MIN(al.created_at) AS erster_eintrag,
    MAX(al.created_at) AS letzter_eintrag
FROM audit_logs al
WHERE al.company_id IS NOT NULL
GROUP BY al.company_id, DATE_TRUNC('month', al.created_at)
"""

_GDPR_DELETION_STATUS_VIEW = """\
CREATE OR REPLACE VIEW gdpr_deletion_status AS
SELECT
    dr.id AS anfrage_id,
    dr.user_id,
    u.email AS benutzer_email,
    dr.status,
    dr.reason AS grund,
    dr.requested_at AS angefragt_am,
    dr.deletion_deadline AS frist,
    dr.completed_at AS abgeschlossen_am,
    dr.documents_deleted AS geloeschte_dokumente,
    dr.audit_entries_anonymized AS anonymisierte_audit_eintraege,
    dr.processed_by_id AS bearbeitet_von_id,
    CASE
        WHEN dr.status = 'completed' THEN 'Abgeschlossen'
        WHEN dr.status = 'rejected' THEN 'Abgelehnt'
        WHEN dr.status = 'cancelled' THEN 'Storniert'
        WHEN dr.status = 'processing' THEN 'In Bearbeitung'
        WHEN dr.deletion_deadline < NOW() AND dr.status = 'pending' THEN 'Ueberfaellig'
        WHEN dr.deletion_deadline < NOW() + INTERVAL '7 days' AND dr.status = 'pending' THEN 'Frist bald'
        ELSE 'Offen'
    END AS status_anzeige,
    CASE
        WHEN dr.status = 'pending' THEN
            GREATEST(0, EXTRACT(EPOCH FROM (dr.deletion_deadline - NOW())) / 86400)
        ELSE NULL
    END AS verbleibende_tage
FROM gdpr_deletion_requests dr
LEFT JOIN users u ON u.id = dr.user_id
"""


# HINWEIS (Reconcile 2026-06): Die View gdpr_deletion_status setzt die Tabelle
# `gdpr_deletion_requests` voraus. Diese ist im ORM-Modell definiert
# (models_gdpr_compliance.py: GDPRDeletionRequest), wird aber von KEINER Migration
# angelegt (023b nutzt sie nur guarded via table_exists). From-scratch fehlt sie
# daher -> "relation gdpr_deletion_requests does not exist". Hier modell-treu und
# idempotent angelegt, BEVOR die View sie referenziert.
_GDPR_DELETION_REQUESTS_TABLE = """\
CREATE TABLE IF NOT EXISTS gdpr_deletion_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    reason TEXT,
    deletion_deadline TIMESTAMPTZ NOT NULL,
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    processed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    deletion_reason VARCHAR(255),
    documents_deleted INTEGER DEFAULT 0,
    audit_entries_anonymized INTEGER DEFAULT 0
)
"""


def upgrade() -> None:
    op.execute(_GDPR_DELETION_REQUESTS_TABLE)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_gdpr_deletion_requests_user_id "
        "ON gdpr_deletion_requests (user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_gdpr_deletion_requests_status "
        "ON gdpr_deletion_requests (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_gdpr_deletion_requests_deadline "
        "ON gdpr_deletion_requests (deletion_deadline)"
    )
    op.execute(_GOBD_AUDIT_SUMMARY_VIEW)
    op.execute(_GDPR_DELETION_STATUS_VIEW)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS gdpr_deletion_status")
    op.execute("DROP VIEW IF EXISTS gobd_audit_summary")
    # Tabelle gehoert modellseitig zu GDPRDeletionRequest; hier mit-angelegt, daher
    # auch hier idempotent entfernen.
    op.execute("DROP TABLE IF EXISTS gdpr_deletion_requests")
