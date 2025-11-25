# Daily Operations Checklist
**Ablage-System - Tägliche Betriebsprüfungen**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Estimated Time: 15-20 minutes

---

## Purpose
This daily checklist ensures the Ablage-System operates at peak performance and identifies issues before they impact users.

## Prerequisites
- Access to production environment
- Monitoring dashboard credentials
- Basic understanding of system architecture

---

## Morning Checks (08:00 - 09:00)

### 1. System Health Overview
**Time: 3 minutes**

```bash
# Check all services are running
docker-compose ps

# Expected output: All services "Up" status
# backend       Up      0.0.0.0:8000->8000/tcp
# worker        Up
# postgres      Up      0.0.0.0:5432->5432/tcp
# redis         Up      0.0.0.0:6379->6379/tcp
# minio         Up      0.0.0.0:9000-9001->9000-9001/tcp
```

**✅ Checkpoint:**
- [ ] All 5 core services running
- [ ] No services in "Restarting" state
- [ ] Container uptime > 24 hours (or since last planned restart)

**⚠️ Action if Failed:** Check logs with `docker-compose logs --tail=50 [service]`

---

### 2. API Health Check
**Time: 2 minutes**

```bash
# Check API health endpoint
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
#   "timestamp": "2025-01-23T08:05:00Z"
# }
```

**✅ Checkpoint:**
- [ ] HTTP 200 response
- [ ] All checks return `true`
- [ ] Response time < 100ms

**⚠️ Action if Failed:**
- Database false → Check PostgreSQL connection
- Redis false → Check Redis service
- GPU false → Run GPU diagnostics (Section 3)
- Disk false → Check disk usage (Section 4)

---

### 3. GPU Status Verification
**Time: 2 minutes**

```bash
# Check GPU availability and memory
nvidia-smi --query-gpu=name,memory.used,memory.free,utilization.gpu --format=csv

# Expected output:
# RTX 4080, 2400 MiB, 13700 MiB, 15%
```

**✅ Checkpoint:**
- [ ] GPU detected and accessible
- [ ] Memory used < 4 GB (idle state)
- [ ] No zombie processes holding GPU memory
- [ ] Temperature < 80°C

**⚠️ Action if Failed:**
```bash
# Clear GPU cache if memory high at idle
docker exec ablage-backend python -c "import torch; torch.cuda.empty_cache()"

# Check for stuck processes
nvidia-smi | grep python

# If temperature high, check cooling system
```

---

### 4. Disk Space Check
**Time: 1 minute**

```bash
# Check disk usage for critical paths
df -h | grep -E '(Filesystem|/var/lib/docker|/mnt/minio)'

# Alert thresholds:
# /var/lib/docker  → Warning: >70%, Critical: >85%
# /mnt/minio       → Warning: >75%, Critical: >90%
```

**✅ Checkpoint:**
- [ ] Docker volume < 70% used
- [ ] MinIO storage < 75% used
- [ ] Root partition < 80% used

**⚠️ Action if Failed:**
- Docker volume high → Clean old images: `docker system prune -a --volumes`
- MinIO high → Archive old documents or expand storage
- Root high → Check log files: `du -sh /var/log/* | sort -h`

---

### 5. Database Connection Pool
**Time: 2 minutes**

```bash
# Check PostgreSQL connection status
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT count(*) as active_connections,
         max_conn.setting::int as max_connections,
         round(count(*)::numeric / max_conn.setting::numeric * 100, 2) as pct_used
  FROM pg_stat_activity
  CROSS JOIN (SELECT setting FROM pg_settings WHERE name = 'max_connections') max_conn
  WHERE state = 'active';"

# Expected output:
# active_connections | max_connections | pct_used
# 5                  | 100             | 5.00
```

**✅ Checkpoint:**
- [ ] Active connections < 50% of max
- [ ] No long-running queries (> 5 minutes)
- [ ] Connection pool not exhausted

**⚠️ Action if Failed:**
```sql
-- Check for blocking queries
SELECT pid, query, state, wait_event_type, query_start
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;

-- Terminate stuck query (if confirmed safe)
-- SELECT pg_terminate_backend(PID);
```

---

### 6. Redis Queue Depth
**Time: 2 minutes**

```bash
# Check Celery queue depth
docker exec ablage-redis redis-cli LLEN celery

# Expected output: < 50 (low queue backlog)
```

**✅ Checkpoint:**
- [ ] Queue depth < 50 documents
- [ ] No stale tasks (older than 1 hour)
- [ ] Worker processing tasks actively

**⚠️ Action if Failed:**
```bash
# Check worker status
docker-compose logs worker --tail=20

# Inspect queue contents
docker exec ablage-redis redis-cli --scan --pattern 'celery*'

# If queue stuck, restart worker
docker-compose restart worker
```

---

### 7. Error Log Review
**Time: 3 minutes**

```bash
# Check for errors in last 24 hours
docker-compose logs --since 24h | grep -E '(ERROR|CRITICAL|Exception)' | tail -20

# Count errors by type
docker-compose logs --since 24h | grep ERROR | awk '{print $4}' | sort | uniq -c | sort -rn
```

**✅ Checkpoint:**
- [ ] < 10 errors in last 24 hours
- [ ] No CRITICAL level errors
- [ ] No repeated error patterns (> 5 occurrences)

**⚠️ Action if Failed:**
- GPU OOM errors → Review [gpu_troubleshooting_decision_tree.md](gpu_troubleshooting_decision_tree.md)
- Database errors → Check [performance_degradation_runbook.md](performance_degradation_runbook.md)
- Authentication errors → Review security logs

---

## Midday Checks (12:00 - 12:30)

### 8. Performance Metrics Review
**Time: 5 minutes**

```bash
# Check API response times (P95)
curl -s http://localhost:8000/metrics | grep 'http_request_duration_seconds{quantile="0.95"}'

# Expected: < 0.5 seconds (500ms)
```

**Metrics to Review:**
1. **API Latency (P95):** < 500ms ✅
2. **OCR Throughput:** > 150 docs/hour ✅
3. **Error Rate:** < 1% ✅
4. **GPU Utilization:** 40-80% during peak ✅

**⚠️ Action if Failed:**
- High latency → Check database query performance
- Low throughput → Review batch sizing configuration
- High errors → Check error logs (Section 7)

---

### 9. Backup Verification
**Time: 2 minutes**

```bash
# Verify last backup completed successfully
ls -lh /mnt/backups/ | tail -5

# Check backup age
find /mnt/backups -name "ablage_backup_*.tar.gz" -mtime -1 | wc -l

# Expected: At least 1 backup from last 24 hours
```

**✅ Checkpoint:**
- [ ] Backup exists from last 24 hours
- [ ] Backup size reasonable (not 0 bytes, not 10x normal)
- [ ] Backup script completed without errors

**⚠️ Action if Failed:**
- Check backup logs: `journalctl -u ablage-backup.service -n 50`
- Manually trigger backup: `/opt/ablage/scripts/backup.sh`
- Verify backup integrity: `tar -tzf /mnt/backups/latest.tar.gz | head -20`

---

## Evening Checks (17:00 - 17:30)

### 10. Daily Document Processing Summary
**Time: 3 minutes**

```sql
-- Connect to database
docker exec ablage-postgres psql -U postgres -d ablage

-- Get processing statistics for today
SELECT
  COUNT(*) as total_documents,
  COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed,
  COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed,
  ROUND(AVG(EXTRACT(EPOCH FROM (completed_at - created_at))), 2) as avg_processing_time_sec
FROM documents
WHERE DATE(created_at) = CURRENT_DATE;
```

**✅ Checkpoint:**
- [ ] Success rate > 95%
- [ ] Average processing time < 10 seconds
- [ ] No documents stuck in "processing" for > 1 hour

**⚠️ Action if Failed:**
```sql
-- Find stuck documents
SELECT id, status, created_at,
       EXTRACT(EPOCH FROM (NOW() - created_at))/3600 as hours_stuck
FROM documents
WHERE status = 'processing'
  AND created_at < NOW() - INTERVAL '1 hour'
ORDER BY created_at;

-- Reset stuck documents (manual intervention)
-- UPDATE documents SET status = 'pending' WHERE id = 'STUCK_DOC_ID';
```

---

### 11. User Activity Review
**Time: 2 minutes**

```sql
-- Daily active users
SELECT COUNT(DISTINCT user_id) as daily_active_users
FROM api_logs
WHERE DATE(timestamp) = CURRENT_DATE;

-- Peak hour analysis
SELECT EXTRACT(HOUR FROM timestamp) as hour, COUNT(*) as requests
FROM api_logs
WHERE DATE(timestamp) = CURRENT_DATE
GROUP BY hour
ORDER BY hour;
```

**✅ Checkpoint:**
- [ ] Daily active users within expected range
- [ ] Peak hours identified (typically 09:00-11:00, 14:00-16:00)
- [ ] No unusual traffic spikes

**⚠️ Action if Failed:**
- Unusual spike → Check for abuse/DDoS (review rate limiting logs)
- Zero activity → Check if system accessible from user network
- Unexpected pattern → Investigate with security team

---

### 12. Security Scan Summary
**Time: 2 minutes**

```bash
# Check for failed authentication attempts
docker-compose logs backend --since 24h | grep 'authentication failed' | wc -l

# Expected: < 20 failed attempts per day
```

**✅ Checkpoint:**
- [ ] < 20 failed authentication attempts
- [ ] No brute force patterns (same IP > 5 attempts)
- [ ] No suspicious API access patterns

**⚠️ Action if Failed:**
```bash
# Identify suspicious IPs
docker-compose logs backend --since 24h | grep 'authentication failed' | \
  awk '{print $NF}' | sort | uniq -c | sort -rn | head -10

# Block IP if confirmed malicious (via firewall)
# sudo ufw deny from SUSPICIOUS_IP
```

---

## End of Day Summary

### 13. Daily Report Generation
**Time: 5 minutes**

```bash
# Generate daily report
python /opt/ablage/scripts/generate_daily_report.py --date today --output /var/log/ablage/daily_report_$(date +%F).txt

# Review key metrics
cat /var/log/ablage/daily_report_$(date +%F).txt
```

**Report Sections:**
1. **System Availability:** Target 99.9% uptime
2. **Document Processing:** Total, success rate, avg time
3. **Error Summary:** Count by type, critical issues
4. **Performance:** API latency, GPU utilization, throughput
5. **Security:** Failed auth attempts, suspicious activity
6. **Resource Usage:** CPU, RAM, disk, GPU memory

**✅ Daily Sign-off Checklist:**
- [ ] All critical checks passed
- [ ] No outstanding alerts
- [ ] Backup verified
- [ ] Performance within targets
- [ ] Daily report generated and reviewed
- [ ] Any issues documented in operations log

---

## Escalation Procedures

### When to Escalate
Escalate immediately if:
- ❌ System unavailable for > 5 minutes
- ❌ Data loss suspected
- ❌ Security breach detected
- ❌ GPU hardware failure
- ❌ Database corruption
- ❌ Multiple critical checks failed

### Escalation Contacts
1. **Level 1:** DevOps Team Lead - ops-team@company.com
2. **Level 2:** System Architect - architecture@company.com
3. **Level 3:** CTO - cto@company.com

### Emergency Procedures
- **System down:** Follow [incident_response_playbook.md](../incident_response_playbook.md)
- **GPU issues:** Follow [gpu_troubleshooting_decision_tree.md](gpu_troubleshooting_decision_tree.md)
- **Performance degradation:** Follow [performance_degradation_runbook.md](performance_degradation_runbook.md)
- **Security incident:** Follow [security_incident_runbook.md](security_incident_runbook.md)

---

## Automation Opportunities

### Current Manual Tasks
These checks should eventually be automated:
- [ ] Health endpoint monitoring (target: every 60 seconds)
- [ ] GPU status checks (target: every 5 minutes)
- [ ] Disk space alerts (target: threshold-based)
- [ ] Error log aggregation (target: real-time)
- [ ] Daily report generation (target: automated at 18:00)

### Monitoring Integration
Consider integrating with:
- **Prometheus** for metrics collection
- **Grafana** for visualization
- **AlertManager** for automated alerts
- **PagerDuty** for on-call notifications

---

## Notes Section

### Date: _________________

**Issues Found:**
-

**Actions Taken:**
-

**Follow-up Required:**
-

**Completed By:** _________________
**Sign-off Time:** _________________

---

## Revision History

| Version | Date       | Author      | Changes                          |
|---------|------------|-------------|----------------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial daily operations checklist |

---

## Related Documents
- [Weekly Maintenance Runbook](weekly_maintenance_runbook.md)
- [Monthly Health Audit Runbook](monthly_health_audit_runbook.md)
- [Incident Response Playbook](../incident_response_playbook.md)
- [GPU Troubleshooting Decision Tree](gpu_troubleshooting_decision_tree.md)
- [Performance Degradation Runbook](performance_degradation_runbook.md)
- [Security Incident Runbook](security_incident_runbook.md)
