# Celery Task Deadlock Recovery Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High)
> RTO: 15 Minuten | RPO: Tasks können wiederholt werden

## Alert

```
CeleryTaskDeadlock - Task hängt > 30 Minuten
CeleryWorkerUnresponsive - Worker antwortet nicht auf Ping
CeleryTaskStuck - Task im Status "started" > 60 Minuten
```

## Symptome

- Tasks bleiben im Status "STARTED" hängen
- Worker reagiert nicht auf `celery inspect ping`
- Neue Tasks werden nicht verarbeitet
- CPU-Auslastung bei 0% oder 100% (Deadlock/Busy-Loop)
- Memory-Nutzung steigt kontinuierlich (Memory Leak)

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Worker-Status prüfen

```bash
# Worker-Ping
docker exec ablage-worker celery -A app.workers.celery_app inspect ping

# Aktive Tasks
docker exec ablage-worker celery -A app.workers.celery_app inspect active

# Reserved Tasks
docker exec ablage-worker celery -A app.workers.celery_app inspect reserved

# Worker-Statistiken
docker exec ablage-worker celery -A app.workers.celery_app inspect stats
```

### 2. Hängende Tasks identifizieren

```bash
# Tasks im Status "STARTED"
docker exec ablage-backend python -c "
from app.workers.celery_app import app
from celery.result import AsyncResult

# Aktive Task-IDs aus Redis
import redis
r = redis.Redis.from_url('redis://localhost:6379')
for key in r.scan_iter('celery-task-meta-*'):
    task_id = key.decode().replace('celery-task-meta-', '')
    result = AsyncResult(task_id, app=app)
    if result.state == 'STARTED':
        print(f'{task_id}: {result.state} since {result.date_done}')
"

# Detaillierte Task-Info
docker exec ablage-worker celery -A app.workers.celery_app inspect query_task <task_id>
```

### 3. Worker-Prozess analysieren

```bash
# Worker-Container-Status
docker stats ablage-worker --no-stream

# Prozesse im Worker
docker exec ablage-worker ps aux

# Thread-Dump
docker exec ablage-worker python -c "
import faulthandler
faulthandler.dump_traceback()
"

# Strace für hängenden Prozess
docker exec ablage-worker strace -p <PID> -f -s 1000 2>&1 | head -50
```

---

## Diagnose

### 4. Deadlock-Ursache identifizieren

```bash
# Lock-Dateien prüfen
docker exec ablage-worker ls -la /tmp/*.lock 2>/dev/null

# Redis-Locks prüfen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD KEYS "*lock*"

# GPU-Lock (häufige Ursache)
docker exec ablage-backend python -c "
from app.gpu_manager import GPUManager
gm = GPUManager()
print(gm.get_detailed_status())
"

# Database-Locks
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT pid, state, query, wait_event_type, wait_event
FROM pg_stat_activity
WHERE state != 'idle';
"
```

### 5. Celery-Logs analysieren

```bash
# Worker-Logs (letzte Aktivität)
docker logs ablage-worker --since 30m 2>&1 | tail -100

# Fehler und Exceptions
docker logs ablage-worker --since 1h 2>&1 | grep -E "ERROR|Exception|Traceback"

# Task-Lifecycle
docker logs ablage-worker --since 1h 2>&1 | grep -E "Task|received|succeeded|failed"
```

### 6. Memory-Leak erkennen

```bash
# Memory-Trend
docker stats ablage-worker --no-stream --format "{{.MemUsage}}"

# Python Memory-Profiling
docker exec ablage-worker python -c "
import tracemalloc
tracemalloc.start()

# Snapshot nach kurzer Zeit
import time
time.sleep(5)
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
"
```

---

## Lösung

### Option A: Graceful Worker-Restart

```bash
# SIGTERM senden (graceful)
docker-compose kill -s SIGTERM worker

# Warten auf Beendigung (max 60s)
timeout 60 docker wait ablage-worker || docker kill ablage-worker

# Worker neu starten
docker-compose up -d worker
```

### Option B: Task revoken und Worker neustarten

```bash
# Hängende Tasks abbrechen
docker exec ablage-worker celery -A app.workers.celery_app control revoke <task_id> --terminate

# Alle aktiven Tasks abbrechen
docker exec ablage-backend python -c "
from app.workers.celery_app import app

i = app.control.inspect()
active = i.active() or {}

for worker, tasks in active.items():
    for task in tasks:
        app.control.revoke(task['id'], terminate=True, signal='SIGKILL')
        print(f'Revoked: {task[\"id\"]}')"

# Worker neustarten
docker-compose restart worker
```

### Option C: Force Kill und Cleanup

```bash
# Worker hart beenden
docker-compose kill worker

# Locks bereinigen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD DEL "gpu:lock" "celery:lock:*"

# Stale Tasks bereinigen
docker exec ablage-backend python -c "
from app.workers.celery_app import app
import redis

r = redis.Redis.from_url('redis://localhost:6379')
for key in r.scan_iter('celery-task-meta-*'):
    task_id = key.decode().replace('celery-task-meta-', '')
    result = app.AsyncResult(task_id)
    if result.state in ['STARTED', 'PENDING']:
        result.forget()
        print(f'Cleaned: {task_id}')
"

# Worker neu starten
docker-compose up -d worker
```

### Option D: Pool-Typ ändern

```bash
# Prefork kann Deadlocks verursachen - auf solo wechseln
# docker-compose.yml
services:
  worker:
    command: >
      celery -A app.workers.celery_app worker
      --loglevel=info
      --concurrency=1
      --pool=solo
```

### Option E: Task-Timeout setzen

```python
# celery_app.py
app.conf.task_soft_time_limit = 1800  # 30 Minuten Soft-Limit
app.conf.task_time_limit = 3600       # 60 Minuten Hard-Limit
app.conf.task_acks_late = True        # Acknowledge nach Completion

# Oder pro Task
@app.task(soft_time_limit=600, time_limit=900)
def process_document(doc_id):
    ...
```

---

## Database-Deadlock-Behandlung

### PostgreSQL-Locks prüfen

```bash
# Aktive Locks
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT
    blocked_locks.pid AS blocked_pid,
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

# Blockierende Transaktion beenden
docker exec ablage-postgres psql -U ablage_admin -d ablage -c "
SELECT pg_terminate_backend(<blocking_pid>);
"
```

---

## Redis-Lock-Cleanup

```bash
# Alle Celery-Locks anzeigen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD KEYS "*lock*"

# Stale Locks löschen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD DEL "celery:lock:task_queue"
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD DEL "celery:lock:chord_unlock"

# Lock-TTL prüfen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD TTL "celery:lock:task_queue"
```

---

## Monitoring

### Prometheus Alerts

```yaml
groups:
  - name: celery_deadlock_alerts
    rules:
      - alert: CeleryTaskStuck
        expr: |
          celery_task_started_total - celery_task_succeeded_total - celery_task_failed_total > 0
          and
          time() - celery_task_last_activity_seconds > 1800
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Celery Task hängt seit 30+ Minuten"

      - alert: CeleryWorkerUnresponsive
        expr: celery_worker_ping_latency_seconds > 30
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Celery Worker antwortet nicht"

      - alert: CeleryMemoryLeak
        expr: |
          rate(container_memory_usage_bytes{name="ablage-worker"}[1h]) > 10000000
        for: 30m
        labels:
          severity: warning
        annotations:
          summary: "Worker Memory steigt kontinuierlich"
```

### Celery Flower Dashboard

```bash
# Flower starten (falls nicht aktiv)
docker-compose up -d flower

# Flower UI: http://localhost:5555
# Zeigt: Task-Status, Worker-Health, Queue-Länge
```

---

## Verifikation

```bash
# Worker-Ping
docker exec ablage-worker celery -A app.workers.celery_app inspect ping

# Keine stuck Tasks
docker exec ablage-worker celery -A app.workers.celery_app inspect active

# Test-Task
docker exec ablage-backend python -c "
from app.workers.tasks import health_check
result = health_check.delay()
print(f'Task ID: {result.id}')
print(f'Result: {result.get(timeout=10)}')
"

# Queue verarbeitet Tasks
docker exec ablage-worker celery -A app.workers.celery_app inspect stats
```

---

## Präventivmaßnahmen

### 1. Task-Timeouts setzen

```python
# Alle Tasks mit Timeout
app.conf.task_default_rate_limit = '10/m'
app.conf.task_soft_time_limit = 600   # 10 Minuten
app.conf.task_time_limit = 900        # 15 Minuten
```

### 2. Heartbeat aktivieren

```python
# celery_app.py
app.conf.worker_send_task_events = True
app.conf.task_send_sent_event = True
app.conf.worker_prefetch_multiplier = 1
```

### 3. Automatic Worker Restart

```yaml
# docker-compose.yml
services:
  worker:
    restart: always
    deploy:
      resources:
        limits:
          memory: 4G
    healthcheck:
      test: ["CMD", "celery", "-A", "app.workers.celery_app", "inspect", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Eskalation

| Symptom | Aktion |
|---------|--------|
| Task hängt 10-30 Min | Beobachten, Logs prüfen |
| Task hängt 30-60 Min | Graceful Restart |
| Worker nicht erreichbar | Force Kill + Cleanup |
| Wiederkehrende Deadlocks | Code-Review, Pool-Typ ändern |

---

## Verwandte Runbooks

- [GPU Lock Contention](gpu-lock-contention.md)
- [Celery Queue Backlog](celery-queue-backlog.md)
- [Celery Worker Recovery](celery-worker-restart.md)
- [PostgreSQL Connection Pool](postgresql-connection-pool-exhaustion.md)
