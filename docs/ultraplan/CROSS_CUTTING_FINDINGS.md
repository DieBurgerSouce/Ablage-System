# Cross-Cutting Findings

**Methodik:** Findings die mehrere Perspektiven unabhängig identifiziert haben (höchste Priorität), Widersprüche zwischen Perspektiven, sowie eigene Synthese-Lücken die keine einzelne Perspektive sah.

**Datenbasis:** 10 Audit-Reports + 11 Perspektiven (Stand: 2026-05-03 23:50).

---

## 1. Cross-Cutting Findings (≥3 Perspektiven)

### 1.1 Multi-Tenancy ist Begriffschaos + faktische Lücke
**Identifiziert von:** Backend-Audit (00b §10), DB-Schema-Audit (00c §3), Security-Audit (00h §A01), Backend-Engineer (04 §Top-5 Lücken), Security-Architekt (06 §A01)

**Befund:** Das System nutzt `company_id` (616 Treffer in 82 von 95 Files) als faktischen Tenant-Diskriminator, aber Code/Doku spricht parallel von `tenant_id` (das im Privat-Modul für **Mieter** steht, nicht Mandanten). Folgen:
- 13 DB-Tables ohne Tenant-Spalte (kritisch: `Invoice`, `ChatToolAction`, `DashboardShare`)
- 200+ Services filtern `company_id` manuell ohne zentralen Authorization-Decorator
- Eine vergessene Stelle = Cross-Tenant-Leak
- RLS aktiv (Migration 025) als Defense-in-Depth, aber nur wenn `app.current_company_id` korrekt gesetzt
- Pilot mit 1 Kunde on-prem: machbar. Multi-Tenant-SaaS: 2-4 Monate Hardening

**Severity:** 5/5 — strukturelles Risiko, Datenleck-Potential
**Effort to fix:** Hoch (3-4 Monate für volle Multi-Tenancy)
**Pilot-Blocker (1 Kunde on-prem):** NEIN
**Markt-Blocker (mehrere Kunden eine Instanz):** JA

### 1.2 God-Objects als systemisches Anti-Pattern
**Identifiziert von:** Backend-Audit (00b §2), API-Audit (00d §1), Backend-Engineer (04 §Top-5 Lücken)

**Befund:** Mehrere extreme File-Größen die nicht reviewbar/testbar sind:
- `app/services/structured_extraction_service.py` — 118 KB
- `app/services/privat/tax_optimization_service.py` — 99 KB
- `app/services/streckengeschaeft/__init__.py` — 88 KB **Logik im `__init__`-File!**
- `app/services/quick_classification_service.py` — 79 KB
- `app/api/v1/orchestration.py` — 554 `@router.*`-Decorations / 148 KB

**Severity:** 4/5 — Wartbarkeit/Bug-Fix-Latenz unhaltbar
**Effort:** Refactor 2-4 Wochen pro God-Object
**Pilot-Blocker:** Nein direkt, aber jede Änderung in diesen Files = Risiko
**Skalierungs-Blocker:** JA — Code-Wachstum 4x in 5 Monaten zeigt: ohne Refactor explodieren diese weiter

### 1.3 Frontend-Polish ist da, Frontend-Tests sind dünn
**Identifiziert von:** Frontend-Audit (00e), Frontend-Engineer (03), Test-Audit (00g), Live-Walk (00j)

**Befund:** 5/6 FAANG-Pilot-Blocker (404, Empty-States, Onboarding, 2FA, Password-Reset) sind behoben. ABER:
- 39 Component-Tests bei 127 Features — Kerntmodule (Risk-Scoring, Spotlight, Onboarding-Wizard, Dashboard, OCR-Review) haben 0 Tests
- 93 axe-core-Violations (Dec 2025), keine Folge-Audits
- Code-Splitting nur in 22 von 299 Routes (`lazy()`)
- 4 parallele Onboarding-Systeme (WelcomeModal, CompanySetupWizard, OnboardingWizard, ProductTour) — keine Route, alle in localStorage

**Severity:** 4/5 — Pilot funktioniert, aber Bug-Triage wird Engpass
**Effort:** Test-Coverage 4-6 Wochen, Onboarding-Konsolidierung 1 Woche
**Pilot-Blocker:** Nein (für 1 Familienbetrieb-Pilot)
**Markt-Blocker:** JA (a11y CLAUDE.md WCAG-2.1-AA Behauptung nicht haltbar)

### 1.4 Solo-Ops-Notification ist tot
**Identifiziert von:** Infrastructure-Audit (00f), DevOps-Perspektive (05), Live-Walk (00j)

**Befund:** Die Live-Walk-Beweisführung ist hart: zum Audit-Zeitpunkt war Backend offline, niemand (auch nicht Ben) wusste es. Konkret:
- Slack-Webhook in `alertmanager.yml` auskommentiert
- SMTP zeigt auf `localhost:587` (kein Mailserver)
- PagerDuty/OpsGenie/Teams-Templates vorhanden, nicht aktiviert
- Sentry im Compose, aber `SENTRY_DSN` optional
- Push-Notifications: nicht verifiziert

**DevOps-Perspektive Note: 5.5/10** — primär wegen dieser Lücke.

**Severity:** 5/5 — Solo-Ops-K.O.-Kriterium
**Effort:** 30 Min für Slack-Webhook, 2-4h für Push-Notification-Setup
**Pilot-Blocker:** JA — bei Crash am Pilotkundentag = Reputations-Schaden

### 1.5 Silent-Catches an Compliance-/Audit-/Import-Stellen
**Identifiziert von:** Backend-Audit (00b §6), Backend-Engineer (04 §Top-5 Lücken), Compliance-Perspektive (07)

**Befund:** 56 `except Exception: pass` im Service-Layer, präzise an den falschen Stellen:
- `access_analytics_service.py:840, 861` (Audit silent)
- `email_import_service.py:798, 822, 1111` (Imports silent)
- `folder_import_service.py:839, 881, 1078` (Imports silent)
- `fraud_detection_service.py:683` (Fraud silent)
- `search_service.py:662, 672` (Index-Update silent)

**Implikation:** Pilot bekommt Datenverlust ohne Telemetrie. Lexware-Import-Bug wird nicht gemeldet, GoBD-AuditLog-Schreibfehler werden geschluckt. Konflikt mit GoBD-Anspruch.

**Severity:** 4/5
**Effort:** 1-2 Tage systematischer Sweep mit `logger.exception` + targeted-catch
**Pilot-Blocker:** TEILWEISE (Daten könnten verloren gehen ohne Sichtbarkeit)

### 1.6 Test-Coverage strukturell dünn (besonders E2E)
**Identifiziert von:** Test-Audit (00g), Frontend-Audit (00e), Frontend-Engineer (03)

**Befund:** 
- 678 Unit-Tests, 53 Integration, 53 "E2E" — aber `tests/e2e/` sind verkappte Integration-Tests mit Mocks, kein Playwright/`*.spec.ts`
- 39 Frontend-Component-Tests bei 127 Features
- Pilot-Workflow (Eingangsrechnung → OCR → Buchen → Archivieren) nicht E2E-getestet
- Keine SLA-Asserts (<2 Min, <10 Sek, <15 Min) automatisiert

**Severity:** 4/5
**Effort:** 2-3 Wochen für minimal-viablen Playwright-E2E
**Pilot-Blocker:** TEILWEISE (Pilot-Versprechen nicht messbar verifiziert)

### 1.7 Drei Security-Pilot-Blocker (alle adressierbar in 2 Tagen)
**Identifiziert von:** Security-Audit (00h), Security-Perspektive (06)

**Befund:** Drei konkrete Pilot-Blocker mit definitivem Fix:
1. **`python-jose==3.3.0`** mit CVE-2024-33664 — Migration zu PyJWT (bereits Dependency)
2. **JWT in Response-Body statt httpOnly-Cookie** — `set_cookie` im Login-Endpoint
3. **CSP enthält `unsafe-inline`** — Nonce-/Hash-basiert + Inline-Scripts ausbauen

Plus: Login-Rate-Limit `10/minute` zu schwach (BSI-Empfehlung 5/15min + Lockout).

**Severity:** 5/5 — Junior-Pentester findet das in <1 Tag
**Effort:** 2 Tage für Top-3 + 1 Woche für Rate-Limit + CSP-Hardening
**Pilot-Blocker:** JA bei externem Pentest, Nein für familieninternen Pilot

### 1.8 Compliance-HARD-Blocker für DATEV-Zertifizierung
**Identifiziert von:** Compliance-Audit (00i), Compliance-Perspektive (07)

**Befund:** GoBD/Hash-Chain-Implementation ist exzellent, aber für **DATEV-Zertifizierung** + **B2G-XRechnungen** fehlt:
- **Verfahrensdokumentation als signiertes Artefakt** (BMF-Schreiben 2019 Rz. 151-155, Tag-1-Anforderung beim Außenprüfer)
- **KOSIT-Validator** für B2G-XRechnungen (Bundesbehörden lehnen ohne Konformitätsstempel ab)
- **Art. 30 DSGVO Verzeichnis** ist Modell ohne Daten (Bußgeld bis 10 Mio EUR)
- **DATEV-Belegbilder-Upload** nicht produktiv, Schnittstellen-Zertifizierung nicht beantragt
- **TSE/KassenSichV** Anwendbarkeit ungeklärt (vor Pilot mit Steuerberater + Anwalt klären, sonst §379 AO Bußgeld)

**Compliance-Perspektive Note: 6.5/10**

**Severity:** 5/5 für DATEV-Zertifizierung, 3/5 für Familienbetrieb-Pilot
**Effort:** 4-6 Wochen Verfahrensdoku, 2 Wochen KOSIT, 1-2 Wochen Art. 30, 6-12 Wochen DATEV-Zertifizierung
**Pilot-Blocker:** Nein für Familie, JA für DATEV-zertifizierte Markt-Position

### 1.9 ML/Data-Reality lag deutlich unter Plan-Sprache
**Identifiziert von:** ML-Audit (00k), Data-Scientist-Perspektive (08), Frontend-Engineer (03)

**Befund:** OCR-Backend-Pluralität ist überdurchschnittlich (13+ Agents), RAG-Stack ist tief integriert (~85% Plan-Realisierung). Aber:
- **Keine veröffentlichten Accuracy-Zahlen** (CER/WER pro Backend, Umlaut-Recall, NDCG, Recall@k)
- **CLAUDE.md "100% Umlaut-Accuracy"** code-strukturell aber nicht numerisch belegt
- **Self-Learning-Loop nicht zeitgesteuert** — nur reactive bei OCR-Tasks, nicht via Celery-Beat
- **Drift-Reports leer** trotz konfigurierter Beat-Schedule
- **Trainings-Daten unannotiert** (10× UP*-Dirs mit ~10k Roh-PDFs, 0 JSON-Annotations)
- **Translation-Plan obsolet** (PlanVektorPipeline.md fordert MarianMT, Code hat Argos/LibreTranslate/DeepL)

**Severity:** 3/5 für Pilot (Confidence-Thresholds + Review-Queue tragen den Pilot-Modus), 5/5 für Markt-Versprechen
**Effort:** 4 Wochen für Accuracy-Messreihe, 2 Wochen für Self-Learning-Beat, 2-4 Wochen Annotation-Pipeline
**Pilot-Blocker:** Nein. **Markt-Blocker:** JA — ohne Zahlen keine Verkaufs-Aussagen

### 1.10 Onboarding-Chaos (4 parallele Systeme)
**Identifiziert von:** Azubi (02), Frontend-Audit (00e), Product-Manager (09 — sobald fertig)

**Befund:** Frontend hat **vier parallele Onboarding-Systeme**:
1. `WelcomeModal.tsx` (4 Schritte)
2. `CompanySetupWizard.tsx` (4 Steps)
3. `features/onboarding/components/OnboardingWizard.tsx` (5 Steps)
4. `features/product-tour/` (TourProvider/TourSpotlight/TourTooltip + GettingStartedChecklist)

Plus: Tooltip/Help-System (`ContextualTooltip`, `HelpTooltip`, `FeatureHint`, `HelpPanel`, `HelpSearch`) ist gebaut aber **wird nirgends in Routes importiert**.

**Severity:** 3/5
**Effort:** 1 Woche für Konsolidierung + 1 Woche Tooltip-Integration in Top-20-Routes
**Pilot-Blocker:** Nein, aber Azubi-UX leidet

---

## 2. Widersprüche zwischen Perspektiven

### 2.1 ANALYSIS_*.md (Dez 2025) sagt 92-95% Production-Ready vs. Audit-Schnitt 6-7/10

**Auflösung:** Beide haben Recht aus ihrer Definition:
- ANALYSIS misst **Feature-Vollständigkeit** auf Backend-Ebene → 92-95%
- Audits messen **Pilot-Readiness** mit Frontend-Polish, Tests, Solo-Ops, Security-Pilot-Blocker → 6-7/10

**Realität:** System ist Backend-Enterprise + Frontend-Beta + Ops-Solo-fragil. Bens FAANG-Audit2-Lese hatte das schon erkannt.

### 2.2 ANALYSIS sagt "Multi-Tenant" als Stärke vs. Backend-Audit sagt "keine echte Multi-Tenancy"

**Auflösung:** ANALYSIS sah `company_id`-Pattern als ausreichend. Backend-Audit unterscheidet zwischen "Single-Customer-on-prem" (funktioniert) und "Multi-Tenant-SaaS auf einer Instanz" (fehlt). Beides ist konsistent — die Frage ist die Deployment-Strategie.

### 2.3 Frontend-Audit (8/10) vs. Live-Walk (4/10)

**Auflösung:** Frontend-Audit prüft Code-Qualität (Type-Safety, Komponenten, Toolchain) → 8/10. Live-Walk prüft das laufende System mit offline Backend → konnte nur 30% testen → 4/10. Bei hochgefahrenem System würde Live-Walk auf 6-7/10 steigen.

### 2.4 Compliance-Audit "GoBD exzellent" vs. Compliance-Perspektive "Verfahrensdoku HARD BLOCKER"

**Auflösung:** GoBD-DB-Layer (CashEntry-Trigger, Hash-Chain) ist Bank-Niveau. Aber **Verfahrensdokumentation** ist organisationelle Pflicht (BMF-Schreiben 2019 Rz. 151-155), nicht Code. Dass das System eine Verfahrens-Doku-Generator-Klasse hat heißt nicht, dass Ben ein signiertes, archiviertes PDF hat. Beides richtig — Code-Substrat exzellent, Compliance-Artefakt fehlt.

---

## 3. Neue Findings (nicht in einzelner Perspektive)

### 3.1 Code-Wachstum 4x in 5 Monaten (Tempo-Risiko)

ANALYSIS Stand Dez 2025: 210 Services, 93 Routes, 70 Migrations.
Aktuell Mai 2026: 797 Services (+280%), 299 Routes (+221%), 227 Migrations (+224%).

Das ist eine **Skalierungsbeschleunigung**, nicht stabile Entwicklung. Das Code-Wachstum hat:
- 4 God-Objects produziert (>60 KB)
- 56 Silent-Catches eingebaut
- 4 parallele Onboarding-Systeme entstehen lassen
- Multi-Tenant-Begriffsverwirrung manifestiert (`company_id` vs `tenant_id`)
- Test-Coverage von 80% (ANALYSIS) auf ~30% (Audit) gefallen

**Diagnose:** Ben + Claude Code generieren schneller als refactored wird. Das ist ein **Solo-Founder-typisches Anti-Pattern**: Feature-Velocity hoch, technische Schulden bauen sich schneller auf als sie abbezahlt werden.

**Empfehlung:** Sprint 0 sollte ein expliziter "Konsolidierungs-Sprint" sein — keine neuen Features, nur God-Object-Splits, Onboarding-Konsolidierung, Silent-Catch-Sweep.

### 3.2 Code-Doku-Drift in mehreren Domänen

Mehrere Stellen wo Doku/Code auseinanderlaufen:
- `api/v1/README.md:13` sagt "JWT in httpOnly Cookie" → Code: JWT in Response-Body
- `CLAUDE.md` sagt "WCAG 2.1 AA" → axe-core: 93 Violations
- `CLAUDE.md` sagt "100% Umlaut-Accuracy" → Live-Walk: "Zuruck" auf Forgot-Password-Page
- `CLAUDE.md` sagt "Multi-Tenancy" → Code: Single-Tenant-pro-Instanz
- `PlanVektorPipeline.md` fordert MarianMT → Code: Argos/LibreTranslate
- `ANALYSIS_*.md` sagt 70 Migrations → Code: 227

**Diagnose:** Markdown-Pläne sind 5 Monate alt und werden nicht aktualisiert. Erstgespräche mit Pilot-Kunden anhand der Pläne werden enttäuscht.

**Empfehlung:** Vor Pilot ein Marketing-Doc-Audit. Pläne archivieren oder aktualisieren.

### 3.3 Tooltip-/Help-System ist gebaut aber nicht aktiviert

Frontend hat ein vollständiges In-App-Help-System (`ContextualTooltip`, `HelpTooltip`, `FeatureHint`, `HelpPanel`, `HelpSearch`, `HelpProvider`, `VideoPlayer`) — aber wird in **0 von 299 Routes** genutzt.

**Diagnose:** Klassischer "haben wir gebaut, vergessen zu integrieren". Azubi-UX leidet konkret.

**Empfehlung:** 1 Woche Top-20-Routes mit Help-Integration ausstatten.

### 3.4 RAG-Stack hat ALLE Bausteine + niemand nutzt sie produktiv

ML-Audit zeigt: pgvector + Qdrant dual-active, Embedding-Service, Reranker, Customer-Cards, Tool-Registry, Action-Dispatcher, Excel/Word-Reportgenerierung, WebSocket-Chat. Dazu in Codebase: Qwen3-Stack-Hooks.

Aber: keine ARTIFAKTE, keine A/B-Test-Reports neuer als 2026-01-18 (3.5 Monate alt). 121k-Zeilen-`training_samples.json` isoliert.

**Diagnose:** Ben hat Sehnsucht nach KI-Wow-Effekt, hat den Stack gebaut, kommt aber operativ nicht nach. Klassisches Solo-Founder-Pattern.

**Empfehlung:** Pilot-Kommunikation **NICHT** über RAG/AI-Features führen. Stattdessen über GoBD/On-Premises/OCR-Pluralität (was REAL produktionsreif ist).

### 3.5 Bus-Faktor 1 als Top-Risiko

Ben ist Solo. Die Codebase ist 797 Services groß. Wenn Ben 6 Wochen krank wird:
- Niemand kann God-Objects warten (118 KB Files sind nicht Pair-Programming-tauglich)
- Niemand weiß, wo die 4 parallelen Onboarding-Systeme verschaltet sind
- Pilot-Kunde bekommt keinen Support
- DATEV-Zertifizierungs-Antrag stoppt

**Empfehlung:** Vor Pilot eine "Kann-jemand-anderes-das-übernehmen"-Doku — selbst wenn Ben sie selbst schreibt, beim Lesen wird klar, wo die Wissens-Inseln sind.

---

## 4. Konvergente Themen (Was wirklich zählt)

Die Synthese zeigt **drei Cluster**, die alle Perspektiven in unterschiedlicher Sprache wiederholen:

### Cluster A: "Solo-Founder-Hardening" (Pilot-Blocker)
- Notification-Pipe (DevOps 1.4)
- 3 Security-Pilot-Blocker (1.7)
- Silent-Catches an Compliance-Stellen (1.5)

→ **2-Wochen-Hardening-Sprint** vor Pilot.

### Cluster B: "Markt-Vorbereitung" (Markt-Blocker)
- Multi-Tenancy-Decision (1.1)
- DATEV-Zertifizierungs-Pfad + Verfahrensdokumentation (1.8)
- ML-Accuracy-Messreihe (1.9)
- Test-Coverage E2E (1.6)

→ **3-6-Monats-Plan** zwischen Pilot-Ende und Markt-Start.

### Cluster C: "Skalierungs-Vorbereitung" (Bus-Faktor + Code-Health)
- God-Objects (1.2)
- Code-Doku-Drift (3.2)
- Onboarding-Konsolidierung (1.10)
- Bus-Faktor (3.5)

→ **6-12-Monats-Plan** vor Hire #2.

---

## 5. Was diese Synthese NICHT in den ANALYSIS_*.md fand

Die existierenden ANALYSIS-Reports waren Stand Dez 2025. Diese Mission identifiziert mindestens 5 NEUE Findings:

1. **Code-Wachstum 4x in 5 Monaten** als systemischer Indikator (3.1) — ANALYSIS hatte nur statischen Snapshot
2. **Live-Walk-Befund: Backend offline ohne Notification** (1.4) — ANALYSIS prüfte nur Code, nicht Runtime
3. **Onboarding-Chaos (4 parallele Systeme)** (1.10) — wurde von keiner ANALYSIS adressiert
4. **Code-Doku-Drift** (3.2) — neue Disziplin (Doku als eigener Audit-Pfad)
5. **Multi-Tenancy-Begriffsverwirrung** (1.1) — ANALYSIS sah `company_id` als ausreichend, hat aber `tenant_id`-Doku dazu nicht synchronisiert
6. **Verfahrensdokumentation HARD BLOCKER für Außenprüfung** (1.8) — Compliance-Schicht fehlt

**Damit erfüllt die Mission das Quality-Gate "≥3 neue Findings".**
