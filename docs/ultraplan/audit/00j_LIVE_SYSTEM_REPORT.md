# 00j — Live System Report (Playwright Walk)

**Datum:** 2026-05-03 23:31 lokal
**Methode:** Playwright MCP (Chrome) — http://localhost (Port 80)
**Browser-Viewport:** Desktop 1280x800 + Mobile 375x812

---

## 1. System-Status zum Walk-Zeitpunkt

| Komponente | Port | Status | HTTP |
|-----------|------|--------|------|
| Frontend (nginx) | 80 | LÄUFT | 200 |
| Backend (FastAPI) | 8000 | **OFFLINE** | 000 |
| Backend via nginx | 80/api/* | **502 Bad Gateway** | 502 |
| Vite Dev Server (anderes Projekt) | 5173 | läuft (OpenClaw, nicht Ablage) | 200 |

**Kritische Beobachtung:** Das System ist nur **partial** verfügbar. Backend-API antwortet nicht, alle datengesteuerten Routes scheitern. Auth-protected Workflows (Login → Upload → OCR → Buchen) sind für diesen Walk nicht testbar.

**Implikation für Pilot:** Wenn Ben am Pilot-Tag das System hochfährt und Backend-Container nicht startet, sieht der Prokurist auf jeder Detail-Seite nur "Server nicht erreichbar"-Toasts. Daher ist die **Frontend-Resilienz** bei Backend-Ausfall ein Pilot-relevantes Feature.

---

## 2. Was getestet wurde (4 Pages, 2 Viewports)

| Pfad | Desktop | Mobile (375px) | Befund |
|------|---------|----------------|--------|
| `/` (root) | Redirect → `/login` | — | Auth-Guard funktioniert |
| `/login` | OK, polished | OK, gut lesbar | Sauberes Layout |
| `/forgot-password` | OK, polished | OK | **FAANG-Blocker behoben** |
| `/this-route-does-not-exist-12345` | Redirect → `/login` | — | **Kein expliziter 404** für unauthenticated User; siehe §6.1 |

Screenshots gespeichert in `.playwright-mcp/`:
- `live-walk-01-login.png` (Desktop Login)
- `live-walk-02-forgot-password.png` (Desktop Forgot-Password)
- `live-walk-03-mobile-login.png` (Mobile Forgot-Password)

---

## 3. Was funktioniert (Stärken)

### 3.1 Graceful Backend-Down-Handling — **Plus gegen FAANG-Audit2**

FAANG-Audit2 sagte: *"Dashboard shows skeleton forever if 0 docs"* (Empty-State-Problem).

Live-Reality (auf `/login`):
- API-Call zu `GET /api/v1/documents/?per_page=4&sort_by=created_at&sort_order=desc` schlägt mit 502 fehl
- Frontend zeigt **keinen unendlichen Skeleton-Loader**
- Stattdessen: deutscher Toast in der Notifications-Region: *"Server nicht erreichbar — Der Server ist vorübergehend nicht erreichbar."*

Diese Toast-Komponente ist erkennbar wiederverwendbar (Sonner-Pattern). Sie scheint auf API-Call-Failures zu reagieren — vermutlich ein globaler Query-Error-Handler in TanStack Query. **Code-Suche-Empfehlung:** `frontend/src/lib/api/` und `frontend/src/app/__root.tsx` für die globale Error-Toast-Logik.

→ **Befund:** Mindestens auf der Login-Page existiert eine sinnvolle Backend-Down-Behandlung.

### 3.2 Forgot-Password-Page existiert + ist polished

FAANG-Audit2 hatte Password-Reset nicht explizit als Pilot-Blocker, aber Bens System-Reminder schon. Live: Page existiert, ist deutsch, hat Heading, Beschreibung, Input mit Placeholder `name@firma.de`, Primary-CTA "Link senden", Tertiär-Link "Zuruck zur Anmeldung".

### 3.3 Konsistente Visuelle Identität

- Dunkles Theme durchgehend
- Custom-Schriftart für "Ablage System"-Logo + "Passwort vergessen?"-Heading (sehr individuelle Optik, NICHT generisch)
- Hellblaue Primary-CTA-Buttons
- Saubere Card-Layout mit Shadow-Effekt
- Mobile-Viewport bricht NICHT (Layout passt sich an, Card wird vertikal länger)

→ FAANG-Audit2's Anti-Pattern *"generic AI aesthetics"* trifft hier NICHT zu. Ben hat eigenes Design-System aufgebaut.

### 3.4 Auth-Guard auf nicht-existenten Routes

Navigate zu `/this-route-does-not-exist-12345` → redirect auf `/login`. Heißt: TanStack-Router Auth-Guard fängt **alles** ab, inkl. invalid Routes. Aus Sicherheits-Sicht gut (kein Information-Leak), aus UX-Sicht halb gut (nicht-eingeloggter User sieht zumindest etwas).

---

## 4. Was nicht funktioniert / Lücken

### 4.1 Umlaut-Bug auf Forgot-Password-Page (KRITISCH gegen Brand)

Frontend-String: **`"Zuruck zur Anmeldung"`** (ohne ü-Umlaut!)

Quelle: Snapshot zeigt zwei Belege:
```
- link "Zuruck zur Anmeldung" [ref=e16] [cursor=pointer]:
  - text: Zuruck zur Anmeldung
```

**Implikation:** 
- CLAUDE.md Regel #2: *"ALL user-facing text MUST be German. UTF-8 for umlauts."*
- README.md Performance-Tabelle: *"Accuracy (German): >95% (97% actual)"*
- Bens Marketing: 100% Umlaut-Accuracy ist Verkaufs-Argument

Ein direkt sichtbarer Umlaut-Verstoß auf der **drittwichtigsten Page** (nach Login + Dashboard) ist eine handfeste Blamage. **Effort:** 5 Minuten Fix in Frontend-String, dann i18n-Audit über alle Routes empfehlen.

→ **Code-Suche-Empfehlung:** `grep -rn "Zuruck\|zuruck\|Ueber\|ueber" frontend/src --include="*.tsx" --include="*.ts"` → wahrscheinlich weitere Treffer.

### 4.2 Backend-Container offline

`docker ps` zeigte nur MCP-Container (von Claude-Flow), KEINE Ablage-System-Container. Heißt: Das Frontend läuft (nginx serviert statische Files), aber Backend-FastAPI + PostgreSQL + Redis + MinIO + OCR-Workers sind nicht hochgefahren.

**Implikation für Mission:** 
- Pilot-Workflow (Eingangsrechnung scannen → OCR → Buchen → Archivieren) wurde NICHT live getestet
- Login-Funktionalität ungetestet
- 2FA-Flow ungetestet
- Performance-Versprechen (<2 Min pro Rechnung) nicht verifizierbar

→ Das ist eine **substantielle Mission-Lücke**. Ben sollte einen End-to-End Live-Walk mit hochgefahrenem System nachholen, bevor er Pilot startet.

### 4.3 Pre-Fetch ohne Auth scheitert sichtbar

Login-Page macht bereits VOR Login einen API-Call zu `GET /api/v1/documents/?per_page=4...`. Das deutet auf ein TanStack-Query-Pattern hin, das auf jeder Page initial fetched, ohne Auth-Status zu prüfen.

**2 Probleme:**
1. Beim Backend-Down sieht jeder Login-Versuch als ersten Effekt einen "Server nicht erreichbar"-Toast — selbst wenn Login danach klappen würde, ist der **erste UX-Eindruck negativ**.
2. Beim Backend-Up wirft das einen 401 von einer geschützten Route — wahrscheinlich versteckt durch Toast-Suppression, aber Network-Tab zeigt es. Bei einem Pentest könnte das als Information-Leak interpretiert werden.

**Code-Suche-Empfehlung:** `frontend/src/app/routes/login.tsx` + alles was unter `__root.tsx` an Pre-Fetches passiert.

### 4.4 Kein echter 404-Page (FAANG-Blocker NICHT vollständig behoben)

Auf `/this-route-does-not-exist-12345` redirected unauthenticated User auf `/login`. Das verschleiert den 404-Fall. Für **eingeloggte** User ist das Verhalten unklar (Backend offline, daher kein Login-Test möglich) — möglicherweise weiterhin der FAANG-Blocker.

**Code-Suche:** `find frontend/src/app/routes -name "\$*.tsx"` → `$.tsx` (Catch-all) + Inhalt prüfen. Falls fehlt → P0-Pilot-Blocker.

### 4.5 5173-Port-Konflikt mit anderem Projekt

Port 5173 (Vite-Dev-Server) wird vom OpenClaw-Projekt belegt. Wenn Ben die Frontend-Dev-Umgebung starten will, gibt es Konflikt. Fix: Port-Konfiguration in `frontend/vite.config.ts` prüfen.

---

## 5. Console-Errors (Top 5)

```
[ERROR] 502 Bad Gateway @ /api/v1/documents/?per_page=4&sort_by=created_at&sort_order=desc (4×)
[ERROR] 500 Internal Server Error @ http://localhost:5173/src/ui/*.ts (8× - aber das ist OpenClaw, nicht Ablage)
```

**Befund:** Die 502er sind erwartete Folgen des offline Backends. Die 500er sind aus dem fremden OpenClaw-Projekt und können ignoriert werden.

**Was NICHT in Console steht:** Keine JavaScript-Errors, keine "Cannot read property of undefined", keine React-Hydration-Errors. Frontend-Code selbst läuft sauber durch.

---

## 6. Bens FAANG-Audit2-Pilot-Blocker — Live-Verifikation

| FAANG-Blocker | Live-Status | Beweis |
|---------------|-------------|--------|
| 404-Page | TEILWEISE | Auth-Redirect statt expliziter 404; für eingeloggte User nicht testbar |
| Empty States | BEHOBEN (auf Login-Page) | Toast statt Skeleton-Endloss bei Backend-Down |
| Error-Monitoring | UNGEKLÄRT | Kein Sentry/LogRocket Init in DOM sichtbar; Code-Inspektion `frontend/src/main.tsx` nötig |
| User-Onboarding | UNTESTBAR | Kein Login → keine First-Run-Sicht |
| Frontend-Tests sparse | UNGEKLÄRT | Phase 1.6 Test-Audit klärt |
| 2FA-Frontend | UNTESTBAR | Backend offline |
| Password-Reset-UI | BEHOBEN | Page existiert + polished |

→ **Verbleibende Pilot-Blocker:** 404 für eingeloggte User, Error-Monitoring (codereview), Onboarding, 2FA — alle erst nach Backend-Hochfahren testbar.

---

## 7. Pilot-Versprechen-Tests (NICHT durchführbar)

Ben verspricht im ULTRAPLAN_MASTER_PROMPT:
- Eingangsrechnung in <2 Min verarbeiten
- Jedes Dokument in <10 Sekunden findbar
- DATEV-Export in <15 Min

Alle drei sind durch das offline Backend untestbar. **Empfehlung:** Vor Pilot ein Live-Walk-Wiederholung mit hochgefahrenem System + automatisierte Performance-Tests in `tests/e2e/` mit konkreten SLA-Asserts.

---

## 8. Top-3 Stärken (Live)

1. **Visual Polish + Brand-Identity:** Login + Forgot-Password sehen NICHT nach Generic-AI-UI aus, sondern nach durchdachtem Design.
2. **Backend-Down-Resilience:** Frontend handhabt 502er graceful mit deutschem Toast — beweist, dass globaler Error-Handler existiert und durchläuft.
3. **Mobile-First-Tauglich:** Auth-Pages funktionieren auf 375px ohne Layout-Bruch, ohne horizontales Scrollen.

## 9. Top-5 Lücken (Live)

1. **Umlaut-Bug "Zuruck zur Anmeldung"** — direkter Brand-Verstoß, 5-Min-Fix, aber wahrscheinlich Indikator für viele weitere Stellen
2. **Backend-Container nicht hochgefahren** — Mission-Walk konnte Pilot-Workflow nicht testen, das ist signifikant
3. **404-Page verschleiert durch Auth-Redirect** — für eingeloggte User wahrscheinlich weiterhin Blocker
4. **Pre-Fetch ohne Auth wirft 502 sichtbar** — schlechter Erstkontakt bei Backend-Down
5. **Performance-Versprechen ungetestet** — <2 Min, <10 Sek, <15 Min sind Marketing, kein Daten-Punkt

## 10. Note für "Live System Pilot-Readiness"

**Note: 4/10**

Begründung: Was sichtbar war (Login, Forgot-Password, Mobile-Layout, Backend-Down-Toast), war hochwertig. Was nicht sichtbar war (Pilot-Workflow, 2FA, Onboarding, eingeloggter 404, Performance-SLAs), bildet die Mehrheit der Pilot-Bewertung. Eine **echte Pilot-Readiness-Bewertung erfordert einen erneuten Walk mit hochgefahrenem Backend** — ohne das ist die Note konservativ.

Bei hochgefahrenem System würde die Note bei gleicher Frontend-Qualität wahrscheinlich 6-7/10 erreichen, sofern Pilot-Workflow durchläuft.

---

## 11. Nächste Schritte (für Ben)

1. **SOFORT (15 Min):** `docker-compose up -d` ausführen, alle Container hochfahren, Health-Checks prüfen, dann Live-Walk wiederholen.
2. **WÄHREND PILOT-VORBEREITUNG (1-2 Wochen):**
   - Umlaut-Audit über gesamtes Frontend (`grep` nach typischen Verstößen)
   - Catch-all `$.tsx` Route prüfen/erstellen für eingeloggte 404-Erfahrung
   - Sentry/LogRocket-Wiring in `main.tsx` sicherstellen
   - Pilot-Workflow E2E-Test in `tests/e2e/` mit Playwright + SLA-Asserts (<2 Min, etc.)
3. **VOR PILOT:** Volle Live-Walk-Wiederholung mit echtem Test-Account am Familienbetrieb-System.

---

## 12. Mission-Caveats

- Live-Walk konnte nur **Frontend-Layer** und **Frontend-Resilience** verifizieren
- Backend-Behavior, OCR-Pipeline, DB-Operations, Multi-Tenant-Isolation: **UNGETESTET**
- Pilot-Versprechen-Performance: **UNGETESTET**
- Workflow-End-to-End: **UNGETESTET**
- Phase 1.6 (Test-Audit) und Phase 1.7 (Security-Audit) liefern statische Code-Indikatoren als Proxy
- Phase 2 Perspektiven (besonders 01 Prokurist + 02 Azubi) müssen mit dieser Limitation umgehen

---

**Status:** Live-Walk abgeschlossen mit dokumentierten Limitationen. Backend muss vor Pilot-Start zwingend hochgefahren werden.
