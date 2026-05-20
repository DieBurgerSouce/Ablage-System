# Distributed Tracing Guide

## Overview

The Ablage System uses OpenTelemetry for distributed tracing, enabling end-to-end visibility of requests across all services. Traces are collected, processed, and visualized using Jaeger.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ABLAGE SYSTEM COMPONENTS                     │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ FastAPI  │  │  Celery  │  │ OCR GPU  │  │  Redis   │       │
│  │  (OTEL)  │  │  (OTEL)  │  │  (OTEL)  │  │  (OTEL)  │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬──────┘      │
│       │             │             │             │              │
│       └─────────────┴─────────────┴─────────────┘              │
│                         │                                       │
└─────────────────────────┼───────────────────────────────────────┘
                          │ OTLP (gRPC/HTTP)
                          ▼
              ┌───────────────────────┐
              │  OTEL COLLECTOR       │
              │                       │
              │ • Receives traces     │
              │ • Filters/samples     │
              │ • Batches exports     │
              └───────┬───────────────┘
                      │
                      ▼
              ┌───────────────────────┐
              │       JAEGER          │
              │                       │
              │ • Storage (Badger)    │
              │ • Query & Search      │
              │ • Web UI (:16686)     │
              └───────────────────────┘
```

## Quick Start

### Start Tracing Infrastructure

```bash
# Start tracing services alongside main application
docker-compose -f docker-compose.yml \
  -f infrastructure/tracing/docker-compose.tracing.yml up -d

# Access Jaeger UI
open http://localhost:16686
```

### Environment Configuration

```bash
# .env settings for tracing
OTEL_ENABLED=true
OTEL_SERVICE_NAME=ablage-system
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
OTEL_EXPORTER_OTLP_PROTOCOL=grpc
```

## Components

### 1. OpenTelemetry Collector

Located at `infrastructure/tracing/otel-collector/otel-collector-config.yaml`

**Receivers:**
- OTLP (gRPC :4317, HTTP :4318)
- Jaeger (gRPC :14250, Thrift HTTP :14268)
- Zipkin (:9411)

**Processors:**
- Memory limiter (512 MiB limit)
- Batch processing (5s timeout, 512 batch size)
- Resource detection (Docker, system)
- Tail sampling (errors, slow requests, OCR operations)

**Exporters:**
- Jaeger via OTLP
- Prometheus metrics (:8889)
- Debug logging

### 2. Jaeger

Located at `infrastructure/tracing/docker-compose.tracing.yml`

**Features:**
- All-in-one deployment (dev/staging)
- Badger storage (persistent)
- Custom sampling strategies

**Ports:**
| Port | Protocol | Description |
|------|----------|-------------|
| 16686 | HTTP | Jaeger UI |
| 4317 | gRPC | OTLP gRPC receiver |
| 4318 | HTTP | OTLP HTTP receiver |
| 14250 | gRPC | Jaeger gRPC |
| 14268 | HTTP | Jaeger Thrift HTTP |
| 9411 | HTTP | Zipkin compatible |

### 3. Application Instrumentation

Located at `app/core/tracing.py`

**Auto-instrumentation:**
- FastAPI (HTTP requests/responses)
- SQLAlchemy (database queries)
- Redis (cache operations)
- Celery (task execution)
- HTTPX/Requests (outbound HTTP)

## Usage in Code

### Basic Tracing

```python
from app.core.tracing import get_tracer, trace_span, TracingService

# Get tracer instance
tracer = get_tracer()

# Manual span creation
with tracer.start_as_current_span("custom_operation") as span:
    span.set_attribute("custom.key", "value")
    # ... operation ...
```

### Using Decorator

```python
from app.core.tracing import trace_span

@trace_span("process_document")
async def process_document(doc_id: str):
    # Automatically creates span with function name
    # and records exceptions
    pass
```

### OCR-Specific Attributes

```python
from app.core.tracing import set_ocr_span_attributes

# Add OCR-specific attributes to current span
set_ocr_span_attributes(
    backend="deepseek",
    document_id="doc-123",
    page_count=5,
    confidence=0.95,
    processing_time_ms=1234.5
)
```

### Creating Child Spans

```python
from app.core.tracing import get_tracer

tracer = get_tracer()

async def process_batch(documents: list):
    with tracer.start_as_current_span("batch_processing") as parent:
        for doc in documents:
            with tracer.start_as_current_span("process_single") as child:
                child.set_attribute("document.id", doc.id)
                await process_document(doc)
```

## Sampling Strategies

Located at `infrastructure/tracing/jaeger/sampling.json`

### Service-Specific Sampling

| Service | Base Rate | Special Operations |
|---------|-----------|-------------------|
| ablage-system | 10% | OCR: 100%, Documents: 50% |
| ablage-worker | 50% | OCR processing: 100% |
| ablage-frontend | 5% | - |

### Tail Sampling (OTEL Collector)

Traces are sampled based on:
1. **Errors**: All traces with errors (100%)
2. **Latency**: Requests >2s (100%)
3. **OCR Operations**: All OCR traces (100%)
4. **Default**: 10% probabilistic sampling

## Dashboards & Queries

### Jaeger UI Features

1. **Search Traces**: Filter by service, operation, tags, duration
2. **Compare Traces**: Side-by-side trace comparison
3. **Dependencies**: Service dependency graph
4. **Monitor**: SLO monitoring (Jaeger 1.50+)

### Common Searches

```
# Find slow OCR operations
service=ablage-system operation=POST /api/v1/ocr/* minDuration=2s

# Find errors
service=ablage-system error=true

# Find specific document processing
service=ablage-system tag=document.id:doc-123

# Find by OCR backend
service=ablage-system tag=ocr.backend:deepseek
```

## Best Practices

### 1. Span Naming

```python
# Good: Descriptive, consistent naming
"POST /api/v1/documents/{id}"
"ocr.process_document"
"db.query.documents"
"redis.get.document_cache"

# Bad: Vague or inconsistent
"process"
"doStuff"
"handler"
```

### 2. Attributes

```python
# Essential attributes
span.set_attribute("document.id", doc_id)
span.set_attribute("document.type", "invoice")
span.set_attribute("ocr.backend", "deepseek")
span.set_attribute("ocr.confidence", 0.95)
span.set_attribute("user.id", user_id)

# Avoid: PII in attributes
# Never: span.set_attribute("user.email", email)
```

### 3. Error Recording

```python
from opentelemetry.trace import Status, StatusCode

try:
    result = await process()
except Exception as e:
    span.set_status(Status(StatusCode.ERROR, str(e)))
    span.record_exception(e)
    raise
```

### 4. Context Propagation

```python
# Context is automatically propagated via headers
# W3C Trace Context: traceparent, tracestate

# For Celery tasks, context is propagated via task headers
@celery_app.task
def process_task(doc_id: str):
    # Trace context automatically available
    pass
```

## Troubleshooting

### No Traces Appearing

1. Check OTEL_ENABLED environment variable
2. Verify collector connectivity:
   ```bash
   curl http://localhost:4318/v1/traces
   ```
3. Check collector logs:
   ```bash
   docker logs ablage-otel-collector
   ```

### High Memory Usage

1. Adjust tail_sampling num_traces
2. Increase batch processor timeout
3. Lower sampling rates

### Missing Spans

1. Ensure all services use same trace context format
2. Check instrumentor initialization order
3. Verify context propagation headers

## mTLS Configuration

For production environments, enable mTLS between services:

1. Generate certificates:
   ```bash
   ./scripts/generate-mtls-certs.sh
   ```

2. Configure nginx with mTLS:
   ```nginx
   include /etc/nginx/snippets/mtls.conf;
   ```

3. Configure services to present client certificates

## Related Documentation

- [Metrics & Monitoring Guide](./Metrics-Monitoring-Guide.md)
- [Deployment-Production Guide](./Deployment-Production.md)
- [Security & Authentication](./Security&Authentication.md)

## External References

- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [OTEL Collector Configuration](https://opentelemetry.io/docs/collector/configuration/)
