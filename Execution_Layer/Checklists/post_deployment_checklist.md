# Post-Deployment Checklist
**Ablage-System - Nachbereitungsprüfung**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Purpose: Verify deployment success and system stability

---

## Checklist Overview

**Complete this checklist 30-60 minutes AFTER deployment.**

- ⏱️ **Duration:** 30 minutes
- 🎯 **Purpose:** Verify deployment success, catch issues early
- ⚠️ **Trigger Rollback if:** Any CRITICAL check fails

---

## Section 1: Immediate Verification (0-15 minutes)

### 1.1 Service Health ✅ CRITICAL
**Time:** 2 minutes

```bash
# Check all services running
docker-compose ps

# Expected: All services "Up" status
```

**Checklist:**
- [ ] ✅ Backend service: Up
- [ ] ✅ Worker service: Up
- [ ] ✅ PostgreSQL: Up
- [ ] ✅ Redis: Up
- [ ] ✅ MinIO: Up
- [ ] ⚠️ No restart loops (restart count should be 0)

**If any service down → IMMEDIATE ROLLBACK**

---

### 1.2 Health Endpoint ✅ CRITICAL
**Time:** 1 minute

```bash
# Check health endpoint
curl -s http://localhost:8000/health | jq

# Expected response:
# {
#   "status": "healthy",
#   "checks": {
#     "database": true,
#     "redis": true,
#     "minio": true,
#     "gpu": true,
#     "disk_space": true
#   },
#   "version": "v1.3.0",
#   "timestamp": "2025-01-23T14:35:00Z"
# }
```

**Checklist:**
- [ ] ✅ HTTP 200 response
- [ ] ✅ "status": "healthy"
- [ ] ✅ All checks return `true`
- [ ] ✅ Correct version deployed
- [ ] ⚠️ Response time <100ms

**If health check fails → IMMEDIATE ROLLBACK**

---

### 1.3 Error Log Check ✅ CRITICAL
**Time:** 3 minutes

```bash
# Check for errors since deployment
docker-compose logs --since 15m | grep -E '(ERROR|CRITICAL|Exception)'

# Expected: No critical errors, minimal warnings
```

**Checklist:**
- [ ] ✅ Zero CRITICAL errors
- [ ] ✅ <5 ERROR entries (if any, must be understood)
- [ ] ⚠️ <20 WARNING entries
- [ ] ⚠️ No unexpected exceptions

**Review any errors found:**
```bash
# Categorize errors by type
docker-compose logs --since 15m | grep ERROR | awk '{print $4}' | sort | uniq -c
```

**If >5 errors or any CRITICAL → INVESTIGATE immediately, consider rollback**

---

### 1.4 Smoke Tests ✅ CRITICAL
**Time:** 5 minutes

**Run automated smoke tests:**
```bash
# Run smoke test suite
pytest tests/smoke/post_deployment_smoke.py -v

# Expected: All tests pass
```

**Manual smoke tests:**
```bash
# 1. User authentication
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d '{"username":"test@example.com","password":"test123"}' \
  -H "Content-Type: application/json"

# 2. Document upload
curl -X POST http://localhost:8000/api/v1/documents/ \
  -F "file=@tests/fixtures/sample_de.pdf" \
  -H "Authorization: Bearer $TOKEN"

# 3. Document retrieval
curl http://localhost:8000/api/v1/documents/$DOC_ID \
  -H "Authorization: Bearer $TOKEN"
```

**Checklist:**
- [ ] ✅ Authentication works
- [ ] ✅ Document upload succeeds
- [ ] ✅ Document retrieval works
- [ ] ⚠️ OCR processing starts (check queue)
- [ ] ⚠️ Search functionality operational

**If any smoke test fails → IMMEDIATE ROLLBACK**

---

### 1.5 Database Integrity
**Time:** 4 minutes

```sql
-- Connect to database
docker exec ablage-postgres psql -U postgres -d ablage

-- Check for connection errors
SELECT COUNT(*) FROM pg_stat_activity WHERE wait_event_type = 'Lock';
-- Expected: 0 (no locks)

-- Verify recent documents
SELECT COUNT(*) FROM documents WHERE created_at > NOW() - INTERVAL '15 minutes';
-- Should show new test documents from smoke tests

-- Check for migration issues
SELECT version_num FROM alembic_version;
-- Should match expected version
```

**Checklist:**
- [ ] ✅ Database accessible
- [ ] ✅ No blocking locks
- [ ] ✅ Migration version correct
- [ ] ⚠️ Recent data visible
- [ ] ⚠️ Foreign key constraints intact

---

## Section 2: Performance Verification (15-30 minutes)

### 2.1 API Response Times
**Time:** 5 minutes

```bash
# Benchmark critical endpoints
ab -n 100 -c 10 http://localhost:8000/health
ab -n 50 -c 5 -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/documents/

# Check Prometheus metrics
curl -s http://localhost:9090/api/v1/query?query='histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[5m]))'
```

**Checklist:**
- [ ] ✅ Health endpoint: P95 <50ms
- [ ] ✅ Document list: P95 <300ms
- [ ] ⚠️ Document upload: P95 <500ms
- [ ] ⚠️ No timeout errors

**Target Metrics:**
| Endpoint | P50 | P95 | P99 |
|----------|-----|-----|-----|
| /health | <20ms | <50ms | <100ms |
| /documents/ | <100ms | <300ms | <500ms |
| /documents/{id} | <50ms | <150ms | <300ms |

**If any P95 exceeds target by >50% → INVESTIGATE**

---

### 2.2 OCR Processing Throughput
**Time:** 5 minutes

```bash
# Queue 10 test documents
for i in {1..10}; do
  curl -X POST http://localhost:8000/api/v1/documents/ \
    -F "file=@tests/fixtures/sample_de.pdf" \
    -H "Authorization: Bearer $TOKEN"
done

# Monitor processing rate
docker-compose logs -f worker | grep "Processing batch"

# Check queue depth
docker exec ablage-redis redis-cli LLEN celery
```

**Checklist:**
- [ ] ⚠️ Queue depth <50 documents
- [ ] ⚠️ Processing rate ≥150 docs/hour
- [ ] ⚠️ No stuck documents (same doc processing >5 min)
- [ ] ⚠️ GPU utilization 40-80% during processing

**If processing rate <100 docs/hour → INVESTIGATE performance**

---

### 2.3 Resource Utilization
**Time:** 5 minutes

```bash
# CPU usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# GPU status
nvidia-smi --query-gpu=utilization.gpu,utilization.memory,memory.used,memory.free --format=csv

# Disk I/O
iostat -x 1 5
```

**Checklist:**
- [ ] ⚠️ CPU usage <70% average
- [ ] ⚠️ Memory usage <80%
- [ ] ⚠️ GPU memory usage <85%
- [ ] ⚠️ Disk I/O latency <10ms

**Resource Baselines:**
| Resource | Idle | Active | Alert Threshold |
|----------|------|--------|-----------------|
| CPU | 10-20% | 40-60% | >80% |
| RAM | 30-40% | 50-70% | >85% |
| GPU | 5-15% | 60-80% | >90% |
| Disk I/O | <5MB/s | 20-50MB/s | >100MB/s |

---

### 2.4 Database Performance
**Time:** 5 minutes

```sql
-- Check query performance
SELECT
  query,
  calls,
  mean_exec_time,
  max_exec_time
FROM pg_stat_statements
WHERE calls > 10
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Expected: All queries <100ms average

-- Check for slow queries
SELECT
  pid,
  now() - pg_stat_activity.query_start AS duration,
  query
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - pg_stat_activity.query_start > interval '1 second';

-- Expected: Empty result
```

**Checklist:**
- [ ] ⚠️ No queries >100ms average
- [ ] ⚠️ No queries running >5 seconds
- [ ] ⚠️ Connection pool not exhausted (<50% used)
- [ ] ⚠️ No table locks

---

## Section 3: Extended Monitoring (30-60 minutes)

### 3.1 Error Rate Monitoring
**Time:** Continuous (check every 10 minutes)

```bash
# Count errors in last 10 minutes
docker-compose logs --since 10m | grep ERROR | wc -l

# Expected: <5 errors per 10 minutes
```

**Checklist:**
- [ ] ⚠️ Error rate <1% of requests
- [ ] ⚠️ No error rate spike (>2x baseline)
- [ ] ⚠️ Error types consistent with baseline

**Monitor error trends:**
```bash
# Error count every 10 minutes for 1 hour
for i in {1..6}; do
  echo "$(date): $(docker-compose logs --since 10m | grep ERROR | wc -l) errors"
  sleep 600
done
```

---

### 3.2 User Activity Monitoring
**Time:** Continuous (check after 30 minutes)

```sql
-- Active users in last 30 minutes
SELECT COUNT(DISTINCT user_id) as active_users
FROM api_logs
WHERE timestamp > NOW() - INTERVAL '30 minutes';

-- Compare to baseline (should be similar)

-- Failed requests
SELECT
  endpoint,
  status_code,
  COUNT(*) as failure_count
FROM api_logs
WHERE status_code >= 400
  AND timestamp > NOW() - INTERVAL '30 minutes'
GROUP BY endpoint, status_code
ORDER BY failure_count DESC;

-- Expected: <1% failure rate
```

**Checklist:**
- [ ] ⚠️ Active users within 20% of baseline
- [ ] ⚠️ No user-reported issues
- [ ] ⚠️ Request failure rate <1%

---

### 3.3 GPU Stability
**Time:** Continuous (check every 15 minutes)

```bash
# Monitor GPU memory over time
watch -n 60 'nvidia-smi --query-gpu=memory.used,memory.free --format=csv,noheader'

# Log GPU stats
for i in {1..4}; do
  echo "$(date): $(nvidia-smi --query-gpu=memory.used --format=csv,noheader)"
  sleep 900  # 15 minutes
done
```

**Checklist:**
- [ ] ⚠️ No GPU OOM errors
- [ ] ⚠️ GPU memory stable (not growing)
- [ ] ⚠️ GPU temperature <80°C
- [ ] ⚠️ No GPU crashes/resets

**If GPU memory climbing → INVESTIGATE memory leak**

---

## Section 4: User Feedback & Validation

### 4.1 User Reports
**Time:** First hour after deployment

**Checklist:**
- [ ] ⚠️ No critical user-reported issues
- [ ] ⚠️ No support tickets filed for new bugs
- [ ] ⚠️ User acceptance testing passed (if applicable)

**Monitor support channels:**
- Email: support@company.com
- Slack: #ablage-support
- Issue tracker: [link]

---

### 4.2 Business Metrics
**Time:** 1-24 hours after deployment

**Checklist:**
- [ ] ⚠️ Document upload rate normal
- [ ] ⚠️ OCR success rate ≥95%
- [ ] ⚠️ User engagement unchanged or improved
- [ ] ⚠️ No revenue impact (if applicable)

```sql
-- Compare documents processed: today vs. yesterday
SELECT
  DATE(created_at) as date,
  COUNT(*) as documents_processed,
  COUNT(CASE WHEN status = 'completed' THEN 1 END) as successful,
  ROUND(COUNT(CASE WHEN status = 'completed' THEN 1 END)::numeric / COUNT(*) * 100, 2) as success_rate
FROM documents
WHERE created_at > NOW() - INTERVAL '2 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Expected: Success rate ≥95%, volume similar to yesterday
```

---

## Section 5: Documentation & Communication

### 5.1 Deployment Log Entry
**Time:** 5 minutes

```markdown
**Deployment ID:** DEPLOY-2025-01-23-001
**Version:** v1.3.0
**Deployed By:** [Your Name]
**Date/Time:** 2025-01-23 14:30 CET
**Duration:** 25 minutes
**Downtime:** None

**Changes:**
- Feature: Enhanced German text validation
- Bug fix: Fixed GPU memory leak in batch processing
- Performance: Optimized database queries for document search

**Migration:** Yes (added index on documents.extracted_text)
**Migration Time:** 3 minutes

**Issues Encountered:** None
**Rollback Required:** No

**Post-Deployment Metrics (1 hour):**
- Error Rate: 0.3% (baseline: 0.4%)
- API P95 Latency: 285ms (target: <500ms)
- OCR Throughput: 195 docs/hour (target: >192)
- GPU Memory Peak: 82% (target: <85%)

**Status:** ✅ SUCCESS
**Signed Off By:** [Your Name]
**Date:** 2025-01-23 15:30 CET
```

**Save to:** `/var/log/ablage/deployments/DEPLOY-2025-01-23-001.md`

---

### 5.2 Team Communication
**Time:** 5 minutes

**Send deployment success notification:**
```markdown
Subject: ✅ Deployment v1.3.0 - SUCCESS

Team,

Deployment v1.3.0 completed successfully at 14:30 CET.

**Highlights:**
- Enhanced German validation
- Fixed GPU memory leak
- 30% faster document search

**Metrics (1 hour post-deployment):**
- All health checks: ✅ GREEN
- Error rate: 0.3% (improved from 0.4%)
- API latency: 285ms P95 (within SLA)
- Throughput: 195 docs/hour

**Issues:** None reported

**Next Steps:**
- Continue monitoring for 24 hours
- User feedback collection ongoing

Thank you for testing on staging!

[Your Name]
DevOps Team
```

---

## Section 6: Rollback Decision Tree

### When to Rollback?

```
CRITICAL ISSUES (Immediate Rollback):
├─→ Any service down/crashing
├─→ Health check failing
├─→ Error rate >10%
├─→ Data loss detected
├─→ Security breach
└─→ >5 user-reported critical bugs in first hour

HIGH-SEVERITY ISSUES (Consider Rollback):
├─→ Error rate 5-10%
├─→ Performance degradation >50%
├─→ GPU OOM errors recurring
├─→ Database migration issues
└─→ Multiple user-reported bugs

MONITOR & FIX (No Rollback):
├─→ Error rate <5%
├─→ Performance within 20% of baseline
├─→ Isolated bug reports
└─→ Metrics trending in right direction
```

---

### Rollback Procedure
**If rollback needed:**

```bash
# 1. Notify team IMMEDIATELY
/opt/ablage/scripts/send_alert.sh \
  --severity CRITICAL \
  --message "Initiating deployment rollback - [REASON]"

# 2. Execute rollback
git checkout tags/v1.2.3  # Previous stable version
docker-compose down
docker-compose pull
docker-compose up -d

# 3. Rollback database migration (if needed)
alembic downgrade -1

# 4. Verify rollback
curl http://localhost:8000/health
pytest tests/smoke/ -v

# 5. Document incident
# Create post-mortem report

# Expected time to rollback: <10 minutes
```

---

## Section 7: Sign-Off

### 7.1 Success Criteria ✅ ALL MUST BE TRUE
- [ ] ✅ All services healthy for 30+ minutes
- [ ] ✅ Zero critical errors
- [ ] ✅ Performance within SLA targets
- [ ] ✅ Smoke tests passing
- [ ] ✅ No user-reported critical issues
- [ ] ✅ Resource utilization normal
- [ ] ✅ GPU stable (no OOM errors)
- [ ] ✅ Database queries performant

### 7.2 Final Approval
- [ ] Deployment log entry completed
- [ ] Team notified of success
- [ ] Monitoring dashboard reviewed
- [ ] Next steps planned (if any issues found)

**Deployment Status:** [✅ SUCCESS / ⚠️ SUCCESS WITH ISSUES / ❌ FAILED]

**Signed Off By:** ________________
**Date/Time:** ________________

---

## Extended Monitoring Schedule

### Next 24 Hours
- **+2 hours:** Check metrics dashboard
- **+4 hours:** Review error logs
- **+8 hours:** Business metrics review
- **+24 hours:** Full system health audit

### Next Week
- **Day 2:** Performance trend analysis
- **Day 3:** User feedback review
- **Day 7:** Post-deployment retrospective

---

## Continuous Improvement

**After each deployment:**
1. What went well?
2. What could be improved?
3. Any near-misses or close calls?
4. Checklist items to add/modify?

**Submit feedback:** [link-to-feedback-form]

---

## Related Documents
- [Pre-Deployment Checklist](pre_deployment_checklist.md)
- [Incident Response Playbook](../incident_response_playbook.md)
- [Performance Degradation Runbook](../Runbooks/performance_degradation_runbook.md)
- [Daily Operations Checklist](../Runbooks/daily_operations_checklist.md)

---

## Revision History

| Version | Date       | Author      | Changes                            |
|---------|------------|-------------|------------------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial post-deployment checklist  |

---

**Remember: A successful deployment is one you can walk away from confidently!** ✅
