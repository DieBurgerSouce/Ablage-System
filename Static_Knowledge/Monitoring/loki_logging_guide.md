# Loki Logging Guide - Ablage-System

**Version:** 1.0
**Last Updated:** 2025-01-23
**Status:** Production-Ready
**Prerequisites:** [Prometheus Metrics Guide](prometheus_metrics_guide.md), [Grafana Dashboards Guide](grafana_dashboards_guide.md)

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Loki Installation](#loki-installation)
4. [Promtail Configuration](#promtail-configuration)
5. [Log Formats & Structure](#log-formats--structure)
6. [LogQL Query Language](#logql-query-language)
7. [Grafana Integration](#grafana-integration)
8. [Log Retention & Storage](#log-retention--storage)
9. [Best Practices](#best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### Purpose

Grafana Loki is a log aggregation system designed to be cost-effective and easy to operate. It indexes labels (metadata) rather than full-text content, making it highly efficient for on-premises deployments.

### Why Loki?

**Advantages for Ablage-System:**
- **Label-based indexing**: Lower storage costs than Elasticsearch
- **Prometheus-like querying**: Familiar LogQL syntax
- **Grafana integration**: Unified observability (metrics + logs + traces)
- **On-premises friendly**: No cloud dependencies
- **German language support**: Full UTF-8 support for umlauts

**Architecture Philosophy:**
```
Prometheus: Metrics (numbers over time)
Loki:       Logs (events with context)
Grafana:    Visualization (unified view)
```

### Key Concepts

**Labels:**
- Metadata attached to log streams (e.g., `{job="ablage-backend", level="error"}`)
- Used for indexing and querying
- Keep cardinality low (<50 unique label combinations per job)

**Streams:**
- Unique combination of labels
- Example: `{job="ablage-backend", environment="production", instance="server-01"}`

**Chunks:**
- Compressed batches of log entries
- Stored in object storage (filesystem or S3-compatible)

**Querying:**
- Filter by labels first (fast)
- Parse log content second (slower)

---

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────┐
│                  Grafana (Visualization)                 │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   Loki (Log Aggregation)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Distributor  │  │  Ingester    │  │   Querier    │  │
│  │ (Receives)   │─▶│  (Indexes)   │◀─│  (Queries)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                           │                              │
│                           ▼                              │
│  ┌─────────────────────────────────────────────────┐   │
│  │         Storage (Filesystem / MinIO)             │   │
│  │  - Index (labels)                                │   │
│  │  - Chunks (compressed logs)                      │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                         ▲
                         │
     ┌───────────────────┼───────────────────┐
     │                   │                   │
┌────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐
│ Promtail  │    │  Promtail   │    │  Promtail   │
│ (Backend) │    │  (Worker)   │    │  (Nginx)    │
└────┬──────┘    └──────┬──────┘    └──────┬──────┘
     │                   │                   │
     ▼                   ▼                   ▼
[Backend Logs]    [Worker Logs]     [Access Logs]
```

### Component Roles

**1. Promtail (Log Shipper)**
- Discovers log files
- Attaches labels
- Ships logs to Loki
- Like Prometheus node_exporter but for logs

**2. Loki (Log Aggregation Server)**
- **Distributor**: Receives logs from Promtail
- **Ingester**: Indexes labels, compresses chunks
- **Querier**: Executes LogQL queries
- **Compactor**: Merges chunks, enforces retention

**3. Storage**
- **Filesystem** (simple, single-node)
- **MinIO/S3** (distributed, production)

**4. Grafana (Visualization)**
- Explore logs interactively
- Create log dashboards
- Correlate logs with metrics

---

## Loki Installation

### Docker Compose Setup

**File:** `docker-compose.loki.yml`

```yaml
version: '3.8'

services:
  loki:
    image: grafana/loki:2.9.3
    container_name: ablage-loki
    ports:
      - "3100:3100"
    volumes:
      - ./loki/config.yml:/etc/loki/config.yml:ro
      - loki-data:/loki
    command: -config.file=/etc/loki/config.yml
    restart: unless-stopped
    networks:
      - ablage-network

  promtail:
    image: grafana/promtail:2.9.3
    container_name: ablage-promtail
    volumes:
      - ./promtail/config.yml:/etc/promtail/config.yml:ro
      - /var/log:/var/log:ro
      - /var/lib/docker/containers:/var/lib/docker/containers:ro
    command: -config.file=/etc/promtail/config.yml
    restart: unless-stopped
    networks:
      - ablage-network
    depends_on:
      - loki

volumes:
  loki-data:
    driver: local

networks:
  ablage-network:
    external: true
```

**Start Loki:**
```bash
docker-compose -f docker-compose.loki.yml up -d
```

### Loki Configuration

**File:** `loki/config.yml`

```yaml
auth_enabled: false  # Single-tenant mode

server:
  http_listen_port: 3100
  grpc_listen_port: 9096
  log_level: info

# Data persistence
common:
  path_prefix: /loki
  storage:
    filesystem:
      chunks_directory: /loki/chunks
      rules_directory: /loki/rules
  replication_factor: 1
  ring:
    instance_addr: 127.0.0.1
    kvstore:
      store: inmemory

# Ingester configuration
ingester:
  chunk_idle_period: 5m      # Flush inactive chunks after 5min
  chunk_retain_period: 30s   # Keep chunks in memory for 30s
  max_chunk_age: 1h          # Force chunk cutoff after 1h
  chunk_target_size: 1048576 # 1MB chunks
  chunk_encoding: snappy     # Compression algorithm

# Limits
limits_config:
  retention_period: 336h      # 14 days (2 weeks)
  ingestion_rate_mb: 10       # 10 MB/s per tenant
  ingestion_burst_size_mb: 20 # 20 MB burst
  max_label_names_per_series: 30
  max_label_value_length: 2048
  reject_old_samples: true
  reject_old_samples_max_age: 168h  # 7 days

# Query configuration
query_range:
  results_cache:
    cache:
      embedded_cache:
        enabled: true
        max_size_mb: 100

# Schema configuration
schema_config:
  configs:
    - from: 2024-01-01
      store: boltdb-shipper
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

# Compactor (cleanup old data)
compactor:
  working_directory: /loki/compactor
  shared_store: filesystem
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150

# Table manager (index management)
table_manager:
  retention_deletes_enabled: true
  retention_period: 336h  # 14 days
```

**Key Settings Explained:**

- **`retention_period: 336h`**: Keep logs for 14 days, then delete
- **`chunk_idle_period: 5m`**: Batch logs for 5 minutes before flushing
- **`chunk_encoding: snappy`**: Fast compression (CPU-efficient)
- **`max_label_value_length: 2048`**: Prevents excessively long labels

### Production Setup (MinIO Storage)

**For distributed/production environments, use MinIO:**

```yaml
# loki/config-production.yml
common:
  storage:
    s3:
      s3: http://ablage-minio:9000
      bucketnames: loki-chunks
      endpoint: ablage-minio:9000
      access_key_id: ${MINIO_ACCESS_KEY}
      secret_access_key: ${MINIO_SECRET_KEY}
      s3forcepathstyle: true
      insecure: false

schema_config:
  configs:
    - from: 2024-01-01
      store: boltdb-shipper
      object_store: s3  # Changed from filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h
```

**Create MinIO bucket:**
```bash
mc mb local/loki-chunks
mc mb local/loki-ruler
```

---

## Promtail Configuration

### Overview

Promtail is the agent that ships logs from application servers to Loki.

**File:** `promtail/config.yml`

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0
  log_level: info

# Where to send logs
clients:
  - url: http://ablage-loki:3100/loki/api/v1/push
    batchwait: 1s          # Wait 1s before sending batch
    batchsize: 1048576     # 1MB batches
    timeout: 10s

# Scrape configuration
scrape_configs:
  # Backend application logs
  - job_name: backend
    static_configs:
      - targets:
          - localhost
        labels:
          job: ablage-backend
          environment: production
          __path__: /var/log/ablage/backend/*.log

    # Parse JSON logs
    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            level: level
            message: message
            request_id: request_id
            user_id: user_id
            endpoint: endpoint
            status_code: status_code

      - labels:
          level:
          endpoint:

      - timestamp:
          source: timestamp
          format: RFC3339

      - output:
          source: message

  # Worker logs (Celery)
  - job_name: worker
    static_configs:
      - targets:
          - localhost
        labels:
          job: ablage-worker
          environment: production
          __path__: /var/log/ablage/worker/*.log

    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            level: level
            message: message
            task_id: task_id
            task_name: task_name

      - labels:
          level:
          task_name:

      - timestamp:
          source: timestamp
          format: RFC3339

  # Nginx access logs
  - job_name: nginx
    static_configs:
      - targets:
          - localhost
        labels:
          job: nginx
          environment: production
          __path__: /var/log/nginx/access.log

    # Parse Nginx log format
    pipeline_stages:
      - regex:
          expression: '^(?P<remote_addr>[\w\.]+) - (?P<remote_user>[\w-]+) \[(?P<timestamp>.*)\] "(?P<method>\w+) (?P<path>[\w\/\?=&\-\.]+) HTTP/(?P<http_version>[\d\.]+)" (?P<status>\d{3}) (?P<body_bytes_sent>\d+) "(?P<http_referer>.*)" "(?P<http_user_agent>.*)"$'

      - labels:
          method:
          status:

      - timestamp:
          source: timestamp
          format: "02/Jan/2006:15:04:05 -0700"

  # Docker container logs
  - job_name: docker
    static_configs:
      - targets:
          - localhost
        labels:
          job: docker
          environment: production
          __path__: /var/lib/docker/containers/*/*.log

    # Parse Docker JSON logs
    pipeline_stages:
      - json:
          expressions:
            stream: stream
            log: log
            time: time

      - labels:
          stream:

      - timestamp:
          source: time
          format: RFC3339Nano

      - output:
          source: log
```

### Pipeline Stages Explained

**1. JSON Stage:**
```yaml
- json:
    expressions:
      level: level           # Extract "level" field from JSON
      message: message       # Extract "message" field
      request_id: request_id
```

**Parses JSON logs like:**
```json
{
  "timestamp": "2025-01-23T15:30:00Z",
  "level": "ERROR",
  "message": "Database connection failed",
  "request_id": "req_123"
}
```

**2. Labels Stage:**
```yaml
- labels:
    level:      # Promote level to label (for filtering)
    endpoint:   # Promote endpoint to label
```

**Creates indexed labels for fast querying.**

**Caution:** Don't add high-cardinality fields as labels (e.g., `request_id`, `user_id`). Keep them in log content.

**3. Timestamp Stage:**
```yaml
- timestamp:
    source: timestamp  # Field containing timestamp
    format: RFC3339    # Timestamp format
```

**Parses timestamp from log, so Loki knows when event occurred.**

**4. Output Stage:**
```yaml
- output:
    source: message  # Use this field as the final log line
```

**Determines what text appears in Grafana log viewer.**

**5. Regex Stage (for non-JSON logs):**
```yaml
- regex:
    expression: '^(?P<timestamp>[\d\-:T]+) (?P<level>\w+) (?P<message>.*)$'
```

**Parses structured text logs.**

### Promtail Service Discovery

**Auto-discover Docker containers:**

```yaml
scrape_configs:
  - job_name: docker-autodiscovery
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 15s

    relabel_configs:
      # Only scrape containers with label
      - source_labels: [__meta_docker_container_label_logging]
        regex: "enabled"
        action: keep

      # Use container name as job label
      - source_labels: [__meta_docker_container_name]
        regex: '/(.*)'
        target_label: job

      # Environment from container label
      - source_labels: [__meta_docker_container_label_environment]
        target_label: environment
```

**Add label to containers in docker-compose.yml:**
```yaml
services:
  backend:
    image: ablage/backend:latest
    labels:
      logging: "enabled"
      environment: "production"
```

---

## Log Formats & Structure

### Structured Logging (JSON)

**Best Practice:** Always use structured (JSON) logging for machine-readable logs.

**Python Example (structlog):**

```python
import structlog

logger = structlog.get_logger(__name__)

# ✅ GOOD: Structured logging
logger.info(
    "user_login",
    user_id="user_123",
    username="mueller@firma.de",
    ip_address="192.168.1.100",
    success=True
)

# Output:
# {
#   "timestamp": "2025-01-23T15:30:00.123Z",
#   "level": "info",
#   "event": "user_login",
#   "user_id": "user_123",
#   "username": "mueller@firma.de",
#   "ip_address": "192.168.1.100",
#   "success": true
# }
```

**❌ BAD: Unstructured string logging**
```python
logger.info(f"User {username} logged in from {ip_address}")

# Output:
# 2025-01-23 15:30:00 INFO User mueller@firma.de logged in from 192.168.1.100
```

**Why JSON is better:**
- Easy to parse in LogQL
- Consistent field names
- Supports German umlauts natively
- Machine-readable

### Standard Log Fields

**Required Fields:**
- `timestamp` (RFC3339): When the event occurred
- `level` (string): `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `message` (string): Human-readable description

**Recommended Fields:**
- `request_id` (string): Trace requests across services
- `user_id` (string): Associate actions with users
- `endpoint` (string): API endpoint (e.g., `/api/v1/documents`)
- `method` (string): HTTP method (`GET`, `POST`, etc.)
- `status_code` (int): HTTP status code
- `duration_ms` (int): Request duration in milliseconds

**Application-Specific Fields:**
- `document_id` (string): For document-related events
- `ocr_backend` (string): `deepseek`, `got_ocr`, `surya`
- `gpu_id` (int): GPU device ID (0, 1, ...)
- `error_type` (string): Error class name (e.g., `ValidationError`)

### Log Levels

**When to use each level:**

**DEBUG:**
- Detailed diagnostic information
- Not logged in production (too verbose)
- Example: Variable values, function entry/exit

**INFO:**
- Normal application behavior
- Key events (user login, document uploaded)
- Example: "Document doc_123 uploaded by user_456"

**WARNING:**
- Potentially harmful situations
- Application can continue
- Example: "Cache miss, falling back to database"

**ERROR:**
- Error events that allow application to continue
- Example: "Failed to process document doc_123: Invalid PDF format"

**CRITICAL:**
- Severe errors causing application shutdown
- Example: "Database connection lost, shutting down"

### German Language Logs

**User-facing messages in German, technical fields in English:**

```python
logger.error(
    "dokument_verarbeitung_fehlgeschlagen",  # Event name (lowercase, underscores)
    document_id="doc_789",
    user_id="user_456",
    fehler_nachricht="Ungültiges PDF-Format",  # German message
    error_type="ValidationError",             # Technical term (English OK)
    technical_details="File signature mismatch: expected %PDF, got %PNG"
)
```

**Output:**
```json
{
  "timestamp": "2025-01-23T15:30:00.123Z",
  "level": "ERROR",
  "event": "dokument_verarbeitung_fehlgeschlagen",
  "document_id": "doc_789",
  "user_id": "user_456",
  "fehler_nachricht": "Ungültiges PDF-Format",
  "error_type": "ValidationError",
  "technical_details": "File signature mismatch: expected %PDF, got %PNG"
}
```

**Loki handles UTF-8 natively**, so äöüß work perfectly in labels and log content.

---

## LogQL Query Language

### Basics

LogQL is similar to PromQL but for logs.

**Query Structure:**
```
{labels} |= "search text" | parser | filter | aggregation
```

**Example:**
```logql
{job="ablage-backend", level="error"} |= "database" | json | status_code >= 500
```

**Breakdown:**
1. `{job="ablage-backend", level="error"}` - Filter by labels (FAST)
2. `|= "database"` - Line filter (contains "database")
3. `| json` - Parse JSON log content
4. `| status_code >= 500` - Filter parsed field

### Label Selectors

**Exact match:**
```logql
{job="ablage-backend"}
```

**Regex match:**
```logql
{job=~"ablage-(backend|worker)"}
```

**Not equal:**
```logql
{job!="nginx"}
```

**Multiple labels (AND):**
```logql
{job="ablage-backend", environment="production", level="error"}
```

### Line Filters

**Contains:**
```logql
{job="ablage-backend"} |= "database connection"
```

**Does not contain:**
```logql
{job="ablage-backend"} != "health check"
```

**Regex match:**
```logql
{job="ablage-backend"} |~ "error|exception|failed"
```

**Regex not match:**
```logql
{job="ablage-backend"} !~ "debug|trace"
```

### Parsers

**JSON Parser:**
```logql
{job="ablage-backend"} | json
```

**Extracts all JSON fields as labels for filtering.**

**Example log:**
```json
{"level": "ERROR", "message": "Failed", "status_code": 500}
```

**After `| json`, you can filter:**
```logql
{job="ablage-backend"} | json | status_code >= 500
```

**Logfmt Parser (key=value format):**
```logql
{job="nginx"} | logfmt
```

**Example log:**
```
level=error method=POST path=/api/v1/documents status=500
```

**Regex Parser:**
```logql
{job="nginx"} | regexp `^(?P<method>\w+) (?P<path>[\w/]+) (?P<status>\d+)$`
```

**Pattern Parser (simple extraction):**
```logql
{job="ablage-backend"} | pattern `<timestamp> <level> <message>`
```

### Label Filters (Post-Parse)

**After parsing, filter extracted fields:**

```logql
{job="ablage-backend"}
  | json
  | level="ERROR"
  | status_code >= 500
  | duration_ms > 1000
```

**Numeric comparison:**
- `=`, `!=`, `>`, `>=`, `<`, `<=`

**String comparison:**
- `=`, `!=`, `=~` (regex)

**IP address:**
```logql
{job="nginx"} | json | ip(remote_addr) = "192.168.1.0/24"
```

### Aggregations

**Count log lines:**
```logql
count_over_time({job="ablage-backend", level="error"}[5m])
```

**Rate (logs per second):**
```logql
rate({job="ablage-backend"}[5m])
```

**Sum (numeric field):**
```logql
sum(rate({job="ablage-backend"} | json | unwrap duration_ms [5m])) by (endpoint)
```

**Average:**
```logql
avg(rate({job="ablage-backend"} | json | unwrap duration_ms [5m])) by (endpoint)
```

**Top N:**
```logql
topk(10,
  sum(rate({job="ablage-backend", level="error"}[5m])) by (endpoint)
)
```

### Practical Examples

**1. Find all errors in last 5 minutes:**
```logql
{job="ablage-backend", level="error"}
```

**2. Find slow API requests (>1 second):**
```logql
{job="ablage-backend"}
  | json
  | duration_ms > 1000
```

**3. Count errors by endpoint:**
```logql
sum(count_over_time({job="ablage-backend", level="error"}[1h])) by (endpoint)
```

**4. Database connection errors:**
```logql
{job="ablage-backend", level="error"} |= "database connection"
```

**5. Failed OCR jobs:**
```logql
{job="ablage-worker"} |= "ocr_processing_failed" | json
```

**6. User login attempts:**
```logql
{job="ablage-backend"} |= "user_login" | json | success="true"
```

**7. 5xx errors rate:**
```logql
sum(rate({job="ablage-backend"} | json | status_code >= 500 [5m]))
```

**8. Logs from specific user:**
```logql
{job="ablage-backend"} | json | user_id="user_456"
```

**9. German language error messages:**
```logql
{job="ablage-backend", level="error"} |~ "Fehler|fehlgeschlagen|ungültig"
```

**10. GPU memory warnings:**
```logql
{job="ablage-worker"} |= "gpu_memory_high" | json | memory_percent > 85
```

---

## Grafana Integration

### Add Loki Datasource

**Grafana UI:**
1. Configuration → Data Sources → Add data source
2. Select "Loki"
3. URL: `http://ablage-loki:3100`
4. Save & Test

**Via Configuration File:**

```yaml
# grafana/provisioning/datasources/loki.yml
apiVersion: 1

datasources:
  - name: Loki
    type: loki
    access: proxy
    url: http://ablage-loki:3100
    jsonData:
      maxLines: 1000
      timeout: 60
      derivedFields:
        - datasourceUid: prometheus  # Link to Prometheus
          matcherRegex: "request_id=(\\w+)"
          name: "Request ID"
          url: "/explore?orgId=1&left={\"datasource\":\"Prometheus\",\"queries\":[{\"expr\":\"{request_id=\\\"$${__value.raw}\\\"}\"}]}"
```

### Explore Logs

**Grafana → Explore → Select Loki datasource**

**1. Basic Log Browser:**
- Select labels from dropdowns
- Click "Run query"
- View logs in real-time

**2. Live Tailing:**
- Enable "Live" toggle (top-right)
- Logs stream in real-time (like `tail -f`)

**3. Context:**
- Click on a log line
- Click "Show context" to see surrounding logs

**4. Log Details:**
- Expand log line to see all fields
- Click field values to filter

### Log Panels in Dashboards

**Add to existing dashboard:**

**Panel Type:** Logs

**Query:**
```logql
{job="ablage-backend", level="error"}
```

**Panel Options:**
- **Max data points**: 1000
- **Order**: Newest first
- **Dedupe**: Off
- **Show labels**: Selected labels only
- **Wrap lines**: On (for long logs)

**Example Panel Configuration:**
```json
{
  "type": "logs",
  "title": "Backend Errors (Last 1h)",
  "targets": [
    {
      "expr": "{job=\"ablage-backend\", level=\"error\"}",
      "refId": "A"
    }
  ],
  "options": {
    "showLabels": false,
    "showTime": true,
    "wrapLogMessage": true,
    "sortOrder": "Descending",
    "dedupStrategy": "none",
    "enableLogDetails": true
  },
  "fieldConfig": {
    "defaults": {
      "custom": {}
    }
  }
}
```

### Correlation (Logs ↔ Metrics)

**Link logs to metrics using labels:**

**Example: Jump from logs to metrics**

**In log panel, add derived field:**
```json
{
  "derivedFields": [
    {
      "datasourceUid": "prometheus",
      "matcherRegex": "request_id=(\\w+)",
      "name": "View Metrics",
      "url": "/d/ablage-app-metrics?var-request_id=${__value.raw}"
    }
  ]
}
```

**Now clicking on `request_id` in logs opens metrics dashboard.**

**Example: Jump from metrics to logs**

**In metrics panel (Grafana), add data link:**
```json
{
  "dataLinks": [
    {
      "title": "View Logs",
      "url": "/explore?orgId=1&left={\"datasource\":\"Loki\",\"queries\":[{\"expr\":\"{job=\\\"ablage-backend\\\",request_id=\\\"${__field.labels.request_id}\\\"}\"}]}"
    }
  ]
}
```

---

## Log Retention & Storage

### Retention Policy

**Default: 14 days (336 hours)**

**Adjust in Loki config:**
```yaml
limits_config:
  retention_period: 720h  # 30 days

compactor:
  retention_enabled: true
  retention_delete_delay: 2h
```

**Retention by Stream (advanced):**
```yaml
limits_config:
  retention_stream_limits:
    # Keep errors longer
    - selector: '{level="error"}'
      priority: 1
      retention: 2160h  # 90 days

    # Keep debug logs shorter
    - selector: '{level="debug"}'
      priority: 2
      retention: 72h  # 3 days
```

### Storage Estimates

**Example: Ablage-System (100 req/s)**

- **Log volume**: ~50 MB/day (compressed)
- **14-day retention**: ~700 MB storage
- **30-day retention**: ~1.5 GB storage
- **Index overhead**: ~10% of log size

**Calculation:**
```
Logs per second: 100 requests × 2 log lines per request = 200 logs/s
Bytes per log: ~500 bytes (JSON, compressed 5:1 = 100 bytes)
Daily volume: 200 logs/s × 100 bytes × 86400 seconds = 1.7 GB/day (uncompressed)
Daily volume (compressed): 1.7 GB ÷ 5 = 340 MB/day

14-day retention: 340 MB/day × 14 = 4.8 GB
```

**Adjust compression ratio (3:1 to 10:1) based on log content.**

### Storage Optimization

**1. Reduce Log Volume:**
```python
# Only log in production what's necessary
if settings.ENVIRONMENT == "production":
    logging.getLogger().setLevel(logging.INFO)  # No DEBUG logs
else:
    logging.getLogger().setLevel(logging.DEBUG)
```

**2. Sampling (for high-volume logs):**
```python
import random

# Sample 10% of INFO logs
if level == "INFO" and random.random() > 0.1:
    return  # Skip logging
```

**3. Separate Streams by Importance:**
```yaml
# Promtail config: Send debug logs to separate Loki instance
clients:
  - url: http://loki-prod:3100/loki/api/v1/push
    match:
      selector: '{level!="debug"}'

  - url: http://loki-debug:3100/loki/api/v1/push
    match:
      selector: '{level="debug"}'
```

**4. Compress Chunks Aggressively:**
```yaml
# Loki config
ingester:
  chunk_encoding: snappy  # Fast (default)
  # Or: gzip (smaller, slower)
  # Or: lz4 (balance)
```

### Backup & Disaster Recovery

**Loki stores data in two places:**
1. **Index** (BoltDB): `/loki/index/`
2. **Chunks** (compressed logs): `/loki/chunks/`

**Backup Strategy:**

**Daily backups:**
```bash
#!/bin/bash
# /usr/local/bin/backup-loki.sh

BACKUP_DIR="/backup/loki/$(date +%Y-%m-%d)"
mkdir -p $BACKUP_DIR

# Stop Loki (to ensure consistency)
docker stop ablage-loki

# Backup index and chunks
cp -r /var/lib/docker/volumes/loki-data/_data/* $BACKUP_DIR/

# Restart Loki
docker start ablage-loki

# Compress backup
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR

# Remove backups older than 30 days
find /backup/loki -name "*.tar.gz" -mtime +30 -delete
```

**Add to cron:**
```
0 2 * * * /usr/local/bin/backup-loki.sh
```

**Restore:**
```bash
# Stop Loki
docker stop ablage-loki

# Extract backup
tar -xzf /backup/loki/2025-01-23.tar.gz -C /var/lib/docker/volumes/loki-data/_data/

# Start Loki
docker start ablage-loki
```

---

## Best Practices

### 1. Log What Matters

**Do Log:**
- ✅ Errors and exceptions (with stack traces)
- ✅ User actions (login, logout, document upload)
- ✅ Performance issues (slow queries, timeouts)
- ✅ Security events (authentication failures, permission denied)
- ✅ State changes (document processed, job completed)

**Don't Log:**
- ❌ Sensitive data (passwords, API keys, credit cards)
- ❌ PII without consent (personal addresses, phone numbers)
- ❌ Verbose debug info in production
- ❌ Every single request (sample high-volume endpoints)

### 2. Use Structured Logging

**Always use JSON logs in production:**

```python
# ❌ BAD
logger.info(f"User {user_id} uploaded document {doc_id}")

# ✅ GOOD
logger.info(
    "document_uploaded",
    user_id=user_id,
    document_id=doc_id,
    file_size_mb=file_size / 1024 / 1024,
    mime_type=mime_type
)
```

### 3. Add Context

**Include identifiers for correlation:**

**Request ID (trace requests across services):**
```python
# Add to all logs in a request
import contextvars

request_id_var = contextvars.ContextVar('request_id', default=None)

@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
    request_id_var.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# In logging
logger.info("processing_document", request_id=request_id_var.get())
```

**User ID:**
```python
logger.info("action_performed", user_id=current_user.id)
```

**Document ID:**
```python
logger.info("ocr_started", document_id=doc_id)
```

### 4. Label Cardinality

**Keep label combinations low (<50 per job):**

**❌ BAD (high cardinality):**
```yaml
# Promtail config
labels:
  user_id:      # 10,000+ unique users = 10,000 streams!
  document_id:  # 100,000+ documents = disaster!
```

**✅ GOOD (low cardinality):**
```yaml
labels:
  job: ablage-backend
  environment: production  # 3 values: dev, staging, prod
  level: error             # 5 values: DEBUG, INFO, WARNING, ERROR, CRITICAL
  instance: server-01      # 10 servers max
# Total streams: 1 × 3 × 5 × 10 = 150 ✅
```

**Keep high-cardinality fields in log content, NOT labels:**
```python
# user_id goes in log content, not labels
logger.info("action", user_id=user_id)  # ✅
```

### 5. Performance

**Optimize log queries:**

**❌ SLOW:**
```logql
{job="ablage-backend"} |~ ".*error.*"  # Regex on all logs
```

**✅ FAST:**
```logql
{job="ablage-backend", level="error"}  # Label filter first
```

**Use label filters first, then line filters, then parsers:**

**Optimal order:**
```logql
{job="ablage-backend", level="error"}  # 1. Labels (FAST - indexed)
  |= "database"                        # 2. Line filter (FAST - text search)
  | json                               # 3. Parser (MEDIUM - parse JSON)
  | duration_ms > 1000                 # 4. Field filter (SLOW - filter parsed data)
```

### 6. Security & Compliance

**Never log:**
- Passwords (plain or hashed)
- API keys / tokens
- Credit card numbers
- Social security numbers
- Health information (HIPAA)

**Sanitize logs:**
```python
def sanitize(data: dict) -> dict:
    """Remove sensitive fields from log data."""
    sensitive_fields = ['password', 'api_key', 'token', 'credit_card']
    return {k: v for k, v in data.items() if k not in sensitive_fields}

logger.info("user_data", **sanitize(user_dict))
```

**German Privacy (GDPR/DSGVO):**
- User data logging requires consent
- Implement log deletion on user request
- Document retention period (14-30 days typical)

### 7. German Language Support

**Use UTF-8 encoding everywhere:**

**Python:**
```python
import structlog

logger = structlog.get_logger()

logger.error(
    "dokument_verarbeitung_fehlgeschlagen",
    fehler="Ungültige Umlaute: äöüÄÖÜß",
    dokument_id="doc_123"
)
```

**Loki handles UTF-8 natively, no special configuration needed.**

**LogQL queries with German:**
```logql
{job="ablage-backend"} |= "Müller"  # Works perfectly
{job="ablage-backend"} |~ "Größe|größer"  # Regex with umlauts
```

---

## Troubleshooting

### Promtail Not Sending Logs

**Symptom:** No logs appearing in Grafana

**Check 1: Promtail running?**
```bash
docker ps | grep promtail
docker logs ablage-promtail --tail=50
```

**Check 2: Can Promtail reach Loki?**
```bash
docker exec ablage-promtail curl http://ablage-loki:3100/ready
# Expected: {"status": "ready"}
```

**Check 3: Log files exist?**
```bash
docker exec ablage-promtail ls -lh /var/log/ablage/
```

**Check 4: File permissions?**
```bash
# Promtail needs read access
sudo chmod +r /var/log/ablage/*.log
```

**Check 5: Promtail metrics:**
```bash
curl http://localhost:9080/metrics | grep promtail_sent_entries_total
# Should be > 0 and increasing
```

### Loki Query Timeout

**Symptom:** Queries fail with "timeout" error

**Cause:** Query too broad (too many logs to scan)

**Solution 1: Add more label filters**
```logql
# ❌ SLOW: Scans all logs
{job="ablage-backend"} |= "error"

# ✅ FAST: Scans only error-level logs
{job="ablage-backend", level="error"}
```

**Solution 2: Reduce time range**
```logql
# ❌ SLOW: 7 days
{job="ablage-backend"}[7d]

# ✅ FAST: 1 hour
{job="ablage-backend"}[1h]
```

**Solution 3: Increase Loki timeout**
```yaml
# loki/config.yml
server:
  http_server_read_timeout: 60s
  http_server_write_timeout: 60s

query_range:
  max_query_length: 721h  # 30 days
  max_query_parallelism: 16
```

### High Memory Usage

**Symptom:** Loki using >4 GB RAM

**Cause:** Large chunks in memory

**Solution: Tune ingester**
```yaml
# loki/config.yml
ingester:
  chunk_idle_period: 3m      # Flush faster (down from 5m)
  chunk_target_size: 524288  # Smaller chunks (512 KB down from 1 MB)
  max_chunk_age: 30m         # Force flush faster (down from 1h)
```

**Restart Loki:**
```bash
docker restart ablage-loki
```

### Labels Not Showing Up

**Symptom:** Parsed fields not available as labels

**Cause:** Labels not promoted in Promtail pipeline

**Solution: Add labels stage**
```yaml
# promtail/config.yml
pipeline_stages:
  - json:
      expressions:
        level: level
        endpoint: endpoint

  - labels:
      level:      # ← Add this to make 'level' a label
      endpoint:   # ← Add this to make 'endpoint' a label
```

**Restart Promtail:**
```bash
docker restart ablage-promtail
```

### Logs Missing

**Symptom:** Gaps in log timeline

**Possible causes:**

**1. Retention deleted logs:**
```bash
# Check retention setting
docker exec ablage-loki cat /etc/loki/config.yml | grep retention_period
```

**2. Clock skew:**
```bash
# Check server time
date
# Check Loki time
docker exec ablage-loki date
# If different: sync clocks (NTP)
```

**3. Loki was down:**
```bash
# Check Loki uptime
docker ps --format "{{.Names}}: {{.Status}}" | grep loki
```

**4. Promtail buffer full:**
```bash
# Check Promtail metrics
curl http://localhost:9080/metrics | grep promtail_dropped_entries_total
# If > 0: Increase Promtail resources or batch size
```

---

## Summary

### What We Covered

- ✅ Loki architecture and installation
- ✅ Promtail configuration for log shipping
- ✅ Structured JSON logging with German support
- ✅ LogQL query language (labels, filters, aggregations)
- ✅ Grafana integration (log panels, correlation with metrics)
- ✅ Log retention and storage optimization
- ✅ Best practices for production logging
- ✅ Troubleshooting common issues

### Quick Reference

**LogQL Cheat Sheet:**
```logql
# Basic query
{job="ablage-backend"}

# With filters
{job="ablage-backend", level="error"}

# Line filter
{job="ablage-backend"} |= "database"

# Parse JSON
{job="ablage-backend"} | json

# Filter parsed field
{job="ablage-backend"} | json | status_code >= 500

# Count logs
count_over_time({job="ablage-backend"}[5m])

# Rate
rate({job="ablage-backend"}[5m])

# Aggregation
sum(count_over_time({job="ablage-backend", level="error"}[1h])) by (endpoint)
```

**Promtail Pipeline:**
```yaml
pipeline_stages:
  - json:           # Parse JSON
      expressions: {...}
  - labels:         # Promote to labels
      level:
  - timestamp:      # Extract timestamp
      source: timestamp
      format: RFC3339
  - output:         # Set log line
      source: message
```

### Next Steps

1. **Configure Promtail** on all servers
2. **Create log panels** in Grafana dashboards
3. **Set up alerts** on error logs (integrate with AlertManager)
4. **Implement structured logging** in application code
5. **Monitor log volume** and adjust retention as needed

---

**Document Status:** ✅ Production-Ready
**Last Reviewed:** 2025-01-23
**Next Review:** 2025-04-23
**Owner:** Operations Team
