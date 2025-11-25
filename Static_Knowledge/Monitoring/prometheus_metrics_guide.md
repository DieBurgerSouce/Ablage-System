# Prometheus Metrics Guide
**Ablage-System - Metriken und Monitoring mit Prometheus**

Version: 1.0
Last Updated: 2025-01-23
Owner: DevOps Team
Status: PRODUCTION

---

## Executive Summary

Comprehensive Prometheus metrics guide for Ablage-System, covering instrumentation, metric types, collection strategies, and alerting rules.

**Monitoring Coverage:**
- ✅ Application Metrics: API latency, throughput, errors
- ✅ Infrastructure Metrics: CPU, memory, disk, GPU
- ✅ Business Metrics: Document processing rate, user activity
- ✅ Custom Metrics: German text accuracy, OCR performance

---

## Table of Contents

1. [Prometheus Architecture](#prometheus-architecture)
2. [Metric Types](#metric-types)
3. [Application Instrumentation](#application-instrumentation)
4. [Infrastructure Metrics](#infrastructure-metrics)
5. [GPU Metrics](#gpu-metrics)
6. [Query Examples](#query-examples)
7. [Alerting Rules](#alerting-rules)

---

## Prometheus Architecture

### Data Flow

```
Application
  └─→ /metrics endpoint
       ↓
   Prometheus (scrape every 15s)
       ↓
   Time-Series Database
       ↓
   Grafana (visualization)
   AlertManager (alerting)
```

### Configuration

```yaml
# prometheus.yml

global:
  scrape_interval: 15s
  evaluation_interval: 15s
  external_labels:
    cluster: 'ablage-production'
    environment: 'production'

# Alertmanager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']

# Load alerting rules
rule_files:
  - 'alerts/*.yml'

# Scrape configurations
scrape_configs:
  # Ablage Backend API
  - job_name: 'ablage-backend'
    static_configs:
      - targets: ['backend:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s

  # Ablage Worker
  - job_name: 'ablage-worker'
    static_configs:
      - targets: ['worker:9090']
    metrics_path: '/metrics'

  # PostgreSQL
  - job_name: 'postgresql'
    static_configs:
      - targets: ['postgres-exporter:9187']

  # Redis
  - job_name: 'redis'
    static_configs:
      - targets: ['redis-exporter:9121']

  # MinIO
  - job_name: 'minio'
    static_configs:
      - targets: ['minio:9000']
    metrics_path: '/minio/v2/metrics/cluster'

  # NVIDIA GPU
  - job_name: 'nvidia-gpu'
    static_configs:
      - targets: ['nvidia-exporter:9835']

  # Node Exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']
```

---

## Metric Types

### 1. Counter

**Definition:** Monotonically increasing value (only goes up).

**Use Cases:** Request counts, error counts, tasks completed.

**Example:**

```python
from prometheus_client import Counter

# Define counter
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

# Increment counter
http_requests_total.labels(method='GET', endpoint='/api/v1/documents', status='200').inc()
```

**PromQL Queries:**

```promql
# Total requests in last 5 minutes
increase(http_requests_total[5m])

# Request rate per second
rate(http_requests_total[1m])

# Requests by status code
sum(rate(http_requests_total[5m])) by (status)
```

---

### 2. Gauge

**Definition:** Value that can go up or down.

**Use Cases:** Current CPU usage, memory usage, queue depth.

**Example:**

```python
from prometheus_client import Gauge

# Define gauge
gpu_memory_usage_bytes = Gauge(
    'gpu_memory_usage_bytes',
    'GPU memory usage in bytes',
    ['gpu_id']
)

# Set gauge value
gpu_memory_usage_bytes.labels(gpu_id='0').set(12_884_901_888)  # 12 GB
```

**PromQL Queries:**

```promql
# Current GPU memory usage
gpu_memory_usage_bytes{gpu_id="0"}

# GPU memory usage as percentage
(gpu_memory_usage_bytes / gpu_memory_total_bytes) * 100

# Average memory usage over 5 minutes
avg_over_time(gpu_memory_usage_bytes[5m])
```

---

### 3. Histogram

**Definition:** Samples observations and counts them in configurable buckets.

**Use Cases:** Request latencies, response sizes.

**Example:**

```python
from prometheus_client import Histogram

# Define histogram
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Observe value
with http_request_duration_seconds.labels(method='POST', endpoint='/api/v1/documents').time():
    # Process request
    process_document()
```

**PromQL Queries:**

```promql
# P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# P99 latency
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Average latency
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])
```

---

### 4. Summary

**Definition:** Similar to histogram but calculates quantiles on the client side.

**Use Cases:** When you need precise quantiles.

**Example:**

```python
from prometheus_client import Summary

ocr_processing_duration = Summary(
    'ocr_processing_duration_seconds',
    'OCR processing duration',
    ['backend']
)

# Observe value
with ocr_processing_duration.labels(backend='deepseek').time():
    result = ocr_engine.process(document)
```

---

## Application Instrumentation

### FastAPI Integration

```python
# app/monitoring/metrics.py

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import FastAPI, Response
import time

app = FastAPI()

# Define metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

ocr_documents_processed_total = Counter(
    'ocr_documents_processed_total',
    'Total documents processed',
    ['backend', 'status']
)

ocr_processing_duration_seconds = Histogram(
    'ocr_processing_duration_seconds',
    'OCR processing duration',
    ['backend'],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0)
)

gpu_memory_usage_bytes = Gauge(
    'gpu_memory_usage_bytes',
    'GPU memory usage',
    ['gpu_id']
)

document_queue_length = Gauge(
    'document_queue_length',
    'Number of documents in processing queue'
)

# Middleware for automatic instrumentation
@app.middleware("http")
async def prometheus_middleware(request, call_next):
    method = request.method
    path = request.url.path

    start_time = time.time()

    response = await call_next(request)

    duration = time.time() - start_time
    status = response.status_code

    # Record metrics
    http_requests_total.labels(method=method, endpoint=path, status=status).inc()
    http_request_duration_seconds.labels(method=method, endpoint=path).observe(duration)

    return response

# Metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

### OCR Service Instrumentation

```python
# app/services/ocr_service.py

import torch
from prometheus_client import Counter, Histogram, Gauge

# Metrics
ocr_documents_processed = Counter(
    'ocr_documents_processed_total',
    'Documents processed by OCR',
    ['backend', 'status']
)

ocr_processing_duration = Histogram(
    'ocr_processing_duration_seconds',
    'OCR processing time',
    ['backend']
)

ocr_accuracy_score = Gauge(
    'ocr_accuracy_score',
    'OCR accuracy score (0-1)',
    ['backend']
)

gpu_memory_usage = Gauge(
    'gpu_memory_usage_bytes',
    'GPU memory usage',
    ['gpu_id']
)

class OCRService:
    def __init__(self, backend: str = "deepseek"):
        self.backend = backend

    async def process(self, document: Document) -> OCRResult:
        """Process document with metrics instrumentation."""

        # Start timer
        with ocr_processing_duration.labels(backend=self.backend).time():
            try:
                # Update GPU metrics
                if torch.cuda.is_available():
                    memory_used = torch.cuda.memory_allocated(0)
                    gpu_memory_usage.labels(gpu_id='0').set(memory_used)

                # Process document
                result = await self._process_with_backend(document)

                # Record success
                ocr_documents_processed.labels(
                    backend=self.backend,
                    status='success'
                ).inc()

                # Record accuracy if available
                if result.confidence:
                    ocr_accuracy_score.labels(backend=self.backend).set(result.confidence)

                return result

            except Exception as e:
                # Record failure
                ocr_documents_processed.labels(
                    backend=self.backend,
                    status='error'
                ).inc()
                raise
```

### German Text Validation Metrics

```python
# app/utils/german_validator.py

from prometheus_client import Counter, Histogram

german_validation_total = Counter(
    'german_text_validation_total',
    'German text validations',
    ['validation_type', 'result']
)

umlaut_accuracy = Histogram(
    'umlaut_accuracy_ratio',
    'Umlaut detection accuracy',
    buckets=(0.9, 0.95, 0.98, 0.99, 1.0)
)

class GermanValidator:
    def validate_umlauts(self, text: str) -> bool:
        """Validate German umlauts with metrics."""

        try:
            result = self._check_umlauts(text)

            # Record validation
            german_validation_total.labels(
                validation_type='umlaut',
                result='valid' if result else 'invalid'
            ).inc()

            # Record accuracy
            accuracy = self._calculate_accuracy(text)
            umlaut_accuracy.observe(accuracy)

            return result

        except Exception as e:
            german_validation_total.labels(
                validation_type='umlaut',
                result='error'
            ).inc()
            raise
```

---

## Infrastructure Metrics

### System Metrics (Node Exporter)

```promql
# CPU usage per core
100 - (avg by (instance, cpu) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Total CPU usage
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory usage percentage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Disk usage percentage
(1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100

# Disk I/O
rate(node_disk_read_bytes_total[5m])
rate(node_disk_written_bytes_total[5m])

# Network traffic
rate(node_network_receive_bytes_total[5m])
rate(node_network_transmit_bytes_total[5m])
```

### PostgreSQL Metrics

```promql
# Active connections
pg_stat_activity_count{state="active"}

# Database size
pg_database_size_bytes{datname="ablage"}

# Query duration P95
histogram_quantile(0.95, rate(pg_stat_statements_mean_exec_time_bucket[5m]))

# Slow queries (>1 second)
pg_stat_activity_max_tx_duration{datname="ablage"} > 1

# Transaction rate
rate(pg_stat_database_xact_commit{datname="ablage"}[5m])

# Cache hit ratio
rate(pg_stat_database_blks_hit{datname="ablage"}[5m]) /
(rate(pg_stat_database_blks_hit{datname="ablage"}[5m]) + rate(pg_stat_database_blks_read{datname="ablage"}[5m]))
```

### Redis Metrics

```promql
# Memory usage
redis_memory_used_bytes

# Connected clients
redis_connected_clients

# Operations per second
rate(redis_commands_processed_total[1m])

# Keyspace hit ratio
rate(redis_keyspace_hits_total[5m]) /
(rate(redis_keyspace_hits_total[5m]) + rate(redis_keyspace_misses_total[5m]))

# Evicted keys
rate(redis_evicted_keys_total[5m])
```

---

## GPU Metrics

### NVIDIA GPU Metrics

```python
# nvidia_exporter configuration
# Collects metrics from nvidia-smi

# Key metrics:
# - nvidia_gpu_temperature_celsius
# - nvidia_gpu_utilization_percent
# - nvidia_gpu_memory_used_bytes
# - nvidia_gpu_memory_total_bytes
# - nvidia_gpu_power_usage_watts
```

```promql
# GPU utilization
nvidia_gpu_utilization_percent{gpu="0"}

# GPU memory usage percentage
(nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes) * 100

# GPU temperature
nvidia_gpu_temperature_celsius{gpu="0"}

# GPU power usage
nvidia_gpu_power_usage_watts{gpu="0"}

# GPU memory free
nvidia_gpu_memory_total_bytes - nvidia_gpu_memory_used_bytes
```

### Custom GPU Metrics

```python
# app/utils/gpu_manager.py

from prometheus_client import Gauge
import torch

gpu_compute_utilization = Gauge(
    'gpu_compute_utilization_percent',
    'GPU compute utilization',
    ['gpu_id']
)

gpu_memory_allocated = Gauge(
    'gpu_memory_allocated_bytes',
    'GPU memory allocated by PyTorch',
    ['gpu_id']
)

gpu_memory_cached = Gauge(
    'gpu_memory_cached_bytes',
    'GPU memory cached by PyTorch',
    ['gpu_id']
)

class GPUManager:
    def update_metrics(self):
        """Update GPU metrics."""
        if not torch.cuda.is_available():
            return

        gpu_id = 0

        # Memory metrics
        allocated = torch.cuda.memory_allocated(gpu_id)
        cached = torch.cuda.memory_reserved(gpu_id)

        gpu_memory_allocated.labels(gpu_id=str(gpu_id)).set(allocated)
        gpu_memory_cached.labels(gpu_id=str(gpu_id)).set(cached)

        # Utilization (requires nvidia-ml-py3)
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_id)
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_compute_utilization.labels(gpu_id=str(gpu_id)).set(utilization.gpu)
        except:
            pass
```

---

## Query Examples

### Application Performance

```promql
# Request rate (requests/second)
sum(rate(http_requests_total[1m]))

# Error rate percentage
(sum(rate(http_requests_total{status=~"5.."}[5m])) /
 sum(rate(http_requests_total[5m]))) * 100

# P95 API latency
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))

# Requests by endpoint
sum(rate(http_requests_total[5m])) by (endpoint)

# Success rate
(sum(rate(http_requests_total{status=~"2.."}[5m])) /
 sum(rate(http_requests_total[5m]))) * 100
```

### OCR Performance

```promql
# Documents processed per hour
sum(rate(ocr_documents_processed_total[1h])) * 3600

# OCR processing P95 latency
histogram_quantile(0.95,
  sum(rate(ocr_processing_duration_seconds_bucket[5m])) by (le, backend))

# Success rate by backend
sum(rate(ocr_documents_processed_total{status="success"}[5m])) by (backend) /
sum(rate(ocr_documents_processed_total[5m])) by (backend)

# Average OCR accuracy
avg(ocr_accuracy_score) by (backend)
```

### System Health

```promql
# High CPU usage (>80%)
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80

# High memory usage (>85%)
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 85

# Disk space low (<20% free)
(node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 20

# High GPU memory usage (>85%)
(nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes) * 100 > 85
```

---

## Alerting Rules

### alerts/application.yml

```yaml
groups:
  - name: application
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: |
          (sum(rate(http_requests_total{status=~"5.."}[5m])) /
           sum(rate(http_requests_total[5m]))) * 100 > 5
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }}% (threshold: 5%)"

      # Slow API responses
      - alert: HighAPILatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) > 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "API latency is high"
          description: "P95 latency is {{ $value }}s (threshold: 500ms)"

      # Low OCR throughput
      - alert: LowOCRThroughput
        expr: |
          sum(rate(ocr_documents_processed_total[1h])) * 3600 < 192
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "OCR throughput below target"
          description: "Processing {{ $value }} docs/hour (target: 192)"
```

### alerts/infrastructure.yml

```yaml
groups:
  - name: infrastructure
    interval: 30s
    rules:
      # High CPU usage
      - alert: HighCPUUsage
        expr: |
          100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 80
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High CPU usage"
          description: "CPU usage is {{ $value }}% (threshold: 80%)"

      # High memory usage
      - alert: HighMemoryUsage
        expr: |
          (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100 > 85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value }}% (threshold: 85%)"

      # Low disk space
      - alert: LowDiskSpace
        expr: |
          (node_filesystem_avail_bytes / node_filesystem_size_bytes) * 100 < 20
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Low disk space"
          description: "Only {{ $value }}% free (threshold: 20%)"
```

### alerts/gpu.yml

```yaml
groups:
  - name: gpu
    interval: 15s
    rules:
      # GPU not available
      - alert: GPUNotAvailable
        expr: |
          up{job="nvidia-gpu"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "GPU not responding"
          description: "GPU metrics endpoint is down"

      # High GPU memory usage
      - alert: HighGPUMemoryUsage
        expr: |
          (nvidia_gpu_memory_used_bytes / nvidia_gpu_memory_total_bytes) * 100 > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High GPU memory usage"
          description: "GPU memory usage is {{ $value }}% (threshold: 85%)"

      # GPU temperature high
      - alert: HighGPUTemperature
        expr: |
          nvidia_gpu_temperature_celsius > 80
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "GPU temperature high"
          description: "GPU temperature is {{ $value }}°C (threshold: 80°C)"
```

---

## Related Documents

- [Grafana Dashboards Guide](grafana_dashboards_guide.md)
- [Loki Logging Guide](loki_logging_guide.md)
- [Alerting Strategy](alerting_strategy_guide.md)
- [Performance Tuning](../Static_Knowledge/Optimization/performance_tuning_guide.md)

---

## Revision History

| Version | Date       | Author      | Changes                        |
|---------|------------|-------------|--------------------------------|
| 1.0     | 2025-01-23 | DevOps Team | Initial Prometheus metrics guide |

---

**"What gets measured gets managed." - Peter Drucker**

📊 **Metrics Excellence Achieved!**
