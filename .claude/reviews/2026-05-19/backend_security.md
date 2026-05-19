# Backend Security Review

Scope: `app/api/v1/` (14 priority files) + `app/services/` secret scan. Date: 2026-05-19.

## Critical

| File:line | Issue | Fix |
|-----------|-------|-----|
| `app/api/v1/privat.py:29` | `from app.core.security import build_content_disposition` — but `build_content_disposition` is defined in `app/core/security_auth.py:1106`, **not** in the `app/core/security/` package (see `__init__.py`). Likely `ImportError` at module load → entire Privat router unavailable, or runtime `AttributeError` on every PDF/iCal export endpoint. Confirm via `python -c "from app.api.v1 import privat"`. | Change to `from app.core.security_auth import build_content_disposition` (as `audit_chain.py:28` and `compliance_autopilot.py:21` correctly do). |
| `app/api/v1/event_sourcing.py:93-99,143-148,184-211` | **No whitelist for `aggregate_type`** path parameter. Passed straight into `EventStore.get_events/get_event_count` and `ProjectionService.project`. If the service uses it to build SQL/Redis keys without validation, it's an injection vector. Also enables IDOR enumeration of aggregate types across companies (only `company_id` filter applied downstream — trust on dependency). | Add Pydantic `Literal[...]` or in-router whitelist set (e.g. `{"document","invoice","entity",...}`) and reject unknown types with 400 before reaching the service. |
| `app/api/v1/notification_rules.py:493-513` | `POST /test` accepts arbitrary `conditions` + `event_data` JSON and runs them through `RuleConditionMatcher` with **zero size/depth limits and no authorization beyond authenticated user**. A malicious payload (deeply nested, large list, regex-like operator) can DoS the worker. No rate limiting either. | Cap payload size (Pydantic constrained types or `max_length` on dict keys), validate the `operator`/`op` against a closed enum, and add `@limiter.limit("30/minute")`. |
| `app/api/v1/dpia.py:294-318` | `GET /{dpia_id}` — `service.get_by_id(db, dpia_id)` is **not filtered by `company_id` in the query**. Multi-tenant leak window: the row is fetched, then `dpia.company_id != current_user.company_id` is checked in Python. If `company_id` is `None` on the row (legacy data), the check `if dpia.company_id and ...` (line 311) **silently allows access**. Same pattern in `update_status` (320), `add_dpo_consultation` (363), `get_recommendations` (403), `get_audit_trail` (424). | Filter `company_id` in the SELECT (`.where(DPIA.company_id == current_user.company_id)`); change the `if dpia.company_id and ...` short-circuit to `if dpia.company_id != current_user.company_id` (no `and`) so missing company forbids by default. |

## High

| File:line | Issue | Fix |
|-----------|-------|-----|
| `app/api/v1/retention_admin.py:164,263,366` | `safe_error_detail(<str>, e)` — **arguments swapped**. Signature is `safe_error_detail(e: Exception, context: str=...)` (`app/core/safe_errors.py:97`). Calling with `(str, Exception)` raises in the type-checker path or strips PII protection at runtime (the helper does `e.__class__.__name__` on a `str`). | Swap to `safe_error_detail(e, "Fehler beim Abrufen der Retention-Einstellungen")` etc. |
| `app/api/v1/trash.py:244-297` | `DELETE /{document_id}` deletes by `owner_id == current_user.id` but **does not filter by `company_id`**. If a user is moved between companies (or shares a `User` row), they can permanently delete documents they once owned. Hard-delete (`db.delete(doc)`) cascades — no audit chain entry written here. | Add `Document.company_id == current_user.company_id` to the `where`; emit an audit event before `db.delete`. |
| `app/api/v1/trash.py:300-360` | `DELETE /trash` (empty trash) — same missing `company_id` filter; bulk hard-deletes by `owner_id` only. Also iterates `await db.delete(doc)` in a loop instead of `delete(Document).where(...)` bulk — N+1 + transactional risk if it fails midway. | Add company filter, switch to bulk `delete()` statement, wrap in `try/except` with rollback. |
| `app/api/v1/nlq.py:80-143` | NLQ endpoint executes LLM-generated SQL via `NLQOrchestrator`. `sql_sanitizer.py` exists with whitelist (good), but: (1) **no rate limiting** on `/query` or `/query/stream` — costly LLM + DB cycles can be abused; (2) `generated_sql` is returned in the response (line 118), echoing potential injection payloads to attackers for iteration. | Add `@limiter.limit("10/minute")`; gate `generated_sql` field behind a feature flag or admin role; ensure `nlq_orchestrator` calls `SQLSanitizer.sanitize()` (verify path). |
| `app/api/v1/graphql_api.py:266-301` | `_apply_filters` iterates user-supplied `filters: Dict[str, object]` and applies `field.ilike(value)` etc. **No allow-list on filter field names** per entity_type — any column (including PII like `iban`, `vat_id` on `BusinessEntity`, or `password_hash` on `User` if mapped) can be used as a filter predicate, enabling boolean-based field oracle attacks. | Define `ALLOWED_FILTER_FIELDS` whitelist per entity (mirror `ALLOWED_ORDER_FIELDS` at 212-219) and reject unknown keys. |
| `app/api/v1/audit_chain.py:113-117,177-181` | `entry_hash` is logged as `entry_hash[:16] + "..."` (good practice) **but** the full `entry_hash` and `root_hash` echo back in `verify_proof` response (line 224-228). Hashes themselves are not PII but combined with `user_id` allow chain-mapping for an external observer. Minor; review whether responses should require auditor role. | Restrict `POST /verify` to auditor/admin role (currently any authenticated user). |
| `app/api/v1/dlp.py:44-48` | `_get_client_info` reads `request.client.host` and `User-Agent` header truncated to 255 chars, then passes to `dlp_service.log_dlp_event`. If logger/DB writer interpolates `user_agent` into log lines without CRLF stripping, **CRLF injection in audit log** is possible (CWE-117). | Strip `\r\n` from `user_agent` before storage; ensure structured logger doesn't allow raw newlines. |

## Medium

| File:line | Issue | Fix |
|-----------|-------|-----|
| `app/api/v1/ai_decisions.py:144-200` | List endpoint — no `limit` cap on `decision_type` value (free string filter), allowing `LIKE`-style fingerprinting. Also `confidence_min` not bounded server-side beyond Pydantic Query annotation. AuthZ via `company_id` is present (line 165) ✓. | Whitelist `decision_type` against known enum values. |
| `app/api/v1/notification_rules.py:317-331` | `GET /{rule_id}` uses `db.get(NotificationRule, rule_id)` — **no `user_id` filter in query**, only post-fetch check (line 325). IDOR enumeration timing oracle (same row vs missing row both go through `get`). Same pattern in `update_rule`, `delete_rule`, `toggle_rule`, `get_rule_statistics`. | Filter `user_id` in the SELECT or via the engine; return uniform 404 for both. |
| `app/api/v1/event_sourcing.py:209-228` | `get_projection` calls `event_store.get_events(after_sequence=0, ...)` just to fetch `last_sequence` — pulls **all events** for the aggregate into memory. DoS vector for aggregates with millions of events. | Add `event_store.get_last_sequence()` method using `MAX(sequence_number)`. |
| `app/api/v1/compliance_autopilot.py:218-268` | `prepare_audit_package` — **no rate limit**, builds full ZIP of company documents in memory (`io.BytesIO(package.zip_content)`). Authenticated user can request unbounded large archives. | Add `@limiter.limit("2/hour")`; stream the ZIP instead of materializing in memory. |
| `app/api/v1/smart_escalation.py:233-286, 295-327` | No rate limiting on recommendation endpoints; each call runs scoring across all team members (heavy). Also `request.exclude_user_ids` is parsed as `UUID(...)` directly (line 256) — on bad input raises generic `ValueError` → 500 instead of 400. | Add `@limiter.limit("30/minute")`; wrap UUID parsing in try/except → 400. |
| `app/api/v1/supplier_verification.py:269-314` | `batch_verify` allows 50 entities per call; **no rate limit** so a user can iterate 50×N quickly. Each call hits **external** registers (Handelsregister, VIES) — potential cost + IP-ban risk. | Add `@limiter.limit("5/minute")` and per-company daily quota. |
| `app/api/v1/privat.py:382-396` | `create_space` for `SHARED` type reads `X-Company-ID` header via `get_current_company_id()`. Header injection of an arbitrary company UUID currently fine only if downstream validates membership — verify `space_service.create_shared_space` enforces user∈company. (Couldn't confirm from this file.) | Add explicit membership check in router before service call. |
| All 12 priority files (except `privat.py`, `retention_admin.py`) | **No rate limiting decorators**. `nlq`, `dlp`, `audit_chain`, `event_sourcing`, `graphql_api`, `trash`, `dpia`, `ai_decisions`, `compliance_autopilot`, `notification_rules`, `smart_escalation`, `supplier_verification` all unprotected. | Apply `@limiter.limit("60/minute", key_func=get_user_identifier)` baseline; tighter for expensive endpoints (NLQ, audit export, supplier verify). |

## Low

| File:line | Issue | Fix |
|-----------|-------|-----|
| `app/api/v1/dlp.py:344-382` | `/scan` accepts `text` up to 100 000 chars per request — fine, but processes regex over full text without timeout. ReDoS risk if `SensitiveDataType` patterns are not RE2-safe. | Wrap `detect_sensitive_data` in `asyncio.wait_for(..., timeout=2.0)`. |
| `app/api/v1/audit_chain.py:295-358` | `export` endpoint: date range defaults to 30 days, **no upper bound** on `to_date - from_date`. User can request 10-year export → large memory + Merkle tree computation. | Cap range to e.g. 1 year; require admin for longer. |
| `app/services/erp/lexware_connector.py:208`, `app/services/erp/odoo_connector.py:49`, `app/services/calendar/caldav_client.py:87` | String `"your-secret"`, `"your_api_key"`, `"passwort"` — confirmed **docstring examples**, not real secrets. No action needed. | None. |
| `app/services/banking/*.py` (account_connection_service:326, auto_transaction_import_service:434/590, payment_initiation_service:352/466) | `access_token="placeholder"` — placeholders waiting for OAuth integration; commented as such. | None now; track in tech debt. |
| `app/services/gdpr_service.py:280` | `user.hashed_password = "DELETED_GDPR_ART17"` — sentinel value, not a secret. Confirmed intentional. | None. |
| `app/api/v1/trash.py:103,353` | Structured logs include `user_id` and `count` (no PII) — good. | None. |
| `app/api/v1/ai_decisions.py:407-411` | Logs `decision_id`, `feedback_type`, `has_correction` (bool). No PII. | None. |

## Summary table

| Severity | Count | Files most affected |
|----------|-------|----|
| Critical | 4 | `privat.py` (broken import), `event_sourcing.py` (no whitelist), `notification_rules.py` (test DoS), `dpia.py` (multi-tenant bypass) |
| High | 8 | `retention_admin.py` (swapped args), `trash.py` (missing company filter ×2), `nlq.py` (no RL + SQL echo), `graphql_api.py` (filter whitelist), `audit_chain.py` (verify role), `dlp.py` (CRLF) |
| Medium | 8 | `ai_decisions.py`, `notification_rules.py` (IDOR×4), `event_sourcing.py` (mem), `compliance_autopilot.py` (audit ZIP), `smart_escalation.py`, `supplier_verification.py`, `privat.py`, all-files-rate-limit |
| Low | 7 | `dlp.py` ReDoS, `audit_chain.py` date range, services secrets (false positive) |

**Top 3 must-fix before pilot**: (1) `privat.py:29` import error — verify router actually loads; (2) `dpia.py` multi-tenant query filter; (3) `retention_admin.py` swapped `safe_error_detail` args.

**Rate limiting** is the biggest systemic gap: 12 of 14 reviewed routers are unprotected. Recommend a router-level dependency that applies a sensible default unless overridden.

PII logging: no IBAN/VAT-ID/customer numbers found being logged in the reviewed files (good — `safe_error_log` and structlog field discipline are followed). Lexware-specific PII gates are in services, not in these routers.
