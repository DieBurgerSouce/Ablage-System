# Monitoring Setup

You are setting up comprehensive monitoring for the Ablage-System.

## Your Task

Implement monitoring infrastructure with Prometheus, Grafana, and application instrumentation:

### 1. Prometheus Metrics Exporter

Create `app/core/metrics.py`:

```python
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from fastapi import Response

# OCR Metrics
ocr_requests_total = Counter(
    'ocr_requests_total',
    'Total OCR processing requests',
    ['backend', 'status']
)

ocr_processing_duration = Histogram(
    'ocr_processing_duration_seconds',
    'OCR processing time',
    ['backend'],
    buckets=[0.5, 1, 2, 5, 10, 30, 60]
)

# GPU Metrics
gpu_memory_usage = Gauge(
    'gpu_memory_usage_bytes',
    'Current GPU memory usage',
    ['device']
)

# Queue Metrics
document_queue_length = Gauge(
    'document_queue_length',
    'Number of documents in processing queue'
)

# API Metrics
api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status_code']
)

api_request_duration = Histogram(
    'api_request_duration_seconds',
    'API request duration',
    ['method', 'endpoint']
)

# Database Metrics
db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections'
)

# Error Metrics
errors_total = Counter(
    'errors_total',
    'Total errors',
    ['error_type', 'endpoint']
)
```

### 2. Middleware for Automatic Tracking

Create `app/middleware/prometheus.py`:

```python
from starlette.middleware.base import BaseHTTPMiddleware
import time

class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time
        api_request_duration.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

        api_requests_total.labels(
            method=request.method,
            endpoint=request.url.path,
            status_code=response.status_code
        ).inc()

        return response
```

### 3. Metrics Endpoint

Add to `app/main.py`:

```python
from prometheus_client import generate_latest

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

### 4. Prometheus Configuration

Create `infrastructure/monitoring/prometheus.yml`:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'ablage-api'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'

  - job_name: 'ablage-worker'
    static_configs:
      - targets: ['worker:8001']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
```

### 5. Grafana Dashboards

Create `infrastructure/monitoring/grafana/dashboards/ablage-overview.json`:

Dashboard panels:
- API request rate (requests/sec)
- API response times (p50, p95, p99)
- OCR processing queue length
- OCR processing time by backend
- GPU memory usage
- GPU utilization
- Error rate
- Active database connections
- Cache hit rate (Redis)

### 6. Docker Compose Integration

Add to `docker-compose.yml`:

```yaml
prometheus:
  image: prom/prometheus:latest
  volumes:
    - ./infrastructure/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus-data:/prometheus
  ports:
    - "9090:9090"
  networks:
    - ablage-network

grafana:
  image: grafana/grafana:latest
  volumes:
    - ./infrastructure/monitoring/grafana:/etc/grafana/provisioning
    - grafana-data:/var/lib/grafana
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
  networks:
    - ablage-network
  depends_on:
    - prometheus

postgres-exporter:
  image: prometheuscommunity/postgres-exporter:latest
  environment:
    - DATA_SOURCE_NAME=postgresql://postgres:postgres@postgres:5432/ablage_ocr?sslmode=disable
  networks:
    - ablage-network

redis-exporter:
  image: oliver006/redis_exporter:latest
  environment:
    - REDIS_ADDR=redis:6379
  networks:
    - ablage-network

node-exporter:
  image: prom/node-exporter:latest
  networks:
    - ablage-network

volumes:
  prometheus-data:
  grafana-data:
```

### 7. Alerting Rules

Create `infrastructure/monitoring/alerts.yml`:

```yaml
groups:
  - name: ablage_alerts
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: rate(errors_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"

      - alert: SlowOCRProcessing
        expr: histogram_quantile(0.95, rate(ocr_processing_duration_seconds_bucket[5m])) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "OCR processing is slow"

      - alert: GPUMemoryHigh
        expr: gpu_memory_usage_bytes / gpu_memory_total_bytes > 0.9
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "GPU memory usage above 90%"

      - alert: QueueBacklog
        expr: document_queue_length > 100
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Large queue backlog"
```

### 8. Health Checks

Enhance `app/api/v1/health.py`:

```python
@router.get("/health")
async def health_check():
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "minio": await check_minio(),
        "gpu": check_gpu(),
        "queue": await check_queue_health()
    }

    all_healthy = all(checks.values())

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": checks,
        "timestamp": datetime.utcnow()
    }
```

### 9. Custom Metrics for GPU

Create GPU monitoring script:

```python
import torch
from prometheus_client import Gauge

gpu_utilization = Gauge('gpu_utilization_percent', 'GPU utilization', ['device'])
gpu_temperature = Gauge('gpu_temperature_celsius', 'GPU temperature', ['device'])
gpu_power_usage = Gauge('gpu_power_watts', 'GPU power usage', ['device'])

async def update_gpu_metrics():
    if torch.cuda.is_available():
        # Update GPU metrics from nvidia-smi
        pass
```

### 10. Documentation

Create `docs/MONITORING.md`:
- How to access Grafana (http://localhost:3000)
- Default credentials
- Available dashboards
- How to create custom dashboards
- Alert configuration
- Metric descriptions

## Output

Provide:
1. All monitoring code files
2. Docker Compose additions
3. Prometheus configuration
4. Grafana dashboard JSON
5. Alert rules
6. Setup and access instructions
