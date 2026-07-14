# Drift-Reconcile 2026-07 — Live-DB ↔ Alembic-Kette (Migrationen 276–279)

> **Datum:** 2026-07-14 · **Branch:** `feature/neuausrichtung-2026-07` (kein Push) ·
> **Bediener:** Claude (Fable 5) mit Gates durch Ben · **Prod-Stack:** lief durchgehend unberührt weiter.
> **Auftrag:** Phönix-Empfehlung E4 (`docs/qa-reports/phoenix-2026-07/REPORT.md` §9.4) —
> letztes ruhiges Fenster vor Go-Live 01.08.

## §1 Executive Summary

| DONE-Kriterium | Status | Beleg |
|---|---|---|
| Frisch-Beweis: leere DB → `upgrade head` (279) fehlerfrei + Doppellauf-Idempotenz | ✅ | §5 |
| Katalog-Diff Frisch↔Live: **alle 9 Dimensionen exakt 0** (Whitelist = nur Grants `ablage_app`) | ✅ | §6/§8 |
| Live-Policy-Prüfsumme vorher == nachher (`abf41a6b…` beidseitig) | ✅ | §6 |
| Tests grün (Klon: 8 passed · Live vor UND nach Neustarts: je 8 passed) | ✅ | §5/§6 |
| OpenAPI-Diff = 0 (added=[] removed=[], 1990→1990 Pfade — keine gefrorenen Module reaktiviert) | ✅ | §6 |
| Funktionsbatterie inkl. Feature-Toggle-History-Beweis grün | ✅ | §6 |
| Rollback-Anker restic **`1c67592a`** (12,169 MiB, check: no errors), Gate 2 durch Ben 14.07. | ✅ | §6 |

**Kernaussage:** Live-DB und Migrationskette sind erstmals **vollständig deckungsgleich**
(Spalten, Constraints, Indexe, Policies, Trigger, Enums, Kommentare, RLS-Flags, Funktionen —
je Diff 0). Der GoBD-relevante Feature-Toggle-Audit-Trail, der auf Live still verloren ging,
funktioniert jetzt nachweislich end-to-end. Nebenbei aktiviert: Download-Fix F-PHX-P1-4 (E3).

## §2 Ausgangslage (Drift-Karte VORHER)

Basis: Phönix §6 (13.07.), ergänzt um Neubefunde der Explore-Forensik (14.07., alle read-only belegt):

| Dimension | Befund |
|---|---|
| Root-Cause | Live per `Base.metadata.create_all()` gebootstrapped + auf Head **gestampt** → es fehlen exakt die migration-only-Objekte ohne ORM-Modell (Mig 238/239/246/250/253) |
| Tabellen nur in Frisch | `ai_chat_sessions`, `feature_toggle_history`, `morning_briefing_cache` + 4 partitionierte Parents + 44 Kinder (~377 Indexe) |
| Trigger nur in Frisch | 8 = 4 CDC (Mig 238) + 4 Dual-Write (Mig 239) |
| Views nur in Frisch | `gobd_audit_summary`, `gdpr_deletion_status` (Mig 253) |
| **NEU:** CDC-Sequence-Drift | Live fehlt `cdc_sequence_number_seq` **und** der Spalten-Default auf `change_data_capture_logs.sequence_number` (ORM `models_cdc.py` ohne `sa.Sequence`) |
| **NEU:** CDC-Tabellen | `change_data_capture_logs` (0 Zeilen) + `cdc_consumer_offsets` existieren BEIDSEITIG (ORM) — nur die Trigger fehlen |
| Enum-Waisen | Live: 68 Typen, 36 genutzt, **32 verwaist** (0 Spalten inkl. Array-Nutzung; exakte Liste in Migration 277) |
| **NEU:** `feature_toggle_history` | wird AKTIV per Roh-SQL beschrieben/gelesen (`feature_toggle_admin_service.py:62/:437`, try/except-geschluckt) → **Audit-Trail ging auf Live still verloren** |
| **NEU:** Partition-Beat | `partition-ensure-daily`/`-archive-weekly`/`-update-stats-daily` liefen auf Live seit jeher nachts ins Leere (Funktionen fehlen, Fehler geschluckt, `partition_management` = 0 Zeilen) |
| **NEU:** Umgebung | Host-Port 5434 gehört inzwischen `claude-hub-postgres` (Fremdprojekt!) — `.env`-`DATABASE_URL` ist stale; Live-Zugriff nur via `docker exec ablage-postgres` |

Live-VORHER-Sentinels (2026-07-14, `artifacts/live_before_checksums.txt`):
`alembic_version=275` · `policy_md5=abf41a6b555bca9064c1d704fbb8d271` · `rls_flags_md5=69026e8a61dd692b0934d1b095f4168d` ·
`audit_logs=563` · `documents=25` · `partition_management=0` · `change_data_capture_logs=0` · Enum-Typen=68 · `feature_toggle_history` fehlt.

## §3 Entscheidungen (Gate 1, Ben 2026-07-14 — alle per AskUserQuestion abgesegnet)

| # | Objekt(e) | Entscheidung | Begründung |
|---|---|---|---|
| 1 | `feature_toggle_history` | **(a) nachziehen** | aktiv genutzt; GoBD-Audit-Lücke schließt sich |
| 2 | `ai_chat_sessions`, `morning_briefing_cache` | **(b) aus Kette droppen** | totes Design (In-Memory-Stores), ai_chat-Modul gefroren, RAG nutzt Tabelle nicht |
| 3 | Partitions-Subsystem (Parents+Kinder+Idx+3 Fn+4 Trigger) | **(b) droppen + Beat-Jobs deaktivieren** | Cutover nie erfolgt, kein Leser, Zwillinge = Source of Truth |
| 4 | CDC (4 Trigger + Funktion) | **(b) droppen; Sequence/Default normalisieren** | kein Konsument (ABC ohne Impl.), teurer Hot-Path, unbegrenztes Wachstum; Tabellen+Admin-API bleiben |
| 5 | Views | **(a) nachziehen** | read-only, risikofrei, Compliance-Sichtbarkeit |
| 6 | 32 Enum-Waisen | **Richtung B: alle droppen** | varchar kanonisch (Models=String(50)); löst Perception §8.6 |
| 7 | Grants `ablage_app`, `alembic_version` | **(c) Whitelist** | §8 |
| 8 | **Gate 1.5** (14.07., nach Katalog-Tiefenanalyse): zweite Drift-Ebene — 8 fehlende + 5 Leichen-Spalten, 153 Defaults, 46 Nullability, 16 Typen, ~50 FK-ON-DELETE, ~93 Indexe, ~260 Kommentare, 1 Funktion | **„Volle Parität jetzt"** → Migration 278 (generiert) | DONE-Kriterium „Diff = nur Whitelist" sonst unerreichbar; Richtung Kette-kanonisch mit 6 Model-Truth-Ausnahmen |

## §4 Migrations-Design

- **276 `drift_reconcile_structural_parity`**: Abschnitte A (feature_toggle_history nachziehen, DDL exakt wie Mig 250),
  B (246-Tabellen droppen), C (Partitions-Subsystem: Trigger→Funktionen→Parents→Hilfsfunktionen→
  `partition_management`-Datenparität), D (CDC: Trigger→Funktion→DROP DEFAULT→DROP SEQUENCE),
  E (Views verbatim aus 253), F (5 Postconditions als DO-$$-Katalog-Checks, transaktionaler Abbruch).
- **277 `drop_orphaned_enum_types`**: 32× `DROP TYPE IF EXISTS` (ohne CASCADE = selbstsichernd)
  + Postcondition auf die exakte Namensliste.
- **278 `column_constraint_index_parity`** (GENERIERT aus den Katalog-Diffs, `artifacts/gen278_emit.py`,
  475 Statements): G1 8 ADD COLUMN · G2 5 Leichen-Drops (Runtime-Guard: 0 Zeilen) · G3 16 Typen
  (10 varchar→text Kette-kanonisch + 6 Model-Truth beidseitig, guarded) · G4 153 Defaults ·
  G5 46 Nullability · G6 113 Constraint-Statements (36 FK-Replaces, 28 Adds, Renames, 2 Drops) ·
  G7 120 Index-Statements (+ kpi_history_utc_day-Funktion) · G8 ~260 Kommentare (format %I/%L) ·
  Postconditions P1–P6.
- Muster Migration 275: PostgreSQL-Guard, **1 Statement = 1 op.execute** (env.py-$$-Splitter),
  `downgrade` = begründeter No-op (Audit-Trail-Schutz / kein Wiederaufbau toter Subsysteme).
- Live-Lauf mit `ALEMBIC_TX_PER_MIGRATION=1` (Commit je Revision, Postconditions sichern je Revision).

## §5 PROVE Frisch + Klon-Generalprobe (Wegwerf-Instanz `reconcile-pg`, pgvector/pg16, Netz `reconcile-net`)

| Beweis | Ergebnis |
|---|---|
| From-scratch: leere DB + init.sql-Substrat → `upgrade head` (finale Dateien) | **exit=0, Head=278**, alle Postconditions (276: P-A…P-E, 277, 278: P1–P6) passiert |
| Idempotenz-Doppellauf (Frisch UND Klon) | **0 „Running upgrade"** = No-op, Version bleibt 278 |
| **Klon-Generalprobe** (pg_dump Live → `ablage_clone`, echte 25 Dokumente) → 275→278 | **grün in einem Durchlauf** (nach 3 Generator-Fixes, s.u.) |
| Katalog-Diff Klon(278) ↔ Frisch(278), 9 Dimensionen | **COLS 0/8534 · POLICIES 0/169 · TRG 0/28 · ENUM 0/36 · COMMENTS 0/1071 · RLS-Flags 0/491 · FUNCTIONS 0/31**; CON=146/IDX=18 = pg_restore-Re-Parse-Artefakte der Klon-Methodik (alle nach Tabelle+Name gepaart, nur ARRAY-Cast-Rendering; Gegenprobe `ck_adhoc_schedule_frequency`: auf ECHTEM Live und Frisch **identisch**) |
| Tests im Wegwerf-Container gegen den Klon(278) | `test_rls_policy_guards` + `test_rls_guc_persistence` + `test_module_freeze`: **8 passed** |

**Funde der Klon-Generalprobe (alle gefixt + regeneriert, danach erneuter Voll-Beweis):**
1. **Funktions-Dimension fehlte**: `kpi_history_utc_day()` (Mig 084) existierte auf Live nicht —
   der funktionale Unique-Index `uq_kpi_history_space_kpi_date` schlug fehl (TX-Rollback wie designed).
   pg_proc-Vergleich ergab: einzige fehlende Funktion → in 278/G7 nachgezogen + Postcondition P6.
2. **FK-Replace bei Namensgleichheit**: guarded ADD wurde übersprungen, alte ON-DELETE-Aktion blieb
   → DROP CONSTRAINT IF EXISTS läuft jetzt immer vor dem ADD.
3. **2 Unique-Index-Altlasten** (`ix_event_log_event_id`, `ix_llm_cache_prompt_hash`): Rename-Ziel
   entsteht in G6 als Constraint-Backing-Index → Drop statt Rename.

**Gotchas dokumentiert:** Wegwerf-Container brauchen zusätzlich zu DB_PASSWORD/MINIO_ACCESS_KEY/
MINIO_SECRET_KEY (Runbook-Liste) inzwischen **SECRET_KEY** (pydantic-Pflichtfeld; Production-Mode
erzwingt 128-bit-Entropie + ≥25 % einzigartige Zeichen + ≥12-Zeichen-MinIO-Keys). Bewährter Weg:
`ENVIRONMENT=development DEBUG=true SECRET_KEY=$(openssl rand -base64 48)`. Ferner: Docker-Desktop-API
500t intermittierend unter Last (Retry hilft; Datenpfad unberührt); vom Harness gestoppte
`docker run`-Clients lassen den Container weiterlaufen (Monitor auf Container-Ende setzen).

## §6 PROVE Live (Gate 2, Ben 14.07. — Freigabe nach Snapshot-Nennung)

| Schritt | Ergebnis |
|---|---|
| Rollback-Anker | restic-Snapshot **`1c67592a`** (14.07. 21:13, 12,169 MiB; enthält pg_dump, `alembic_version.txt`=275, GoBD-Signierschlüssel; `restic check`: no errors) |
| Live-Lauf | `docker exec -e ALEMBIC_TX_PER_MIGRATION=1 ablage-backend … alembic upgrade head`: **275→276→277→278** in einem Durchlauf; **279** (Render-Normalisierung) nachgezogen — Live = Head **279**. Prod-Container liefen durchgehend |
| Prüfsummen | `policy_md5` vorher **==** nachher (`abf41a6b555bca9064c1d704fbb8d271`); `audit_logs`=563, `documents`=25 unversehrt; Enums 68→**36**; `feature_toggle_history` existiert; Views=2 (`artifacts/live_{before,after}_checksums.txt`) |
| **Finaler Katalog-Diff Live(279)↔Frisch(279)** | **alle 9 Dimensionen = 0**: COLS 0/8534 · CON 0/2007 · IDX 0/2764 · POLICIES 0/169 · TRG 0/28 · ENUM 0/36 · COMMENTS 0/1071 · RLS-Flags 0/491 · FUNCTIONS 0/31 |
| Tests auf Live | `test_rls_policy_guards` + `test_rls_guc_persistence` + `test_module_freeze`: **8 passed** — vor UND nach den Neustarts |
| OpenAPI | added=[] removed=[] (1990→1990 Pfade) — keine gefrorenen Module reaktiviert |
| Funktionsbatterie | Login ✓ · Dokument 200 ✓ · FTS „Bürohaus" total=14 ✓ · `prove` **verified**, Kette valid ✓ · Upload→OCR **completed nach ~25 s** → per FTS auffindbar ✓ (Beweisdokument bleibt als 26. Dokument) |
| **276-Kernbeweis** | Feature-Flag-Toggle (Superuser, PATCH 200/200): `feature_toggle_history` **0→2 Einträge**, History-API liefert beide Aktionen, Flag-Endzustand unverändert — der zuvor still verlorene GoBD-Audit-Trail schreibt jetzt real |
| Bonus (Phönix E3) | Backend-Neustart aktivierte Download-Fix F-PHX-P1-4: `GET /documents/{id}/download` → **HTTP 200**, 472/472 Bytes |

**Gate-2-Risiko-Hinweis (dokumentiert vor Freigabe):** Der Backend-Entrypoint führt bei
Container-Start `alembic upgrade head` aus (`docker/entrypoint.sh`, RUN_MIGRATIONS-Default true;
nur worker/worker-cpu/beat stehen auf false). Da `alembic/` per Bind-Mount im Container liegt,
hätte ein **ungeplanter Backend-Neustart** zwischen Migrations-Commit und Gate-2-Freigabe die
Migrationen bereits angewandt. Mitigation: VORHER-Prüfsummen gesichert (§2), Frisch-+Klon-Beweis
vor dem Commit, Fenster kurz gehalten; Hinweis stand in der Gate-2-Frage.

## §7 Begleit-Code (Commits 2–4)

- `app/workers/celery_app.py`: include `partition_maintenance`, 3 Beat-Jobs
  (`partition-ensure-daily/-archive-weekly/-update-stats-daily`) und 4 `task_routes` entfernt;
  Import-Check im Container: `partition-beats: []`, 213 Beat-Einträge verbleiben, Freeze-Mechanik intakt.
- Nachträge aus der Verifikation: `app/workers/tasks/__init__.py` importierte die Partition-Tasks
  weiterhin (Decorator-Registrierung trotz fehlendem include) **und** führte sie in `__all__`
  (latente Star-Import-Falle) — beides entfernt; `__all__`-Konsistenz verifiziert (fehlende Namen: []).
- `partition_maintenance.py`: Kopf-Docstring „DEAKTIVIERT seit Reconcile 2026-07"; Modul bleibt als Referenz.
- Neustarts: worker-cpu, worker (GPU), beat, backend — alle healthy; Backend-Entrypoint-alembic = No-op
  („Schema auf 'head'"). Beat-Log seit Neustart: **0** Partition-Referenzen; worker-cpu-Banner partition-frei.
- Commits: `6832b4616` (276–278 + Report/Artefakte) · `b193f208b` (279 + celery) ·
  `a1e888c3d` (__init__-Import) · `55dc92716` (__all__). Kein Push (Regel).

## §8 Verbleibende Whitelist (Soll-Zustand für künftige Katalog-Diffs)

| Objekt | Begründung |
|---|---|
| Grants `grantee=ablage_app` (nur Live) | opt-in `scripts/db/create_app_role.sql` — läuft bewusst nicht auf Wegwerf-DBs; Default-Privileges griffen für neue Tabellen automatisch (feature_toggle_history: SELECT/INSERT/UPDATE/DELETE ✓, R8 gegenstandslos) |
| `alembic_version`-Inhalt | naturgemäß |
| init.sql-Substrat (Extensions pg_trgm/uuid-ossp/unaccent + 2 Funktionen) | Deployment-Standard `infrastructure/postgres/init.sql` (docker-entrypoint-initdb.d) — Frisch-Vergleiche müssen es mit anwenden |

Die frühere „users-Default-Kosmetik" ist durch 278/G4 **beseitigt** (kein Whitelist-Eintrag mehr nötig).

## §9 Findings & Folgearbeiten

| # | Finding / Folgearbeit | Status |
|---|---|---|
| F-REC-1 | **Zweite Drift-Ebene unter der Phönix-Karte** (Spalten-Attribute, FK-ON-DELETE, Indexe, Kommentare, 1 Funktion) — Gate 1.5 „Volle Parität" → Migration 278 generiert | ✅ behoben + bewiesen |
| F-REC-2 | `feature_toggle_history`-Schreibpfad schluckte Fehler still (try/except) — der Audit-Trail fehlte MONATE unbemerkt. Empfehlung: solche „best-effort"-Writes mit Metrik/Alert versehen | 🟡 Folgearbeit (Backlog) |
| F-REC-3 | Host-Port 5434 gehört inzwischen `claude-hub-postgres`; `.env`-`DATABASE_URL` (localhost:5434) ist **stale** und zeigt auf eine FREMDE DB. Doku/CLAUDE.md „PostgreSQL :5434" überholt. Empfehlung: `.env`-Eintrag korrigieren/entfernen | 🟡 Folgearbeit (Ben) |
| F-REC-4 | Backend-Entrypoint migriert bei jedem Neustart automatisch (Bind-Mount + RUN_MIGRATIONS-Default true) — im Reconcile-Fenster ein dokumentiertes Risiko; generell gewollt, aber F-14 (Advisory-Lock nicht-blockierend für Nicht-Migratoren) bleibt offen | dokumentiert |
| F-REC-5 | Feature-Flags-Tabelle enthält 4 Schemathesis-Fuzzing-Leichen (Namen `0`, Keys `0/00/0…`) — kosmetisch; bei Gelegenheit aufräumen | 🟡 Backlog |
| F-REC-6 | Wegwerf-Container-Env gewachsen: SECRET_KEY jetzt Pflicht (+Entropie-Checks in Production-Mode) — Runbook-Gotcha-Liste ergänzt (§5) | ✅ dokumentiert |
| F-REC-7 | Generator + Katalog-Methodik (`artifacts/gen278_emit.py`, 9-Dimensionen-Diff) sind wiederverwendbar für künftige Paritäts-Checks (z.B. Quartals-Restore-Test koppeln) | Empfehlung |
| Offen (unverändert, Phönix E1/E2) | restic-Tagesautomatik + Hetzner-Offsite-Bein | Ben |

---
*Alle Zahlen/Zitate stammen aus real ausgeführten Kommandos dieser Session (psql, docker, pg_dump,
pytest, curl); Artefakte unter `artifacts/`.*
