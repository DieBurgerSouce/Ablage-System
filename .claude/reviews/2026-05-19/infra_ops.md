# Infra & Ops Review

Scope: docker-compose stack, 17 GitHub workflows, Prometheus rules, alembic migration graph, Sentry/Loki/Jaeger wiring. Branch: `sprint-0-pilot-hardening`.

## Containers

**Strengths.** Main `docker-compose.yml` (1676 lines, ~22 services) is well-hardened: every service has `security_opt: no-new-privileges:true`, explicit `deploy.resources.limits/reservations`, `healthcheck`, `stop_grace_period`, JSON-file logging with rotation (`max-size`/`max-file`). Secrets use `${VAR:?error}` form (fails fast on missing), never hardcoded. Production-facing ports are bound to `127.0.0.1:` (postgres, redis, minio, qdrant, prometheus, grafana). Backend runs as non-root (`user: "1000:1000"`), `read_only: true`, tmpfs for `/tmp` and `/app/cache`. Postgres has SSL forced on, pg_hba.conf mounted. Redis has `--requirepass` enforced. Qdrant API-Key required (no anonymous start).

**Findings.**
- **HIGH: `edoburu/pgbouncer:latest`** (line 82) — mutable tag in critical data-path container. Pin to a digest or semver tag.
- **HIGH: `docker-compose.airgap.yml`** uses `:latest` for `minio`, `ollama`, `grafana`, `prometheus` (lines 287, 319, 352, 385). Airgap deployments need reproducible images by definition; this is incompatible with offline operation.
- **MEDIUM:** No image is pinned by SHA256 digest anywhere — only by version tag (e.g. `redis:7-alpine`, `prom/prometheus:v2.54.0`). Tags are mutable; supply-chain integrity for an on-prem product would benefit from `image: redis@sha256:...`.
- **MEDIUM:** PostgreSQL `entrypoint` copies SSL cert/key from `/tmp/ssl` to `/var/lib/postgresql` at every start. Cert file mounts already require `:ro` host files; this copy step is fragile (fails silently if cert files missing). Consider `command:` only, with certs mounted directly.
- **LOW:** `redis_exporter` has `healthcheck: disable: true` (line 1365) — acceptable per inline comment but it means Prometheus scrape status is the only liveness signal.
- **LOW:** Sentinel HA profile and Postgres replication (`--max_wal_senders=3`) are scaffolded but commented out / off by default.

## CI/CD

**17 workflows.** Action pinning is excellent: nearly every `uses:` is SHA-pinned with a version comment (e.g. `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2`, `aquasecurity/trivy-action@76071ef...# v0.31.0`).

**Findings — mutable tags still present in `uses:`:**
- `actions/setup-node@v4` (e2e.yml:81)
- `actions/setup-qemu-action@v3` (docker-build.yml:58)
- `docker/login-action@v3` (docker-build.yml:65/134/188/230, docker.yml:49)
- `docker/metadata-action@v5` (multiple)
- `anchore/sbom-action@v0` (docker-build.yml:97)
- `azure/setup-helm@v3`, `hashicorp/setup-terraform@v3`, `peter-evans/create-pull-request@v6`, `softprops/action-gh-release@v1`, `slackapi/slack-github-action@v1.25.0`, `actions/github-script@v7`, `actions/create-release@v1`, `actions/download-artifact@v4`, `grafana/setup-k6-action@v1`, `yannh/kubeconform-action@v0.6.0`, `controlplaneio/kubesec-action@v0.0.2`, `aquasecurity/tfsec-action@v1.0.3`, `zaproxy/action-api-scan@v0.9.0`.

These are 15+ mutable references on a codebase that otherwise enforced SHA pinning — the policy is inconsistent.

**Workflow service containers** still pin `postgres:16-alpine` and `redis:7-alpine` by tag (CI, e2e, performance, backup-restore-test). One outlier: `ci.yml:238` uses `minio/minio:latest` for integration tests (the production compose pins to a release date).

**Test/Deploy gating — CRITICAL.**
- `deploy.yml` has NO dependency on `ci.yml`. There is no `workflow_run`, no required-status-check enforcement visible in the workflow. The `pre-deploy-checks` job at line 71 contains `echo "Running pre-deployment smoke tests..."` followed by `# Add actual smoke test commands here` — i.e. an empty stub. The only gate to production is `environment: production-approval` (GitHub Environment), which is configured in repo settings, not in code. Tests can fail and deploy can still proceed if a human approves.
- `deploy-staging.continue-on-error: true` for post-deployment smoke tests (line 136). Production sets `continue-on-error: false`, which is correct, but the staging→production promotion path therefore tolerates staging smoke-test failures.
- Production deploy at line 260 uses `--scale backend=2` then immediately `--scale backend=1` — this is presented as "Blue-Green" but is just rolling within `docker-compose`. Real blue/green would need separate compose projects or k8s.

**Artifact retention.** Good: CI artifacts 30 days, security-scan SBOMs 90 days.

**Secrets.** All deploy secrets use `${{ secrets.* }}` correctly. SSH key written to `~/.ssh/staging_key`, cleaned up in `if: always()` block.

## Monitoring & Alerting

**Disabled alert rules found.** The recent "Slack-Spam-Sweep" commit removed two; the codebase also has more:

| File | Disabled alert | Reason | Status |
|------|----------------|--------|--------|
| `backup-alerts.yml:84-93` | `BackupEncryptionDisabled` | Encryption feature not yet implemented (Sprint-0 G06) | Stale until backend ships |
| `redis-alerts.yml:148-157` | `RedisReplicationBroken` | Single-node Redis in compose | Should re-enable when HA profile becomes default |
| `ocr-alerts.yml:210-252` | `GPUTemperatureHigh`, `GPUThermalThrottling`, `GPUTemperatureCritical`, `GPUPowerLimitReached` | "dcgm-exporter not installed" | **WRONG** — `docker-compose.yml:1482` runs `nvidia/dcgm-exporter:3.3.0-3.2.0-ubuntu22.04`. The DCGM exporter is in the stack; these alerts can and should be re-enabled. |

The OCR GPU thermal alerts being disabled is a real safety gap: 4 GPU rules dormant on a system whose entire OCR throughput depends on an RTX 4080.

## Migrations

**261 migrations under `alembic/versions/`. The migration graph has 20 heads.** Programmatic enumeration of `revision`/`down_revision`:

```
014_add_email_verification, 021, 054, 066, 074, 089,
100_slack_integration, 111_add_delegation_tables, 115,
137_add_gobd_compliance_checks, 147_add_document_lineage,
151_gobd_immutable, 203_add_psd2_banking_integration,
208_add_notification_templates, 211_rls_coverage_audit, 213,
261, streckengeschaeft_002, streckengeschaeft_003, streckengeschaeft_004
```

`alembic upgrade head` will fail with "Multiple head revisions are present" unless `heads` is invoked or merges are created. The Streckengeschäft branch appears intentional (parallel feature work) and a merge revision `090_merge_lexware_streckengeschaeft.py` exists — but 19 other heads suggest dangling intermediate revisions that were never reconnected. This is a CI/deployment landmine: `deploy.yml:120` runs `alembic upgrade head` unguarded.

**Most recent 5 (by leading number):** `261_add_query_performance_indexes`, `260_add_domain_constraints`, `259_seed_default_roles`, `258_add_missing_indexes`, `257_add_missing_constraints`. Linear chain 257→261 is intact and dated 2026-03-09.

**Recommendation:** Run `alembic heads` in CI and fail the build if `count > 1`. Create merge revisions for the 19 dangling heads or document why each is a deliberate branch.

## Observability (Sentry, Loki, Jaeger)

**Sentry.** Wired correctly. `app/main.py:71-77`:

```python
try:
    from infrastructure.sentry.init_sentry import initialize_sentry_for_backend
    initialize_sentry_for_backend()
    logger.info("sentry_initialized")
except Exception as e:
    logger.warning("sentry_not_configured", **safe_error_log(e))
```

`docker-compose.yml:550-555` passes `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE` (0.1), `SENTRY_PROFILES_SAMPLE_RATE` (0.1), `SENTRY_ENABLE_TRACING`, `ENVIRONMENT`, `VERSION`. `init_sentry.py` reads them from `os.getenv`. The recent commit `20c9bb1b` fixed the `ModuleNotFoundError` by mounting `./infrastructure:/app/infrastructure:ro` (line 613). Defaults are sane (10% trace/profile sample). Empty `SENTRY_DSN` cleanly disables — the `try/except` makes that a `warning`, not a startup failure.

**Loki.** `grafana/loki:3.2.0` (1167), bound to 127.0.0.1:3100, paired with `grafana/promtail:3.2.0` (1388). Healthcheck on `/ready`, 2G memory limit. Monitoring-network only.

**Jaeger.** `jaegertracing/all-in-one:1.53` (1265). OTLP gRPC (4317) and HTTP (4318) exposed, Badger persistent storage (`BADGER_EPHEMERAL: "false"`). Backend `OTLP_ENDPOINT=jaeger:4317` and `TRACING_ENABLED=true` by default — tracing is live.

## Summary

The runtime stack is one of the more disciplined on-prem Docker Compose setups I've audited: pervasive resource limits, no-new-privileges, healthchecks, secret-mandatory env vars, localhost-bound ports. Sentry/Loki/Jaeger are wired through and the recent Sprint-0 fixes (mount `infrastructure/`, asyncpg sslmode, dcgm-exporter image) are sound.

The audit surfaces five risks worth fixing this sprint, in priority order:

1. **CRITICAL — 20 alembic heads.** `alembic upgrade head` is unsafe; deploy.yml runs it unguarded. Add `alembic heads | wc -l == 1` check to CI; create merge revisions.
2. **CRITICAL — Deploy decoupled from CI.** `deploy.yml` has no required-tests dependency. `pre-deploy-checks` smoke-test step is a `# TODO` echo. Either gate via `workflow_run: workflows: [CI]` + `conclusion == success`, or enforce branch protection "required status checks" in repo settings and document it.
3. **HIGH — GPU thermal alerts disabled despite DCGM exporter running.** Re-enable the 4 alerts in `ocr-alerts.yml:210-252`; the comment justifying the disable is stale.
4. **HIGH — Mutable image tags.** `edoburu/pgbouncer:latest` in prod compose; `:latest` for minio/ollama/grafana/prometheus in airgap compose; 15+ `@v3/@v4` action refs in workflows. Pin everything to digest or full semver.
5. **MEDIUM — Backup encryption.** `BackupEncryptionDisabled` alert is disabled because the feature is unbuilt. Track Sprint-0 G06 to completion or remove the metric entirely.

Sentry, Loki, Jaeger and Prometheus are healthy. Containers are hardened. The two real failure modes left in this stack are migration drift and the absence of a code-enforced test→deploy gate.
