"""K1 (CRITICAL): Konsolidiere alle 15 dangling Heads zu einem Head.

Vor dieser Migration hatte ``alembic heads`` 15 Eintraege - das fuehrte
zu folgenden Problemen:

* ``alembic upgrade head`` schlug mit "Multiple head revisions are present"
  fehl.
* ``.github/workflows/deploy.yml`` rief diesen Befehl ungeschuetzt auf,
  d.h. jeder Production-Deploy haette die Datenbank in einem unklaren
  Zustand lassen koennen.

Die 15 Heads sind:

* 014_add_email_verification
* 021 (add_notifications_table)
* 054 (add_mahnungswesen_tables)
* 066 (fix_search_analytics_query)
* 100_slack_integration
* 111_add_delegation_tables
* 115 (ocr_correction_feedback)
* 137_add_gobd_compliance_checks
* 147_add_document_lineage
* 151_gobd_immutable
* 203_add_psd2_banking_integration
* 208_add_notification_templates
* 211_rls_coverage_audit
* 213 (add_po_matching_and_recurring_invoice_tables)
* 261 (add_query_performance_indexes) - die "Haupt"-Linie

Diese Merge-Revision ist eine reine Strukturzusammenfuehrung - keine
Schemaaenderungen, kein Datenfluss. Nach dieser Revision liefert
``alembic heads`` genau einen Eintrag: ``262``.

Revision ID: 262
Revises: 261, 014_add_email_verification, 021, 054, 066,
         100_slack_integration, 111_add_delegation_tables, 115,
         137_add_gobd_compliance_checks, 147_add_document_lineage,
         151_gobd_immutable, 203_add_psd2_banking_integration,
         208_add_notification_templates, 211_rls_coverage_audit, 213
Create Date: 2026-05-19

Quelle: MASTER_REVIEW_2026-05-19.md, K1.
"""
from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision = "262"
down_revision = (
    "261",
    "014_add_email_verification",
    "021",
    "054",
    "066",
    "100_slack_integration",
    "111_add_delegation_tables",
    "115",
    "137_add_gobd_compliance_checks",
    "147_add_document_lineage",
    "151_gobd_immutable",
    "203_add_psd2_banking_integration",
    "208_add_notification_templates",
    "211_rls_coverage_audit",
    "213",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge-Revision - keine Schemaaenderungen erforderlich."""
    pass


def downgrade() -> None:
    """Merge-Revision - keine Schemaaenderungen erforderlich."""
    pass
