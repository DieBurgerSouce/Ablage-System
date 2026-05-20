# Runbook: Celery Worker Recovery

> Wiederherstellung bei Celery Worker Ausfaellen

## Uebersicht

| Metrik | Wert |
|--------|------|
| Severity | HIGH |
| RTO | 5 Minuten |
| RPO | Tasks werden gequeued |
| On-Call | Backend Team |

## Symptome

- OCR-Verarbeitung haengt
- Tasks bleiben im "pending" Status
- GPU wird nicht genutzt obwohl verfuegbar
- Keine Fortschrittsmeldungen bei Batch-Jobs

## Diagnose

### 1. Worker-Status pruefen

```bash
# Container-Status
docker compose ps worker

# Worker-Logs
docker compose logs --tail=100 worker

# Celery Worker Status
docker compose exec backend celery -A app.workers.celery_app inspect active
docker compose exec backend celery -A app.workers.celery_app inspect reserved
docker compose exec backend celery -A app.workers.celery_app inspect stats
```

### 2. Queue-Status pruefen

```bash
# Queue-Laenge
docker compose exec redis redis-cli LLEN celery

# Aufgaben in Queue
docker compose exec backend celery -A app.workers.celery_app inspect scheduled
```

### 3. GPU-Status pruefen (falls GPU-Worker)

```bash
# GPU verfuegbar?
nvidia-smi

# GPU im Container sichtbar?
docker compose exec worker nvidia-smi

# GPU-Lock Status
docker compose exec redis redis-cli GET "gpu:lock:0"
```

### 4. Haeufige Fehler

| Fehler | Ursache |
|--------|---------|
| `Worker not found` | Worker nicht gestartet |
| `Connection refused` | Redis nicht erreichbar |
| `CUDA out of memory` | GPU Memory erschoepft |
| `Task failed` | Fehler in Task-Logik |
| `deadlock` | GPU-Lock nicht freigegeben |

## Recovery-Schritte

### Fall 1: Worker gestoppt/crashed

```bash
# Neustart
docker compose restart worker

# Logs pruefen
docker compose logs -f worker

# Verifizieren
docker compose exec backend celery -A app.workers.celery_app inspect ping
```

### Fall 2: Tasks haengen (Deadlock)

```bash
# Aktive Tasks pruefen
docker compose exec backend celery -A app.workers.celery_app inspect active

# Worker graceful restart
docker compose exec worker celery -A app.workers.celery_app control shutdown
docker compose up -d worker

# GPU-Lock freigeben (falls noetig)
docker compose exec redis redis-cli DEL "gpu:lock:0"
```

### Fall 3: GPU Memory erschoepft

```bash
# GPU-Status
nvidia-smi

# GPU-Cache leeren
docker compose exec worker python -c "import torch; torch.cuda.empty_cache()"

# Worker neu starten
docker compose restart worker

# Falls GPU immer noch belegt:
# ACHTUNG: Stoppt alle GPU-Prozesse!
sudo fuser -k /dev/nvidia0
docker compose restart worker
```

### Fall 4: Queue uebergelaufen

```bash
# Queue-Laenge
docker compose exec redis redis-cli LLEN celery

# Alte/fehlgeschlagene Tasks loeschen
docker compose exec backend celery -A app.workers.celery_app purge -f

# Worker mit mehr Concurrency starten (temporaer)
docker compose exec worker celery -A app.workers.celery_app worker \
  --concurrency=4 --pool=solo --loglevel=info
```

### Fall 5: Worker kann Redis nicht erreichen

```bash
# Redis-Verbindung testen
docker compose exec worker python -c "
import redis
r = redis.Redis(host='redis', port=6379)
print(r.ping())
"

# Netzwerk pruefen
docker network inspect ablage_backend-network

# Services neu verbinden
docker compose restart redis worker
```

## Stuck Tasks retten

```bash
# Fehlgeschlagene Tasks finden
docker compose exec backend celery -A app.workers.celery_app events -d

# Task-Status in DB aktualisieren
docker compose exec backend python -c "
from app.db.session import get_session
from app.db.models import Document
from sqlalchemy import update

with get_session() as db:
    db.execute(
        update(Document)
        .where(Document.status == 'processing')
        .where(Document.updated_at < datetime.now() - timedelta(hours=1))
        .values(status='pending')
    )
    db.commit()
"

# Tasks neu in Queue einreihen
docker compose exec backend python -c "
from app.workers.tasks import process_document
from app.db.session import get_session
from app.db.models import Document

with get_session() as db:
    stuck = db.query(Document).filter(Document.status == 'pending').all()
    for doc in stuck:
        process_document.delay(str(doc.id))
"
```

## Monitoring & Alerting

### Celery Flower (UI)

```bash
# Flower starten
docker compose exec backend celery -A app.workers.celery_app flower \
  --port=5555 --persistent=true

# Zugriff: http://localhost:5555
```

### Prometheus Metriken

```yaml
# Alert bei Worker-Ausfall
- alert: CeleryWorkerDown
  expr: celery_workers == 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "Celery Worker nicht erreichbar"
```

## Verifizierung

Nach Recovery:

```bash
# 1. Worker-Status
docker compose exec backend celery -A app.workers.celery_app inspect ping

# 2. Test-Task ausfuehren
docker compose exec backend python -c "
from app.workers.tasks import health_check_task
result = health_check_task.delay()
print(result.get(timeout=30))
"

# 3. Queue-Status
docker compose exec redis redis-cli LLEN celery

# 4. GPU verfuegbar
docker compose exec worker nvidia-smi
```

## Eskalation

| Zeit | Aktion |
|------|--------|
| 2 min | Worker neugestartet |
| 10 min | Eskalation an Backend Lead |
| 30 min | Eskalation an CTO |

## Praevention

- Worker Auto-Restart (`restart: unless-stopped`)
- Task Timeouts setzen (`task_time_limit`)
- GPU Memory Guard aktivieren
- Dead Letter Queue fuer fehlgeschlagene Tasks
- Monitoring mit Flower oder Prometheus

---

*Letzte Aktualisierung: 2024-12*
