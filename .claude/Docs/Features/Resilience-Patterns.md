# Resilience Patterns Module

**Status**: Production-Ready
**Module**: `app/core/resilience.py`
**Created**: 2026-02-08
**Test Coverage**: >80% target

## Overview

Enterprise resilience patterns for graceful degradation when services fail:
- **Circuit Breaker**: Fail fast when service is down, auto-recovery
- **Retry with Backoff**: Exponential backoff for transient failures
- **Bulkhead**: Resource isolation and concurrent request limiting

## Features

### 1. Circuit Breaker

Thread-safe state machine with 3 states:

```
CLOSED → (failures >= threshold) → OPEN
OPEN → (after timeout) → HALF_OPEN
HALF_OPEN → (success) → CLOSED
HALF_OPEN → (failure) → OPEN
```

**Configuration**:
- `failure_threshold`: Failures before opening (default: 5)
- `recovery_timeout_seconds`: Time before testing recovery (default: 60s)
- `half_open_max_calls`: Successful calls to close (default: 3)

**Usage**:

```python
from app.core.resilience import circuit_breaker

# Decorator pattern with fallback
@circuit_breaker("external_api", failure_threshold=3, fallback=lambda: None)
async def call_external_api():
    response = await httpx.get("https://api.example.com")
    return response.json()

# Manual usage
from app.core.resilience import get_ocr_circuit_breaker

breaker = get_ocr_circuit_breaker("deepseek")
if breaker.can_execute():
    try:
        result = await ocr_backend.process(image)
        breaker.record_success()
    except Exception as e:
        breaker.record_failure(e)
        raise
else:
    raise CircuitBreakerOpenError("deepseek", retry_after=120)
```

### 2. Retry with Exponential Backoff

Automatic retry with configurable backoff strategy:

**Formula**: `delay = min(base_delay * (exponential_base ** attempt), max_delay)`
**Jitter**: Random multiplier (0.5-1.5) to prevent thundering herd

**Usage**:

```python
from app.core.resilience import retry_with_backoff

@retry_with_backoff(
    max_retries=3,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True,
    retryable_exceptions=(ConnectionError, TimeoutError)
)
async def call_api():
    return await client.get("/data")
```

**Backoff Sequence** (base=1.0, exp=2.0, no jitter):
- Attempt 1: immediate
- Retry 1: after 1.0s
- Retry 2: after 2.0s
- Retry 3: after 4.0s

### 3. Bulkhead Pattern

Limit concurrent calls to prevent resource exhaustion:

```python
from app.core.resilience import Bulkhead

bulkhead = Bulkhead(name="gpu_ocr", max_concurrent=2, max_queue=5)

async def process_document(doc_id: str):
    async with bulkhead:
        return await ocr_backend.process(doc_id)
```

**Parameters**:
- `max_concurrent`: Maximum parallel calls
- `max_queue`: Maximum waiting queue (0 = reject immediately)

**Raises**: `BulkheadFullError` when limit reached

## OCR-Specific Configuration

Pre-configured circuit breaker for OCR backends:

```python
from app.core.resilience import get_ocr_circuit_breaker

# For each OCR backend
deepseek_breaker = get_ocr_circuit_breaker("deepseek")
got_breaker = get_ocr_circuit_breaker("got-ocr")
surya_breaker = get_ocr_circuit_breaker("surya")
```

**OCR Settings**:
- `failure_threshold`: 3 (faster reaction to GPU/VRAM issues)
- `recovery_timeout`: 120s (more time for GPU recovery)
- `half_open_max_calls`: 2

## Monitoring

### Prometheus Metrics

```python
# Circuit breaker metrics
circuit_breaker_state_changes_total{name, from_state, to_state}
circuit_breaker_calls_total{name, state, result}
circuit_breaker_state{name}  # Gauge: 0=CLOSED, 1=OPEN, 2=HALF_OPEN

# Retry metrics
retry_attempts_total{function, attempt}

# Bulkhead metrics
bulkhead_rejections_total{name}
```

### Circuit Breaker Registry

Monitor all circuit breakers:

```python
from app.core.resilience import CircuitBreakerRegistry

registry = CircuitBreakerRegistry.get_instance()
states = registry.get_all_states()
# {'ocr:deepseek': CLOSED, 'external_api': OPEN, ...}
```

## Error Handling

### Custom Exceptions

**CircuitBreakerOpenError**:
```python
try:
    result = await protected_call()
except CircuitBreakerOpenError as e:
    logger.warning(
        "service_unavailable",
        service=e.service_name,
        retry_after=e.retry_after_seconds
    )
    # Queue for later processing or use fallback
```

**BulkheadFullError**:
```python
try:
    async with bulkhead:
        result = await expensive_operation()
except BulkheadFullError as e:
    logger.warning(
        "resource_limit_reached",
        service=e.service_name,
        limit=e.max_concurrent
    )
    # Return 503 Service Unavailable with Retry-After header
```

## Integration Patterns

### 1. OCR Pipeline with Full Resilience

```python
from app.core.resilience import (
    circuit_breaker,
    retry_with_backoff,
    get_ocr_circuit_breaker,
    Bulkhead
)

# Bulkhead for GPU concurrency
ocr_bulkhead = Bulkhead(name="gpu_ocr", max_concurrent=2)

@circuit_breaker("ocr_deepseek", failure_threshold=3)
@retry_with_backoff(max_retries=2, base_delay=1.0)
async def process_with_deepseek(image_path: str):
    async with ocr_bulkhead:
        return await deepseek_backend.process(image_path)

async def process_document_resilient(doc_id: str):
    try:
        result = await process_with_deepseek(doc_id)
        return result
    except CircuitBreakerOpenError:
        # Fallback to CPU-based OCR
        logger.info("ocr_fallback_to_cpu", doc_id=doc_id)
        return await surya_cpu_backend.process(doc_id)
```

### 2. API Endpoint with Graceful Degradation

```python
@router.post("/documents/{doc_id}/ocr")
@circuit_breaker("ocr_api", fallback=queue_for_later_processing)
async def trigger_ocr(
    doc_id: str,
    db: AsyncSession = Depends(get_db)
):
    document = await get_document_or_404(db, doc_id)
    result = await ocr_service.process(document)
    return {"status": "completed", "result": result}

async def queue_for_later_processing(doc_id: str, *args, **kwargs):
    # Circuit is open - queue for background processing
    await celery_app.send_task(
        "ocr.process_document",
        args=[doc_id],
        countdown=300  # Try again in 5 minutes
    )
    return {"status": "queued", "retry_after": 300}
```

## Testing

### Demo Script

Run `python test_resilience_demo.py` to verify:
- ✅ Circuit breaker state transitions
- ✅ Decorator patterns (sync/async)
- ✅ Retry with backoff
- ✅ OCR circuit breaker configuration
- ✅ Registry singleton

### Unit Tests

Location: `tests/unit/core/test_resilience.py`

**Coverage**:
- Circuit breaker state machine (all transitions)
- Thread safety
- Decorator patterns (sync/async)
- Retry with exponential backoff
- Bulkhead concurrent limits
- Registry singleton
- OCR helper configuration

**Run tests**:
```bash
# Local
pytest tests/unit/core/test_resilience.py -v

# Docker
docker-compose exec backend pytest tests/unit/core/test_resilience.py -v
```

## Best Practices

### 1. Circuit Breaker Placement

✅ **DO**: Place at service boundaries
```python
# External API calls
@circuit_breaker("payment_gateway")
async def process_payment(...)

# OCR backends
@circuit_breaker("ocr_deepseek")
async def ocr_process(...)
```

❌ **DON'T**: Place on internal functions
```python
# Internal helpers - no need for circuit breaker
def format_date(date_str: str):
    ...
```

### 2. Retry Strategy

✅ **DO**: Retry transient errors
```python
@retry_with_backoff(
    retryable_exceptions=(ConnectionError, TimeoutError, HTTPError)
)
async def call_api():
    ...
```

❌ **DON'T**: Retry validation errors
```python
# Validation errors won't fix themselves
@retry_with_backoff(retryable_exceptions=(ValidationError,))  # BAD
async def validate_input(data):
    ...
```

### 3. Combine Patterns

```python
# Layer resilience patterns
@circuit_breaker("service_x", fallback=use_cache)
@retry_with_backoff(max_retries=3)
async def call_service_x():
    async with service_bulkhead:
        return await client.get("/data")
```

**Order matters**:
1. Circuit Breaker (outermost - fast fail)
2. Retry (middle - handle transient failures)
3. Bulkhead (innermost - limit concurrency)

## Configuration

### Environment Variables

```bash
# Override circuit breaker defaults
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
CIRCUIT_BREAKER_HALF_OPEN_MAX=3

# Retry defaults
RETRY_MAX_ATTEMPTS=3
RETRY_BASE_DELAY=1.0
RETRY_MAX_DELAY=60.0
```

### Per-Service Configuration

```python
# In app/core/config.py
class CircuitBreakerConfig(BaseModel):
    ocr_backends: Dict[str, CircuitBreakerSettings] = {
        "deepseek": CircuitBreakerSettings(
            failure_threshold=3,
            recovery_timeout=120
        ),
        "got-ocr": CircuitBreakerSettings(
            failure_threshold=5,
            recovery_timeout=60
        )
    }
```

## Troubleshooting

### Circuit stays OPEN

**Symptoms**: Service permanently unavailable, no recovery

**Diagnosis**:
```python
from app.core.resilience import CircuitBreakerRegistry

registry = CircuitBreakerRegistry.get_instance()
states = registry.get_all_states()
print(states)  # Check which circuits are OPEN
```

**Solutions**:
1. Check if underlying service is actually down
2. Increase `recovery_timeout_seconds`
3. Lower `half_open_max_calls` (easier recovery)
4. Manual reset: `breaker.reset()`

### Too many retries

**Symptoms**: High latency, cascading failures

**Solutions**:
1. Lower `max_retries` (fail faster)
2. Increase `base_delay` (less aggressive)
3. Add circuit breaker (prevent retry storm)

### Bulkhead rejections

**Symptoms**: Many `BulkheadFullError` exceptions

**Solutions**:
1. Increase `max_concurrent`
2. Add queue: `max_queue=10`
3. Scale horizontally (more workers)
4. Optimize underlying operation

## Migration Guide

### From Direct Calls

**Before**:
```python
async def process_document(doc_id: str):
    return await ocr_backend.process(doc_id)
```

**After**:
```python
@circuit_breaker("ocr_backend", failure_threshold=3)
@retry_with_backoff(max_retries=2)
async def process_document(doc_id: str):
    return await ocr_backend.process(doc_id)
```

### From Manual Error Handling

**Before**:
```python
for attempt in range(3):
    try:
        return await api_call()
    except Exception:
        if attempt < 2:
            await asyncio.sleep(2 ** attempt)
        else:
            raise
```

**After**:
```python
@retry_with_backoff(max_retries=2, base_delay=1.0, exponential_base=2.0)
async def api_call():
    ...
```

## Related Documentation

- `.claude/Docs/Architecture/GPU-Resource-Management.md` - GPU VRAM limits
- `.claude/Docs/Operations/Runbooks/OCR-Backend-Failure.md` - OCR troubleshooting
- `.claude/Docs/API/ErrorCatalog.md` - Error codes
- `app/core/safe_errors.py` - Error logging patterns

## Future Enhancements

- [ ] Rate limiting integration
- [ ] Adaptive thresholds (ML-based)
- [ ] Dashboard for circuit breaker visualization
- [ ] Health check endpoints
- [ ] Distributed circuit breaker (Redis-backed)
- [ ] Timeout decorator
- [ ] Fallback chain pattern
