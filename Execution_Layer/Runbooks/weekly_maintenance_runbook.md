# Weekly Maintenance Runbook
**Ablage-System - Wöchentliche Wartung**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Schedule: Every Sunday, 22:00-24:00 CET
Estimated Time: 60-90 minutes

---

## Purpose
Weekly maintenance ensures optimal system performance, prevents issues, and validates backups. This runbook complements the [daily operations checklist](daily_operations_checklist.md) with deeper system health checks.

## Prerequisites
- [ ] Scheduled maintenance window communicated to users
- [ ] Recent backup verified (< 24 hours old)
- [ ] All team members notified
- [ ] Emergency rollback plan ready

---

## Maintenance Window Preparation (30 minutes before)

### 1. Pre-Maintenance Backup
**Time: 20 minutes**

```bash
# Create pre-maintenance snapshot
timestamp=$(date +%Y%m%d_%H%M%S)

# Backup database
docker exec ablage-postgres pg_dump -U postgres -F c -b -v -f \
  /backups/pre_maintenance_${timestamp}.dump ablage

# Backup MinIO data catalog
docker exec ablage-minio mc mirror local/documents/ /backups/minio_${timestamp}/

# Backup configuration
tar -czf /mnt/backups/config_${timestamp}.tar.gz \
  docker-compose.yml \
  .env \
  /etc/nginx/ \
  /opt/ablage/config/

# Verify backups
ls -lh /mnt/backups/ | grep ${timestamp}
```

**✅ Checkpoint:**
- [ ] Database backup created (size > 100MB)
- [ ] MinIO backup initiated
- [ ] Configuration backup created
- [ ] Backup integrity verified

---

### 2. System Snapshot
**Time: 5 minutes**

```bash
# Document current state
docker-compose ps > /var/log/ablage/weekly_maintenance_${timestamp}_before.txt
docker stats --no-stream >> /var/log/ablage/weekly_maintenance_${timestamp}_before.txt
nvidia-smi >> /var/log/ablage/weekly_maintenance_${timestamp}_before.txt
df -h >> /var/log/ablage/weekly_maintenance_${timestamp}_before.txt
free -h >> /var/log/ablage/weekly_maintenance_${timestamp}_before.txt
```

---

### 3. User Notification
**Time: 5 minutes**

```bash
# Enable maintenance mode
docker exec ablage-backend python -c "
from app.core.config import settings
settings.MAINTENANCE_MODE = True
"

# Show maintenance page to users
# API returns 503 Service Unavailable with message:
# "System wartung läuft. Voraussichtliche Dauer: 90 Minuten."
```

---

## Maintenance Tasks (60 minutes)

### Task 1: Database Maintenance
**Time: 20 minutes**

**1.1 VACUUM and ANALYZE**
```sql
-- Connect to database
docker exec ablage-postgres psql -U postgres -d ablage

-- Verbose vacuum with analysis
VACUUM (VERBOSE, ANALYZE) documents;
VACUUM (VERBOSE, ANALYZE) api_logs;
VACUUM (VERBOSE, ANALYZE) document_access_log;
VACUUM (VERBOSE, ANALYZE) auth_logs;

-- Check table bloat after vacuum
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  n_dead_tup as dead_tuples,
  n_live_tup as live_tuples,
  round(n_dead_tup::float / NULLIF(n_live_tup, 0) * 100, 2) as dead_ratio
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Expected: dead_ratio < 5% after VACUUM
```

**1.2 Index Maintenance**
```sql
-- Rebuild fragmented indexes
REINDEX TABLE CONCURRENTLY documents;
REINDEX TABLE CONCURRENTLY api_logs;

-- Analyze index usage
SELECT
  schemaname,
  tablename,
  indexname,
  idx_scan as index_scans,
  idx_tup_read as tuples_read,
  idx_tup_fetch as tuples_fetched,
  pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC
LIMIT 20;

-- Flag unused indexes (idx_scan = 0)
-- Consider dropping if confirmed unused
```

**1.3 Update Statistics**
```sql
-- Update planner statistics for better query plans
ANALYZE VERBOSE;

-- Check statistics freshness
SELECT
  schemaname,
  tablename,
  last_vacuum,
  last_autovacuum,
  last_analyze,
  last_autoanalyze
FROM pg_stat_user_tables
ORDER BY last_analyze NULLS FIRST;
```

**✅ Checkpoint:**
- [ ] VACUUM completed successfully
- [ ] Indexes rebuilt
- [ ] Statistics updated
- [ ] No table bloat >10%

**⏱️ Expected Duration:** 15-20 minutes for 10M rows

---

### Task 2: Log Rotation and Cleanup
**Time: 10 minutes**

**2.1 Rotate Application Logs**
```bash
# Compress old logs
find /var/log/ablage/ -name "*.log" -mtime +7 -exec gzip {} \;

# Archive logs older than 30 days
find /var/log/ablage/ -name "*.log.gz" -mtime +30 -exec mv {} /mnt/archive/logs/ \;

# Delete logs older than 90 days
find /mnt/archive/logs/ -name "*.log.gz" -mtime +90 -delete

# Check log sizes
du -sh /var/log/ablage/
du -sh /mnt/archive/logs/
```

**2.2 Clean Application Logs Table**
```sql
-- Archive old API logs (>90 days)
CREATE TABLE api_logs_archive_$(date +%Y%m) AS
SELECT * FROM api_logs
WHERE timestamp < NOW() - INTERVAL '90 days';

-- Delete archived data
DELETE FROM api_logs WHERE timestamp < NOW() - INTERVAL '90 days';

-- Vacuum to reclaim space
VACUUM FULL api_logs;

-- Same for auth_logs
DELETE FROM auth_logs WHERE timestamp < NOW() - INTERVAL '180 days';
VACUUM FULL auth_logs;
```

**2.3 Docker Log Cleanup**
```bash
# Truncate Docker logs (keep last 100MB)
docker-compose logs --tail=1000000 > /dev/null

# Clean up old Docker logs
sudo sh -c "truncate -s 0 /var/lib/docker/containers/*/*-json.log"

# Configure log rotation for future
sudo vi /etc/docker/daemon.json
# {
#   "log-driver": "json-file",
#   "log-opts": {
#     "max-size": "100m",
#     "max-file": "5"
#   }
# }

# Restart Docker if config changed
# sudo systemctl restart docker
```

**✅ Checkpoint:**
- [ ] Old logs compressed
- [ ] Archived logs moved
- [ ] Database logs cleaned (>90 days)
- [ ] Docker logs rotated

---

### Task 3: Docker Image Cleanup
**Time: 10 minutes**

**3.1 Remove Unused Images**
```bash
# List all images
docker images -a

# Remove dangling images (no tag)
docker image prune -a -f

# Remove unused images (not referenced by any container)
docker image prune -a --filter "until=168h" -f  # Older than 7 days

# Expected: Free up 5-20 GB
```

**3.2 Remove Unused Volumes**
```bash
# List all volumes
docker volume ls

# Remove dangling volumes
docker volume prune -f

# Check volume sizes
docker system df -v
```

**3.3 Container Optimization**
```bash
# Remove stopped containers older than 7 days
docker container prune --filter "until=168h" -f

# Check Docker disk usage
docker system df

# Expected output:
# TYPE           TOTAL    ACTIVE   SIZE      RECLAIMABLE
# Images         15       5        12GB      7GB (58%)
# Containers     10       5        2GB       100MB (5%)
# Local Volumes  8        6        50GB      10GB (20%)
```

**✅ Checkpoint:**
- [ ] Dangling images removed
- [ ] Unused volumes cleaned
- [ ] Docker disk usage < 80%

---

### Task 4: Security Updates
**Time: 15 minutes**

**4.1 System Package Updates**
```bash
# Update package lists
sudo apt update

# Check for security updates
sudo apt list --upgradable | grep -i security

# Apply security updates only
sudo apt upgrade -y --security

# Check if reboot required
[ -f /var/run/reboot-required ] && cat /var/run/reboot-required.pkgs

# Note: Schedule reboot if kernel updated
```

**4.2 Docker Image Updates**
```bash
# Pull latest base images
docker-compose pull

# Check for image vulnerabilities (if Trivy installed)
trivy image ablage-backend:latest
trivy image ablage-worker:latest

# Critical/High vulnerabilities found? Rebuild images.
```

**4.3 Dependency Updates (Review Only)**
```bash
# Check for outdated Python packages
docker exec ablage-backend pip list --outdated

# Generate requirements report
docker exec ablage-backend pip list --outdated > /tmp/outdated_packages_$(date +%F).txt

# Review and schedule updates (not during maintenance window)
cat /tmp/outdated_packages_$(date +%F).txt
```

**✅ Checkpoint:**
- [ ] Security updates applied
- [ ] No critical vulnerabilities in images
- [ ] Outdated dependencies documented

**⚠️ Action if Kernel Updated:** Schedule reboot for next maintenance window

---

### Task 5: Backup Validation
**Time: 10 minutes**

**5.1 Test Database Restore**
```bash
# Create test database
docker exec ablage-postgres psql -U postgres -c "CREATE DATABASE ablage_test_restore;"

# Restore latest backup
docker exec ablage-postgres pg_restore -U postgres -d ablage_test_restore \
  /backups/ablage_backup_latest.dump

# Verify row counts match
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT 'ablage' as db, COUNT(*) FROM documents
  UNION ALL
  SELECT 'restore' as db, COUNT(*) FROM ablage_test_restore.documents;"

# Cleanup
docker exec ablage-postgres psql -U postgres -c "DROP DATABASE ablage_test_restore;"
```

**5.2 Verify Backup Integrity**
```bash
# Check backup files exist and not corrupt
for backup in /mnt/backups/ablage_backup_*.tar.gz; do
  echo "Checking $backup..."
  tar -tzf "$backup" > /dev/null && echo "  ✓ OK" || echo "  ✗ CORRUPT"
done

# Verify backup age
latest_backup=$(ls -t /mnt/backups/ablage_backup_*.tar.gz | head -1)
backup_age_hours=$(( ($(date +%s) - $(stat -c %Y "$latest_backup")) / 3600 ))

echo "Latest backup age: ${backup_age_hours} hours"

if [ "$backup_age_hours" -gt 24 ]; then
  echo "⚠️  WARNING: Backup older than 24 hours!"
fi
```

**5.3 Test MinIO Restore**
```bash
# List recent backups
docker exec ablage-minio mc ls /backups/minio_*/

# Verify file count matches production
prod_count=$(docker exec ablage-minio mc ls --recursive local/documents/ | wc -l)
backup_count=$(docker exec ablage-minio mc ls --recursive /backups/minio_latest/ | wc -l)

echo "Production files: $prod_count"
echo "Backup files: $backup_count"

if [ "$prod_count" -ne "$backup_count" ]; then
  echo "⚠️  WARNING: File count mismatch!"
fi
```

**✅ Checkpoint:**
- [ ] Database restore test successful
- [ ] Backup files not corrupted
- [ ] Latest backup < 24 hours old
- [ ] MinIO backup file count matches

---

### Task 6: Performance Benchmarking
**Time: 10 minutes**

**6.1 API Response Time Test**
```bash
# Benchmark health endpoint
ab -n 1000 -c 10 http://localhost:8000/health

# Expected results:
# - Requests per second: >500
# - Mean time per request: <20ms
# - Failed requests: 0

# Benchmark document upload (with test file)
ab -n 100 -c 5 -p /tmp/test_doc.pdf \
  -T application/pdf \
  http://localhost:8000/api/v1/documents/

# Expected: P95 < 500ms
```

**6.2 Database Query Performance**
```sql
-- Check slow queries
SELECT
  query,
  calls,
  mean_exec_time,
  max_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Expected: mean_exec_time < 100ms for all queries
```

**6.3 GPU Performance Test**
```bash
# Run OCR benchmark
docker exec ablage-backend python /opt/ablage/scripts/benchmark_ocr.py \
  --documents 50 \
  --output /tmp/weekly_benchmark_$(date +%F).json

# Expected throughput: >180 docs/hour
# Expected P95 latency: <10s per document

cat /tmp/weekly_benchmark_$(date +%F).json
```

**✅ Checkpoint:**
- [ ] API response times within targets
- [ ] No slow database queries (>100ms)
- [ ] GPU throughput >180 docs/hour

---

## Post-Maintenance Tasks (15 minutes)

### Task 7: Service Health Verification
**Time: 10 minutes**

**7.1 Restart Services (Fresh State)**
```bash
# Graceful restart all services
docker-compose restart

# Wait for services to be ready
sleep 30

# Verify all services running
docker-compose ps

# Expected: All services "Up" status
```

**7.2 Comprehensive Health Check**
```bash
# API health
curl -s http://localhost:8000/health | jq
# Expected: {"status": "healthy", "checks": {"database": true, ...}}

# Database connection
docker exec ablage-postgres psql -U postgres -d ablage -c "SELECT 1;"

# Redis connection
docker exec ablage-redis redis-cli PING
# Expected: PONG

# MinIO connection
docker exec ablage-minio mc ls local/documents/ | head -5

# GPU available
nvidia-smi --query-gpu=name,memory.used,memory.free --format=csv
```

**7.3 Smoke Test Critical Workflows**
```bash
# Test document upload workflow
curl -X POST http://localhost:8000/api/v1/documents/ \
  -F "file=@/tmp/test_doc.pdf" \
  -H "Authorization: Bearer TEST_TOKEN"

# Test OCR processing (manually trigger)
# ... document processing test ...

# Test document retrieval
curl -s http://localhost:8000/api/v1/documents/TEST_DOC_ID
```

**✅ Checkpoint:**
- [ ] All services healthy
- [ ] Database accessible
- [ ] Redis operational
- [ ] MinIO accessible
- [ ] GPU detected
- [ ] Critical workflows functional

---

### Task 8: Disable Maintenance Mode
**Time: 2 minutes**

```bash
# Disable maintenance mode
docker exec ablage-backend python -c "
from app.core.config import settings
settings.MAINTENANCE_MODE = False
"

# Verify API accessible
curl -s http://localhost:8000/health

# Send completion notification
/opt/ablage/scripts/send_notification.sh \
  --type "Maintenance Complete" \
  --message "Weekly maintenance completed successfully. System operational."
```

---

### Task 9: Post-Maintenance Report
**Time: 3 minutes**

```bash
# Generate maintenance report
cat > /var/log/ablage/weekly_maintenance_report_$(date +%F).md <<EOF
# Weekly Maintenance Report
**Date:** $(date)
**Duration:** [ACTUAL_DURATION] minutes
**Status:** [SUCCESS/ISSUES]

## Tasks Completed
- [x] Database VACUUM and ANALYZE
- [x] Log rotation and cleanup
- [x] Docker image cleanup
- [x] Security updates applied
- [x] Backup validation
- [x] Performance benchmarking

## Metrics
### Before Maintenance
- Disk usage: [BEFORE_DISK_USAGE]%
- Database size: [BEFORE_DB_SIZE]
- API P95 latency: [BEFORE_LATENCY]ms

### After Maintenance
- Disk usage: [AFTER_DISK_USAGE]% (Δ [DELTA]%)
- Database size: [AFTER_DB_SIZE] (Δ [DELTA])
- API P95 latency: [AFTER_LATENCY]ms

### Performance
- OCR throughput: [THROUGHPUT] docs/hour
- API requests/second: [RPS]
- GPU utilization: [GPU_UTIL]%

## Issues Found
- [LIST_ANY_ISSUES_OR_NONE]

## Action Items
- [ ] [ACTION_ITEM_1]
- [ ] [ACTION_ITEM_2]

## Next Maintenance
**Scheduled:** $(date -d "next Sunday 22:00" +"%Y-%m-%d %H:%M CET")

**Performed by:** [YOUR_NAME]
**Reviewed by:** [REVIEWER_NAME]
EOF

# Email report to team
mail -s "Weekly Maintenance Report - $(date +%F)" \
  ops-team@company.com < /var/log/ablage/weekly_maintenance_report_$(date +%F).md
```

---

## Rollback Procedure

**If Issues Occur During Maintenance:**

```bash
# STOP immediately
docker-compose stop

# Restore from pre-maintenance backup
docker exec ablage-postgres dropdb ablage
docker exec ablage-postgres createdb ablage
docker exec ablage-postgres pg_restore -U postgres -d ablage \
  /backups/pre_maintenance_${timestamp}.dump

# Restore MinIO
docker exec ablage-minio mc mirror /backups/minio_${timestamp}/ local/documents/

# Restore configuration
tar -xzf /mnt/backups/config_${timestamp}.tar.gz -C /

# Restart services
docker-compose up -d

# Verify health
curl http://localhost:8000/health

# Notify team
/opt/ablage/scripts/send_alert.sh \
  --severity HIGH \
  --message "Maintenance rollback performed. Investigating issue."
```

**⏱️ Rollback Time:** 10-15 minutes

---

## Success Criteria

### All Checks Must Pass
- [ ] All services running and healthy
- [ ] Database performance metrics within targets
- [ ] Disk usage reduced or maintained
- [ ] Backups validated and tested
- [ ] No critical security vulnerabilities
- [ ] Performance benchmarks met or exceeded
- [ ] No errors in health checks
- [ ] Maintenance report generated

### Target Metrics
- **Database Dead Tuple Ratio:** <5%
- **Disk Space Freed:** 5-20 GB
- **API P95 Latency:** <320ms
- **OCR Throughput:** >180 docs/hour
- **Backup Age:** <24 hours
- **Service Uptime:** 99.9% (allowing 90min maintenance)

---

## Maintenance Schedule

| Week | Additional Tasks |
|------|------------------|
| 1st of month | Full database VACUUM FULL |
| 2nd of month | Certificate expiration check |
| 3rd of month | Disaster recovery drill |
| 4th of month | Performance trend analysis |

---

## Related Documents
- [Daily Operations Checklist](daily_operations_checklist.md)
- [Monthly Health Audit Runbook](monthly_health_audit_runbook.md)
- [Performance Degradation Runbook](performance_degradation_runbook.md)
- [Backup Workflow](../backup_workflow.md)

---

## Revision History

| Version | Date       | Author      | Changes                         |
|---------|------------|-------------|---------------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial weekly maintenance runbook |
