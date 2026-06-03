# Recent Changes

## 2026-06-03
- **chore(config)**: FINTS_ALLOW_MOCK_SYNC + FINTS_AUTO_SYNC_ENABLED Flags in app/core/config.py (beide Default False, G0-Prereq)
- **chore(infra)**: asn1crypto==1.5.1 in requirements.txt gepinnt (RFC-3161-TSA, tsa_service.py)
- **docs(env)**: .env.example BANKING/FinTS-Sektion ergaenzt (PSD2-Konfigurationsvariablen)
- **docs(reviews)**: Interface-Kontrakt G1<->G4 (Dashboard-KPIs M1-M4, Fraud-Alert-Persistenz M5, Celery-Restart-Hook M6)
- **chore(config)**: .claude/CLAUDE.md Status-Header auf 🟡 korrigiert (vormals ueberschaetzt als Production-Ready)
- **chore(config)**: memory/KNOWN_ISSUES.md um 4 verifizierte Blocker B1-B4 ergaenzt (Status-Scan 2026-06-03)
- **chore(config)**: memory/PROJECT_STATUS.md Reality-Check-Sektion (A-Z-Fan-Out-Scan, 12 Subagents)
- **chore(config)**: memory/TECHNICAL_DEBT.md Debt-Level von LOW auf MITTEL-HOCH korrigiert
- **ci(g2)**: Alle 17 Workflows Branch-Trigger `main` → `master` (Gates feuerten real nie); B3-Blocker behoben
- **ci(g2)**: ci.yml/docker.yml/docker-build.yml/dependencies.yml bauen aus 3 realen Dockerfiles (Root-`Dockerfile`, `frontend/Dockerfile`, `docker/Dockerfile.worker`)
- **ci(g2)**: `pip-audit` blockierend in ci.yml + dependencies.yml (ersetzt `safety … || true`); JSON-Report-Artefakt bleibt
- **ci(g2)**: `.secrets.baseline` als gültige detect-secrets-1.4.0-Baseline neu erzeugt (vormals leeres `{}`)
- **ci(g2)**: dependabot.yml docker-Ecosystem für `/`, `/frontend`, `/docker`; toter `python-dependencies`-Job entfernt
- **ci(g2)**: `docker-compose.dev.yml` ohne `target: development`; `deploy.yml` Pfad `alembic/versions`; `canary-deploy.yml` deaktiviert (`if: false`)
- **ci(g2)**: `.releaserc.json` Release-Branch `main` → `master`; manuelles `release.yml` als Release-Mechanismus gewählt
- **chore(security/g2)**: `browser-diagnostics/` (21 MB) untrackt + `.gitignore` — 73 abgelaufene JWTs (kein Auth-Risiko) mit PII; bleibt in History (DSGVO-Voll-Purge separat)
- **chore(g2)**: `.claude/CLAUDE.md` PostgreSQL-Port `:5433` → `:5434` (Hyper-V-Reservierung); `package.json`+`pyproject.toml` Version `1.0.0` → `0.1.0`
- **note(g2)**: ⚠️ Push blockiert — Parallelprozess hat kontaminierten Commit (87ec57e6 + 18 G3-Frontend-Dateien) auf origin/feature/g2-cicd gepusht; saubere lokale Commits liegen bereit, Auflösung an Team (siehe SESSION_LOG)

## 2026-05-20 (Pilot-Ship v0.1.0 — PR #9 Squash-Merge)

- **feat(pilot)**: PR #9 squash-gemerged, Tag `pilot-v0.1.0`, erste produktive Pilot-Version
- **feat(pilot)**: Sprint-0 (G01-G10), Phase A (K1-K6), Phase B (B1-B7), Multi-Agent-Review konsolidiert
- **fix(security)**: 5 CRITICAL + 11 HIGH-Sec gefixt; Merge-Konflikt Option B geloest

## 2026-05-20 (Sprint-1 — Sec-Reste)

- **fix(security)**: `trash.py` Multi-Tenant-Filter + Bulk-DELETE + Audit-Event vor Hard-Delete (S1.1)
- **fix(api)**: `retention_admin.py` `safe_error_detail` Args-Reihenfolge korrigiert (S1.2)
- **fix(security)**: `graphql_api.py` `ALLOWED_FILTER_FIELDS` Whitelist (CWE-89, S1.3)
- **fix(api)**: `nlq.py` `generated_sql` nur fuer Superuser (S1.4)
- **fix(db)**: `InvoiceTracking.entity_id` Column nachgezogen (S1.5/F4)
