# Celery Async OCR Tasks - Implementation Summary

## Overview

Comprehensive Celery-based async task processing system for the Ablage System OCR platform. Provides GPU-aware background processing with real-time progress updates, automatic retries, and WebSocket support.

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   FastAPI App   │────▶│ Redis Broker │────▶│ Celery Workers  │
│   (main.py)     │     │  (Queue)     │     │  (GPU-managed)  │
└─────────────────┘     └──────────────┘     └─────────────────┘
        │                                              │
        │                                              ▼
        │                                    ┌─────────────────┐
        │                                    │  OCR Backends   │
        │                                    │  - DeepSeek     │
        │                                    │  - GOT-OCR      │
        │                                    │  - Surya        │
        │                                    └─────────────────┘
        │                                              │
        ▼                                              ▼
┌─────────────────┐                          ┌─────────────────┐
│   PostgreSQL    │◀─────────────────────────│   Results DB    │
│   (State)       │                          │   (OCR Data)    │
└─────────────────┘                          └─────────────────┘
```

## Implemented Components

### 1. Celery App Configuration (`app/workers/celery_app.py`)

**Features:**
- Redis broker and result backend
- GPU-aware task routing (only 1 GPU task at a time)
- Priority queues (high: 9, normal: 5, low: 1)
- Automatic retry with exponential backoff
- Task events for monitoring
- GPU memory management with threading lock

**Key Classes:**
- `GPUTask`: Base class for GPU tasks with automatic memory cleanup
- `CPUTask`: Base class for CPU-only tasks
- `gpu_memory_guard()`: Context manager for GPU memory monitoring

**Configuration:**
```python
worker_pool="solo"  # Single process for GPU isolation
worker_prefetch_multiplier=1  # One task at a time
task_acks_late=True  # Acknowledge after completion
task_time_limit=300  # 5 minutes max
```

### 2. OCR Tasks (`app/workers/tasks/ocr_tasks.py`)

**Implemented Tasks:**

#### `process_document_task` (GPU Task)
Main OCR processing task with:
- Document loading from database
- OCR processing with backend selection
- German text validation
- Progress updates (German messages)
- Result storage in database
- Automatic GPU fallback on OOM

**Progress Steps:**
1. 0%: "Dokument wird geladen..."
2. 20%: "OCR-Verarbeitung läuft..."
3. 70%: "Deutsche Textvalidierung..."
4. 90%: "Speichere Ergebnisse..."
5. 100%: "Verarbeitung abgeschlossen!"

#### `batch_process_task` (GPU Task)
Batch document processing:
- Sequential processing (GPU tasks)
- Per-document progress tracking
- Aggregated success/failure statistics

#### `validate_german_text_task` (CPU Task)
Standalone German text validation:
- Umlaut detection
- Date/amount extraction
- Business term recognition
- OCR error detection
- Quality scoring

#### `extract_metadata_task` (CPU Task)
Metadata extraction from processed documents:
- Dates, amounts, IBANs, VAT IDs
- Business term extraction
- Database metadata updates

#### `cleanup_task` (CPU Task)
Automated cleanup (runs hourly):
- Delete old processing jobs
- Delete old system metrics
- Clean up temporary files

#### `update_system_metrics` (CPU Task)
System monitoring (runs every 5 minutes):
- CPU and memory usage
- Disk usage
- GPU memory (if available)
- Stores metrics in database

### 3. Task Callbacks (`app/workers/task_callbacks.py`)

**Callback Functions:**

#### `on_success()`
- Updates document status to COMPLETED
- Updates processing job with results
- Logs success metrics

#### `on_failure()`
- Updates document status to FAILED
- Logs error details
- Can send notifications (TODO)

#### `on_retry()`
- Increments retry counter
- Logs retry attempts
- Updates job error message

**Helper Classes:**

#### `ProgressCallback`
Real-time progress tracking:
```python
progress = ProgressCallback(task, total_steps=100)
progress.update(25, "Verarbeite Seite 1...")
progress.complete("Fertig!")
```

### 4. Task Service (`app/services/task_service.py`)

**High-level API for task management:**

```python
task_service = TaskService()

# Submit OCR task
result = await task_service.submit_document_task(
    session=db_session,
    document_id=doc_id,
    backend="auto",
    language="de",
    priority="high"
)

# Check status
status = task_service.get_task_status(task_id)

# Cancel task
task_service.cancel_task(task_id)

# Get user's tasks
tasks = await task_service.get_user_tasks(session, user_id)
```

### 5. REST API (`app/api/v1/tasks.py`)

**Endpoints:**

#### `GET /api/v1/tasks/{task_id}`
Get task status with progress

**Response:**
```json
{
  "task_id": "abc-123",
  "state": "PROGRESS",
  "progress": 45,
  "current": 45,
  "total": 100,
  "message": "OCR-Verarbeitung läuft...",
  "ready": false
}
```

#### `DELETE /api/v1/tasks/{task_id}`
Cancel running task

**Response:**
```json
{
  "task_id": "abc-123",
  "cancelled": true,
  "message": "Aufgabe wurde abgebrochen"
}
```

#### `GET /api/v1/tasks/`
List user's recent tasks

**Query Parameters:**
- `limit`: Max tasks to return (1-100, default: 10)

**Response:**
```json
{
  "user_id": "user-uuid",
  "tasks": [
    {
      "job_id": "job-uuid",
      "document_id": "doc-uuid",
      "task_id": "celery-task-id",
      "status": "processing",
      "priority": 5,
      "celery_state": "PROGRESS",
      "progress": 67
    }
  ],
  "total": 3
}
```

#### `GET /api/v1/tasks/{task_id}/result`
Get task result (blocks with timeout)

**Query Parameters:**
- `timeout`: Seconds to wait (1-300)

#### `WS /api/v1/tasks/ws/{task_id}`
WebSocket for real-time updates

**Message Format:**
```json
{
  "task_id": "abc-123",
  "state": "PROGRESS",
  "progress": 75,
  "message": "Deutsche Textvalidierung...",
  "current": 75,
  "total": 100
}
```

**Final Message (Success):**
```json
{
  "task_id": "abc-123",
  "state": "SUCCESS",
  "message": "Verarbeitung erfolgreich abgeschlossen!",
  "result": {
    "success": true,
    "text": "Extracted text...",
    "confidence": 0.95
  }
}
```

## Usage Examples

### 1. Start Celery Worker

```bash
# Start worker with GPU support
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=1 \
  --pool=solo \
  --queues=ocr_high,ocr_normal,validation,metadata,maintenance,metrics

# Start Celery Beat (for periodic tasks)
celery -A app.workers.celery_app beat --loglevel=info

# Start Flower (monitoring UI)
celery -A app.workers.celery_app flower --port=5555
```

### 2. Submit Task via API

```python
import httpx

# Submit OCR task
response = await client.post(
    "/api/v1/documents/upload",
    files={"file": open("document.pdf", "rb")},
    data={
        "backend": "auto",
        "language": "de",
        "priority": "high"
    }
)

task_id = response.json()["task_id"]

# Monitor progress
status = await client.get(f"/api/v1/tasks/{task_id}")
print(status.json())
```

### 3. WebSocket Client (JavaScript)

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/v1/tasks/ws/${taskId}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress}% - ${data.message}`);

  if (data.state === 'SUCCESS') {
    console.log('Result:', data.result);
    ws.close();
  }
};
```

### 4. Direct Task Submission (Internal)

```python
from app.workers.tasks.ocr_tasks import process_document_task

# Submit task
task = process_document_task.apply_async(
    args=[str(document_id)],
    kwargs={
        "backend": "deepseek",
        "language": "de",
        "detect_fraktur": True
    },
    priority=9  # High priority
)

# Get result
result = task.get(timeout=300)
```

## GPU Management

### Memory Protection

- **GPU Lock**: Only 1 GPU task executes at a time (threading lock)
- **Memory Guard**: Monitors VRAM usage (threshold: 13.6GB = 85% of 16GB)
- **Automatic Cleanup**: GPU cache cleared after each task
- **OOM Recovery**: Automatic retry with smaller batch size or CPU fallback

### Task Distribution

```
GPU Queue (ocr_high, ocr_normal):
  - process_document_task
  - batch_process_task

CPU Queue (validation, metadata):
  - validate_german_text_task
  - extract_metadata_task

Maintenance Queue:
  - cleanup_task
  - update_system_metrics
```

## Error Handling

### Automatic Retries

```python
GPUTask:
  max_retries = 3
  retry_backoff = True
  retry_backoff_max = 600  # 10 minutes
  autoretry_for = (torch.cuda.OutOfMemoryError, RuntimeError)

CPUTask:
  max_retries = 3
  retry_backoff = True
  retry_backoff_max = 300  # 5 minutes
```

### Retry Strategy

1. **First failure**: Retry immediately
2. **Second failure**: Wait 2^1 = 2 minutes
3. **Third failure**: Wait 2^2 = 4 minutes
4. **Final failure**: Mark as FAILED, update database

### German Error Messages

All user-facing errors are in German:
- "Dokument nicht gefunden"
- "Zeitüberschreitung bei der Verarbeitung"
- "GPU-Speicher überschritten"
- "Verarbeitung fehlgeschlagen"

## Database Integration

### Models Updated

- **Document**: Status, OCR results, German validation
- **ProcessingJob**: Task tracking, retry counts
- **OCRResult**: Detailed OCR output with layout
- **SystemMetrics**: Performance monitoring

### Status Flow

```
PENDING → QUEUED → PROCESSING → COMPLETED
                              ↓
                           FAILED (with retries)
                              ↓
                         CANCELLED (by user)
```

## Monitoring

### Flower Dashboard

Access at `http://localhost:5555`:
- Active tasks
- Worker status
- Task history
- Queue sizes
- Success/failure rates

### Database Metrics

Stored every 5 minutes:
- CPU usage
- Memory usage
- GPU VRAM usage
- Disk usage

### Logging

Structured logging with `structlog`:
```json
{
  "event": "ocr_task_completed",
  "task_id": "abc-123",
  "document_id": "doc-uuid",
  "backend": "deepseek",
  "duration_ms": 2340,
  "confidence": 0.95,
  "timestamp": "2025-01-20T10:30:00Z"
}
```

## Performance Targets

### Single Document OCR

- **DeepSeek (GPU)**: 2-3 pages/second
- **GOT-OCR (GPU)**: 5-7 pages/second
- **Surya (CPU)**: 1-2 pages/second

### Batch Processing

- **GPU**: 1 document at a time (sequential)
- **CPU**: Up to 3 concurrent documents

### Latency

- **Task submission**: < 100ms
- **Status check**: < 50ms
- **WebSocket update**: < 2s interval

## Configuration

### Environment Variables

```bash
# Celery
CELERY_BROKER_URL=redis://localhost:6380/0
CELERY_RESULT_BACKEND=redis://localhost:6380/0

# OCR
OCR_TIMEOUT_SECONDS=300
DEFAULT_OCR_BACKEND=auto
DEFAULT_LANGUAGE=de

# GPU
GPU_MEMORY_FRACTION=0.85
ENABLE_GPU=true
GPU_BATCH_SIZE=32
```

### Queue Priorities

```python
ocr_high: priority=9    # High-priority OCR
ocr_normal: priority=5  # Normal OCR
validation: priority=3  # German validation
metadata: priority=3    # Metadata extraction
maintenance: priority=1 # Cleanup
metrics: priority=1     # System metrics
```

## Testing

### Unit Tests

```bash
pytest tests/test_celery_tasks.py -v
```

### Integration Tests

```bash
# Start services first
docker-compose up -d redis postgres

# Run tests
pytest tests/integration/test_async_ocr.py -v
```

### Manual Testing

```bash
# Submit test task
python -c "
from app.workers.tasks.ocr_tasks import process_document_task
task = process_document_task.delay('test-doc-id')
print(f'Task ID: {task.id}')
print(f'Status: {task.status}')
"
```

## Troubleshooting

### GPU Tasks Not Running

```bash
# Check GPU availability
nvidia-smi

# Check worker logs
celery -A app.workers.celery_app inspect active

# Check GPU lock status
python -c "from app.workers.celery_app import _gpu_lock; print(f'Locked: {_gpu_lock.locked()}')"
```

### Tasks Stuck in Queue

```bash
# Check queue lengths
celery -A app.workers.celery_app inspect reserved

# Purge queue (dangerous!)
celery -A app.workers.celery_app purge
```

### Memory Leaks

```bash
# Monitor GPU memory
watch -n 1 nvidia-smi

# Check worker memory
celery -A app.workers.celery_app inspect stats
```

## Future Enhancements

### Planned Features

1. **Email Notifications**: Send completion emails
2. **Webhook Support**: POST results to external URLs
3. **Task Priorities**: User-defined priority levels
4. **Task Dependencies**: Chain tasks together
5. **Result Caching**: Redis caching for frequent queries
6. **Distributed Workers**: Multi-GPU support

### Optimization Opportunities

1. **Batch Optimization**: Dynamic batch sizing
2. **Model Caching**: Keep models loaded in memory
3. **Pipeline Parallelism**: Process while extracting
4. **Result Streaming**: Stream large results

## Dependencies

### Required Packages

```
celery==5.3.4
redis==5.0.1
flower==2.0.1
kombu==5.3.4
structlog==24.1.0
psutil==5.9.7
```

### Optional (for monitoring)

```
prometheus-client==0.19.0
```

## Files Created/Modified

### New Files

```
app/workers/celery_app.py          # Celery configuration
app/workers/tasks/__init__.py      # Task exports
app/workers/tasks/ocr_tasks.py     # Main OCR tasks
app/workers/task_callbacks.py      # Lifecycle callbacks
app/services/task_service.py       # Task management service
app/api/v1/tasks.py                # REST + WebSocket API
CELERY_IMPLEMENTATION.md           # This file
```

### Modified Files

```
app/main.py                        # Added task router
requirements.txt                   # Added Celery deps
```

## Summary

Fully functional Celery-based async task processing system with:
- ✅ GPU-aware task scheduling
- ✅ Priority queues
- ✅ Real-time progress updates
- ✅ WebSocket support
- ✅ Automatic retries
- ✅ German error messages
- ✅ Database state management
- ✅ System monitoring
- ✅ Comprehensive error handling
- ✅ Production-ready configuration

**Status**: Ready for production use with RTX 4080 GPU acceleration.
