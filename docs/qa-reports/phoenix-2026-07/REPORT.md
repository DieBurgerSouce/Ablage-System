# Phönix-Probe 2026-07 — Disaster-Recovery-Generalprobe + Migrationsketten-Parität

> **Datum:** 2026-07-13 · **Branch:** `feature/neuausrichtung-2026-07` (kein Push) ·
> **Bediener:** Claude (Fable 5) mit Gates durch Ben · **Prod-Stack:** lief durchgehend unberührt weiter.

## §1 Executive Summary

| DONE-Kriterium | Status | Beleg |
|---|---|---|
| Restore-Beweis grün inkl. `prove` auf restauriertem Dokument | ✅ | §4: `"verdict":"verified"`, Kette 5/5, Byte-Hash identisch |
| RTO dokumentiert | ✅ | §3: **9:33 min** bis prove-grün; 15:02 min inkl. Bugfix-Umweg |
| Paritäts-Migration committed + doppelt bewiesen | ✅ | §5: Migration 275 (`8e70ac85c`); Frisch 29→0; Klon+Live No-op per Prüfsumme |
| DR-Runbook steht | ✅ | `docs/runbooks/disaster-recovery.md` (jeder Schritt real ausgeführt) |
| Isolation nachweislich nie verletzt | ✅ | §8: eigener Stack `ablage-phoenix`; einziger Prod-Write = Gate G3 |

**Kernaussage:** Aus einem restic-Snapshot entsteht in **unter 10 Minuten** ein funktionierendes
System, dessen GoBD-Hash-Beweiskette den Restore übersteht. Die Generalprobe fand dabei
**einen produktiven Live-Bug** (Original-Download 500, gefixt) und deckte auf, dass die
**nächtliche In-Container-Backup-Schiene Postgres noch nie gesichert hat** (§7).

## §2 Backup-Realität (drei Schichten, ehrlich vermessen)

| Schicht | Design | Realität (verifiziert 13.07.) |
|---|---|---|
| A) Beat `backup-full-daily` → BackupService → `/var/backups/ablage` | täglich 02:30 | **KAPUTT**: `pg_dump`/`redis-cli`/`mc` fehlen im Worker-Image → 4/5 Quellen scheitern, nur config-Tarball entsteht; Task meldet trotzdem `task_success`. `postgres/`- und `full/`-Verzeichnis im Volume **leer seit Anlage (06.05.)**. Letzter Lauf überhaupt: 10.07. 02:30 — seit 3 Tagen feuert der Schedule nicht (Beleg: `docker logs ablage-worker-cpu`, Volume-Listing `ablage_system_backups`). |
| B) BackupService rsync-Remote | deaktiviert (durch restic ersetzt) | deaktiviert ✓ |
| C) restic 3-2-1 (`scripts/backup/restic_backup.sh`) | Host-Cron, lokal + Hetzner | **War nie operationalisiert** (kein Repo/Passwort/ENV auf dieser Maschine; DR_RUNBOOK-Restore-Protokoll leer). **In dieser Probe etabliert:** Repo `C:\restic-phoenix\repo`, Snapshot `589f1a8e` (12,164 MiB), `restic check`: *no errors*. **Offsite-Bein (Hetzner) fehlt weiterhin.** |

**Snapshot-Inhalt (Soll erfüllt):** pg_dump custom (2,8 MB, via `pg_restore --list` verifiziert),
alle MinIO-Buckets (documents: 90 Objekte, exports/thumbnails: 0), `.env`, nginx-TLS,
`alembic_version.txt` (=274), **GoBD-Signierschlüssel** (neu, §7 F-PHX-P0-2).

## §3 Restore-Protokoll + RTO (rto.csv, minutengenau)

| Uhrzeit (13.07.) | Marke | Δ kumuliert |
|---|---|---|
| 02:33:38 | restore-start (restic restore latest) | 0:00 |
| 02:33:42 | restic-restore-done (120 Dateien) | 0:04 |
| 02:34:05 | .env.phoenix aus restaurierter .env | 0:27 |
| 02:34:58 | postgres/redis/minio healthy | 1:20 |
| 02:35:32 | ablage_app-Rolle + Default-Privileges | 1:54 |
| 02:37:07 | pg_restore fertig (25 Dokumente, 110 Policies)¹ | 3:29 |
| 02:37:42 | MinIO-Mirror fertig (90/90 Objekte) | 4:04 |
| 02:39:09 | Backend healthy (/health 200) | 5:31 |
| 02:41:14 | Login grün (pruefer, Bearer) | 7:36 |
| 02:41:15 | Dokument-Abruf grün | 7:37 |
| ~02:41:17² | Suche grün (FTS „Bürohaus“: 14 Treffer) | ~7:39 |
| ~02:41:17² | **prove = „verified“ (DIE KRONE)** | **≈9:33 (Marke 02:43:11)** |
| 02:43:11 | Signierschlüssel-Roundtrip grün | 9:33 |
| 02:48:40 | Byte-Beweis grün (nach Fix F-PHX-P1-4 + Backend-Neustart) | 15:02 |
| 02:48:40 | **BEWEIS-KOMPLETT-GRUEN** | **15:02** |

¹ Erster Versuch scheiterte an `docker cp` → tmpfs-`/tmp` (§7 F-PHX-P2-1); eine verfrühte
pg-restore-Marke 02:35:34 in rto.csv ist Artefakt dieses Fehlversuchs.
² Suche/prove liefen im selben Batch wie Login (02:41:14-17); die Marken wurden erst 02:43:11
nachgetragen — konservativ wird 02:43:11 als prove-Zeitpunkt gerechnet.

**RTO (Minimal-Stack, 12-MiB-Snapshot): 9:33 min** bis zum kryptographischen Integritätsbeweis;
15:02 min für die volle Batterie inkl. Entdeckung+Fix eines echten Live-Bugs.
**RPO real:** Alter des jüngsten Snapshots — bis restic täglich läuft: unbegrenzt (§9 E1); Soll ≤24 h. PITR/WAL nicht aktiv (§7).

## §4 Beweis-Batterie (alle Aussagen aus echten Kommandos)

1. **Login** `POST /api/v1/auth/login` (pruefer@localhost.com, viewer): Token 359 Zeichen. Rate-Limit beachtet (max. 4 Versuche).
2. **Dokument** `GET /api/v1/documents/a24af4ff-…`: HTTP 200, `status:"completed"` — das Trust-Theater-K1-Dokument (Bürohaus-Müller-Rechnung, 12.07.).
3. **Suche** `GET /documents/search/?q=B%C3%BCrohaus&search_type=fts`: HTTP 200, `"total":14`.
4. **Original-Bytes** `GET /documents/…/download` (als Owner azubi@): HTTP 200, 149.851 Bytes,
   `sha256 = 5b24928acf74bc08697dc6a5e9c92455e2935f09e35840e0e491f16940364e80` — **identisch mit stored_hash**.
   (Als Nicht-Owner-Viewer liefert der Endpoint 404 — Owner/Shared-Check ist Absicht, Defense-in-Depth.)
5. **DIE KRONE** `POST /integrity/documents/…/prove` (als Prüferin):
   ```json
   {"verdict":"verified","file_hash_matches":true,"baseline_source":"archiv",
    "stored_hash":"5b24928a…","computed_hash":"5b24928a…",
    "chain":{"entries_total":5,"entries_verified":5,"valid":true},
    "tsa":{"present":false,"valid":null},
    "message_de":"Dieses Dokument ist seit dem 12.07.2026 nachweislich unverändert. …"}
   ```
   → Die Hash-Beweiskette hat den Restore überlebt. TSA lokal geprüft (kein Internet nötig); Dokument trägt keinen RFC-3161-Stempel (Hinweis, kein Fehler).
6. **GoBD-Signierschlüssel-Roundtrip:** `sha256(restaurierter Key) == sha256(Live-Key)` =
   `f8a577fd…` beidseitig — Verfahrensdoku-Signaturen bleiben nach Totalverlust verifizierbar.

## §5 Migration 275 — Paritäts-Doppel-Beweis

**Datei:** `alembic/versions/275_rls_guc_nullif_hardening_parity.py` (Commit `8e70ac85c`).
Inhalt: die DO-$$-Blöcke aus `repair_rls_guc_casts_20260712.sql` (25 Policies) und
`…_round2_20260712.sql` (4 Policies) verbatim, plus **Postcondition** (Regexe = `test_rls_policy_guards`),
die die Migration transaktional abbricht, falls ungeguardete Casts übrig blieben. downgrade = No-op (begründet).

| Beweis | Kommando | Ergebnis |
|---|---|---|
| Gap existiert | leere DB → `alembic upgrade 274` | **29 Guard-Verletzungen** (exakt 25+4 — die 500er-Klassen F-P1-001/F-P2-008 wären zurück) |
| 275 schließt ihn | leere DB → `upgrade head` (241 Migrationen) | Head=275, **0 Verletzungen**, 39 NULLIF-Policies, 110 Policies gesamt |
| Tests Frisch | pytest test_rls_policy_guards (Wegwerf-Container) | **2 passed** |
| No-op am Klon | Phönix-`ablage_system` (restaurierter Live-Stand) 274→275 | Policy-Prüfsumme **vorher==nachher** `cb0b2ce96a5914e91c99a12058c18c65` |
| Tests Klon | pytest guards + guc_persistence im Phönix-Backend | **4 passed** |
| **Live (Gate G3, von Ben freigegeben)** | `docker exec ablage-backend alembic upgrade head` (MIGRATION_DATABASE_URL) | `274 -> 275`; Prüfsumme vorher==nachher `cb0b2ce9…`; **pytest 4 passed auf Live** |

## §6 Drift-Karte Live vs. frisch migrierte DB (nach 275)

Methode: normalisierte `pg_dump --schema-only`-Diffs + 4 Katalog-Queries (Policies, RLS-Flags,
Trigger, Grants), Live nur lesend. Rohdaten lagen unter `C:\restic-phoenix\diff\` (Kennzahlen hier konserviert).

| Dimension | Diff | Bewertung |
|---|---|---|
| **RLS-Policies (Ausdrücke, Rollen, Kommandos)** | **0 Zeilen** | ✅ Paritätsziel erreicht |
| GoBD-Immutability-Trigger (domain_events, gobd_audit_chain) | beidseitig vorhanden | ✅ |
| Tabellen nur in Frisch | `ai_chat_sessions`, `feature_toggle_history`, `morning_briefing_cache` + 4 partitionierte Parents (`audit_logs_partitioned`, `document_access_logs_partitioned`, `document_lineage_events_partitioned`, `event_log_partitioned`) + 44 Partitions-Kinder | ⚠️ **Live FEHLEN diese Objekte** (historischer Stamp/Reconcile) — Folge-Reconcile empfohlen (§9 E4) |
| Trigger nur in Frisch | 8 (CDC-/Dual-Write-/Partitions-Trigger) | ⚠️ dito — NICHT ad-hoc auf Live aktivieren (ändert Schreibpfade) |
| Views nur in Frisch | `gdpr_deletion_status`, `gobd_audit_summary` | ⚠️ dito (Compliance-Sichten!) |
| Indexe nur in Frisch | 377 (fast alle auf Partitions-Kindern) | erklärt durch obige Tabellen |
| Enum-Typen nur auf Live | 9 (`processing_status`, `document_type`, `ocr_backend`, …) | bekannter offener Punkt varchar↔Enum (Perception §8.6) — Richtungsentscheidung steht aus |
| `users`-Tabelle | nur Default-Kosmetik (`daily_quota DEFAULT 100` etc. live) | unkritisch, dokumentiert |
| Grants | 493 nur-live (= `ablage_app` via `create_app_role.sql` — auf Frisch bewusst nicht gelaufen), 53 nur-fresh (Owner-Grants der Frisch-only-Tabellen) | erklärt/whitelisted |

## §7 Findings

| ID | Sev | Finding | Status |
|---|---|---|---|
| F-PHX-P0-1 | P0 | restic-3-2-1 nie operationalisiert; **kein Offsite-Bein (Hetzner)**; Quartals-Restore-Test war nie durchgeführt (Protokoll leer) | **teilbehoben**: lokales Repo + dieser erste bewiesene Restore; Offsite + Automatisierung OFFEN (§9 E1/E2) |
| F-PHX-P0-2 | P0 | GoBD-Signierschlüssel fehlte im Backup-Set → nach Totalverlust alle GoBD-/Verfahrensdoku-Signaturen unverifizierbar | **BEHOBEN** `6e4ddbe91` (stage_signing_keys) + Roundtrip bewiesen (§4.6) |
| F-PHX-P0-3 | P0 | Nächtliche Backup-Schiene (Beat→BackupService) hat **Postgres noch nie gesichert**: pg_dump/redis-cli/mc fehlen im Worker-Image; Task meldet dennoch `task_success`; Schedule feuert seit 10.07. gar nicht mehr | OFFEN (§9 E1: restic zur führenden Schicht machen; Task fixen oder ehrlich deaktivieren + Alerting korrigieren) |
| F-PHX-P1-1 | P1 | PITR/WAL nicht aktiv → RPO = Snapshot-Alter (~24 h bei täglichem Lauf) | OFFEN, bewusst (Solo-Betrieb); dokumentiert |
| F-PHX-P1-4 | P1 | **Live-Bug**: `GET /documents/{id}/download` + `…/download/pdf` → HTTP 500, `StorageService.download_file` existiert nicht (AttributeError; auf Live reproduziert) | **BEHOBEN** `f69d9e6f6` (3 Aufrufe → `download_document`); auf Phönix verifiziert (Byte-Beweis §4.4); **greift auf Prod beim nächsten Backend-Neustart** |
| F-PHX-P1-5 | P1 | Rest-Drift: Live fehlen 3 Tabellen/4 Partitions-Subsysteme/8 Trigger/2 Views ggü. Kette (§6) | OFFEN → §9 E4 |
| F-PHX-P2-1 | P2 | `scripts/backup.sh`/`scripts/restore.sh` stale und gefährlich (DB `ablage_ocr`, User `postgres`); Backup-Recovery-Guide.md ist generisches AWS-Tutorial | OFFEN (löschen/als deprecated markieren) |
| F-PHX-P2-2 | P2 | Windows-Gotchas: `docker cp`→tmpfs unmöglich; `chmod` auf NTFS No-op (Klartext-Stage nur per icacls schützbar); MSYS-Pfad-Mangling | dokumentiert im Runbook §4 |
| Korrektur | — | Früherer Verdacht „create_app_role.sql nie angewandt / RLS gebypassed“ ist **überholt**: Live-App verbindet als `ablage_app` (23 Connections, NOSUPERUSER/NOBYPASSRLS) — RLS ist im Betrieb wirksam | erledigt (11.07.-Runbook-Vorlauf) |

Hinweis (kein Bug): Original-Download verlangt Owner/Shared — eine Viewerin kann beweisen
(`prove`), aber nicht das Original ziehen. Bewusste Defense-in-Depth; im Runbook vermerkt.

## §8 Isolations-Nachweis

- Eigenes Compose-Projekt `-p ablage-phoenix`, eigene Datei `docker/phoenix/docker-compose.phoenix.yml`, Volumes `ablage-phoenix_*`, Netz `ablage-phoenix_phoenix-net` (auto-Subnet, kein 172.28.x), Ports 18000/15434/16380/19000/19001 (vorab als frei verifiziert).
- Zugriffe auf Prod ausschließlich lesend (`docker exec` pg_dump/psql-SELECT/printenv/logs, `:ro`-Volume-Mounts in Wegwerf-Containern) — mit einer Ausnahme: **Gate G3** (Migration 275, von Ben explizit freigegeben; nachweislicher No-op außer `alembic_version` 274→275).
- Prod-Container liefen durchgehend (Uptime-Verlauf 20 h → kontinuierlich steigend; kein Restart, kein Stop). Odoo unberührt. Kein `git push`.
- Secrets: nur in `C:\restic-phoenix\.env.phoenix` + Stage (icacls-beschränkt auf benfi+SYSTEM); nie in Logs/Report; Klartext-Reste werden beim Abbau gelöscht (Gate G4).

## §9 Empfehlungen (Rest-Risiken, priorisiert)

1. **E1 (vor Go-Live 01.08.): restic täglich automatisieren** — Task-Scheduler-Job (03:15) mit dem bewiesenen Windows-Aufruf (Runbook §1); Erfolgs-Metrik/Alert daran koppeln statt an den kaputten Beat-Task (F-PHX-P0-3).
2. **E2 (vor Go-Live): Hetzner-Offsite-Bein** — Storage Box + `RESTIC_REPO_REMOTE` (Anleitung steht in `scripts/backup/DR_RUNBOOK.md`); erst dann ist es 3-2-1. **restic-Passwort-Offline-Kopie (Papier/Tresor) anlegen!**
3. **E3: F-PHX-P1-4-Fix aktivieren** — beim nächsten geplanten Backend-Neustart (kein Not-Restart nötig; bis dahin ist Original-Download auf Live defekt!).
4. **E4: Drift-Reconcile Live↔Kette** (3 Tabellen, Partitions-Subsysteme, 2 Views, 8 Trigger) — als eigenes, gated Wartungsfenster; CDC-/Dual-Write-Trigger ändern Schreibpfade und gehören nicht in einen Ad-hoc-Fix. Danach erneuter Katalog-Diff (Soll: nur noch Enum/Grants-Whitelist).
5. **E5: Quartals-Restore-Test institutionalisieren** — Runbook §6; erste Protokollzeile ist mit dieser Probe gefüllt.

---
*Alle Zahlen/Zitate stammen aus real ausgeführten Kommandos dieser Session (restic, psql, curl,
pytest, docker); Kommandos zum Nachvollziehen stehen im DR-Runbook.*
