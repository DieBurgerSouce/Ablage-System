# Celery Task Orchestration

> **Feinpoliert und durchdacht** - Enterprise-Grade Task Orchestration für das Ablage-System

## Inhaltsverzeichnis

1. [Übersicht](#übersicht)
2. [Architektur](#architektur)
3. [Task-Kategorien](#task-kategorien)
4. [GPU Task Management](#gpu-task-management)
5. [Queue-Konfiguration](#queue-konfiguration)
6. [Dead Letter Queue (DLQ)](#dead-letter-queue-dlq)
7. [Beat Scheduler](#beat-scheduler)
8. [Monitoring & Metriken](#monitoring--metriken)
9. [Error Handling & Retry-Strategien](#error-handling--retry-strategien)
10. [Best Practices](#best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Übersicht

Das Ablage-System nutzt **Celery 5.3+** als verteilte Task-Queue für asynchrone Verarbeitung. Die Architektur ist speziell für GPU-beschleunigte OCR-Workloads auf einer RTX 4080 (16GB VRAM) optimiert.

### Kernmerkmale

| Feature | Beschreibung |
|---------|--------------|
| **GPU-Isolation** | Solo-Worker-Pool für exklusive GPU-Nutzung |
| **Distributed Locking** | Redis-basiertes GPU-Lock mit Auto-Refresh |
| **Priority Queues** | 10 Prioritätsstufen (0=höchste, 9=niedrigste) |
| **Dead Letter Queue** | Automatische Fehler-Recovery und Inspektion |
| **Prometheus-Metriken** | Enterprise-Monitoring auf Port 8001 |
| **Graceful Degradation** | GPU → CPU Fallback bei OOM |

### Technologie-Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    Celery Workers                           │
│  ┌─────────────────┐  ┌─────────────────┐                  │
│  │   GPU Worker    │  │   CPU Worker    │                  │
│  │  (pool=solo)    │  │  (pool=prefork) │                  │
│  │  concurrency=1  │  │  concurrency=4  │                  │
│  └────────┬────────┘  └────────┬────────┘                  │
│           │                    │                            │
│           ▼                    ▼                            │
│  ┌─────────────────────────────────────────────┐           │
│  │              Redis Broker                    │           │
│  │    ┌──────────────────────────────────┐     │           │
│  │    │  Priority Queues (0-9)           │     │           │
│  │    │  - ocr_high (GPU, P:0-2)         │     │           │
│  │    │  - ocr_normal (GPU, P:3-5)       │     │           │
│  │    │  - embedding_* (GPU, P:4-7)      │     │           │
│  │    │  - validation (CPU, P:5)         │     │           │
│  │    │  - backup (CPU, P:9)             │     │           │
│  │    │  - dlq (Dead Letter Queue)       │     │           │
│  │    └──────────────────────────────────┘     │           │
│  └─────────────────────────────────────────────┘           │
│           │                                                 │
│           ▼                                                 │
│  ┌─────────────────────────────────────────────┐           │
│  │         Redis Result Backend                 │           │
│  │         (gzip, 24h TTL)                      │           │
│  └─────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

---

## Architektur

### Celery App Konfiguration

```python
# app/workers/celery_app.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "ablage_system",
    broker=settings.CELERY_BROKER_URL,      # redis://localhost:6380/0
    backend=settings.CELERY_RESULT_BACKEND, # redis://localhost:6380/1
    include=[
        "app.workers.tasks.ocr_tasks",           # OCR-Verarbeitung
        "app.workers.tasks.embedding_tasks",     # Embedding-Generierung
        "app.workers.tasks.backup_tasks",        # Automatisierte Backups
        "app.workers.tasks.cleanup_tasks",       # Wartungsaufgaben
        "app.workers.tasks.gdpr_tasks",          # DSGVO-Compliance
        "app.workers.tasks.ml_tasks",            # ML-Training & Tracking
        "app.workers.tasks.dlq_management_tasks", # DLQ-Management
        "app.workers.tasks.training_tasks",      # OCR Training
        "app.workers.tasks.extraction_tasks",    # Strukturierte Extraktion
        "app.workers.tasks.rag_tasks",           # RAG-Verarbeitung
        "app.workers.tasks.monitoring_tasks",    # Health Monitoring
        "app.workers.tasks.export_tasks",        # Export-Jobs
    ]
)
```

### Worker-Konfiguration

```python
celery_app.conf.update(
    # Serialisierung
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Task-Ausführung
    task_track_started=True,
    task_time_limit=600,              # 10 Minuten Hard Limit
    task_soft_time_limit=570,         # 9.5 Minuten Soft Limit
    task_acks_late=True,              # ACK nach Verarbeitung

    # Worker-Einstellungen
    worker_prefetch_multiplier=1,     # Kritisch für GPU
    worker_max_tasks_per_child=10,    # Memory-Management
    worker_pool="solo",               # GPU-Isolation

    # Result Backend
    result_expires=86400,             # 24h TTL
    result_compression="gzip",

    # Priority Queue
    broker_transport_options={
        "priority_steps": list(range(10)),
        "queue_order_strategy": "priority",
        "visibility_timeout": 43200,  # 12h für lange OCR-Tasks
    },
)
```

### Task-Klassen

#### GPUTask Base Class

```python
class GPUTask(Task):
    """Basis-Klasse für GPU-intensive Tasks.

    Features:
    - Distributed GPU-Lock via Redis
    - Automatischer Lock-Refresh für lange Tasks
    - GPU-Speicher-Cleanup nach Ausführung
    - OOM-Detection und Recovery
    """
    abstract = True

    # Retry-Konfiguration
    autoretry_for = (torch.cuda.OutOfMemoryError, RuntimeError)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True

    # Queue-Routing
    queue = "ocr_normal"
    priority = 5

    _lock_value: Optional[str] = None

    def before_start(self, task_id, args, kwargs):
        """GPU-Lock vor Task-Start erwerben."""
        self._lock_value = acquire_gpu_lock(timeout=30)
        set_gpu_lock_status(True)

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """GPU-Lock nach Task freigeben."""
        if self._lock_value:
            release_gpu_lock(self._lock_value)
            set_gpu_lock_status(False)
            self._lock_value = None

        # GPU-Speicher aufräumen
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def refresh_lock(self) -> bool:
        """Lock-TTL für lange Tasks refreshen."""
        if self._lock_value:
            return refresh_gpu_lock(self._lock_value, extend_seconds=60)
        return False
```

#### CPUTask Base Class

```python
class CPUTask(Task):
    """Basis-Klasse für CPU-bound Tasks.

    Features:
    - Keine GPU-Abhängigkeit
    - Parallele Ausführung möglich
    - Standard-Retry-Logik
    """
    abstract = True

    autoretry_for = (Exception,)
    max_retries = 3
    retry_backoff = True
    retry_backoff_max = 60

    queue = "validation"
    priority = 5
```

---

## Task-Kategorien

### OCR Tasks

| Task | Beschreibung | Base | Queue | Priority |
|------|--------------|------|-------|----------|
| `process_document_task` | Einzeldokument OCR | GPUTask | ocr_normal | 5 |
| `batch_process_task` | Batch OCR (max 500 Docs) | GPUTask | ocr_normal | 6 |
| `process_document_workflow` | Full Processing Pipeline | GPUTask | ocr_high | 2 |

**process_document_task** - Haupttask für OCR:

```python
@celery_app.task(
    bind=True,
    base=GPUTask,
    name="app.workers.tasks.ocr_tasks.process_document_task"
)
def process_document_task(
    self,
    document_id: str,
    backend: str = "auto",        # auto, deepseek, got_ocr, surya, surya_gpu
    language: str = "de",         # de, en
    detect_layout: bool = True,
    detect_fraktur: bool = False,
    priority: str = "normal"
) -> Dict[str, Any]:
    """
    Verarbeitet ein Dokument mit OCR.

    Workflow:
    1. Dokument von MinIO laden
    2. OCR mit gewähltem Backend
    3. Deutsche Textvalidierung
    4. Speichern in DB
    5. Embedding-Task queuen
    6. RAG-Chunking-Task queuen
    7. Extraktion-Task queuen

    Returns:
        {
            "success": True,
            "document_id": "...",
            "text": "Extrahierter Text...",
            "confidence": 0.95,
            "backend_used": "deepseek",
            "processing_time_ms": 2345,
            "embedding_task_id": "...",
            "rag_chunking_task_id": "..."
        }
    """
```

### Embedding Tasks

| Task | Beschreibung | Base | Queue | Priority |
|------|--------------|------|-------|----------|
| `generate_document_embedding` | Einzeldokument Embedding | GPUTask | embedding_normal | 7 |
| `batch_generate_embeddings` | Batch Embedding | GPUTask | embedding_normal | 8 |
| `update_embeddings_for_model` | Model-Update Migration | GPUTask | embedding_high | 4 |

### Backup Tasks

| Task | Beschreibung | Base | Queue | Priority |
|------|--------------|------|-------|----------|
| `backup_full_task` | Vollständiges Backup | CPUTask | backup | 9 |
| `backup_postgres_task` | PostgreSQL Backup | CPUTask | backup | 9 |
| `backup_redis_task` | Redis Backup | CPUTask | backup | 9 |
| `apply_retention_task` | Retention Policy | CPUTask | maintenance | 9 |

### GDPR Tasks

| Task | Beschreibung | Base | Queue | Priority |
|------|--------------|------|-------|----------|
| `process_deletion_request` | Art. 17 Löschung | CPUTask | validation | 3 |
| `export_user_data` | Art. 20 Datenportabilität | CPUTask | validation | 5 |
| `anonymize_user_data` | Anonymisierung | CPUTask | validation | 4 |

### Maintenance Tasks

| Task | Beschreibung | Base | Queue | Priority |
|------|--------------|------|-------|----------|
| `cleanup_task` | Alte Ergebnisse löschen | CPUTask | maintenance | 9 |
| `update_system_metrics` | Metriken sammeln | CPUTask | metrics | 8 |
| `health_check_workers` | Worker Health Check | CPUTask | metrics | 1 |

---

## GPU Task Management

### Distributed GPU Lock

Das System verwendet Redis für verteiltes GPU-Locking, um Race Conditions bei GPU-Zugriffen zu verhindern.

```
┌─────────────────────────────────────────────────────────────┐
│                    GPU Lock Lifecycle                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐            │
│  │  ACQUIRE │────▶│   HELD   │────▶│ RELEASE  │            │
│  └──────────┘     └──────────┘     └──────────┘            │
│       │                │                 │                   │
│       ▼                ▼                 ▼                   │
│  SET NX + EX      REFRESH TTL       DEL (atomic)            │
│  (30s timeout)    (alle 25s)        (WATCH/MULTI)           │
│                                                              │
│  Lock Key: "ablage:gpu:lock"                                │
│  Default TTL: 60 Sekunden                                   │
│  Refresh Interval: 25 Sekunden                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Lock-Funktionen

```python
# Lock erwerben (blockierend, max 30s warten)
lock_value = acquire_gpu_lock(timeout=30)

# Lock refreshen für lange Tasks (> 60s)
success = refresh_gpu_lock(lock_value, extend_seconds=60)

# Lock freigeben (atomisch)
released = release_gpu_lock(lock_value)

# Lock-Status prüfen
status = check_gpu_lock_health()
# Returns: {"locked": True, "owner": "worker:1234:...", "ttl_seconds": 45}
```

### Background Lock Refresh

Für OCR-Tasks, die länger als 60 Sekunden dauern, wird ein Background-Task für periodisches Lock-Refresh gestartet:

```python
async def _periodic_lock_refresh(
    task: GPUTask,
    interval: int = 25  # Sekunden
) -> None:
    """Background-Task für periodisches GPU-Lock-Refresh."""
    while True:
        await asyncio.sleep(interval)
        refreshed = await loop.run_in_executor(None, task.refresh_lock)
        if not refreshed:
            logger.warning("gpu_lock_refresh_failed")
```

### GPU Memory Management

```python
@contextmanager
def gpu_memory_guard(threshold_gb: float = 13.6):
    """Context Manager für GPU-Speicher-Überwachung.

    Args:
        threshold_gb: Maximaler VRAM-Verbrauch (85% von 16GB)
    """
    try:
        yield
    finally:
        if torch.cuda.is_available():
            current_memory = torch.cuda.memory_allocated() / 1024**3
            if current_memory > threshold_gb:
                logger.warning("gpu_memory_high", current_gb=current_memory)
                torch.cuda.empty_cache()
```

### OOM Detection & Recovery

```python
def _is_oom_error(exception: Exception) -> bool:
    """Erkennt GPU Out-of-Memory Fehler."""
    if isinstance(exception, torch.cuda.OutOfMemoryError):
        return True

    oom_indicators = [
        "out of memory",
        "cuda out of memory",
        "oom",
        "memory allocation",
        "cannot allocate",
    ]
    return any(ind in str(exception).lower() for ind in oom_indicators)
```

### CPU Fallback bei GPU-Timeout

```python
except SoftTimeLimitExceeded:
    # GPU-Timeout: Fallback zu CPU-Backend
    if actual_backend in ["deepseek", "got_ocr", "surya_gpu"]:
        ocr_result = await ocr_service.process_document(
            image_path=local_file_path,
            backend="surya",  # CPU-Backend
            language=language
        )
        document.ocr_backend_used = "surya_cpu_fallback"
```

---

## Queue-Konfiguration

### Priority-Stufen

| Priority | Verwendung | Beispiel-Tasks |
|----------|------------|----------------|
| 0-2 | **Kritisch** | Fehler-Recovery, Health Checks |
| 3-4 | **Hoch** | DSGVO-Löschungen, Workflow-Pipeline |
| 5-6 | **Normal** | Standard OCR, Embeddings |
| 7-8 | **Niedrig** | Batch-Jobs, Metriken |
| 9 | **Background** | Backups, Cleanup |

### Queue-Definitionen

```python
task_queues = {
    # GPU Tasks - Hohe Priorität
    "ocr_high": {
        "exchange": "ocr_high",
        "routing_key": "ocr.high",
        "queue_arguments": {
            "x-max-priority": 10,
            "x-dead-letter-exchange": "dlq",
            "x-dead-letter-routing-key": "dlq",
        },
    },

    # GPU Tasks - Normale Priorität
    "ocr_normal": {
        "exchange": "ocr_normal",
        "routing_key": "ocr.normal",
        "queue_arguments": {
            "x-max-priority": 10,
            "x-dead-letter-exchange": "dlq",
        },
    },

    # Embedding Tasks
    "embedding_high": {...},
    "embedding_normal": {...},

    # CPU Tasks
    "validation": {...},
    "metadata": {...},
    "backup": {...},
    "maintenance": {...},
    "metrics": {...},

    # Dead Letter Queue
    "dlq": {
        "exchange": "dlq",
        "routing_key": "dlq",
        "queue_arguments": {
            "x-max-priority": 10,
            "x-message-ttl": 604800000,  # 7 Tage
        },
    },
}
```

### Task Routing

```python
task_routes = {
    # OCR Tasks
    "app.workers.tasks.ocr_tasks.process_document_task": {
        "queue": "ocr_normal",
        "priority": 5,
    },
    "app.workers.tasks.ocr_tasks.batch_process_task": {
        "queue": "ocr_normal",
        "priority": 6,
    },
    "app.workers.tasks.ocr_tasks.process_document_workflow": {
        "queue": "ocr_high",
        "priority": 2,
    },

    # Embedding Tasks
    "app.workers.tasks.embedding_tasks.*": {
        "queue": "embedding_normal",
        "priority": 7,
    },

    # Backup Tasks
    "app.workers.tasks.backup_tasks.*": {
        "queue": "backup",
        "priority": 9,
    },
}
```

### Worker-Start mit Queues

```bash
# GPU Worker - alle GPU-Queues
celery -A app.workers.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --pool=solo \
    -Q ocr_high,ocr_normal,embedding_high,embedding_normal

# CPU Worker - alle CPU-Queues
celery -A app.workers.celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --pool=prefork \
    -Q validation,metadata,backup,maintenance,metrics,dlq
```

---

## Dead Letter Queue (DLQ)

### Konzept

Fehlgeschlagene Tasks werden automatisch in die DLQ verschoben, anstatt gelöscht zu werden. Dies ermöglicht:

- **Inspektion**: Fehlermeldungen und Stack Traces analysieren
- **Retry**: Tasks mit korrigierten Parametern erneut ausführen
- **Monitoring**: Fehlertrends erkennen

```
┌─────────────────────────────────────────────────────────────┐
│                    Dead Letter Queue Flow                    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Task Failure                                                │
│       │                                                      │
│       ▼                                                      │
│  ┌──────────────┐     ┌──────────────┐                      │
│  │ Max Retries  │────▶│     DLQ      │                      │
│  │  Exceeded    │     │  (7 Tage)    │                      │
│  └──────────────┘     └──────────────┘                      │
│                              │                               │
│                              ▼                               │
│                    ┌─────────────────────┐                  │
│                    │   Admin Dashboard   │                  │
│                    │   - Inspect         │                  │
│                    │   - Retry           │                  │
│                    │   - Delete          │                  │
│                    └─────────────────────┘                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### DLQ Management Tasks

```python
@celery_app.task(bind=True, base=CPUTask)
def process_dlq_batch(
    self,
    max_items: int = 100,
    retry_strategy: str = "exponential"
) -> Dict[str, Any]:
    """Verarbeitet DLQ-Einträge in Batches."""

@celery_app.task(bind=True, base=CPUTask)
def analyze_dlq_patterns(self) -> Dict[str, Any]:
    """Analysiert Fehlermuster in der DLQ."""

@celery_app.task(bind=True, base=CPUTask)
def cleanup_old_dlq_entries(
    self,
    older_than_days: int = 7
) -> Dict[str, Any]:
    """Löscht alte DLQ-Einträge."""
```

### DLQ API Endpoints

```http
# DLQ-Status abrufen
GET /api/v1/tasks/dlq/status

# DLQ-Einträge auflisten
GET /api/v1/tasks/dlq?limit=50&offset=0

# Einzelnen Eintrag inspizieren
GET /api/v1/tasks/dlq/{task_id}

# Task erneut ausführen
POST /api/v1/tasks/dlq/{task_id}/retry

# Eintrag löschen
DELETE /api/v1/tasks/dlq/{task_id}

# Batch-Retry
POST /api/v1/tasks/dlq/batch-retry
{
    "task_ids": ["...", "..."],
    "retry_options": {"priority": 2}
}
```

---

## Beat Scheduler

### Scheduled Tasks

```python
celery_app.conf.beat_schedule = {
    # =================================================================
    # BACKUP TASKS - Täglich
    # =================================================================
    "backup-full-daily": {
        "task": "app.workers.tasks.backup_tasks.backup_full_task",
        "schedule": crontab(hour=2, minute=30),  # 02:30 UTC
        "options": {"queue": "backup", "priority": 9},
    },

    "backup-retention-weekly": {
        "task": "app.workers.tasks.backup_tasks.apply_retention_task",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        "options": {"queue": "maintenance", "priority": 9},
    },

    "backup-sync-remote-daily": {
        "task": "app.workers.tasks.backup_tasks.sync_to_remote_task",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "backup", "priority": 9},
    },

    # =================================================================
    # CLEANUP TASKS
    # =================================================================
    "cleanup-old-results": {
        "task": "app.workers.tasks.cleanup_tasks.cleanup_task",
        "schedule": crontab(hour=3, minute=30),
        "args": [24],  # 24 Stunden alt
        "options": {"queue": "maintenance", "priority": 9},
    },

    # =================================================================
    # MONITORING TASKS
    # =================================================================
    "update-system-metrics": {
        "task": "app.workers.tasks.ocr_tasks.update_system_metrics",
        "schedule": timedelta(minutes=5),
        "options": {"queue": "metrics", "priority": 8},
    },

    "worker-health-check": {
        "task": "app.workers.tasks.monitoring_tasks.health_check_workers",
        "schedule": timedelta(minutes=2),
        "options": {"queue": "metrics", "priority": 1},
    },

    # =================================================================
    # TRAINING TASKS - Wöchentlich
    # =================================================================
    "training-generate-daily-stats": {
        "task": "app.workers.tasks.training_tasks.generate_daily_stats",
        "schedule": crontab(hour=1, minute=0),
        "options": {"queue": "maintenance", "priority": 8},
    },

    "training-process-feedback": {
        "task": "app.workers.tasks.training_tasks.process_feedback_queue",
        "schedule": crontab(minute=0),  # Stündlich
        "options": {"queue": "maintenance", "priority": 7},
    },

    "training-update-weights": {
        "task": "app.workers.tasks.training_tasks.update_learned_weights",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "maintenance", "priority": 8},
    },

    "training-run-benchmarks": {
        "task": "app.workers.tasks.training_tasks.run_scheduled_benchmarks",
        "schedule": crontab(hour=3, minute=0, day_of_week="sunday"),
        "options": {"queue": "ocr_normal", "priority": 7},
    },

    # =================================================================
    # DLQ MANAGEMENT
    # =================================================================
    "dlq-analyze-patterns": {
        "task": "app.workers.tasks.dlq_management_tasks.analyze_dlq_patterns",
        "schedule": crontab(hour=6, minute=0),
        "options": {"queue": "maintenance", "priority": 8},
    },

    "dlq-cleanup-old": {
        "task": "app.workers.tasks.dlq_management_tasks.cleanup_old_dlq_entries",
        "schedule": crontab(hour=4, minute=30),
        "args": [7],  # 7 Tage
        "options": {"queue": "maintenance", "priority": 9},
    },
}
```

### Beat Scheduler starten

```bash
# Beat Scheduler (separater Prozess)
celery -A app.workers.celery_app beat \
    --loglevel=info \
    --scheduler=celery.beat:PersistentScheduler \
    --pidfile=/var/run/celery/beat.pid
```

### Schedule-Übersicht

| Task | Zeitplan | Queue | Priorität |
|------|----------|-------|-----------|
| Vollständiges Backup | 02:30 UTC täglich | backup | 9 |
| Retention Policy | Sonntag 03:00 | maintenance | 9 |
| Remote Sync | 04:00 UTC täglich | backup | 9 |
| Cleanup alte Ergebnisse | 03:30 UTC täglich | maintenance | 9 |
| System-Metriken | Alle 5 Minuten | metrics | 8 |
| Worker Health Check | Alle 2 Minuten | metrics | 1 |
| Training Stats | 01:00 UTC täglich | maintenance | 8 |
| Feedback Processing | Stündlich | maintenance | 7 |
| Benchmark-Läufe | Sonntag 03:00 | ocr_normal | 7 |
| DLQ-Analyse | 06:00 UTC täglich | maintenance | 8 |
| DLQ-Cleanup | 04:30 UTC täglich | maintenance | 9 |

---

## Monitoring & Metriken

### Prometheus Metriken

Der Celery Worker exponiert Metriken auf Port 8001:

```
┌─────────────────────────────────────────────────────────────┐
│                    Prometheus Metriken                       │
│                    http://worker:8001/metrics                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  TASK METRIKEN                                              │
│  ─────────────                                              │
│  ablage_celery_tasks_total{task, queue, status}             │
│  ablage_celery_task_duration_seconds{task, queue}           │
│  ablage_celery_tasks_active{task, queue}                    │
│  ablage_celery_task_retries_total{task, queue}              │
│  ablage_celery_task_exceptions_total{task, type}            │
│                                                              │
│  GPU METRIKEN                                               │
│  ────────────                                               │
│  ablage_celery_gpu_memory_bytes{type=allocated|reserved}    │
│  ablage_celery_gpu_utilization_percent                      │
│  ablage_celery_gpu_oom_events_total{task}                   │
│  ablage_celery_gpu_lock_wait_seconds{task}                  │
│  ablage_celery_gpu_lock_held                                │
│                                                              │
│  WORKER METRIKEN                                            │
│  ───────────────                                            │
│  ablage_celery_worker_up                                    │
│  ablage_celery_worker_uptime_seconds                        │
│  ablage_celery_worker_tasks_processed_total                 │
│  ablage_celery_worker_pool_size                             │
│                                                              │
│  QUEUE METRIKEN                                             │
│  ──────────────                                             │
│  ablage_celery_queue_length{queue_name}                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Metriken-Sammlung

```python
# Task-Start aufzeichnen
record_task_started(task_id, task_name, queue)

# Task-Erfolg aufzeichnen
record_task_succeeded(task_id, task_name, queue)

# Task-Fehler aufzeichnen
record_task_failed(task_id, task_name, queue, exception_type)

# GPU-OOM aufzeichnen
record_gpu_oom(task_name)

# GPU-Lock-Wartezeit aufzeichnen
record_gpu_lock_wait(task_name, wait_time)
```

### Grafana Dashboard

Ein vorkonfiguriertes Dashboard ist verfügbar unter:
`http://localhost:3002/d/celery-monitoring`

**Panels:**
- Task Success Rate (%)
- Task Duration Histogram
- Active Tasks by Queue
- GPU Memory Usage
- GPU Lock Wait Time
- Queue Lengths
- DLQ Size
- Worker Uptime

### Alerting Rules

```yaml
# prometheus/alerts/celery_alerts.yml
groups:
  - name: celery_alerts
    rules:
      - alert: CeleryWorkerDown
        expr: ablage_celery_worker_up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Celery Worker ist nicht erreichbar"

      - alert: HighGPUMemoryUsage
        expr: ablage_celery_gpu_utilization_percent > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "GPU-Speicherauslastung über 85%"

      - alert: TaskQueueBacklog
        expr: ablage_celery_queue_length{queue_name="ocr_normal"} > 100
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "OCR-Queue hat > 100 wartende Tasks"

      - alert: HighTaskFailureRate
        expr: |
          rate(ablage_celery_tasks_total{status="failed"}[5m])
          / rate(ablage_celery_tasks_total{status="started"}[5m])
          > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Task-Fehlerrate über 10%"

      - alert: DLQGrowing
        expr: ablage_celery_queue_length{queue_name="dlq"} > 50
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Dead Letter Queue wächst (> 50 Einträge)"
```

---

## Error Handling & Retry-Strategien

### Retry-Konfiguration

```python
@celery_app.task(
    bind=True,
    base=GPUTask,
    autoretry_for=(
        torch.cuda.OutOfMemoryError,
        ConnectionError,
        TimeoutError,
    ),
    retry_backoff=True,           # Exponential Backoff
    retry_backoff_max=300,        # Max 5 Minuten
    retry_jitter=True,            # Zufällige Verzögerung
    max_retries=3,
    default_retry_delay=60,       # 1 Minute initial
)
def process_document_task(self, document_id: str, ...):
    ...
```

### Exponential Backoff

```
Retry 1: 60s (default_retry_delay)
Retry 2: 120s (60s * 2^1)
Retry 3: 240s (60s * 2^2)
Max:     300s (retry_backoff_max)

Mit Jitter: ±50% zufällige Variation
```

### Fehlertypen und Handling

```python
try:
    result = await ocr_service.process_document(...)

except SoftTimeLimitExceeded:
    # Timeout - CPU-Fallback versuchen
    logger.warning("gpu_timeout", document_id=document_id)
    result = await fallback_cpu_processing(...)

except torch.cuda.OutOfMemoryError as e:
    # GPU OOM - Speicher aufräumen, retry mit kleinerer Batch
    record_gpu_oom(self.name)
    torch.cuda.empty_cache()
    raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

except GPUNotAvailableError:
    # GPU nicht verfügbar - sofort zu CPU wechseln
    result = await cpu_ocr_processing(...)

except OCRProcessingError as e:
    # OCR-spezifischer Fehler - in DLQ verschieben
    await update_document_status(session, doc_uuid, ProcessingStatus.FAILED)
    raise  # Wird von DLQ abgefangen
```

### Custom Exception Handling

```python
from app.core.exceptions import (
    GPUOutOfMemoryError,
    GPUNotAvailableError,
    OCRProcessingError,
    OCRBackendTimeoutError,
)

@celery_app.task(bind=True, base=GPUTask)
def process_document_task(self, document_id: str, ...):
    try:
        ...
    except Exception as e:
        # GPU OOM spezifisch behandeln
        if _is_oom_error(e):
            gpu_manager = get_worker_gpu_recovery_manager()
            await gpu_manager.clear_gpu_memory()

            if self.request.retries < self.max_retries:
                countdown = 60 * (2 ** self.request.retries)
                raise self.retry(exc=e, countdown=countdown)
            else:
                raise GPUOutOfMemoryError(
                    message=f"GPU OOM nach {self.max_retries} Versuchen",
                    required_gb=14.0,
                    available_gb=2.0
                )

        # Andere Fehler normal behandeln
        raise OCRProcessingError(
            document_id=document_id,
            backend=backend,
            reason=str(e)
        )
```

---

## Best Practices

### 1. Task-Design

```python
# ✅ RICHTIG: Idempotente Tasks
@celery_app.task(bind=True)
def process_document(self, document_id: str):
    """Task kann ohne Seiteneffekte mehrfach ausgeführt werden."""
    existing = await get_result(document_id)
    if existing and not force_regenerate:
        return existing  # Skip wenn bereits verarbeitet

# ❌ FALSCH: Nicht-idempotente Tasks
@celery_app.task
def increment_counter():
    """Jede Ausführung ändert den Zustand."""
    counter.increment()
```

### 2. Async in Celery

```python
# ✅ RICHTIG: asyncio.run() für async Code
def process_document_task(self, document_id: str):
    async def process_async():
        async with get_async_session_context() as session:
            ...

    return asyncio.run(process_async())

# ❌ FALSCH: Event Loop manuell erstellen
def process_document_task(self, document_id: str):
    loop = asyncio.new_event_loop()  # Memory Leak!
    try:
        return loop.run_until_complete(process_async())
    finally:
        loop.close()
```

### 3. GPU-Ressourcen

```python
# ✅ RICHTIG: GPU-Speicher am Ende aufräumen
finally:
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

# ✅ RICHTIG: Kleine Batches bei OOM
batch_size = 4
if memory_usage > 80:
    batch_size = max(1, batch_size // 2)
```

### 4. Fehlerbehandlung

```python
# ✅ RICHTIG: Spezifische Exception-Typen
autoretry_for = (
    torch.cuda.OutOfMemoryError,
    ConnectionError,
    TimeoutError,
)

# ❌ FALSCH: Alle Exceptions abfangen
autoretry_for = (Exception,)  # Auch permanente Fehler werden geretried
```

### 5. Logging

```python
# ✅ RICHTIG: Strukturiertes Logging
logger.info(
    "ocr_task_completed",
    task_id=task_id,
    document_id=document_id,
    backend=backend,
    duration_ms=processing_ms,
    confidence=0.95
)

# ❌ FALSCH: String-Interpolation
logger.info(f"Task {task_id} completed for doc {document_id}")
```

### 6. Batch-Größen

```python
# ✅ RICHTIG: Batch-Größe begrenzen
MAX_BATCH_SIZE = 500
if len(document_ids) > MAX_BATCH_SIZE:
    raise ValueError(f"Batch zu groß: max {MAX_BATCH_SIZE}")

# ✅ RICHTIG: Memory-effiziente Batch-Verarbeitung
for idx, doc_id in enumerate(document_ids):
    process_single(doc_id)
    if idx % 10 == 0:
        torch.cuda.empty_cache()  # Periodisch aufräumen
```

---

## Troubleshooting

### Problem: GPU Lock Deadlock

**Symptome:**
- Tasks hängen bei "Warte auf GPU-Lock"
- `check_gpu_lock_health()` zeigt alten Owner

**Lösung:**
```bash
# Lock manuell freigeben
redis-cli DEL ablage:gpu:lock

# Oder via API
curl -X POST http://localhost:8000/api/v1/gpu/force-release-lock
```

### Problem: Tasks verschwinden

**Symptome:**
- Tasks starten, aber kein Ergebnis
- `celery inspect active` zeigt keine aktiven Tasks

**Ursachen & Lösungen:**
```bash
# 1. Worker-Pool-Probleme
# Lösung: pool=solo für GPU-Tasks
celery -A app.workers.celery_app worker --pool=solo

# 2. Visibility Timeout zu kurz
# Lösung: In celery_app.conf
broker_transport_options = {
    "visibility_timeout": 43200,  # 12 Stunden
}

# 3. Worker stirbt während Verarbeitung
# Lösung: task_acks_late = True
```

### Problem: High Memory Usage

**Symptome:**
- Worker-Speicher wächst kontinuierlich
- GPU-Speicher wird nicht freigegeben

**Lösungen:**
```python
# 1. Worker nach N Tasks neustarten
worker_max_tasks_per_child = 10

# 2. GPU-Speicher nach jedem Task leeren
def after_return(self, ...):
    torch.cuda.empty_cache()

# 3. asyncio.run() statt manueller Loop
return asyncio.run(process_async())  # ✅
```

### Problem: DLQ wächst

**Symptome:**
- DLQ hat viele Einträge
- Ähnliche Fehlermuster

**Analyse:**
```bash
# DLQ-Inhalt inspizieren
curl http://localhost:8000/api/v1/tasks/dlq?limit=10

# Muster analysieren
curl http://localhost:8000/api/v1/tasks/dlq/analyze
```

**Lösung:**
```python
# Häufige Ursache: Falsche Dateipfade
# → Dokument existiert nicht mehr in MinIO

# Batch-Retry mit korrigierten Parametern
POST /api/v1/tasks/dlq/batch-retry
{
    "filter": {"error_type": "FileNotFoundError"},
    "action": "delete"  # Oder "retry" mit neuen Parametern
}
```

### Problem: Slow Task Performance

**Diagnose:**
```bash
# Task-Dauer analysieren
curl http://worker:8001/metrics | grep duration

# GPU-Auslastung prüfen
nvidia-smi

# Queue-Längen prüfen
curl http://worker:8001/metrics | grep queue_length
```

**Optimierungen:**
1. **Batch-Größe anpassen**: Größere Batches = höherer Durchsatz
2. **GPU-Lock optimieren**: Lock-Refresh-Intervall verkürzen
3. **Queue-Prioritäten**: Kritische Tasks höher priorisieren
4. **Worker skalieren**: Mehr CPU-Worker für Nebenaufgaben

### Useful Commands

```bash
# Worker-Status
celery -A app.workers.celery_app inspect active
celery -A app.workers.celery_app inspect reserved
celery -A app.workers.celery_app inspect scheduled

# Queue-Längen
celery -A app.workers.celery_app inspect active_queues

# Task widerrufen
celery -A app.workers.celery_app control revoke <task_id>

# Worker herunterfahren
celery -A app.workers.celery_app control shutdown

# Beat-Status
celery -A app.workers.celery_app beat --detach --loglevel=info
```

---

## Anhang: Task-Register

### Vollständige Task-Liste

| Task-Name | Modul | Base | Queue |
|-----------|-------|------|-------|
| `process_document_task` | ocr_tasks | GPUTask | ocr_normal |
| `batch_process_task` | ocr_tasks | GPUTask | ocr_normal |
| `process_document_workflow` | ocr_tasks | GPUTask | ocr_high |
| `validate_german_text_task` | ocr_tasks | CPUTask | validation |
| `extract_metadata_task` | ocr_tasks | CPUTask | metadata |
| `cleanup_task` | ocr_tasks | CPUTask | maintenance |
| `update_system_metrics` | ocr_tasks | CPUTask | metrics |
| `generate_document_embedding` | embedding_tasks | GPUTask | embedding_normal |
| `batch_generate_embeddings` | embedding_tasks | GPUTask | embedding_normal |
| `backup_full_task` | backup_tasks | CPUTask | backup |
| `backup_postgres_task` | backup_tasks | CPUTask | backup |
| `backup_redis_task` | backup_tasks | CPUTask | backup |
| `apply_retention_task` | backup_tasks | CPUTask | maintenance |
| `process_deletion_request` | gdpr_tasks | CPUTask | validation |
| `export_user_data` | gdpr_tasks | CPUTask | validation |
| `chunk_document` | rag_tasks | CPUTask | metadata |
| `process_dlq_batch` | dlq_management_tasks | CPUTask | dlq |
| `analyze_dlq_patterns` | dlq_management_tasks | CPUTask | maintenance |

---

*Dokumentation erstellt am 2026-01-09*
*Version: 1.0*
*Ablage-System - Feinpoliert und durchdacht*
