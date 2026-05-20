# Test Coverage Review

**Date:** 2026-05-19
**Scope:** Backend (`app/api/v1`, `app/services`, `tests/`)
**Numbers:** 257 API modules / 94 API test files -> ~183 untested API modules (71%). ~235 service files / ~177 service tests -> ~117 untested services (38% of which involve security, banking, or OCR).

---

## Critical Untested Endpoints (Security/Compliance)

Sorted by GDPR/financial/auth blast radius. All endpoints lack `tests/unit/api/test_<name>_api.py`.

| # | Endpoint | Risk | Why it matters |
|---|----------|------|----------------|
| 1 | `mfa.py` | CRITICAL | 2FA setup/verification - account takeover risk without tests |
| 2 | `encryption.py` | CRITICAL | Key management & document encryption (GDPR Art. 32) |
| 3 | `dpia.py` | CRITICAL | Data Protection Impact Assessment (GDPR Art. 35) |
| 4 | `dlp.py` | CRITICAL | Data Loss Prevention - PII leakage path |
| 5 | `consent.py` | CRITICAL | GDPR Art. 7 consent records |
| 6 | `retention_admin.py` | CRITICAL | Retention enforcement (GoBD 10-year + GDPR delete) |
| 7 | `audit_chain.py` / `integrity.py` | HIGH | Tamper-evident chain - silent breaks possible |
| 8 | `cross_tenant_reports.py` | HIGH | Multi-tenant boundary, see CRITICAL RULE Multi-Tenancy |
| 9 | `tenant_rate_limits.py` (admin), `holding.py` | HIGH | Tenant isolation + privilege escalation surfaces |
| 10 | `signatures.py` | HIGH | E-signature legal validity (eIDAS) |
| 11 | `einvoice.py` / `invoice_pipeline.py` | HIGH | XRechnung/ZUGFeRD - tax law (UStG 14) |
| 12 | `datev.py`, `datev_booking.py`, `datev_connect.py` | HIGH | Steuerberater integration - financial accuracy |
| 13 | `gobd_compliance.py` | HIGH | GoBD audit failure -> tax penalty |
| 14 | `fraud.py` | HIGH | Fraud detection bypass = financial loss |
| 15 | `banking_fints.py` / `enhanced_banking.py` / `reconciliation.py` | HIGH | PSD2/SCA flows, payment correctness |
| 16 | `payment_behavior.py` | HIGH | Touches IBAN/BIC (PII per CRITICAL RULE 8) |
| 17 | `push_notifications.py` (service tested, API not) | MEDIUM | Subscription endpoint auth |
| 18 | `odoo_webhooks.py` | MEDIUM | Inbound webhook signature validation |
| 19 | `graphql_api.py` | MEDIUM | Query depth/complexity DoS, field-level authz |
| 20 | `nlq.py` | MEDIUM | SQL sanitizer at boundary (CRITICAL RULE 9) |
| 21 | `presence.py` / `ms_teams.py` / `teams.py` | MEDIUM | Real-time channel auth |
| 22 | `trash.py` | MEDIUM | Soft-delete / GDPR restore boundary |
| 23 | `annotations.py` / `annotations_enhanced.py` / `annotations_extended.py` | MEDIUM | Three near-duplicates - likely auth drift |

---

## High Priority Untested Services

Top 15 by business criticality (no `tests/unit/services/test_<name>.py`):

| # | Service | Domain | Criticality |
|---|---------|--------|-------------|
| 1 | `banking/fints_service.py` + `enhanced_fints_service.py` | Banking | PSD2/SCA |
| 2 | `banking/payment_initiation_service.py` | Banking | Money movement |
| 3 | `banking/payment_automation_service.py` | Banking | Auto-pay rules |
| 4 | `banking/payment_service.py` | Banking | Core payment logic |
| 5 | `banking/auto_reconciliation_service.py` + `smart_reconciliation_service.py` + `reconciliation_service.py` | Banking | Match logic - over/underpayment |
| 6 | `banking/skonto_service.py` | Banking | Documented as Production-Ready, no test |
| 7 | `banking/partial_payment_service.py` | Banking | Teilzahlungen |
| 8 | `permission_audit_service.py` | Security | RBAC drift / privilege creep |
| 9 | `tenant_rate_limit_service.py` | Security | Tenant DoS protection |
| 10 | `chat_sharing_service.py` | Security | Cross-tenant share leak |
| 11 | `coverage_tracking_service.py` | Compliance | Self-referential gap detection |
| 12 | `ocr/formula_extraction_service.py`, `ocr/semantic_validation_service.py` | OCR | Output correctness |
| 13 | `ocr_cache_service.py` (only partial coverage exists), `tune_service.py` | OCR | Cache poisoning / model swap |
| 14 | `contextual_umlaut_restorer.py`, `german_phonetic_matcher.py`, `german_spellchecker.py`, `german_terminology_service.py` | OCR/German | CRITICAL RULE 2 (German correctness) |
| 15 | `backup_restore_test_service.py` | Compliance | Disaster recovery validation |

Also noted (out of top 15 but worth tracking): `document_lifecycle_engine.py`, `document_quality_score_service.py`, `cross_document_intelligence_service.py`, `extraction_confidence_service.py`, `feedback_service.py`, `master_data_hygiene_service.py`, `proactive_assistant_service.py`.

---

## Missing Integration Tests

`tests/integration/` has 56 files. Existing scenarios cover `documents`, `banking_workflow`, `multi_tenant_isolation`, `lexware` (implicit via `document_entity_linker`), `risk_scoring`, `lineage`, `skonto_pipeline`, `einvoice_integration`, `psd2_banking_flow`, `email_import_pipeline`, `dlq_management`, `alembic_migrations`, `rls_context`.

Gaps for the five requested scenarios:

1. **Upload -> OCR -> Index -> Search end-to-end**: NOT covered as one chain. `test_ocr_pipeline_integration.py` and `test_search_workflow.py` exist as silos but never traverse upload -> backend selection -> embedding -> vector index -> search-result with permission filter. **Recommend: `test_document_ingestion_pipeline.py`** (upload PDF -> wait for Celery -> assert pgvector row -> search returns it with correct tenant/owner).
2. **Lexware import -> entity linking**: Lexware has unit tests (`test_lexware_import_service`, `test_document_entity_linker_service`) but no integration test that imports a real CSV, links to existing documents, and verifies `customer_id` propagation under multi-tenant RLS.
3. **E-invoice generation E2E**: `test_einvoice_integration.py` exists but verify it covers XRechnung CIUS validation + Pflichtfelder (Leitweg-ID, BT-10) + signed PDF flow. Currently likely happy-path only - missing invalid VAT/IBAN rejection paths.
4. **GDPR deletion workflow**: `test_gdpr` unit/service tests exist; no integration scenario for full Art. 17 flow: request -> 30-day grace -> cascading delete -> S3 purge -> audit row -> verify search returns 0. **High priority** given CRITICAL RULE 8.
5. **Multi-tenant isolation extended**: `test_multi_tenant_isolation.py` and `test_rls_context.py` exist. Gaps: (a) cross-tenant attack matrix against `cross_tenant_reports`, `holding`, `nlq`, `graphql` endpoints; (b) tenant-scoped MinIO bucket isolation; (c) Redis namespace bleed (cache/queue).

Additional missing integration: webhook outbound retry+DLQ replay, OCR backend failover chain (DeepSeek OOM -> GOT -> Surya CPU), Slack notification deduplication, DATEV Connect token refresh under failure.

---

## Recent Test Quality Assessment

Read 20+ lines of each of the 8 new test files. Overall quality: **good - solid happy-path, gaps in adversarial coverage.**

Strengths (observed in all 8 files):
- Consistent header `# -*- coding: utf-8 -*-` + German docstrings (CRITICAL RULE 2).
- `pytestmark` markers (`unit`, `api`) set correctly.
- Mocks via `AsyncMock`/`Mock` - no real DB/HTTP coupling.
- Pydantic schema validation tested (`test_action_request_invalid_action`).
- Auth-required negative paths included (smart_inbox: "ohne Token -> 401").

Edge cases MISSING per file:
- **test_smart_inbox_api**: No SQL injection in `action` field; no oversize `data` dict (1MB+); no concurrent `act` on same item (idempotency); snooze with past datetime; pagination edge (limit=0, limit=10000).
- **test_spotlight_api**: q max_length tested per docstring but no Unicode-edge (surrogate pairs, RTL); no rate-limit assertion; no cross-tenant query leakage.
- **test_document_export_service**: ZIP/CSV tested but no path-traversal in filename, no zip-bomb defense, no permission denial mid-batch (partial failure rollback), no >100k row CSV streaming.
- **test_document_lifecycle_service**: Stage transitions covered; missing concurrent transition race (two users), SLA boundary (= exact deadline), backward transition rejection.
- **test_embedding_service**: Cache hit/miss covered; missing GPU OOM fallback assertion (CRITICAL RULE 3), poisoned-cache scenario, empty-string input, vector L2-norm sanity.
- **test_push_notification_service**: 5-failure deactivation tested per docstring; missing token-revocation race, broadcast to >1000 users batching, malformed VAPID key.
- **test_spotlight_service**: Partial-failure resilience present; missing timeout per parallel branch, response truncation when total >limit, German-stem matching ("Rechnung" vs "Rechnungen").
- **test_umlaut_validation_service**: Detection/correction tested; missing false positives ("Strasse" as proper noun), Fraktur-OCR artifacts (long-s), mixed-case "STRASSE" -> "STRASSE/STRASSE", performance on 100k-char doc.

Verdict: **acceptable as v1 - add an "edge cases" class to each within next sprint.**

---

## Recommended Test Order

Suggested implementation order (highest ROI first):

1. **`test_mfa_api.py`** + **`test_encryption_api.py`** - account-takeover blocker.
2. **`test_gdpr_deletion_e2e.py`** (integration) - Art. 17 cascading delete.
3. **`test_banking_payment_service.py`** + **`test_fints_service.py`** + **`test_payment_initiation_service.py`** - money movement.
4. **`test_dpia_api.py`** + **`test_consent_api.py`** + **`test_retention_admin_api.py`** - GDPR audit prep.
5. **`test_document_ingestion_pipeline.py`** (integration) - upload->OCR->search.
6. **`test_audit_chain_api.py`** + **`test_integrity_api.py`** - tamper detection.
7. **`test_cross_tenant_attack_matrix.py`** (integration) - hit all admin/holding/nlq endpoints.
8. **`test_einvoice_api.py`** + **`test_gobd_compliance_api.py`** - tax law.
9. **`test_skonto_service.py`** + **`test_partial_payment_service.py`** + **`test_reconciliation_service.py`** - financial logic.
10. **`test_german_*.py`** (phonetic, spellchecker, terminology, umlaut_restorer) - CRITICAL RULE 2.
11. **Edge-case additions** to the 8 new tests (per-file gaps above).
12. **`test_datev_*.py`** trio + **`test_signatures_api.py`** + **`test_dlp_api.py`**.

---

## Summary

Coverage is broad on the documented "Production-Ready" features (~94 API tests, ~177 service tests) but **71% of API modules lack a dedicated unit test**, with the gap concentrated in the highest-risk areas: MFA, encryption, DPIA/DLP/consent, audit chain, banking/FinTS/payments, e-invoicing, DATEV, and cross-tenant admin. Integration suite covers 56 scenarios but lacks the canonical upload->OCR->index->search chain, a full GDPR Art. 17 cascade, and a cross-tenant attack matrix. The 8 newly committed tests are structurally solid (German, mocks, schema validation, auth-401) but uniformly under-cover adversarial inputs (injection, oversize, concurrency, GPU-OOM, German edge cases) - add an `EdgeCases` class to each. Highest-ROI next 5: MFA, encryption, GDPR-deletion E2E, payment-service trio, ingestion-pipeline E2E.
