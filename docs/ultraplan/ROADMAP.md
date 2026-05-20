# Roadmap: Pilot → Markt → Skalierung

**Datum:** 2026-05-03
**Owner:** Ben (Solo-Founder)
**Methodik:** Sprint-basiert, max 7 Tasks/Woche, Definition of Done pro Task, Erfolgsmetriken pro Sprint

---

## Sprint 0 — Stop-the-Bleeding (Diese Woche, 5 Tage)

**Ziel:** Pilot-Blocker eliminieren bevor Backend-Container das nächste Mal still und leise crasht.

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| S0.1 | Slack-Webhook in Alertmanager aktivieren (G01) | 30min | Test-Alert erscheint in Bens Slack |
| S0.2 | `python-jose` → `pyjwt` Migration (G02) | 4h | `pip-audit` zeigt keinen kritischen CVE; alle 2FA-Tests grün |
| S0.3 | JWT in httpOnly-Cookie umstellen (G03) | 4h | Cookie sichtbar in DevTools, `localStorage`-Nutzung entfernt; Pentest-Vor-Check ok |
| S0.4 | `asyncio.run` Bug `adhoc_report_service.py:991` fixen (G04) | 2h | Adhoc-Report-Test grün, kein RuntimeError |
| S0.5 | Backend-Auto-Start + Watchdog konfigurieren (G05) | 1T | Backend startet bei System-Reboot autom., Crash-Recovery ≤30s |
| S0.6 | Sentry-DSN aktivieren (G10) | 2h | Erster Test-Error erscheint in Sentry-Inbox |
| S0.7 | Backup-Restore-Test ausführen + protokollieren (G08) | 4h | DR_RUNBOOK.md hat aktuelles Datum + erfolgreiche Restore-Bestätigung |

**Erfolgsmetriken Sprint 0:**
- 0 kritische CVEs in Dependencies
- Slack-Notification-Test bestanden
- Backend-Crash-Recovery <60s ohne Ben-Manual-Intervention
- Aktuelle Restore-Test-Doku <30 Tage alt

**Risiko-Trigger:** Falls auch nur 1 Sprint-0-Task nicht in 5 Tagen erledigt → Pilot-Datum **um 1 Woche verschieben**.

---

## Sprint 1 — Pilot-Hardening Auth + UX (Woche 2)

**Ziel:** Auth-Flow härten + UX-Pilot-Blocker schließen.

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| S1.1 | Login-Rate-Limit `5/15min + Lockout` (G07) | 4h | Brute-Force-Test: 6. Versuch wird gesperrt |
| S1.2 | "Zuruck"-Umlaut + i18n-Lint (G06, G22) | 4h | ESLint-Rule blockiert Umlaut-fehlende Strings; alle Treffer im Repo gefixt |
| S1.3 | Onboarding-Konsolidierung: 4→1 System (G11) | 1W | Neue User-Journey: 1 klarer Onboarding-Flow, alte 3 Systeme entfernt |
| S1.4 | Pilot-Workflow E2E-Test (G09) | 3T | Playwright-Test "Eingangsrechnung→OCR→Buchen→Archiv" grün, mit SLA-Asserts <2min |
| S1.5 | 56 Silent-Catches sweepen (G15) | 1W | `grep -c "except Exception:[\s\n]*pass"` = 0; alle ersetzt durch `logger.exception` |
| S1.6 | Pilot-Telemetrie-Dashboard (G21) | 1W | Grafana-Dashboard zeigt: TTFV, Workflow-Errors/h, OCR-Latenz p95 |

**Erfolgsmetriken Sprint 1:**
- E2E-Test-SLA: Pilot-Workflow <2min p95
- Onboarding-Drop-off-Rate <30% (gemessen über Telemetrie)
- 0 Silent-Catches im Service-Layer

---

## Sprint 2 — Compliance + Security-Hardening (Woche 3)

**Ziel:** Pilot-Compliance vorbereiten, ohne DATEV-Zertifizierung.

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| S2.1 | Verfahrensdokumentation als signiertes PDF generieren (G19) | 2W | PDF mit Datum, Hash, in `docs/compliance/` archiviert |
| S2.2 | Art. 30 DSGVO-Verzeichnis Seed + UI (G20) | 1W | 20 Aktivitäten gepflegt, Admin-UI editierbar |
| S2.3 | TSE/KassenSichV-Klärung mit Steuerberater (G35) | 1W | Schriftliche Einschätzung Steuerberater + Anwalt liegt vor |
| S2.4 | CSP `unsafe-inline` entfernen + Nonce-CSP (G16) | 1W | CSP-Header ohne `unsafe-inline`, alle Inline-Scripts in Source-Files |
| S2.5 | `pip-audit` + `gitleaks` + `bandit` in CI (G24) | 1T | GitHub-Action zeigt Status pro PR |
| S2.6 | Vault-Integration für Secrets (G25) | 1W | Mindestens DB-Password + JWT-Secret aus Vault gelesen |
| S2.7 | `training_migration_service.py:223` Whitelist (G17) | 4h | Tabellenname gegen Whitelist geprüft |

**Erfolgsmetriken Sprint 2:**
- Verfahrensdokumentation als signiertes Artefakt vorhanden
- CSP-Score auf securityheaders.com: A (von D)
- Steuerberater-Statement zu TSE liegt vor

---

## Sprint 3-4 — UX-Polish + Test-Coverage (Wochen 4-5)

**Ziel:** Pilot-User-Erlebnis erstklassig + Tests für Pilot-Phase.

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| S3.1 | Tooltip/Help in Top-20-Routes integrieren (G12) | 1W | Top-20-Routes haben mind. 3 Tooltips/Hilfe-Buttons |
| S3.2 | Glossar-Seite ("BWA, Skonto, SKR03") (G13) | 3T | `/help/glossar` Route mit ≥30 Begriffen, durchsuchbar |
| S3.3 | Sandbox-Mode (Read-Only Übungs-Mode) (G14) | 1W | Azubi kann ohne Datenverlust-Risiko alles ausprobieren |
| S3.4 | A11y-CI-Gate mit axe-core (G28) | 1W | PR-Check: `axe-core` Violations <5 |
| S3.5 | 93 axe-Violations beheben (G28) | 2W | Aktueller axe-Audit: 0 critical, ≤5 serious |
| S3.6 | Component-Tests: Risk-Scoring + Spotlight (G26) | 2W | ≥10 Tests für Risk-Scoring, ≥5 für Spotlight |
| S3.7 | KOSIT-Validator integrieren (G18) | 1W | XRechnung-Test besteht KOSIT-Validation |

**Erfolgsmetriken Sprint 3-4:**
- A11y axe-Score: 0 critical, ≤5 serious (von 93)
- Frontend-Component-Coverage: ≥40% kritischer Module
- KOSIT-konformer XRechnung-Export

---

## Sprint 5-8 — Pilot live + Stabilisierung (Wochen 6-9)

### Vor Pilot-Tag (Sprint 5, Woche 6):

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| S5.1 | Pilot-Kick-off-Meeting Familienbetrieb | 4h | 4 Stakeholder onboarded, Erwartungen abgestimmt |
| S5.2 | Daily-Check-in-Plan etabliert | 2h | Slack-Channel + tägliche 10min-Synchpunkte |
| S5.3 | Hot-Fix-Prozess dokumentiert | 4h | "Wenn X kaputt → Ben fixt in <Yh"-SLA-Doku |
| S5.4 | Pilot-Daten-Migration (Lexware-Import) | 2T | 3 Monate historische Daten in Ablage-System importiert |
| S5.5 | Onboarding-Workshop mit Prokurist + Azubis (3h) | 3h | Pilot-Team kann Workflow ohne Ben durchführen |

### Pilot-Phase (Sprint 6-7, Wochen 7-8):

**Tägliche Aktivitäten:**
- Telemetrie-Check (TTFV, Workflow-Errors, OCR-Latenz)
- 10min-Daily-Standup mit Pilot-Team
- Hot-Fix-Bearbeitung (Ziel: <2h Mean-Time-to-Resolution für P0-Bugs)
- Wöchentliche Retrospektive

**Erfolgsmetriken Pilot-Phase:**
- 0 verpasste Skonto-Fristen während Pilot
- TTFV (Eingangsrechnung→archiviert) <2 Min p50, <5 Min p95
- 0 Datenverluste, 0 GoBD-Violations
- NPS-Score Pilot-Team ≥7/10

### Pilot-Wrap-up (Sprint 8, Woche 9):

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| S8.1 | Pilot-Retrospective + Findings-Doc | 1T | Markdown-Report mit ≥10 konkreten Lessons-Learned |
| S8.2 | Pilot-Kunden-Testimonial sammeln | 2h | Schriftliche Aussage des Prokuristen |
| S8.3 | TCO-Vergleich vs vorherige Tools (Lexware+StarMoney+...) | 1T | Spreadsheet mit ist-vs-vorher Stunden + €€ |
| S8.4 | Markt-Entscheidung: Multi-Tenant vs Single-on-prem (G37) | 2T | ADR-Dokument mit Begründung |

---

## Monate 3-6 — Markt-Eintritt

### Monat 3: ICP-Reframe + Pricing

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| M3.1 | ICP-Reframe-Workshop (Founder 10): Family-Office-Light? (G58) | 4W | Neue ICP-Definition + 5 hypothetische Kunden-Profile |
| M3.2 | Pricing finalisieren (Perpetual + Maintenance) (G57) | 1W | 3 Pakete (Basic/Pro/Enterprise) mit konkreten €€-Zahlen |
| M3.3 | Solo-Founder-Support-Modell (G56) | 1W | SLA-Doku, Eskalations-Pfad, Hot-Fix-Prozess |
| M3.4 | Pilot-Erfolgs-Story als Case-Study verfassen | 1W | 2-Pager PDF, Foto-Material, Zahlen-Tabelle |

### Monat 4: God-Object-Refactoring (parallel zu Monat 3)

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| M4.1 | `streckengeschaeft/__init__.py` 88KB → Module (G41) | 2W | Init-File <2KB, Logik in 5+ Sub-Modules |
| M4.2 | `structured_extraction_service.py` 118KB → Split (G43) | 2W | Datei <30KB, gleiche Tests grün |
| M4.3 | `tax_optimization_service.py` 99KB → Split (G44) | 2W | Datei <30KB, gleiche Tests grün |

### Monat 5: Multi-Tenancy-Decision-Implementation

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| M5.1 | Falls Multi-Tenant: `company_id` zu `Invoice` etc. (G38) | 8W | 13 Tables haben `company_id` mit Backfill-Migration |
| M5.2 | Zentralisierter Auth-Decorator (G39) | 4W | Alle 200+ manuellen Filter durch Decorator ersetzt |
| M5.3 | Externer Pentest beauftragen (G46) | 3W | Pentest-Bericht mit ≤2 Critical-Findings |

### Monat 6: DATEV-Zertifizierung-Antrag + Markt-Launch-Prep

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| M6.1 | DATEV-Schnittstellen-Zertifizierung beantragen (G40) | 1W (Antrag), 6M (Durchlauf) | Partnerschaftsantrag eingereicht |
| M6.2 | DATEV-Belegbilder-Upload produktiv (G34) | 2W | E2E-Test mit Test-DATEV-Account erfolgreich |
| M6.3 | Erste 5 Cold-Outreach-Gespräche (Bergisches Land) | 2W | 5 Erstgespräche durchgeführt + Follow-up-Plan |

**Erfolgsmetriken Monate 3-6:**
- 5+ Erstgespräche mit potenziellen Kunden geführt
- DATEV-Antrag im Lauf
- Pentest-Findings ≤5 Critical
- Multi-Tenancy-Strategie entschieden + dokumentiert

---

## Monate 6-12 — Skalierung

### Monate 6-9: Erste zahlende Kunden

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| M9.1 | 3-5 zahlende Kunden onboarden | 3M | 3+ Verträge unterschrieben + System produktiv |
| M9.2 | OCR-Accuracy-Messreihe veröffentlichen (G29) | 2W | CER/WER pro Backend in Marketing-Material |
| M9.3 | Test-Coverage als CI-Gate (G60) | 1W | PR mit <60% Coverage wird abgelehnt |
| M9.4 | DR-RTO/RPO-SLA dokumentiert + getestet (G55) | 1W | RTO ≤4h, RPO ≤24h schriftlich + getestet |

### Monate 9-12: Bus-Faktor-Mitigation + Pivot-Optionen

| # | Task | Effort | Definition of Done |
|---|------|-------|--------------------|
| M12.1 | Onboarding-Doc für Hire #2 schreiben (G51) | 2W | 50-Seiten-Doku, jeder Senior-Dev kann in 1W onboarden |
| M12.2 | Spin-Off-Evaluation: Family-Office-Light (G61) | 4W | Markt-Studie + Cost-Estimate für Standalone-Produkt |
| M12.3 | Spin-Off-Evaluation: LkSG-Compliance (G64) | 4W | Markt-Studie + Cost-Estimate |
| M12.4 | Hire-#2-Entscheidung: Senior-Dev oder Sales? | 1M | Job-Doku, ggf. Stelle ausgeschrieben |

**Erfolgsmetriken Monate 6-12:**
- 5-10 zahlende Kunden
- Hire-#2-Entscheidung getroffen + ggf. Onboarding gestartet
- Pivot-Optionen evaluiert mit Daten-Basis
- DATEV-Zertifizierung im fortgeschrittenen Stadium

---

## Wann ist der erste Hire fällig?

Laut Investor-Perspektive (11): **Bus-Faktor 1 ist Top-Risiko**. Der erste Hire sollte fällig werden, sobald:
- 3+ zahlende Kunden auf der Platte sind (Support-Last steigt)
- Ben >50% Zeit in Support steckt (Feature-Velocity sinkt)
- Pilot-Erfolg + erste Kunden-Referenzen den Hire-Cost rechtfertigen

**Kandidaten-Profil:** Senior Backend-Engineer mit FastAPI/Postgres-Background, der die God-Objects refactored UND Pilot-Customer-Support übernehmen kann.

---

## Risiko-Trigger für Roadmap-Anpassung

Falls in irgendeinem Sprint ≥3 Tasks ausfallen:
- **Sprint 0-2:** Pilot-Datum nach hinten schieben
- **Sprint 5-8:** Pilot-Phase verlängern, NICHT weitere Kunden onboarden
- **Monat 3-6:** Markt-Eintritt verschieben, Pilot-Stabilisierung priorisieren
- **Monat 6-12:** Skalierung pausieren, Hire #2 priorisieren

---

## Total Effort Summary

| Phase | Dauer | Tasks | Aufwand (geschätzt) |
|-------|-------|------:|--------------------:|
| Sprint 0 | 1W | 7 | 5 Personentage |
| Sprint 1-4 | 4W | 26 | 20 PT |
| Sprint 5-8 (Pilot) | 4W | 9 | 15 PT (+ Tagesgeschäft) |
| Monate 3-6 | 4M | 13 | 60 PT |
| Monate 6-12 | 6M | 8 | 40 PT (+ Customer-Work) |
| **Total bis Monat 12** | **12M** | **63** | **~140 PT** |

Bei 5 PT/Woche durchschnittlich: das ist ein 28-Wochen-Plan = 7 Monate fokussierter Vollzeit-Arbeit. Realistisch in 12 Monaten machbar wenn Ben 60% Coding + 40% Customer/Sales/Support hat.
