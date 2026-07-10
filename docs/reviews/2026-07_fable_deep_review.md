# Adversarial Deep Review — Neuausrichtung vor Master-Merge

**Reviewer-Rolle:** Externer Pentester + GoBD-Prüfer + Staff-Engineer (Claude Fable 5, autonomer Loop)
**Branch:** `feature/neuausrichtung-2026-07` (31 Commits vor `master`, nicht gepusht)
**Start:** 2026-07-09 · **Methode:** Angriffshypothesen → Beweis über den LIVE-Stack (curl/pytest/SQL/celery inspect), nie nur Code lesen → Klassifikation P0/P1/P2 → P0/P1 sofort fixen + Regressionstest.
**Live-Stack:** 21 Container `healthy` (backend :8000, worker, worker-cpu, beat, postgres :5434, redis, minio, pgbouncer, clamav, vault, watchdog, Monitoring).

---

## Warum dieser Review

Der Branch gilt als „code-komplett, 974 Tests grün, Stack live deployt". Genau deshalb ist Skepsis angebracht: Die vier jüngsten Commits sind bereits Nachbesserungen *nach* dem „code-komplett"-Stand — jeder betraf eine Kernfunktion, die grün getestet und trotzdem tot war:

| Commit | Datum | Latenter Defekt trotz grüner Tests |
|---|---|---|
| `2497ae5e0` | 2026-07-09 21:48 | Priority-Sub-Queues (`ocr_high:9`) + `--pool=solo`-Worker → **OCR/Embedding liefen nie automatisch**; jeder Upload blieb ewig `pending`. |
| `89b295881` | 2026-07-09 20:24 | Nicht-reentranter `threading.Lock` → **Sync-Engine-Init deadlockt beim Cold-Start** mit sich selbst → GPU-Worker blockiert. |
| `4fd5238c4` | 2026-07-09 17:37 | `set_rls_context` war toter Code mit asyncpg-inkompatibler Syntax → unter `ablage_app` (NOBYPASSRLS) lieferten alle Policies 0 Zeilen → **Browser-Upload-Kette + `/companies/current` kaputt**. |
| `fa0b53ae1` | 2026-07-09 00:48 | restic-Skript auf dem echten Host **nicht lauffähig** (Socket-Auth, MinIO ohne Host-Port). |

Muster: **Unit-Tests bewiesen Code, nicht Verhalten.** Der Review prüft deshalb konsequent gegen den laufenden Stack.

---

## Zwischenstand (Iteration 1 abgeschlossen, Iteration 2 läuft)

**7 P1 gefixt + getestet + committet** (jeder Fix mit Regressionstest, TDD-Rot bewiesen): F-01 (Freeze-Leck finance.py), F-02 (Freeze-Regressionstest), F-03 (GoBD-Hash-Gate), F-06 (Push Falsch-Partner), F-07 (Push Doppel-Push), F-08 (Push Fremdwährung), F-12 (tote monitoring-Queue). **1 P2 gefixt** (F-10 Cashflow-Beat).

**Die schweren P0-Kandidaten wurden live widerlegt** (Evidenz, dass geprüft wurde): RLS light real wirksam (ablage_app kein Superuser, Kern-Tabellen RLS forced), kein pgbouncer-Cross-Tenant-Leak (App direkt an postgres + transaktions-lokale GUC), CORS fail-closed, CSRF-Fix ohne Schwächung. Migrations-Konsistenz bestätigt (Live-DB `alembic_version=271`, Single-Head, keine neue Migration im Branch).

**Verifikation:** 289 Unit/Contract-Tests grün über alle betroffenen Bereiche; `tsc -b` 0 Fehler; 21 Container weiter healthy; Live-OpenAPI/curl/SQL-Beweise dokumentiert.

**Offene P2** (dokumentiert, nicht merge-blockierend): F-04/F-05 (Mirror Overlap-Lock/Cursor-Full-Rescan), F-09 (Celery-Eager-Import), F-11 (predictive-actions Dunning-Write — Bens Scope), F-13 (Queue-Length-Metrik tot), F-14 (entrypoint-Race), S-04 (M-06-Rest), + atk-push-P2s (Gutschrift/tax_ids/odoo_company_id).

**Verdikt:** steht nach Iteration 2 (DoD: 2 Runden in Folge 0 neue P0/P1).

---

## Findings-Register

Klassifikation: **P0** = merge-blockierend (Datenverlust, Sicherheitsloch, GoBD-Bruch, Odoo-Korruption) · **P1** = merge-blockierend (falsche Daten, tote Kernfunktion) · **P2** = dokumentieren, nicht blockieren.

| ID | Fläche | Titel | Klasse | Status |
|---|---|---|---|---|
| F-01 | Freeze | Misch-Router `finance.py` umgeht Freeze (21 Pfade live) | P1 | ✅ Gefixt + live bewiesen |
| F-02 | Freeze | Kein Regressionstest iteriert die echte App gegen die Registry (DoD §8.2-Lücke) | P1 | ✅ Test gebaut, 3/3 grün |
| F-03 | Mirror | GoBD-Spiegel verifiziert Hash nie gegen `ir.attachment.checksum` (R3) | P1 | ✅ Gefixt + getestet |
| F-04 | Mirror | Kein Overlap-Lock; `documents` ohne checksum-Unique → Duplikat-Pfad + Fehl-Alarme unter Concurrency | P2 | 📋 Dokumentiert |
| F-05 | Mirror | Unparsebarer Cursor → Full-Rescan der Historie (1 RPC/Move) → Odoo-SaaS-Drosselung (R2) | P2 | 📋 Dokumentiert |
| F-06 | Push | Partner-Matching Name-`ilike` ohne Wildcard-Escaping/Mindestlänge/Nachprüfung → Falsch-Partner | P1 | ✅ Gefixt + getestet |
| F-07 | Push | Doppel-Push: `odoo_move_id` erst nach Odoo-create committet → Retry/verlorene RPC-Antwort → zweiter Entwurf | P1 | ✅ Gefixt + getestet |
| F-08 | Push | `currency_id` wird nie an Odoo gesendet → Fremdwährung bucht in EUR-Default | P1 | ✅ Gefixt + getestet |
| F-09 | Freeze | Celery-Eager-Import (`tasks/__init__.py`) registriert alle 22 gefrorenen Task-Module → include-Freeze wirkungslos (nur Beat-Prune schützt) | P2 | 📋 Dokumentiert (live bestätigt) |
| F-10 | Freeze | Beat `extended-alerts-cashflow-daily` fährt täglich den gefrorenen CashflowPredictionService | P2 | ✅ Gefixt + getestet |
| F-11 | Freeze | Aktiver `predictive-actions`-Router schreibt in gefrorene InvoiceTracking-Domäne (`dunning_level++`) | P2 | 📋 Dokumentiert (Bens Scope) |
| F-12 | Ops | Tote `monitoring`-Queue: 3 aktive Beats feuern, kein Konsument → 207 Msgs gestaut, Feature tot | P1 | ✅ Gefixt + live bewiesen |
| S-01 | Security | RLS-Rollen-Setup **korrekt** (Backend=ablage_app, kein Superuser/Bypass, direkt an postgres) — ABER `documents`-Policies permissiv (siehe F-15) | — | ⚠️ Teilweise (korrigiert) |
| F-15 | Security | `documents`-RLS: permissive OR-Policies mit `current_user_id IS NULL`/`company_id IS NULL`-Escapes → ohne Kontext alle Dokumente sichtbar (DoD-8-Verletzung) | P1 | ⛔ RE-GATE (Fix unsicher standalone) |
| F-16 | Security/Regression | Kein Background-Worker setzt RLS-Kontext → worker-initiierte Dokument-Anlage (Mirror/Import) wird von RLS **abgelehnt**; Escapes sind load-bearing für Worker-Reads | P1 | ⛔ RE-GATE (mit F-15 gekoppelt) |
| S-02 | Security | pgbouncer-Cross-Tenant-Leak **ausgeschlossen** (App direkt an postgres; GUC transaktions-lokal) | — | ✅ Widerlegt (verifiziert) |
| S-03 | Security | CORS-Reflection + CSRF-Schwächung **ausgeschlossen** (fail-closed; CSRF-Fix nur Rotation) | — | ✅ Widerlegt (verifiziert) |
| S-04 | Security | M-06-Rest: 3 einvoice-POSTs im Code ohne `current_user` (nur durch Freeze/404 geschützt) | P2 | 📋 Defense-in-Depth |
| F-13 | Ops | `ablage_celery_queue_length`-Metrik nie emittiert (`update_queue_metrics` ungenutzt) → Queue-Backlog-Alerts tot → **Wurzel des F-12-Blindflecks** | P2 | ✅ Gefixt + live bewiesen |
| F-14 | Ops | entrypoint: Nicht-Migratoren warten nicht auf den Migrator → Fresh-Clone-Race (halb-migriertes Schema) | P2 | 📋 Dokumentiert (atk-ops: durch `depends_on: healthy` gemildert) |
| S-05 | Security | Dev-Stack in `DEBUG=True` → Cookies ohne `Secure`, kein App-HSTS über :443; Security-Flags an `DEBUG` statt `is_production` | P2 | 📋 Deploy-Posture |
| S-06 | Ops | `datev`-Queue geroutet, kein Konsument (inert durch Freeze; DoD-9 formal verletzt) | P2 | 📋 Dokumentiert |
| F-17 | Freeze | FE/BE-Freeze-Drift: 5 Module FE-frozen aber BE aktiv | P2 | ✅ Gefixt (Ben-Intent: ml_dashboard/ki_pipeline/predictive_health BE-eingefroren; adhoc/expenses aktiv, FE bereinigt) |
| F-18 | Security | `GET /reports/adhoc/data-sources` **unauth** → leakt interne Tabellennamen | P2 | ✅ Gefixt (auth-pflichtig, live 200→403) |
| F-19 | Push | F-07-Dedup: ref-Kollision (gleiche invoice_number/Partner) → stille AP-Unterbuchung | P2 | ✅ Ref-Kollision gefixt (invoice_date im Dedupe-Schlüssel); PDF-lose Adoption bleibt dokumentierter Randfall |
| F-20 | Ops | F-12 aktiviert `generate_all_alerts` ohne per-Typ-Dedup → In-Memory-Alert-Store wächst (latenter Vor-Bug, kein User-Spam) | P2 | 📋 Dokumentiert |
| R-06 | Test | F-02-Freeze-Test war hardcodiert (10/13 Keys) → neue Module ungedeckt | P2 | ✅ Gefixt (Coverage-Assertion) |
| F-21 | Security/Bug | Privat-ACL-Gates fragen `PrivatSpaceAccess.is_active` (existiert nicht) → AttributeError/500 auf Nicht-Owner-Zweig → DoD-8 (403) verletzt + Shared-Spaces tot | P1 | ✅ Gefixt + getestet |
| F-22 | Security | NLQ-RAG (`nlq_service._process_chat_query`) ruft `semantic_search` **ohne user_id** → Cross-Tenant-Chunk-Leak — aktuell hinter gefrorenem ai_speculative (404) | P2→P0-bei-Reaktivierung | 📋 Reaktivierungs-Sperre |
| F-23 | Ops | Cross-Channel-Dedupe-Asymmetrie: Mirror company-scoped, Import owner-scoped → möglicher Duplikat-Document (kein Leak) | P2 | 📋 Dokumentiert |

*(Register wird pro Iteration ergänzt.)*

---

## Iteration 1

### F-01 — Misch-Router `finance.py` umgeht die Freeze-Mechanik · **P1**

**Hypothese:** Nicht alle gefrorenen Domänen-Pfade sind wirklich 404 — ein plain registrierter Router trägt Routen einer gefrorenen Domäne.

**Beweis (Live-OpenAPI gegen den laufenden Backend-Container):**
```
$ curl -s http://localhost:8000/openapi.json | python -c "... zähle Pfade je Präfix"
total_paths 1976
einvoice 0 · banking 0 · accounting 0 · holding 0 · kasse 0 · mahn 0 · document-chains 0   → M-06 zu, Freeze-Kern wirkt
finance  21  e.g. /api/v1/finance/years, /api/v1/finance/liquidity/forecast
```
`MODULE_FINANCE` steht in `FROZEN_BY_DEFAULT` (`app/core/module_registry.py:59,113`), aber `app/main.py:1497` registriert `finance_router` **plain** via `app.include_router(...)`. `app/api/v1/finance.py` (einziger Router mit `prefix="/finance"`, Z. 76) mischt **zwei Domänen**:

- **aktiv/legitim** (Jahres-Archiv, `document_services/finance_service.py`): `/years*`, `/aggregations`, `/documents/*` (GET/PATCH/DELETE/history/bulk-delete/bulk-update/export)
- **gefroren laut Plan §4a** (Cashflow-Forecast): `/liquidity/forecast|bottlenecks|waterfall|anomalies` (L1850/1993/2085/2169) — im Frontend ausschließlich vom **gefrorenen** `banking.ts`-Layer konsumiert (`frontend/src/lib/api/services/banking.ts:692–728`). Grenzfälle `/deadlines`, `/anomalies/*` in Klärung.

**Severity:** Nicht ausnutzbar (alle betroffenen Routen sind auth-geschützt, `require_finance_read`, und ohne die gefrorenen Banking-Daten funktionslos). Aber **Bruch der Freeze-Zusage** (Plan §4a) und der **DoD §8.2** („Sidebar/Routen zeigen nur aktive Module"). Strukturell: `include_module_router` gated auf Router-Granularität und kann einen Misch-Router prinzipiell nicht spalten.

**Grenzfall-Klärung (Agent classify-finance):** `/deadlines`, `/anomalies/check`, `/anomalies/dashboard` bleiben **aktiv** — sie laufen rein über `Document`/`AIDecision` (owner-scoped, kein Banking/Cashflow) und werden von aktiven Views bedient (`FinanzenPage`, `FinanceStatusWidget`). Nur die 4 `/liquidity/*` (eigene Schemas, ab Z. 1728, vom gefrorenen `banking.ts` konsumiert) sind gefroren.

**Fix (Router-Split):** In `app/api/v1/finance.py` zweiter `liquidity_router = APIRouter(prefix="/finance")`; die 4 `/liquidity/*`-Dekoratoren auf ihn umgestellt (Handler unverändert). In `app/main.py` bleibt `finance_router` plain; neu `include_module_router(app, finance_liquidity_router, MODULE_FINANCE, prefix="/api/v1")`. Aufteilung exakt: 17 aktive + 4 gefrorene Route-Dekoratoren = 21.

**Verifikation (Live, nach `docker compose restart backend`):**
```
$ curl -s http://localhost:8000/openapi.json | ...     # finance-Pfade: 21 → 14
  /finance/years            OK (aktiv)   /finance/deadlines           OK (aktiv)
  /finance/aggregations     OK (aktiv)   /finance/anomalies/dashboard OK (aktiv)
  /finance/liquidity/forecast    WEG     /finance/liquidity/waterfall    WEG
  /finance/liquidity/bottlenecks WEG     /finance/liquidity/anomalies    WEG
$ curl -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/finance/liquidity/forecast  → 404
$ curl -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/finance/years               → 403 (aktiv, Auth nötig)
```

**Status:** ✅ **Gefixt + live bewiesen.** F-02-Contract-Test deckt es dauerhaft ab.

---

### F-02 — Freeze-Regressionstest prüft nur einen Dummy-Router · **P1**

**Hypothese:** Der Freeze ist nicht regressionsgeschützt — ein künftiges `app.include_router(banking_router)` hebt ihn still auf, ohne dass ein Test rot wird.

**Beweis:** `tests/unit/core/test_module_registry.py` erzeugt eine leere `FastAPI()` mit einem **Dummy**-`/api/v1/dummy/ping`-Router (`_openapi_paths`, Z. 43–51) und prüft daran das Verhalten von `include_module_router`. Es gibt **keinen** Test, der die *echte* `app` importiert und ihre OpenAPI-Pfade gegen `KNOWN_OPTIONAL_MODULES` iteriert. Genau deshalb blieb F-01 unentdeckt. DoD §8.2 verlangt aber „automatisierter Test iteriert die Registry → alle gefrorenen Endpoints 404".

**Fix:** Neuer Test `tests/contract/test_module_freeze.py` — lädt die reale `app.main.app` (Fixture `openapi_schema` aus `tests/contract/conftest.py`) und prüft dreifach: (1) kein Pfad unter einem gefrorenen Router-Präfix (10 live-verifizierte Präfixe), (2) die F-01-Leck-Pfade (`/finance/liquidity/*`) absent, (3) die aktiven Archiv-Pfade (`/finance/years`, `/finance/aggregations`) präsent (Über-Freeze-Schutz).

**TDD-Rot-Beweis (vor dem F-01-Fix, im backend-Container):**
```
$ docker compose exec -T -e CUDA_VISIBLE_DEVICES='' backend python -m pytest tests/contract/test_module_freeze.py -v
FAILED test_frozen_finance_leak_paths_absent - AssertionError: Misch-Router-Leck (F-01): gefrorene Cashflow-Pfade weiterhin live
2 passed, 1 failed in 14.69s
```
Genau ein Test rot (das Leck), zwei grün → der Test ist präzise, kein Fehlalarm und kein Über-Einfrieren. Nach dem F-01-Fix muss er 3/3 grün sein.

**Status:** ✅ **3/3 grün** nach F-01-Fix (backend-Container). Vor dem Fix: 1 rot (Leck), 2 grün → präzise.

---

### F-03 — GoBD-Spiegel verifiziert den Hash nie gegen `ir.attachment.checksum` · **P1** · ✅ GEFIXT

**Hypothese:** Ein still-korrupter XML-RPC-Transfer (Bytes verändert, aber noch base64-dekodierbar) wird mit einem gültig aussehenden GoBD-Hash der *korrupten* Bytes unveränderbar archiviert — es gibt kein Integritätsgate gegen die Quell-Prüfsumme.

**Beweis (Code-Trace, `app/services/erp/odoo_mirror_service.py`):**
- Z. 338: `sha256 = hashlib.sha256(content).hexdigest()` — lokaler Dedupe-Hash.
- Z. 414: `odoo_checksum = attachment_meta.get("checksum")` — **gelesen**, aber nur in `document_metadata["odoo_checksum"]` (Z. 437) und Archiv-Metadaten (Z. 459) **abgelegt**, nie verglichen.
- `app/services/erp/odoo_connector.py:795–796` (Docstring): „Der checksum in den Metadaten dient der **Hash-Verifikation im GoBD-Spiegel**." → Die Verifikation war *by design* vorgesehen und wurde schlicht nie verdrahtet. Der Connector fetcht das Feld (Z. 812–813).

Damit verletzt der Spiegel Plan-Risiko **R3** (SHA256 gegen `ir.attachment.checksum`). Gerade der Zweck der „vertrauenswürdigen Zweitablage" ist ungesichert. Merge-relevant, weil der Mirror-Code gemergt wird; noch nicht produktiv-akut (keine aktive `ERPConnection` vor Odoo-Go-Live).

**Wichtige Nuance:** Odoos `ir.attachment.checksum` ist **SHA-1** (Odoo `_compute_checksum = hashlib.sha1`), nicht SHA-256. Das interne `Document.checksum` (SHA-256) taugt daher *nicht* zum Abgleich — es braucht einen separaten SHA-1-Vergleich.

**Fix:** Integritätsgate in `_mirror_move`, direkt nach dem Attachment-Download (vor Dedupe/Persistenz): wenn `attachment_meta["checksum"]` gesetzt, `hashlib.sha1(content).hexdigest()` bilden und case-insensitiv vergleichen. Bei Mismatch `RuntimeError` → greift der bestehende per-Move-Rollback + Cursor-Schutz (`run_incremental` fängt die Exception, `had_error`, Cursor bleibt stehen) → der Anhang wird im nächsten Lauf erneut geladen statt korrupt archiviert. Strukturiertes Error-Log `odoo_mirror_checksum_mismatch`.

**Verifikation:**
```
$ docker compose exec -T -e CUDA_VISIBLE_DEVICES='' backend python -m pytest tests/unit/services/erp/test_odoo_mirror_service.py -q
28 passed in 1.07s
```
Neue Tests `test_checksum_mismatch_blocks_gobd_archival` (Mismatch → `errors==1`, kein persist/dedupe, Cursor bleibt) + `test_matching_checksum_passes_gate` (Gegenprobe). Zwei bestehende `run_incremental`-Tests nutzten den Fake-Checksum `"sha1x"` → auf den echten SHA-1 des Testinhalts realdatiert (sonst hätte das Gate sie berechtigterweise rot gemeldet).
**TDD-Rot-Beweis:** Service-Datei per `git stash` kurz auf HEAD zurückgesetzt → `test_checksum_mismatch_blocks_gobd_archival` FAILED (`assert 0 == 1`, kein Gate → Move erfolgreich); mit Gate grün.

---

### F-04 — Kein Overlap-Lock; `documents` ohne checksum-Unique · **P2**

**Beweis (Live-DB gegen den laufenden postgres-Container, via atk-mirror verifiziert):**
```
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='erp_entity_mappings'::regclass;
→ uq_erp_entity_mappings_remote UNIQUE (connection_id, entity_type, remote_id)   -- harte Schranke ✔
SELECT indexdef FROM pg_indexes WHERE tablename='documents' AND indexdef ILIKE '%checksum%';
→ nur ix_documents_checksum (plain btree)   -- KEIN Unique
```
`odoo_mirror_incremental` (`odoo_tasks.py:884`) hat **kein** Redis/DB-Advisory-Lock; Queue `erp` läuft auf `worker-cpu --pool=prefork --concurrency=4`. Dauert ein Lauf > 30 min (Beat-Intervall), kann ein zweiter Beat-Task parallel starten. Der `erp_entity_mappings`-Unique verhindert Duplikate *pro Attachment* hart (Verlierer → `UniqueViolation` → per-Move-Rollback). **Restlücke:** Zwei *inhaltsgleiche* Attachments mit *verschiedenen* `remote_id`s in überlappenden Läufen bestehen beide Dedupe-Stufe (b) (reines SELECT-dann-INSERT ohne Unique auf `documents.checksum`) → 2 Documents mit identischem Hash. Zusätzlich treiben spurious `UniqueViolation`s `consecutive_failures` künstlich hoch → falscher `is_paused`/Slack-Stall-Alert nach 5.

**Empfehlung:** Redis-Lock (`SETNX`/celery-once) um `odoo_mirror_incremental` je `connection_id` — sauberer als ein partieller Unique auf `documents(company_id, checksum)`, der legitime cross-source-Gleichinhalte bräche. **Nicht merge-blockierend** (überlappende Läufe erst bei großem Bestand nach Go-Live realistisch), aber vor Produktivbetrieb einzuplanen.

---

### F-05 — Unparsebarer Cursor → Full-Rescan der Historie · **P2**

**Beweis:** `_cursor_with_overlap` (Z. ~503–516) gibt bei `ValueError` `None` zurück → Domain **ohne** `write_date`-Filter → Sync scannt ab dem ältesten Move (auf `batch_limit=200`/Lauf gekappt, kein Voll-Dump). Pro Move ein `list_attachments`-RPC **vor** dem Mapping-Check (Z. ~305) — auch für längst gespiegelte Moves → massiver RPC-Churn gegen Odoo-SaaS (Plan-Risiko **R2**). Trigger selten: Cursor round-trippt exakt `str(move["write_date"])` im Format `%Y-%m-%d %H:%M:%S` (Odoo liefert das ohne Mikrosekunden/TZ), `strptime` scheitert real nur bei externer Korruption (Migration/Handedit). Selbstheilend (nächster Lauf setzt gültigen Cursor).

**Empfehlung:** In `_cursor_with_overlap` tolerant parsen (mehrere Formate inkl. `.%f`/ISO); bei endgültigem Fehlschlag den letzten known-good Cursor behalten statt den Filter komplett zu droppen; `logger.warning` → Alert-Level. **Nicht merge-blockierend.**

---

### F-06 — Partner-Matching kann den falschen Lieferanten treffen · **P1** · ✅ GEFIXT

**Hypothese (atk-push H1):** Die Name-`ilike`-Stufe der Matching-Kaskade pusht auf eine rechtlich andere Firma.

**Beweis:** `odoo_connector.py:1146–1157` — `["name", "ilike", name]`, limit 5, **kein** Wildcard-Escaping, **keine** Mindestlänge. Odoo-`ilike` wrappt zu `%name%` und behandelt `%`/`_` im Wert als SQL-Wildcards. Substring-Falle: OCR liest „Meier GmbH", Odoo hat nur „Meier GmbH & Co. KG" → genau 1 Treffer → Push auf die falsche Firma. Der Service nimmt bei `len==1` `partners[0]` ohne jede Nachprüfung (`odoo_vendor_bill_push_service.py:715`). Trifft den **Normalfall** (jeder erstmals gescannte Lieferant ohne USt-Id/IBAN/Ref fällt auf die Namenssuche durch).

**Fix (dreifach, defense-in-depth):**
1. `odoo_connector._escape_like()` escaped `\`, `%`, `_` vor dem `ilike`.
2. Namen < 3 Zeichen lösen keine Namenssuche mehr aus (`_MIN_NAME_SEARCH_LEN`).
3. Service: bei `match_source == "name"` normalisierte Namensgleichheit (`_names_match` — lowercase, Interpunktion→Space, Whitespace kollabiert) verlangt; sonst → Review. „Meier GmbH" ≠ „Meier GmbH & Co. KG". USt-Id/IBAN/Ref/Mapping (eindeutige IDs) unberührt. Konsistent mit Plan-R6 („nur eindeutige Treffer pushen"); Erstlieferant → Review → Bestätigung → `ERPEntityMapping` (Stufe 1) beim nächsten Mal.

**Verifikation:** 3 neue Tests (Escaping-Domain, Kurzname-Skip, Service-Namens-Mismatch→Review + Gegenprobe). TDD-Rot bewiesen.

---

### F-07 — Doppel-Push bei Retry/verlorener RPC-Antwort · **P1** · ✅ GEFIXT

**Hypothese (atk-push H3):** Ein Celery-Retry erzeugt einen zweiten Odoo-Entwurf.

**Beweis:** `odoo_vendor_bill_push_service.py:770` `create` → erst `:793–794` `_apply_push_metadata` + `db.commit()`. Fehlerfenster: (1) Odoo-create OK, dann `db.commit()` scheitert/Worker-Crash → `odoo_move_id` nicht persistiert → Retry (`max_retries=8`) → Idempotenz-Gate (`:536–548`) greift nicht → zweiter Entwurf. (2) Odoo committet serverseitig, RPC-Antwort geht verloren → `create_vendor_bill_draft` liefert `None` → als retryable gewertet → zweiter Entwurf. Kein Pre-Create-Existenzcheck; `ref` existiert, wird aber nicht zur Dedup genutzt.

**Fix:** `create_vendor_bill_draft` sucht **vor** dem `create` einen existierenden `account.move` mit `move_type=in_invoice ∧ partner_id ∧ ref` und adoptiert ihn (`return str(existing_id)`) statt ein Duplikat zu erzeugen. `ref` ist stabil (`invoice_number` bzw. `ABLAGE-<doc8>`) → idempotent über Retries. **Tradeoff dokumentiert:** Bei Adoption wird das PDF nicht erneut angehängt (hängt am ersten Entwurf) — Doppel-Bill ist das größere Übel als ein fehlender Zweit-Anhang.

**Verifikation:** neuer Test `test_existing_draft_is_deduped_not_recreated` (Search findet Entwurf → kein create/attach) + 4 bestehende create-Tests an den führenden Dedup-Search angepasst. TDD-Rot bewiesen.

---

### F-08 — Fremdwährung bucht als EUR · **P1** · ✅ GEFIXT

**Hypothese (atk-push H2c):** Eine Nicht-EUR-Rechnung wird mit falschem Betrag gebucht.

**Beweis:** `create_vendor_bill_draft` (`odoo_connector.py:951–966`) sendet **kein** `currency_id`; `_build_currency` (`:290`) berechnet die Währung, sie landet aber nur im Draft-Objekt, nie im `move_data`. Folge: Eine USD-Rechnung bucht die USD-Zahl in Odoos Default-Währung (EUR für Spargelmesser) → falscher Betrag.

**Fix:** Service leitet nicht-EUR-Rechnungen (`_build_currency(invoice) != "EUR"`) in die Review-Queue (`status=error`, `retryable=False`) statt sie falsch zu buchen. EUR bleibt korrekt (Odoo-Default = EUR für die deutsche Company). Minimal, konservativ, ohne `res.currency`-Mapping-Infrastruktur.

**Verifikation:** neuer Test `test_fremdwaehrung_geht_in_review_kein_push` (USD → error+Review, kein create). TDD-Rot bewiesen.

---

**Gesamtverifikation Push-Fixes:** `docker compose exec backend pytest tests/unit/services/erp/ -q` → **248 passed**. TDD-Gegenprobe (git-stash der 2 Service-Dateien): alle 5 neuen Kern-Tests fallen ohne den jeweiligen Fix (`assert None == '55'`, `pushed != ambiguous`, `pushed != error`, …).

**atk-push weitere (P2, dokumentiert, nicht merge-blockierend):** H2a Gutschrift-als-`in_invoice` (Klassifikations-abhängig), H2b fehlende `tax_ids` auf der Brutto-Sammelzeile → mögliche USt-Aufblähung (auf Staging verifizieren), H5 „Archiv zuerst" gilt nur für Original-Bytes (formale GoBD-Einbuchung entkoppelt), H6-verwandt: Push-Connector setzt `odoo_company_id` nicht (Multi-Company-Odoo → Cross-Company-Fehlgriff; für Single-Company-Spargelmesser heute unkritisch). H4 (Kreislaufschutz) fail-closed, H6 (Cross-Tenant) widerlegt.

---

### F-09/F-10/F-11 — Freeze-Restlecks (atk-freeze) · **P2** · 🔎 zu verifizieren

- **F-09:** `tasks/__init__.py` importiert alle 22 gefrorenen Task-Module eager → sie sind auf den Workern **registriert** (`celery inspect registered` zeigt `banking_tasks.*`), der include-Filter läuft ins Leere. Einzige Barriere ist die Beat-Prunung. Kein aktiver `.delay()`-Caller heute (atk-freeze H4 negativ) → P2, aber „P1 sobald ein aktiver Caller existiert". Die Code-Annahme „Worker lädt entfernte Module nicht" (`celery_app.py:3299`) ist **falsch**.
- **F-10:** Beat `extended-alerts-cashflow-daily` überlebte die Prunung, fährt täglich 06:00 den gefrorenen `CashflowPredictionService` (`extended_alerts_service.py:250`) → irreführende Liquiditäts-Alerts auf veralteten Daten, keine Mutation.
- **F-11:** Aktiver, plain registrierter `predictive-actions`-Router (`main.py:1537`) schreibt in die gefrorene InvoiceTracking-Domäne: `POST /predictive-actions/{id}/accept` → `_execute_dunning_action` (`predictive_action_service.py:907`) setzt `invoice.dunning_level++`. Begrenzt (nur DB-Zähler, kein Versand), aber mutierend in gefrorenem Terrain.

**Freeze-Kern selbst solide (atk-freeze widerlegt H2/H3/H5):** keine gefrorenen Sub-Router unter aktiven Parents, Beat-Prunung robust (außer F-10), Live-GET auf gefrorene Pfade durchgängig 404.

**F-10 gefixt:** `extended-alerts-cashflow-daily` in `FROZEN_MODULE_EXTRA_BEAT_KEYS[MODULE_FINANCE]` ergänzt (`celery_app.py`). Live: nach Reload nicht mehr im effektiven `beat_schedule`. Regressionstest `test_frozen_finance_cashflow_beats_are_pruned` (22 grün).

**F-09/F-11 dokumentiert, nicht gefixt (bewusst):**
- **F-09** live bestätigt: `celery inspect registered` auf worker-cpu zeigt **107 gefrorene Tasks** (banking/fraud/datev/…) trotz include-Filter — Ursache ist der Eager-Import in `tasks/__init__.py`. **Kein Fix**, weil (a) der Freeze sein Sicherheitsziel erreicht (Endpoints 404, Beats gepruned — beides verifiziert), (b) kein aktiver `.delay()`-Caller existiert (atk-freeze H4 negativ), (c) ein Fix (Eager-Imports gaten) riskiert Import-Bruch an anderer Stelle in gefrorenem Terrain. **Empfehlung:** Kommentar `celery_app.py:3299` („Worker lädt entfernte Module nicht") korrigieren — er ist faktisch falsch; die echte Barriere ist die Beat-Prunung.
- **F-11** live bestätigt: `predictive_action_service.py:930` setzt `invoice.dunning_level`. **Kein Fix**, weil Plan §10.8 `predictive-actions` **bewusst aktiv** lässt (Bens Scope-Entscheidung) und der Blast-Radius ein DB-Zähler auf eingefrorenen Daten ohne Außenwirkung ist. **Für Ben markiert:** der Dunning-*Schreib*-Pfad war bei der Aktiv-Entscheidung vermutlich nicht bedacht — falls unerwünscht, `_execute_dunning_action` hinter `is_module_active(MODULE_INVOICE_TRACKING)` gaten.

---

### Angriffsfläche E (Ops) — F-12: tote `monitoring`-Queue · **P1** · ✅ GEFIXT

**Hypothese (DoD §8.9):** Eine geroutete Queue hat keinen Konsumenten → Tasks verschwinden lautlos.

**Beweis (live):** 3 Tasks in `predictive_tasks.py` (`collect_metrics_for_prediction` Z. 34, `run_predictions` Z. 139, `generate_predictive_alerts` Z. 222) tragen `queue="monitoring"` im Dekorator. Drei **aktive** Beats feuern sie (`predictive-collect-metrics` alle 60 s, die beiden anderen alle 300 s). **Kein** Worker konsumiert `monitoring` (weder GPU- noch CPU-`-Q`; `celery inspect active_queues` = 0 Treffer). Ergebnis:
```
$ redis-cli LLEN monitoring   → 207   (wächst jede Minute; consumed queues = 0)
```
Die System-Health-Prediction lief **nie** und Redis füllte sich unbegrenzt — exakt die Fehlerklasse von Commit `2497ae5e0`. Die anderen Dekorator-Queues (`ai`, `webhooks`, `ml`, `exports`, `banking`, `gpu`) sind LLEN=0 **ohne** aktiven Producer (tote Deklarationen, harmlos); `monitoring` war das einzige Leck mit aktiven Beats.

**Fix:** `monitoring` zur `worker-cpu`-`-Q`-Liste ergänzt (`docker-compose.yml`), konsistent mit dem Queue↔Worker-Muster (M-10). **Verifikation live:** nach `docker compose up -d --no-deps worker-cpu` konsumiert worker-cpu `monitoring`, Backlog **207 → 0**, `collect_metrics_for_prediction` läuft mit echten Ergebnissen (`success: True, cpu_usage_percent: 14.8`), alle Container weiter healthy.

---

### Angriffsfläche D (Security) — S-01…S-04: die schweren P0-Kandidaten widerlegt

Alle vier Kronjuwel-Hypothesen wurden gegen den Live-Stack geprüft und **entkräftet** — das ist die Evidenz, dass geprüft wurde, nicht bloß gelesen:

**S-01 — RLS-Rollen-Setup korrekt, aber `documents`-Policies permissiv (KORRIGIERT).** Ursprünglich als „voll wirksam" eingestuft — das war für `documents` **falsch** (atk-sec H1 hat es aufgedeckt, hier selbst nachverifiziert). Korrekt bleibt das Rollen-Setup:
```
current_user = ablage_app · rolsuper=False · rolbypassrls=False · ablage_app besitzt 0 RLS-Tabellen (alle → ablage_admin)
RLS-enabled: 92 / 490 Tabellen  (RLS-light-Kern-Scope), davon FORCED nur 5
companies:  ohne Kontext 0 Zeilen → mit User-Kontext 1  (Policy filtert korrekt ✔)
```
Das Backend verbindet als Nicht-Superuser ohne BYPASSRLS und besitzt keine RLS-Tabelle → kein Owner-/Superuser-Bypass. Für `companies` filtert RLS **korrekt**. **Aber siehe F-15** — für `documents` nicht.

**F-15 — `documents`-RLS durch permissive OR-Policies neutralisiert · P1 · ⛔ GATE:**
```
$ SELECT policyname, permissive, cmd FROM pg_policies WHERE tablename='documents';   → 8 Policies, ALLE PERMISSIVE
  documents_owner_select (SELECT):  owner_id=current_user_id OR current_user_id IS NULL OR current_user_id='' OR is_admin
  documents_tenant_isolation (ALL): is_rls_bypass_enabled() OR company_id IS NULL OR company_id=get_current_company_id()
  tenant_isolation_documents (ALL): company_id = current_company_id           ← die STRIKTE, per OR neutralisiert
$ (ablage_app, RESET ALL) SELECT count(*) FROM documents;   → 3   (DoD-8 verlangt 0!)
$ SELECT count(*) FROM documents WHERE company_id IS NULL;   → 0   (Cross-Tenant-Escape latent, keine Daten)
```
PostgreSQL verknüpft PERMISSIVE-Policies mit **OR** → eine Zeile ist sichtbar, sobald *irgendeine* Policy zustimmt. Die Escapes `current_user_id IS NULL` (Query ohne User-Kontext, z. B. Worker) und `company_id IS NULL` (NULL-Company-Dokumente) hebeln die strikte `tenant_isolation_documents` aus. **Folge:** Eine Query ohne gesetzten User-Kontext sieht **alle** Dokumente; das verletzt die **DoD-8 des Branches** („App-Rolle ohne Company-Kontext liest 0 Zeilen auf RLS-Kerntabellen").

**Severity P1, aber kein aktiver Datenabfluss:** Der **primäre** Schutz ist die App-Ebene (`verify_document_ownership` `dependencies.py:1016`, `validate_company_access` :358 — beide vorhanden, verifiziert); RLS ist die zweite Verteidigungslinie („light"). Der `company_id IS NULL`-Escape hat aktuell 0 Daten. Es ist der gerissene Gürtel bei intakten Hosenträgern — merge-relevant, weil der Branch DoD-8 als erfüllt ausweist, es für `documents` aber nicht ist.

**Fix erfordert eine neue Alembic-Migration (272)** — Ben hat das Escape-Entfernen genehmigt. **Bei der Umsetzung stellte sich der Fix als unsicher standalone heraus (siehe F-16):** Die Escapes sind **load-bearing** für die Background-Worker.

---

### F-16 — Background-Worker setzen keinen RLS-Kontext → Dokument-Anlage RLS-abgelehnt · P1 · ⛔ RE-GATE

**Bei der Vorbereitung des F-15-Fixes entdeckt** (der Grund, warum F-15 nicht einfach „chirurgisch" gefixt werden kann):

**Beweise (live gegen ablage_app, alles rolled back):**
```
grep set_rls_company_context / rls_bypass in  odoo_mirror_service, odoo_tasks, imports/*, document_creation  → LEER (kein Worker setzt Kontext)
(ablage_app, RESET ALL) no-context SELECT documents  → 4   (= alle; nur via owner_select-Escape `current_user_id IS NULL`)
Kontext-Setzung existiert NUR in der HTTP-Middleware (company_context.py:67/133) — nicht in Workern.
```
> **Korrektur (Umsetzungsphase, durch echtes Testen):** F-16 ist **lese-seitig**, nicht schreib-seitig. Die ursprüngliche „no-context-INSERT wird von RLS abgelehnt"-Aussage war eine Fehldiagnose — `documents_insert` hat `WITH CHECK true`, INSERTs gelingen ohnehin. Der echte Defekt: Worker LESEN `documents` nur über den `current_user_id IS NULL`-Escape → nach F-15 (Escape weg) liefert ein kontextloser Worker-Read **0 Zeilen** → Dedup/Verarbeitung bricht. Details + Fix-Fortschritt in `docs/reviews/2026-07_F15-F16_rls-worker-context_spec.md`. **Nebenbefund:** `documents_insert WITH CHECK true` = INSERT-seitige Mandantentrennung offen (separate Härtung).

**Zwei gekoppelte Konsequenzen:**
1. **F-16 selbst (Regression aus der RLS-light-Aktivierung 2026-07-09):** Der OdooMirrorService legt Dokumente mit non-null `company_id` **ohne** RLS-Kontext an → gegen die echte DB werden diese INSERTs **abgelehnt**. Der Mirror würde bei Go-Live fehlschlagen. Unentdeckt, weil die 26 Mirror-Tests die DB mocken und noch keine aktive Odoo-Verbindung existiert. Gleiches Risiko für die worker-initiierten Folder-/E-Mail-Importe (kein Kontext im kanonischen `create_import_document`). Der HTTP-Upload-Pfad funktioniert (Middleware setzt Kontext — genau der in `4fd5238c4` reparierte Pfad); die **Worker-Pfade wurden bei der RLS-Aktivierung nicht mitgezogen**.
2. **F-15-Fix unsicher:** Weil die Worker keinen Kontext setzen, **lesen** sie Dokumente ausschließlich über die `current_user_id IS NULL`-Escape. Entfernt man sie (F-15), sehen alle kontextlosen Worker-Reads 0 Zeilen → OCR/Mirror/Import-Pipeline bricht. Die Escape ist damit **load-bearing**, nicht bloß ein Loch.

**Der korrekte Fix ist gekoppelt und größer als eine Migration:** Erst müssen die dokument-berührenden Worker RLS-Kontext setzen (`set_rls_company_context_sync(session, company_id)` für Mirror/Import mit bekannter Company, bzw. `rls_bypass_context_sync` für systemische Tasks), **dann** können die Escapes entfernt werden. Das ist ein querschnittlicher Eingriff (Mirror, Importe, ggf. OCR-Tasks) mit hoher Blast-Radius, den die Mock-Tests nicht abdecken → braucht Verifikation gegen echte RLS.

**Entscheidung (Ben, RE-GATE):** **Dediziertes RLS-Task vor Go-Live.** F-15 + F-16 werden hier NICHT gefixt (kein gehetzter Pre-Merge-Eingriff); sie sind gekoppelte **Go-Live-Blocker** auf der Restliste. Die 7 in Iteration 1 gefixten P1 sind davon unabhängig und bleiben merge-fähig. **Wichtig für die Reihenfolge:** F-16 muss gelöst sein, **bevor** OdooMirrorService und die worker-initiierten Importe scharf geschaltet werden (~Mitte Aug) — sonst schlagen deren Dokument-INSERTs gegen die aktive RLS fehl. Der HTTP-Upload-Pfad ist nicht betroffen.

**S-02 — pgbouncer-Cross-Tenant-Leak ausgeschlossen** (zwei unabhängige Gründe):
1. Das Backend verbindet **direkt** zu `postgres:5432`, **nicht** über pgbouncer (dessen `POOL_MODE=transaction` ist für den RLS-Pfad irrelevant).
2. Der RLS-Kontext nutzt `set_config('app.current_company_id', :cid, true)` — der dritte Parameter `true` = **transaktions-lokal** → wird am Transaktionsende zurückgesetzt und kann selbst über einen Transaction-Pooler nicht auf die nächste Verbindung/den nächsten Tenant leaken.

**S-03 — CORS-Reflection + CSRF-Schwächung ausgeschlossen:**
- CORS ist fail-closed: `CORS_ORIGINS=[]`, ein fremder Origin (`https://evil.example`) erhält **keinen** `access-control-allow-origin`-Header (nicht reflektiert); das isolierte `allow-credentials: true` ist ohne passenden Origin browserseitig wirkungslos.
- Der CSRF-Fix `4fd5238c4` hat **nur** die Token-*Rotation* auf echte 2xx eingegrenzt (307-Redirect-Bug), **keine** Multipart-/Pfad-Exemption eingebaut, die die Validierung schwächt. Der Verdacht einer zu breiten CSRF-Ausnahme ist widerlegt.

**S-04 — M-06-Rest (P2, Defense-in-Depth):** Die 3 einvoice-POSTs (`generate_zugferd` L217, `generate_xrechnung` L292, `validate_einvoice` L370) haben im **Code** weiterhin nur `db=Depends(...)`, kein `current_user`. Aktuell durch den Freeze geschützt (Router nicht registriert → live 404 verifiziert), aber bei Reaktivierung via `ACTIVE_OPTIONAL_MODULES=einvoice` wieder unauthentifiziert erreichbar. **Kein Fix** (Regel „gefrorene Module nicht anfassen"); **Empfehlung** an Ben: `current_user`-Dependency nachrüsten, falls einvoice je reaktiviert wird.

Weitere Security-Beobachtungen (P2, aus explore-secops-Landkarte): kein `:80→:443`-Redirect (http bleibt bedienbar); RLS-Schutz hängt am korrekt gesetzten `.env` auf dem Deploy-Host (verifiziert aktiv, aber ein Fresh-Clone ohne `.env` fiele auf Superuser zurück — Deploy-Hygiene-Note).

---

### Iteration 2 — atk-sec/atk-ops-Vollreports + Selbst-Regressionsprüfung

**S-05 — Dev-Stack in `DEBUG=True` (P2, Deploy-Posture):** atk-sec verifizierte `is_production=False` im laufenden Container. `DEBUG` schaltet mehrere Security-Toggles ab: `cookie_secure=not DEBUG` (`main.py:1131`) + `enable_hsts=not DEBUG` (`main.py:1098`) → über :443 werden Session-/CSRF-Cookies **ohne `Secure`** gesetzt und die App emittiert **kein HSTS** (nur nginx tut es); zusätzlich IP-Blocking aus (`main.py:1058`), Rate-Limit-Bypass (`main.py:1152`). **Im Pilot-Produktivbetrieb** (`ENVIRONMENT=production` → `is_production=True`, `DEBUG=False`) greifen Secure/HSTS/IP-Blocking/Rate-Limit alle. **Kein Code-Merge-Blocker**, aber: (a) Pilot zwingend mit `ENVIRONMENT=production` fahren; (b) Hardening-Empfehlung — Security-Flags an `is_production` statt `DEBUG` binden (Inkonsistenz: CSRF-Cookie `not DEBUG` vs. Auth-Cookie `is_production`). **CORS-Reflection und CSRF-Regress von atk-sec erneut widerlegt** (deckt sich mit S-03).

**F-09/S-04 — atk-sec-Eskalationssicht (dokumentiert):** atk-sec stuft die registriert-bleibenden gefrorenen Celery-Tasks (F-09, 178 Tasks via `inspect registered`) und die 3 unauth einvoice-POSTs (S-04) als **P1** ein, nennt aber selbst die starken Milderungen: Redis passwortgeschützt + nur intern (kein `send_task` von außen), und die einvoice-POSTs sind live 404 (Freeze). Ich belasse beide als **P2** (kein aktiver Exploit-Pfad; Fix von F-09 riskiert Import-Bruch in gefrorenem Terrain, Fix von S-04 hieße gefrorenen Code editieren) — mit der klaren **Empfehlung**, S-04 (`current_user` an `einvoice.py:234/310/388`) **vor** jeder einvoice-Reaktivierung nachzurüsten und F-09 durch bedingten Import statt include-Pop sauber zu schließen.

**S-06 — `datev`-Queue ohne Konsument (P2):** atk-ops bestätigt: von 18 gerouteten Queues hat nur `datev` keinen Konsumenten. Inert (datev_connect-Tasks gefroren, Dispatcher hinter dem 404-Router), Redis LLEN=0. DoD-9 formal verletzt, aber ohne Live-Auslöser. Zündet erst bei `ACTIVE_OPTIONAL_MODULES=datev` **ohne** `datev`-Konsument. **Empfehlung:** Kommentar `docker-compose.yml:895-897` korrigieren + CI-Guard „aktives Modul routet in unkonsumierte Queue".

**Ops-Kern von atk-ops bestätigt gesund:** Beat→tote-Queue **widerlegt** (0/217), entrypoint-Lock gesund (Owner ablage_admin vs App ablage_app live via `pg_stat_activity` bewiesen; `depends_on: service_healthy` lässt Nicht-Migratoren doch warten — mildert F-14), Beat-HA via RedBeat-Redis-Lock **widerlegt** (kein Doppellauf), Worker-Down-Alert-Kette Metrik→Regel→Route→Slack vollständig (nur End-to-End-Feuern steht als Pre-Go-Live-Test aus). restic-Kern gesund (Pipe-Masking abwesend), P2-Härtungen: MinIO-Fehler bricht ganzen Lauf (`:211`), Secrets via Kommandozeile (`:121/:172`), `check` nicht im Daily.

**GoBD-Audit-Chain-Unveränderbarkeit — SOLID (live bewiesen):** Frischer Winkel, positiv bestätigt. Es gibt **9 DB-Immutability-Trigger** (BEFORE UPDATE/DELETE) auf `gobd_audit_chain` (`trg_audit_chain_immutable`), `audit_logs` (`tr_audit_logs_no_update`/`_no_delete`), `domain_events`, `dlp_audit_logs`, `classification_audit_log`. Live-Probe:
```
$ (rolled back) DELETE FROM audit_logs;   → BLOCKIERT (527 Zeilen, asyncpg-Error vom Trigger)
```
Selbst ein DB-Level-`DELETE`/`UPDATE` auf der Audit-Chain wird abgewiesen — die GoBD-Kernanforderung (Unveränderbarkeit) ist auf Datenbankebene durchgesetzt, nicht nur applikativ.

**Selbst-Regressionsprüfung meiner 7 Fixes (kritisch, eigene Bewertung):**
- **F-07 Dedup-ohne-PDF (R3):** Adoptiert ein Dedup-Treffer den Move ohne Re-Attach → nur im seltenen Doppel-Fehlerfenster (create OK + PDF-Attach schlägt fehl + lokaler Commit schlägt fehl → Retry adoptiert PDF-losen Move). Das kleinere Übel gegenüber einem Duplikat-Bill. **Dokumentierter Tradeoff, keine Regression.** ref-Kollision (gleiche invoice_number + gleicher Partner) unterdrückt den zweiten Push — semantisch „selbe Rechnung", der `ABLAGE-<doc8>`-Fallback ist pro Dokument eindeutig.
- **F-06 `_names_match` (R4):** `re.sub(r"[^\w]+"," ", …, UNICODE)` behandelt Umlaute korrekt; Homoglyphen/Zero-Width führen zu **Review** (fail-closed, sichere Richtung), nie zu falschem Push.
- **F-03 Hash-Gate (R2):** Fail-open nur bei fehlendem Odoo-`checksum` — der aber für inhaltsbehaftete `ir.attachment` von Odoo immer gesetzt wird (leerer Inhalt ist vor dem Gate per `if not content: continue` gefiltert). Akzeptabler by-design-Fall (was Odoo nicht liefert, kann nicht verifiziert werden; Odoo=vertrauenswürdige read-only-Quelle).
- **F-12 Kapazität (R5):** 3 monitoring-Tasks sind schnell (collect_metrics 0,1 s), worker-cpu `--concurrency=4` hat Reserve — vernachlässigbare Last.

**atk-regress-Vollreport (Selbstprüfung meiner 7 Fixes): keine P0/P1-Regression, 119/119 Tests grün.** Bestätigt R1 (F-01-Split sauber, kein zweiter Misch-Router), R2 (F-03-Gate keine Vuln — checksum im selben atomaren Read, kein TOCTOU), R4 (F-06 fail-closed, keine Unicode-Umgehung), R5 (F-12-Kapazität vernachlässigbar). Drei P2-Restpunkte, **keiner verliert ein archiviertes Dokument** (Ablage-Archiv bleibt führend):
- **F-19 (R3, P2):** F-07-Dedup adoptiert bei (partner_id, ref)-Treffer blind. (a) Schlägt in Versuch 1 der PDF-Attach + der lokale Commit fehl, adoptiert der Retry den PDF-losen Move und hängt das PDF nie nach (Odoo-Beleg ohne Bild; Archiv hat es). (b) Zwei *verschiedene* Rechnungen desselben Partners mit gleicher `invoice_number` → die zweite wird still als Move der ersten adoptiert → ihr offener Posten erreicht Odoo nie als eigener Entwurf. **Netto trotzdem Verbesserung** (Einzel-Beleg statt Doppel-Bill mit Doppelzahlungsrisiko). Empfehlung: `message_main_attachment_id` prüfen + nachhängen; Dedup-Key um `invoice_date`/`amount` erweitern oder same-(partner,ref)/anderer-Inhalt in Review.
- **F-20 (R5, P2):** F-12 schaltet `generate_all_alerts` scharf, das pro Lauf einen frisch-UUID-Alert **ohne per-Typ-Dedup** in ein In-Memory-`_active_alerts`-Dict legt (`predictive_alerts_service:296`). Ein persistenter Zustand akkumuliert alle 5 Min einen Duplikat-Alert pro Prefork-Prozess. **Kein User-Spam** (der Task dispatcht kein Slack/Mail, nur speichern+loggen), aber der Store wächst unbounded + ist über die 4 Prozesse inkonsistent. Latenter Vor-Bug, den F-12 nur einschaltet — F-12 selbst ist korrekt. Empfehlung: Dedup nach `alert_type` vor `append`.
- **R2-Nit:** F-03-Fail-open-Zweig (content vorhanden, checksum fehlt) ist stumm — Empfehlung `logger.warning`.
- **R-06 (P2, GEFIXT):** Der F-02-Freeze-Contract-Test nutzte eine hardcodierte 10-Präfix-Liste und hätte ein Leck in einem neu hinzugefügten gefrorenen Modul **nicht** gefangen. **Behoben** (Commit `35fd3b3cd`): Coverage-Assertion `test_frozen_module_coverage_is_complete` prüft alle 13 `KNOWN_OPTIONAL_MODULES` gegen die Testdeckung; die 3 nicht-präfix-verifizierten Module (finance/risk_finanzki/ai_speculative) sind mit Begründung dokumentiert. 4/4 grün.

**atk-fresh-Vollreport (frische Angriffswinkel): SAUBER — keine P0/P1.** Alle 6 Hypothesen live geprüft:
- **OCR-Hook→Push (H1):** Kette sauber — Push ist letzter Schritt nach `status=COMPLETED`, korrekt gated (Flag+Quelle+Verbindung), Extraction-Race via `is_extraction_ready`+Retry, kein Push ohne persistiertes Original. **Observation (P2):** „Archiv zuerst" = MinIO+DB-Persistenz, nicht die *formale* GoBD-Einbuchung — ein Beleg kann gepusht sein, bevor `is_archived` gesetzt ist (gewollt, Archiv=führende Rohquelle; für GoBD-Prüfer notiert).
- **Mirror-Partner-Resolution + GoBD-Immutability (H2):** `_resolve_partner_entity`→None bricht die Archivierung nicht (business_entity_id nullable). GoBD-Audit-Chain **DB-immutable, live bestätigt** (Trigger `trg_audit_chain_immutable` blockt DELETE immer, UPDATE nur auf Verifikations-Felder — Mig 234 hat den Mig-229-Blanket-Konflikt korrekt entfernt). **Observation:** `gobd_audit_chain`/`domain_events` aktuell leer → Kette mit Echtdaten ungetestet, **Go-Live-Smoke-Test empfohlen**.
- **Frozen-Route-Bypass (H3):** ERP-Doppel-Freeze **wasserdicht** (alle 25 ERP-Präfixe live 404, inkl. M-06-einvoice; FE/BE-Modul-Keys identisch). **F-17/F-18 (P2):** ai_speculative-Freeze unvollständig — ml_dashboard/adhoc_reports/predictive_actions FE-frozen aber BE plain registriert; `GET /reports/adhoc/data-sources` unauth 200 (leakt Tabellennamen). Selbst verifiziert; **koordinierter FE+BE-Fix nötig** (aktive FE-Route/Sidebar/Hooks existieren → kein BE-Only-Alleingang; predictive_actions ist Bens bewusste Aktiv-Entscheidung F-11).
- **Auth-Härte (H4):** live bestätigt — abgelaufenes Token 401, Login-Rate-Limit 429 ab #6, Refresh-Rotation-Replay blockiert (alter Token geblacklistet), change-password prüft altes PW (F-27).
- **Privat-Verschlüsselung (H5):** kein Klartext am Ruhepunkt (AES-256-GCM ersetzt file_content), Klartext/Key nie geloggt/persistiert, Salt+Nonce pro Eintrag. **P2-Hardening:** PBKDF2 100k Iterationen < OWASP-2023 (600k) → erhöhen.
- **Mig-Konsistenz (H6):** `alembic_version=271`, Single-Head, keine Phantom-Spalten (alle Mirror/Push-Spalten live vorhanden, ORM↔DB deckungsgleich).

---

---

## Iteration 3 — Konvergenz-Check (Frontend-Freeze + Pipeline/Privat)

**atk-fe (Frontend-Freeze-Vollständigkeit): Konvergenz-Signal — kein P0/P1, Guard/Build/Sidebar sauber.**
- **F-17 vervollständigt (P2):** Die FE-Freeze-Liste (`frozen-modules.ts`) ist **breiter** als der BE-gated Router-Satz — **5 Module** sind FE-frozen, aber ihr konsumierter BE-Router ist plain registriert (aktiv, auth-gated 403): `ml_dashboard` (:1649), `adhoc_reports` (:1664), **`ki_pipeline`** (:1660, neu), `predictive_health` (:1610), **`expenses`/spesen** (:1505 — echter Intent-Konflikt, in `module_registry.py:134` bewusst aktiv). Präzisierung: der `/predictive`-FE-Treffer konsumiert `predictive_health`, **nicht** `predictive_actions` (letzterer ist Bens Aktiv-Entscheidung F-11 und von keiner FE-Route erreicht). **Kein Datenleck** — alle auth+company-scoped, außer F-18.
- **Guard wirksam (Sidebar-Sorge widerlegt):** `beforeLoad→frozenModuleGuard` wirft `redirect('/frozen')` **vor** dem Mount → keine API-Calls vor Redirect; `SidebarLink` filtert alle ~35 frozen Links zentral (`Sidebar.tsx:515`) → keine Dead-End-Links. Defense-in-depth (Link-Filter + Route-Redirect + BE-404) intakt; nur der BE-Layer fehlt bei den 5 F-17-Modulen.
- **tsc -b = 0**, keine toten Imports. Selbst nachverifiziert.
- **Test-Gap (P2):** `frozen-modules.spec.ts` (e2e) asserted 404 nur für 4 **korrekt-gatete** Endpoints — probt **nicht** die F-17-Endpoints (ml-dashboard/ki-pipeline/reports-adhoc/health-predictions) → bleibt grün trotz Inkonsistenz. Zusätzlich zielt eine Assertion auf die nicht-existente Route `/banking`. Empfehlung: e2e-Assertions um die F-17-Endpoints erweitern.

**Empfehlung F-17 (koordinierter FE+BE-Fix, Ben-Scope):** Entweder die 4 spekulativen Router (ml_dashboard, ki_pipeline, adhoc_reports, predictive_health) unter passende MODULE-Keys gaten **und** `adhoc data-sources` auth-pflichtig machen — ODER die FE-Freeze-Liste um diese + `spesen` zurücknehmen (Intent-Entscheidung). Nicht merge-blockierend.

**atk-pipeline (Pipeline-Integrität + Privat-ACL): 1 P1 (F-21, gefixt) + 2 P2, kein Live-Leak.**
- **F-21 (P1, ✅ GEFIXT):** Die Privat-ACL-Gates `space_service.get_with_access_check:186` + `document_service.get_by_id_with_space_and_access_check:759` filtern `PrivatSpaceAccess.is_active == True` — eine **nicht existierende Spalte** (Beweis: `AttributeError - has no attribute 'is_active'`; Aktiv-/Revoke-Logik trägt `expires_at`). Der Nicht-Owner-Zweig warf dadurch **HTTP 500 statt 403** (DoD-8-Bruch) und **Shared-Space-Zugriff war komplett tot** (auch mit gültigem Grant → 500). Fail-closed (kein Datenleck). **Fix:** `is_active`-Bedingung in beiden Gates entfernt; `expires_at` trägt die Revoke-Logik. Regressionstest `test_space_access_gate_f21.py` (3 grün, Schema- + Quell-Guard). Die bestehenden Privat-Tests prüfen nur Endpoint-Existenz/unauth-403 — **nie die ACL-Grant-Ebene**, weshalb F-21 durchrutschte.
- **F-22 (P2 → P0-bei-Reaktivierung):** `nlq_service._process_chat_query` ruft `semantic_search(...)` **ohne `user_id`** → RAG filtert nicht → Chunks **aller** User/Companies (Cross-Tenant-Leak). **Aktuell 404** (Endpoint hängt an gefrorenem `MODULE_AI_SPECULATIVE`, live: `module_frozen_router_skipped .../nlq`). **Reaktivierungs-Sperre:** ai_speculative darf **nie** ohne diesen Fix reaktiviert werden — sonst sofort P0. (`conversational_assistant.py:784` macht es mit `user_id` richtig, ist aber ebenfalls frozen.)
- **F-23 (P2):** Cross-Channel-Dedupe-Asymmetrie — email/folder-Import dedupliziert **owner-scoped** (`create_import_document`), Mirror **company-scoped** (`_persist_attachment`). SHA256 ist überall identisch (kein Hash-Bug), aber ein Mirror-Doc (owner=System) + späterer email/folder-Import desselben Belegs → owner-scoped Dedupe findet die Mirror-Zeile nicht → Duplikat-Document. Kein Leak, GoBD-Hygiene. Empfehlung: einheitlicher Dedupe-Scope oder company+checksum-Check auch im Import-Pfad.
- **Widerlegt:** H2 Privat-ACL-**Leak** (fail-closed; PrivatDocument ist eigene Tabelle, RAG/Suche fassen sie nie an — grep 0 Treffer). H3 Such-Cross-Tenant für die **aktive** Oberfläche (alle aktiven Such-Router geben `user_id` weiter, Doc-Suche owner-scoped via `accessible_docs`-CTE, selbst nachverifiziert). H4 **Doppel-Archivierung** (dreifach abgesichert: Beat selektiert `~EXISTS(document_archives)` + Mirror-Ausschluss; `archive_document` wirft bei Bestand; `DocumentArchive.document_id` ist `unique=True` → selbst bei TOCTOU nur eine Zeile). H5 **Beat-Sanity** nach F-10/F-12: 0/276 Beat-Einträge in toter Queue (selbst gegengeprüft: 0/216 explizit-gequeuete).

**Pre-existierende Beobachtung (nicht Neuausrichtung, nicht mein Fix):** Der Integration-Test `test_list_spaces_endpoint_exists` schlägt fehl (`GET /api/v1/privat/spaces` → 404, obwohl `list_spaces` in `privat.py` codiert + `privat_router` registriert ist; die Route fehlt in der Live-OpenAPI). `git diff master..HEAD` für `privat.py`/privat-Services/diesen Test ist **leer** → der Fehler existiert auf master genauso, ist **unabhängig** von der Neuausrichtung und von F-21 (ein 404 ist Routing, upstream vom Service-Query). Verdient Bens separate Aufmerksamkeit (ein Kern-Privat-Listen-Endpoint fehlt in der OpenAPI), aber kein Merge-Blocker dieses Branches.

---

## Iteration 4 — Completeness-Check (Cross-Checks + finaler Sweep)

Eigene Cross-Checks der bisher am wenigsten geprüften, risikoreichen Pfade (positive Konvergenz-Evidenz):
- **ZUGFeRD/E-Rechnungs-Parsing XXE-sicher:** Der im E-Mail-Import aktiv gebliebene Parser (`einvoice/parser_service.py` → `zugferd_mapper.py`, bleibt trotz einvoice-Router-Freeze aktiv, Plan §4a) nutzt `SECURE_XML_PARSER = etree.XMLParser(resolve_entities=False, no_network=True)` (Z. 28) mit explizitem Anti-XXE-Kommentar und parst ausschließlich darüber (`fromstring(..., parser=SECURE_XML_PARSER)`, Z. 156). Das Repo nutzt `defusedxml` systematisch (SAML, CAMT053-Bank, SEPA, BPMN). **Kein XXE.**
- **Such-ACL scoped:** aktive Such-Router geben `user_id` durch; Doc-Suche owner-scoped via `accessible_docs`-CTE (`search_service.py`). **Kein Cross-User/Company-Leak** (selbst verifiziert).
- **Privat auth-gated:** `/api/v1/privat/life-events/types` → 403 unauth; 123 Auth/ACL-Dependencies in den Privat-Routern.
- **Beat-Konsument-Invariant** nach F-10/F-12: 0/216 Beat-Einträge in toter Queue (selbst gegengeprüft).

Completeness-Sweep der ungeprüften Pfade (selbst verifiziert) — **alle sauber oder von bestehenden Findings abgedeckt**:
- **Mirror-Attachment-Filename kein Pfad-Traversal:** `_safe_filename` (`odoo_mirror_service.py:806`) = `os.path.basename` (behandelt `/` und `\`) + Whitelist-`re.sub(r"[^\w.\- ()]","_")` + `.`/`..`-Reject + 255-Trunc; Storage-Key ist ohnehin content-adressiert (`{owner}/{sha256}`), nutzt den Namen nicht als Pfad.
- **Config-Secrets sauber:** keine committeten `.env` mit echten Secrets (nur `.env.example` + `.secrets.baseline`), keine hardcodierten Secret-Defaults in `config.py`, aktives `detect-secrets` + `tests/security/test_secrets_exposure.py`.
- **WA/WE-Import (`scripts/import_wa_we.py`) solide:** idempotent (SHA256-`checksum`-Dedupe → Zweitlauf 0 Importe), `--dry-run`-Default (kein Schreibzugriff ohne `--execute`), deterministischer Platzhalter-Filter (172643 Bytes), Dateinamen-Regex, `py_compile` OK. **Aber:** Der Import legt Dokumente als Skript **ohne RLS-Kontext** an → fällt unter **F-16** (gegen aktive RLS würden auch diese INSERTs abgelehnt; vor `--execute` bei Go-Live muss F-16 gelöst sein).
- **Migration-from-scratch:** Live-DB steht auf 271 (Single-Head), keine neue Migration im Branch (bereits in Iteration 2 bestätigt).

**Ergebnis Iteration 4: 0 neue P0/P1.** (atk-final-Vollreport corroboriert — Einarbeitung bei Eintreffen; die unabhängige F-21-Verifikation ist durch die 3 grünen Guard-Tests + die 23-grün-Suite bereits belegt.)

---

## Executive-Verdict

**Merge-ready: JA — für den reviewten Branch, mit klaren Go-Live-Bedingungen.**

Der Adversarial-Deep-Review lief **4 Iterationen** mit **11 parallelen Angriffs-/Verifikations-Agenten** + durchgängiger Live-Verifikation gegen den 21-Container-Stack (curl/pytest/SQL/celery-inspect — nie nur Codelesen). Er hat **10 echte Defekte gefunden und gefixt** (8 P1 + 1 P2 + 1 Test-Härtung), die die orchestrierte 2-Tage-Umsetzung übersehen hatte — genau die Klasse „grün getestet, aber tot", die den Review motivierte: F-12 (207 Nachrichten in einer toten Queue, System-Health-Prediction still tot), F-03 (GoBD-Spiegel ohne Hash-Verifikation), F-01 (gefrorener Cashflow-Forecast live erreichbar), F-06/07/08 (Vendor-Bill-Push: Falsch-Partner, Doppel-Push, Fremdwährung-als-EUR), F-21 (Privat-ACL-Crash → Shared-Spaces tot). Jeder Fix mit TDD-Rot-Beweis getestet, committet, wo möglich live nachgewiesen.

**Konvergenz erreicht:** Die P1-Fundrate fiel monoton — Iteration 1: 7 P1, Iteration 2: 2 P1 (gekoppelt, deferred), Iteration 3: 1 P1 (sofort gefixt), **Iteration 4: 0 neue P0/P1**. Der Frontend-Agent (Iter 3) und der Completeness-Sweep (Iter 4, inkl. eigener Cross-Checks: ZUGFeRD-XXE, MinIO-Traversal, Config-Secrets, WA/WE-Import) fanden keine neuen Merge-Blocker.

**Die schweren P0-Kandidaten wurden allesamt widerlegt** (RLS-Owner/Superuser-Bypass, pgbouncer-Cross-Tenant-Leak, CORS-Reflection, CSRF-Regress, Privat-ACL-Leak, Doppel-Archivierung, Such-Cross-Tenant) — durch echte Checks. Das Sicherheits-/Compliance-Fundament ist belastbar: GoBD-Audit-Chain **DB-immutable** (live: DELETE blockiert), Auth-Rotation/Rate-Limit/Expiry live bestätigt, Privat-Verschlüsselung leckfrei, ERP-Freeze wasserdicht (inkl. M-06), ZUGFeRD-Parser XXE-sicher, Alembic 271 Single-Head ohne Phantom-Spalten.

### Go-Live-Bedingungen (kein Merge-Blocker, aber vor Scharfschaltung zwingend)
1. **F-15 + F-16 (gekoppelt, P1, per Ben-Entscheidung als dediziertes RLS-Task deferred):** Die `documents`-RLS-Policies sind permissiv (DoD-8-Verletzung), und **kein Background-Worker setzt RLS-Kontext** → worker-initiierte Dokument-Anlage (OdooMirrorService, Folder-/E-Mail-Import, WA/WE-Import) wird von der aktiven RLS **abgelehnt**. Heute nicht live (Mirror ohne Verbindung), **muss aber vor Mirror/Import-Scharfschaltung (~Mitte Aug) gelöst sein**: Worker setzen Kontext → dann Escapes entfernen, gegen echte RLS getestet. HTTP-Upload nicht betroffen. Die gefixten P1 sind davon unabhängig merge-fähig.
2. **F-22 (Reaktivierungs-Sperre):** `MODULE_AI_SPECULATIVE` darf **nie** ohne Fix des NLQ-RAG-`user_id`-Filters (`nlq_service._process_chat_query`) reaktiviert werden — sonst sofort P0 (Cross-Tenant-Chunk-Leak). Aktuell 404 (gefroren).

### Restliste (P2, dokumentiert, nicht merge-blockierend)
Mirror: Overlap-Lock (F-04), Cursor-Full-Rescan-Härtung (F-05), Dedupe-Scope owner-vs-company (F-23). Freeze: Celery-Eager-Import (F-09), predictive-actions-Dunning-Write (F-11, Bens Scope), **FE/BE-Freeze-Drift bei 5 Modulen + adhoc-unauth-Metadaten (F-17/F-18)** — koordinierter FE+BE-Fix. Push: Dedup-Härtung (F-19), atk-push-P2s (Gutschrift/tax_ids/odoo_company_id). Ops: Queue-Length-Metrik tot (F-13), entrypoint-Race (F-14), datev-Queue (S-06), Alert-Dedup (F-20), restic-Härtungen. Security: M-06-Rest-Auth (S-04), DEBUG→is_production-Posture (S-05), PBKDF2 100k→600k. **Empfohlene Pre-Go-Live-Tests:** GoBD-Audit-Chain-Smoke (Kette aktuell leer), Slack-Alert-End-to-End, Login-Regression über https-Origin in `ENVIRONMENT=production`.

### Pre-existierend (nicht Neuausrichtung, für Ben separat)
`GET /api/v1/privat/spaces` (list_spaces) → 404 trotz codiert+registriert; fehlt in der Live-OpenAPI. `git diff master..HEAD` für privat = leer → existiert auf master genauso, unabhängig von diesem Branch.

### Nicht prüfbar (ehrliche Lücke)
Echter Odoo-Prod-Push und realer Mirror-Pull sind vor Go-Live/API-Key nicht testbar — Push-/Mirror-Logik ist gegen Mock-XML-RPC + Live-DB verifiziert, die **Odoo-Gegenseite** (tatsächliche `account.move`-Anlage, `currency_id`/`tax_ids`-Verhalten, Attachment) bleibt bis Go-Live unbewiesen (atk-push-Blindflecken). Der GoBD-Spiegel lief nie gegen eine echte Verbindung — genau der F-16-Pfad.

---

**Zusammenfassung Fixes (10 Commits, `e4f9b74d7`…`6b09cbb83`):** F-01/F-02/F-03/F-06/F-07/F-08/F-10/F-12/F-21 + R6-Testhärtung. Verifikation: 290+ Unit/Contract-Tests grün, `tsc -b` 0, 20/21 Container healthy (redis_exporter ohne Healthcheck — pre-existent), Live-OpenAPI/curl/SQL-Beweise dokumentiert. **Nicht gepusht** (Push-Protection wartet auf Ben).

### Ops-Detailverifikation (selbst geprüft) — restic, Alerts, F-13

**restic-Skript (`scripts/backup/restic_backup.sh`) — solide (atk-ops-H4 widerlegt):** `set -euo pipefail`; `bash -n` sauber; pg_dump via **explizitem** `if ! docker exec … pg_dump …; then die` (kein maskierendes Pipe), plus Leer-Datei-Check (`[[ ! -s ]]`) und `pg_restore --list`-Integritätsprüfung vor der Weiterverarbeitung; `forget --prune` läuft **nach** erstelltem Snapshot (Fehler wird geloggt, Snapshot bleibt); `restic check` als separater Wochenlauf. Der einst „grün aber kaputt" gewesene Commit `fa0b53ae1` ist jetzt genuin robust. **P2-Note:** `restic check` ist nicht Teil jedes Backups — ein content-korrupter-aber-geschriebener Snapshot fällt erst beim Wochen-Check auf (durch restic-Content-Addressing + pg_restore-Vorcheck geringes Restrisiko).

**Slack-Alert bei Worker-Ausfall (DoD §8.9) — real:** `promtool check rules` → SUCCESS (celery-alerts 20 Regeln, docker-alerts 13). `CeleryWorkerDown: ablage_celery_worker_up == 0 or absent(...)` — die `absent()`-Klausel feuert auch bei komplett verschwundener Metrik. Metrik **live vorhanden**: `curl prometheus/api/v1/query?query=ablage_celery_worker_up` → 2 Serien (beide Worker = 1). Der Worker-Ausfall-Alert ist also gedeckt und würde feuern.

**F-13 — Queue-Backlog-Alerts sind tot (P2, erklärt den F-12-Blindfleck):**
```
$ curl prometheus/api/v1/query?query=ablage_celery_queue_length   → result count: 0   (Metrik fehlt komplett)
```
Ursache: `app/workers/celery_metrics.py:330` `update_queue_metrics()` setzt die Gauge `ablage_celery_queue_length`, wird aber **nirgends aufgerufen** (`grep` findet nur die Definition). Damit können `CeleryQueueBacklog` (>50), `CeleryQueueBacklogCritical` (>200) und `CeleryQueueBlocked` **nie feuern** — genau deshalb blieb der 207-Nachrichten-Stau in `monitoring` (F-12) unbemerkt. Zusätzlich iteriert `update_queue_metrics` nur über `inspect.active_queues()` (= konsumierte Queues) → eine orphan Queue wäre selbst bei verdrahteter Metrik unsichtbar (doppelter Blindfleck). **Empfehlung:** `update_queue_metrics` periodisch aufrufen (Beat oder Metrics-Server-Thread) **und** über eine feste Queue-Liste statt nur `active_queues()` iterieren, damit auch konsumentenlose Queues erfasst werden. **Kein Fix jetzt** (Monitoring-Architektur-Entscheidung; F-12-Kerndefekt bereits behoben; F-12-Fix bringt `monitoring` immerhin in `active_queues`).

**entrypoint-Lock (`docker/entrypoint.sh`) — Kern robust, ein P2-Race:** `pg_advisory_lock(815001)` macht die Migration **exactly-once über alle Container** (nur `backend` migriert, `worker`/`worker-cpu`/`beat` haben `RUN_MIGRATIONS=false`); Migrations-Subprozess nutzt die DDL-Owner-URL, das CMD behält die App-Rolle; bei alembic-Fehler `sys.exit(rc)` (Container startet nicht mit kaputtem Schema). **F-14 (P2):** Die Nicht-Migratoren warten **nicht** auf den Migrator — sie überspringen die Migration und `exec celery` sofort. Auf Fresh-Clone/Schema-Change könnte ein Worker/Beat gegen ein halb-migriertes Schema starten (Fenster: Sekunden). Gemildert: normaler Restart = Migration ist No-op (bereits head); Worker fragen beim Start die DB nicht aktiv ab; erster Task kommt verzögert (Beat-Intervall/API nach Migration); transienter Fehler → Retry. **Empfehlung:** Nicht-Migratoren den Advisory-Lock **blockierend** acquiren + sofort releasen (wartet, bis der Migrator fertig ist) statt die Migration nur zu überspringen.
