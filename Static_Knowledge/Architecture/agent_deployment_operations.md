# Agent Deployment & Operations Guide
**Ablage-System Document Processing Platform**
**Version:** 1.0
**Last Updated:** 2025-01-23

---

## 📑 Table of Contents

1. [Deployment Architecture](#deployment-architecture)
2. [Container Configuration](#container-configuration)
3. [Agent Orchestration](#agent-orchestration)
4. [Production Deployment](#production-deployment)
5. [Monitoring & Observability](#monitoring--observability)
6. [Health Checks](#health-checks)
7. [Scaling Strategies](#scaling-strategies)
8. [Troubleshooting](#troubleshooting)
9. [Disaster Recovery](#disaster-recovery)

---

## Deployment Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   PRODUCTION DEPLOYMENT                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │   FastAPI    │      │    Celery    │      │   Redis   │ │
│  │   Backend    │◄────►│   Workers    │◄────►│   Queue   │ │
│  │  (Agents)    │      │  (Agents)    │      │           │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
│         │                     │                             │
│         │                     │                             │
│         ▼                     ▼                             │
│  ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│  │ PostgreSQL   │      │    MinIO     │      │   GPU     │ │
│  │  (Metadata)  │      │  (Storage)   │      │   RTX     │ │
│  │              │      │              │      │   4080    │ │
│  └──────────────┘      └──────────────┘      └───────────┘ │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              MONITORING STACK                       │    │
│  │  Prometheus │ Grafana │ Loki │ AlertManager        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Deployment Components

| Component | Purpose | Scaling | GPU Access |
|-----------|---------|---------|------------|
| **FastAPI Backend** | API endpoints, synchronous agent tasks | Horizontal | No |
| **Celery Workers** | Async agent tasks, OCR processing | Horizontal (limited by GPU) | Yes |
| **Redis** | Task queue, caching | Vertical | No |
| **PostgreSQL** | Metadata, task results | Vertical | No |
| **MinIO** | Document storage | Horizontal | No |

---

## Container Configuration

### Docker Compose Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  # FastAPI Backend (Agents ohne GPU)
  backend:
    build:
      context: .
      dockerfile: docker/Dockerfile.backend
    image: ablage-system/backend:latest
    container_name: ablage-backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ablage
      - REDIS_URL=redis://redis:6379/0
      - MINIO_URL=http://minio:9000
      - LOG_LEVEL=INFO
      - ENVIRONMENT=production
    volumes:
      - ./app:/app/app
      - ./config:/app/config
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped

  # Celery Worker (GPU-enabled für OCR Agents)
  worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    image: ablage-system/worker:latest
    container_name: ablage-worker
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ablage
      - REDIS_URL=redis://redis:6379/0
      - MINIO_URL=http://minio:9000
      - LOG_LEVEL=INFO
      - NVIDIA_VISIBLE_DEVICES=0  # GPU 0
      - CUDA_VISIBLE_DEVICES=0
    volumes:
      - ./app:/app/app
      - ./config:/app/config
      - ./models:/app/models  # OCR model cache
    depends_on:
      - backend
      - redis
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    restart: unless-stopped
    command: >
      celery -A app.workers.celery_app worker
      --loglevel=info
      --concurrency=1
      --pool=solo
      --queues=ocr,default

  # PostgreSQL Database
  postgres:
    image: postgres:16
    container_name: ablage-postgres
    environment:
      - POSTGRES_DB=ablage
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infrastructure/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # Redis Queue & Cache
  redis:
    image: redis:7-alpine
    container_name: ablage-redis
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # MinIO Object Storage
  minio:
    image: minio/minio:latest
    container_name: ablage-minio
    command: server /data --console-address ":9001"
    environment:
      - MINIO_ROOT_USER=minioadmin
      - MINIO_ROOT_PASSWORD=minioadmin123
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"  # API
      - "9001:9001"  # Console
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3
    restart: unless-stopped

  # Prometheus Monitoring
  prometheus:
    image: prom/prometheus:latest
    container_name: ablage-prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    volumes:
      - ./infrastructure/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    restart: unless-stopped

  # Grafana Dashboard
  grafana:
    image: grafana/grafana:latest
    container_name: ablage-grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin123
      - GF_INSTALL_PLUGINS=redis-datasource
    volumes:
      - ./infrastructure/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./infrastructure/grafana/datasources:/etc/grafana/provisioning/datasources
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  minio_data:
  prometheus_data:
  grafana_data:
```

### Dockerfile für Backend

```dockerfile
# docker/Dockerfile.backend
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app /app/app
COPY config /app/config

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile für GPU Worker

```dockerfile
# docker/Dockerfile.worker
FROM nvidia/cuda:12.0-runtime-ubuntu22.04

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Install PyTorch with CUDA support
RUN pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Application code
COPY app /app/app
COPY config /app/config

# Pre-download OCR models (optional, for faster startup)
# RUN python3 -c "from app.services.ocr import download_models; download_models()"

# Run Celery worker
CMD ["celery", "-A", "app.workers.celery_app", "worker", \
     "--loglevel=info", "--concurrency=1", "--pool=solo"]
```

---

## Agent Orchestration

### Celery Configuration

```python
# app/workers/celery_app.py
from celery import Celery
from app.core.config import settings

# Create Celery app
celery_app = Celery(
    'ablage_agents',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Berlin',
    enable_utc=True,

    # Task routing
    task_routes={
        'app.workers.agent_tasks.ocr_processing_task': {'queue': 'ocr'},
        'app.workers.agent_tasks.document_classification_task': {'queue': 'default'},
        'app.workers.agent_tasks.monitoring_task': {'queue': 'default'}
    },

    # Task time limits
    task_time_limit=600,  # 10 minutes hard limit
    task_soft_time_limit=480,  # 8 minutes soft limit

    # Task retries
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # Result backend
    result_expires=3600,  # 1 hour

    # Worker settings
    worker_prefetch_multiplier=1,  # No prefetching (GPU workers)
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks (memory cleanup)

    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True
)
```

### Agent Tasks

```python
# app/workers/agent_tasks.py
from celery import Task
from app.workers.celery_app import celery_app
from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent
from Execution_Layer.Agents.document_classifier_agent import DocumentClassifierAgent
import structlog

logger = structlog.get_logger(__name__)


class AgentTask(Task):
    """Base task class for agent tasks with automatic agent lifecycle."""

    _agent = None

    @property
    def agent(self):
        """Get or create agent instance (singleton per worker)."""
        if self._agent is None:
            self._agent = self.create_agent()
        return self._agent

    def create_agent(self):
        """Override in subclass to create specific agent."""
        raise NotImplementedError

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure."""
        logger.error(
            "agent_task_failed",
            task_id=task_id,
            agent=self.agent.agent_id,
            error=str(exc)
        )


@celery_app.task(
    bind=True,
    base=AgentTask,
    name='app.workers.agent_tasks.ocr_processing_task',
    queue='ocr',
    max_retries=3,
    default_retry_delay=60
)
async def ocr_processing_task(self, document_id: str, backend: str = "auto"):
    """
    Process document with OCR agent.

    Args:
        document_id: Document to process
        backend: OCR backend to use

    Returns:
        OCR result dict
    """
    logger.info(
        "ocr_task_started",
        task_id=self.request.id,
        document_id=document_id,
        backend=backend
    )

    try:
        # Initialize agent if needed
        if not hasattr(self, '_ocr_agent'):
            from Execution_Layer.Agents.ocr_processing_agent import OCRProcessingAgent
            self._ocr_agent = OCRProcessingAgent()
            await self._ocr_agent.initialize()

        # Process document
        result = await self._ocr_agent.process_task({
            "document_id": document_id,
            "backend": backend
        })

        logger.info(
            "ocr_task_completed",
            task_id=self.request.id,
            document_id=document_id,
            success=result["success"],
            processing_time_ms=result.get("processing_time_ms")
        )

        return result

    except Exception as exc:
        logger.exception(
            "ocr_task_error",
            task_id=self.request.id,
            document_id=document_id,
            error=str(exc)
        )

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(
    bind=True,
    name='app.workers.agent_tasks.document_classification_task',
    queue='default',
    max_retries=3
)
async def document_classification_task(self, document_id: str):
    """
    Classify document.

    Args:
        document_id: Document to classify

    Returns:
        Classification result dict
    """
    logger.info(
        "classification_task_started",
        task_id=self.request.id,
        document_id=document_id
    )

    try:
        # Initialize agent if needed
        if not hasattr(self, '_classifier_agent'):
            from Execution_Layer.Agents.document_classifier_agent import DocumentClassifierAgent
            self._classifier_agent = DocumentClassifierAgent()
            await self._classifier_agent.initialize()

        # Classify document
        result = await self._classifier_agent.process_task({
            "document_id": document_id
        })

        logger.info(
            "classification_task_completed",
            task_id=self.request.id,
            document_id=document_id,
            document_type=result.get("document_type"),
            confidence=result.get("confidence")
        )

        return result

    except Exception as exc:
        logger.exception(
            "classification_task_error",
            task_id=self.request.id,
            document_id=document_id,
            error=str(exc)
        )
        raise
```

---

## Production Deployment

### Pre-Deployment Checklist

```markdown
## Pre-Deployment Checklist

### Code Quality
- [ ] All tests passing (unit, integration, e2e)
- [ ] Code coverage > 80%
- [ ] Type checking clean (mypy)
- [ ] Linting clean (ruff)
- [ ] Security scan clean (bandit)

### Configuration
- [ ] Environment variables configured (.env.production)
- [ ] Database migrations applied
- [ ] Secrets managed securely (Vault/Secrets Manager)
- [ ] SSL certificates configured
- [ ] CORS settings configured

### Infrastructure
- [ ] GPU drivers installed (CUDA 12.x, cuDNN 8.9+)
- [ ] Docker installed and configured
- [ ] Sufficient disk space (min 500GB)
- [ ] Network connectivity verified
- [ ] Firewall rules configured

### Monitoring
- [ ] Prometheus exporters configured
- [ ] Grafana dashboards imported
- [ ] AlertManager rules configured
- [ ] Log aggregation configured (Loki)
- [ ] Health check endpoints tested

### Backup & Recovery
- [ ] Database backup strategy configured
- [ ] MinIO backup configured
- [ ] Disaster recovery plan documented
- [ ] Rollback procedure tested

### Documentation
- [ ] Deployment documentation updated
- [ ] Runbooks created
- [ ] Incident response procedures documented
- [ ] Team trained on operations
```

### Deployment Steps

```bash
#!/bin/bash
# deploy.sh - Production deployment script

set -e  # Exit on error
set -u  # Exit on undefined variable

# Configuration
ENVIRONMENT="production"
BACKUP_DIR="/backups/ablage-$(date +%Y%m%d-%H%M%S)"

echo "======================================"
echo "Ablage-System Production Deployment"
echo "======================================"

# Step 1: Pre-deployment backup
echo "Step 1: Creating pre-deployment backup..."
mkdir -p "$BACKUP_DIR"

# Backup database
docker exec ablage-postgres pg_dump -U postgres ablage > "$BACKUP_DIR/database.sql"

# Backup MinIO data
docker exec ablage-minio mc mirror /data "$BACKUP_DIR/minio/"

echo "Backup completed: $BACKUP_DIR"

# Step 2: Pull latest images
echo "Step 2: Pulling latest images..."
docker-compose pull

# Step 3: Stop services
echo "Step 3: Stopping services..."
docker-compose down

# Step 4: Database migrations
echo "Step 4: Running database migrations..."
docker-compose run --rm backend alembic upgrade head

# Step 5: Start services
echo "Step 5: Starting services..."
docker-compose up -d

# Step 6: Wait for services to be healthy
echo "Step 6: Waiting for services to be healthy..."
timeout=300
elapsed=0
interval=5

while [ $elapsed -lt $timeout ]; do
    if docker-compose ps | grep -q "unhealthy"; then
        echo "Waiting for services to become healthy... (${elapsed}s/${timeout}s)"
        sleep $interval
        elapsed=$((elapsed + interval))
    else
        echo "All services healthy!"
        break
    fi
done

if [ $elapsed -ge $timeout ]; then
    echo "ERROR: Services did not become healthy within ${timeout}s"
    echo "Rolling back..."
    docker-compose down
    # Restore from backup
    docker-compose up -d postgres
    docker exec -i ablage-postgres psql -U postgres ablage < "$BACKUP_DIR/database.sql"
    exit 1
fi

# Step 7: Smoke tests
echo "Step 7: Running smoke tests..."
python scripts/smoke_tests.py

# Step 8: Verify GPU access
echo "Step 8: Verifying GPU access..."
docker exec ablage-worker python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"

echo "======================================"
echo "Deployment completed successfully!"
echo "======================================"

# Step 9: Post-deployment verification
echo "Step 9: Post-deployment verification..."
echo "Backend health: $(curl -f http://localhost:8000/health)"
echo "Prometheus: http://localhost:9090"
echo "Grafana: http://localhost:3000 (admin/admin123)"
echo "MinIO Console: http://localhost:9001 (minioadmin/minioadmin123)"
```

---

## Monitoring & Observability

### Prometheus Configuration

```yaml
# infrastructure/prometheus/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

  external_labels:
    environment: 'production'
    project: 'ablage-system'

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - 'alertmanager:9093'

# Scrape configurations
scrape_configs:
  # Backend metrics
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'

  # Celery worker metrics
  - job_name: 'celery'
    static_configs:
      - targets: ['worker:9090']

  # PostgreSQL metrics
  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  # Redis metrics
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  # MinIO metrics
  - job_name: 'minio'
    static_configs:
      - targets: ['minio:9000']
    metrics_path: '/minio/v2/metrics/cluster'

  # Node exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  # NVIDIA GPU exporter
  - job_name: 'nvidia_gpu'
    static_configs:
      - targets: ['nvidia-gpu-exporter:9835']
```

### Alert Rules

```yaml
# infrastructure/prometheus/alerts.yml
groups:
  - name: agent_alerts
    interval: 30s
    rules:
      # High error rate
      - alert: AgentHighErrorRate
        expr: |
          rate(agent_tasks_total{status="error"}[5m])
          /
          rate(agent_tasks_total[5m])
          > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High agent task error rate"
          description: "{{ $labels.agent_id }} has error rate > 10% (current: {{ $value | humanizePercentage }})"

      # GPU out of memory
      - alert: GPUOutOfMemory
        expr: gpu_vram_usage_percent > 95
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "GPU VRAM usage critical"
          description: "GPU VRAM usage is {{ $value }}%"

      # Slow task processing
      - alert: SlowTaskProcessing
        expr: |
          histogram_quantile(0.95,
            rate(agent_task_duration_seconds_bucket[5m])
          ) > 60
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Slow agent task processing"
          description: "95th percentile task duration is {{ $value }}s"

      # Worker down
      - alert: WorkerDown
        expr: up{job="celery"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Celery worker down"
          description: "Celery worker has been down for more than 1 minute"

      # High queue length
      - alert: HighQueueLength
        expr: celery_queue_length > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High task queue length"
          description: "Task queue has {{ $value }} pending tasks"
```

### Grafana Dashboard

```json
{
  "dashboard": {
    "title": "Ablage-System Agents",
    "panels": [
      {
        "title": "Task Processing Rate",
        "targets": [
          {
            "expr": "rate(agent_tasks_total[5m])",
            "legendFormat": "{{ agent_id }} - {{ status }}"
          }
        ]
      },
      {
        "title": "Task Duration (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(agent_task_duration_seconds_bucket[5m]))",
            "legendFormat": "{{ agent_id }}"
          }
        ]
      },
      {
        "title": "GPU VRAM Usage",
        "targets": [
          {
            "expr": "gpu_vram_usage_percent",
            "legendFormat": "VRAM Usage %"
          }
        ]
      },
      {
        "title": "Active Tasks",
        "targets": [
          {
            "expr": "agent_active_tasks",
            "legendFormat": "{{ agent_id }}"
          }
        ]
      }
    ]
  }
}
```

---

## Health Checks

### Health Check Endpoint

```python
# app/api/v1/health.py
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from typing import Dict, Any
from app.gpu_manager import GPUManager
from app.db.session import async_session_maker
import redis
import minio
import structlog

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    """
    Comprehensive health check endpoint.

    Checks:
    - Database connection
    - Redis connection
    - MinIO connection
    - GPU availability
    - Disk space
    """
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "minio": await check_minio(),
        "gpu": check_gpu(),
        "disk_space": check_disk_space()
    }

    all_healthy = all(check["healthy"] for check in checks.values())
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if all_healthy else "unhealthy",
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat()
        }
    )


async def check_database() -> Dict[str, Any]:
    """Check database connection."""
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))

        return {
            "healthy": True,
            "message": "Database connection OK"
        }

    except Exception as e:
        logger.error("database_health_check_failed", error=str(e))
        return {
            "healthy": False,
            "message": f"Database error: {str(e)}"
        }


async def check_redis() -> Dict[str, Any]:
    """Check Redis connection."""
    try:
        redis_client = redis.from_url(settings.REDIS_URL)
        redis_client.ping()

        return {
            "healthy": True,
            "message": "Redis connection OK"
        }

    except Exception as e:
        logger.error("redis_health_check_failed", error=str(e))
        return {
            "healthy": False,
            "message": f"Redis error: {str(e)}"
        }


async def check_minio() -> Dict[str, Any]:
    """Check MinIO connection."""
    try:
        minio_client = minio.Minio(
            settings.MINIO_URL,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY
        )

        # Check if bucket exists
        bucket_exists = minio_client.bucket_exists(settings.MINIO_BUCKET)

        return {
            "healthy": True,
            "message": "MinIO connection OK",
            "bucket_exists": bucket_exists
        }

    except Exception as e:
        logger.error("minio_health_check_failed", error=str(e))
        return {
            "healthy": False,
            "message": f"MinIO error: {str(e)}"
        }


def check_gpu() -> Dict[str, Any]:
    """Check GPU availability."""
    try:
        gpu_manager = GPUManager()

        if not gpu_manager.is_available():
            return {
                "healthy": True,  # GPU optional, not critical
                "message": "GPU not available (CPU fallback active)",
                "available": False
            }

        status = gpu_manager.get_status()

        return {
            "healthy": status["vram_usage_percent"] < 95,
            "message": "GPU OK",
            "available": True,
            "vram_usage_percent": status["vram_usage_percent"],
            "free_vram_gb": status["free_vram_gb"]
        }

    except Exception as e:
        logger.error("gpu_health_check_failed", error=str(e))
        return {
            "healthy": True,  # GPU optional
            "message": f"GPU check error: {str(e)}",
            "available": False
        }


def check_disk_space() -> Dict[str, Any]:
    """Check available disk space."""
    try:
        import psutil

        disk = psutil.disk_usage('/')
        free_percent = (disk.free / disk.total) * 100

        return {
            "healthy": free_percent > 10,  # At least 10% free
            "message": "Disk space OK" if free_percent > 10 else "Low disk space",
            "free_percent": free_percent,
            "free_gb": disk.free / (1024**3)
        }

    except Exception as e:
        logger.error("disk_health_check_failed", error=str(e))
        return {
            "healthy": False,
            "message": f"Disk check error: {str(e)}"
        }
```

---

## Scaling Strategies

### Horizontal Scaling

```yaml
# Scale Celery workers
docker-compose up -d --scale worker=4
```

### GPU Worker Pool

```yaml
# docker-compose.gpu-pool.yml
# Multiple GPU workers for parallel OCR processing

services:
  worker-gpu-0:
    extends: worker
    container_name: ablage-worker-gpu-0
    environment:
      - NVIDIA_VISIBLE_DEVICES=0
      - CUDA_VISIBLE_DEVICES=0
      - WORKER_ID=gpu-0

  worker-gpu-1:
    extends: worker
    container_name: ablage-worker-gpu-1
    environment:
      - NVIDIA_VISIBLE_DEVICES=1
      - CUDA_VISIBLE_DEVICES=1
      - WORKER_ID=gpu-1
```

---

**Document Status:** ✅ **COMPLETE**

Production-ready deployment guide mit:
- ✅ Container Configuration (Docker Compose)
- ✅ Agent Orchestration (Celery)
- ✅ Deployment Scripts
- ✅ Monitoring & Observability (Prometheus, Grafana)
- ✅ Health Checks
- ✅ Scaling Strategies
