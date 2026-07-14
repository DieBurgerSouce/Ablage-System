"""Drift-Reconcile E4 (Teil 1/2): Strukturelle Paritaet Live-DB <-> Migrationskette.

Kontext (Phoenix-DR-Probe 2026-07, REPORT.md par.6 + Explore-Forensik 2026-07-14):
Die Live-DB wurde historisch per Base.metadata.create_all() gebootstrapped und auf
Head GESTAMPT — ihr fehlen exakt die migration-only-Objekte ohne ORM-Modell aus den
Migrationen 238/239/246/250/253. Diese Migration stellt Paritaet her, in BEIDE
Richtungen (Gate-1-Entscheidungen durch Ben, 2026-07-14):

  A) feature_toggle_history NACHZIEHEN (Entscheidung a):
     Einziges Drift-Objekt mit aktivem Nutzer — feature_toggle_admin_service.py
     schreibt/liest es per Roh-SQL (INSERT Z.62, SELECT Z.437), beides in
     try/except geschluckt -> der GoBD-relevante Feature-Flag-Audit-Trail ging
     auf Live bislang STILL verloren. Definition exakt wie Migration 250
     (Constraints unbenannt -> identische PG-Auto-Namen, kein Katalog-Diff).

  B) ai_chat_sessions + morning_briefing_cache ENTFERNEN (Entscheidung b):
     Totes Design aus Migration 246 — der Code nutzt In-Memory-Stores
     (ai_chat_service.py SessionStore, morning_briefing.py _briefing_cache),
     kein ORM-Modell, keine Referenz; ai_chat gehoert zudem zum gefrorenen
     Modul MODULE_AI_SPECULATIVE. Der neue RAG-Chat nutzt die Tabelle nicht.

  C) Partitions-Subsystem ENTFERNEN (Entscheidung b):
     Migration 239 legte 4 partitionierte Schatten-Tabellen (+44 Kinder,
     ~377 Indexe), 3 Hilfsfunktionen und 4 Dual-Write-Trigger an. Der Cutover
     fand nie statt; KEIN Code liest die Schattendaten; die Zwillinge
     (audit_logs etc.) sind Source of Truth. Die Dual-Write-Trigger haetten
     auf Live jeden audit_logs-INSERT brechen lassen (Zieltabelle fehlt) —
     genau deshalb NIE ad-hoc aktivieren. partition_management (ORM-Tabelle)
     BLEIBT; nur ihre Registrierungszeilen der Schatten-Partitionen werden
     entfernt (Datenparitaet Frisch<->Live). Begleitend werden die ins Leere
     laufenden Beat-Jobs entfernt (celery_app.py, separater Commit).

  D) CDC-Trigger ENTFERNEN + Sequence-Normalisierung (Entscheidung b):
     Migration 238 haengte an documents/invoice_tracking/business_entities/
     bank_transactions AFTER-Trigger mit teurem Spalten-Diff pro UPDATE.
     Ein Konsument existiert NICHT (CDCConsumer ist ABC ohne Subklasse, kein
     Task, kein Cleanup -> unbegrenztes Wachstum ohne Leser). Die Tabellen
     change_data_capture_logs (0 Zeilen) + cdc_consumer_offsets existieren
     BEIDSEITIG (ORM-Modelle) und bleiben, ebenso die read-only Admin-API
     /api/v1/admin/cdc (OpenAPI unveraendert). Zusaetzlich normalisiert:
     Live fehlt die Sequence cdc_sequence_number_seq + der Spalten-Default
     (create_all-Artefakt, models_cdc.py ohne sa.Sequence) — die Kette wird
     auf den Live-Zustand gezogen (erst DROP DEFAULT — auf Live idempotenter
     No-op — dann DROP SEQUENCE; Reihenfolge zwingend wegen Dependency).

  E) Compliance-Views NACHZIEHEN (Entscheidung a):
     gobd_audit_summary + gdpr_deletion_status aus Migration 253, Bodies
     VERBATIM (inkl. %%-Schreibweise — identischer Ausfuehrungspfad wie 253
     -> identische Katalog-Definition Frisch<->Live). Read-only, risikofrei.

  F) Postconditions je Abschnitt (Muster Migration 275): Katalog-Checks, die
     die Migration transaktional abbrechen, falls das Zielbild nicht erreicht
     ist — identisch gruen auf frischer DB und auf Live.

WICHTIG (alembic/env.py, asyncpg): _split_sql_statements() laesst Strings mit
$$-Bloecken nur dann ungesplittet, wenn ausserhalb der $$-Bloecke hoechstens ein
Semikolon steht. Deshalb ist jedes Statement / jeder DO-Block EIN eigener
op.execute-Aufruf; niemals weitere Statements in denselben String haengen.

Idempotent in beide Richtungen: Auf Live (Objekte fehlen teils) und auf einer
from-scratch-DB (Objekte existieren aus 238/239/246/250/253) fuehrt
`upgrade head` fehlerfrei zum SELBEN Katalog. DROP-Statements bewusst OHNE
CASCADE: eine unbekannte Abhaengigkeit soll die Migration abbrechen (Rollback)
statt still Objekte mitzureissen.

Downgrade ist bewusst ein No-op, dreifach begruendet:
  1. feature_toggle_history zu droppen hiesse den GoBD-Audit-Trail zu
     vernichten — nie gewollt.
  2. Ein "korrekter" Rueckbau muesste das tote Partitions-/CDC-/246-Subsystem
     wieder aufbauen (~500 Zeilen DDL-Duplikat aus 238/239/246) — die
     Re-Einfuehrung bewusst stillgelegter Infrastruktur per Downgrade ist
     sinnfrei und riskant.
  3. Ein partieller Rueckbau (nur Views droppen) vergroesserte den Abstand
     zum 275-Kettenzustand statt ihn zu verkleinern.

Revision ID: 276
Revises: 275
Create Date: 2026-07-14
"""
from alembic import op

revision = "276"
down_revision = "275"
branch_labels = None
depends_on = None


# --- E: View-Bodies VERBATIM aus 253_gobd_gdpr_compliance_views.py ------------
# (inkl. %%-Schreibweise; NICHT umformatieren, sonst entsteht ein
#  View-Definitions-Diff zwischen Frisch [via 253] und Live [via 276].)

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


# --- F: Postconditions (je EIN DO-Block = EIN op.execute) ---------------------

_POST_A_FEATURE_TOGGLE_HISTORY = """\
DO $$
DECLARE
    n_idx INT;
BEGIN
    IF to_regclass('public.feature_toggle_history') IS NULL THEN
        RAISE EXCEPTION 'Migration 276/A: feature_toggle_history fehlt';
    END IF;
    SELECT count(*) INTO n_idx FROM pg_indexes
    WHERE schemaname = 'public' AND tablename = 'feature_toggle_history'
      AND indexname IN ('ix_feature_toggle_history_flag_name',
                        'ix_feature_toggle_history_changed_by_id',
                        'ix_feature_toggle_history_created_at');
    IF n_idx <> 3 THEN
        RAISE EXCEPTION 'Migration 276/A: feature_toggle_history-Indexe unvollstaendig (%/3)', n_idx;
    END IF;
END $$
"""

_POST_B_DEAD_TABLES_GONE = """\
DO $$
BEGIN
    IF to_regclass('public.ai_chat_sessions') IS NOT NULL THEN
        RAISE EXCEPTION 'Migration 276/B: ai_chat_sessions existiert noch';
    END IF;
    IF to_regclass('public.morning_briefing_cache') IS NOT NULL THEN
        RAISE EXCEPTION 'Migration 276/B: morning_briefing_cache existiert noch';
    END IF;
END $$
"""

_POST_C_PARTITION_SUBSYSTEM_GONE = """\
DO $$
DECLARE
    n INT;
BEGIN
    IF to_regclass('public.audit_logs_partitioned') IS NOT NULL
       OR to_regclass('public.document_access_logs_partitioned') IS NOT NULL
       OR to_regclass('public.document_lineage_events_partitioned') IS NOT NULL
       OR to_regclass('public.event_log_partitioned') IS NOT NULL THEN
        RAISE EXCEPTION 'Migration 276/C: partitionierte Parents noch vorhanden';
    END IF;
    -- Faengt das einzige Loch von DROP TABLE parent: zuvor DETACHTE Kinder
    -- (Namensschema aus create_time_partition: <parent>_pYYYY_MM).
    SELECT count(*) INTO n FROM pg_class c
    JOIN pg_namespace ns ON ns.oid = c.relnamespace
    WHERE ns.nspname = 'public'
      AND c.relkind IN ('r', 'p')
      AND c.relname ~ '^(audit_logs|document_access_logs|document_lineage_events|event_log)_partitioned_p';
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 276/C: % Partitions-Kinder ueberlebt (detached?)', n;
    END IF;
    SELECT count(*) INTO n FROM pg_proc p
    JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = 'public'
      AND p.proname IN ('create_time_partition', 'archive_old_partitions',
                        'update_partition_row_counts',
                        'trg_audit_logs_dual_write', 'trg_document_access_logs_dual_write',
                        'trg_document_lineage_events_dual_write', 'trg_event_log_dual_write');
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 276/C: % Partitions-Funktionen noch vorhanden', n;
    END IF;
    IF to_regclass('public.partition_management') IS NULL THEN
        RAISE EXCEPTION 'Migration 276/C: partition_management darf NICHT fallen (ORM-Tabelle)';
    END IF;
    SELECT count(*) INTO n FROM partition_management
    WHERE table_name IN ('audit_logs_partitioned', 'document_access_logs_partitioned',
                         'document_lineage_events_partitioned', 'event_log_partitioned');
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 276/C: % Schatten-Registrierungen in partition_management uebrig', n;
    END IF;
END $$
"""

_POST_D_CDC_GONE = """\
DO $$
DECLARE
    n INT;
BEGIN
    SELECT count(*) INTO n FROM pg_trigger t
    JOIN pg_class c ON c.oid = t.tgrelid
    WHERE NOT t.tgisinternal
      AND t.tgname IN ('cdc_documents_trigger', 'cdc_invoice_tracking_trigger',
                       'cdc_business_entities_trigger', 'cdc_bank_transactions_trigger');
    IF n > 0 THEN
        RAISE EXCEPTION 'Migration 276/D: % CDC-Trigger noch vorhanden', n;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
               WHERE ns.nspname = 'public' AND p.proname = 'cdc_capture_changes') THEN
        RAISE EXCEPTION 'Migration 276/D: cdc_capture_changes() noch vorhanden';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
               WHERE ns.nspname = 'public' AND c.relkind = 'S'
                 AND c.relname = 'cdc_sequence_number_seq') THEN
        RAISE EXCEPTION 'Migration 276/D: cdc_sequence_number_seq noch vorhanden';
    END IF;
    -- Die ORM-Tabellen MUESSEN bleiben (beidseitig vorhanden, Admin-API liest sie):
    IF to_regclass('public.change_data_capture_logs') IS NULL
       OR to_regclass('public.cdc_consumer_offsets') IS NULL THEN
        RAISE EXCEPTION 'Migration 276/D: CDC-Tabellen duerfen NICHT fallen';
    END IF;
    -- Kein Spalten-Default mehr auf sequence_number (Live-Normalzustand):
    IF EXISTS (
        SELECT 1 FROM pg_attrdef d
        JOIN pg_class c ON c.oid = d.adrelid
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = d.adnum
        WHERE c.relname = 'change_data_capture_logs' AND a.attname = 'sequence_number'
    ) THEN
        RAISE EXCEPTION 'Migration 276/D: sequence_number traegt noch einen Default';
    END IF;
END $$
"""

_POST_E_VIEWS_PRESENT = """\
DO $$
DECLARE
    n INT;
BEGIN
    SELECT count(*) INTO n FROM pg_views
    WHERE schemaname = 'public'
      AND viewname IN ('gobd_audit_summary', 'gdpr_deletion_status');
    IF n <> 2 THEN
        RAISE EXCEPTION 'Migration 276/E: Compliance-Views unvollstaendig (%/2)', n;
    END IF;
END $$
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # Alle Objekte sind PostgreSQL-only (SQLite-Test-Runs skippen).
        return

    # --- A: feature_toggle_history nachziehen (Definition exakt wie Mig 250;
    #        Constraints unbenannt -> identische PG-Auto-Namen wie beim
    #        op.create_table-Lauf der Kette). --------------------------------
    op.execute("""\
CREATE TABLE IF NOT EXISTS feature_toggle_history (
    id UUID DEFAULT gen_random_uuid() NOT NULL,
    feature_flag_id UUID REFERENCES feature_flags(id) ON DELETE SET NULL,
    flag_name VARCHAR(100) NOT NULL,
    action VARCHAR(50) NOT NULL,
    old_value JSONB,
    new_value JSONB,
    changed_by_id UUID REFERENCES users(id) ON DELETE SET NULL,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
)""")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feature_toggle_history_flag_name ON feature_toggle_history (flag_name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feature_toggle_history_changed_by_id ON feature_toggle_history (changed_by_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feature_toggle_history_created_at ON feature_toggle_history (created_at)")

    # --- B: tote 246-Tabellen entfernen (ohne CASCADE: unbekannte Abhaengige
    #        sollen abbrechen statt still mitzufallen). -----------------------
    op.execute("DROP TABLE IF EXISTS ai_chat_sessions")
    op.execute("DROP TABLE IF EXISTS morning_briefing_cache")

    # --- C: Partitions-Subsystem entfernen (Reihenfolge zwingend:
    #        Trigger -> Trigger-Funktionen -> Parents (Kinder fallen mit) ->
    #        Hilfsfunktionen -> Registrierungszeilen). ------------------------
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_to_partitioned ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_document_access_logs_to_partitioned ON document_access_logs")
    op.execute("DROP TRIGGER IF EXISTS trg_document_lineage_events_to_partitioned ON document_lineage_events")
    op.execute("DROP TRIGGER IF EXISTS trg_event_log_to_partitioned ON event_log")
    op.execute("DROP FUNCTION IF EXISTS trg_audit_logs_dual_write()")
    op.execute("DROP FUNCTION IF EXISTS trg_document_access_logs_dual_write()")
    op.execute("DROP FUNCTION IF EXISTS trg_document_lineage_events_dual_write()")
    op.execute("DROP FUNCTION IF EXISTS trg_event_log_dual_write()")
    # Attachte Partitionen (alle 44 Kinder) fallen mit dem Parent automatisch —
    # dafuer ist KEIN CASCADE noetig; CASCADE bleibt bewusst weg (s.o.).
    op.execute("DROP TABLE IF EXISTS audit_logs_partitioned")
    op.execute("DROP TABLE IF EXISTS document_access_logs_partitioned")
    op.execute("DROP TABLE IF EXISTS document_lineage_events_partitioned")
    op.execute("DROP TABLE IF EXISTS event_log_partitioned")
    op.execute("DROP FUNCTION IF EXISTS create_time_partition(TEXT, DATE, DATE)")
    op.execute("DROP FUNCTION IF EXISTS archive_old_partitions(TEXT, INTERVAL)")
    op.execute("DROP FUNCTION IF EXISTS update_partition_row_counts(TEXT)")
    op.execute("""\
DELETE FROM partition_management
WHERE table_name IN ('audit_logs_partitioned', 'document_access_logs_partitioned',
                     'document_lineage_events_partitioned', 'event_log_partitioned')""")

    # --- D: CDC-Trigger/Funktion entfernen + Sequence-Normalisierung ---------
    op.execute("DROP TRIGGER IF EXISTS cdc_documents_trigger ON documents")
    op.execute("DROP TRIGGER IF EXISTS cdc_invoice_tracking_trigger ON invoice_tracking")
    op.execute("DROP TRIGGER IF EXISTS cdc_business_entities_trigger ON business_entities")
    op.execute("DROP TRIGGER IF EXISTS cdc_bank_transactions_trigger ON bank_transactions")
    op.execute("DROP FUNCTION IF EXISTS cdc_capture_changes()")
    # Erst den Default loesen (auf Live ohne Default ein fehlerfreier No-op),
    # dann die Sequence droppen — der Default haengt per Dependency an ihr.
    op.execute("ALTER TABLE change_data_capture_logs ALTER COLUMN sequence_number DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS cdc_sequence_number_seq")

    # --- E: Compliance-Views nachziehen (Bodies verbatim aus 253) ------------
    op.execute(_GOBD_AUDIT_SUMMARY_VIEW)
    op.execute(_GDPR_DELETION_STATUS_VIEW)

    # --- F: Postconditions (transaktionaler Abbruch bei Zielverfehlung) ------
    op.execute(_POST_A_FEATURE_TOGGLE_HISTORY)
    op.execute(_POST_B_DEAD_TABLES_GONE)
    op.execute(_POST_C_PARTITION_SUBSYSTEM_GONE)
    op.execute(_POST_D_CDC_GONE)
    op.execute(_POST_E_VIEWS_PRESENT)


def downgrade() -> None:
    # Bewusst No-op: siehe Docstring (Audit-Trail-Schutz, kein Wiederaufbau
    # toter Subsysteme, partieller Rueckbau vergroesserte den Drift).
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
