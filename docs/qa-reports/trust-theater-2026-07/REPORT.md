# Trust-Theater K1 — „Beweisen"-Button (2026-07-12)

**Auftrag:** Die unsichtbare GoBD-Compliance sichtbar und erlebbar machen. Hash-Chain, Merkle, RFC-3161-TSA und DB-Immutability existierten im Backend, aber kein Nutzer sah sie je (Perception-Audit §6, Trust-Gaps T-01…T-04).

**GATE-Entscheid (Ben):** K1 „Beweisen"-Button — Live-Verifikation direkt am Dokument (statt K2 Prüfer-Modus / K3 Integritäts-Dashboard).

**Branch:** `feature/neuausrichtung-2026-07` (= Live-Code, Backend bind-mounted) · lokale Commits, kein Push.

---

## 1. Was gebaut wurde

### Backend

| Baustein | Datei | Beschreibung |
|---|---|---|
| **Prove-Endpoint** | `app/api/v1/integrity.py` | `POST /api/v1/integrity/documents/{id}/prove` — lädt das Original serverseitig aus MinIO, berechnet SHA-256 neu, vergleicht mit der versiegelten Baseline (`DocumentArchive.content_hash`, sonst `DocumentHash.file_hash`), prüft die Beweiskette des Dokuments und den RFC-3161-Token. **Kein Upload nötig** — das fehlte bisher (Verify existierte nur upload- oder archive_id-basiert). Antwort differenziert statt Pauschal-Boolean: `verdict` (verified/tampered/no_baseline), `file_hash_matches`, `baseline_source`, `chain{…}`, `tsa{…}`, `message_de`. |
| **Ketten-Prüfung pro Dokument** | `app/services/compliance/audit_chain_service.py` | Neu: `verify_document_entries()` — prüft Content-Hash, Combined-Hash und Verkettung zum Vorgänger für alle Einträge EINES Dokuments (schnell, dokument-lokal; firmenweite Komplettprüfung bleibt beim Beat-Task `verify_chain`). Respektiert die Immutability-Trigger-Allow-List (nur `is_verified`/`last_verified_at`/`verification_error`). |
| **Schemas** | `app/db/schemas_integrity.py` | `DocumentProofResponse`, `ChainProofInfo`, `TsaProofInfo`, `ProofVerdictEnum`. |

### Beifang: 2 echte latente Bugs gefixt

1. **TSA-Verify war immer falsch-negativ** (`archive_service.py`): Der Token wird bei der Archivierung über die **rohen Digest-Bytes** erstellt (`request_timestamp(data=bytes.fromhex(content_hash))`, intern nochmal SHA-256 → Imprint = SHA256(digest)), aber beim Verify gegen die **vollen Datei-Bytes** geprüft (Imprint-Vergleich = SHA256(datei)) → jede TSA-Prüfung wäre fehlgeschlagen. Fix: Verify nutzt jetzt dieselben Digest-Bytes wie die Erstellung.
2. **5 Compliance-Archiv-Endpoints waren für Bearer-Flows nie funktionsfähig** (`compliance.py`): `POST/GET /compliance/archive*` nutzten `get_user_company_id_dep` (liefert nur die ID, setzt **keinen** RLS-GUC) → RLS auf `documents`/`document_archives` lieferte 0 Zeilen → 404 „keine Berechtigung" trotz Berechtigung. Fix: neue Dependency `require_company_id` (via `require_company`, setzt RLS-Kontext). Live bewiesen: Archivierung vorher 404 → nachher 201.

### Frontend

| Baustein | Datei | Beschreibung |
|---|---|---|
| **DocumentIntegrityPanel** | `frontend/src/features/gobd/components/DocumentIntegrityPanel.tsx` | Badge im **immer sichtbaren** Header der Dokument-Detailseite („GoBD-versiegelt seit TT.MM.JJJJ · SHA-256" bzw. ehrlich „Noch nicht versiegelt") + Button **„Integrität beweisen"** → Dialog mit grünem Beweis-Panel („Mathematisch bewiesen: unverändert" + verständliche deutsche Erklärung), rotem Manipulations-Befund (mit Handlungsanweisung, technische Details standardmäßig aufgeklappt) oder ehrlichem „keine Baseline"-Zustand. Technischer Aufklapper: Baseline-Quelle, beide Hashes, Beweiskette, TSA, Prüfzeitpunkt. |
| **Header-Einbau** | `frontend/src/app/routes/documents.$documentId.tsx` | Panel neben der MIME-Badge — erfüllt den P3-Prüferin-Walk (prüft `main.innerText` auf `/SHA\|Hash\|Prüfsumme\|Zeitstempel\|TSA\|Signatur\|Integrität/i` VOR jedem Tab-Klick). |
| **API-Reparatur** | `frontend/src/features/gobd/api/gobd-api.ts` | Die gobd-Feature-API rief `/archive/documents/*` auf — **diese Pfade existierten im Backend nie** (toter Code seit Einführung). Repariert auf die realen Pfade (`/compliance/archive*`) + neue `proveDocumentIntegrity()`. Der alte `verifyDocumentIntegrity`-Wrapper (genutzt von `ArchiveManagement`) läuft jetzt über den Prove-Endpoint. |
| **Hook** | `frontend/src/features/gobd/hooks/use-gobd.ts` | `useProveDocument()` (kein Toast — das Panel rendert das Ergebnis selbst); `useArchiveEntry` mit `retry: false` (404 = „nicht versiegelt", kein Fehler). |

**Bewusst NICHT gebaut:** Lebenszyklus-Tab-Ergänzung (TabsList ist im SplitDocumentViewer dupliziert — Risiko ohne Zusatznutzen, Header-Panel erfüllt den Walk); `/trust-dashboard` bleibt eingefroren und wird nicht verlinkt. Keine Schema-Migration nötig.

---

## 2. Beweise

### ① Positiver Live-Beweis (echtes Dokument, echter Stack) — GRÜN ✅

- Dokument `a24af4ff-cb5c-4eea-99b1-80e07e399520` (Perception-Fixture „Bürohaus Müller", Firma „Perception Audit GmbH") via `POST /compliance/archive` GoBD-versiegelt (HTTP 201, Frist bis 2036-12-31).
- **API:** `POST /integrity/documents/{id}/prove` → `verdict: verified`, `file_hash_matches: true`, `baseline_source: archiv`, Kette intakt. Der Server lädt dabei wirklich die Original-Bytes aus MinIO und hasht neu — kein gespeichertes „OK" wird wiedergekäut.
- **UI (Playwright, echter Login als Prokurist):** Badge „GoBD-versiegelt seit 12.07.2026 · SHA-256" → Klick „Integrität beweisen" → grünes Panel mit identischen Hashes. Screenshots: `screenshots/01-detail-header-mit-siegel-badge.png`, `screenshots/02-beweis-gruen-live.png`. Vorher-Vergleich: `screenshots/00-vorher-detail-ohne-trust-oberflaeche.png` (Perception iter02 — keinerlei Trust-Oberfläche).

### ② Negativ-Beweis (manipulierte Kopie, ISOLIERT) — ROT ✅

**Warum nicht am Live-Archiv:** Die `gobd_audit_chain` ist per DB-Trigger unlöschbar (DELETE immer geblockt). Ein Live-Rot-Test würde die echte Beweiskette **dauerhaft** mit `INTEGRITY_CHECK_FAILED`-Einträgen verschmutzen. Deshalb dreistufige Beweiskette:

1. **Logik-Beweis (isolierte pytest-Umgebung, echte SHA-256-Mathematik):** `tests/unit/test_prove_integrity_logic.py` — baut eigene In-Memory-Objekte, manipuliert NUR diese Kopien:
   - 1 geändertes Byte im Inhalt (`119,00 €` → `919,00 €`) → `hash_match=False`, Archiv wird `is_verified=False` + Begründung „Manipulation".
   - Manipuliertes `event_data` in der Beweiskette → `valid=False`, `broken_at_sequence=2`.
   - Gefälschter `previous_hash` (Verkettung) → `valid=False`, `broken_at_sequence=3`.
   - Fremde Firma → `ValueError` (kein Prüfrecht).
2. **UI-Rot-Beweis (Playwright, Response-Interception — echtes Archiv unberührt):** rotes Panel „Integrität verletzt" mit Handlungsanweisung und sichtbar abweichendem Hash (`deadbeef…` vs. Baseline). Screenshot: `screenshots/03-beweis-rot-manipulation-erkannt.png`. Skript: `frontend/e2e/perception/trust-proof.mjs`.
3. **Bindeglied:** Der Live-Test `test_prove_liefert_differenzierten_beweis` schlägt hart Alarm, falls das echte Archiv je `tampered` meldet.

### Tests & Gates (alle grün)

| Gate | Ergebnis |
|---|---|
| pytest neu (`test_prove_integrity_logic.py` 8 + `test_prove_endpoint_live.py` 3) | **11 passed** |
| pytest Regression (`test_openapi_generates`, `test_annotations_endpoint_live`, `test_rls_policy_guards`) | **6 passed** |
| vitest (`DocumentIntegrityPanel.test.tsx`) | **7 passed** |
| `tsc -b` (typecheck) | **0 Fehler** |
| Live-Smoke: prove auf echtem Dokument | 200, `verified` |
| Live-Smoke: prove mit Zufalls-UUID | 404 (Isolation) |

### Senior-Review (adversarial, vor Commit)

Unabhängiger Review-Agent über den gesamten Diff: **keine High-Confidence-Korrektheits- oder Security-Bugs.** Bestätigt durch Code-Trace: TSA-Doppel-Hash-Fix konsistent mit der Erstellung (Imprint = SHA256(SHA256(Datei)) auf beiden Seiten); kein Multi-Tenancy-Leak (alle Queries company-gefiltert, der company-agnostische `get_document_integrity_status`-Helper wird im Endpoint defensiv geguarded); `verify_document_entries` mutiert exakt die Trigger-Allow-List (Migration 234) und nichts anderes; Verhaltensänderung der 5 Archive-Endpoints bricht keine bestehenden Cookie-/Header-Flows. Geforderter Regression-Guard für den TSA-Pfad wurde nachgeliefert (`test_tsa_verify_nutzt_digest_bytes_wie_bei_erstellung` — inkl. Gotcha: das Modul `tsa_service` wird im Package-Namespace vom gleichnamigen Singleton verschattet, monkeypatch braucht importlib).

---

## 3. Ehrliche Grenzen & Folgearbeit

1. **TSA im Live-Stack ungenutzt:** Kein Dokument hat bisher einen RFC-3161-Token (`use_tsa=false` Standard; FreeTSA-Fallback bräuchte Internet — On-Premises!). Das Panel sagt das ehrlich („Kein qualifizierter Zeitstempel vorhanden — Versiegelung basiert auf der internen Hash-Beweiskette"). Der TSA-Verify-Pfad ist durch den Fix jetzt korrekt, aber empirisch nur strukturell geprüft. → Folgearbeit: interne TSA-Konfiguration ODER TSA-Erwartung aus der Verfahrensdoku streichen.
2. **Auto-Archivierung:** Nur explizit archivierte Dokumente haben eine Archiv-Baseline; der tägliche `gobd_auto_archive_task` (03:30, nach Grace-Tagen) versiegelt nach. Neue Dokumente zeigen bis dahin ehrlich „Noch nicht versiegelt" + no_baseline-Erklärung. → Optional: „Jetzt versiegeln"-Aktion für Admins im Panel.
3. **Weitere Compliance-Endpoints ohne RLS-Kontext:** `/compliance/report`, `/quick-status`, retention u. a. nutzen weiter `get_user_company_id_dep` — je nach Tabellen-RLS liefern sie ggf. leere Zahlen statt Fehlern. Nicht K1-Scope, gleiche Fix-Schablone (`require_company_id`) liegt jetzt bereit.
4. **T-01/T-03/T-04 bleiben offen** (Audit-Trail-Tab am Dokument, Verfahrensdoku-Download in der Navigation, Prüfer-Rollen-Sicht = K2). Explore-Erkenntnis fürs nächste Mal: RBAC-Rolle `tax_advisor` existiert bereits (read-only, Migration 073/259), aber `accept_invite` legt keine `UserCompany`-Zeile an und `access_until` wird zur Request-Zeit nicht geprüft — beides Pflicht-Reparaturen für K2.
5. **Chain-Statistik-Anzeige:** Der grüne Beweis zählt nur die Einträge DIESES Dokuments (dokument-lokal). Die firmenweite Ketten-Gesundheit zeigt weiterhin `/admin/audit-trail` (stündlicher Beat-Task).
6. **Review-Finding (niedrig):** `chain.entries_total` ist auf die neuesten 100 Einträge gekappt (`get_entries_by_document(limit=100)`) — da jeder „Beweisen"-Klick selbst einen `INTEGRITY_CHECK_*`-Eintrag anhängt, kann ein viel geprüftes Dokument den Cap irgendwann erreichen; die Zahl wäre dann „geprüfte", nicht „alle" Einträge. Kein Security-/GoBD-Impact (Komplettprüfung = `verify_chain`-Beat), aber Kandidat für Umbenennung/echten Count.

## 4. Abschluss-Validierung (Nachfrage Ben, 2026-07-12 abends)

Systematischer Voll-Check nach Commit `2007a810c`:

| Prüfung | Ergebnis |
|---|---|
| Working Tree | sauber (einzig `.login-times.json` = pre-existierendes Perception-Harness-Artefakt, nicht von dieser Session) |
| **Übersehene Bestandssuite** `tests/integration/test_gobd_api.py` (testet genau die geänderten Endpoints; im ersten Durchgang nicht gelaufen) | **21 passed** ✅ |
| Weitere Konsumenten der geänderten Module (Backend-Tests + Frontend-Importe außerhalb features/gobd) | keine — grep-verifiziert |
| Ruff-Diff `compliance.py` HEAD~1↔HEAD | identisch (keine neuen Meldungen) |
| mypy-Diff HEAD~1↔HEAD (5 Dateien) | 206 → 244; **alle ~38 neuen = dieselben SQLAlchemy-ORM-Noise-Klassen wie der Bestand in denselben Dateien** (Column-Typ vs. Laufzeitwert, untyped `StorageService.__init__`, impliziter `Company`-Re-Export — Nachbarcode `verify_chain` erzeugt identische Meldungen). Kein `Any` eingeführt, keine neue Fehlerklasse; mypy ist für diese Dateien kein scharfes Gate (206 pre-existierend). |
| Stack-Health | alle ablage-Container healthy, Backend+Frontend 200 |
| OpenAPI | prove-Route vorhanden |
| **Live-Beweis als ECHTE Zielpersona** `pruefer@localhost.com` (Viewer — erster Durchgang testete nur Prokurist) | Archiv-Info 200 (`is_verified: true`), prove → `verified`, Kette valid, 4 Einträge (jeder Beweis protokolliert sich selbst in der Kette — by design) ✅ |
| Screenshots | 4 Dateien vorhanden (00-vorher, 01-Badge, 02-grün, 03-rot) |

## 5. Reproduktion

```bash
# Backend-Tests (im Container, GPU aus)
docker exec -e CUDA_VISIBLE_DEVICES= ablage-backend pytest \
  tests/unit/test_prove_integrity_logic.py tests/integration/test_prove_endpoint_live.py -v

# Frontend-Tests (Suite einzeln — Windows-Worker!)
cd frontend && npx vitest run src/features/gobd/components/__tests__/DocumentIntegrityPanel.test.tsx
npm run typecheck

# UI-Beweis-Screenshots (Login-Rate-Limit beachten: ≥15 s Abstand)
cd frontend && node e2e/perception/trust-proof.mjs <documentId>
```
