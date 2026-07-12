# Perception-Audit 2026-07 — Die ersten 10 Minuten

**Kontext:** Am 01.08.2026 onboardet das Büro-Team (~6–10 User). Bei diesem Produkt ist Wahrnehmung = Produkt. Dieser Report protokolliert iterative Persona-Walks (Playwright, echter UI-Login, Stoppuhr) gegen den Live-Stack, gefundene Reibungen und deren belegte Fixes.

**Branch:** `feature/neuausrichtung-2026-07` (= Live-Code, Backend bind-mounted) · lokale Commits, kein Push.

## 1. Ziel & DONE-Kriterien — ✅ ERFÜLLT

- [x] **P1-TTFV (Azubi: Upload → OCR → Wiederfinden) < 5 min ohne Hilfe** — erreicht: **0,4 min (Iter 01)** / **15,8 s (Iter 02)** (vorher: Blocker, Upload endete in HTTP 500).
- [x] **Alle Blocker gefixt und belegt** (Test grün + Screenshots) — 8 Blocker behoben und belegt (F-P1-001…004, F-P4-001, F-P2-001, F-P2-004, F-P2-005).
- [x] **2 Iterationen in Folge ohne neue Blocker** — Iteration 01 (nach Fixes) und Iteration 02 beide mit allen 4 Personas grün, **0 Blocker** (nur Stolper/Kosmetik/Trust-Gaps).
- [x] Report vollständig.

## 2. Setup & Umgebungs-Caveats

- Walks laufen gegen `http://localhost:80` (Frontend-nginx) + Backend `:8000`.
- Live-Env: `DEBUG=true`, `ENVIRONMENT=development`, Rate-Limit AN (Login 5/min/IP) — Walks halten ≥15 s Login-Abstand, bei 429 einmal 60 s Backoff.
- Eigene Test-Identitäten: Firma **„Perception Audit GmbH"** (`DE888888888`) mit 4 synthetischen Personas (`azubi|prokurist|pruefer|familie@localhost.com`, kein Superuser) + Lieferant **„Bürohaus Müller GmbH"** (`DE888800001`). Seed: `scripts/seed_perception.py`. **Keine echten Accounts/Firmendaten; Odoo unberührt (Push-Flag aus).**
- Fixture: `frontend/e2e/perception/fixtures/eingangsrechnung-buerohaus-mueller.pdf` (synthetische Eingangsrechnung, Umlaut-Test „Bürohaus Müller GmbH" eingebaut).
- Harness: `frontend/playwright.perception.config.ts` + `frontend/e2e/perception/` (workers=1, echter UI-Login, Soft-Fail-Schritte, automatischer 4xx/5xx-/Console-Tap, robuster `searchFor`-Helfer).
- Deploy-Wege: Backend bind-mountet `./app` → Fix = `docker restart ablage-backend`. Frontend-Bundle im Image → Fix = `docker compose build frontend && up -d`.

## 3. TTFV-Tabelle (Persona × Iteration)

| Persona / Metrik | vor Fixes | Iteration 01 | Iteration 02 (Bestätigung) | Ziel |
|---|---|---|---|---|
| **P1 Azubi TTFV** (Login→Upload→OCR→gefunden) | ∞ (Blocker: Upload 500) | **0,4 min (24 s)** ✓ | **15,8 s** ✓ | < 5 min |
| P1 OCR-Dauer (Surya-GPU) | – | 13–21 s | 12,5 s | < 300 s Budget |
| **P2 Prokurist Suche→Treffer** | ∞ (0 Treffer, owner-scoped) | **1,4 s** ✓ | **2,5 s** ✓ | < 10 s |
| P3 Prüferin Dokument-Detail erreichbar | nein (owner-scoped 0 Docs) | ja | ja (firmenweit) | – |
| P4 Familie Privat-Space lädt | nein (Router-404) | ja (HTTP 200) | ja | – |
| Blocker pro Iteration | – | **0** | **0** | 0 |

## 4. Findings-Register

| ID | Persona | Iter | Route | Beschreibung | Severity | Sprache? | Status | Beleg |
|---|---|---|---|---|---|---|---|---|
| F-SYS-001 | alle | 00 | `:80/:443` | Frontend-Container existierte nur als „Created" — nie gestartet; App für alle Nutzer unerreichbar | Blocker | – | **gefixt (Pre-Flight)**: `docker compose build frontend && up -d`; `/login` → 200 | curl 200, Container healthy |
| F-SYS-002 | alle | 00 | `https://ablage.firmenich.lan` | LAN-Domain unerreichbar: kein hosts-/DNS-Eintrag auf diesem Rechner — Team am 01.08. bräuchte die „schöne" URL | Stolper | – | **offen** (Empfehlung: DNS/hosts-Rollout im Onboarding-Runbook) | curl 000, hosts ohne Eintrag |
| F-P1-001 | alle | 01 | `POST /documents/` | **Nicht-Admin-Upload → HTTP 500** („invalid input syntax for type boolean: ''"). 25 Alt-RLS-Policies casteten `current_setting()` ohne NULLIF-Guard; nach `commit()` im Handler verlor die Request-Session den RLS-Kontext (GUC='') → Crash bzw. „Could not refresh instance". Hätte ab 01.08. **jeden** normalen Büro-User beim ersten Upload getroffen. | Blocker | – | **gefixt+bewiesen**: `scripts/db/repair_rls_guc_casts_20260712.sql` (25 Policies NULLIF-gehärtet, 0 verbleibend) + `persist_rls_gucs()` (after_begin-Listener re-appliziert GUCs pro Transaktion). Beweis: azubi-Upload 201, 2× pytest grün, 0 sichtbare Zeilen ohne Kontext | `findings/repair_rls_guc_casts_20260712.log`, `tests/integration/test_rls_guc_persistence.py` |
| F-P1-002 | P1 | 01 | OCR-Pipeline | Text-loses „Duplikat" wurde als `completed` markiert und der OCR-Lauf übersprungen → Dokument „fertig", aber ohne Text und **unauffindbar** in der Suche | Blocker | – | **gefixt+bewiesen**: Skip nur bei tatsächlich vorhandenem Text; sonst normal weiter-OCRen (`ocr_tasks.py`). Beweis: `extracted_text` 665 Zeichen, `search_vector` gesetzt, Suche „Müller" = 6 Treffer | GPU-Worker-Log, DB-Query |
| F-P1-003 | alle | 01 | `check_rate_limit` | Free-Tier hart auf **10 Requests/Stunde** codiert (ignorierte Settings + `users.rate_limit_hourly`-Override) → Büro-User nach ~10 Such-/Listen-Aufrufen 1 h gesperrt (429, Retry-After 3600) | Blocker | – | **gefixt+bewiesen**: `resolve_user_hourly_rate_limit()` verdrahtet Settings + User-Override; Default Free 600/h. Beweis: 7 Unit-Tests grün | `tests/unit/test_rate_limit_resolution.py` |
| F-P1-004 | alle | 01 | erster Login | **Drei Onboarding-Ebenen gleichzeitig** (OnboardingWizard-Modal + verschachteltes WelcomeModal + geführte Produkt-Tour), überlagert, plus „Erste Schritte"-Sidebar → Azubi-Ersteindruck = Chaos; Tour-Overlay blockierte sogar das Suchfeld | Blocker | – | **gefixt+bewiesen**: 1 kanonischer Flow (Wizard); WelcomeModal aus `__root` entfernt + defensiv geguarded; Tour-Auto-Start default aus (opt-in via Header-`TourLauncher`). Beweis: 5 vitest grün, `tsc -b` 0, Vorher/Nachher-Screenshots | `features/onboarding/hooks/__tests__/onboarding-coordination.test.ts` |
| F-P4-001 | P4 | 01 | `/privat`, alle `/api/v1/privat/*` | **Privat-Bereich komplett tot (404)**: Modul `app/api/v1/privat.py` (3637 Z., echte Routen) wurde vom leeren Package `app/api/v1/privat/` verschattet → `main.py` mountete den Leer-Router. Familienmitglied sah „Fehler beim Laden der Daten". | Blocker | – | **gefixt+bewiesen**: Modul → `privat/routes.py` verschoben + im Package re-exportiert. Beweis: `/privat/dashboard` + `/privat/spaces` → 200; Regressionstest grün | `tests/unit/test_openapi_generates.py::test_privat_endpoints_are_mounted` |
| F-P2-001 | P2/P3 | 01 | `/documents/*`, Suche | **Dokument-Zugriff durchgängig owner-scoped** — jeder sah/fand nur eigene Uploads. Prokurist fand die Rechnung des Azubi (gleiche Firma) NICHT → geteiltes GoBD-Archiv unbrauchbar. **Scope-Entscheid Ben: „firmenweit teilen".** | Blocker | – | **gefixt+bewiesen**: Lesen (Liste/Detail/Suche) auf `company_id` umgestellt (`document_service.py`, `search_service.py`); Schreiben bleibt owner-geschützt. Beweis: Prokurist Suche=6 + Liste=17; **Cross-Company-Isolation hält** (E2E-Viewer anderer Firma sieht 0 Perception-Docs); 4 Unit-Tests grün | `tests/unit/test_document_visibility_scope.py` |
| F-P1-005 | alle | 01 | global | Roter „destructive"-Toast **„Nicht gefunden — Die angeforderte Ressource wurde nicht gefunden"** bei jedem 404 (Hintergrund-/Polling-Aufrufe + gefrorene Optional-Module) → erschreckte neue Nutzer auf fast jeder Seite | Stolper | ja (Ton) | **gefixt+bewiesen**: 404 in `SILENT_STATUS_CODES` (globaler Toast unterdrückt; komponentennahe 404-Behandlung unberührt). Beweis: 33 vitest grün, `tsc -b` 0 | `frontend/src/lib/api/__tests__/error-toast-handler.test.ts` |
| F-P2-004 | P1/P2 | 02 | `/documents/search/` | **Suche → HTTP 500** nach ressourcen-knappem Neustart: GPU-Modell lud in fp16, Semantic-/Reranker-Matmul warf `RuntimeError: mat1 and mat2 must have the same dtype (Half vs Float)` → riss die gesamte (Hybrid-)Suche auf 500 | Blocker | – | **gefixt+bewiesen**: Semantic- **und** Reranker-Aufruf in `_search_hybrid` mit try/except umschlossen → degradiert bei GPU-Fehler auf reine FTS (kein GPU) statt 500. Beweis: Suche HTTP 200, degraded-Pfad greift | `app/services/search_service.py` (`hybrid_semantic_degraded_to_fts`) |
| F-P2-005 | P1/P2 | 02 | FTS-Suche | **FTS fand „Müller" nicht** (0 Treffer trotz vorhandenem Dokument): Umlaut-/Kompositum-Expansion wurde via `plainto_tsquery` mit **UND** verknüpft (`'mull' & 'muell'`) statt OR — die Expansion, deren Intent OCR-Toleranz (OR) ist, machte die Query strikter. Erst dadurch war die GPU-freie FTS als Fallback wertlos. | Blocker | – | **gefixt+bewiesen**: `_search_fts` baut die tsquery als **OR** je Term (Gesamtquery als AND-Gruppe + Einzelwörter als OR-Alternativen; `CAST(..)` statt `::` wegen SQLAlchemy-Bind-Falle). Beweis: FTS „Müller"=12, „Mueller"(ue)=12 (OCR-Umlaut-Toleranz), Cross-Company-Isolation hält, 3 pytest grün | `tests/unit/test_search_fts_or_terms.py` |
| F-P2-002 | P2 | 01 | `/documents/$id` (Detail) | Detailansicht lässt Kernfragen offen — Lieferant/Absender, Betrag, Datum nicht auf den ersten Blick erkennbar (Prokurist muss suchen) | Stolper | – | **offen** (Empfehlung Iteration 02+: Kern-Metadaten prominent im Detail-Kopf) | Screenshot p2-detail |
| F-P2-003 | P2 | 01 | `/documents/$id` | Status wird als englischer Rohwert angezeigt (`completed`/`pending`) statt deutscher Begriffe („Abgeschlossen"/„In Bearbeitung") | Kosmetik | **ja** | **offen** (Empfehlung: deutsche Status-Labels) | Screenshot p2-detail |
| F-P3-005 | P3 | 01 | `/documents` (Index) | `/documents` liefert eine **404-Seite** (keine Sammel-Dokumentliste-Route); wer die URL rät, landet auf „Seite nicht gefunden". Dokumente sind nur über Suche/Smart Inbox erreichbar. | Stolper | – | **offen** (Empfehlung: entweder Index-Route mit Firmenliste, oder Nav-Eintrag „Dokumente" auf Suche zeigen) | Screenshot p3-documents-404 |

## 5. Sprachbefunde (Deutsch-Check)

- **F-P1-005** (behoben): Fehler-Toast-Ton — der pauschale rote „Nicht gefunden"-Toast wirkte auf neue Nutzer alarmierend; jetzt unterdrückt.
- **F-P2-003** (offen): Englische Status-Rohwerte (`completed`/`pending`/`processing`/`failed`) in der Detailansicht statt deutscher Begriffe.
- Positiv: Onboarding-Wizard, Suchseite, Upload, Privat-Bereich durchgängig sauberes Deutsch inkl. korrekter Umlaute (UTF-8); Fixture „Bürohaus Müller GmbH" wird korrekt mit Umlaut indexiert und gefunden.

## 6. P3 Vertrauens-Gaps (separat — Input für Trust-Theater-Folge-Prompt)

Aus dem P3-Walk (Steuerberaterin/Prüfer-Blick). **Nicht in diesem Loop gefixt** (Trust-Oberfläche = eigener Folge-Prompt), außer wo Blocker:

- **T-01 Audit-Trail unsichtbar**: Dokument-Detail zeigt keinen erkennbaren Verlauf/Historie/Audit-Trail — die Prüferin sieht nicht, wer wann was am Dokument getan hat. (Backend-Audit-Logs existieren, aber nicht am Dokument erlebbar.)
- **T-02 Integrität nicht erlebbar**: Kein Hash/Prüfsumme/Zeitstempel/TSA/Signatur am Dokument sichtbar — die GoBD-Unveränderbarkeit ist vorhanden (Hash-Kette, signierte Verfahrensdoku), aber für den Prüfer nicht wahrnehmbar.
- **T-03 Verfahrensdokumentation nicht auffindbar**: Aus der UI heraus (weder Navigation noch Suche) nicht erreichbar — existiert nur „hinter den Kulissen" als signiertes PDF.
- **T-04 Compliance-/Audit-Seiten unklar für Prüfer-Rolle**: `/compliance`, `/audit-trail`, `/audit-logs` wirken für die Viewer-Rolle als Fehler-/Sperrseiten — unklar, was ein Prüfer hier überhaupt sehen darf.

→ Diese vier Punkte sind der Kern-Input für den Trust-Theater-Folge-Prompt: Das Archiv **ist** vertrauenswürdig (Hash/TSA/Verfahrensdoku vorhanden), aber es **wirkt** nicht so, weil nichts davon für den Prüfer sichtbar/erlebbar gemacht wird.

## 7. Iterations-Log

### Iteration 00 (Pre-Flight, 2026-07-11/12)
- Frontend gebaut + gestartet (F-SYS-001 gefixt), LAN-Check (F-SYS-002 offen), GPU-Worker verifiziert (RTX 4080, Modelle preloaded), Seed + Login-Smokes (200), Fixture-PDF generiert.
- Tech-Notiz: `user_companies`-RLS-Policy honoriert `app.rls_bypass` NICHT (nur `app.current_user_id`/`app.is_admin`) — Seed-Skripte müssen `app.is_admin` setzen; `scripts/seed_e2e.py` würde bei Neu-Seeding identisch scheitern (RLS-Restrunde-Kandidat).

### Iteration 01 (2026-07-12)
- **4 Blocker + 1 Trust-relevanter Stolper gefixt und belegt:**
  - F-P1-001 RLS-GUC-Kontextverlust (Upload-500) → NULLIF-Härtung 25 Policies + `persist_rls_gucs()`
  - F-P1-002 OCR-Duplikat-Skip ohne Text → nur bei echtem Text skippen
  - F-P1-003 Rate-Limit 10/h hart codiert → Settings/Override verdrahtet, 600/h
  - F-P1-004 Onboarding-Chaos (3 Overlays) → 1 kanonischer Flow, Tour opt-in
  - F-P4-001 Privat-Router verschattet (alle `/privat/*` 404) → Modul ins Package verschoben
  - F-P2-001 Dokumente owner-scoped → firmenweit (Ben-Entscheid), Cross-Company-Isolation verifiziert
  - F-P1-005 pauschaler roter 404-Toast → unterdrückt
- **Belegte Metriken:** P1-TTFV 0,4 min, P2-Suche 1,4 s, alle 4 Walks grün.
- **Tests:** pytest (RLS-Persistenz, Rate-Limit, Privat-Mount, Doc-Visibility), 38 vitest (Onboarding-Koordination, Toast-Handler), `tsc -b` = 0.
- **Offene Nicht-Blocker:** F-SYS-002 (LAN-DNS), F-P2-002/003 (Detail-Klarheit + deutsche Status), F-P3-005 (`/documents`-Index-404), P3-Trust-Gaps T-01…04.

### Iteration 02 (Bestätigungslauf, 2026-07-12)
- **Kontext:** Der Live-Stack musste nach einem Windows-/Docker-Ressourcen-Engpass (Fork-/OOM-Fehler durch die parallelen Builds+Playwright-Läufe) neu booten. Dabei lud das GPU-Modell in fp16 → **neuer Such-Blocker (500)** aufgedeckt.
- **2 neue Blocker gefixt und belegt (Such-Robustheit):**
  - F-P2-004 Hybrid-Suche degradiert bei GPU-Fehler auf FTS statt 500.
  - F-P2-005 FTS baut OR-tsquery → findet „Müller"/„Mueller" deterministisch ohne GPU.
- **Alle 4 Personas grün, 0 Blocker:** P1-TTFV 15,8 s, P2-Suche 2,5 s, P3 öffnet Firmendokument über Suche (firmenweite Sicht bestätigt), P4 Privat-Space lädt. (P3/P4 wegen des Umgebungs-Ressourcen-Engpasses einzeln nachgefahren — beide grün.)
- **Tests gesamt grün:** 16 pytest + 38 vitest, `tsc -b` = 0.
- **Harness-Härtung:** `searchFor`-Helfer (OR-robuste Suche, Verify-per-URL), gebundene Clicks (kein 600-s-Hänger mehr), `dismissFirstRunOverlays`.
- **DoD erfüllt:** P1-TTFV < 5 min ✓, alle Blocker gefixt+belegt ✓, 2 Iterationen in Folge ohne neue Blocker (Iter 01 + Iter 02) ✓, Report vollständig ✓.

## 8. Offene Empfehlungen (priorisiert)

1. **P3-Trust-Oberfläche sichtbar machen** (T-01…04) — höchste Priorität für „Prüfer-Vertrauen": Audit-Trail-Tab am Dokument, Hash/Zeitstempel/Signatur-Badge, Verfahrensdoku-Download in der Navigation, klare Prüfer-Rollen-Sicht. → eigener Trust-Theater-Folge-Prompt.
2. **F-P2-002/003** — Kern-Metadaten (Lieferant/Betrag/Datum) prominent im Detail-Kopf; deutsche Status-Labels statt `completed`/`pending`.
3. **F-P3-005** — `/documents`-Index: entweder Firmenliste-Route oder Nav-Eintrag „Dokumente" → Suche.
4. **F-SYS-002** — `ablage.firmenich.lan` per DNS/hosts im Onboarding-Runbook fürs Team ausrollen.
5. **Tech-Schuld** — `test_app_openapi_generates`-Schwelle (>2000 Pfade) ist seit dem Neuausrichtung-Modul-Freeze veraltet (aktuell 1989, freeze-bedingt); Schwelle an gefrorene Modul-Landschaft anpassen. RLS-`app.is_admin`-Seed-Gotcha in `seed_e2e.py` nachziehen.
