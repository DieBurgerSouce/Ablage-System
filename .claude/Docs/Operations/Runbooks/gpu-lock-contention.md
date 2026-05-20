# GPU Lock Contention Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High)
> RTO: 15 Minuten | RPO: N/A (Tasks werden wiederholt)

## Alert

```
GPULockTimeout - GPU Lock nicht in 180s erhalten
GPULockContention - > 5 Tasks warten auf GPU
GPUHighQueueTime - GPU Queue-Wartezeit > 60s
```

## Symptome

- OCR-Tasks hängen im Status "pending"
- Celery-Worker zeigen "waiting for GPU lock"
- GPU-Auslastung bei 0% obwohl Tasks warten
- Timeout-Fehler in Worker-Logs
- Dashboard zeigt wachsende Task-Queue

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. GPU-Lock-Status prüfen

```bash
# Aktuelle Lock-Inhaber
docker exec ablage-backend python -c "
from app.gpu_manager import GPUManager
gm = GPUManager()
status = gm.get_detailed_status()
print(f'Lock held by: {status.lock_holder}')
print(f'Lock acquired at: {status.lock_acquired_at}')
print(f'Waiting tasks: {status.waiting_count}')
print(f'Lock timeout: {status.lock_timeout}s')
"

# GPU-Nutzung
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv
```

### 2. Hängende Prozesse identifizieren

```bash
# GPU-Prozesse
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv

# Celery-Worker-Status
docker exec ablage-worker celery -A app.workers.celery_app inspect active

# Worker mit GPU-Tasks
docker logs ablage-worker --since 10m 2>&1 | grep -E "GPU|cuda|torch"
```

### 3. Lock-Reset (Notfall)

```bash
# GPU-Lock forciert freigeben
docker exec ablage-backend python -c "
from app.gpu_manager import GPUManager
gm = GPUManager()
gm.force_release_lock()
print('GPU Lock released')
"

# Alternative: Redis-Lock direkt löschen
docker exec ablage-redis redis-cli -a \$REDIS_PASSWORD DEL "gpu:lock"
docker exec ablage-redis redis-cli -a \$REDIS_PASSWORD DEL "gpu:lock:holder"
```

---

## Diagnose

### 4. Lock-Historie analysieren

```bash
# Lock-Acquire/Release-Logs
docker logs ablage-worker --since 1h 2>&1 | grep -E "acquire|release|lock"

# Durchschnittliche Lock-Dauer
docker exec ablage-backend python -c "
from app.services.gpu_metrics_service import GPUMetricsService
metrics = GPUMetricsService()
stats = metrics.get_lock_statistics(hours=1)
print(f'Avg lock duration: {stats.avg_duration_seconds:.2f}s')
print(f'Max lock duration: {stats.max_duration_seconds:.2f}s')
print(f'Lock acquisitions: {stats.total_acquisitions}')
print(f'Lock timeouts: {stats.timeout_count}')
"
```

### 5. GPU-Prozess-Status

```bash
# Detaillierte GPU-Prozess-Info
nvidia-smi pmon -s um -c 5

# CUDA-Kontext prüfen
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv

# Zombie-Prozesse finden
ps aux | grep -E "python.*ocr|torch|cuda" | grep -v grep
```

### 6. Worker-Deadlocks erkennen

```bash
# Worker-Thread-Dump
docker exec ablage-worker python -c "
import sys
import traceback
import threading

for thread_id, frame in sys._current_frames().items():
    print(f'\n--- Thread {thread_id} ---')
    traceback.print_stack(frame)
"

# Celery-Events
docker exec ablage-worker celery -A app.workers.celery_app events --dump
```

---

## Lösung

### Option A: Worker neu starten

```bash
# Graceful Worker-Restart
docker-compose restart worker

# Falls Worker nicht reagiert
docker-compose kill worker
docker-compose up -d worker

# GPU-Speicher bereinigen
docker exec ablage-worker python -c "
import torch
torch.cuda.empty_cache()
import gc
gc.collect()
"
```

### Option B: Lock-Timeout erhöhen

```bash
# Temporär längeren Timeout setzen
docker exec ablage-backend python -c "
from app.core.config import update_runtime_setting
update_runtime_setting('GPU_LOCK_TIMEOUT', 300)  # 5 Minuten
"

# Oder in .env
# GPU_LOCK_TIMEOUT=300
```

### Option C: Konkurrenz reduzieren

```bash
# Nur einen Worker mit GPU-Tasks
docker-compose up -d --scale worker=1 worker

# Oder: Concurrency auf 1 setzen
# docker-compose.yml
# command: celery -A app.workers.celery_app worker --concurrency=1 --pool=solo
```

### Option D: GPU-Prozess beenden

```bash
# Hängenden GPU-Prozess identifizieren
nvidia-smi --query-compute-apps=pid,process_name --format=csv,noheader

# Prozess beenden (VORSICHT!)
PID=$(nvidia-smi --query-compute-apps=pid --format=csv,noheader | head -1)
if [ -n "$PID" ]; then
    kill -9 $PID
    echo "Killed GPU process $PID"
fi

# GPU-Reset (letzte Option)
nvidia-smi --gpu-reset -i 0
```

### Option E: Distributed Locking verbessern

```python
# app/gpu_manager.py - Verbesserter Lock-Mechanismus
import redis
from contextlib import contextmanager

class GPUManager:
    def __init__(self):
        self.redis = redis.Redis.from_url(settings.REDIS_URL)
        self.lock_name = "gpu:lock"
        self.lock_timeout = settings.GPU_LOCK_TIMEOUT

    @contextmanager
    def acquire_gpu(self, task_id: str, timeout: int = None):
        """Acquire GPU lock with automatic release."""
        timeout = timeout or self.lock_timeout
        lock = self.redis.lock(
            self.lock_name,
            timeout=timeout,
            blocking_timeout=timeout,
            thread_local=False
        )

        acquired = lock.acquire(blocking=True)
        if not acquired:
            raise GPULockTimeoutError(f"Could not acquire GPU lock in {timeout}s")

        try:
            self.redis.set("gpu:lock:holder", task_id, ex=timeout)
            yield
        finally:
            try:
                lock.release()
            except redis.exceptions.LockError:
                pass  # Lock already released/expired
            self.redis.delete("gpu:lock:holder")
```

---

## Queue-Management

### Wartende Tasks priorisieren

```bash
# Hochprioritäts-Tasks vorziehen
docker exec ablage-worker celery -A app.workers.celery_app inspect reserved

# Queue neu ordnen (falls möglich)
docker exec ablage-backend python -c "
from app.workers.celery_app import app
from celery import chain

# Pending Tasks abrufen
i = app.control.inspect()
reserved = i.reserved()
print(f'Reserved tasks: {reserved}')
"
```

### Tasks abbrechen

```bash
# Bestimmten Task abbrechen
docker exec ablage-worker celery -A app.workers.celery_app control revoke <task_id> --terminate

# Alle wartenden GPU-Tasks abbrechen
docker exec ablage-backend python -c "
from app.workers.celery_app import app

i = app.control.inspect()
reserved = i.reserved() or {}

for worker, tasks in reserved.items():
    for task in tasks:
        if 'ocr' in task.get('name', '').lower():
            app.control.revoke(task['id'], terminate=True)
            print(f'Revoked: {task[\"id\"]}')"
```

---

## Monitoring

### Prometheus Alerts

```yaml
groups:
  - name: gpu_alerts
    rules:
      - alert: GPULockTimeout
        expr: gpu_lock_wait_seconds > 180
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "GPU Lock Timeout (>180s)"

      - alert: GPULockContention
        expr: gpu_lock_waiting_tasks > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Hohe GPU Lock Contention"

      - alert: GPUIdleWithQueue
        expr: nvidia_gpu_utilization == 0 AND gpu_task_queue_length > 0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU idle obwohl Tasks warten"
```

### Lock-Metriken exportieren

```python
# app/metrics.py
from prometheus_client import Gauge, Counter, Histogram

gpu_lock_waiting_tasks = Gauge(
    'gpu_lock_waiting_tasks',
    'Number of tasks waiting for GPU lock'
)

gpu_lock_acquisitions = Counter(
    'gpu_lock_acquisitions_total',
    'Total GPU lock acquisitions'
)

gpu_lock_duration = Histogram(
    'gpu_lock_duration_seconds',
    'GPU lock hold duration',
    buckets=[1, 5, 10, 30, 60, 120, 180]
)
```

---

## Verifikation

```bash
# Lock-Status nach Fix
docker exec ablage-backend python -c "
from app.gpu_manager import GPUManager
gm = GPUManager()
print(gm.get_detailed_status())
"

# GPU-Auslastung
nvidia-smi --query-gpu=utilization.gpu --format=csv -l 1

# Task-Queue leer?
docker exec ablage-worker celery -A app.workers.celery_app inspect active

# Test-OCR
curl -X POST http://localhost:8000/api/v1/ocr/test \
  -F "file=@tests/fixtures/sample.pdf" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Präventivmaßnahmen

### 1. Lock-Timeouts konfigurieren

```python
# settings.py
GPU_LOCK_TIMEOUT = 180  # Sekunden
GPU_LOCK_RETRY_DELAY = 5  # Sekunden zwischen Retries
GPU_MAX_LOCK_RETRIES = 3
```

### 2. Task-Priorisierung

```python
# celery_app.py
app.conf.task_routes = {
    'app.workers.tasks.ocr_high_priority': {'queue': 'gpu_high'},
    'app.workers.tasks.ocr_normal': {'queue': 'gpu_normal'},
    'app.workers.tasks.ocr_batch': {'queue': 'gpu_low'},
}

app.conf.task_queue_max_priority = 10
```

### 3. Automatisches Lock-Cleanup

```python
# Celery Beat Schedule
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
        60.0,  # Alle 60 Sekunden
        cleanup_stale_gpu_locks.s(),
        name='cleanup-gpu-locks'
    )

@app.task
def cleanup_stale_gpu_locks():
    from app.gpu_manager import GPUManager
    gm = GPUManager()
    gm.cleanup_stale_locks(max_age_seconds=300)
```

---

## Eskalation

| Wartezeit | Aktion |
|-----------|--------|
| 30-60s | Normal, beobachten |
| 60-120s | Lock-Holder prüfen |
| 120-180s | Worker-Restart erwägen |
| 180s+ | Lock-Reset, Eskalation |

---

## Verwandte Runbooks

- [GPU OOM Recovery](gpu-oom-recovery.md)
- [Celery Queue Backlog](celery-queue-backlog.md)
- [Celery Worker Recovery](celery-worker-restart.md)
