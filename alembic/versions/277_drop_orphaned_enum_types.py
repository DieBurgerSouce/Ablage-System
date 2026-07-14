"""Drift-Reconcile E4 (Teil 2/2): 32 verwaiste Enum-Typen entfernen (Richtung B).

Kontext (Phoenix-Drift-Karte par.6 "9 Enum-Typen nur auf Live" + Perception
par.8 Punkt 6 "varchar<->Enum-Richtungsentscheidung"): Auf der Live-DB
existieren 68 Enum-Typen, davon sind 32 VERWAIST — keine einzige Tabellen-/
Index-Spalte nutzt sie (verifiziert 2026-07-14 gegen pg_attribute inkl.
Array-Typen, relkind r/p/i/m/v/f). Zwei Herkunftsfamilien:

  - Legacy-Native-Enums der create_all-Aera, die NUR auf Live existieren
    (processing_status, document_type, ocr_backend, ...): Die Spalten
    (documents.status/document_type/ocr_backend_used, users.preferred_
    ocr_backend) sind laengst VARCHAR; die Typen blieben als Katalog-Leichen.
  - Von der Kette selbst erzeugte Waisen (Mig 001/064/086/104/110/111/215/217
    u.a.): CREATE TYPE ohne (verbliebene) Spaltenbindung — existieren auf
    Frisch UND Live, sind aber ueberall ungenutzt.

Richtungsentscheidung (Gate 1, Ben 2026-07-14): **varchar ist kanonisch.**
Alle Models deklarieren die betroffenen Felder als Column(String(50)) mit
Python-Enum als Wertelieferant (models.py: ProcessingStatus/DocumentType/
OCRBackend etc.); kein sa.Enum, kein native_enum. Diese Migration droppt
daher alle 32 Waisen — der Katalog konvergiert beidseitig auf 0 Waisen.

Sicherung: DROP TYPE bewusst OHNE CASCADE — bestuende wider Erwarten eine
Abhaengigkeit (Spalte/Funktion/Domain/Cast), bricht die Migration ab und
rollt transaktional zurueck, statt etwas mitzureissen. IF EXISTS macht sie
beidseitig idempotent (einige Typen existieren nur auf Live, andere nur je
nach Historie). Die Postcondition prueft exakt die 32er-Namensliste —
bewusst KEIN generischer "keine-Waisen"-Check, der kuenftige, hier nicht
entschiedene Typen faelschlich mitverurteilen wuerde.

Fixierungs-Query (Nachvollziehbarkeit; so wurde die Liste erhoben):
    SELECT t.typname FROM pg_type t
    JOIN pg_namespace ns ON ns.oid = t.typnamespace
    WHERE ns.nspname = 'public' AND t.typtype = 'e'
      AND NOT EXISTS (
          SELECT 1 FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          WHERE (a.atttypid = t.oid OR a.atttypid = t.typarray)
            AND a.attnum > 0 AND NOT a.attisdropped
            AND c.relkind IN ('r','p','i','m','v','f'))
    ORDER BY 1;

Downgrade ist bewusst ein No-op: Die Label-Listen der 32 Typen sind ueber
8+ historische Migrationen verstreut, kein Objekt referenziert sie, ihre
Wiederherstellung haette keinen Konsumenten. (Alternative — Re-CREATE aller
32 Typen mit Original-Labels — erwogen und als reiner Ballast verworfen.)

Revision ID: 277
Revises: 276
Create Date: 2026-07-14
"""
from alembic import op

revision = "277"
down_revision = "276"
branch_labels = None
depends_on = None

# Live-verifizierte Waisen-Liste (2026-07-14), alphabetisch:
_ORPHANED_ENUM_TYPES = [
    "activity_visibility",
    "approvalpriority",
    "approvalruletype",
    "approvalstatus",
    "check_item_status",
    "delegation_reason",
    "delegation_status",
    "delegation_type",
    "document_type",
    "documenttype",
    "gap_category",
    "invitation_role",
    "invitation_status",
    "movementstatus",
    "movementtype",
    "ocr_backend",
    "processing_status",
    "processingbackend",
    "processingstatus",
    "sample_source",
    "subscription_tier",
    "team_activity_type",
    "team_document_permission",
    "team_member_role",
    "team_status",
    "team_type",
    "team_visibility",
    "template_delegation_type",
    "validation_rule_type",
    "validation_status",
    "verification_status",
    "year_end_status",
]

_POSTCONDITION = """\
DO $$
DECLARE
    n INT;
    uebrig TEXT;
BEGIN
    SELECT count(*), string_agg(t.typname, ', ' ORDER BY t.typname)
      INTO n, uebrig
    FROM pg_type t
    JOIN pg_namespace ns ON ns.oid = t.typnamespace
    WHERE ns.nspname = 'public' AND t.typtype = 'e'
      AND t.typname IN (
        'activity_visibility', 'approvalpriority', 'approvalruletype',
        'approvalstatus', 'check_item_status', 'delegation_reason',
        'delegation_status', 'delegation_type', 'document_type',
        'documenttype', 'gap_category', 'invitation_role',
        'invitation_status', 'movementstatus', 'movementtype',
        'ocr_backend', 'processing_status', 'processingbackend',
        'processingstatus', 'sample_source', 'subscription_tier',
        'team_activity_type', 'team_document_permission', 'team_member_role',
        'team_status', 'team_type', 'team_visibility',
        'template_delegation_type', 'validation_rule_type',
        'validation_status', 'verification_status', 'year_end_status');
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 277: % Enum-Waisen ueberleben: %', n, uebrig;
    END IF;
END $$
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Enum-Typen existieren nur auf PostgreSQL (SQLite-Test-Runs skippen).
        return
    for enum_name in _ORPHANED_ENUM_TYPES:
        # OHNE CASCADE (selbstsichernd), IF EXISTS (beidseitig idempotent);
        # ein Statement je op.execute (env.py-Splitter, siehe Docstring 276).
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
    op.execute(_POSTCONDITION)


def downgrade() -> None:
    # Bewusst No-op: siehe Docstring — Wiederherstellung ohne Konsumenten.
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
