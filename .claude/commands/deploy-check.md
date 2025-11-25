# Deployment Readiness Check

You are performing a comprehensive pre-deployment check to ensure the application is production-ready.

## Your Task

Run a thorough deployment readiness assessment:

### 1. Code Quality Checks

- [ ] All tests passing (`pytest`)
- [ ] Test coverage >= 80% (`pytest --cov`)
- [ ] Type checking clean (`mypy app/`)
- [ ] Linting clean (`ruff check .`)
- [ ] Formatting consistent (`ruff format --check .`)
- [ ] No security vulnerabilities (`bandit -r app/`)
- [ ] No secrets in code (`detect-secrets scan`)
- [ ] Pre-commit hooks passing

### 2. Database Checks

- [ ] All migrations applied (`alembic current`)
- [ ] No pending migrations
- [ ] Migrations reversible (check downgrade functions)
- [ ] Database backup exists and is recent
- [ ] Connection pooling configured correctly
- [ ] Indexes exist for frequent queries

### 3. Configuration Checks

- [ ] `.env.example` up to date
- [ ] All required environment variables documented
- [ ] No hardcoded secrets or URLs
- [ ] Logging configuration appropriate for production
- [ ] CORS settings restrictive
- [ ] Rate limiting enabled
- [ ] Session security configured (httpOnly, secure cookies)

### 4. Dependencies Checks

- [ ] `requirements.txt` has pinned versions
- [ ] No known vulnerabilities (`pip-audit` or `safety check`)
- [ ] All licenses compatible
- [ ] Docker base images up to date
- [ ] Python version specified in runtime config

### 5. Performance Checks

- [ ] GPU memory limits configured
- [ ] Database connection pooling sized appropriately
- [ ] Redis connection pooling configured
- [ ] Batch sizes optimized for hardware
- [ ] API response times acceptable (< 2s for OCR)
- [ ] No N+1 query problems

### 6. Monitoring & Observability

- [ ] Health check endpoint working (`/health`)
- [ ] Metrics endpoint configured (if applicable)
- [ ] Structured logging in place
- [ ] Error tracking configured
- [ ] Log levels appropriate (INFO, not DEBUG)

### 7. Docker & Infrastructure

- [ ] Docker images build successfully
- [ ] Container health checks defined
- [ ] Resource limits set (CPU, memory)
- [ ] Restart policies configured
- [ ] Volumes for persistent data defined
- [ ] Networks properly configured

### 8. Security Checks

- [ ] HTTPS enforced
- [ ] Authentication working
- [ ] Authorization rules tested
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention
- [ ] CSRF protection enabled
- [ ] Security headers configured

### 9. Documentation

- [ ] README.md up to date
- [ ] DEPLOYMENT.md exists with deployment steps
- [ ] API documentation current
- [ ] Architecture diagrams accurate
- [ ] Runbook for common issues
- [ ] Rollback procedure documented

### 10. Backup & Recovery

- [ ] Database backup strategy in place
- [ ] Backup restoration tested
- [ ] MinIO bucket backup configured
- [ ] Recovery time objective (RTO) documented
- [ ] Recovery point objective (RPO) documented

## Execution

Run all checks and provide:

1. **Summary**: Overall readiness status (Ready/Not Ready)
2. **Passed Checks**: List of successful checks with ✅
3. **Failed Checks**: List of failures with ❌ and remediation steps
4. **Warnings**: Non-blocking issues with ⚠️
5. **Recommendations**: Suggestions for improvement

## Output Format

```markdown
# Deployment Readiness Report

**Status:** ✅ READY / ❌ NOT READY
**Date:** YYYY-MM-DD
**Checked By:** Claude Code

## Summary
- Total Checks: XX
- Passed: XX ✅
- Failed: XX ❌
- Warnings: XX ⚠️

## Details

### ✅ Passed (XX)
- Test coverage: 85%
- ...

### ❌ Failed (XX)
- Migration pending: Run `alembic upgrade head`
- ...

### ⚠️ Warnings (XX)
- Redis connection pool: Consider increasing max connections
- ...

## Recommendations
1. ...
2. ...
```
