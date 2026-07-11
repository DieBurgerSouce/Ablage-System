# Perception-Audit 2026-07 — Die ersten 10 Minuten

**Kontext:** Am 01.08.2026 onboardet das Büro-Team (~6–10 User). Bei diesem Produkt ist Wahrnehmung = Produkt. Dieser Report protokolliert iterative Persona-Walks (Playwright, echter UI-Login, Stoppuhr) gegen den Live-Stack, gefundene Reibungen und deren belegte Fixes.

**Branch:** `feature/neuausrichtung-2026-07` (= Live-Code, Backend bind-mounted) · lokale Commits, kein Push.

## 1. Ziel & DONE-Kriterien

- [ ] P1-TTFV (Azubi: Upload → OCR → Wiederfinden) **< 5 min ohne Hilfe**
- [ ] Alle Blocker gefixt **und** belegt (Test grün + Vorher/Nachher-Screenshot)
- [ ] 2 Iterationen in Folge ohne neue Blocker
- [ ] Report vollständig

## 2. Setup & Umgebungs-Caveats

- Walks laufen gegen `http://localhost:80` (Frontend-nginx) + Backend `:8000`.
- Live-Env: `DEBUG=true`, `ENVIRONMENT=development`, Rate-Limit AN (Login 5/min/IP) — Walks halten ≥15 s Login-Abstand.
- Eigene Test-Identitäten: Firma **„Perception Audit GmbH"** (`DE888888888`) mit 4 synthetischen Personas (`azubi|prokurist|pruefer|familie@localhost.com`, kein Superuser) + Lieferant **„Bürohaus Müller GmbH"** (`DE888800001`). Seed: `scripts/seed_perception.py`. **Keine echten Accounts/Firmendaten; Odoo unberührt.**
- Fixture: `frontend/e2e/perception/fixtures/eingangsrechnung-buerohaus-mueller.pdf` (synthetische Eingangsrechnung, Umlaut-Test eingebaut).
- Harness: `frontend/playwright.perception.config.ts` + `frontend/e2e/perception/` (workers=1, echter UI-Login, Soft-Fail-Schritte, automatischer 4xx/5xx-/Console-Tap).

## 3. TTFV-Tabelle (Persona × Iteration)

| Iteration | P1 TTFV (Ziel <5 min) | P1 OCR-Dauer | P2 Suche→Treffer (Ziel <10 s) | Anmerkung |
|---|---|---|---|---|
| _(folgt)_ | | | | |

## 4. Findings-Register

| ID | Persona | Iter | Route | Beschreibung | Severity | Sprache? | Status | Beleg |
|---|---|---|---|---|---|---|---|---|
| F-SYS-001 | alle | 00 | `:80/:443` | Frontend-Container existierte nur als „Created" — nie gestartet; App für alle Nutzer unerreichbar | Blocker | – | **gefixt (Pre-Flight)**: `docker compose build frontend && up -d`; `/login` → HTTP 200 | curl-Beleg 200, Container healthy |
| F-SYS-002 | alle | 00 | `https://ablage.firmenich.lan` | LAN-Domain unerreichbar: kein hosts-/DNS-Eintrag auf diesem Rechner — Team am 01.08. bräuchte die „schöne" URL | Stolper | – | **offen** (Empfehlung: DNS/hosts-Rollout im Onboarding-Runbook) | curl 000, hosts ohne Eintrag |

## 5. Sprachbefunde (Deutsch-Check)

_(folgt aus den Walks)_

## 6. P3 Vertrauens-Gaps (separat — Input für Trust-Folge-Prompt)

_(folgt aus den P3-Walks; wird hier gesammelt, nicht gefixt außer Blocker)_

## 7. Iterations-Log

### Iteration 00 (Pre-Flight, 2026-07-11/12)
- Frontend gebaut + gestartet (F-SYS-001 gefixt), LAN-Check (F-SYS-002 offen), GPU-Worker verifiziert (RTX 4080, Modelle preloaded), Seed + 2 Login-Smokes (200), Fixture-PDF generiert.
- Tech-Notiz (kein Perception-Finding): `user_companies`-RLS-Policy honoriert `app.rls_bypass` NICHT (nur `app.current_user_id`/`app.is_admin`) — Seed-Skripte müssen `app.is_admin` setzen; `scripts/seed_e2e.py` würde bei Neu-Seeding identisch scheitern. Kandidat für RLS-Restrunde-Nachtrag.

## 8. Offene Empfehlungen (priorisiert)

_(wird fortgeschrieben)_
