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

## Findings-Register

Klassifikation: **P0** = merge-blockierend (Datenverlust, Sicherheitsloch, GoBD-Bruch, Odoo-Korruption) · **P1** = merge-blockierend (falsche Daten, tote Kernfunktion) · **P2** = dokumentieren, nicht blockieren.

| ID | Fläche | Titel | Klasse | Status |
|---|---|---|---|---|
| F-01 | Freeze | Misch-Router `finance.py` umgeht Freeze (21 Pfade live) | P1 | ✅ Gefixt + live bewiesen |
| F-02 | Freeze | Kein Regressionstest iteriert die echte App gegen die Registry (DoD §8.2-Lücke) | P1 | ✅ Test gebaut, 3/3 grün |
| F-03 | Mirror | GoBD-Spiegel verifiziert Hash nie gegen `ir.attachment.checksum` (R3) | P1 | ✅ Gefixt + getestet |
| F-04 | Mirror | Kein Overlap-Lock; `documents` ohne checksum-Unique → Duplikat-Pfad + Fehl-Alarme unter Concurrency | P2 | 📋 Dokumentiert |
| F-05 | Mirror | Unparsebarer Cursor → Full-Rescan der Historie (1 RPC/Move) → Odoo-SaaS-Drosselung (R2) | P2 | 📋 Dokumentiert |
| F-06 | Push | Partner-Matching Name-`ilike` ohne Wildcard-Escaping/Mindestlänge/Nachprüfung → Falsch-Partner | P1 | 🔧 in Arbeit |
| F-07 | Push | Doppel-Push: `odoo_move_id` erst nach Odoo-create committet → Retry/verlorene RPC-Antwort → zweiter Entwurf | P1 | 🔧 in Arbeit |
| F-08 | Push | `currency_id` wird nie an Odoo gesendet → Fremdwährung bucht in EUR-Default | P1 | 🔧 in Arbeit |
| F-09 | Freeze | Celery-Eager-Import (`tasks/__init__.py`) registriert alle 22 gefrorenen Task-Module → include-Freeze wirkungslos (nur Beat-Prune schützt) | P2→P1-latent | 🔎 Verifiziere |
| F-10 | Freeze | Beat `extended-alerts-cashflow-daily` fährt täglich den gefrorenen CashflowPredictionService | P2 | 🔎 Verifiziere |
| F-11 | Freeze | Aktiver `predictive-actions`-Router schreibt in gefrorene InvoiceTracking-Domäne (`dunning_level++`) | P2 | 🔎 Verifiziere |

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

*Weitere Findings aus den Angriffsflächen A (Freeze), C (Push), D (Security), E (Ops) folgen, sobald die parallelen Beweise vorliegen. atk-mirror: H1/H2/H4 adversarial widerlegt (Move-Atomarität + serverseitiger Draft-Filter + kein lokaler Uhr-Bezug im Cursor).*
