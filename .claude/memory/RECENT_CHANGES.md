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
- **feat(g4)**: Backend-Services/Workers/DB-Remediation (M7-M15 + G1-Kontrakt M3/M5/M6), Commit `bd272d80` auf `feature/g4-services-db` (17 Dateien)
- **fix(g4/M9)**: enhanced_fints Mock-Sync hinter FINTS_ALLOW_MOCK_SYNC -> kein Fake-Eingang loest Reconciliation/IncomingPayment aus (Unit-Test gruen)
- **fix(g4/M7-M8)**: auto_transaction_import — PSD2 kein Platzhalter-Token an echte API; FinTS-Auto-Sync OUTSCOPED (BaFin)
- **fix(g4/celery)**: 4 Beat/Route-Renames; refresh_query_suggestions->warm_cache; reactivate_snoozed_items entfernt; 5 Task-Module sichtbar; fints-sync-daily hinter FINTS_AUTO_SYNC_ENABLED
- **fix(g4/M10-M13)**: Fraud/AI-Wahrheit (ApprovalRequest/ApprovalStep/AuditLog; echte Confidence/COUNT-Queries; is_estimated)
- **fix(g4/M14)**: TSA RFC-3161 via asn1crypto (kein Handbau-ASN.1-Fallback)
- **fix(g4/M15)**: GoBD echte company_id-Checks; XL ehrlich WARNING/teilgeprueft statt false PASSED
- **chore(g4/db)**: app/db/all_models.py Aggregator (468 Tabellen); models_collaboration app.db.base->models_base-Fix

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
