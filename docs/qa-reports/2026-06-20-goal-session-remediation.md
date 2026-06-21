# Goal-Session Remediation — 2026-06-20

**Branch:** `fix/az-deep-remediation` → `merge --no-ff` nach **`master` = `43971d7ae`** (gepusht).
**Alembic head:** 270. **Voriger master:** `e122a1dc8` (strikter Vorfahre → konfliktfrei).
**Revert-Anker:** Tag `pre-merge-master-backup-2026-06-20` · Rollback: `git revert -m 1 43971d7ae`.

Dieser Lauf hat die nach dem A-Z-Audit **genuin offenen** Findings neu verifiziert (stale vs.
echt-offen) und die autonom + nachhaltig lösbaren vollständig behoben — jeweils pro Fix
isoliert reproduziert (kein False-Green) und live/Test-DB-verifiziert. Tokens/Zeit waren kein
Faktor; ULTRATHINK.

---

## 1. Voll behoben (committet, je verifiziert)

### GET-500-Sweep: 10 → 0 (parameterlose GET-Endpoints)
Der F-31-Loop hatte „192→0" gemeldet, aber per **Stichprobe** — ein **vollständiger** Sweep
über alle 1061 parameterlosen GET-Endpoints fand einen ganzen verpassten Cluster:
- **Training-Quality-Cluster** (5 Endpoints, nie funktional, Modell↔Code-Schema-Drift):
  `/training/exports` (VerificationStatus aus falschem Modul), `/training/coverage/status`
  (int−None bei NULL-Profilfeldern), `/training/quality/check` + `/retraining-recommendation`
  (`OCRTrainingSample.correction_history` existiert nicht → `source=='correction'`;
  `OCRQualitySnapshot.timestamp` → echte Spalte `snapshot_time`),
  `/training/quality-reports/comparison/all` (OCRCorrection-Import → OCRValidationCorrection;
  undefiniertes `since`; `OCRBackendBenchmark.table_accuracy` existiert nicht → CER-auf-Tabellen-Proxy).
- **`/health/startup` 503**: Redis-Check baute die URL aus `REDIS_HOST:REDIS_PORT`
  (Host-Mapping `localhost:6380`, im Container unerreichbar) statt aus `settings.REDIS_URL`.
- **`/rag/customers/search`** (Timeout): Route-Shadowing (`/{customer_id}` vor `/search`) +
  falsche Spalte `last_sync_at`→`last_full_sync_at` (8 Stellen) + fehlendes `rollback()`
  (pg_trgm-Fehler brach die TX ab → ILIKE-Fallback `InFailedSQLTransactionError`).
- 4 `streckengeschäft`-„Fehler" waren Sweep-Script-Artefakte (UnicodeEncodeError am `ä`).
- **Ergebnis: voller Re-Sweep 0/1061 5xx**, keine Regression.

### permission-cache (RBAC) — war dauerhaft tot
Kein „disabled", sondern ein **Client-Wiring-Bug**: `_get_redis_client()` cachte den
`RedisStateManager` statt des rohen aioredis-Clients → jede `.get/.setex/.delete/.scan_iter`
warf still `AttributeError` → **permanenter per-Request-In-Memory-Fallback, kein Worker-Sync**.
Fix: über `manager.get_client()`. Invalidierung war bereits zentral. **43 Tests** (inkl.
Wiring-Regression-Guard, ohne Fix ROT).

### rag `get_card` — Perf + Daten-Verschmutzung
Für nicht-existente Kunden lief die volle RAG+LLM-Pipeline UND es wurde eine **leere Junk-Card
persistiert** (15-40 s + DB-Müll). Fix: früher Return `None` ohne Quell-Dokumente. Warmer
Aufruf **0,16 s**, 404, keine Card.

### PaymentService company-scope (Multi-Tenant-Isolation)
War user-scoped (Migration 232 unvollständig) → company-scoped Konten haben `user_id=NULL` →
„Bankkonto nicht gefunden". 9 Isolations-Methoden auf `company_id` umgestellt, **Migration 269**
(`PaymentOrder`/`PaymentBatch.user_id` → nullable; auf Live-DB angewandt + in source),
`acting_user_id`-Audit, Response `user_id`→Optional, 9 Routes + Saga umgestellt, `get_skonto`
bleibt user-scoped. **2 strict-xfail-Tests grün gegen echte Test-DB** (A sieht nur A). Cascade
3 maskierter pre-existing Bugs mitgefixt (`data.end_to_end_id`, Test-IBAN-Prüfziffern,
`db_payment.bank_account`-Assertion). 77 Mock-Tests grün, Live-Endpoints 200.

### GoBD: signiertes, persistiertes, versioniertes Verfahrensdokumentations-PDF
On-premises, **ohne externes Zertifikat / Cloud**: neuer `DocumentSigner` (selbst-enthaltener
RSA-PSS/SHA-256, interner Key in beschreibbarem Volume `GOBD_SIGNING_DIR`; `/app/certs` ist
read-only). `ProcedureDocService.generate_signed_pdf` (reportlab-PDF → SHA-256 → signieren →
MinIO → Metadaten), **Migration 270** (additive `pdf_*`-Spalten; auf Live-DB), 3 company-scoped
Endpoints (`sign-pdf` / `{id}/pdf` / `{id}/verify`). **4 Unit-Tests + Service-E2E gegen echte
DB+MinIO** (PDF 11,7 KB, `sha_matches`/`signature_valid`/`tamper_detected` alle True).

### RLS_ENFORCE_DEFAULT — bounded fail-closed (opt-in)
Neuer Schalter (Default **AUS** → keine Verhaltensänderung). Wenn AN, verweigert
`set_rls_company_context` fehlenden ODER ungültigen Tenant-Kontext hart — schliesst eine echte
**fail-OPEN-Lücke** (ungültige `company_id` wurde im `except ValueError` still verschluckt →
Query ohne Tenant-Filter). **4 adversariale Tests**. _Bewusst NICHT enthalten:_ voller
RLS-Policy-Abschluss (siehe offen).

### Weitere (committet)
F-14 (`build:strict`-CI-Gate), F-27 (`change-password` prüft altes PW), F-08
(Payment-Prod-Guard), F-24 (Port-Bind 127.0.0.1), Test-Infra-Enabler (db-Fixture
`DROP SCHEMA CASCADE` + Extensions), auto_file_document (`data_category`), F-15 OTEL-SDK,
F-28 (surya-Dataset-Pfad), SeasonalPatternResponse-Shadowing-500, Dedup-Ratchet (3/9 echt
aufgelöst, Rest dokumentiert), conftest-`max_locks`-Limit dokumentiert.

---

## 2. Genuin offen (dediziert / Entscheidung nötig)
- **RLS-Policy-Reconciliation** — Substrat inkonsistent: 4 überlappende Migrationen mit **3
  verschiedenen** Session-Vars (`current_user_id`/`current_company_id`/`current_tenant_id`);
  Mig 210 erzwingt auf einer nie-gesetzten Var; `company_id IS NULL`-Leak. Braucht
  Policy-Reconciliation + `pg_policies`-Live-Audit + Route-Exemption, bevor der Flag produktiv AN kann.
- **F-21 E2E (~16 Specs)** — auf echte App-Bugs gegated (React.lazy/Suspense-Hang über ~22
  Routes; fehlender CPU-OCR-Worker); `fixme`-Flip wäre fake-green.
- **F-30 Onboarding** — G11-Produktentscheidung (4→1).
- **2 saubere A-Z-Loop-Runs** (DoD) — braucht dediziertes RAM-Fenster + Worker-Stop.

---

## 3. Verifikations-Gotchas (für Folgeläufe)
- Test-DB im Container: `export TEST_DATABASE_URL="${DATABASE_URL/ablage_system/ablage_test}"`
  (`postgres:5432/ablage_test`). NIE zwei pytest gleichzeitig auf ablage_test (Schema-Race).
- `DROP SCHEMA CASCADE` der ~480-Tabellen-Schema sprengt `max_locks_per_transaction` (Default 64)
  → SKIP bei Wiederholung auf befüllter Test-DB; Fix `-c max_locks_per_transaction=256` (Cluster-
  Reconfig, gated) oder ablage_test neu anlegen. CI (frische DB) unbetroffen.
- pytest im GPU-Image braucht `CUDA_VISIBLE_DEVICES=''`. Backend-Boot lädt OCR-Modelle (~1-3 Min).
  `127.0.0.1` statt `localhost` (Windows-IPv6). `/app/certs` read-only; `/app/outputs` schreibbar.
- Cached Module brauchen `docker restart`; nur fehlgeschlagene Imports re-importieren lazy.
- Docker-Desktop-Engine-Hänger (`dockerDesktopLinuxEngine` 500) → `wsl --shutdown` heilt sofort.
