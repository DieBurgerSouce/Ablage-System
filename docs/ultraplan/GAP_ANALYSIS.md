# Gap-Analysis Matrix

**Methodik:** Tabellarische Aufstellung aller identifizierten Gaps aus 10 Audit-Reports + 11 Perspektiven. Pro Gap: ID, Beschreibung, Quelle, Severity (1-5), Effort (Tage/Wochen), Pilot-Blocker (Familie), Markt-Blocker (DATEV-Markt), Skalierungs-Blocker (10+ Kunden), Dependency.

**Sortierung:** Severity × (1/Effort) — höchster Impact pro investierter Zeit zuerst.

**Skala:**
- Severity: 1=trivial → 5=kritisch
- Effort: h=Stunden, T=Tage, W=Wochen, M=Monate
- Blocker: Y=Ja, N=Nein, T=Teilweise

---

## Tier 1: Sofort-Maßnahmen (Sprint 0, vor Pilot)

| ID | Gap | Quelle | Sev | Effort | Pilot | Markt | Skal | Dep |
|----|-----|--------|----:|--------|------:|------:|-----:|-----|
| G01 | Slack-Webhook in `alertmanager.yml` aktivieren | DevOps 5, Infra 00f | 5 | 30min | Y | Y | Y | — |
| G02 | `python-jose==3.3.0` → `pyjwt` Migration (CVE-2024-33664) | Sec 6, 00h | 5 | 4h | Y | Y | Y | — |
| G03 | JWT in httpOnly-Cookie statt Response-Body (`api/v1/auth.py:166`) | Sec 6, 00h | 5 | 4h | Y | Y | Y | G02 |
| G04 | `asyncio.run()` Bug in `adhoc_report_service.py:991` fixen | BE 4, 00b §4 | 5 | 2h | Y | Y | Y | — |
| G05 | Backend-Container-Auto-Start + Watchdog | DevOps 5, Live-Walk 00j | 5 | 1T | Y | Y | Y | G01 |
| G06 | `Zuruck zur Anmeldung` Umlaut-Fix + i18n-Lint | FE 3, Live-Walk 00j | 3 | 1h | T | Y | T | — |
| G07 | Login-Rate-Limit `10/min` → `5/15min + Lockout` | Sec 6, 00h | 4 | 4h | T | Y | Y | — |
| G08 | Backup-Restore-Test manuell ausführen + dokumentieren | DevOps 5, 00f | 4 | 4h | Y | Y | Y | — |
| G09 | Pilot-Workflow E2E-Test (Eingangsrechnung→OCR→Buchen→Archiv) | Test 00g, Prokurist 1 | 4 | 3T | Y | Y | T | — |
| G10 | Sentry-DSN aktivieren (selbst-hosted Sentry ist im Compose) | DevOps 5, FE 3 | 4 | 2h | T | Y | Y | — |

---

## Tier 2: Pre-Pilot-Hardening (Sprint 1-2, 2-4 Wochen vor Pilot)

| ID | Gap | Quelle | Sev | Effort | Pilot | Markt | Skal | Dep |
|----|-----|--------|----:|--------|------:|------:|-----:|-----|
| G11 | 4 parallele Onboarding-Systeme konsolidieren | Azubi 2, FE 00e | 3 | 1W | T | Y | Y | — |
| G12 | Tooltip/Help-System in Top-20-Routes integrieren | Azubi 2, FE 00e | 3 | 1W | T | Y | T | G11 |
| G13 | Glossar-Seite ("BWA, Skonto, SKR03 erklärt") | Azubi 2 | 3 | 3T | T | Y | T | — |
| G14 | Sandbox-/Übungs-Mode für Azubis | Azubi 2 | 4 | 1W | T | Y | T | — |
| G15 | 56 `except Exception: pass` mit `logger.exception` ersetzen | BE 4, 00b §6 | 4 | 1W | T | Y | Y | — |
| G16 | CSP `unsafe-inline` entfernen + Nonce-basierte CSP | Sec 6, 00h | 4 | 1W | T | Y | Y | — |
| G17 | `training_migration_service.py:223` Tabellenname-Whitelist | Sec 6, 00h | 3 | 4h | N | Y | Y | — |
| G18 | KOSIT-Validator für B2G-XRechnungen integrieren | Compliance 7, 00i | 3 | 1W | N | Y | Y | — |
| G19 | Verfahrensdokumentation als signiertes PDF generieren+archivieren | Compliance 7, 00i | 5 | 2W | T | Y | Y | — |
| G20 | Art. 30 DSGVO-Verzeichnis Seed-Migration + Admin-UI | Compliance 7, 00i | 4 | 1W | N | Y | Y | — |
| G21 | Pilot-Telemetrie-Dashboard (TTFV, Workflow-Errors, Latenz) | PM 9, FE 00e | 4 | 1W | Y | Y | Y | G10 |
| G22 | i18n-Lint-Rule (Umlaut-Korrektheit) | FE 3, Live-Walk | 2 | 4h | N | Y | T | G06 |
| G23 | Python-Dependency-Update (`fastapi 0.110→0.115`, `passlib` ersetzen) | Sec 6 | 3 | 1W | N | Y | Y | — |
| G24 | `pip-audit` + `gitleaks` + `bandit` in CI verankern | Sec 6, 00h | 3 | 1T | N | Y | Y | — |
| G25 | Vault-Integration für Secrets (statt `.env`-Files) | DevOps 5, 00f | 4 | 1W | T | Y | Y | — |

---

## Tier 3: Pilot-Begleitung + Stabilisierung (Sprint 3-6, 4-8 Wochen Pilot live)

| ID | Gap | Quelle | Sev | Effort | Pilot | Markt | Skal | Dep |
|----|-----|--------|----:|--------|------:|------:|-----:|-----|
| G26 | Frontend-Component-Tests für Risk-Scoring/Spotlight/Onboarding | FE 3, Test 00g | 3 | 2W | N | Y | Y | — |
| G27 | Echte E2E-Tests via Playwright `*.spec.ts` (10 kritische Flows) | Test 00g, FE 3 | 4 | 2W | T | Y | Y | — |
| G28 | A11y-CI-Gate (axe-core in Build-Pipeline, 93 Violations fixen) | FE 3, 00e | 4 | 2W | N | Y | Y | — |
| G29 | OCR-Accuracy-Messreihe (CER/WER pro Backend, Baseline) | DataSci 8, 00k | 5 | 2W | N | Y | Y | — |
| G30 | Self-Learning-Beat in Celery-Schedule aktivieren | DataSci 8, 00k | 3 | 1T | N | Y | Y | — |
| G31 | Drift-Reports debug + Output-Path verifizieren | DataSci 8, 00k | 3 | 1T | N | Y | Y | — |
| G32 | Auto-Ground-Truth-Pipeline auf 10× UP*-Dirs durchlaufen | DataSci 8, 00k | 4 | 4W | N | Y | Y | — |
| G33 | A/B-Test-Pipeline reaktivieren oder offiziell pausieren | DataSci 8, 00k | 2 | 2T | N | Y | T | — |
| G34 | DATEV-Belegbilder-Upload produktiv + Schnittstellen-Test | Compliance 7, 00i | 4 | 2W | N | Y | Y | — |
| G35 | TSE/KassenSichV-Anwendbarkeit klären (Steuerberater + Anwalt) | Compliance 7, 00i | 5 | 1W | T | Y | Y | — |
| G36 | Translation-Plan-Update: PlanVektorPipeline.md vs Code-Reality | DataSci 8 | 2 | 2T | N | T | T | — |

---

## Tier 4: Markt-Vorbereitung (Monate 3-6)

| ID | Gap | Quelle | Sev | Effort | Pilot | Markt | Skal | Dep |
|----|-----|--------|----:|--------|------:|------:|-----:|-----|
| G37 | Multi-Tenancy-Decision: Single-Tenant-pro-Instanz vs Multi | BE 4, DB 00c, Sec 00h | 5 | 2T | N | Y | Y | — |
| G38 | Falls Multi-Tenant: `company_id` zu `Invoice` + 12 weitere Tables | DB 00c, Sec 00h | 5 | 2M | N | Y | Y | G37 |
| G39 | Zentralisierter Authorization-Decorator (statt 200+ manuelle Filter) | Sec 6, 00h | 4 | 1M | N | Y | Y | G37 |
| G40 | DATEV-Schnittstellen-Zertifizierung beantragen + durchlaufen | Compliance 7, 00i | 5 | 6M | N | Y | Y | G34 |
| G41 | `streckengeschaeft/__init__.py` (88KB) → Module aufsplitten | BE 4, 00b §2 | 4 | 2W | N | T | Y | — |
| G42 | `app/api/v1/orchestration.py` (554 endpoints) → Sub-Domains | API 00d, BE 4 | 4 | 1M | N | T | Y | — |
| G43 | `structured_extraction_service.py` (118KB) → Module-Split | BE 4, 00b §2 | 4 | 2W | N | T | Y | — |
| G44 | `tax_optimization_service.py` (99KB) → Module-Split | BE 4, 00b §2 | 4 | 2W | N | T | Y | — |
| G45 | `quick_classification_service.py` (79KB) → Module-Split | BE 4, 00b §2 | 4 | 1W | N | T | Y | — |
| G46 | Externer Pentest (5 PT Web-App + 2 PT Code-Review) | Sec 6, 00h | 5 | 3W | N | Y | Y | G02-G07,G16 |
| G47 | Transaction-Boundaries an Multi-Step-Mutationen ergänzen | BE 4, 00b §4 | 4 | 2W | N | Y | Y | — |
| G48 | N+1-Sweep + Eager-Loading in `spotlight_service.py` etc. | BE 4, 00b §5 | 3 | 1W | N | T | Y | — |
| G49 | Code-Splitting auf 80%+ der 299 Routes (statt 22) | FE 3 | 3 | 2W | N | Y | Y | — |
| G50 | DSGVO-DPA-Templates für Steuerberater-Verträge | Compliance 7 | 3 | 1W | N | Y | Y | — |

---

## Tier 5: Skalierungs-Vorbereitung (Monate 6-12)

| ID | Gap | Quelle | Sev | Effort | Pilot | Markt | Skal | Dep |
|----|-----|--------|----:|--------|------:|------:|-----:|-----|
| G51 | Bus-Faktor-1-Mitigation: Onboarding-Doc für Hire #2 | Investor 11, GROUND_TRUTH §3.5 | 4 | 2W | N | T | Y | — |
| G52 | RAG-Stack vor Markt-Kommunikation entfernen oder produktiv machen | DataSci 8, GROUND_TRUTH §3.4 | 4 | 4W | N | Y | T | G29-G33 |
| G53 | GPU-VRAM-Limit + Concurrent-OCR-Test (RTX 4080 16GB) | DevOps 5, Infra 00f | 4 | 1W | N | T | Y | — |
| G54 | Postgres-RAM-Limit von 4GB auf 8GB anheben (pgvector-Last) | DevOps 5, Infra 00f | 3 | 1h | N | T | Y | — |
| G55 | Disaster-Recovery: RTO/RPO-SLA dokumentieren + testen | DevOps 5, Infra 00f | 4 | 1W | N | Y | Y | G08 |
| G56 | Solo-Founder-Support-Modell: Pilot-Kunden-SLA dokumentieren | Founder 10, Investor 11 | 4 | 1W | T | Y | Y | — |
| G57 | Pricing-Modell finalisieren (Perpetual License + Maintenance) | Founder 10, Investor 11 | 4 | 1W | N | Y | Y | — |
| G58 | ICP-Reframe: KMU-Cloud-Alternative → Family-Office-Light | Founder 10 | 5 | 4W | N | Y | Y | — |
| G59 | Code-Doku-Drift Audit (CLAUDE.md, ANALYSIS_*, Pläne) | GROUND_TRUTH §3.2 | 3 | 1W | N | Y | T | — |
| G60 | Test-Coverage-Targets als CI-Gate (nicht erreicht = no-merge) | Test 00g | 4 | 1W | N | Y | Y | — |

---

## Tier 6: Strategische / Optionale Items

| ID | Gap | Quelle | Sev | Effort | Pilot | Markt | Skal | Dep |
|----|-----|--------|----:|--------|------:|------:|-----:|-----|
| G61 | Privat-Modul als Spin-Off-Produkt evaluieren ("Family Office Light") | Founder 10 | 3 | 4W | N | T | T | G58 |
| G62 | Streckengeschäft-Modul als Standalone-Produkt evaluieren | Founder 10 | 3 | 4W | N | T | T | — |
| G63 | RAG-Layer als API-Add-On vermarkten (Document-Chat) | Founder 10 | 3 | 6W | N | T | T | G52 |
| G64 | LkSG-Compliance-Plattform als Pivot-Option | Founder 10 | 2 | 12W | N | T | T | — |
| G65 | Mobile-App (iOS/Android) für Document-Capture | DevOps 5, PM 9 | 2 | 12W | N | T | T | — |
| G66 | DATEV-Marketplace-Listung anstreben | Founder 10 | 4 | 8W | N | Y | Y | G40 |

---

## Cluster-Zusammenfassung

| Cluster | Anzahl Gaps | Primär Schwerpunkt |
|---------|------------:|--------------------|
| **A: Solo-Hardening (Pilot)** | 10 (G01-G10) | Notification, Security-3, Backend-Stabilität, Live-Test |
| **B: UX/Compliance-Hardening (Pre-Pilot)** | 15 (G11-G25) | Onboarding, Glossar, Silent-Catches, CSP, Verfahrensdoku, Art.30 |
| **C: Pilot-Stabilisierung (Live)** | 11 (G26-G36) | Tests, A11y, ML-Messung, DATEV-Belege, TSE-Klärung |
| **D: Markt-Vorbereitung** | 14 (G37-G50) | Multi-Tenancy, God-Object-Splits, Pentest, DATEV-Zertifizierung |
| **E: Skalierungs-Vorbereitung** | 10 (G51-G60) | Bus-Faktor, GPU-Limits, ICP-Reframe, DR-SLA |
| **F: Optional/Pivot** | 6 (G61-G66) | Spin-Offs, Mobile, Marketplace |

**Total:** 66 Gaps. Mission-Quality-Gate `≥40 Gaps`: **erfüllt** mit 66.

---

## Fokus-Empfehlung

**Wenn Ben nur 1 Liste durchziehen kann, dann Tier 1+2 (G01-G25):**
- **Tier 1 (10 Gaps):** Sprint 0, ~5 Tage Aufwand → Pilot-Blocker eliminieren
- **Tier 2 (15 Gaps):** Sprint 1-2, ~4 Wochen Aufwand → Pilot-Hardening

Das macht den Unterschied zwischen "Pilot wird Reputations-Schaden" und "Pilot wird Referenz-Kunde".

Tier 3-4 sollte parallel zur Pilot-Phase laufen — Tier 5-6 erst nach Pilot-Abschluss + Markt-Entscheidung.
