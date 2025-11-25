# Sentry Integration - Ablage-System OCR

Error tracking, performance monitoring, and application insights with Sentry.

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r infrastructure/sentry/requirements.txt

# Configure Sentry DSN
cp infrastructure/sentry/.env.example infrastructure/sentry/.env
nano infrastructure/sentry/.env  # Add your SENTRY_DSN

# Initialize in your application (see example_usage.py)
```

## 📋 Features

### Error Tracking

- **Automatic Exception Capture**: All unhandled exceptions captured
- **User Context**: Track which users encounter errors
- **Request Context**: Full request details (method, URL, headers)
- **Stack Traces**: Complete stack traces with local variables
- **Breadcrumbs**: Activity trail leading to errors
- **Source Maps**: Source code context in error reports

### Performance Monitoring

- **Transaction Tracking**: Monitor API endpoint performance
- **Database Query Tracking**: Slow query detection
- **GPU Operation Tracking**: Monitor OCR backend performance
- **Custom Spans**: Track specific code sections
- **Slow Request Detection**: Automatic tagging of slow requests

### Integrations

- **FastAPI**: Automatic endpoint tracking
- **SQLAlchemy**: Database query monitoring
- **Celery**: Background task tracking with retries
- **Redis**: Cache operation monitoring
- **Logging**: Python logging integration

## ⚙️ Configuration

### Environment Variables

Create `.env` file:

```bash
# Sentry DSN (required)
SENTRY_DSN=https://examplePublicKey@o0.ingest.sentry.io/0

# Environment
ENVIRONMENT=production

# Version/Release
VERSION=0.1.0

# Sampling rates (0.0 to 1.0)
SENTRY_TRACES_SAMPLE_RATE=0.1          # 10% of transactions
SENTRY_PROFILES_SAMPLE_RATE=0.1        # 10% profiling
SENTRY_WORKER_TRACES_SAMPLE_RATE=0.05  # 5% for workers

# Enable tracing
SENTRY_ENABLE_TRACING=true

# Slow request threshold
SENTRY_SLOW_REQUEST_THRESHOLD_MS=1000
```

### Get Sentry DSN

1. **Sign up**: https://sentry.io/signup/
2. **Create Project**: Choose "Python" → "FastAPI"
3. **Copy DSN**: Settings → Projects → [Your Project] → Client Keys (DSN)
4. **Add to `.env`**: `SENTRY_DSN=your_dsn_here`

### Sampling Rates

Control what percentage of events to send:

- **Production**: 5-10% (low overhead, sufficient data)
- **Staging**: 20-50% (more detailed testing)
- **Development**: 100% (catch everything)

```python
# Low traffic (< 1000 req/day): 100%
SENTRY_TRACES_SAMPLE_RATE=1.0

# Medium traffic (1k-10k req/day): 10-20%
SENTRY_TRACES_SAMPLE_RATE=0.1

# High traffic (> 10k req/day): 1-5%
SENTRY_TRACES_SAMPLE_RATE=0.01
```

## 🔧 Integration

### FastAPI Application

```python
from fastapi import FastAPI
from infrastructure.sentry.init_sentry import initialize_sentry_for_backend
from infrastructure.sentry.middleware import SentryMiddleware, SentryContextMiddleware

app = FastAPI()

# Initialize Sentry on startup
@app.on_event("startup")
async def startup():
    initialize_sentry_for_backend(
        app_name="ablage-backend",
        environment="production",
        release="0.1.0"
    )

# Add middleware
app.add_middleware(SentryMiddleware, slow_request_threshold_ms=1000)
app.add_middleware(SentryContextMiddleware)
```

### Celery Worker

```python
from celery import Celery
from infrastructure.sentry.init_sentry import initialize_sentry_for_worker
from infrastructure.sentry.celery_integration import SentryTask

celery_app = Celery('ablage-worker')

@celery_app.on_after_configure.connect
def setup_sentry(sender, **kwargs):
    initialize_sentry_for_worker(
        worker_name="ablage-worker",
        environment="production",
        release="0.1.0"
    )

# Use SentryTask as base
@celery_app.task(base=SentryTask, bind=True)
def my_task(self, arg):
    # Task is automatically tracked
    pass
```

## 📊 Usage Examples

### Basic Error Tracking

```python
from infrastructure.sentry.sentry import capture_exception, capture_message

try:
    result = risky_operation()
except Exception as e:
    # Capture exception with context
    capture_exception(e, extra={
        'user_id': user_id,
        'document_id': document_id,
    })
    raise

# Capture custom message
capture_message(
    "GPU memory usage high",
    level='warning',
    extra={'usage_percent': 85}
)
```

### User Context

```python
from infrastructure.sentry.sentry import set_user_context

# Set user context when user logs in
set_user_context(
    user_id=str(current_user.id),
    email=current_user.email,
    username=current_user.username
)

# Now all errors will be associated with this user
```

### Custom Context

```python
from infrastructure.sentry.sentry import set_context

# Add OCR-specific context
set_context('ocr', {
    'backend': 'deepseek',
    'language': 'de',
    'document_type': 'pdf',
    'page_count': 10,
})

# Add GPU context
set_context('gpu', {
    'device': 'RTX 4080',
    'memory_allocated': '8.5 GB',
    'temperature': '72°C',
})
```

### Breadcrumbs

```python
from infrastructure.sentry.sentry import add_breadcrumb

# Add breadcrumb for debugging
add_breadcrumb(
    message='Starting document processing',
    category='ocr',
    level='info',
    data={
        'document_id': doc_id,
        'backend': 'deepseek',
    }
)

# Processing steps
add_breadcrumb(
    message='Image preprocessing complete',
    category='ocr',
    level='info'
)

add_breadcrumb(
    message='OCR inference complete',
    category='ocr',
    level='info',
    data={'duration_ms': 1234}
)
```

### Performance Tracking

```python
from infrastructure.sentry.sentry import trace_function, trace_span

# Track entire function
@trace_function(op='ocr.process')
async def process_document(document_id: str):
    # Function execution time is tracked
    result = await ocr_service.process(document_id)
    return result

# Track specific span
@trace_span(op='db.query', description='Fetch documents')
async def fetch_documents(db: Session):
    # This span appears under parent transaction
    result = await db.execute(...)
    return result
```

### Manual Transactions

```python
from infrastructure.sentry.sentry import SentryTransaction

with SentryTransaction('batch_process', op='ocr.batch') as transaction:
    transaction.set_tag('batch_size', len(documents))
    transaction.set_tag('backend', 'deepseek')
    transaction.set_data('document_ids', document_ids)

    try:
        results = []
        for doc_id in document_ids:
            result = await process_document(doc_id)
            results.append(result)

        transaction.set_status('ok')
        return results
    except Exception as e:
        transaction.set_status('internal_error')
        raise
```

### GPU Operations

```python
from infrastructure.sentry.sentry import track_gpu_operation

async def process_with_gpu(image_path: str):
    with track_gpu_operation('inference', 'deepseek'):
        try:
            result = model.process(image_path)
            return result
        except torch.cuda.OutOfMemoryError as e:
            # GPU OOM tracked automatically
            raise
```

### Celery Tasks

```python
from infrastructure.sentry.celery_integration import SentryTask, track_ocr_task

@track_ocr_task(backend='deepseek')
@celery_app.task(base=SentryTask, bind=True, max_retries=3)
def process_task(self, document_id: str):
    try:
        result = process_document(document_id)
        return result
    except Exception as e:
        # Exception captured with task context
        raise self.retry(exc=e, countdown=60)
```

## 🔒 Security & Privacy

### Sensitive Data Filtering

Sentry automatically filters:

- **Headers**: Authorization, Cookie, X-API-Key
- **Query Parameters**: token, api_key, password
- **POST Data**: password, token, api_key, secret

Custom filtering in `sentry.py`:

```python
def before_send_filter(event, hint):
    # Scrub sensitive data before sending
    if 'request' in event:
        # Filter headers, query params, body
        pass
    return event
```

### PII Protection

```python
# Disable PII by default
sentry_sdk.init(
    dsn=dsn,
    send_default_pii=False,  # Don't send IP, user agent, etc.
    # ...
)
```

### Ignored Exceptions

Don't send noisy exceptions:

```python
# In before_send_filter()
ignored_exceptions = [
    'RequestValidationError',  # Client errors
    'HTTPException',           # Expected HTTP errors
]
```

## 📊 Monitoring in Sentry Dashboard

### Key Metrics to Monitor

1. **Error Rate**: Errors per minute
2. **Apdex Score**: User satisfaction (response time)
3. **Transaction Throughput**: Requests per second
4. **P95 Response Time**: 95th percentile latency
5. **Failure Rate**: % of failed requests

### Performance Dashboard

**Custom Dashboards**:

- OCR processing time by backend
- GPU utilization and OOM errors
- Database query performance
- API endpoint latency
- Celery task duration

### Alerts

**Set up alerts for**:

- Error rate spike (> 10 errors/min)
- P95 latency increase (> 2s)
- GPU OOM errors (any occurrence)
- Failed Celery tasks (> 5% failure rate)
- Disk space low (< 10%)

## 🐛 Troubleshooting

### No Events in Sentry

```bash
# Check DSN is set
echo $SENTRY_DSN

# Test Sentry connection
python -c "
import sentry_sdk
sentry_sdk.init(dsn='YOUR_DSN')
sentry_sdk.capture_message('Test message')
"

# Check logs for errors
grep -i sentry /var/log/ablage-system/backend.log
```

### Too Many Events

```bash
# Reduce sampling rate
export SENTRY_TRACES_SAMPLE_RATE=0.01  # 1%

# Filter noisy endpoints
# In middleware, skip health checks:
if request.url.path == '/health':
    return await call_next(request)
```

### Performance Issues

```bash
# Disable profiling
export SENTRY_PROFILES_SAMPLE_RATE=0.0

# Reduce trace sampling
export SENTRY_TRACES_SAMPLE_RATE=0.05

# Disable for specific endpoints
# Add to middleware:
if request.url.path.startswith('/static'):
    return await call_next(request)
```

### Missing Context

```python
# Ensure user context is set
from infrastructure.sentry.sentry import set_user_context

@app.middleware("http")
async def add_user_context(request, call_next):
    if user := getattr(request.state, 'user', None):
        set_user_context(
            user_id=str(user.id),
            username=user.username
        )
    return await call_next(request)
```

## 📈 Best Practices

### 1. Set User Context Early

```python
# In authentication middleware
if user := await get_current_user(request):
    set_user_context(
        user_id=str(user.id),
        email=user.email,
        username=user.username
    )
```

### 2. Add Breadcrumbs for Debugging

```python
# Before critical operations
add_breadcrumb(
    message='Starting GPU inference',
    category='gpu',
    level='info',
    data={'backend': 'deepseek', 'batch_size': 32}
)
```

### 3. Tag Important Operations

```python
# Tag GPU operations
with track_gpu_operation('inference', 'deepseek'):
    result = model.process(image)

# Tag by feature
sentry_sdk.set_tag('feature', 'ocr')
sentry_sdk.set_tag('backend', backend_name)
```

### 4. Capture Context on Errors

```python
try:
    result = process_document(doc_id)
except Exception as e:
    capture_exception(e, extra={
        'document_id': doc_id,
        'user_id': user_id,
        'backend': backend,
        'retry_count': retries,
    })
    raise
```

### 5. Use Transactions for Performance

```python
# Track complex operations
with SentryTransaction('document.ocr', op='ocr'):
    result = await process_document(doc_id)
```

## 📚 Resources

- [Sentry Python SDK Documentation](https://docs.sentry.io/platforms/python/)
- [FastAPI Integration](https://docs.sentry.io/platforms/python/guides/fastapi/)
- [Celery Integration](https://docs.sentry.io/platforms/python/guides/celery/)
- [Performance Monitoring](https://docs.sentry.io/product/performance/)
- [Error Tracking Best Practices](https://docs.sentry.io/product/issues/issue-details/)

---

**Last Updated**: 2025-01-24
**Maintainer**: Ablage-System Team
