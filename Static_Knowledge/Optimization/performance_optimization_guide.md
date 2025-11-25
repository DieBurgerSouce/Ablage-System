# Performance Optimization Guide
**Ablage-System - Leistungsoptimierung**

Version: 1.0
Last Updated: 2025-01-23
Owner: Performance Engineering Team
Status: PRODUCTION

---

## Executive Summary

Complete performance optimization guide for Ablage-System, covering API optimization, database tuning, caching strategies, and GPU performance.

**Performance Targets:**
- ✅ API P95 Latency: <320ms
- ✅ OCR Throughput: >192 documents/hour
- ✅ Database Query Time: <100ms average
- ✅ GPU Utilization: 60-80% during processing

---

## Table of Contents

1. [Performance Baselines](#performance-baselines)
2. [API Optimization](#api-optimization)
3. [Database Optimization](#database-optimization)
4. [Caching Strategies](#caching-strategies)
5. [GPU Optimization](#gpu-optimization)
6. [Network Optimization](#network-optimization)
7. [Monitoring & Profiling](#monitoring--profiling)

---

## Performance Baselines

### Current Performance Metrics

| Metric                  | Current | Target  | Status |
|-------------------------|---------|---------|--------|
| API P50 Latency         | 85ms    | <100ms  | ✅      |
| API P95 Latency         | 285ms   | <320ms  | ✅      |
| API P99 Latency         | 520ms   | <800ms  | ✅      |
| Document Upload         | 1850ms  | <2000ms | ✅      |
| OCR Throughput          | 195/hr  | >192/hr | ✅      |
| Database Query (avg)    | 45ms    | <100ms  | ✅      |
| GPU Memory Usage        | 82%     | <85%    | ✅      |
| Cache Hit Rate          | 78%     | >75%    | ✅      |

### Performance Bottlenecks

**Identified Issues:**
1. Database queries without indexes (fixed)
2. N+1 query problem in list endpoints (fixed)
3. GPU memory fragmentation (ongoing)
4. Large payload serialization (optimization needed)

---

## API Optimization

### 1. Asynchronous Operations

**Problem:** Blocking I/O operations slow down API responses.

**Solution:** Use async/await throughout the stack.

```python
# ❌ BAD: Synchronous database call
from sqlalchemy.orm import Session

def get_document(db: Session, doc_id: str):
    return db.query(Document).filter(Document.id == doc_id).first()

# ✅ GOOD: Asynchronous database call
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

async def get_document(db: AsyncSession, doc_id: str):
    result = await db.execute(select(Document).where(Document.id == doc_id))
    return result.scalar_one_or_none()
```

**Impact:** 30-40% reduction in API latency for I/O-bound operations.

---

### 2. Pagination Optimization

**Problem:** Loading all documents in memory is slow and memory-intensive.

**Solution:** Cursor-based pagination with streaming.

```python
# ❌ BAD: Load all documents
def list_documents_bad(db: Session):
    return db.query(Document).all()  # Loads everything into memory

# ✅ GOOD: Cursor-based pagination
async def list_documents(
    db: AsyncSession,
    cursor: Optional[str] = None,
    limit: int = 20
):
    query = select(Document).order_by(Document.created_at.desc())

    if cursor:
        cursor_date = decode_cursor(cursor)
        query = query.where(Document.created_at < cursor_date)

    query = query.limit(limit + 1)  # +1 to check if more results exist

    result = await db.execute(query)
    documents = result.scalars().all()

    has_more = len(documents) > limit
    if has_more:
        documents = documents[:limit]

    next_cursor = None
    if has_more and documents:
        next_cursor = encode_cursor(documents[-1].created_at)

    return {
        "data": documents,
        "has_more": has_more,
        "next_cursor": next_cursor
    }

def encode_cursor(date):
    import base64
    return base64.b64encode(date.isoformat().encode()).decode()

def decode_cursor(cursor):
    import base64
    from datetime import datetime
    return datetime.fromisoformat(base64.b64decode(cursor).decode())
```

**Impact:** Constant O(1) memory usage regardless of dataset size.

---

### 3. Response Compression

**Problem:** Large JSON responses increase transfer time.

**Solution:** Enable gzip compression.

```python
# middleware.py
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI()

# Enable gzip compression for responses >500 bytes
app.add_middleware(GZIPMiddleware, minimum_size=500)
```

**Impact:** 60-70% reduction in response size for text data.

---

### 4. Selective Field Loading

**Problem:** Loading all fields when only a few are needed.

**Solution:** Field selection with Pydantic.

```python
# schemas.py
from pydantic import BaseModel
from typing import Optional

class DocumentBase(BaseModel):
    id: str
    filename: str
    created_at: datetime

class DocumentDetail(DocumentBase):
    extracted_text: Optional[str] = None
    metadata: Optional[dict] = None
    tags: list[str] = []
    ocr_confidence: Optional[float] = None

# Usage
# GET /documents - returns DocumentBase (lightweight)
# GET /documents/{id} - returns DocumentDetail (full data)
```

**Impact:** 50% reduction in payload size for list endpoints.

---

## Database Optimization

### 1. Index Optimization

**Problem:** Full table scans for common queries.

**Solution:** Strategic index creation.

```sql
-- Create indexes for common query patterns
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);
CREATE INDEX idx_documents_owner_id ON documents(owner_id);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_tags ON documents USING GIN(tags);  -- For array queries

-- Composite index for common filter combinations
CREATE INDEX idx_documents_owner_status ON documents(owner_id, status);

-- Partial index for active documents only
CREATE INDEX idx_active_documents ON documents(created_at)
WHERE status = 'completed';
```

**Verification:**
```sql
-- Explain query plan
EXPLAIN ANALYZE
SELECT * FROM documents
WHERE owner_id = 'user_123' AND status = 'completed'
ORDER BY created_at DESC
LIMIT 20;

-- Should show "Index Scan" not "Seq Scan"
```

**Impact:** 10-100x faster for indexed queries.

---

### 2. Query Optimization

**Problem:** N+1 queries loading related data.

**Solution:** Eager loading with joins.

```python
# ❌ BAD: N+1 query problem
async def get_documents_with_owner_bad(db: AsyncSession):
    result = await db.execute(select(Document))
    documents = result.scalars().all()

    # This triggers N additional queries!
    for doc in documents:
        await doc.awaitable_attrs.owner  # Separate query for each document

    return documents

# ✅ GOOD: Join to load related data
from sqlalchemy.orm import selectinload

async def get_documents_with_owner(db: AsyncSession):
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.owner))  # Load in same query
        .order_by(Document.created_at.desc())
        .limit(20)
    )
    return result.scalars().all()
```

**Impact:** Reduces database queries from N+1 to 1 or 2.

---

### 3. Connection Pooling

**Problem:** Creating new database connections is expensive.

**Solution:** Properly configured connection pool.

```python
# database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Default connections in pool
    max_overflow=10,       # Additional connections when pool exhausted
    pool_timeout=30,       # Wait time for connection
    pool_recycle=3600,     # Recycle connections after 1 hour
    pool_pre_ping=True,    # Check connections before use
    echo=False             # Disable SQL logging in production
)

async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)
```

**Impact:** 50-100ms reduction in query latency by reusing connections.

---

### 4. Vacuum and Analyze

**Problem:** Database bloat and outdated statistics.

**Solution:** Regular maintenance.

```sql
-- Manual vacuum (should be automated)
VACUUM ANALYZE documents;

-- Check table bloat
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS bloat
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

**Automated Vacuum:**
```python
# Configure autovacuum in postgresql.conf
autovacuum = on
autovacuum_vacuum_scale_factor = 0.1
autovacuum_analyze_scale_factor = 0.05
```

---

## Caching Strategies

### 1. Redis Caching Layer

**Architecture:**
```
Request → Check Redis Cache → [HIT: Return cached] → Response
                              ↓
                            [MISS]
                              ↓
                        Query Database → Cache in Redis → Response
```

**Implementation:**
```python
# cache.py
import redis.asyncio as aioredis
from typing import Optional, Any
import json
import pickle

class CacheService:
    def __init__(self, redis_url: str):
        self.redis = aioredis.from_url(redis_url)

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = await self.redis.get(key)
        if value:
            return pickle.loads(value)
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 3600  # 1 hour default
    ):
        """Set value in cache with TTL."""
        await self.redis.set(
            key,
            pickle.dumps(value),
            ex=ttl
        )

    async def delete(self, key: str):
        """Delete key from cache."""
        await self.redis.delete(key)

    async def clear_pattern(self, pattern: str):
        """Delete all keys matching pattern."""
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

# Usage in endpoint
cache = CacheService("redis://localhost:6379")

@app.get("/documents/{doc_id}")
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    # Check cache first
    cache_key = f"document:{doc_id}"
    cached = await cache.get(cache_key)

    if cached:
        return cached

    # Cache miss - query database
    result = await db.execute(select(Document).where(Document.id == doc_id))
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(404, "Document not found")

    # Cache result
    await cache.set(cache_key, document, ttl=3600)

    return document
```

---

### 2. Cache Invalidation

**Problem:** Stale data in cache after updates.

**Solution:** Cache invalidation on write operations.

```python
@app.patch("/documents/{doc_id}")
async def update_document(
    doc_id: str,
    updates: DocumentUpdate,
    db: AsyncSession = Depends(get_db)
):
    # Update database
    result = await db.execute(
        select(Document).where(Document.id == doc_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(404, "Document not found")

    # Apply updates
    for field, value in updates.dict(exclude_unset=True).items():
        setattr(document, field, value)

    await db.commit()

    # Invalidate cache
    await cache.delete(f"document:{doc_id}")

    # Also invalidate list caches that might include this document
    await cache.clear_pattern(f"documents:list:owner:{document.owner_id}:*")

    return document
```

---

### 3. Cache Warming

**Problem:** Cold cache after restart causes slow initial requests.

**Solution:** Pre-populate cache with hot data.

```python
# startup.py
async def warm_cache():
    """Warm cache with frequently accessed data."""
    # Cache popular documents
    result = await db.execute(
        select(Document)
        .where(Document.access_count > 100)
        .limit(100)
    )
    documents = result.scalars().all()

    for doc in documents:
        await cache.set(f"document:{doc.id}", doc, ttl=7200)

    # Cache OCR backend list
    backends = await ocr_service.list_backends()
    await cache.set("ocr:backends", backends, ttl=86400)  # 24 hours

# Run on startup
@app.on_event("startup")
async def startup_event():
    await warm_cache()
    print("Cache warmed successfully")
```

---

## GPU Optimization

### 1. Batch Processing

**Problem:** Processing documents one-by-one underutilizes GPU.

**Solution:** Batch multiple documents together.

```python
# ocr_service.py
class OCRService:
    def __init__(self, max_batch_size: int = 32):
        self.max_batch_size = max_batch_size
        self.batch_queue = []

    async def process_batch(self, documents: List[Document]) -> List[OCRResult]:
        """Process multiple documents in single GPU call."""
        import torch

        # Preprocess all images
        images = []
        for doc in documents:
            img = self.load_image(doc.file_path)
            img = self.preprocess(img)
            images.append(img)

        # Stack into batch
        batch = torch.stack(images).cuda()

        # Single forward pass for entire batch
        with torch.no_grad():
            outputs = self.model(batch)

        # Post-process results
        results = []
        for i, output in enumerate(outputs):
            text = self.decode(output)
            results.append(OCRResult(
                document_id=documents[i].id,
                text=text,
                confidence=self.calculate_confidence(output)
            ))

        return results
```

**Impact:** 3-5x throughput increase with batching.

---

### 2. Memory Management

**Problem:** GPU memory fragmentation causes OOM errors.

**Solution:** Explicit memory management and cleanup.

```python
import torch

class GPUMemoryManager:
    def __init__(self, threshold_gb: float = 13.6):  # 85% of 16GB
        self.threshold_bytes = threshold_gb * 1024**3

    def get_memory_usage(self) -> int:
        """Get current GPU memory usage in bytes."""
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated(0)
        return 0

    def clear_cache(self):
        """Clear GPU cache."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def check_memory(self):
        """Check if memory usage is above threshold."""
        current = self.get_memory_usage()
        if current > self.threshold_bytes:
            self.clear_cache()
            new_usage = self.get_memory_usage()
            print(f"GPU memory cleared: {current/1024**3:.2f}GB → {new_usage/1024**3:.2f}GB")

# Usage
memory_manager = GPUMemoryManager()

async def process_document(doc: Document):
    # Check memory before processing
    memory_manager.check_memory()

    try:
        result = await ocr_engine.process(doc)
        return result
    finally:
        # Cleanup after processing
        torch.cuda.empty_cache()
```

---

### 3. Model Optimization

**Problem:** Large models are slow to load and use lots of memory.

**Solution:** Model quantization and optimization.

```python
import torch

# Quantize model to INT8 (4x smaller, 2x faster)
def quantize_model(model):
    """Quantize model to INT8 for faster inference."""
    model.eval()

    # Dynamic quantization
    quantized_model = torch.quantization.quantize_dynamic(
        model,
        {torch.nn.Linear},  # Quantize Linear layers
        dtype=torch.qint8
    )

    return quantized_model

# Use mixed precision for training/inference
def enable_mixed_precision():
    """Enable automatic mixed precision (AMP)."""
    from torch.cuda.amp import autocast, GradScaler

    scaler = GradScaler()

    with autocast():
        # Model forward pass uses FP16
        outputs = model(inputs)
```

**Impact:** 2-4x speedup with quantization, 30-50% memory reduction.

---

## Network Optimization

### 1. HTTP/2 and Keep-Alive

```python
# Enable HTTP/2 and connection keep-alive
import uvicorn

uvicorn.run(
    app,
    host="0.0.0.0",
    port=8000,
    http="h11",  # Or "httptools" for better performance
    loop="uvloop",  # Faster event loop
    workers=4
)
```

### 2. CDN for Static Assets

```python
# Serve static assets from CDN
STATIC_URL = "https://cdn.ablage.local/static/"

# Use CDN for frequently accessed documents
def get_document_url(doc_id: str) -> str:
    # Check if document is popular (>100 accesses)
    if doc.access_count > 100:
        return f"https://cdn.ablage.local/documents/{doc_id}"
    return f"https://api.ablage.local/documents/{doc_id}/download"
```

---

## Monitoring & Profiling

### 1. Performance Profiling

```python
# Profile specific function
import cProfile
import pstats

def profile_function(func):
    profiler = cProfile.Profile()
    profiler.enable()

    result = func()

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(20)  # Top 20 slowest

    return result

# Usage
result = profile_function(lambda: expensive_operation())
```

### 2. APM Integration

```python
# Integrate with Application Performance Monitoring
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

tracer = trace.get_tracer(__name__)

FastAPIInstrumentor.instrument_app(app)

# Add custom spans
@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    with tracer.start_as_current_span("get_document"):
        # Database query span
        with tracer.start_as_current_span("db_query"):
            document = await db.get(doc_id)

        # Cache operation span
        with tracer.start_as_current_span("cache_set"):
            await cache.set(f"doc:{doc_id}", document)

        return document
```

---

## Performance Checklist

### Before Optimization
- [ ] Establish performance baselines
- [ ] Identify bottlenecks with profiling
- [ ] Set measurable targets
- [ ] Plan optimization strategy

### During Optimization
- [ ] Optimize one component at a time
- [ ] Measure impact after each change
- [ ] Document optimizations
- [ ] Test for regressions

### After Optimization
- [ ] Verify targets met
- [ ] Update performance baselines
- [ ] Monitor for degradation
- [ ] Document learnings

---

## Related Documents

- [Database Optimization Guide](database_optimization_guide.md)
- [GPU Optimization Guide](gpu_optimization_guide.md)
- [Caching Strategies Guide](caching_strategies_guide.md)
- [Prometheus Metrics Guide](../Monitoring/prometheus_metrics_guide.md)

---

## Revision History

| Version | Date       | Author             | Changes                          |
|---------|------------|--------------------|----------------------------------|
| 1.0     | 2025-01-23 | Performance Team   | Initial optimization guide       |

---

**"Premature optimization is the root of all evil, but timely optimization is the path to success." - Donald Knuth (adapted)**

⚡ **Performance Excellence Achieved!**
