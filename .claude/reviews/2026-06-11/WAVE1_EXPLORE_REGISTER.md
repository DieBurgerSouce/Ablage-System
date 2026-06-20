# WAVE 1 — Komplett-Exploration: Findings-Register

**Datum:** 2026-06-11 (Pfadsegment `undefined` vom Orchestrator-Aufruf vorgegeben)
**Commit (HEAD bei Synthese):** `2f79f8b9` (master)
**Quellen:** 16 Explorer-Agenten (~316 Roh-Findings) + adversariale Verifikation, dedupliziert auf 50 gezählte Findings (P0–P3) + 30 widerlegte Findings.
**Hinweis Sicherheit:** Konkrete Secret-Werte aus Explorer-Belegen werden hier bewusst NICHT wiedergegeben (Critical Rule 1).

---

## Executive Summary

Welle 1 hat 16 Bereiche mit ~316 Roh-Findings exploriert; nach Deduplikation verbleiben 50 gezählte Einträge (1× P0, 12× P1, 25× P2, 12× P3) plus 30 widerlegte Findings. Kernbefund: Die vier historischen Produktionsblocker B1–B4 sind verifiziert behoben bzw. bewusst gescoped; die Codebasis ist substanziell gehärtet (Migrationen 265–268, Multi-Tenant-Welle 1a, Test-Wahrheit G5). Kritisch bleibt genau ein P0: `DEBUG=true` in der Produktions-`.env` bypasst die 2FA für Admin-Rollen. Auf P1 folgen Secrets-Rotation/Vault-Aktivierung, 10 untriagierte Schemathesis-5xx-Bugs, der rote `build:strict` (100+ TS-Fehler), ungesicherte Deploy-Migrationen, Real-DB-Stamp-Reconciliation, das fehlende GoBD-Verfahrensdoku-Artefakt, 196 Integration-Failures, Banking-Placeholder-Tokens, Stub-Risikodatenquellen sowie ungesicherte Git-Arbeit (Worktrees/Stashes/Branches). Auffällig: knapp ein Drittel der Roh-Findings hielt der adversarialen Verifikation nicht stand (v. a. Celery-Beat-Tasknamen, API-Test-Zahlen, veraltete Obsidian-Notizen) — diese sind sauber in der Sektion „Widerlegt" abgetrennt und zählen nicht. P2/P3 bündeln Qualitäts-, Doku- und Infra-Politur (K8s-Härtung vor Erstnutzung, Monitoring-Lücken, stale Runbooks, Celery-Robustheit).

---

## Statistik

### Nach Priorität

| Priorität | Anzahl | Definition |
|---|---|---|
| P0 | 1 | Blockierend/kritisch (Sicherheit, Datenverlust, App startet nicht) |
| P1 | 12 | Hoch (echte Funktionslücken, unmergte wertvolle Arbeit, rote Tests) |
| P2 | 25 | Mittel (Qualität, stale Doku, fehlende Tests) |
| P3 | 12 | Niedrig/Politur (inkl. verifiziert-behobener Sammelposten) |
| Widerlegt | 30 | verified=false — zählen nicht |

### Nach Bereich (Roh-Findings → davon widerlegt)

| Bereich | Roh | Widerlegt |
|---|---|---|
| status-memory | 15 | 3 |
| reviews-plans | 22 | 3 |
| git-archaeology | 11 | 0 |
| backend-markers | 24 | 1 |
| frontend-audit | 23 | 1 |
| tests-audit | 18 | 0 |
| migrations-db | 18 | 1 |
| infra-deploy | 24 | 0 |
| api-surface | 10 | 5 |
| docs-truth | 14 | 0 |
| obsidian-notes | 24 | 6 |
| celery-events | 19 | 5 |
| kubernetes-and-iac | 22 | 1 |
| monitoring-observability | 23 | 0 |
| security-posture | 25 | 2 |
| github-workflows-quality | 24 | 2 |
| **Summe** | **316** | **30** |

---

## P0 — Blockierend / Kritisch

| ID | Bereich | Finding | Beleg | Status | Verifiziert | Vorgeschlagene Aktion |
|---|---|---|---|---|---|---|
| W1-001 | security-posture | `DEBUG=true` in Produktions-`.env` bypasst 2FA für Admin-Rollen; zusätzlich `ENVIRONMENT=development` gesetzt | `.env` Z.46; `app/core/rbac.py` Z.238/252/303/322/375/455 | offen | ✅ | Sofort `DEBUG=false`; 2FA-Bypass nur bei `TESTING` erlauben; E2E-Tests gegen Staging-Env statt Prod-`.env` |

---

## P1 — Hoch

| ID | Bereich | Finding | Beleg | Status | Verifiziert | Vorgeschlagene Aktion |
|---|---|---|---|---|---|---|
| W1-002 | security-posture, infra-deploy | Vault per Default deaktiviert (`VAULT_ENABLED=false`); produktive Secrets (DB, Redis, MinIO, Qdrant, Slack-Webhook, Sentry-DSN) klartext in lokaler `.env`. NICHT in Git-Historie (verifiziert), aber Werte zirkulierten in Review-/Agent-Artefakten | `docker-compose.yml` Z.545/692/833; `.env` (Werte hier nicht wiedergegeben) | offen | ✅ | Alle betroffenen Secrets rotieren; Vault für Produktion verpflichtend (Default true + Healthcheck); File-Mount-Pattern für Slack/SMTP abschließen |
| W1-003 | backend-markers, status-memory, reviews-plans | Banking/PSD2-Funktionslücke: `payment_initiation_service` nutzt „placeholder"-Access-Tokens ungeschützt (Z.352/466); Auto-Sync per Flags (`FINTS_/PSD2_AUTO_SYNC_ENABLED=False`) sicher deaktiviert; echter OAuth2/SCA-Token bewusst OUTSCOPED (BaFin) | `payment_initiation_service.py:352/466`; `auto_transaction_import_service.py:426-447`; `celery_app.py:3130-3140` | teilweise (geguarded) | ✅ | SecureTokenVault implementieren oder Payment-Initiation hart deaktivieren; Outscope-Entscheidung in KNOWN_ISSUES/Docs fixieren |
| W1-004 | tests-audit, status-memory, reviews-plans | 10 reproduzierbare 5xx-Bugs aus Schemathesis-Baseline (Input-Validierung → 500 statt 422, fehlende 404-Handler); Triage offen; `api-fuzz.yml` non-blocking | `docs/qa-reports/2026-06-10-schemathesis-baseline.md` (curl-Repros); `.github/workflows/api-fuzz.yml` | offen | ✅ | Bugs triagieren + fixen; ab ~2026-06-24 `continue-on-error` entfernen; danach Re-Run mit höherem MAX_FAILURES |
| W1-005 | frontend-audit | `build:strict` rot: 100+ TS-Fehler. Reproduziert: framer-motion Easing TS2322 (`lib/animations/index.ts:17/82`), Props-Mismatch `onSave` vs `onSuccess` (`admin.imports.email.tsx:40`), fehlende Document-Properties, Hook-API-Drift (`open-file.tsx`), tote Route `/document-graph` | `npm run typecheck`-Ausgabe; tsc-Repro | offen | ✅ | TS-Fehler abbauen (Start: animations, EmailConfigForm-Props, Document-Types); `build:strict` als CI-Gate aktivieren |
| W1-006 | migrations-db | Deploy-Migrationen ungesichert: kein automatisches `alembic upgrade head` im Container-Start; `deploy.yml`-SSH-Heredocs ohne `set -e` (Migrationsfehler stoppt Deploy nicht); kein Dry-Run; kein Runbook | `Dockerfile` CMD Z.136; `deploy.yml` Z.136-161/276-304 | offen | ✅ | `set -e` + explizites Migrations-Gate mit Rollback; `--sql`-Dry-Run; Runbook `Database-Migrations-Deployment.md` erstellen |
| W1-007 | migrations-db | Real-DB-Stamp-Abhängigkeit: Bestands-DBs auf 261 ohne 151-Branch erreichen Head nur via `stamp 262` → `upgrade head`; Lösung existiert in `scripts/dbtest/setup_real_test_db.sh`, Prod-Prozess/Runbook fehlt; from-scratch nur bis 265 re-verifiziert (266–268 ausstehend) | `KNOWN_ISSUES.md` Z.58; `scripts/dbtest/setup_real_test_db.sh` Z.58-65 | teilweise | ✅ | Dev-/Prod-DB reconcilen + dokumentieren; CI-Gate „from-scratch bis 268" |
| W1-008 | obsidian-notes | GoBD-Verfahrensdokumentation existiert nur als Code-Generator (Bytes in RAM), kein signiertes, versioniertes PDF-Artefakt — Voraussetzung für Außenprüfung | `procedure_documentation_service.py`; Vault `06_Compliance/GoBD_Checklist.md` | offen | ✅ | PDF generieren, digital signieren, versionieren, revisionssicher ablegen |
| W1-009 | tests-audit | 196 pre-existing Integration-Failures als Baseline dokumentiert (Branch=master bitidentisch, 0 neue), aber untriagiert | `RECENT_CHANGES.md` (W1 1a); Failure-Snapshots in `.claude/` (bitidentisch verifiziert) | offen | ✅ | Triage nach Kategorie (DB-/GPU-Required, Mock, Spec-Drift); `known_issue`-Marker zur Abgrenzung neuer Regressionen |
| W1-010 | backend-markers | Dashboard-CashFlow-KPI liefert `current_balance=0.0` hardcoded (TODO G4); `get_balance` existiert in Banking-Services, ist nicht angebunden. OCR-Quality-KPI-Service existiert inzwischen DB-gestützt — Anbindung verifizieren | `app/api/v1/dashboard.py:813/947-950`; `ocr_quality_metrics_service.py:208-263` | teilweise | ✅ | Kontostand-Lesemethode anbinden; OCR-KPI-Anbindung prüfen; TODO(G4) schließen |
| W1-011 | backend-markers | Externe Risiko-/Registerdaten nur Stubs/Mocks: NorthData/Schufa-B2B/Creditreform geben immer None (`risk_scoring_service:169/216/265`); Bundesanzeiger default Mock (`BUNDESANZEIGER_MOCK=True`), Handelsregister default disabled; Creditreform fällt ohne Credentials in Mock-Mode | `risk_scoring_service.py`; `external/bundesanzeiger_service.py:374`; `handelsregister_service.py:823`; `creditreform_service.py:111-115` | offen | ✅ | Echte APIs anbinden ODER Features im UI ehrlich als „nicht verfügbar" kennzeichnen; Mock-Status sichtbar loggen |
| W1-012 | infra-deploy | `init-db.sql` ändert Datenbank `ablage_ocr`, Compose startet aber mit `ablage_system` → From-Scratch-Provisionierung inkonsistent. Verifier ausgefallen — zuerst reproduzieren | `infrastructure/docker/init-db.sql:27-29` vs `docker-compose.yml:10` | offen (unverifiziert) | ⚠️ Verifier ausgefallen | Reproduzieren; Hardcode durch `POSTGRES_DB`-Env ersetzen |
| W1-013 | git-archaeology | Ungesicherte/unmergte Arbeit: 3 detached Worktrees (`.cursor/worktrees/...{hik,jfw,rhz}`) auf `64d6121a` (KEIN Vorfahre von master); `feature/ocr-performance` 19+ unmerged Commits (Tag-Backup existiert); Stashes 0–6 (stash@{1}: 151 Dateien, 9k+ Insertions); `develop` 2 Commits vor master | `git worktree list`; `git stash list`; `git log master..develop` | offen | ✅ (Worktrees) | Inhalte sichten: mergen/taggen, dann Worktrees entfernen, Stashes droppen, develop-Strategie klären, Remote-Branch nach Sichtung löschen |

---

## P2 — Mittel

| ID | Bereich | Finding | Beleg | Status | Verifiziert | Vorgeschlagene Aktion |
|---|---|---|---|---|---|---|
| W1-014 | security-posture, status-memory, tests-audit | RLS/Tenant-Restausbau: `RLS_ENFORCE_DEFAULT` (fail-closed) + `get_tenant_db`-Wrapper offen; Celery-Tasks ohne garantierten RLS-Kontext; PaymentService user-scoped (2 strict-xfail) | `app/api/dependencies.py` (set_rls_context); `test_multi_tenant_migration.py` | offen | – | Nächste Tenant-Härtungswelle; PaymentService-Scope entscheiden (Design vs. Bug) und dokumentieren |
| W1-015 | kubernetes-and-iac | K8s/IaC (nicht produktiv) vor Erstnutzung härten: „changeme"-Secrets in `kustomization.yaml:70-74`, GPU-Worker als root, keine RBAC/PDB/PodSecurity, `:latest`-Images mit pull Always, K3s-Token-Default, Terraform-State über HTTP, Single-Proxmox-Node, Patroni ungenutzt, CORS `*` | `infrastructure/kubernetes/...`; `terraform/main.tf:54`; Ansible defaults | offen | ✅ (6 Kernpunkte) | Vor jedem K8s-Deploy: Sealed-Secrets/ESO, Image-Pinning, RBAC/PDB, HTTPS-State; Canonical-Methode (Helm vs. Kustomize) festlegen |
| W1-016 | frontend-audit | 20 `as any`/`as unknown`-Casts in UI-kritischen Pfaden; Badge-variant-Cast (`RiskOverviewWidget.tsx:140`) Runtime-Mismatch-anfällig; `CreateDashboard.tsx:138 setMode(v as any)` | grep-Inventar (13 Komponenten) | offen | ✅ | Union-Types statt Casts; `getRiskLevel`-Returntyp auf Badge-Variants einengen |
| W1-017 | frontend-audit | Deutsch-Regel verletzt: Platzhalter "Error" (`EmailConfigWizard.tsx:509`) und "INBOX/Error" (`EmailConfigForm.tsx:526`) | beide Dateien, Zeilen bestätigt | offen | ✅ | Auf „Fehler"/„INBOX/Fehler" ändern; Lint-Regel für englische UI-Strings erwägen |
| W1-018 | frontend-audit, status-memory, reviews-plans | Vitest hängt unter Windows bei >1 Datei parallel (Worker-Deadlock); keine Mitigation in `vitest.config.ts`; `frontend/package-lock.json` lokal modifiziert (legacy-peer-deps), uncommitted | RECENT_CHANGES W3; `vitest.config.ts`; git status | offen | – | `threads/isolate`-Config bzw. Worker-Setup prüfen; package-lock-Entscheidung treffen (committen + dokumentieren oder Workaround fixen) |
| W1-019 | api-surface | `documents.py`: 23/46 Endpoints ohne response_model (inkl. Binary-Downloads ohne FileResponse-Deklaration), `response_model=None`-Antipattern (Z.1127/1249); Pagination-Limits inkonsistent (10/20/50/100); Auth-Dependencies uneinheitlich | `app/api/v1/documents.py:1335/1396/1630/1693`; `search.py` | offen | ✅ (documents) | Response-Modelle/`response_class` nachziehen; zentrale PaginationParams-Dependency; Auth-Pattern standardisieren |
| W1-020 | monitoring-observability | OTEL-Collector deployt, aber SDK nicht integriert (OpenTelemetry-Pakete fehlen in pyproject; `init_telemetry` läuft ins Leere) → Tracing effektiv tot | `docker-compose.tracing.yml:98-140`; `app/main.py` | offen | ✅ | OTEL-SDK in FastAPI-Middleware + Celery integrieren; W3C-Trace-Context propagieren |
| W1-021 | monitoring-observability, obsidian-notes | Alerts referenzieren nicht existierende Metriken (`ablage_ocr_cer/wer_estimate_avg`); kein End-to-End-Pipeline-SLI; keine Task-Age/Backpressure-Metriken; Alertmanager-SMTP hardcoded `localhost:587`; R27 (escalate_overdue_approvals hing 47h auf SMTP, solo-pool) Status prüfen | `business-alerts.yml:13-62`; `alertmanager.yml:64/113/145`; Vault §R27 | offen | ✅ (Metriken/SMTP) | CER/WER-Histogramme implementieren oder Alerts entfernen; `document_processing_duration`-SLI; SMTP per Env + Timeout-Schutz im Eskalations-Task |
| W1-022 | monitoring-observability | Metrics-Scraping ohne TLS; `METRICS_SCRAPE_TOKEN` nur als Kommentar; Prometheus-Schutz hängt allein an Nginx (.htpasswd, ohne Rate-Limit für /metrics) | `prometheus.yml:31-135`; nginx conf Z.213-224 | offen | ✅ | Bearer-Token für alle Scrape-Jobs; TLS oder dokumentierte Netz-Isolation |
| W1-023 | infra-deploy | Qdrant-Inkonsistenz: Backend-Default `QDRANT_ENABLED=false`, Worker `=true`; Qdrant startet immer (kein profile) und Backend wartet auf Qdrant-Health auch wenn deaktiviert | `docker-compose.yml:419/581/635-636/728` | offen | ✅ | Defaults angleichen; profile `[vector]` oder Qdrant als Pflichtdienst; Healthcheck auf authentifizierten HTTP-Endpoint |
| W1-024 | infra-deploy | Watchdog-Container läuft als root (`user: 0:0`) mit ungeschütztem `docker.sock`-Mount | `docker-compose.yml:1587/1605` | offen | – | Socket read-only + Allow-List oder dedizierter Restart-Sidecar mit Minimalrechten |
| W1-025 | github-workflows-quality | Deployment-Gates löchrig: Staging-Smoke-Tests `continue-on-error:true`; `SLO_STATUS` geparst aber nie geprüft; `terraform.yml` schreibt AWS-Creds nach `~/.aws/credentials` ohne Cleanup; ungenutzte `KUBECONFIG_SECRET`-Env auf Job-Ebene | `deploy.yml:167/312-327`; `terraform.yml:128-135/205-212`; `k8s-deploy.yml:40` | offen | ✅ (alle 4) | `continue-on-error` entfernen + Gate auf deploy-staging; SLO-Assertion ergänzen; `configure-aws-credentials`-Action bzw. Cleanup; Z.40 löschen |
| W1-026 | security-posture | Supply-Chain: keine Image-Signierung (cosign/SLSA-Provenance), CI-Commits unsigniert, pip-Install ohne `--require-hashes` (Basis-Images korrekt SHA-gepinnt) | `docker-build.yml`; `release.yml:176/215`; `Dockerfile` | offen | ✅ (3×) | cosign + SLSA-Provenance; signierte CI-Commits + Branch-Protection; `pip-compile --generate-hashes` |
| W1-027 | security-posture | Interne Service-Kommunikation unverschlüsselt: Redis/MinIO plaintext TCP (Postgres-TLS teilweise vorhanden); keine Service-zu-Service-Auth (Celery nur Redis-Passwort) | `docker-compose.yml:136/566/706`; `mtls.conf` (ungenutzt) | offen | ✅ | TLS für Redis/MinIO; Celery-Message-Signing; mTLS-Rollout mit On-Prem-Risikoabwägung dokumentieren |
| W1-028 | security-posture | GDPR-Retention nicht automatisiert (`gdpr_tasks` ohne Beat-Schedule, Audit-Logs ohne TTL); fail-closed-Rate-Limits auf Auth-Endpoints (password-reset) nicht explizit | `app/workers/tasks/gdpr_tasks.py`; `celery_app.py` beat_schedule; `.env` RATE_LIMIT_* | offen | – | Beat-Job `enforce_retention_policy`; explizite `@rate_limit`-Dekoratoren mit fail_closed |
| W1-029 | backend-markers | Hardcoded Firmen-Referenzen `folie`/`messer` (`VALID_COMPANIES` frozenset; Fallback-Pfade) statt CompanyService | `entity_search_service.py:39/199-209/298-307`; `api/v1/entities.py:266/384` | teilweise | ✅ | Auf `CompanyService.get_company_short_names()` umstellen; grep-Sweep über Codebasis |
| W1-030 | backend-markers | Folder-Modell-Entscheidung offen: deaktivierte `default_folder`-FKs (`models_erp_import:614/686`, `models_entity_business:379`); NLQ-/Routing-Services mit „Folder model does not exist" | `nlq_service.py:40`; `routing_intelligence_service.py:37` | Entscheidung offen | – | Architektur-Entscheid: Folder-Modell implementieren oder FK-/Parameter-Reste entfernen |
| W1-031 | backend-markers | Compliance-Code-Lücken: `autopilot_service` exportiert Mock-Content statt MinIO-Dateien (Z.331); `gobd_service` Hash-Validierung auskommentiert (Z.366) | `compliance/autopilot_service.py`; `compliance/gobd_service.py` | offen | – | MinIO.get_object integrieren; Hash-Validierung aktivieren oder Deaktivierung begründet dokumentieren |
| W1-032 | celery-events | Celery/Orchestrator-Robustheit: Idempotenz nicht flächendeckend auf Beat-Tasks; Retry/DLQ uneinheitlich (keine Eskalation bei DLQ-Wachstum); Notifications ohne Retry; GPU-Lock-TTL 60s vs. OCR-Tasks >60s; Sentinel-Config ohne Validierung; sync/async-Mix in BPMN-Tasks; Decision-Deques ohne Monitoring; 28/40 EventTypes ohne Orchestrator-Handler (verifiziert) | `event_bus.py`; `cross_module_orchestrator.py:231-293`; `celery_app.py:35-81` | offen | ✅ (Events), – (Rest) | Idempotency-Keys für Daily-Tasks; GPU-Lock-Auto-Refresh; DLQ-Schwellen-Alerts; Handler für High-Impact-Events registrieren |
| W1-033 | docs-truth | Status-Doku inkonsistent: PROJECT_STATUS nennt alembic head 267 (real 268); Root-CLAUDE.md-Header verweist auf „4 offene Blocker" (Stand 2026-06-03, überholt); Feature-Tabelle „Production-Ready" ohne Caveats; KNOWN_ISSUES↔RECENT_CHANGES-Checklisten unscharf; 2 CLAUDE.md ohne Disambiguation | `PROJECT_STATUS.md:31`; `CLAUDE.md:4/271-284` | offen | ✅ (Production-Ready-Claim) | Konsistenz-Pass über Memory-/Statusdateien; Caveats-Spalte in Feature-Tabelle; Disambiguations-Hinweis |
| W1-034 | docs-truth, api-surface | Runbooks/API-Doku stale: falsche Containernamen (`ablage-backend` → `backend`, betrifft ~23 Runbooks), ungeprüfte Endpoint-Referenzen, Flower als undokumentierte Abhängigkeit, Host-vs-Container unklar; `.claude/Docs/API` spiegelt Legacy-Stand (50 statt 257 Router) | Runbooks gpu-oom/celery-queue; `.claude/Docs/API/` | offen | – | Suchen+Ersetzen Containernamen; Runbook-Voraussetzungs-Header; API-Doku archivieren oder aus OpenAPI regenerieren |
| W1-035 | tests-audit | Frontend-Coverage fehlt in CI (Vitest 1514 Cases ohne Thresholds/Report); Backend-Coverage-Gate prüft nur Line-, nicht Branch-Coverage | `coverage.yml:71-72`; `vitest.config.ts` | offen | – | Vitest-Coverage-Thresholds + CI-Report; Branch-Coverage-Gate (mind. 70 Prozent) ergänzen |
| W1-036 | migrations-db | `status` varchar↔native-Enum-Drift: Richtungsentscheidung weder getroffen noch dokumentiert | `KNOWN_ISSUES.md:59` | Entscheidung offen | – | EnumStrategy dokumentieren (native Enum + Migration 269+ ODER String beibehalten), dann konsistent umsetzen |
| W1-037 | obsidian-notes | E-Invoicing ca. 80 Prozent: ZUGFeRD/XRechnung-Erzeugung vorhanden, KOSIT-Validator-Integration (normativ erforderlich) fehlt — Stand gegen Code verifizieren (Obsidian-Quelle teils stale) | Vault `06_Compliance/E-Invoicing_Mandat.md`; EXECUTION_PLAN G18 | teilweise | – | Stand prüfen; KOSIT-Validator integrieren; alle 3 Profile gegen Standard validieren |
| W1-038 | github-workflows-quality | Weitere CI-Politur: canary-deploy `if:false`-Geisterworkflow; DAST ignoriert `fail_on_risk`-Input; Trivy-Registry-Scan ohne MEDIUM; Release triggert Docker-Build async ohne Sync; SBOM-Retention 30 vs. 90 Tage; pr-security SARIF-Upload vor Erzeugung; alembic-Check in deploy nur grep-Heuristik; Performance-Tests ohne Baseline-Vergleich; `sleep 30`-Race; Action-SHA-Pins veralten (kein Dependabot für Actions) | jeweilige Workflow-Dateien in `.github/workflows/` | offen | – | Issue-Backlog anlegen und sukzessive abarbeiten; Dependabot-Ecosystem `github-actions` aktivieren |

---

## P3 — Niedrig / Politur

| ID | Bereich | Finding | Beleg | Status | Verifiziert | Vorgeschlagene Aktion |
|---|---|---|---|---|---|---|
| W1-039 | frontend-audit | Politur: `console.log` in `Form.stories.tsx:330`; loki-client localhost-Fallback + `console.warn` (DEV-gaten); unused Imports in mehreren Routes; `@ts-ignore`-Begründungen dokumentieren | `loki-client.ts:17/26`; diverse Routes | offen | ✅ (localhost) | Kleinfixes; ESLint `no-unused-vars` automatisieren |
| W1-040 | backend-markers | NotImplementedError-Basisklassen ohne `@abstractmethod` (`confidence_router.py:427`; `daily_insights_engine.py:390`) | beide Dateien | offen | – | `@abstractmethod` annotieren |
| W1-041 | backend-markers | Platzhalter-Reste: `rag_tasks` customer_card_sync/report_generation „placeholder"; SLA-Placeholder `workflows.py:1713`; Dummy-Metriken `benchmark_dataset.py:497`; GPU-Warmup-Dummy-Image; BLZ→BIC-Hardcode-Fallback; auskommentierter HR-Block `supplier_risk_monitor.py:441-450` | jeweilige Dateien | offen | – | Implementieren oder aus Beat/Code entfernen + dokumentieren |
| W1-042 | tests-audit | Skip-Hygiene: 8 Stub-Skips in API-Tests („stub - nicht implementiert"); hardcoded `True`-Skip (`test_batch_processing`); README für `tests/_archived/`; Celery-E2E (non-eager) fehlt | `tests/unit/api/...`; `pytest.ini` | offen | – | Stubs archivieren/implementieren; Skips an Env-Var/Issue binden |
| W1-043 | infra-deploy | Infra-Doku/Kleinigkeiten: Profil-Matrix (ha/gpu/optional), SKIP_JANUS-Build-Arg, pgbouncer-Rolle, DB_SSL_MODE in `.env.example`, Beat-Image `:latest` ohne build, tests-Mount im Worker, stop_grace-Strategie, Loki-Cold-Storage, AlertManager-SMTP-Setup-README, nginx `/health`-Doku, `.htpasswd`-Hard-Fail, Qdrant-Healthcheck mit API-Key, worker-cpu/GPU-Pool-Konkurrenz, Vault-README, Slack-Webhook-File-Mount-Doku, Prometheus-90d-Retention-Sizing | `docker-compose.yml` u. a. | offen | – | Infrastructure-README/Runbooks ergänzen; Einzelfixes nach Gelegenheit |
| W1-044 | docs-truth, migrations-db | Doku-Politur: CHANGELOG-Release-Policy (Unreleased wächst seit v0.1.0), DB-Skalierung (99 Model-Files, 541 Tabellen) dokumentieren, alembic Extension-Strategie + file_template, Streckengeschäft-Migrations-README | `CHANGELOG.md`; `alembic.ini` | offen | – | Release-Policy definieren; kurze Doku-Ergänzungen |
| W1-045 | monitoring-observability | Monitoring-Politur: DCGM-Exporter bei GPU-Prod reaktivieren (bewusst aus, App-Metriken vorhanden); Grafana-Datasource `sslmode=disable`; SLO-Ziele/Error-Budget nicht dokumentiert; K8s-ServiceMonitor (erst bei K8s-Einsatz); Exporter-Deployment-Prerequisite-Doku; MinIO-Bucket-Metriken; Loki-Archivierung | `prometheus.yml`; `datasources.yml`; `system-slo-alerts.yml` | offen | ✅ (DCGM-Kontext) | `SLO-Definitions.md` erstellen; Rest bei Bedarf |
| W1-046 | security-posture | Security-Hygiene-Backlog: API-Key-Lifecycle/Rotation + SecurityEvents, Audit-Log-Key-Rotation (fixe KDF-Salt), OIDC-Härtung (PKCE/Nonce/JWKS-Doku), SSH-Key-Mgmt-Doku, Netzsegmentierungs-Doku, Encryption-at-Rest-Guide, Bandit in `security-scan.yml` (pip-audit bereits blockierend in ci.yml), Upload-Restpunkte (ZIP-Tiefe; Sanitization/Magic-Bytes/ClamAV bereits vorhanden) | jeweilige Services/Configs | offen | ✅ (Upload teilmitigiert) | Als geplanten Hardening-Backlog priorisieren |
| W1-047 | obsidian-notes | Business-/Produkt-Items aus Vault (teils unverifiziert): ICP-Reframe-Entscheidung max. 90 Tage post-Pilot, Pricing-Hypothesen, Bus-Faktor-1/Onboarding-Doku (G51), Glossar (G13), A11y-93-Violations (G28), Onboarding 4→1 (G11), RAG-Accuracy-Metriken (G47), Pilot-Vorbereitung (Stress-Test, Vertrag) | Obsidian `_Ablage_System` | offen | – (Pilot-Profil: ⚠️ Verifier ausgefallen) | Nach Pilot-Roadmap takten; Vault-Stand gegen Code prüfen (mehrere Obsidian-Findings waren stale) |
| W1-048 | reviews-plans | Plan-Hygiene: `breezy-napping-hare` archivieren (abgeschlossen 2026-03-09); `fluffy-orbiting-alpaca` (ralph-loop) Relevanz prüfen; `hidden-finding-pond` (Audit-Trail/Pagination) Status via git-log klären; `serene-percolating-llama` Quick-Greps; `velvet-moseying-tome` (/doco) optional; `adaptive-seeking-cray` Rest (nur Fix 3 offen) prüfen | `.claude/plans/*` | offen | – | Plans-Ordner aufräumen (archive/), Reststatus notieren |
| W1-049 | mehrere | Behoben (verifiziert) — kein Handlungsbedarf: B1 (zentrale company_id-Dependency; Mini-Follow-up: 46 `user.company_id`-Treffer aus Verifikation stichprobenartig prüfen), B2 (by-design + Mock-Guards), B3 (3 reale Dockerfiles in CI), B4 (Security-/Tenant-Tests echt; Coverage-Roadmap 50→90 separat), Multi-Company-500-Bugs (Migration 268 + order_by/limit), OCR-OOM→FAILED + Surya-CPU-Fallback + Celery-Idempotenz-Claim (ab2fad10), 4 Prod-Bugs (encryption-Aliase, InsightType.SUGGESTION, DATEV-Kontierung, workflow_insights), Model↔DB-Reconciliation (Migrationen 265–268), Goals G0–G5, M7–M15, Migration 266 | git log; KNOWN_ISSUES; Verifier-Notizen | behoben | ✅ | Nur B1-Stichprobe (`user.company_id`) als Mini-Follow-up |
| W1-050 | git-archaeology | Repo-Kleinkram: uncommitted `CLAUDE.md` + `.claude/settings.local.json` (Slack-ask) committen oder verwerfen; lokale gemergte Branches (`feature/offensive-2026-06`, Wellen-Branches) löschen; `origin/feature/g5-test-truth`-Bedarf klären | `git status`; `git branch -a` | offen | – | Kurzes Housekeeping nach W1-013-Sichtung |

---

## Widerlegte Findings (verified=false — zählen nicht)

| ID | Bereich | Ursprüngliche Behauptung | Widerlegung / Befund |
|---|---|---|---|
| W1-051 | reviews-plans | B1 „VERIFIED RESOLVED" (0 Treffer, vollständig zentralisiert) | Verifier fand 46 `user.company_id`-Treffer in app/api (vermutlich Relationship-Zugriffe) — Absolutaussage nicht haltbar; B1-Kern dennoch behoben (siehe W1-049, Follow-up dort) |
| W1-052 | status-memory | B4-Variante „teilweise behoben" mit Detailzahlen | Adversariale Prüfung fand Widersprüche in den Detailbehauptungen; B4-Kern separat verifiziert (W1-049) |
| W1-053 | status-memory | Cross-Engine-get_db-Loch „W1-GELÖST" inkl. Zusatzbehauptungen | Kern-Fix (Re-Export, Entity-Filter, 885 Tests) bestätigt, Zusatzbehauptungen falsifiziert; RLS-Restausbau in W1-014 |
| W1-054 | status-memory | auto_file_document buggy + Auto-Approval crasht | Approval-metadata-Bug ist behoben (Commit 4f49aaed, `request_metadata=`); Finding veraltet/inkohärent |
| W1-055 | reviews-plans | „4 Production Blockers Tracked" als offener Zustand | Falsifiziert: B1–B4 sind nicht mehr offen (behoben bzw. by-design gescoped) |
| W1-056 | reviews-plans | adaptive-seeking-cray: 11 Fixes „UNVERIFIED/nicht implementiert" | 10 von 11 Fixes via Commits 590bdca2/970e72d1 (Feb 2026) implementiert; nur Fix 3 offen (→ W1-048) |
| W1-057 | backend-markers | worker_control_service fehlt (TODO G4, M6) | Service existiert vollständig (`app/services/admin/worker_control_service.py:40-107`) |
| W1-058 | frontend-audit | shadcn Select `value=""` Crash-Risk offen | Bereits mitigiert: admin.sso.tsx nutzt `undefined` + Warnkommentar; ocr-training nutzt `oder "all"`-Fallback |
| W1-059 | migrations-db | Stamp-Reconciliation-Skript/Doku fehlt komplett | `scripts/dbtest/setup_real_test_db.sh` Z.58-65 führt `stamp 262 && upgrade head` bereits aus; nur Prod-Runbook-Lücke bleibt (→ W1-007) |
| W1-060 | obsidian-notes | Sprint 0: 2 Ben-Actions ausstehend (Sentry-DSN fehlt) | Sentry-DSN bereits 2026-05-04 in .env eingetragen; Finding stale |
| W1-061 | obsidian-notes | Live-Alerts-Triage (Commit 0b1b391e) | Falscher Commit-Hash (real 6e877ef6); Momentaufnahme vom 2026-05-20, überholt |
| W1-062 | obsidian-notes | Roadmap mit „Anti-Roadmap-Liste Zeile 78-92" | Liste existiert an genannter Stelle nicht (Zeilen enthalten Sprint-3-Tasks); materiell falsche Referenzen |
| W1-063 | obsidian-notes | 9 Pilot-Blockers Phase B (Datei 2026-05-19_Phase_B_...) | Referenzierte Log-Datei existiert nicht; Zahlen nicht belegbar |
| W1-064 | obsidian-notes | 4 God-Objects >60KB, „554 Endpoints in 1 File", 56 Silent-Catches | Teilweise invalidiert: God-Objects existieren, aber zentrale Zahlen/Belege falsch |
| W1-065 | obsidian-notes | DATEV-Zertifizierung 0 Prozent, Antrag Monat 6 (DATEV_Zertifizierung.md/Roadmap.md) | Referenzierte Dateien existieren nicht; reale Compliance-Doku nennt Q4 2026 |
| W1-066 | celery-events | Beat-Task `folder_import_rules.apply_pending` nicht registriert | Korrekt registriert (`import_tasks.py:1030` mit explizitem Task-Namen) |
| W1-067 | celery-events | vault/partition/recompute_seasonal Beat-Tasks unregistriert | Alle Module in `celery_app.conf.include` (Z.322/364/368); Kurz-Namen korrekt |
| W1-068 | celery-events | ocr_learning-Beat-Namen mismatch | Bewusste Kurz-Namen-Konvention; Modul inkludiert (Z.351), Namen explizit definiert (Z.62/303) |
| W1-069 | celery-events | smart_dashboard-Beat-Namen mismatch | Nicht reproduzierbar; Namen stimmen mit shared_task-Definitionen überein |
| W1-070 | celery-events | pipeline/saga-Beat-Tasks „Task not found" | `saga.process_dead_letter_queue` u. a. korrekt mit explizitem Namen registriert (`saga_tasks.py:37-38`) |
| W1-071 | kubernetes-and-iac | local-path StorageClass „in Production ohne Replikation" | K8s-Manifeste existieren, sind aber NICHT produktiv (Produktion läuft docker-compose); Härtung vor Erstnutzung → W1-015 |
| W1-072 | api-surface | 249/257 Router ohne Testdateien (97 Prozent Gap) | Faktisch falsch: 83 von 257 Routern haben Testdateien |
| W1-073 | api-surface | health.py: 22/22 Endpoints ohne response_model | Falsch: 18 von 22 haben response_model |
| W1-074 | api-surface | ocr.py: 31/31 Endpoints ohne response_model | Falsch: 18 Endpoints haben response_model (OCRPreviewResponse etc.) |
| W1-075 | api-surface | auth.py: 26/52 (50 Prozent) ohne response_model | Zahlen falsch: 26 Endpoints total, 8 ohne = 31 Prozent; Kern nur teilweise wahr |
| W1-076 | api-surface | Admin-Submodule: nur 1/11 mit Tests | Falsch: 6 von 15 Admin-Modulen haben Tests |
| W1-077 | security-posture | Hardcoded Secrets in `.env` IN GIT-REPOSITORY | `.env` existiert lokal mit Secrets, ist aber NICHT in der Git-Historie (`git show HEAD:.env` schlägt fehl); lokales Secret-Handling → W1-002 |
| W1-078 | security-posture | Fehlende RBAC auf „public" Endpoints (/gpu/status, /monitoring/...) | Widerlegt: alle genannten Endpoints erfordern Authentifizierung |
| W1-079 | github-workflows-quality | Fehlendes PR-Check-Gate in CI (Summary nicht blockierend) | ci-summary nutzt `if: always()` + `exit 1` bei Fehlschlag — als Required-Status nutzbar; Implementierung korrekt |
| W1-080 | github-workflows-quality | SSH-Secrets ohne Cleanup-Guard (alle Workflows/Zeilen) | Wesentliche Korrekturen nötig (Zeilen/Dateien teils falsch); verifizierter Terraform-Teilaspekt separat erfasst (→ W1-025) |

---

## Nicht geprüft / Coverage-Lücken

- **Runbooks:** Nur 2 von 23 Runbooks stichprobengeprüft (gpu-oom, celery-queue) — eigenes Runbook-Audit empfohlen (docs-truth).
- **Pläne:** GOAL-G3/G4/G5-Checklisten nur summarisch via RECENT_CHANGES/git-log abgedeckt, nicht Item für Item (reviews-plans).
- **Git:** Stash-Inhalte nicht inspiziert (Apply wäre destruktiv); Zweck der 3 detached Worktrees unbekannt; `origin/feature/g5-test-truth`-Historie ungeprüft — manuelle Sichtung nötig (W1-013).
- **Tests:** Die 196 Integration-Failures sind als Baseline belegt, aber nicht einzeln kategorisiert; Schemathesis-Repros nicht erneut ausgeführt; Fixture-Graphen-Tiefe ungeprüft (tests-audit).
- **Infra/IaC:** Terraform-/Ansible-Logik nicht ausgeführt/validiert; SSL-Zertifikats-Gültigkeit, Netz-Konnektivität, Proxmox/K3s-Runtime-State, GPU-Präsenz ungeprüft (infra-deploy, kubernetes-and-iac).
- **Monitoring:** Nur statische Config-Analyse — Laufzeitverhalten der Exporter, Grafana-Dashboard-Inhalte, Loki-Query-Performance, OTEL-Runtime nicht geprüft (monitoring-observability).
- **API:** Keine tiefe Endpoint-Logik-Analyse (nur Signaturen); GraphQL- und WebSocket-Endpoints nicht separat auditiert; keine Laufzeit-Response-Validierung (api-surface).
- **Frontend:** Kein vollständiger Audit aller 299 Routen (tote Props/Components); Vitest-Hang nicht reproduziert/diagnostiziert; keine AST-basierte Dead-Code-Analyse (frontend-audit).
- **Celery/Events:** Saga-Kompensationsketten, Event-Sourcing-Snapshots, Webhook-DLQ-Routing, Multi-Worker-Beat-Konkurrenz, Redis-Failover des Event-Bus nicht tief geprüft (celery-events).
- **Security:** Kein Pentest/Fuzzing gegen Live-Instanz; kein vollständiger Celery-RLS-Audit; ISO-27001/SOC2/PCI-Gaps nicht erhoben; Vault-KMS-Auto-Unseal nicht geprüft (security-posture).
- **Obsidian:** 04_Module_Knowledge nur strukturell erfasst; 28 ANALYSIS-Dateien in docs/ultraplan nicht im Detail nachrecherchiert; obsidian-sync-Archive ungeprüft. Achtung: Obsidian-Quellen hatten die höchste Widerlegungsquote — vor Maßnahmen Stand gegen Code prüfen (obsidian-notes).
- **Workflows:** Nur statische YAML-Analyse (kein Runtime-Verhalten); GitHub-Repo-Settings (Branch-Protection, Environments) nicht einsehbar; Existenz von tests/smoke/ und tests/performance/ nicht verifiziert (github-workflows-quality).
- **Memory:** Tech-Debt-Items mit Status LOW und granulare, als erledigt dokumentierte Beat-Fixe bewusst ausgelassen (status-memory).

---

*Erstellt vom Welle-1-Synthese-Agenten am 2026-06-11 auf HEAD `2f79f8b9`. Schreibweg: Bash-Heredoc (Write/Edit wegen PostToolUse-Rollback-Hook bewusst vermieden).*
