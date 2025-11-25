# Performance Degradation Runbook
**Ablage-System - Leistungsabfall Behebung**

Version: 1.0
Last Updated: 2025-01-23
Owner: Performance Engineering Team
Severity: HIGH

---

## Quick Reference

| Symptom | Target | Action | Page |
|---------|--------|--------|------|
| API P95 > 500ms | <320ms | Database optimization | [§1](#1-api-latency-degradation) |
| Throughput < 150 docs/hr | >192 docs/hr | Batch tuning | [§2](#2-throughput-degradation) |
| Queue depth > 100 | <50 | Scale workers | [§3](#3-queue-backlog) |
| Database slow queries | <100ms | Index optimization | [§4](#4-database-performance) |
| Redis latency > 10ms | <2ms | Memory/eviction | [§5](#5-cache-performance) |
| GPU utilization < 40% | 60-80% | CPU bottleneck | [§6](#6-gpu-underutilization) |

---

## Performance Baselines

### Established Targets (Production)
```yaml
api_performance:
  health_check:
    p50: <20ms
    p95: <50ms
    p99: <100ms

  document_upload:
    p50: <200ms
    p95: <500ms
    p99: <1000ms

  document_retrieval:
    cached:
      p50: <30ms
      p95: <100ms
    uncached:
      p50: <100ms
      p95: <300ms

ocr_performance:
  throughput:
    target: 192 docs/hour
    minimum: 150 docs/hour
    optimal: 200+ docs/hour

  per_document_processing:
    simple:
      p50: <3s
      p95: <5s
    complex:
      p50: <8s
      p95: <15s

resource_utilization:
  gpu:
    idle: 5-15%
    active: 60-80%
    peak: <85%

  cpu:
    average: 40-60%
    peak: <80%

  memory:
    backend: <4GB
    worker: <8GB
    total_system: <24GB

  disk_io:
    read: <100MB/s
    write: <50MB/s
```

---

## 1. API Latency Degradation

### Symptoms
- P95 latency >500ms (target: <320ms)
- Slow user interface responses
- Timeout errors in frontend

### Diagnosis Steps

**Step 1: Identify Slow Endpoints**
```bash
# Query Prometheus metrics
curl -s 'http://localhost:9090/api/v1/query?query=histogram_quantile(0.95,rate(http_request_duration_seconds_bucket[5m]))' | jq

# Or check application logs
docker-compose logs backend | grep 'request_duration' | awk '{print $NF}' | sort -rn | head -20

# Expected output: Top 20 slowest endpoints
```

**Step 2: Database Query Analysis**
```sql
-- Connect to PostgreSQL
docker exec ablage-postgres psql -U postgres -d ablage

-- Find slow queries (>100ms)
SELECT
  query,
  calls,
  total_time / calls as avg_time_ms,
  min_time as min_ms,
  max_time as max_ms
FROM pg_stat_statements
WHERE total_time / calls > 100
ORDER BY avg_time_ms DESC
LIMIT 20;

-- If pg_stat_statements not enabled:
-- CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
-- ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
-- (requires PostgreSQL restart)
```

**Step 3: Check for N+1 Queries**
```python
# Enable SQLAlchemy query logging
docker exec ablage-backend python -c "
import logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Run test request and count queries
from app.api.v1.documents import get_document
# ... test code ...
"

# Look for repeated similar queries (N+1 pattern)
```

**Step 4: Network Latency Check**
```bash
# Internal container network
docker exec ablage-backend ping -c 5 ablage-postgres
docker exec ablage-backend ping -c 5 ablage-redis
docker exec ablage-backend ping -c 5 ablage-minio

# Expected: <1ms average latency
```

---

### Solution 1.1: Database Query Optimization

**Problem:** Slow queries without proper indexes

**Fix: Add Missing Indexes**
```sql
-- Analyze query plans for slow queries
EXPLAIN ANALYZE
SELECT * FROM documents WHERE user_id = 'user123' AND status = 'completed'
ORDER BY created_at DESC LIMIT 10;

-- Look for "Seq Scan" (bad) vs "Index Scan" (good)

-- Add composite index if missing
CREATE INDEX CONCURRENTLY idx_documents_user_status_created
ON documents(user_id, status, created_at DESC);

-- Verify improvement
EXPLAIN ANALYZE
SELECT * FROM documents WHERE user_id = 'user123' AND status = 'completed'
ORDER BY created_at DESC LIMIT 10;
```

**Common Indexes Needed:**
```sql
-- User document lookups
CREATE INDEX CONCURRENTLY idx_documents_user_status
ON documents(user_id, status);

-- OCR result searches
CREATE INDEX CONCURRENTLY idx_documents_extracted_text_gin
ON documents USING GIN (to_tsvector('german', extracted_text));

-- Date range queries
CREATE INDEX CONCURRENTLY idx_documents_created_at
ON documents(created_at DESC);

-- API logs performance
CREATE INDEX CONCURRENTLY idx_api_logs_timestamp
ON api_logs(timestamp DESC);
```

**⏱️ Time to Resolve:** 5-30 minutes (depending on table size)
**🔄 Requires Downtime:** NO (`CREATE INDEX CONCURRENTLY`)

---

### Solution 1.2: Enable Query Result Caching

**Problem:** Repeated expensive queries for same data

**Fix: Redis Caching Layer**
```python
# Update app/services/cache_service.py
from functools import wraps
import hashlib
import json

def cache_query(ttl_seconds=300):
    """Decorator to cache database query results."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            cache_key = f"query:{func.__name__}:{_hash_args(args, kwargs)}"

            # Try cache first
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)

            # Execute query
            result = await func(*args, **kwargs)

            # Cache result
            await redis.setex(cache_key, ttl_seconds, json.dumps(result))

            return result
        return wrapper
    return decorator

# Usage in repository
class DocumentRepository:
    @cache_query(ttl_seconds=300)  # 5 minute cache
    async def get_user_documents(self, user_id: str, status: str):
        """Cached query for user documents."""
        result = await self.db.execute(
            select(Document)
            .where(Document.user_id == user_id, Document.status == status)
            .order_by(Document.created_at.desc())
            .limit(50)
        )
        return result.scalars().all()
```

**Cache Invalidation Strategy:**
```python
# Update cache on document changes
class DocumentService:
    async def update_document_status(self, doc_id: str, new_status: str):
        """Update document and invalidate cache."""
        # Update database
        await self.repository.update(doc_id, status=new_status)

        # Invalidate user's document list cache
        document = await self.repository.get(doc_id)
        cache_pattern = f"query:get_user_documents:{document.user_id}:*"
        await redis.delete_pattern(cache_pattern)
```

**⏱️ Time to Resolve:** 30-60 minutes (implementation)
**🔄 Requires Downtime:** NO (rolling deployment)

---

### Solution 1.3: Connection Pool Tuning

**Problem:** Connection pool exhaustion causing waits

**Diagnosis:**
```sql
-- Check current connections
SELECT count(*) as total_connections,
       count(*) FILTER (WHERE state = 'active') as active,
       count(*) FILTER (WHERE state = 'idle') as idle,
       count(*) FILTER (WHERE wait_event IS NOT NULL) as waiting
FROM pg_stat_activity;
```

**Fix: Increase Pool Size**
```python
# Update app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Increase from 10
    max_overflow=40,       # Increase from 20
    pool_pre_ping=True,    # Verify connections before use
    pool_recycle=3600,     # Recycle connections after 1 hour
    echo_pool=True         # Log pool events for debugging
)
```

**PostgreSQL Configuration:**
```conf
# Edit postgresql.conf
max_connections = 200           # Increase from 100
shared_buffers = 4GB           # 25% of RAM
effective_cache_size = 12GB    # 75% of RAM
work_mem = 16MB                # Per-operation memory
maintenance_work_mem = 512MB   # For VACUUM, index creation

# Apply changes
docker-compose restart postgres
```

**⏱️ Time to Resolve:** 10-15 minutes
**🔄 Requires Downtime:** YES (PostgreSQL restart)

---

## 2. Throughput Degradation

### Symptoms
- Processing <150 documents/hour (target: 192+)
- Queue growing despite active workers
- GPU underutilized (<40%)

### Diagnosis Steps

**Step 1: Current Throughput Measurement**
```sql
-- Throughput over last hour
SELECT
  DATE_TRUNC('hour', completed_at) as hour,
  COUNT(*) as documents_processed,
  AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) as avg_processing_time
FROM documents
WHERE completed_at > NOW() - INTERVAL '24 hours'
  AND status = 'completed'
GROUP BY hour
ORDER BY hour DESC;
```

**Step 2: Worker Status Check**
```bash
# Check Celery worker status
docker exec ablage-worker celery -A app.celery inspect active

# Check queue depth
docker exec ablage-redis redis-cli LLEN celery

# Monitor worker logs
docker-compose logs -f worker | grep 'throughput\|batch_size\|processing_time'
```

**Step 3: Identify Bottleneck**
```bash
# GPU utilization
nvidia-smi dmon -s u -c 60  # Monitor for 1 minute

# CPU utilization
docker stats ablage-worker --no-stream

# Disk I/O
iostat -x 5 5  # 5 samples, 5 seconds apart
```

---

### Solution 2.1: Optimize Batch Processing

**Problem:** Suboptimal batch sizes

**Current vs. Optimal Configuration:**
```yaml
# Current (suboptimal)
batch_config:
  simple: 8
  medium: 4
  complex: 2

# Optimal (from experiments)
batch_config:
  simple: 12
  medium: 6
  complex: 3

  # Enable complexity-aware batching
  adaptive_sizing: true
  complexity_assessment: true
```

**Implementation:**
```python
# Update app/services/ocr/batch_optimizer.py
class BatchOptimizer:
    def __init__(self):
        self.batch_sizes = {
            'simple': 12,
            'medium': 6,
            'complex': 3
        }

    def optimize_batch(self, documents: List[Document]) -> List[List[Document]]:
        """Group documents by complexity and create optimal batches."""
        # Assess complexity
        categorized = {
            'simple': [],
            'medium': [],
            'complex': []
        }

        for doc in documents:
            complexity = self._assess_complexity(doc)
            categorized[complexity].append(doc)

        # Create batches per complexity level
        batches = []
        for complexity, docs in categorized.items():
            batch_size = self.batch_sizes[complexity]
            for i in range(0, len(docs), batch_size):
                batches.append(docs[i:i+batch_size])

        return batches

    def _assess_complexity(self, document: Document) -> str:
        """Assess document complexity for batch sizing."""
        # Simple heuristics
        if document.page_count == 1 and not document.has_tables:
            return 'simple'
        elif document.page_count > 5 or document.has_images:
            return 'complex'
        else:
            return 'medium'
```

**Expected Improvement:** +40-60% throughput (120 → 192 docs/hour)

**⏱️ Time to Resolve:** 20-30 minutes
**🔄 Requires Downtime:** Minimal (worker restart)

---

### Solution 2.2: Parallel Worker Scaling

**Problem:** Single worker can't keep up with demand

**Assessment:**
```bash
# Current worker count
docker-compose ps | grep worker

# Queue depth trend
for i in {1..10}; do
  echo "$(date): $(docker exec ablage-redis redis-cli LLEN celery) documents queued"
  sleep 30
done

# If queue growing: need more workers
```

**Fix: Scale Workers**
```yaml
# Update docker-compose.yml
services:
  worker:
    # ... existing config ...
    deploy:
      replicas: 3  # Increase from 1

      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
              device_ids: ['0']  # Share GPU across workers
```

**GPU Sharing Strategy:**
```python
# Update app/core/config.py
GPU_CONFIG = {
    'max_workers_per_gpu': 3,  # RTX 4080 can handle 3 workers
    'memory_per_worker_gb': 5,  # ~5GB per worker (15GB total)
    'enable_mps': False  # Multi-Process Service (advanced)
}

# Workers coordinate via Redis lock
class GPUResourceManager:
    async def acquire_gpu_slot(self, worker_id: str) -> bool:
        """Acquire GPU slot with memory reservation."""
        # Check current GPU users
        current_users = await redis.smembers('gpu:workers')

        if len(current_users) >= GPU_CONFIG['max_workers_per_gpu']:
            return False  # GPU full

        # Reserve slot
        await redis.sadd('gpu:workers', worker_id)
        await redis.expire('gpu:workers', 300)  # 5 min timeout

        return True
```

**Monitoring Multi-Worker Setup:**
```bash
# Watch GPU memory per process
watch -n 1 'nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader'

# Ensure total < 13.6GB (85% of 16GB)
```

**⏱️ Time to Resolve:** 30-45 minutes
**🔄 Requires Downtime:** NO (gradual scaling)

---

### Solution 2.3: Preprocessing Pipeline Optimization

**Problem:** CPU-bound preprocessing bottleneck

**Diagnosis:**
```python
# Profile preprocessing time
docker exec ablage-backend python -c "
import time
from app.utils.image_preprocessing import preprocess_image
import numpy as np

# Test image
image = np.random.randint(0, 255, (2048, 2048, 3), dtype=np.uint8)

# Time preprocessing
start = time.time()
for _ in range(10):
    preprocessed = preprocess_image(image)
elapsed = time.time() - start

print(f'Average preprocessing time: {elapsed/10*1000:.2f}ms')
# Target: <50ms per image
"
```

**Fix: GPU-Accelerated Preprocessing**
```python
# Update app/utils/image_preprocessing.py
import cv2
import numpy as np
import torch
import kornia

class GPUImagePreprocessor:
    def __init__(self):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    def preprocess_batch(self, images: List[np.ndarray]) -> torch.Tensor:
        """GPU-accelerated batch preprocessing."""
        # Convert to tensor batch
        batch = np.stack([self._prepare_image(img) for img in images])
        batch_tensor = torch.from_numpy(batch).to(self.device)

        # GPU operations (Kornia)
        batch_tensor = kornia.geometry.resize(batch_tensor, (1024, 1024))
        batch_tensor = kornia.enhance.normalize(batch_tensor, mean=0.5, std=0.5)
        batch_tensor = kornia.filters.gaussian_blur2d(batch_tensor, (5, 5), (1.5, 1.5))

        return batch_tensor

    def _prepare_image(self, image: np.ndarray) -> np.ndarray:
        """Minimal CPU preparation."""
        if len(image.shape) == 2:  # Grayscale
            image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)

        return image.transpose(2, 0, 1)  # HWC -> CHW
```

**Performance Gain:**
- CPU preprocessing: ~150ms per image
- GPU preprocessing: ~15ms per image (10x faster)
- Batch of 12: 1.8s → 0.2s (9x speedup)

**⏱️ Time to Resolve:** 1-2 hours (implementation + testing)
**🔄 Requires Downtime:** NO (rolling deployment)

---

## 3. Queue Backlog

### Symptoms
- Queue depth >100 documents (target: <50)
- Processing can't keep up with uploads
- User wait times increasing

### Solution 3.1: Priority Queue Implementation

**Problem:** All documents treated equally

**Fix: Priority-Based Processing**
```python
# Update app/workers/ocr_tasks.py
from celery import Task

class PriorityOCRTask(Task):
    priority_levels = {
        'urgent': 9,    # VIP users, small documents
        'high': 6,      # Standard users, simple docs
        'normal': 3,    # Batch uploads
        'low': 0        # Background processing
    }

@celery_app.task(base=PriorityOCRTask, bind=True)
def process_document_prioritized(self, document_id: str, user_tier: str):
    """Process document with priority based on user tier."""
    # Priority determined by user_tier and doc complexity
    complexity = assess_document_complexity(document_id)

    if user_tier == 'premium' or complexity == 'simple':
        priority = self.priority_levels['urgent']
    elif user_tier == 'standard':
        priority = self.priority_levels['high']
    else:
        priority = self.priority_levels['normal']

    # Process with priority
    return process_with_priority(document_id, priority)
```

**Configure Celery Priority:**
```python
# app/celery_app.py
from kombu import Queue

app = Celery('ablage')

app.conf.task_queues = [
    Queue('urgent', priority=9),
    Queue('high', priority=6),
    Queue('default', priority=3),
    Queue('batch', priority=0),
]

app.conf.task_default_queue = 'default'
app.conf.task_default_priority = 3
```

**⏱️ Time to Resolve:** 1-2 hours
**🔄 Requires Downtime:** YES (Celery reconfiguration)

---

## 4. Database Performance

### Symptoms
- Slow queries (>100ms avg)
- Connection pool exhaustion
- High CPU on PostgreSQL container

### Solution 4.1: VACUUM and ANALYZE

**Problem:** Table bloat and stale statistics

**Fix:**
```sql
-- Check table bloat
SELECT
  schemaname, tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
  n_dead_tup as dead_tuples,
  n_live_tup as live_tuples,
  round(n_dead_tup::float / NULLIF(n_live_tup, 0) * 100, 2) as dead_ratio
FROM pg_stat_user_tables
WHERE n_live_tup > 0
ORDER BY n_dead_tup DESC;

-- VACUUM tables with high dead_ratio (>10%)
VACUUM ANALYZE documents;
VACUUM ANALYZE api_logs;

-- Full vacuum (requires exclusive lock, do during maintenance)
-- VACUUM FULL documents;
```

**Automated Vacuuming:**
```conf
# PostgreSQL auto-vacuum tuning (postgresql.conf)
autovacuum = on
autovacuum_max_workers = 3
autovacuum_naptime = 60s  # Check every minute
autovacuum_vacuum_threshold = 50
autovacuum_vacuum_scale_factor = 0.1  # Vacuum at 10% dead tuples

# Restart PostgreSQL
docker-compose restart postgres
```

**⏱️ Time to Resolve:** 5-15 minutes (VACUUM), 30 minutes (auto-vacuum setup)
**🔄 Requires Downtime:** NO (ANALYZE), YES (VACUUM FULL)

---

### Solution 4.2: Partition Large Tables

**Problem:** `documents` table too large (>10M rows)

**Fix: Time-Based Partitioning**
```sql
-- Create partitioned table
CREATE TABLE documents_partitioned (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    status VARCHAR(50),
    created_at TIMESTAMP NOT NULL,
    -- ... other columns ...
) PARTITION BY RANGE (created_at);

-- Create partitions for each month
CREATE TABLE documents_2025_01 PARTITION OF documents_partitioned
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');

CREATE TABLE documents_2025_02 PARTITION OF documents_partitioned
FOR VALUES FROM ('2025-02-01') TO ('2025-03-01');

-- ... create more partitions ...

-- Migrate data (during maintenance window)
BEGIN;
INSERT INTO documents_partitioned SELECT * FROM documents;
DROP TABLE documents;
ALTER TABLE documents_partitioned RENAME TO documents;
COMMIT;

-- Create indexes on partitions
CREATE INDEX idx_documents_2025_01_user ON documents_2025_01(user_id);
CREATE INDEX idx_documents_2025_02_user ON documents_2025_02(user_id);
```

**Expected Improvement:** 3-5x faster queries on recent data

**⏱️ Time to Resolve:** 2-4 hours (depending on data size)
**🔄 Requires Downtime:** YES (migration window)

---

## 5. Cache Performance

### Symptoms
- Redis latency >10ms (target: <2ms)
- High memory usage (>80% of max)
- Evictions occurring frequently

### Solution 5.1: Redis Memory Optimization

**Diagnosis:**
```bash
# Check Redis memory
docker exec ablage-redis redis-cli INFO memory

# Key statistics
docker exec ablage-redis redis-cli INFO stats | grep evicted

# Sample keys
docker exec ablage-redis redis-cli --scan --pattern '*' | head -100
```

**Fix: Eviction Policy Tuning**
```conf
# redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru  # Evict least recently used keys

# Optimize for throughput
save ""  # Disable RDB persistence (risky but fast)
appendonly no  # Disable AOF

# Or keep persistence but tune
save 900 1
save 300 10
save 60 10000
```

**Key Expiration Strategy:**
```python
# Update cache service to set appropriate TTLs
CACHE_TTL = {
    'document_metadata': 3600,     # 1 hour
    'user_session': 1800,          # 30 minutes
    'api_rate_limit': 60,          # 1 minute
    'query_results': 300,          # 5 minutes
    'health_check': 30,            # 30 seconds
}

class CacheService:
    async def set(self, key: str, value: any, category: str = 'default'):
        """Set with category-based TTL."""
        ttl = CACHE_TTL.get(category, 300)
        await self.redis.setex(key, ttl, value)
```

**⏱️ Time to Resolve:** 15-30 minutes
**🔄 Requires Downtime:** YES (Redis restart)

---

## 6. GPU Underutilization

### Symptoms
- GPU utilization <40% (target: 60-80%)
- Slow throughput despite available GPU capacity
- CPU at 100% while GPU idle

**Solution:** See [GPU Troubleshooting Decision Tree](gpu_troubleshooting_decision_tree.md) Section 3.2

---

## Performance Testing

### Load Testing Protocol

```bash
# Install k6
docker pull grafana/k6

# Run load test
docker run --rm \
  -v $(pwd)/tests/load:/scripts \
  grafana/k6 run /scripts/api_load_test.js

# Test scenarios:
# 1. Baseline (10 users)
# 2. Normal load (50 users)
# 3. Peak load (100 users)
# 4. Stress test (200+ users)
```

**Load Test Script:**
```javascript
// tests/load/api_load_test.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up
    { duration: '5m', target: 50 },   // Normal load
    { duration: '2m', target: 100 },  // Peak
    { duration: '5m', target: 50 },   // Scale down
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],  // 95% under 500ms
    http_req_failed: ['rate<0.01'],    // <1% errors
  },
};

export default function () {
  // Health check
  const healthRes = http.get('http://localhost:8000/health');
  check(healthRes, { 'health check OK': (r) => r.status === 200 });

  sleep(1);

  // Upload document
  const uploadRes = http.post('http://localhost:8000/api/v1/documents/', {
    file: http.file(/* ... */),
  });
  check(uploadRes, { 'upload OK': (r) => r.status === 201 });

  sleep(2);
}
```

---

## Escalation

**When to Escalate:**
- Performance degradation >30 minutes
- Database unresponsive
- Complete system slowdown
- Cannot identify root cause

**Escalation Path:**
1. **Level 1:** Performance Team Lead
2. **Level 2:** System Architect
3. **Level 3:** CTO

---

## Related Documents
- [Daily Operations Checklist](daily_operations_checklist.md)
- [GPU Troubleshooting Decision Tree](gpu_troubleshooting_decision_tree.md)
- [Weekly Maintenance Runbook](weekly_maintenance_runbook.md)
- [Database Optimization Guide](../../Static_Knowledge/Technical_Details/database_architecture.md)

---

## Revision History

| Version | Date       | Author               | Changes                       |
|---------|------------|----------------------|-------------------------------|
| 1.0     | 2025-01-23 | Performance Team     | Initial performance runbook   |
