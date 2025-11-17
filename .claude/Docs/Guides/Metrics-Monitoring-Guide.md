# Metrics & Monitoring Guide

## 🎯 Overview

Comprehensive production-grade monitoring setup for the Ablage System using the industry-standard Prometheus + Grafana stack. This guide covers everything from metric instrumentation to alert configuration, dashboard design, and incident response.

### Why Monitoring Matters

**Observability is not optional in production systems.** The Ablage System processes sensitive business documents with complex GPU-accelerated ML pipelines. Without comprehensive monitoring, you're flying blind:

- **Performance Issues**: Detect slow OCR processing, database bottlenecks, memory leaks
- **Resource Exhaustion**: Track GPU VRAM, CPU, RAM before they cause failures
- **Error Tracking**: Identify failing backends, API errors, processing failures
- **Capacity Planning**: Predict when to scale horizontally/vertically
- **SLA Compliance**: Measure uptime, latency, accuracy against targets
- **Cost Optimization**: Identify underutilized resources

### Monitoring Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ABLAGE SYSTEM COMPONENTS                     │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ FastAPI  │  │  Celery  │  │ OCR GPU  │  │ PostgreSQL│      │
│  │  Metrics │  │  Metrics │  │  Metrics │  │  Exporter │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬──────┘      │
│       │             │             │             │              │
│       └─────────────┴─────────────┴─────────────┘              │
│                         │                                       │
└─────────────────────────┼───────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │   PROMETHEUS SERVER   │
              │                       │
              │ • Scrapes metrics     │
              │ • Stores time series  │
              │ • Evaluates alerts    │
              │ • Recording rules     │
              └───────┬───────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
┌──────────────┐ ┌─────────┐ ┌──────────────┐
│   GRAFANA    │ │ ALERTMGR│ │  PROMETHEUS  │
│              │ │         │ │  FEDERATION  │
│ • Dashboards │ │ • Routes│ │  (Multi-DC)  │
│ • Queries    │ │ • Groups│ │              │
│ • Alerts     │ │ • Notify│ │              │
└──────────────┘ └────┬────┘ └──────────────┘
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
┌──────────────┐ ┌─────────┐ ┌──────────────┐
│    SLACK     │ │PAGERDUTY│ │    EMAIL     │
└──────────────┘ └─────────┘ └──────────────┘
```

### Key Concepts

**Metrics**: Quantitative measurements of system behavior (counters, gauges, histograms)
**Labels**: Dimensions for filtering/aggregating metrics (e.g., `method="POST"`, `backend="deepseek"`)
**Scraping**: Prometheus pulls metrics from HTTP endpoints every 15s
**PromQL**: Query language for analyzing time-series data
**Alerting**: Automated notifications when metrics violate thresholds
**Dashboards**: Visual representation of metrics for monitoring
**SLIs/SLOs**: Service Level Indicators/Objectives for measuring reliability

---

## 📊 Application Metrics

### Metric Types

Prometheus supports 4 metric types:

1. **Counter**: Monotonically increasing value (requests, errors)
2. **Gauge**: Value that can go up/down (memory, queue depth, active connections)
3. **Histogram**: Distribution of values (request duration, response size)
4. **Summary**: Similar to histogram, calculates quantiles client-side

### Core Metrics Module

```python
# backend/core/metrics.py

"""
Prometheus metrics for the Ablage System.

This module defines all application metrics using the prometheus_client library.
Metrics are exposed on /metrics endpoint and scraped by Prometheus every 15s.

Naming Convention:
- Use snake_case
- Include unit suffix (_seconds, _bytes, _total)
- Use descriptive names (http_requests_total, not requests)
- Namespace with component (ocr_processing_duration_seconds)
"""

from prometheus_client import Counter, Histogram, Gauge, Summary, Info
from prometheus_client import generate_latest, REGISTRY, CONTENT_TYPE_LATEST
import time
import psutil
import GPUtil
from typing import Optional


# ==============================================================================
# HTTP/API METRICS
# ==============================================================================

http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests received',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

http_request_size_bytes = Summary(
    'http_request_size_bytes',
    'HTTP request size in bytes',
    ['method', 'endpoint']
)

http_response_size_bytes = Summary(
    'http_response_size_bytes',
    'HTTP response size in bytes',
    ['method', 'endpoint']
)

http_requests_in_progress = Gauge(
    'http_requests_in_progress',
    'Number of HTTP requests currently being processed',
    ['method', 'endpoint']
)

# ==============================================================================
# OCR PROCESSING METRICS
# ==============================================================================

ocr_processing_duration_seconds = Histogram(
    'ocr_processing_duration_seconds',
    'OCR processing duration in seconds',
    ['backend', 'document_type', 'complexity'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0]
)

ocr_requests_total = Counter(
    'ocr_requests_total',
    'Total OCR requests',
    ['backend', 'document_type', 'status']
)

ocr_confidence_score = Histogram(
    'ocr_confidence_score',
    'OCR confidence score distribution',
    ['backend', 'document_type'],
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99, 1.0]
)

ocr_pages_processed_total = Counter(
    'ocr_pages_processed_total',
    'Total pages processed by OCR',
    ['backend']
)

ocr_characters_extracted_total = Counter(
    'ocr_characters_extracted_total',
    'Total characters extracted by OCR',
    ['backend']
)

ocr_backend_health = Gauge(
    'ocr_backend_health',
    'OCR backend health status (1=healthy, 0=unhealthy)',
    ['backend']
)

ocr_model_load_duration_seconds = Histogram(
    'ocr_model_load_duration_seconds',
    'Time to load OCR model into memory',
    ['backend', 'model_name'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0]
)

# ==============================================================================
# GPU METRICS
# ==============================================================================

gpu_memory_used_bytes = Gauge(
    'gpu_memory_used_bytes',
    'GPU memory currently in use',
    ['gpu_id', 'gpu_name']
)

gpu_memory_total_bytes = Gauge(
    'gpu_memory_total_bytes',
    'Total GPU memory available',
    ['gpu_id', 'gpu_name']
)

gpu_utilization_percent = Gauge(
    'gpu_utilization_percent',
    'GPU utilization percentage (0-100)',
    ['gpu_id', 'gpu_name']
)

gpu_temperature_celsius = Gauge(
    'gpu_temperature_celsius',
    'GPU temperature in Celsius',
    ['gpu_id', 'gpu_name']
)

gpu_power_draw_watts = Gauge(
    'gpu_power_draw_watts',
    'GPU power consumption in watts',
    ['gpu_id', 'gpu_name']
)

gpu_model_loaded = Gauge(
    'gpu_model_loaded',
    'Currently loaded model on GPU (1=loaded, 0=unloaded)',
    ['gpu_id', 'model_name']
)

# ==============================================================================
# QUEUE/CELERY METRICS
# ==============================================================================

queue_depth = Gauge(
    'queue_depth',
    'Number of jobs waiting in queue',
    ['queue_name', 'priority']
)

queue_processing_time_seconds = Histogram(
    'queue_processing_time_seconds',
    'Time spent processing queue jobs',
    ['queue_name', 'task_name'],
    buckets=[0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 300.0, 600.0]
)

celery_tasks_total = Counter(
    'celery_tasks_total',
    'Total Celery tasks executed',
    ['task_name', 'status']
)

celery_task_retries_total = Counter(
    'celery_task_retries_total',
    'Total Celery task retries',
    ['task_name', 'retry_reason']
)

celery_workers_active = Gauge(
    'celery_workers_active',
    'Number of active Celery workers'
)

# ==============================================================================
# DATABASE METRICS
# ==============================================================================

db_connections_active = Gauge(
    'db_connections_active',
    'Number of active database connections'
)

db_connections_idle = Gauge(
    'db_connections_idle',
    'Number of idle database connections'
)

db_connections_max = Gauge(
    'db_connections_max',
    'Maximum allowed database connections'
)

db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query duration in seconds',
    ['query_type', 'table'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

db_queries_total = Counter(
    'db_queries_total',
    'Total database queries executed',
    ['query_type', 'status']
)

db_transactions_total = Counter(
    'db_transactions_total',
    'Total database transactions',
    ['status']
)

db_size_bytes = Gauge(
    'db_size_bytes',
    'Database size in bytes',
    ['database']
)

db_table_rows = Gauge(
    'db_table_rows',
    'Number of rows in table',
    ['table']
)

# ==============================================================================
# CACHE/REDIS METRICS
# ==============================================================================

cache_operations_total = Counter(
    'cache_operations_total',
    'Total cache operations',
    ['operation', 'status']
)

cache_hit_rate = Gauge(
    'cache_hit_rate',
    'Cache hit rate (0-1)'
)

cache_memory_used_bytes = Gauge(
    'cache_memory_used_bytes',
    'Redis memory usage in bytes'
)

cache_keys_total = Gauge(
    'cache_keys_total',
    'Total number of keys in cache'
)

cache_evictions_total = Counter(
    'cache_evictions_total',
    'Total cache key evictions'
)

# ==============================================================================
# STORAGE/S3 METRICS
# ==============================================================================

s3_operations_total = Counter(
    's3_operations_total',
    'Total S3/MinIO operations',
    ['operation', 'bucket', 'status']
)

s3_operation_duration_seconds = Histogram(
    's3_operation_duration_seconds',
    'S3 operation duration in seconds',
    ['operation', 'bucket'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0]
)

s3_bytes_uploaded_total = Counter(
    's3_bytes_uploaded_total',
    'Total bytes uploaded to S3',
    ['bucket']
)

s3_bytes_downloaded_total = Counter(
    's3_bytes_downloaded_total',
    'Total bytes downloaded from S3',
    ['bucket']
)

s3_bucket_size_bytes = Gauge(
    's3_bucket_size_bytes',
    'S3 bucket size in bytes',
    ['bucket']
)

s3_bucket_objects_total = Gauge(
    's3_bucket_objects_total',
    'Total objects in S3 bucket',
    ['bucket']
)

# ==============================================================================
# SYSTEM METRICS
# ==============================================================================

system_cpu_usage_percent = Gauge(
    'system_cpu_usage_percent',
    'System CPU usage percentage',
    ['cpu']
)

system_memory_used_bytes = Gauge(
    'system_memory_used_bytes',
    'System memory used in bytes'
)

system_memory_total_bytes = Gauge(
    'system_memory_total_bytes',
    'Total system memory in bytes'
)

system_disk_used_bytes = Gauge(
    'system_disk_used_bytes',
    'Disk space used in bytes',
    ['mount_point']
)

system_disk_total_bytes = Gauge(
    'system_disk_total_bytes',
    'Total disk space in bytes',
    ['mount_point']
)

system_network_bytes_sent_total = Counter(
    'system_network_bytes_sent_total',
    'Total network bytes sent',
    ['interface']
)

system_network_bytes_received_total = Counter(
    'system_network_bytes_received_total',
    'Total network bytes received',
    ['interface']
)

# ==============================================================================
# BUSINESS METRICS
# ==============================================================================

documents_uploaded_total = Counter(
    'documents_uploaded_total',
    'Total documents uploaded',
    ['document_type', 'user_tier']
)

documents_processed_total = Counter(
    'documents_processed_total',
    'Total documents successfully processed',
    ['document_type']
)

documents_failed_total = Counter(
    'documents_failed_total',
    'Total documents that failed processing',
    ['document_type', 'failure_reason']
)

active_users = Gauge(
    'active_users',
    'Number of active users in the last N minutes',
    ['time_window']
)

api_keys_active = Gauge(
    'api_keys_active',
    'Number of active API keys'
)

revenue_generated_total = Counter(
    'revenue_generated_total',
    'Total revenue generated',
    ['currency', 'plan_tier']
)

# ==============================================================================
# APPLICATION INFO
# ==============================================================================

app_info = Info(
    'ablage_system',
    'Application information'
)
app_info.info({
    'version': '1.0.0',
    'environment': 'production',
    'python_version': '3.11.5',
    'build_date': '2025-01-15'
})


# ==============================================================================
# METRIC COLLECTION FUNCTIONS
# ==============================================================================

def collect_system_metrics():
    """Collect system-level metrics (CPU, memory, disk, network)"""

    # CPU usage per core
    cpu_percent = psutil.cpu_percent(interval=1, percpu=True)
    for i, percent in enumerate(cpu_percent):
        system_cpu_usage_percent.labels(cpu=f"cpu{i}").set(percent)

    # Memory
    mem = psutil.virtual_memory()
    system_memory_used_bytes.set(mem.used)
    system_memory_total_bytes.set(mem.total)

    # Disk
    for partition in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(partition.mountpoint)
            system_disk_used_bytes.labels(mount_point=partition.mountpoint).set(usage.used)
            system_disk_total_bytes.labels(mount_point=partition.mountpoint).set(usage.total)
        except PermissionError:
            continue

    # Network
    net_io = psutil.net_io_counters(pernic=True)
    for interface, counters in net_io.items():
        system_network_bytes_sent_total.labels(interface=interface).inc(counters.bytes_sent)
        system_network_bytes_received_total.labels(interface=interface).inc(counters.bytes_recv)


def collect_gpu_metrics():
    """Collect GPU metrics using GPUtil"""
    try:
        gpus = GPUtil.getGPUs()
        for gpu in gpus:
            labels = {'gpu_id': str(gpu.id), 'gpu_name': gpu.name}

            gpu_memory_used_bytes.labels(**labels).set(gpu.memoryUsed * 1024 * 1024)
            gpu_memory_total_bytes.labels(**labels).set(gpu.memoryTotal * 1024 * 1024)
            gpu_utilization_percent.labels(**labels).set(gpu.load * 100)
            gpu_temperature_celsius.labels(**labels).set(gpu.temperature)

            # Note: Power draw requires nvidia-smi or pynvml
            # gpu_power_draw_watts.labels(**labels).set(gpu.powerDraw)
    except Exception as e:
        print(f"Error collecting GPU metrics: {e}")


def collect_db_metrics(db_session):
    """Collect database metrics"""
    from sqlalchemy import text

    # Connection pool stats
    pool = db_session.bind.pool
    db_connections_active.set(pool.checkedout())
    db_connections_idle.set(pool.size() - pool.checkedout())
    db_connections_max.set(pool.size())

    # Database size
    result = db_session.execute(text(
        "SELECT pg_database_size(current_database())"
    ))
    db_size_bytes.labels(database='ablage_system').set(result.scalar())

    # Table row counts
    tables = ['documents', 'ocr_results', 'users', 'processing_jobs']
    for table in tables:
        result = db_session.execute(text(f"SELECT COUNT(*) FROM {table}"))
        db_table_rows.labels(table=table).set(result.scalar())


def collect_redis_metrics(redis_client):
    """Collect Redis cache metrics"""
    info = redis_client.info('stats')

    # Hit rate calculation
    hits = info.get('keyspace_hits', 0)
    misses = info.get('keyspace_misses', 0)
    total = hits + misses
    hit_rate = hits / total if total > 0 else 0
    cache_hit_rate.set(hit_rate)

    # Memory usage
    memory_info = redis_client.info('memory')
    cache_memory_used_bytes.set(memory_info.get('used_memory', 0))

    # Key count
    db_info = redis_client.info('keyspace')
    total_keys = sum(
        db_info.get(f'db{i}', {}).get('keys', 0)
        for i in range(16)
    )
    cache_keys_total.set(total_keys)

    # Evictions
    cache_evictions_total.inc(info.get('evicted_keys', 0))


def collect_celery_metrics(app):
    """Collect Celery queue metrics"""
    from celery import current_app

    inspect = current_app.control.inspect()

    # Active workers
    active = inspect.active()
    if active:
        celery_workers_active.set(len(active))

    # Queue depths
    reserved = inspect.reserved()
    if reserved:
        for worker, tasks in reserved.items():
            for task in tasks:
                queue_depth.labels(
                    queue_name=task['delivery_info']['routing_key'],
                    priority=task.get('priority', 5)
                ).inc()


# ==============================================================================
# METRICS ENDPOINT
# ==============================================================================

def metrics_endpoint():
    """
    Expose Prometheus metrics on /metrics endpoint.

    Usage:
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/metrics")
        async def metrics():
            return Response(
                content=metrics_endpoint(),
                media_type=CONTENT_TYPE_LATEST
            )
    """
    return generate_latest(REGISTRY)
```

---

## 🔧 Metric Collection Patterns

### HTTP Middleware Pattern

```python
# backend/middleware/metrics.py

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.metrics import (
    http_requests_total,
    http_request_duration_seconds,
    http_request_size_bytes,
    http_response_size_bytes,
    http_requests_in_progress
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Middleware to collect HTTP request/response metrics.

    Tracks:
    - Request count by method, endpoint, status
    - Request duration histogram
    - Request/response size
    - In-progress requests
    """

    async def dispatch(self, request: Request, call_next):
        # Get endpoint path (normalize IDs to avoid cardinality explosion)
        path = self._normalize_path(request.url.path)
        method = request.method

        # Track in-progress requests
        http_requests_in_progress.labels(method=method, endpoint=path).inc()

        # Measure request size
        request_size = int(request.headers.get('content-length', 0))
        http_request_size_bytes.labels(method=method, endpoint=path).observe(request_size)

        # Start timer
        start_time = time.time()

        try:
            # Process request
            response = await call_next(request)
            status = response.status_code

            # Measure response size
            response_size = int(response.headers.get('content-length', 0))
            http_response_size_bytes.labels(method=method, endpoint=path).observe(response_size)

        except Exception as e:
            # Track 500 errors
            status = 500
            raise

        finally:
            # Record metrics
            duration = time.time() - start_time

            http_requests_total.labels(
                method=method,
                endpoint=path,
                status=status
            ).inc()

            http_request_duration_seconds.labels(
                method=method,
                endpoint=path
            ).observe(duration)

            http_requests_in_progress.labels(method=method, endpoint=path).dec()

        return response

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path to avoid cardinality explosion.

        Examples:
            /api/documents/12345 -> /api/documents/{id}
            /api/users/abc-def-ghi -> /api/users/{id}
        """
        import re

        # Replace UUIDs
        path = re.sub(
            r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            '/{id}',
            path,
            flags=re.IGNORECASE
        )

        # Replace numeric IDs
        path = re.sub(r'/\d+', '/{id}', path)

        return path


# Register middleware
from fastapi import FastAPI

app = FastAPI()
app.add_middleware(MetricsMiddleware)
```

### Decorator Pattern

```python
# backend/decorators/metrics.py

import time
import functools
from backend.core.metrics import (
    ocr_processing_duration_seconds,
    ocr_requests_total,
    ocr_confidence_score,
    db_query_duration_seconds,
    db_queries_total
)


def track_ocr_metrics(backend: str):
    """
    Decorator to track OCR processing metrics.

    Usage:
        @track_ocr_metrics(backend="deepseek")
        async def process_document(doc_id: str):
            # OCR processing logic
            return result
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()

            # Extract document type from kwargs
            doc_type = kwargs.get('document_type', 'unknown')
            complexity = kwargs.get('complexity', 'unknown')

            try:
                # Execute function
                result = await func(*args, **kwargs)

                # Track success
                ocr_requests_total.labels(
                    backend=backend,
                    document_type=doc_type,
                    status='success'
                ).inc()

                # Track confidence score
                if hasattr(result, 'confidence'):
                    ocr_confidence_score.labels(
                        backend=backend,
                        document_type=doc_type
                    ).observe(result.confidence)

                return result

            except Exception as e:
                # Track failure
                ocr_requests_total.labels(
                    backend=backend,
                    document_type=doc_type,
                    status='failed'
                ).inc()
                raise

            finally:
                # Track duration
                duration = time.time() - start_time
                ocr_processing_duration_seconds.labels(
                    backend=backend,
                    document_type=doc_type,
                    complexity=complexity
                ).observe(duration)

        return wrapper
    return decorator


def track_db_query(query_type: str, table: str):
    """
    Decorator to track database query metrics.

    Usage:
        @track_db_query(query_type="SELECT", table="documents")
        def get_document(doc_id: str):
            return db.query(...).first()
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = func(*args, **kwargs)

                db_queries_total.labels(
                    query_type=query_type,
                    status='success'
                ).inc()

                return result

            except Exception:
                db_queries_total.labels(
                    query_type=query_type,
                    status='failed'
                ).inc()
                raise

            finally:
                duration = time.time() - start_time
                db_query_duration_seconds.labels(
                    query_type=query_type,
                    table=table
                ).observe(duration)

        return wrapper
    return decorator


# Usage example
@track_ocr_metrics(backend="deepseek")
async def process_with_deepseek(document_path: str, document_type: str, complexity: str):
    """Process document with DeepSeek backend"""
    # ... OCR logic ...
    return OCRResult(text="...", confidence=0.95)
```

### Context Manager Pattern

```python
# backend/context/metrics.py

import time
from contextlib import contextmanager
from backend.core.metrics import (
    s3_operations_total,
    s3_operation_duration_seconds
)


@contextmanager
def track_s3_operation(operation: str, bucket: str):
    """
    Context manager to track S3 operation metrics.

    Usage:
        with track_s3_operation(operation="upload", bucket="documents"):
            s3_client.upload_file(file_path, bucket, key)
    """
    start_time = time.time()

    try:
        yield

        # Success
        s3_operations_total.labels(
            operation=operation,
            bucket=bucket,
            status='success'
        ).inc()

    except Exception as e:
        # Failure
        s3_operations_total.labels(
            operation=operation,
            bucket=bucket,
            status='failed'
        ).inc()
        raise

    finally:
        # Duration
        duration = time.time() - start_time
        s3_operation_duration_seconds.labels(
            operation=operation,
            bucket=bucket
        ).observe(duration)


# Usage example
from backend.context.metrics import track_s3_operation

async def upload_document(file_path: str, doc_id: str):
    with track_s3_operation(operation="upload", bucket="original-documents"):
        await s3_client.upload_file(
            file_path,
            "original-documents",
            f"{doc_id}.pdf"
        )
```

### Celery Task Metrics

```python
# backend/tasks/metrics.py

from celery import Task
from celery.signals import task_prerun, task_postrun, task_failure, task_retry
from backend.core.metrics import (
    celery_tasks_total,
    celery_task_retries_total,
    queue_processing_time_seconds
)
import time


class MetricsTask(Task):
    """
    Base Celery task class that automatically tracks metrics.

    Usage:
        @celery_app.task(base=MetricsTask, bind=True)
        def process_document(self, doc_id: str):
            # Task logic
            pass
    """

    def __call__(self, *args, **kwargs):
        # Track start time
        self.start_time = time.time()

        return super().__call__(*args, **kwargs)


@task_prerun.connect
def track_task_prerun(sender=None, task_id=None, task=None, **kwargs):
    """Track task start"""
    task.start_time = time.time()


@task_postrun.connect
def track_task_postrun(sender=None, task_id=None, task=None, state=None, **kwargs):
    """Track task completion"""
    duration = time.time() - getattr(task, 'start_time', time.time())

    celery_tasks_total.labels(
        task_name=sender.name,
        status='success'
    ).inc()

    queue_processing_time_seconds.labels(
        queue_name=sender.queue or 'celery',
        task_name=sender.name
    ).observe(duration)


@task_failure.connect
def track_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Track task failure"""
    celery_tasks_total.labels(
        task_name=sender.name,
        status='failed'
    ).inc()


@task_retry.connect
def track_task_retry(sender=None, reason=None, **kwargs):
    """Track task retry"""
    celery_task_retries_total.labels(
        task_name=sender.name,
        retry_reason=str(reason)
    ).inc()
```

---

## 🎨 Grafana Dashboards

### Complete System Overview Dashboard

```json
{
  "dashboard": {
    "id": null,
    "uid": "ablage-overview",
    "title": "Ablage System - Overview",
    "tags": ["ablage", "overview"],
    "timezone": "browser",
    "schemaVersion": 36,
    "version": 1,
    "refresh": "10s",
    "time": {
      "from": "now-1h",
      "to": "now"
    },
    "timepicker": {
      "refresh_intervals": ["5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h"]
    },
    "panels": [
      {
        "id": 1,
        "type": "stat",
        "title": "Request Rate",
        "gridPos": {
          "x": 0,
          "y": 0,
          "w": 6,
          "h": 4
        },
        "targets": [
          {
            "expr": "sum(rate(http_requests_total[5m]))",
            "legendFormat": "req/s",
            "refId": "A"
          }
        ],
        "options": {
          "reduceOptions": {
            "values": false,
            "calcs": ["lastNotNull"]
          },
          "orientation": "auto",
          "textMode": "auto",
          "colorMode": "value",
          "graphMode": "area"
        },
        "fieldConfig": {
          "defaults": {
            "unit": "reqps",
            "decimals": 2,
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"value": null, "color": "green"},
                {"value": 50, "color": "yellow"},
                {"value": 100, "color": "red"}
              ]
            }
          }
        }
      },
      {
        "id": 2,
        "type": "stat",
        "title": "Error Rate",
        "gridPos": {
          "x": 6,
          "y": 0,
          "w": 6,
          "h": 4
        },
        "targets": [
          {
            "expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m])) * 100",
            "legendFormat": "%",
            "refId": "A"
          }
        ],
        "options": {
          "reduceOptions": {
            "values": false,
            "calcs": ["lastNotNull"]
          },
          "textMode": "auto",
          "colorMode": "value"
        },
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "decimals": 2,
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"value": null, "color": "green"},
                {"value": 1, "color": "yellow"},
                {"value": 5, "color": "red"}
              ]
            }
          }
        }
      },
      {
        "id": 3,
        "type": "stat",
        "title": "GPU Utilization",
        "gridPos": {
          "x": 12,
          "y": 0,
          "w": 6,
          "h": 4
        },
        "targets": [
          {
            "expr": "avg(gpu_utilization_percent)",
            "legendFormat": "%",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "decimals": 1,
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"value": null, "color": "blue"},
                {"value": 50, "color": "green"},
                {"value": 80, "color": "yellow"},
                {"value": 95, "color": "red"}
              ]
            }
          }
        }
      },
      {
        "id": 4,
        "type": "stat",
        "title": "Queue Depth",
        "gridPos": {
          "x": 18,
          "y": 0,
          "w": 6,
          "h": 4
        },
        "targets": [
          {
            "expr": "sum(queue_depth)",
            "legendFormat": "jobs",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "short",
            "decimals": 0,
            "thresholds": {
              "mode": "absolute",
              "steps": [
                {"value": null, "color": "green"},
                {"value": 100, "color": "yellow"},
                {"value": 500, "color": "orange"},
                {"value": 1000, "color": "red"}
              ]
            }
          }
        }
      },
      {
        "id": 5,
        "type": "graph",
        "title": "Request Rate by Endpoint",
        "gridPos": {
          "x": 0,
          "y": 4,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "sum(rate(http_requests_total[5m])) by (endpoint)",
            "legendFormat": "{{endpoint}}",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "reqps",
            "label": "Requests/sec"
          },
          {
            "format": "short"
          }
        ],
        "lines": true,
        "fill": 1,
        "linewidth": 2,
        "legend": {
          "show": true,
          "values": true,
          "current": true,
          "max": true,
          "alignAsTable": true
        }
      },
      {
        "id": 6,
        "type": "graph",
        "title": "Response Time (P95, P99)",
        "gridPos": {
          "x": 12,
          "y": 4,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))",
            "legendFormat": "{{endpoint}} p95",
            "refId": "A"
          },
          {
            "expr": "histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))",
            "legendFormat": "{{endpoint}} p99",
            "refId": "B"
          }
        ],
        "yaxes": [
          {
            "format": "s",
            "label": "Duration"
          }
        ],
        "lines": true,
        "fill": 0,
        "linewidth": 2
      },
      {
        "id": 7,
        "type": "heatmap",
        "title": "Request Duration Heatmap",
        "gridPos": {
          "x": 0,
          "y": 12,
          "w": 24,
          "h": 8
        },
        "targets": [
          {
            "expr": "sum(increase(http_request_duration_seconds_bucket[1m])) by (le)",
            "format": "heatmap",
            "refId": "A"
          }
        ],
        "heatmap": {},
        "yAxis": {
          "format": "s",
          "decimals": 2
        },
        "cards": {
          "cardPadding": 2
        },
        "color": {
          "mode": "spectrum",
          "colorScheme": "interpolateSpectral",
          "exponent": 0.5
        }
      },
      {
        "id": 8,
        "type": "table",
        "title": "Top Slow Endpoints",
        "gridPos": {
          "x": 0,
          "y": 20,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "topk(10, histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint)))",
            "format": "table",
            "instant": true,
            "refId": "A"
          }
        ],
        "transformations": [
          {
            "id": "organize",
            "options": {
              "excludeByName": {},
              "indexByName": {},
              "renameByName": {
                "Value": "P95 Duration (s)",
                "endpoint": "Endpoint"
              }
            }
          }
        ]
      },
      {
        "id": 9,
        "type": "table",
        "title": "Error Breakdown",
        "gridPos": {
          "x": 12,
          "y": 20,
          "w": 12,
          "h": 8
        },
        "targets": [
          {
            "expr": "sum(rate(http_requests_total{status=~\"[45]..\"}[5m])) by (endpoint, status)",
            "format": "table",
            "instant": true,
            "refId": "A"
          }
        ]
      }
    ]
  }
}
```

### OCR Processing Dashboard

```json
{
  "dashboard": {
    "uid": "ablage-ocr",
    "title": "Ablage System - OCR Processing",
    "tags": ["ablage", "ocr"],
    "panels": [
      {
        "id": 1,
        "type": "stat",
        "title": "Total Documents Processed (24h)",
        "gridPos": {"x": 0, "y": 0, "w": 8, "h": 4},
        "targets": [
          {
            "expr": "sum(increase(documents_processed_total[24h]))",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "short",
            "decimals": 0,
            "thresholds": {
              "steps": [
                {"value": null, "color": "blue"},
                {"value": 1000, "color": "green"},
                {"value": 10000, "color": "yellow"}
              ]
            }
          }
        }
      },
      {
        "id": 2,
        "type": "stat",
        "title": "Processing Success Rate",
        "gridPos": {"x": 8, "y": 0, "w": 8, "h": 4},
        "targets": [
          {
            "expr": "sum(rate(ocr_requests_total{status=\"success\"}[5m])) / sum(rate(ocr_requests_total[5m])) * 100",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "decimals": 2,
            "thresholds": {
              "steps": [
                {"value": null, "color": "red"},
                {"value": 90, "color": "yellow"},
                {"value": 95, "color": "green"}
              ]
            }
          }
        }
      },
      {
        "id": 3,
        "type": "stat",
        "title": "Average Confidence Score",
        "gridPos": {"x": 16, "y": 0, "w": 8, "h": 4},
        "targets": [
          {
            "expr": "avg(ocr_confidence_score)",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percentunit",
            "decimals": 3,
            "min": 0,
            "max": 1,
            "thresholds": {
              "steps": [
                {"value": null, "color": "red"},
                {"value": 0.85, "color": "yellow"},
                {"value": 0.95, "color": "green"}
              ]
            }
          }
        }
      },
      {
        "id": 4,
        "type": "graph",
        "title": "Processing Time by Backend",
        "gridPos": {"x": 0, "y": 4, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "histogram_quantile(0.50, sum(rate(ocr_processing_duration_seconds_bucket[5m])) by (le, backend))",
            "legendFormat": "{{backend}} p50",
            "refId": "A"
          },
          {
            "expr": "histogram_quantile(0.95, sum(rate(ocr_processing_duration_seconds_bucket[5m])) by (le, backend))",
            "legendFormat": "{{backend}} p95",
            "refId": "B"
          },
          {
            "expr": "histogram_quantile(0.99, sum(rate(ocr_processing_duration_seconds_bucket[5m])) by (le, backend))",
            "legendFormat": "{{backend}} p99",
            "refId": "C"
          }
        ],
        "yaxes": [
          {
            "format": "s",
            "label": "Duration",
            "logBase": 1
          }
        ],
        "legend": {
          "show": true,
          "alignAsTable": true,
          "values": true,
          "current": true,
          "avg": true,
          "max": true
        }
      },
      {
        "id": 5,
        "type": "graph",
        "title": "Request Rate by Backend",
        "gridPos": {"x": 12, "y": 4, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "sum(rate(ocr_requests_total[5m])) by (backend)",
            "legendFormat": "{{backend}}",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "reqps",
            "label": "Requests/sec"
          }
        ],
        "stack": true,
        "fill": 5
      },
      {
        "id": 6,
        "type": "piechart",
        "title": "Backend Distribution",
        "gridPos": {"x": 0, "y": 12, "w": 8, "h": 8},
        "targets": [
          {
            "expr": "sum(increase(ocr_requests_total[1h])) by (backend)",
            "legendFormat": "{{backend}}",
            "refId": "A"
          }
        ],
        "options": {
          "pieType": "pie",
          "displayLabels": ["name", "percent"],
          "legend": {
            "displayMode": "table",
            "placement": "right",
            "values": ["value", "percent"]
          }
        }
      },
      {
        "id": 7,
        "type": "bargauge",
        "title": "Confidence Score Distribution",
        "gridPos": {"x": 8, "y": 12, "w": 8, "h": 8},
        "targets": [
          {
            "expr": "sum(rate(ocr_confidence_score_bucket[5m])) by (le, backend)",
            "legendFormat": "{{backend}} - {{le}}",
            "refId": "A"
          }
        ],
        "options": {
          "orientation": "horizontal",
          "displayMode": "gradient",
          "showUnfilled": true
        }
      },
      {
        "id": 8,
        "type": "stat",
        "title": "Backend Health Status",
        "gridPos": {"x": 16, "y": 12, "w": 8, "h": 8},
        "targets": [
          {
            "expr": "ocr_backend_health",
            "legendFormat": "{{backend}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {"value": 0, "text": "Unhealthy", "color": "red"},
              {"value": 1, "text": "Healthy", "color": "green"}
            ],
            "thresholds": {
              "steps": [
                {"value": 0, "color": "red"},
                {"value": 1, "color": "green"}
              ]
            }
          },
          "overrides": []
        },
        "options": {
          "colorMode": "background"
        }
      },
      {
        "id": 9,
        "type": "table",
        "title": "Processing Stats by Document Type",
        "gridPos": {"x": 0, "y": 20, "w": 24, "h": 8},
        "targets": [
          {
            "expr": "sum(rate(ocr_requests_total[1h])) by (document_type, backend, status)",
            "format": "table",
            "instant": true,
            "refId": "A"
          }
        ],
        "transformations": [
          {
            "id": "organize",
            "options": {
              "renameByName": {
                "document_type": "Document Type",
                "backend": "Backend",
                "status": "Status",
                "Value": "Rate (req/s)"
              }
            }
          }
        ]
      }
    ]
  }
}
```

### GPU Monitoring Dashboard

```json
{
  "dashboard": {
    "uid": "ablage-gpu",
    "title": "Ablage System - GPU Monitoring",
    "tags": ["ablage", "gpu", "hardware"],
    "panels": [
      {
        "id": 1,
        "type": "graph",
        "title": "GPU Memory Usage",
        "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "gpu_memory_used_bytes / gpu_memory_total_bytes * 100",
            "legendFormat": "{{gpu_name}} (GPU {{gpu_id}})",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "percent",
            "label": "Memory Usage %",
            "min": 0,
            "max": 100
          }
        ],
        "alert": {
          "name": "GPU Memory High",
          "conditions": [
            {
              "evaluator": {
                "params": [90],
                "type": "gt"
              },
              "operator": {
                "type": "and"
              },
              "query": {
                "params": ["A", "5m", "now"]
              },
              "reducer": {
                "params": [],
                "type": "avg"
              },
              "type": "query"
            }
          ],
          "executionErrorState": "alerting",
          "for": "5m",
          "frequency": "1m",
          "message": "GPU memory usage above 90%",
          "noDataState": "no_data",
          "notifications": []
        },
        "thresholds": [
          {
            "value": 80,
            "colorMode": "critical",
            "op": "gt",
            "fill": true,
            "line": true
          }
        ]
      },
      {
        "id": 2,
        "type": "graph",
        "title": "GPU Utilization",
        "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "gpu_utilization_percent",
            "legendFormat": "{{gpu_name}} (GPU {{gpu_id}})",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "percent",
            "label": "Utilization %",
            "min": 0,
            "max": 100
          }
        ]
      },
      {
        "id": 3,
        "type": "graph",
        "title": "GPU Temperature",
        "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "gpu_temperature_celsius",
            "legendFormat": "{{gpu_name}} (GPU {{gpu_id}})",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "celsius",
            "label": "Temperature",
            "min": 0,
            "max": 100
          }
        ],
        "thresholds": [
          {
            "value": 80,
            "colorMode": "critical",
            "op": "gt"
          }
        ]
      },
      {
        "id": 4,
        "type": "graph",
        "title": "GPU Power Draw",
        "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "gpu_power_draw_watts",
            "legendFormat": "{{gpu_name}} (GPU {{gpu_id}})",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "watt",
            "label": "Power (W)"
          }
        ]
      },
      {
        "id": 5,
        "type": "stat",
        "title": "Currently Loaded Models",
        "gridPos": {"x": 0, "y": 16, "w": 24, "h": 4},
        "targets": [
          {
            "expr": "gpu_model_loaded",
            "legendFormat": "GPU {{gpu_id}}: {{model_name}}",
            "refId": "A"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "mappings": [
              {"value": 0, "text": "Unloaded", "color": "gray"},
              {"value": 1, "text": "Loaded", "color": "green"}
            ]
          }
        },
        "options": {
          "colorMode": "background",
          "orientation": "horizontal"
        }
      }
    ]
  }
}
```

### Database Performance Dashboard

```json
{
  "dashboard": {
    "uid": "ablage-database",
    "title": "Ablage System - Database Performance",
    "tags": ["ablage", "database", "postgresql"],
    "panels": [
      {
        "id": 1,
        "type": "graph",
        "title": "Connection Pool Usage",
        "gridPos": {"x": 0, "y": 0, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "db_connections_active",
            "legendFormat": "Active",
            "refId": "A"
          },
          {
            "expr": "db_connections_idle",
            "legendFormat": "Idle",
            "refId": "B"
          },
          {
            "expr": "db_connections_max",
            "legendFormat": "Max",
            "refId": "C"
          }
        ],
        "yaxes": [
          {
            "format": "short",
            "label": "Connections"
          }
        ],
        "stack": true
      },
      {
        "id": 2,
        "type": "graph",
        "title": "Query Duration by Type",
        "gridPos": {"x": 12, "y": 0, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket[5m])) by (le, query_type))",
            "legendFormat": "{{query_type}} p95",
            "refId": "A"
          },
          {
            "expr": "histogram_quantile(0.99, sum(rate(db_query_duration_seconds_bucket[5m])) by (le, query_type))",
            "legendFormat": "{{query_type}} p99",
            "refId": "B"
          }
        ],
        "yaxes": [
          {
            "format": "s",
            "label": "Duration",
            "logBase": 10
          }
        ]
      },
      {
        "id": 3,
        "type": "graph",
        "title": "Query Rate by Type",
        "gridPos": {"x": 0, "y": 8, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "sum(rate(db_queries_total[5m])) by (query_type)",
            "legendFormat": "{{query_type}}",
            "refId": "A"
          }
        ],
        "yaxes": [
          {
            "format": "ops",
            "label": "Queries/sec"
          }
        ],
        "stack": true
      },
      {
        "id": 4,
        "type": "table",
        "title": "Table Sizes",
        "gridPos": {"x": 12, "y": 8, "w": 12, "h": 8},
        "targets": [
          {
            "expr": "db_table_rows",
            "format": "table",
            "instant": true,
            "refId": "A"
          }
        ],
        "transformations": [
          {
            "id": "organize",
            "options": {
              "renameByName": {
                "table": "Table",
                "Value": "Row Count"
              }
            }
          }
        ]
      }
    ]
  }
}
```

---

## 🚨 Alert Rules

### Complete Alerting Configuration

```yaml
# prometheus/alerts.yml

groups:
  # ==============================================================================
  # CRITICAL ALERTS - Immediate Response Required
  # ==============================================================================

  - name: critical_alerts
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
          ) * 100 > 5
        for: 5m
        labels:
          severity: critical
          component: api
          team: backend
        annotations:
          summary: "High HTTP error rate detected"
          description: "Error rate is {{ $value | humanizePercentage }} (threshold: 5%)"
          runbook_url: "https://docs.ablage-system.com/runbooks/high-error-rate"
          dashboard_url: "https://grafana.ablage-system.com/d/ablage-overview"

      - alert: APIDown
        expr: up{job="ablage-api"} == 0
        for: 1m
        labels:
          severity: critical
          component: api
          team: backend
        annotations:
          summary: "API server is down"
          description: "API server {{ $labels.instance }} is not responding"
          runbook_url: "https://docs.ablage-system.com/runbooks/api-down"

      - alert: GPUOutOfMemory
        expr: |
          (
            gpu_memory_used_bytes / gpu_memory_total_bytes
          ) * 100 > 95
        for: 2m
        labels:
          severity: critical
          component: gpu
          team: ml
        annotations:
          summary: "GPU memory critically low"
          description: "GPU {{ $labels.gpu_id }} ({{ $labels.gpu_name }}) memory usage at {{ $value | humanizePercentage }}"
          runbook_url: "https://docs.ablage-system.com/runbooks/gpu-oom"

      - alert: DatabaseConnectionPoolExhausted
        expr: |
          (
            db_connections_active / db_connections_max
          ) * 100 > 90
        for: 5m
        labels:
          severity: critical
          component: database
          team: backend
        annotations:
          summary: "Database connection pool near exhaustion"
          description: "{{ $value | humanizePercentage }} of connection pool in use"
          runbook_url: "https://docs.ablage-system.com/runbooks/db-pool-exhausted"

      - alert: DiskSpaceRunningOut
        expr: |
          (
            system_disk_used_bytes / system_disk_total_bytes
          ) * 100 > 90
        for: 10m
        labels:
          severity: critical
          component: infrastructure
          team: platform
        annotations:
          summary: "Disk space critically low"
          description: "Disk {{ $labels.mount_point }} at {{ $value | humanizePercentage }} capacity"
          runbook_url: "https://docs.ablage-system.com/runbooks/disk-space"

      - alert: CeleryWorkersDown
        expr: celery_workers_active == 0
        for: 2m
        labels:
          severity: critical
          component: workers
          team: backend
        annotations:
          summary: "No active Celery workers"
          description: "All Celery workers are down - no background processing"
          runbook_url: "https://docs.ablage-system.com/runbooks/celery-workers-down"

  # ==============================================================================
  # WARNING ALERTS - Attention Needed Soon
  # ==============================================================================

  - name: warning_alerts
    interval: 1m
    rules:
      - alert: HighResponseTime
        expr: |
          histogram_quantile(
            0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint)
          ) > 1.0
        for: 10m
        labels:
          severity: warning
          component: api
          team: backend
        annotations:
          summary: "High API response time"
          description: "Endpoint {{ $labels.endpoint }} P95 latency: {{ $value | humanizeDuration }}"
          runbook_url: "https://docs.ablage-system.com/runbooks/high-latency"

      - alert: QueueBacklog
        expr: sum(queue_depth) > 1000
        for: 10m
        labels:
          severity: warning
          component: workers
          team: backend
        annotations:
          summary: "Processing queue backing up"
          description: "{{ $value }} jobs in queue - may need more workers"
          runbook_url: "https://docs.ablage-system.com/runbooks/queue-backlog"

      - alert: LowCacheHitRate
        expr: cache_hit_rate < 0.7
        for: 15m
        labels:
          severity: warning
          component: cache
          team: backend
        annotations:
          summary: "Cache hit rate low"
          description: "Cache hit rate at {{ $value | humanizePercentage }} (target: >70%)"
          runbook_url: "https://docs.ablage-system.com/runbooks/low-cache-hit-rate"

      - alert: HighMemoryUsage
        expr: |
          (
            system_memory_used_bytes / system_memory_total_bytes
          ) * 100 > 85
        for: 5m
        labels:
          severity: warning
          component: infrastructure
          team: platform
        annotations:
          summary: "High memory usage"
          description: "Memory usage at {{ $value | humanizePercentage }}"
          runbook_url: "https://docs.ablage-system.com/runbooks/high-memory"

      - alert: GPUTemperatureHigh
        expr: gpu_temperature_celsius > 80
        for: 5m
        labels:
          severity: warning
          component: gpu
          team: ml
        annotations:
          summary: "GPU temperature elevated"
          description: "GPU {{ $labels.gpu_id }} temperature: {{ $value }}°C"
          runbook_url: "https://docs.ablage-system.com/runbooks/gpu-temperature"

      - alert: OCRProcessingSlowdown
        expr: |
          histogram_quantile(
            0.95,
            sum(rate(ocr_processing_duration_seconds_bucket[5m])) by (le, backend)
          ) > 10.0
        for: 10m
        labels:
          severity: warning
          component: ocr
          team: ml
        annotations:
          summary: "OCR processing slower than expected"
          description: "Backend {{ $labels.backend }} P95 processing time: {{ $value | humanizeDuration }}"
          runbook_url: "https://docs.ablage-system.com/runbooks/slow-ocr"

  # ==============================================================================
  # INFO ALERTS - Informational Only
  # ==============================================================================

  - name: info_alerts
    interval: 5m
    rules:
      - alert: HighRequestVolume
        expr: sum(rate(http_requests_total[5m])) > 100
        for: 15m
        labels:
          severity: info
          component: api
          team: backend
        annotations:
          summary: "High request volume"
          description: "Request rate: {{ $value | humanize }} req/s"

      - alert: ModelSwapOccurred
        expr: changes(gpu_model_loaded[5m]) > 0
        labels:
          severity: info
          component: gpu
          team: ml
        annotations:
          summary: "GPU model swap detected"
          description: "Model changed on GPU {{ $labels.gpu_id }}"

      - alert: LargeS3Upload
        expr: increase(s3_bytes_uploaded_total[1m]) > 1000000000
        labels:
          severity: info
          component: storage
          team: platform
        annotations:
          summary: "Large S3 upload detected"
          description: "{{ $value | humanize1024 }}B uploaded to {{ $labels.bucket }} in last minute"

  # ==============================================================================
  # SLO BURN RATE ALERTS
  # ==============================================================================

  - name: slo_alerts
    interval: 30s
    rules:
      # Fast burn rate (targeting 99.9% availability SLO)
      - alert: ErrorBudgetBurnRateFast
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[1h]))
            /
            sum(rate(http_requests_total[1h]))
          ) > (1 - 0.999) * 14.4
        for: 5m
        labels:
          severity: critical
          component: slo
          team: backend
        annotations:
          summary: "Fast error budget burn rate"
          description: "At current rate, monthly error budget will be exhausted in 2 days"
          runbook_url: "https://docs.ablage-system.com/runbooks/error-budget-burn"

      # Slow burn rate
      - alert: ErrorBudgetBurnRateSlow
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[6h]))
            /
            sum(rate(http_requests_total[6h]))
          ) > (1 - 0.999) * 3
        for: 30m
        labels:
          severity: warning
          component: slo
          team: backend
        annotations:
          summary: "Slow error budget burn rate"
          description: "Error budget burning faster than expected"
          runbook_url: "https://docs.ablage-system.com/runbooks/error-budget-burn"

      # Latency SLO violation (95% of requests < 500ms)
      - alert: LatencySLOViolation
        expr: |
          histogram_quantile(
            0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          ) > 0.5
        for: 10m
        labels:
          severity: warning
          component: slo
          team: backend
        annotations:
          summary: "Latency SLO violated"
          description: "P95 latency {{ $value | humanizeDuration }} exceeds 500ms target"
          runbook_url: "https://docs.ablage-system.com/runbooks/latency-slo"
```

### Alert Routing Configuration

```yaml
# alertmanager/alertmanager.yml

global:
  resolve_timeout: 5m
  slack_api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'
  pagerduty_url: 'https://events.pagerduty.com/v2/enqueue'

# Templates for notification formatting
templates:
  - '/etc/alertmanager/templates/*.tmpl'

# Route tree
route:
  receiver: 'default'
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h

  routes:
    # Critical alerts -> PagerDuty + Slack
    - match:
        severity: critical
      receiver: 'pagerduty-critical'
      continue: true

    - match:
        severity: critical
      receiver: 'slack-critical'
      group_wait: 0s

    # Warning alerts -> Slack only
    - match:
        severity: warning
      receiver: 'slack-warnings'
      group_wait: 5m

    # Info alerts -> Slack (throttled)
    - match:
        severity: info
      receiver: 'slack-info'
      group_wait: 30m
      repeat_interval: 24h

    # Database alerts -> Database team
    - match:
        component: database
      receiver: 'database-team'

    # GPU/ML alerts -> ML team
    - match_re:
        component: (gpu|ocr|ml)
      receiver: 'ml-team'

# Inhibition rules (suppress certain alerts when others are firing)
inhibit_rules:
  # Don't alert on high queue depth if workers are down
  - source_match:
      alertname: 'CeleryWorkersDown'
    target_match:
      alertname: 'QueueBacklog'
    equal: ['instance']

  # Don't alert on high error rate if API is down
  - source_match:
      alertname: 'APIDown'
    target_match:
      alertname: 'HighErrorRate'
    equal: ['instance']

  # Suppress warnings if critical alert firing
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']

# Receivers
receivers:
  - name: 'default'
    slack_configs:
      - channel: '#alerts-default'
        title: 'Alert: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
        severity: '{{ .GroupLabels.severity }}'
        description: '{{ .GroupLabels.alertname }}: {{ .CommonAnnotations.summary }}'
        details:
          firing: '{{ .Alerts.Firing | len }}'
          resolved: '{{ .Alerts.Resolved | len }}'
          num_alerts: '{{ .Alerts | len }}'

  - name: 'slack-critical'
    slack_configs:
      - channel: '#alerts-critical'
        color: 'danger'
        title: ':rotating_light: CRITICAL: {{ .GroupLabels.alertname }}'
        text: |
          {{ range .Alerts }}
          *Summary:* {{ .Annotations.summary }}
          *Description:* {{ .Annotations.description }}
          *Runbook:* {{ .Annotations.runbook_url }}
          *Dashboard:* {{ .Annotations.dashboard_url }}
          {{ end }}
        send_resolved: true

  - name: 'slack-warnings'
    slack_configs:
      - channel: '#alerts-warnings'
        color: 'warning'
        title: ':warning: Warning: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
        send_resolved: true

  - name: 'slack-info'
    slack_configs:
      - channel: '#alerts-info'
        color: 'good'
        title: 'ℹ️ Info: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'database-team'
    slack_configs:
      - channel: '#team-database'
        username: 'Database Alert Bot'
    email_configs:
      - to: 'database-team@ablage-system.com'
        from: 'alerts@ablage-system.com'
        smarthost: 'smtp.gmail.com:587'
        auth_username: 'alerts@ablage-system.com'
        auth_password: 'YOUR_PASSWORD'

  - name: 'ml-team'
    slack_configs:
      - channel: '#team-ml'
        username: 'ML Alert Bot'
```

---

## 📈 SLI/SLO Monitoring

### Service Level Objectives

```python
# backend/monitoring/slo.py

"""
Service Level Objectives (SLOs) for Ablage System.

SLOs define measurable targets for service reliability.
We use the four golden signals: latency, traffic, errors, saturation.
"""

from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime, timedelta


@dataclass
class SLO:
    """Service Level Objective definition"""
    name: str
    description: str
    target: float  # Target percentage (e.g., 0.999 for 99.9%)
    measurement_window: timedelta
    error_budget: float  # Calculated from target


# ==============================================================================
# AVAILABILITY SLOs
# ==============================================================================

AVAILABILITY_SLO = SLO(
    name="API Availability",
    description="Percentage of successful HTTP requests (non-5xx)",
    target=0.999,  # 99.9%
    measurement_window=timedelta(days=30),
    error_budget=0.001  # 0.1% = 43.2 minutes/month downtime
)

# PromQL for measuring availability:
# sum(rate(http_requests_total{status!~"5.."}[30d])) /
# sum(rate(http_requests_total[30d]))


# ==============================================================================
# LATENCY SLOs
# ==============================================================================

LATENCY_SLO_P95 = SLO(
    name="API Latency P95",
    description="95th percentile response time < 500ms",
    target=0.95,
    measurement_window=timedelta(days=7),
    error_budget=0.05
)

# PromQL for measuring P95 latency:
# histogram_quantile(0.95,
#   sum(rate(http_request_duration_seconds_bucket[7d])) by (le)
# ) < 0.5

LATENCY_SLO_P99 = SLO(
    name="API Latency P99",
    description="99th percentile response time < 2s",
    target=0.99,
    measurement_window=timedelta(days=7),
    error_budget=0.01
)


# ==============================================================================
# QUALITY SLOs
# ==============================================================================

OCR_QUALITY_SLO = SLO(
    name="OCR Confidence Score",
    description="Percentage of OCR results with >95% confidence",
    target=0.95,
    measurement_window=timedelta(days=7),
    error_budget=0.05
)

# PromQL for measuring OCR quality:
# sum(rate(ocr_confidence_score_bucket{le="0.95"}[7d])) /
# sum(rate(ocr_confidence_score_count[7d]))


# ==============================================================================
# ERROR BUDGET CALCULATION
# ==============================================================================

class ErrorBudgetCalculator:
    """Calculate and track error budget consumption"""

    def __init__(self, slo: SLO):
        self.slo = slo

    def calculate_budget_remaining(
        self,
        total_requests: int,
        failed_requests: int
    ) -> Dict:
        """
        Calculate remaining error budget.

        Returns:
            {
                'budget_remaining': float,  # 0.0 to 1.0
                'requests_remaining': int,
                'is_healthy': bool
            }
        """
        # Total allowed failures
        allowed_failures = total_requests * self.slo.error_budget

        # Remaining budget
        failures_remaining = allowed_failures - failed_requests
        budget_remaining = failures_remaining / allowed_failures if allowed_failures > 0 else 1.0

        return {
            'budget_remaining': max(0.0, budget_remaining),
            'requests_remaining': max(0, int(failures_remaining)),
            'is_healthy': budget_remaining > 0,
            'total_requests': total_requests,
            'failed_requests': failed_requests,
            'allowed_failures': int(allowed_failures)
        }

    def calculate_burn_rate(
        self,
        error_rate: float,
        window_hours: float = 1.0
    ) -> float:
        """
        Calculate error budget burn rate.

        Burn rate = (actual error rate) / (allowed error rate)

        Burn rate > 1 means consuming budget faster than sustainable.
        Burn rate < 1 means within budget.

        Args:
            error_rate: Current error rate (0.0 to 1.0)
            window_hours: Measurement window in hours

        Returns:
            Burn rate multiplier
        """
        # Calculate normalized error rate for the window
        window_fraction = window_hours / (self.slo.measurement_window.total_seconds() / 3600)
        allowed_error_rate = self.slo.error_budget * window_fraction

        if allowed_error_rate == 0:
            return float('inf') if error_rate > 0 else 0.0

        return error_rate / allowed_error_rate


# ==============================================================================
# PROMETHEUS RECORDING RULES FOR SLOs
# ==============================================================================

# prometheus/recording_rules.yml
"""
groups:
  - name: slo_recording_rules
    interval: 30s
    rules:
      # Availability SLI
      - record: sli:http_requests:availability
        expr: |
          sum(rate(http_requests_total{status!~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m]))

      # Latency SLI (P95)
      - record: sli:http_request_duration:p95
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          )

      # Latency SLI (P99)
      - record: sli:http_request_duration:p99
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          )

      # OCR Quality SLI
      - record: sli:ocr_confidence:high_quality_rate
        expr: |
          sum(rate(ocr_confidence_score_bucket{le="0.95"}[5m]))
          /
          sum(rate(ocr_confidence_score_count[5m]))

      # Error budget remaining (30-day window)
      - record: slo:error_budget:remaining:30d
        expr: |
          1 - (
            sum(increase(http_requests_total{status=~"5.."}[30d]))
            /
            (sum(increase(http_requests_total[30d])) * 0.001)
          )

      # Fast burn rate (1h window)
      - record: slo:error_budget:burn_rate:1h
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[1h]))
            /
            sum(rate(http_requests_total[1h]))
          ) / 0.001

      # Slow burn rate (6h window)
      - record: slo:error_budget:burn_rate:6h
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[6h]))
            /
            sum(rate(http_requests_total[6h]))
          ) / 0.001
"""
```

---

## 🔧 Prometheus Configuration

### Complete Prometheus Setup

```yaml
# prometheus/prometheus.yml

global:
  # How frequently to scrape targets
  scrape_interval: 15s

  # How frequently to evaluate rules
  evaluation_interval: 15s

  # Attach these labels to any time series or alerts
  external_labels:
    cluster: 'ablage-production'
    environment: 'production'
    region: 'eu-central-1'

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['localhost:9093']
      timeout: 10s

# Load rules from these files
rule_files:
  - '/etc/prometheus/rules/*.yml'
  - '/etc/prometheus/alerts/*.yml'
  - '/etc/prometheus/recording_rules/*.yml'

# Scrape configurations
scrape_configs:
  # ==============================================================================
  # ABLAGE SYSTEM COMPONENTS
  # ==============================================================================

  # FastAPI application
  - job_name: 'ablage-api'
    static_configs:
      - targets: ['localhost:8000']
        labels:
          component: 'api'
          team: 'backend'
    metrics_path: '/metrics'
    scrape_interval: 10s

  # Celery workers
  - job_name: 'ablage-workers'
    static_configs:
      - targets:
          - 'worker-1:9090'
          - 'worker-2:9090'
          - 'worker-3:9090'
        labels:
          component: 'workers'
          team: 'backend'
    metrics_path: '/metrics'

  # ==============================================================================
  # DATABASE EXPORTERS
  # ==============================================================================

  # PostgreSQL exporter
  - job_name: 'postgresql'
    static_configs:
      - targets: ['localhost:9187']
        labels:
          component: 'database'
          team: 'backend'
    metrics_path: '/metrics'

  # ==============================================================================
  # CACHE EXPORTERS
  # ==============================================================================

  # Redis exporter
  - job_name: 'redis'
    static_configs:
      - targets: ['localhost:9121']
        labels:
          component: 'cache'
          team: 'backend'
    metrics_path: '/metrics'

  # ==============================================================================
  # GPU MONITORING
  # ==============================================================================

  # NVIDIA GPU exporter (dcgm-exporter)
  - job_name: 'nvidia-gpu'
    static_configs:
      - targets: ['localhost:9400']
        labels:
          component: 'gpu'
          team: 'ml'
    metrics_path: '/metrics'

  # ==============================================================================
  # INFRASTRUCTURE MONITORING
  # ==============================================================================

  # Node exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
        labels:
          component: 'infrastructure'
          team: 'platform'
    metrics_path: '/metrics'

  # ==============================================================================
  # STORAGE MONITORING
  # ==============================================================================

  # MinIO/S3 exporter
  - job_name: 'minio'
    static_configs:
      - targets: ['localhost:9000']
        labels:
          component: 'storage'
          team: 'platform'
    metrics_path: '/minio/v2/metrics/cluster'
    scrape_interval: 30s

  # ==============================================================================
  # PROMETHEUS SELF-MONITORING
  # ==============================================================================

  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
        labels:
          component: 'monitoring'
          team: 'platform'

# Storage configuration
storage:
  tsdb:
    # Retention period
    retention.time: 30d

    # Retention size
    retention.size: 50GB

    # Data directory
    path: /prometheus/data

    # WAL compression
    wal_compression: true

# Remote write (for long-term storage)
remote_write:
  - url: 'https://prometheus-long-term-storage.ablage-system.com/api/v1/write'
    queue_config:
      capacity: 10000
      max_shards: 50
      min_shards: 1
      max_samples_per_send: 5000
      batch_send_deadline: 5s
      min_backoff: 30ms
      max_backoff: 100ms

# Remote read (for queries spanning > 30 days)
remote_read:
  - url: 'https://prometheus-long-term-storage.ablage-system.com/api/v1/read'
    read_recent: true
```

### Recording Rules for Performance

```yaml
# prometheus/recording_rules.yml

groups:
  - name: request_aggregations
    interval: 15s
    rules:
      # Request rate by endpoint (1m)
      - record: job:http_requests:rate1m
        expr: sum(rate(http_requests_total[1m])) by (job, endpoint)

      # Request rate by endpoint (5m)
      - record: job:http_requests:rate5m
        expr: sum(rate(http_requests_total[5m])) by (job, endpoint)

      # Error rate by endpoint
      - record: job:http_requests:error_rate5m
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m])) by (job, endpoint)
          /
          sum(rate(http_requests_total[5m])) by (job, endpoint)

  - name: latency_aggregations
    interval: 15s
    rules:
      # P50 latency
      - record: job:http_request_duration:p50
        expr: |
          histogram_quantile(0.50,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (job, endpoint, le)
          )

      # P95 latency
      - record: job:http_request_duration:p95
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (job, endpoint, le)
          )

      # P99 latency
      - record: job:http_request_duration:p99
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (job, endpoint, le)
          )

  - name: ocr_aggregations
    interval: 30s
    rules:
      # OCR throughput
      - record: backend:ocr_pages:rate5m
        expr: sum(rate(ocr_pages_processed_total[5m])) by (backend)

      # Average OCR confidence
      - record: backend:ocr_confidence:avg
        expr: avg(ocr_confidence_score) by (backend)

  - name: resource_utilization
    interval: 30s
    rules:
      # GPU memory utilization
      - record: gpu:memory:utilization
        expr: gpu_memory_used_bytes / gpu_memory_total_bytes

      # System memory utilization
      - record: instance:memory:utilization
        expr: system_memory_used_bytes / system_memory_total_bytes

      # Disk utilization
      - record: instance:disk:utilization
        expr: system_disk_used_bytes / system_disk_total_bytes
```

---

## 📊 Logging Integration

### Structured Logging Configuration

```python
# backend/core/logging_config.py

"""
Structured logging configuration using structlog.

Benefits:
- Machine-readable JSON logs
- Contextual information (request ID, user ID, etc.)
- Easy filtering and searching
- Integration with log aggregation systems
"""

import logging
import structlog
from structlog.processors import JSONRenderer
from datetime import datetime


def configure_logging():
    """Configure structured logging for the application"""

    structlog.configure(
        processors=[
            # Add log level
            structlog.stdlib.add_log_level,

            # Add logger name
            structlog.stdlib.add_logger_name,

            # Add timestamp
            structlog.processors.TimeStamper(fmt="iso"),

            # Add stack info for exceptions
            structlog.processors.StackInfoRenderer(),

            # Format exceptions
            structlog.processors.format_exc_info,

            # Add correlation ID from context
            structlog.contextvars.merge_contextvars,

            # Render as JSON
            JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Usage in application code
logger = structlog.get_logger()

# Simple log
logger.info("Document uploaded", document_id="doc_123", user_id="user_456")

# Log with exception
try:
    process_document()
except Exception as e:
    logger.error(
        "Document processing failed",
        document_id="doc_123",
        error=str(e),
        exc_info=True
    )

# Output:
# {
#   "event": "Document uploaded",
#   "document_id": "doc_123",
#   "user_id": "user_456",
#   "level": "info",
#   "timestamp": "2025-01-15T10:30:45.123456Z",
#   "logger": "backend.api.upload"
# }
```

### ELK Stack Configuration

```yaml
# filebeat/filebeat.yml

filebeat.inputs:
  # Application logs
  - type: log
    enabled: true
    paths:
      - /var/log/ablage-system/api/*.log
      - /var/log/ablage-system/workers/*.log

    # Parse JSON logs
    json.keys_under_root: true
    json.add_error_key: true
    json.message_key: event

    # Add metadata
    fields:
      service: ablage-system
      environment: production
    fields_under_root: true

    # Multiline handling for stack traces
    multiline.pattern: '^\s'
    multiline.match: after

# Processors
processors:
  # Add host metadata
  - add_host_metadata:
      when.not.contains.tags: forwarded

  # Add Docker metadata (if running in containers)
  - add_docker_metadata: ~

  # Add Kubernetes metadata (if running in K8s)
  - add_kubernetes_metadata: ~

# Output to Elasticsearch
output.elasticsearch:
  hosts: ["http://elasticsearch:9200"]
  index: "ablage-logs-%{+yyyy.MM.dd}"

  # Pipeline for additional processing
  pipeline: ablage-log-pipeline

  # Bulk settings
  bulk_max_size: 5000
  worker: 2

# Output to Logstash (alternative)
# output.logstash:
#   hosts: ["logstash:5044"]
#   ssl.enabled: true

# Logging
logging.level: info
logging.to_files: true
logging.files:
  path: /var/log/filebeat
  name: filebeat
  keepfiles: 7
  permissions: 0644
```

```yaml
# logstash/pipeline/ablage-logs.conf

input {
  beats {
    port => 5044
    ssl => true
    ssl_certificate => "/etc/logstash/certs/logstash.crt"
    ssl_key => "/etc/logstash/certs/logstash.key"
  }
}

filter {
  # Parse JSON if not already parsed
  if ![json_parsed] {
    json {
      source => "message"
      target => "parsed"
    }

    mutate {
      add_field => { "json_parsed" => true }
    }
  }

  # Extract timestamp
  date {
    match => [ "timestamp", "ISO8601" ]
    target => "@timestamp"
  }

  # Geo-IP lookup for client IPs
  if [client_ip] {
    geoip {
      source => "client_ip"
      target => "geoip"
    }
  }

  # Parse user agent
  if [user_agent] {
    useragent {
      source => "user_agent"
      target => "ua"
    }
  }

  # Add severity level mapping
  if [level] == "error" or [level] == "critical" {
    mutate {
      add_field => { "severity" => "high" }
    }
  } else if [level] == "warning" {
    mutate {
      add_field => { "severity" => "medium" }
    }
  } else {
    mutate {
      add_field => { "severity" => "low" }
    }
  }
}

output {
  elasticsearch {
    hosts => ["http://elasticsearch:9200"]
    index => "ablage-logs-%{+YYYY.MM.dd}"
    document_type => "_doc"
  }

  # Also output to stdout for debugging
  stdout {
    codec => rubydebug
  }
}
```

### Correlation IDs for Distributed Tracing

```python
# backend/middleware/correlation.py

import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
from contextvars import ContextVar

# Context variable for request ID
request_id_var: ContextVar[str] = ContextVar('request_id', default=None)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add correlation IDs to requests.

    Correlation IDs allow tracking a request across multiple services/components.
    """

    async def dispatch(self, request: Request, call_next):
        # Check if client provided a correlation ID
        correlation_id = request.headers.get('X-Correlation-ID')

        # Generate new ID if not provided
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store in context var
        request_id_var.set(correlation_id)

        # Bind to structlog context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path
        )

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers['X-Correlation-ID'] = correlation_id

        return response


# Usage in dependencies
from fastapi import Depends

async def get_correlation_id() -> str:
    """Dependency to get current correlation ID"""
    return request_id_var.get()


# Usage in route handlers
@router.post("/documents")
async def upload_document(
    correlation_id: str = Depends(get_correlation_id)
):
    logger.info(
        "Processing document upload",
        correlation_id=correlation_id
    )
    # ...
```

---

## 📱 Notification Channels

### Slack Integration

```python
# backend/notifications/slack.py

"""
Slack notification integration for alerts and events.
"""

import requests
import json
from typing import Optional, Dict, List
from enum import Enum


class SlackColor(str, Enum):
    """Slack attachment colors"""
    GOOD = "good"  # Green
    WARNING = "warning"  # Yellow
    DANGER = "danger"  # Red
    INFO = "#439FE0"  # Blue


class SlackNotifier:
    """Send notifications to Slack via webhooks"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_message(
        self,
        text: str,
        channel: Optional[str] = None,
        username: Optional[str] = "Ablage System",
        icon_emoji: Optional[str] = ":robot_face:"
    ) -> bool:
        """
        Send simple text message to Slack.

        Args:
            text: Message text (supports Markdown)
            channel: Override default channel (#alerts)
            username: Bot username
            icon_emoji: Bot icon

        Returns:
            True if successful
        """
        payload = {
            "text": text,
            "username": username,
            "icon_emoji": icon_emoji
        }

        if channel:
            payload["channel"] = channel

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to send Slack notification: {e}")
            return False

    def send_alert(
        self,
        title: str,
        message: str,
        severity: str = "info",
        fields: Optional[List[Dict]] = None,
        link_url: Optional[str] = None
    ) -> bool:
        """
        Send formatted alert to Slack.

        Args:
            title: Alert title
            message: Alert description
            severity: critical, warning, or info
            fields: Additional fields to display
            link_url: Link to dashboard/runbook

        Returns:
            True if successful
        """
        # Map severity to color
        color_map = {
            "critical": SlackColor.DANGER,
            "warning": SlackColor.WARNING,
            "info": SlackColor.INFO
        }
        color = color_map.get(severity, SlackColor.INFO)

        # Map severity to emoji
        emoji_map = {
            "critical": ":rotating_light:",
            "warning": ":warning:",
            "info": ":information_source:"
        }
        emoji = emoji_map.get(severity, ":bell:")

        # Build attachment
        attachment = {
            "color": color.value,
            "title": f"{emoji} {title}",
            "text": message,
            "footer": "Ablage System Monitoring",
            "ts": int(datetime.utcnow().timestamp())
        }

        if link_url:
            attachment["title_link"] = link_url

        if fields:
            attachment["fields"] = fields

        payload = {
            "username": "Alert Bot",
            "icon_emoji": ":bell:",
            "attachments": [attachment]
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"Failed to send Slack alert: {e}")
            return False


# Usage example
from backend.notifications.slack import SlackNotifier

notifier = SlackNotifier(webhook_url=os.getenv("SLACK_WEBHOOK_URL"))

# Send alert
notifier.send_alert(
    title="High Error Rate Detected",
    message="API error rate is 5.2% over the last 5 minutes",
    severity="critical",
    fields=[
        {"title": "Current Rate", "value": "5.2%", "short": True},
        {"title": "Threshold", "value": "1%", "short": True},
        {"title": "Endpoint", "value": "/api/ocr/process", "short": False}
    ],
    link_url="https://grafana.ablage-system.com/d/ablage-overview"
)
```

### PagerDuty Integration

```python
# backend/notifications/pagerduty.py

"""
PagerDuty integration for critical incidents.
"""

from pypd import Event, EventV2
import os
from typing import Dict, Optional
from datetime import datetime


class PagerDutyNotifier:
    """Send incidents to PagerDuty"""

    def __init__(self, integration_key: str):
        self.integration_key = integration_key

    def trigger_incident(
        self,
        title: str,
        description: str,
        severity: str = "critical",
        source: str = "ablage-system",
        custom_details: Optional[Dict] = None,
        dedup_key: Optional[str] = None
    ) -> str:
        """
        Trigger a PagerDuty incident.

        Args:
            title: Incident summary
            description: Detailed description
            severity: critical, error, warning, or info
            source: Source system name
            custom_details: Additional context
            dedup_key: Deduplication key (groups related incidents)

        Returns:
            Deduplication key for the incident
        """
        # Build event payload
        payload = {
            'summary': title,
            'severity': severity,
            'source': source,
            'timestamp': datetime.utcnow().isoformat(),
            'custom_details': custom_details or {}
        }

        # Add description to custom details
        payload['custom_details']['description'] = description

        try:
            response = EventV2.create(data={
                'routing_key': self.integration_key,
                'event_action': 'trigger',
                'dedup_key': dedup_key,
                'payload': payload
            })

            return response.get('dedup_key')

        except Exception as e:
            print(f"Failed to trigger PagerDuty incident: {e}")
            raise

    def acknowledge_incident(self, dedup_key: str):
        """Acknowledge an incident"""
        try:
            EventV2.create(data={
                'routing_key': self.integration_key,
                'event_action': 'acknowledge',
                'dedup_key': dedup_key
            })
        except Exception as e:
            print(f"Failed to acknowledge incident: {e}")

    def resolve_incident(self, dedup_key: str):
        """Resolve an incident"""
        try:
            EventV2.create(data={
                'routing_key': self.integration_key,
                'event_action': 'resolve',
                'dedup_key': dedup_key
            })
        except Exception as e:
            print(f"Failed to resolve incident: {e}")


# Usage example
from backend.notifications.pagerduty import PagerDutyNotifier

notifier = PagerDutyNotifier(integration_key=os.getenv("PAGERDUTY_KEY"))

# Trigger incident
dedup_key = notifier.trigger_incident(
    title="GPU Out of Memory",
    description="GPU 0 (RTX 4080) memory usage at 98%",
    severity="critical",
    custom_details={
        'gpu_id': '0',
        'gpu_name': 'RTX 4080',
        'memory_used': '15.6 GB',
        'memory_total': '16 GB',
        'current_model': 'deepseek-janus-pro'
    },
    dedup_key="gpu-oom-gpu0"
)
```

---

## 🎯 Best Practices

### Metric Naming Conventions

**Good metric names:**
```
http_requests_total  # Clear what it counts
http_request_duration_seconds  # Includes unit
ocr_processing_duration_seconds  # Descriptive
gpu_memory_used_bytes  # Specific unit
```

**Bad metric names:**
```
requests  # Too vague
duration  # Missing context
gpu_mem  # Abbreviated, unclear unit
ocr_time  # Missing unit
```

**Rules:**
1. Use snake_case
2. Include unit suffix (_seconds, _bytes, _total)
3. Be descriptive but concise
4. Group related metrics with common prefix

### Cardinality Management

**Cardinality** = number of unique label combinations

**Problem**: High cardinality causes memory bloat and slow queries.

**Examples:**

❌ **HIGH CARDINALITY (BAD)**
```python
# User ID as label -> millions of series
http_requests_total{user_id="user_12345", endpoint="/api/documents"}

# Document ID as label -> unbounded cardinality
ocr_processing_duration{document_id="doc_abc123"}
```

✅ **LOW CARDINALITY (GOOD)**
```python
# User tier instead of ID
http_requests_total{user_tier="premium", endpoint="/api/documents"}

# Document type instead of ID
ocr_processing_duration{document_type="invoice", backend="deepseek"}
```

**Guidelines:**
- Keep label cardinality < 100 values per label
- Avoid unbounded labels (IDs, timestamps, UUIDs)
- Use labels for dimensions you'll aggregate/filter on
- Store high-cardinality data in logs, not metrics

### Dashboard Design Principles

1. **Above the fold**: Most important metrics visible without scrolling
2. **Logical grouping**: Group related panels together
3. **Consistent time ranges**: Use dashboard-wide time picker
4. **Descriptive titles**: Clear, specific panel titles
5. **Show thresholds**: Visualize SLO targets on graphs
6. **Use appropriate visualizations**:
   - **Stat panels**: Single values (error rate, request count)
   - **Time series**: Trends over time
   - **Heatmaps**: Distribution visualization
   - **Tables**: Detailed breakdowns
7. **Add links**: Link to runbooks, related dashboards
8. **Include context**: Annotations for deployments/incidents

### Alert Design Guidelines

**Alert fatigue is REAL.** Bad alerts train people to ignore them.

✅ **Good Alerts:**
```yaml
# Actionable - Clear what to do
- alert: HighErrorRate
  expr: error_rate > 5%
  annotations:
    runbook_url: "https://..."  # Link to fix procedure

# Symptom-based - User-impacting
- alert: SlowResponses
  expr: p95_latency > 500ms

# Appropriate urgency - Critical = wakes you up
- alert: APIDown
  severity: critical  # Only for real emergencies
```

❌ **Bad Alerts:**
```yaml
# Too sensitive - Triggers on noise
- alert: AnyError
  expr: errors > 0

# Cause-based - Not user-impacting
- alert: HighCPU
  expr: cpu > 80%  # So what? Are users affected?

# Vague - No clear action
- alert: SomethingWrong
  description: "Check the system"
```

**Rules:**
1. Every alert must be actionable
2. Every alert must have a runbook
3. Critical alerts = immediate human intervention needed
4. Warning alerts = investigate soon
5. Use inhibition rules to prevent alert storms
6. Group related alerts
7. Test alerts in staging first

---

## 🔧 Troubleshooting

### Missing Metrics

**Problem**: Metrics not appearing in Prometheus

**Debugging:**
```bash
# Check if target is up
curl http://localhost:8000/metrics

# Check Prometheus targets page
http://localhost:9090/targets

# Check Prometheus logs
docker logs prometheus

# Verify metric format
curl http://localhost:8000/metrics | grep metric_name
```

**Common causes:**
- Incorrect scrape config
- Firewall blocking Prometheus
- Metric not registered
- Label cardinality too high

### High Memory Usage

**Problem**: Prometheus consuming excessive memory

**Causes:**
1. Too many time series (high cardinality)
2. Long retention period
3. Expensive queries

**Solutions:**
```yaml
# Reduce retention
--storage.tsdb.retention.time=15d

# Limit samples
--storage.tsdb.max-samples-per-chunk=120

# Use recording rules for expensive queries
groups:
  - name: expensive_queries
    interval: 1m
    rules:
      - record: precomputed:expensive_metric
        expr: sum(rate(metric[5m])) by (label)
```

### Slow Queries

**Problem**: Grafana dashboards loading slowly

**Solutions:**
1. Use recording rules
2. Reduce time range
3. Limit number of series
4. Use `rate()` instead of `increase()` for counters
5. Avoid regex label matchers

**Example optimization:**
```promql
# Slow - Regex matching
http_requests_total{endpoint=~"/api/.*"}

# Fast - Exact match
http_requests_total{endpoint="/api/documents"}

# Slow - Large time range
rate(http_requests_total[1h])

# Fast - Smaller window
rate(http_requests_total[5m])
```

---

## 📚 References

- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Grafana Documentation](https://grafana.com/docs/)
- [SRE Book - Monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)
- [RED Method](https://www.weave.works/blog/the-red-method-key-metrics-for-microservices-architecture/)
- [USE Method](http://www.brendangregg.com/usemethod.html)
- [Four Golden Signals](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals)
