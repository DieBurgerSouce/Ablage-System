# F-15 + F-16 — RLS-Worker-Kontext-Task (ausgearbeitete Spec)

**Kontext:** Go-Live-Blocker aus dem Adversarial-Deep-Review (`docs/reviews/2026-07_fable_deep_review.md`). Per Ben-Entscheidung als dediziertes Task vor der Scharfschaltung von OdooMirrorService + worker-Importen (~Mitte Aug) zu lösen. **Diese Datei ist die Ausarbeitung — sie führt keine Migration aus.** Migration/Umsetzung erst auf Bens Signal (Migration = GATE).

---

## 1. Das Problem (verifiziert)

**F-15 — `documents`-RLS permissiv (DoD-8-Verletzung):** 8 PERMISSIVE Policies auf `documents`, per OR verknüpft. Escapes `current_user_id IS NULL`/`current_user_id=''` (in `documents_owner_select/update/delete`) und `company_id IS NULL` (in `documents_tenant_isolation`) heben die strikte `tenant_isolation_documents` aus.
```
(ablage_app, RESET ALL) SELECT count(*) FROM documents  → 3   (DoD-8 verlangt 0)
```

**F-16 — kein Background-Worker setzt RLS-Kontext (Regression aus der RLS-light-Aktivierung 2026-07-09):**
```
grep set_rls_company_context / rls_bypass in app/workers/ + app/services/  → 0 aufrufende Stellen
(ablage_app, RESET ALL) INSERT INTO documents(company_id=<non-null>)  → RLS WITH CHECK LEHNT AB
```
Nur die HTTP-Middleware (`company_context.py:67/133`) setzt Kontext. **Kopplung:** Die Escapes sind *load-bearing* — Worker LESEN `documents` nur über `current_user_id IS NULL`. F-15 (Escapes entfernen) ohne F-16 (Worker-Kontext) bricht die gesamte OCR/Mirror/Import-Pipeline. Reihenfolge daher zwingend: **erst Worker-Kontext, dann Escapes entfernen.**

---

## 2. Blast-Radius (verifiziert)

**Ersteller (legen `documents` an, KENNEN die company_id):**
| Pfad | Stelle | company_id-Quelle |
|---|---|---|
| OdooMirrorService | `odoo_mirror_service.py:440` (`_persist_attachment`) | `connection.company_id` |
| Kanonischer Import (folder/email/WA-WE) | `document_creation.py:213` (`create_import_document`, Param `company_id`) | Funktions-Parameter |

**Prozessoren (lesen/ändern `documents` per ID, kennen company_id erst NACH dem Read):** OCR (`ocr_tasks.py` — `select(Document)` + `document.status=…` an ~8 Stellen: 215/220/346/397/492/948…), `gobd_compliance_tasks` (Auto-Archiv), auto_filing, annotation, barcode, cleanup, customer_detection, document_intelligence u. a. — **~20 aktive Worker-Task-Module** berühren `documents`; insgesamt **57 `get_async_session_context`-Aufrufe in `app/workers/`**. (Gefrorene Module wie banking/ai_ethics/chain sind ebenfalls dabei, aber irrelevant — sie laufen nicht.)

**Kritischer Constraint:** `get_async_session_context` ist **NICHT worker-exklusiv** — 4 API-Endpunkte nutzen sie auch (`api/v1/exports.py`, `odoo_webhooks.py`, `rag/chat_ws.py`, `tasks.py`) + 3 Services. **Ein pauschaler Bypass in dieser Factory wäre FALSCH** (würde RLS für diese API-Pfade aushebeln). Der Bypass muss worker-scoped/explizit sein.

**Verfügbare Helfer (existieren, werden nur nicht genutzt):**
- async: `set_rls_company_context(db, company_id)` (`company_context.py:384`), `rls_bypass_context(db)` (CM, :541), `enable_rls_bypass(db)` (:475)
- sync: `set_rls_company_context_sync(session, company_id)` (`session.py:208`), `rls_bypass_context_sync(session)` (:282)

---

## 3. Designentscheidung (für Ben)

Zwei Sub-Muster brauchen zwei Behandlungen:
- **Ersteller** kennen company_id → **Company-Kontext** setzen (scoped, sauberste Semantik: der Insert läuft company-gescoped, WITH CHECK passt).
- **Prozessoren** arbeiten per document_id (Chicken-Egg: company_id erst nach Read bekannt) → **Bypass** (systemische, vertrauenswürdige Pipeline-Tasks; verarbeiten bereits über autorisierte Kanäle angelegte Dokumente).

**Empfohlener Ansatz (risikoarm, safe-by-default):**
1. **Neuer expliziter Worker-Session-Helfer** statt Änderung der geteilten Factory:
   ```python
   # app/db/session.py
   @asynccontextmanager
   async def get_worker_session_context(company_id: UUID | None = None):
       async with get_async_session_context() as session:
           if company_id is not None:
               await set_rls_company_context(session, company_id)   # Ersteller: scoped
           else:
               await enable_rls_bypass(session)                     # Prozessoren: systemisch
           yield session
   ```
   Default-Factory bleibt unverändert → die 4 API-Sites sind **nicht** betroffen (safe-by-default).
2. **Ersteller** auf `get_worker_session_context(company_id=…)` umstellen: Mirror-Task + der Import-Task-Wrapper, der `create_import_document` aufruft.
3. **Prozessoren** (die document-berührenden Worker-Tasks) auf `get_worker_session_context()` (Bypass) umstellen. Pragmatisch: nur die document-berührenden ~20 Module, nicht alle 57 (aber Konsistenz-Regel dokumentieren: „Worker, die RLS-Tabellen berühren, nutzen get_worker_session_context").
4. **Erst danach** die F-15-Migration (Escape-Entfernung).

**Alternative, die Ben abwägen sollte:** separate DB-Rolle `ablage_worker` mit BYPASSRLS (Worker-Deployment nutzt sie, HTTP-Backend bleibt `ablage_app`). Sauberste Trennung, aber zwei Rollen + `.env`/compose-Änderung. Für 6–10 interne User mit App-Layer-Primärschutz + Privat-Doppelverschlüsselung ist der Helfer-Ansatz (oben) verhältnismäßiger.

---

## 4. F-15-Migration (nach Worker-Kontext, GATE-pflichtig)

Neue Alembic-Migration (Head 271 → 272). **Nur USING-Klauseln (Lesepfad) härten; WITH CHECK unangetastet lassen** (Inserts der Ersteller laufen dann über den gesetzten Company-Kontext, nicht über den `company_id IS NULL`-Escape):

```sql
-- documents_owner_select / _update / _delete: no-context-Escape entfernen
ALTER POLICY documents_owner_select ON documents USING (
    (owner_id)::text = current_setting('app.current_user_id', true)
    OR current_setting('app.is_admin', true) = 'true'
);   -- OR current_user_id IS NULL / = ''  ENTFERNT   (analog _update, _delete)

-- documents_tenant_isolation: NULL-company-Escape aus USING entfernen (WITH CHECK bleibt)
ALTER POLICY documents_tenant_isolation ON documents USING (
    is_rls_bypass_enabled()
    OR company_id = get_current_company_id()
);   -- OR company_id IS NULL  ENTFERNT (nur USING)
```
`is_rls_bypass_enabled()` bleibt → die worker-Bypass-Sessions (Prozessoren) funktionieren weiter. Nach der Migration: no-context-Read = 0 (DoD-8), Company-Kontext-Read = gescoped, Bypass-Read = alle.

**Analog prüfen (separater Schritt):** `invoices`, `approval_requests`, `document_versions` (die anderen FORCE-Tabellen) auf dasselbe Escape-Muster — der Review hat nur `documents` tief geprüft.

---

## 5. Teststrategie (der eigentliche Aufwand)

**Die bestehenden Tests mocken die DB → sie fangen F-16 strukturell nicht.** Es braucht ein **echtes-RLS-Integrations-Harness** (Test-DB, Verbindung als `ablage_app`, kein Superuser):
1. **F-15-Read-Gate:** ohne Kontext → `SELECT documents` = 0; mit User-Kontext → nur eigene/company-Docs; mit Bypass → alle. (Genau die DoD-8-Zusage.)
2. **F-16-Ersteller:** Mirror-/Import-INSERT mit gesetztem Company-Kontext → erfolgreich (WITH CHECK passt); ohne Kontext → abgelehnt (Regressionsschutz).
3. **F-16-Prozessor:** ein OCR-Task-artiger Read+UPDATE per document_id unter Bypass → funktioniert nach Escape-Entfernung.
4. **Cross-Tenant-Negativ:** User A sieht Docs von Company B nicht (auch nicht mit gesetztem falschem Kontext).
5. **Smoke der echten Pipeline** gegen die Test-DB: Upload→OCR→completed, folder-Import→Doc, (Mock-)Mirror→Doc — alle mit den neuen Sessions grün.

Ort: neues `tests/integration/test_rls_worker_context.py` (nutzt die reale Test-DB, nicht die Mock-Session). Fixture-Muster analog zu bestehenden Integration-Tests, aber mit `SET ROLE ablage_app` / echter App-Rolle.

---

## 6. Sequenzierung, Rollback, Aufwand

**Reihenfolge (zwingend):**
1. `get_worker_session_context`-Helfer + echtes-RLS-Test-Harness (rot, weil Worker noch keinen Kontext setzen).
2. Ersteller (Mirror + Import) auf Company-Kontext umstellen → Ersteller-Tests grün.
3. Prozessoren (document-berührende Worker) auf Bypass umstellen → Pipeline-Smoke grün, ALT (mit Escapes) noch grün.
4. **GATE → Ben:** F-15-Migration 272 ausführen (Escapes entfernen). Danach DoD-8-Read-Gate grün, Pipeline weiter grün (weil Worker jetzt Kontext/Bypass haben).
5. Volllauf: `docker compose exec backend pytest tests/integration/test_rls_worker_context.py` + Pipeline-Smoke + regressives ERP/privat/unit-Set.

**Rollback:** Migration 272 hat ein `downgrade`, das die Escapes wieder hinzufügt (kehrt zum Ist-Zustand zurück). Der Worker-Kontext-Code ist unabhängig sicher (setzt Kontext/Bypass, schadet mit Escapes nicht). Rollback-Reihenfolge umgekehrt: erst Migration down, dann optional Worker-Änderungen zurück.

**Aufwand grob:** Helfer + Harness 0,5 PT; Ersteller 0,5 PT; Prozessoren-Umstellung (~20 Module, mechanisch + review) 1–1,5 PT; Migration + DoD-Verifikation 0,5 PT; Puffer für echte-RLS-Überraschungen 0,5 PT. **≈ 3–4 PT.** Passt in Bens „vor Mitte August"-Fenster.

**Nicht vergessen:** Der WA/WE-Import (`scripts/import_wa_we.py --execute`) ist ebenfalls ein Ersteller ohne Kontext → muss vor seinem einmaligen Lauf denselben Company-Kontext setzen (bzw. über den instrumentierten Import-Pfad laufen).
