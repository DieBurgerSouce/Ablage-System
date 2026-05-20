# Celery Queue Backlog Runbook

> **Ablage-System Operations Runbook**
> Severity: SEV-2 (High)
> RTO: 30 Minuten | RPO: Tasks queued (keine Datenverlust)

## Alert

```
CeleryQueueBacklogWarning - > 50 pending tasks
CeleryQueueBacklogCritical - > 200 pending tasks
```

## Symptome

- Dokumente bleiben im Status "pending" oder "queued"
- Lange Wartezeiten für OCR-Verarbeitung
- Dashboard zeigt wachsende Queue-Tiefe
- Benutzer beschweren sich über langsame Verarbeitung

---

## Sofortmaßnahmen (< 5 Minuten)

### 1. Queue-Status prüfen

```bash
# Aktive Queues und Tiefe
docker exec ablage-worker celery -A app.workers.celery_app inspect active_queues

# Queue-Längen via Redis
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD LLEN celery

# Detaillierte Queue-Statistiken
docker exec ablage-worker celery -A app.workers.celery_app inspect stats
```

### 2. Worker-Status prüfen

```bash
# Aktive Worker
docker exec ablage-worker celery -A app.workers.celery_app inspect active

# Worker-Ping
docker exec ablage-worker celery -A app.workers.celery_app inspect ping

# Reservierte Tasks
docker exec ablage-worker celery -A app.workers.celery_app inspect reserved
```

### 3. GPU-Status prüfen (häufige Ursache)

```bash
# GPU-Auslastung
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv

# GPU-Lock Status
docker exec ablage-backend python -c "
from app.gpu_manager import GPUManager
gm = GPUManager()
print(gm.get_detailed_status())
"
```

---

## Diagnose (5-15 Minuten)

### 4. Task-Fehler identifizieren

```bash
# Fehlgeschlagene Tasks in letzter Stunde
docker exec ablage-worker celery -A app.workers.celery_app events -d

# Task-Logs
docker logs ablage-worker --since 1h 2>&1 | grep -E "(ERROR|FAILURE|Exception)"
```

### 5. Queue-Verteilung analysieren

```bash
# Tasks nach Queue
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD KEYS "celery*" | while read key; do
    echo "$key: $(docker exec ablage-redis redis-cli -a $REDIS_PASSWORD LLEN $key)"
done
```

### 6. Durchsatz messen

```bash
# Tasks pro Minute (letzte 10 Minuten)
docker exec ablage-backend python -c "
from app.metrics import get_task_throughput
print(f'Durchsatz: {get_task_throughput()} tasks/min')
"
```

---

## Lösung

### Option A: Worker horizontal skalieren

```bash
# Zusätzlichen Worker starten
docker-compose up -d --scale worker=3

# Oder mit spezifischer Queue
docker-compose exec -d worker celery -A app.workers.celery_app worker \
    --loglevel=info \
    --queues=ocr_high_priority \
    --concurrency=1
```

### Option B: GPU-Speicher freigeben

```bash
# GPU Cache leeren
docker exec ablage-worker python -c "
import torch
torch.cuda.empty_cache()
import gc
gc.collect()
"

# Worker neu starten
docker-compose restart worker
```

### Option C: Niedrigprioritäre Tasks verschieben

```bash
# Tasks temporär pausieren (Flower UI)
curl -X POST http://localhost:5555/api/queue/low_priority/pause

# Oder: Rate Limiter aktivieren
docker exec ablage-backend python -c "
from app.core.rate_limiter import set_ocr_rate_limit
set_ocr_rate_limit(requests_per_minute=10)
"
```

### Option D: Queue purgen (Notfall)

```bash
# WARNUNG: Löscht alle ausstehenden Tasks!
docker exec ablage-worker celery -A app.workers.celery_app purge -f

# Spezifische Queue purgen
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD DEL celery_low_priority
```

---

## Langfristige Maßnahmen

### 1. Auto-Scaling konfigurieren

```python
# celery_app.py
app.conf.worker_autoscaler = 'celery.worker.autoscale:Autoscaler'
app.conf.worker_autoscale = (10, 3)  # Max 10, Min 3 Workers

# Oder: KEDA-basiertes Scaling in Kubernetes
```

### 2. Queue-Prioritäten optimieren

```python
# Prioritäts-Queues definieren
CELERY_QUEUES = {
    'ocr_critical': {'priority': 10},
    'ocr_high': {'priority': 7},
    'ocr_default': {'priority': 5},
    'ocr_low': {'priority': 3},
    'batch_export': {'priority': 1},
}
```

### 3. Backpressure implementieren

```python
# API mit Queue-Backpressure
@router.post("/documents/upload")
async def upload_document(file: UploadFile):
    queue_depth = await get_queue_depth()
    if queue_depth > 100:
        raise HTTPException(
            status_code=503,
            detail="System überlastet. Bitte später erneut versuchen.",
            headers={"Retry-After": "60"}
        )
    # ... normale Verarbeitung
```

---

## Verifikation

```bash
# Queue-Tiefe nach Fix
docker exec ablage-redis redis-cli -a $REDIS_PASSWORD LLEN celery

# Worker-Aktivität
docker exec ablage-worker celery -A app.workers.celery_app inspect active

# Durchsatz prüfen (sollte steigen)
watch -n 5 'curl -s http://localhost:8000/api/v1/metrics | grep celery_tasks_completed'
```

---

## Metriken & Dashboards

- **Grafana Dashboard**: "Celery Queue Monitoring"
- **Prometheus Queries**:
  ```promql
  # Queue-Tiefe
  celery_queue_length{queue="celery"}

  # Durchsatz
  rate(celery_task_completed_total[5m])

  # Wartezeit
  histogram_quantile(0.95, celery_task_wait_seconds_bucket)
  ```

---

## Eskalation

| Queue-Tiefe | Aktion |
|-------------|--------|
| 50-100 | On-Call: Beobachten |
| 100-200 | Worker skalieren |
| 200-500 | Team-Lead informieren |
| 500+ | Eskalation: Platform Team |

---

## Verwandte Runbooks

- [Celery Worker Recovery](celery-worker-restart.md)
- [GPU OOM Recovery](gpu-oom-recovery.md)
- [Redis Cluster Recovery](redis-cluster-recovery.md)
