# ULTRAPLAN_MASTER

**Das eine Dokument, das Ben in 6 Monaten nochmal liest.**

**Erstellt:** 2026-05-03
**Methodik:** 10 Code-Audits + 11 unabhängige Perspektiven + Live-Walk via Playwright
**Branch:** feature/ocr-performance | 5 Commits ahead of master

---

## 1. Executive Summary (max 500 Wörter)

Ben hat in 5 Monaten ein 4× vergrößertes Document-Management-System gebaut — 797 Backend-Services, 299 Frontend-Routes, 227 Migrationen — und hat aus dem FAANG-Audit2-Lese die richtige Lehre gezogen: **5 von 6 Frontend-Pilot-Blocker sind objektiv behoben** (404-Page, Empty-States, Onboarding, 2FA, Password-Reset). Die Backend-Substanz ist senior-engineering-tauglich (EventStore-Hash-Chain in Bank-Niveau, Pydantic v2 sauber, Cross-DB-Layer, RLS auf Postgres-Ebene).

Aber Live-Walk + Audit-Synthese zeigen drei systemische Lücken, die zwischen "Pilot wird Referenz-Kunde" und "Pilot wird Reputations-Schaden" entscheiden:

**Erstens** ist die Solo-Ops-Notification-Pipe tot — Live-Walk hat bewiesen, dass das Backend offline war ohne dass jemand es bemerkte. Slack-Webhook auskommentiert, SMTP zeigt auf `localhost:587`, PagerDuty-Templates ungenutzt. **Sprint 0 muss das in 30 Minuten fixen.**

**Zweitens** lauern drei konkrete Security-Pilot-Blocker, die ein Junior-Pentester in unter einem Tag findet: `python-jose==3.3.0` mit aktivem CVE-2024-33664, JWT in Response-Body statt httpOnly-Cookie (entgegen eigener Doku), CSP mit `unsafe-inline`. **2 Tage Aufwand für alle drei.**

**Drittens** sind Multi-Tenancy + DATEV-Zertifizierung systemische Markt-Blocker. Das System nutzt `company_id` (616 Treffer in 82 Files) als faktischen Tenant-Diskriminator, aber 13 kerngeschäftliche Tabellen (inkl. `Invoice`) haben keine Tenant-Spalte. Multi-Tenant-SaaS auf einer Instanz: nicht möglich ohne 2-4 Monate Hardening. DATEV-Zertifizierung-Antrag noch nicht eingereicht. **Markt-Eintritt frühestens Monat 6, realistisch Monat 9-12.**

Konsequenz: **Pilot beim Familienbetrieb in 3-4 Wochen JA**, sobald Sprint 0 läuft. **Markt als "Cloud-Alternative für deutsche KMU" NEIN** — die Founder-Perspektive empfiehlt Pivot zu *Family-Office-Light für Mittelstand-Patriarchen*. Privat-Modul (38 Services), GoBD-Hash-Chain, On-Premises-Souveränität, Streckengeschäft-Detection sind Differentiatoren, gegen die lexoffice nicht antritt.

Investor-Perspektive ergänzt: **Bedingt investierbar als Lifestyle-Business** mit 30-50 Kunden Cap, **NICHT als VC-Case**. Codebase-Asset-Wert: 180-250k EUR (Werkvertrag-Aufwand mit 50% Tech-Debt-Abschlag). 50k€-Brücken-Darlehen gegen erste 10 Pilot-Verträge realistisch, 500k€-Equity-Run nicht.

Bus-Faktor 1 ist Top-Risiko. Hire #2 sollte spätestens bei Kunde #3 ausgeschrieben werden (~Monat 9-12). Bis dahin: keine 60-Wochenstunden-Sprints, Pflicht-Urlaub 2 Wochen pro Quartal, Konsolidierungs-Bias statt Feature-Velocity.

Die 5-Monats-Code-Vervielfachung hat 4 God-Objects produziert (>60 KB pro File), 56 Silent-Catches an Compliance-Pfaden, 4 parallele Onboarding-Systeme, und Code-Doku-Drift zwischen CLAUDE.md-Versprechen und Code-Reality. Ein Konsolidierungs-Sprint ist überfällig — Sprint 0 ist explizit als solcher definiert.

**Verdict:** Pilot Ja, Markt mit Pivot, Skalierung mit Hire #2. Die nächsten 5 Tage entscheiden über die nächsten 12 Monate.

---

## 2. Methodik (kurz)

**Datenbasis:**
- 17 Pflicht-Dokumente gelesen (ANALYSIS_*.md, FAANG-Audit2, alle Pläne, README, CLAUDE.md, Letzte 250 CHANGELOG-Zeilen)
- 10 parallele Audit-Subagenten: Backend, DB-Schema, API, Frontend, Infra, Tests, Security, Compliance, Live-System (Playwright), ML/Data
- 11 parallele Perspektiv-Subagenten: Prokurist, Azubi, FE-Engineer, BE-Engineer, DevOps, Security-Architect, Compliance-Officer, Data-Scientist, Product-Manager, Founder/CEO, Investor/CFO
- Live-Walk via Playwright MCP auf laufendem Frontend (Backend war offline → Limitation dokumentiert)

**Quality-Gates:**
- ≥40 Gaps in GAP_ANALYSIS: erfüllt mit 66
- ≥20 Risiken in RISK_REGISTER: erfüllt mit 26
- ≥3 neue Findings in keiner ANALYSIS_*.md: erfüllt mit 6 (siehe CROSS_CUTTING §5)
- Datei:Zeile-Evidenz bei jeder Behauptung: durchgängig

---

## 3. Verdict pro Stufe

| Stufe | Antwort | Bedingung |
|-------|---------|-----------|
| **Stufe 1: Pilot Familienbetrieb (3-4 Wochen)** | **JA** | Sprint 0 (5 Tage Hardening) + Sprint 1-2 (4 Wochen Pre-Pilot-Polish) |
| **Stufe 2: Markt-Eintritt (Monat 3-6)** | **JA, aber mit Pivot** | ICP-Reframe von "KMU-Cloud-Alternative" zu "Family-Office-Light On-Prem". DATEV-Zertifizierung-Antrag in Monat 6. |
| **Stufe 3: Skalierung (Monat 6-12)** | **JA mit Cap** | Lifestyle-Business 30-50 Kunden, Hire #2 bei Kunde #3, kein VC-Pitch |

---

## 4. Die 11 Perspektiv-Verdikte

| # | Perspektive | Note | 1-Satz-Verdict |
|---|-------------|------|---------------|
| 01 | Prokurist (52, 18J Lexware) | **5/10** | "Hochglanz-Schaufenster, dahinter ein Maschinenraum mit 3.012 Endpoints, der mir am Pilot-Tag in 30% der Fälle das Genick brechen wird, wenn nicht jemand die Frontend-Lücken zuklappt und das Backend hochfährt." |
| 02 | Azubi (1. Lehrjahr) | n/a | "Ich verstehe nicht, was 90% der Sidebar-Punkte sind, hab Angst auf 'Löschen' zu klicken — ich brauche zwei Wochen Anleitung bevor ich hier was anfasse." |
| 03 | Frontend Engineer | n/a | "Solide TypeScript-Disziplin und konsistente Toolchain treffen auf systematische Lücken bei Code-Splitting (nur 22/299 Routes lazy()), Component-Tests und Accessibility — produktionstauglich für Pilot, aber strukturell nicht skalierungsbereit." |
| 04 | Backend Engineer | **6/10** | "Solides Mid-Senior-Backend mit Enterprise-Ambitionen — krankt an God-Objects, Async/Sync-Vermischung in Celery, und Silent-Catches an Compliance-Pfaden." |
| 05 | DevOps | **5.5/10** | "Die Infrastruktur ist überraschend reif — aber der letzte Mile zu Bens Telefon ist tot, und das ist bei Solo-Ops der einzige Mile, der zählt." |
| 06 | Security Architect | **6/10** | "Enterprise-tauglich konzipiert, aber drei Pilot-Blocker (JWT-im-Body, python-jose CVE, CSP unsafe-inline) findet ein gezielter Angreifer in unter einem Tag." |
| 07 | Compliance Officer | **6.5/10** | "Eines der saubersten Compliance-Fundamente in einem deutschen Mittelstandstool — aber ohne signierte Verfahrensdokumentation darf das System bei Außenprüfung oder erster B2G-XRechnung nicht ans Tageslicht." |
| 08 | Data Scientist | **6.5/10** | "ML-baulich erstaunlich weit — aber das System misst seine Versprechen nicht: keine veröffentlichten Accuracy-Zahlen, kein Drift-Reporting, kein zeitgesteuerter Self-Learning-Loop." |
| 09 | Product Manager | **5/10** | "Pilot-Blocker substanziell adressiert (Frontend 8/10), aber Cognitive Load (299 Routes / 127 Features) und 4 parallele Onboarding-Systeme machen das System für Azubis schwer zugänglich." |
| 10 | Founder/CEO | n/a | "Pilot beim Familienbetrieb JA — aber das Produkt darf NICHT als 'Cloud-Alternative für deutsche KMU' auf den Markt; das ist ein Kindheits-ICP. Reframe oder pivotiere innerhalb 90 Tagen, sonst bury." |
| 11 | Investor/CFO | n/a | "Bedingt investierbar — als Lifestyle-Business mit 30-50 Kunden Cap, NICHT als VC-Case; ein 500k-EUR-Equity-Investment macht keinen Sinn, ein 50k-EUR-Brücken-Darlehen gegen die ersten 10 Pilotverträge schon." |

**Schnitt der quantitativen Notes:** 5.83/10
**Audit-Schnitt:** 6.2/10
**Konsens:** Backend-Enterprise + Frontend-Beta + Ops-Solo-fragil

---

## 5. Cross-Cutting Findings (Top 10)

(Voll-Detail in `CROSS_CUTTING_FINDINGS.md`)

1. **Multi-Tenancy ist Begriffschaos + faktische Lücke** (Backend, DB, Security, BE-Eng, Sec-Architect)
2. **God-Objects als systemisches Anti-Pattern** (Backend, API, BE-Eng) — 4 Files >60KB, 1 API-File mit 554 Endpoints
3. **Frontend-Polish ist da, Frontend-Tests sind dünn** (Frontend, FE-Eng, Test, Live-Walk)
4. **Solo-Ops-Notification ist tot** (Infra, DevOps, Live-Walk)
5. **Silent-Catches an Compliance-/Audit-/Import-Stellen** (Backend, BE-Eng, Compliance) — 56 Vorkommen
6. **Test-Coverage strukturell dünn (besonders E2E)** (Test, Frontend, FE-Eng)
7. **Drei Security-Pilot-Blocker (alle adressierbar in 2 Tagen)** (Security, Sec-Architect)
8. **Compliance-HARD-Blocker für DATEV-Zertifizierung** (Compliance, Compliance-Officer)
9. **ML/Data-Reality lag deutlich unter Plan-Sprache** (ML, Data-Scientist, FE-Eng)
10. **Onboarding-Chaos (4 parallele Systeme)** (Azubi, Frontend, PM)

---

## 6. Gap-Analyse-Highlights (Top 15)

(Voll-Detail in `GAP_ANALYSIS.md` — 66 Gaps insgesamt)

| ID | Gap | Effort | Severity |
|----|-----|--------|---------:|
| G01 | Slack-Webhook in Alertmanager aktivieren | 30min | 5 |
| G02 | python-jose → pyjwt (CVE-2024-33664) | 4h | 5 |
| G03 | JWT in httpOnly-Cookie statt Body | 4h | 5 |
| G04 | asyncio.run-Bug in adhoc_report_service.py:991 | 2h | 5 |
| G05 | Backend-Container Auto-Start + Watchdog | 1T | 5 |
| G19 | Verfahrensdokumentation als signiertes PDF | 2W | 5 |
| G29 | OCR-Accuracy-Messreihe (CER/WER baseline) | 2W | 5 |
| G35 | TSE/KassenSichV-Klärung mit Steuerberater | 1W | 5 |
| G37 | Multi-Tenancy-Architektur-Decision | 2T | 5 |
| G40 | DATEV-Schnittstellen-Zertifizierung | 6M | 5 |
| G46 | Externer Pentest | 3W | 5 |
| G58 | ICP-Reframe zu Family-Office-Light | 4W | 5 |
| G15 | 56 Silent-Catches sweepen | 1W | 4 |
| G11 | 4 Onboarding-Systeme konsolidieren | 1W | 3 |
| G51 | Bus-Faktor-1 Mitigation (Hire-#2-Doku) | 2W | 4 |

---

## 7. Roadmap-Highlights

(Voll-Detail in `ROADMAP.md`)

### Sprint 0 (Diese Woche, 5 Tage): Stop-the-Bleeding
**G01, G02, G03, G04, G05, G08, G10** — Notification-Pipe + 3 Security-Pilot-Blocker + Backend-Watchdog + Backup-Test + Sentry

### Sprint 1-4 (4 Wochen Pre-Pilot-Hardening)
- Login-Rate-Limit härten (G07)
- Onboarding-Konsolidierung (G11)
- Pilot-Workflow E2E-Test (G09)
- Silent-Catches sweepen (G15)
- Verfahrensdokumentation (G19)
- Art. 30 DSGVO Verzeichnis (G20)
- TSE-Klärung (G35)
- CSP hardening (G16)

### Sprint 5-8 (4 Wochen Pilot live)
- Pilot-Kick-off, Daily-Check-in, Hot-Fix-SLA <2h
- Telemetrie-Dashboard
- Workflow-Erfolgsmessung (TTFV <2min p50)

### Monate 3-6: Markt-Eintritt
- ICP-Reframe (G58)
- God-Object-Refactoring (G41-G45)
- Multi-Tenancy-Decision + Implementation (G37, G38, G39)
- DATEV-Zertifizierung-Antrag (G40)
- Externer Pentest (G46)

### Monate 6-12: Skalierung
- 5-10 zahlende Kunden onboarden
- OCR-Accuracy-Messreihe (G29)
- Hire #2 Onboarding-Doc (G51)
- Spin-Off-Evaluation: Family-Office-Light (G61), LkSG (G64)

**Total:** ~140 Personentage über 12 Monate (60% Coding, 40% Customer/Sales/Support).

---

## 8. Risk Register Top 10

(Voll-Detail in `RISK_REGISTER.md` — 26 Risiken)

| R# | Risiko | P×I | Mitigation |
|----|--------|----:|------|
| R01 | Pilot-Reputations-Schaden bei Familienbetrieb-Crash | H×H=9 | Sprint 0: Notification + Watchdog |
| R02 | Externer Pentester findet Pilot-Blocker in <1 Tag | H×H=9 | Sprint 0+2: 3 Security-Fixes vor Pentest |
| R03 | Bus-Faktor-1: Ben krank/unavailable | M×H=6 | Hire #2 bei Kunde #3 |
| R04 | DATEV-Zertifizierung dauert >9 Monate | H×M=6 | Antrag JETZT in Monat 6 |
| R05 | Multi-Tenant-Refactor blockiert Markt-Eintritt | M×H=6 | Architektur-Decision Sprint 8 |
| R20 | Solo-Founder-Burnout | M×H=6 | Pflicht-Urlaub, Hire #2 spätestens Monat 9 |
| R07 | Familienbetrieb-Pilot scheitert sichtbar | M×M=4 | Sprint 0-2 Hardening + Daily-Check-in |
| R08 | Code-Wachstum 4x → Wartungs-Hölle | M×M=4 | Sprint 0 Konsolidierungs-Bias, God-Object-Refactor |
| R15 | Postgres-RAM 4GB reicht nicht bei pgvector | M×M=4 | Sofort auf 8GB |
| R17 | VC-Käufer-Story scheitert | M×M=4 | Stattdessen Lifestyle-Business + 50k Brücken-Darlehen |

---

## 9. Empfehlung an Ben — direkt, ehrlich, persönlich

**Ben, drei Dinge persönlich:**

**1. Reframe deine Story.** Du hast keine "Cloud-Alternative für deutsche KMU" gebaut — du hast ein **Family-Office-Light-System für Mittelstand-Patriarchen** gebaut. Privat-Modul (38 Services!), GoBD-Hash-Chain, On-Premises-Souveränität, Streckengeschäft-Detection. Gegen lexoffice 5-Min-Setup verlierst du. Gegen "ich bin ein Mittelstand-Patriarch und brauche ein Tool, das mein Privatvermögen + Firma + Mahnwesen + Streckengeschäft + DATEV in einem hat, on-prem, GoBD-konform" gewinnst du gegen niemanden. Innerhalb 90 Tagen entscheiden.

**2. Akzeptiere das Lifestyle-Cap.** Investor-Perspektive sagt es klar: 30-50 Kunden á 5-10k€/Jahr = 250-500k€ ARR = lebensfähiges Solo-Business. Das ist OK. 50k€-Brücken-Darlehen gegen die ersten 10 Pilot-Verträge ist realistisch — 500k€-Equity-Run nicht. Plane für ein Lifestyle-Geschäft, nicht für einen VC-Exit. Wenn der VC-Exit kommt, kommt er als Bonus.

**3. Schalte den FAANG-Mode aus.** Du hast in 5 Monaten den Code vervierfacht. Das ist nicht nachhaltig. Sprint 0 ist ein Konsolidierungs-Sprint — keine neuen Features. Beim nächsten Code-Spaß-Drift (RAG-Layer ausbauen, weil es Spaß macht): zähle 24 Stunden, dann frage dich: "Verdient mir das einen Kunden in 3 Monaten?"

**Und ein viertes, weniger persönlich:** Diese Mission hat 28 Markdown-Files produziert. In 6 Monaten lies primär `EXECUTIVE_DASHBOARD.md` + `RISK_REGISTER.md`. Wenn die Notes seitdem gestiegen sind, läufst du gut. Wenn sie gefallen sind, war eines der Risiken aus R01-R10 echt geworden — schaue dir an, welches.

---

## 10. Anhang: Verzeichnis aller erstellten Sub-Dokumente

```
docs/ultraplan/
├── 00_GROUND_TRUTH.md                    (Phase 0 — Was existiert wirklich)
├── audit/                                (Phase 1 — Tiefen-Audit)
│   ├── 00b_BACKEND_AUDIT.md              Note 6/10
│   ├── 00c_DB_SCHEMA_AUDIT.md            Note 7/10
│   ├── 00d_API_INVENTORY.md              Note 5/10
│   ├── 00e_FRONTEND_AUDIT.md             Note 8/10
│   ├── 00f_INFRASTRUCTURE_AUDIT.md       Note 6.5/10
│   ├── 00g_TEST_AUDIT.md                 Note 6/10
│   ├── 00h_SECURITY_AUDIT.md             Note 6/10
│   ├── 00i_COMPLIANCE_AUDIT.md           Note 6.5/10
│   ├── 00j_LIVE_SYSTEM_REPORT.md         Note 4/10 (Backend offline)
│   └── 00k_ML_DATA_AUDIT.md              Note 6.5/10
├── perspectives/                         (Phase 2 — 11 Perspektiven)
│   ├── 01_prokurist.md                   Note 5/10
│   ├── 02_azubi.md
│   ├── 03_frontend_engineer.md
│   ├── 04_backend_engineer.md            Note 6/10
│   ├── 05_devops.md                      Note 5.5/10
│   ├── 06_security.md                    Note 6/10
│   ├── 07_compliance.md                  Note 6.5/10
│   ├── 08_data_scientist.md              Note 6.5/10
│   ├── 09_product_manager.md             Note 5/10
│   ├── 10_founder_ceo.md
│   └── 11_investor.md
├── CROSS_CUTTING_FINDINGS.md             (10 Cross-Cutting Themen, 6 neue Findings)
├── GAP_ANALYSIS.md                       (66 Gaps, sortiert nach Severity × 1/Effort)
├── ROADMAP.md                            (Sprint 0-12 Monate, ~140 PT)
├── RISK_REGISTER.md                      (26 Risiken nach P×I sortiert)
├── EXECUTIVE_DASHBOARD.md                (1-Seiten-Killer, klares Verdict)
└── ULTRAPLAN_MASTER.md                   (Dieses Dokument)
```

**Total: 28 Markdown-Dateien.** Mission-Quality-Gate (≥17 Files): erfüllt mit 28.

---

**Mission-Status:** ABGESCHLOSSEN
**Nächste Aktion (von Ben):** Sprint 0 starten — G01 (Slack-Webhook) als allererster Task, 30 Minuten Aufwand.
