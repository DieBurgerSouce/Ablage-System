# Pre-Deployment Checklist
**Ablage-System - Bereitstellungsprüfung**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Purpose: Ensure safe, successful production deployments

---

## Checklist Overview

**Use this checklist before EVERY production deployment.**

- ⏱️ **Estimated Time:** 30-45 minutes
- 🎯 **Success Rate Target:** 100% items checked
- ⚠️ **Abort Deployment if:** Any CRITICAL item fails

**Deployment Types:**
- 🔵 **Standard:** Regular feature/bug fix deployment
- 🟡 **High-Risk:** Database migrations, architecture changes
- 🔴 **Emergency:** Hot-fix for production incident

---

## Section 1: Code Quality (15 minutes)

### 1.1 Tests ✅ CRITICAL
```bash
# Run full test suite
pytest --cov=app --cov-report=term

# Expected results:
# - All tests pass (0 failures)
# - Coverage ≥80%
# - No skipped tests (unless documented)
```

**Checklist:**
- [ ] ✅ All unit tests pass (0 failures)
- [ ] ✅ All integration tests pass
- [ ] ✅ Test coverage ≥80%
- [ ] ⚠️ No tests skipped without documented reason
- [ ] ⚠️ No test warnings or deprecation notices

**If ANY test fails → STOP deployment**

---

### 1.2 Code Quality ✅ CRITICAL
```bash
# Type checking
mypy app/

# Expected: No errors

# Linting
ruff check .

# Expected: No errors
```

**Checklist:**
- [ ] ✅ Type checking passes (`mypy` clean)
- [ ] ✅ Linting passes (`ruff` clean)
- [ ] ⚠️ No `# type: ignore` added without justification
- [ ] ⚠️ No `# noqa` added without justification

---

### 1.3 Code Review ✅ CRITICAL
**Checklist:**
- [ ] ✅ Pull request approved by ≥2 reviewers
- [ ] ✅ All review comments addressed
- [ ] ⚠️ CI/CD pipeline green (all checks pass)
- [ ] ⚠️ No merge conflicts
- [ ] ⚠️ Branch up-to-date with main

**If not approved → STOP deployment**

---

## Section 2: Security & Compliance (10 minutes)

### 2.1 Security Scan ✅ CRITICAL
```bash
# Dependency vulnerabilities
pip-audit --format json

# Docker image scan
trivy image --severity CRITICAL,HIGH ablage-backend:latest
```

**Checklist:**
- [ ] ✅ Zero CRITICAL vulnerabilities
- [ ] ⚠️ HIGH vulnerabilities documented and accepted
- [ ] ⚠️ No secrets in code (API keys, passwords, tokens)
- [ ] ⚠️ No hardcoded credentials
- [ ] ⚠️ Environment variables updated in .env.example

**Tool: Check for secrets**
```bash
# Scan for secrets
git secrets --scan

# Or use gitleaks
gitleaks detect --source . --verbose
```

---

### 2.2 GDPR Compliance (if applicable)
**Checklist:**
- [ ] ⚠️ No new PII collection without legal review
- [ ] ⚠️ Data retention policies respected
- [ ] ⚠️ Audit logging for sensitive operations
- [ ] ⚠️ Privacy impact assessment (if required)

---

## Section 3: Database Changes (15 minutes)

### 3.1 Migrations ✅ CRITICAL (if applicable)

**⚠️ SKIP if no database changes**

```bash
# Check for new migrations
alembic current
alembic heads

# Review migration SQL
alembic upgrade head --sql > /tmp/migration_$(date +%F).sql
cat /tmp/migration_$(date +%F).sql
```

**Checklist:**
- [ ] ✅ Migration tested on staging database
- [ ] ✅ Migration SQL reviewed (no destructive operations)
- [ ] ✅ Rollback migration created and tested
- [ ] ⚠️ Estimated migration time documented (<5 min preferred)
- [ ] ⚠️ Downtime required? (Yes/No) → If Yes, notify users
- [ ] ⚠️ Large table migrations (<10M rows) tested for performance
- [ ] ⚠️ Indexes created with `CONCURRENTLY` (no locks)

**Migration Risk Assessment:**
```markdown
Migration Type: [ADD COLUMN / ALTER TABLE / DROP COLUMN / etc.]
Affected Table: [table_name]
Table Size: [X rows, Y GB]
Estimated Time: [X minutes]
Requires Downtime: [YES/NO]
Rollback Plan: [describe]
```

**If migration time >10 minutes → Schedule maintenance window**

---

### 3.2 Data Integrity
**Checklist:**
- [ ] ✅ Backup taken before deployment
- [ ] ⚠️ Foreign key constraints validated
- [ ] ⚠️ Data migration script (if needed) tested on staging
- [ ] ⚠️ No data loss in migration

---

## Section 4: Infrastructure Readiness (10 minutes)

### 4.1 Environment Configuration
```bash
# Verify environment variables
docker-compose config

# Check for missing variables
diff .env.example .env
```

**Checklist:**
- [ ] ✅ All required environment variables set
- [ ] ⚠️ `.env` file not committed to git
- [ ] ⚠️ Production secrets rotated (if changed)
- [ ] ⚠️ SSL certificates valid (>30 days remaining)

**Check SSL expiration:**
```bash
echo | openssl s_client -connect ablage.company.com:443 2>/dev/null | \
  openssl x509 -noout -enddate
```

---

### 4.2 Resource Capacity
```bash
# Check current resource usage
df -h  # Disk space
free -h  # Memory
nvidia-smi  # GPU

# Check logs don't fill disk
du -sh /var/log/
```

**Checklist:**
- [ ] ✅ Disk space >20% free
- [ ] ✅ Memory usage <80%
- [ ] ⚠️ GPU memory <70% (idle state)
- [ ] ⚠️ Log rotation configured
- [ ] ⚠️ /tmp directory cleaned (<5GB)

**If disk space <20% → Clean up before deployment**

---

### 4.3 Backup Verification
```bash
# Verify recent backup exists
ls -lh /mnt/backups/ | tail -5

# Check backup age
latest_backup=$(ls -t /mnt/backups/ablage_backup_*.tar.gz | head -1)
backup_age_hours=$(( ($(date +%s) - $(stat -c %Y "$latest_backup")) / 3600 ))
echo "Backup age: ${backup_age_hours} hours"
```

**Checklist:**
- [ ] ✅ Backup exists from last 24 hours
- [ ] ✅ Backup size reasonable (not 0 bytes, not 10x normal)
- [ ] ⚠️ Backup tested (restoration drill passed)
- [ ] ⚠️ Offsite backup verified

**If backup >24 hours old → Create fresh backup first**

---

## Section 5: Monitoring & Alerting (5 minutes)

### 5.1 Monitoring Setup
**Checklist:**
- [ ] ⚠️ Monitoring dashboards accessible
- [ ] ⚠️ Alert rules configured for new features
- [ ] ⚠️ On-call engineer identified and notified
- [ ] ⚠️ Runbooks updated (if new failure modes introduced)

---

### 5.2 Health Checks
```bash
# Verify health check endpoint working
curl -s http://staging.ablage.company.com/health | jq

# Expected: {"status": "healthy", "checks": {...}}
```

**Checklist:**
- [ ] ✅ Health check endpoint returns 200 OK
- [ ] ⚠️ All health check components passing
- [ ] ⚠️ Health check includes new dependencies (if added)

---

## Section 6: Documentation (5 minutes)

### 6.1 Deployment Documentation
**Checklist:**
- [ ] ⚠️ CHANGELOG.md updated
- [ ] ⚠️ API documentation regenerated (if API changes)
- [ ] ⚠️ Runbooks updated (if operational changes)
- [ ] ⚠️ Architecture diagrams updated (if architecture changes)

---

### 6.2 Communication
**Checklist:**
- [ ] ⚠️ Deployment announcement sent to team
- [ ] ⚠️ Users notified (if user-facing changes)
- [ ] ⚠️ Stakeholders informed (if high-risk deployment)
- [ ] ⚠️ Rollback plan documented and shared

**Deployment Announcement Template:**
```markdown
📢 **Deployment Notification**

**Date/Time:** [YYYY-MM-DD HH:MM CET]
**Duration:** [Estimated deployment time]
**Impact:** [User-facing changes / Downtime expected]

**Changes:**
- [Feature 1]
- [Bug fix 2]
- [Infrastructure change 3]

**Risks:** [None / Medium / High]
**Rollback Plan:** [Describe how to rollback if issues occur]

**Contact:** [On-call engineer name/contact]
```

---

## Section 7: Staging Verification (10 minutes)

### 7.1 Staging Deployment ✅ CRITICAL
```bash
# Deploy to staging first
docker-compose -f docker-compose.staging.yml pull
docker-compose -f docker-compose.staging.yml up -d

# Wait for services to start
sleep 30

# Check health
curl http://staging.ablage.company.com/health
```

**Checklist:**
- [ ] ✅ Deployed to staging environment
- [ ] ✅ Staging health check passes
- [ ] ✅ Smoke tests pass on staging
- [ ] ✅ No errors in staging logs

**If staging deployment fails → STOP production deployment**

---

### 7.2 Smoke Tests on Staging
```bash
# Run smoke tests
pytest tests/smoke/ --env=staging -v

# Manual tests checklist:
```

**Checklist:**
- [ ] ✅ User login works
- [ ] ✅ Document upload works
- [ ] ✅ OCR processing works
- [ ] ✅ Document download works
- [ ] ⚠️ Search functionality works
- [ ] ⚠️ API endpoints return expected responses

**If any smoke test fails → Fix before production**

---

## Section 8: Deployment Plan (5 minutes)

### 8.1 Deployment Strategy
**Select deployment type:**
- [ ] 🔵 **Standard Deployment** (Rolling update, no downtime)
- [ ] 🟡 **Blue-Green Deployment** (Zero-downtime, instant rollback)
- [ ] 🔴 **Maintenance Window** (Downtime required for migrations)

**Deployment Steps:**
```markdown
1. [ ] Enable maintenance mode (if downtime required)
2. [ ] Pull latest Docker images
3. [ ] Run database migrations (if applicable)
4. [ ] Restart services (rolling or all-at-once)
5. [ ] Run post-deployment smoke tests
6. [ ] Monitor for 15 minutes
7. [ ] Disable maintenance mode
8. [ ] Confirm success
```

---

### 8.2 Rollback Plan ✅ CRITICAL
**Checklist:**
- [ ] ✅ Rollback procedure documented
- [ ] ✅ Previous version tagged in Git
- [ ] ✅ Previous Docker images available
- [ ] ⚠️ Database rollback migration tested (if applicable)
- [ ] ⚠️ Rollback tested on staging

**Rollback Command:**
```bash
# Rollback to previous version
git checkout tags/v1.2.3  # Previous stable tag
docker-compose pull
docker-compose up -d

# Rollback database (if needed)
alembic downgrade -1
```

**Time to rollback:** <10 minutes

---

## Section 9: Post-Deployment Monitoring

### 9.1 Monitoring Window (15 minutes after deployment)
**Checklist:**
- [ ] Monitor error rates (should be <1%)
- [ ] Monitor API latency (P95 <500ms)
- [ ] Monitor GPU memory (should be <85%)
- [ ] Monitor queue depth (should be <50)
- [ ] Check logs for errors/warnings

**Commands:**
```bash
# Watch logs for errors
docker-compose logs -f --tail=100 | grep -E '(ERROR|CRITICAL)'

# Monitor API requests
curl -s http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m]) | jq

# Check GPU status
watch -n 5 nvidia-smi
```

---

### 9.2 User Feedback
**Checklist:**
- [ ] No user-reported issues in first 15 minutes
- [ ] User acceptance testing passed (if applicable)
- [ ] Performance as expected under load

---

## Section 10: Final Sign-Off

### 10.1 Deployment Success Criteria
**ALL must be true:**
- [ ] ✅ All services running and healthy
- [ ] ✅ No errors in logs (first 15 minutes)
- [ ] ✅ API response times within SLA (<500ms P95)
- [ ] ✅ OCR processing functional
- [ ] ✅ No user-reported critical issues
- [ ] ✅ Monitoring shows green status

---

### 10.2 Documentation
**Checklist:**
- [ ] Deployment logged in deployment log
- [ ] Issues encountered documented
- [ ] Post-deployment report sent to team

**Deployment Log Entry:**
```markdown
**Deployment ID:** DEPLOY-2025-01-23-001
**Date/Time:** 2025-01-23 14:30 CET
**Version:** v1.3.0
**Deployed by:** [Your Name]
**Duration:** 25 minutes
**Downtime:** None
**Issues:** None
**Rollback Required:** No
**Status:** ✅ SUCCESS
```

---

## Emergency Rollback Procedure

**If critical issue detected after deployment:**

```bash
# IMMEDIATELY rollback
git checkout tags/v1.2.3  # Previous version
docker-compose down
docker-compose up -d

# If database migration ran, rollback database
alembic downgrade -1

# Verify rollback successful
curl http://localhost:8000/health

# Notify team
/opt/ablage/scripts/send_alert.sh \
  --severity CRITICAL \
  --message "Deployment rolled back due to [ISSUE]"
```

**Time to rollback:** <10 minutes

---

## Deployment Types - Specific Checklists

### 🔵 Standard Deployment (Most Common)
Additional checks:
- [ ] No breaking API changes
- [ ] Backward compatible with client versions
- [ ] Feature flags used for gradual rollout

### 🟡 High-Risk Deployment
Additional checks:
- [ ] Stakeholder approval obtained
- [ ] Extended monitoring period (60 minutes)
- [ ] Rollback drill performed beforehand
- [ ] Database expert on standby

### 🔴 Emergency Hot-Fix
Reduced checks (ONLY for critical production issues):
- [ ] ✅ Tests pass
- [ ] ✅ Code reviewed by 1 senior engineer
- [ ] ✅ Tested on staging
- [ ] Document reason for expedited process

---

## Checklist Scorecard

**Calculate your score:**
- ✅ CRITICAL items: Must be 100%
- ⚠️ WARNING items: Should be ≥90%

**Total Items:** 75
**Critical Items:** 25
**Warning Items:** 50

**Your Score:**
- Critical: ___/25 (must be 25/25)
- Warning: ___/50 (should be ≥45/50)

**✅ PASS:** Critical 100% AND Warning ≥90%
**❌ FAIL:** Any critical item failed OR warning <90%

---

## Continuous Improvement

**After each deployment, reflect:**
- What went well?
- What went wrong?
- What would you improve next time?
- Any checklist items to add/remove?

**Submit improvements:** [feedback-form-link]

---

## Related Documents
- [Post-Deployment Checklist](post_deployment_checklist.md)
- [Deployment Workflow](../deployment_workflow.md)
- [Incident Response Playbook](../incident_response_playbook.md)
- [Daily Operations Checklist](../Runbooks/daily_operations_checklist.md)

---

## Revision History

| Version | Date       | Author      | Changes                           |
|---------|------------|-------------|-----------------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial pre-deployment checklist  |

---

**Remember: It's better to delay a deployment than to deploy something broken. When in doubt, ask for help!** 🚀
