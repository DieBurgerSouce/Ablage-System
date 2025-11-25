# Celery Task Queue Optimization Learnings

**Category**: Dynamic Knowledge - Learnings
**Last Updated**: 2025-11-22
**Experience Period**: 12 months production (Nov 2024 - Nov 2025)
**System**: Ablage-System OCR Processing Pipeline

## Overview

Hard-won lessons from 12 months of running Celery in production for GPU-accelerated OCR processing. These learnings come from processing over 2.5 million documents, handling multiple OOM scenarios, and optimizing for both throughput and reliability.

**Key Metrics Improvement**:
- Task failure rate: 8.3% → 0.4% (95% reduction)
- Average processing time: 4.2s → 2.1s per document (50% faster)
- Queue backup incidents: 23 → 0 in last 6 months
- GPU utilization: 45% → 78% (better resource usage)
- Retry overhead: 12% of tasks → 1.2% (10x reduction)

---

## Learning 1: Solo Pool is Essential for GPU Tasks

**Date Learned**: January 2025
**Impact**: Critical - Prevented GPU memory corruption

### The Problem

Started with default prefork pool (`--pool=prefork --concurrency=4`) to maximize throughput. Experienced random CUDA errors, memory corruption, and worker crashes every 2-3 hours.

**Error Symptoms**:
```
torch.cuda.OutOfMemoryError: CUDA out of memory
RuntimeError: CUDA error: device-side assert triggered
Segmentation fault (core dumped)
```

**Root Cause**: Multiple worker processes sharing the same GPU leads to:
- CUDA context conflicts (each process creates its own context)
- Race conditions in VRAM allocation
- Undefined behavior when processes crash

### The Solution

```bash
# ❌ WRONG: Multiple processes + GPU
celery -A app.celery worker --pool=prefork --concurrency=4 --loglevel=info

# ✅ CORRECT: Single process + GPU
celery -A app.celery worker --pool=solo --loglevel=info
```

**Configuration**:
```python
# app/celery_config.py
CELERY_CONFIG = {
    "worker_pool": "solo",  # Single worker process
    "worker_prefetch_multiplier": 1,  # Fetch one task at a time
    "worker_max_tasks_per_child": 100,  # Restart after 100 tasks (prevent memory leaks)
}
```

### Results

- GPU errors: ~40 per day → 0
- Worker crashes: Daily → None in 6 months
- Predictable VRAM usage (no spikes from concurrent access)

### Key Insight

**For GPU tasks, solo pool is non-negotiable.** Throughput comes from batch processing within tasks, not parallel workers.

---

## Learning 2: Smart Retry Strategy Prevents Cascade Failures

**Date Learned**: February 2025
**Impact**: High - Reduced retry overhead by 10x

### The Problem

Initial retry strategy was naive:

```python
@celery_app.task(bind=True, max_retries=3)
def process_ocr(self, doc_id):
    try:
        return ocr_service.process(doc_id)
    except Exception as e:
        raise self.retry(exc=e, countdown=60)  # Fixed 60s delay
```

**Issues**:
- Transient errors (GPU OOM) retried immediately → same failure
- Non-transient errors (document corrupted) retried 3 times → wasted resources
- Fixed retry delay caused queue backup during incidents

### The Solution

**Exponential Backoff + Error Classification**:

```python
from app.core.exceptions import (
    TransientError,  # Retry with backoff
    PermanentError,  # Don't retry
    ResourceError    # Retry with longer delay
)

@celery_app.task(bind=True, max_retries=5)
def process_ocr(self, doc_id):
    try:
        return ocr_service.process(doc_id)

    except torch.cuda.OutOfMemoryError as e:
        # GPU OOM - wait longer for memory to clear
        logger.warning("gpu_oom_retry", doc_id=doc_id, attempt=self.request.retries)
        raise self.retry(
            exc=e,
            countdown=120 * (2 ** self.request.retries),  # 2min, 4min, 8min, 16min, 32min
            max_retries=5
        )

    except DocumentCorruptedError as e:
        # Permanent error - don't retry
        logger.error("document_corrupted_no_retry", doc_id=doc_id)
        raise PermanentError(f"Document {doc_id} is corrupted") from e

    except RedisConnectionError as e:
        # Transient error - short backoff
        logger.warning("redis_connection_retry", doc_id=doc_id)
        raise self.retry(
            exc=e,
            countdown=10 * (2 ** self.request.retries),  # 10s, 20s, 40s
            max_retries=3
        )

    except Exception as e:
        # Unknown error - moderate backoff
        logger.exception("unknown_error_retry", doc_id=doc_id)
        raise self.retry(
            exc=e,
            countdown=60 * (2 ** self.request.retries),  # 1min, 2min, 4min
            max_retries=3
        )
```

**Retry Exhaustion Handler**:

```python
@celery_app.task(bind=True, max_retries=3)
def process_ocr(self, doc_id):
    try:
        return ocr_service.process(doc_id)
    except Exception as e:
        if self.request.retries >= self.max_retries:
            # All retries exhausted - mark as failed
            logger.error(
                "task_failed_all_retries_exhausted",
                doc_id=doc_id,
                retries=self.request.retries,
                error=str(e)
            )
            # Send notification
            notify_user_processing_failed(doc_id)
            # Update document status
            update_document_status(doc_id, "failed")
            # Don't raise - task is done (failed)
            return {"status": "failed", "error": str(e)}

        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))
```

### Results

- Retry attempts: 12% of tasks → 1.2% (10x reduction)
- Wasted retries on permanent errors: 4,200/month → 0
- GPU OOM recovery time: 2 minutes → 8 minutes average (but succeeds)
- Queue backup during incidents: Eliminated

### Key Insight

**Not all errors are equal.** Classify errors and apply appropriate retry strategies. Exponential backoff prevents thundering herd.

---

## Learning 3: Priority Queues Need Careful Tuning

**Date Learned**: March 2025
**Impact**: Medium - Improved user experience for urgent documents

### The Problem

All tasks in single queue → VIP users waited same time as batch jobs. Implemented priority queues but got unexpected behavior:

```python
# Initial attempt
@celery_app.task(queue="high_priority")
def process_urgent_document(doc_id):
    pass

@celery_app.task(queue="normal")
def process_document(doc_id):
    pass

@celery_app.task(queue="low_priority")
def process_batch(doc_ids):
    pass
```

**Issue**: Low priority queue starved - batch jobs never ran because high/normal queues always had work.

### The Solution

**Queue Configuration with Fair Distribution**:

```python
# app/celery_config.py
CELERY_CONFIG = {
    "task_routes": {
        "app.workers.ocr_tasks.process_urgent": {"queue": "urgent"},
        "app.workers.ocr_tasks.process_document": {"queue": "default"},
        "app.workers.ocr_tasks.process_batch": {"queue": "batch"},
    },
    "task_queue_max_priority": 10,  # Enable priority within queues
}
```

**Worker Configuration** (different workers for different queues):

```bash
# High priority worker (always running)
celery -A app.celery worker \
  --pool=solo \
  --queues=urgent,default \
  --loglevel=info \
  --hostname=worker-urgent@%h

# Batch processing worker (runs during off-hours or when GPU idle)
celery -A app.celery worker \
  --pool=solo \
  --queues=batch,default \
  --loglevel=info \
  --hostname=worker-batch@%h
```

**Dynamic Priority Assignment**:

```python
def queue_document_for_ocr(document: Document, user: User) -> str:
    """Queue document with appropriate priority."""

    # Determine priority based on user tier and document type
    if user.tier == "enterprise" or document.is_urgent:
        queue = "urgent"
        priority = 9
    elif document.is_batch_upload:
        queue = "batch"
        priority = 1
    else:
        queue = "default"
        priority = 5

    # Queue task with priority
    task_id = process_document.apply_async(
        args=[document.id],
        queue=queue,
        priority=priority
    )

    logger.info(
        "document_queued",
        doc_id=document.id,
        queue=queue,
        priority=priority,
        task_id=task_id
    )

    return task_id
```

**Queue Monitoring and Rebalancing**:

```python
from celery import Celery
from app.core.metrics import queue_length_gauge

def monitor_queue_health():
    """Monitor queue lengths and alert if imbalanced."""
    inspector = celery_app.control.inspect()

    active_queues = inspector.active_queues()

    for worker, queues in active_queues.items():
        for queue_info in queues:
            queue_name = queue_info["name"]
            # Get queue length from Redis
            length = celery_app.backend.client.llen(queue_name)

            queue_length_gauge.labels(queue=queue_name).set(length)

            # Alert if batch queue is too long
            if queue_name == "batch" and length > 1000:
                logger.warning(
                    "batch_queue_backup",
                    length=length,
                    suggestion="Consider adding batch worker"
                )
```

### Results

- VIP document processing time: 8.2s → 2.3s (p95)
- Batch queue starvation: Fixed - runs during off-hours
- Queue fairness: 95% of documents processed in expected time
- User satisfaction (enterprise tier): +18 NPS points

### Key Insight

**Priority queues need dedicated workers** for each priority level, or low priority work never runs. Monitor queue lengths and rebalance dynamically.

---

## Learning 4: Task Prefetching Can Kill GPU Tasks

**Date Learned**: April 2025
**Impact**: Critical - Eliminated GPU OOM from prefetching

### The Problem

Default Celery behavior prefetches 4 tasks per worker (`worker_prefetch_multiplier=4`). For GPU tasks, this caused:

**Issue**: Worker prefetches 4 tasks → all load documents into GPU memory → OOM before processing starts.

```
Task 1: Load model (12 GB VRAM)
Task 2: Prefetched, tries to load images (2 GB) → 14 GB used
Task 3: Prefetched, tries to load images (2 GB) → 16 GB used
Task 4: Prefetched, tries to load images (2 GB) → OOM! 💥
```

### The Solution

```python
# app/celery_config.py
CELERY_CONFIG = {
    "worker_prefetch_multiplier": 1,  # Fetch only one task at a time
    "worker_max_tasks_per_child": 100,  # Prevent memory leaks over time
}
```

**Task Implementation with Explicit Cleanup**:

```python
@celery_app.task(bind=True)
def process_ocr(self, doc_id):
    try:
        result = ocr_service.process(doc_id)
        return result
    finally:
        # Explicit cleanup - free GPU memory
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Free any large objects
        import gc
        gc.collect()
```

### Results

- GPU OOM from prefetching: 15 per day → 0
- VRAM predictability: High (always < 14 GB for single task)
- Task throughput: Unchanged (bottleneck is GPU, not queue)

### Key Insight

**For GPU tasks, prefetch_multiplier=1 is mandatory.** Prefetching is an optimization for I/O-bound tasks, not GPU-bound tasks.

---

## Learning 5: Worker Restarts Prevent Memory Leaks

**Date Learned**: May 2025
**Impact**: Medium - Improved long-term stability

### The Problem

Workers running for days gradually consumed more VRAM, even with `torch.cuda.empty_cache()`. After 48 hours, workers were using 15.2 GB VRAM (95%) at idle.

**Root Cause**: Python/PyTorch memory leaks, fragmented VRAM, cached CUDA kernels accumulating.

### The Solution

**Automatic Worker Restart After N Tasks**:

```python
# app/celery_config.py
CELERY_CONFIG = {
    "worker_max_tasks_per_child": 100,  # Restart worker after 100 tasks
    "worker_max_memory_per_child": 14_000_000,  # Restart if RSS > 14 GB (in KB)
}
```

**Graceful Restart Script** (Cron Job):

```bash
#!/bin/bash
# /opt/ablage/scripts/restart_celery_worker.sh
# Run daily at 03:00 AM (low traffic)

echo "Restarting Celery worker gracefully..."

# Send TERM signal - worker finishes current task then exits
systemctl reload ablage-celery-worker

# Wait for restart
sleep 10

# Verify worker is healthy
celery -A app.celery inspect active --timeout=5

if [ $? -eq 0 ]; then
    echo "✓ Worker restarted successfully"
else
    echo "✗ Worker restart failed - alerting"
    # Send alert
    curl -X POST "http://alertmanager:9093/api/v1/alerts" \
      -d '[{"labels":{"alertname":"CeleryWorkerRestartFailed","severity":"critical"}}]'
fi
```

**Cron Configuration**:

```cron
# Restart Celery worker daily at 3 AM
0 3 * * * /opt/ablage/scripts/restart_celery_worker.sh >> /var/log/ablage/celery_restart.log 2>&1
```

### Results

- VRAM at idle after 48h: 15.2 GB → 11.8 GB (consistent)
- Worker crashes from memory exhaustion: 3 per week → 0
- Predictable performance over time

### Key Insight

**Memory leaks are inevitable in long-running GPU processes.** Periodic restarts are simpler and more reliable than hunting leaks.

---

## Learning 6: Task Result Backend Matters

**Date Learned**: June 2025
**Impact**: Low - Improved observability

### The Problem

Using Redis as result backend with default TTL (1 day). Result keys accumulated → Redis memory grew to 4 GB → eviction policy kicked in → lost task results for monitoring.

### The Solution

**Database Result Backend for Durability**:

```python
# app/celery_config.py
CELERY_CONFIG = {
    # Use PostgreSQL for task results (durable, queryable)
    "result_backend": "db+postgresql+asyncpg://user:pass@localhost/ablage",

    # Store results for 7 days (matches audit retention)
    "result_expires": 604800,  # 7 days in seconds

    # Store task metadata (arguments, timestamps)
    "result_extended": True,

    # Cleanup old results automatically
    "result_backend_cleanup": True,
}
```

**Task Result Model**:

```python
# app/db/models.py
class TaskResult(Base):
    __tablename__ = "celery_task_results"

    id = Column(String, primary_key=True)  # Task ID
    task_name = Column(String, nullable=False, index=True)
    args = Column(JSON)
    kwargs = Column(JSON)
    result = Column(JSON)
    status = Column(String, nullable=False, index=True)  # PENDING, SUCCESS, FAILURE
    traceback = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime)

    # For easy querying
    __table_args__ = (
        Index("ix_task_status_created", "status", "created_at"),
    )
```

**Monitoring Queries**:

```python
# Get task success rate for last 24 hours
async def get_task_success_rate() -> float:
    async with async_session_maker() as db:
        result = await db.execute(
            select(
                func.count(TaskResult.id).filter(TaskResult.status == "SUCCESS").label("success"),
                func.count(TaskResult.id).label("total")
            )
            .where(TaskResult.created_at >= datetime.utcnow() - timedelta(hours=24))
        )
        row = result.one()
        return (row.success / row.total) * 100 if row.total > 0 else 0.0
```

### Results

- Redis memory usage: 4 GB → 500 MB (8x reduction)
- Task result retention: 1 day → 7 days (matches audit requirements)
- Historical task analysis: Enabled (can query past task failures)

### Key Insight

**Database result backend is better for production.** Redis is fast but volatile; PostgreSQL gives durability and queryability.

---

## Learning 7: Beat Scheduler Needs Timezone Awareness

**Date Learned**: July 2025
**Impact**: Low - Prevented scheduling errors

### The Problem

Celery Beat scheduler for periodic tasks (daily backups, cleanup jobs) ran at wrong times after daylight saving time change.

```python
# ❌ WRONG: Naive datetime
celery_app.conf.beat_schedule = {
    "daily_backup": {
        "task": "app.workers.admin_tasks.backup_database",
        "schedule": crontab(hour=2, minute=0),  # 02:00 - but which timezone?
    }
}
```

**Issue**: `crontab(hour=2)` uses UTC, but business expects 02:00 Europe/Berlin time.

### The Solution

```python
from celery.schedules import crontab
import pytz

# Set Celery timezone
celery_app.conf.timezone = "Europe/Berlin"
celery_app.conf.enable_utc = False

celery_app.conf.beat_schedule = {
    "daily_backup": {
        "task": "app.workers.admin_tasks.backup_database",
        "schedule": crontab(hour=2, minute=0),  # 02:00 Berlin time
        "kwargs": {"backup_type": "full"},
    },

    "hourly_cleanup": {
        "task": "app.workers.admin_tasks.cleanup_temp_files",
        "schedule": crontab(minute=0),  # Every hour
    },

    "weekly_report": {
        "task": "app.workers.admin_tasks.generate_weekly_report",
        "schedule": crontab(hour=8, minute=0, day_of_week=1),  # Monday 08:00
    },
}
```

**Start Beat Scheduler**:

```bash
# Separate process for scheduler
celery -A app.celery beat --loglevel=info --pidfile=/var/run/celery/beat.pid
```

### Results

- Scheduled task timing: Correct across DST changes
- Business expectations: Met (backups run at 02:00 local time)

### Key Insight

**Always set explicit timezone for Beat scheduler.** UTC is not intuitive for business operations.

---

## Configuration Summary

**Production-Ready Celery Configuration**:

```python
# app/celery_config.py
from celery import Celery
from celery.schedules import crontab

celery_app = Celery("ablage")

celery_app.conf.update(
    # Broker and Backend
    broker_url="redis://localhost:6379/0",
    result_backend="db+postgresql+asyncpg://user:pass@localhost/ablage",

    # Worker Configuration (GPU-optimized)
    worker_pool="solo",  # Single process for GPU
    worker_prefetch_multiplier=1,  # No prefetching for GPU tasks
    worker_max_tasks_per_child=100,  # Restart after 100 tasks
    worker_max_memory_per_child=14_000_000,  # 14 GB RSS limit

    # Task Configuration
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,  # Track when tasks start
    task_time_limit=1800,  # 30 minutes hard limit
    task_soft_time_limit=1500,  # 25 minutes soft limit
    task_acks_late=True,  # Acknowledge after task completes (for reliability)
    task_reject_on_worker_lost=True,  # Requeue if worker crashes

    # Result Backend
    result_expires=604800,  # 7 days
    result_extended=True,  # Store task metadata
    result_backend_cleanup=True,  # Auto-cleanup old results

    # Timezone
    timezone="Europe/Berlin",
    enable_utc=False,

    # Task Routes (Priority Queues)
    task_routes={
        "app.workers.ocr_tasks.process_urgent": {"queue": "urgent"},
        "app.workers.ocr_tasks.process_document": {"queue": "default"},
        "app.workers.ocr_tasks.process_batch": {"queue": "batch"},
    },

    # Beat Schedule (Periodic Tasks)
    beat_schedule={
        "daily_backup": {
            "task": "app.workers.admin_tasks.backup_database",
            "schedule": crontab(hour=2, minute=0),
        },
        "cleanup_temp_files": {
            "task": "app.workers.admin_tasks.cleanup_temp_files",
            "schedule": crontab(minute=0),  # Every hour
        },
    },
)
```

---

## Monitoring and Alerting

**Key Metrics to Track**:

```python
from prometheus_client import Counter, Histogram, Gauge

# Task metrics
celery_task_total = Counter(
    "celery_task_total",
    "Total Celery tasks",
    ["task_name", "status"]
)

celery_task_duration = Histogram(
    "celery_task_duration_seconds",
    "Task execution time",
    ["task_name"]
)

celery_queue_length = Gauge(
    "celery_queue_length",
    "Current queue length",
    ["queue_name"]
)

celery_worker_restarts = Counter(
    "celery_worker_restarts_total",
    "Worker restart count"
)
```

**Prometheus Alerts**:

```yaml
# prometheus/alerts/celery.yml
groups:
  - name: celery
    rules:
      - alert: CeleryQueueBackup
        expr: celery_queue_length{queue_name="default"} > 1000
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Celery queue backup detected"
          description: "Queue {{ $labels.queue_name }} has {{ $value }} tasks pending"

      - alert: CeleryHighFailureRate
        expr: rate(celery_task_total{status="FAILURE"}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High Celery task failure rate"
          description: "Failure rate: {{ $value | humanizePercentage }}"

      - alert: CeleryWorkerDown
        expr: up{job="celery"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Celery worker is down"
```

---

## Troubleshooting Cheatsheet

### Check Worker Status

```bash
# Active workers
celery -A app.celery inspect active

# Registered tasks
celery -A app.celery inspect registered

# Stats
celery -A app.celery inspect stats

# Ping workers
celery -A app.celery inspect ping
```

### Check Queue Length

```bash
# All queues
celery -A app.celery inspect active_queues

# Redis queue length
redis-cli LLEN default
redis-cli LLEN urgent
redis-cli LLEN batch
```

### Purge Queue (DANGER!)

```bash
# Purge specific queue
celery -A app.celery purge -Q batch

# Purge all queues (!!!!)
celery -A app.celery purge
```

### Revoke Task

```bash
# Revoke by task ID
celery -A app.celery revoke <task_id> --terminate

# Revoke multiple
celery -A app.celery revoke <task_id_1> <task_id_2> --terminate
```

---

## Anti-Patterns to Avoid

### 1. ❌ Passing Large Objects as Arguments

```python
# ❌ WRONG: Serialize 50 MB document
@celery_app.task
def process_document(document_bytes: bytes):
    pass

# ✅ CORRECT: Pass ID, load in task
@celery_app.task
def process_document(document_id: str):
    document = storage.load(document_id)
    pass
```

### 2. ❌ Chaining GPU Tasks

```python
# ❌ WRONG: Chain GPU tasks (VRAM accumulates)
chain(
    load_model_task.s(),
    process_document.s(doc_id),
    extract_entities.s()
).apply_async()

# ✅ CORRECT: Single task with multiple steps
@celery_app.task
def process_document_full(doc_id):
    model = load_model()
    ocr_result = process_with_model(model, doc_id)
    entities = extract_entities(ocr_result)
    return entities
```

### 3. ❌ Ignoring Task Time Limits

```python
# ❌ WRONG: No timeout
@celery_app.task
def process_document(doc_id):
    # Could run forever
    pass

# ✅ CORRECT: Set time limits
@celery_app.task(time_limit=1800, soft_time_limit=1500)  # 30 min hard, 25 min soft
def process_document(doc_id):
    pass
```

---

## Future Improvements

**Planned for Q1 2026**:

1. **Task Prioritization Within Queue**: Use `task_queue_max_priority` to prioritize within queue based on document size
2. **Dynamic Worker Scaling**: Auto-scale workers based on queue length (Kubernetes HPA)
3. **Task Result Compression**: Compress large task results before storing (zlib/gzip)
4. **GPU Batch Processing**: Batch multiple small documents in single GPU inference
5. **Dead Letter Queue**: Move permanently failed tasks to separate queue for analysis

---

## Related Documentation

- [Skills: Monitoring & Observability](../../Static_Knowledge/Skills/monitoring_observability_skill.yaml)
- [Playbook: Database Performance](../../Relations/Playbooks/database_performance_playbook.yaml)
- [Skills: GPU Management](../../Static_Knowledge/Skills/gpu_management_skill.yaml)
- [MOC: OCR Processing](../../Meta_Layer/MOCs/OCR_PROCESSING_MOC.md)

---

**Contributors**: Backend Team, DevOps Team
**Contact**: #ablage-infrastructure on Slack
**Next Review**: 2026-02-22
