# Operational Runbooks - Ablage-System

**Version:** 1.0
**Last Updated:** 2025-01-23
**Status:** Production-Ready
**Audience:** On-call Engineers, Operations Team

---

## Table of Contents

1. [Overview](#overview)
2. [Runbook Format](#runbook-format)
3. [GPU OOM (Out of Memory) Errors](#gpu-oom-out-of-memory-errors)
4. [High API Latency](#high-api-latency)
5. [Database Connection Exhaustion](#database-connection-exhaustion)
6. [OCR Processing Failures](#ocr-processing-failures)
7. [Redis Cache Failures](#redis-cache-failures)
8. [Disk Space Critical](#disk-space-critical)
9. [Authentication Failures](#authentication-failures)
10. [Certificate Expiration](#certificate-expiration)
11. [Emergency Procedures](#emergency-procedures)
12. [Post-Incident Review](#post-incident-review)

---

## Overview

### Purpose

This document provides step-by-step procedures for diagnosing and resolving common production incidents in the Ablage-System. Each runbook follows a standard format to ensure consistent incident response.

### When to Use

- **During Incidents**: Follow relevant runbook when alert fires
- **Proactive Investigation**: Diagnose issues before they become critical
- **Training**: Onboard new on-call engineers
- **Post-Mortems**: Reference procedures during incident reviews

### On-Call Prerequisites

Before going on-call, ensure you have:

- ✅ Access to Grafana dashboards (https://grafana.ablage.local)
- ✅ SSH access to production servers
- ✅ Database admin credentials (in password manager)
- ✅ PagerDuty/alerting system configured
- ✅ Documentation bookmarks saved
- ✅ Emergency contacts list
- ✅ Tested backup restoration procedure (at least once)

### Escalation Path

```
Level 1: On-Call Engineer (You)
   ↓ (if unresolved after 30 min)
Level 2: Senior Engineer / Team Lead
   ↓ (if critical system failure)
Level 3: CTO / Infrastructure Team
```

**Escalation Criteria:**
- Unable to diagnose issue after 30 minutes
- Data loss suspected
- Security incident confirmed
- Multiple critical services down

### Communication Channels

**During Incidents:**
- Slack: #incidents channel
- Email: incidents@ablage.local
- Phone: Emergency hotline (see contact list)

**Status Updates:**
- Update every 15 minutes during active incidents
- Use incident.io or similar for status tracking
- Notify stakeholders of resolution

---

## Runbook Format

Each runbook follows this structure:

### Incident: [Name]

**Severity:** Critical / High / Medium / Low

**Symptoms:**
- What users experience
- What alerts fire

**Diagnosis:**
1. Step-by-step investigation process
2. Queries to run
3. Dashboards to check

**Resolution:**
1. Immediate mitigation steps
2. Root cause fix
3. Verification steps

**Prevention:**
- Long-term fixes
- Monitoring improvements
- Configuration changes

**Related:**
- Dashboards
- Metrics
- Documentation links

---

## GPU OOM (Out of Memory) Errors

### Incident: GPU Out of Memory

**Severity:** High (OCR processing stops)

**Alert Name:** `GPUMemoryHigh` or `OCRProcessingFailed`

### Symptoms

**User Experience:**
- OCR processing fails with timeout errors
- Document status stuck in "processing"
- Error message: "Dokument konnte nicht verarbeitet werden"

**System Behavior:**
- Worker logs show `torch.cuda.OutOfMemoryError`
- GPU memory usage at 100%
- New OCR jobs not starting
- Celery workers may crash

**Metrics:**
```promql
# GPU memory at 100%
gpu_memory_used_bytes / gpu_memory_total_bytes > 0.95

# OCR failures increased
rate(ocr_documents_processed_total{status="failed"}[5m]) > 0
```

**Grafana Dashboard:**
- [GPU Monitoring](https://grafana.ablage.local/d/ablage-gpu-metrics)

### Diagnosis

#### Step 1: Confirm GPU OOM

**SSH to worker server:**
```bash
ssh ablage-worker-01
```

**Check GPU memory:**
```bash
nvidia-smi
```

**Expected Output (OOM):**
```
+-----------------------------------------------------------------------------+
| Processes:                                                                  |
|  GPU   GI   CI        PID   Type   Process name                  GPU Memory |
|        ID   ID                                                      Usage   |
|=============================================================================|
|    0   N/A  N/A     12345      C   python                            15.8GB |
+-----------------------------------------------------------------------------+
```

**If Memory Usage > 14.4 GB (90%)**: OOM confirmed

#### Step 2: Check Worker Logs

```bash
docker logs ablage-worker-01 --tail=100 | grep -i "outofmemory"
```

**Look for:**
```
torch.cuda.OutOfMemoryError: CUDA out of memory. Tried to allocate 2.00 GiB (GPU 0; 16.00 GiB total capacity; 14.50 GiB already allocated; 1.20 GiB free; 14.80 GiB reserved in total by PyTorch)
```

#### Step 3: Identify Batch Size

**Check current batch size:**
```bash
docker exec ablage-worker-01 python -c "from app.services.ocr.gpu_manager import GPUBatchProcessor; print(f'Optimal batch size: {GPUBatchProcessor().optimal_batch_size}')"
```

**Check recent jobs:**
```bash
# Check last 10 OCR jobs for batch information
docker exec ablage-backend python -c "
from app.db import SessionLocal
from app.models import OCRJob
db = SessionLocal()
jobs = db.query(OCRJob).order_by(OCRJob.created_at.desc()).limit(10).all()
for job in jobs:
    print(f'Job {job.id}: Batch size {job.batch_size}, Status: {job.status}')
"
```

#### Step 4: Check for Memory Leaks

**Monitor memory over time:**
```bash
watch -n 1 "nvidia-smi --query-gpu=memory.used --format=csv,noheader"
```

**If memory steadily increases even when idle:** Memory leak suspected

### Resolution

#### Immediate Mitigation (5 minutes)

**Step 1: Restart Worker (clears GPU memory)**

```bash
# Graceful restart (waits for current jobs to finish, max 5 min)
docker exec ablage-worker-01 celery -A app.celery control shutdown

# Wait for shutdown (max 5 min)
sleep 10

# Start worker
docker restart ablage-worker-01
```

**Expected Result:**
- GPU memory drops to <1 GB
- Workers start accepting jobs again
- OCR processing resumes

**Verify:**
```bash
nvidia-smi
docker logs ablage-worker-01 --tail=20
```

#### Step 2: Reduce Batch Size (if reoccurs)

**Edit worker configuration:**
```bash
# Edit environment variables
sudo nano /etc/ablage/worker.env
```

**Change:**
```bash
# Before
MAX_BATCH_SIZE=32

# After
MAX_BATCH_SIZE=16  # Reduce by 50%
```

**Restart worker:**
```bash
docker restart ablage-worker-01
```

#### Step 3: Enable Dynamic Batch Sizing

**Verify dynamic batch sizing is enabled:**
```bash
docker exec ablage-worker-01 python -c "
from app.core.config import settings
print(f'Dynamic batch sizing: {settings.ENABLE_DYNAMIC_BATCH_SIZING}')
"
```

**If disabled, enable:**
```bash
# In /etc/ablage/worker.env
ENABLE_DYNAMIC_BATCH_SIZING=true
```

#### Root Cause Fix (30-60 minutes)

**Option A: Model Quantization (reduces memory by 40%)**

```bash
# Switch to quantized model
docker exec ablage-backend python -c "
from app.services.ocr.model_manager import ModelManager
manager = ModelManager()
manager.enable_quantization('deepseek')
"
```

**Expected Impact:**
- Memory usage: 14.7 GB → 9.2 GB (37% reduction)
- Batch size: 8 → 16 (2x increase possible)
- Slight accuracy decrease (98.2% → 97.8%, acceptable)

**Option B: GPU Memory Guard (automatic recovery)**

**Verify GPU memory guard is active:**
```python
# Check app/services/ocr/gpu_batch_processor.py
with gpu_memory_guard(threshold_gb=13.6):  # 85% of 16GB
    results = model.process_batch(images)
```

**If not present, add to processing code.**

**Option C: Add Second GPU Worker (if available)**

```bash
# Start second worker on different GPU
docker run -d \
  --name ablage-worker-02 \
  --gpus '"device=1"' \  # Use GPU 1
  -e CELERY_WORKER_NAME=worker-02 \
  ablage/worker:latest
```

#### Verification

**Run test OCR job:**
```bash
curl -X POST https://api.ablage.local/api/v1/ocr/process \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_document.pdf" \
  -F "backend=deepseek"
```

**Monitor GPU memory during processing:**
```bash
watch -n 1 "nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader"
```

**Success Criteria:**
- GPU memory stays below 85% (13.6 GB)
- OCR job completes successfully
- Worker logs show no OOM errors

### Prevention

#### 1. Monitoring & Alerting

**Add Prometheus alert:**
```yaml
# prometheus/alerts/gpu.yml
groups:
  - name: gpu_alerts
    rules:
      - alert: GPUMemoryHigh
        expr: (gpu_memory_used_bytes / gpu_memory_total_bytes) > 0.85
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "GPU memory usage high: {{ $value | humanizePercentage }}"
          description: "GPU memory on {{ $labels.instance }} is above 85% for 2 minutes"
          runbook_url: "https://docs.ablage.local/runbooks/gpu-oom"
```

#### 2. Configuration Tuning

**Set conservative batch sizes:**
```bash
# /etc/ablage/worker.env
MAX_BATCH_SIZE=16  # Down from 32
BATCH_SIZE_SAFETY_MARGIN=0.15  # Reserve 15% memory
ENABLE_DYNAMIC_BATCH_SIZING=true
```

#### 3. Model Optimization

**Enable quantization by default:**
```python
# app/core/config.py
class Settings(BaseSettings):
    ENABLE_MODEL_QUANTIZATION: bool = True
    QUANTIZATION_DTYPE: str = "int8"
```

#### 4. Resource Monitoring

**Set up daily GPU memory report:**
```bash
# cron job: daily at 9 AM
0 9 * * * /usr/local/bin/gpu-memory-report.sh | mail -s "Daily GPU Report" ops@ablage.local
```

**Script content:**
```bash
#!/bin/bash
# /usr/local/bin/gpu-memory-report.sh

echo "GPU Memory Report - $(date)"
echo "================================"
nvidia-smi
echo ""
echo "Peak Memory (last 24h):"
docker exec prometheus promtool query instant \
  'max_over_time(gpu_memory_used_bytes[24h]) / gpu_memory_total_bytes * 100'
```

### Related

**Dashboards:**
- [GPU Monitoring](https://grafana.ablage.local/d/ablage-gpu-metrics)
- [OCR Performance](https://grafana.ablage.local/d/ablage-business-metrics)

**Metrics:**
```promql
# Current GPU memory usage
gpu_memory_used_bytes / gpu_memory_total_bytes

# GPU memory over time
rate(gpu_memory_used_bytes[5m])

# OCR failures
rate(ocr_documents_processed_total{status="failed"}[5m])
```

**Documentation:**
- [GPU Optimization Guide](../Optimization/performance_optimization_guide.md)
- [OCR Service Architecture](../Architecture/Backend_Services/ocr_service_architecture.md)

---

## High API Latency

### Incident: High API Response Time

**Severity:** High (user experience degradation)

**Alert Name:** `HighAPILatency` or `SLOViolation`

### Symptoms

**User Experience:**
- Slow page loads (> 5 seconds)
- API requests timing out
- "Verbindungsprobleme" (connection issues) errors

**System Behavior:**
- P95 latency > 320ms (SLO violation)
- Request queue building up
- CPU or database saturation

**Metrics:**
```promql
# P95 latency above SLO
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket[5m])
) > 0.32

# Request rate normal but latency high
rate(http_requests_total[5m]) > 50
AND
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.32
```

**Grafana Dashboard:**
- [Application Metrics](https://grafana.ablage.local/d/ablage-app-metrics)

### Diagnosis

#### Step 1: Identify Affected Endpoints

**Check Grafana - Request Duration by Endpoint:**
```promql
topk(10,
  histogram_quantile(0.95,
    rate(http_request_duration_seconds_bucket[5m])
  )
) by (endpoint)
```

**Look for endpoints with >320ms P95 latency.**

**Alternative - Check logs:**
```bash
docker logs ablage-backend --since=10m | grep -i "slow_request" | tail -20
```

#### Step 2: Check System Resources

**CPU Usage:**
```bash
docker stats ablage-backend --no-stream
```

**Expected (healthy):**
```
CONTAINER       CPU %     MEM USAGE / LIMIT
ablage-backend  45.2%     2.1GB / 4GB
```

**If CPU > 80%:** CPU bottleneck suspected

**Memory Usage:**
```bash
free -h
```

**If available memory < 500MB:** Memory pressure suspected

#### Step 3: Check Database

**PostgreSQL connection count:**
```bash
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT COUNT(*) AS active_connections,
         state
  FROM pg_stat_activity
  WHERE datname = 'ablage'
  GROUP BY state;
"
```

**Expected (healthy):**
```
 active_connections | state
--------------------+--------
                 15 | active
                  3 | idle
```

**If active > 20:** Connection pool exhaustion suspected

**Slow queries:**
```bash
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT pid, usename, query_start, state, query
  FROM pg_stat_activity
  WHERE state = 'active'
    AND query_start < NOW() - INTERVAL '5 seconds'
  ORDER BY query_start;
"
```

**If queries running > 5 seconds:** Slow query suspected

#### Step 4: Check Cache Hit Rate

```promql
rate(cache_hits_total[5m]) /
(rate(cache_hits_total[5m]) + rate(cache_misses_total[5m])) * 100
```

**Expected:** >80%
**If < 70%:** Cache issues suspected

#### Step 5: Analyze Specific Slow Requests

**Enable request tracing (if not already):**
```bash
# View recent slow requests from logs
docker logs ablage-backend --since=5m | grep "request_duration_ms" | \
  jq 'select(.request_duration_ms > 500)' | head -10
```

**Example output:**
```json
{
  "timestamp": "2025-01-23T15:30:45Z",
  "level": "WARNING",
  "message": "slow_request",
  "endpoint": "/api/v1/documents",
  "method": "GET",
  "request_duration_ms": 1250,
  "user_id": "user_456",
  "query_params": {"limit": 100, "skip": 10000}
}
```

**Note:** `skip=10000` with offset pagination is inefficient (see Resolution).

### Resolution

#### Immediate Mitigation (2-5 minutes)

**Step 1: Scale Backend Horizontally (if available)**

```bash
# Increase backend replicas
docker service scale ablage-backend=4  # From 2 to 4

# Or with docker-compose
docker-compose up -d --scale backend=4
```

**Expected Impact:**
- Distributes load across more instances
- Latency should drop within 1-2 minutes

**Step 2: Restart Slow Instance (if single instance is slow)**

```bash
# Identify slow instance
docker ps | grep ablage-backend

# Graceful restart
docker restart ablage-backend
```

**Caution:** Only restart if you have multiple instances OR during low-traffic period.

**Step 3: Clear Cache (if cache hit rate low)**

```bash
# Connect to Redis
docker exec -it ablage-redis redis-cli

# Check memory usage
INFO memory

# If memory at 100%, clear LRU keys
CONFIG SET maxmemory-policy allkeys-lru

# Or flush all (nuclear option - use carefully)
FLUSHALL
```

**Expected Impact:**
- Temporarily slower (cold cache)
- Gradual improvement as cache warms up (15-30 min)

#### Root Cause Fixes (30-60 minutes)

**Fix 1: Optimize Slow Endpoint**

**Example: `/api/v1/documents` with offset pagination**

**Before (slow):**
```python
@app.get("/documents")
async def list_documents(skip: int = 0, limit: int = 20, db: AsyncSession = Depends(get_db)):
    documents = await db.execute(
        select(Document).offset(skip).limit(limit)
    )
    return documents.scalars().all()
```

**After (fast - cursor pagination):**
```python
@app.get("/documents")
async def list_documents(
    cursor: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    query = select(Document).order_by(Document.id).limit(limit)
    if cursor:
        query = query.where(Document.id > cursor)

    documents = await db.execute(query)
    results = documents.scalars().all()

    next_cursor = results[-1].id if results else None
    return {
        "data": results,
        "pagination": {"next_cursor": next_cursor}
    }
```

**Deploy:**
```bash
# Build and deploy new version
docker build -t ablage-backend:fix-pagination .
docker service update --image ablage-backend:fix-pagination ablage-backend
```

**Fix 2: Add Database Index**

**If slow queries identified:**
```sql
-- Example: Slow query on documents filtered by owner_id and created_at
-- CREATE INDEX CONCURRENTLY to avoid table lock
CREATE INDEX CONCURRENTLY idx_documents_owner_created
ON documents(owner_id, created_at DESC);
```

**Apply migration:**
```bash
docker exec ablage-backend alembic upgrade head
```

**Fix 3: Increase Connection Pool**

**Edit configuration:**
```bash
sudo nano /etc/ablage/backend.env
```

**Change:**
```bash
# Before
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# After (if connections exhausted)
DB_POOL_SIZE=30
DB_MAX_OVERFLOW=20
```

**Restart backend:**
```bash
docker restart ablage-backend
```

**Fix 4: Enable Response Compression**

**Add middleware (if not already enabled):**
```python
# app/main.py
from fastapi.middleware.gzip import GZipMiddleware

app.add_middleware(GZipMiddleware, minimum_size=1000)
```

**Expected Impact:**
- Payload size reduced by 60-70%
- Network transfer time reduced significantly

#### Verification

**Test affected endpoint:**
```bash
# Measure response time
time curl -w "\nTime: %{time_total}s\n" \
  -H "Authorization: Bearer $TOKEN" \
  https://api.ablage.local/api/v1/documents?limit=20
```

**Expected:** <200ms

**Check Grafana:**
- P95 latency should drop below 320ms within 5 minutes
- Request queue length should decrease

**Load test (optional):**
```bash
# Using Apache Bench
ab -n 1000 -c 10 -H "Authorization: Bearer $TOKEN" \
  https://api.ablage.local/api/v1/documents
```

**Success Criteria:**
- P95 latency < 320ms
- No 5xx errors
- Connection pool not exhausted

### Prevention

#### 1. Monitoring & Alerting

**Add Prometheus alert:**
```yaml
# prometheus/alerts/api.yml
groups:
  - name: api_alerts
    rules:
      - alert: HighAPILatency
        expr: |
          histogram_quantile(0.95,
            rate(http_request_duration_seconds_bucket{job="ablage-backend"}[5m])
          ) > 0.32
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "API latency above SLO: {{ $value | humanizeDuration }}"
          description: "P95 latency on {{ $labels.endpoint }} is {{ $value }}s (SLO: 320ms)"
          runbook_url: "https://docs.ablage.local/runbooks/high-api-latency"
```

#### 2. Performance Testing

**Add to CI/CD pipeline:**
```yaml
# .github/workflows/performance-test.yml
- name: Performance Test
  run: |
    docker-compose -f docker-compose.test.yml up -d
    sleep 10
    locust -f tests/performance/api_load_test.py \
      --host=http://localhost:8000 \
      --users=100 \
      --spawn-rate=10 \
      --run-time=5m \
      --headless \
      --only-summary
```

**Fail build if P95 > 320ms.**

#### 3. Database Optimization

**Regular index maintenance:**
```sql
-- Weekly maintenance job
ANALYZE;  -- Update statistics
REINDEX DATABASE ablage;  -- Rebuild indexes
```

**Add slow query logging:**
```ini
# postgresql.conf
log_min_duration_statement = 500  # Log queries > 500ms
```

#### 4. Auto-Scaling

**Configure auto-scaling (if using Kubernetes):**
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: ablage-backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: ablage-backend
  minReplicas: 2
  maxReplicas: 8
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: http_request_duration_p95
      target:
        type: AverageValue
        averageValue: "250m"  # 250ms
```

### Related

**Dashboards:**
- [Application Metrics](https://grafana.ablage.local/d/ablage-app-metrics)
- [Database Performance](https://grafana.ablage.local/d/ablage-db-metrics)

**Metrics:**
```promql
# P95 latency by endpoint
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket[5m])
) by (endpoint)

# Database connection pool usage
db_connections_active / db_connections_pool_size * 100

# Cache hit rate
rate(cache_hits_total[5m]) /
(rate(cache_hits_total[5m]) + rate(cache_misses_total[5m]))
```

**Documentation:**
- [Performance Optimization Guide](../Optimization/performance_optimization_guide.md)
- [API Documentation](../API_Documentation/api_overview.md)

---

## Database Connection Exhaustion

### Incident: Database Connection Pool Exhausted

**Severity:** Critical (API requests fail)

**Alert Name:** `DatabaseConnectionPoolExhausted`

### Symptoms

**User Experience:**
- API requests fail with 500 errors
- Error message: "Datenbankverbindung fehlgeschlagen"
- Slow or unresponsive application

**System Behavior:**
- Backend logs show `QueuePool limit exceeded`
- Database shows many connections in "idle" or "idle in transaction" state
- New requests wait indefinitely for connections

**Metrics:**
```promql
# Connection pool at 100%
db_connections_active >= db_connections_pool_size

# Waiting connections
db_connections_waiting > 0
```

**Grafana Dashboard:**
- [Application Metrics](https://grafana.ablage.local/d/ablage-app-metrics) → Database section

### Diagnosis

#### Step 1: Confirm Connection Exhaustion

**Check PostgreSQL connections:**
```bash
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT COUNT(*) AS total_connections,
         state,
         wait_event_type
  FROM pg_stat_activity
  WHERE datname = 'ablage'
  GROUP BY state, wait_event_type
  ORDER BY total_connections DESC;
"
```

**Expected Output (exhausted):**
```
 total_connections |        state        | wait_event_type
-------------------+---------------------+-----------------
                30 | idle                | NULL
                10 | idle in transaction | Client
                 5 | active              | NULL
```

**If total >= max_connections (95):** Exhaustion confirmed

**Check pool configuration:**
```bash
docker exec ablage-backend python -c "
from app.core.config import settings
print(f'Pool size: {settings.DB_POOL_SIZE}')
print(f'Max overflow: {settings.DB_MAX_OVERFLOW}')
print(f'Total possible: {settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW}')
"
```

#### Step 2: Identify Connection Leaks

**Long-running idle transactions:**
```bash
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT pid,
         usename,
         application_name,
         state,
         state_change,
         NOW() - state_change AS duration,
         query
  FROM pg_stat_activity
  WHERE datname = 'ablage'
    AND state = 'idle in transaction'
    AND NOW() - state_change > INTERVAL '5 minutes'
  ORDER BY duration DESC;
"
```

**If many "idle in transaction" > 5 minutes:** Connection leak suspected

#### Step 3: Check for Blocked Transactions

**Blocking locks:**
```bash
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT blocked_locks.pid AS blocked_pid,
         blocked_activity.usename AS blocked_user,
         blocking_locks.pid AS blocking_pid,
         blocking_activity.usename AS blocking_user,
         blocked_activity.query AS blocked_statement,
         blocking_activity.query AS blocking_statement
  FROM pg_catalog.pg_locks blocked_locks
  JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
  JOIN pg_catalog.pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
  JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
  WHERE NOT blocked_locks.granted;
"
```

**If results:** Lock contention is contributing to exhaustion

### Resolution

#### Immediate Mitigation (2 minutes)

**Step 1: Terminate Idle Connections**

**Kill long-running idle transactions:**
```bash
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = 'ablage'
    AND state = 'idle in transaction'
    AND NOW() - state_change > INTERVAL '5 minutes';
"
```

**Expected:** Connections freed, new requests succeed

**Caution:** Only terminate "idle in transaction", NOT "active" queries.

**Step 2: Restart Backend (if connections still stuck)**

```bash
# Graceful restart
docker restart ablage-backend

# Wait for restart
sleep 10

# Verify connections dropped
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT COUNT(*) FROM pg_stat_activity WHERE datname = 'ablage';
"
```

**Expected:** Connection count drops to <10

#### Root Cause Fixes (30-60 minutes)

**Fix 1: Increase Connection Pool Size**

**Edit configuration:**
```bash
sudo nano /etc/ablage/backend.env
```

**Change:**
```bash
# Before
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10
POOL_TIMEOUT=30

# After
DB_POOL_SIZE=30       # Increase base pool
DB_MAX_OVERFLOW=20    # Increase overflow
POOL_TIMEOUT=15       # Reduce timeout (fail fast)
POOL_RECYCLE=3600     # Recycle connections after 1h
POOL_PRE_PING=true    # Validate connections before use
```

**Restart backend:**
```bash
docker restart ablage-backend
```

**Fix 2: Fix Connection Leaks in Code**

**Add context manager to ensure connections close:**

**Before (leak):**
```python
@app.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    documents = await db.execute(select(Document))
    return documents.scalars().all()
    # Connection may not be returned to pool if exception occurs
```

**After (safe):**
```python
@app.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    try:
        documents = await db.execute(select(Document))
        return documents.scalars().all()
    finally:
        await db.close()  # Explicit close
```

**Better - use dependency injection properly:**
```python
# app/api/dependencies.py
async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

**Fix 3: Add Connection Pool Monitoring**

**Add Prometheus metrics:**
```python
# app/db/monitoring.py
from prometheus_client import Gauge

db_pool_size = Gauge('db_connections_pool_size', 'Database connection pool size')
db_pool_checked_out = Gauge('db_connections_checked_out', 'Checked out connections')
db_pool_overflow = Gauge('db_connections_overflow', 'Overflow connections')

def update_pool_metrics():
    pool = engine.pool
    db_pool_size.set(pool.size())
    db_pool_checked_out.set(pool.checkedout())
    db_pool_overflow.set(pool.overflow())

# Call this periodically (every 10s)
```

**Fix 4: Implement Statement Timeout**

**Prevent long-running queries from holding connections:**
```python
# app/core/config.py
DATABASE_URL = "postgresql+asyncpg://...?options=-c statement_timeout=30000"
# 30 seconds max per query
```

**Or set in PostgreSQL config:**
```ini
# postgresql.conf
statement_timeout = 30000  # 30 seconds
```

#### Verification

**Check connection count:**
```bash
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT COUNT(*) AS connections FROM pg_stat_activity WHERE datname = 'ablage';
"
```

**Expected:** <50% of pool size during normal operation

**Load test:**
```bash
# Concurrent requests
ab -n 100 -c 20 -H "Authorization: Bearer $TOKEN" \
  https://api.ablage.local/api/v1/documents
```

**Success Criteria:**
- No connection pool exhaustion errors
- All requests complete successfully
- Connection count returns to baseline after load

### Prevention

#### 1. Monitoring & Alerting

**Add Prometheus alert:**
```yaml
# prometheus/alerts/database.yml
groups:
  - name: database_alerts
    rules:
      - alert: DatabaseConnectionPoolHigh
        expr: db_connections_active / db_connections_pool_size > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Database connection pool at {{ $value | humanizePercentage }}"
          description: "Connection pool usage high on {{ $labels.instance }}"

      - alert: DatabaseConnectionPoolExhausted
        expr: db_connections_waiting > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database connection pool exhausted"
          description: "{{ $value }} connections waiting for pool on {{ $labels.instance }}"
          runbook_url: "https://docs.ablage.local/runbooks/db-connection-exhaustion"
```

#### 2. Connection Lifecycle Management

**Set connection lifecycle parameters:**
```python
# app/db/engine.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=30,
    max_overflow=20,
    pool_timeout=15,
    pool_recycle=3600,      # Recycle after 1 hour
    pool_pre_ping=True,     # Validate before use
    echo_pool="debug"       # Log pool events (dev only)
)
```

#### 3. Regular Maintenance

**Weekly connection audit:**
```bash
# Check for idle connections
docker exec ablage-postgres psql -U postgres -d ablage -c "
  SELECT state, COUNT(*)
  FROM pg_stat_activity
  WHERE datname = 'ablage'
  GROUP BY state;
"
```

**Monthly review:**
- Analyze connection pool metrics (avg, peak)
- Adjust pool size if needed
- Review slow query log for connection-holding queries

### Related

**Dashboards:**
- [Application Metrics](https://grafana.ablage.local/d/ablage-app-metrics)
- [Database Performance](https://grafana.ablage.local/d/ablage-db-metrics)

**Metrics:**
```promql
# Connection pool usage
db_connections_active / db_connections_pool_size * 100

# Waiting connections
db_connections_waiting

# Connection acquisition time
rate(db_connection_acquisition_seconds_sum[5m]) /
rate(db_connection_acquisition_seconds_count[5m])
```

**Documentation:**
- [Database Architecture](../Architecture/Database/database_architecture.md)
- [Performance Optimization](../Optimization/performance_optimization_guide.md)

---

## OCR Processing Failures

### Incident: OCR Processing Failures

**Severity:** High (core functionality impaired)

**Alert Name:** `OCRFailureRateHigh` or `OCRProcessingStalled`

### Symptoms

**User Experience:**
- Documents stuck in "processing" status
- OCR fails with generic error message
- Processing never completes (timeout after 5 minutes)

**System Behavior:**
- High OCR failure rate (>5%)
- Worker logs show exceptions
- GPU may be idle despite queued jobs

**Metrics:**
```promql
# OCR failure rate > 5%
rate(ocr_documents_processed_total{status="failed"}[5m]) /
rate(ocr_documents_processed_total[5m]) > 0.05

# No documents processed in 5 minutes
rate(ocr_documents_processed_total{status="completed"}[5m]) == 0
```

**Grafana Dashboard:**
- [Business Metrics](https://grafana.ablage.local/d/ablage-business-metrics)
- [GPU Monitoring](https://grafana.ablage.local/d/ablage-gpu-metrics)

### Diagnosis

#### Step 1: Check OCR Job Queue

**Celery queue length:**
```bash
docker exec ablage-worker-01 celery -A app.celery inspect active
docker exec ablage-worker-01 celery -A app.celery inspect reserved
```

**Expected (healthy):**
- Active: 1-2 tasks per worker
- Reserved: 0-5 tasks per worker

**If Active == 0 AND Reserved > 0:** Worker stuck

#### Step 2: Check Worker Logs

```bash
docker logs ablage-worker-01 --tail=100 | grep -A 10 "ERROR"
```

**Common errors:**

**A) Model Loading Error:**
```
FileNotFoundError: Model checkpoint not found: /models/deepseek/model.safetensors
```

**B) GPU Error:**
```
RuntimeError: CUDA error: device-side assert triggered
```

**C) Timeout Error:**
```
celery.exceptions.SoftTimeLimitExceeded: TimeLimitExceeded(300,)
```

**D) Memory Error:**
```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

#### Step 3: Check GPU Status

```bash
nvidia-smi
```

**If GPU utilization == 0% BUT jobs queued:** GPU not being used

**If GPU processes crashed:**
```
+-----------------------------------------------------------------------------+
| Processes:                                                                  |
|  No running processes found                                                 |
+-----------------------------------------------------------------------------+
```

#### Step 4: Test OCR Manually

**Run test OCR job:**
```bash
docker exec ablage-worker-01 python -c "
from app.services.ocr.deepseek import DeepSeekOCR
from PIL import Image
import numpy as np

ocr = DeepSeekOCR()
test_image = np.random.randint(0, 255, (1024, 768, 3), dtype=np.uint8)
result = ocr.process(test_image)
print(f'OCR result: {result[:100]}...')
"
```

**If this fails:** OCR service broken
**If this succeeds:** Queue or task distribution issue

### Resolution

#### Immediate Mitigation (5 minutes)

**Step 1: Restart Worker**

```bash
# Graceful restart
docker exec ablage-worker-01 celery -A app.celery control shutdown

# Wait for shutdown
sleep 10

# Start worker
docker restart ablage-worker-01

# Verify worker started
docker logs ablage-worker-01 --tail=20
```

**Expected:** Worker starts accepting jobs

**Step 2: Purge Failed Jobs (if queue blocked)**

```bash
# Purge failed tasks
docker exec ablage-worker-01 celery -A app.celery purge

# Confirm: y
```

**Caution:** This deletes all queued jobs. Only use if queue is completely blocked.

**Step 3: Switch OCR Backend (temporary)**

**If DeepSeek failing, switch to GOT-OCR:**

```bash
# Update default backend
docker exec ablage-backend python -c "
from app.core.config import settings
settings.DEFAULT_OCR_BACKEND = 'got_ocr'  # Fallback to GOT-OCR
"
```

**Or via environment variable:**
```bash
# Edit /etc/ablage/backend.env
DEFAULT_OCR_BACKEND=got_ocr

docker restart ablage-backend
```

#### Root Cause Fixes

**Fix 1: Model File Corruption**

**Symptoms:** `FileNotFoundError` or `RuntimeError: Error loading state dict`

**Resolution:**
```bash
# Re-download model
docker exec ablage-worker-01 python -c "
from app.services.ocr.model_manager import ModelManager
manager = ModelManager()
manager.download_model('deepseek', force=True)  # Force re-download
"
```

**Expected:** Model re-downloaded (2-5 GB, takes 5-10 minutes)

**Fix 2: CUDA Error**

**Symptoms:** `RuntimeError: CUDA error`

**Resolution:**
```bash
# Reset GPU
nvidia-smi --gpu-reset

# Restart worker
docker restart ablage-worker-01
```

**If persists, reboot server:**
```bash
sudo reboot
```

**Fix 3: Timeout Too Short**

**Symptoms:** `SoftTimeLimitExceeded` for large documents

**Resolution:**
```bash
# Edit worker configuration
sudo nano /etc/ablage/worker.env
```

**Change:**
```bash
# Before
CELERY_TASK_TIME_LIMIT=300  # 5 minutes

# After (for large documents)
CELERY_TASK_TIME_LIMIT=600  # 10 minutes
CELERY_TASK_SOFT_TIME_LIMIT=540  # 9 minutes (warning)
```

**Restart worker:**
```bash
docker restart ablage-worker-01
```

**Fix 4: OCR Backend Selection Logic**

**If auto-selection choosing wrong backend:**

**Update orchestrator logic:**
```python
# app/services/ocr/orchestrator.py
async def select_backend(self, document: Document) -> str:
    """Select optimal OCR backend based on document characteristics."""

    # High-quality scans: DeepSeek (best accuracy)
    if document.dpi >= 300 and document.file_size_mb < 10:
        return "deepseek"

    # Large documents: GOT-OCR (faster)
    elif document.page_count > 50:
        return "got_ocr"

    # Low-quality scans: Surya (better preprocessing)
    elif document.dpi < 150:
        return "surya"

    # Default: DeepSeek
    else:
        return "deepseek"
```

#### Verification

**Test OCR endpoint:**
```bash
# Upload and process test document
curl -X POST https://api.ablage.local/api/v1/ocr/process \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@test_invoice.pdf" \
  -F "backend=deepseek"
```

**Expected response:**
```json
{
  "job_id": "job_789",
  "status": "queued",
  "estimated_completion": "2025-01-23T15:35:00Z"
}
```

**Monitor job:**
```bash
# Poll status every 5 seconds
while true; do
  curl -s https://api.ablage.local/api/v1/ocr/status/job_789 \
    -H "Authorization: Bearer $TOKEN" | jq '.status'
  sleep 5
done
```

**Success Criteria:**
- Job completes within expected time (2-5 seconds for 1 page)
- Status transitions: queued → processing → completed
- Extracted text is accurate

### Prevention

#### 1. Monitoring & Alerting

**Add Prometheus alert:**
```yaml
# prometheus/alerts/ocr.yml
groups:
  - name: ocr_alerts
    rules:
      - alert: OCRFailureRateHigh
        expr: |
          rate(ocr_documents_processed_total{status="failed"}[5m]) /
          rate(ocr_documents_processed_total[5m]) > 0.05
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "OCR failure rate high: {{ $value | humanizePercentage }}"
          description: "OCR failures above 5% threshold"

      - alert: OCRProcessingStalled
        expr: rate(ocr_documents_processed_total{status="completed"}[5m]) == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "OCR processing stalled - no completions in 5 minutes"
          runbook_url: "https://docs.ablage.local/runbooks/ocr-failures"
```

#### 2. Health Checks

**Add OCR health endpoint:**
```python
# app/api/v1/health.py
@router.get("/health/ocr")
async def ocr_health_check():
    """Test OCR processing with dummy image."""
    try:
        from app.services.ocr.deepseek import DeepSeekOCR
        import numpy as np

        ocr = DeepSeekOCR()
        test_image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = ocr.process(test_image)

        return {
            "status": "healthy",
            "backend": "deepseek",
            "gpu_available": torch.cuda.is_available()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }, 503
```

**Monitor health endpoint:**
```yaml
# prometheus/prometheus.yml
scrape_configs:
  - job_name: 'ablage-health'
    metrics_path: '/api/v1/health/ocr'
    scrape_interval: 60s
    static_configs:
      - targets: ['ablage-backend:8000']
```

#### 3. Automatic Fallback

**Implement retry with different backend:**
```python
# app/workers/ocr_tasks.py
@celery_app.task(bind=True, max_retries=3)
async def process_document_task(self, document_id: str, backend: str = "auto"):
    try:
        result = await ocr_backends[backend].process(document)
        return result
    except Exception as e:
        logger.error(f"OCR failed with {backend}", error=str(e))

        # Retry with different backend
        if self.request.retries == 0 and backend == "deepseek":
            logger.info("Retrying with got_ocr backend")
            raise self.retry(exc=e, kwargs={"backend": "got_ocr"}, countdown=10)
        elif self.request.retries == 1 and backend == "got_ocr":
            logger.info("Retrying with surya backend")
            raise self.retry(exc=e, kwargs={"backend": "surya"}, countdown=10)
        else:
            # All backends failed
            raise
```

#### 4. Regular Testing

**Daily synthetic monitoring:**
```bash
#!/bin/bash
# /usr/local/bin/ocr-synthetic-test.sh

# Upload test document
JOB_ID=$(curl -s -X POST https://api.ablage.local/api/v1/ocr/process \
  -H "Authorization: Bearer $MONITORING_TOKEN" \
  -F "file=@/opt/ablage/test-documents/sample.pdf" \
  | jq -r '.job_id')

# Wait for completion (max 60s)
for i in {1..12}; do
  STATUS=$(curl -s https://api.ablage.local/api/v1/ocr/status/$JOB_ID \
    -H "Authorization: Bearer $MONITORING_TOKEN" \
    | jq -r '.status')

  if [ "$STATUS" = "completed" ]; then
    echo "OCR synthetic test: PASS"
    exit 0
  fi

  sleep 5
done

echo "OCR synthetic test: FAIL (timeout)"
exit 1
```

**Add to cron:**
```
0 */6 * * * /usr/local/bin/ocr-synthetic-test.sh | logger -t ocr-monitor
```

### Related

**Dashboards:**
- [Business Metrics](https://grafana.ablage.local/d/ablage-business-metrics)
- [GPU Monitoring](https://grafana.ablage.local/d/ablage-gpu-metrics)

**Metrics:**
```promql
# OCR success rate
rate(ocr_documents_processed_total{status="completed"}[5m]) /
rate(ocr_documents_processed_total[5m]) * 100

# Processing time by backend
histogram_quantile(0.95,
  rate(ocr_processing_duration_seconds_bucket[5m])
) by (backend)

# Queue length
celery_queue_length{queue="ocr"}
```

**Documentation:**
- [OCR Service Architecture](../Architecture/Backend_Services/ocr_service_architecture.md)
- [GPU Optimization Guide](../Optimization/performance_optimization_guide.md)

---

## Redis Cache Failures

### Incident: Redis Cache Unavailable

**Severity:** Medium (degraded performance, not total failure)

**Alert Name:** `RedisCacheDown` or `CacheHitRateLow`

### Symptoms

**User Experience:**
- Slower API responses (cache miss → database query)
- No immediate errors (graceful degradation)

**System Behavior:**
- Backend logs show Redis connection errors
- Cache hit rate drops to 0%
- Database load increases (all queries hit database)

**Metrics:**
```promql
# Cache hit rate == 0%
rate(cache_hits_total[5m]) /
(rate(cache_hits_total[5m]) + rate(cache_misses_total[5m])) == 0

# Redis unavailable
redis_up == 0
```

### Diagnosis

#### Step 1: Check Redis Status

```bash
# Check if Redis container is running
docker ps | grep ablage-redis

# If not running: Start Redis
docker start ablage-redis

# If running: Check logs
docker logs ablage-redis --tail=50
```

**Common issues:**
- Out of memory
- Config error
- Disk full (for persistence)

#### Step 2: Test Redis Connection

```bash
# Connect to Redis
docker exec -it ablage-redis redis-cli

# Test ping
PING
# Expected: PONG

# Check memory
INFO memory

# Check keys
DBSIZE
```

**If cannot connect:** Redis is down
**If memory at 100%:** Out of memory

#### Step 3: Check Backend Connection

```bash
# Test Redis connection from backend
docker exec ablage-backend python -c "
from redis.asyncio import Redis
import asyncio

async def test():
    redis = Redis(host='ablage-redis', port=6379, decode_responses=True)
    try:
        await redis.ping()
        print('Redis: Connected')
    except Exception as e:
        print(f'Redis: Failed - {e}')
    finally:
        await redis.close()

asyncio.run(test())
"
```

### Resolution

#### Immediate Mitigation

**Step 1: Restart Redis (if down)**

```bash
docker restart ablage-redis

# Wait for startup
sleep 5

# Verify
docker exec ablage-redis redis-cli PING
```

**Step 2: Clear Memory (if OOM)**

```bash
# Connect to Redis
docker exec -it ablage-redis redis-cli

# Check memory
INFO memory

# If at limit, flush old keys
# Option A: Set eviction policy
CONFIG SET maxmemory-policy allkeys-lru

# Option B: Flush all (nuclear option)
FLUSHALL
```

**Step 3: Bypass Cache Temporarily**

**Disable caching in backend (emergency):**
```bash
# Edit environment
sudo nano /etc/ablage/backend.env

# Add
ENABLE_CACHING=false

# Restart backend
docker restart ablage-backend
```

**Caution:** Performance will degrade, but system stays operational.

#### Root Cause Fixes

**Fix 1: Increase Redis Memory**

```bash
# Edit Redis config
sudo nano /etc/ablage/redis.conf
```

**Change:**
```
# Before
maxmemory 1gb

# After
maxmemory 2gb

# Eviction policy
maxmemory-policy allkeys-lru
```

**Restart Redis:**
```bash
docker restart ablage-redis
```

**Fix 2: Enable Redis Persistence (if data loss)**

**RDB snapshots:**
```
# redis.conf
save 900 1      # Save after 900s if 1 key changed
save 300 10     # Save after 300s if 10 keys changed
save 60 10000   # Save after 60s if 10000 keys changed

dbfilename dump.rdb
dir /data
```

**AOF (more durable):**
```
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
```

**Fix 3: Connection Pool Tuning**

**Increase connection pool:**
```python
# app/core/config.py
REDIS_MAX_CONNECTIONS = 50  # Up from 20
REDIS_SOCKET_KEEPALIVE = True
REDIS_SOCKET_CONNECT_TIMEOUT = 5
REDIS_RETRY_ON_TIMEOUT = True
```

#### Verification

**Test cache operations:**
```bash
# Set key
docker exec ablage-redis redis-cli SET test_key "test_value"

# Get key
docker exec ablage-redis redis-cli GET test_key
# Expected: "test_value"

# Check TTL
docker exec ablage-redis redis-cli EXPIRE test_key 60
docker exec ablage-redis redis-cli TTL test_key
# Expected: ~60
```

**Test from backend:**
```bash
docker exec ablage-backend python -c "
from app.services.cache import CacheService
from redis.asyncio import Redis
import asyncio

async def test():
    redis = Redis(host='ablage-redis', port=6379)
    cache = CacheService(redis)

    await cache.set('test', {'foo': 'bar'}, ttl=60)
    value = await cache.get('test')
    print(f'Cached value: {value}')

    await redis.close()

asyncio.run(test())
"
```

**Monitor cache hit rate:**
```promql
rate(cache_hits_total[5m]) /
(rate(cache_hits_total[5m]) + rate(cache_misses_total[5m])) * 100
```

**Expected:** >70% within 15 minutes (cache warming)

### Prevention

#### 1. Monitoring & Alerting

```yaml
# prometheus/alerts/redis.yml
groups:
  - name: redis_alerts
    rules:
      - alert: RedisCacheDown
        expr: redis_up == 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Redis cache unavailable"

      - alert: RedisMemoryHigh
        expr: redis_memory_used_bytes / redis_memory_max_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Redis memory at {{ $value | humanizePercentage }}"
```

#### 2. Cache Warming

**Warm cache on startup:**
```python
# app/main.py
@app.on_event("startup")
async def warm_cache():
    """Pre-populate cache with frequently accessed data."""
    from app.services.cache import warm_cache
    await warm_cache()
```

#### 3. Graceful Degradation

**Always handle Redis failures:**
```python
async def get_document(doc_id: str, db: AsyncSession, cache: CacheService):
    """Get document with cache fallback."""
    try:
        # Try cache first
        cached = await cache.get(f"document:{doc_id}")
        if cached:
            return cached
    except Exception as e:
        logger.warning(f"Cache error: {e}, falling back to database")

    # Cache miss or error: query database
    document = await db.get(Document, doc_id)

    # Try to cache result (best effort)
    try:
        if document:
            await cache.set(f"document:{doc_id}", document.to_dict(), ttl=3600)
    except Exception:
        pass  # Continue even if caching fails

    return document
```

### Related

**Dashboards:**
- [Application Metrics](https://grafana.ablage.local/d/ablage-app-metrics)

**Metrics:**
```promql
# Cache hit rate
rate(cache_hits_total[5m]) /
(rate(cache_hits_total[5m]) + rate(cache_misses_total[5m]))

# Redis memory usage
redis_memory_used_bytes / redis_memory_max_bytes

# Redis operations
rate(redis_commands_processed_total[5m])
```

---

## Disk Space Critical

### Incident: Disk Space Critically Low

**Severity:** Critical (system may crash)

**Alert Name:** `DiskSpaceCritical`

### Symptoms

**User Experience:**
- File uploads fail
- Document processing fails
- API errors

**System Behavior:**
- Disk usage >90%
- Logs show "No space left on device"
- Services may crash

**Metrics:**
```promql
# Disk usage >90%
(1 - node_filesystem_avail_bytes{mountpoint="/"} /
     node_filesystem_size_bytes{mountpoint="/"}) > 0.90
```

### Diagnosis

#### Step 1: Check Disk Usage

```bash
df -h
```

**Critical if >90% on root or data partition.**

#### Step 2: Find Large Directories

```bash
# Top 10 largest directories
du -h --max-depth=3 / | sort -hr | head -20
```

**Common culprits:**
- `/var/lib/docker` (Docker images/containers)
- `/var/log` (logs)
- `/opt/ablage/storage` (MinIO documents)

#### Step 3: Check Docker Disk Usage

```bash
docker system df
```

**Example output:**
```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          25        10        15.2GB    8.5GB (56%)
Containers      15        5         2.1GB     1.2GB (57%)
Local Volumes   30        20        50GB      10GB (20%)
```

### Resolution

#### Immediate Mitigation (5-10 minutes)

**Step 1: Clean Docker (safe)**

```bash
# Remove unused images
docker image prune -a -f

# Remove stopped containers
docker container prune -f

# Remove unused volumes (caution: check first)
docker volume ls -qf dangling=true
docker volume prune -f
```

**Expected:** Frees 5-10 GB

**Step 2: Clean Logs**

```bash
# Truncate large log files
sudo find /var/log -type f -name "*.log" -size +100M -exec truncate -s 0 {} \;

# Clean systemd journal
sudo journalctl --vacuum-size=500M
```

**Step 3: Archive Old Documents (if MinIO storage full)**

```bash
# List large buckets
mc du local/documents --depth=1

# Archive documents older than 6 months
mc find local/documents --older-than 180d --exec "mc mv {} local/archive/{}"
```

#### Root Cause Fixes

**Fix 1: Enable Log Rotation**

```bash
# Create logrotate config
sudo nano /etc/logrotate.d/ablage
```

**Content:**
```
/var/log/ablage/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 ablage ablage
}
```

**Fix 2: Docker Log Limits**

```bash
# Edit docker daemon config
sudo nano /etc/docker/daemon.json
```

**Add:**
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

**Restart Docker:**
```bash
sudo systemctl restart docker
```

**Fix 3: Document Retention Policy**

**Implement automatic archival:**
```python
# scripts/archive_old_documents.py
from datetime import datetime, timedelta
from app.db import SessionLocal
from app.models import Document

db = SessionLocal()
cutoff_date = datetime.now() - timedelta(days=180)

# Mark old documents for archival
old_docs = db.query(Document).filter(
    Document.created_at < cutoff_date,
    Document.status != 'archived'
).all()

for doc in old_docs:
    # Move to cold storage
    storage.archive(doc.file_path)
    doc.status = 'archived'
    db.commit()
```

**Add to cron:**
```
0 2 * * 0 /usr/local/bin/archive_old_documents.py
```

#### Verification

```bash
# Check disk space
df -h /

# Expected: <80% usage
```

### Prevention

#### 1. Monitoring & Alerting

```yaml
groups:
  - name: disk_alerts
    rules:
      - alert: DiskSpaceWarning
        expr: (1 - node_filesystem_avail_bytes / node_filesystem_size_bytes) > 0.75
        labels:
          severity: warning

      - alert: DiskSpaceCritical
        expr: (1 - node_filesystem_avail_bytes / node_filesystem_size_bytes) > 0.90
        labels:
          severity: critical
```

#### 2. Automatic Cleanup

**Daily cleanup cron:**
```bash
#!/bin/bash
# /usr/local/bin/daily-cleanup.sh

# Clean Docker
docker image prune -a -f --filter "until=168h"  # 7 days
docker container prune -f
docker volume prune -f

# Clean logs
find /var/log/ablage -name "*.log" -mtime +7 -delete
```

---

## Emergency Procedures

### Complete System Failure

**When to use:** All services down, no user access

**Step 1: Assess Scope (2 minutes)**
- Check Grafana: All metrics flat?
- SSH to servers: Can you connect?
- Check other services: Network issue or Ablage-specific?

**Step 2: Restart All Services (5 minutes)**
```bash
# Stop all
docker-compose down

# Wait
sleep 10

# Start dependencies first
docker-compose up -d postgres redis minio

# Wait for databases
sleep 20

# Start application
docker-compose up -d backend worker

# Check logs
docker-compose logs -f
```

**Step 3: If Still Down - Rollback (10 minutes)**
```bash
# Rollback to last known good version
docker-compose down
git checkout <last-good-commit>
docker-compose up -d

# Or restore from backup
./scripts/restore-backup.sh <backup-date>
```

### Data Loss Suspected

**Critical:** Follow data recovery procedures immediately

**Step 1: Stop All Writes**
```bash
# Put system in read-only mode
docker-compose stop backend worker
```

**Step 2: Assess Damage**
```bash
# Check database integrity
docker exec ablage-postgres pg_dump -U postgres ablage > /tmp/backup-check.sql

# Check file storage
mc ls local/documents | wc -l
```

**Step 3: Restore from Backup**
```bash
# Restore database
./scripts/restore-database.sh <timestamp>

# Restore files
./scripts/restore-minio.sh <timestamp>

# Verify
./scripts/verify-restoration.sh
```

**Step 4: Incident Report**
- Document what was lost
- Timeline of events
- Root cause
- Prevention measures

---

## Post-Incident Review

### Template

**Incident:** [Title]
**Date:** [YYYY-MM-DD]
**Duration:** [Start time - End time]
**Severity:** [Critical / High / Medium / Low]

**Timeline:**
- [HH:MM] - Alert fired
- [HH:MM] - On-call engineer paged
- [HH:MM] - Incident acknowledged
- [HH:MM] - Diagnosis completed
- [HH:MM] - Mitigation applied
- [HH:MM] - Issue resolved
- [HH:MM] - Verification completed

**Impact:**
- Users affected: [number]
- Duration of impact: [minutes]
- Data loss: [Yes/No, details]
- Revenue impact: [if applicable]

**Root Cause:**
[Detailed explanation of what caused the incident]

**Resolution:**
[What was done to resolve the incident]

**Action Items:**
1. [Action] - Owner: [Name] - Due: [Date]
2. [Action] - Owner: [Name] - Due: [Date]

**Lessons Learned:**
- What went well
- What could be improved
- Changes needed to prevent recurrence

---

**Document Status:** ✅ Production-Ready
**Last Reviewed:** 2025-01-23
**Next Review:** 2025-04-23 (Quarterly)
**Owner:** Operations Team
