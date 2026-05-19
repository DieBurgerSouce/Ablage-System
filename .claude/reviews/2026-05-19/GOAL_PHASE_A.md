/goal Phase A — 6 Pilot-Ship Blocker fixen

Ziel: 6 kritische Blocker aus `.claude/reviews/2026-05-19/MASTER_REVIEW_2026-05-19.md` beheben. Branch: sprint-0-pilot-hardening. Pro Fix ein Commit (conventional-commits).

**K3 (5min) — Import-Bug Privat-Router**
`app/api/v1/privat.py:29` ändern: `from app.core.security import build_content_disposition` → `from app.core.security_auth import build_content_disposition` (wie audit_chain.py:28 + compliance_autopilot.py:21 es bereits korrekt machen). Verify: `python -c "from app.api.v1 import privat"` ohne ImportError.

**K4 (30min) — dpia.py Multi-Tenant Bypass**
`app/api/v1/dpia.py` — fünf Endpoints (`get_by_id:294`, `update_status:320`, `add_dpo_consultation:363`, `get_recommendations:403`, `get_audit_trail:424`): (a) im Service-Call `.where(DPIA.company_id == current_user.company_id)` im SELECT statt Post-Fetch-Check; (b) Shortcircuit `if dpia.company_id and ...` zu `if dpia.company_id != current_user.company_id` (ohne `and`) — bei NULL ablehnen statt durchlassen. Test: `tests/unit/api/test_dpia_api.py` neu mit Cross-Tenant + NULL-company_id Cases.

**K5 (15min) — notification_rules.py /test DoS**
`app/api/v1/notification_rules.py:493-513`: Pydantic constrained types auf `conditions` und `event_data` (max_length=10000 für Strings, max_items=100 für Listen, max recursion-depth via custom validator). `operator`/`op` gegen geschlossenes Enum prüfen. `@limiter.limit("30/minute", key_func=get_user_identifier)` Decorator hinzu. Test: malformed deeply-nested payload → 422 statt Worker-Hang.

**K6 (20min) — event_sourcing.py aggregate_type Whitelist**
`app/api/v1/event_sourcing.py` — Zeilen 93-99, 143-148, 184-211: `aggregate_type` als `Literal["document","invoice","entity","payment","contract","dunning"]` typen (oder konstantes Set + 400 bei unknown vor Service-Call). Test: unbekannter Type → 400, kein Reach-Through zum EventStore.

**K2 (1h) — deploy.yml Test-Gate**
`.github/workflows/deploy.yml`: (a) `on: workflow_run: workflows: ["CI"], types: [completed]` als Trigger; (b) erstes Job-Step `if: github.event.workflow_run.conclusion == 'success'` als Guard; (c) `pre-deploy-checks` Stub (Zeile 71) entweder mit echtem Smoke-Curl gegen Health-Endpoints füllen ODER ersatzlos streichen (das `# TODO`-Echo ist gefährlicher als nichts). Verify: PR mit failing test darf nicht deployen können.

**K1 (2-4h) — 20 Alembic Heads konsolidieren**
`alembic heads` ausführen, Output dokumentieren. Für jeden der 19 dangling Heads (alle außer dem Streckengeschäft-Branch mit existierender Merge 090): entweder (a) Merge-Revision erstellen via `alembic merge -m "merge <feature>" <head1> <head2>` oder (b) als bewussten Branch dokumentieren in `alembic/versions/README.md`. Ziel: `alembic heads` gibt nach Konsolidierung **genau 1 head** zurück. Neuer CI-Step in `.github/workflows/ci.yml`: `test -z "$(alembic heads --resolve-dependencies | tail -n +2)"` (fails wenn >1 head).

**Reihenfolge & Parallelisierung**
Seriell-Vorschlag K3 → K4 → K5 → K6 → K2 → K1 (steigender Aufwand). Parallel-Vorschlag: 4 Coder-Agents (Security-Bundle K3+K4+K5+K6, Infra-CI K2, Migration K1, Tests separat) per Background-Spawn, danach Synthese-Commit.

**Verification (definition of done)**
1. `python -c "from app.api.v1 import privat"` ohne Fehler
2. `pytest tests/unit/api/test_{dpia,notification_rules,event_sourcing}_api.py -v` grün
3. `alembic heads` → 1 Eintrag; `alembic upgrade head` ohne Fehler auf frischer DB
4. CI-Workflow rejected einen PR mit `assert False`-Test bevor deploy.yml triggert
5. CHANGELOG.md `[Unreleased] Fixed`-Eintrag pro Fix
6. Commit-Chain auf `sprint-0-pilot-hardening` 6 Commits, alle pre-commit-hooks grün

**Out of Scope für Phase A** (kommt in Phase B): Rate-Limiting auf die 12 anderen Router, Frontend Logger-Sweep, Pydantic-v2-Codemod, Doc-Formatter-Revert, MFA/Encryption-Tests, GPU-Thermal-Alerts. Diese sind im MASTER_REVIEW priorisiert.
