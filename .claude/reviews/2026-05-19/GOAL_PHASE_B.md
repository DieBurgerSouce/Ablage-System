/goal Phase B — Discipline-Sweep

Ziel: 7 High-Prio Findings aus `.claude/reviews/2026-05-19/MASTER_REVIEW_2026-05-19.md` beheben. Branch: sprint-0-pilot-hardening. Pro Task ein Commit, bei verwandten Aenderungen gebuendelt.

**B1 (2-3h) — Doc-Formatter-Revert**
20 Docs mit Formatter-Schaden, 343 Zeilen Content in ANALYSIS_*.md verloren. `git restore CLAUDE.md README.md PlanRAGAblage.md ANALYSIS_*.md Static_Knowledge/{ADRs/00{2,3,5}*,SOPs/00{4,5}*}.md Dynamic_Knowledge/Learnings/*.md docs/{INFRASTRUCTURE_STATUS,OCR_EVALUATION_2025,PADDLEOCR_COMMERCIAL_INFO,guides/*}.md .claude/ORCHESTRATION_ENTERPRISE_PLAN.md`. `.claude/plan.md` + `breezy-napping-hare.md` selektiv. `.prettierignore` mit `*.md` ODER `proseWrap: preserve` + GFM-Tables aus. DoD: `git diff --stat` 0 Doc-Aenderungen.

**B2 (2-3h) — Frontend Logger-Sweep (71 console.*)**
71 production `console.log/error` ersetzen durch `logger.*` aus `lib/logger.ts`. Liste in `frontend_review.md` H1. ESLint `no-console: ['error']` in `.eslintrc.cjs` (Exception `lib/logger.ts` + `*.stories.tsx`). DoD: `grep -rE "console\.(log|error|warn|debug)" frontend/src --include="*.ts*" | grep -vE "lib/logger|\.stories|\.test"` = 0.

**B3 (3-4h) — Pydantic-v2-Codemod**
73 `class Config:` + 11 `@validator` + 1 `.dict()` in 33 API-Files + 6 Services. `class Config: X=Y` → `model_config=ConfigDict(X=Y)`, `@validator("X")` → `@field_validator("X") @classmethod`, `.dict()` → `.model_dump()`, `each_item=True` in Body-Loop. DoD: `grep -rE "class Config:|@validator\(|\.dict\(\)" app/` = 0; `pytest -W error::DeprecationWarning` Pydantic-clean.

**B4 (2-3h) — Rate-Limit 12 Router**
`@limiter.limit("X/period", key_func=get_user_identifier)` auf: nlq.py (10/min), dlp.py (30/min), audit_chain/event_sourcing/graphql_api/trash/dpia/ai_decisions/notification_rules.py (60/min), compliance_autopilot.prepare_audit_package (2/hour), smart_escalation (30/min), supplier_verification.batch_verify (5/min). Imports + `request: Request` ergaenzen. DoD: AST-Check, jeder Endpoint in den 12 Files mit Decorator.

**B5 (1-2T) — Top-5 fehlende Tests**
`tests/unit/api/test_mfa_api.py` (Setup/Verify/Disable/Backup-Codes), `test_encryption_api.py` (Key-Mgmt, Doc-Encrypt, GDPR Art. 32), `tests/integration/test_gdpr_deletion_e2e.py` (Art. 17: request → 30d → delete → S3-purge → audit → search-leer), `tests/unit/services/test_payment_service.py` (Money-Movement, IBAN-PII), `tests/integration/test_document_ingestion_pipeline.py` (upload → OCR → embed → vector → tenant-Search). DoD: alle gruen, >=10 Tests each, Cross-Tenant.

**B6 (30min) — GPU-Thermal-Alerts reaktivieren**
`infrastructure/prometheus/ocr-alerts.yml:210-252` — `GPUTemperatureHigh`, `GPUThermalThrottling`, `GPUTemperatureCritical`, `GPUPowerLimitReached` entkommentieren. Disable-Grund "dcgm-exporter not installed" ist falsch — laeuft seit `docker-compose.yml:1482`. DoD: `curl -s localhost:9090/api/v1/rules | jq '..|.name? | select(startswith("GPU"))'` listet 4.

**B7 (1h) — Mutable Image-Tags pinnen**
15+ Action-Refs (`@v3/@v4/@v5` ohne SHA), `edoburu/pgbouncer:latest` (`docker-compose.yml:82`), `:latest` fuer minio/ollama/grafana/prometheus in `docker-compose.airgap.yml`. SHAs via `gh api /repos/<owner>/<action>/git/refs/tags/<tag>` + `docker inspect --format='{{.RepoDigests}}'`. DoD: keine Mutable-Tags in `.github/workflows/*.yml` und `docker-compose*.yml`.

**Reihenfolge**
B1+B6 zuerst (low-risk). B2+B3 parallel (2 Coder auf verschiedene Files). B4+B7 parallel. B5 zuletzt. Optional 4-Coder-Background-Swarm + Synthese.

**DoD**: 0 unbeabsichtigte Doc-Aenderungen | pytest Pydantic-clean | 0 `console.*` in Prod-Frontend | 12 Router mit `@limiter.limit` | >=50 neue Tests gruen | 4 GPU-Alerts aktiv | keine Mutable-Tags | CHANGELOG-Eintraege

**Out of Scope (Phase C+)**: `as any` 305→0, Dict[str,Any]→TypedDicts, i18n-Entscheidung, 22 Refactor-Kandidaten >1500 LOC, Backup-Encryption, RAG-Spec-Abschluss, Sprint-1 Auth-Haertung.
