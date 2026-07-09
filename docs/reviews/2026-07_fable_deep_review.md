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
| F-06 | Push | Partner-Matching Name-`ilike` ohne Wildcard-Escaping/Mindestlänge/Nachprüfung → Falsch-Partner | P1 | ✅ Gefixt + getestet |
| F-07 | Push | Doppel-Push: `odoo_move_id` erst nach Odoo-create committet → Retry/verlorene RPC-Antwort → zweiter Entwurf | P1 | ✅ Gefixt + getestet |
| F-08 | Push | `currency_id` wird nie an Odoo gesendet → Fremdwährung bucht in EUR-Default | P1 | ✅ Gefixt + getestet |
| F-09 | Freeze | Celery-Eager-Import (`tasks/__init__.py`) registriert alle 22 gefrorenen Task-Module → include-Freeze wirkungslos (nur Beat-Prune schützt) | P2 | 📋 Dokumentiert (live bestätigt) |
| F-10 | Freeze | Beat `extended-alerts-cashflow-daily` fährt täglich den gefrorenen CashflowPredictionService | P2 | ✅ Gefixt + getestet |
| F-11 | Freeze | Aktiver `predictive-actions`-Router schreibt in gefrorene InvoiceTracking-Domäne (`dunning_level++`) | P2 | 📋 Dokumentiert (Bens Scope) |
| F-12 | Ops | Tote `monitoring`-Queue: 3 aktive Beats feuern, kein Konsument → 207 Msgs gestaut, Feature tot | P1 | ✅ Gefixt + live bewiesen |
| S-01 | Security | RLS light **wirksam** (Backend=ablage_app, kein Superuser/Bypass, Kern-Tabellen RLS forced) | — | ✅ Widerlegt (verifiziert) |
| S-02 | Security | pgbouncer-Cross-Tenant-Leak **ausgeschlossen** (App direkt an postgres; GUC transaktions-lokal) | — | ✅ Widerlegt (verifiziert) |
| S-03 | Security | CORS-Reflection + CSRF-Schwächung **ausgeschlossen** (fail-closed; CSRF-Fix nur Rotation) | — | ✅ Widerlegt (verifiziert) |
| S-04 | Security | M-06-Rest: 3 einvoice-POSTs im Code ohne `current_user` (nur durch Freeze/404 geschützt) | P2 | 📋 Defense-in-Depth |
| F-13 | Ops | `ablage_celery_queue_length`-Metrik nie emittiert (`update_queue_metrics` ungenutzt) → Queue-Backlog-Alerts tot → **Wurzel des F-12-Blindflecks** | P2 | 📋 Dokumentiert (live bestätigt) |

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

**S-01 — RLS light ist real wirksam** (nicht nur Happy-Path). SQL gegen die Live-DB als effektive App-Rolle:
```
current_user = ablage_app · rolsuper=False · rolbypassrls=False
documents / invoices / approval_requests / document_versions:  rls_enabled=True, rls_forced=True
documents owner = ablage_admin  (≠ ablage_app → kein Owner-Bypass; forced schließt ihn ohnehin)
RLS-enabled: 92 / 490 Tabellen  (= „RLS light"-Kern-Scope laut Plan §7, kein Vollausbau)
```
Das Backend verbindet als Nicht-Superuser ohne BYPASSRLS, die Kern-Tabellen haben RLS **enabled UND forced** — selbst der Tabellen-Owner unterläge den Policies. Der schwerste RLS-Verdacht (Superuser-Bypass/Owner-Bypass) ist widerlegt.

**S-02 — pgbouncer-Cross-Tenant-Leak ausgeschlossen** (zwei unabhängige Gründe):
1. Das Backend verbindet **direkt** zu `postgres:5432`, **nicht** über pgbouncer (dessen `POOL_MODE=transaction` ist für den RLS-Pfad irrelevant).
2. Der RLS-Kontext nutzt `set_config('app.current_company_id', :cid, true)` — der dritte Parameter `true` = **transaktions-lokal** → wird am Transaktionsende zurückgesetzt und kann selbst über einen Transaction-Pooler nicht auf die nächste Verbindung/den nächsten Tenant leaken.

**S-03 — CORS-Reflection + CSRF-Schwächung ausgeschlossen:**
- CORS ist fail-closed: `CORS_ORIGINS=[]`, ein fremder Origin (`https://evil.example`) erhält **keinen** `access-control-allow-origin`-Header (nicht reflektiert); das isolierte `allow-credentials: true` ist ohne passenden Origin browserseitig wirkungslos.
- Der CSRF-Fix `4fd5238c4` hat **nur** die Token-*Rotation* auf echte 2xx eingegrenzt (307-Redirect-Bug), **keine** Multipart-/Pfad-Exemption eingebaut, die die Validierung schwächt. Der Verdacht einer zu breiten CSRF-Ausnahme ist widerlegt.

**S-04 — M-06-Rest (P2, Defense-in-Depth):** Die 3 einvoice-POSTs (`generate_zugferd` L217, `generate_xrechnung` L292, `validate_einvoice` L370) haben im **Code** weiterhin nur `db=Depends(...)`, kein `current_user`. Aktuell durch den Freeze geschützt (Router nicht registriert → live 404 verifiziert), aber bei Reaktivierung via `ACTIVE_OPTIONAL_MODULES=einvoice` wieder unauthentifiziert erreichbar. **Kein Fix** (Regel „gefrorene Module nicht anfassen"); **Empfehlung** an Ben: `current_user`-Dependency nachrüsten, falls einvoice je reaktiviert wird.

Weitere Security-Beobachtungen (P2, aus explore-secops-Landkarte): kein `:80→:443`-Redirect (http bleibt bedienbar); `Secure`-Cookie nur in prod (`ENVIRONMENT=production` gesetzt → greift); RLS-Schutz hängt am korrekt gesetzten `.env` auf dem Deploy-Host (verifiziert aktiv, aber ein Fresh-Clone ohne `.env` fiele auf Superuser zurück — Deploy-Hygiene-Note).

### Ops-Detailverifikation (selbst geprüft) — restic, Alerts, F-13

**restic-Skript (`scripts/backup/restic_backup.sh`) — solide (atk-ops-H4 widerlegt):** `set -euo pipefail`; `bash -n` sauber; pg_dump via **explizitem** `if ! docker exec … pg_dump …; then die` (kein maskierendes Pipe), plus Leer-Datei-Check (`[[ ! -s ]]`) und `pg_restore --list`-Integritätsprüfung vor der Weiterverarbeitung; `forget --prune` läuft **nach** erstelltem Snapshot (Fehler wird geloggt, Snapshot bleibt); `restic check` als separater Wochenlauf. Der einst „grün aber kaputt" gewesene Commit `fa0b53ae1` ist jetzt genuin robust. **P2-Note:** `restic check` ist nicht Teil jedes Backups — ein content-korrupter-aber-geschriebener Snapshot fällt erst beim Wochen-Check auf (durch restic-Content-Addressing + pg_restore-Vorcheck geringes Restrisiko).

**Slack-Alert bei Worker-Ausfall (DoD §8.9) — real:** `promtool check rules` → SUCCESS (celery-alerts 20 Regeln, docker-alerts 13). `CeleryWorkerDown: ablage_celery_worker_up == 0 or absent(...)` — die `absent()`-Klausel feuert auch bei komplett verschwundener Metrik. Metrik **live vorhanden**: `curl prometheus/api/v1/query?query=ablage_celery_worker_up` → 2 Serien (beide Worker = 1). Der Worker-Ausfall-Alert ist also gedeckt und würde feuern.

**F-13 — Queue-Backlog-Alerts sind tot (P2, erklärt den F-12-Blindfleck):**
```
$ curl prometheus/api/v1/query?query=ablage_celery_queue_length   → result count: 0   (Metrik fehlt komplett)
```
Ursache: `app/workers/celery_metrics.py:330` `update_queue_metrics()` setzt die Gauge `ablage_celery_queue_length`, wird aber **nirgends aufgerufen** (`grep` findet nur die Definition). Damit können `CeleryQueueBacklog` (>50), `CeleryQueueBacklogCritical` (>200) und `CeleryQueueBlocked` **nie feuern** — genau deshalb blieb der 207-Nachrichten-Stau in `monitoring` (F-12) unbemerkt. Zusätzlich iteriert `update_queue_metrics` nur über `inspect.active_queues()` (= konsumierte Queues) → eine orphan Queue wäre selbst bei verdrahteter Metrik unsichtbar (doppelter Blindfleck). **Empfehlung:** `update_queue_metrics` periodisch aufrufen (Beat oder Metrics-Server-Thread) **und** über eine feste Queue-Liste statt nur `active_queues()` iterieren, damit auch konsumentenlose Queues erfasst werden. **Kein Fix jetzt** (Monitoring-Architektur-Entscheidung; F-12-Kerndefekt bereits behoben; F-12-Fix bringt `monitoring` immerhin in `active_queues`).

**entrypoint-Lock (`docker/entrypoint.sh`) — laut Landkarte robust** (pg_advisory_lock(815001), `RUN_MIGRATIONS=false` auf worker/worker-cpu/beat, `MIGRATION_DATABASE_URL` = DDL-Owner ≠ App-Rolle). Eine adversariale Race-Tiefenprüfung (Migrator-Tod bei gehaltenem Lock) steht als Rest-Item in Iteration 2.
