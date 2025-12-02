# Celery Async OCR Tasks - Quick Start Guide

## Prerequisites

1. **Redis** running on port 6380
2. **PostgreSQL** running on port 5433
3. **Python 3.11+** with dependencies installed
4. **NVIDIA GPU** (RTX 4080) with CUDA 12.x (optional, falls back to CPU)

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start Redis (if not running)

```bash
# Using Docker
docker run -d -p 6380:6379 --name redis redis:7-alpine

# Or using docker-compose
docker-compose up -d redis
```

### 3. Configure Environment

Create/update `.env` file:

```bash
# Celery
CELERY_BROKER_URL=redis://localhost:6380/0
CELERY_RESULT_BACKEND=redis://localhost:6380/0

# Database
DATABASE_URL=postgresql+asyncpg://ablage_admin:changeme@localhost:5433/ablage_system

# OCR Settings
OCR_TIMEOUT_SECONDS=300
DEFAULT_OCR_BACKEND=auto
DEFAULT_LANGUAGE=de

# GPU
ENABLE_GPU=true
GPU_MEMORY_FRACTION=0.85
```

## Starting the System

### Terminal 1: Start FastAPI Server

```bash
python app/main.py
```

API will be available at `http://localhost:8000`

### Terminal 2: Start Celery Worker

```bash
celery -A app.workers.celery_app worker \
  --loglevel=info \
  --concurrency=1 \
  --pool=solo \
  --queues=ocr_high,ocr_normal,validation,metadata,maintenance,metrics
```

### Terminal 3: Start Celery Beat (Optional - for periodic tasks)

```bash
celery -A app.workers.celery_app beat --loglevel=info
```

### Terminal 4: Start Flower Monitoring (Optional)

```bash
celery -A app.workers.celery_app flower --port=5555
```

Access Flower at `http://localhost:5555`

## Basic Usage

### 1. Using the REST API

#### Submit OCR Task

```bash
curl -X POST "http://localhost:8000/api/v1/ocr/process" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -F "backend=auto" \
  -F "language=de" \
  -F "priority=high"
```

Response:
```json
{
  "task_id": "abc-123-def-456",
  "document_id": "doc-uuid",
  "status": "queued",
  "message": "Aufgabe wurde erstellt"
}
```

#### Check Task Status

```bash
curl "http://localhost:8000/api/v1/tasks/abc-123-def-456" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Response:
```json
{
  "task_id": "abc-123-def-456",
  "state": "PROGRESS",
  "progress": 75,
  "message": "Deutsche Textvalidierung...",
  "current": 75,
  "total": 100,
  "ready": false
}
```

#### Get Task Result

```bash
curl "http://localhost:8000/api/v1/tasks/abc-123-def-456/result?timeout=30" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Cancel Task

```bash
curl -X DELETE "http://localhost:8000/api/v1/tasks/abc-123-def-456" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### List User's Tasks

```bash
curl "http://localhost:8000/api/v1/tasks/?limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 2. Using WebSocket for Real-Time Updates

#### Python Client

```python
import asyncio
import websockets
import json

async def monitor_task(task_id, token):
    uri = f"ws://localhost:8000/api/v1/tasks/ws/{task_id}"

    async with websockets.connect(uri) as websocket:
        while True:
            message = await websocket.recv()
            data = json.loads(message)

            print(f"Progress: {data.get('progress', 0)}%")
            print(f"Message: {data.get('message', '')}")

            if data.get('state') in ['SUCCESS', 'FAILURE']:
                print(f"Final state: {data['state']}")
                if data.get('result'):
                    print(f"Result: {data['result']}")
                break

# Run
asyncio.run(monitor_task("abc-123-def-456", "your-token"))
```

#### JavaScript Client

```javascript
const ws = new WebSocket(`ws://localhost:8000/api/v1/tasks/ws/${taskId}`);

ws.onopen = () => {
  console.log('WebSocket connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  console.log(`Progress: ${data.progress}% - ${data.message}`);

  if (data.state === 'SUCCESS') {
    console.log('Success!', data.result);
    ws.close();
  } else if (data.state === 'FAILURE') {
    console.error('Failed:', data.error);
    ws.close();
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('WebSocket closed');
};
```

### 3. Direct Task Submission (Internal Python)

```python
from app.workers.tasks.ocr_tasks import process_document_task
from uuid import UUID

# Submit task
task = process_document_task.apply_async(
    args=[str(document_id)],
    kwargs={
        "backend": "auto",
        "language": "de",
        "detect_layout": True,
        "detect_fraktur": True,
        "priority": "high"
    },
    priority=9
)

print(f"Task ID: {task.id}")
print(f"Status: {task.status}")

# Wait for result (blocks)
result = task.get(timeout=300)
print(f"Result: {result}")
```

## Monitoring

### Flower Dashboard

Access `http://localhost:5555` for:
- Real-time task monitoring
- Worker status
- Queue lengths
- Task history
- Success/failure rates

### Celery Commands

```bash
# Inspect active tasks
celery -A app.workers.celery_app inspect active

# Inspect registered tasks
celery -A app.workers.celery_app inspect registered

# Check worker stats
celery -A app.workers.celery_app inspect stats

# Purge all queues (DANGEROUS!)
celery -A app.workers.celery_app purge

# Shutdown worker
celery -A app.workers.celery_app control shutdown
```

### Check GPU Status

```bash
# NVIDIA GPU status
nvidia-smi

# GPU lock status (Python)
python -c "from app.workers.celery_app import _gpu_lock; print(f'GPU Locked: {_gpu_lock.locked()}')"

# Current GPU memory
python -c "import torch; print(f'GPU Memory: {torch.cuda.memory_allocated() / 1024**3:.2f} GB')"
```

## Common Scenarios

### Scenario 1: Process Single Document

```python
import httpx
import asyncio

async def process_document(file_path):
    async with httpx.AsyncClient() as client:
        # Upload and start processing
        with open(file_path, "rb") as f:
            response = await client.post(
                "http://localhost:8000/api/v1/ocr/process",
                files={"file": f},
                data={
                    "backend": "auto",
                    "language": "de",
                    "detect_layout": True
                },
                headers={"Authorization": f"Bearer {token}"}
            )

        task_id = response.json()["task_id"]
        print(f"Task submitted: {task_id}")

        # Poll for completion
        while True:
            status = await client.get(
                f"http://localhost:8000/api/v1/tasks/{task_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            data = status.json()

            print(f"Progress: {data.get('progress', 0)}%")

            if data.get('ready'):
                return data.get('result')

            await asyncio.sleep(2)

# Run
result = asyncio.run(process_document("document.pdf"))
print(f"Extracted text: {result['text'][:100]}...")
```

### Scenario 2: Batch Processing

```python
async def batch_process(file_paths):
    # Upload all documents
    document_ids = []
    for file_path in file_paths:
        # ... upload logic ...
        document_ids.append(doc_id)

    # Submit batch task
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/ocr/batch",
            json={
                "document_ids": document_ids,
                "backend": "auto",
                "language": "de"
            },
            headers={"Authorization": f"Bearer {token}"}
        )

    task_id = response.json()["task_id"]

    # Monitor progress
    # ... polling logic ...

    return results
```

### Scenario 3: High Priority Processing

```python
# Submit with high priority
task = process_document_task.apply_async(
    args=[str(document_id)],
    kwargs={
        "backend": "deepseek",  # Best quality
        "language": "de",
        "priority": "high"
    },
    priority=9  # Highest priority
)
```

## Troubleshooting

### Problem: Tasks stuck in queue

**Solution:**
```bash
# Check worker is running
celery -A app.workers.celery_app inspect active

# Check queue status
celery -A app.workers.celery_app inspect reserved

# Restart worker if needed
```

### Problem: GPU out of memory

**Solution:**
- Tasks automatically retry with CPU fallback
- Check GPU memory: `nvidia-smi`
- Reduce batch size in config
- Ensure only 1 GPU task runs at a time

### Problem: WebSocket disconnects

**Solution:**
- Check network connection
- Verify task_id is valid
- Check server logs for errors
- Ensure WebSocket support in proxy (if using)

### Problem: Slow processing

**Check:**
1. GPU availability: `nvidia-smi`
2. Worker status: `celery -A app.workers.celery_app inspect active`
3. Queue lengths: `celery -A app.workers.celery_app inspect reserved`
4. System resources: `htop` or `top`

## Performance Tips

### 1. GPU Optimization

- Keep worker pool size at 1 (`--concurrency=1`)
- Use `--pool=solo` for GPU isolation
- Monitor VRAM with `nvidia-smi`
- Clear cache regularly

### 2. Queue Management

- Use priority queues appropriately
- High priority for urgent tasks
- Normal priority for regular workflow
- Low priority for background tasks

### 3. Batch Processing

- Group similar documents
- Use batch endpoints for multiple files
- Consider document size limits

### 4. Monitoring

- Use Flower for real-time monitoring
- Check logs regularly
- Monitor system metrics
- Set up alerts for failures

## Next Steps

1. **Read Full Documentation**: See `CELERY_IMPLEMENTATION.md`
2. **Configure for Production**: Set proper secrets and limits
3. **Set Up Monitoring**: Configure Flower and alerts
4. **Test Performance**: Run load tests
5. **Optimize Settings**: Tune worker count and timeouts

## Support

For issues or questions:
1. Check logs: `celery -A app.workers.celery_app events`
2. Monitor with Flower: `http://localhost:5555`
3. Review implementation docs: `CELERY_IMPLEMENTATION.md`
4. Check GPU status: `nvidia-smi`

## Quick Reference

### Environment Variables
- `CELERY_BROKER_URL`: Redis connection
- `CELERY_RESULT_BACKEND`: Result storage
- `OCR_TIMEOUT_SECONDS`: Max processing time
- `ENABLE_GPU`: Enable/disable GPU

### Worker Commands
```bash
# Start worker
celery -A app.workers.celery_app worker --loglevel=info

# Start beat
celery -A app.workers.celery_app beat --loglevel=info

# Start flower
celery -A app.workers.celery_app flower
```

### API Endpoints
- `POST /api/v1/ocr/process` - Submit OCR task
- `GET /api/v1/tasks/{task_id}` - Get task status
- `DELETE /api/v1/tasks/{task_id}` - Cancel task
- `GET /api/v1/tasks/` - List tasks
- `WS /api/v1/tasks/ws/{task_id}` - WebSocket updates

### Task Priorities
- **High (9)**: Urgent documents
- **Normal (5)**: Regular workflow
- **Low (1)**: Background tasks

---

**Status**: Production ready with RTX 4080 GPU support
**Last Updated**: 2025-01-20
